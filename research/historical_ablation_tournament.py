"""Complete historical cross-game ablation + selector tournament.

Retrospective development evidence only. Official V1-V8 decisions are never changed.
"""
from __future__ import annotations

import bisect
import csv
import datetime as dt
import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

from common import *
import parlay_lab
import slips

NY=ZoneInfo("America/New_York")
OUT=ROOT/"research"/"historical_ablation_tournament"
OUT.mkdir(parents=True,exist_ok=True)

OFFICIAL=("V1","V2","V3","V4","V5","V6","V8")

VARIANTS={
    "A_MIN4": dict(family="gate",rule="V2 but min_books=4",confirm="bovada+draftkings",min_books=4,rec_min=1.5,selector="max_joint"),
    "A_NODEPTH": dict(family="gate",rule="V2 without reception-depth gate",confirm="bovada+draftkings",min_books=5,rec_min=-1,selector="max_joint"),
    "A_FAIR3565": dict(family="gate",rule="V2 with fair range 35-65%",confirm="bovada+draftkings",min_books=5,rec_min=1.5,fair=(.35,.65),selector="max_joint"),
    "A_EDGE3": dict(family="gate",rule="V2 plus pair edge >=3%",confirm="bovada+draftkings",min_books=5,rec_min=1.5,pair_edge=3,selector="max_joint"),
    "A_EDGE5": dict(family="gate",rule="V2 plus pair edge >=5%",confirm="bovada+draftkings",min_books=5,rec_min=1.5,pair_edge=5,selector="max_joint"),
    "A_PERSIST2": dict(family="gate",rule="V2; both legs seen >=2 candidate snapshots",confirm="bovada+draftkings",min_books=5,rec_min=1.5,persist=2,selector="max_joint"),
    "A_PERSIST3": dict(family="gate",rule="V2; both legs seen >=3 candidate snapshots",confirm="bovada+draftkings",min_books=5,rec_min=1.5,persist=3,selector="max_joint"),
    "S_MAXEDGE": dict(family="selector",rule="V2 pool; maximize reconstructed edge",confirm="bovada+draftkings",min_books=5,rec_min=1.5,selector="max_edge"),
    "S_MAXMINP": dict(family="selector",rule="V2 pool; maximize weaker-leg fair probability",confirm="bovada+draftkings",min_books=5,rec_min=1.5,selector="max_min_prob"),
    "S_MAXPERSIST": dict(family="selector",rule="V2 pool; maximize minimum persistence",confirm="bovada+draftkings",min_books=5,rec_min=1.5,selector="max_persist"),
    "C_NOCONFIRM": dict(family="control",rule="Pinnacle fair + >=5 books; no BOV/DK confirmation",confirm="none",min_books=5,rec_min=1.5,selector="max_joint"),
    "C_RANDOM_V2": dict(family="control",rule="Deterministic random positive-edge pair from V2 pool",confirm="bovada+draftkings",min_books=5,rec_min=1.5,selector="random"),
}

UNAVAILABLE={
    "A_FRESH300":"Historical quote freshness metadata was not archived.",
    "A_MAINLINE":"Historical line_type metadata was not archived.",
    "STEAM":"Historical movement/steam responses were not archived.",
    "CONTEXT":"Historical game-context snapshots were not archived.",
}

KNOWN_DEV={
    "2026-09-20": {("Justin Jefferson","player_receptions","6.5","Under"),
                   ("Tyler Shough","player_pass_interceptions","0.5","Under")},
    "2026-09-27": {("Javonte Williams","player_receptions","2.5","Under"),
                   ("Ladd McConkey","player_receptions","4.5","Under")},
}

def f(x,d=None):
    try:return float(x)
    except (TypeError,ValueError):return d

def i(x,d=0):
    try:return int(float(x))
    except (TypeError,ValueError):return d

def line_key(r):
    return (r["event_id"],r["market"],r["player"],str(r["point"]),r["side"],r["book"])

def leg_key(r):
    return (r["event_id"],r["market"],r["player"],str(r["point"]),r["side"])

def sunday_slates():
    by=defaultdict(list)
    for e in read_rows("events"):
        try: local=parse_iso(e["commence_time"]).astimezone(NY)
        except Exception: continue
        if local.weekday()==6: by[local.date().isoformat()].append(e)
    out={}
    for ds,rows in by.items():
        if len(rows)<2:continue
        out[ds]=dict(date=ds,event_ids={r["event_id"] for r in rows},
                     first_kick=min(parse_iso(r["commence_time"]) for r in rows),events=rows)
    return dict(sorted(out.items()))

