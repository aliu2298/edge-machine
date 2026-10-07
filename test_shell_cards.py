#!/usr/bin/env python3
"""SofaScore shell slice 3: Rules-applied cards, and the slice-2 follow-ups.

Fails while a selected contest has no card payload, a multi-bet row shows
only the first price, an unknown status reads Void, or an ungraded bet past
the await window still says Open. Passes once each bet is a mini card
(Production before Sandbox), prices list in cents, and the follow-ups hold.
No network. Browser checks need REQUIRE_BROWSER=1.
"""
import datetime
import html as html_lib
import json
import os
import re
import shutil
import sys
import tempfile
import threading
from datetime import timedelta, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

import sandbox_build
import shell_build

FAILS = []
ROOT = os.path.dirname(os.path.abspath(__file__))
NOW = datetime.datetime(2026, 10, 5, 18, 0, tzinfo=timezone.utc)


def ok(cond, why):
    print(f"  {'ok  ' if cond else 'FAIL'} {why}")
    if not cond:
        FAILS.append(why)


def eq(got, want, why):
    ok(got == want, why if got == want else f"{why} — got {got!r}, want {want!r}")


def _lead(lid, home, away, kickoff, status, pair, sport, price, **extra):
    row = {
        "id": lid,
        "home": home,
        "away": away,
        "match": f"{home} v {away}",
        "headline": extra.pop("headline", f"{home} to win"),
        "kickoff": kickoff,
        "status": status,
        "pair": pair,
        "sport": sport,
        "lane": extra.pop("lane", "production"),
        "price_at_log": price,
        "league": extra.pop("league", "League"),
        "source": extra.pop("source", pair.split("|", 1)[0]),
        "sandbox_quote": lid,
    }
    row.update(extra)
    return row


def _blob(leads):
    return {"leads": {lead["id"]: lead for lead in leads}, "pairs": {}}


def _rows(page):
    return re.findall(r'<button\b[^>]*class="running-row"[^>]*>.*?</button>', page, re.S)


def _attr(tag, name):
    match = re.search(rf'\b{name}="([^"]*)"', tag)
    return html_lib.unescape(match.group(1)) if match else None


def _contests(leads, now=NOW, d=None, st=None):
    blob = _blob(leads)
    empty = {"quotes": []}
    stages = {"pairs": {}}
    lanes = shell_build.collect_lanes(d or empty, st or stages, blob, now)
    return shell_build.contests_from_lanes(lanes, now, d=d or empty, st=st or stages)


def _cards(row):
    raw = _attr(row, "data-cards")
    if not raw:
        return None
    return json.loads(raw)


print("unknown status is not Void")
eq(shell_build._status_label("void"), "Void", "a real void is still Void")
eq(shell_build._status_label("held"), "held", "an unknown status stays the raw status")
eq(shell_build._status_label(None), "Unknown", "a missing status is Unknown")
ok(shell_build._status_label("held") != "Void", "an unknown status is never Void")
ok(shell_build._status_label("bogus") != "Void", "another unknown status is never Void")
held = _contests([
    _lead("held", "Held", "Match", "2026-10-04T15:00:00Z", "held",
          "oddspedia|cricket", "cricket", 0.30),
])
eq(held[0]["status"], "held", "the row shows the raw status, not Void")
eq(held[0]["cards"][0]["status"], "held", "the card shows the raw status, not Void")
held_page = shell_build.page(NOW, d={"quotes": []}, st={"pairs": {}}, blob=_blob([
    _lead("held", "Held", "Match", "2026-10-04T15:00:00Z", "held",
          "oddspedia|cricket", "cricket", 0.30),
]))
held_row = _rows(held_page)[0]
ok(">held</span>" in held_row and ">Void</span>" not in held_row,
   "rendered unknown status is the escaped raw word")


print("\nungraded bets past six hours")
def _one(kickoff, now=NOW):
    return _contests([
        _lead("x", "Home", "Away", kickoff, "pending", "oddspedia|cricket", "cricket", 0.50),
    ], now=now)[0]


at_kick = _one("2026-10-05T18:00:00Z")
eq(at_kick["bucket"], "live", "kickoff equal to now is Live")
eq(at_kick["status"], "Open", "kickoff equal to now is not awaiting")
ok(not at_kick["awaiting"], "the equal-now contest is not awaiting")
just_before = _one("2026-10-05T18:00:01Z")
eq(just_before["bucket"], "upcoming", "the instant before kickoff is Upcoming")
eq(just_before["status"], "Open", "an upcoming bet stays Open")
just_after = _one("2026-10-05T17:59:59Z")
eq(just_after["bucket"], "live", "one second after kickoff is Live")
eq(just_after["status"], "Open", "one second after kickoff is not yet awaiting")
at_six = _one("2026-10-05T12:00:00Z")
eq(at_six["bucket"], "live", "exactly six hours after kickoff stays Live")
eq(at_six["status"], "Open", "the six-hour boundary is still Open")
ok(not at_six["awaiting"], "exactly six hours is not past the window")
past_six = _one("2026-10-05T11:59:59Z")
eq(past_six["bucket"], "live", "past six hours stays in the Live bucket")
eq(past_six["status"], "Awaiting result", "past six hours and ungraded says Awaiting result")
eq(past_six["spoken"], "awaiting result", "awaiting is spoken as awaiting result")
ok(past_six["awaiting"], "the contest is marked awaiting")
eq(past_six["cards"][0]["status"], "Awaiting result",
   "the card for an ungraded bet past six hours says Awaiting result")
eq(past_six["cards"][0]["spoken"], "awaiting result",
   "that card is spoken as awaiting result")
