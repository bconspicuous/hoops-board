"""Week-N streaming optimizer for one roster slot (v2.2 model: real daily schedule, daily lineup fill, back-to-back layer).
The 12 kept players fill the 10 daily starting slots first (by value); the streamer plays only if a slot he can fill is
still open that day. Plans = who holds the slot each day; each change of holder costs one acquisition.
Objective: P(win the H2H week, >= 6 of 11 categories) vs the opponent's projected week."""
import json, math, sys, os, hashlib
import numpy as np
REF = json.load(open("/home/claude/hoops-board/src/ref22.json")); ROS = json.load(open(os.environ.get("ROSTERS", "/home/claude/hoops-board/src/data/rosters.json")))
F = REF["fields"]; PL = {a[0]: dict(zip(F, a)) for a in REF["players"]}
KEYS = ["FGM", "FGA", "FTM", "FTA", "TPM", "REB", "AST", "STL", "BLK", "TO", "PTS", "PF", "DDg"]; KI = {k: i for i, k in enumerate(KEYS)}
CATS = ["FG", "FT", "TPM", "REB", "AST", "STL", "BLK", "TO", "DD", "PTS", "PF"]; LOW = {"TO", "PF"}
CV = dict(PTS=.40, REB=.45, AST=.55, STL=.85, BLK=1.0, TPM=.75, TO=.60, PF=.45); PCT_SD = dict(FG=.018, FT=.030)
POSB = dict(PG=1, SG=2, SF=4, PF=8, C=16); SLOTM = [1, 2, 4, 8, 16, 3, 12, 31, 31, 31]
W = int(os.environ.get("WEEK", 0)); D = int(os.environ.get("DRAWS", 400)); B2B = os.environ.get("B2B", "1") == "1"
sched, b2bd = REF["sched"][W], REF["b2bd"][W]; ND = len(sched)
STATUS = ROS.get("status", {})
def mask(p): m = POSB.get(p["pos"], 0); [m := m | POSB.get(e, 0) for e in p["elig"].split(",")]; return m
def b2bp(n): x = REF["b2bp"].get(n); return (x[0], x[1]) if x else (.02, .5)
def avail(p, per_game=False):
    g = 1.0 if per_game else min(1.0, p["gp"] / 82); pN = pB = g
    if B2B and p["team"]:
        s = REF["b2bShare"].get(p["team"], .18); r0 = 0 if per_game else b2bp(p["name"])[0]; h = g / (1 - s * r0); r = r0
        if h > 1: h = 1; r = max(0, (1 - g) / s)
        pN, pB = h, h * (1 - r)
    st = STATUS.get(p["name"], p.get("status") or "")
    if W == 0 or os.environ.get("CURWEEK") == str(W):
        if st == "O": pN = pB = 0
        elif st == "DTD": pN *= .8; pB *= .8
    return pN, pB
def vecs(p):
    v = np.array([p[k] or 0 for k in KEYS], float)
    if not B2B: return v, v
    k = b2bp(p["name"])[1]; fx = REF["b2bFx"]; o = dict(zip(KEYS, v)); fgp = o["FGM"] / o["FGA"] if o["FGA"] else 0; ftp = o["FTM"] / o["FTA"] if o["FTA"] else 0
    FGA, FTA = o["FGA"] * (1 + k * fx["FGA"]), o["FTA"] * (1 + k * fx["FTA"])
    r = dict(FGA=FGA, FGM=FGA * max(0, fgp + k * fx["FGp"]), FTA=FTA, FTM=FTA * max(0, ftp + k * fx["FTp"]))
    for key in ["TPM", "REB", "AST", "STL", "BLK", "TO", "PTS", "PF", "DDg"]: r[key] = o[key] * (1 + k * fx[key])
    return v, np.array([r[k] for k in KEYS])
