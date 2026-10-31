import os
"""Projection v2: early-season regression calibrated on 2021-2026 Basketball Reference game logs.
For each stat s and each early-sample bucket (games played in the first D days: 1,2,3,4+):
    rest-of-season per-game = b0 + b1 * prior + b2 * early per-game        (WLS, weights = rest-of-season games)
History: prior = previous season per-game (>=20 g), early = first D days of the season, target = remainder (>=20 g).
2027:    prior = ESPN 2027 projection, early = 2027 per-game to date (ESPN API), D = days elapsed since the 2026-10-20 opener.
"""
import csv, json, os, sys, datetime as dt
from collections import defaultdict
W = os.path.dirname(os.path.abspath(__file__)) + '/'
GL = os.environ.get('GAMELOGS', os.path.join(W, '..', 'data', '')+'history/gamelogs.csv')
D = int(os.environ.get('V2_DAYS', '6'))
ST = ['MP', 'FGM', 'FGA', 'TPM', 'FTM', 'FTA', 'REB', 'AST', 'STL', 'BLK', 'TO', 'PTS']
COL = {'MP': 'mp', 'FGM': 'fg', 'FGA': 'fga', 'TPM': 'fg3', 'FTM': 'ft', 'FTA': 'fta', 'REB': 'trb', 'AST': 'ast', 'STL': 'stl', 'BLK': 'blk', 'TO': 'tov', 'PTS': 'pts'}
logs = defaultdict(list); opener = {}
for r in csv.DictReader(open(GL, encoding='utf-8')):
    s = int(r['season']); d = r['date']; logs[(r['player'], s)].append(r)
    opener[s] = min(opener.get(s, d), d)
def avg(rows): n = len(rows); return ({k: sum(float(x[COL[k]] or 0) for x in rows) / n for k in ST}, n) if n else (None, 0)
bucket = lambda n: min(n, 4)
data = defaultdict(list)   # (stat, bucket) -> [(prior, early, y, w)]
data0 = defaultdict(list)  # stat -> [(prior, y, w)] (no early games)
for (pl, s), rows in logs.items():
    cut = (dt.date.fromisoformat(opener[s]) + dt.timedelta(days=D)).isoformat()
    early = [x for x in rows if x['date'] < cut]; rest = [x for x in rows if x['date'] >= cut]
    prev = logs.get((pl, s - 1), [])
    pa, pn = avg(prev); ra, rn = avg(rest); ea, en = avg(early)
    if pn < 20 or rn < 20: continue
    for k in ST:
        if en: data[(k, bucket(en))].append((pa[k], ea[k], ra[k], rn))
        data0[k].append((pa[k], ra[k], rn))
def wls(X, y, w):
    # normal equations, tiny ridge for stability
    p = len(X[0]); A = [[sum(w[i] * X[i][a] * X[i][b] for i in range(len(y))) + (1e-6 if a == b else 0) for b in range(p)] for a in range(p)]
    bvec = [sum(w[i] * X[i][a] * y[i] for i in range(len(y))) for a in range(p)]
    for c in range(p):  # gaussian elimination
        piv = max(range(c, p), key=lambda r: abs(A[r][c])); A[c], A[piv] = A[piv], A[c]; bvec[c], bvec[piv] = bvec[piv], bvec[c]
        for r in range(p):
            if r != c:
                f = A[r][c] / A[c][c]; A[r] = [A[r][j] - f * A[c][j] for j in range(p)]; bvec[r] -= f * bvec[c]
    beta = [bvec[i] / A[i][i] for i in range(p)]
    yh = [sum(beta[j] * X[i][j] for j in range(p)) for i in range(len(y))]; ym = sum(w[i] * y[i] for i in range(len(y))) / sum(w)
    ssr = sum(w[i] * (y[i] - yh[i]) ** 2 for i in range(len(y))); sst = sum(w[i] * (y[i] - ym) ** 2 for i in range(len(y)))
    return beta, 1 - ssr / sst if sst else 0
