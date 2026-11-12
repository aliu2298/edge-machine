"""fillsim: ONE honest fill simulator for every paper lane (2026-11-12, Olu: the paper v live gap).

Paper lanes each carried their own fill rule and the rules disagreed (a touch fills / only a print through the bid fills; any print
sells / 50 contracts sell; a 60 second wait or none). Lanes that looked good on paper lost live: the over 3.5 cheap NO sold on
prints that landed seconds after its fill, AAA gas daily sold on opening-minute prints from before its entry, the Album lanes
bought at asks nobody could trade. This module is the one place those rules now live. It is pure: it reads trade prints and
returns what an order would have done. No network, no ledger, no lane knowledge.

WHAT IT MODELS (rule set "honest-v1")

  Trade prints, not candles and not the bid. A print is (time, YES price, contracts, taker side). Kalshi's taker side says who
  crossed the spread: "yes" = the taker bought YES from a resting YES offer, "no" = the taker sold YES into a resting YES bid.
  Block trades are dropped (they never touch the book).

  TAKER BUY at a quoted ask. The ask must have been real: enough contracts bought at or under it within 60 minutes (10, or the
  order's own size if larger), and the ask not under half the last trade before it. Only prints where the taker BOUGHT our side
  count: a sale into a bid at that price shows a bid, not an offer.

  RESTING BUY at a limit (post-only).
    crossed    the price was already at or through the limit when the order went up: the exchange refuses a post-only order that
               would cross, so there is no entry (the quote at that minute if the lane has one, else the last print before it).
    through    a print strictly through the limit fills us first, whoever the taker was: nobody sells lower while a better bid rests.
    offer      a print AT the limit where the taker bought from a resting offer at our price: no bid stood at that price (the
               offer would have traded with it), so our bid would have been alone there and that seller meets us. Off in
               honest-v1 (Rules.offer_fills): sound on paper, but no live fill has shown it yet.
    queue      a print AT the limit where the taker sold into bids at our price: those bids were ahead of us. We fill only after
               `queue_ahead` contracts have traded there. In honest-v1 that is never: see CALIBRATION.
  Fills are sized: an order for 10 fills 10 only when 10 contracts' worth of those prints came. Under that it is partial.

  RESTING SELL at a target = a resting buy of the other side at 1 - target, so the same four cases apply, mirrored. A sell posted
  after a fill counts prints only from `latency_s` after that fill (the order is not up before then). A target the price is
  already through when the sell goes up is "crossed": it is sold as a taker at the target, not as a resting order, and only once
  a later print confirms the price was still there (a flash print seconds after the fill confirms nothing).

  FEES are the exchange's, read from the live fills (live_record_publish.py): a taker pays 0.07 x p x (1 - p) per contract rounded
  UP to $0.0001; a resting fill pays nothing; settlement pays nothing.

WHAT IT DOES NOT MODEL: other traders reacting to our order, the true queue at a price, and outages.

CALIBRATION (fillsim_calibrate.py, 2026-11-12, on the follower's own posted bids and sell legs; picked on half the tickers, checked
on the other half).
  resting buys   190 posted bids, 96 live fills. "Only a print strictly through the bid fills" calls 98.9% right on half A and
                 97.0% on half B. Counting touches adds two fills the tape shows, and both are the follower's OWN fill (the only
                 contracts that traded at that price), so they prove nothing. The one touch that was not ours (ATHRSO, Nov 1:
                 13.7 contracts traded at exactly 10c) did not fill live.
  resting sells  224 YES-split legs resting from the tip, 120 sold live. Strictly-through calls 97.3% right on both halves. Seven
                 legs only touched their target: six sold live, one did not. Half A alone would pick "a touch fills" (100%), but
                 those six matches are again our own prints. So in a thin book an early order often does fill on a touch, and
                 strictly-through misses about 1 live sell in 20 there: the simulator errs toward fewer fills. TOUCH (below) is
                 the other bracket; live results have landed between the two.
  the wait       116 sells posted after a live fill, 80 sold. No wait: 95.8% right, with 3 false sells on the over 3.5 lane
                 (prints seconds after the fill). 5 to 120 seconds tie on half A (98.1%); 30 to 120 seconds leave one false sell
                 (KASBES, a known executor fault). 60 seconds, the lanes' existing rule, sits inside that band and is kept.
So honest-v1 is: queue_ahead = infinite (a touch never fills), offer_fills off (no live case decided it), latency 60 s. The queue
and offer cases stay in the code for a lane that can show its own queue (a saved book).
"""
import bisect
import dataclasses
import datetime as dt
import math

