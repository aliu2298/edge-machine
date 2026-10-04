#!/usr/bin/env python3
"""A space inside an MMA or boxing name is still that fighter.

John Castaneda vs Alatengheili and vs Alateng Heili are one bout. The Kalshi
copy is voided. Tennis, a rematch, a series game, and a different opponent
stay apart. Nothing here reads data/ or the network.
"""
import copy
import sys

import sandbox_audit as A
import sandbox_sources as S
import sandbox_track as T

FAILS = []
KALSHI = "mma_fav_band:KXUFCFIGHT-26SEP26CASHEI"
POLY = "mma_fav_band:aec-ufc-johcas-alaten-2026-09-26"


def ok(cond, why):
    print(f"  {'ok  ' if cond else 'FAIL'} {why}")
    if not cond:
        FAILS.append(why)


def eq(got, want, why):
    ok(got == want, f"{why} — got {got!r}, want {want!r}" if got != want else why)


def _castaneda(row_id, venue, side_b, logged, start, **kw):
    q = dict(
        id=row_id, source="mma_fav_band", sport="mma", venue=venue, bet=True,
        status="lost", pnl=-100.0, stake=100.0, price=0.75, pick="a", result="b",
        side_a="John Castaneda", side_b=side_b, market_id=row_id.split(":", 1)[-1],
        logged=logged, start=start, date="2026-09-26",
        settled="2026-09-27T01:28:01+00:00",
    )
    q.update(kw)
    return q


def _book():
    kalshi = _castaneda(
        KALSHI, "kalshi", "Alateng Heili",
        "2026-09-25T13:45:06+00:00", "2026-09-26T21:05:00+00:00")
    poly = _castaneda(
        POLY, "polymarket_us", "Alatengheili",
        "2026-09-24T22:06:45+00:00", "2026-09-26T21:30:00+00:00")
    other = _castaneda(
        "mma_fav_band:other-fight", "kalshi", "Other Fighter",
        "2026-09-25T13:45:06+00:00", "2026-09-26T21:05:00+00:00",
        market_id="KXUFCFIGHT-26SEP26OTHER")
    return {"quotes": [poly, kalshi, other], "retired": {}, "_archive": []}


def test_castaneda_matches_and_only_the_kalshi_copy_is_voided():
    print("Castaneda: the split name matches, and only the Kalshi copy is voided")
    joined = getattr(S, "_joined", None)
    if joined is None:
        ok(False, "spaces and case fold out of the name")
    else:
        eq(joined("Alateng Heili"), "alatengheili", "spaces and case fold out of the name")
    eq(S._score("Alateng Heili", "Alatengheili", "mma"), 1.0,
       "the MMA spelling fallback treats the split name as the same fighter")
    eq(S._score("Alateng Heili", "Alatengheili", "boxing"), 1.0,
       "boxing uses the same join")
    score, flipped = S.pair_match(
        "John Castaneda", "Alatengheili", "John Castaneda", "Alateng Heili", sport="mma")
    eq(score, 1.0, "the Castaneda pair matches")
    eq(flipped, False, "the two copies are the same way round")
    ok(hasattr(T, "void_listed_settled_dups"), "the tracker step exists")
    if not hasattr(T, "void_listed_settled_dups"):
        return
    eq(T.SETTLED_DUP_VOIDS.get(KALSHI), POLY, "the Kalshi id is the listed row, Polymarket US stands")
    d = _book()
    kept_before = copy.deepcopy(d["quotes"][0])
    other_before = copy.deepcopy(d["quotes"][2])
    settled = d["quotes"][1]["settled"]
    n = T.void_listed_settled_dups(d, verbose=False)
    voided = d["quotes"][1]
    eq(n, 1, "one row is voided")
    eq(voided["status"], "void", "the Kalshi copy is void")
    eq(voided["pnl"], 0.0, "the void carries no P/L")
    eq(voided["note"], f"dup of {POLY}", "the note names the kept id")
    eq(voided["settled"], settled, "the settled time stays")
    eq(voided["id"], KALSHI, "the voided row is the Kalshi id")
    eq(d["quotes"][0], kept_before, "the Polymarket US copy is untouched")
    eq(d["quotes"][2], other_before, "a different opponent in the same book is untouched")
    again = T.void_listed_settled_dups(d, verbose=False)
    eq(again, 0, "a second call voids nothing")
    eq(voided["settled"], settled, "the second call leaves the settled time")
    eq(voided["note"], f"dup of {POLY}", "the second call leaves the note")

    refused = _book()
    refused["quotes"][0]["side_b"] = "Someone Else"
    eq(T.void_listed_settled_dups(refused, verbose=False), 0,
       "a listed id whose opponent does not match is not voided")
    eq(refused["quotes"][1]["status"], "lost", "that Kalshi copy stays a loss")


