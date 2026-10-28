"""v1_v8_bridge.py — canonical V1–V8 historical + forward ledger.

This is a derived reporting layer only. It never changes model rules or frozen decisions.
It stitches the retrospective historical reconstruction to the frozen forward ledger,
preferring forward evidence on any overlapping date, and deduplicates identical execution
tickets selected by multiple models.

Cross-game ticket prices are labeled reconstructed unless a genuine quote source exists.
"""
from __future__ import annotations

import csv
import datetime as dt
import json
from collections import defaultdict
from pathlib import Path
from zoneinfo import ZoneInfo

from common import *

ROOT = Path(__file__).resolve().parent
HIST = ROOT / "research" / "historical_ablation_tournament" / "benchmark.csv"
OUT = ROOT / "research" / "v1_v8_bridge"
OUT.mkdir(parents=True, exist_ok=True)
NY = ZoneInfo("America/New_York")

MODELS = ("V1","V2","V3","V4","V5","V6","V7","V8")
LEDGER_FIELDS = [
    "board_date","week_key","source_phase","evidence_class","cutoff_method","board_ts",
    "model","model_name","slip_no","decision","qualified_legs","valid_pairs",
    "selection_key","legs","book","price","price_source","pricing_status",
    "fair_joint_prob","model_edge_pct","stake","resolution","pnl","pnl_status","note",
]
UNIQUE_FIELDS = [
    "board_date","week_key","source_phase","evidence_class","ticket_key","selection_key",
    "models","book","price","price_source","pricing_status","legs","resolution","pnl",
    "pnl_status","model_count","conflict","note",
]
COVERAGE_FIELDS = [
    "board_date","event_count","candidate_snapshots","first_kick","source_status",
    "source_detail","historical_cutoff","forward_board_ts",
]

def _f(x, default=None):
    try: return float(x)
    except (TypeError, ValueError): return default

def _i(x, default=0):
    try: return int(float(x))
    except (TypeError, ValueError): return default

def _read_csv(path):
    if not Path(path).exists():
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))

def _week_key(date_s):
    d=dt.date.fromisoformat(date_s)
    return (d-dt.timedelta(days=d.weekday())).isoformat()

def _parse_legs(raw):
    if isinstance(raw, list):
        return raw
    if not raw:
        return []
    try:
        x=json.loads(raw)
        return x if isinstance(x,list) else []
    except Exception:
        return []

def _leg_key(leg):
    return "|".join(map(str,(
        leg.get("event_id",""),leg.get("market",""),leg.get("player",""),
        leg.get("point",""),leg.get("side",""),
    )))

def _selection_key(legs):
    return "||".join(sorted(_leg_key(x) for x in legs)) if legs else ""

def _price_status(price_source, price):
    if price in ("",None):
        return "none"
    s=str(price_source or "").lower()
    if any(x in s for x in ("actual_quote","sportsbook_quote","sgp_quote")):
        return "actual_quote"
    return "reconstructed_independent_product"

def _pnl_status(pricing_status, resolution):
    if not resolution or resolution=="open":
        return "unsettled"
    return "actual_quote_pnl" if pricing_status=="actual_quote" else "hypothetical_from_reconstructed_price"

def normalize_historical(rows):
    out=[]; dates=set()
    for r in rows:
        v=r.get("variant","")
        if not v.startswith("OFF_V"):
            continue
        if v=="OFF_V8_2":
            model="V8"; slip_no=2
        else:
            model=v.replace("OFF_",""); slip_no=1 if r.get("decision")=="play" else 0
        if model not in MODELS or model=="V7":
            continue
        ds=r.get("date","")
        if not ds:
            continue
        dates.add(ds)
        legs=_parse_legs(r.get("legs",""))
        selection=r.get("selection_key") or _selection_key(legs)
        price=r.get("price","")
        price_source="independent_product"
        pricing=_price_status(price_source,price)
        resolution=r.get("resolution","")
        out.append(dict(
            board_date=ds,week_key=_week_key(ds),source_phase="historical_reconstruction",
            evidence_class="retrospective_development",cutoff_method=r.get("benchmark_reason",""),
            board_ts=r.get("cutoff",""),model=model,model_name="",
            slip_no=slip_no,decision=r.get("decision","no_play"),
            qualified_legs=r.get("qualified_legs",""),valid_pairs=r.get("valid_pairs",""),
            selection_key=selection,legs=json.dumps(legs,separators=(",",":")),
            book=r.get("book",""),price=price,price_source=price_source,pricing_status=pricing,
            fair_joint_prob=r.get("fair_joint_prob",""),model_edge_pct=r.get("model_edge_pct",""),
            stake=STAKE_USD if r.get("decision")=="play" else 0,
            resolution=resolution,pnl=r.get("pnl",""),
            pnl_status=_pnl_status(pricing,resolution),
            note="retrospective causal reconstruction; not out-of-sample forward evidence",
        ))
    # V7 was and remains blocked. Preserve that state explicitly for historical dates.
    for ds in sorted(dates):
        out.append(dict(
            board_date=ds,week_key=_week_key(ds),source_phase="historical_reconstruction",
            evidence_class="retrospective_development",cutoff_method="blocked",
            board_ts="",model="V7",model_name="",slip_no=0,decision="no_play",
            qualified_legs=0,valid_pairs=0,selection_key="",legs="[]",book="",price="",
            price_source="",pricing_status="none",fair_joint_prob="",model_edge_pct="",
            stake=0,resolution="",pnl="",pnl_status="unsettled",
            note="blocked: actual cross-game parlay quote capture not available",
        ))
    return out