VERSION = "honest-v1"
EPS = 1e-9


@dataclasses.dataclass(frozen=True)
class Rules:
    name: str = VERSION
    taker_rate: float = 0.07           # taker fee = rate x p x (1 - p) per contract ...
    maker_rate: float = 0.0            # ... a resting fill pays nothing (every resting fill on file: fee_cost 0)
    fee_grid: float = 0.0001           # ... rounded up to this, per contract
    entry_window_s: int = 3600         # a taker entry's ask must trade inside this window after the quote
    entry_min_n: float = 10.0          # ... with at least this many contracts (or the order's size if larger)
    last_trade_floor: float = 0.5      # ... and the ask must not sit under this share of the last trade before it
    queue_ahead: float = math.inf      # contracts ahead of a resting order at its own price. inf = a touch never fills (calibrated)
    latency_s: float = 60.0            # a follow-up order (a sell after a fill) is up this long after the fill (calibrated)
    cross_lookback_s: int = 5400       # with no quote, the last print this recent says where the price stood when the order went up
    offer_fills: bool = False          # the "offer" case above; off = every print at the limit waits in the queue
    taker_side_entry: bool = True      # a taker entry counts only prints where the taker bought its side
    unconfirmed_ok: bool = False       # a taker entry the prints can neither confirm nor refute still counts (QUOTED, below)
    entry_drift: float = 0.05          # ... unless every print in the window sat more than this above the ask (the price had moved)


HONEST = Rules()
# Buy-and-hold lanes that log a live two-sided quote (the tracker, the rule ledgers, the dailies). Their logged ask is taken as real
# unless the prints REFUTE it: on 101 tracker bets that really filled live, the 10-contract print test confirmed only 86, because
# nobody takes the 90c side of a favourite; and on 366 live bets the price paid was within 0.3c of the price logged.
QUOTED = dataclasses.replace(HONEST, unconfirmed_ok=True)
# The upper bracket: every print at the order's price fills it, as if it stood first in the queue. Live fills sit between the two.
TOUCH = dataclasses.replace(HONEST, name="touch", queue_ahead=0.0)


# ---------------------------------------------------------------- prints
def _ts(raw):
    if isinstance(raw, (int, float)):
        return float(raw)
    s = str(raw).replace("Z", "+00:00")
    return dt.datetime.fromisoformat(s).timestamp()


def _num(v):
    try:
        return None if v is None else float(v)
    except (TypeError, ValueError):
        return None


def prints_from_trades(trades):
    """[(ts, yes price, contracts, taker side)] oldest first, from Kalshi /markets/trades rows. Block trades are dropped."""
    out = []
    for i, t in enumerate(trades or []):
        if t.get("is_block_trade"):
            continue
        yes, no = _num(t.get("yes_price_dollars")), _num(t.get("no_price_dollars"))
        if yes is None and no is not None:
            yes = 1 - no
        n = _num(t.get("count_fp"))
        if n is None:
            n = _num(t.get("count")) or 0.0
        if yes is None or not t.get("created_time") or n <= 0:
            continue
        taker = t.get("taker_side")
        out.append((_ts(t["created_time"]), round(yes, 4), n, taker if taker in ("yes", "no") else None, -i))
    out.sort(key=lambda p: (p[0], p[4]))          # the API serves newest first: inside one instant, keep the exchange's order
    return [p[:4] for p in out]


def as_prints(rows, side="yes"):
    """A lane's own [(ts, price, contracts)] rows (priced on `side`, no taker side) as fillsim prints."""
    return sorted((float(t), round(px if side == "yes" else 1 - px, 4), float(n), None) for t, px, n in rows)


def other(side):
    return "no" if side == "yes" else "yes"


def px_of(p, side):
    """A print's price on `side`."""
    return p[1] if side == "yes" else round(1 - p[1], 4)


def _from(prints, ts):
    """Index of the first print at or after ts."""
    return bisect.bisect_left(prints, (ts,))


