#!/usr/bin/env python3
"""Settle-only passes (2026-11-16): the five window-entry ledgers settle every hour while a started pick is open, and add nothing.

Over the international break soccer-team-rules had no run from Nov 8 19:01Z, so Inter v Como and Fiorentina v Juventus sat
"unsettled" for 186 hours; soccer-rules last ran Nov 15 18:46Z. Covered: the switch (settle_only.py) closes every entry gate, the VPS
asks hourly only when a STARTED pick is open and no entry window of that lane is open, the stamps are allowed and trigger their own
workflow, and stuck_picks.py finds open picks 12h past their start."""
import datetime as dt
import json
import os
import re
import tempfile

import lane_windows as LW
import stuck_picks as SP

FAILS = []
UTC = dt.timezone.utc


def check(label, got, want):
    ok = got == want
    print(f"  {'ok  ' if ok else 'FAIL'} {label}" + ("" if ok else f" (got {got!r}, want {want!r})"))
    if not ok:
        FAILS.append(label)


def at(*a):
    return dt.datetime(*a, tzinfo=UTC)


print("the switch")
os.environ.pop("EDGE_SETTLE_ONLY", None)
import contender_overs, nba_rules, nba_value, sa_o15, settle_only, soccer_rules, soccer_team_rules  # noqa: E401
check("off by default", settle_only.on(), False)
now = at(2026, 11, 16, 12, 0)
fx = [dict(league=lg, home="A", away="B", kickoff=(now + dt.timedelta(minutes=45)).isoformat(), played=False)
      for lg in list(soccer_rules.MARKETS["Total goals"] if "Total goals" in soccer_rules.MARKETS else [])[:1]]
os.environ["EDGE_SETTLE_ONLY"] = "1"
check("on", settle_only.on(), True)
check("every entry gate returns nothing",
      (soccer_rules.due(fx, now), soccer_team_rules.due(fx, now), nba_rules.due([dict(start=now.isoformat())], now),
       contender_overs.due(fx, now), sa_o15.due(fx, now), nba_value.due("nba_tt_value_1h", {"x": dict(start=now.isoformat())}, now)),
      ([], [], [], [], [], []))
import climate_lanes
st = climate_lanes.new_state() if hasattr(climate_lanes, "new_state") else None
os.environ.pop("EDGE_SETTLE_ONLY", None)

print("\nthe VPS asks only for a started open pick")
d = tempfile.mkdtemp()
os.makedirs(os.path.join(d, "data"))


def ledger(name, picks=None, rows=None):
    body = {"rules": {"r": {"picks": picks}}} if picks is not None else {"rows": rows}
    json.dump(body, open(os.path.join(d, "data", name), "w"))


ledger("soccer_rules_ledger.json", [dict(status="open", start="2026-11-15T14:00:00Z")])
ledger("contender_overs_ledger.json", [dict(status="won", start="2026-11-10T14:00:00Z")])
ledger("sa_o15_ledger.json", [])
ledger("soccer_team_rules_ledger.json", [dict(status="open", start="2026-11-17T14:00:00Z")])          # not started yet
ledger("nba_rules_ledger.json", [dict(status="lost", start="2026-11-10T14:00:00Z")])
ledger("nba_value_ledger.json", [dict(status="open")])                                                  # no start: counted
ledger("climate_lanes_ledger.json", rows=[dict(status="open", day="2026-11-15")])
op = LW.settle_open(now, root=d)
check("started open pick -> asked", op["soccer_rules_settle"], True)
check("an open pick that has not started -> not asked", op["soccer_team_rules_settle"], False)
check("only settled picks -> not asked", op["nba_rules_settle"], False)
check("an open pick with no start -> asked", op["nba_value_settle"], True)
check("a weather row whose day has ended -> asked", op["climate_settle"], True)
check("... but not on the day itself", LW.settle_open(at(2026, 11, 15, 20, 0), root=d)["climate_settle"], False)
check("no ledger file -> not asked", LW.settle_open(now, root=os.path.join(d, "none"))["soccer_rules_settle"], False)

asks = lambda t, s: sorted(w["lane"] for w, k in LW.due(t, ledger={"quotes": []}, games=[], fixtures=[], settle=s) if w["lane"].endswith("_settle"))   # noqa: E731
check("one read this hour per open lane", asks(now, op), ["climate_settle", "nba_value_settle", "soccer_rules_settle"])
check("no settle windows without the ledgers (tests, plain listing)", [w for w in LW.windows(now) if w["lane"].endswith("_settle")], [])
check("read number 1, a new stamp text every hour", (LW.stamp_lines(now, settle=op)["data/soccer_rules_settle_window/request.txt"],
      LW.stamp_lines(now + dt.timedelta(hours=1), settle=op)["data/soccer_rules_settle_window/request.txt"]),
      ("soccer_rules_settle 2026-11-16T13:00:00+00:00 read 1", "soccer_rules_settle 2026-11-16T14:00:00+00:00 read 1"))
check("asked at any minute of the hour, once per hour (the stamp text is the same)",
      (LW.stamp_lines(at(2026, 11, 16, 12, 1), settle=op) == LW.stamp_lines(at(2026, 11, 16, 12, 46), settle=op)), True)

