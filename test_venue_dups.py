#!/usr/bin/env python3
"""Duplicate, window, and void checks. Stdlib assertions, collected by pytest too.

Run with `python3 test_venue_dups.py` or `python3 -m pytest test_venue_dups.py -v`.
"""
import importlib.util
import json
import os
import sys
import tempfile

import sandbox_sources as S
import sandbox_track as T

ROOT = os.path.dirname(os.path.abspath(__file__))


def _void():
    path = os.path.join(ROOT, "scripts", "void_venue_dups.py")
    assert os.path.exists(path), f"void script missing at {path}"
    spec = importlib.util.spec_from_file_location("void_venue_dups_checks", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _fight(market_id, venue, start, **kw):
    q = dict(sport="mma", venue=venue, market_id=market_id, source="mma_fav_band",
             side_a="Vanessa Demopoulos", side_b="Yazmin Jauregui",
             start=start, date="2026-09-26")
    q.update(kw)
    return q


def test_duplicate_kalshi_and_polymarket_us_of_one_fight():
    """The later settled copy of one fight, on the other venue, is a duplicate."""
    assert hasattr(T, "settled_cross_venue_dups"), "settled_cross_venue_dups is missing"
    kept = _fight("KXUFCFIGHT-26SEP26DEMJAU", "kalshi", "2026-09-26T23:00:00+00:00",
                  id="mma_fav_band:KXUFCFIGHT-26SEP26DEMJAU", bet=True, status="won",
                  pnl=14.94, logged="2026-09-22T00:41:36+00:00")
    later = _fight("aec-ufc-vandem-yazjau-2026-09-26", "polymarket_us",
                   "2026-09-26T18:30:00+00:00",
                   id="mma_fav_band:aec-ufc-vandem-yazjau-2026-09-26", bet=True,
                   status="won", pnl=14.94, logged="2026-09-22T21:47:04+00:00")
    pairs = T.settled_cross_venue_dups([kept, later])
    assert pairs, "the Polymarket US copy was not flagged as a duplicate of the Kalshi bet"
    assert pairs[0][0]["id"] == later["id"]
    assert pairs[0][1]["id"] == kept["id"]


def test_window_matches_a_4_5h_kalshi_placeholder():
    """Kalshi's start for Demopoulos vs Jauregui is 4.5h off Polymarket US. One contest."""
    kx = _fight("KXUFCFIGHT-26SEP26DEMJAU", "kalshi", "2026-09-26T23:00:00+00:00")
    pm = _fight("aec-ufc-vandem-yazjau-2026-09-26", "polymarket_us", "2026-09-26T18:30:00+00:00")
    assert T._same_contest_quote(kx, pm), "a 4.5h Kalshi placeholder was not the same contest"


def test_window_matches_an_8_5h_kalshi_placeholder():
    """Hiestand vs Nakamura: Kalshi 03:00 the next morning, Polymarket US 18:30. Still one fight."""
    kx = _fight("KXUFCFIGHT-26SEP26HIENAK", "kalshi", "2026-09-27T03:00:00+00:00",
                side_a="Brady Hiestand", side_b="Rinya Nakamura")
    pm = _fight("aec-ufc-brahie-rinnak-2026-09-26", "polymarket_us", "2026-09-26T18:30:00+00:00",
                side_a="Brady Hiestand", side_b="Rinya Nakamura")
    assert T._same_contest_quote(kx, pm), "an 8.5h Kalshi placeholder was not the same contest"


def test_window_does_not_match_a_doubleheader():
    """Rays vs Yankees dh1 and dh2 are 6h apart. The 12h window does not apply to baseball."""
    g1 = dict(sport="mlb", venue="polymarket_us", market_id="aec-mlb-tb-nyy-2026-09-22-dh1",
              side_a="Tampa Bay Rays", side_b="New York Yankees",
              start="2026-09-22T17:05:00+00:00", date="2026-09-22")
    g2 = dict(g1, market_id="aec-mlb-tb-nyy-2026-09-22-dh2", venue="kalshi",
              start="2026-09-22T23:05:00+00:00")
    assert not T._same_contest_quote(g1, g2), "dh1 and dh2 were treated as one contest"


def test_window_does_not_match_the_next_game_of_a_series():
    """The next Rays/Yankees game is a day later. A Kalshi start 8h off must not glue them."""
    nxt = dict(sport="mlb", venue="polymarket_us", market_id="aec-mlb-tb-nyy-2026-09-23",
               side_a="Tampa Bay Rays", side_b="New York Yankees",
               start="2026-09-23T23:10:00+00:00", date="2026-09-23")
    kalshi = dict(sport="mlb", venue="kalshi", market_id="KXMLBGAME-26SEP22TBNYY",
                  side_a="Tampa Bay Rays", side_b="New York Yankees",
                  start="2026-09-23T07:10:00+00:00", date="2026-09-22")
    assert not T._same_contest_quote(nxt, kalshi), "the next game of a series was treated as one contest"


def test_window_same_day_cricket_rematch_past_12h_is_not_a_duplicate():
    """Australia v England, two T20s on 2026-09-20, a morning match and a night match 14h later.

    Cricket is not baseball or table tennis, so the 12h Kalshi window applies. A placeholder
    start is 4.5 to 8.5 hours off the real start. Fourteen hours is a second match on the
    same date, not one match's clock error, even though the sides agree and one id is a
    Kalshi ticker. The night match must not be retired or voided as a duplicate.
    """
    assert S.pair_match("Australia", "England", "Australia", "England", sport="cricket")[0] > 0
    morning = dict(sport="cricket", venue="kalshi", source="cricket_consensus",
                   market_id="KXCRICKETT20MATCH-26SEP20AUSENG",
                   side_a="Australia", side_b="England",
                   start="2026-09-20T06:00:00+00:00", date="2026-09-20")
    same_match = dict(morning, venue="polymarket_us", market_id="aec-cric-aus-eng-2026-09-20",
                      start="2026-09-20T14:00:00+00:00")
    night = dict(sport="cricket", venue="polymarket_us", source="cricket_consensus",
                 market_id="aec-cric-aus-eng-2026-09-20-2",
                 side_a="Australia", side_b="England",
                 start="2026-09-20T20:00:00+00:00", date="2026-09-20")
    assert T._same_contest_quote(morning, same_match), (
        "the same T20 with a Kalshi start 8h off was not one contest")
    assert not T._same_contest_quote(morning, night), (
        "a same-day cricket rematch 14h apart was treated as one contest")
    bets = [
        dict(morning, id="cricket_consensus:KXCRICKETT20MATCH-26SEP20AUSENG", bet=True,
             status="lost", pnl=-100.0, logged="2026-09-20T01:00:00+00:00"),
        dict(night, id="cricket_consensus:aec-cric-aus-eng-2026-09-20-2", bet=True,
             status="lost", pnl=-100.0, logged="2026-09-20T12:00:00+00:00"),
    ]
    assert hasattr(T, "settled_cross_venue_dups")
    assert T.settled_cross_venue_dups(bets) == [], "the night T20 was flagged as a duplicate"
    open_rows = {"quotes": [
        dict(morning, id="cricket_consensus:KXCRICKETT20MATCH-26SEP20AUSENG", status="open",
             bet=True, logged="2026-09-20T01:00:00+00:00"),
        dict(night, id="cricket_consensus:aec-cric-aus-eng-2026-09-20-2", status="open",
             bet=True, logged="2026-09-20T12:00:00+00:00"),
    ]}
    assert T.retire_venue_duplicates(open_rows, verbose=False) == 0
    assert [q["status"] for q in open_rows["quotes"]] == ["open", "open"]


def _sample_pair():
    kept = dict(id="mma_fav_band:KXUFCFIGHT-26SEP26DEMJAU", source="mma_fav_band", sport="mma",
                venue="kalshi", market_id="KXUFCFIGHT-26SEP26DEMJAU", bet=True, status="won",
                result="b", pnl=14.94, price=0.87, pick="b", stake=100.0,
                side_a="Vanessa Demopoulos", side_b="Yazmin Jauregui",
                start="2026-09-26T23:00:00+00:00", date="2026-09-26",
                logged="2026-09-22T00:41:36+00:00", settled="2026-09-27T01:27:39+00:00")
    later = dict(kept, id="mma_fav_band:aec-ufc-vandem-yazjau-2026-09-26",
                 market_id="aec-ufc-vandem-yazjau-2026-09-26", venue="polymarket_us",
                 start="2026-09-26T18:30:00+00:00", logged="2026-09-22T21:47:04+00:00",
                 settled="2026-09-26T21:29:23+00:00")
    return kept, later


def test_void_later_copy_and_second_apply_writes_nothing():
    """--apply voids the later copy once. A second --apply does not rewrite the file."""
    V = _void()
    kept, later = _sample_pair()
    fresh = {"quotes": [dict(kept), dict(later)], "meta": {"runs": 3}, "retired": {}}
    directory = tempfile.mkdtemp()
    path = os.path.join(directory, "ledger.json")
    V.run(apply=True, load=lambda: fresh, path=path)
    once = open(path).read()
    loaded = json.loads(once)
    voided = next(q for q in loaded["quotes"] if q["id"] == later["id"])
    assert voided["status"] == "void"
    assert voided["pnl"] == 0.0
    assert voided["note"] == "dup of mma_fav_band:KXUFCFIGHT-26SEP26DEMJAU"
    assert voided["settled"] == "2026-09-26T21:29:23+00:00"
    V.run(apply=True, load=lambda: json.load(open(path)), path=path)
    assert open(path).read() == once, "a second --apply rewrote the ledger"


def test_void_apply_aborts_without_writing_when_not_confirmed():
    """If confirm_untouched reports NOT CONFIRMED, --apply exits and leaves the file alone.

    The planted fault is a void that also rewrites the kept row's P/L. That is outside
    the fields a void is allowed to change, so the check must refuse the write.
    """
    V = _void()
    kept, later = _sample_pair()
    src = {"quotes": [dict(kept), dict(later)], "meta": {"runs": 3}, "retired": {}}
    directory = tempfile.mkdtemp()
    path = os.path.join(directory, "ledger.json")
    with open(path, "w") as fh:
        json.dump(src, fh)
    before = open(path, "rb").read()
    real = V.apply_voids

    def apply_and_touch_kept(d):
        changes = real(d)
        for q in d["quotes"]:
            if q.get("id") == kept["id"]:
                q["pnl"] = 999.0
        return changes

    V.apply_voids = apply_and_touch_kept
    try:
        try:
            V.run(apply=True, load=lambda: json.load(open(path)), path=path)
        except SystemExit as exc:
            assert exc.code not in (0, None), f"--apply exited {exc.code}, want non-zero"
        else:
            raise AssertionError("--apply wrote anyway when confirm_untouched was NOT CONFIRMED")
    finally:
        V.apply_voids = real
    assert open(path, "rb").read() == before, "the ledger was written after NOT CONFIRMED"


def test_hontama_lee_bracket_and_hyphen_are_the_same_player():
    """Kalshi 'Eunhye Lee (b. 2000)' and Polymarket US 'Eun-Hye Lee' are one opponent.

    Mai Hontama vs Eunhye Lee, starts 0.3h apart. The birth-year aside and the hyphen
    must not hide the duplicate.
    """
    score = S.pair_match("Mai Hontama", "Eunhye Lee (b. 2000)", "Mai Hontama", "Eun-Hye Lee",
                         sport="tennis")[0]
    assert score > 0, f"name score was {score}, want > 0"
    kalshi = dict(sport="tennis", venue="kalshi", source="tennis_fav_band",
                  market_id="KXWTAMATCH-26SEP18HONLEE",
                  side_a="Mai Hontama", side_b="Eunhye Lee (b. 2000)",
                  start="2026-09-19T03:10:00+00:00", date="2026-09-18")
    pm = dict(sport="tennis", venue="polymarket_us", source="tennis_fav_band",
              market_id="aec-wta-maihon-eunlee-2026-09-18",
              side_a="Mai Hontama", side_b="Eun-Hye Lee",
              start="2026-09-19T03:30:00+00:00", date="2026-09-19")
    assert T._same_contest_quote(kalshi, pm), "Hontama v Lee was not one contest"


if __name__ == "__main__":
    failed = 0
    for name in sorted(n for n in list(globals()) if n.startswith("test_")):
        try:
            globals()[name]()
        except Exception as exc:
            failed += 1
            print(f"FAIL {name}: {exc}")
        else:
            print(f"ok   {name}")
    print(f"\n{'FAILED: ' + str(failed) if failed else 'all venue-dup tests passed'}")
    sys.exit(1 if failed else 0)
