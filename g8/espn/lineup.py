#!/usr/bin/env python3
"""Set the 8-team league lineup on ESPN from an approved plan (g8/lineup/plan.json). Runs ONLY inside the GitHub Action
(.github/workflows/g8-lineup.yml), which holds the ESPN cookies as secrets; the cookies are never printed or written.

  mode=dry   read the live ESPN lineup, map the plan to ESPN player ids and slots, list the moves, write g8/lineup/last_run.json.
             Never writes to ESPN.
  mode=live  same, then — only if the plan's status is "approved" and its date is today or later (US Eastern) — submit the moves
             as one ESPN ROSTER transaction, re-read the lineup and verify it. Players whose game has already started are never moved.

Plan format (written by g8/sim/lineup.js, approved by the manager):
  {"id": "...", "date": "YYYY-MM-DD" (US Eastern game day), "status": "pending|approved|executed|rejected|failed",
   "slots": [{"name": "Rudy Gobert", "slot": "C"}, ...  every rostered player, slot in PG SG SF PF C G F UTIL BE IR]}
Stdlib only."""
import json, os, re, sys, time, unicodedata, urllib.request, urllib.error
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(__file__))
import fetch_g8 as F                                   # same league id / season / cookie handling as the sync

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PLAN = os.environ.get("PLAN", os.path.join(ROOT, "g8", "lineup", "plan.json"))
OUT = os.path.join(ROOT, "g8", "lineup", "last_run.json")
MODE = (os.environ.get("MODE") or "dry").lower()
SLOT_ID = {"PG": 0, "SG": 1, "SF": 2, "PF": 3, "C": 4, "G": 5, "F": 6, "UTIL": 11, "BE": 12, "IR": 13}
ID_SLOT = {v: k for k, v in SLOT_ID.items()}
WRITE_HOST = "https://lm-api-writes.fantasy.espn.com"
try:
    from zoneinfo import ZoneInfo; ET = ZoneInfo("America/New_York")
except Exception:
    ET = timezone(timedelta(hours=-5))


