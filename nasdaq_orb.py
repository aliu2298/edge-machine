"""Nasdaq open breakout (2026-10-18): a Sandbox PAPER lane on QQQ. It never places an order.

Asked for by Olu after the research of 2026-10-18 (memory gold-asia-open-breakout): a friend's
opening-range breakout, tested on 807 days of QQQ 1-minute bars. Done without look-ahead
(signal = a minute CLOSING beyond the range, entry = the NEXT minute's open) it is flat to
negative; this lane watches it live anyway. Not in Production, not fed to the bot, and it does
not touch the Alpaca account: it reads market data only.

Pre-registered variants, one row per variant per trading day, QQQ, no stop, one position:
  A    "friend"       range 9:30-10:00 ET, signal from 10:00, exit 15 min after entry
  B    "first 5"      range 9:30-9:35 ET,  signal from 9:35,  exit 15 min after entry
  C15  "premarket 5"  range 9:25-9:30 ET,  signal from 9:30,  exit 15 min after entry
  C30  "premarket 5"  the same, exit 30 min after entry (the version that read best before
                      the look-ahead fix: +3.5bp at a 30-minute hold)
The signal is the first minute, from the variant's start and before 11:00 ET, whose CLOSE is
above the range high (long) or below the range low (short). Entry is the NEXT minute's open;
exit is the close of the minute that ends `hold` minutes after entry. No signal before 11:00 is
no_break. Market holidays and half-days (an early close) are logged as skipped.

Prices. Gross bp is open-to-close from the 1-minute bars. Net bp buys at the ask and sells at
the bid, from the latest quote snapshotted at the start of the entry minute and of the exit
minute (Alpaca charges no stock commission). Alpaca's plan here forbids the SIP latest quote
and SIP bars younger than 15 minutes (HTTP 403, checked 2026-10-18), so:
  * quotes are IEX's top of book, polled once a minute while the session runs;
  * bars are SIP (premarket included, which variant C needs; IEX has no 9:25 bars) and are read
    once they are 15 minutes old. Every decision uses only bars that closed by that minute, so
    reading them later changes nothing about what the rule could have known.

Runs on edge-vps from a user crontab (scripts/vps_nasdaq_orb.sh), started before 9:20 ET and
sleeping on the New York clock, so it is DST-safe.
"""
import datetime as dt
import json
import math
import os
import sys
import time
import urllib.parse
from zoneinfo import ZoneInfo

ROOT = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(ROOT, "data", "nasdaq_orb_ledger.json")
ET = ZoneInfo("America/New_York")
SYMBOL = "QQQ"
REVIEW_AT = 10                         # settled days per variant before a review
CUTOFF = (11, 0)                       # no signal minute at or after 11:00 ET
DATA = "https://data.alpaca.markets"
CALENDAR = "https://paper-api.alpaca.markets/v2/calendar"   # read-only

# key: (label, range start, range end, signal from, hold minutes)
VARIANTS = {
    "A": ("friend · 30-min range, 15-min hold", (9, 30), (10, 0), (10, 0), 15),
    "B": ("first 5 · 5-min range, 15-min hold", (9, 30), (9, 35), (9, 35), 15),
    "C15": ("premarket 5 · 9:25-9:30 range, 15-min hold", (9, 25), (9, 30), (9, 30), 15),
    "C30": ("premarket 5 · 9:25-9:30 range, 30-min hold", (9, 25), (9, 30), (9, 30), 30),
}

# Fallback when the calendar cannot be read. Full closures and early (13:00 ET) closes.
HOLIDAYS = {
    "2026-11-26", "2026-12-25", "2027-01-01", "2027-01-18", "2027-02-15", "2027-03-26",
    "2027-05-31", "2027-06-18", "2027-07-05", "2027-09-06", "2027-11-25", "2027-12-24",
}
HALF_DAYS = {"2026-11-27", "2026-12-24", "2027-11-26"}


# ---------- time ----------

def at(day, hm):
    """The UTC instant of hh:mm New York time on `day` (a date)."""
    return dt.datetime(day.year, day.month, day.day, hm[0], hm[1], tzinfo=ET).astimezone(dt.timezone.utc)


