"""parlay_lab.py — causal, paper-only cross-game parlay research layer.

The existing H1–H4 / slips experiment remains untouched. This module runs a separate
model tournament from the current board, freezes each game-day decision once, settles
those frozen decisions later, renders docs/index.html, and produces compact Telegram text.

Forward model family (all paper-only):
  V1 Strict        Pinnacle fair + Bovada AND DraftKings confirm, >=5 books, receptions >2.5
  V2 Depth         same, receptions >1.5
  V3 Bovada        Pinnacle fair + Bovada confirms, >=5 books, receptions >1.5
  V4 DraftKings    Pinnacle fair + DraftKings confirms, >=5 books, receptions >1.5
  V5 Any 2         Pinnacle fair + any 2 confirming books, >=5 books, receptions >1.5
  V6 Any 3         Pinnacle fair + any 3 confirming books, >=5 books, receptions >1.5
  V7 Value Floor   BLOCKED until an actual cross-game parlay quote is captured
  V8 Strong Slate  V3 pool, up to two slips, second slip shares no games with the first

Board freeze: first scheduled/manual run at or after 08:00 America/New_York on a date
with NFL games that have not kicked off. The actual freeze timestamp is persisted; later
prices cannot rewrite that date. The GitHub Action runs every 6h, so a failed/missed tick
may freeze later than 08:00 — the exact timestamp is always displayed.
"""
from __future__ import annotations

import csv
import datetime as dt
import html
import itertools
import json
import math
import os
import statistics
from collections import defaultdict
from zoneinfo import ZoneInfo

from common import *
import slips as _slips
import sgp_shadow as _sgp_shadow

NY = ZoneInfo("America/New_York")
BOARD_HOUR_ET = 8
MIN_MODEL_BOOKS = 5
RESEARCH_MODELS = ("V1", "V2", "V3", "V4", "V5", "V6", "V7", "V8")
CONFIRM_BOOKS = {"bovada", "draftkings", "fanduel", "hardrock", "underdog", "kalshi", "fanatics"}
EXECUTION_BOOKS = {"bovada", "draftkings", "fanduel", "hardrock", "underdog", "kalshi", "fanatics"}

MODEL_META = {
    "V1": dict(name="Strict", status="FROZEN", detail="BOV + DK · REC >2.5", confirm="bovada+draftkings", rec_min=2.5, max_slips=1),
    "V2": dict(name="Depth", status="LEAD", detail="BOV + DK · REC >1.5", confirm="bovada+draftkings", rec_min=1.5, max_slips=1),
    "V3": dict(name="Bovada", status="CHALLENGER", detail="BOV confirm · REC >1.5", confirm="bovada", rec_min=1.5, max_slips=1),
    "V4": dict(name="DraftKings", status="TRACKING", detail="DK confirm · REC >1.5", confirm="draftkings", rec_min=1.5, max_slips=1),
    "V5": dict(name="Any 2", status="TRACKING", detail="Any 2 confirms · REC >1.5", confirm="any2", rec_min=1.5, max_slips=1),
    "V6": dict(name="Any 3", status="TRACKING", detail="Any 3 confirms · REC >1.5", confirm="any3", rec_min=1.5, max_slips=1),
    "V7": dict(name="Value Floor", status="BLOCKED", detail="Needs actual parlay quote", confirm="blocked", rec_min=1.5, max_slips=0),
    "V8": dict(name="Strong Slate", status="CHALLENGER", detail="V3 pool · up to 2 independent", confirm="bovada", rec_min=1.5, max_slips=2),
}

DECISION_FIELDS = [
    "ts", "phase", "board_date", "board_ts", "week_key", "model", "model_name", "slip_no", "decision",
    "qualified_legs", "valid_pairs", "event_ids", "legs", "confirm_books", "book", "price", "price_source",
    "fair_joint_prob", "break_even_prob", "model_edge_pct", "stake", "resolution", "pnl", "settled_ts", "note",
]

# Development replay is deliberately stored separately from forward results. These are the
# causal historical replays discussed during model development; they are NOT out-of-sample.
DEVELOPMENT_REPLAY = [
    # V1
    dict(model="V1", board_date="2026-09-20", slip_no=1, decision="play", book="draftkings", price=293,
         fair_joint_prob=.2814, model_edge_pct=10.56, resolution="won", pnl=14.64,
         legs=["Justin Jefferson U6.5 receptions", "Tyler Shough U0.5 interceptions"]),
    dict(model="V1", board_date="2026-09-27", slip_no=0, decision="no_play", resolution="", pnl=0.0, legs=[]),
    # V2
    dict(model="V2", board_date="2026-09-20", slip_no=1, decision="play", book="draftkings", price=293,
         fair_joint_prob=.2814, model_edge_pct=10.56, resolution="won", pnl=14.64,
         legs=["Justin Jefferson U6.5 receptions", "Tyler Shough U0.5 interceptions"]),
    dict(model="V2", board_date="2026-09-27", slip_no=1, decision="play", book="draftkings", price=373,
         fair_joint_prob=.2284, model_edge_pct=8.04, resolution="won", pnl=18.65,
         legs=["Javonte Williams U2.5 receptions", "Ladd McConkey U4.5 receptions"]),
    # V3 selected the same top slip but expanded the opportunity pool (5->9 pairs Sep20; 1->2 Sep27 vs V2).
    dict(model="V3", board_date="2026-09-20", slip_no=1, decision="play", book="draftkings", price=293,
         fair_joint_prob=.2814, model_edge_pct=10.56, resolution="won", pnl=14.64,
         legs=["Justin Jefferson U6.5 receptions", "Tyler Shough U0.5 interceptions"]),
    dict(model="V3", board_date="2026-09-27", slip_no=1, decision="play", book="draftkings", price=373,
         fair_joint_prob=.2284, model_edge_pct=8.04, resolution="won", pnl=18.65,
         legs=["Javonte Williams U2.5 receptions", "Ladd McConkey U4.5 receptions"]),
    # V8 diagnostic strong-slate scale: up to two non-overlapping pairs from V3 pool.
    dict(model="V8", board_date="2026-09-20", slip_no=1, decision="play", book="draftkings", price=293,
         fair_joint_prob=.2814, model_edge_pct=10.56, resolution="won", pnl=14.64,
         legs=["Justin Jefferson U6.5 receptions", "Tyler Shough U0.5 interceptions"]),
    dict(model="V8", board_date="2026-09-20", slip_no=2, decision="play", book="bovada", price=383,
         fair_joint_prob=.2207, model_edge_pct=6.61, resolution="won", pnl=19.15,
         legs=["Cooper Rush O0.5 rushing yards", "Malik Washington O3.5 receptions"]),
    dict(model="V8", board_date="2026-09-27", slip_no=1, decision="play", book="draftkings", price=373,
         fair_joint_prob=.2284, model_edge_pct=8.04, resolution="won", pnl=18.65,
         legs=["Javonte Williams U2.5 receptions", "Ladd McConkey U4.5 receptions"]),
]

