# Club 90: NBA quarter and half lines (nba_qlines, Sandbox, paper): pre-registration, 2026-11-23

Requested by Olu via the Edge Machine Coordinator, 2026-11-23 ("Assign that to session"); half lines added the same day. Paper only: no orders, no live switch, nothing to Production without Olu.
Code: `nba_qlines.py`, page `nba_qlines_build.py` (a block on the NBA page, indexed on the Sandbox page), workflow `.github/workflows/nba-qlines.yml`,
ledger `data/nba_qlines_ledger.json`, played games `data/nba_qlines/games.json`. This file is committed BEFORE the lane can post its first entry.

## The idea (Nov 22 backtest, disk only)
Some teams' games land on one side of a game-total line almost every time. Over Kalshi's ask 30 minutes before the tip, after fees, the 24 team-line pairs at 90% or better went
367-25 on 392 bets, +16.0%. Point in time (the team's prior games, 5 or more, at 90% or better): 223 bets, +15.4%. Blind every-game baselines: -8.4% to +8.6%.
Files: `~/edge-research/olu_picks_2026-11/qall.json`, `qscore.py`, `qscore_out.txt`. That is in-sample evidence; this lane is the forward test from the first night it runs.

## Lines (config, `nba_qlines.LINES`; game totals, both teams, regulation only)
| Section | Kalshi series | Periods | Over | Under |
|---|---|---|---|---|
| 1Q | KXNBA1QTOTAL | 1 | 51.5 | 59.5 |
| 2Q | KXNBA2QTOTAL | 2 | 50.5 | 63.5 |
| 3Q | KXNBA3QTOTAL | 3 | 53.5 | 64.5 |
| 4Q | KXNBA4QTOTAL | 4 | 48.5 | 62.5 |
| 1H | KXNBA1HTOTAL | 1+2 | 104.5 | 119.5 |
| 2H | KXNBA2HTOTAL | 3+4 plus overtime | 100.5 | 115.5 |
A change to a line, to the 90% bar or to the games floor is a new registration: the old rows keep their line, the new rows record theirs. Overtime counts only in the 2H section: Kalshi's 2H total includes overtime (checked on settled Nov 15, 17 and 22 games, e.g. 130 v 100 in regulation), while 1Q to 4Q and 1H do not. Entries are always graded by Kalshi's result, which is what pays.

## The tracker (the gate's data)
After every game, each team's season hit rate at every configured line is rebuilt from ESPN's period scores (the scoreboard's line scores), only from games already played.
An OVER hit is a game total above the line; an UNDER hit is below it (lines end in .5, so there are no pushes). Every game the team played counts, home or away.
Each section shows the live table: team, hits/games, percent, qualifies yes/no, qualified since (the date of the first night it was eligible on its current run).

## The gate (checked at the entry read, not from a fixed list)
1. The team's hit rate at that line is 90% or better on games played BEFORE the night of the game (games on the same night, even finished ones, do not count).
2. At least 10 games played (config `MIN_GAMES`).
3. If both teams in a game qualify on the same line and direction, that is ONE entry.
4. A team that falls below 90% stops at once, and re-enters on the night after it climbs back. No list is carried between nights: the gate is recomputed at every read.

## The entry
One read per game, 15 to 40 minutes before the tip (the target is about 30; the workflow runs every ten minutes and takes the first read in the window).
Over: buy YES at the ask. Under: buy NO at 1 minus the YES bid. Spread (YES ask minus YES bid) 5 cents or less, else no entry (counted as "wide" in the read log).
Taker fee on the entry (7% x p x (1 - p) a contract, `fillsim.fee`). Held to settlement; no sell. Nothing is placed anywhere.
Rung rule: the configured line if Kalshi lists it, else the nearest listed rung 1 to 3 points away in the HARDER direction only (a higher line for an over, a lower line for an under);
the nearest listed rung is the one used, and if its quote fails the spread or price test there is no entry (no walking to a farther rung). The rung used is recorded on the row.

## The control (per section and direction)
Every game that night with a usable rung is also bet BLIND on the same line with the same rung rule, the same read, the same fee, held to settlement, qualifying or not.
The page shows each lane beside its control.

## Reading
Olu reads each section at 10 settled entries (a lane's over or under, separately), then at 30, against its control and after fees. The page shows n of 10, then n of 30.
Paper only; the lane never trades and never changes another lane's record.

## Note, 2026-11-24: the first slate was backfilled from candles
The Nov 23 slate (10 games, tips 00:00Z-03:00Z Nov 24) took no live read: the GitHub cron missed every 15-40 minute window. This file was committed before those tips, so Olu asked for that one night to be recorded afterwards.
`python3 nba_qlines.py --backfill-2026-11-23` (a one-off; the date is hard-coded and any other date is refused) runs the lane's own code for each Nov 23 game: `team_rows` before the night for the qualifiers, `pick_rung` with the same
spread limit and harder-direction offsets, the blind controls, `look_many`. The only difference is the price: the YES bid and ask closes of Kalshi's 1-minute candles at tip-30 (the last candle at or before it), instead of a live quote. A game or rung with no candle quote, or a spread over 5 cents,
is skipped with its reason, as a live read would. Every row carries `backfilled: true` and `source: "candles@tip-30"`, and the page marks those rows and keeps the count ("N of M entries backfilled"). Games already read live are never overwritten. From Nov 24 on, entries are live reads.
