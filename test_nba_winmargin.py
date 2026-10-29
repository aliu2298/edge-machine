#!/usr/bin/env python3
"""Offline checks for the NBA Win margin tracker (nba_winmargin.py) and its NBA page section."""
import datetime as dt
import os
import re
import sys
import tempfile
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

import nba_pace_build as N
import nba_winmargin as W
import nba_winmargin_build as WB
import sandbox_build

FAILS = []
UTC = dt.timezone.utc
ROOT = os.path.dirname(os.path.abspath(__file__))


def check(label, got, want):
    ok = got == want
    print(f"  {'ok  ' if ok else 'FAIL'} {label}" + ("" if ok else f" (got {got!r}, want {want!r})"))
    if not ok:
        FAILS.append(label)


print("tickers")
check("game date from the event suffix", W.game_date("26OCT26GSWDEN"), dt.date(2026, 10, 26))
check("a bad suffix has no date", W.game_date("XXOCT26GSWDEN"), None)
check("home = the last three letters", W.teams_of("26OCT26GSWDEN"), ("GSW", "DEN"))
check("bucket 1-5", W.bucket_of({"ticker": "KXNBAWINMARGIN-26OCT28LALLAC-LAL1TO5"}), ("LAL", "1-5"))
check("bucket 11-20", W.bucket_of({"ticker": "KXNBAWINMARGIN-26OCT28LALLAC-LAC11TO20"}), ("LAC", "11-20"))
check("bucket 21+", W.bucket_of({"ticker": "KXNBAWINMARGIN-26OCT28LALLAC-LAL21PLUS"}), ("LAL", "21+"))
check("bands: 9c, 10c, 19c, 20c", [W.band_of(a) for a in (0.09, 0.10, 0.19, 0.20)], ["5-10c", "10-20c", "10-20c", "20-35c"])
check("sides: 55% favourite, 45% toss-up, 44.9% underdog", [W.side_of(x) for x in (0.55, 0.45, 0.449)],
      ["favourite", "toss-up", "underdog"])

print("population")
check("5c and 35c asks with a 5c spread are in", [W.in_population(dict(bid=a - 0.05, ask=a)) for a in (0.05, 0.35)], [True, True])
check("a 6c spread, a 4c ask and a 36c ask are out",
      [W.in_population(dict(bid=b, ask=a)) for b, a in ((0.10, 0.16), (0.01, 0.04), (0.33, 0.36))], [False, False, False])
check("no quote is out", W.in_population(dict(bid=None, ask=None)), False)

print("metrics from trade prints")
TIP = 1_000_000
ENTRY = TIP - 3600
tr = [(ENTRY - 60, 0.50, 99),          # before the entry: ignored
      (ENTRY + 60, 0.10, 5),
      (TIP + 600, 0.20, 10),           # first 2x, 10 min after the tip
      (TIP + 900, 0.25, 4),
      (TIP + 1800, 0.12, 1),           # back under 2x
      (TIP + 2400, 0.31, 2)]           # last print, at 3.1x: holds one minute
m = W.metrics(tr, 0.10, TIP, ENTRY)
check("peak is the highest print after the entry / the ask", m["peak"], 3.1)
check("reached 2x and 3x, not 5x", (m["r2"], m["r3"], m["r5"]), (True, True, False))
check("first 2x in minutes from the tip", m["first2"], 10.0)
check("minutes at 2x+ is a step function (5 + 15 + 1)", m["above2"], 21.0)
check("contracts at 2x+", m["vol2"], 16.0)
check("prints counted from the entry", m["prints"], 5)
check("3x and 5x are not possible from a 34c ask", W.metrics([(TIP, 0.9, 1)], 0.34, TIP, ENTRY)["r3"], None)
check("a print before the tip at 2x counts with a negative minute",
      W.metrics([(TIP - 600, 0.2, 1)], 0.1, TIP, ENTRY)["first2"], -10.0)
check("no print after the entry is no metrics", W.metrics([(ENTRY - 1, 0.2, 1)], 0.1, TIP, ENTRY), None)
check("path: highest print per minute, from the entry", W.path_of(tr, TIP, ENTRY)[:2], [[-59, 10], [10, 20]])

print("entry quote and win share")
cs = {"market_tickers": ["A", "B"], "market_candlesticks": [
    [dict(end_period_ts=ENTRY - 120, yes_bid=dict(close_dollars="0.10"), yes_ask=dict(close_dollars="0.13")),
     dict(end_period_ts=ENTRY, yes_bid=dict(close_dollars="0.11"), yes_ask=dict(close_dollars="0.14")),
     dict(end_period_ts=ENTRY + 60, yes_bid=dict(close_dollars="0.50"), yes_ask=dict(close_dollars="0.60"))],
    [dict(end_period_ts=ENTRY + 60, yes_bid=dict(close_dollars="0.2"), yes_ask=dict(close_dollars="0.3"))]]}
