#!/usr/bin/env python3
"""Void the later copy of a contest that was bet twice, once per venue. One-time, idempotent.

A lane that switches venue logs the same contest again under a new market id. Both copies
settle, so the P/L counts twice. Kalshi's start is a placeholder 4.5 to 8.5 hours off the
real start, which is why the old 3-hour check missed them. The earliest logged bet stands.
The later one is voided: status void, P/L 0, note "dup of <kept id>". Its settled time
stays. The kept row is not touched. A price settlement (result "price", settle_px) is
never a target.

The same contest means the same lane, the same two participants, and the same event date
with starts within 12 hours, on a different venue or id scheme. A baseball doubleheader
or series, and a table-tennis rematch, are not the same contest.

Dry-run is the default and writes nothing. --apply writes data/sandbox_ledger.json through
the atomic writer. A row that lives only in data/sandbox_archive/ is voided there too, and
the retired rollup is reduced by what that row had contributed. A second --apply finds
nothing left to void and does not write.

Usage:
  python3 scripts/void_venue_dups.py
  python3 scripts/void_venue_dups.py --dry-run
  python3 scripts/void_venue_dups.py --apply
"""
import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import sandbox_track as T

# Fields a void is allowed to change. Everything else on that row stays, including settled.
_CHANGED = ("status", "pnl", "note")
_WATCH = ("status", "pnl", "note", "result", "settled", "settle_px", "price", "pick",
          "stake", "bet", "market_id", "venue", "source")


def _rows(d):
    """Live quotes, then archived bets, first id wins so a quote is not read twice."""
    seen, out = set(), []
    for q in list(d.get("quotes") or []) + list(d.get("_archive") or []):
        i = q.get("id")
        if i in seen:
            continue
        seen.add(i)
        out.append(q)
    return out


def _bet_rows(d):
    return [q for q in _rows(d) if q.get("bet")]


def totals(d):
    """Pre-fee and after-fee P/L of won/lost bets, plus settled and void counts.

    Price settlements are reported beside that, not inside it: they are not wins or
    losses, and this script does not change them. Archived bets are included once.
    The retired rollup is not added on top of the archive.
    """
    bets = _bet_rows(d)
    decided = [q for q in bets if q.get("status") in ("won", "lost")]
    voids = [q for q in bets if q.get("status") == "void"]
    priced = [q for q in bets if q.get("status") == "settled" and q.get("result") == "price"]
    by_lane = {}
    for q in decided:
        lane = by_lane.setdefault(q.get("source"), {"n": 0, "pnl": 0.0, "pnl_fee": 0.0})
        lane["n"] += 1
        lane["pnl"] += q.get("pnl") or 0.0
        lane["pnl_fee"] += T.pnl_after_fee(q)
    return dict(
        settled=len(decided),
        voids=len(voids),
        pnl=round(sum(q.get("pnl") or 0.0 for q in decided), 2),
        pnl_fee=round(sum(T.pnl_after_fee(q) for q in decided), 2),
        priced=len(priced),
        priced_pnl=round(sum(q.get("pnl") or 0.0 for q in priced), 2),
        lanes=by_lane,
        ids=len(_rows(d)),
    )


def _watch(q):
    return {k: q.get(k) for k in _WATCH}


def _unroll_retired(d, q, old_status, old_pnl):
    """A pruned bet was folded into `retired`. Voiding it takes that P/L back out.

    The row stays in the archive, so the quote and bet counts are unchanged. It is no
    longer a settled win or loss, and its Brier term no longer counts twice.
    """
    r = (d.get("retired") or {}).get(q.get("source"))
    if not r:
        return
    r["settled"] = r.get("settled", 0) - 1
    if old_status == "won":
        r["won"] = r.get("won", 0) - 1
    r["staked"] = round(r.get("staked", 0.0) - float(q.get("stake") or 0.0), 2)
    r["pnl"] = round(r.get("pnl", 0.0) - float(old_pnl or 0.0), 2)
    if (q.get("result") in ("a", "b") and not q.get("untraded")
            and q.get("prob_a") is not None):
        term = (q["prob_a"] - (1.0 if q["result"] == "a" else 0.0)) ** 2
        r["brier_sum"] = r.get("brier_sum", 0.0) - term
        r["brier_n"] = r.get("brier_n", 0) - 1


