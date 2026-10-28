# V1–V8 full-history bridge

Generated: **2026-10-28T16:56:12Z** · LAB_VERSION **2026-10-28-v1-v8-full-history-bridge-v1**

**Purpose:** restore one continuous V1–V8 record. The historical reconstruction ends where frozen forward decisions begin. SGP remains additive and separate.

## Pricing warning

Cross-game ticket P&L is hypothetical whenever pricing_status=reconstructed_independent_product.

## Coverage

| Sunday | Status | Events | Candidate snapshots | Board/cutoff |
|---|---|---:|---:|---|
| 2026-09-20 | historical_reconstruction | 14 | 13 | 2026-09-20T10:11:49Z |
| 2026-09-27 | historical_reconstruction | 14 | 17 | 2026-09-27T10:56:13Z |
| 2026-10-04 | historical_reconstruction | 14 | 23 | 2026-10-04T03:07:18Z |
| 2026-10-11 | forward_frozen | 13 | 24 | 2026-10-11T13:15:38Z |
| 2026-10-18 | forward_frozen | 12 | 15 | 2026-10-18T17:28:46Z |
| 2026-10-25 | forward_frozen | 12 | 31 | 2026-10-25T14:31:17Z |
| 2026-11-01 | future | 12 | 2 | — |

## Model record

| Model | Hist plays | Forward plays | W-L | Void | Hit | Hypothetical P&L | ROI | Actual-quote tickets |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| V1 | 2 | 0 | 1-1 | 0 | 50.0% | $+9.64 | 96.4% | 0 |
| V2 | 3 | 1 | 2-2 | 0 | 50.0% | $+23.29 | 116.5% | 0 |
| V3 | 3 | 1 | 2-2 | 0 | 50.0% | $+23.29 | 116.5% | 0 |
| V4 | 3 | 3 | 5-1 | 0 | 83.3% | $+52.53 | 175.1% | 0 |
| V5 | 3 | 1 | 1-3 | 0 | 25.0% | $+0.44 | 2.2% | 0 |
| V6 | 2 | 0 | 1-1 | 0 | 50.0% | $+9.64 | 96.4% | 0 |
| V7 | 0 | 0 | 0-0 | 0 | — | $+0.00 | — | 0 |
| V8 | 5 | 1 | 3-3 | 0 | 50.0% | $+37.44 | 124.8% | 0 |

## Deduplicated execution record

Unique execution tickets: **16** · settled **16** · record **9-7** · voids **0** · hypothetical P&L **$+89.61**.

Identical tickets selected by multiple V-models count once here.

| Evidence phase | Unique tickets | W-L | Hit | Hypothetical P&L | ROI |
|---|---:|---:|---:|---:|---:|
| Historical reconstruction | 12 | 6-6 | 50.0% | $+66.32 | 110.5% |
| Frozen forward | 4 | 3-1 | 75.0% | $+23.29 | 116.5% |

| Sunday | Models | Ticket | Result | Price | Pricing | P&L |
|---|---|---|---|---:|---|---:|
| 2026-09-20 | V4,V5 | Chuba Hubbard O13.5 rush attempts + Justin Jefferson U6.5 receptions | lost | 274 | reconstructed_independent_product | $-5.00 |
| 2026-09-20 | V8 | Cooper Rush O0.5 rush yds + Malik Washington O3.5 receptions | won | 383 | reconstructed_independent_product | $+19.15 |
| 2026-09-20 | V6 | Caleb Williams U19.5 pass completions + Tyler Shough U0.5 pass interceptions | won | 293 | reconstructed_independent_product | $+14.64 |
| 2026-09-20 | V1,V2,V3,V8 | Justin Jefferson U6.5 receptions + Tyler Shough U0.5 pass interceptions | won | 293 | reconstructed_independent_product | $+14.64 |
| 2026-09-27 | V2,V3,V8 | Ladd McConkey U4.5 receptions + Javonte Williams U2.5 receptions | won | 373 | reconstructed_independent_product | $+18.65 |
| 2026-09-27 | V4,V5 | Dominic Zvada O1.5 field goals made + Ladd McConkey U4.5 receptions | won | 309 | reconstructed_independent_product | $+15.44 |
| 2026-10-04 | V2,V3,V8 | Marcus Mariota O0.5 pass interceptions + Xavier Hutchinson U2.5 receptions | lost | 290 | reconstructed_independent_product | $-5.00 |
| 2026-10-04 | V1 | Marcus Mariota O0.5 pass interceptions + Josh Allen O0.5 pass interceptions | lost | 351 | reconstructed_independent_product | $-5.00 |
| 2026-10-04 | V4 | Chase McLaughlin U1.5 field goals made + Chris Bell U2.5 receptions | won | 276 | reconstructed_independent_product | $+13.80 |
| 2026-10-04 | V5 | Chase McLaughlin U1.5 field goals made + Kenneth Walker III O2.5 receptions | lost | 238 | reconstructed_independent_product | $-5.00 |
| 2026-10-04 | V6 | Xavier Hutchinson U2.5 receptions + Jauan Jennings O2.5 receptions | lost | 320 | reconstructed_independent_product | $-5.00 |
| 2026-10-04 | V8 | Josh Allen O0.5 pass interceptions + Jauan Jennings O2.5 receptions | lost | 383 | reconstructed_independent_product | $-5.00 |
| 2026-10-11 | V4 | Makai Lemon O3.5 receptions + Jahmyr Gibbs O19.5 rush attempts | won | 304 | reconstructed_independent_product | $+15.20 |
| 2026-10-18 | V4 | Puka Nacua U2.5 rush yds + Jordan Love U1.5 pass tds | won | 399 | reconstructed_independent_product | $+8.50 |
| 2026-10-25 | V4 | Tyjae Spears O2.5 receptions + Elijah Higgins O12.5 reception yds | won | 339 | reconstructed_independent_product | $+4.59 |
| 2026-10-25 | V2,V3,V5,V8 | Jahan Dotson O2.5 receptions + Elijah Higgins O12.5 reception yds | lost | 377 | reconstructed_independent_product | $-5.00 |

## Evidence boundaries

- Historical rows are retrospective development evidence, not forward validation.
- Frozen forward rows are never replaced by retrospective reconstruction on the same date.
- V7 remains blocked until actual cross-game parlay quote capture exists.
- A winning/losing ticket result is real when settled, but P&L is hypothetical if its ticket price was reconstructed.
- SGP results live in their own family and do not replace or pause V1–V8.
