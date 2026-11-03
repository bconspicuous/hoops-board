#!/usr/bin/env python3
"""Roster moves (add/drop, IR) for Garak Twindragons from g8/moves/plan.json. Runs ONLY inside the GitHub Action
(.github/workflows/g8-moves.yml) with the 8-team cookies from secrets; cookies are never printed or written.

  mode=dry   for the listed items: check the add is still a free agent / on waivers, the drop is on our roster and droppable, the
             weekly add limit, the max-C limit, IR eligibility, and that our roster still matches the plan. Prints the exact moves.
             Never writes to ESPN.
  mode=live  same checks, then submits ONLY items whose status in plan.json is "approved", one ESPN transaction per item:
               add/drop  type FREEAGENT (or WAIVER for a player on waivers): ADD toTeamId + DROP fromTeamId in one transaction
               IR        type ROSTER: LINEUP move to slot 13 (IR)
               ir+add    IR move first, then the add (no drop)
             After each item the roster is re-read and verified. No automatic retries (ESPN may have processed a request whose
             response was lost); a failed item stops the run.
  ITEMS env: comma-separated item numbers (default: all approved items in live, all items in dry).
  IR rule (manager, 2026-11-03): an IR player who is DTD does not block adds. Not documented by ESPN; the first live add made while
  an IR player is not OUT records ESPN's actual behaviour in g8/moves/ir_rule.json."""
import json, os, re, sys, time, unicodedata, urllib.request, urllib.error
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(__file__))
import fetch_g8 as F

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PLAN = os.path.join(ROOT, "g8", "moves", "plan.json")
OUT = os.path.join(ROOT, "g8", "moves", "last_run.json")
IRRULE = os.path.join(ROOT, "g8", "moves", "ir_rule.json")
MODE = (os.environ.get("MODE") or "dry").lower()
WRITE = f"https://lm-api-writes.fantasy.espn.com/apis/v3/games/fba/seasons/{F.SEASON}/segments/0/leagues/{F.LEAGUE_ID}/transactions/"
OUT_OK = {"OUT", "INJURY_RESERVE", "SUSPENSION"}
try:
    from zoneinfo import ZoneInfo; ET = ZoneInfo("America/New_York")
except Exception:
    ET = timezone(timedelta(hours=-5))


