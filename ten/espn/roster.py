#!/usr/bin/env python3
"""Add / drop / IR-return moves for Garak Twindragons on ESPN, with a two-factor approval.

  MODE=plan     read-only. Validates one move and writes ten/espn/roster_plan.json with a plan hash:
                  ADD + DROP        free-agent pickup (or a waiver claim when the player is on waivers)
                  ADD only          only when an active roster spot is open
                  ACTIVATE + DROP   IR player back to the bench, a dropped player makes room (Kawhi-type returns)
                Checks: the add is a free agent / on waivers (not on another team), the drop is on our roster,
                season (70) and matchup (7) acquisition limits, the user's fixed top-10 core (never dropped unless
                ALLOW_CORE=1), and ESPN's waiver rules (24 h, daily processing).
  MODE=execute  needs PLAN_HASH plus APPROVE_ADD / APPROVE_DROP / APPROVE_ACTIVATE = the player names the owner typed
                when approving. Re-plans from live ESPN data; any mismatch (hash, names, availability, limits) stops
                without writing. A drop is never sent without its add / activation in the same run.

Env: ESPN_S2, ESPN_SWID (secrets, never printed), ADD, DROP, ACTIVATE (player names), ALLOW_CORE. Stdlib only.
"""
import hashlib, json, os, sys, unicodedata, urllib.request, urllib.error
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fetch_espn as F
import lineup as LU

HERE = os.path.dirname(os.path.abspath(__file__))
OUTF = os.path.join(HERE, "roster_plan.json")
READ = "https://lm-api-reads.fantasy.espn.com"


