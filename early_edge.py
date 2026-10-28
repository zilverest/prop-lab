"""early_edge.py — preregistered E1 Early Edge single-leg shadow experiment.

E1 never changes official V1–V8 or S0–S3 decisions. It freezes the FIRST qualifying
single-leg market disagreement and later measures persistence, closing-line value,
calibration and paper outcome. There is no auto-wager path.
"""
from __future__ import annotations

import csv
import datetime as dt
import html
import json
from collections import defaultdict
from zoneinfo import ZoneInfo

from common import *
import slips

NY = ZoneInfo("America/New_York")
POC_MIN_EV_PCT = 5.0
POC_MIN_HOURS_TO_KICK = 12.0

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


def _is_poc(r):
    """Reporting-only POC cohort. Does not alter E1 signal generation."""
    ev=_f(r.get("ev_pct")); hours=_f(r.get("hours_to_kick"))
    return ev is not None and ev >= POC_MIN_EV_PCT and hours is not None and hours >= POC_MIN_HOURS_TO_KICK

def _stats(rows):
    settled=[r for r in rows if r.get("resolution") in ("won","lost","void","push")]
    decided=[r for r in settled if r.get("resolution") in ("won","lost")]
    wins=sum(r.get("resolution")=="won" for r in decided)
    losses=sum(r.get("resolution")=="lost" for r in decided)
    voids=sum(r.get("resolution")=="void" for r in settled)
    pushes=sum(r.get("resolution")=="push" for r in settled)
    pnl=sum(_f(r.get("pnl"),0) for r in settled)
    stake=STAKE_USD*len(decided)
    same=[r for r in settled if str(r.get("same_point","")).lower() in ("true","1") and _f(r.get("clv_implied_pp")) is not None]
    beats=[r for r in same if str(r.get("beat_close_price","")).lower() in ("true","1","false","0")]
    return dict(
        signals=len(rows),settled=len(settled),open=max(0,len(rows)-len(settled)),
        wins=wins,losses=losses,voids=voids,pushes=pushes,
        hit_rate=(100*wins/(wins+losses) if wins+losses else None),
        pnl=round(pnl,2),roi=(100*pnl/stake if stake else None),
        same_point=len(same),
        avg_clv=(sum(_f(r.get("clv_implied_pp"),0) for r in same)/len(same) if same else None),
        beat_close=(100*sum(str(r.get("beat_close_price","")).lower() in ("true","1") for r in beats)/len(beats) if beats else None),
    )

def poc_summary():
    rows=read_rows("e1_early_edge_signals")
    poc=[r for r in rows if _is_poc(r)]
    by_date={}
    for ds in sorted({r.get("target_date","") for r in poc if r.get("target_date")}):
        by_date[ds]=_stats([r for r in poc if r.get("target_date")==ds])
    return dict(
        rule=dict(min_ev_pct=POC_MIN_EV_PCT,min_hours_to_kick=POC_MIN_HOURS_TO_KICK),
        broad=_stats(rows),poc=_stats(poc),by_date=by_date,
    )

def _pct(x, digits=1):
    return "—" if x is None else f"{x:.{digits}f}%"

def _money(x):
    x=_f(x,0)
    return ("+" if x>0 else "") + "$" + f"{x:.2f}"

def _h(x):
    return html.escape(str(x))

def _market_label(market):
    return str(market or "").replace("player_","").replace("_"," ")

