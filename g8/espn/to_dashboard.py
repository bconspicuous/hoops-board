#!/usr/bin/env python3
"""g8/data (ESPN sync of the 8-team league) -> src/data docs of the 8-team dashboard, then rebuild index.html.

  rosters.json  active/IR per team + O/DTD status (names mapped to the projection pool; unknown names kept as-is)
  live.json     current matchup category totals (only when run between 03:00 and 13:00 US Eastern, so no game is in progress;
                totals then cover games through yesterday ET). The weekly add count comes from ESPN's acquisition counter.
  results.json  final category W-L-T of completed matchup periods (oriented to the dashboard's away/home pairs)
  actuals.json  2026-27 per-game averages from ESPN (GP, DD included) for rostered players and the top free agents
Keeps meta.json / fa.json / rules.json. Stdlib only. Usage (repo root): python g8/espn/to_dashboard.py [--no-build]
"""
import csv, difflib, json, os, re, shutil, subprocess, sys, unicodedata
from datetime import datetime, timedelta, timezone

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
G8 = os.path.join(ROOT, "g8", "data"); SRC = os.path.join(ROOT, "src"); DATA = os.path.join(SRC, "data")
CATS = {"FG%": "FG", "FT%": "FT", "3PM": "TPM", "REB": "REB", "AST": "AST", "STL": "STL", "BLK": "BLK", "TO": "TO", "PF": "PF", "DD": "DD", "PTS": "PTS"}
LOW = {"TO", "PF"}


def note(kind, msg): print(f"::{kind} title=g8 dashboard::{msg}")


