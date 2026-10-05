# Sunday 2026-10-04 retrospective replay

**Status:** missed forward freeze due infrastructure failure. This replay uses only data committed before kickoff. It is diagnostic, not forward-validation evidence.

Last committed pregame cutoff: **2026-10-04T03:07:18Z**. Intended ~08:00 ET freeze data was not committed, so no retrospective result is labeled official.

## Cross-game model ladder at last committed board

| Model | Qualified legs | Positive-edge pairs | Selected | Result |
|---|---:|---:|---|---|
| V1 | 3 | 2 | Marcus Mariota O0.5 pass interceptions + Josh Allen O0.5 pass interceptions | lost (-5.0) |
| V2 | 5 | 9 | Marcus Mariota O0.5 pass interceptions + Xavier Hutchinson U2.5 receptions | lost (-5.0) |
| V3 | 5 | 9 | Marcus Mariota O0.5 pass interceptions + Xavier Hutchinson U2.5 receptions | lost (-5.0) |
| V4 | 10 | 41 | Chris Bell U2.5 receptions + Chase McLaughlin U1.5 field goals made | won (13.8) |
| V5 | 13 | 73 | Kenneth Walker III O2.5 receptions + Chase McLaughlin U1.5 field goals made | lost (-5.0) |
| V6 | 4 | 6 | Tyler Warren U5.5 receptions + Xavier Hutchinson U2.5 receptions | lost (-5.0) |
| V7 | 0 | 0 | NO PLAY | — |
| V8 | 5 | 9 | Marcus Mariota O0.5 pass interceptions + Xavier Hutchinson U2.5 receptions<br>Josh Allen O0.5 pass interceptions + Jauan Jennings O2.5 receptions | lost (-5.0)<br>lost (-5.0) |

## Selection stability across committed pregame snapshots

| Cutoff | V1 | V2 | V3 | V4 | V5 | V6 | V8 |
|---|---|---|---|---|---|---|---|
| 2026-10-03T10:43:53Z | Jordan Love + Kirk Cousins | Jordan Love + Kirk Cousins | Jordan Love + Kirk Cousins | Chris Bell + Chase McLaughlin | Kenneth Walker III + Chase McLaughlin | NO PLAY | Jordan Love + Kirk Cousins |
| 2026-10-03T15:19:05Z | Jordan Love + Kirk Cousins | Jordan Love + Kirk Cousins | Jordan Love + Kirk Cousins | Chris Bell + Chase McLaughlin | Kenneth Walker III + Darius Slayton | NO PLAY | Jordan Love + Kirk Cousins / Tyler Warren + Davante Adams |
| 2026-10-03T20:17:11Z | Jordan Love + Kirk Cousins | Jordan Love + Kirk Cousins | Jordan Love + Kirk Cousins | Kirk Cousins + Chase McLaughlin | Darius Slayton + Chase McLaughlin | NO PLAY | Jordan Love + Kirk Cousins |
| 2026-10-04T03:07:18Z | Marcus Mariota + Josh Allen | Marcus Mariota + Xavier Hutchinson | Marcus Mariota + Xavier Hutchinson | Chris Bell + Chase McLaughlin | Kenneth Walker III + Chase McLaughlin | Tyler Warren + Xavier Hutchinson | Marcus Mariota + Xavier Hutchinson / Josh Allen + Jauan Jennings |

## Unique selected slips at the final committed board

1. **V1**: Marcus Mariota O0.5 pass interceptions + Josh Allen O0.5 pass interceptions | draftkings reconstructed +351 | fair 23.8% | edge +7.2% | **LOST**
2. **V2, V3, V8**: Marcus Mariota O0.5 pass interceptions + Xavier Hutchinson U2.5 receptions | bovada reconstructed +290 | fair 27.5% | edge +7.5% | **LOST**
3. **V4**: Chris Bell U2.5 receptions + Chase McLaughlin U1.5 field goals made | draftkings reconstructed +276 | fair 28.7% | edge +8.0% | **WON**
4. **V5**: Kenneth Walker III O2.5 receptions + Chase McLaughlin U1.5 field goals made | hardrock reconstructed +238 | fair 32.9% | edge +11.1% | **LOST**
5. **V6**: Tyler Warren U5.5 receptions + Xavier Hutchinson U2.5 receptions | bovada reconstructed +320 | fair 26.2% | edge +10.2% | **LOST**
6. **V8**: Josh Allen O0.5 pass interceptions + Jauan Jennings O2.5 receptions | bovada reconstructed +383 | fair 22.3% | edge +7.5% | **LOST**

## SGP true-correlation funnel at final committed board

- Verified same-team candidate pairs: **116398**
- S2 quality + dual-confirm pairs reaching pre-quote stage: **14**
- Tier-A core-quality pairs: **640**
- Tier-A + dual-confirm pairs: **3**
- Tier-A/B broad core-quality pairs: **1350**

Actual Sunday SGP prices were never frozen, so S2/S3-A/B/C/D/E cannot be called finalized slips. The report records which pairs reached the pre-quote funnel and their eventual outcomes only.

## Interpretation guardrail

Sunday is one retrospective slate and the same underlying legs create many correlated pairs. Pair counts are therefore not independent samples. Use the ladder to diagnose filter strictness and use CLV/forward results, not one Sunday's W/L, to judge edge.