print("\nan entry window that is open settles anyway: no second ask")
ko = at(2026, 11, 16, 13, 0)
fxs = [dict(league=sorted(LW.SOCCER_SERIES)[0], kickoff=ko.isoformat(), played=False, home="A", away="B")]
inside = at(2026, 11, 16, 12, 0)                         # 60 minutes before: inside 90-20
w = [x for x in LW.windows(inside, ledger={"quotes": []}, games=[], fixtures=fxs, settle=op) if x["lane"] in ("soccer_rules", "soccer_rules_settle")]
check("entry window open -> no soccer_rules_settle window", sorted(x["lane"] for x in w), ["soccer_rules"])
w = [x for x in LW.windows(at(2026, 11, 16, 15, 0), ledger={"quotes": []}, games=[], fixtures=fxs, settle=op) if x["lane"] in ("soccer_rules", "soccer_rules_settle")]
check("... and once it has closed the settle window is back", "soccer_rules_settle" in [x["lane"] for x in w], True)

print("\nthe stamps, the VPS allow-list and the workflows")
vps = open("scripts/vps_window_requests.sh").read()
for lane, path in [(k, v) for k, v in LW.STAMP.items() if k.endswith("_settle")]:
    wf = {"soccer_rules_settle": "soccer-rules", "soccer_team_rules_settle": "soccer-team-rules", "nba_rules_settle": "nba-rules",
          "nba_value_settle": "nba-value", "climate_settle": "climate-lanes"}[lane]
    y = open(f".github/workflows/{wf}.yml").read()
    check(f"{lane}: allowed on the VPS, triggers {wf}.yml, sets the switch, and matches the window glob",
          (f"{path}" in vps, os.path.dirname(path) + "/**" in y, "EDGE_SETTLE_ONLY=1" in y, bool(re.match(r"data/[a-z_]+_window/request\.txt$", path))),
          (True, True, True, True))
check("every settle lane has a stamp", sorted(LW.SETTLE_LANES), sorted(k for k in LW.STAMP if k.endswith("_settle")))

print("\nstuck_picks.py")
now2 = at(2026, 11, 16, 12, 0)
data = {"last_run": "2026-11-16T11:00:00+00:00", "rules": {"r": {"picks": [
    dict(status="open", ticker="OLD", start="2026-11-08T19:00:00Z"), dict(status="open", ticker="NEW", start="2026-11-16T09:00:00Z"),
    dict(status="open", ticker="NOSTART"), dict(status="won", ticker="DONE", start="2026-11-01T00:00:00Z")]}}}
stuck, no_start, total = SP.scan(data, now2, 12.0)
check("open 12h past the start is stuck; recent, no-start and settled picks are not", ([t for t, h in stuck], no_start, total), (["OLD"], 1, 3))
check("the age of last_run", round(SP.age(data, now2), 2), 1.0)
check("a bare day counts as the end of that day", SP.start_of(dict(day="2026-11-15")), at(2026, 11, 16, 0, 0))
# 2026-11-22: a "no quote" shadow record and a perp entered on a Friday evening (time stop in regular-hours minutes) were reported stuck.
fri = at(2026, 11, 20, 21, 18).timestamp()
perps = {"events": [dict(status="open", ticker="KXBAPERP", day="2026-11-20", entry_ts=int(fri)),
                    dict(status="open", ticker="KXOLDPERP", day="2026-11-01", entry_ts=int(fri) - 20 * 86400)],
         "btts": {"T1:X": dict(status="open", event="X", start="2026-11-21T16:15Z", quote=False)}}
check("a perp held over the weekend and a no-quote shadow are not stuck; a perp past any time stop is",
      [t for t, h in SP.scan(perps, at(2026, 11, 22, 8, 30), 12.0)[0]], ["KXOLDPERP"])
d2 = tempfile.mkdtemp()
os.makedirs(os.path.join(d2, "data"))
json.dump(data, open(os.path.join(d2, "data", "x_ledger.json"), "w"))
lines, n = SP.report(root=d2, now=now2)
check("report: one line per ledger with the ticker and the last_run age", (n, [l for l in lines if l.startswith("x_ledger")][0].count("OLD"),
      "last_run 1.0h ago" in [l for l in lines if l.startswith("x_ledger")][0]), (1, 1, True))

# 2026-11-16: the Tests step ran with EDGE_SETTLE_ONLY=1 (set by the step before it) and the entry tests died; every settle-only workflow's Tests step must clear it.
import glob
for wf in ("soccer-rules", "soccer-team-rules", "nba-rules", "nba-value", "climate-lanes"):
    txt = open(f".github/workflows/{wf}.yml").read()
    i = txt.index("- name: Tests")
    check(f"{wf}: the Tests step clears EDGE_SETTLE_ONLY", 'EDGE_SETTLE_ONLY: ""' in txt[i:i + 300], True)

print()
if FAILS:
    print(f"{len(FAILS)} FAILED")
    raise SystemExit(1)
print("ALL OK")
