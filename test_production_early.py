#!/usr/bin/env python3
"""Six rules moved to Production on 2026-10-08 as EARLY pairs, and the Early state itself.

Three things are held here. The six (source, sport) ids are listed by hand with that move
date, and each resolves from the display name it was asked for -- not the label, which an
open PR may change -- to one rule id. The feed can express every one of their picks the
way it expresses the current pairs: the over-1.5 Yes, the BTTS Yes, the over-3.5 Yes on
the league under domain, a basket of Kalshi legs, and a Kalshi daily-close ladder rung.
And the Early badge: "Early · N bets" on a Production pair moved on or after the state's
date with under EARLY_N settled since its move, on the Production pairs table, its sport
page's Rules table and the home rule cards, dropping on its own at EARLY_N and never on a
pair moved before that date. No network, nothing read from data/.
"""
import datetime
import re
import sys
from datetime import timedelta, timezone

import cricket_cards
import crypto_build
import production as PR
import sandbox_build as SB
import sandbox_sources as S
import sandbox_track as T
import shell_build
import soccer_cards
import tennis_cards

FAILS = []


def ok(cond, why):
    print(f"  {'ok  ' if cond else 'FAIL'} {why}")
    if not cond:
        FAILS.append(why)


def eq(got, want, why):
    ok(got == want, why if got == want else f"{why} — got {got!r}, want {want!r}")


MOVE = "2026-10-08"
NOW = datetime.datetime(2026, 10, 8, 18, 30, tzinfo=timezone.utc)
BUILT = NOW.isoformat()
KO = (NOW + timedelta(hours=20)).isoformat()
SIX = {
    "crypto_fav_band|crypto_fav": "Crypto favourite band",
    "tennis_combo2|tennis_combo": "Tennis 2-leg combo",
    "o15_form_l10|soccer_o15": "Over 1.5 form rule",
    "o15_ranked|soccer_o15": "Over 1.5, ranked: the day's top 2 mismatches under 0.80",
    "liga_btts_even|soccer_btts": "La Liga BTTS in balanced matches",
    "bund_o35|soccer_u35": "Bundesliga over 3.5, every match",
}

# ---------------------------------------------------------------------------
print("the six ids are in Production, moved by hand on the same day")
# ---------------------------------------------------------------------------
for key, name in SIX.items():
    ov = T.PAIR_OVERRIDES.get(key)
    eq((ov or {}).get("moved_on"), MOVE, f"{key} is listed with move date {MOVE}")
    ok(ov is not None and ov.get("production_at") is None,
       f"{key} is ready from the run that moves it, like the existing pairs")
    source, sport = key.split("|", 1)
    meta = S.SOURCES.get(source) or {}
    eq(str(meta.get("label", "")).split(" (")[0], name, f"{source} is the rule named {name!r}")
    ok(sport in (meta.get("sports") or []), f"{sport} is a scope {source} is registered on")
    ok(meta.get("connected") and meta.get("kind") == "Rule", f"{source} is a connected rule")
# Each display name maps to ONE rule id. The ambiguous neighbours are named here so the
# listing cannot drift onto them.
ok("pm_combo2|tennis_pmcombo" not in T.PAIR_OVERRIDES
   and S.SOURCES["pm_combo2"]["label"].startswith("Tennis 2-leg combo on Polymarket US"),
   "the combo is the Kalshi basket, not the Polymarket US one")
ok("bund_o35_fav|soccer_u35" not in T.PAIR_OVERRIDES
   and "2.00-2.60" in S.SOURCES["bund_o35_fav"]["label"],
   "the Bundesliga rule is every match, not the favourite-priced variant")
for twin in ("o15_form_l10|soccer_o15_cup", "o15_form_l10|soccer_o15_intl",
             "o15_ranked|soccer_o15_cup"):
    ok(twin not in T.PAIR_OVERRIDES, f"{twin} is not listed: league scope only")
ok("o15_ranked|soccer_o15_intl" in T.PAIR_OVERRIDES
   and T.PAIR_OVERRIDES["o15_ranked|soccer_o15_intl"]["moved_on"] == "2026-10-01",
   "the ranked rule's internationals pair keeps its own earlier listing")
# The tennis rules are frozen from 2026-10-08. Promotion is a paper decision, not a
# parameter change: the band, the basket markup and the reset stamp read as they did.
eq((S.TENNIS_3H_BAND, S.COMBO_MARKUP[2], S.TENNIS_COMBO_BAND_SINCE),
   ((0.70, 0.85), 0.0084, "2026-10-04T06:46:57+00:00"),
   "promotion touches no tennis parameter")
eq(len(T.PAIR_OVERRIDES), 12, "five pairs before, eleven after the six, twelve with commodities (2026-10-09)")

# The tracker moves them on its next run, and the Since-Production record starts there.
_stages = {"pairs": {}, "events": []}
_changes = T.evaluate_stages({"quotes": []}, _stages, now=NOW, verbose=False)
for key in SIX:
    pair = _stages["pairs"].get(key) or {}
    eq((pair.get("stage"), pair.get("by_hand"), pair.get("ready_at")),
       ("production", MOVE, BUILT), f"{key} moves on the run after the merge, ready at that run")
ok(all(c["pair"] in T.PAIR_OVERRIDES for c in _changes), "nothing moved that was not listed")


