# SGP Shadow Runner

**Paper research only. No sportsbook account interaction and no automatic betting.**

The single-game lab runs beside the cross-game V1–V8 tournament but has separate data, records, P&L, and promotion rules.

## Model family

| Model | Rule | Purpose |
|---|---|---|
| S0 | highest-quality unrelated pair | negative/control construction |
| S1 | legacy passer + catcher, same direction | old heuristic control; team identity is recorded but not required |
| S2 | verified same-team passer/catcher, Pinnacle fair, >=5 books, reception line >1.5, >=1 BOV+DK dual-confirmed leg | quality stack without empirical correlation adjustment |
| S3-A | Tier A true-correlation + dual confirm + positive S3 pricing edge | strict value |
| S3-B | Tier A + dual confirm, no price gate | hit/confirmation diagnostic |
| S3-C | Tier A + positive S3 pricing edge, no confirmation gate | test confirmation necessity |
| S3-D | Tier A, no confirmation or price gate | pure true-correlation outcome diagnostic |
| S3-E | Tier A+B, no confirmation or price gate | broader-volume control |

S3 uses the conservative priors in `research/s3_true_correlation/results/s3_priors_recomputed.csv`, trained on 2021–2024 and validated on 2025.

## Causal timing

`data/current_lines.csv` is observed on every tick. Board counts are stored for events within 36 hours of kickoff.

An event freezes on the first successful tick with **0 < hours-to-kick <= 8**. This is event-relative rather than a hard clock time so the six-hour GitHub cadence works for Thursday night, Sunday afternoon, London, and Monday night games.

At freeze:

1. nflverse weekly roster data verifies player team and position.
2. current PropLine lines build S0–S3 candidate pairs.
3. eligible candidate pairs are sent to PropLine `/sgp` for actual DraftKings/FanDuel SGP research quotes.
4. S0/S1/S2/S3-A:E decisions are persisted once and never rewritten.
5. every S3 candidate receives an approval/rejection row with the exact failing gate.

## Generated data

The runner creates these files automatically:

- `data/sgp_shadow_boards.csv` — running board counts/snapshots.
- `data/sgp_shadow_decisions.csv` — frozen model play/no-play decisions.
- `data/sgp_shadow_results.csv` — settled paper plays.
- `data/sgp_rejection_audit.csv` — candidate/model gate audit, later labeled winner/loss.
- `data/sgp_roster_cache.csv` — compact current-season nflverse team/position cache.

The rejection audit preserves rejected winners and rejected losers. A winning ticket rejected for an expensive price remains a **winning outcome but rejected value play**.

## Settlement

Paper stake is `$5` per approved shadow slip. Both legs must win for a win. If either loses, the SGP loses. If a leg is void/push, the shadow ticket is marked void rather than inventing a correlated reprice.

## Dashboard / Telegram

The main dashboard shows a separate **Single-Game Lab · Shadow Only** section with model records and `week -> date -> game -> slip` history.

SGP shadow slips are **not** included in the cross-game Telegram lineup message and never change V1–V8 records.

## Roster source

The runner downloads the free nflverse weekly roster CSV once per local day and compacts it to the fields needed for team verification. If the download fails, a recent cache (<=7 days) may be used. If no usable roster is available, S2/S3 will not freeze an unverifiable team relationship.

## Tests

```bash
python3 -m unittest discover -s tests -p 'test_sgp_shadow.py' -v
```
