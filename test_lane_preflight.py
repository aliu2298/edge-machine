#!/usr/bin/env python3
"""Lane pre-flight: three Kalshi states, and the board the lane actually reads.

No network. Kalshi answers are stubbed. The BTTS/totals section calls the
real fetch with stubbed events, which is what the tracker runs once a series
relists.
"""
import inspect
import os
import subprocess
from datetime import datetime, timedelta, timezone

import sandbox_sources as S

FAILS = []
N = 0
NOW = datetime(2026, 10, 2, 12, 0, tzinfo=timezone.utc)

try:
    import lane_preflight as P
except ImportError:
    P = None


def ok(cond, msg):
    global N
    N += 1
    if cond:
        print(f"  ok   {msg}")
    else:
        print(f"  FAIL {msg}")
        FAILS.append(msg)


def eq(a, b, msg):
    ok(a == b, msg if a == b else f"{msg} (got {a!r}, want {b!r})")


def _need():
    if P is None:
        raise ImportError("lane_preflight")


def _leg(event, code, name, ask="0.4000", exp="2026-10-04T21:00:00Z"):
    return {
        "ticker": f"{event}-{code}",
        "event_ticker": event,
        "yes_sub_title": name,
        "status": "active",
        "yes_ask_dollars": ask,
        "yes_bid_dollars": "0.3800",
        "no_ask_dollars": "0.6200",
        "no_bid_dollars": "0.6000",
        "expected_expiration_time": exp,
    }


def three_way(series, day="26OCT04", exp="2026-10-04T21:00:00Z"):
    """One open three-way event the soccer board can keep."""
    event = f"{series}-{day}HEEGRO"
    return [
        _leg(event, "HEE", "Homeside", "0.4500", exp),
        _leg(event, "GRO", "Awayside", "0.3000", exp),
        _leg(event, "TIE", "Tie", "0.2500", exp),
    ]


def total_event(series, day="26OCT04", lines=None):
    event = f"{series}-{day}HOMWAY"
    lines = lines or (
        ("Over 1.5 goals scored", "2"),
        ("Over 2.5 goals scored", "3"),
        ("Over 3.5 goals scored", "4"),
    )
    markets = []
    for sub, suf in lines:
        markets.append({
            "ticker": f"{event}-{suf}",
            "event_ticker": event,
            "yes_sub_title": sub,
            "status": "active",
            "yes_ask_dollars": "0.5500",
            "yes_bid_dollars": "0.5300",
            "no_ask_dollars": "0.4700",
            "no_bid_dollars": "0.4500",
        })
    return {
        "event_ticker": event,
        "title": "Homeside vs Awayside",
        "markets": markets,
    }


def btts_event(series, day="26OCT04"):
    event = f"{series}-{day}HOMWAY"
    return {
        "event_ticker": event,
        "title": "Homeside vs Awayside: both teams to score",
        "markets": [{
            "ticker": f"{event}-BTTS",
            "event_ticker": event,
            "yes_sub_title": "Both teams to score",
            "status": "active",
            "yes_ask_dollars": "0.5200",
            "yes_bid_dollars": "0.5000",
            "no_ask_dollars": "0.5000",
            "no_bid_dollars": "0.4800",
        }],
    }


def game_event(series, day="26OCT04", exp="2026-10-04T21:00:00Z"):
    """The same three-way, nested the way the goals fetch reads a GAME series."""
    markets = three_way(series, day, exp)
    return {
        "event_ticker": markets[0]["event_ticker"],
        "title": "Homeside vs Awayside",
        "markets": markets,
    }


class _Book:
    """Stub Kalshi. A ticker with no entry is a known series and an empty book."""

    def __init__(self):
        self.rows = {}
        self.calls = []
        self.fail = set()

    def set(self, ticker, **parts):
        self.rows.setdefault(ticker, {}).update(parts)

    def __call__(self, url):
        self.calls.append(url)
        path, _, query = url.partition("?")
        if "/series/" in path:
            ticker = path.rstrip("/").rsplit("/", 1)[-1]
            if ticker in self.fail:
                raise P.ProbeError(f"down {ticker}")
            spec = self.rows.get(ticker, {})
            if "status" in spec:
                return spec["status"]
            return 200, {"series": {"ticker": ticker, "title": spec.get("title", ticker)}}
        ticker = ""
        for bit in query.split("&"):
            if bit.startswith("series_ticker="):
                ticker = bit.split("=", 1)[1]
        if ticker in self.fail:
            raise P.ProbeError(f"down {ticker}")
        spec = self.rows.get(ticker, {})
        if "/markets" in path:
            markets = spec.get("markets", [])
            return 200, {"markets": markets, "cursor": ""}
        if "/events" in path:
            return 200, {"events": spec.get("events", []), "cursor": ""}
        raise AssertionError(url)


