#!/usr/bin/env python3
"""Offline checks for t1m_sell15 (2026-11-08): the phase-5 touch (50+ contracts at or above 1.5x, no print in the minute
after a sweep second), the sell and hold side by side on T1-M's own entries, the fresh record, one read per entry, the
in-sample backfill kept apart, T1-M's ledger never written, and the row under T1, the T1-M fold and the Sandbox index."""
import datetime as dt
import hashlib
import json
import os
import sys

import sandbox_audit
import t1m_sell15 as T
import t1m_sell15_build as TB

FAILS = []
UTC = dt.timezone.utc


def check(label, got, want):
    ok = got == want
    print(f"  {'ok  ' if ok else 'FAIL'} {label}" + ("" if ok else f" (got {got!r}, want {want!r})"))
    if not ok:
        FAILS.append(label)


def iso(t):
    return dt.datetime.fromtimestamp(t, UTC).isoformat().replace("+00:00", "Z")


print("the phase-5 rule")
check("target = round(1.5 x entry); none above 66c", (T.target(0.40), T.target(0.66), T.target(0.67)), (0.60, 0.99, None))
pr = [(100, 0.40, 10.0), (200, 0.70, 30.0), (230, 0.70, 30.0), (300, 0.70, 30.0)]
el, n = T.eligible(pr)
check("a sweep second (5c+ above the last print) drops the prints of the next 60 seconds", ([x[0] for x in el], n), ([100, 300], 1))
o = T.outcome(0.41, False, pr)
check("30 eligible contracts at 70c is no touch: held, lost", (o["touched"], o["sell"] == o["hold"], o["hold"]), (False, True, -1.0))
o = T.outcome(0.41, False, pr + [(400, 0.61, 25.0)])
c41 = 0.41 + T.fee(0.41, 0.07)
check("55 eligible at or above the 61c target: touched, sold at 61c after the taker fee on both legs",
      (o["target"], o["touched"], o["sell"], o["sell_maker"] > o["sell"]),
      (0.61, True, round((0.61 - T.fee(0.61, 0.07) - c41) / c41, 4), True))
o = T.outcome(0.70, True, [(10, 0.99, 500.0)])
check("an entry above 66c: no target, hold only", (o["target"], o["touched"], o["sell"]), (None, None, None))

print("\nthe run")
KO = int(dt.datetime(2026, 11, 21, 15, 0, tzinfo=UTC).timestamp())
PICKS = [
    dict(id="T1M:KXEPLTOTAL-26NOV21ARSCHE", ticker="KXEPLTOTAL-26NOV21ARSCHE-4", price=0.40, start=iso(KO),
         logged=iso(KO - 3000), status="lost", match="Arsenal v Chelsea", league="Premier League"),
    dict(id="T1M:KXEPLTOTAL-26NOV21LIVMCI", ticker="KXEPLTOTAL-26NOV21LIVMCI-4", price=0.50, start=iso(KO),
         logged=iso(KO - 3000), status="open", match="Liverpool v Manchester City", league="Premier League"),
    dict(id="T1M:KXSERIEATOTAL-26NOV08INTCOM", ticker="KXSERIEATOTAL-26NOV08INTCOM-4", price=0.41, start="2026-11-08T17:00Z",
         logged="2026-11-08T15:31:15Z", status="lost", match="Internazionale v Como", league="Serie A"),
]
calls = []


def fetch(path, *a, **k):
    calls.append(path)
    if path.startswith("markets/") and "trades" not in path:
        tk = path.split("/", 1)[1]
        settled = "ARSCHE" in tk
        return {"market": dict(ticker=tk, status="finalized" if settled else "active", result="no" if settled else "",
                               close_time=iso(KO + 7200))}
    if "trades?" in path:
        return {"trades": [dict(created_time=iso(KO + 600), yes_price_dollars="0.60", count_fp="60"),
                           dict(created_time=iso(KO - 600), yes_price_dollars="0.95", count_fp="999")], "cursor": ""}
    return {}


h0 = hashlib.md5(open(T.TEAM_LEDGER, "rb").read()).hexdigest() if os.path.exists(T.TEAM_LEDGER) else None
st = T.run(T.empty(), now=dt.datetime(2026, 11, 21, 19, tzinfo=UTC), fetch=fetch, picks=PICKS)
check("one settled entry read; the unsettled one waits; the pre-registration one is skipped",
      ([e["id"] for e in st["entries"]], list(st["skips"])), (["T1M:KXEPLTOTAL-26NOV21ARSCHE"], ["T1M:KXSERIEATOTAL-26NOV08INTCOM"]))
