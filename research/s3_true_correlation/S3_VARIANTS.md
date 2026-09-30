# S3 Variant Matrix

| Model | Archetypes | Dual confirmation | Price gate | Intended role |
|---|---|---|---|---|
| S3-A Strict Value | Tier A | >=1 leg BOV+DK | S3 edge > 0 | Strict value |
| S3-B Hit+Confirm | Tier A | >=1 leg BOV+DK | None | Confirmation/outcome test |
| S3-C Value-NoConfirm | Tier A | None | S3 edge > 0 | Test confirmation necessity |
| S3-D Quality-Hit | Tier A | None | None | Pure correlation outcome test |
| S3-E Broad | Tier A+B | None | None | Higher-volume control |

## Metrics to record for every variant
- week / date / game
- play / no-play
- candidate count
- rejected candidate count by gate
- QB / catcher / teams / positions
- archetype
- conservative correlation prior (`rho_cons`)
- marginal fair probabilities
- independence joint probability
- correlation-adjusted joint probability
- actual SGP book / quote / break-even probability
- model pricing gap in percentage points
- result
- $5 fixed-stake P&L
- Brier score / calibration fields
- rejection outcome (winner or loser) for rejected candidates

## Rejection audit
Rejected winners are retained as research observations.
A winner rejected for a negative pricing edge remains a **winning outcome but a rejected value play**.
This allows outcome-selection and price-selection performance to be judged independently.