def _run(book, now=NOW):
    results = P.evaluate(book, now=now, attempts=1)
    text, code = P.render(results, now)
    return results, text, code


def _one(results, lane, series, kind):
    hits = [r for r in results if r["lane"] == lane and r["series"] == series and r["kind"] == kind]
    eq(len(hits), 1, f"one result for {lane} {series} {kind}")
    return hits[0] if len(hits) == 1 else {"state": None, "level": None, "detail": ""}


def test_map_uses_lane_constants():
    _need()
    print("\nmap is the ten lanes' own constants")
    by = {}
    for lane, series, kind in P.checks():
        by.setdefault(lane, []).append((series, kind))
    eq(list(by), [
        "ere_draw", "ere_o15", "bund_o35", "bund_o35_fav", "liga_btts_even",
        "liga_u15_dog", "turkey_o25_dog", "turkey_btts_dog", "mls_away_band",
        "mls_fade_home",
    ], "the ten lanes, in matchday order, and no others")
    eq(by["ere_draw"], [(S.ERE_DRAW_SERIES, "three_way")], "ere_draw reads ERE_DRAW_SERIES")
    eq(by["ere_o15"], [(S.ERE_O15_TOTAL, "total"), (S.ERE_O15_GAME, "three_way")],
       "ere_o15 reads ERE_O15_TOTAL and ERE_O15_GAME")
    eq(by["bund_o35"], [(S.BUND_O35_TOTAL, "total"), (S.BUND_O35_GAME, "three_way")],
       "bund_o35 reads BUND_O35_TOTAL and BUND_O35_GAME")
    eq(by["bund_o35_fav"], by["bund_o35"], "bund_o35_fav reads the same two series")
    eq(by["liga_btts_even"], [(S.LIGA_BTTS, "btts"), (S.LIGA_GAME, "three_way")],
       "liga_btts_even reads LIGA_BTTS and LIGA_GAME")
    eq(by["liga_u15_dog"], [(S.LIGA_TOTAL, "total"), (S.LIGA_GAME, "three_way")],
       "liga_u15_dog reads LIGA_TOTAL and LIGA_GAME")
    eq(by["turkey_o25_dog"], [(S.TURKEY_TOTAL, "total"), (S.TURKEY_GAME, "three_way")],
       "turkey_o25_dog reads TURKEY_TOTAL and TURKEY_GAME")
    eq(by["turkey_btts_dog"], [(S.TURKEY_BTTS, "btts"), (S.TURKEY_GAME, "three_way")],
       "turkey_btts_dog reads TURKEY_BTTS and TURKEY_GAME")
    eq(by["mls_away_band"], [(S.MLS_GAME, "three_way")], "mls_away_band reads MLS_GAME")
    eq(by["mls_fade_home"], [(S.MLS_GAME, "three_way"), (S.MLS_GAME, "p05")],
       "mls_fade_home reads MLS_GAME on the three-way board and the +0.5 board")
    eq(P.board_sport("ere_o15", "total"), "soccer_o15", "ere_o15's total is the over-1.5 board")
    eq(P.board_sport("bund_o35", "total"), "soccer_u35", "bund_o35's total is the over-3.5 board")
    eq(P.board_sport("turkey_o25_dog", "total"), "soccer_o25", "turkey_o25_dog's total is the over-2.5 board")
    eq(P.board_sport("liga_btts_even", "btts"), "soccer_btts", "liga_btts_even reads the BTTS board")
    eq(P.board_sport("mls_fade_home", "p05"), "soccer_p05", "mls_fade_home reads the +0.5 board")
    eq(P.board_sport("ere_draw", "three_way"), "soccer", "a three-way series is the soccer board")
    for lane, kind, sport in (
            ("ere_o15", "total", "soccer_o15"),
            ("bund_o35", "total", "soccer_u35"),
            ("liga_btts_even", "btts", "soccer_btts"),
            ("mls_fade_home", "p05", "soccer_p05"),
            ("ere_draw", "three_way", "soccer")):
        if kind == "three_way":
            continue
        eq(P.board_sport(lane, kind), S.SOURCES[lane]["sports"][0],
           f"{lane}'s {kind} board is the sport the lane is registered on")