def candidate_snapshot_index(slates):
    event_to_date={eid:ds for ds,s in slates.items() for eid in s["event_ids"]}
    times={ds:set() for ds in slates}
    leg_times={ds:defaultdict(set) for ds in slates}
    for r in read_rows("candidates"):
        ds=event_to_date.get(r.get("event_id"))
        if not ds:continue
        ts=r.get("ts","")
        try:t=parse_iso(ts)
        except Exception:continue
        if t>=slates[ds]["first_kick"]:continue
        times[ds].add(ts);leg_times[ds][leg_key(r)].add(ts)
    for r in read_rows("sgp_shadow_boards"):
        ds=event_to_date.get(r.get("event_id"))
        if not ds:continue
        ts=r.get("snapshot_ts") or r.get("ts","")
        try:t=parse_iso(ts)
        except Exception:continue
        if t<slates[ds]["first_kick"]:times[ds].add(ts)
    return ({ds:sorted(v) for ds,v in times.items()},
            {ds:{k:sorted(v) for k,v in m.items()} for ds,m in leg_times.items()})

def persistence_fn(times_map,cutoff):
    return lambda k: bisect.bisect_right(times_map.get(k,[]),cutoff)

def confirm_ok(books,rule):
    books=set(books)
    if rule=="bovada+draftkings":return {"bovada","draftkings"}.issubset(books)
    if rule=="none":return True
    return False

def build_variant(cfg,state_rows,persist):
    all_by_leg=defaultdict(dict);gated=defaultdict(dict)
    lo,hi=cfg.get("fair",(.30,.70))
    for r in state_rows:
        k=leg_key(r);all_by_leg[k][r["book"]]=r
        fp=f(r.get("fair_prob"));ev=f(r.get("ev_pct"));nb=i(r.get("n_books"))
        if fp is None or ev is None:continue
        if not(lo<=fp<=hi) or ev<GATE["min_ev_pct"] or nb<cfg.get("min_books",5):continue
        if r.get("fair_source")!="pinnacle":continue
        gated[k][r["book"]]=r
    legs=[]
    for k,by_book in gated.items():
        books=set(by_book)
        if not confirm_ok(books,cfg.get("confirm","bovada+draftkings")):continue
        if k[1]=="player_receptions":
            pt=f(k[3])
            if pt is None or pt<=cfg.get("rec_min",1.5):continue
        if persist(k)<cfg.get("persist",0):continue
        rs=list(by_book.values());fps=[f(x.get("fair_prob")) for x in rs if f(x.get("fair_prob")) is not None]
        if not fps:continue
        rep=max(rs,key=lambda r:(r["book"]=="bovada",r["book"]=="draftkings",r.get("ts","")))
        legs.append(dict(event_id=k[0],market=k[1],player=k[2],point=k[3],side=k[4],
                         fair_prob=sum(fps)/len(fps),n_books=max(i(x.get("n_books")) for x in rs),
                         confirm_books=sorted(books&parlay_lab.CONFIRM_BOOKS),home=rep.get("home",""),away=rep.get("away",""),
                         persistence=persist(k)))
    pairs=[p for p in parlay_lab._pairs(legs,all_by_leg) if p["edge"]>=cfg.get("pair_edge",0)]
    return legs,pairs

def choose(pairs,selector,seed):
    if not pairs:return []
    if selector=="max_edge":return [max(pairs,key=lambda p:(p["edge"],p["joint"]))]
    if selector=="max_min_prob":return [max(pairs,key=lambda p:(min(p["a"]["fair_prob"],p["b"]["fair_prob"]),p["joint"]))]
    if selector=="max_persist":return [max(pairs,key=lambda p:(min(p["a"].get("persistence",0),p["b"].get("persistence",0)),p["joint"]))]
    if selector=="random":
        h=int(hashlib.sha256(seed.encode()).hexdigest()[:16],16);return [pairs[h%len(pairs)]]
    return [max(pairs,key=lambda p:(p["joint"],p["edge"]))]

