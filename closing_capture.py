"""closing_capture.py — direct opening/closing archive + ID-aware CLV diagnostics.

This is additive evidence. It does not alter the original /clv/grade H2 experiment.
It captures PropLine's canonical /odds/closing rows after kickoff and joins future
candidate rows by stable outcome_id whenever possible.
"""
from __future__ import annotations

import csv
import json
from collections import defaultdict

from common import *

CLOSING_FIELDS=[
    "captured_ts","sport","event_id","commence_time","market","book","player","player_id","side",
    "point","outcome_id","book_outcome_id","line_type","closing_price","closing_point","closing_at",
    "closing_age_seconds","is_stale","opening_price","opening_point","opening_at","opening_age_seconds",
]
OWN_CLV_FIELDS=[
    "graded_ts","candidate_ts","event_id","market","player","player_id","point","side","book","price",
    "outcome_id","closing_price","closing_point","closing_at","is_stale","same_point",
    "candidate_implied_prob","closing_implied_prob","clv_implied_pp","beat_close_price","beat_close_point",
    "line_type","match_method",
]


def _point(x): return "" if x is None else str(x)


def _chunks(items,n=18):
    items=list(items)
    for i in range(0,len(items),n): yield items[i:i+n]


def _event_map():
    return {r["event_id"]:r for r in read_rows("events") if r.get("event_id")}


def _market_index():
    """Build once per run; never rescan the large line-history file event by event."""
    out=defaultdict(set)
    for name in ("line_identity_history","candidates"):
        for r in read_rows(name):
            if r.get("event_id") and r.get("market"):
                out[r["event_id"]].add(r["market"])
    return out


def _flatten(resp, captured_ts):
    if not isinstance(resp,dict) or "_error" in resp: return []
    out=[]; eid=str(resp.get("id","")); sport=resp.get("sport_key",""); commence=resp.get("commence_time","")
    for bk in resp.get("bookmakers",[]) or []:
        book=bk.get("key","")
        if book not in BOOKS_TRACKED: continue
        for m in bk.get("markets",[]) or []:
            market=m.get("key",""); line_type=m.get("line_type","")
            for o in m.get("outcomes",[]) or []:
                out.append(dict(
                    captured_ts=captured_ts,sport=sport,event_id=eid,commence_time=commence,
                    market=market,book=book,player=o.get("description","") or "",
                    player_id=o.get("player_id","") or "",side=o.get("name","") or "",point=_point(o.get("point")),
                    outcome_id=o.get("outcome_id","") or "",book_outcome_id=o.get("book_outcome_id","") or "",
                    line_type=o.get("line_type") or line_type or "",
                    closing_price=o.get("price","") if o.get("price") is not None else "",
                    closing_point=_point(o.get("point")),closing_at=o.get("closing_at","") or "",
                    closing_age_seconds=o.get("closing_age_seconds","") if o.get("closing_age_seconds") is not None else "",
                    is_stale=o.get("is_stale","") if o.get("is_stale") is not None else "",
                    opening_price=o.get("opening_price","") if o.get("opening_price") is not None else "",
                    opening_point=_point(o.get("opening_point")),opening_at=o.get("opening_at","") or "",
                    opening_age_seconds=o.get("opening_age_seconds","") if o.get("opening_age_seconds") is not None else "",
                ))
    return out


def capture(api, now=None, min_after_kick_minutes=10):
    """Capture canonical closing rows once per event after kickoff.

    An event is marked complete only if every requested market chunk returned successfully.
    """
    now=now or utcnow(); ts=iso(now); events=_event_map()
    done=set(state_get("closing_captured_events",[]) or [])
    market_index=_market_index()
    new_rows=[]; newly_done=[]; failures=[]
    for eid,e in events.items():
        if eid in done: continue
        try: mins=(now-parse_iso(e["commence_time"])).total_seconds()/60
        except Exception: continue
        if mins < min_after_kick_minutes: continue
        markets=sorted(market_index.get(eid,set()))
        if not markets:
            continue
        ok=True; event_rows=[]
        for chunk in _chunks(markets):
            resp=api.get(f"/sports/{e.get('sport') or SPORTS[0]}/events/{eid}/odds/closing",
                         markets=",".join(chunk),includeBookIds="true")
            if isinstance(resp,dict) and "_error" in resp:
                ok=False; failures.append(f"{eid}:{resp.get('_error')}"); break
            event_rows.extend(_flatten(resp,ts))
        if ok:
            new_rows.extend(event_rows); newly_done.append(eid)
    append_rows("closing_lines",new_rows,CLOSING_FIELDS)
    if newly_done:
        state_set("closing_captured_events",sorted(done|set(newly_done)))
    summary=dict(ts=ts,events=len(newly_done),rows=len(new_rows),failures=failures)
    print("closing capture",json.dumps(summary,sort_keys=True)); return summary


