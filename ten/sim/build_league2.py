import json, os
W=os.path.dirname(os.path.abspath(__file__))+'/'
import os
d=json.load(open(W+os.environ.get('SRC','league2_out.json')))
tpl=open(W+'league_template.html').read()
head=tpl[:tpl.index('</style>')+8]   # title, meta, fonts, base tokens/styles (same identity as v1)
body=open(W+'league2_body.html').read()
P={p['id']:p for p in d['proj']}
LAB={'FG':'FG%','FT':'FT%','TPM':'3PM','REB':'REB','AST':'AST','STL':'STL','BLK':'BLK','TO':'TO','DD':'DD','PTS':'PTS','TW':'TW'}
C=d['cats']
_UP=json.load(open(W+'user_plan.json'))
extra=_UP.get('notes',{})
for t in d['teams']:
    top=sorted(t['roster'],key=lambda i:P[i]['vr'])[:3]
    s=[LAB[c] for c in C if t['profile']['rank'][c]<=2]; w=[LAB[c] for c in C if t['profile']['rank'][c]>=9]
    base=f"{'·'.join(P[i]['n'] for i in top)} 중심. 강점 {'·'.join(s) or '없음'}, 약점 {'·'.join(w) or '없음'}."
    if t['me']:
        low=[P[i]['n'] for i,_ in t['drop'][:4]]
        base+=f" 기여 최저: {'·'.join(low)}."
    t['note']=extra.get(t['abbr'],'')+(' ' if t['abbr'] in extra else '')+base
_M=json.load(open(os.path.join(W, '..', 'data', '')+'meta.json')); d['asOf']=_M['asOf']; _SYNC='ESPN API 동기화 '+_M['asOf'][5:10].replace('-','/')+' '+_M['asOf'][11:16]
d['fresh']=[['일별 상위 10명·연속경기 규칙·주 2회 교체 반영',1],[_SYNC,0],['로스터·부상·대진 = ESPN 실시간',0],['실제 기록 ESPN API(최대 3경기)',0],['1주차 최종 반영',0],[_UP.get('headline','사용자 운영 계획 반영'),1],['부상자 복귀일 = ESPN 리포트',0],['Basketball Reference 2021~2026',0],['NBA 일정 1~14주 실제',0]]
_RS=json.load(open(W+'rosters_espn.json')); _fd=_RS['current'].get('fromDate','2026-10-26'); import datetime as _d2
_last=(_d2.date.fromisoformat(_fd)-_d2.timedelta(days=1)).strftime('%m/%d')
_SC=json.load(open(W+'nba_sched.json')); _cp=_RS['current']['period']; _ws=_d2.date.fromisoformat(_SC['starts'][_cp-1]); _we=_ws+_d2.timedelta(days=6)
d['w1meta']={'title':f"매치업 {_cp} ({_ws.strftime('%m/%d')}~{_we.strftime('%m/%d')}) · {_last} 경기까지 확정 + 남은 경기 예측",'through':f"{_last} 경기까지",'remaining':f"{_fd[5:].replace('-','/')}~{_we.strftime('%m/%d')}",'rosterNote':'ESPN API 실시간 로스터·스코어. 확정분은 ESPN 카테고리 합계 그대로, 남은 날은 일별 상위 10명 예측.'}
d['stepWhen']={}
d['actualThrough']=f"{_last} 경기(ESPN API 2027 시즌 평균)"
d['planRisk']='교체안은 무소속 선수 시즌 예측치 기준이며, 다른 팀이 먼저 영입할 수 있습니다. IR 선수는 ESPN 예상 복귀일부터 합류하고, 활성 로스터가 13명을 넘으면 가치 최하위 선수를 방출한다고 가정했습니다.'
OPTS=[('kat','최근 평가','mid','')]
d['tradeOptions']=[]
for k,tag,tc,fair in OPTS:
    x=json.load(open(W+f"opt_{k}{os.environ.get('SUF','')}.json")); d['tradeOptions'].append({'key':k,'label':x['label'],'tag':tag,'tagc':tc,'fair':fair,'give':x['give'],'get':x['get'],'to':x['to'],'me':x['me'],'partner':x['partner']})
d['tradeEval']=d['tradeOptions'][0]
d['tradeOptsNote']='트레이드 효과 = 트레이드 전 로스터(Gobert 보유, Gafford 영입 반영) 대비. 같은 프로젝션·같은 시드 1만 회, 3~22주 전 팀 주 2회 교체 가정.'
d['tsimNote']=''
for t in d['teams']:
    for k in ('ecNo','season0'): t.pop(k,None)
d.pop('doo',None)
for m in d['week1']:
    m['rec']=['0-0-0' if r=='0-0-11' else r for r in m['rec']]