# ---------------------------------------------------------------------------
print("\nthe Early badge: text and threshold")
# ---------------------------------------------------------------------------
eq(PR.EARLY_N, 10, "the threshold is the same ten the ROI greys under")
eq(PR.EARLY_STATE_SINCE, MOVE, "the state exists from the day the six moved")
eq(PR.early_label(0), "Early · 0 bets", "nothing settled yet reads Early · 0 bets")
eq(PR.early_label(1), "Early · 1 bet", "one bet is singular")
eq(PR.early_label(9), "Early · 9 bets", "nine is still early")
eq(PR.early_label(10), None, "the badge drops at ten")
eq(PR.early_label(37), None, "and stays off")
eq(PR.early_label(None), "Early · 0 bets", "no count reads as none settled")
eq(PR.early_label("x"), None, "an unreadable count is no badge, not a crash")
_new = {"stage": "production", "by_hand": MOVE, "ready_at": BUILT}
_old = {"stage": "production", "by_hand": "2026-10-04", "ready_at": "2026-10-04T07:03:02+00:00"}
eq(PR.early_state(_new, 3), "Early · 3 bets", "a pair moved on the date with three settled is early")
eq(PR.early_state(_new, 10), None, "the same pair at ten is not")
eq(PR.early_state(_old, 3), None, "a pair moved BEFORE the date is never badged: existing pairs are unaffected")
eq(PR.early_state(dict(_new, stage="sandbox"), 0), None, "a Sandbox pair has no Early state")
eq(PR.early_state(None, 0), None, "no pair, no badge")
eq(PR.early_html("Early · 2 bets"), ' <span class="sig w early">Early · 2 bets</span>',
   "the badge is one chip beside the Production one")
eq(PR.early_html(None), "", "and nothing when there is no badge")


def _settled(i, key, won=True, days_after=0):
    source, sport = key.split("|", 1)
    start = NOW + timedelta(days=days_after, hours=i)
    return dict(id=f"{source}:{i}", source=source, sport=sport, market_id=f"M-{i}", bet=True,
                pick="a", price=0.6, price_a=0.6, price_b=0.42, price_draw=None,
                status="won" if won else "lost", result="a" if won else "b",
                pnl=round(100 * (1 / 0.6 - 1), 2) if won else -100.0, stake=100.0,
                venue="kalshi_binary", side_a="Yes", side_b="No", label=f"x {i}",
                start=start.isoformat(), logged=NOW.isoformat(), espn_home="A", espn_away="B",
                league="Bundesliga", start_source="espn")


KEY = "bund_o35|soccer_u35"
_ledger = {"quotes": [_settled(i, KEY, won=i % 3 != 0) for i in range(4)]}
eq(PR.early_badge(_ledger, KEY, _new), "Early · 4 bets", "early_badge counts the settled bets since the move")
_nine = {"quotes": [_settled(i, KEY) for i in range(9)]}
_ten = {"quotes": [_settled(i, KEY) for i in range(10)]}
eq(PR.early_badge(_nine, KEY, _new), "Early · 9 bets", "nine settled since the move is still badged")
eq(PR.early_badge(_ten, KEY, _new), None, "the tenth settled bet drops it, with no change anywhere else")
_before = {"quotes": [dict(_settled(i, KEY), start=(NOW - timedelta(days=2, hours=i)).isoformat())
                      for i in range(10)]}
eq(PR.early_badge(_before, KEY, _new), "Early · 0 bets",
   "bets on contests before the move are the Sandbox record, not the since-Production one")
eq(PR.early_badge(_ten, KEY, _old), None, "an older pair is not read at all")
eq(PR.early_badge(_ten, KEY, None), None, "no stage record, no badge")


# ---------------------------------------------------------------------------
print("\nthe feed expresses each of the six like the current pairs")
# ---------------------------------------------------------------------------
def _goals(source, sport, mid, **extra):
    q = dict(id=f"{source}:{mid}", source=source, sport=sport, market_id=mid, bet=True,
             pick="a", price=0.7, price_a=0.7, price_b=0.32, price_draw=None, status="open",
             result=None, pnl=0.0, stake=100.0, start=KO, logged=NOW.isoformat(),
             label="x", side_a="Yes", side_b="No", venue="kalshi_binary", league="Bundesliga",
             espn_home="SC Freiburg", espn_away="Schalke 04", start_source="espn", team=None)
    q.update(extra)
    return q


# Over 1.5, league scope: the Yes on KX<league>TOTAL-2, as the internationals pair publishes.
for source in ("o15_form_l10", "o15_ranked"):
    q = _goals(source, "soccer_o15", "KXSERIEATOTAL-26OCT11LECBFC-2", league="Serie A",
               espn_home="Lecce", espn_away="Bologna")
    ok(T.placeable(q) and PR.start_verified(q), f"{source}: a league over-1.5 Yes with an ESPN start reaches the feed")
    lead = PR.lead_from_quote(q, f"{source}|soccer_o15", BUILT)
    eq((lead["headline"], lead["bet"], lead.get("route")), ("Over 1.5 goals", {"kind": "total_gte", "n": 2}, None),
       f"{source}: the lead claims over 1.5 as a plain Yes")
    eq(lead["match"], "Lecce v Bologna", f"{source}: on its fixture")
    ok(not T.placeable(dict(q, sport="soccer_o15_cup", league="EFL Cup")), f"{source}: the cup twin still does not")

# BTTS: the Yes on KXLALIGABTTS-...-BTTS, league scope.
btts = _goals("liga_btts_even", "soccer_btts", "KXLALIGABTTS-26OCT10ALAATM-BTTS", league="La Liga",
              espn_home="Alavés", espn_away="Atlético Madrid", price=0.54)
