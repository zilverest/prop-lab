# NBA Phase 1 - Causal Preseason Replay

Generated: 2026-10-12T15:05:56Z

**Evidence class: PRESEASON_REPLAY_DIAGNOSTIC**

Each decision uses only snapshots available at or before its historical cutoff. Closing lines and results are joined afterward.

Events requested: **20**  
Events replayed successfully: **20**

## Variant summary

| Variant | Plays | W-L | Avg CLV pp | Beat close | Brier | Paper P&L | ROI | Unique |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| B0_LOO | 5 | 5-0 | +0.00 | 0.0% | 0.235 | USD +25.00 | 100.0% | 1 |
| B0_BOVADA | 0 | 0-0 | — | — | — | USD +0.00 | — | 0 |
| B0_NOVIG | 11 | 6-5 | +0.00 | 0.0% | 0.240 | USD +2.32 | 4.2% | 6 |
| PERSIST2 | 4 | 4-0 | +0.00 | 0.0% | 0.235 | USD +20.00 | 100.0% | 1 |
| PERSIST3 | 3 | 3-0 | +0.00 | 0.0% | 0.235 | USD +15.00 | 100.0% | 1 |
| C_RANDOM_B0 | 5 | 5-0 | +0.00 | 0.0% | 0.235 | USD +25.00 | 100.0% | 1 |

## Timing summary

### T-8h

| Variant | Plays | Avg CLV pp | Beat close | Brier |
|---|---:|---:|---:|---:|
| B0_LOO | 1 | +0.00 | 0.0% | 0.234 |
| B0_BOVADA | 0 | — | — | — |
| B0_NOVIG | 1 | +0.00 | 0.0% | 0.218 |
| PERSIST2 | 0 | — | — | — |
| PERSIST3 | 0 | — | — | — |
| C_RANDOM_B0 | 1 | +0.00 | 0.0% | 0.234 |

### T-4h

| Variant | Plays | Avg CLV pp | Beat close | Brier |
|---|---:|---:|---:|---:|
| B0_LOO | 1 | +0.00 | 0.0% | 0.235 |
| B0_BOVADA | 0 | — | — | — |
| B0_NOVIG | 1 | — | — | 0.232 |
| PERSIST2 | 1 | +0.00 | 0.0% | 0.235 |
| PERSIST3 | 0 | — | — | — |
| C_RANDOM_B0 | 1 | +0.00 | 0.0% | 0.235 |

### T-2h

| Variant | Plays | Avg CLV pp | Beat close | Brier |
|---|---:|---:|---:|---:|
| B0_LOO | 1 | +0.00 | 0.0% | 0.235 |
| B0_BOVADA | 0 | — | — | — |
| B0_NOVIG | 2 | +0.00 | 0.0% | 0.244 |
| PERSIST2 | 1 | +0.00 | 0.0% | 0.235 |
| PERSIST3 | 1 | +0.00 | 0.0% | 0.235 |
| C_RANDOM_B0 | 1 | +0.00 | 0.0% | 0.235 |

### T-1h

| Variant | Plays | Avg CLV pp | Beat close | Brier |
|---|---:|---:|---:|---:|
| B0_LOO | 1 | +0.00 | 0.0% | 0.235 |
| B0_BOVADA | 0 | — | — | — |
| B0_NOVIG | 3 | +0.00 | 0.0% | 0.220 |
| PERSIST2 | 1 | +0.00 | 0.0% | 0.235 |
| PERSIST3 | 1 | +0.00 | 0.0% | 0.235 |
| C_RANDOM_B0 | 1 | +0.00 | 0.0% | 0.235 |

### T-0.5h

| Variant | Plays | Avg CLV pp | Beat close | Brier |
|---|---:|---:|---:|---:|
| B0_LOO | 1 | +0.00 | 0.0% | 0.235 |
| B0_BOVADA | 0 | — | — | — |
| B0_NOVIG | 4 | +0.00 | 0.0% | 0.260 |
| PERSIST2 | 1 | +0.00 | 0.0% | 0.235 |
| PERSIST3 | 1 | +0.00 | 0.0% | 0.235 |
| C_RANDOM_B0 | 1 | +0.00 | 0.0% | 0.235 |

## Guardrails

- Preseason replay is diagnostic and is not regular-season validation.
- Closing lines and results are joined only after causal selections are constructed.
- Repeated timing observations of one underlying selection are correlated.
- P&L is secondary to CLV and calibration.
- No variant may be promoted from this replay alone.

## Next gate

Use this replay to verify plumbing and screen hypotheses only. Keep collecting NBA snapshots permanently. The 2026-27 regular-season opener begins the formal forward evidence stream.
