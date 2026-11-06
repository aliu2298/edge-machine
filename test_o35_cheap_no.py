#!/usr/bin/env python3
"""Offline checks for o35_cheap_no_wave (o35_cheap_no.py) and its Soccer page section."""
import datetime as dt
import re
import sys

import chaos_replay as CR
import o35_cheap_no as O
import o35_cheap_no_build as B
import sandbox_audit
import soccer_build

FAILS = []
UTC = dt.timezone.utc


def check(label, got, want):
    ok = got == want
    print(f"  {'ok  ' if ok else 'FAIL'} {label}" + ("" if ok else f" (got {got!r}, want {want!r})"))
    if not ok:
        FAILS.append(label)


def near(label, got, want, tol=1e-6):
    ok = got is not None and abs(got - want) <= tol
    print(f"  {'ok  ' if ok else 'FAIL'} {label}" + ("" if ok else f" (got {got!r}, want {want!r})"))
    if not ok:
        FAILS.append(label)


KICK = int(dt.datetime(2026, 10, 31, 19, 0, tzinfo=UTC).timestamp())
OCC = KICK + 4 * 3600


def pr(mins, no, n=10.0):
    """A print `mins` minutes after kickoff at NO price `no`."""
    return (KICK + mins * 60, no, n)


print("fees, keys, kickoff")
near("maker fee 0.0175 p(1-p)", O.fee(0.10), 0.0175 * 0.1 * 0.9)
check("variant keys and labels", (O.vkey(0.10, 2), O.vkey(0.15, None), O.vlabel("10c_2x"), O.vlabel("20c_hold")),
      ("10c_2x", "15c_hold", "NO bid 10c · sell at 2x", "NO bid 20c · hold to settlement"))
check("v2 keeps only the 10c bid; the ledger still stores 2x/3x/4x/hold", (O.LIMITS, O.V1_LIMITS, len({O.vkey(l, m) for l in O.LIMITS for m in (None,) + O.MULTS})), ((0.10,), (0.10, 0.15, 0.20), 4))
check("headline is the 10c bid sold at 4x, 3x beside it; v2 stamp", (O.HEADLINE, O.HEAD_MULT, O.COMPARE_MULT, O.VERSION, O.SINCE), (0.10, 4, 3, "o35-v4", "2026-11-01"))
check("eleven leagues: the Soccer page's twelve less the Saudi Pro League", (len(O.SR.SERIES), len(O.LEAGUES), "Saudi Pro League" in O.LEAGUES), (12, 11, False))

print("\nthe bid fills on the first print at or under the limit")
base = [pr(-30, 0.85), pr(5, 0.60), pr(40, 0.30), pr(70, 0.12), pr(80, 0.09), pr(90, 0.04), pr(95, 0.25, 60), pr(100, 0.30, 55)]
ev = O.evaluate(base, KICK, "no", O.V1_LIMITS)
check("v3 evaluates the 10c bid and its first-half comparison only", list(O.evaluate(base, KICK, "no")), ["10", "10e"])
check("10c bid: filled by the 9c print, not the 12c print", ev["10"]["fill_at"], KICK + 80 * 60)
check("15c bid fills earlier on the 12c print; 20c on the 12c print too", (ev["15"]["fill_at"], ev["20"]["fill_at"]), (KICK + 70 * 60,) * 2)
check("the fill is at the limit, whatever printed", ev["10"]["limit"], 0.10)
check("a 12c print does not fill a 10c bid", O.evaluate([pr(70, 0.12)], KICK, "no")["10"], None)
check("v4: a print exactly at the limit only touches the bid: no fill", O.evaluate([pr(70, 0.10)], KICK, "no")["10"], None)
check("v4: a print at 9c fills the 10c bid", O.evaluate([pr(70, 0.09)], KICK, "no")["10"]["fill_print"], 0.09)
check("v4: the first print under the limit fills, one at the limit before it does not",
      O.evaluate([pr(65, 0.10), pr(70, 0.09)], KICK, "no")["10"]["fill_at"], KICK + 70 * 60)
cx = [pr(58, 0.04, 5), pr(80, 0.03)]
check("v4: No already under the bid at the bid minute (last print 04c): the match is not entered, nothing fills",
      (O.evaluate(cx, KICK, "no")["10"], O.crossed_at_bid(cx, KICK, 0.10)), (None, 0.04))
