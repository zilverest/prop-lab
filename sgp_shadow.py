"""sgp_shadow.py — paper-only single-game SGP shadow research.

This module is deliberately separate from the live cross-game V1–V8 family and the
legacy H1–H4/slips experiment.  It never logs into a sportsbook and never places a bet.
It only:
  * observes the exact current PropLine board,
  * verifies QB/pass-catcher team identity using nflverse weekly rosters,
  * requests PropLine's /sgp quote for research candidates,
  * freezes S0/S1/S2/S3-A:E decisions before kickoff,
  * records every S3 rejection reason, and
  * settles paper outcomes from data/results.csv.

Freeze policy: first successful GitHub tick with 0 < hours-to-kick <= 8.  The repo runs
roughly every six hours, so this normally lands near 08:00 ET for Sunday 1pm games and
14:00 ET for Thursday night games.  Frozen rows never rewrite after later prices arrive.
"""
from __future__ import annotations

import csv
import datetime as dt
import itertools
import json
import math
import os
import re
import tempfile
import unicodedata
import urllib.request
from collections import defaultdict
from zoneinfo import ZoneInfo

from common import *
import slips as _slips

NY = ZoneInfo("America/New_York")
OBSERVE_HOURS_BEFORE = 36.0
FREEZE_HOURS_BEFORE = 8.0
MAX_QUOTES_PER_EVENT = 30
ROSTER_MAX_AGE_DAYS = 7
SHADOW_BOOKS = tuple(SGP_BOOKS)              # PropLine SGP books currently supported by the project
SHADOW_MODELS = ("S0", "S1", "S2", "S3-A", "S3-B", "S3-C", "S3-D", "S3-E")
# Only experimental gate rejections belong in the long-form audit. Structural impossibilities
# (wrong team, failed core quality, unsupported archetype) remain summarized in decision notes.
AUDIT_RESEARCH_REASONS = {"", "no_dual_confirm_leg", "no_sgp_quote", "tier_b_not_allowed", "nonpositive_pricing_edge"}

MODEL_META = {
    "S0": dict(name="Stranger", status="CONTROL", detail="Legacy unrelated-pair control"),
    "S1": dict(name="Legacy Stack", status="CONTROL", detail="Passer + catcher, same direction; identity not required"),
    "S2": dict(name="Quality Stack", status="SHADOW", detail="Verified same team + Pinnacle/5b + ≥1 dual-confirm leg"),
    "S3-A": dict(name="Strict Value", status="SHADOW", detail="Tier A + dual confirm + positive S3 price edge"),
    "S3-B": dict(name="Hit + Confirm", status="SHADOW", detail="Tier A + dual confirm; no price gate"),
    "S3-C": dict(name="Value NoConfirm", status="SHADOW", detail="Tier A + positive S3 price edge"),
    "S3-D": dict(name="Quality Hit", status="SHADOW", detail="Tier A; no confirmation or price gate"),
    "S3-E": dict(name="Broad", status="SHADOW", detail="Tier A+B; no confirmation or price gate"),
}

PASSER_ARCH = {
    "player_pass_yds": "PASS_YDS",
    "player_pass_completions": "COMPLETIONS",
    "player_pass_attempts": "ATTEMPTS",
    "player_pass_tds": "PASS_TD",
}
CATCHER_ARCH = {
    "player_reception_yds": "REC_YDS",
    "player_receptions": "RECEPTIONS",
    "player_reception_tds": "REC_TD",
    "player_receiving_tds": "REC_TD",
}

TIER_A = {
    ("PASS_YDS__REC_YDS", "WR"),
    ("PASS_TD__REC_TD", "WR"),
    ("PASS_TD__REC_TD", "TE"),
    ("COMPLETIONS__RECEPTIONS", "WR"),
    ("COMPLETIONS__RECEPTIONS", "TE"),
    ("COMPLETIONS__RECEPTIONS", "RB"),
}
TIER_B = {
    ("PASS_YDS__RECEPTIONS", "WR"),
    ("PASS_YDS__REC_YDS", "TE"),
    ("PASS_YDS__REC_YDS", "RB"),
    ("ATTEMPTS__RECEPTIONS", "WR"),
    ("ATTEMPTS__RECEPTIONS", "TE"),
    ("ATTEMPTS__RECEPTIONS", "RB"),
    ("PASS_TD__REC_TD", "RB"),
}

BOARD_FIELDS = [
    "ts", "snapshot_ts", "board_date", "week_key", "event_id", "commence_time", "home", "away",
    "hours_to_kick", "roster_status", "raw_legs", "quality_legs", "legacy_stack_pairs", "stranger_pairs",
    "verified_team_pairs", "s2_pairs", "tier_a_pairs", "tier_b_pairs", "frozen", "note",
]
DECISION_FIELDS = [
    "ts", "board_date", "board_ts", "week_key", "event_id", "commence_time", "home", "away",
    "model", "model_name", "decision", "slip_no", "pair_id", "qb_player", "catcher_player", "qb_team",
    "catcher_team", "catcher_position", "qb_market", "qb_side", "qb_point", "qb_fair_prob",
    "catcher_market", "catcher_side", "catcher_point", "catcher_fair_prob", "archetype", "tier", "rho_cons",
    "independent_prob", "model_joint_prob", "confirm_books", "book", "sgp_price", "book_break_even_prob",
    "pricing_edge_pp", "stake", "resolution", "pnl", "settled_ts", "note",
]
AUDIT_FIELDS = [
    "ts", "board_date", "board_ts", "week_key", "event_id", "home", "away", "model", "pair_id",
    "qb_player", "catcher_player", "qb_team", "catcher_team", "catcher_position", "qb_market", "qb_side",
    "qb_point", "qb_fair_prob", "catcher_market", "catcher_side", "catcher_point", "catcher_fair_prob",
    "archetype", "tier", "rho_cons", "independent_prob", "model_joint_prob", "confirm_books", "book",
    "sgp_price", "book_break_even_prob", "pricing_edge_pp", "approved", "rejection_reason", "resolution",
    "pnl_if_played", "settled_ts",
]
RESULT_FIELDS = [
    "settled_ts", "board_date", "week_key", "event_id", "home", "away", "model", "pair_id", "book",
    "sgp_price", "stake", "resolution", "pnl", "model_joint_prob", "book_break_even_prob", "pricing_edge_pp",
    "qb_player", "catcher_player", "archetype", "tier",
]
ROSTER_FIELDS = ["season", "week", "team", "position", "full_name", "football_name", "status"]


def _f(x, default=None):
    try: return float(x)
    except (TypeError, ValueError): return default


def _i(x, default=0):
    try: return int(float(x))
    except (TypeError, ValueError): return default


def _week_key(date_s):
    d = dt.date.fromisoformat(date_s); return (d - dt.timedelta(days=d.weekday())).isoformat()


def _norm_name(s):
    s = re.sub(r"\s*\([A-Z]{2,4}\)\s*$", "", str(s or "")).strip()
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    parts = [p for p in s.split() if p not in {"jr", "sr", "ii", "iii", "iv", "v"}]
    return " ".join(parts)


