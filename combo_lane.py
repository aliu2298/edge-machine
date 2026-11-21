"""combo_crypto_sp_no — one paper 2-leg combo a trading day: crypto NO + S&P NO, both read at the same minute (Sandbox paper, 2026-11-21).

Olu: "convert the leadership page to combo". Spec: docs/combos_high_hit_2026-11-20.md ("Build spec"), pre-registration:
docs/prereg_combo_crypto_sp_2026-11-21.md, written before the first entry.

The minute: the run that follows the crypto No lane (crypto_fav_band_below) logging its pick, inside the same tracker job, about 13:35 ET.
  Crypto leg  that lane's own pick today (the highest-priced coin if there are several), at the ask the lane just logged. A pick read
              more than MAX_GAP_MIN before this run is stale and the day is "no combo".
  S&P leg     finance_nc's rule re-run NOW (never the 12:30 ET pick): the cheapest KXINXU H1600 rung with a No ask of 90-98c, a spread
              of 3c or less and 25+ contracts. finance_nc's own ledger is not touched.
No combo (with the reason) when either leg has no pick at that minute, and on weekends.
Price: 0.994 x 1.03 (the crypto-S&P link) x the product of the two No asks, plus the taker fee 0.07 x p x (1 - p). The combo pays 1 only if
both legs win; a void or part-value leg multiplies by its settled value (no refund). Comparison: the same two legs as singles at the same
minute. Public reads only; nothing is ordered. Combo legs are bought at the ask, so a lane that rests bids or sells to a target cannot be a leg.
"""
import datetime as dt
import json
import os
import urllib.parse

import daily_track as D
import finance_nc as FN

KEY = "combo_crypto_sp_no"
LABEL = "Combo · crypto No + S&P No, one paper combo a day"
REGISTERED = "2026-11-21"
PATH = os.path.join(D.ROOT, "data", "combo_ledger.json")
CRYPTO_LANE = "crypto_fav_band_below"
MARKUP = 0.994 * 1.03
FEE_RATE = 0.07
MAX_GAP_MIN = 20          # the crypto pick must have been logged this recently for the minute to count as the same
GIVE_UP_ET = (14, 30)     # no crypto pick by this time on a weekday: "no combo", the lane did not pick
READ_AT = 30              # settled combos
UTC = dt.timezone.utc


def empty():
    return {"version": "combo-v1", "key": KEY, "registered": REGISTERED, "days": [], "error": None, "last_run": None}


def load(path=PATH):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return empty()


def fee(p):
    return FEE_RATE * p * (1 - p)


def combo_price(ask_c, ask_s):
    """(price, fee, cost) of the paper combo: the leg asks multiplied, with the link markup, plus the taker fee."""
    p = round(MARKUP * ask_c * ask_s, 6)
    f = round(fee(p), 6)
    return p, f, round(p + f, 6)


def single_cost(ask):
    return round(ask + fee(ask), 6)


def crypto_pick(quotes, day, now):
    """The crypto lane's pick for `day` (an ET date): its highest-priced bet row logged that day, or None.
    `quotes` is the sandbox ledger's quote list."""
    rows = []
    for q in quotes:
        if q.get("source") != CRYPTO_LANE or not q.get("bet") or q.get("price") is None:
            continue
        at = D.instant(q.get("logged"))
        if at and at.astimezone(D.ET).date() == day:
            rows.append((q["price"], q["market_id"], q, at))
    if not rows:
        return None
    price, market_id, q, at = max(rows, key=lambda r: (r[0], r[1]))
    return dict(ticker=market_id, ask=float(price), logged=at.isoformat(), label=q.get("label"),
                gap_min=round((now - at).total_seconds() / 60, 1))


