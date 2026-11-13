#!/usr/bin/env python3
"""Offline checks for the BTTS row added to africa_goals on Nov 13 2026 (after the window opened): the count rule (kickoffs after 18:30 UTC
Nov 13 only), the entry at the same hourly quote, earlier matches shown and flagged but never counted, the three pre-registered rows and
the pooled row untouched, first-half BTTS not tracked, and the Soccer page row."""
import datetime as dt
import sys

import africa_goals as AG
import sandbox_audit
import soccer_lanes as L

FAILS = []
UTC = dt.timezone.utc
EARLY = dt.datetime(2026, 11, 13, 16, 0, tzinfo=UTC)         # kicks off before 18:30 UTC Nov 13: shown, not counted
LATE = dt.datetime(2026, 11, 14, 16, 0, tzinfo=UTC)          # counted


def check(label, got, want):
    ok = got == want
    print(f"  {'ok  ' if ok else 'FAIL'} {label}" + ("" if ok else f" (got {got!r}, want {want!r})"))
    if not ok:
        FAILS.append(label)


def event(home, away, code, ko, day):
    tag = f"{AG.TOTAL}-{day}{code}"
    exp = (ko + dt.timedelta(hours=4)).strftime("%Y-%m-%dT%H:%M:%SZ")
    ms = [dict(ticker=f"{tag}-{i + 3}", title=f"Will over {ln} goals be scored?", expected_expiration_time=exp, status="active")
          for i, ln in enumerate((0.5, 1.5, 2.5, 3.5))]
    return dict(event_ticker=tag, title=f"{home} vs {away}: Total Goals", markets=ms)


def candle(end, bid, ask):
    return dict(end_period_ts=int(end.timestamp()), yes_bid=dict(close_dollars=str(bid)), yes_ask=dict(close_dollars=str(ask)))


class Net:
    def __init__(self, events, btts, quotes, boom=False):
        self.events, self.btts, self.quotes, self.boom, self.calls = events, btts, quotes, boom, []

    def __call__(self, path):
        self.calls.append(path)
        if path.startswith("events?"):
            return dict(events=self.events if "status=open" in path else [])
        if path.startswith(f"markets?event_ticker={AG.BTTS_SERIES}-"):
            if self.boom:
                raise OSError("kalshi down")
            return dict(markets=self.btts.get(path.split(f"{AG.BTTS_SERIES}-")[1].split("&")[0], []))
        if path.startswith("markets?event_ticker="):
            return dict(markets=[])
        if "/candlesticks" in path:
            tk = path.split("/markets/")[1].split("/candlesticks")[0]
            return dict(candlesticks=[candle(e, b, a) for e, b, a in self.quotes.get(tk, [])])
        return {}


def fx(home, away, ko):
    return dict(home=home, away=away, kickoff=ko.isoformat(), league=AG.LEAGUE)


print("the count rule")
check("kickoff exactly at 18:30 UTC Nov 13 does not count; a minute later does",
      (AG.counts("2026-11-13T18:30:00+00:00"), AG.counts("2026-11-13T18:31:00+00:00")), (False, True))
check("an earlier kickoff of the window does not count, a later day does", (AG.counts(EARLY.isoformat()), AG.counts(LATE.isoformat())), (False, True))
check("the three pre-registered rows are unchanged", [(k, v["series"], v["side"], v["line"]) for k, v in AG.ROWS.items()],
      [("U35", "KXAFCONTOTAL", "no", 3.5), ("O15", "KXAFCONTOTAL", "yes", 1.5), ("T1", "KXAFCONTEAMTOTAL", "yes", 0.5)])
check("the BTTS row: KXAFCONBTTS, YES, the same 3h hourly entry, label says it was added after the window opened",
      (AG.BTTS["series"], AG.BTTS["side"], AG.ENTRY_H, AG.BTTS_LABEL), ("KXAFCONBTTS", "yes", 3.0, "added Nov 13 2026, after the window opened"))
check("first-half BTTS is not tracked", "1HBTTS" in AG.BTTS_SERIES or any("1HBTTS" in v.get("series", "") for v in AG.ALL_ROWS.values()), False)

