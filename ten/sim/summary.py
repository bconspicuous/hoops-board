"""Build out/summary.json + out/summary.md (Korean, for the scheduled report) from the latest pipeline outputs."""
import json, os
W = os.path.dirname(os.path.abspath(__file__)) + '/'; D = os.path.join(W, '..', 'data', '')
L1 = json.load(open(W + 'league2_out.json')); L2 = json.load(open(W + 'league2_out_v2.json'))
RO = json.load(open(D + 'rosters.json')); META = json.load(open(D + 'meta.json'))
SP = {k: json.load(open(W + f'stream_plan_{k}.json')) for k in ('rec', 'c2', 'free')}
WK = json.load(open(W + 'wk_now.json'))
CATL = {'FG': 'FG%', 'FT': 'FT%', 'TPM': '3PM', 'REB': 'REB', 'AST': 'AST', 'STL': 'STL', 'BLK': 'BLK', 'TO': 'TO', 'DD': 'DD', 'PTS': 'PTS', 'TW': 'TW'}
rec = {t['abbr']: t['record'] for t in RO['teams']}
ME = next(i for i, t in enumerate(L1['teams']) if t['me'])
def week(L):
    m = next(m for m in L['week1'] if ME in (m['a'], m['b'])); a = m['a'] == ME
    win = m['pA'] if a else m['pB']; lose = m['pB'] if a else m['pA']
    cats = {c['c']: round(((c['pw'] + c['pt'] / 2) if a else (1 - c['pw'] - c['pt'] / 2)) * 100) for c in m['cats']}
    return {'opp': L['teams'][m['b'] if a else m['a']]['abbr'], 'oppName': L['teams'][m['b'] if a else m['a']]['name'], 'record': m['rec'][0 if a else 1], 'win': win, 'lose': lose, 'cats': cats}
w1, w2 = week(L1), week(L2)
teams = []
for i, t in enumerate(L1['teams']):
    s1, s2 = t['season'], L2['teams'][i]['season']; r = rec.get(t['abbr'], {})
    teams.append({'abbr': t['abbr'], 'name': t['name'], 'me': t['me'], 'rec': f"{r.get('wins', 0)}-{r.get('losses', 0)}-{r.get('ties', 0)}", 'pct': r.get('percentage', 0),
                  'ec': t['ec'], 'W': s1['W'], 'L': s1['L'], 'T': s1['T'], 'p4': s1['p4'], 'champ': s1['champ'], 'avgRank': s1['avgRank'], 'p4v2': s2['p4'], 'Wv2': s2['W']})
order = sorted(teams, key=lambda x: -x['W'])
for k, t in enumerate(order): t['projRank'] = k + 1
cur = sorted(teams, key=lambda x: -x['pct'])
for k, t in enumerate(cur): t['curRank'] = k + 1
me = next(t for t in teams if t['me'])
me['planW'] = SP['rec']['sum']['plan']['W']; me['planRank'] = 1 + sum(1 for t in teams if not t['me'] and t['W'] > me['planW'])
# this week: recommend the best current-week move only if it is worth an acquisition
best = next((x for x in (WK.get('doubles') or [])[:1] + (WK['singles'] or [])[:1] if x['e'] >= WK['base']['e'] - 0.01), None)
nowMove = best if best and WK['remDays'] >= 2 else None   # at least 2 moves a week
plan = SP['rec']; nxt = [x for x in plan['log'] if not x.get('now')][:2]
sm = {'asOf': META['asOf'], 'me': me, 'week': {'v1': w1, 'v2': w2, 'remDays': WK['remDays'], 'base': WK['base'], 'nowMove': nowMove, 'alts': WK['singles'][:3]},
      'plans': {k: {'p4': v['sum']['plan']['p4'], 'champ': v['sum']['plan']['champ'], 'used': v['sum']['used'], 'W': v['sum']['plan']['W'], 'L': v['sum']['plan']['L']} for k, v in SP.items()},
      'base': plan['sum']['base'], 'next': nxt, 'teams': order, 'acq': next(t for t in RO['teams'] if t['me'])['transactions']['acquisitions']}
