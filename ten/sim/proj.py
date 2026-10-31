import os
# Projection model v3 (2026-10-23)
#  1) per-player WLS linear trend on Basketball-Reference per-game stats, seasons 2021..2026 (weights = games)
#  2) inverse-variance blend with ESPN 2027 projection (error SDs calibrated by back-testing the trend model on 2026)
#  3) 2026-27 actual per-game stats blended in with a week-based weight (weeks 1-3: 10%)
import csv, json, math, unicodedata, collections, statistics as st, sys
W = os.path.dirname(os.path.abspath(__file__)) + '/'
BRF = W + 'br_player_per_game.csv'
PL = json.load(open(W + 'players10.json'))['players']
R = json.load(open(W + os.environ.get('ROSTERS', 'rosters_1024.json')))
ROOK = json.load(open(W + 'ncaa_rookies.json')) if len(sys.argv) > 1 and sys.argv[1] == 'final' else {}
STATS = ['MP', 'FGM', 'FGA', 'TPM', 'FTM', 'FTA', 'REB', 'AST', 'STL', 'BLK', 'TO', 'PTS']
BRCOL = {'MP': 'mp_per_game', 'FGM': 'fg_per_game', 'FGA': 'fga_per_game', 'TPM': 'x3p_per_game', 'FTM': 'ft_per_game', 'FTA': 'fta_per_game',
         'REB': 'trb_per_game', 'AST': 'ast_per_game', 'STL': 'stl_per_game', 'BLK': 'blk_per_game', 'TO': 'tov_per_game', 'PTS': 'pts_per_game'}
FLOOR = {'MP': 10, 'FGM': 1.5, 'FGA': 3, 'TPM': 0.4, 'FTM': 0.5, 'FTA': 0.7, 'REB': 2, 'AST': 1, 'STL': 0.4, 'BLK': 0.3, 'TO': 0.6, 'PTS': 5}
YEARS = list(range(2021, 2027))
def norm(s):
    s = ''.join(c for c in unicodedata.normalize('NFKD', s) if not unicodedata.combining(c)).lower()
    for ch in ".'’`": s = s.replace(ch, '')
    s = s.replace('-', ' ')
    return ' '.join(s.split())
def strip_suffix(s): return ' '.join(w for w in s.split() if w not in ('jr', 'sr', 'ii', 'iii', 'iv'))
ALIAS = {'jimmy butler iii': 'jimmy butler', 'ronald holland ii': 'ron holland', 'g niang': 'georges niang'}
# ---------- BR history
seasons = collections.defaultdict(dict)   # player_id -> season -> row (multi-team total row wins)
names = collections.defaultdict(set)
for r in csv.DictReader(open(BRF, encoding='utf-8')):
    if r['lg'] != 'NBA' or not r['season'].isdigit(): continue
    y = int(r['season'])
    if y < 2016: continue
    pid = r['player_id']; names[norm(r['player'])].add(pid); names[strip_suffix(norm(r['player']))].add(pid)
    multi = r['team'].endswith('TM') or r['team'] == 'TOT'
    if y not in seasons[pid] or multi: seasons[pid][y] = r
def rowvals(r):
    v = {}
    for s, c in BRCOL.items():
        try: v[s] = float(r[c]) if r[c] not in ('', 'NA') else 0.0
        except ValueError: v[s] = 0.0
    v['G'] = float(r['g'] or 0); v['age'] = r['age']; v['team'] = r['team']
    return v
def match(name):
    n = norm(name); n = ALIAS.get(n, n)
    c = names.get(n) or names.get(strip_suffix(n)) or set()
    if not c: return None
    # prefer the id with the most recent season
    return max(c, key=lambda pid: max(seasons[pid]) if seasons[pid] else 0)
# ---------- WLS trend
def wls(pts, x0):
    # pts: [(x, y, w)], returns prediction at x0 and leverage
    if len(pts) == 1: return pts[0][1], 1.0
    sw = sum(w for _, _, w in pts); mx = sum(x * w for x, _, w in pts) / sw; my = sum(y * w for _, y, w in pts) / sw
    sxx = sum(w * (x - mx) ** 2 for x, _, w in pts)
    b = sum(w * (x - mx) * (y - my) for x, y, w in pts) / sxx if sxx > 0 else 0.0
    return max(0.0, my + b * (x0 - mx)), (1 / sw + (x0 - mx) ** 2 / sxx) * sw / len(pts) if sxx > 0 else 1.0
