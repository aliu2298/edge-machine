#!/usr/bin/env python3
"""The Crypto page: the favourite-band rule on Kalshi's daily coin closes, on the
shared sport template (sport_page).

One rule, its market-days as the events, the method folded away. The record, verdict and ROI are the Sandbox row's
own figures, the same strings the Sandbox table prints, so this page cannot
disagree with the Sandbox about the pair. The page states the unit the Sandbox
cannot: the lane is judged per market-day, not per contract, because the coins
move together.

No live venue call is made here; the page is rebuilt by
the tracker, and a Kalshi hiccup must not turn into a failed publish.
"""
import datetime
import os

import fmt
import sandbox_build as B
import sandbox_sources as S
import sandbox_track as T
import site_chrome as C

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "public_site", "crypto.html")

# The one lane on this page. family() files crypto under "Markets" with the
# other yes/no domains, which is right for the Sandbox and wrong for here.
SPORTS = ("crypto_fav",)
SOURCE = "crypto_fav_band"
# The four sibling lanes (2026-10-18): the Yes and No favourite, in the 0.70-0.80 band and the
# 0.60-0.70 band below it. Each is its own Sandbox row; only the first is in Production.
LANES = ("crypto_fav_band", "crypto_fav_band_below", "crypto_fav_band_60", "crypto_fav_band_below_60")
RULE_NAMES = {
    "crypto_fav_band": "Favourite band · 3h to the close",
    "crypto_fav_band_below": "Favourite band, below · No 0.70–0.80",
    "crypto_fav_band_60": "Favourite band 60 · Yes 0.60–0.70",
    "crypto_fav_band_below_60": "Favourite band 60, below · No 0.60–0.70",
}
COIN_LABELS = {"bitcoin": "BTC", "ethereum": "ETH", "solana": "SOL",
               "ripple": "XRP", "hyperliquid": "HYPE"}
TOC = (("rules", "Rules"), ("events", "Events"), ("method", "Method"))
LEDE = "Daily favourite-band picks on Kalshi coin closes · times CT"


def esc(x):
    return C.esc("" if x is None else x)


def crypto_rows(d, st):
    rows = [r for r in B.pair_list(d, st) if r["sport"] in SPORTS]
    return sorted(rows, key=lambda r: r["name"])


def _fav_row(rows, source=SOURCE):
    return next((r for r in rows if r.get("sport") == "crypto_fav" and r.get("name") == source), None)


def _fav_quotes(d):
    """Every row this lane has logged: bets (live and archived) and watch-only quotes."""
    return [q for q in (T.bet_rows(d) + [q for q in (d.get("quotes") or []) if not q.get("bet")])
            if q.get("source") in LANES and q.get("sport") in SPORTS]


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
    """The rung backed, as the venue names it: '$84,500 or above', or 'No · $84,500 or above'."""
    if q.get("pick") == "b":
        return f"No · {q.get('side_a') or '—'}"
    side = B._side(q)
    return str(side or "—")


# ------------------------------------------------------------------ the picks list
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


# ------------------------------------------------------------------ the rule
def params(source=SOURCE):
    """The four entry parameters, as (name, value), from the registered constants."""
    below = "below" in source
    lo, hi = S.CRYPTO_FAV_BAND_60 if source.endswith("_60") else S.CRYPTO_FAV_BAND
    band = (f"{lo * 100:g}¢ to under {hi * 100:g}¢" if source.endswith("_60") else f"{lo * 100:g}–{hi * 100:g}¢")
    side = "No ask, on the rung above the price," if below else "Yes ask"
    return (
        ("Entry", f"{side} {band}, {S.CRYPTO_FAV_MIN_H:g}–{S.CRYPTO_FAV_MAX_H:g}h before the close"),
        ("Selection", f"{'cheapest' if source != SOURCE else 'lowest'} qualifying rung, one per coin"),
        ("Liquidity", f"≤{S.CRYPTO_FAV_MAX_SPREAD * 100:g}¢ spread, {S.CRYPTO_FAV_MIN_ASK_SIZE:g}+ {'No ' if below else ''}ask"),
        ("Close", f"{S.CRYPTO_FAV_CLOSE_ET:02d}:00 ET"),
    )


