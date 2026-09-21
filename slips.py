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
    return {"event_id": c["event_id"], "market": c["market"], "player": c["player"], "point": c["point"], "side": c["side"]}

def open_candidates():
    """Distinct gated candidates whose game hasn't kicked off."""
    now = utcnow()
    return [c for c in distinct_candidates() if parse_iso(c["commence_time"]) > now]

def logged_sets(kind):
    """{(book, frozenset(leg_keys))} for every slip of this kind already in the ledger."""
    out = set()
    for s in read_rows("slips"):
        if s["kind"] != kind: continue
        try: legs = json.loads(s["legs"])
        except json.JSONDecodeError: continue
        out.add((s["book"], frozenset((l.get("event_id", s["event_id"]), l["market"], l["player"], str(l["point"]), l["side"]) for l in legs)))
    return out

def _row(kind, book, combo, price, note, **extra):
    r = dict(ts=iso(), kind=kind, event_id=",".join(sorted({c["event_id"] for c in combo})), book=book,
             legs=json.dumps([leg_dict(c) for c in combo]), price=price, stake=STAKE_USD,
             ev_pct_at_bet=combo[0]["ev_pct"] if len(combo) == 1 else "",
             fair_prob_at_bet=combo[0]["fair_prob"] if len(combo) == 1 else "",
             correlation_factor="", quoted="", resolution="open", pnl_units="", settled_ts="", note=note)
    r.update(extra); return r

def auto_log():
    """Every distinct gated candidate -> $STAKE_USD straight. Idempotent."""
    existing = logged_sets("straight"); new = []
    for c in distinct_candidates():
        k = (c["book"], frozenset([leg_key(c)]))
        if k in existing: continue
        new.append(_row("straight", c["book"], [c], c["price"], "auto")); existing.add(k)
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
    cands = open_candidates()
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
    for c in open_candidates():
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
def leg_resolution(results_index, event_id, market, player, point, side, book):
    key = (event_id, market, player, str(point), side, book)
    r = results_index.get(key)
    if r: return r["resolution"]
    # fall back to any book's grading of the same leg if our slip's book never resolved it
    for k, r in results_index.items():
        if k[:5] == key[:5]: return r["resolution"]
    return None

def settle():
    results = read_rows("results")
    idx = {(r["event_id"], r["market"], r["player"], str(r["point"]), r["side"], r["book"]): r for r in results}
    slips = read_rows("slips")
    if not slips: return 0
    changed = False
    for s in slips:
        if s["resolution"] != "open": continue
        legs = json.loads(s["legs"])
        resols = [leg_resolution(idx, l.get("event_id", s["event_id"]), l["market"], l["player"], l["point"], l["side"], s["book"]) for l in legs]
        if any(r is None for r in resols): continue                     # not all graded yet
        if any(r == "lost" for r in resols):
            s["resolution"], s["pnl_units"] = "lost", -float(s["stake"])
        elif all(r in ("won", "push") for r in resols) and any(r == "won" for r in resols) and all(r != "lost" for r in resols):
            wins = sum(r == "won" for r in resols)
            s["resolution"] = "won" if wins == len(resols) else "push_adj"
            s["pnl_units"] = (am_to_dec(s["price"]) - 1) * float(s["stake"]) if wins == len(resols) else 0.0
        elif all(r == "push" for r in resols):
            s["resolution"], s["pnl_units"] = "push", 0.0
        else:
            continue
        s["settled_ts"] = iso(); changed = True
    if changed:
        # rewrite whole file (small; simplest correct way to update in place)
        import os
        p = csv_path("slips")
        with open(p, "w", newline="") as f:
            import csv as _csv
            w = _csv.DictWriter(f, fieldnames=SLIP_FIELDS); w.writeheader()
            for s in slips: w.writerow(s)
    return sum(1 for s in slips if s["settled_ts"] == slips[0].get("settled_ts", "__never__")) if changed else 0

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
