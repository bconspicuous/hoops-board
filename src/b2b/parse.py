import json, re, datetime as dt
from collections import defaultdict
FULL = {"Atlanta Hawks":"ATL","Boston Celtics":"BOS","Brooklyn Nets":"BKN","Charlotte Hornets":"CHA","Chicago Bulls":"CHI","Cleveland Cavaliers":"CLE","Dallas Mavericks":"DAL","Denver Nuggets":"DEN","Detroit Pistons":"DET","Golden State Warriors":"GSW","Houston Rockets":"HOU","Indiana Pacers":"IND","Los Angeles Clippers":"LAC","Los Angeles Lakers":"LAL","Memphis Grizzlies":"MEM","Miami Heat":"MIA","Milwaukee Bucks":"MIL","Minnesota Timberwolves":"MIN","New Orleans Pelicans":"NOP","New York Knicks":"NYK","Oklahoma City Thunder":"OKC","Orlando Magic":"ORL","Philadelphia 76ers":"PHI","Phoenix Suns":"PHX","Portland Trail Blazers":"POR","Sacramento Kings":"SAC","San Antonio Spurs":"SAS","Toronto Raptors":"TOR","Utah Jazz":"UTA","Washington Wizards":"WAS"}
TO_REF = {"NOP":"NOR","PHX":"PHO"}
games = []
for line in open("sched_raw_oct.txt"):
    d, m = line.strip().split(" | "); a, h = m.split(" @ "); games.append((d, FULL[a], FULL[h]))
for line in open("sched_raw_rest.txt"):
    s = line.strip()
    if not s: continue
    md_, m = s.split(" "); a, h = m.split("@"); mo, da = map(int, md_.split("-")); y = 2026 if mo >= 10 else 2027
    games.append((f"{y}-{mo:02d}-{da:02d}", a, h))
ref = json.load(open("/home/claude/nba/dash/ref.json"))
cols = ref["cols"]; ok = set(FULL.values())
bad = [g for g in games if g[1] not in ok or g[2] not in ok]; print("bad codes", bad)
dup = defaultdict(int)
for d, a, h in games: dup[(d, a)] += 1; dup[(d, h)] += 1
print("team twice same day:", [k for k, v in dup.items() if v > 1])
# per-week counts vs grid
def wk(d):
    for i, (s, e) in enumerate(zip(ref["starts"], ref["ends"])):
        if s <= d <= e: return i
cnt = defaultdict(int)
for d, a, h in games:
    w = wk(d)
    for t in (a, h): cnt[(w, TO_REF.get(t, t))] += 1
mism = []
for w in range(14):
    for i, c in enumerate(cols):
        if cnt[(w, c)] != ref["grid"][w][i]: mism.append((w + 1, c, cnt[(w, c)], ref["grid"][w][i]))
print("total games", len(games), "| mismatches (week, team, parsed, grid):", len(mism)); print(mism)
json.dump(games, open("games.json", "w"))
