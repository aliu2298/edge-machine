#!/usr/bin/env python3
"""Offline checks for the African qualifiers goals check (africa_goals.py): the three pre-registered bets, the hourly-quote
entry three hours before the ESPN kickoff, exact name matching (the reverse fixture four days later is never taken), the
backfilled mark, the fill simulator's quoted rule at settlement, the match-day score, and the Soccer page rows."""
import copy
import datetime as dt
import os
import sys

import africa_goals as AG
import fillsim as F
import lane_windows as W
import sandbox_audit
import sandbox_sources as S
import sandbox_track as T
import soccer_lanes as L
import sport_page as SP

FAILS = []
UTC = dt.timezone.utc
KO = dt.datetime(2026, 11, 13, 16, 0, tzinfo=UTC)
ENTRY = KO - dt.timedelta(hours=3)


def check(label, got, want):
    ok = got == want
    print(f"  {'ok  ' if ok else 'FAIL'} {label}" + ("" if ok else f" (got {got!r}, want {want!r})"))
    if not ok:
        FAILS.append(label)


def fx(home, away, ko=KO):
    return dict(home=home, away=away, kickoff=ko.isoformat(), league=AG.LEAGUE)


def event(home, away, code, ko=KO, day="26NOV13"):
    tag = f"{AG.TOTAL}-{day}{code}"
    exp = (ko + dt.timedelta(hours=4)).strftime("%Y-%m-%dT%H:%M:%SZ")
    # The suffix is deliberately not the line: the line is read from the market's own words.
    ms = [dict(ticker=f"{tag}-{i + 3}", title=f"Will over {ln} goals be scored?", expected_expiration_time=exp, status="active")
          for i, ln in enumerate((0.5, 1.5, 2.5, 3.5))]
    return dict(event_ticker=tag, title=f"{home} vs {away}: Total Goals", markets=ms)


def team_ms(home, away, code, day="26NOV13"):
    tag = f"{AG.TEAM}-{day}{code}"
    return [dict(ticker=f"{tag}-{code[:3]}1", yes_sub_title=f"{home} over 0.5 goals"),
            dict(ticker=f"{tag}-{code[3:]}1", yes_sub_title=f"{away} over 0.5 goals"),
            dict(ticker=f"{tag}-{code[:3]}2", yes_sub_title=f"{home} over 1.5 goals")]


def candle(end, bid, ask):
    return dict(end_period_ts=int(end.timestamp()), yes_bid=dict(close_dollars=str(bid)), yes_ask=dict(close_dollars=str(ask)))


class Net:
    """A fake Kalshi: events by status, team markets by suffix, hourly candles and results by ticker."""

    def __init__(self, events, teams, quotes, results=None):
        self.events, self.teams, self.quotes, self.results, self.calls = events, teams, quotes, results or {}, []

    def __call__(self, path):
        self.calls.append(path)
        if path.startswith("events?"):
            return dict(events=self.events if "status=open" in path else [])
        if path.startswith(f"markets?event_ticker={AG.TEAM}-"):
            return dict(markets=self.teams.get(path.split(f"{AG.TEAM}-")[1].split("&")[0], []))
        if "/candlesticks" in path:
            tk = path.split("/markets/")[1].split("/candlesticks")[0]
            return dict(candlesticks=[candle(e, b, a) for e, b, a in self.quotes.get(tk, [])])
        if path.startswith("markets/"):
            return dict(market=self.results.get(path.split("markets/")[1], dict(status="active")))
        return {}


print("the pre-registered bets")
check("three bet types: NO over 3.5, YES over 1.5, YES each side over 0.5",
      [(k, v["series"], v["side"], v["line"]) for k, v in AG.ROWS.items()],
      [("U35", "KXAFCONTOTAL", "no", 3.5), ("O15", "KXAFCONTOTAL", "yes", 1.5), ("T1", "KXAFCONTEAMTOTAL", "yes", 0.5)])
check("entry three hours before kickoff, a fresh record from Nov 12, prices 2c to 98c",
      (AG.ENTRY_H, AG.FROM, AG.PRICE_MIN, AG.PRICE_MAX), (3.0, "2026-11-12", 0.02, 0.98))
doc = open(os.path.join(AG.ROOT, AG.PREREG)).read()
check("the pre-registration keeps its rules and thresholds",
      all(x in doc for x in ("`KXAFCONTOTAL` rung 4 (over 3.5, the NO side)", "`KXAFCONTOTAL` rung 2 (over 1.5, the YES side)",
                             "`KXAFCONTEAMTOTAL` each side's rung 1 (the YES side)", "three hours before kickoff",
                             "by 3 points or more", "a match day is one outcome", "wins 80% or more")), True)
