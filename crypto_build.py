#!/usr/bin/env python3
"""The Crypto page: the favourite-band rule, and the baseline that motivated it.

WHY IT EXISTS SEPARATELY. Crypto is two pairs, not twenty, so this page is not here to
hold a long list. It is here because the two pairs only make sense next to each other and
neither reads correctly alone.

`spot|crypto` is a declared NULL HYPOTHESIS — today's price carried forward — and it came
back flat over 22 days (26 market-days, 15 won v 14.44 priced, z -0.07). That is its
answer, not its failure: it says Kalshi's daily coin buckets are efficiently priced, so
nothing subtler is worth connecting on the strength of a forecast.

`crypto_fav_band|crypto_fav` is the follow-up question, and a different one. It does not
forecast anything. It asks whether the PRICE ITSELF is biased in the 0.70-0.80 favourite
band, held for about three hours into the 17:00 ET close.

WHAT THIS PAGE ADDS THAT THE SANDBOX CANNOT. Both pairs sit inside the Sandbox's folding
"Markets" section with climate, commodities and finance, where the thing that matters most
about them is invisible: they are judged PER DAY, not per bet, because the coins move
together. A reader seeing "97 bets" on the Sandbox has no way to know the honest
denominator is 26. This page states the unit, and the measurement behind it, in the place
where the record is read.

No live venue call is made here. The page is rebuilt by the tracker, and a Kalshi hiccup
must not turn into a failed publish.
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

# Both pairs, named rather than derived: family() puts crypto in "Markets" with the other
# yes/no domains, which is right for the Sandbox and wrong for this page.
SPORTS = ("crypto_fav", "crypto")


def esc(x):
    return C.esc("" if x is None else x)


def crypto_rows(d, st):
    rows = [r for r in B.pair_list(d, st) if r["sport"] in SPORTS]
    order = {s: i for i, s in enumerate(SPORTS)}
    return sorted(rows, key=lambda r: (order.get(r["sport"], 9), r["name"]))


def _fav_row(rows):
    return next((r for r in rows if r.get("sport") == "crypto_fav"), None)


def _fav_quotes(d):
    return [q for q in (T.bet_rows(d) + [q for q in (d.get("quotes") or []) if not q.get("bet")])
            if q.get("source") == "crypto_fav_band" and q.get("sport") == "crypto_fav"]


def _series(q):
    market_id = str(q.get("market_id") or "")
    return market_id.split("-", 1)[0] if "-" in market_id else market_id


def _coin_watch(d):
    """Five fixed live series, with only facts already stored in the ledger."""
    quotes = _fav_quotes(d)
    out = []
    labels = {
        "bitcoin": "BTC", "ethereum": "ETH", "solana": "SOL",
        "ripple": "XRP", "hyperliquid": "HYPE",
    }
    for series, coin in S.COINS.items():
        items = [q for q in quotes if _series(q) == series]
        items.sort(key=lambda q: str(q.get("logged") or q.get("start") or ""), reverse=True)
        open_rows = [q for q in items if q.get("bet") and q.get("status") == "open"]
        bets = [q for q in items if q.get("bet")]
        latest = open_rows[0] if open_rows else (bets[0] if bets else (items[0] if items else None))
        if open_rows:
            state = "Open"
            state_cls = "crypto-state-open"
        elif latest and latest.get("bet") and latest.get("status") in ("won", "lost"):
            state = "Last " + str(latest.get("status")).title()
            state_cls = "crypto-state-won" if latest.get("status") == "won" else "crypto-state-lost"
        else:
            state = "Watching"
            state_cls = "crypto-state-watch"
        price = latest.get("price") if isinstance(latest, dict) else None
        price_text = fmt.cents(price) if price is not None else "—"
        out.append((labels.get(coin, coin.upper()), series, state, state_cls, price_text))
    return out


def _watch_html(d):
    cards = []
    for coin, series, state, state_cls, price in _coin_watch(d):
        cards.append(
            f'<div class="crypto-coin">'
            f'<div class="crypto-coin-name"><strong>{esc(coin)}</strong><span>{esc(series)}</span></div>'
            f'<div class="crypto-coin-price">{esc(price)}</div>'
            f'<span class="crypto-state {esc(state_cls)}">{esc(state)}</span>'
            f'</div>'
        )
    return "".join(cards)


def _hero(rows):
    fav = _fav_row(rows)
    a = (fav or {}).get("a") or {}
    n = int(a.get("n") or 0)
    won = int(a.get("won") or 0)
    roi = a.get("roi_fee")
    clv = a.get("clv")
    clv_n = int(a.get("clv_n") or 0)
    open_n = int((fav or {}).get("open") or 0)
    stage = "Production" if (fav or {}).get("prod") else "Sandbox"
    roi_text = B.pct(roi, sign=True) if roi is not None else "—"
    clv_text = fmt.signed_cents(clv) if clv is not None and clv_n else "—"
    remaining = max(0, T.READ_FLOOR - n)
    progress_cells = "".join(
        '<span class="is-filled" aria-hidden="true"></span>' if i < n
        else '<span aria-hidden="true"></span>'
        for i in range(T.READ_FLOOR)
    )
    return f"""<section class="crypto-hero" aria-label="Crypto lane status">
