"""instrumentation.py — additive live metadata for the prop research lab.

This module never changes the frozen V1–V8 or S0–S3 model rules. It enriches the
current board with stable PropLine ids, quote-age metadata and game context so later
CLV/calibration work can be joined without fuzzy player-name matching.
"""
from __future__ import annotations

import csv
import json
import os
from collections import defaultdict

from common import *

META_FIELDS = [
    "ts","sport","event_id","commence_time","market","book","book_event_id","player","player_id",
    "side","point","price","outcome_id","book_outcome_id","line_type","last_change_at","last_seen_at",
    "market_last_update","book_updated_at","book_version","suspended_at",
]
CONTEXT_FIELDS = ["ts","sport","event_id","commence_time","hours_to_kick","payload"]
STEAM_FIELDS = [
    "ts","sport","event_id","commence_time","hours_to_kick","market","name","team",
    "open_point","latest_point","books_quoting","books_moved","consensus_direction",
    "avg_prob_shift","consensus_point_shift","steam_score",
]
STEAM_PLAYER_FIELDS = [
    "ts","sport","event_id","commence_time","hours_to_kick","market","player","side","team",
    "open_point","latest_point","books_quoting","books_moved","consensus_direction",
    "avg_prob_shift","consensus_point_shift","steam_score",
]
HEALTH_FIELDS = ["ts","phase","status","events","rows","api_calls","api_remaining","note"]


def _f(x, default=None):
    try: return float(x)
    except (TypeError, ValueError): return default


def _point(x):
    return "" if x is None else str(x)


def _chunks(items, n=18):
    items=list(items)
    for i in range(0,len(items),n):
        yield items[i:i+n]


def _current_near_rows(now=None, max_hours=36.0):
    now=now or utcnow(); out=[]
    for r in read_rows("current_lines"):
        try:
            h=(parse_iso(r["commence_time"])-now).total_seconds()/3600
        except Exception:
            continue
        if 0 < h <= max_hours:
            out.append(r)
    return out


SGP_CORE_MARKETS = {
    "player_pass_yds","player_pass_completions","player_pass_attempts","player_pass_tds",
    "player_reception_yds","player_receptions","player_reception_tds","player_receiving_tds",
}


def _research_markets(erows):
    """Markets worth instrumenting, without dragging in every deep alternate."""
    markets=set()
    for r in erows:
        try:
            fp=float(r.get("fair_prob",""));ev=float(r.get("ev_pct",""));nb=int(float(r.get("n_books",0)))
        except Exception:
            fp=ev=None;nb=0
        if r.get("market") in SGP_CORE_MARKETS or (
            fp is not None and GATE["fair_min"]<=fp<=GATE["fair_max"]
            and ev is not None and ev>=GATE["min_ev_pct"] and nb>=GATE["min_books"]
        ):
            markets.add(r.get("market",""))
    return sorted(m for m in markets if m)


def _flatten_odds(resp, ts):
    if not isinstance(resp,dict) or "_error" in resp: return []
    out=[]; sport=resp.get("sport_key",""); eid=str(resp.get("id","")); commence=resp.get("commence_time","")
    for bk in resp.get("bookmakers",[]) or []:
        book=bk.get("key","")
        if book not in BOOKS_TRACKED: continue
        for m in bk.get("markets",[]) or []:
            market=m.get("key",""); mtype=m.get("line_type",""); mlast=m.get("last_update","")
            suspended=m.get("suspended_at","")
            for o in m.get("outcomes",[]) or []:
                out.append(dict(
                    ts=ts,sport=sport,event_id=eid,commence_time=commence,market=market,book=book,
                    book_event_id=bk.get("book_event_id","") or "",player=o.get("description","") or "",
                    player_id=o.get("player_id","") or "",side=o.get("name","") or "",point=_point(o.get("point")),
                    price=o.get("price","") if o.get("price") is not None else "",
                    outcome_id=o.get("outcome_id","") or "",book_outcome_id=o.get("book_outcome_id","") or "",
                    line_type=o.get("line_type") or mtype or "",last_change_at=o.get("last_change_at","") or "",
                    last_seen_at=o.get("last_seen_at","") or "",market_last_update=mlast,
                    book_updated_at=o.get("book_updated_at","") or "",book_version=o.get("book_version","") or "",
                    suspended_at=suspended or "",
                ))
    return out


