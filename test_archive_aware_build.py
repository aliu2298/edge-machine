#!/usr/bin/env python3
"""Settled and void counts survive a monthly roll-up.

The fixture ledger is built in memory. Nothing here reads data/, the live
ledger, or the network. A roll-up moves settled bets (and, in the #47 shape,
voids) into `_archive`. The headline, the void count, per-lane P/L and ROI,
and the weekly archive pages must be the same after that move.

Two archive shapes are checked. Today's prune copies won, lost, and
settled+price bets. The later shape copies every bet, voids included.
Compact price rows are not bets and must not be counted.
"""
import copy
import datetime
import re
import sys
from datetime import timezone

import production
import sandbox_build as SB
import sandbox_sources as S
import sandbox_track as T
import sport_tab

FAILS = []
# Noon UTC on 4 Oct 2026. Chicago is CDT (UTC-5). The recent window is the
# seven Chicago dates 28 Sep through 4 Oct.
NOW = datetime.datetime(2026, 10, 4, 12, 0, tzinfo=timezone.utc)


def _refuse(*_a, **_k):
    raise AssertionError("this test must not read the live ledger or the archive files")


T.load = _refuse
T.load_stages = _refuse
T.load_archive = _refuse


def ok(cond, why):
    print(f"  {'ok  ' if cond else 'FAIL'} {why}")
    if not cond:
        FAILS.append(why)


def eq(got, want, why):
    if got == want:
        ok(True, why)
        return
    if isinstance(got, str) and isinstance(want, str) and max(len(got), len(want)) > 400:
        ok(False, f"{why} — {len(got)} bytes vs {len(want)} bytes")
        return
    if isinstance(got, dict) and isinstance(want, dict):
        diffs = [k for k in sorted(set(got) | set(want)) if got.get(k) != want.get(k)]
        ok(False, f"{why} — differs in {diffs}")
        return
    ok(False, f"{why} — got {got!r}, want {want!r}")


def _bet(**kw):
    row = dict(
        bet=True, source="espn_fpi", sport="nfl", venue="polymarket_us",
        pick="a", side_a="Home", side_b="Away", price=0.55, stake=100.0,
        result="a", pnl=81.82, label="Home v Away", url="",
        price_a=0.55, price_b=0.45,
    )
    row.update(kw)
    return row


