# g8 · 라인업 자동 설정 (승인제)

| 단계 | 누가 | 무엇을 |
|---|---|---|
| 1. 제안 | 정기 실행(Claude) | ESPN 동기화 직후 `node g8/sim/lineup.js` → `plan.json`·`plan.md` (오늘 미국 동부 경기일, 상태 `pending`) |
| 2. 검증 | 정기 실행(Claude) | `g8-lineup.yml`을 `mode=dry`로 실행 → ESPN 현재 라인업과 대조, 슬롯 규정 검사, `last_run.json` (ESPN에 쓰지 않음) |
| 3. 승인 요청 | Claude → 감독 | 푸시·메시지로 변경안과 기대 효과 제시, "승인/거절" 답을 기다림 |
| 4. 실행 | 감독이 "승인"한 경우에만 | `plan.json` 상태를 `approved`로 커밋 → `g8-lineup.yml`을 `mode=live`로 실행 → ESPN 반영 후 재조회로 검증, 상태 `executed`/`failed` |

## 규칙
- 실행은 감독의 명시적 승인 뒤에만. 답이 없거나 "거절"이면 아무것도 바뀌지 않음(`rejected`).
- 오늘(미국 동부) 라인업만 실행. 이미 경기가 시작된 선수, IR 슬롯은 건드리지 않음.
- 승인 후 계획을 다시 만들면 선발이 같을 때만 승인 상태를 이어받음. 선발이 바뀌면 다시 승인 필요.
- 기대 효과 0.02 카테고리 승 미만 변경은 `minor`로 표시만 하고 승인 요청 안 함.
- 쿠키는 GitHub Secrets(`G8_ESPN_S2`/`G8_ESPN_SWID`)에만 있고 Action 안에서만 사용.

## 승인 처리 절차 (Claude가 감독의 "승인"을 받았을 때)
1. `git pull` 후 `plan.json`의 `date`가 오늘(미국 동부)이고 상태가 `pending`/`minor`인지 확인
2. `status="approved"`, `approvedAt=<now ISO>` 로 바꿔 커밋·푸시
3. `gh api -X POST repos/bconspicuous/hoops-board/actions/workflows/g8-lineup.yml/dispatches -f ref=main -f 'inputs[mode]=live'`
4. 실행 완료까지 대기 → `git pull` → `last_run.json`의 `ok`·`verified`·`moves`·`skipped`를 감독에게 보고
