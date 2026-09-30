#!/usr/bin/env python3
"""S3 True Correlation research engine.

Standalone research-only module. It does NOT modify prop-lab or its dashboard.

Inputs
------
- nflverse weekly player stats CSVs, e.g. stats_player_week_2024.csv
- optionally a current candidate CSV containing current prop thresholds/fair probs

Core idea
---------
1) verify same-team QB/pass-catcher identity from player-week data,
2) choose one primary QB per team/week (max pass attempts),
3) build QB/pass-catcher game-pair observations,
4) measure raw continuous correlation and threshold joint-outcome lift,
5) shrink lift toward independence (1.0),
6) validate on held-out seasons.

No betting or sportsbook automation is performed.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import statistics
from collections import defaultdict
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Iterable, Optional

PASS_CATCHER_POSITIONS = {"WR", "TE", "RB", "FB"}
QB_MARKETS = {
    "player_pass_yds": "passing_yards",
    "player_pass_tds": "passing_tds",
    "player_pass_completions": "completions",
    "player_pass_attempts": "qb_attempts",
}
CATCHER_MARKETS = {
    "player_receptions": "receptions",
    "player_reception_yds": "receiving_yards",
    "player_receiving_yards": "receiving_yards",
    "player_receiving_tds": "receiving_tds",
    "player_targets": "targets",
}

# Broad archetypes we want to estimate before line-specific modeling.
ARCHETYPES = [
    ("passing_yards", "receiving_yards"),
    ("passing_yards", "receptions"),
    ("completions", "receptions"),
    ("qb_attempts", "receptions"),
    ("passing_tds", "receiving_tds"),
    ("passing_tds", "receptions"),
    ("passing_tds", "receiving_yards"),
]


def _f(x, default=0.0):
    try:
        if x in (None, "", "NA", "NaN", "nan"):
            return default
        return float(x)
    except (TypeError, ValueError):
        return default


def _i(x, default=0):
    try:
        return int(float(x))
    except (TypeError, ValueError):
        return default


def pearson(xs: list[float], ys: list[float]) -> Optional[float]:
    if len(xs) != len(ys) or len(xs) < 3:
        return None
    mx = statistics.fmean(xs)
    my = statistics.fmean(ys)
    dx = [x - mx for x in xs]
    dy = [y - my for y in ys]
    num = sum(a*b for a, b in zip(dx, dy))
    den = math.sqrt(sum(a*a for a in dx) * sum(b*b for b in dy))
    return None if den == 0 else num / den


def hit(value: float, point: float, side: str) -> bool:
    s = side.strip().lower()
    if s == "over":
        return value > point
    if s == "under":
        return value < point
    raise ValueError(f"Unsupported side: {side}")


def american_to_prob(price: float) -> float:
    price = float(price)
    return 100.0 / (price + 100.0) if price > 0 else (-price) / ((-price) + 100.0)


def shrink_lift(raw_lift: float, n: int, prior_strength: float = 200.0) -> float:
    """Shrink multiplicative lift toward independence (1.0) on log scale."""
    if raw_lift <= 0 or n <= 0:
        return 1.0
    w = n / (n + prior_strength)
    return math.exp(w * math.log(raw_lift))


@dataclass
class PairObs:
    season: int
    week: int
    team: str
    opponent_team: str
    qb_id: str
    qb_name: str
    catcher_id: str
    catcher_name: str
    catcher_position: str
    qb_attempts: float
    passing_yards: float
    passing_tds: float
    completions: float
    receptions: float
    receiving_yards: float
    receiving_tds: float
    targets: float


def read_weekly_stats(paths: Iterable[str | Path]) -> list[dict]:
    out = []
    for path in paths:
        with open(path, newline="", encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                if (r.get("season_type") or "REG").upper() != "REG":
                    continue
                out.append(r)
    return out


def build_pair_observations(rows: list[dict], min_catcher_opportunities: float = 1.0) -> list[PairObs]:
    """Build verified same-team QB/pass-catcher game observations.

    Player stats themselves include season/week/team/position, so no name heuristic is
    used. One primary QB per team-week is selected by pass attempts.
    """
    by_game: dict[tuple[int,int,str], list[dict]] = defaultdict(list)
    for r in rows:
        season = _i(r.get("season"))
        week = _i(r.get("week"))
        team = (r.get("team") or "").strip()
        if not season or not week or not team:
            continue
        by_game[(season, week, team)].append(r)

    obs: list[PairObs] = []
    for (season, week, team), players in by_game.items():
        qbs = [p for p in players if (p.get("position") or "").upper() == "QB"]
        if not qbs:
            continue
        qb = max(qbs, key=lambda p: _f(p.get("attempts")))
        if _f(qb.get("attempts")) <= 0:
            continue
        opponent = (qb.get("opponent_team") or "").strip()

        for c in players:
            pos = (c.get("position") or "").upper()
            if pos not in PASS_CATCHER_POSITIONS:
                continue
            opportunities = max(_f(c.get("targets")), _f(c.get("receptions")))
            if opportunities < min_catcher_opportunities:
                continue
            obs.append(PairObs(
                season=season,
                week=week,
                team=team,
                opponent_team=opponent,
                qb_id=(qb.get("player_id") or "").strip(),
                qb_name=(qb.get("player_display_name") or qb.get("player_name") or "").strip(),
                catcher_id=(c.get("player_id") or "").strip(),
                catcher_name=(c.get("player_display_name") or c.get("player_name") or "").strip(),
                catcher_position=pos,
                qb_attempts=_f(qb.get("attempts")),
                passing_yards=_f(qb.get("passing_yards")),
                passing_tds=_f(qb.get("passing_tds")),
                completions=_f(qb.get("completions")),
                receptions=_f(c.get("receptions")),
                receiving_yards=_f(c.get("receiving_yards")),
                receiving_tds=_f(c.get("receiving_tds")),
                targets=_f(c.get("targets")),
            ))
    return obs


def raw_archetype_table(obs: list[PairObs], train_seasons: set[int], val_seasons: set[int]) -> list[dict]:
    rows = []
    for qstat, cstat in ARCHETYPES:
        rec = {"qb_stat": qstat, "catcher_stat": cstat}
        for label, seasons in (("train", train_seasons), ("validation", val_seasons)):
            subset = [o for o in obs if o.season in seasons]
            xs = [float(getattr(o, qstat)) for o in subset]
            ys = [float(getattr(o, cstat)) for o in subset]
            r = pearson(xs, ys)
            rec[f"{label}_n"] = len(subset)
            rec[f"{label}_pearson"] = None if r is None else round(r, 6)
        rows.append(rec)
    return rows


def threshold_lift(
    obs: list[PairObs],
    qb_stat: str,
    qb_point: float,
    qb_side: str,
    catcher_stat: str,
    catcher_point: float,
    catcher_side: str,
    seasons: Optional[set[int]] = None,
    prior_strength: float = 200.0,
) -> dict:
    subset = [o for o in obs if seasons is None or o.season in seasons]
    n = len(subset)
    if not n:
        return {"n": 0, "p_qb": None, "p_catcher": None, "p_independent": None,
                "p_joint": None, "raw_lift": None, "shrunk_lift": None}
    ah = [hit(float(getattr(o, qb_stat)), qb_point, qb_side) for o in subset]
    bh = [hit(float(getattr(o, catcher_stat)), catcher_point, catcher_side) for o in subset]
    p_a = sum(ah) / n
    p_b = sum(bh) / n
    p_ind = p_a * p_b
    p_joint = sum(a and b for a, b in zip(ah,bh)) / n
    raw = (p_joint / p_ind) if p_ind > 0 else None
    shrunk = shrink_lift(raw, n, prior_strength) if raw is not None else None
    return {
        "n": n,
        "p_qb": p_a,
        "p_catcher": p_b,
        "p_independent": p_ind,
        "p_joint": p_joint,
        "raw_lift": raw,
        "shrunk_lift": shrunk,
    }


def evaluate_candidate(obs: list[PairObs], candidate: dict, train_seasons: set[int], val_seasons: set[int],
                       prior_strength: float = 200.0) -> dict:
    qmarket = candidate["qb_market"]
    cmarket = candidate["catcher_market"]
    if qmarket not in QB_MARKETS or cmarket not in CATCHER_MARKETS:
        raise ValueError("Unsupported market archetype")
    qstat, cstat = QB_MARKETS[qmarket], CATCHER_MARKETS[cmarket]
    args = dict(
        obs=obs, qb_stat=qstat, qb_point=float(candidate["qb_point"]), qb_side=candidate["qb_side"],
        catcher_stat=cstat, catcher_point=float(candidate["catcher_point"]), catcher_side=candidate["catcher_side"],
        prior_strength=prior_strength,
    )
    tr = threshold_lift(seasons=train_seasons, **args)
    va = threshold_lift(seasons=val_seasons, **args)
    out = {**candidate, "qb_stat": qstat, "catcher_stat": cstat,
           "train": tr, "validation": va}

    # Provisional research gate — deliberately conservative and transparent.
    tr_l = tr.get("shrunk_lift")
    va_l = va.get("shrunk_lift")
    stable = bool(
        tr.get("n",0) >= 200 and va.get("n",0) >= 80 and
        tr_l is not None and va_l is not None and tr_l > 1.03 and va_l > 1.00 and
        abs(tr_l - va_l) <= 0.15
    )
    out["stable_positive_lift"] = stable

    # If the current market supplied fair marginal probabilities, use their
    # independent product and apply only the *validated/shrunk* historical lift.
    fq = candidate.get("qb_fair_prob")
    fc = candidate.get("catcher_fair_prob")
    if stable and fq is not None and fc is not None:
        base = float(fq) * float(fc)
        lift_to_use = min(tr_l, va_l)  # conservative: weaker of train/validation
        out["current_independent_prob"] = base
        out["current_lift_used"] = lift_to_use
        out["current_joint_prob"] = min(0.999, base * lift_to_use)
    else:
        out["current_independent_prob"] = None
        out["current_lift_used"] = None
        out["current_joint_prob"] = None
    return out


def write_csv(path: Path, rows: list[dict]):
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields = []
    seen = set()
    for r in rows:
        for k in r:
            if k not in seen:
                fields.append(k); seen.add(k)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader(); w.writerows(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stats", nargs="+", required=True, help="nflverse weekly player-stat CSVs")
    ap.add_argument("--train", default="2021,2022,2023,2024")
    ap.add_argument("--validation", default="2025")
    ap.add_argument("--out", default="s3_output")
    ap.add_argument("--candidate-json", help="Optional candidate JSON for line-specific lift evaluation")
    args = ap.parse_args()

    train = {int(x) for x in args.train.split(",") if x.strip()}
    val = {int(x) for x in args.validation.split(",") if x.strip()}
    rows = read_weekly_stats(args.stats)
    obs = build_pair_observations(rows)
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    write_csv(out / "same_team_qb_catcher_observations.csv", [asdict(o) for o in obs])
    write_csv(out / "raw_archetype_correlations.csv", raw_archetype_table(obs, train, val))

    summary = {
        "rows_loaded": len(rows), "pair_observations": len(obs),
        "train_seasons": sorted(train), "validation_seasons": sorted(val),
    }
    if args.candidate_json:
        candidate = json.loads(Path(args.candidate_json).read_text(encoding="utf-8"))
        result = evaluate_candidate(obs, candidate, train, val)
        (out / "candidate_evaluation.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        summary["candidate_evaluated"] = True
    (out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))

if __name__ == "__main__":
    main()