def _identity_lookup():
    exact={}; loose={}
    for r in read_rows("line_identity_history"):
        k=(r.get("event_id"),r.get("market"),r.get("player"),r.get("point"),r.get("side"),r.get("book"))
        exact[k]=r
        lk=(r.get("event_id"),r.get("market"),r.get("player"),r.get("side"),r.get("book"))
        loose[lk]=r
    return exact,loose


def _closing_lookup():
    by_id={}; exact={}; loose={}
    for r in read_rows("closing_lines"):
        if r.get("outcome_id"): by_id[r["outcome_id"]]=r
        k=(r.get("event_id"),r.get("market"),r.get("player"),r.get("point"),r.get("side"),r.get("book"))
        exact[k]=r
        lk=(r.get("event_id"),r.get("market"),r.get("player"),r.get("side"),r.get("book"))
        loose[lk]=r
    return by_id,exact,loose


def _better_point(side, taken, close):
    try: a=float(taken); b=float(close)
    except Exception: return ""
    if a==b: return False
    if side=="Over": return a < b
    if side=="Under": return a > b
    return ""


def grade_candidates(now=None):
    """Build an ID-aware CLV table for future candidate observations.

    Positive clv_implied_pp means the market moved toward the taken price at the same point:
    closing implied probability exceeded the candidate's implied probability.
    """
    now=now or utcnow(); ts=iso(now)
    id_exact,id_loose=_identity_lookup(); by_id,c_exact,c_loose=_closing_lookup()
    existing={(r.get("candidate_ts"),r.get("event_id"),r.get("market"),r.get("player"),r.get("point"),r.get("side"),r.get("book"))
              for r in read_rows("own_clv")}
    out=[]
    for c in read_rows("candidates"):
        key=(c.get("ts"),c.get("event_id"),c.get("market"),c.get("player"),c.get("point"),c.get("side"),c.get("book"))
        if key in existing: continue
        ik=(c.get("event_id"),c.get("market"),c.get("player"),c.get("point"),c.get("side"),c.get("book"))
        ident=id_exact.get(ik)
        method="outcome_id"
        close=None
        if ident and ident.get("outcome_id"):
            close=by_id.get(ident["outcome_id"])
        if close is None:
            close=c_exact.get(ik); method="exact"
        if close is None:
            lk=(c.get("event_id"),c.get("market"),c.get("player"),c.get("side"),c.get("book"))
            ident=ident or id_loose.get(lk); close=c_loose.get(lk); method="loose"
        if close is None: continue
        try:
            cp=am_to_p(int(float(c["price"]))); zp=am_to_p(int(float(close["closing_price"])))
            clv_pp=100*(zp-cp)
        except Exception:
            cp=zp=clv_pp=""
        same=str(c.get("point",""))==str(close.get("closing_point",""))
        beat_price=(clv_pp>0) if isinstance(clv_pp,(int,float)) and same else ""
        out.append(dict(
            graded_ts=ts,candidate_ts=c.get("ts",""),event_id=c.get("event_id",""),market=c.get("market",""),
            player=c.get("player",""),player_id=(ident or {}).get("player_id",""),point=c.get("point",""),
            side=c.get("side",""),book=c.get("book",""),price=c.get("price",""),
            outcome_id=(ident or {}).get("outcome_id",""),closing_price=close.get("closing_price",""),
            closing_point=close.get("closing_point",""),closing_at=close.get("closing_at",""),
            is_stale=close.get("is_stale",""),same_point=str(bool(same)),
            candidate_implied_prob=cp,closing_implied_prob=zp,clv_implied_pp=clv_pp,
            beat_close_price=beat_price,beat_close_point=_better_point(c.get("side"),c.get("point"),close.get("closing_point")),
            line_type=close.get("line_type",""),match_method=method,
        ))
        existing.add(key)
    append_rows("own_clv",out,OWN_CLV_FIELDS)
    summary=dict(ts=ts,rows=len(out),id_matches=sum(r["match_method"]=="outcome_id" for r in out),
                 exact_matches=sum(r["match_method"]=="exact" for r in out),loose_matches=sum(r["match_method"]=="loose" for r in out))
    print("own clv",json.dumps(summary,sort_keys=True)); return summary


def run(api,now=None):
    return {"capture":capture(api,now),"grade":grade_candidates(now)}
