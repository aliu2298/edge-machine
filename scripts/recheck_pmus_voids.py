#!/usr/bin/env python3
"""Re-check Polymarket US rows the resolver voided or left open. One-time, idempotent.

A final Polymarket US settlement that is not a clean 0 or 1 pays the price the
venue paid, including exactly 0.5. A walkover settles at the last fair price.
That is a payout, not a refund. Only an explicit cancel, or a void that already
carries a note (duplicate, swapped teams, a late log, a pre-gate price), stays
a void.

Targets:
  * polymarket_us, status void, result void, no note — the resolver wrote these.
  * polymarket_us, status open, no result, no note, whose start date is already
    in the past — the previous rule reopened in-between prices and left them
    open. A match from today is still the grader's. A fetch that is not a final
    price does not touch an open row, so a clean 0 or 1 stays for the grader.
  * a polymarket US combo basket (venue combo, source pm_combo* / id pmcombo*)
    with no note, void or open, whose leg is one of those markets.

A yes/long buyer is paid the settlement. A no/short buyer is paid one minus it.
A basket is paid the product of its leg payouts (1 won, 0 lost, the fair price
for a price-settled leg). A lost leg settles the basket even when another leg
is unresolved. P/L is stake * (paid / entry - 1), before fees. The row stores
result "price", status "settled", and settle_px.

Dry-run by default. --apply writes data/sandbox_ledger.json through the atomic
writer (temp file, then os.replace). A second --apply changes nothing: a
price-settled row is no longer a void and no longer open.

A 429 or any other fetch error leaves that market unchanged. An error is never
a void and never a price. A price is written only when the market payload says
closed and MARKET_STATUS_RESOLVED. The gateway rate-limits hard, so requests
are spaced and a 429 backs off.

Usage:
  python3 scripts/recheck_pmus_voids.py
  python3 scripts/recheck_pmus_voids.py --apply
"""
import argparse
import datetime
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import sandbox_sources as S
import sandbox_track as T

INTERVAL = 1.05          # the gateway 429s after a short burst of fast calls
RETRY_AFTER = (8, 16, 32, 64)


def _started_long_ago(q, now):
    """True when the quote's start date is before today's UTC date.

    The rows the previous rule reopened all started on an earlier day. A match
    from today is left for the grader even if it has already begun.
    """
    start = q.get("start")
    if not start:
        return True
    today = now.astimezone(datetime.timezone.utc).strftime("%Y-%m-%d")
    return str(start)[:10] < today


def _note(q):
    return str(q.get("note") or "").strip()


def is_resolver_void(q):
    """A Polymarket US void with no note: the resolver wrote it, nothing else did."""
    return (q.get("venue") == "polymarket_us" and q.get("status") == "void"
            and q.get("result") == "void" and not _note(q))


def is_open_pmus(q, now):
    """An open Polymarket US row the previous rule may have left unsettled."""
    return (q.get("venue") == "polymarket_us" and q.get("status") == "open"
            and q.get("result") is None and not _note(q) and _started_long_ago(q, now))


def is_pm_combo(q):
    mid = str(q.get("market_id") or "")
    src = str(q.get("source") or "")
    return q.get("venue") == "combo" and (mid.startswith("pmcombo") or src.startswith("pm_combo"))


def affected_combos(quotes, market_ids):
    """Void or open Polymarket US baskets with a targeted leg, and no note."""
    out = []
    for q in quotes:
        if not is_pm_combo(q) or _note(q):
            continue
        voided = q.get("status") == "void" and q.get("result") == "void"
        opened = q.get("status") == "open" and q.get("result") is None
        if not voided and not opened:
            continue
        legs = q.get("legs") or []
        if any(leg.get("venue") == "polymarket_us" and leg.get("market_id") in market_ids
               for leg in legs):
            out.append(q)
    return out


def _fmt(val):
    if isinstance(val, float):
        return format(val, "g")
    return "" if val is None else str(val)


def _change(q, before, settlement):
    old_status, old_result, old_pnl, _old_settled = before
    return dict(
        id=q.get("id"), market_id=q.get("market_id"), source=q.get("source"),
        bet=bool(q.get("bet")), side=q.get("pick"), entry=q.get("price"),
        old_status=old_status, old_result=old_result, old_pnl=old_pnl,
        new_status=q.get("status"), new_result=q.get("result"), new_pnl=q.get("pnl"),
        settlement=settlement, paid=q.get("settle_px"),
    )


def _leg_kind(leg, fetched, quotes):
    """(kind, venue_settlement) for one basket leg.

    The fetch wins when it answered. Otherwise a result already stored on that
    market is used, so a leg that was never a void does not have to be fetched
    again. 'unknown' means this leg cannot settle the basket yet.
    """
    mid = leg.get("market_id")
    if mid in fetched:
        kind, val = fetched[mid]
        if kind not in ("unknown", None):
            return kind, val
    for q in quotes:
        if q.get("market_id") != mid or q.get("venue") != "polymarket_us":
            continue
        result = q.get("result")
        if result in ("a", "b", "void"):
            return result, None
        if result == "price" and q.get("settle_px") is not None:
            px = float(q["settle_px"])
            venue = (1.0 - px) if q.get("pick") == "b" else px
            return "price", venue
    return "unknown", None