<div class="crypto-hero-top">
<div><span class="crypto-stage">{esc(stage)}</span><h1>Crypto</h1></div>
<div class="crypto-live-dot"><span aria-hidden="true"></span>{open_n} open</div>
</div>
<div class="crypto-return"><strong>{esc(roi_text)}</strong><span>ROI after fees</span></div>
<div class="crypto-stats">
<div><b>{won}–{max(0, n - won)}</b><span>record</span></div>
<div><b>{esc(clv_text)}</b><span>vs close</span></div>
<div><b>{n} / {T.READ_FLOOR}</b><span>market-days</span></div>
</div>
<div class="crypto-progress" role="progressbar" aria-valuemin="0" aria-valuemax="{T.READ_FLOOR}" aria-valuenow="{min(n, T.READ_FLOOR)}">
{progress_cells}
</div>
<p class="sm mut">{remaining} more independent market-day{"s" if remaining != 1 else ""} before the planned read.</p>
</section>"""


def _record_cards(rows):
    fav = _fav_row(rows)
    if not fav:
        return '<div class="note">No crypto favourite-band record yet.</div>'
    a = fav.get("a") or {}
    won = a.get("won") or 0
    expected = a.get("expected")
    priced_text = f"{expected:.1f}" if expected is not None else "—"
    edge_text = f"{won - expected:+.1f} wins" if expected is not None else "—"
    return f"""<div class="crypto-metrics">
<div><span>Won v priced</span><strong>{esc(won)} v {esc(priced_text)}</strong><small>{esc(edge_text)}</small></div>
<div><span>Contracts</span><strong>{esc(a.get("n_bets", 0))}</strong><small>{esc(a.get("n_bets", 0))} contracts logged</small></div>
</div>"""


def _scan_status(d, now):
    """Display stored tracker coverage and the existing rule's entry window."""
    stamp = (d.get("meta") or {}).get("updated")
    try:
        last = datetime.datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
        if last.tzinfo is None:
            last = None
    except ValueError:
        last = None
    coverage = ((d.get("coverage") or {}).get("crypto_fav") or {}).get("crypto_fav_band")
    recorded = isinstance(coverage, dict) and last is not None
    status = "Coverage recorded" if recorded else "Not recorded"
    detail = (f'{coverage.get("offered", 0)} quotes · {coverage.get("picked", 0)} picks'
              if recorded else "No stored scanner coverage")
    local = now.astimezone(S.CRYPTO_FAV_TZ)
    close = local.replace(hour=S.CRYPTO_FAV_CLOSE_ET, minute=0, second=0, microsecond=0)
    end = close - datetime.timedelta(hours=S.CRYPTO_FAV_MIN_H)
    if local > end:
        close += datetime.timedelta(days=1)
    start = close - datetime.timedelta(hours=S.CRYPTO_FAV_MAX_H)
    end = close - datetime.timedelta(hours=S.CRYPTO_FAV_MIN_H)
    window = f'{fmt.chicago(start):%b %-d, %-I:%M %p}–{fmt.chicago(end):%-I:%M %p} CT'
    return f'''<section class="crypto-health" aria-label="Scanner status">
<div><span>Scanner coverage</span><b>{esc(status)}</b><small>{esc(detail)}</small></div>
<div><span>Last tracker scan</span><b>{esc(fmt.when(last) if last else "Not recorded")}</b><small>Coin-specific scan times unavailable</small></div>
<div><span>{"Current" if start <= local <= end else "Next"} entry window</span><b>{esc(window)}</b><small>{S.CRYPTO_FAV_MAX_H:g}–{S.CRYPTO_FAV_MIN_H:g}h before close</small></div>
</section>'''


