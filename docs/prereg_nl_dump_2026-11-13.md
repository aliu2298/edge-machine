# Nations League dump bid: pre-registration (Nov 13 2026)

Sandbox PAPER watch, observation only, never in Production. Written before the first game it counts was played. Nothing below is tuned: the rule
is Fable's stage-2 replay (`s2_replay.py`, flash dump map stage 2, docs PR 448) with the row list below. `nl_dump.py` reproduces it bet for bet
on the stored research tapes (720 cells, 671 bets, 0 differences).

## The lead
UEFA Nations League total goals (`KXUEFANLTOTAL`) is the one group of the flash dump map, stage 2, where a trailing bid looked green: 20c under,
+2.9% / +3.3% on the found dates and +12.4% / +10.2% on the later dates (2 s / 25 s), 49 to 59 bets a half, t about 1. Not significant, and the
table was read before the cell was chosen. This is the forward check.

## The rule (fixed)
- Every whole minute T a bid rests DEPTH under R, the last trade on the bid's side (YES price for a YES bid, 1 minus YES for a NO bid), on both
  sides of every rung of every game. None if nothing traded in the 10 minutes before T, if R is over 95c, or if the bid would sit under 5c.
- Live from T + DELAY to T + 60 s + DELAY (the next minute's order replaces it). DELAY 25 s is the headline (the order path as measured), 2 s the
  comparison. Not placed if a trade between T and T + DELAY is already at or under it.
- Fill (fillsim honest-v1): only a trade strictly under the bid while it is live; filled at the bid; size = what $1 buys, or what traded through.
- Sell (exit A): resting at R - 5c, up 60 s after the fill, filled only by a trade strictly through it; if the price is already there it is sold
  as a taker with the taker fee. Unsold contracts ride to the result.
- One position a side of a market at a time: no new bid until it is fully sold; none after one is left to the result.
- Fees: Kalshi lists no maker fee on this series (fee_type quadratic), so resting fills pay nothing; a taker sale pays 0.07 x p x (1 - p).

## Rows (each its own record, each in both delay columns, all on the same trades)
| Row | Bid under | Exit |
|---|---|---|
| D20 (headline) | 20c | sold at R - 5c |
| D15 | 15c | sold at R - 5c |
| H20 | 20c | simply held to the result (the D20 fills, no sell) |
| D40 | 40c, only bids in the last 3 hours of each market's trading | sold at R - 5c |

D40 is the deep-bid lead of the stage-2 report ("Stage 3 proposal"), found after the tables were read; it is shown for completeness and is not
a test of anything the report passed.

## How it runs
Each market is replayed once, after it settles, from Kalshi's public trade prints (one pull a market), in `nl-dump.yml` (hourly, GitHub Actions).
No VPS, no live loop, no orders. Games from Nov 14 2026 (the Nov 13 games were in the research sample). Own ledger `data/nl_dump_ledger.json`.

## Reads
- Score: bets cluster by game (the Kalshi event), `fdr_check.lane_stats`.
- Read once at 100 fills and once at 200 in the headline (25 s) column, per row. Keep = a positive return and a score of 2 or more. Otherwise retire.
- Pace: about one fill a market at 20c; about 100 markets in the week of Nov 14 to 17, so the first read lands at the end of this window. The next
  window is March.
- Not read, not scored: the 2 s column (comparison), the share that came back, the share sold.
