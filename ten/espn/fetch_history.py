#!/usr/bin/env python3
"""One-off: per-game logs 2021-2026 from Basketball Reference for the v2 projection model.

Reads ten/espn/history_players.json [{name, brId, seasons}], fetches
https://www.basketball-reference.com/players/<x>/<brId>/gamelog/<season> (regular season),
writes ten/data/history/gamelogs.csv (player, season, date, mp, fg, fga, fg3, ft, fta, trb, ast, stl, blk, tov, pts).
Respects BR's crawl limit (<= 20 requests/minute). Resumable: skips player-seasons already in the CSV.
"""
import csv, json, os, re, sys, time, html, urllib.request, urllib.error
BASE = os.path.dirname(__file__)
OUT = os.path.join(BASE, "..", "data", "history"); os.makedirs(OUT, exist_ok=True)
CSV = os.path.join(OUT, "gamelogs.csv")
COLS = ["player", "season", "date", "mp", "fg", "fga", "fg3", "ft", "fta", "trb", "ast", "stl", "blk", "tov", "pts"]
DELAY = float(os.environ.get("BR_DELAY", "3.4")); LIMIT = int(os.environ.get("LIMIT", "0")); BUDGET = float(os.environ.get("BUDGET_MIN", "320")) * 60
players = json.load(open(os.path.join(BASE, "history_players.json"), encoding="utf-8"))
done = set()
if os.path.exists(CSV):
    for r in csv.DictReader(open(CSV, encoding="utf-8")): done.add((r["player"], r["season"]))
    for r in csv.DictReader(open(os.path.join(OUT, "status.csv"), encoding="utf-8")) if os.path.exists(os.path.join(OUT, "status.csv")) else []:
        if r["status"] in ("ok", "empty"): done.add((r["player"], r["season"]))
new = not os.path.exists(CSV)
fo = open(CSV, "a", newline="", encoding="utf-8"); w = csv.DictWriter(fo, fieldnames=COLS)
if new: w.writeheader()
sn = os.path.join(OUT, "status.csv"); snew = not os.path.exists(sn)
so = open(sn, "a", newline="", encoding="utf-8"); sw = csv.DictWriter(so, fieldnames=["player", "season", "status", "games"])
if snew: sw.writeheader()
ROW = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S); CELL = re.compile(r'<(?:td|th)[^>]*data-stat="([^"]+)"[^>]*>(.*?)</(?:td|th)>', re.S); TAG = re.compile(r"<[^>]+>")
def parse(page):
    # regular-season table only: old id "pgl_basic", new id "player_game_log_reg"
    m = re.search(r'<table[^>]+id="(?:player_game_log_reg|pgl_basic)"[^>]*>(.*?)</table>', page, re.S)
    if not m:  # tables can be wrapped in HTML comments
        m = re.search(r'<table[^>]+id="(?:player_game_log_reg|pgl_basic)"[^>]*>(.*?)</table>', page.replace("<!--", "").replace("-->", ""), re.S)
    if not m: return None
    rows = []
    for tr in ROW.findall(m.group(1)):
        c = {k: html.unescape(TAG.sub("", v)).strip() for k, v in CELL.findall(tr)}
        d = c.get("date") or c.get("date_game")
        if not d or not re.match(r"\d{4}-\d{2}-\d{2}", d): continue
        if not c.get("mp") or c.get("reason"): continue
        mp = c["mp"]; mp = (int(mp.split(":")[0]) + int(mp.split(":")[1]) / 60) if ":" in mp else float(mp or 0)
        g = lambda k: c.get(k, "") or "0"
        rows.append({"date": d, "mp": round(mp, 2), "fg": g("fg"), "fga": g("fga"), "fg3": g("fg3"), "ft": g("ft"), "fta": g("fta"), "trb": g("trb"),
                     "ast": g("ast"), "stl": g("stl"), "blk": g("blk"), "tov": g("tov"), "pts": g("pts")})
    return rows
t0 = time.time(); n = 0; fails = 0
for p in players:
    for s in p["seasons"]:
        if (p["name"], str(s)) in done: continue
        if LIMIT and n >= LIMIT: break
        if time.time() - t0 > BUDGET: print("time budget reached"); break
        url = f"https://www.basketball-reference.com/players/{p['brId'][0]}/{p['brId']}/gamelog/{s}"
        st, games = "fail", 0
        for att in range(3):
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36", "Accept-Language": "en-US,en;q=0.9"})
                with urllib.request.urlopen(req, timeout=40) as r: page = r.read().decode("utf-8", "replace")
                rows = parse(page)
                if rows is None: st = "notable"; break
                for row in rows: w.writerow({"player": p["name"], "season": s, **row})
                st, games = ("ok" if rows else "empty"), len(rows); break
            except urllib.error.HTTPError as e:
                st = f"http{e.code}"
                if e.code == 429: print("429 rate limited - sleeping 70s"); time.sleep(70)
                elif e.code == 404: break
            except Exception as e:
                st = "err"; time.sleep(5)
        sw.writerow({"player": p["name"], "season": s, "status": st, "games": games}); fo.flush(); so.flush()
        n += 1; fails += st not in ("ok", "empty")
        if n % 50 == 0: print(f"{n} requests, {fails} failures, {int(time.time() - t0)}s")
        time.sleep(DELAY)
    else:
        continue
    break
print(f"done: {n} requests, {fails} failures, {int(time.time() - t0)}s")