def _ledger():
    """Quotes hold the live bets. The archive holds one bet that has already
    left the ledger, and one compact price row. A duplicate id is checked on
    its own, so this roll-up moves each bet once."""
    recent_won = _bet(
        id="recent-won", status="won",
        settled="2026-10-02T18:00:00+00:00", logged="2026-10-01T18:00:00+00:00",
        start="2026-10-02T17:00:00+00:00", market_id="m-recent-won",
        close_price=0.50, close_at="2026-10-02T16:30:00+00:00")
    dup = _bet(
        id="dup", status="won",
        settled="2026-09-15T18:00:00+00:00", logged="2026-09-14T18:00:00+00:00",
        start="2026-09-15T17:00:00+00:00", market_id="m-dup")
    quotes = [
        recent_won,
        _bet(id="recent-void", status="void", result=None, pnl=0.0, price=0.40,
             settled="2026-10-01T18:00:00+00:00", logged="2026-09-30T18:00:00+00:00",
             start="2026-10-01T17:00:00+00:00", market_id="m-recent-void"),
        _bet(id="old-won", status="won",
             settled="2026-09-10T18:00:00+00:00", logged="2026-09-09T18:00:00+00:00",
             start="2026-09-10T17:00:00+00:00", market_id="m-old-won"),
        _bet(id="old-lost", status="lost", result="b", pnl=-100.0, price=0.45,
             price_a=0.45, price_b=0.55,
             settled="2026-09-18T18:00:00+00:00", logged="2026-09-17T18:00:00+00:00",
             start="2026-09-18T17:00:00+00:00", market_id="m-old-lost"),
        _bet(id="old-void", status="void", result=None, pnl=0.0,
             settled="2026-09-20T18:00:00+00:00", logged="2026-09-19T18:00:00+00:00",
             start="2026-09-20T17:00:00+00:00", market_id="m-old-void"),
        _bet(id="old-price", status="settled", result="price", pnl=12.5, price=0.50,
             settle_px=0.62,
             settled="2026-09-12T18:00:00+00:00", logged="2026-09-11T18:00:00+00:00",
             start="2026-09-12T17:00:00+00:00", market_id="m-old-price"),
        _bet(id="open-bet", status="open", result=None, pnl=None, settled=None,
             logged="2026-10-03T18:00:00+00:00", start="2026-10-05T17:00:00+00:00",
             market_id="m-open"),
        dup,
        _bet(id="removed", source="olbg", sport="boxing", status="won",
             settled="2026-09-11T18:00:00+00:00", logged="2026-09-10T18:00:00+00:00",
             start="2026-09-11T17:00:00+00:00", market_id="m-removed"),
        _bet(id="refused", source="tennis_fav_band_3h", sport="tennis", tier="wta",
             status="won", market_id="aec-wta-refused",
             settled="2026-09-11T18:00:00+00:00", logged="2026-09-10T18:00:00+00:00",
             start="2026-09-11T17:00:00+00:00"),
        _bet(id="tennis-kept", source="tennis_fav_band_3h", sport="tennis", tier="atp",
             status="won", market_id="atp-kept-1",
             settled="2026-09-16T18:00:00+00:00", logged="2026-09-15T18:00:00+00:00",
             start="2026-09-16T17:00:00+00:00"),
        _bet(id="cu-won", source="corners_under", sport="soccer_corners", status="won",
             venue="kalshi_binary",
             settled="2026-09-09T18:00:00+00:00", logged="2026-09-08T18:00:00+00:00",
             start="2026-09-09T17:00:00+00:00", market_id="m-cu-won"),
        _bet(id="odd-void", source="oddspedia", sport="cricket", status="void",
             result=None, pnl=0.0,
             settled="2026-09-19T18:00:00+00:00", logged="2026-09-18T18:00:00+00:00",
             start="2026-09-19T17:00:00+00:00", market_id="m-odd-void"),
    ]
    already = _bet(
        id="already-archived", status="won",
        settled="2026-09-08T18:00:00+00:00", logged="2026-09-07T18:00:00+00:00",
        start="2026-09-08T17:00:00+00:00", market_id="m-already")
    compact = dict(
        id="compact-price", bet=False, compact=True, source="polymarket", sport="tennis",
        status="graded", result="a", price_a=0.40, price_b=0.60, market_id="compact-market",
        venue="polymarket", logged="2026-09-01T12:00:00+00:00",
        settled="2026-09-02T12:00:00+00:00")
    return {
        "quotes": quotes,
        "_archive": [already, compact],
        "meta": {},
        "coverage": {},
        "retired": {},
    }


ST = {
    "pairs": {
        "espn_fpi|nfl": {
            "stage": "production",
            "ready_at": "2026-09-01T00:00:00+00:00",
            "promoted_at": "2026-09-01T00:00:00+00:00",
            "by_hand": "2026-09-01",
            "since": None,
        },
    },
    "events": [],
}
BLOB = {
    "leads": {},
    "pairs": {"espn_fpi|nfl": {}},
    "unlisted_skipped": 0,
    "unverified_kickoff_skipped": 0,
}


def _rollup(d, voids):
    """Move settled bets into the archive. Voids move only in the #47 shape.

    A removed row stays, the way prune() leaves it. An id already archived is
    dropped from the quotes without a second copy.
    """
    stay, moved = [], []
    have = {q.get("id") for q in d["_archive"]}
    for q in d["quotes"]:
        status = q.get("status")
        go = (q.get("bet") and q.get("settled") and not S.removed_row(q)
              and (status in ("won", "lost")
                   or (status == "settled" and q.get("result") == "price")
                   or (voids and status == "void")))
        if not go:
            stay.append(q)
            continue
        if q.get("id") not in have:
            moved.append(copy.deepcopy(q))
            have.add(q.get("id"))
    return dict(d, quotes=stay, _archive=list(d["_archive"]) + moved)


def _pages(d, st):
    sandbox, _index, weeks = SB.render_pages(
        now=NOW, d=copy.deepcopy(d), st=copy.deepcopy(st))
    sandbox = SB.label_cells(sandbox)
    weeks = {slug: SB.label_cells(html) for slug, html in weeks.items()}
    return sandbox, weeks


