"""snapshot.py — capture the board.

For every upcoming event (within SNAPSHOT_HOURS_BEFORE):
  1. GET /ev            -> data/lines.csv     (change-only: a row is written when price/fair/ev moved)
  2. apply GATE         -> data/candidates.csv (singles that pass; the "slips" of this experiment)
  3. POST /sgp probes   -> data/sgp.csv       (H4: book's correlated price vs independent product)

Usage: python3 snapshot.py                 (live)
       python3 snapshot.py --from-file f.json --event-id 32646   (offline test on a saved /ev response)
"""
import argparse, json, random, hashlib
from common import *

LINE_FIELDS = ["ts", "sport", "event_id", "commence_time", "home", "away", "market", "player", "point",
               "side", "book", "price", "ev_pct", "fair_prob", "fair_source", "n_books", "hours_to_kick"]
CAND_FIELDS = LINE_FIELDS + ["bettable", "gate_note"]
SGP_FIELDS = ["ts", "sport", "event_id", "book", "legs", "sgp_price", "independent_price",
              "correlation_factor", "quoted", "note"]

def line_key(r):
    return "|".join(str(r[k]) for k in ("event_id", "market", "player", "point", "side", "book"))

def sig(r):
    return f"{r['price']}|{r['fair_prob']}|{r['ev_pct']}"

def flatten_ev(ev, sport, ts):
    """One row per (line, tracked book outcome)."""
    rows = []
    kick = parse_iso(ev["commence_time"]); h2k = round((kick - parse_iso(ts)).total_seconds() / 3600, 1)
    for l in ev.get("lines", []):
        mk = l["market_key"]
        if not mk.startswith("player_"): continue
        books = {o["book"] for o in l["outcomes"]}
        for o in l["outcomes"]:
            if o["book"] not in BOOKS_TRACKED: continue
            fp = l["fair_probs"].get(o["name"])
            rows.append(dict(ts=ts, sport=sport, event_id=str(ev["id"]), commence_time=ev["commence_time"],
                             home=ev["home_team"], away=ev["away_team"], market=mk,
                             player=l["description"], point=l["point"] if l["point"] is not None else "",
                             side=o["name"], book=o["book"], price=o["price"], ev_pct=o["ev_pct"],
                             fair_prob=fp if fp is not None else "", fair_source=l["fair_source"],
                             n_books=len(books), hours_to_kick=h2k))
    return rows

def passes_gate(r):
    """Return (ok, note). Pure function of one line row."""
    try:
        fp = float(r["fair_prob"]); ev = float(r["ev_pct"]); nb = int(r["n_books"])
    except (TypeError, ValueError):
        return False, "no fair prob"
    if not (GATE["fair_min"] <= fp <= GATE["fair_max"]): return False, "deep alt"
    if nb < GATE["min_books"]: return False, f"{nb} books"
    if r["fair_source"] not in GATE["trusted_anchors"] and nb < GATE["kalshi_min_books"]:
        return False, f"{r['fair_source']} anchor, {nb} books"
    if ev < GATE["min_ev_pct"]: return False, f"ev {ev:+.1f}"
    return True, f"ev {ev:+.1f} fair {fp:.3f} {r['fair_source']} {nb}b"

def sgp_probes(api, ev, sport, ts, rows):
    """H4: pick a few pairs of near-main legs from different players, ask the book its SGP price."""
    out = []
    mains = [r for r in rows if r["book"] in SGP_BOOKS and r["fair_prob"] != "" and 0.4 <= float(r["fair_prob"]) <= 0.6
             and r["market"] in ("player_pass_yds", "player_rush_yds", "player_reception_yds", "player_receptions")]
    for book in SGP_BOOKS:
        pool = [r for r in mains if r["book"] == book]
        players = {}
        for r in pool: players.setdefault(r["player"], []).append(r)
        if len(players) < 2: continue
        rnd = random.Random(int(hashlib.md5(f"{ev['id']}{ts[:10]}{book}".encode()).hexdigest(), 16))
        for _ in range(SGP_PROBES_PER_EVENT):
            a, b = rnd.sample(sorted(players), 2)
            la, lb = rnd.choice(players[a]), rnd.choice(players[b])
            legs = [{"market": la["market"], "name": la["side"], "description": la["player"], "point": float(la["point"])},
                    {"market": lb["market"], "name": lb["side"], "description": lb["player"], "point": float(lb["point"])}]
            res = api.post(f"/sports/{sport}/events/{ev['id']}/sgp", {"bookmaker": book, "legs": legs})
            note = ""
            if "_error" in res: note = f"http {res['_error']}"
            out.append(dict(ts=ts, sport=sport, event_id=str(ev["id"]), book=book, legs=json.dumps(legs),
                            sgp_price=res.get("sgp_price", ""), independent_price=res.get("independent_price", ""),
                            correlation_factor=res.get("correlation_factor", ""), quoted=res.get("quoted", ""), note=note))
    return out

def run(api=None, from_file=None, event_id=None, sport="football_nfl", do_sgp=True):
    ts = iso()
    seen = state_get("line_sigs", {})          # key -> sig of last written row (change-only)
    n_lines = n_cand = n_sgp = n_events = 0
    events = []
    if from_file:
        ev = json.load(open(from_file)); ev["id"] = event_id or ev["id"]; events = [ev]
    else:
        evs = api.get(f"/sports/{sport}/events")
        if isinstance(evs, dict) and "_error" in evs: raise RuntimeError(f"events: {evs}")
        now = utcnow()
        for e in evs:
            kick = parse_iso(e["commence_time"])
            if 0 < (kick - now).total_seconds() / 3600 <= SNAPSHOT_HOURS_BEFORE:
                ev = api.get(f"/sports/{sport}/events/{e['id']}/ev")
                if isinstance(ev, dict) and "_error" not in ev and ev.get("lines"):
                    events.append(ev)
    for ev in events:
        n_events += 1
        rows = flatten_ev(ev, sport, ts)
        changed = []
        for r in rows:
            k = line_key(r); s = sig(r)
            if seen.get(k) != s:
                seen[k] = s; changed.append(r)
        n_lines += append_rows("lines", changed, LINE_FIELDS)
        cands = []
        for r in rows:
            ok, note = passes_gate(r)
            if ok:
                c = dict(r); c["bettable"] = r["book"] in BETTABLE; c["gate_note"] = note; cands.append(c)
        n_cand += append_rows("candidates", cands, CAND_FIELDS)
        if do_sgp and api is not None:
            n_sgp += append_rows("sgp", sgp_probes(api, ev, sport, ts, rows), SGP_FIELDS)
        append_rows("events", [dict(event_id=str(ev["id"]), sport=sport, home=ev["home_team"], away=ev["away_team"],
                                    commence_time=ev["commence_time"], first_seen=ts)],
                    ["event_id", "sport", "home", "away", "commence_time", "first_seen"]) \
            if str(ev["id"]) not in {e["event_id"] for e in read_rows("events")} else None
    state_set("line_sigs", seen)
    state_set("last_snapshot", ts)
    summary = dict(ts=ts, events=n_events, changed_lines=n_lines, candidates=n_cand, sgp_probes=n_sgp,
                   api_calls=getattr(api, "calls", 0), api_remaining=getattr(api, "remaining", None))
    print(json.dumps(summary)); return summary

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--from-file"); ap.add_argument("--event-id"); ap.add_argument("--sport", default="football_nfl")
    ap.add_argument("--no-sgp", action="store_true")
    a = ap.parse_args()
    api = None if a.from_file else Api()
    run(api, a.from_file, a.event_id, a.sport, do_sgp=not a.no_sgp)
