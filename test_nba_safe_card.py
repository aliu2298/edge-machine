#!/usr/bin/env python3
"""Offline checks for the NBA Safe Card (nba_safe_card.py) and its page section."""
import datetime as dt
import sys

import lane_windows as W
import nba_safe_card as SC
import nba_safe_card_build as SB
import nba_value_model as M
import sandbox_audit

FAILS = []
UTC = dt.timezone.utc
NOW = dt.datetime(2026, 10, 22, 21, 45, tzinfo=UTC)


def check(label, got, want):
    ok = got == want
    print(f"  {'ok  ' if ok else 'FAIL'} {label}" + ("" if ok else f" (got {got!r}, want {want!r})"))
    if not ok:
        FAILS.append(label)


def mk(ticker, line, bid, ask, status="active"):
    return dict(ticker=ticker, floor_strike=line, strike_type="greater", yes_bid_dollars=str(bid),
                yes_ask_dollars=str(ask), status=status)


G = dict(id="g1", home="PHI", away="CLE", start="2026-10-22T23:00Z", completed=False)
MODEL = dict(mu={"PHI": 110.0, "CLE": 115.0}, mu_q1=58.0)

print("price band, the NO price and the spread")
check("band edges 0.84 and 0.95 are in, 0.835 and 0.955 out",
      [SC.in_band(p) for p in (0.84, 0.95, 0.835, 0.955)], [True, True, False, False])
legs = SC.legs_for(G, "game", [mk("KXNBATOTAL-26OCT22CLEPHI-256", 255.5, 0.10, 0.12)], MODEL)
no = next(x for x in legs if x["side"] == "no")
check("NO = 1 - the YES bid", no["price"], 0.9)
check("a 4c spread is not quoted", SC.legs_for(G, "game", [mk("X-1", 255.5, 0.10, 0.14)], MODEL), [])
check("a one-sided rung is not quoted", SC.legs_for(G, "game", [mk("X-1", 255.5, 0.0, 0.05)], MODEL), [])

print("\nmodel P per market")
phi = lambda line, mu, sd: round(1 - M.phi((line - mu) / sd), 4)
yes = lambda kind, line, unit=None: next(x["p"] for x in SC.legs_for(G, kind, [mk(f"KX-26OCT22CLEPHI-{unit or ''}{int(line)}", line, .4, .42)], MODEL)
                                         if x["side"] == "yes")
check("team total: Normal(mu_team, 11.83)", yes("tt", 120.5, "PHI"), phi(120.5, 110.0, 11.83))
check("1Q: Normal(mu_q1, 8.28)", yes("q1", 60.5), phi(60.5, 58.0, 8.28))
check("game: Normal(mu_home + mu_away, 18.9)", yes("game", 230.5), phi(230.5, 225.0, 18.9))
check("1H: Normal(0.505 x game mu, 13.0)", yes("h1", 115.5), phi(115.5, 0.505 * 225.0, 13.0))

print("\nlabels agree, both sides of every market")
labs = dict(home_ft="O+D+", away_ft="O-D-", home_q1="O+D-", away_q1="O+D+", home_h1="O-D+", away_h1="O-D-")
leg = lambda kind, side, unit="game": dict(kind=kind, side=side, unit=unit)
ok = lambda kind, side, unit="game", l=labs: SC.labels_agree(leg(kind, side, unit), G, l)[0]
check("team OVER: own O+ and opponent D+ (PHI O+ v CLE D-: no)", ok("tt", "yes", "PHI"), False)
check("team UNDER: own O- and opponent D- (CLE O- v PHI D+: no)", ok("tt", "no", "CLE"), False)
check("team OVER holds with own O+ and opponent D+",
      ok("tt", "yes", "PHI", dict(labs, away_ft="O-D+")), True)
check("team UNDER holds with own O- and opponent D-",
      ok("tt", "no", "CLE", dict(labs, home_ft="O+D-")), True)
check("game OVER needs both D+, UNDER both D-",
      (ok("game", "yes", l=dict(labs, away_ft="O-D+")), ok("game", "no", l=dict(labs, home_ft="O+D-")), ok("game", "no")),
      (True, True, False))
check("1Q OVER needs both O+ (q1 labels)", (ok("q1", "yes"), ok("q1", "no")), (True, False))
check("1H UNDER needs both O- (h1 labels)", (ok("h1", "no"), ok("h1", "yes")), (True, False))
check("no labels: no agreement", SC.labels_agree(leg("game", "no"), G, {})[0], False)