DEV_OPPORTUNITIES = {
    "V1": {"2026-09-20": dict(qualified_legs=4, valid_pairs=5), "2026-09-27": dict(qualified_legs=1, valid_pairs=0)},
    "V2": {"2026-09-20": dict(qualified_legs=4, valid_pairs=5), "2026-09-27": dict(qualified_legs=2, valid_pairs=1)},
    "V3": {"2026-09-20": dict(qualified_legs=5, valid_pairs=9), "2026-09-27": dict(qualified_legs=3, valid_pairs=2)},
    "V8": {"2026-09-20": dict(qualified_legs=5, valid_pairs=9), "2026-09-27": dict(qualified_legs=3, valid_pairs=2)},
}


def _f(x, default=None):
    try: return float(x)
    except (TypeError, ValueError): return default


def _i(x, default=0):
    try: return int(float(x))
    except (TypeError, ValueError): return default


def _line_key(r):
    return (r["event_id"], r["market"], r["player"], str(r["point"]), r["side"], r["book"])


def _leg_key(r):
    return (r["event_id"], r["market"], r["player"], str(r["point"]), r["side"])


def _passes_gate(r):
    fp, ev, nb = _f(r.get("fair_prob")), _f(r.get("ev_pct")), _i(r.get("n_books"))
    if fp is None or ev is None: return False
    if not (GATE["fair_min"] <= fp <= GATE["fair_max"]): return False
    if nb < GATE["min_books"]: return False
    if r.get("fair_source") not in GATE["trusted_anchors"] and nb < GATE["kalshi_min_books"]: return False
    return ev >= GATE["min_ev_pct"]


def _fmt_leg(l):
    m = l["market"].replace("player_", "").replace("_", " ")
    return f"{l['player']} {l['side'][0]}{l['point']} {m}"


def _week_key(date_s):
    d = dt.date.fromisoformat(date_s)
    monday = d - dt.timedelta(days=d.weekday())
    return monday.isoformat()


def _week_label(date_s):
    d = dt.date.fromisoformat(date_s)
    monday = d - dt.timedelta(days=d.weekday())
    sunday = monday + dt.timedelta(days=6)
    if monday.month == sunday.month:
        return f"Week of {monday.strftime('%b')} {monday.day}–{sunday.day}"
    return f"Week of {monday.strftime('%b')} {monday.day}–{sunday.strftime('%b')} {sunday.day}"


def _event_map():
    return {r["event_id"]: r for r in read_rows("events")}


def _today_event_ids(now=None):
    now = now or utcnow()
    local = now.astimezone(NY)
    date_s = local.date().isoformat()
    out = []
    for e in read_rows("events"):
        try: kick = parse_iso(e["commence_time"])
        except Exception: continue
        if kick <= now: continue
        if kick.astimezone(NY).date().isoformat() == date_s:
            out.append(e["event_id"])
    return date_s, out


def should_freeze(now=None):
    now = now or utcnow(); local = now.astimezone(NY)
    date_s, eids = _today_event_ids(now)
    if local.hour < BOARD_HOUR_ET or not eids: return False, date_s, eids
    existing = [r for r in read_rows("parlay_decisions") if r.get("phase") == "forward" and r.get("board_date") == date_s]
    return not bool(existing), date_s, eids


def _latest_lines(event_ids, cutoff=None):
    """Exact current board when available; change-only history is fallback for offline/legacy runs."""
    event_ids = set(event_ids)
    current = read_rows("current_lines")
    if current:
        return [r for r in current if r.get("event_id") in event_ids]
    cutoff = cutoff or utcnow(); last = {}
    for r in read_rows("lines"):
        if r["event_id"] not in event_ids: continue
        try: ts = parse_iso(r["ts"])
        except Exception: continue
        if ts > cutoff: continue
        last[_line_key(r)] = r
    return list(last.values())


def _current_leg_universe(event_ids, cutoff=None):
    """Return (eligible source rows grouped by underlying leg, all current quotes grouped by leg/book)."""
    rows = _latest_lines(event_ids, cutoff)
    all_by_leg = defaultdict(dict)
    gated_by_leg = defaultdict(dict)
    for r in rows:
        all_by_leg[_leg_key(r)][r["book"]] = r
        if _passes_gate(r) and r.get("fair_source") == "pinnacle":
            gated_by_leg[_leg_key(r)][r["book"]] = r
    return gated_by_leg, all_by_leg


def _depth_ok(key, threshold):
    _eid, market, _player, point, _side = key
    if market != "player_receptions": return True
    p = _f(point)
    return p is not None and p > threshold


def _confirm_ok(books, rule):
    books = set(books)
    if rule == "bovada+draftkings": return {"bovada", "draftkings"}.issubset(books)
    if rule == "bovada": return "bovada" in books
    if rule == "draftkings": return "draftkings" in books
    if rule == "any2": return len(books & CONFIRM_BOOKS) >= 2
    if rule == "any3": return len(books & CONFIRM_BOOKS) >= 3
    return False


