# Kalshi Climate study, part 2: forecasts and station data against the prices (Nov 13 2026)

Research only. No lane, page or Production change. Every test, split and pass mark was written down before its result was read.

Part 1 (`climate_study_part1_2026-11-12.md`) used Kalshi's prices alone. Part 2 adds the outside data: the official daily reports, the stations' own readings and the public forecast, for the daily high and low ladders.

"Return" is per bet after fees at the quoted price. "Score" is the return over its error, with a city-day counted as one outcome; 2 or more is the bar on the found months and 1.5 on the unseen ones. Found months are Dec 2025 to Jun 2026; unseen months are Jul to Nov 11 2026.

## Verdict

**The outside data gives no new strategy. It improves one rule a little and explains both.**

- The public forecast does not beat the price at any entry time. Where it points, the price has already gone, and further.
- Same-day station readings are useless at our speed. The market is watching finer sensor data than the hourly reports.
- The one gain: the cold lean on highs is better when it is skipped on days the public forecast sits above the favourite. Unseen months: +1.7% a bet instead of +1.4%.

### Final ranking, parts 1 and 2

| Rank | Strategy | Found months | Unseen months | Bets a week | Contracts at the price |
|---|---|---|---|---|---|
| 1 | **Cold lean on highs, version 2**: NO on the bracket two cooler than the favourite, 10pm ET the day before, skipped when the public forecast is above the favourite | +2.6% on 1,993 | **+1.7% on 1,601, score 2.9** | about 84 on 18 cities | median 146 |
| 2 | **Warm lean on lows**: NO on the bracket two warmer than the favourite, same time | +1.9% on 1,146 | **+2.1% on 1,021, score 3.0** | about 53 | median 19 |

At one stake a bet, that is about 1.4 stakes a week from the first and 1.1 from the second, before any slippage. Both buy contracts near 95c. No cheap-contract strategy came out of this study: every cheap YES tested, with or without a forecast behind it, loses.

Not ranked, all failed: forecast against price (48 cells), "midnight days" (20 cells), forecast tilt (24 cells), same-day readings (38 cells), and from part 1 day-of rain, hourly markets, ladder sums, resting orders.

## The data

| Set | Source | Cover |
|---|---|---|
| Official daily reports (high, low) | Iowa Environmental Mesonet, NWS CLI products | 21 stations, 2025 and 2026 |
| Station readings (hourly and special reports, with the 6-hour max and min) | Iowa Environmental Mesonet, ASOS | 21 stations, Oct 30 2025 to Nov 12 2026 |
| Public forecast (NBM station text: daytime max, overnight min, 3-hourly temperatures, four runs a day) | Iowa Environmental Mesonet, MOS archive | 18 stations, Dec 2025 to Nov 2026 |

