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
def pmatch(a, b): x, y = pwin(a, b), pwin(b, a); return x / (x + y)

# ---------------- planner ----------------
if __name__ == "__main__":
    ME, SLOT = "Garak Twindragons", os.environ.get("SLOT", "John Collins")
    GADD = [x for x in os.environ.get("OPP_ADD", "Derik Queen").split("|") if x]
    A = int(os.environ.get("ACQ", 6)); TOPC = int(os.environ.get("TOPC", 14)); BEAM = int(os.environ.get("BEAM", 60))
    WAIVER = {n: 1 for n in os.environ.get("WAIVER", "Coby White|Jaden McDaniels|Reed Sheppard|DeMar DeRozan|RJ Barrett").split("|") if n}
    opp_team = next(b if a == ME else a for a, b in REF["matchups"][W] if ME in (a, b))
    T = ROS["teams"]; mine = [n for n in T[ME]["active"] if n != SLOT]
    opp = T[opp_team]["active"] + GADD
    rostered = {n for t in T.values() for n in t["active"] + t.get("ir", [])} | set(GADD)
    CMAX = int(os.environ.get("CMAX", 4)); c_base = sum(1 for n in mine if PL[n]["pos"] == "C")
    pool = [n for n, p in PL.items() if n not in rostered and p["team"] and (STATUS.get(n) or p.get("status") or "") != "O"
            and not (p["pos"] == "C" and c_base >= CMAX)] + [SLOT]
    print("centers kept:", c_base, "-> C streamers allowed:", c_base < CMAX, flush=True)
    to, no, _ = fill_base(opp); OPP = summarize(to, no)
    tb, nb, free = fill_base(mine)
    CON, GMS = {}, {}
    for n in pool:
        p = PL[n]; pl = plays(p, per_game=True); ok = slot_open(free, mask(p)); v0, v1 = vecs(p)
        use = (pl > 0) & ok; CON[n] = use[:, :, None] * np.where((pl == 2)[:, :, None], v1, v0)[:, :, :]; GMS[n] = use.mean(0)
    def evaluate(h):
        tot = tb.copy(); n = nb
        for d, x in enumerate(h):
            if x: tot += CON[x][:, d, :]; n += GMS[x][d]
        return summarize(tot, n)
    def score(h): return pmatch(evaluate(h), OPP)
    base_h = [SLOT] * ND; base = score(base_h); none = score([None] * ND)
    # per-day candidate shortlist by single-day marginal effect
    short = {}
    for d in range(ND):
        sc = []
        for n in pool:
            if n == SLOT or GMS[n][d] < .05 or WAIVER.get(n, 0) > d: continue
            h = [None] * ND; h[d] = n; sc.append((score(h), n))
        short[d] = [n for _, n in sorted(sc, reverse=True)[:TOPC]]
    # beam search over day-by-day holders (contiguous holding, no re-adds, <= A changes)
    beam = [(base, (SLOT,), 0)]
    for d in range(1, ND + 1):
        pass
    states = [((SLOT,), 0)]  # holders for days [0..d)
    beam = []
    for d in range(ND):
        nxt = {}
        for hist, acq in states:
            prev = hist[-1] if hist else SLOT
            opts = [(prev, acq)] + [(c, acq + 1) for c in short[d] if c not in hist and c != prev and acq + 1 <= A]
            for c, a2 in opts:
                h = list(hist[1:] if hist and hist[0] == SLOT and len(hist) == d + 1 else hist)
                nxt[(tuple(hist) + (c,), a2)] = None
        cand = []
        for (hist, a2) in nxt:
            seq = list(hist[1:]) + [None] * (ND - d - 1)          # hist[0] is the initial holder marker
            cand.append((score(seq), hist, a2))
        cand.sort(key=lambda x: -x[0]); states = [(h, a) for _, h, a in cand[:BEAM]]
        best_partial = cand[0]
    final = []
    for hist, a2 in states:
        seq = list(hist[1:]); final.append((score(seq), seq, a2))
    final.sort(key=lambda x: -x[0])
    best_by_a = {}
    for s, seq, a2 in final:
        if a2 not in best_by_a: best_by_a[a2] = (s, seq)
    days = []
    import datetime as dt
    d0 = dt.date.fromisoformat(REF["starts"][W])
    for d in range(ND): days.append((d0 + dt.timedelta(days=d)).strftime("%m/%d %a"))
    bs, bseq, ba = final[0]; ev = evaluate(bseq); evb = evaluate(base_h)
    out = dict(week=W + 1, opp=opp_team, opp_add=GADD, days=days, base=base, empty_slot=none, best=dict(p=bs, seq=bseq, acq=ba),
               by_acq={a: dict(p=s, seq=q) for a, (s, q) in sorted(best_by_a.items())},
               cats_base=pcat(evb, OPP), cats_best=pcat(ev, OPP), games_base=evb["n"], games_best=ev["n"], opp_games=OPP["n"],
               slot_games_base=[float(GMS[SLOT][d]) for d in range(ND)], slot_games_best=[float(GMS[x][d]) if x else 0 for d, x in enumerate(bseq)],
               open_slot_rate=[float(np.mean(free[:, d] > 0)) for d in range(ND)], teams_playing=[len(s) for s in sched],
               shortlist={days[d]: [(n, PL[n]["team"], PL[n]["pos"], round(float(GMS[n][d]), 2)) for n in short[d][:6]] for d in range(ND)},
               means_base={c: float(evb["c"][c]) for c in CATS}, means_best={c: float(ev["c"][c]) for c in CATS}, means_opp={c: float(OPP["c"][c]) for c in CATS})
    json.dump(out, open(os.environ.get("OUT", "/home/claude/nba/stream22/plan.json"), "w"), ensure_ascii=False, indent=1)
    print(json.dumps({k: out[k] for k in ("base", "empty_slot", "best", "open_slot_rate", "teams_playing")}, ensure_ascii=False))
    for a, v in out["by_acq"].items(): print(a, round(v["p"] * 100, 1), v["seq"])