check("the last candle ending at or before the entry; none later", W.entry_quotes(cs, ENTRY), {"A": (0.11, 0.14)})
sh = W.shares([dict(team="X", bid=0.2, ask=0.3), dict(team="X", bid=0.1, ask=0.1), dict(team="Y", bid=0.2, ask=0.2),
               dict(team="Y", bid=None, ask=None)])
check("win share: bucket mids summed per team, normalised", sh, {"X": 0.6364, "Y": 0.3636})

print("a game from a fake Kalshi")


def fake(path):
    if path.startswith("events?"):
        return {"events": [{"event_ticker": "KXNBAWINMARGIN-26OCT26GSWDEN"},
                           {"event_ticker": "KXNBAWINMARGIN-26OCT10GSWDEN"}]}     # preseason: skipped
    if path.startswith("markets?event_ticker=KXNBAGAME-"):
        return {"markets": [{"expected_expiration_time": "2026-10-27T05:00:00Z"}]}
    if path.startswith("markets?event_ticker=KXNBAWINMARGIN-"):
        ms = []
        for t in ("GSW", "DEN"):
            for b in ("1TO5", "6TO10", "11TO20", "21PLUS"):
                ms.append(dict(ticker=f"KXNBAWINMARGIN-26OCT26GSWDEN-{t}{b}", yes_sub_title=f"{t} wins by {b}",
                               status="finalized", result="yes" if t + b == "DEN1TO5" else "no"))
        return {"markets": ms}
    if "/candlesticks" in path:
        tks = [f"KXNBAWINMARGIN-26OCT26GSWDEN-{t}{b}" for t in ("GSW", "DEN") for b in ("1TO5", "6TO10", "11TO20", "21PLUS")]
        e = int(dt.datetime(2026, 10, 27, 1, tzinfo=UTC).timestamp())
        q = {"GSW": (0.08, 0.10), "DEN": (0.15, 0.17)}
        return {"market_tickers": tks, "market_candlesticks": [
            [dict(end_period_ts=e - 60, yes_bid=dict(close_dollars=str(q[W.bucket_of({"ticker": t})[0]][0])),
                  yes_ask=dict(close_dollars=str(q[W.bucket_of({"ticker": t})[0]][1])))] for t in tks]}
    if path.startswith("markets/trades?"):
        assert "min_ts=" in path
        if "DEN1TO5" in path:
            return {"trades": [dict(created_time="2026-10-27T02:20:00Z", yes_price_dollars="0.40", count_fp="7"),
                               dict(created_time="2026-10-27T02:40:00Z", yes_price_dollars="0.20", count_fp="1")]}
        return {"trades": []}
    raise AssertionError(path)


st = W.empty()
new = W.run(st, now=dt.datetime(2026, 10, 27, 12, tzinfo=UTC), fetch=fake)
check("no error on the fake run", st["error"], None)
check("only regular-season games are tracked", new, ["KXNBAWINMARGIN-26OCT26GSWDEN"])
g = st["games"]["KXNBAWINMARGIN-26OCT26GSWDEN"]
check("tip = KXNBAGAME expected expiration - 3h", g["tip"], "2026-10-27T02:00:00+00:00")
check("home and away from the suffix", (g["home"], g["away"], g["night"]), ("DEN", "GSW", "2026-10-26"))
check("eight buckets, final, stamped", (len(g["rows"]), g["final"], g["version"]), (8, True, W.VERSION))
den = next(r for r in g["rows"] if r["ticker"].endswith("DEN1TO5"))
check("DEN 1-5: entry ask, home, favourite, 10-20c band, in the population",
      (den["ask"], den["home"], den["side"], den["band"], den["pop"]), (0.17, True, "favourite", "10-20c", True))
check("DEN 1-5 reached 2x at +20 min, held 20 min, won (+83c)",
      (den["m"]["r2"], den["m"]["first2"], den["m"]["above2"], den["won_minus_ask"]), (True, 20.0, 20.0, 0.83))
check("a contract with no print after the entry has no metrics",
      next(r for r in g["rows"] if r["ticker"].endswith("GSW1TO5"))["m"], None)
check("a second run adds nothing", W.run(st, now=dt.datetime(2026, 10, 27, 13, tzinfo=UTC), fetch=fake), [])

print("save and load")
with tempfile.TemporaryDirectory() as d:
    p = os.path.join(d, "x.json")
    W.save(st, p)
    check("the ledger round-trips", W.load(p), st)

print("summaries")


