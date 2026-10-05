"""run.py — phased Eevee pipeline.

The scheduled workflow commits after each time-sensitive phase:
  capture -> COMMIT exact board -> research/freeze -> COMMIT decisions -> settle/report -> COMMIT

That ordering makes a provider outage downstream unable to erase a successfully captured board.
Official V1–V8 and S0–S3 rules are unchanged; additive instrumentation lives in separate files.
"""
import argparse
import traceback

from common import *
import snapshot, close, report, slips, parlay_lab, sgp_shadow
import instrumentation, closing_capture, shadow_lab, evidence_report, calibration_report


def _clock(now=None):
    now=now or utcnow(); local=now.astimezone(parlay_lab.NY); week=local.strftime("%G-W%V")
    return now,local,week


def capture_phase(api,now=None,hours_before=None,legacy_sgp=True):
    now,local,_=_clock(now)
    snaps=[]
    for sport in SPORTS:
        snaps.append(snapshot.run(api,sport=sport,do_sgp=legacy_sgp,hours_before=hours_before))
    events_seen=sum(x.get("events",0) for x in snaps)

    # Additive metadata. Failures here are warnings; the canonical /ev board is already persisted.
    meta=context=steam={}
    try:
        max_hours=min(float(hours_before),36.0) if hours_before is not None else 36.0
        meta=instrumentation.capture_live_meta(api,now,max_hours=max_hours)
    except Exception as e:
        meta={"warning":f"{type(e).__name__}: {e}"}; print("metadata warning",meta["warning"]); traceback.print_exc()
    try:
        max_hours=min(float(hours_before),36.0) if hours_before is not None else 36.0
        context=instrumentation.capture_context(api,now,max_hours=max_hours)
    except Exception as e:
        context={"warning":f"{type(e).__name__}: {e}"}; print("context warning",context["warning"]); traceback.print_exc()
    try:
        steam_hours=min(float(hours_before),12.0) if hours_before is not None else 12.0
        steam=instrumentation.capture_movement(api,now,max_hours=steam_hours)
    except Exception as e:
        steam={"warning":f"{type(e).__name__}: {e}"}; print("steam warning",steam["warning"]); traceback.print_exc()

    try:
        shadow_obs=shadow_lab.run_observe(now)
    except Exception as e:
        shadow_obs=0; print("shadow-observe warning",type(e).__name__,e); traceback.print_exc()

    if events_seen==0 and local.weekday() in (3,4,5,6):
        telegram(f"Eevee — warning: snapshot found 0 events on {local:%a %H:%M} ET. API remaining={api.remaining}")
    instrumentation.health("capture","ok",events_seen,sum(x.get("changed_lines",0) for x in snaps),api,
                           note=f"hours_before={hours_before or SNAPSHOT_HOURS_BEFORE}; shadow={shadow_obs}")
    out=dict(events=events_seen,snapshots=snaps,meta=meta,context=context,steam=steam,
             shadow_observations=shadow_obs,api_calls=api.calls,remaining=api.remaining)
    print("capture ok",out); return out


def research_phase(api,now=None,legacy_auto=True):
    now,local,_=_clock(now)

    # Preserve the older experiment on the normal cadence only. Fast game-day capture can disable it.
    if legacy_auto:
        n_auto=dict(straight=slips.auto_log(),parlay=slips.auto_parlays(),sgp=slips.auto_sgps(api))
    else:
        n_auto=dict(straight=0,parlay=0,sgp=0)

    # Official cross-game freeze, unchanged.
    frozen=parlay_lab.freeze_today(now)

    # Official SGP shadow observe/freeze, unchanged. Settlement is a later phase.
    sgp_obs=sgp_shadow.observe(now)
    try:
        sgp_quotes=sgp_shadow.track_quote_history(api,now)
    except Exception as e:
        sgp_quotes={"warning":f"{type(e).__name__}: {e}"}
        print("sgp quote history warning",sgp_quotes["warning"])
        traceback.print_exc()
    sgp_fr=sgp_shadow.freeze(api,now)
    parlay_lab.write_dashboard()

    date_s=local.date().isoformat()
    if frozen and state_get("parlay_gameday_msg_date")!=date_s:
        msg=parlay_lab.daily_telegram(date_s)
        if msg:
            telegram(msg);state_set("parlay_gameday_msg_date",date_s)

    instrumentation.health("research","ok",sgp_fr.get("events",0),frozen+sgp_fr.get("decisions",0),api,
                           note=f"legacy_auto={legacy_auto}; sgp_obs={sgp_obs}")
    out=dict(auto_slips=n_auto,parlay_frozen_rows=frozen,sgp_observations=sgp_obs,
             sgp_quote_history=sgp_quotes,sgp_freeze=sgp_fr,api_calls=api.calls,remaining=api.remaining)
    print("research ok",out);return out


