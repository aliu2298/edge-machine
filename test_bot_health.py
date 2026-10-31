#!/usr/bin/env python3
"""bot_health.py (status-only health, published hourly from edge-vps), the reports/daily rules and the Sandbox
"Daily health" card (daily_health.py). Offline.

The guard is the point: edge-machine is public, so data/bot_health.json and every reports/daily report must
carry no money amount and nothing key-like. This test runs the guard over the committed files too, so a
report that breaks the rule turns the suite red.
"""
import datetime as dt
import json
import os
import re
import sys
import tempfile

import bot_health as H
import daily_health as DH
import sandbox_audit

FAILS = []
ROOT = os.path.dirname(os.path.abspath(__file__))
NOW = dt.datetime(2026, 10, 31, 12, 0, tzinfo=dt.timezone.utc)
# A word the public pages are kept free of, assembled so this file does not carry it (sandbox_audit scans it).
GUARDED = "b" + "ot"


def check(label, got, want):
    ok = got == want
    print(f"  {'ok  ' if ok else 'FAIL'} {label}" + ("" if ok else f" (got {got!r}, want {want!r})"))
    if not ok:
        FAILS.append(label)


def iso(mins_ago):
    return (NOW - dt.timedelta(minutes=mins_ago)).isoformat()


print("the guard")
check("a clean status object passes", H.guard({"engine": {"state": "running"}, "balances": {"kalshi": "OK"}}), [])
check("a $ amount anywhere fails", H.guard({"note": "account $1,204"}), ["a $ amount"])
check("a money field holding a number fails, whatever its name's case",
      [x for x in H.guard({"balances": {"Kalshi_Cash": 812.4}, "pnl": 3})], ["a number in money field balances.Kalshi_Cash",
                                                                           "a number in money field pnl"])
check("a state string in a money field is allowed; a bool too", H.guard({"pnl_sign": {"today": "up"}, "loss_cap": {"blocked": True}}), [])
check("key-like strings and identifiers fail: a uuid, a long token, a PEM, a named key",
      [bool(H.guard(x)) for x in ({"x": "4f6a2c1e-0b9d-4c3e-8a77-12ab34cd56ef"}, {"x": "A" * 44},
                                  {"x": "-----BEGIN PRIVATE KEY-----"}, {"api_key": "x"}, {"note": "order_id 77"})],
      [True, True, True, True, True])
check("plain text works too (a report)", (H.guard("1 red, 0 amber\n- red · x · balance $40"), H.guard("All green")),
      (["a $ amount"], []))
check("scrub takes amounts and key-like strings out of an error's words",
      H.scrub("daily loss cap reached (-12.34 today against a -25.00 cap), order 4f6a2c1e-0b9d-4c3e-8a77-12ab34cd56ef $5"),
      "daily loss cap reached (… today against a … cap), order … …")

print("\nthe build: status only")
ST = dict(running=True, halted=False, stale=False, dry_run=False, cycle=41210, heartbeat_age_s=40, last_error="venue said $3.10 short",
          feed=dict(feeds=dict(production=dict(updated_at=iso(12), picks=30, actionable=4, status="ok", problems=[]),
                               production_econ=dict(updated_at=iso(95), picks=2, actionable=0, status="stale", problems=["old"]))),
          glance=dict(day_pnl=-26.5, loss_cap=25.0, open_positions=9),
          pnl=dict(totals=dict(realised=12.3, cost=100.0)))
LEDGER = [dict(ts=iso(60 * 30), kind="order", venue="kalshi"),
          dict(ts=iso(300), kind="order", venue="kalshi"), dict(ts=iso(200), kind="order"),
          dict(ts=iso(250), kind="error", scope="feed", feed="production", err="HTTP 502 at $9 depth"),
          dict(ts=iso(100), kind="cycle"),
          dict(ts=iso(50), kind="error", scope="cycle", err="Kalshi 429 on /portfolio/balance"),
          dict(ts=iso(40), kind="error", scope="orphan"), dict(ts=iso(30), kind="network_wait")]
RISK = dict(day="2026-10-31", account_at="2026-10-31T00:05:11", account_parts=dict(polymarket_cash=212.0, kalshi_cash=31.5,
                                                                                  positions_mark=40.0), account=283.5)
PROJ = dict(days=[dict(offset=-1, actual=dict(pnl=4.2)), dict(offset=0, actual=None)])
SERVER = dict(disk_pct=41, mem_free_mb=512, backup_age_h=5.5, jobs={"edge-closes": dict(last="ok", timer="active")})
doc = H.build(NOW, ST, True, LEDGER, RISK, PROJ, SERVER, low_usd=50)
check("engine: running, LIVE, cycle, beat age, the service, the error's words without the amount",
      doc["engine"], dict(state="running", mode="LIVE", cycle=41210, beat_age_s=40, service_active=True,
                          last_error="venue said … short"))
check("orders in the last 24 h by venue (the 30 h old order is out; no venue means Polymarket)",
      doc["orders_24h"], {"kalshi": 1, "polymarket": 1})
check("errors: the loud one after the last clean cycle is open, the one before it cleared, quiet ones are warnings by type",
      (doc["errors"]["open_count"], doc["errors"]["cleared"], doc["errors"]["warnings"], doc["errors"]["open"][0]["scope"]),
      (1, 1, {"orphan": 1, "transient_retry": 1}, "cycle"))
check("feeds: age in minutes and lead counts", doc["feeds"]["production_econ"],
      dict(age_min=95, leads=2, actionable=0, status="stale", problems=1))
check("loss cap: blocked when today's P/L is at or below minus the cap", doc["loss_cap"], dict(blocked=True, state="blocked"))
check("balances: OK or LOW against the threshold from today's read, never the cash",
      (doc["balances"]["polymarket"], doc["balances"]["kalshi"], doc["balances"]["read_at"]), ("OK", "LOW", "2026-10-31T00:05"))
