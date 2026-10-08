#!/usr/bin/env python3
"""The Commodities page: the favourite-band rule on Kalshi's daily commodity ladders.

Built the way crypto.html is: four stat tiles, a one-row rules table, one flat
list of picks grouped by trading day, and the method folded away. The record,
verdict and ROI are the Sandbox row's own figures, so this page cannot disagree
with the Sandbox about the pair. The page states the unit the Sandbox cannot:
the lane is judged per market-day, not per contract, and a market-day is a
trading day.

The list and table reuse the Tennis page's patterns (tn-*), so the sport pages
read as one product. No live venue call is made here; the page is rebuilt by
the tracker, and a Kalshi hiccup must not turn into a failed publish.
"""
import datetime
import os

import fmt
import production
import sandbox_build as B
import sandbox_sources as S
import sandbox_track as T
import site_chrome as C
import tennis_cards as TN

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "public_site", "commodities.html")

SPORTS = ("commodities_fav",)
SOURCE = "commod_fav_band"
TOC = (("rule", "Rule"), ("picks", "Picks"), ("method", "Method"))
LEDE = "Daily favourite-band picks on Kalshi commodity closes · times CT"


def esc(x):
    return C.esc("" if x is None else x)


def commod_rows(d, st):
    rows = [r for r in B.pair_list(d, st) if r["sport"] in SPORTS]
    return sorted(rows, key=lambda r: r["name"])


def _fav_row(rows):
    return next((r for r in rows if r.get("sport") == "commodities_fav"), None)


def _fav_quotes(d):
    """Every row this lane has logged: bets (live and archived) and watch-only quotes."""
    return [q for q in (T.bet_rows(d) + [q for q in (d.get("quotes") or []) if not q.get("bet")])
            if q.get("source") == SOURCE and q.get("sport") in SPORTS]


def _series(q):
    market_id = str(q.get("market_id") or "")
    return market_id.split("-", 1)[0] if "-" in market_id else market_id


def _short(series):
    return S.COMMOD_FAV_SHORT.get(series, series)


def _close(q):
    raw = q.get("start")
    if not raw:
        return None
    try:
        return fmt.chicago(raw).astimezone(datetime.timezone.utc)
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def _day_of(q):
    """The Chicago day a quote settles on: its close, else its stored date."""
    close = _close(q)
    if close is not None:
        return fmt.chicago(close).date()
    raw = q.get("date")
    try:
        return datetime.date.fromisoformat(str(raw)[:10])
    except (TypeError, ValueError):
        return None


def _as_utc(now):
    if now.tzinfo is None:
        return now.replace(tzinfo=datetime.timezone.utc)
    return now.astimezone(datetime.timezone.utc)


def _series_close(series, day):
    """This series' close on an Eastern calendar day, as a UTC instant."""
    hour, minute = S.commod_fav_close_et(series)
    local = datetime.datetime.combine(day, datetime.time(hour, minute), S.COMMOD_FAV_TZ)
    return local.astimezone(datetime.timezone.utc)


def state_of(q):
    """(word, class) for one row: W / L once settled, open while it runs, watching for a quote."""
    if q is None:
        return "no entry", "is-none"
    status = q.get("status")
    if q.get("bet"):
        if status == "won":
            return "W", "is-won"
        if status == "lost":
            return "L", "is-lost"
        if status == "void":
            return "void", "is-none"
        return "open", "is-live"
    return "watching", "is-next"


def pick_text(q):
    """The rung backed, named by its commodity: 'WTI above $81.49'."""
    side = str(B._side(q) or "").strip()
    name = _short(_series(q))
    if side.lower().endswith(" or above"):
        return f"{name} above {side[:-len(' or above')]}"
    return f"{name} {side}" if side else name