print("\nthe clean leg: 8 of the last 10")
t0 = dt.datetime(2026, 10, 1, tzinfo=UTC)
pts = {"PHI": [(t0 + dt.timedelta(days=i), p) for i, p in enumerate([100] * 2 + [125] * 8)]}
L = dict(kind="tt", unit="PHI", side="yes", line=120.5)
check("cleared 120.5 in 8/10: passes", SC.clean(L, pts)[:2], (True, "cleared 120.5 in 8/10"))
check("stayed under 120.5 in 2/10: an UNDER fails", SC.clean(dict(L, side="no"), pts)[0], False)
check("6 games: 80% rounded up, 5 of 6 needed", SC.clean(L, {"PHI": pts["PHI"][-6:]})[0], True)
check("fewer than 5 games: no check", SC.clean(L, {"PHI": pts["PHI"][-4:]})[:2], (True, "clean check skipped (4 games)"))

print("\nthe card: best edge first, one leg per game, odds 1.70 with 3-4 legs")
S = lambda g, edge, price: dict(game=g, edge=edge, price=price, ticker=f"{g}-{edge}", side="no")
legs4 = [S("a", 0.08, 0.84), S("a", 0.09, 0.86), S("b", 0.07, 0.85), S("c", 0.06, 0.86), S("d", 0.05, 0.87), S("e", 0.04, 0.84)]
card, reason = SC.pick_card(legs4)
check("one leg per game, best edge first, stops at 4 legs once odds pass 1.70",
      ([x["ticker"] for x in card], round(SC.odds_of(card), 2), reason), (["a-0.09", "b-0.07", "c-0.06", "d-0.05"], 1.83, None))
check("three legs at 84c+ cannot reach 1.70", round(SC.odds_of([S("x", 0, 0.84)] * 3), 3) < 1.70, True)
check("fewer than 3 legs can go on: no card",
      SC.pick_card([S("a", .05, .84), S("b", .05, .84)])[1], "no card tonight: only 2 legs can go on a card "
      "(a card needs 3 to 4 legs, one per game)")
short = SC.pick_card([S(g, .05, .95) for g in "abcd"])
check("four legs short of 1.70: no card with the reason", (short[0], "short of 1.70x" in short[1]), ([], True))

print("\nsmall slates (amendment 2026-10-22): up to 2 legs a game, never same-direction implied pairs")
check("cap: 2 a game under 4 games, 1 from 4", [SC.per_game_cap(n) for n in (1, 2, 3, 4, 9)], [2, 2, 2, 1, 1])
Lg = lambda g, kind, side, edge, price=0.86, unit="game": dict(game=g, match=g, kind=kind, unit=unit, side=side,
                                                                edge=edge, price=price, ticker=f"{g}-{kind}-{unit}-{side}")
pair = lambda a, b: SC.pair_ok(a, b)[0]
check("refused: game total + team total, same direction",
      (pair(Lg("x", "game", "no", .1), Lg("x", "tt", "no", .1, unit="PHI")), pair(Lg("x", "game", "yes", .1), Lg("x", "tt", "yes", .1, unit="PHI"))),
      (False, False))
check("refused: 1H + game, and 1Q + 1H, same direction",
      (pair(Lg("x", "h1", "no", .1), Lg("x", "game", "no", .1)), pair(Lg("x", "q1", "yes", .1), Lg("x", "h1", "yes", .1))), (False, False))
check("refused: the same market twice", pair(Lg("x", "game", "no", .1), Lg("x", "game", "yes", .1)), False)
check("allowed: team OVER + 1Q UNDER; home and away team OVERs; 1Q OVER + game UNDER; game + team opposite ways",
      (pair(Lg("x", "tt", "yes", .1, unit="PHI"), Lg("x", "q1", "no", .1)),
       pair(Lg("x", "tt", "yes", .1, unit="PHI"), Lg("x", "tt", "yes", .1, unit="CLE")),
       pair(Lg("x", "q1", "yes", .1), Lg("x", "game", "no", .1)),
       pair(Lg("x", "game", "no", .1), Lg("x", "tt", "yes", .1, unit="PHI"))), (True, True, True, True))
small = [Lg("A", "game", "no", .09), Lg("A", "tt", "no", .085, unit="PHI"), Lg("A", "q1", "yes", .08),
         Lg("B", "h1", "no", .07), Lg("B", "q1", "no", .065), Lg("B", "q1", "yes", .06), Lg("B", "game", "no", .05)]
