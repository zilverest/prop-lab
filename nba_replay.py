"""NBA Phase 1 causal pseudo-live replay."""
from __future__ import annotations
import datetime as dt
import hashlib
import json
import os
import pathlib
import statistics
from collections import Counter, defaultdict
import nba_audit

SPORT = "basketball_nba"
CORE_MARKETS = ("player_points", "player_rebounds", "player_assists", "player_threes")
CUTOFF_HOURS = (8.0, 4.0, 2.0, 1.0, 0.5)
MIN_FAIR, MAX_FAIR, MIN_EV, MIN_LOO_REFS = 0.30, 0.70, 0.03, 2
STAKE = 5.0
MAX_EVENTS = int(os.environ.get("NBA_REPLAY_MAX_EVENTS", "20"))
ROOT = pathlib.Path(__file__).resolve().parent
OUT_DIR = ROOT / "research" / "nba" / "phase1"
DATA_DIR = ROOT / "data" / "nba"

def am_to_prob(price):
    p=float(price)
    return (-p)/((-p)+100.0) if p<0 else 100.0/(p+100.0)

def am_to_decimal(price):
    p=float(price)
    return 1.0+(100.0/(-p) if p<0 else p/100.0)

def no_vig_prob(over_price, under_price, side):
    po,pu=am_to_prob(over_price),am_to_prob(under_price)
    total=po+pu
    if total<=0:return None
    return po/total if side.lower()=="over" else pu/total

def parse_time(value): return nba_audit.parse_iso(value)

def bookmaker_nodes(payload):
    for node in nba_audit.walk(payload):
        books=node.get("bookmakers")
        if isinstance(books,list): yield books

def history_records(payload):
    rows=[]; seen=set()
    for books in bookmaker_nodes(payload):
        for book in books:
            if not isinstance(book,dict):continue
            bkey=str(book.get("key") or book.get("title") or "")
            for market in book.get("markets",[]) or []:
                if not isinstance(market,dict):continue
                mkey=market.get("key") or market.get("market") or ""
                ltype=market.get("line_type") or ""
                if mkey not in CORE_MARKETS:continue
                for outcome in market.get("outcomes",[]) or []:
                    if not isinstance(outcome,dict):continue
                    player=outcome.get("description") or outcome.get("player") or outcome.get("player_name") or ""
                    side=outcome.get("name") or outcome.get("side") or ""
                    oid=outcome.get("outcome_id"); pid=outcome.get("player_id")
                    for snap in outcome.get("snapshots",[]) or []:
                        if not isinstance(snap,dict):continue
                        stamp=snap.get("recorded_at") or snap.get("ts") or snap.get("timestamp")
                        price=snap.get("price")
                        if price is None:price=snap.get("price_american")
                        point=snap.get("point")
                        if point is None:point=outcome.get("point")
                        key=(bkey,mkey,str(oid),str(stamp),str(price),str(point))
                        if key in seen:continue
                        seen.add(key)
                        rows.append(dict(book=bkey,market=mkey,line_type=ltype,player=player,side=side,
                                         point=point,price=price,recorded_at=stamp,outcome_id=oid,player_id=pid))
    return rows

def closing_map(payload):
    out={}
    for books in bookmaker_nodes(payload):
        for book in books:
            if not isinstance(book,dict):continue
            bkey=str(book.get("key") or book.get("title") or "")
            for market in book.get("markets",[]) or []:
                mkey=market.get("key") or ""
                if mkey not in CORE_MARKETS:continue
                for outcome in market.get("outcomes",[]) or []:
                    oid=outcome.get("outcome_id")
                    if oid is None:continue
                    out[str(oid)]=dict(book=bkey,market=mkey,
                        closing_price=outcome.get("closing_price",outcome.get("price")),
                        closing_point=outcome.get("closing_point",outcome.get("point")),
                        closing_at=outcome.get("closing_at"),line_type=market.get("line_type") or "")
    return out

