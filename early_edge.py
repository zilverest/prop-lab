"""early_edge.py — preregistered E1 Early Edge single-leg shadow experiment.

E1 never changes official V1–V8 or S0–S3 decisions. It freezes the FIRST qualifying
single-leg market disagreement and later measures persistence, closing-line value,
calibration and paper outcome. There is no auto-wager path.
"""
from __future__ import annotations

import csv
import datetime as dt
import json
from collections import defaultdict
from zoneinfo import ZoneInfo

from common import *
import slips

NY = ZoneInfo("America/New_York")

FIELDS = [
    "ts","snapshot_ts","event_id","commence_time","target_date","week_key",
    "hours_to_kick","timing_bucket","market","player","point","side","book","price",
    "ev_pct","fair_prob","fair_source","n_books","line_type_at_entry","meta_available",
    "signal_key","persistence_final","persistence_class","edge_bucket",
    "resolution","pnl","brier","calibration_error","closing_price","closing_point",
    "closing_at","same_point","clv_implied_pp","beat_close_price","beat_close_point",
    "closing_line_type","settled_ts","note",
]

def _f(x, default=None):
    try: return float(x)
    except (TypeError, ValueError): return default

def _i(x, default=0):
    try: return int(float(x))
    except (TypeError, ValueError): return default

def _leg_key(r):
    return (str(r.get("event_id","")), r.get("market",""), r.get("player",""),
            str(r.get("point","")), r.get("side",""))

def _line_key(r):
    return _leg_key(r) + (r.get("book",""),)

def _meta_index():
    out={}
    for r in read_rows("current_line_meta"):
        out[_line_key(r)] = r
    return out

def _timing(hours):
    h=_f(hours)
    if h is None: return ""
    if h>24: return "T-24h+"
    if h>12: return "T-24_to_12h"
    if h>8: return "T-12_to_8h"
    if h>4: return "T-8_to_4h"
    if h>2: return "T-4_to_2h"
    if h>1: return "T-2_to_1h"
    return "T-1h"

def _week_key(date_s):
    d=dt.date.fromisoformat(date_s)
    return (d-dt.timedelta(days=d.weekday())).isoformat()

def _numeric_eligible(r):
    fp=_f(r.get("fair_prob")); ev=_f(r.get("ev_pct")); nb=_i(r.get("n_books"))
    return (
        r.get("side") in ("Over","Under")
        and str(r.get("point","")) != ""
        and fp is not None and .30 <= fp <= .70
        and ev is not None and ev >= 3.0
        and nb >= 5
    )

def _eligible(r, meta):
    if not _numeric_eligible(r):
        return False
    m=meta.get(_line_key(r))
    line_type=(m or {}).get("line_type","")
    if line_type and line_type != "main":
        return False
    return True

def _prior_eligible_keys(cutoff_ts):
    """Conservative anti-backfill guard: do not call an already-seen signal first."""
    out=set()
    for r in read_rows("candidates"):
        if r.get("ts","") >= cutoff_ts:
            continue
        if _numeric_eligible(r):
            out.add(_leg_key(r))
    return out

def _edge_bucket(ev):
    x=_f(ev,0)
    if x >= 12: return "12+"
    if x >= 8: return "8-12"
    if x >= 5: return "5-8"
    return "3-5"

def _persistence_class(n):
    n=_i(n)
    if n >= 5: return "D5+"
    if n >= 3: return "D3+"
    if n == 2: return "D2"
    return "D1"

