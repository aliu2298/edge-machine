#!/usr/bin/env python3
"""The three NO claims added with the 2026-10-16 promotions: btts_no, win_no, ftts_no.

Each is the No of the exact Kalshi contract the quote names, and the feed says which team
the contract is about so the follower can confirm it before buying.
"""
import sys
from datetime import datetime, timezone
import production as PR
import sandbox_sources as S
import sandbox_track as T

FAILS = []


def check(label, got, want):
    ok = got == want
    print(f"  {'ok  ' if ok else 'FAIL'} {label}" + ("" if ok else f" (got {got!r}, want {want!r})"))
    if not ok:
        FAILS.append(label)


BASE = dict(venue="kalshi_binary", pick="b", side_a="Yes", side_b="No", status="open", bet=True,
            start="2026-10-18T19:00:00+00:00", logged="2026-10-17T15:00:00+00:00", start_source="espn",
            price=0.60, label="x")
btts = dict(BASE, id="btts_form_l10_fade:KXEREDIVISIEBTTS-26OCT18GROAJA-BTTS", source="btts_form_l10_fade",
            sport="soccer_btts", market_id="KXEREDIVISIEBTTS-26OCT18GROAJA-BTTS", league="Eredivisie",
            espn_home="FC Groningen", espn_away="Ajax Amsterdam", kalshi_title="Both Teams To Score")
win = dict(BASE, id="mls_fade_home:KXMLSGAME-26OCT17LAGSD-LAG", source="mls_fade_home", sport="soccer_p05",
           market_id="KXMLSGAME-26OCT17LAGSD-LAG", league="MLS", espn_home="LA Galaxy", espn_away="San Diego FC",
           team="San Diego FC", opponent="LA Galaxy", kalshi_title="Los Angeles G")
ftts = dict(BASE, id="ftts_no_70_80:KXUELFTTS-26OCT15JAGARA-ARA", source="ftts_no_70_80", sport="soccer_ftts",
            market_id="KXUELFTTS-26OCT15JAGARA-ARA", league="Europa League", espn_home="Jagiellonia",
            espn_away="Ararat-Armenia", team="Ararat-Armenia", opponent="Jagiellonia",
            kalshi_title="FC Ararat-Armenia")

for name, q, kind, headline, team in (
        ("BTTS No", btts, "btts_no", "Both teams to score: No", None),
        ("home not to win", win, "win_no", "San Diego FC +0.5 (LA Galaxy not to win)", "LA Galaxy"),
        ("not to score first", ftts, "ftts_no", "Ararat-Armenia not to score first", "Ararat-Armenia")):
    print(f"\n{name}")
    check("the feed can publish it", T.placeable(q), True)
    lead = PR.lead_from_quote(q, f"{q['source']}|{q['sport']}", "2026-10-17T15:00:00+00:00")
    check("the claim", (lead["bet"]["kind"], lead["bet"].get("team")), (kind, team))
    check("the headline", lead["headline"], headline)
    check("the No of the exact contract", (lead["route"]["market"], lead["route"]["outcome_side"]),
          (q["market_id"], "no"))
    check("its Yes is not this claim", T.feed_bet(dict(q, pick="a")) == {"kind": kind}, False)

print("\nthe five promotions of 2026-10-16 (btts_form_l10_fade out again 2026-10-17, record kept)")
check("four of the five are still listed by hand that day",
      sorted(k for k, v in T.PAIR_OVERRIDES.items() if v["moved_on"] == "2026-10-16"),
      ["espn_fpi|nfl", "ftts_no_70_80|soccer_ftts",
       "mls_fade_home|soccer_p05", "team2_form_l10|soccer_team2"])
check("btts_form_l10_fade|soccer_btts is off the list and goes back keeping its record",
      ("btts_form_l10_fade|soccer_btts" in T.PAIR_OVERRIDES, T.PAIR_REMOVALS["btts_form_l10_fade|soccer_btts"]["keep_record"]),
      (False, True))
_rm = {"pairs": {"btts_form_l10_fade|soccer_btts": dict(stage="production", promoted_at="2026-10-16T17:17:38+00:00",
                                                        entry_since=None, by_hand="2026-10-16")}, "events": []}
T.evaluate_stages({"quotes": []}, _rm, now=datetime(2026, 10, 18, 6, tzinfo=timezone.utc), verbose=False)
check("a kept-record removal returns to the Sandbox on its old clock (None = whole record), demoted_at set",
      {k: _rm["pairs"]["btts_form_l10_fade|soccer_btts"].get(k) for k in ("stage", "since", "demoted_at")},
      dict(stage="sandbox", since=None, demoted_at="2026-10-18T06:00:00+00:00"))
_rm2 = {"pairs": {"pm_combo4|tennis_pmcombo": dict(stage="production", promoted_at="2026-10-01T00:00:00+00:00")}, "events": []}
T.evaluate_stages({"quotes": []}, _rm2, now=datetime(2026, 10, 18, 6, tzinfo=timezone.utc), verbose=False)
check("an ordinary removal still restarts the clock at the removal",
      _rm2["pairs"].get("pm_combo4|tennis_pmcombo", {}).get("since"), "2026-10-18T06:00:00+00:00")
check("ESPN FPI NFL is not paused", S.lane_paused("espn_fpi", "nfl"), False)
check("FTTS rows map to a league like a goals row", S.quote_league(ftts), "Europa League")

print(f"\n{'ALL PASS' if not FAILS else str(len(FAILS)) + ' FAILED'}")
sys.exit(1 if FAILS else 0)