check("v4: a 10c print at the bid minute is also a cross (YES bid at 0.90 would meet it)", O.crossed_at_bid([pr(59, 0.10)], KICK, 0.10), 0.10)
check("v4: No above the bid at the bid minute is entered and can fill later",
      (O.crossed_at_bid([pr(58, 0.30)], KICK, 0.10), O.evaluate([pr(58, 0.30), pr(80, 0.08)], KICK, "no")["10"] is not None), (None, True))
check("v4: the last print wins (a 4c print an hour ago, then 25c: not crossed)", O.crossed_at_bid([pr(10, 0.04), pr(58, 0.25)], KICK, 0.10), None)
check("v4: no print at all before the bid minute: not crossed", O.crossed_at_bid([pr(80, 0.04)], KICK, 0.10), None)
check("a print an hour and a minute before kickoff is before the old bid was placed",
      O.evaluate([pr(-61, 0.05)], KICK, "no"), {"10": None, "10e": None})
e30 = O.evaluate([pr(-30, 0.05)], KICK, "no")
check("v3: a print before kickoff + 60 never fills the bid; the old bid's first-half fill is the comparison",
      (e30["10"], e30["10e"]["fill_at"]), (None, KICK - 1800))
e59, e60 = O.evaluate([pr(59, 0.05)], KICK, "no"), O.evaluate([pr(60, 0.05)], KICK, "no")
check("minute 59 is first half (comparison), minute 60 is the second-half bid",
      (e59["10"], e59["10e"] is not None, e60["10"]["fill_at"], e60["10e"]), (None, True, KICK + 3600, None))
chk = O.evaluate([pr(30, 0.05), pr(80, 0.05)], KICK, "no")
check("v4: a first-half fill at 5c leaves No under the bid at the bid minute: the second-half bid is not entered, the comparison keeps the fill",
      (chk["10"], chk["10e"]["fill_at"]), (None, KICK + 30 * 60))
chk = O.evaluate([pr(30, 0.05), pr(50, 0.30), pr(80, 0.05)], KICK, "no")
check("... but if No had recovered above the bid by the bid minute, the bid is entered and fills at the later print",
      (chk["10"]["fill_at"], chk["10e"]["fill_at"]), (KICK + 80 * 60, KICK + 30 * 60))

print("\nthe sells: later prints, 50 contracts at or above the target")
b = ev["10"]
s2, s3, s4 = b["sells"]["2"], b["sells"]["3"], b["sells"]["4"]
check("2x target is 20c; the 25c and 30c prints after the fill carry 115 contracts: sells", (s2["target"], s2["volume"], s2["filled"], s2["thin"]), (0.2, 115.0, True, False))
check("it fills at the first print at or above the target", s2["at"], KICK + 95 * 60)
check("3x target 30c: only the 30c print counts, 55 contracts: sells", (s3["target"], s3["volume"], s3["filled"]), (0.3, 55.0, True))
check("4x target 40c: nothing prints there: held, not thin", (s4["target"], s4["volume"], s4["filled"], s4["thin"]), (0.4, 0.0, False, False))
thin = O.evaluate([pr(80, 0.09), pr(90, 0.25, 49.9)], KICK, "no")["10"]["sells"]["2"]
check("49.9 contracts at the target is thin: it does not sell", (thin["filled"], thin["thin"], thin["volume"]), (False, True, 49.9))
edge = O.evaluate([pr(80, 0.09), pr(90, 0.25, 30), pr(91, 0.22, 20)], KICK, "no")["10"]["sells"]["2"]
check("volume adds across prints at or above the target: exactly 50 sells", (edge["filled"], edge["volume"]), (True, 50.0))
before = O.evaluate([pr(60, 0.25, 500), pr(80, 0.09)], KICK, "no")["10"]["sells"]["2"]
check("a print above the target BEFORE the bid filled does not count", (before["filled"], before["volume"]), (False, 0.0))
check("a 20c bid's 4x target is capped at 98c", O.evaluate([pr(80, 0.19)], KICK, "no", O.V1_LIMITS)["20"]["sells"]["4"]["target"], 0.8)
check("the payout is 1 on a NO result, 0 on YES", (O.evaluate(base, KICK, "no")["10"]["payout"], O.evaluate(base, KICK, "yes")["10"]["payout"]), (1.0, 0.0))