def history(pid, years):
    out = []
    for y in years:
        r = seasons[pid].get(y)
        if r:
            v = rowvals(r)
            if v['G'] >= 1: out.append((y, v))
    return out
def trend(hist, x0):
    pred = {}
    for s in STATS:
        pts = [(y, v[s], max(1.0, v['G'])) for y, v in hist]
        lo, hi = min(p[1] for p in pts), max(p[1] for p in pts)
        pred[s] = min(max(wls(pts, x0)[0], 0.75 * lo), 1.25 * hi)   # extrapolation guard: stay within 75%..125% of the observed range
    return pred
# ---------- back-test: predict 2026 from 2021..2025 (and naive = last season)
bt = collections.defaultdict(lambda: collections.defaultdict(list)); naive = collections.defaultdict(list)
for pid, ss in seasons.items():
    a = ss.get(2026)
    if not a: continue
    av = rowvals(a)
    if av['G'] < 30 or av['MP'] < 20: continue   # calibrate on fantasy-relevant rotation players
    h = history(pid, range(2021, 2026))
    if not h: continue
    n = len(h); n = 1 if n == 1 else (2 if n <= 3 else 4); pr = trend(h, 2026); last = h[-1][1]
    for s in STATS:
        lvl = max(av[s], FLOOR[s])
        bt[n][s].append(((pr[s] - av[s]) / lvl, av['G'])); naive[s].append(((last[s] - av[s]) / lvl, av['G']))
def rmse(lst): sw = sum(w for _, w in lst); return math.sqrt(sum(e * e * w for e, w in lst) / sw) if sw else None
RREG = {n: {s: rmse(bt[n][s]) for s in STATS} for n in sorted(bt)}
RNAIVE = {s: rmse(naive[s]) for s in STATS}
NBT = {n: len(bt[n]['PTS']) for n in sorted(bt)}
RESPN = {s: 0.8 * min(RNAIVE[s], min(RREG[n][s] for n in RREG)) for s in STATS}   # assumption: ESPN beats the best simple statistical forecast by 20%
def rreg(n, s): return RREG[1 if n == 1 else (2 if n <= 3 else 4)][s]   # calibration groups: 1 season / 2-3 / 4+
# ---------- ESPN projection (per game) from the draft dataset
def espn_vals(p):
    return {'MP': p.get('mpg', 0) or 0, 'FGM': p['FGM'], 'FGA': p['FGA'], 'TPM': p['TPM'], 'FTM': p['FTM'], 'FTA': p['FTA'],
            'REB': p['REB'], 'AST': p['AST'], 'STL': p['STL'], 'BLK': p['BLK'], 'TO': p['TO'], 'PTS': p['PTS']}
# ---------- 2026-27 actual stats
ACT = {}
for fn, src in [('actual_2027_a.csv', 'BR 10/21'), ('actual_espn_1024.csv', 'ESPN 10/22')] + ([('actual_espn_live.csv', os.environ.get('LIVE_SRC', 'ESPN API'))] if os.path.exists(W + 'actual_espn_live.csv') else []):   # ESPN (through Oct 22) overrides BR (through Oct 21)
  for r in csv.DictReader(open(W + fn, encoding='utf-8')):
    g = float(r['G']); ACT[norm(r['Player'])] = {'src': src, 'G': g, 'MP': float(r['MP']), 'FGM': float(r['FG']), 'FGA': float(r['FGA']), 'TPM': float(r['3P']),
        'FTM': float(r['FT']), 'FTA': float(r['FTA']), 'REB': float(r['TRB']), 'AST': float(r['AST']), 'STL': float(r['STL']), 'BLK': float(r['BLK']),
        'TO': float(r['TOV']), 'PTS': float(r['PTS'])}
WEEK = int(os.environ.get('WEEK', '1'))
WACT_TABLE = [(3, 0.10), (6, 0.30), (9, 0.50), (12, 0.60), (15, 0.70), (99, 0.80)]
WACT = next(w for k, w in WACT_TABLE if WEEK <= k)
# ---------- pool
rostered = {n for t in R['teams'] for n in t['players'] + t['ir']} | set(R['trade']['give']) | set(R['trade']['get'])
pool = [p for p in PL if (p.get('espnRank') and p['espnRank'] <= 300) or p['name'] in rostered]
# DD calibration: old model DD rate vs second-largest of PTS/REB/AST (ratio adjustment keeps each player's DD history)
def s2(v): return sorted([v['PTS'], v['REB'], v['AST']])[1]
cal = sorted((s2(espn_vals(p)), p['DDg']) for p in PL if p['gp'] > 0 and p.get('basis') == 'espn')
def fdd(x):   # local average DD rate around second-best stat x (kernel smoother)
    num = den = 0.0
    for a, d in cal:
        k = math.exp(-((a - x) / 0.8) ** 2); num += k * d; den += k
    return max(0.002, num / den)