def _headline(page):
    m = re.search(
        r"([\d,]+) settled on the record(?: · ([\d,]+) void)?", page)
    if not m:
        return None
    void = int(m.group(2).replace(",", "")) if m.group(2) else 0
    return int(m.group(1).replace(",", "")), void


def _ids(html):
    return re.findall(r'data-id="([^"]*)"', html)


def _lanes(d, st):
    rows = SB.pair_list(copy.deepcopy(d), copy.deepcopy(st))
    out = []
    for r in rows:
        a = r["a"]
        out.append((
            r["name"], r["sport"], a["n"], a["won"], round(a["pnl"], 2),
            None if a["roi"] is None else round(a["roi"], 6),
            None if a.get("roi_fee") is None else round(a["roi_fee"], 6),
            r["open"],
        ))
    return tuple(sorted(out))


def _records(d, st):
    rows = SB.pair_list(copy.deepcopy(d), copy.deepcopy(st))
    return len([r for r in rows if r["sport"] not in S.DAY_CLUSTERED])


def _tabs(d, st):
    d, st = copy.deepcopy(d), copy.deepcopy(st)
    return {
        "soccer": sport_tab.build(
            "Soccer", "soccer", "t", "l", d, st, NOW, preflight=False),
        "tennis": sport_tab.build(
            "Tennis", "tennis", "t", "l", d, st, NOW, preflight=False),
        "cricket": sport_tab.build(
            "Cricket", "cricket", "t", "l", d, st, NOW, preflight=False),
    }


def _production(d, st):
    return production.page(copy.deepcopy(d), copy.deepcopy(st), BLOB, "", now=NOW)


def _snapshot(d, st):
    sandbox, weeks = _pages(d, st)
    return dict(
        headline=_headline(sandbox),
        weeks=weeks,
        lanes=_lanes(d, st),
        records=_records(d, st),
        tabs=_tabs(d, st),
        production=_production(d, st),
        baselines=T.baselines(copy.deepcopy(d)),
        close="1 of 1" in sandbox,
        running="open-bet" in _ids(sandbox),
    )


def _check(label, before, after):
    print(f"\n{label}")
    eq(after["headline"], before["headline"], "headline settled and void counts")
    eq(after["headline"], (8, 3), "fixture headline is 8 settled and 3 void")
    eq(set(after["weeks"]), set(before["weeks"]), "weekly archive page set")
    eq(after["weeks"], before["weeks"], "weekly archive page contents")
    eq(after["lanes"], before["lanes"], "per-lane record, P/L and ROI")
    eq(after["records"], before["records"], "[records] count")
    eq(after["tabs"], before["tabs"], "soccer, tennis and cricket pages")
    eq(after["production"], before["production"], "Production record")
    eq(after["baselines"], before["baselines"], "blind baselines")
    ok(before["close"] and after["close"], "closing-price sentence still counts the archived bet")
    ok(before["running"] and after["running"], "the open bet stays on Running")
    for slug, html in after["weeks"].items():
        ids = _ids(html)
        eq(len(ids), len(set(ids)), f"{slug} has no duplicate row")
    all_ids = [i for html in after["weeks"].values() for i in _ids(html)]
    eq(all_ids.count("dup"), 1, "each rolled bet is on one week page")
    for banned in ("removed", "refused", "compact-price", "open-bet"):
        ok(banned not in all_ids, f"{banned} is not on a weekly archive page")
    ok("already-archived" in all_ids, "a bet that exists only in the archive is on its week page")


def _dedup():
    """The same id in the ledger and the archive counts once, as the live row.

    This checks the settled split directly. Building the whole Sandbox would
    also judge the pair, and two copies of one id are not two outcomes.
    """
    print("\nduplicate id")
    live = _bet(
        id="dup", status="won", pnl=81.82,
        settled="2026-09-15T18:00:00+00:00", logged="2026-09-14T18:00:00+00:00",
        start="2026-09-15T17:00:00+00:00", market_id="m-dup-live")
    stale = _bet(
        id="dup", status="lost", result="b", pnl=-100.0, price=0.45,
        settled="2026-09-15T18:00:00+00:00", logged="2026-09-14T18:00:00+00:00",
        start="2026-09-15T17:00:00+00:00", market_id="m-dup-stale")
    d = {"quotes": [live], "_archive": [stale], "meta": {}, "coverage": {}, "retired": {}}
    recent, older = SB.partition_settled(d, NOW)
    done = recent + older
    eq(len(done), 1, "a duplicated id adds one settled bet, not two")
    html = SB.archive_week_html(SB.week_slug(done[0]), done, NOW, d) if done else ""
    ok("+$82" in html, "the week page shows the live row's P/L")
    ok("\u2212$100" not in html, "the archived copy of that id is not rendered")
    ok(html.count('data-id="dup"') == 1, "the week page lists that id once")


