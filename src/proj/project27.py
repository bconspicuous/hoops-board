"""2026-27 projection = ESPN projection combined with a 6-season weighted linear regression of each player's
Basketball-Reference record (2020-21 .. 2025-26), by inverse variance.

  regression  : per stat, WLS of per-game value on season (weights = games x recency^age-of-season), slope shrunk by
                (n-1)/(n-1+K_SHRINK); predicts season 2027. FG%/FT% are regressed on attempts-weighted percentages and
                converted back to makes. Players without a 2025-26 record are projected from their latest seasons
                (extra variance per missing year). DD rate: per-game normal model for PTS/REB/AST >= 10 fitted on
                2025-26, times the player's own shrunk DD calibration.
  variance    : sigma_R(stat, n) = pooled backtest relative RMSE (2021-25 -> 2026, same method) x sqrt((1+1/n)/mean(1+1/n)) x level,
                inflated when the
                player changed teams (x TEAM_VAR) or skipped seasons. sigma_E = sqrt(KAPPA) x the pooled sigma_R.
                w_R = sigma_E^2 / (sigma_E^2 + sigma_R^2), bounded to [W_MIN, W_MAX].
  rookies     : no NBA record -> NCAA 2025-26 per-game translated to the NBA (fixed factors) weighted W_NCAA against ESPN,
                when proj/ncaa.json has the player; otherwise ESPN only.
  in-season   : not here — the dashboard blends 2026-27 actual per-game stats by week (10/30/50/70/90 %).
  out         : ref27_base.json (ESPN file format: per-game fields replaced, value/vpg shifted by the same valuation)
                with ref["proj"] = per-player rationale and ref["projMeta"] = method + backtest table.
"""
import json, math, os, sys, statistics as st
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from brload import load_all

T_STAR = 2027
DELTA = float(os.environ.get("DELTA", "0.75"))        # recency factor per season back
K_SHRINK = float(os.environ.get("K_SHRINK", "4"))     # slope shrinkage
KAPPA = float(os.environ.get("KAPPA", "0.8"))         # ESPN error variance / full-history regression error variance  [assumption]
TEAM_VAR = 2.0                                         # regression variance multiplier after a team change              [assumption]
GAP_VAR = 0.5                                          # +50% variance per season without a record                       [assumption]
W_MIN, W_MAX = 0.10, 0.60
W_NCAA = 0.30
MIN_G = 10
CNT = ["FGA", "FTA", "TPM", "REB", "AST", "STL", "BLK", "TO", "PF", "PTS"]
FLOOR = {"FGA": 2, "FTA": 1, "TPM": .5, "REB": 1, "AST": .5, "STL": .3, "BLK": .3, "TO": .5, "PF": .8, "PTS": 2, "FGp": .40, "FTp": .70}
NCAA_TR = {"PTS": .62, "REB": .80, "AST": .70, "STL": .75, "BLK": .75, "TPM": .60, "TO": .85, "PF": .85, "FGA": .66, "FTA": .55, "FGp": -.035, "FTp": 0.0}

ref = json.load(open("ref22_espn.json")); F = ref["fields"]; P = [dict(zip(F, r)) for r in ref["players"]]
H = json.load(open("data/hist.json"))["players"]
NC = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "ncaa.json"))) if os.path.exists(os.path.join(os.path.dirname(os.path.abspath(__file__)), "ncaa.json")) else {}
names = [p["name"] for p in P]
seasons, _ = load_all(names)
for n in names:                                        # 2025-26: complete record (ESPN actuals == BR, verified) incl. DD
    h = H.get(n) or {}
    if h.get("pg26") and (h.get("gp26") or 0) > 0:
        r = seasons[n].get(2026) or {"team": None}
        r.update({k: h["pg26"][k] for k in ["FGM", "FGA", "FTM", "FTA", "TPM", "REB", "AST", "STL", "BLK", "TO", "PTS", "PF"]})
        r["G"] = h["gp26"]; r["DDg"] = h["pg26"]["DDg"]; seasons[n][2026] = r

def pts_of(rows, stat, upto):
    out = []
    for t, r in rows.items():
        if t >= upto or r["G"] < MIN_G: continue
        w = r["G"] * DELTA ** (upto - 1 - t)
        if stat == "FGp":
            if r["FGA"] <= 0: continue
            out.append((t, r["FGM"] / r["FGA"], w * r["FGA"]))
        elif stat == "FTp":
            if r["FTA"] <= 0: continue
            out.append((t, r["FTM"] / r["FTA"], w * r["FTA"]))
        else: out.append((t, r[stat], w))
    return out