def test_never_seen_is_loud():
    _need()
    print("\nnever seen")
    book = _Book()
    book.set(S.ERE_DRAW_SERIES, status=(404, {"error": {"code": "not_found", "message": "not found"}}))
    results, text, code = _run(book)
    row = _one(results, "ere_draw", S.ERE_DRAW_SERIES, "three_way")
    eq(row["state"], "never seen", "a 404 series is never seen")
    eq(row["level"], "error", "never seen is a failure")
    ok(code != 0, "never seen exits non-zero")
    ok(f"::error::ere_draw {S.ERE_DRAW_SERIES} never seen" in text,
       "the error annotation names the lane, the series and never seen")
    ok("Kalshi has no such series ticker" in text, "the message says the ticker is unknown")
    # The other lane that reads this series is ere_o15's game board. It fails too.
    other = _one(results, "ere_o15", S.ERE_O15_GAME, "three_way")
    eq(other["state"], "never seen", "ere_o15 names the same missing game series")
    ok(not any("/markets" in u and S.ERE_DRAW_SERIES in u for u in book.calls),
       "a series Kalshi has never heard of is not also asked for markets")


def test_quiet_series_warns_and_exits_0():
    _need()
    print("\nexists but no open markets")
    book = _Book()
    results, text, code = _run(book)
    eq(code, 0, "an empty book does not fail the run")
    row = _one(results, "ere_o15", S.ERE_O15_TOTAL, "total")
    eq(row["state"], "exists but no open markets", "a known series with no markets is quiet")
    eq(row["level"], "warning", "quiet is a warning")
    ok(f"::warning::ere_o15 {S.ERE_O15_TOTAL} exists but no open markets" in text,
       "the warning annotation names the lane")
    ok("::error::" not in text, "a quiet book prints no error")
    ok(all(r["lane"] for r in results), "every line names a lane")
    ok(len(results) == len(P.checks()), "every lane series gets a line")


def test_listed_reaches_the_board():
    _need()
    print("\nlisted")
    book = _Book()
    book.set(S.ERE_DRAW_SERIES, markets=three_way(S.ERE_DRAW_SERIES))
    book.set(S.ERE_O15_TOTAL, events=[total_event(S.ERE_O15_TOTAL)])
    book.set(S.LIGA_BTTS, events=[btts_event(S.LIGA_BTTS)])
    book.set(S.MLS_GAME, markets=three_way(S.MLS_GAME), events=[game_event(S.MLS_GAME)])
    book.set(S.BUND_O35_TOTAL, events=[total_event(S.BUND_O35_TOTAL)])
    results, text, code = _run(book)
    eq(code, 0, "markets that reach the board do not fail the run")
    draw = _one(results, "ere_draw", S.ERE_DRAW_SERIES, "three_way")
    eq(draw["state"], "listed", "an in-window three-way is listed")
    eq(draw["level"], "ok", "listed is not a warning")
    ok("soccer board" in draw["detail"], "the line names the soccer board ere_draw reads")
    o15 = _one(results, "ere_o15", S.ERE_O15_TOTAL, "total")
    eq(o15["state"], "listed", "an in-window over 1.5 reaches ere_o15")
    ok("soccer_o15" in o15["detail"], "the line names the over-1.5 board")
    btts = _one(results, "liga_btts_even", S.LIGA_BTTS, "btts")
    eq(btts["state"], "listed", "an in-window BTTS market reaches liga_btts_even")
    fade = _one(results, "mls_fade_home", S.MLS_GAME, "p05")
    eq(fade["state"], "listed", "an in-window MLS game reaches the +0.5 board")
    away = _one(results, "mls_away_band", S.MLS_GAME, "three_way")
    eq(away["state"], "listed", "the same MLS game reaches the three-way board")
    bund = _one(results, "bund_o35", S.BUND_O35_TOTAL, "total")
    eq(bund["state"], "listed", "an in-window over 3.5 reaches bund_o35")
    fav = _one(results, "bund_o35_fav", S.BUND_O35_TOTAL, "total")
    eq(fav["state"], "listed", "bund_o35_fav names that same total")
    ok("::error::" not in text, "listed markets print no error")
    ok(text.startswith("2026-10-02T12:00Z lane pre-flight"), "the report is stamped in UTC")


