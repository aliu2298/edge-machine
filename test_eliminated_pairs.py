#!/usr/bin/env python3
"""Four pairs that lose both ways stop picking, and stay off every page.

covers MLB, the NHL puck line, and both weather lanes are eliminated:
connected=False, a retired note, and an S.ELIMINATED entry. covers NFL is
retired on the same note and is not eliminated. All four sources stay in
S.REMOVED_SOURCES, so a removed lane never renders — not in the eliminated
list, a sport section, the retired list, or a note.

Fails on main: the four pairs are still connected and not in S.ELIMINATED.
Passes once that state is set and every built page still has zero hits.
No network.
"""
import os
import re
from datetime import datetime, timezone

import production
import sandbox_build as SB
import sandbox_sources as S
import sandbox_track as T
import site_root

FAILS = []
NOW = datetime(2026, 10, 2, 4, 0, tzinfo=timezone.utc)
ROOT = os.path.dirname(os.path.abspath(__file__))
TERMS = ("covers", "oddsshark", "nhl_dog_pl", "nws_fade", "nws", "climate", "weather")
_NWS = re.compile(r"nws(?!_fade)", re.I)


def ok(cond, why):
    print(f"  {'ok  ' if cond else 'FAIL'} {why}")
    if not cond:
        FAILS.append(why)


def eq(got, want, why):
    ok(got == want, why if got == want else f"{why} — got {got!r}, want {want!r}")


def _pages():
    sandbox, index, weeks = SB.render_pages(NOW)
    out = {
        "sandbox.html": sandbox,
        "archive/index.html": index,
        "production.html": production.page(
            T.load(), T.load_stages(), production.load_feed(), "", now=NOW),
        "trading.html": SB.trading_page(NOW),
        "index.html": site_root.root_stub(NOW),
    }
    root = os.path.join(ROOT, "public_site", "index.html")
    with open(root, encoding="utf-8") as f:
        out["public_site/index.html"] = f.read()
    out.update({f"archive/{slug}.html": html for slug, html in weeks.items()})
    return out


def _counts(html):
    low = html.lower()
    return {
        "covers": low.count("covers"),
        "oddsshark": low.count("oddsshark"),
        "nhl_dog_pl": low.count("nhl_dog_pl"),
        "nws_fade": low.count("nws_fade"),
        "nws": len(_NWS.findall(html)),
        "climate": low.count("climate"),
        "weather": low.count("weather"),
    }


def main():
    print("\nthe four pairs are eliminated, and every one of them stays removed")
    ok(not S.SOURCES["covers"]["connected"] and S.SOURCES["covers"].get("retired")
       and ("covers", "mlb") in S.ELIMINATED and ("covers", "nfl") not in S.ELIMINATED
       and "covers" in S.REMOVED_SOURCES,
       "covers MLB is eliminated, covers NFL is not, and covers stays removed")
    ok("2026-10-01" in (S.SOURCES["covers"].get("retired") or ""),
       "the covers retired note is dated")
    ok(not S.SOURCES["nhl_dog_pl"]["connected"] and S.SOURCES["nhl_dog_pl"].get("retired")
       and ("nhl_dog_pl", "nhl_pl") in S.ELIMINATED and "nhl_dog_pl" in S.REMOVED_SOURCES,
       "nhl_dog_pl is eliminated and stays removed")
    ok(("nws", "climate") in S.ELIMINATED and ("nws_fade", "climate") in S.ELIMINATED
       and not S.SOURCES["nws"]["connected"] and not S.SOURCES["nws_fade"]["connected"]
       and S.SOURCES["nws"].get("retired") and S.SOURCES["nws_fade"].get("retired")
       and "nws" in S.REMOVED_SOURCES and "nws_fade" in S.REMOVED_SOURCES
       and S.lane_removed("nws", "climate") and S.lane_removed("nws_fade", "climate")
       and S.lane_removed("covers", "mlb") and S.lane_removed("covers", "nfl")
       and S.lane_removed("nhl_dog_pl", "nhl_pl"),
       "both weather pairs are eliminated and all four sources stay off every page")
    for key in ("covers|mlb", "covers|nfl", "nhl_dog_pl|nhl_pl", "nws|climate", "nws_fade|climate"):
        ok(key not in T.PAIR_OVERRIDES, f"{key} is not a Production pair")
    # spot was RETIRED 2026-10-05, not eliminated: its question was answered (flat over
    # 26 market-days, z -0.07) and a flat null hypothesis has no fade to keep open. It
    # stays OFF the removed list on purpose, so its two open bets still grade and its
    # record stays readable on the page.
    ok(not S.SOURCES["spot"]["connected"] and S.SOURCES["spot"].get("retired"),
       "spot is retired with its finding recorded")
    ok("spot" not in S.REMOVED_SOURCES and not S.lane_removed("spot", "crypto"),
       "and retired, not eliminated -- so grading and its record continue")
    # A blind baseline is the bar a CHOICE has to clear. Boxing and MMA lost their last
    # chooser on 2026-10-04 and the rows kept rendering off the venues' contests, reading
    # as a lane that made money -- "MMA, back the favourite, +20.8%" -- when it is the
    # favourite-longshot bias, already priced. Hidden by hand on 2026-10-05.
    import sandbox_build as BLD
    for _sp in ("boxing", "mma"):
        ok(BLD.judges_nothing(_sp), f"{_sp} has no chooser left, so its baseline row is hidden")
    # Scoped deliberately. A registry or ledger rule would also take table tennis, MLB and
    # NHL Rest, and would contradict what test_tip_lanes_removed already pins: boxing and
    # MMA keep their venue sweep and coverage row, and table tennis keeps a baseline row
    # whenever the full ledger holds its contests. Those were separate decisions.
    for _sp in ("soccer", "tennis", "cricket", "nfl", "table_tennis", "mlb", "nhl_rest"):
        ok(not BLD.judges_nothing(_sp), f"{_sp} keeps its baseline row")
    ok("boxing" not in S.REMOVED_VENUE_SPORTS and "mma" not in S.REMOVED_VENUE_SPORTS,
       "and their venue listings are still swept -- only the baseline row was hidden")

    ok("scores24" in S.REMOVED_SOURCES and "sportsgambler" in S.REMOVED_SOURCES
       and "soccerpredictions" in S.REMOVED_SOURCES,
       "scores24, sportsgambler, and soccerpredictions stay off the board")

    print("\nno built page renders a removed eliminated lane")
    pages = _pages()
    ok(len(pages) > 4, f"{len(pages)} pages built")
    for name in sorted(pages):
        counts = _counts(pages[name])
        bits = " ".join(f"{term}={counts[term]}" for term in TERMS)
        ok(all(n == 0 for n in counts.values()), f"{name}: {bits}")

    print(f"\n{'FAILED: ' + str(len(FAILS)) if FAILS else 'eliminated pairs passed'}")
    for item in FAILS:
        print(f"  - {item}")
    return 1 if FAILS else 0


if __name__ == "__main__":
    raise SystemExit(main())
