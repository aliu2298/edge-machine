#!/usr/bin/env python3
"""A rule's display name carries its scope wherever the name is shared across scopes.

"Team scores 1+ form rule · Clubs" and "Team scores 1+ form rule · Internationals" are
two Production rules that used to print as one name. Display only: the registered
label, the source id, the ledger and pair keys, and the Production lead ids are
untouched, and this file holds that line as much as the new one.
"""
import datetime
import re
import sys
from datetime import timezone

import sandbox_build as SB
import sandbox_sources as S
import shell_build
import soccer_cards
import production

FAILS = []


def ok(cond, why):
    print(f"  {'ok  ' if cond else 'FAIL'} {why}")
    if not cond:
        FAILS.append(why)


def eq(got, want, why):
    ok(got == want, why if got == want else f"{why} — got {got!r}, want {want!r}")


print("the helper")
eq(S.scoped_rule("team1_form_l5", "soccer_team1"), "Team scores 1+ form rule · Clubs",
   "the league pair of a rule with twins is the club one")
eq(S.scoped_rule("team1_form_l5", "soccer_team1_intl"), "Team scores 1+ form rule · Internationals",
   "the internationals twin")
eq(S.scoped_rule("team1_form_l5", "soccer_team1_cup"), "Team scores 1+ form rule · Cups", "the cup twin")
eq(S.scoped_rule("bund_o35", "soccer_u35"), "Bundesliga over 3.5, every match",
   "a rule registered on one scope keeps its plain name")
eq(S.scoped_rule("corners_under", "soccer_corners"), "Corners under form rule", "so does a one-sport rule")
eq(S.scoped_rule("crypto_fav_band", "crypto_fav"), "Crypto favourite band", "and a non-soccer rule")
eq(S.scoped_rule("team1_form_l5"), "Team scores 1+ form rule",
   "without a sport the name is plain: the scope cannot be known")
eq(S.scoped_rule("nobody", "soccer"), "nobody", "an unknown source is its id, not a crash")
eq(S.scoped_rule("tennis_fav_band_3h", "tennis").startswith("Tennis favourite band"), True,
   "the parenthetical is dropped as before")
eq(S.CLUB_SCOPE_LABEL, "Clubs", "the league scope word is Clubs")
eq(S.scope_of("soccer_o15_cup"), "_cup", "scope_of reads the cup suffix")
eq(S.scope_of("soccer_o15"), "", "and the league pair has none")
twins = sorted(n for n in S.SOURCES if len(S.rule_scopes(n)) > 1)
ok("team1_form_l5" in twins and "o15_form_l10" in twins and "bund_o35" not in twins,
   f"rule_scopes finds the rules that span scopes ({len(twins)} of them)")
for n in twins:
    names = {S.scoped_rule(n, sp) for sp in S.SOURCES[n]["sports"]}
    eq(len(names), len({S.scope_of(sp) for sp in S.SOURCES[n]["sports"]}), f"{n}: every scope prints a distinct name")
    ok(all(" · " in x for x in names), f"{n}: every scope's name carries its scope")
plain = dict(name="not-a-source", sport="soccer_team1", meta={"label": "A frozen block (x)", "kind": "Rule"},
             a=dict(n=0, won=0, expected=0, roi_fee=None, z=0), open=0, prod=False, moved="", v="waiting", fade={})
eq(SB.rule_name(plain), "A frozen block", "a row without a registered source keeps the label it carries")

print("\nnothing a join reads has moved")
eq(S.SOURCES["team1_form_l5"]["label"], "Team scores 1+ form rule (5/5 scored, opponent 5/5 conceded)",
   "the registered label is unchanged")
eq(S.SOURCES["team1_form_l5"]["sports"], ["soccer_team1", "soccer_team1_cup", "soccer_team1_intl"],
   "the sports list is unchanged")
