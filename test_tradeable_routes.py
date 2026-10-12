#!/usr/bin/env python3
"""Nothing in Production is observation only (2026-10-12).

Every Production lead names a market a follower can buy, in the exchange's own terms:
  * a Kalshi lead's route is the exact market ticker, its event, Kalshi's own wording of
    that market's Yes, the side (Yes, or No for an under or a corners fade) and that
    side's price at log -- so "FC Cologne" never has to be matched against "FC Köln";
  * a Kalshi tennis basket is a combo lead: the collection read from Kalshi, every leg's
    market and event ticker, the player, the Yes side, the ask at log, the basket id and
    the modelled price (legs' product times the measured markup);
  * an open basket's start is verified run by run as Tennis Explorer lists its legs,
    because a basket logged a day ahead was never re-checked and never published;
  * a pair that cannot be followed says so: red on the Production page and an item on
    the Control Center's attention list.
No network: every Kalshi read is a fake getter or a lookup dict.
"""
import copy
import datetime
import sys
from datetime import timedelta, timezone

import control_center as CC
import production as PR
import sandbox_sources as S
import sandbox_track as T

FAILS = []
NOW = datetime.datetime(2026, 10, 12, 18, 0, tzinfo=timezone.utc)
BUILT = NOW.isoformat()
KO = (NOW + timedelta(hours=6)).isoformat()


def ok(cond, why):
    print(f"  {'ok  ' if cond else 'FAIL'} {why}")
    if not cond:
        FAILS.append(why)


def eq(got, want, why):
    ok(got == want, why if got == want else f"{why} — got {got!r}, want {want!r}")


# ---------------------------------------------------------------------------
print("the readers keep Kalshi's own names")
# ---------------------------------------------------------------------------
m = {"ticker": "KXMLSTOTAL-26OCT14RSLSJ-4", "event_ticker": "KXMLSTOTAL-26OCT14RSLSJ",
     "yes_sub_title": "Over 3.5 goals scored", "yes_ask_dollars": "0.44", "yes_bid_dollars": "0.42",
     "no_ask_dollars": "0.57", "no_bid_dollars": "0.55"}
ko = NOW + timedelta(days=2)
row = S._yes_no_row(m, "soccer_u35", "Real Salt Lake v San Jose Earthquakes: over 3.5 goals", ko,
                    {"home": "Real Salt Lake", "away": "San Jose Earthquakes"}, "MLS", "KXMLSTOTAL")
eq((row["kalshi_title"], row["event"]), ("Over 3.5 goals scored", "KXMLSTOTAL-26OCT14RSLSJ"),
   "a yes/no row carries Kalshi's wording of the Yes and its event ticker")
eq((row["espn_home"], row["side_a"]), ("Real Salt Lake", "Yes"), "the ESPN names and sides the rules read are unchanged")

tennis_row = dict(market_id="KXATPMATCH-26OCT13SINMED", side_a="Jannik Sinner", side_b="Daniil Medvedev",
                  start=KO, venue="kalshi", start_source="tennisexplorer",
                  tickers={"a": "KXATPMATCH-26OCT13SINMED-SIN", "b": "KXATPMATCH-26OCT13SINMED-MED"})
leg = S._combo_leg(tennis_row, "b", 0.7812)
eq((leg["market_id"], leg["market"], leg["name"], leg["ask"], leg["start_source"]),
   ("KXATPMATCH-26OCT13SINMED", "KXATPMATCH-26OCT13SINMED-MED", "Daniil Medvedev", 0.7812, "tennisexplorer"),
   "a basket leg keeps its event (settlement reads it), the player's own market, the ask it was cut at and its start source")


def _leg_row(mid, code, name, price, start, verified=True):
    return dict(market_id=mid, sport="tennis", side_a=name, side_b="Other", price_a=price,
                price_b=round(1 - price + 0.02, 2), tradeable={"a": True, "b": True}, start=start,
                date=start[:10], venue="kalshi", price_draw=None, untraded=False,
                start_source="tennisexplorer" if verified else None,
                tickers={"a": f"{mid}-{code}", "b": f"{mid}-OTH"})