def dashboard_html():
    """Static E1 POC panel for the main dashboard. Reporting only."""
    rows=read_rows("e1_early_edge_signals")
    if not rows:
        return '''<section class="card panel e1-panel"><h3>E1 POC · Early price dislocation</h3><p>No E1 signals have been recorded yet.</p></section>'''

    poc=[r for r in rows if _is_poc(r)]
    broad=_stats(rows); ps=_stats(poc)
    settled_poc=[r for r in poc if r.get("resolution") in ("won","lost","void","push")]
    d12=_stats([r for r in settled_poc if r.get("persistence_class") in ("D1","D2")])
    d3=_stats([r for r in settled_poc if r.get("persistence_class") in ("D3+","D5+")])

    slate_rows=[]
    dates=sorted({r.get("target_date","") for r in poc if r.get("target_date")}, reverse=True)
    for ds in dates[:8]:
        x=_stats([r for r in poc if r.get("target_date")==ds])
        date_label=dt.date.fromisoformat(ds).strftime("%b %-d")
        rec=f'{x["wins"]}–{x["losses"]}' + (f'–{x["voids"]}V' if x["voids"] else "")
        slate_rows.append(
            f'<tr><td>{_h(date_label)}</td><td>{x["signals"]}</td><td>{_h(rec)}</td>'
            f'<td>{_money(x["pnl"])}</td><td>{_pct(x["avg_clv"],2)}</td><td>{_pct(x["beat_close"])}</td></tr>'
        )

    latest_rows=[]
    for r in sorted(poc,key=lambda x:(x.get("target_date",""),x.get("snapshot_ts","")),reverse=True)[:8]:
        res=(r.get("resolution") or "open").upper()
        cls="win" if res=="WON" else "loss" if res=="LOST" else "open"
        edge=_f(r.get("ev_pct")); hours=_f(r.get("hours_to_kick"))
        latest_rows.append(
            f'<tr><td>{_h(r.get("target_date",""))}</td><td><b>{_h(r.get("player",""))}</b><br>'
            f'<span class="e1-sub">{_h(r.get("side",""))} {_h(r.get("point",""))} {_h(_market_label(r.get("market")))}</span></td>'
            f'<td>{_pct(edge)}</td><td>{hours:.1f}h</td><td class="{cls}">{_h(res)}</td><td>{_money(r.get("pnl")) if r.get("pnl") not in ("",None) else "—"}</td></tr>'
        )

    broad_rec=f'{broad["wins"]}–{broad["losses"]}'
    poc_rec=f'{ps["wins"]}–{ps["losses"]}' + (f'–{ps["voids"]}V' if ps["voids"] else "")
    return f'''
<style>
.e1-panel{{margin-top:14px;padding:22px}}
.e1-head{{display:flex;justify-content:space-between;gap:18px;align-items:flex-start}}
.e1-head h3{{font-size:24px;margin:0 0 5px}}
.e1-head p{{max-width:760px}}
.e1-badge{{font-size:9px;font-weight:800;letter-spacing:.06em;padding:6px 9px;border-radius:999px;background:#eef6ff;color:#1769aa;white-space:nowrap}}
.e1-kpis{{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:8px;margin:14px 0}}
.e1-kpi{{padding:11px;border-radius:13px;border:1px solid #eee;background:#fafafa}}
.e1-kpi small{{display:block;font-size:8px;text-transform:uppercase;letter-spacing:.05em;color:var(--mut)}}
.e1-kpi b{{display:block;font-size:18px;margin-top:4px}}
.e1-compare{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:9px;margin:12px 0}}
.e1-box{{border:1px solid #eee;border-radius:14px;padding:12px;background:#fff}}
.e1-box small{{font-size:8px;text-transform:uppercase;letter-spacing:.05em;color:var(--mut)}}
.e1-box b{{display:block;font-size:18px;margin:4px 0}}
.e1-box span,.e1-sub{{font-size:8px;color:var(--mut)}}
.e1-grid{{display:grid;grid-template-columns:1fr 1.35fr;gap:14px;margin-top:14px}}
.e1-grid h4{{font-size:13px;margin:0 0 6px}}
@media(max-width:900px){{.e1-kpis{{grid-template-columns:repeat(3,1fr)}}.e1-grid{{grid-template-columns:1fr}}}}
@media(max-width:620px){{.e1-kpis{{grid-template-columns:repeat(2,1fr)}}.e1-compare{{grid-template-columns:1fr}}}}
</style>
<section class="card e1-panel">
  <div class="e1-head"><div><small>E1 early edge</small><h3>POC · Early price dislocation</h3>
    <p>Reporting-only monitor for the frozen POC cohort: first E1 signal with <b>≥{POC_MIN_EV_PCT:.0f}% estimated edge</b> and <b>≥{POC_MIN_HOURS_TO_KICK:.0f} hours before kickoff</b>. E1 remains forward shadow only and never auto-wagers.</p></div>
    <div class="e1-badge">FORWARD SHADOW · POC</div>
  </div>
  <div class="e1-kpis">
    <div class="e1-kpi"><small>Record</small><b>{poc_rec}</b></div>
    <div class="e1-kpi"><small>Hit rate</small><b>{_pct(ps["hit_rate"])}</b></div>
    <div class="e1-kpi"><small>Paper P&amp;L</small><b>{_money(ps["pnl"])}</b></div>
    <div class="e1-kpi"><small>Paper ROI</small><b>{_pct(ps["roi"])}</b></div>
    <div class="e1-kpi"><small>Avg CLV</small><b>{_pct(ps["avg_clv"],2)}</b></div>
    <div class="e1-kpi"><small>Beat close</small><b>{_pct(ps["beat_close"])}</b></div>
  </div>
  <div class="e1-compare">
    <div class="e1-box"><small>POC cohort</small><b>{ps["signals"]} signals</b><span>{ps["settled"]} settled · {ps["same_point"]} exact same-point closes</span></div>
    <div class="e1-box"><small>All E1 context</small><b>{broad_rec} · {_money(broad["pnl"])}</b><span>{broad["signals"]} signals · {_pct(broad["avg_clv"],2)} avg CLV</span></div>
    <div class="e1-box"><small>Persistence diagnostic</small><b>D1/D2 {d12["wins"]}–{d12["losses"]}</b><span>D3+/D5+ {d3["wins"]}–{d3["losses"]} · diagnostic, not entry gate</span></div>
  </div>
  <div class="e1-grid">
    <div><h4>POC by slate</h4><table><tr><th>slate</th><th>n</th><th>record</th><th>P&amp;L</th><th>CLV</th><th>beat</th></tr>{''.join(slate_rows) or '<tr><td colspan="6">No settled POC slates yet.</td></tr>'}</table></div>
    <div><h4>Latest POC signals</h4><table><tr><th>date</th><th>prop</th><th>edge</th><th>early</th><th>result</th><th>P&amp;L</th></tr>{''.join(latest_rows) or '<tr><td colspan="6">No POC signals yet.</td></tr>'}</table></div>
  </div>
</section>'''

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
