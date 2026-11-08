#!/usr/bin/env python3
"""NFL team total · OVER main line +1 (2026-11-08): one Sandbox PAPER lane, `nfl_tt_main1`.

Paper only: not in Production, not in the Production feed, no PAIR_OVERRIDES entry, on its own fresh record
(data/nfl_tt_main1_ledger.json) from its first entry. Nothing is placed. Approved by Olu 2026-11-08.

PRE-REGISTERED 2026-11-08, before any entry. The thesis is the one nfl_tt.py tests: Kalshi sets NFL team-total
lines a little low. This lane tests it by STRUCTURE, not by price: the rung one strike above the main line.
Evidence (deep dive 2026-11-08 on Kalshi KXNFLTEAMTOTAL hourly quotes 1 hour before kickoff, 2026 weeks 1-9,
243 team ladders, spread 5c or less, after fee, z clustered by NFL week):
  main+1 (the rung one above the main line): 112 won v 100.3 priced, avg ask 41c, +6.9%, z +1.54;
  positive in the research weeks (1-6, +6.6%) AND the forward weeks (7-9, +7.6%).
  Neighbours: main line +0.7%, main+2 +2.1%, main-1 -2.8%, main-2 -1.0%, main+3 -1.2%.
  Expected edge: about +6%, not the +20% the 35-45c lane showed in research. At that size 30 entries cannot
  prove it (the ROI standard error is several times the edge); the read at 30 is a direction check.
  Review at 10 settled entries (Olu reviews at 10+), decide at 30.

THE RULES
1. Scope: Kalshi's NFL team-total ladders (series KXNFLTEAMTOTAL), matched to ESPN kickoffs exactly as
   nfl_tt.py does (nfl_tt.find_event, nfl_tt.ladders).
2. Quote: a rung counts only with a two-sided YES quote (bid above 0, ask below 1) and spread at most 5c
   (nfl_tt.quote). No depth floor; the size at the ask is recorded.
3. Main line: per team per game, among that team's quoted rungs, the rung whose YES mid ((bid + ask) / 2) is
   nearest 0.50; a tie goes to the lower strike. This is the deep dive's analyze.main_line, run on the same
   quoted ladder (the distance is rounded to 6 places so a float tie is a tie).
4. Bet: the YES on the NEXT HIGHER strike of that quoted ladder (main+1), at its ask. No price band: the rung
   is defined by structure. If the main line is the team's top quoted rung there is no main+1: no entry, and
   the skip is logged in the ledger ("skips").
5. Entry: 45 to 75 minutes before the ESPN kickoff (inclusive), while ESPN still has the game as not
   started. One frozen entry per team per game.
6. Settled on Kalshi's official result, profit per $100 after the 7% taker fee 0.07 p (1 - p). Stats are
   clustered by NFL week (nfl_tt.stats).
7. Blind baseline: nfl_tt's own (the YES on EVERY in-window team-total rung with the same quote), read over
   the same dates as this lane (logged from REGISTERED on). It is not logged twice.

How it runs: a step of nfl-tt.yml, so it reads in the same VPS-asked windows as nfl_tt (no host change), plus
the hourly schedule that settles. It shares nfl_tt's ESPN and Kalshi readers; nfl_tt keeps writing the schedule.
"""
import datetime as dt
import json
import os

import nfl_tt as N

ROOT = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(ROOT, "data", "nfl_tt_main1_ledger.json")
LANE = "nfl_tt_main1"
LANES = (LANE,)
REGISTERED = "2026-11-08"
SERIES = N.SERIES
WINDOW_MIN = N.WINDOW_MIN
FEE = N.FEE
READ_AT = {LANE: 30}
REVIEW_AT = 10
RETIRED = {}
SKIP_NO_ABOVE = "no quoted rung above the main line"

NAMES = {LANE: "NFL team total · OVER main line +1"}
PREREG = {LANE: (
    "PRE-REGISTERED 2026-11-08, before any entry. Thesis: Kalshi sets NFL team-total lines a little low; this "
    "lane tests it by structure, not price. Deep dive on Kalshi KXNFLTEAMTOTAL quotes 1h before kickoff, 2026 "
    "weeks 1-9 (243 team ladders, spread ≤5c, after fee, week-clustered z): the rung one above the main line "
    "won 112 v 100.3 priced at an average 41c, +6.9%, z +1.54, and was positive in both the research weeks "
    "(1-6, +6.6%) and the forward weeks (7-9, +7.6%). Expected edge about +6%, not the +20% the 35-45c lane "
    "showed in research, so 30 entries are a direction check, not proof. Review at 10 settled entries, decide "
    "at 30; fresh record from the first entry, no backfill.")}
DEFINITION = {LANE: (
    "Kalshi NFL team totals (KXNFLTEAMTOTAL). Per team per game, the main line is the quoted rung whose YES mid "
    "((bid+ask)/2) is nearest 0.50, a tie to the lower strike; back YES (over) on the NEXT HIGHER quoted strike "
    "at its ask. No price band. If no quoted rung sits above the main line, no entry (logged as a skip). Entry "
    "45-75 minutes before the ESPN kickoff, one frozen entry per team per game. Only a two-sided YES quote with "
    "spread ≤5c counts, no depth floor. Settled on Kalshi's official result after the 7% taker fee; stats "
    "clustered by NFL week. Blind baseline: the YES on every in-window team-total rung with the same quote, over "
    "the same dates. Paper, Sandbox only.")}
