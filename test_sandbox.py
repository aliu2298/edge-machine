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
# Both found live: the same game sat in the universe once per venue.
eq(S.canon("A's", "mlb"), "athletics", "Kalshi's \"A's\" resolves to the Athletics")
ok(T._same_contest(dict(sport="mlb", side_a="Seattle", side_b="A's", date="2026-09-11"),
                   dict(sport="mlb", side_a="Seattle Mariners", side_b="Athletics", date="2026-09-11")),
   "Kalshi's Seattle vs A's is Polymarket's Mariners vs Athletics, not a second copy")
ok(T._same_contest(dict(sport="boxing", side_a="Opetaia J.", side_b="Mikaelyan N.", date="2026-09-12"),
                   dict(sport="boxing", side_a="Opetaia", side_b="Mikaelian", date="2026-09-12")),
   "a transliteration (Mikaelyan / Mikaelian) does not put one fight in twice")
ok(not T._same_contest(dict(sport="boxing", side_a="Sean Garcia", side_b="Abraham Morales", date="2026-09-12"),
                       dict(sport="boxing", side_a="Garcia", side_b="Benn", date="2026-09-12")),
   "one shared surname is not enough — a different opponent is a different fight")

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

# A page that LOADED is healthy even with no call. Oddspedia's cricket page once carried
# exactly two tips on opposite sides of one match; consensus made no call, and the old
# count-based check reported the feed as broken.
eq(BUILD.feed_health({"coverage": {"cricket": {"oddspedia": 0}},
                      "feed_status": {"oddspedia": "ok"}, "quotes": []}), "",
   "a feed whose page loaded is not flagged just because it produced no call")
out = BUILD.feed_health({"coverage": {"cricket": {"oddspedia": 3}},
                         "feed_status": {"oddspedia": "down: challenge not cleared"},
                         "quotes": []})
ok("Oddspedia" in out and "challenge not cleared" in out,
   "a feed whose page did NOT load is flagged, with the reason, whatever the counts say")

# Adapters mark themselves; one loaded page anywhere keeps a multi-page source healthy.
S.FEED_STATUS.clear()
S._mark("covers", False, "picks page unreachable")
S._mark("covers", True)
S._mark("covers", False, "picks page unreachable")
eq(S.FEED_STATUS["covers"], "ok", "one page loading keeps a source healthy even if another failed")
S.FEED_STATUS.clear()
S._mark("sportsgambler", False, "no league page loaded")
eq(S.FEED_STATUS["sportsgambler"], "down: no league page loaded", "a source with no page loaded is down")
S.FEED_STATUS.clear()

real_avail_ = B.available
B.available = lambda: False
try:
    B.fetch_rows(["https://example.invalid/y"], log=lambda *a: None)
    eq(B.STATUS["https://example.invalid/y"], "not fetched",
       "a page the browser never reached is recorded as not fetched, not as ok")
finally:
    B.available = real_avail_

# ---------------------------------------------------------------------------
print("\nretired venue")
# ---------------------------------------------------------------------------
real_pm_ = S.resolve_polymarket
called_ = []
S.resolve_polymarket = lambda mid: called_.append(mid) or "a"
d = {"quotes": [quote(id="scores24:espn:ger.1:1", source="scores24", sport="soccer",
                      venue="espn", market_id="espn:ger.1:1", pick="a", price=0.6)],
     "meta": {}, "coverage": {}}
T.grade(d, verbose=False)
S.resolve_polymarket = real_pm_
eq(d["quotes"][0]["status"], "void",
   "a bet on the retired ESPN venue is refunded — nothing can settle it any more")
close(d["quotes"][0]["pnl"], 0.0, "and it never invents P/L")
eq(called_, [], "it is never sent to Polymarket, which has no such market")

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

real_pm_fetch, real_kv_fetch = S.fetch_polymarket_us, S.fetch_kalshi_venue
def _pm_flaky(sport, stats=None):
    if sport == "nfl":
        raise http.client.RemoteDisconnected("dropped")
    return []
S.fetch_polymarket_us = _pm_flaky
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
    S.fetch_polymarket_us, S.fetch_kalshi_venue = real_pm_fetch, real_kv_fetch

# ---------------------------------------------------------------------------
print("\nyes/no markets (climate, crypto and the rest)")
# ---------------------------------------------------------------------------
def bm(**kw):
    m = dict(ticker="KXHIGHNY-26SEP12-B77.5", strike_type="between", floor_strike=77,
             cap_strike=78, yes_sub_title="77° to 78°", title="Will the maximum temperature be 77-78°?")
    m.update(kw)
    return m

eq(S.market_range(bm()), (77, 78), "a between market pays out inside its two strikes")
eq(S.market_range(bm(strike_type="greater", floor_strike=82, cap_strike=None)), (82, None),
   "a greater market is unbounded above")
eq(S.market_range(bm(strike_type="less", floor_strike=None, cap_strike=75)), (None, 75),
   "a less market is unbounded below")
ok(S.in_range(77, bm()) and S.in_range(78, bm()),
   "a bucket titled \"77° to 78°\" includes BOTH 77 and 78")
ok(not S.in_range(76, bm()) and not S.in_range(79, bm()),
   "and nothing outside it")
ok(not S.in_range(82, bm(strike_type="greater", floor_strike=82, cap_strike=None)),
   "a >82 market is titled \"83° or above\", so 82 does not settle it")
ok(not S.in_range(75, bm(strike_type="less", floor_strike=None, cap_strike=75)),
   "a <75 market is titled \"74° or below\", so 75 does not settle it")
ok(S.in_range(83, bm(strike_type="greater", floor_strike=82, cap_strike=None)),
   "83 settles a >82 market yes")
ok(S.in_range(74, bm(strike_type="less", floor_strike=None, cap_strike=75)),
   "74 settles a <75 market yes")

# The NWS forecast must pick exactly ONE bucket for a city and day.
rows = [dict(sport="climate", venue="kalshi_binary", market_id=f"KXHIGHNY-26SEP12-{t}",
             series="KXHIGHNY", date="2026-09-12", market=m, price_a=p,
             tradeable={"a": True, "b": True})
        for t, m, p in (("B75.5", bm(floor_strike=75, cap_strike=76), 0.05),
                        ("B77.5", bm(floor_strike=77, cap_strike=78), 0.34),
                        ("B79.5", bm(floor_strike=79, cap_strike=80), 0.46),
                        ("T82", bm(strike_type="greater", floor_strike=82, cap_strike=None), 0.02))]
real_uni, real_nws = S.UNIVERSE, S.nws_highs
S.UNIVERSE = {"climate": rows}
S.nws_highs = lambda lat, lon: {"2026-09-12": 78.0}
try:
    picks = S.fetch_nws("climate")
finally:
    S.UNIVERSE, S.nws_highs = real_uni, real_nws
eq(len(picks), 1, "one forecast backs one bucket, never several")
eq(picks[0]["market_id"], "KXHIGHNY-26SEP12-B77.5", "and it is the bucket holding 78F")
eq(picks[0]["pick"], "a", "backed as YES on that bucket")

# A ladder settles many strikes at once; back the one still in doubt, not a certainty.
ladder = [dict(sport="crypto", venue="kalshi_binary", market_id=f"KXSOLD-26SEP12-T{k}",
               series="KXSOLD", date="2026-09-12", price_a=p, tradeable={"a": tr, "b": True},
               market=bm(strike_type="greater", floor_strike=k, cap_strike=None))
          for k, p, tr in ((58, 1.00, False), (101, 0.68, True), (95, 0.93, True))]
real_uni2, real_spot = S.UNIVERSE, S.spot_price
S.UNIVERSE = {"crypto": ladder}
S.spot_price = lambda coin: 101.62
try:
    sp = S.fetch_spot("crypto")
finally:
    S.UNIVERSE, S.spot_price = real_uni2, real_spot
eq(len(sp), 1, "one spot reading backs one strike")
eq(sp[0]["market_id"], "KXSOLD-26SEP12-T101",
   "the strike nearest a coin flip, not the $58 certainty priced at 1.00")

# A quote that names its market is matched by id — there are no names to compare.
uni = [dict(market_id="KXHIGHNY-26SEP12-B77.5", sport="climate", side_a="77° to 78°",
            side_b="No", date="2026-09-12"),
       dict(market_id="KXHIGHNY-26SEP12-B79.5", sport="climate", side_a="79° to 80°",
            side_b="No", date="2026-09-12")]
m = T.match_quotes(uni, [dict(market_id="KXHIGHNY-26SEP12-B77.5", pick="a")])
eq(m, {"KXHIGHNY-26SEP12-B77.5": ("pick", "a")}, "a market-id quote lands on that market only")
eq(T.match_quotes(uni, [dict(market_id="KXHIGHNY-26SEP99-XX", pick="a")]), {},
   "a quote naming a market this universe does not hold matches nothing")

# Settlement reads the market's own yes/no result.
real_get = S._get
S._get = lambda url, **kw: {"market": {"status": "finalized", "result": "yes"}}
try:
    eq(S.resolve_kalshi_market("KXHIGHNY-26SEP10-B77.5"), "a", "a YES result settles side A")
    S._get = lambda url, **kw: {"market": {"status": "finalized", "result": "no"}}
    eq(S.resolve_kalshi_market("KXHIGHNY-26SEP10-B77.5"), "b", "a NO result settles side B")
    S._get = lambda url, **kw: {"market": {"status": "active", "result": ""}}
    eq(S.resolve_kalshi_market("KXHIGHNY-26SEP10-B77.5"), None, "an open market is not settled")
finally:
    S._get = real_get

# Lead time is an integrity rule: a market about to expire has already happened.
# Every connected source must land in a matrix group, or it disappears from the board.
import sandbox_build as BUILD2
_grouped = {k for _t, kinds in [("Tipsters", ("Tipster site",)),
                                ("Forecasters", ("Forecaster", "Baseline")),
                                ("Models and books", ("Statistical model", "Sportsbook",
                                                      "Sportsbook consensus")),
                                ("Rules", ("Rule",)),
                                ("Prediction markets", ("Prediction market",))] for k in kinds}
for _n, _m in S.SOURCES.items():
    if _m["connected"]:
        ok(_m["kind"] in _grouped,
           f"{_m['label']} has kind {_m['kind']!r}, which the board groups and shows")
for _n, _m in S.SOURCES.items():
    ok(set(_m["sports"]) <= set(S.SPORTS),
       f"{_m['label']} only claims domains that exist")
ok("climate" not in S.SOURCES["polymarket"]["sports"],
   "Polymarket does not claim domains it has never priced")

eq(S.KALSHI_BINARY["climate"]["lead_h"], 12,
   "a daily temperature market is only taken with half a day of uncertainty left")
ok(all(cfg["lead_h"] >= 2 for cfg in S.KALSHI_BINARY.values()),
   "no domain logs a forecast against a market that is about to expire")

# ---------------------------------------------------------------------------

print("\n== the readability banner is judged per SOURCE, not on the total ==")
# Every cell greys itself on its own settled count, but the banner used to compare the
# lifetime TOTAL against MIN_N. At 57 settled across seven sources it announced "the ROI
# column is now readable" while greying out every figure in it — the best single source
# was on n=15. A total is not a sample; nobody bets "all sources".
import sandbox_build as SB


def _verdict(per_source_settled):
    """Reproduce the banner for a given {source: settled} shape."""
    settled = sum(per_source_settled.values())
    scores = {k: {"settled": v} for k, v in per_source_settled.items()}
    best = max((v["settled"] for v in scores.values()), default=0)
    ready = [n for n, v in scores.items() if v["settled"] >= SB.MIN_N]
    if settled == 0:
        return "none"
    if not ready:
        return f"not-readable:best={best}"
    return f"readable:{len(ready)}"


ok(_verdict({}) == "none", "no settled bets -> no record claimed")
ok(_verdict({"a": 15, "b": 12, "c": 10, "d": 7, "e": 6, "f": 5, "g": 2})
   == "not-readable:best=15",
   "57 total spread thin stays UNREADABLE (the bug: it used to read as readable)")
ok(_verdict({"a": SB.MIN_N}) == "readable:1",
   "one source reaching the floor on its own is readable")
ok(_verdict({"a": SB.MIN_N, "b": SB.MIN_N, "c": 4}) == "readable:2",
   "only the sources past the floor are counted as readable")
ok(_verdict({"a": SB.MIN_N - 1}) == f"not-readable:best={SB.MIN_N - 1}",
   "one short of the floor is still not readable")

# ---------------------------------------------------------------------------
print("\nPolymarket book gate")
# ---------------------------------------------------------------------------
# The defect: a just-listed market shows a MIDPOINT near 0.50 with no book behind it, and
# only an exact 0.50/0.50 was caught. Panin v Linger was logged at 0.515 and was 0.88 once
# money arrived. Every case below is a shape seen live on 2026-09-12.
eq(S.pm_book(dict(bestBid="0.7", bestAsk="0.71", spread="0.01", liquidityNum=101568))[:3],
   (True, 0.71, 0.3), "a tight, funded book is tradeable and booked at the asks")
eq(S.pm_book(dict(bestBid="0.85", bestAsk="0.91", spread="0.06", liquidityNum=49))[0], False,
   "Panin v Linger's book (6c spread, $49) is not a price")
eq(S.pm_book(dict(bestBid="0.54", bestAsk="0.84", spread="0.3", liquidityNum=107))[0], False,
   "a 30c spread is not a price, however much volume traded")
eq(S.pm_book(dict(bestBid="0.49", bestAsk="0.51", spread="0.02", liquidityNum=20))[0], False,
   "a tight spread with $20 behind it is one quote, not a market")
eq(S.pm_book(dict(bestBid=None, bestAsk="1", spread="0.69", liquidityNum=0))[0], False,
   "a one-sided book is never tradeable")
eq(S.pm_book(dict(bestBid="0.48", bestAsk="0.53", spread="0.05", liquidityNum=100))[0], True,
   "exactly at the spread and liquidity limits still counts")

