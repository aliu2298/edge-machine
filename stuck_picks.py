"""stuck_picks.py — picks still open long after they started, per lane ledger (2026-11-16).

    python3 stuck_picks.py              every data/*.json ledger that holds picks or rows, stuck ones and each ledger's last_run age
    python3 stuck_picks.py --hours 24   a different threshold (default 12 hours past the start)
    python3 stuck_picks.py --quiet      only the ledgers that have stuck picks or a stale last_run

One line per ledger: `<file>  stuck N  last_run <age>  <tickers...>`. A pick is STUCK when its status is "open" and its start (start,
kickoff, start_time, or the end of its `day`) is more than --hours behind. A pick with no readable start is counted as "no start" and
not as stuck. The last_run age is the ledger's own `last_run`. Read-only: nothing is written. Exit 0 always; the daily check reads it.
"""
import datetime as dt
import glob
import json
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
STALE_RUN_H = 6.0                                  # a last_run older than this is flagged
# Lanes that no longer run: a old last_run is expected, so it is marked "retired" instead of STALE.
RETIRED = {"nba_safe_card.json", "nfl_tt_ledger.json", "nfl_tt_main1_ledger.json", "nhl_goal_lanes_ledger.json",
           "gold_orb_ledger.json", "tennis_totals_ledger.json"}
START_KEYS = ("start", "kickoff", "start_time", "game_start", "close_time")
TICKER_KEYS = ("ticker", "market_id", "id", "event")


def _when(v):
    try:
        t = dt.datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except ValueError:
        return None
    return t if t.tzinfo else t.replace(tzinfo=dt.timezone.utc)


# A perpetual (Kalshi Invest *PERP, rebound.py) has no start: an open position closes on its stop, its target or a time stop counted
# in REGULAR-HOURS minutes (at most 5 sessions), so one entered on a Friday evening is rightly open all weekend. It counts as stuck
# only once its entry is older than the longest time stop could take in calendar days (5 sessions + a weekend + a holiday).
PERP_MAX_DAYS = 9


def start_of(row):
    """The row's start as an aware datetime, or None. A bare `day` counts as the end of that UTC day."""
    if str(row.get("ticker") or "").endswith("PERP") and isinstance(row.get("entry_ts"), (int, float)):
        return dt.datetime.fromtimestamp(row["entry_ts"], dt.timezone.utc) + dt.timedelta(days=PERP_MAX_DAYS)
    for k in START_KEYS:
        t = _when(row[k]) if row.get(k) else None
        if t:
            return t
    d = _when(row["day"]) if row.get("day") else None
    return d + dt.timedelta(days=1) if d else None


def walk(node, depth=0):
    """Every dict that has status == 'open' (the ledgers nest picks under rules/lanes/entries/rows)."""
    if depth > 6:
        return
    if isinstance(node, dict):
        if node.get("status") == "open":
            yield node
        for v in node.values():
            if isinstance(v, (dict, list)):
                yield from walk(v, depth + 1)
    elif isinstance(node, list):
        for v in node:
            yield from walk(v, depth + 1)


def label(row):
    for k in TICKER_KEYS:
        if row.get(k):
            return str(row[k])
    return "?"


def scan(data, now, hours):
    """(stuck [(label, hours_past)], no_start, open_total) for one ledger's JSON."""
    stuck, no_start, total = [], 0, 0
    for r in walk(data):
        total += 1
        if r.get("bet") is False:       # an observation quote the tracker logged, never a pick: it grades when its venue settles (gas: Kalshi closes, then settles days later)
            continue
        if r.get("quote") is False:     # a "no quote" shadow record (shadows.py): no market was priced, so there is nothing to settle
            continue
        t = start_of(r)
        if t is None:
            no_start += 1
        elif now - t > dt.timedelta(hours=hours):
            stuck.append((label(r) + (f" [venue {r['venue_status']}]" if r.get("venue_status") else ""), (now - t).total_seconds() / 3600))
    return sorted(stuck, key=lambda x: -x[1]), no_start, total


def age(data, now):
    """Hours since the ledger's own last_run, or None."""
    t = _when(data.get("last_run")) if isinstance(data, dict) and data.get("last_run") else None
    return (now - t).total_seconds() / 3600 if t else None


def report(root=None, now=None, hours=12.0, quiet=False):
    now = now or dt.datetime.now(dt.timezone.utc)
    lines, n_stuck = [], 0
    for path in sorted(glob.glob(os.path.join(root or ROOT, "data", "*.json"))):
        try:
            with open(path) as f:
                data = json.load(f)
        except (OSError, ValueError):
            continue
        if not isinstance(data, dict):
            continue
        stuck, no_start, total = scan(data, now, hours)
        a = age(data, now)
        if not total and a is None:
            continue                                   # not a lane ledger
        if not total and not stuck and quiet:
            continue
        retired = os.path.basename(path) in RETIRED
        flag = a is not None and a > STALE_RUN_H and not retired
        if quiet and not stuck and not flag:
            continue
        n_stuck += len(stuck)
        shown = ", ".join(f"{t} ({h:.0f}h)" for t, h in stuck[:12]) + (f" +{len(stuck) - 12} more" if len(stuck) > 12 else "")
        lines.append(f"{os.path.basename(path):42} stuck {len(stuck):3}  open {total:3}"
                     + (f" ({no_start} no start)" if no_start else "")
                     + f"  last_run {'%.1fh ago' % a if a is not None else 'none'}{'  STALE' if flag else '  retired' if retired else ''}"
                     + (f"  {shown}" if stuck else ""))
    lines.append(f"{n_stuck} stuck pick(s) open more than {hours:g}h after their start")
    return lines, n_stuck


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    hours = float(argv[argv.index("--hours") + 1]) if "--hours" in argv else 12.0
    lines, _ = report(hours=hours, quiet="--quiet" in argv)
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