def test_open_but_unwired_is_loud():
    _need()
    print("\nlisted but not on the board — series not on the fetch")
    book = _Book()
    book.set(S.ERE_DRAW_SERIES, markets=three_way(S.ERE_DRAW_SERIES))
    saved = list(S.KALSHI_VENUE_SERIES["soccer"])
    try:
        S.KALSHI_VENUE_SERIES["soccer"] = [s for s in saved if s != S.ERE_DRAW_SERIES]
        results, text, code = _run(book)
    finally:
        S.KALSHI_VENUE_SERIES["soccer"] = saved
    row = _one(results, "ere_draw", S.ERE_DRAW_SERIES, "three_way")
    eq(row["state"], "listed but not on the board", "open markets the soccer fetch does not request are not listed")
    eq(row["level"], "error", "that miss is a failure")
    ok(code != 0, "it exits non-zero")
    ok(f"::error::ere_draw {S.ERE_DRAW_SERIES} listed but not on the board" in text,
       "the error annotation names the lane")
    ok("does not request" in row["detail"], "the detail says the fetch never asks for the series")
    ok(S.ERE_DRAW_SERIES in S.KALSHI_VENUE_SERIES["soccer"], "the venue list is restored")


def test_wrong_shape_is_loud():
    _need()
    print("\nlisted but not on the board — parser drops the contract")
    book = _Book()
    book.set(S.ERE_O15_TOTAL, events=[total_event(
        S.ERE_O15_TOTAL, lines=(("Over 4.5 goals scored", "5"),))])
    results, text, code = _run(book)
    row = _one(results, "ere_o15", S.ERE_O15_TOTAL, "total")
    eq(row["state"], "listed but not on the board", "an open total with no over-1.5 line does not reach ere_o15")
    eq(row["level"], "error", "a shape the board drops is a failure")
    ok(code != 0, "it exits non-zero")
    ok("ere_o15" in text and "listed but not on the board" in text, "the line names ere_o15")
    ok("::error::" in text, "the failure is an error annotation")


def test_outside_window_warns():
    _need()
    print("\nopen markets outside the board window")
    book = _Book()
    book.set(S.ERE_DRAW_SERIES, markets=three_way(
        S.ERE_DRAW_SERIES, day="26OCT20", exp="2026-10-20T21:00:00Z"))
    results, text, code = _run(book)
    row = _one(results, "ere_draw", S.ERE_DRAW_SERIES, "three_way")
    eq(row["state"], "listed but not on the board", "a game past the horizon is not on the board today")
    eq(row["level"], "warning", "that is the listing window, not a broken fetch")
    eq(code, 0, "a window miss does not fail the run")
    ok("window" in row["detail"], "the detail says it is the window")
    ok(f"::warning::ere_draw {S.ERE_DRAW_SERIES} listed but not on the board" in text,
       "the warning annotation names the lane")
    ok("::error::" not in text, "a window miss prints no error")


def test_transport_error_is_not_never_seen():
    _need()
    print("\ntransport error")
    book = _Book()
    book.fail.add(S.TURKEY_BTTS)
    results, text, code = _run(book)
    row = _one(results, "turkey_btts_dog", S.TURKEY_BTTS, "btts")
    eq(row["state"], "could not check", "a failed request is not a verdict about the series")
    ok(row["state"] != "never seen", "it is not reported as never seen")
    ok("no open markets" not in row["state"], "it is not reported as a quiet book")
    eq(row["level"], "error", "an unchecked series fails the run")
    ok(code != 0, "it exits non-zero")
    ok("turkey_btts_dog" in text and "::error::" in text, "the error names turkey_btts_dog")


def test_call_count_stays_small():
    _need()
    print("\ncall count")
    book = _Book()
    _run(book)
    series_calls = [u for u in book.calls if "/series/" in u.split("?", 1)[0]]
    tickers = [u.rstrip("/").rsplit("/", 1)[-1] for u in series_calls]
    eq(sorted(tickers), sorted(set(tickers)), "each series is probed once")
    wanted = {series for _lane, series, _kind in P.checks()}
    eq(set(tickers), wanted, "the probes are exactly the lanes' series")
    ok(len(book.calls) <= 40, f"a full pre-flight stays within 40 calls (made {len(book.calls)})")
    ok(all("api.elections.kalshi.com" in u for u in book.calls), "every call is Kalshi's public host")


