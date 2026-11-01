#!/usr/bin/env python3
"""cfb_home_dog_x4 (2026-11-01, Olu): the college football home underdog, 10-25c, sell everything at 4x. The picker
(home / away / neutral / no ESPN match / ESPN down), the lane's config, and how the nfl page shows it beside the
blind baseline."""
import datetime as dt

import cfb_home
import chaos_build as CB
import chaos_lanes
import chaos_replay as C

FAILS = []


def check(label, got, want):
    ok = got == want
    print(f"  {'ok  ' if ok else 'FAIL'} {label}" + ("" if ok else f" (got {got!r}, want {want!r})"))
    if not ok:
        FAILS.append(label)


def game(home, away, neutral=False, abbr=("H", "A")):
    def team(name, short, ab):
        return dict(displayName=name, shortDisplayName=short, location=short, name=name.split()[-1], abbreviation=ab)
    return dict(id="1", competitions=[dict(neutralSite=neutral, competitors=[
        dict(homeAway="home", team=team(*home, abbr[0])), dict(homeAway="away", team=team(*away, abbr[1]))])])


EV = "KXNCAAFGAME-26NOV07OHSTWIS"
BOARD = [game(("Ohio State Buckeyes", "Ohio State"), ("Wisconsin Badgers", "Wisconsin"), abbr=("OSU", "WIS"))]


def ctx(asks, names=("Ohio St.", "Wisconsin"), event=EV):
    t = [event + "-OHST", event + "-WIS"]
    return dict(event=event, tickers=t, markets={t[0]: dict(yes_sub_title=names[0]), t[1]: dict(yes_sub_title=names[1])},
                entry_view=lambda tk, s: dict(ask=asks[tk[len(event) + 1:]], bid=asks[tk[len(event) + 1:]] - 0.01))


def pick(board, asks, **kw):
    return cfb_home.home_dog_picker(lambda d: board)(ctx(asks, **kw))


print("names")
check("St. -> State, & -> and, letters only", (cfb_home.norm("Ohio St."), cfb_home.norm("Texas A&M"), cfb_home.norm("Miami (OH)")),
      ("ohiostate", "texasaandm", "miamioh"))

check("accents are dropped and the listed aliases map to ESPN's names (San José, UL Monroe, UT Martin, UAlbany, SE Louisiana)",
      [cfb_home.match_game(n, [game((a, a.split()[0] + " " + a.split()[1]), ("Other Team", "Other"))]) is not None
       for n, a in ((["San Jose St.", "Other"], "San José State Spartans"), (["Louisiana-Monroe", "Other"], "UL Monroe Warhawks"),
                    (["Tennessee-Martin", "Other"], "UT Martin Skyhawks"), (["University at Albany", "Other"], "UAlbany Great Danes"),
                    (["Southeastern Louisiana", "Other"], "SE Louisiana Lions"))], [True] * 5)

print("\nthe picker")
b2 = [game(("Wisconsin Badgers", "Wisconsin"), ("Ohio State Buckeyes", "Ohio State"), abbr=("WIS", "OSU"))]
check("the HOME underdog (Wisconsin at home, 20c) is picked", pick(b2, {"OHST": 0.80, "WIS": 0.20}), [(EV + "-WIS", "yes")])
check("the AWAY underdog (Wisconsin away, 20c) is not", pick(BOARD, {"OHST": 0.80, "WIS": 0.20}), [])
neutral = game(("Wisconsin Badgers", "Wisconsin"), ("Ohio State Buckeyes", "Ohio State"), neutral=True)
check("a neutral-site game buys neither side", (pick([neutral], {"OHST": 0.80, "WIS": 0.20}), pick([neutral], {"OHST": 0.20, "WIS": 0.80})), ([], []))
check("the band is 10-25c: 26c and 9c are not bought", (pick(b2, {"OHST": 0.74, "WIS": 0.26}), pick(b2, {"OHST": 0.91, "WIS": 0.09})), ([], []))
check("the band edges 10c and 25c are bought", (pick(b2, {"OHST": 0.90, "WIS": 0.10}), pick(b2, {"OHST": 0.75, "WIS": 0.25})),
      ([(EV + "-WIS", "yes")], [(EV + "-WIS", "yes")]))
check("a wide spread (over 3c) is not bought", cfb_home.home_dog_picker(lambda d: b2)(dict(ctx({"OHST": 0.8, "WIS": 0.2}),
      entry_view=lambda tk, s: dict(ask=0.2, bid=0.10))), [])
check("the other team's 'Ohio St.' matches 'Ohio State Buckeyes' at home too",
      pick(BOARD, {"OHST": 0.20, "WIS": 0.80}), [(EV + "-OHST", "yes")])

