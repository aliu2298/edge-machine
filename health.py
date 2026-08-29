#!/usr/bin/env python3
"""health.py — guardrails for the picks pipeline.

The real risk in this pipeline is SILENT failure, not loud failure. A pick whose
kickoff date is wrong, or whose teams don't match a venue's naming, simply keeps
rendering as "upcoming" forever with nothing anywhere reporting a problem.

This checks for that and writes GitHub Actions annotations so issues land on the run
summary instead of being buried in step logs.

Exit code is 0 by default: a warning must never block the Pages deploy, because a
stale board is worse than a flagged one. Pass --strict to exit 1 instead (useful
locally, or if you later want the run marked red).

Usage:  python3 health.py [--strict]
"""
import json, os, sys, datetime

ROOT = os.path.dirname(os.path.abspath(__file__))
MIRROR = os.path.join(ROOT, "data", "predictions.json")   # sports board source

SETTLE_GRACE_DAYS = 2      # a match may legitimately be ungraded the morning after


def note(level, msg):
    """GitHub Actions annotation; plain text when run locally."""
    if os.environ.get("GITHUB_ACTIONS"):
        print(f"::{level}::{msg}")
    else:
        print(f"  [{level.upper()}] {msg}")


def main():
    strict = "--strict" in sys.argv
    if not os.path.exists(MIRROR):
        note("error", "data/predictions.json missing — nothing to check")
        return 1
    rows = json.load(open(MIRROR)).get("picks", [])
    today = datetime.date.today()
    problems = 0

    print(f"checking {len(rows)} picks")

    # Kalshi buttons actually resolving for upcoming fixtures.
    #
    # The lookup fails soft by design, so a wrong series ticker is indistinguishable from
    # "no market exists" unless something explicitly looks. Two signals:
    #   a) a configured series returning zero events  -> almost certainly a bad ticker
    #      (KXUEFAGAME was empty while Europa actually lived under KXUELGAME)
    #   b) a pick with no link -> usually a wrong kickoff DATE, since venue_link only
    #      accepts a ±1 day gap. That is exactly how pick #122 was caught — a Europa tie
    #      dated Tuesday when the competition plays Thursday.
    try:
        from export_public import fetch_kalshi_events, venue_link, kalshi_series_counts

        for series, n in sorted(kalshi_series_counts().items()):
            if n == 0:
                note("warning", f"LINKS series {series} returned 0 events — wrong ticker? "
                                f"(KXUEFAGAME was empty while Europa lived under KXUELGAME)")
                problems += 1

        events = fetch_kalshi_events()
        _own_pending = [p for p in rows if p.get("status") == "pending"
                        and p.get("sport") not in (None, "kalshi")]

        # Own picks whose kickoff has passed but are still pending. Without this a pick
        # filed on the WRONG DAY simply drops out of the coverage window and stops being
        # checked at all — reverting #122 to its bad Tuesday date made it vanish from the
        # count rather than raise anything.
        for p in _own_pending:
            ko = (p.get("kickoff") or p.get("event_date") or "")[:10]
            try:
                age = (today - datetime.date.fromisoformat(ko)).days
            except ValueError:
                continue
            if age > SETTLE_GRACE_DAYS:
                note("warning", f"STUCK own pick #{p.get('id')} {p.get('match')} "
                                f"({ko}, {age}d) still pending — settle it, or the "
                                f"kickoff date is wrong")
                problems += 1

        # Coverage window includes the grace period, so a just-passed pick is still
        # examined rather than silently falling out of scope.
        cutoff = (today - datetime.timedelta(days=SETTLE_GRACE_DAYS)).isoformat()
        own = [p for p in _own_pending
               if (p.get("kickoff") or p.get("event_date") or "")[:10] >= cutoff]
        if own:
            miss = [p for p in own
                    if not venue_link(p.get("match", ""),
                                      p.get("kickoff") or p.get("event_date"), events)]
            print(f"  kalshi links: {len(own)-len(miss)}/{len(own)} upcoming")
            for p in miss:
                note("warning", f"LINKS no Kalshi match for own pick #{p.get('id')} "
                                f"{p.get('match')} ({(p.get('kickoff') or '')[:10]}) — "
                                f"check the kickoff date is right; venue_link allows only "
                                f"±1 day")
            problems += len(miss)
    except Exception as e:
        note("warning", f"LINKS check skipped: {e}")

    # predictions rows carry a graded status (win/loss/half_*/void), not a "settled" flag —
    # reuse export_public's tuple so the two stay in step.
    from export_public import SETTLED
    settled = sum(1 for p in rows if p.get("status") in SETTLED)
    pending = sum(1 for p in rows if p.get("status") == "pending")
    print(f"  settled: {settled} | pending: {pending} | issues: {problems}")
    if not problems:
        print("  ✅ all checks passed")
    return 1 if (problems and strict) else 0


if __name__ == "__main__":
    # A guardrail must never be able to break the thing it guards. main() is warn-only by
    # exit code, but an unhandled exception bypassed that and failed the pipeline for three
    # days (a TypeError sorting stuck picks). Any unexpected error is now reported and
    # swallowed, unless --strict is explicitly requested.
    try:
        sys.exit(main())
    except Exception as e:
        import traceback
        note("warning", f"health crashed ({type(e).__name__}: {e}) — "
                        f"checks skipped, pipeline continues")
        traceback.print_exc()
        sys.exit(1 if "--strict" in sys.argv else 0)
