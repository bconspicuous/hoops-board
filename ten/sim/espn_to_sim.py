import os
"""Convert ESPN API sync output (hoops-board/ten/data) into simulation inputs."""
import json, csv, os, sys, unicodedata
W = os.path.dirname(os.path.abspath(__file__)) + '/'
D = os.path.join(W, '..', 'data', '')
old = json.load(open(W + 'rosters_1026b.json'))
pl = json.load(open(W + 'players10.json')); L = pl['players'] if isinstance(pl, dict) else pl
def norm(s): return ''.join(c for c in unicodedata.normalize('NFKD', s) if not unicodedata.combining(c)).lower().replace('.', '').replace("'", '').strip()
ALIAS = {'jimmy butler iii': 'jimmy butler', 'ronald holland ii': 'ron holland', 'g niang': 'georges niang', 'nicolas claxton': 'nic claxton'}
BYN = {norm(p['name']): p['name'] for p in L}
def m(n):
    k = norm(n); k = ALIAS.get(k, k)
    if k in BYN: return BYN[k]
    k2 = k.replace(' jr', '').replace(' iii', '').replace(' ii', '')
    for kk, v in BYN.items():
        if kk.replace(' jr', '').replace(' iii', '').replace(' ii', '') == k2: return v
    return None
ro = json.load(open(D + 'rosters.json')); sb = json.load(open(D + 'scoreboard.json')); meta = json.load(open(D + 'meta.json'))
oldt = {t['abbr']: t for t in old['teams']}; miss = []
teams = []
for t in ro['teams']:
    def mm(lst):
        out = []
        for n in lst:
            x = m(n)
            (out.append(x) if x else miss.append((t['abbr'], n)))
        return out
    teams.append({'name': t['name'], 'abbr': t['abbr'], 'mgr': oldt.get(t['abbr'], {}).get('mgr', ''), 'me': t['me'], 'players': mm(t['players']), 'ir': mm(t['ir'])})
st = {k: sorted({m(n) for n in v if m(n)}) for k, v in ro['status'].items()}
os_ = ['Jalen Williams']   # user: out for season (ESPN still lists DTD)
st['DTD'] = [n for n in st['DTD'] if n not in os_]
CATS = ['FG%', 'FT%', '3PM', 'REB', 'AST', 'STL', 'BLK', 'TO', 'DD', 'PTS', 'TW']
weeks = {}
for g in sb['matchups']: weeks.setdefault(g['period'], []).append(g)
w1 = weeks[1]
totals = {}; made = {}; rec = {}
for g in w1:
    for side in ('home', 'away'):
        s = g[side]; c = s['cats']; totals[s['team']] = [c.get(k, 0) for k in CATS]; made[s['team']] = [c.get('FGM'), c.get('FGA'), c.get('FTM'), c.get('FTA')]
        rec[s['team']] = f"{s['wins']}-{s['losses']}-{s['ties']}"
sched = [[[g['home']['team'], g['away']['team']] for g in weeks[p]] for p in sorted(weeks) if p <= 22]
cur = sb['currentMatchupPeriod']
out = {'asOf': meta['asOf'], 'source': 'ESPN API', 'teams': teams, 'status': {'O': st.get('O', []), 'DTD': st.get('DTD', []), 'OS': os_},
       'trade': old['trade'], 'reserveFA': old.get('reserveFA', []),
       'week1': {'asOf': meta['asOf'], 'note': 'Matchup 1 final (ESPN API)', 'remFrom': 6, 'pairs': sched[0], 'totals': totals, 'made': made, 'record': rec},
       'schedule': sched, 'currentPeriod': cur,
       'current': {'period': cur, 'pairs': sched[cur - 1] if cur - 1 < len(sched) else [], 'record': {g[s]['team']: f"{g[s]['wins']}-{g[s]['losses']}-{g[s]['ties']}" for g in weeks.get(cur, []) for s in ('home', 'away')},
                   'cats': {g[s]['team']: g[s]['cats'] for g in weeks.get(cur, []) for s in ('home', 'away')}}}
