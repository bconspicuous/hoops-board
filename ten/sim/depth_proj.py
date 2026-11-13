#!/usr/bin/env python3
"""Depth-aware 2026-27 projection (user setting proj_config.basis = "last15depth").

Per-game line = per-minute production over the last 15 days (regressed to the player's 2026-27 season rate)
              x projected minutes in the CURRENT team context.
Projected minutes / starter share: each team game of the last 15 days is weighted by how closely its rotation matches
today's (who of the current healthy core played, and whether players who are OUT now were playing then) and by recency.
So a teammate's return (e.g. Quickley back -> Shead back to the bench) or a new injury moves minutes immediately.

Inputs : ../data/gamelogs.csv (box scores), ../data/players_splits.csv (season per-game), ../data/rosters.json (O/DTD),
         ../data/injuries.json, user_plan.json returnOverrides, actual_espn_live.csv (season lines, written by espn_to_sim.py)
Outputs: actual_espn_live.csv (overwritten: depth lines; players without recent games keep their season line),
         actual_dd.json (DD per game), depth_report.json (role table for the dashboard / reports)
"""
import csv, json, math, os, re, unicodedata
from collections import defaultdict
from datetime import date

W = os.path.dirname(os.path.abspath(__file__)) + '/'
D = W + '../data/'
ST = ['FGM', 'FGA', '3PM', 'FTM', 'FTA', 'REB', 'AST', 'STL', 'BLK', 'TO', 'PTS']
COL = {'FGM': 'FG', 'FGA': 'FGA', '3PM': '3P', 'FTM': 'FT', 'FTA': 'FTA', 'REB': 'TRB', 'AST': 'AST', 'STL': 'STL', 'BLK': 'BLK', 'TO': 'TOV', 'PTS': 'PTS'}
K_MIN = 150.0      # minutes of prior weight (season per-minute rate) when regressing the last-15 rate
DECAY = 0.88       # recency weight per team game (most recent = 1)
SIM_POW = 12.0     # how strongly games with a different rotation are down-weighted (similarity is minutes-weighted)


def norm(s):
    s = unicodedata.normalize('NFKD', s or '').encode('ascii', 'ignore').decode().lower()
    s = re.sub(r"[.'`]", '', s); s = re.sub(r'\b(jr|sr|ii|iii|iv)\b', '', s)
    return ' '.join(re.sub(r'[^a-z0-9]+', ' ', s).split())


def f(x):
    try: return float(x)
    except (TypeError, ValueError): return 0.0