def settle_phase(api,now=None):
    now,local,week=_clock(now)

    # Original CLV endpoint is useful evidence but remains non-fatal.
    try:
        cl=close.run(api)
    except Exception as e:
        cl={"warning":f"{type(e).__name__}: {e}"};print("close warning (continuing settle):",cl["warning"]);traceback.print_exc()

    # Independent canonical closing-line archive + ID-aware CLV.
    try:
        canonical_close=closing_capture.run(api,now)
    except Exception as e:
        canonical_close={"warning":f"{type(e).__name__}: {e}"};print("canonical-close warning",canonical_close["warning"]);traceback.print_exc()

    legacy_settled=slips.settle()
    parlay_settled=parlay_lab.settle_forward(now)
    sgp_settled=sgp_shadow.settle(now)
    shadow_settled=shadow_lab.run_settle(now)

    parlay_lab.write_dashboard()
    report.write_pages()
    evidence_report.write()
    calibration_report.write()

    if local.weekday()==1 and 8<=local.hour<15 and state_get("parlay_summary_week")!=week:
        telegram(parlay_lab.weekly_telegram(now));state_set("parlay_summary_week",week)

    instrumentation.health("settle","ok",0,legacy_settled+parlay_settled+sgp_settled.get("decisions",0)+shadow_settled,api,
                           note=f"canonical_close={canonical_close}")
    out=dict(close=cl,canonical_close=canonical_close,legacy_settled=legacy_settled,
             parlay_settled=parlay_settled,sgp_settled=sgp_settled,shadow_settled=shadow_settled,
             api_calls=api.calls,remaining=api.remaining)
    print("settle ok",out);return out


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--phase",choices=("all","capture","research","settle"),default="all")
    ap.add_argument("--hours-before",type=float)
    ap.add_argument("--no-legacy-sgp",action="store_true",help="skip old random H4 probes on fast capture runs")
    ap.add_argument("--no-legacy-auto",action="store_true",help="skip old auto slip generation on fast research runs")
    a=ap.parse_args()

    api=Api();now=utcnow()
    try:
        if a.phase=="capture":
            return capture_phase(api,now,a.hours_before,legacy_sgp=not a.no_legacy_sgp)
        if a.phase=="research":
            return research_phase(api,now,legacy_auto=not a.no_legacy_auto)
        if a.phase=="settle":
            return settle_phase(api,now)

        out={}
        out["capture"]=capture_phase(api,now,a.hours_before,legacy_sgp=not a.no_legacy_sgp)
        out["research"]=research_phase(api,now,legacy_auto=not a.no_legacy_auto)
        out["settle"]=settle_phase(api,now)
        print("tick ok",out);return out
    except Exception as e:
        _,local,_=_clock(now)
        telegram(f"Eevee — FAILED {local:%a %Y-%m-%d %H:%M} ET\n{type(e).__name__}: {e}"[:3500])
        instrumentation.health(a.phase,"failed",0,0,api,note=f"{type(e).__name__}: {e}")
        traceback.print_exc();raise


if __name__=="__main__":
    main()
