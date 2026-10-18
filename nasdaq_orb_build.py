"""The Trading page's "Nasdaq open breakout (paper)" section (nasdaq_orb.py). Never breaks the page."""
import html as _h

import nasdaq_orb as N

SECTION_ID = "nasdaq-orb"


def esc(x):
    return _h.escape(str(x))


def _f(x, unit="bp", sign=True):
    if x is None:
        return "—"
    return f"{x:+.1f}{unit}" if sign else f"{x:.1f}{unit}"


def section(state=None):
    state = N.load() if state is None else state
    summ = N.summary(state)
    rows = []
    for k, s in summ.items():
        need = max(0, N.REVIEW_AT - s["days"])
        win = "—" if s["win"] is None else f"{s['win'] * 100:.0f}%"
        t = "—" if s["t"] is None else f"{s['t']:+.2f}"
        review = "review due" if not need else f"{need} more day" + ("s" if need != 1 else "")
        rows.append(f'<tr><td><b>{esc(k)}</b></td><td>{esc(s["label"])}</td>'
                    f'<td class="num">{s["days"]}</td><td class="num">{s["trades"]}</td>'
                    f'<td class="num">{win}</td>'
                    f'<td class="num">{_f(s["gross"])}</td><td class="num">{_f(s["net"])}</td>'
                    f'<td class="num">{_f(s["spread"], sign=False)}</td>'
                    f'<td class="num">{t}</td><td class="sm mut">{review}</td></tr>')
    days = []
    for r in sorted(state.get("rows") or [], key=lambda r: (r["day"], r["variant"]), reverse=True)[:60]:
        st = {"settled": "settled", "no_break": "no break", "skipped": "skipped", "open": "open",
              "no_data": "no data"}.get(r["status"], r["status"])
        quote = ("—" if r.get("bid_in") is None else
                 f'{r["bid_in"]:.2f}/{r["ask_in"]:.2f} → {r["bid_out"]:.2f}/{r["ask_out"]:.2f}'
                 if r.get("bid_out") is not None else f'{r["bid_in"]:.2f}/{r["ask_in"]:.2f} → —')
        ent = (r.get("entry_min") or "") + (f" @ {r['entry']:.2f}" if r.get("entry") else "")
        ext = (r.get("exit_min") or "") + (f" @ {r['exit']:.2f}" if r.get("exit") else "")
        rng = (f'{r["range_lo"]:.2f}–{r["range_hi"]:.2f}' if r.get("range_hi") is not None else "—")
        days.append(f'<tr><td>{esc(r["day"])}</td><td><b>{esc(r["variant"])}</b></td><td>{esc(rng)}</td>'
                    f'<td>{esc(r.get("side") or "")}</td><td>{esc(r.get("signal_min") or "")}</td>'
                    f'<td>{esc(ent)}</td><td>{esc(ext)}</td>'
                    f'<td class="num">{_f(r.get("gross_bp"))}</td><td>{esc(quote)}</td>'
                    f'<td class="num">{_f(r.get("net_bp"))}</td>'
                    f'<td>{esc(st + (" · " + r["note"] if r.get("note") and r["status"] != "settled" else ""))}</td></tr>')
    body = "".join(days) or ('<tr><td colspan="11" class="mut">No days yet: the first session read is '
                             'Monday 2026-10-19, 9:20–11:50 ET.</td></tr>')
    feeds = sorted({r.get("quote_feed") for r in state.get("rows") or [] if r.get("quote_feed")})
    feed_note = ("IEX top of book" if feeds in ([], ["iex"]) else " / ".join(f.upper() for f in feeds))
    return f"""<section id="{SECTION_ID}">
<h2>Nasdaq open breakout (paper)</h2>
<p class="sm">Paper · never places an order · not in Production. QQQ opening-range breakout, four
pre-registered variants, one row each per trading day, no stop, one position. Reviewed at
{N.REVIEW_AT}+ settled days per variant.</p>
<div class="tbl"><table><thead><tr><th>Variant</th><th>Rule</th><th class="num">Days</th><th class="num">Trades</th>
<th class="num">Win</th><th class="num">Avg gross</th><th class="num">Avg net</th><th class="num">Avg spread</th>
<th class="num">t</th><th>Review</th></tr></thead><tbody>{"".join(rows)}</tbody></table></div>
<details class="fold"><summary>Daily rows</summary>
<div class="tbl"><table><thead><tr><th>Day</th><th>Variant</th><th>Range</th><th>Side</th><th>Signal</th>
<th>Entry</th><th>Exit</th><th class="num">Gross</th><th>Bid/ask in → out</th><th class="num">Net</th><th>Status</th></tr></thead>
<tbody>{body}</tbody></table></div></details>
<details class="fold trade-method"><summary>How the record is kept</summary>
<div class="note sm">The range is the high and low of the 1-minute bars in the variant's window (A 9:30–10:00 ET,
B 9:30–9:35, C 9:25–9:30 premarket). The signal is the first minute, before 11:00 ET, that <b>closes</b> above the
high (long) or below the low (short); entry is the <b>next</b> minute's open and exit the close 15 or 30 minutes
later. No signal by 11:00 is <i>no break</i>; market holidays and half-days are skipped. Gross is open to close on
SIP bars, read once they are 15 minutes old, and every decision uses only bars closed by that minute. Net buys at
the ask and sells at the bid from the quote taken at the start of the entry and exit minutes: {esc(feed_note)}
(this data plan refuses the SIP quote), and no commission. Days counts settled plus no-break days; t is on net
when quotes exist, else gross. The backtest on 807 days, done the same way, was flat to negative; this lane
watches it live.</div>
</details>
</section>"""


def safe_section():
    try:
        return section()
    except Exception as exc:                                    # noqa: BLE001
        return f'<section id="{SECTION_ID}"><h2>Nasdaq open breakout (paper)</h2><p class="sm mut">Section unavailable ({type(exc).__name__}).</p></section>'
