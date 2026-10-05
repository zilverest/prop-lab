# Eevee — prop lab

Paper-trading experiment: are player-prop markets accessible to a Florida bettor efficient?
Data from PropLine (Hobby tier). Runs unattended on GitHub Actions every 6 hours. **No money is staked.**

## Hypotheses (fixed before week 1 — do not edit mid-season)

| # | Claim | Measured by | Verdict rule |
|---|-------|-------------|--------------|
| H1 | Underdog lines sit off consensus enough to beat their hold | `/ev` EV% on Underdog rows, fair 35–65%, ≥3 books | REJECT if ≥200 rows and zero at ≥+3% |
| H2 | Off-consensus legs beat the closing line (real edge signal) | `/clv/grade` on every candidate | ≥100 legs: ACCEPT if avg EV-vs-close > 0 and beat-close > 55%, else REJECT |
| H3 | Hard Rock singles are beatable | `/ev` EV% on Hard Rock rows, same filter | REJECT if ≥200 rows and zero at ≥+3% |
| H4 | Same-game correlation is mispriced | `/sgp` factor = book price ÷ independent product | ≥60 probes: REJECT if median factor in 0.9–1.1 |

**Money enters only if H2 accepts and one of H1/H3/H4 accepts.** Otherwise the project ends with a finding.

## Candidate gates (a "slip" in this experiment is a single that passes all of these)

- fair probability 30–70% (deep alt lines are devig error, not edge)
- quoted by ≥3 books
- EV ≥ +3% against the no-vig fair line
- if the anchor is an exchange (Kalshi/Polymarket) rather than Pinnacle/Bovada, ≥4 books required

Every candidate is logged whether or not it's at a bettable book, and every one is CLV-graded after kickoff.

## Files

| File | Role |
|------|------|
| `snapshot.py` | pulls `/ev` per upcoming event → change-only history plus `data/current_lines.csv` (exact current board), candidates, SGP probes |
| `close.py` | after kickoff: `/clv/grade` → `data/clv.csv`; when final: `/results` → `data/results.csv` |
| `parlay_lab.py` | frozen V1–V8 forward parlay tournament, settlement, Telegram lineup summary, dynamic `docs/index.html` |
| `sgp_shadow.py` | separate S0/S1/S2/S3-A:E single-game shadow runner: roster verification, actual `/sgp` quotes, frozen decisions, rejection audit, settlement |
| `report.py` | legacy H1–H4 rollups + verdicts → `docs/ledger.html` + `docs/internal.html` |
| `docs/index.html` | dynamic Parlay Lab forward-research cockpit — GitHub Pages homepage |
| `run.py` | phased runner: capture → research/freeze → settle/report; each phase can run independently |
| `instrumentation.py` | stable outcome/player IDs, quote freshness metadata, game context, pipeline health |
| `closing_capture.py` | direct `/odds/closing` archive + ID-aware CLV diagnostics, separate from H2 |
| `shadow_lab.py` | additive gate/selector/timing tournament + Brier/calibration/CLV metrics |
| `evidence_report.py` | book/market/side/timing CLV cohort report → `docs/evidence.html` |
| `common.py` | API client, CSV store, gates, Telegram |
| `SGP_SHADOW.md` | SGP shadow model definitions, generated files, timing, and settlement rules |
| `.github/workflows/lab.yml` | base 6h pipeline with an immutable commit after capture, freeze, and settlement |
| `.github/workflows/fast-game-capture.yml` | hourly near-game capture/freeze on primary NFL game days |
| `.github/workflows/instrumentation-validation.yml` | compile + offline unit-test gate for research plumbing |

All data is plain CSV — open in pandas or Excel. `data/state.json` holds bookkeeping (change-detection signatures, closed events, message cadence).

## Telegram

The older Top-8-straights and weekly “board captured” messages are retired. Telegram is now intentionally compact:

- **Game day** — one Parlay Lab research message when the frozen board is created. Identical lineups selected by several models are deduplicated and tagged `V1 · V2 · V3` rather than repeated.
- **Tuesday** — compact forward model-tournament summary (V1–V6 + V8).
- **FAILED / warning** — immediately on an exception or an empty Thu–Sun snapshot.

Cross-game prices are still reconstructed from the two leg prices. Telegram explicitly says `recon` and tells you to verify the live platform ticket; no bet is placed automatically. V7 remains blocked until actual parlay-quote capture exists.

## Instrumentation sprint

The official forward models are frozen. New research is additive and is stored separately so it cannot rewrite V1–V8 or S0–S3 outcomes.

The pipeline now commits in three stages:

```
capture exact board + IDs/freshness
→ git checkpoint
→ freeze official research decisions
→ git checkpoint
→ settlement + canonical closing lines + reports
→ git checkpoint
```

That ordering prevents a downstream API failure from erasing a successfully captured pregame board.

Near game time, a second workflow captures the board more frequently. Every committed board is mirrored into a shadow tournament that tests gate ablations, selector alternatives, persistence, quote freshness, main-vs-alt lines, timing buckets, and matched controls. Shadow observations record expected wins, Brier score, calibration error, canonical closing-line movement and paper P&L.