# ---------------------------------------------------------------- fees
def fee(price, qty=1.0, taker=True, rules=HONEST):
    """The exchange's fee on `qty` contracts at `price`: per contract, rounded up to the fee grid."""
    rate = rules.taker_rate if taker else rules.maker_rate
    if rate <= 0 or not 0 < price < 1:
        return 0.0
    per = math.ceil(round(rate * price * (1 - price) / rules.fee_grid, 9)) * rules.fee_grid
    return round(per * qty, 6)


def stake_qty(price, stake=1.0):
    """Whole contracts a `stake` buys at `price`, never under one (the follower's sizing)."""
    return float(max(1, math.floor(stake / price + EPS))) if price > 0 else 0.0


# ---------------------------------------------------------------- taker orders
def taker_buy(prints, ts, ask, side="yes", qty=1.0, rules=HONEST, book_size=None):
    """Was `ask` on `side` at time `ts` a price an order for `qty` could really have paid?

    -> dict(ok, status verified | unverified | unconfirmed | refuted, how, reason, printed, need, last_trade). `book_size`: contracts
    offered at or under the ask in a book read AT the entry (a live lane), which verifies on its own when it covers the order.
    Under a rule set with unconfirmed_ok (QUOTED), an ask the prints do not confirm still counts ("unconfirmed") unless they refute
    it: it sat under half the last trade, or every trade in the window was more than entry_drift above it."""
    need = max(rules.entry_min_n, qty)
    i = _from(prints, ts)
    last = px_of(prints[i - 1], side) if i > 0 else None
    out = dict(ok=False, status="unverified", ask=ask, need=need, last_trade=last, printed=None)
    if last is not None and ask < rules.last_trade_floor * last - EPS:
        return dict(out, reason=f"ask {ask:.2f} under half the last trade {last:.2f}")
    if book_size is not None and book_size >= need - EPS:
        return dict(out, ok=True, status="verified", how="book")
    printed = 0.0
    for p in prints[i:]:
        if p[0] <= ts:
            continue
        if p[0] > ts + rules.entry_window_s:
            break
        bought = p[3] is None or p[3] == side or not rules.taker_side_entry
        if bought and px_of(p, side) <= ask + EPS:
            printed += p[2]
    out["printed"] = round(printed, 2)
    if printed >= need - EPS:
        return dict(out, ok=True, status="verified", how="print")
    mins = rules.entry_window_s // 60
    why = f"{printed:g} contracts bought at or under the ask within {mins} minutes (under {need:g})"
    if not rules.unconfirmed_ok:
        return dict(out, reason=why)
    seen = [px_of(p, side) for p in prints[i:] if ts < p[0] <= ts + rules.entry_window_s]
    if seen and min(seen) > ask + rules.entry_drift + EPS:
        return dict(out, status="refuted", reason=f"every trade in the window was above {ask + rules.entry_drift:.2f}: the price had moved")
    return dict(out, ok=True, status="unconfirmed", how="quote", note=why)


def taker_sell(prints, ts, bid, side="yes", qty=1.0, rules=HONEST):
    """A taker sale of `side` at `bid`: the same check as a taker buy of the other side at 1 - bid."""
    r = taker_buy(prints, ts, round(1 - bid, 4), other(side), qty, rules)
    if r.get("last_trade") is not None:
        r["last_trade"] = round(1 - r["last_trade"], 4)
    return dict(r, ask=None, bid=bid)


# ---------------------------------------------------------------- resting orders
def crossed(prints, ts, limit, side, rules=HONEST, quote=None):
    """Would a post-only BUY of `side` at `limit` posted at `ts` cross? `quote` = (bid, ask) on `side` at that minute if known;
    else the last print inside the lookback at or under the limit says the price was already there. -> the price it saw, or None."""
    if quote is not None:
        ask = quote[1]
        return ask if ask is not None and ask <= limit + EPS else None
    i = _from(prints, ts)
    if i == 0 or prints[i - 1][0] < ts - rules.cross_lookback_s:
        return None
    last = px_of(prints[i - 1], side)
    return last if last <= limit + EPS else None


