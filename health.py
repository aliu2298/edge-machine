#!/usr/bin/env python3
"""health.py — guardrails for the boards.

The real risk here is SILENT failure, not loud failure. A lead whose fixture never matches
a final score just sits "pending" forever; a venue feed that quietly returns nothing
makes every market button vanish with no error anywhere. Both look fine on the page.

Writes GitHub Actions annotations so problems land on the run summary rather than being
buried in step logs.

Exit code is 0 by default: a warning must never block the Pages deploy, because a stale
board is worse than a flagged one. Pass --strict to exit 1 instead.

Usage:  python3 health.py [--strict]
"""
import json, os, sys, datetime

ROOT = os.path.dirname(os.path.abspath(__file__))
LEADS = os.path.join(ROOT, "data", "streaks.json")
LEDGER = os.path.join(ROOT, "data", "streak_leads.json")
BOOK = os.path.join(ROOT, "data", "book_ledger.json")

SETTLE_GRACE_DAYS = 2      # a match may legitimately be ungraded the morning after
LEADS_STALE_HOURS = 36     # the daily job should be refreshing this
LINK_HORIZON_DAYS = 3      # a sportsbook prices this far out; beyond it no line is normal


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
            note("warning", "NO LEADS — expected during the summer break (World Cup + "
                            "European off-season); suspicious otherwise.")
            problems += 1
    except Exception as e:
        note("error", f"LEADS unreadable: {e}")
        return 1

    # 2. LEDGER — pending leads that can never grade.
    #
    # A lead whose match finished days ago and never matched a final score is the silent
    # failure this file exists for: it renders as a normal pending row. A fixture that
    # VANISHES from the feed can never grade, so waiting out the ledger's 7-day void tells
    # us nothing new. FC Utrecht v Go Ahead Eagles (2026-09-05) was abandoned, dropped out
    # of ESPN entirely, and sat pending for a week. Flag it as soon as it is a day overdue
    # AND absent from the feed.
    board = []                            # near-term leads, for the venue check below
    try:
        ledger = json.load(open(LEDGER)).get("leads", {})
        pending = [e for e in ledger.values() if e.get("status") == "pending"]
        settled = len(ledger) - len(pending)
        print(f"  ledger: {len(pending)} pending, {settled} settled")
        try:
            import streaks_fetch
            known = {(f["date"], f["home"], f["away"])
                     for f in streaks_fetch.load_or_fetch()["fixtures"]}
        except Exception:
            known = set()             # no feed, no claim: stay silent rather than guess
        today = now.date()
        flagged = set()
        for e in pending:
            try:
                age = (today - datetime.date.fromisoformat(e["date"])).days
            except (KeyError, ValueError):
                continue
            key = (e["date"], e["home"], e["away"])
            if age > 1 and known and key not in known and key not in flagged:
                flagged.add(key)
                note("warning", f"GONE {e['match']} ({e['date']}) was {age}d ago and is "
                                f"no longer in the fixture feed — abandoned, postponed "
                                f"or moved; it can never grade")
                problems += 1
            elif age > SETTLE_GRACE_DAYS and key not in flagged:
                flagged.add(key)
                note("warning", f"STUCK pending lead {e['match']} ({e['date']}, {age}d "
                                f"ago) never graded — the fixture may have moved, or "
                                f"team names drifted from ESPN's")
                problems += 1

        # The ledger must never carry a venue URL. Links resolve at RENDER time so a
        # venue switch takes effect on leads already logged; a stored URL silently
        # outlives the switch.
        stored = sorted({k for e in ledger.values() if isinstance(e, dict)
                         for k, v in e.items() if isinstance(v, str) and "://" in v})
        if stored:
            note("warning", f"LEDGER stores venue URLs in {stored} — links must "
                            f"resolve at render time, not be frozen at publish")
            problems += 1

        horizon = now + datetime.timedelta(days=LINK_HORIZON_DAYS)
        for l in blob.get("leads", []):
            try:
                ko = datetime.datetime.fromisoformat(
                    (l.get("kickoff") or "").replace("Z", "+00:00"))
            except ValueError:
                continue
            if now < ko <= horizon:
                board.append(l)
    except Exception as e:
        note("warning", f"LEDGER check skipped: {e}")

    # 2b. BOOK LEDGER — prices every fixture inside 24h. A silently-empty book feed
    # shows up here as a ledger that stops growing while fixtures keep kicking off.
    try:
        bk = json.load(open(BOOK))
        rows = bk.get("rows", {})
        pend = sum(1 for r in rows.values() if r.get("status") == "pending")
        upd = datetime.datetime.fromisoformat(bk["updated_at"]) if bk.get("updated_at") else None
        age = (now - upd).total_seconds() / 3600 if upd else None
        print(f"  book: {len(rows)} fixtures priced, {pend} pending"
              + (f", written {age:.1f}h ago" if age is not None else ""))
        if age is not None and age > LEADS_STALE_HOURS:
            note("warning", f"BOOK ledger last written {age:.0f}h ago — is book_track "
                            f"running?")
            problems += 1
    except FileNotFoundError:
        print("  book: no ledger yet")
    except Exception as e:
        note("warning", f"BOOK check skipped: {e}")

    # 3. VENUE PRICES — leads are priced on Kalshi and Polymarket US (Bovada until
    # 2026-09-13, when it started failing every request and nothing said so). A feed
    # returning nothing is indistinguishable from "no market exists" unless something
    # explicitly looks, so both venues answering nothing at all is a warning.
    #
    # Coverage is only meaningful NEAR TERM: a sportsbook prices the next few days and
    # posts distant fixtures closer to kickoff, so a lead two weeks out legitimately has
    # no line yet. Only leads inside LINK_HORIZON_DAYS are checked — a fixture that has
    # kicked off has no pre-match market by definition, and counting those as misses
    # made the check read "3/5" while the board was in fact fully linked.
    try:
        import venue_book as VB
        if board:
            miss = []
            for p in board:
                k = VB.fixture_key(p)
                if not (k and VB.fixture_quotes(k)):
                    miss.append(p)
            print(f"  venue prices: {len(board)-len(miss)}/{len(board)} leads inside "
                  f"{LINK_HORIZON_DAYS}d ({VB.STATS['calls']} calls, {VB.STATS['errors']} failed)")
            for p in miss:
                print(f"    (no venue price for {p['match']})")
            if len(miss) == len(board) and VB.STATS["errors"]:
                note("warning", f"PRICES no lead priced on either venue and {VB.STATS['errors']} "
                                f"venue reads failed — Kalshi / Polymarket US unreachable?")
                problems += 1
    except Exception as e:
        note("warning", f"PRICES check skipped: {e}")

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
