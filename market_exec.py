#!/usr/bin/env python3
"""market_exec.py — place the market lane's NEXT-OPEN orders on Alpaca.

market_track.py is a RECORD: it logs what a rule would have done, from bars that have already
printed. It is deliberately retrospective — `scan` refuses to log a signal on the last bar
because the open it would enter at does not exist yet, and `grade` refuses to close a trade
whose exit bar has not printed. That is correct for a research record and useless for trading:
by the time a trade is in the ledger, its entry is in the past.

This module is the other half. It evaluates exactly the two cases the ledger skips —

    ENTRY   a rule's signal fires on the LAST bar          -> buy at the next open
    EXIT    an open trade's exit triggers on the LAST bar  -> sell at the next open

— and places market orders queued for the next open (see TIME_IN_FORCE). Tomorrow market_track will log the same signals
from the bars that by then exist, with the ids this module already used, so the record and the
account describe the same trades and can be compared fill by fill.

THE LEDGER IS NEVER WRITTEN HERE. data/market_ledger.json is the pre-registered record and an
execution bug must not be able to edit it. This module reads it and keeps its own state in
data/market_orders.json.

What it deliberately does NOT trade:

  * `etf_overnight`, which enters at the signal bar's CLOSE. A market-on-close order has to be
    in before 15:50 ET and the daily runner starts at 16:10, after the close it would need to
    trade. Executing it would need its own earlier timer; logging it as skipped is honest,
    quietly entering at the next open instead would be a different rule.
  * the crypto and intraday-day lanes. Crypto never opens, so "the next open" has no meaning,
    and the day lane works off 5-minute bars on a different lifecycle.
  * any rule removed from the board, matching market_track.rule_removed.

Usage:
    python3 market_exec.py                 what WOULD be sent (default: nothing is placed)
    python3 market_exec.py --place         actually send the orders
    python3 market_exec.py --status        account, positions and today's orders
"""
import os, sys, json, uuid, datetime, urllib.request, urllib.error

import market_sources as M
import market_track as T
from zoneinfo import ZoneInfo

_NY = ZoneInfo("America/New_York")

ROOT = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(ROOT, "data", "market_orders.json")

# Paper by default, and loudly. The live host is reachable only by setting ALPACA_LIVE=1, so
# pointing the live account at this takes a deliberate act, not a default nobody re-read.
PAPER_HOST = "https://paper-api.alpaca.markets"
LIVE_HOST = "https://api.alpaca.markets"

# Sizing. Equal notional per position, because the ledger grades every trade as one equally
# weighted result; sizing by conviction here would measure something the record does not.
def _num(env, default):
    """An override from the environment, or the default. Always PRINTED when it differs, because
    a risk limit that changed silently is worse than one that was never there."""
    try:
        v = float(os.environ[env])
        return v if v > 0 else default
    except (KeyError, ValueError):
        return default


# Sizing. Overridable from the environment so going live can start small without a code change
# — the point of readying this now is that switching is one act, not another build.
NOTIONAL_USD = _num("ALPACA_NOTIONAL_USD", 1000.0)
MAX_POSITIONS = int(_num("ALPACA_MAX_POSITIONS", 60))   # 60 x $1000 never needs margin at ~$95k
MAX_NEW_PER_DAY = int(_num("ALPACA_MAX_NEW_PER_DAY", 20))   # a bad data day is not 400 orders

# Loss caps. Checked on every run, in paper as well as live, so the thing that is supposed to
# protect the live account has been exercised for months before it ever sees any.
MAX_DAILY_LOSS_PCT = _num("ALPACA_MAX_DAILY_LOSS_PCT", 3.0)   # v the previous close's equity
MAX_DRAWDOWN_PCT = _num("ALPACA_MAX_DRAWDOWN_PCT", 15.0)      # v a high-water mark kept here

# A BREACH STOPS BUYING AND NEVER STOPS SELLING. A cap that blocked exits would lock the
# account into the losing positions it exists to limit, and each rule's exit is the only thing
# that ends a trade — there is no stop-loss underneath it.

# Namespace for client_order_id. Alpaca rejects a repeat, which is the point: it is the
# exchange-side half of at-most-once, and survives this process dying mid-run.
NS = uuid.UUID("3b2e1f4a-9c7d-5e6b-8a1f-2d4c6e8b0a39")

LANE = "swing"               # the only lane whose entries are "the next open"


