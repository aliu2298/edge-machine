"""Logic tests for the Sandbox Tracker. Stdlib only, no network.

Every test here exists because the behaviour it pins would otherwise fail SILENTLY —
a source with a broken matcher and a source with no edge produce the identical board.
Most of these are regressions from the first live runs, not hypotheticals.
"""

import sys
from datetime import datetime, timedelta, timezone

import sandbox_sources as S
import sandbox_track as T

FAILS = []


def ok(cond, msg):
    if cond:
        print(f"  ok   {msg}")
    else:
        print(f"  FAIL {msg}")
        FAILS.append(msg)


def eq(a, b, msg):
    ok(a == b, f"{msg} (got {a!r}, want {b!r})")


def close(a, b, msg, tol=1e-6):
    ok(a is not None and abs(a - b) < tol, f"{msg} (got {a!r}, want ~{b!r})")


# ---------------------------------------------------------------------------
print("\nname matching")
# ---------------------------------------------------------------------------
eq(S.canon("New York G", "nfl"), "giants", "Kalshi's truncated city resolves to nickname")
eq(S.canon("New York Giants", "nfl"), "giants", "ESPN full name resolves")
eq(S.canon("Giants", "nfl"), "giants", "Polymarket nickname resolves")
eq(S.canon("Los Angeles R", "nfl"), "rams", "trailing initial separates the LA teams")
eq(S.canon("Los Angeles C", "nfl"), "chargers", "…and the other one")
eq(S.canon("Seattle", "mlb"), "mariners", "MLB city resolves")
eq(S.canon("Chicago White Sox", "mlb"), "white sox", "White Sox is not the Cubs")
eq(S.canon("Chicago Cubs", "mlb"), "cubs", "Cubs is not the White Sox")
eq(S.canon("Novak Djokovic", "tennis"), "", "individual sports have no alias table")

# The Sox collision is the reason STOP keeps colour words.
ok(S.sim("Boston Red Sox", "Chicago White Sox") < 0.5, "Red Sox and White Sox stay apart")
ok(S.sim("Yankees", "New York Yankees") >= 0.99, "short and long forms of one team match")

score, flipped = S.pair_match("Giants", "Rams", "New York G", "Los Angeles R", sport="nfl")
ok(score >= 0.99 and not flipped, "cross-feed NFL fixture matches, right way round")

score, flipped = S.pair_match("Giants", "Rams", "Los Angeles R", "New York G", sport="nfl")
ok(score >= 0.99 and flipped, "reversed fixture is detected as flipped, not rejected")

score, _ = S.pair_match("Rams", "Bears", "Los Angeles C", "Chicago", sport="nfl")
eq(score, 0.0, "Rams/Chargers share a city but are not the same team")

# ---------------------------------------------------------------------------
print("\nKalshi ticker dates")
# ---------------------------------------------------------------------------
eq(S.kalshi_date("KXNFLGAME-26SEP21NYGLAR"), "2026-09-21", "NFL game date from ticker")
eq(S.kalshi_date("KXMLBGAME-26SEP122140SEAATH"), "2026-09-12", "MLB ticker with a time suffix")
eq(S.kalshi_date("KXATPMATCH-26SEP11ZVEKHA"), "2026-09-11", "ATP ticker")
# close_time sits ~2 days after kickoff; trusting it shifted every NFL game a week.
ok(S.kalshi_date("KXNFLGAME-26SEP21NYGLAR", "2026-09-24T00:15:00Z") == "2026-09-21",
   "ticker beats close_time when both are present")

# ---------------------------------------------------------------------------
print("\nodds maths")
# ---------------------------------------------------------------------------
close(S.american_to_prob(-170), 170 / 270, "favourite moneyline to implied probability")
close(S.american_to_prob(142), 100 / 242, "underdog moneyline to implied probability")
a, b = S.devig(S.american_to_prob(-170), S.american_to_prob(142))
close(a + b, 1.0, "de-vigged pair sums to exactly 1")
ok(a > b, "the favourite keeps the larger share after de-vigging")
# Without de-vig a book's pair sums to ~1.05 and every quote looks like free edge.
raw = S.american_to_prob(-170) + S.american_to_prob(142)
ok(raw > 1.02, "raw book pair really does carry a margin worth stripping")

# ---------------------------------------------------------------------------
print("\nhead-to-head filter")
# ---------------------------------------------------------------------------
ok(S._is_head_to_head("Cincinnati Reds vs. Los Angeles Dodgers",
                      "Cincinnati Reds", "Los Angeles Dodgers"), "moneyline is kept")
ok(not S._is_head_to_head("Will there be a run scored in the first inning?: Cincinnati",
                          "Cincinnati Reds", "Los Angeles Dodgers"), "inning prop rejected")
ok(not S._is_head_to_head("Set Handicap: Samsonova (-1.5) vs Siegemund (+1.5)",
                          "Samsonova", "Siegemund"), "handicap prop rejected")
ok(not S._is_head_to_head("Duncan/Ribero vs. Bianchi/Sheehy: Set 1 Games O/U 8.5",
                          "Over", "Under"), "over/under rejected")
ok(not S._is_head_to_head("Will the Cardinals win the season series against the Rams?",
                          "Yes", "No"), "season-series future rejected")
# Substring matching on "over" would delete Vancouver, Dover and Hanover from the board.
ok(S._is_head_to_head("Vancouver vs. Hanover", "Vancouver", "Hanover"),
   "prop words match on word boundaries, not substrings")

# ---------------------------------------------------------------------------
print("\npick selection")
# ---------------------------------------------------------------------------
pick, edge, price = T.decide(0.60, 0.50, 0.50)
eq(pick, "a", "backs side A when it rates A above the price")
close(edge, 0.10, "edge is probability minus price")
close(price, 0.50, "records the price actually taken")