check("... and carries the dated note that the read is now also a paper lane",
      "## Note, Nov 12 2026: now also a paper lane" in doc and "marked as backfilled" in doc, True)

print("\nnames: exact after normalising, a short alias table, never fuzzy")
check("Congo Republic is ESPN's Congo", AG.same_team("Congo Republic", "Congo"), True)
check("Congo DR is not Congo", AG.same_team("Congo DR", "Congo"), False)
check("Guinea is not Guinea-Bissau or Equatorial Guinea",
      (AG.same_team("Guinea", "Guinea-Bissau"), AG.same_team("Guinea", "Equatorial Guinea")), (False, False))
check("accents and case are ignored", AG.same_team("Côte d'Ivoire", "Ivory Coast"), True)
e = event("Congo Republic", "Comoros", "COGCOM")
first, back = fx("Congo", "Comoros"), fx("Comoros", "Congo", KO + dt.timedelta(days=4))
check("the fixture on the day, home and away either way round", AG.find_fixture(e, [back, first]) is first, True)
check("the reverse fixture four days later is never taken", AG.find_fixture(e, [back]), None)
check("two fixtures that both fit: skipped, not guessed", AG.find_fixture(e, [first, dict(first)]), None)
check("a different opponent is no match", AG.find_fixture(e, [fx("Congo", "Gabon")]), None)

print("\nESPN fixtures")
ev = dict(id="1", date="2026-11-13T16:00Z", competitions=[dict(status=dict(type=dict(name="STATUS_SECOND_HALF")), competitors=[
    dict(homeAway="home", team=dict(displayName="Nigeria")), dict(homeAway="away", team=dict(displayName="Tanzania"))])])
check("a match in play keeps its kickoff", AG.fixture_of(ev), fx("Nigeria", "Tanzania"))
gone = copy.deepcopy(ev)
gone["competitions"][0]["status"]["type"]["name"] = "STATUS_POSTPONED"
check("a postponed match is dropped", AG.fixture_of(gone), None)

print("\nthe hourly quote")
t = ENTRY.timestamp()
cs = [(t - 7 * 3600, 0.50, 0.52), (t - 3600, 0.60, 0.62), (t, 0.64, 0.66), (t + 3600, 0.90, 0.92)]
check("the last candle ending at or before the entry time", AG.quote_at(cs, t), (0.64, 0.66, t))
check("a later candle is never read", AG.quote_at(cs[:2] + cs[3:], t), (0.60, 0.62, t - 3600))
check("a quote over six hours old is no quote", AG.quote_at(cs[:1] + cs[3:], t), None)
check("a one-sided or crossed quote is no quote", AG.quote_at([(t, None, 0.66), (t, 0.70, 0.66), (t, 0.0, 0.0)], t), None)

print("\nentries")
f1 = fx("Nigeria", "Tanzania")
e1 = event("Nigeria", "Tanzania", "NGRTAN")
tk = {m["title"]: m["ticker"] for m in e1["markets"]}
o15, o35 = tk["Will over 1.5 goals be scored?"], tk["Will over 3.5 goals be scored?"]
teams = {"26NOV13NGRTAN": team_ms("Nigeria", "Tanzania", "NGRTAN")}
t_ngr, t_tan = teams["26NOV13NGRTAN"][0]["ticker"], teams["26NOV13NGRTAN"][1]["ticker"]
quotes = {o15: [(ENTRY, 0.70, 0.72)], o35: [(ENTRY, 0.25, 0.27)], t_ngr: [(ENTRY, 0.985, 0.99)], t_tan: [(ENTRY, 0.40, 0.42)]}
net = Net([e1], teams, quotes)
check("not due before the hour's quote is final (kickoff - 3h + 5 min)",
      (AG.due(f1, ENTRY + dt.timedelta(minutes=4)), AG.due(f1, ENTRY + dt.timedelta(minutes=5))), (False, True))
check("a kickoff before Nov 12 is never due", AG.due(fx("A", "B", dt.datetime(2026, 11, 11, 20, tzinfo=UTC)), KO), False)
check("a match over ten days old is not picked up", AG.due(f1, KO + dt.timedelta(days=11)), False)
state = AG.load("/nonexistent")
now = ENTRY + dt.timedelta(minutes=20)
new = AG.run(state, [f1], now, net, tape=lambda tkr, fetch: [])
check("before the entry hour a run logs nothing", AG.run(AG.load("/nonexistent"), [f1], ENTRY - dt.timedelta(hours=1), net), [])
check("one match: NO over 3.5, YES over 1.5 and the side inside 2c to 98c",
      sorted(new), sorted([f"U35:{o35}", f"O15:{o15}", f"T1:{t_tan}"]))