def results_map(payload):
    out={}
    for node in nba_audit.walk(payload):
        outcomes=node.get("outcomes")
        if not isinstance(outcomes,list):continue
        market=node.get("key") or node.get("market") or node.get("market_key") or ""
        if market not in CORE_MARKETS:continue
        for outcome in outcomes:
            if not isinstance(outcome,dict):continue
            oid=outcome.get("outcome_id")
            if oid is None:continue
            out[str(oid)]=dict(resolution=outcome.get("resolution"),
                               actual_value=outcome.get("actual_value"),market=market)
    return out

def latest_at(records,cutoff):
    latest={}
    for row in records:
        stamp=parse_time(row.get("recorded_at"))
        if stamp is None or stamp>cutoff:continue
        key=(row["book"],row["market"],row["player"],str(row["side"]).lower(),str(row["outcome_id"]))
        old=latest.get(key)
        if old is None or parse_time(old["recorded_at"])<stamp:latest[key]=row
    return list(latest.values())

def exact_two_way_books(rows):
    groups=defaultdict(dict)
    for row in rows:
        side=str(row.get("side") or "").lower()
        if side not in ("over","under"):continue
        if row.get("point") in (None,"") or row.get("price") in (None,""):continue
        if row.get("line_type")!="main":continue
        key=(row["book"],row["market"],row["player"],str(row["point"]))
        groups[key][side]=row
    return {k:v for k,v in groups.items() if "over" in v and "under" in v}

def reference_table(pairs):
    by_line=defaultdict(dict)
    for (book,market,player,point),sides in pairs.items():
        try:
            over=no_vig_prob(sides["over"]["price"],sides["under"]["price"],"over")
            under=no_vig_prob(sides["over"]["price"],sides["under"]["price"],"under")
        except Exception:continue
        if over is None:continue
        by_line[(market,player,point)][book]=dict(over=over,under=under,
                                                  over_row=sides["over"],under_row=sides["under"])
    return by_line

def candidate_pool(rows,reference):
    table=reference_table(exact_two_way_books(rows)); candidates=[]
    for (market,player,point),books in table.items():
        for candidate_book,info in books.items():
            for side in ("over","under"):
                row=info[side+"_row"]; refs=[]; fair=None
                if reference=="LOO_CONSENSUS":
                    vals=[]
                    for book,ref in books.items():
                        if book==candidate_book:continue
                        vals.append(float(ref[side]));refs.append(book)
                    if len(vals)<MIN_LOO_REFS:continue
                    fair=statistics.median(vals)
                elif reference=="BOVADA_REF":
                    if candidate_book=="bovada" or "bovada" not in books:continue
                    fair=float(books["bovada"][side]);refs=["bovada"]
                elif reference=="NOVIG_REF":
                    if candidate_book=="novig" or "novig" not in books:continue
                    fair=float(books["novig"][side]);refs=["novig"]
                else:raise ValueError(reference)
                if not (MIN_FAIR<=fair<=MAX_FAIR):continue
                try:
                    ev=fair*am_to_decimal(row["price"])-1.0
                    implied=am_to_prob(row["price"])
                except Exception:continue
                if ev<MIN_EV:continue
                candidates.append(dict(reference=reference,book=candidate_book,market=market,
                    player=player,point=point,side=side.title(),price=row["price"],
                    outcome_id=row.get("outcome_id"),player_id=row.get("player_id"),
                    fair_prob=fair,candidate_implied_prob=implied,estimated_ev=ev,
                    reference_books=sorted(refs),reference_book_count=len(refs),
                    recorded_at=row.get("recorded_at")))
    candidates.sort(key=lambda x:(x["estimated_ev"],x["fair_prob"]),reverse=True)
    return candidates

def identity(c):
    return "|".join(map(str,(c.get("market"),c.get("player"),c.get("point"),c.get("side"),c.get("book"))))

