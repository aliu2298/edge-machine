"""top5_goalless_dip: top-5 leagues + UCL, buy the goalless dip on over 1.5 (2026-10-30, Olu). Sandbox PAPER.

The goalless-dip engine is arg_dip.py; this file is the lane's config and its pre-registration.

THE RULE, pre-registered before the first entry (2026-10-31):
  markets  the over 1.5 rung (floor_strike 1.5) of Kalshi KXEPLTOTAL, KXLALIGATOTAL, KXSERIEATOTAL,
           KXBUNDESLIGATOTAL, KXLIGUE1TOTAL and KXUCLTOTAL, every match.
  kickoff  the market's occurrence_datetime minus 4 hours.
  P        the pregame YES ask an hour before kickoff, from 1-minute candles (the last minute quote at or
           before that time, archived "close" or live "close_dollars"), with a spread of 5c or less, P 10-95c,
           and only if that ask passes the entry-validity check (#253): 10+ contracts traded at or through it
           within 60 minutes after, and not under half the last trade before it. A match without such a P is
           skipped.
  BUY      a resting YES buy at round(0.55 x P, 2) from kickoff (the HEADLINE; 0.65 x P is tracked on the same
           matches). It counts as a fill only when ALL of: a trade prints at or below the limit after kickoff;
           10+ contracts print at or below it within 60 minutes of that first touch; and the low price HELD:
           the prints at or below the limit span 2+ minutes within 5 minutes of the first touch, or 50+
           contracts print there. Anything less is a "thin touch", recorded and not counted (the soccer NO-side
           clean-up found brief stray prints carried almost all of the paper profit, and a real resting bid
           would rarely get them).
  SELL     a resting sell at P placed at the fill. It fills when a later trade prints at or above P; else the
           position settles (1 if 2+ goals, 0 otherwise).
  FEES     maker 0.0175 p(1-p) in and out (both orders rest); nothing at settlement.
  CONTROL  the same fills held to settlement. An unfilled buy is "no fill" and costs nothing.
  READ     an outcome is a MATCH; z is clustered by matchday (the date in the event ticker), with the league
           shown per row and split per league. ROI is the mean per fill (equal stake). Review at 10 filled
           matches, decide at 30.

RECORD: fresh from 2026-10-31. The research behind it (~/edge-research/dip_study_2026-10-30/, dip.py: 414 matches
Aug-Oct 2026, buy at 55% +12.1% per fill on 136 fills, z +2.5) is IN-SAMPLE. Recomputed with the held rule and the
ask check (~/edge-research/top5_dip_2026-10-30/heldcheck.py): 118 fills, +15.4%, z +2.7. It is replayed once by
this code (python3 top5_dip.py --backfill, 2026-10-30: 430 matches Aug 1-Oct 30, 146 fills at 55%, +16.6% per fill,
hold +3.6%, z +3.7 by matchday; 65%: 172 fills, +8.0%) into state["insample"], shown once and labelled, never
counted.
OUT OF SAMPLE: the Brasileirão over 0.5 version of the dip did NOT replicate, so this lane is a test, not a bet.

Own ledger data/top5_dip_ledger.json; read hourly by .github/workflows/top5-dip.yml from settled matches.
Paper only: no order is placed, and Production has no executor for resting in-play buys.
"""
import os
import sys

import arg_dip as A

ROOT = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(ROOT, "data", "top5_dip_ledger.json")
LEAGUES = {"KXEPLTOTAL": "EPL", "KXLALIGATOTAL": "La Liga", "KXSERIEATOTAL": "Serie A",
           "KXBUNDESLIGATOTAL": "Bundesliga", "KXLIGUE1TOTAL": "Ligue 1", "KXUCLTOTAL": "UCL"}
OOS_NOTE = ("Out-of-sample check, Brasileirão over 0.5: the dip buy did NOT replicate there, so this lane is a "
            "test, not a bet.")
INSAMPLE_NOTE = ("The research found +12.1% per fill at 55% (136 fills, z +2.5) counting any fill with 10+ contracts. "
                 "The table below is the same matches under this lane's stricter rule: the price must hold and the "
                 "pregame ask must pass its check.")

TOP5 = dict(lane="top5_goalless_dip", label="Top-5 soccer · buy the goalless dip (over 1.5)",
            series=tuple(LEAGUES), leagues=LEAGUES, strike=1.5, since="2026-10-31",
            insample=("2026-08-01", "2026-10-30"), fractions=(0.55, 0.65), headline=0.55, path=PATH,
            version="top5dip-v1", held=True, p_range=(0.10, 0.95))


def load(path=None):
    return A.load(path, cfg=TOP5)


if __name__ == "__main__":
    raise SystemExit(A.main(sys.argv[1:], cfg=TOP5))
