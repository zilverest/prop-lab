"""slips.py — turn logged candidates into tracked slips (paper only, $5 flat per slip).

  python3 slips.py list [--n 20]                        list recent distinct candidates, indexed
  python3 slips.py straight --idx 3                      log a $5 straight bet on candidate #3 (manual)
  python3 slips.py sgp --idx 3,7 --book fanduel           log a $5 SGP ticket from two same-event candidates
  python3 slips.py settle                                 resolve open slips against data/results.csv
  python3 slips.py show                                   print the ledger + running P&L

`auto_log()` is called every tick from run.py: every distinct gated candidate becomes a $5 paper
straight automatically (idempotent — won't double-log the same leg). `straight` / `sgp` above are
for manually building extra tickets (e.g. an SGP combo) on top of that. All paper, no real stakes.
"""
import argparse, json
from common import *

SLIP_FIELDS = ["ts", "kind", "event_id", "book", "legs", "price", "stake", "ev_pct_at_bet",
               "fair_prob_at_bet", "correlation_factor", "quoted", "resolution", "pnl_units",
               "settled_ts", "note"]

# ---------------------------------------------------------------- candidates
def distinct_candidates():
    """Latest observation of each distinct (event,market,player,point,side,book), newest first."""
    seen = {}
    for c in read_rows("candidates"):
        k = (c["event_id"], c["market"], c["player"], c["point"], c["side"], c["book"])
        seen[k] = c
    return sorted(seen.values(), key=lambda c: c["ts"], reverse=True)

def label(c):
    leg = f"{c['player']} {c['market'].replace('player_','')} {c['side']} {c['point']}"
    return f"{c['away']} @ {c['home']}  |  {leg}  |  {c['book']} {c['price']}  EV {float(c['ev_pct']):+.1f}%  ({c['fair_source']}/{c['n_books']}b)"

# ---------------------------------------------------------------- auto-log
def leg_key(c):
    return (c["event_id"], c["market"], c["player"], str(c["point"]), c["side"])

def leg_dict(c):
    return {"event_id": c["event_id"], "market": c["market"], "player": c["player"], "point": c["point"], "side": c["side"],
            "book": c.get("book", ""), "price": c.get("price", "")}

def open_candidates():
    """Distinct gated candidates whose game hasn't kicked off."""
    now = utcnow()
    return [c for c in distinct_candidates() if parse_iso(c["commence_time"]) > now]

def candidate_seen_counts():
    """How many times each distinct leg has been observed in candidates.csv — the persistence signal."""
    counts = {}
    for c in read_rows("candidates"):
        counts[leg_key(c)] = counts.get(leg_key(c), 0) + 1
    return counts

def candidate_score(c, seen_count):
    """Canonical quality score for one gated candidate leg. Additive and fully transparent — every
    part is shown wherever the score is displayed. Used both to rank picks (Telegram, dashboard) and,
    via AUTO_LOG_MIN_SCORE, to decide what gets auto-logged at all — the quality-over-quantity lever."""
    ev = float(c["ev_pct"]); fp = float(c["fair_prob"]); nb = int(c["n_books"]); src = c["fair_source"]
    parts = {"ev": round(ev, 2)}
    score = ev
    parts["anchor"] = 1.0 if src in GATE["trusted_anchors"] else 0.0; score += parts["anchor"]
    parts["depth"] = min(1.0, 0.25 * max(0, nb - 3)); score += parts["depth"]
    parts["persist"] = min(1.5, 0.5 * max(0, seen_count - 1)); score += parts["persist"]
    parts["coin"] = 0.5 if 0.45 <= fp <= 0.55 else 0.0; score += parts["coin"]
    parts["combo"] = -1.0 if c["market"] in COMBO_MARKETS else 0.0; score += parts["combo"]
    return round(score, 2), parts

def quality_candidates():
    """open_candidates() filtered to AUTO_LOG_MIN_SCORE. This is the single lever for 'more quality,
    less quantity' over time — raise the constant in common.py and every slip type tightens together,
    with no other code change."""
    counts = candidate_seen_counts()
    out = []
    for c in open_candidates():
        score, parts = candidate_score(c, counts.get(leg_key(c), 1))
        if score >= AUTO_LOG_MIN_SCORE:
            d = dict(c); d["_score"] = score; d["_parts"] = parts; out.append(d)
    return out