def deterministic_pick(pool,seed):
    if not pool:return None
    digest=hashlib.sha256(seed.encode()).hexdigest()
    return pool[int(digest[:12],16)%len(pool)]

def decision_row(event,cutoff_name,cutoff_hours,candidate,variant,pool_size,persistence):
    base=dict(event_id=str(event.get("id")),commence_time=event.get("commence_time"),
              home=event.get("home_team"),away=event.get("away_team"),
              cutoff=cutoff_name,cutoff_hours=cutoff_hours,variant=variant,pool_size=pool_size,
              decision="no_play" if candidate is None else "play",persistence=0)
    if candidate is None:return base
    base.update(candidate);base["selection_key"]=identity(candidate)
    base["persistence"]=persistence.get(identity(candidate),0)
    return base

def grade(decision,closes,results):
    row=dict(decision)
    if row.get("decision")!="play":return row
    oid=str(row.get("outcome_id") or "");close=closes.get(oid);result=results.get(oid)
    row["closing_available"]=bool(close);row["result_available"]=bool(result)
    row["closing_price"]=close.get("closing_price") if close else None
    row["closing_point"]=close.get("closing_point") if close else None
    row["closing_at"]=close.get("closing_at") if close else None
    row["same_point"]=bool(close and str(close.get("closing_point"))==str(row.get("point")))
    row["clv_implied_pp"]=None;row["beat_close"]=None
    if row["same_point"] and close.get("closing_price") not in (None,""):
        try:
            taken=am_to_prob(row["price"]);closing=am_to_prob(close["closing_price"])
            row["clv_implied_pp"]=100.0*(closing-taken);row["beat_close"]=closing>taken
        except Exception:pass
    resolution=result.get("resolution") if result else None
    row["resolution"]=resolution;row["actual_value"]=result.get("actual_value") if result else None
    y=1.0 if resolution=="won" else 0.0 if resolution=="lost" else None
    row["brier"]=(float(row["fair_prob"])-y)**2 if y is not None else None
    row["calibration_error"]=y-float(row["fair_prob"]) if y is not None else None
    row["pnl"]=None
    if resolution=="won":row["pnl"]=STAKE*(am_to_decimal(row["price"])-1.0)
    elif resolution=="lost":row["pnl"]=-STAKE
    elif resolution in ("push","void"):row["pnl"]=0.0
    return row

def metric_summary(rows):
    plays=[r for r in rows if r.get("decision")=="play"]
    settled=[r for r in plays if r.get("resolution") in ("won","lost")]
    clv=[float(r["clv_implied_pp"]) for r in plays if r.get("clv_implied_pp") is not None]
    brier=[float(r["brier"]) for r in settled if r.get("brier") is not None]
    beat=[bool(r.get("beat_close")) for r in plays if r.get("beat_close") is not None]
    wins=sum(r.get("resolution")=="won" for r in settled);losses=sum(r.get("resolution")=="lost" for r in settled)
    pnl=sum(float(r.get("pnl") or 0.0) for r in plays if r.get("pnl") is not None);stake=STAKE*len(settled)
    return dict(plays=len(plays),settled=len(settled),wins=wins,losses=losses,
                hit_rate=wins/len(settled) if settled else None,
                avg_clv_implied_pp=statistics.mean(clv) if clv else None,
                beat_close_rate=sum(beat)/len(beat) if beat else None,
                brier=statistics.mean(brier) if brier else None,pnl=pnl,
                roi=pnl/stake if stake else None,
                unique_underlying=len({r.get("selection_key") for r in plays if r.get("selection_key")}))