mixed = _contests([
    _lead("graded", "Half", "Graded", "2026-10-05T11:00:00Z", "miss",
          "a|soccer", "soccer", 0.40),
    _lead("stuck", "Half", "Graded", "2026-10-05T11:00:00Z", "pending",
          "b|soccer", "soccer", 0.70),
])
eq(mixed[0]["bucket"], "live", "a half-graded contest past six hours stays Live")
eq(mixed[0]["status"], "1L 1 awaiting",
   "the open bet past six hours reads as awaiting beside the loss")
eq(mixed[0]["spoken"], "1 lost, 1 awaiting result",
   "the mix is spoken as 1 lost, 1 awaiting result")
eq([card["status"] for card in mixed[0]["cards"]], ["L", "Awaiting result"],
   "only the stuck bet's card says Awaiting result")
inside = _contests([
    _lead("g2", "Half", "Fresh", "2026-10-05T14:00:00Z", "miss",
          "a|soccer", "soccer", 0.40),
    _lead("o2", "Half", "Fresh", "2026-10-05T14:00:00Z", "pending",
          "b|soccer", "soccer", 0.70),
])
eq(inside[0]["status"], "1L 1 open",
   "an open bet inside six hours still reads Open beside the loss")
eq(inside[0]["cards"][1]["status"], "Open",
   "that card still says Open")
past_page = shell_build.page(NOW, d={"quotes": []}, st={"pairs": {}}, blob=_blob([
    _lead("late", "Late", "Grade", "2026-10-05T11:59:59Z", "pending",
          "oddspedia|cricket", "cricket", 0.50),
    _lead("on", "On", "Time", "2026-10-05T12:00:00Z", "pending",
          "oddspedia|cricket", "cricket", 0.51),
]))


def _named_row(page, name, why):
    found = [row for row in _rows(page) if _attr(row, "data-name") == name]
    eq(len(found), 1, why)
    return found[0] if len(found) == 1 else ""


late_row = _named_row(past_page, "Late v Grade", "the awaiting contest is its own row")
on_row = _named_row(past_page, "On v Time", "the six-hour contest is its own row")
ok('data-awaiting="true"' in late_row and ">Awaiting result</span>" in late_row,
   "the stuck row renders Awaiting result")
eq(_attr(late_row, "data-filter"), "live", "Awaiting result stays in Live")
ok('data-awaiting="true"' not in on_row and ">Open</span>" in on_row,
   "the six-hour boundary row stays Open")
saved_await = shell_build.SHELL_AWAIT_HOURS
try:
    shell_build.SHELL_AWAIT_HOURS = 1
    moved = _one("2026-10-05T16:00:00Z")
    eq(moved["status"], "Awaiting result",
       "SHELL_AWAIT_HOURS is read on each call")
finally:
    shell_build.SHELL_AWAIT_HOURS = saved_await
eq(_one("2026-10-05T16:00:00Z")["status"], "Open",
   "restoring SHELL_AWAIT_HOURS restores the six-hour window")


print("\nreversed sides and the Chicago day")
reversed_sides = _contests([
    _lead("home", "Chicago Fire", "Chicago Stars", "2026-10-05T18:00:00Z", "hit",
          "a|soccer", "soccer", 0.40),
    _lead("away", "chicago stars", "CHICAGO FIRE", "2026-10-05T20:00:00Z", "miss",
          "b|soccer", "soccer", 0.55),
])
eq(len(reversed_sides), 1,
   "reversed home/away with a different case on one Chicago day is one contest")
eq(len(reversed_sides[0]["cards"]) if reversed_sides else 0, 2,
   "that contest keeps both bets")
same_chicago = _contests([
    _lead("utc5", "Day", "Line", "2026-10-05T18:00:00Z", "hit",
          "a|soccer", "soccer", 0.41),
    _lead("utc6", "Day", "Line", "2026-10-06T03:30:00Z", "miss",
          "b|soccer", "soccer", 0.42),
])
eq(len(same_chicago), 1,
   "two UTC dates on the same Chicago day are one contest")
split_chicago = _contests([
    _lead("before", "Night", "Edge", "2026-10-05T04:30:00Z", "hit",
          "a|soccer", "soccer", 0.43),
    _lead("after", "Night", "Edge", "2026-10-05T06:00:00Z", "miss",
          "b|soccer", "soccer", 0.44),
])
eq(len(split_chicago), 2,
   "one UTC date that crosses midnight in Chicago is two contests")


print("\na win beside an awaiting bet")
won_open = _contests([
    _lead("won", "Win", "Wait", "2026-10-05T11:00:00Z", "hit",
          "a|soccer", "soccer", 0.40),
    _lead("stuck", "Win", "Wait", "2026-10-05T11:00:00Z", "pending",
          "b|soccer", "soccer", 0.70),
])
eq(len(won_open), 1, "a win and an open bet are one contest")
eq(won_open[0]["bucket"] if won_open else None, "live",
   "a win plus an open bet past six hours stays Live")
eq(won_open[0]["status"] if won_open else None, "1W 1 awaiting",
   "the row shows 1W 1 awaiting")
ok(won_open and won_open[0]["awaiting"],
   "the mixed row keeps the awaiting flag for the warn bar")
eq([card["status"] for card in (won_open[0]["cards"] if won_open else [])],
   ["W", "Awaiting result"],
   "the cards are a W and an Awaiting result")
won_page = shell_build.page(NOW, d={"quotes": []}, st={"pairs": {}}, blob=_blob([
    _lead("won", "Win", "Wait", "2026-10-05T11:00:00Z", "hit",
          "a|soccer", "soccer", 0.40),
    _lead("stuck", "Win", "Wait", "2026-10-05T11:00:00Z", "pending",
          "b|soccer", "soccer", 0.70),
]))
won_row = _named_row(won_page, "Win v Wait", "the mixed awaiting contest is its own row")
ok('data-awaiting="true"' in won_row, "the mixed row renders the warn-bar flag")
ok(">1W 1 awaiting</span>" in won_row, "the mixed row renders 1W 1 awaiting")


