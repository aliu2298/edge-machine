# NBA POTM: best team among the stat top 3, holdout test (2026-11-14)
Research only. No lane, no rule change, no orders. Rule and pass mark were committed before the holdout data was pulled: [prereg](nba_potm_bestteam_prereg_2026-11-14.md). Follows [#468](nba_potm_history_2026-11-14.md).

Rule: at day D, take the stat model's top 3 in the conference, pick the one whose team has the best win% in the window (tie-break: model score).
Found = 2021-26, 50 awards (in-sample, the idea came from these). Holdout = 2018-19 and 2019-20, 18 awards (2019-20 March was not awarded, so skipped). Same data source, parser and model as #468.

## Result (share of awards won by the pick, 95% range)
| sample, checkpoint | best team of top 3 | stat leader | winner anywhere in top 3 |
|---|---|---|---|
| found, day 14 | 19/50 = 38% (26-52) | 15/50 = 30% (19-44) | 70% |
| found, day 21 | 25/50 = 50% (37-63) | 21/50 = 42% (29-56) | 76% |
| HOLDOUT, day 14 | 12/18 = 67% (44-84) | 13/18 = 72% (49-88) | 94% |
| HOLDOUT, day 21 | 9/18 = 50% (29-71) | 12/18 = 67% (44-84) | 89% |
| pooled 68, day 14 | 31/68 = 46% (34-57) | 28/68 = 41% (30-53) | 76% |
| pooled 68, day 21 | 34/68 = 50% (38-62) | 33/68 = 49% (37-60) | 79% |
Day 7 and 28 (descriptive): rule 24% and 43% pooled, leader 31% and 47%.

## Against the pre-registered pass mark
1. Holdout day-21 hit rate at least 50%: yes (exactly 9 of 18).
2. Rule beats the stat leader by at least 2 awards at BOTH day 14 and 21 on the holdout: NO (it won 1 fewer at day 14 and 3 fewer at day 21).
3. Better than the leader on the found seasons at day 21: yes (in-sample, +4).
**Fails, so the verdict is MOVE ON.** No paper check is proposed.

The in-sample edge (+8 points at day 21) was found after looking at those same awards and did not survive fresh seasons. In 2018-20 the stat leader was already right two times in three (Harden and Antetokounmpo dominated). The rule picked someone else at day 21 in 7 of 18 awards: it gained 1 (LeBron, Jan 2020) and lost 4 (Harden three times, Embiid once), net minus 3.

## Verdict for Olu
1. This rule cannot read the Kalshi POTM board better than "pick the stat leader". Pooled over 68 awards both win about half the time at day 21 (50% vs 49%); the difference is noise.
2. What does hold up: by day 21 the winner is in the stat top 3 about 4 times in 5 (79% pooled, 89% in the holdout years). That narrows the field but nobody has a way yet to choose inside it.
3. Price: a pick that wins about 50% (interval 38-62%) is only worth buying below about 38c, the low end of the range, not at the 50c point estimate, and the rule gives no information beyond the stat leader, so it has no standing of its own. At a 70c favourite price none of these picks is cheap.
4. Next step would be a different question (does the market price at day 14-21 beat these hit rates?), which needs settled Kalshi months. Waiting for the first settled window (~Dec 1) and the daily snapshot (#461) is the only way. No paper check proposed now.
Caveats: 18 holdout awards, intervals about +/-22 points; field is each season's top 45 scorers; team win% is over the games the player played.
Data and scripts: `~/edge-research/nba_potm_history_2026-11-14/` (bestteam.py, mkfield_holdout.py).
