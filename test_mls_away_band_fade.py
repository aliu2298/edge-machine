#!/usr/bin/env python3
"""MLS away band, retired and faded (2026-10-16): mls_away_band_fade."""
import sys
import production as PR
import sandbox_build as B
import sandbox_sources as S
import sandbox_track as T

FAILS = []


def check(label, got, want):
    ok = got == want
    print(f"  {'ok  ' if ok else 'FAIL'} {label}" + ("" if ok else f" (got {got!r}, want {want!r})"))
    if not ok:
        FAILS.append(label)


# The board carries Kalshi's names, the +0.5 rows ESPN's (MLS_ESPN_TO_KALSHI joins them).
def game(code, pa, pdr, pb, home="Orlando", away="DC United"):
    return dict(market_id=f"KXMLSGAME-{code}", venue="kalshi", sport="soccer", side_a=home, side_b=away,
                price_a=pa, price_draw=pdr, price_b=pb, untraded=False,
                tradeable={"a": True, "b": True, "draw": True})


def win(code, leg, opponent, team, a, b):
    """A soccer_p05 row: the `opponent`'s own win contract, whose No is `team` +0.5."""
    return dict(market_id=f"KXMLSGAME-{code}-{leg}", venue="kalshi_binary", sport="soccer_p05",
                opponent=opponent, team=team, price_a=a, price_b=b, untraded=False,
                tradeable={"a": True, "b": True})


uni = {"soccer": [game("26OCT17ORLDCU", 0.57, 0.23, 0.22),             # away de-vigged 0.216: in band
                  game("26OCT17NYCCLB", 0.45, 0.27, 0.30, "New York City", "Columbus")],  # 0.294: out
       "soccer_p05": [win("26OCT17ORLDCU", "ORL", "Orlando City SC", "D.C. United", 0.57, 0.45),
                      win("26OCT17ORLDCU", "DCU", "D.C. United", "Orlando City SC", 0.22, 0.80),
                      win("26OCT17NYCCLB", "CLB", "Columbus Crew", "New York City FC", 0.30, 0.72),
                      # a club the name join does not know is never taken as the away side
                      win("26OCT17ORLDCU", "XXX", "Unknown FC", "Orlando City SC", 0.22, 0.80)]}

print("selection: mls_away_band's matches, the No on the away side's own contract")
check("the follow rule still picks the in-band match", S.fetch_mls_away_band("soccer", uni),
      [dict(market_id="KXMLSGAME-26OCT17ORLDCU", pick="b")])
check("the fade takes the No of D.C. United's win contract, and nothing else",
      S.fetch_mls_away_band_fade("soccer_p05", uni), [dict(market_id="KXMLSGAME-26OCT17ORLDCU-DCU", pick="b")])
check("never the home side's contract", any(p["market_id"].endswith("-ORL")
      for p in S.fetch_mls_away_band_fade("soccer_p05", uni)), False)
check("only on soccer_p05", S.fetch_mls_away_band_fade("soccer", uni), [])

print("\nthe follow side is retired on soccer, off the pages, on a fresh record for the fade")
check("mls_away_band logs soccer no more", "soccer" in S.SOURCES["mls_away_band"]["sports"], False)
check("its retirement is recorded", bool((S.SOURCES["mls_away_band"].get("retired_sports") or {}).get("soccer")), True)
check("the fade is registered on soccer_p05",
      ("mls_away_band_fade" in S.CHALLENGERS, S.SOURCES["mls_away_band_fade"]["sports"]), (True, ["soccer_p05"]))
d, st = T.load(), T.load_stages()
names = {(r["name"], r["sport"]) for r in B.pair_list(d, st)}
check("the retired pair is not listed", ("mls_away_band", "soccer") in names, False)
check("the fade starts with no bets from before it was registered",
      [q["id"] for q in T.all_bets(d) if q.get("source") == "mls_away_band_fade"
       and str(q.get("logged") or "") < "2026-10-16T20:00"], [])
check("it is a Sandbox lane, not a Production pair", "mls_away_band_fade|soccer_p05" in T.PAIR_OVERRIDES, False)

print("\nits feed claim, should it ever be promoted: the No of the away side's win")
q = dict(win("26OCT17ORLDCU", "DCU", "D.C. United", "Orlando City", 0.22, 0.80), id="mls_away_band_fade:x",
         source="mls_away_band_fade", pick="b", price=0.80, status="open", bet=True, league="MLS",
         espn_home="Orlando City", espn_away="D.C. United", start="2026-10-17T23:30:00+00:00",
         logged="2026-10-17T15:00:00+00:00", start_source="espn", side_a="Yes", side_b="No",
         kalshi_title="D.C. United", label="x")
lead = PR.lead_from_quote(q, "mls_away_band_fade|soccer_p05", "2026-10-17T15:00:00+00:00")
check("win_no on D.C. United", (lead["bet"], lead["headline"], lead["route"]["outcome_side"]),
      ({"kind": "win_no", "team": "D.C. United"}, "Orlando City +0.5 (D.C. United not to win)", "no"))

print(f"\n{'ALL PASS' if not FAILS else str(len(FAILS)) + ' FAILED'}")
sys.exit(1 if FAILS else 0)
