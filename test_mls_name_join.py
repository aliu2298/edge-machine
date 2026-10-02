#!/usr/bin/env python3
"""MLS fade-home joins an ESPN club name to that club's Kalshi name.

The +0.5 row's opponent is the ESPN display name. The three-way board's home
is Kalshi's yes_sub_title. An exact string compare drops every home game
except San Diego FC, the one club spelled the same in both. This file fails
while that compare is still exact, and passes once each stored pair joins
and a lookalike or an unknown name does not.

No network. Lead files are not written.
"""
import json
import sys

import sandbox_sources as S

FAILS = []

# ESPN display name, Kalshi yes_sub_title. Hard-coded. No network.
# Kalshi spellings in NOT_A_LEDGER_SIDE are yes_sub_title values from Kalshi's
# public markets API, not side_a/side_b on a stored KXMLSGAME ledger row.
# The PR body records the fetch.
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

NOT_A_LEDGER_SIDE = frozenset({
    "Columbus",
    "DC United",
    "Los Angeles G",
    "New England",
    "Seattle",
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


def _espn_names():
    with open("data/espn_seasons.json") as f:
        rows = json.load(f)["rows"]
    names = set()
    for comp, _date, home, away, _hg, _ag in rows:
        if comp == "usa.1":
            names.add(home)
            names.add(away)
    return names


def _kalshi_names():
    with open("data/sandbox_ledger.json") as f:
        quotes = json.load(f)["quotes"]
    names = set()
    for q in quotes:
        if q.get("venue") != "kalshi":
            continue
        if not str(q.get("market_id") or "").startswith("KXMLSGAME"):
            continue
        if q.get("side_a"):
            names.add(q["side_a"])
        if q.get("side_b"):
            names.add(q["side_b"])
    return names


def main():
    espn = _espn_names()
    kalshi = _kalshi_names()
    clubs = {n for n in espn if n not in ("Arsenal", "Liga MX All-Stars", "MLS All-Stars")}
    eq(len(clubs), 30, "stored ESPN seasons list 30 current MLS clubs")
    mapped = {e for e, _k in PAIRS}
    eq(mapped, clubs, "every current club is mapped")
    eq(len(PAIRS), 30, "all 30 clubs have both spellings")
    ok(len({k for _e, k in PAIRS}) == len(PAIRS),
       "no two clubs share a Kalshi spelling")

    for espn_name, kalshi_name in PAIRS:
        ok(espn_name in espn, f"ESPN spelling {espn_name!r} is in data/espn_seasons.json")
        if kalshi_name not in NOT_A_LEDGER_SIDE:
            ok(kalshi_name in kalshi,
               f"Kalshi spelling {kalshi_name!r} is a KXMLSGAME side in the ledger")
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

    print("\n9/27 stored boards")
    with open("data/sandbox_ledger.json") as f:
        quotes = json.load(f)["quotes"]
    three, p05 = [], []
    for q in quotes:
        if not str(q.get("market_id") or "").startswith("KXMLSGAME"):
            continue
        if q.get("date") != "2026-09-27":
            continue
        if q.get("venue") == "kalshi" and q.get("side_a"):
            three.append(q)
        elif q.get("venue") == "kalshi_binary" and q.get("sport") == "soccer_p05" and q.get("opponent"):
            p05.append(q)
    boards = []
    for q in sorted(three, key=lambda r: (r["market_id"], r.get("source") or "")):
        pa, pdr, pb = float(q["price_a"]), float(q["price_draw"]), float(q["price_b"])
        total = pa + pdr + pb
        ph = pa / total
        boards.append((q["market_id"], q["side_a"], ph, q.get("source")))
        print(f"  {q['market_id']} {q['side_a']} home {ph:.4f} ({pa}+{pdr}+{pb}) {q.get('source')}")
    in_band = [b for b in boards if S.MLS_FADE_HOME_BAND[0] <= b[2] < S.MLS_FADE_HOME_BAND[1]]
    eq(in_band, [], "no stored 2026-09-27 three-way home price is inside 0.40-0.45")
    have = {S._ere_code(b[0]) for b in boards}
    missing = sorted({S._ere_code(q["market_id"]) for q in p05} - have)
    print(f"  p05 fixtures with no stored three-way board: {missing}")
    uni = {"soccer": [_board(S._ere_code(q["market_id"]), q["side_a"], q.get("side_b") or "Away",
                             pa=q["price_a"], pdr=q["price_draw"], pb=q["price_b"])
                      for q in three],
           "soccer_p05": p05}
    eq(S.fetch_mls_fade_home("soccer_p05", universe=uni), [],
       "replaying the stored 2026-09-27 boards, the lane picks 0")

    print(f"\n{'FAILED: ' + str(len(FAILS)) if FAILS else 'mls name join passed'}")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
