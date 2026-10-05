#!/usr/bin/env python3
"""Retrospective Sunday 2026-10-04 replay from committed pregame data only.

Purpose:
- Reconstruct the cross-game V1-V8 model ladder at every committed Sunday pregame snapshot.
- Grade the selected pairs against results.csv.
- Inspect CLV for selected underlying legs.
- Reconstruct the SGP true-correlation PRE-QUOTE funnel. We intentionally do not call
  historical /sgp pricing after the fact, so SGP rows are contenders, not finalized plays.

This is diagnostic only. It never writes parlay_decisions.csv or sgp_shadow_decisions.csv.
"""
from __future__ import annotations

import csv
import json
import os
import sys
from collections import defaultdict
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from common import *  # noqa
import parlay_lab
import sgp_shadow
import slips

TARGET_DATE = "2026-10-04"
NY = ZoneInfo("America/New_York")
OUT_DIR = ROOT / "research" / "sunday_2026_10_04_replay"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# These are the clean committed snapshots visible in sgp_shadow_boards.csv before Sunday kickoff.
# 03:07Z is the final committed board before the failed Sunday morning freeze.
REQUESTED_CUTOFFS = [
    "2026-10-03T10:43:53Z",
    "2026-10-03T15:19:05Z",
    "2026-10-03T20:17:11Z",
    "2026-10-04T03:07:18Z",
]


def sunday_events():
    out = {}
    for e in read_rows("events"):
        try:
            d = parse_iso(e["commence_time"]).astimezone(NY).date().isoformat()
        except Exception:
            continue
        if d == TARGET_DATE:
            out[e["event_id"]] = e
    return out


def reconstruct_snapshots(event_ids, cutoffs):
    """Latest change-only line state at each cutoff, built in one streaming pass."""
    cut_dt = [parse_iso(x) for x in cutoffs]
    states = [dict() for _ in cutoffs]
    p = csv_path("lines")
    with open(p, newline="") as f:
        for r in csv.DictReader(f):
            if r.get("event_id") not in event_ids:
                continue
            try:
                ts = parse_iso(r["ts"])
            except Exception:
                continue
            key = parlay_lab._line_key(r)
            for i, c in enumerate(cut_dt):
                if ts <= c:
                    states[i][key] = r
    return [list(x.values()) for x in states]


def universe_from_rows(rows):
    all_by_leg = defaultdict(dict)
    gated_by_leg = defaultdict(dict)
    for r in rows:
        all_by_leg[parlay_lab._leg_key(r)][r["book"]] = r
        if parlay_lab._passes_gate(r) and r.get("fair_source") == "pinnacle":
            gated_by_leg[parlay_lab._leg_key(r)][r["book"]] = r
    return gated_by_leg, all_by_leg


def grade_leg(grader, leg, book=""):
    return grader.leg(
        {"market": leg["market"], "player": leg["player"], "point": leg["point"], "side": leg["side"]},
        leg["event_id"],
        book,
    )


def grade_pair(grader, pair):
    a, b = pair["a"], pair["b"]
    ra = grade_leg(grader, a, pair.get("book", ""))
    rb = grade_leg(grader, b, pair.get("book", ""))
    res = [ra, rb]
    if "lost" in res:
        result, pnl = "lost", -STAKE_USD
    elif any(x is None for x in res):
        result, pnl = "ungraded", None
    else:
        live = []
        if ra == "won":
            live.append(pair["price_a"])
        if rb == "won":
            live.append(pair["price_b"])
        if not live:
            result, pnl = ("void" if all(x == "void" for x in res) else "push"), 0.0
        elif len(live) == 2:
            result = "won"
            pnl = (pair["decimal"] - 1) * STAKE_USD
        else:
            result = "won_reduced"
            pnl = (am_to_dec(int(live[0])) - 1) * STAKE_USD
    return {
        "leg_results": res,
        "resolution": result,
        "pnl": None if pnl is None else round(pnl, 2),
    }


