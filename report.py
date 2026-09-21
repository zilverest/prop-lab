"""report.py — turn the CSVs into verdicts.

  python3 report.py               -> writes docs/index.html, prints summary
  python3 report.py --telegram    -> also sends the summary to Telegram
  python3 report.py --kind board  -> short "board captured" message (Thursday)
"""
import argparse, html, json, re, statistics as st, datetime as dt
from collections import defaultdict
from common import *
import slips as _slips

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

def universe(lines):
    """The same near-main, >=3-books denominator used everywhere else — every book pooled together."""
    return [r for r in lines if fnum(r["fair_prob"]) is not None and NEAR[0] <= fnum(r["fair_prob"]) <= NEAR[1] and int(r["n_books"]) >= 3]

def extremity_bucket(fp):
    d = abs(fp - 0.5)
    if d < 0.05: return "near-coin (45-55%)"
    if d < 0.10: return "slight lean (40-45 / 55-60%)"
    return "moderate lean (35-40 / 60-65%)"

EXTREMITY_ORDER = ["near-coin (45-55%)", "slight lean (40-45 / 55-60%)", "moderate lean (35-40 / 60-65%)"]

def timing_bucket(h):
    if h >= 72: return "early week (72h+)"
    if h >= 24: return "midweek (24-72h)"
    return "close to kickoff (<24h)"

TIMING_ORDER = ["early week (72h+)", "midweek (24-72h)", "close to kickoff (<24h)"]

def slice_stats(rows, bucketer, order):
    out = []
    for label in order:
        sub = [r for r in rows if bucketer(r) == label]
        ev = [fnum(r["ev_pct"]) for r in sub]
        if not ev: out.append(dict(label=label, n=0)); continue
        out.append(dict(label=label, n=len(ev), mean=st.mean(ev), plus=sum(e > 0 for e in ev), plus3=sum(e >= 3 for e in ev)))
    return out

def bucket_slices(lines):
    u = universe(lines)
    by_extremity = slice_stats(u, lambda r: extremity_bucket(fnum(r["fair_prob"])), EXTREMITY_ORDER)
    by_timing = slice_stats(u, lambda r: timing_bucket(fnum(r["hours_to_kick"], 999)), TIMING_ORDER)
    return dict(n=len(u), by_extremity=by_extremity, by_timing=by_timing)

# ---------------------------------------------------------------- construction theories
def _construct(note):
    m = re.search(r"construct=([a-z\-]+)", note or "")
    return m.group(1) if m else "unlabelled"

def _slip_stats(rows):
    settled = [r for r in rows if r["resolution"] != "open"]
    won = sum(r["resolution"] == "won" for r in settled); lost = sum(r["resolution"] == "lost" for r in settled)
    pnl = sum(fnum(r["pnl_units"], 0.0) for r in settled)
    staked = sum(fnum(r["stake"], 0.0) for r in settled if r["resolution"] in ("won", "lost"))
    return dict(n=len(rows), open=len(rows) - len(settled), won=won, lost=lost,
                win_pct=100 * won / (won + lost) if (won + lost) else None,
                pnl=pnl, roi=100 * pnl / staked if staked else None)

def construction_report():
    slips = read_rows("slips")
    straights = _slip_stats([r for r in slips if r["kind"] == "straight"])
    r_s = (straights["roi"] or 0.0) / 100.0
    parlays = [r for r in slips if r["kind"] == "parlay"]
    by_construct = {}
    for c in ("anchor-pure", "ev-ranked", "unlabelled"):
        sub = [r for r in parlays if _construct(r["note"]) == c]
        if sub: by_construct[c] = _slip_stats(sub)
    by_legs = {}
    for n in (2, 3):
        sub = [r for r in parlays if len(json.loads(r["legs"])) == n]
        st_ = _slip_stats(sub); st_["predicted_roi"] = 100 * ((1 + r_s) ** n - 1)   # if legs carry the straights' ROI independently
        by_legs[n] = st_
    sgps = [r for r in slips if r["kind"] == "sgp"]
    sgp_by = {}
    for c in ("stack", "stranger", "unlabelled"):
        sub = [r for r in sgps if _construct(r["note"]) == c]
        if not sub: continue
        f = [fnum(r["correlation_factor"]) for r in sub if fnum(r["correlation_factor"]) is not None]
        d = _slip_stats(sub); d["median_factor"] = st.median(f) if f else None; d["n_factor"] = len(f)
        sgp_by[c] = d
    return dict(straights_roi=straights["roi"], parlay_by_construct=by_construct, parlay_by_legs=by_legs, sgp_by_construct=sgp_by)


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
                recent_candidates=sorted(cands, key=lambda c: c["ts"])[-15:][::-1],
                ledger=_slips.ledger_summary(),
                slices=bucket_slices(lines),
                constructions=construction_report(),
                top_conviction=ranked_live(public_build()["live"])[:15],
                recent_slips=read_rows("slips")[-15:][::-1])

