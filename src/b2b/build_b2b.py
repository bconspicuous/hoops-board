"""Build v2.2 reference data: real daily schedule for all 14 weeks, back-to-back flags, and per-player B2B parameters.
Player B2B model (hierarchical, documented in the dashboard):
  r  = P(sits the 2nd night of a team back-to-back | otherwise available)   -> rest propensity tiers
  k  = intensity of the 2nd-night production drop (minutes load x age)       -> multiplies league-level effects
Sources: Basketball-Reference 2025-26 / 2024-25 per-game (age, G, MP); NBA Player Participation Policy (35+ / load-managed);
league-level 2nd-night effects from RotoWire (2014-15 top-40: PTS -5%, AST -5%, REB -2%) and Frontiers 2021 (2016-17 team-level)."""
import json, datetime as dt
from collections import defaultdict
ref = json.load(open("/home/claude/nba/dash/ref.json"))
F = ref["fields"]; P = [dict(zip(F, a)) for a in ref["players"]]
TO_REF = {"NOP": "NOR", "PHX": "PHO"}
games = json.load(open("games.json"))
days = defaultdict(set)
for d, a, h in games:
    for t in (a, h): days[TO_REF.get(t, t)].add(d)
for t in list(days):            # week 8: two NBA Cup knockout/replacement games per team listed as TBD on 12-08 and 12-11
    days[t] |= {"2026-12-08", "2026-12-11"}
prev = lambda d: (dt.date.fromisoformat(d) - dt.timedelta(days=1)).isoformat()
sched, b2bd = [], []
for s, e in zip(ref["starts"], ref["ends"]):
    W, B = [], []
    d = dt.date.fromisoformat(s)
    while d.isoformat() <= e:
        ds = d.isoformat(); on = sorted(t for t in ref["cols"] if ds in days[t]); W.append(on); B.append([t for t in on if prev(ds) in days[t]]); d += dt.timedelta(days=1)
    sched.append(W); b2bd.append(B)
# sanity: weekly counts == grid
for w in range(14):
    for i, c in enumerate(ref["cols"]):
        assert sum(c in day for day in sched[w]) == ref["grid"][w][i], (w, c)
share = {t: round(sum(len([1 for day in B if t in day]) for B in b2bd) / sum(sum(t in day for day in W) for W in sched), 4) for t in ref["cols"]}
# ---- player inputs
br26 = {l.split("|")[0]: l.strip().split("|") for l in open("raw_br.txt") if l.strip()}
br25 = {l.split("|")[0]: l.strip().split("|") for l in open("raw_br25.txt") if l.strip()}
# ages (2026-27 opening night, from birth dates) for veterans missing from the truncated BR table
AGE_KNOWN = {"Al Horford": 40, "Brook Lopez": 38, "Draymond Green": 36, "Damian Lillard": 36, "Bogdan Bogdanovic": 34, "Kyrie Irving": 34,
             "Kyle Anderson": 33, "Kentavious Caldwell-Pope": 33, "Bradley Beal": 33, "Andre Drummond": 33, "Buddy Hield": 33, "G. Niang": 33,
             "Gary Payton II": 33, "Larry Nance Jr.": 33, "Clint Capela": 32, "Marcus Smart": 32, "Kris Dunn": 32, "Alex Caruso": 32,
             "Caris LeVert": 32, "Fred VanVleet": 32, "Luke Kornet": 31, "Terance Mann": 30, "Luke Kennard": 30, "Simone Fontecchio": 30,
             "Trey Lyles": 30, "T. Lyles": 30, "Tyrese Haliburton": 26, "Robert Williams III": 29}
# season-long absence in 2025-26 (Achilles/ACL), returning in 2026-27
RETURNERS = {"Tyrese Haliburton", "Damian Lillard", "Fred VanVleet", "Kyrie Irving"}
OVERRIDE = {"Joel Embiid": (0.80, "본인 언급: 백투백 출전 지양"), "Kawhi Leonard": (0.45, "부하 관리 이력")}
rank = {p["name"]: i for i, p in enumerate(sorted(P, key=lambda p: -p["value"]))}
out = {}
for p in P:
    n = p["name"]; b = br26.get(n); b5 = br25.get(n)
    age = int(b[1]) + 1 if b else AGE_KNOWN.get(n)            # BR age is as of Feb 1 of the season -> +1 for 2026-27
    g26 = int(b[2]) if b else None; mp26 = float(b[4]) if b else None
    g25 = int(b5[1]) if b5 else None; mp25 = float(b5[2]) if b5 else None
    mp = mp26 or mp25 or (32 if rank[n] < 60 else 27 if rank[n] < 150 else 22)
    k = min(1.2, max(0.2, (mp - 18) / 16)) * (1.15 if age and age >= 33 else 1.0)
    r, why = 0.02, []
    if age and age >= 35: r += 0.25; why.append(f"35세 이상({age}) 휴식 규정 예외")
    elif age and age >= 34: r += 0.10; why.append(f"고령({age})")
    if n in RETURNERS: r += 0.25; why.append("장기 부상 복귀 시즌")
    elif g26 is not None and g26 <= 20 and mp >= 24: r += 0.20; why.append(f"전년 {g26}경기 출전(장기 결장)")
    elif g26 is not None and g26 <= 45 and mp >= 28 and (g25 is None or g25 <= 60): r += 0.10; why.append(f"2시즌 결장 누적({g25 if g25 is not None else '—'}·{g26}경기)")
    if n in OVERRIDE: r, w = OVERRIDE[n]; why.insert(0, w)
    r = min(r, 0.85)
    out[n] = [round(r, 3), round(k, 3), age, g26, mp26, g25, " · ".join(why) or "일반"]
ref["sched"] = sched; ref["b2bd"] = b2bd; ref["b2bShare"] = share; ref["b2bp"] = out
ref["b2bFx"] = {"PTS": -0.05, "AST": -0.05, "REB": -0.02, "STL": -0.04, "BLK": -0.05, "TPM": -0.04, "TO": -0.03, "PF": 0.03, "FGA": -0.03, "FTA": -0.03, "DDg": -0.08, "FGp": -0.010, "FTp": -0.005, "sd": 0.05}
json.dump(ref, open("/home/claude/nba/dash/ref22.json", "w"), ensure_ascii=False, separators=(",", ":"))
tiers = defaultdict(int)
for n, v in out.items(): tiers[round(v[0], 2)] += 1
print("r distribution:", sorted(tiers.items()))
print("B2B share by team:", sorted(share.items(), key=lambda x: -x[1])[:5], "...")
for n in ["Joel Embiid", "Kawhi Leonard", "LeBron James", "Stephen Curry", "Kevin Durant", "James Harden", "Tyrese Haliburton", "Anthony Davis", "Giannis Antetokounmpo", "Coby White", "Shai Gilgeous-Alexander", "Al Horford", "Jayson Tatum"]:
    print(n, out[n])