def plays(p, per_game=False):
    """(D, ND) int8: 0 no game/out, 1 normal game, 2 2nd night of a back-to-back; common random numbers per player."""
    out = np.zeros((D, ND), np.int8)
    if not p["team"]: return out
    rng = np.random.default_rng(int(hashlib.md5(f"{W}|{p['name']}".encode()).hexdigest()[:8], 16)); u = rng.random((D, ND)); pN, pB = avail(p, per_game)
    for d in range(ND):
        if p["team"] in sched[d]:
            isb = p["team"] in b2bd[d]; out[:, d] = np.where(u[:, d] < (pB if isb else pN), 2 if isb else 1, 0)
    return out
def fill_base(names):
    """Greedy daily fill for kept players. Returns per-draw totals (D, K), games used, and free-slot bitmask (D, ND)."""
    ps = sorted([PL[n] for n in names], key=lambda p: -p["value"]); pl = [plays(p) for p in ps]; vv = [vecs(p) for p in ps]; mk = [mask(p) for p in ps]
    tot = np.zeros((D, len(KEYS))); free = np.zeros((D, ND), np.int32); n = 0.0
    for k in range(D):
        for d in range(ND):
            fr = 1023
            for j, p in enumerate(ps):
                st = pl[j][k, d]
                if not st: continue
                for s in range(10):
                    if (fr >> s & 1) and (SLOTM[s] & mk[j]): fr &= ~(1 << s); tot[k] += vv[j][st - 1]; n += 1; break
            free[k, d] = fr
    return tot, n / D, free
def slot_open(free, m):
    ok = np.zeros(free.shape, bool)
    for s in range(10):
        if SLOTM[s] & m: ok |= (free >> s & 1).astype(bool)
    return ok
def summarize(tot, n):
    m = tot.mean(0); c = {x: m[KI[x]] for x in ["TPM", "REB", "AST", "STL", "BLK", "TO", "PTS", "PF"]}; c["DD"] = m[KI["DDg"]]
    c["FG"] = m[KI["FGM"]] / max(m[KI["FGA"]], 1e-9); c["FT"] = m[KI["FTM"]] / max(m[KI["FTA"]], 1e-9)
    sv = {x: tot[:, KI[x]].var() for x in ["TPM", "REB", "AST", "STL", "BLK", "TO", "PTS", "PF"]}; sv["DD"] = tot[:, KI["DDg"]].var()
    sv["FG"] = (tot[:, KI["FGM"]] / np.maximum(tot[:, KI["FGA"]], 1e-9)).var(); sv["FT"] = (tot[:, KI["FTM"]] / np.maximum(tot[:, KI["FTA"]], 1e-9)).var()
    return dict(c=c, sv=sv, n=n)
def msd(o, c):
    n = max(o["n"], 1); sv = o["sv"][c]
    if c in PCT_SD: return o["c"][c], math.sqrt((PCT_SD[c] * math.sqrt(35 / n)) ** 2 + sv)
    if c == "DD": return o["c"][c], math.sqrt(max(o["c"][c], 1e-6) + sv)
    return o["c"][c], math.sqrt((CV[c] * o["c"][c] / math.sqrt(n)) ** 2 + sv)
def pcat(a, b):
    out = {}
    for c in CATS:
        (ma, sa), (mb, sb) = msd(a, c), msd(b, c); p = .5 * (1 + math.erf((ma - mb) / math.sqrt(sa * sa + sb * sb + 1e-12) / math.sqrt(2))); out[c] = 1 - p if c in LOW else p
    return out
def pwin(a, b):
    dist = [1.0]
    for p in pcat(a, b).values():
        nd = [0.0] * (len(dist) + 1)
        for k, q in enumerate(dist): nd[k] += q * (1 - p); nd[k + 1] += q * p
        dist = nd
    return sum(dist[6:])
INTC = {"TPM", "REB", "AST", "STL", "BLK", "TO", "DD", "PTS", "PF"}
def pcat3(a, b):
    """per category (P(win), P(tie), P(loss)) for a; integer totals tie when |diff| < 0.5 (continuity correction), FG%/FT% never tie"""
    P = lambda x: .5 * (1 + math.erf(x / math.sqrt(2))); out = {}
    for c in CATS:
        (ma, sa), (mb, sb) = msd(a, c), msd(b, c); s = math.sqrt(sa * sa + sb * sb + 1e-12); d = ma - mb
        hi, lo = ((1 - P((.5 - d) / s), P((-.5 - d) / s)) if c in INTC else (P(d / s), 1 - P(d / s)))
        ti = max(0.0, 1 - hi - lo); out[c] = (lo, ti, hi) if c in LOW else (hi, ti, lo)
    return out