# ------------------------------------------------------------------ the picks list
def _pick_html(series, q, when):
    word, cls = state_of(q)
    name = f"{_short(series)} · {series}"
    if q is not None:
        link = B.safe_href(S.market_url(q), name)
        pick = B.esc(pick_text(q)) if q.get("bet") or q.get("side_a") else ""
        price = fmt.cents(q.get("price")) if q.get("price") is not None else "—"
    else:
        link = B.esc(name)
        pick, price = "", ""
    muted = " is-muted" if q is None else ""
    return (f'<div class="tn-pick cr-pick{muted} {cls}" data-series="{B.esc(series)}">'
            f'<span class="tn-time">{B.esc(when)}</span>'
            f'<span class="tn-match">{link}</span>'
            f'<span class="tn-pos">{f"<b>{pick}</b>" if pick else ""}</span>'
            f'<span class="tn-price">{B.esc(price)}</span>'
            f'<span class="tn-state {cls}">{B.esc(word)}</span></div>')


def day_blocks(d, now):
    """[(day, [(series, quote or None)])], today first, then earlier days, newest first.

    Today lists every series once, when today is a trading day: its bet or
    watch-only quote, else no entry. Every other day lists the rows logged on it.
    """
    now = _as_utc(now)
    today = fmt.chicago(now).date()
    by_day = {}
    for q in _fav_quotes(d):
        day = _day_of(q)
        if day is None:
            continue
        by_day.setdefault(day, []).append(q)
    blocks = []
    todays = by_day.pop(today, [])
    if S.commod_fav_trading_day(today) or todays:
        rows = []
        for series in S.COMMOD_FAV_SERIES:
            mine = sorted((q for q in todays if _series(q) == series),
                          key=lambda q: (not q.get("bet"), str(q.get("logged") or "")))
            bets = [q for q in mine if q.get("bet")]
            rows.append((series, bets[0] if bets else (mine[0] if mine else None)))
        blocks.append((today, rows))
    for day in sorted(by_day, reverse=True):
        rows = sorted(by_day[day], key=lambda q: (not q.get("bet"), _series(q)))
        blocks.append((day, [(_series(q), q) for q in rows]))
    return blocks


def picks_html(d, now):
    now = _as_utc(now)
    today = fmt.chicago(now).date()
    parts = []
    for day, rows in day_blocks(d, now):
        label = TN._day_label(day, today)
        items = [f'<div class="tn-day">{B.esc(label)}</div>']
        for series, q in rows:
            close = _close(q) if q is not None else None
            if close is None and day == today:
                close = _series_close(series, today)
            when = fmt.clock(close) if close is not None else "—"
            items.append(_pick_html(series, q, when))
        parts.append(f'<div class="tn-dayblock">{"".join(items)}</div>')
    if not parts:
        return '<p class="tn-empty">No market-day today and nothing settled yet.</p>'
    return f'<div class="tn-picks">{"".join(parts)}</div>'


def _window_text(start, end):
    s, e = fmt.chicago(start), fmt.chicago(end)
    first = f"{s:%-I:%M}" if f"{s:%p}" == f"{e:%p}" else f"{s:%-I:%M %p}"
    return f"{fmt._MONTHS[s.month - 1]} {s.day}, {first}–{e:%-I:%M %p} CT"


def _scan_status(d, now):
    """One muted line: last scan · quotes seen · the next entry window."""
    now = _as_utc(now)
    stamp = (d.get("meta") or {}).get("updated")
    try:
        last = datetime.datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
        if last.tzinfo is None:
            last = None
    except ValueError:
        last = None
    coverage = ((d.get("coverage") or {}).get("commodities_fav") or {}).get(SOURCE)
    bits = [f"Last scan {fmt.when(last)}" if last is not None else "Last scan not recorded"]
    if isinstance(coverage, dict) and last is not None:
        bits.append(f'{int(coverage.get("offered") or 0)} quotes')
    else:
        bits.append("no scanner coverage stored")
    label, series, start, end, _close_at = S.commod_fav_windows(now)[0]
    word = "current" if start <= now <= end else "next"
    names = " + ".join(_short(x) for x in series)
    bits.append(f"{word} window {_window_text(start, end)} ({names})")
    return f'<p class="sm mut cr-scan">{esc(" · ".join(bits))}</p>'


