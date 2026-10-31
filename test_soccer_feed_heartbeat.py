#!/usr/bin/env python3
"""Offline checks for the soccer feeds' heartbeat (--heartbeat on soccer_rules_production.py and
soccer_team_rules_production.py, 2026-10-30): a fresh updated_at between match windows, never a stale lead."""
import datetime as dt
import sys

import soccer_rules_production as SRP
import soccer_team_rules_production as TP

FAILS = []
UTC = dt.timezone.utc
NOW = dt.datetime(2026, 10, 30, 14, 0, tzinfo=UTC)


def check(label, got, want):
    ok = got == want
    print(f"  {'ok  ' if ok else 'FAIL'} {label}" + ("" if ok else f" (got {got!r}, want {want!r})"))
    if not ok:
        FAILS.append(label)


def pick(rule, ticker, match, team, opp, league, price, status="open", start="2026-10-30T19:00Z",
         logged="2026-10-30T12:00:00+00:00", side="yes", line=1.5, **kw):
    ev = ticker.rsplit("-", 1)[0]
    return dict(dict(id=f"{rule}:{ev}:{'home' if match.startswith(team) else 'away'}", rule=rule, ticker=ticker, event=ev,
                     match=match, team=team, opponent=opp, league=league, side=side, price=price, line=line,
                     start=start, logged=logged, status=status, title=f"Will {team.split()[-1]} score over {line:g} goals?"), **kw)


def state(last_run):
    return {"last_run": last_run.isoformat(), "error": None, "rules": {
        "T5": {"picks": [
            pick("T5", "KXMLSTEAMTOTAL-26OCT30LAFSEA-LAF2", "LAFC v Seattle Sounders", "LAFC", "Seattle Sounders", "MLS", 0.47),
            pick("T5", "KXMLSTEAMTOTAL-26OCT30NYCPHI-NYC2", "NYCFC v Philadelphia", "NYCFC", "Philadelphia", "MLS", 0.45,
                 start="2026-10-30T12:30Z", logged="2026-10-30T11:00:00+00:00")]},
        "T7": {"picks": [pick("T7", "KXBUNDESLIGATEAMTOTAL-26OCT29BAYDOR-BAY3", "Bayern Munich v Dortmund", "Bayern Munich",
                              "Dortmund", "Bundesliga", 0.70, side="no", line=2.5, status="won", start="2026-10-29T16:30Z",
                              logged="2026-10-29T15:00:00+00:00", profit=42.0, payout=1.0)]}}}


def leads(blob, status=None):
    return {l["route"]["market"] if l.get("route") else l["id"]: l for l in blob["leads"].values()
            if status is None or l.get("status") == status}


print("the team-rules feed, collector last read 6h ago (between windows)")
old = state(NOW - dt.timedelta(hours=6))
normal = TP.feed(old, now=NOW)
check("normal build: updated_at is the collector's last read (6h old: the follower's 8h guard is next)",
      normal["updated_at"], (NOW - dt.timedelta(hours=6)).replace(microsecond=0).isoformat())
beat = TP.feed(old, now=NOW, heartbeat=True)
check("heartbeat build: updated_at is the clock", beat["updated_at"], NOW.replace(microsecond=0).isoformat())
check("  and the board_built_at with it", beat["board_built_at"], beat["updated_at"])
check("no stale lead passes as fresh: the collector is unhealthy (6h > 3h), so no open lead is published",
      [l for l in beat["leads"].values() if l.get("status") == "pending"], [])
check("  the settled history stays", sorted(l["id"] for l in beat["leads"].values() if l.get("status") != "pending") ==
      sorted(l["id"] for l in normal["leads"].values() if l.get("status") != "pending"), True)
check("  the collector's health is reported as it is", sorted(set(beat["collector_healthy"].values())), [False])

print("\nthe collector read an hour ago: heartbeat keeps live leads, drops started ones")
fresh = state(NOW - dt.timedelta(hours=1))
hb = TP.feed(fresh, now=NOW, heartbeat=True)
pending = leads(hb, "pending")
check("the 19:00Z kickoff is still a lead; the 12:30Z one (kicked off) is not",
      ("KXMLSTEAMTOTAL-26OCT30LAFSEA-LAF2" in pending, "KXMLSTEAMTOTAL-26OCT30NYCPHI-NYC2" in pending), (True, False))
later = TP.feed(fresh, now=NOW + dt.timedelta(hours=6), heartbeat=True)
check("six hours on, with no new read, the same lead is gone (kicked off 19:00Z; unhealthy collector too)",
      leads(later, "pending"), {})
check("a heartbeat at any hour is within the follower's 8h guard",
      all(dt.datetime.fromisoformat(f["updated_at"]) >= t - dt.timedelta(hours=8)
          for f, t in ((hb, NOW), (later, NOW + dt.timedelta(hours=6)))), True)