def pair_json(pair, grader):
    g = grade_pair(grader, pair)
    return {
        "book": pair["book"],
        "price": pair["price"],
        "fair_joint_prob": round(pair["joint"], 6),
        "break_even_prob": round(pair["break_even"], 6),
        "model_edge_pct": round(pair["edge"], 3),
        "legs": [
            {
                "event_id": pair["a"]["event_id"],
                "player": pair["a"]["player"],
                "market": pair["a"]["market"],
                "side": pair["a"]["side"],
                "point": pair["a"]["point"],
                "fair_prob": round(pair["a"]["fair_prob"], 6),
                "price": pair["price_a"],
            },
            {
                "event_id": pair["b"]["event_id"],
                "player": pair["b"]["player"],
                "market": pair["b"]["market"],
                "side": pair["b"]["side"],
                "point": pair["b"]["point"],
                "fair_prob": round(pair["b"]["fair_prob"], 6),
                "price": pair["price_b"],
            },
        ],
        **g,
    }


def clv_index():
    idx = defaultdict(list)
    for r in read_rows("clv"):
        k = (r.get("event_id"), r.get("market"), r.get("player"), str(r.get("point", "")), r.get("side"))
        idx[k].append(r)
    return idx


def clv_for_leg(idx, leg, preferred_book=""):
    k = (leg["event_id"], leg["market"], leg["player"], str(leg["point"]), leg["side"])
    rows = idx.get(k, [])
    if not rows:
        return None
    r = next((x for x in rows if x.get("book") == preferred_book), None)
    if r is None:
        r = next((x for x in rows if x.get("matched") in ("True", "true", "1")), rows[0])
    def f(x):
        try:
            return float(x)
        except Exception:
            return None
    return {
        "book": r.get("book", ""),
        "matched": r.get("matched", ""),
        "beat_close": r.get("beat_close", ""),
        "clv_pct": f(r.get("clv_pct")),
        "ev_vs_close_pct": f(r.get("ev_vs_close_pct")),
        "closing_is_final": r.get("closing_is_final", ""),
    }


def model_replay(rows, grader, clv):
    gated, all_by_leg = universe_from_rows(rows)
    out = {}
    for model in parlay_lab.RESEARCH_MODELS:
        result = parlay_lab.evaluate_model(model, gated, all_by_leg)
        selections = [pair_json(p, grader) for p in result["selections"]]
        for s in selections:
            s["clv"] = [clv_for_leg(clv, l, s["book"]) for l in s["legs"]]

        ladder_model = "V3" if model == "V8" else model
        eligible = [] if model == "V7" else parlay_lab._eligible_legs(ladder_model, gated)
        pairs = [] if model == "V7" else [p for p in parlay_lab._pairs(eligible, all_by_leg) if p["edge"] > 0]
        pair_grades = [grade_pair(grader, p)["resolution"] for p in pairs]
        leg_grades = [grade_leg(grader, l, "") for l in eligible]

        out[model] = {
            "qualified_legs": result["qualified_legs"],
            "valid_pairs": result["valid_pairs"],
            "selections": selections,
            "all_valid_pairs_settled": sum(x in ("won", "won_reduced", "lost", "push", "void") for x in pair_grades),
            "all_valid_pairs_won": sum(x in ("won", "won_reduced") for x in pair_grades),
            "eligible_legs_settled": sum(x in ("won", "lost", "push", "void") for x in leg_grades),
            "eligible_legs_won": sum(x == "won" for x in leg_grades),
            "eligible_legs_lost": sum(x == "lost" for x in leg_grades),
            "note": result.get("note", ""),
        }
    return out


def candidate_pair_to_dict(p, grader):
    q, c = p.get("qb", {}), p.get("catcher", {})
    book = ""
    legs = [
        {"event_id": q.get("event_id"), "market": q.get("market"), "player": q.get("player"), "point": q.get("point"), "side": q.get("side")},
        {"event_id": c.get("event_id"), "market": c.get("market"), "player": c.get("player"), "point": c.get("point"), "side": c.get("side")},
    ]
    gr = [grade_leg(grader, x, book) for x in legs]
    if "lost" in gr:
        res = "lost"
    elif any(x is None for x in gr):
        res = "ungraded"
    elif all(x == "won" for x in gr):
        res = "won"
    elif "won" in gr:
        res = "won_with_void_or_push"
    else:
        res = "void_or_push"
    return {
        "pair_id": p.get("pair_id", ""),
        "qb": q.get("player", ""),
        "catcher": c.get("player", ""),
        "qb_market": q.get("market", ""),
        "qb_side": q.get("side", ""),
        "qb_point": q.get("point", ""),
        "catcher_market": c.get("market", ""),
        "catcher_side": c.get("side", ""),
        "catcher_point": c.get("point", ""),
        "archetype": p.get("archetype", ""),
        "tier": p.get("tier", ""),
        "position": p.get("position", ""),
        "dual_confirm": bool(p.get("dual_confirm")),
        "core_quality": bool(p.get("core_quality")),
        "independent_prob": p.get("independent_prob"),
        "model_prob": p.get("model_prob"),
        "result": res,
        "leg_results": gr,
    }