uni = {"tennis": [_leg_row("KXATPMATCH-26OCT13AAA", "AAA", "Alpha", 0.78, "2026-10-13T08:00:00+00:00"),
                  _leg_row("KXATPMATCH-26OCT13BBB", "BBB", "Beta", 0.80, "2026-10-13T10:00:00+00:00")]}
orig_kept = S.tennis_fav_kept
S.tennis_fav_kept = lambda mid: True
try:
    basket = [r for r in S.tennis_combo_rows(uni) if r["market_id"].startswith("combo2")][0]
finally:
    S.tennis_fav_kept = orig_kept
eq([(l["market"], l["ask"]) for l in basket["legs"]],
   [("KXATPMATCH-26OCT13AAA-AAA", 0.78), ("KXATPMATCH-26OCT13BBB-BBB", 0.8)], "each leg of a built basket keeps its market and ask")
eq(basket["price_a"], round(0.78 * 0.80 * (1 + S.COMBO_MARKUP[2]), 4),
   "the basket's price is the legs' product times the measured 2-leg markup (ask1 x ask2 x 1.0084)")

# ---------------------------------------------------------------------------
print("\nKalshi's collections, read and chosen")
# ---------------------------------------------------------------------------
pages = [
    {"multivariate_contracts": [
        {"collection_ticker": "KXMVECROSSCATEGORY-R", "series_ticker": "KXMVECROSSCATEGORY", "exchange_index": 1,
         "associated_event_tickers": ["KXATPMATCH-26OCT13AAA", "KXATPMATCH-26OCT13BBB"]}],
     "cursor": "next"},
    {"multivariate_contracts": [
        {"collection_ticker": "KXMVESPORTSMULTIGAMEEXTENDED-R", "series_ticker": "KXMVESPORTSMULTIGAMEEXTENDED",
         "exchange_index": 1, "associated_events": [{"ticker": "KXATPMATCH-26OCT13AAA"},
                                                    {"ticker": "KXATPMATCH-26OCT13BBB"}]}],
     "cursor": ""},
]
calls = []


def _pages(url):
    calls.append(url)
    return pages[len(calls) - 1]


cols = S.kalshi_combo_collections(getter=_pages)
eq([c["ticker"] for c in cols], ["KXMVECROSSCATEGORY-R", "KXMVESPORTSMULTIGAMEEXTENDED-R"], "every page of open collections is read")
ok("cursor=next" in calls[1], "following Kalshi's cursor")
eq(S.combo_collection(["KXATPMATCH-26OCT13AAA", "KXATPMATCH-26OCT13BBB"], cols)["ticker"],
   "KXMVESPORTSMULTIGAMEEXTENDED-R", "the sports multi-game collection wins when it lists every leg")
eq(S.combo_collection(["KXATPMATCH-26OCT13AAA", "KXATPMATCH-26OCT13ZZZ"], cols), None,
   "no collection lists a leg it does not carry")
eq(S.combo_collection(["KXATPMATCH-26OCT13AAA"], [c for c in cols if "CROSS" in c["ticker"]])["ticker"],
   "KXMVECROSSCATEGORY-R", "another collection that lists the legs is the fallback")


def _boom(url):
    raise RuntimeError("down")


eq(S.kalshi_combo_collections(getter=_boom), [], "an outage is an empty list, not a crash")
eq(S.kalshi_event_markets("KXBUNDESLIGAGAME-26OCT11KOEBMG", getter=lambda url: {"markets": [
    {"ticker": "KXBUNDESLIGAGAME-26OCT11KOEBMG-KOE", "yes_sub_title": "FC Köln"}]}),
   [{"ticker": "KXBUNDESLIGAGAME-26OCT11KOEBMG-KOE", "yes_sub_title": "FC Köln"}], "an event's markets are read by ticker")
eq(S.kalshi_event_markets("KXX-1", getter=_boom), [], "and fail soft")

# ---------------------------------------------------------------------------
print("\nan open basket's start is verified as its legs are")
# ---------------------------------------------------------------------------