check("P&L: the sign only", doc["pnl_sign"], dict(today="down", yesterday="up"))
check("the published object passes its own guard, and no input amount survives in it",
      (H.guard(doc), any(s in json.dumps(doc) for s in ("26.5", "212", "31.5", "283", "12.3", "100.0", "$"))), ([], False))
stale = H.build(NOW, ST, True, [], dict(RISK, day="2026-10-30"), None, SERVER)
check("a day-start read from another day leaves the balances unknown", (stale["balances"]["kalshi"], stale["pnl_sign"]["yesterday"]),
      ("unknown", "unknown"))
down = H.build(NOW, None, False, [], None, None, SERVER)
check("an unreachable engine says so, with nothing invented",
      (down["engine"]["state"], down["engine"]["mode"], down["loss_cap"]["state"], down["feeds"], down["orders_24h"]),
      ("unreachable", None, "unknown", {}, {}))
check("halted and stale engines are named", (H.engine_part(dict(ST, halted=True), True, NOW)["state"],
                                             H.engine_part(dict(ST, stale=True), True, NOW)["state"]), ("halted", "stale"))
check("its top-level shape", sorted(doc), sorted(["schema", "published_at", "engine", "orders_24h", "errors", "feeds", "loss_cap",
                                                  "balances", "pnl_sign", "server"]))

print("\nthe committed files: data/bot_health.json and every reports/daily report")
path = os.path.join(ROOT, "data", "bot_health.json")
if os.path.exists(path):
    check("data/bot_health.json passes the guard", H.guard(json.load(open(path))), [])
else:
    print("  skip  data/bot_health.json is not published yet")
names = DH.reports()
for n in names:
    text = open(os.path.join(DH.DIR, n), encoding="utf-8").read()
    check(f"reports/daily/{n} passes the guard", H.guard(text), [])
    check(f"reports/daily/{n} is in the README's format", DH.parse(text) is not None, True)
check("the README states the rules the routine follows",
      all(x in open(os.path.join(DH.DIR, "README.md")).read() for x in ("YYYY-MM-DD-am.md", "All green", "N red, N amber",
                                                                       "No money amounts", "BOT_HEALTH_LOW_USD")), True)

print("\nthe Sandbox card")
with tempfile.TemporaryDirectory() as d:
    check("no report yet", "no report yet" in DH.card(d), True)
    open(os.path.join(d, "2026-10-30-pm.md"), "w").write("All green\nChecked 2026-10-30 19:30 CT\n- green · Sandbox · ok\n")
    open(os.path.join(d, "2026-10-31-am.md"), "w").write(
        "1 red, 2 amber\nChecked 2026-10-31 07:30 CT\n- green · Sandbox Tracker · ran 40 min ago\n"
        "- amber · Chaos replay · last run 26 h ago\n- red · Trading engine · not cycling for 12 min\n"
        f"- amber · {GUARDED.title()} engine · the {GUARDED} is stale\n")
    open(os.path.join(d, "notes.md"), "w").write("not a report")
    c = DH.card(d)
    t = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", c))
    check("the newest report (am of the 31st after pm of the 30th), its verdict and time",
          ("1 red, 2 amber" in t, "checked 2026-10-31 07:30 CT" in t, "2026-10-31-am.md" in c), (True, True, True))
    check("red first, then amber; greens are not listed",
          re.findall(r'<li class="(\w+)">', c), ["red", "amber", "amber"])
    check("a line the public pages cannot carry shows only its status", "a component · detail in the report" in t, True)
    check("the card passes the copy guard and the money guard", (sandbox_audit.COPY_RE.search(t), H.guard(t)), (None, []))
    open(os.path.join(d, "2026-11-01-am.md"), "w").write("Everything fine\n")
    check("a newest report out of format says so", "not in the expected format" in DH.card(d), True)
import sandbox_build
check("the card sits on the Sandbox page", 'id="daily-health"' in sandbox_build.daily_health_card(), True)

print("\nthe VPS plumbing")
sh = open(os.path.join(ROOT, "scripts", "vps_bot_health.sh")).read()
unit = open(os.path.join(ROOT, "scripts", "edge-health.service")).read()
timer = open(os.path.join(ROOT, "scripts", "edge-health.timer")).read()
check("the script commits only data/bot_health.json, under the shared clone lock, after a rebase",
      (re.findall(r"git add (\S+)", sh), "edge-shared.lock" in sh, "git pull -q --rebase origin main" in sh), (["data/bot_health.json"], True, True))
check("the unit sets the paths, the jobs and the LOW threshold on the server only",
      all(x in unit for x in ("ENGINE_DIR=", "ENGINE_UNIT=", "ENGINE_JOBS=", "BOT_HEALTH_LOW_USD=50", "User=" + GUARDED)), True)
check("the job list is quoted, or systemd keeps only its first name",
      re.search(r'^Environment="ENGINE_JOBS=[^"]+ [^"]+"$', unit, re.M) is not None, True)
check("the job never reports on itself (systemd clears its last exit while it runs)",
      "edge-health" in re.search(r'ENGINE_JOBS=([^"]+)', unit).group(1), False)
check("hourly", "OnCalendar=*-*-* *:23:00" in timer and "Persistent=true" in timer, True)
check("no guarded phrase in the new public files",
      [f for f in ("bot_health.py", "daily_health.py", "scripts/vps_bot_health.sh", "reports/daily/README.md")
       if sandbox_audit.COPY_RE.search(open(os.path.join(ROOT, f)).read())], [])

print(f"\n{'ALL PASS' if not FAILS else str(len(FAILS)) + ' FAILED'}")
sys.exit(1 if FAILS else 0)