def replay_event(event):
    eid=str(event.get("id"));markets=",".join(CORE_MARKETS)
    history=nba_audit.request_json(f"/sports/{SPORT}/events/{eid}/odds/history",
        {"markets":markets,"relative_from":"-12h","relative_to":"0","interval":"30m","changes_only":"false"})
    closing=nba_audit.request_json(f"/sports/{SPORT}/events/{eid}/odds/closing",{"markets":markets})
    results=nba_audit.request_json(f"/sports/{SPORT}/events/{eid}/results",{"markets":markets})
    if not history["ok"]:
        return dict(event=event,status="history_unavailable",error=history["body"],decisions=[])
    hist_rows=history_records(history["body"]);closes=closing_map(closing["body"]) if closing["ok"] else {}
    graded=results_map(results["body"]) if results["ok"] else {}
    tip=parse_time(event.get("commence_time"))
    if tip is None:return dict(event=event,status="bad_commence_time",decisions=[])
    decisions=[];persistence=Counter()
    for hours in CUTOFF_HOURS:
        cutoff=tip-dt.timedelta(hours=hours);name=f"T-{hours:g}h";current=latest_at(hist_rows,cutoff)
        loo=candidate_pool(current,"LOO_CONSENSUS");bov=candidate_pool(current,"BOVADA_REF");nov=candidate_pool(current,"NOVIG_REF")
        for cand in loo:persistence[identity(cand)]+=1
        top_loo=loo[0] if loo else None;top_bov=bov[0] if bov else None;top_nov=nov[0] if nov else None
        p2=next((c for c in loo if persistence[identity(c)]>=2),None)
        p3=next((c for c in loo if persistence[identity(c)]>=3),None)
        rand=deterministic_pick(loo,f"{eid}|{name}|C_RANDOM_B0")
        raw=[
            decision_row(event,name,hours,top_loo,"B0_LOO",len(loo),persistence),
            decision_row(event,name,hours,top_bov,"B0_BOVADA",len(bov),persistence),
            decision_row(event,name,hours,top_nov,"B0_NOVIG",len(nov),persistence),
            decision_row(event,name,hours,p2,"PERSIST2",len(loo),persistence),
            decision_row(event,name,hours,p3,"PERSIST3",len(loo),persistence),
            decision_row(event,name,hours,rand,"C_RANDOM_B0",len(loo),persistence)]
        decisions.extend(grade(row,closes,graded) for row in raw)
    return dict(event={k:event.get(k) for k in ("id","commence_time","home_team","away_team","status")},
                status="ok",history_records=len(hist_rows),closing_outcomes=len(closes),
                result_outcomes=len(graded),decisions=decisions)

def completed_events():
    resp=nba_audit.request_json(f"/sports/{SPORT}/scores",{"days_from":30})
    if not resp["ok"] or not isinstance(resp["body"],list):
        raise RuntimeError("NBA scores unavailable: "+json.dumps(resp["body"]))
    rows=[r for r in resp["body"] if isinstance(r,dict) and r.get("status")=="final"]
    rows.sort(key=lambda r:str(r.get("commence_time","")))
    return rows[-MAX_EVENTS:]

def write_jsonl(path,rows):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("w",encoding="utf-8") as fh:
        for row in rows:fh.write(json.dumps(row,sort_keys=True)+"\n")

def run():
    events=completed_events();replayed=[replay_event(e) for e in events]
    decisions=[d for item in replayed for d in item.get("decisions",[])]
    variants=("B0_LOO","B0_BOVADA","B0_NOVIG","PERSIST2","PERSIST3","C_RANDOM_B0")
    by_variant={v:metric_summary([r for r in decisions if r.get("variant")==v]) for v in variants}
    by_cutoff={}
    for cutoff in [f"T-{h:g}h" for h in CUTOFF_HOURS]:
        by_cutoff[cutoff]={v:metric_summary([r for r in decisions if r.get("variant")==v and r.get("cutoff")==cutoff]) for v in variants}
    report=dict(phase="NBA-1 causal replay",generated_at=nba_audit.iso(),
        evidence_class="PRESEASON_REPLAY_DIAGNOSTIC",sport=SPORT,
        preregistered=dict(markets=list(CORE_MARKETS),cutoffs_hours=list(CUTOFF_HOURS),
                           min_fair=MIN_FAIR,max_fair=MAX_FAIR,min_ev=MIN_EV,
                           min_loo_reference_books=MIN_LOO_REFS,main_line_only=True),
        events_requested=len(events),events_ok=sum(item.get("status")=="ok" for item in replayed),
        events=replayed,summary_by_variant=by_variant,summary_by_cutoff=by_cutoff,
        interpretation_guardrails=[
            "Preseason replay is diagnostic and is not regular-season validation.",
            "Closing lines and results are joined only after causal selections are constructed.",
            "Repeated timing observations of one underlying selection are correlated.",
            "P&L is secondary to CLV and calibration.",
            "No variant may be promoted from this replay alone."])
    return report,decisions

