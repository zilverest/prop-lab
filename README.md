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
| `snapshot.py` | pulls `/ev` per upcoming event → `data/lines.csv` (change-only), `data/candidates.csv`, `data/sgp.csv` |
| `close.py` | after kickoff: `/clv/grade` → `data/clv.csv`; when final: `/results` → `data/results.csv` |
| `report.py` | rollups + verdicts → `docs/index.html` (GitHub Pages) and Telegram text |
| `run.py` | one tick: snapshot → close → report → Telegram cadence |
| `common.py` | API client, CSV store, gates, Telegram |
| `.github/workflows/lab.yml` | cron every 6h, commits data + docs back to the repo |

All data is plain CSV — open in pandas or Excel. `data/state.json` holds bookkeeping (change-detection signatures, closed events, message cadence).

## Telegram

- **Board captured** — once per week, first snapshot with events
- **Weekly summary** — Tuesdays
- **FAILED / warning** — immediately on any error or an empty Thu–Sun snapshot

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
`close.py`) once every leg in it has a graded result. The dashboard's "Slip ledger" card shows the
running count and P&L; `data/slips.csv` is the full record.

## Offline test

```
python3 snapshot.py --from-file ev_sample.json --event-id 32646 --no-sgp
python3 report.py
```

## Known limits

- PropLine's NFL archive starts September 2026 — nothing to backtest; the sample accumulates one week at a time.
- For NFL props the fair-line anchor is usually Kalshi (Pinnacle posts no NFL props). Exchange anchors are thin; that's why the gates require extra books.
- Underdog here prices two-way (~-112/-112), not flat pick'em payouts. H1 tests it as a book, because that's what it is in this feed.
- `lines.csv` grows all season. If the repo gets heavy, move old weeks to a release asset.

## Settlement

A slip leg is graded, in order: the exact result row at the slip's book; the exact row at any book;
otherwise the player's actual stat vs our line (Over/Under legs). The last step matters because when
a line moves before kickoff, books stop listing the number we logged. Voided legs (player didn't play)
are dropped: a straight is refunded, a parlay/SGP pays the remaining legs at their own prices. Any leg
still ungradeable 72 hours after kickoff is voided, so nothing stays open forever.

## Confirming a deploy

`LAB_VERSION` in `common.py` is printed in the public page footer and at the top of `internal.html`.
After uploading new code and running a tick, check that version on the page.