def normalize_forward(rows):
    out=[]
    for r in rows:
        if r.get("phase")!="forward":
            continue
        model=r.get("model","")
        if model not in MODELS:
            continue
        ds=r.get("board_date","")
        if not ds:
            continue
        legs=_parse_legs(r.get("legs",""))
        selection=_selection_key(legs)
        price=r.get("price","")
        source=r.get("price_source","")
        pricing=_price_status(source,price)
        resolution=r.get("resolution","")
        out.append(dict(
            board_date=ds,week_key=r.get("week_key") or _week_key(ds),
            source_phase="forward_frozen",evidence_class="forward_validation",
            cutoff_method="frozen_live_board",board_ts=r.get("board_ts") or r.get("ts",""),
            model=model,model_name=r.get("model_name",""),slip_no=r.get("slip_no",""),
            decision=r.get("decision",""),qualified_legs=r.get("qualified_legs",""),
            valid_pairs=r.get("valid_pairs",""),selection_key=selection,
            legs=json.dumps(legs,separators=(",",":")),book=r.get("book",""),
            price=price,price_source=source,pricing_status=pricing,
            fair_joint_prob=r.get("fair_joint_prob",""),model_edge_pct=r.get("model_edge_pct",""),
            stake=r.get("stake",""),resolution=resolution,pnl=r.get("pnl",""),
            pnl_status=_pnl_status(pricing,resolution),
            note=r.get("note",""),
        ))
    return out

def build_ledger(historical_rows, forward_rows):
    hist=normalize_historical(historical_rows)
    fwd=normalize_forward(forward_rows)
    forward_dates={r["board_date"] for r in fwd}
    # Never mix retrospective reconstruction with frozen forward evidence for the same date.
    hist=[r for r in hist if r["board_date"] not in forward_dates]
    rows=hist+fwd
    rows.sort(key=lambda r:(r["board_date"],MODELS.index(r["model"]),_i(r.get("slip_no"))))
    return rows

def _ticket_key(r):
    return "||".join(map(str,(
        r.get("board_date",""),r.get("selection_key",""),r.get("book",""),
        r.get("price",""),r.get("price_source",""),
    )))

def dedupe_tickets(rows):
    grouped=defaultdict(list)
    for r in rows:
        if r.get("decision")!="play" or not r.get("selection_key"):
            continue
        grouped[_ticket_key(r)].append(r)
    out=[]
    for key,rr in sorted(grouped.items(), key=lambda kv:(kv[1][0]["board_date"],kv[0])):
        models=sorted({r["model"] for r in rr},key=lambda x:MODELS.index(x))
        resolutions={r.get("resolution","") for r in rr}
        pnls={str(r.get("pnl","")) for r in rr}
        conflict=len(resolutions)>1 or len(pnls)>1
        r=rr[0]
        out.append(dict(
            board_date=r["board_date"],week_key=r["week_key"],source_phase=r["source_phase"],
            evidence_class=r["evidence_class"],ticket_key=key,selection_key=r["selection_key"],
            models=",".join(models),book=r["book"],price=r["price"],price_source=r["price_source"],
            pricing_status=r["pricing_status"],legs=r["legs"],resolution=r["resolution"],
            pnl=r["pnl"],pnl_status=r["pnl_status"],model_count=len(models),
            conflict=str(conflict),
            note=("CONFLICT across duplicate model rows" if conflict else "deduplicated identical execution ticket"),
        ))
    return out

