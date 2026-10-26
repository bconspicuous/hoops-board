# g8 · 8팀 리그(G League, ESPN 751654965) ESPN 자동 연동

10팀 리그(`ten/`, 워크플로 `ten · ESPN league sync`, Secrets `ESPN_S2`/`ESPN_SWID`)와 코드·데이터·Secrets를 공유하지 않습니다.

| 구성 | 내용 |
|---|---|
| 워크플로 | `.github/workflows/g8-espn.yml` — 하루 3회(미국 동부 03~13시, 경기 없는 시간) + 수동 실행 |
| Secrets | `G8_ESPN_S2`, `G8_ESPN_SWID` (8팀 리그용, 별도) |
| 수집 | `g8/espn/fetch_g8.py` → `g8/data/` (rosters, scoreboard, players_2027.csv, injuries, meta) |
| 변환 | `g8/espn/to_dashboard.py` → `src/data/` rosters·live·results·actuals → `src/build_v22.py` → 루트 `index.html` |

## 쿠키 등록 (최초 1회, 만료 시 재등록)
1. PC 브라우저로 fantasy.espn.com 로그인 → 개발자도구 → Application → Cookies → `espn_s2`, `SWID` 값 복사
2. GitHub 저장소 Settings → Secrets and variables → Actions → New repository secret
   - `G8_ESPN_S2` = espn_s2 값, `G8_ESPN_SWID` = SWID 값(중괄호 포함)
3. Actions → `g8 · ESPN league sync (8-team G League)` → Run workflow

쿠키는 Secrets에만 저장되며 저장소·로그에 기록되지 않습니다. 같은 ESPN 계정이면 10팀 리그와 값이 같아도 되지만, Secret 이름은 분리해 한쪽 갱신이 다른 쪽에 영향을 주지 않습니다.

## 동작 규칙
- 로스터·부상 상태(O/DTD)·주간 영입 횟수·카테고리 합계는 ESPN 값이 기준(수동 캡처보다 우선). 사용자 지정 상태(예: DTD를 O로)는 다음 동기화에서 ESPN 값으로 덮어씀
- 진행 중 매치업 합계(`live`)는 미국 동부 03~13시 실행분만 반영(전날 경기까지 확정). 종료된 매치업은 `results`에 카테고리 W-L-T로 고정
- 2026-27 실적(`actuals`)은 ESPN 시즌 평균(GP·DD 포함)
- 아티팩트(claude.ai) 대시보드는 GitHub에서 갱신할 수 없어 Claude가 같은 데이터를 저장소(league/*)에 반영할 때 갱신됨
