# proj · 2026-27 projection (ESPN × Basketball-Reference regression)

| File | Role |
|---|---|
| `br/2021.txt … 2026_a.txt` | BR season per-game rows (pipe-separated; 2021–2025 = scoring leaders visible on the season page, ~top 250) |
| `br/box/g<MMDD><HOME>.txt` | BR 2026-27 box scores (`TEAM|Player|MP|FG|FGA|3P|FT|FTA|TRB|AST|STL|BLK|TOV|PF|PTS`, `DNP` rows) |
| `ncaa.json` | NCAA 2025-26 per-game for rookies (sports-reference cbb) |
| `brload.py` | Name normalisation + season loader |
| `project27.py` | Regression, backtest, inverse-variance blend with ESPN, DD model, rookie blend → `../ref27_base.json` |
| `actuals27.py` | Box scores → `../data/actuals.json` (league/actuals) |

Pipeline (from `src/`): `python3 proj/project27.py` → `IN=ref27_base.json python3 neutral.py 0.3333 0` → `python3 proj/actuals27.py <through>` → `python3 publish.py …`