def _open_basket(**over):
    legs = [dict(market_id="KXATPMATCH-26OCT13AAA", pick="a", venue="kalshi", name="Alpha",
                 start="2026-10-13T06:00:00+00:00"),
            dict(market_id="KXATPMATCH-26OCT13BBB", pick="a", venue="kalshi", name="Beta",
                 start="2026-10-13T06:00:00+00:00")]
    q = dict(id="tennis_combo2:combo2:2026-10-12:abc", source="tennis_combo2", sport="tennis_combo",
             market_id="combo2:2026-10-12:abc", label="2-leg tennis combo: Alpha + Beta",
             side_a="All 2 win", side_b="Any one loses", venue="combo", pick="a", price=0.629,
             bet=True, status="open", start="2026-10-13T06:00:00+00:00", start_source=None,
             logged="2026-10-12T09:00:00+00:00", legs=legs)
    q.update(over)
    return q


d = {"quotes": [_open_basket()]}
before = copy.deepcopy(d["quotes"][0])
eq(T.verify_open_baskets(d, {"tennis": [uni["tennis"][0], dict(uni["tennis"][1], start_source=None)]}), 0,
   "one leg still on Kalshi's estimate: the basket stays unverified")
q = d["quotes"][0]
eq((q["start_source"], q["legs"][0]["start_source"], q["legs"][0]["start"]),
   (None, "tennisexplorer", "2026-10-13T08:00:00+00:00"), "but the confirmed leg keeps its confirmed start")
eq(T.verify_open_baskets(d, uni), 1, "once both legs are confirmed the basket is verified")
eq((q["start"], q["start_source"], q["estimated_start"]),
   ("2026-10-13T08:00:00+00:00", "tennisexplorer", "2026-10-13T06:00:00+00:00"),
   "its start is the EARLIER leg's confirmed start; Kalshi's estimate is kept as estimated_start")
eq([l["market"] for l in q["legs"]], ["KXATPMATCH-26OCT13AAA-AAA", "KXATPMATCH-26OCT13BBB-BBB"],
   "and each leg's own market is filled in from the row")
eq({k: q[k] for k in ("id", "price", "pick", "market_id", "status")},
   {k: before[k] for k in ("id", "price", "pick", "market_id", "status")}, "nothing else about the bet moves")
eq(T.verify_open_baskets(d, uni), 0, "a verified basket is left alone on the next run")
settled = {"quotes": [_open_basket(status="won")]}
eq(T.verify_open_baskets(settled, uni), 0, "a settled basket is never re-timed")
pmb = {"quotes": [_open_basket(legs=[dict(l, venue="polymarket_us") for l in _open_basket()["legs"]])]}
eq(T.verify_open_baskets(pmb, uni), 0, "a Polymarket basket is not touched: only Kalshi baskets are published")
ok(PR.start_verified(q) and T.placeable(q), "the verified Kalshi basket reaches the feed")

# ---------------------------------------------------------------------------
print("\nthe combo lead")
# ---------------------------------------------------------------------------
kx = {"collections": cols}
lead = PR.lead_from_quote(q, "tennis_combo2|tennis_combo", BUILT, kalshi=kx)
r = lead["route"]
eq((lead["bet"]["kind"], r["venue"], r["instrument"], r["how"]), ("combo", "kalshi", "combo", "request_quote"),
   "kind combo, on Kalshi, asked for by RFQ")
eq(r["mve_collection_ticker"], "KXMVESPORTSMULTIGAMEEXTENDED-R", "the collection is the one read from Kalshi")
eq((r["basket_id"], lead["basket_id"]), ("combo2:2026-10-12:abc", "combo2:2026-10-12:abc"), "the basket id rides on the route and the lead")
eq((r["modelled_price"], r["max_price"], lead["price_at_log"]), (0.629, 0.629, 0.629),
   "the modelled price is the ceiling and the price at log")
eq(lead["kickoff"], "2026-10-13T08:00Z", "kickoff is the earlier leg's verified start")
eq(r["legs"], [
    {"market": "KXATPMATCH-26OCT13AAA-AAA", "event": "KXATPMATCH-26OCT13AAA", "player": "Alpha",
     "outcome_side": "yes", "ask_at_log": None, "starts": "2026-10-13T08:00"},
    {"market": "KXATPMATCH-26OCT13BBB-BBB", "event": "KXATPMATCH-26OCT13BBB", "player": "Beta",
     "outcome_side": "yes", "ask_at_log": None, "starts": "2026-10-13T10:00"}],
   "every leg: market, event, player, Yes, the ask at log (none on a basket logged before legs kept it)")
