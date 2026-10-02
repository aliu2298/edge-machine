#!/usr/bin/env python3
"""MLS fade-home joins an ESPN club name to that club's Kalshi name.

The +0.5 row's opponent is the ESPN display name. The three-way board's home
is Kalshi's yes_sub_title. An exact string compare drops every home game
except San Diego FC, the one club spelled the same in both. This file fails
while that compare is still exact, and passes once each stored pair joins
and a lookalike or an unknown name does not.

The production map is pinned to PAIRS. KALSHI_TITLES is the yes_sub_title
set recorded from the public markets API on 2026-10-02. The 9/27 boards
are inline fixtures. No network. Lead files are not written.
"""
import sys

import sandbox_sources as S

FAILS = []

# ESPN display name, Kalshi yes_sub_title. The reviewed table. No network.
PAIRS = (
    ("Atlanta United FC", "Atlanta"),
    ("Austin FC", "Austin"),
    ("Charlotte FC", "Charlotte"),
    ("Chicago Fire FC", "Chicago Fire"),
    ("FC Cincinnati", "Cincinnati"),
    ("Colorado Rapids", "Colorado"),
    ("Columbus Crew", "Columbus"),
    ("FC Dallas", "Dallas"),
    ("D.C. United", "DC United"),
    ("Houston Dynamo FC", "Houston"),
    ("Inter Miami CF", "Miami"),
    ("LA Galaxy", "Los Angeles G"),
    ("LAFC", "Los Angeles F"),
    ("Minnesota United FC", "Minnesota"),
    ("CF Montréal", "Montreal"),
    ("Nashville SC", "Nashville"),
    ("New England Revolution", "New England"),
    ("New York City FC", "New York City"),
    ("Red Bull New York", "New York RB"),
    ("Orlando City SC", "Orlando"),
    ("Philadelphia Union", "Philadelphia"),
    ("Portland Timbers", "Portland"),
    ("Real Salt Lake", "Salt Lake"),
    ("San Diego FC", "San Diego FC"),
    ("San Jose Earthquakes", "San Jose"),
    ("Seattle Sounders FC", "Seattle"),
    ("Sporting Kansas City", "Kansas City"),
    ("St. Louis CITY SC", "Saint Louis"),
    ("Toronto FC", "Toronto"),
    ("Vancouver Whitecaps", "Vancouver"),
)

# yes_sub_title values on series KXMLSGAME, recorded from the public markets
# API on 2026-10-02. The 30 clubs plus Tie.
KALSHI_TITLES = frozenset({
    "Atlanta",
    "Austin",
    "Charlotte",
    "Chicago Fire",
    "Cincinnati",
    "Colorado",
    "Columbus",
    "Dallas",
    "DC United",
    "Houston",
    "Miami",
    "Los Angeles G",
    "Los Angeles F",
    "Minnesota",
    "Montreal",
    "Nashville",
    "New England",
    "New York City",
    "New York RB",
    "Orlando",
    "Philadelphia",
    "Portland",
    "Salt Lake",
    "San Diego FC",
    "San Jose",
    "Seattle",
    "Kansas City",
    "Saint Louis",
    "Toronto",
    "Vancouver",
    "Tie",
})

# (espn opponent, kalshi home) that must not join. Real names only.
LOOKALIKES = (
    ("LA Galaxy", "Los Angeles F"),
    ("LAFC", "Los Angeles G"),
    ("LAFC", "LA Galaxy"),
    ("New York City FC", "New York RB"),
    ("Red Bull New York", "New York City"),
    ("Sporting Kansas City", "Saint Louis"),
    ("Sporting KC", "Kansas City"),
    ("New York", "New York City"),
    ("New York", "New York RB"),
    ("Los Angeles", "Los Angeles F"),
    ("Kansas", "Kansas City"),
)


def ok(cond, msg):
    if cond:
        print(f"  ok   {msg}")
    else:
        print(f"  FAIL {msg}")
        FAILS.append(msg)


def eq(got, want, msg):
    ok(got == want, msg if got == want else f"{msg} — got {got!r}, want {want!r}")


def _board(code, home, away="Away", pa=0.43, pdr=0.27, pb=0.32):
    return dict(venue="kalshi", market_id=f"KXMLSGAME-{code}", side_a=home, side_b=away,
                price_a=pa, price_draw=pdr, price_b=pb,
                tradeable={"a": True, "b": True, "draw": True}, untraded=False)


def _p05(code, suffix, opponent, team="Other", ask=0.42, no=0.60):
    return dict(venue="kalshi_binary", market_id=f"KXMLSGAME-{code}-{suffix}",
                team=team, opponent=opponent, price_a=ask, price_b=no,
                tradeable={"a": True, "b": True}, untraded=False)


def _picked(code, home, opponent, **kw):
    uni = {"soccer": [_board(code, home)],
           "soccer_p05": [_p05(code, "H", opponent, **kw)]}
    return [p["market_id"] for p in S.fetch_mls_fade_home("soccer_p05", universe=uni)]