print("\nunknown statuses follow the kickoff")
future_unknown = _contests([
    _lead("later", "Later", "Kick", "2026-10-08T15:00:00Z", "postponed",
          "oddspedia|cricket", "cricket", 0.30),
])
eq(len(future_unknown), 1, "a future unknown status stays on the list")
eq(future_unknown[0]["bucket"], "upcoming", "a future unknown status is Upcoming")
eq(future_unknown[0]["status"], "postponed", "it keeps its own status")
eq(future_unknown[0]["cards"][0]["status"], "postponed", "its card keeps that status")
past_unknown = _contests([
    _lead("earlier", "Earlier", "Kick", "2026-10-04T15:00:00Z", "postponed",
          "oddspedia|cricket", "cricket", 0.31),
])
eq(past_unknown[0]["bucket"], "settled", "a past unknown status is Settled")
eq(past_unknown[0]["status"], "postponed", "the past row keeps the raw status")
missing_future = _contests([
    _lead("blank", "Blank", "Status", "2026-10-08T15:00:00Z", None,
          "oddspedia|cricket", "cricket", 0.32),
])
eq(missing_future[0]["bucket"], "upcoming", "a missing status with a future kickoff is Upcoming")
eq(missing_future[0]["status"], "Unknown", "that row is labeled Unknown")
unknown_page = shell_build.page(NOW, d={"quotes": []}, st={"pairs": {}}, blob=_blob([
    _lead("later", "Later", "Kick", "2026-10-08T15:00:00Z", "postponed",
          "oddspedia|cricket", "cricket", 0.30),
]))
later_row = _named_row(unknown_page, "Later v Kick", "the future unknown contest is its own row")
eq(_attr(later_row, "data-filter"), "upcoming", "the future unknown row is in Upcoming")
ok(">postponed</span>" in later_row, "the future unknown row shows postponed")


print("\ncents rounding")
rounded = _contests([
    _lead("rnd", "Round", "Price", "2026-10-04T15:00:00Z", "hit",
          "oddspedia|cricket", "cricket", 0.535),
])
eq(rounded[0]["price_text"], "54¢", "0.535 rounds to 54¢ on the row")
eq(rounded[0]["cards"][0]["price"], "54¢", "0.535 rounds to 54¢ on the card")
eq(shell_build._cents(0.535), "54¢", "the cents helper pins 0.535 at 54¢")
rounded_page = shell_build.page(NOW, d={"quotes": []}, st={"pairs": {}}, blob=_blob([
    _lead("rnd", "Round", "Price", "2026-10-04T15:00:00Z", "hit",
          "oddspedia|cricket", "cricket", 0.535),
]))
eq(_attr(_rows(rounded_page)[0], "data-price"), "54¢", "the rendered row pins 54¢")


print("\ncards, prices, and sport pages")
hostile_lane = "<svg/onload=alert(1)>"
hostile_market = '<img src=x onerror=alert(1)>'
mix = [
    _lead("sand", "Mix", "Match", "2026-10-04T15:00:00Z", "hit",
          "aaa|soccer", "soccer", 0.40, lane="sandbox", headline="Draw",
          source="aaa", venue="kalshi"),
    _lead("prod", "Mix", "Match", "2026-10-04T15:00:00Z", "miss",
          "zzz|soccer", "soccer", 0.67, headline=hostile_market,
          source=hostile_lane, edge_at_log=0.042,
          route={"venue": "polymarket_us"}),
]
found = _contests(mix)
eq(len(found), 1, "a production bet and a sandbox bet stay one contest")
eq(len(found[0]["cards"]), len(found[0]["bets"]),
   "one card per bet")
eq([card["pill"] for card in found[0]["cards"]], ["PRODUCTION", "Sandbox"],
   "Production cards come before Sandbox cards")
eq(found[0]["price_text"], "67¢ / 40¢",
   "the row price lists each bet, production price first")
eq(found[0]["page"], "./soccer.html", "a soccer contest links to soccer.html")
prod_card, sand_card = found[0]["cards"]
eq(prod_card["lane"], hostile_lane, "the card keeps the hostile lane name")
eq(prod_card["market"], hostile_market, "the card keeps the hostile market")
eq(prod_card["venue"], "Polymarket US", "the venue badge uses the source label")
eq(prod_card["price"], "67¢", "the card price is cents")
eq(prod_card["edge"], "+4.2%", "a stored edge is shown in the board's percent format")
eq(sand_card["venue"], "Kalshi", "Kalshi uses the board's venue label")
eq(sand_card["market"], "Draw", "the sandbox card keeps its market")
ok("edge" not in sand_card, "a card with no stored edge omits edge")
group, assessed, *_rest = sandbox_build.pair_status(
    {"quotes": []}, {"pairs": {}}, "zzz", "soccer")
want_verdict = sandbox_build.VERDICTS[
    sandbox_build.verdict(assessed) if group is not None else "nobets"][0]
eq(prod_card["verdict"], want_verdict, "the verdict is the sport page's helper")
ok("roi" not in prod_card and "record" not in prod_card,
   "an empty sample omits ROI and record")
plain = _contests([
    _lead("c", "Home", "Away", "2026-10-06T15:00:00Z", "pending",
          "oddspedia|cricket", "cricket", 0.50),
])
eq(plain[0]["page"], "./cricket.html", "a cricket contest links to cricket.html")
ok("edge" not in plain[0]["cards"][0], "a null edge is omitted")
mma = _contests([
    _lead("m", "A", "B", "2026-10-06T15:00:00Z", "pending", "x|mma", "mma", 0.50),
])
eq(mma[0]["page"], "./production.html", "a sport without a page links to production.html")
crypto = _contests([
    _lead("k", "Coin", "Band", "2026-10-06T15:00:00Z", "pending",
          "spot|crypto", "crypto", 0.55),
])
eq(crypto[0]["page"], "./crypto.html", "crypto links to crypto.html")