eq(S.quote_league(btts), "La Liga", "a BTTS row maps to its league like a goals row")
ok(T.placeable(btts) and PR.start_verified(btts), "BTTS Yes in a mapped league with an ESPN start reaches the feed")
ok(not T.placeable(dict(btts, pick="b")), "its No is a different claim and is not published")
ok(not T.placeable(dict(btts, league="Allsvenskan")), "nor an unmapped league")
ok(not T.placeable(dict(btts, espn_home=None)), "and it still needs its fixture")
lead = PR.lead_from_quote(btts, "liga_btts_even|soccer_btts", BUILT)
eq((lead["headline"], lead["bet"], lead.get("route"), lead["league"]),
   ("Both teams to score", {"kind": "btts"}, None, "La Liga"), "the lead says both teams to score, a plain Yes")
eq(lead["id"], "2026-10-09|Alavés|Atlético Madrid|Both teams to score · La Liga BTTS in balanced matches",
   "the lead id names the fixture, the claim and the rule's plain label")
eq(T.feed_pick("soccer_btts"), "a", "BTTS is a Yes kind")

# Bundesliga over 3.5: the YES on the same KX...TOTAL-4 contract the under rule backs the No on.
over = _goals("bund_o35", "soccer_u35", "KXBUNDESLIGATOTAL-26OCT11SCFSCH-4", price=0.39)
ok(T.placeable(over) and PR.start_verified(over), "the Bundesliga over-3.5 Yes reaches the feed")
lead = PR.lead_from_quote(over, KEY, BUILT)
eq((lead["headline"], lead["bet"], lead.get("route")), ("Over 3.5 goals", {"kind": "total_gte", "n": 4}, None),
   "the lead claims over 3.5 as a plain Yes, no route needed")
under = dict(over, source="u35_low_scoring", pick="b")
ok(T.placeable(under), "the No on the same contract is the under, still expressible")
ulead = PR.lead_from_quote(under, "u35_low_scoring|soccer_u35", BUILT)
eq((ulead["headline"], ulead["bet"], ulead["route"]["outcome_side"]),
   ("Under 3.5 goals", {"kind": "total_lte", "n": 3}, "no"),
   "and it is published the way the internationals under is: named contract, No side")
eq(T.feed_bet(over), {"kind": "total_gte", "n": 4}, "feed_bet reads the over off the Yes pick")
eq(T.feed_bet(under), {"kind": "total_lte", "n": 3}, "and the under off the No")
eq(T.feed_bet(dict(over, pick="draw")), None, "a pick on no named side is nothing")
eq(T.feed_pick("soccer_u35"), "b", "the domain's NAMED bet is still the under")
eq(T.FEED_YES_TWIN, {"soccer_u35": {"kind": "total_gte", "n": 4}}, "the Yes twin exists on the league under domain only")
eq(T.feed_bet(dict(over, sport="soccer_u35_intl")), None,
   "the internationals under domain has no over twin: no rule there backs the Yes")
ok(not T.placeable(dict(over, sport="soccer_u35_cup", league="DFB Pokal")), "the cup twin still does not")

# The tennis combo: a basket of Kalshi legs, published as a quote request, verified by its legs.
def _basket(start_source="tennisexplorer"):
    legs = [dict(market_id="KXATPMATCH-26OCT09SAKRUB", name="Andrey Rublev", pick="b", start=KO, venue="kalshi"),
            dict(market_id="KXATPMATCH-26OCT09ZHOMUS", name="Lorenzo Musetti", pick="b", start=KO, venue="kalshi")]
    return dict(id="tennis_combo2:combo2:2026-10-09:x", source="tennis_combo2", sport="tennis_combo",
                market_id="combo2:2026-10-09:x", label="2-leg tennis combo: Andrey Rublev + Lorenzo Musetti",
                side_a="All 2 win", side_b="Any one loses", pick="a", price=0.5954, venue="combo", bet=True,
                status="open", start=KO, logged=NOW.isoformat(), start_source=start_source, legs=legs)


basket = _basket()
ok(T.placeable(basket) and PR.start_verified(basket), "a 2-leg basket of Kalshi legs with verified starts reaches the feed")
lead = PR.lead_from_quote(basket, "tennis_combo2|tennis_combo", BUILT)
eq(lead["bet"], {"kind": "combo", "n": 2, "all_must_win": True}, "the lead is a combo claim")
eq((lead["route"]["instrument"], lead["route"]["how"], lead["route"]["max_price"], len(lead["route"]["legs"])),
   ("combo", "request_quote", 0.5954, 2), "routed as a quote request with the legs and the price ceiling")
ok(not PR.start_verified(_basket(start_source=None)), "a basket whose legs carry no verified start is held back")
pm = dict(basket, source="pm_combo2", sport="tennis_pmcombo",
          legs=[dict(l, venue="polymarket_us") for l in basket["legs"]])
ok(not T.placeable(pm), "the Polymarket US basket is still refused: nothing can act on one")

# Crypto: one rung of a Kalshi daily-close ladder, the close read off the contract.
rung = dict(id="crypto_fav_band:KXBTCD-26OCT0817-T82749.99", source="crypto_fav_band", sport="crypto_fav",
            market_id="KXBTCD-26OCT0817-T82749.99", label="Bitcoin price on Oct 8, 2026?",
            side_a="$82,750 or above", side_b="No", pick="a", price=0.78, price_a=0.78, price_b=0.24,
            price_draw=None, venue="kalshi_binary", bet=True, status="open",
            start="2026-10-08T21:05:00+00:00", venue_start=None, start_source=None,
            logged="2026-10-08T17:49:59+00:00", date="2026-10-08")
