#!/usr/bin/env python3
"""verify_coverage.py — prove every league's teams are actually accounted for.

WHY THIS EXISTS
---------------
Teams went missing from the board silently. Liverpool, Lyon, Valencia, AS Monaco and
LA Galaxy were all absent — not from a fetch failure, but because the browse view dropped
any side without a 3+ run, so a league of 20 rendered 15 and nothing anywhere said so.
That is the failure mode this repo keeps hitting: a page that looks fine while quietly
holding less than it should.

So this checks the chain end to end, per league:

    ESPN fixtures  ->  teams seen  ->  teams with form  ->  teams on the board

and compares the count against the league's real size. A gap at any stage is named.

Exit code is 1 only under --strict; the daily job should surface problems, not block on
them. Squad counts are the league's actual size — update SQUADS when a league changes.

Usage:  python3 verify_coverage.py [--strict] [--verbose]
"""
import json, os, sys, collections

import streaks_fetch
import streaks_build as B

ROOT = os.path.dirname(os.path.abspath(__file__))
BOARD = os.path.join(ROOT, "data", "streaks.json")

# Real league sizes for 2026. A league that fields fewer than this on the board has
# something missing; MORE is normal, because cup ties pull in outside clubs.
SQUADS = {
    "Premier League": 20, "La Liga": 20, "Bundesliga": 18, "Serie A": 20,
    "Ligue 1": 18, "Eredivisie": 18, "Primeira Liga": 18, "MLS": 30,
    "Saudi Pro League": 18,
}
# Cup competitions have no fixed membership, so a size check is meaningless for them.
NO_SQUAD_CHECK = {"Champions League", "Europa League"}


def note(level, msg):
    if os.environ.get("GITHUB_ACTIONS"):
        print(f"::{level}::{msg}")
    else:
        print(f"  [{level.upper()}] {msg}")


def main():
    strict = "--strict" in sys.argv
    verbose = "--verbose" in sys.argv
    problems = 0

    fixtures = streaks_fetch.load_or_fetch()["fixtures"]
    by_team = B.team_games(fixtures)
    shown = B.team_streaks(by_team, B.MIN_PLAYED_SHOWN)

    try:
        board = json.load(open(BOARD))
        on_board = {t["team"] for t in board.get("teams", [])}
        fire = {t["team"] for t in board.get("fire", [])}
    except Exception as e:
        note("error", f"cannot read {BOARD}: {e}")
        return 1

    # teams seen in each league's COMPETITIVE fixtures
    seen = collections.defaultdict(set)
    for f in fixtures:
        if f.get("competitive", True):
            seen[f["league"]].add(f["home"])
            seen[f["league"]].add(f["away"])

    print(f"{'league':20s} {'seen':>5s} {'form':>5s} {'board':>6s} {'squad':>6s}  status")
    print("-" * 68)
    for lg in sorted(seen):
        teams = seen[lg]
        with_form = {t for t in teams if t in shown}
        on = {t for t in teams if t in on_board}
        squad = SQUADS.get(lg)
        missing = sorted(teams - on_board)

        status = "ok"
        if lg not in NO_SQUAD_CHECK and squad and len(on) < squad:
            status = f"SHORT by {squad - len(on)}"
            note("warning", f"COVERAGE {lg}: {len(on)} of {squad} on the board "
                            f"(missing: {', '.join(missing[:6])}"
                            f"{'…' if len(missing) > 6 else ''})")
            problems += 1
        elif missing:
            # not short of the squad, but some seen team never reached the board
            status = f"{len(missing)} unlisted"

        print(f"{lg:20s} {len(teams):5d} {len(with_form):5d} {len(on):6d} "
              f"{(squad or '—'):>6}  {status}")
        if verbose and missing:
            for t in missing:
                print(f"      unlisted: {t} ({len(by_team.get(t, []))} games)")

    # A team with games but no board row means the render dropped it — the exact bug
    # this file was written for.
    ghosts = [t for t, g in by_team.items()
              if len(g) >= B.MIN_PLAYED_SHOWN and t in shown and t not in on_board]
    # friendly-only sides are filtered on purpose and are not ghosts
    ghosts = [t for t in ghosts
              if any(g.get("comp", True) for g in by_team[t])]
    if ghosts:
        note("warning", f"DROPPED {len(ghosts)} teams have form but no board row: "
                        f"{', '.join(sorted(ghosts)[:8])}")
        problems += 1

    print(f"\n  teams with form: {len(shown)} | on board: {len(on_board)} | "
          f"on fire: {len(fire)}")
    print(f"  issues: {problems}")
    if not problems:
        print("  ✅ every league's squad is accounted for")
    return 1 if (problems and strict) else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        import traceback
        note("warning", f"verify_coverage crashed ({type(e).__name__}: {e})")
        traceback.print_exc()
        sys.exit(1 if "--strict" in sys.argv else 0)