def official_universe(rows):
    all_by_leg=defaultdict(dict);gated=defaultdict(dict)
    for r in rows:
        all_by_leg[leg_key(r)][r["book"]]=r
        if parlay_lab._passes_gate(r) and r.get("fair_source")=="pinnacle":
            gated[leg_key(r)][r["book"]]=r
    return gated,all_by_leg

def selection_key(p):
    return "" if not p else "||".join(sorted("|".join(map(str,(x["event_id"],x["market"],x["player"],x["point"],x["side"]))) for x in (p["a"],p["b"])))

def selection_parts(p):
    return set() if not p else {(x["player"],x["market"],str(x["point"]),x["side"]) for x in (p["a"],p["b"])}

def serialize_pair(p):
    if not p:return None
    return dict(key=selection_key(p),parts=sorted([list(x) for x in selection_parts(p)]),book=p["book"],price=p["price"],
                fair_joint_prob=round(p["joint"],6),break_even_prob=round(p["break_even"],6),model_edge_pct=round(p["edge"],3),
                legs=[dict(event_id=x["event_id"],market=x["market"],player=x["player"],point=x["point"],side=x["side"],
                           fair_prob=round(x["fair_prob"],6),persistence=x.get("persistence","")) for x in (p["a"],p["b"])])

def grade_pair(grader,p):
    if not p:return dict(resolution="",pnl=0.0,brier=None)
    rs=[grader.leg(dict(market=x["market"],player=x["player"],point=x["point"],side=x["side"]),x["event_id"],p["book"]) for x in (p["a"],p["b"])]
    if "lost" in rs:res="lost";pnl=-STAKE_USD;y=0.0
    elif any(x is None for x in rs):return dict(resolution="ungraded",pnl=None,brier=None,leg_results=rs)
    elif all(x=="won" for x in rs):res="won";pnl=(p["decimal"]-1)*STAKE_USD;y=1.0
    elif "won" in rs:
        res="won_reduced";dec=1.0;y=None
        for price,x in ((p["price_a"],rs[0]),(p["price_b"],rs[1])):
            if x=="won":dec*=am_to_dec(int(float(price)))
        pnl=(dec-1)*STAKE_USD
    else:res="void" if all(x=="void" for x in rs) else "push";pnl=0.0;y=None
    return dict(resolution=res,pnl=round(pnl,2),brier=((p["joint"]-y)**2 if y is not None else None),leg_results=rs)

def clv_index():
    exact=defaultdict(list);anybook=defaultdict(list)
    for r in read_rows("clv"):
        if str(r.get("matched","")).lower() not in ("true","1"):continue
        if str(r.get("closing_is_final","")).lower() not in ("true","1"):continue
        k=(r.get("event_id"),r.get("market"),r.get("player"),str(r.get("point","")),r.get("side"))
        exact[k+(r.get("book"),)].append(r);anybook[k].append(r)
    return exact,anybook

def clv_pair(p,idx):
    if not p:return dict(clv_n=0,avg_ev_vs_close=None,beat_close_pct=None)
    exact,anybook=idx;vals=[];beats=[]
    for leg in (p["a"],p["b"]):
        k=(leg["event_id"],leg["market"],leg["player"],str(leg["point"]),leg["side"])
        rr=exact.get(k+(p["book"],)) or anybook.get(k) or []
        if not rr:continue
        r=rr[-1];v=f(r.get("ev_vs_close_pct"))
        if v is not None:vals.append(v)
        b=str(r.get("beat_close","")).lower()
        if b in ("true","1","false","0"):beats.append(b in ("true","1"))
    return dict(clv_n=len(vals),avg_ev_vs_close=(sum(vals)/len(vals) if vals else None),
                beat_close_pct=(100*sum(beats)/len(beats) if beats else None))

def timing_bucket(cutoff,first_kick):
    h=(first_kick-parse_iso(cutoff)).total_seconds()/3600
    if h>24:return "T-24h+"
    if h>12:return "T-24_to_12h"
    if h>8:return "T-12_to_8h"
    if h>4:return "T-8_to_4h"
    if h>2:return "T-4_to_2h"
    if h>1:return "T-2_to_1h"
    return "T-1h"