def observe(now=None):
    now=now or utcnow()
    rows=read_rows("current_lines")
    if not rows:
        return 0
    snapshot_ts=max((r.get("ts","") for r in rows), default="")
    if not snapshot_ts:
        return 0
    meta=_meta_index()
    existing={r.get("signal_key") for r in read_rows("e1_early_edge_signals")}
    prior=_prior_eligible_keys(snapshot_ts)
    grouped=defaultdict(list)
    for r in rows:
        if _eligible(r,meta):
            grouped[_leg_key(r)].append(r)

    out=[]
    for key,choices in grouped.items():
        sk="|".join(key)
        if sk in existing or key in prior:
            continue
        rep=max(choices,key=lambda r:(_f(r.get("ev_pct"),-999),_i(r.get("n_books")),r.get("book","")))
        try:
            local_date=parse_iso(rep["commence_time"]).astimezone(NY).date().isoformat()
        except Exception:
            local_date=""
        m=meta.get(_line_key(rep))
        line_type=(m or {}).get("line_type","") or "unknown"
        out.append(dict(
            ts=iso(now),snapshot_ts=snapshot_ts,event_id=rep.get("event_id",""),
            commence_time=rep.get("commence_time",""),target_date=local_date,
            week_key=_week_key(local_date) if local_date else "",
            hours_to_kick=rep.get("hours_to_kick",""),timing_bucket=_timing(rep.get("hours_to_kick")),
            market=rep.get("market",""),player=rep.get("player",""),point=str(rep.get("point","")),
            side=rep.get("side",""),book=rep.get("book",""),price=rep.get("price",""),
            ev_pct=rep.get("ev_pct",""),fair_prob=rep.get("fair_prob",""),
            fair_source=rep.get("fair_source",""),n_books=rep.get("n_books",""),
            line_type_at_entry=line_type,meta_available=bool(m),signal_key=sk,
            persistence_final="",persistence_class="",edge_bucket=_edge_bucket(rep.get("ev_pct")),
            resolution="",pnl="",brier="",calibration_error="",closing_price="",closing_point="",
            closing_at="",same_point="",clv_implied_pp="",beat_close_price="",beat_close_point="",
            closing_line_type="",settled_ts="",
            note="E1_EARLY_EDGE_SHADOW · first qualifying signal only · never auto-wagered",
        ))
        existing.add(sk)
    n=append_rows("e1_early_edge_signals",out,FIELDS)
    print("e1 observe",json.dumps({"ts":iso(now),"snapshot_ts":snapshot_ts,"signals":n},sort_keys=True))
    return n

def _persistence_count(signal):
    seen=set()
    kick=signal.get("commence_time","")
    for r in read_rows("candidates"):
        if _leg_key(r) != _leg_key(signal):
            continue
        if r.get("ts","") < signal.get("snapshot_ts",""):
            continue
        if kick and r.get("ts","") > kick:
            continue
        if _numeric_eligible(r):
            seen.add(r.get("ts",""))
    return max(1,len(seen))

def _clv_row(signal, own):
    matches=[
        r for r in own
        if r.get("candidate_ts")==signal.get("snapshot_ts")
        and r.get("event_id")==signal.get("event_id")
        and r.get("market")==signal.get("market")
        and r.get("player")==signal.get("player")
        and str(r.get("point",""))==str(signal.get("point",""))
        and r.get("side")==signal.get("side")
        and r.get("book")==signal.get("book")
    ]
    return matches[-1] if matches else None

def settle(now=None):
    now=now or utcnow()
    rows=read_rows("e1_early_edge_signals")
    if not rows:
        return 0
    grader=slips.Grader(read_rows("results"))
    own=read_rows("own_clv")
    changed=0
    for r in rows:
        if r.get("resolution"):
            continue
        res=grader.leg(r,r.get("event_id",""),r.get("book",""))
        if res is None:
            continue
        stake=STAKE_USD
        if res=="won":
            pnl=(am_to_dec(int(float(r["price"])))-1)*stake
            y=1.0
        elif res=="lost":
            pnl=-stake
            y=0.0
        else:
            pnl=0.0
            y=None
        p=_f(r.get("fair_prob"))
        r["resolution"]=res
        r["pnl"]=round(pnl,2)
        r["settled_ts"]=iso(now)
        if p is not None and y is not None:
            r["brier"]=round((p-y)**2,6)
            r["calibration_error"]=round(y-p,6)
        n=_persistence_count(r)
        r["persistence_final"]=n
        r["persistence_class"]=_persistence_class(n)
        c=_clv_row(r,own)
        if c:
            r["closing_price"]=c.get("closing_price","")
            r["closing_point"]=c.get("closing_point","")
            r["closing_at"]=c.get("closing_at","")
            r["same_point"]=c.get("same_point","")
            r["beat_close_price"]=c.get("beat_close_price","")
            r["beat_close_point"]=c.get("beat_close_point","")
            r["closing_line_type"]=c.get("line_type","")
            if c.get("same_point")=="True":
                r["clv_implied_pp"]=c.get("clv_implied_pp","")
        changed+=1
    if changed:
        with open(csv_path("e1_early_edge_signals"),"w",newline="") as f:
            w=csv.DictWriter(f,fieldnames=FIELDS,extrasaction="ignore")
            w.writeheader();w.writerows(rows)
    print("e1 settle",json.dumps({"ts":iso(now),"settled":changed},sort_keys=True))
    return changed
