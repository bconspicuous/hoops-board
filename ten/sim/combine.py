import os
import json
W=os.path.dirname(os.path.abspath(__file__))+'/'
tpl=open(W+os.environ.get('TPL','league3_template.html')).read(); head=tpl[:tpl.index('</style>')+8]
body=open(W+os.environ.get('BODY','league3_body.html')).read()
enc=lambda d: json.dumps(d,ensure_ascii=False,separators=(',',':')).replace('</','<\\/')
d1=json.load(open(W+'d1.json')); d2=json.load(open(W+'d2.json'))
eng=open(W+'simeng.js').read() if os.path.exists(W+'simeng.js') else ''
# extras for the A-D tabs (2026-11-21): probability history, completed-week results/category totals, the scheduled task's plans
def xtra():
    X = {}
    try: X['trend'] = json.load(open(W+'trend.json')).get('points', [])
    except Exception: X['trend'] = []
    try:
        sb = json.load(open(W+'../data/scoreboard.json')); cur = sb.get('currentMatchupPeriod') or 0
        K = [('FGM','FGM'),('FGA','FGA'),('FTM','FTM'),('FTA','FTA'),('TPM','3PM'),('REB','REB'),('AST','AST'),('STL','STL'),('BLK','BLK'),('TO','TO'),('DD','DD'),('PTS','PTS'),('TW','TW')]
        tot, res, per = {}, {}, set()
        for m in sb.get('matchups', []):
            if not m.get('period') or m['period'] >= cur or not m.get('home') or not m.get('away'): continue
            per.add(m['period'])
            for a, b in ((m['home'], m['away']), (m['away'], m['home'])):
                T = tot.setdefault(a['team'], {k: 0 for k, _ in K}); c = a.get('cats') or {}
                for k, src in K: T[k] += c.get(src) or 0
                res.setdefault(a['team'], []).append({'w': m['period'], 'opp': b['team'], 'W': a.get('wins', 0), 'L': a.get('losses', 0), 'T': a.get('ties', 0)})
        X['catTot'] = {t: dict({'FG': v['FGM'] / max(v['FGA'], 1), 'FT': v['FTM'] / max(v['FTA'], 1)}, **{k: v[k] for k in ('TPM','REB','AST','STL','BLK','TO','DD','PTS','TW')}) for t, v in tot.items()}
        X['res'] = {t: sorted(v, key=lambda x: x['w']) for t, v in res.items()}; X['nWeeks'] = len(per)
    except Exception as e: X['err'] = str(e)[:200]
    for k, f in (('lineupPlan', '../espn/lineup_plan.json'), ('rosterPlan', '../espn/roster_plan.json')):
        try: X[k] = json.load(open(W+f))
        except Exception: pass
    return X
html=head+'\n'+body.replace('%%SIMENG%%',eng).replace('%%XTRA%%',enc(xtra())).replace('%%DATA2%%',enc(d2)).replace('%%DATA%%',enc(d1))
open(W+'league10.html','w').write(html); print(len(html))
