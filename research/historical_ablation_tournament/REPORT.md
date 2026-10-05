# Complete historical ablation + selector tournament

**RETROSPECTIVE DEVELOPMENT EVIDENCE ONLY.** Official V1–V8 forward history is unchanged.

Usable Sunday slates: **3**. Historical boards evaluated: **52**.

Future-only tests excluded rather than fabricated: A_FRESH300, A_MAINLINE, steam, and context.

## Benchmark cutoffs

| Slate | Cutoff | Timing | Method | V2 selection |
|---|---|---|---|---|
| 2026-09-20 | 2026-09-20T10:11:49Z | T-8_to_4h | development-aligned | Justin Jefferson U6.5 receptions + Tyler Shough U0.5 pass interceptions |
| 2026-09-27 | 2026-09-27T10:56:13Z | T-8_to_4h | development-aligned | Ladd McConkey U4.5 receptions + Javonte Williams U2.5 receptions |
| 2026-10-04 | 2026-10-04T03:07:18Z | T-12_to_8h | last-committed-pregame | Marcus Mariota O0.5 pass interceptions + Xavier Hutchinson U2.5 receptions |

## Benchmark tournament

| Variant | Plays | W-L | P&L | ROI | Expected W | Brier | Avg EV vs close | Same as V2 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| OFF_V1 | 2 | 1-1 | USD +9.64 | 96.4% | 0.52 | 0.286 | 4.54% | 1/2 (50%) |
| OFF_V2 | 3 | 2-1 | USD +28.29 | 188.6% | 0.79 | 0.396 | 3.77% | 3/3 (100%) |
| OFF_V3 | 3 | 2-1 | USD +28.29 | 188.6% | 0.79 | 0.396 | 3.77% | 3/3 (100%) |
| OFF_V4 | 3 | 2-1 | USD +24.24 | 161.6% | 0.85 | 0.374 | 0.44% | 0/3 (0%) |
| OFF_V5 | 3 | 1-2 | USD +5.44 | 36.3% | 0.89 | 0.241 | 2.46% | 0/3 (0%) |
| OFF_V6 | 2 | 1-1 | USD +9.64 | 96.4% | 0.54 | 0.292 | 3.50% | 0/2 (0%) |
| OFF_V8 | 3 | 2-1 | USD +28.29 | 188.6% | 0.79 | 0.396 | 3.77% | 3/3 (100%) |
| OFF_V8_2 | 2 | 1-1 | USD +14.15 | 141.5% | 0.44 | 0.328 | 0.44% | 0/2 (0%) |
| A_MIN4 | 3 | 2-1 | USD +28.29 | 188.6% | 0.79 | 0.396 | 3.77% | 3/3 (100%) |
| A_NODEPTH | 3 | 1-1 | USD +15.29 | 101.9% | 0.56 | 0.296 | 6.02% | 2/3 (67%) |
| A_FAIR3565 | 3 | 2-1 | USD +28.29 | 188.6% | 0.79 | 0.396 | 3.77% | 3/3 (100%) |
| A_EDGE3 | 3 | 2-1 | USD +28.29 | 188.6% | 0.79 | 0.396 | 3.77% | 3/3 (100%) |
| A_EDGE5 | 3 | 2-1 | USD +28.29 | 188.6% | 0.79 | 0.396 | 3.77% | 3/3 (100%) |
| A_PERSIST2 | 2 | 1-1 | USD +9.64 | 96.4% | 0.54 | 0.292 | 3.50% | 0/2 (0%) |
| A_PERSIST3 | 2 | 1-1 | USD +9.64 | 96.4% | 0.52 | 0.289 | 3.50% | 0/2 (0%) |
| S_MAXEDGE | 3 | 2-1 | USD +28.29 | 188.6% | 0.77 | 0.393 | 2.40% | 2/3 (67%) |
| S_MAXMINP | 3 | 2-1 | USD +28.29 | 188.6% | 0.79 | 0.396 | 3.77% | 3/3 (100%) |
| S_MAXPERSIST | 3 | 2-1 | USD +30.89 | 205.9% | 0.72 | 0.409 | 3.60% | 1/3 (33%) |
| C_NOCONFIRM | 3 | 1-2 | USD +0.16 | 1.1% | 1.08 | 0.226 | 1.44% | 0/3 (0%) |
| C_RANDOM_V2 | 3 | 2-1 | USD +28.29 | 188.6% | 0.77 | 0.394 | 2.40% | 2/3 (67%) |

## Per-slate selections

### 2026-09-20 · 2026-09-20T10:11:49Z · development-aligned