card2, why2 = SC.pick_card(small, cap=2)
check("small slate: best edge first, implied pairs skipped (A game+team unders, B 1Q+1H unders), two a game, four legs",
      [x["ticker"] for x in card2], ["A-game-game-no", "A-q1-game-yes", "B-h1-game-no", "B-q1-game-yes"])
card1, why1 = SC.pick_card(small, cap=1)
check("the same legs on a big-slate cap: one a game, no card", (card1, why1.startswith("no card tonight: only 2 legs")), ([], True))
r_card = dict(legs=[dict(x, p=0.93) for x in card2], odds=1.83, reason=None)
txt = SC.card_rationale(r_card, dict(quoted=9, band=8, safety=7, value=6, labels=6, clean=6))
check("the card says which game gave two legs, and that the combo assumes independence",
      ("2 legs from A: small slate, legs not same-direction." in txt, "2 legs from B" in txt, "(assumes legs independent)" in txt),
      (True, True, True))
check("a one-leg-per-game card says neither",
      "independent" in SC.card_rationale(dict(r_card, legs=[dict(Lg(g, "game", "no", .1), p=.93) for g in "abcd"]),
                                         dict(quoted=9, band=8, safety=7, value=6, labels=6, clean=6)), False)

print("\nthe level check (amended 2026-10-24): a lean label, not a block")
GAPS = dict(n=56, avg=-3.5, beat=0.46)
lc = lambda med, mu, sides, g=GAPS: SC.level_check(med, mu, sides, g)
check("a gap over 8 points is a data problem: no card",
      (lc({"PHI": 120.0}, {"PHI": 110.5}, ["no"])["ok"], lc({"PHI": 120.0}, {"PHI": 110.5}, ["no"])["reason"].startswith("no card tonight: model level")),
      (False, True))
check("a gap over 4 points is a warning, the card still builds",
      (lc({"PHI": 115.0}, {"PHI": 110.5}, ["no"])["ok"], lc({"PHI": 115.0}, {"PHI": 110.5}, ["no"])["warning"][:8]), (True, "warning:"))
check("no Kalshi level to compare: no card (a data problem)", lc({}, {}, ["no"] * 5)["ok"], False)
allun = lc({"PHI": 111.0}, {"PHI": 110.5}, ["no"] * 14)
check("14 of 14 label survivors unders: builds, with the lean label and the season gap",
      (allun["ok"], allun["lean"]), (True, "model leans under: Kalshi lines running 3.5 pts above results season to date (56 team-games)"))
check("over-leaning, and Kalshi's lines below results", lc({"PHI": 111.0}, {"PHI": 110.5}, ["yes"] * 6, dict(n=10, avg=2.0, beat=.6))["lean"],
      "model leans over: Kalshi lines running 2.0 pts below results season to date (10 team-games)")
check("no season gap yet: the label says so", lc({"PHI": 111.0}, {"PHI": 110.5}, ["no"] * 5, None)["lean"],
      "model leans under: no season-to-date results gap yet")
check("4 of 5 (80%) or 2 survivors: no label", (lc({"PHI": 111.0}, {"PHI": 110.5}, ["no"] * 4 + ["yes"])["lean"],
      lc({"PHI": 111.0}, {"PHI": 110.5}, ["no"] * 2)["lean"]), (None, None))

print("\nrationale text")
r = SC.rationale(dict(match="PHX@POR", kind="game", unit="game", side="no", line=249.5, price=0.84, p=0.916, mu=223.5,
                      edge=0.076, labels="POR O+D− v PHX O−D−"))
check("a game UNDER reads like the pre-registration",
      r, "PHX@POR game UNDER 249.5 @84c: model 91.6% (mu 223.5, line +26.0 above mu); "
         "labels POR O+D− v PHX O−D− (both defences agree); edge +7.6c")
r2 = SC.rationale(dict(match="CLE@PHI", kind="tt", unit="PHI", side="yes", line=104.5, price=0.88, p=0.93, mu=118.0,
                       edge=0.05, labels="PHI O+D+ v O−D+", clean="cleared 104.5 in 9/10"))
check("a team total names the team and the clean check", ("PHI team total OVER 104.5" in r2, "cleared 104.5 in 9/10" in r2), (True, True))

