"""2026-27 actual per-game stats -> league/actuals doc (data/actuals.json).
   in : BR box scores (pipe files TEAM|Player|MP|FG|FGA|3P|FT|FTA|TRB|AST|STL|BLK|TOV|PF|PTS or TEAM|Player|DNP) in BR_DIR/box/
        optional BR season per-game rows (2027.txt) for teams whose box scores are missing
   out: data/actuals.json {asOf, through, source, players: {name: {g, min, fgm, fga, ftm, fta, tpm, reb, ast, stl, blk, to, pf, pts, dd}}}
        per-game values except dd (= total double-doubles), only projection-pool players.
   usage: python3 proj/actuals27.py <through YYYY-MM-DD> [complete_teams_only=1]"""
import json, os, sys, glob
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from brload import BR, TEAMMAP, norm, pool_map, ALIAS

through = sys.argv[1]; only_complete = len(sys.argv) > 2 and sys.argv[2] == "1"
ref = json.load(open("ref22_espn.json")); names = [p[0] for p in ref["players"]]; pm = pool_map(names)
tot = {}; teams_box = set(); games = 0
for f in sorted(glob.glob(os.path.join(BR, "box", "g*.txt"))):
    games += 1
    for line in open(f, encoding="utf-8"):
        x = line.strip().split("|")
        if len(x) < 3: continue
        team = TEAMMAP.get(x[0], x[0]); teams_box.add(team)
        if x[2].startswith("DNP") or len(x) < 15: continue
        k = ALIAS.get(norm(x[1]), norm(x[1]))
        if k not in pm: continue
        mm, ss = (x[2].split(":") + ["0"])[:2]; v = [float(y) for y in x[3:15]]
        FG, FGA, P3, FT, FTA, TRB, AST, STL, BLK, TOV, PF, PTS = v
        t = tot.setdefault(pm[k], {"g": 0, "min": 0, "fgm": 0, "fga": 0, "ftm": 0, "fta": 0, "tpm": 0, "reb": 0, "ast": 0, "stl": 0, "blk": 0, "to": 0, "pf": 0, "pts": 0, "dd": 0, "team": team})
        t["g"] += 1; t["min"] += int(mm) + int(ss) / 60
        for key, val in zip(["fgm", "fga", "tpm", "ftm", "fta", "reb", "ast", "stl", "blk", "to", "pf", "pts"], [FG, FGA, P3, FT, FTA, TRB, AST, STL, BLK, TOV, PF, PTS]): t[key] += val
        t["dd"] += 1 if sum(1 for s in (PTS, TRB, AST, STL, BLK) if s >= 10) >= 2 else 0
extra = 0; pg_path = os.path.join(BR, "2027.txt")
if not only_complete and os.path.exists(pg_path):          # season per-game rows (games >= 1) for teams without a box score file
    for line in open(pg_path, encoding="utf-8"):
        x = line.strip().split("|")
        if len(x) != 17 or x[0] == "Player": continue
        team = TEAMMAP.get(x[2], x[2])
        if team in teams_box: continue
        k = ALIAS.get(norm(x[0]), norm(x[0]))
        if k not in pm or pm[k] in tot: continue
        G, MP, FG, FGA, P3, FT, FTA, TRB, AST, STL, BLK, TOV, PF, PTS = [float(y) for y in x[3:]]
        tot[pm[k]] = {"g": G, "min": MP * G, "fgm": FG * G, "fga": FGA * G, "ftm": FT * G, "fta": FTA * G, "tpm": P3 * G, "reb": TRB * G, "ast": AST * G, "stl": STL * G, "blk": BLK * G, "to": TOV * G, "pf": PF * G, "pts": PTS * G,
                      "dd": (1 if sum(1 for s in (PTS, TRB, AST, STL, BLK) if s >= 10) >= 2 else 0) if G == 1 else None, "team": team}; extra += 1
tp = 0                                                       # BR team pages (season per-game, all games to date): used when they cover more games
for f in sorted(glob.glob(os.path.join(BR, "team27", "*.txt"))):
    team = TEAMMAP.get(os.path.basename(f)[:3], os.path.basename(f)[:3])
    for line in open(f, encoding="utf-8"):
        x = line.strip().split("|")
        if len(x) != 15 or x[0] == "Player": continue
        k = ALIAS.get(norm(x[0]), norm(x[0]))
        if k not in pm: continue
        G, MP, FG, FGA, P3, FT, FTA, TRB, AST, STL, BLK, TOV, PF, PTS = [float(y) for y in x[1:]]
        if G <= 0 or (pm[k] in tot and tot[pm[k]]["g"] >= G): continue
        tot[pm[k]] = {"g": G, "min": MP * G, "fgm": FG * G, "fga": FGA * G, "ftm": FT * G, "fta": FTA * G, "tpm": P3 * G, "reb": TRB * G, "ast": AST * G, "stl": STL * G, "blk": BLK * G, "to": TOV * G, "pf": PF * G, "pts": PTS * G, "dd": None, "team": team}; tp += 1
players = {}
for n, t in tot.items():
    g = t["g"]; players[n] = {"g": int(g), "min": round(t["min"] / g, 1), **{k: round(t[k] / g, 3) for k in ["fgm", "fga", "ftm", "fta", "tpm", "reb", "ast", "stl", "blk", "to", "pf", "pts"]}, "dd": t["dd"]}
doc = {"asOf": f"{through} (BR)", "through": through, "source": f"Basketball-Reference box scores ({games} games) + team pages ({tp} players with more games; DD n/a)",
       "teamsComplete": sorted(teams_box), "players": players}
json.dump(doc, open("data/actuals.json", "w"), ensure_ascii=False, indent=0)
print(f"actuals: {len(players)} pool players ({games} box scores, {tp} from team pages)")
