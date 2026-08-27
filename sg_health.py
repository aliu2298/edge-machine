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
MIRROR = os.path.join(ROOT, "data", "predictions.json")   # sports board source

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
    # Sort on age ONLY. `sorted(stuck, reverse=True)` compared the tuples, so two picks
    # with the SAME age fell through to comparing the dicts and raised TypeError — which
    # crashed the whole run for three days. Never sort tuples whose tail isn't orderable.
    for age, p in sorted(stuck, key=lambda x: -x[0]):
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
            print(f"  kalshi links (tips): {tot_linked}/{tot} upcoming "
                  f"({', '.join(f'{l} {linked.get(l,0)}/{n}' for l, n in sorted(by_league.items()))})")

        # Same check for the SPORTS board, which is a different data source
        # (data/predictions.json, the user's own picks). Here a missing link is usually
        # a wrong kickoff DATE rather than a bad series ticker: venue_link only accepts a
        # ±1 day gap, so a pick filed on the wrong day silently loses its button. That is
        # exactly how pick #122 was caught — a Europa tie dated Tuesday when the
        # competition plays Thursday.
        if os.path.exists(MIRROR):
            rows = json.load(open(MIRROR)).get("picks", [])
            _own_pending = [p for p in rows if p.get("status") == "pending"
                            and p.get("sport") not in (None, "kalshi")]

            # Own picks whose kickoff has passed but are still pending. Without this a
            # pick filed on the WRONG DAY simply drops out of the coverage window and
            # stops being checked at all — reverting #122 to its bad Tuesday date made it
            # vanish from the count rather than raise anything.
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
                print(f"  kalshi links (sports): {len(own)-len(miss)}/{len(own)} upcoming")
                for p in miss:
                    note("warning", f"LINKS no Kalshi match for own pick #{p.get('id')} "
                                    f"{p.get('match')} ({(p.get('kickoff') or '')[:10]}) — "
                                    f"check the kickoff date is right; venue_link allows only "
                                    f"±1 day")
                problems += len(miss)
    except Exception as e:
        note("warning", f"LINKS check skipped: {e}")

    # 5. BTTS CROSS-CHECK — the tip grader and the market-implied BTTS tracker are two
    # independent paths to the same fact. When the tip IS a BTTS bet they must agree; a
    # disagreement means one of them is wrong, which is far more useful than either being
    # quietly wrong on its own.
    for p in picks:
        tip = (p.get("tip_text") or "").lower()
        if "both teams to score" not in tip or p.get("status") != "settled":
            continue
        res, actual = p.get("tip_result"), p.get("btts_actual")
        if res in (None, "ungraded") or actual is None:
            continue
        backed_yes = "- yes" in tip or "yes @" in tip
        should_win = (actual == "Yes") == backed_yes
        if (res == "win") != should_win:
            note("warning", f"BTTS MISMATCH {p.get('match')}: tip '{p.get('tip_text')}' "
                            f"graded {res} but btts_actual={actual} — grader disagrees with "
                            f"the market tracker, one of them is wrong")
            problems += 1

    # 6. UNGRADED — settled but the grader couldn't score the tip.
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
    # A guardrail must never be able to break the thing it guards. main() is warn-only by
    # exit code, but an unhandled exception bypassed that and failed the pipeline for three
    # days (a TypeError sorting stuck picks). Any unexpected error is now reported and
    # swallowed, unless --strict is explicitly requested.
    try:
        sys.exit(main())
    except Exception as e:
        import traceback
        note("warning", f"sg_health crashed ({type(e).__name__}: {e}) — "
                        f"checks skipped, pipeline continues")
        traceback.print_exc()
        sys.exit(1 if "--strict" in sys.argv else 0)