def mechanism():
    lo, hi = S.CRYPTO_FAV_BAND
    coins = ", ".join(sorted(S.COINS))
    dark = ", ".join(sorted(S.COINS_DARK))
    return f"""<section id="rule">
<h2>The rule under test</h2>
<div class="note">Registered <b>2026-10-05</b>, before it logged anything, and registered
<b>expecting to find nothing</b>. Every number below was fixed in advance.</div>
<div class="tbl"><table>
<tr><th>Entry</th><td>Yes ask <b>{lo:.2f}–{hi:.2f}</b>, both ends inclusive</td></tr>
<tr><th>Window</th><td>{S.CRYPTO_FAV_MIN_H:g}–{S.CRYPTO_FAV_MAX_H:g} hours before the
 <b>{S.CRYPTO_FAV_CLOSE_ET}:00 Eastern</b> close — about a three-hour hold, settling the
 same afternoon. Matched in Eastern, not in UTC: that close is 21:00Z under daylight time
 and 22:00Z under standard time, and a fixed UTC hour would have silently stopped the lane
 at the November change. The hourly closes on the same series are a different contract and
 are not this bet.</td></tr>
<tr><th>When it reads</th><td>A launchd timer on the always-on Mac dispatches the tracker at
 <b>13:15 local Central</b>, permanently 2.83h before the close because Central and Eastern
 shift on the same date. GitHub\u2019s cron cannot hold a 90-minute window: measured over 18
 days it ran 4.2 times a day against 8 scheduled, landing inside the window on 10 of
 18.</td></tr>
<tr><th>Which rung</th><td>The <b>lowest-priced rung in band</b>, one per coin. A ladder
 offers several at once, so the choice is fixed in advance rather than after seeing
 results.</td></tr>
<tr><th>Why one per coin</th><td>Rungs are <b>nested, not exclusive</b> — “$84,750 or
 above” and “$84,500 or above” settle on one move. Counting both is one bet counted twice,
 the defect that once read the spot baseline at z +10.40 against a true +0.24.</td></tr>
<tr><th>Liquidity floor</th><td>Two-sided quote, spread ≤
 {S.CRYPTO_FAV_MAX_SPREAD*100:.0f}c, ask size ≥ {S.CRYPTO_FAV_MIN_ASK_SIZE}. One coin
 quoted a single price across fourteen consecutive strikes, which is a stale book rather
 than fourteen prices.</td></tr>
<tr><th>Coins live</th><td>{esc(coins)}</td></tr>
<tr><th>Listed, no open market</th><td class="mut">{esc(dark)}</td></tr>
<tr><th>Judged against</th><td>Backing <b>every</b> in-band rung in the window, so the
 lane only counts if picking the lowest beats the band itself.</td></tr>
<tr><th>Read at</th><td>30 independent outcomes — and an outcome is a <b>day</b>, so about
 six weeks.</td></tr>
</table></div>
<div class="note"><b>What it has to beat.</b> At the taker fee the effective price at
mid-band is <b>0.7632</b>, so the band must beat its own price by about <b>1.3pp</b> just
to break even — roughly the whole size of the favourite-longshot bias anywhere this
Sandbox has measured it. The one direct prior is against it: the spot baseline’s own
0.70–0.80 cell ran <b class="neg">−1.9pp at z −0.17</b> on 10 bets over 8 days.</div>
</section>"""