COEF = {}
for k in ST:
    for b in (1, 2, 3, 4):
        rows = data.get((k, b), [])
        if len(rows) >= 25:
            beta, r2 = wls([[1, r[0], r[1]] for r in rows], [r[2] for r in rows], [r[3] for r in rows]); COEF[(k, b)] = {'b0': beta[0], 'b1': beta[1], 'b2': beta[2], 'r2': r2, 'n': len(rows)}
    rows = data0[k]; beta, r2 = wls([[1, r[0]] for r in rows], [r[1] for r in rows], [r[2] for r in rows]); COEF[(k, 0)] = {'b0': beta[0], 'b1': beta[1], 'b2': 0, 'r2': r2, 'n': len(rows)}
for b in (2, 3, 4):   # fall back to the nearest smaller bucket if a bucket is thin
    for k in ST:
        if (k, b) not in COEF and (k, b - 1) in COEF: COEF[(k, b)] = COEF[(k, b - 1)]
# ---- apply to 2027
PJ = json.load(open(W + 'proj_1023.json'))
def norm(s): return s.lower().replace('.', '').replace("'", '').replace(' jr', '').replace(' iii', '').replace(' ii', '').strip()
ACT = {}
for r in csv.DictReader(open(W + 'actual_espn_live.csv', encoding='utf-8')):
    g = float(r['G'] or 0)
    if g <= 0: continue
    ACT[norm(r['Player'])] = (int(round(g)), {'MP': float(r['MP']), 'FGM': float(r['FG']), 'FGA': float(r['FGA']), 'TPM': float(r['3P']), 'FTM': float(r['FT']), 'FTA': float(r['FTA']),
                                             'REB': float(r['TRB']), 'AST': float(r['AST']), 'STL': float(r['STL']), 'BLK': float(r['BLK']), 'TO': float(r['TOV']), 'PTS': float(r['PTS'])})
out = json.loads(json.dumps(PJ)); used = 0
for p in out['players']:
    E = p.get('espn') or {}
    if not E: continue
    g, a = ACT.get(norm(p['name']), (0, None)); b = bucket(g) if g else 0
    fin = {}
    for k in ST:
        c = COEF.get((k, b)) or COEF[(k, 0)]
        prior = E.get(k, p['final'].get(k, 0)); early = a[k] if a else 0
        fin[k] = max(0.0, c['b0'] + c['b1'] * prior + c['b2'] * early)
    fin['FGM'] = min(fin['FGM'], fin['FGA']); fin['FTM'] = min(fin['FTM'], fin['FTA']); fin['TPM'] = min(fin['TPM'], fin['FGM'])
    p['v1final'] = p['final']; p['final'] = {**p['final'], **fin}; p['method'] = 'v2'; p['v2'] = {'games': g, 'bucket': b}; used += 1
o27 = dt.date(2026, 10, 20); out['summary'] = dict(out.get('summary', {}), V2={'days': D, 'cutLabel': (o27 + dt.timedelta(days=D - 1)).strftime('%m/%d'), 'openers': opener, 'coef': {f'{k}|{b}': v for (k, b), v in COEF.items()}, 'train': sum(len(v) for v in data.values()) // len(ST), 'players': len(logs)})
json.dump(out, open(W + 'proj_v2.json', 'w'))
print('player-seasons', len(logs), 'train rows per stat (early)', {b: len(data.get(('PTS', b), [])) for b in (1, 2, 3, 4)}, 'prior-only', len(data0['PTS']), 'applied', used)
for k in ['PTS', 'REB', 'AST', 'TPM', 'STL', 'BLK']:
    print(k, ' '.join(f"b{b}: {COEF[(k,b)]['b0']:.2f}+{COEF[(k,b)]['b1']:.2f}*E+{COEF[(k,b)]['b2']:.2f}*A r2={COEF[(k,b)]['r2']:.2f} n={COEF[(k,b)]['n']}" for b in (0, 1, 2, 3, 4) if (k, b) in COEF))