eq(T.LADDER_SPORTS, ("crypto_fav", "commodities_fav"), "the ladder sports are the crypto and commodities favourite bands")
ok(T.placeable(rung), "a Kalshi ladder rung's Yes reaches the feed")
ok(PR.start_verified(rung), "its close is a term of the contract, so it needs no outside verification")
ok(not PR.start_verified(dict(rung, start="not a time")), "but a rung with no readable close is held back")
ok(not T.placeable(dict(rung, pick="b")), "the No side is never the rule's bet")
ok(not T.placeable(dict(rung, venue="polymarket_us")), "and only Kalshi lists the ladder")
lead = PR.lead_from_quote(rung, "crypto_fav_band|crypto_fav", BUILT)
eq(lead["headline"], "$82,750 or above at the close", "the lead names the rung as the venue does")
eq(lead["match"], "Bitcoin price on Oct 8, 2026", "and the coin's close as the contest")
eq(lead["bet"], {"kind": "ladder", "side": "yes"}, "the claim is the Yes on a ladder rung")
eq(lead["route"], {"venue": "kalshi", "market": "KXBTCD-26OCT0817-T82749.99",
                   "outcome": "$82,750 or above", "outcome_side": "yes"},
   "routed to the exact contract and rung")
eq((lead["kickoff"], lead["league"], lead["home"], lead["away"]),
   ("2026-10-08T21:05Z", "Crypto · Favourite band", None, None), "the kickoff is the close")
eq(lead["id"], "2026-10-08|KXBTCD-26OCT0817-T82749.99|$82,750 or above at the close · Crypto favourite band",
   "one lead per rung per close")
eq(lead["status"], "pending", "open until the close")

# The feed itself, on the daily-close schedule: logged 2.8h before the close, published that run,
# still pending at the next run, settled after the close.
stages = {"pairs": {"crypto_fav_band|crypto_fav": dict(_new)}}
at_log = datetime.datetime(2026, 10, 8, 18, 11, tzinfo=timezone.utc)
feed = PR.build_feed({"quotes": [rung]}, stages, now=at_log)
eq([l["status"] for l in feed["leads"].values()], ["pending"], "the rung is published on the run that logged it")
eq((feed["unlisted_skipped"], feed["unverified_kickoff_skipped"]), (0, 0), "nothing held back")
later = PR.build_feed({"quotes": [rung]}, stages, now=datetime.datetime(2026, 10, 8, 20, 11, tzinfo=timezone.utc))
eq(len(later["leads"]), 1, "still on the feed at the next run before the close")
won = dict(rung, status="won", result="a", pnl=28.21, settled="2026-10-08T21:30:00+00:00")
after = PR.build_feed({"quotes": [won]}, stages, now=datetime.datetime(2026, 10, 9, 2, 11, tzinfo=timezone.utc))
eq([l["status"] for l in after["leads"].values()], ["hit"], "and reads hit once the close settles it")
yesterday = dict(rung, market_id="KXBTCD-26OCT0717-T82749.99", id="crypto_fav_band:KXBTCD-26OCT0717-T82749.99",
                 start="2026-10-07T21:05:00+00:00", status="won", result="a", pnl=28.21)
eq(len(PR.build_feed({"quotes": [rung, yesterday]}, stages, now=at_log)["leads"]), 1,
   "a close before the move is the Sandbox record, not a lead")
eq(PR.pair_health("crypto_fav_band|crypto_fav", [rung], 1, feed["pairs"], now=at_log), ("ok", "publishing"),
   "the pair's light is green: nothing it logs is dropped")

# One lead for every one of the six, through the one feed builder, with the one stage file.
stages6 = {"pairs": {key: dict(_new) for key in SIX}}
ledger6 = {"quotes": [
    _goals("o15_form_l10", "soccer_o15", "KXSERIEATOTAL-26OCT11LECBFC-2", league="Serie A"),
    _goals("o15_ranked", "soccer_o15", "KXSERIEATOTAL-26OCT11LECBFC-2", league="Serie A"),
    btts, over, basket, rung,
]}
feed6 = PR.build_feed(ledger6, stages6, now=NOW)
eq(sorted(l["pair"] for l in feed6["leads"].values()), sorted(SIX), "each of the six publishes one lead")
eq((feed6["unlisted_skipped"], feed6["unverified_kickoff_skipped"]), (0, 0), "with nothing held back")
eq(set(feed6["pairs"]), set(SIX), "and the feed's pairs map names all six")


# ---------------------------------------------------------------------------
print("\nwhere the badge shows")
# ---------------------------------------------------------------------------
# The Production pairs table, built from a ledger with three settled since the move.
d3 = {"quotes": [_settled(i, KEY, won=i != 1) for i in range(3)]
      + [_settled(i, "u35_low_scoring|soccer_u35_intl", won=True) for i in range(3)]}
# The settled bets kicked off after the move but settle before the page clock.
page_now = NOW + timedelta(days=2)
st_page = {"pairs": {KEY: dict(_new), "u35_low_scoring|soccer_u35_intl": dict(_old)}}
html = PR.page(d3, st_page, {"leads": {}, "pairs": {}}, "", now=page_now)
row = html.split("Bundesliga over 3.5, every match", 1)[1].split("</tr>", 1)[0]
ok('<span class="sig w early">Early · 3 bets</span>' in row, "the Production pairs table badges the new pair")
ok('class="mut">' in row.split("too early", 1)[0] and "too early" in row,
   "its since-Production ROI stays grey and marked too early, as before")
