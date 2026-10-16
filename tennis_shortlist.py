"""Frozen v1 daily UTR shortlist. Public books only; never submits an order."""
import datetime as dt
import math
import urllib.parse
from zoneinfo import ZoneInfo

NAME = "tennis_utr_shortlist_v1"
POOL = "tennis_utr_shortlist_pool_v1"
CT = ZoneInfo("America/Chicago")
MAX_DAILY = 3
MAX_SPREAD = .03
MAX_AGE_SECONDS = 300
STAKE = 100


def instant(value):
    try:
        x = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return x if x.tzinfo else None
    except (ValueError, TypeError):
        return None


def day(value):
    x = instant(value)
    return x.astimezone(CT).date().isoformat() if x else None


def book(slug):
    import sandbox_sources as S
    return S._get(f"{S.PMUS}/v1/markets/{urllib.parse.quote(str(slug), safe='')}/book", tries=1)


def read_book(payload, side, now):
    """NO-side asks are complemented YES bids; depth follows that side."""
    import sandbox_sources as S
    m = (payload or {}).get("marketData") or {}
    at = instant(m.get("transactTime"))
    if m.get("state") != "MARKET_STATE_OPEN" or not at or not 0 <= (now-at).total_seconds() <= MAX_AGE_SECONDS:
        return None
    def levels(key):
        out = []
        for row in m.get(key) or []:
            p, n = S._pmus_amt(row.get("px")), S._num(row.get("qty"))
            if p is not None and n is not None and math.isfinite(p) and math.isfinite(n) and 0 < p < 1 and n > 0:
                out.append((p, n))
        return out
    bids, asks = levels("bids"), levels("offers")
    if not bids or not asks:
        return None
    bid, ask = max(p for p, _ in bids), min(p for p, _ in asks)
    if not bid < ask or ask-bid > MAX_SPREAD + 1e-9:
        return None
    price = ask if side == "a" else 1-bid
    size = sum(n for p, n in (asks if side == "a" else bids) if abs(p-(ask if side == "a" else bid)) < 1e-9)
    cost = price + .06 * price * (1-price)  # existing paper fee model, not a fee quote
    # No depth floor here (2026-10-15). It wanted STAKE/cost (~135) contracts at the single best
    # price, enough for the full $100 PAPER stake, and live UTR books hold 4-17 there with the
    # size a few cents behind, so the rule logged nothing after Oct 14. No other sport's rule
    # gates on depth: the record is kept at the posted price, and execution checks the book it
    # actually trades ($1 a bet) itself. A quoted ask with any size is enough.
    if not .70 <= price < .75 or size <= 0:
        return None
    return dict(price=round(price, 6), cost=round(cost, 6), ask_size=size,
                spread=round(ask-bid, 6), price_a=ask, price_b=1-bid,
                book_at=at.isoformat())


def select(rows, previous, now, get_book=book):
    import sandbox_sources as S
    today = now.astimezone(CT).date().isoformat()
    prior = [q for q in previous if q.get("source") == NAME and q.get("bet")]
    remaining = max(0, MAX_DAILY-sum(day(q.get("logged")) == today for q in prior))
    used = {str(q.get("market_id")) for q in prior}
    def contest(r):
        return (tuple(sorted(str(r.get(k) or "").casefold().strip() for k in ("side_a", "side_b"))),
                day(r.get("start")))
    matches = {contest(q) for q in prior}
    audit, eligible = [], []
    for r in rows:
        if r.get("venue") != "polymarket_us" or S.tennis_tier(r.get("market_id")) != "utr":
            continue
        if S.tennis_start_window(r, now) != "in" or r.get("untraded") or r.get("price_draw") is not None:
            continue
        sides = [s for s in ("a", "b") if .70 <= float(r.get("price_"+s) or 0) < .75]
        if len(sides) != 1:
            continue
        side = sides[0]
        try:
            b = read_book(get_book(r["market_id"]), side, now)
        except Exception as e:
            audit.append(dict(market_id=r["market_id"], reason="book unavailable: " + type(e).__name__))
            continue
        if not b:
            audit.append(dict(market_id=r["market_id"], reason="book failed freshness/price/spread/depth gate"))
            continue
        candidate = dict(r, **b, pick=side)
        eligible.append(candidate)
    eligible.sort(key=lambda r: (r["cost"], r["spread"], -r["ask_size"], r["start"], r["market_id"]))
    picks = []
    for r in eligible:
        duplicate = str(r["market_id"]) in used or contest(r) in matches
        if not duplicate and len(picks) < remaining:
            picks.append(r)
            used.add(str(r["market_id"]))
            matches.add(contest(r))
        audit.append(dict(market_id=r["market_id"], reason="already selected" if duplicate else
                          "selected" if r in picks else "daily cap", price=r["price"],
                          cost=r["cost"], spread=r["spread"], ask_size=r["ask_size"], book_at=r["book_at"]))
    return picks, eligible, audit


def comparison(d):
    """Modeled returns for selected picks and ALL eligible first observations."""
    import sandbox_track as T
    seen, groups = set(), {NAME: [], POOL: []}
    for q in T.all_bets(d):
        if q.get("source") not in groups or q.get("id") in seen:
            continue
        seen.add(q.get("id"))
        if q.get("result") not in ("a", "b", "price"):
            continue
        x = dict(q)
        if x["result"] != "price":
            x["status"] = "won" if x.get("pick") == x["result"] else "lost"
        groups[q["source"]].append(x)
    return {key: dict(n=len(qs), roi=sum(T.pnl_after_fee(q) for q in qs)/(100*len(qs)) if qs else None)
            for key, qs in groups.items()}