def norm(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[.'`]", "", s); s = re.sub(r"\b(jr|sr|ii|iii|iv)\b", "", s)
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def note(kind, msg): print(f"::{kind} title=g8 moves::{msg}")


def jdump(p, o): os.makedirs(os.path.dirname(p), exist_ok=True); json.dump(o, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


def headers():
    s2, swid = os.environ.get("ESPN_S2"), os.environ.get("ESPN_SWID")
    if not (s2 and swid): F.die("G8_ESPN_S2 / G8_ESPN_SWID secrets are required")
    return {"Cookie": f"espn_s2={s2}; SWID={swid}", "User-Agent": "Mozilla/5.0 (hoops-board g8 moves)", "Accept": "application/json", "Content-Type": "application/json"}, swid


def state():
    lg = F.get(["mTeam", "mRoster", "mSettings", "mStatus"])
    teams = lg.get("teams") or []
    me = next((t for t in teams if F.team_name(t) == F.MY_TEAM), None)
    if not me: F.die(f"team {F.MY_TEAM} not found")
    ent = []
    for e in (me.get("roster") or {}).get("entries", []):
        p = (e.get("playerPoolEntry") or {}).get("player") or {}
        ent.append({"id": e.get("playerId") or p.get("id"), "name": p.get("fullName"), "slot": e.get("lineupSlotId"), "inj": p.get("injuryStatus") or "ACTIVE",
                    "pos": p.get("defaultPositionId"), "eligible": p.get("eligibleSlots") or []})
    owned = {}
    for t in teams:
        for e in (t.get("roster") or {}).get("entries", []):
            owned[e.get("playerId")] = F.team_name(t)
    sp, mp = lg.get("scoringPeriodId"), (lg.get("status") or {}).get("currentMatchupPeriod")
    acq = int(((me.get("transactionCounter") or {}).get("matchupAcquisitionTotals") or {}).get(str(mp), 0) or 0)
    rs = (lg.get("settings") or {}).get("rosterSettings") or {}
    return lg, me, ent, owned, sp, mp, acq, rs


def kona(flt):
    """one kona_player_info read on the league reads host; returns players or None (never exits)"""
    h, _ = headers(); h = dict(h); h.pop("Content-Type", None); h["X-Fantasy-Filter"] = json.dumps(flt)
    url = f"https://lm-api-reads.fantasy.espn.com/apis/v3/games/fba/seasons/{F.SEASON}/segments/0/leagues/{F.LEAGUE_ID}?view=kona_player_info"
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=30) as r:
            return (json.loads(r.read().decode("utf-8")) or {}).get("players") or []
    except Exception as e:
        note("warning", f"player lookup variant failed ({str(e)[:120]})"); return None


def find_player(name, espn_id):
    """player-pool lookup -> {id, name, status FREEAGENT/WAIVERS/ONTEAM, onTeamId, inj, pos}. Tries an id filter, then the same
    top-free-agent query the sync uses, then a name filter."""
    tries = []
    if espn_id: tries.append({"players": {"filterIds": {"value": [int(espn_id)]}}})
    tries.append({"players": {"filterStatus": {"value": ["FREEAGENT", "WAIVERS"]}, "limit": 300, "sortPercOwned": {"sortPriority": 1, "sortAsc": False}}})
    tries.append({"players": {"filterName": {"value": name}, "limit": 25}})
    for flt in tries:
        for pe in kona(flt) or []:
            p = pe.get("player") or {}
            if (espn_id and p.get("id") == int(espn_id)) or norm(p.get("fullName")) == norm(name):
                return {"id": p.get("id"), "name": p.get("fullName"), "status": pe.get("status") or ("ONTEAM" if pe.get("onTeamId") else "FREEAGENT"),
                        "onTeamId": pe.get("onTeamId"), "inj": p.get("injuryStatus"), "pos": p.get("defaultPositionId"), "proTeamId": p.get("proTeamId")}
    return None


def post(body):
    h, _ = headers()
    try:
        with urllib.request.urlopen(urllib.request.Request(WRITE, data=json.dumps(body).encode(), headers=h, method="POST"), timeout=30) as r:
            txt = r.read().decode("utf-8") or "{}"
        try: return True, json.loads(txt)
        except Exception: return True, {"raw": txt[:300]}
    except urllib.error.HTTPError as e:
        return False, {"code": e.code, "body": e.read()[:600].decode("utf-8", "ignore")}


def main():
    plan = json.load(open(PLAN, encoding="utf-8"))
    want = [int(x) for x in (os.environ.get("ITEMS") or "").replace(" ", "").split(",") if x]
    items = [i for i in plan.get("items") or [] if (not want or i["n"] in want)]
    if MODE == "live": items = [i for i in items if i.get("status") == "approved"]
    res = {"planId": plan.get("id"), "mode": MODE, "at": datetime.now(ET).isoformat(timespec="minutes"), "items": [], "ok": False}
    if not items:
        res.update(ok=True, note="no matching items" + (" with status approved" if MODE == "live" else "")); jdump(OUT, res); print(res["note"]); return
    lg, me, ent, owned, sp, mp, acq, rs = state()
    limit = int(((json.load(open(os.path.join(ROOT, "src", "data", "rules.json"), encoding="utf-8")).get("acquisition") or {}).get("perMatchup")) or 7)   # league rule: 7 per matchup
    sig = "|".join(sorted(e["name"] for e in ent if e["slot"] != 13)) + "#" + "|".join(sorted(e["name"] for e in ent if e["slot"] == 13))
    res.update(scoringPeriodId=sp, matchupPeriod=mp, addsUsed=acq, rosterMatchesPlan=(norm(sig) == norm(plan.get("rosterSig", ""))))
    irBad = [e["name"] + f" ({e['inj']})" for e in ent if e["slot"] == 13 and e["inj"] not in OUT_OK]
    if irBad: res["irNotOut"] = irBad; note("warning", "IR player(s) not OUT: " + ", ".join(irBad) + " — manager says DTD does not block adds; checking on the first live add")
    undrop = set((json.load(open(os.path.join(ROOT, "src", "data", "rules.json"), encoding="utf-8")).get("undroppable") or []))
    byname = {norm(e["name"]): e for e in ent}
    maxC = int((json.load(open(os.path.join(ROOT, "src", "data", "rules.json"), encoding="utf-8")).get("roster") or {}).get("maxC") or 4)   # ESPN defaultPositionId 5 = C
    h, swid = headers()
    for it in items:
        r = {"n": it["n"], "kind": it["kind"], "checks": [], "ok": False}; res["items"].append(r)
        def bad(msg): r["checks"].append("✗ " + msg); return False
        okk = True
        if not res["rosterMatchesPlan"]: okk = bad("our ESPN roster changed since the plan was made — re-plan")
        drop = byname.get(norm(it.get("drop"))) if it.get("drop") else None
        irp = byname.get(norm(it.get("ir"))) if it.get("ir") else None
        if it.get("drop") and not drop: okk = bad(f"{it['drop']} is not on our roster")
        if drop and drop["name"] in undrop: okk = bad(f"{drop['name']} is undroppable")
        if irp and it["kind"] == "activate":
            if irp["slot"] != 13: okk = bad(f"{irp['name']} is not on IR")
            if not drop: okk = bad("activation needs a drop (roster is full)")
        elif irp:
            if irp["inj"] not in OUT_OK: okk = bad(f"{irp['name']} is {irp['inj']} — not IR-eligible")
            if sum(1 for e in ent if e["slot"] == 13) >= int((rs.get("lineupSlotCounts") or {}).get("13", 2)): okk = bad("no free IR slot")
        add = None
        if it.get("add"):
            add = find_player(it["add"], it.get("addEspnId"))
            if not add: okk = bad(f"{it['add']} not found in the player pool")
            elif add["status"] not in ("FREEAGENT", "WAIVERS") or (add.get("onTeamId") or 0) not in (0, None): okk = bad(f"{add['name']} is no longer available ({add['status']}, team {add.get('onTeamId')})")
            if add and not add.get("proTeamId"): okk = bad(f"{add['name']} has no NBA team (unsigned) — no games")
            if acq >= limit: okk = bad(f"weekly add limit reached ({acq}/{limit})")
            cnow = sum(1 for e in ent if e["slot"] != 13 and e["pos"] == 5) - (1 if drop and drop["pos"] == 5 else 0) - (1 if irp and irp["pos"] == 5 else 0)
            if add and add.get("pos") == 5 and cnow + 1 > maxC: okk = bad(f"max C {maxC} would be exceeded")
        r["add"] = add and {k: add[k] for k in ("name", "status")}; r["drop"] = drop and drop["name"]; r["ir"] = irp and irp["name"]
        r["checks"].append("✓ checks passed" if okk else "✗ not executable")
        if not okk or MODE != "live": r["ok"] = okk; continue
        # ---- live: activation = drop first, then IR -> bench
        if it["kind"] == "activate":
            ok, resp = post({"isLeagueManager": False, "teamId": me["id"], "type": "FREEAGENT", "memberId": swid, "scoringPeriodId": sp, "executionType": "EXECUTE",
                             "items": [{"playerId": drop["id"], "type": "DROP", "fromTeamId": me["id"]}]})
            r["dropResponse"] = resp if not ok else {k: resp.get(k) for k in ("id", "status") if isinstance(resp, dict)}
            if not ok: bad("ESPN rejected the drop"); break
            time.sleep(2)
            ok, resp = post({"isLeagueManager": False, "teamId": me["id"], "type": "ROSTER", "memberId": swid, "scoringPeriodId": sp, "executionType": "EXECUTE",
                             "items": [{"playerId": irp["id"], "type": "LINEUP", "fromLineupSlotId": 13, "toLineupSlotId": 12}]})
            r["activateResponse"] = resp if not ok else {k: resp.get(k) for k in ("id", "status") if isinstance(resp, dict)}
            if not ok: bad("drop done, but ESPN rejected moving the player off IR — move him to the bench by hand"); break
            time.sleep(3)
            _, _, ent2, _, _, _, acq2, _ = state(); names2 = {norm(e["name"]): e for e in ent2}
            verified = norm(drop["name"]) not in names2 and names2.get(norm(irp["name"]), {}).get("slot") not in (13, None)
            r.update(ok=verified, verified=verified); it["status"] = "executed" if verified else "failed"; it["executedAt"] = res["at"]
            ent, byname, acq = ent2, names2, acq2
            if not verified: bad("ESPN shows a different roster after the activation"); break
            continue
        # ---- live: one item = IR move (if any) then the add/drop transaction
        if irp:
            ok, resp = post({"isLeagueManager": False, "teamId": me["id"], "type": "ROSTER", "memberId": swid, "scoringPeriodId": sp, "executionType": "EXECUTE",
                             "items": [{"playerId": irp["id"], "type": "LINEUP", "fromLineupSlotId": irp["slot"], "toLineupSlotId": 13}]})
            r["irResponse"] = resp if not ok else {k: resp.get(k) for k in ("id", "status") if isinstance(resp, dict)}
            if not ok: bad("ESPN rejected the IR move"); break
            time.sleep(2)
        if add:
            body = {"isLeagueManager": False, "teamId": me["id"], "type": "WAIVER" if add["status"] == "WAIVERS" else "FREEAGENT", "memberId": swid,
                    "scoringPeriodId": sp, "executionType": "EXECUTE", "items": [{"playerId": add["id"], "type": "ADD", "toTeamId": me["id"]}]}
            if add["status"] == "WAIVERS": body["bidAmount"] = 0
            if drop: body["items"].append({"playerId": drop["id"], "type": "DROP", "fromTeamId": me["id"]})
            ok, resp = post(body)
            r["response"] = resp if not ok else {k: resp.get(k) for k in ("id", "status", "type") if isinstance(resp, dict)}
            if irBad:   # record what ESPN did while an IR player was not OUT
                jdump(IRRULE, {"at": res["at"], "irNotOut": irBad, "addAccepted": ok, "espn": r["response"]})
            if not ok: bad("ESPN rejected the transaction"); break
        time.sleep(3)
        _, _, ent2, _, _, _, acq2, _ = state()
        names2 = {norm(e["name"]): e for e in ent2}
        pending = add and add["status"] == "WAIVERS"
        verified = (not add or pending or norm(add["name"]) in names2) and (not drop or pending or norm(drop["name"]) not in names2) and (not irp or names2.get(norm(irp["name"]), {}).get("slot") == 13)
        r.update(ok=verified, verified=verified, waiverPending=bool(pending), addsUsedAfter=acq2)
        it["status"] = "executed" if verified and not pending else ("claim-submitted" if pending else "failed"); it["executedAt"] = res["at"]
        ent, byname, acq = ent2, names2, acq2
        if not verified: bad("ESPN shows a different roster after the transaction"); break
    res["ok"] = all(x["ok"] for x in res["items"])
    jdump(OUT, res)
    if MODE == "live": jdump(PLAN, plan)
    print(json.dumps(res, ensure_ascii=False)[:3000])
    if not res["ok"]:
        if MODE == "live": F.die("one or more items failed — see g8/moves/last_run.json")
        note("warning", "some items are not executable — see g8/moves/last_run.json")


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception:
        import traceback
        F.die("crash: " + traceback.format_exc()[-900:])