old_row = html.split("Under 3.5 low-scoring rule", 1)[1].split("</tr>", 1)[0]
ok("Early" not in old_row, "a pair moved before the state existed shows no badge on three settled")
ok("· 2 · 1 early" in html, "the Pairs fold counts how many are early")
ok(f"moved on or after {MOVE}" in html and "<b>Early</b>" in html, "and the table's note says what the badge means")
d10 = {"quotes": [_settled(i, KEY) for i in range(10)]}
html10 = PR.page(d10, {"pairs": {KEY: dict(_new)}}, {"leads": {}, "pairs": {}}, "", now=page_now)
ok("Early" not in html10.split("<section", 1)[1].split("</section>", 1)[0].split("<p class", 1)[0]
   and 'sig w early' not in html10, "at ten settled the badge is gone from the table")
ok("· 1</span>" in html10 and "early</span>" not in html10, "and the fold no longer counts an early pair")
_empty = PR.page({"quotes": []}, {"pairs": {}}, {"leads": {}, "pairs": {}}, "", now=page_now)
ok('sig w early' not in _empty and "early</span>" not in _empty, "an empty Production has nothing to badge")

# The Sandbox row model: pair_list carries the badge text, so every sport page reads one value.
rows = SB.pair_list(d3, st_page)
by = {f"{r['name']}|{r['sport']}": r for r in rows}
eq(by[KEY].get("early"), "Early · 3 bets", "the pair row carries its Early text")
eq(by["u35_low_scoring|soccer_u35_intl"].get("early"), None, "an older pair's row carries none")
eq(SB.pair_list(d10, {"pairs": {KEY: dict(_new)}})[0].get("early"), None, "and at ten the row carries none")


def _row(key, early, **over):
    source, sport = key.split("|", 1)
    r = dict(name=source, sport=sport, meta=S.SOURCES[source],
             a=dict(n=3, won=2, expected=1.8, roi_fee=0.12, z=0.4, clv=None, clv_n=0, n_bets=3, unit=None,
                    roi=0.15, pnl=36.0),
             open=1, last="", fade={}, gone=None, prod=True, moved=MOVE, removed=None, v="early",
             since=None, early=early)
    r.update(over)
    return r


# Soccer: the Status chip.
soc = soccer_cards._rule_rows(d3, _row(KEY, "Early · 3 bets"), 0)
ok('<span class="sig y">Production</span> <span class="sig w early">Early · 3 bets</span>' in soc,
   "the soccer Rules table badges beside the Production chip")
ok("Early" not in soccer_cards._rule_rows(d3, _row(KEY, None), 0), "and not once the text is gone")
ok("Early" not in soccer_cards._rule_rows(d3, _row(KEY, "Early · 3 bets", prod=False), 0),
   "a Sandbox row never shows one, whatever it carries")
ok('<span class="sig y">Production</span> <span class="sig w early">Early · 3 bets</span>'
   in soccer_cards.rules_table(d3, [_row(KEY, "Early · 3 bets")]), "through the whole table")
# Tennis: the summary badges.
ten = tennis_cards._rule_row({"quotes": []}, _row("tennis_combo2|tennis_combo", "Early · 0 bets"), NOW)
ok('<span class="sig y">PRODUCTION</span> <span class="sig w early">Early · 0 bets</span>' in ten,
   "the tennis Rules table badges beside PRODUCTION")
ok("Early" not in tennis_cards._rule_row({"quotes": []}, _row("tennis_combo2|tennis_combo", None), NOW),
   "and drops it with the text")
# Cricket: the same row shape.
cri = cricket_cards._rule_row({"quotes": []}, _row("oddspedia|cricket", "Early · 2 bets"), NOW)
ok('<span class="sig y">PRODUCTION</span> <span class="sig w early">Early · 2 bets</span>' in cri,
   "the cricket Rules table would badge an early pair the same way")
# Crypto: the one-row rule table.
cry = crypto_build.rule_html([_row("crypto_fav_band|crypto_fav", "Early · 0 bets",
                                   a=dict(n=0, won=0, expected=0, roi_fee=None, n_bets=0, unit="market-day"))],
                             {"quotes": []})
ok('<span class="sig y">PRODUCTION</span> <span class="sig w early">Early · 0 bets</span>' in cry,
   "the crypto rule row badges beside PRODUCTION")
ok("Early" not in crypto_build.rule_html([_row("crypto_fav_band|crypto_fav", None,
                                              a=dict(n=0, won=0, expected=0, roi_fee=None, n_bets=0, unit="market-day"))],
                                         {"quotes": []}), "and not without the text")

# The home rule cards: the card carries the text and shell.js prints it as a pill.
board = shell_build._lane_board(d3, st_page, KEY, {})
eq(board.get("early"), "Early · 3 bets", "the home card board reads the same badge")
eq(shell_build._lane_board(d3, st_page, "u35_low_scoring|soccer_u35_intl", {}).get("early"), None,
   "and none for an older pair")
lane = {"source": "bund_o35", "sport_key": "soccer_u35", "lane": "Production", "price": 0.39,
        "status": "Open", "headline": "Over 3.5 goals", "venue": "kalshi_binary"}
