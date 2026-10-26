# ten · ESPN 리그 데이터 연동

ESPN Fantasy Basketball v3 API(비공식, `lm-api-reads.fantasy.espn.com`)로 리그 504060248(26-27 fantasy) 데이터를 받아 `ten/data/`에 저장합니다.

- 호출: `GET /apis/v3/games/fba/seasons/2027/segments/0/leagues/504060248?view=mSettings&view=mTeam&view=mRoster&view=mMatchupScore&view=mStatus`
- 무소속 선수: 같은 주소에 `view=kona_player_info` + `X-Fantasy-Filter` 헤더(FREEAGENT·WAIVERS, 보유율 상위 200명)
- 실행: GitHub Actions `ten · ESPN league sync`(6시간마다, 수동 실행 가능) → `ten/data/`만 커밋
- 산출물: `rosters.json`(팀·로스터·IR·부상 상태), `scoreboard.json`(매치업별 카테고리 합계·W-L-T), `players_2027.csv`(2027 시즌 평균), `meta.json`, `espn_raw_league.json`

## 비공개 리그 설정 (필요 시)
1. PC 브라우저로 fantasy.espn.com 로그인 → 개발자도구 → Application(저장소) → Cookies → `espn_s2`, `SWID` 값 복사
2. GitHub 저장소 Settings → Secrets and variables → Actions → New repository secret
   - `ESPN_S2` = espn_s2 값, `ESPN_SWID` = SWID 값(중괄호 포함)
3. Actions 탭 → `ten · ESPN league sync` → Run workflow

쿠키는 Secrets에만 저장되고 저장소에는 기록되지 않습니다. 저장소가 공개이므로 `ten/data/`의 로스터·기록은 누구나 볼 수 있습니다.
