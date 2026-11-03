#!/usr/bin/env python3
"""Daily lineup for Garak Twindragons on ESPN, with an approval step.

  MODE=plan     read-only: read our ESPN roster for the target US date, build the best legal lineup
                (players with a game first, matchup-leverage priority from ten/sim/lineup_week.json),
                write ten/espn/lineup_plan.json with the moves and a plan hash. No write requests.
  MODE=execute  needs PLAN_HASH = the hash the owner approved. Rebuilds the plan from live ESPN data;
                if the hash differs (roster/injuries/slots changed) it stops without writing.
                Otherwise submits the lineup moves (lineup slots only, never adds/drops/trades),
                re-reads the roster and records the result in lineup_plan.json.

Env: ESPN_S2, ESPN_SWID (GitHub secrets, never printed), TARGET_DATE (YYYY-MM-DD, US date; default = today US/Eastern).
Stdlib only.
"""
import hashlib, json, os, sys, urllib.request, urllib.error
from datetime import date, datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fetch_espn as F

HERE = os.path.dirname(os.path.abspath(__file__))
SIM = os.path.join(HERE, "..", "sim")
OUTF = os.path.join(HERE, "lineup_plan.json")
DAY1 = date(2026, 10, 20)                       # scoringPeriodId 1 = opening night
WRITE_HOST = "https://lm-api-writes.fantasy.espn.com"
SCHED_CODE = {"NOP": "NOR", "PHX": "PHO"}       # ESPN pro abbreviations -> schedule file codes
SLOTNAME = {0: "PG", 1: "SG", 2: "SF", 3: "PF", 4: "C", 5: "G", 6: "F", 11: "UTIL", 12: "BE", 13: "IR"}
OUT_STATUS = {"OUT", "INJURY_RESERVE", "SUSPENSION"}
AVAIL = {"DAY_TO_DAY": 0.75, "QUESTIONABLE": 0.75, "DOUBTFUL": 0.3}


def et_now():
    # US/Eastern without tzdata: EDT (UTC-4) until the first Sunday of November 2am, EST (UTC-5) after
    u = datetime.now(timezone.utc)
    nov1 = date(u.year, 11, 1); first_sun = nov1 + timedelta(days=(6 - nov1.weekday()) % 7)
    dst_end = datetime(first_sun.year, first_sun.month, first_sun.day, 6, tzinfo=timezone.utc)
    return u - timedelta(hours=5 if u >= dst_end or u.month < 3 else 4)


def headers(json_body=False):
    s2, swid = os.environ.get("ESPN_S2"), os.environ.get("ESPN_SWID")
    if not (s2 and swid):
        F.die("ESPN_S2 / ESPN_SWID secrets are missing")
    h = {"User-Agent": "Mozilla/5.0 (hoops-board ten lineup)", "Accept": "application/json", "Cookie": f"espn_s2={s2}; SWID={swid}",
         "X-Fantasy-Source": "kona", "X-Fantasy-Platform": "kona-PROD-web"}
    if json_body:
        h["Content-Type"] = "application/json"
    return h


def read_team(spid):
    url = f"https://lm-api-reads.fantasy.espn.com{F.PATH}?view=mRoster&view=mTeam&view=mSettings&scoringPeriodId={spid}"
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers()), timeout=30) as r:
        d = json.loads(r.read().decode("utf-8"))
    me = next((t for t in d.get("teams", []) if f"{t.get('location', '')} {t.get('nickname', '')}".strip() == F.MY_TEAM or t.get("name") == F.MY_TEAM), None)
    if not me:
        F.die("our team was not found in the league response")
    counts = {int(k): v for k, v in d["settings"]["rosterSettings"]["lineupSlotCounts"].items() if v}
    rows = []
    for e in me["roster"]["entries"]:
        p = e["playerPoolEntry"]["player"]
        rows.append({"id": p["id"], "name": p["fullName"], "slot": e["lineupSlotId"], "elig": [s for s in p.get("eligibleSlots", []) if s in counts],
                     "pro": F.PRO.get(p.get("proTeamId"), "FA"), "inj": p.get("injuryStatus") or "ACTIVE"})
    return me["id"], counts, rows