card = shell_build._card(lane, board)
eq((card["pill"], card.get("early")), ("PRODUCTION", "Early · 3 bets"), "a Production card carries the badge")
ok("early" not in shell_build._card(dict(lane, lane="sandbox"), board), "a Sandbox card never does")
ok("early" not in shell_build._card(lane, dict(board, early=None)), "nor a Production card past ten")
js = open("public_site/shell.js", encoding="utf-8").read()
ok('if (card.early)' in js and 'early.className = "lane-pill early"' in js
   and "early.textContent = card.early" in js, "shell.js prints the badge as a pill beside PRODUCTION")
css = open("public_site/site.css", encoding="utf-8").read()
ok(".rule-mini .lane-pill.early" in css and ".sig.early" in css, "the pill and the chip are styled")

# ---------------------------------------------------------------------------
print("\nthe Sandbox record keeps its clock through the move")
# ---------------------------------------------------------------------------
# o15_form_l10|soccer_o15 came off Production on 2026-09-21 and its Sandbox clock
# restarted there: 4-0 on 4 since, 24-6 on 30 in all. The move must not change that
# record -- it changes where the picks publish, nothing beside them.
CLOCK = "2026-09-21T01:44:02+00:00"
O15 = "o15_form_l10|soccer_o15"


def _o15(i, when, won):
    q = _settled(i, O15, won=won)
    q.update(start=(when + timedelta(hours=i)).isoformat(), logged=when.isoformat(),
             market_id=f"KXMLSTOTAL-26SEP{10 + i}X-2", league="MLS")
    return q


before = datetime.datetime(2026, 9, 15, 12, tzinfo=timezone.utc)
after = datetime.datetime(2026, 9, 25, 12, tzinfo=timezone.utc)
d_o15 = {"quotes": [_o15(i, before, won=i % 5 != 0) for i in range(26)]
         + [_o15(100 + i, after, won=True) for i in range(4)]}
# The live stage row: a Sandbox clock and no demoted_at, because the 2026-09-21 removal
# was made by hand before by-hand removals were stamped. (A pair whose demotion IS
# stamped and is then re-listed has that demotion cancelled by evaluate_stages, and its
# whole record counts again, on purpose; that is a different row from this one.)
st_o15 = {"pairs": {O15: {"stage": "sandbox", "since": CLOCK}}, "events": []}
_grp, a_before, *_ = SB.pair_status(d_o15, st_o15, "o15_form_l10", "soccer_o15")
eq((a_before["n"], a_before["won"]), (4, 4), "before the move the Sandbox record counts from the clock")
T.evaluate_stages(d_o15, st_o15, now=NOW, verbose=False)
moved = st_o15["pairs"][O15]
eq((moved["stage"], moved.get("since"), moved.get("entry_since")), ("production", None, CLOCK),
   "the move carries the clock into entry_since")
eq(T.record_since(moved), CLOCK, "record_since reads it back")
eq(T.record_since({"stage": "sandbox", "since": CLOCK}), CLOCK, "and a Sandbox pair's own clock")
eq(T.record_since({"stage": "production"}), None, "a pair that never reset has no clock: its whole record")
eq(T.record_since(None), None, "no pair, no clock")
_grp, a_after, *_ = SB.pair_status(d_o15, st_o15, "o15_form_l10", "soccer_o15")
eq((a_after["n"], a_after["won"]), (4, 4), "after the move the Sandbox row still counts 4-0 on 4, not 24-6 on 30")
page_o15 = PR.page(d_o15, st_o15, {"leads": {}, "pairs": {}}, "", now=NOW + timedelta(days=1))
row_o15 = page_o15.split("Over 1.5 form rule", 1)[1].split("</tr>", 1)[0]
ok('<td class="num">4<div class="sm mut">settled</div></td>' in row_o15,
   "and the Production pairs table's Sandbox Bets column says 4")
ok('<td class="num">30<div class="sm mut">settled</div></td>' not in row_o15, "never 30")
row_list = next(r for r in SB.pair_list(d_o15, st_o15) if r["name"] == "o15_form_l10" and r["sport"] == "soccer_o15")
eq(row_list["since"], CLOCK, "the row carries the clock for the league split and the pick lists")

# ---------------------------------------------------------------------------
print("\ncommodities (2026-10-09): the same rung on Kalshi's daily commodity ladders")
# ---------------------------------------------------------------------------
CKEY = "commod_fav_band|commodities_fav"
CMOVE = "2026-10-09"
eq((T.PAIR_OVERRIDES.get(CKEY) or {}).get("moved_on"), CMOVE, f"{CKEY} is listed with move date {CMOVE}")
ok(T.PAIR_OVERRIDES[CKEY].get("production_at") is None, "ready from the run that moves it")
eq(S.SOURCES["commod_fav_band"]["sports"], ["commodities_fav"], "one pair: the lane has one sport")
ok(not S.lane_paused("commod_fav_band", "commodities_fav") and not S.lane_removed("commod_fav_band", "commodities_fav")
   and "commod_fav_band" not in S.PAUSED_LANES, "the lane is not paused and not removed: it logs")
eq(T.LADDER_SPORTS, ("crypto_fav", "commodities_fav"), "it is a ladder sport beside crypto")
# No `since` on a lane that never reset, so the record is the whole record, and the
# Early badge counts from the move like the six before it.
_cst = {"pairs": {}, "events": []}
T.evaluate_stages({"quotes": []}, _cst, now=NOW, verbose=False)
_cp = _cst["pairs"][CKEY]
eq((_cp["stage"], _cp["by_hand"], _cp["ready_at"]), ("production", CMOVE, BUILT), "it moves on the run after the merge")
eq(PR.early_badge({"quotes": []}, CKEY, _cp), "Early · 0 bets", "and wears the Early badge with nothing settled since")