def pmatch(a, b):
    """objective = expected category win share for the week, (W + T/2) / 11 — the league ranks by cumulative category win%"""
    return sum(w + t / 2 for w, t, l in pcat3(a, b).values()) / len(CATS)

# ---------------- planner ----------------
def optimize(keep, slot, opp_sum, pool, A, avail_from, topc=16, beam_w=120, regap=2):
    """Best day-by-day holder sequence for one slot. keep = the other roster players; slot = current holder.
    Re-adding a player we dropped is allowed `regap` days after the drop (league waiver rule); players with
    avail_from[d] > d are still on waivers (claim not assumed). Returns (p, seq, acq, summary, n_slot_games)."""
    tb, nb, free = fill_base(keep); CON, GMS = {}, {}
    for n in set(pool) | {slot}:
        p = PL[n]; pl = plays(p, per_game=True); ok = slot_open(free, mask(p)); v0, v1 = vecs(p)
        use = (pl > 0) & ok; CON[n] = use[:, :, None] * np.where((pl == 2)[:, :, None], v1, v0); GMS[n] = use.mean(0)
    def evaluate(h):
        tot = tb.copy(); n = nb
        for d, x in enumerate(h):
            if x: tot += CON[x][:, d, :]; n += GMS[x][d]
        return summarize(tot, n)
    sc = lambda h: pmatch(evaluate(h), opp_sum)
    short = {}
    for d in range(ND):
        lst = []
        for n in pool:
            if n == slot or GMS[n][d] < .05 or avail_from.get(n, 0) > d: continue
            h = [None] * ND; h[d] = n; lst.append((sc(h), n))
        short[d] = [n for _, n in sorted(lst, reverse=True)[:topc]]
    def can_add(c, hist, d):
        if avail_from.get(c, 0) > d: return False
        if c not in hist: return True
        last = max(i for i, x in enumerate(hist) if x == c)          # last day held (hist index = day)
        return d >= last + 1 + regap                                  # dropped on last+1, back after regap days
    states = [((), 0)]
    for d in range(ND):
        nxt = set()
        for hist, acq in states:
            prev = hist[-1] if hist else slot
            nxt.add((hist + (prev,), acq))
            if acq < A:
                for c in short[d]:
                    if c != prev and (c != slot or hist) and can_add(c, list(hist) if hist else [slot], d): nxt.add((hist + (c,), acq + 1))
        cand = sorted(((sc(list(h) + [None] * (ND - d - 1)), h, a) for h, a in nxt), key=lambda x: -x[0])
        states = [(h, a) for _, h, a in cand[:beam_w]]
    fin = sorted(((sc(list(h)), list(h), a) for h, a in states), key=lambda x: -x[0])
    byA = {}
    for s, h, a in fin: byA.setdefault(a, (s, h))
    s, h, a = fin[0]; ev = evaluate(h)
    return dict(p=s, seq=h, acq=a, sum=ev, byA=byA, short=short, gms={x: GMS[x] for x in set(h)}, base=sc([slot] * ND), none=sc([None] * ND), evaluate=evaluate)

