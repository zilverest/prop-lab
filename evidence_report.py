"""evidence_report.py — cohort diagnostics from canonical closing-line evidence.

This report is descriptive only. It must not mutate official model rules.
"""
from __future__ import annotations

import html
import os
from collections import defaultdict

from common import *


def _f(x,d=None):
    try:return float(x)
    except (TypeError,ValueError):return d


def _i(x,d=0):
    try:return int(float(x))
    except (TypeError,ValueError):return d


def _cohort(rows,key):
    by=defaultdict(list)
    for r in rows:
        v=r.get(key,"") or "unknown"
        if str(r.get("same_point","")).lower()!="true":continue
        if _f(r.get("clv_implied_pp")) is None:continue
        by[v].append(r)
    out=[]
    for v,rr in by.items():
        clv=[_f(x["clv_implied_pp"]) for x in rr]
        beat=sum(_f(x["clv_implied_pp"],0)>0 for x in rr)
        out.append(dict(name=v,n=len(rr),avg=sum(clv)/len(clv),beat=100*beat/len(rr),
                        avg_ev=sum(_f(x.get("ev_pct"),0) for x in rr)/len(rr)))
    return sorted(out,key=lambda x:(-x["n"],x["name"]))


def _table(title,rows):
    body=[]
    for r in rows:
        body.append(f'<tr><td>{html.escape(str(r["name"]))}</td><td>{r["n"]}</td><td>{r["avg"]:+.2f} pp</td><td>{r["beat"]:.0f}%</td><td>{r["avg_ev"]:+.2f}%</td></tr>')
    return f'''<section><h2>{html.escape(title)}</h2><table><thead><tr><th>Group</th><th>N</th><th>Avg CLV</th><th>Beat close</th><th>Avg candidate EV</th></tr></thead><tbody>{''.join(body)}</tbody></table></section>'''


def write():
    own=read_rows("own_clv")
    orig=read_rows("clv")
    same=[r for r in own if str(r.get("same_point","")).lower()=="true" and _f(r.get("clv_implied_pp")) is not None]
    id_matches=sum(r.get("match_method")=="outcome_id" for r in own)
    matched_orig=sum(str(r.get("matched","")).lower() in ("true","1") for r in orig)
    avg=(sum(_f(r["clv_implied_pp"]) for r in same)/len(same)) if same else None
    beat=(100*sum(_f(r["clv_implied_pp"],0)>0 for r in same)/len(same)) if same else None

    cards=f'''<div class="cards">
<div><b>Canonical CLV rows</b><strong>{len(own)}</strong><small>ID matches {id_matches}</small></div>
<div><b>Same-point graded</b><strong>{len(same)}</strong><small>Avg CLV {"—" if avg is None else f"{avg:+.2f} pp"}</small></div>
<div><b>Beat close</b><strong>{"—" if beat is None else f"{beat:.0f}%"}</strong><small>Same-point price movement</small></div>
<div><b>Original H2 matched</b><strong>{matched_orig}/{len(orig)}</strong><small>Legacy /clv/grade experiment</small></div>
</div>'''

    sections=[
        _table("By book",_cohort(own,"book")),
        _table("By market",_cohort(own,"market")),
        _table("By side",_cohort(own,"side")),
        _table("By timing",_cohort(own,"timing_bucket")),
        _table("By line type",_cohort(own,"line_type")),
        _table("By fair source",_cohort(own,"fair_source")),
    ]
    page=f'''<!doctype html><meta charset="utf-8"><title>Prop Lab Evidence</title><style>
body{{font:14px/1.45 system-ui;max-width:1200px;margin:auto;padding:22px;color:#18181b}}h1{{font-size:25px}}h2{{font-size:16px;margin-top:28px}}p,small{{color:#666}}.cards{{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}}.cards>div{{background:#f6f6f7;border-radius:12px;padding:12px}}.cards b,.cards strong,.cards small{{display:block}}.cards strong{{font-size:22px;margin:5px 0}}table{{width:100%;border-collapse:collapse}}th,td{{padding:7px;border-bottom:1px solid #e5e5e5;text-align:right}}th:first-child,td:first-child{{text-align:left}}@media(max-width:800px){{.cards{{grid-template-columns:repeat(2,1fr)}}}}</style>
<h1>Evidence cockpit</h1><p>Canonical closing-line cohorts. Descriptive only; official model rules remain frozen.</p>{cards}{''.join(sections)}
<p><a href="diagnostics.html">Shadow gate / selector / timing tournament →</a></p>'''
    with open(os.path.join(DOCS,"evidence.html"),"w",encoding="utf-8") as f:f.write(page)
    return page


if __name__=="__main__":
    write()