def wls(pts, tstar):
    W = sum(w for _, _, w in pts); tb = sum(w * t for t, _, w in pts) / W; yb = sum(w * y for _, y, w in pts) / W
    Sxx = sum(w * (t - tb) ** 2 for t, _, w in pts); n = len(pts); b = 0.0
    if n >= 2 and Sxx > 0:
        b = sum(w * (t - tb) * (y - yb) for t, y, w in pts) / Sxx * (n - 1) / (n - 1 + K_SHRINK)
    y = yb + b * (tstar - tb)
    last = max(pts)[1]
    if y < 0: y = 0.0
    return y, b

def regress(rows, upto):
    """per-stat prediction for season `upto` from seasons < upto; None when no usable season"""
    out = {}; n = 0
    for s in CNT + ["FGp", "FTp"]:
        pts = pts_of(rows, s, upto)
        if not pts: continue
        y, b = wls(pts, upto)
        if s in ("FGp", "FTp"): y = min(max(y, .25 if s == "FGp" else .40), .75 if s == "FGp" else .95)
        out[s] = (y, b); n = max(n, len(pts))
    return out, n

# ---------- backtest: 2021-25 -> 2026 (relative RMSE by stat and number of seasons) ----------
def bucket(n): return 1 if n <= 1 else 2 if n == 2 else 3 if n == 3 else 4
bt = {}; naive = {}
for nm, rows in seasons.items():
    a = rows.get(2026)
    if not a or a["G"] < 25: continue
    pr, n = regress(rows, 2026)
    if not pr: continue
    prior = [t for t in rows if t < 2026 and rows[t]["G"] >= MIN_G]
    if not prior: continue
    lastr = rows[max(prior)]
    for s, (y, _) in pr.items():
        act = a["FGM"] / a["FGA"] if s == "FGp" and a["FGA"] else a["FTM"] / a["FTA"] if s == "FTp" and a["FTA"] else a.get(s)
        if act is None or s in ("FGp", "FTp") and (a["FGA" if s == "FGp" else "FTA"] < 1): continue
        lv = max(act, FLOOR[s]) if s not in ("FGp", "FTp") else 1.0
        bt.setdefault((s, bucket(n)), []).append(((y - act) / lv) ** 2)
        ln = lastr["FGM"] / lastr["FGA"] if s == "FGp" and lastr["FGA"] else lastr["FTM"] / lastr["FTA"] if s == "FTp" and lastr["FTA"] else lastr.get(s, 0)
        naive.setdefault(s, []).append(((ln - act) / lv) ** 2)
# pooled relative RMSE per stat, spread over n by the prediction-variance factor (1 + 1/n) (bucket estimates are too noisy)
RREL = {}; NS = {}
for nm, rows in seasons.items():
    a = rows.get(2026)
    if a and a["G"] >= 25:
        k = len([t for t in rows if t < 2026 and rows[t]["G"] >= MIN_G])
        if k: NS[nm] = k
mfac = st.mean(1 + 1 / k for k in NS.values())
POOLED = {s: math.sqrt(st.mean([x for b in (1, 2, 3, 4) for x in bt.get((s, b), [])])) for s in CNT + ["FGp", "FTp"]}
def rrel(s, n): return POOLED[s] * math.sqrt((1 + 1 / max(1, n)) / mfac)
bt_table = {s: {"n1": round(rrel(s, 1), 3), "n3": round(rrel(s, 3), 3), "n6": round(rrel(s, 6), 3),
                "naive": round(math.sqrt(st.mean(naive[s])), 3), "reg": round(POOLED[s], 3),
                "N": sum(len(bt.get((s, b), [])) for b in (1, 2, 3, 4))} for s in CNT + ["FGp", "FTp"]}
# ---------- DD model: P(PTS, REB, AST >= 10) per game ~ normal with sd = a * mean^0.5 + c, two-of-three ----------
PHI = lambda x: .5 * (1 + math.erf(x / math.sqrt(2)))
def ddm(pts, reb, ast, A):
    def p10(m, a): s = a[0] * math.sqrt(max(m, 0)) + a[1]; return 1 - PHI((9.5 - m) / s)
    a, b, c = p10(pts, A[0]), p10(reb, A[1]), p10(ast, A[2])
    return a * b + a * c + b * c - 2 * a * b * c
