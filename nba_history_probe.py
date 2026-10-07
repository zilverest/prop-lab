"""Capture one NBA event's raw API shapes for Phase 1 replay engineering."""
import json
import os
import pathlib
from nba_audit import request_json, SPORT, CORE_MARKETS

OUT = pathlib.Path("research/nba/probe")
EVENT_ID = os.environ.get("NBA_PROBE_EVENT_ID", "317856")

def main():
    OUT.mkdir(parents=True, exist_ok=True)
    markets = ",".join(CORE_MARKETS)
    calls = {
        "history": request_json(f"/sports/{SPORT}/events/{EVENT_ID}/odds/history", {
            "markets": markets,
            "relative_from": "-24h",
            "relative_to": "0",
            "interval": "30m",
            "changes_only": "false",
        }),
        "closing": request_json(f"/sports/{SPORT}/events/{EVENT_ID}/odds/closing", {"markets": markets}),
        "results": request_json(f"/sports/{SPORT}/events/{EVENT_ID}/results", {"markets": markets}),
    }
    summary = {}
    for name, call in calls.items():
        body = call.get("body")
        (OUT / f"{name}.json").write_text(json.dumps(body, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        summary[name] = {
            "ok": call.get("ok"),
            "status": call.get("status"),
            "type": type(body).__name__,
            "top_keys": sorted(body.keys()) if isinstance(body, dict) else None,
            "rows": len(body) if isinstance(body, list) else None,
        }
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, sort_keys=True))

if __name__ == "__main__":
    main()
