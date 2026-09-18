"""run.py — one scheduled tick. Called by GitHub Actions every 6 hours.

  snapshot -> close -> report(dashboard)
  Telegram: 'board captured' once per ISO week (first snapshot with events),
            weekly summary once per week on Tuesday, and any failure immediately.
"""
import traceback, datetime as dt
from common import *
import snapshot, close, report, slips

def main():
    api = Api()
    now = utcnow(); week = now.strftime("%G-W%V")
    try:
        snaps = []
        for sport in SPORTS:
            snaps.append(snapshot.run(api, sport=sport))
        cl = close.run(api)
        n_auto = dict(straight=slips.auto_log(), parlay=slips.auto_parlays(), sgp=slips.auto_sgps(api))
        slips.settle()
        s = report.build()
        open(os.path.join(DOCS, "index.html"), "w").write(report.html_page(s))
        events_seen = sum(x["events"] for x in snaps)
        if events_seen and state_get("board_msg_week") != week:
            telegram(report.text_summary(s, "board")); state_set("board_msg_week", week)
        if now.weekday() == 1 and 12 <= now.hour < 19 and state_get("summary_week") != week:   # Tuesday, ~8am–3pm ET
            telegram(report.text_summary(s, "weekly")); state_set("summary_week", week)
        if events_seen == 0 and now.weekday() in (3, 4, 5, 6):                                 # Thu–Sun with nothing captured
            telegram(f"Eevee — warning: snapshot found 0 events on {now:%a %H:%M}Z. API remaining={api.remaining}")
        print("tick ok", dict(events=events_seen, auto_slips=n_auto, api_calls=api.calls, remaining=api.remaining))
    except Exception as e:
        telegram(f"Eevee — FAILED {now:%a %Y-%m-%d %H:%M}Z\n{type(e).__name__}: {e}"[:3500])
        traceback.print_exc(); raise

if __name__ == "__main__":
    main()