def sgp_prequote(rows, grader):
    """Reconstruct candidate funnels only. No retrospective quote fabrication."""
    roster_idx = sgp_shadow._roster_index()
    priors = sgp_shadow._load_priors()
    by_event = defaultdict(list)
    for r in rows:
        by_event[r["event_id"]].append(r)

    totals = defaultdict(int)
    top = {"S2": [], "S3-B": [], "S3-D": [], "S3-E": []}
    event_detail = {}

    for eid, erows in by_event.items():
        try:
            u = sgp_shadow._candidate_universe(eid, erows, roster_idx, priors)
        except Exception as e:
            event_detail[eid] = {"error": f"{type(e).__name__}: {e}"}
            continue
        true = [p for p in u["true"] if p.get("relation") == "same_team"]
        s2 = [p for p in true if p.get("core_quality") and p.get("dual_confirm")]
        a = [p for p in true if p.get("core_quality") and p.get("tier") == "A"]
        a_dual = [p for p in a if p.get("dual_confirm")]
        broad = [p for p in true if p.get("core_quality") and p.get("tier") in ("A", "B")]
        totals["verified_same_team"] += len(true)
        totals["s2_prequote"] += len(s2)
        totals["tier_a"] += len(a)
        totals["tier_a_dual"] += len(a_dual)
        totals["tier_a_b"] += len(broad)

        def best(items, prob_key):
            if not items:
                return None
            p = max(items, key=lambda x: float(x.get(prob_key) or 0))
            return candidate_pair_to_dict(p, grader)

        event_detail[eid] = {
            "s2_prequote": len(s2),
            "tier_a": len(a),
            "tier_a_dual": len(a_dual),
            "tier_a_b": len(broad),
            "top_S2": best(s2, "independent_prob"),
            "top_S3B": best(a_dual, "model_prob"),
            "top_S3D": best(a, "model_prob"),
            "top_S3E": best(broad, "model_prob"),
        }
        for label, val in (("S2", event_detail[eid]["top_S2"]), ("S3-B", event_detail[eid]["top_S3B"]),
                           ("S3-D", event_detail[eid]["top_S3D"]), ("S3-E", event_detail[eid]["top_S3E"])):
            if val:
                top[label].append(val)

    return {
        "totals": dict(totals),
        "events": event_detail,
        "note": "PRE-QUOTE ONLY. Sunday freeze never reached /sgp quote capture, so price/value models cannot be finalized retrospectively without contaminating the forward test.",
    }


def unique_latest_slips(replay):
    grouped = {}
    for model, d in replay.items():
        for s in d["selections"]:
            key = tuple(sorted((x["event_id"], x["market"], x["player"], str(x["point"]), x["side"]) for x in s["legs"]))
            g = grouped.setdefault(key, {"models": [], "slip": s})
            g["models"].append(model)
            if s["fair_joint_prob"] > g["slip"]["fair_joint_prob"]:
                g["slip"] = s
    return list(grouped.values())


def fmt_pct(x):
    return "—" if x is None else f"{100*float(x):.1f}%"


def leg_text(l):
    return f'{l["player"]} {l["side"][0]}{l["point"]} {l["market"].replace("player_","").replace("_"," ")}'