def test_btts_leagues_cover_the_five_fragments():
    print("\nBTTS_LEAGUES covers the five league fragments")
    for frag in ("EREDIVISIE", "BUNDESLIGA", "LALIGA", "SUPERLIG", "MLS"):
        ok(frag in S.BTTS_LEAGUES, f"{frag} is a BTTS_LEAGUES fragment")
    # The fetch builds KX{fragment}TOTAL and KX{fragment}BTTS. The lane constants
    # are those tickers, so a fragment that does not produce the constant cannot
    # be what the lane reads.
    eq("KX" + "EREDIVISIE" + "TOTAL", S.ERE_O15_TOTAL, "EREDIVISIE builds ERE_O15_TOTAL")
    eq("KX" + "BUNDESLIGA" + "TOTAL", S.BUND_O35_TOTAL, "BUNDESLIGA builds BUND_O35_TOTAL")
    eq("KX" + "LALIGA" + "TOTAL", S.LIGA_TOTAL, "LALIGA builds LIGA_TOTAL")
    eq("KX" + "LALIGA" + "BTTS", S.LIGA_BTTS, "LALIGA builds LIGA_BTTS")
    eq("KX" + "SUPERLIG" + "TOTAL", S.TURKEY_TOTAL, "SUPERLIG builds TURKEY_TOTAL")
    eq("KX" + "SUPERLIG" + "BTTS", S.TURKEY_BTTS, "SUPERLIG builds TURKEY_BTTS")
    eq("KX" + "MLS" + "GAME", S.MLS_GAME, "MLS builds MLS_GAME, which the +0.5 board reads")


def test_totals_and_btts_fetch_pick_up_relisted_series():
    print("\nstubbed totals and BTTS come back onto the boards")
    now = NOW
    frags = ("EREDIVISIE", "BUNDESLIGA", "LALIGA", "SUPERLIG", "MLS")
    home = {
        "EREDIVISIE": "Ere Home", "BUNDESLIGA": "Bund Home", "LALIGA": "Liga Home",
        "SUPERLIG": "Turk Home", "MLS": "Mls Home",
    }
    away = {k: v.replace("Home", "Away") for k, v in home.items()}
    fixtures = []
    totals = {}
    btts = {}
    for frag in frags:
        fixtures.append(dict(
            home=home[frag], away=away[frag], kickoff="2026-10-03T18:00Z",
            played=False, home_goals=None, away_goals=None, comp="league", competitive=True,
        ))
        t_series = f"KX{frag}TOTAL"
        b_series = f"KX{frag}BTTS"
        code = "26OCT03" + frag[:3]
        t_event = f"{t_series}-{code}"
        b_event = f"{b_series}-{code}"
        title = f"{home[frag]} vs {away[frag]}"
        totals[t_series] = [{
            "event_ticker": t_event,
            "title": title + ": Total Goals",
            "markets": [
                {"ticker": f"{t_event}-2", "yes_sub_title": "Over 1.5 goals scored", "status": "active",
                 "yes_ask_dollars": "0.62", "yes_bid_dollars": "0.60",
                 "no_ask_dollars": "0.40", "no_bid_dollars": "0.38"},
                {"ticker": f"{t_event}-3", "yes_sub_title": "Over 2.5 goals scored", "status": "active",
                 "yes_ask_dollars": "0.52", "yes_bid_dollars": "0.50",
                 "no_ask_dollars": "0.50", "no_bid_dollars": "0.48"},
                {"ticker": f"{t_event}-4", "yes_sub_title": "Over 3.5 goals scored", "status": "active",
                 "yes_ask_dollars": "0.34", "yes_bid_dollars": "0.32",
                 "no_ask_dollars": "0.68", "no_bid_dollars": "0.66"},
            ],
        }]
        btts[b_series] = [{
            "event_ticker": b_event,
            "title": title + ": BTTS",
            "markets": [{
                "ticker": f"{b_event}-BTTS", "status": "active",
                "yes_ask_dollars": "0.55", "yes_bid_dollars": "0.53",
                "no_ask_dollars": "0.47", "no_bid_dollars": "0.45",
            }],
        }]
    goals = S.fetch_kalshi_goals(fixtures=fixtures, now=now, events_by_series=totals)
    got_btts = S.fetch_kalshi_btts(fixtures=fixtures, now=now, events_by_series=btts)
    want = {
        "KXEREDIVISIETOTAL": "soccer_o15",
        "KXBUNDESLIGATOTAL": "soccer_u35",
        "KXLALIGATOTAL": "soccer_o15",
        "KXSUPERLIGTOTAL": "soccer_o25",
        "KXMLSTOTAL": "soccer_o15",
    }
    for series, sport in want.items():
        ids = [r["market_id"] for r in goals.get(sport, [])]
        ok(any(m.startswith(series + "-") for m in ids),
           f"{series} is on the {sport} board once it relists")
    btts_ids = [r["market_id"] for r in got_btts]
    for frag in frags:
        series = f"KX{frag}BTTS"
        ok(any(m.startswith(series + "-") for m in btts_ids),
           f"{series} is on the BTTS board once it relists")
    # The fetch only asks for fragments in BTTS_LEAGUES. Drop MLS and the same
    # stub is invisible. Put the fragment back before anything else reads it.
    saved = dict(S.BTTS_LEAGUES)
    try:
        S.BTTS_LEAGUES.pop("MLS")
        dropped = S.fetch_kalshi_goals(fixtures=fixtures, now=now, events_by_series=totals)
        dropped_b = S.fetch_kalshi_btts(fixtures=fixtures, now=now, events_by_series=btts)
    finally:
        S.BTTS_LEAGUES.clear()
        S.BTTS_LEAGUES.update(saved)
    ok(not any(str(r["market_id"]).startswith("KXMLSTOTAL")
               for rows in dropped.values() for r in rows),
       "without the MLS fragment the totals fetch does not keep KXMLSTOTAL")
    ok(not any(str(r["market_id"]).startswith("KXMLSBTTS") for r in dropped_b),
       "without the MLS fragment the BTTS fetch does not keep KXMLSBTTS")
    ok("MLS" in S.BTTS_LEAGUES, "the fragment list is restored")


