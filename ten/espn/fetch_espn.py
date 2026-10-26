#!/usr/bin/env python3
"""ESPN Fantasy Basketball (v3) fetcher for the 10-team league "26-27 fantasy".

Pulls teams, rosters (with injury status and 2027 season averages), the current
matchup scoreboard (category totals) and the top free agents, then writes:
  ten/data/espn_raw_league.json   trimmed raw response (for debugging / new fields)
  ten/data/rosters.json           rosters in the dashboard's format (players, ir, status)
  ten/data/scoreboard.json        current + past matchups with category totals and W-L-T
  ten/data/players_2027.csv       season averages for rostered players and top free agents
  ten/data/meta.json              fetch time, scoring period, matchup period

Private leagues need the espn_s2 and SWID cookies (env ESPN_S2, ESPN_SWID).
Stdlib only, so it runs on a bare GitHub Actions runner.
"""
import csv, json, os, sys, time, urllib.request, urllib.error
from datetime import datetime, timezone, timedelta

LEAGUE_ID = os.environ.get("ESPN_LEAGUE_ID", "504060248")
SEASON = int(os.environ.get("ESPN_SEASON", "2027"))      # ESPN labels 2026-27 as 2027
OUT = os.environ.get("ESPN_OUT", os.path.join(os.path.dirname(__file__), "..", "data"))
HOSTS = ["https://lm-api-reads.fantasy.espn.com", "https://fantasy.espn.com"]
PATH = f"/apis/v3/games/fba/seasons/{SEASON}/segments/0/leagues/{LEAGUE_ID}"

# ESPN basketball stat ids (community-documented; unknown ids are kept as "s<id>")
STAT = {0: "PTS", 1: "BLK", 2: "STL", 3: "AST", 4: "OREB", 5: "DREB", 6: "REB", 11: "TO", 13: "FGM", 14: "FGA",
        15: "FTM", 16: "FTA", 17: "3PM", 18: "3PA", 19: "FG%", 20: "FT%", 21: "3P%", 37: "DD", 38: "TD", 40: "MIN", 41: "GS", 42: "GP"}
SLOT = {0: "PG", 1: "SG", 2: "SF", 3: "PF", 4: "C", 5: "G", 6: "F", 7: "SG/SF", 8: "G/F", 9: "PF/C", 10: "F/C", 11: "UTIL", 12: "BE", 13: "IR"}
PRO = {1: "ATL", 2: "BOS", 3: "NOP", 4: "CHI", 5: "CLE", 6: "DAL", 7: "DEN", 8: "DET", 9: "GSW", 10: "HOU", 11: "IND", 12: "LAC", 13: "LAL", 14: "MIA",
       15: "MIL", 16: "MIN", 17: "BKN", 18: "NYK", 19: "ORL", 20: "PHI", 21: "PHX", 22: "POR", 23: "SAC", 24: "SAS", 25: "OKC", 26: "UTA", 27: "WAS",
       28: "TOR", 29: "MEM", 30: "CHA", 0: "FA"}
INJ = {"OUT": "O", "DAY_TO_DAY": "DTD", "INJURY_RESERVE": "O", "SUSPENSION": "O", "QUESTIONABLE": "DTD", "DOUBTFUL": "DTD"}
# dashboard team codes by ESPN team name (fallback: ESPN abbrev)
CODE = {"Garak Twindragons": "GTD", "PaloAlto Wenoja": "JYP", "Samseong Homeless": "SMS", "Helio honeymoons": "Doo", "Jongno Karina": "IYH",
        "Team Bbang Guns": "TBG", "Seoul Dreamers": "KOO", "Garibong CHaRdaddy": "GGAM", "Kfinco_ThePianist": "SONG", "Saving PakPaks": "KWNG"}
MY_TEAM = os.environ.get("ESPN_MY_TEAM", "Garak Twindragons")


def get(views, extra_headers=None):
    q = "&".join("view=" + v for v in views)
    hdr = {"User-Agent": "Mozilla/5.0 (hoops-board ten fetcher)", "Accept": "application/json"}
    s2, swid = os.environ.get("ESPN_S2"), os.environ.get("ESPN_SWID")
    if s2 and swid:
        hdr["Cookie"] = f"espn_s2={s2}; SWID={swid}"
    hdr.update(extra_headers or {})
    last = None
    for host in HOSTS:
        for attempt in range(3):
            try:
                req = urllib.request.Request(f"{host}{PATH}?{q}", headers=hdr)
                with urllib.request.urlopen(req, timeout=30) as r:
                    body = r.read().decode("utf-8")
                data = json.loads(body)
                if isinstance(data, dict) and data.get("messages") and not data.get("teams") and not data.get("players"):
                    raise RuntimeError("ESPN error: " + json.dumps(data["messages"])[:300])
                return data
            except urllib.error.HTTPError as e:
                last = f"{host} HTTP {e.code}: {e.read()[:300]!r}"
                if e.code in (401, 403):
                    sys.exit(f"ESPN denied access ({e.code}). Private league: set ESPN_S2 and ESPN_SWID secrets. {last}")
            except Exception as e:  # network / JSON
                last = f"{host}: {e}"
            time.sleep(2 * (attempt + 1))
    sys.exit("ESPN fetch failed: " + str(last))


def team_name(t):
    if t.get("name"):
        return t["name"].strip()
    return f"{t.get('location', '')} {t.get('nickname', '')}".strip()


