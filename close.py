"""close.py — after kickoff, settle the record.

For each event that has started and isn't closed yet:
  1. POST /clv/grade with every distinct candidate  -> data/clv.csv      (H2: did our price beat the close?)
  2. GET  /results (once final)                     -> data/results.csv  (won/lost/push + actual value)
Events are marked closed once results are final (or 3 days after kickoff, whichever first).
"""
import json
from common import *

CLV_FIELDS = ["graded_ts", "event_id", "market", "player", "point", "side", "book", "price", "ev_pct_at_bet",
              "fair_prob_at_bet", "matched", "unmatched_reason", "closing_price", "closing_point", "closing_fair_prob",
              "fair_source", "clv_pct", "ev_vs_close_pct", "beat_close", "resolution", "actual_value", "closing_is_final"]
RES_FIELDS = ["graded_ts", "event_id", "market", "player", "point", "side", "book", "price", "resolution", "actual_value"]

def distinct_candidates(event_id):
    seen = {}
    for c in read_rows("candidates"):
        if c["event_id"] != event_id: continue
        k = (c["market"], c["player"], c["point"], c["side"], c["book"])
        seen[k] = c                       # keep the latest observation of each distinct leg
    return list(seen.values())

def grade_clv(api, sport, event_id, cands, ts):
    bets = []
    for i, c in enumerate(cands):
        b = {"ref": str(i), "sport_key": sport, "event_id": int(event_id), "market": c["market"],
             "bookmaker": c["book"], "selection": c["player"], "side": c["side"], "price": int(c["price"]), "stake": 1}
        if c["point"] != "": b["point"] = float(c["point"])
        bets.append(b)
    if not bets: return []
    res = api.post("/clv/grade", bets)
    if not isinstance(res, dict) or "bets" not in res:
        print("clv/grade unexpected:", str(res)[:300]); return []
    out = []
    for b in res["bets"]:
        c = cands[int(b["ref"])]
        out.append(dict(graded_ts=ts, event_id=event_id, market=c["market"], player=c["player"], point=c["point"],
                        side=c["side"], book=c["book"], price=c["price"], ev_pct_at_bet=c["ev_pct"],
                        fair_prob_at_bet=c["fair_prob"], **{k: b.get(k, "") for k in
                        ("matched", "unmatched_reason", "closing_price", "closing_point", "closing_fair_prob", "fair_source",
                         "clv_pct", "ev_vs_close_pct", "beat_close", "resolution", "actual_value", "closing_is_final")}))
    return out

def pull_results(api, sport, event_id, ts):
    res = api.get(f"/sports/{sport}/events/{event_id}/results")
    if not isinstance(res, dict) or "_error" in res: return [], False
    final = res.get("status") == "final"
    out = []
    for bk in res.get("bookmakers", []):
        if bk["key"] not in BOOKS_TRACKED: continue
        for m in bk.get("markets", []):
            if not m["key"].startswith("player_"): continue
            for o in m.get("outcomes", []):
                out.append(dict(graded_ts=ts, event_id=event_id, market=m["key"], player=o.get("description", ""),
                                point=o.get("point", "") if o.get("point") is not None else "", side=o["name"],
                                book=bk["key"], price=o.get("price", ""), resolution=o.get("resolution", ""),
                                actual_value=o.get("actual_value", "")))
    return out, final

def run(api):
    ts = iso(); now = utcnow()
    closed = set(state_get("closed_events", []))
    graded_clv = set(state_get("clv_graded_events", []))
    n_clv = n_res = 0; done = []
    for e in read_rows("events"):
        eid = e["event_id"]
        if eid in closed: continue
        kick = parse_iso(e["commence_time"]); hrs = (now - kick).total_seconds() / 3600
        if hrs < 0: continue                                  # not started
        sport = e["sport"]
        if eid not in graded_clv and hrs >= 0.5:              # close is final once the game has started
            rows = grade_clv(api, sport, eid, distinct_candidates(eid), ts)
            n_clv += append_rows("clv", rows, CLV_FIELDS)
            if rows or not distinct_candidates(eid): graded_clv.add(eid)
        if hrs >= 4:                                          # game long over — try results
            rows, final = pull_results(api, sport, eid, ts)
            if final:
                n_res += append_rows("results", rows, RES_FIELDS); done.append(eid)
            elif hrs >= 72:
                done.append(eid)                              # give up on a result we never got; keep moving
    closed |= set(done)
    state_set("closed_events", sorted(closed)); state_set("clv_graded_events", sorted(graded_clv))
    summary = dict(ts=ts, clv_rows=n_clv, result_rows=n_res, events_closed=len(done), api_calls=api.calls)
    print(json.dumps(summary)); return summary

if __name__ == "__main__":
    run(Api())