def games_on(day):
    S = json.load(open(os.path.join(SIM, "nba_sched.json")))
    for w, st in enumerate(S["starts"]):
        d0 = date.fromisoformat(st)
        if w < len(S["sched"]) and 0 <= (day - d0).days < len(S["sched"][w]):
            return set(S["sched"][w][(day - d0).days])
    return None


def build(day, counts, rows):
    plan = json.load(open(os.path.join(SIM, "user_plan.json")))
    over = plan.get("returnOverrides", {})
    lw = os.path.join(SIM, "lineup_week.json")
    pri = {}
    if os.path.exists(lw):
        L = json.load(open(lw))
        for k, r in enumerate(L.get("rankCur") or L.get("rank") or []):
            pri[r["name"]] = r["score"]
    play = games_on(day)
    if play is None:
        F.die(f"no NBA schedule for {day} in ten/sim/nba_sched.json")
    start_slots = [s for s in sorted(counts) if s not in (12, 13) for _ in range(counts[s])]
    info = []
    for r in rows:
        if r["slot"] == 13:
            info.append({**r, "why": "IR"}); continue
        has_game = SCHED_CODE.get(r["pro"], r["pro"]) in play
        out = r["inj"] in OUT_STATUS or (r["name"] in over and over[r["name"]] > day.isoformat())
        a = 0.0 if (not has_game or out) else AVAIL.get(r["inj"], 1.0)
        base = pri.get(r["name"], min(pri.values()) - 0.01 if pri else 0.0)
        info.append({**r, "game": has_game, "out": out, "a": a, "p": a * max(base, 1e-3)})   # expected contribution = availability x matchup-leverage score
    act = [x for x in info if x.get("why") != "IR"]
    if len(act) > len(start_slots) + counts.get(12, 0):
        F.die("more active players than lineup + bench slots")
    # 1) starters: greedy by priority on the slot matroid (augmenting paths), playing players first
    owner = [None] * len(start_slots)

    def aug(x, seen):
        for k, s in enumerate(start_slots):
            if s in x["elig"] and k not in seen:
                seen.add(k)
                if owner[k] is None or aug(owner[k], seen):
                    owner[k] = x; return True
        return False

    for x in sorted(act, key=lambda x: -x["p"]):
        snap = owner[:]
        if x["a"] > 0 and not aug(x, set()):
            owner[:] = snap
    starters = [x for x in owner if x]
    # fill still-empty start slots with idle players (no effect on stats, keeps the lineup legal and moves few players)
    for x in sorted([x for x in act if x not in starters], key=lambda x: (x["slot"] == 12, -x["p"])):
        if None not in owner:
            break
        snap = owner[:]
        if not aug(x, set()):
            owner[:] = snap
    starters = [x for x in owner if x]
    # 2) re-seat starters preferring their current slot (fewest moves)
    owner = [None] * len(start_slots)
    for x in starters:
        for k, s in enumerate(start_slots):
            if s == x["slot"] and owner[k] is None:
                owner[k] = x; break
    for x in starters:
        if x not in owner and not aug(x, set()):
            F.die(f"could not seat {x['name']}")
    want = {x["id"]: start_slots[k] for k, x in enumerate(owner) if x}
    for x in act:
        want.setdefault(x["id"], 12)
    moves = [{"playerId": x["id"], "name": x["name"], "from": x["slot"], "to": want[x["id"]]} for x in act if want[x["id"]] != x["slot"]]
    lineup = [{"slot": SLOTNAME[want[x["id"]]], "name": x["name"], "pro": x["pro"], "game": x["game"], "inj": x["inj"], "out": x["out"]}
              for x in sorted(act, key=lambda x: (want[x["id"]] == 12, start_slots.index(want[x["id"]]) if want[x["id"]] in start_slots else 99))]
    return moves, lineup, [x["name"] for x in info if x.get("why") == "IR"]