print("\nbuild, freeze, tip price, settlement")
GAMES = {f"g{i}": dict(id=f"g{i}", home=h, away=a, start="2026-10-22T23:00Z", completed=False)
         for i, (h, a) in enumerate((("PHI", "CLE"), ("OKC", "DEN"), ("LAL", "GS"), ("MEM", "UTAH")))}
LABS = {gid: dict(home_ft="O-D-", away_ft="O-D-", home_q1="O-D-", away_q1="O-D-", home_h1="O-D-", away_h1="O-D-") for gid in GAMES}
LADDER = [mk("GAME-250", 249.5, 0.13, 0.15), mk("GAME-240", 239.5, 0.30, 0.32)]
results = {}


def fetch(path):
    if path.startswith("markets?"):
        ev = path.split("event_ticker=")[1].split("&")[0]
        if ev.startswith("KXNBATOTAL-26OCT22"):
            return {"markets": [dict(m, ticker=f"{ev}-{m['ticker']}") for m in LADDER]}
        if ev.startswith("KXNBATEAMTOTAL-26OCT22"):          # a level to compare: Kalshi's 50c line is 110.5
            return {"markets": [mk(f"{ev}-{SC.T.NR.E2K.get(t, t)}{int(line)}", line, round(mid - .01, 2), round(mid + .01, 2))
                                for t in ("PHI", "CLE", "OKC", "DEN", "LAL", "GS", "MEM", "UTAH")
                                for line, mid in ((109.5, .55), (111.5, .45))]}
        return {"markets": []}
    t = path.split("/", 1)[1]
    if t in results:
        return {"market": dict(status="finalized", result=results[t])}
    return {"market": dict(status="active", yes_bid_dollars="0.12", yes_ask_dollars="0.14")}


SC.T.model_for = lambda g, games, pri=None, at=None, pre=None: dict(mu={g["home"]: 110.0, g["away"]: 110.0}, mu_q1=58.0)
SC.D.pages = lambda path, key, fetch: fetch(path).get(key) or []
state = SC.empty()
state["preseason"] = [dict(start="2026-10-10T23:00Z", team="PHI", pts=100)]
early = SC.run(state, GAMES, NOW - dt.timedelta(hours=3), fetch, pri={}, labs_all=LABS)
check("3 hours before the first tip: nothing built", (early, state["cards"]), ([], {}))
built = SC.run(state, GAMES, NOW, fetch, pri={}, labs_all=LABS)
card = state["cards"]["2026-10-22"]
check("75 minutes before the first tip: tonight's card", (built, card["status"], len(card["legs"])), (["2026-10-22"], "open", 4))
check("four game UNDER 249.5 legs at 87c, odds 1.75",
      ({(x["kind"], x["side"], x["line"], x["price"]) for x in card["legs"]}, card["odds"]),
      ({("game", "no", 249.5, 0.87)}, round(1 / 0.87 ** 4, 3)))
check("the funnel counts are logged", sorted(card["counts"]), ["band", "card", "clean", "labels", "quoted", "safety", "value"])
check("every leg the funnel looked at is logged with a cut reason, or is on the card",
      all(x["cut"] for x in card["candidates"]) and all(x["cut"] is None for x in card["legs"]), True)
SC.run(state, GAMES, NOW + dt.timedelta(minutes=10), fetch, pri={}, labs_all=LABS)
check("frozen: a later read does not rebuild", state["cards"]["2026-10-22"]["built_at"], NOW.isoformat())
check("price at tip logged once inside 60-90 min of the leg's own tip",
      {x.get("price_at_tip") for x in card["legs"]}, {0.88})
for x in card["legs"]:
    results[x["ticker"]] = "no"
SC.run(state, GAMES, NOW + dt.timedelta(hours=6), fetch, pri={}, labs_all=LABS)
check("all four NO legs win: the card wins, paying its odds", (card["status"], card["profit"]),
      ("won", round(card["odds"] - 1, 4)))
