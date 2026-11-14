# NBA POTM "best team among the stat top 3" rule, pre-registration, 2026-11-14
Written and committed BEFORE any 2018-19 / 2019-20 data was pulled. Follows [#468](nba_potm_history_2026-11-14.md), where the idea came from an in-sample look (winner had the better team record in 21 of 29 awards the stat leader lost).

Rule (fixed): at checkpoint day D, take the stat model's top 3 in the conference (same score, field, eligibility and softmax as #468: z(PPG)+0.5 z(RPG)+0.5 z(APG) times (0.5 + team win% over the games he played in the window)). Pick the one whose team win% in the window (over his games) is highest; tie-break: higher model score.
Primary checkpoints: day 14 and day 21. Descriptive only: day 7 and 28.
Comparators: the stat leader (rank 1) at the same checkpoint, and "random pick of the top 3" (1/3 when the winner is in the top 3).
Found seasons: 2021-22 to 2025-26 (50 awards, rule was suggested by looking at them, so in-sample). Holdout: 2018-19 and 2019-20 (Basketball-Reference awards; windows with no award, e.g. 2019-20 March, are skipped; windows Nov (season start to Nov 30), Dec, Jan, Feb, Mar (to season end) as in #468). Same data source and parser; field = that season's top 45 scorers.
Expected holdout size: about 18 awards, so intervals are wide (about +/-22pp). This test can only say "worth a paper check", never "proven".

Success mark (all must hold on the holdout):
1. rule hit rate at day 21 >= 50%;
2. at BOTH day 14 and day 21 the rule wins at least 2 more awards than the stat leader does;
3. rule hit rate is also above the stat leader's on the found seasons at day 21 (sanity, in-sample).
Pricing statement, if it passes: pooled (found + holdout) hit rate at day 21 with its Wilson interval; a pick is "worth it" only below the LOWER end of that interval, not the point estimate.
If it fails: verdict MOVE ON, no paper check proposed.
