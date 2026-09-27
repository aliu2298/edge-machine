#!/usr/bin/env python3
"""Re-check Polymarket US voids the resolver wrote. One-time, idempotent.

The resolver used to void every settlement that was not a clean 0 or 1. Exactly
0.5 (or an explicit cancel) really is a refund. Any other price strictly between
0 and 1 is a final fair-market settlement with no winner: those rows reopen and
are flagged, and a clean 0 or 1 is re-settled with the tracker's own P/L rules.

Targets only rows the resolver voided: venue polymarket_us, status void, result
void, and no note. A note means the row was voided for another reason (duplicate,
swapped teams, a late log, a pre-gate price) and it stays void. Also re-checks
void Polymarket US combo baskets (venue combo, source pm_combo* / id pmcombo*)
whose Polymarket US leg is one of those markets. The basket follows its legs.

Dry-run by default. --apply writes data/sandbox_ledger.json through the atomic
writer (temp file, then os.replace). A second --apply changes nothing: reopened
and re-settled rows are no longer resolver voids, and a 0.5 void stays a void.

A 429 or any other fetch error leaves that market unchanged and lists it as not
re-checked. An error is never a void and never a reopen. The gateway rate-limits
hard, so requests are spaced and a 429 backs off.

Re-run with --apply if main's ledger moved before this merges. Only the rows
this script decides are rewritten.

Usage:
  python3 scripts/recheck_pmus_voids.py
  python3 scripts/recheck_pmus_voids.py --apply
"""
import argparse
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


def is_resolver_void(q):
    """A Polymarket US void with no note: the resolver wrote it, nothing else did."""
    return (q.get("venue") == "polymarket_us" and q.get("status") == "void"
            and q.get("result") == "void" and not str(q.get("note") or "").strip())


def is_pm_combo(q):
    mid = str(q.get("market_id") or "")
    src = str(q.get("source") or "")
    return q.get("venue") == "combo" and (mid.startswith("pmcombo") or src.startswith("pm_combo"))


def affected_combos(quotes, market_ids):
    """Void Polymarket US baskets with a resolver-voided leg, and no note of their own."""
    out = []
    for q in quotes:
        if not is_pm_combo(q) or q.get("status") != "void" or q.get("result") != "void":
            continue
        if str(q.get("note") or "").strip():
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
        bet=bool(q.get("bet")),
        old_status=old_status, old_result=old_result, old_pnl=old_pnl,
        new_status=q.get("status"), new_result=q.get("result"), new_pnl=q.get("pnl"),
        settlement=settlement,
    )


def _reopen(q):
    q["status"] = "open"
    q["result"] = None
    q["pnl"] = 0.0
    q["settled"] = None


def _combo_action(q, fetched):
    """What a basket should become, following resolve_combo's leg order.

    A void leg refunds the basket. An in-between leg reopens it — a stored void
    would otherwise stick, because a later None cannot replace a void. A leg that
    was not re-checked blocks a win/loss, but does not block that reopen: unknown
    is left as it is only when no leg is a known void or a known in-between price.
    """
    lost = False
    saw_unknown = False
    for leg in q.get("legs") or []:
        if leg.get("venue") != "polymarket_us":
            return "leave", None
        mid = leg.get("market_id")
        kind, val = fetched.get(mid, ("unknown", None))
        if mid not in fetched or kind in ("unknown", None):
            saw_unknown = True
            continue
        if kind == "void":
            return "keep", val
        if kind == "review":
            return "reopen", val
        if kind not in ("a", "b"):
            saw_unknown = True
            continue
        if kind != leg.get("pick"):
            lost = True
    if saw_unknown:
        return "leave", None
    return "resettle", ("b" if lost else "a")


def recheck(quotes, fetched, stamp):
    """Apply fetched settlements to resolver voids and their baskets.

    `fetched` maps a market id to (kind, value). kind is 'a', 'b', 'void',
    'review', or 'unknown'. Mutates `quotes`. Returns the rows that changed,
    in ledger order. A second call with the same `fetched` returns nothing.
    """
    targets = [q for q in quotes if is_resolver_void(q)]
    market_ids = {q.get("market_id") for q in targets}
    combos = affected_combos(quotes, market_ids)
    changes = []

    for q in targets:
        mid = q.get("market_id")
        kind, val = fetched.get(mid, ("unknown", None))
        if kind in ("unknown", None, "void"):
            continue
        before = (q.get("status"), q.get("result"), q.get("pnl"), q.get("settled"))
        if kind == "review":
            _reopen(q)
        elif kind in ("a", "b"):
            T._apply_result(q, kind, stamp)
        else:
            continue
        after = (q.get("status"), q.get("result"), q.get("pnl"), q.get("settled"))
        if after == before:
            continue
        changes.append(_change(q, before, val))

    for q in combos:
        action, info = _combo_action(q, fetched)
        if action in ("leave", "keep"):
            continue
        before = (q.get("status"), q.get("result"), q.get("pnl"), q.get("settled"))
        if action == "reopen":
            _reopen(q)
            shown = info
        elif action == "resettle":
            T._apply_result(q, info, stamp)
            shown = info
        else:
            continue
        after = (q.get("status"), q.get("result"), q.get("pnl"), q.get("settled"))
        if after == before:
            continue
        changes.append(_change(q, before, shown))
    return changes


