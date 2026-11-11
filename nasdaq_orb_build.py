"""The Trading page's "Nasdaq open breakout (paper)" section (nasdaq_orb.py). Never breaks the page."""
import html as _h

import nasdaq_orb as N
import trading_layout as L

SECTION_ID = "nasdaq-orb"


def esc(x):
    return _h.escape(str(x))


def _f(x, unit="bp", sign=True):
    if x is None:
        return "—"
    return f"{x:+.1f}{unit}" if sign else f"{x:.1f}{unit}"


def _retired_line():
    """One sentence naming the retired variants, from nasdaq_orb.RETIRED."""
    if not N.RETIRED:
        return ""
    by_day = {}
    for k, (last, why) in sorted(N.RETIRED.items()):
        by_day.setdefault((last, why), []).append(k)
    parts = [f'{" and ".join(ks)} retired after {last} ({why})' for (last, why), ks in sorted(by_day.items())]
    return "; ".join(parts) + ". They log no new days; their records stay below."


DAY_HEAD = ('<div class="tbl"><table><thead><tr><th>Day</th><th>Variant</th><th>Range</th><th>Side</th><th>Signal</th>'
            '<th>Entry</th><th>Exit</th><th class="num">Gross</th><th>Bid/ask in → out</th><th class="num">Net</th>'
            '<th>Status</th></tr></thead><tbody>')


def _day_row(r):
    st = {"settled": "settled", "no_break": "no break", "skipped": "skipped", "open": "open",
          "no_data": "no data"}.get(r["status"], r["status"])
    quote = ("—" if r.get("bid_in") is None else
             f'{r["bid_in"]:.2f}/{r["ask_in"]:.2f} → {r["bid_out"]:.2f}/{r["ask_out"]:.2f}'
             if r.get("bid_out") is not None else f'{r["bid_in"]:.2f}/{r["ask_in"]:.2f} → —')
    ent = (r.get("entry_min") or "") + (f" @ {r['entry']:.2f}" if r.get("entry") else "")
    ext = (r.get("exit_min") or "") + (f" @ {r['exit']:.2f}" if r.get("exit") else "")
    rng = (f'{r["range_lo"]:.2f}–{r["range_hi"]:.2f}' if r.get("range_hi") is not None else "—")
    return (f'<tr><td>{esc(r["day"])}</td><td><b>{esc(r["variant"])}</b></td><td>{esc(rng)}</td>'
            f'<td>{esc(r.get("side") or "")}</td><td>{esc(r.get("signal_min") or "")}</td>'
            f'<td>{esc(ent)}</td><td>{esc(ext)}</td>'
            f'<td class="num">{_f(r.get("gross_bp"))}</td><td>{esc(quote)}</td>'
            f'<td class="num">{_f(r.get("net_bp"))}</td>'
            f'<td>{esc(st + (" · " + r["note"] if r.get("note") and r["status"] != "settled" else ""))}</td></tr>')


def _review(k, s, state):
    need = max(0, N.REVIEW_AT - s["days"])
    if s.get("retired"):
        # Retired after its last logged day. Until that day has settled it is still the last day.
        if any(r["variant"] == k and r["day"] >= s["retired"] and r["status"] in ("settled", "no_break", "skipped", "no_data")
               for r in state.get("rows") or []):
            return L.sig(f'Retired {s["retired"]} at {s["days"]} days, {s["retired_why"]}', "x")
        return L.sig(f'last day {s["retired"]}, then retired ({s["retired_why"]})', "x")
    target = N.READ_TARGET.get(k)
    if target and s["days"] >= N.REVIEW_AT:
        # Past the first review and kept collecting to a later read (C15, 2026-11-08).
        return L.sig(f'collecting {min(s["days"], target)}/{target}', "w" if s["days"] >= target else "n")
    return L.sig("review due", "w") if not need else L.sig(f'{s["days"]}/{N.REVIEW_AT} to review')