def test_these_stay_apart():
    print("a different opponent, a rematch, a series, and tennis stay apart")
    eq(S.pair_match("John Castaneda", "Alatengheili", "John Castaneda", "Someone Else",
                    sport="mma")[0], 0.0, "a different opponent does not match")
    first = _castaneda(KALSHI, "kalshi", "Alateng Heili",
                       "2026-09-11T13:45:06+00:00", "2026-09-12T21:05:00+00:00",
                       date="2026-09-12")
    rematch = _castaneda(POLY, "polymarket_us", "Alatengheili",
                         "2026-09-24T22:06:45+00:00", "2026-09-26T21:30:00+00:00")
    ok(not T._same_contest_quote(first, rematch), "a rematch two weeks later is not the same contest")
    eq(T.settled_cross_venue_dups([first, rematch]), [], "the rematch is not a duplicate")

    nxt = dict(sport="mlb", venue="polymarket_us", market_id="aec-mlb-tb-nyy-2026-09-23",
               side_a="Tampa Bay Rays", side_b="New York Yankees",
               start="2026-09-23T23:10:00+00:00", date="2026-09-23")
    kalshi = dict(sport="mlb", venue="kalshi", market_id="KXMLBGAME-26SEP22TBNYY",
                  side_a="Tampa Bay Rays", side_b="New York Yankees",
                  start="2026-09-23T07:10:00+00:00", date="2026-09-22")
    ok(not T._same_contest_quote(nxt, kalshi), "an MLB series game stays apart")
    eq(S._score("Boston Red Sox", "Chicago White Sox", "mlb") == 1.0, False,
       "the join rule does not score two MLB clubs as one")

    eq(S.pair_match("Nika Radisic", "Viktoria Morvayova", "Joanna Garland", "Viktoria Morvayova",
                    sport="tennis")[0], 0.0,
       "Radisic v Morvayova stays apart from Garland v Morvayova")
    eq(S.pair_match("Hunter / Krawczyk", "Ninomiya M / Radisic N",
                    "Joanna Garland", "Viktoria Morvayova", sport="tennis")[0], 0.0,
       "Radisic/Garland v Morvayova tennis doubles stays apart")
    eq(S._score("Alateng Heili", "Alatengheili", "tennis"), 0.0,
       "a tennis name that would join-equal does not match")


def test_audit_warns_on_a_removed_lane_duplicate():
    print("the audit warns on a removed-lane duplicate")
    later = _castaneda(KALSHI, "kalshi", "Alateng Heili",
                       "2026-09-25T13:45:06+00:00", "2026-09-26T21:05:00+00:00")
    kept = _castaneda(POLY, "polymarket_us", "Alatengheili",
                      "2026-09-24T22:06:45+00:00", "2026-09-26T21:30:00+00:00")
    rep = A.Report()
    A.check_duplicates({"quotes": [kept, later]}, rep)
    ok(not rep.errors, "a removed-lane duplicate is not an error")
    ok(any(KALSHI in m and POLY in m for _c, m in rep.warnings),
       "a removed-lane duplicate is a warning")
    ok(not any("no settled bet repeats" in m for _c, m in rep.passed),
       "the audit does not call that duplicate clean")

    live_a = dict(kept, id="oddspedia:a", source="oddspedia", sport="cricket",
                  side_a="Australia", side_b="England", market_id="aec-cric-a")
    live_b = dict(later, id="oddspedia:b", source="oddspedia", sport="cricket",
                  side_a="Australia", side_b="England", market_id="KXCRICKET-B")
    live = A.Report()
    A.check_duplicates({"quotes": [live_a, live_b]}, live)
    ok(live.errors and not live.warnings, "a duplicate on a lane still on the board is an error")


def main():
    test_castaneda_matches_and_only_the_kalshi_copy_is_voided()
    print()
    test_these_stay_apart()
    print()
    test_audit_warns_on_a_removed_lane_duplicate()
    print()
    if FAILS:
        print(f"FAIL {len(FAILS)}")
        return 1
    print("PASS name join")
    return 0


if __name__ == "__main__":
    sys.exit(main())