def resting_buy(prints, placed_ts, limit, side="yes", qty=1.0, rules=HONEST, cancel_ts=None, quote=None, check_cross=True):
    """A post-only resting BUY of `qty` contracts of `side` at `limit`, up from placed_ts until cancel_ts (None = to the last print).

    -> dict(status crossed | unfilled | partial | filled, qty (filled), first_ts, fill_ts (when the last contract filled), via
    (how the first contract filled: through | offer | queue), through_n / offer_n / queue_n (contracts printed in each case while
    the order was up), touched (a print reached the limit at all))."""
    out = dict(status="unfilled", limit=limit, side=side, want=qty, qty=0.0, first_ts=None, fill_ts=None, via=None,
               through_n=0.0, offer_n=0.0, queue_n=0.0, touched=False)
    if check_cross:
        saw = crossed(prints, placed_ts, limit, side, rules, quote)
        if saw is not None:
            return dict(out, status="crossed", saw=saw)
    got, ahead = 0.0, rules.queue_ahead
    for p in prints[_from(prints, placed_ts):]:
        if cancel_ts is not None and p[0] >= cancel_ts:
            break
        px = px_of(p, side)
        if px > limit + EPS:
            continue
        out["touched"] = True
        if px < limit - EPS:
            how, mine = "through", p[2]
            out["through_n"] += p[2]
        elif rules.offer_fills and p[3] == side:
            how, mine = "offer", p[2]
            out["offer_n"] += p[2]
        else:
            how = "queue"
            out["queue_n"] += p[2]
            used = min(ahead, p[2])
            ahead -= used
            mine = p[2] - used
        if got >= qty - EPS or mine <= EPS:
            continue
        if out["first_ts"] is None:
            out.update(first_ts=p[0], via=how)
        got = min(qty, got + mine)
        if got >= qty - EPS:
            out["fill_ts"] = p[0]
    for k in ("through_n", "offer_n", "queue_n"):
        out[k] = round(out[k], 2)
    out["qty"] = round(got, 4)
    out["status"] = "filled" if got >= qty - EPS else "partial" if got > EPS else "unfilled"
    return out


def resting_sell(prints, from_ts, target, side="yes", qty=1.0, rules=HONEST, until_ts=None, quote=None, after_fill=True):
    """A post-only resting SELL of `qty` contracts of `side` at `target`. With after_fill the order goes up `latency_s` after from_ts
    (from_ts is the fill it follows); without, it is up at from_ts (a sell that was already resting, e.g. posted before a tip).

    -> resting_buy's dict in sell terms, plus status "crossed": the price was already at or through the target when it went up, so
    it is sold as a TAKER at the target (taker=True). With a quote that is immediate; with only the last print to go by, it waits
    for a later print at or above the target to confirm, and is unfilled without one."""
    up = from_ts + (rules.latency_s if after_fill else 0.0)
    q = None if quote is None else (round(1 - quote[1], 4) if quote[1] is not None else None,
                                    round(1 - quote[0], 4) if quote[0] is not None else None)
    r = resting_buy(prints, up, round(1 - target, 4), other(side), qty, rules, until_ts, q)
    r.update(limit=target, side=side, up_ts=up, taker=False)
    if r["status"] != "crossed":
        return r
    saw = round(1 - r["saw"], 4)
    if quote is not None:                                   # the book itself said so: sold into it at once
        r.update(qty=qty, first_ts=up, fill_ts=up, via="crossed", taker=True, saw=saw)
        return r
    # Only the last print said so, and a flash print proves nothing about the book a minute later. The sale counts once a
    # later print at or above the target confirms the price was there (ours would have been the lowest offer, so it trades first).
    c = resting_buy(prints, up, round(1 - target, 4), other(side), qty, dataclasses.replace(rules, queue_ahead=0.0), until_ts,
                    check_cross=False)
    c.update(limit=target, side=side, up_ts=up, saw=saw, taker=c["qty"] > EPS)
    if c["qty"] > EPS:
        c.update(status="crossed", via="crossed")
    return c