def _same_start():
    """Two rungs share a start. One is live, one is already archived.

    day_units keeps the first of those rungs as the day's representative.
    The representative, and the cells that copy it, have to be the same
    after the live rung moves into the archive.
    """
    print("\nsame-start rungs")
    start = "2026-09-10T17:00:00+00:00"
    close_at = "2026-09-10T16:30:00+00:00"
    early = _bet(
        id="corners-early", source="corners_under", sport="soccer_corners",
        venue="polymarket_us", status="won", price=0.55, pnl=81.82,
        logged="2026-09-09T12:00:00+00:00", settled="2026-09-10T20:00:00+00:00",
        start=start, market_id="KXCORNERS-MATCH1-2",
        close_price=0.40, close_at=close_at)
    late = _bet(
        id="corners-late", source="corners_under", sport="soccer_corners",
        venue="polymarket_us", status="won", price=0.45, pnl=122.22,
        logged="2026-09-09T18:00:00+00:00", settled="2026-09-10T20:00:00+00:00",
        start=start, market_id="KXCORNERS-MATCH1-4",
        close_price=0.80, close_at=close_at)
    spot_early = _bet(
        id="spot-early", source="spot", sport="crypto", venue="polymarket_us",
        status="won", pick="a", result="a", price=0.80, pnl=25.0,
        price_a=0.80, price_b=0.20, date="2026-09-10",
        logged="2026-09-09T12:00:00+00:00", settled="2026-09-10T20:00:00+00:00",
        start=start, market_id="BTCD-26SEP10-T1")
    spot_late = _bet(
        id="spot-late", source="spot", sport="crypto", venue="polymarket_us",
        status="won", pick="b", result="b", price=0.70, pnl=42.86,
        price_a=0.30, price_b=0.70, date="2026-09-10",
        logged="2026-09-09T18:00:00+00:00", settled="2026-09-10T20:00:00+00:00",
        start=start, market_id="BTCD-26SEP10-T2")
    # The earlier rung is already archived. The later one is still live.
    d = {
        "quotes": [late, spot_late],
        "_archive": [early, spot_early],
        "meta": {}, "coverage": {}, "retired": {},
    }

    def cells(book):
        corners = T.assess(book, "corners_under", "soccer_corners",
                           venues=T.TRADEABLE_VENUES)
        spot = T.assess(book, "spot", "crypto")
        base = next(detail for key, _label, _ok, detail in spot["criteria"]
                    if key == "baseline")
        return (round(corners["clv"], 4) if corners["clv"] is not None else None,
                corners["clv_n"], SB.close_cell(corners), base)

    before = cells(d)
    after = cells(_rollup(d, voids=True))
    # Earliest logged rung: close 0.40 against the day's average price 0.50.
    eq(before[0], -0.1, "the corners representative is the earlier rung")
    eq(before[1], 1, "the two rungs are one close")
    ok("back the favourite" in before[3], "the spot line names back the favourite")
    ok("+25.0%" in before[3], "the favourite line uses the earlier rung's prices")
    eq(after, before, "CLV cell and back-the-favourite line survive the roll-up")

    print("\narchive id dedupe in per-sport score")
    first = _bet(id="twice", status="won", pnl=10.0, stake=100.0,
                 logged="2026-09-01T12:00:00+00:00", settled="2026-09-02T12:00:00+00:00",
                 start="2026-09-02T17:00:00+00:00", market_id="m-twice-a")
    second = _bet(id="twice", status="won", pnl=99.0, stake=100.0,
                  logged="2026-09-01T13:00:00+00:00", settled="2026-09-02T12:00:00+00:00",
                  start="2026-09-02T17:00:00+00:00", market_id="m-twice-b")
    scored = T.score({"quotes": [], "_archive": [first, second], "retired": {}}, "nfl")
    row = scored["espn_fpi"]
    eq(row["settled"], 1, "two archived copies of one id count once")
    eq(round(row["pnl"], 2), 10.0, "the first archived copy is the one that counts")


