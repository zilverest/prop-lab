# NBA Phase 1 — Causal Replay + Forward Archive

Status: APPROVED 2026-10-07

## Purpose

Test NBA market-efficiency hypotheses using a pseudo-live historical replay while starting permanent forward collection before PropLine Hobby's rolling 30-day history window expires.

This phase does not create a real-money betting model. It does not alter NFL V1-V8 or S0-S3.

## Evidence classes

1. PRESEASON_REPLAY_DIAGNOSTIC
   - Historical preseason events replayed causally.
   - Useful for plumbing, reference-source comparison, CLV mechanics and hypothesis screening.
   - Never pooled with regular-season evidence.

2. REGULAR_SEASON_FORWARD
   - Begins with the 2026-27 regular-season opener.
   - Immutable snapshots collected prospectively.
   - Primary evidence for any eventual promotion.

## Core markets

- player_points
- player_rebounds
- player_assists
- player_threes

Main-line two-sided Over/Under only for the baseline. Milestones and combos are retained only as raw archive data if encountered; they are not eligible for B0.

## Replay clock

Target decision times:
- T-8h
- T-4h
- T-2h
- T-1h
- T-30m

T-12h is recorded when available but not required. T-24h is observational only because Phase 0 found no sample coverage.

At each cutoff the replay may use only snapshots with recorded_at <= cutoff.

## Fair-probability/reference tournament

Pinnacle was absent in the Phase 0 NBA prop sample, so no Pinnacle assumption is imported from NFL.

Reference families:

- LOO_CONSENSUS: median no-vig fair probability across exact-line two-sided books excluding the candidate book.
- BOVADA_REF: exact-line two-sided Bovada no-vig probability when available.
- NOVIG_REF: exact-line two-sided Novig no-vig probability when available.

A candidate book can never serve as its own reference.

## Baseline gate

B0 is deliberately simple and preregistered:

- main-line exact Over/Under
- candidate fair probability 30%-70%
- at least 2 independent reference books for LOO_CONSENSUS
- estimated candidate EV >= +3%
- snapshot timestamp at or before the replay cutoff

This threshold is a research baseline, not an optimized NBA rule.

## Replay variants

- B0_LOO: highest estimated-EV B0 candidate per event/cutoff from leave-one-out consensus.
- B0_BOVADA: highest estimated-EV candidate using Bovada as reference.
- B0_NOVIG: highest estimated-EV candidate using Novig as reference.
- PERSIST2: B0_LOO candidate identity must have qualified at >=2 replay cutoffs up to that time.
- PERSIST3: B0_LOO candidate identity must have qualified at >=3 replay cutoffs up to that time.
- C_RANDOM_B0: deterministic random candidate from the same B0_LOO candidate pool.

The random control seed is deterministic from event_id + cutoff so replays are reproducible.

## Primary metrics

In order:
1. same-point canonical CLV in implied-probability percentage points
2. beat-close rate
3. Brier score
4. calibration error
5. result hit rate
6. fixed-$5 paper P&L (secondary)

Repeated timing snapshots of the same underlying candidate are correlated and are reported separately from unique-selection metrics.

## Causal guardrails

- No closing line or result is visible during selection.
- Selection is built solely from /odds/history snapshots at/before cutoff.
- Closing/results are joined only after the decision rows are frozen in memory.
- outcome_id is preferred for joins.
- Missing historical information is unavailable, never inferred.
- Preseason and regular-season evidence are never pooled.
- No tuning from a single slate/game.
- No SGP or parlay work in this phase.

## Data retention

PropLine Hobby history is limited to 30 days by event age. Phase 1 therefore starts a separate NBA archive immediately. Raw/reduced pregame observations, closing lines and results will be committed under NBA-specific data paths and cannot modify NFL data files.

## Exit gate

Phase 1 is complete when:

- causal replay runs successfully on all accessible completed NBA preseason events within the current Hobby window,
- B0/reference/persistence/random variants are graded,
- data-quality coverage is quantified,
- permanent NBA forward capture is ready before the regular-season opener,
- full repo test suite passes,
- no NFL behavior changes.

Do not promote an NBA selector or SGP model from Phase 1.
