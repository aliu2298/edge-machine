#!/usr/bin/env python3
"""Offline checks for the mentions dump bid (mentions_dump.py, 2026-11-14): the first-strike clock, bids only before it and after FROM_TS, the 50c-or-less row,
the held control, the maker fee only where the series lists it, the sweep and backfill (idempotent), the pre-registered read, and the page section: no venue
call and no guarded phrase."""
import sys

import mentions_dump as M
import mentions_dump_build as MB
import nl_dump as N
import sandbox_audit

FAILS = []


def check(label, got, want):
    ok = got == want
    print(f"  {'ok  ' if ok else 'FAIL'} {label}" + ("" if ok else f" (got {got!r}, want {want!r})"))
    if not ok:
        FAILS.append(label)


B = M.FROM_TS + 3600


def tape(drop_at=600, low=0.35, rest=0.58, high=0.60, minutes=30):
    """A word at 60c, one print down to `low`, then back to `rest`."""
    p = [(B + 30 * i, high, 20.0, "yes") for i in range(2 * drop_at // 60)]
    p.append((B + drop_at, low, 80.0, "yes"))
    p += [(B + drop_at + 40 + 30 * i, rest, 20.0, "yes") for i in range(2 * minutes)]
    return p


print("the first-strike clock")
check("a jump from under 90c to 97c+ is a strike", M.first_strike({"a": [(1, 0.5, 1), (5, 0.98, 1)]}), 5)
check("a word that never traded under 90c is not a strike", M.first_strike({"a": [(1, 0.95, 1), (5, 0.99, 1)]}), None)
check("the earliest word of the event sets the clock", M.first_strike({"a": [(1, 0.5, 1), (50, 0.99, 1)], "b": [(1, 0.4, 1), (9, 0.97, 1)]}), 9)
check("no trade, no strike", M.first_strike({"a": []}), None)

print("the replay")
t = tape()
r = M.replay(t, "no", False, None)
yes_bets = r["M20_25s"]
check("a bid 20c under 60c fills on the 35c print", any(b["side"] == "yes" and abs(b["L"] - 0.40) < 1e-9 for b in yes_bets), True)
check("it is sold back (price returns inside 5c)", [b["sold"] for b in yes_bets if b["side"] == "yes"][:1], [True])
check("the 15c row bids 45c", any(abs(b["L"] - 0.45) < 1e-9 for b in r["M15_25s"] if b["side"] == "yes"), True)
check("the 50c-or-less row keeps a 40c bid", len(r["M20L_25s"]) > 0, True)
hi = M.replay(tape(high=0.90, low=0.60, rest=0.88), "no", False, None)
check("the 50c-or-less row skips a 70c bid that the main row takes", (all(b["L"] <= 0.5 for b in hi["M20L_25s"]), any(b["L"] > 0.5 for b in hi["M20_25s"])), (True, True))
check("the held control never sells", all(not b["sold"] for b in r["H20_25s"]), True)
check("bids stop at the confirm: a clock before the drop leaves no fill", M.replay(t, "no", False, B + 300)["M20_25s"], [])
check("bids before FROM_TS do not count", M.replay([(p[0] - 7200, *p[1:]) for p in t], "no", False, None)["M20_25s"], [])
mk = M.replay(t, "no", True, None)
check("a maker-fee series charges the resting fill", mk["M20_25s"][0]["roi"] != r["M20_25s"][0]["roi"], True)

print("the sweep, the backfill and the ledger")
CALLS = []


def get(path):
    CALLS.append(path)
    if path.startswith("series?"):
        return {"series": [{"ticker": "KXTEST", "fee_type": "quadratic"}, {"ticker": "KXMAKE", "fee_type": "quadratic_with_maker_fees"}]}
    if path.startswith("markets?series_ticker=KXTEST"):
        return {"markets": [{"event_ticker": "KXTEST-26NOV14", "ticker": "KXTEST-26NOV14-A"}], "cursor": ""}
    if path.startswith("markets?series_ticker="):
        return {"markets": [], "cursor": ""}
    if path.startswith("events/KXTEST-26NOV14"):
        mk = [dict(ticker="KXTEST-26NOV14-A", result="no", close_time="2026-11-15T01:00:00Z", yes_sub_title="Word A"),
              dict(ticker="KXTEST-26NOV14-B", result="yes", close_time="2026-11-15T01:00:00Z", yes_sub_title="Word B")]
        return {"event": {"title": "What will X say?", "event_ticker": "KXTEST-26NOV14"}, "markets": mk}
    raise AssertionError(path)


def fake_tape(tk):
    return tape() if tk.endswith("-A") else [(B + 30 * i, 0.5, 5.0, "yes") for i in range(40)] + [(B + 1300, 0.98, 5.0, "yes")]


st = M.empty()
n = M.run(st, now=M.FROM_TS + 86400, get=get, tape=fake_tape)
check("one event read", (n, sorted(st["events"])), (1, ["KXTEST-26NOV14"]))
check("both words are in the ledger", sorted(st["markets"]), ["KXTEST-26NOV14-A", "KXTEST-26NOV14-B"])
check("the first strike is the 98c print of word B", st["events"]["KXTEST-26NOV14"]["confirm"], B + 1300)
check("the day is the close day", st["events"]["KXTEST-26NOV14"]["day"], "2026-11-15")
check("a series that charges a maker fee is flagged", M.mention_series(get), {"KXTEST": False, "KXMAKE": True})
before = {k: v for k, v in st["markets"].items()}
n2 = M.run(st, now=M.FROM_TS + 90000, get=get, tape=fake_tape)
check("a second run reads nothing again", (n2, st["markets"] == before), (0, True))
check("the sweep goes back a safe margin", st["swept"], M.FROM_TS + 90000)

print("an event with a word still open waits, then is dropped")


def get_open(path):
    if path.startswith("events/"):
        return {"event": {"title": "T"}, "markets": [dict(ticker="X-A", result="yes", close_time="2026-11-15T01:00:00Z"), dict(ticker="X-B", result="")]}
    return get(path)


st2 = M.empty()
st2["pending"]["KXTEST-26NOV14"] = dict(series="KXTEST", first=M.FROM_TS)
check("not all settled: nothing read, still pending", (M.run(st2, now=M.FROM_TS + 100, get=get_open, tape=fake_tape, series={"KXTEST": False}), len(st2["pending"])), (0, 1))
check("after four days it is dropped, not graded", (M.run(st2, now=M.FROM_TS + 5 * 86400, get=get_open, tape=fake_tape, series={}), len(st2["pending"]), st2["events"]), (0, 0, {}))

print("the pre-registered read")
for n_, roi, tt, want in ((50, 0.2, 3.0, "too early"), (150, 0.2, 3.0, "read at 100: positive"), (300, 0.1, 2.5, "read at 300: held"),
                          (300, -0.1, -1.0, "read at 300: retired"), (300, 0.05, 1.0, "read at 300: not decided"), (700, 0.1, 2.5, "read at 600: held")):
    check(f"{n_} fills, {roi:+.2f}, t {tt}", M.read_text("M20", dict(n=n_, roi=roi, t=tt)).startswith(want), True)

print("the page")
rec = M.records(st)
check("the headline row has the fill", rec["M20"]["headline"]["n"] > 0, True)
real_get = MB.M.D.get


def no_net(*a, **k):
    raise AssertionError("the page build called the venue")


MB.M.D.get = no_net
html = MB.section(st)
MB.M.D.get = real_get
check("the section names the lane", "Mentions dump bid" in html and 'id="dump-bid"' in html, True)
check("percentages only: no dollar sign in the section", "$" in html, False)
check("the confirm clock is explained", "97c or more" in html, True)
check("an empty ledger still builds", "No event read yet" in MB.section(M.empty()), True)
check("no guarded phrase in the section", sandbox_audit.COPY_RE.search(html), None)
for f in ("mentions_dump.py", "mentions_dump_build.py", "test_mentions_dump.py"):
    check(f"no guarded phrase in {f}", sandbox_audit.COPY_RE.search(open(f).read()), None)

print("ALL PASS" if not FAILS else f"FAILED: {FAILS}")
sys.exit(1 if FAILS else 0)
