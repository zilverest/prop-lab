"""shadow_lab.py — additive gate/selector/timing tournament.

Official V1–V8 are NEVER changed here. This module observes the same committed board and
runs diagnostic variants in parallel so each NFL slate can answer many questions at once:
filter strictness, selector choice, persistence, quote freshness and timing.

Every observation is paper-only and clearly labeled SHADOW_DIAGNOSTIC.
"""
from __future__ import annotations

import csv
import datetime as dt
import hashlib
import html
import json
import os
from collections import defaultdict
from zoneinfo import ZoneInfo

from common import *
import parlay_lab
import slips

NY=ZoneInfo("America/New_York")

FIELDS=[
    "ts","snapshot_ts","target_date","week_key","variant","family","rule","selector","slip_no",
    "qualified_legs","valid_pairs","decision","selection_key","legs","book","price","fair_joint_prob",
    "break_even_prob","model_edge_pct","persistence_min","meta_coverage","resolution","pnl","brier",
    "calibration_error","settled_ts","note",
]

VARIANTS={
    "A_MIN4": dict(family="gate",rule="V2 but min_books=4",confirm="bovada+draftkings",min_books=4,rec_min=1.5,selector="max_joint"),
    "A_NODEPTH": dict(family="gate",rule="V2 without reception-depth gate",confirm="bovada+draftkings",min_books=5,rec_min=-1,selector="max_joint"),
    "A_FAIR3565": dict(family="gate",rule="V2 with fair range 35–65%",confirm="bovada+draftkings",min_books=5,rec_min=1.5,fair=(.35,.65),selector="max_joint"),
    "A_EDGE3": dict(family="gate",rule="V2 plus pair edge >=3%",confirm="bovada+draftkings",min_books=5,rec_min=1.5,pair_edge=3,selector="max_joint"),
    "A_EDGE5": dict(family="gate",rule="V2 plus pair edge >=5%",confirm="bovada+draftkings",min_books=5,rec_min=1.5,pair_edge=5,selector="max_joint"),
    "A_PERSIST2": dict(family="gate",rule="V2; both legs seen >=2 snapshots",confirm="bovada+draftkings",min_books=5,rec_min=1.5,persist=2,selector="max_joint"),
    "A_PERSIST3": dict(family="gate",rule="V2; both legs seen >=3 snapshots",confirm="bovada+draftkings",min_books=5,rec_min=1.5,persist=3,selector="max_joint"),
    "A_FRESH300": dict(family="gate",rule="V2; confirming quotes seen <=300s ago",confirm="bovada+draftkings",min_books=5,rec_min=1.5,fresh=300,selector="max_joint"),
    "A_MAINLINE": dict(family="gate",rule="V2; representative Pinnacle leg must be main-line",confirm="bovada+draftkings",min_books=5,rec_min=1.5,mainline=True,selector="max_joint"),
    "S_MAXEDGE": dict(family="selector",rule="V2 pool; maximize reconstructed edge",confirm="bovada+draftkings",min_books=5,rec_min=1.5,selector="max_edge"),
    "S_MAXMINP": dict(family="selector",rule="V2 pool; maximize weaker leg probability",confirm="bovada+draftkings",min_books=5,rec_min=1.5,selector="max_min_prob"),
    "S_MAXPERSIST": dict(family="selector",rule="V2 pool; maximize minimum persistence",confirm="bovada+draftkings",min_books=5,rec_min=1.5,selector="max_persist"),
    "C_NOCONFIRM": dict(family="control",rule="Pinnacle fair + >=5 books; no BOV/DK confirmation",confirm="none",min_books=5,rec_min=1.5,selector="max_joint"),
    "C_RANDOM_V2": dict(family="control",rule="Deterministic random positive-edge pair from V2 pool",confirm="bovada+draftkings",min_books=5,rec_min=1.5,selector="random"),
}


def _f(x,d=None):
    try:return float(x)
    except (TypeError,ValueError):return d


def _i(x,d=0):
    try:return int(float(x))
    except (TypeError,ValueError):return d


def _leg_key(r):
    return (r.get("event_id"),r.get("market"),r.get("player"),str(r.get("point","")),r.get("side"))


def _line_key(r):
    return _leg_key(r)+(r.get("book"),)


def _target_board(rows,now):
    local=now.astimezone(NY); dates=defaultdict(set)
    for r in rows:
        try:d=parse_iso(r["commence_time"]).astimezone(NY).date()
        except Exception:continue
        if d>=local.date(): dates[d].add(r["event_id"])
    if not dates:return "",set()
    target=min(dates)
    return target.isoformat(),dates[target]