def fmt(x, d=1, suf=""):
    return "—" if x is None else f"{x:+.{d}f}{suf}" if isinstance(x, float) else str(x)

def pct(x):
    return "—" if x is None else f"{x:.0f}%"

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
    cn = s.get("constructions", {})
    sb = cn.get("sgp_by_construct", {})
    if sb:
        L.append("SGP factor: " + " · ".join(f"{k} {fmt(v.get('median_factor'),3)} (n={v['n']})" for k, v in sb.items() if v.get('median_factor') is not None))
    pb = cn.get("parlay_by_construct", {})
    if pb:
        L.append("Parlay ROI: " + " · ".join(f"{k} {fmt(v.get('roi'))}% (n={v['n']})" for k, v in pb.items()))
    lg = s.get("ledger", {})
    if lg.get("n"):
        L.append(f"Slip ledger (${lg['stake_usd']:.0f} each): {lg['n']} logged · {lg['open']} open · "
                 f"{lg['won']}-{lg['lost']} ({pct(lg.get('win_pct'))} W/L) · ${lg.get('pnl_units',0):+.2f} · ROI {fmt(lg.get('roi'))}%")
        for k in ("straight", "parlay", "sgp"):
            b = lg["by_kind"][k]
            if b["n"]:
                L.append(f"  {k:8} {b['n']:>3} · {b['won']}-{b['lost']} ({pct(b.get('win_pct'))}) · ${b['pnl']:+.2f} · ROI {fmt(b.get('roi'))}%")
    return "\n".join(L)

def svg_hist(h, title):
    if not h: return ""
    mx = max(c for _, c in h) or 1; w = 20; W = w * len(h) + 40; H = 120
    bars = "".join(f'<rect x="{30+i*w}" y="{100-90*c/mx:.1f}" width="{w-2}" height="{90*c/mx:.1f}" fill="{"#c0504d" if x<0 else "#4f9d69"}"/>'
                   for i, (x, c) in enumerate(h))
    ticks = "".join(f'<text x="{30+i*w+w/2}" y="114" font-size="8" text-anchor="middle" fill="#888">{x}</text>' for i, (x, _) in enumerate(h) if x % 5 == 0)
    return f'<h3>{title}</h3><svg viewBox="0 0 {W} {H}" width="100%" style="max-width:640px">{bars}{ticks}<line x1="{30+15*w}" y1="0" x2="{30+15*w}" y2="102" stroke="#999" stroke-dasharray="3"/></svg>'