def unit():
    return """<section id="unit">
<h2>Why a day is one bet</h2>
<div class="note">Both crypto pairs are scored <b>per market-day</b>, not per bet, and that
is measured rather than assumed. Over 90 days of daily closes for the five live coins:</div>
<div class="tbl"><table>
<tr><th>Mean pairwise return correlation</th><td><b>+0.757</b></td></tr>
<tr><th>Mean sign agreement</th><td><b>77.8%</b></td></tr>
<tr><th>Days all five move the same way</th><td><b>54.4%</b></td></tr>
<tr><th>Variance inflation (k=5)</th><td><b>4.03</b></td></tr>
<tr><th>Independent draws in a day</th><td><b>1.24</b>, not 5</td></tr>
<tr><th>z overstatement if keyed per coin</th><td><b class="neg">2.01×</b></td></tr>
</table></div>
<div class="note">A day of “or above” rungs wins or loses together because the coins do, so
the day is the unit. Keying per coin would overstate the evidence by about double, in
exactly the direction that makes a dead lane look alive — which is how the spot baseline
once read z +10.40 against a true +0.24.</div>
</section>"""


def build(d=None, st=None, now=None):
    now = now or datetime.datetime.now(datetime.timezone.utc)
    d = d if d is not None else T.load()
    st = st if st is not None else T.load_stages()
    rows = crypto_rows(d, st)

    lo, hi = S.CRYPTO_FAV_BAND
    band = f"{lo * 100:g}–{hi * 100:g}¢"
    window = f"{S.CRYPTO_FAV_MIN_H:g}–{S.CRYPTO_FAV_MAX_H:g}h"
    liquidity = f"≤{S.CRYPTO_FAV_MAX_SPREAD * 100:g}¢ spread · {S.CRYPTO_FAV_MIN_ASK_SIZE:g}+ ask"
    close = f"{S.CRYPTO_FAV_CLOSE_ET:02d}:00 ET"

    body = f"""{_hero(rows)}
<nav class="crypto-tabs" aria-label="Crypto sections">
<a href="#today">Today</a><a href="#performance">Performance</a><a href="#method">Method</a>
</nav>

<section id="today" class="crypto-section">
<div class="crypto-section-head"><div><span class="crypto-eyebrow">Today’s watch</span><h2>Five live coins</h2></div>
<span class="crypto-rule-chip">{esc(band)} · {esc(window)}</span></div>
<div class="crypto-watch">{_watch_html(d)}</div>
{_scan_status(d, now)}
<div class="crypto-rule-strip">
<div><span>Entry</span><b>Yes ask {esc(band)}</b></div>
<div><span>Selection</span><b>Lowest qualifying rung</b></div>
<div><span>Liquidity</span><b>{esc(liquidity)}</b></div>
<div><span>Close</span><b>{esc(close)}</b></div>
</div>
</section>

<section id="performance" class="crypto-section">
<span id="lanes"></span>
<div class="crypto-section-head"><div><span class="crypto-eyebrow">Performance</span><h2>Favourite-band record</h2></div></div>
{_record_cards(rows)}
<details class="crypto-disclosure">
<summary>Full record table</summary>
<div class="note sm">Counts are <b>market-days</b>, not individual contracts.</div>
{B.sport_sections(d, rows)}
</details>
</section>

<section id="method" class="crypto-section">
<div class="crypto-section-head"><div><span class="crypto-eyebrow">Research notes</span><h2>Method</h2></div></div>
<details class="crypto-disclosure"><summary>The rule under test</summary>{mechanism()}</details>
<details class="crypto-disclosure"><summary>Why a day is one outcome</summary>{unit()}</details>
</section>
<footer>Read-only static export · rebuilt by GitHub Actions · research, not betting advice.</footer>
"""
    return C.document(
        "Edge Machine · Crypto",
        "Crypto favourite-band Analyst Desk: today, performance, and method.",
        "crypto",
        (("today", "Today"), ("performance", "Performance"), ("method", "Method")),
        C.stamp(now),
        body,
        script_src="./site.js",
        scripts=("./tables.js",),
        sports=True,
    )


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