fit = [(r["PTS"], r["REB"], r["AST"], r["DDg"], r["G"]) for rows in seasons.values() for t, r in rows.items() if t == 2026 and r.get("DDg") is not None and r["G"] >= 20]
best = None
for ap in (.9, 1.1, 1.3, 1.5):
    for ar in (.6, .7, .8, .9, 1.0):
        for aa in (.6, .7, .8, .9, 1.0):
            A = ((ap, 1.0), (ar, .8), (aa, .8)); e = sum(g * (ddm(p, r, a, A) - d) ** 2 for p, r, a, d, g in fit)
            if best is None or e < best[0]: best = (e, A)
DDA = best[1]
dd_rmse = math.sqrt(best[0] / sum(f[4] for f in fit))

# ---------- valuation (same structure as the draft-prep value; pool = ESPN top 150) for the value shift ----------
pool = sorted(P, key=lambda p: -p["value"])[:150]; NEG = {"TO", "PF"}; C = ["FG", "FT", "TPM", "REB", "AST", "STL", "BLK", "TO", "DD", "PTS", "PF"]
fgL = sum(p["FGM"] for p in pool) / sum(p["FGA"] for p in pool); ftL = sum(p["FTM"] for p in pool) / sum(p["FTA"] for p in pool)
raw = lambda p, c: p["FGM"] - p["FGA"] * fgL if c == "FG" else p["FTM"] - p["FTA"] * ftL if c == "FT" else p["DDg"] if c == "DD" else p[c]
mu = {c: st.mean(raw(p, c) for p in pool) for c in C}; sd = {c: st.pstdev(raw(p, c) for p in pool) for c in C}
muT = {c: st.mean(raw(p, c) * p["gp"] for p in pool) for c in C}; sdT = {c: st.pstdev(raw(p, c) * p["gp"] for p in pool) for c in C}
vpg = lambda p: sum((-1 if c in NEG else 1) * (raw(p, c) - mu[c]) / sd[c] for c in C)
vt = lambda p: sum((-1 if c in NEG else 1) * (raw(p, c) * p["gp"] - muT[c]) / sdT[c] for c in C)
scale = st.pstdev([vpg(p) for p in pool]) / st.pstdev([vt(p) for p in pool])
val = lambda p: .5 * vpg(p) + .5 * vt(p) * scale