| Variant | Qualified | Pairs | Selection | Result | P&L |
|---|---:|---:|---|---|---:|
| OFF_V1 | 4 | 5 | Justin Jefferson U6.5 receptions + Tyler Shough U0.5 pass interceptions | won | USD +14.64 |
| OFF_V2 | 4 | 5 | Justin Jefferson U6.5 receptions + Tyler Shough U0.5 pass interceptions | won | USD +14.64 |
| OFF_V3 | 5 | 9 | Justin Jefferson U6.5 receptions + Tyler Shough U0.5 pass interceptions | won | USD +14.64 |
| OFF_V4 | 6 | 13 | Chuba Hubbard O13.5 rush attempts + Justin Jefferson U6.5 receptions | lost | USD -5.00 |
| OFF_V5 | 7 | 19 | Chuba Hubbard O13.5 rush attempts + Justin Jefferson U6.5 receptions | lost | USD -5.00 |
| OFF_V6 | 4 | 6 | Caleb Williams U19.5 pass completions + Tyler Shough U0.5 pass interceptions | won | USD +14.64 |
| OFF_V8 | 5 | 9 | Justin Jefferson U6.5 receptions + Tyler Shough U0.5 pass interceptions | won | USD +14.64 |
| OFF_V8_2 | 5 | 9 | Cooper Rush O0.5 rush yds + Malik Washington O3.5 receptions | won | USD +19.15 |
| A_MIN4 | 4 | 5 | Justin Jefferson U6.5 receptions + Tyler Shough U0.5 pass interceptions | won | USD +14.64 |
| A_NODEPTH | 4 | 5 | Justin Jefferson U6.5 receptions + Tyler Shough U0.5 pass interceptions | won | USD +14.64 |
| A_FAIR3565 | 4 | 5 | Justin Jefferson U6.5 receptions + Tyler Shough U0.5 pass interceptions | won | USD +14.64 |
| A_EDGE3 | 4 | 5 | Justin Jefferson U6.5 receptions + Tyler Shough U0.5 pass interceptions | won | USD +14.64 |
| A_EDGE5 | 4 | 5 | Justin Jefferson U6.5 receptions + Tyler Shough U0.5 pass interceptions | won | USD +14.64 |
| A_PERSIST2 | 3 | 3 | Caleb Williams U19.5 pass completions + Tyler Shough U0.5 pass interceptions | won | USD +14.64 |
| A_PERSIST3 | 3 | 3 | Caleb Williams U19.5 pass completions + Tyler Shough U0.5 pass interceptions | won | USD +14.64 |
| S_MAXEDGE | 4 | 5 | Justin Jefferson U6.5 receptions + Tyler Shough U0.5 pass interceptions | won | USD +14.64 |
| S_MAXMINP | 4 | 5 | Justin Jefferson U6.5 receptions + Tyler Shough U0.5 pass interceptions | won | USD +14.64 |
| S_MAXPERSIST | 4 | 5 | Cooper Rush O0.5 rush yds + Caleb Williams U19.5 pass completions | won | USD +17.24 |
| C_NOCONFIRM | 34 | 479 | Juwan Johnson O3.5 receptions + Alec Pierce O2.5 receptions | lost | USD -5.00 |
| C_RANDOM_V2 | 4 | 5 | Justin Jefferson U6.5 receptions + Tyler Shough U0.5 pass interceptions | won | USD +14.64 |

### 2026-09-27 · 2026-09-27T10:56:13Z · development-aligned

| Variant | Qualified | Pairs | Selection | Result | P&L |
|---|---:|---:|---|---|---:|
| OFF_V1 | 1 | 0 | NO PLAY | — | USD +0.00 |
| OFF_V2 | 2 | 1 | Ladd McConkey U4.5 receptions + Javonte Williams U2.5 receptions | won | USD +18.65 |
| OFF_V3 | 3 | 2 | Ladd McConkey U4.5 receptions + Javonte Williams U2.5 receptions | won | USD +18.65 |
| OFF_V4 | 4 | 5 | Dominic Zvada O1.5 field goals made + Ladd McConkey U4.5 receptions | won | USD +15.44 |
| OFF_V5 | 3 | 3 | Dominic Zvada O1.5 field goals made + Ladd McConkey U4.5 receptions | won | USD +15.44 |
| OFF_V6 | 0 | 0 | NO PLAY | — | USD +0.00 |
| OFF_V8 | 3 | 2 | Ladd McConkey U4.5 receptions + Javonte Williams U2.5 receptions | won | USD +18.65 |
| OFF_V8_2 | 3 | 2 | NO PLAY | — | USD +0.00 |
| A_MIN4 | 2 | 1 | Ladd McConkey U4.5 receptions + Javonte Williams U2.5 receptions | won | USD +18.65 |
| A_NODEPTH | 3 | 3 | Emmett Johnson O1.5 receptions + Ladd McConkey U4.5 receptions | won_reduced | USD +5.65 |
| A_FAIR3565 | 2 | 1 | Ladd McConkey U4.5 receptions + Javonte Williams U2.5 receptions | won | USD +18.65 |
| A_EDGE3 | 2 | 1 | Ladd McConkey U4.5 receptions + Javonte Williams U2.5 receptions | won | USD +18.65 |
| A_EDGE5 | 2 | 1 | Ladd McConkey U4.5 receptions + Javonte Williams U2.5 receptions | won | USD +18.65 |
| A_PERSIST2 | 1 | 0 | NO PLAY | — | USD +0.00 |
| A_PERSIST3 | 1 | 0 | NO PLAY | — | USD +0.00 |
| S_MAXEDGE | 2 | 1 | Ladd McConkey U4.5 receptions + Javonte Williams U2.5 receptions | won | USD +18.65 |
| S_MAXMINP | 2 | 1 | Ladd McConkey U4.5 receptions + Javonte Williams U2.5 receptions | won | USD +18.65 |
| S_MAXPERSIST | 2 | 1 | Ladd McConkey U4.5 receptions + Javonte Williams U2.5 receptions | won | USD +18.65 |
| C_NOCONFIRM | 32 | 415 | Marcus Mariota O0.5 pass tds + Harold Fannin Jr. O3.5 receptions | won | USD +10.16 |
| C_RANDOM_V2 | 2 | 1 | Ladd McConkey U4.5 receptions + Javonte Williams U2.5 receptions | won | USD +18.65 |