def _eligible_legs(model, gated_by_leg):
    meta = MODEL_META[model]
    if meta["confirm"] == "blocked": return []
    out = []
    for key, by_book in gated_by_leg.items():
        books = set(by_book)
        if not _confirm_ok(books, meta["confirm"]): continue
        rows = list(by_book.values())
        if max((_i(r.get("n_books")) for r in rows), default=0) < MIN_MODEL_BOOKS: continue
        if not _depth_ok(key, meta["rec_min"]): continue
        # Fair probability is market-level; average the confirming rows to remove tiny row noise.
        fps = [_f(r.get("fair_prob")) for r in rows if _f(r.get("fair_prob")) is not None]
        if not fps: continue
        rep = max(rows, key=lambda r: (r["book"] == "bovada", r["book"] == "draftkings", r["ts"]))
        out.append(dict(
            event_id=key[0], market=key[1], player=key[2], point=key[3], side=key[4],
            fair_prob=sum(fps)/len(fps), n_books=max(_i(r.get("n_books")) for r in rows),
            confirm_books=sorted(books & CONFIRM_BOOKS), home=rep.get("home", ""), away=rep.get("away", ""),
        ))
    return out


def _execution_for_pair(a, b, all_by_leg):
    qa, qb = all_by_leg.get((a["event_id"],a["market"],a["player"],str(a["point"]),a["side"]),{}), \
             all_by_leg.get((b["event_id"],b["market"],b["player"],str(b["point"]),b["side"]),{})
    best = None
    for book in sorted((set(qa) & set(qb) & EXECUTION_BOOKS)):
        pa, pb = _i(qa[book].get("price"), None), _i(qb[book].get("price"), None)
        if pa is None or pb is None: continue
        dec = am_to_dec(pa) * am_to_dec(pb)
        if best is None or dec > best["decimal"]:
            best = dict(book=book, price=dec_to_am(dec), decimal=dec, price_a=pa, price_b=pb)
    return best


def _pairs(legs, all_by_leg):
    out = []
    for a, b in itertools.combinations(legs, 2):
        if a["event_id"] == b["event_id"]: continue
        ex = _execution_for_pair(a, b, all_by_leg)
        if not ex: continue
        jp = a["fair_prob"] * b["fair_prob"]
        edge = (jp * ex["decimal"] - 1) * 100
        out.append(dict(a=a, b=b, joint=jp, edge=edge, break_even=1/ex["decimal"], **ex))
    return sorted(out, key=lambda p: (-p["joint"], -p["edge"]))


def evaluate_model(model, gated_by_leg, all_by_leg):
    meta = MODEL_META[model]
    if model == "V7":
        return dict(model=model, qualified_legs=0, valid_pairs=0, selections=[], note="blocked: actual cross-game parlay quote capture not implemented")
    legs = _eligible_legs(model if model != "V8" else "V3", gated_by_leg)
    pairs = [p for p in _pairs(legs, all_by_leg) if p["edge"] > 0]
    selections = []
    if pairs:
        selections.append(pairs[0])
    if model == "V8" and selections:
        used_events = {selections[0]["a"]["event_id"], selections[0]["b"]["event_id"]}
        second = next((p for p in pairs if p["a"]["event_id"] not in used_events and p["b"]["event_id"] not in used_events), None)
        if second: selections.append(second)
    return dict(model=model, qualified_legs=len(legs), valid_pairs=len(pairs), selections=selections, note="")


def _decision_rows(result, date_s, board_ts):
    model = result["model"]; meta = MODEL_META[model]; rows = []
    base = dict(ts=iso(), phase="forward", board_date=date_s, board_ts=board_ts, week_key=_week_key(date_s),
                model=model, model_name=meta["name"], qualified_legs=result["qualified_legs"], valid_pairs=result["valid_pairs"])
    if not result["selections"]:
        rows.append(dict(base, slip_no=0, decision="no_play", event_ids="", legs="[]", confirm_books="", book="", price="",
                         price_source="", fair_joint_prob="", break_even_prob="", model_edge_pct="", stake=0,
                         resolution="", pnl="", settled_ts="", note=result["note"] or "no qualifying cross-game pair"))
        return rows
    for i, p in enumerate(result["selections"], 1):
        legs = []
        for l, price in ((p["a"], p["price_a"]), (p["b"], p["price_b"])):
            legs.append(dict(event_id=l["event_id"], market=l["market"], player=l["player"], point=l["point"], side=l["side"],
                             fair_prob=round(l["fair_prob"],6), n_books=l["n_books"], confirm_books=l["confirm_books"],
                             price=price, book=p["book"], home=l.get("home",""), away=l.get("away","")))
        rows.append(dict(base, slip_no=i, decision="play", event_ids=",".join(sorted([p["a"]["event_id"],p["b"]["event_id"]])),
                         legs=json.dumps(legs, separators=(",",":")), confirm_books=";".join(sorted(set(p["a"]["confirm_books"]) | set(p["b"]["confirm_books"]))),
                         book=p["book"], price=p["price"], price_source="independent_product", fair_joint_prob=round(p["joint"],6),
                         break_even_prob=round(p["break_even"],6), model_edge_pct=round(p["edge"],3), stake=STAKE_USD,
                         resolution="open", pnl="", settled_ts="", note="paper research; verify live platform price before any real-world use"))
    return rows


def freeze_today(now=None):
    """Freeze the current game-day board once. Returns number of rows appended.

    A stale current_lines.csv is never allowed to create a forward decision. If the live snapshot
    failed, we wait for the next successful tick rather than silently using old quotes.
    """
    now = now or utcnow()
    ok, date_s, eids = should_freeze(now)
    if not ok: return 0
    current = [r for r in read_rows("current_lines") if r.get("event_id") in set(eids)]
    if not current: return 0
    newest = max((parse_iso(r["ts"]) for r in current if r.get("ts")), default=None)
    if newest is None or (now - newest).total_seconds() > 2 * 3600:
        return 0
    gated, all_lines = _current_leg_universe(eids, now)
    board_ts = iso(now)
    rows = []
    for model in RESEARCH_MODELS:
        rows.extend(_decision_rows(evaluate_model(model, gated, all_lines), date_s, board_ts))
    n = append_rows("parlay_decisions", rows, DECISION_FIELDS)
    state_set("parlay_board_last", dict(date=date_s, ts=board_ts, events=eids, rows=n))
    return n


