"""bot_health.py: the trading engine's health as STATUS ONLY, published hourly from edge-vps to data/bot_health.json.

Written 2026-10-30 for the twice-daily cloud health check (7:30 AM and 7:30 PM CT), which reads this file
instead of a shell on the server. edge-machine is a PUBLIC repository, so (Olu, option B) the file carries
NO MONEY AMOUNTS: no balances, P&L, fees, positions or loss figures. Only:

  engine     state (running / stopped / halted / stale / unreachable), LIVE or dry, cycle, last beat age
  orders     orders placed in the last 24 h, by venue
  errors     open errors (scope and short text, numbers scrubbed), the count cleared since, warning counts
  feeds      each feed's age and lead counts
  loss cap   blocked yes / no (the engine's own test: today's P/L at or below minus the cap)
  balances   OK or LOW per venue against a threshold set on the VPS only (BOT_HEALTH_LOW_USD, default 50),
             from the engine's own day-start read (risk_day.json); the threshold and the cash never leave the box
  P&L        the SIGN only: today so far and yesterday, up / down / flat / unknown
  server     disk %, memory free, the newest backup's age, each scheduled job's last result, published_at

Read-only: it calls the engine's local status API and reads its files; it reads no secret, calls no exchange,
places and cancels nothing. guard() runs before anything is written and refuses a file with a "$" amount, a
money-like field holding a number, or a key-like string; test_bot_health.py runs the same guard over the
committed file and every reports/daily/*.md.

    python3 bot_health.py --out data/bot_health.json      # on edge-vps (scripts/vps_bot_health.sh)
"""
import datetime as dt
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.request

SCHEMA = 1
UTC = dt.timezone.utc
LOUD = {"cycle", "pick", "feed", "results", "unresolved_claim"}   # as health_report.py
# The scheduled jobs whose last result is reported; the unit names them (ENGINE_JOBS) so no host name lives here.
JOBS = tuple(os.environ.get("ENGINE_JOBS", "edge-closes edge-kick edge-health").split())

# ---------------------------------------------------------------- the guard
MONEY_RE = re.compile(r"\$\s*-?\d")
# Field names that would carry money if they held a number, matched on whole words of the name (kalshi_cash,
# day_pnl; never "polymarket"). A state string ("OK", "up") or a bool in one is allowed.
MONEY_KEYS = re.compile(r"(?:^|_)(?:balances?|cash|pnl|p_l|profit|loss|fees?|cost|mark|realised|unrealised|realized|"
                        r"unrealized|account|equity|stake|value|positions?)(?:_|$)", re.I)
SECRET_RE = re.compile(
    r"-----BEGIN|\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b"   # PEM, uuid (ids)
    r"|\b[A-Za-z0-9+/_=-]{40,}\b"                                                    # long key-like runs
    r"|(?i:\b(?:api[_-]?key|secret|token|passphrase|private[_-]?key|order[_-]?id|account[_-]?id)\b)")


def guard(obj):
    """Problems that keep a health file off the public repo: [] when it is fit to publish."""
    out = []
    text = obj if isinstance(obj, str) else json.dumps(obj, ensure_ascii=False)
    if MONEY_RE.search(text):
        out.append("a $ amount")
    if SECRET_RE.search(text):
        out.append("a key-like string or identifier")

    def walk(x, path):
        if isinstance(x, dict):
            for k, v in x.items():
                if MONEY_KEYS.search(str(k)) and isinstance(v, (int, float)) and not isinstance(v, bool):
                    out.append(f"a number in money field {path + str(k)}")
                walk(v, path + str(k) + ".")
        elif isinstance(x, list):
            for i, v in enumerate(x):
                walk(v, f"{path}{i}.")
    if not isinstance(obj, str):
        walk(obj, "")
    return out


_AMOUNT = re.compile(r"\$?[-+]?\d[\d,]*\.\d+|\$\s*\d[\d,]*")


def scrub(text, n=100):
    """An error's words with every amount-looking number and key-like string removed, cut to n characters."""
    return SECRET_RE.sub("…", _AMOUNT.sub("…", str(text or "")))[:n]