def bar_time(b):
    return dt.datetime.fromisoformat(str(b["t"]).replace("Z", "+00:00"))


def et_hm(t):
    return t.astimezone(ET).strftime("%H:%M")


# ---------- the rule ----------

def build_range(bars, day, start, end):
    """(high, low, n) over the bars starting in [start, end) ET, or None with no bar there."""
    lo_t, hi_t = at(day, start), at(day, end)
    inside = [b for b in bars if lo_t <= bar_time(b) < hi_t]
    if not inside:
        return None
    return max(b["h"] for b in inside), min(b["l"] for b in inside), len(inside)


def signal(bars, day, rng, sig_from):
    """(side, signal bar) for the first bar from `sig_from`, before 11:00 ET, closing outside."""
    hi, lo = rng[0], rng[1]
    a, cut = at(day, sig_from), at(day, CUTOFF)
    for b in sorted(bars, key=bar_time):
        t = bar_time(b)
        if t < a or t >= cut:
            continue
        if b["c"] > hi:
            return "long", b
        if b["c"] < lo:
            return "short", b
    return None


def entry_exit(bars, sig_bar, hold):
    """(entry bar, exit bar): the first bar after the signal, and the bar ending `hold` minutes
    after the entry (the last bar starting before entry + hold, if a minute is missing)."""
    later = sorted((b for b in bars if bar_time(b) > bar_time(sig_bar)), key=bar_time)
    if not later:
        return None, None
    entry = later[0]
    end = bar_time(entry) + dt.timedelta(minutes=hold)
    held = [b for b in later if bar_time(b) < end]
    # The exit bar must actually have closed at `end` - a feed that stops early is not an exit.
    if not held or bar_time(held[-1]) < end - dt.timedelta(minutes=3):
        return entry, None
    return entry, held[-1]


def bp(a, b):
    return round((b - a) / a * 1e4, 2)


def spread_bp(q):
    if not q or not q.get("bp") or not q.get("ap"):
        return None
    mid = (q["bp"] + q["ap"]) / 2
    return round((q["ap"] - q["bp"]) / mid * 1e4, 2)


def net_bp(side, q_in, q_out):
    """Buy at the ask, sell at the bid. None without both quotes."""
    if not (q_in and q_out and q_in.get("bp") and q_in.get("ap") and q_out.get("bp") and q_out.get("ap")):
        return None
    if side == "long":
        return bp(q_in["ap"], q_out["bp"])
    return round((q_in["bp"] - q_out["ap"]) / q_in["bp"] * 1e4, 2)


def grade(day, key, bars, quotes=None, quote_feed=None, bar_feed="sip"):
    """One variant's row for one day. `quotes` maps an ET minute "HH:MM" to the quote
    snapshotted at the start of that minute."""
    label, r0, r1, sig_from, hold = VARIANTS[key]
    quotes = quotes or {}
    row = dict(id=f"{day.isoformat()}:{key}", day=day.isoformat(), variant=key, label=label,
               symbol=SYMBOL, hold=hold, bar_feed=bar_feed, quote_feed=quote_feed)
    rng = build_range(bars, day, r0, r1)
    if not rng:
        return dict(row, status="no_data", note="no bars in the range")
    row.update(range_hi=rng[0], range_lo=rng[1], range_bars=rng[2])
    sig = signal(bars, day, rng, sig_from)
    if not sig:
        return dict(row, status="no_break")
    side, sb = sig
    entry, exit_ = entry_exit(bars, sb, hold)
    row.update(side=side, signal_min=et_hm(bar_time(sb)), signal_close=sb["c"])
    if not entry or not exit_:
        return dict(row, status="open", note="waiting for the exit bar")
    t_in = bar_time(entry)
    t_out = t_in + dt.timedelta(minutes=hold)
    q_in, q_out = quotes.get(et_hm(t_in)), quotes.get(et_hm(t_out))
    g = bp(entry["o"], exit_["c"]) * (1 if side == "long" else -1)
    s_in, s_out = spread_bp(q_in), spread_bp(q_out)
    return dict(row, status="settled", entry_min=et_hm(t_in), entry=entry["o"],
                exit_min=et_hm(t_out), exit=exit_["c"], gross_bp=round(g, 2),
                bid_in=(q_in or {}).get("bp"), ask_in=(q_in or {}).get("ap"),
                bid_out=(q_out or {}).get("bp"), ask_out=(q_out or {}).get("ap"),
                spread_bp=(round((s_in + s_out) / 2, 2) if s_in is not None and s_out is not None else None),
                net_bp=net_bp(side, q_in, q_out))