def plan_hash(day, spid, moves):
    key = json.dumps([day.isoformat(), spid, sorted((m["playerId"], m["from"], m["to"]) for m in moves)])
    return hashlib.sha256(key.encode()).hexdigest()[:10]


def main():
    mode = os.environ.get("MODE", "plan")
    day = date.fromisoformat(os.environ["TARGET_DATE"]) if os.environ.get("TARGET_DATE") else et_now().date()
    spid = (day - DAY1).days + 1
    team_id, counts, rows = read_team(spid)
    moves, lineup, ir = build(day, counts, rows)
    h = plan_hash(day, spid, moves)
    now = datetime.now(timezone(timedelta(hours=9))).strftime("%Y-%m-%dT%H:%M+09:00")
    res = {"date": day.isoformat(), "scoringPeriodId": spid, "hash": h, "createdKST": now, "mode": mode,
           "moves": [{**m, "fromSlot": SLOTNAME.get(m["from"]), "toSlot": SLOTNAME.get(m["to"])} for m in moves],
           "lineup": lineup, "ir": ir, "playing": sum(1 for x in lineup if x["game"] and not x["out"]), "status": "planned"}
    if mode == "execute":
        want = (os.environ.get("PLAN_HASH") or "").strip()
        if not want or want != h:
            res["status"] = f"aborted: approved plan {want or '-'} != current plan {h} (roster, injuries or slots changed; re-approve)"
        elif not moves:
            res["status"] = "nothing to do"
        else:
            swid = os.environ["ESPN_SWID"].strip()
            body = {"isLeagueManager": False, "teamId": team_id, "type": "ROSTER", "memberId": swid, "scoringPeriodId": spid, "executionType": "EXECUTE",
                    "items": [{"playerId": m["playerId"], "type": "LINEUP", "fromLineupSlotId": m["from"], "toLineupSlotId": m["to"]} for m in moves]}
            url = f"{WRITE_HOST}{F.PATH}/transactions/"
            try:
                req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=headers(True), method="POST")
                with urllib.request.urlopen(req, timeout=30) as r:
                    resp = json.loads(r.read().decode("utf-8") or "{}")
                res["espn"] = {"http": 200, "status": resp.get("status"), "type": resp.get("type"), "id": resp.get("id")}
            except urllib.error.HTTPError as e:
                msg = e.read()[:400].decode("utf-8", "replace")
                res["espn"] = {"http": e.code, "message": msg}
            _, _, rows2 = read_team(spid)
            now_slot = {r["id"]: r["slot"] for r in rows2}
            ok = [m["name"] for m in moves if now_slot.get(m["playerId"]) == m["to"]]
            res["applied"] = ok
            res["status"] = "executed" if len(ok) == len(moves) else f"partial/failed: {len(ok)}/{len(moves)} moves applied"
    json.dump(res, open(OUTF, "w"), ensure_ascii=False, indent=1)
    lines = [f"## 라인업 {res['status']} · {res['date']} (scoringPeriod {spid}) · plan {h}",
             "| 슬롯 | 선수 | NBA | 경기 | 상태 |", "|---|---|---|---|---|"]
    lines += [f"| {x['slot']} | {x['name']} | {x['pro']} | {'O' if x['game'] else '-'} | {'결장' if x['out'] else x['inj']} |" for x in lineup]
    lines += ["", "변경: " + (", ".join(f"{m['name']} {SLOTNAME.get(m['from'])}→{SLOTNAME.get(m['to'])}" for m in moves) or "없음")]
    if res.get("espn"):
        lines.append(f"ESPN 응답: {json.dumps(res['espn'], ensure_ascii=False)}")
    print("\n".join(lines))
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        open(os.environ["GITHUB_STEP_SUMMARY"], "a").write("\n".join(lines) + "\n")
    if mode == "execute" and res["status"] not in ("executed", "nothing to do"):
        print(f"::warning title=lineup::{res['status']}")


if __name__ == "__main__":
    main()