# ---------------------------------------------------------------- the build (pure)
def _age_s(iso, now):
    try:
        t = dt.datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return max(0, int((now - t).total_seconds()))


def _sign(x):
    if x is None:
        return "unknown"
    return "up" if x > 0.005 else "down" if x < -0.005 else "flat"


def engine_part(st, service_active, now):
    if st is None:
        state = "unreachable"
    elif st.get("halted"):
        state = "halted"
    elif not st.get("running"):
        state = "stopped"
    elif st.get("stale"):
        state = "stale"
    else:
        state = "running"
    st = st or {}
    return dict(state=state, mode=None if not st else ("dry" if st.get("dry_run") else "LIVE"), cycle=st.get("cycle"),
                beat_age_s=st.get("heartbeat_age_s"), service_active=service_active,
                last_error=scrub(st.get("last_error")) if st.get("last_error") else None)


def ledger_part(rows, now):
    """Orders by venue, open errors, cleared, warnings by type, over the last 24 h (health_report.py's rules)."""
    since = (now - dt.timedelta(hours=24)).isoformat()
    by_venue, loud, warn, last_clean = {}, [], {}, ""
    for r in rows:
        if r.get("ts", "") < since:
            continue
        k = r.get("kind")
        if k == "cycle" and not r.get("problems"):
            last_clean = max(last_clean, r.get("ts", ""))
        if k == "order":
            v = (r.get("venue") or "polymarket_us").replace("polymarket_us", "polymarket")
            by_venue[v] = by_venue.get(v, 0) + 1
        elif k in ("reconcile_wait", "network_wait"):
            warn["transient_retry"] = warn.get("transient_retry", 0) + 1
        elif k == "error":
            if r.get("scope") in LOUD:
                loud.append(r)
            else:
                key = str(r.get("scope") or "other")
                warn[key] = warn.get(key, 0) + 1
    live = [r for r in loud if r.get("ts", "") > last_clean]

    def what(r):
        msg = r.get("err") or r.get("detail") or "; ".join(r.get("problems") or []) or "no detail recorded"
        return dict(scope=str(r.get("scope")) + (f" ({r['feed']})" if r.get("feed") else ""), at=str(r.get("ts", ""))[:16],
                    text=scrub(msg))
    return dict(orders_24h=by_venue, errors=dict(open=[what(r) for r in live[-5:]], open_count=len(live),
                                                  cleared=len(loud) - len(live), warnings=warn))


def feeds_part(st, now):
    out = {}
    for name, f in sorted((((st or {}).get("feed") or {}).get("feeds") or {}).items()):
        age = _age_s(f.get("updated_at"), now)
        out[name] = dict(age_min=None if age is None else round(age / 60), leads=f.get("picks"),
                         actionable=f.get("actionable"), status=f.get("status"),
                         problems=len(f.get("problems") or []))
    return out


def risk_part(st, risk_day, projection, low_usd, now):
    g = (st or {}).get("glance") or {}
    pnl_today, cap = g.get("day_pnl"), g.get("loss_cap")
    blocked = None if pnl_today is None or cap is None else bool(pnl_today <= -cap)
    parts = (risk_day or {}).get("account_parts") or {}
    fresh = (risk_day or {}).get("day") == now.date().isoformat()

    def state(v):
        return "unknown" if v is None or not fresh else ("LOW" if v < low_usd else "OK")
    days = {d.get("offset"): d for d in (projection or {}).get("days") or []}
    yday = (days.get(-1) or {}).get("actual")
    return dict(loss_cap=dict(blocked=blocked, state="unknown" if blocked is None else ("blocked" if blocked else "ok")),
                balances=dict(polymarket=state(parts.get("polymarket_cash")), kalshi=state(parts.get("kalshi_cash")),
                              read_at=str((risk_day or {}).get("account_at") or "")[:16] or None,
                              rule="LOW under the threshold set on the server"),
                pnl_sign=dict(today=_sign(pnl_today), yesterday=_sign(yday.get("pnl")) if yday else "unknown"))


