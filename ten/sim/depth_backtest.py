#!/usr/bin/env python3
"""Back-test of the depth projection (depth_proj.compute) against actual NBA box scores -> depth_calib.json + backtest_report.json

For every game day T (from the 8th day of the season): project each player's line with only the box scores of the
15 days before T (as the live pipeline would have that morning), then compare with what he actually did on T.
Players who were with the team and not injured count even when the coach did not play them (0 minutes) - that is a
real fantasy miss. Compared with two naive baselines (season-to-date per game, raw last-15 per game).
Fits: rotation-weighting parameters (K_MIN, DECAY, SIM_POW), a minutes shrink toward the raw recent average, and
per-stat multipliers by role (starter / bench), 75% of the measured mean bias, capped at +/-15%.
"""
import csv, json, os, itertools
from collections import defaultdict
from datetime import date, timedelta
import sys; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import depth_proj as DP

W = DP.W; ST = DP.ST; f = DP.f; norm = DP.norm
SD = {'FGM': 2.3, 'FGA': 4.5, '3PM': 1.3, 'FTM': 1.8, 'FTA': 2.1, 'REB': 2.8, 'AST': 2.0, 'STL': 0.9, 'BLK': 0.8, 'TO': 1.2, 'PTS': 6.0}   # typical per-game spread, to weigh errors


def season_prior(hist):
    agg = defaultdict(lambda: defaultdict(float))
    for r in hist:
        if f(r['MIN']) <= 0 or r['dnp'] == '1': continue
        a = agg[norm(r['player'])]; a['GP'] += 1; a['MIN'] += f(r['MIN'])
        for s in ST: a[s] += f(r[s])
        dd = sum(1 for s in ('PTS', 'REB', 'AST', 'STL', 'BLK') if f(r[s]) >= 10); a['DD'] += 1 if dd >= 2 else 0
    return {k: {**{s: a[s] / a['GP'] for s in ST + ['MIN', 'DD']}, 'GP': a['GP']} for k, a in agg.items()}


def run(logs, days, P, shrink=0.0, collect=False):
    err = defaultdict(float); n = 0; rows_out = []
    sums = defaultdict(lambda: defaultdict(float))
    for T in days:
        hist = [r for r in logs if r['date'] < T]
        cut = (date.fromisoformat(T) - timedelta(days=15)).isoformat()
        win = [r for r in hist if r['date'] >= cut]
        today = [r for r in logs if r['date'] == T]
        out = {norm(r['player']) for r in today if r['dnp'] == '1' and r['reason'] and 'COACH' not in r['reason'].upper()}
        prior = season_prior(hist)
        lines, dd, rep = DP.compute(win, prior, out, **P)
        nm = {norm(k): v for k, v in rep.items()}
        for r in today:
            k = norm(r['player'])
            if k in out or k not in lines: continue
            L = lines[k]; R = nm.get(k, {}); pm0 = L['MP']
            pm = (1 - shrink) * pm0 + shrink * R.get('min15', pm0); sc = pm / pm0 if pm0 > 0 else 1
            act = {s: (f(r[s]) if f(r['MIN']) > 0 else 0.0) for s in ST}; amin = f(r['MIN'])
            role = R.get('role', 'bench')
            for s in ST:
                p = L[s] * sc
                err[s] += abs(act[s] - p) / SD[s]
                sums[role][s + '_p'] += p; sums[role][s + '_a'] += act[s]
            sums[role]['MIN_p'] += pm; sums[role]['MIN_a'] += amin; sums[role]['n'] += 1
            err['MIN'] += abs(amin - pm) / 6.0; n += 1
            if collect:
                sea = prior.get(k)
                raw = [x for x in win if norm(x['player']) == k and f(x['MIN']) > 0]
                base = {'season': {s: sea[s] for s in ST} if sea else None,
                        'last15': {s: sum(f(x[s]) for x in raw) / len(raw) for s in ST} if raw else None}
                rows_out.append((role, act, {s: L[s] * sc for s in ST}, base))
    score = sum(err[s] for s in ST) / max(1, n)
    return score, n, sums, err, rows_out


def main():
    logs = [r for r in csv.DictReader(open(DP.D + 'gamelogs.csv', encoding='utf-8')) if r['date'] >= '2026-10-20']
    dates = sorted({r['date'] for r in logs})
    days = [d for d in dates if d >= (date(2026, 10, 20) + timedelta(days=8)).isoformat()]
    grid = list(itertools.product([60.0, 150.0, 300.0], [0.80, 0.88, 0.95], [4.0, 12.0, 20.0]))
    best = None
    for K, Dc, Sp in grid:
        P = {'K_MIN': K, 'DECAY': Dc, 'SIM_POW': Sp}
        sc, n, *_ = run(logs, days, P)
        if not best or sc < best[0]: best = (sc, P)
        print(f"K {K:5.0f} decay {Dc:.2f} pow {Sp:4.0f}  error {sc:.4f}  n {n}")
    P = best[1]
    shr = min(((run(logs, days, P, a)[0], a) for a in [0.0, 0.15, 0.3, 0.5]))
    sc, n, sums, err, rows = run(logs, days, P, shr[1], collect=True)
    mult = {}
    for role, S in sums.items():
        mult[role] = {}
        for s in ST:
            r = S[s + '_a'] / S[s + '_p'] if S[s + '_p'] > 0 else 1.0
            mult[role][s] = round(max(0.85, min(1.15, 1 + 0.75 * (r - 1))), 3)   # 75% of the measured mean bias (weekly sums need mean-unbiased lines)
    # baselines on the same player-days
    def berr(key):
        e = m = 0
        for role, act, pr, base in rows:
            b = base[key]
            if not b: continue
            e += sum(abs(act[s] - b[s]) / SD[s] for s in ST); m += 1
        return e / max(1, m)
    def merr(): return sum(sum(abs(a[s] - p[s]) / SD[s] for s in ST) for _, a, p, _ in rows) / max(1, len(rows))
    def merr_cal(): return sum(sum(abs(a[s] - p[s] * mult[role][s]) / SD[s] for s in ST) for role, a, p, _ in rows) / max(1, len(rows))
    rep = {'days': [days[0], days[-1]], 'playerDays': n, 'params': P, 'minShrink': shr[1],
           'error': {'season_avg': round(berr('season'), 4), 'last15_raw': round(berr('last15'), 4), 'depth': round(merr(), 4), 'depth_calibrated': round(merr_cal(), 4)},
           'bias': {role: {s: round(S[s + '_a'] / S[s + '_p'] - 1, 3) if S[s + '_p'] else None for s in ST + ['MIN']} for role, S in sums.items()},
           'count': {role: int(S['n']) for role, S in sums.items()}, 'mult': mult}
    json.dump(rep, open(W + 'backtest_report.json', 'w'), ensure_ascii=False, indent=1)
    json.dump({**P, 'minShrink': shr[1], 'mult': mult, 'fittedTo': days[-1], 'fitted': f"{days[0]}..{days[-1]} ({n} player-days)"}, open(W + 'depth_calib.json', 'w'), ensure_ascii=False, indent=1)
    print(json.dumps(rep, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
