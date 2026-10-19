#!/usr/bin/env python3
"""Three page fixes of 2026-10-19: a sane z on a few market-days, Production counts that agree,
and market labels worded for the side a lane actually bets."""
import sys

import control_center as CC
import sandbox_build as B
import sandbox_track as T
import soccer_cards as SC

FAILS = []


def ok(cond, why):
    print(f"  {'ok  ' if cond else 'FAIL'} {why}")
    if not cond:
        FAILS.append(why)


def bet(source, sport, market_id, date, price, won, pick="a", side_b="No"):
    return dict(id=f"{source}:{market_id}", source=source, sport=sport, market_id=market_id, date=date,
                start=f"{date}T21:00:00+00:00", logged=f"{date}T18:00:00+00:00", bet=True, pick=pick,
                side_a="Yes", side_b=side_b, price_a=price if pick == "a" else round(1 - price, 2),
                price_b=price if pick == "b" else round(1 - price, 2), price_draw=None, price=price,
                venue="kalshi_binary", status="won" if won else "lost", result=pick if won else ("b" if pick == "a" else "a"),
                pnl=round(T.STAKE * (1 / price - 1), 2) if won else -T.STAKE, stake=T.STAKE, settled=f"{date}T21:05:00+00:00")


print("1. a few market-days that all win read a modest z, not +14")
rows = []
for i, day in enumerate(("2026-10-12", "2026-10-13", "2026-10-14", "2026-10-15", "2026-10-16")):
    for j, (series, price) in enumerate((("KXGOLDD", 0.75), ("KXSILVERD", 0.78), ("KXWTI", 0.80))):
        rows.append(bet("commod_fav_band", "commodities_fav", f"{series}-26OCT{12 + i}17-T{j}", day, price, True))
d = {"meta": {}, "quotes": rows, "coverage": {}}
a = T.assess(d, "commod_fav_band", "commodities_fav")
ok((a["n"], a["won"], a["unit"]) == (5, 5, "market-day"), f"five market-days, all won (n {a['n']}, won {a['won']})")
ok(0.5 < a["z"] < 2.0, f"z is about +1, the binomial answer for 5-0 at ~0.78 (got {a['z']:+.2f})")
mixed = []
for i, day in enumerate(("2026-10-12", "2026-10-13", "2026-10-14", "2026-10-15", "2026-10-16", "2026-10-19")):
    mixed.append(bet("crypto_fav_band", "crypto_fav", f"KXBTCD-26OCT{12 + i}17-T1", day, 0.75, i % 3 != 2))
c = T.assess({"meta": {}, "quotes": mixed, "coverage": {}}, "crypto_fav_band", "crypto_fav")
ok(c["unit"] == "market-day" and abs(c["z"]) < 2, f"the crypto lanes take the same market-day path (z {c['z']:+.2f})")

print("\n2. a Production pair that has not bet yet is still listed, so the counts agree")
st = {"pairs": {"corners_ucl_fade|soccer_corners": {"stage": "production", "by_hand": "2026-10-15"}}}
listed = [r for r in B.pair_list({"meta": {}, "quotes": []}, st) if r["prod"]]
ok([(r["name"], r["v"]) for r in listed] == [("corners_ucl_fade", "nobets")], "corners_ucl_fade is listed, Too early")
entries = CC.scorecard_rows(listed)
html = CC._scorecard_html(entries, ["Econ Daily favourite band"])
ok("Production 1 lists the sports pairs; Econ Daily favourite band is also in Production through its own feed, "
   "which makes the 2 in the tile above." in html, "the scorecard says why its Production count is one under the tile")
ok("cc-prod-note" not in CC._scorecard_html(entries), "and says nothing when nothing sits outside it")

print("\n3. market labels follow the side the lane bets")
ok(B.side_words("soccer_u35", "a") == "Soccer · Over 3.5", "the Yes on the Under 3.5 market is Over 3.5 (bund_o35)")
ok(B.side_words("soccer_u35", "b") == "Soccer · Under 3.5", "the No stays Under 3.5 (u35_low_scoring)")
ok(B.side_words("soccer_o25", "b") == "Soccer · Under 2.5", "the No on Over 2.5 is Under 2.5 (o25_congestion)")
ok(B.side_words("soccer_o15", "b") == "Soccer · Under 1.5", "the No on Over 1.5 is Under 1.5 (liga_u15_dog)")
ok(B.side_words("soccer_o15_intl", "b") == "Soccer · Under 1.5 · Internationals", "a scope suffix is kept")
ok(B.side_words("soccer_btts", "b") == "Soccer · BTTS · No", "the No on BTTS says so")
ok(B.side_words("crypto_fav", "b") == "Crypto · Favourite band · No", "a crypto below lane says No")
ok(B.side_words("soccer_corners", "a") == "Soccer · Corners", "a label that names no side is left alone")
ok(B.side_words("soccer_p05", "b") == "Soccer · Team +0.5", "Team +0.5 is the No it names")
ok(B.side_words("soccer_u35", None) == "Soccer · Under 3.5", "no bets yet: the sport label as it is")
ld = {"meta": {}, "quotes": [bet("bund_o35", "soccer_u35", "KXBUNDESLIGATOTAL-26OCT18LEVSCF-4", "2026-10-18", 0.45, True)]}
row = next(r for r in B.pair_list(ld, {"pairs": {}}) if r["name"] == "bund_o35")
ok((row["side"], B.side_label(row), SC.market(ld, row)) == ("a", "Soccer · Over 3.5", "Over 3.5"),
   f"bund_o35 reads Over 3.5 in the scorecard and on the Soccer page ({B.side_label(row)!r}, {SC.market(ld, row)!r})")
fade = next(r for r in B.pair_list({"meta": {}, "quotes": []}, {"pairs": {}}) if r["name"] == "team2_ranked_fade")
ok(B.side_label(fade) == "Soccer · Team 2+ · No · Internationals",
   f"a fade with no bets yet reads its No side, ahead of the scope ({B.side_label(fade)!r})")
sc = CC.scorecard_rows([row])
ok(sc[0]["sport_label"] == "Soccer · Over 3.5", "the Home scorecard's market line")

print(f"\n{'ALL PASS' if not FAILS else str(len(FAILS)) + ' FAILED'}")
sys.exit(1 if FAILS else 0)
