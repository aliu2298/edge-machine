# Pre-registration: mentions dump bid (paper watch), Nov 14 2026

Source: docs PR 464 (`docs/mentions_bounce_study_2026-11-14.md`, build spec at the end), run as a Sandbox paper lane `mentions_dump_bid` by Olu's go-ahead
on Nov 14 2026. Observation only: no orders, no VPS, no live loop.

## Pre-registration text (verbatim from the study)

"Mentions dump bid. Paper. Every Kalshi mention event; each minute a bid 20c under the last trade on both
sides of every word, until the first word is confirmed; honest fills, order 25 seconds late; sold 15c above the bid, otherwise held.
Read at 100, 300 and 600 fills, scored by event. Held if the main row is positive with t of 2 or more at 300 fills. Retired if it is
negative at 300. The 50c-or-less row is judged the same way and replaces the main row only if it is ahead at 600."

## Rule as built (nl_dump.replay, the engine of every dump and before-start watch)
- Both sides of every word, every Kalshi series in the Mentions category (465 listed today). Each whole minute a bid rests 20c under the last trade on its side.
  Needs a trade in the last 10 minutes, a last trade of 95c or less and a bid of 5c or more. Live 25 s late (headline) or 2 s (comparison).
- Fill: honest-v1, a trade strictly through the bid; size what $1 buys, capped by what printed through.
- Bids stop at the first word confirmed: the first trade at 97c or more in a word that last traded under 90c, over every word of the event. A bid whose minute is
  before that trade stands. The listed start is not used.
- Sell: a resting sale at the price before the drop minus 5c, up 60 s after the fill, filled only by a trade strictly through it (taker, with the taker fee,
  if the price is already there). Unsold contracts ride to the result. One open position a side of a word.
  The study's "sold 15c above the bid" is this rule at 20c under: +15c over the bid on the 20c rows, +10c on the 15c row (the coordinator's check; the
  doc's own words are "back within 5c of where it was").
- Fees: resting fills free unless the series lists a maker fee (none of the 465 does today; the code charges 0.0175 x p x (1 - p) if one appears); taker 0.07 x p x (1 - p).

## Rows (all on the same trades, each in both delay columns)
| row | rule | role |
|---|---|---|
| M20 | 20c under, all prices, sold back | the tested rule: the headline |
| M20L | 20c under, bids of 50c or less, sold back | a lead seen after the test: second row, never the headline |
| M15 | 15c under, sold back | the weakest pass in the study |
| H20 | 20c under, first fill of each side of a word held to the result | control |

## What counts
- Only bids whose minute is at or after 2026-11-14 19:00 UTC. An event is read once, after every one of its words has settled; one not fully settled in four
  days is dropped, not graded. Events are clusters for the score (the words of one event move together).
- Reads: 100 fills (positive or not, no decision), 300 (held if M20 is positive with t of 2 or more, retired if negative), 600 (M20L replaces M20 only if ahead).
- Keep the dip-hold lane running as it is until this lane has 300 fills, then compare; that call is Olu's.

## Request load
One series list and one markets listing a series (465, about two minutes at the shared throttle) every four hours at minute 11, then one event listing and one
trade history a word for each new event. Own ledger `data/mentions_dump_ledger.json`; workflow `mentions-dump.yml`; page section "Dump bid" on the Culture page.