def logged_sets(kind):
    """{(book, frozenset(leg_keys))} for every slip of this kind already in the ledger."""
    out = set()
    for s in read_rows("slips"):
        if s["kind"] != kind: continue
        try: legs = json.loads(s["legs"])
        except json.JSONDecodeError: continue
        out.add((s["book"], frozenset((l.get("event_id", s["event_id"]), l["market"], l["player"], str(l["point"]), l["side"]) for l in legs)))
    return out

def _fnum(x, d=None):
    try: return float(x)
    except (TypeError, ValueError): return d

def _row(kind, book, combo, price, note, **extra):
    """combo items are candidate dicts (have ev_pct/fair_prob/n_books/fair_source). For a single-leg
    straight these are stored as-is; for multi-leg parlays/SGPs we store the average edge and fair
    probability across legs so the combo can be scored later, same as a straight."""
    evs = [_fnum(c.get("ev_pct")) for c in combo if _fnum(c.get("ev_pct")) is not None]
    fps = [_fnum(c.get("fair_prob")) for c in combo if _fnum(c.get("fair_prob")) is not None]
    r = dict(ts=iso(), kind=kind, event_id=",".join(sorted({c["event_id"] for c in combo})), book=book,
             legs=json.dumps([leg_dict(c) for c in combo]), price=price, stake=STAKE_USD,
             ev_pct_at_bet=round(sum(evs) / len(evs), 2) if evs else "",
             fair_prob_at_bet=round(sum(fps) / len(fps), 4) if fps else "",
             correlation_factor="", quoted="", resolution="open", pnl_units="", settled_ts="", note=note)
    r.update(extra); return r

def auto_log():
    """Every gated candidate that clears AUTO_LOG_MIN_SCORE -> $STAKE_USD straight. Idempotent."""
    existing = logged_sets("straight"); new = []
    for c in quality_candidates():
        k = (c["book"], frozenset([leg_key(c)]))
        if k in existing: continue
        new.append(_row("straight", c["book"], [c], c["price"], f"auto score={c['_score']}")); existing.add(k)
    return append_rows("slips", new, SLIP_FIELDS)

def _build_parlays(cands, construct, existing):
    """Shared parlay builder. `construct` is a label written to the note so report.py can compare rules.
    One book per ticket, one leg per game, pairs (1,2),(3,4),... up to MAX_PARLAYS_PER_BOOK plus one 3-leg.
    Priced as the independent product of the legs' decimal odds."""
    new = []; by_book = {}
    for c in cands: by_book.setdefault(c["book"], []).append(c)
    for book, legs in by_book.items():
        legs.sort(key=lambda c: -float(c["ev_pct"]))
        pool, seen_ev = [], set()
        for c in legs:
            if c["event_id"] in seen_ev: continue
            seen_ev.add(c["event_id"]); pool.append(c)
        combos = [pool[i:i + 2] for i in range(0, min(len(pool) - 1, 2 * MAX_PARLAYS_PER_BOOK), 2)]
        if len(pool) >= 3: combos.append(pool[:3])
        for combo in combos:
            if len(combo) < 2: continue
            k = (book, frozenset(leg_key(c) for c in combo))
            if k in existing: continue
            dec = 1.0
            for c in combo: dec *= am_to_dec(c["price"])
            new.append(_row("parlay", book, combo, dec_to_am(dec), f"auto construct={construct} legs={len(combo)} independent product"))
            existing.add(k)
    return new

def auto_parlays():
    """Two constructions run side by side so report.py can compare them:
      ev-ranked   — every gated candidate, ranked by EV (the original rule)
      anchor-pure — only legs with a trusted anchor (Pinnacle/Bovada) AND >= PARLAY_PURE_MIN_BOOKS quoting.
                    Theory: estimation error compounds in a parlay, so build from the least-noisy legs, not the biggest EV.
    A combo already logged under one construction is not re-logged under the other. Idempotent."""
    existing = logged_sets("parlay")
    cands = quality_candidates()
    pure = [c for c in cands if c["fair_source"] in GATE["trusted_anchors"] and int(c["n_books"]) >= PARLAY_PURE_MIN_BOOKS]
    new = _build_parlays(pure, "anchor-pure", existing)          # pure first so shared combos get the stricter label
    new += _build_parlays(cands, "ev-ranked", existing)
    return append_rows("slips", new, SLIP_FIELDS)

def is_stack(a, b):
    """Heuristic: a passer leg + a pass-catcher leg, same game, same direction. The feed has no team field,
    so this can occasionally pair a QB with the opposing team's receiver — labelled 'stack' but audit it."""
    mk = {a["market"], b["market"]}
    return bool(mk & PASSER_MARKETS) and bool(mk & CATCHER_MARKETS) and a["side"] == b["side"]

