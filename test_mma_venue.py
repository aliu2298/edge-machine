#!/usr/bin/env python3
"""MMA favourite-band bets go on Polymarket US when that venue lists the fight.

Kalshi is the fallback only when Polymarket US does not. An open Kalshi entry
whose fight has not started is retired as unplaceable and replaced once, at
Polymarket US's live price. No network. Fails on main, where the Kalshi entry
blocks the Polymarket US one.
"""
import copy
import os
import tempfile
from datetime import datetime, timedelta, timezone

import production
import sandbox_audit as A
import sandbox_build as SB
import sandbox_close as SC
import sandbox_sources as S
import sandbox_track as T

FAILS = []
NOTE = "kalshi_unplaceable"


def ok(cond, why):
    print(f"  {'ok  ' if cond else 'FAIL'} {why}")
    if not cond:
        FAILS.append(why)


def eq(got, want, why):
    ok(got == want, why if got == want else f"{why} — got {got!r}, want {want!r}")


def _publish(d, universe, now=None):
    """publish with only the band fetchers, so a unit test never hits the network.

    The wide favourite-band rule is off the board. The tennis case calls the
    3-hour lane, which reads the universe and does not touch the network.
    `now` pins the clock when a case must not read the wall clock.
    """
    saved_ch, saved_uni = S.CHALLENGERS, S.UNIVERSE
    S.CHALLENGERS = {
        "mma_fav_band": S.fetch_tennis_fav_band,
        "tennis_fav_band_3h": S.fetch_tennis_fav_band_3h,
    }
    try:
        return T.publish(d, universe, {}, verbose=False, now=now)
    finally:
        S.CHALLENGERS = saved_ch
        S.UNIVERSE = saved_uni


def _row(mid, venue, side_a, side_b, price_a, price_b, start, sport="mma"):
    # The midpoint sits just inside the side-a ask. A real book does that, so the
    # venue's own self-quote has no 3pp edge and is not a second bet. Averaging the
    # two asks puts the mid near 0.50 and the cheap side looks like a bet.
    return dict(market_id=mid, venue=venue, sport=sport, label=f"{side_a} vs {side_b}",
                side_a=side_a, side_b=side_b, price_a=price_a, price_b=price_b,
                mid_a=round(price_a - 0.01, 4), untraded=False,
                tradeable={"a": True, "b": True}, start=start.isoformat(),
                date=start.date().isoformat(), volume=1.0, url="")


def _open_kalshi(mid, side_a, side_b, start, price=0.88, pick="a"):
    return dict(id=f"mma_fav_band:{mid}", source="mma_fav_band", sport="mma",
                venue="kalshi", market_id=mid, status="open", bet=True, pick=pick,
                price=price, price_a=price if pick == "a" else round(1.02 - price, 2),
                price_b=price if pick == "b" else round(1.02 - price, 2),
                stake=100.0, pnl=0.0, side_a=side_a, side_b=side_b,
                start=start.isoformat(), date=start.date().isoformat(),
                logged="2026-09-29T15:48:21+00:00", start_source="venue",
                result=None, settled=None)


def _bets(d, source):
    return [q for q in d["quotes"] if q.get("source") == source and q.get("bet")]


def _page(d, st, now):
    _rows, n_live = SB.open_rows(d)
    recent, older = SB.partition_settled(d, now)
    n_void = sum(1 for q in d["quotes"]
                 if q.get("status") == "void" and q.get("bet") and not S.removed_row(q))
    n_settled = (len(recent) + len(older)) - n_void
    rows = SB.pair_list(d, st)
    noedge = sum(1 for r in rows if r["v"] == "noedge" and not r.get("gone"))
    feed = production.build_feed(d, st, now=now)
    held = feed["unlisted_skipped"] + feed["unverified_kickoff_skipped"]
    return dict(settled=n_settled, void=n_void, running=n_live, noedge=noedge, held=held)


def main():
    saved_removed = S.REMOVED_SOURCES
    # Off the board as of 2026-10-04. These cases are the guarded
    # Kalshi-to-Polymarket-US replacement, so they lift the source for the
    # run and put it back. The live tracker does not log the lane.
    S.REMOVED_SOURCES = frozenset(n for n in saved_removed if n != "mma_fav_band")
    try:
        return _cases()
    finally:
        S.REMOVED_SOURCES = saved_removed