page = shell_build.page(NOW, d={"quotes": []}, st={"pairs": {}}, blob=_blob(mix))
rows = _rows(page)
eq(len(rows), 1, "the mixed contest is one Running row")
eq(_attr(rows[0], "data-price"), "67¢ / 40¢", "the row attribute lists both prices")
eq(_attr(rows[0], "data-page"), "./soccer.html", "the row carries the sport page")
parsed = _cards(rows[0])
eq([card["pill"] for card in parsed], ["PRODUCTION", "Sandbox"],
   "the embedded payload keeps Production before Sandbox")
eq(parsed[0]["lane"], hostile_lane, "the embedded lane name survives escaping")
eq(parsed[0]["market"], hostile_market, "the embedded market survives escaping")
ok('class="rule-mini"' not in page, "cards are not painted until a row is selected")
ok("Select a contest in Running." in page, "the detail pane starts empty")
ok(hostile_market not in page and "&lt;img src=x onerror=alert(1)&gt;" in page,
   "the hostile market is escaped")
ok(hostile_lane not in page and "&lt;svg/onload=alert(1)&gt;" in page,
   "the hostile lane name is escaped")
ok('href="javascript:' not in page and 'href="data:' not in page,
   "card text does not become a javascript or data link")
ok(re.search(r">\s*History\s*<", page, re.I) is None, "there is no History tab")
ok('href="./production.html"' in page and "Full page" in page,
   "Full page still starts on the Production board")


print("\nlive helpers, not a new formula")
import sandbox_track as T
live_d, live_st = T.load(), T.load_stages()
live_pair = "oddspedia|cricket"
live = _contests([
    _lead("live", "Home", "Away", "2026-10-04T15:00:00Z", "hit",
          live_pair, "cricket", 0.37, headline="Home to win",
          route={"venue": "kalshi"}),
], d=live_d, st=live_st)
live_group, live_a, *_rest = sandbox_build.pair_status(live_d, live_st, "oddspedia", "cricket")
live_key = sandbox_build.verdict(live_a) if live_group is not None else "nobets"
live_card = live[0]["cards"][0]
eq(live_card.get("verdict"), sandbox_build.VERDICTS[live_key][0],
   "the live card verdict is pair_status plus verdict()")
if live_a.get("n"):
    eq(live_card.get("roi"), sandbox_build.pct(live_a.get("roi_fee"), sign=True),
       "ROI after fees is sandbox_build.pct of the assessed roi_fee")
    eq(live_card.get("record"), f"{live_a['won']}\u2013{live_a['n'] - live_a['won']}",
       "the record is the assessed won-lost line")
else:
    ok("roi" not in live_card and "record" not in live_card,
       "a live pair with no sample omits ROI and record")
eq(live_card["lane"], "Oddspedia community tips",
   "the lane name is the source label the board prints")
eq(live_card["venue"], "Kalshi", "the live card's venue badge is Kalshi")


print("\neach card uses its own pair")


def _settled_quote(i, source, won, price, sport="soccer", venue="kalshi", qid=None):
    return {
        "id": qid or f"{source}-{i}",
        "source": source,
        "sport": sport,
        "bet": True,
        "status": "won" if won else "lost",
        "result": "a" if won else "b",
        "pick": "a",
        "venue": venue,
        "price": price,
        "price_a": price,
        "price_b": round(1 - price, 4),
        "pnl": 100 * (1 / price - 1) if won else -100,
        "stake": 100.0,
        "logged": f"2026-08-{(i % 27) + 1:02d}T00:00:00+00:00",
        "start": f"2026-08-{(i % 27) + 1:02d}T12:00:00+00:00",
        "market_id": f"m-{source}-{i}",
        "side_a": "Yes",
        "side_b": "No",
    }


pair_quotes = [_settled_quote(i, "aaa_lane", True, 0.40) for i in range(12)]
pair_quotes += [_settled_quote(i, "zzz_lane", False, 0.55) for i in range(5)]
pair_d = {"quotes": pair_quotes}
pair_st = {"pairs": {}}
pair_leads = [
    _lead("own-a", "Split", "Pairs", "2026-10-04T15:00:00Z", "hit",
          "aaa_lane|soccer", "soccer", 0.40, source="aaa_lane", headline="Team 1+"),
    _lead("own-b", "Split", "Pairs", "2026-10-04T15:00:00Z", "miss",
          "zzz_lane|soccer", "soccer", 0.55, source="zzz_lane", headline="Under 3.5"),
]
pair_contest = _contests(pair_leads, d=pair_d, st=pair_st)[0]
eq(len(pair_contest["cards"]), 2, "the two-pair contest has two cards")
eq([card["market"] for card in pair_contest["cards"]], ["Team 1+", "Under 3.5"],
   "each card keeps its own market")
seen_records = []
for card, bet in zip(pair_contest["cards"], pair_contest["bets"]):
    source, sport = bet["pair"].split("|", 1)
    group, assessed, *_rest = sandbox_build.pair_status(pair_d, pair_st, source, sport)
    key = sandbox_build.verdict(assessed) if group is not None else "nobets"
    want = sandbox_build.VERDICTS[key][0]
    eq(card.get("verdict"), want, f"{card['market']} takes verdict() for {bet['pair']}")
    ok(card.get("verdict") != group,
       f"{card['market']} does not use the group label {group!r}")
    record = f"{assessed['won']}\u2013{assessed['n'] - assessed['won']}"
    eq(card.get("record"), record, f"{card['market']} shows its own record")
    eq(card.get("roi"), sandbox_build.pct(assessed.get("roi_fee"), sign=True),
       f"{card['market']} shows its own ROI after fees")
    seen_records.append(card["record"])