def _pick_sgp_pairs(legs):
    """From one game's candidates (EV-sorted) return {'stack': pair or None, 'stranger': pair or None}."""
    pairs = {"stack": None, "stranger": None}
    best = {"stack": -1e9, "stranger": -1e9}
    for i in range(len(legs)):
        for j in range(i + 1, len(legs)):
            a, b = legs[i], legs[j]
            if a["player"] == b["player"]: continue
            kind = "stack" if is_stack(a, b) else "stranger"
            score = float(a["ev_pct"]) + float(b["ev_pct"])
            if score > best[kind]: best[kind] = score; pairs[kind] = [a, b]
    return pairs

def auto_sgps(api):
    """Per game, two deliberate constructions, each sent to every SGP book for its own correlated price:
      stack    — passer + pass-catcher, same direction (positively correlated; tests whether books discount it enough)
      stranger — two unrelated legs (control: correlation_factor should sit near 1.0)
    Log only if quoted. One attempt per (book, legs) per SGP_RETRY_HOURS. Idempotent."""
    existing = logged_sets("sgp"); new = []
    attempted = state_get("sgp_attempted", {}); now = utcnow()
    by_event = {}
    for c in quality_candidates():
        if c["point"] in ("", None) or c["side"] not in ("Over", "Under"): continue
        by_event.setdefault(c["event_id"], []).append(c)
    for eid, legs in by_event.items():
        legs.sort(key=lambda c: -float(c["ev_pct"]))
        pairs = _pick_sgp_pairs(legs)
        sport = next((e["sport"] for e in read_rows("events") if e["event_id"] == eid), SPORTS[0])
        for construct, combo in pairs.items():
            if not combo: continue
            body_legs = [{"market": c["market"], "name": c["side"], "description": c["player"], "point": float(c["point"])} for c in combo]
            for book in SGP_BOOKS:
                k = (book, frozenset(leg_key(c) for c in combo))
                if k in existing: continue
                ak = f"{book}|{eid}|" + "|".join(sorted("/".join(x) for x in k[1]))
                last = attempted.get(ak)
                if last and (now - parse_iso(last)).total_seconds() < SGP_RETRY_HOURS * 3600: continue
                attempted[ak] = iso(now)
                res = api.post(f"/sports/{sport}/events/{eid}/sgp", {"bookmaker": book, "legs": body_legs})
                if not isinstance(res, dict) or res.get("quoted") is not True: continue
                new.append(_row("sgp", book, combo, res["sgp_price"],
                                f"auto construct={construct} independent_price={res.get('independent_price')}",
                                correlation_factor=res.get("correlation_factor", ""), quoted=True))
                existing.add(k)
    state_set("sgp_attempted", attempted)
    return append_rows("slips", new, SLIP_FIELDS)

def cmd_list(a):
    cands = distinct_candidates()[: a.n]
    if not cands: print("no candidates logged yet"); return
    for i, c in enumerate(cands):
        print(f"[{i}] {label(c)}")

# ---------------------------------------------------------------- build
def cmd_straight(a):
    cands = distinct_candidates()
    c = cands[a.idx]
    row = dict(ts=iso(), kind="straight", event_id=c["event_id"], book=c["book"],
               legs=json.dumps([{"market": c["market"], "player": c["player"], "point": c["point"], "side": c["side"]}]),
               price=c["price"], stake=STAKE_USD, ev_pct_at_bet=c["ev_pct"], fair_prob_at_bet=c["fair_prob"],
               correlation_factor="", quoted="", resolution="open", pnl_units="", settled_ts="", note="manual")
    append_rows("slips", [row], SLIP_FIELDS)
    print("logged straight:", label(c))

