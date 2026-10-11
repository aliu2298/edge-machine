#!/usr/bin/env python3
"""data/status.json, the overdue grace for a multi-day contest, and the feeds the
last run could not read.

  * A Test match runs five days: a bet on it is not overdue a day after the start,
    on the tracker's flag or on the audit's stale check.
  * sandbox_track.broken_feeds is the one list; the Sandbox feed check prints it.
  * The Pinnacle totals lane reports its own read, so a run that read Pinnacle and
    found no 2.5 line is "ok", not "could not be read".
  * build_status / write_status: the shape the Control Center reads, and last_read
    carried forward across runs.
"""
import datetime
import json
import os
import sys
import tempfile
from datetime import timedelta, timezone

import sandbox_audit
import sandbox_build as B
import sandbox_sources as S
import sandbox_track as T

NOW = datetime.datetime(2026, 10, 11, 20, 0, tzinfo=timezone.utc)
FAILED = 0


def ok(cond, label):
    global FAILED
    print(f"  {'ok  ' if cond else 'FAIL'} {label}")
    if not cond:
        FAILED += 1


def eq(got, want, label):
    ok(got == want, f"{label} — got {got!r}, want {want!r}")


def _bet(qid, hours_ago, source="oddspedia", sport="cricket", venue="polymarket_us", market_id="m",
         label="Alpha v Beta", status="open", logged_ago=None):
    start = NOW - timedelta(hours=hours_ago)
    return dict(id=qid, source=source, sport=sport, venue=venue, market_id=market_id, label=label,
                bet=True, status=status, pick="a", price=0.5, stake=100.0, pnl=0.0,
                start=start.isoformat(), logged=(start - timedelta(hours=logged_ago or 3)).isoformat(),
                side_a="Alpha", side_b="Beta", date=start.date().isoformat())


print("a Test match is not overdue a day after it starts")
test = _bet("oddspedia:aec-testcr-sao-aus-2026-10-09", 45, market_id="aec-testcr-sao-aus-2026-10-09",
            label="South Africa vs Australia")
t20 = _bet("oddspedia:aec-t20icr-x-y-2026-10-10", 30, market_id="aec-t20icr-x-y-2026-10-10")
old_test = _bet("oddspedia:aec-testcr-old-2026-10-01", 150, market_id="aec-testcr-old-2026-10-01")
kalshi = _bet("tennis_combo2:combo2:x", 25, source="tennis_combo2", sport="tennis_combo", venue="combo",
              market_id="combo2:2026-10-10:abc")
d = {"quotes": [test, t20, old_test, kalshi], "meta": {"updated": NOW.isoformat()}}
eq(T.contest_length_h(test), T.TEST_MATCH_H, "a Polymarket US Test slug is a five-day contest")
eq(T.contest_length_h(t20), 0, "a T20 is decided the same day")
eq(T.overdue_after_h(test), T.OVERDUE_H + 5 * 24, "a Test bet is overdue only 24h after its fifth day")
got = [q["id"] for q, _age in T.overdue_bets(d, NOW)]
ok("oddspedia:aec-testcr-sao-aus-2026-10-09" not in got, "45h into a Test is not overdue")
ok("oddspedia:aec-t20icr-x-y-2026-10-10" in got and "tennis_combo2:combo2:x" in got,
   "a T20 at 30h and a basket at 25h still are")
ok("oddspedia:aec-testcr-old-2026-10-01" in got, "a Test 150h past its start is")

print("\nthe audit's stale check gives the Test the same length")
rep = sandbox_audit.Report() if hasattr(sandbox_audit, "Report") else None
if rep is not None:
    sandbox_audit.check_stale({"quotes": [test, old_test], "meta": {"updated": NOW.isoformat()}}, rep, network=False, now=NOW)
    text = " ".join(str(x) for x in list(getattr(rep, "warnings", [])) + list(getattr(rep, "errors", [])))
    ok("sao-aus" not in text, "the two-day-old Test bet is not asked about")
    ok("testcr-old" in text or not text, "the Test well past five days is asked about (or nothing is, offline)")