by = {p["id"]: p for p in AG.picks_of(state)}
check("YES pays the ask; NO pays 1 - the bid", (by[f"O15:{o15}"]["price"], by[f"U35:{o35}"]["price"], by[f"T1:{t_tan}"]["price"]),
      (0.72, 0.75, 0.42))
check("the team row names its side; over 1.5 goals for a side is never bet",
      (by[f"T1:{t_tan}"]["team"], any(p["ticker"].endswith("2") and p["rule"] == "T1" for p in by.values())), ("Tanzania", False))
check("a 99c side is left out, with the reason kept", state["skips"][f"T1:{t_ngr}"]["why"], "price 0.99 outside 2c to 98c")
check("logged before kickoff: not backfilled", {p["backfilled"] for p in by.values()}, {False})
check("a second run adds nothing and does not re-read the skipped side",
      (AG.run(state, [f1], now + dt.timedelta(hours=1), net, tape=lambda tkr, fetch: []), len(AG.picks_of(state))), ([], 3))
late = AG.load("/nonexistent")
AG.run(late, [f1], KO + dt.timedelta(hours=5), net, tape=lambda tkr, fetch: [])
lp = {p["id"]: p for p in AG.picks_of(late)}
check("a run after kickoff logs the SAME price from the same hourly quote, marked backfilled",
      [(lp[k]["price"], lp[k]["quote_end"], lp[k]["backfilled"]) for k in sorted(lp)],
      [(by[k]["price"], by[k]["quote_end"], True) for k in sorted(by)])
old = event("Ghana", "Somalia", "GHASOM", dt.datetime(2026, 9, 25, 16, tzinfo=UTC), "26SEP25")
st3 = AG.load("/nonexistent")
check("September's matches are the research, not the record",
      (AG.run(st3, [fx("Ghana", "Somalia", dt.datetime(2026, 9, 25, 16, tzinfo=UTC))], now, Net([old], {}, {})), st3["runs"][-1]["events"]),
      ([], 0))
st4 = AG.load("/nonexistent")
AG.run(st4, [], now, net)
check("a Kalshi match with no ESPN fixture is named, never bet", (st4["unmatched"], AG.picks_of(st4)), (["Nigeria vs Tanzania: Total Goals"], []))

print("\nsettlement: the fill simulator's quoted rule, the exchange's fee")
row = dict(by[f"O15:{o15}"])
won = AG.grade(row, 1.0, [])
check("no prints: the quoted ask counts (unconfirmed), paid 72c plus the taker fee",
      (won["status"], won["fill"], won["profit"]), ("won", "unconfirmed", round(100 * (1 / (0.72 + F.fee(0.72)) - 1), 2)))
check("a loss is the whole stake", AG.grade(row, 0.0, [])["profit"], -100.0)
ts = AG.D.instant(row["entry_at"]).timestamp()
moved = [(ts + 600, 0.85, 20.0, "yes"), (ts + 1200, 0.86, 15.0, "yes")]
ref = AG.grade(row, 1.0, moved)
check("every print before kickoff over 5c above the ask: refuted, no fill, no profit", (ref["status"], ref["fill"], ref["profit"]),
      ("no_fill", "refuted", None))
check("prints at the ask verify it", AG.grade(row, 1.0, [(ts + 600, 0.72, 25.0, "yes")])["fill"], "verified")
net.results = {o15: dict(status="finalized", result="yes"), o35: dict(status="finalized", result="yes")}
n, errs = AG.settle(state, KO + dt.timedelta(hours=3), net, tape=lambda tkr, fetch: [])
by = {p["id"]: p for p in AG.picks_of(state)}
check("over 1.5 YES won, over 3.5 NO lost, the side still open",
      (n, errs, by[f"O15:{o15}"]["status"], by[f"U35:{o35}"]["status"], by[f"T1:{t_tan}"]["status"]), (2, [], "won", "lost", "open"))

print("\nthe record: a match day is one outcome")


def pk(day, price, status, profit=None):
    return dict(start=f"2026-11-{day}T16:00:00+00:00", price=price, status=status,
                profit=profit if profit is not None else (round(100 * (1 / (price + F.fee(price)) - 1), 2) if status == "won" else -100.0))