def evaluate_board(ds,cutoff,state,slate,leg_times,grader,clv_idx):
    rows=[r for r in state.values() if r.get("event_id") in slate["event_ids"]]
    persist=persistence_fn(leg_times,cutoff);gated,all_by_leg=official_universe(rows);out={}
    for model in OFFICIAL:
        z=parlay_lab.evaluate_model(model,gated,all_by_leg);p=z["selections"][0] if z["selections"] else None
        g=grade_pair(grader,p);c=clv_pair(p,clv_idx)
        out["OFF_"+model]=dict(family="official_mirror",rule=parlay_lab.MODEL_META[model]["detail"],selector="official",
                                qualified_legs=z["qualified_legs"],valid_pairs=z["valid_pairs"],selection=serialize_pair(p),**g,**c)
    for name,cfg in VARIANTS.items():
        legs,pairs=build_variant(cfg,rows,persist);sels=choose(pairs,cfg["selector"],ds+"|"+cutoff+"|"+name);p=sels[0] if sels else None
        g=grade_pair(grader,p);c=clv_pair(p,clv_idx)
        out[name]=dict(family=cfg["family"],rule=cfg["rule"],selector=cfg["selector"],qualified_legs=len(legs),valid_pairs=len(pairs),
                       selection=serialize_pair(p),**g,**c)
    return dict(date=ds,cutoff=cutoff,timing_bucket=timing_bucket(cutoff,slate["first_kick"]),variants=out)

def reconstruct(slates,snapshot_times,leg_times,grader,clv_idx):
    event_to_date={eid:ds for ds,s in slates.items() for eid in s["event_ids"]}
    states={ds:{} for ds in slates};queues={ds:list(times) for ds,times in snapshot_times.items()};pos={ds:0 for ds in slates};evaluated={ds:[] for ds in slates}
    def eval_before(ts):
        for ds in slates:
            while pos[ds]<len(queues[ds]) and queues[ds][pos[ds]]<ts:
                cutoff=queues[ds][pos[ds]];evaluated[ds].append(evaluate_board(ds,cutoff,states[ds],slates[ds],leg_times[ds],grader,clv_idx));pos[ds]+=1
    def eval_equal(ts):
        for ds in slates:
            while pos[ds]<len(queues[ds]) and queues[ds][pos[ds]]==ts:
                cutoff=queues[ds][pos[ds]];evaluated[ds].append(evaluate_board(ds,cutoff,states[ds],slates[ds],leg_times[ds],grader,clv_idx));pos[ds]+=1
    current_ts=None;group=[]
    with open(csv_path("lines"),newline="") as fobj:
        for r in csv.DictReader(fobj):
            ts=r.get("ts","")
            if current_ts is None:current_ts=ts
            if ts!=current_ts:
                eval_before(current_ts)
                for x in group:
                    ds=event_to_date.get(x.get("event_id"))
                    if ds:states[ds][line_key(x)]=x
                eval_equal(current_ts);group=[];current_ts=ts
            group.append(r)
        if group:
            eval_before(current_ts)
            for x in group:
                ds=event_to_date.get(x.get("event_id"))
                if ds:states[ds][line_key(x)]=x
            eval_equal(current_ts)
    for ds in slates:
        while pos[ds]<len(queues[ds]):
            cutoff=queues[ds][pos[ds]];evaluated[ds].append(evaluate_board(ds,cutoff,states[ds],slates[ds],leg_times[ds],grader,clv_idx));pos[ds]+=1
    return evaluated

def pick_benchmarks(evals):
    out={}
    for ds,boards in evals.items():
        matches=[]
        if ds in KNOWN_DEV:
            for b in boards:
                sel=b["variants"].get("OFF_V2",{}).get("selection")
                if sel and {tuple(x) for x in sel["parts"]}==KNOWN_DEV[ds]:matches.append(b)
        if matches:
            target=dt.datetime.combine(dt.date.fromisoformat(ds),dt.time(8,0),tzinfo=NY).astimezone(dt.timezone.utc)
            chosen=min(matches,key=lambda b:(0 if parse_iso(b["cutoff"])>=target else 1,abs((parse_iso(b["cutoff"])-target).total_seconds())))
            reason="development-aligned"
        else:
            chosen=max(boards,key=lambda b:b["cutoff"]);reason="last-committed-pregame"
        out[ds]=dict(reason=reason,board=chosen)
    return out

