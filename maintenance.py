"""maintenance.py — idempotent data-retention cleanup.

Keeps the evidence used by the current experiments while removing rows that can never
enter a model/report. This runs before every scheduled tick so the repo stays bounded.
"""
import csv
import json
import os
from common import *

AUDIT_KEEP_REASONS = {
    "no_dual_confirm_leg",
    "no_sgp_quote",
    "tier_b_not_allowed",
    "nonpositive_pricing_edge",
}


def _mb(path):
    return round(os.path.getsize(path) / (1024 * 1024), 2) if os.path.exists(path) else 0.0


def compact_lines():
    """Drop raw deep-alt / thin-market history that no current model or report can use.

    current_lines.csv remains the complete live board. candidates.csv, CLV, slips and
    frozen decisions are untouched.
    """
    path = csv_path("lines")
    if not os.path.exists(path):
        return {"before_mb": 0, "after_mb": 0, "rows": 0, "kept": 0}
    tmp = path + ".tmp"
    total = kept = 0
    with open(path, newline="") as src, open(tmp, "w", newline="") as dst:
        rd = csv.DictReader(src)
        fields = rd.fieldnames or []
        wr = csv.DictWriter(dst, fieldnames=fields, extrasaction="ignore")
        wr.writeheader()
        for r in rd:
            total += 1
            try:
                fp = float(r.get("fair_prob", ""))
                nb = int(float(r.get("n_books", 0)))
            except (TypeError, ValueError):
                continue
            if not (GATE["fair_min"] <= fp <= GATE["fair_max"]):
                continue
            if nb < GATE["min_books"]:
                continue
            wr.writerow(r)
            kept += 1
    before = _mb(path)
    os.replace(tmp, path)
    return {"before_mb": before, "after_mb": _mb(path), "rows": total, "kept": kept}


def compact_audit():
    """Keep only model-relevant SGP audit rows.

    Structural impossibilities are already counted in the frozen decision note and do
    not need one giant row per impossible pair/model combination.
    """
    path = csv_path("sgp_rejection_audit")
    if not os.path.exists(path):
        return {"before_mb": 0, "after_mb": 0, "rows": 0, "kept": 0}
    before = _mb(path)
    with open(path, newline="") as src:
        rd = csv.DictReader(src)
        fields = rd.fieldnames or []
        latest = {}
        total = 0
        for r in rd:
            total += 1
            approved = str(r.get("approved", "")).lower() in ("true", "1")
            reason = r.get("rejection_reason", "")
            if not approved and reason not in AUDIT_KEEP_REASONS:
                continue
            key = (
                r.get("event_id", ""),
                r.get("model", ""),
                r.get("pair_id", ""),
                r.get("book", ""),
                str(approved),
                reason,
            )
            latest[key] = r
    tmp = path + ".tmp"
    with open(tmp, "w", newline="") as dst:
        wr = csv.DictWriter(dst, fieldnames=fields, extrasaction="ignore")
        wr.writeheader()
        wr.writerows(latest.values())
    os.replace(tmp, path)
    return {"before_mb": before, "after_mb": _mb(path), "rows": total, "kept": len(latest)}


def prune_state():
    """line_sigs only needs keys for events that can still be snapshotted."""
    path = os.path.join(DATA, "state.json")
    if not os.path.exists(path):
        return {"before_mb": 0, "after_mb": 0, "line_sigs": 0, "kept": 0}
    before = _mb(path)
    with open(path) as f:
        state = json.load(f)
    sigs = state.get("line_sigs", {}) or {}
    now = utcnow()
    active = set()
    for e in read_rows("events"):
        try:
            if parse_iso(e.get("commence_time", "")) > now:
                active.add(str(e.get("event_id", "")))
        except Exception:
            continue
    kept = {k: v for k, v in sigs.items() if str(k).split("|", 1)[0] in active}
    state["line_sigs"] = kept
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f, indent=1, sort_keys=True)
    os.replace(tmp, path)
    return {"before_mb": before, "after_mb": _mb(path), "line_sigs": len(sigs), "kept": len(kept)}


def main():
    out = {
        "lines": compact_lines(),
        "sgp_rejection_audit": compact_audit(),
        "state": prune_state(),
    }
    print("maintenance", json.dumps(out, sort_keys=True))


if __name__ == "__main__":
    main()