def host():
    return LIVE_HOST if os.environ.get("ALPACA_LIVE") == "1" else PAPER_HOST


def live():
    return host() == LIVE_HOST


# Live keys are a SEPARATE pair under their own names in the same 0600 file. Not a switch over
# one pair: a paper key sent to the live host fails with a 401 that reads like an outage, and a
# live key sent to the paper host would quietly trade the wrong account. Keeping them apart
# means the only way to reach the live account is to have deliberately stored a live key AND set
# ALPACA_LIVE=1 — two acts, neither of them a default.
LIVE_KEY_NAMES = ("APCA_LIVE_API_KEY_ID", "APCA_LIVE_API_SECRET_KEY")


def _live_creds():
    path = os.path.expanduser("~/.alpaca-credentials")
    kv = {}
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if "=" in line and not line.startswith("#"):
                    a, b = line.split("=", 1)
                    kv[a.strip()] = b.strip().strip('"').strip("'")
    except OSError:
        return None, None
    return kv.get(LIVE_KEY_NAMES[0]) or None, kv.get(LIVE_KEY_NAMES[1]) or None


def live_configured():
    k, s_ = _live_creds()
    return bool(k and s_)


def _headers():
    if live():
        key, sec = _live_creds()
        if not key:
            raise RuntimeError(
                "ALPACA_LIVE=1 but no live keys stored. Add "
                f"{LIVE_KEY_NAMES[0]} and {LIVE_KEY_NAMES[1]} to ~/.alpaca-credentials. "
                "The paper keys are deliberately not reused for the live host.")
    else:
        key, sec = M._creds()
    if not key:
        raise RuntimeError("no Alpaca credentials")
    return {"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": sec,
            "User-Agent": "edge-machine/1.0", "Accept": "application/json",
            "Content-Type": "application/json"}


def _call(method, path, body=None, timeout=30):
    req = urllib.request.Request(
        host() + path, method=method, headers=_headers(),
        data=json.dumps(body).encode() if body is not None else None)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as f:
            raw = f.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        detail = e.read()[:400].decode("utf-8", "replace")
        raise AlpacaError(e.code, detail) from e


class AlpacaError(Exception):
    def __init__(self, code, detail):
        self.code, self.detail = code, detail
        super().__init__(f"HTTP {code}: {detail}")


def account():
    return _call("GET", "/v2/account")


def positions():
    return {p["symbol"]: p for p in _call("GET", "/v2/positions")}


def open_orders():
    return _call("GET", "/v2/orders?status=open&limit=500")


def clock():
    return _call("GET", "/v2/clock")


def client_order_id(tid, action):
    """Stable per (trade, side). A re-run sends the same id and Alpaca refuses the duplicate."""
    return f"em-{uuid.uuid5(NS, f'{tid}|{action}')}"


# ------------------------------------------------------------------ what to send
def executable_rules(rules=None):
    """The rules this module is allowed to trade, with the reason any is left out."""
    out, skipped = {}, {}
    for name, rule in (rules or T.RULES).items():
        if T.rule_removed(name):
            skipped[name] = "removed from the board"
        elif rule.get("lane") != LANE:
            skipped[name] = f"{rule.get('lane')} lane — the next open does not apply"
        elif rule.get("signal") is None:
            skipped[name] = "no daily signal"
        elif rule.get("entry") == "close":
            skipped[name] = "enters at the close — needs a market-on-close order before 15:50 ET"
        else:
            out[name] = rule
    return out, skipped


def pending_entries(bars_by_symbol, d, rules=None):
    """Signals on the LAST bar — the ones `scan` refuses to log because the open is not in yet.

    The id is the id market_track will give this trade tomorrow, so the order and the record
    line up without a mapping table.
    """
    rules, _ = executable_rules(rules)
    seen = {t["id"] for t in d["trades"]}
    out = []
    for name, rule in rules.items():
        gated = rule.get("universe", "stocks") == "stocks"
        for sym in T.universe_for(rule, list(bars_by_symbol)):
            bars = bars_by_symbol[sym]
            if len(bars) < 210:
                continue
            h = bars                                  # through the last printed bar
            if gated and M.dollar_volume(h[-1]) < M.MIN_DOLLAR_VOLUME:
                continue
            tid = T.trade_id(name, sym, T._day(h[-1]))
            if tid in seen or not rule["signal"](h):
                continue
            out.append(dict(id=tid, rule=name, symbol=sym, action="buy",
                            signal_day=T._day(h[-1]), ref_price=float(h[-1]["c"])))
    return sorted(out, key=lambda x: (x["rule"], x["symbol"]))


