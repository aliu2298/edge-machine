#!/usr/bin/env python3
"""The Control Center reads data/status.json (sandbox_track.build_status).

When the file describes the ledger the page renders, three things come from it:
the overdue open bets (aged to the build clock, plus any bet that crossed its
window after the file was written), the broken feeds, and each lane's last
successful read toward its area's freshness. A missing file falls back to the
ledger quietly; a file from another run, or one that cannot be read, falls back
and is itself an attention item. No network, and nothing reads data/ except the
check that inputs() names the tracker's own path.
"""
import copy
import datetime
import json
import os
import tempfile
from datetime import timedelta, timezone

import control_center as CC
import sandbox_build as SB
import sandbox_sources as S
import sandbox_track as T

FAILS = []
NOW = datetime.datetime(2026, 10, 12, 6, 0, tzinfo=timezone.utc)
RUN = (NOW - timedelta(hours=2)).isoformat()          # the tracker run the file describes


def ok(cond, why):
    print(f"  {'ok  ' if cond else 'FAIL'} {why}")
    if not cond:
        FAILS.append(why)


def eq(got, want, why):
    ok(got == want, why if got == want else f"{why} — got {got!r}, want {want!r}")


def _q(i, source, sport, hours, status="open", **over):
    """One bet starting `hours` from NOW (negative: already started)."""
    start = NOW + timedelta(hours=hours)
    q = dict(id=f"{source}:{sport}:{i}", source=source, sport=sport, bet=True, status=status,
             pick="a", price=0.6, price_a=0.6, price_b=0.42, venue="kalshi_binary",
             market_id=f"M{i}", label=f"Alpha {i} v Beta {i}", side_a="Yes", side_b="No",
             start=start.isoformat(), logged=(start - timedelta(hours=8)).isoformat(),
             date=start.date().isoformat(), stake=100.0, pnl=0.0, result=None)
    q.update(over)
    return q


def _ledger(quotes, feed_status=None, coverage=None, updated=RUN, lane_reads=None):
    meta = {"updated": updated}
    if lane_reads is not None:
        meta["lane_reads"] = lane_reads
    return {"quotes": list(quotes), "coverage": coverage or {}, "feed_status": feed_status or {},
            "meta": meta}


def _model(d, status):
    return CC.model(d, {"pairs": {}, "events": []}, {"leads": {}, "pairs": {}}, NOW,
                    nba={}, market={}, closes={}, runs=None, status=status)


def _kinds(m):
    return [i["kind"] for i in m["attention"]]


def _texts(m, kind):
    return [i["text"] for i in m["attention"] if i["kind"] == kind]


print("which file is used")
d = _ledger([])
st = T.build_status(d, now=datetime.datetime.fromisoformat(RUN))
eq(CC.current_status(None, d), (None, None), "no file: nothing used, nothing said")
eq(CC.current_status(st, d), (st, None), "a file whose ledger_updated is the ledger's run is used")
old, why = CC.current_status(dict(st, ledger_updated="2026-10-11T21:00:00+00:00"), d)
ok(old is None and "describes the run of 2026-10-11T21:00:00+00:00" in why and RUN in why,
   "a file from another run is not used, and the note names both runs")
bad, why = CC.current_status({"written": RUN}, d)
ok(bad is None and "could not be read" in why, "a file without lanes is not used, and says so")
bad, why = CC.current_status(["not", "a", "dict"], d)
ok(bad is None and "could not be read" in why, "nor is a file that is not an object")
_, why = CC.current_status(st, _ledger([], updated=None))
ok(why is not None and "unstamped" in why, "an unstamped ledger cannot be matched")

print("\nbroken feeds come from the file")
d = _ledger([], feed_status={"oddspedia": "down: Cloudflare challenge"})
st = T.build_status(d, now=datetime.datetime.fromisoformat(RUN))
m = _model(d, st)
eq(_texts(m, "feed"), [f"{S.SOURCES['oddspedia']['label']} could not be read on the last run (Cloudflare challenge)"],
   "the feed the run could not read is listed with its reason")
eq(m["status_read"], True, "the model says it read the file")
forged = copy.deepcopy(st)
forged["broken_feeds"] = [{"source": "espn_fpi", "label": "ESPN FPI / Matchup Predictor", "reason": "down: page unreachable"}]
m = _model(d, forged)
eq(_texts(m, "feed"), ["ESPN FPI / Matchup Predictor could not be read on the last run (down: page unreachable)"],
   "the list is the file's, not recomputed from the ledger")
eq([i["area"] for i in m["attention"] if i["kind"] == "feed"], [CC._area_of_sport("nfl")],
   "and each item still lands on its source's area")
clean = copy.deepcopy(st)
clean["broken_feeds"] = []
eq(_texts(_model(d, clean), "feed"), [], "a file that lists none shows none, whatever the ledger's feed_status says")
eq(_texts(_model(d, None), "feed"), [f"{S.SOURCES['oddspedia']['label']} could not be read on the last run (Cloudflare challenge)"],
   "with no file the ledger's own feed check is used, unchanged")
eq(_texts(_model(d, None), "feed"), [f"{l} could not be read on the last run ({r})" for _n, l, r in SB.dark_feeds(d)],
   "which is sandbox_build.dark_feeds")

print("\noverdue bets come from the file, aged to the build clock")
late = _q(1, "corners_under", "soccer_corners", hours=-40)                 # 40h past start now
later = _q(2, "tennis_fav_band_3h", "tennis", hours=-30, venue="polymarket_us")
d = _ledger([late, later])
run_at = datetime.datetime.fromisoformat(RUN)
st = T.build_status(d, now=run_at)
eq([x["id"] for x in st["overdue_open"]], [late["id"], later["id"]], "the file lists both, oldest first")
eq(st["overdue_open"][0]["hours_past_start"], 38.0, "aged to the run that wrote it")
m = _model(d, st)
eq(_texts(m, "overdue"), ["Alpha 1 vs Beta 1 is still open 40h past its start",
                          "Alpha 2 vs Beta 2 is still open 30h past its start"],
   "the page ages each to its own clock and spells the contest the page's way")