RS=json.load(open(W+'rosters_espn.json')); INF=RS.get('injuryInfo',{}); RET=RS.get('returns',{})
import datetime as _dt
SCH=json.load(open(W+'nba_sched.json')); _st=SCH['starts']
def _missed(team_code, ret):
    n=0
    for w in range(1, len(SCH['sched'])):
        base=_dt.date.fromisoformat(_st[w])
        for dd, day in enumerate(SCH['sched'][w]):
            if team_code in day and (base+_dt.timedelta(dd)).isoformat() < ret: n+=1
    return n
d['injury']=[]
for t in RS['teams']:
    for n in t['players']+t['ir']:
        if n in INF:
            x=INF[n]
            tm=next((p['t'] for p in d['proj'] if p['n']==n), '')
            code={'UTAH':'UTA','WSH':'WAS','PHX':'PHO','NO':'NOR','SA':'SAS','NY':'NYK','GS':'GSW'}.get(tm,tm)
            d['injury'].append({'team':t['abbr'],'n':n,'me':t['me'],'ir':n in t['ir'],'status':x['status'],'injury':x['injury'],'ret':RET.get(n,''),'espn':x['espnReturn'],'basis':x['basis'],'note':x['note'],'miss':_missed(code, RET.get(n,'9999'))})
d['injury'].sort(key=lambda x:(not x['me'], x['ret']))
d['returns']=RET; d['injuryAsOf']=json.load(open(os.path.join(W, '..', 'data', '')+'injuries.json'))['asOf'].replace('T',' ')[:16]
d['wk3']=json.load(open(W+os.environ.get('WK3','wk3add_out.json')))
_SP=[('rec','상위 10명 고정 · 주 최대 3회 · 다음 2주 공동 최적화',True),('c2','상위 10명 고정 · 주 최대 2회',False),('free','참고: 방출 제한 없음 · 주 최대 3회',False)]
_WK=json.load(open(W+'wk_now.json')); _b=(_WK['singles'] or [None])[0]
_nm=_b if _b and _WK['remDays']>=2 and (_b['win']-_WK['base']['win']>=0.05 or _b['e']-_WK['base']['e']>=0.2) else None
_SCs=json.load(open(W+'nba_sched.json'))['starts']
_nowrow={'week':_WK['week'],'start':_SCs[_WK['week']-1],'opp':_WK['opp'],'oppName':_WK['oppName'],'moves':[{'drop':m['drop'],'add':m['add'],'g':m['g'],'gDrop':m['gDrop']} for m in (_nm['moves'] if _nm else [])],
         'nMoves':len(_nm['moves']) if _nm else 0,'before':_WK['base']['e'],'after':(_nm or _WK['base'])['e'],'winBefore':_WK['base']['win'],'winAfter':(_nm or _WK['base'])['win'],'per':{},'perBefore':{},'now':True}
d['streamPlans']=[]
for k,lab,rec in _SP:
    x=json.load(open(W+f'stream_plan_{k}.json')); d['streamPlans'].append({'key':k,'label':lab,'rec':rec,'log':[_nowrow]+[l for l in x['log'] if not l.get('now')],'sum':x['sum']})
d['streamBase']=json.load(open(W+'stream_plan_rec.json'))['sum']['base']
_R=json.load(open(os.path.join(W, '..', 'data', '')+'rosters.json')); d['acqUsed']=next(t for t in _R['teams'] if t['abbr']=='GTD')['transactions']['acquisitions']
d['streamMeta']=f"v1 프로젝션 기준 · 지금까지 교체 {d['acqUsed']}회 사용(ESPN) · 이번 주(잔여)~22주차 계획"
_SPJ=json.load(open(W+'stream_plan_rec.json'))['sum']; _sn=lambda n: n if n in ('Kawhi Leonard',) else n.split(' ',1)[-1]
d['streamNote']='집중안 = 교체 선택 기준에서 해당 카테고리 주간 승률을 1배 더 가중(평가는 동일한 시즌 시뮬레이션). PTS·AST 승률 = 3~22주 매주 실제 상대 대비 평균. '+'상위 10명(사용자 지정: '+'·'.join(_SPJ.get('core',[]))+')은 방출하지 않음. IR 선수 복귀로 활성 13명 초과 시 가치 최하위 선수를 방출(교체 횟수 미소진).'+' 3·4주차(Seoul Dreamers·Saving PakPaks)는 두 주를 함께 놓고 조합을 탐색해, 교체 1회당 기대 카테고리 +0.08개 미만이면 교체하지 않음. 5주차부터는 매주 그 주 상대(ESPN 실제 대진)를 상대로 기대 카테고리 승수를 가장 많이 올리는 교체를 순서대로 고름(무소속 상위 90명 × 우리 팀 하위 5명). 1·2번째 교체는 +0.03개 이상, 3번째는 +0.12개 이상일 때만 실행해 남은 주에 주 2회 이상을 쓸 수 있도록 한도를 관리. 상대 팀은 주 2회 평균적 교체를 가정. 한계: 다른 팀이 같은 무소속 선수를 먼저 데려갈 수 있고, 무소속 선수 예측치는 시즌 평균이라 실제 효과는 이보다 작을 수 있음.'
_KS=[json.loads(l) for l in open(W+'ksens_out.jsonl')] if os.path.exists(W+'ksens_out.jsonl') else []
_kb=_RS['returns'].get('Kawhi Leonard','')
def _kl(r):
    dd=(_d2.date.fromisoformat(r)-_d2.date.fromisoformat(_kb)).days
    return f"{r[5:].replace('-','/')} (ESPN 예상)" if dd==0 else f"{r[5:].replace('-','/')} ({abs(dd)//7}주 {'빠름' if dd<0 else '지연'})"