def prow(night, bucket, ask, r2, above2, won, side="favourite", band="10-20c"):
    return dict(night=night, tip=night + "T23:00:00+00:00", bucket=bucket, ask=ask, side=side, band=band, pop=True,
                result="yes" if won else "no", won_minus_ask=(1 if won else 0) - ask, team="X",
                m=dict(peak=2.5 if r2 else 1.2, r2=r2, r3=False, r5=False, first2=30.0 if r2 else None,
                       above2=above2, vol2=50.0 if r2 else 0.0, prints=3))


rows = [prow("2026-10-20", "1-5", 0.10, True, 12, False), prow("2026-10-21", "1-5", 0.20, False, 0, True),
        prow("2026-10-22", "1-5", 0.10, True, 5, False), prow("2026-10-23", "1-5", 0.20, True, 40, False)]
s = W.stats(rows)
check("n, reached 2x, held 10+ min", (s["n"], s["r2"], s["held10"]), (4, 0.75, 0.5))
check("medians over the contracts that reached 2x", (s["first2"], s["above2"], s["vol2"]), (30.0, 12, 50.0))
check("won - ask is the average", round(s["won_minus_ask"], 4), round((1 - 0.6) / 4, 4))
check("halves: older first, the odd row to the newer half", [len(x) for x in W.halves(rows[:3])], [1, 2])

print("the page section")
html = sandbox_build.label_cells(WB.section(st))
check("observation-only wording", "Observation only — no buying or selling rule yet." in html, True)
check("three summary tables with the fair rates in the header",
      html.count("Reached 2x (fair 50%)") >= 3 and "Reached 3x (fair 33%)" in html and "Reached 5x (fair 20%)" in html, True)
check("last night's game is listed", "GSW @ DEN" in html and "DEN by 1-5" in html and "17c → 40c (2.4x)" in html, True)
check("every summary cell is named for the phone cards", 'data-l="Reached 2x (fair 50%)"' in html, True)
check("an empty ledger still renders", "No settled game in the tracker yet." in WB.section(W.empty()), True)

page = N.build({"window": 5, "games": [], "seed": {"teams": {}}}, dt.datetime(2026, 10, 29, 12, tzinfo=UTC))
order = [page.find(f'<section id="{i}"') for i in ("cheap-side", "winmargin", "safe-card", "matchups", "retired")]
check("the section sits under the cheap-side card and above the Safe Card", all(x >= 0 for x in order) and order == sorted(order), True)
check("nothing between the cheap side and the tracker",
      page[page.index('<section id="cheap-side"'):page.index('<section id="winmargin"')].count("<section id="), 1)
check("the page nav names it", '<a href="#winmargin">Win margin</a>' in page, True)
check("no inline SVG on the NBA page", "<svg" not in page, True)


def browser_checks():
    print("\nbrowser")
    from require_browser import require_browser
    sync_playwright = require_browser("test_nba_winmargin.py")
    if sync_playwright is None:
        return
    folder = tempfile.mkdtemp(prefix="nba-winmargin-")
    for name in ("site.css", "tables.js", "sports.js"):
        os.symlink(os.path.join(ROOT, "public_site", name), os.path.join(folder, name))
    # The real ledger when it is there (the widest numbers), else the fake game.
    real = W.load() if os.path.exists(W.PATH) else st
    built = N.build({"window": 5, "games": [], "seed": {"teams": {}}}, dt.datetime(2026, 10, 29, 12, tzinfo=UTC))
    built = re.sub(r'<section id="winmargin">.*?</section>', lambda _: sandbox_build.label_cells(WB.section(real)),
                   built, count=1, flags=re.S)
    with open(os.path.join(folder, "nba.html"), "w", encoding="utf-8") as fh:
        fh.write(built)

    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *a, **k):
            super().__init__(*a, directory=folder, **k)

        def log_message(self, *a):
            return

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(channel="chrome", headless=True)
            page_ = browser.new_page(viewport={"width": 1280, "height": 800})
            page_.goto(f"http://127.0.0.1:{httpd.server_address[1]}/nba.html", wait_until="load")
            for width in (320, 375, 1280):
                page_.set_viewport_size({"width": width, "height": 800})
                page_.wait_for_timeout(40)
                for sel in ("#winmargin details",):
                    for d in page_.locator(sel).all():
                        d.evaluate("d => d.open = true")
                page_.wait_for_timeout(40)
                over = page_.evaluate("document.documentElement.scrollWidth > document.documentElement.clientWidth + 1")
                check(f"no sideways scroll at {width}px with every tracker fold open", over, False)
                vis = page_.locator("#winmargin h2").is_visible()
                check(f"the tracker heading shows at {width}px", vis, True)
            browser.close()
    finally:
        httpd.shutdown()


browser_checks()

print()
if FAILS:
    print(f"{len(FAILS)} FAILED")
    sys.exit(1)
print("PASS nba win margin tracker")