def pending_exits(bars_by_symbol, d, rules=None):
    """Open trades whose exit triggered on the LAST bar — `grade` leaves these for tomorrow."""
    rules, _ = executable_rules(rules)
    out = []
    for t in d["trades"]:
        if t["status"] != "open":
            continue
        rule = rules.get(t["rule"])
        if not rule:
            continue
        bars = bars_by_symbol.get(t["symbol"]) or []
        idx = next((i for i, b in enumerate(bars) if T._day(b) == t["entry_day"]), None)
        if idx is None:
            continue
        after = bars[idx + 1:]
        k = rule["exit"](after, dict(hist=bars[:idx + 1]))
        # k is the index of the bar whose CLOSE triggers the exit; the trade leaves at the
        # NEXT open. k + 1 == len(after) is exactly "triggered on the last bar, no open yet".
        if k is None or k + 1 != len(after):
            continue
        out.append(dict(id=t["id"], rule=t["rule"], symbol=t["symbol"], action="sell",
                        entry_day=t["entry_day"], ref_price=float(bars[-1]["c"])))
    return sorted(out, key=lambda x: (x["rule"], x["symbol"]))


def size(intent, cash_left):
    """Whole shares worth about NOTIONAL_USD. Market-on-open does not accept fractions."""
    px = intent.get("ref_price") or 0
    if px <= 0:
        return 0
    qty = int(NOTIONAL_USD // px)
    if qty < 1 or qty * px > cash_left:
        return 0
    return qty


def risk(acct, s):
    """-> (may_buy, [reasons]). Selling is never gated; see MAX_DAILY_LOSS_PCT above."""
    equity = float(acct.get("equity") or 0)
    prev = float(acct.get("last_equity") or 0)
    hwm = max(float(s["meta"].get("high_water") or 0), equity)
    s["meta"]["high_water"] = round(hwm, 2)
    reasons = []
    if prev > 0:
        day = (prev - equity) / prev * 100.0
        if day >= MAX_DAILY_LOSS_PCT:
            reasons.append(f"down {day:.2f}% today, cap {MAX_DAILY_LOSS_PCT:.1f}%")
    if hwm > 0:
        dd = (hwm - equity) / hwm * 100.0
        if dd >= MAX_DRAWDOWN_PCT:
            reasons.append(f"down {dd:.2f}% from the high-water mark, cap {MAX_DRAWDOWN_PCT:.1f}%")
    if acct.get("trading_blocked") or acct.get("account_blocked"):
        reasons.append("the broker has blocked trading on this account")
    return (not reasons), reasons


def plan(bars_by_symbol, d, rules=None, state=None):
    """-> (orders to send, refusals with a named reason). Sells first: they free cash."""
    s = state if state is not None else refresh(load_state())
    mine = held_by_trade(s)
    acct_pos = positions()
    acct = account()
    cash = float(acct.get("cash") or 0)
    may_buy, risk_reasons = risk(acct, s)
    orders, refused = [], []

    # Local state first (cheap, and covers orders still "sending"), then the exchange, which
    # knows about every host.
    ex = exchange_orders()

    def at_exchange(tid, action):
        return ex.get(client_order_id(tid, action))

    def live_at_exchange(tid, action):
        o = at_exchange(tid, action)
        return bool(o) and o.get("status") not in ("canceled", "expired", "rejected")

    sold, bought = committed(s, "sell"), committed(s, "buy")
    for ex_ in pending_exits(bars_by_symbol, d, rules):
        if ex_["id"] in sold or live_at_exchange(ex_["id"], "sell"):
            refused.append(dict(ex_, reason="a sell for this trade is already placed"))
            continue
        q = mine.get(ex_["id"])
        if not q:
            # Not in this host's file — ask the broker whether the buy filled anywhere.
            bo = at_exchange(ex_["id"], "buy")
            q = int(float((bo or {}).get("filled_qty") or 0)) or None
        if not q:
            # The ledger is in this trade and this module never filled it. Normal while the
            # account catches up with a record that started months earlier; never silent.
            refused.append(dict(ex_, reason="never bought, here or at the broker"))
            continue
        # Never sell more of a symbol than the account actually holds, however the per-trade
        # arithmetic came out.
        in_acct = abs(int(float((acct_pos.get(ex_["symbol"]) or {}).get("qty") or 0)))
        if in_acct < q:
            refused.append(dict(ex_, reason=f"account holds {in_acct}, trade wants {q}"))
            continue
        orders.append(dict(ex_, qty=q))

    n_open = len(bought - committed(s, "sell"))
    new = 0
    for en in pending_entries(bars_by_symbol, d, rules):
        if not may_buy:
            refused.append(dict(en, reason="LOSS CAP: " + "; ".join(risk_reasons)))
            continue
        if en["id"] in bought or live_at_exchange(en["id"], "buy"):
            refused.append(dict(en, reason="already bought or queued"))
            continue
        if n_open + new >= MAX_POSITIONS:
            refused.append(dict(en, reason=f"position cap ({MAX_POSITIONS})"))
            continue
        if new >= MAX_NEW_PER_DAY:
            refused.append(dict(en, reason=f"daily new-order cap ({MAX_NEW_PER_DAY})"))
            continue
        qty = size(en, cash)
        if qty < 1:
            refused.append(dict(en, reason="one share costs more than the per-trade notional"
                                            if (en["ref_price"] or 0) > NOTIONAL_USD
                                            else "not enough cash left"))
            continue
        orders.append(dict(en, qty=qty))
        cash -= qty * en["ref_price"]
        new += 1
    return orders, refused


# TIME IN FORCE: "day", not "opg" (2026-10-12). Two things went wrong with market-on-open:
#   * Alpaca accepts an opg order only between 19:00 and 09:28 ET. The daily job runs at 16:10
#     ET, so every order it sent on 2026-10-12 came back HTTP 403, 11 of 11.
#   * The opg orders that WERE accepted (14, sent 04:01 ET that Monday) mostly expired at the
#     open: paper filled 3 of 14 in its opening auction and let 11 lapse unfilled.
# A market "day" order sent after the close is queued and goes in at the next session's open,
# so the 16:10 job can stay where it is, and it fills at the first trade rather than gambling on
# the paper auction. The record still enters at the bar's open; --reconcile measures the gap
# between that and the fill, so the difference is reported, not hidden.
# ALPACA_TIF=opg brings market-on-open back; it is then refused outside its window by name.
TIME_IN_FORCE = os.environ.get("ALPACA_TIF", "day").strip().lower()
if TIME_IN_FORCE not in ("day", "opg"):
    TIME_IN_FORCE = "day"


def opg_window_open(now=None):
    """True between 19:00 and 09:28 New York time, the only hours Alpaca takes an opg order."""
    now = now or datetime.datetime.now(datetime.timezone.utc)
    t = now.astimezone(_NY).time()
    return t >= datetime.time(19, 0) or t < datetime.time(9, 28)


def submit(order):
    """One market order for the next open: a queued day order, or opg when ALPACA_TIF=opg."""
    body = {"symbol": order["symbol"], "qty": str(order["qty"]), "side": order["action"],
            "type": "market", "time_in_force": TIME_IN_FORCE,
            "client_order_id": client_order_id(order["id"], order["action"])}
    return _call("POST", "/v2/orders", body)


# ------------------------------------------------------------------ state
def exchange_orders(days=120):
    """{client_order_id: order} from Alpaca — the shared truth about what has been sent.

    data/market_orders.json is PER HOST and deliberately not committed, so it cannot answer
    "has this trade been bought?" for an order some other machine placed. The client_order_id
    is a pure function of (trade id, side), so the broker's own order list answers it for every
    host at once. Without this, an order placed from a laptop would never be sold by the VPS:
    the sell would be refused as "never bought by this module", and the position would sit
    there while the ledger recorded a clean exit.
    """
    after = (datetime.date.today() - datetime.timedelta(days=days)).isoformat()
    out, page = {}, None
    while True:
        q = f"/v2/orders?status=all&limit=500&direction=desc&after={after}"
        if page:
            q += "&page_token=" + page
        rows = _call("GET", q)
        if not rows:
            break
        for r in rows:
            cid = r.get("client_order_id")
            if cid and cid.startswith("em-"):
                out.setdefault(cid, r)
        if len(rows) < 500:
            break
        page = rows[-1]["id"]
    return out


def refresh(s):
    """Update every non-terminal order from Alpaca, so `held` counts FILLS and not intentions.

    A market-on-open order can be accepted the evening before and still not fill — the open
    gaps past a halt, the symbol stops trading. Counting an accepted order as a position would
    make this module sell shares it never owned.
    """
    for o in s["orders"]:
        if o.get("status") not in ("accepted", "sending") or not o.get("client_order_id"):
            continue
        try:
            r = _call("GET", "/v2/orders:by_client_order_id?client_order_id=" + o["client_order_id"])
        except AlpacaError:
            continue
        o["order_status"] = r.get("status")
        o["filled_qty"] = int(float(r.get("filled_qty") or 0))
        o["filled_avg_price"] = float(r.get("filled_avg_price") or 0) or None
        if r.get("status") in ("filled", "canceled", "expired", "rejected", "done_for_day"):
            o["status"] = "filled" if o["filled_qty"] else "unfilled"
    return s


# Two different questions, and conflating them is how an order gets sent twice.
LIVE_STATUS = ("sending", "accepted", "filled", "duplicate")   # exists at the exchange


def committed(s, action):
    """Trade ids that already have a live or filled order on this side.

    A market-on-open order sits "accepted" and unfilled from the evening it is sent until the
    open — zero shares held, but very much a real order. Planning against SHARES would re-plan
    it every run; only the client_order_id would stop the second send, and the dry run would
    be describing orders it is not going to place.
    """
    return {o["id"] for o in s["orders"]
            if o.get("action") == action and o.get("status") in LIVE_STATUS}


def held_by_trade(s):
    """{trade_id: shares} actually FILLED, per TRADE — not per symbol.

    Two rules can be long the same name at once; the ledger logs them as separate trades and
    grades them separately, so one rule leaving must sell ITS shares and leave the other's
    alone. Selling the account's whole position would close a trade the record still has open,
    and nothing downstream would notice.

    Fills only: an accepted order is not a position, and selling against one would be selling
    shares that may never arrive.
    """
    qty = {}
    for o in s["orders"]:
        if o.get("status") != "filled":
            continue
        n = int(o.get("filled_qty") or 0)
        qty[o["id"]] = qty.get(o["id"], 0) + (n if o["action"] == "buy" else -n)
    return {k: v for k, v in qty.items() if v > 0}


def load_state():
    try:
        with open(STATE) as f:
            s = json.load(f)
    except (OSError, ValueError):
        s = {}
    s.setdefault("orders", [])
    s.setdefault("meta", {})
    return s


def save_state(s):
    s["meta"]["updated"] = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    s["meta"]["host"] = host()
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    tmp = STATE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(s, f, indent=1, sort_keys=True)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, STATE)