ok(PR.route_ok(r), "a route_ok basket route")
legs_with_ask = copy.deepcopy(q)
legs_with_ask["legs"][0]["ask"], legs_with_ask["legs"][1]["ask"] = 0.78, 0.8
eq([l["ask_at_log"] for l in PR.lead_from_quote(legs_with_ask, "tennis_combo2|tennis_combo", BUILT, kalshi=kx)["route"]["legs"]],
   [0.78, 0.8], "a leg logged with its ask carries it")
bare = PR.lead_from_quote(q, "tennis_combo2|tennis_combo", BUILT)
ok("route" not in bare and bare["unroutable"] == "no open Kalshi collection lists every leg",
   "without a collection the lead goes out unrouted and says why")
no_mkt = copy.deepcopy(q)
for l in no_mkt["legs"]:
    l.pop("market")
nm = PR.lead_from_quote(no_mkt, "tennis_combo2|tennis_combo", BUILT, kalshi=kx)
ok(nm.get("unroutable", "").startswith("no Kalshi market named for"), "a leg with no market named is unroutable too")
looked = PR.lead_from_quote(no_mkt, "tennis_combo2|tennis_combo", BUILT, kalshi=dict(kx, markets={
    "KXATPMATCH-26OCT13AAA": [{"ticker": "KXATPMATCH-26OCT13AAA-AAA", "yes_sub_title": "Alpha"},
                              {"ticker": "KXATPMATCH-26OCT13AAA-ZZZ", "yes_sub_title": "Zed"}],
    "KXATPMATCH-26OCT13BBB": [{"ticker": "KXATPMATCH-26OCT13BBB-BBB", "yes_sub_title": "Beta"},
                              {"ticker": "KXATPMATCH-26OCT13BBB-YYY", "yes_sub_title": "Yan"}]}))
eq([l["market"] for l in looked["route"]["legs"]], ["KXATPMATCH-26OCT13AAA-AAA", "KXATPMATCH-26OCT13BBB-BBB"],
   "a leg logged before markets were kept is named from the live event, side a being the home code")

# ---------------------------------------------------------------------------
print("\nsingle Kalshi contracts")
# ---------------------------------------------------------------------------


def _bin(source, sport, mid, pick, price, **over):
    q = dict(id=f"{source}:{mid}", source=source, sport=sport, market_id=mid, venue="kalshi_binary",
             pick=pick, price=price, price_a=0.44, price_b=0.57, side_a="Yes", side_b="No", bet=True,
             status="open", start=KO, logged=BUILT, start_source="espn", league="MLS",
             espn_home="Real Salt Lake", espn_away="San Jose Earthquakes", label="x")
    q.update(over)
    return q


under = _bin("u35_low_scoring", "soccer_u35", "KXMLSTOTAL-26OCT14RSLSJ-4", "b", 0.57,
             kalshi_title="Over 3.5 goals scored", event="KXMLSTOTAL-26OCT14RSLSJ")
ul = PR.lead_from_quote(under, "u35_low_scoring|soccer_u35", BUILT)
eq(ul["route"], {"venue": "kalshi", "market": "KXMLSTOTAL-26OCT14RSLSJ-4", "event": "KXMLSTOTAL-26OCT14RSLSJ",
                 "outcome": "Over 3.5 goals scored", "outcome_side": "no", "price_at_log": 0.57,
                 "claim": "Under 3.5 goals"},
   "an under is the NO of the exact over contract, named in Kalshi's words, at the NO price at log")
old_under = dict(under)
old_under.pop("kalshi_title")
ol = PR.lead_from_quote(old_under, "u35_low_scoring|soccer_u35", BUILT, kalshi={"markets": {
    "KXMLSTOTAL-26OCT14RSLSJ": [{"ticker": "KXMLSTOTAL-26OCT14RSLSJ-4", "yes_sub_title": "Over 3.5 goals scored"}]}})
