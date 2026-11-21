"""combo.html (2026-11-21, Olu: "convert the leadership page to combo"): the paper crypto No + S&P No combo, one a trading day.

Reads data/combo_ledger.json (combo_lane.py) and the two lanes' own single records. Percentages only. No inline style or SVG;
header-row tables, labelled for the phone cards by sandbox_build.label_cells.
"""
import datetime as dt
import html as _h
import os

import combo_lane as CL
import daily_track as D
import site_chrome as C

KEY = "combo"
TITLE = "Edge Machine · Combo"
DESCRIPTION = ("One paper two-leg combo a trading day, crypto No with S&P No, both read at the same minute, against the same two legs as singles.")
SECTIONS = (("today", "Today"), ("record", "Record"), ("days", "Days"), ("prereg", "Pre-registration"))
PREREG_DOC = "docs/prereg_combo_crypto_sp_2026-11-21.md"
TEXT = ("Crypto NO with S&P NO, one two-leg paper combo a trading day. Both legs are chosen at the minute the crypto NO lane logs its pick: "
        "the crypto pick, and the cheapest S&P 16:00 ET rung with a NO ask of 90c to 98c, a spread of 3c or less and 25 or more contracts at "
        "that minute. Priced at 0.994 x 1.03 x the product of the two NO asks, plus the taker fee. The idea came from 19 days to Nov 19 2026 on "
        "which the two legs were priced at different times (17 landed, +23.1%); at one moment only 8 or 9 of those days could be formed "
        "(+5% to +30%). None of that counts: the row starts at zero. Read at 30 settled combos against the same legs as singles.")
RULE = ("Keep only if the return is above zero and the break-even markup is above the paper markup on those 30. Retire at once if either "
        "lane's own singles go under zero.")
NOTE = ("A combo leg is bought at the ask, at one minute. A lane that rests a bid or sells to a target cannot be a leg, because the combo "
        "has no resting order and cannot be sold early.")


def esc(x):
    return _h.escape(str(x), quote=True)


def pct(v, sign=True):
    return "—" if v is None else f"{v * 100:+.1f}%" if sign else f"{v * 100:.1f}%"


def cents(v):
    return f"{v * 100:.0f}c"


def when(iso):
    t = D.instant(iso)
    return t.astimezone(D.ET).strftime("%H:%M ET") if t else "—"


def leg_text(r):
    c, s = r["crypto"], r["sp"]
    return (f"{esc(c.get('label') or c['ticker'])} No at {cents(c['ask'])} · S&amp;P {esc(s.get('title') or s['ticker'])} No at {cents(s['ask'])}")


def today_section(state, now):
    today = now.astimezone(D.ET).date().isoformat()
    r = next((x for x in state["days"] if x["day"] == today), None)
    if r is None:
        what = ("<p>No combo yet today. Both legs are read in one minute, about 13:35 ET on a weekday, right after the crypto No lane logs its pick."
                if now.astimezone(D.ET).weekday() < 5 else "<p>No combo at weekends: the S&amp;P does not trade.")
        return f'<section id="today"><h2>Today</h2>{what}</p></section>'
    if r["status"] == "no_combo":
        return f'<section id="today"><h2>Today</h2><p><b>No combo.</b> {esc(r["reason"])}.</p></section>'
    return ('<section id="today"><h2>Today</h2>'
            f'<p><b>{leg_text(r)}</b></p>'
            f'<p class="sm">Read at {esc(when(r["read_at"]))} (asks {cents(r["crypto"]["ask"])} and {cents(r["sp"]["ask"])}, so the price can be re-worked). Combo price {cents(r["price"])} plus the fee, {cents(r["cost"])} in all, pays 100c '
            f'only if both legs win ({r["payout"] / r["cost"]:.2f}x). The two legs as singles would cost {cents(r["singles"]["crypto"])} and '
            f'{cents(r["singles"]["sp"])}. Status: {esc(r["status"])}.</p></section>')


