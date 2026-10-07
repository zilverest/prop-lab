# NBA Phase 1 — Pseudo-Live Historical Replay + Forward Collection

Status: APPROVED
Date: 2026-10-07

## Purpose

Use PropLine's timestamped NBA odds history to replay completed games as if Eevee were live at fixed pre-tip decision times.

This phase is DEVELOPMENT / PRESEASON DIAGNOSTIC evidence only. It must never be relabeled as regular-season forward validation.

The live NFL families remain unchanged.

## Core principle

At replay cutoff T-x, the engine may use only information timestamped at or before that cutoff.

Later snapshots, canonical closing lines, and final graded outcomes remain hidden until after the decision is frozen.

This preserves causal timing and prevents look-ahead bias.

## Core markets

Initial market set:

- player_points
- player_rebounds
- player_assists
- player_threes

Initial analysis should prefer standard two-sided Over/Under main lines.

Milestones, thresholds, alternates, combo props and SGPs are excluded from the primary baseline until explicitly introduced as separate preregistered variants.

## Replay times

Attempt:

- T-12h
- T-8h
- T-4h
- T-2h
- T-1h
- T-30m

T-24h may be retained when genuinely available but is not required because the Phase 0 audit showed frequent absence in preseason.

If no eligible board exists near a target cutoff, record unavailable. Do not substitute a later snapshot.

## Fair/reference probability tournament

Pinnacle is NOT required for NBA Phase 1 because Phase 0 did not observe Pinnacle in sampled NBA player-prop history.

Reference candidates must be compared empirically rather than declared sharp by assumption.

Initial reference families:

1. LOO_CONSENSUS
   Leave-one-book-out cross-book consensus for the target book.

2. MARKET_MEDIAN
   Median no-vig probability across eligible two-sided books.

3. NOVIG_REFERENCE
   Novig as a standalone reference where a comparable two-sided line exists.

4. BOVADA_REFERENCE
   Bovada as a standalone reference where available.

5. BROAD_WEIGHTED
   A preregistered broad consensus using only contemporaneous eligible books.

Standalone sources with insufficient coverage must produce no observation rather than fallback silently.

## Baseline question

Does a contemporaneous market disagreement signal predict later closing-line value?

Primary evidence:

- average CLV in implied-probability percentage points
- beat-close rate
- same-point close coverage
- canonical close availability

Secondary evidence:

- Brier score
- calibration error
- W/L
- fixed-stake paper P&L

P&L is not the primary promotion metric.

## Hypothesis tournament

All hypotheses are additive. Do not tune thresholds after inspecting one game.

### H1 — Persistence
Compare candidates observed at:
- first appearance
- persistence >=2 snapshots
- persistence >=3 snapshots
- persistence >=4 snapshots

### H2 — Breadth
Compare:
- >=3 books
- >=4 books
- >=5 books
- >=6 books

### H3 — Confirmation
Compare:
- any 1 independent confirming book
- any 2
- any 3
- no named confirmation control

### H4 — Freshness
Compare contemporaneous/fresh quotes with stale or old quotes where metadata supports the distinction.

### H5 — Line type
Primary baseline: main-line only.
Alternates may run as a separate shadow/control family if line_type is reliable.

### H6 — Apparent edge magnitude
Pre-register buckets:
- 0 to <1 pp
- 1 to <2 pp
- 2 to <3 pp
- 3 to <5 pp
- >=5 pp

Test monotonicity. Larger claimed edge should not be treated as better unless CLV/calibration support it.

### H7 — Timing
Compare the same underlying hypothesis at each replay cutoff.

## Matched controls

Every promoted-looking hypothesis must be compared with a deterministic matched random control drawn from the same:
- game/date
- market
- timing bucket
- approximate probability bucket
- available-book count where possible

A hypothesis that does not beat its matched control on CLV/calibration is not considered demonstrated.

## Unit of analysis

Repeated snapshots of the same player/market/line/side are NOT independent observations.

Reports must expose both:
- snapshot observations
- unique underlying selections / line-side entities

Promotion logic uses unique or appropriately clustered evidence, not raw snapshot count.

## Preseason interpretation

All completed 2026 preseason games available in PropLine may be replayed.

Allowed conclusions:
- pipeline works / does not work
- data-quality findings
- reference-source coverage
- hypothesis is interesting / not interesting
- hypothesis falsified in preseason development

Not allowed:
- "proven NBA edge"
- "validated profitable model"
- retroactive forward evidence

## Regular-season validation

Before the first formal 2026-27 regular-season test, freeze a specification using only the development evidence available up to that point.

Formal stages:

Development (historical/preseason)
-> one-shot Validation
-> Confirmation
-> forward regular-season validation

No model promoted from development may claim forward status retroactively.

## Forward collection

In parallel with historical replay, create an isolated NBA capture path.

It must:
- remain separate from NFL files/state
- use basketball_nba only
- capture exact boards and metadata
- preserve immutable timing
- collect closing lines/results after games
- never auto-wager
- never send NFL-style lineup Telegram messages unless separately approved

Preseason forward observations remain diagnostic-only.

## Exit criteria for Phase 1

Phase 1 is complete when:

1. At least all currently accessible completed preseason NBA games have been causally replayed where history is available.
2. Core four markets have coverage statistics.
3. Reference-source tournament has results.
4. Persistence, breadth, confirmation, timing and edge-bucket analyses exist.
5. Matched controls exist.
6. CLV/calibration lead interpretation.
7. Forward NBA capture runs independently without touching NFL state.
8. A Phase 2 recommendation is issued:
   - PASS
   - CONDITIONAL PASS
   - REJECT / redesign

No SGP or parlay work begins in Phase 1.