TEAM_NAMES = {
    "ARI":"arizona cardinals","ATL":"atlanta falcons","BAL":"baltimore ravens","BUF":"buffalo bills",
    "CAR":"carolina panthers","CHI":"chicago bears","CIN":"cincinnati bengals","CLE":"cleveland browns",
    "DAL":"dallas cowboys","DEN":"denver broncos","DET":"detroit lions","GB":"green bay packers",
    "HOU":"houston texans","IND":"indianapolis colts","JAX":"jacksonville jaguars","KC":"kansas city chiefs",
    "LV":"las vegas raiders","LAC":"los angeles chargers","LAR":"los angeles rams","MIA":"miami dolphins",
    "MIN":"minnesota vikings","NE":"new england patriots","NO":"new orleans saints","NYG":"new york giants",
    "NYJ":"new york jets","PHI":"philadelphia eagles","PIT":"pittsburgh steelers","SEA":"seattle seahawks",
    "SF":"san francisco 49ers","TB":"tampa bay buccaneers","TEN":"tennessee titans","WAS":"washington commanders",
}
TEAM_ALIAS = {v:k for k,v in TEAM_NAMES.items()}
TEAM_ALIAS.update({"jacksonville jaguars":"JAX", "washington command ers":"WAS"})


def _team_code(label):
    s = str(label or "").strip()
    m = re.match(r"^([A-Z]{2,4})\b", s)
    if m:
        code = m.group(1)
        if code == "JAC": code = "JAX"
        return code
    n = _norm_name(s)
    return TEAM_ALIAS.get(n, "")


def _roster_url(season):
    return f"https://github.com/nflverse/nflverse-data/releases/download/weekly_rosters/roster_weekly_{season}.csv"


def _roster_cache_path(): return csv_path("sgp_roster_cache")


def _download_roster_cache(season, now=None):
    """Download nflverse weekly roster CSV, compact to the latest row per player/team, persist only useful fields."""
    now = now or utcnow(); url = _roster_url(season)
    req = urllib.request.Request(url, headers={"User-Agent":"prop-lab/sgp-shadow"})
    with urllib.request.urlopen(req, timeout=90) as r:
        raw = r.read().decode("utf-8", "replace")
    reader = csv.DictReader(raw.splitlines())
    latest = {}
    for row in reader:
        if str(row.get("season", "")) not in (str(season), str(float(season))): continue
        name = row.get("full_name") or row.get("football_name") or row.get("player_name") or ""
        team = row.get("team") or row.get("club_code") or ""
        pos = row.get("position") or row.get("pos_abb") or row.get("pos_name") or ""
        if not (name and team and pos): continue
        if team == "JAC": team = "JAX"
        week = _i(row.get("week"), 0)
        key = (_norm_name(name), team)
        prev = latest.get(key)
        if prev is None or week >= _i(prev.get("week"), 0):
            latest[key] = dict(season=season, week=week, team=team, position=pos,
                               full_name=name, football_name=row.get("football_name", ""), status=row.get("status", ""))
    if not latest: raise RuntimeError("nflverse roster download parsed zero rows")
    p = _roster_cache_path()
    with open(p, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=ROSTER_FIELDS, extrasaction="ignore"); w.writeheader(); w.writerows(latest.values())
    state_set("sgp_roster_cache", {"season":season, "downloaded_at":iso(now), "rows":len(latest), "source":url})
    return len(latest)


def ensure_roster_cache(now=None):
    now = now or utcnow(); local = now.astimezone(NY); season = local.year
    meta = state_get("sgp_roster_cache", {}) or {}; p = _roster_cache_path()
    fresh = False
    if os.path.exists(p) and str(meta.get("season")) == str(season):
        try:
            age = (now - parse_iso(meta.get("downloaded_at", ""))).total_seconds()/86400
            fresh = age < 1.0
        except Exception: pass
    if fresh: return "fresh"
    try:
        _download_roster_cache(season, now); return "refreshed"
    except Exception as e:
        if os.path.exists(p):
            try:
                age = (now - parse_iso(meta.get("downloaded_at", ""))).total_seconds()/86400
                if age <= ROSTER_MAX_AGE_DAYS: return f"stale:{age:.1f}d"
            except Exception: pass
        return f"unavailable:{type(e).__name__}"


def _roster_index():
    p = _roster_cache_path(); idx = defaultdict(list)
    if not os.path.exists(p): return idx
    with open(p, newline="") as f:
        for r in csv.DictReader(f): idx[_norm_name(r.get("full_name") or r.get("football_name"))].append(r)
    return idx


def _resolve_player(name, event_teams, roster_idx):
    rows = roster_idx.get(_norm_name(name), [])
    candidates = [r for r in rows if r.get("team") in event_teams]
    if len(candidates) == 1: return candidates[0]
    if len(candidates) > 1:
        candidates.sort(key=lambda r:_i(r.get("week"),0), reverse=True); return candidates[0]
    return None


def _snapshot_rows(now=None):
    now = now or utcnow(); rows = read_rows("current_lines")
    if not rows: return [], "missing"
    times=[]
    for r in rows:
        try: times.append(parse_iso(r.get("ts", "")))
        except Exception: pass
    if not times: return [], "bad_ts"
    newest=max(times); age=(now-newest).total_seconds()/3600
    if age > 2.25: return [], f"stale:{age:.1f}h"
    return rows, "fresh"


def _leg_key(r): return (r.get("event_id"), r.get("market"), r.get("player"), str(r.get("point","")), r.get("side"))


def _passes_gate(r):
    try: fp=float(r["fair_prob"]); ev=float(r["ev_pct"]); nb=int(float(r["n_books"]))
    except Exception: return False
    if not (GATE["fair_min"] <= fp <= GATE["fair_max"]): return False
    if nb < GATE["min_books"]: return False
    if r.get("fair_source") not in GATE["trusted_anchors"] and nb < GATE["kalshi_min_books"]: return False
    return ev >= GATE["min_ev_pct"]


def _aggregate_legs(event_rows):
    """One underlying line/side per leg with current market-level fair data and confirmation metadata."""
    grouped=defaultdict(list)
    for r in event_rows:
        if r.get("side") not in ("Over","Under") or r.get("point") in ("",None): continue
        grouped[_leg_key(r)].append(r)
    seen_counts = _slips.candidate_seen_counts()
    out=[]
    for key, rows in grouped.items():
        pinnacle=[r for r in rows if r.get("fair_source")=="pinnacle" and _f(r.get("fair_prob")) is not None]
        source_rows=pinnacle or [r for r in rows if _f(r.get("fair_prob")) is not None]
        if not source_rows: continue
        rep=max(source_rows,key=lambda r:(_i(r.get("n_books")), _f(r.get("ev_pct"),-999)))
        fair=sum(float(r["fair_prob"]) for r in source_rows)/len(source_rows)
        confirm={r["book"] for r in rows if _passes_gate(r) and r.get("fair_source")=="pinnacle"}
        candidate_rows=[]
        for r in rows:
            if not _passes_gate(r): continue
            try:
                score,_parts=_slips.candidate_score(r, seen_counts.get(key,1))
            except Exception:
                score=float(r.get("ev_pct",0))
            if score >= AUTO_LOG_MIN_SCORE: candidate_rows.append((score,r))
        best=max(candidate_rows,key=lambda x:x[0]) if candidate_rows else (None,None)
        out.append(dict(
            event_id=key[0], market=key[1], player=key[2], point=key[3], side=key[4], fair_prob=fair,
            fair_source=rep.get("fair_source",""), n_books=max(_i(r.get("n_books")) for r in rows),
            confirm_books=sorted(confirm), dual_confirm=("bovada" in confirm and "draftkings" in confirm),
            quality=best[1] is not None, quality_score=best[0] if best[0] is not None else "",
            ev_pct=_f(best[1].get("ev_pct")) if best[1] else None,
            current_books=sorted({r.get("book") for r in rows if r.get("book")}), commence_time=rep.get("commence_time",""),
            home=rep.get("home",""), away=rep.get("away",""),
        ))
    return out


