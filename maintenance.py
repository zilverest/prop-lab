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
    """Migrate the legacy monolithic change-only archive into daily CSV shards.

    Preserve every originally retained row. Frozen decisions, candidate ledgers,
    live current_lines and CLV archives remain untouched. Future captures append
    directly to data/lines/YYYY-MM-DD.csv, so no >100 MB single Git blob can form.
    """
    path=csv_path("lines")
    if not os.path.exists(path):
        return {"before_mb": 0, "after_mb": 0, "rows": 0, "kept": 0, "mode": "partitioned"}
    before=_mb(path)
    import tempfile
    import shutil
    output_dir=os.path.join(DATA,"lines")
    os.makedirs(output_dir,exist_ok=True)
    total=kept=0
    # No in-place partial migration; create all shards in temporary storage first.
    temp_dir=tempfile.mkdtemp(prefix=".lines-migrate-",dir=DATA)
    try:
        handles={}
        try:
            with open(path,newline="") as src:
                rd=csv.DictReader(src)
                fields=rd.fieldnames or []
                if not fields or "ts" not in fields:
                    raise ValueError("legacy lines.csv has no valid header")
                for row in rd:
                    total+=1
                    stamp=str(row.get("ts",""))
                    if len(stamp)<10 or stamp[4]!="-" or stamp[7]!="-":
                        raise ValueError(f"invalid timestamp in lines.csv at row {total}")
                    date=stamp[:10]
                    # Existing compact_lines() only retained this quality universe.
                    # Preserve every current row regardless of its score or age.
                    if date not in handles:
                        fp=open(os.path.join(temp_dir,date+".csv"),"w",newline="")
                        w=csv.DictWriter(fp,fieldnames=fields,extrasaction="ignore")
                        w.writeheader()
                        handles[date]=(fp,w)
                    handles[date][1].writerow(row)
                    kept+=1
        finally:
            for fp,_ in handles.values():
                fp.close()
        # If any output already exists, refuse to overwrite or double-count history.
        conflicts=[fn for fn in os.listdir(temp_dir) if os.path.exists(os.path.join(output_dir,fn))]
        if conflicts:
            raise RuntimeError("line partition already exists: "+", ".join(conflicts[:3]))
        sizes=[(fn,os.path.getsize(os.path.join(temp_dir,fn))) for fn in os.listdir(temp_dir)]
        limit=80*1024*1024
        oversized=[fn for fn,sz in sizes if sz>=limit]
        if oversized:
            raise RuntimeError("line date partition exceeds safe Git size: "+", ".join(oversized[:3]))
        for fn,_ in sizes:
            os.replace(os.path.join(temp_dir,fn),os.path.join(output_dir,fn))
        os.remove(path)
        return {"before_mb": before, "after_mb": 0, "rows": total,
                "kept": kept, "partitions": len(sizes), "mode": "migrated"}
    finally:
        shutil.rmtree(temp_dir,ignore_errors=True)


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