def _week_key(date_s):
    d=dt.date.fromisoformat(date_s); return (d-dt.timedelta(days=d.weekday())).isoformat()


def _persistence(event_ids,cutoff_ts):
    counts=defaultdict(set)
    for r in read_rows("candidates"):
        if r.get("event_id") not in event_ids:continue
        if r.get("ts","")>cutoff_ts:continue
        counts[_leg_key(r)].add(r.get("ts",""))
    return {k:len(v) for k,v in counts.items()}


def _meta_index():
    out={}
    for r in read_rows("current_line_meta"):
        out[(r.get("event_id"),r.get("market"),r.get("player"),str(r.get("point","")),r.get("side"),r.get("book"))]=r
    return out


def _confirm_ok(books,rule):
    books=set(books)
    if rule=="bovada+draftkings":return {"bovada","draftkings"}.issubset(books)
    if rule=="bovada":return "bovada" in books
    if rule=="draftkings":return "draftkings" in books
    if rule=="any2":return len(books&parlay_lab.CONFIRM_BOOKS)>=2
    if rule=="any3":return len(books&parlay_lab.CONFIRM_BOOKS)>=3
    if rule=="none":return True
    return False


def _fresh(meta,row,now,seconds):
    m=meta.get(_line_key(row))
    if not m:return False
    stamp=m.get("last_seen_at") or m.get("market_last_update") or m.get("last_change_at")
    try:return 0 <= (now-parse_iso(stamp)).total_seconds() <= seconds
    except Exception:return False


def _main(meta,row):
    m=meta.get(_line_key(row)); return bool(m and m.get("line_type")=="main")


def _build(cfg,rows,now,persist,meta):
    all_by_leg=defaultdict(dict); gated=defaultdict(dict)
    fair_lo,fair_hi=cfg.get("fair",(.30,.70))
    min_books=cfg.get("min_books",5); rec_min=cfg.get("rec_min",1.5)
    for r in rows:
        k=_leg_key(r); all_by_leg[k][r["book"]]=r
        fp=_f(r.get("fair_prob")); ev=_f(r.get("ev_pct")); nb=_i(r.get("n_books"))
        if fp is None or ev is None or not(fair_lo<=fp<=fair_hi) or ev<GATE["min_ev_pct"] or nb<min_books:continue
        if r.get("fair_source")!="pinnacle":continue
        if cfg.get("fresh") and not _fresh(meta,r,now,cfg["fresh"]):continue
        if cfg.get("mainline") and not _main(meta,r):continue
        gated[k][r["book"]]=r
    legs=[]
    for k,by_book in gated.items():
        books=set(by_book)
        if not _confirm_ok(books,cfg.get("confirm","bovada+draftkings")):continue
        if k[1]=="player_receptions":
            pt=_f(k[3])
            if pt is None or pt<=rec_min:continue
        if persist.get(k,0)<cfg.get("persist",0):continue
        rs=list(by_book.values()); fps=[_f(x.get("fair_prob")) for x in rs if _f(x.get("fair_prob")) is not None]
        if not fps:continue
        rep=max(rs,key=lambda r:(r["book"]=="bovada",r["book"]=="draftkings",r.get("ts","")))
        legs.append(dict(event_id=k[0],market=k[1],player=k[2],point=k[3],side=k[4],
                         fair_prob=sum(fps)/len(fps),n_books=max(_i(x.get("n_books")) for x in rs),
                         confirm_books=sorted(books&parlay_lab.CONFIRM_BOOKS),home=rep.get("home",""),away=rep.get("away",""),
                         persistence=persist.get(k,0)))
    pairs=[p for p in parlay_lab._pairs(legs,all_by_leg) if p["edge"]>=cfg.get("pair_edge",0)]
    return legs,pairs


def _select(pairs,selector,seed):
    if not pairs:return []
    if selector=="max_edge":return [max(pairs,key=lambda p:(p["edge"],p["joint"]))]
    if selector=="max_min_prob":return [max(pairs,key=lambda p:(min(p["a"]["fair_prob"],p["b"]["fair_prob"]),p["joint"]))]
    if selector=="max_persist":return [max(pairs,key=lambda p:(min(p["a"].get("persistence",0),p["b"].get("persistence",0)),p["joint"]))]
    if selector=="random":
        h=int(hashlib.sha256(seed.encode()).hexdigest()[:16],16); return [pairs[h%len(pairs)]]
    return [max(pairs,key=lambda p:(p["joint"],p["edge"]))]


