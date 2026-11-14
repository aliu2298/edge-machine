# NBA Player of the Month history study, pre-registration, 2026-11-14
Written BEFORE any game logs were pulled or compared with winners. Winners list (Basketball-Reference awards/pom.html) is fetched; nothing scored.

Sample: seasons 2021-22 .. 2025-26, windows Nov (season start to Nov 30, i.e. "Oct/Nov"), Dec, Jan, Feb, Mar (Mar 1 to season end,
absorbs April) x East/West = 50 awards. (2020-21 skipped: shortened-season windows.)

Field: top 45 scorers of the season by PPG (B-Ref per-game page) plus nobody else. Conference by their current team.
Known bias: field chosen with season hindsight (adds some who were bad early); it can only make the leader at a checkpoint look
WORSE than reality (a late-season star in the field who was slumping in the window cannot lead), so it does not inflate hold rates.

Checkpoints: day 7, 14, 21, 28 after window start (calendar days, games on or before that date only; no look-ahead). Plus "final".
Eligibility: >= 5 games played in window by the checkpoint (day 7 relaxed to >= 3).
Score (fixed, from #459): z(PPG)+0.5 z(RPG)+0.5 z(APG) z-scored across eligible players of ALL conferences that day,
times team factor (0.5 + team win% over the games he played in the window), higher = leading. Conference = the player's own.
Win probability implied: softmax(score, T=1) within conference over eligible players (same as #459).
Lead size = gap between #1 and #2 score, and implied prob of #1.

Measures: P(leader wins), P(winner in top 2, top 3), P(rank-1 changes between checkpoint and final), by checkpoint, by lead size tercile / by implied prob band
(compare "implied ~70%" band against realised rate). Also the realised rate in bands 40-55, 55-70, 70+.
Not tested: any trade rule; no Kalshi prices exist for these months. The verdict is about whether a ~70c price on a checkpoint leader is too cheap or too dear,
given the implied-prob band hold rate and its sampling uncertainty (Wilson interval). n of 50 is small; state that.