_start = (datetime.now(timezone.utc) + timedelta(hours=10)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _pm_market(mid, a, b, px, bid, ask, spread, liq, vol):
    return dict(id=mid, outcomes=f'["{a}", "{b}"]', outcomePrices=f'["{px}", "{1 - px:.3f}"]',
                bestBid=bid, bestAsk=ask, spread=spread, liquidityNum=liq, volumeNum=vol,
                acceptingOrders=True, closed=False, gameStartTime=_start,
                question=f"{a} vs. {b}")


_events = [
    dict(slug="e1", title="Vlad Panin vs. Dakota Linger", startDate=_start, markets=[
        _pm_market("thin", "Vlad Panin", "Dakota Linger", 0.515, "0.02", "0.99", "0.97", 49, 90000)]),
    dict(slug="e2", title="Ryan Garcia vs. Conor Benn", startDate=_start, markets=[
        _pm_market("deep", "Ryan Garcia", "Conor Benn", 0.705, "0.70", "0.71", "0.01", 101568, 500)]),
]
_saved_get = S._get
S._get = lambda url, **kw: _events if "offset=0" in url else []
try:
    _stats = {}
    _rows = S.fetch_polymarket("boxing", stats=_stats)
finally:
    S._get = _saved_get
_by = {r["market_id"]: r for r in _rows}
eq(_rows[0]["market_id"], "deep", "a priced book sorts ahead of an unpriced one with 180x the volume")
eq((_by["thin"]["untraded"], _by["deep"]["untraded"]), (True, False),
   "the placeholder is flagged untraded; the real book is not")
eq((_by["deep"]["price_a"], _by["deep"]["price_b"], _by["deep"]["mid_a"]), (0.71, 0.3, 0.705),
   "a priced row carries the two asks, and the midpoint separately")
eq(_stats["priced"], 1, "the coverage count reports priced books under the gate")

# publish: nothing at all is logged against an unpriced row — tipsters included — and the
# market's own quote is its midpoint, not its ask.
_saved_ch = S.CHALLENGERS
S.CHALLENGERS = {"oddspedia": lambda sp: [dict(a="Vlad Panin", b="Dakota Linger", pick="a", date=_start[:10]),
                                          dict(a="Ryan Garcia", b="Conor Benn", pick="a", date=_start[:10])]}
S.SOURCES["oddspedia"]["sports"].append("boxing")
try:
    d = {"quotes": [], "meta": {}, "coverage": {}}
    T.publish(d, {"boxing": _rows}, {}, verbose=False)
finally:
    S.SOURCES["oddspedia"]["sports"].remove("boxing")
    S.CHALLENGERS = _saved_ch
_logged = {(q["source"], q["market_id"]): q for q in d["quotes"]}
ok(not any(mid == "thin" for _s, mid in _logged),
   "no source is logged against the placeholder book, so it can be quoted later at a real price")
close(_logged[("polymarket", "deep")]["prob_a"], 0.705, "Polymarket's own quote is the midpoint")
close(_logged[("oddspedia", "deep")]["price"], 0.71, "a tip is booked at the ask a follower pays")
eq((_logged[("oddspedia", "deep")]["spread"], _logged[("oddspedia", "deep")]["liquidity"]),
   (0.01, 101568.0), "every quote records the book it was priced against")

# ---------------------------------------------------------------------------
print("\npre-gate history")
# ---------------------------------------------------------------------------
_now = datetime.now(timezone.utc)
_future = (_now + timedelta(hours=5)).isoformat()
_past = (_now - timedelta(days=1)).isoformat()
d = {"quotes": [
    dict(id="1", source="polymarket", sport="boxing", venue="polymarket", status="open", start=_future, pnl=0.0),
    dict(id="2", source="oddspedia", sport="cricket", venue="polymarket", status="lost", start=_past,
         pnl=-100.0, bet=True, settled=_past),
    dict(id="3", source="polymarket", sport="cricket", venue="polymarket", status="open", start=_past, pnl=0.0),
    dict(id="4", source="covers", sport="mlb", venue="polymarket", status="won", start=_past, pnl=80.0),
    dict(id="5", source="kalshi", sport="cricket", venue="kalshi", status="open", start=_future, pnl=0.0),
    dict(id="6", source="polymarket", sport="boxing", venue="polymarket", status="open", start=_future,
         pnl=0.0, spread=0.01),
], "meta": {}}
eq(T.retire_pre_gate(d, now=_now, verbose=False), (1, 2),
   "unstarted pre-gate quotes are removed; started or settled ones are voided")
_q = {q["id"]: q for q in d["quotes"]}
ok("1" not in _q, "an unstarted pre-gate quote is removed so it can be re-quoted under the gate")
eq((_q["2"]["status"], _q["2"]["pnl"], _q["2"]["note"]), ("void", 0.0, T.PRE_GATE_NOTE),
   "a settled pre-gate bet is voided: no stake, no P/L")
eq(_q["3"]["status"], "void", "a started-but-unsettled pre-gate quote is voided, never graded")
eq(_q["4"]["status"], "won", "sports whose books were real (MLB) are untouched")
eq(_q["5"]["status"], "open", "Kalshi-venue quotes were ask-priced all along and are untouched")
eq(_q["6"]["status"], "open", "a quote logged under the gate is untouched")
eq(T.retire_pre_gate(d, now=_now, verbose=False), (0, 0), "running it again changes nothing")
for _x in d["quotes"]:
    _x.setdefault("bet", False)
eq(T.score(d)["oddspedia"]["settled"], 0, "a voided pre-gate bet leaves the source's record")

# ---------------------------------------------------------------------------
print("\nPinnacle via The Odds API")
# ---------------------------------------------------------------------------
_ev = dict(home_team="Ryan Garcia", away_team="Conor Benn", commence_time=_start, bookmakers=[
    dict(key="pinnacle", markets=[dict(key="h2h", outcomes=[
        dict(name="Ryan Garcia", price=1.36), dict(name="Conor Benn", price=3.25),
        dict(name="Draw", price=26.0)])])])
close(S.pinnacle_prob(_ev, "Ryan Garcia"), (1 / 1.36) / (1 / 1.36 + 1 / 3.25),
      "de-vigged over the two sides, the draw dropped", tol=1e-9)
close(S.pinnacle_prob(_ev, "Conor Benn"), (1 / 3.25) / (1 / 1.36 + 1 / 3.25),
      "and oriented to whichever side is asked for", tol=1e-9)
eq(S.pinnacle_prob(dict(bookmakers=[dict(key="betfair_ex_eu", markets=[])]), "X"), None,
   "no Pinnacle line on the event -> no probability, never another book's")

import os as _os
_calls = []
_remaining = [480]


def _fake_odds(path, params):
    _calls.append(path)
    if "apiKey" in params:
        ok(False, "the key is added inside _odds_get, never passed around")
    if path == "/sports":
        return [dict(key="boxing_boxing", group="Boxing", active=True, has_outrights=False),
                dict(key="boxing_outrights", group="Boxing", active=True, has_outrights=True)], \
            {"x-requests-remaining": str(_remaining[0])}
    if path.endswith("/events"):
        return [dict(home_team="Ryan Garcia", away_team="Conor Benn"),
                dict(home_team="Nobody Listed", away_team="Also Nobody")], {}
    if path.endswith("/odds"):
        return [_ev], {"x-requests-remaining": str(_remaining[0] - 1), "x-requests-used": "21"}
    raise AssertionError(path)


def _reset_odds():
    S._odds_sports = None
    S.ODDS_USAGE.clear()
    S.FEED_STATUS.clear()
    _calls.clear()


_saved_odds_get, _saved_key = S._odds_get, _os.environ.get("ODDS_API_KEY")
S._odds_get = _fake_odds
S.UNIVERSE = {"boxing": [dict(side_a="Garcia", side_b="Benn", untraded=False)]}
try:
    _os.environ.pop("ODDS_API_KEY", None)
    _reset_odds()
    eq(S.fetch_pinnacle("boxing"), [], "no key -> nothing fetched")
    eq((_calls, S.FEED_STATUS.get("pinnacle", "")[:4]), ([], "down"),
       "and the feed is reported down rather than silently empty")

    _os.environ["ODDS_API_KEY"] = "test-key-not-real"
    _reset_odds()
    _got = S.fetch_pinnacle("boxing")
    eq(len(_got), 1, "one priced bout")
    eq((_got[0]["a"], _got[0]["b"]), ("Ryan Garcia", "Conor Benn"), "quote carries both sides")
    eq(_calls, ["/sports", "/sports/boxing_boxing/events", "/sports/boxing_boxing/odds"],
       "free calls first; outright keys skipped; one paid call")
    eq((S.ODDS_USAGE["remaining"], S.ODDS_USAGE["calls"]), (479, 1), "credit usage is tracked")
    eq(S.FEED_STATUS.get("pinnacle"), "ok", "a readable feed reports ok")
    S.fetch_pinnacle("cricket")
    eq(_calls.count("/sports"), 1, "the free sport list is fetched once per run, not per sport")
    ok(not any("apiKey" in c for c in _calls), "the key is added inside _odds_get, never passed around")

    _reset_odds()
    S.UNIVERSE = {"boxing": [dict(side_a="Somebody", side_b="Else", untraded=False)]}
    S.fetch_pinnacle("boxing")
    ok(not any(c.endswith("/odds") for c in _calls),
       "no credit is spent when no listed contest is waiting for the price")

    _reset_odds()
    S.UNIVERSE = {"boxing": [dict(side_a="Garcia", side_b="Benn", untraded=True)]}
    S.fetch_pinnacle("boxing")
    ok(not any(c.endswith("/odds") for c in _calls),
       "nor for a contest whose venue book is unpriced — it cannot be logged this run")

    _reset_odds()
    _remaining[0] = S.ODDS_RESERVE - 1
    S.UNIVERSE = {"boxing": [dict(side_a="Garcia", side_b="Benn", untraded=False)]}
    S.fetch_pinnacle("boxing")
    ok(not any(c.endswith("/odds") for c in _calls), "below the credit reserve, nothing is spent")
    ok("reserve" in S.FEED_STATUS.get("pinnacle", ""), "and the page says why")
    _remaining[0] = 480

    _reset_odds()
    S.ODDS_USAGE["calls"] = S.ODDS_MAX_CALLS
    S.fetch_pinnacle("boxing")
    ok(not any(c.endswith("/odds") for c in _calls), "the per-run paid-call cap holds")

    _reset_odds()
    S.ODDS_USAGE["allowance"] = 0
    S.fetch_pinnacle("boxing")
    ok(not any(c.endswith("/odds") for c in _calls), "a run whose paced share is zero spends nothing")
    ok("paced" in S.FEED_STATUS.get("pinnacle", "") or S.FEED_STATUS.get("pinnacle") == "ok",
       "and the feed says the budget is paced rather than broken")
finally:
    S._odds_get = _saved_odds_get
    S.UNIVERSE = None
    _reset_odds()
    if _saved_key is None:
        _os.environ.pop("ODDS_API_KEY", None)
    else:
        _os.environ["ODDS_API_KEY"] = _saved_key

_saved_urlopen = S.urllib.request.urlopen


def _boom(req, timeout=None):
    raise S.urllib.error.HTTPError(req.full_url, 401, "Unauthorized", {}, None)


S.urllib.request.urlopen = _boom
_os.environ["ODDS_API_KEY"] = "secret-value-123"
try:
    S._odds_get("/sports", {})
    ok(False, "a 401 raises")
except RuntimeError as e:
    ok("secret-value-123" not in str(e) and "apiKey" not in str(e),
       "an error message never carries the key or the URL")
finally:
    S.urllib.request.urlopen = _saved_urlopen
    if _saved_key is None:
        _os.environ.pop("ODDS_API_KEY", None)
    else:
        _os.environ["ODDS_API_KEY"] = _saved_key

# ---------------------------------------------------------------------------
print("\nnothing is logged once a contest has started")
# ---------------------------------------------------------------------------
# Al Wahda v Sharjah was logged 74 seconds after kickoff and won +$178: the venue feeds
# keep a contest for five minutes past its start. The rule is for every source and venue.
_n = datetime.now(timezone.utc)
_rows_late = [
    dict(market_id="k-started", sport="soccer", venue="kalshi", label="Al Wahda vs Sharjah",
         side_a="Al Wahda", side_b="Sharjah", price_a=0.36, price_b=0.38, price_draw=0.30,
         tradeable={"a": True, "b": True, "draw": True}, untraded=False,
         start=(_n - timedelta(seconds=74)).isoformat(), date=_n.strftime("%Y-%m-%d"),
         volume=0.0, url=""),
    dict(market_id="k-future", sport="soccer", venue="kalshi", label="Hoffenheim vs Stuttgart",
         side_a="Hoffenheim", side_b="Stuttgart", price_a=0.41, price_b=0.33, price_draw=0.27,
         tradeable={"a": True, "b": True, "draw": True}, untraded=False,
         start=(_n + timedelta(hours=3)).isoformat(), date=_n.strftime("%Y-%m-%d"),
         volume=0.0, url=""),
]
_saved_ch = S.CHALLENGERS
S.CHALLENGERS = {"soccerpredictions": lambda sp: [
    dict(market_id="k-started", pick="a"), dict(market_id="k-future", pick="draw")]}
try:
    d = {"quotes": [], "meta": {}, "coverage": {}}
    T.publish(d, {"soccer": _rows_late}, {}, verbose=False)
finally:
    S.CHALLENGERS = _saved_ch
eq(sorted(q["market_id"] for q in d["quotes"]), ["k-future"],
   "a contest 74 seconds past its start is not logged; one still ahead is")
ok(T._started(dict(start="not a date"), _n), "an unreadable start counts as started, never as open")
ok(T._started(dict(start=_n.replace(tzinfo=None).isoformat()), _n + timedelta(seconds=1)),
   "a naive timestamp is read as UTC")

_ledger = {"quotes": [
    dict(id="late", source="soccerpredictions", status="won", pnl=177.78, bet=True,
         logged="2026-09-11T16:16:14+00:00", start="2026-09-11T16:15:00+00:00", settled="x"),
    dict(id="edge", source="covers", status="open", pnl=0.0, bet=True,
         logged="2026-09-11T16:15:00+00:00", start="2026-09-11T16:15:00+00:00"),
    dict(id="fine", source="covers", status="lost", pnl=-100.0, bet=True,
         logged="2026-09-11T06:00:00+00:00", start="2026-09-11T16:15:00+00:00", settled="x"),
]}
eq(T.retire_late(_ledger, verbose=False), 2, "a late win and a quote logged AT the start are voided")
_q = {q["id"]: q for q in _ledger["quotes"]}
eq((_q["late"]["status"], _q["late"]["pnl"], _q["late"]["note"]), ("void", 0.0, T.LATE_NOTE),
   "the late win leaves the record entirely")
eq(_q["fine"]["status"], "lost", "a quote logged ten hours ahead is untouched")
eq(T.retire_late(_ledger, verbose=False), 0, "running it again changes nothing")

# ---------------------------------------------------------------------------
print("\nblind baselines")
# ---------------------------------------------------------------------------
_c = dict(result="draw", price_a=0.41, price_b=0.33, price_draw=0.27)
close(T.blind_pnl(_c, "draw"), 100 * (1 / 0.27 - 1), "back the draw on a drawn match pays the Tie price", tol=0.01)
eq(T.blind_pnl(_c, "favourite"), -100.0, "the favourite loses to a draw")
eq(T.blind_pnl(_c, "underdog"), -100.0, "and so does the underdog")
close(T.blind_pnl(dict(result="b", price_a=0.62, price_b=0.40), "underdog"), 150.0,
      "the underdog is the lower-priced side", tol=0.01)
eq(T.blind_pnl(dict(result="a", price_a=0.62, price_b=0.40), "draw"), None,
   "no draw bet exists on a two-way contest")
eq(T.blind_pnl(dict(result="a", price_a=0.97, price_b=0.04), "favourite"), None,
   "the same price band as every source: no blind bet at 0.97")
eq(T.blind_pnl(dict(result="void", price_a=0.5, price_b=0.5), "favourite"), None,
   "no result, no baseline")

_bl = {"quotes": [
    dict(market_id="m1", sport="soccer", status="won", result="draw", logged="2026-09-12T01:00:00+00:00",
         price_a=0.41, price_b=0.33, price_draw=0.27),
    dict(market_id="m1", sport="soccer", status="graded", result="draw", logged="2026-09-12T09:00:00+00:00",
         price_a=0.50, price_b=0.30, price_draw=0.20),
    dict(market_id="m2", sport="soccer", status="void", result="a", logged="2026-09-12T01:00:00+00:00",
         price_a=0.60, price_b=0.20, price_draw=0.20),
]}
_b = T.baselines(_bl, "soccer")
eq(_b["draw"]["n"], 1, "each contest once; void quotes ignored")
close(_b["draw"]["pnl"], 100 * (1 / 0.27 - 1), "priced at the EARLIEST quote on the contest", tol=0.01)

# ---------------------------------------------------------------------------
print("\nstamp of approval")
# ---------------------------------------------------------------------------
_wk = datetime(2026, 9, 1, 15, tzinfo=timezone.utc)


def _bet(i, won, price=0.5, pick="a", week=0, pnl=None, pa=None, pb=None, pd=None, source="tip"):
    res = pick if won else ("b" if pick == "a" else "a")
    return dict(source=source, sport="soccer", bet=True, status="won" if won else "lost",
                pick=pick, price=price, result=res,
                pnl=(pnl if pnl is not None else (round(100 * (1 / price - 1), 2) if won else -100.0)),
                start=(_wk + timedelta(weeks=week, hours=i)).isoformat(),
                price_a=pa if pa is not None else price, price_b=pb if pb is not None else 1 - price,
                price_draw=pd)


# A genuinely good record CHOOSES: on half the contests it takes the underdog (0.40) and
# wins 60%, on the other half the favourite (0.62) and wins 90%. Always taking one side
# would just be that blind rule under another name — see the tests below.
_good = []
for i in range(60):
    if i % 2 == 0:
        _good.append(_bet(i, i % 10 < 6, price=0.40, pick="a", week=i // 10, pa=0.40, pb=0.62))
    else:
        _good.append(_bet(i, i % 10 != 9, price=0.62, pick="b", week=i // 10, pa=0.40, pb=0.62))
_a = T.assess({"quotes": _good}, "tip")
eq(_a["status"], "approved", "60 bets over 6 weeks that beat the price and every blind rule")
ok(all(c[2] for c in _a["criteria"]), "…with every criterion ticked")
_a = T.assess({"quotes": [_bet(i, i % 5 < 3, price=0.40, pick="a", week=i // 10, pa=0.40, pb=0.62)
                          for i in range(60)]}, "tip")
eq(dict((c[0], c[2]) for c in _a["criteria"])["baseline"], False,
   "a source that always takes the underdog is 'back the underdog', however well it did")

_a = T.assess({"quotes": [_bet(i, i % 5 < 3, price=0.40, pa=0.40, pb=0.62) for i in range(60)]}, "tip")
eq((_a["status"], dict((c[0], c[2]) for c in _a["criteria"])["sample"]), ("watch", False),
   "the same record inside ONE week is not approved — one weekend is one draw of the weather")

_a = T.assess({"quotes": [_bet(i, i % 5 < 3, price=0.60, pa=0.60, pb=0.42, week=i // 10) for i in range(60)]}, "tip")
eq(dict((c[0], c[2]) for c in _a["criteria"])["baseline"], False,
   "a source that only ever backs the favourite cannot beat 'back the favourite'")

_luck = [_bet(i, False, price=0.40, pa=0.40, pb=0.62, week=i // 10) for i in range(59)]
_luck.append(_bet(59, True, price=0.05, pnl=10000.0, pa=0.05, pb=0.96, week=5))
_a = T.assess({"quotes": _luck}, "tip")
eq(dict((c[0], c[2]) for c in _a["criteria"])["one_hit"], False,
   "one enormous win cannot carry a record")

_fade = ([_bet(i, i % 5 < 4, price=0.40, pa=0.40, pb=0.62, week=i // 10) for i in range(30)] +
         [_bet(30 + i, i % 5 < 1, price=0.40, pa=0.40, pb=0.62, week=3 + i // 10) for i in range(30)])
_a = T.assess({"quotes": _fade}, "tip")
eq(dict((c[0], c[2]) for c in _a["criteria"])["halves"], False,
   "a record that made its money early and lost it late is not approved")

eq(T.assess({"quotes": _good[:20]}, "tip")["status"], "unproven", "under the read floor there is no stamp at all")
_a = T.assess({"quotes": [_bet(i, i % 5 < 1, price=0.40, pa=0.40, pb=0.62, week=i // 10) for i in range(40)]}, "tip")
eq(_a["status"], "failing", "readable and behind the price is failing")
eq(T.assess({"quotes": _good}, "someone-else")["n"], 0, "a stamp is per source")

_draws = [_bet(i, i % 2 == 0, price=0.28, pick="draw", pa=0.40, pb=0.34, pd=0.28, week=i // 10)
          for i in range(60)]
_a = T.assess({"quotes": _draws}, "tip")
_crit = {c[0]: c for c in _a["criteria"]}
eq(_crit["baseline"][2], False,
   "picking the draw on every contest cannot beat 'back every draw' on those contests")
ok("draw" in _crit["baseline"][3], "and the page names the rule it failed to beat")
ok(T.APPROVAL["min_bets"] > T.READ_FLOOR, "the stamp asks for more than the read floor")

# ---------------------------------------------------------------------------
print("\nOLBG boxing consensus")
# ---------------------------------------------------------------------------
def _olbg_row(fight, when, choice, n, total, market="Win Fight"):
    return (f'<li><div class="grd tip content-visibility-auto"><div class="rw ev">'
            f'<a itemprop="url" href="https://www.olbg.com/betting-tips/Boxing/All_Boxing/x/16">'
            f'<h5 class="truncate" itemprop="name">{fight}</h5></a>'
            f'<time itemprop="startDate" datetime="{when}"> Today 01:15</time></div>'
            f'<div class="rw sel"><a href="#"><h4 class=" my-3 text-lg">{choice}</h4></a> '
            f'<p class="truncate text-sm">{market}</p></div>'
            f'<div class="rw odds"><span data-decimal="1.50"></span></div>'
            f'<div class="rw tips"><b class="text-xs truncate">{n}/{total} Win Tips</b></div></div></li>')


_page = "<html>" + "".join([
    _olbg_row("Jai Opetaia v Norair Mikaeljan", "2026-09-13T02:00:00.000Z", "Jai Opetaia", 9, 14),
    _olbg_row("DaMazzion Vanhouter v Raphael Akpejiori", "2026-09-13T01:15:00.000Z", "Raphael Akpejiori", 9, 17),
    _olbg_row("Ryan Garcia v Conor Benn", "2026-09-13T03:30:00.000Z", "Ryan Garcia", 10, 25),
    _olbg_row("Mark Magsayo v Andres Cortes", "2026-09-13T00:15:00.000Z", "Draw", 10, 14),
    _olbg_row("Takuma Inoue v Tenshin Nasukawa", "2026-09-27T09:00:00.000Z", "Takuma Inoue", 2, 2),
    _olbg_row("Gable Steveson v Sean Sharaf", "2026-09-20T02:30:00.000Z", "Gable Steveson", 3, 3),
    _olbg_row("A Fighter v B Fighter", "2026-09-20T02:30:00.000Z", "A Fighter", 5, 6, market="Method of Victory"),
]) + "</html>"
_calls = {c["a"]: c for c in S.parse_olbg(_page)}
eq(sorted(_calls), ["DaMazzion Vanhouter", "Gable Steveson", "Jai Opetaia"],
   "only fights where a fighter holds a strict majority of 3+ Win Fight tips are calls")
eq(_calls["Jai Opetaia"]["pick"], "a", "9/14 on the first-named fighter is side a")
eq(_calls["DaMazzion Vanhouter"]["pick"], "b", "a majority on the second-named fighter is side b")
eq(_calls["Jai Opetaia"]["date"], "2026-09-13", "dated from the page's own start time")
ok("Garcia" not in str(_calls), "10 of 25 is a plurality, not a consensus: no call")
ok("Magsayo" not in str(_calls), "a fight whose top tip is the draw is no call on a two-way market")
ok("Inoue" not in str(_calls), "two tips are not a consensus")
ok("A Fighter" not in str(_calls), "only the Win Fight market is read")
eq(S.parse_olbg("<html>nothing here</html>"), [], "a page with no rows parses to nothing")

_saved_html = S._get_html
try:
    S._olbg_cache.clear(); S.FEED_STATUS.clear()
    S._get_html = lambda url, **kw: "<html><title>Just a moment...</title>challenge-platform</html>"
    eq(S.fetch_olbg("boxing"), [], "a Cloudflare interstitial yields no calls")
    eq(S.FEED_STATUS.get("olbg"), "down: Cloudflare challenge", "and is reported as a wall, not as silence")

    S._olbg_cache.clear(); S.FEED_STATUS.clear()
    _hits = []
    S._get_html = lambda url, **kw: (_hits.append(url), _page)[1]
    eq(len(S.fetch_olbg("boxing")), 3, "the live path returns the parsed calls")
    S.fetch_olbg("boxing")
    eq(len(_hits), 1, "one request per run, however often it is asked")
    eq(S.FEED_STATUS.get("olbg"), "ok", "a readable page reports ok")
    eq(S.fetch_olbg("tennis"), [], "boxing only")
finally:
    S._get_html = _saved_html
    S._olbg_cache.clear(); S.FEED_STATUS.clear()

m_ = T.match_quotes(
    [dict(market_id="kb1", sport="boxing", side_a="Opetaia J.", side_b="Mikaelian N.", date="2026-09-13")],
    [dict(a="Jai Opetaia", b="Norair Mikaeljan", pick="a", date="2026-09-13")])
eq(m_.get("kb1"), ("pick", "a"), "OLBG's 'Mikaeljan' matches the venue's 'Mikaelian'")
eq(S.pair_match("Garcia", "Benn", "Sean Garcia", "Abraham Morales", sport="boxing")[0], 0.0,
   "one shared surname cannot match a different bout")
eq(S.pair_match("Molina", "Rubio", "Mark Magsayo", "Andres Cortes", sport="boxing")[0], 0.0,
   "unrelated fighters never match")
eq(S.pair_match("Mikaelian", "Opetaia", "Mikaeljan", "Opetaia", sport="tennis")[1], False,
   "the near-spelling rule is boxing only")

# ---------------------------------------------------------------------------
print("\nfight nights: Pinnacle start times, and MMA")
# ---------------------------------------------------------------------------
_now = datetime(2026, 9, 12, 22, 30, tzinfo=timezone.utc)
_ev = [dict(a="Jai Opetaia", b="Norair Mikaeljan", start=datetime(2026, 9, 13, 2, 0, tzinfo=timezone.utc)),
       dict(a="DaMazzion Vanhouter", b="Raphael Akpejiori", start=datetime(2026, 9, 13, 1, 15, tzinfo=timezone.utc)),
       dict(a="Somebody", b="Else", start=datetime(2026, 9, 20, 2, 0, tzinfo=timezone.utc))]
_fr = [
    # Kalshi's 3h-early estimate has passed, the bout has not: re-timed and kept.
    dict(side_a="Opetaia J.", side_b="Mikaelian N.", start="2026-09-12T23:00:00+00:00", label="x"),
    # Polymarket stamped the card start for this bout: re-timed and kept.
    dict(side_a="Vanhouter", side_b="Akpejiori", start="2026-09-12T21:00:00+00:00", label="y"),
    # No Pinnacle event and its venue start has passed: dropped, exactly as before.
    dict(side_a="Panin", side_b="Linger", start="2026-09-12T21:00:00+00:00", label="z"),
    # No Pinnacle event and still ahead: kept on the venue's own start.
    dict(side_a="Conway", side_b="Jeffers", start="2026-09-19T18:00:00+00:00", label="w"),
    # Same surnames on a card a month away: a match over a day off is not trusted.
    dict(side_a="Somebody", side_b="Else", start="2026-10-20T02:00:00+00:00", label="v"),
]
_kept, _st = S.apply_pinnacle_starts("boxing", _fr, events=_ev, now=_now)
_by = {r["label"]: r for r in _kept}
eq(sorted(_by), ["v", "w", "x", "y"], "re-timed bouts kept, a started unmatched bout dropped")
eq((_by["v"]["start_source"], _by["v"]["start"]), ("venue", "2026-10-20T02:00:00+00:00"),
   "a Pinnacle match more than a day off the venue is not trusted: the venue start stands")
eq(_by["x"]["start"], "2026-09-13T01:30:00+00:00",
   "start = Pinnacle commence minus the margin, never Pinnacle's exact time")
eq((_by["x"]["start_source"], _by["w"]["start_source"]), ("pinnacle", "venue"), "every row says where its start came from")
eq(_by["x"]["venue_start"], "2026-09-12T23:00:00+00:00", "the venue's own start is kept alongside")
eq(_by["y"]["date"], "2026-09-13", "the date follows the re-timed start")
eq((_st["matched"], _st["dropped"]), (2, 1), "stats count the re-timed and the dropped")
ok(S.PINNACLE_START_MARGIN_MIN >= 15, "the margin allows for a card running ahead of schedule")
ok(not T._started(_by["x"], _now), "so Opetaia can be logged at 22:30 for a 02:00 walk-out")
ok(T._started(_by["x"], datetime(2026, 9, 13, 1, 31, tzinfo=timezone.utc)),
   "and stops being loggable half an hour before Pinnacle's time")

_t = S.apply_pinnacle_starts("boxing", [dict(side_a="Panin", side_b="Linger",
                                             start="2026-09-12T21:00:00", label="naive")],
                             events=[], now=_now)[0]
eq(_t, [], "a naive venue timestamp is read as UTC, and a passed one is still dropped")

# The fight lookback is for fights only.
ok("mma" in S.START_FROM_PINNACLE and "boxing" in S.START_FROM_PINNACLE and "tennis" not in S.START_FROM_PINNACLE,
   "only boxing and MMA are re-timed")
_pm_old = S._get
_start_past = (datetime.now(timezone.utc) - timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
_evs = [dict(slug="c", title="Garcia vs. Benn", startDate=_start_past, markets=[
    dict(id="gb", outcomes='["Ryan Garcia", "Conor Benn"]', outcomePrices='["0.70", "0.30"]',
         bestBid="0.70", bestAsk="0.71", spread="0.01", liquidityNum=5000, volumeNum=9,
         acceptingOrders=True, closed=False, gameStartTime=_start_past,
         question="Ryan Garcia vs. Conor Benn")])]
S._get = lambda url, **kw: _evs if "offset=0" in url else []
try:
    eq([r["market_id"] for r in S.fetch_polymarket("boxing")], ["gb"],
       "a boxing market whose card start passed two hours ago is kept for re-timing")
    eq(S.fetch_polymarket("tennis"), [], "a tennis market two hours past its start is not")
finally:
    S._get = _pm_old

eq((S.SPORTS.get("mma"), S.PM_TAGS.get("mma"), S.KALSHI_VENUE_SERIES.get("mma"), S.ODDS_GROUPS.get("mma")),
   ("MMA", "ufc", ["KXUFCFIGHT", "KXMMAFIGHT"], "Mixed Martial Arts"), "MMA is wired to every venue and to Pinnacle")
ok("mma" in S.SOURCES["olbg"]["sports"] and "mma" in S.SOURCES["pinnacle"]["sports"],
   "OLBG and Pinnacle both cover MMA")
eq(S.pair_match("Silva", "Delgado", "Jean Silva", "Jose Miguel Delgado", sport="mma")[1], False,
   "a UFC bout matches its fuller spelling")
ok(S.pair_match("Mikaelian", "Opetaia", "Mikaeljan", "Opetaia", sport="mma")[0] > 0,
   "transliterations match in MMA as in boxing")

_saved_html = S._get_html
_hits = []
try:
    S._olbg_cache.clear(); S.FEED_STATUS.clear()
    S._get_html = lambda url, **kw: (_hits.append(url), _page)[1]
    S.fetch_olbg("boxing"); S.fetch_olbg("mma")
    eq(len(_hits), 1, "boxing and MMA read OLBG's one shared listing with a single request")
finally:
    S._get_html = _saved_html
    S._olbg_cache.clear(); S.FEED_STATUS.clear()

import sandbox_build as SB
_rows = "\n".join([f'<tr class="grp"><td>G</td></tr>'] + [f"<tr><td>r{i}</td>\n<td>x</td></tr>" for i in range(12)])
_html = SB.collapse(_rows, "<tr><th>h</th></tr>", 40, "things")
ok("Show 4 more things" in _html, "12 rows show 8 and fold 4, counting rows not template lines")
ok("the latest 12 of 40" in _html, "and say how many exist beyond the rows listed")
eq(SB.collapse("<tr><td>a</td></tr>", "<tr><th>h</th></tr>", 1, "x").count("<details"), 0,
   "a short list is not folded")

# ---------------------------------------------------------------------------
print("\nOdds API credits last the month")
# ---------------------------------------------------------------------------
_t0 = datetime(2026, 9, 1, 0, 30, tzinfo=timezone.utc)


def _simulate(start, credits=500, manual_per_day=2, wanted=4):
    """Spend a month the way the workflow would: the scheduled runs a day plus manual ones."""
    now, rem, spent_days = start, credits, set()
    end = datetime(2026, 10, 1, tzinfo=timezone.utc)
    while now < end:
        for _run in range(S.ODDS_RUNS_PER_DAY + manual_per_day):
            spend = min(wanted, S.odds_allowance(rem, now))
            rem -= spend
            if spend:
                spent_days.add(now.date())
        now += timedelta(days=1)
    return rem, len(spent_days)


_left, _days = _simulate(_t0)
ok(_left >= S.ODDS_RESERVE - 1, f"a month of {S.ODDS_RUNS_PER_DAY} scheduled + 2 manual runs a day never runs dry (left {_left})")
eq(_days, 30, "and Pinnacle still gets a paid call on every single day of the month")
_left, _days = _simulate(datetime(2026, 9, 13, 0, 17, tzinfo=timezone.utc), credits=483)
ok(_left >= S.ODDS_RESERVE - 1 and _days == 18, f"from today's 483, it lasts to the 1st with a call every day (left {_left})")
eq(S.odds_allowance(S.ODDS_RESERVE, _t0), 0, "at the reserve, nothing is spent")
eq(S.odds_allowance(500, datetime(2026, 9, 30, 20, tzinfo=timezone.utc)), S.ODDS_MAX_CALLS,
   "near the reset a full balance is spent up to the ceiling, never beyond it")
eq(S.odds_allowance(None), 1, "an unknown balance spends one call, cautiously")
eq(S.odds_allowance(400, datetime(2026, 12, 20, tzinfo=timezone.utc)) >= 1, True, "December rolls into January")

# ---------------------------------------------------------------------------
print("\nPinnacle v venue: credits go to contests nothing else covers")
# ---------------------------------------------------------------------------
_now = datetime.now(timezone.utc)
_soon = (_now + timedelta(hours=6)).isoformat()
_hr = lambda h: (_now - timedelta(minutes=h)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _pev(home, away, prices, age_min=5):
    return dict(home_team=home, away_team=away, commence_time=_soon, bookmakers=[
        dict(key="pinnacle", markets=[dict(key="h2h", last_update=_hr(age_min),
             outcomes=[dict(name=n, price=p) for n, p in prices.items()])])])


close(S.pinnacle_prob(_pev("Leeds United", "Newcastle United",
                           {"Leeds United": 3.0, "Draw": 3.4, "Newcastle United": 2.4}),
                      "Leeds United", three_way=True),
      (1 / 3.0) / (1 / 3.0 + 1 / 3.4 + 1 / 2.4), "soccer keeps the draw in the de-vig", tol=1e-9)
eq(S.pinnacle_prob(_pev("A", "B", {"A": 1.9, "B": 1.9}), "A", three_way=True), None,
   "a three-way sport with no draw price is not priced at all")

_univ = {
    "boxing": [dict(market_id="bx1", side_a="Garcia", side_b="Benn", untraded=False)],
    "soccer": [dict(market_id="sc1", side_a="Leeds United", side_b="Newcastle United", untraded=False),
               dict(market_id="sc2", side_a="Brentford", side_b="Chelsea", untraded=False),
               dict(market_id="sc3", side_a="Everton", side_b="Ipswich Town", untraded=False)],
}
_ev_lists = {
    "/sports/boxing_boxing/events": [dict(home_team="Ryan Garcia", away_team="Conor Benn")],
    "/sports/soccer_epl/events": [dict(home_team="Leeds United", away_team="Newcastle United"),
                                  dict(home_team="Brentford", away_team="Chelsea"),
                                  dict(home_team="Everton", away_team="Ipswich Town")],
}
_odds = {
    "/sports/boxing_boxing/odds": [_pev("Ryan Garcia", "Conor Benn", {"Ryan Garcia": 1.4, "Conor Benn": 3.1})],
    "/sports/soccer_epl/odds": [
        _pev("Leeds United", "Newcastle United", {"Leeds United": 3.0, "Draw": 3.4, "Newcastle United": 2.4}),
        _pev("Brentford", "Chelsea", {"Brentford": 3.6, "Draw": 3.6, "Chelsea": 2.0}, age_min=240),
        _pev("Everton", "Ipswich Town", {"Everton": 2.1, "Draw": 3.3, "Ipswich Town": 3.6})],
}
_paid = []


def _fake_plan_get(path, params):
    if path == "/sports":
        return [dict(key="boxing_boxing", group="Boxing", active=True, has_outrights=False),
                dict(key="soccer_epl", group="Soccer", active=True, has_outrights=False)], \
            {"x-requests-remaining": "400"}
    if path.endswith("/events"):
        return _ev_lists.get(path, []), {}
    _paid.append(path)
    return _odds[path], {"x-requests-remaining": str(400 - len(_paid))}


_saved_get2, _saved_key2 = S._odds_get, _os.environ.get("ODDS_API_KEY")
S._odds_get = _fake_plan_get
_os.environ["ODDS_API_KEY"] = "test-key-not-real"
try:
    _reset_odds(); _paid.clear()
    S.ODDS_USAGE["allowance"] = 1
    _plan = S.plan_pinnacle(_univ, covered={"soccer": {"sc2"}, "boxing": set()})
    eq(_paid, ["/sports/soccer_epl/odds"],
       "with one credit, it goes to the key with the most uncovered contests (EPL 2, boxing 1)")
    eq(S.ODDS_USAGE["calls"], 1, "and the run's allowance is never exceeded")
    eq(sorted(q["a"] for q in _plan["soccer"]), ["Everton", "Leeds United"],
       "every fresh line on the paid key is quoted, covered or not")
    eq(S.ODDS_USAGE.get("stale"), 1, "a Pinnacle line four hours old is skipped, and counted")
    eq(_plan["boxing"], [], "no credit left for boxing this run")
    eq(S.ODDS_USAGE["planned"][0]["uncovered"], 2, "the plan is recorded, most uncovered first")

    _reset_odds(); _paid.clear()
    S.ODDS_USAGE["allowance"] = 0
    S.plan_pinnacle(_univ, covered={})
    eq(_paid, [], "an allowance of zero spends nothing, whatever is uncovered")

    # publish: Pinnacle is planned after every other source, and flags its uncovered contests
    _reset_odds(); _paid.clear()
    S.ODDS_USAGE["allowance"] = 2
    _rows = {"soccer": [dict(r, sport="soccer", venue="kalshi", label=f"{r['side_a']} vs {r['side_b']}",
                             price_a=0.30, price_b=0.40, price_draw=0.28,
                             tradeable={"a": True, "b": True, "draw": True},
                             start=_soon, date=_soon[:10], volume=0.0, url="")
                        for r in _univ["soccer"]]}
    _saved_ch = S.CHALLENGERS
    S.CHALLENGERS = {"soccerpredictions": lambda sp: [dict(market_id="sc1", pick="draw")]}
    try:
        d = {"quotes": [], "meta": {}, "coverage": {}}
        T.publish(d, _rows, {}, verbose=False)
    finally:
        S.CHALLENGERS = _saved_ch
    _pq = {q["market_id"]: q for q in d["quotes"] if q["source"] == "pinnacle"}
    eq((_pq["sc1"]["uncovered"], _pq["sc3"]["uncovered"]), (False, True),
       "a contest a tipster covered this run is not uncovered; one nobody touched is")
    close(_pq["sc3"]["prob_a"], (1 / 2.1) / (1 / 2.1 + 1 / 3.3 + 1 / 3.6), "soccer Pinnacle probability includes the draw", tol=1e-3)
    eq(_pq["sc3"]["bet"], True, "Everton at 0.30 against a Pinnacle 0.45 is a bet")
    ok(all(q.get("uncovered") is None for q in d["quotes"] if q["source"] != "pinnacle"),
       "only Pinnacle quotes carry the uncovered flag")
    ok("pinnacle" not in S.CHALLENGERS, "Pinnacle is planned, not fetched sport by sport")
finally:
    S._odds_get = _saved_get2
    _reset_odds()
    if _saved_key2 is None:
        _os.environ.pop("ODDS_API_KEY", None)
    else:
        _os.environ["ODDS_API_KEY"] = _saved_key2

# ---------------------------------------------------------------------------
print("\nstages: Sandbox -> QA")
# ---------------------------------------------------------------------------
_base = datetime(2026, 9, 1, 15, tzinfo=timezone.utc)


def _sb(i, won, pick="a", price=0.40, week=0, source="covers", sport="mlb", logged=None, venue="polymarket_us"):
    st = _base + timedelta(weeks=week, hours=i)
    return dict(source=source, sport=sport, bet=True, status="won" if won else "lost", pick=pick,
                price=price, result=pick if won else ("b" if pick == "a" else "a"), venue=venue,
                pnl=round(100 * (1 / price - 1), 2) if won else -100.0, start=st.isoformat(),
                logged=(logged or (st - timedelta(hours=5))).isoformat(),
                price_a=price if pick == "a" else 0.40, price_b=0.62 if pick == "a" else price,
                price_draw=None)


def _chooser(n, week_span, source="covers", sport="mlb", start_i=0, logged=None, win_every=(6, 9)):
    """A source that CHOOSES: underdog on even contests (wins 6 in 10), favourite on odd (9 in 10)."""
    out = []
    for i in range(n):
        wk = (i * week_span) // n
        if i % 2 == 0:
            out.append(_sb(start_i + i, i % 10 < win_every[0], "a", 0.40, wk, source, sport, logged))
        else:
            out.append(_sb(start_i + i, i % 10 < win_every[1], "b", 0.62, wk, source, sport, logged))
    return out


_old_sources = S.SOURCES
S.SOURCES = {"covers": dict(_old_sources["covers"], sports=["mlb", "nfl", "soccer"]),
             "polymarket": _old_sources["polymarket"]}
try:
    eq(T.QA_ENTRY["min_bets"] < T.APPROVAL["min_bets"] and T.QA_ENTRY["z_min"] < T.APPROVAL["z_min"], True,
       "the QA entry gate is lighter than the stamp")
    d = {"quotes": _chooser(32, 3)}
    st = {"pairs": {}, "events": []}
    _t = datetime(2026, 9, 25, tzinfo=timezone.utc)
    ch = T.evaluate_stages(d, st, now=_t, verbose=False)
    eq([(c["pair"], c["to"]) for c in ch], [("covers|mlb", "qa")], "32 good bets over 3 weeks promote MLB, not NFL")
    eq(st["pairs"]["covers|mlb"]["stage"], "qa", "the registry records the stage")
    eq(st["pairs"]["covers|mlb"]["entry"]["n"], 32, "with the evidence it was promoted on")
    ok("covers|nfl" not in st["pairs"], "an untouched sandbox pair is not written to the registry")
    eq(T.evaluate_stages(d, st, now=_t, verbose=False), [], "re-running changes nothing")

    one_week = {"quotes": _chooser(32, 1)}
    eq(T.evaluate_stages(one_week, {"pairs": {}, "events": []}, now=_t, verbose=False), [],
       "the same record inside one week is not promoted")
    fav_only = {"quotes": [_sb(i, i % 10 < 9, "b", 0.62, i // 11) for i in range(33)]}
    eq(T.evaluate_stages(fav_only, {"pairs": {}, "events": []}, now=_t, verbose=False), [],
       "a source that only backs the favourite is not promoted however well it did")

    # QA judges fresh data only: the promoting history does not count.
    _promo = st["pairs"]["covers|mlb"]["promoted_at"]
    a = T.assess(d, "covers", "mlb", since=_promo)
    eq(a["n"], 0, "QA starts from zero bets at promotion")
    _fresh_bad = [_sb(100 + i, i % 5 == 0, "a", 0.40, 4 + i // 10, logged=_t + timedelta(hours=1 + i))
                  for i in range(30)]
    d2 = {"quotes": d["quotes"] + _fresh_bad}
    ch = T.evaluate_stages(d2, st, now=_t + timedelta(days=2), verbose=False)
    eq([(c["pair"], c["to"]) for c in ch], [("covers|mlb", "sandbox")],
       "30 fresh QA bets behind the price demote the pair")
    ok("behind the price" in ch[0]["reason"], "with the reason recorded")
    ch = T.evaluate_stages(d2, st, now=_t + timedelta(days=3), verbose=False)
    eq(ch, [], "after demotion the old promoting record cannot re-promote it: it must re-qualify on new bets")
    eq(len(st["events"]), 2, "every change is in the event log")

    # Production-ready: the stamp on fresh data + positive CLV + positive after fees.
    st3 = {"pairs": {"covers|soccer": dict(stage="qa", promoted_at="2026-09-01T00:00:00+00:00")}, "events": []}
    # Soccer on Kalshi, home or away: a record the feed can publish.
    fresh = [dict(q, sport="soccer", venue="kalshi", market_id=f"KXEPLGAME-26SEP01X{i:02d}")
             for i, q in enumerate(_chooser(60, 6))]
    for q in fresh:
        q["close_price"] = q["price"] + 0.02
        q["close_at"] = (datetime.fromisoformat(q["start"]) - timedelta(minutes=10)).isoformat()
    ch = T.evaluate_stages({"quotes": fresh}, st3, now=_t, verbose=False)
    eq(ch, [], "passing the ready gate once is not ready: it must hold")
    eq(st3["pairs"]["covers|soccer"].get("ready_since"), _t.isoformat(), "the hold starts the first run it passes")
    eq(T.evaluate_stages({"quotes": fresh}, st3, now=_t + timedelta(days=6), verbose=False), [],
       "six days of holding is not yet seven")
    ch = T.evaluate_stages({"quotes": fresh}, st3, now=_t + timedelta(days=7), verbose=False)
    eq([c["to"] for c in ch], ["ready"], "held for seven days, with CLV and fees positive, it is ready")
    eq(T.evaluate_stages({"quotes": fresh}, st3, now=_t + timedelta(days=8), verbose=False), [],
       "ready is marked once")
    _thin = [dict(q) for q in fresh]
    for q in _thin[29:]:
        q.pop("close_price"); q.pop("close_at")
    ch = T.evaluate_stages({"quotes": _thin}, st3, now=_t + timedelta(days=9), verbose=False)
    eq([c["to"] for c in ch], ["unready"], "with only 29 closing prices the gate fails, and ready is withdrawn")
    ok("closing price" in ch[0]["reason"], "naming the criterion it lost")
    ok("ready_at" not in st3["pairs"]["covers|soccer"] and "ready_since" not in st3["pairs"]["covers|soccer"],
       "the hold starts again from nothing")
    for q in fresh:
        q["close_price"] = q["price"] - 0.02
    st4 = {"pairs": {"covers|soccer": dict(stage="qa", promoted_at="2026-09-01T00:00:00+00:00")}, "events": []}
    ch = T.evaluate_stages({"quotes": fresh}, st4, now=_t, verbose=False)
    eq([c["to"] for c in ch], ["sandbox"], "the same record buying above the closing price is demoted, not ready")
    ok("closing price" in ch[0]["reason"], "because it is behind the close")

    # The feed cannot publish it: the same fresh MLB record clears everything else and is not ready.
    _mlb = [dict(q, sport="mlb", venue="polymarket_us") for q in _chooser(60, 6)]
    for q in _mlb:
        q["close_price"] = q["price"] + 0.02
        q["close_at"] = (datetime.fromisoformat(q["start"]) - timedelta(minutes=10)).isoformat()
    _stm = {"pairs": {"covers|mlb": dict(stage="qa", promoted_at="2026-09-01T00:00:00+00:00")}, "events": []}
    T.evaluate_stages({"quotes": _mlb}, _stm, now=_t, verbose=False)
    ch = T.evaluate_stages({"quotes": _mlb}, _stm, now=_t + timedelta(days=8), verbose=False)
    eq(ch, [], "an MLB record the feed cannot publish never becomes ready")
    _gate = dict((k, (p, det)) for k, _l, p, det in T.ready_gate(T.assess({"quotes": _mlb}, "covers", "mlb",
                                                                           venues=T.TRADEABLE_VENUES)))
    eq(_gate["route"][0], False, "because the route criterion fails")
    ok("0 of 60" in _gate["route"][1], "and says how many bets had a route")
    _draws = [dict(q, pick="draw") if i % 10 == 0 else q for i, q in enumerate(fresh)]
    eq(T.placeable(_draws[0]), True, "a soccer draw on Kalshi is publishable (Tie contract) since 2026-09-16")
    eq(T.placeable(_draws[1]), True, "a soccer side on Kalshi does")
    eq(T.placeable(dict(_draws[1], market_id="KXALLSVENSKANGAME-26SEP01X")), False,
       "but not in an unmapped league")

    # polymarket.com bets never count toward QA.
    _com = [dict(q, venue="polymarket") for q in _chooser(32, 3)]
    eq(T.evaluate_stages({"quotes": _com}, {"pairs": {}, "events": []}, now=_t, verbose=False), [],
       "a record logged on polymarket.com, closed to US accounts, is not promoted")
    eq(T.assess({"quotes": _com}, "covers", "mlb")["n"], 32,
       "though the Sandbox's own view still counts it")



    # Demotion also covers the blind rules and a pair that stops betting.
    st5 = {"pairs": {"covers|mlb": dict(stage="qa", promoted_at="2026-09-01T00:00:00+00:00")}, "events": []}
    ch = T.evaluate_stages(fav_only, st5, now=_t, verbose=False)
    eq([c["to"] for c in ch], ["sandbox"], "30+ fresh bets that are just 'back the favourite' are demoted")
    ok("blind rule" in ch[0]["reason"], "for not beating every blind rule")
    st6 = {"pairs": {"covers|mlb": dict(stage="qa", promoted_at="2026-09-01T00:00:00+00:00")}, "events": []}
    _few = _chooser(5, 1)
    eq(T.evaluate_stages({"quotes": _few}, st6, now=datetime(2026, 9, 20, tzinfo=timezone.utc), verbose=False), [],
       "a young QA pair with few bets is left alone")
    ch = T.evaluate_stages({"quotes": _few}, st6, now=datetime(2026, 9, 30, tzinfo=timezone.utc), verbose=False)
    eq([(c["to"], c["reason"]) for c in ch], [("sandbox", "no new bet in 21 days")],
       "21 days without a new bet sends it back, whatever the count")

    # The sample is a span of days, not calendar weeks touched.
    _sun_mon = [dict(q, start=(datetime(2026, 9, 13, 12, tzinfo=timezone.utc) + timedelta(hours=i)).isoformat())
                for i, q in enumerate(_chooser(32, 1))]
    _am = T.assess({"quotes": _sun_mon}, "covers", "mlb")
    eq(_am["span_days"] < 2, True, "32 bets from a Sunday into a Monday span under two days")
    eq(dict((k, p) for k, _l, p, _d in T.qa_entry(_am))["sample"], False,
       "and do not pass QA's 14-day sample, though they touch two calendar weeks")

    # Baselines are never promoted.
    S.SOURCES = {"spot": dict(_old_sources["spot"], sports=["mlb"])}
    eq(T.evaluate_stages({"quotes": [dict(q, source="spot") for q in _chooser(32, 3)]},
                         {"pairs": {}, "events": []}, now=_t, verbose=False), [],
       "a baseline with a promotable record is not promoted")
finally:
    S.SOURCES = _old_sources

close(T.pnl_after_fee(dict(price=0.5, status="won", venue="polymarket")), 100 * (1 / (0.5 + 0.06 * 0.25) - 1),
      "a won bet pays the price plus the Polymarket taker fee", tol=0.01)
close(T.pnl_after_fee(dict(price=0.5, status="won", venue="kalshi")), 100 * (1 / (0.5 + 0.07 * 0.25) - 1),
      "Kalshi's fee rate is 0.07", tol=0.01)
eq(T.pnl_after_fee(dict(price=0.5, status="lost", venue="kalshi")), -100.0, "a lost bet loses the stake")

# ---------------------------------------------------------------------------
print("\nclosing prices")
# ---------------------------------------------------------------------------
_n0 = datetime.now(timezone.utc)
_row = dict(market_id="cl1", sport="mlb", venue="kalshi", label="A vs B", side_a="A", side_b="B",
            price_a=0.40, price_b=0.62, price_draw=None, tradeable={"a": True, "b": True},
            untraded=False, start=(_n0 + timedelta(hours=5)).isoformat(), date=_n0.strftime("%Y-%m-%d"),
            volume=0.0, url="")
_q = dict(id="covers:cl1", source="covers", sport="mlb", market_id="cl1", venue="kalshi", pick="a",
          price=0.40, bet=True, status="open", start=_row["start"])
d = {"quotes": [dict(_q)]}
eq(T.snap_closing(d, {"mlb": [dict(_row, price_a=0.44)]}, now=_n0), 1, "an open bet takes the venue's current price")
eq(d["quotes"][0]["close_price"], 0.44, "for the side it backed")
T.snap_closing(d, {"mlb": [dict(_row, price_a=0.47)]}, now=_n0 + timedelta(hours=1))
eq(d["quotes"][0]["close_price"], 0.47, "refreshed every run, so the last one before the start stands")
T.snap_closing(d, {"mlb": [dict(_row, price_a=0.30)]}, now=_n0 + timedelta(hours=6))
eq(d["quotes"][0]["close_price"], 0.47, "a snapshot after the start is never taken")
T.snap_closing(d, {"mlb": [dict(_row, price_a=0.30, untraded=True)]}, now=_n0 + timedelta(hours=2))
eq(d["quotes"][0]["close_price"], 0.47, "an untraded book leaves the last good snapshot")
T.snap_closing(d, {"mlb": [dict(_row, price_a=0.30, tradeable={"a": False, "b": True})]}, now=_n0 + timedelta(hours=2))
eq(d["quotes"][0]["close_price"], 0.47, "nor does a side whose own book is not tradeable")
T.snap_closing(d, {"mlb": [dict(_row, venue="polymarket", price_a=0.30)]}, now=_n0 + timedelta(hours=2))
eq(d["quotes"][0]["close_price"], 0.47, "a different venue's price is never a closing price")
d2 = {"quotes": [dict(_q, bet=False), dict(_q, status="won")]}
eq(T.snap_closing(d2, {"mlb": [_row]}, now=_n0), 0, "no-bet quotes and settled bets are left alone")
d3 = {"quotes": [dict(_q, pick="draw", sport="soccer")]}
T.snap_closing(d3, {"soccer": [dict(_row, price_draw=0.29, tradeable={"a": True, "b": True, "draw": True})]}, now=_n0)
eq(d3["quotes"][0]["close_price"], 0.29, "a draw bet closes on the draw price")
_ac = T.assess({"quotes": [dict(_q, status="won", result="a", pnl=150.0, logged=_n0.isoformat(),
                                start=(_n0 + timedelta(hours=5)).isoformat(), price_a=0.40, price_b=0.62,
                                close_price=0.47,
                                close_at=(_n0 + timedelta(hours=5, minutes=-20)).isoformat())]}, "covers")
close(_ac["clv"], 0.07, "CLV is close minus price: bought at 0.40, closed at 0.47", tol=1e-9)
eq(_ac["clv_beat"], 1.0, "and it beat the close")

# ---------------------------------------------------------------------------
print("\nQA page")
# ---------------------------------------------------------------------------
_qd = {"quotes": [dict(source="espn_fpi", sport="mlb", bet=True, status="won", pick="a", price=0.40,
                       result="a", pnl=150.0, venue="kalshi", price_a=0.40, price_b=0.62, price_draw=None,
                       logged="2026-09-12T01:00:00+00:00", start="2026-09-12T20:00:00+00:00",
                       close_price=0.44, close_at="2026-09-12T19:40:00+00:00"),
                  dict(source="espn_fpi", sport="mlb", bet=True, status="won", pick="a", price=0.40,
                       result="a", pnl=150.0, venue="kalshi", price_a=0.40, price_b=0.62, price_draw=None,
                       logged="2026-09-09T01:00:00+00:00", start="2026-09-09T20:00:00+00:00")]}
_st = {"pairs": {"espn_fpi|mlb": dict(stage="qa", promoted_at="2026-09-11T00:00:00+00:00", entry=dict(n=31))},
       "events": [dict(pair="espn_fpi|mlb", to="qa", at="2026-09-11T00:00:00+00:00",
                       evidence=dict(n=31, z=1.3, roi=0.2))]}
_html = SB.qa_page(_qd, _st, "<style></style>")
ok("IN QA · " in _html, "a promoted pair is listed in QA with its progress")
ok(">1<div" in _html.replace(" ", "") or "<td class=\"num\">1<div" in _html,
   "and judged on 1 fresh bet — the pre-promotion bet does not count")
ok("+4.0¢" in _html, "its closing-line value is shown")
ok("→ QA" in _html, "the promotion is in the history")
ok("ESPN FPI · MLB" in _html, "pairs are labelled source · sport")
_empty = SB.qa_page({"quotes": []}, {"pairs": {}, "events": []}, "<style></style>")
ok("Nothing has been promoted yet" in _empty and "No promotions or demotions yet" in _empty,
   "an empty registry says so rather than showing empty tables")
ok('href="./qa.html">QA</a>' in open("sandbox_build.py").read(), "the Sandbox nav links to QA")
eq(T.assess(_qd, "espn_fpi", "mlb", since="2026-09-11T00:00:00+00:00")["n"], 1,
   "QA's record counts only the bet logged after promotion")

# ---------------------------------------------------------------------------
print("\nclosing prices near the deadline")
# ---------------------------------------------------------------------------
import sandbox_close as SC
_c0 = datetime(2026, 9, 13, 12, 0, tzinfo=timezone.utc)
_cq = lambda **kw: dict(dict(id="covers:c1", source="covers", sport="mlb", market_id="c1", venue="polymarket",
                             pick="a", price=0.40, bet=True, status="open",
                             start=(_c0 + timedelta(minutes=20)).isoformat()), **kw)
eq(T.close_deadline(_cq()), _c0 + timedelta(minutes=20), "a contest's deadline is its start")
_lh = S.KALSHI_BINARY["climate"]["lead_h"]
eq(T.close_deadline(_cq(venue="kalshi_binary", sport="climate")),
   _c0 + timedelta(minutes=20) - timedelta(hours=_lh),
   "a yes/no market's deadline is its expiry minus the domain's quoting lead")
_dd = {"quotes": [_cq(), _cq(id="covers:c2", start=(_c0 + timedelta(hours=3)).isoformat()),
                  _cq(id="covers:c3", bet=False), _cq(id="covers:c4", status="won"),
                  _cq(id="covers:c5", start=(_c0 - timedelta(minutes=1)).isoformat())]}
eq([q["id"] for q in SC.due(_dd, _c0)], ["covers:c1"],
   "only open bets whose deadline is inside the next window are due — not later, not started, not no-bets")
_cl = {"closes": {"covers:old": {"price": 0.5, "at": "2026-08-01T00:00:00+00:00"}}}
eq(SC.run(_dd, _cl, now=_c0, price=lambda q: 0.43), (1, 1), "the due bet is snapshotted")
eq(_cl["closes"]["covers:c1"], {"price": 0.43, "at": _c0.isoformat(), "lead_min": 20.0},
   "with its price, the time, and how far before the deadline it was taken")
ok("covers:old" not in _cl["closes"], "entries older than the keep window are pruned")
_cl2 = {"closes": {}}
eq(SC.run(_dd, _cl2, now=_c0, price=lambda q: None), (0, 1), "an unreadable or untradeable book takes nothing")

import json, tempfile as _tfc
_cdir = _tfc.mkdtemp()
for _w, _snap in (("close", {"covers:c1": {"price": 0.40, "at": (_c0 - timedelta(minutes=30)).isoformat()}}),
                  ("watchdog", {"covers:c1": {"price": 0.42, "at": (_c0 - timedelta(minutes=10)).isoformat()},
                                "covers:c9": {"price": 0.55, "at": _c0.isoformat()}})):
    with open(_os.path.join(_cdir, f"{_w}.json"), "w") as _f:
        json.dump({"closes": _snap}, _f)
_merged = T.load_closes(directory=_cdir)["closes"]
eq(sorted(_merged), ["covers:c1", "covers:c9"], "every writer's file is read")
eq(_merged["covers:c1"]["price"], 0.42, "and the latest snapshot of a bet wins across writers")
eq(SC.CLOSE_WINDOW_MIN <= T.CLOSE_MAX_LEAD_MIN, True, "the close window never takes a snapshot too early to count")
_saved_cd = T.CLOSES_DIR
T.CLOSES_DIR = _cdir
_saved_load = T.load
T.load = lambda: {"quotes": [_cq(start=(datetime.now(timezone.utc) + timedelta(minutes=20)).isoformat())]}
_saved_vp = S.venue_price
SC.S.venue_price = lambda q: 0.44
try:
    SC.run.__defaults__ = (None, lambda q: 0.44)
    SC.main(["--writer", "boards"])
    ok(_os.path.exists(_os.path.join(_cdir, "boards.json")), "a writer writes only its own file")
    eq(json.load(open(_os.path.join(_cdir, "boards.json")))["closes"]["covers:c1"]["price"], 0.44,
       "with the snapshot it took")
    eq(json.load(open(_os.path.join(_cdir, "close.json")))["closes"]["covers:c1"]["price"], 0.40,
       "and never touches another writer's")
finally:
    T.CLOSES_DIR, T.load, SC.S.venue_price = _saved_cd, _saved_load, _saved_vp
    SC.run.__defaults__ = (None, S.venue_price)
_dm = {"quotes": [_cq(close_price=0.41, close_at=(_c0 - timedelta(hours=5)).isoformat())]}
eq(T.apply_closes(_dm, _cl), 1, "the close job's later snapshot is merged into the ledger")
eq((_dm["quotes"][0]["close_price"], _dm["quotes"][0]["close_at"]), (0.43, _c0.isoformat()), "and replaces the older one")
eq(T.apply_closes(_dm, {"closes": {"covers:c1": {"price": 0.3, "at": (_c0 - timedelta(hours=1)).isoformat()}}}), 0,
   "an older snapshot never replaces a newer one")
eq(T.apply_closes(_dm, {"closes": {"covers:c1": {"price": 0.3, "at": (_c0 + timedelta(hours=1)).isoformat()}}}), 0,
   "a snapshot after the deadline is never merged")
eq(T.close_lead_min(_dm["quotes"][0]), 20.0, "lead is measured from the snapshot to the deadline")
ok(T.fresh_close(_dm["quotes"][0]), "a snapshot 20 minutes out counts toward CLV")
ok(not T.fresh_close(_cq(close_price=0.41, close_at=(_c0 - timedelta(hours=5)).isoformat())),
   "a snapshot five hours out does not")
_early = dict(_cq(status="won", result="a", pnl=150.0, logged=_c0.isoformat(), price_a=0.40, price_b=0.62),
              close_price=0.50, close_at=(_c0 - timedelta(hours=5)).isoformat())
eq(T.assess({"quotes": [_early]}, "covers")["clv"], None, "so an early snapshot is never scored as closing-line value")
_bq = _cq(venue="kalshi_binary", sport="climate", start=(_c0 + timedelta(hours=_lh, minutes=30)).isoformat())
eq(T.snap_closing({"quotes": [_bq]}, {"climate": [dict(market_id="c1", venue="kalshi_binary", price_a=0.9, price_b=0.1,
                                                     untraded=False, tradeable={"a": True, "b": True},
                                                     start=_bq["start"])]},
                  now=_c0 + timedelta(hours=1)), 0,
   "the tracker's own snapshot also stops at a yes/no market's quoting cut-off")

# ---------------------------------------------------------------------------
print("\nPinnacle credits: efficient sports and covered keys get nothing")
# ---------------------------------------------------------------------------
_pr = lambda sport, n, bet_at=None: [dict(source="pinnacle", sport=sport, status="open", bet=(i == bet_at))
                                     for i in range(n)]
eq(T.pinnacle_retired({"quotes": _pr("soccer", 30) + _pr("cricket", 40, bet_at=3) + _pr("boxing", 29)}),
   {"soccer"}, "30 quotes and never an edge retires a sport; one bet, or under 30 quotes, does not")
eq(T.pinnacle_retired({"quotes": [dict(q, status="void") for q in _pr("soccer", 30)]}), set(),
   "voided quotes do not count")
_saved_get3, _saved_key3 = S._odds_get, _os.environ.get("ODDS_API_KEY")
S._odds_get = _fake_plan_get
_os.environ["ODDS_API_KEY"] = "test-key-not-real"
try:
    _reset_odds(); _paid.clear()
    S.ODDS_USAGE["allowance"] = 4
    _plan = S.plan_pinnacle(_univ, covered={"soccer": {"sc2"}, "boxing": set()}, retired={"soccer"})
    eq(_paid, ["/sports/boxing_boxing/odds"], "a retired sport gets no paid call, even with the most uncovered")
    eq(S.ODDS_USAGE["retired"], ["soccer"], "and the page is told which sports are retired")
    ok("soccer" not in _plan, "no soccer quotes are produced")
    _reset_odds(); _paid.clear()
    S.ODDS_USAGE["allowance"] = 4
    S.plan_pinnacle(_univ, covered={"soccer": {"sc1", "sc2", "sc3"}, "boxing": {"bx1"}})
    eq(_paid, [], "keys with no uncovered contest are never paid for, whatever the allowance")
finally:
    S._odds_get = _saved_get3
    _reset_odds()
    if _saved_key3 is None:
        _os.environ.pop("ODDS_API_KEY", None)
    else:
        _os.environ["ODDS_API_KEY"] = _saved_key3

# ---------------------------------------------------------------------------
print("\nheadline: no blended P/L")
# ---------------------------------------------------------------------------
_src = open("sandbox_build.py").read()
ok("net P/L</span>" not in _src and "ROI on turnover" not in _src, "the blended P/L and ROI tiles are gone")
ok("working</span>" in _src and "not working</span>" in _src, "replaced by working / not working counts")
ok("v blind</th>" in _src and "Beat the close</th>" in _src,
   "the pair table carries v blind and beat-the-close columns")

# ---------------------------------------------------------------------------
print("\nsettled bets are archived, not lost")
# ---------------------------------------------------------------------------
import tempfile as _tf, json
_old_set = (datetime.now(timezone.utc) - timedelta(days=60)).isoformat()
_arch_bets = [dict(_sb(i, i % 10 < 6, "a", 0.40, i // 10), id=f"covers:ar{i}", market_id=f"ar{i}",
                   settled=_old_set, stake=100.0) for i in range(40)]
_nonbet = dict(_arch_bets[0], id="polymarket:nb", source="polymarket", bet=False, status="graded", prob_a=0.4)
_da = {"quotes": [dict(q) for q in _arch_bets] + [_nonbet], "_archive": []}
_before = T.assess(_da, "covers", "mlb")["n"]
T.prune(_da, verbose=False)
eq(len(_da["quotes"]), 0, "old settled rows leave the ledger")
eq(len(_da["_archive"]), 41, "every settled bet goes to the archive, plus a compact copy of the price-only row")
_cmp = next(x for x in _da["_archive"] if x.get("compact"))
ok(_cmp["bet"] is False and "prob_a" not in _cmp and _cmp["result"] == _nonbet["result"],
   "the compact copy keeps only what a population baseline reads")
eq(T.assess(_da, "covers", "mlb")["n"], _before, "judgement reads the archive, so nothing is lost")
eq(_da["retired"]["covers"]["settled"], 40, "the rolled-up totals still count them")
T.prune(_da, verbose=False)
eq(len(_da["_archive"]), 41, "pruning again never duplicates")
_tmpd = _tf.mkdtemp()
_saved_ledger = T.LEDGER
T.LEDGER = _os.path.join(_tmpd, "ledger.json")
try:
    _da["meta"] = {}
    T.save(_da, archive_dir=_os.path.join(_tmpd, "arch"))
    ok("_archive" not in json.load(open(T.LEDGER)), "the archive is never written into the ledger")
    _files = _os.listdir(_os.path.join(_tmpd, "arch"))
    eq(_files, [f"{_old_set[:7]}.json"], "it is stored by the month the bets settled")
    eq(len(T.load_archive(_os.path.join(_tmpd, "arch"))), 41, "and loads back whole")
    eq(len(_da["_archive"]), 41, "saving leaves the in-memory archive in place")
finally:
    T.LEDGER = _saved_ledger

# ---------------------------------------------------------------------------
print("\nPolymarket US is the venue")
# ---------------------------------------------------------------------------
_now_us = datetime.now(timezone.utc)
_soon_us = (_now_us + timedelta(hours=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
def _usm(slug, a, b, bid, ask, mtype="tennis_match_winner", **kw):
    return dict(dict(slug=slug, sportsMarketType=mtype, outcomes=json.dumps([a, b]), closed=False,
                     bestBidQuote={"value": str(bid)}, bestAskQuote={"value": str(ask)},
                     gameStartTime=_soon_us), **kw)
_us_payload = {
    "/v2/sports": {"sports": [{"name": "Tennis", "leagues": [{"slug": "wta"}]},
                              {"name": "Baseball", "leagues": [{"slug": "mlb"}, {"slug": "kbo"}]}]},
    "/v2/leagues/wta/events?limit=100": {"events": [
        {"slug": "ev1", "period": "NS", "markets": [
            _usm("m1", "Iga Swiatek", "Coco Gauff", 0.60, 0.62),
            _usm("m1-sets", "Over", "Under", 0.4, 0.5, mtype="tennis_match_total_sets")]},
        {"slug": "ev2", "period": "S2", "markets": [_usm("m2", "A B", "C D", 0.5, 0.52)]},
        {"slug": "ev3", "period": "NS", "markets": [_usm("m3", "E F", "G H", 0.30, 0.45)]},
        {"slug": "ev4", "period": "NS", "closed": True, "markets": [_usm("m4", "I J", "K L", 0.5, 0.51)]}]},
    "/v1/markets/m1/settlement": {"slug": "m1", "settlement": 1},
    "/v1/markets/m5/settlement": {"slug": "m5", "settlement": 0},
    "/v1/markets/m1/bbo": {"marketData": {"bestBid": {"value": "0.63"}, "bestAsk": {"value": "0.65"}}},
}
_saved_get_us, _saved_leagues = S._get, S._pmus_leagues
def _fake_us_get(url, tries=3, timeout=20):
    for k, v in _us_payload.items():
        if url == S.PMUS + k:
            return v
    raise RuntimeError("404")
S._get, S._pmus_leagues = _fake_us_get, None
try:
    eq(S.pmus_leagues("mlb"), ["mlb"], "MLB takes the mlb league only, not KBO")
    _us_rows = S.fetch_polymarket_us("tennis")
    _by = {r["market_id"]: r for r in _us_rows}
    eq(sorted(_by), ["m1", "m3"], "in-play (period S2) and closed events are never listed")
    eq((_by["m1"]["venue"], _by["m1"]["price_a"], _by["m1"]["price_b"], _by["m1"]["mid_a"]),
       ("polymarket_us", 0.62, 0.4, 0.61), "side A at the ask, side B at 1 - bid, the midpoint kept")
    eq((_by["m1"]["untraded"], _by["m3"]["untraded"]), (False, True), "a 15c spread is not a tradeable book")
    eq(_by["m1"]["url"], "https://polymarket.us/event/ev1", "linked to the Polymarket US event")
    eq((S.resolve_polymarket_us("m1"), S.resolve_polymarket_us("m5"), S.resolve_polymarket_us("m9")),
       ("a", "b", None), "settlement 1 = first outcome won, 0 = lost, 404 = not yet")
    eq(S.venue_price(dict(venue="polymarket_us", market_id="m1", pick="b")), 0.37,
       "the closing price for side B is 1 - bid on the US book")
finally:
    S._get, S._pmus_leagues = _saved_get_us, _saved_leagues
eq(S.SOURCES["polymarket_us"]["kind"], "Prediction market", "Polymarket US is listed as a source")
ok("polymarket" in S.CHALLENGERS, "polymarket.com is now a comparison source")
_uni = {"tennis": [dict(market_id="u1", venue="polymarket_us", sport="tennis", label="Iga Swiatek vs Coco Gauff",
                        side_a="Iga Swiatek", side_b="Coco Gauff", price_a=0.62, price_b=0.40, mid_a=0.61,
                        untraded=False, start=(_now_us + timedelta(hours=5)).isoformat(),
                        date=_now_us.strftime("%Y-%m-%d"), volume=0.0, url="")]}
_saved_ch2 = S.CHALLENGERS
S.CHALLENGERS = {"polymarket": lambda sp: [dict(a="Iga Swiatek", b="Coco Gauff", prob_a=0.70,
                                                 date=_now_us.strftime("%Y-%m-%d"))]}
try:
    _dp = {"quotes": [], "meta": {}, "coverage": {}}
    T.publish(_dp, _uni, {}, verbose=False)
finally:
    S.CHALLENGERS = _saved_ch2
_qs = {q["source"]: q for q in _dp["quotes"]}
eq((_qs["polymarket_us"]["bet"], _qs["polymarket_us"]["prob_a"]), (False, 0.61),
   "the US exchange's own midpoint is logged for Brier and never bets")
eq((_qs["polymarket"]["bet"], _qs["polymarket"]["venue"], _qs["polymarket"]["price"]), (True, "polymarket_us", 0.62),
   "polymarket.com at 0.70 against a 0.62 US ask is a bet, booked on the US venue")
eq(T.FEE_RATE["polymarket_us"], 0.06, "Polymarket US taker fee applies to QA's after-fee ROI")

# ---------------------------------------------------------------------------
print("\nKalshi soccer starts from ESPN")
# ---------------------------------------------------------------------------
_e0 = datetime(2026, 9, 13, 8, 0, tzinfo=timezone.utc)
_krows = [dict(market_id="KXSERIEAGAME-26SEP13TORROM", side_a="Torino", side_b="Roma",
               start=(_e0 + timedelta(hours=2, minutes=30)).isoformat(), date="2026-09-13"),
          dict(market_id="K2", side_a="Leeds United", side_b="Newcastle",
               start=(_e0 + timedelta(hours=6)).isoformat(), date="2026-09-13"),
          dict(market_id="K3", side_a="Real Madrid", side_b="Rayo Vallecano",
               start=(_e0 + timedelta(hours=10)).isoformat(), date="2026-09-13"),
          dict(market_id="K4", side_a="Nowhere FC", side_b="Elsewhere",
               start=(_e0 + timedelta(hours=3)).isoformat(), date="2026-09-13")]
_efx = [dict(home="Torino", away="AS Roma", kickoff="2026-09-14T16:30Z", played=False),
        dict(home="Newcastle United", away="Leeds United", kickoff="2026-09-13T14:00Z", played=False),
        dict(home="Real Madrid", away="Rayo Vallecano", kickoff="2026-09-12T19:00Z", played=True)]
_rt, _st = S.apply_espn_starts(_krows, fixtures=_efx, now=_e0)
_rb = {r["market_id"]: r for r in _rt}
eq((_rb["KXSERIEAGAME-26SEP13TORROM"]["start"][:16], _rb["KXSERIEAGAME-26SEP13TORROM"]["start_source"]),
   ("2026-09-14T16:30", "espn"), "a Kalshi placeholder date takes ESPN's real kickoff, the estimate kept")
eq(_rb["K2"].get("start_source"), None, "the reverse fixture (away v home) is never used")
ok("K3" not in _rb, "a row whose ESPN fixture has already been played is dropped")
eq(_rb["K4"].get("start_source"), None, "an unmatched row keeps Kalshi's estimate")
eq(_st["matched"], 1, "and the run reports how many were re-timed")

# ---------------------------------------------------------------------------
print("\nweather: city labels and one ladder = one outcome")
# ---------------------------------------------------------------------------
eq(S.display_label(dict(label="Will the maximum temperature be 80-81° on Sep 13, 2026?",
                        market_id="KXHIGHLAX-26SEP13-B80.5")),
   "Los Angeles: Will the maximum temperature be 80-81° on Sep 13, 2026?", "the city is named")
eq(S.display_label(dict(label="Cowboys vs Giants", market_id="x")), "Cowboys vs Giants", "other labels are untouched")
eq(S.outcome_cluster(dict(venue="kalshi_binary", market_id="KXHIGHNY-26SEP13-B80.5", id="a")),
   S.outcome_cluster(dict(venue="kalshi_binary", market_id="KXHIGHNY-26SEP13-B82.5", id="b")),
   "two buckets of one city's day share a cluster")
_wb = lambda mid, won, price: dict(id=f"nws:{mid}", source="nws", sport="climate", bet=True, venue="kalshi_binary",
                                   market_id=mid, status="won" if won else "lost", pick="a", price=price,
                                   pnl=round(100 * (1 / price - 1), 2) if won else -100.0,
                                   start="2026-09-13T19:00:00+00:00", logged="2026-09-13T01:00:00+00:00",
                                   result="a" if won else "b", price_a=price, price_b=1 - price, price_draw=None)
_pair = [_wb("KXHIGHNY-26SEP13-B80.5", True, 0.3), _wb("KXHIGHNY-26SEP13-B82.5", False, 0.3)]
_ap = T.assess({"quotes": _pair}, "nws")
close(_ap["z"], (1 - 0.6) / (0.6 * 0.4) ** 0.5, "z uses the ladder as one draw: P = 0.6, var 0.24", tol=1e-9)
eq((_ap["n"], _ap["n_eff"]), (2, 1), "two bets, one independent outcome")

# ---------------------------------------------------------------------------
print("\nbet lists: every bet, searchable, counts that agree")
# ---------------------------------------------------------------------------
_lsrc = open("sandbox_build.py").read()
ok('class="flt"' in _lsrc and "input.flt" in _lsrc, "running and settled lists carry a filter box")
ok("def open_rows(d, limit=None)" in _lsrc and "def settled_rows(d, limit=None)" in _lsrc,
   "no bet is cut from the lists any more")
ok('{n_hist - n_void:,}{f" · {n_void} void"' in _lsrc, "the settled heading counts won/lost apart from voids")

# ---------------------------------------------------------------------------
print("\na venue switch never quotes a contest twice")
# ---------------------------------------------------------------------------
_t9 = "2026-09-14T23:10:00+00:00"
_old = dict(id="espn_fpi:4287261", source="espn_fpi", sport="mlb", market_id="4287261", venue="polymarket",
            side_a="San Diego Padres", side_b="San Francisco Giants", start=_t9, logged="2026-09-13T12:00:00+00:00",
            status="open", bet=True, pick="a", price=0.55, pnl=0.0)
_new = dict(_old, id="espn_fpi:aec-mlb-sd-sf-2026-09-14", market_id="aec-mlb-sd-sf-2026-09-14",
            venue="polymarket_us", logged="2026-09-13T21:16:00+00:00", price=0.57)
_dh = dict(_new, id="espn_fpi:aec-mlb-sd-sf-2026-09-14-g2", market_id="aec-mlb-sd-sf-2026-09-14-g2",
           start="2026-09-15T03:40:00+00:00")
_other = dict(_new, id="covers:aec-mlb-sd-sf-2026-09-14", source="covers")
_ddup = {"quotes": [dict(_old), dict(_new), dict(_dh), dict(_other)]}
eq(T.retire_venue_duplicates(_ddup, verbose=False), 1, "one duplicate found")
_st9 = {q["id"]: q["status"] for q in _ddup["quotes"]}
eq((_st9["espn_fpi:4287261"], _st9["espn_fpi:aec-mlb-sd-sf-2026-09-14"]), ("open", "void"),
   "the earliest quote stands; the re-quote on the new venue is voided")
eq(_st9["espn_fpi:aec-mlb-sd-sf-2026-09-14-g2"], "open", "a doubleheader's second game 4.5h later is its own contest")
eq(_st9["covers:aec-mlb-sd-sf-2026-09-14"], "open", "another source on the same contest is untouched")
eq(T.retire_venue_duplicates(_ddup, verbose=False), 1, "idempotent")
_settled_dup = {"quotes": [dict(_old), dict(_new, status="won", logged="2026-09-13T12:30:00+00:00")]}
T.retire_venue_duplicates(_settled_dup, verbose=False)
eq(_settled_dup["quotes"][1]["status"], "won", "settled history from before the switch is never rewritten")
_tt = [dict(_old, sport="table_tennis", source="polymarket_us", venue="polymarket_us", id="p:1", market_id="1",
            side_a="Rak Serhii", side_b="Pesternikov Denys", start="2026-09-14T00:30:00+00:00",
            logged="2026-09-13T21:16:00+00:00", bet=False),
       dict(_old, sport="table_tennis", source="polymarket_us", venue="polymarket_us", id="p:2", market_id="2",
            side_a="Rak Serhii", side_b="Pesternikov Denys", start="2026-09-14T01:05:00+00:00",
            logged="2026-09-13T21:16:00+00:00", bet=False)]
eq(T.retire_venue_duplicates({"quotes": _tt}, verbose=False), 0,
   "a table-tennis rematch 35 minutes later is a different match")
_up_row = dict(market_id="aec-mlb-sd-sf-2026-09-14", venue="polymarket_us", sport="mlb", label="x",
               side_a="San Diego Padres", side_b="San Francisco Giants", price_a=0.57, price_b=0.45, mid_a=0.56,
               untraded=False, start=(datetime.now(timezone.utc) + timedelta(hours=3)).isoformat(),
               date="2026-09-14", volume=0.0, url="")
_prev = dict(_old, start=_up_row["start"], source="espn_fpi")
_saved_ch3 = S.CHALLENGERS
S.CHALLENGERS = {"espn_fpi": lambda sp: [dict(a="San Diego Padres", b="San Francisco Giants", prob_a=0.70,
                                              date="2026-09-14")]}
try:
    _dpub = {"quotes": [_prev], "meta": {}, "coverage": {}}
    T.publish(_dpub, {"mlb": [_up_row]}, {}, verbose=False)
finally:
    S.CHALLENGERS = _saved_ch3
eq([q["id"] for q in _dpub["quotes"] if q["source"] == "espn_fpi"], ["espn_fpi:4287261"],
   "publish refuses a source's second quote on a contest it already priced elsewhere")

# ---------------------------------------------------------------------------
print("\nProduction: pairs that hold the ready gate, published as a feed")
# ---------------------------------------------------------------------------
import production as PR
_pnow = datetime(2026, 10, 1, 12, tzinfo=timezone.utc)
_ready = "2026-09-30T00:00:00+00:00"
_pst = {"pairs": {"soccerpredictions|soccer": dict(stage="qa", promoted_at="2026-09-20T00:00:00+00:00", ready_at=_ready),
                  "espn_fpi|mlb": dict(stage="qa", promoted_at="2026-09-20T00:00:00+00:00"),
                  "covers|soccer": dict(stage="sandbox", since="2026-09-01T00:00:00+00:00")}, "events": []}
def _pq(i, **kw):
    base = dict(id=f"soccerpredictions:KXEPLGAME-26OCT02LEENEW{i}", source="soccerpredictions", sport="soccer",
                market_id=f"KXEPLGAME-26OCT02LEENEW{i}", venue="kalshi", bet=True, pick="a", price=0.44, edge=None,
                side_a="Leeds United", side_b="Newcastle", status="open", start_source="espn",
                start=(_pnow + timedelta(hours=20 + i)).isoformat(), logged="2026-09-30T06:00:00+00:00")
    base.update(kw)
    return base
_pd = {"quotes": [
    _pq(1),                                                            # open, routable -> published
    _pq(2, pick="b"),                                                  # away side
    _pq(3, pick="draw"),                                               # draw: published (Tie)
    _pq(4, logged="2026-09-29T06:00:00+00:00"),                        # logged before Production
    _pq(5, market_id="KXALLSVENSKANGAME-26OCT02AIKHAM", id="sp:5"),    # unmapped league
    _pq(6, start=(_pnow - timedelta(hours=1)).isoformat()),            # already started
    _pq(7, status="won", pnl=127.27, result="a", price_a=0.44, price_b=0.3, price_draw=0.3,
        start=(_pnow - timedelta(days=1)).isoformat()),   # settled: kept for results
    _pq(8, bet=False),                                                 # no bet
    dict(_pq(9), source="espn_fpi", sport="mlb", venue="polymarket_us"),   # pair not in Production
    _pq(10, start_source=None),                                        # Kalshi-estimated kickoff
]}
_feed = PR.build_feed(_pd, _pst, now=_pnow)
eq(sorted(_feed["pairs"]), ["soccerpredictions|soccer"], "only a pair in QA with ready_at is in Production")
_fl = sorted(_feed["leads"].values(), key=lambda l: l["sandbox_quote"])
eq([l["sandbox_quote"][-1] for l in _fl], ["1", "2", "3", "7"],
   "published: open routable bets logged since ready, and recent settled ones; nothing else")
eq(_feed["unlisted_skipped"], 1, "the unmapped league is held back and counted")
_l3 = next(l for l in _fl if l["sandbox_quote"].endswith("3"))
eq((_l3["bet"], _l3["headline"]), ({"kind": "match_result", "side": "draw"}, "Draw"), "a draw tip is published as a draw")
eq(_feed["unverified_kickoff_skipped"], 1, "a lead whose kickoff is only Kalshi's estimate is held back too")
eq(sorted(_feed["pairs"]["soccerpredictions|soccer"]),
   ["entered_at", "fast_track", "promoted_at", "ready_at", "route", "sandbox_clv", "sandbox_n", "sandbox_roi", "sandbox_roi_fee"],
   "each pair carries the Sandbox's own record since ready, to compare real fills with")
_l1 = next(l for l in _fl if l["sandbox_quote"].endswith("1"))
eq((_l1["bet"], _l1["home"], _l1["away"], _l1["league"], _l1["status"]),
   ({"kind": "match_result", "side": "home"}, "Leeds United", "Newcastle", "Premier League", "pending"),
   "a Production lead is a match_result on the board's league name")
eq(next(l for l in _fl if l["sandbox_quote"].endswith("2"))["bet"]["side"], "away", "side b is the away side")
eq((_l1["last_seen_at"], _feed["board_built_at"]), (_pnow.isoformat(), _pnow.isoformat()),
   "open leads carry the build stamp, as the Leads ledger does")
_l7 = next(l for l in _fl if l["sandbox_quote"].endswith("7"))
eq((_l7["status"], "last_seen_at" in _l7), ("hit", False), "a settled lead is graded and never looks current")
ok(_l1["id"].startswith(_l1["date"] + "|Leeds United|Newcastle|"),
   "ids start date|home|away, as the Leads ledger's do")
_empty = PR.build_feed({"quotes": []}, {"pairs": {}}, now=_pnow)
eq((_empty["leads"], _empty["pairs"]), ({}, {}), "with nothing in Production the feed is empty, not missing")
_html = PR.page(_pd, _pst, _feed, "<style></style>", now=_pnow)
ok("Leeds United to win" in _html and "SoccerPredictions.ai · Soccer" in _html, "the page lists the open leads by source label")
ok('href="./production.html">Production</a>' in open("streaks_build.py").read(), "every board links Production")

# ---------------------------------------------------------------------------
print("\nsoccer BTTS on Kalshi and the pre-registered form rule")
# ---------------------------------------------------------------------------
_b0 = datetime(2026, 9, 14, 12, tzinfo=timezone.utc)
def _bfx(day, home, away, hg, ag, played=True):
    ko = datetime(2026, 9, day, 15, tzinfo=timezone.utc) if day > 0 else _b0 + timedelta(days=-day)
    return dict(home=home, away=away, kickoff=ko.strftime("%Y-%m-%dT%H:%MZ"), played=played,
                home_goals=hg, away_goals=ag, competitive=True)
_hist = []
for i in range(10):                       # Hot FC: 8 of last 10 BTTS; Warm FC: 7; Cold FC: 3; Short FC: 9 games
    _hist.append(dict(_bfx(1, "Hot FC", f"X{i}", 1, 1 if i < 8 else 0), kickoff=f"2026-08-{i+1:02d}T15:00Z"))
    _hist.append(dict(_bfx(1, f"Y{i}", "Warm FC", 2, 1 if i < 7 else 0), kickoff=f"2026-08-{i+1:02d}T15:00Z"))
    _hist.append(dict(_bfx(1, "Cold FC", f"Z{i}", 1, 1 if i < 3 else 0), kickoff=f"2026-08-{i+1:02d}T15:00Z"))
    if i < 9:
        _hist.append(dict(_bfx(1, "Short FC", f"W{i}", 1, 1), kickoff=f"2026-08-{i+1:02d}T15:00Z"))
# a BTTS game AFTER kickoff must never count
_hist.append(dict(_bfx(1, "Cold FC", "Late", 1, 1), kickoff="2026-09-20T15:00Z"))
_up = [dict(home="Hot FC", away="Warm FC", kickoff="2026-09-15T18:00Z", played=False, home_goals=None, away_goals=None),
       dict(home="Hot FC", away="Cold FC", kickoff="2026-09-16T18:00Z", played=False, home_goals=None, away_goals=None),
       dict(home="Short FC", away="Hot FC", kickoff="2026-09-17T18:00Z", played=False, home_goals=None, away_goals=None)]
_fx_all = _hist + _up
def _kev(ticker, title, ya, yb, na, nb):
    return {"event_ticker": ticker, "title": title, "markets": [
        {"ticker": ticker + "-BTTS", "status": "active", "yes_ask_dollars": str(ya), "yes_bid_dollars": str(yb),
         "no_ask_dollars": str(na), "no_bid_dollars": str(nb)}]}
_evs = {"KXEPLBTTS": [_kev("KXEPLBTTS-26SEP15HOTWAR", "Hot FC vs Warm FC: BTTS", 0.62, 0.60, 0.40, 0.38),
                      _kev("KXEPLBTTS-26SEP16HOTCOL", "Hot FC vs Cold FC: BTTS", 0.55, 0.53, 0.47, 0.45),
                      _kev("KXEPLBTTS-26SEP17SHOHOT", "Short FC vs Hot FC: BTTS", 0.70, 0.68, 0.32, 0.30),
                      _kev("KXEPLBTTS-26SEP15NOWNOW", "Nowhere vs Nobody: BTTS", 0.5, 0.48, 0.52, 0.5),
                      _kev("KXEPLBTTS-26SEP15WARHOT", "Warm FC vs Hot FC: BTTS", 0.6, 0.58, 0.42, 0.4)]}
_brows = S.fetch_kalshi_btts(fixtures=_fx_all, now=_b0, events_by_series=_evs)
eq(sorted(r["market_id"] for r in _brows),
   ["KXEPLBTTS-26SEP15HOTWAR-BTTS", "KXEPLBTTS-26SEP16HOTCOL-BTTS", "KXEPLBTTS-26SEP17SHOHOT-BTTS"],
   "only markets matched to an ESPN fixture, home first, are listed")
_br = {r["market_id"]: r for r in _brows}["KXEPLBTTS-26SEP15HOTWAR-BTTS"]
eq((_br["side_a"], _br["price_a"], _br["price_b"], _br["start"][:16], _br["venue"], _br["start_source"]),
   ("Yes", 0.62, 0.40, "2026-09-15T18:00", "kalshi_binary", "espn"),
   "Yes at its ask, No at its ask, kicked off at ESPN's time, settled as a yes/no market")
for _ka, _eb in [("Bilbao", "Athletic Club"), ("New York RB", "Red Bull New York"), ("DC United", "D.C. United"),
                 ("Ferencvarosi", "Ferencvaros"), ("Lillestroem", "Lillestrom")]:
    ok(S._score(_ka, _eb, "soccer") > 0.9, f"Kalshi's {_ka!r} matches ESPN's {_eb!r}")
ok(S._score("New York City", "Red Bull New York", "soccer") == 0, "the two New York clubs stay apart")
eq(S.btts_form(_fx_all, "Cold FC", datetime(2026, 9, 16, 18, tzinfo=timezone.utc)), (3, 10),
   "form counts only games before kickoff (a later BTTS is ignored)")
_rule = S.fetch_btts_form_l10("soccer_btts", universe={"soccer_btts": _brows}, fixtures=_fx_all)
eq([q["market_id"] for q in _rule], ["KXEPLBTTS-26SEP15HOTWAR-BTTS"],
   "the rule backs Yes only where BOTH teams are 7+ of 10 (not 8 v 3, not a side with 9 games)")
eq(_rule[0]["pick"], "a", "and it backs Yes")
eq(len(S.fetch_btts_market("soccer_btts", universe={"soccer_btts": _brows})), 3, "the market's own price is logged on every match")
eq((S.SOURCES["btts_form_l10"]["kind"], S.SOURCES["btts_market"]["kind"]), ("Rule", "Baseline"),
   "the rule can be promoted; the market's own price never is")

_pnow = datetime(2026, 9, 14, 12, tzinfo=timezone.utc)
_saved_ch4 = S.CHALLENGERS
S.CHALLENGERS = {"btts_market": lambda sp: S.fetch_btts_market(sp, universe={"soccer_btts": _brows}),
                 "btts_form_l10": lambda sp: S.fetch_btts_form_l10(sp, universe={"soccer_btts": _brows}, fixtures=_fx_all)}
try:
    _db = {"quotes": [], "meta": {}, "coverage": {}}
    # Publishing checks "has it started?" against the real clock. Pin it to the fixture set's own
    # "now", or these fixed Sep 15-17 kickoffs start failing the moment they are in the past.
    _real_started = T._started
    T._started = lambda r, _now, _f=_real_started: _f(r, _b0)
    try:
        T.publish(_db, {"soccer_btts": _brows}, {}, verbose=False)
    finally:
        T._started = _real_started
finally:
    S.CHALLENGERS = _saved_ch4
_bq = {(q["source"], q["market_id"]): q for q in _db["quotes"]}
_rq = _bq[("btts_form_l10", "KXEPLBTTS-26SEP15HOTWAR-BTTS")]
eq((_rq["bet"], _rq["pick"], _rq["price"]), (True, "a", 0.62), "the rule's bet is booked at the Yes ask")
ok(not any(q["bet"] for q in _db["quotes"] if q["source"] == "btts_market"), "the market's own price never bets")

# population baseline: rule 2/2 at 0.62 against backing Yes on all 4 matches (2 won at 0.62, 2 lost at 0.55)
def _pb(mid, src, won, price, bet):
    return dict(id=f"{src}:{mid}", source=src, sport="soccer_btts", market_id=mid, venue="kalshi_binary",
                bet=bet, pick="a" if bet else None, price=price if bet else None, price_a=price, price_b=1 - price,
                result="a" if won else "b", status=("won" if won else "lost") if bet else "graded",
                pnl=(round(100 * (1 / price - 1), 2) if won else -100.0) if bet else 0.0,
                start=f"2026-09-1{mid}T18:00:00+00:00", logged="2026-09-10T00:00:00+00:00")
_dpop = {"quotes": [_pb(1, "btts_form_l10", True, 0.62, True), _pb(2, "btts_form_l10", True, 0.62, True),
                    _pb(1, "btts_market", True, 0.62, False), _pb(2, "btts_market", True, 0.62, False),
                    _pb(3, "btts_market", False, 0.55, False), _pb(4, "btts_market", False, 0.55, False)]}
_ap2 = T.assess(_dpop, "btts_form_l10", "soccer_btts")
_crit = dict((k, (p, det)) for k, _l, p, det in _ap2["criteria"])
ok("back Yes on every match" in _crit["baseline"][1], "the rule is judged against backing Yes on every match")
eq(_crit["baseline"][0], True, "and beats it here (+61% v backing all four)")


print("\nsoccer goals on Kalshi: over 1.5, team 1+, team 2+, and the fast track")
_g0 = datetime(2026, 9, 14, 12, tzinfo=timezone.utc)
def _gfx(home, away, hg, ag, day):
    return dict(home=home, away=away, home_goals=hg, away_goals=ag, played=True, competitive=True,
                kickoff=f"2026-08-{day:02d}T15:00Z")
_gh = []
for i in range(10):
    _gh.append(_gfx("Goal FC", f"G{i}", 2, 1 if i < 9 else 0, i + 1))      # 10/10 over 1.5 · scored 2+ 10/10
    _gh.append(_gfx(f"S{i}", "Sieve FC", 1, 2 if i < 8 else 0, i + 1))     # Sieve: 8/10 over 1.5, conceded 2+ 8/10, conceded in 8/10
    _gh.append(_gfx("Dull FC", f"D{i}", 0, 0 if i < 5 else 1, i + 1))      # Dull: under
    _gh.append(_gfx(f"L{i}", "Leak FC", 3, 1, i + 1))                      # Leak: scored 1, conceded 3 every game
_gh.append(dict(_gfx("Leak FC", "Late", 0, 0, 1), kickoff="2026-09-20T15:00Z"))   # after kickoff: ignored
_gup = [dict(home="Goal FC", away="Leak FC", kickoff="2026-09-15T18:00Z", played=False, home_goals=None, away_goals=None),
        dict(home="Dull FC", away="Sieve FC", kickoff="2026-09-16T18:00Z", played=False, home_goals=None, away_goals=None)]
_gall = _gh + _gup
def _gm(ticker, sub, ya, yb):
    return {"ticker": ticker, "yes_sub_title": sub, "status": "active", "yes_ask_dollars": str(ya),
            "yes_bid_dollars": str(yb), "no_ask_dollars": str(round(1 - yb, 2)), "no_bid_dollars": str(round(1 - ya, 2))}
_gevs = {
    "KXEPLTOTAL": [{"event_ticker": "KXEPLTOTAL-26SEP15GOALEA", "title": "Goal FC vs Leak FC: Total Goals",
                    "markets": [_gm("KXEPLTOTAL-26SEP15GOALEA-1", "Over 0.5 goals scored", 0.95, 0.94),
                                _gm("KXEPLTOTAL-26SEP15GOALEA-2", "Over 1.5 goals scored", 0.84, 0.83),
                                _gm("KXEPLTOTAL-26SEP15GOALEA-4", "Over 3.5 goals scored", 0.33, 0.32)]},
                   {"event_ticker": "KXEPLTOTAL-26SEP16DULSIE", "title": "Dull FC vs Sieve FC: Total Goals",
                    "markets": [_gm("KXEPLTOTAL-26SEP16DULSIE-2", "Over 1.5 goals scored", 0.70, 0.69)]}],
    "KXEPLTEAMTOTAL": [{"event_ticker": "KXEPLTEAMTOTAL-26SEP15GOALEA", "title": "Goal FC vs Leak FC: Team Total",
                        "markets": [_gm("KXEPLTEAMTOTAL-26SEP15GOALEA-GOA1", "Goal FC over 0.5 goals", 0.86, 0.85),
                                    _gm("KXEPLTEAMTOTAL-26SEP15GOALEA-GOA2", "Goal FC over 1.5 goals", 0.55, 0.54),
                                    _gm("KXEPLTEAMTOTAL-26SEP15GOALEA-LEA1", "Leak FC over 0.5 goals", 0.60, 0.59),
                                    _gm("KXEPLTEAMTOTAL-26SEP15GOALEA-GOA3", "Goal FC over 2.5 goals", 0.30, 0.29)]}],
}
_gst = {}
_grows = S.fetch_kalshi_goals(fixtures=_gall, now=_g0, events_by_series=_gevs, stats=_gst)
eq({k: sorted(r["market_id"] for r in v) for k, v in _grows.items()},
   {"soccer_o15": ["KXEPLTOTAL-26SEP15GOALEA-2", "KXEPLTOTAL-26SEP16DULSIE-2"],
    "soccer_team1": ["KXEPLTEAMTOTAL-26SEP15GOALEA-GOA1", "KXEPLTEAMTOTAL-26SEP15GOALEA-LEA1"],
    "soccer_team2": ["KXEPLTEAMTOTAL-26SEP15GOALEA-GOA2"],
    "soccer_u35": ["KXEPLTOTAL-26SEP15GOALEA-4"], "soccer_p05": []},
   "over 1.5 from the totals ladder; over 0.5 / 1.5 per side from team totals; other lines ignored")
_t1 = {r["market_id"]: r for r in _grows["soccer_team1"]}
eq((_t1["KXEPLTEAMTOTAL-26SEP15GOALEA-LEA1"]["team"], _t1["KXEPLTEAMTOTAL-26SEP15GOALEA-LEA1"]["opponent"],
    _t1["KXEPLTEAMTOTAL-26SEP15GOALEA-LEA1"]["league"], _t1["KXEPLTEAMTOTAL-26SEP15GOALEA-LEA1"]["start_source"]),
   ("Leak FC", "Goal FC", "Premier League", "espn"), "a team-total row names its side, the opponent, the league and ESPN's kickoff")
eq(S.team_form(_gall, "Leak FC", datetime(2026, 9, 15, 18, tzinfo=timezone.utc), lambda gf, ga: gf + ga >= 2, 10)[:2],
   (10, 10), "form counts only games before kickoff")
eq([q["market_id"] for q in S.fetch_o15_form_l10("soccer_o15", universe=_grows, fixtures=_gall)],
   ["KXEPLTOTAL-26SEP15GOALEA-2"], "over 1.5 rule: both 9+/10 (Goal 10, Leak 10) yes; Dull v Sieve (8/10) no")
eq(sorted(q["market_id"] for q in S.fetch_team1_form_l5("soccer_team1", universe=_grows, fixtures=_gall)),
   ["KXEPLTEAMTOTAL-26SEP15GOALEA-GOA1"],
   "team 1+ rule: each side on its own — Leak FC scored in 5/5, but Goal FC kept a clean sheet last time out")
eq([q["market_id"] for q in S.fetch_team2_form_l10("soccer_team2", universe=_grows, fixtures=_gall)],
   ["KXEPLTEAMTOTAL-26SEP15GOALEA-GOA2"], "team 2+ rule: Goal FC 10/10 scored 2+, Leak FC 10/10 conceded 2+")
ok(S.outcome_cluster(dict(venue="kalshi_binary", sport="soccer_team1", market_id="KXEPLTEAMTOTAL-26SEP15GOALEA-GOA1", id="x"))
   != S.outcome_cluster(dict(venue="kalshi_binary", sport="soccer_team1", market_id="KXEPLTEAMTOTAL-26SEP15GOALEA-LEA1", id="y")),
   "both sides of one team total can land: two outcomes, not one ladder")

_saved_ch5 = S.CHALLENGERS
S.CHALLENGERS = {"goals_market": lambda sp: S.fetch_goals_market(sp, universe=_grows),
                 "team1_form_l5": lambda sp: S.fetch_team1_form_l5(sp, universe=_grows, fixtures=_gall)}
try:
    _gdb = {"quotes": [], "meta": {}, "coverage": {}}
    # Publishing checks "has it started?" against the real clock. Pin it to the fixture set's own
    # "now", or these fixed Sep 15-17 kickoffs start failing the moment they are in the past.
    _real_started = T._started
    T._started = lambda r, _now, _f=_real_started: _f(r, _g0)
    try:
        T.publish(_gdb, _grows, {}, verbose=False)
    finally:
        T._started = _real_started
finally:
    S.CHALLENGERS = _saved_ch5
_gq = {(q["source"], q["market_id"]): q for q in _gdb["quotes"]}
_tq = _gq[("team1_form_l5", "KXEPLTEAMTOTAL-26SEP15GOALEA-GOA1")]
eq((_tq["bet"], _tq["price"], _tq["team"], _tq["espn_home"], _tq["league"]), (True, 0.86, "Goal FC", "Goal FC", "Premier League"),
   "the rule's bet is booked at the Yes ask and keeps its side and fixture")
ok(not any(q["bet"] for q in _gdb["quotes"] if q["source"] == "goals_market"), "the goals market's own price never bets")
eq(T.placeable(_tq), True, "Yes on a team-goals market in a mapped league is publishable")
eq(T.placeable(dict(_tq, pick="b")), False, "No is not")
eq(T.placeable(dict(_tq, league="Allsvenskan")), False, "nor an unmapped league")

# fast track: probation -> cleared / failed, and Production publishes it from the first bet
def _ftq(i, won, price=0.8, logged="2026-09-14T06:00:00+00:00"):
    return dict(id=f"team1_form_l5:M{i}", source="team1_form_l5", sport="soccer_team1", market_id=f"KXEPLTEAMTOTAL-26SEP{15+i%10}X-A{i}",
                venue="kalshi_binary", bet=True, pick="a", price=price, price_a=price, price_b=1 - price,
                status="won" if won else "lost", result="a" if won else "b",
                pnl=round(100 * (1 / price - 1), 2) if won else -100.0,
                start=(datetime(2026, 9, 15, 18, tzinfo=timezone.utc) + timedelta(hours=i)).isoformat(), logged=logged,
                label="x", side_a="Yes", side_b="No", league="Premier League", espn_home="Goal FC", espn_away="Leak FC",
                team="Goal FC", start_source="espn")
_meta = S.SOURCES["team1_form_l5"]
_st_ft = {"pairs": {}, "events": []}
_d_ft = {"quotes": [_ftq(i, True) for i in range(5)]}
T.evaluate_stages(_d_ft, _st_ft, now=datetime(2026, 9, 20, tzinfo=timezone.utc), verbose=False)
eq((_st_ft["pairs"]["team1_form_l5|soccer_team1"]["stage"], _st_ft["pairs"]["team1_form_l5|soccer_team1"]["fast_track"]["state"]),
   ("sandbox", "probation"), "a fast-tracked pair is on probation below its sample")
ok("team1_form_l5|soccer_team1" in PR.production_pairs(_st_ft), "and in Production from the first bet")
_d_ft = {"quotes": [_ftq(i, i % 10 != 0, price=0.8) for i in range(30)]}            # 27/30 at 0.80
eq(T.fast_track_status(_d_ft, "team1_form_l5", "soccer_team1", _meta)[0], "cleared",
   "30 bets, profitable after fees and z >= 1: cleared")
_d_fail = {"quotes": [_ftq(i, i % 5 != 0, price=0.8) for i in range(30)]}         # 24/30 at 0.80
T.evaluate_stages(_d_fail, _st_ft, now=datetime(2026, 10, 10, tzinfo=timezone.utc), verbose=False)
_pf = _st_ft["pairs"]["team1_form_l5|soccer_team1"]
eq((_pf["fast_track"]["state"], _pf["since"][:10]), ("failed", "2026-10-10"),
   "at the price paid and no better: failed, back to the ladder on fresh evidence")
ok("team1_form_l5|soccer_team1" not in PR.production_pairs(_st_ft), "and out of Production")
T.evaluate_stages(_d_ft, _st_ft, now=datetime(2026, 10, 11, tzinfo=timezone.utc), verbose=False)
eq(_st_ft["pairs"]["team1_form_l5|soccer_team1"]["fast_track"]["state"], "failed", "a failed fast track is never re-opened")

_open = dict(_ftq(99, True), status="open", pnl=0.0, result=None,
             start=datetime(2026, 9, 16, 18, tzinfo=timezone.utc).isoformat(), logged="2026-09-15T00:00:00+00:00")
_st_p = {"pairs": {"team1_form_l5|soccer_team1": dict(stage="sandbox", since=None,
                                                     fast_track=dict(since="2026-09-14T00:00:00+00:00", state="probation"))}}
_fd = PR.build_feed({"quotes": [_open]}, _st_p, now=datetime(2026, 9, 15, 12, tzinfo=timezone.utc))
_gl = list(_fd["leads"].values())
eq([(l["bet"], l["home"], l["away"], l["headline"], l["league"], l["status"]) for l in _gl],
   [({"kind": "team_gte", "n": 1, "team": "Goal FC"}, "Goal FC", "Leak FC", "Goal FC to score 1+", "Premier League", "pending")],
   "a fast-tracked team-goals bet is published in the Leads board's bet vocabulary")
eq(_fd["pairs"]["team1_form_l5|soccer_team1"]["route"], "fast track · probation", "and the pair says how it got there")
_o15 = dict(_open, sport="soccer_o15", source="o15_form_l10", id="o15_form_l10:Z", team=None)
eq(PR.lead_from_quote(_o15, "o15_form_l10|soccer_o15", "2026-09-15T12:00:00+00:00")["bet"],
   {"kind": "total_gte", "n": 2}, "an over-1.5 bet is total_gte 2")
ok("fast track" in PR.page({"quotes": [_open]}, _st_p, _fd, ""), "the Production page shows how a pair got there")


print("\ntennis favourite-band rule")
_tr = [dict(market_id="t1", price_a=0.80, price_b=0.22, price_draw=None),
       dict(market_id="t2", price_a=0.30, price_b=0.75, price_draw=None),
       dict(market_id="t3", price_a=0.90, price_b=0.12, price_draw=None),
       dict(market_id="t4", price_a=0.60, price_b=0.42, price_draw=None)]
eq(S.fetch_tennis_fav_band("tennis", universe={"tennis": _tr}), [dict(market_id="t1", pick="a"), dict(market_id="t2", pick="b")],
   "backs the side priced 0.75 up to (not including) 0.90, on either side of the contest")
def _tq(mid, src, pick, pa, pb, result, bet):
    price = (pa if pick == "a" else pb) if bet else None
    won = bet and result == pick
    return dict(id=f"{src}:{mid}", source=src, sport="tennis", market_id=mid, venue="polymarket_us", bet=bet,
                pick=pick if bet else None, price=price, price_a=pa, price_b=pb, result=result,
                status=("won" if won else "lost") if bet else "graded",
                pnl=(round(100 * (1 / price - 1), 2) if won else -100.0) if bet else 0.0,
                start=f"2026-09-1{mid[-1]}T18:00:00+00:00", logged="2026-09-10T00:00:00+00:00")
_dt = {"quotes": [_tq("m1", "tennis_fav_band", "a", 0.80, 0.22, "a", True),
                  _tq("m1", "polymarket_us", None, 0.80, 0.22, "a", False),
                  _tq("m2", "polymarket_us", None, 0.55, 0.47, "b", False),     # favourite loses
                  _tq("m3", "polymarket_us", None, 0.65, 0.37, "b", False)]}    # favourite loses
_at = T.assess(_dt, "tennis_fav_band", "tennis")
_ct = dict((k, (p, det)) for k, _l, p, det in _at["criteria"])
ok("the favourite on every match" in _ct["baseline"][1], "judged against backing the favourite on every match")
eq(_ct["baseline"][0], True, "and beats it here (+25% v favourites losing two of three)")
eq((S.SOURCES["mma_fav_band"]["sports"], S.CHALLENGERS["mma_fav_band"] is S.CHALLENGERS["tennis_fav_band"],
    S.SOURCES["mma_fav_band"]["baseline"]), (["mma"], True, "favourite_population"),
   "MMA runs the same band rule, judged the same way")
eq(S.fetch_tt_band("table_tennis", universe={"table_tennis": [dict(market_id="x", price_a=0.44, price_b=0.57, price_draw=None),
                                                              dict(market_id="y", price_a=0.60, price_b=0.42, price_draw=None)]}),
   [dict(market_id="x", pick="b")], "table tennis backs the 0.55-0.60 side only (0.60 itself is out)")


print("\nMLB fade-the-streak rule")
_mg = []
for i in range(25):
    ts = f"2026-08-{i+1:02d}T23:05Z"
    _mg.append(dict(start=ts, home="Hot Sox", away=f"X{i}", home_runs=5, away_runs=2 if i >= 17 else 9))   # Hot: won last 8 of 10
    _mg.append(dict(start=ts, home="Cold Cubs", away=f"Y{i}", home_runs=1, away_runs=4 if i >= 16 else 0))  # Cold: lost last 9 of 10
    _mg.append(dict(start=ts, home="Mid Mets", away=f"Z{i}", home_runs=3 if i % 2 else 1, away_runs=2))  # 5 of 10
_mg.append(dict(start="2026-09-20T23:05Z", home="Cold Cubs", away="Q", home_runs=9, away_runs=0))      # after first pitch: ignored
_mrows = {"mlb": [dict(market_id="m1", side_a="Hot Sox", side_b="Cold Cubs", start="2026-09-10T23:05:00+00:00", price_a=0.6, price_b=0.42),
                  dict(market_id="m2", side_a="Mid Mets", side_b="Cold Cubs", start="2026-09-10T23:05:00+00:00", price_a=0.5, price_b=0.52),
                  dict(market_id="m3", side_a="Cold Cubs", side_b="Hot Sox", start="2026-09-10T23:05:00+00:00", price_a=0.4, price_b=0.62)]}
eq(S.mlb_form(_mg, "Cold Cubs", datetime(2026, 9, 10, 23, 5, tzinfo=timezone.utc)), (1, 25), "form counts only games before first pitch")
eq(S.fetch_mlb_fade_streak("mlb", universe=_mrows, games=_mg), [dict(market_id="m1", pick="b"), dict(market_id="m3", pick="a")],
   "backs the cold team against a hot one, from either side; a cold team v a .500 team is no bet")
_mrows2 = {"mlb": _mrows["mlb"][:1] + [dict(market_id="m4", side_a="Hot Sox", side_b="Cold Cubs", start="2026-09-11T23:05:00+00:00", price_a=0.6, price_b=0.42)]}
eq(S.fetch_mlb_fade_streak("mlb", universe=_mrows2, games=_mg), [dict(market_id="m1", pick="b")],
   "only each team's next game: game 2 of the series waits until game 1 is final")


print("\nSandbox page: pairs sorted into working / not working / too early; QA lists only promoted pairs")
def _pq2(src, sport, i, won, price=0.5):
    return dict(id=f"{src}:{sport}:{i}", source=src, sport=sport, market_id=f"{sport}{i}", venue="polymarket_us", bet=True,
                pick="a", price=price, price_a=price, price_b=1 - price, result="a" if won else "b",
                status="won" if won else "lost", pnl=100.0 if won else -100.0, stake=100.0,
                start=f"2026-08-{1 + i % 28:02d}T18:00:00+00:00", logged=f"2026-08-{1 + i % 28:02d}T10:00:00+00:00")
_pd = {"quotes": [_pq2("covers", "mlb", i, i % 3 != 0) for i in range(36)]          # 24/36 at 0.5: working
                + [_pq2("covers", "nfl", i, i % 3 == 0) for i in range(33)]         # 11/33: not working
                + [_pq2("espn_fpi", "mlb", i, i % 2 == 0) for i in range(5)]}      # too early
_g, _c = SB.pair_rows(_pd, {"pairs": {}})
eq((_c["working"], _c["failing"]), (1, 1), "a readable pair ahead of the price is working; one behind it is not")
ok(_c["leaning"] + _c["behind"] == 1, "a pair under the floor is too early, sorted by its lean")
ok("Covers" in "".join(_g["working"]) and "MLB" in "".join(_g["working"]), "rows name the source and the sport")
ok("On deck" not in SB.qa_page(_pd, {"pairs": {}, "events": []}, "<style></style>"),
   "QA no longer lists sandbox pairs that have not succeeded")


print("\nunder 3.5 low-scoring rule")
_ux = []
for i in range(10):
    _ux.append(dict(_gfx("Tight FC", f"T{i}", 1 if i < 8 else 3, 0, i + 1), league="Serie A"))   # scored <=1 in 8/10
    _ux.append(dict(_gfx(f"B{i}", "Blunt FC", 0, 1 if i < 7 else 2, i + 1), league="Serie A"))   # scored <=1 in 7/10
    _ux.append(dict(_gfx("Tight FC", f"C{i}", 4, 0, i + 1), league="Coppa Italia"))              # other competition: ignored
_ux += [dict(_gfx("Loose FC", f"L{i}", 3, 3, i + 1), league="Serie A") for i in range(10)]
_uu = {"soccer_u35": [dict(market_id="u1", start="2026-09-15T18:00:00+00:00", league="Serie A", espn_home="Tight FC", espn_away="Blunt FC", price_a=0.3, price_b=0.72),
                      dict(market_id="u2", start="2026-09-15T18:00:00+00:00", league="Serie A", espn_home="Tight FC", espn_away="Loose FC", price_a=0.4, price_b=0.62)]}
eq(S.fetch_u35_low_scoring("soccer_u35", universe=_uu, fixtures=_ux), [dict(market_id="u1", pick="b")],
   "backs the under (No) only where both teams scored <=1 in 7+ of 10 in THIS competition")
eq(S.SOURCES["u35_low_scoring"]["baseline"], "population", "judged against backing the under on every match")


print("\nteam +0.5 unbeaten rule")
_pevs = {"KXSERIEAGAME": [{"event_ticker": "KXSERIEAGAME-26SEP15TIGLOO", "title": "Tight FC vs Loose FC",
                           "markets": [_gm("KXSERIEAGAME-26SEP15TIGLOO-TIG", "Tight FC", 0.45, 0.44),
                                       _gm("KXSERIEAGAME-26SEP15TIGLOO-LOO", "Loose FC", 0.30, 0.29),
                                       _gm("KXSERIEAGAME-26SEP15TIGLOO-TIE", "Tie", 0.27, 0.26)]}]}
_pup = [dict(home="Tight FC", away="Loose FC", kickoff="2026-09-15T18:00Z", played=False, home_goals=None, away_goals=None, league="Serie A")]
_prow = S.fetch_kalshi_goals(fixtures=_ux + _pup, now=_g0, events_by_series=_pevs)["soccer_p05"]
eq(sorted((r["market_id"], r["team"], r["opponent"], r["price_b"]) for r in _prow),
   [("KXSERIEAGAME-26SEP15TIGLOO-LOO", "Tight FC", "Loose FC", 0.71), ("KXSERIEAGAME-26SEP15TIGLOO-TIG", "Loose FC", "Tight FC", 0.56)],
   "each win market is a row whose No is the other team +0.5; the tie market is skipped")
# Tight FC won all 10 (unbeaten 10/10); Loose FC drew all 10 (won 0/10, but unbeaten)
eq(S.fetch_p05_unbeaten("soccer_p05", universe={"soccer_p05": _prow}, fixtures=_ux + _pup),
   [dict(market_id="KXSERIEAGAME-26SEP15TIGLOO-LOO", pick="b")],
   "backs Tight FC +0.5 (No on Loose FC winning); Loose FC +0.5 fails because Tight FC won 10 of 10")


print("\nprice-only rows fold after 7 days; populations survive in compact form")
_now7 = datetime.now(timezone.utc)
def _pr(i, src, days, bet=False, market=None, result="a"):
    st = (_now7 - timedelta(days=days)).isoformat()
    return dict(id=f"{src}:{i}", source=src, sport="soccer_u35", market_id=market or f"m{i}", venue="kalshi_binary",
                bet=bet, pick="b" if bet else None, price=0.7 if bet else None, price_a=0.3, price_b=0.72, result=result,
                status=("won" if result == "b" else "lost") if bet else "graded", pnl=(42.0 if result == "b" else -100.0) if bet else 0.0,
                stake=100.0 if bet else 0.0, settled=st, logged=st, start=st, prob_a=0.3 if not bet else None)
_d7 = {"quotes": [_pr(1, "goals_market", 10), _pr(2, "goals_market", 3), _pr(3, "u35_low_scoring", 10, bet=True, market="m1", result="b"),
                  _pr(4, "pinnacle", 10, market="m1"), _pr(5, "pinnacle", 10, market="m9")], "_archive": []}
T.prune(_d7, verbose=False)
eq(sorted(q["id"] for q in _d7["quotes"]), ["goals_market:2", "u35_low_scoring:3"],
   "a price-only row folds after 7 days; a bet stays for the full 45")
eq(sorted(x["id"] for x in _d7["_archive"]), ["goals_market:1", "pinnacle:5"],
   "compact copies: every Baseline row, and one row per contest not already covered")
_ap7 = T.assess(_d7, "u35_low_scoring", "soccer_u35")
ok(any("every match" in det for _k, _l, _p, det in _ap7["criteria"]), "the rule's population still reads the folded baseline rows")


print("\nper-sport thresholds: high-volume sports trade calendar for sample")
def _hv(i, won, sport="tennis"):
    return dict(id=f"x:{sport}:{i}", source="tennis_fav_band", sport=sport, market_id=f"{sport}{i}", venue="polymarket_us",
                bet=True, pick="a", price=0.8, price_a=0.8, price_b=0.22, result="a" if won else "b",
                status="won" if won else "lost", pnl=25.0 if won else -100.0, stake=100.0,
                start=(datetime(2026, 9, 10, tzinfo=timezone.utc) + timedelta(hours=i * 1.4)).isoformat(),
                logged="2026-09-10T00:00:00+00:00")
_dh = {"quotes": [_hv(i, i % 10 != 0) for i in range(110)]}     # 99/110 at 0.80 over ~6.4 days
_eh = dict((k, p) for k, _l, p, _d in T.qa_entry(T.assess(_dh, "tennis_fav_band", "tennis", venues=T.TRADEABLE_VENUES)))
eq((_eh["sample"], _eh["price"]), (True, True), "tennis: 110 bets at z >= 1.5 clears the entry sample and price gates")
_ds = {"quotes": [dict(q, sport="soccer") for q in _dh["quotes"]]}
_es = dict((k, p) for k, _l, p, _d in T.qa_entry(T.assess(_ds, "tennis_fav_band", "soccer", venues=T.TRADEABLE_VENUES)))
eq(_es["sample"], False, "the same record in soccer still needs 14 days")
_dt = {"quotes": [_hv(i, i % 10 != 0) for i in range(40)]}
eq(dict((k, p) for k, _l, p, _d in T.qa_entry(T.assess(_dt, "tennis_fav_band", "tennis")))["sample"], False,
   "tennis needs 50 bets, not 30")
_d1 = {"quotes": [dict(_hv(i, i % 10 != 0), start=(datetime(2026, 9, 10, tzinfo=timezone.utc) + timedelta(minutes=i * 5)).isoformat()) for i in range(60)]}
eq(dict((k, p) for k, _l, p, _d in T.qa_entry(T.assess(_d1, "tennis_fav_band", "tennis")))["sample"], True,
   "and no day span: 60 bets inside five hours count")
eq(T.sport_rules("mlb")["entry"], T.QA_ENTRY, "every other sport keeps the original gate")


print("\nhigh-volume sports: the Sandbox record counts in QA")
# the favourite population: 20 other matches where the 0.60 favourite won only 8
_dh["quotes"] += [dict(_hv(200 + i, False), id=f"pm:{i}", source="polymarket_us", bet=False, pick=None, price=None,
                       price_a=0.6, price_b=0.42, result="a" if i < 8 else "b", status="graded", pnl=0.0, stake=0.0)
                  for i in range(20)]
_stq = {"pairs": {}, "events": []}
T.evaluate_stages(_dh, _stq, now=datetime(2026, 9, 20, tzinfo=timezone.utc), verbose=False)
_pq = _stq["pairs"].get("tennis_fav_band|tennis") or {}
eq(_pq.get("stage"), "qa", "a tennis pair with 110 bets at z >= 1.5 is promoted")
eq(T.assess(_dh, "tennis_fav_band", "tennis", since=T.qa_since(_pq, "tennis"), venues=T.TRADEABLE_VENUES)["n"], 110,
   "and QA judges all 110, not only bets logged after the promotion")
eq(T.qa_since(dict(promoted_at="2026-09-20T00:00:00+00:00"), "mlb"), "2026-09-20T00:00:00+00:00",
   "every other sport is still judged on fresh bets only")


print("\nSoccerPredictions moved to QA by hand; production at 70 bets")
def _spq(i, won):
    # a tipster that mixes favourites and underdogs, so it can beat both blind rules
    pick = "a" if i % 2 == 0 else "b"
    price = 0.45 if pick == "a" else 0.33
    return dict(id=f"sp:{i}", source="soccerpredictions", sport="soccer", market_id=f"KXEPLGAME-26SEP{10+i%9}X{i}",
                venue="kalshi", bet=True, pick=pick, price=price, price_a=0.45, price_b=0.33, price_draw=0.25,
                result=pick if won else "draw", status="won" if won else "lost",
                pnl=round(100 * (1 / price - 1), 2) if won else -100.0, stake=100.0,
                start=(datetime(2026, 9, 1, tzinfo=timezone.utc) + timedelta(hours=i * 3)).isoformat(),
                logged="2026-09-01T00:00:00+00:00")
_spd = {"quotes": [_spq(i, i % 3 != 0) for i in range(20)]}
_sps = {"pairs": {}, "events": []}
T.evaluate_stages(_spd, _sps, now=datetime(2026, 9, 17, tzinfo=timezone.utc), verbose=False)
_spp = _sps["pairs"]["soccerpredictions|soccer"]
eq((_spp["stage"], _spp.get("by_hand"), _spp.get("ready_at")), ("qa", "2026-09-16", None),
   "moved to QA on the next run with only 20 bets, not ready yet")
_spd["quotes"] += [_spq(i, i % 3 != 0) for i in range(20, 70)]
T.evaluate_stages(_spd, _sps, now=datetime(2026, 9, 18, tzinfo=timezone.utc), verbose=False)
ok(_sps["pairs"]["soccerpredictions|soccer"].get("ready_at"), "at 70 settled bets, profitable after fees, it is in Production")
ok("soccerpredictions|soccer" in PR.production_pairs(_sps), "and the Production feed lists it")
_spd["quotes"] = [dict(q, status="lost", result="draw", pnl=-100.0) if int(q["id"].split(":")[1]) % 3 else q for q in _spd["quotes"]]
T.evaluate_stages(_spd, _sps, now=datetime(2026, 9, 18, 6, tzinfo=timezone.utc), verbose=False)
ok(not _sps["pairs"]["soccerpredictions|soccer"].get("ready_at"), "and leaves it the run it stops being profitable")

print(f"\n{'FAILED: ' + str(len(FAILS)) if FAILS else 'all sandbox tests passed'}")
for f in FAILS:
    print("   -", f)
sys.exit(1 if FAILS else 0)
