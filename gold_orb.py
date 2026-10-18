#!/usr/bin/env python3
"""gold_orb.py — the Gold Asia-open breakout, a Sandbox PAPER lane on Coinbase gold futures.

Paper · never places an order. Nothing here touches Production or the Polymarket/Kalshi executor.

Why (research 2026-10-18, memory gold-asia-open-breakout): a friend's "Asia-open breakout" was
tested on 750 nights of gold minute data. A first pass looked good (+3.0bp/+1.0bp research/holdout
on the 5-minute range), but it filled at the range edge and judged both-sides minutes on their full
high/low, which is look-ahead; re-run look-ahead-free the same cell is +0.9bp (t +0.91) and -1.2bp.
Olu kept the lane anyway as a MEASUREMENT ("build both plans, let's see what turns up"): what do
the two versions really net at Coinbase Derivatives' gold future (GOL-<expiry>-CDE, 1 oz), and
what is that venue's real spread at 8 pm CT? Two pre-registered variants, not retuned:
    A  "friend"  range = the 30-minute candle 7:30-8:00 pm CT (America/Chicago, follows DST)
    B  "5-min"   range = the five minutes 7:55-8:00 pm CT
    signal  the first minute after 8:00 pm that CLOSES above the range high (LONG) or below the
            range low (SHORT), within 60 minutes; decided only once that minute has finished
    entry   the NEXT minute's open
    exit    the close 15 minutes after entry (the close of the 15th minute held); no stop
A's range is the 30-minute candle as a chart draws it, from whatever traded; B keeps its
pre-registered skip, every one of its five minutes must have traded (Coinbase prints a candle only
for a minute with a trade).

Nights are Sunday to Thursday (Chicago dates). Outcomes that are not a trade are logged:
    no_range    B: a minute of 7:55-7:59 has no candle; A: nothing traded 7:30-7:59
    no_break    no minute closed beyond the range by 9:00 pm CT
Two returns a trade, in bp of the entry price and in $ a contract:
    gross   side * (exit - entry), entry at the next minute's open
    net     at the venue: buy at the ask and sell at the bid, at entry and at exit (the book at the
            entry poll and at the exit poll), minus the fee a contract a side on both sides
SHADOW: each variant is also logged from a fixed 01:00 UTC anchor (the China open). Under daylight
time 01:00 UTC IS 8:00 pm CT; from Nov 1 it is 7:00 pm CST, so the anchors split.

The live run (`--run`) is time-critical, so it runs on edge-vps from a user crontab
(scripts/vps_gold_orb.sh), not on GitHub's cron. Olu reviews at 10+ settled nights per variant.
"""
import datetime as dt
import json
import math
import os
import sys
import time
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

ROOT = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(ROOT, "data", "gold_orb_ledger.json")
CT = ZoneInfo("America/Chicago")
UTC = dt.timezone.utc
API = "https://api.coinbase.com/api/v3/brokerage/market/"
CONTRACT = "GOL"                  # Coinbase Derivatives gold futures, GOL-<expiry>-CDE
CONTRACT_OZ = 1
BREAK_MIN, HOLD_MIN = 60, 15
# variant -> (range minutes before the anchor, minutes that must have traded, page name)
VARIANTS = {"A": (30, 1, "A · friend · 30-min range 7:30–8:00 pm"),
            "B": (5, 5, "B · 5-min range 7:55–8:00 pm")}
ANCHOR_CT = (20, 0)               # 8:00 pm America/Chicago
SHADOW_UTC = (1, 0)               # 01:00 UTC, the China open
NIGHTS = (6, 0, 1, 2, 3)          # Sun-Thu, Chicago date
POLL_S = 5
RANGE_GRACE_S = 120               # a 7:59 candle can lag the clock; no_range only after this
# Fee a contract a side, in $. Source: Coinbase Derivatives' fee schedule filed with the CFTC in
# 2024 (cftc.gov/filings/orgrules/rules051624991.pdf), "Gold Futures" $0.10 per side for
# non-professionals, electronic. That is the EXCHANGE fee only: Coinbase Financial Markets' own
# commission is not in it, and the 2026 schedule could not be read. Olu chose this figure.
FEE_PER_SIDE = 0.10
FEE_NOTE = "fee: $0.10/side (CDE 2024 filing, non-professional, exchange fee only)"
READ_AT = 10                      # Olu reviews at 10+ settled nights per variant