def registered_row(source=SOURCE):
    """The lane as registered, before the Sandbox lists it.

    pair_list gives a pair a row once it has bet. Until then the page still has a
    rule to show: the registration itself, with no record, no ROI and the
    Sandbox's own 'Too early' verdict. Nothing here is a number the
    ledger has not produced.
    """
    meta = S.SOURCES.get(source) or {}
    return dict(name=source, sport="crypto_fav", meta=meta, prod=False, open=0, since=None,
                v="waiting", a=dict(n=0, won=0, expected=0.0, roi_fee=None, n_bets=0, unit="market-day"))


def page_rows(d, st):
    """The Sandbox rows, and the registration of each sibling lane that has not bet yet."""
    rows = crypto_rows(d, st)
    have = {r.get("name") for r in rows}
    return rows + [registered_row(name) for name in LANES if name not in have]


def rule_name(row):
    return RULE_NAMES.get(row.get("name"), RULE_NAMES[SOURCE])


def market(d, row):
    return "Kalshi"


def definition(d, row):
    """The entry parameters first, then the registered definition."""
    dl = "".join(f"<dt>{esc(k)}</dt><dd>{esc(v)}</dd>" for k, v in params(row.get("name") or SOURCE))
    import sport_page as SP
    return f'<dl class="sp-params">{dl}</dl>' + SP.definition_html(row["meta"].get("note"))


def recent_html(d, row, now):
    """The scanner line: last scan, quotes seen, the next entry window."""
    return _scan_status(d, now)


def events(d, rows, now):
    """One event per coin per market-day, holding each sibling lane's bet or watch-only quote."""
    import sport_page as SP
    now = _as_utc(now)
    groups, order = {}, []
    for q in _fav_quotes(d):
        row = _fav_row(rows, q.get("source")) or registered_row(q.get("source"))
        word, _cls = state_of(q)
        state = {"W": "won", "L": "lost", "void": "void", "open": "open"}.get(word, "watch")
        series = _series(q)
        key = (series, q.get("date"))
        if key not in groups:
            groups[key] = dict(close=_close(q), series=series, q=q, picks=[])
            order.append(key)
        groups[key]["picks"].append(SP.pick(row, q, pick_text(q) if (q.get("bet") or q.get("side_a")) else "",
                                            state, price=q.get("price")))
    out = []
    for key in order:
        g = groups[key]
        g["picks"].sort(key=lambda p: LANES.index(p["q"].get("source")) if p["q"].get("source") in LANES else 9)
        out.append(SP.event(g["close"], f"{_coin(g['series'])} · {g['series']}", g["picks"],
                            href=S.market_url(g["q"]), sub="", key=(g["series"], key[1])))
    return out


# ------------------------------------------------------------------ method
def method(d, rows, now):
    inner = f'''{_scan_status(d, now)}
<p class="sm">A day is one bet because the five coins move together: over 90 days of closes their returns correlate at +0.76 and all five move the same way on 54% of days, so a day's rungs win or lose as one and keying per coin would overstate the evidence about twofold. Each contract is logged at the ask of the side its lane backs (Yes for the band lanes, No for the "below" lanes, which back No on a rung above the price) inside the window, settled on Kalshi's own result at a flat ${int(T.STAKE)} stake, and the day is graded as a single outcome against backing every in-band rung that day; the lane reads at {T.READ_FLOOR} market-days.</p>
<p class="sm"><b>Scheduling.</b> A timer on the always-on Mac runs the tracker at 13:15 Central, a fixed 2.83h before the 17:00 Eastern close on either side of the clock change; GitHub's cron could not hold the 90-minute window (inside it on 10 of 18 days). The close is matched in Eastern, not UTC, and the hourly closes on the same series are a different contract.</p>'''
    return "Method", "why a day is one bet · scheduling", inner, False


def build(d=None, st=None, now=None):
    import sport_page as SP
    now = _as_utc(now or datetime.datetime.now(datetime.timezone.utc))
    d = d if d is not None else T.load()
    st = st if st is not None else T.load_stages()
    rows = page_rows(d, st)
    sp = SP.spec(
        family="Crypto", key="crypto", title="Edge Machine · Crypto",
        description="Daily favourite-band picks on Kalshi coin closes, and the rule's record per market-day.",
        scope="Daily favourite-band picks on Kalshi coin closes", venue="Kalshi",
        rows=rows, events=events, rule_name=rule_name, market=market,
        definition=definition, recent=recent_html, method=method, scoped=False,
        unit=lambda row: "market-day")
    return SP.page(sp, d, st, now, rows=rows)


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