eq(ol["route"]["outcome"], "Over 3.5 goals scored", "a quote logged before titles were kept is named from the live event")
ok("outcome" not in PR.lead_from_quote(old_under, "u35_low_scoring|soccer_u35", BUILT)["route"],
   "and with no lookup the route leaves the wording out rather than guess it: the ticker is exact")
team2 = _bin("team2_ranked", "soccer_team2", "KXSERIEATEAMTOTAL-26OCT11LECBFC-BFC2", "a", 0.47,
             team="Bologna", kalshi_title="Bologna over 1.5 goals", league="Serie A")
t2 = PR.lead_from_quote(team2, "team2_ranked|soccer_team2", BUILT)
eq((t2["headline"], t2["route"]["market"], t2["route"]["outcome"], t2["route"]["outcome_side"]),
   ("Bologna to score 2+", "KXSERIEATEAMTOTAL-26OCT11LECBFC-BFC2", "Bologna over 1.5 goals", "yes"),
   "a Yes market (team 2+) is routed to its exact ticker too, so no club name is matched")

game = dict(id="ere_draw:KXBUNDESLIGAGAME-26OCT11KOEBMG", source="ere_draw", sport="soccer", venue="kalshi",
            market_id="KXBUNDESLIGAGAME-26OCT11KOEBMG", side_a="FC Köln", side_b="M´gladbach",
            pick="a", price=0.41, price_a=0.41, price_b=0.33, price_draw=0.27, bet=True, status="open",
            start=KO, logged=BUILT, start_source="espn", label="FC Köln vs M´gladbach",
            tickers={"a": "KXBUNDESLIGAGAME-26OCT11KOEBMG-KOE", "b": "KXBUNDESLIGAGAME-26OCT11KOEBMG-BMG",
                     "draw": "KXBUNDESLIGAGAME-26OCT11KOEBMG-TIE"},
            titles={"a": "FC Köln", "b": "M´gladbach", "draw": "Tie"})
gl = PR.lead_from_quote(game, "x|soccer", BUILT)
eq((gl["route"]["market"], gl["route"]["outcome"], gl["route"]["outcome_side"]),
   ("KXBUNDESLIGAGAME-26OCT11KOEBMG-KOE", "FC Köln", "yes"),
   "Cologne v Gladbach names Kalshi's own contract and name, not 'FC Cologne'")
dl = PR.lead_from_quote(dict(game, pick="draw", price=0.27), "ere_draw|soccer", BUILT)
eq((dl["headline"], dl["route"]["market"], dl["route"]["outcome"], dl["route"]["price_at_log"]),
   ("Draw", "KXBUNDESLIGAGAME-26OCT11KOEBMG-TIE", "Tie", 0.27), "a draw is the Tie contract")
old_game = {k: v for k, v in game.items() if k not in ("tickers", "titles")}
live = {"markets": {"KXBUNDESLIGAGAME-26OCT11KOEBMG": [
    {"ticker": "KXBUNDESLIGAGAME-26OCT11KOEBMG-KOE", "yes_sub_title": "FC Köln"},
    {"ticker": "KXBUNDESLIGAGAME-26OCT11KOEBMG-TIE", "yes_sub_title": "Tie"},
    {"ticker": "KXBUNDESLIGAGAME-26OCT11KOEBMG-BMG", "yes_sub_title": "M´gladbach"}]}}
for pick, want in (("a", "KOE"), ("b", "BMG"), ("draw", "TIE")):
    got = PR.lead_from_quote(dict(old_game, pick=pick), "x|soccer", BUILT, kalshi=live)["route"]["market"]
    eq(got, f"KXBUNDESLIGAGAME-26OCT11KOEBMG-{want}", f"an older quote's side {pick} maps to -{want} through kalshi_sides")
fb = PR.lead_from_quote(old_game, "x|soccer", BUILT)["route"]
eq((fb["market"], fb["outcome"]), ("KXBUNDESLIGAGAME-26OCT11KOEBMG", "FC Köln"),
   "with no lookup, the event and Kalshi's own side name: the follower matches it exactly")