print("\ndead fills: after the over is all but certain")
dead = O.evaluate([pr(80, 0.01, 40)], KICK, "yes")["10"]
live = O.evaluate([pr(80, 0.08, 40)], KICK, "yes")["10"]
check("a fill whose print is NO 2c or less is a dead fill and is kept", (dead is not None, dead["dead"], live["dead"]), (True, True, False))

print("\nthe ledger rows: ROI after maker fees on both legs")
entry = dict(version="o35-v2", event="KXMLSTOTAL-26OCT31AAABBB", league="MLS", night="2026-10-31", kickoff=KICK, form_rule=True, bids={"10": b, "15": ev["15"], "20": ev["20"]})
rows = O.trade_rows([entry])
by = {r["variant"]: r for r in rows}
cost = 0.10 + O.fee(0.10)
near("hold on a NO result: payout 1, cost = limit + maker fee", by["10c_hold"]["roi"], (1 - cost) / cost)
near("2x sell: proceeds target less its maker fee", by["10c_2x"]["roi"], (0.2 - O.fee(0.2) - cost) / cost)
near("4x not filled: held to settlement", by["10c_4x"]["roi"], (1 - cost) / cost)
check("twelve rows for a market where all three bids filled", len(rows), 12)
check("rows carry the night, league, kickoff, flags", (by["10c_2x"]["night"], by["10c_2x"]["league"], by["10c_2x"]["dead"], by["10c_2x"]["form_rule"]), ("2026-10-31", "MLS", False, True))
lose = dict(entry, bids={"10": O.evaluate(base, KICK, "yes")["10"]})
l = {r["variant"]: r for r in O.trade_rows([lose])}
near("held after a YES result loses the whole cost", l["10c_hold"]["roi"], -1.0)
near("a filled 2x sell still wins on a YES result", l["10c_2x"]["roi"], (0.2 - O.fee(0.2) - cost) / cost)
check("an entry with no fill makes no rows", O.trade_rows([dict(entry, bids={"10": None, "15": None, "20": None})]), [])

print("\nreplaying a settled game from its trades")
EV = "KXMLSTOTAL-26OCT31AAABBB"
MK = dict(ticker=EV + "-4", floor_strike=3.5, status="finalized", result="no",
          occurrence_datetime=dt.datetime.fromtimestamp(OCC, UTC).strftime("%Y-%m-%dT%H:%M:%SZ"))
CALLS = []


def trade_row(ts, no, n):
    return dict(created_time=dt.datetime.fromtimestamp(ts, UTC).strftime("%Y-%m-%dT%H:%M:%S.000000Z"), no_price_dollars=f"{no:.4f}",
                yes_price_dollars=f"{1 - no:.4f}", count_fp=f"{n:.2f}")


def fetch(path):
    CALLS.append(path)
    if path.startswith("events?series_ticker=KXMLSTOTAL"):
        return {"events": [dict(event_ticker=EV), dict(event_ticker="KXMLSTOTAL-26OCT31CCCDDD")], "cursor": None}
    if path.startswith("events?"):
        return {"events": [], "cursor": None}
    if path.startswith("markets?limit=200&event_ticker=" + EV):
        return {"markets": [dict(MK, ticker=EV + "-3", floor_strike=2.5), MK], "cursor": None}
    if path.startswith("markets?limit=200&event_ticker=KXMLSTOTAL-26OCT31CCCDDD"):
        return {"markets": [dict(MK, ticker="KXMLSTOTAL-26OCT31CCCDDD-4", status="active", result="")], "cursor": None}
    if path.startswith("markets/trades"):
        return {"trades": [trade_row(KICK + m * 60, no, n) for m, no, n in ((100, 0.30, 55), (80, 0.09, 10), (5, 0.60, 3))], "cursor": None}
    raise AssertionError(path)


NOW = dt.datetime(2026, 11, 1, 6, 0, tzinfo=UTC)
st = O.load("/nonexistent")
check("a fresh record begins on 2026-11-01 as v4", (st["since"], st["entries"], st["version"]), ("2026-11-01", [], "o35-v4"))
st["since"] = "2026-10-31"                         # the replayed game is from the night before
O.run(st, NOW, fetch, forms={EV})
check("the settled game is recorded, the one still active waits", (len(st["entries"]), st["observations"]["waiting"]), (1, 1))
e = st["entries"][0]
check("kickoff is Kalshi's time minus 4 hours; the night is its ET date", (e["kickoff"], e["night"]), (KICK, "2026-10-31"))
check("the over 3.5 market is the -4 rung, tagged as an over 1.5 form-rule match, stamped", (e["id"], e["form_rule"], e["version"]), (EV + "-4", True, O.VERSION))
check("prints came back oldest first, so the 9c print filled and the later 30c print sold",
      (e["bids"]["10"]["fill_at"], e["bids"]["10"]["sells"]["3"]["filled"]), (KICK + 80 * 60, True))