def _cases():
    soon = datetime.now(timezone.utc) + timedelta(days=2)
    soon = soon.replace(microsecond=0)
    past = datetime.now(timezone.utc) - timedelta(hours=3)
    past = past.replace(microsecond=0)

    print("\nPolymarket US lists the fight: the bet is logged there")
    kalshi = _row("KXUFCFIGHT-26OCT03SMIWHI", "kalshi", "Jacobe Smith", "Bruce Whitehead",
                  0.88, 0.14, soon)
    pmus = _row("aec-ufc-smiwhi-2026-10-03", "polymarket_us", "Jacobe Smith", "Bruce Whitehead",
                0.86, 0.16, soon)
    fresh = {"quotes": [], "meta": {}, "coverage": {}}
    _publish(fresh, {"mma": [kalshi, pmus]})
    logged = _bets(fresh, "mma_fav_band")
    eq(len(logged), 1, "one MMA favourite-band bet is logged")
    if logged:
        eq(logged[0]["venue"], "polymarket_us", "that bet is on Polymarket US")
        eq(logged[0]["price"], 0.86, "the price is Polymarket US's ask, not Kalshi's 0.88")
        eq(logged[0]["market_id"], pmus["market_id"], "the market is the Polymarket US listing")

    print("\nPolymarket US does not list it: Kalshi is still used")
    only = {"quotes": [], "meta": {}, "coverage": {}}
    _publish(only, {"mma": [kalshi]})
    kalshi_bets = _bets(only, "mma_fav_band")
    eq([(q["venue"], q["price"]) for q in kalshi_bets], [("kalshi", 0.88)],
       "a fight Polymarket US does not list is still booked on Kalshi")
    dark = _row("KXUFCFIGHT-26OCT03DARK", "kalshi", "Dark One", "Dark Two",
                0.82, 0.20, soon)
    dark["untraded"] = True
    gated = {"quotes": [], "meta": {}, "coverage": {}}
    _publish(gated, {"mma": [dark]})
    eq(_bets(gated, "mma_fav_band"), [], "an untraded Kalshi book is still not a bet")

    print("\nan open Kalshi entry moves once, before the start")
    stuck = _open_kalshi("KXUFCFIGHT-26OCT03SMIWHI", "Jacobe Smith", "Bruce Whitehead", soon)
    moved = {"quotes": [stuck], "meta": {}, "coverage": {}}
    t0 = datetime.now(timezone.utc) - timedelta(seconds=2)
    _publish(moved, {"mma": [pmus]})
    t1 = datetime.now(timezone.utc) + timedelta(seconds=2)
    mma = [q for q in moved["quotes"] if q.get("source") == "mma_fav_band"]
    eq(stuck["status"], "void", "the Kalshi entry is retired")
    eq(stuck["bet"], False, "the retired row is not a bet")
    eq(stuck["pnl"], 0.0, "the retired row carries no P/L")
    eq(stuck.get("note"), NOTE, "the reason is kalshi_unplaceable")
    ok(stuck.get("settled") not in (None, ""), "the retired row has a retired timestamp")
    live = [q for q in mma if q.get("bet") and q.get("status") == "open"]
    eq([(q.get("venue"), q.get("price"), q.get("market_id")) for q in live],
       [("polymarket_us", 0.86, pmus["market_id"])],
       "one Polymarket US entry replaces it at the live price")
    if live and live[0].get("venue") == "polymarket_us":
        eq(live[0]["venue"], "polymarket_us", "the replacement is on Polymarket US")
        eq(live[0]["price"], 0.86, "the replacement uses the live Polymarket US price")
        eq(live[0]["price"] != 0.88, True, "the Kalshi price is not reused")
        logged_at = datetime.fromisoformat(live[0]["logged"])
        retired_at = datetime.fromisoformat(stuck["settled"])
        ok(t0 <= logged_at <= t1, "logged_at is the time this row was logged")
        ok(t0 <= retired_at <= t1, "the retirement is stamped during this run")
        eq(live[0]["logged"] != "2026-09-29T15:48:21+00:00", True, "the old Kalshi log time is not reused")
    _publish(moved, {"mma": [pmus]})
    eq(len([q for q in moved["quotes"] if q.get("source") == "mma_fav_band"]), 2,
       "a second run does not add a third entry")
    eq(len([q for q in moved["quotes"] if q.get("source") == "mma_fav_band" and q.get("bet")
            and q.get("status") == "open"]), 1,
       "one fight never has two live entries")

    print("\nPolymarket US has already started: the Kalshi bet stays")
    # Kalshi's own start is a placeholder hours later. Retirement looks at the
    # Polymarket US start, so a fight already under way is not voided.
    when = datetime(2026, 10, 3, 21, 0, tzinfo=timezone.utc)
    k_start = datetime(2026, 10, 4, 0, 0, tzinfo=timezone.utc)
    p_start = datetime(2026, 10, 3, 20, 30, tzinfo=timezone.utc)
    underway = _open_kalshi("KXUFCFIGHT-26OCT03WINARM", "Anthony Wint", "Lucas Armand",
                            k_start, price=0.82)
    underway_before = copy.deepcopy(underway)
    underway_pm = _row("aec-ufc-antwin-lucarm-2026-10-03", "polymarket_us",
                       "Anthony Wint", "Lucas Armand", 0.83, 0.19, p_start)
    underway_book = {"quotes": [underway], "meta": {}, "coverage": {}}
    _publish(underway_book, {"mma": [underway_pm]}, now=when)
    eq(underway, underway_before,
       "an open Kalshi bet stays when Polymarket US has already started")
    eq([q for q in underway_book["quotes"]
        if q.get("source") == "mma_fav_band" and q.get("venue") == "polymarket_us"],
       [], "no Polymarket US entry is logged for a fight that has started there")

    print("\na contest that starts during the fetch is not logged")
    # publish() used to stamp every quote with the clock from the start of the
    # run. A fetch that outlasts a start then logged the bet with `logged`
    # before the start, and retire_late did not void it.
    t_fetch = datetime.now(timezone.utc).replace(microsecond=0)
    mid_start = t_fetch + timedelta(seconds=30)
    clock = {"t": t_fetch}

    def _fake_clock():
        return clock["t"]

    def _advance(sport):
        clock["t"] = mid_start + timedelta(seconds=5)
        return [dict(market_id="KXUFCFIGHT-MIDFETCH", pick="a")]

    mid_row = _row("KXUFCFIGHT-MIDFETCH", "polymarket_us", "Mid Fetch", "Late Start",
                   0.82, 0.20, mid_start)
    mid_book = {"quotes": [], "meta": {}, "coverage": {}}
    saved_ch, saved_uni = S.CHALLENGERS, S.UNIVERSE
    saved_clock = getattr(T, "_clock", None)
    S.CHALLENGERS = {"mma_fav_band": _advance}
    if saved_clock is not None:
        T._clock = _fake_clock
    try:
        T.publish(mid_book, {"mma": [mid_row]}, {}, verbose=False)
    finally:
        if saved_clock is not None:
            T._clock = saved_clock
        S.CHALLENGERS = saved_ch
        S.UNIVERSE = saved_uni
    eq(_bets(mid_book, "mma_fav_band"), [],
       "a contest that starts during the fetch is not logged")
    T.retire_late(mid_book, verbose=False)
    eq(_bets(mid_book, "mma_fav_band"), [],
       "retire_late is not left to clean up a back-dated log")

    print("\nafter the fight starts, nothing switches")
    started = _open_kalshi("KXUFCFIGHT-26OCT03WINARM", "Anthony Wint", "Lucas Armand", past)
    before = copy.deepcopy(started)
    late_pm = _row("aec-ufc-winarm-2026-10-03", "polymarket_us", "Anthony Wint", "Lucas Armand",
                   0.79, 0.23, past)
    late = {"quotes": [started], "meta": {}, "coverage": {}}
    _publish(late, {"mma": [late_pm]})
    eq(started, before, "a started Kalshi entry is left alone")
    eq(_bets(late, "mma_fav_band"), [started], "no Polymarket US entry is logged after the start")

    print("\nother rules are unchanged, and another retirement still blocks")
    # Inside the 3-hour window the kept tennis lane still uses. The wide rule is off the board.
    near = (datetime.now(timezone.utc) + timedelta(hours=1)).replace(microsecond=0)
    t_k = _row("KXATPMATCH-26OCT03ALPHBE", "kalshi", "Alex Alpha", "Blake Beta",
               0.78, 0.24, near, sport="tennis")
    t_k["start_source"] = "tennisexplorer"
    t_p = _row("aec-atp-alpha-beta-2026-10-03", "polymarket_us", "Alex Alpha", "Blake Beta",
               0.79, 0.23, near, sport="tennis")
    tennis = {"quotes": [], "meta": {}, "coverage": {}}
    _publish(tennis, {"tennis": [t_k, t_p]})
    tennis_bets = _bets(tennis, "tennis_fav_band_3h")
    eq([(q["venue"], q["market_id"]) for q in tennis_bets], [("kalshi", t_k["market_id"])],
       "the 3-hour favourite band still books the first venue, which is Kalshi when it is listed first")
    ok(not _bets(tennis, "tennis_fav_band"), "the wide favourite-band rule logs nothing")
    held = dict(id="tennis_fav_band_3h:KXATPMATCH-26OCT03HELD", source="tennis_fav_band_3h",
                sport="tennis", venue="kalshi", market_id="KXATPMATCH-26OCT03HELD",
                status="open", bet=True, pick="a", price=0.78, price_a=0.78, price_b=0.24,
                stake=100.0, pnl=0.0, side_a="Cara Cole", side_b="Dana Dale",
                start=near.isoformat(), date=near.date().isoformat(),
                logged="2026-09-29T12:00:00+00:00")
    dup_row = _row("aec-atp-cole-dale-2026-10-03", "polymarket_us", "Cara Cole", "Dana Dale",
                   0.78, 0.24, near, sport="tennis")
    dup = {"quotes": [held], "meta": {}, "coverage": {}}
    _publish(dup, {"tennis": [dup_row]})
    eq([q["id"] for q in dup["quotes"] if q.get("source") == "tennis_fav_band_3h"],
       [held["id"]], "a non-MMA duplicate is still blocked")
    other = _open_kalshi("KXUFCFIGHT-26OCT03PINPUL", "Damian Pinas", "Andrey Pulyaev", soon, price=0.81)
    other["status"] = "void"
    other["bet"] = False
    other["stake"] = 0.0
    other["note"] = T.DUPLICATE_NOTE
    other["settled"] = "2026-09-29T18:00:00+00:00"
    other_pm = _row("aec-ufc-pinpul-2026-10-03", "polymarket_us", "Damian Pinas", "Andrey Pulyaev",
                    0.84, 0.18, soon)
    blocked = {"quotes": [other], "meta": {}, "coverage": {}}
    _publish(blocked, {"mma": [other_pm]})
    eq(_bets(blocked, "mma_fav_band"), [],
       "a Kalshi MMA row retired for any other reason still blocks a second bet")
    eq(other["note"], T.DUPLICATE_NOTE, "that other retirement is not rewritten")

    print("\nthe retired row is out of the counts, and the audit is clean")
    retired = stuck
    replacement = next((q for q in live if q.get("venue") == "polymarket_us"), None)
    ok(retired["id"] not in SB.open_rows(moved)[0] and not retired.get("bet"),
       "bets running does not include the retired row")
    record = T.assess(moved, "mma_fav_band", "mma")
    eq((record["n"], record["pnl"]), (0, 0.0),
       "the retired row is not in the MMA record or its P/L")
    window = soon - timedelta(minutes=30)
    fetched = []

    def _price(q):
        fetched.append(q["id"])
        return 0.5

    SC.run(moved, {"closes": {}}, now=window, price=_price)
    ok(retired["id"] not in fetched, "no closing price is fetched for the retired row")
    if replacement:
        ok(replacement["id"] in fetched, "the Polymarket US row is still priced")
    resolved = []
    saved_k, saved_pm = S.resolve_kalshi, S.resolve_polymarket_us

    def _kalshi(mid):
        resolved.append(("kalshi", mid))
        return "a"

    def _pm(mid):
        resolved.append(("polymarket_us", mid))
        return "a"

    S.resolve_kalshi, S.resolve_polymarket_us = _kalshi, _pm
    try:
        T.grade(moved, verbose=False, now=soon + timedelta(hours=5), mismatches=set())
    finally:
        S.resolve_kalshi, S.resolve_polymarket_us = saved_k, saved_pm
    eq((retired.get("status"), retired.get("bet"), retired.get("note"), retired.get("pnl")),
       ("void", False, NOTE, 0.0), "grade() leaves the retired row frozen")
    ok(("kalshi", retired["market_id"]) not in resolved,
       "grade() does not resolve the retired Kalshi market")
    if replacement:
        eq(replacement.get("status"), "won", "grade() still settles the Polymarket US row")
        ok(("polymarket_us", replacement["market_id"]) in resolved,
           "grade() still resolves the Polymarket US market")

    planted = dict(id="espn_fpi:probe-mlb", source="espn_fpi", sport="nfl", venue="kalshi",
                   market_id="probe-mlb", bet=True, pick="a", price=0.60, price_a=0.60,
                   price_b=0.42, stake=100.0, result="a", status="won",
                   pnl=round(100.0 * (1.0 / 0.60 - 1.0), 2),
                   side_a="Alpha", side_b="Beta",
                   start=(soon - timedelta(days=5)).isoformat(),
                   logged=(soon - timedelta(days=6)).isoformat(),
                   settled=(soon - timedelta(days=4)).isoformat())
    audit_d = {"quotes": list(moved["quotes"]) + [planted], "meta": {"updated": soon.isoformat()}}
    bet_rep = A.Report()
    A.check_bets(audit_d, bet_rep)
    dup_rep = A.Report()
    A.check_duplicates(audit_d, dup_rep)
    stale_rep = A.Report()
    A.check_stale(audit_d, stale_rep, False, now=soon)
    settle_calls = []

    def _settle(mid):
        settle_calls.append(mid)
        return "a"

    fd, watch = tempfile.mkstemp(prefix="mma-settle-", suffix=".json")
    os.close(fd)
    os.remove(watch)
    saved_res = S.resolve_kalshi
    S.resolve_kalshi = _settle
    try:
        settle_rep = A.Report()
        A.check_settlement(audit_d, settle_rep, 25, path=watch)
    finally:
        S.resolve_kalshi = saved_res
        try:
            os.remove(watch)
        except OSError:
            pass
    ok(not bet_rep.errors and not dup_rep.errors and not stale_rep.errors and not settle_rep.errors,
       "bets, duplicates, stale and settlement are clean with the retired row in the ledger"
       + ("" if not (bet_rep.errors or dup_rep.errors or stale_rep.errors or settle_rep.errors)
          else f" — {(bet_rep.errors + dup_rep.errors + stale_rep.errors + settle_rep.errors)[:3]}"))
    ok(retired["market_id"] not in settle_calls, "settlement does not re-resolve the retired market")
    ok("probe-mlb" in settle_calls, "settlement still samples a non-MMA settled bet")
    # The cases above lift mma_fav_band out of REMOVED_SOURCES so the
    # replacement can run. The committed stages file may still name that pair
    # as Production until the next tracker run. Put the source back for this
    # check: off the board, the audit warns and does not error.
    held_removed = S.REMOVED_SOURCES
    S.REMOVED_SOURCES = held_removed | {"mma_fav_band"}
    try:
        prod_rep = A.Report()
        A.check_production(audit_d, T.load_stages(), prod_rep)
    finally:
        S.REMOVED_SOURCES = held_removed
    ok(not prod_rep.errors, "the production check stays clean"
       + ("" if not prod_rep.errors else f" — {prod_rep.errors[:2]}"))

    print("\nfrozen ledger: Smith stays, the other three move")
    # Built in the test. No ledger file and no wall clock. Smith is 0.90 on
    # Polymarket US, outside the band, so that Kalshi bet stays open.
    frozen_now = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)
    frozen_st = {"pairs": {"mma_fav_band|mma": {
        "stage": "production", "ready_at": "2026-09-01T00:00:00+00:00",
        "promoted_at": "2026-09-01T00:00:00+00:00", "by_hand": "2026-09-01"}}}

    def _settled(mid, side_a, side_b, start, price, status):
        pnl = (-100.0 if status == "lost"
               else round(100.0 * (1.0 / price - 1.0), 2))
        return dict(id=f"mma_fav_band:{mid}", source="mma_fav_band", sport="mma",
                    venue="kalshi", market_id=mid, status=status, bet=True, pick="a",
                    price=price, price_a=price, price_b=round(1.02 - price, 2),
                    stake=100.0, pnl=pnl, side_a=side_a, side_b=side_b,
                    start=start.isoformat(), date=start.date().isoformat(),
                    logged="2026-09-26T18:00:00+00:00",
                    settled="2026-09-27T04:00:00+00:00",
                    start_source="venue", result="a" if status == "won" else "b")

    card = [
        ("KXUFCFIGHT-26OCT03SMIWHI", "Jacobe Smith", "Bruce Whitehead",
         datetime(2026, 10, 3, 22, 20, tzinfo=timezone.utc), 0.88, "a",
         "aec-ufc-jacsmi-bruwhi-2026-10-03", 0.90, 0.12),
        ("KXUFCFIGHT-26OCT03WINARM", "Anthony Wint", "Lucas Armand",
         datetime(2026, 10, 4, 0, 0, tzinfo=timezone.utc), 0.82, "a",
         "aec-ufc-antwin-lucarm-2026-10-03", 0.83, 0.19),
        ("KXUFCFIGHT-26OCT03PINPUL", "Damian Pinas", "Andrey Pulyaev",
         datetime(2026, 10, 4, 0, 40, tzinfo=timezone.utc), 0.81, "a",
         "aec-ufc-dampin-andpul-2026-10-03", 0.81, 0.21),
        ("KXUFCFIGHT-26OCT03FIGTAL", "Deiveson Figueiredo", "Payton Talbott",
         datetime(2026, 10, 4, 3, 0, tzinfo=timezone.utc), 0.82, "b",
         "aec-ufc-deifig-paytal-2026-10-03", 0.19, 0.83),
    ]
    before = {"quotes": [
        _settled("KXUFCFIGHT-26SEP26DEMJAU", "Vanessa Demopoulos", "Yazmin Jauregui",
                 datetime(2026, 9, 26, 23, 0, tzinfo=timezone.utc), 0.80, "won"),
        _settled("KXUFCFIGHT-26SEP26HIENAK", "Brady Hiestand", "Rinya Nakamura",
                 datetime(2026, 9, 27, 3, 0, tzinfo=timezone.utc), 0.82, "lost"),
        _settled("KXUFCFIGHT-26SEP27CASHEI", "Cory Sandhagen", "Heinisch",
                 datetime(2026, 9, 27, 5, 0, tzinfo=timezone.utc), 0.81, "lost"),
    ], "meta": {}, "coverage": {}}
    listings = []
    for mid, a, b, start, px, pick, slug, pa, pb in card:
        before["quotes"].append(_open_kalshi(mid, a, b, start, price=px, pick=pick))
        listings.append(_row(slug, "polymarket_us", a, b, pa, pb, start))
    after = copy.deepcopy(before)
    pre = _page(before, frozen_st, frozen_now)
    _publish(after, {"mma": listings}, now=frozen_now)
    post = _page(after, frozen_st, frozen_now)
    retired_ids = sorted(q["id"] for q in after["quotes"] if q.get("note") == NOTE)
    added = [q for q in after["quotes"] if q.get("source") == "mma_fav_band" and q.get("bet")
             and q.get("venue") == "polymarket_us" and q.get("status") == "open"]
    smith = next(q for q in after["quotes"] if q["id"] == "mma_fav_band:KXUFCFIGHT-26OCT03SMIWHI")
    print(f"  before  settled {pre['settled']} · void {pre['void']} · "
          f"bets running {pre['running']} · no edge {pre['noedge']} · held back {pre['held']}")
    print(f"  after   settled {post['settled']} · void {post['void']} · "
          f"bets running {post['running']} · no edge {post['noedge']} · held back {post['held']}")
    eq(retired_ids, [
        "mma_fav_band:KXUFCFIGHT-26OCT03FIGTAL",
        "mma_fav_band:KXUFCFIGHT-26OCT03PINPUL",
        "mma_fav_band:KXUFCFIGHT-26OCT03WINARM",
    ], "the three in-band Kalshi picks are retired")
    eq((smith["status"], smith["bet"], smith.get("note"), smith["price"]),
       ("open", True, None, 0.88),
       "Smith stays on Kalshi when Polymarket US is 0.90, outside the band")
    eq(sorted((q["market_id"], q["pick"], q["price"]) for q in added), [
        ("aec-ufc-antwin-lucarm-2026-10-03", "a", 0.83),
        ("aec-ufc-dampin-andpul-2026-10-03", "a", 0.81),
        ("aec-ufc-deifig-paytal-2026-10-03", "b", 0.83),
    ], "three Polymarket US entries are logged at the in-band asks")
    eq(pre["held"], 7, "the frozen card holds back 7 Kalshi bets")
    eq(post["held"], 4, "Smith and the three settled Kalshi fights stay held back")
    eq((post["settled"], post["void"], post["running"], post["noedge"]),
       (pre["settled"], pre["void"], pre["running"], pre["noedge"]),
       "settled, void, bets running and no edge are unchanged")
    rep = A.Report()
    A.check_bets(after, rep)
    A.check_duplicates(after, rep)
    A.check_stale(after, rep, False, now=frozen_now)
    A.check_records(after, frozen_st, rep)
    ok(not rep.errors, "the frozen ledger audits clean"
       + ("" if not rep.errors else f" — {rep.errors[:3]}"))

    print(f"\n{'FAILED: ' + str(len(FAILS)) if FAILS else 'mma venue passed'}")
    for item in FAILS:
        print(f"  - {item}")
    return 1 if FAILS else 0


if __name__ == "__main__":
    raise SystemExit(main())