def norm(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[.'`]", "", s); s = re.sub(r"\b(jr|sr|ii|iii|iv)\b", "", s)
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def note(kind, msg): print(f"::{kind} title=g8 lineup::{msg}")


def save(obj):
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(obj, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


def cookie_headers():
    s2, swid = os.environ.get("ESPN_S2"), os.environ.get("ESPN_SWID")
    if not (s2 and swid): F.die("G8_ESPN_S2 / G8_ESPN_SWID secrets are required")
    return {"Cookie": f"espn_s2={s2}; SWID={swid}", "User-Agent": "Mozilla/5.0 (hoops-board g8 lineup)", "Accept": "application/json"}, swid


def read_team():
    lg = F.get(["mTeam", "mRoster", "mSettings", "mStatus"])
    me = next((t for t in lg.get("teams") or [] if F.team_name(t) == F.MY_TEAM), None)
    if not me: F.die(f"team {F.MY_TEAM} not found")
    entries = []
    for e in (me.get("roster") or {}).get("entries", []):
        p = (e.get("playerPoolEntry") or {}).get("player") or {}
        entries.append({"id": e.get("playerId") or p.get("id"), "name": p.get("fullName"), "slot": e.get("lineupSlotId"),
                        "eligible": p.get("eligibleSlots") or [], "proTeamId": p.get("proTeamId"),
                        "locked": bool((e.get("playerPoolEntry") or {}).get("lineupLocked") or e.get("lineupLocked"))})
    counts = {int(k): v for k, v in (((lg.get("settings") or {}).get("rosterSettings") or {}).get("lineupSlotCounts") or {}).items()}
    return lg, me, entries, counts


def game_starts(day):
    """proTeamId -> tip-off (ET) on `day`, from the fantasy API's pro schedule (same cookies)."""
    h, _ = cookie_headers()
    url = f"https://lm-api-reads.fantasy.espn.com/apis/v3/games/fba/seasons/{F.SEASON}?view=proTeamSchedules_wl"
    with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=30) as r:
        data = json.loads(r.read().decode("utf-8"))
    out = {}
    for t in (data.get("settings") or {}).get("proTeams") or []:
        for games in (t.get("proGamesByScoringPeriod") or {}).values():
            for g in games:
                if not g.get("date"): continue
                st = datetime.fromtimestamp(g["date"] / 1000, ET)
                if st.date() == day:
                    for tid in (g.get("homeProTeamId"), g.get("awayProTeamId")):
                        if tid is not None: out[tid] = st
    return out


def mark(plan, status, **kw):
    plan.update(status=status, **kw); json.dump(plan, open(PLAN, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


def main():
    plan = json.load(open(PLAN, encoding="utf-8"))
    if not plan.get("slots"):
        save({"planId": plan.get("id"), "mode": MODE, "date": plan.get("date"), "ok": True, "note": f"plan has no lineup (status {plan.get('status')})"}); print("nothing to do"); return
    now = datetime.now(ET); day = datetime.strptime(plan["date"], "%Y-%m-%d").date()
    res = {"planId": plan.get("id"), "mode": MODE, "date": plan["date"], "at": now.isoformat(timespec="minutes"), "moves": [], "skipped": [], "ok": False}
    if day < now.date():
        res["error"] = "plan date is in the past"; save(res); F.die(res["error"])
    if MODE == "live" and day != now.date():
        res["error"] = "live runs only set today's lineup (US Eastern); re-plan on the game day"; save(res); F.die(res["error"])
    lg, me, entries, counts = read_team()
    sp_now = lg.get("scoringPeriodId")
    sp = sp_now + (day - now.date()).days
    res["scoringPeriodId"] = sp
    try:
        starts = game_starts(day)
    except Exception as e:
        starts = {}; note("warning", f"pro schedule unavailable ({e}); relying on ESPN lineupLocked flags only")
    by = {norm(e["name"]): e for e in entries}
    want, unknown = {}, []
    for s in plan["slots"]:
        e = by.get(norm(s["name"]))
        if not e: unknown.append(s["name"]); continue
        if s["slot"] not in SLOT_ID: F.die(f"unknown slot {s['slot']} for {s['name']}")
        want[e["id"]] = SLOT_ID[s["slot"]]
    if unknown: res["unknownPlayers"] = unknown; note("warning", "not on the ESPN roster (ignored): " + ", ".join(unknown))
    items = []
    for e in entries:
        to = want.get(e["id"])
        if to is None or to == e["slot"]: continue
        tip = starts.get(e["proTeamId"])
        if 13 in (to, e["slot"]):                                # IR moves change the roster size: the manager does them by hand
            res["skipped"].append({"name": e["name"], "from": ID_SLOT.get(e["slot"]), "to": ID_SLOT.get(to), "why": "IR slot — not changed automatically"}); continue
        if day == now.date() and (e["locked"] or (tip and now >= tip)):   # lineupLocked refers to today's scoring period only
            res["skipped"].append({"name": e["name"], "from": ID_SLOT.get(e["slot"]), "to": ID_SLOT.get(to), "why": "game started / locked"}); continue
        if to not in e["eligible"]:
            res["skipped"].append({"name": e["name"], "from": ID_SLOT.get(e["slot"]), "to": ID_SLOT.get(to), "why": "not eligible"}); continue
        items.append({"playerId": e["id"], "type": "LINEUP", "fromLineupSlotId": e["slot"], "toLineupSlotId": to})
        res["moves"].append({"name": e["name"], "from": ID_SLOT.get(e["slot"]), "to": ID_SLOT.get(to)})
    # resulting lineup must respect the league's slot counts
    final = {e["id"]: e["slot"] for e in entries}
    for it in items: final[it["playerId"]] = it["toLineupSlotId"]
    used = {}
    for v in final.values(): used[v] = used.get(v, 0) + 1
    over = {ID_SLOT.get(k, k): n for k, n in used.items() if k not in (12,) and n > counts.get(k, 0)}
    res["finalLineup"] = sorted(([ID_SLOT.get(v, v), e["name"]] for e in entries for v in [final[e["id"]]]), key=lambda x: list(SLOT_ID).index(x[0]) if x[0] in SLOT_ID else 99)
    if over:
        res["error"] = f"resulting lineup exceeds slot counts {over} (a locked player blocks a swap?) — nothing submitted"; save(res); F.die(res["error"])
    print(json.dumps({"moves": res["moves"], "skipped": res["skipped"]}, ensure_ascii=False))
    if MODE != "live" or not items:
        res["ok"] = True; res["note"] = "dry run — nothing written" if MODE != "live" else "no change needed"; save(res)
        if MODE == "live" and plan.get("status") == "approved": mark(plan, "executed", executedAt=res["at"], moves=[], skipped=res["skipped"])
        return
    if plan.get("status") != "approved":
        res["error"] = f"plan status is '{plan.get('status')}', not 'approved' — nothing submitted"; save(res); F.die(res["error"])
    h, swid = cookie_headers(); h["Content-Type"] = "application/json"
    body = {"isLeagueManager": False, "teamId": me["id"], "type": "ROSTER", "memberId": swid, "scoringPeriodId": sp, "executionType": "EXECUTE", "items": items}
    url = f"{WRITE_HOST}/apis/v3/games/fba/seasons/{F.SEASON}/segments/0/leagues/{F.LEAGUE_ID}/transactions/"
    try:
        with urllib.request.urlopen(urllib.request.Request(url, data=json.dumps(body).encode(), headers=h, method="POST"), timeout=30) as r:
            resp = json.loads(r.read().decode("utf-8") or "{}")
        res["response"] = {k: resp.get(k) for k in ("id", "status", "type", "scoringPeriodId") if isinstance(resp, dict)}
    except urllib.error.HTTPError as e:
        res["error"] = f"ESPN rejected the lineup ({e.code}): {e.read()[:400]!r}"; save(res); mark(plan, "failed", failedAt=res["at"]); F.die(res["error"])
    time.sleep(3)
    _, _, after, _ = read_team()
    got = {e["id"]: e["slot"] for e in after}
    miss = [m for m, it in zip(res["moves"], items) if got.get(it["playerId"]) != it["toLineupSlotId"]]
    res["verified"] = not miss; res["notApplied"] = miss; res["ok"] = not miss
    save(res); mark(plan, "executed" if not miss else "failed", executedAt=res["at"], moves=res["moves"], skipped=res["skipped"])
    if miss: F.die("submitted, but ESPN shows a different lineup for: " + ", ".join(m["name"] for m in miss))
    print("lineup set and verified")


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception:
        import traceback
        F.die("crash: " + traceback.format_exc()[-900:])
