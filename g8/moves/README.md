# g8 · 영입·방출·IR 자동화 (항목별 승인제)

| 단계 | 누가 | 무엇을 |
|---|---|---|
| 1. 제안 | 정기 실행(Claude) | ESPN 동기화 직후 `node g8/sim/moves.js` → `plan.json`·`plan.md`. 번호 붙은 항목(영입/방출, IR 이동, IR 복귀+방출) |
| 2. 검증 | 정기 실행(Claude) | `g8-moves.yml` `mode=dry`: 영입 대상이 아직 FA/웨이버인지, 방출 대상이 우리 로스터·방출 가능 선수인지, 주간 영입 한도, C 최대 4, IR 자격, 로스터가 제안 시점과 같은지 |
| 3. 승인 요청 | Claude → 감독 | 새 항목만 번호와 기대 효과(이번 주 기대 카테고리 승, 우승·1위 확률 변화)로 제시. "1번 승인"처럼 번호 지정 필요 |
| 4. 실행 | 감독이 번호로 승인한 항목만 | 해당 항목 `status="approved"` 커밋 → `g8-moves.yml` `mode=live`, `items=<번호>` → ESPN 거래 → 재조회 검증 → `executed`/`claim-submitted`/`failed` |

## 제안 기준·안전장치
- 이번 주 +0.05승 이상 또는 우승 +1%p 이상, 우승확률을 0.5%p 넘게 깎는 안은 제외. 최대 3건, 이번 주 남은 영입 한도 안에서
- 방출 후보에서 제외: ESPN 방출 불가 선수, 시즌 가치 상위 8명(PROTECT)
- 서로 동시에 할 수 없는 항목(C 한도·같은 방출 대상)은 표시
- 실행 직전 재검증 실패 시 해당 항목 중단. 자동 재시도 없음(응답이 끊겨도 ESPN이 처리했을 수 있으므로 재조회로만 확인)
- 웨이버 선수는 클레임 제출(`claim-submitted`), 결과는 ESPN 처리 후 다음 동기화에서 확인
- IR: O 상태 선수만 IR로. IR 선수가 O가 아니게 되면 복귀+방출안을 제안(선택 사항)
- IR 규칙(감독 판단 2026-11-03): IR 선수가 DTD여도 영입 가능. ESPN 공식 문서는 "건강한 선수가 IR에 있으면 영입 불가"까지만 명시 → 첫 실제 사례 결과를 `ir_rule.json`에 기록

## 승인 처리 절차 (Claude가 감독의 "N번 승인"을 받았을 때)
1. `git pull` 후 `plan.json`에서 해당 번호 항목 확인(상태 `proposed`). 여러 번호면 `conflicts` 확인
2. 해당 항목만 `status="approved"`, `approvedAt` 기록 → 커밋·푸시
3. `gh api -X POST repos/bconspicuous/hoops-board/actions/workflows/g8-moves.yml/dispatches -f ref=main -f 'inputs[mode]=live' -f 'inputs[items]=N'`
4. 완료 대기 → `git pull` → `last_run.json` 보고(검증 결과, 거래 응답, 실패 사유). 성공 시 `node g8/sim/lineup.js`로 라인업 재제안
5. "N번 거절" → `status="rejected"` 커밋