def norm(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[.'`]", "", s); s = re.sub(r"\b(jr|sr|ii|iii|iv)\b", "", s)
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


ref = json.load(open(os.path.join(SRC, "ref22.json"), encoding="utf-8"))
POOL = {norm(p[0]): p[0] for p in ref["players"]}
TEAMS = ref["teams"]


def pname(n):
    return POOL.get(norm(n), n)


def tname(n, cache={}):
    if n in TEAMS: return n
    if n not in cache:
        m = difflib.get_close_matches(n, TEAMS, n=1, cutoff=0.6) or [x for x in TEAMS if norm(x) == norm(n)]
        cache[n] = m[0] if m else None
        if not m: note("warning", f"ESPN team '{n}' not matched to a dashboard team")
    return cache[n]


def load(p, d=None):
    try: return json.load(open(p, encoding="utf-8"))
    except FileNotFoundError: return d


def dump(name, obj):
    p = os.path.join(DATA, name + ".json"); old = load(p)
    keep = lambda o: {k: v for k, v in (o or {}).items() if k != "asOf"}
    if keep(old) == keep(obj): return False
    json.dump(obj, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1); return True


def main(build=True):
    ros, sb, meta = load(os.path.join(G8, "rosters.json")), load(os.path.join(G8, "scoreboard.json")), load(os.path.join(G8, "meta.json"), {})
    if not ros or not sb:
        note("notice", "g8/data not present yet - nothing to convert"); return
    asOf = ros.get("asOf"); changed = []
    # ---- rosters
    teams, status, unknown = {}, {}, []
    for t in ros["teams"]:
        tn = tname(t["name"])
        if not tn: continue
        act = [pname(n) for n in t["players"]]; ir = [pname(n) for n in t["ir"]]
        unknown += [n for n in act + ir if n not in {p[0] for p in ref["players"]}]
        teams[tn] = {"active": act, "ir": ir}
    for st, names in (ros.get("status") or {}).items():
        for n in names: status[pname(n)] = st
    on = {n for t in teams.values() for n in t["active"] + t["ir"]}
    status = {n: s for n, s in status.items() if n in on}
    ov = (load(os.path.join(DATA, "meta.json"), {}) or {}).get("statusOverride") or {}   # user-set statuses beat ESPN's
    for n, s in ov.items():
        if n in on: status[n] = s
        elif s: note("notice", f"statusOverride for {n} ignored (not on a roster)")
    if len(teams) != len(TEAMS): note("warning", f"{len(teams)} of {len(TEAMS)} teams matched")
    if unknown: note("notice", "no projection (ignored by the simulation): " + ", ".join(sorted(set(unknown))[:15]))
    if dump("rosters", {"asOf": asOf, "source": "ESPN API sync (GitHub Actions g8-espn)", "teams": teams, "status": status}): changed.append("rosters")
    # ---- matchups: results (final periods) and live (current period)
    cur = sb.get("currentMatchupPeriod"); games = sb.get("matchups") or []
    def side_cats(s): return {CATS[k]: v for k, v in (s.get("cats") or {}).items() if k in CATS}
    def find(period, a, b):
        for g in games:
            if g.get("period") != period: continue
            h, w = tname(g["home"]["team"]), tname(g["away"]["team"])
            if {h, w} == {a, b}: return (g["away"], g["home"]) if w == a else (g["home"], g["away"]), g
        return None, None
    results = load(os.path.join(DATA, "results.json"), {}) or {}
    weeks = dict(results.get("weeks") or {}); totals = dict(results.get("totals") or {})
    for wi, pairs in enumerate(ref["matchups"]):
        period = wi + 1
        if cur is None or period >= cur: continue
        rows, tot = [], {}
        for a, b in pairs:
            pair, g = find(period, a, b)
            if not g or g.get("winner") in (None, "UNDECIDED"): rows = None; break
            sa, sb2 = pair
            rows.append({"away": a, "home": b, "a": [int(sa.get("wins") or 0), int(sa.get("losses") or 0), int(sa.get("ties") or 0)]})
            tot[a] = side_cats(sa); tot[b] = side_cats(sb2)
        if rows: weeks[str(period)] = rows; totals[str(period)] = tot
    if dump("results", {"asOf": asOf, "source": "ESPN API sync — final category results", "weeks": weeks, "totals": totals}): changed.append("results")
    try:
        from zoneinfo import ZoneInfo; et = datetime.now(ZoneInfo("America/New_York"))
    except Exception:
        et = datetime.now(timezone(timedelta(hours=-5)))
    # live totals are safe when no NBA game is in progress: yesterday's (ET) games all final and none of today's started.
    # Uses ESPN's public scoreboard (g8/data/nba_days.json); falls back to the 03:00-13:00 ET window if it is missing.
    nd, quiet = load(os.path.join(G8, "nba_days.json"), {}) or {}, None
    y, t = (et.date() - timedelta(days=1)).isoformat(), et.date().isoformat()
    if nd.get("days") and y in nd["days"] and t in nd["days"] and not nd.get("error"):
        quiet = all(g.get("state") == "post" for g in nd["days"][y]) and all(g.get("state") == "pre" for g in nd["days"][t])
        note("notice", f"NBA games: yesterday {[g.get('state') for g in nd['days'][y]].count('post')}/{len(nd['days'][y])} final, "
                       f"today {[g.get('state') for g in nd['days'][t]].count('pre')}/{len(nd['days'][t])} not started -> live {'updated' if quiet else 'kept'}")
    if quiet is None: quiet = 3 <= et.hour < 13
    if cur and quiet:
        cats = {}
        for a, b in ref["matchups"][cur - 1] if cur - 1 < len(ref["matchups"]) else []:
            pair, g = find(cur, a, b)
            if g: cats[a] = side_cats(pair[0]); cats[b] = side_cats(pair[1])
        adds = {}
        for t in ros["teams"]:
            tn = tname(t["name"]); acq = t.get("acqByPeriod") or {}
            if tn: adds[tn] = int(acq.get(str(cur), acq.get(cur, 0)) or 0)
        live = {"asOf": asOf, "week": cur, "through": (et.date() - timedelta(days=1)).isoformat(),
                "source": "ESPN API sync — current matchup totals through yesterday (US Eastern)", "cats": cats, "adds": adds}
        if cats and dump("live", live): changed.append("live")
    else:
        note("notice", f"live totals not updated at {et:%H:%M} ET (a game is in progress or yesterday's games are not all final)")
    # ---- actuals (ESPN season averages)
    acts = {}
    csvp = os.path.join(G8, "players_2027.csv")
    if os.path.exists(csvp):
        f = lambda r, k: float(r[k]) if r.get(k) not in (None, "") else 0.0
        for r in csv.DictReader(open(csvp, encoding="utf-8")):
            g = f(r, "G")
            if g <= 0: continue
            n = pname(r["Player"])
            acts[n] = {"g": int(round(g)), "min": round(f(r, "MP"), 1), "fgm": f(r, "FG"), "fga": f(r, "FGA"), "ftm": f(r, "FT"), "fta": f(r, "FTA"),
                       "tpm": f(r, "3P"), "reb": f(r, "TRB"), "ast": f(r, "AST"), "stl": f(r, "STL"), "blk": f(r, "BLK"), "to": f(r, "TOV"),
                       "pf": f(r, "PF") if r.get("PF") not in (None, "") else None, "pts": f(r, "PTS"),
                       "dd": round(f(r, "DD") * g) if r.get("DD") not in (None, "") else None}
        if acts and dump("actuals", {"asOf": (asOf or "")[:10] + " (ESPN)", "through": (et.date() - timedelta(days=1)).isoformat(),
                                     "source": "ESPN API season averages (rostered + top-200 free agents)", "players": acts}): changed.append("actuals")
    print("changed:", changed or "none")
    if build and changed:
        subprocess.run([sys.executable, "build_v22.py", "data"], cwd=SRC, check=True)
        shutil.copyfile(os.path.join(SRC, "web", "index.html"), os.path.join(ROOT, "index.html"))
        print("rebuilt index.html")


if __name__ == "__main__":
    main(build="--no-build" not in sys.argv)
