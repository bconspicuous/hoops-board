"""Neutral projection: regress every player's ESPN projection toward his recent record by ONE rule for the whole pool
   (all 8 rosters and free agents), so no team keeps a projection-optimism edge.
   in : ref22_espn.json (ESPN projections, untouched), data/hist.json (2025-26 per-game + GP, 2024-25 GP)
   out: ref22.json  — gp and per-game stats adjusted, value/vpg shifted by the same valuation, ESPN GP kept as gpE
   rule: GP     = (1-W_GP)*ESPN + W_GP*recent GP   (recent = 2025-26 if >=10 games, else 2024-25 if >=10, else ESPN only)
         per-game = (1-W_PG)*ESPN + W_PG*2025-26 actual   (only with >=20 games in 2025-26; rookies/no record keep ESPN)
   usage: python3 neutral.py [W_GP] [W_PG]     (defaults 1/3, 0.2)"""
import json, sys, statistics as st
W_GP = float(sys.argv[1]) if len(sys.argv) > 1 else 1 / 3
W_PG = float(sys.argv[2]) if len(sys.argv) > 2 else 0.2
import os
KEEP = set(x for x in os.environ.get("KEEP_GP", "").split("|") if x)        # players whose GP stays at the ESPN projection
KEEP_LT = float(os.environ.get("KEEP_GP_LT", "0"))                           # ...or every player whose recent GP is below this
OUT = os.environ.get("OUT", "ref22.json")
ref = json.load(open("ref22_espn.json")); F = ref["fields"]; H = json.load(open("data/hist.json"))["players"]
K = ["FGM", "FGA", "FTM", "FTA", "TPM", "REB", "AST", "STL", "BLK", "TO", "PTS", "PF", "DDg"]
P = [dict(zip(F, r)) for r in ref["players"]]
# valuation used for the shift (same structure as the draft-prep value: 50% per-game z + 50% season-total z, pool = top 150)
pool = sorted(P, key=lambda p: -p["value"])[:150]; NEG = {"TO", "PF"}; C = ["FG", "FT", "TPM", "REB", "AST", "STL", "BLK", "TO", "DD", "PTS", "PF"]
fgL = sum(p["FGM"] for p in pool) / sum(p["FGA"] for p in pool); ftL = sum(p["FTM"] for p in pool) / sum(p["FTA"] for p in pool)
raw = lambda p, c: p["FGM"] - p["FGA"] * fgL if c == "FG" else p["FTM"] - p["FTA"] * ftL if c == "FT" else p["DDg"] if c == "DD" else p[c]
mu = {c: st.mean(raw(p, c) for p in pool) for c in C}; sd = {c: st.pstdev(raw(p, c) for p in pool) for c in C}
muT = {c: st.mean(raw(p, c) * p["gp"] for p in pool) for c in C}; sdT = {c: st.pstdev(raw(p, c) * p["gp"] for p in pool) for c in C}
vpg = lambda p: sum((-1 if c in NEG else 1) * (raw(p, c) - mu[c]) / sd[c] for c in C)
vt = lambda p: sum((-1 if c in NEG else 1) * (raw(p, c) * p["gp"] - muT[c]) / sdT[c] for c in C)
scale = st.pstdev([vpg(p) for p in pool]) / st.pstdev([vt(p) for p in pool])
val = lambda p: .5 * vpg(p) + .5 * vt(p) * scale
nG = nP = 0
for p in P:
    h = H.get(p["name"], {}); e = dict(p); p["gpE"] = p["gp"]
    rec = h.get("gp26") if (h.get("gp26") or 0) >= 10 else h.get("gp25") if (h.get("gp25") or 0) >= 10 else None
    p["gpR"] = rec
    if rec is not None and p["gp"] and p["name"] not in KEEP and not (rec < KEEP_LT): p["gp"] = round((1 - W_GP) * p["gp"] + W_GP * rec, 1); nG += 1
    if h.get("pg26") and (h.get("gpPG") or 0) >= 20:
        for k in K: p[k] = round((1 - W_PG) * p[k] + W_PG * h["pg26"][k], 3)
        nP += 1
    k = dict(p); k["gp"] = p["gpE"]                                   # same player with the ESPN games kept (dashboard GP-assumption switch)
    p["vKeep"] = round(p["value"] + val(k) - val(e), 3)
    f = dict(p); f["gp"] = 82.0                                       # every game played (dashboard "full availability" mode)
    p["vFull"] = round(p["value"] + val(f) - val(e), 3) if p["gpE"] else p["value"]
    p["vpg"] = round(p["vpg"] + vpg(p) - vpg(e), 3); p["value"] = round(p["value"] + val(p) - val(e), 3)
F2 = F + ["gpE", "gpR", "vKeep", "vFull"]
ref["fields"] = F2; ref["players"] = [[p[f] for f in F2] for p in P]
ref["neutral"] = {"wGP": round(W_GP, 3), "wPG": W_PG, "gpAdjusted": nG, "pgAdjusted": nP, "source": "2025-26 실제(ESPN) · 2024-25 출전(BR)", "keepGP": sorted(KEEP), "keepGpBelow": KEEP_LT}
s = json.dumps(ref, ensure_ascii=False, separators=(",", ":")); assert "</script" not in s.lower()
open(OUT, "w").write(s)
print(f"neutral: GP weight {W_GP:.2f} on recent record ({nG} players), per-game weight {W_PG:.2f} on 2025-26 ({nP} players)")
