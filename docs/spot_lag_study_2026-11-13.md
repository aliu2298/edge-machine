# Spot lag: does the Kalshi 15-minute crypto book lag spot, and can it be traded? (Nov 13 2026)

Research only. No lane, page or Production change. The tests and the split were written down before any price in the recorder's files was analysed.

Data: the spot-lag recorder, Nov 9 18:04 UTC to Nov 13 22:37 UTC. Every second: Coinbase spot and the Kalshi best bid and ask for the open BTC, ETH and SOL 15-minute market; plus every trade print of each window with its exchange time. About 393 windows a coin. Found on Nov 9 to 11; the unseen days are Nov 12 and 13, read once.

"Return" is per bet after taker fees.

## Verdict

**There is no tradeable lag. The lag is in the data feed, not in the market.**

- The Kalshi quote the recorder collects is about **16 seconds old** when it arrives. It comes from the public market-data request, which serves a delayed snapshot.
- The market itself does not lag: **trade prints reprice within the same second** as a spot move.
- Tested on the recorded quote, "buy the side spot just moved towards" looks like +5% to +43%. Tested on the prices that actually traded, the same rule **loses 4% to 8%** in every version, on both the found and the unseen days.
- A late-window rule (spot is past the strike, the price has not caught up) had one promising cell on the found days and **made −3% on the unseen days**. Dropped.
- **Order delay does not rescue anything.** The honest version loses even with no delay at all.

No strategy, so no build spec. One recommendation at the end.

## 1. The recorded book is 16 seconds old

After spot moves 5 or more basis points inside 2 seconds (BTC, found days, 210 events):

| Seconds after the move | 0 | 2 | 5 | 10 | 20 | 30 |
|---|---|---|---|---|---|---|
| Recorded Kalshi mid, move in cents | −0.1 | 0.3 | 1.1 | 4.0 | 10.4 | 11.3 |
| Trade prints, move in cents | 4.8 | 4.9 | 4.9 | 5.3 | 5.8 | 6.3 |

- The recorded quote has done 10% of its move after 5 seconds and 92% after 20. ETH and SOL are the same.
- The prints have moved in the first second.
- **Direct check.** When the price is moving, a second's prints sit inside the bid and ask recorded for that second only 9% of the time. They sit inside the bid and ask recorded 15 seconds later 45% of the time. The best match is the quote recorded 16 to 17 seconds later, on all three coins, on the found days and again on the unseen days.
- This is what the earlier one-minute test saw ("spot moved, Kalshi had not followed"). Kalshi had followed. The quote we were reading had not.

## 2. Strategy A: after a spot move, buy the side it favours

Spot moves 3, 5 or 10 basis points in 2 seconds; buy the favoured side 0 to 5 seconds later; sell 10 or 30 seconds after, or hold to the end. 45 cells.

| Move 5+ basis points, order 2 seconds later | Priced off the recorded quote | Priced off what traded |
|---|---|---|
| Found days, sell after 30 seconds | +11.1% on 1,268 | −5.1% on 915 |
| Found days, hold | +11.8% on 1,268 | −7.6% on 1,063 |
| Unseen days, sell after 30 seconds | +7.4% on 1,836 | −5.3% on 1,255 |
| Unseen days, hold | +7.2% on 1,836 | −7.8% on 1,496 |

- Priced off what traded, every cell with a sale loses 4% to 7% at every delay, including none. That is two taker fees and the spread, with nothing to pay for them.
- Held to the end after the biggest moves (10+ basis points): +2% on about 100 found, +13% on about 100 unseen, scores 0.2 and 1.0. Not a result.
- The left-hand column is what a backtest on the recorder's quotes would have reported. Those prices were not there to trade.

## 3. Strategy B: late in the window, spot is past the strike

A fair chance for YES from spot, the strike, the time left and the last ten minutes' volatility; in the last 60 seconds the settlement average is allowed for. Bet when the fair chance beats the traded price plus fee by 3, 5 or 10 points. 45 cells, priced off what traded.

| | Found days | Unseen days |
|---|---|---|
| Last 120 seconds, 5+ points, order 2 seconds later | +59.7% on 149, score 2.0 | **−3.0% on 149** |
| Last 60 seconds, 5+ points, 2 seconds later | −33.3% on 69 | −21.4% on 62 |
| Last 30 seconds, 5+ points, 2 seconds later | −10.8% on 26 | −22.2% on 32 |

- No cell passed the correction on the found days. The one lead was checked once on the unseen days and failed.
- On the found days the same rule did as well when it was fed spot from 5 seconds earlier (+62%), so it was never a lag effect.
- In the last minute the result turns sharply negative as soon as the order is 2 or more seconds late: the people on the other side are faster.

## 4. Latency

- The recorder's requests take about 75 milliseconds (90% under 136) to both Kalshi and Coinbase from the server.
- The follower's ledger keeps one time per order, to the second. It acts on a signal in the same one-second cycle it first sees it. The signal's own publication time is not kept, so a true signal-to-order time cannot be measured from what exists.
- Assumed reaction time for a purpose-built loop: 1 to 2 seconds from a spot move to an order at the exchange.
- **Sensitivity: none.** Strategy A loses at every delay from 0 to 5 seconds. Strategy B's one lead did not depend on delay either, and failed.

## 5. Size

Book depth was not recorded. At the moments strategy B would have bought, 275 to 1,700 contracts printed in that second, so size was never the limit. The price was.

## Limits

- **Five days**, one stretch of market.
- **Spot is sampled once a second.** A lag shorter than a second cannot be seen here. It also could not be traded by an order path that takes a second.
- **Costs are taken from prints**: what a taker actually paid in that second or the next. A second with no such print is no trade.
- **Coinbase is not the settlement index.** The strike sat within about 3 basis points of the Coinbase mid at the open; the settlement value tracked Coinbase's last-minute average to within 0.5 to 1.1 basis points.

## Recommendation

- **Do not build a spot-lag lane.**
- **Treat any research priced off the public quote request with care wherever seconds matter.** In moving markets it is about 16 seconds behind. Entries and exits should be checked against trade prints, as the fill simulator does. Hourly and minute candles are not affected in the same way: their quotes are stamped by the exchange.
- The recorder does not need extending for this question. It can stop on schedule.

## Files

Research folder: `~/edge-research/spotlag_2026-11-13/`. `PREREGISTERED.md` and `RULES.md` (tests, notes and the unseen-day reads, with times), `build.py` (second-by-second grids), `l1.py` (lag profile), `l1b.py` (age of the recorded quote), `l23.py` (both strategies, on prints and on the recorded quote). The recorder's files are in `~/edge-research/spotlag_data/` and are read as data only.