def sp_pick(fetch, now):
    """finance_nc's rule at this minute, without writing its ledger: (pick dict | None, reason)."""
    try:
        markets = D.pages("markets?limit=1000&status=open&series_ticker=" + FN.SERIES, "markets", fetch)
    except Exception as e:                                  # noqa: BLE001
        return None, f"S&P ladder could not be read: {str(e)[:80]}"
    pool = []
    for m in markets:
        if FN.in_scope(m, now) or not FN.listing_gate(m):
            continue
        q = FN.no_quote(fetch("markets/" + urllib.parse.quote(m["ticker"], safe="") + "/orderbook?depth=1"))
        if FN.eligible(q):
            pool.append((q["ask"], m["ticker"], m, q))
    if not pool:
        return None, "no S&P rung in the 90-98c, 3c-spread, 25-contract rule at that minute"
    ask, ticker, m, q = min(pool, key=lambda r: (r[0], r[1]))
    return dict(ticker=ticker, ask=ask, bid=q["bid"], size=q["size"], close=m.get("close_time"),
                title=str(m.get("yes_sub_title") or m.get("subtitle") or m.get("title") or "")), None


def add_day(state, quotes, fetch=D.get, now=None):
    """Make the day's decision once: a combo row, or a "no combo" row with its reason. Weekdays only."""
    now = now or dt.datetime.now(UTC)
    et = now.astimezone(D.ET)
    day = et.date()
    if day.weekday() >= 5 or any(r["day"] == day.isoformat() for r in state["days"]):
        return state
    cp = crypto_pick(quotes, day, now)
    base = dict(day=day.isoformat(), read_at=now.replace(microsecond=0).isoformat())
    if cp is None:
        if (et.hour, et.minute) >= GIVE_UP_ET:
            state["days"].append(dict(base, status="no_combo", reason="the crypto No lane made no pick today"))
        return state                                            # earlier than that: the lane may still pick
    if cp["gap_min"] > MAX_GAP_MIN:
        state["days"].append(dict(base, status="no_combo", crypto=cp,
                                  reason=f"the crypto pick was logged {cp['gap_min']:.0f} min before this read, not the same minute"))
        return state
    sp, why = sp_pick(fetch, now)
    if sp is None:
        state["days"].append(dict(base, status="no_combo", crypto=cp, reason=why))
        return state
    p, f, cost = combo_price(cp["ask"], sp["ask"])
    state["days"].append(dict(base, status="open", crypto=cp, sp=sp, price=p, fee=f, cost=cost, payout=1.0,
                              singles=dict(crypto=single_cost(cp["ask"]), sp=single_cost(sp["ask"]))))
    return state


def no_value(ticker, fetch):
    """The No side's settled value (1 - the yes payout), or None while the market is not final."""
    m = fetch("markets/" + urllib.parse.quote(ticker, safe="")).get("market", {})
    if m.get("ticker") != ticker:
        raise ValueError("settlement ticker mismatch")
    yes = D.payout(m)
    return None if yes is None else round(1 - yes, 6)


def settle(state, fetch=D.get):
    errors = []
    for r in state["days"]:
        if r["status"] != "open":
            continue
        try:
            vc, vs = no_value(r["crypto"]["ticker"], fetch), no_value(r["sp"]["ticker"], fetch)
        except Exception as e:                                  # noqa: BLE001
            errors.append(f"{r['day']}: {str(e)[:80]}")
            continue
        if vc is None or vs is None:
            continue
        v = round(vc * vs, 6)                                   # a void or part-value leg multiplies in, with no refund
        r.update(value_crypto=vc, value_sp=vs, value=v,
                 status="won" if v == 1 else "lost" if v == 0 else "no_result",
                 roi=round(v / r["cost"] - 1, 4),
                 roi_crypto=round(vc / r["singles"]["crypto"] - 1, 4), roi_sp=round(vs / r["singles"]["sp"] - 1, 4))
    return errors


