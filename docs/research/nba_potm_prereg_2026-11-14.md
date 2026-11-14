# NBA Player of the Month (Kalshi KXNBAPOTM) research, pre-registration, 2026-11-14
Written BEFORE the model was scored against prices.

Structure of the market (mapped, see README): ONE series, two events per window (EAST, WEST). Only ONE window exists:
KXNBAPOTM-NOV26EAST/WEST (the 2026-27 "October/November" award, created 2026-10-21, winner announced ~Dec 1).
No settled months, no archived events -> no backtest is possible; no rule can be validated.

Fixed model (snapshot only): over qualified players (ESPN season to date, min 8 games)
  score = (z(PPG) + 0.5*z(RPG) + 0.5*z(APG)) with a team factor (0.5 + team win%), then softmax (temperature 1) within each
  conference -> implied win probability.
Candidate rules that WOULD be tested once months exist (not testable now):
  R1 buy the model leader at day N when priced under X; R2 buy the cheap side where model and market disagree;
  R3 favourite-longshot by price band; fills on the real ask / trade prints. Cluster by month.
Decision rule written now: build needs >= 6 settled windows with the same rule winning in found and later halves; with n = 0 the
verdict can only be WATCH or MOVE ON.
