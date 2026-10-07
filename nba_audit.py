"""NBA Phase 0 read-only PropLine capability audit."""
from __future__ import annotations
import datetime as dt
import json
import os
import pathlib
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter, defaultdict

BASE = "https://api.prop-line.com/v1"
SPORT = "basketball_nba"
CORE_MARKETS = ("player_points", "player_rebounds", "player_assists", "player_threes")
WINDOWS_HOURS = (24.0, 12.0, 8.0, 4.0, 2.0, 1.0, 0.5)
MAX_SAMPLE_EVENTS = int(os.environ.get("NBA_AUDIT_MAX_EVENTS", "5"))
ROOT = pathlib.Path(__file__).resolve().parent
OUT_DIR = ROOT / "research" / "nba"

def iso(t=None):
    return (t or dt.datetime.now(dt.timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ")

def parse_iso(value):
    if not value:
        return None
    try:
        return dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None

def request_json(path, params=None):
    key = os.environ.get("ODDS_API_KEY")
    if not key:
        raise RuntimeError("ODDS_API_KEY not set")
    url = BASE + path
    if params:
        url += "?" + urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
    req = urllib.request.Request(url, headers={"X-API-Key": key, "User-Agent": "prop-lab-nba-audit/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode()
            return {"ok": True, "status": resp.status, "body": json.loads(raw) if raw else None,
                    "headers": {k.lower(): v for k, v in resp.headers.items()}}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode(errors="replace")[:2000]
        try:
            body = json.loads(raw)
        except Exception:
            body = {"raw": raw}
        return {"ok": False, "status": exc.code, "body": body,
                "headers": {k.lower(): v for k, v in exc.headers.items()}}
    except (urllib.error.URLError, TimeoutError) as exc:
        return {"ok": False, "status": None,
                "body": {"error": type(exc).__name__, "message": str(exc)}, "headers": {}}

def walk(obj):
    if isinstance(obj, dict):
        yield obj
        for value in obj.values():
            yield from walk(value)
    elif isinstance(obj, list):
        for value in obj:
            yield from walk(value)

def outcome_rows(payload):
    rows = []
    for node in walk(payload):
        outcomes = node.get("outcomes")
        if not isinstance(outcomes, list):
            continue
        market = node.get("key") or node.get("market") or node.get("market_key") or ""
        for outcome in outcomes:
            if isinstance(outcome, dict):
                row = dict(outcome)
                row["_market"] = market
                rows.append(row)
    return rows

def bookmaker_keys(payload):
    keys = set()
    for node in walk(payload):
        books = node.get("bookmakers")
        if isinstance(books, list):
            for book in books:
                if isinstance(book, dict) and book.get("key"):
                    keys.add(str(book["key"]))
        book = node.get("bookmaker") or node.get("bookmaker_key")
        if isinstance(book, str):
            keys.add(book)
    return sorted(keys)

def market_keys(payload):
    keys = set()
    for node in walk(payload):
        key = node.get("key") or node.get("market") or node.get("market_key")
        if isinstance(key, str) and key.startswith("player_"):
            keys.add(key)
    return sorted(keys)

def recorded_times(payload):
    out = []
    for node in walk(payload):
        for key in ("recorded_at", "timestamp", "ts", "last_seen_at", "last_change_at", "closing_at", "opening_at"):
            parsed = parse_iso(node.get(key))
            if parsed:
                out.append(parsed)
                break
    return sorted(set(out))

def history_window_presence(payload, commence_time, tolerance_minutes=40):
    tip = parse_iso(commence_time)
    result = {f"T-{h:g}h": False for h in WINDOWS_HOURS}
    if not tip:
        return result
    times = recorded_times(payload)
    for hours in WINDOWS_HOURS:
        target = tip - dt.timedelta(hours=hours)
        result[f"T-{hours:g}h"] = any(
            abs((stamp - target).total_seconds()) <= tolerance_minutes * 60 for stamp in times
        )
    return result

def id_coverage(rows):
    return {field: {"present": sum(bool(r.get(field)) for r in rows), "total": len(rows)}
            for field in ("outcome_id", "player_id", "book_outcome_id")}

def classify_verdict(sample_events, history_ok, closing_ok, results_ok):
    if sample_events >= 2 and history_ok and closing_ok and results_ok:
        return "CONDITIONAL PASS"
    if sample_events >= 1 and (history_ok or closing_ok or results_ok):
        return "CONDITIONAL PASS"
    return "BLOCKED"

def quota(headers):
    return {
        "daily_limit": headers.get("x-daily-limit") or headers.get("ratelimit-limit"),
        "daily_used": headers.get("x-daily-used"),
        "daily_remaining": headers.get("x-daily-remaining") or headers.get("ratelimit-remaining"),
        "daily_reset": headers.get("x-daily-reset"),
        "archive_starts": headers.get("x-propline-archive-starts"),
        "export_window_start": headers.get("x-propline-export-window-start"),
    }

def sample_completed(scores):
    if not isinstance(scores, list):
        return []
    rows = [r for r in scores if isinstance(r, dict) and r.get("status") == "final"]
    rows.sort(key=lambda r: str(r.get("commence_time", "")), reverse=True)
    return rows[:MAX_SAMPLE_EVENTS]

def audit_event(event):
    eid = str(event.get("id"))
    markets = ",".join(CORE_MARKETS)
    calls = {
        "markets": request_json(f"/sports/{SPORT}/events/{eid}/markets"),
        "results": request_json(f"/sports/{SPORT}/events/{eid}/results", {"markets": markets}),
        "closing": request_json(f"/sports/{SPORT}/events/{eid}/odds/closing", {"markets": markets}),
        "history": request_json(f"/sports/{SPORT}/events/{eid}/odds/history", {
            "markets": markets, "relative_from": "-24h", "relative_to": "0",
            "interval": "30m", "changes_only": "true"
        }),
    }
    payloads = {name: call["body"] for name, call in calls.items()}
    result_rows = outcome_rows(payloads["results"])
    closing_rows = outcome_rows(payloads["closing"])
    history_rows = outcome_rows(payloads["history"])
    present = sorted(set(market_keys(payloads["markets"])) |
                     set(market_keys(payloads["results"])) |
                     set(market_keys(payloads["closing"])) |
                     set(market_keys(payloads["history"])))
    books = sorted(set(bookmaker_keys(payloads["results"])) |
                   set(bookmaker_keys(payloads["closing"])) |
                   set(bookmaker_keys(payloads["history"])))
    all_rows = result_rows + closing_rows + history_rows
    close_ids = {str(r.get("outcome_id")) for r in closing_rows if r.get("outcome_id")}
    hist_ids = {str(r.get("outcome_id")) for r in history_rows if r.get("outcome_id")}
    joined = []
    for row in result_rows:
        oid = row.get("outcome_id")
        if oid and str(oid) in close_ids and str(oid) in hist_ids:
            joined.append({
                "market": row.get("_market"),
                "player": row.get("description") or row.get("player_name"),
                "side": row.get("name"),
                "point": row.get("point"),
                "resolution": row.get("resolution"),
                "actual_value": row.get("actual_value"),
                "outcome_id": oid,
            })
        if len(joined) >= 4:
            break
    return {
        "event": {k: event.get(k) for k in ("id", "commence_time", "home_team", "away_team", "status")},
        "api": {name: {"ok": call["ok"], "status": call["status"],
                       "error": None if call["ok"] else call["body"],
                       "quota": quota(call["headers"])}
                for name, call in calls.items()},
        "core_markets_present": [m for m in CORE_MARKETS if m in present],
        "all_player_markets_present": present,
        "result_outcomes": len(result_rows),
        "closing_outcomes": len(closing_rows),
        "history_outcomes": len(history_rows),
        "books": books,
        "history_windows": history_window_presence(payloads["history"], event.get("commence_time")),
        "identity": id_coverage(all_rows),
        "end_to_end_joined_examples": joined,
    }

def resolution_summary(body):
    if not isinstance(body, dict):
        return {}
    nba = {}
    for row in body.get("by_sport", []) or []:
        if isinstance(row, dict) and row.get("sport_key") == SPORT:
            nba = row
            break
    return {"days": body.get("days"), "nba": nba, "top_markets": body.get("top_markets", [])}

def run():
    base = {
        "sports": request_json("/sports"),
        "scores": request_json(f"/sports/{SPORT}/scores", {"days_from": 30}),
        "upcoming": request_json(f"/sports/{SPORT}/events"),
        "resolution": request_json("/markets/resolution-summary", {"days": 90}),
    }
    scores = base["scores"]["body"] if isinstance(base["scores"]["body"], list) else []
    completed = sample_completed(scores)
    events = [audit_event(event) for event in completed]
    counts = Counter()
    books = Counter()
    for event in events:
        counts.update(event["core_markets_present"])
        books.update(event["books"])
    history_ok = any(e["api"]["history"]["ok"] and e["history_outcomes"] > 0 for e in events)
    closing_ok = any(e["api"]["closing"]["ok"] and e["closing_outcomes"] > 0 for e in events)
    results_ok = any(e["api"]["results"]["ok"] and e["result_outcomes"] > 0 for e in events)
    finals = [r for r in scores if r.get("status") == "final"]
    headers = next((call["headers"] for call in base.values() if call["headers"]), {})
    sports_body = base["sports"]["body"] if isinstance(base["sports"]["body"], list) else []
    return {
        "phase": "NBA-0",
        "generated_at": iso(),
        "sport": SPORT,
        "scope": "read-only capability audit; no NBA model",
        "verdict": classify_verdict(len(events), history_ok, closing_ok, results_ok),
        "documentation_constraint": "PropLine documentation says NBA graded history begins with the 2026-27 season.",
        "account": {
            "sport_available": any(isinstance(x, dict) and x.get("key") == SPORT for x in sports_body),
            "quota": quota(headers),
            "endpoint_status": {name: {"ok": call["ok"], "status": call["status"]} for name, call in base.items()},
        },
        "event_coverage": {
            "score_rows_30d": len(scores),
            "final_games_30d": len(finals),
            "earliest_final_30d": min((r.get("commence_time") for r in finals if r.get("commence_time")), default=None),
            "latest_final_30d": max((r.get("commence_time") for r in finals if r.get("commence_time")), default=None),
            "sampled_completed_games": len(events),
            "upcoming_events": len(base["upcoming"]["body"]) if isinstance(base["upcoming"]["body"], list) else None,
        },
        "resolution_summary": resolution_summary(base["resolution"]["body"]),
        "core_market_sample_coverage": {m: counts.get(m, 0) for m in CORE_MARKETS},
        "books_seen_in_sample": dict(sorted(books.items())),
        "pinnacle_seen": bool(books.get("pinnacle")),
        "history_access_worked": history_ok,
        "closing_access_worked": closing_ok,
        "results_access_worked": results_ok,
        "events": events,
        "limitations": [
            "No pre-2026-27 NBA graded regular-season archive is expected from PropLine.",
            "Historical endpoint depth is tier-capped by event age.",
            "Preseason is diagnostic only and must never be mixed with formal regular-season evidence.",
            "Repeated snapshots are not independent observations.",
        ],
        "phase1_recommendation": (
            "If recent NBA history, closing lines and results are healthy, begin isolated forward NBA collection now "
            "for main-line player_points, player_rebounds, player_assists and player_threes. Keep preseason diagnostic-only. "
            "At the 2026-27 regular-season opener start a preregistered baseline focused on CLV and calibration, with no selector or SGP."
        ),
    }

def render_markdown(report):
    event_cov = report["event_coverage"]
    lines = [
        "# NBA Phase 0 - Data Capability Audit",
        "",
        "Generated: " + report["generated_at"],
        "",
        "## Verdict: " + report["verdict"],
        "",
        report["documentation_constraint"],
        "",
        "## Account and endpoints",
        "",
        "- NBA sport available: " + str(report["account"]["sport_available"]),
        "- History access worked: " + str(report["history_access_worked"]),
        "- Closing-line access worked: " + str(report["closing_access_worked"]),
        "- Results access worked: " + str(report["results_access_worked"]),
        "- Quota snapshot: " + json.dumps(report["account"]["quota"], sort_keys=True),
        "",
        "## Event coverage",
        "",
        "- Recent score rows (30d): " + str(event_cov["score_rows_30d"]),
        "- Final games (30d): " + str(event_cov["final_games_30d"]),
        "- Earliest final in returned window: " + str(event_cov["earliest_final_30d"] or "unavailable"),
        "- Latest final in returned window: " + str(event_cov["latest_final_30d"] or "unavailable"),
        "- Completed games sampled end-to-end: " + str(event_cov["sampled_completed_games"]),
        "",
        "## Core-market sample coverage",
        "",
    ]
    for market, count in report["core_market_sample_coverage"].items():
        lines.append("- " + market + ": " + str(count) + " sampled games")
    lines += ["", "## Books seen", "", json.dumps(report["books_seen_in_sample"], sort_keys=True),
              "", "Pinnacle seen: " + str(report["pinnacle_seen"]), "", "## Sampled events", ""]
    for event in report["events"]:
        meta = event["event"]
        lines += [
            "### " + str(meta.get("away_team")) + " @ " + str(meta.get("home_team")) + " - " + str(meta.get("commence_time")),
            "- Event id: " + str(meta.get("id")),
            "- Core markets: " + (", ".join(event["core_markets_present"]) or "none"),
            "- Result outcomes: " + str(event["result_outcomes"]),
            "- Closing outcomes: " + str(event["closing_outcomes"]),
            "- Historical outcome rows: " + str(event["history_outcomes"]),
            "- Books: " + (", ".join(event["books"]) or "none"),
            "- History windows: " + json.dumps(event["history_windows"], sort_keys=True),
            "- Identity coverage: " + json.dumps(event["identity"], sort_keys=True),
            "- End-to-end joined examples: " + str(len(event["end_to_end_joined_examples"])),
            "",
        ]
    lines += ["## Resolution summary", "", json.dumps(report["resolution_summary"], indent=2, sort_keys=True),
              "", "## Limitations", ""]
    lines.extend("- " + item for item in report["limitations"])
    lines += ["", "## Recommended NBA Phase 1", "", report["phase1_recommendation"],
              "", "## Human action required", "",
              "None if the existing GitHub ODDS_API_KEY secret can run this audit.",
              "", "Stop here. Do not implement NBA Phase 1 without explicit approval.", ""]
    return "\n".join(lines)

def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    report = run()
    (OUT_DIR / "nba_data_audit.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (OUT_DIR / "NBA_DATA_AUDIT.md").write_text(render_markdown(report), encoding="utf-8")
    print(json.dumps({
        "verdict": report["verdict"],
        "sampled_completed_games": report["event_coverage"]["sampled_completed_games"],
        "history_access_worked": report["history_access_worked"],
        "closing_access_worked": report["closing_access_worked"],
        "results_access_worked": report["results_access_worked"],
        "quota": report["account"]["quota"],
    }, sort_keys=True))

if __name__ == "__main__":
    main()
