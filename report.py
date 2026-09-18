"""report.py — turn the CSVs into verdicts.

  python3 report.py               -> writes docs/index.html, prints summary
  python3 report.py --telegram    -> also sends the summary to Telegram
  python3 report.py --kind board  -> short "board captured" message (Thursday)
"""
import argparse, html, json, statistics as st
from collections import defaultdict
from common import *

NEAR = (0.35, 0.65)

def latest_per_line(rows):
    """lines.csv is change-only; the latest row per key is the current state."""
    cur = {}
    for r in rows:
        k = (r["event_id"], r["market"], r["player"], r["point"], r["side"], r["book"])
        if k not in cur or r["ts"] > cur[k]["ts"]: cur[k] = r
    return list(cur.values())

def fnum(x, d=None):
    try: return float(x)
    except (TypeError, ValueError): return d

def book_stats(lines, book):
    sub = [r for r in lines if r["book"] == book and fnum(r["fair_prob"]) is not None
           and NEAR[0] <= fnum(r["fair_prob"]) <= NEAR[1] and int(r["n_books"]) >= 3]
    ev = [fnum(r["ev_pct"]) for r in sub]
    if not ev: return dict(n=0)
    return dict(n=len(ev), mean=st.mean(ev), median=st.median(ev), plus=sum(e > 0 for e in ev),
                plus3=sum(e >= 3 for e in ev), hist=hist(ev))