def season_avg(player):
    """2027 actual season averages (statSourceId 0, statSplitTypeId 0)."""
    for s in player.get("stats") or []:
        if s.get("seasonId") == SEASON and s.get("statSourceId") == 0 and s.get("statSplitTypeId") == 0:
            avg = s.get("averageStats") or {}
            return {STAT.get(int(k), f"s{k}"): round(v, 3) for k, v in avg.items() if v is not None}
    return {}


def player_row(p, owner, slot=None, status=None):
    a = season_avg(p)
    return {"Player": p.get("fullName"), "Team": PRO.get(p.get("proTeamId"), str(p.get("proTeamId"))), "Owner": owner, "Slot": slot or "",
            "Status": status or INJ.get(p.get("injuryStatus") or "", ""), "G": a.get("GP", ""), "MP": a.get("MIN", ""),
            "FG": a.get("FGM", ""), "FGA": a.get("FGA", ""), "3P": a.get("3PM", ""), "FT": a.get("FTM", ""), "FTA": a.get("FTA", ""),
            "TRB": a.get("REB", ""), "AST": a.get("AST", ""), "STL": a.get("STL", ""), "BLK": a.get("BLK", ""), "TOV": a.get("TO", ""),
            "PTS": a.get("PTS", ""), "DD": a.get("DD", "")}


def main():
    os.makedirs(OUT, exist_ok=True)
    lg = get(["mSettings", "mTeam", "mRoster", "mMatchupScore", "mStatus"])
    teams = lg.get("teams") or []
    if not teams:
        sys.exit("No teams in response - check league id / season / cookies")
    tname = {t["id"]: team_name(t) for t in teams}
    tcode = {t["id"]: CODE.get(team_name(t), t.get("abbrev") or str(t["id"])) for t in teams}

    rosters, status, rows = [], {"O": [], "DTD": []}, []
    for t in teams:
        players, ir = [], []
        for e in (t.get("roster") or {}).get("entries", []):
            p = (e.get("playerPoolEntry") or {}).get("player") or {}
            nm, slot = p.get("fullName"), SLOT.get(e.get("lineupSlotId"), str(e.get("lineupSlotId")))
            st = INJ.get(p.get("injuryStatus") or "", "")
            (ir if slot == "IR" else players).append(nm)
            if st in status:
                status[st].append(nm)
            rows.append(player_row(p, tcode[t["id"]], slot, st))
        rec = ((t.get("record") or {}).get("overall") or {})
        rosters.append({"name": tname[t["id"]], "abbr": tcode[t["id"]], "espnId": t["id"], "me": tname[t["id"]] == MY_TEAM,
                        "players": players, "ir": ir, "record": {k: rec.get(k) for k in ("wins", "losses", "ties", "percentage")}})

    sp = (lg.get("status") or {}).get("currentMatchupPeriod") or lg.get("scoringPeriodId")
    games = []
    for m in lg.get("schedule") or []:
        side = lambda s: {"team": tcode.get((s or {}).get("teamId")), "wins": ((s or {}).get("cumulativeScore") or {}).get("wins"),
                          "losses": ((s or {}).get("cumulativeScore") or {}).get("losses"), "ties": ((s or {}).get("cumulativeScore") or {}).get("ties"),
                          "cats": {STAT.get(int(k), f"s{k}"): (v or {}).get("score") for k, v in (((s or {}).get("cumulativeScore") or {}).get("scoreByStat") or {}).items()}}
        games.append({"period": m.get("matchupPeriodId"), "winner": m.get("winner"), "home": side(m.get("home")), "away": side(m.get("away"))})

    # top free agents / waivers by % rostered
    flt = {"players": {"filterStatus": {"value": ["FREEAGENT", "WAIVERS"]}, "limit": 200, "sortPercOwned": {"sortPriority": 1, "sortAsc": False},
                       "filterStatsForTopScoringPeriodIds": {"value": 2, "additionalValue": [f"00{SEASON}", f"10{SEASON}"]}}}
    fa = get(["kona_player_info"], {"X-Fantasy-Filter": json.dumps(flt)})
    for pe in fa.get("players") or []:
        p = pe.get("player") or {}
        st = INJ.get(p.get("injuryStatus") or "", "")
        if st in status:
            status[st].append(p.get("fullName"))
        rows.append(player_row(p, "FA", "", st))

    now = datetime.now(timezone(timedelta(hours=9))).isoformat(timespec="minutes")
    json.dump({"asOf": now, "leagueId": LEAGUE_ID, "season": SEASON, "teams": rosters, "status": status},
              open(os.path.join(OUT, "rosters.json"), "w"), ensure_ascii=False, indent=1)
    json.dump({"asOf": now, "currentMatchupPeriod": sp, "matchups": games}, open(os.path.join(OUT, "scoreboard.json"), "w"), ensure_ascii=False, indent=1)
    with open(os.path.join(OUT, "players_2027.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    trim = {k: lg.get(k) for k in ("id", "seasonId", "scoringPeriodId", "status")}
    trim["settings"] = {k: (lg.get("settings") or {}).get(k) for k in ("name", "scoringSettings", "rosterSettings", "scheduleSettings", "tradeSettings", "acquisitionSettings")}
    json.dump(trim, open(os.path.join(OUT, "espn_raw_league.json"), "w"), ensure_ascii=False, indent=1)
    json.dump({"asOf": now, "scoringPeriodId": lg.get("scoringPeriodId"), "currentMatchupPeriod": sp, "teams": len(teams), "players": len(rows),
               "auth": bool(os.environ.get("ESPN_S2"))}, open(os.path.join(OUT, "meta.json"), "w"), indent=1)
    print(f"ok: {len(teams)} teams, {len(rows)} players, matchup period {sp}, asOf {now}")


if __name__ == "__main__":
    main()