def skipped(day, reason):
    return [dict(id=f"{day.isoformat()}:{k}", day=day.isoformat(), variant=k, label=v[0], symbol=SYMBOL,
                 hold=v[4], status="skipped", note=reason) for k, v in VARIANTS.items()]


def session(day, cal=None):
    """'full', 'holiday' or 'half_day' for `day`, from the Alpaca calendar when given."""
    if day.weekday() >= 5:
        return "holiday"
    if cal is not None:
        hit = [c for c in cal if c.get("date") == day.isoformat()]
        if not hit:
            return "holiday"
        return "full" if hit[0].get("close") == "16:00" else "half_day"
    d = day.isoformat()
    return "holiday" if d in HOLIDAYS else "half_day" if d in HALF_DAYS else "full"


def grade_day(day, bars, quotes=None, cal=None, quote_feed=None, bar_feed="sip"):
    kind = session(day, cal)
    if kind != "full":
        return skipped(day, "market holiday" if kind == "holiday" else "half-day (early close)")
    return [grade(day, k, bars, quotes, quote_feed, bar_feed) for k in VARIANTS]


# ---------- the ledger ----------

def load(path=PATH):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {"version": "nasdaq-orb-v1", "rows": []}


def merge(state, rows, now=None):
    """Upsert rows by id. A settled or skipped row is final; anything else may be replaced."""
    by = {r["id"]: r for r in state.get("rows") or []}
    for r in rows:
        old = by.get(r["id"])
        if old and old.get("status") in ("settled", "skipped", "no_break") and r.get("status") not in ("settled", "skipped", "no_break"):
            continue
        by[r["id"]] = r
    state["rows"] = sorted(by.values(), key=lambda r: (r["day"], r["variant"]))
    state["updated"] = (now or dt.datetime.now(dt.timezone.utc)).replace(microsecond=0).isoformat()
    return state


def save(state, path=PATH):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f, indent=1, sort_keys=True)
        f.write("\n")
    os.replace(tmp, path)


def summary(state):
    """Per variant: days decided, trades, win %, mean gross/net/spread, t of net (else gross)."""
    out = {}
    for k, v in VARIANTS.items():
        rows = [r for r in state.get("rows") or [] if r["variant"] == k]
        done = [r for r in rows if r["status"] in ("settled", "no_break")]
        tr = [r for r in rows if r["status"] == "settled"]
        g = [r["gross_bp"] for r in tr]
        n_ = [r["net_bp"] for r in tr if r.get("net_bp") is not None]
        sp = [r["spread_bp"] for r in tr if r.get("spread_bp") is not None]
        base = n_ if n_ else g

        def mean(x):
            return sum(x) / len(x) if x else None

        t = None
        if len(base) >= 2:
            m = mean(base)
            sd = math.sqrt(sum((x - m) ** 2 for x in base) / (len(base) - 1))
            t = round(m / (sd / math.sqrt(len(base))), 2) if sd > 0 else None
        out[k] = dict(label=v[0], days=len(done), trades=len(tr), no_break=len(done) - len(tr),
                      win=(sum(x > 0 for x in g) / len(g)) if g else None,
                      gross=mean(g), net=mean(n_), spread=mean(sp), t=t, t_on="net" if n_ else "gross",
                      skipped=sum(r["status"] == "skipped" for r in rows))
    return out


# ---------- data (read-only) ----------

def _get(url):
    import market_sources as MS
    return MS._get(url, tries=3)


def fetch_bars(day, feed="sip", get=None):
    get = get or _get
    q = dict(timeframe="1Min", start=at(day, (9, 15)).strftime("%Y-%m-%dT%H:%M:%SZ"),
             end=at(day, (11, 45)).strftime("%Y-%m-%dT%H:%M:%SZ"), feed=feed, limit=1000, adjustment="raw")
    return (get(f"{DATA}/v2/stocks/{SYMBOL}/bars?{urllib.parse.urlencode(q)}") or {}).get("bars") or []