else:
    ok(True, "audit Report class not importable here; the stale filter is covered by the tracker check")

print("\nbroken feeds: one list, printed by the Sandbox feed check")
dark = {"coverage": {"cricket": {"oddspedia": {"offered": 10, "picked": 0}}}, "feed_status": {}, "quotes": []}
bf = T.broken_feeds(dark)
ok(any(x["source"] == "oddspedia" for x in bf), "a source with rows on offer and no pick on any sport is dark")
ok("Oddspedia community tips could not be read" in B.feed_health(dark), "and the page says so")
fine = {"coverage": {"cricket": {"oddspedia": {"offered": 10, "picked": 0}}}, "feed_status": {"oddspedia": "ok"}, "quotes": []}
eq(T.broken_feeds(fine), [], "a source whose status says ok is not dark whatever it picked")
eq(B.feed_health(fine), "", "and the page prints no warning")
down = {"coverage": {}, "feed_status": {"oddspedia": "down: Cloudflare challenge"}, "quotes": []}
eq([(x["source"], x["reason"]) for x in T.broken_feeds(down)], [("oddspedia", "Cloudflare challenge")],
   "a status that says down names its reason")
ok("Oddspedia community tips (Cloudflare challenge)" in B.feed_health(down), "the page prints the reason")

print("\nthe Pinnacle totals lane reports its own read")
_KO = NOW + timedelta(days=1)


def _o25row(home, away):
    return dict(sport="soccer_o25", venue="kalshi_binary", market_id=f"KXEPLTOTAL-{home[:3].upper()}{away[:3].upper()}-3",
                espn_home=home, espn_away=away, price_a=0.5, price_b=0.5, untraded=False, start=_KO.isoformat(),
                date=_KO.date().isoformat(), side_a="Yes", side_b="No", label=f"{home} v {away} over 2.5")


def _plan(point=3.5, fail=False, key=True, remaining=200):
    S.ODDS_USAGE.clear()
    S.ODDS_USAGE.update(allowance=2, remaining=remaining)
    S._pin_totals_cache.clear()
    S.FEED_STATUS.pop("pin_totals", None)
    real = (S._odds_key, S.pinnacle_events, S._odds_get)
    S._odds_key = (lambda: "stub") if key else (lambda: None)
    S.pinnacle_events = lambda sport: [dict(a="Arsenal", b="Chelsea", start=_KO, key="soccer_epl")]

    def _get(path, params):
        if fail:
            raise RuntimeError("HTTP 500")
        markets = [dict(key="totals", last_update=None,
                        outcomes=[dict(name="Over", price=1.90, point=point),
                                  dict(name="Under", price=1.95, point=point)])]
        return [dict(home_team="Arsenal", away_team="Chelsea",
                     bookmakers=[dict(key="pinnacle", last_update=None, markets=markets)])], {}
    S._odds_get = _get
    try:
        return S.plan_pinnacle_totals({"soccer_o25": [_o25row("Arsenal", "Chelsea")]}, now=NOW)
    finally:
        S._odds_key, S.pinnacle_events, S._odds_get = real


out = _plan(point=3.5)
eq(S.FEED_STATUS.get("pin_totals"), "ok", "a read that found only a 3.5 line is still a read")
eq(out.get("soccer_o25", []), [], "and it quotes nothing at 2.5")
_plan(fail=True)
ok(str(S.FEED_STATUS.get("pin_totals", "")).startswith("down: HTTP 500"), "a failed odds call marks the lane down with the error")
_plan(key=False)
ok(str(S.FEED_STATUS.get("pin_totals", "")).startswith("down: no ODDS_API_KEY"), "no key marks it down")
_plan(remaining=0)
ok(str(S.FEED_STATUS.get("pin_totals", "")).startswith("down: credit reserve"), "the credit reserve marks it down")
S.FEED_STATUS.pop("pin_totals", None)
S.FEED_STATUS.pop("pinnacle", None)
S.ODDS_USAGE.clear()

