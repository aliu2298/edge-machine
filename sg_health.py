#!/usr/bin/env python3
"""sg_health.py — guardrails for the tips pipeline.

The real risk in this pipeline is SILENT failure, not loud failure:

  * A fixture whose teams don't match ESPN never settles. It just sits as "pending"
    and keeps rendering as though it were an upcoming game. That happened to
    Vancouver v LAFC — ESPN calls them "LAFC" and sportsgambler "Los Angeles FC",
    so no token overlapped, and a two-day-old match showed under "Upcoming" for days
    with nothing anywhere reporting a problem.
  * A parser that breaks against a site redesign yields empty fields, not an error —
    the board renders, just emptier, and nothing complains.

This checks for both and writes GitHub Actions annotations so they land on the run
summary instead of being buried in step logs.

Exit code is 0 by default: a warning must never block the Pages deploy, because a
stale board is worse than a flagged one. Pass --strict to exit 1 instead (useful
locally, or if you later want the run marked red).

Usage:  python3 sg_health.py [--strict]
"""
import json, os, sys, datetime

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, "data", "sg_picks.json")

SETTLE_GRACE_DAYS = 2      # a match may legitimately be ungraded the morning after
STALE_AFTER_HOURS = 36     # data file should be refreshed daily
MIN_PARSE_RATE = 0.80      # share of upcoming rows that must carry a published tip
MIN_PARSE_SAMPLE = 8       # below this, one blank field swings the rate — too noisy to act on


def note(level, msg):
    """GitHub Actions annotation; plain text when run locally."""
    if os.environ.get("GITHUB_ACTIONS"):
        print(f"::{level}::{msg}")
    else:
        print(f"  [{level.upper()}] {msg}")


def main():
    strict = "--strict" in sys.argv
    if not os.path.exists(DATA):
        note("error", "data/sg_picks.json missing — the scrape never produced output")
        return 1
    blob = json.load(open(DATA))
    picks = blob.get("picks", [])
    today = datetime.date.today()
    problems = 0

    print(f"checking {len(picks)} rows (updated {blob.get('updated_at','?')})")

    # 1. STUCK — past its match date but never graded.
    stuck = []
    for p in picks:
        if p.get("status") != "pending":
            continue
        try:
            age = (today - datetime.date.fromisoformat(p.get("date", ""))).days
        except ValueError:
            continue
        if age > SETTLE_GRACE_DAYS:
            stuck.append((age, p))
    for age, p in sorted(stuck, reverse=True):
        note("warning", f"STUCK {age}d unsettled: {p.get('match')} ({p.get('league')}) "
                        f"{p.get('date')} — likely an ESPN team-name mismatch; "
                        f"add an entry to ALIASES in sg_settle.py")
    problems += len(stuck)

    # 2. STALE — the daily job hasn't refreshed the file.
    try:
        upd = datetime.datetime.fromisoformat(blob["updated_at"])
        hrs = (datetime.datetime.now(datetime.timezone.utc) - upd).total_seconds() / 3600
        if hrs > STALE_AFTER_HOURS:
            note("warning", f"STALE data: last updated {hrs:.0f}h ago "
                            f"(expected within {STALE_AFTER_HOURS}h) — is the cron running?")
            problems += 1
    except Exception:
        note("warning", "STALE check skipped: updated_at missing or unparseable")

    # 3. PARSE — upcoming rows should carry the three tracked fields.
    upcoming = [p for p in picks if p.get("status") == "pending"
                and (p.get("date") or "") >= today.isoformat()]
    if len(upcoming) >= MIN_PARSE_SAMPLE:
        for field, label in (("tip_text", "published tip"),
                             ("proj_score", "projected score"),
                             ("btts_yes_odds", "BTTS odds")):
            have = sum(1 for p in upcoming if p.get(field))
            rate = have / len(upcoming)
            if rate < MIN_PARSE_RATE:
                note("warning", f"PARSE {label}: only {have}/{len(upcoming)} upcoming rows "
                                f"({rate:.0%}) — sportsgambler's markup may have changed")
                problems += 1
    elif upcoming:
        print(f"  parse check skipped: only {len(upcoming)} upcoming rows "
              f"(need {MIN_PARSE_SAMPLE})")
    print(f"  upcoming rows: {len(upcoming)}")

    # 4. LINKS — Kalshi buttons actually resolving for upcoming fixtures.
    #
    # This is the check that was missing when KXUEFAGAME (an EMPTY series) meant every
    # Europa League card rendered with no Kalshi button. The lookup fails soft by design,
    # so a wrong series ticker is indistinguishable from "no market exists" unless
    # something explicitly looks. Two signals:
    #   a) a configured series returning zero events  -> almost certainly a bad ticker
    #   b) a league with several fixtures but zero links -> that league's series is wrong
    # Overall coverage is deliberately NOT alerted on: plenty of fixtures genuinely have
    # no Kalshi market, so a global rate would cry wolf.
    try:
        from export_public import fetch_kalshi_events, venue_link, kalshi_series_counts

        for series, n in sorted(kalshi_series_counts().items()):
            if n == 0:
                note("warning", f"LINKS series {series} returned 0 events — wrong ticker? "
                                f"(KXUEFAGAME was empty while Europa lived under KXUELGAME)")
                problems += 1

        if upcoming:
            events = fetch_kalshi_events()
            by_league, linked = {}, {}
            for p in upcoming:
                lg = p.get("league") or "?"
                by_league[lg] = by_league.get(lg, 0) + 1
                if venue_link((p.get("match") or "").replace(" v ", " vs "),
                              p.get("date"), events):
                    linked[lg] = linked.get(lg, 0) + 1
            for lg, total in sorted(by_league.items()):
                got = linked.get(lg, 0)
                if total >= 2 and got == 0:
                    note("warning", f"LINKS {lg}: 0 of {total} upcoming fixtures got a Kalshi "
                                    f"link — check that league's series ticker in KALSHI_SERIES")
                    problems += 1
            tot_linked, tot = sum(linked.values()), len(upcoming)
            print(f"  kalshi links: {tot_linked}/{tot} upcoming "
                  f"({', '.join(f'{l} {linked.get(l,0)}/{n}' for l, n in sorted(by_league.items()))})")
    except Exception as e:
        note("warning", f"LINKS check skipped: {e}")

    # 5. UNGRADED — settled but the grader couldn't score the tip.
    ungraded = [p for p in picks if p.get("status") == "settled"
                and p.get("tip_result") == "ungraded"]
    for p in ungraded:
        note("warning", f"UNGRADED tip (market type not handled): "
                        f"{p.get('match')} — {p.get('tip_text')}")
    problems += len(ungraded)

    settled = sum(1 for p in picks if p.get("status") == "settled")
    print(f"  settled: {settled} | pending: {len(picks)-settled} | issues: {problems}")
    if not problems:
        print("  ✅ all checks passed")
    return 1 if (problems and strict) else 0


if __name__ == "__main__":
    sys.exit(main())