def _combo_action(q, fetched, quotes):
    """(action, result, settlement_shown) for one basket.

    action is 'leave', 'keep', 'lost', 'price', or 'resettle'. A lost leg
    returns immediately, even when another leg is unresolved.
    """
    product = 1.0
    priced = False
    voided = False
    pending = False
    shown = None
    for leg in q.get("legs") or []:
        if leg.get("venue") != "polymarket_us":
            return "leave", None, None
        kind, val = _leg_kind(leg, fetched, quotes)
        if kind in ("unknown", None):
            pending = True
            continue
        if kind == "void":
            voided = True
            continue
        if kind == "price":
            product *= S.pmus_paid(leg.get("pick"), val)
            priced = True
            shown = val
            continue
        if kind not in ("a", "b"):
            pending = True
            continue
        if kind != leg.get("pick"):
            return "lost", "b", val
    if pending:
        return "leave", None, None
    if voided:
        return "keep", "void", None
    if priced:
        return "price", ("price", product), shown
    if q.get("status") == "void":
        return "resettle", "a", None
    return "leave", None, None


def recheck(quotes, fetched, stamp, now=None):
    """Apply fetched settlements. Mutates `quotes`. Returns the rows that changed.

    `fetched` maps a market id to (kind, value). kind is 'a', 'b', 'void',
    'price', or 'unknown'. A second call with the same `fetched` returns nothing.
    """
    now = now or datetime.datetime.now(datetime.timezone.utc)
    voids = [q for q in quotes if is_resolver_void(q)]
    opens = [q for q in quotes if is_open_pmus(q, now)]
    market_ids = {q.get("market_id") for q in voids + opens}
    combos = affected_combos(quotes, market_ids)
    changes = []

    def _write(q, res, shown):
        before = (q.get("status"), q.get("result"), q.get("pnl"), q.get("settled"))
        T._apply_result(q, res, stamp)
        after = (q.get("status"), q.get("result"), q.get("pnl"), q.get("settled"))
        if after == before:
            return
        changes.append(_change(q, before, shown))

    for q in voids:
        mid = q.get("market_id")
        kind, val = fetched.get(mid, ("unknown", None))
        if kind in ("unknown", None, "void"):
            continue
        if kind in ("a", "b"):
            _write(q, kind, val)
        elif kind == "price" and val is not None:
            _write(q, ("price", float(val)), val)

    for q in opens:
        # A clean winner stays open for the grader. Only a final price closes it.
        mid = q.get("market_id")
        kind, val = fetched.get(mid, ("unknown", None))
        if kind != "price" or val is None:
            continue
        _write(q, ("price", float(val)), val)

    for q in combos:
        action, res, shown = _combo_action(q, fetched, quotes)
        if action in ("leave", "keep") or res is None:
            continue
        _write(q, res, shown)
    return changes


def paper_pnl(changes):
    """Stake P/L added by the rewrite, before fees. Voids and opens carried 0."""
    total = 0.0
    for c in changes:
        if not c["bet"]:
            continue
        total += (c["new_pnl"] or 0.0) - (c["old_pnl"] or 0.0)
    return round(total, 2)


def paper_pnl_after_fee(changes, quotes):
    """The same bets after the taker fee, minus the 0 they carried as voids or opens."""
    by_id = {q.get("id"): q for q in quotes}
    total = 0.0
    for c in changes:
        if not c["bet"]:
            continue
        q = by_id.get(c["id"])
        if q is None or q.get("status") not in ("won", "lost", "settled"):
            continue
        total += T.pnl_after_fee(q)
    return round(total, 2)


def _pace(state, interval):
    gap = interval - (time.monotonic() - state["last"])
    if gap > 0:
        time.sleep(gap)
    state["last"] = time.monotonic()