def record_section(state):
    rec = CL.record(state)
    rows = [
        ("Settled combos", f'{rec["n"]} of {CL.READ_AT} for the read'),
        ("Landed", f'{rec["landed"]} of {rec["n"]}' if rec["n"] else "—"),
        ("Pays when it lands", f'{rec["pays"]:.2f}x' if rec["pays"] else "—"),
        ("Return a combo", pct(rec["mean_roi"])),
        ("The same two legs as singles", pct(rec["single_both"])),
        ("— crypto leg alone", pct(rec["single_crypto"])),
        ("— S&amp;P leg alone", pct(rec["single_sp"])),
        ("Break-even markup", f'{rec["break_even"]:.2f}' if rec["break_even"] else "—"),
        ("Longest losing run", str(rec["run"])),
        ("Open combos", str(rec["open"])),
        ("Days with no combo", str(rec["no_combo"])),
        ("Read", esc(CL.verdict(rec, [roi for _k, _n, _w, roi in own_rows()]))),
    ]
    body = "".join(f"<tr><td>{k}</td><td>{v}</td></tr>" for k, v in rows)
    own = own_singles()
    return ('<section id="record"><h2>Record</h2>'
            '<p class="sm">The record starts at zero on the first combo day; the 19 days of research do not count. Return is after the taker fee.</p>'
            f'<div class="tbl"><table><thead><tr><th>Line</th><th>Value</th></tr></thead><tbody>{body}</tbody></table></div>'
            f'<h3>Each lane\'s own single record</h3>{own}</section>')


def own_rows():
    """[(lane, settled, won, return)] for the two lanes' own ledgers (all days), for comparison with the combo's legs."""
    out = []
    try:
        import sandbox_track as T
        qs = [q for q in (T.load().get("quotes") or []) if q.get("source") == CL.CRYPTO_LANE and q.get("bet") and q.get("status") in ("won", "lost")]
        n = len(qs)
        out.append(("Crypto No 70-80c", n, sum(q["status"] == "won" for q in qs), (sum(q["pnl"] for q in qs) / (n * T.STAKE)) if n else None))
    except Exception:                                           # noqa: BLE001
        out.append(("Crypto No 70-80c", 0, 0, None))
    try:
        import finance_nc as FN
        r = FN.record(FN.load().get("picks") or [])
        out.append(("S&amp;P No 90-98c", r["n_bets"], r["won"], r["roi_fee"]))
    except Exception:                                           # noqa: BLE001
        out.append(("S&amp;P No 90-98c", 0, 0, None))
    return out


def own_singles():
    out = own_rows()
    body = "".join(f"<tr><td>{k}</td><td class=\"num\">{n}</td><td class=\"num\">{w}</td><td class=\"num\">{pct(roi)}</td></tr>" for k, n, w, roi in out)
    return f'<div class="tbl"><table><thead><tr><th>Lane</th><th>Settled</th><th>Won</th><th>Return</th></tr></thead><tbody>{body}</tbody></table></div>'


def days_section(state):
    rows = []
    for r in sorted(state["days"], key=lambda r: r["day"], reverse=True):
        if r["status"] == "no_combo":
            rows.append(f'<tr><td>{esc(r["day"])}</td><td colspan="5">No combo: {esc(r["reason"])}</td></tr>')
            continue
        res = "—" if r["status"] == "open" else {"won": "Landed", "lost": "Missed"}.get(r["status"], "Part value")
        rows.append(f'<tr><td>{esc(r["day"])}</td><td>{leg_text(r)}</td><td>{esc(when(r["read_at"]))}</td>'
                    f'<td class="num">{cents(r["cost"])}{(" (real quote " + cents(r["real_quote"]) + ")") if r.get("real_quote") else ""}</td><td>{res}</td>'
                    f'<td class="num">{pct(r.get("roi"))}</td></tr>')
    table = ('<div class="tbl"><table><thead><tr><th>Day</th><th>Legs</th><th>Priced at</th><th>Cost</th><th>Result</th><th>Return</th></tr></thead>'
             f'<tbody>{"".join(rows)}</tbody></table></div>') if rows else "<p>No days yet.</p>"
    return f'<section id="days"><h2>Days</h2>{table}</section>'


def prereg_section():
    return (f'<section id="prereg"><h2>Pre-registration</h2><p>{esc(TEXT)}</p><p class="sm">{esc(RULE)}</p><p class="sm">{esc(NOTE)}</p>'
            f'<p class="sm mut">Written before the first entry, in {esc(PREREG_DOC)} in the repository.</p></section>')


def build(state=None, now=None):
    now = now or dt.datetime.now(dt.timezone.utc)
    state = state if state is not None else CL.load()
    body = ('<section id="lede"><h1>Combo</h1><p class="lede">One paper two-leg combo a trading day: the crypto No lane\'s pick with the S&amp;P No rung, '
            'both read at the same minute. It pays only if both win.</p></section>'
            + today_section(state, now) + record_section(state) + days_section(state) + prereg_section())
    html = C.document(TITLE, DESCRIPTION, KEY, SECTIONS, C.stamp(now), body, script_src="./site.js", scripts=("./tables.js",))
    import sandbox_build
    return sandbox_build.label_cells(html)


def main():
    out = os.path.join(D.ROOT, "public_site", "combo.html")
    with open(out, "w") as f:
        f.write(build())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