def _depth_ok(leg):
    if leg["market"] == "player_receptions":
        return _f(leg.get("point"),0) > 1.5
    return True


def _legacy_stack(a,b):
    return a["player"]!=b["player"] and a["side"]==b["side"] and ({a["market"],b["market"]}&set(PASSER_MARKETS)) and ({a["market"],b["market"]}&set(CATCHER_MARKETS))


def _archetype(qb, catcher):
    q=PASSER_ARCH.get(qb["market"]); c=CATCHER_ARCH.get(catcher["market"])
    return f"{q}__{c}" if q and c else ""


def _load_priors():
    candidates=[
        os.path.join(os.path.dirname(__file__),"research","s3_true_correlation","results","s3_priors_recomputed.csv"),
        os.path.join(os.path.dirname(__file__),"s3_priors_recomputed.csv"),
    ]
    for p in candidates:
        if os.path.exists(p):
            out={}
            with open(p,newline="") as f:
                for r in csv.DictReader(f):
                    rho=_f(r.get("rho_cons"))
                    if rho is not None: out[(r["archetype"],r["pos"])]=dict(r,rho_cons=rho)
            return out
    return {}


# Acklam inverse-normal approximation (public-domain style numerical approximation).
def _norm_ppf(p):
    p=min(max(float(p),1e-10),1-1e-10)
    a=[-3.969683028665376e+01,2.209460984245205e+02,-2.759285104469687e+02,1.383577518672690e+02,-3.066479806614716e+01,2.506628277459239e+00]
    b=[-5.447609879822406e+01,1.615858368580409e+02,-1.556989798598866e+02,6.680131188771972e+01,-1.328068155288572e+01]
    c=[-7.784894002430293e-03,-3.223964580411365e-01,-2.400758277161838e+00,-2.549732539343734e+00,4.374664141464968e+00,2.938163982698783e+00]
    d=[7.784695709041462e-03,3.224671290700398e-01,2.445134137142996e+00,3.754408661907416e+00]
    pl=0.02425; ph=1-pl
    if p<pl:
        q=math.sqrt(-2*math.log(p)); return (((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5])/((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    if p>ph:
        q=math.sqrt(-2*math.log(1-p)); return -(((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5])/((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    q=p-.5; r=q*q
    return (((((a[0]*r+a[1])*r+a[2])*r+a[3])*r+a[4])*r+a[5])*q/(((((b[0]*r+b[1])*r+b[2])*r+b[3])*r+b[4])*r+1)


def _norm_cdf(x): return .5*(1+math.erf(x/math.sqrt(2)))
def _norm_pdf(x): return math.exp(-.5*x*x)/math.sqrt(2*math.pi)


def _bvn_cdf(a,b,rho):
    rho=max(min(float(rho),.95),-.95)
    if abs(rho)<1e-9: return _norm_cdf(a)*_norm_cdf(b)
    lo=-8.0; hi=min(float(a),8.0)
    if hi<=lo: return 0.0
    n=160
    if n%2: n+=1
    h=(hi-lo)/n; den=math.sqrt(1-rho*rho)
    def f(x): return _norm_pdf(x)*_norm_cdf((b-rho*x)/den)
    s=f(lo)+f(hi)
    for i in range(1,n): s+=(4 if i%2 else 2)*f(lo+i*h)
    return min(max(s*h/3,0.0),1.0)


def correlated_joint_prob(p1,p2,rho,side1="Over",side2="Over"):
    """Gaussian-copula joint probability for two binary threshold events."""
    p1=min(max(float(p1),1e-8),1-1e-8); p2=min(max(float(p2),1e-8),1-1e-8)
    # Convert both requested events to W <= quantile(p); Over flips the latent variable sign.
    s1=1 if side1=="Under" else -1; s2=1 if side2=="Under" else -1
    return _bvn_cdf(_norm_ppf(p1), _norm_ppf(p2), rho*s1*s2)


def _pair_id(a,b):
    parts=[f"{x['player']}|{x['market']}|{x['side']}|{x['point']}" for x in (a,b)]
    return "||".join(sorted(parts))


def _pair_body(a,b):
    return [{"market":x["market"],"name":x["side"],"description":x["player"],"point":float(x["point"])} for x in (a,b)]


def _quote_pair(api,event_id,sport,a,b):
    quotes=[]
    for book in SHADOW_BOOKS:
        res=api.post(f"/sports/{sport}/events/{event_id}/sgp", {"bookmaker":book,"legs":_pair_body(a,b)})
        if isinstance(res,dict) and res.get("quoted") is True and res.get("sgp_price") not in ("",None):
            price=int(float(res["sgp_price"])); quotes.append(dict(book=book,sgp_price=price,
                independent_price=res.get("independent_price",""),correlation_factor=res.get("correlation_factor",""),
                break_even=am_to_p(price),error=""))
        elif isinstance(res,dict) and res.get("_error") in (503,):
            quotes.append(dict(book=book,error=f"http {res['_error']}"))
    return quotes


def _best_quote(quotes):
    good=[q for q in quotes if q.get("sgp_price") not in (None,"")]
    if not good: return None
    return max(good,key=lambda q:am_to_dec(int(q["sgp_price"])))


def _event_row(event_id):
    return next((r for r in read_rows("events") if r.get("event_id")==str(event_id)),{})


def _event_context(event_id,event_rows,roster_idx):
    ev=_event_row(event_id); home=ev.get("home") or (event_rows[0].get("home") if event_rows else ""); away=ev.get("away") or (event_rows[0].get("away") if event_rows else "")
    teams={_team_code(home),_team_code(away)}-{""}
    return home,away,teams


def _candidate_universe(event_id,event_rows,roster_idx,priors):
    legs=_aggregate_legs(event_rows); home,away,event_teams=_event_context(event_id,event_rows,roster_idx)
    resolved={}
    for l in legs:
        rr=_resolve_player(l["player"],event_teams,roster_idx)
        if rr: resolved[_leg_key(l)]=rr
    quality=[l for l in legs if l.get("quality")]
    stranger=[]; legacy=[]
    for a,b in itertools.combinations(quality,2):
        if a["player"]==b["player"]: continue
        if _legacy_stack(a,b): legacy.append((a,b))
        else: stranger.append((a,b))
    stranger.sort(key=lambda p:-(float(p[0].get("quality_score") or 0)+float(p[1].get("quality_score") or 0)))
    legacy.sort(key=lambda p:-(float(p[0].get("quality_score") or 0)+float(p[1].get("quality_score") or 0)))

    true_pairs=[]
    passers=[l for l in legs if l["market"] in PASSER_ARCH]
    catchers=[l for l in legs if l["market"] in CATCHER_ARCH]
    for q,c in itertools.product(passers,catchers):
        if q["player"]==c["player"] or q["side"]!=c["side"]: continue
        qr=resolved.get(_leg_key(q)); cr=resolved.get(_leg_key(c))
        relation="unknown"
        if qr and cr: relation="same_team" if qr.get("team")==cr.get("team") else "opponents"
        pos=(cr or {}).get("position","")
        arch=_archetype(q,c); prior=priors.get((arch,pos))
        tier="A" if (arch,pos) in TIER_A else "B" if (arch,pos) in TIER_B else ""
        independent=float(q["fair_prob"])*float(c["fair_prob"])
        rho=prior.get("rho_cons") if prior else None
        adjusted=correlated_joint_prob(q["fair_prob"],c["fair_prob"],rho,q["side"],c["side"]) if rho is not None else None
        true_pairs.append(dict(qb=q,catcher=c,qb_roster=qr,catcher_roster=cr,relation=relation,position=pos,
                               archetype=arch,tier=tier,rho_cons=rho,independent_prob=independent,model_prob=adjusted,
                               pair_id=_pair_id(q,c),dual_confirm=bool(q.get("dual_confirm") or c.get("dual_confirm")),
                               core_quality=(q.get("fair_source")=="pinnacle" and c.get("fair_source")=="pinnacle" and q["n_books"]>=5 and c["n_books"]>=5 and _depth_ok(q) and _depth_ok(c))))
    true_pairs.sort(key=lambda p:-((p.get("model_prob") or p["independent_prob"]) + (.03 if p.get("dual_confirm") else 0)))
    return dict(legs=legs,quality=quality,stranger=stranger,legacy=legacy,true=true_pairs,home=home,away=away,event_teams=event_teams,resolved=resolved)


def _quote_candidates(api,event_id,sport,univ):
    """Quote the union of controls and top true-correlation candidates once, with a hard API cap."""
    candidates=[]; seen=set()
    for source,pairs in (("S0",univ["stranger"][:1]),("S1",univ["legacy"][:1])):
        for a,b in pairs:
            pid=_pair_id(a,b)
            if pid not in seen: candidates.append(dict(pair_id=pid,qb=a,catcher=b,kind=source,true=None)); seen.add(pid)
    for p in univ["true"]:
        # Quote only pairs that could reach S2/S3 after identity/market quality checks.
        if p["relation"]!="same_team" or not p["core_quality"]: continue
        pid=p["pair_id"]
        if pid in seen: continue
        candidates.append(dict(pair_id=pid,qb=p["qb"],catcher=p["catcher"],kind="TRUE",true=p)); seen.add(pid)
    candidates=candidates[:MAX_QUOTES_PER_EVENT]
    out={}; transient=0
    for p in candidates:
        qs=_quote_pair(api,event_id,sport,p["qb"],p["catcher"])
        if qs and all(q.get("error") for q in qs): transient+=1
        out[p["pair_id"]]=dict(pair=p,quotes=qs,best=_best_quote(qs))
    return out, transient


def _model_eval(model,p,quote_info):
    """Return (approved, reason, predicted_probability)."""
    best=(quote_info or {}).get("best")
    if model in ("S0","S1"):
        if not best: return False,"no_sgp_quote",p.get("independent_prob")
        return True,"",p.get("independent_prob")
    # S2/S3 require verified identity and market quality.
    if p.get("relation")!="same_team": return False,"team_not_verified_same",p.get("model_prob") or p.get("independent_prob")
    if not p.get("core_quality"): return False,"core_quality_failed",p.get("model_prob") or p.get("independent_prob")
    if model=="S2":
        if not p.get("dual_confirm"): return False,"no_dual_confirm_leg",p.get("independent_prob")
        if not best: return False,"no_sgp_quote",p.get("independent_prob")
        return True,"",p.get("independent_prob")
    if not p.get("archetype") or p.get("rho_cons") is None or not p.get("tier"):
        return False,"unsupported_correlation_archetype",p.get("model_prob")
    if model!="S3-E" and p.get("tier")!="A": return False,"tier_b_not_allowed",p.get("model_prob")
    if model in ("S3-A","S3-B") and not p.get("dual_confirm"): return False,"no_dual_confirm_leg",p.get("model_prob")
    if not best: return False,"no_sgp_quote",p.get("model_prob")
    edge_pp=100*((p.get("model_prob") or 0)-best["break_even"])
    if model in ("S3-A","S3-C") and edge_pp <= 0: return False,"nonpositive_pricing_edge",p.get("model_prob")
    return True,"",p.get("model_prob")


def _pair_record(p,best=None,prob_override=None):
    q=p.get("qb",{}); c=p.get("catcher",{}); qr=p.get("qb_roster") or {}; cr=p.get("catcher_roster") or {}
    prob=prob_override if prob_override is not None else (p.get("model_prob") if p.get("model_prob") is not None else p.get("independent_prob"))
    be=best.get("break_even") if best else None
    edge=(100*(prob-be)) if (prob is not None and be is not None) else None
    return dict(pair_id=p.get("pair_id") or _pair_id(q,c),qb_player=q.get("player",""),catcher_player=c.get("player",""),
                qb_team=qr.get("team",""),catcher_team=cr.get("team",""),catcher_position=p.get("position",""),
                qb_market=q.get("market",""),qb_side=q.get("side",""),qb_point=q.get("point",""),qb_fair_prob=q.get("fair_prob",""),
                catcher_market=c.get("market",""),catcher_side=c.get("side",""),catcher_point=c.get("point",""),catcher_fair_prob=c.get("fair_prob",""),
                archetype=p.get("archetype",""),tier=p.get("tier",""),rho_cons=p.get("rho_cons","") if p.get("rho_cons") is not None else "",
                independent_prob=p.get("independent_prob","") if p.get("independent_prob") is not None else "",
                model_joint_prob=prob if prob is not None else "",confirm_books=json.dumps(sorted(set(q.get("confirm_books",[])+c.get("confirm_books",[])))),
                book=best.get("book","") if best else "",sgp_price=best.get("sgp_price","") if best else "",
                book_break_even_prob=be if be is not None else "",pricing_edge_pp=edge if edge is not None else "")


def _event_hours(ev,now):
    try: return (parse_iso(ev["commence_time"])-now).total_seconds()/3600
    except Exception: return None


def observe(now=None):
    now=now or utcnow(); rows,status=_snapshot_rows(now)
    if not rows: return 0
    roster_status=ensure_roster_cache(now); roster_idx=_roster_index(); priors=_load_priors()
    by_event=defaultdict(list)
    for r in rows: by_event[r["event_id"]].append(r)
    existing={(r.get("event_id"),r.get("snapshot_ts")) for r in read_rows("sgp_shadow_boards")}
    new=[]
    for eid,erows in by_event.items():
        ev=_event_row(eid); h=_event_hours(ev,now)
        if h is None or not (0<h<=OBSERVE_HOURS_BEFORE): continue
        snap=max((r.get("ts","") for r in erows),default="")
        if (eid,snap) in existing: continue
        u=_candidate_universe(eid,erows,roster_idx,priors)
        true=[p for p in u["true"] if p["relation"]=="same_team"]
        new.append(dict(ts=iso(now),snapshot_ts=snap,board_date=now.astimezone(NY).date().isoformat(),week_key=_week_key(now.astimezone(NY).date().isoformat()),
                        event_id=eid,commence_time=ev.get("commence_time",""),home=u["home"],away=u["away"],hours_to_kick=round(h,2),
                        roster_status=roster_status,raw_legs=len(u["legs"]),quality_legs=len(u["quality"]),legacy_stack_pairs=len(u["legacy"]),stranger_pairs=len(u["stranger"]),
                        verified_team_pairs=len(true),s2_pairs=sum(p["core_quality"] and p["dual_confirm"] for p in true),
                        tier_a_pairs=sum(p["core_quality"] and p["tier"]=="A" for p in true),tier_b_pairs=sum(p["core_quality"] and p["tier"]=="B" for p in true),
                        frozen="",note=status))
    return append_rows("sgp_shadow_boards",new,BOARD_FIELDS)


def _frozen_event_ids():
    return {r.get("event_id") for r in read_rows("sgp_shadow_decisions") if r.get("event_id")}


def freeze(api,now=None):
    now=now or utcnow(); rows,status=_snapshot_rows(now)
    if not rows: return dict(events=0,decisions=0,audits=0,skipped=status)
    roster_status=ensure_roster_cache(now)
    if roster_status.startswith("unavailable"):
        return dict(events=0,decisions=0,audits=0,skipped=roster_status)
    roster_idx=_roster_index(); priors=_load_priors(); frozen=_frozen_event_ids()
    by_event=defaultdict(list)
    for r in rows: by_event[r["event_id"]].append(r)
    all_dec=[]; all_audit=[]; n_events=0
    for eid,erows in by_event.items():
        if eid in frozen: continue
        ev=_event_row(eid); h=_event_hours(ev,now)
        if h is None or not (0<h<=FREEZE_HOURS_BEFORE): continue
        u=_candidate_universe(eid,erows,roster_idx,priors); sport=erows[0].get("sport") or SPORTS[0]
        quoted,transient=_quote_candidates(api,eid,sport,u)
        # If every attempted quote failed transiently, leave unfrozen so the next tick can retry.
        if quoted and transient==len(quoted): continue
        board_date=now.astimezone(NY).date().isoformat(); week=_week_key(board_date); board_ts=max((r.get("ts","") for r in erows),default=iso(now))
        n_events+=1

        # Build one candidate list per model. Controls use their selected pair; S2/S3 use true-pair universe.
        controls={}
        for model,pairs in (("S0",u["stranger"][:1]),("S1",u["legacy"][:1])):
            if pairs:
                a,b=pairs[0]; controls[model]=dict(qb=a,catcher=b,qb_roster=None,catcher_roster=None,relation="legacy",position="",archetype="",tier="",rho_cons=None,
                    independent_prob=float(a["fair_prob"])*float(b["fair_prob"]),model_prob=None,pair_id=_pair_id(a,b),dual_confirm=False,core_quality=True)
        model_candidates={m:[] for m in SHADOW_MODELS}
        for m,p in controls.items(): model_candidates[m]=[p]
        true=u["true"]
        model_candidates["S2"]=true
        for m in ("S3-A","S3-B","S3-C","S3-D","S3-E"): model_candidates[m]=true

        # Audit every S2/S3 pair-model gate, including rejected winners later.
        for model in ("S2","S3-A","S3-B","S3-C","S3-D","S3-E"):
            for p in true:
                qi=quoted.get(p["pair_id"],{}); ok,reason,pred=_model_eval(model,p,qi); best=qi.get("best")
                base=_pair_record(p,best,pred)
                if ok or reason in AUDIT_RESEARCH_REASONS:
                    all_audit.append(dict(ts=iso(now),board_date=board_date,board_ts=board_ts,week_key=week,event_id=eid,home=u["home"],away=u["away"],model=model,
                                          approved=str(bool(ok)),rejection_reason=reason,resolution="",pnl_if_played="",settled_ts="",**base))

        for model in SHADOW_MODELS:
            approved=[]; reasons=defaultdict(int)
            for p in model_candidates[model]:
                qi=quoted.get(p["pair_id"],{}); ok,reason,pred=_model_eval(model,p,qi)
                if ok:
                    best=qi.get("best"); base=_pair_record(p,best,pred); approved.append((p,base))
                else: reasons[reason or "rejected"]+=1
            # Selection criterion differs by purpose: value variants maximize edge; hit variants maximize predicted P.
            chosen=None
            if approved:
                if model in ("S3-A","S3-C"):
                    chosen=max(approved,key=lambda x:_f(x[1].get("pricing_edge_pp"),-999))
                else:
                    chosen=max(approved,key=lambda x:_f(x[1].get("model_joint_prob"),0))
            if chosen:
                p,base=chosen
                all_dec.append(dict(ts=iso(now),board_date=board_date,board_ts=board_ts,week_key=week,event_id=eid,commence_time=ev.get("commence_time",""),home=u["home"],away=u["away"],
                                    model=model,model_name=MODEL_META[model]["name"],decision="play",slip_no=1,stake=STAKE_USD,resolution="open",pnl="",settled_ts="",
                                    note="SGP SHADOW ONLY · actual PropLine /sgp quote · never auto-wagered",**base))
            else:
                reason_txt=", ".join(f"{k}:{v}" for k,v in sorted(reasons.items())) or "no_candidates"
                all_dec.append(dict(ts=iso(now),board_date=board_date,board_ts=board_ts,week_key=week,event_id=eid,commence_time=ev.get("commence_time",""),home=u["home"],away=u["away"],
                                    model=model,model_name=MODEL_META[model]["name"],decision="no_play",slip_no=0,pair_id="",qb_player="",catcher_player="",qb_team="",catcher_team="",catcher_position="",
                                    qb_market="",qb_side="",qb_point="",qb_fair_prob="",catcher_market="",catcher_side="",catcher_point="",catcher_fair_prob="",archetype="",tier="",rho_cons="",independent_prob="",
                                    model_joint_prob="",confirm_books="",book="",sgp_price="",book_break_even_prob="",pricing_edge_pp="",stake=0,resolution="",pnl="",settled_ts="",note=reason_txt))
    nd=append_rows("sgp_shadow_decisions",all_dec,DECISION_FIELDS); na=append_rows("sgp_rejection_audit",all_audit,AUDIT_FIELDS)
    return dict(events=n_events,decisions=nd,audits=na,skipped="")


def _grade_pair(row,grader):
    if row.get("decision")!="play": return None
    legs=[
        dict(market=row["qb_market"],player=row["qb_player"],point=row["qb_point"],side=row["qb_side"]),
        dict(market=row["catcher_market"],player=row["catcher_player"],point=row["catcher_point"],side=row["catcher_side"]),
    ]
    res=[grader.leg(l,row["event_id"],row.get("book","")) for l in legs]
    if any(r is None for r in res): return None
    if "lost" in res: return "lost"
    if "void" in res or "push" in res: return "void"      # do not invent correlated repricing
    return "won"


def _pnl_for(res,price,stake=STAKE_USD):
    if res=="lost": return -float(stake)
    if res=="won" and price not in ("",None): return (am_to_dec(int(float(price)))-1)*float(stake)
    if res in ("void","push"): return 0.0
    return None


def settle(now=None):
    now=now or utcnow(); results=read_rows("results")
    if not results: return dict(decisions=0,audits=0,results=0)
    grader=_slips.Grader(results); kick={e["event_id"]:e.get("commence_time","") for e in read_rows("events")}
    rows=read_rows("sgp_shadow_decisions"); n=0; result_rows=[]; existing={(r.get("model"),r.get("event_id"),r.get("pair_id"),r.get("book")) for r in read_rows("sgp_shadow_results")}
    for r in rows:
        if r.get("decision")!="play" or r.get("resolution") not in ("open",""): continue
        res=_grade_pair(r,grader)
        if res is None:
            try:
                if (now-parse_iso(kick.get(r["event_id"],""))).total_seconds()>72*3600: res="void"
            except Exception: pass
        if res is None: continue
        pnl=_pnl_for(res,r.get("sgp_price"),_f(r.get("stake"),STAKE_USD)); r["resolution"]=res; r["pnl"]=round(pnl or 0,2); r["settled_ts"]=iso(now); n+=1
        k=(r["model"],r["event_id"],r.get("pair_id"),r.get("book"))
        if k not in existing:
            result_rows.append({k2:r.get(k2,"") for k2 in RESULT_FIELDS}); result_rows[-1]["settled_ts"]=iso(now); existing.add(k)
    if n:
        with open(csv_path("sgp_shadow_decisions"),"w",newline="") as f:
            w=csv.DictWriter(f,fieldnames=DECISION_FIELDS,extrasaction="ignore"); w.writeheader(); w.writerows(rows)
    nr=append_rows("sgp_shadow_results",result_rows,RESULT_FIELDS)

    audits=read_rows("sgp_rejection_audit"); na=0
    for r in audits:
        if r.get("resolution"): continue
        fake=dict(decision="play",event_id=r["event_id"],book=r.get("book",""),qb_market=r["qb_market"],qb_player=r["qb_player"],qb_point=r["qb_point"],qb_side=r["qb_side"],
                  catcher_market=r["catcher_market"],catcher_player=r["catcher_player"],catcher_point=r["catcher_point"],catcher_side=r["catcher_side"])
        res=_grade_pair(fake,grader)
        if res is None: continue
        r["resolution"]=res; pnl=_pnl_for(res,r.get("sgp_price"),STAKE_USD); r["pnl_if_played"]="" if pnl is None else round(pnl,2); r["settled_ts"]=iso(now); na+=1
    if na:
        with open(csv_path("sgp_rejection_audit"),"w",newline="") as f:
            w=csv.DictWriter(f,fieldnames=AUDIT_FIELDS,extrasaction="ignore"); w.writeheader(); w.writerows(audits)
    return dict(decisions=n,audits=na,results=nr)


def _event_map():
    return {r.get("event_id", ""): r for r in read_rows("events") if r.get("event_id")}


def _dev_game_date(event_id, events=None):
    events = events or _event_map()
    ev = events.get(str(event_id), {})
    try:
        return parse_iso(ev.get("commence_time", "")).astimezone(NY).date().isoformat()
    except Exception:
        return ""


def _legacy_pair_row(model, slip, events):
    try:
        legs = json.loads(slip.get("legs", "[]"))
    except Exception:
        legs = []
    if len(legs) != 2:
        return None
    a, b = legs
    if b.get("market") in PASSER_ARCH and a.get("market") not in PASSER_ARCH:
        a, b = b, a
    event_id = str(slip.get("event_id", ""))
    ev = events.get(event_id, {})
    ds = _dev_game_date(event_id, events)
    price = _i(slip.get("price"), 0)
    be = (1 / am_to_dec(price)) if price else None
    return dict(
        ts=slip.get("ts", ""), board_date=ds, board_ts=slip.get("ts", ""),
        week_key=_week_key(ds) if ds else "", event_id=event_id,
        commence_time=ev.get("commence_time", ""), home=ev.get("home", ""), away=ev.get("away", ""),
        model=model, model_name=MODEL_META[model]["name"], decision="play", slip_no="1",
        pair_id=f'dev:{model}:{event_id}', qb_player=a.get("player", ""), catcher_player=b.get("player", ""),
        qb_team="", catcher_team="", catcher_position="", qb_market=a.get("market", ""),
        qb_side=a.get("side", ""), qb_point=a.get("point", ""), qb_fair_prob="",
        catcher_market=b.get("market", ""), catcher_side=b.get("side", ""), catcher_point=b.get("point", ""),
        catcher_fair_prob="", archetype="STRANGER_CONTROL" if model=="S0" else "LEGACY_HEURISTIC_STACK",
        tier="LEGACY", rho_cons="", independent_prob="", model_joint_prob="", confirm_books="",
        book=slip.get("book", ""), sgp_price=price, book_break_even_prob=be or "", pricing_edge_pp="",
        stake=_f(slip.get("stake"), STAKE_USD), resolution=slip.get("resolution", ""),
        pnl=_f(slip.get("pnl_units"), 0), settled_ts=slip.get("settled_ts", ""),
        note="development replay; one first construction per game; legacy identity not verified",
    )


def _legacy_development_rows(model):
    """Historical one-pair-per-game controls used in the development analysis."""
    assert model in ("S0", "S1")
    events = _event_map(); chosen = {}; ordered = []
    for r in read_rows("slips"):
        if r.get("kind") != "sgp" or r.get("resolution") not in ("won", "lost", "void", "push"):
            continue
        try:
            legs = json.loads(r.get("legs", "[]"))
        except Exception:
            continue
        if len(legs) != 2:
            continue
        note = r.get("note", "")
        stack = _slips.is_stack(legs[0], legs[1])
        if model == "S1":
            ok = ("construct=stack" in note) or ("construct=" not in note and stack)
        else:
            ok = ("construct=stranger" in note) or ("construct=" not in note and not stack)
        if not ok:
            continue
        eid = str(r.get("event_id", ""))
        if eid in chosen:
            continue
        row = _legacy_pair_row(model, r, events)
        if row:
            chosen[eid] = row; ordered.append(row)
    return ordered


_S2_PRE_IDENTITY_PAIRS = (
    ("23215", frozenset(("Javonte Williams", "Lamar Jackson"))),
    ("32655", frozenset(("Ladd McConkey", "Josh Allen"))),
    ("32660", frozenset(("Michael Mayer", "Tyler Shough"))),
)


def _s2_pre_identity_rows():
    """Diagnostic only: the 2-1 quality-stack sample predates teammate verification."""
    events = _event_map(); slips = read_rows("slips"); out=[]
    for eid, names in _S2_PRE_IDENTITY_PAIRS:
        matches=[]
        for r in slips:
            if r.get("kind") != "sgp" or str(r.get("event_id")) != eid:
                continue
            try: legs=json.loads(r.get("legs","[]"))
            except Exception: continue
            if len(legs)!=2 or frozenset(x.get("player","") for x in legs) != names:
                continue
            if r.get("resolution") not in ("won","lost","void","push"): continue
            matches.append(r)
        if not matches: continue
        r=max(matches,key=lambda x:_i(x.get("price"),-9999))
        row=_legacy_pair_row("S2",r,events)
        if not row: continue
        row["archetype"]="PRE_IDENTITY_QUALITY_STACK"; row["tier"]="DIAGNOSTIC"
        row["note"]="pre-identity diagnostic only; not a replay of current verified-team S2"
        out.append(row)
    return out


def _s3d_development_rows():
    """Verified Tier-A true-correlation bridge examples from the development archive."""
    events=_event_map()
    seeds=[
        dict(event_id="32653", book="fanduel", price=150, qb="Jameis Winston", catcher="Malik Nabers",
             pos="WR", qb_market="player_pass_yds", qb_side="Under", qb_point=200.5, qb_fair=.5248,
             c_market="player_reception_yds", c_side="Under", c_point=52.5, c_fair=.5,
             archetype="PASS_YDS__REC_YDS", rho=.30424078103150837, result="won", pnl=7.50),
        dict(event_id="32659", book="draftkings", price=156, qb="Jacoby Brissett", catcher="Trey McBride",
             pos="TE", qb_market="player_pass_completions", qb_side="Over", qb_point=21.5, qb_fair=.5248,
             c_market="player_receptions", c_side="Over", c_point=7.5, c_fair=.4425,
             archetype="COMPLETIONS__RECEPTIONS", rho=.2567339180009476, result="won", pnl=7.80),
    ]
    out=[]
    for z in seeds:
        ev=events.get(z["event_id"],{}); ds=_dev_game_date(z["event_id"],events)
        model_prob=correlated_joint_prob(z["qb_fair"],z["c_fair"],z["rho"],z["qb_side"],z["c_side"])
        be=1/am_to_dec(z["price"]); edge=(model_prob-be)*100
        out.append(dict(
            ts="development",board_date=ds,board_ts="development",week_key=_week_key(ds) if ds else "",
            event_id=z["event_id"],commence_time=ev.get("commence_time",""),home=ev.get("home",""),away=ev.get("away",""),
            model="S3-D",model_name=MODEL_META["S3-D"]["name"],decision="play",slip_no="1",
            pair_id=f'dev:S3-D:{z["event_id"]}',qb_player=z["qb"],catcher_player=z["catcher"],qb_team="VERIFIED",
            catcher_team="VERIFIED",catcher_position=z["pos"],qb_market=z["qb_market"],qb_side=z["qb_side"],qb_point=z["qb_point"],qb_fair_prob=z["qb_fair"],
            catcher_market=z["c_market"],catcher_side=z["c_side"],catcher_point=z["c_point"],catcher_fair_prob=z["c_fair"],
            archetype=z["archetype"],tier="A",rho_cons=z["rho"],independent_prob=z["qb_fair"]*z["c_fair"],
            model_joint_prob=model_prob,confirm_books="none",book=z["book"],sgp_price=z["price"],book_break_even_prob=be,
            pricing_edge_pp=edge,stake=STAKE_USD,resolution=z["result"],pnl=z["pnl"],settled_ts="development",
            note="verified true-correlation development bridge; S3-D ignores confirmation and price gate",
        ))
    return out


DEV_STATUS = {
    "S0": ("DEVELOPMENT REPLAY", "One first stranger/control construction per settled game."),
    "S1": ("DEVELOPMENT REPLAY", "One first legacy stack per settled game; team identity was not verified."),
    "S2": ("PRE-IDENTITY DIAGNOSTIC", "Three historical quality-stack tickets from before teammate verification; not current-S2 evidence."),
    "S3-A": ("BRIDGE REPLAY", "0 approved: Tier-A candidates failed confirmation and/or pricing gates."),
    "S3-B": ("BRIDGE REPLAY", "0 approved: no verified Tier-A candidate passed the dual-confirm requirement."),
    "S3-C": ("BRIDGE REPLAY", "0 approved: verified Tier-A candidates had negative S3 pricing edge."),
    "S3-D": ("DEVELOPMENT REPLAY", "Two verified Tier-A true-correlation candidates; outcome-only model."),
    "S3-E": ("PARTIAL / PENDING", "Full Tier-A+B historical replay has not been enumerated; known Tier-A subset is shown only as context."),
}


def development_rows(model):
    if model in ("S0","S1"): return _legacy_development_rows(model)
    if model=="S2": return _s2_pre_identity_rows()
    if model in ("S3-A","S3-B","S3-C"): return []
    if model=="S3-D": return _s3d_development_rows()
    if model=="S3-E":
        rows=[]
        for r in _s3d_development_rows():
            x=dict(r); x["model"]="S3-E"; x["model_name"]=MODEL_META["S3-E"]["name"]
            x["pair_id"]=x["pair_id"].replace("S3-D","S3-E")
            x["note"]="known Tier-A subset only; full S3-E Tier-A+B replay pending"
            rows.append(x)
        return rows
    return []


def _record(rows):
    plays=[r for r in rows if r.get("decision")=="play"]
    settled=[r for r in plays if r.get("resolution") in ("won","lost","void","push")]
    w=sum(r.get("resolution")=="won" for r in settled); l=sum(r.get("resolution")=="lost" for r in settled)
    pnl=sum(_f(r.get("pnl"),0) for r in settled); stake=sum(_f(r.get("stake"),0) for r in plays)
    return dict(slips=len(plays),wins=w,losses=l,pnl=pnl,stake=stake,roi=(100*pnl/stake if stake else None),hit=(100*w/(w+l) if w+l else None),
                games=len({r.get("event_id") for r in rows if r.get("event_id")}),no_play=sum(r.get("decision")=="no_play" for r in rows))


def model_data():
    fwd=read_rows("sgp_shadow_decisions"); out={}
    for m in SHADOW_MODELS:
        fr=[r for r in fwd if r.get("model")==m]; dr=development_rows(m)
        out[m]=dict(meta=MODEL_META[m],fwd_rows=fr,fwd_record=_record(fr),dev_rows=dr,dev_record=_record(dr),dev_status=DEV_STATUS[m])
    return out


def _wl(rec):
    return f'{rec["wins"]}–{rec["losses"]}' if rec["wins"]+rec["losses"] else "0–0"


def _history_html(rows, phase_label, phase_note=""):
    if not rows:
        return f'<div class="sgp-phase"><div class="sgp-phase-title"><b>{phase_label}</b><span>{phase_note}</span></div><div class="sgpslip-empty">No approved slips in this historical sample.</div></div>'
    byweek=defaultdict(list)
    for r in rows: byweek[r.get("week_key","")].append(r)
    weeks=[]
    for wk in sorted(byweek,reverse=True):
        dates=defaultdict(list)
        for r in byweek[wk]: dates[r.get("board_date","")].append(r)
        days=[]
        for ds in sorted(dates,reverse=True):
            games=defaultdict(list)
            for r in dates[ds]: games[r.get("event_id","")].append(r)
            gs=[]
            for eid,gr in games.items():
                ev=gr[0]; plays=[x for x in gr if x.get("decision")=="play"]
                slip_rows=[]
                for x in plays:
                    price=_i(x.get("sgp_price"),0); res=(x.get("resolution") or "open").upper(); pnl=x.get("pnl")
                    pnl_txt=f'${_f(pnl,0):+.2f}' if pnl not in ("",None) else ""
                    fair=_f(x.get("model_joint_prob"),None); be=_f(x.get("book_break_even_prob"),None); edge=_f(x.get("pricing_edge_pp"),None)
                    fair_txt=f'{100*fair:.1f}%' if fair is not None else "—"; be_txt=f'{100*be:.1f}%' if be is not None else "—"; edge_txt=f'{edge:+.1f} pp' if edge is not None else "—"
                    corr=_f(x.get("rho_cons"),None); corr_txt=f'{corr:.3f}' if corr is not None else "—"
                    note=x.get("note","")
                    note_html=f'<div class="sgpcaveat">{note}</div>' if note else ''
                    slip_rows.append(f'<details class="sgpslip"><summary><span>{x["model"]} · {x.get("book","").upper()} {price:+d}</span><b>{res}</b><em>{pnl_txt}</em></summary><div class="sgpslipbody"><strong>{x.get("qb_player","")} + {x.get("catcher_player","")}</strong><div>{x.get("archetype","")} · {x.get("tier","") or "—"} · rho {corr_txt}</div><div>S3 fair {fair_txt} · book BE {be_txt} · edge {edge_txt}</div><div>{x.get("qb_market","")} {x.get("qb_side","")} {x.get("qb_point","")} · {x.get("catcher_market","")} {x.get("catcher_side","")} {x.get("catcher_point","")}</div>{note_html}</div></details>')
                slips=''.join(slip_rows) or '<div class="sgpslip-empty">No model play</div>'
                gs.append(f'<details class="sgpgame"><summary>{ev.get("away","")} @ {ev.get("home","")} · {len(plays)} slips</summary>{slips}</details>')
            days.append(f'<details class="sgpday"><summary>{ds} · {sum(x.get("decision")=="play" for x in dates[ds])} slips</summary>{"".join(gs)}</details>')
        weeks.append(f'<details class="sgpweek"><summary>Week of {wk}</summary>{"".join(days)}</details>')
    return f'<div class="sgp-phase"><div class="sgp-phase-title"><b>{phase_label}</b><span>{phase_note}</span></div>{"".join(weeks)}</div>'


def dashboard_html():
    md=model_data(); boards=read_rows("sgp_shadow_boards"); latest=max((r.get("snapshot_ts","") for r in boards),default="")
    cards=[]; histories=[]
    for m in SHADOW_MODELS:
        d=md[m]; dev=d["dev_record"]; fwd=d["fwd_record"]
        if m=="S3-E": dev_line=f'KNOWN SUBSET {_wl(dev)} · full replay pending'
        elif m=="S2": dev_line=f'PRE-ID {_wl(dev)} · {dev["slips"]} diagnostic slips'
        else: dev_line=f'DEV {_wl(dev)} · {dev["slips"]} slips'
        cards.append(f'<div class="sgpm"><b>{m}</b><span>{MODEL_META[m]["name"]}</span><strong>{_wl(fwd)}</strong><em>FWD {fwd["slips"]} slips · {fwd["pnl"]:+.2f}</em><small>{dev_line}</small></div>')
        phase_label,phase_note=d["dev_status"]
        devhist=_history_html(d["dev_rows"],phase_label,phase_note)
        fwdhist=_history_html(d["fwd_rows"],"FORWARD VALIDATION","Frozen shadow decisions only; begins at 0–0 and never rewrites history.")
        histories.append(f'<details class="sgpmodelhist"><summary><span>{m} · {MODEL_META[m]["name"]}</span><b>{dev_line}</b><em>FWD {_wl(fwd)}</em></summary><div class="sgpmodelbody">{devhist}{fwdhist}</div></details>')
    latest_note=f'Latest board snapshot: {latest or "none yet"}'
    return f'''<section class="card panel sgp-shadow"><style>
.sgp-shadow{{margin-top:14px}}.sgphead{{display:flex;justify-content:space-between;gap:14px;align-items:flex-start}}.sgphead small{{font-size:8px;color:var(--mut);font-weight:750;letter-spacing:.08em}}.sgphead>span{{font-size:8px;color:var(--mut)}}.sgpmodels{{display:grid;grid-template-columns:repeat(4,1fr);gap:7px;margin:12px 0}}.sgpm{{padding:9px;border-radius:11px;background:#f7f7f9;border:1px solid #eee}}.sgpm b,.sgpm span,.sgpm strong,.sgpm em,.sgpm small{{display:block}}.sgpm b{{font-size:9px}}.sgpm span{{font-size:8px;color:var(--mut);margin-top:2px}}.sgpm strong{{font-size:17px;margin-top:6px}}.sgpm em{{font-style:normal;font-size:8px;color:var(--mut);margin-top:2px}}.sgpm small{{font-size:7px;color:#7b7b82;margin-top:5px;line-height:1.3}}.sgphist details{{border:1px solid #eee;border-radius:10px;margin:5px 0;background:#fff;overflow:hidden}}.sgphist summary{{font-size:9px;padding:8px 9px}}.sgpmodelhist>summary{{display:grid;grid-template-columns:1fr auto auto;gap:10px;align-items:center;background:#fafafa}}.sgpmodelhist>summary span{{font-weight:800}}.sgpmodelhist>summary b{{font-size:8px;color:var(--mut)}}.sgpmodelhist>summary em{{font-style:normal;font-size:8px}}.sgpmodelbody{{padding:5px 8px 8px}}.sgp-phase{{margin-top:8px;padding-top:8px;border-top:1px solid #eee}}.sgp-phase-title{{display:flex;justify-content:space-between;gap:10px;align-items:flex-start;padding:0 2px 5px}}.sgp-phase-title b{{font-size:8px;letter-spacing:.07em}}.sgp-phase-title span{{font-size:7px;color:var(--mut);text-align:right;max-width:70%}}.sgpday,.sgpgame{{margin-left:8px!important;background:#fafafa!important}}.sgpgame{{margin-left:16px!important}}.sgpslip{{margin:5px 8px 7px!important;background:#fff!important}}.sgpslip>summary{{display:grid;grid-template-columns:1fr auto auto;gap:8px;align-items:center}}.sgpslip>summary span{{font-weight:750}}.sgpslip>summary b{{font-size:8px;color:var(--mut)}}.sgpslip>summary em{{font-style:normal;font-size:8px;font-weight:750}}.sgpslipbody{{padding:0 9px 9px}}.sgpslipbody strong{{display:block;font-size:9px}}.sgpslipbody div{{font-size:8px;color:var(--mut);margin-top:4px;line-height:1.35}}.sgpcaveat{{padding:6px;border-radius:7px;background:#fff8e8;color:#665d4b!important}}.sgpslip-empty{{padding:8px 10px;color:var(--mut);font-size:8px;border-top:1px solid #eee}}@media(max-width:800px){{.sgpmodels{{grid-template-columns:repeat(2,1fr)}}.sgpmodelhist>summary{{grid-template-columns:1fr auto}}.sgpmodelhist>summary b{{display:none}}}}
</style><div class="sgphead"><div><small>SINGLE-GAME LAB · SHADOW ONLY</small><h3>True-correlation SGP tournament</h3><p>Development replay and forward validation are separated. S0/S1 are legacy controls; S2 pre-identity history is diagnostic only; S3-E is only a known subset until its full broad replay is enumerated.</p></div><span>{latest_note}</span></div><div class="sgpmodels">{''.join(cards)}</div><div class="sgphist">{''.join(histories)}</div></section>'''

def rejection_summary():
    rows=read_rows("sgp_rejection_audit"); out={}
    for m in ("S3-A","S3-B","S3-C","S3-D","S3-E"):
        rr=[r for r in rows if r.get("model")==m and str(r.get("approved")).lower() not in ("true","1") and r.get("resolution") in ("won","lost")]
        out[m]=dict(rejected_winners=sum(r["resolution"]=="won" for r in rr),rejected_losers=sum(r["resolution"]=="lost" for r in rr))
    return out


def run_tick(api,now=None):
    now=now or utcnow(); obs=observe(now); fr=freeze(api,now); st=settle(now)
    return dict(observations=obs,freeze=fr,settle=st)


if __name__=="__main__":
    api=Api(); print(json.dumps(run_tick(api),indent=2,sort_keys=True))
