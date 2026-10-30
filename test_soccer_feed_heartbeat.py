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
check("normal build: updated_at is the collector's last read (6h old: the bot's 8h guard is next)",
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
check("a heartbeat at any hour is within the bot's 8h guard",
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
wf = open(".github/workflows/soccer-feed-heartbeat.yml").read()
check("the heartbeat workflow runs both feeds with --heartbeat, hourly, and saves only the two feed files",
      ("python3 soccer_rules_production.py --heartbeat" in wf, "python3 soccer_team_rules_production.py --heartbeat" in wf,
       "cron:" in wf, "git add data/soccer_rules_production_leads.json data/soccer_team_rules_production_leads.json" in wf),
      (True, True, True, True))
check("it places nothing and never reads a key", ("TOKEN" in wf.replace("github.token", ""), "secrets." in wf), (False, False))

print(f"\n{'ALL PASS' if not FAILS else str(len(FAILS)) + ' FAILED'}")
sys.exit(1 if FAILS else 0)