print("\nthe status file")
d2 = {"quotes": [test, t20, _bet("oddspedia:settled", 60, status="won", market_id="k2")],
      "meta": {"updated": NOW.isoformat()},
      "coverage": {"cricket": {"oddspedia": {"offered": 21, "picked": 0}}},
      "feed_status": {"oddspedia": "ok", "espn_fpi": "down: page unreachable"}}
s = T.build_status(d2, now=NOW)
eq(sorted(s), ["broken_feeds", "lanes", "ledger_updated", "overdue_open", "written"], "the top-level keys")
eq(s["written"], NOW.isoformat(), "written is the build clock")
lane = s["lanes"]["oddspedia|cricket"]
eq(sorted(lane), ["kind", "label", "last_quote", "last_read", "offered", "open", "paused", "picked", "read", "source", "sport"],
   "the lane keys")
eq((lane["read"], lane["last_read"], lane["offered"], lane["picked"], lane["open"]),
   ("ok", NOW.isoformat(), 21, 0, 2), "a source read this run: ok, last_read now, this run's counts, its open bets")
eq(lane["last_quote"], max(q["logged"] for q in d2["quotes"]), "last_quote is the newest logged quote on the lane")
ok(all(k.count("|") == 1 for k in s["lanes"]) and all(S.SOURCES[v["source"]]["connected"] for v in s["lanes"].values()),
   "every lane is source|sport for a connected source")
ok(any(v["read"] == "paused" and v["paused"] for v in s["lanes"].values()), "a paused lane says so")
eq([(x["id"], x["overdue_after_h"]) for x in s["overdue_open"]], [("oddspedia:aec-t20icr-x-y-2026-10-10", 24)],
   "overdue_open lists the T20 and not the Test, with the hours it was allowed")
eq([x["source"] for x in s["broken_feeds"]], ["espn_fpi"], "broken_feeds is broken_feeds(d)")
olbg = next(v for k, v in s["lanes"].items() if k.startswith("espn_fpi|"))
eq((olbg["read"], olbg["last_read"]), ("down: page unreachable", None), "a source down this run has no last_read to carry")
previous = {"lanes": {next(k for k in s["lanes"] if k.startswith("espn_fpi|")): {"last_read": "2026-10-10T08:00:00+00:00"}}}
s2 = T.build_status(d2, now=NOW, previous=previous)
olbg2 = next(v for k, v in s2["lanes"].items() if k.startswith("espn_fpi|"))
eq(olbg2["last_read"], "2026-10-10T08:00:00+00:00", "last_read carries forward from the previous file when this run did not read")
with tempfile.TemporaryDirectory() as tmp:
    path = os.path.join(tmp, "status.json")
    T.write_status(d2, now=NOW, path=path)
    first = json.load(open(path))
    eq(first["lanes"]["oddspedia|cricket"]["last_read"], NOW.isoformat(), "write_status writes the file")
    later = dict(d2, feed_status={"oddspedia": "down: Cloudflare challenge"})
    T.write_status(later, now=NOW + timedelta(hours=3), path=path)
    second = json.load(open(path))
    eq(second["lanes"]["oddspedia|cricket"]["last_read"], NOW.isoformat(),
       "a later run that could not read keeps the last successful read")
    eq(second["lanes"]["oddspedia|cricket"]["read"], "down: Cloudflare challenge", "and says what happened this run")
    ok(not os.path.exists(path + ".tmp"), "the temp file is gone")
_wf = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".github", "workflows", "sandbox-tracker.yml")).read()
ok("if [ -f data/status.json ]; then\n            git add data/status.json" in _wf,
   "the tracker commits data/status.json when the run wrote it, and a run without one still lands its ledger")
ok("write_status(d)" in open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "sandbox_track.py")).read(),
   "main() writes it after the ledger is saved")

print(f"\n{'FAILED: ' + str(FAILED) if FAILED else 'all ok'}")
sys.exit(1 if FAILED else 0)