def run(state, quotes, fetch=D.get, now=None):
    now = now or dt.datetime.now(UTC)
    state["last_run"] = now.replace(microsecond=0).isoformat()
    errors = []
    try:
        add_day(state, quotes, fetch, now)
    except Exception as e:                                      # noqa: BLE001
        errors.append(f"entry: {str(e)[:100]}")
    errors += settle(state, fetch)
    state["error"] = "; ".join(errors)[:600] or None
    return state


def record(state):
    """The lines the page shows: lands, payout, return a combo, the same legs as singles, longest losing run, days with no combo."""
    done = [r for r in state["days"] if r["status"] in ("won", "lost", "no_result")]
    n = len(done)
    out = dict(n=n, open=sum(r["status"] == "open" for r in state["days"]), no_combo=sum(r["status"] == "no_combo" for r in state["days"]),
               read_at=READ_AT)
    if not n:
        return dict(out, landed=0, mean_roi=None, single_crypto=None, single_sp=None, single_both=None, pays=None, run=0, break_even=None)
    out["landed"] = sum(r["status"] == "won" for r in done)
    out["mean_roi"] = sum(r["roi"] for r in done) / n
    out["single_crypto"] = sum(r["roi_crypto"] for r in done) / n
    out["single_sp"] = sum(r["roi_sp"] for r in done) / n
    out["single_both"] = (out["single_crypto"] + out["single_sp"]) / 2        # the two legs as two equal-sized single bets
    out["pays"] = sum(1.0 / r["cost"] for r in done) / n
    longest = cur = 0
    for r in sorted(done, key=lambda r: r["day"]):
        cur = cur + 1 if r["status"] != "won" else 0
        longest = max(longest, cur)
    out["run"] = longest
    # The most the combo could cost, as a multiple of the product of the leg asks plus the fee, before its return reaches zero.
    out["break_even"] = break_even_markup(done)
    return out


def break_even_markup(done):
    """The markup on the product of the two No asks at which the combo's return over `done` is zero, fee included (bisection).
    The paper price uses MARKUP; the combo holds up only while this is above it."""
    landed = sum(r["status"] == "won" for r in done)
    if not done or not landed:
        return 0.0
    prods = [r["crypto"]["ask"] * r["sp"]["ask"] for r in done]
    pay = sum(r.get("value", 1.0 if r["status"] == "won" else 0.0) for r in done) / len(done)             # the mean settled value (a part-value leg counts)
    cost = lambda m: sum(m * x + fee(m * x) for x in prods) / len(prods)    # noqa: E731
    lo, hi = 0.0, 1.0 / max(prods)                              # price stays at or below 1 up to hi
    if cost(hi) <= pay:
        return hi
    for _ in range(60):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if cost(mid) < pay else (lo, mid)
    return round((lo + hi) / 2, 4)


def verdict(rec, lanes=None):
    """The pre-registered read (Build spec): at READ_AT settled combos keep only if the return is above zero AND the break-even markup is
    above the paper markup; retire at once if either lane's own singles (`lanes` = [return or None, ...]) are under zero."""
    under = [x for x in (lanes or []) if x is not None and x < 0]
    if under:
        return "retire at once: a lane's own singles are under zero"
    if rec["n"] < READ_AT:
        return f"too early ({rec['n']} of {READ_AT} settled combos; read once at {READ_AT})"
    if rec["mean_roi"] > 0 and rec["break_even"] > MARKUP:
        return "keep: the return is above zero and the break-even markup is above the paper markup"
    return "retire: the return is not above zero, or the break-even markup is not above the paper markup"


def _sandbox_quotes():
    import sandbox_track as T
    try:
        return T.load().get("quotes") or []
    except Exception:                                           # noqa: BLE001
        return []


def main():
    state = run(load(), _sandbox_quotes())
    os.makedirs(os.path.dirname(PATH), exist_ok=True)
    tmp = PATH + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f, indent=2, sort_keys=True)
        f.write("\n")
    os.replace(tmp, PATH)
    print(KEY, "days", len(state["days"]), "error", state["error"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
