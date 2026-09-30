# S3 True Correlation — Checkpoint 2026-09-30

## Status
**RESEARCH ONLY / NOT ACTIVE IN PRODUCTION**

This checkpoint preserves the S3 single-game correlation work without changing the live
cross-game V1–V8 models, Telegram routing, or dashboard.

## Data split
- Training: NFL regular seasons **2021–2024**
- Validation: **2025**
- 2026: reserved for forward evaluation
- Source data: nflverse weekly player statistics
- Raw nflverse season files are intentionally NOT committed here; use `download_nflverse.py`
  to reproduce them.

## Empirical sample
From the uploaded 2021–2025 nflverse player-week files:
- rows loaded: **90,585**
- verified same-team primary-QB/pass-catcher observations: **21,569**

See:
- `results/summary.json`
- `results/same_team_qb_catcher_observations.csv`
- `results/raw_archetype_correlations.csv`
- `results/s3_priors_recomputed.csv`

## Identity rule
A pair is not a true stack unless:
1. same season/week/team,
2. QB is the primary QB for that team-week (highest pass attempts),
3. catcher is WR/TE/RB/FB,
4. catcher has receiving opportunity,
5. opposing-team and UNKNOWN relationships are rejected.

The old S1 heuristic is not accepted as evidence of correlation until this identity join passes.

## Current conservative archetype tiers

### Tier A
Used by S3-A through S3-D.

- `PASS_YDS__REC_YDS / WR`
- `PASS_TD__REC_TD / WR`
- `PASS_TD__REC_TD / TE`
- `COMPLETIONS__RECEPTIONS / WR`
- `COMPLETIONS__RECEPTIONS / TE`
- `COMPLETIONS__RECEPTIONS / RB`

These all have positive train/validation correlation with conservative `rho_cons`
approximately >= 0.25 in `results/s3_priors_recomputed.csv`.

### Tier B
Added only by S3-E broad research.

- `PASS_YDS__RECEPTIONS / WR`
- `PASS_YDS__REC_YDS / TE`
- `PASS_YDS__REC_YDS / RB`
- `ATTEMPTS__RECEPTIONS / WR`
- `ATTEMPTS__RECEPTIONS / TE`
- `ATTEMPTS__RECEPTIONS / RB`
- `PASS_TD__REC_TD / RB`

Tier B is deliberately broader and is a shadow/control expansion, not a promoted production whitelist.

## S3 variant tournament — frozen definitions

All variants require:
- verified same-team primary QB + pass catcher,
- actual supported QB/catcher market archetype,
- Pinnacle fair probability available for both legs,
- >=5 books on both legs,
- reception depth screen (`receptions > 1.5` when a reception line is involved),
- actual SGP quote when evaluating price,
- max one primary slip per game for comparison.

### S3-A — STRICT VALUE
- Tier A archetype only
- at least one leg is Bovada + DraftKings dual-confirmed
- correlation-adjusted S3 fair probability > book break-even probability
- purpose: strict value model

### S3-B — HIT + CONFIRM
- Tier A archetype only
- at least one leg is Bovada + DraftKings dual-confirmed
- **no price gate**
- purpose: isolate whether cross-book confirmation helps outcome selection even when the book charges heavily

### S3-C — VALUE, NO CONFIRM
- Tier A archetype only
- no Bovada/DK confirmation requirement
- S3 fair probability > book break-even probability
- purpose: test whether confirmation is unnecessarily restrictive

### S3-D — QUALITY HIT
- Tier A archetype only
- no confirmation requirement
- no price gate
- purpose: pure true-correlation / outcome-selection shadow model

### S3-E — BROAD TRUE CORRELATION
- Tier A + Tier B archetypes
- no confirmation requirement
- no price gate
- purpose: higher-volume control to measure where correlation quality begins to degrade

## Legacy / controls
- S0: stranger control
- S1: legacy heuristic stack (team identity not guaranteed)
- S2: quality stack without empirically measured correlation
- S3-A:E: verified true-correlation research family

## Current 2026 bridge result
The first bridge audit found:
- strict S3 approved slips: **0**
- two verified true-correlation near-candidates were historical winners but were materially
  overpriced by their archived SGP quotes under the S3 fair-probability estimate.
- therefore W/L and price/value must be reported separately.

This is evidence for running multiple strictness variants, not for loosening production rules.

## Forward-test principle
Cross-game and SGP tracks must remain separate:

### Cross-game
- V1–V8
- current live forward experiment

### Single-game SGP shadow
- S0/S1/S2/S3-A:E
- separate ledger and model history
- never contributes to V1–V8 record, P&L, or model promotion

Weekly research reporting may display both families side by side, but never merge their records.

## Promotion rule
No S3 variant is promoted to the official dashboard/Telegram execution layer merely because
it wins a few tickets. Promotion requires forward evidence on:
- activity / number of games,
- predicted vs observed hit rate,
- Brier/calibration,
- actual SGP pricing gap,
- fixed-stake P&L / ROI,
- rejection audit (winners and losers filtered out),
- stability across multiple weeks.

## Known limitation
This checkpoint does NOT automatically run S3 against live 2026 SGP boards.
A separate shadow integration is still required to:
1. obtain current 2026 team identity,
2. run S3-A:E on live/archived SGP quotes,
3. persist play/no-play/reject decisions before kickoff,
4. settle those decisions afterward.

Until that integration is added, this checkpoint is reproducible research, not a live SGP forward runner.