def _metrics(rows):
    plays=[r for r in rows if r.get("decision")=="play"] if rows and "decision" in rows[0] else list(rows)
    settled=[r for r in plays if r.get("resolution") in ("won","lost","void","push")]
    wins=sum(r.get("resolution")=="won" for r in settled)
    losses=sum(r.get("resolution")=="lost" for r in settled)
    voids=sum(r.get("resolution")=="void" for r in settled)
    pushes=sum(r.get("resolution")=="push" for r in settled)
    pnl=sum(_f(r.get("pnl"),0) for r in settled)
    risk=sum(_f(r.get("stake"),STAKE_USD) for r in settled if r.get("resolution") in ("won","lost")) if rows and "stake" in rows[0] else STAKE_USD*(wins+losses)
    actual_quotes=sum(r.get("pricing_status")=="actual_quote" for r in plays)
    return dict(
        plays=len(plays),settled=len(settled),wins=wins,losses=losses,voids=voids,pushes=pushes,
        hit_rate=(100*wins/(wins+losses) if wins+losses else None),
        hypothetical_pnl=round(pnl,2),hypothetical_roi=(100*pnl/risk if risk else None),
        actual_quote_tickets=actual_quotes,
    )

def model_summary(rows):
    out={}
    for model in MODELS:
        rr=[r for r in rows if r.get("model")==model]
        m=_metrics(rr) if rr else _metrics([])
        m["historical_plays"]=sum(r.get("decision")=="play" and r.get("source_phase")=="historical_reconstruction" for r in rr)
        m["forward_plays"]=sum(r.get("decision")=="play" and r.get("source_phase")=="forward_frozen" for r in rr)
        out[model]=m
    return out

def coverage_rows(ledger):
    events=read_rows("events")
    candidates=read_rows("candidates")
    by_date=defaultdict(list)
    for e in events:
        try: local=parse_iso(e.get("commence_time","")).astimezone(NY)
        except Exception: continue
        if local.weekday()==6:
            by_date[local.date().isoformat()].append(e)
    hist_by={r["board_date"]:r for r in ledger if r["source_phase"]=="historical_reconstruction"}
    fwd_by={r["board_date"]:r for r in ledger if r["source_phase"]=="forward_frozen"}
    now=utcnow().astimezone(NY).date()
    out=[]
    for ds,ers in sorted(by_date.items()):
        if len(ers)<2:
            continue
        ids={e["event_id"] for e in ers}
        times=sorted({r.get("ts","") for r in candidates if r.get("event_id") in ids and r.get("ts")})
        first_kick=min(parse_iso(e["commence_time"]) for e in ers)
        if ds in fwd_by:
            status="forward_frozen"; detail="canonical frozen forward V1–V8 decisions"
        elif ds in hist_by:
            status="historical_reconstruction"; detail="retrospective causal reconstruction from archived pregame board"
        elif dt.date.fromisoformat(ds)>now:
            status="future"; detail="Sunday has not occurred yet"
        else:
            status="unavailable"; detail="no historical bridge row and no frozen forward decision"
        out.append(dict(
            board_date=ds,event_count=len(ers),candidate_snapshots=len(times),first_kick=iso(first_kick),
            source_status=status,source_detail=detail,
            historical_cutoff=hist_by.get(ds,{}).get("board_ts",""),
            forward_board_ts=fwd_by.get(ds,{}).get("board_ts",""),
        ))
    return out

def build_payload(historical_rows=None, forward_rows=None):
    historical_rows=_read_csv(HIST) if historical_rows is None else historical_rows
    forward_rows=read_rows("parlay_decisions") if forward_rows is None else forward_rows
    ledger=build_ledger(historical_rows,forward_rows)
    unique=dedupe_tickets(ledger)
    return dict(
        generated_at=iso(),lab_version=LAB_VERSION,
        methodology="historical reconstruction before forward start + frozen forward decisions thereafter; forward dates supersede retrospective rows",
        pricing_warning="Cross-game ticket P&L is hypothetical whenever pricing_status=reconstructed_independent_product.",
        sgp_scope="SGP remains a separate additive research family and is not included in this ledger.",
        model_summary=model_summary(ledger),
        phase_summary={
            "historical_reconstruction": _metrics([x for x in unique if x.get("source_phase")=="historical_reconstruction"]),
            "forward_frozen": _metrics([x for x in unique if x.get("source_phase")=="forward_frozen"]),
        },
        unique_summary=_metrics(unique),
        ledger=ledger,unique_tickets=unique,
    )

