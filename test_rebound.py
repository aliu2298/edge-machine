#!/usr/bin/env python3
"""Rebound after a slide (rebound.py, 2026-11-11): observation-only lanes — the slide, the support, the confirmation,
honest fills, the fresh record v the in-sample backfill, and the page row."""
import datetime as dt
import os
import re
import sys

import invest as I
import invest_build as IB
import rebound as R
import sandbox_audit

FAILS = []


def check(why, got, want):
    good = got == want
    print(f"  {'ok  ' if good else 'FAIL'} {why}" + ("" if good else f" — got {got!r}, want {want!r}"))
    if not good:
        FAILS.append(why)


UTC = dt.timezone.utc
T0 = int(dt.datetime(2026, 11, 16, 14, 30, tzinfo=UTC).timestamp())           # Monday 09:30 ET


def daily(n=60, low=100.0):
    """n sessions to Friday 2026-11-13: flat at 110, one pivot low at `low` 20 sessions back."""
    out, d = [], dt.date(2026, 11, 13)
    days = []
    while len(days) < n:
        if d.weekday() < 5:
            days.append(d)
        d -= dt.timedelta(days=1)
    for i, day in enumerate(reversed(days)):
        lo = low if i == n - 20 else 108.0
        out.append(dict(t=f"{day}T05:00:00Z", o=110.0, h=111.0, l=lo, c=110.0, v=1e6))
    return out


def ticks(path):
    """Minute reference ticks (stock price / 50): 110 -> a slide to 100.2 (touching 100), RSI turns up, back to 104."""
    rows, px = [], 110.0
    seq = [110.0] * 60 + [110.0 - 0.1 * k for k in range(1, 99)] + [100.2] * 20 + [100.2 + 0.05 * k for k in range(1, 80)]
    for k, p in enumerate(seq):
        rows.append(dict(ts=T0 + 60 * k, sym="ABC", bid=round(p / 50 - 0.002, 4), ask=round(p / 50 + 0.002, 4),
                         last=p / 50, ref=p / 50, open=True))
    return rows


rows = ticks(None)
D = daily()
print("the lanes")
check("two observation-only lanes, as the research ranked them", (sorted(R.LANES), R.LANES["rb_5d"]["strong"],
      R.LANES["rb_24h"]["drop"], R.LANES["rb_5d"]["drop"], R.PREREG_SHA[:8]), (["rb_24h", "rb_5d"], True, 0.05, 0.10, "17ecd1cd"))

print("\nthe signal")
ev = R.signals("KXABCPERP", rows, D, [], 50.0, "rb_24h", set(), T0 + 86400)
check("a 5%+ slide that reaches support (100, a daily pivot low) and whose selling slows gives one event",
      (len(ev), ev and ev[0]["level_stock"], ev and ev[0]["stop"], ev and round(ev[0]["target"] * 50, 2)),
      (1, 100.0, round(0.99 * 100 / 50, 6), round(100 + 0.5 * (110.0 - 100), 2)))
check("the entry signal comes after the touch, never on it", ev[0]["signal_ts"] > ev[0]["touch_ts"], True)
flat = [dict(r, ref=r["ref"] if r["ref"] > 105 / 50 else 105 / 50) for r in rows]
check("no slide (the price never 5% under its 24-hour high): no event", R.signals("KXABCPERP", flat, D, [], 50.0, "rb_24h", set(), T0 + 86400), [])
check("the 5-day lane needs a 10% slide: 110 -> 100.2 is 8.9%, so nothing", R.signals("KXABCPERP", rows, D, [], 50.0, "rb_5d", set(), T0 + 86400), [])
weak = R.signals("KXABCPERP", rows, daily(low=90.0), [], 50.0, "rb_24h", set(), T0 + 86400)
check("with no pivot at 100 the touch is the round number 100 (any support counts on the 24-hour lane)",
      (len(weak), weak and weak[0]["strength"]), (1, 0))
check("strength counts the methods agreeing (pivot + tested before) on the 100 level", ev[0]["strength"] >= 1, True)
broke = rows[:178] + [dict(r, ts=r["ts"], ref=95 / 50, bid=95 / 50 - 0.002, ask=95 / 50 + 0.002) for r in rows[178:]]
check("support that fails (a close 0.5% under it) before selling slows gives no event",
      R.signals("KXABCPERP", broke, D, [], 50.0, "rb_24h", set(), T0 + 86400), [])
check("one per stock per session: a known id is not logged again",
      R.signals("KXABCPERP", rows, D, [], 50.0, "rb_24h", {ev[0]["id"]}, T0 + 86400), [])

print("\nhonest fills")
e = dict(ev[0])
prints = lambda t0, t1: [(t, r["ask"]) for r in rows for t in (r["ts"] + 5,) if t0 <= t < t1]
R.grade(e, rows, prints, T0 + 86400)
first = next(r for r in rows if r["ts"] > ev[0]["signal_ts"])
check("the entry fills at the ask of the next minute on a print at or through it; still under the target: open",
      (e["status"], e["entry"], e["entry_ts"]), ("open", first["ask"], first["ts"]))
e3 = dict(e)
R.grade(e3, rows, lambda t0, t1: prints(t0, t1) + ([(t0 + 1, e["target"] + 0.001)] if t0 > e["entry_ts"] + 600 else []), T0 + 86400)
check("the target fills only on a print through it, at the target, maker fee", (e3["status"], e3["exit_why"], e3["exit"]),
      ("settled", "target", e["target"]))
e2 = dict(ev[0])
R.grade(e2, rows, lambda t0, t1: [], T0 + 86400)
check("no print at or through the ask in 5 minutes: no fill", e2["status"], "no_fill")

print("\nthe record and the page")
st = dict(events=[dict(ev[0], status="settled", net=0.02, exit_why="target", backfill=True),
                  dict(ev[0], id="x", status="settled", net=-0.01, exit_why="stop", backfill=False)], ratios={})
check("the fresh record leaves out the in-sample backfill", (R.summary(st)["rb_24h"]["n"], R.summary(st, True)["rb_24h"]["n"]), (1, 2))
html, n, settled, open_ = IB.section_and_counts(state={"events": [], "flags": [], "collector": {}}, research={}, rebound_state=st)
check("two observation rows in the Invest section, counted as running lanes, labelled observation only",
      (n, len(re.findall(r'data-source="invest_rb_', html)), "observation" in html, "did not clear the research bar" in html),
      (2, 2, True, True))
check("in-sample rows are marked so; the how-it-was-tested fold says none cleared",
      ("in-sample" in html, "None did" in html), (True, True))
check("plain copy: no dollar sign, no guarded phrase, no market id", (re.search(r"\$\d", html), sandbox_audit.COPY_RE.findall(html),
      re.findall(r"\bKX[A-Z0-9]{3,}", html)), (None, [], []))
check("the VPS run calls it after invest.py and publishes its state",
      all(x in open(os.path.join(I.ROOT, "scripts", "vps_invest.sh")).read() for x in ("rebound.py track", "data/rebound_state.json")), True)
check("index perps are never sent to Alpaca (a non-ticker fails the whole batch)",
      "re.fullmatch(r\"[A-Z]{1,5}(\\.[A-Z])?\"" in open(os.path.join(I.ROOT, "rebound.py")).read(), True)

print(f"\n{'ALL PASS' if not FAILS else str(len(FAILS)) + ' FAILED'}")
sys.exit(1 if FAILS else 0)
