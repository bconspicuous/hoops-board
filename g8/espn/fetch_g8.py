#!/usr/bin/env python3
"""ESPN Fantasy Basketball (v3) fetcher for the 8-team league "G League" (ESPN 751654965).
Independent copy of ten/espn/fetch_espn.py (no shared code or files with the 10-team league).

Pulls teams, rosters (with injury status and 2027 season averages), the current
matchup scoreboard (category totals) and the top free agents, then writes:
  g8/data/espn_raw_league.json   trimmed raw response (for debugging / new fields)
  g8/data/rosters.json           rosters in the dashboard's format (players, ir, status)
  g8/data/scoreboard.json        current + past matchups with category totals and W-L-T
  g8/data/players_2027.csv       season averages for rostered players and top free agents
  g8/data/meta.json              fetch time, scoring period, matchup period

Private leagues need the espn_s2 and SWID cookies (env ESPN_S2, ESPN_SWID).
Stdlib only, so it runs on a bare GitHub Actions runner.
"""
import csv, json, os, sys, time, urllib.request, urllib.error
from datetime import datetime, timezone, timedelta

LEAGUE_ID = os.environ.get("ESPN_LEAGUE_ID", "751654965")
SEASON = int(os.environ.get("ESPN_SEASON", "2027"))      # ESPN labels 2026-27 as 2027
OUT = os.environ.get("ESPN_OUT", os.path.join(os.path.dirname(__file__), "..", "data"))
HOSTS = ["https://lm-api-reads.fantasy.espn.com", "https://fantasy.espn.com"]
PATH = f"/apis/v3/games/fba/seasons/{SEASON}/segments/0/leagues/{LEAGUE_ID}"

# ESPN basketball stat ids (community-documented; unknown ids are kept as "s<id>")
STAT = {0: "PTS", 1: "BLK", 2: "STL", 3: "AST", 9: "PF", 4: "OREB", 5: "DREB", 6: "REB", 11: "TO", 13: "FGM", 14: "FGA",
        15: "FTM", 16: "FTA", 17: "3PM", 18: "3PA", 19: "FG%", 20: "FT%", 21: "3P%", 37: "DD", 38: "TD", 40: "MIN", 41: "GS", 42: "GP", 43: "TW"}
SLOT = {0: "PG", 1: "SG", 2: "SF", 3: "PF", 4: "C", 5: "G", 6: "F", 7: "SG/SF", 8: "G/F", 9: "PF/C", 10: "F/C", 11: "UTIL", 12: "BE", 13: "IR"}
PRO = {1: "ATL", 2: "BOS", 3: "NOP", 4: "CHI", 5: "CLE", 6: "DAL", 7: "DEN", 8: "DET", 9: "GSW", 10: "HOU", 11: "IND", 12: "LAC", 13: "LAL", 14: "MIA",
       15: "MIL", 16: "MIN", 17: "BKN", 18: "NYK", 19: "ORL", 20: "PHI", 21: "PHX", 22: "POR", 23: "SAC", 24: "SAS", 25: "OKC", 26: "UTA", 27: "WAS",
       28: "TOR", 29: "MEM", 30: "CHA", 0: "FA"}
INJ = {"OUT": "O", "DAY_TO_DAY": "DTD", "INJURY_RESERVE": "O", "SUSPENSION": "O", "QUESTIONABLE": "DTD", "DOUBTFUL": "DTD"}
# dashboard team codes by ESPN team name (fallback: ESPN abbrev)
CODE = {}   # 8-team league: the full ESPN team name is the code (the dashboard keys teams by name)
MY_TEAM = os.environ.get("ESPN_MY_TEAM", "Garak Twindragons")


def die(msg):
    print("::error title=ESPN sync::" + msg.replace("\n", " "))   # visible as a run annotation
    sys.exit(1)


def get(views, extra_headers=None):
    q = "&".join("view=" + v for v in views)
    hdr = {"User-Agent": "Mozilla/5.0 (hoops-board g8 fetcher)", "Accept": "application/json"}
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
                    die(f"ESPN denied access ({e.code}). Private league: set ESPN_S2 and ESPN_SWID secrets. {last}")
            except Exception as e:  # network / JSON
                last = f"{host}: {e}"
            time.sleep(2 * (attempt + 1))
    die("ESPN fetch failed: " + str(last))