def cmd_sgp(a):
    idxs = [int(x) for x in a.idx.split(",")]
    cands = distinct_candidates()
    picked = [cands[i] for i in idxs]
    eids = {c["event_id"] for c in picked}
    if len(eids) != 1:
        print("all legs must be from the same event_id:", eids); return
    eid = picked[0]["event_id"]
    legs = [{"market": c["market"], "name": c["side"], "description": c["player"],
             "point": float(c["point"]) if c["point"] not in ("", None) else None} for c in picked]
    api = Api()
    sport = next((e["sport"] for e in read_rows("events") if e["event_id"] == eid), SPORTS[0])
    res = api.post(f"/sports/{sport}/events/{eid}/sgp", {"bookmaker": a.book, "legs": [
        {k: v for k, v in l.items() if v is not None} for l in legs]})
    if res.get("quoted") is not True:
        print("book would not quote this slip:", json.dumps(res)[:500]); return
    row = dict(ts=iso(), kind="sgp", event_id=eid, book=a.book,
               legs=json.dumps([{"market": c["market"], "player": c["player"], "point": c["point"], "side": c["side"]} for c in picked]),
               price=res["sgp_price"], stake=STAKE_USD, ev_pct_at_bet="",
               fair_prob_at_bet="", correlation_factor=res.get("correlation_factor", ""), quoted=True,
               resolution="open", pnl_units="", settled_ts="", note=f"manual independent_price={res.get('independent_price')}")
    append_rows("slips", [row], SLIP_FIELDS)
    print(f"logged SGP: {a.book} price {res['sgp_price']}  correlation_factor {res.get('correlation_factor')}")
    for c in picked: print("  leg:", label(c))

# ---------------------------------------------------------------- settle
UNGRADEABLE_AFTER_HOURS = 72     # a leg still unresolvable this long after kickoff is voided so nothing sits open forever

class Grader:
    """Resolves one slip leg against results.csv, in order of preference:
      1. exact grading row at the slip's own book (same event, market, player, point, side)
      2. exact grading row at any book
      3. the player's actual stat value vs our point (Over/Under legs only) — needed because when a
         line moves before kickoff, books stop listing the number we logged, so no exact row exists
    Returns 'won' | 'lost' | 'push' | 'void' | None (not graded yet)."""
    def __init__(self, results):
        self.exact_book, self.exact_any, self.actual = {}, {}, {}
        for r in results:
            k = (r["event_id"], r["market"], r["player"], str(r["point"]), r["side"])
            self.exact_book[k + (r["book"],)] = r["resolution"]
            if r["resolution"] in ("won", "lost", "push") or k not in self.exact_any:
                self.exact_any[k] = r["resolution"]                    # prefer a decided grade over a void
            if r.get("actual_value") not in ("", None):
                try: self.actual[k[:3]] = float(r["actual_value"])
                except ValueError: pass

    def leg(self, l, event_id, book):
        k = (event_id, l["market"], l["player"], str(l["point"]), l["side"])
        rb, ra = self.exact_book.get(k + (book,)), self.exact_any.get(k)
        for r in (rb, ra):
            if r in ("won", "lost", "push"): return r
        r = rb or ra
        a = self.actual.get(k[:3])
        if a is not None and l["point"] not in ("", None) and l["side"] in ("Over", "Under"):
            pt = float(l["point"])
            if a == pt: return "push"
            return "won" if (a > pt) == (l["side"] == "Over") else "lost"
        if r == "void": return "void"                                  # graded void and no stat recorded: player didn't play
        return None

def _leg_decimal(l, slip_book, cand_price):
    """Decimal odds for one leg: stored on the leg (new slips), else the candidates.csv price, else None."""
    if l.get("price") not in ("", None):
        try: return am_to_dec(int(float(l["price"])))
        except ValueError: pass
    p = cand_price.get((l.get("event_id"), l["market"], l["player"], str(l["point"]), l["side"], l.get("book") or slip_book))
    return am_to_dec(int(float(p))) if p not in ("", None) else None

def settle():
    """Resolve open slips. Multi-leg rules match how books settle:
       any leg lost -> lost; void/push legs are dropped and the rest pays at the reduced price;
       every leg void/push -> stake returned. Legs still ungradeable UNGRADEABLE_AFTER_HOURS after
       kickoff are treated as void so nothing stays open forever. Returns number of slips settled."""
    slips = read_rows("slips")
    if not slips: return 0
    g = Grader(read_rows("results"))
    kick = {e["event_id"]: e["commence_time"] for e in read_rows("events")}
    cand_price = {}
    for c in read_rows("candidates"):
        cand_price[(c["event_id"], c["market"], c["player"], str(c["point"]), c["side"], c["book"])] = c["price"]
    now = utcnow(); n = 0
    for s in slips:
        if s["resolution"] != "open": continue
        legs = json.loads(s["legs"])
        eids = [l.get("event_id") or s["event_id"].split(",")[0] for l in legs]
        res = []
        for l, e in zip(legs, eids):
            r = g.leg(l, e, s["book"])
            if r is None and e in kick and (now - parse_iso(kick[e])).total_seconds() > UNGRADEABLE_AFTER_HOURS * 3600:
                r = "void"
            res.append(r)
        if "lost" in res:                                               # decided even if other legs are pending
            s["resolution"], s["pnl_units"] = "lost", -float(s["stake"])
        elif any(r is None for r in res):
            continue
        else:
            live = [l for l, r in zip(legs, res) if r == "won"]
            stake = float(s["stake"])
            if not live:
                s["resolution"] = "void" if all(r == "void" for r in res) else "push"; s["pnl_units"] = 0.0
            elif len(live) == len(legs):
                s["resolution"], s["pnl_units"] = "won", (am_to_dec(s["price"]) - 1) * stake
            else:
                decs = [_leg_decimal(l, s["book"], cand_price) for l in live]
                if any(d is None for d in decs):                         # no per-leg price: split the ticket price evenly
                    decs = [am_to_dec(s["price"]) ** (1 / len(legs))] * len(live)
                d = 1.0
                for x in decs: d *= x
                s["resolution"], s["pnl_units"] = "won", (d - 1) * stake
                s["note"] = (s["note"] + f" reduced={len(live)}/{len(legs)} legs").strip()
        s["settled_ts"] = iso(); n += 1
    if n:
        import csv as _csv
        with open(csv_path("slips"), "w", newline="") as f:
            w = _csv.DictWriter(f, fieldnames=SLIP_FIELDS, extrasaction="ignore"); w.writeheader()
            for s in slips: w.writerow(s)
    return n

