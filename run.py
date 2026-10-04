"""run.py — one scheduled tick. Called by GitHub Actions every 6 hours.

  snapshot -> close -> legacy paper slips -> cross-game forward research -> SGP shadow research -> reports

Telegram is now intentionally compact:
  * game-day: Parlay Lab high-quality research lineups only (deduped across V1–V8)
  * Tuesday: compact cross-game Parlay Lab model-tournament summary
  * SGP shadow research is dashboard-only and never sent as a game-day action message
  * fatal pipeline failures / empty-snapshot warnings remain immediate
  * recoverable CLV outages are logged but do NOT abort the research tick

The older Top-8-straights / board-captured Telegram messages are retired; the full legacy
ledger and H1–H4 diagnostics remain available on the dashboard pages.
"""
import traceback
import datetime as dt
from common import *
import snapshot, close, report, slips, parlay_lab, sgp_shadow


def main():
    api = Api()
    now = utcnow(); local = now.astimezone(parlay_lab.NY); week = local.strftime("%G-W%V")
    try:
        snaps = []
        for sport in SPORTS:
            snaps.append(snapshot.run(api, sport=sport))

        # CLV is evidence, not a dependency of the forward decision engine.
        # A provider timeout must never cost us a causal board freeze.
        try:
            cl = close.run(api)
        except Exception as e:
            cl = {"warning": f"{type(e).__name__}: {e}"}
            print("close warning (continuing tick):", cl["warning"])
            traceback.print_exc()

        # Preserve the original experiment exactly; these remain paper-only audit data.
        n_auto = dict(straight=slips.auto_log(), parlay=slips.auto_parlays(), sgp=slips.auto_sgps(api))
        slips.settle()

        # New additive research layer. A board is frozen once and never rewritten after later prices arrive.
        pl = parlay_lab.run_tick(now)

        # Separate single-game SGP shadow family. This records paper research only; it never alters V1–V8.
        sgp_shadow_tick = sgp_shadow.run_tick(api, now)

        # Re-render once after SGP shadow state is written so the homepage shows both research families.
        parlay_lab.write_dashboard()

        # Original pages survive as ledger.html + internal.html. Parlay Lab owns docs/index.html.
        s = report.write_pages()

        date_s = local.date().isoformat()
        if pl.get("frozen_rows") and state_get("parlay_gameday_msg_date") != date_s:
            msg = parlay_lab.daily_telegram(date_s)
            if msg:
                telegram(msg); state_set("parlay_gameday_msg_date", date_s)

        # Tuesday morning/afternoon ET: compact forward model tournament, not the older long H1-H4 message.
        if local.weekday() == 1 and 8 <= local.hour < 15 and state_get("parlay_summary_week") != week:
            telegram(parlay_lab.weekly_telegram(now)); state_set("parlay_summary_week", week)

        events_seen = sum(x["events"] for x in snaps)
        if events_seen == 0 and local.weekday() in (3, 4, 5, 6):
            telegram(f"Eevee — warning: snapshot found 0 events on {local:%a %H:%M} ET. API remaining={api.remaining}")

        print("tick ok", dict(events=events_seen, close=cl, auto_slips=n_auto, parlay_lab=pl,
                              sgp_shadow=sgp_shadow_tick, api_calls=api.calls, remaining=api.remaining))
    except Exception as e:
        telegram(f"Eevee — FAILED {local:%a %Y-%m-%d %H:%M} ET\n{type(e).__name__}: {e}"[:3500])
        traceback.print_exc(); raise


if __name__ == "__main__":
    main()
