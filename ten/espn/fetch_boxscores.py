#!/usr/bin/env python3
"""NBA box scores for the last N days (ESPN public site API, no cookies) -> ten/data/gamelogs.csv

One row per player per game: date, game id, team, opponent, win, starter, dnp (+ reason), minutes and counting stats.
Used to project each player's CURRENT role (minutes, starter vs bench) given who is healthy on his team now.
Env: DAYS (default 15). Stdlib only.
"""
import csv, json, os, sys, time, urllib.request
from datetime import datetime, timedelta, timezone

OUT = os.environ.get("ESPN_OUT", os.path.join(os.path.dirname(__file__), "..", "data"))
DAYS = int(os.environ.get("DAYS", "15"))
SITE = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba"
FIX = {"GS": "GSW", "NY": "NYK", "SA": "SAS", "NO": "NOP", "UTAH": "UTA", "WSH": "WAS"}


def get(url):
    last = None
    for k in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (hoops-board ten boxscores)", "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:
            last = e; time.sleep(2 * (k + 1))
    raise RuntimeError(f"{url}: {last}")


def num(x):
    try: return float(x)
    except (TypeError, ValueError): return 0.0


def split(x):
    a, _, b = (x or "0-0").partition("-")
    return num(a), num(b)


def main():
    et = datetime.now(timezone.utc) - timedelta(hours=5)
    rows, games = [], 0
    for k in range(DAYS, 0, -1):
        day = (et - timedelta(days=k)).strftime("%Y%m%d")
        sb = get(f"{SITE}/scoreboard?dates={day}")
        for ev in sb.get("events") or []:
            st = ((ev.get("status") or {}).get("type") or {})
            if not st.get("completed"):
                continue
            comp = (ev.get("competitions") or [{}])[0]
            sides = {c["team"]["id"]: c for c in comp.get("competitors", [])}
            box = get(f"{SITE}/summary?event={ev['id']}").get("boxscore") or {}
            games += 1
            for tb in box.get("players") or []:
                tid = (tb.get("team") or {}).get("id"); ab = (tb.get("team") or {}).get("abbreviation", "")
                me = sides.get(tid) or {}; opp = next((c for i, c in sides.items() if i != tid), {})
                for sblk in tb.get("statistics") or []:
                    keys = [s.upper() for s in (sblk.get("keys") or sblk.get("labels") or [])]
                    for a in sblk.get("athletes") or []:
                        ath = a.get("athlete") or {}
                        stats = a.get("stats") or []
                        d = dict(zip(keys, stats))
                        g = lambda *names: next((d[n] for n in names if n in d), None)
                        fgm, fga = split(g("FIELDGOALSMADE-FIELDGOALSATTEMPTED", "FG"))
                        tpm, tpa = split(g("THREEPOINTFIELDGOALSMADE-THREEPOINTFIELDGOALSATTEMPTED", "3PT"))
                        ftm, fta = split(g("FREETHROWSMADE-FREETHROWSATTEMPTED", "FT"))
                        rows.append({"date": f"{day[:4]}-{day[4:6]}-{day[6:]}", "game": ev["id"], "team": FIX.get(ab, ab),
                                     "opp": FIX.get((opp.get("team") or {}).get("abbreviation", ""), (opp.get("team") or {}).get("abbreviation", "")),
                                     "win": 1 if me.get("winner") else 0, "player": ath.get("displayName"), "espnId": ath.get("id"),
                                     "starter": 1 if a.get("starter") else 0, "dnp": 1 if (a.get("didNotPlay") or not stats) else 0, "reason": a.get("reason") or "",
                                     "MIN": num(g("MINUTES", "MIN")), "FGM": fgm, "FGA": fga, "3PM": tpm, "FTM": ftm, "FTA": fta,
                                     "REB": num(g("REBOUNDS", "REB")), "AST": num(g("ASSISTS", "AST")), "STL": num(g("STEALS", "STL")),
                                     "BLK": num(g("BLOCKS", "BLK")), "TO": num(g("TURNOVERS", "TO")), "PTS": num(g("POINTS", "PTS"))})
    cols = ["date", "game", "team", "opp", "win", "player", "espnId", "starter", "dnp", "reason", "MIN", "FGM", "FGA", "3PM", "FTM", "FTA", "REB", "AST", "STL", "BLK", "TO", "PTS"]
    with open(os.path.join(OUT, "gamelogs.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols); w.writeheader(); w.writerows(rows)
    print(f"boxscores: {games} games, {len(rows)} player rows, last {DAYS} days")


if __name__ == "__main__":
    main()