check("trades are read from an hour before kickoff", any(f"min_ts={KICK - 3600}" in c for c in CALLS), True)
n_calls = len(CALLS)
O.run(st, NOW + dt.timedelta(hours=1), fetch, forms={EV})
check("a second run does not read the game's trades again", (len(st["entries"]), any("markets/trades" in c for c in CALLS[n_calls:])), (1, False))
early = O.load("/nonexistent")
early["since"] = "2026-11-02"
O.run(early, NOW, fetch, forms=set())
check("a game before the lane's first night is not recorded", early["entries"], [])
nofill = dict(MK)
check("an event with no over 3.5 market is skipped with a reason", O.over35([dict(MK, ticker=EV + "-3", floor_strike=2.5)]), None)
check("the form-rule tag reads the ledger and ignores other sources",
      O.form_rule_events("/nonexistent"), set())

print("\nthe v1 and v2 records: kept, collapsed, and out of the v3 headline")
v1e = dict(entry, version="o35-v1", event="KXMLSTOTAL-26OCT30XXXYYY", night="2026-10-30", kickoff=KICK - 86400)
v2e = dict(entry, version="o35-v2", event="KXMLSTOTAL-26OCT31EEEFFF")
entry = dict(entry, version="o35-v3")
unstamped = {k: v for k, v in entry.items() if k != "version"}
mix = dict(O.load("/nonexistent"), entries=[v1e, v2e, entry, unstamped])
o1, o2, n3 = O.split3(mix["entries"])
check("split3: o35-v1 and an unstamped entry are v1, stamped v2 and v3 are their own", (len(o1), len(o2), len(n3)), (2, 1, 1))
hm = B.section(mix)
check("v3 headline counts only v3 entries (1 game); v2 and v1 sit in folds with every bid and exit",
      ("1 games" in hm, "Before the Nov trim (v1)" in hm, "Before the second-half rule (v2)" in hm, O.vlabel("10c_hold") in hm, O.vlabel("20c_4x") in hm,
       O.vlabel("10c_2x") + " (headline)" in hm, "2 games" in hm), (True, True, True, True, True, True, True))
check("the second-half note and the first-half comparison are on the page, labelled not evidence",
      ("Research note, not evidence" in hm, 'data-lane="o35_cheap_no_wave_first_half"' in hm, "First-half fills, tracked" in hm), (True, True, True))
v3e = dict(entry, version="o35-v3", event="KXMLSTOTAL-26NOV01JJJKKK")
h3 = B.section(dict(mix, entries=mix["entries"] + [v3e]))
check("a v3 entry sits in its own closed fold with the reason v4 exists; the v4 headline still counts only v4",
      ("Before the exchange rules (v3)" in h3, "post-only crosses" in h3, re.search(r'data-lane="o35_cheap_no_wave_v3"', h3) is not None, "1 games" in h3),
      (True, True, True, True))
check("the v2 fold is closed by default", re.search(r'<details class="section-disclosure" data-lane="o35_cheap_no_wave_v2">', hm) is not None, True)
check("the v1 fold is closed by default", re.search(r'<details class="section-disclosure" data-lane="o35_cheap_no_wave_v1">', hm) is not None, True)
check("the trim date and reason are on the page", "Trimmed 2026-10-31" in hm, True)
import json, os, tempfile
tf = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
json.dump({"since": "2026-10-28", "version": "o35-v1", "entries": [v1e]}, tf)
tf.close()
mg = O.load(tf.name)
os.unlink(tf.name)
check("loading a v1 ledger starts v4 fresh from SINCE and keeps v1_since", (mg["version"], mg["since"], mg["v1_since"], len(mg["entries"])), ("o35-v4", "2026-11-01", "2026-10-28", 1))
tf = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
json.dump({"since": "2026-10-31", "version": "o35-v2", "entries": [v2e]}, tf)
tf.close()
mg2 = O.load(tf.name)
os.unlink(tf.name)
check("loading a v2 ledger keeps its entries and its start as v2_since", (mg2["version"], mg2["since"], mg2["v2_since"], len(mg2["entries"])), ("o35-v4", "2026-11-01", "2026-10-31", 1))
tf = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
json.dump({"since": "2026-11-01", "version": "o35-v3", "seen": {"KXA-1": "x"}, "entries": [dict(v2e, version="o35-v3")]}, tf)
tf.close()
mg3 = O.load(tf.name)
os.unlink(tf.name)
check("loading a v3 ledger keeps its entries, starts v4 on the same day and reads every event again (Nov 1 is re-scored)",
      (mg3["version"], mg3["since"], mg3["v3_since"], len(mg3["entries"]), mg3["seen"], mg3["seen_v3"]), ("o35-v4", "2026-11-01", "2026-11-01", 1, {}, {"KXA-1": "x"}))