def _sep27(atx=(0.40, 0.26, 0.35)):
    """2026-09-27 boards and +0.5 rows, inlined. `atx` is the ATXSD price triple."""
    pa, pdr, pb = atx
    return {
        "soccer": [
            _board("26SEP26ATXSD", "Austin", "San Diego FC", pa=pa, pdr=pdr, pb=pb),
            _board("26SEP26DALLAFC", "Dallas", "Los Angeles F", pa=0.40, pdr=0.26, pb=0.36),
            _board("26SEP26HOUSKC", "Houston", "Kansas City", pa=0.66, pdr=0.20, pb=0.15),
            _board("26SEP26NSHTOR", "Nashville", "Toronto", pa=0.67, pdr=0.19, pb=0.15),
        ],
        "soccer_p05": [
            _p05("26SEP26ATXSD", "ATX", "Austin FC", team="San Diego FC", ask=0.40, no=0.61),
            _p05("26SEP26ATXSD", "SD", "San Diego FC", team="Austin FC", ask=0.35, no=0.66),
            _p05("26SEP26DALLAFC", "DAL", "FC Dallas", team="LAFC", ask=0.40, no=0.61),
            _p05("26SEP26DALLAFC", "LAFC", "LAFC", team="FC Dallas", ask=0.36, no=0.65),
            _p05("26SEP26HOUSKC", "HOU", "Houston Dynamo FC", team="Sporting Kansas City",
                 ask=0.66, no=0.35),
            _p05("26SEP26HOUSKC", "SKC", "Sporting Kansas City", team="Houston Dynamo FC",
                 ask=0.15, no=0.86),
            _p05("26SEP26NSHTOR", "NSH", "Nashville SC", team="Toronto FC", ask=0.67, no=0.34),
            _p05("26SEP26NSHTOR", "TOR", "Toronto FC", team="Nashville SC", ask=0.15, no=0.86),
        ],
    }


def _show_board(board):
    pa, pdr, pb = float(board["price_a"]), float(board["price_draw"]), float(board["price_b"])
    total = pa + pdr + pb
    print(f"  {board['market_id']} {board['side_a']} home {pa / total:.4f} "
          f"hold {total - 1.0:.4f} ({pa}+{pdr}+{pb})")


def main():
    got_map = getattr(S, "MLS_ESPN_TO_KALSHI", None)
    if got_map == dict(PAIRS):
        ok(True, "the production map is exactly the reviewed table")
    elif got_map is None:
        ok(False, "the production map is exactly the reviewed table — MLS_ESPN_TO_KALSHI is missing")
    else:
        ok(False, "the production map is exactly the reviewed table — map differs from PAIRS")
    eq(len(PAIRS), 30, "all 30 clubs have both spellings")
    ok(len({e for e, _k in PAIRS}) == len(PAIRS), "ESPN keys are unique")
    ok(len({k for _e, k in PAIRS}) == len(PAIRS), "Kalshi values are unique")
    eq({k for _e, k in PAIRS} | {"Tie"}, KALSHI_TITLES,
       "Kalshi spellings plus Tie equal the recorded yes_sub_title set")

    for espn_name, kalshi_name in PAIRS:
        code = "26OCT04" + "".join(ch for ch in kalshi_name if ch.isalnum())[:8]
        want = [f"KXMLSGAME-{code}-H"]
        eq(_picked(code, kalshi_name, espn_name), want,
           f"{espn_name} joins the Kalshi row {kalshi_name}")

    print("\nlookalikes and unknown names")
    for espn_name, kalshi_name in LOOKALIKES:
        code = "26OCT04NO" + "".join(ch for ch in (espn_name + kalshi_name) if ch.isalnum())[:10]
        eq(_picked(code, kalshi_name, espn_name), [],
           f"{espn_name} does not join {kalshi_name}")
    eq(_picked("26OCT04UNK", "Columbus", "Not A Club"), [],
       "an unknown name does not join a real Kalshi row")
    eq(_picked("26OCT04SELF", "Not A Club", "Not A Club"), [],
       "an unknown name does not match even itself")

    print("\nColumbus lane")
    # In band: 0.43 / 1.02 = 0.4216. No ask 0.60 is under the 0.66 ceiling.
    uni = {
        "soccer": [_board("26OCT03CLBMIA", "Columbus", "Miami")],
        "soccer_p05": [
            _p05("26OCT03CLBMIA", "CLB", "Columbus Crew", team="Inter Miami CF"),
            _p05("26OCT03CLBMIA", "MIA", "Inter Miami CF", team="Columbus Crew", ask=0.31, no=0.71),
        ],
    }
    eq([p["market_id"] for p in S.fetch_mls_fade_home("soccer_p05", universe=uni)],
       ["KXMLSGAME-26OCT03CLBMIA-CLB"],
       "an in-band home with ESPN 'Columbus Crew' and Kalshi 'Columbus' is picked")
    eq([p["pick"] for p in S.fetch_mls_fade_home("soccer_p05", universe=uni)], ["b"],
       "and the pick is still the NO")

    print("\n9/27 boards")
    stored = _sep27()
    for board in stored["soccer"]:
        _show_board(board)
    eq(S.fetch_mls_fade_home("soccer_p05", universe=stored), [],
       "replaying the 2026-09-27 boards, the lane picks 0")

    print("\nATXSD positive control")
    # 0.43 / 1.01 = 0.4257, hold 1%. Same +0.5 rows as the replay above.
    nudged = _sep27((0.43, 0.26, 0.32))
    _show_board(nudged["soccer"][0])
    picks = S.fetch_mls_fade_home("soccer_p05", universe=nudged)
    eq([p["market_id"] for p in picks], ["KXMLSGAME-26SEP26ATXSD-ATX"],
       "ATXSD at 0.43/0.26/0.32 picks exactly KXMLSGAME-26SEP26ATXSD-ATX")
    eq([p["pick"] for p in picks], ["b"],
       "and that pick is the NO")

    print(f"\n{'FAILED: ' + str(len(FAILS)) if FAILS else 'mls name join passed'}")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
