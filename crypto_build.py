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

    settled = sum(r["a"]["n"] for r in rows)
    prod = sum(1 for r in rows if r.get("prod"))
    open_bets = sum(1 for q in d.get("quotes", [])
                    if q.get("bet") and q.get("status") == "open"
                    and q.get("sport") in SPORTS)
    tiles = "".join(f'<div class="tile"><b>{v:,}</b><span>{k}</span></div>' for k, v in (
        ("pairs with a record", len(rows)),
        ("outcomes settled", settled),
        ("bets running", open_bets),
        ("in Production", prod),
        ("coins live", len(S.COINS)),
    ))

    body = f"""<h1>Crypto</h1>
<p class="lede">One rule and the baseline that motivated it. The baseline asked whether a
forecast could beat assuming nothing changes, and the answer was no. The rule asks a
different question: whether the price itself is biased in the favourite band.</p>
<div class="tiles">{tiles}</div>
{mechanism()}
{unit()}
<section id="lanes">
<h2>Records</h2>
<div class="note">Counts are <b>market-days</b>, the unit above — not individual
contracts.</div>
{B.sport_sections(d, rows)}
</section>
<footer>Read-only static export · rebuilt by GitHub Actions · research, not betting advice.</footer>
"""
    return C.document(
        "Edge Machine · Crypto",
        "The crypto favourite-band rule, the no-change baseline, and why a day is one bet.",
        "crypto",
        (("rule", "The rule under test"), ("unit", "Why a day is one bet"),
         ("lanes", "Records")),
        C.stamp(now),
        body,
        script_src="./site.js",
        scripts=("./tables.js",),
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