def metrics(rows):
    plays=[r for r in rows if r.get("selection")];settled=[r for r in plays if r.get("resolution") in ("won","lost")]
    wins=sum(r["resolution"]=="won" for r in settled);losses=sum(r["resolution"]=="lost" for r in settled)
    pnl=sum(f(r.get("pnl"),0) for r in plays if f(r.get("pnl")) is not None);expected=sum(f(r["selection"].get("fair_joint_prob"),0) for r in settled)
    b=[f(r.get("brier")) for r in settled if f(r.get("brier")) is not None];clv=[f(r.get("avg_ev_vs_close")) for r in plays if f(r.get("avg_ev_vs_close")) is not None]
    unique=len({r["selection"]["key"] for r in plays});stake=STAKE_USD*len([r for r in plays if r.get("resolution") in ("won","lost","won_reduced")])
    return dict(plays=len(plays),settled=len(settled),wins=wins,losses=losses,unique=unique,pnl=round(pnl,2),roi=(100*pnl/stake if stake else None),
                expected_wins=expected,brier=(sum(b)/len(b) if b else None),avg_ev_vs_close=(sum(clv)/len(clv) if clv else None))

def summarize_benchmarks(benchmarks):
    rows_by_date={ds:x["board"]["variants"] for ds,x in benchmarks.items()};summary={}
    order=["OFF_"+x for x in OFFICIAL]+list(VARIANTS)
    for v in order:
        rr=[rows_by_date[ds].get(v,{}) for ds in rows_by_date];m=metrics(rr);same=both=0
        for ds,rows in rows_by_date.items():
            a=rows.get(v,{}).get("selection");b=rows.get("OFF_V2",{}).get("selection")
            if a and b:
                both+=1;same+=a["key"]==b["key"]
        m.update(both_play=both,same=same,same_pct=(100*same/both if both else None));summary[v]=m
    return summary

def all_snapshot_summary(evals):
    by=defaultdict(list)
    for ds,boards in evals.items():
        for b in boards:
            for v,r in b["variants"].items():by[v].append(dict(r,date=ds,cutoff=b["cutoff"],timing_bucket=b["timing_bucket"]))
    overall={v:metrics(rr) for v,rr in by.items()};timing={}
    for v,rr in by.items():
        g=defaultdict(list)
        for r in rr:g[r["timing_bucket"]].append(r)
        timing[v]={k:metrics(x) for k,x in g.items()}
    return overall,timing

def leg_txt(sel):
    if not sel:return "NO PLAY"
    return " + ".join(f'{x["player"]} {x["side"][0]}{x["point"]} {x["market"].replace("player_","").replace("_"," ")}' for x in sel["legs"])

def fmt(x,d=2,suffix=""):
    return "—" if x is None else f"{x:.{d}f}{suffix}"