# ---------- the clock ----------

def is_night(day):
    return day.weekday() in NIGHTS


def anchors(day):
    """[(anchor key, anchor instant UTC, shadow?)] for the Chicago night `day`."""
    main = dt.datetime(day.year, day.month, day.day, *ANCHOR_CT, tzinfo=CT).astimezone(UTC)
    nxt = day + dt.timedelta(days=1)
    shadow = dt.datetime(nxt.year, nxt.month, nxt.day, *SHADOW_UTC, tzinfo=UTC)
    return [("ct_2000", main, False), ("utc_0100", shadow, True)]


def night_of(now):
    """The Chicago night a run started at `now` belongs to: the evening's date in Chicago."""
    return now.astimezone(CT).date()


# ---------- the rule, on candles ----------

def minute(t):
    return int(t.timestamp()) // 60 * 60


def by_minute(candles):
    """{minute start epoch: candle with float fields} from Coinbase's list (newest first)."""
    out = {}
    for c in candles or []:
        out[int(c["start"])] = {k: float(c[k]) for k in ("open", "high", "low", "close", "volume")}
    return out


def build_range(cm, anchor, variant):
    """(high, low) of the variant's range minutes before `anchor`, or None when fewer than its
    required minutes traded (B: all five; A: any of the thirty)."""
    length, need, _ = VARIANTS[variant]
    a = minute(anchor)
    mins = [a - 60 * i for i in range(length, 0, -1) if a - 60 * i in cm]
    if len(mins) < need:
        return None
    return max(cm[m]["high"] for m in mins), min(cm[m]["low"] for m in mins)


def find_signal(cm, anchor, hi, lo, upto=None):
    """First minute within BREAK_MIN of the anchor that CLOSES beyond the range, over minutes
    starting before `upto` (epoch; the live run passes the current minute so only finished
    minutes count). ("long"|"short", minute epoch) or None."""
    a = minute(anchor)
    for m in range(a, a + 60 * BREAK_MIN, 60):
        if upto is not None and m >= upto:
            break
        c = cm.get(m)
        if not c:
            continue
        if c["close"] > hi:
            return "long", m
        if c["close"] < lo:
            return "short", m
    return None


def entry_minute(signal_m):
    return signal_m + 60


def exit_due(entry_m):
    """The instant the hold ends: HOLD_MIN minutes after the entry minute opens."""
    return entry_m + 60 * HOLD_MIN


def fills(cm, signal_m):
    """(entry, entry_late?, exit, exit_carried?) from the candles, or None before any print.

    Entry is the open of the minute after the signal; if nothing traded in it, the first open
    after it inside the hold (entry_late). Exit is the close of the last minute held (the one
    ending HOLD_MIN minutes after entry opens); if nothing traded in it, the last close before
    (exit_carried)."""
    e = entry_minute(signal_m)
    held = sorted(m for m in cm if e <= m < exit_due(e))
    if held:
        entry, late = cm[held[0]]["open"], held[0] != e
    elif signal_m in cm:
        entry, late = cm[signal_m]["close"], True
    else:
        return None
    last = exit_due(e) - 60
    if last in cm:
        return entry, late, cm[last]["close"], False
    if held:
        return entry, late, cm[held[-1]]["close"], True
    return entry, late, entry, True


def returns(side, entry_px, exit_px, entry_book=None, exit_book=None, fee=FEE_PER_SIDE):
    """Gross and venue-net returns a contract, in $ and bp of the entry price."""
    s = 1 if side == "long" else -1
    gross_usd = s * (exit_px - entry_px) * CONTRACT_OZ
    out = dict(gross_usd=round(gross_usd, 4), gross_bp=round(1e4 * gross_usd / (entry_px * CONTRACT_OZ), 3))
    eb, xb = entry_book or {}, exit_book or {}
    if all(eb.get(k) for k in ("bid", "ask")) and all(xb.get(k) for k in ("bid", "ask")):
        fill_in = eb["ask"] if s == 1 else eb["bid"]
        fill_out = xb["bid"] if s == 1 else xb["ask"]
        net_usd = s * (fill_out - fill_in) * CONTRACT_OZ - 2 * fee
        out.update(fill_in=fill_in, fill_out=fill_out, net_usd=round(net_usd, 4),
                   net_bp=round(1e4 * net_usd / (entry_px * CONTRACT_OZ), 3))
    return out