def html_page(s):
    hr, ud, h2, h4, lg = s["hr"], s["ud"], s["h2"], s["h4"], s.get("ledger", {})
    vrows = "".join(f"<tr><td>{k}</td><td><b>{v}</b></td></tr>" for k, v in s["verdicts"].items())
    srow = "".join(f"<tr><td>{r['ts'][:16]}</td><td>{r['kind']}</td><td>{r['book']}</td><td>{r['price']}</td>"
                   f"<td>{html.escape(' + '.join(l['player'] for l in json.loads(r['legs'])))}</td>"
                   f"<td>{r['resolution']}</td><td>{('$'+format(float(r['pnl_units']),'+.2f')) if r['pnl_units'] not in ('', None) else ''}</td></tr>" for r in s.get("recent_slips", []))
    def kind_row(k):
        b = lg.get("by_kind", {}).get(k)
        if not b or not b["n"]: return f"<tr><td>{k}</td><td colspan=5><small>none yet</small></td></tr>"
        return (f"<tr><td>{k}</td><td>{b['n']}</td><td>{b['open']}</td><td>{b['won']}-{b['lost']}</td>"
                f"<td>{pct(b.get('win_pct'))}</td><td>${b['pnl']:+.2f} · ROI {fmt(b.get('roi'))}%</td></tr>")
    krows = "".join(kind_row(k) for k in ("straight", "parlay", "sgp"))
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
<div class="g">
<div class="card"><h3>By odds extremity</h3><small>near-main universe, all books pooled, n={s['slices']['n']}</small>
<table><tr><th>bucket</th><th>n</th><th>mean EV</th><th>+EV</th><th>≥+3%</th></tr>{"".join(f"<tr><td>{b['label']}</td><td>{b['n']}</td><td>{fmt(b.get('mean'))}%</td><td>{b.get('plus','—')}</td><td>{b.get('plus3','—')}</td></tr>" for b in s['slices']['by_extremity'])}</table>
<small>Tests the favorite-longshot bias: literature says slight leans hold up best, extreme edges are usually devig artifacts.</small></div>
<div class="card"><h3>By time to kickoff</h3><small>same universe, n={s['slices']['n']}</small>
<table><tr><th>bucket</th><th>n</th><th>mean EV</th><th>+EV</th><th>≥+3%</th></tr>{"".join(f"<tr><td>{b['label']}</td><td>{b['n']}</td><td>{fmt(b.get('mean'))}%</td><td>{b.get('plus','—')}</td><td>{b.get('plus3','—')}</td></tr>" for b in s['slices']['by_timing'])}</table>
<small>Tests whether early lines lag real-world news more than lines set close to kickoff.</small></div>
</div>
<div class="card"><h2>Slip ledger</h2>
{f"{lg['n']} logged · {lg['open']} open · {lg['won']}-{lg['lost']} <b>({pct(lg.get('win_pct'))} W/L)</b> · staked ${lg.get('staked_usd',0):.0f} · <b>{'$'+format(lg.get('pnl_units',0),'+.2f')}</b> · ROI {fmt(lg.get('roi'))}%" if lg.get('n') else "none logged yet — auto-builds every tick from gated candidates"}
<table><tr><th>kind</th><th>logged</th><th>open</th><th>W-L</th><th>W/L%</th><th>P&amp;L</th></tr>{krows}</table>
<small>${lg.get('stake_usd', 5):.0f} flat per slip, paper only. <b>straight</b> = every gated candidate. <b>parlay</b> = same-book, cross-game, EV-ranked pairs + one 3-leg, priced as the independent product. <b>sgp</b> = per game, two best legs, at FanDuel/DraftKings' own correlated price (logged only if the book quotes it). Settles each tick once every leg is graded. W/L% excludes pushes.</small>
<h3>Recent slips</h3>
<table><tr><th>ts</th><th>kind</th><th>book</th><th>price</th><th>legs</th><th>result</th><th>pnl</th></tr>{srow or '<tr><td colspan=7>none yet</td></tr>'}</table></div>
<div class="card"><h2>Construction theories</h2>
<div class="g">
<div><h3>Parlays by rule</h3><table><tr><th>rule</th><th>n</th><th>W-L</th><th>W/L%</th><th>ROI</th></tr>
{"".join(f"<tr><td>{k}</td><td>{v['n']}</td><td>{v['won']}-{v['lost']}</td><td>{pct(v.get('win_pct'))}</td><td>{fmt(v.get('roi'))}%</td></tr>" for k, v in s['constructions']['parlay_by_construct'].items()) or '<tr><td colspan=5><small>none yet</small></td></tr>'}</table>
<small>anchor-pure = Pinnacle/Bovada anchor and ≥{PARLAY_PURE_MIN_BOOKS} books per leg; ev-ranked = original rule. Theory: less-noisy legs compound less error.</small></div>
<div><h3>Parlays by leg count</h3><table><tr><th>legs</th><th>n</th><th>W-L</th><th>realized ROI</th><th>predicted*</th></tr>
{"".join(f"<tr><td>{k}</td><td>{v['n']}</td><td>{v['won']}-{v['lost']}</td><td>{fmt(v.get('roi'))}%</td><td>{fmt(v.get('predicted_roi'))}%</td></tr>" for k, v in s['constructions']['parlay_by_legs'].items())}</table>
<small>*if each leg carried the straights' realized ROI ({fmt(s['constructions']['straights_roi'])}%) independently: (1+r)^n − 1. Realized well below predicted ⇒ extra parlay hold.</small></div>
<div><h3>SGP by construction</h3><table><tr><th>type</th><th>n</th><th>median factor</th><th>W-L</th><th>ROI</th></tr>
{"".join(f"<tr><td>{k}</td><td>{v['n']}</td><td>{fmt(v.get('median_factor'),3) if v.get('median_factor') is not None else '—'}</td><td>{v['won']}-{v['lost']}</td><td>{fmt(v.get('roi'))}%</td></tr>" for k, v in s['constructions']['sgp_by_construct'].items()) or '<tr><td colspan=5><small>none yet</small></td></tr>'}</table>
<small>stack = passer + pass-catcher, same direction (heuristic, no team data); stranger = unrelated legs. factor = book SGP price ÷ independent product. Stack factor well below stranger factor ⇒ the book is discounting correlation.</small></div>
</div></div>
<div class="card"><h2>Top conviction (open straights)</h2>
<table><tr><th>score</th><th>leg</th><th>book</th><th>price</th><th>kickoff</th><th>ev</th><th>anchor</th><th>depth</th><th>seen</th><th>coin</th><th>combo</th></tr>
{"".join(f"<tr><td><b>{y['score']:.1f}</b></td><td>{html.escape(leg_text(y['legs_parsed'][0]))}</td><td>{y['book']}{' <b>HR</b>' if y['book'] in BETTABLE else ''}</td><td>{int(y['price']):+d}</td><td>{y['kickoff'][:16] if y['kickoff'] else '—'}</td><td>{y['parts']['ev']:+.1f}</td><td>{y['parts']['anchor']:+.0f}</td><td>{y['parts']['depth']:+.2f}</td><td>×{int(y['parts']['persist']/0.5)+1}</td><td>{y['parts']['coin']:+.1f}</td><td>{y['parts']['combo']:+.0f}</td></tr>" for y in s.get('top_conviction', []))}</table>
<small>score = ev% + anchor(+1 Pinnacle/Bovada) + depth(+0.25/book over 3, cap 1) + persistence(+0.5/extra snapshot, cap 1.5) + near-coin(+0.5 if 45–55%) − combo(1). Game-day Telegram sends the top {TOP_N} in the 12h window.</small></div>
<div class="card"><h2>Recent candidates</h2><table><tr><th>ts</th><th>game</th><th>player</th><th>leg</th><th>book</th><th>price</th><th>EV</th><th>anchor</th></tr>{crow or '<tr><td colspan=8>none yet</td></tr>'}</table>
<small>{s['candidates']} distinct candidates so far · {s['bettable_candidates']} at a bettable book</small></div>
<div class="card"><small>Gates: fair 30–70% · ≥3 books · EV ≥ +3% · exchange anchors need ≥4 books. Sources: PropLine /ev, /clv/grade, /results, /sgp.</small></div>
</body></html>"""

# ---------------------------------------------------------------- public page
MARKET_LABEL = {"player_pass_yds": "pass yds", "player_rush_yds": "rush yds", "player_reception_yds": "rec yds",
                "player_receptions": "receptions", "player_pass_tds": "pass TD", "player_pass_attempts": "pass att",
                "player_pass_completions": "completions", "player_rush_attempts": "rush att",
                "player_pass_rush_yds": "pass+rush yds", "player_reception_longest": "longest rec",
                "player_longest_completion": "longest comp", "player_anytime_td": "anytime TD", "player_1st_td": "first TD",
                "player_kicking_points": "kicking pts", "player_field_goals_made": "FGs made", "player_pass_interceptions": "INTs"}
BOOK_LABEL = {"hardrock": "Hard Rock", "draftkings": "DraftKings", "fanduel": "FanDuel", "kalshi": "Kalshi",
              "underdog": "Underdog", "pinnacle": "Pinnacle", "bovada": "Bovada", "fanatics": "Fanatics"}

def leg_text(l):
    m = MARKET_LABEL.get(l["market"], l["market"].replace("player_", "").replace("_", " "))
    pt = f" {l['point']}" if l.get("point") not in ("", None) else ""
    return f"{l['player']} {l['side']}{pt} {m}"

def checked_stats():
    """Total near-main props actually checked (>=3 books) across every tracked book, and the
    clearance rate against that denominator — the number that answers 'is 8 out of how many?'"""
    lines = latest_per_line(read_rows("lines"))
    checked = [r for r in lines if fnum(r["fair_prob"]) is not None and NEAR[0] <= fnum(r["fair_prob"]) <= NEAR[1] and int(r["n_books"]) >= 3]
    cands = read_rows("candidates")
    distinct_c = {(c["event_id"], c["market"], c["player"], c["point"], c["side"], c["book"]) for c in cands}
    return dict(checked=len(checked), cleared=len(distinct_c),
                rate=100 * len(distinct_c) / len(checked) if checked else None)

def public_build():
    slips = read_rows("slips")
    settled = [s for s in slips if s["resolution"] != "open" and s["settled_ts"]]
    settled.sort(key=lambda s: s["settled_ts"])
    cum, series = 0.0, []
    for s in settled:
        cum += fnum(s["pnl_units"], 0.0); series.append((s["settled_ts"][:10], cum))
    weeks = {}
    for s in settled:
        wk = parse_iso(s["settled_ts"]).strftime("%G-W%V")
        w = weeks.setdefault(wk, dict(week=wk, n=0, won=0, lost=0, pnl=0.0))
        w["n"] += 1; w["won"] += s["resolution"] == "won"; w["lost"] += s["resolution"] == "lost"; w["pnl"] += fnum(s["pnl_units"], 0.0)
    kick = {e["event_id"]: e["commence_time"] for e in read_rows("events")}
    live = []
    for sl in slips:
        if sl["resolution"] != "open": continue
        legs = json.loads(sl["legs"])
        ks = [kick.get(l.get("event_id", sl["event_id"])) for l in legs]
        ks = [k for k in ks if k]
        live.append(dict(sl, legs_parsed=legs, kickoff=min(ks) if ks else "", started=bool(ks) and parse_iso(min(ks)) <= utcnow()))
    live.sort(key=lambda x: (x["kickoff"] or "9", x["ts"]))
    by_kind = {}
    for k in ("straight", "parlay", "sgp"):
        rows_k = [dict(x, _open=True) for x in live if x["kind"] == k]
        rows_k += [dict(x, _open=False) for x in settled[::-1] if x["kind"] == k][:25]
        by_kind[k] = rows_k[:30]
    return dict(generated=iso(), ledger=_slips.ledger_summary(), settled=settled[::-1][:40], series=series, live=live,
                by_kind_rows=by_kind, top_picks=ranked_live(live)[:TOP_N],
                checked=checked_stats(),
                weeks=sorted(weeks.values(), key=lambda w: w["week"], reverse=True),
                first_settled=settled[0]["settled_ts"][:10] if settled else None)

def conviction(slip, cand_counts, cands_by_key):
    """Score a straight slip using the canonical slips.candidate_score, so the auto-log filter and
    every displayed ranking always agree. Returns (score, parts) or None for non-straights."""
    if slip["kind"] != "straight": return None
    leg = slip["legs_parsed"][0]
    key = (leg.get("event_id", slip["event_id"]), leg["market"], leg["player"], str(leg["point"]), leg["side"], slip["book"])
    c = cands_by_key.get(key)
    if c is None:                                    # candidate row aged out of candidates.csv; score from what the slip itself stored
        c = dict(market=leg["market"], ev_pct=slip.get("ev_pct_at_bet") or 0, fair_prob=slip.get("fair_prob_at_bet") or 0.5,
                n_books=3, fair_source="")
    return _slips.candidate_score(c, cand_counts.get(key, 1))

def ranked_live(live):
    """Attach conviction to every open straight; returns list sorted best-first."""
    cands = read_rows("candidates")
    counts, by_key = {}, {}
    for c in cands:
        k = (c["event_id"], c["market"], c["player"], str(c["point"]), c["side"], c["book"])
        counts[k] = counts.get(k, 0) + 1; by_key[k] = c        # last observation wins for fields
    out = []
    for x in live:
        r = conviction(x, counts, by_key)
        if r is None: continue
        y = dict(x); y["score"], y["parts"] = r; out.append(y)
    return sorted(out, key=lambda y: -y["score"])

def live_text(hours=12):
    """Game-day Telegram: the TOP_N highest-conviction straights kicking off within `hours`.
    Everything else stays on the dashboard. Returns None if nothing is in the window."""
    p = public_build(); now = utcnow()
    soon = [x for x in p["live"] if x["kickoff"] and 0 <= (parse_iso(x["kickoff"]) - now).total_seconds() <= hours * 3600]
    if not soon: return None
    ranked = ranked_live(soon)
    top = ranked[:TOP_N]
    lg = p["ledger"]
    L = [f"Eevee — game day · top {len(top)} of {len(soon)} live ($5 paper each)"]
    L.append("ranked by edge + anchor + depth + persistence; not a win prediction")
    for i, x in enumerate(top, 1):
        t = parse_iso(x["kickoff"]).astimezone(dt.timezone(dt.timedelta(hours=-4))).strftime("%a %-I:%M%p")
        hr = " · HR" if x["book"] in BETTABLE else ""
        pr = x["parts"]
        L.append(f"\n{i}. [{x['score']:.1f}] {leg_text(x['legs_parsed'][0])}")
        L.append(f"   {BOOK_LABEL.get(x['book'], x['book'])} {int(x['price']):+d}{hr} · {t}")
        L.append(f"   ev {pr['ev']:+.1f} · anchor {pr['anchor']:+.0f} · depth {pr['depth']:+.2f} · seen×{int(pr['persist']/0.5)+1} · coin {pr['coin']:+.1f}{' · combo -1' if pr['combo'] else ''}")
    rest = len(soon) - len(top)
    if rest > 0: L.append(f"\n+{rest} more (incl. parlays/SGPs) on the dashboard")
    L.append(f"Record {lg.get('won',0)}–{lg.get('lost',0)} · ${lg.get('pnl_units',0):+.2f} · ROI {fmt(lg.get('roi'))}%")
    return "\n".join(L)

def record_text():
    """Telegram text: record, P&L, ROI by kind + all live slips."""
    p = public_build(); lg = p["ledger"]
    if not lg.get("n"): return "Eevee — no slips logged yet."
    L = [f"Eevee — record", f"{lg['won']}–{lg['lost']} ({pct(lg.get('win_pct'))}) · ${lg['pnl_units']:+.2f} on ${lg['staked_usd']:.0f} · ROI {fmt(lg.get('roi'))}%"]
    for k, name in (("straight", "Straights"), ("parlay", "Parlays"), ("sgp", "SGPs")):
        b = lg["by_kind"][k]
        if b["n"]: L.append(f"  {name}: {b['won']}–{b['lost']} ({pct(b.get('win_pct'))}) · ${b['pnl']:+.2f} · ROI {fmt(b.get('roi'))}% · {b['open']} open")
    if p["live"]:
        L.append(f"\nLive ({len(p['live'])}):")
        for x in p["live"][:25]:
            t = parse_iso(x["kickoff"]).astimezone(dt.timezone(dt.timedelta(hours=-4))).strftime("%a %-I%p") if x["kickoff"] else "—"
            L.append(f"  {t} {x['kind'][:3].upper()} {BOOK_LABEL.get(x['book'], x['book'])} {int(x['price']):+d} · " + " + ".join(leg_text(l) for l in x["legs_parsed"]))
        if len(p["live"]) > 25: L.append(f"  …and {len(p['live']) - 25} more")
    return "\n".join(L)

def svg_cum(series):
    if len(series) < 2: return '<div class="mut">Cumulative P&amp;L chart appears after the first few slips settle.</div>'
    W, H, pad = 640, 160, 28
    ys = [y for _, y in series]; lo, hi = min(0, min(ys)), max(0, max(ys)); hi = hi if hi > lo else lo + 1
    xs = [pad + (W - 2 * pad) * i / (len(series) - 1) for i in range(len(series))]
    yy = [H - pad - (H - 2 * pad) * (y - lo) / (hi - lo) for y in ys]
    zero = H - pad - (H - 2 * pad) * (0 - lo) / (hi - lo)
    path = " ".join(f"{'M' if i == 0 else 'L'}{x:.1f},{y:.1f}" for i, (x, y) in enumerate(zip(xs, yy)))
    col = "#4f9d69" if ys[-1] >= 0 else "#c0504d"
    return (f'<svg viewBox="0 0 {W} {H}" width="100%" style="max-width:{W}px">'
            f'<line x1="{pad}" y1="{zero:.1f}" x2="{W-pad}" y2="{zero:.1f}" stroke="#8886" stroke-dasharray="4"/>'
            f'<path d="{path}" fill="none" stroke="{col}" stroke-width="2.5"/>'
            f'<text x="{pad}" y="14" font-size="11" fill="#888">{series[0][0]}</text>'
            f'<text x="{W-pad}" y="14" font-size="11" fill="#888" text-anchor="end">{series[-1][0]} · ${ys[-1]:+.2f}</text></svg>')

def public_page(p):
    lg = p["ledger"]; bk = lg.get("by_kind", {})
    def stat(label, val, sub=""):
        return f'<div class="stat"><div class="v">{val}</div><div class="l">{label}</div>{f"<div class=mut>{sub}</div>" if sub else ""}</div>'
    hero = "".join([
        stat("record", f"{lg.get('won',0)}–{lg.get('lost',0)}", f"{pct(lg.get('win_pct'))} win rate"),
        stat("paper P&L", f"${lg.get('pnl_units',0):+.2f}", f"on ${lg.get('staked_usd',0):.0f} staked"),
        stat("ROI", fmt(lg.get('roi'), 1, '%'), f"${lg.get('stake_usd',5):.0f} flat per slip"),
        stat("slips settled", str(lg.get('settled',0)), f"{lg.get('open',0)} pending"),
    ]) if lg.get("n") else '<div class="mut">No slips have settled yet — the first results land after this weekend\'s games.</div>'
    def kick_label(k, started):
        if not k: return "—"
        t = parse_iso(k).astimezone(dt.timezone(dt.timedelta(hours=-4)))       # ET (EDT); NFL season is EDT until early Nov
        lab = t.strftime("%a %-I:%M %p ET")
        return f'{lab} <span class="mut">(in progress)</span>' if started else lab
    def slip_row(x):
        legs = x.get("legs_parsed") or json.loads(x["legs"])
        head = (f'<tr><td>{kick_label(x["kickoff"], x.get("started")) if x.get("_open") else x["settled_ts"][:10]}</td>'
                f'<td>{BOOK_LABEL.get(x["book"], x["book"])}</td>'
                f'<td>{html.escape("  +  ".join(leg_text(l) for l in legs))}</td><td>{int(x["price"]):+d}</td>')
        if x.get("_open"): return head + '<td class="mut">pending</td><td></td></tr>'
        return head + f'<td class="{x["resolution"]}">{x["resolution"].replace("push_adj","push")}</td><td>${fnum(x["pnl_units"],0):+.2f}</td></tr>'
    def kcard(k, title, desc):
        b = bk.get(k, {})
        rows_k = p["by_kind_rows"].get(k, [])
        summary = (f'<div class="row"><b>{b["won"]}–{b["lost"]}</b><span>{pct(b.get("win_pct"))}</span>'
                   f'<span>${b["pnl"]:+.2f}</span><span>ROI {fmt(b.get("roi"))}%</span><span class="mut">{b["open"]} pending</span></div>') if b.get("n") else '<div class="mut">none yet</div>'
        table = ('<table><tr><th>when</th><th>book</th><th>legs</th><th>price</th><th>result</th><th>P&amp;L</th></tr>'
                 + "".join(slip_row(x) for x in rows_k) + '</table>') if rows_k else '<div class="mut">none yet</div>'
        return (f'<div class="card"><h3>{title}</h3><div class="mut">{desc}</div>{summary}'
                f'<details style="margin-top:8px"><summary><span class="mut">show slips ({len(rows_k)})</span></summary>'
                f'<div class="wrap" style="margin-top:8px">{table}</div></details></div>')
    kinds = kcard("straight", "Straights", "one player prop, one book") + \
            kcard("parlay", "Parlays", "2–3 legs across different games, same book") + \
            kcard("sgp", "Same-game parlays", "2 legs, one game, at the book's own correlated price")
    top = p.get("top_picks", [])
    toprows = "".join(
        f'<tr><td><b>{y["score"]:.1f}</b></td><td>{html.escape(leg_text(y["legs_parsed"][0]))}</td>'
        f'<td>{BOOK_LABEL.get(y["book"], y["book"])}{" <b>HR</b>" if y["book"] in BETTABLE else ""}</td>'
        f'<td>{int(y["price"]):+d}</td><td>{kick_label(y["kickoff"], y.get("started"))}</td></tr>' for y in top)
    topcard = ('<h2>Top picks <span class="mut" style="font-weight:400;font-size:14px">'
               '\u00b7 highest-scored open straights</span></h2>'
               '<div class="card wrap"><table><tr><th>score</th><th>leg</th><th>book</th><th>price</th><th>kickoff</th></tr>'
               + (toprows or '<tr><td colspan=5 class=mut>none open right now</td></tr>') + '</table>'
               '<div class="mut" style="margin-top:8px">Score = edge size + trusted-book bonus + coverage depth '
               '+ how many snapshots it survived + near-coinflip bonus, minus a penalty for combo stat lines. '
               'Ranks confidence in the <i>finding</i>, not a prediction it wins. Everything below is the full, unfiltered log.</div></div>')
    rows = "".join(
        f'<tr><td>{s["settled_ts"][:10]}</td><td>{s["kind"]}</td><td>{BOOK_LABEL.get(s["book"], s["book"])}</td>'
        f'<td>{html.escape("  +  ".join(leg_text(l) for l in json.loads(s["legs"])))}</td>'
        f'<td>{int(s["price"]):+d}</td><td class="{s["resolution"]}">{s["resolution"].replace("push_adj","push")}</td>'
        f'<td>${fnum(s["pnl_units"],0):+.2f}</td></tr>' for s in p["settled"])
    wrows = "".join(f'<tr><td>{w["week"]}</td><td>{w["n"]}</td><td>{w["won"]}–{w["lost"]}</td><td>${w["pnl"]:+.2f}</td></tr>' for w in p["weeks"])
    lrows = "".join(
        f'<tr><td>{kick_label(x["kickoff"], x["started"])}</td><td>{x["kind"]}</td><td>{BOOK_LABEL.get(x["book"], x["book"])}</td>'
        f'<td>{html.escape("  +  ".join(leg_text(l) for l in x["legs_parsed"]))}</td><td>{int(x["price"]):+d}</td></tr>' for x in p["live"])
    n_live = len(p["live"])
    ck = p.get("checked", {})
    howworks = f"""<h2>How it works</h2><div class="card">