def write_outputs(slates,snapshot_times,benchmarks,summary,overall,timing,evals):
    fields=["variant","date","benchmark_reason","cutoff","timing_bucket","decision","selection_key","legs","book","price","fair_joint_prob","model_edge_pct","resolution","pnl","brier","avg_ev_vs_close","qualified_legs","valid_pairs"]
    with open(OUT/"benchmark.csv","w",newline="") as fobj:
        w=csv.DictWriter(fobj,fieldnames=fields);w.writeheader()
        for ds,bx in benchmarks.items():
            b=bx["board"]
            for v,r in b["variants"].items():
                sel=r.get("selection")
                w.writerow(dict(variant=v,date=ds,benchmark_reason=bx["reason"],cutoff=b["cutoff"],timing_bucket=b["timing_bucket"],decision="play" if sel else "no_play",
                                selection_key=sel["key"] if sel else "",legs=json.dumps(sel["legs"],separators=(",",":")) if sel else "[]",
                                book=sel["book"] if sel else "",price=sel["price"] if sel else "",fair_joint_prob=sel["fair_joint_prob"] if sel else "",
                                model_edge_pct=sel["model_edge_pct"] if sel else "",resolution=r.get("resolution",""),pnl=r.get("pnl",""),brier=r.get("brier",""),
                                avg_ev_vs_close=r.get("avg_ev_vs_close",""),qualified_legs=r.get("qualified_legs",0),valid_pairs=r.get("valid_pairs",0)))
    payload=dict(generated_at=iso(),status="RETROSPECTIVE_DEVELOPMENT_ONLY",unavailable_historical=UNAVAILABLE,
                 slates={ds:dict(event_ids=sorted(s["event_ids"]),first_kick=iso(s["first_kick"]),snapshot_count=len(snapshot_times[ds])) for ds,s in slates.items()},
                 benchmarks={ds:dict(reason=x["reason"],cutoff=x["board"]["cutoff"],timing_bucket=x["board"]["timing_bucket"],variants=x["board"]["variants"]) for ds,x in benchmarks.items()},
                 benchmark_summary=summary,all_snapshot_summary=overall,timing_summary=timing,all_snapshots=evals)
    (OUT/"results.json").write_text(json.dumps(payload,indent=2,sort_keys=True),encoding="utf-8")

    order=["OFF_"+x for x in OFFICIAL]+list(VARIANTS)
    lines=["# Complete historical ablation + selector tournament","",
           "**RETROSPECTIVE DEVELOPMENT EVIDENCE ONLY.** Official V1–V8 forward history is unchanged.","",
           f"Usable Sunday slates: **{len(slates)}**. Historical boards evaluated: **{sum(len(x) for x in snapshot_times.values())}**.","",
           "Future-only tests excluded rather than fabricated: A_FRESH300, A_MAINLINE, steam, and context.","",
           "## Benchmark cutoffs","",
           "| Slate | Cutoff | Timing | Method | V2 selection |","|---|---|---|---|---|"]
    for ds,bx in benchmarks.items():
        b=bx["board"];lines.append(f'| {ds} | {b["cutoff"]} | {b["timing_bucket"]} | {bx["reason"]} | {leg_txt(b["variants"]["OFF_V2"].get("selection"))} |')
    lines+=["","## Benchmark tournament","",
            "| Variant | Plays | W-L | P&L | ROI | Expected W | Brier | Avg EV vs close | Same as V2 |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for v in order:
        m=summary[v];same="—" if m["same_pct"] is None else f'{m["same"]}/{m["both_play"]} ({m["same_pct"]:.0f}%)'
        lines.append(f'| {v} | {m["plays"]} | {m["wins"]}-{m["losses"]} | USD {m["pnl"]:+.2f} | {fmt(m["roi"],1,"%")} | {m["expected_wins"]:.2f} | {fmt(m["brier"],3)} | {fmt(m["avg_ev_vs_close"],2,"%")} | {same} |')
    lines+=["","## Per-slate selections",""]
    for ds,bx in benchmarks.items():
        b=bx["board"];lines+=[f"### {ds} · {b['cutoff']} · {bx['reason']}","",
            "| Variant | Qualified | Pairs | Selection | Result | P&L |","|---|---:|---:|---|---|---:|"]
        for v in order:
            r=b["variants"][v];pnl=r.get("pnl");pnl_txt="—" if pnl is None else f"USD {pnl:+.2f}"
            lines.append(f'| {v} | {r.get("qualified_legs",0)} | {r.get("valid_pairs",0)} | {leg_txt(r.get("selection"))} | {r.get("resolution") or "—"} | {pnl_txt} |')
        lines.append("")
    lines+=["## Guardrails","",
            "- Three Sunday slates are far too few to promote a model from P&L alone.",
            "- Sep 20 and Sep 27 are development-era data, not out-of-sample evidence.",
            "- Oct 4 uses the last committed pregame board because the intended freeze was lost.",
            "- Repeated snapshots are correlated observations, not independent bets.",
            "- Prefer calibration, CLV, selection stability, and matched controls over raw W/L."]
    (OUT/"REPORT.md").write_text("\n".join(lines)+"\n",encoding="utf-8")

def main():
    slates=sunday_slates();snapshot_times,leg_times=candidate_snapshot_index(slates)
    grader=slips.Grader(read_rows("results"));idx=clv_index()
    evals=reconstruct(slates,snapshot_times,leg_times,grader,idx);benchmarks=pick_benchmarks(evals)
    summary=summarize_benchmarks(benchmarks);overall,timing=all_snapshot_summary(evals)
    write_outputs(slates,snapshot_times,benchmarks,summary,overall,timing,evals)
    print(json.dumps(dict(slates=len(slates),snapshots=sum(len(x) for x in snapshot_times.values()),
                          benchmark_cutoffs={ds:x["board"]["cutoff"] for ds,x in benchmarks.items()},variants=len(summary)),sort_keys=True))

if __name__=="__main__":
    main()