print("\nentries")
e1, e2 = event("Mali", "Rwanda", "MLIRWA", EARLY, "26NOV13"), event("Uganda", "Botswana", "UGABOT", LATE, "26NOV14")
b1, b2 = f"{AG.BTTS_SERIES}-26NOV13MLIRWA-BTTS", f"{AG.BTTS_SERIES}-26NOV14UGABOT-BTTS"
btts = {"26NOV13MLIRWA": [dict(ticker=b1, yes_sub_title="Both Teams To Score")], "26NOV14UGABOT": [dict(ticker=b2, yes_sub_title="Both Teams To Score")]}
o15_1 = [m["ticker"] for m in e1["markets"] if m["title"].startswith("Will over 1.5")][0]
quotes = {b1: [(EARLY - dt.timedelta(hours=3), 0.38, 0.40)], b2: [(LATE - dt.timedelta(hours=3), 0.40, 0.42)], o15_1: [(EARLY - dt.timedelta(hours=3), 0.70, 0.72)]}
fixtures = [fx("Mali", "Rwanda", EARLY), fx("Uganda", "Botswana", LATE)]
state = AG.load("/nonexistent")
now = LATE - dt.timedelta(hours=2, minutes=30)
net = Net([e1, e2], btts, quotes)
log = AG.run(state, fixtures, now, net, tape=lambda t, f: [])
by = {p["id"]: p for p in AG.picks_of(state, "BTTS")}
check("a BTTS bet on each match, from the same hourly quote at the ask", sorted((p["match"], p["price"]) for p in by.values()),
      [("Mali v Rwanda", 0.40), ("Uganda v Botswana", 0.42)])
check("the earlier match is flagged not counted and marked backfilled; the later one counts",
      (by[f"BTTS:{b1}"]["counted"], by[f"BTTS:{b1}"]["backfilled"], by[f"BTTS:{b2}"]["counted"], by[f"BTTS:{b2}"]["backfilled"]), (False, True, True, False))
check("the other rows still log: the old match's over 1.5 is bet as before", f"O15:{o15_1}" in log, True)
check("the pooled row (three goal bets) does not include BTTS", {p["rule"] for p in AG.picks_of(state)} <= {"U35", "O15", "T1"}, True)
check("a second run adds nothing", AG.run(state, fixtures, now + dt.timedelta(hours=1), net, tape=lambda t, f: []), [])

print("\nthe record counts only the later matches")
for p in by.values():
    p.update(status="won", profit=140.0)
rec = AG.record(list(by.values()))
check("the earlier match is left out of every figure", (rec["n"], rec["won"], rec["days"], round(rec["price"], 2)), (1, 1, 1, 0.42))
check("counted() keeps ordinary picks and drops flagged ones", len(AG.counted(list(by.values()) + [dict(rule="O15", status="won")])), 2)

print("\na price outside 2c to 98c, and a failed BTTS read")
q2 = dict(quotes, **{b2: [(LATE - dt.timedelta(hours=3), 0.985, 0.99)]})
st2 = AG.load("/nonexistent")
AG.run(st2, fixtures, now, Net([e1, e2], btts, q2), tape=lambda t, f: [])
check("a 99c ask is not bet, with the reason kept", (f"BTTS:{b2}" in st2["skips"], st2["skips"].get(f"BTTS:{b2}", {}).get("why")), (True, "price 0.99 outside 2c to 98c"))
st3 = AG.load("/nonexistent")
AG.run(st3, fixtures, now, Net([e1, e2], btts, quotes, boom=True), tape=lambda t, f: [])
check("a failed BTTS read leaves the three rows logging", (len(AG.picks_of(st3, "BTTS")), f"O15:{o15_1}" in {p["id"] for p in AG.picks_of(st3)}), (0, True))

print("\nthe Soccer page row")
rows = L.africa_rows(state)
r = {x["name"]: x for x in rows}["africa_goals_btts"]
check("a Sandbox observation row, pinned under the combined row, in the Internationals scope",
      (r["prod"], r.get("pin"), r.get("after"), r["meta"]["kind"] if "kind" in r.get("meta", {}) else "Observation"), (False, True, "africa_goals_all", "Observation"))
words = r["own"]["details"] + r["own"]["entries"] + r["own"]["label"] + r["meta"]["note"]
check("the label and fold say it was added after the window opened and what counts",
      all(x in words for x in ("added Nov 13 2026, after the window opened", "after 18:30 UTC on Nov 13 2026", "shown, not counted", "First-half both teams to score")), True)
check("its record is the counted match only", r["a"]["n"], 1)
check("the pooled row still sums the three bet rows only", rows[0]["a"]["n"], sum(x["a"]["n"] for x in rows[1:4]))
check("public copy passes the guard and holds no dollar amount", (bool(sandbox_audit.COPY_RE.search(words)), "$" in words), (False, False))

if FAILS:
    print(f"\nFAILED {len(FAILS)}")
    sys.exit(1)
print("\nall ok")