print("\nthe rules feed (A7, A6, D3, Argentina over 1.5) takes the same switch")
rs = {"rules": {}, "last_run": (NOW - dt.timedelta(hours=7)).isoformat(), "error": None}
sa = {"picks": [], "rules": {}, "last_run": (NOW - dt.timedelta(hours=7)).isoformat(), "error": None}
nb = SRP.feed(rs, sa, now=NOW)
hbr = SRP.feed(rs, sa, now=NOW, heartbeat=True)
check("normal: the read's time; heartbeat: the clock",
      (nb["updated_at"], hbr["updated_at"]),
      ((NOW - dt.timedelta(hours=7)).replace(microsecond=0).isoformat(), NOW.replace(microsecond=0).isoformat()))
check("no open lead on an unhealthy collector", [l for l in hbr["leads"].values() if l.get("status") == "pending"], [])

print("\nthe switch and the workflow")
import inspect
check("both scripts accept --heartbeat", all('"--heartbeat"' in inspect.getsource(m.main) for m in (SRP, TP)), True)
wf = open(".github/workflows/feeds-heartbeat.yml").read()
check("the heartbeat workflow runs all four feeds with --heartbeat and saves only their files",
      tuple(f"python3 {s} --heartbeat" in wf for s in ("soccer_rules_production.py", "soccer_team_rules_production.py",
                                                       "nba_value_production.py", "daily_production.py")), (True,) * 4)
check("it does not rely on cron alone: twice an hour plus a run after the Sandbox Tracker and the lane workflows",
      ("cron: '7,37 * * * *'" in wf, "workflow_run:" in wf, '"Sandbox Tracker"' in wf, "types: [completed]" in wf), (True,) * 4)
check("it saves exactly the four feed files",
      all(f in wf for f in ("data/soccer_rules_production_leads.json", "data/soccer_team_rules_production_leads.json",
                            "data/nba_value_production_leads.json", "data/econ_production_leads.json")), True)
check("it places nothing and never reads a key", ("TOKEN" in wf.replace("github.token", ""), "secrets." in wf), (False, False))

print("\nthe NBA value and Econ feeds take the same switch (2026-10-31)")
import daily_production as DP
import nba_value_production as NP
import production as P
nv = {"last_run": (NOW - dt.timedelta(hours=6)).isoformat(), "error": None, "rules": {}}
nb, hb = NP.feed(nv, now=NOW), NP.feed(nv, now=NOW, heartbeat=True)
check("NBA value: the read's time normally, the clock on a heartbeat",
      (nb["updated_at"], hb["updated_at"]), ((NOW - dt.timedelta(hours=6)).replace(microsecond=0).isoformat(), NOW.replace(microsecond=0).isoformat()))
check("  and an empty feed stays empty (the lanes left Production)", hb["leads"], {})
ec = {"nc": {l: {"last_success": (NOW - dt.timedelta(hours=7)).isoformat(), "error": None} for l in DP.NC_PUBLISHED}}
eb, eh = DP.feed(ec, now=NOW), DP.feed(ec, now=NOW, heartbeat=True)
check("Econ: the oldest scan's time normally, the clock on a heartbeat",
      (eb["updated_at"], eh["updated_at"]), ((NOW - dt.timedelta(hours=7)).replace(microsecond=0).isoformat(), NOW.replace(microsecond=0).isoformat()))
check("  a stale scan publishes no open lead", [l for l in eh["leads"].values() if l.get("status") == "pending"], [])
check("all four scripts accept --heartbeat", all('"--heartbeat"' in __import__("inspect").getsource(m.main) or "'--heartbeat'" in __import__("inspect").getsource(m.main)
                                                  for m in (SRP, TP, NP, DP)), True)

print("\na feed restamped in the last 20 minutes is left alone")
import json, os, tempfile
with tempfile.TemporaryDirectory() as tmp:
    path = os.path.join(tmp, "f.json")
    P.save_feed({"updated_at": (NOW - dt.timedelta(minutes=5)).isoformat(), "leads": {}}, path)
    check("age 5 min -> below the skip line; 30 min -> above it",
          (round(P.feed_age_min(path, now=NOW)), P.feed_age_min(path, now=NOW + dt.timedelta(minutes=25)) > P.HEARTBEAT_SKIP_MIN), (5, True))
    check("a missing feed has no age (so a heartbeat builds it)", P.feed_age_min(os.path.join(tmp, "none.json")), None)

print(f"\n{'ALL PASS' if not FAILS else str(len(FAILS)) + ' FAILED'}")
sys.exit(1 if FAILS else 0)