ok(len(set(seen_records)) == 2, "the two cards do not share one record")
ok(pair_contest["cards"][0]["roi"] != pair_contest["cards"][1]["roi"],
   "the two cards do not share one ROI")
eq(pair_contest["cards"][0]["stats_note"], "Sandbox, US exchanges, all competitions",
   "the card says the stats are the US-exchange record, every competition")


print("\ninternational lanes from a fixed contest")
intl_quotes = []
for i in range(12):
    intl_quotes.append(_settled_quote(
        i, "team1_form_l5", True, 0.40, sport="soccer_team1_intl",
        venue="kalshi_binary", qid="intl-team" if i == 0 else None))
for i in range(5):
    intl_quotes.append(_settled_quote(
        i, "o15_ranked", False, 0.55, sport="soccer_o15_intl",
        venue="kalshi_binary", qid="intl-o15" if i == 0 else None))
intl_d = {"quotes": intl_quotes}
intl_st = {"pairs": {}}
intl_leads = [
    _lead("intl-team", "Intl", "Fixture", "2026-10-04T15:00:00Z", "hit",
          "team1_form_l5|soccer_team1_intl", "soccer_team1_intl", 0.40,
          source="team1_form_l5", headline="Team 1+"),
    _lead("intl-o15", "Intl", "Fixture", "2026-10-04T15:00:00Z", "miss",
          "o15_ranked|soccer_o15_intl", "soccer_o15_intl", 0.55,
          source="o15_ranked", headline="Over 1.5"),
]
intl_contest = _contests(intl_leads, d=intl_d, st=intl_st)[0]
eq(len(intl_contest["cards"]), 2, "the international contest has two cards")
eq(sorted(bet["pair"] for bet in intl_contest["bets"]),
   ["o15_ranked|soccer_o15_intl", "team1_form_l5|soccer_team1_intl"],
   "the Over 1.5 fixture uses the o15_ranked pair")
intl_records = []
for card, bet in zip(intl_contest["cards"], intl_contest["bets"]):
    eq(card.get("venue"), "Kalshi",
       f"{card.get('market')} on the international contest is badged Kalshi")
    src, sport = bet["pair"].split("|", 1)
    group, assessed, *_rest = sandbox_build.pair_status(intl_d, intl_st, src, sport)
    key = sandbox_build.verdict(assessed) if group is not None else "nobets"
    eq(card.get("verdict"), sandbox_build.VERDICTS[key][0],
       f"{card.get('market')} uses verdict() for {bet['pair']}")
    ok(card.get("verdict") != group,
       f"{card.get('market')} does not use the group label {group!r}")
    if assessed.get("n"):
        record = f"{assessed['won']}\u2013{assessed['n'] - assessed['won']}"
        eq(card.get("record"), record,
           f"{card.get('market')} shows that pair's record")
        intl_records.append(card.get("record"))
ok(len(intl_records) == 2 and len(set(intl_records)) == 2,
   "the two international cards do not share one record")
intl_pairs = [
    (card.get("market"), card.get("venue"))
    for card, bet in zip(intl_contest["cards"], intl_contest["bets"])
    if bet.get("pair") in (
        "o15_ranked|soccer_o15_intl", "team1_form_l5|soccer_team1_intl")
]
eq(len(intl_pairs), 2, "the contest has Over 1.5 and Team 1+ international cards")
for market, venue in intl_pairs:
    eq(venue, "Kalshi", f"{market} is badged Kalshi")


print("\nvenue from the paper-bet row")
bare = _lead("bare-id", "Bare", "Venue", "2026-10-04T15:00:00Z", "hit",
             "team1_form_l5|soccer_team1_intl", "soccer_team1_intl", 0.67,
             headline="Away to score 1+")
bare.pop("venue", None)
quote = {
    "id": "bare-id",
    "source": "team1_form_l5",
    "sport": "soccer_team1_intl",
    "bet": True,
    "status": "won",
    "venue": "kalshi_binary",
    "price": 0.67,
    "pick": "a",
    "logged": "2026-10-01T00:00:00+00:00",
    "start": "2026-10-04T15:00:00+00:00",
    "market_id": "KXEXAMPLE-1",
}
bare_contest = _contests([bare], d={"quotes": [quote]})[0]
eq(bare_contest["cards"][0]["venue"], "Kalshi",
   "a lead with no venue takes Kalshi from the ledger's kalshi_binary row")
kept = _lead("own-venue", "Venue", "Keep", "2026-10-04T15:00:00Z", "hit",
             "team1_form_l5|soccer_team1_intl", "soccer_team1_intl", 0.51,
             headline="Own venue", route={"venue": "polymarket_us"})
kept_quote = dict(quote, id="own-venue")
eq(_contests([kept], d={"quotes": [kept_quote]})[0]["cards"][0]["venue"],
   "Polymarket US",
   "the lead's own venue wins over the paper-bet row")
no_row = _lead("no-row", "No", "Row", "2026-10-04T15:00:00Z", "hit",
               "team1_form_l5|soccer_team1_intl", "soccer_team1_intl", 0.50,
               headline="No venue")
ok("venue" not in _contests([no_row])[0]["cards"][0],
   "with no lead venue and no paper-bet row, the badge is omitted")


def _raise_oserror(*_args, **_kwargs):
    raise OSError("unexpected")


def _raise_zero(*_args, **_kwargs):
    raise ZeroDivisionError("empty sample")


def _raise_value(*_args, **_kwargs):
    raise ValueError("empty sample")


_saved_pair_status = sandbox_build.pair_status
sandbox_build.pair_status = _raise_oserror
try:
    _raised = False
    try:
        shell_build._lane_board({"quotes": []}, {"pairs": {}}, "aaa|soccer", {})
    except OSError:
        _raised = True
    ok(_raised, "an unexpected OSError from pair_status is raised")
