#!/usr/bin/env python3
"""The Crypto page: the favourite-band rule on Kalshi's daily coin closes.

Four stat tiles, one flat list of picks grouped by day, a one-row rules table,
and the method folded away. The record, verdict and ROI are the Sandbox row's
own figures, the same strings the Sandbox table prints, so this page cannot
disagree with the Sandbox about the pair. The page states the unit the Sandbox
cannot: the lane is judged per market-day, not per contract, because the coins
move together.

The list and table reuse the Tennis page's patterns (tn-*), so the sport pages
read as one product. No live venue call is made here; the page is rebuilt by
the tracker, and a Kalshi hiccup must not turn into a failed publish.
"""
import datetime
import os

import fmt
import sandbox_build as B
import sandbox_sources as S
import sandbox_track as T
import site_chrome as C
import tennis_cards as TN

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "public_site", "crypto.html")

# The one lane on this page. family() files crypto under "Markets" with the
# other yes/no domains, which is right for the Sandbox and wrong for here.
SPORTS = ("crypto_fav",)
SOURCE = "crypto_fav_band"
COIN_LABELS = {"bitcoin": "BTC", "ethereum": "ETH", "solana": "SOL",
               "ripple": "XRP", "hyperliquid": "HYPE"}
TOC = (("picks", "Picks"), ("rule", "Rule"), ("method", "Method"))
LEDE = "Daily favourite-band picks on Kalshi coin closes · times CT"


def esc(x):
    return C.esc("" if x is None else x)


def crypto_rows(d, st):
    rows = [r for r in B.pair_list(d, st) if r["sport"] in SPORTS]
    return sorted(rows, key=lambda r: r["name"])


def _fav_row(rows):
    return next((r for r in rows if r.get("sport") == "crypto_fav"), None)


def _fav_quotes(d):
    """Every row this lane has logged: bets (live and archived) and watch-only quotes."""
    return [q for q in (T.bet_rows(d) + [q for q in (d.get("quotes") or []) if not q.get("bet")])
            if q.get("source") == SOURCE and q.get("sport") in SPORTS]


def _series(q):
    market_id = str(q.get("market_id") or "")
    return market_id.split("-", 1)[0] if "-" in market_id else market_id


def _coin(series):
    return COIN_LABELS.get(S.COINS.get(series, ""), S.COINS.get(series, series).upper())


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


def _today_close(now):
    """Today's 17:00 ET close as a UTC instant."""
    local = _as_utc(now).astimezone(S.CRYPTO_FAV_TZ)
    close = local.replace(hour=S.CRYPTO_FAV_CLOSE_ET, minute=0, second=0, microsecond=0)
    return close.astimezone(datetime.timezone.utc)


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
    """The rung backed, as the venue names it: '$84,500 or above'."""
    side = B._side(q)
    return str(side or "—")


# ------------------------------------------------------------------ the picks list
def _pick_html(coin, series, q, when):
    word, cls = state_of(q)
    if q is not None:
        link = B.safe_href(S.market_url(q), f"{coin} · {series}")
        pick = B.esc(pick_text(q)) if q.get("bet") or q.get("side_a") else "—"
        price = fmt.cents(q.get("price")) if q.get("price") is not None else "—"
    else:
        link = f"{B.esc(coin)} · {B.esc(series)}"
        pick, price = "", ""
    muted = " is-muted" if q is None else ""
    return (f'<div class="tn-pick cr-pick{muted} {cls}" data-series="{B.esc(series)}">'
            f'<span class="tn-time">{B.esc(when)}</span>'
            f'<span class="tn-match">{link}</span>'
            f'<span class="tn-pos">{f"<b>{pick}</b>" if pick else ""}</span>'
            f'<span class="tn-price">{B.esc(price)}</span>'
            f'<span class="tn-state {cls}">{B.esc(word)}</span></div>')