def capture_live_meta(api, now=None, max_hours=36.0):
    """Capture stable ids + freshness for near-kickoff current rows.

    We query only market keys already present in current_lines.csv, in bounded chunks.
    current_line_meta.csv is the exact latest metadata board; line_identity_history.csv
    only appends an identity the first time we encounter that exact live leg.
    """
    now=now or utcnow(); ts=iso(now); rows=_current_near_rows(now,max_hours)
    by_event=defaultdict(list)
    for r in rows: by_event[r["event_id"]].append(r)
    all_meta=[]; failures=[]
    for eid, erows in by_event.items():
        markets=_research_markets(erows)
        sport=erows[0].get("sport") or SPORTS[0]
        for chunk in _chunks(markets):
            resp=api.get(f"/sports/{sport}/events/{eid}/odds",markets=",".join(chunk),includeBookIds="true")
            if isinstance(resp,dict) and "_error" in resp:
                failures.append(f"{eid}:{resp.get('_error')}"); continue
            all_meta.extend(_flatten_odds(resp,ts))

    # Exact latest metadata board.
    p=csv_path("current_line_meta")
    with open(p,"w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=META_FIELDS,extrasaction="ignore"); w.writeheader(); w.writerows(all_meta)

    # Preserve stable identities without duplicating every hourly observation.
    hist=read_rows("line_identity_history")
    existing={(r.get("event_id"),r.get("market"),r.get("book"),r.get("outcome_id"),r.get("point")) for r in hist}
    new=[]
    for r in all_meta:
        k=(r.get("event_id"),r.get("market"),r.get("book"),r.get("outcome_id"),r.get("point"))
        if not r.get("outcome_id") or k in existing: continue
        new.append(r); existing.add(k)
    append_rows("line_identity_history",new,META_FIELDS)

    summary=dict(ts=ts,events=len(by_event),rows=len(all_meta),new_identities=len(new),failures=failures)
    print("instrumentation meta",json.dumps(summary,sort_keys=True)); return summary


def capture_context(api, now=None, max_hours=36.0):
    """Persist change-only game context (venue/weather/etc.) as raw canonical JSON."""
    now=now or utcnow(); ts=iso(now); near=_current_near_rows(now,max_hours)
    events={}
    for r in near: events[r["event_id"]]=r
    old=read_rows("context_snapshots")
    last={}
    for r in old: last[r.get("event_id")]=r.get("payload","")
    out=[]; failures=[]
    for eid,r in events.items():
        sport=r.get("sport") or SPORTS[0]
        resp=api.get(f"/sports/{sport}/events/{eid}/context")
        if isinstance(resp,dict) and "_error" in resp:
            failures.append(f"{eid}:{resp.get('_error')}"); continue
        payload=json.dumps(resp,sort_keys=True,separators=(",",":"))
        if payload==last.get(eid): continue
        try: h=round((parse_iso(r["commence_time"])-now).total_seconds()/3600,2)
        except Exception: h=""
        out.append(dict(ts=ts,sport=sport,event_id=eid,commence_time=r.get("commence_time",""),
                        hours_to_kick=h,payload=payload))
    append_rows("context_snapshots",out,CONTEXT_FIELDS)
    summary=dict(ts=ts,events=len(events),changed=len(out),failures=failures)
    print("instrumentation context",json.dumps(summary,sort_keys=True)); return summary


def capture_movement(api, now=None, max_hours=12.0, since="-6h"):
    """Capture change-only multi-book steam summaries near kickoff.

    This is descriptive shadow evidence only. No official filter uses steam_score.
    """
    now=now or utcnow(); ts=iso(now); near=_current_near_rows(now,max_hours)
    by_event=defaultdict(list)
    for r in near: by_event[r["event_id"]].append(r)

    old=read_rows("steam_player_snapshots")
    last={}
    for r in old:
        k=(r.get("event_id"),r.get("market"),r.get("player"),r.get("side"),r.get("team"))
        last[k]="|".join(str(r.get(x,"")) for x in (
            "open_point","latest_point","books_quoting","books_moved","consensus_direction",
            "avg_prob_shift","consensus_point_shift","steam_score"
        ))

    out=[]; failures=[]
    for eid,erows in by_event.items():
        markets=_research_markets(erows)
        if not markets: continue
        sport=erows[0].get("sport") or SPORTS[0]
        commence=erows[0].get("commence_time","")
        try:h=round((parse_iso(commence)-now).total_seconds()/3600,2)
        except Exception:h=""
        for chunk in _chunks(markets):
            resp=api.get(f"/sports/{sport}/events/{eid}/movement",
                         markets=",".join(chunk),since=since,includeBookIds="true")
            if isinstance(resp,dict) and "_error" in resp:
                failures.append(f"{eid}:{resp.get('_error')}"); continue
            for x in (resp.get("steam",[]) if isinstance(resp,dict) else []):
                r=dict(
                    ts=ts,sport=sport,event_id=eid,commence_time=commence,hours_to_kick=h,
                    market=x.get("market","") or "",player=x.get("description","") or "",
                    side=x.get("name","") or "",team=x.get("team","") or "",
                    open_point=_point(x.get("open_point")),latest_point=_point(x.get("latest_point")),
                    books_quoting=x.get("books_quoting","") if x.get("books_quoting") is not None else "",
                    books_moved=x.get("books_moved","") if x.get("books_moved") is not None else "",
                    consensus_direction=x.get("consensus_direction","") or "",
                    avg_prob_shift=x.get("avg_prob_shift","") if x.get("avg_prob_shift") is not None else "",
                    consensus_point_shift=x.get("consensus_point_shift","") if x.get("consensus_point_shift") is not None else "",
                    steam_score=x.get("steam_score","") if x.get("steam_score") is not None else "",
                )
                k=(eid,r["market"],r["player"],r["side"],r["team"])
                sig="|".join(str(r.get(z,"")) for z in (
                    "open_point","latest_point","books_quoting","books_moved","consensus_direction",
                    "avg_prob_shift","consensus_point_shift","steam_score"
                ))
                if sig==last.get(k): continue
                out.append(r);last[k]=sig

    append_rows("steam_player_snapshots",out,STEAM_PLAYER_FIELDS)
    summary=dict(ts=ts,events=len(by_event),changed=len(out),failures=failures,since=since)
    print("instrumentation steam",json.dumps(summary,sort_keys=True));return summary


def health(phase,status="ok",events=0,rows=0,api=None,note=""):
    r=dict(ts=iso(),phase=phase,status=status,events=events,rows=rows,
           api_calls=getattr(api,"calls",0),api_remaining=getattr(api,"remaining",""),note=note)
    append_rows("pipeline_health",[r],HEALTH_FIELDS)
    return r