def settle_forward(now=None):
    rows = read_rows("parlay_decisions")
    if not rows: return 0
    now = now or utcnow(); grader = _slips.Grader(read_rows("results")); events = _event_map(); n=0
    for r in rows:
        if r.get("phase") != "forward" or r.get("decision") != "play" or r.get("resolution") != "open": continue
        try: legs = json.loads(r["legs"])
        except Exception: continue
        res=[]
        for l in legs:
            gr = grader.leg(l, l["event_id"], r["book"])
            if gr is None:
                ev=events.get(l["event_id"])
                if ev and (now-parse_iso(ev["commence_time"])).total_seconds() > _slips.UNGRADEABLE_AFTER_HOURS*3600:
                    gr="void"
            res.append(gr)
        if "lost" in res:
            resolution="lost"; pnl=-float(r["stake"])
        elif any(x is None for x in res):
            continue
        else:
            live=[l for l,x in zip(legs,res) if x=="won"]
            stake=float(r["stake"])
            if not live:
                resolution="void" if all(x=="void" for x in res) else "push"; pnl=0.0
            elif len(live)==len(legs):
                resolution="won"; pnl=(am_to_dec(int(float(r["price"])))-1)*stake
            else:
                dec=1.0
                for l in live: dec*=am_to_dec(int(float(l["price"])))
                resolution="won"; pnl=(dec-1)*stake
                r["note"]=(r.get("note","")+f" reduced={len(live)}/{len(legs)} legs").strip()
        r["resolution"]=resolution; r["pnl"]=round(pnl,2); r["settled_ts"]=iso(now); n+=1
    if n:
        p=csv_path("parlay_decisions")
        with open(p,"w",newline="") as f:
            w=csv.DictWriter(f,fieldnames=DECISION_FIELDS,extrasaction="ignore"); w.writeheader(); w.writerows(rows)
    return n


def _record(rows):
    plays=[r for r in rows if r.get("decision")=="play"]
    settled=[r for r in plays if r.get("resolution") in ("won","lost","push","void")]
    wins=sum(r.get("resolution")=="won" for r in settled); losses=sum(r.get("resolution")=="lost" for r in settled)
    stake=sum(_f(r.get("stake"),0) for r in plays)
    pnl=sum(_f(r.get("pnl"),0) for r in settled)
    gross=stake+pnl
    roi=(100*pnl/stake) if stake else None
    hit=(100*wins/(wins+losses)) if (wins+losses) else None
    fps=[_f(r.get("fair_joint_prob")) for r in plays if _f(r.get("fair_joint_prob")) is not None]
    edges=[_f(r.get("model_edge_pct")) for r in plays if _f(r.get("model_edge_pct")) is not None]
    dates=sorted({r.get("board_date") for r in rows if r.get("board_date")})
    play_dates={r.get("board_date") for r in plays}
    return dict(slips=len(plays), settled=len(settled), wins=wins, losses=losses, stake=stake, gross=gross, pnl=pnl, roi=roi, hit=hit,
                avg_joint=(100*sum(fps)/len(fps)) if fps else None, avg_edge=(sum(edges)/len(edges)) if edges else None,
                dates=len(dates), play_days=len(play_dates), no_play_days=max(0,len(dates)-len(play_dates)))


def _dev_rows(model):
    rows=[]
    for r in DEVELOPMENT_REPLAY:
        if r["model"]!=model: continue
        q=DEV_OPPORTUNITIES.get(model,{}).get(r["board_date"],{})
        rows.append(dict(r, phase="development", stake=STAKE_USD if r["decision"]=="play" else 0,
                         qualified_legs=q.get("qualified_legs",0), valid_pairs=q.get("valid_pairs",0),
                         board_ts="development replay", week_key=_week_key(r["board_date"]), price_source="independent_product",
                         break_even_prob=(1/am_to_dec(r["price"])) if r.get("price") else "", model_name=MODEL_META[model]["name"],
                         event_ids="", confirm_books="", settled_ts="", note="retrospective development replay"))
    return rows


def model_data():
    forward=read_rows("parlay_decisions")
    out={}
    for m in RESEARCH_MODELS:
        f=[r for r in forward if r.get("model")==m]
        d=_dev_rows(m)
        out[m]=dict(meta=MODEL_META[m], development=d, forward=f, dev_record=_record(d), forward_record=_record(f))
    return out


def _unique_today_plays(date_s=None):
    rows=read_rows("parlay_decisions")
    if date_s is None:
        dates=sorted({r.get("board_date") for r in rows if r.get("phase")=="forward"})
        if not dates: return []
        date_s=dates[-1]
    plays=[r for r in rows if r.get("phase")=="forward" and r.get("board_date")==date_s and r.get("decision")=="play"]
    grouped={}
    for r in plays:
        try: legs=json.loads(r["legs"])
        except Exception: continue
        key=tuple(sorted((l["event_id"],l["market"],l["player"],str(l["point"]),l["side"]) for l in legs))
        g=grouped.setdefault(key,dict(row=r,models=[]))
        g["models"].append(r["model"])
        # Prefer the higher reconstructed price if duplicated across models/books.
        if _i(r.get("price"),-999999) > _i(g["row"].get("price"),-999999): g["row"]=r
    out=list(grouped.values())
    out.sort(key=lambda g:-_f(g["row"].get("fair_joint_prob"),0))
    return out