eq([i["area"] for i in m["attention"] if i["kind"] == "overdue"], ["soccer", "tennis"], "each on its area")
crossed = _q(3, "corners_under", "soccer_corners", hours=-25)             # 23h past at the run, 25h now
d2 = _ledger([late, later, crossed])
st2 = T.build_status(d2, now=run_at)
eq([x["id"] for x in st2["overdue_open"]], [late["id"], later["id"]], "at the run the third was not yet overdue")
eq(_texts(_model(d2, st2), "overdue")[-1], "Alpha 3 vs Beta 3 is still open 25h past its start",
   "a bet that crossed its window after the file was written is added from the ledger")
settled = _ledger([dict(late, status="won", result="a", pnl=66.67), later])
eq(_texts(_model(settled, dict(st, ledger_updated=RUN)), "overdue"), ["Alpha 2 vs Beta 2 is still open 30h past its start"],
   "a bet the ledger shows settled is not listed, even if the file still names it")
ghost = copy.deepcopy(st)
ghost["overdue_open"].append(dict(st["overdue_open"][0], id="corners_under:soccer_corners:99"))
eq(len(_texts(_model(d, ghost), "overdue")), 2, "an id the ledger does not hold is skipped, never invented")
test = _q(4, "oddspedia", "cricket", hours=-60, venue="polymarket_us",
          market_id="aec-testcr-sao-aus-2026-10-09", label="South Africa v Australia")
d3 = _ledger([test])
eq(_texts(_model(d3, T.build_status(d3, now=run_at)), "overdue"), [],
   "a Test match inside its five-day window is not overdue (the file and the ledger agree)")

print("\na file from another run falls back to the ledger and says so")
stale = dict(T.build_status(d, now=run_at), ledger_updated="2026-10-11T18:00:00+00:00")
stale["overdue_open"] = []
m = _model(d, stale)
eq(_kinds(m)[0], "status", "the first item says the file is out of date")
ok("read the ledger instead" in m["attention"][0]["text"], "and that the ledger was read instead")
eq(len(_texts(m, "overdue")), 2, "the overdue bets are the ledger's, not the stale file's empty list")
eq(m["status_read"], False, "the model says it did not use the file")
eq(_kinds(_model(d, None)).count("status"), 0, "no file at all is not an attention item")

print("\nan area's last read takes its lanes' last_read")
d = _ledger([], lane_reads={"soccer": (NOW - timedelta(hours=20)).isoformat()})
st = T.build_status(d, now=run_at)
eq(next(a for a in _model(d, None)["areas"] if a["key"] == "soccer")["status"], "stale",
   "without the file, a soccer read 20h ago is stale")
fresh = copy.deepcopy(st)
key = next(k for k, v in fresh["lanes"].items() if v["sport"] == "soccer")
fresh["lanes"][key]["last_read"] = (NOW - timedelta(hours=2)).isoformat()
soccer = next(a for a in _model(d, fresh)["areas"] if a["key"] == "soccer")
eq((soccer["status"], soccer["last_read"]), ("healthy", NOW - timedelta(hours=2)),
   "a soccer lane the file says was read 2h ago makes the area fresh")
other = copy.deepcopy(st)
key = next(k for k, v in other["lanes"].items() if v["sport"] == "cricket")
other["lanes"][key]["last_read"] = (NOW - timedelta(hours=1)).isoformat()
eq(next(a for a in _model(d, other)["areas"] if a["key"] == "soccer")["status"], "stale",
   "a read on another family's lane does not freshen soccer")
older = copy.deepcopy(st)
key = next(k for k, v in older["lanes"].items() if v["sport"] == "soccer")
older["lanes"][key]["last_read"] = (NOW - timedelta(hours=40)).isoformat()
eq(next(a for a in _model(d, older)["areas"] if a["key"] == "soccer")["last_read"], NOW - timedelta(hours=20),
   "an older file read never pulls the area back: the newest signal wins")

print("\nthe build reads the tracker's own file")
eq(CC.STATUS_PATH, T.STATUS, "inputs() reads the path write_status writes")
with tempfile.TemporaryDirectory() as tmp:
    path = os.path.join(tmp, "status.json")
    saved = CC.STATUS_PATH
    try:
        CC.STATUS_PATH = path
        eq(CC.inputs()["status"], None, "a missing file reads as None")
        T.write_status(_ledger([], feed_status={"oddspedia": "down: 403"}), now=run_at, path=path)
        got = CC.inputs()["status"]
        eq(got["broken_feeds"][0]["source"], "oddspedia", "a written file reads back whole")
        open(path, "w").write("{not json")
        eq(CC.inputs()["status"], None, "a corrupt file reads as None, not a crash")
    finally:
        CC.STATUS_PATH = saved
d = _ledger([], feed_status={"oddspedia": "down: Cloudflare challenge"})
html = CC.page(NOW, d=d, st={"pairs": {}, "events": []}, blob={"leads": {}, "pairs": {}},
               extra=dict(nba={}, market={}, closes={}, runs=None,
                          status=T.build_status(d, now=run_at)))
ok("could not be read on the last run (Cloudflare challenge)" in html,
   "page() passes the file from inputs() through to the attention list")

print()
if FAILS:
    print(f"{len(FAILS)} FAILED")
    for f in FAILS:
        print(" -", f)
    raise SystemExit(1)
print("all checks passed")