# ---------------------------------------------------------------- a whole trade
def settle(entry_px, qty, sells, payout, entry_taker=True, rules=HONEST):
    """One trade after fees. `sells` = [(price, contracts, taker?)]; what is not sold is paid `payout` (1 or 0; None = still open).

    -> dict(cost, proceeds, roi, gross (the return before any fee), sold, held, open)."""
    stake = entry_px * qty
    cost = stake + fee(entry_px, qty, entry_taker, rules)
    sold = sum(n for _p, n, _t in sells)
    held = max(0.0, qty - sold)
    raw = sum(p * n for p, n, _t in sells)
    net = raw - sum(fee(p, n, t, rules) for p, n, t in sells)
    if held > EPS and payout is None:
        return dict(cost=round(cost, 6), proceeds=None, roi=None, gross=None, sold=round(sold, 4), held=round(held, 4), open=True)
    pay = held * (payout or 0.0)
    return dict(cost=round(cost, 6), proceeds=round(net + pay, 6), roi=round((net + pay - cost) / cost, 4),
                gross=round((raw + pay - stake) / stake, 4), sold=round(sold, 4), held=round(held, 4), open=False)


def trade(prints, side, entry, exits=(), payout=None, qty=None, rules=HONEST, whole=False):
    """One paper trade end to end.

    entry  dict(kind "taker", ts, price[, book_size])                     buy at a quoted ask
           dict(kind "rest", ts, price[, cancel_ts, quote, check_cross])  a post-only resting bid
    exits  [dict(target, share[, from_ts, until_ts, quote])]  resting sells; share of the position each. from_ts given = the sell is
           up from then (or from the fill + latency if that is later); not given = it goes up latency after the fill.
    payout 1.0 if `side` won, 0.0 if it lost, None while unsettled.
    qty    contracts wanted (default: what $1 buys at the entry price).
    whole  size the sells in whole contracts, the way the follower does: each leg but the last gets its share rounded down, the
           last leg the rest (5 contracts at 50/50 = 2 and 3).

    -> dict(status no_entry | open | settled, why, entry {...}, legs [...], qty, cost, roi, hold (the same entry held to the end),
    gross, sold). A partial resting fill is traded at the size that filled."""
    px = entry["price"]
    want = qty if qty is not None else stake_qty(px)
    if entry["kind"] == "taker":
        e = taker_buy(prints, entry["ts"], px, side, want, rules, entry.get("book_size"))
        if not e["ok"]:
            return dict(status="no_entry", why="unverified ask: " + e["reason"], entry=e, legs=[], qty=0.0, roi=None, hold=None)
        got, fill_ts, is_taker = want, entry["ts"], True
    else:
        e = resting_buy(prints, entry["ts"], px, side, want, rules, entry.get("cancel_ts"), entry.get("quote"),
                        entry.get("check_cross", True))
        if e["qty"] <= EPS:
            why = "the bid would have crossed" if e["status"] == "crossed" else \
                  ("touched, never filled (behind the queue)" if e["touched"] else "the price never reached the bid")
            return dict(status="no_entry", why=why, entry=e, legs=[], qty=0.0, roi=None, hold=None)
        got, fill_ts, is_taker = e["qty"], e["fill_ts"] or e["first_ts"], False
    legs, sells, left = [], [], got
    for k, x in enumerate(exits):
        n = round(got * x["share"], 4)
        if whole:
            n = left if k == len(exits) - 1 else float(math.floor(got * x["share"] + EPS))
            left = round(left - n, 4)
        if n <= EPS:
            legs.append(dict(target=x["target"], share=x["share"], want=0.0, sold=0.0, status="no size", via=None, ts=None, taker=False))
            continue
        start = fill_ts + rules.latency_s
        if x.get("from_ts") is not None and x["from_ts"] >= start:
            s = resting_sell(prints, x["from_ts"], x["target"], side, n, rules, x.get("until_ts"), x.get("quote"), after_fill=False)
        else:
            s = resting_sell(prints, fill_ts, x["target"], side, n, rules, x.get("until_ts"), x.get("quote"))
        legs.append(dict(target=x["target"], share=x["share"], want=n, sold=s["qty"], status=s["status"], via=s["via"],
                         ts=s["fill_ts"] or s["first_ts"], taker=s["taker"]))
        if s["qty"] > EPS:
            sells.append((x["target"], s["qty"], s["taker"]))
    r = settle(px, got, sells, payout, is_taker, rules)
    hold = settle(px, got, [], payout, is_taker, rules)
    return dict(status="open" if r["open"] else "settled", why=None, entry=e, legs=legs, qty=got, fill_ts=fill_ts, cost=r["cost"],
                roi=r["roi"], hold=hold["roi"], gross=r["gross"], sold=r["sold"])
