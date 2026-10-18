# hoops-board · source

Source for the published `index.html` (dashboard v2.2). Kept here so the build can be restored if the working environment is reset.

| Path | Role |
|---|---|
| `v22/template.html` | Page template (`__REF__` = reference data, `__EMBED__` = league snapshot) |
| `ref22.json` | Reference data: player projections, 2026-27 daily schedule, back-to-back flags and per-player B2B parameters |
| `ref.json` | Base reference data that `b2b/build_b2b.py` extends into `ref22.json` |
| `data/rosters.json`, `data/meta.json` | Current league snapshot embedded in `index.html` |
| `apply_rosters.py` | Validates a transcribed roster snapshot (names, duplicates, 13-man and 4-C limits) and stages it |
| `build_v22.py` | Builds `v22/dashboard.html` (artifact page) and `web/index.html` (this site) |
| `b2b/` | Schedule transcription (Land of Basketball), Basketball-Reference season inputs and the B2B parameter build |

Daily update: `python3 apply_rosters.py new_rosters.json data` → `python3 build_v22.py data` → copy `web/index.html` to the repository root.