def _write_csv(path,fields,rows):
    with open(path,"w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction="ignore");w.writeheader();w.writerows(rows)

def _money(x):
    return "—" if x in (None,"") else f"${float(x):+.2f}"

def _pct(x):
    return "—" if x is None else f"{x:.1f}%"

def _leg_text(raw):
    legs=_parse_legs(raw)
    if not legs:return "NO PLAY"
    return " + ".join(f'{x.get("player","")} {str(x.get("side",""))[:1]}{x.get("point","")} {x.get("market","").replace("player_","").replace("_"," ")}' for x in legs)

def write():
    payload=build_payload()
    coverage=coverage_rows(payload["ledger"])
    _write_csv(OUT/"ledger.csv",LEDGER_FIELDS,payload["ledger"])
    _write_csv(OUT/"unique_tickets.csv",UNIQUE_FIELDS,payload["unique_tickets"])
    _write_csv(OUT/"coverage.csv",COVERAGE_FIELDS,coverage)
    compact={k:v for k,v in payload.items() if k not in ("ledger","unique_tickets")}
    compact["coverage"]=coverage
    (OUT/"summary.json").write_text(json.dumps(compact,indent=2,sort_keys=True),encoding="utf-8")

    lines=[
        "# V1–V8 full-history bridge","",
        f"Generated: **{payload['generated_at']}** · LAB_VERSION **{payload['lab_version']}**","",
        "**Purpose:** restore one continuous V1–V8 record. The historical reconstruction ends where frozen forward decisions begin. SGP remains additive and separate.","",
        "## Pricing warning","",
        payload["pricing_warning"],"","## Coverage","",
        "| Sunday | Status | Events | Candidate snapshots | Board/cutoff |",
        "|---|---|---:|---:|---|",
    ]
    for c in coverage:
        board=c["forward_board_ts"] or c["historical_cutoff"] or "—"
        lines.append(f'| {c["board_date"]} | {c["source_status"]} | {c["event_count"]} | {c["candidate_snapshots"]} | {board} |')
    lines += ["","## Model record","",
              "| Model | Hist plays | Forward plays | W-L | Void | Hit | Hypothetical P&L | ROI | Actual-quote tickets |",
              "|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for m in MODELS:
        x=payload["model_summary"][m]
        lines.append(f'| {m} | {x["historical_plays"]} | {x["forward_plays"]} | {x["wins"]}-{x["losses"]} | {x["voids"]} | {_pct(x["hit_rate"])} | {_money(x["hypothetical_pnl"])} | {_pct(x["hypothetical_roi"])} | {x["actual_quote_tickets"]} |')
    u=payload["unique_summary"]
    h=payload["phase_summary"]["historical_reconstruction"]
    fwd=payload["phase_summary"]["forward_frozen"]
    lines += ["","## Deduplicated execution record","",
              f'Unique execution tickets: **{u["plays"]}** · settled **{u["settled"]}** · record **{u["wins"]}-{u["losses"]}** · voids **{u["voids"]}** · hypothetical P&L **{_money(u["hypothetical_pnl"])}**.',"",
              "Identical tickets selected by multiple V-models count once here.","",
              "| Evidence phase | Unique tickets | W-L | Hit | Hypothetical P&L | ROI |",
              "|---|---:|---:|---:|---:|---:|",
              f'| Historical reconstruction | {h["plays"]} | {h["wins"]}-{h["losses"]} | {_pct(h["hit_rate"])} | {_money(h["hypothetical_pnl"])} | {_pct(h["hypothetical_roi"])} |',
              f'| Frozen forward | {fwd["plays"]} | {fwd["wins"]}-{fwd["losses"]} | {_pct(fwd["hit_rate"])} | {_money(fwd["hypothetical_pnl"])} | {_pct(fwd["hypothetical_roi"])} |',"",
              "| Sunday | Models | Ticket | Result | Price | Pricing | P&L |",
              "|---|---|---|---|---:|---|---:|"]
    for r in payload["unique_tickets"]:
        lines.append(f'| {r["board_date"]} | {r["models"]} | {_leg_text(r["legs"])} | {r["resolution"] or "open"} | {r["price"] or "—"} | {r["pricing_status"]} | {_money(r["pnl"])} |')
    lines += ["","## Evidence boundaries","",
              "- Historical rows are retrospective development evidence, not forward validation.",
              "- Frozen forward rows are never replaced by retrospective reconstruction on the same date.",
              "- V7 remains blocked until actual cross-game parlay quote capture exists.",
              "- A winning/losing ticket result is real when settled, but P&L is hypothetical if its ticket price was reconstructed.",
              "- SGP results live in their own family and do not replace or pause V1–V8.",
              ""]
    (OUT/"REPORT.md").write_text("\n".join(lines),encoding="utf-8")
    print(json.dumps(dict(rows=len(payload["ledger"]),unique=len(payload["unique_tickets"]),coverage=len(coverage),summary=payload["unique_summary"]),sort_keys=True))
    return payload

if __name__=="__main__":
    write()
