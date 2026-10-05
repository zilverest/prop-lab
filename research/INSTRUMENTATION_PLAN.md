# Instrumentation Sprint v1 — frozen-model evidence plan

## Purpose

NFL data arrives slowly, so every clean slate must answer many questions in parallel without changing the official models after seeing results.

**Official forward families remain frozen:**
- Cross-game: V1–V8
- SGP: S0 / S1 / S2 / S3-A / S3-B / S3-C / S3-D / S3-E

Everything below is additive shadow evidence and cannot rewrite an official decision.

## What is now collected

### 1. Durable board checkpoints
The scheduled pipeline is split into three commits:

1. capture exact current board + metadata
2. freeze official research decisions
3. settle + closing-line evidence + reports

A later API failure cannot erase a successfully committed board.

### 2. Denser game-day capture
The eevee-fast-game-capture workflow records near-game boards hourly on primary NFL game days and Saturday afternoon/evening before the Sunday slate.

The 6-hour base job continues to run all week.

### 3. Stable identity + stale-quote metadata
instrumentation.py queries PropLine /odds?includeBookIds=true near kickoff and stores:
- outcome_id
- player_id
- book_outcome_id
- line_type
- last_change_at
- last_seen_at
- book/market timestamps

The original candidate schema is untouched.

### 4. Independent closing-line archive
closing_capture.py calls /odds/closing after kickoff and creates a canonical closing-line table separate from the original H2 /clv/grade experiment.

Future candidates are joined by outcome_id when possible, with exact-name fallback only when necessary.

### 5. Shadow gate tournament
The following variants run at every committed board:

| Variant | Question |
|---|---|
| A_MIN4 | Is the 5-book minimum too strict? |
| A_NODEPTH | Does the receptions-depth gate add value? |
| A_FAIR3565 | Is a tighter fair-probability range cleaner? |
| A_EDGE3 | Does a >=3% pair-edge floor help? |
| A_EDGE5 | Does a >=5% pair-edge floor help more? |
| A_PERSIST2 | Do edges surviving 2 snapshots improve? |
| A_PERSIST3 | Do edges surviving 3 snapshots improve? |
| A_FRESH300 | Are stale quotes manufacturing edge? |
| A_MAINLINE | Are main lines cleaner than alternates? |
| S_MAXEDGE | Is max reconstructed edge a better selector? |
| S_MAXMINP | Is maximizing the weaker leg better? |
| S_MAXPERSIST | Is persistence a better selector? |
| C_NOCONFIRM | What happens with no BOV/DK confirmation? |
| C_RANDOM_V2 | Probability-pool control selected deterministically at random |

Official V1–V8 are also mirrored at every snapshot to measure timing and selection stability.

### 6. Evidence metrics
Shadow observations settle with:
- W/L
- fixed-$5 paper P&L
- expected wins
- Brier score
- calibration error
- canonical closing-line movement when available
- beat-close rate
- timing bucket
- persistence

## Timing buckets

Every shadow observation is labeled:
- T-24h+
- T-12h
- T-8h
- T-4h
- T-2h
- T-1h

This lets us test whether an apparent edge is strongest early, close to kickoff, or only when it persists.

## Interpretation rules

1. **Do not tune an official model from one slate.**
2. P&L is secondary to probability calibration and CLV at this sample size.
3. Repeated snapshots of one underlying ticket are not independent samples.
4. A shadow variant may be called **interesting** after at least 3 clean slates and 10 unique settled selections.
5. A variant may be considered for promotion only after at least 6 clean slates and 25 unique settled selections, and only if:
   - average CLV is positive,
   - calibration/Brier is no worse than the official parent,
   - the effect is not driven by one slate,
   - the result survives a matched control comparison.
6. Promotion requires a separate pre-registered forward test. Development/shadow evidence never becomes forward evidence retroactively.

## Main questions for the next slates

1. Is the apparent cross-game edge still present after stale-quote and main-line controls?
2. Does confirmation improve CLV/calibration, or only reduce sample size?
3. Does persistence predict better outcomes/CLV?
4. Does max-joint-probability remain the best selector versus max-edge, max-min-leg and max-persistence?
5. Which books, markets, sides and timing buckets consistently beat the close?
6. Are S3 probability estimates calibrated in forward data?
7. Are rejected candidates worse than accepted candidates for the reason the gate intended?