pick, edge, _ = T.decide(0.30, 0.50, 0.50)
eq(pick, "b", "backs side B when it rates A below the price")
close(edge, 0.20, "edge measured on the side actually backed")

pick, _, _ = T.decide(0.50, 0.50, 0.50)
eq(pick, None, "agreeing with the price is not a pick")

# ---------------------------------------------------------------------------
print("\none-to-one matching (the baseball-series trap)")
# ---------------------------------------------------------------------------
series = [
    dict(market_id="g1", sport="mlb", side_a="Cincinnati Reds", side_b="Los Angeles Dodgers",
         date="2026-09-10"),
    dict(market_id="g2", sport="mlb", side_a="Cincinnati Reds", side_b="Los Angeles Dodgers",
         date="2026-09-11"),
]
one_quote = [dict(a="Cincinnati", b="Los Angeles D", prob_a=0.35, date="2026-09-10")]
m = T.match_quotes(series, one_quote)
eq(len(m), 1, "one price cannot be booked against two games of the same series")
eq(list(m), ["g1"], "it lands on the nearer date")
eq(m["g1"][0], "prob", "a probability source is carried as a probability")

both = [dict(a="Cincinnati", b="Los Angeles D", prob_a=0.35, date="2026-09-10"),
        dict(a="Cincinnati", b="Los Angeles D", prob_a=0.42, date="2026-09-11")]
m = T.match_quotes(series, both)
eq(len(m), 2, "two prices for two games both land")
close(m["g1"][1], 0.35, "…and each lands on its own date")
close(m["g2"][1], 0.42, "…both of them")

flip = T.match_quotes(
    [dict(market_id="x", sport="mlb", side_a="Los Angeles Dodgers",
          side_b="Cincinnati Reds", date="2026-09-10")],
    [dict(a="Cincinnati", b="Los Angeles D", prob_a=0.35, date="2026-09-10")])
close(flip["x"][1], 0.65, "a reversed fixture has its probability inverted, not copied")

# ---------------------------------------------------------------------------
print("\nsettlement and P/L")
# ---------------------------------------------------------------------------
def quote(**kw):
    q = dict(id="s:1", source="kalshi", sport="mlb", market_id="1", label="A vs B",
             side_a="A", side_b="B", url="", date="2026-01-01",
             start=(datetime.now(timezone.utc) - timedelta(days=1)).isoformat(),
             logged="", prob_a=0.6, price_a=0.4, price_b=0.6, pick="a", edge=0.2,
             price=0.4, bet=True, stake=100.0, untraded=False,
             status="open", pnl=0.0, result=None, settled=None)
    q.update(kw)
    return q

d = {"quotes": [quote()], "meta": {}, "coverage": {}}
S_resolve = S.resolve_polymarket
S.resolve_polymarket = lambda mid: "a"
T.grade(d, verbose=False)
eq(d["quotes"][0]["status"], "won", "a correct pick settles as won")
close(d["quotes"][0]["pnl"], 150.0, "$100 at 0.40 returns $150 profit")

d = {"quotes": [quote()], "meta": {}, "coverage": {}}
S.resolve_polymarket = lambda mid: "b"
T.grade(d, verbose=False)
eq(d["quotes"][0]["status"], "lost", "a wrong pick settles as lost")
close(d["quotes"][0]["pnl"], -100.0, "a loss costs exactly the stake")

d = {"quotes": [quote()], "meta": {}, "coverage": {}}
S.resolve_polymarket = lambda mid: "void"
T.grade(d, verbose=False)
eq(d["quotes"][0]["status"], "void", "an unresolved/cancelled market voids")
close(d["quotes"][0]["pnl"], 0.0, "a void never invents P/L")

d = {"quotes": [quote(bet=False, stake=0.0, pick=None)], "meta": {}, "coverage": {}}
S.resolve_polymarket = lambda mid: "a"
T.grade(d, verbose=False)
eq(d["quotes"][0]["status"], "graded",
   "a no-bet quote is scored for accuracy but never counted as a loss")

# A market that has not started yet must never be settled.
d = {"quotes": [quote(start=(datetime.now(timezone.utc) + timedelta(days=2)).isoformat())],
     "meta": {}, "coverage": {}}
S.resolve_polymarket = lambda mid: "a"
T.grade(d, verbose=False)
eq(d["quotes"][0]["status"], "open", "a future fixture is not graded early")
S.resolve_polymarket = S_resolve

# ---------------------------------------------------------------------------
print("\nscoring")
# ---------------------------------------------------------------------------
d = {"quotes": [
    quote(id="kalshi:1", market_id="1", status="won", pnl=150.0, result="a"),
    quote(id="kalshi:2", market_id="2", status="lost", pnl=-100.0, result="b"),
], "meta": {}, "coverage": {}}
s = T.score(d)["kalshi"]
eq(s["settled"], 2, "both settled bets counted")
eq(s["won"], 1, "one winner")
close(s["hit"], 0.5, "hit rate is winners over settled")
close(s["pnl"], 50.0, "P/L is the sum of the two")
close(s["roi"], 0.25, "ROI is P/L over total staked, not over winnings")
close(s["brier"], ((0.6 - 1) ** 2 + (0.6 - 0) ** 2) / 2, "Brier over both graded quotes")

# Placeholder 0.50/0.50 books must not drown the accuracy column.
d = {"quotes": [
    quote(id="polymarket:1", source="polymarket", market_id="1", status="graded",
          result="a", bet=False, stake=0.0, prob_a=0.5, untraded=True),
    quote(id="polymarket:2", source="polymarket", market_id="2", status="graded",
          result="a", bet=False, stake=0.0, prob_a=0.8, untraded=False),
], "meta": {}, "coverage": {}}
s = T.score(d)["polymarket"]
eq(s["brier_n"], 1, "untraded placeholder books are excluded from Brier")
close(s["brier"], (0.8 - 1) ** 2, "only the real price is scored")