finally:
    sandbox_build.pair_status = _saved_pair_status
for _exc, _raiser, _why in (
    (ZeroDivisionError, _raise_zero, "a ZeroDivisionError from pair_status is raised"),
    (ValueError, _raise_value, "a ValueError from pair_status is raised"),
):
    sandbox_build.pair_status = _raiser
    _raised = False
    try:
        try:
            shell_build._lane_board({"quotes": []}, {"pairs": {}}, "aaa|soccer", {})
        except _exc:
            _raised = True
        ok(_raised, _why)
    finally:
        sandbox_build.pair_status = _saved_pair_status
eq(shell_build._lane_board({}, {"pairs": {}}, "aaa|soccer", {}),
   {"verdict": None, "roi": None, "record": None},
   "a ledger with no quotes omits verdict, ROI and record")
_empty_sample = shell_build._lane_board(
    {"quotes": []}, {"pairs": {}}, "missing|soccer", {})
ok(_empty_sample["roi"] is None and _empty_sample["record"] is None,
   "an empty sample omits ROI and record without dividing")


print("\nfull page targets a page that exists")
js_page = shell_build.page(NOW, d={"quotes": []}, st={"pairs": {}}, blob=_blob(mix))
for _row in _rows(js_page):
    _href = _attr(_row, "data-page")
    _name = _href[2:] if _href and _href.startswith("./") else _href
    ok(_name and os.path.isfile(os.path.join(ROOT, "public_site", _name)),
       f"{_href} is a page on disk")
ok(not os.path.isfile(os.path.join(ROOT, "public_site", "football.html")),
   "football.html is not a page, so a link to it would fail this check")
_shell_js = open(os.path.join(ROOT, "public_site", "shell.js"), encoding="utf-8").read()
ok("var SAFE_PAGE" in _shell_js and "SAFE_PAGE.test(page)" in _shell_js,
   "shell.js refuses a Full page href that is not a sport or Production page")
ok('card.roi + " Sandbox ROI after fees"' in _shell_js
   and 'card.record + " Sandbox record"' in _shell_js,
   "ROI and record are labeled as the Sandbox record")
ok("card.stats_note" in _shell_js,
   "the all-competitions note is rendered from the card")


print("\nshell text is at least 11px")
css = open(os.path.join(ROOT, "public_site", "site.css"), encoding="utf-8").read()
shell_at = css.find("/* SofaScore shell.")
ok(shell_at >= 0, "site.css marks the shell block")
shell_css = css[shell_at:]
declared = re.findall(r"font-size:\s*([0-9.]+)(px|rem|em)\b", shell_css)
ok(declared, "the shell block declares font sizes")
small = []
for number, unit in declared:
    px = float(number) if unit == "px" else float(number) * 15
    if px < 11:
        small.append(f"{number}{unit}")
eq(small, [], "no shell font-size is below 11px")
js = open(os.path.join(ROOT, "public_site", "shell.js"), encoding="utf-8").read()
for needle in ("innerHTML", "insertAdjacentHTML", "outerHTML", "document.write", "eval("):
    ok(needle not in js, f"shell.js does not use {needle}")
ok("textContent" in js, "shell.js writes card text with textContent")