Research views:
- `/diagnostics.html` — gate / selector / timing shadow tournament
- `/evidence.html` — canonical CLV cohorts by book, market, side, timing, line type and fair source
- `research/INSTRUMENTATION_PLAN.md` — pre-registered interpretation and promotion rules

## Building slips (paper only)

Candidates are logged automatically every tick. To turn one or more into a tracked slip:

```
python3 slips.py list                      # indexed list of recent distinct candidates
python3 slips.py straight --idx 3          # log a 1-unit straight bet on candidate #3
python3 slips.py sgp --idx 3,7 --book fanduel   # same-event legs -> real book SGP price via /sgp
python3 slips.py show                      # ledger + running P&L
```

`sgp` requires all picked legs to share one `event_id` and calls the book's own correlated-price
endpoint — if the book won't quote that combination it tells you and logs nothing. Every slip is
1 unit, paper only, and settles automatically each tick (`run.py` calls `slips.settle()` after
`close.py`) once every leg in it has a graded result. The paper ledger (`docs/ledger.html`) shows the
running count and P&L; `data/slips.csv` is the full record.

## Parlay Lab forward research

The historical Sep. 20–27 results are stored only as a **development replay**. They remain visible for context but are never treated as forward validation. Beginning with the next game-day board, decisions are frozen to `data/parlay_decisions.csv` and never retroactively reshuffled after later prices arrive.

Forward board freeze: the first successful scheduled/manual tick at or after **08:00 America/New_York** on an NFL game day. The exact freeze timestamp is recorded on the dashboard. `snapshot.py` also writes `data/current_lines.csv` each tick so the parlay models use only lines that still exist on the live board; the change-only `lines.csv` is not used as live state when `current_lines.csv` is available.

Frozen variants:

| Model | Rule |
|---|---|
| V1 Strict | Pinnacle fair + Bovada & DraftKings confirmation + ≥5 books + receptions >2.5 |
| V2 Depth | V1, but receptions >1.5 |
| V3 Bovada | Pinnacle fair + Bovada confirmation + ≥5 books + receptions >1.5 |
| V4 DraftKings | Pinnacle fair + DraftKings confirmation + ≥5 books + receptions >1.5 |
| V5 Any 2 | Pinnacle fair + any 2 confirming books + ≥5 books + receptions >1.5 |
| V6 Any 3 | Pinnacle fair + any 3 confirming books + ≥5 books + receptions >1.5 |
| V7 Value Floor | blocked until actual cross-game parlay quotes can be captured |
| V8 Strong Slate | V3 pool; up to two positive-edge pairs, second pair may not share either game with the first |

The dashboard drills down **model → week → date → slip** and shows no-play dates as data, not omissions. The original H1–H4 and legacy paper-slip records remain separate and unchanged.

## Single-game SGP shadow research

The SGP research family runs separately from the cross-game tournament. It observes the current board, verifies true same-team QB/pass-catcher identity from nflverse weekly rosters, requests actual PropLine `/sgp` research quotes near kickoff, freezes S0/S1/S2/S3-A:E decisions, and settles them later. Its data and P&L never alter V1–V8.

SGP decisions freeze event-by-event on the first successful tick within **8 hours of kickoff**. The dashboard exposes the SGP family as **shadow only**; game-day Telegram remains the cross-game lineup message. See `SGP_SHADOW.md` and `research/s3_true_correlation/` for the frozen model definitions and empirical priors.

## Offline test

```
python3 snapshot.py --from-file ev_sample.json --event-id 32646 --no-sgp
python3 report.py
```

## Known limits

- PropLine's NFL archive starts September 2026 — nothing to backtest; the sample accumulates one week at a time.
- Fair-source coverage varies by market and week. The parlay research variants intentionally require `fair_source=pinnacle`; if Pinnacle is absent, those variants simply produce fewer or no plays.
- Underdog here prices two-way (~-112/-112), not flat pick'em payouts. H1 tests it as a book, because that's what it is in this feed.
- `lines.csv` grows all season. If the repo gets heavy, move old weeks to a release asset.

## Settlement

A slip leg is graded, in order: the exact result row at the slip's book; the exact row at any book;
otherwise the player's actual stat vs our line (Over/Under legs). The last step matters because when
a line moves before kickoff, books stop listing the number we logged. Voided legs (player didn't play)
are dropped: a straight is refunded, a parlay/SGP pays the remaining legs at their own prices. Any leg
still ungradeable 72 hours after kickoff is voided, so nothing stays open forever.

## Confirming a deploy

`LAB_VERSION` in `common.py` is printed in the paper-ledger footer and at the top of `internal.html`.
After uploading new code and running a tick, check that version on `ledger.html` or `internal.html`.

## GitHub Pages

- `/` → dynamic Parlay Lab forward-research cockpit (`docs/index.html`, regenerated by `parlay_lab.py`)
- `/ledger.html` → existing Eevee paper ledger (generated by `report.py`)
- `/internal.html` → existing H1–H4 research lab (generated by `report.py`)

`docs/index.html` is generated every tick from the frozen development replay plus `data/parlay_decisions.csv`. The forward section begins empty and grows week → date → slip without changing prior decisions.