def _request(url, state, interval):
    """Parsed JSON, or (None, error). A 429 backs off. Any error is not a settlement."""
    for attempt, backoff in enumerate(RETRY_AFTER):
        _pace(state, interval)
        try:
            req = urllib.request.Request(url, headers={"User-Agent": S.UA, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=20) as resp:
                return json.load(resp), None
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt + 1 < len(RETRY_AFTER):
                retry = e.headers.get("Retry-After") if e.headers else None
                try:
                    wait = float(retry)
                except (TypeError, ValueError):
                    wait = backoff
                time.sleep(max(wait, 1.0))
                state["last"] = time.monotonic()
                continue
            return None, f"HTTP {e.code}"
        except Exception as e:
            return None, f"{type(e).__name__}"
    return None, "HTTP 429"


def _is_final(body):
    market = body.get("market") if isinstance(body, dict) else None
    if not isinstance(market, dict):
        return False
    return (market.get("closed") is True
            and str(market.get("status") or "") == "MARKET_STATUS_RESOLVED")


def fetch_one(slug, state, interval=INTERVAL):
    """(kind, value, error). error is set only when the row must be left alone."""
    url = f"{S.PMUS}/v1/markets/{urllib.parse.quote(str(slug))}/settlement"
    body, err = _request(url, state, interval)
    if err or body is None:
        return "unknown", None, err or "no body"
    kind, val = S.classify_polymarket_us(body)
    if kind is None:
        return "unknown", None, "non-numeric settlement"
    if kind != "price":
        return kind, val, None
    status_url = f"{S.PMUS}/v1/market/slug/{urllib.parse.quote(str(slug))}"
    market, merr = _request(status_url, state, interval)
    if merr or not _is_final(market):
        return "unknown", None, merr or "market not final"
    return "price", val, None


def fetch_markets(slugs, interval=INTERVAL):
    state = {"last": 0.0}
    fetched, errors = {}, {}
    for i, slug in enumerate(slugs, 1):
        kind, val, err = fetch_one(slug, state, interval)
        fetched[slug] = (kind, val)
        if err:
            errors[slug] = err
        shown = _fmt(val) if val is not None else (err or "")
        print(f"  {i}/{len(slugs)} {slug} {kind} {shown}", flush=True)
    return fetched, errors


def write_ledger(d, path=None):
    """Replace the ledger atomically. The archive is not part of this file."""
    body = {k: v for k, v in d.items() if k not in ("_archive", "_archive_dirty")}
    ids = [q.get("id") for q in body.get("quotes") or []]
    if len(ids) != len(set(ids)):
        raise SystemExit("duplicate quote ids; ledger not written")
    T.atomic_write_json(path or T.LEDGER, body, prefix=".ledger-")


def format_report(changes, errors, fetched, quotes):
    lines = []
    lines.append("id | market | source | bet | side | entry | venue settlement | paid | "
                 "old status/result/pnl | new status/result/pnl")
    lines.append("--- | --- | --- | --- | --- | --- | --- | --- | --- | ---")
    for c in changes:
        old = f"{c['old_status']}/{c['old_result']}/{c['old_pnl']}"
        new = f"{c['new_status']}/{c['new_result']}/{c['new_pnl']}"
        lines.append(" | ".join(str(x) for x in (
            c["id"], c["market_id"], c["source"], "yes" if c["bet"] else "no",
            c.get("side") if c.get("side") is not None else "",
            _fmt(c.get("entry")), _fmt(c.get("settlement")), _fmt(c.get("paid")),
            old, new)))
    missed = sorted(mid for mid, (kind, _v) in fetched.items() if kind == "unknown")
    kept = sum(1 for kind, _v in fetched.values() if kind == "void")
    priced = sum(1 for c in changes if c["new_result"] == "price")
    resettled = sum(1 for c in changes if c["new_status"] in ("won", "lost", "graded"))
    lines.append("")
    lines.append(
        f"price-settled {priced} / kept void (cancel) {kept} / "
        f"re-settled won-lost {resettled} / not re-checked {len(missed)}")
    lines.append(f"paper P/L before fees {paper_pnl(changes):+.2f}")
    lines.append(f"paper P/L after fees {paper_pnl_after_fee(changes, quotes):+.2f}")
    if missed:
        lines.append("not re-checked: " + ", ".join(missed))
    if errors:
        lines.append("fetch errors: " + ", ".join(f"{k} ({v})" for k, v in sorted(errors.items())))
    return "\n".join(lines)


def run(apply=False, interval=INTERVAL, load=None, stamp=None, now=None):
    d = load() if load else T.load()
    quotes = d["quotes"]
    now = now or datetime.datetime.now(datetime.timezone.utc)
    voids = [q for q in quotes if is_resolver_void(q)]
    opens = [q for q in quotes if is_open_pmus(q, now)]
    market_ids = {q.get("market_id") for q in voids + opens}
    extra = set()
    for q in affected_combos(quotes, market_ids):
        for leg in q.get("legs") or []:
            if leg.get("venue") == "polymarket_us" and leg.get("market_id"):
                extra.add(leg["market_id"])
    slugs = sorted(mid for mid in (market_ids | extra) if mid)
    print(f"  {len(voids)} resolver voids, {len(opens)} open rows, "
          f"{len(slugs)} fetches", flush=True)
    fetched, errors = fetch_markets(slugs, interval)
    stamp = stamp or T.now_iso()
    changes = recheck(quotes, fetched, stamp, now=now)
    print(format_report(changes, errors, fetched, quotes))
    if apply and changes:
        write_ledger(d)
        print(f"  wrote {len(changes)} rows")
    elif apply:
        print("  no changes; ledger not written")
    else:
        print("  dry-run; ledger not written")
    return changes


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--apply", action="store_true",
                    help="write the ledger (default is a dry-run)")
    ap.add_argument("--sleep", type=float, default=INTERVAL,
                    help="seconds between gateway requests (default 1.05)")
    args = ap.parse_args(argv)
    run(apply=args.apply, interval=args.sleep)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