e = st["entries"][0]
check("same entry as T1-M (price 40c); 60 contracts at 60c in play touch the 60c target; a pre-kickoff print never counts",
      (e["entry"], e["target"], e["touched"], e["won"]), (0.40, 0.60, True, False))
n = len(calls)
T.run(st, now=dt.datetime(2026, 11, 21, 20, tzinfo=UTC), fetch=fetch, picks=PICKS)
check("a second run reads only the entry still unsettled", [c for c in calls[n:] if "ARSCHE" in c], [])
h1 = hashlib.md5(open(T.TEAM_LEDGER, "rb").read()).hexdigest() if os.path.exists(T.TEAM_LEDGER) else None
check("T1-M's ledger is never written", h0, h1)

print("\nthe readout")
rows = [dict(id=f"m{i}", ko=i, entry=0.4, target=0.6, touched=i % 4 != 0, won=i % 2 == 0, hold=0.0, sell=0.1, sell_maker=0.12)
        for i in range(8)]
for r in rows:
    r["hold"] = (1.0 - 0.42) / 0.42 if r["won"] else -1.0
    r["sell"] = (0.6 - 0.02 - 0.42) / 0.42 if r["touched"] else r["hold"]
s = T.summary(rows + [dict(rows[0], id="x", target=None, touched=None, sell=None)])
check("side by side on the same entries: n, touches, the entry with no target counted apart",
      (s["n"], s["touched"], s["no_target"], round(s["touch_rate"], 3)), (8, 6, 1, 0.75))
check("difference = mean of sell minus hold, halves by kickoff", (round(s["diff"], 4), s["diff_h"][0] is not None),
      (round(sum(r["sell"] - r["hold"] for r in rows) / 8, 4), True))
check("reads", (T.read_of(3)[:9], T.read_of(12)[:6], T.read_of(31)), ("too early", "review", f"decide; about {T.NEED_N} needed to read a +10% edge at z 2"))

print("\nthe page")
st["insample"] = dict(entries=rows, skips={}, built="x", since=T.BACKFILL_FROM)
r = TB.row(st)
check("one Sandbox row with the frozen id and name, right under T1, observation only",
      (r["name"], r["own"]["label"], r["prod"], r["after"]), ("t1m_sell15", "T1-M · 1.5x sell (readout)", False, "st_t1"))
d = r["own"]["details"]
check("the fold: the side by side, fair 67%, the difference, halves, maker variant, the in-sample backfill and phase 5's note",
      all(x in d for x in ("Hold ROI, after fees (T1-M&#x27;s exit)", "v fair 67%", "Difference, sell minus hold", "Earlier half",
                           "Maker-sell variant", "In-sample backfill", "not counted", "z +0.9", "About 60 matches")), True)
check("the in-sample record is not the headline", r["a"]["n"], 1)
words = d + r["own"]["label"] + r["meta"]["note"] + TB.fold_html(st) + TB.index_row(st)
check("public copy passes the copy guard, no dollar amounts", (bool(sandbox_audit.COPY_RE.search(words)), "$" in words), (False, False))
check("a readout inside T1-M's fold links to the row", 'href="#t1m-sell15"' in TB.fold_html(st), True)
check("the Sandbox index row links to the Soccer page", 'href="./soccer.html#t1m-sell15"' in TB.index_row(st), True)
import soccer_lanes
live, _gone, _q = soccer_lanes.team_rows({"rules": {}})
names = [x["name"] for x in live]
check("on the Soccer page the readout follows T1's siblings", names.index("t1m_sell15") > names.index("st_t1h"), True)
t1m = next(x for x in live if x["name"] == "st_t1m")
check("T1-M's fold carries the readout; T1-M's own record is unchanged by it", ("1.5x sell readout" in t1m["own"]["details"],
      t1m["a"]["n"]), (True, 0))
import chaos_build
check("the Sandbox index lists it", 'data-lane="t1m_sell15"' in "".join(chaos_build._extra_index_rows()), True)

if FAILS:
    print(f"\nFAILED {len(FAILS)}")
    sys.exit(1)
print("\nall ok")