print("\nno ESPN match is a skip with a note, never a guess")
for label, board in (("an empty scoreboard", []), ("a scoreboard without the game", [game(("Iowa Hawkeyes", "Iowa"), ("Purdue Boilermakers", "Purdue"))])):
    try:
        pick(board, {"OHST": 0.80, "WIS": 0.20})
        got = "picked"
    except C.SkipEvent as e:
        got = str(e)
    check(f"{label}: SkipEvent naming the teams", got, "no ESPN match for Ohio St. v Wisconsin")
check("an event with no price in the band needs no ESPN lookup", cfb_home.home_dog_picker(lambda d: 1 / 0)(ctx({"OHST": 0.5, "WIS": 0.5})), [])
try:
    cfb_home.home_dog_picker(lambda d: (_ for _ in ()).throw(RuntimeError("down")))(ctx({"OHST": 0.8, "WIS": 0.2}))
    got = "no error"
except C.SkipEvent:
    got = "skip"
except RuntimeError:
    got = "retry"
check("ESPN unreachable is NOT a skip: the engine retries the event on its next run", got, "retry")
check("Miami v Miami (OH): exact names decide who is home",
      cfb_home.match_game(["Miami (OH)", "Miami"], [game(("Miami Hurricanes", "Miami"), ("Miami (OH) RedHawks", "Miami (OH)"))]),
      (False, {"Miami (OH)": "away", "Miami": "home"}))

print("\nthe skip reaches the ledger")
lane = next(x for x in chaos_lanes.LANES if x["id"] == "cfb_home_dog_x4")
st = C.empty()
_le, _re = C.list_events, C.replay_event
C.list_events = lambda series, since, fetch, until=None: [EV]
C.replay_event = lambda ln, series, event, fetch, now=None: (None, "no ESPN match for Ohio St. v Wisconsin")
try:
    C.run(st, [lane], now=dt.datetime(2026, 11, 8, 10, tzinfo=C.UTC), fetch=None)
finally:
    C.list_events, C.replay_event = _le, _re
check("the event is on the lane's skipped list with its note", st["lanes"]["cfb_home_dog_x4"]["skipped"], {EV: "no ESPN match for Ohio St. v Wisconsin"})

print("\nthe lane")
check("series, hours, headline, record start", (lane["series"], lane["entry_hours"], lane["headline"], lane["since"]),
      (["KXNCAAFGAME"], (1, 24), "x4", "2026-11-02"))
check("the exits: hold, the split, x2 x3 x4 and the standard targets", (set(C.LANE_EXITS + C.SINGLES) <= set(lane["exits"]), "x4" in lane["exits"]), (True, True))
check("not a baseline and not retired", (lane.get("baseline"), lane.get("retired")), (None, None))
check("the research is on the card and marked not evidence", ("Not evidence" in lane["caution"], "+140.6%" in lane["caution"], "+63.7%" in lane["caution"],
      "25% reach 4x" in lane["caution"], "each Saturday" in lane["caution"]), (True,) * 5)
check("the lane sits first on the nfl page, above the blind baseline", CB.HOMES["nfl"][:2], ("cfb_home_dog_x4", "cfb_dog_tp50"))
check("the headline column reads Sell-all-at-4x", (CB.head_word([dict(headline="x4")]), CB.head_word([dict(headline="split")]), CB.head_word([])),
      ("Sell-all-at-4x", "Split", "Split"))

print("\nthe nfl page")
state = C.empty()
for ln in chaos_lanes.LANES:
    if ln["id"] in ("cfb_home_dog_x4", "cfb_dog_tp50"):
        C.lane_state(state, ln, dt.datetime(2026, 11, 8, 10, tzinfo=C.UTC))
html = CB.sport_section("nfl", state)
a, b = html.find('data-lane="cfb_home_dog_x4"'), html.find('id="baseline-cfb_dog_tp50"')
check("the lane's card, then the baseline block directly after it", 0 < a < b, True)
check("the card reads headline v hold and says review at 10, decide at 30", ("Sell-all-at-4x v hold" in html, "Review at 10 settled events, decide at 30" in html), (True, True))
check("the baseline says a filtered lane must beat it", "must beat" in html[b:], True)
idx = CB.index(list(CB.with_config(state)["lanes"].values()))
check("the Sandbox Chaos index lists the lane with a link to nfl.html and the headline column",
      ('data-lane="cfb_home_dog_x4"' in idx, 'href="./nfl.html#cheap-side"' in idx, "Sell-all-at-4x ROI" in idx), (True, True, True))
import sandbox_audit
check("public copy passes the guard", [m.group(0) for m in sandbox_audit.COPY_RE.finditer(html)], [])
check("no dollar amounts in the card", "$" in html, False)

print("\nALL PASS" if not FAILS else f"\n{len(FAILS)} FAILED")
raise SystemExit(1 if FAILS else 0)
