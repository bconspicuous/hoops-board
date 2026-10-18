"""Validate a transcribed roster snapshot and stage it for the v2.2 build.
   usage: python3 apply_rosters.py new_rosters.json [docs_dir=docs_live]
   input : {"asOf": "...", "teams": {team: {"active": [...], "ir": [...]}}, "status": {name: "O"|"DTD"}}
   checks: team names, player names vs projection pool (fuzzy suggestions), duplicates across teams,
           active roster <= 13, centers <= 4, status keys on rosters. Writes docs_dir/rosters.json (+ meta.json copy)."""
import json, sys, os, difflib, shutil
src = json.load(open(sys.argv[1])); out = sys.argv[2] if len(sys.argv) > 2 else "docs_live"
ref = json.load(open("ref22.json")); F = ref["fields"]; P = {a[0]: dict(zip(F, a)) for a in ref["players"]}
names = list(P); errs, warns, seen = [], [], {}
for t in src["teams"]:
    if t not in ref["teams"]: errs.append(f"unknown team: {t}")
for t, r in src["teams"].items():
    act, ir = r.get("active", []), r.get("ir", [])
    for n in act + ir:
        if n not in P:
            sug = difflib.get_close_matches(n, names, n=3, cutoff=0.6)
            (warns if not sug else errs).append(f"{t}: '{n}' not in pool" + (f" -> did you mean {sug}?" if sug else " (no projection: needs model projection)"))
        if n in seen: errs.append(f"duplicate: {n} on {seen[n]} and {t}")
        seen[n] = t
    if len(act) > 13: errs.append(f"{t}: {len(act)} active (>13)")
    nc = sum(1 for n in act if n in P and P[n]["pos"] == "C")
    if nc > 4: warns.append(f"{t}: {nc} centers active (>4)")
for n in src.get("status", {}):
    if n not in seen: warns.append(f"status for player not on any roster: {n}")
print("ERRORS:", errs or "none"); print("WARNINGS:", warns or "none")
print({t: (len(r.get('active', [])), len(r.get('ir', []))) for t, r in src["teams"].items()})
if not errs:
    os.makedirs(out, exist_ok=True); json.dump(src, open(os.path.join(out, "rosters.json"), "w"), ensure_ascii=False, indent=1)
    meta = json.load(open("seed_meta.json")); meta["asOf"] = src["asOf"]; json.dump(meta, open(os.path.join(out, "meta.json"), "w"), ensure_ascii=False)
    print("staged ->", out)
