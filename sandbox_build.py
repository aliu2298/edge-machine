"""Renders the Sandbox Tracker ledger into public_site/sandbox.html.

Pure presentation — it reads the ledger and writes a page, and never fetches or grades.
That split is deliberate: the page can always be rebuilt from the ledger, so a rendering
bug can never cost a settled result.
"""

import html
import json
import os
import sys
from datetime import datetime, timezone

import sandbox_sources as S
import sandbox_track as T

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "public_site", "sandbox.html")

# Below this many settled bets, ROI is noise dressed as a finding. Three lanes in this
# repo have already died from a rate being read without the sample behind it, so the
# board refuses to call a winner until the number can carry the claim.
MIN_N = 30


def esc(x):
    return html.escape(str(x))


def pct(x, digits=1, sign=False):
    if x is None:
        return "—"
    return f"{x*100:+.{digits}f}%" if sign else f"{x*100:.{digits}f}%"


def money(x):
    if x is None:
        return "—"
    return f"{'+' if x >= 0 else '−'}${abs(x):,.0f}"


def cls(x):
    return "pos" if (x or 0) > 0 else ("neg" if (x or 0) < 0 else "mut")


def leaderboard(scores):
    rows = []
    for name, s in sorted(scores.items(),
                          key=lambda kv: (kv[1]["connected"], kv[1]["settled"]), reverse=True):
        if not s["connected"]:
            continue
        thin = s["settled"] < MIN_N
        roi = (f'<span class="{cls(s["roi"])}">{pct(s["roi"], sign=True)}</span>'
               if s["roi"] is not None and not thin
               else f'<span class="mut">{pct(s["roi"], sign=True)}</span>')
        verdict = ('<span class="sig n">NO READ</span>' if thin else
                   '<span class="sig y">PROFITABLE</span>' if (s["roi"] or 0) > 0 else
                   '<span class="st miss">LOSING</span>')
        rows.append(f"""<tr>
<td><b>{esc(s['label'])}</b><div class="mut sm">{esc(s['kind'])} · {esc(s['site'])}</div></td>
<td class="num">{s['quotes']:,}</td><td class="num">{s['bets']:,}</td>
<td class="num">{s['settled']:,}</td>
<td class="num">{pct(s['hit']) if s['hit'] is not None else '—'}</td>
<td class="num">{roi}</td>
<td class="num {cls(s['pnl'])}">{money(s['pnl']) if s['settled'] else '—'}</td>
<td class="num">{f"{s['brier']:.4f}" if s['brier'] is not None else '—'}</td>
<td>{verdict}</td></tr>""")
    return "\n".join(rows)


def coverage_table(cov):
    """Sport x source grid of what each feed actually returned on the last run."""
    names = [n for n, m in S.SOURCES.items() if m["connected"]]
    head = "".join(f'<th class="num">{esc(S.SOURCES[n]["label"].split(" (")[0])}</th>'
                   for n in names)
    rows = []
    for sport, label in S.SPORTS.items():
        cells = []
        for n in names:
            v = (cov.get(sport) or {}).get(n)
            if sport not in S.SOURCES[n]["sports"]:
                cells.append('<td class="num mut">n/a</td>')
            elif v is None:
                cells.append('<td class="num neg">—</td>')
            elif v == 0:
                cells.append('<td class="num neg">0</td>')
            else:
                cells.append(f'<td class="num pos">{v:,}</td>')
        rows.append(f"<tr><td><b>{esc(label)}</b></td>{''.join(cells)}</tr>")
    return f"""<div class="tbl"><table>
<tr><th>Sport</th>{head}</tr>
{''.join(rows)}</table></div>"""