def daily_telegram(date_s=None):
    groups=_unique_today_plays(date_s)
    rows=read_rows("parlay_decisions")
    if date_s is None:
        dates=sorted({r.get("board_date") for r in rows if r.get("phase")=="forward"})
        if not dates: return None
        date_s=dates[-1]
    if not any(r.get("board_date")==date_s for r in rows): return None
    label=dt.date.fromisoformat(date_s).strftime("%a %b %-d")
    if not groups:
        statuses=[]
        for m in ("V1","V2","V3","V4","V5","V6","V8"):
            rr=[r for r in rows if r.get("board_date")==date_s and r.get("model")==m]
            if rr: statuses.append(f"{m}: no play")
        return "\n".join([f"⚪ PARLAY LAB — {label}", "PAPER RESEARCH · NO PLAY", "", " · ".join(statuses), "Quality > quantity."])
    L=[f"🟢 PARLAY LAB — {label}", f"PAPER RESEARCH · {len(groups)} unique lineup{'s' if len(groups)!=1 else ''}", ""]
    for i,g in enumerate(groups,1):
        r=g["row"]; legs=json.loads(r["legs"]); models=" · ".join(sorted(g["models"], key=lambda x:int(x[1:])))
        L.append(f"{i}. {r['book'].upper()} recon {int(float(r['price'])):+d} · {models}")
        L.append("   " + " + ".join(_fmt_leg(l) for l in legs))
        L.append(f"   Fair {100*float(r['fair_joint_prob']):.1f}% · Edge {float(r['model_edge_pct']):+.1f}%")
    L += ["", "Recon price only — verify the live platform ticket before any real-world action."]
    return "\n".join(L)


def weekly_telegram(now=None):
    now=now or utcnow(); local=now.astimezone(NY); monday=local.date()-dt.timedelta(days=local.weekday()); key=monday.isoformat()
    rows=[r for r in read_rows("parlay_decisions") if r.get("phase")=="forward" and r.get("week_key")==key]
    if not rows: return "📊 PARLAY LAB — weekly\nNo forward boards frozen this week yet."
    L=[f"📊 PARLAY LAB — {_week_label(local.date().isoformat())}", "PAPER FORWARD TOURNAMENT"]
    for m in ("V1","V2","V3","V4","V5","V6","V8"):
        rr=[r for r in rows if r.get("model")==m]; rec=_record(rr)
        if not rr: continue
        if rec["slips"]:
            wl=f"{rec['wins']}–{rec['losses']}" if rec["settled"] else "open"
            L.append(f"{m} {MODEL_META[m]['name']}: {wl} · {rec['slips']} slips · ${rec['pnl']:+.2f}")
        else: L.append(f"{m} {MODEL_META[m]['name']}: NO PLAY")
    L.append("Dashboard → https://zilverest.github.io/prop-lab/")
    return "\n".join(L)


def _h(x): return html.escape(str(x))

def _money(x):
    x=_f(x,0); return f"{'+' if x>0 else ''}${x:.2f}"

def _pct(x): return "—" if x is None else f"{x:+.1f}%" if x<0 else f"{x:.1f}%"


def _history_html(model, dev, forward):
    def phase_block(title, rows, css):
        if not rows: return f'<div class="emptyhist">{title}: no data yet.</div>'
        by_week=defaultdict(list)
        for r in rows: by_week[r.get("week_key") or _week_key(r["board_date"])].append(r)
        blocks=[]
        for wk in sorted(by_week):
            wr=by_week[wk]; wrec=_record(wr)
            by_date=defaultdict(list)
            for r in wr: by_date[r["board_date"]].append(r)
            dates=[]
            for date_s in sorted(by_date):
                dr=by_date[date_s]; plays=[r for r in dr if r.get("decision")=="play"]
                drec=_record(dr); daylab=dt.date.fromisoformat(date_s).strftime("%b %-d, %Y")
                slips=[]
                if not plays:
                    q=max((_i(r.get("qualified_legs")) for r in dr), default=0); p=max((_i(r.get("valid_pairs")) for r in dr), default=0)
                    slips.append(f'<div class="nop"><b>NO PLAY</b><span>{q} qualifying legs · {p} valid pairs</span></div>')
                else:
                    for r in plays:
                        try: legs=json.loads(r["legs"]) if isinstance(r.get("legs"),str) else r.get("legs",[])
                        except Exception: legs=[]
                        if legs and isinstance(legs[0],dict): legtxt=" + ".join(_fmt_leg(l) for l in legs)
                        else: legtxt=" + ".join(legs)
                        res=(r.get("resolution") or "open").upper(); cls="win" if res=="WON" else "loss" if res=="LOST" else "open"
                        price=r.get("price"); pr=f"{int(float(price)):+d}" if price not in ("",None) else "—"
                        fp=_f(r.get("fair_joint_prob")); fp_txt=f"{100*fp:.1f}%" if fp is not None else "—"
                        edge=_f(r.get("model_edge_pct")); edge_txt=f"{edge:+.1f}%" if edge is not None else "—"
                        slips.append(f'''<details class="slip"><summary><span>Slip {r.get('slip_no','')}</span><b class="{cls}">{res}</b><em>{_money(r.get('pnl')) if r.get('pnl') not in ('',None) else ''}</em></summary>
                          <div class="slipbody"><strong>{_h(legtxt)}</strong><div>{_h(str(r.get('book','')).upper())} · {pr} · Fair {fp_txt} · Edge {edge_txt}</div>
                          <button class="platform-btn" type="button" disabled title="Live platform handoff is not implemented yet">Platforms · placeholder</button></div></details>''')
                dates.append(f'''<details class="day"><summary><span>{daylab}</span><b>{len(plays)} slip{'s' if len(plays)!=1 else ''}</b><em>{_money(drec['pnl'])}</em></summary><div class="daybody">{''.join(slips)}</div></details>''')
            blocks.append(f'''<details class="week"><summary><span>{_week_label(wr[0]['board_date'])}</span><b>{wrec['wins']}–{wrec['losses']} · {wrec['slips']} slips</b><em>{_money(wrec['pnl'])}</em></summary><div class="weekbody">{''.join(dates)}</div></details>''')
        return f'<div class="phase {css}"><div class="phase-title">{title}</div>{"".join(blocks)}</div>'
    return phase_block("Development replay · in-sample", dev, "dev") + phase_block("Forward validation · frozen", forward, "fwd")


def _model_payload():
    md=model_data(); payload={}
    for m,d in md.items():
        payload[m]=dict(meta=d["meta"], dev=d["dev_record"], fwd=d["forward_record"])
    return payload