# ------------------------------------------------------------------ tiles and the rule
def _unit(n):
    return f'market-day{"" if n == 1 else "s"}'


def tiles_html(rows, d):
    fav = _fav_row(rows)
    a = (fav or {}).get("a") or {}
    n = int(a.get("n") or 0)
    open_n = sum(1 for q in _fav_quotes(d) if q.get("bet") and q.get("status") == "open")
    if n and a.get("roi_fee") is not None:
        klass = "mut" if n < B.MIN_N else fmt.tone(a["roi_fee"], ".1f", 100)
        roi = f'<b class="{klass}">{B.pct(a["roi_fee"], sign=True)}</b>'
    else:
        roi = '<b class="mut">—</b>'
    return (
        '<div class="tiles tn-tiles">'
        f'<div class="tile"><b>{open_n}</b><span>open picks</span></div>'
        f'<div class="tile"><b>{esc(TN.record_text(a))}</b><span>record · W–L</span></div>'
        f'<div class="tile">{roi}<span>ROI after fees</span></div>'
        f'<div class="tile"><b>{n} of {S.COMMOD_FAV_READ_DAYS}</b><span>market-days logged · {S.COMMOD_FAV_READ_DAYS} planned</span></div>'
        '</div>')


def params():
    """The entry parameters, as (name, value), from the registered constants."""
    lo, hi = S.COMMOD_FAV_BAND
    wti_h, wti_m = S.commod_fav_close_et("KXWTI")
    oth_h, oth_m = S.COMMOD_FAV_DEFAULT_CLOSE_ET
    return (
        ("Entry", f"Yes ask {lo * 100:g}–{hi * 100:g}¢, {S.COMMOD_FAV_MIN_H:g}–{S.COMMOD_FAV_MAX_H:g}h before the close"),
        ("Selection", "lowest qualifying rung, one per commodity, trading days only"),
        ("Liquidity", f"≤{S.COMMOD_FAV_MAX_SPREAD * 100:g}¢ spread, {S.COMMOD_FAV_MIN_ASK_SIZE:g}+ ask"),
        ("Close", f"WTI {wti_h:02d}:{wti_m:02d} ET · the rest {oth_h:02d}:{oth_m:02d} ET"),
    )


_HEAD = ('<tr><th>Rule</th><th>Venue</th><th class="num">Record</th>'
         '<th class="num">ROI</th><th>Verdict</th><th class="num">Open</th></tr>')


def _registered_row():
    """The lane as registered, before the Sandbox lists it.

    pair_list gives a pair a row once it has bet. Until then the page still has a
    rule to show: the registration itself, with no record, no ROI and the
    Sandbox's own 'Waiting for results' verdict. Nothing here is a number the
    ledger has not produced.
    """
    meta = S.SOURCES.get(SOURCE) or {}
    return dict(name=SOURCE, sport="commodities_fav", meta=meta, prod=False, open=0,
                v="waiting", a=dict(n=0, won=0, expected=0.0, roi_fee=None, n_bets=0))


def rule_html(rows, d):
    fav = _fav_row(rows) or _registered_row()
    a = fav["a"]
    n = int(a.get("n") or 0)
    open_n = sum(1 for q in _fav_quotes(d) if q.get("bet") and q.get("status") == "open")
    note = (fav["meta"].get("note") or "").strip()
    stage = (' <span class="sig y">PRODUCTION</span>' + production.early_html(fav.get("early"))
             if fav.get("prod") else "")
    dl = "".join(f"<dt>{esc(k)}</dt><dd>{esc(v)}</dd>" for k, v in params())
    sample = f'<div class="sm mut">on {n} {_unit(n)}</div>' if n else ""
    return (
        f'<div class="tbl"><table class="tn-rules cr-rules">{_HEAD}'
        f'<tr data-source="{esc(fav["name"])}" data-sport="{esc(fav["sport"])}">'
        f'<td><details class="tn-rule"><summary><b>Favourite band · 3h to the close</b>{stage}</summary>'
        f'<dl class="cr-params">{dl}</dl>'
        f'<p class="tn-def sm mut">{esc(note)}</p></details></td>'
        f'<td>Kalshi</td>'
        f'<td class="num">{esc(TN.record_text(a))}</td>'
        f'<td class="num">{TN.roi_html(fav)}{sample}</td>'
        f'<td>{TN.verdict_html(fav)}</td>'
        f'<td class="num">{open_n or "—"}</td></tr></table></div>')