def spread_bp(book):
    if not book or not book.get("bid") or not book.get("ask"):
        return None
    mid = (book["bid"] + book["ask"]) / 2
    return round(1e4 * (book["ask"] - book["bid"]) / mid, 3)


# ---------- the ledger ----------

def load(path=PATH):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return {"version": "gold-orb-v2", "nights": [], "runs": []}


def save(state, path=PATH):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f, indent=1, sort_keys=True)
        f.write("\n")
    os.replace(tmp, path)


def row_for(state, day, variant, key, anchor, shadow):
    rid = f"{variant}:{key}:{day.isoformat()}"
    for r in state["nights"]:
        if r["id"] == rid:
            return r
    r = dict(id=rid, night=day.isoformat(), variant=variant, anchor=key, anchor_at=anchor.isoformat(),
             shadow=shadow, status="pending")
    state["nights"].append(r)
    return r


def summary(rows):
    """Settled trades: n, win % (net > 0), average gross, net and entry spread in bp, net $, t of net."""
    done = [r for r in rows if r.get("status") == "settled" and r.get("net_bp") is not None]
    n = len(done)
    if not n:
        return dict(n=0, win=None, gross=None, net=None, spread=None, t=None, net_usd=None)
    net = [r["net_bp"] for r in done]
    mean = sum(net) / n
    sd = math.sqrt(sum((x - mean) ** 2 for x in net) / (n - 1)) if n > 1 else 0.0
    spreads = [r["entry_spread_bp"] for r in done if r.get("entry_spread_bp") is not None]
    return dict(n=n, win=sum(x > 0 for x in net) / n, gross=sum(r["gross_bp"] for r in done) / n, net=mean,
                spread=(sum(spreads) / len(spreads) if spreads else None),
                t=(mean / (sd / math.sqrt(n)) if sd > 0 else None),
                net_usd=sum(r["net_usd"] for r in done) / n)


# ---------- one poll: advance a row ----------

def step(row, cm, book, now, product):
    """Advance one variant-anchor row from the candles `cm` and the book seen at `now`.
    Returns True when the row changed."""
    if row["status"] not in ("pending", "ranged", "open"):
        return False
    anchor = dt.datetime.fromisoformat(row["anchor_at"])
    t = now.timestamp()
    a = minute(anchor)
    changed = False
    if row["status"] == "pending":
        if t < a:
            return False
        rng = build_range(cm, anchor, row["variant"])
        if rng is None:
            if t >= a + RANGE_GRACE_S:
                row.update(status="no_range", product=product, settled_at=now.isoformat())
                return True
            return False
        row.update(status="ranged", product=product, range_high=rng[0], range_low=rng[1])
        changed = True
    if row["status"] == "ranged":
        sig = find_signal(cm, anchor, row["range_high"], row["range_low"], upto=minute(now))
        if sig:
            side, m = sig
            # The first poll that sees the finished signal minute is the entry poll: its book is
            # the one an order at the next minute's open would meet.
            row.update(status="open", side=side, signal_at=dt.datetime.fromtimestamp(m, UTC).isoformat(),
                       entry_at=dt.datetime.fromtimestamp(entry_minute(m), UTC).isoformat(),
                       exit_at=dt.datetime.fromtimestamp(exit_due(entry_minute(m)), UTC).isoformat(),
                       entry_book=book, entry_spread_bp=spread_bp(book))
            changed = True
        elif minute(now) >= a + 60 * BREAK_MIN:
            row.update(status="no_break", settled_at=now.isoformat())
            return True
    if row["status"] == "open":
        sm = minute(dt.datetime.fromisoformat(row["signal_at"]))
        if t < exit_due(entry_minute(sm)):
            return changed
        f = fills(cm, sm)
        if f is None:
            return changed
        entry, late, exit_px, carried = f
        row.update(entry_px=entry, entry_late=late, exit_px=exit_px, exit_carried=carried, exit_book=book,
                   exit_spread_bp=spread_bp(book),
                   **returns(row["side"], entry, exit_px, row.get("entry_book"), book))
        row.update(status="settled", settled_at=now.isoformat())
        changed = True
    return changed


# ---------- Coinbase ----------