def _browser():
    from require_browser import require_browser
    sync_playwright = require_browser("test_shell_cards.py")
    if sync_playwright is None:
        return
    site = tempfile.mkdtemp(prefix="shell-cards-")
    try:
        browser_html = shell_build.page(NOW, d={"quotes": []}, st={"pairs": {}}, blob=_blob(mix + [
            _lead("late", "Late", "Grade", "2026-10-05T11:59:59Z", "pending",
                  "oddspedia|cricket", "cricket", 0.50),
            _lead("on", "On", "Time", "2026-10-05T12:00:00Z", "pending",
                  "oddspedia|cricket", "cricket", 0.51),
            _lead("won", "Win", "Wait", "2026-10-05T11:00:00Z", "hit",
                  "a|soccer", "soccer", 0.40),
            _lead("stuck", "Win", "Wait", "2026-10-05T11:00:00Z", "pending",
                  "b|soccer", "soccer", 0.70),
        ]))
        open(os.path.join(site, "index.html"), "w", encoding="utf-8").write(browser_html)
        for name in ("site.css", "shell.js", "tables.js"):
            shutil.copy(os.path.join(ROOT, "public_site", name), os.path.join(site, name))

        class Handler(SimpleHTTPRequestHandler):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, directory=site, **kwargs)

            def log_message(self, fmt, *args):
                return

        httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{httpd.server_address[1]}/index.html"
        print("\nbrowser")
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(channel="chrome", headless=True)
                view = browser.new_page(viewport={"width": 1280, "height": 800})
                view.goto(base, wait_until="load")
                colors = view.evaluate("""() => {
                  const awaiting = document.querySelector('.running-status[data-status="awaiting"]');
                  const open = document.querySelector('.running-row:not([data-awaiting="true"]) .running-status');
                  if (!awaiting || !open) return null;
                  const a = getComputedStyle(awaiting);
                  const b = getComputedStyle(open);
                  return { awaiting: a.color, open: b.color, italic: a.fontStyle };
                }""")
                ok(colors and colors["awaiting"] != colors["open"] and colors["italic"] == "italic",
                   f"Awaiting result is styled apart from an open Live row ({colors})")
                warn = view.evaluate("""() => {
                  const row = [...document.querySelectorAll(".running-row")]
                    .find((item) => item.getAttribute("data-name") === "Win v Wait");
                  if (!row) return null;
                  const shadow = getComputedStyle(row).boxShadow;
                  return {
                    flag: row.getAttribute("data-awaiting"),
                    shadow: shadow,
                    hidden: row.hidden,
                  };
                }""")
                ok(warn and warn["flag"] == "true" and not warn["hidden"]
                   and "245, 194, 107" in warn["shadow"],
                   f"a mixed awaiting row keeps the warn bar ({warn})")
                view.locator('.bet-chip').filter(has_text="Late v Grade").focus()
                view.keyboard.press("Enter")
                view.wait_for_timeout(30)
                card_style = view.evaluate("""() => {
                  const status = document.querySelector(".rule-mini .running-status");
                  if (!status) return null;
                  const style = getComputedStyle(status);
                  return {
                    token: status.getAttribute("data-status"),
                    color: style.color,
                    italic: style.fontStyle,
                    text: status.textContent,
                  };
                }""")
                ok(card_style and card_style["token"] == "awaiting"
                   and card_style["italic"] == "italic"
                   and "245, 194, 107" in card_style["color"]
                   and "Awaiting result" in card_style["text"],
                   f"an Awaiting result card uses the warn italic style ({card_style})")
                view.keyboard.press("Escape")
                view.wait_for_timeout(30)
                view.click('.running-filters button[data-filter="settled"]')
                view.wait_for_timeout(30)
                row = view.locator(".running-row:not([hidden])")
                row.focus()
                view.keyboard.press("Enter")
                shown = view.evaluate("""() => {
                  const cards = [...document.querySelectorAll(".rule-mini")];
                  const section = document.getElementById("rules-section");
                  const line = document.getElementById("rules-line");
                  const empty = document.getElementById("rules-empty");
                  const link = document.querySelector("a.full-page");
                  const host = document.getElementById("rules-cards");
                  return {
                    n: cards.length,
                    pills: cards.map((card) => {
                      const pill = card.querySelector(".lane-pill");
                      return pill ? pill.textContent : "";
                    }),
                    text: host ? host.textContent : "",
                    imgs: host ? host.querySelectorAll("img, svg, script").length : -1,
                    section: section ? section.textContent : "",
                    line: line ? line.textContent : "",
                    emptyHidden: empty ? empty.hidden : null,
                    href: link ? link.getAttribute("href") : "",
                    html: host ? host.innerHTML : "",
                  };
                }""")
                ok(shown["n"] == 2, f"keyboard selection renders one card per bet ({shown['n']})")
                eq(shown["pills"], ["PRODUCTION", "Sandbox"],
                   "rendered cards keep Production before Sandbox")
                ok(shown["section"] == "Rules applied · 2 lanes fired",
                   f"the section counts the lanes ({shown['section']!r})")
                ok("67¢ / 40¢" in shown["line"],
                   f"the header lists both prices ({shown['line']!r})")
                ok(hostile_lane in shown["text"] and hostile_market in shown["text"],
                   "hostile lane and market names render as text")
                ok("Sandbox, US exchanges, all competitions" in shown["text"],
                   "the card says the stats are the US-exchange record")
                live = view.evaluate("""() => {
                  const region = document.getElementById("rules-live");
                  const pressed = document.querySelector('.running-row[aria-pressed="true"]');
                  return {
                    live: region ? region.getAttribute("aria-live") : "",
                    text: region ? region.textContent : "",
                    name: pressed ? pressed.getAttribute("data-name") : "",
                  };
                }""")
                eq(live["live"], "polite", "the selection is announced in a polite live region")
                ok(live["name"] and live["name"] in live["text"],
                   f"the live region names the selected contest ({live['text']!r})")
                eq(shown["imgs"], 0, "hostile names do not become elements")
                ok("<img" not in shown["html"] and "<svg" not in shown["html"]
                   and "<script" not in shown["html"],
                   "the card host has no injected tags")
                ok(shown["emptyHidden"], "the empty state hides once cards show")
                eq(shown["href"], "./soccer.html", "Full page follows the contest's sport page")
                sizes = view.evaluate("""() => {
                  const nodes = [...document.querySelectorAll("header.site *, main *")];
                  const small = [];
                  for (const el of nodes) {
                    if (el.closest(".sr-only")) continue;
                    const size = parseFloat(getComputedStyle(el).fontSize);
                    if (size < 11) small.push((el.className || el.tagName) + " " + size);
                  }
                  return small;
                }""")
                eq(sizes, [], "computed shell text, including the cards, is at least 11px")
                loaded = view.evaluate("""async () => {
                  const res = await fetch("./shell.js");
                  return await res.text();
                }""")
                ok("innerHTML" not in loaded and "insertAdjacentHTML" not in loaded,
                   "the shell.js the page loaded does not use innerHTML")
                ok("SAFE_PAGE.test(page)" in loaded,
                   "the shell.js the page loaded still checks Full page hrefs")
                view.keyboard.press("Escape")
                view.wait_for_timeout(30)
                escaped = view.evaluate("""() => {
                  const empty = document.getElementById("rules-empty");
                  const live = document.getElementById("rules-live");
                  const link = document.querySelector("a.full-page");
                  return {
                    pressed: document.querySelectorAll('.running-row[aria-pressed="true"]').length,
                    chips: document.querySelectorAll('.bet-chip[aria-pressed="true"]').length,
                    cards: document.querySelectorAll(".rule-mini").length,
                    emptyHidden: empty ? empty.hidden : null,
                    live: live ? live.textContent : "",
                    href: link ? link.getAttribute("href") : "",
                  };
                }""")
                eq(escaped["pressed"], 0, "Escape clears aria-pressed")
                eq(escaped["chips"], 0, "Escape clears the chip's aria-pressed")
                eq(escaped["cards"], 0, "Escape clears the cards")
                ok(not escaped["emptyHidden"], "Escape restores the empty state")
                eq(escaped["live"], "Select a contest in Running.",
                   "Escape announces the empty state")
                eq(escaped["href"], "./production.html",
                   "Escape resets Full page to the Production board")
                view.click(".running-row:not([hidden])")
                view.wait_for_timeout(30)
                view.click(".running-row:not([hidden])")
                view.wait_for_timeout(30)
                reclicked = view.evaluate("""() => {
                  const link = document.querySelector("a.full-page");
                  return {
                    pressed: document.querySelectorAll('.running-row[aria-pressed="true"]').length,
                    cards: document.querySelectorAll(".rule-mini").length,
                    href: link ? link.getAttribute("href") : "",
                  };
                }""")
                eq(reclicked["pressed"], 0, "clicking the selected row clears aria-pressed")
                eq(reclicked["cards"], 0, "clicking the selected row clears the cards")
                eq(reclicked["href"], "./production.html",
                   "clicking the selected row resets Full page")
                sport = view.evaluate("""() => {
                  const nav = document.querySelector("nav.sports");
                  nav.setAttribute("data-sport-filter", "cricket");
                  document.querySelector(".running-filters button[aria-pressed='true']").click();
                  const row = [...document.querySelectorAll(".running-row")]
                    .find((item) => item.getAttribute("data-name") === "Mix v Match");
                  return row ? row.hidden : null;
                }""")
                ok(sport is True, "a cricket sport filter hides the soccer row")
                view.locator(".bet-chip").filter(has_text="Mix v Match").first.click()
                view.wait_for_timeout(30)
                opened = view.evaluate("""() => {
                  const nav = document.querySelector("nav.sports");
                  const row = [...document.querySelectorAll(".running-row")]
                    .find((item) => item.getAttribute("data-name") === "Mix v Match");
                  const chip = [...document.querySelectorAll(".bet-chip")]
                    .find((item) => item.textContent.indexOf("Mix v Match") >= 0);
                  const link = document.querySelector("a.full-page");
                  return {
                    filter: nav ? nav.getAttribute("data-sport-filter") : "",
                    hidden: row ? row.hidden : null,
                    pressed: row ? row.getAttribute("aria-pressed") : "",
                    chip: chip ? chip.getAttribute("aria-pressed") : "",
                    cards: document.querySelectorAll(".rule-mini").length,
                    href: link ? link.getAttribute("href") : "",
                    bucket: document.querySelector(".running-filters button[aria-pressed='true']")
                      ? document.querySelector(".running-filters button[aria-pressed='true']").getAttribute("data-filter")
                      : "",
                  };
                }""")
                ok(opened["filter"] in ("all", "soccer") and opened["hidden"] is False
                   and opened["pressed"] == "true" and opened["chip"] == "true"
                   and opened["cards"] == 2 and opened["href"] == "./soccer.html"
                   and opened["bucket"] == "settled",
                   f"a chip reveals the contest, selects it, and opens its cards ({opened})")
                view.locator(".bet-chip").filter(has_text="Mix v Match").first.focus()
                view.keyboard.press(" ")
                view.wait_for_timeout(30)
                closed = view.evaluate("""() => {
                  const link = document.querySelector("a.full-page");
                  return {
                    pressed: document.querySelectorAll('.running-row[aria-pressed="true"]').length,
                    chips: document.querySelectorAll('.bet-chip[aria-pressed="true"]').length,
                    cards: document.querySelectorAll(".rule-mini").length,
                    href: link ? link.getAttribute("href") : "",
                  };
                }""")
                eq(closed["pressed"], 0, "Space on the selected chip clears the row")
                eq(closed["chips"], 0, "Space on the selected chip clears aria-pressed")
                eq(closed["cards"], 0, "Space on the selected chip closes the cards")
                eq(closed["href"], "./production.html",
                   "closing the chip resets Full page")
                view.evaluate("""() => {
                  const row = document.querySelector(".running-row:not([hidden])");
                  row.setAttribute("data-page", "./football.html");
                  row.click();
                }""")
                view.wait_for_timeout(30)
                blocked = view.evaluate("""() => {
                  const link = document.querySelector("a.full-page");
                  return link ? link.getAttribute("href") : "";
                }""")
                eq(blocked, "./production.html",
                   "a Full page href for a missing page stays on production.html")
                view.click('.running-filters button[data-filter="upcoming"]')
                view.wait_for_timeout(30)
                cleared = view.evaluate("""() => {
                  const empty = document.getElementById("rules-empty");
                  const link = document.querySelector("a.full-page");
                  return {
                    cards: document.querySelectorAll(".rule-mini").length,
                    empty: empty ? empty.textContent : "",
                    emptyHidden: empty ? empty.hidden : null,
                    href: link ? link.getAttribute("href") : "",
                  };
                }""")
                eq(cleared["cards"], 0, "hiding the selected row clears the cards")
                eq(cleared["empty"], "Select a contest in Running.",
                   "hiding the selected row restores the empty state")
                ok(not cleared["emptyHidden"], "the empty state is visible again")
                eq(cleared["href"], "./production.html",
                   "Full page returns to the Production board")
                phone = browser.new_page(viewport={"width": 390, "height": 740})
                phone.goto(base, wait_until="load")
                phone.click('.running-filters button[data-filter="settled"]')
                phone.wait_for_timeout(30)
                phone.click(".running-row:not([hidden])")
                phone.wait_for_timeout(50)
                placed = phone.evaluate("""() => {
                  const section = document.getElementById("rules-section");
                  if (!section) return null;
                  const box = section.getBoundingClientRect();
                  return { top: box.top, bottom: box.bottom, height: window.innerHeight };
                }""")
                ok(placed and placed["top"] < placed["height"] and placed["bottom"] > 0,
                   f"a narrow screen scrolls the cards into view ({placed})")
                phone.close()
                browser.close()
        finally:
            httpd.shutdown()
    finally:
        shutil.rmtree(site, ignore_errors=True)


_browser()

print()
if FAILS:
    print(f"{len(FAILS)} FAILED")
    sys.exit(1)
print("all passed")
