# NBA Phase 0 - Data Capability Audit

Generated: 2026-10-07T21:30:00Z

## Verdict: CONDITIONAL PASS

PropLine documentation says NBA graded history begins with the 2026-27 season.

## Account and endpoints

- NBA sport available: True
- History access worked: True
- Closing-line access worked: True
- Results access worked: True
- Quota snapshot: {"archive_starts": null, "daily_limit": "5000", "daily_remaining": "4797", "daily_reset": "1791417600", "daily_used": "203", "export_window_start": null}

## Event coverage

- Recent score rows (30d): 91
- Final games (30d): 12
- Earliest final in returned window: 2026-10-03T23:00:00Z
- Latest final in returned window: 2026-10-07T02:00:00Z
- Completed games sampled end-to-end: 5

## Core-market sample coverage

- player_points: 5 sampled games
- player_rebounds: 4 sampled games
- player_assists: 4 sampled games
- player_threes: 4 sampled games

## Books seen

{"bovada": 2, "courtside": 1, "fanatics": 4, "fanduel": 3, "novig": 5, "pick6": 5, "prophetx": 5, "underdog": 5}

Pinnacle seen: False

## Sampled events

### Los Angeles Lakers @ Golden State Warriors - 2026-10-07T02:00:00Z
- Event id: 317856
- Core markets: player_points, player_rebounds, player_assists, player_threes
- Result outcomes: 300
- Closing outcomes: 300
- Historical outcome rows: 300
- Books: bovada, fanatics, fanduel, novig, pick6, prophetx, underdog
- History windows: {"T-0.5h": true, "T-12h": true, "T-1h": true, "T-24h": false, "T-2h": true, "T-4h": true, "T-8h": true}
- Identity coverage: {"book_outcome_id": {"present": 0, "total": 900}, "outcome_id": {"present": 900, "total": 900}, "player_id": {"present": 300, "total": 900}}
- End-to-end joined examples: 4

### Denver Nuggets @ Utah Jazz - 2026-10-07T01:00:00Z
- Event id: 318754
- Core markets: player_points, player_rebounds, player_assists, player_threes
- Result outcomes: 300
- Closing outcomes: 300
- Historical outcome rows: 300
- Books: bovada, fanatics, fanduel, novig, pick6, prophetx, underdog
- History windows: {"T-0.5h": true, "T-12h": false, "T-1h": true, "T-24h": false, "T-2h": true, "T-4h": true, "T-8h": true}
- Identity coverage: {"book_outcome_id": {"present": 0, "total": 900}, "outcome_id": {"present": 900, "total": 900}, "player_id": {"present": 300, "total": 900}}
- End-to-end joined examples: 4

### New Orleans Pelicans @ Oklahoma City Thunder - 2026-10-07T00:00:00Z
- Event id: 318155
- Core markets: player_points, player_rebounds, player_assists, player_threes
- Result outcomes: 311
- Closing outcomes: 311
- Historical outcome rows: 311
- Books: courtside, fanatics, fanduel, novig, pick6, prophetx, underdog
- History windows: {"T-0.5h": true, "T-12h": true, "T-1h": true, "T-24h": false, "T-2h": true, "T-4h": true, "T-8h": true}
- Identity coverage: {"book_outcome_id": {"present": 0, "total": 933}, "outcome_id": {"present": 933, "total": 933}, "player_id": {"present": 311, "total": 933}}
- End-to-end joined examples: 4

### Brooklyn Nets @ Charlotte Hornets - 2026-10-06T23:00:00Z
- Event id: 317333
- Core markets: player_points, player_rebounds, player_assists, player_threes
- Result outcomes: 235
- Closing outcomes: 235
- Historical outcome rows: 235
- Books: fanatics, novig, pick6, prophetx, underdog
- History windows: {"T-0.5h": true, "T-12h": false, "T-1h": true, "T-24h": false, "T-2h": true, "T-4h": true, "T-8h": true}
- Identity coverage: {"book_outcome_id": {"present": 0, "total": 705}, "outcome_id": {"present": 705, "total": 705}, "player_id": {"present": 235, "total": 705}}
- End-to-end joined examples: 4

### Los Angeles Lakers @ Sacramento Kings - 2026-10-06T02:00:00Z
- Event id: 318158
- Core markets: player_points
- Result outcomes: 28
- Closing outcomes: 28
- Historical outcome rows: 28
- Books: novig, pick6, prophetx, underdog
- History windows: {"T-0.5h": true, "T-12h": true, "T-1h": true, "T-24h": false, "T-2h": false, "T-4h": true, "T-8h": false}
- Identity coverage: {"book_outcome_id": {"present": 0, "total": 84}, "outcome_id": {"present": 84, "total": 84}, "player_id": {"present": 28, "total": 84}}
- End-to-end joined examples: 4

## Resolution summary

{
  "days": null,
  "nba": {},
  "top_markets": []
}

## Limitations

- No pre-2026-27 NBA graded regular-season archive is expected from PropLine.
- Historical endpoint depth is tier-capped by event age.
- Preseason is diagnostic only and must never be mixed with formal regular-season evidence.
- Repeated snapshots are not independent observations.

## Recommended NBA Phase 1

If recent NBA history, closing lines and results are healthy, begin isolated forward NBA collection now for main-line player_points, player_rebounds, player_assists and player_threes. Keep preseason diagnostic-only. At the 2026-27 regular-season opener start a preregistered baseline focused on CLV and calibration, with no selector or SGP.

## Human action required

None if the existing GitHub ODDS_API_KEY secret can run this audit.

Stop here. Do not implement NBA Phase 1 without explicit approval.