inj = json.load(open(D + 'injuries.json'))['injuries']
roster_names = {n for t in teams for n in t['players'] + t['ir']} | set(old.get('reserveFA', []))
OVR = {}   # 10/28: Kawhi now follows ESPN (knee inflammation, est. return 11/23, IR)
ret, info = {}, {}
for x in inj:
    n = m(x['player'] or '')
    if not n or n in os_: continue
    rd = (x.get('returnDate') or '')[:10]
    if n in OVR: rd, why = OVR[n]
    else: why = 'ESPN 예상 복귀일'
    if rd: ret[n] = rd
    info[n] = {'status': x.get('status'), 'returnDate': rd, 'espnReturn': (x.get('returnDate') or '')[:10], 'injury': ' '.join(v for v in [x.get('side'), x.get('injury'), x.get('detail')] if v), 'note': (x.get('short') or '')[:220], 'basis': why, 'updated': (x.get('date') or '')[:10]}
for n, (rd, why) in OVR.items():
    if n not in ret and n in roster_names: ret[n] = rd; info[n] = {'status': 'Out', 'returnDate': rd, 'espnReturn': '', 'injury': '', 'note': '', 'basis': why, 'updated': ''}
out['returns'] = ret; out['injuryInfo'] = {k: v for k, v in info.items() if k in roster_names}
import datetime as _dt
_now = _dt.datetime.fromisoformat(meta['asOf'])
out['current']['fromDate'] = ((_now - _dt.timedelta(hours=38)).date() + _dt.timedelta(days=1)).isoformat()   # first US game date not yet final
PLAN = json.load(open(W + 'user_plan.json'))
out.update(PLAN)
# pending trade (accepted, in 24h review): swap rosters for the season; current week split by date via teamWindows/curExtra
TRD = PLAN.get('pendingTrade')
if TRD:
    tA = next(t for t in out['teams'] if t['abbr'] == TRD['a']); tB = next(t for t in out['teams'] if t['abbr'] == TRD['b'])
    ga = [n for n in TRD['aGives'] if n in tA['players']]; gb = [n for n in TRD['bGives'] if n in tB['players']]
    eff = TRD['effective']; prev = (_dt.date.fromisoformat(eff) - _dt.timedelta(days=1)).isoformat()
    _exp = _now.date() > _dt.date.fromisoformat(eff) + _dt.timedelta(days=2)
    if ga and gb and _exp: TRD['status'] = 'expired (not executed by ESPN)'; ga = gb = []
    if ga and gb:   # not yet processed by ESPN
        tA['players'] = [n for n in tA['players'] if n not in ga] + gb; tB['players'] = [n for n in tB['players'] if n not in gb] + ga
        if out['current']['fromDate'] < eff:
            out['curExtra'] = {TRD['a']: ga, TRD['b']: gb}
            out['teamWindows'] = {TRD['a']: {**{n: {'to': prev} for n in ga}, **{n: {'from': eff} for n in gb}},
                                  TRD['b']: {**{n: {'to': prev} for n in gb}, **{n: {'from': eff} for n in ga}}}
        TRD['status'] = 'pending (applied in sim)'
    elif not TRD.get('status', '').startswith('expired'): TRD['status'] = 'processed by ESPN'
    print('trade', TRD['status'], ga, gb)
for _ab, _lst in PLAN.get('swaps', {}).items():   # planned add/drop: drop leaves the roster, add joins from its date
    _t = next(t for t in out['teams'] if t['abbr'] == _ab)
    for _s in _lst:
        if _s['add'] in _t['players'] or _s['drop'] not in _t['players']: continue
        if _now.date() > _dt.date.fromisoformat(_s['from']) + _dt.timedelta(days=2): continue   # planned move never made: ignore
        _t['players'] = [n for n in _t['players'] if n != _s['drop']] + [_s['add']]
        out.setdefault('windows', {})[_s['add']] = {'from': _s['from']}
    print('swaps', _ab, _lst)
print('returns', ret)
json.dump(out, open(W + 'rosters_espn.json', 'w'), ensure_ascii=False, indent=1)
rows = [r for r in csv.DictReader(open(D + 'players_2027.csv', encoding='utf-8')) if r['G'] not in ('', '0', '0.0')]
with open(W + 'actual_espn_live.csv', 'w', newline='', encoding='utf-8') as f:
    w = csv.DictWriter(f, fieldnames=['Player', 'Team', 'G', 'MP', 'FG', 'FGA', '3P', 'FT', 'FTA', 'TRB', 'AST', 'STL', 'BLK', 'TOV', 'PTS'])
    w.writeheader()
    for r in rows: w.writerow({k: r[k] for k in w.fieldnames})
print('teams', len(teams), 'sizes', [len(t['players']) for t in teams], 'missing', miss, 'actual rows', len(rows), 'weeks', len(sched), 'current', cur)