print("\nstats: z needs 3 nights, halves, clustering")
mk = lambda night, roi, k: dict(variant="10c_2x", night=night, roi=roi, cost=0.1, profit=roi * 0.1, won=roi > 0, reason="target",
                                kickoff=k, league="MLS", dead=False, thin=False, form_rule=False)
two = CR.stats([mk("n1", .5, 1), mk("n1", -.5, 2), mk("n2", .5, 3), mk("n2", -1, 4)])
check("two nights: no z", two["z"], None)
three = CR.stats([mk("n1", .5, 1), mk("n2", -.5, 2), mk("n3", 1.5, 3), mk("n4", -1, 4)])
check("four nights give a z", three["z"] is not None, True)
old, new = B.halves([mk("n1", 1, 1), mk("n1", 1, 2), mk("n2", -1, 3), mk("n2", -1, 4)])
check("older half v newer half, by kickoff", (round(old, 2), round(new, 2)), (1.0, -1.0))
check("under four rows: no halves", B.halves([mk("n1", 1, 1)]), (None, None))
check("review at 10, decide at 30", (B.read_of(5, None), B.read_of(12, 0.1), B.read_of(31, 0.1), B.read_of(31, -0.1)),
      ("too early (5 of 10)", "review (12 of 30 to decide)", "decide", "decide"))

print("\nthe Soccer page section")
empty = B.section(O.load("/nonexistent"))
check("empty record says so and keeps the lane card", ('id="cheap-side"' in empty, "0 entries: no game has settled since the v4 record began" in empty, O.LANE in empty), (True, True, True))
html = B.section(st)
check("the lane's name, the 4x headline and the 3x comparison are shown; 2x, hold, 15c and 20c are not",
      (O.LABEL in html, O.vlabel("10c_4x") + " (headline)" in html, O.vlabel("10c_3x") in html, O.vlabel("10c_2x") in html, "hold to settlement" in html,
       O.vlabel("15c_4x") in html or O.vlabel("20c_4x") in html), (True, True, True, False, False, False))
check("dead and thin counts, halves, league and form-rule rows",
      ("Dead fills" in html, "Thin sells" in html, "Older half" in html, "Over 1.5 form-rule matches" in html, "<td><b>MLS</b></td>" in html), (True,) * 5)
check("the fill list shows the contracts at 3x and 4x", ("Sell at 4x · contracts" in html and "Sell at 3x · contracts" in html and "Sell at 2x" not in html and "sold" in html), True)
check("header-row tables for the phone labels (no thead)", "<thead>" not in html, True)
check("no private-system words in the page copy", sandbox_audit.COPY_RE.search(html), None)
page = soccer_build.build()
# 2026-11-05 (Olu): one row of the Soccer page's Production rules, its words in the row's fold (soccer_lanes).
k = page.find('id="cheap-side"')
row = page[k:k + 400]
check("the lane is a Production row of the Soccer page, linked as #cheap-side",
      (k > 0, 'data-source="o35_cheap_no_wave"' in row, 'data-stage="production"' in row), (True, True, True))
check("its fold carries the exits, the league split and the versions", all(x in B.panel(st) for x in ("<b>Exits</b>", "<b>By league</b>", "<b>Fills</b>")), True)
check("its tables are labelled for the phone", 'data-l="Filled"' in B.place("<main><section id=\"x\"></section>", st), True)

print(f"\n{'ALL PASS' if not FAILS else str(len(FAILS)) + ' FAILED'}")
sys.exit(1 if FAILS else 0)