IN_SAMPLE = (
    "In-sample, NOT counted in this record (deep dive 2026-11-08, hourly quotes 1h before kickoff, 2026 weeks "
    "1-9, 243 team ladders): main+1 112 won v 100.3 priced, avg ask 41c, +6.9% after fee, z +1.54; weeks 1-6 "
    "+6.6%, weeks 7-9 +7.6%. Neighbouring rungs: main line +0.7%, main+2 +2.1%, main−1 −2.8%.")


def retired(lane, now):
    r = RETIRED.get(lane)
    return bool(r) and now.astimezone(N.ET).date().isoformat() >= r["on"]


def fee(p):
    return N.fee(p)


def empty():
    return {"version": "nfl-tt-main1-v1", "registered": REGISTERED, "rules": {LANE: {"picks": []}},
            "runs": [], "skips": []}


def load(path=PATH):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return empty()


def main_line(ladder):
    """The quoted rung whose mid is nearest 0.50, a tie to the lower strike (analyze.main_line)."""
    return min(ladder, key=lambda r: (round(abs((r[2] + r[3]) / 2 - 0.5), 6), r[0])) if ladder else None


def pick_main1(ladder):
    """(main line, main+1) for one team's quoted ladder [(strike, market, bid, ask)]; main+1 is None when the main
    line is the top quoted strike, and both are None for an empty ladder."""
    rs = sorted(ladder, key=lambda r: (r[0], str(r[1].get("ticker"))))
    m = main_line(rs)
    if m is None:
        return None, None
    i = rs.index(m)
    return m, (rs[i + 1] if i + 1 < len(rs) else None)


def entry(ev, g, team, main, r, now):
    p = N.entry(LANE, ev, g, team, r, now)
    p.update(id=f"{LANE}:{ev['event_ticker']}:{team}", rule=LANE, main_line=main[0],
             main_mid=round((main[2] + main[3]) / 2, 4), main_ticker=main[1].get("ticker"),
             why=f"{team} over {r[0]} YES {r[3]:.2f} (main line {main[0]})")
    return p


def picks_for(ev, g, now):
    """([entries], [skips]) for one matched, in-window game."""
    out, skips = [], []
    for team, ladder in sorted(N.ladders(ev, g).items()):
        m, r = pick_main1(ladder)
        if m is None:
            continue
        if r is None:
            skips.append(dict(id=f"{LANE}:{ev['event_ticker']}:{team}", event=ev["event_ticker"], team=team,
                              game=f"{g['away']} @ {g['home']}", start=g.get("start"), week=N.week_of(g),
                              main_line=m[0], reason=SKIP_NO_ABOVE, logged=now.isoformat()))
            continue
        out.append(entry(ev, g, team, m, r, now))
    return out, skips


def stats(picks):
    return N.stats(picks)


def baseline_picks(base_state=None):
    """nfl_tt's blind baseline rows over this lane's dates (logged from REGISTERED on)."""
    st = base_state if base_state is not None else (N.load() if os.path.exists(N.PATH) else N.empty())
    rows = ((st.get("rules") or {}).get(N.BASE) or {}).get("picks") or []
    return [p for p in rows if str(p.get("logged") or "")[:10] >= REGISTERED]


def run(state, games, now=None, fetch=N.D.get):
    now = now or dt.datetime.now(dt.timezone.utc)
    state["rules"].setdefault(LANE, {"picks": []})
    state.setdefault("skips", [])
    seen = {p["id"] for p in state["rules"][LANE]["picks"]}
    skipped = {s["id"] for s in state["skips"]}
    log, errs = [], []
    st = dict(due=0, matched=0, entered=0, skipped=0)
    todo = N.due(games, now) if not retired(LANE, now) else []
    events = None
    if todo:
        try:
            events = N.fetch_events(fetch)
        except Exception as e:                                  # noqa: BLE001
            errs.append(f"{SERIES}: {str(e)[:80]}")
    for g in todo if events is not None else ():
        st["due"] += 1
        ev = N.find_event(g, events)
        if not ev:
            continue
        st["matched"] += 1
        rows, skips = picks_for(ev, g, now)
        for p in rows:
            if p["id"] in seen:
                continue
            state["rules"][LANE]["picks"].append(p)
            seen.add(p["id"])
            log.append(p["id"])
            st["entered"] += 1
        for s in skips:
            if s["id"] in seen or s["id"] in skipped:
                continue
            state["skips"].append(s)
            skipped.add(s["id"])
            st["skipped"] += 1
    errs += N.settle(state, now, fetch)
    state["last_run"] = now.isoformat()
    state["error"] = "; ".join(errs)[:1000] or None
    state["runs"] = (state.get("runs") or [])[-50:] + [dict(at=now.isoformat(), new=len(log), **st)]
    return log


def main(argv=None):
    import sys
    argv = sys.argv[1:] if argv is None else argv
    out = argv[argv.index("--out") + 1] if "--out" in argv else PATH
    now = dt.datetime.now(dt.timezone.utc)
    state = load(out)
    try:
        games, espn_err = N.espn_games(now), None
    except Exception as e:                                      # noqa: BLE001
        games, espn_err = [], f"ESPN: {str(e)[:80]}"            # settles anyway; the error is on the page
    new = run(state, games, now)
    if espn_err:
        state["error"] = "; ".join(x for x in (espn_err, state.get("error")) if x)[:1000]
    tmp = out + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f, indent=1, sort_keys=True)
        f.write("\n")
    os.replace(tmp, out)
    print("run", state["runs"][-1], "new", new, "error", state["error"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