if __name__ == "__main__":
    import datetime as dt
    ME, SLOT = "Garak Twindragons", os.environ.get("SLOT", "John Collins")
    GADD = [x for x in os.environ.get("OPP_ADD", "Derik Queen").split("|") if x]
    RULE_ACQ = round(7 * len(REF["sched"][int(os.environ.get("WEEK", 0))]) / 7)   # league rule: 7 adds per 7-day matchup, prorated
    A = int(os.environ.get("ACQ", RULE_ACQ)); OA = int(os.environ.get("OPP_ACQ", RULE_ACQ))
    AVAIL = {n: int(d) for n, d in (x.split("=") for x in os.environ.get("AVAIL_FROM", "Coby White=1|Jaden McDaniels=1|Reed Sheppard=1|DeMar DeRozan=1|RJ Barrett=1").split("|") if x)}
    opp_team = next(b if a == ME else a for a, b in REF["matchups"][W] if ME in (a, b))
    T = ROS["teams"]; mine = [n for n in T[ME]["active"] if n != SLOT]; opp_all = T[opp_team]["active"] + GADD
    OSLOT = os.environ.get("OPP_SLOT") or min(opp_all, key=lambda n: PL[n]["value"]); opp_keep = [n for n in opp_all if n != OSLOT]
    rostered = {n for t in T.values() for n in t["active"] + t.get("ir", [])} | set(GADD)
    def pool_for(keep, cmax=4):
        cb = sum(1 for n in keep if PL[n]["pos"] == "C")
        return [n for n, p in PL.items() if n not in rostered and p["team"] and (STATUS.get(n) or p.get("status") or "") != "O" and not (p["pos"] == "C" and cb >= cmax)]
    # 1) opponent without streaming, 2) our plan vs that, 3) opponent best-response streaming vs our plan, 4) our plan vs streaming opponent
    to, no, _ = fill_base(opp_all); OPP0 = summarize(to, no)
    r0 = optimize(mine, SLOT, OPP0, pool_for(mine), A, AVAIL)
    ours0 = r0["sum"]; base_static = pmatch(summarize(*fill_base(mine + [SLOT])[:2]), OPP0)
    ro = optimize(opp_keep, OSLOT, ours0, [n for n in pool_for(opp_keep)], OA, AVAIL)
    OPP1 = ro["sum"]
    r1 = optimize(mine, SLOT, OPP1, pool_for(mine), A, AVAIL)
    keep_vs_stream = pmatch(summarize(*fill_base(mine + [SLOT])[:2]), OPP1)
    d0 = dt.date.fromisoformat(REF["starts"][W]); days = [(d0 + dt.timedelta(days=d)).strftime("%m/%d %a") for d in range(ND)]
    nm = lambda s: [x if x else "-" for x in s]
    out = dict(week=W + 1, days=days, opp=opp_team, opp_add=GADD, opp_slot=OSLOT,
               static=dict(keep=base_static, plan=r0["p"], seq=r0["seq"], acq=r0["acq"]),
               opp_stream=dict(seq=ro["seq"], acq=ro["acq"], opp_p_vs_our_plan=ro["p"]),
               vs_streaming_opp=dict(keep=keep_vs_stream, plan=r1["p"], seq=r1["seq"], acq=r1["acq"], byA={a: dict(p=s, seq=h) for a, (s, h) in sorted(r1["byA"].items())}),
               cats_keep_vs_stream=pcat(summarize(*fill_base(mine + [SLOT])[:2]), OPP1), cats_plan_vs_stream=pcat(r1["sum"], OPP1), cats_plan_vs_static=pcat(r0["sum"], OPP0),
               overlap=[(days[d], r1["seq"][d]) for d in range(ND) if r1["seq"][d] and r1["seq"][d] == ro["seq"][d]],
               shortlist={days[d]: [(n, PL[n]["team"], PL[n]["pos"], PL[n]["AST"], PL[n]["STL"]) for n in r1["short"][d][:6]] for d in range(ND)})
    json.dump(out, open(os.environ.get("OUT", "/home/claude/nba/stream22/plan2.json"), "w"), ensure_ascii=False, indent=1, default=float)
    print("opp slot:", OSLOT, "| static: keep %.1f -> plan %.1f" % (base_static * 100, r0["p"] * 100), nm(r0["seq"]))
    print("opp streams:", nm(ro["seq"]), "acq", ro["acq"])
    print("vs streaming opp: keep %.1f -> plan %.1f" % (keep_vs_stream * 100, r1["p"] * 100), nm(r1["seq"]), "acq", r1["acq"])
    for a, (s, h) in sorted(r1["byA"].items()): print("  acq", a, round(s * 100, 1), nm(h))
    print("overlap:", out["overlap"])
