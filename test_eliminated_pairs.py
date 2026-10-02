#!/usr/bin/env python3
"""Four pairs that lose both ways leave their sport sections.

Weather stays off every built page, including the eliminated list.
covers MLB and the NHL puck-line lane show only in that list.
covers NFL stays in the NFL section, retired and not eliminated.

Fails on main: those two pairs are not in the eliminated list.
Passes once they are, and once weather still renders nowhere.
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
TERMS = ("nws_fade", "nws", "climate", "weather")
_NWS = re.compile(r"nws(?!_fade)", re.I)
_SPORT = '<details class="sport"><summary><b>'
COVERS = "Covers / OddsShark computer picks"
NHL = "NHL underdog +1.5"


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
        "nws_fade": low.count("nws_fade"),
        "nws": len(_NWS.findall(html)),
        "climate": low.count("climate"),
        "weather": low.count("weather"),
    }


def _chunks(html):
    chunks = {}
    for part in html.split(_SPORT)[1:]:
        name, _, rest = part.partition("</b>")
        chunks.setdefault(name, []).append(rest)
    return chunks


def _table(rest):
    """The sport table, before a nested details block."""
    return rest.split(_SPORT)[0].split("</details>")[0]


def main():
    print("\nno built page renders weather")
    pages = _pages()
    ok(len(pages) > 4, f"{len(pages)} pages built")
    for name in sorted(pages):
        counts = _counts(pages[name])
        bits = " ".join(f"{term}={counts[term]}" for term in TERMS)
        ok(all(n == 0 for n in counts.values()), f"{name}: {bits}")

    print("\ncovers MLB and the NHL lane sit in the eliminated list, not their sports")
    chunks = _chunks(pages["sandbox.html"])
    ok("MLB" in chunks and "NFL" in chunks and "NHL" in chunks and "Eliminated" in chunks,
       "MLB, NFL, NHL, and Eliminated sections are on the sandbox page")
    mlb = _table(chunks["MLB"][0])
    nfl = _table(chunks["NFL"][0])
    nhl = _table(chunks["NHL"][0])
    elim = chunks["Eliminated"][0].split("</details>")[0]
    ok(COVERS not in mlb, "covers is not in the MLB sport section")
    ok(NHL not in nhl, "nhl_dog_pl is not in the NHL sport section")
    ok(COVERS in nfl, "covers NFL stays in the NFL section")
    ok(COVERS in elim and "MLB" in elim, "covers MLB is in the eliminated list")
    ok(NHL in elim, "nhl_dog_pl is in the eliminated list")
    elim_counts = _counts(elim)
    ok(all(n == 0 for n in elim_counts.values()),
       "the eliminated list does not draw weather "
       + " ".join(f"{term}={elim_counts[term]}" for term in TERMS))

    print("\nthe four pairs are retired, and weather stays removed")
    ok(not S.SOURCES["covers"]["connected"] and ("covers", "mlb") in S.ELIMINATED
       and ("covers", "nfl") not in S.ELIMINATED,
       "covers MLB is eliminated and covers NFL is not")
    ok(not S.SOURCES["nhl_dog_pl"]["connected"] and ("nhl_dog_pl", "nhl_pl") in S.ELIMINATED,
       "nhl_dog_pl is eliminated")
    ok(("nws", "climate") in S.ELIMINATED and ("nws_fade", "climate") in S.ELIMINATED
       and S.lane_removed("nws", "climate") and S.lane_removed("nws_fade", "climate"),
       "both weather pairs are eliminated and still removed from every page")
    for key in ("covers|mlb", "covers|nfl", "nhl_dog_pl|nhl_pl", "nws|climate", "nws_fade|climate"):
        ok(key not in T.PAIR_OVERRIDES, f"{key} is not a Production pair")
    ok(S.SOURCES["spot"]["connected"] and "spot" not in S.REMOVED_SOURCES,
       "spot stays connected")
    ok("scores24" in S.REMOVED_SOURCES and "sportsgambler" in S.REMOVED_SOURCES
       and "soccerpredictions" in S.REMOVED_SOURCES,
       "scores24, sportsgambler, and soccerpredictions stay off the board")

    print(f"\n{'FAILED: ' + str(len(FAILS)) if FAILS else 'eliminated pairs passed'}")
    for item in FAILS:
        print(f"  - {item}")
    return 1 if FAILS else 0


if __name__ == "__main__":
    raise SystemExit(main())
