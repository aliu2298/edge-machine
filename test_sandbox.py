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
print(f"\n{'FAILED: ' + str(len(FAILS)) if FAILS else 'all sandbox tests passed'}")
for f in FAILS:
    print("   -", f)
sys.exit(1 if FAILS else 0)