def fetch_injuries():
    """League-wide NBA injury report from ESPN's public site API (includes estimated return dates)."""
    out, errs = [], []
    for url in ["https://site.api.espn.com/apis/site/v2/sports/basketball/nba/injuries",
                "https://site.web.api.espn.com/apis/site/v2/sports/basketball/nba/injuries"]:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (hoops-board g8 fetcher)", "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=30) as r:
                data = json.loads(r.read().decode("utf-8"))
            for team in data.get("injuries") or []:
                for inj in team.get("injuries") or []:
                    a = inj.get("athlete") or {}
                    d = inj.get("details") or {}
                    out.append({"player": a.get("displayName"), "team": (a.get("team") or {}).get("abbreviation") or team.get("displayName"),
                                "status": inj.get("status"), "date": inj.get("date"), "type": inj.get("type", {}).get("description") if isinstance(inj.get("type"), dict) else inj.get("type"),
                                "returnDate": d.get("returnDate"), "detail": d.get("detail"), "side": d.get("side"), "injury": d.get("type"),
                                "fantasyStatus": (d.get("fantasyStatus") or {}).get("description"),
                                "short": inj.get("shortComment"), "long": inj.get("longComment")})
            if out:
                return out, None
        except Exception as e:
            errs.append(f"{url}: {e}")
    return out, "; ".join(errs)


def fetch_nba_days():
    """NBA games of yesterday and today (US Eastern), each with state pre / in / post. Lets the converter take the live matchup
    totals whenever no game is in progress, not only in a fixed time window. Source: ESPN's public scoreboard; if that is refused,
    the fantasy API's pro-team schedule (start times only: a game counts as final 3h30m after tip-off)."""
    try:
        from zoneinfo import ZoneInfo; ET = ZoneInfo("America/New_York")
    except Exception:
        ET = timezone(timedelta(hours=-5))
    now = datetime.now(ET); want = [now.date() - timedelta(days=1), now.date()]
    out, errs = {"asOfET": now.isoformat(timespec="minutes"), "days": {}, "source": None}, []
    hdr = {"User-Agent": "Mozilla/5.0 (hoops-board g8 fetcher)", "Accept": "application/json"}
    for base in ("https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard?dates=",
                 "https://site.web.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard?dates="):
        try:
            days = {}
            for d in want:
                with urllib.request.urlopen(urllib.request.Request(base + d.strftime("%Y%m%d"), headers=hdr), timeout=30) as r:
                    data = json.loads(r.read().decode("utf-8"))
                days[d.isoformat()] = [{"id": e.get("id"), "start": e.get("date"), "name": e.get("shortName"),
                                        "state": (((e.get("status") or {}).get("type") or {}).get("state"))} for e in data.get("events") or []]
            out.update(days=days, source=base.split("/apis")[0]); return out
        except Exception as e:
            errs.append(f"{base.split('/apis')[0]}: {e}")
    try:   # fantasy API pro schedule (same auth as the league fetch)
        h = dict(hdr); s2, swid = os.environ.get("ESPN_S2"), os.environ.get("ESPN_SWID")
        if s2 and swid: h["Cookie"] = f"espn_s2={s2}; SWID={swid}"
        url = f"https://lm-api-reads.fantasy.espn.com/apis/v3/games/fba/seasons/{SEASON}?view=proTeamSchedules_wl"
        with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=30) as r:
            data = json.loads(r.read().decode("utf-8"))
        seen, days = set(), {d.isoformat(): [] for d in want}
        for t in (data.get("settings") or {}).get("proTeams") or []:
            for games in (t.get("proGamesByScoringPeriod") or {}).values():
                for g in games:
                    if g.get("id") in seen or not g.get("date"): continue
                    seen.add(g.get("id")); st = datetime.fromtimestamp(g["date"] / 1000, ET); k = st.date().isoformat()
                    if k not in days: continue
                    state = "pre" if now < st else ("post" if now > st + timedelta(hours=3, minutes=30) else "in")
                    days[k].append({"id": g.get("id"), "start": st.isoformat(timespec="minutes"), "state": state})
        if seen:
            out.update(days=days, source="fantasy proTeamSchedules (start times)"); return out
        errs.append("fantasy proTeamSchedules: no games")
    except Exception as e:
        errs.append(f"fantasy proTeamSchedules: {e}")
    out["error"] = "; ".join(errs)
    return out


def team_name(t):
    if t.get("name"):
        return t["name"].strip()
    return f"{t.get('location', '')} {t.get('nickname', '')}".strip()


def season_avg(player):
    """2027 actual season averages (statSourceId 0, statSplitTypeId 0)."""
    for s in player.get("stats") or []:
        if s.get("seasonId") == SEASON and s.get("statSourceId") == 0 and s.get("statSplitTypeId") == 0:
            avg = s.get("averageStats") or {}
            out = {}
            for k, v in avg.items():
                try:
                    out[STAT.get(int(k), f"s{k}")] = round(float(v), 3)
                except (TypeError, ValueError):
                    pass
            return out
    return {}