def render_markdown(report):
    lines=["# NBA Phase 1 - Causal Preseason Replay","",
           "Generated: "+report["generated_at"],"",
           "**Evidence class: PRESEASON_REPLAY_DIAGNOSTIC**","",
           "Each decision uses only snapshots available at or before its historical cutoff. Closing lines and results are joined afterward.","",
           "Events requested: **"+str(report["events_requested"])+"**  ",
           "Events replayed successfully: **"+str(report["events_ok"])+"**","",
           "## Variant summary","",
           "| Variant | Plays | W-L | Avg CLV pp | Beat close | Brier | Paper P&L | ROI | Unique |",
           "|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for variant,m in report["summary_by_variant"].items():
        clv="—" if m["avg_clv_implied_pp"] is None else f"{m['avg_clv_implied_pp']:+.2f}"
        beat="—" if m["beat_close_rate"] is None else f"{100*m['beat_close_rate']:.1f}%"
        brier="—" if m["brier"] is None else f"{m['brier']:.3f}"
        roi="—" if m["roi"] is None else f"{100*m['roi']:.1f}%"
        lines.append(f"| {variant} | {m['plays']} | {m['wins']}-{m['losses']} | {clv} | {beat} | {brier} | USD {m['pnl']:+.2f} | {roi} | {m['unique_underlying']} |")
    lines+=["","## Timing summary",""]
    for cutoff,variants in report["summary_by_cutoff"].items():
        lines+=["### "+cutoff,"","| Variant | Plays | Avg CLV pp | Beat close | Brier |","|---|---:|---:|---:|---:|"]
        for variant,m in variants.items():
            clv="—" if m["avg_clv_implied_pp"] is None else f"{m['avg_clv_implied_pp']:+.2f}"
            beat="—" if m["beat_close_rate"] is None else f"{100*m['beat_close_rate']:.1f}%"
            brier="—" if m["brier"] is None else f"{m['brier']:.3f}"
            lines.append(f"| {variant} | {m['plays']} | {clv} | {beat} | {brier} |")
        lines.append("")
    lines+=["## Guardrails",""]
    lines.extend("- "+x for x in report["interpretation_guardrails"])
    lines+=["","## Next gate","",
            "Use this replay to verify plumbing and screen hypotheses only. Keep collecting NBA snapshots permanently. The 2026-27 regular-season opener begins the formal forward evidence stream.",""]
    return "\n".join(lines)

def main():
    report,decisions=run();OUT_DIR.mkdir(parents=True,exist_ok=True);DATA_DIR.mkdir(parents=True,exist_ok=True)
    (OUT_DIR/"NBA_PHASE1_REPLAY.json").write_text(json.dumps(report,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    (OUT_DIR/"NBA_PHASE1_REPLAY.md").write_text(render_markdown(report),encoding="utf-8")
    write_jsonl(DATA_DIR/"preseason_replay_decisions.jsonl",decisions)
    print(json.dumps(dict(events_ok=report["events_ok"],events_requested=report["events_requested"],
                          summary_by_variant=report["summary_by_variant"]),sort_keys=True))

if __name__=="__main__":main()