def apply_voids(d):
    """Void the later copy of each settled cross-venue pair. Returns the change list.

    Idempotent: a row already void is not a pair, so a second call returns nothing and
    changes nothing. Price rows are never in the pair list.
    """
    live_ids = {q.get("id") for q in d.get("quotes") or []}
    changes = []
    for later, kept in T.settled_cross_venue_dups(_rows(d)):
        old_status, old_pnl = later.get("status"), later.get("pnl")
        old_settled = later.get("settled")
        later["status"] = "void"
        later["pnl"] = 0.0
        later["note"] = f"dup of {kept.get('id')}"
        if later.get("settled") != old_settled:
            later["settled"] = old_settled
        if later.get("id") not in live_ids:
            _unroll_retired(d, later, old_status, old_pnl)
            month = str(old_settled or "")[:7]
            if month:
                d.setdefault("_archive_dirty", set()).add(month)
        changes.append(dict(
            voided_id=later.get("id"), kept_id=kept.get("id"), lane=later.get("source"),
            result=old_status, pnl_before=old_pnl, settled=old_settled,
            sport=later.get("sport"), venue=later.get("venue"),
            side_a=later.get("side_a"), side_b=later.get("side_b"),
        ))
    return changes


def _money(n):
    return f"{n:+,.2f}"


def format_report(changes, before, after, confirm):
    lines = []
    lines.append("voided id | kept id | lane | result | pnl before")
    lines.append("--- | --- | --- | --- | ---")
    for c in changes:
        lines.append(" | ".join(str(x) for x in (
            c["voided_id"], c["kept_id"], c["lane"], c["result"], c["pnl_before"])))
    lines.append("")
    lines.append(f"pairs voided: {len(changes)}")
    lines.append(
        f"P/L before: pre-fee {_money(before['pnl'])}  after-fee {_money(before['pnl_fee'])}  "
        f"settled {before['settled']}  void {before['voids']}")
    lines.append(
        f"P/L after:  pre-fee {_money(after['pnl'])}  after-fee {_money(after['pnl_fee'])}  "
        f"settled {after['settled']}  void {after['voids']}")
    lines.append(
        f"price settlements unchanged: {after['priced']} rows, P/L {_money(after['priced_pnl'])}")
    lines.append("per-lane P/L change (pre-fee, after-fee):")
    lanes = sorted(set(before["lanes"]) | set(after["lanes"]))
    for name in lanes:
        b, a = before["lanes"].get(name) or {}, after["lanes"].get(name) or {}
        dp = round((a.get("pnl") or 0.0) - (b.get("pnl") or 0.0), 2)
        df = round((a.get("pnl_fee") or 0.0) - (b.get("pnl_fee") or 0.0), 2)
        if dp or df:
            lines.append(f"  {name}: pre-fee {_money(dp)}  after-fee {_money(df)}")
    lines.append(confirm)
    return "\n".join(lines)


def confirm_untouched(before_snap, d, voided_ids):
    """No win or loss outside the voided copies moved, and no id disappeared."""
    after = {q.get("id"): _watch(q) for q in _rows(d)}
    if set(before_snap) != set(after):
        lost = sorted(set(before_snap) - set(after))
        gained = sorted(set(after) - set(before_snap))
        return f"NOT CONFIRMED: ids lost {lost[:5]} gained {gained[:5]}"
    moved = []
    for i, old in before_snap.items():
        new = after[i]
        if i in voided_ids:
            changed = [k for k in _WATCH if old.get(k) != new.get(k)]
            if set(changed) - set(_CHANGED) or new.get("settled") != old.get("settled"):
                moved.append(i)
            continue
        if old.get("status") in ("won", "lost") and old != new:
            moved.append(i)
        if old.get("result") == "price" and old != new:
            moved.append(i)
    if moved:
        return f"NOT CONFIRMED: unexpected edits {moved[:8]}"
    return (f"confirmed: {len(voided_ids)} voided copies changed, no other win or loss moved, "
            f"no price row changed, no ids lost ({len(after)} ids)")


def write_ledger(d, path=None):
    """Replace the ledger atomically. Archive months are rewritten only when a void landed there."""
    dirty = d.pop("_archive_dirty", set())
    archive = d.pop("_archive", None)
    body = {k: v for k, v in d.items() if k not in ("_archive", "_archive_dirty")}
    ids = [q.get("id") for q in body.get("quotes") or []]
    if len(ids) != len(set(ids)):
        raise SystemExit("duplicate quote ids; ledger not written")
    try:
        T.atomic_write_json(path or T.LEDGER, body, prefix=".ledger-")
        if dirty and archive is not None:
            T.save_archive(archive, dirty)
    finally:
        if archive is not None:
            d["_archive"] = archive


def run(apply=False, load=None, path=None):
    d = load() if load else T.load()
    before = totals(d)
    snap = {q.get("id"): _watch(q) for q in _rows(d)}
    changes = apply_voids(d)
    after = totals(d)
    confirm = confirm_untouched(snap, d, {c["voided_id"] for c in changes})
    print(format_report(changes, before, after, confirm))
    if apply and changes:
        write_ledger(d, path)
        print(f"  wrote {len(changes)} void(s)")
    elif apply:
        print("  no changes; ledger not written")
    return changes


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="report the voids and write nothing (the default)")
    mode.add_argument("--apply", action="store_true", help="void the later copy of each pair and write the ledger")
    args = ap.parse_args()
    run(apply=args.apply)
    return 0


if __name__ == "__main__":
    sys.exit(main())