def get(path, timeout=10):
    req = urllib.request.Request(API + path, headers={"User-Agent": "edge-machine-gold-orb"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def pick_product(products, now):
    """The GOL contract to read: most 24h volume among unexpired ones, nearest expiry on a tie."""
    best = None
    for p in products:
        fd = p.get("future_product_details") or {}
        if fd.get("contract_code") != CONTRACT or p.get("trading_disabled") or p.get("is_disabled"):
            continue
        try:
            exp = dt.datetime.fromisoformat(str(fd.get("contract_expiry")).replace("Z", "+00:00"))
        except ValueError:
            continue
        if exp <= now:
            continue
        key = (-float(p.get("volume_24h") or 0), exp)
        if best is None or key < best[0]:
            best = (key, p["product_id"])
    return best[1] if best else None


def candles(product, start, end, fetch=get):
    q = urllib.parse.urlencode(dict(granularity="ONE_MINUTE", start=int(start.timestamp()), end=int(end.timestamp())))
    return by_minute(fetch(f"products/{product}/candles?{q}").get("candles"))


def book_top(product, fetch=get):
    b = fetch(f"product_book?product_id={product}&limit=5").get("pricebook") or {}
    bid = (b.get("bids") or [{}])[0]
    ask = (b.get("asks") or [{}])[0]
    f = lambda x: float(x) if x not in (None, "") else None
    return dict(bid=f(bid.get("price")), bid_size=f(bid.get("size")), ask=f(ask.get("price")),
                ask_size=f(ask.get("size")), at=b.get("time"))


# ---------- the live run ----------

def run(state, now_fn=lambda: dt.datetime.now(UTC), fetch=get, sleep=time.sleep, path=None, log=print):
    """Watch tonight's two anchors until both are resolved. Writes `path` after each change."""
    start = now_fn()
    day = night_of(start)
    if not is_night(day):
        log(f"{day} ({day:%a}) is not a Sun-Thu night; nothing to do")
        return []
    rows = [row_for(state, day, v, k, a, s) for v in VARIANTS for k, a, s in anchors(day)]
    first = min(dt.datetime.fromisoformat(r["anchor_at"]) for r in rows)
    last = max(dt.datetime.fromisoformat(r["anchor_at"]) for r in rows)
    deadline = last + dt.timedelta(minutes=BREAK_MIN + 1 + HOLD_MIN + 5)
    longest = max(v[0] for v in VARIANTS.values())
    product = pick_product(fetch("products?product_type=FUTURE").get("products") or [], start)
    log(f"night {day} product {product} anchors " + ", ".join(sorted({r["anchor_at"] for r in rows})))
    if not product:
        for r in rows:
            r.update(status="error", error="no GOL contract listed")
        return rows
    errors = 0
    while True:
        now = now_fn()
        if all(r["status"] not in ("pending", "ranged", "open") for r in rows) or now > deadline:
            break
        if now < first - dt.timedelta(seconds=1):
            sleep(min(POLL_S, max(0.5, (first - now).total_seconds())))
            continue
        try:
            cm = candles(product, first - dt.timedelta(minutes=longest + 1), now + dt.timedelta(minutes=1), fetch)
            book = book_top(product, fetch)
            changed = [r for r in rows if step(r, cm, book, now, product)]
            for r in changed:
                log(f"{now:%H:%M:%SZ} {r['id']} -> {r['status']}")
            if changed and path:
                save(state, path)
        except Exception as e:                                    # noqa: BLE001
            errors += 1
            log(f"{now:%H:%M:%SZ} read failed: {str(e)[:120]}")
        sleep(POLL_S)
    for r in rows:
        if r["status"] in ("pending", "ranged", "open"):
            r.update(status="error", error="run ended before the row resolved", settled_at=now_fn().isoformat())
    state["runs"] = (state.get("runs") or [])[-60:] + [dict(at=start.isoformat(), night=day.isoformat(),
                                                             product=product, read_errors=errors,
                                                             statuses={f"{r['variant']}:{r['anchor']}": r["status"] for r in rows})]
    state["last_run"] = now_fn().isoformat()
    return rows


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    out = argv[argv.index("--out") + 1] if "--out" in argv else PATH
    src = argv[argv.index("--from") + 1] if "--from" in argv else out
    if "--run" not in argv:
        st = load(src)
        for v in VARIANTS:
            for k, _a, _s in anchors(dt.date.today()):
                print(v, k, summary([r for r in st["nights"] if r.get("variant") == v and r.get("anchor") == k]))
        return 0
    state = load(src)
    rows = run(state, path=out)
    save(state, out)
    print("done", [(r["id"], r["status"], r.get("net_bp")) for r in rows])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