def write_report(payload):
    lines = []
    lines.append("# Sunday 2026-10-04 retrospective replay")
    lines.append("")
    lines.append("**Status:** missed forward freeze due infrastructure failure. This replay uses only data committed before kickoff. It is diagnostic, not forward-validation evidence.")
    lines.append("")
    lines.append(f'Last committed pregame cutoff: **{payload["latest_cutoff"]}**. Intended ~08:00 ET freeze data was not committed, so no retrospective result is labeled official.')
    lines.append("")
    lines.append("## Cross-game model ladder at last committed board")
    lines.append("")
    lines.append("| Model | Qualified legs | Positive-edge pairs | Selected | Result |")
    lines.append("|---|---:|---:|---|---|")
    latest = payload["snapshots"][-1]["cross_game"]
    for m in parlay_lab.RESEARCH_MODELS:
        d = latest[m]
        if d["selections"]:
            sel = d["selections"]
            txt = "<br>".join(" + ".join(leg_text(x) for x in s["legs"]) for s in sel)
            res = "<br>".join(f'{s["resolution"]} ({s["pnl"] if s["pnl"] is not None else "—"})' for s in sel)
        else:
            txt = "NO PLAY"
            res = "—"
        lines.append(f'| {m} | {d["qualified_legs"]} | {d["valid_pairs"]} | {txt} | {res} |')

    lines.append("")
    lines.append("## Selection stability across committed pregame snapshots")
    lines.append("")
    lines.append("| Cutoff | V1 | V2 | V3 | V4 | V5 | V6 | V8 |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for snap in payload["snapshots"]:
        vals = []
        for m in ("V1","V2","V3","V4","V5","V6","V8"):
            sels = snap["cross_game"][m]["selections"]
            if not sels:
                vals.append("NO PLAY")
            else:
                vals.append(" / ".join(" + ".join(x["player"] for x in s["legs"]) for s in sels))
        lines.append("| " + snap["cutoff"] + " | " + " | ".join(vals) + " |")

    lines.append("")
    lines.append("## Unique selected slips at the final committed board")
    lines.append("")
    for i, g in enumerate(payload["latest_unique_slips"], 1):
        s = g["slip"]
        lines.append(f'{i}. **{", ".join(g["models"])}**: ' + " + ".join(leg_text(x) for x in s["legs"]) +
                     f' | {s["book"]} reconstructed {s["price"]:+d} | fair {fmt_pct(s["fair_joint_prob"])} | edge {s["model_edge_pct"]:+.1f}% | **{s["resolution"].upper()}**')

    lines.append("")
    lines.append("## SGP true-correlation funnel at final committed board")
    lines.append("")
    t = payload["sgp_prequote"]["totals"]
    lines.append(f'- Verified same-team candidate pairs: **{t.get("verified_same_team",0)}**')
    lines.append(f'- S2 quality + dual-confirm pairs reaching pre-quote stage: **{t.get("s2_prequote",0)}**')
    lines.append(f'- Tier-A core-quality pairs: **{t.get("tier_a",0)}**')
    lines.append(f'- Tier-A + dual-confirm pairs: **{t.get("tier_a_dual",0)}**')
    lines.append(f'- Tier-A/B broad core-quality pairs: **{t.get("tier_a_b",0)}**')
    lines.append("")
    lines.append("Actual Sunday SGP prices were never frozen, so S2/S3-A/B/C/D/E cannot be called finalized slips. The report records which pairs reached the pre-quote funnel and their eventual outcomes only.")
    lines.append("")
    lines.append("## Interpretation guardrail")
    lines.append("")
    lines.append("Sunday is one retrospective slate and the same underlying legs create many correlated pairs. Pair counts are therefore not independent samples. Use the ladder to diagnose filter strictness and use CLV/forward results, not one Sunday's W/L, to judge edge.")
    (OUT_DIR / "REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    events = sunday_events()
    event_ids = set(events)
    if not event_ids:
        raise SystemExit("No Sunday events found")
    snapshots = reconstruct_snapshots(event_ids, REQUESTED_CUTOFFS)
    grader = slips.Grader(read_rows("results"))
    clv = clv_index()

    snap_out = []
    for cutoff, rows in zip(REQUESTED_CUTOFFS, snapshots):
        snap_out.append({
            "cutoff": cutoff,
            "line_rows": len(rows),
            "cross_game": model_replay(rows, grader, clv),
        })

    latest_rows = snapshots[-1]
    payload = {
        "generated_at": iso(),
        "target_date": TARGET_DATE,
        "method": "retrospective replay from committed pregame line history; no postgame prices used",
        "forward_status": "MISSED_FORWARD_FREEZE",
        "event_ids": sorted(event_ids),
        "latest_cutoff": REQUESTED_CUTOFFS[-1],
        "snapshots": snap_out,
        "latest_unique_slips": unique_latest_slips(snap_out[-1]["cross_game"]),
        "sgp_prequote": sgp_prequote(latest_rows, grader),
    }
    (OUT_DIR / "results.json").write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    write_report(payload)
    print(json.dumps({
        "events": len(event_ids),
        "cutoffs": len(REQUESTED_CUTOFFS),
        "latest_unique_slips": len(payload["latest_unique_slips"]),
        "sgp_prequote": payload["sgp_prequote"]["totals"],
    }, sort_keys=True))


if __name__ == "__main__":
    main()