def _step_script(wf, name):
    step = wf.split("- name: " + name, 1)[-1]
    nxt = step.find("\n      - ")
    if nxt != -1:
        step = step[:nxt]
    run_at = step.find("run: |\n")
    if run_at < 0:
        return ""
    lines = []
    for line in step[run_at + len("run: |\n"):].splitlines():
        if line.startswith("          "):
            lines.append(line[10:])
        elif line.strip() == "":
            lines.append("")
        else:
            break
    return "\n".join(lines) + "\n"


def test_preflight_is_its_own_workflow():
    print("\npre-flight workflow, not the tracker")
    root = os.path.dirname(os.path.abspath(__file__))
    wf_dir = os.path.join(root, ".github", "workflows")
    tracker = open(os.path.join(wf_dir, "sandbox-tracker.yml"), encoding="utf-8").read()
    path = os.path.join(wf_dir, "lane-preflight.yml")
    ok(os.path.isfile(path), "lane-preflight.yml is its own workflow")
    wf = open(path, encoding="utf-8").read() if os.path.isfile(path) else ""
    ok("python3 lane_preflight.py" in wf, "the new workflow runs python3 lane_preflight.py")
    ok("timeout-minutes: 5" in wf, "the job is bounded at 5 minutes")
    ok("contents: read" in wf and "contents: write" not in wf,
       "the workflow is contents: read")
    ok("persist-credentials: false" in wf, "checkout does not persist credentials")
    ok('cron: "26 */3 * * *"' in wf, "the cron is :26, clear of the tracker and the boards")
    ok("workflow_dispatch:" in wf, "it can be run by hand")
    ok("actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1" in wf
       and "actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97" in wf,
       "checkout and setup-python use the repo's pinned SHAs")
    ok(bool(wf) and "secrets" not in wf and "set +e" not in wf
       and "continue-on-error" not in wf and "|| true" not in wf and "exit 0" not in wf,
       "a non-zero pre-flight fails this job, and the step reads no secret")
    ok("lane_preflight" not in tracker and "PREFLIGHT" not in tracker
       and "preflight" not in tracker,
       "the tracker workflow does not run the pre-flight")
    fail = _step_script(tracker, "Fail the job if the tracker or the page build failed")
    ran = subprocess.run(["bash", "-c", fail], capture_output=True, text=True, env={
        **os.environ,
        "TRACK_RC": "0", "BUILD_RC": "0", "GATE_FAIL": "false", "LIVE_RC": "0",
        "PREFLIGHT_RC": "1",
    })
    ok(ran.returncode == 0 and "Lane pre-flight" not in ran.stdout
       and "preflight" not in ran.stdout.lower(),
       "a pre-flight failure does not fail the tracker job")
    horizon = inspect.signature(S.fetch_kalshi_venue).parameters["horizon_days"].default
    ok(horizon == inspect.signature(S.fetch_kalshi_goals).parameters["horizon_days"].default
       == inspect.signature(S.fetch_kalshi_btts).parameters["horizon_days"].default,
       "the three board fetches share one horizon")


