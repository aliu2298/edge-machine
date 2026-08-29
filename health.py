#!/usr/bin/env python3
"""health.py — guardrails for the boards.

The real risk here is SILENT failure, not loud failure. A pick whose fixture never matches
a final score just sits "live" forever; a Kalshi series ticker that quietly returns nothing
makes every market button vanish with no error anywhere. Both look fine on the page.

Writes GitHub Actions annotations so problems land on the run summary rather than being
buried in step logs.

Exit code is 0 by default: a warning must never block the Pages deploy, because a stale
board is worse than a flagged one. Pass --strict to exit 1 instead.

Usage:  python3 health.py [--strict]
"""
import json, os, sys, datetime

ROOT = os.path.dirname(os.path.abspath(__file__))
SLATE = os.path.join(ROOT, "data", "slate.json")
LEADS = os.path.join(ROOT, "data", "streaks.json")

SETTLE_GRACE_DAYS = 2      # a match may legitimately be ungraded the morning after
LEADS_STALE_HOURS = 36     # the daily job should be refreshing this


def note(level, msg):
    """GitHub Actions annotation; plain text when run locally."""
    if os.environ.get("GITHUB_ACTIONS"):
        print(f"::{level}::{msg}")
    else:
        print(f"  [{level.upper()}] {msg}")


def main():
    strict = "--strict" in sys.argv
    now = datetime.datetime.now(datetime.timezone.utc)
    problems = 0

    # 1. LEADS FRESHNESS — everything downstream is drawn from this file.
    try:
        blob = json.load(open(LEADS))
        built = datetime.datetime.fromisoformat(blob["built_at"])
        hrs = (now - built).total_seconds() / 3600
        n_leads = len(blob.get("leads", []))
        if hrs > LEADS_STALE_HOURS:
            note("warning", f"STALE streaks.json is {hrs:.0f}h old "
                            f"(expected within {LEADS_STALE_HOURS}h) — is the cron running?")
            problems += 1
        print(f"  leads: {n_leads} ({hrs:.1f}h old)")
        if n_leads == 0:
            note("warning", "NO LEADS — the slate cannot refill. Expected during the "
                            "summer break (World Cup + European off-season); "
                            "suspicious otherwise.")
            problems += 1
    except Exception as e:
        note("error", f"LEADS unreadable: {e}")
        return 1

    # 2. SLATE — stuck picks, and whether the board is actually full.
    try:
        import slate as S
        sb = S.load(SLATE)
        live = S.live_picks(sb)
        settled = [p for p in sb["picks"].values() if p["status"] != "live"]
        print(f"  slate: {len(live)} live, {len(settled)} settled")

        # A live pick whose match finished days ago never matched a final score. That is
        # the silent failure this file exists for — it renders as a normal pending card.
        for p in live:
            ko = S._dt(p.get("kickoff"))
            if ko and (now - ko).days > SETTLE_GRACE_DAYS:
                note("warning", f"STUCK live pick {p['match']} ({p['date']}, "
                                f"{(now-ko).days}d ago) never graded — the fixture may "
                                f"have moved, or team names drifted from ESPN's")
                problems += 1

        if len(live) < S.SLATE_SIZE and n_leads:
            note("warning", f"SLATE only {len(live)}/{S.SLATE_SIZE} filled while "
                            f"{n_leads} leads exist — selection may be over-constrained")
            problems += 1
    except Exception as e:
        note("warning", f"SLATE check skipped: {e}")

    # 3. VENUE LINKS — a series ticker returning zero events is indistinguishable from
    # "no market exists" unless something explicitly looks. KXUEFAGAME looked right,
    # returned HTTP 200, and was empty; every Europa card lost its button silently.
    try:
        from venues import fetch_kalshi_events, venue_link, kalshi_series_counts
        for series, n in sorted(kalshi_series_counts().items()):
            if n == 0:
                note("warning", f"LINKS series {series} returned 0 events — wrong ticker? "
                                f"(KXUEFAGAME was empty while Europa lived under KXUELGAME)")
                problems += 1
        if live:
            events = fetch_kalshi_events()
            miss = [p for p in live
                    if not venue_link(p["match"].replace(" v ", " vs "),
                                      p.get("kickoff") or p["date"], events)]
            print(f"  kalshi links: {len(live)-len(miss)}/{len(live)} live picks")
            # Not every fixture has a market, so a miss is informational, not a problem.
            for p in miss:
                print(f"    (no market for {p['match']})")
    except Exception as e:
        note("warning", f"LINKS check skipped: {e}")

    print(f"  issues: {problems}")
    if not problems:
        print("  ✅ all checks passed")
    return 1 if (problems and strict) else 0


if __name__ == "__main__":
    # A guardrail must never be able to break the thing it guards. main() is warn-only by
    # exit code, but an unhandled exception bypassed that once and failed the pipeline for
    # three days. Any unexpected error is reported and swallowed unless --strict is asked.
    try:
        sys.exit(main())
    except Exception as e:
        import traceback
        note("warning", f"health crashed ({type(e).__name__}: {e}) — "
                        f"checks skipped, pipeline continues")
        traceback.print_exc()
        sys.exit(1 if "--strict" in sys.argv else 0)