def norm(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    return " ".join(s.replace(".", "").replace("'", "").replace("-", " ").split())


def read_json(path_q, extra=None):
    h = LU.headers(); h.update(extra or {})
    with urllib.request.urlopen(urllib.request.Request(f"{READ}{F.PATH}{path_q}", headers=h), timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def league(spid=None):
    d = read_json("?view=mRoster&view=mTeam&view=mSettings&view=mStatus" + (f"&scoringPeriodId={spid}" if spid else ""))
    me = next((t for t in d.get("teams", []) if f"{t.get('location', '')} {t.get('nickname', '')}".strip() == F.MY_TEAM or t.get("name") == F.MY_TEAM), None)
    if not me:
        F.die("our team was not found in the league response")
    rows = [{"id": e["playerPoolEntry"]["player"]["id"], "name": e["playerPoolEntry"]["player"]["fullName"], "slot": e["lineupSlotId"],
             "inj": e["playerPoolEntry"]["player"].get("injuryStatus") or "ACTIVE"} for e in me["roster"]["entries"]]
    st = d.get("status", {})
    return d, me, rows, d.get("scoringPeriodId"), st.get("currentMatchupPeriod")


def find_available(name):
    flt = {"players": {"filterStatus": {"value": ["FREEAGENT", "WAIVERS"]}, "limit": 600, "sortPercOwned": {"sortPriority": 1, "sortAsc": False}}}
    d = read_json("?view=kona_player_info", {"X-Fantasy-Filter": json.dumps(flt)})
    for pe in d.get("players") or []:
        p = pe.get("player") or {}
        if norm(p.get("fullName")) == norm(name):
            return {"id": p["id"], "name": p["fullName"], "status": pe.get("status"), "pro": F.PRO.get(p.get("proTeamId"), "FA"), "inj": p.get("injuryStatus") or "ACTIVE"}
    return None


def build():
    add_n, drop_n, act_n = (os.environ.get(k, "").strip() for k in ("ADD", "DROP", "ACTIVATE"))
    d, me, rows, spid, mp = league()
    acq = d["settings"]["acquisitionSettings"]; cnt = me.get("transactionCounter") or {}
    slots = {int(k): v for k, v in d["settings"]["rosterSettings"]["lineupSlotCounts"].items() if v}
    active_cap = sum(v for k, v in slots.items() if k != 13)
    core = set(json.load(open(os.path.join(LU.SIM, "user_plan.json"))).get("core", []))
    by = {norm(r["name"]): r for r in rows}
    errs, warn, plan = [], [], {"spid": spid, "matchupPeriod": mp}
    drop = by.get(norm(drop_n)) if drop_n else None
    if drop_n and not drop:
        errs.append(f"방출 대상 {drop_n}이(가) 우리 로스터에 없음")
    if drop and drop["slot"] == 13 and not act_n:
        warn.append(f"{drop['name']}은(는) IR 선수 — IR 선수 방출")
    if drop and drop["name"] in core and os.environ.get("ALLOW_CORE") != "1":
        errs.append(f"{drop['name']}은(는) 상위 10명 고정(core) — 사용자 규칙상 방출 불가(사용자가 명시하면 ALLOW_CORE=1)")
    n_active = sum(1 for r in rows if r["slot"] != 13)
    if add_n:
        a = find_available(add_n)
        if not a:
            errs.append(f"영입 대상 {add_n}: FA·웨이버 명단에 없음(다른 팀 소속이거나 이름 불일치)")
        else:
            plan["add"] = a
            plan["type"] = "WAIVER" if a["status"] == "WAIVERS" else "FREEAGENT"
            if plan["type"] == "WAIVER":
                warn.append(f"{a['name']}은(는) 웨이버 상태 — 즉시 영입이 아니라 웨이버 신청(ESPN 처리 시각 {acq.get('waiverProcessHour')}시, 순번 우선)")
            if a["inj"] in LU.OUT_STATUS:
                warn.append(f"{a['name']} 현재 {a['inj']}")
        used, lim = cnt.get("acquisitions", 0), acq.get("acquisitionLimit", 70)
        mused, mlim = (cnt.get("matchupAcquisitionTotals") or {}).get(str(mp), 0), acq.get("matchupAcquisitionLimit", 7)
        plan["limits"] = {"season": f"{used}/{lim}", "matchup": f"{int(mused)}/{int(mlim)}"}
        if used >= lim: errs.append(f"시즌 영입 한도 소진({used}/{lim})")
        if mused >= mlim: errs.append(f"이번 매치업 영입 한도 소진({int(mused)}/{int(mlim)})")
        if not drop and n_active >= active_cap:
            errs.append(f"로스터가 가득 참(활성 {n_active}/{active_cap}) — 방출 선수를 함께 지정해야 함")
    if act_n:
        ir = by.get(norm(act_n))
        if not ir or ir["slot"] != 13:
            errs.append(f"IR 복귀 대상 {act_n}이(가) IR 칸에 없음")
        else:
            plan["activate"] = ir
            if ir["inj"] in LU.OUT_STATUS:
                warn.append(f"{ir['name']} ESPN 상태가 아직 {ir['inj']} — 복귀시키면 결장 선수가 활성 로스터를 차지")
            if not drop and n_active >= active_cap:
                errs.append("활성 로스터가 가득 참 — IR 복귀에는 방출 선수가 필요")
    if drop_n and not add_n and not act_n:
        errs.append("방출 단독 실행은 지원하지 않음(영입 또는 IR 복귀와 함께만)")
    if not (add_n or act_n):
        errs.append("ADD 또는 ACTIVATE 중 하나는 필요")
    if drop:
        plan["drop"] = drop
    if acq.get("waiverHours"):
        warn.append(f"방출 선수는 {acq['waiverHours']}시간 웨이버 — 그 사이 다른 팀이 데려갈 수 있어 되돌릴 수 없음") if drop else None
    key = json.dumps([spid, plan.get("type"), (plan.get("add") or {}).get("id"), (drop or {}).get("id"), (plan.get("activate") or {}).get("id")])
    plan["hash"] = hashlib.sha256(key.encode()).hexdigest()[:10]
    return d, me, plan, errs, [w for w in warn if w]


def post(body):
    url = f"{LU.WRITE_HOST}{F.PATH}/transactions/"
    try:
        req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=LU.headers(True), method="POST")
        with urllib.request.urlopen(req, timeout=30) as r:
            resp = json.loads(r.read().decode("utf-8") or "{}")
        return {"http": 200, "status": resp.get("status"), "type": resp.get("type"), "id": resp.get("id")}
    except urllib.error.HTTPError as e:
        return {"http": e.code, "message": e.read()[:400].decode("utf-8", "replace")}


def main():
    mode = os.environ.get("MODE", "plan")
    d, me, plan, errs, warn = build()
    now = datetime.now(timezone(timedelta(hours=9))).strftime("%Y-%m-%dT%H:%M+09:00")
    res = {"createdKST": now, "mode": mode, **{k: v for k, v in plan.items()}, "errors": errs, "warnings": warn,
           "status": "invalid" if errs else "planned"}
    if mode == "execute" and not errs:
        appr = {k: norm(os.environ.get(k, "")) for k in ("APPROVE_ADD", "APPROVE_DROP", "APPROVE_ACTIVATE")}
        need = {"APPROVE_ADD": norm((plan.get("add") or {}).get("name", "")), "APPROVE_DROP": norm((plan.get("drop") or {}).get("name", "")),
                "APPROVE_ACTIVATE": norm((plan.get("activate") or {}).get("name", ""))}
        if (os.environ.get("PLAN_HASH") or "").strip() != plan["hash"]:
            res["status"] = f"aborted: approved plan {os.environ.get('PLAN_HASH') or '-'} != current plan {plan['hash']} (re-approve)"
        elif appr != need:
            res["status"] = "aborted: approved player names do not match the plan"
        else:
            swid, tid, spid = os.environ["ESPN_SWID"].strip(), me["id"], plan["spid"]
            base = {"isLeagueManager": False, "teamId": tid, "memberId": swid, "scoringPeriodId": spid, "executionType": "EXECUTE"}
            out = []
            if plan.get("add"):
                items = [{"playerId": plan["add"]["id"], "type": "ADD", "toTeamId": tid}]
                if plan.get("drop"):
                    items.append({"playerId": plan["drop"]["id"], "type": "DROP", "fromTeamId": tid})
                body = {**base, "type": plan["type"], "items": items}
                if plan["type"] == "WAIVER":
                    body["bidAmount"] = 0
                out.append(post(body))
            else:   # IR return: drop first (frees the spot), then IR -> bench
                out.append(post({**base, "type": "FREEAGENT", "items": [{"playerId": plan["drop"]["id"], "type": "DROP", "fromTeamId": tid}]}) if plan.get("drop") else {"skipped": "no drop"})
                if out[-1].get("http") in (200, None):
                    out.append(post({**base, "type": "ROSTER", "items": [{"playerId": plan["activate"]["id"], "type": "LINEUP", "fromLineupSlotId": 13, "toLineupSlotId": 12}]}))
            res["espn"] = out
            _, me2, rows2, _, _ = league()
            ids = {r["id"]: r["slot"] for r in rows2}
            ok_now = (not plan.get("add") or plan["add"]["id"] in ids) and (not plan.get("drop") or plan["drop"]["id"] not in ids)
            if not ok_now and all(x.get("http") == 200 for x in out):   # roster locked for today: ESPN applies the move from the next scoring period
                _, _, rows3, _, _ = league(spid + 1)
                ids = {r["id"]: r["slot"] for r in rows3}; res["effective"] = f"next scoring period ({spid + 1})"
            chk = []
            if plan.get("add") and plan["type"] == "FREEAGENT": chk.append(("영입", plan["add"]["id"] in ids))
            if plan.get("drop"): chk.append(("방출", plan["drop"]["id"] not in ids))
            if plan.get("activate"): chk.append(("IR 복귀", ids.get(plan["activate"]["id"]) not in (None, 13)))
            res["verified"] = {k: v for k, v in chk}
            if plan.get("type") == "WAIVER":
                res["status"] = "waiver claim submitted" if all(x.get("http") == 200 for x in out) else "failed: " + json.dumps(out, ensure_ascii=False)[:300]
            else:
                res["status"] = "executed" if chk and all(v for _, v in chk) else "partial/failed: " + ", ".join(f"{k} {'완료' if v else '미반영'}" for k, v in chk)
    json.dump(res, open(OUTF, "w"), ensure_ascii=False, indent=1)
    a, dr, ac = plan.get("add") or {}, plan.get("drop") or {}, plan.get("activate") or {}
    lines = [f"## 로스터 이동 {res['status']} · plan {plan['hash']}",
             f"- 유형: {plan.get('type') or ('IR 복귀' if ac else '-')} · 영입 {a.get('name', '-')}({a.get('status', '')} {a.get('pro', '')}) · 방출 {dr.get('name', '-')} · IR 복귀 {ac.get('name', '-')}",
             f"- 한도: {plan.get('limits', {})}"] + [f"- 오류: {e}" for e in errs] + [f"- 주의: {w}" for w in warn]
    if res.get("espn"):
        lines.append(f"- ESPN 응답: {json.dumps(res['espn'], ensure_ascii=False)}")
    print("\n".join(lines))
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        open(os.environ["GITHUB_STEP_SUMMARY"], "a").write("\n".join(lines) + "\n")
    if errs or (mode == "execute" and res["status"] not in ("executed", "waiver claim submitted")):
        print(f"::warning title=roster::{res['status']} {'; '.join(errs)}"[:900])


if __name__ == "__main__":
    main()