# ---------------------------------------------------------------------------
print("\nthe feed counts routes per pair, and a pair that cannot be followed says so")
# ---------------------------------------------------------------------------
eq(PR.route_ok({"venue": "kalshi", "market": "X"}), True, "a single contract needs a venue and a market")
eq(PR.route_ok({"venue": "kalshi"}), False, "a route without a market is not")
eq(PR.route_ok(None), False, "nor is no route")
eq(PR.route_ok({"venue": "kalshi", "instrument": "combo", "mve_collection_ticker": "C",
                "legs": [{"market": "A"}, {"market": None}]}), False, "a basket needs every leg's market")
st = {"pairs": {"tennis_combo2|tennis_combo": {"stage": "production", "by_hand": "2026-10-08",
                                               "ready_at": "2026-10-08T17:50:08+00:00",
                                               "promoted_at": "2026-10-08T17:50:08+00:00"},
                "u35_low_scoring|soccer_u35": {"stage": "production", "by_hand": "2026-10-11",
                                               "ready_at": "2026-10-11T00:00:00+00:00",
                                               "promoted_at": "2026-10-11T00:00:00+00:00"}}}
unverified = _open_basket(start=(NOW + timedelta(hours=10)).isoformat())
feed = PR.build_feed({"quotes": [unverified, under]}, st, now=NOW, kalshi=kx)
rc = feed["pairs"]["tennis_combo2|tennis_combo"]["routing"]
eq((rc["leads"], rc["unverified"]), (0, 1), "the unverified basket is held back and counted")
eq(rc["problem"], "1 bet in the window, none published: 1 held for an unverified start",
   "so the combo pair cannot be followed, in those words")
ru = feed["pairs"]["u35_low_scoring|soccer_u35"]["routing"]
eq((ru["leads"], ru["routed"], ru["problem"]), (1, 1, None), "the under pair's lead is routed: nothing to say")
verified = copy.deepcopy(q)
feed2 = PR.build_feed({"quotes": [verified]}, st, now=NOW, kalshi=kx)
eq(feed2["pairs"]["tennis_combo2|tennis_combo"]["routing"]["routed"], 1, "a verified basket is published, routed")
feed3 = PR.build_feed({"quotes": [verified]}, st, now=NOW)
r3 = feed3["pairs"]["tennis_combo2|tennis_combo"]["routing"]
eq(r3["problem"], "1 of 1 lead carry no tradeable route (no open Kalshi collection lists every leg)",
   "a lead published without a route is named with the reason")
state, why = PR.pair_health("tennis_combo2|tennis_combo", [verified], 1, feed3["pairs"], now=NOW,
                            routing=r3)
eq((state, why), ("bad", "not tradeable: " + r3["problem"]), "the Production page's light goes red with that reason")
items = CC._attention({"quotes": []}, st, st["pairs"], NOW, None, None, blob=feed)
route_items = [i for i in items if i["kind"] == "route"]
eq([(i["area"], i["href"]) for i in route_items], [("tennis", "./production.html")],
   "the Control Center lists it under Tennis, linking the Production page")
ok(route_items and "cannot be followed: 1 bet in the window, none published" in route_items[0]["text"],
   "in the feed's own words")

# ---------------------------------------------------------------------------
print("\nevery Production pair on today's ledger can carry a route")
# ---------------------------------------------------------------------------
ledger = T.load()
stages = T.load_stages()
for key in sorted(PR.production_pairs(stages)):
    source, sport = key.split("|", 1)
    bets = [x for x in T.bet_rows(ledger) if x.get("source") == source and x.get("sport") == sport
            and x.get("bet") and T.placeable(x) and x.get("venue") != "combo"]
    if not bets:
        continue
    try:
        lead = PR.lead_from_quote(bets[-1], key, BUILT)
    except (KeyError, ValueError, TypeError):
        continue
    ok(PR.route_ok(lead.get("route")), f"{key}: its latest publishable bet names {lead.get('route', {}).get('market')}")

print()
if FAILS:
    print(f"{len(FAILS)} FAILED")
    sys.exit(1)
print("all passed")
