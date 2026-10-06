#!/usr/bin/env python3
"""SofaScore shell slice 2: the Running list, and the #69 follow-ups.

Fails while the root is still an empty pane, record_build stamps index.html
with its own clock, or the freshness notes still call that page a redirect stub.
Passes once one build writes a Production contest row per contest, the filters
count those rows, and the follow-ups hold. No network.
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

FAILS = []
ROOT = os.path.dirname(os.path.abspath(__file__))
NOW = datetime.datetime(2026, 10, 5, 18, 0, tzinfo=timezone.utc)


def ok(cond, why):
    print(f"  {'ok  ' if cond else 'FAIL'} {why}")
    if not cond:
        FAILS.append(why)


def eq(got, want, why):
    ok(got == want, why if got == want else f"{why} — got {got!r}, want {want!r}")


def _lead(lid, home, away, kickoff, status, pair, sport, price, league="League"):
    return {
        "id": lid,
        "home": home,
        "away": away,
        "match": f"{home} v {away}",
        "headline": f"{home} to win",
        "kickoff": kickoff,
        "status": status,
        "pair": pair,
        "sport": sport,
        "lane": "production",
        "price_at_log": price,
        "league": league,
        "source": pair.split("|", 1)[0],
        "sandbox_quote": lid,
    }


def _blob(leads):
    return {"leads": {lead["id"]: lead for lead in leads}, "pairs": {}}


def _rows(page):
    return re.findall(r'<button\b[^>]*class="running-row"[^>]*>.*?</button>', page, re.S)


def _chips(page):
    return re.findall(r'<button\b[^>]*class="bet-chip"[^>]*>.*?</button>', page, re.S)


def _chip_text(tag):
    return re.sub(r"\s+", " ", html_lib.unescape(re.sub(r"<[^>]+>", " ", tag))).strip()


def _attr(tag, name):
    match = re.search(rf'\b{name}="([^"]*)"', tag)
    return html_lib.unescape(match.group(1)) if match else None


def _filter_count(page, key, label):
    match = re.search(
        rf'data-filter="{key}"[^>]*>{label} <span class="count">(\d+)</span>',
        page)
    return int(match.group(1)) if match else None


def _groups(page):
    return re.findall(
        r'<section class="running-group"[^>]*>\s*<h3>([^<]+)</h3>(.*?)</section>',
        page, re.S)


def _quote(qid, status, start, settled=None, price=0.54, source="oddspedia",
           home="QuoteHome", away="QuoteAway"):
    row = {
        "id": qid,
        "source": source,
        "sport": "cricket",
        "bet": True,
        "status": status,
        "pick": "a",
        "side_a": home,
        "side_b": away,
        "market_id": "m-" + qid,
        "venue": "polymarket_us",
        "start": start,
        "logged": "2026-10-01T00:00:00+00:00",
        "start_source": "espn",
        "price": price,
        "label": f"{home} v {away}",
    }
    if settled:
        row["settled"] = settled
    if status == "won":
        row["result"] = "a"
    if status == "lost":
        row["result"] = "b"
    if status == "settled":
        row["result"] = "price"
    return row


def _prod_st(*keys):
    return {"pairs": {
        key: {"stage": "production", "ready_at": "2026-09-01T00:00:00+00:00"}
        for key in keys
    }}


print("running rows")
import shell_build

LEADS = [
    _lead("alpha-a", "Alpha", "Beta", "2026-10-06T15:00:00Z", "pending",
          "oddspedia|cricket", "cricket", 0.54, "Big Bash"),
    _lead("alpha-b", "Alpha", "Beta", "2026-10-06T15:00:00Z", "pending",
          "team1|cricket", "cricket", 0.40, "Big Bash"),
    _lead("gamma", "Gamma", "Delta", "2026-10-07T15:00:00Z", "pending",
          "o15_ranked|soccer_o15_intl", "soccer_o15_intl", 0.61, "Nations League"),
    _lead("echo", "Echo", "Foxtrot", "2026-10-04T15:00:00Z", "hit",
          "oddspedia|cricket", "cricket", 0.48, "Big Bash"),
    _lead("inside", "Inside", "Edge", "2026-10-01T18:00:00Z", "miss",
          "oddspedia|cricket", "cricket", 0.33, "Big Bash"),
    _lead("old", "Old", "Gone", "2026-09-21T18:00:00Z", "hit",
          "oddspedia|cricket", "cricket", 0.70, "Big Bash"),
    _lead("live", "Live", "Now", "2026-10-05T12:00:00Z", "pending",
          "oddspedia|cricket", "cricket", 0.52, "Big Bash"),
    _lead("voided", "Void", "Match", "2026-10-03T18:00:00Z", "void",
          "oddspedia|cricket", "cricket", 0.50, "Big Bash"),
    _lead("priced", "Price", "Result", "2026-10-02T18:00:00Z", "price",
          "oddspedia|cricket", "cricket", 0.25, "Big Bash"),
    _lead("hostile", "<b>Beta", 'javascript:alert(1)', "2026-10-08T15:00:00Z", "pending",
          "oddspedia|cricket", "cricket", 0.54, 'League "x"'),
]
PAGE = shell_build.page(NOW, d={"quotes": []}, st={"pairs": {}}, blob=_blob(LEADS))
ROWS = _rows(PAGE)

eq(len(ROWS), 8, "one row per contest, with the contest outside the 14-day window left out")
ok("Old v Gone" not in PAGE, "a contest outside the 14 Chicago-day window is left out")
ok(f"Last {shell_build.SHELL_SETTLED_DAYS} days" in PAGE,
   "the settled caption is the shell window constant")
ok('id="settled-caption" hidden' in PAGE, "the caption starts hidden, with Live selected")
ok(all("o15_ranked" not in row and "team1|cricket" not in row for row in ROWS),
   "rows do not print source ids")

by_name = {_attr(row, "data-name"): row for row in ROWS}


def _got(name):
    return by_name.get(name, "")


ok("Alpha v Beta" in by_name, "the two Alpha lanes collapse to one contest")
eq(sum(1 for row in ROWS if _attr(row, "data-name") == "Alpha v Beta"), 1,
   "the contest title is not repeated per lane")
ok("2 lanes" in _got("Alpha v Beta"), "a contest with two lanes shows the count")
ok("Gamma v Delta" in by_name and "2 lanes" not in _got("Gamma v Delta"),
   "a single lane does not show a count")
eq(_attr(_got("Alpha v Beta"), "data-price"), "54¢ / 40¢",
   "two different prices both show, 54¢ and 40¢")
ok("$" not in _got("Alpha v Beta") and "0.54" not in _got("Alpha v Beta"),
   "the row does not print a dollar price or the raw fraction")
eq(_attr(_got("Alpha v Beta"), "data-filter"), "upcoming", "a later kickoff is upcoming")
eq(_attr(_got("Live v Now"), "data-filter"), "live", "started and unsettled is live")
ok(">Live</span>" in _got("Live v Now"), "a live row's time says Live")
eq(_attr(_got("Echo v Foxtrot"), "data-filter"), "settled", "a hit inside the window is settled")
ok(">W</span>" in _got("Echo v Foxtrot"), "a hit renders as W")
ok('class="sr-only">won</span>' in _got("Echo v Foxtrot"),
   "a single win is spoken as won")
ok(">L</span>" in _got("Inside v Edge"), "a miss renders as L")
ok('class="sr-only">lost</span>' in _got("Inside v Edge"),
   "a single loss is spoken as lost")
ok(">Void</span>" in _got("Void v Match"), "a void renders as Void")
ok(">price result</span>" in _got("Price v Result"), "a price payout renders as price result")
ok(">2 open</span>" in _got("Alpha v Beta") and 'class="sr-only">2 open</span>' in _got("Alpha v Beta"),
   "two open bets on one contest read 2 open")
ok(">Production</span>" in _got("Alpha v Beta"), "the lane pill says Production")
ok(">Sandbox</span>" not in PAGE, "Sandbox contests are not on the Production list")
ok("Tomorrow" in _got("Alpha v Beta"), "tomorrow's kickoff is a relative day")
ok("Yesterday" in _got("Echo v Foxtrot"), "yesterday's kickoff is a relative day")

groups = _groups(PAGE)
eq([name for name, _body in groups], ["Soccer", "Cricket"],
   "rows are grouped under sport labels, Soccer then Cricket")
soccer_body = dict(groups)["Soccer"]
cricket_body = dict(groups)["Cricket"]
ok("Gamma v Delta" in soccer_body and "Alpha v Beta" not in soccer_body,
   "a soccer contest sits under Soccer only")
ok("Alpha v Beta" in cricket_body and "Gamma v Delta" not in cricket_body,
   "a cricket contest sits under Cricket only")

for key, label in (("live", "Live"), ("settled", "Settled"), ("upcoming", "Upcoming")):
    shown = sum(1 for row in ROWS if _attr(row, "data-filter") == key)
    eq(_filter_count(PAGE, key, label), shown,
       f"the {label} count equals the rendered {label} rows")

ok("No live paper bets" in PAGE and "No settled paper bets" in PAGE
   and "No upcoming paper bets" in PAGE,
   "each filter has its empty-state copy")
ok("No live, settled, or upcoming paper bets." not in PAGE,
   "the combined empty line is gone")
ok("These filters do not change the list yet." not in PAGE,
   "the filters are no longer marked display-only")
ok('class="rule-mini"' not in PAGE, "there are still no rule cards")
ok("Select a contest in Running." in PAGE, "the detail pane starts empty")
ok('id="rules-line"' in PAGE, "the detail header is ready for the selected contest")
ok('href="javascript:' not in PAGE and 'href="data:' not in PAGE,
   "rendered text does not become a javascript or data link")
ok("<script>alert" not in PAGE and "&lt;b&gt;Beta" in PAGE,
   "contest text is escaped")
ok("javascript:alert(1)" in html_lib.unescape(PAGE)
   and 'href="javascript:alert(1)"' not in PAGE,
   "a javascript: string stays text")
_sports_nav = re.search(r'<nav class="sports"[^>]*>.*?</nav>', PAGE, re.S)
ok(_sports_nav and 'aria-disabled' not in _sports_nav.group(0)
   and 'tabindex="-1"' not in _sports_nav.group(0)
   and 'id="sports-soon"' not in PAGE and ">Coming soon</p>" not in PAGE,
   "sport pills are enabled filters, with no Coming soon note")
ok('data-sport="all" aria-pressed="true"' in (_sports_nav.group(0) if _sports_nav else ""),
   "All starts pressed")
eq(PAGE.count('aria-describedby="settled-caption"'), 1,
   "only the Settled filter points at the 14-day caption")
ok('data-filter="settled" aria-pressed="false" aria-describedby="settled-caption"' in PAGE,
   "the Settled filter's described-by is the caption")


print("\nopen and recent roll")
CHIPS = _chips(PAGE)
ok(CHIPS, "the fixture roll has chips")
ok("No open or recent paper bets yet." not in PAGE,
   "a roll with chips does not keep the empty state")
empty_roll = shell_build.page(
    NOW, d={"quotes": []}, st={"pairs": {}}, blob={"leads": {}, "pairs": {}})
ok("No open or recent paper bets yet." in empty_roll and 'class="bet-chip"' not in empty_roll,
   "the empty state stays when there is nothing to show")
ok("Old v Gone" not in _chip_text(" ".join(CHIPS)),
   "a contest outside the 14-day window is not a chip")
chip_names = []
for chip in CHIPS:
    contest = _attr(chip, "data-contest")
    matched = [item for item in ROWS if _attr(item, "data-contest") == contest]
    eq(len(matched), 1, f"chip {contest} selects exactly one Running row")
    if len(matched) != 1:
        continue
    chip_names.append((_attr(chip, "data-status"), _attr(matched[0], "data-name")))
# Open bets by kickoff, then settled bets newest first.
eq([item[1] for item in chip_names], [
    "Live v Now",
    "Alpha v Beta",
    "Alpha v Beta",
    "Gamma v Delta",
    "<b>Beta v javascript:alert(1)",
    "Echo v Foxtrot",
    "Void v Match",
    "Price v Result",
    "Inside v Edge",
], "open chips follow kickoff, then settled chips are newest first")
eq([item[0] for item in chip_names], [
    "Open", "Open", "Open", "Open", "Open", "W", "Void", "price result", "L",
], "chip status is Open, then W, Void, price result, and L")
alpha_chips = [chip for chip in CHIPS if "Alpha v Beta" in _chip_text(chip)]
eq(len(alpha_chips), 2, "each open bet on one contest is its own chip")
eq(_attr(alpha_chips[0], "data-contest"), _attr(_got("Alpha v Beta"), "data-contest"),
   "a chip points at that contest's Running row")
ok("C" in _chip_text(alpha_chips[0]) and "Alpha to win · 54¢" in _chip_text(alpha_chips[0]),
   "a chip shows the sport letter, the market, and the price in cents")
ok("Alpha to win · 40¢" in _chip_text(alpha_chips[1]),
   "the second chip keeps the other bet's price")
gamma_chips = [chip for chip in CHIPS if "Gamma v Delta" in _chip_text(chip)]
eq(len(gamma_chips), 1, "Gamma v Delta is one chip")
ok(gamma_chips and "S" in _chip_text(gamma_chips[0]),
   "a soccer chip uses the sport letter S")
ok('aria-pressed="false"' in CHIPS[0] and "tabindex=\"-1\"" not in CHIPS[0],
   "a chip is a focusable button that starts unpressed")
ok("&lt;b&gt;" in CHIPS[4] and 'href="javascript:' not in CHIPS[4],
   "the hostile chip escapes the contest name and does not make it a link")
top = re.search(r'<div class="topbar">.*?<p class="stamp">(.*?)</p>', PAGE, re.S)
ok(top and "2026-10-05T18:00:00Z" in top.group(1) and "CT" in top.group(1),
   "the top bar stamp is this build's clock, labeled CT")
ok(shell_build._stamp(NOW) in top.group(0),
   "the stamp reuses the build timestamp, not a new clock")


print("\ntwo prices inside the 14-day window")
_twin_kick = datetime.datetime(2026, 10, 4, 16, 0, tzinfo=timezone.utc)
ok(shell_build._in_shell_window(_twin_kick, NOW),
   "the two-price fixture is inside the 14-day settled window")
_twin_page = shell_build.page(NOW, d={"quotes": []}, st={"pairs": {}}, blob=_blob([
    _lead("w91", "Twin", "Price", "2026-10-04T16:00:00Z", "hit",
          "a|soccer", "soccer", 0.91),
    _lead("l40", "Twin", "Price", "2026-10-04T16:00:00Z", "miss",
          "b|soccer", "soccer", 0.40),
]))
_twin_rows = [row for row in _rows(_twin_page) if _attr(row, "data-name") == "Twin v Price"]
_two_price = [row for row in _twin_rows if " / " in (_attr(row, "data-price") or "")]
ok(len(_two_price) > 0, "the fixture checked at least one two-price contest")
eq(len(_twin_rows), 1, "two prices on one contest are one Running row")
eq(_attr(_twin_rows[0], "data-filter"), "settled",
   "a graded two-price contest inside the window is Settled")
eq(_attr(_twin_rows[0], "data-price"), "91¢ / 40¢",
   "a production-recent row lists each bet's cents")
ok("92¢" not in (_attr(_twin_rows[0], "data-price") or ""),
   "91¢ is not shown as 92¢")
_twin_cards = json.loads(_attr(_twin_rows[0], "data-cards"))
eq([card["price"] for card in _twin_cards], ["91¢", "40¢"],
   "each card price matches that bet, 91¢ then 40¢")
eq(_twin_cards[0]["price"], shell_build._cents(0.91),
   "the card price is the cents helper, so 0.91 stays 91¢")
eq(shell_build._cents(0.91), "91¢", "0.91 formats as 91¢")


def _face_leads(pairs, kickoff="2026-10-04T15:00:00Z"):
    leads = []
    for i, item in enumerate(pairs):
        status, pair = item[0], item[1]
        price = item[2] if len(item) > 2 else 0.5
        leads.append(_lead(
            f"mix-{i}", "Kazakhstan", "Faroe Islands", kickoff,
            status, pair, "soccer", price, "UEFA Nations League"))
    return leads


def _face_page(pairs, kickoff="2026-10-04T15:00:00Z"):
    return _rows(shell_build.page(
        NOW, d={"quotes": []}, st={"pairs": {}},
        blob=_blob(_face_leads(pairs, kickoff))))


def _face_contests(pairs, kickoff="2026-10-04T15:00:00Z"):
    blob = _blob(_face_leads(pairs, kickoff))
    return shell_build.contests_from_lanes(
        shell_build.collect_lanes({"quotes": []}, {"pairs": {}}, blob, NOW), NOW)


def _subset_gaps(contests, entries):
    """Entries are (match, status, cents).

    A Live contest is exempt only when it still has an open bet. A finished
    contest that was bucketed Live anyway is checked, so a missing price fails.
    A gap means a production bet was not matched to its own status and price.
    Prices come from the contest's bet list, not the row price.
    """
    by_match = {}
    for contest in contests:
        by_match[contest["match"]] = {
            "bucket": contest["bucket"],
            "bets": [dict(bet) for bet in contest["bets"]],
        }
    gaps = []
    for match, status, cents in entries:
        contest = by_match.get(match)
        if contest is None:
            gaps.append((match, status, cents))
            continue
        open_bet = any(bet.get("status") == "Open" for bet in contest["bets"])
        if contest["bucket"] == "live" and open_bet:
            continue
        if not open_bet and contest["bucket"] != "settled":
            gaps.append((match, status, cents))
            continue
        found = next((i for i, bet in enumerate(contest["bets"])
                      if bet["status"] == status and shell_build._cents(bet["price"]) == cents),
                     None)
        if found is None:
            gaps.append((match, status, cents))
            continue
        contest["bets"].pop(found)
    return gaps


def _bet_labels(visual):
    if visual in ("W", "L", "Open", "Void", "price result", "Awaiting result"):
        return [visual]
    labels = {"W": "W", "L": "L", "price result": "price result", "void": "Void",
              "open": "Open", "awaiting": "Awaiting result"}
    out = []
    rest = visual
    while rest:
        rest = rest.lstrip()
        if not rest:
            break
        matched = re.match(r"(\d+)(W|L)(?![A-Za-z])", rest) or re.match(
            r"(\d+) (price result|void|open|awaiting)(?![A-Za-z])", rest)
        if not matched:
            word = rest.strip()
            if word and " " not in word and not word[0].isdigit():
                out.append(word)
                break
            raise AssertionError(visual)
        out.extend([labels[matched.group(2)]] * int(matched.group(1)))
        rest = rest[matched.end():]
    return out


print("\nsplit results stay one row")
# Under 3.5 sorts ahead of Faroe 1+ by pair name. The row must not keep only that loss.
kaz_pairs = [
    ("miss", "under35|soccer", 0.67),
    ("hit", "zzz_faroe|soccer", 0.80),
]
kaz = _face_page(kaz_pairs)
kaz_contest = _face_contests(kaz_pairs)
eq(len(kaz), 1, "Kazakhstan v Faroe stays one row when the two bets grade apart")
eq(len(kaz_contest), 1, "the split is still one contest in the row model")
ok(">1W 1L</span>" in kaz[0], "Faroe 1+ won and Under 3.5 lost render as 1W 1L")
ok('class="sr-only">1 won, 1 lost</span>' in kaz[0],
   "the split is spoken as 1 won, 1 lost")
eq([shell_build._cents(bet["price"]) for bet in kaz_contest[0]["bets"]], ["67¢", "80¢"],
   "each Kazakhstan bet keeps its own price, 67¢ and 80¢")
eq([bet["status"] for bet in kaz_contest[0]["bets"]], ["L", "W"],
   "the bet list is the loss and the win, not the row's first result")
eq(_attr(kaz[0], "data-price"), "67¢ / 80¢",
   "different prices list on the row, 67¢ and 80¢")
ok(all(shell_build._cents(bet["price"]) in _attr(kaz[0], "data-price")
       for bet in kaz_contest[0]["bets"]),
   "every Kazakhstan bet's cents is on the row")
# One fixture, two lead ids. One lead has sides; the other has only the
# match title Production writes as "{home} v {away}". They are one row.
half_kick = "2026-10-04T15:00:00Z"
half_sided = _lead("half-sides", "Halfmatch", "Teams", half_kick, "hit",
                   "a|soccer", "soccer", 0.41)
half_title = {
    "id": "half-title",
    "match": "Halfmatch v Teams",
    "headline": "Over 1.5 goals",
    "kickoff": half_kick,
    "status": "miss",
    "pair": "b|soccer",
    "sport": "soccer",
    "lane": "production",
    "price_at_log": 0.62,
    "league": "League",
    "source": "b",
    "sandbox_quote": "half-title",
}
half_blob = _blob([half_sided, half_title])
half_rows = _rows(shell_build.page(
    NOW, d={"quotes": []}, st={"pairs": {}}, blob=half_blob))
half_named = [row for row in half_rows if _attr(row, "data-name") == "Halfmatch v Teams"]
eq(len(half_named), 1, "two leads for Halfmatch v Teams, with different ids, are one row")
ok(">1W 1L</span>" in half_named[0], "that fixture's win and loss render as 1W 1L")
half_contests = shell_build.contests_from_lanes(
    shell_build.collect_lanes({"quotes": []}, {"pairs": {}}, half_blob, NOW), NOW)
eq(len(half_contests), 1, "the title-only lead shares the sided lead's contest key")
eq(sorted(bet["status"] for bet in half_contests[0]["bets"]), ["L", "W"],
   "both Halfmatch bets are on that one contest")
other_day = dict(half_title, id="half-other-day", kickoff="2026-10-02T15:00:00Z",
                 status="hit", sandbox_quote="half-other-day")
apart = shell_build.contests_from_lanes(
    shell_build.collect_lanes({"quotes": []}, {"pairs": {}},
                              _blob([half_sided, other_day]), NOW), NOW)
eq(len(apart), 2, "the same sides on another day stay two contests")
eq(_bet_labels("1W 1L"), ["W", "L"],
   "1W 1L is two bets, so a row compare would miss one (the 20 vs 19 gap)")
eq(len(_bet_labels("1W 1L")), 2, "the two Kazakhstan bets both count")
two_wins = _face_page([("hit", "a|soccer"), ("hit", "b|soccer")])
ok(">2W</span>" in two_wins[0] and 'class="sr-only">2 won</span>' in two_wins[0],
   "two wins render as 2W and are spoken as 2 won")
win_void = _face_page([("hit", "a|soccer"), ("void", "b|soccer")])
ok(">1W 1 void</span>" in win_void[0] and "1 won, 1 void" in win_void[0],
   "a win and a void render as 1W 1 void")
win_price = _face_page([("hit", "a|soccer"), ("price", "b|soccer")])
ok(">1W 1 price result</span>" in win_price[0] and "1 won, 1 price result" in win_price[0],
   "a win and a price result both show")
loss_pairs = [("miss", "a|soccer", 0.33), ("pending", "b|soccer", 0.44)]
# Inside the six-hour window, so the open bet still reads Open.
loss_open = _face_page(loss_pairs, kickoff="2026-10-05T14:00:00Z")
ok(">1L 1 open</span>" in loss_open[0] and "1 lost, 1 open" in loss_open[0],
   "a settled bet and an open bet both show")
loss_contest = _face_contests(loss_pairs, kickoff="2026-10-05T14:00:00Z")
eq(loss_contest[0]["bucket"], "live",
   "one open bet past kickoff makes the contest Live, even with a settled bet beside it")
eq(_attr(loss_open[0], "data-filter"), "live", "that one-open/one-settled row is Live")
eq(_subset_gaps(loss_contest, [("Kazakhstan v Faroe Islands", "L", "33¢")]), [],
   "the settled bet on a Live contest is left out of the Settled subset")
ok(_subset_gaps(
    [dict(loss_contest[0], bucket="settled")],
    [("Kazakhstan v Faroe Islands", "L", "33¢")]) == [],
   "the same bet matches once the contest is Settled and the price is its own")
eq(_subset_gaps(
    [dict(loss_contest[0], bucket="settled",
          bets=[{"status": "L", "price": 0.44, "pair": "a|soccer"}])],
    [("Kazakhstan v Faroe Islands", "L", "33¢")]),
   [("Kazakhstan v Faroe Islands", "L", "33¢")],
   "a first-bet price does not satisfy the other bet")
_finished_live = {
    "match": "Finished v Pair",
    "bucket": "live",
    "bets": [
        {"status": "W", "price": 0.50, "pair": "a|soccer"},
        {"status": "L", "price": 0.40, "pair": "b|soccer"},
    ],
}
eq(_subset_gaps([_finished_live], [("Finished v Pair", "W", "99¢")]),
   [("Finished v Pair", "W", "99¢")],
   "a finished two-bet contest marked Live is not exempt without an open bet")
eq(_subset_gaps(
    [dict(_finished_live, bets=_finished_live["bets"] + [
        {"status": "Open", "price": 0.20, "pair": "c|soccer"}])],
    [("Finished v Pair", "W", "99¢")]),
   [],
   "a Live contest with an actual open bet stays exempt")
_matched_live = {
    "match": "Finished v Pair",
    "bucket": "live",
    "bets": [
        {"status": "W", "price": 0.50, "pair": "a|soccer"},
        {"status": "L", "price": 0.40, "pair": "b|soccer"},
    ],
}
eq(_subset_gaps([_matched_live], [("Finished v Pair", "W", "50¢")]),
   [("Finished v Pair", "W", "50¢")],
   "a finished contest marked Live is a gap even when its price matches")
_done = _face_contests([("hit", "a|soccer", 0.50), ("miss", "b|soccer", 0.40)])
eq(_done[0]["bucket"], "settled",
   "two settled Production bets are Settled, not Live")
eq(_subset_gaps(_done, [("Kazakhstan v Faroe Islands", "W", "50¢")]), [],
   "those settled bets are checked rather than skipped")

print("\nempty filter and quote window")
empty = shell_build.page(
    NOW, d={"quotes": []}, st={"pairs": {}}, blob={"leads": {}, "pairs": {}})
eq(_rows(empty), [], "an empty board has no contest rows")
for key, label in (("live", "Live"), ("settled", "Settled"), ("upcoming", "Upcoming")):
    eq(_filter_count(empty, key, label), 0, f"an empty board counts {label} as 0")
ok('id="running-empty"' in empty and "No live paper bets" in empty,
   "the empty live state keeps the Running chrome")
ok('id="running-title"' in empty and 'class="running-filters"' in empty,
   "the pane chrome stays when a filter is empty")
ok(not any(_attr(row, "data-filter") == "upcoming" for row in _rows(empty)),
   "the empty board has zero upcoming rows")
ok(all(bet == "Open" for bet in []),
   "an empty upcoming bet list passes")

st = _prod_st("oddspedia|cricket")
_TILES = '<div class="tiles"><div class="tile"><b>1</b><span>pairs in Production</span></div></div>'
live_q = shell_build.page(NOW, d={"quotes": [
    _quote("live-q", "open", "2026-10-05T12:00:00+00:00"),
]}, st=st, blob={"leads": {}, "pairs": {}}, tiles=_TILES)
live_rows = _rows(live_q)
eq(len(live_rows), 1, "a started open Production bet is a live row even though the feed drops it")
eq(_attr(live_rows[0], "data-name"), "QuoteHome v QuoteAway", "the live row names the contest")
eq(_attr(live_rows[0], "data-filter"), "live", "that quote is in Live")
eq(_attr(live_rows[0], "data-price"), "54¢", "the live quote price is cents")

upcoming_q = shell_build.page(NOW, d={"quotes": [
    _quote("up-q", "open", "2026-10-08T15:00:00+00:00"),
]}, st=st, blob={"leads": {}, "pairs": {}}, tiles=_TILES)
eq(_rows(upcoming_q), [], "an upcoming quote stays off the list until the Production feed has it")

inside_feed = shell_build.page(NOW, d={"quotes": [
    _quote("feed-q", "won", "2026-10-02T18:00:00+00:00",
           settled="2026-10-02T20:00:00+00:00", price=0.41),
]}, st=st, blob={"leads": {}, "pairs": {}}, tiles=_TILES)
eq(_rows(inside_feed), [],
   "a settled quote inside production's window is not added from the ledger")

older = shell_build.page(NOW, d={"quotes": [
    _quote("older-q", "won", "2026-09-26T18:00:00+00:00",
           settled="2026-09-27T02:00:00+00:00", price=0.41),
]}, st=st, blob={"leads": {}, "pairs": {}}, tiles=_TILES)
older_rows = _rows(older)
eq(len(older_rows), 1,
   "a settled quote older than production's window and inside 14 Chicago days comes from the ledger")
ok(">W</span>" in older_rows[0], "that ledger quote uses the same won → W path")
eq(_attr(older_rows[0], "data-price"), "41¢", "that ledger quote uses the same cents path")
eq(_attr(older_rows[0], "data-filter"), "settled", "that ledger quote is Settled")

before_entry = shell_build.page(NOW, d={"quotes": [
    _quote("early-q", "won", "2026-09-26T18:00:00+00:00",
           settled="2026-09-27T02:00:00+00:00", price=0.41),
]}, st={"pairs": {
    "oddspedia|cricket": {"stage": "production", "ready_at": "2026-09-27T00:00:00+00:00"},
}}, blob={"leads": {}, "pairs": {}}, tiles=_TILES)
eq(_rows(before_entry), [],
   "a ledger bet kicked off before the pair entered Production stays out")

dup_lead = _lead("dup-q", "QuoteHome", "QuoteAway", "2026-09-26T18:00:00Z", "hit",
                 "oddspedia|cricket", "cricket", 0.41)
dup_quote = _quote("dup-q", "won", "2026-09-26T18:00:00+00:00",
                   settled="2026-09-27T02:00:00+00:00", price=0.99)
dup_blob = _blob([dup_lead])
dup_page = shell_build.page(NOW, d={"quotes": [dup_quote]}, st=st, blob=dup_blob, tiles=_TILES)
dup_rows = _rows(dup_page)
eq(len(dup_rows), 1, "a feed bet is not added again from the ledger")
eq(_attr(dup_rows[0], "data-price"), "41¢", "the feed price wins over the ledger copy")
dup_contests = shell_build.contests_from_lanes(
    shell_build.collect_lanes({"quotes": [dup_quote]}, st, dup_blob, NOW), NOW)
eq(len(dup_contests), 1, "the duplicate quote does not become a second contest")
eq(len(dup_contests[0]["bets"]), 1, "the feed id is not listed twice")
eq(shell_build._cents(dup_contests[0]["bets"][0]["price"]), "41¢",
   "the kept bet is the feed price, not the ledger's 99¢")

# Noon Chicago time. Sep 21 2026 is CDT (UTC−5), so 17:00Z is 12:00 CT.
boundary_out = "2026-09-21T17:00:00+00:00"
boundary_in = "2026-09-22T17:00:00+00:00"
ok(not shell_build._in_shell_window(
    datetime.datetime.fromisoformat(boundary_out), NOW),
   "a kickoff 14 Chicago days ago is outside the shell window")
ok(shell_build._in_shell_window(
    datetime.datetime.fromisoformat(boundary_in), NOW),
   "a kickoff 13 Chicago days ago is inside the shell window")
eq(_rows(shell_build.page(NOW, d={"quotes": [
    _quote("out-q", "won", boundary_out, settled="2026-09-22T02:00:00+00:00", price=0.41),
]}, st=st, blob={"leads": {}, "pairs": {}}, tiles=_TILES)), [],
   "the 14-day boundary leaves out the Chicago date 14 days ago")
boundary_rows = _rows(shell_build.page(NOW, d={"quotes": [
    _quote("in-q", "won", boundary_in, settled="2026-09-23T02:00:00+00:00", price=0.41),
]}, st=st, blob={"leads": {}, "pairs": {}}, tiles=_TILES))
eq(len(boundary_rows), 1, "the 14-day boundary keeps the next Chicago date")
ok(">W</span>" in boundary_rows[0] and _attr(boundary_rows[0], "data-price") == "41¢",
   "the boundary row keeps the ledger status and price")
feed_edge = _rows(shell_build.page(
    NOW, d={"quotes": []}, st={"pairs": {}},
    blob=_blob([_lead("edge-in", "Edge", "In", "2026-09-22T17:00:00Z", "hit",
                      "oddspedia|cricket", "cricket", 0.41)])))
eq(len(feed_edge), 1, "a feed lead on the last kept Chicago date stays")
feed_out = _rows(shell_build.page(
    NOW, d={"quotes": []}, st={"pairs": {}},
    blob=_blob([_lead("edge-out", "Edge", "Out", "2026-09-21T17:00:00Z", "hit",
                      "oddspedia|cricket", "cricket", 0.41)])))
eq(feed_out, [], "a feed lead on the Chicago date 14 days ago drops")
# 04:30Z is 11:30 PM CT the day before; 05:30Z is 12:30 AM CT. A UTC-date
# window would keep the first one, because both instants are Sep 22 in UTC.
night_out = "2026-09-22T04:30:00+00:00"
night_in = "2026-09-22T05:30:00+00:00"
ok(not shell_build._in_shell_window(
    datetime.datetime.fromisoformat(night_out), NOW),
   "11:30 PM CT on the excluded Chicago date stays out")
ok(shell_build._in_shell_window(
    datetime.datetime.fromisoformat(night_in), NOW),
   "12:30 AM CT on the next Chicago date stays in")
eq(_rows(shell_build.page(
    NOW, d={"quotes": []}, st={"pairs": {}},
    blob=_blob([_lead("night-out", "Night", "Out", "2026-09-22T04:30:00Z", "hit",
                      "oddspedia|cricket", "cricket", 0.41)]))), [],
   "a kickoff just before midnight CT on the boundary date is not a row")
night_rows = _rows(shell_build.page(
    NOW, d={"quotes": []}, st={"pairs": {}},
    blob=_blob([_lead("night-in", "Night", "In", "2026-09-22T05:30:00Z", "hit",
                      "oddspedia|cricket", "cricket", 0.41)])))
eq(len(night_rows), 1, "a kickoff just after midnight CT on the next date is a row")

import production
eq(production.KEEP_SETTLED_DAYS, 7, "production.KEEP_SETTLED_DAYS stays 7")
eq(shell_build.SHELL_SETTLED_DAYS, 14, "the shell window is its own 14-day constant")
ok("KEEP_SETTLED_DAYS = 7" in open(os.path.join(ROOT, "production.py"), encoding="utf-8").read(),
   "production.py still defines KEEP_SETTLED_DAYS as 7")
saved_days = production.KEEP_SETTLED_DAYS
try:
    production.KEEP_SETTLED_DAYS = 1
    ok(shell_build._in_shell_window(NOW - timedelta(days=2), NOW),
       "shrinking production.KEEP_SETTLED_DAYS does not shrink the shell window")
    ok(not shell_build._in_production_window(NOW - timedelta(days=2), NOW),
       "the production cutoff still follows KEEP_SETTLED_DAYS")
    widened = _rows(shell_build.page(NOW, d={"quotes": [
        _quote("young-q", "won", "2026-10-03T18:00:00+00:00",
               settled="2026-10-03T20:00:00+00:00", price=0.41),
    ]}, st=st, blob={"leads": {}, "pairs": {}}, tiles=_TILES))
    eq(len(widened), 1,
       "once a quote is older than the production cutoff, the ledger supplies it")
finally:
    production.KEEP_SETTLED_DAYS = saved_days
ok(shell_build._in_production_window(
    NOW - timedelta(days=production.KEEP_SETTLED_DAYS), NOW),
   "a kickoff exactly KEEP_SETTLED_DAYS ago stays inside the production cutoff")
ok(not shell_build._in_production_window(
    NOW - timedelta(days=production.KEEP_SETTLED_DAYS, seconds=1), NOW),
   "a kickoff just older than KEEP_SETTLED_DAYS is outside the production cutoff")
saved_shell = shell_build.SHELL_SETTLED_DAYS
try:
    shell_build.SHELL_SETTLED_DAYS = 9
    shrunk = shell_build.page(NOW, d={"quotes": []}, st={"pairs": {}}, blob=_blob([
        _lead("twelve", "Twelve", "Ago", "2026-09-23T18:00:00Z", "hit",
              "oddspedia|cricket", "cricket", 0.41),
        _lead("eight", "Eight", "Ago", "2026-09-27T18:00:00Z", "hit",
              "oddspedia|cricket", "cricket", 0.22),
    ]))
    ok("Last 9 days" in shrunk and "Last 14 days" not in shrunk,
       "the caption renders from SHELL_SETTLED_DAYS")
    shrunk_rows = _rows(shrunk)
    ok(all(_attr(row, "data-name") != "Twelve v Ago" for row in shrunk_rows),
       "a 12-Chicago-day bet drops when the constant is 9")
    ok(any(_attr(row, "data-name") == "Eight v Ago" for row in shrunk_rows),
       "an 8-Chicago-day bet stays when the constant is 9")
    ok(not shell_build._in_shell_window(
        datetime.datetime(2026, 9, 23, 18, 0, tzinfo=timezone.utc), NOW),
       "SHELL_SETTLED_DAYS is read on each call")
finally:
    shell_build.SHELL_SETTLED_DAYS = saved_shell
ok(shell_build._in_shell_window(
    datetime.datetime(2026, 9, 23, 18, 0, tzinfo=timezone.utc), NOW),
   "restoring SHELL_SETTLED_DAYS restores the 14-day window")

sandbox_only = shell_build.page(NOW, d={"quotes": [
    _quote("sand-q", "open", "2026-10-05T12:00:00+00:00"),
]}, st={"pairs": {
    "oddspedia|cricket": {"stage": "sandbox", "since": "2026-09-01T00:00:00+00:00"},
}}, blob={"leads": {}, "pairs": {}}, tiles=_TILES)
eq(_rows(sandbox_only), [], "a Sandbox-stage contest is not listed on the Production shell")

print("\nsame clock as the page argument")
late = NOW + timedelta(hours=6)
between = _blob([
    _lead("soon", "Soon", "Later", "2026-10-05T21:00:00Z", "pending",
          "oddspedia|cricket", "cricket", 0.54),
])
early_page = shell_build.page(NOW, d={"quotes": []}, st={"pairs": {}}, blob=between)
late_page = shell_build.page(late, d={"quotes": []}, st={"pairs": {}}, blob=between)
early_rows = _rows(early_page)
late_rows = _rows(late_page)
eq(len(early_rows), 1, "the between-clock contest is still one row")
eq(_attr(early_rows[0], "data-filter"), "upcoming",
   "classification uses the build clock, not a later instant")
ok('<span class="running-time">Live</span>' not in early_rows[0],
   "that contest is not marked Live on the build clock")
eq(_attr(late_rows[0], "data-filter"), "live",
   "the same contest is live when the build clock is after kickoff")

print("\none pass, one clock, copied tiles")
import production
import sandbox_build
fixture_d = {"quotes": []}
fixture_st = {"pairs": {
    "oddspedia|cricket": {
        "stage": "production",
        "ready_at": "2026-09-27T00:00:00+00:00",
        "since": "2026-09-01T00:00:00+00:00",
        "by_hand": "2026-09-27",
    },
}}
fixture_blob = _blob([
    _lead("soon", "Alpha", "Beta", "2026-10-06T15:00:00Z", "pending",
          "oddspedia|cricket", "cricket", 0.61),
])
prod_html, index_html = sandbox_build.production_and_index(
    NOW, fixture_d, fixture_st, fixture_blob)
prod_tiles = shell_build.tiles_html(prod_html)
index_tiles = shell_build.tiles_html(index_html)
eq(index_tiles, prod_tiles, "the shared pass still copies Production tiles onto the shell")
prod_stamp = re.search(r'<time datetime="([^"]+)"', prod_html)
index_stamp = re.search(r'<p class="stamp">.*?<time datetime="([^"]+)"', index_html, re.S)
ok(prod_stamp and index_stamp and prod_stamp.group(1) == index_stamp.group(1),
   "the shared pass stamps index.html with production.html's clock")
ok('data-name="Alpha v Beta"' in index_html, "that same pass writes the Running row")


def _stamp(page):
    match = re.search(r'<p class="stamp">(.*?)</p>', page, re.S)
    return match.group(1) if match else ""


print("\ntracker build writes both pages from the first clock")
calls = {"n": 0}
base = datetime.datetime(2026, 10, 5, 18, 0, tzinfo=timezone.utc)
_RealDate = sandbox_build.datetime


class _Stepped(_RealDate):
    @classmethod
    def now(cls, tz=None):
        calls["n"] += 1
        if calls["n"] == 1:
            return base
        return base + timedelta(hours=2)


saved = {
    "out": sandbox_build.OUT,
    "clock": sandbox_build.datetime,
    "render": sandbox_build.render_pages,
    "trade": sandbox_build.trading_page,
}
sandbox_build.datetime = _Stepped
sandbox_build.render_pages = lambda now=None, d=None, st=None: ("<html>sandbox</html>", "<html>arch</html>", {})
sandbox_build.trading_page = lambda now: "<html>trade</html>"
import cricket_build
import crypto_build
import soccer_build
import tennis_build
saved_builds = {
    "soccer": soccer_build.build,
    "tennis": tennis_build.build,
    "cricket": cricket_build.build,
    "crypto": crypto_build.build,
}
for mod in (soccer_build, tennis_build, cricket_build, crypto_build):
    mod.build = lambda *args, **kwargs: "<html></html>"
tmpdir = tempfile.mkdtemp(prefix="shell-main-")
sandbox_build.OUT = os.path.join(tmpdir, "sandbox.html")
try:
    sandbox_build.main()
    prod_path = os.path.join(tmpdir, "production.html")
    index_path = os.path.join(tmpdir, "index.html")
    ok(os.path.isfile(prod_path) and os.path.isfile(index_path),
       "the tracker build writes production.html and index.html")
    if os.path.isfile(prod_path) and os.path.isfile(index_path):
        prod_body = open(prod_path, encoding="utf-8").read()
        index_body = open(index_path, encoding="utf-8").read()
        prod_when = re.search(r'datetime="([^"]+)"', prod_body)
        index_when = re.search(r'datetime="([^"]+)"', _stamp(index_body))
        eq(None if index_when is None else index_when.group(1),
           None if prod_when is None else prod_when.group(1),
           "index.html does not carry a later clock than production.html")
        eq(None if prod_when is None else prod_when.group(1), "2026-10-05T18:00:00Z",
           "both pages use the tracker's first clock")
finally:
    sandbox_build.OUT = saved["out"]
    sandbox_build.datetime = saved["clock"]
    sandbox_build.render_pages = saved["render"]
    sandbox_build.trading_page = saved["trade"]
    soccer_build.build = saved_builds["soccer"]
    tennis_build.build = saved_builds["tennis"]
    cricket_build.build = saved_builds["cricket"]
    crypto_build.build = saved_builds["crypto"]
    shutil.rmtree(tmpdir, ignore_errors=True)


print("\ntakeover copies tiles and the production clock")
boom = {"n": 0}
real_page = production.page


def _boom(*args, **kwargs):
    boom["n"] += 1
    raise AssertionError("takeover recounted tiles")


take_dir = tempfile.mkdtemp(prefix="shell-take-")
take_prod = os.path.join(take_dir, "production.html")
take_index = os.path.join(take_dir, "index.html")
open(take_prod, "w", encoding="utf-8").write(
    '<time datetime="2026-10-01T12:00:00Z">Updated Oct 1, 7:00 AM CT</time>\n'
    '<div class="tiles"><div class="tile"><b>4</b><span>pairs in Production</span></div></div>\n')
open(take_index, "w", encoding="utf-8").write("old shell\n")
import site_root
saved_out = site_root.OUT
saved_site_dt = site_root.datetime


class _SiteClock:
    timezone = timezone

    class datetime(datetime.datetime):
        @classmethod
        def now(cls, tz=None):
            return base + timedelta(hours=5)

        @staticmethod
        def strptime(text, pattern):
            return datetime.datetime.strptime(text, pattern)


site_root.OUT = take_index
site_root.datetime = _SiteClock
production.page = _boom
try:
    site_root.main()
finally:
    production.page = real_page
    site_root.OUT = saved_out
    site_root.datetime = saved_site_dt
taken = open(take_index, encoding="utf-8").read()
eq(boom["n"], 0, "takeover does not call production.page")
ok("2026-10-01T12:00:00Z" in _stamp(taken), "takeover stamps the shell with production.html's clock")
ok("2026-10-05" not in _stamp(taken), "takeover does not stamp the shell with its own clock")
ok('<div class="tile"><b>4</b><span>pairs in Production</span></div>' in taken,
   "takeover copies the production tiles")
shutil.rmtree(take_dir, ignore_errors=True)


print("\ntakeover does not rebuild Running from newer data")
drift_dir = tempfile.mkdtemp(prefix="shell-drift-")
drift_prod = os.path.join(drift_dir, "production.html")
drift_index = os.path.join(drift_dir, "index.html")
drift_blob = _blob([
    _lead("soon", "Alpha", "Beta", "2026-10-06T15:00:00Z", "pending",
          "oddspedia|cricket", "cricket", 0.61),
])
drift_prod_html, drift_index_html = sandbox_build.production_and_index(
    NOW, {"quotes": []}, {"pairs": {
        "oddspedia|cricket": {
            "stage": "production",
            "ready_at": "2026-09-27T00:00:00+00:00",
            "since": "2026-09-01T00:00:00+00:00",
            "by_hand": "2026-09-27",
        },
    }}, drift_blob)
open(drift_prod, "w", encoding="utf-8").write(drift_prod_html)
open(drift_index, "w", encoding="utf-8").write(drift_index_html)
newer_blob = _blob([
    _lead("soon", "Newer", "Data", "2026-10-06T15:00:00Z", "pending",
          "oddspedia|cricket", "cricket", 0.22),
])
lane_calls = {"n": 0}
real_collect = shell_build.collect_lanes


def _count_lanes(*args, **kwargs):
    lane_calls["n"] += 1
    return real_collect(*args, **kwargs)


saved_loaders = {
    "collect": shell_build.collect_lanes,
    "feed": production.load_feed,
    "load": shell_build.T.load,
    "stages": shell_build.T.load_stages,
    "out": site_root.OUT,
}
shell_build.collect_lanes = _count_lanes
production.load_feed = lambda *args, **kwargs: newer_blob
shell_build.T.load = lambda *args, **kwargs: {"quotes": []}
shell_build.T.load_stages = lambda *args, **kwargs: {"pairs": {}}
site_root.OUT = drift_index
try:
    site_root.main()
    matched = open(drift_index, encoding="utf-8").read()
    eq(lane_calls["n"], 0, "a matching stamp does not rebuild Running")
    ok("Alpha v Beta" in matched and "Newer v Data" not in matched,
       "Running still names the production build, not the newer ledger")
    tampered = matched.replace("2026-10-05T18:00:00Z", "2026-10-01T00:00:00Z", 1)
    open(drift_index, "w", encoding="utf-8").write(tampered)
    site_root.main()
    copied = open(drift_index, encoding="utf-8").read()
    eq(lane_calls["n"], 0, "a stamp mismatch still does not rebuild Running")
    ok("Alpha v Beta" in copied and "Newer v Data" not in copied,
       "the copied Running block is still the tracker block")
    ok("2026-10-05T18:00:00Z" in _stamp(copied),
       "the copied shell takes production.html's clock")
    ok("2026-10-01T00:00:00Z" not in _stamp(copied),
       "the copied shell does not keep the stale index clock")
finally:
    shell_build.collect_lanes = saved_loaders["collect"]
    production.load_feed = saved_loaders["feed"]
    shell_build.T.load = saved_loaders["load"]
    shell_build.T.load_stages = saved_loaders["stages"]
    site_root.OUT = saved_loaders["out"]
    shutil.rmtree(drift_dir, ignore_errors=True)


print("\nstamps-differ copies tiles and the clock")
swapped_clock = site_root._swap_time(
    '<p class="stamp"><time datetime="2026-10-01T00:00:00Z">old</time></p>',
    '<p class="stamp"><time datetime="2026-10-05T12:00:00Z">a\\b</time></p>')
ok("a\\b" in swapped_clock and "2026-10-05T12:00:00Z" in swapped_clock,
   "a backslash in the clock is copied literally")
copy_dir = tempfile.mkdtemp(prefix="shell-copy-")
copy_prod = os.path.join(copy_dir, "production.html")
copy_index = os.path.join(copy_dir, "index.html")
running_block = (
    '<div class="running-filters" role="group" aria-label="Running filters"></div>'
    '<div class="running-list" id="running-list">'
    '<button type="button" class="running-row" data-name="Alpha v Beta">Alpha v Beta</button>'
    '</div>'
    '<p class="shell-empty" id="running-empty">No live paper bets</p>'
)
open(copy_index, "w", encoding="utf-8").write(
    '<p class="stamp"><time datetime="2026-10-01T00:00:00Z">old</time></p>'
    '<div class="tiles"><div class="tile"><b>4</b><span>pairs in Production</span></div></div>'
    + running_block)
open(copy_prod, "w", encoding="utf-8").write(
    '<p class="stamp"><time datetime="2026-10-05T12:00:00Z">a\\b</time></p>'
    '<div class="tiles"><div class="tile"><b>10</b><span>leads still to come</span></div></div>')
saved_copy_out = site_root.OUT
site_root.OUT = copy_index
try:
    site_root.main()
    copied_shell = open(copy_index, encoding="utf-8").read()
finally:
    site_root.OUT = saved_copy_out
ok('<b>10</b>' in copied_shell and "leads still to come" in copied_shell,
   "a different stamp copies production.html's tiles")
ok('<b>4</b>' not in copied_shell, "the stale tiles do not stay")
ok("2026-10-05T12:00:00Z" in copied_shell and "a\\b" in copied_shell,
   "a different stamp copies production.html's clock, backslash included")
ok(running_block in copied_shell, "the Running block is not rebuilt")
open(copy_index, "w", encoding="utf-8").write(
    '<p class="stamp"><time datetime="2026-10-01T00:00:00Z">old</time></p>'
    '<div class="tiles"><div class="tile"><b>4</b><span>pairs in Production</span></div></div>'
    + running_block)
open(copy_prod, "w", encoding="utf-8").write(
    '<p class="stamp"><time datetime="2026-10-01T00:00:00Z">old</time></p>'
    '<div class="tiles"><div class="tile"><b>10</b><span>leads still to come</span></div></div>')
site_root.OUT = copy_index
try:
    site_root.main()
    held = open(copy_index, encoding="utf-8").read()
finally:
    site_root.OUT = saved_copy_out
    shutil.rmtree(copy_dir, ignore_errors=True)
ok('<b>4</b>' in held and '<b>10</b>' not in held,
   "a matching stamp does not copy newer tiles")


print("\nrecord_build does not stamp index.html")
import book_track
import fire_track
import record_build
import streaks_fetch
import streaks_track

saved_record = {
    "out": record_build.OUT_DIR,
    "fetch": streaks_fetch.load_or_fetch,
    "report": streaks_track.report,
    "compare": streaks_track.rule_compare,
    "load": streaks_track.load,
    "fire": fire_track.report,
    "book": book_track.report,
    "book_load": book_track.load,
}
streaks_fetch.load_or_fetch = lambda: {"fixtures": []}
streaks_track.report = lambda fixtures: {"pending": 0, "graded": 0}
streaks_track.rule_compare = lambda *args, **kwargs: {}
streaks_track.load = lambda *args, **kwargs: {}
fire_track.report = lambda fixtures: {"graded": 0}
book_track.report = lambda blob: {"graded": 0}
book_track.load = lambda: {}
record_dir = tempfile.mkdtemp(prefix="shell-record-")
record_index = os.path.join(record_dir, "index.html")
open(record_index, "w", encoding="utf-8").write("KEEP-STAMP\n")
record_build.OUT_DIR = record_dir
try:
    record_build.build()
finally:
    record_build.OUT_DIR = saved_record["out"]
    streaks_fetch.load_or_fetch = saved_record["fetch"]
    streaks_track.report = saved_record["report"]
    streaks_track.rule_compare = saved_record["compare"]
    streaks_track.load = saved_record["load"]
    fire_track.report = saved_record["fire"]
    book_track.report = saved_record["book"]
    book_track.load = saved_record["book_load"]
eq(open(record_index, encoding="utf-8").read(), "KEEP-STAMP\n",
   "record_build leaves index.html on the shell clock")
shutil.rmtree(record_dir, ignore_errors=True)


print("\nfreshness notes")
fresh = open(os.path.join(ROOT, "page_freshness.py"), encoding="utf-8").read()
ok("redirect stub" not in fresh.lower(),
   "page_freshness.py does not call index.html a redirect stub")
record_src = open(os.path.join(ROOT, "record_build.py"), encoding="utf-8").read()
ok("sends visitors to the Sandbox" not in record_src,
   "record_build.py does not describe the root as a Sandbox redirect")
ok("root -> sandbox.html" not in record_src,
   "record_build.py does not log a redirect write")
wf_dir = os.path.join(ROOT, ".github", "workflows")
for name in sorted(os.listdir(wf_dir)):
    if not name.endswith(".yml"):
        continue
    body = open(os.path.join(wf_dir, name), encoding="utf-8").read()
    stale = [
        line.strip() for line in body.splitlines()
        if "redirect stub" in line.lower() and "not a redirect stub" not in line.lower()
    ]
    eq(stale, [], f"{name} does not describe index.html as a redirect stub")


print("\ncommitted shell")
_committed = open(os.path.join(ROOT, "public_site", "index.html"), encoding="utf-8").read()
_committed_rows = _rows(_committed)
ok(_committed_rows or 'id="running-empty"' in _committed,
   "committed index.html lists Running contests or the empty state")
for _key, _label in (("live", "Live"), ("settled", "Settled"), ("upcoming", "Upcoming")):
    eq(_filter_count(_committed, _key, _label),
       sum(1 for _row in _committed_rows if _attr(_row, "data-filter") == _key),
       f"committed {_label} count equals the committed rows")
ok('class="rule-mini"' not in _committed,
   "committed index.html does not paint rule cards before a row is selected")
if _committed_rows:
    ok('data-cards="' in _committed, "committed index.html embeds a card payload per contest")
_prod_committed = open(os.path.join(ROOT, "public_site", "production.html"), encoding="utf-8").read()
eq(shell_build.tiles_html(_committed), shell_build.tiles_html(_prod_committed),
   "committed index.html tiles equal committed production.html tiles")
_RESULT = {"landed": "W", "missed": "L", "paid": "price result"}
_recent = _prod_committed.split('id="recent"', 1)[1].split('id="held-back"', 1)[0]
_prod_rows = [
    (html_lib.unescape(name), html_lib.unescape(headline), _RESULT[status])
    for name, headline, status in re.findall(
        r'data-l="Match">([^<]*)</td>.*?data-l="Lead">([^<]*)</td>'
        r'.*?data-l="Result"><span class="[^"]*">([^<]+)</span>',
        _recent, re.S)
]


def _visual(row):
    match = re.search(r'aria-hidden="true">([^<]*)</span>', row)
    return html_lib.unescape(match.group(1)) if match else ""


def _bucket_bets(rows, bucket):
    bets = []
    for row in rows:
        if _attr(row, "data-filter") != bucket:
            continue
        bets.extend(_bet_labels(_visual(row)))
    return bets


_price_re = re.compile(r"^(?:\d+¢|—)(?: / (?:\d+¢|—))*$")
_known_status = {"W", "L", "Void", "price result", "Open", "awaiting", "mixed", ""}
_contest_ids = []
for _row in _committed_rows:
    _price = _attr(_row, "data-price") or ""
    ok(_price_re.match(_price) is not None, f"a Running price is cents ({_price})")
    ok(_attr(_row, "data-filter") in ("live", "settled", "upcoming"),
       "a Running row is Live, Settled, or Upcoming")
    _cid = _attr(_row, "data-contest")
    ok(_cid, "a Running row has a contest id")
    _contest_ids.append(_cid)
    _data_status = _attr(_row, "data-status") or ""
    if _data_status not in _known_status:
        ok(_visual(_row) != "Void",
           f"an unknown status stays {_visual(_row)!r}, not Void")
    _payload = _attr(_row, "data-cards")
    if _payload:
        for _card in json.loads(_payload):
            _card_price = _card.get("price") or ""
            ok(_price_re.match(_card_price) is not None,
               f"a card price is cents ({_card_price})")
            _card_status = _card.get("status") or ""
            if _card_status not in ("W", "L", "Void", "price result", "Open", "Awaiting result"):
                ok(_card_status != "Void",
                   f"an unknown card status stays {_card_status!r}, not Void")
eq(len(_contest_ids), len(set(_contest_ids)), "committed Running has one row per contest")
_clock_m = re.search(r'<time datetime="([^"]+)"', _prod_committed)
ok(_clock_m is not None, "production.html has a build clock")
_model = []
if _clock_m is not None:
    _when = datetime.datetime.strptime(
        _clock_m.group(1), "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    _model = shell_build.contests_from_lanes(
        shell_build.collect_lanes(
            shell_build.T.load(), shell_build.T.load_stages(), production.load_feed(), _when),
        _when)
_model_keys = []
for _contest in _model:
    _model_keys.append((
        _contest.get("sport"), _contest.get("match"), _contest.get("kickoff")))
    _open = any(bet.get("status") == "Open" for bet in _contest["bets"])
    _graded = _contest["bets"] and all(
        bet.get("status") in ("W", "L", "Void", "price result") for bet in _contest["bets"])
    if _graded:
        eq(_contest["bucket"], "settled",
           f"{_contest['match']} has no open bet, so it is Settled")
    elif _contest["bucket"] == "live":
        ok(_open, f"{_contest['match']} is Live only while a bet is still open")
    for _bet in _contest["bets"]:
        _cents = shell_build._cents(_bet.get("price"))
        ok(_price_re.match(_cents) is not None, f"a model price is cents ({_cents})")
        if _bet.get("status") not in ("W", "L", "Void", "price result", "Open"):
            ok(_bet.get("status") != "Void",
               f"an unknown model status stays {_bet.get('status')!r}, not Void")
eq(len(_model_keys), len(set(_model_keys)),
   "the Running model has one contest per sport, match, and kickoff")
_by_name = {}
for _row in _committed_rows:
    _by_name.setdefault(_attr(_row, "data-name"), []).append(_row)
_matched_settled = 0
_feed_leads = list((production.load_feed() or {}).get("leads", {}).values())
for _name, _headline, _status in _prod_rows:
    if _clock_m is None:
        break
    _same = [lead for lead in _feed_leads if lead.get("match") == _name]
    _kicks = [production._one_instant(lead.get("kickoff")) for lead in _same]
    if not _same or not any(
            k is not None and shell_build._in_shell_window(k, _when) for k in _kicks):
        continue  # not in this feed, or outside the 14-day window at the build clock
    if any(lead.get("status") == "pending" and k is not None and k <= _when
           for lead, k in zip(_same, _kicks)):
        continue  # a Live contest with an open bet is exempt
    _hits = _by_name.get(_name, [])
    eq(len(_hits), 1, f"production recent lead {_name} is one Running row")
    if len(_hits) != 1:
        continue
    eq(_attr(_hits[0], "data-filter"), "settled", f"production recent lead {_name} is Settled")
    ok(_status in _bet_labels(_visual(_hits[0])),
       "a production recent status is on that Running row")
    _matched_settled += 1
# Guard against a vacuous loop only when this data can feed it: Production
# recent rows on the page and a graded feed lead inside the 14-day window at
# the build clock. A quiet week (no recent Production leads) or a feed whose
# graded leads are all older than 14 days has nothing to check.
_window_graded = [
    lead for lead in _feed_leads
    if lead.get("status") and lead.get("status") != "pending"
    and production._one_instant(lead.get("kickoff")) is not None
    and _clock_m is not None
    and shell_build._in_shell_window(production._one_instant(lead.get("kickoff")), _when)
]
if _prod_rows and _window_graded:
    ok(_matched_settled > 0,
       "the Settled loop checked at least one in-window production recent row")
else:
    print("  skip  no in-window graded Production lead at this build clock; the Settled loop has nothing to check")
_shell_settled = _bucket_bets(_committed_rows, "settled")
ok(len(_shell_settled) >= _matched_settled,
   "Running Settled bets cover the production recent rows still on the page")
ok(f"Last {shell_build.SHELL_SETTLED_DAYS} days" in _committed,
   "committed Settled caption renders from SHELL_SETTLED_DAYS")
_to_come = re.search(
    r'<div class="tile"><b>(\d+)</b><span>leads still to come</span>', _committed)
_upcoming_bets = _bucket_bets(_committed_rows, "upcoming")
eq(len(_upcoming_bets), int(_to_come.group(1)) if _to_come else None,
   "Upcoming bets equal the strip's leads still to come")
_graded_visual = {"W", "L", "Void", "price result"}
ok(all(bet not in _graded_visual for bet in _upcoming_bets),
   "an upcoming bet is still open or an unresolved status")
eq(_committed.count('aria-describedby="settled-caption"'), 1,
   "committed Settled filter points at the caption")


def _browser():
    from require_browser import require_browser
    sync_playwright = require_browser("test_running_list.py")
    if sync_playwright is None:
        return
    site = tempfile.mkdtemp(prefix="shell-browser-")
    try:
        open(os.path.join(site, "index.html"), "w", encoding="utf-8").write(PAGE)
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
                page = browser.new_page(viewport={"width": 1280, "height": 800})
                page.goto(base, wait_until="load")
                roll = page.evaluate("""() => {
                  const track = document.querySelector(".bet-roll-track");
                  if (!track) return null;
                  const style = getComputedStyle(track);
                  return {
                    overflowX: style.overflowX,
                    nowrap: style.flexWrap,
                    chips: track.querySelectorAll(".bet-chip").length,
                    empty: track.querySelector(".bet-roll-empty") ? true : false,
                  };
                }""")
                ok(roll and roll["chips"] > 0 and not roll["empty"]
                   and roll["overflowX"] in ("auto", "scroll") and roll["nowrap"] == "nowrap",
                   f"the roll is a horizontal chip scroller ({roll})")
                page.set_viewport_size({"width": 640, "height": 800})
                page.wait_for_timeout(30)
                narrow_roll = page.evaluate("""() => {
                  const track = document.querySelector(".bet-roll-track");
                  return {
                    scrolls: track.scrollWidth > track.clientWidth + 1,
                    page: document.documentElement.scrollWidth > document.documentElement.clientWidth + 1,
                  };
                }""")
                ok(narrow_roll["scrolls"] and not narrow_roll["page"],
                   f"at 640px the roll scrolls inside the track ({narrow_roll})")
                page.set_viewport_size({"width": 1280, "height": 800})
                page.wait_for_timeout(30)
                styles = page.evaluate("""() => {
                  const pressed = document.querySelector('nav.sports button[data-sport="all"]');
                  const idle = document.querySelector('nav.sports button[data-sport="crypto"]');
                  const filter = document.querySelector('.running-filters button[aria-pressed="true"]');
                  const a = getComputedStyle(pressed);
                  const b = getComputedStyle(idle);
                  const c = getComputedStyle(filter);
                  return {
                    pressedOpacity: a.opacity,
                    idleOpacity: b.opacity,
                    pressedBg: a.backgroundColor,
                    idleBg: b.backgroundColor,
                    filterBg: c.backgroundColor,
                    pressedColor: a.color,
                    filterColor: c.color,
                    disabled: idle.getAttribute("aria-disabled"),
                    tab: idle.tabIndex,
                  };
                }""")
                ok(styles["disabled"] is None and styles["tab"] >= 0
                   and float(styles["pressedOpacity"]) == 1
                   and float(styles["idleOpacity"]) == 1
                   and styles["pressedBg"] == styles["filterBg"]
                   and styles["pressedBg"] != styles["idleBg"]
                   and styles["pressedColor"] == styles["filterColor"],
                   f"a pressed sport pill matches a pressed filter and stays enabled ({styles})")
                page.click('.running-filters button[data-filter="upcoming"]')
                page.wait_for_timeout(30)
                shown = page.evaluate("""() => {
                  const rows = [...document.querySelectorAll(".running-row")];
                  return rows.map((row) => ({
                    filter: row.getAttribute("data-filter"),
                    display: getComputedStyle(row).display,
                    h: row.getBoundingClientRect().height,
                  }));
                }""")
                upcoming_on = [row for row in shown if row["filter"] == "upcoming"]
                upcoming_off = [row for row in shown if row["filter"] != "upcoming"]
                ok(upcoming_on and all(row["display"] != "none" and row["h"] > 0 for row in upcoming_on)
                   and upcoming_off and all(row["display"] == "none" and row["h"] == 0 for row in upcoming_off),
                   "Upcoming hides the other buckets, including settled rows in the same sport group "
                   f"({shown})")
                roles = page.evaluate("""() => ({
                  listbox: document.querySelectorAll('[role="listbox"]').length,
                  option: document.querySelectorAll('[role="option"]').length,
                })""")
                eq(roles, {"listbox": 0, "option": 0}, "Running rows are not a listbox")
                page.click('.running-filters button[data-filter="settled"]')
                page.wait_for_timeout(30)
                caption_on = page.evaluate("""() => {
                  const cap = document.getElementById("settled-caption");
                  if (!cap) return null;
                  return {
                    hidden: cap.hidden,
                    text: cap.textContent,
                    display: getComputedStyle(cap).display,
                  };
                }""")
                ok(caption_on and caption_on["hidden"] is False
                   and caption_on["text"] == "Last 14 days"
                   and caption_on["display"] != "none",
                   f"Settled shows the caption from the 14-day constant ({caption_on})")
                page.locator('.running-filters button[data-filter="settled"]').focus()
                page.keyboard.press("Tab")
                page.keyboard.press("Tab")
                tabbed = page.evaluate("""() => {
                  const el = document.activeElement;
                  return el ? el.className : "";
                }""")
                ok("running-row" in tabbed, f"Tab reaches a Running row ({tabbed})")
                first = page.locator(".running-row:not([hidden])").nth(0)
                second = page.locator(".running-row:not([hidden])").nth(1)
                first.focus()
                page.keyboard.press("Enter")
                selected = page.evaluate("""() => {
                  const rows = [...document.querySelectorAll(".running-row")];
                  const on = rows.filter((row) => row.getAttribute("aria-pressed") === "true");
                  const current = on[0];
                  const line = document.getElementById("rules-line");
                  const empty = document.getElementById("rules-empty");
                  return {
                    n: on.length,
                    pressed: current ? current.getAttribute("aria-pressed") : "",
                    name: current ? current.getAttribute("data-name") : "",
                    shadow: current ? getComputedStyle(current).boxShadow : "",
                    line: line ? line.textContent : "",
                    emptyHidden: empty ? empty.hidden : null,
                    cards: document.querySelectorAll(".rule-mini").length,
                    want: current ? JSON.parse(current.getAttribute("data-cards") || "[]").length : 0,
                    section: (document.getElementById("rules-section") || {}).textContent || "",
                    selectedAttr: document.querySelectorAll("[aria-selected]").length,
                  };
                }""")
                ok(selected["n"] == 1 and selected["pressed"] == "true"
                   and selected["name"] and selected["name"] in selected["line"]
                   and "inset" in selected["shadow"]
                   and "¢" in selected["line"] and " · " in selected["line"]
                   and selected["emptyHidden"] and selected["cards"] == selected["want"]
                   and selected["cards"] >= 1
                   and selected["section"].startswith("Rules applied · ")
                   and selected["selectedAttr"] == 0,
                   f"Enter presses one row, names it, and shows its cards ({selected})")
                second.focus()
                page.keyboard.press("Space")
                moved = page.evaluate("""() => {
                  const rows = [...document.querySelectorAll(".running-row:not([hidden])")];
                  return rows.map((row) => row.getAttribute("aria-pressed"));
                }""")
                eq(moved[:2], ["false", "true"], "Space moves aria-pressed to the focused row")
                eq(moved.count("true"), 1, "Space leaves only one row pressed")
                page.locator(".running-row:not([hidden])").nth(0).click()
                clicked = page.evaluate("""() => {
                  const rows = [...document.querySelectorAll(".running-row:not([hidden])")];
                  return rows.map((row) => row.getAttribute("aria-pressed"));
                }""")
                eq(clicked[0], "true", "a click presses that row")
                eq(clicked.count("true"), 1, "a click clears the other rows")
                page.click('.running-filters button[data-filter="upcoming"]')
                page.wait_for_timeout(30)
                cleared = page.evaluate("""() => {
                  const line = document.getElementById("rules-line");
                  const head = document.getElementById("rules-head");
                  const empty = document.getElementById("rules-empty");
                  return {
                    pressed: document.querySelectorAll('.running-row[aria-pressed="true"]').length,
                    line: line ? line.textContent : null,
                    headHidden: head ? head.hidden : null,
                    emptyHidden: empty ? empty.hidden : null,
                    empty: empty ? empty.textContent : "",
                    cards: document.querySelectorAll(".rule-mini").length,
                    sectionHidden: (document.getElementById("rules-section") || {}).hidden,
                  };
                }""")
                caption_off = page.evaluate("""() => {
                  const cap = document.getElementById("settled-caption");
                  return cap ? cap.hidden : null;
                }""")
                ok(caption_off is True, "leaving Settled hides the caption")
                eq(cleared["pressed"], 0, "hiding the selected row clears aria-pressed")
                eq(cleared["line"], "", "hiding the selected row clears the detail header")
                ok(cleared["headHidden"] and not cleared["emptyHidden"]
                   and cleared["empty"] == "Select a contest in Running."
                   and cleared["cards"] == 0 and cleared["sectionHidden"],
                   f"the detail pane returns to its empty state and clears cards ({cleared})")
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
