#!/usr/bin/env python3
"""The S&P 500 opening sweep live trial (2026-11-17, Olu): the decision-snapshot publisher refuses anything but public fields, and the 10c row
shows the live record beside the paper row, same windows, percentages only. Offline."""
import json
import os
import tempfile

import sandbox_audit
import sp_sweep_publish as P
import swing15_build as WB
import sw15c2 as C2

FAILS = []


def check(label, got, want):
    ok = got == want
    print(f"  {'ok  ' if ok else 'FAIL'} {label}" + ("" if ok else f" (got {got!r}, want {want!r})"))
    if not ok:
        FAILS.append(label)


TK = "KXINX15M-26NOV181000-00"
GOOD = dict(lane="sp_sweep_10c", bot_version="spsweep-live-v1", ticker=TK, day="2026-11-18", open="2026-11-18T14:45:00+00:00", decided_at="2026-11-18T14:50:00+00:00",
            outcome="entered", rule_ok=True, rest_s=1.4, fill_side="yes", fill_s=7.4, fill_price=0.08, qty=10.0, sold=10.0, sold_price=0.3, exit="bid", result="no",
            limit=0.1, target=0.3)

print("the publisher")
check("a good row passes", P.sanitise(dict(updated_at="x", decisions={TK: GOOD}))["decisions"][TK]["fill_s"], 7.4)
for label, bad in (("a field outside the whitelist (a balance)", dict(GOOD, balance=25.0)), ("an order id", dict(GOOD, why="0b1c2d3e-0000-4000-8000-123456789abc")),
                   ("a dollar sign", dict(GOOD, why="lost $1")), ("a price over 1", dict(GOOD, fill_price=8.0)), ("an unknown outcome", dict(GOOD, outcome="bought")),
                   ("another market", dict(GOOD, ticker="KXBTC15M-26NOV181000-00")), ("another lane", dict(GOOD, lane="x"))):
    try:
        P.sanitise(dict(decisions={TK: bad}))
        got = "published"
    except P.Refused:
        got = "refused"
    check(f"refused: {label}", got, "refused")
check("the VPS entry runs it and adds only its file", all(x in open("scripts/vps_nba_wm_decisions.sh").read() for x in ("sp_sweep_publish.py", "git add data/sp_sweep_decisions.json")), True)

print("\nthe row")
led = C2.load()
check("no decisions yet: says so, no dollar amount", ("No live window yet" in WB.live_trial_html(C2, led, "/nonexistent.json"), "$" in WB.live_trial_html(C2, led, "/nonexistent.json")), (True, False))
t1, t2, t3 = sorted(led["windows"])[:3]
dec = {"decisions": {
    t1: dict(GOOD, ticker=t1, result="yes", exit=None, sold=10.0, sold_price=0.30, fill_price=0.09),                 # sold at 30c: +233%
    t2: dict(lane="sp_sweep_10c", ticker=t2, outcome="no_fill", rest_s=1.1, result="no"),
    t3: dict(GOOD, ticker=t3, result="no", sold=0.0, sold_price=None, fill_price=0.10, fill_side="yes")}}           # held and lost: -100%
f = tempfile.mktemp(suffix=".json")
json.dump(dec, open(f, "w"))
html = WB.live_trial_html(C2, led, f)
check("three windows, two live fills, the first +233.3% and the second -100%: mean +66.7%", ("<td data-l=\"Windows\" class=\"num\">3</td>" in html, "+66.7%" in html), (True, True))
check("both rows are shown, the paper row on the same windows", ("<td data-l=\"Row\">Live</td>" in html, "Paper, the same windows" in html), (True, True))
check("rest time and review rule on the page", ("Median time from the open to both bids resting: 1.4 s" in html, "Review at 10 live fills, decide at 30" in html), (True, True))
check("public copy: no dollar amount, no guarded phrase", ("$" in html, sandbox_audit.COPY_RE.findall(html)), (False, []))
check("the 10c row carries it, the retired rows do not", ("Live trial" in WB.section(__import__("swing15").load()).split('id="sw15-archive"')[0]), True)

print(f"\n{'ALL PASS' if not FAILS else str(len(FAILS)) + ' FAILED'}")
raise SystemExit(1 if FAILS else 0)