def day_blocks(d, now):
    """[(day, [(coin, series, quote or None)])], today first, then earlier days, newest first.

    Today lists every live coin once: its bet or watch-only quote, else no
    entry. Every other day lists the rows that were logged on it.
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
    rows = []
    for series in S.COINS:
        mine = [q for q in todays if _series(q) == series]
        mine.sort(key=lambda q: (not q.get("bet"), str(q.get("logged") or "")), reverse=False)
        bets = [q for q in mine if q.get("bet")]
        rows.append((_coin(series), series, bets[0] if bets else (mine[0] if mine else None)))
    blocks.append((today, rows))
    for day in sorted(by_day, reverse=True):
        rows = sorted(by_day[day], key=lambda q: (not q.get("bet"), _series(q)))
        blocks.append((day, [(_coin(_series(q)), _series(q), q) for q in rows]))
    return blocks


def picks_html(d, now):
    now = _as_utc(now)
    today = fmt.chicago(now).date()
    close_today = fmt.clock(_today_close(now))
    parts = []
    for day, rows in day_blocks(d, now):
        label = TN._day_label(day, today)
        items = [f'<div class="tn-day">{B.esc(label)}</div>']
        for coin, series, q in rows:
            close = _close(q) if q is not None else None
            when = fmt.clock(close) if close is not None else (close_today if day == today else "—")
            items.append(_pick_html(coin, series, q, when))
        parts.append(f'<div class="tn-dayblock">{"".join(items)}</div>')
    return f'<div class="tn-picks">{"".join(parts)}</div>'


def _window(now):
    """('Next' or 'Current', 'Oct 8, 12:30–2:00 PM CT') for the entry window."""
    local = _as_utc(now).astimezone(S.CRYPTO_FAV_TZ)
    close = local.replace(hour=S.CRYPTO_FAV_CLOSE_ET, minute=0, second=0, microsecond=0)
    end = close - datetime.timedelta(hours=S.CRYPTO_FAV_MIN_H)
    if local > end:
        close += datetime.timedelta(days=1)
    start = close - datetime.timedelta(hours=S.CRYPTO_FAV_MAX_H)
    end = close - datetime.timedelta(hours=S.CRYPTO_FAV_MIN_H)
    s, e = fmt.chicago(start), fmt.chicago(end)
    first = f"{s:%-I:%M}" if f"{s:%p}" == f"{e:%p}" else f"{s:%-I:%M %p}"
    text = f"{fmt._MONTHS[s.month - 1]} {s.day}, {first}–{e:%-I:%M %p} CT"
    return ("Current" if start <= local <= end else "Next"), text


def _scan_status(d, now):
    """One muted line: last scan · quotes seen · the next entry window."""
    stamp = (d.get("meta") or {}).get("updated")
    try:
        last = datetime.datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
        if last.tzinfo is None:
            last = None
    except ValueError:
        last = None
    coverage = ((d.get("coverage") or {}).get("crypto_fav") or {}).get(SOURCE)
    bits = [f"Last scan {fmt.when(last)}" if last is not None else "Last scan not recorded"]
    if isinstance(coverage, dict) and last is not None:
        bits.append(f'{int(coverage.get("offered") or 0)} quotes')
    else:
        bits.append("no scanner coverage stored")
    word, window = _window(now)
    bits.append(f"{word.lower()} window {window}")
    return f'<p class="sm mut cr-scan">{esc(" · ".join(bits))}</p>'


# ------------------------------------------------------------------ tiles and the rule
def _unit(a, n=None):
    n = a.get("n") if n is None else n
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
        f'<div class="tile"><b>{n} of {T.READ_FLOOR}</b><span>market-days logged · {T.READ_FLOOR} planned</span></div>'
        '</div>')


def params():
    """The four entry parameters, as (name, value), from the registered constants."""
    lo, hi = S.CRYPTO_FAV_BAND
    return (
        ("Entry", f"Yes ask {lo * 100:g}–{hi * 100:g}¢, {S.CRYPTO_FAV_MIN_H:g}–{S.CRYPTO_FAV_MAX_H:g}h before the close"),
        ("Selection", "lowest qualifying rung, one per coin"),
        ("Liquidity", f"≤{S.CRYPTO_FAV_MAX_SPREAD * 100:g}¢ spread, {S.CRYPTO_FAV_MIN_ASK_SIZE:g}+ ask"),
        ("Close", f"{S.CRYPTO_FAV_CLOSE_ET:02d}:00 ET"),
    )


_HEAD = ('<tr><th>Rule</th><th>Venue</th><th class="num">Record</th>'
         '<th class="num">ROI</th><th>Verdict</th><th class="num">Open</th></tr>')


def rule_html(rows, d):
    fav = _fav_row(rows)
    if not fav:
        return '<div class="note">No crypto favourite-band record yet.</div>'
    a = fav["a"]
    n = int(a.get("n") or 0)
    open_n = sum(1 for q in _fav_quotes(d) if q.get("bet") and q.get("status") == "open")
    note = (fav["meta"].get("note") or "").strip()
    stage = ' <span class="sig y">PRODUCTION</span>' if fav.get("prod") else ""
    dl = "".join(f"<dt>{esc(k)}</dt><dd>{esc(v)}</dd>" for k, v in params())
    sample = f'<div class="sm mut">on {n} {_unit(a, n)}</div>' if n else ""
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
    return f'''<section id="method" class="tn-system">
<details><summary><b>Method</b><small>why a day is one bet · scheduling</small></summary>
<div>
<p class="sm">A day is one bet because the five coins move together: over 90 days of closes their returns correlate at +0.76 and all five move the same way on 54% of days, so a day's rungs win or lose as one and keying per coin would overstate the evidence about twofold. Each contract is logged at the Yes ask inside the window, settled on Kalshi's own result at a flat ${int(T.STAKE)} stake, and the day is graded as a single outcome against backing every in-band rung that day; the lane reads at {T.READ_FLOOR} market-days.</p>
<p class="sm"><b>Scheduling.</b> A timer on the always-on Mac runs the tracker at 13:15 Central, a fixed 2.83h before the 17:00 Eastern close on either side of the clock change; GitHub's cron could not hold the 90-minute window (inside it on 10 of 18 days). The close is matched in Eastern, not UTC, and the hourly closes on the same series are a different contract.</p>
</div>
</details>
</section>'''


def build(d=None, st=None, now=None):
    now = _as_utc(now or datetime.datetime.now(datetime.timezone.utc))
    d = d if d is not None else T.load()
    st = st if st is not None else T.load_stages()
    rows = crypto_rows(d, st)
    body = f"""<h1>Crypto</h1>
<p class="lede">{esc(LEDE)}</p>
<p class="sm mut cr-updated">{esc(fmt.display_updated(now))}</p>
{tiles_html(rows, d)}
<section id="picks" class="tn-section">
<h2>Picks</h2>
<p class="sm mut">Today's five coins once each, then every settled market-day.</p>
{picks_html(d, now)}
{_scan_status(d, now)}
</section>
<section id="rule" class="tn-section">
<h2>Rule</h2>
<p class="sm mut">Open the row for the entry parameters and the registered definition.</p>
{rule_html(rows, d)}
</section>
{method_html()}
<footer>Read-only static export · rebuilt by GitHub Actions · research, not betting advice.</footer>
"""
    page = C.document(
        "Edge Machine · Crypto",
        "Daily favourite-band picks on Kalshi coin closes, and the rule's record per market-day.",
        "crypto",
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