def hist(vals, lo=-15, hi=10, step=1):
    b = defaultdict(int)
    for v in vals: b[max(lo, min(hi - step, step * (v // step)))] += 1
    return [(x, b.get(x, 0)) for x in range(lo, hi, step)]

def h2_stats(clv):
    m = [r for r in clv if r["matched"] in ("True", "true", "1") and r["closing_is_final"] in ("True", "true", "1")]
    if not m: return dict(n=0)
    evc = [fnum(r["ev_vs_close_pct"]) for r in m if fnum(r["ev_vs_close_pct"]) is not None]
    beat = [r["beat_close"] in ("True", "true", "1") for r in m]
    res = [r for r in m if r["resolution"] in ("won", "lost", "push")]
    pnl = 0.0
    for r in res:
        if r["resolution"] == "won": pnl += am_to_dec(r["price"]) - 1
        elif r["resolution"] == "lost": pnl -= 1
    return dict(n=len(m), avg_ev_vs_close=st.mean(evc) if evc else None, beat_pct=100 * sum(beat) / len(beat),
                graded=len(res), pnl_units=pnl, roi=100 * pnl / len(res) if res else None,
                bettable=sum(r["book"] in BETTABLE for r in m))

def h4_stats(sgp):
    q = [fnum(r["correlation_factor"]) for r in sgp if r["quoted"] in ("True", "true", "1") and fnum(r["correlation_factor"])]
    if not q: return dict(n=0)
    return dict(n=len(q), mean=st.mean(q), median=st.median(q), under1=sum(x < 1 for x in q), over1=sum(x > 1 for x in q))

def verdicts(hr, ud, h2, h4, weeks):
    v = {}
    v["H3 Hard Rock singles"] = ("REJECT" if hr.get("n", 0) >= 200 and hr["plus3"] == 0 else "open") if hr.get("n") else "no data"
    v["H1 Underdog lines"] = ("REJECT" if ud.get("n", 0) >= 200 and ud["plus3"] == 0 else "open") if ud.get("n") else "no data"
    if h2.get("n", 0) >= 100:
        v["H2 CLV"] = "ACCEPT" if h2["avg_ev_vs_close"] > 0 and h2["beat_pct"] > 55 else "REJECT"
    else: v["H2 CLV"] = f"open ({h2.get('n', 0)}/100 legs)"
    if h4.get("n", 0) >= 60:
        v["H4 correlation"] = "REJECT (priced)" if 0.9 <= h4["median"] <= 1.1 else "open (factor off 1.0)"
    else: v["H4 correlation"] = f"open ({h4.get('n', 0)}/60 probes)"
    return v

def build():
    lines = latest_per_line(read_rows("lines")); cands = read_rows("candidates"); clv = read_rows("clv")
    sgp = read_rows("sgp"); events = read_rows("events")
    hr, ud = book_stats(lines, "hardrock"), book_stats(lines, "underdog")
    h2, h4 = h2_stats(clv), h4_stats(sgp)
    weeks = len({parse_iso(e["commence_time"]).strftime("%G-W%V") for e in events}) if events else 0
    distinct_c = {(c["event_id"], c["market"], c["player"], c["point"], c["side"], c["book"]) for c in cands}
    return dict(generated=iso(), events=len(events), weeks=weeks, lines=len(lines), candidates=len(distinct_c),
                bettable_candidates=len({k for k in distinct_c if k[5] in BETTABLE}), hr=hr, ud=ud, h2=h2, h4=h4,
                verdicts=verdicts(hr, ud, h2, h4, weeks), last_snapshot=state_get("last_snapshot"),
                recent_candidates=sorted(cands, key=lambda c: c["ts"])[-15:][::-1])

def fmt(x, d=1, suf=""):
    return "—" if x is None else f"{x:+.{d}f}{suf}" if isinstance(x, float) else str(x)

def text_summary(s, kind="weekly"):
    if kind == "board":
        return (f"Eevee — board captured {s['last_snapshot'] or ''}\n{s['events']} events tracked · {s['lines']} live lines\n"
                f"Hard Rock near-main: n={s['hr'].get('n',0)} mean EV {fmt(s['hr'].get('mean'))}% · +3% rows: {s['hr'].get('plus3',0)}\n"
                f"Candidates so far: {s['candidates']} ({s['bettable_candidates']} at Hard Rock)")
    L = [f"Eevee — weekly summary ({s['weeks']} wk, {s['events']} events)"]
    L.append(f"H3 Hard Rock: n={s['hr'].get('n',0)} mean {fmt(s['hr'].get('mean'))}% · +3%: {s['hr'].get('plus3',0)} → {s['verdicts']['H3 Hard Rock singles']}")
    L.append(f"H1 Underdog: n={s['ud'].get('n',0)} mean {fmt(s['ud'].get('mean'))}% · +3%: {s['ud'].get('plus3',0)} → {s['verdicts']['H1 Underdog lines']}")
    h2 = s["h2"]
    L.append(f"H2 CLV: {h2.get('n',0)} legs · EV vs close {fmt(h2.get('avg_ev_vs_close'))}% · beat close {fmt(h2.get('beat_pct'),0,'%')} → {s['verdicts']['H2 CLV']}")
    L.append(f"Paper: {h2.get('graded',0)} graded · {fmt(h2.get('pnl_units'),2)}u · ROI {fmt(h2.get('roi'))}%")
    h4 = s["h4"]
    L.append(f"H4 SGP: {h4.get('n',0)} probes · median factor {fmt(h4.get('median'),3) if h4.get('median') else '—'} → {s['verdicts']['H4 correlation']}")
    return "\n".join(L)

def svg_hist(h, title):
    if not h: return ""
    mx = max(c for _, c in h) or 1; w = 20; W = w * len(h) + 40; H = 120
    bars = "".join(f'<rect x="{30+i*w}" y="{100-90*c/mx:.1f}" width="{w-2}" height="{90*c/mx:.1f}" fill="{"#c0504d" if x<0 else "#4f9d69"}"/>'
                   for i, (x, c) in enumerate(h))
    ticks = "".join(f'<text x="{30+i*w+w/2}" y="114" font-size="8" text-anchor="middle" fill="#888">{x}</text>' for i, (x, _) in enumerate(h) if x % 5 == 0)
    return f'<h3>{title}</h3><svg viewBox="0 0 {W} {H}" width="100%" style="max-width:640px">{bars}{ticks}<line x1="{30+15*w}" y1="0" x2="{30+15*w}" y2="102" stroke="#999" stroke-dasharray="3"/></svg>'

def html_page(s):
    hr, ud, h2, h4 = s["hr"], s["ud"], s["h2"], s["h4"]
    vrows = "".join(f"<tr><td>{k}</td><td><b>{v}</b></td></tr>" for k, v in s["verdicts"].items())
    crow = "".join(f"<tr><td>{c['ts'][:16]}</td><td>{html.escape(c['away'])} @ {html.escape(c['home'])}</td><td>{html.escape(c['player'])}</td>"
                   f"<td>{c['market'].replace('player_','')} {c['side']} {c['point']}</td><td>{c['book']}</td><td>{c['price']}</td>"
                   f"<td>{fmt(fnum(c['ev_pct']))}%</td><td>{c['fair_source']}/{c['n_books']}b</td></tr>" for c in s["recent_candidates"])
    return f"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Eevee — prop lab</title><style>
:root{{--bg:#fff;--fg:#1a1a1a;--mut:#666;--card:#f6f6f6}}@media(prefers-color-scheme:dark){{:root{{--bg:#111;--fg:#eee;--mut:#999;--card:#1c1c1c}}}}
body{{font:15px/1.5 system-ui,sans-serif;background:var(--bg);color:var(--fg);max-width:900px;margin:0 auto;padding:16px}}
.card{{background:var(--card);border-radius:10px;padding:14px 16px;margin:12px 0}}table{{width:100%;border-collapse:collapse;font-size:13px}}
td,th{{padding:4px 6px;text-align:left;border-bottom:1px solid #8883}}small{{color:var(--mut)}}.g{{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px}}
</style></head><body>
<h1>Eevee — prop lab</h1><small>generated {s['generated']} · last snapshot {s['last_snapshot']} · {s['weeks']} weeks · {s['events']} events · {s['lines']} live lines</small>
<div class="card"><h2>Verdicts</h2><table>{vrows}</table><small>Rules fixed before week 1. Money enters only if H2 accepts and one of H1/H3/H4 accepts.</small></div>
<div class="g">
<div class="card"><h3>H3 · Hard Rock near-main</h3>n={hr.get('n',0)} · mean {fmt(hr.get('mean'))}% · median {fmt(hr.get('median'))}%<br>+EV rows {hr.get('plus',0)} · ≥+3% {hr.get('plus3',0)}</div>
<div class="card"><h3>H1 · Underdog near-main</h3>n={ud.get('n',0)} · mean {fmt(ud.get('mean'))}% · median {fmt(ud.get('median'))}%<br>+EV rows {ud.get('plus',0)} · ≥+3% {ud.get('plus3',0)}</div>
<div class="card"><h3>H2 · closing line value</h3>{h2.get('n',0)} graded legs ({h2.get('bettable',0)} at Hard Rock)<br>EV vs close {fmt(h2.get('avg_ev_vs_close'))}% · beat close {fmt(h2.get('beat_pct'),0,'%')}<br>paper {h2.get('graded',0)} settled · {fmt(h2.get('pnl_units'),2)}u · ROI {fmt(h2.get('roi'))}%</div>
<div class="card"><h3>H4 · SGP correlation</h3>{h4.get('n',0)} quoted probes<br>median factor {fmt(h4.get('median'),3) if h4.get('median') else '—'} · &lt;1: {h4.get('under1',0)} · &gt;1: {h4.get('over1',0)}<br><small>factor = book SGP price ÷ independent product; ≈1.0 means correlation is priced</small></div>
</div>
<div class="card">{svg_hist(hr.get('hist'), 'Hard Rock EV% distribution (near-main, ≥3 books)')}{svg_hist(ud.get('hist'), 'Underdog EV% distribution (near-main, ≥3 books)')}</div>
<div class="card"><h2>Recent candidates</h2><table><tr><th>ts</th><th>game</th><th>player</th><th>leg</th><th>book</th><th>price</th><th>EV</th><th>anchor</th></tr>{crow or '<tr><td colspan=8>none yet</td></tr>'}</table>
<small>{s['candidates']} distinct candidates so far · {s['bettable_candidates']} at a bettable book</small></div>
<div class="card"><small>Gates: fair 30–70% · ≥3 books · EV ≥ +3% · exchange anchors need ≥4 books. Sources: PropLine /ev, /clv/grade, /results, /sgp.</small></div>
</body></html>"""

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--telegram", action="store_true"); ap.add_argument("--kind", default="weekly")
    a = ap.parse_args()
    s = build()
    open(os.path.join(DOCS, "index.html"), "w").write(html_page(s))
    txt = text_summary(s, a.kind); print(txt)
    if a.telegram: telegram(txt)
