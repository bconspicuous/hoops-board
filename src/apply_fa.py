"""Turn an ESPN 'Players > Add' capture transcription into data/fa.json (the dashboard's league/fa doc).
   input : incoming/fa_<date>.txt  — one player per line: Name[|WA:Mon|Tue...][|DTD|O]
   output: data/fa.json  {asOf, source, players:{name:{wa?: YYYY-MM-DD, st?: DTD|O}}, unprojected:[...]}
   usage : python3 apply_fa.py incoming/fa_2026-10-18.txt 2026-10-18T23:28+09:00
   WA day names resolve to the next such date on/after the capture date (the waiver clear / claim date)."""
import json, sys, datetime, difflib, os
src, asof = sys.argv[1], sys.argv[2]
H = os.path.dirname(os.path.abspath(__file__))
ref = json.load(open(os.path.join(H, "ref22.json"))); F = ref["fields"]; P = {r[0]: dict(zip(F, r)) for r in ref["players"]}
ros = json.load(open(os.path.join(H, "data/rosters.json")))
on = {n: t for t, v in ros["teams"].items() for n in v.get("active", []) + v.get("ir", [])}
d0 = datetime.date.fromisoformat(asof[:10]); DOW = {"Mon": 0, "Tue": 1, "Wed": 2, "Thu": 3, "Fri": 4, "Sat": 5, "Sun": 6}
out, unproj, errs = {}, [], []
for line in open(src, encoding="utf8"):
    line = line.strip()
    if not line: continue
    parts = line.split("|"); n = parts[0].strip(); rec = {}
    for x in parts[1:]:
        if x.startswith("WA:"): k = DOW[x[3:]]; rec["wa"] = (d0 + datetime.timedelta(days=(k - d0.weekday()) % 7)).isoformat()
        elif x in ("DTD", "O"): rec["st"] = x
        else: errs.append(f"{n}: unknown flag {x}")
    if n in on: errs.append(f"{n}: listed as FA but rostered by {on[n]}")
    if n not in P: unproj.append(n); continue
    if n in out: errs.append(f"{n}: duplicate")
    out[n] = rec
if errs: print("\n".join(errs)); sys.exit(1)
doc = {"asOf": asof, "source": "ESPN Players(Add) 화면 캡처", "players": out, "unprojected": unproj}
json.dump(doc, open(os.path.join(H, "data/fa.json"), "w", encoding="utf8"), ensure_ascii=False, indent=1)
print(f"fa.json: {len(out)} projected FAs ({sum('wa' in r for r in out.values())} on waivers, {sum('st' in r for r in out.values())} DTD/O); unprojected {len(unproj)}: {', '.join(unproj)}")
