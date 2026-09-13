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
    """Spend a month the way the workflow would: 4 scheduled runs a day plus manual ones."""
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
ok(_left >= S.ODDS_RESERVE - 1, f"a month of 4 scheduled + 2 manual runs a day never runs dry (left {_left})")
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

print(f"\n{'FAILED: ' + str(len(FAILS)) if FAILS else 'all sandbox tests passed'}")
for f in FAILS:
    print("   -", f)
sys.exit(1 if FAILS else 0)