# ---------- per player ----------
PROJ = {}; cnt = {"reg": 0, "ncaa": 0, "espn": 0}
OUTK = ["PTS", "REB", "AST", "STL", "BLK", "TPM", "TO", "PF", "FGp", "FTp", "DDg"]
for p in P:
    nm = p["name"]; rows = seasons[nm]; e = dict(p)
    espn = {s: p[s] for s in CNT}; espn["FGp"] = p["FGM"] / p["FGA"] if p["FGA"] else 0; espn["FTp"] = p["FTM"] / p["FTA"] if p["FTA"] else 0; espn["DDg"] = p["DDg"]
    pr, n = regress(rows, T_STAR)
    used = sorted(t for t in rows if rows[t]["G"] >= MIN_G)
    info = {"n": n, "yrs": used, "method": "", "wR": {}, "R": {}, "E": {}, "B": {}, "slope": {}}
    if pr:
        last = max(used); gap = 2026 - last
        lastTeam = rows[last].get("team"); moved = bool(lastTeam and p["team"] and lastTeam not in ("2TM", "3TM", "4TM") and lastTeam != p["team"])
        R = {s: pr[s][0] for s in pr}
        for s in CNT + ["FGp", "FTp"]:
            if s not in R: R[s] = espn[s]
        # DD: model on the regressed PTS/REB/AST x the player's own (shrunk) calibration from 2025-26
        r26 = rows.get(2026); cal = 1.0
        if r26 and r26.get("DDg") is not None:
            m26 = ddm(r26["PTS"], r26["REB"], r26["AST"], DDA)
            if m26 > .01: cal = (r26["DDg"] * r26["G"] + 30 * m26) / ((r26["G"] + 30) * m26)
        R["DDg"] = min(.98, ddm(R["PTS"], R["REB"], R["AST"], DDA) * cal)
        B = {}
        for s in CNT + ["FGp", "FTp"]:
            cR = rrel(s, n) ** 2 * (TEAM_VAR if moved else 1) * (1 + GAP_VAR * gap); cE = KAPPA * POOLED[s] ** 2
            w = min(W_MAX, max(W_MIN, cE / (cE + cR))); info["wR"][s] = round(w, 3)
            B[s] = w * R[s] + (1 - w) * espn[s]
        wdd = (info["wR"]["PTS"] + info["wR"]["REB"] + info["wR"]["AST"]) / 3; info["wR"]["DDg"] = round(wdd, 3)
        B["DDg"] = wdd * R["DDg"] + (1 - wdd) * espn["DDg"]
        info["method"] = "회귀+ESPN"; info["moved"] = moved; info["gap"] = gap; info["lastTeam"] = lastTeam; cnt["reg"] += 1
        info["slope"] = {s: round(pr[s][1], 3) for s in ("PTS", "REB", "AST", "TPM", "STL", "BLK") if s in pr}
    elif nm in NC:
        c = NC[nm]; R = {}
        for s in CNT: R[s] = c[s] * NCAA_TR[s]
        R["FGp"] = c["FGM"] / c["FGA"] + NCAA_TR["FGp"] if c["FGA"] else espn["FGp"]; R["FTp"] = c["FTM"] / c["FTA"] if c["FTA"] else espn["FTp"]
        R["DDg"] = ddm(R["PTS"], R["REB"], R["AST"], DDA)
        B = {s: W_NCAA * R[s] + (1 - W_NCAA) * espn[s] for s in R}; info["wR"] = {s: W_NCAA for s in R}
        info["method"] = "NCAA+ESPN"; info["ncaa"] = {"school": c.get("school"), "G": c.get("G")}; cnt["ncaa"] += 1
    else:
        R = None; B = dict(espn); info["method"] = "ESPN"; info["wR"] = {s: 0 for s in OUTK}; cnt["espn"] += 1
    # write back (makes from attempts x percentage)
    for s in CNT: p[s] = round(B[s], 3)
    p["FGM"] = round(B["FGA"] * B["FGp"], 3); p["FTM"] = round(B["FTA"] * B["FTp"], 3); p["DDg"] = round(B["DDg"], 3)
    p["vpg"] = round(p["vpg"] + vpg(p) - vpg(e), 3); p["value"] = round(p["value"] + val(p) - val(e), 3)
    rd = lambda d: {s: round(d[s], 3) for s in OUTK if s in d} if d else None
    info["E"] = rd(espn); info["R"] = rd(R); info["B"] = rd(B); info["dv"] = round(p["value"] - e["value"], 2)
    PROJ[nm] = info

ref["players"] = [[p[f] for f in F] for p in P]
ref["proj"] = PROJ
ref["projMeta"] = {"asOf": "2026-10-23", "tStar": T_STAR, "delta": DELTA, "kShrink": K_SHRINK, "kappa": KAPPA, "teamVar": TEAM_VAR, "gapVar": GAP_VAR,
                   "wMin": W_MIN, "wMax": W_MAX, "wNcaa": W_NCAA, "minG": MIN_G, "counts": cnt, "backtest": bt_table, "ddFit": {"A": DDA, "rmse": round(dd_rmse, 3), "N": len(fit)},
                   "seasons": "BR 2020-21..2024-25 per-game (득점 상위 ~250명/시즌) + 2025-26 전 선수(BR=ESPN 실적 일치 검증)",
                   "inSeason": [[1, 3, .1], [4, 6, .3], [7, 9, .5], [10, 12, .7], [13, 17, .9]]}
s = json.dumps(ref, ensure_ascii=False, separators=(",", ":")); assert "</script" not in s.lower()
open(os.environ.get("OUT", "ref27_base.json"), "w").write(s)
print("counts", cnt, "DD fit", DDA, round(dd_rmse, 3))
print("backtest rel RMSE (reg vs naive last season):")
for k, v in bt_table.items(): print(f"  {k:4s} n1 {v['n1']:.3f} n3 {v['n3']:.3f} n6 {v['n6']:.3f} | reg {v['reg']:.3f} naive {v['naive']:.3f} N {v['N']}")