eq(S.SCOPE_LABEL, {"_cup": "Cups", "_intl": "Internationals"}, "the twin scope words are unchanged")
NOW = datetime.datetime(2026, 10, 8, 12, tzinfo=timezone.utc)
ko = NOW + datetime.timedelta(hours=6)
q = dict(id="team1_form_l5:KXEPLTEAM1-26OCT08ARSCHE-ARS", source="team1_form_l5", sport="soccer_team1_intl",
         market_id="KXEPLTEAM1-26OCT08ARSCHE-ARS", label="Arsenal v Chelsea: Arsenal to score 1+",
         side_a="Yes", side_b="No", pick="a", price=0.7, bet=True, status="open",
         start=ko.isoformat(), date=ko.date().isoformat(), logged=NOW.isoformat(), venue="kalshi_binary",
         url="https://kalshi.com/markets/x", league="Premier League", espn_home="Arsenal", espn_away="Chelsea",
         team="Arsenal", opponent="Chelsea")
lead = production.lead_from_quote(q, "team1_form_l5|soccer_team1_intl", NOW.isoformat())
ok(lead["id"].endswith(" · Team scores 1+ form rule") and "Clubs" not in lead["id"]
   and "Internationals" not in lead["id"], "a Production lead id keeps the plain label")
eq(lead["pair"], "team1_form_l5|soccer_team1_intl", "the pair key is untouched")

print("\nevery display site")
row_intl = dict(name="team1_form_l5", sport="soccer_team1_intl", meta=S.SOURCES["team1_form_l5"],
                a=dict(n=10, won=10, expected=8.0, roi_fee=0.18, z=1.5, clv=None, clv_n=0, n_bets=10, unit=None),
                open=0, last="", fade={}, gone=None, prod=True, moved="2026-10-01", removed=None, v="promising", since=None)
row_club = dict(row_intl, sport="soccer_team1", moved="2026-09-18")
eq(SB._who(row_club), "Team scores 1+ form rule · Clubs", "the Sandbox summary names the club pair")
eq(SB._who(row_intl), "Team scores 1+ form rule · Internationals", "and the internationals pair")
ok("Team scores 1+ form rule · Clubs" in SB._row(row_club) and "Team scores 1+ form rule · Internationals" in SB._row(row_intl),
   "the Sandbox table row carries the scope in the name")
ok("INTERNATIONALS</span>" not in SB._row(row_intl) and "CLUBS</span>" not in SB._row(row_club),
   "and no longer needs a scope chip beside it")
eq(SB._source_label(q), "Team scores 1+ form rule · Internationals", "a ledger row (roll, settled, archive) names its scope")
eq(SB._source_label(dict(q, sport="soccer_team1")), "Team scores 1+ form rule · Clubs", "the club pair's row says Clubs")
defs = SB.definitions([row_club, row_intl])
ok("· Rule · Clubs, Internationals" in defs, "the definitions block lists the scopes as Clubs and Internationals")
eq(shell_build._lane_name("team1_form_l5", "soccer_team1"), "Team scores 1+ form rule · Clubs", "the home page rule card and bets roll")
eq(shell_build._lane_name("team1_form_l5", "soccer_team1_intl"), "Team scores 1+ form rule · Internationals", "same, internationals")
eq(shell_build._lane_name("bund_o35", "soccer_u35"), "Bundesliga over 3.5, every match", "a one-scope rule stays plain on the home page")
eq(soccer_cards._rule_name(row_club), "Team scores 1+ form rule · Clubs", "the soccer rules table")
eq(soccer_cards._scoped_name(row_intl), "Team scores 1+ form rule · Internationals", "the soccer Production chip")

stages = {"pairs": {"team1_form_l5|soccer_team1": {"stage": "production", "by_hand": "2026-09-18",
                                                     "ready_at": "2026-09-18T00:00:00+00:00"},
                    "team1_form_l5|soccer_team1_intl": {"stage": "production", "by_hand": "2026-10-01",
                                                          "ready_at": "2026-10-01T00:00:00+00:00"}}}
settled = dict(q, id="settled", status="won", result="a", pnl=42.86, settled=NOW.isoformat(),
               start=(NOW - datetime.timedelta(days=1)).isoformat(), date=(NOW - datetime.timedelta(days=1)).date().isoformat())
page = production.page({"quotes": [settled]}, stages, {"leads": {}, "pairs": {}}, "", now=NOW)
ok("Team scores 1+ form rule · Clubs" in page and "Team scores 1+ form rule · Internationals" in page,
   "the Production pairs table tells the two rules apart")
ok(">Team scores 1+ form rule</b>" not in page, "and never prints the shared plain name as a pair")

if FAILS:
    print(f"\nFAILED {len(FAILS)}")
    sys.exit(1)
print("all passed")