def build(now, st, service_active, ledger_rows, risk_day, projection, server, low_usd=50.0):
    """The published object, from inputs already read. Pure: the tests drive it."""
    doc = dict(schema=SCHEMA, published_at=now.astimezone(UTC).isoformat(timespec="seconds"),
               engine=engine_part(st, service_active, now), **ledger_part(ledger_rows, now),
               feeds=feeds_part(st, now), **risk_part(st, risk_day, projection, low_usd, now), server=server)
    return doc


# ---------------------------------------------------------------- the reads (edge-vps)
def _get(api, path):
    with urllib.request.urlopen(api + path, timeout=25) as f:
        return json.load(f)


def _json(path):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _ledger(path):
    rows = []
    try:
        with open(path) as f:
            for ln in f:
                try:
                    rows.append(json.loads(ln))
                except ValueError:
                    continue
    except OSError:
        pass
    return rows


def _job(unit):
    out = subprocess.run(["systemctl", "show", unit + ".service", "-p", "Result", "-p", "ExecMainExitTimestamp",
                          "-p", "ExecMainStatus"], capture_output=True, text=True).stdout
    kv = dict(line.split("=", 1) for line in out.splitlines() if "=" in line)
    timer = subprocess.run(["systemctl", "is-active", unit + ".timer"], capture_output=True, text=True).stdout.strip()
    if not kv.get("ExecMainExitTimestamp"):
        last = "not run yet"
    else:
        last = "ok" if kv.get("Result") == "success" and kv.get("ExecMainStatus", "0") == "0" else "failed"
    return dict(last=last, timer=timer or "missing")


def server_part(backups, now):
    du = shutil.disk_usage("/")
    mem = {}
    try:
        for line in open("/proc/meminfo"):
            k, v = line.split(":", 1)
            mem[k] = int(v.split()[0]) // 1024
    except OSError:
        pass
    tars = sorted(f for f in os.listdir(backups) if f.endswith(".tgz")) if os.path.isdir(backups) else []
    age = (now.timestamp() - os.path.getmtime(os.path.join(backups, tars[-1]))) / 3600 if tars else None
    return dict(disk_pct=round(du.used / du.total * 100), mem_free_mb=mem.get("MemAvailable"),
                backup_age_h=None if age is None else round(age, 1), jobs={u: _job(u) for u in JOBS})


def read_live(now):
    """Everything from edge-vps. Paths and unit names come from edge-health.service (ENGINE_DIR, ENGINE_UNIT,
    ENGINE_JOBS, BACKUP_DIR); without them the part is reported unknown rather than guessed."""
    api = os.environ.get("ENGINE_API", "http://127.0.0.1:8788")
    home = os.environ.get("ENGINE_DIR", "")
    st = pj = None
    try:
        st = _get(api, "/api/status")
    except Exception:                                           # noqa: BLE001
        st = None
    try:
        pj = _get(api, "/api/projection")
    except Exception:                                           # noqa: BLE001
        pj = None
    unit = os.environ.get("ENGINE_UNIT")
    active = (subprocess.run(["systemctl", "is-active", unit], capture_output=True, text=True).stdout.strip() == "active"
              if unit else None)
    return build(now, st, active, _ledger(os.path.join(home, "ledger.jsonl")) if home else [],
                 _json(os.path.join(home, "risk_day.json")) if home else None,
                 pj, server_part(os.environ.get("BACKUP_DIR", os.path.expanduser("~/backups")), now),
                 low_usd=float(os.environ.get("BOT_HEALTH_LOW_USD", "50")))


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    out = argv[argv.index("--out") + 1] if "--out" in argv else "data/bot_health.json"
    doc = read_live(dt.datetime.now(UTC))
    bad = guard(doc)
    if bad:
        print("bot_health: refusing to publish: " + "; ".join(bad))
        return 1
    tmp = out + ".tmp"
    with open(tmp, "w") as f:
        json.dump(doc, f, indent=1, sort_keys=True)
        f.write("\n")
    os.replace(tmp, out)
    print(f"bot_health: engine {doc['engine']['state']}, {doc['errors']['open_count']} open error(s), wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
