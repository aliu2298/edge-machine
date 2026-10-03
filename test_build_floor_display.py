#!/usr/bin/env python3
"""Displayed BUILD verdicts go through build_passes and subperiod_passes.

Frozen fixtures only. Nothing here reads the live ledger, so a later tracker
run does not move the result.

Fails on a tree whose pages do not call the helpers. Passes once every
displayed BUILD pass/fail is that call.
"""
import pathlib

import sandbox_build as SB
import sandbox_sources as S
import sandbox_track as T

FAILS = []
ROOT = pathlib.Path(__file__).resolve().parent

# The ten league bands whose notes publish a held-out split. Order is the page order.
LANES = (
    "turkey_btts_dog",
    "turkey_o25_dog",
    "ere_o15",
    "ere_draw",
    "bund_o35_fav",
    "bund_o35",
    "liga_btts_even",
    "liga_u15_dog",
    "mls_away_band",
    "mls_fade_home",
)


def ok(cond, why):
    print(f"  {'ok  ' if cond else 'FAIL'} {why}")
    if not cond:
        FAILS.append(why)


def eq(got, want, why):
    ok(got == want, why if got == want else f"{why} — got {got!r}, want {want!r}")


def main():
    # Absent on a tree that still has no display caller. The raise is the
    # base failure; everything below is the head.
    print("display entry")
    eq(S.BUILD_Z, 2.0, "the z bar stays 2.0")
    eq(S.BUILD_MIN_SUBPERIOD_MATCHES, 60, "the match floor stays 60")
    eq(S.display_build_passes([(180, 2.4), (37, 3.56)]), False,
       "180 then 37 at a strong z does not pass")
    eq(S.display_build_passes([(180, 2.4), (60, S.BUILD_Z)]), True,
       "two blocks at the floor still pass")
    eq(S.display_build_passes([(500, 3.0)]), False,
       "one block of 500 at z 3 does not pass")
    eq(S.display_subperiod_passes(37, 3.56), False, "37 matches fails the cell")
    eq(S.display_subperiod_passes(180, 2.4), True, "180 matches at z 2.4 passes the cell")
    eq(S.display_subperiod_passes(None, 3.56), False, "an unpublished n is not a pass")
    eq(S.display_subperiod_passes(80, None), False, "an unpublished z is not a pass")

    print("unpublished figures reach the helper")
    seen = []
    real_build = S.build_passes

    def spy_build(rows):
        rows = list(rows)
        seen.append(rows)
        return real_build(rows)

    S.build_passes = spy_build
    try:
        eq(S.display_build_passes([(None, 2.5), (37, 3.56)]), False,
           "a missing n still fails after the helper sees it")
        eq(seen, [[(0, 2.5), (37, 3.56)]],
           "a missing n is handed to build_passes as a failing count")
    finally:
        S.build_passes = real_build

    print("published blocks")
    eq(tuple(S.BUILD_BANDS), LANES, "the ten league bands, and no others")
    eq(S.BUILD_BANDS["turkey_btts_dog"],
       (("two-in", None, 1.96), ("held-out", 37, 3.56)),
       "turkey_btts_dog keeps the published 37 at z +3.56")
    eq(S.BUILD_BANDS["bund_o35_fav"],
       (("two-in", None, 2.72), ("held-out", None, 2.48)),
       "bund_o35_fav keeps both published z values and does not invent n")
    eq(S.BUILD_BANDS["bund_o35"],
       (("four seasons", 1224, 3.01),),
       "bund_o35 stays the one published four-season block")
    eq(S.BUILD_BANDS["liga_u15_dog"],
       (("two-in", None, 2.38), ("held-out", 51, -0.04)),
       "liga_u15_dog z is in the under-1.5 direction")
    eq(S.BUILD_BANDS["liga_btts_even"],
       (("two-in", None, None), ("held-out", 113, 0.60)),
       "liga_btts_even held-out stays 113 at z +0.60")
    eq(S.BUILD_BANDS["mls_away_band"],
       (("2024-2025", None, None), ("held-out", 74, None)),
       "mls_away_band held-out n is 74 and its z is not published")
    eq(S.BUILD_BANDS["mls_fade_home"],
       (("2024-2025", None, None), ("held-out", 61, None)),
       "mls_fade_home held-out n is 61 and its z is not published")
    for name in ("turkey_o25_dog", "ere_o15", "ere_draw"):
        eq(S.BUILD_BANDS[name], (("two-in", None, None), ("held-out", None, None)),
           f"{name} does not turn a prose bound into a z")
    ok("turkey_btts_dog" in S.SOURCES and S.SOURCES["turkey_btts_dog"]["connected"],
       "turkey_btts_dog stays registered")
    ok("37 matches" in S.SOURCES["turkey_btts_dog"]["note"]
       and "z +3.56" in S.SOURCES["turkey_btts_dog"]["note"],
       "the turkey_btts_dog note is unchanged")

    print("rendered words")
    thin = SB.build_lane_bits(
        "Thin example", (("two-in", 180, 2.4), ("held-out", 37, 3.56)))
    ok("Fails BUILD" in thin["band"] and "BUILD pass" not in thin["band"],
       "a 37-match block renders Fails BUILD")
    ok(">pass<" in thin["band"] and ">fail<" in thin["band"],
       "the thick cell passes and the 37-match cell fails")
    both = SB.build_lane_bits(
        "Both clear", (("two-in", 180, 2.4), ("held-out", 60, S.BUILD_Z)))
    ok("BUILD pass" in both["band"] and "Fails BUILD" not in both["band"],
       "two blocks at the floor render BUILD pass")
    one = SB.build_lane_bits("One block", (("only", 500, 3.0),))
    ok("Fails BUILD" in one["matrix"] and ">pass<" in one["matrix"],
       "one block of 500 passes its cell and fails the band")
    ok(one["matrix"].count(">pass<") == 1, "the missing second block is not a fake pass")

    print("no second path")
    saved_build = S.build_passes
    S.build_passes = lambda rows: True
    try:
        flipped = SB.build_lane_bits(
            "Thin example", (("two-in", 180, 2.4), ("held-out", 37, 3.56)))
        ok("BUILD pass" in flipped["matrix"] and "Fails BUILD" not in flipped["matrix"],
           "patching build_passes flips the band word")
        ok(">fail<" in flipped["band"],
           "the cell still follows subperiod_passes when only build_passes is patched")
    finally:
        S.build_passes = saved_build
    saved_cell = S.subperiod_passes
    S.subperiod_passes = lambda n, z: False
    try:
        flipped = SB.build_lane_bits(
            "Both clear", (("two-in", 180, 2.4), ("held-out", 60, S.BUILD_Z)))
        ok("Fails BUILD" in flipped["band"] and ">pass<" not in flipped["band"],
           "patching subperiod_passes flips the cell and the band")
        ok("BUILD pass" not in flipped["matrix"],
           "a patched cell cannot leave a BUILD pass behind")
    finally:
        S.subperiod_passes = saved_cell

    page_src = (ROOT / "sandbox_build.py").read_text()
    ok("display_build_passes" in page_src and "display_subperiod_passes" in page_src,
       "the page calls the display wrappers")
    stripped = page_src.replace("display_build_passes", "").replace("display_subperiod_passes", "")
    ok("build_passes(" not in stripped and "subperiod_passes(" not in stripped,
       "the page does not call the helpers on its own")
    for fname in ("production.py", "sandbox_track.py"):
        text = (ROOT / fname).read_text()
        ok("display_build_passes" not in text and "BUILD_BANDS" not in text,
           f"{fname} does not grow a BUILD verdict path")

    print("empty ledger still shows the lanes")
    empty = {"quotes": [], "meta": {}}
    stages = {"pairs": {}}
    before = dict(T.PAIR_OVERRIDES)
    rows = SB.pair_list(empty, stages)
    names = {r["name"] for r in rows}
    for name in LANES:
        ok(name in names, f"{name} is on the page with no entries")
    turkey = next(r for r in rows if r["name"] == "turkey_btts_dog")
    eq(turkey["v"], "build_fail", "turkey_btts_dog shows the failing verdict")
    eq(SB.lane_build_word("turkey_btts_dog"), "Fails BUILD",
       "the turkey band word is Fails BUILD")
    for gone in ("nws", "nws_fade", "covers"):
        ok(gone not in names, f"{gone} is not a row")
    section = SB.sport_sections(empty, rows)
    ok("Fails BUILD" in section and "Turkey BTTS" in section,
       "the soccer section renders the turkey failing verdict")
    ok("National Weather Service" not in section and "Covers / OddsShark" not in section,
       "weather and covers are not in the sport section")
    research = SB.build_research(rows)
    ok("BUILD pass" not in research, "no published band clears the floor")
    ok(research.count("Fails BUILD") >= len(LANES),
       "every league band renders a failing band verdict")
    ok("National Weather Service" not in research and "Covers" not in research,
       "the BUILD tables do not render weather or covers")
    eq(dict(T.PAIR_OVERRIDES), before, "rendering does not touch PAIR_OVERRIDES")

    print("a live record keeps its own word")
    quotes = []
    for i in range(36):
        won = i % 3 != 0
        quotes.append(dict(
            id=f"mls_away_band:soccer:{i}", source="mls_away_band", sport="soccer",
            market_id=f"m{i}", venue="polymarket_us", bet=True, pick="a",
            price=0.5, price_a=0.5, price_b=0.5, result="a" if won else "b",
            status="won" if won else "lost", pnl=100.0 if won else -100.0, stake=100.0,
            start=f"2026-08-{1 + i % 28:02d}T18:00:00+00:00",
            logged=f"2026-08-{1 + i % 28:02d}T10:00:00+00:00"))
    live = SB.pair_list({"quotes": quotes, "meta": {}}, {"pairs": {}})
    mls = next(r for r in live if r["name"] == "mls_away_band")
    eq(mls["v"], "proven", "36 settled bets keep the live-record verdict")
    ok(SB.lane_build_word("mls_away_band") == "Fails BUILD",
       "the research verdict stays a fail beside that record")

    print(f"\n{len(FAILS)} failure(s)" if FAILS else "\nall build-floor display tests passed")
    return 1 if FAILS else 0


if __name__ == "__main__":
    raise SystemExit(main())
