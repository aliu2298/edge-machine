#!/usr/bin/env python3
"""slate_backtest.py — replay the whole board day by day over past fixtures.

WHAT THIS ASKS THAT streaks_backtest DOES NOT
---------------------------------------------
streaks_backtest grades EVERY qualifying lead, which answers "do confluences carry
information". This answers a narrower and more honest question: **what would this board
actually have produced**, drawing three at a time under the real selection rules —
rarest-first, one per fixture, one per team, window widening, slots refilling as picks
settle. The two can disagree, and the slate's number is the one that matters, because it
is the only one that describes what a reader would have seen.

NO LOOKAHEAD
------------
The simulation steps through time at the cron hour. At each step it rebuilds the fixture
list AS OF that moment — anything not yet kicked off is unplayed and scoreless, exactly as
the real pipeline would have seen it — then recomputes form, leads and rarity from scratch
before drawing. At no point can a fixture's own result, or any later result, reach the pick
being made on it.

Usage:  python3 slate_backtest.py [--verbose]
"""
import sys, copy, datetime, collections

import streaks_fetch
import streaks_build as B
import streaks_track as T
import slate as S

CRON_HOUR = 11        # the pipeline's daily run, 11:17 UTC


def _dt(iso):
    if not iso:
        return None
    try:
        return datetime.datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def fixtures_asof(fixtures, now):
    """The fixture list as the pipeline would have seen it at `now`.

    A fixture is 'played' only if it kicked off before `now` AND we know its score.
    Everything else is stripped back to scoreless, so no future result can leak into the
    form that drives a pick.
    """
    out = []
    for f in fixtures:
        ko = _dt(f.get("kickoff"))
        known = f.get("played") and f.get("home_goals") is not None
        if known and ko is not None and ko < now:
            out.append(f)
        else:
            g = dict(f)
            g["played"] = False
            g["home_goals"] = g["away_goals"] = None
            out.append(g)
    return out


def leads_asof(fixtures_now, now):
    """Exactly what streaks_build would have published at `now`."""
    by_team = B.team_games(fixtures_now)
    streaks = B.team_streaks(by_team)
    if not streaks:
        return []
    rates = B.base_rates(streaks)
    return B.find_leads(fixtures_now, streaks, rates, now=now, links=False)


def simulate(fixtures, verbose=False):
    played = [f for f in fixtures
              if f.get("played") and f.get("home_goals") is not None and _dt(f.get("kickoff"))]
    if not played:
        return {"picks": {}}, []
    kos = sorted(_dt(f["kickoff"]) for f in played)
    # start once there is enough history for anyone to qualify (MIN_PLAYED games deep)
    start = kos[0] + datetime.timedelta(days=45)
    end = kos[-1] + datetime.timedelta(days=1)

    blob = {"picks": {}}
    timeline = []
    t = start.replace(hour=CRON_HOUR, minute=17, second=0, microsecond=0)
    while t <= end:
        snap = fixtures_asof(fixtures, t)
        leads = leads_asof(snap, t)
        blob, graded = S.grade(snap, blob, t)
        blob, drawn = S.draw(leads, blob, t)
        if verbose and (graded or drawn):
            print(f"  {t.date()}  graded {graded:2d}  drew {len(drawn):2d}  "
                  f"live {len(S.live_picks(blob))}")
        timeline.append({"t": t.isoformat(), "graded": graded, "drawn": len(drawn),
                         "live": len(S.live_picks(blob))})
        t += datetime.timedelta(days=1)

    # settle anything still open using the full (final) fixture list
    blob, _ = S.grade(fixtures, blob, end + datetime.timedelta(days=30))
    return blob, timeline


def main():
    verbose = "--verbose" in sys.argv
    fixtures = streaks_fetch.load_or_fetch()["fixtures"]
    blob, timeline = simulate(fixtures, verbose)

    decided = [p for p in blob["picks"].values() if p["status"] in ("hit", "miss")]
    void = [p for p in blob["picks"].values() if p["status"] == "void"]
    live = S.live_picks(blob)

    print(f"\nSLATE BACKTEST — {len(timeline)} simulated days, "
          f"3 picks held at a time")
    print(f"drawn: {len(blob['picks'])} | graded: {len(decided)} | "
          f"void: {len(void)} | still open at the end: {len(live)}")
    if not decided:
        print("nothing graded — not enough history")
        return

    rep = S.report(fixtures, blob)
    print(f"\noverall: {rep['hits']}/{rep['graded']} = {rep['rate']:.1%}\n")
    print(f"{'bet':16s} {'n':>4s} {'hit rate':>10s} {'lg-adj base':>12s} {'lift':>9s} "
          f"  verdict")
    print("-" * 70)
    for r in rep["rows"]:
        base = f"{r['base']:.1%}" if r["base"] is not None else "—"
        lift = f"{r['lift']*100:+.1f}pp" if r["lift"] is not None else "—"
        print(f"{r['kind']:16s} {r['n']:4d} {r['rate']:9.1%} {base:>12s} {lift:>9s} "
              f"  {'SIGNIFICANT' if r['significant'] else 'not sig'}")

    # How often could the board actually field three?
    fill = collections.Counter(d["live"] for d in timeline)
    print(f"\nslate fill across the run: "
          + ", ".join(f"{k} live on {v} days" for k, v in sorted(fill.items())))
    days_short = sum(v for k, v in fill.items() if k < S.SLATE_SIZE)
    print(f"days short of a full slate: {days_short}/{len(timeline)} "
          f"({days_short/len(timeline):.0%})")

    lags = []
    for p in blob["picks"].values():
        d, k = _dt(p.get("drawn_at")), _dt(p.get("kickoff"))
        if d and k:
            lags.append((k - d).total_seconds() / 86400)
    if lags:
        lags.sort()
        print(f"draw-to-kickoff lag: median {lags[len(lags)//2]:.1f}d, "
              f"max {lags[-1]:.1f}d  (how far the window had to stretch)")

    if not any(r["significant"] for r in rep["rows"]):
        print("\nNo bet type's interval clears its league-adjusted baseline. On this\n"
              "sample the slate is not distinguishable from the population — no edge.")


if __name__ == "__main__":
    main()