<p>Every few hours, the system checks player-prop lines across ~15 sportsbooks and exchanges (DraftKings, FanDuel, Hard Rock, Kalshi, Polymarket, and others). For each prop it strips out the house's cut to get a no-vig "fair" probability, then averages that across every book pricing it — that's the market consensus.</p>
<p>A prop only becomes a candidate if it clears three checks: <b>at least 3 books</b> are pricing the exact same line, the fair probability sits in a <b>normal 30–70% range</b> (extreme longshot lines produce math artifacts, not real edges, so they're excluded entirely), and the gap between one book's price and the consensus is <b>at least 3%</b> — big enough to not be rounding noise.</p>
<div class="row" style="margin:10px 0"><b>{ck.get('checked',0):,}</b><span class="mut">near-main props checked this way</span><b>{ck.get('cleared',0)}</b><span class="mut">cleared all three checks</span><b>{f"{ck['rate']:.2f}%" if ck.get('rate') is not None else "—"}</b><span class="mut">clearance rate</span></div>
<p class="mut">One cleared prop can become more than one slip below — a straight bet, and it may also feed a cross-game parlay or a same-game parlay — so the slip counts above are not a count of distinct edges found. The clearance rate is the number that actually says how rare a real disagreement is. A low, stable rate over the season is the expected, honest outcome — it would mean these markets are efficient, which is more likely true than not.</p>
<p class="mut">Passing these checks doesn't prove a bet is right — it just means it's worth tracking. The real test is <b>closing line value</b>: does the market move toward our number before kickoff? That's measured separately and isn't shown on this page, but it's what ultimately decides whether any of this is signal.</p>
</div>
"""
    return f"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Eevee · paper prop ledger</title><style>
:root{{--bg:#fff;--fg:#1a1a1a;--mut:#6b6b6b;--card:#f5f5f4;--line:#e5e5e3}}
@media(prefers-color-scheme:dark){{:root{{--bg:#101010;--fg:#ececec;--mut:#9a9a9a;--card:#1a1a1a;--line:#2a2a2a}}}}
body{{font:16px/1.55 system-ui,-apple-system,sans-serif;background:var(--bg);color:var(--fg);max-width:880px;margin:0 auto;padding:20px 16px 48px}}
h1{{font-size:26px;margin:8px 0 4px}}h2{{font-size:18px;margin:28px 0 10px}}h3{{font-size:15px;margin:0 0 4px}}
.mut{{color:var(--mut);font-size:13.5px}}.card{{background:var(--card);border-radius:12px;padding:14px 16px}}
.hero{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin:14px 0}}
.stat{{background:var(--card);border-radius:12px;padding:14px}}.stat .v{{font-size:26px;font-weight:650;letter-spacing:-.01em}}.stat .l{{font-size:12px;text-transform:uppercase;letter-spacing:.06em;color:var(--mut)}}
.g{{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:10px}}.row{{display:flex;gap:14px;flex-wrap:wrap;margin-top:8px;align-items:baseline}}
table{{width:100%;border-collapse:collapse;font-size:13.5px}}td,th{{padding:7px 6px;text-align:left;border-bottom:1px solid var(--line);vertical-align:top}}th{{color:var(--mut);font-weight:500;font-size:12px;text-transform:uppercase;letter-spacing:.05em}}
td.won{{color:#3d8b5a;font-weight:600}}td.lost{{color:#b5453f;font-weight:600}}.wrap{{overflow-x:auto}}
footer{{margin-top:36px;padding-top:14px;border-top:1px solid var(--line)}}
details>summary{{cursor:pointer;list-style:none;display:flex;gap:8px;align-items:baseline}}details>summary::-webkit-details-marker{{display:none}}
details>summary::before{{content:"▸";color:var(--mut);font-size:14px}}details[open]>summary::before{{content:"▾"}}
</style></head><body>
<h1>Eevee · paper prop ledger</h1>
<div class="mut">Every slip here is built by a fixed rule set and settled against the box score. $5 flat, paper only, nothing is placed. Updated {p['generated'][:16]}Z{f" · tracking since {p['first_settled']}" if p['first_settled'] else ""}.</div>
<div class="hero">{hero}</div>
{howworks}
{topcard}
<h2>By slip type</h2><div class="g">{kinds}</div>
<h2>Cumulative P&amp;L</h2><div class="card">{svg_cum(p['series'])}</div>
<details class="card" style="margin-top:14px" open><summary><h2 style="display:inline;margin:0">Live slips</h2> <span class="mut">· {n_live} pending · tap to collapse</span></summary>
<div class="wrap" style="margin-top:12px"><table><tr><th>kickoff</th><th>type</th><th>book</th><th>legs</th><th>price</th></tr>{lrows or '<tr><td colspan=5 class=mut>nothing pending — new slips appear as the week\'s board is captured</td></tr>'}</table>
<div class="mut" style="margin-top:8px">Auto-generated by the rule set, $5 paper each. Settles into the table below when the game ends.</div></div></details>
<details class="card" style="margin-top:14px"><summary><h2 style="display:inline;margin:0">Settled slips</h2> <span class="mut">· last 40 · tap to expand</span></summary>
<div class="wrap" style="margin-top:12px"><table><tr><th>settled</th><th>type</th><th>book</th><th>legs</th><th>price</th><th>result</th><th>P&amp;L</th></tr>{rows or '<tr><td colspan=7 class=mut>none yet</td></tr>'}</table></div></details>
<h2>Week by week</h2><div class="card wrap"><table><tr><th>week</th><th>settled</th><th>W–L</th><th>P&amp;L</th></tr>{wrows or '<tr><td colspan=4 class=mut>none yet</td></tr>'}</table></div>
<footer class="mut">What this is: a season-long paper experiment on NFL player props. Slips are generated automatically from a pre-committed rule set — the rules don't change mid-season, and every slip is logged whether it wins or loses. Prices are from PropLine. This page is a record, not advice; nothing here is a recommendation to bet.</footer>
</body></html>"""

def write_pages():
    s = build(); p = public_build()
    open(os.path.join(DOCS, "index.html"), "w").write(public_page(p))
    open(os.path.join(DOCS, "internal.html"), "w").write(html_page(s))
    return s

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--telegram", action="store_true"); ap.add_argument("--kind", default="weekly")
    a = ap.parse_args()
    s = write_pages()
    txt = text_summary(s, a.kind); print(txt)
    if a.telegram: telegram(txt)