def test_kalshi_title_cannot_inject_a_workflow_command():
    _need()
    print("\nworkflow command injection")
    book = _Book()
    book.set(S.ERE_O15_TOTAL, title="Legit\n::add-mask::x")
    _results, text, _code = _run(book)
    lines = text.splitlines()
    ok(not any(line.startswith("::add-mask::") for line in lines),
       "a newline in a Kalshi title cannot start ::add-mask::")
    encoded = [line for line in lines if "%0A::add-mask::x" in line or "%0A%3A%3Aadd-mask" in line]
    ok(bool(encoded) and all("\n" not in line and "\r" not in line for line in encoded),
       "the newline is percent-encoded on one annotation line")
    ok(any(line.startswith("::warning::") or line.startswith("::warning ") for line in encoded),
       "that line is the warning for the lane")
    if not hasattr(P, "workflow_command"):
        ok(False, "property values on a workflow command are percent-encoded")
        return
    cmd = P.workflow_command("warning", "100%", title="Legit\n::add-mask::x,y")
    ok("\n" not in cmd and "\r" not in cmd, "the command is a single line")
    ok("title=Legit%0A%3A%3Aadd-mask%3A%3Ax%2Cy" in cmd,
       "a property encodes newline, colon and comma")
    ok(cmd.endswith("::100%25"), "percent in the message is encoded first")
    ok("%0A" in cmd and "%250A" not in cmd and "%253A" not in cmd,
       "an encoded newline is not percent-encoded a second time")


def test_bad_payload_is_could_not_check():
    _need()
    print("\nbad payload")
    book = _Book()
    book.set(S.ERE_O15_TOTAL, events=["x"])
    try:
        results, _text, code = _run(book)
        row = _one(results, "ere_o15", S.ERE_O15_TOTAL, "total")
        eq(row["state"], "could not check", "a non-dict event is could not check")
        eq(row["level"], "error", "an unreadable book fails the run")
        ok(code != 0, "it exits non-zero")
        ok(row["state"] != "never seen", "it is not never seen")
    except Exception as exc:
        ok(False, f"a non-dict event is could not check, not {type(exc).__name__}")
    book2 = _Book()
    book2.set(S.LIGA_BTTS, status=(200, ["not", "an", "object"]))
    results2, _text2, _code2 = _run(book2)
    row2 = _one(results2, "liga_btts_even", S.LIGA_BTTS, "btts")
    eq(row2["state"], "could not check", "JSON that is not an object is could not check")
    import http.client
    raised = []

    def boom(_url):
        raise http.client.IncompleteRead(b"partial")

    try:
        got = P.evaluate(boom, now=NOW, attempts=1, pause=0)
    except Exception as exc:
        raised.append(type(exc).__name__)
        got = []
    ok(not raised and got and all(r["state"] == "could not check" for r in got),
       "http.client.HTTPException is could not check, not a traceback")


def test_retries_429_and_5xx():
    _need()
    print("\nretry 429 and 5xx")
    book = _Book()
    hits = {}

    def get(url):
        hits[url] = hits.get(url, 0) + 1
        path = url.split("?", 1)[0]
        if hits[url] == 1 and path.rstrip("/").endswith("/series/" + S.ERE_DRAW_SERIES):
            return 429, {}
        if hits[url] == 1 and path.rstrip("/").endswith("/series/" + S.TURKEY_BTTS):
            return 503, {"error": "unavailable"}
        return book(url)

    results = P.evaluate(get, now=NOW, attempts=3, pause=0)
    draw = _one(results, "ere_draw", S.ERE_DRAW_SERIES, "three_way")
    eq(draw["state"], "exists but no open markets", "a 429 then a 200 is the book")
    btts = _one(results, "turkey_btts_dog", S.TURKEY_BTTS, "btts")
    eq(btts["state"], "exists but no open markets", "a 503 is retried")
    draw_url = next(u for u in hits if u.rstrip("/").endswith("/series/" + S.ERE_DRAW_SERIES))
    eq(hits[draw_url], 2, "the 429 series is fetched a second time")
    # A 404 is the never-seen verdict. Retrying it would hide a renamed ticker.
    misses = {"n": 0}

    def once(url):
        if "/series/" in url.split("?", 1)[0] and url.rstrip("/").endswith(S.ERE_DRAW_SERIES):
            misses["n"] += 1
        return book(url)

    book.set(S.ERE_DRAW_SERIES, status=(404, {"error": {"code": "not_found"}}))
    P.evaluate(once, now=NOW, attempts=3, pause=0)
    eq(misses["n"], 1, "a 404 is not retried")
    pause = inspect.signature(P.evaluate).parameters["pause"].default
    tries = inspect.signature(P.evaluate).parameters["attempts"].default
    ok(pause <= 1 and tries <= 4, "the backoff stays inside the 5-minute job")


