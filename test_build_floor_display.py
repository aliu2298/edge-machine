#!/usr/bin/env python3
"""A displayed BUILD verdict is build_passes, not a z-only chip.

Frozen fixtures. Nothing here reads the live ledger.

On a tree that still renders the live chip for a BUILD block, the rendered
row says Proven edge for one block of 500 at z 3.0. That ignores the floor.
After the row calls build_passes, the same fixture renders Fails BUILD.
"""
import sandbox_build as SB
import sandbox_sources as S

FAILS = []


def ok(cond, why):
    print(f"  {'ok  ' if cond else 'FAIL'} {why}")
    if not cond:
        FAILS.append(why)


def eq(got, want, why):
    ok(got == want, why if got == want else f"{why} — got {got!r}, want {want!r}")


def chip_row(blocks, n, z):
    """The sport-table row for one frozen BUILD block. No ledger."""
    a = dict(n=n, z=z, roi_fee=0.2, won=n, expected=n / 2, n_bets=n,
             clv=None, clv_n=0, build_subperiods=list(blocks))
    v = SB.verdict(a)
    row = dict(
        a=a, v=v, sport="soccer", open=0, prod=False, moved="",
        meta=dict(label="Frozen BUILD block", kind="Rule"),
        fade={}, removed=None,
    )
    return v, SB._row(row)


def main():
    # #36's own cases. These call the functions; they do not restate them.
    print("#36 unit cases")
    eq(S.BUILD_Z, 2.0, "the BUILD price bar stays 2.0")
    eq(S.BUILD_MIN_SUBPERIOD_MATCHES, 60, "a sub-period needs 60 matches")
    eq(S.subperiod_passes(25, 4.0), False,
       "a held-out sub-period of 25 matches with a strong edge does not pass")
    eq(S.subperiod_passes(60, S.BUILD_Z), True, "60 matches at the z bar can pass")
    eq(S.subperiod_passes(59, 4.0), False, "59 matches cannot pass")
    eq(S.subperiod_passes(60, S.BUILD_Z - 0.01), False,
       "60 matches under the z bar still cannot pass")
    eq(S.build_passes([(180, 2.4), (25, 4.0)]), False,
       "a band whose held-out sub-period is 25 matches does not pass BUILD")
    eq(S.build_passes([(180, 2.4), (60, S.BUILD_Z)]), True,
       "both sub-periods at the floor can pass")
    eq(S.build_passes([(180, 2.4), (59, 4.0)]), False,
       "a band whose held-out sub-period is 59 matches does not pass BUILD")
    eq(S.build_passes([]), False, "no sub-period is not a pass")
    eq(S.build_passes([(500, 3.0)]), False,
       "one sub-period does not pass BUILD, even at 500 matches and z 3.0")

    print("rendered chip")
    v, html = chip_row([(500, 3.0)], 500, 3.0)
    print("RENDERED one block of 500 at z 3.0:")
    print(html)
    print(f"chip word: {SB.VERDICTS[v][0]}")
    ok(v == "build_fail" and "Fails BUILD" in html and "Proven edge" not in html,
       "one block of 500 at z 3.0 renders through build_passes, not as Proven edge")

    v, html = chip_row([(180, 2.4), (25, 4.0)], 25, 4.0)
    print("RENDERED held-out 25 at z 4.0:")
    print(html)
    print(f"chip word: {SB.VERDICTS[v][0]}")
    ok(v == "build_fail" and "Fails BUILD" in html,
       "a 25-match block at z 4.0 renders through build_passes")

    v, html = chip_row([(180, 2.4), (60, S.BUILD_Z)], 60, S.BUILD_Z)
    print("RENDERED two blocks at the floor:")
    print(html)
    print(f"chip word: {SB.VERDICTS[v][0]}")
    ok(v != "build_fail" and "Fails BUILD" not in html,
       "two blocks at the floor are not a BUILD fail")

    print("the chip calls build_passes")
    saved = S.build_passes
    S.build_passes = lambda rows: False
    try:
        v, html = chip_row([(180, 2.4), (60, S.BUILD_Z)], 60, S.BUILD_Z)
        print("RENDERED after build_passes forced false:")
        print(html)
        print(f"chip word: {SB.VERDICTS[v][0]}")
        ok(v == "build_fail" and "Fails BUILD" in html,
           "forcing build_passes false flips the rendered chip")
    finally:
        S.build_passes = saved
    S.build_passes = lambda rows: True
    try:
        v, _html = chip_row([(500, 3.0)], 500, 3.0)
        ok(v != "build_fail",
           "forcing build_passes true does not leave a BUILD fail")
    finally:
        S.build_passes = saved

    print("no new sport rows")
    empty = {"quotes": [], "meta": {}}
    names = {r["name"] for r in SB.pair_list(empty, {"pairs": {}})}
    for lane in ("turkey_btts_dog", "turkey_o25_dog", "ere_o15", "ere_draw",
                 "bund_o35", "bund_o35_fav", "liga_btts_even", "liga_u15_dog",
                 "mls_away_band", "mls_fade_home", "nws", "nws_fade", "covers"):
        ok(lane not in names, f"{lane} is not a new sport row")
    ok("turkey_btts_dog" in S.SOURCES and S.SOURCES["turkey_btts_dog"]["connected"],
       "turkey_btts_dog stays registered")
    cov = SB.coverage_table({"soccer_btts": {"turkey_btts_dog": {"picked": 0, "offered": 0}}})
    ok("0 of 0" in cov and "Fails BUILD" not in cov,
       "the coverage cell stays 0 of 0")
    ok("National Weather Service" not in cov and "Covers" not in cov,
       "the coverage fixture does not draw weather or covers")

    print(f"\n{len(FAILS)} failure(s)" if FAILS else "\nall build-floor display tests passed")
    return 1 if FAILS else 0


if __name__ == "__main__":
    raise SystemExit(main())