def main():
    if not os.path.exists(D + 'gamelogs.csv'):
        print('depth_proj: no gamelogs.csv - season lines kept'); return
    logs = list(csv.DictReader(open(D + 'gamelogs.csv', encoding='utf-8')))
    season = {}
    if os.path.exists(D + 'players_splits.csv'):
        for r in csv.DictReader(open(D + 'players_splits.csv', encoding='utf-8')):
            if r['split'] == 'season': season[norm(r['Player'])] = r
    ro = json.load(open(D + 'rosters.json'))
    out_now = {norm(n) for n in ro.get('status', {}).get('O', [])}
    try:
        for i in json.load(open(D + 'injuries.json')).get('injuries', []):
            if (i.get('fantasyStatus') or '').upper() == 'OUT' or (i.get('status') or '').lower() == 'out': out_now.add(norm(i.get('player')))
    except Exception: pass
    today = date.today().isoformat()
    for n, d in json.load(open(W + 'user_plan.json')).get('returnOverrides', {}).items():
        if d > today: out_now.add(norm(n))
    # team games (most recent first)
    by_game = defaultdict(list)
    for r in logs: by_game[(r['team'], r['date'], r['game'])].append(r)
    team_games = defaultdict(list)
    for (t, dt, g) in sorted(by_game, key=lambda x: x[1], reverse=True): team_games[t].append((dt, g))
    played = lambda r: f(r['MIN']) > 0 and r['dnp'] != '1'
    injured_dnp = lambda r: r['dnp'] == '1' and r['reason'] and 'COACH' not in r['reason'].upper()
    report, lines, dd = {}, {}, {}
    for t, games in team_games.items():
        rows = {g: {norm(r['player']): r for r in by_game[(t, dt, g)]} for dt, g in games}
        tot = defaultdict(float); name = {}
        for g in rows:
            for k, r in rows[g].items():
                name[k] = r['player']
                if played(r): tot[k] += f(r['MIN'])
        order = sorted(tot, key=lambda k: -tot[k])
        core = [k for k in order if k not in out_now][:8]
        gone = [k for k in order[:9] if k in out_now]          # rotation players who are out now
        sim = {}
        imp = {k: tot[k] for k in core + gone}; den = sum(imp.values()) or 1.0
        for i, (dt, g) in enumerate(games):
            R = rows[g]
            hit = sum(imp[k] for k in core if k in R and played(R[k])) + sum(imp[k] for k in gone if not (k in R and played(R[k])))
            sim[g] = (hit / den) ** SIM_POW * DECAY ** i
        for k in name:
            if k in out_now: continue
            ws = wm = wst = 0.0; agg = defaultdict(float); mins = 0.0; gp = 0
            for dt, g in games:
                r = rows[g].get(k)
                if r is None or injured_dnp(r): continue          # not with the team / injured that night
                w = sim[g]; m = f(r['MIN']) if played(r) else 0.0
                ws += w; wm += w * m; wst += w * (1 if r['starter'] == '1' and played(r) else 0)
                if played(r):   # production rates weighted the same way (role-specific usage)
                    gp += 1; mins += w * m
                    for s in ST: agg[s] += w * f(r[s])
            if ws <= 0 or gp == 0: continue
            pm = wm / ws
            sea = season.get(k); smin = f(sea['MIN']) if sea else 0
            line = {}
            for s in ST:
                r15 = agg[s] / max(mins, 1e-9)
                rs = (f(sea[s]) / smin) if sea and smin > 0 else r15
                line[s] = (mins * r15 + K_MIN * rs) / (mins + K_MIN) * pm
            line['FGM'] = min(line['FGM'], line['FGA']); line['FTM'] = min(line['FTM'], line['FTA'])
            sdd = f(sea['DD']) if sea else 0.0
            dd[k] = round(min(0.95, sdd * (pm / smin) ** 1.5) if smin > 0 else sdd, 4)
            lines[k] = {'G': gp, 'MP': round(pm, 2), **{s: round(v, 3) for s, v in line.items()}}
            m7 = [f(rows[g][k]['MIN']) for dt, g in games[:4] if k in rows[g] and played(rows[g][k])]
            raw = [f(rows[g][k]['MIN']) for dt, g in games if k in rows[g] and played(rows[g][k])]
            report[name[k]] = {'team': t, 'projMin': round(pm, 1), 'startShare': round(wst / ws, 2), 'min15': round(sum(raw) / max(1, len(raw)), 1), 'g15': gp,
                               'seasonMin': round(smin, 1), 'lastMin': m7[:4], 'role': 'starter' if wst / ws >= 0.5 else 'bench'}
    # rewrite actual_espn_live.csv: depth line where available, season line otherwise
    src = list(csv.DictReader(open(W + 'actual_espn_live.csv', encoding='utf-8')))
    fields = ['Player', 'Team', 'G', 'MP', 'FG', 'FGA', '3P', 'FT', 'FTA', 'TRB', 'AST', 'STL', 'BLK', 'TOV', 'PTS']
    seen, n_dep, dd_out = set(), 0, {}
    with open(W + 'actual_espn_live.csv', 'w', newline='', encoding='utf-8') as fo:
        w = csv.DictWriter(fo, fieldnames=fields); w.writeheader()
        for r in src:
            k = norm(r['Player']); seen.add(k); L = lines.get(k)
            if k in dd: dd_out[r['Player']] = dd[k]
            if L:
                n_dep += 1
                r = {'Player': r['Player'], 'Team': r['Team'], 'G': L['G'], 'MP': L['MP'], **{COL[s]: L[s] for s in ST}}
            w.writerow({c: r.get(c, '') for c in fields})
    json.dump(dd_out, open(W + 'actual_dd.json', 'w'), ensure_ascii=False)
    json.dump({'asOf': max((r['date'] for r in logs), default=''), 'days': len({r['date'] for r in logs}), 'players': report,
               'method': 'last-15-day per-minute rate (regressed to season, 150-min prior) x minutes weighted by rotation similarity to today and recency'},
              open(W + 'depth_report.json', 'w'), ensure_ascii=False)
    print(f'depth_proj: {n_dep} players on depth lines ({len(report)} with recent games), out now {len(out_now)}')


if __name__ == '__main__':
    main()