def test_open_event_without_markets_counts_as_one():
    _need()
    print("\nopen event with no nested markets")
    book = _Book()
    book.set(S.ERE_O15_TOTAL, events=[{
        "event_ticker": f"{S.ERE_O15_TOTAL}-26OCT04HOMWAY",
        "title": "Homeside vs Awayside",
        "markets": [],
    }])
    results, text, code = _run(book)
    row = _one(results, "ere_o15", S.ERE_O15_TOTAL, "total")
    eq(row["state"], "listed but not on the board",
       "an open event shell is not an empty book")
    ok("1" in row["detail"] and "no nested" in row["detail"],
       "the shell counts as 1")
    eq(row["level"], "warning", "legs that are not listed yet do not fail the run")
    eq(code, 0, "the run stays green")
    ok("::error::" not in text, "a shell prints no error")


def test_body_cap_redirect_and_summary():
    _need()
    print("\nbody cap, redirect, step summary")
    if not hasattr(P, "read_capped") or not hasattr(P, "kalshi_https"):
        ok(False, "responses are capped and redirects must stay on the Kalshi host")
        return
    chunks = [b"a" * 100, b"b" * 100]

    class _Stream:
        def read(self, _n):
            return chunks.pop(0) if chunks else b""

    eq(P.read_capped(_Stream(), limit=250), b"a" * 100 + b"b" * 100,
       "a small body is kept")
    chunks2 = [b"z" * 80, b"z" * 80]

    class _Big:
        def read(self, _n):
            return chunks2.pop(0) if chunks2 else b""

    try:
        P.read_capped(_Big(), limit=100)
        ok(False, "a body over the cap is refused")
    except P.ProbeError:
        ok(True, "a body over the cap is refused")
    ok(P.kalshi_https("https://api.elections.kalshi.com/trade-api/v2/series/X"),
       "the Kalshi host over HTTPS is allowed")
    ok(not P.kalshi_https("https://evil.example/series/X"),
       "another host is not allowed")
    ok(not P.kalshi_https("http://api.elections.kalshi.com/trade-api/v2/series/X"),
       "plain HTTP is not allowed")
    if not hasattr(P, "summary_text") or not hasattr(P, "write_step_summary"):
        ok(False, "the full result list is written to the step summary")
        return
    book = _Book()
    results = P.evaluate(book, now=NOW, attempts=1)
    summary = P.summary_text(results, NOW)
    for row in results:
        flat = P.format_result(row).replace("\r", " ").replace("\n", " ")
        ok(flat in summary, f"the summary lists {row['lane']} {row['series']}")
    path = "/tmp/lane-preflight-summary.md"
    os.environ["GITHUB_STEP_SUMMARY"] = path
    try:
        if os.path.exists(path):
            os.remove(path)
        P.write_step_summary(summary)
        got = open(path, encoding="utf-8").read()
    finally:
        os.environ.pop("GITHUB_STEP_SUMMARY", None)
    eq(got, summary, "GITHUB_STEP_SUMMARY receives every lane")


TESTS = (
    test_map_uses_lane_constants,
    test_never_seen_is_loud,
    test_quiet_series_warns_and_exits_0,
    test_listed_reaches_the_board,
    test_open_but_unwired_is_loud,
    test_wrong_shape_is_loud,
    test_outside_window_warns,
    test_transport_error_is_not_never_seen,
    test_call_count_stays_small,
    test_btts_leagues_cover_the_five_fragments,
    test_totals_and_btts_fetch_pick_up_relisted_series,
    test_preflight_is_its_own_workflow,
    test_kalshi_title_cannot_inject_a_workflow_command,
    test_bad_payload_is_could_not_check,
    test_retries_429_and_5xx,
    test_open_event_without_markets_counts_as_one,
    test_body_cap_redirect_and_summary,
)

for _t in TESTS:
    try:
        _t()
    except Exception as exc:
        ok(False, f"{_t.__name__} ({type(exc).__name__}: {exc})")

print(f"\n{N} checks, {len(FAILS)} failed")
for f in FAILS:
    print("   -", f)
raise SystemExit(1 if FAILS else 0)