json.dump(sm, open(W + 'out/summary.json', 'w'), ensure_ascii=False, indent=1)
pc = lambda v: f"{v * 100:.0f}%"
_PS = json.load(open(W + 'proj_1023.json'))['summary']
sm['projection'] = {'actualOnly': bool(_PS.get('actualOnly')), 'nActual': _PS.get('nActual'), 'noActual': _PS.get('noActual', [])}
json.dump(sm, open(W + 'out/summary.json', 'w'), ensure_ascii=False, indent=1)
_CF = json.load(open(W + 'proj_config.json')) if os.path.exists(W + 'proj_config.json') else {}
_PL = ("- 프로젝션: 2026-27 최근 15일 · 팀 뎁스 보정(분당 생산성 × 현재 로테이션 기준 예상 출전시간)" if _CF.get('basis') == 'last15depth' and _PS.get('actualOnly') else None) or (f"- 프로젝션: 2026-27 시즌 실제 경기당 성적만 사용({_PS.get('nActual')}명) · 올 시즌 기록 없는 {len(_PS.get('noActual', []))}명만 기존 모델" if _PS.get('actualOnly') else "- 프로젝션: v1 회귀+ESPN+주차 가중 / v2 시즌 초 회귀")
md = [f"# 10팀 리그 시뮬레이션 · {META['asOf'].replace('T', ' ')[:16]} KST", _PL, '',
      f"## 우리 팀 예상 순위: 권장 교체안 실행 시 {me['planRank']}위 · 일반 교체 가정 시 {me['projRank']}위 (현재 {me['curRank']}위, {me['rec']})",
      f"- 4강 {pc(me['p4'])}(v2 {pc(me['p4v2'])}) · 우승 {me['champ'] * 100:.1f}% · 권장 교체안 실행 시 4강 {pc(sm['plans']['rec']['p4'])}, 우승 {sm['plans']['rec']['champ'] * 100:.1f}%", '',
      f"## 이번 주({WK['week']}주차) vs {w1['oppName']} ({w1['opp']})",
      f"- 현재 {w1['record']} · 승리 확률 {pc(w1['win'])}(v2 {pc(w2['win'])}) · 남은 {WK['remDays']}일",
      '- 카테고리 승률: ' + ', '.join(f"{CATL[c]} {v}%" for c, v in w1['cats'].items()), '']
md.append('## 이번 주 교체 플랜')
if nowMove: md.append("- 권장(남은 경기 기준): " + ', '.join(f"{m['drop']} → {m['add']}({m['team']}, {m['g']}경기)" for m in nowMove['moves']) + f" · 승리 {pc(WK['base']['win'])} → {pc(nowMove['win'])}")
else: md.append(f"- 이번 주 남은 일정 {WK['remDays']}일 · 교체는 다음 주 플랜으로 이월")
for x in nxt:
    mv = ', '.join(f"{m['drop']} → {m['add']}" for m in x['moves']) or '유지'
    md.append(f"- {x['week']}주차({x['start'][5:].replace('-', '/')}~) vs {x['opp']}: {mv} · 승리 {pc(x['winBefore'])} → {pc(x['winAfter'])}" + (f" · IR 복귀로 {x['forced']} 방출" if x.get('forced') else ''))
LW = json.load(open(W + 'lineup_week.json')) if os.path.exists(W + 'lineup_week.json') else None
if LW:
    md += ['', f"## 추천 라인업 ({LW['week']}주차 vs {LW['opp']}, {'권장 교체 반영' if LW['rosterMode'] == 'plan' else '현재 로스터'})"]
    for x in LW['days']:
        if x['n'] > 10: md.append(f"- {x['date'][5:].replace('-', '/')}: {x['n']}명 출전 가능 → 벤치 {', '.join(b['name'] for b in x['bench'])}" + (f" (결장 {', '.join(x['out'])})" if x['out'] else ''))
    if not any(x['n'] > 10 for x in LW['days']): md.append('- 10명 초과일 없음 · 출전 가능 전원 선발')
    sm['lineup'] = LW
    json.dump(sm, open(W + 'out/summary.json', 'w'), ensure_ascii=False, indent=1)
md += ['', '## 예상 순위 · 팀별 현황', '| 예상 | 팀 | 현재 성적(순위) | 예상 카테고리 성적 | 4강 | 우승 |', '|---|---|---|---|---|---|']
for t in order: md.append(f"| {t['projRank']} | {'**' if t['me'] else ''}{t['name']} ({t['abbr']}){'**' if t['me'] else ''} | {t['rec']} ({t['curRank']}위) | {t['W']:.0f}-{t['L']:.0f}-{t['T']:.0f} | {pc(t['p4'])} | {t['champ'] * 100:.1f}% |")
open(W + 'out/summary.md', 'w').write('\n'.join(md) + '\n')
print('\n'.join(md))