def render_dashboard():
    md=model_data(); payload=_model_payload(); latest=state_get("parlay_board_last",{}) or {}
    cards=[]; histories=[]
    for m in RESEARCH_MODELS:
        d=md[m]; dev=d["dev_record"]; fwd=d["forward_record"]; meta=d["meta"]
        primary=fwd if (fwd["dates"] or fwd["slips"]) else dev
        record=f"{primary['wins']}–{primary['losses']}" if primary["settled"] else ("0–0" if meta["status"]!="BLOCKED" else "—")
        phase="FORWARD" if (fwd["dates"] or fwd["slips"]) else "DEV REPLAY"
        cards.append(f'''<button class="model-card {'active' if m=='V2' else ''}" data-model="{m}">
          <div class="mc-top"><span>{m} · {_h(meta['name'])}</span><i>{_h(meta['status'])}</i></div>
          <div class="mc-main"><b>{record}</b><span>{_money(primary['pnl'])} net</span></div>
          <div class="mc-foot"><span>{primary['slips']} slips</span><span>{phase}</span></div></button>''')
        histories.append(f'<div class="history-pane" id="hist-{m}">{_history_html(m,d["development"],d["forward"])}</div>')
    latest_rows=[]
    if latest.get("date"):
        date_s=latest["date"]
        for m in RESEARCH_MODELS:
            rr=[r for r in read_rows("parlay_decisions") if r.get("board_date")==date_s and r.get("model")==m]
            if not rr: continue
            plays=[r for r in rr if r.get("decision")=="play"]
            latest_rows.append(f'<tr><td>{m}</td><td>{max(_i(r.get("qualified_legs")) for r in rr)}</td><td>{max(_i(r.get("valid_pairs")) for r in rr)}</td><td>{len(plays)}</td><td>{" · ".join((r.get("book","").upper()+" "+(f"{int(float(r['price'])):+d}" if r.get("price") else "")) for r in plays) or "NO PLAY"}</td></tr>')
    latest_table=''.join(latest_rows) or '<tr><td colspan="5">No forward board frozen yet.</td></tr>'
    js=json.dumps(payload,separators=(",",":"))
    board_stamp = f"{latest.get('date','No forward board yet')} · frozen {latest.get('ts','—')}" if latest else "No forward board yet"
    version=LAB_VERSION
    return f'''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Parlay Lab · Forward Research</title>
<style>
:root{{--bg:#f5f5f7;--card:#fff;--ink:#1d1d1f;--mut:#6e6e73;--line:#e7e7ea;--blue:#0071e3;--green:#198754;--red:#d83b32}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);font-family:-apple-system,BlinkMacSystemFont,"SF Pro Display","Helvetica Neue",Arial,sans-serif;-webkit-font-smoothing:antialiased}}
a{{color:inherit;text-decoration:none}}.nav{{position:sticky;top:0;z-index:20;background:#f5f5f7dd;backdrop-filter:blur(18px);border-bottom:1px solid #0000000c}}.navin,.shell{{max-width:1220px;margin:auto;padding:0 22px}}.navin{{height:52px;display:flex;align-items:center;justify-content:space-between}}.brand{{font-weight:750}}.links{{font-size:12px;color:var(--mut);display:flex;gap:14px}}.hero{{padding:62px 0 24px}}h1{{font-size:52px;letter-spacing:-.055em;line-height:.98;margin:0 0 10px}}.hero p{{color:var(--mut);font-size:17px;max-width:760px;line-height:1.5}}.card{{background:var(--card);border:1px solid var(--line);border-radius:24px;box-shadow:0 18px 55px #00000010}}.performance{{padding:22px}}.perfhead{{display:flex;justify-content:space-between;gap:16px;align-items:flex-start}}.perfhead small{{color:var(--mut);font-size:10px;text-transform:uppercase;letter-spacing:.08em;font-weight:750}}.perfhead h2{{margin:5px 0 0;font-size:29px;letter-spacing:-.04em}}.stamp{{font-size:10px;padding:6px 9px;border-radius:999px;background:#f1f1f3;color:var(--mut)}}.metrics{{display:grid;grid-template-columns:repeat(8,1fr);gap:7px;margin:15px 0}}.metric{{padding:10px 11px;border-radius:13px;background:#f7f7f9;border:1px solid #eee}}.metric small{{display:block;font-size:8px;color:var(--mut);text-transform:uppercase;letter-spacing:.05em}}.metric b{{display:block;font-size:15px;margin-top:3px;white-space:nowrap}}.grid{{display:block}}.chart{{height:285px;border:1px solid var(--line);border-radius:17px;background:linear-gradient(#eee 1px,transparent 1px),linear-gradient(90deg,#eee 1px,transparent 1px),#fff;background-size:100% 25%,25% 100%}}.chart-note{{display:flex;justify-content:space-between;gap:10px;align-items:center;margin-top:7px;font-size:8px;color:var(--mut)}}.chart-note b{{color:var(--ink)}}svg{{width:100%;height:100%}}.models{{display:grid;grid-template-columns:repeat(8,minmax(0,1fr));gap:7px;margin-top:10px}}.model-card{{border:1px solid #eee;background:#fafafa;border-radius:14px;padding:9px 10px;text-align:left;cursor:pointer;min-width:0}}.model-card.active{{border-color:#b7d7f9;background:#eef6ff}}.mc-top,.mc-main,.mc-foot{{display:flex;justify-content:space-between;gap:8px;align-items:center}}.mc-top span{{font-size:10px;font-weight:750}}.mc-top i{{font-style:normal;font-size:7px;padding:3px 5px;border-radius:999px;background:#ececf0;color:var(--mut)}}.mc-main{{margin-top:8px}}.mc-main b{{font-size:19px}}.mc-main span{{font-size:8px;color:var(--mut);text-align:right}}.mc-foot{{margin-top:5px;font-size:7px;color:var(--mut)}}.model-detail{{margin-top:16px;padding-top:16px;border-top:1px solid var(--line)}}.detail-head{{display:flex;justify-content:space-between;gap:14px;align-items:flex-start;margin-bottom:10px}}.detail-title small{{display:block;font-size:8px;color:var(--mut);text-transform:uppercase;letter-spacing:.08em;font-weight:750}}.detail-title h3{{margin:4px 0 0;font-size:18px}}.theory-chip{{text-align:right;max-width:460px}}.theory-chip b{{display:inline-block;font-size:8px;padding:4px 6px;border-radius:999px;background:#eef6ff;color:#1769aa;margin-bottom:4px}}.theory-chip span{{display:block;color:var(--mut);font-size:9px;line-height:1.35}}.history-pane{{display:none}}.history-pane.active{{display:block}}.phase-title{{font-size:9px;text-transform:uppercase;letter-spacing:.08em;color:var(--mut);font-weight:750;margin:10px 0 6px}}details.week,details.day,details.slip{{border:1px solid #eee;border-radius:12px;background:#fff;margin:6px 0;overflow:hidden}}summary{{cursor:pointer;list-style:none;display:grid;grid-template-columns:1fr auto auto;gap:12px;align-items:center;padding:10px 11px;font-size:10px}}summary::-webkit-details-marker{{display:none}}summary span{{font-weight:700}}summary b{{font-size:9px;color:var(--mut)}}summary em{{font-style:normal;font-weight:750}}.weekbody,.daybody,.slipbody{{padding:0 10px 10px}}.day{{margin-left:8px!important;background:#fafafa!important}}.slip{{margin-left:8px!important}}.slipbody strong{{font-size:10px;display:block}}.slipbody div{{font-size:9px;color:var(--mut);margin-top:5px}}.platform-btn{{margin-top:8px;border:0;border-radius:8px;padding:6px 8px;font-size:8px;color:#999}}.win{{color:var(--green)!important}}.loss{{color:var(--red)!important}}.open{{color:var(--mut)!important}}.nop{{padding:10px;border-radius:10px;background:#f5f5f7;font-size:9px;display:flex;justify-content:space-between}}.emptyhist{{font-size:10px;color:var(--mut);padding:8px}}.lower{{display:grid;grid-template-columns:1fr;gap:14px;margin-top:14px}}.panel{{padding:18px}}.panel h3{{margin:0 0 5px;font-size:18px}}.panel p{{margin:0 0 12px;font-size:10px;color:var(--mut);line-height:1.45}}table{{width:100%;border-collapse:collapse;font-size:9px}}th,td{{padding:8px;border-bottom:1px solid #eee;text-align:left}}th{{color:var(--mut);text-transform:uppercase;letter-spacing:.05em;font-size:8px}}.notice{{margin-top:12px;padding:10px;border-radius:12px;background:#fff8e8;border:1px solid #f0dfb6;color:#665d4b;font-size:9px;line-height:1.45}}footer{{padding:44px 0 36px;color:var(--mut);font-size:9px}}
@media(max-width:1000px){{.metrics{{grid-template-columns:repeat(4,1fr)}}.models{{grid-template-columns:repeat(4,minmax(0,1fr))}}.lower{{grid-template-columns:1fr}}}}@media(max-width:620px){{.navin,.shell{{padding:0 14px}}h1{{font-size:40px}}.metrics{{grid-template-columns:repeat(2,1fr)}}.models{{grid-template-columns:repeat(2,minmax(0,1fr))}}.links{{display:none}}}}
</style></head><body><div class="nav"><div class="navin"><div class="brand">Parlay Lab</div><div class="links"><a href="ledger.html">Paper Ledger</a><a href="internal.html">H1–H4 Lab</a></div></div></div>
<main class="shell"><section class="hero"><h1>Frozen models.<br>Forward evidence.</h1><p>V1–V8 run in parallel on the same causal board. Development replays stay labeled separately; forward decisions never rewrite themselves after kickoff.</p></section>
<section class="card performance"><div class="perfhead"><div><small>Model tournament</small><h2>Equity + leaderboard</h2></div><div class="stamp">{_h(board_stamp)}</div></div>
<div class="metrics"><div class="metric"><small>Phase</small><b id="mxPhase">—</b></div><div class="metric"><small>Staked</small><b id="mxStake">—</b></div><div class="metric"><small>Gross</small><b id="mxGross">—</b></div><div class="metric"><small>Net</small><b id="mxNet">—</b></div><div class="metric"><small>ROI</small><b id="mxRoi">—</b></div><div class="metric"><small>Slips</small><b id="mxSlips">—</b></div><div class="metric"><small>Hit rate</small><b id="mxHit">—</b></div><div class="metric"><small>Avg joint P</small><b id="mxJoint">—</b></div></div>
<div class="grid"><div class="chart"><svg id="chart" viewBox="0 0 900 285"></svg></div><div class="chart-note"><span>All model curves remain visible for context.</span><b id="chartSelected">Selected · V2</b></div><div class="models">{''.join(cards)}</div><div class="notice">Forward results are the judge. Development replays (Sep 20–27) were used to discover the models and are not out-of-sample validation. Ticket prices are reconstructed independent products until live cross-game quote capture is added.</div></div>
<div class="model-detail"><div class="detail-head"><div class="detail-title"><small>Selected model</small><h3 id="theoryName">V2 · Depth</h3></div><div class="theory-chip"><b id="theoryStatus">LEAD</b><span id="theoryDetail">BOV + DK · REC &gt;1.5</span></div></div>{''.join(histories)}</div></section>
<div class="lower"><section class="card panel"><h3>Latest frozen board</h3><p>Opportunity density and final slip count by model. V3 is intended to widen the candidate pool; V8 tests whether exceptional boards support a second independent slip.</p><table><tr><th>model</th><th>legs</th><th>pairs</th><th>slips</th><th>research execution</th></tr>{latest_table}</table></section></div>
{_sgp_shadow.dashboard_html()}
<footer>Paper research only · nothing is automatically wagered · code version {_h(version)}.</footer></main>
<script>const DATA={js};let active='V2';const $=id=>document.getElementById(id);
const COLORS={{V1:'#6e6e73',V2:'#0071e3',V3:'#6f8fb3',V4:'#8f7aa8',V5:'#6d9d88',V6:'#a88a68',V7:'#aaaab0',V8:'#566b8c'}};
function money(x){{x=Number(x||0);return (x>0?'+':'')+'$'+x.toFixed(2)}}
function pct(x){{return x==null?'—':Number(x).toFixed(1)+'%'}}
function primary(m){{let d=DATA[m];return (d.fwd.dates||d.fwd.slips)?d.fwd:d.dev}}
function select(m){{
  active=m;
  document.querySelectorAll('.model-card').forEach(b=>b.classList.toggle('active',b.dataset.model===m));
  document.querySelectorAll('.history-pane').forEach(p=>p.classList.toggle('active',p.id==='hist-'+m));
  let d=DATA[m],r=primary(m),phase=(d.fwd.dates||d.fwd.slips)?'FORWARD':'DEV REPLAY';
  $('mxPhase').textContent=phase;$('mxStake').textContent='$'+Number(r.stake||0).toFixed(2);$('mxGross').textContent='$'+Number(r.gross||0).toFixed(2);
  $('mxNet').textContent=money(r.pnl);$('mxRoi').textContent=r.roi==null?'—':Number(r.roi).toFixed(1)+'%';$('mxSlips').textContent=r.slips;
  $('mxHit').textContent=r.hit==null?'—':Number(r.hit).toFixed(1)+'%';$('mxJoint').textContent=r.avg_joint==null?'—':Number(r.avg_joint).toFixed(1)+'%';
  $('theoryName').textContent=m+' · '+d.meta.name;$('theoryStatus').textContent=d.meta.status;$('theoryDetail').textContent=d.meta.detail;
  $('chartSelected').textContent='Selected · '+m;
  draw();
}}
function draw(){{
  let s=$('chart'),ns='http://www.w3.org/2000/svg';s.innerHTML='';
  let nets=Object.keys(DATA).map(m=>Number(primary(m).pnl||0));
  let min=Math.min(-5,0,...nets),max=Math.max(10,0,...nets);if(max-min<10)max=min+10;
  const y=v=>240-180*(v-min)/(max-min);
  for(let i=0;i<5;i++){{
    let v=min+(max-min)*i/4,yy=y(v);
    let l=document.createElementNS(ns,'line');l.setAttribute('x1',70);l.setAttribute('x2',850);l.setAttribute('y1',yy);l.setAttribute('y2',yy);l.setAttribute('stroke',Math.abs(v)<.001?'#cfcfd4':'#e8e8eb');s.appendChild(l);
    let t=document.createElementNS(ns,'text');t.setAttribute('x',12);t.setAttribute('y',yy+4);t.setAttribute('font-size',10);t.setAttribute('fill','#888');t.textContent=(v>=0?'+':'')+'$'+v.toFixed(0);s.appendChild(t)
  }}
  Object.keys(DATA).filter(m=>m!==active).forEach(m=>{{
    let net=Number(primary(m).pnl||0),c=COLORS[m]||'#8e8e93';
    let p=document.createElementNS(ns,'polyline');p.setAttribute('points','110,'+y(0)+' 790,'+y(net));p.setAttribute('fill','none');p.setAttribute('stroke',c);p.setAttribute('stroke-width',2);p.setAttribute('stroke-opacity','.18');p.setAttribute('stroke-linecap','round');s.appendChild(p);
    let e=document.createElementNS(ns,'circle');e.setAttribute('cx',790);e.setAttribute('cy',y(net));e.setAttribute('r',3);e.setAttribute('fill',c);e.setAttribute('fill-opacity','.22');s.appendChild(e)
  }});
  let net=Number(primary(active).pnl||0),c=COLORS[active]||'#0071e3';
  let halo=document.createElementNS(ns,'polyline');halo.setAttribute('points','110,'+y(0)+' 790,'+y(net));halo.setAttribute('fill','none');halo.setAttribute('stroke','#fff');halo.setAttribute('stroke-width',8);halo.setAttribute('stroke-linecap','round');s.appendChild(halo);
  let p=document.createElementNS(ns,'polyline');p.setAttribute('points','110,'+y(0)+' 790,'+y(net));p.setAttribute('fill','none');p.setAttribute('stroke',c);p.setAttribute('stroke-width',4);p.setAttribute('stroke-linecap','round');s.appendChild(p);
  [[110,0],[790,net]].forEach(([x,v])=>{{let e=document.createElementNS(ns,'circle');e.setAttribute('cx',x);e.setAttribute('cy',y(v));e.setAttribute('r',5);e.setAttribute('fill',c);e.setAttribute('stroke','#fff');e.setAttribute('stroke-width',2);s.appendChild(e)}});
  let label=document.createElementNS(ns,'text');label.setAttribute('x',800);label.setAttribute('y',y(net)+4);label.setAttribute('font-size',10);label.setAttribute('font-weight','700');label.setAttribute('fill',c);label.textContent=active+' '+money(net);s.appendChild(label);
  [['Start',110],['Current',790]].forEach(([x,a])=>{{let t=document.createElementNS(ns,'text');t.setAttribute('x',a-20);t.setAttribute('y',270);t.setAttribute('font-size',10);t.setAttribute('fill','#888');t.textContent=x;s.appendChild(t)}})
}}
document.querySelectorAll('.model-card').forEach(b=>b.addEventListener('click',()=>select(b.dataset.model)));select('V2');</script></body></html>'''


def write_dashboard():
    page=render_dashboard()
    with open(os.path.join(DOCS,"index.html"),"w",encoding="utf-8") as f: f.write(page)
    return page


def run_tick(now=None):
    """Freeze if eligible, settle prior decisions, and render the dashboard. Returns activity counts."""
    n_freeze=freeze_today(now)
    n_settle=settle_forward(now)
    write_dashboard()
    return dict(frozen_rows=n_freeze, settled=n_settle)


if __name__ == "__main__":
    a=run_tick(); print(json.dumps(a,sort_keys=True)); print(daily_telegram() or "no daily board")