def fetch_quote(feed, get=None):
    q = ((get or _get)(f"{DATA}/v2/stocks/{SYMBOL}/quotes/latest?feed={feed}") or {}).get("quote") or {}
    return dict(bp=q.get("bp"), ap=q.get("ap"), t=q.get("t")) if q.get("bp") and q.get("ap") else None


def fetch_calendar(day, get=None):
    try:
        return (get or _get)(f"{CALENDAR}?start={day.isoformat()}&end={day.isoformat()}")
    except Exception:                                           # noqa: BLE001
        return None


def sleep_until(t, now=None, sleeper=time.sleep):
    wait = (t - (now or dt.datetime.now(dt.timezone.utc))).total_seconds()
    if wait > 0:
        sleeper(wait)


def live(day_path, now_fn=None, sleeper=time.sleep, get=None):
    """The VPS run for today: wait for 9:20 ET, snapshot the quote each minute 9:24-11:32 ET,
    then (once the SIP bars are 15 minutes old) grade every variant into `day_path`."""
    now_fn = now_fn or (lambda: dt.datetime.now(dt.timezone.utc))
    day = now_fn().astimezone(ET).date()
    state = load(day_path) if os.path.exists(day_path) else {}
    if state.get("day") != day.isoformat():
        state = {"day": day.isoformat(), "quotes": {}, "rows": []}
    sleep_until(at(day, (9, 20)), now_fn(), sleeper)
    cal = fetch_calendar(day, get)
    kind = session(day, cal)
    if kind != "full":
        state["rows"] = grade_day(day, [], cal=cal)
        save(state, day_path)
        return state
    feed = None
    for f in ("sip", "iex"):                     # SIP is refused on this plan; say which was used
        try:
            fetch_quote(f, get)
            feed = f
            break
        except Exception:                                       # noqa: BLE001
            continue
    state["quote_feed"] = feed
    t = at(day, (9, 24))
    while t <= at(day, (11, 32)):
        sleep_until(t + dt.timedelta(seconds=1), now_fn(), sleeper)
        if feed and now_fn() < t + dt.timedelta(seconds=45):    # a stale snapshot is no quote
            try:
                q = fetch_quote(feed, get)
                if q:
                    state["quotes"][et_hm(t)] = q
            except Exception:                                   # noqa: BLE001
                pass
        save(state, day_path)
        t += dt.timedelta(minutes=1)
    sleep_until(at(day, (11, 49)), now_fn(), sleeper)
    bar_feed, bars = "sip", []
    try:
        bars = fetch_bars(day, "sip", get)
    except Exception:                                           # noqa: BLE001
        bar_feed, bars = "iex", fetch_bars(day, "iex", get)
    state["rows"] = grade_day(day, bars, state["quotes"], cal, feed, bar_feed)
    save(state, day_path)
    return state


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    out = argv[argv.index("--out") + 1] if "--out" in argv else PATH
    if "--live" in argv:
        day_path = argv[argv.index("--live") + 1]
        st = live(day_path)
        for r in st["rows"]:
            print(r["id"], r["status"], r.get("side") or "", r.get("gross_bp", ""), r.get("net_bp", ""))
        return 0
    if "--merge" in argv:
        rows = load(argv[argv.index("--merge") + 1]).get("rows") or []
        save(merge(load(out), rows), out)
        print("merged", len(rows), "rows into", out)
        return 0
    if "--finalize" in argv:                    # a past day from bars alone (no quotes, so no net)
        day = dt.date.fromisoformat(argv[argv.index("--finalize") + 1])
        bars = fetch_bars(day, "sip")
        rows = grade_day(day, bars, {}, fetch_calendar(day))
        save(merge(load(out), rows), out)
        for r in rows:
            print(r["id"], r["status"], r.get("side") or "", r.get("signal_min") or "", r.get("gross_bp", ""))
        return 0
    print("usage: nasdaq_orb.py --live DAYFILE | --merge DAYFILE [--out LEDGER] | --finalize YYYY-MM-DD [--out LEDGER]")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
