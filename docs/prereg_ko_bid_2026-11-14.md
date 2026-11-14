# Before-kickoff dump bid: pre-registration (Nov 14 2026)

Sandbox PAPER watch, observation only, never in Production. Written before the first bid it counts. The rule is the build spec of the flash dump
condition study (docs PR 450), unchanged; `nl_dump.replay` is the engine (it reproduces Fable's stage-2 replay bet for bet).

> "Before-kickoff dump bid, soccer game markets. Paper only. Read at 50 and at 100 fills a row. Keep = positive return after fees with t of 2 or
> more, clustered by game, and both halves of the record positive. Retire = under that at 100 fills. Row 2 is judged on its own. No retuning of
> depth, clock or exit before the 100-fill read."

## The lead
National-team soccer game markets, the stage-2 bid placed before kickoff: found dates +11.7% (56 bets, t 1.74), later dates +18.4% (92 bets,
t 3.69); with bids kept to 3 hours or more before the listed kickoff, +17.4% on 83 bets in 43 games (t 3.1) at 25 s. It missed the written bar on
the found dates and the 3-hour cut was made after looking, so it is a lead, not a pass. It did not carry to the Nations League total or to the
early run-up in props or NBA points. Club leagues were never pulled: row 2 is untested.

## The rule (fixed)
- Kalshi soccer game-winner markets: home, tie and away, every leg of every game.
- From the first trade until 3 hours before the listed kickoff (Kalshi's expected expiration minus 6 hours), every whole minute T a bid rests 15c
  under R, the last trade on the bid's side, on both sides of every leg. None if nothing traded in the 10 minutes before T, if R is over 95c, or
  if the bid would sit under 5c. Live from T + 25 s to T + 85 s (the next minute's order replaces it).
- Fill (fillsim honest-v1): only a trade strictly under the bid while it is live; filled at the bid; size = what $1 buys, or what traded through.
- Sell: resting at R - 5c, up 60 s after the fill, filled only by a trade strictly through it; if the price is already there it is sold as a
  taker with the taker fee. Unsold contracts ride to the result. One position a side of a market at a time.
- Fees: national-team series pay no maker fee (fee_type quadratic); club series pay 0.0175 x p x (1 - p) on every resting fill, buy and sell
  (quadratic_with_maker_fees); a taker sale pays 0.07 x p x (1 - p).
- Columns: 25 s order delay is the headline (the order path as measured), 2 s the comparison.

## Rows
1. National teams: KXCONCACAFNLGAME, KXAFCONGAME, KXINTLFRIENDLYGAME, KXUEFANLGAME.
2. Club leagues: KXEPLGAME, KXLALIGAGAME, KXSERIEAGAME, KXBUNDESLIGAGAME, KXUCLGAME. Never tested; judged on its own.

## What counts
Games from Nov 14 2026, and only bids placed after Nov 14 2026 12:00 UTC (the rule was fixed before then). Each market is replayed once after it
settles, from Kalshi's public trade prints, in `ko-bid.yml`. The replay is after the fact, so a late or missed run is caught up by the next one
(the ledger holds every market read; a run reads whatever settled markets are not in it).

## Read
At 50 and at 100 fills a row, headline column, clustered by game (`fdr_check.lane_stats`). Keep = a positive return after fees, a score of 2 or
more, and both halves of the record positive. Retire = under that at 100 fills. No retuning of depth, clock or exit before the 100-fill read.
The 2 s column, the share that came back and the share sold are description.

## Pace
National-team games come in windows (the current one ends Nov 17; the next is March). Club leagues resume Nov 20 to 21. About one fill for every
six markets, a median of 11 contracts through the bid: it is small and cannot carry size.