d['kawhiSens']=[{**k,'label':_kl(k['ret']),'base':k['ret']==_kb,'miss':_missed('TOR',k['ret'])} for k in _KS] if _kb else []
d['kawhiNote']='결장 경기 = 2주차(10/26)부터 복귀 전까지 TOR 실제 일정 기준. 권장안의 주차별 로스터를 고정하고 복귀일만 바꾼 근사치(복귀 시 방출 시점은 ESPN 예상일 기준). v1 프로젝션 기준.'
SM=d['summary']
d['foot']=[
 '데이터: ESPN Fantasy API(리그 504060248, GitHub Actions 동기화 2026-10-26 16:21 KST) — 로스터·IR·부상 상태·1주차 카테고리 합계·22주 대진표·선수별 2027 시즌 평균. 과거 기록 = Basketball Reference 경기당 기록(sumitrodatta/bball-reference-datasets). 신인 NCAA 기록 = 위키피디아. ESPN 2027 프로젝션 = ESPN 300.',
 f'선수별 실제 기록: ESPN API 2027 시즌 평균(253명, 10/25 경기까지 최대 3경기). 1~3주차 반영 비중 {round(SM["WACT"]*100)}%라 영향은 제한적입니다.',
 '시뮬레이션(일별): 매일 경기가 있는 선수 중 ESPN 포지션 규칙(PG·SG·SF·PF·C·G·F·UTIL×3)에 맞는 상위 10명만 집계하고, 출전 불확실분은 벤치 선수가 채우는 기대값으로 계산. 1~14주는 실제 NBA 일정, 15주 이후는 2~14주 요일 패턴 반복. Embiid·LeBron·Curry·Kyrie는 연속 이틀 경기 중 1경기만 출전(사용자 지정). 날짜별 로스터: Gobert ↔ Nembhard 11/2 처리 가정(이번 주는 Gobert 우리 팀), Paul Reed → Gafford 11/2부터, Kawhi IR 11/23 복귀, 복귀 시 Saddiq Bey 방출(가정). Ajay Mitchell = Jalen Williams 경기당 기록 승계(사용자 지정, 출전 경기 수는 Ajay 기준). 어퀴지션 70회 한도를 고려해 3주차부터 전 팀이 매주 2회 교체: 가치가 가장 낮은 2명을 그 주 빈 슬롯을 가장 많이 채우는 팀의 무소속 선수(무소속 가치 6~30위 평균 기록)로 교체. 주간 변동: 카운팅 카테고리 경기당 변동계수, FG%·FT%는 시도 수 기반 이항분포.',
 '부상 가정: ESPN NBA 부상 리포트(site.api.espn.com)의 예상 복귀일부터 출전 가능으로 보고, 실제 NBA 일정에서 그 전 경기는 결장 처리(Kawhi 무릎 염증 11/23 포함 전원 ESPN 기준). IR 선수도 복귀일 이후 로스터에 합류하며, 13명 한도를 넘으면 가치가 가장 낮은 선수를 대체한다고 가정. 날짜가 없는 OUT 선수는 2주차까지 결장, DTD는 정상 출전으로 처리. Jalen Williams는 시즌 아웃(사용자 지정).',
 '대진: ESPN API의 실제 22주 대진표 사용(1주차는 최종 카테고리 합계로 확정). 플레이오프 4팀(1v4·2v3 → 결승, 각 1주).',
 '불확실성: 시즌마다 선수 성적 ±10%, 20% 확률로 장기 결장(예상 경기의 35~85%), NBA 팀 승수 ±6승을 무작위 적용해 1만 회 반복.',
]
if os.environ.get('DUMP'):
    json.dump(d,open(W+os.environ['DUMP'],'w'),ensure_ascii=False); print('dumped'); raise SystemExit
js=json.dumps(d,ensure_ascii=False,separators=(',',':')).replace('</','<\\/')
html=head+'\n'+body.replace('%%DATA%%',js)
open(W+'league2.html','w').write(html)
print(len(html))