def _logged_id_tie():
    """Same logged time. id is the tiebreak, and it has to win in every merge.

    logged alone keeps whichever list the row sits in. That is enough for Spot,
    whose rungs were logged at different times, and not enough for Corners.
    The favourite-population scan inside assess() merges the archive on its
    own, so the same key has to be used there too.
    """
    print("\nsame logged time, id breaks the tie")
    start = "2026-09-10T17:00:00+00:00"
    logged = "2026-09-09T12:00:00+00:00"
    close_at = "2026-09-10T16:30:00+00:00"
    # Lower id, already archived. Higher id, still live, listed first.
    low = _bet(
        id="corners-a", source="corners_under", sport="soccer_corners",
        venue="polymarket_us", status="won", price=0.55, pnl=81.82,
        logged=logged, settled="2026-09-10T20:00:00+00:00",
        start=start, market_id="KXCORNERS-MATCH1-2",
        close_price=0.40, close_at=close_at)
    high = _bet(
        id="corners-b", source="corners_under", sport="soccer_corners",
        venue="polymarket_us", status="won", price=0.45, pnl=122.22,
        logged=logged, settled="2026-09-10T20:00:00+00:00",
        start=start, market_id="KXCORNERS-MATCH1-4",
        close_price=0.80, close_at=close_at)
    d = {
        "quotes": [high],
        "_archive": [low],
        "meta": {}, "coverage": {}, "retired": {},
    }
    corners = T.assess(d, "corners_under", "soccer_corners", venues=T.TRADEABLE_VENUES)
    after = T.assess(_rollup(d, voids=True), "corners_under", "soccer_corners",
                     venues=T.TRADEABLE_VENUES)
    # Average price 0.50, and the lower id's close is 0.40.
    eq(round(corners["clv"], 4) if corners["clv"] is not None else None, -0.1,
       "the corners representative is the lower id, not the live row")
    eq((after["clv"], after["clv_n"]), (corners["clv"], corners["clv_n"]),
       "the corners representative survives the roll-up when logged times match")

    # Favourite on every match. The lower id is the 0.60 favourite; the live
    # row is the 0.80. Logged alone keeps the live row until it is archived.
    rule = _bet(
        id="rule-1", source="mls_away_band", sport="soccer",
        venue="polymarket_us", status="won", price=0.50, pnl=100.0,
        price_a=0.50, price_b=0.50, result="a",
        logged="2026-09-08T12:00:00+00:00", settled="2026-09-10T20:00:00+00:00",
        start=start, market_id="RULE-1")
    pop_low = _bet(
        id="a-pop", source="polymarket_us", sport="soccer",
        venue="polymarket_us", status="won", price=0.60, pnl=66.67,
        price_a=0.60, price_b=0.40, result="a",
        logged=logged, settled="2026-09-10T20:00:00+00:00",
        start=start, market_id="POP-1")
    pop_high = _bet(
        id="b-pop", source="polymarket_us", sport="soccer",
        venue="polymarket_us", status="won", price=0.80, pnl=25.0,
        price_a=0.80, price_b=0.20, result="a",
        logged=logged, settled="2026-09-10T20:00:00+00:00",
        start=start, market_id="POP-1")
    book = {
        "quotes": [pop_high, rule],
        "_archive": [pop_low],
        "meta": {}, "coverage": {}, "retired": {},
    }

    def baseline(rows):
        got = T.assess(rows, "mls_away_band", "soccer")
        return next(detail for key, _label, _ok, detail in got["criteria"]
                    if key == "baseline")

    before_line = baseline(book)
    after_line = baseline(_rollup(book, voids=True))
    ok("+83.3%" in before_line, "the population price is the lower id")
    ok("+62.5%" not in before_line, "the live row does not win a logged-time tie")
    eq(after_line, before_line, "the population price survives the roll-up")


