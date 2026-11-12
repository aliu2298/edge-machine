# Version 2 research: Eredivisie draw and commodities favourite band (Nov 12 2026)

Two lanes were dug into for a pattern that separates winners from losers. The filters to try were written down before any filtered result was read. A filter had to beat version 1 by 2 points on one period, then again on a second period with a score of 2 or more.

"Points" is the share of bets won minus the price paid. Returns are per bet after fees.

## Summary

| Lane | Result |
|---|---|
| Eredivisie draw | **A version 2 holds.** Back the draw only when the home side is the favourite, and only inside 24 hours of kickoff. Built as a Sandbox paper lane on a fresh record. |
| Commodities favourite band | **No version 2.** One filter passed the numbers test but does not show in the lane's own bets. Keep version 1. |

Nothing was promoted.

## Eredivisie draw

### What separates winners from losers

**1. Who the favourite is.** Inside the band, the draw beats its price when the home side is favoured and not when the away side is.

| Period | Prices | Home favourite | Away favourite |
|---|---|---|---|
| 2013/14 to 2020/21 | Bookmaker close | +1.5 points (443) | +4.0 points (263) |
| 2021/22 to 2025/26 | Bookmaker close | +8.8 points (264) | −0.8 points (168) |
| 2025/26 | Kalshi, 3h before kickoff | +15.8 points (46) | +1.6 points (32) |
| 2026/27 so far | Kalshi, 3h before kickoff | +18.9 points (31) | −12.5 points (19) |

The home favourite was ahead in each of the last five seasons. Before that it was not a pattern.

**2. When the bet is placed.** Version 1 logs its bets a median 4.5 days before kickoff. The research was on closing prices.

| Entry on Kalshi | Bets | Drew | Price | Return |
|---|---|---|---|---|
| 4.5 days before kickoff | 50 | 24.0% | 23.3c | −5.7% |
| 24 hours before | 127 | 32.3% | 23.3c | +30.4% |
| 3 hours before | 128 | 32.0% | 23.2c | +29.9% |

### What did not separate them

On 13 seasons of bookmaker prices: low goal totals, draw-prone teams, a close match, and the draw price drifting. Two looked good on the first eight seasons and vanished on the last five. On Kalshi: whether the draw price fell in the last day, and 24h against 3h entry.

Fixture congestion could not be tested: there is no European fixture list before 2021.

### Version 2

Version 1's band and ask cap, plus: the home side is the favourite, and kickoff is 24 hours away or less.

Replay on Kalshi's history, entry 24h before kickoff, honest fills:

| | Bets | Match days | Drew | Price | Return |
|---|---|---|---|---|---|
| Version 2 | 76 | 58 | 38.2% | 23.2c | +55.6% |
| Version 2, 2025/26 | 45 | 34 | 35.6% | 23.3c | +44.7% |
| Version 2, 2026/27 | 31 | 24 | 41.9% | 23.2c | +71.3% |
| Version 1, same entry time | 127 | 76 | 32.3% | 23.3c | +30.4% |

- **Built:** Sandbox lane `ere_draw_home`, fresh record from Nov 12. Version 1 keeps its record. Pre-registration: `docs/prereg_ere_draw_v2_2026-11-12.md`.
- **Gate check:** the replay passes the evidence test (score 2.42, both halves up, up without its best day). The lane's own record is empty, so the gate itself reads "no entries yet".

### Caveats

- The first eight seasons do not show the home-favourite pattern. It is recent.
- It is one of eight filters tried.
- Kalshi's 2025/26 season is the same matches as the last bookmaker season. Only 2026/27, 31 bets, is new evidence.
- About 2 bets a matchweek: 30 bets is about four months.

### The lane's live run, for reference

Live Oct 11 to Nov 2: 4 wins in 17, −4.3%. Paper: +22.6% on 29. Those bets were placed days before kickoff, and both the home and the away favourite were backed.

## Commodities favourite band

### The longer history

Version 1 was replayed on every daily ladder Kalshi still serves hourly prices for: six commodities, Apr 1 to Nov 11, 771 closes, 316 bets.

| Period | Bets | Won | Price | Points | Return (honest) |
|---|---|---|---|---|---|
| Apr to Aug | 207 | 80.7% | 74.5c | +6.1 | +3.6% (186) |
| Sep to Nov 11 | 109 | 70.6% | 74.3c | −3.7 | −9.4% (102) |

Over the whole period the band is close to fair.

### What was tried

| Filter | Apr to Aug | Sep to Nov 11 | Holds |
|---|---|---|---|
| Metals v energy | Metals +8.3 points | Metals −7.0 | No |
| Monday | +19.7 points (52) | −19.6 (18) | No, it reversed |
| Quiet day v busy day | No gap | Quiet +1.4, busy −8.4 | Not a candidate |
| Rung price rising | +8.2 points | −2.7 | No |
| Ask 75-80c v 70-75c | +8.3 v +3.9 | +5.5 v −11.7 | Passes the numbers test |

### Why there is no version 2

The 75-80c half passed the written test. I did not build it, for three reasons:

- **It does not show in the lane's own bets.** The lane's 37 bets at 75-80c returned +9.2%; its 31 at 70-75c returned +9.8%.
- **Part of the second period had been seen.** The Nov 1 study had already shown this split on Sep and Oct. On Nov 1 to 11, the only unseen part, both halves lost (5 and 8 bets).
- **It is a price band, not a selection reason.** On honest fills the 75-80c half made +3.1% on the second period, a score of 0.4.

Recommendation: keep version 1. If Olu wants the 75-80c half tracked anyway, it can run as a paper row.

### One more thing about version 1

The lane's own record is better than the replay of the same rule over the same closes.

| Oct 8 to Nov 11 | Bets | Won | Return |
|---|---|---|---|
| The lane | 68 | 84% | +9.5% |
| Replay, same closes | 41 | 71% | −7.1% |

The lane reads the live book up to three times in its window and needs 25 contracts on offer; the replay takes one hourly quote. On 12 of 41 shared closes they picked different rungs, and on 27 the replay found nothing in band. So the replay is not the lane, and the lane's record cannot be checked on history. Its live record (21 wins in 25, +11.5%) is the best evidence, and it is small.

## 15-Minute lanes, re-graded

The two kept S&P 500 rules, on every S&P 500 window in the ledgers (Nov 9 to 11, 75 windows). Their fresh records from Nov 11 are still empty.

| Rule | Page | Honest | If touches fill |
|---|---|---|---|
| A · favourite with 5 minutes left | −0.1% (71) | −0.4% (65) | −0.4% (65) |
| C · underdog at 15c, sell at 2x | +61.6% (30) | +58.5% (27) | +62.6% (30) |

Rule C holds up on honest fills. It is three days of data. Rule A is flat. Lead Swap is being rebuilt by another session and was not re-graded.

## Files

- Research folder: `~/edge-research/lanes_v2_2026-11-12/` (the menu written in advance, pulls, analysis scripts).
- Bookmaker history: football-data.co.uk, Eredivisie, 2013/14 to 2026/27.
