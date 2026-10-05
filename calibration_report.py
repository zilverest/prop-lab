"""calibration_report.py — probability calibration diagnostics.

Uses one observation per underlying leg per timing bucket so repeated book rows do not
pretend to be independent outcomes. This is descriptive shadow evidence only.
"""
from __future__ import annotations

import html
import json
import os
from collections import defaultdict

from common import *
import slips


def _f(x,d=None):
    try:return float(x)
    except (TypeError,ValueError):return d


def _timing(hours):
    try:h=float(hours)
    except Exception:return "unknown"
    if h>24:return "T-24h+"
    if h>12:return "T-24_to_12h"
    if h>8:return "T-12_to_8h"
    if h>4:return "T-8_to_4h"
    if h>2:return "T-4_to_2h"
    if h>1:return "T-2_to_1h"
    return "T-1h"


def _prob_bucket(p):
    if p<.40:return "30–40%"
    if p<.50:return "40–50%"
    if p<.60:return "50–60%"
    return "60–70%"


def observations():
    """Deduplicate to the latest candidate observation per underlying leg/timing bucket."""
    chosen={}
    for r in read_rows("candidates"):
        p=_f(r.get("fair_prob"))
        if p is None or not (GATE["fair_min"]<=p<=GATE["fair_max"]):continue
        tb=_timing(r.get("hours_to_kick"))
        key=(r.get("event_id"),r.get("market"),r.get("player"),str(r.get("point","")),r.get("side"),tb)
        prev=chosen.get(key)
        # Fair probability is market-level, so one book row per underlying leg is enough.
        # Prefer a Pinnacle-anchored row and otherwise the latest observation.
        rank=(r.get("fair_source")=="pinnacle",r.get("ts",""))
        if prev is None or rank>(prev["_rank"]):
            x=dict(r);x["_rank"]=rank;x["timing_bucket"]=tb;chosen[key]=x

    grader=slips.Grader(read_rows("results"));out=[]
    for r in chosen.values():
        leg=dict(market=r["market"],player=r["player"],point=r["point"],side=r["side"])
        res=grader.leg(leg,r["event_id"],r.get("book",""))
        if res not in ("won","lost"):continue
        p=_f(r["fair_prob"]);y=1.0 if res=="won" else 0.0
        out.append(dict(
            event_id=r["event_id"],market=r["market"],player=r["player"],point=r["point"],side=r["side"],
            fair_prob=p,fair_source=r.get("fair_source",""),n_books=r.get("n_books",""),
            timing_bucket=r["timing_bucket"],prob_bucket=_prob_bucket(p),resolution=res,
            brier=(p-y)**2,error=y-p,
        ))
    return out


def _group(rows,key):
    by=defaultdict(list)
    for r in rows:by[r.get(key,"unknown")].append(r)
    out=[]
    for name,rr in by.items():
        n=len(rr);forecast=sum(x["fair_prob"] for x in rr)/n;actual=sum(x["resolution"]=="won" for x in rr)/n
        out.append(dict(name=name,n=n,forecast=forecast,actual=actual,gap=actual-forecast,
                        brier=sum(x["brier"] for x in rr)/n))
    return sorted(out,key=lambda x:(x["name"]))


def _table(title,rows):
    trs=[]
    for r in rows:
        trs.append(f'<tr><td>{html.escape(str(r["name"]))}</td><td>{r["n"]}</td><td>{100*r["forecast"]:.1f}%</td><td>{100*r["actual"]:.1f}%</td><td>{100*r["gap"]:+.1f} pp</td><td>{r["brier"]:.3f}</td></tr>')
    return f'''<section><h2>{html.escape(title)}</h2><table><thead><tr><th>Bucket</th><th>N</th><th>Forecast</th><th>Actual</th><th>Calibration gap</th><th>Brier</th></tr></thead><tbody>{''.join(trs)}</tbody></table></section>'''


def write():
    rows=observations();n=len(rows)
    forecast=sum((r["fair_prob"] for r in rows),0.0)/n if n else None
    actual=sum(r["resolution"]=="won" for r in rows)/n if n else None
    brier=sum(r["brier"] for r in rows)/n if n else None
    page=f'''<!doctype html><meta charset="utf-8"><title>Prop Lab Calibration</title><style>
body{{font:14px/1.45 system-ui;max-width:1100px;margin:auto;padding:22px;color:#18181b}}h1{{font-size:25px}}h2{{font-size:16px;margin-top:28px}}p{{color:#666}}.hero{{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}}.hero div{{padding:12px;border-radius:12px;background:#f6f6f7}}.hero b,.hero strong{{display:block}}.hero strong{{font-size:21px;margin-top:5px}}table{{width:100%;border-collapse:collapse}}th,td{{padding:7px;border-bottom:1px solid #e5e5e5;text-align:right}}th:first-child,td:first-child{{text-align:left}}@media(max-width:800px){{.hero{{grid-template-columns:repeat(2,1fr)}}}}</style>
<h1>Probability calibration</h1><p>Latest underlying-leg observation per timing bucket. Book duplicates are collapsed; timing snapshots remain descriptive repeated measures.</p>
<div class="hero"><div><b>Graded observations</b><strong>{n}</strong></div><div><b>Mean forecast</b><strong>{"—" if forecast is None else f"{100*forecast:.1f}%"}</strong></div><div><b>Actual win rate</b><strong>{"—" if actual is None else f"{100*actual:.1f}%"}</strong></div><div><b>Brier</b><strong>{"—" if brier is None else f"{brier:.3f}"}</strong></div></div>
{_table("By probability bucket",_group(rows,"prob_bucket"))}
{_table("By timing",_group(rows,"timing_bucket"))}
{_table("By side",_group(rows,"side"))}
{_table("By market",_group(rows,"market"))}
<p><a href="diagnostics.html">Shadow diagnostics</a> · <a href="evidence.html">Closing-line evidence</a></p>'''
    with open(os.path.join(DOCS,"calibration.html"),"w",encoding="utf-8") as f:f.write(page)
    summary=dict(rows=n,forecast=forecast,actual=actual,brier=brier)
    print("calibration",json.dumps(summary,sort_keys=True));return summary


if __name__=="__main__":
    write()