def _selection_key(p):
    return "||".join(sorted("|".join(map(str,(x["event_id"],x["market"],x["player"],x["point"],x["side"]))) for x in (p["a"],p["b"])))


def _row(variant,family,rule,selector,slip_no,qualified_legs,valid_pairs,p,target_date,snapshot_ts,meta_coverage):
    base=dict(ts=iso(),snapshot_ts=snapshot_ts,target_date=target_date,week_key=_week_key(target_date),
              variant=variant,family=family,rule=rule,selector=selector,slip_no=slip_no,
              qualified_legs=qualified_legs,valid_pairs=valid_pairs,persistence_min="",meta_coverage=round(meta_coverage,3),
              resolution="",pnl="",brier="",calibration_error="",settled_ts="",note="SHADOW_DIAGNOSTIC · never an official forward decision")
    if not p:
        return dict(base,decision="no_play",selection_key="",legs="[]",book="",price="",fair_joint_prob="",
                    break_even_prob="",model_edge_pct="")
    ls=[]
    for leg,price in ((p["a"],p["price_a"]),(p["b"],p["price_b"])):
        ls.append(dict(event_id=leg["event_id"],market=leg["market"],player=leg["player"],point=leg["point"],side=leg["side"],
                       fair_prob=round(leg["fair_prob"],6),price=price,book=p["book"],persistence=leg.get("persistence","")))
    return dict(base,decision="play",selection_key=_selection_key(p),legs=json.dumps(ls,separators=(",",":")),
                book=p["book"],price=p["price"],fair_joint_prob=round(p["joint"],6),
                break_even_prob=round(p["break_even"],6),model_edge_pct=round(p["edge"],3),
                persistence_min=min(p["a"].get("persistence",0),p["b"].get("persistence",0)))


def observe(now=None):
    now=now or utcnow(); current=read_rows("current_lines")
    if not current:return 0
    snapshot_ts=max((r.get("ts","") for r in current),default="")
    target_date,eids=_target_board(current,now)
    if not target_date:return 0
    rows=[r for r in current if r.get("event_id") in eids]
    existing={(r.get("snapshot_ts"),r.get("variant"),r.get("slip_no")) for r in read_rows("shadow_snapshots")}
    persist=_persistence(eids,snapshot_ts); meta=_meta_index()
    meta_hits=sum(1 for r in rows if _line_key(r) in meta); coverage=(meta_hits/len(rows)) if rows else 0
    out=[]

    all_by_leg=defaultdict(dict); gated=defaultdict(dict)
    for r in rows:
        all_by_leg[parlay_lab._leg_key(r)][r["book"]]=r
        if parlay_lab._passes_gate(r) and r.get("fair_source")=="pinnacle":gated[parlay_lab._leg_key(r)][r["book"]]=r
    for model in parlay_lab.RESEARCH_MODELS:
        result=parlay_lab.evaluate_model(model,gated,all_by_leg)
        sels=result["selections"] or [None]
        for i,p in enumerate(sels,1):
            k=(snapshot_ts,"OFF_"+model,str(i))
            if k in existing:continue
            out.append(_row("OFF_"+model,"official_mirror",parlay_lab.MODEL_META[model]["detail"],"official",i,
                            result["qualified_legs"],result["valid_pairs"],p,target_date,snapshot_ts,coverage))

    for name,cfg in VARIANTS.items():
        legs,pairs=_build(cfg,rows,now,persist,meta)
        sels=_select(pairs,cfg["selector"],snapshot_ts+"|"+name) or [None]
        for i,p in enumerate(sels,1):
            k=(snapshot_ts,name,str(i))
            if k in existing:continue
            out.append(_row(name,cfg["family"],cfg["rule"],cfg["selector"],i,len(legs),len(pairs),p,target_date,snapshot_ts,coverage))
    n=append_rows("shadow_snapshots",out,FIELDS)
    print("shadow observe",json.dumps(dict(ts=iso(now),snapshot_ts=snapshot_ts,target_date=target_date,rows=n,meta_coverage=coverage),sort_keys=True))
    return n


def _grade(row,grader):
    try:legs=json.loads(row.get("legs","[]"))
    except Exception:return None
    if not legs:return None
    rs=[grader.leg(l,l["event_id"],row.get("book","")) for l in legs]
    if "lost" in rs:return "lost",rs
    if any(x is None for x in rs):return None
    if all(x=="won" for x in rs):return "won",rs
    if "won" in rs:return "won_reduced",rs
    return ("void" if all(x=="void" for x in rs) else "push"),rs