- The download was capped at the 128 MB Olu approved. The forecast files came uncompressed, so San Antonio, Seattle, San Francisco and November 2025 were cut.
- No look-ahead: a station reading counts only if it is 10 minutes older than the entry; a forecast run only if it is 2 hours older.
- Anything fitted (the forecast's error spread, city shifts) is fitted on the found months, and inside them with the bet's own month left out.

## 1. Settlement

Kalshi's settled figure equals the official NWS daily report on 99.9% of city-days: 5,974 of 5,983 highs and 5,202 of 5,208 lows. The station list in the build specs is right. There is no settlement quirk to trade.

## 2. Why the evening-before market is too narrow

| | Highs | Lows |
|---|---|---|
| Official figure is beyond the most extreme hourly reading | 63% of days | 42% of days |
| By how much, on average | 0.76 degrees | 0.51 degrees |

- The official high and low come from one-minute sensor data. Hourly values, in readings or in forecasts, sit inside them.
- Lows are also set late: after 6pm standard time on 20% to 27% of days, depending on the season. A "morning low" misses those.
- A price built from hourly forecast values is short at both ends. That is the cold lean on highs and the warm lean on lows.

## 3. Same-day station readings: nothing

Reads at 10am, 1pm, 4pm, 7pm and 10pm local, found months only.

- **Brackets that can no longer win.** Thousands at each read. The bid was above zero on 1 to 11 of them. Nothing to sell.
- **The highest reading so far, in the evening.** Where its bracket was still under 99c at 7pm, it won 35% of the time at a price of 38c. The market disagreed with the hourly reports and was right two times in three.
- **A table of how much further the high or low goes** (by hour, season and how far the last reading is from the extreme so far). It scores 0.08 to 0.18 against the market's 0.03 to 0.10; lower is better. All 24 cells lose, 5% to 72%.

The unseen months were not opened for this family. Trading the day itself needs a live one-minute feed and fast quoting. That is not something we can do.

## 4. Forecast against price: the price wins

The forecast is the latest NBM station run: the daytime max (or morning min), widened to the whole standard-time day with its 3-hourly temperatures. A chance for each bracket comes from how far the official figure has landed from that forecast. Bets where the chance beats the cost by 3, 6 or 10 points, at 4pm ET and 10pm ET the day before, 6am and 10am on the day.

| Score, lower is better | Forecast | Market |
|---|---|---|
| Highs, 10pm ET the day before | 0.125 | 0.109 |
| Highs, 10am on the day | 0.119 | 0.094 |
| Lows, 10pm ET the day before | 0.122 | 0.110 |
| Lows, 10am on the day | 0.101 | 0.038 |

- All 48 cells lose: highs 5% to 51%, lows 6% to 74%.
- **The forecast does carry news.** When it sits above the favourite the evening before, the high lands warmer 39% of the time and cooler 18%. When it sits below, lows land cooler 40% and warmer 13%.
- **The news is already in the price, and more.** YES on the bracket the forecast points to: −23% on highs when it points warm, −17% to −30% when it points cool. 24 tilt cells, none passes.

## 5. Midnight days: real, and priced

The usual forecast high is a daytime figure and the low a morning one. The market settles on midnight to midnight, standard time. On some days the high is at the start of the day or the low at the end.

- Such days are 5% of highs and 16% of lows the evening before.
- The favourite does miss the expected way on them: highs land warmer 38% against 29% on other days; lows land cooler 37% against 28%.
- It is in the price. NO on the favourite loses 5% to 12%. YES on the forecast's bracket loses 24% to 41% (one cell is +7% on 82 bets, score 0.3). 20 cells, none passes.

## 6. The one gain: when to skip the cold lean

The tilt table split the cold lean by where the public forecast sat against the favourite. I had written down the opposite guess (take the bet when the forecast agrees with it); that fails. The found months showed:

| Public forecast against the favourite | Found months | Unseen months, read once |
|---|---|---|
| Below | +4.3% on 607 | +1.9% on 574 |
| Inside | +1.9% on 1,386 | +1.6% on 1,027 |
| Above | −0.2% on 319 | −2.5% on 129 |

**Rule, written down before the unseen months were read:** the cold lean, skipped when the forecast is above the favourite.

| Unseen months, 18 cities | Bets | Return | Score |
|---|---|---|---|
| Cold lean, version 1 | 1,730 | +1.4% | 2.5 |
| **Version 2: skip when the forecast is above** | 1,601 | **+1.7%** | 2.9 |
| The bets version 2 leaves out | 129 | −2.5% | |

- Every unseen month is positive. October is again the weakest (+0.2%).
- **Why it would work:** the public forecast reads low (section 2). People who follow it bid the cool brackets. When the forecast itself is above the favourite, nobody is bidding them, and the bracket two cooler is not over-priced.
- **Taking only "forecast below"** also passes its mark (+1.9% on 574, score 1.8) but October loses and two bets in three are given up. Not recommended.
- **Lows:** the same split on the warm lean is small and does not mirror. No filter for lows.

## Limits

- **One year.** Found on seven months, confirmed on four and a half.
- **The gain from version 2 is small**: 0.3 points a bet, from dropping about 7% of bets. It passed its mark, but the split came from a table, not from my first guess.
- **Six unseen periods have been read in this study.** Cold lean (pass), its resting version (fail), day-of rain (fail), warm lean on lows (pass), cold lean version 2 (pass), cold lean on "forecast below" only (marginal pass).
- **Forecasts cover 18 of 21 cities**, and from December 2025.
- **Fills are quoted, not proven**, as in part 1. Lows are thin.

## Build spec: cold lean on highs, version 2

For whoever builds. A Sandbox paper lane. This replaces the version 1 spec in part 1.

- **Rule:** at 10:00 pm ET the day before, on each city's next-day high ladder with all six brackets quoted, the favourite is the bracket with the highest mid price. Take the bracket two cooler. Buy NO at 1 minus the YES bid, taker fee, hold to settlement.
- **Skip** when there is no bracket two cooler, the YES bid is 0, fewer than six brackets are quoted, **or the public forecast is above the favourite**.
- **The one change from version 1:** the forecast skip.
  - Forecast: the newest NBM station text run (NBS) for the city's station that is at least 2 hours old. Take the larger of its daytime max for the day and its 3-hourly temperatures inside the day (midnight to midnight, local standard time). Add the city's shift from `c1f_shifts.json` (all within 0.4 of a degree; 0 for a city not listed).
  - "Above the favourite" means that number is more than half a degree over the favourite bracket's top. If the favourite is the open-ended top bracket, it is never above.
  - If no forecast can be read, take the bet and mark the row "no forecast".
- **Scope:** the 21 daily-high series listed in part 1. Stations: NYC KNYC, Chicago KMDW, Miami KMIA, Austin KAUS, Denver KDEN, Los Angeles KLAX, Philadelphia KPHL, Atlanta KATL, Boston KBOS, Dallas KDFW, Washington KDCA, Houston KHOU, Las Vegas KLAS, Minneapolis KMSP, New Orleans KMSY, Oklahoma City KOKC, Phoenix KPHX, San Diego KSAN, San Antonio KSAT, Seattle KSEA, San Francisco KSFO.
- **Entry timing:** one read at 10:00 pm ET, from the live book. Log the YES bid, the contracts at that bid, the favourite's bracket, the forecast and its run time.
- **Control rows, same time, same page:** (a) NO on the bracket two warmer; (b) the skipped bets, recorded but not counted in the lane.
- **Record:** a city-day is one outcome. Paper only.
- **Retire or keep:** by the text below.

### Pre-registration text for the forward check

> Cold lean on highs, version 2, Sandbox paper. Read once at 1,000 settled bets (about eleven weeks).
> - Keep if the return after fees is above zero and above control (a), NO on the bracket two warmer.
> - Retire if it is zero or below, or not above control (a).
> - The skip is kept if the skipped bets, control (b), returned less than the lane. If they returned more, the lane goes back to version 1 on the same record and the skip is dropped.
> - Stop early and review if the return is below −3% at 300 settled bets.
> - No city is dropped or added, and the read time is not moved, before that read.

The warm lean on lows keeps its part 1 spec and pre-registration text unchanged.

## What would be needed for more

- **A live one-minute feed from the official stations and continuous quoting.** That is where the same-day money is, and the hourly markets in part 1 say the same.
- **A second summer for rain.** The day-of rain NO made +9% in August and September and +2.8% after. It can only be re-tested from May 2027.

## Files

Research folder: `~/edge-research/climate_2026-11-12/`. `PREREGISTERED.md` and `RULES.md` hold the tests and rules as written in advance, with times. Part 2 scripts: `pull_ext.py` (the download), `ext_lib.py`, `ext_reads.py` (readers and the join), `f6.py` (settlement), `f5.py` (same-day readings), `f4.py`, `f4b.py`, `f4c.py` (forecast against price, midnight days, tilt), `c1f_hold.py` (version 2 on the unseen months), `c1f_shifts.json`. Downloaded files are in `ext/` and are data only.