check("a leg's profit is after the 7% fee", card["legs"][0]["profit"], round(1 / (0.87 + SC.fee(0.87)) - 1, 4))
lost = dict(card, status="open", legs=[dict(x, status="open") for x in card["legs"]], candidates=[])
results[lost["legs"][0]["ticker"]] = "yes"
st2 = {"cards": {"x": lost}}
SC.settle(st2, NOW + dt.timedelta(hours=6), fetch)
check("one leg loses: the card loses $1", (lost["status"], lost["profit"]), ("lost", -1.0))
two = {k: GAMES[k] for k in ("g0", "g1")}
st3 = SC.empty()
st3["preseason"] = []
SC.run(st3, two, NOW, fetch, pri={}, labs_all=LABS)
check("a two-game slate with only game-total legs: one per game (the same market twice is refused), no card",
      (st3["cards"]["2026-10-22"]["per_game_cap"], st3["cards"]["2026-10-22"]["reason"]),
      (2, "no card tonight: only 2 legs can go on a card (a card needs 3 to 4 legs, up to two per game)"))
one = {"g0": GAMES["g0"]}
st4 = SC.empty()
st4["preseason"] = []
SC.run(st4, one, NOW, fetch, pri={}, labs_all=LABS)
check("a one-game slate cannot make 3 legs", st4["cards"]["2026-10-22"]["reason"],
      "no card tonight: only 1 game on the slate (a card needs 3 to 4 legs, at most 2 per game)")

print("\nan all-under night builds a card with the lean label (2026-10-24)")
results.clear()
LADDER[:] = [mk("GAME-250", 249.5, 0.13, 0.15), mk("GAME-252", 251.5, 0.11, 0.13), mk("GAME-254", 253.5, 0.09, 0.11)]
st5 = SC.empty()
st5["preseason"] = []
GAPS = dict(n=56, avg=-3.5, beat=0.46)
SC.run(st5, GAMES, NOW, fetch, pri={}, labs_all=LABS, season_gap=GAPS)
c5 = st5["cards"]["2026-10-22"]
check("14 under legs survive and all of them lean one way, yet the card still builds",
      (c5["status"], len(c5["legs"]), {x["side"] for x in c5["legs"]}, c5["guard"]["ok"]), ("open", 4, {"no"}, True))
check("the lean label names the season gap", c5["lean"],
      "model leans under: Kalshi lines running 3.5 pts above results season to date (56 team-games)")
check("and the card rationale names it", "model leans under: Kalshi lines running 3.5 pts above results" in c5["rationale"], True)
check("the page shows the label above the card", "model leans under" in SB.section(st5), True)
check("an unlabelled night carries no lean", state["cards"]["2026-10-22"].get("lean"), None)
st6 = SC.empty()
st6["preseason"] = []
SC.run(st6, GAMES, NOW, lambda path: {"markets": []} if "KXNBATEAMTOTAL" in path else fetch(path), pri={}, labs_all=LABS)
check("no Kalshi team-total level at all: no card, a data problem",
      st6["cards"]["2026-10-22"]["reason"].startswith("no card tonight: no Kalshi team-total level"), True)

check("the dated amendment is in the pre-registered text and on the page",
      ("AMENDMENT 2026-10-24" in SC.__doc__, "Amendment 2026-10-24" in SB.section(st5), "season-data level stays the driver" in SC.__doc__),
      (True, True, True))

print("\nlane windows: the VPS asks 90-60 minutes before each tip")
tips = [dt.datetime(2026, 10, 22, 23, 0, tzinfo=UTC)]
got = lambda h, m: sorted(k for w, k in W.due(dt.datetime(2026, 10, 22, h, m, tzinfo=UTC), {"quotes": []}, [], [], nba_safe=tips)
                          if w["lane"] == "nba_safe_card")
check("a 23:00Z tip: read 1 at 21:35, read 2 at 21:50, none at 22:00", (got(21, 35), got(21, 50), got(22, 0)), ([1], [2], []))
check("its stamp file", W.STAMP["nba_safe_card"], "data/nba_safe_card_window/request.txt")

print("\nthe page section")
html = SB.section(state)
check("its id, heading and tonight's card with rationales",
      ('<section id="safe-card">' in html, "<h2>Safe Card</h2>" in html, "game UNDER 249.5 @87c" in html,
       "combined odds 1.75" in html), (True, True, True, True))
check("the record, the filter table and the calibration",
      ("1 won · 0 lost" in html, "Which filter mattered" in html, "Model calibration" in html), (True, True, True))
check("an empty ledger says when the card is built", "No card yet" in SB.section(SC.empty()), True)
check("public copy passes the guard", sandbox_audit.COPY_RE.search(html + SC.__doc__) is None, True)

print(f"\n{'ALL PASS' if not FAILS else str(len(FAILS)) + ' FAILED'}")
sys.exit(1 if FAILS else 0)