def place(orders, dry_run=True):
    """Send the orders. A claim is written BEFORE each send, so a crash cannot re-send."""
    s = load_state()
    # A FAILED send never reached the broker, so it is not a claim: on 2026-10-12 all 11 orders
    # failed on the opg window and this set would have refused every one of them forever.
    done = {(o["id"], o["action"]) for o in s["orders"] if o.get("status") != "failed"}
    sent, failed = [], []
    for o in orders:
        if (o["id"], o["action"]) in done:
            continue
        if dry_run:
            sent.append(dict(o, status="dry_run"))
            continue
        if TIME_IN_FORCE == "opg" and not opg_window_open():
            failed.append(dict(o, status="failed",
                               error="not sent: opg orders are taken only 19:00-09:28 ET"))
            continue
        rec = dict(o, client_order_id=client_order_id(o["id"], o["action"]),
                   sent_at=datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"))
        s["orders"].append(dict(rec, status="sending"))
        save_state(s)                                  # claim first, then send
        try:
            res = submit(o)
            s["orders"][-1].update(status="accepted", alpaca_id=res.get("id"),
                                   order_status=res.get("status"))
            sent.append(s["orders"][-1])
        except AlpacaError as e:
            # 422 on a duplicate client_order_id is the dedupe working, not a failure.
            dup = e.code == 422 and "client_order_id" in (e.detail or "")
            s["orders"][-1].update(status="duplicate" if dup else "failed", error=str(e)[:300])
            (sent if dup else failed).append(s["orders"][-1])
        save_state(s)
    return sent, failed


# ------------------------------------------------------------------ reconciliation
FILLS = os.path.join(ROOT, "data", "market_fills.json")


def _bps(a, b):
    """(a - b) / b in basis points. None if b is not a usable price."""
    try:
        return round((float(a) - float(b)) / float(b) * 10_000, 2)
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def reconcile(d=None, days=120):
    """Compare what the broker FILLED against what the ledger RECORDED. -> a report dict.

    The whole record is costed at market_sources.COST_BPS_PER_SIDE — 5bp a side, assumed. Every
    net return and every verdict rests on that number being roughly right, and until now nothing
    measured it. This does: the ledger's entry is a bar's open, the fill is what the account
    actually paid, and the gap between them is the real cost of crossing.

    Expect the gap to be larger than pure slippage, and say so rather than calling it slippage.
    Bars come from the free IEX feed, so the "open" in the ledger is IEX's first print, while a
    market-on-open order executes in the primary exchange's opening auction. Part of what this
    measures is that difference — which is just as important, because it is the error in the
    prices the record is built from.

    It also answers an integrity question the cost model does not: is there a fill with no trade
    behind it? market_exec and market_track are supposed to partition the signals exactly. An
    orphan fill means they have drifted, and that is the failure that would otherwise be silent.
    """
    d = d if d is not None else T.load()
    ex = exchange_orders(days)
    by_trade = {t["id"]: t for t in d["trades"]}
    seen, rows, orphans = set(), [], []

    for tid, t in by_trade.items():
        for side, ledger_px, day_key in (("buy", t.get("entry"), "entry_day"),
                                         ("sell", t.get("exit"), "exit_day")):
            cid = client_order_id(tid, side)
            o = ex.get(cid)
            if not o:
                continue
            seen.add(cid)
            qty = int(float(o.get("filled_qty") or 0))
            if qty <= 0:
                rows.append(dict(id=tid, rule=t.get("rule"), symbol=t.get("symbol"), side=side,
                                 status=o.get("status"), ledger=ledger_px, fill=None, slip_bps=None,
                                 qty=0))
                continue
            fill = float(o.get("filled_avg_price") or 0) or None
            # Adverse is POSITIVE on both sides: paying above the recorded open, or selling
            # below it, both cost money. One signed number that means the same thing either way.
            slip = None
            if fill and ledger_px:
                raw = _bps(fill, ledger_px)
                slip = raw if side == "buy" else (None if raw is None else -raw)
            rows.append(dict(id=tid, rule=t.get("rule"), symbol=t.get("symbol"), side=side,
                             status=o.get("status"), ledger=ledger_px, fill=fill, slip_bps=slip,
                             qty=qty,
                             filled_at=(o.get("filled_at") or "")[:19],
                             day=t.get(day_key)))

    # Orders this module placed that no ledger trade claims yet. Two very different cases, and
    # collapsing them would hide the one that matters:
    #   IN FLIGHT  placed, not filled, not yet in the record. The normal state between sending
    #              an order in the evening and market_track logging it after the next close.
    #   ORPHAN     FILLED, and still nothing in the record. The ids are a pure function of the
    #              trade, so this is not a naming mismatch — it is a position the record does
    #              not know about, which is exactly the drift this whole split is meant to
    #              prevent.
    in_flight = []
    for cid, o in ex.items():
        if cid in seen:
            continue
        row = dict(client_order_id=cid, symbol=o.get("symbol"), side=o.get("side"),
                   qty=int(float(o.get("filled_qty") or o.get("qty") or 0)),
                   price=float(o.get("filled_avg_price") or 0) or None,
                   status=o.get("status"), filled_at=(o.get("filled_at") or "")[:19])
        # An expired/canceled order can still own shares (e.g. SWKS filled 11/13).
        # The broker's executed quantity, not the terminal status, determines a fill.
        if float(o.get("filled_qty") or 0) > 0:
            orphans.append(row)
        elif o.get("status") not in ("canceled", "expired", "rejected"):
            in_flight.append(row)

    done = [r for r in rows if r.get("slip_bps") is not None]
    per_rule = {}
    for r in done:
        per_rule.setdefault(r["rule"], []).append(r["slip_bps"])
    summary = dict(
        fills=len(done), unfilled=len([r for r in rows if not r.get("qty")]),
        orphans=len(orphans), in_flight=len(in_flight),
        assumed_bps_per_side=M.COST_BPS_PER_SIDE,
        mean_bps=round(sum(x["slip_bps"] for x in done) / len(done), 2) if done else None,
        median_bps=(sorted(x["slip_bps"] for x in done)[len(done) // 2] if done else None),
        worst_bps=max((x["slip_bps"] for x in done), default=None),
        best_bps=min((x["slip_bps"] for x in done), default=None),
        by_rule={k: dict(n=len(v), mean_bps=round(sum(v) / len(v), 2)) for k, v in sorted(per_rule.items())},
    )
    return dict(summary=summary, rows=sorted(rows, key=lambda r: (r.get("day") or "", r["id"])),
                orphans=orphans, in_flight=in_flight)


def save_fills(rep):
    rep = dict(rep, updated=datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"))
    os.makedirs(os.path.dirname(FILLS), exist_ok=True)
    tmp = FILLS + ".tmp"
    with open(tmp, "w") as f:
        json.dump(rep, f, indent=1, sort_keys=True)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, FILLS)


def print_reconcile(rep):
    s = rep["summary"]
    print(f"fills     : {s['fills']} matched, {s['unfilled']} not filled, "
          f"{s.get('in_flight', 0)} in flight, {s['orphans']} orphan")
    if not s["fills"]:
        print("            nothing filled yet — nothing to measure"
              + (f" ({s.get('in_flight', 0)} order(s) placed and waiting for an open)"
                 if s.get("in_flight") else ""))
    else:
        print(f"cost      : assumed {s['assumed_bps_per_side']:.1f}bp/side  |  "
              f"measured mean {s['mean_bps']:+.2f}bp  median {s['median_bps']:+.2f}bp  "
              f"(worst {s['worst_bps']:+.2f}, best {s['best_bps']:+.2f})")
        print("            positive = adverse (paid above, or sold below, the recorded open)")
        over = s["mean_bps"] is not None and s["mean_bps"] > s["assumed_bps_per_side"]
        if over:
            print(f"            *** measured cost EXCEEDS the {s['assumed_bps_per_side']:.1f}bp "
                  f"the record is costed at — net returns are optimistic ***")
        for rule, v in s["by_rule"].items():
            print(f"    {rule:24} n {v['n']:4}  mean {v['mean_bps']:+7.2f}bp")
    if rep["orphans"]:
        # Not a cost problem. market_exec and market_track are meant to partition the signals
        # exactly, so a fill with no trade behind it means they have drifted apart.
        print(f"ORPHANS   : {len(rep['orphans'])} fill(s) with no trade in the ledger — "
              f"the account and the record have drifted")
        for o in rep["orphans"][:10]:
            print(f"    {o['side']:4} {o['symbol']:6} {o['qty']:>5} @ {o['price']}  {o['filled_at']}")


# ------------------------------------------------------------------ cli
def _fetch_bars():
    syms = M.universe()
    start = (datetime.date.today() - datetime.timedelta(days=500)).isoformat()
    return M.bars(sorted(set(syms + [T.BENCH] + M.ETFS)), "1Day", start=start)


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    if not M.configured():
        print("no Alpaca credentials (~/.alpaca-credentials) — nothing to do")
        return 0

    if "--live-check" in argv:
        # Read-only. Says whether the live path WOULD work, and places nothing whatever happens.
        print("live readiness")
        ok = True
        if not live_configured():
            print(f"  NO    live keys: add {LIVE_KEY_NAMES[0]} and {LIVE_KEY_NAMES[1]} to "
                  f"~/.alpaca-credentials (0600)")
            ok = False
        else:
            print("  yes   live keys are stored")
            prev = os.environ.get("ALPACA_LIVE")
            os.environ["ALPACA_LIVE"] = "1"
            try:
                a = account()
                eq, cash = float(a.get("equity") or 0), float(a.get("cash") or 0)
                print(f"  yes   live account reachable: {a.get('status')} "
                      f"equity=${eq:,.2f} cash=${cash:,.2f}")
                if a.get("trading_blocked") or a.get("account_blocked"):
                    print("  NO    the broker has trading BLOCKED on this account")
                    ok = False
                if cash < NOTIONAL_USD:
                    print(f"  NO    cash ${cash:,.2f} is under one position (${NOTIONAL_USD:,.2f}) "
                          f"— fund it, or lower ALPACA_NOTIONAL_USD")
                    ok = False
                n = int(cash // NOTIONAL_USD) if NOTIONAL_USD else 0
                print(f"        at ${NOTIONAL_USD:,.0f} a position that funds {n} of the "
                      f"{MAX_POSITIONS}-position cap")
            except Exception as e:
                print(f"  NO    live account unreachable: {type(e).__name__}: {str(e)[:160]}")
                ok = False
            finally:
                if prev is None:
                    os.environ.pop("ALPACA_LIVE", None)
                else:
                    os.environ["ALPACA_LIVE"] = prev
        live_on = os.environ.get("ALPACA_LIVE") == "1"
        print(f"  {'LIVE ' if live_on else 'no   '} ALPACA_LIVE is {'SET — this host trades LIVE' if live_on else 'not set, so every run is paper'}")
        print(f"        caps: ${NOTIONAL_USD:,.0f}/trade, {MAX_POSITIONS} positions, "
              f"{MAX_NEW_PER_DAY} new/day, loss {MAX_DAILY_LOSS_PCT:.1f}%/day "
              f"{MAX_DRAWDOWN_PCT:.1f}% drawdown")
        print(f"\n{'READY — arm with Environment=ALPACA_LIVE=1 in edge-market.service' if ok else 'NOT READY'}")
        return 0 if ok else 1

    if "--reconcile" in argv:
        rep = reconcile()
        print_reconcile(rep)
        save_fills(rep)
        print(f"written   : {os.path.relpath(FILLS, ROOT)}")
        return 0

    if "--status" in argv:
        a = account()
        print(f"host      : {host()}{'  *** LIVE ***' if live() else '  (paper)'}")
        print(f"account   : {a.get('status')} cash=${float(a.get('cash') or 0):,.2f} "
              f"equity=${float(a.get('equity') or 0):,.2f}")
        held = positions()
        print(f"positions : {len(held)}")
        for sym, p in sorted(held.items())[:20]:
            print(f"    {sym:6} {p['qty']:>8} @ {float(p['avg_entry_price']):>9.2f}  "
                  f"P/L {float(p['unrealized_pl']):+.2f}")
        oo = open_orders()
        print(f"open orders: {len(oo)}")
        for o in oo[:20]:
            print(f"    {o['symbol']:6} {o['side']:4} {o['qty']:>6} {o['type']}/{o['time_in_force']} "
                  f"{o['status']}")
        return 0

    dry = "--place" not in argv
    rules_ok, skipped = executable_rules()
    print(f"host      : {host()}{'  *** LIVE ***' if live() else '  (paper)'}")
    od = [f"{k}={os.environ[k]}" for k in
          ("ALPACA_NOTIONAL_USD", "ALPACA_MAX_POSITIONS", "ALPACA_MAX_NEW_PER_DAY",
           "ALPACA_MAX_DAILY_LOSS_PCT", "ALPACA_MAX_DRAWDOWN_PCT") if k in os.environ]
    if od:
        print(f"overrides : {', '.join(od)}")
    print(f"rules     : {len(rules_ok)} executable — {', '.join(sorted(rules_ok))}")
    for name, why in sorted(skipped.items()):
        print(f"    skip  {name:22} {why}")

    d = T.load()
    bars = _fetch_bars()
    print(f"bars      : {len(bars)} symbols, through {max((T._day(b[-1]) for b in bars.values() if b), default='?')}")

    st = refresh(load_state())
    ok_buy, why = risk(account(), st)
    save_state(st)
    if not ok_buy:
        print(f"LOSS CAP  : buying halted — {'; '.join(why)}  (exits are never gated)")
    orders, refused = plan(bars, d, state=st)
    buys = [o for o in orders if o["action"] == "buy"]
    sells = [o for o in orders if o["action"] == "sell"]
    print(f"planned   : {len(sells)} sell, {len(buys)} buy"
          f"{'   (DRY RUN — nothing sent; use --place)' if dry else ''}")
    for o in sells + buys:
        print(f"    {o['action']:4} {o['symbol']:6} {o['qty']:>5} @ ~{o['ref_price']:.2f}  "
              f"[{o['rule']}]")
    if refused:
        print(f"refused   : {len(refused)}")
        for r in refused[:20]:
            print(f"    {r['action']:4} {r['symbol']:6} {r['reason']}")

    sent, failed = place(orders, dry_run=dry)
    if not dry:
        print(f"sent      : {len(sent)} accepted, {len(failed)} failed")
        for f in failed:
            print(f"    FAILED {f['symbol']} {f.get('error')}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