def polymarket_panel(d):
    """Answers the question the board was commissioned to answer: does Polymarket
    actually carry these six sports, and is anything trading in them?

    Reads the last run's coverage counts rather than the ledger, because placeholder
    books are deliberately never logged — the ledger knows how many contests are PRICED,
    only the coverage snapshot still knows how many are listed.
    """
    cov = d.get("coverage") or {}
    rows = []
    for sport, label in S.SPORTS.items():
        c = cov.get(sport) or {}
        listed = c.get("polymarket_listed")
        traded = c.get("polymarket_priced", c.get("polymarket"))
        if listed is None:
            rows.append(f"""<tr><td><b>{esc(label)}</b></td><td class="num mut">—</td>
<td class="num mut">—</td><td><span class="sig n">NOT YET CHECKED</span></td>
<td class="mut">no run has covered this sport yet</td></tr>""")
            continue
        # Ratio, not just count. Table tennis lists hundreds of contests of which a
        # handful are priced — counting only the absolute number called that "deep,
        # actively priced", which is the opposite of what the book actually is.
        share = (traded / listed) if listed else 0.0
        if not listed:
            state, note = ('<span class="st miss">NONE SEEN</span>',
                           "no head-to-head market found")
        elif not traded:
            state, note = ('<span class="sig n">LISTED, NOT TRADED</span>',
                           "every market sits at an untouched 50/50")
        elif share < 0.25:
            state, note = ('<span class="sig n">MOSTLY PLACEHOLDER</span>',
                           f"listed in bulk, but only {share*100:.0f}% carries a real price")
        elif traded < 10:
            state, note = ('<span class="sig n">THIN</span>',
                           "a real book, but only a handful of contests")
        else:
            state, note = ('<span class="sig y">LIVE</span>',
                           "a deep, actively priced book")
        rows.append(f"""<tr><td><b>{esc(label)}</b></td>
<td class="num">{listed:,}</td><td class="num">{traded:,}</td>
<td>{state}</td><td class="mut">{esc(note)}</td></tr>""")
    return f"""<div class="tbl"><table>
<tr><th>Sport</th><th class="num">Listed</th><th class="num">Actually priced</th>
<th>Status</th><th>Reading</th></tr>
{''.join(rows)}</table></div>"""


def open_rows(d, limit=25):
    live = [q for q in d["quotes"] if q["status"] == "open" and q["bet"]]
    live.sort(key=lambda q: q["start"])
    out = []
    for q in live[:limit]:
        side = q["side_a"] if q["pick"] == "a" else q["side_b"]
        out.append(f"""<tr><td class="mut">{esc(q['date'])}</td>
<td>{esc(S.SPORTS[q['sport']])}</td>
<td><a href="{esc(q['url'])}" target="_blank" rel="noopener">{esc(q['label'])}</a></td>
<td>{esc(S.SOURCES[q['source']]['label'].split(' (')[0])}</td>
<td><b>{esc(side)}</b></td>
<td class="num">{q['price']:.2f}</td>
<td class="num pos">{pct(q['edge'], sign=True) if q.get('edge') is not None else '<span class="mut">pick</span>'}</td></tr>""")
    return "\n".join(out), len(live)


def settled_rows(d, limit=40):
    done = [q for q in d["quotes"] if q["status"] in ("won", "lost", "void") and q["bet"]]
    done.sort(key=lambda q: q.get("settled") or "", reverse=True)
    out = []
    for q in done[:limit]:
        side = q["side_a"] if q["pick"] == "a" else q["side_b"]
        out.append(f"""<tr><td class="mut">{esc(q['date'])}</td>
<td>{esc(S.SPORTS[q['sport']])}</td><td>{esc(q['label'])}</td>
<td>{esc(S.SOURCES[q['source']]['label'].split(' (')[0])}</td>
<td>{esc(side)}</td><td class="num">{q['price']:.2f}</td>
<td><span class="st {q['status']}">{q['status'].upper()}</span></td>
<td class="num {cls(q['pnl'])}">{money(q['pnl'])}</td></tr>""")
    return "\n".join(out), len(done)


def unconnected_rows():
    out = []
    for name, m in S.SOURCES.items():
        if m["connected"]:
            continue
        out.append(f"""<tr><td><b>{esc(m['label'])}</b>
<div class="mut sm">{esc(m['kind'])} · {esc(m['site'])}</div></td>
<td class="mut">{esc(m['note'])}</td></tr>""")
    return "\n".join(out)