def player_row(p, owner, slot=None, status=None):
    a = season_avg(p)
    return {"Player": p.get("fullName"), "Team": PRO.get(p.get("proTeamId"), str(p.get("proTeamId"))), "Owner": owner, "Slot": slot or "",
            "Status": status or INJ.get(p.get("injuryStatus") or "", ""), "G": a.get("GP", ""), "MP": a.get("MIN", ""),
            "FG": a.get("FGM", ""), "FGA": a.get("FGA", ""), "3P": a.get("3PM", ""), "FT": a.get("FTM", ""), "FTA": a.get("FTA", ""),
            "TRB": a.get("REB", ""), "AST": a.get("AST", ""), "STL": a.get("STL", ""), "BLK": a.get("BLK", ""), "TOV": a.get("TO", ""), "PF": a.get("PF", ""),
            "PTS": a.get("PTS", ""), "DD": a.get("DD", ""), "TW": a.get("TW", ""), "espnId": p.get("id"), "elig": "/".join(SLOT[x] for x in (p.get("eligibleSlots") or []) if x in (0, 1, 2, 3, 4))}


def main():
    os.makedirs(OUT, exist_ok=True)
    lg = get(["mSettings", "mTeam", "mRoster", "mMatchupScore", "mScoreboard", "mStatus"])
    teams = lg.get("teams") or []
    if not teams:
        die("No teams in response - check league id / season / cookies")
    tname = {t["id"]: team_name(t) for t in teams}
    tcode = {t["id"]: team_name(t) for t in teams}

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
        tc = t.get("transactionCounter") or {}
        rosters.append({"name": tname[t["id"]], "abbr": tcode[t["id"]], "espnId": t["id"], "me": tname[t["id"]] == MY_TEAM,
                        "players": players, "ir": ir, "record": {k: rec.get(k) for k in ("wins", "losses", "ties", "percentage")},
                        "acqByPeriod": tc.get("matchupAcquisitionTotals") or {}, "acqTotal": tc.get("acquisitions")})

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
    json.dump({"asOf": now, "currentMatchupPeriod": sp, "scoringPeriodId": lg.get("scoringPeriodId"), "matchups": games}, open(os.path.join(OUT, "scoreboard.json"), "w"), ensure_ascii=False, indent=1)
    with open(os.path.join(OUT, "players_2027.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    trim = {k: lg.get(k) for k in ("id", "seasonId", "scoringPeriodId", "status")}
    try:
        e0 = teams[0]["roster"]["entries"][0]["playerPoolEntry"]["player"]
        trim["samplePlayer"] = {"fullName": e0.get("fullName"), "injuryStatus": e0.get("injuryStatus"), "stats": [x for x in e0.get("stats") or [] if x.get("seasonId") == SEASON][:4]}
        trim["sampleMatchup"] = (lg.get("schedule") or [None])[0]
    except Exception:
        pass
    trim["settings"] = {k: (lg.get("settings") or {}).get(k) for k in ("name", "scoringSettings", "rosterSettings", "scheduleSettings", "tradeSettings", "acquisitionSettings")}
    json.dump(trim, open(os.path.join(OUT, "espn_raw_league.json"), "w"), ensure_ascii=False, indent=1)
    json.dump({"asOf": now, "scoringPeriodId": lg.get("scoringPeriodId"), "currentMatchupPeriod": sp, "teams": len(teams), "players": len(rows),
               "auth": bool(os.environ.get("ESPN_S2")), "league": "g8"}, open(os.path.join(OUT, "meta.json"), "w"), indent=1)
    inj, ierr = fetch_injuries()
    json.dump({"asOf": now, "source": "site.api.espn.com nba/injuries", "error": ierr, "injuries": inj}, open(os.path.join(OUT, "injuries.json"), "w"), ensure_ascii=False, indent=1)
    print(f"injuries: {len(inj)} {ierr or ''}")
    nd = fetch_nba_days()
    json.dump(nd, open(os.path.join(OUT, "nba_days.json"), "w"), ensure_ascii=False, indent=1)
    print("nba days:", nd.get("source"), {k: [g["state"] for g in v] for k, v in nd["days"].items()}, nd.get("error") or "")
    print(f"ok: {len(teams)} teams, {len(rows)} players, matchup period {sp}, asOf {now}")


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception:
        import traceback
        die("crash: " + traceback.format_exc()[-900:])