# ------------------------------------------------------------------ method
def method_html():
    pairs = S.COMMOD_FAV_CORRELATION
    gs = pairs.get(("KXGOLDD", "KXSILVERD"))
    wb = pairs.get(("KXWTI", "KXBRENTD"))
    return f'''<section id="method" class="tn-system">
<details><summary><b>Method</b><small>why a day is one bet · scheduling</small></summary>
<div>
<p class="sm">A day is one bet because the commodities move in pairs: on the ledger's own graded rungs gold and silver moved together at +{gs:.2f} and WTI and Brent at +{wb:.2f}, with copper riding the metals, so a day where both members of a pair fire is reported per commodity here and judged as one outcome in the record. A market-day is a trading day: a weekend or a US exchange holiday is no market-day at all, so the {S.COMMOD_FAV_READ_DAYS}-day read takes about seven weeks. Each contract is logged at the Yes ask inside its window with the bid, ask and ask size it was taken at, settled on Kalshi's own result at a flat ${int(T.STAKE)} stake, and the day is graded as a single outcome against backing every in-band rung that day.</p>
<p class="sm"><b>Scheduling.</b> Two reads a day, one per close: WTI settles at 14:30 Eastern, so its window is 10:00–11:30 Central, and the other five settle at 17:00 Eastern, so theirs is 12:30–2:00 Central, the crypto lane's window. Each is asked for from the always-on box inside its own window by the same stamp-file mechanism the crypto lane uses, because GitHub's cron cannot hold a 90-minute window. The close is matched in Eastern, not UTC, so the November clock change moves it with the exchange.</p>
</div>
</details>
</section>'''


def build(d=None, st=None, now=None):
    now = _as_utc(now or datetime.datetime.now(datetime.timezone.utc))
    d = d if d is not None else T.load()
    st = st if st is not None else T.load_stages()
    rows = commod_rows(d, st)
    body = f"""<h1>Commodities</h1>
<p class="lede">{esc(LEDE)}</p>
<p class="sm mut cr-updated">{esc(fmt.display_updated(now))}</p>
{tiles_html(rows, d)}
<section id="rule" class="tn-section">
<h2>Rule</h2>
<p class="sm mut">Open the row for the entry parameters and the registered definition.</p>
{rule_html(rows, d)}
</section>
<section id="picks" class="tn-section">
<h2>Picks</h2>
<p class="sm mut">Today's six commodities once each, then every settled market-day.</p>
{picks_html(d, now)}
{_scan_status(d, now)}
</section>
{method_html()}
<footer>Read-only static export · rebuilt by GitHub Actions · research, not betting advice.</footer>
"""
    page = C.document(
        "Edge Machine · Commodities",
        "Daily favourite-band picks on Kalshi commodity closes, and the rule's record per market-day.",
        "commodities",
        TOC,
        C.stamp(now),
        body,
        script_src="./site.js",
        scripts=("./tables.js",),
        sports=True,
    )
    # Cells named for the phone layout here, so the direct build and the
    # tracker build (which labels every page) are the same document.
    return B.label_cells(page)


def main():
    html = build()
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    tmp = OUT + ".tmp"
    with open(tmp, "w") as f:
        f.write(html)
    os.replace(tmp, OUT)
    print(f"wrote {OUT} ({len(html):,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
