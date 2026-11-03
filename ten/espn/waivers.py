#!/usr/bin/env python3
"""Read-only waiver / transaction report for the 10-team league -> ten/espn/waivers.json.

  - our pending transactions (waiver claims we filed, incl. the paired drop)
  - league transactions of the last LOOKBACK days, all teams (adds, drops, claims; status incl. failed claims)
  - waiver order (team waiverRank) and players currently on waivers with their clear date and who dropped them
Makes no write requests and prints no secrets. Env: ESPN_S2, ESPN_SWID, LOOKBACK (days, default 7).
"""
import json, os, sys
from datetime import date, datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fetch_espn as F
import lineup as LU
import roster as RO

HERE = os.path.dirname(os.path.abspath(__file__))
KST = timezone(timedelta(hours=9))


def ts(ms):
    return datetime.fromtimestamp(ms / 1000, KST).strftime("%Y-%m-%d %H:%M KST") if ms else None


def main():
    look = int(os.environ.get("LOOKBACK", "7"))
    base = RO.read_json("?view=mTeam&view=mRoster&view=mSettings&view=mStatus&view=mPendingTransactions")
    spid = base.get("scoringPeriodId") or 1
    teams = {t["id"]: {"name": f"{t.get('location', '')} {t.get('nickname', '')}".strip() or t.get("name"), "abbr": t.get("abbrev"),
                       "waiverRank": t.get("waiverRank"), "acq": (t.get("transactionCounter") or {}).get("acquisitions")} for t in base.get("teams", [])}
    me = next(i for i, t in teams.items() if t["name"] == F.MY_TEAM)
    names = {}
    for t in base.get("teams", []):
        for e in (t.get("roster") or {}).get("entries", []):
            p = e["playerPoolEntry"]["player"]; names[p["id"]] = p["fullName"]
    tx = {}
    for x in base.get("transactions") or base.get("pendingTransactions") or []:
        tx[x.get("id")] = x
    for k in range(look + 1):
        try:
            d = RO.read_json(f"?view=mTransactions2&scoringPeriodId={max(1, spid - k)}")
        except Exception as e:
            print(f"::warning::transactions period {spid - k}: {e}"); continue
        for x in d.get("transactions") or []:
            tx.setdefault(x.get("id"), x)
    # players on waivers (clear date)
    flt = {"players": {"filterStatus": {"value": ["WAIVERS"]}, "limit": 100}}
    wv = RO.read_json("?view=kona_player_info", {"X-Fantasy-Filter": json.dumps(flt)})
    on_waivers = []
    for pe in wv.get("players") or []:
        p = pe.get("player") or {}; names[p.get("id")] = p.get("fullName")
        on_waivers.append({"id": p.get("id"), "name": p.get("fullName"), "pro": F.PRO.get(p.get("proTeamId"), "FA"),
                           "waiverClears": ts(pe.get("waiverProcessDate")), "inj": p.get("injuryStatus")})
    # resolve unknown player ids
    unknown = sorted({it.get("playerId") for x in tx.values() for it in x.get("items") or [] if it.get("playerId") not in names})
    if unknown:
        flt = {"players": {"filterIds": {"value": unknown[:200]}, "limit": 200}}
        for pe in RO.read_json("?view=kona_player_info", {"X-Fantasy-Filter": json.dumps(flt)}).get("players") or []:
            p = pe.get("player") or {}; names[p.get("id")] = p.get("fullName")
    tn = lambda i: (teams.get(i) or {}).get("abbr") or ("FA" if i in (0, -1, None) else str(i))
    rows = []
    for x in tx.values():
        items = [{"type": it.get("type"), "player": names.get(it.get("playerId"), str(it.get("playerId"))), "from": tn(it.get("fromTeamId")), "to": tn(it.get("toTeamId"))}
                 for it in x.get("items") or [] if it.get("type") in ("ADD", "DROP", "WAIVER")]
        if not items:
            continue
        rows.append({"id": x.get("id"), "team": tn(x.get("teamId")), "mine": x.get("teamId") == me, "type": x.get("type"), "status": x.get("status"),
                     "proposed": ts(x.get("proposedDate")), "processed": ts(x.get("processDate")), "items": items, "bid": x.get("bidAmount")})
    rows.sort(key=lambda r: r["proposed"] or "", reverse=True)
    last_drop = {}
    for r in sorted(rows, key=lambda r: r["proposed"] or ""):
        for it in r["items"]:
            if it["type"] == "DROP" and r["status"] == "EXECUTED":
                last_drop[it["player"]] = {"by": r["team"], "at": r["processed"] or r["proposed"]}
    for w in on_waivers:
        w["droppedBy"] = last_drop.get(w["name"])
    acq = base["settings"]["acquisitionSettings"]
    out = {"asOf": datetime.now(KST).strftime("%Y-%m-%dT%H:%M+09:00"), "scoringPeriodId": spid,
           "rules": {k: acq.get(k) for k in ("acquisitionType", "waiverHours", "waiverProcessDays", "waiverProcessHour", "waiverOrderReset", "isUsingAcquisitionBudget")},
           "waiverOrder": sorted([{"team": t["abbr"], "name": t["name"], "rank": t["waiverRank"], "acq": t["acq"]} for t in teams.values()], key=lambda t: t["rank"] or 99),
           "myPending": [r for r in rows if r["mine"] and (r["status"] or "").startswith("PENDING")],
           "transactions": rows[:120], "onWaivers": on_waivers,
           "responseKeys": sorted(base.keys())}
    json.dump(out, open(os.path.join(HERE, "waivers.json"), "w"), ensure_ascii=False, indent=1)
    lines = [f"## 웨이버 · {out['asOf']}", f"- 우리 대기 중 신청: " + ("; ".join(f"{' / '.join(i['type'] + ' ' + i['player'] for i in r['items'])} ({r['status']}, {r['proposed']})" for r in out["myPending"]) or "없음"),
             "- 웨이버 순번: " + ", ".join(f"{w['rank']}.{w['team']}" for w in out["waiverOrder"]),
             f"- 최근 {look}일 거래 {len(rows)}건, 웨이버 선수 {len(on_waivers)}명"]
    print("\n".join(lines))
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        open(os.environ["GITHUB_STEP_SUMMARY"], "a").write("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
