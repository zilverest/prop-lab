# Forward Test Plan

## Parallel research families

### A. Cross-game (already live)
V1–V8 continue unchanged.

### B. Single-game SGP (shadow)
S0 / S1 / S2 / S3-A / S3-B / S3-C / S3-D / S3-E.

The two families must have separate:
- decision files,
- records,
- P&L,
- model histories,
- Telegram status,
- promotion criteria.

## Desired hierarchy
`Family -> Model -> Week -> Date -> Game -> Slip`

## Freeze behavior
An SGP decision must be persisted before kickoff and cannot be retroactively changed after
later prices or results arrive.

## Suggested future data files
- `data/sgp_shadow_boards.csv`
- `data/sgp_shadow_decisions.csv`
- `data/sgp_shadow_results.csv`
- `data/sgp_rejection_audit.csv`

## Next integration task
Build a shadow runner that:
1. verifies current 2026 player teams,
2. discovers true same-team candidate pairs,
3. applies S3-A:E in parallel,
4. attaches actual `/sgp` quotes,
5. stores every decision and rejection,
6. settles results,
7. generates a research-only report.

Do not change the production V1–V8 logic while doing this.