# The live crypto lead downstream already reads, copied from data/production_leads.json
# on 2026-10-09. A commodities lead must carry exactly these fields.
CRYPTO_LEAD = {
    "away": None, "bet": {"kind": "ladder", "side": "yes"}, "date": "2026-10-08",
    "edge_at_log": None, "first_seen": "2026-10-08", "headline": "$80,250 or above at the close",
    "home": None,
    "id": "2026-10-08|KXBTCD-26OCT0817-T80249.99|$80,250 or above at the close · Crypto favourite band",
    "kickoff": "2026-10-08T21:05Z", "lane": "production", "league": "Crypto · Favourite band",
    "match": "Bitcoin price on Oct 8, 2026", "pair": "crypto_fav_band|crypto_fav", "price_at_log": 0.76,
    "route": {"market": "KXBTCD-26OCT0817-T80249.99", "outcome": "$80,250 or above",
              "outcome_side": "yes", "venue": "kalshi"},
    "sandbox_quote": "crypto_fav_band:KXBTCD-26OCT0817-T80249.99", "source": "crypto_fav_band",
    "sport": "crypto_fav", "status": "hit",
}


def _crung(series, strike, close, price=0.78, logged=None, **over):
    """A commodities row as the ledger stores it (store_book: bid, ask, ask_size)."""
    token = close.strftime("%y%b%d").upper() + ("14" if series == "KXWTI" else "17")
    q = dict(id=f"commod_fav_band:{series}-{token}-T{strike}", source="commod_fav_band",
             sport="commodities_fav", market_id=f"{series}-{token}-T{strike}",
             label=f"Will the {series} close price be above {strike} on {close:%B %d, %Y}?",
             side_a=f"Above ${strike}", side_b="No", pick="a", price=price, price_a=price,
             price_b=round(1 - price, 2), price_draw=None, venue="kalshi_binary", bet=True,
             status="open", start=close.isoformat(), venue_start=None, start_source=None,
             logged=(logged or close - timedelta(hours=2, minutes=50)).isoformat(),
             date=close.strftime("%Y-%m-%d"), bid=round(price - 0.01, 2), ask=price, ask_size=200)
    q.update(over)
    return q


MON = datetime.datetime(2026, 10, 12, tzinfo=timezone.utc)
wti = _crung("KXWTI", "92.49", MON.replace(hour=18, minute=30))
gold = _crung("KXGOLDD", "4006", MON.replace(hour=21, minute=0))
for q, close in ((wti, "2026-10-12T18:30Z"), (gold, "2026-10-12T21:00Z")):
    ok(T.placeable(q) and PR.start_verified(q), f"{q['market_id']}: a commodity rung's Yes reaches the feed")
    lead = PR.lead_from_quote(q, CKEY, BUILT)
    eq(lead["kickoff"], close, f"{q['market_id']}: the kickoff is the market's own close, read from the row")
    eq(lead["route"], {"venue": "kalshi", "market": q["market_id"], "outcome": q["side_a"], "outcome_side": "yes"},
       f"{q['market_id']}: routed to the exact contract and rung, Yes side")
    eq(lead["bet"], {"kind": "ladder", "side": "yes"}, f"{q['market_id']}: the claim is a ladder Yes")
    eq(lead["price_at_log"], 0.78, f"{q['market_id']}: the price the rule paid")
    eq(set(lead), set(CRYPTO_LEAD) - {"last_seen", "last_seen_at"} | {"last_seen", "last_seen_at"},
       f"{q['market_id']}: the same fields as the crypto lead, plus the open lead's last-seen stamps")
    eq(set(lead["route"]), set(CRYPTO_LEAD["route"]), f"{q['market_id']}: the same route fields")
    eq((lead["home"], lead["away"], lead["league"], lead["lane"], lead["status"]),
       (None, None, "Commodities · Favourite band", "production", "pending"),
       f"{q['market_id']}: no sides, the lane's league, pending until the close")
eq(PR.lead_from_quote(wti, CKEY, BUILT)["match"], "WTI crude close on Oct 12, 2026", "the contest names the commodity and its close")
eq(PR.lead_from_quote(gold, CKEY, BUILT)["headline"], "Above $4006 at the close", "the headline is the rung as Kalshi names it")
eq(PR.lead_from_quote(gold, CKEY, BUILT)["id"],
   "2026-10-12|KXGOLDD-26OCT1217-T4006|Above $4006 at the close · Commodities favourite band",
   "one lead per rung per close")

# The calendar: a close on a day the series does not trade is never published.
fri = datetime.datetime(2026, 10, 9, tzinfo=timezone.utc)
fri_gold = _crung("KXGOLDD", "4006", fri.replace(hour=21))
fri_wti = _crung("KXWTI", "92.49", fri.replace(hour=18, minute=30))
ok(not S.ladder_close_trades(fri_gold) and not PR.start_verified(fri_gold),
   "a Friday 17:00 close for a Monday-to-Thursday series is held back")