def _both_places():
    """A crash can leave one id in the ledger and in the archive.

    prune() has already added it to retired. All-sport score() must not count
    it again. The live row wins. The reach cell reads all_bets() inside
    production.py, which stays the raw list so a repeated id is still visible
    to the day check, so this test does not claim that cell changed.
    """
    print("\nrow in the ledger and the archive")
    live = _bet(id="both", status="won", pnl=80.0, stake=100.0, edge=0.05,
                prob_a=0.60, result="a",
                logged="2026-09-01T12:00:00+00:00", settled="2026-09-02T12:00:00+00:00",
                start="2026-09-02T17:00:00+00:00", market_id="m-both")
    archived = copy.deepcopy(live)
    # retired holds this bet and one earlier bet that is not a row anywhere.
    retired = {"espn_fpi": dict(quotes=2, bets=2, settled=2, won=2,
                                staked=200.0, pnl=180.0, brier_sum=0.25, brier_n=2)}
    d = {"quotes": [live], "_archive": [archived], "retired": retired}
    row = T.score(d)["espn_fpi"]
    eq(row["bets"], 2, "a duplicated id is not in the live count and retired")
    eq(row["settled"], 2, "the settled total counts that id once")
    eq(round(row["pnl"], 2), 180.0, "P/L counts that id once")
    eq(row["won"], 2, "wins count that id once")
    sport = T.score(d, "nfl")["espn_fpi"]
    eq(sport["settled"], 1, "the per-sport total keeps the live row only")
    eq(round(sport["pnl"], 2), 80.0, "the per-sport P/L is the live row")


def _empty_recent_note():
    """The empty recent list must name 7 days, not the placeholder."""
    print("\nempty recent note")
    old = _bet(id="old-only", status="won",
               logged="2026-08-01T12:00:00+00:00", settled="2026-08-02T12:00:00+00:00",
               start="2026-08-02T17:00:00+00:00", market_id="m-old-only")
    d = {"quotes": [old], "_archive": [], "meta": {}, "coverage": {}, "retired": {}}
    html, _index, _weeks = SB.render_pages(now=NOW, d=d, st={"pairs": {}, "events": []})
    ok("Nothing settled in the last 7 days." in html,
       "an empty recent list says 7 days")
    ok("Nothing settled in the last {RECENT_DAYS} days." not in html,
       "the empty recent list does not print the placeholder")


def _avg_edge_stable():
    """All-sport avg_edge keeps an archived bet's edge. It is not on the page."""
    print("\navg_edge across a roll-up")
    a = _bet(id="edge-a", status="won", edge=0.10,
             logged="2026-09-01T12:00:00+00:00", settled="2026-09-02T12:00:00+00:00",
             start="2026-09-02T17:00:00+00:00", market_id="m-edge-a")
    b = _bet(id="edge-b", status="won", edge=0.30,
             logged="2026-09-03T12:00:00+00:00", settled="2026-09-04T12:00:00+00:00",
             start="2026-09-04T17:00:00+00:00", market_id="m-edge-b")
    d = {"quotes": [a, b], "_archive": [], "meta": {}, "coverage": {}, "retired": {}}
    before = T.score(d)["espn_fpi"]["avg_edge"]
    after = T.score(_rollup(d, voids=True))["espn_fpi"]["avg_edge"]
    eq(round(before, 6), 0.2, "the two edges average 0.20")
    eq(None if after is None else round(after, 6),
       None if before is None else round(before, 6),
       "avg_edge is the same after the bets roll up")


def main():
    original = _ledger()
    before = _snapshot(original, ST)
    print("before roll-up:", before["headline"], "weeks", sorted(before["weeks"]))

    both = _rollup(original, voids=True)
    _check("roll-up copies every bet, voids included", before, _snapshot(both, ST))

    today = _rollup(original, voids=False)
    _check("roll-up copies won, lost and price bets; voids stay in the ledger",
           before, _snapshot(today, ST))

    print("\na tracker stage pass after the roll-up")
    st = copy.deepcopy(ST)
    T.evaluate_stages(copy.deepcopy(both), st, now=NOW, verbose=False)
    sandbox, weeks = _pages(both, st)
    eq(_headline(sandbox), before["headline"],
       "headline is unchanged after evaluate_stages")
    eq(weeks, before["weeks"], "weekly pages are unchanged after evaluate_stages")

    _dedup()
    _same_start()
    _logged_id_tie()
    _both_places()
    _empty_recent_note()
    _avg_edge_stable()

    print()
    if FAILS:
        print(f"FAIL {len(FAILS)}")
        return 1
    print("PASS archive-aware roll-up")
    return 0


if __name__ == "__main__":
    sys.exit(main())
