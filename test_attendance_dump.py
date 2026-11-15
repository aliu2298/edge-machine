#!/usr/bin/env python3
"""Offline checks for the attendance and performers dump bid (attendance_dump.py, 2026-11-15): the pool, the PER-ITEM clock (an item confirmed early stops, its
sibling keeps bidding), only events opened after START_TS, the rows (50c-or-less, held control, 20-fill row), the sweep and backfill (idempotent), the
pre-registered read and text, and the page section: no venue call and no guarded phrase."""
import sys

import attendance_dump as A
import attendance_dump_build as AB
import nl_dump as N
import sandbox_audit

FAILS = []


def check(label, got, want):
    ok = got == want
    print(f"  {'ok  ' if ok else 'FAIL'} {label}" + ("" if ok else f" (got {got!r}, want {want!r})"))
    if not ok:
        FAILS.append(label)


B = A.START_TS + 3600


def tape(drop_at=600, low=0.35, rest=0.58, high=0.60, minutes=30):
    p = [(B + 30 * i, high, 20.0, "yes") for i in range(2 * drop_at // 60)]
    p.append((B + drop_at, low, 80.0, "yes"))
    p += [(B + drop_at + 40 + 30 * i, rest, 20.0, "yes") for i in range(2 * minutes)]
    return p


print("the pool")
check("54 series, 30 attend and 24 performers", (len(A.POOL), sum(1 for g in A.POOL.values() if g == A.GROUPS[0]), sum(1 for g in A.POOL.values() if g == A.GROUPS[1])), (54, 30, 24))

print("the per-item clock")
check("an item's own strike", A.strike([(1, 0.5, 1), (5, 0.98, 1)]), 5)
check("an item that never traded under 90c has none", A.strike([(1, 0.95, 1), (5, 0.99, 1)]), None)
t = tape()
r = A.replay(t, "no", False, None)
yes = r["M20_25s"]
check("a bid 20c under 60c fills and is sold back", [b["sold"] for b in yes if b["side"] == "yes"][:1], [True])
check("15c row bids 45c", any(abs(b["L"] - 0.45) < 1e-9 for b in r["M15_25s"] if b["side"] == "yes"), True)
check("the held control never sells", all(not b["sold"] for b in r["H20_25s"]), True)
check("this item's confirm before the drop leaves no fill", A.replay(t, "no", False, B + 300)["M20_25s"], [])
check("bids before START_TS do not count", A.replay([(p[0] - 7200, *p[1:]) for p in t], "no", False, None)["M20_25s"], [])

print("the sweep, events and the ledger")


def mk(ev, op, a_res="yes", b_res="no"):
    def mkt(tk, res):
        return dict(ticker=tk, result=res, open_time=op, close_time="2026-11-20T00:00:00Z", yes_sub_title=tk[-1], event_ticker=ev)
    return [mkt(ev + "-A", a_res), mkt(ev + "-B", b_res)]


def tape_by(tk):
    return tape() if tk.endswith("A") else [(B + 30 * i, 0.5, 5.0, "yes") for i in range(40)] + [(B + 1300, 0.99, 5.0, "yes")]


def get_for(markets):
    def get(path):
        if path.startswith("markets?series_ticker="):
            return dict(markets=[dict(event_ticker=markets[0]["event_ticker"], ticker=markets[0]["ticker"])], cursor=None)
        if path.startswith("events/"):
            return dict(event=dict(title="Grammys attendees", event_ticker=markets[0]["event_ticker"]), markets=markets)
        return {}
    return get


mks = mk("KXATTENDGRAMMYS-27", "2026-11-16T00:00:00Z")
st = A.empty()
n = A.run(st, now=A.START_TS + 100, get=get_for(mks), tape=tape_by, series=["KXATTENDGRAMMYS"])
check("one event read", (n, len(st["events"]), len(st["markets"]), st["pending"]), (1, 1, 2, {}))
check("each item has its own confirm", (st["markets"]["KXATTENDGRAMMYS-27-A"]["confirm"], st["markets"]["KXATTENDGRAMMYS-27-B"]["confirm"] is not None), (None, True))
check("the group is recorded", st["markets"]["KXATTENDGRAMMYS-27-A"]["group"], A.GROUPS[0])
n2 = A.run(st, now=A.START_TS + 200, get=get_for(mks), tape=tape_by, series=["KXATTENDGRAMMYS"])
check("a second run reads nothing again (idempotent)", (n2, len(st["events"])), (0, 1))
old = A.empty()
A.run(old, now=A.START_TS + 100, get=get_for(mk("KXATTENDGRAMMYS-26", "2026-11-01T00:00:00Z")), tape=tape_by, series=["KXATTENDGRAMMYS"])
check("an event that opened before the start is skipped, no bets", ("skipped" in list(old["events"].values())[0], old["markets"]), (True, {}))
openm = mk("KXATTENDGRAMMYS-28", "2026-11-16T00:00:00Z", a_res="")
st3 = A.empty()
check("not all settled: nothing read, still pending", (A.run(st3, now=A.START_TS + 100, get=get_for(openm), tape=tape_by, series=["KXATTENDGRAMMYS"]), len(st3["pending"])), (0, 1))
check("the pending event is kept for months", (A.run(st3, now=A.START_TS + 30 * 86400, get=get_for(openm), tape=tape_by, series=[]), len(st3["pending"])), (0, 1))
check("and dropped after the limit", (A.run(st3, now=A.START_TS + 130 * 86400, get=get_for(openm), tape=tape_by, series=[]), len(st3["pending"])), (0, 0))

print("the rows")
big = A.empty()


def cells(roi, sold, fill):
    return {N.cell_key("M20", d): [dict(roi=roi, side="yes", L=0.4, R=0.6, sold=sold, back=sold, fill=fill)] for d in N.DELAYS}


big["markets"] = {f"E1-{i}": dict(event="E1", day="2026-11-20", series="S", group=A.GROUPS[0], match="m", leg="x", result="yes", prints=9, bets=cells(0.1, True, i))
                  for i in range(20)}
big["markets"]["E2-0"] = dict(event="E2", day="2026-11-20", series="S", group=A.GROUPS[1], match="m", leg="x", result="yes", prints=9, bets=cells(-0.5, False, 1))
check("the 20-fill row keeps only the event with 20 fills", len(A.bets(big, "M20E", A.HEADLINE)), 20)
check("the headline row has both events", len(A.bets(big, "M20", A.HEADLINE)), 21)
check("groups split the headline row", (len(A.bets(big, "M20", A.HEADLINE, A.GROUPS[0])), len(A.bets(big, "M20", A.HEADLINE, A.GROUPS[1]))), (20, 1))

print("the pre-registered read")
for n_, roi, tt, want in ((50, 0.2, 3.0, "too early"), (150, 0.2, 3.0, "read at 100: positive"), (300, 0.1, 2.5, "read at 300: held"),
                          (300, -0.1, -1.0, "read at 300: retired"), (300, 0.05, 1.0, "read at 300: not decided")):
    check(f"{n_} fills, {roi:+.2f}, t {tt}", A.read_text(dict(n=n_, roi=roi, t=tt)).startswith(want), True)
check("the pre-registration text is verbatim", A.PREREG.startswith("Attendance and performers dump bid. Paper.") and A.PREREG.endswith("Expect few fills before February."), True)

print("the page")
real_get = A.D.get


def no_net(*a, **k):
    raise AssertionError("the page build called the venue")


A.D.get = no_net
html = AB.section(big)
html0 = AB.section(A.empty())
A.D.get = real_get
check("the section names the lane", "Attendance and performers dump bid" in html and 'id="attendance-dump"' in html, True)
check("the pre-registration is on the page verbatim", A.PREREG in html, True)
check("percentages only: no dollar sign", "$" in html, False)
check("an empty ledger still builds", "No event read yet" in html0, True)
check("no guarded phrase in the section", sandbox_audit.COPY_RE.search(html), None)
for f in ("attendance_dump.py", "attendance_dump_build.py", "test_attendance_dump.py"):
    check(f"no guarded phrase in {f}", sandbox_audit.COPY_RE.search(open(f).read()), None)

print("ALL PASS" if not FAILS else f"FAILED: {FAILS}")
sys.exit(1 if FAILS else 0)