ok(S.ladder_close_trades(fri_wti) and PR.start_verified(fri_wti), "WTI's Friday 14:30 close is published")
sat = _crung("KXWTI", "92.49", datetime.datetime(2026, 10, 10, 18, 30, tzinfo=timezone.utc))
ok(not PR.start_verified(sat), "a Saturday close is held back")
thanks = _crung("KXSILVERD", "58.75", datetime.datetime(2026, 11, 26, 22, 0, tzinfo=timezone.utc))
ok(not PR.start_verified(thanks), "a US exchange holiday is held back")
ok(S.ladder_close_trades(rung) and PR.start_verified(rung), "a crypto rung has no such calendar: every day closes")
ok(not S.ladder_close_trades(dict(fri_wti, start="not a time")), "an unreadable close is held back")
eq(S.commod_fav_weekdays("KXWTI"), (0, 1, 2, 3, 4), "WTI trades Monday to Friday")
for series in ("KXBRENTD", "KXGOLDD", "KXSILVERD", "KXCOPPERD", "KXNATGASD"):
    eq(S.commod_fav_weekdays(series), (0, 1, 2, 3), f"{series} trades Monday to Thursday")

# The feed, on the lane's own schedule: the WTI window run publishes WTI, the 17:00 run
# publishes the rest, each pending until its close and settled after it.
cst = {"pairs": {CKEY: {"stage": "production", "by_hand": CMOVE, "ready_at": "2026-10-09T14:00:00+00:00"}}}
at_wti = MON.replace(hour=15, minute=40)
feed_wti = PR.build_feed({"quotes": [wti]}, cst, now=at_wti)
eq([l["kickoff"] for l in feed_wti["leads"].values()], ["2026-10-12T18:30Z"], "the WTI window run publishes the WTI rung")
eq((feed_wti["unlisted_skipped"], feed_wti["unverified_kickoff_skipped"]), (0, 0), "nothing held back")
at_five = MON.replace(hour=18, minute=10)
silver = _crung("KXSILVERD", "58.75", MON.replace(hour=21), price=0.79)
feed_five = PR.build_feed({"quotes": [wti, gold, silver]}, cst, now=at_five)
eq(sorted(l["kickoff"] for l in feed_five["leads"].values()), ["2026-10-12T18:30Z", "2026-10-12T21:00Z", "2026-10-12T21:00Z"],
   "the 17:00 run adds the rest; the WTI rung, past its close but open, stays until it settles")
won = dict(gold, status="won", result="a", pnl=28.21, settled="2026-10-12T21:30:00+00:00")
after = PR.build_feed({"quotes": [won]}, cst, now=MON.replace(hour=23))
eq([l["status"] for l in after["leads"].values()], ["hit"], "and reads hit once the close settles it")
feed_fri = PR.build_feed({"quotes": [fri_gold, fri_wti]}, cst, now=fri.replace(hour=15, minute=40))
eq([l["route"]["market"] for l in feed_fri["leads"].values()], [fri_wti["market_id"]],
   "on a Friday only the WTI rung is published; the 17:00 series do not trade")
eq(feed_fri["unverified_kickoff_skipped"], 1, "and the Friday gold rung is counted as held back")
eq(PR.pair_health(CKEY, [wti, gold], 2, feed_five["pairs"], now=at_five), ("ok", "publishing"), "the light is green")
eq(feed_five["pairs"][CKEY]["sandbox_n"], 0, "the feed's pairs map carries the since-move record (nothing settled yet)")

# One rung per commodity per close, whatever the ledger holds.
twin = _crung("KXGOLDD", "4001", MON.replace(hour=21), price=0.74, logged=MON.replace(hour=18, minute=30))
feed_twin = PR.build_feed({"quotes": [gold, twin]}, cst, now=at_five)
eq([l["route"]["market"] for l in feed_twin["leads"].values()], [gold["market_id"]],
   "two gold rungs on one close publish as one lead, the rung logged first")
feed_pair = PR.build_feed({"quotes": [gold, silver]}, cst, now=at_five)
eq(len(feed_pair["leads"]), 2, "two commodities on one close are two leads")
ok(S.SOURCES["commod_fav_band"].get("one_per_coin_close") is True
   and (S.COMMOD_FAV_MAX_SPREAD, S.COMMOD_FAV_MIN_ASK_SIZE, S.COMMOD_FAV_MIN_H, S.COMMOD_FAV_MAX_H) == (0.03, 25, 2.0, 3.5),
   "the Sandbox rule's own gates are unchanged: one per commodity per close, 3c, 25 contracts, 2-3.5h")

# The pages: the commodities rule row badges like the six.
import commodities_build
crow = _row(CKEY, "Early · 0 bets", a=dict(n=1, won=1, expected=0.8, roi_fee=0.24, n_bets=3, unit="market-day"))
chtml = commodities_build.rule_html([crow], {"quotes": []})
ok('<span class="sig y">PRODUCTION</span> <span class="sig w early">Early · 0 bets</span>' in chtml,
   "the commodities rule row shows PRODUCTION and Early · 0 bets")
cpage = PR.page({"quotes": [dict(gold, status="won", result="a", pnl=28.21, settled="2026-10-12T21:30:00+00:00")]},
                {"pairs": {CKEY: dict(_cp)}}, {"leads": {}, "pairs": {}}, "", now=MON.replace(hour=23))
ok("Commodities favourite band" in cpage and 'sig w early">Early · 1 bet</span>' in cpage,
   "the Production pairs table names the pair with its Early count")

print(f"\n{len(FAILS)} FAILED" if FAILS else "\nall passed")
sys.exit(1 if FAILS else 0)