def paper_pnl(changes):
    """Stake P/L added by the rewrite. Voids carried 0, so this is the new P/L of bets."""
    total = 0.0
    for c in changes:
        if not c["bet"]:
            continue
        total += (c["new_pnl"] or 0.0) - (c["old_pnl"] or 0.0)
    return round(total, 2)


def counts(quotes, fetched):
    """checked / kept void / re-settled / reopened+flagged / not re-checked.

    Markets for the three that describe a fetch, rows for the two that describe
    a rewrite. Combo rows are included in the row counts.
    """
    targets = [q for q in quotes if is_resolver_void(q)]
    # Count from the pre-image. Callers that already mutated must pass the
    # fetched map plus the original target ids; see run().
    markets = sorted({q.get("market_id") for q in targets})
    kept = resettled_m = reopened_m = missed = 0
    for mid in markets:
        kind = fetched.get(mid, ("unknown", None))[0]
        if kind == "void":
            kept += 1
        elif kind in ("a", "b"):
            resettled_m += 1
        elif kind == "review":
            reopened_m += 1
        else:
            missed += 1
    return dict(checked=len(markets), kept_void=kept, resettled_markets=resettled_m,
                reopened_markets=reopened_m, not_rechecked=missed)


def _pace(state, interval):
    gap = interval - (time.monotonic() - state["last"])
    if gap > 0:
        time.sleep(gap)
    state["last"] = time.monotonic()


def fetch_one(slug, state, interval=INTERVAL):
    """(kind, value, error). error is set only when the row must be left alone."""
    url = f"{S.PMUS}/v1/markets/{urllib.parse.quote(str(slug))}/settlement"
    for attempt, backoff in enumerate(RETRY_AFTER):
        _pace(state, interval)
        try:
            req = urllib.request.Request(url, headers={"User-Agent": S.UA, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=20) as resp:
                body = json.load(resp)
            kind, val = S.classify_polymarket_us(body)
            if kind is None:
                return "unknown", None, "non-numeric settlement"
            return kind, val, None
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
            return "unknown", None, f"HTTP {e.code}"
        except Exception as e:
            return "unknown", None, f"{type(e).__name__}"
    return "unknown", None, "HTTP 429"


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


def format_report(changes, market_counts, errors, fetched):
    lines = []
    lines.append("id | market_id | source | bet | old status/result/pnl | new status/result/pnl | settlement")
    lines.append("--- | --- | --- | --- | --- | --- | ---")
    for c in changes:
        old = f"{c['old_status']}/{c['old_result']}/{c['old_pnl']}"
        new = f"{c['new_status']}/{c['new_result']}/{c['new_pnl']}"
        lines.append(" | ".join(str(x) for x in (
            c["id"], c["market_id"], c["source"], "yes" if c["bet"] else "no",
            old, new, _fmt(c["settlement"]))))
    missed = sorted(mid for mid, (kind, _v) in fetched.items() if kind == "unknown")
    lines.append("")
    lines.append(
        f"checked {market_counts['checked']} / kept void 0.5 {market_counts['kept_void']} / "
        f"re-settled {sum(1 for c in changes if c['new_status'] in ('won', 'lost', 'graded'))} / "
        f"reopened+flagged {sum(1 for c in changes if c['new_status'] == 'open')} / "
        f"not re-checked {market_counts['not_rechecked']}")
    lines.append(f"paper P/L effect {paper_pnl(changes):+.2f}")
    if missed:
        lines.append("not re-checked: " + ", ".join(missed))
    if errors:
        lines.append("fetch errors: " + ", ".join(f"{k} ({v})" for k, v in sorted(errors.items())))
    return "\n".join(lines)


def run(apply=False, interval=INTERVAL, load=None, stamp=None):
    d = load() if load else T.load()
    quotes = d["quotes"]
    targets = [q for q in quotes if is_resolver_void(q)]
    market_ids = {q.get("market_id") for q in targets}
    extra = set()
    for q in affected_combos(quotes, market_ids):
        for leg in q.get("legs") or []:
            if leg.get("venue") == "polymarket_us" and leg.get("market_id"):
                extra.add(leg["market_id"])
    slugs = sorted(mid for mid in (market_ids | extra) if mid)
    print(f"  {len(targets)} resolver voids across {len(market_ids)} markets, "
          f"{len(slugs)} fetches", flush=True)
    fetched, errors = fetch_markets(slugs, interval)
    # Counts must see the voids before recheck mutates them.
    market_counts = counts(quotes, fetched)
    stamp = stamp or T.now_iso()
    changes = recheck(quotes, fetched, stamp)
    print(format_report(changes, market_counts, errors, {m: fetched.get(m, ("unknown", None))
                                                         for m in market_ids}))
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
                    help="seconds between settlement requests (default 1.05)")
    args = ap.parse_args(argv)
    run(apply=args.apply, interval=args.sleep)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