def build():
    d = T.load()
    scores = T.score(d)
    cov = d.get("coverage") or {}
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    quotes = len(d["quotes"])
    bets = sum(1 for q in d["quotes"] if q["bet"])
    settled = sum(1 for q in d["quotes"] if q["status"] in ("won", "lost"))
    pnl = sum(q["pnl"] for q in d["quotes"] if q["status"] in ("won", "lost"))
    staked = sum(q["stake"] for q in d["quotes"] if q["status"] in ("won", "lost"))
    live_rows, n_live = open_rows(d)
    hist_rows, n_hist = settled_rows(d)

    verdict = ("Nothing is settled yet, so no source has a record. The first fixtures "
               "settle within a day of the first run."
               if settled == 0 else
               f"{settled:,} settled bets so far. "
               + ("Still under the {n} needed before any ROI here means anything."
                  .format(n=MIN_N) if settled < MIN_N else
                  "Past the {n}-bet floor — the ROI column is now readable."
                  .format(n=MIN_N)))

    return f"""<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Sandbox Tracker</title>
<meta name="description" content="Which sports prediction sources actually make money, tracked at real prices across six sports.">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<style>
:root{{--bg:#0a0d14;--card:#10141d;--bd:#232936;--fg:#eef2f7;--mut:#8b94a7;
--pos:#3fb970;--neg:#e06c75;--warn:#f0b429;--acc:#7aa2f7}}
*{{box-sizing:border-box;margin:0}}
body{{background:var(--bg);color:var(--fg);font:15px/1.45 Inter,system-ui,sans-serif;
letter-spacing:-.011em;-webkit-font-smoothing:antialiased;padding:28px 16px 60px}}
.wrap{{max-width:1040px;margin:0 auto}}
h1{{font-size:22px;font-weight:800;letter-spacing:-.02em}}
h2{{font-size:13px;font-weight:700;text-transform:uppercase;letter-spacing:.08em;
color:var(--mut);margin:34px 0 12px}}
.sub{{color:var(--mut);font-size:13px;margin-top:4px}}
.sm{{font-size:11px}}
.mut{{color:var(--mut)}}.pos{{color:var(--pos)}}.neg{{color:var(--neg)}}
a{{color:var(--acc);text-decoration:none}}a:hover{{text-decoration:underline}}
.nav{{display:flex;gap:8px;margin-top:14px;flex-wrap:wrap}}
.nav a{{font-size:12px;font-weight:700;text-decoration:none;color:var(--mut);
border:1px solid var(--bd);border-radius:999px;padding:5px 13px}}
.nav a:hover{{color:var(--fg);border-color:var(--mut)}}
.nav a.on{{color:var(--fg);border-color:var(--mut);background:#161b26}}
.note{{font-size:12.5px;color:var(--mut);line-height:1.6;background:var(--card);
border:1px solid var(--bd);border-radius:10px;padding:12px 14px;margin-bottom:12px}}
.note b{{color:var(--fg);font-weight:600}}
.note.warn{{border-color:#f0b42944;background:#f0b4290a}}
.tiles{{display:flex;gap:9px;flex-wrap:wrap;margin-bottom:13px}}
.tile{{flex:1;min-width:112px;background:var(--card);border:1px solid var(--bd);
border-radius:10px;padding:11px 13px}}
.tile b{{display:block;font-size:19px;font-weight:800;font-variant-numeric:tabular-nums}}
.tile span{{font-size:11px;color:var(--mut)}}
.tbl{{background:var(--card);border:1px solid var(--bd);border-radius:11px;
overflow-x:auto;margin-bottom:13px}}
table{{width:100%;border-collapse:collapse;font-size:12.5px}}
th{{text-align:left;font-size:10px;text-transform:uppercase;letter-spacing:.07em;
color:var(--mut);padding:9px 11px;border-bottom:1px solid var(--bd);white-space:nowrap}}
td{{padding:9px 11px;border-bottom:1px solid #1a1f2b;vertical-align:top}}
tr:last-child td{{border-bottom:none}}
.num{{font-variant-numeric:tabular-nums;text-align:right;white-space:nowrap}}
.st,.sig{{display:inline-block;font-size:9.5px;font-weight:800;letter-spacing:.05em;
border-radius:999px;padding:2px 7px;border:1px solid;white-space:nowrap}}
.st.won,.sig.y{{color:var(--pos);border-color:#3fb97055;background:#3fb97014}}
.st.lost,.st.miss{{color:var(--neg);border-color:#e06c7555;background:#e06c7514}}
.st.void,.sig.n{{color:var(--mut);border-color:var(--bd)}}
footer{{margin-top:40px;font-size:12px;color:var(--mut);text-align:center}}
@media (max-width:600px){{body{{padding:18px 10px 44px;font-size:14px}}h1{{font-size:19px}}}}
</style></head><body><div class="wrap">

<h1>Sandbox Tracker</h1>
<div class="sub">Which prediction source actually makes money · six sports · updated {esc(now)}</div>
<div class="nav"><a href="./">Picks</a><a href="./leads.html">Leads</a>
<a href="./streaks.html">Streaks</a><a href="./record.html">Record</a>
<a href="./today.html">Today</a><a class="on" href="./sandbox.html">Sandbox</a></div>

<div class="note warn">Every source here is logged <b>before the contest starts</b> and
stamped with the <b>price that existed at that moment</b>, then settled for real when the
market resolves. Two kinds of source are tracked and they are staked differently.
<b>Tipsters</b> name a side: that side is backed at the going price, every time, because
that is how a tipster is actually followed — high turnover, no Brier score, and a real
ROI. <b>Models, books and exchanges</b> state a probability: they are backed only when
they disagree with the price by {int(T.EDGE_MIN*100)}pp or more, and they also get an
accuracy score. Everything is flat ${int(T.STAKE)} a bet, so nothing here is bet-sizing
skill. {esc(verdict)}</div>

<div class="tiles">
<div class="tile"><b>{quotes:,}</b><span>predictions logged</span></div>
<div class="tile"><b>{bets:,}</b><span>bets placed</span></div>
<div class="tile"><b>{settled:,}</b><span>settled</span></div>
<div class="tile"><b class="{cls(pnl)}">{money(pnl) if settled else '—'}</b><span>net P/L</span></div>
<div class="tile"><b class="{cls(pnl)}">{pct(pnl/staked, sign=True) if staked else '—'}</b><span>ROI on turnover</span></div>
<div class="tile"><b>{n_live:,}</b><span>bets running</span></div>
</div>

<h2>Which source is profitable?</h2>
<div class="tbl"><table>
<tr><th>Source</th><th class="num">Logged</th><th class="num">Bets</th>
<th class="num">Settled</th><th class="num">Hit</th><th class="num">ROI</th>
<th class="num">P/L</th><th class="num">Brier</th><th>Verdict</th></tr>
{leaderboard(scores)}
</table></div>
<div class="note"><b>ROI</b> is profit over everything staked, at the price actually
available. <b>Brier</b> scores raw accuracy on every logged probability, bet or not —
lower is better, 0.25 is a coin flip — and it is the more honest column early on, because
it uses every prediction instead of only the small slice that cleared the edge threshold.
A blank Brier is not a
gap in the data: a tipster names a side and states no probability, so there is nothing to
calibrate and the column is left empty rather than filled with a 0/1 stand-in.
<b>Polymarket cannot win this table.</b> Its own price is the price everything is
measured against, so its ROI is blank by construction; it is here as the accuracy bar and
as the control that proves the ledger is wired up correctly.<br><br>
<b>Turnover is not comparable across kinds.</b> A tipster bets every game it calls and a
model bets only where it disagrees with the market, so the tipster will always show far
more bets. Compare them on ROI, never on P/L.</div>

<h2>Does Polymarket really cover these sports?</h2>
{polymarket_panel(d)}
<div class="note">Counted live from Polymarket's public gamma API on the last run, not
from documentation. <b>Listed</b> counts pre-match head-to-head markets — the moneyline
only; inning props, handicaps and over/unders are excluded, and so are season-long
futures. <b>Actually priced</b> drops the ones still sitting at an untouched 50/50, which
is the difference between a market existing and a market meaning something. All six
sports are present; the two that are thin are thin in different ways, and only this
column tells them apart. Tracking then takes the <b>{S.MAX_PER_SPORT} deepest books per sport per
run</b> — the shallow end of a 300-contest table-tennis list is quoted prices nobody has
tested, and carrying it would bloat the ledger without sharpening a single verdict.</div>

<h2>Source coverage, last run</h2>
{coverage_table(cov)}
<div class="note">What each feed returned on the most recent run, after matching to a
contest. <b>This row is the smoke alarm.</b> A source that has quietly broken and a
source that simply has no edge produce the same empty leaderboard, so a red
<span class="neg">0</span> where a number is expected means the feed is down — not that
the source is uninterested.</div>

<h2>Running now ({n_live:,})</h2>
{f'<div class="tbl"><table><tr><th>Date</th><th>Sport</th><th>Contest</th><th>Source</th><th>Backing</th><th class="num">Price</th><th class="num">Edge</th></tr>{live_rows}</table></div>' if n_live else '<div class="note">No open bets — no source currently disagrees with the market by enough to act on.</div>'}

<h2>Settled ({n_hist:,})</h2>
{f'<div class="tbl"><table><tr><th>Date</th><th>Sport</th><th>Contest</th><th>Source</th><th>Backed</th><th class="num">Price</th><th></th><th class="num">P/L</th></tr>{hist_rows}</table></div>' if n_hist else '<div class="note">Nothing settled yet. Bets settle when Polymarket resolves the market, usually within hours of the contest finishing.</div>'}

<h2>Declared but not connected</h2>
<div class="tbl"><table>
<tr><th>Source</th><th>Why it is not scored</th></tr>
{unconnected_rows()}
</table></div>
<div class="note">These are listed rather than dropped so the roster stays honest: a
source missing from a board is indistinguishable from a source with nothing to say.
Adding one is a single function returning <code>{{a, b, pick}}</code> or
<code>{{a, b, prob_a}}</code> per contest; the matching, staking, settling and scoring
are already shared. Cloudflare is no longer a blocker either — Scores24 is fetched
through a real headless browser, and any other site behind the same wall can reuse
that step.</div>

<h2>Method</h2>
<div class="note">
<b>Universe.</b> Every pre-match head-to-head market Polymarket lists across the six
sports. Polymarket is the spine because it is the only feed that covers all six, carries
a tradeable price, and resolves itself — which also makes it the settlement oracle for
boxing and table tennis, where ESPN has no data at all.<br><br>
<b>Logging.</b> One quote per source per contest, taken the first time that contest is
seen and never revised. Re-quoting as the price drifts would let a source keep whichever
version of its opinion aged well.<br><br>
<b>Betting.</b> Flat ${int(T.STAKE)}, no staking plan, only when the source disagrees with
the price by {int(T.EDGE_MIN*100)}pp or more and the price sits between
{T.PRICE_FLOOR:.2f} and {T.PRICE_CEIL:.2f}. Longshots are still scored for accuracy but
never backed: at 0.02 one fluke pays 50x and would own the board.<br><br>
<b>Settlement.</b> Polymarket's own resolution. A market that closes without a clean
outcome is voided at zero, never guessed.<br><br>
<b>What would falsify a source.</b> A positive ROI over fewer than {MIN_N} settled bets
is not a finding, and the board says NO READ until it clears that. Beating the market's
price is the only test that counts here — a high hit rate on heavy favourites is not an
edge, it is just backing the favourite.
</div>

<footer>Read-only static export · rebuilt by GitHub Actions · research, not betting advice.</footer>
</div></body></html>"""


def main():
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as f:
        f.write(build())
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