def _kind_stats(slips, kind):
    ks = [s for s in slips if s["kind"] == kind]
    settled = [s for s in ks if s["resolution"] != "open"]
    won = sum(s["resolution"] == "won" for s in settled); lost = sum(s["resolution"] == "lost" for s in settled)
    pnl = sum(float(s["pnl_units"]) for s in settled if s["pnl_units"] != "")
    staked = sum(float(s["stake"]) for s in settled if s["resolution"] in ("won", "lost"))
    return dict(n=len(ks), open=len(ks) - len(settled), won=won, lost=lost,
                win_pct=100 * won / (won + lost) if (won + lost) else None,
                pnl=pnl, roi=100 * pnl / staked if staked else None)

def ledger_summary():
    slips = read_rows("slips")
    if not slips: return dict(n=0)
    settled = [s for s in slips if s["resolution"] != "open"]
    pnl = sum(float(s["pnl_units"]) for s in settled if s["pnl_units"] != "")
    won = sum(s["resolution"] == "won" for s in settled)
    lost = sum(s["resolution"] == "lost" for s in settled)
    decided = won + lost                                   # pushes excluded from win%, standard convention
    staked = sum(float(s["stake"]) for s in settled if s["resolution"] in ("won", "lost"))
    return dict(n=len(slips), open=len(slips) - len(settled), settled=len(settled), won=won, lost=lost,
                win_pct=100 * won / decided if decided else None,
                pnl_units=pnl, roi=100 * pnl / staked if staked else None,
                staked_usd=staked, stake_usd=STAKE_USD,
                straights=sum(s["kind"] == "straight" for s in slips), sgps=sum(s["kind"] == "sgp" for s in slips),
                parlays=sum(s["kind"] == "parlay" for s in slips),
                by_kind={k: _kind_stats(slips, k) for k in ("straight", "parlay", "sgp")})

def cmd_settle(a):
    n = settle(); s = ledger_summary()
    print(f"settle pass done. ledger: {json.dumps(s)}")

def cmd_show(a):
    s = ledger_summary()
    if not s.get("n"): print("no slips logged yet"); return
    print(json.dumps(s, indent=1))
    for r in read_rows("slips")[-a.n:][::-1]:
        legs = json.loads(r["legs"])
        legtxt = " + ".join(f"{l['player']} {l['market'].replace('player_','')} {l['side']} {l['point']}" for l in legs)
        print(f"[{r['resolution']:>9}] {r['ts'][:16]}  {r['kind']:8}  {r['book']:10}  {r['price']:>5}  {legtxt}  pnl=${r['pnl_units'] or 0}")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    p = sp.add_parser("list"); p.add_argument("--n", type=int, default=20); p.set_defaults(f=cmd_list)
    p = sp.add_parser("straight"); p.add_argument("--idx", type=int, required=True); p.set_defaults(f=cmd_straight)
    p = sp.add_parser("sgp"); p.add_argument("--idx", required=True); p.add_argument("--book", default="fanduel"); p.set_defaults(f=cmd_sgp)
    p = sp.add_parser("settle"); p.set_defaults(f=cmd_settle)
    p = sp.add_parser("show"); p.add_argument("--n", type=int, default=15); p.set_defaults(f=cmd_show)
    a = ap.parse_args(); a.f(a)
