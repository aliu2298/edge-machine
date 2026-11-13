# 15-Minute rule C (S&P 500 underdog at 15c): honest fills, cross-market check, version 2 (Nov 13 2026)

Research only. No lane, page or Production change. Each test was written down before it was run; where a period had already been seen, the report says so.

Rule C: a resting buy at 15c on whichever side of the S&P 500 15-minute market gets there in the first 5 minutes, a resting sell at 2x, else sell at the bid with 1 minute left.

"Return" is per bet after fees. "Score" is the return over its error, with a clock hour counted as one outcome; 2 or more is the bar.

## Verdict

- **The rule survives honest fills on the S&P 500, if the orders are in the book within about 10 seconds of each window opening.** Later than that it fades.
- **It is not a cross-market strategy.** On the days the rule was chosen on, all 26 other markets lost on it.
- **It is not luck either, and it is not an underdog winning.** The S&P 15-minute market is new and thin. Just after a window opens, sellers sweep through an empty book and print far below the market. A resting bid catches the sweep and the price is back at once.
- **The opening is closing.** Deep sweeps are getting rarer by the day.
- **A version 2 is justified as a forward paper test**, with honest fills and an order delay built in. Spec at the end. No untouched S&P data is left to confirm it on: the market is nine days old.

## 1. Honest fills

Every S&P window since the market opened on Nov 5 (161 windows), on trade prints, through the fill simulator: a resting buy fills only on a print strictly through its price; a resting sell only strictly through its target, from 60 seconds after the fill; resting fills pay no fee.

| Both bids in the book | 15c, sell 2x | 25c, sell 2x |
|---|---|---|
| At the open | +56.7% on 47, score 4.0 | +35.3% on 107, score 3.5 |
| 5 seconds after | +49.2% on 43 | +27.8% on 104 |
| 10 seconds after | +46.1% on 40, score 3.0 | +28.3% on 102, score 2.8 |
| 30 seconds after | +29.7% on 29, score 1.6 | +13.8% on 91 |
| 60 seconds after | +29.7% on 29 | +18.6% on 89, score 1.7 |

By period, bids up 10 seconds after the open:

| | Nov 5 to 8 | Nov 9 to Nov 11 22:00 UTC (chosen on) | Since Nov 11 22:00 UTC (the lane's record) |
|---|---|---|---|
| 15c | +72% on 9 | +53% on 23 | −2.5% on 8 |
| 25c | +47% on 27 | +22% on 47 | +21% on 28 |

- The lane's own record (8 of 11 sold, +35.6%) uses "a print at the price fills". Under honest fills the same days are 8 bets: +21% with the bids up at the open, −2.5% from 5 seconds on.
- The median fill comes about two minutes after the open; 15% to 19% come in the first 10 seconds.
- "At the open" turns out to be reachable in practice: see "Order delay" below.

### Order delay: what a live order path can do

**Can a bid rest before the window opens? Almost certainly not.**

- The markets are listed well ahead: Monday's 25 S&P windows were created the Friday before, with the status "initialized". So the ticker is known in advance.
- Their public order books are empty until they open, on the S&P and on the crypto 15-minute markets. If orders could rest early, market makers would be there.
- In 161 S&P windows no trade printed before the open, and none in the first second. The first print came 2.0 seconds after the open at the earliest, 6.7 seconds at the median.
- This cannot be proven from public data; only a rejected or accepted order would settle it. But no trade prints in the first 2 seconds, so an order that lands 1 to 2 seconds after the open is in time for everything. In the table above, "at the open" and "2 seconds after" give the same result.

**How fast the live path is today** (measured by Production Moves, read-only):

| Path | Open to both orders resting | Row to read |
|---|---|---|
| Today's fastest loop (45-second tick) | about 25 seconds at the median, 55 to 60 at worst | between the 20- and 60-second rows |
| A clock-aligned loop: orders prepared before each quarter hour, sent 1 to 2 seconds after the open | 1 to 3 seconds looks possible; the signed order request itself has not been timed | the "at the open" row |

At today's speed:

| Both bids up | 15c, sell 2x | 25c, sell 2x |
|---|---|---|
| 20 seconds after the open | +33.3% on 31 | +18.4% on 94 |
| 30 seconds after | +29.7% on 29 | +13.8% on 91 |
| 60 seconds after | +29.7% on 29 | +18.6% on 89 |
| Same delays, since Nov 11 only | −2.5% to −1.2% on 8 | +14% to +21% on 28 |

So at about 25 seconds the 15c row is worth roughly +30% on the whole record and nothing on the last two days; the 25c row roughly +15% to +20%, and it held on the last two days. A clock-aligned loop is what the rule needs to reach the upper rows.

## 2. The page note against its background table

They describe different days.

| Rule C's cell on the other 26 markets | Pooled | Markets positive |
|---|---|---|
| Nov 9 to Nov 11 22:00 UTC (what the note quotes) | −17.3% on 2,052 | 0 of 26 |
| Since Nov 11 22:00 UTC (what the table shows) | −2.3% on 1,432 | 10 of 26 |

- The five markets that look good in the table (Dogecoin +32% on 65, USD/JPY +21%, AUD/USD +21%, Hyperliquid +14%, Gold +14%) all lost on the earlier days (−5%, −26%, −34%, −14%, −13%).
- No market but the S&P is positive in both periods. At 50 to 100 bets a market, one market's figure moves by 12 to 15 points on luck alone.

## 3. Cross-market, or an S&P fluke?

**Not cross-market.** Five price levels (10 to 30c) by three sell multiples, 27 markets and 5 groups, 480 cells, on the chosen-on days:

- Outside the S&P no cell is positive with a score above 1.4. Pooled, the other markets lose 7% to 20% in every cell.
- Since Nov 11 the pooled others are about flat (−8% to +8% by cell).

**Not a fluke of picking the best market.** Shuffling the market labels 2,000 times never produced a best-of-27 as good as the S&P's +61.6% on the chosen-on days. The S&P is positive in 14 of 15 cells on those days and in 14 of 15 since.

**Not a mispriced underdog.** At the quote, the S&P's cheaper side wins no more than its price:

| Cheaper side's ask (minutes 2, 5, 10) | Chosen-on days | Since Nov 11 |
|---|---|---|
| 5-15c | won 0 of 29 | won 3 of 20 |
| 15-25c | 12% at 20c (40) | 16% at 20c (32) |

Buying it at the ask instead of resting a bid does not work: at a 17c cap with a sell at 2x, +30% on 16 then −27% on 13; held to the end, −51% then +4%.

**What it is.** In the first seconds and minutes of an S&P window, trades print far from the market: a sale at 4c, then 24c, while the market sits at 45c. Someone is selling through a thin book. A bid resting at 10c to 25c is filled by the sweep, and the price it resells at is simply where the market already was.

**It is fading.**

| S&P windows with a print through 10c or 90c, 5 seconds to 5 minutes after the open | |
|---|---|
| Nov 6 | 6 of 23 |
| Nov 9 | 5 of 25 |
| Nov 10 | 9 of 25 |
| Nov 11 | 0 of 25 |
| Nov 12 | 3 of 25 |
| Nov 13 | 0 of 25 |

Prints through 25c or 75c are steady, 13 to 20 windows of 25 a day.

## 4. Levels, multiples and size (S&P, bids up 5 seconds after the open)

Found on Nov 5 to Nov 11 22:00 UTC:

| Level | Sell 1.5x | Sell 2x | Sell 3x |
|---|---|---|---|
| 10c | +43% (20) | +80% (20) | +155% (20), score 4.9 |
| 15c | +24% (35) | +66% (35), score 3.9 | +80% (35) |
| 20c | +28% (47) | +40% (47) | +66% (47) |
| 25c | +15% (76) | +32% (76), score 2.5 | +35% (76) |
| 30c | +8% (91) | +16% (91) | −9% (91) |

- By the rule written in advance (best score with positive neighbours) the cell is 10c with a sell at 3x. Since Nov 11 it has had 3 bets, 2 sold. That cannot confirm anything.
- **Size at 10c:** a $1 order fills 83% of its size; $10 fills 51%; $25 fills 31%. Dollars made per bet stop rising at about $25 a bet. This is a small-stake trade.
- About 3 bets a trading day at 10c, 7 at 15c, 15 at 25c, on 25 windows a day. The market trades only in US cash hours.

## Limits

- **Nine days of one market.** 161 windows, seven trading days. Every period has now been looked at; only the forward record can confirm.
- **Order delay is the whole question for live.** The paper record assumes the bids are already there. Today's loop is about 25 seconds late; whether orders can rest before the open could not be tested without placing one.
- **Others can do this.** One more bidder at 11c takes the fill. The fall in deep sweeps may already be that.
- **The other markets were tested on minute candles**, not prints; the candle method matched the tracker's print-based entries on 3,518 of 3,525.

## Build spec: rule C version 2 ("S&P opening sweep")

For whoever builds. Sandbox paper only. Rule C version 1 keeps its record; version 2 is a fresh one.

- **Rule:** on every KXINX15M window, two resting bids, one on YES and one on NO, at the level, placed a set delay after the window opens and cancelled 5 minutes after the open if unfilled. The first to fill is the bet; the other is cancelled. Then a resting sell at the multiple, from 60 seconds after the fill; if unsold with 1 minute left, sell at the bid.
- **Rows (each its own record):** 10c sell 3x; 15c sell 2x; 25c sell 2x.
- **The one change from version 1:** fills by the fill simulator's honest rule on trade prints (a buy only on a print strictly through the level, a sell only strictly through the target), with the bids going up 5 seconds after the open. Two comparison rows per level: bids up 2 seconds after, and 30 seconds after.
- **Fees:** none on a resting fill; the taker fee on a sale at the bid.
- **Scope:** the S&P 500 only. The other 26 markets stay background rows.
- **Also log:** seconds from the open to the fill, contracts printed through the level, and the day's count of windows with a print through 10c/90c.
- **Before anything live:** a clock-aligned loop (both orders prepared before the quarter hour, sent 1 to 2 seconds after the open) and its measured time to both orders resting. On today's loop (about 25 seconds) the 15c and 10c rows should be read at the 30-second comparison row.

### Pre-registration text for the forward check

> Rule C version 2, S&P 500, Sandbox paper, from the first window after the build. Fills by the fill simulator's honest rule, bids up 5 seconds after the open.
> - Read 25c at 150 settled bets, 15c at 80, 10c at 40. One read each.
> - Keep a row if its return after fees is above zero with a score of 1.5 or more, and its 30-second comparison row is also above zero.
> - Retire a row if its return is zero or below at its read.
> - Stop early: if a row has fewer than one bet per trading day over any ten trading days, it is closed as "the opening has gone" whatever its return.
> - No level, multiple or delay is changed before the reads. No other market is added on its own record without its own pre-registration.

## Files

Research folder: `~/edge-research/sw15_2026-11-13/`. `PREREGISTERED.md` (tests and notes with times), `lib15.py`, `t12.py` (the other markets, by period), `t34.py` (grid and shuffle), `t5.py` (calibration and the taker version), `t6.py` and `t7.py` (S&P prints through the fill simulator: delays, levels, size), `peek.py` (opening prints by day).