def settle(now=None):
    now=now or utcnow(); rows=read_rows("shadow_snapshots")
    if not rows:return 0
    grader=slips.Grader(read_rows("results")); changed=0
    for r in rows:
        if r.get("decision")!="play" or r.get("resolution"):continue
        g=_grade(r,grader)
        if g is None:continue
        res,leg_results=g
        stake=STAKE_USD
        if res=="lost":pnl=-stake
        elif res=="won":pnl=(am_to_dec(int(float(r["price"])))-1)*stake
        elif res=="won_reduced":
            legs=json.loads(r["legs"]); dec=1.0
            for l,x in zip(legs,leg_results):
                if x=="won":dec*=am_to_dec(int(float(l["price"])))
            pnl=(dec-1)*stake
        else:pnl=0.0
        p=_f(r.get("fair_joint_prob"))
        y=1.0 if res=="won" else (0.0 if res=="lost" else None)
        r["resolution"]=res;r["pnl"]=round(pnl,2);r["settled_ts"]=iso(now)
        if p is not None and y is not None:
            r["brier"]=round((p-y)**2,6);r["calibration_error"]=round(y-p,6)
        changed+=1
    if changed:
        with open(csv_path("shadow_snapshots"),"w",newline="") as f:
            w=csv.DictWriter(f,fieldnames=FIELDS,extrasaction="ignore");w.writeheader();w.writerows(rows)
    print("shadow settle",json.dumps(dict(ts=iso(now),settled=changed),sort_keys=True));return changed


def _metrics(rows):
    plays=[r for r in rows if r.get("decision")=="play"]
    settled=[r for r in plays if r.get("resolution") in ("won","lost")]
    wins=sum(r["resolution"]=="won" for r in settled);losses=sum(r["resolution"]=="lost" for r in settled)
    expected=sum(_f(r.get("fair_joint_prob"),0) for r in settled)
    b=[_f(r.get("brier")) for r in settled if _f(r.get("brier")) is not None]
    pnl=sum(_f(r.get("pnl"),0) for r in settled);stake=STAKE_USD*len(settled)
    unique=len({(r.get("target_date"),r.get("selection_key")) for r in settled})
    return dict(obs=len(settled),unique=unique,wins=wins,losses=losses,expected=expected,
                brier=(sum(b)/len(b) if b else None),pnl=pnl,roi=(100*pnl/stake if stake else None))


def write_report():
    rows=read_rows("shadow_snapshots"); by=defaultdict(list)
    for r in rows:by[r.get("variant","")].append(r)
    trs=[]
    for name in sorted(by):
        m=_metrics(by[name]);rule=(by[name][0].get("rule","") if by[name] else "")
        b="—" if m["brier"] is None else f'{m["brier"]:.3f}'
        roi="—" if m["roi"] is None else f'{m["roi"]:+.1f}%'
        pnl_txt="$"+f'{m["pnl"]:+.2f}'
        trs.append(f'<tr><td><b>{html.escape(name)}</b><small>{html.escape(rule)}</small></td><td>{m["obs"]}</td><td>{m["unique"]}</td><td>{m["wins"]}-{m["losses"]}</td><td>{m["expected"]:.2f}</td><td>{b}</td><td>{pnl_txt}</td><td>{roi}</td></tr>')
    page=f'''<!doctype html><meta charset="utf-8"><title>Prop Lab Diagnostics</title><style>
body{{font:14px/1.45 system-ui;max-width:1100px;margin:auto;padding:22px;color:#18181b}}h1{{font-size:24px}}p{{color:#666}}table{{width:100%;border-collapse:collapse}}th,td{{padding:8px;border-bottom:1px solid #e5e5e5;text-align:right}}th:first-child,td:first-child{{text-align:left}}small{{display:block;color:#777;font-weight:400;max-width:400px}}.note{{background:#f6f6f7;padding:12px;border-radius:10px}}</style>
<h1>Shadow diagnostics</h1><p>Gate, selector and timing observations. These are repeated snapshot observations, not official forward wagers.</p>
<div class="note"><b>Interpretation:</b> expected wins, Brier score and CLV should lead P&amp;L. Repeated snapshots of the same selection are not independent samples.</div>
<table><thead><tr><th>Variant</th><th>Settled obs</th><th>Unique</th><th>W-L</th><th>Expected W</th><th>Brier</th><th>P&amp;L</th><th>ROI</th></tr></thead><tbody>{''.join(trs)}</tbody></table>'''
    with open(os.path.join(DOCS,"diagnostics.html"),"w",encoding="utf-8") as f:f.write(page)
    return page


def run_observe(now=None):
    n=observe(now);write_report();return n


def run_settle(now=None):
    n=settle(now);write_report();return n