# ---------------------------------------------------------------------------
print("\nidempotency")
# ---------------------------------------------------------------------------
row = dict(market_id="m1", sport="mlb", label="A vs B", side_a="Cincinnati Reds",
           side_b="Los Angeles Dodgers", price_a=0.4, price_b=0.6, untraded=False,
           start=(datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
           date="2026-09-11", volume=100.0, url="")
d = {"quotes": [], "meta": {}, "coverage": {}}
saved = S.CHALLENGERS
S.CHALLENGERS = {}
T.publish(d, {"mlb": [row]}, {}, verbose=False)
first = len(d["quotes"])
T.publish(d, {"mlb": [row]}, {}, verbose=False)
S.CHALLENGERS = saved
eq(first, 1, "the market itself is logged once")
eq(len(d["quotes"]), 1, "re-running never re-quotes a market it has already priced")
eq(d["quotes"][0]["bet"], False,
   "the benchmark is priced at its own price, so it never bets against itself")

# ---------------------------------------------------------------------------
print("\nESPN adapters (offline, real payload shapes)")
# ---------------------------------------------------------------------------
# These two adapters cannot be exercised from a dev machine — ESPN's edge answers the
# sandbox with an Akamai 403 — so they would otherwise run for the very first time in
# production. The payloads below are trimmed copies of live responses, which pins the
# PARSING half of the adapter even when the network half is untestable here.
SCOREBOARD = {"events": [{
    "id": "401872656", "date": "2026-09-14T17:00Z",
    "competitions": [{"id": "401872656", "competitors": [
        {"homeAway": "home", "team": {"displayName": "Seattle Seahawks"}},
        {"homeAway": "away", "team": {"displayName": "New England Patriots"}}]}]}]}
PREDICTOR = {"homeTeam": {"statistics": [
    {"name": "gameProjection", "displayValue": "61.1"},
    {"name": "teamChanceLoss", "displayValue": "38.6"}]}}
ODDS = {"items": [{"provider": {"name": "DraftKings"},
                   "homeTeamOdds": {"moneyLine": -170},
                   "awayTeamOdds": {"moneyLine": 142}}]}


# The scoreboard host is load-bearing and was the entire cause of both ESPN sources
# returning zero in production. site.api 403s from the runner; site.web.api does not.
eq(S.ESPN_SITE, "https://site.web.api.espn.com",
   "ESPN scoreboard uses the host that is not server-side blocked")


def fake_get(url, **kw):
    if "scoreboard" in url:
        return SCOREBOARD
    if "predictor" in url:
        return PREDICTOR
    if "/odds" in url:
        return ODDS
    raise RuntimeError("unexpected url " + url)


real_get = S._get
S._get = fake_get
try:
    fpi = S.fetch_espn_fpi("nfl")
    ok(len(fpi) == 1, "FPI adapter returns one quote per game, de-duplicated across days")
    eq(fpi[0]["a"], "Seattle Seahawks", "side A is the HOME team")
    eq(fpi[0]["b"], "New England Patriots", "side B is the away team")
    close(fpi[0]["prob_a"], 0.611, "gameProjection is a percentage and must be scaled to 0-1")

    dk = S.fetch_draftkings("nfl")
    ok(len(dk) == 1, "DraftKings adapter returns one quote per game")
    eq(dk[0]["a"], "Seattle Seahawks", "book quote is oriented to the home team too")
    close(dk[0]["prob_a"], S.devig(S.american_to_prob(-170), S.american_to_prob(142))[0],
          "book probability is de-vigged, not the raw implied number")
    ok(dk[0]["prob_a"] < S.american_to_prob(-170),
       "de-vigging must LOWER the favourite below its raw implied probability")
finally:
    S._get = real_get

# ---------------------------------------------------------------------------
print("\npruning and rollup")
# ---------------------------------------------------------------------------
# The ledger is rewritten and committed four times a day. Rows kept forever are rows
# git stores forever, so old detail is folded into totals — and the totals have to
# survive that fold, or every source's record silently resets at the horizon.
old_ts = (datetime.now(timezone.utc) - timedelta(days=400)).isoformat()
new_ts = datetime.now(timezone.utc).isoformat()
d = {"quotes": [
    quote(id="kalshi:old1", market_id="o1", status="won", pnl=150.0, result="a", settled=old_ts),
    quote(id="kalshi:old2", market_id="o2", status="lost", pnl=-100.0, result="b", settled=old_ts),
    quote(id="kalshi:new", market_id="n1", status="won", pnl=150.0, result="a", settled=new_ts),
    quote(id="kalshi:open", market_id="p1", status="open", settled=None),
], "meta": {}, "coverage": {}}
rolled = T.prune(d, retain_days=120, verbose=False)
eq(rolled, 2, "only quotes settled past the horizon are rolled up")
eq(len(d["quotes"]), 2, "the recent one and the open one stay as rows")
ok(any(q["status"] == "open" for q in d["quotes"]), "an OPEN quote is never pruned")

s = T.score(d)["kalshi"]
eq(s["settled"], 3, "lifetime settled count survives the rollup")
eq(s["won"], 2, "lifetime wins survive")
close(s["pnl"], 200.0, "lifetime P/L survives")
close(s["roi"], 200.0 / 300.0, "ROI still divides by everything ever staked")
eq(s["brier_n"], 3, "Brier sample survives the rollup")

# Rolling up twice must not double-count.
T.prune(d, retain_days=120, verbose=False)
eq(T.score(d)["kalshi"]["settled"], 3, "pruning again does not double-count the rollup")

# ---------------------------------------------------------------------------
print("\nplaceholder books")
# ---------------------------------------------------------------------------
placeholder = dict(market_id="tt1", sport="table_tennis", label="A vs B", side_a="A",
                   side_b="B", price_a=0.5, price_b=0.5, untraded=True,
                   start=(datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
                   date="2026-09-11", volume=0.0, url="")
d = {"quotes": [], "meta": {}, "coverage": {}}
saved = S.CHALLENGERS
S.CHALLENGERS = {}
T.publish(d, {"table_tennis": [placeholder]}, {}, verbose=False)
S.CHALLENGERS = saved
eq(len(d["quotes"]), 0,
   "an untouched 50/50 book is never logged — it is not a forecast, and it is half the feed")

# ---------------------------------------------------------------------------
print("\nintake cap")
# ---------------------------------------------------------------------------
eq(S.MAX_PER_SPORT, 40, "intake is capped per sport per run")
# The coverage panel must report what Polymarket LISTS, not what the cap let through.
_stats = {}
_rows = S.fetch_polymarket.__wrapped__ if hasattr(S.fetch_polymarket, "__wrapped__") else None
ok("stats" in S.fetch_polymarket.__code__.co_varnames,
   "fetch_polymarket reports pre-cap totals separately from the capped rows")
ok(T.RETAIN_DAYS * 6 * S.MAX_PER_SPORT < 15000,
   "cap and retention together keep the committed ledger to a few thousand rows")

# ---------------------------------------------------------------------------
print("\ntipsters (bare picks)")
# ---------------------------------------------------------------------------
# A tipster names a side and no probability. That is still fully scoreable for PROFIT,
# which is the whole question — it just cannot be calibrated.
tip = T.match_quotes(
    [dict(market_id="t1", sport="nfl", side_a="Giants", side_b="Rams", date="2026-09-14")],
    [dict(a="New York G", b="Los Angeles R", pick="b", date="2026-09-14")])
eq(tip["t1"], ("pick", "b"), "a bare pick is carried as a pick, not coerced to a probability")

flipped_tip = T.match_quotes(
    [dict(market_id="t2", sport="nfl", side_a="Rams", side_b="Giants", date="2026-09-14")],
    [dict(a="New York G", b="Los Angeles R", pick="b", date="2026-09-14")])
eq(flipped_tip["t2"], ("pick", "a"),
   "a reversed fixture flips WHICH SIDE was picked — the opposite bet otherwise")

row_tip = dict(market_id="t3", sport="nfl", label="Giants vs Rams", side_a="Giants",
               side_b="Rams", price_a=0.35, price_b=0.65, untraded=False,
               start=(datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
               date="2026-09-14", volume=500.0, url="")
d = {"quotes": [], "meta": {}, "coverage": {}}
saved = S.CHALLENGERS
S.CHALLENGERS = {"covers": lambda sp: [dict(a="Giants", b="Rams", pick="a", date="2026-09-14")]}
T.publish(d, {"nfl": [row_tip]}, {}, verbose=False)
S.CHALLENGERS = saved
tips = [q for q in d["quotes"] if q["source"] == "covers"]
eq(len(tips), 1, "the tipster's pick is logged")
eq(tips[0]["pick"], "a", "on the side it actually named")
eq(tips[0]["bet"], True, "a bare pick is backed with no edge threshold to clear")
close(tips[0]["price"], 0.35, "…at the price of the side it picked")
eq(tips[0]["prob_a"], None, "and carries no invented probability")
eq(tips[0]["edge"], None, "and no invented edge")

# It must still settle and pay like any other bet.
S_resolve = S.resolve_polymarket
S.resolve_polymarket = lambda mid: "a"
tips[0]["start"] = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
T.grade(d, verbose=False)
S.resolve_polymarket = S_resolve
eq(tips[0]["status"], "won", "a tipster's winning pick settles as won")
close(tips[0]["pnl"], round(100.0 * (1 / 0.35 - 1), 2),
      "and pays at the price it was backed at")

sc = T.score(d)["covers"]
close(sc["roi"], round(100.0 * (1 / 0.35 - 1), 2) / 100.0,
      "the tipster's ROI is real")
eq(sc["brier"], None, "but it has no Brier score — there is nothing to calibrate")

# ---------------------------------------------------------------------------
print("\nscores24 row parsing (headless-browser source)")
# ---------------------------------------------------------------------------
# Pure parsing, no browser needed. Every fixture below is a real row shape captured
# from the live listing pages.
import sandbox_browser as B

win = B.parse_row({"href": "/en/tennis/m-10-09-2026-sabalenka-aryna-pegula-jessica-prediction",
                   "lines": ["18:00", "Today", "Aryna Sabalenka", "Jessica Pegula",
                             "90%", "Aryna Sabalenka Win"]}, "tennis")
eq(win["a"], "Aryna Sabalenka", "first competitor read from the row")
eq(win["b"], "Jessica Pegula", "second competitor read from the row")
eq(win["pick"], "a", "the tip names the first competitor")
eq(win["date"], "2026-09-10", "date comes from the slug, which is DD-MM-YYYY not ISO")

# The tipped side is NOT always the first one listed.
away = B.parse_row({"href": "/en/baseball/m-10-09-2026-chicago-white-sox-pittsburgh-pirates-prediction",
                    "lines": ["18:40", "Today", "Chicago White Sox", "Pittsburgh Pirates",
                              "Pittsburgh Pirates Win", "-"]}, "baseball")
eq(away["pick"], "b", "a tip on the second competitor is recorded as side B")

# Totals and handicaps settle on a different question than the moneyline they would be
# booked against. Scoring one as a match-winner pick records a bet nobody made.
ok(B.parse_row({"href": "/en/tennis/m-11-09-2026-tiafoe-frances-shelton-ben-prediction",
                "lines": ["18:00", "Tomorrow", "Frances Tiafoe", "Ben Shelton",
                          "92%", "Total Over (36,5)"]}, "tennis") is None,
   "a totals tip is not scored as a match-winner pick")
ok(B.parse_row({"href": "/en/tennis/m-11-09-2026-zverev-alexander-khachanov-karen-prediction",
                "lines": ["14:00", "Tomorrow", "Alexander Zverev", "Karen Khachanov",
                          "Karen Khachanov Total Over (15,5)"]}, "tennis") is None,
   "a player-totals tip is rejected even though it names a player")

# Every listing page carries a cross-sport rail. On the cricket, boxing and table-tennis
# pages that rail is the ONLY content, so without the href guard the scraper would
# return ice-hockey tips as cricket ones.
ok(B.parse_row({"href": "/en/ice-hockey/m-10-09-2026-sibir-novosibirsk-amur-khabarovsk-prediction",
                "lines": ["10 Sep,", "07:30", "KHL", "Sibir Novosibirsk",
                          "Amur Khabarovsk", "Prediction", "13"]}, "cricket") is None,
   "the cross-sport rail cannot leak into another sport's picks")

# An unfamiliar layout must fail closed rather than guess which line is a competitor.
ok(B.parse_row({"href": "/en/tennis/m-10-09-2026-a-b-prediction",
                "lines": ["18:00", "Today", "One", "Two", "Three", "Someone Else Win"]},
               "tennis") is None,
   "an unrecognised row shape is dropped, not guessed at")

eq(B.available.__call__() in (True, False), True, "browser availability is a plain bool")
ok(B.fetch_rows.__doc__ and "Never raises" in B.fetch_rows.__doc__,
   "the browser fetch is documented as non-fatal")

# Absent Playwright must degrade to an empty column, never an exception.
real_avail = B.available
B.available = lambda: False
try:
    got = B.fetch_rows(["https://example.invalid/x"], log=lambda *a: None)
    eq(got, {"https://example.invalid/x": []},
       "with no browser installed the source reports nothing and does not raise")
finally:
    B.available = real_avail

# ---------------------------------------------------------------------------
print("\nKalshi as a venue")
# ---------------------------------------------------------------------------

def km(code, title, status="active", result="", bid="0.40", ask="0.42", event="EV", exp=None):
    return dict(ticker=f"{event}-{code}", event_ticker=event, yes_sub_title=title,
                status=status, result=result, yes_bid_dollars=bid, yes_ask_dollars=ask,
                expected_expiration_time=exp)

eq(S.kalshi_sides("KXEPLGAME-26SEP06ARSCFC",
                  [km("ARS", "Arsenal"), km("CFC", "Chelsea"), km("TIE", "Tie")]),
   {"ARS": "a", "CFC": "b", "TIE": "draw"},
   "side A is the team the event code starts with (Arsenal at home)")
eq(S.kalshi_sides("KXEPLGAME-26SEP06ARSCFC",
                  [km("TIE", "Tie"), km("CFC", "Chelsea"), km("ARS", "Arsenal")]),
   {"ARS": "a", "CFC": "b", "TIE": "draw"},
   "the order Kalshi returns markets in never changes which side is home")
eq(S.kalshi_sides("KXMLBGAME-26SEP131920SDSF", [km("SF", "San Francisco"), km("SD", "San Diego")]),
   {"SD": "a", "SF": "b"}, "an embedded four-digit start time is stripped before reading the home code")
eq(S.kalshi_sides("KXBOXING-26SEP12GARCIAMORALE",
                  [km("MORALE", "Abraham Morales"), km("GARCIA", "Sean Garcia")]),
   {"GARCIA": "a", "MORALE": "b"}, "codes of any length resolve — the suffix is never split by width")
eq(S.kalshi_sides("KXCONMEBOLSUDGAME-26SEP16SPABOC",
                  [km("SPA", "Reg Time: Sao Paulo"), km("BOC", "Reg Time: Boca Juniors"),
                   km("TIE", "Reg Time: Tie")])["TIE"], "draw",
   "a 'Reg Time: Tie' outcome is still recognised as the draw")
eq(S._kalshi_name(km("SPA", "Reg Time: Sao Paulo")), "Sao Paulo",
   "the 'Reg Time:' prefix is not part of the club's name")


def resolving(markets):
    real = S._get
    S._get = lambda url, **kw: {"markets": markets}
    try:
        return S.resolve_kalshi("KXEPLGAME-26SEP06ARSCFC")
    finally:
        S._get = real

eq(resolving([km("ARS", "Arsenal", "finalized", "yes"), km("CFC", "Chelsea", "finalized", "no"),
              km("TIE", "Tie", "finalized", "no")]), "a", "a finalized home win settles side A")
eq(resolving([km("ARS", "Arsenal", "finalized", "no"), km("CFC", "Chelsea", "finalized", "no"),
              km("TIE", "Tie", "finalized", "yes")]), "draw", "a finalized Tie settles as a draw")
eq(resolving([km("ARS", "Arsenal"), km("CFC", "Chelsea"), km("TIE", "Tie")]), None,
   "a live event is not settled")
eq(resolving([km("ARS", "Arsenal", "active", "yes"), km("CFC", "Chelsea"), km("TIE", "Tie")]), None,
   "a provisional yes is not settled until the market is final")
eq(resolving([km("ARS", "Arsenal", "finalized", "no"), km("CFC", "Chelsea", "finalized", "no"),
              km("TIE", "Tie", "finalized", "no")]), "void",
   "all final with no winner is a refund, never a guess")

now_ = datetime.now(timezone.utc)
soon = now_ + timedelta(days=1)
far = now_ + timedelta(days=9)
tag = lambda d_: f"{d_:%y}{d_.strftime('%b').upper()}{d_:%d}"
ev, ev_far = f"KXEPLGAME-{tag(soon)}LEENEW", f"KXEPLGAME-{tag(far)}ARSCFC"
exp = (now_ + timedelta(hours=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
book = [km("LEE", "Leeds United", bid="0.39", ask="0.40", event=ev, exp=exp),
        km("NEW", "Newcastle", bid="0.02", ask="0.81", event=ev, exp=exp),
        km("TIE", "Tie", bid="0.27", ask="0.28", event=ev, exp=exp),
        km("ARS", "Arsenal", event=ev_far, exp=exp), km("CFC", "Chelsea", event=ev_far, exp=exp),
        km("TIE", "Tie", event=ev_far, exp=exp)]
real_open = S._kalshi_open
S._kalshi_open = lambda series: book if series == "KXEPLGAME" else []
try:
    krows = S.fetch_kalshi_venue("soccer")
finally:
    S._kalshi_open = real_open
eq(len(krows), 1, "only fixtures inside the horizon become contests")
kr = krows[0]
eq((kr["side_a"], kr["side_b"]), ("Leeds United", "Newcastle"), "home and away read from the event code")
close(kr["price_a"], 0.40, "a side is priced at the ASK — what backing it would actually cost")
close(kr["price_draw"], 0.28, "the draw carries its own ask")
eq(kr["tradeable"], {"a": True, "b": False, "draw": True},
   "a 0.02/0.81 book is untradeable even when the rest of the event is tight")
eq(kr["venue"], "kalshi", "the row is marked as a Kalshi venue")

for sp_, series_ in S.KALSHI_VENUE_SERIES.items():
    eq(len(series_), len(set(series_)), f"no Kalshi series is listed twice for {sp_} — "
       "a duplicate doubles every event's markets and silently drops the event")
ok(isinstance(S.tokens("Leeds United"), frozenset),
   "cached name tokens are frozen, so no caller can corrupt the cache")

# ---------------------------------------------------------------------------
print("\ndraw picks and Kalshi-venue publishing")
# ---------------------------------------------------------------------------
m = T.match_quotes(
    [dict(market_id="k1", sport="soccer", side_a="Newcastle", side_b="Leeds United", date="2026-09-12")],
    [dict(a="Leeds United", b="Newcastle", pick="draw", date="2026-09-12")])
eq(m["k1"], ("pick", "draw"), "a draw stays a draw when the fixture is listed the other way round")

krow = dict(kr, start=(now_ + timedelta(days=1)).isoformat())
d = {"quotes": [], "meta": {}, "coverage": {}}
saved = S.CHALLENGERS
S.CHALLENGERS = {
    "soccerpredictions": lambda sp: [dict(a="Leeds", b="Newcastle United", pick="draw", date=krow["date"])],
    "sportsgambler": lambda sp: [dict(a="Leeds United", b="Newcastle", pick="b", date=krow["date"])],
}
T.publish(d, {"soccer": [krow]}, {}, verbose=False)
S.CHALLENGERS = saved
byq = {q["source"]: q for q in d["quotes"]}
eq(byq["soccerpredictions"]["pick"], "draw", "a Draw tip is logged as a draw")
close(byq["soccerpredictions"]["price"], 0.28, "and priced at the Tie ask")
eq(byq["soccerpredictions"]["bet"], True, "a Draw tip on a tight Tie book is backed")
eq(byq["sportsgambler"]["bet"], False, "a tip on an untradeable side is logged but never backed")
ok("polymarket" not in byq, "no Polymarket self-quote is invented on a Kalshi-venue contest")

nfl_k = dict(sport="nfl", venue="kalshi", market_id="KXNFLGAME-X", label="Denver vs Kansas City",
             side_a="Denver", side_b="Kansas City", price_a=0.44, price_b=0.57, price_draw=None,
             tradeable={"a": True, "b": True}, untraded=False,
             start=(now_ + timedelta(days=1)).isoformat(), date="2026-09-14", volume=0.0, url="")
d = {"quotes": [], "meta": {}, "coverage": {}}
S.CHALLENGERS = {"kalshi": lambda sp: [dict(a="Denver", b="Kansas City", prob_a=0.9, date="2026-09-14")]}
T.publish(d, {"nfl": [nfl_k]}, {}, verbose=False)
S.CHALLENGERS = saved
eq([q for q in d["quotes"] if q["source"] == "kalshi"], [],
   "Kalshi is never scored on a contest where Kalshi IS the price")

# A probability on a three-way market must not have its complement inferred.
three = dict(market_id="KXEPLGAME-9", sport="soccer", label="Leeds vs Newcastle",
             side_a="Leeds United", side_b="Newcastle United", price_a=0.40, price_b=0.35,
             price_draw=0.25, untraded=False, venue="kalshi",
             tradeable={"a": True, "b": True, "draw": True},
             start=(now_ + timedelta(days=1)).isoformat(), date="2026-09-14", volume=0.0, url="")
d = {"quotes": [], "meta": {}, "coverage": {}}
S.CHALLENGERS = {"scores24": lambda sp: [dict(a="Leeds United", b="Newcastle United",
                                              prob_a=0.20, date="2026-09-14")]}
T.publish(d, {"soccer": [three]}, {}, verbose=False)
S.CHALLENGERS = saved
logged = [q for q in d["quotes"] if q["source"] == "scores24"]
eq(len(logged), 1, "the three-way quote is logged")
eq(logged[0]["pick"], None,
   "rating the home side BELOW its price is not an away bet — 1-P(home) contains the draw")

# ---------------------------------------------------------------------------
print("\nsettling three-way Kalshi bets")
# ---------------------------------------------------------------------------
def kq(**kw):
    q = quote(sport="soccer", venue="kalshi", market_id="KXEPLGAME-26SEP20FULMUN",
              id="soccerpredictions:KXEPLGAME-26SEP20FULMUN", source="soccerpredictions",
              side_a="Fulham", side_b="Manchester United", price_a=0.27, price_b=0.49,
              pick="draw", price=0.26, bet=True, prob_a=None, edge=None)
    q.update(kw)
    return q

real_k, real_pm = S.resolve_kalshi, S.resolve_polymarket
calls = []
S.resolve_polymarket = lambda mid: calls.append(mid) or "a"
S.resolve_kalshi = lambda mid: "draw"
d = {"quotes": [kq(), kq(id="sportsgambler:X", source="sportsgambler", pick="a", price=0.27)],
     "meta": {}, "coverage": {}}
T.grade(d, verbose=False)
eq(d["quotes"][0]["status"], "won",
   "a correct Draw tip WINS — the previous grader would have scored it lost")
close(d["quotes"][0]["pnl"], round(100 * (1 / 0.26 - 1), 2), "paid at the Tie price it was backed at")
eq(d["quotes"][1]["status"], "lost", "a side backed in a drawn match loses")
close(d["quotes"][1]["pnl"], -100.0, "and costs the full stake — never refunded")
eq(calls, [], "a Kalshi-venue bet is settled by Kalshi, never by Polymarket")
S.resolve_kalshi, S.resolve_polymarket = real_k, real_pm

# ---------------------------------------------------------------------------
print("\ngap-fill de-duplication")
# ---------------------------------------------------------------------------
pm_row = dict(sport="nfl", side_a="Broncos", side_b="Chiefs", date="2026-09-14")
ok(T._same_contest(dict(sport="nfl", side_a="Denver", side_b="Kansas City", date="2026-09-15"), pm_row),
   "a Kalshi game Polymarket already lists is not added a second time")
ok(not T._same_contest(dict(sport="nfl", side_a="Denver", side_b="Kansas City", date="2026-09-21"), pm_row),
   "the same two teams a week later are a different game")
ok(not T._same_contest(dict(sport="nfl", side_a="Seattle", side_b="Arizona", date="2026-09-14"), pm_row),
   "a different fixture is kept as a gap-fill")

# ---------------------------------------------------------------------------
print("\nsoccer club names")
# ---------------------------------------------------------------------------
# The failure that matters is a WRONG match, not a missed one: a tip on AC Milan booked
# against Inter corrupts the record silently.
for x, y, same in [
    ("Manchester United", "Manchester City", False), ("Man Utd", "Manchester United", True),
    ("Inter", "AC Milan", False), ("Milan", "AC Milan", True), ("Inter Milan", "Inter", True),
    ("Internacional", "Inter", False), ("PSG", "Paris FC", False),
    ("Paris Saint-Germain", "PSG", True), ("LA Galaxy", "Los Angeles G", True),
    ("São Paulo", "Sao Paulo", True), ("Newcastle", "Newcastle United", True),
    ("Hertha Berlin", "Union Berlin", False), ("Real Madrid", "Atletico", False),
    ("Rennes", "Stade Rennais", True), ("Stade Brest 29", "Brest", True),
    ("FC Köln", "Cologne", True), ("M´gladbach", "Borussia Monchengladbach", True),
    ("United", "Leeds United", False), ("Inter Miami", "Inter", False),
    ("Twente", "Enschede", True), ("Santos Laguna", "Santos", False),
]:
    got = S._score(x, y, "soccer") >= 0.5
    eq(got, same, f"{x} vs {y}")

# ---------------------------------------------------------------------------
print("\nSportsGambler and SoccerPredictions.ai parsing")
# ---------------------------------------------------------------------------

# Only pages for fixtures a venue prices are fetched — the rest can never be scored.
sg_links = [("/betting-tips/football/aston-villa-vs-nottingham-forest-prediction-lineups-odds-2026-09-12/",
             "2026-09-12"),
            ("/betting-tips/football/shelbourne-vs-derry-city-prediction-lineups-odds-2026-09-12/",
             "2026-09-12")]
sg_rows = [dict(sport="soccer", side_a="Aston Villa", side_b="Nottingham Forest", date="2026-09-12")]
eq([p for p, _ in S.sportsgambler_priced(sg_links, sg_rows)], [sg_links[0][0]],
   "a SportsGambler page is fetched only when Kalshi prices that fixture")
eq(S.sportsgambler_priced(sg_links, None), sg_links,
   "with no universe known (a standalone run) nothing is filtered out")
eq(S.sportsgambler_priced(sg_links, []), [],
   "with an empty universe nothing is fetched, since nothing could be priced")
def sg_page(title, home="Osasuna", away="Espanyol"):
    return (f'<h2>{home} vs {away} Predictions</h2><div class="content-block">'
            f'<div class="expert-pick"><span>Main Match Prediction</span></div>'
            f'<div class="tip--card__block"><h3 class="tip--card__title"> {title} </h3></div>')

eq(S.parse_sportsgambler(sg_page("Osasuna To Win @ +107"))["pick"], "a",
   "a home To Win tip backs side A")
eq(S.parse_sportsgambler(sg_page("Espanyol To Win @ +250"))["pick"], "b",
   "an away To Win tip backs side B")
eq(S.parse_sportsgambler(sg_page("Draw @ +230"))["pick"], "draw", "a Draw tip is kept as a draw")
for t_ in ("Over 2.5 Goals @ -115", "Bournemouth Asian Hcp 0.0 @ -132",
           "Both Teams To Score - Yes @ -116", "Osasuna To Win & Over 2.5 @ +300"):
    eq(S.parse_sportsgambler(sg_page(t_)), None, f"not a result pick, not scored: {t_}")
eq(S.parse_sportsgambler("<h2>Nothing here</h2>"), None, "a page with no main prediction yields nothing")


def sp_row(url, home, away, tip):
    return (f'<div class="tipsrow"><div class="ml__link"><a href="{url}" class="ml__link p-0" title="x">'
            f'<div class="tipscell tipscell--time muted"><div class="tipscell__text">19:30</div></div>'
            f'<div class="tipscell tipscell--grow"><div class="tipscell__text">'
            f'<div class="tipscell__text__name">{home}</div></div><div class="tipscell__text">'
            f'<div class="tipscell__text__name">{away}</div></div></div>'
            f'<div class="tipscell tipscell--right tipscell--score"><div class="tipscell__text fw-500">'
            f'<span>{tip}</span></div><div class="tipscell__text muted"><span class="oddspan">Odds:</span>'
            f'<span>2.30</span></div></div></a></div></div>')

base = "https://soccerpredictions.ai/"
page = (sp_row(base + "union-berlin-v-schalke-prediction-date-2026-09-11", "Union Berlin", "Schalke", "Home")
        + sp_row(base + "rennes-v-marseille-prediction-date-2026-09-11", "Rennes", "Marseille", "Home & Over 2.5")
        + sp_row(base + "nurnberg-v-hannover-96-prediction-date-2026-09-11", "Nurnberg", "Hannover 96", "Draw")
        + sp_row(base + "venezia-v-fiorentina-prediction-date-2026-09-12", "Venezia", "Fiorentina", "Away"))
eq([(g["a"], g["pick"], g["date"]) for g in S.parse_soccerpredictions(page)],
   [("Union Berlin", "a", "2026-09-11"), ("Nurnberg", "draw", "2026-09-11"), ("Venezia", "b", "2026-09-12")],
   "only plain Home / Away / Draw survive, combined tips are dropped, the date comes from the URL")

# ---------------------------------------------------------------------------
print("\nfeed health check")
# ---------------------------------------------------------------------------
import sandbox_build as BUILD

# Silent on a healthy run, or the reader learns to ignore it.
healthy = {"coverage": {"cricket": {"oddspedia": 4}, "nfl": {"covers": 12},
                        "mlb": {"covers": 1}}, "quotes": []}
eq(BUILD.feed_health(healthy), "", "no warning when every source reported something")

# One quiet sport is an empty fixture list, not a broken feed.
quiet = {"coverage": {"nfl": {"covers": 0}, "mlb": {"covers": 3}}, "quotes": []}
eq(BUILD.feed_health(quiet), "",
   "a source quiet in ONE sport is not flagged — NFL has no games on a Tuesday")

# Dark everywhere is the real failure and must be loud.
dark = {"coverage": {"nfl": {"covers": 0}, "mlb": {"covers": 0}}, "quotes": []}
out = BUILD.feed_health(dark)
ok("Feed check" in out and "Covers" in out,
   "a source empty across every sport it covers IS flagged as a broken feed")

# A source never asked about must not be reported as dark.
eq(BUILD.feed_health({"coverage": {"nfl": {}}, "quotes": []}), "",
   "a source with no coverage entry at all is not accused of being down")

# ---------------------------------------------------------------------------
print("\nnetwork failures never crash the run")
# ---------------------------------------------------------------------------
# Both of these were real: a Polymarket connection dropped mid-run and, because the fetch
# helper did not catch that exception type, the whole run died without grading or saving.
import http.client
import subprocess as _sp
import urllib.request as _ur

real_open, real_run, real_sleep = _ur.urlopen, _sp.run, S.time.sleep
def _dropped(*a, **k):
    raise http.client.RemoteDisconnected("Remote end closed connection without response")
_ur.urlopen = _dropped
_sp.run = lambda *a, **k: type("R", (), {"stdout": ""})()
S.time.sleep = lambda s_: None
try:
    try:
        S._get("https://example.invalid/x", tries=2, timeout=1)
        ok(False, "a dropped connection surfaces as a handled RuntimeError")
    except RuntimeError:
        ok(True, "a dropped connection surfaces as a handled RuntimeError, not a crash")
finally:
    _ur.urlopen, _sp.run, S.time.sleep = real_open, real_run, real_sleep

real_pm_fetch, real_kv_fetch = S.fetch_polymarket, S.fetch_kalshi_venue
def _pm_flaky(sport, stats=None):
    if sport == "nfl":
        raise http.client.RemoteDisconnected("dropped")
    return []
S.fetch_polymarket = _pm_flaky
S.fetch_kalshi_venue = lambda sport, stats=None: []
try:
    # The failure line collect() prints is correct behaviour, but printed from a test it
    # lands in every CI log as "! polymarket/nfl failed" — a false alarm on each run,
    # which is exactly how a real failure line gets ignored.
    import contextlib, io
    with contextlib.redirect_stdout(io.StringIO()):
        uni_, cov_ = T.collect(verbose=False)
    ok(set(uni_) == set(S.SPORTS) and uni_["nfl"] == [],
       "one venue failing for one sport leaves every other sport's collection intact")
finally:
    S.fetch_polymarket, S.fetch_kalshi_venue = real_pm_fetch, real_kv_fetch

# ---------------------------------------------------------------------------
print(f"\n{'FAILED: ' + str(len(FAILS)) if FAILS else 'all sandbox tests passed'}")
for f in FAILS:
    print("   -", f)
sys.exit(1 if FAILS else 0)