out = []; unmatched = []
for p in pool:
    E = espn_vals(p); pid = match(p['name']); hist = history(pid, YEARS) if pid else []
    rec = {'name': p['name'], 'abbr': p['abbr'], 'pos': p['pos'], 'elig': p['elig'], 'gp': p['gp'], 'espnRank': p.get('espnRank'), 'TWg': p['TWg'],
           'brId': pid, 'n': len(hist), 'hist': [[y, round(v['G']), round(v['MP'], 1), round(v['PTS'], 1), round(v['REB'], 1), round(v['AST'], 1), round(v['STL'], 1), round(v['BLK'], 1), round(v['TPM'], 1)] for y, v in hist],
           'espn': {s: round(E[s], 3) for s in STATS}, 'basis': p.get('basis')}
    if hist:
        x0 = 2027; reg = trend(hist, x0); rec['reg'] = {s: round(reg[s], 3) for s in STATS}
        bl = {}; wts = {}
        for s in STATS:
            if s == 'MP' and not E['MP']: bl[s] = reg[s]; wts[s] = 1.0; continue
            lvl = max(E[s], reg[s], FLOOR[s]); sr = rreg(len(hist), s) * lvl; se = RESPN[s] * max(E[s], FLOOR[s])
            w = se * se / (se * se + sr * sr) if p.get('basis') == 'espn' else 0.85
            wts[s] = round(w, 3); bl[s] = w * reg[s] + (1 - w) * E[s]
        rec['wReg'] = wts; rec['method'] = 'reg+espn'
    else:
        nc = ROOK.get(p['name'])
        if nc:   # rookie: NCAA (translated to NBA rookie scale) 30% + ESPN 70% for the stats the NCAA line covers
            t = nc['nba']; bl = dict(E)
            for s in ['PTS', 'REB', 'AST', 'STL', 'BLK']:
                if s in t: bl[s] = 0.3 * t[s] + 0.7 * E[s]
            if 'FGp' in t and E['FGA']: bl['FGM'] = (0.3 * t['FGp'] + 0.7 * E['FGM'] / E['FGA']) * E['FGA']
            if 'FTp' in t and E['FTA']: bl['FTM'] = (0.3 * t['FTp'] + 0.7 * E['FTM'] / E['FTA']) * E['FTA']
            rec['ncaa'] = nc; rec['method'] = 'ncaa+espn'
        else:
            bl = dict(E); rec['method'] = 'espn'
        unmatched.append(p['name'])
    rec['blend'] = {s: round(bl[s], 3) for s in STATS}
    a = ACT.get(norm(p['name']))
    fin = dict(bl)
    if a and a['G'] >= 1:
        for s in STATS: fin[s] = (1 - WACT) * bl[s] + WACT * a[s]
        rec['actual'] = {k: a[k] for k in ['G'] + STATS}; rec['actual']['src'] = a['src']; rec['wAct'] = WACT
    rec['final'] = {s: round(fin[s], 3) for s in STATS}
    # DD: ratio-adjust the existing per-player DD rate by the change in second-best stat
    rec['DDg'] = round(min(0.95, p['DDg'] * fdd(s2(fin)) / fdd(s2(E))), 4) if p['gp'] > 0 else 0
    out.append(rec)
summary = {'RREG': RREG, 'RNAIVE': RNAIVE, 'RESPN': RESPN, 'NBT': NBT, 'WACT': WACT, 'WEEK': WEEK, 'WACT_TABLE': WACT_TABLE, 'pool': len(out), 'noHistory': unmatched}
json.dump({'players': out, 'summary': summary}, open(W + 'proj_1023.json', 'w'), ensure_ascii=False)
print('pool', len(out), 'matched', sum(1 for r in out if r['n']), 'no history', len(unmatched))
print('NBT', NBT)
for s in ['PTS', 'REB', 'AST', 'STL', 'BLK', 'TPM', 'FGM', 'FTA', 'TO']:
    print(s, 'reg', {n: round(RREG[n][s], 3) for n in RREG}, 'naive', round(RNAIVE[s], 3), 'espn', round(RESPN[s], 3))
print('no history:', unmatched)
