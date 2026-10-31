#!/usr/bin/env bash
# Full 10-team league pipeline: ESPN data (ten/data) -> projections v1/v2 -> season sims -> acquisition plans -> dashboard (ten/index.html) + out/summary.*
set -uo pipefail
cd "$(dirname "$0")"
python3 -I espn_to_sim.py | grep -E "trade|swaps|teams"
read CUR FROM ACQ <<<"$(python3 -I -c "
import json; r=json.load(open('rosters_espn.json')); g=json.load(open('../data/rosters.json'))
print(r['current']['period'], r['current']['fromDate'], next(t for t in g['teams'] if t['me'])['transactions']['acquisitions'])")"
DAYS=$(python3 -I -c "import datetime as d; print((d.date.fromisoformat('$FROM')-d.date(2026,10,20)).days)")
CORE_NAMES=$(python3 -I -c "import json; print('|'.join(json.load(open('user_plan.json')).get('core',[])))"); export CORE_NAMES
echo "period $CUR from $FROM days $DAYS acquisitions $ACQ"
ROSTERS=rosters_espn.json WEEK=$CUR LIVE_SRC='ESPN API' python3 -I proj.py final > /dev/null
V2_DAYS=$DAYS python3 -I proj_v2.py | tail -1
# planner input: GTD gets no virtual streamers (the planner chooses real adds)
python3 -I -c "
import json; r=json.load(open('rosters_espn.json'))
r['streamOverride']={'GTD':{str(w):0 for w in range(0,23)}}; json.dump(r,open('rosters_plan.json','w'),ensure_ascii=False)"
( PLAN_NOFA=1 ROSTERS=rosters_espn.json node analyze2.js > out/analyze_v1.log 2>&1 &
  PROJ=proj_v2.json OUTF=league2_out_v2.json PLAN_NOFA=1 ROSTERS=rosters_espn.json node analyze2.js > out/analyze_v2.log 2>&1 &
  export ROSTERS=rosters_plan.json BUDGET=$((70-ACQ)) T12=0.03 T3=0.12 LOOK=0 JOINT34=1
  MAXW=3 PLANOUT=stream_plan_rec.json node stream_plan.js > out/plan_rec.log 2>&1 &
  MAXW=2 PLANOUT=stream_plan_c2.json node stream_plan.js > out/plan_c2.log 2>&1 &
  CORE_NAMES= MAXW=3 PLANOUT=stream_plan_free.json node stream_plan.js > out/plan_free.log 2>&1 &
  ROSTERS=rosters_espn.json WKOUT=wk_now.json node wk2add.js > out/wk_now.log 2>&1 &
  wait )
grep -E "season|acquisitions" out/plan_rec.log
# pending trade still open -> re-evaluate it (otherwise the last evaluation stays)
python3 -I - <<'PY'
import json, subprocess, os
u = json.load(open('user_plan.json')); r = json.load(open('rosters_espn.json')); t = r.get('pendingTrade') or {}
if t and t.get('status', '').startswith('pending'):
    nt = json.load(open('rosters_espn.json')); A = next(x for x in nt['teams'] if x['abbr'] == t['a']); B = next(x for x in nt['teams'] if x['abbr'] == t['b'])
    A['players'] = [n for n in A['players'] if n not in t['bGives']] + t['aGives']; B['players'] = [n for n in B['players'] if n not in t['aGives']] + t['bGives']
    nt.pop('teamWindows', None); nt.pop('curExtra', None); json.dump(nt, open('rosters_espn_notrade.json', 'w'), ensure_ascii=False)
    for suf, proj in (('', 'proj_1023.json'), ('_v2', 'proj_v2.json')):
        env = dict(os.environ, GIVE='|'.join(t['aGives']), GET='|'.join(t['bGives']), TO=t['b'], ROSTERS='rosters_espn_notrade.json', TSOUT=f'opt_kat{suf}.json', PROJ=proj)
        subprocess.run(['node', 'tsim.js'], env=env, stdout=subprocess.DEVNULL, check=True)
        x = json.load(open(f'opt_kat{suf}.json')); x['key'] = 'kat'; x['label'] = ' + '.join(t['aGives']) + ' ↔ ' + ' + '.join(t['bGives']) + f" ({t['b']}) · 예정"; json.dump(x, open(f'opt_kat{suf}.json', 'w'))
    print('trade re-evaluated')
PY
# Kawhi return-date sensitivity while he is still out
rm -f ksens_out.jsonl
KRET=$(python3 -I -c "import json; print(json.load(open('rosters_espn.json'))['returns'].get('Kawhi Leonard',''))")
if [ -n "$KRET" ] && [[ "$KRET" > "$FROM" ]]; then
  for OFF in -7 0 7 21; do
    R=$(python3 -I -c "import datetime as d; print(d.date.fromisoformat('$KRET')+d.timedelta(days=$OFF))")
    python3 -I -c "
import json; r=json.load(open('rosters_plan.json')); r['returns']['Kawhi Leonard']='$R'; json.dump(r,open('rosters_ks.json','w'),ensure_ascii=False)"
    ROSTERS=rosters_ks.json PLANF=stream_plan_rec.json node ksens.js >> ksens_out.jsonl
  done
fi
SRC=league2_out.json DUMP=d1.json python3 -I build_league2.py > /dev/null
SRC=league2_out_v2.json SUF=_v2 WK3=wk3add_out_v2.json DUMP=d2.json python3 -I build_league2.py > /dev/null
python3 -I combine.py > /dev/null
cp league10.html out/league10.html
python3 -I -c "
pre='<!doctype html>\n<html lang=\"ko\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1,viewport-fit=cover\"><meta name=\"robots\" content=\"noindex\"><style>:root{color-scheme:light}body{margin:0}[hidden]{display:none!important}</style>'
open('../index.html','w').write(pre+open('league10.html').read())"
python3 -I summary.py