### 2026-10-04 · 2026-10-04T03:07:18Z · last-committed-pregame

| Variant | Qualified | Pairs | Selection | Result | P&L |
|---|---:|---:|---|---|---:|
| OFF_V1 | 3 | 2 | Marcus Mariota O0.5 pass interceptions + Josh Allen O0.5 pass interceptions | lost | USD -5.00 |
| OFF_V2 | 5 | 9 | Marcus Mariota O0.5 pass interceptions + Xavier Hutchinson U2.5 receptions | lost | USD -5.00 |
| OFF_V3 | 5 | 9 | Marcus Mariota O0.5 pass interceptions + Xavier Hutchinson U2.5 receptions | lost | USD -5.00 |
| OFF_V4 | 10 | 41 | Chase McLaughlin U1.5 field goals made + Chris Bell U2.5 receptions | won | USD +13.80 |
| OFF_V5 | 13 | 73 | Chase McLaughlin U1.5 field goals made + Kenneth Walker III O2.5 receptions | lost | USD -5.00 |
| OFF_V6 | 3 | 3 | Xavier Hutchinson U2.5 receptions + Jauan Jennings O2.5 receptions | lost | USD -5.00 |
| OFF_V8 | 5 | 9 | Marcus Mariota O0.5 pass interceptions + Xavier Hutchinson U2.5 receptions | lost | USD -5.00 |
| OFF_V8_2 | 5 | 9 | Josh Allen O0.5 pass interceptions + Jauan Jennings O2.5 receptions | lost | USD -5.00 |
| A_MIN4 | 5 | 9 | Marcus Mariota O0.5 pass interceptions + Xavier Hutchinson U2.5 receptions | lost | USD -5.00 |
| A_NODEPTH | 6 | 14 | Marcus Mariota O0.5 pass interceptions + Xavier Hutchinson U2.5 receptions | lost | USD -5.00 |
| A_FAIR3565 | 5 | 9 | Marcus Mariota O0.5 pass interceptions + Xavier Hutchinson U2.5 receptions | lost | USD -5.00 |
| A_EDGE3 | 5 | 9 | Marcus Mariota O0.5 pass interceptions + Xavier Hutchinson U2.5 receptions | lost | USD -5.00 |
| A_EDGE5 | 5 | 9 | Marcus Mariota O0.5 pass interceptions + Xavier Hutchinson U2.5 receptions | lost | USD -5.00 |
| A_PERSIST2 | 3 | 3 | Xavier Hutchinson U2.5 receptions + Jauan Jennings O2.5 receptions | lost | USD -5.00 |
| A_PERSIST3 | 2 | 1 | Tyler Warren U5.5 receptions + Jauan Jennings O2.5 receptions | lost | USD -5.00 |
| S_MAXEDGE | 5 | 9 | Xavier Hutchinson U2.5 receptions + Jauan Jennings O2.5 receptions | lost | USD -5.00 |
| S_MAXMINP | 5 | 9 | Marcus Mariota O0.5 pass interceptions + Xavier Hutchinson U2.5 receptions | lost | USD -5.00 |
| S_MAXPERSIST | 5 | 9 | Tyler Warren U5.5 receptions + Jauan Jennings O2.5 receptions | lost | USD -5.00 |
| C_NOCONFIRM | 53 | 1183 | Trey McBride U7.5 receptions + Quentin Johnston O2.5 receptions | lost | USD -5.00 |
| C_RANDOM_V2 | 5 | 9 | Marcus Mariota O0.5 pass interceptions + Jauan Jennings O2.5 receptions | lost | USD -5.00 |

## Guardrails

- Three Sunday slates are far too few to promote a model from P&L alone.
- Sep 20 and Sep 27 are development-era data, not out-of-sample evidence.
- Oct 4 uses the last committed pregame board because the intended freeze was lost.
- Repeated snapshots are correlated observations, not independent bets.
- Prefer calibration, CLV, selection stability, and matched controls over raw W/L.