one_day = [pk(12, 0.70, "won") for _ in range(8)]
spread = [pk(12 + i, 0.70, "won") for i in range(8)]
a, b = AG.record(one_day), AG.record(spread)
check("eight wins on one match day score lower than eight wins on eight days", (a["days"], b["days"], a["z"] < b["z"]), (1, 8, True))
check("one match day is one outcome: its score cannot pass 1", round(a["z"], 6), 1.0)
check("points = share won minus the price paid", round(a["excess"], 4), 0.30)
mix = AG.record([pk(12, 0.70, "won"), pk(12, 0.70, "lost"), dict(pk(12, 0.70, "won"), status="open"), dict(pk(13, 0.6, "won"), status="no_fill", profit=None)])
check("open and no-fill bets are not in the record", (mix["n"], mix["won"], mix["n_bets"]), (2, 1, 2))
check("an empty record reads as empty", (AG.record([])["n"], AG.record([])["roi_fee"], AG.record([])["z"]), (0, None, 0.0))

print("\nthe Soccer page rows")
rows = L.africa_rows(state)
check("the combined row, then one row per bet type, all Sandbox",
      [(r["name"], r["prod"]) for r in rows],
      [("africa_goals_all", False), ("africa_goals_u35", False), ("africa_goals_o15", False), ("africa_goals_t1", False)])
check("every row is in the Internationals scope", {SP.scope_key(r) for r in rows}, {"intl"})
check("pinned, and the bet types sit under the combined row",
      ([r.get("pin") for r in rows], [r.get("after") for r in rows]), ([True] * 4, [None] + ["africa_goals_all"] * 3))
other = dict(rows[0], name="other", pin=False, after=None, a=dict(rows[0]["a"], n=40, roi_fee=0.1))
order = [r["name"] for r in SP.place_after(sorted(rows + [other], key=SP.sandbox_order), rows + [other])]
check("they lead the Sandbox list above a row with more evidence", order,
      ["africa_goals_all", "africa_goals_u35", "africa_goals_o15", "africa_goals_t1", "other"])
check("the combined row pools the three records", rows[0]["a"]["n"], sum(r["a"]["n"] for r in rows[1:]))
check("an observation lane: not a registered tracker source, no Production stage, no entry window on the server",
      (any(k.startswith("africa_goals") for k in S.SOURCES), any("africa_goals" in k for k in (T.load_stages().get("pairs") or {})),
       any("africa" in k for k in W.STAMP)), (False, False, False))
words = "".join(r["own"]["details"] + r["own"]["entries"] + r["own"]["label"] + r["meta"]["note"] for r in rows)
check("the fold says how it is run and that it is observation only",
      all(x in words for x in ("hourly quote three hours before the ESPN kickoff", "never in Production", "Points: the share of bets won",
                               "backfilled", AG.PREREG)), True)
check("public copy: the rows' words pass the copy guard", bool(sandbox_audit.COPY_RE.search(words)), False)
check("percentages only: no dollar amounts", "$" in words, False)
import soccer_build
check("the fold lists the lane's own entries, with no empty tracker list above them",
      ("No pick yet" in soccer_build.recent({"quotes": []}, rows[1]), "Tanzania" in soccer_build.recent({"quotes": []}, rows[3])), (False, True))
check("the Soccer page's own-ledger rows include the lane", "live += africa_rows()" in open(L.__file__).read(), True)

print("\nthe workflow and the ledger")
yml = open(os.path.join(AG.ROOT, ".github", "workflows", "soccer-p4.yml")).read()
check("the hourly soccer read runs it and saves its ledger",
      ("python3 africa_goals.py" in yml, "data/africa_goals_ledger.json" in yml, "test_africa_goals.py" in yml), (True, True, True))
led = AG.load()
picks = AG.picks_of(led)
check("the ledger on file: every bet logged after its kickoff is marked backfilled, and no other",
      all(p["backfilled"] == (p["logged"] > p["start"]) for p in picks), True)
check("... every bet is on or after Nov 12 and inside 2c to 98c",
      all(p["start"][:10] >= AG.FROM and AG.PRICE_MIN <= p["price"] <= AG.PRICE_MAX for p in picks), True)
check("... and its quote ends at or before kickoff - 3h", all(p["quote_end"] <= p["entry_at"] for p in picks), True)

if FAILS:
    print(f"\nFAILED {len(FAILS)}")
    sys.exit(1)
print("\nall ok")