def _variant_row(k, s, state):
    mine = [r for r in sorted(state.get("rows") or [], key=lambda r: r["day"], reverse=True) if r["variant"] == k][:40]
    days = "".join(_day_row(r) for r in mine) or '<tr><td colspan="11" class="mut">No days yet.</td></tr>'
    _label, r0, r1, _sig, hold = N.VARIANTS[k]
    body = (f'<p class="sp-def">QQQ: the first minute before 11:00 ET that closes beyond the '
            f'{r0[0]}:{r0[1]:02d}–{r1[0]}:{r1[1]:02d} ET range; enter at the next open, exit {hold} minutes later. '
            f'No stop, one position, paper.</p>'
            + L.params([("Variant", f"<b>{esc(k)}</b> · {esc(s['label'])}"),
                        ("Days", f'{s["days"]} decided · {s["trades"]} trades · {s["no_break"]} no break'),
                        ("Avg gross", _f(s["gross"])), ("Avg spread", _f(s["spread"], sign=False)),
                        ("t on", esc(s["t_on"]))])
            + L.fold("Daily rows", DAY_HEAD + days + "</tbody></table></div>"))
    win = "—" if s["win"] is None else f"{s['win'] * 100:.0f}%"
    net = _f(s["net"]) if s["net"] is not None else (_f(s["gross"]) + " gross" if s["gross"] is not None else "—")
    t = "—" if s["t"] is None else f"{s['t']:+.2f}"
    return L.rule(f"nasdaq_orb_{k}", f"{k} · {s['label']}", "QQQ · Alpaca", str(s["days"]), win, net, t,
                  _review(k, s, state), body, muted=bool(s.get("retired")))


def section(state=None):
    state = N.load() if state is None else state
    summ = N.summary(state)
    live = [_variant_row(k, s, state) for k, s in summ.items() if not s.get("retired")]
    gone = [_variant_row(k, s, state) for k, s in summ.items() if s.get("retired")]
    empty = "" if state.get("rows") else ('<p class="sm mut">No days yet: the first session read is '
                                          'Monday 2026-10-19, 9:20–11:50 ET.</p>')
    feeds = sorted({r.get("quote_feed") for r in state.get("rows") or [] if r.get("quote_feed")})
    feed_note = ("IEX top of book" if feeds in ([], ["iex"]) else " / ".join(f.upper() for f in feeds))
    retired = (L.fold(f'Retired variants · {esc(" and ".join(sorted(N.RETIRED)))} · records kept',
                      f'<p class="sm mut">{esc(_retired_line())}</p>'
                      + L.rules_list(gone, first="Variant", key="nasdaq-retired")) if gone else "")
    method = L.fold("How the record is kept", f"""
<div class="note sm">Paper · never places an order · not in Production. QQQ opening-range breakout, four
pre-registered variants, one row each per trading day, no stop, one position. Reviewed at
{N.REVIEW_AT}+ settled days per variant.
The range is the high and low of the 1-minute bars in the variant's window (A 9:30–10:00 ET,
B 9:30–9:35, C 9:25–9:30 premarket). The signal is the first minute, before 11:00 ET, that <b>closes</b> above the
high (long) or below the low (short); entry is the <b>next</b> minute's open and exit the close 15 or 30 minutes
later. No signal by 11:00 is <i>no break</i>; market holidays and half-days are skipped. Gross is open to close on
SIP bars, read once they are 15 minutes old, and every decision uses only bars closed by that minute. Net buys at
the ask and sells at the bid from the quote taken at the start of the entry and exit minutes: {esc(feed_note)}
(this data plan refuses the SIP quote), and no commission. Days counts settled plus no-break days; t is on net
when quotes exist, else gross. The backtest on 807 days, done the same way, was flat to negative; this lane
watches it live.</div>""", cls="fold trade-method")
    if not live:                                                # every variant retired (2026-11-11): the lane is retired
        c = [r for r in state.get("rows") or [] if r["variant"] == "C15" and r["status"] == "settled"]
        nocost = sum(1 for r in c if r.get("net_bp") is None)
        note = (f'<p class="sm">Retired {esc(N.RETIRED["C15"][0])}, the last running variant. No profit after costs in '
                f'forward paper trading, matching the earlier 750-800 session backtests that found no edge.</p>'
                f'<p class="sm mut">C15 final: {len(c)} trades; after-costs figures are missing on {nocost} of {len(c)} '
                f'(no quote captured), so its record is mostly before costs and nothing is backfilled.</p>')
        return L.section(SECTION_ID, f"Nasdaq open breakout (paper) · retired {N.RETIRED['C15'][0]}",
                         f"{len(gone)} variants · retired · records kept",
                         note + L.rules_list(gone, first="Variant", key="nasdaq-retired") + empty + method)
    return L.section(SECTION_ID, "Nasdaq open breakout (paper)",
                     f"{len(live)} running · paper",
                     L.rules_list(live, first="Variant", key="nasdaq-orb") + empty + retired + method)


def safe_section():
    try:
        return section()
    except Exception as exc:                                    # noqa: BLE001
        return f'<section id="{SECTION_ID}"><h2>Nasdaq open breakout (paper)</h2><p class="sm mut">Section unavailable ({type(exc).__name__}).</p></section>'
