# Kalshi Climate study, part 1: what Kalshi's own prices can show (Nov 12 2026)

Research only. No lane, page or Production change. Every test, split and pass mark was written down before its result was read.

Updated Nov 13 2026 with all 21 low-temperature cities (section 5): a second rule passes.

Part 1 uses Kalshi data only. Part 2 (forecast against price, station readings against the brackets, settlement mechanics) needs outside weather data that is not downloaded yet.

"Return" is per bet after fees at the quoted price. "Score" is the return over its error, with a city-day counted as one outcome; 2 or more is the bar on the found period and 1.5 on the unseen one.

## Verdict

**Two strategies pass. Both are small, and they are one idea:** the evening before, the market under-prices the day's range. Highs land warmer than the favourite more often than cooler; lows land cooler more often than warmer. Prices alone do not give more: these markets are priced to within their costs.

| Rank | Strategy | Found period | Unseen period | Bets a week | Status |
|---|---|---|---|---|---|
| 1 | **Cold lean, daily highs**: NO on the bracket two cooler than the favourite, the evening before | +2.3% on 2,865, score 4.6 | **+1.3% on 2,016, score 2.5** | about 105 | Passes. Build spec below. |
| 2 | **Warm lean, daily lows**: NO on the bracket two warmer than the favourite, the evening before | +1.9% on 1,146, score 2.2 | **+2.1% on 1,021, score 3.0** | about 53 | Passes. Very thin books. Build spec below. |
| not ranked | Rain on the day: NO where rain is in play | +9.0% on 429, score 2.6 | +2.8% on 218, score 0.5 | about 36 | Fails. Looks like a summer pattern. Re-test May to Sep 2027. |
| not ranked | Hourly temperature markets | nothing passes | not opened | | The profit there is the spread. It needs a live sensor feed and constant quoting, which we cannot trade. |
| not ranked | Ladder sums (all six YES under 100c) | 0.2% of hourly snapshots, about 1.5c wide | not opened | | Too rare and too thin. |

## The map

529 climate and weather series, 211 active, about 88 million contracts in the last 30 days.

| Market | Contracts, last 30 days | Typical spread | Settles on |
|---|---|---|---|
| Daily rain by city (KXRAIN) | 32.3M | about 1c | The Weather Company figure for the airport gauge; needs more than 0 inches |
| Daily high, 21 cities | 0.1M to 7.6M each (LA, NYC, Miami lead) | 1 to 3c | The Weather Company figure for the official climate station |
| Daily low | 0.1M to 0.9M each | 3 to 14c | Same |
| Hourly temperature (Miami, NYC, Chicago, LA) | 1.1M to 2.1M each | wide in the middle prices | Synoptic Data reading at the hour, two decimals |

- A temperature ladder has six two-degree brackets. It opens at 10:00 ET the day before and trades until 11:59 pm local standard time on the day.
- Hurricanes, monthly totals, ski openings and global climate are small or one-off and were not studied.

## The data

| Set | What | Size | Found on | Confirmed on |
|---|---|---|---|---|
| Daily highs | Hourly bid and ask, 21 cities | 6,439 city-days | Nov 2025 to Jun 2026 | Jul to Nov 11 2026 |
| Daily rain | Hourly bid and ask, up to 35 cities | 2,725 city-days | Aug to Sep 2026 | Oct to Nov 11 2026 |
| Hourly temperature | One-minute bid and ask, 4 cities | 6,045 city-hours | first 60% of days | last 40%, not opened |
| Daily lows | Hourly bid and ask, 21 cities | 5,317 city-days | Dec 13 2025 to Jun 2026 | Jul to Nov 11 2026 |

## 1. Daily highs: what does not work

- **Buying at the quote, by price and hour.** 127 cells, YES and NO. Almost all lose. A 5-15c YES wins about 6% and costs 9c. The six asks add up to 106c to 117c.
- **Price path.** A bracket that moved 5c to 20c or more between two reads is fair afterwards, both ways. 72 cells, none passes.
- **Resting orders.** Join the bid or the ask, counted only if the price later trades through. They are picked off: resting YES bids lose 2% to 78%. Of 126 cells one passed, and it made +0.2% on the unseen months.
- **Yesterday's miss.** A warm miss yesterday makes a warm miss today slightly more likely (33% against 29%). Too weak to trade on its own.
- **Ladder sums.** All six YES cost under 100c after fees in 287 of 127,791 hourly snapshots, by about 1.5c. Six legs for 1.5c.

## 2. The cold lean

**What it is.** The evening before, the market's favourite bracket sits a little too cold.

| Where the high landed against the evening-before favourite | Found period | Unseen period |
|---|---|---|
| Cooler | 24% | 22% |
| Same bracket | 46% | 52% |
| Warmer | 30% | 26% |

It showed in every month of the found period and in 17 of 21 cities. The bracket two cooler than the favourite was priced 7.7c and won 4.3%.

**Rule.** At 10:00 pm ET the day before, with all six brackets quoted, find the favourite (highest mid price). On the bracket two cooler, buy NO at the quote and hold to settlement. All 21 cities, every day.

| | Bets | Won | Paid | Return | Score |
|---|---|---|---|---|---|
| Found period | 2,865 | 95.6% | 93.5c | +2.3% | 4.6 |
| Unseen period, read once | 2,016 | 96.0% | 94.8c | **+1.3%** | 2.5 |

- Every month was positive in both periods. October 2026 was only +0.3%.
- A calendar day counted as one outcome gives the same scores.
- **It is the cold side, not the price.** NO on the bracket two warmer, at the same prices: −0.6% then −0.3%. NO on every other non-favourite bracket costing 85c or more: −0.4% then −0.2%.
- **The resting version fails.** Offering instead of taking made +3.2% on the found period and +0.2% on the unseen one.

**Fills and depth.**

- Trade prints, a random 250 of the unseen bets: no quote was refuted; 88 were confirmed by 10 or more contracts trading at the price within the hour; the rest had too little trading to say.
- If every bet got the worst bid of the following hour instead of the quote: +0.4%.
- One evening's order books (15 cities): 17 to 847 contracts at the price, median 146.

**What it is worth.** A bet costs about 95c to win 5c, wins 96% and loses everything 4% of the time. +1.3% a bet, about 105 bets a week. It is fading: +2.3% then +1.3%. Olu has said expensive contracts are low value; this is one of those, and so is the lows rule in section 5. They are the only things here that passed.

## 3. Daily rain

On Aug to Sep 2026 the market priced rain at 27c on average and it rained on 23% of city-days. The day before was fair. From 6am on the day, NO won about 78% where it cost about 72c.

Rule written down before the unseen period was read: at 10am local, buy NO where it costs 30c to under 95c. Variants at 6am, 1pm and 4pm.

| Read | Found (Aug to Sep) | Unseen (Oct to Nov 11) |
|---|---|---|
| 10am | +9.0% on 429, score 2.6 | +2.8% on 218, score 0.5 |
| 6am | +9.6% on 502, score 3.1 | −0.6% on 256 |
| 1pm | +11.1% on 376, score 3.0 | +8.9% on 190, score 1.6 |
| 4pm | +12.4% on 302, score 3.2 | +1.4% on 148 |

**Fails.** October lost 8.5% and November made 33.8%. The likely reading: in summer, scattered showers miss the one airport gauge and the market over-bets rain; in autumn rain is widespread and the price is fair. That can only be tested next May to September.

## 4. Hourly temperature markets

Each market lives one hour and settles on the reading at the top of the next hour.

- **Buying at the quote loses heavily in the middle prices**: 5 minutes in, a 30-50c contract loses 13 to 16 points on either side. The spread is the cost.
- **A simple model does not beat the market.** Last hour's reading plus the usual change for that hour of day scores 0.11 against the market's 0.07 (lower is better). Betting where the model disagreed with the price lost about half the stake at every bar.
- The people quoting these markets watch the sensor live. The money is in the spread, and collecting it needs a live feed and constant quoting.

**Can those hourly readings be used on the daily-high ladder?** No. They are not the official station's high.

| City | Official high minus the day's highest hourly reading | Range |
|---|---|---|
| NYC | −0.3 on average; the hourly reading was higher on 28 of 61 days | −2.4 to +5.0 |
| Miami | +1.6 | −0.5 to +4.4 |
| Chicago | +1.0 | −1.6 to +3.5 |
| LA | +0.6 | −5.5 to +3.9 |

A bracket is two degrees wide, so a reading that can be off by two or more cannot rule brackets in or out.

## 5. Daily lows

**The map (found period, 20 cities).** Costs are much higher than on highs: the six asks add up to 117c to 145c. Buying at the quote: 137 cells, none passes. Resting orders: 126 cells, none passes. The low is not settled by morning: at 10pm on the day the favourite is priced 87c and wins 90%.

**The mirror of the cold lean.** If the market under-prices the day's range, lows should land cooler than the evening-before favourite more often than warmer. They do.

| Where the low landed against the evening-before favourite | Found period | Unseen period |
|---|---|---|
| Cooler | 28.6% | 28.4% |
| Same bracket | 45.7% | 51.7% |
| Warmer | 25.7% | 19.9% |

**Rule, written down before the unseen period was read.** At 10:00 pm ET the day before, buy NO at the quote on the bracket two warmer than the favourite. All low series. Hold to settlement.

| | Bets | Won | Paid | Return | Score |
|---|---|---|---|---|---|
| Found period | 1,146 | 93.6% | 92.0c | +1.9% | 2.2 |
| Unseen period, read once | 1,021 | 97.2% | 95.4c | **+2.1%** | 3.0 |

- **The found period was weak**: one cell, 4 of 7 months up. It was tested because it is the one mirrored prediction of the cold lean, not picked from the map.
- **The unseen period is cleaner**: every month up (Jul +2.9%, Aug +2.7%, Sep +1.8%, Oct +0.4%, Nov +3.7%). October was the weakest month here too.
- **It is the warm side, not the price.** NO on the bracket two cooler, same time: −0.4% then −2.1%.

**Fills and depth. This is the weak point.**

- No contract traded in the bracket in the following hour on 59% of nights.
- Trade prints, a random 250 of the unseen bets: 33 confirmed, 1 refuted, 216 too thin to say.
- If every bet got the worst bid of the following hour instead of the quote: +0.8%.
- One evening's order books (13 ladders): 3 to 95 contracts at the price, median 19. This is a one-contract lane.

## What part 2 needs

The edges people report in weather markets are information edges, and none of them can be tested on prices alone:

1. **Forecast against price.** The latest public model run before the entry time, turned into a chance per bracket.
2. **The station's reading so far against the brackets.** Brackets already ruled out; the high already in. Needs the official station's own readings, which section 4 shows the hourly markets do not give.
3. **Settlement mechanics.** How the settled figure relates to the official climate report, rounding, and the standard-time day.
4. **Why the market under-prices the range**, which would sharpen the two rules that passed. One guess to test: forecasts are hourly values, and a day's true high and low sit beyond the hourly ones.

The data is public (Iowa Environmental Mesonet and NOAA station reports and readings; Open-Meteo archived forecast runs), about 130 MB. It needs Olu's own go-ahead in the research session.

## Limits

- **One year, one unseen period per rule.** The cold lean was found on eight months and confirmed on four and a half.
- **Fills are quoted, not proven.** Two in three cold-lean bets had too little trading in the following hour to confirm the price either way.
- **Depth is one evening's snapshot.**
- **Rain has only 103 days of history**, all of it August to November.
- **Lows are thin.** Most quotes on the warm-lean bracket could not be checked against a trade, and the depth is a few contracts.
- **Four unseen periods have been read in this study**: cold lean (pass), its resting version (fail), day-of rain (fail), warm lean on lows (pass).

## Build spec: cold lean, version 1

For whoever builds. A new Sandbox paper lane; nothing else changes.

- **Rule:** at 10:00 pm ET the day before, on each city's next-day high ladder with all six brackets quoted, the favourite is the bracket with the highest mid price. Take the bracket two cooler. Buy NO at 1 minus the YES bid, taker fee, hold to settlement.
- **Skip** when there is no bracket two cooler, the YES bid is 0, or fewer than six brackets are quoted.
- **Scope:** the 21 daily-high series: KXHIGHNY, KXHIGHCHI, KXHIGHMIA, KXHIGHAUS, KXHIGHDEN, KXHIGHLAX, KXHIGHPHIL, KXHIGHTATL, KXHIGHTBOS, KXHIGHTDAL, KXHIGHTDC, KXHIGHTHOU, KXHIGHTLV, KXHIGHTMIN, KXHIGHTNOLA, KXHIGHTOKC, KXHIGHTPHX, KXHIGHTSAN, KXHIGHTSATX, KXHIGHTSEA, KXHIGHTSFO.
- **Entry timing:** one read at 10:00 pm ET, from the live book. Log the YES bid, the contracts at that bid, and the favourite's bracket.
- **Control row, same time, same page:** NO on the bracket two warmer. It should lose a little; if it starts winning as much as the lane, the lane is a price band and not a lean.
- **Record:** a city-day is one outcome. Paper only.
- **The one change from version 1:** none; this is version 1.
- **Retire or keep:** by the text below.

### Pre-registration text for the forward check

> Cold lean, version 1, Sandbox paper. Read once at 1,000 settled bets (about ten weeks).
> - Keep if the return after fees is above zero and above the control row's (NO on the bracket two warmer).
> - Retire if it is zero or below, or not above the control.
> - Stop early and review if the return is below −3% at 300 settled bets.
> - A score of 2 is not expected before about 1,000 bets and is not required earlier.
> - No city is dropped or added, and the read time is not moved, before that read.

## Build spec: warm lean on lows, version 1

For whoever builds. A second row of the same Sandbox paper lane, or its own lane; nothing else changes.

- **Rule:** at 10:00 pm ET the day before, on each city's next-day low ladder with all six brackets quoted, the favourite is the bracket with the highest mid price. Take the bracket two warmer. Buy NO at 1 minus the YES bid, taker fee, hold to settlement.
- **Skip** when there is no bracket two warmer, the YES bid is 0, or fewer than six brackets are quoted.
- **Scope:** the 21 daily-low series: KXLOWTNYC, KXLOWTCHI, KXLOWTMIA, KXLOWTAUS, KXLOWTDEN, KXLOWTLAX, KXLOWTPHIL, KXLOWTATL, KXLOWTBOS, KXLOWTDAL, KXLOWTDC, KXLOWTHOU, KXLOWTLV, KXLOWTMIN, KXLOWTNOLA, KXLOWTOKC, KXLOWTPHX, KXLOWTSAN, KXLOWTSATX, KXLOWTSEA, KXLOWTSFO.
- **Entry timing:** one read at 10:00 pm ET, from the live book. Log the YES bid, the contracts at that bid, and the favourite's bracket. The logged depth matters more here than on highs.
- **Control row, same time, same page:** NO on the bracket two cooler. It should lose.
- **Record:** a city-day is one outcome. Paper only.
- **The one change from version 1:** none; this is version 1.
- **Retire or keep:** by the text below.

### Pre-registration text for the forward check

> Warm lean on lows, version 1, Sandbox paper. Read once at 500 settled bets (about ten weeks).
> - Keep if the return after fees is above zero and above the control row's (NO on the bracket two cooler).
> - Retire if it is zero or below, or not above the control.
> - Stop early and review if the return is below −3% at 150 settled bets.
> - Also report the share of entries with fewer than 10 contracts at the bid. It does not decide keep or retire; it says how much could be traded.
> - No city is dropped or added, and the read time is not moved, before that read.

## Files

Research folder: `~/edge-research/climate_2026-11-12/`. `PREREGISTERED.md` holds the tests as written in advance, `RULES.md` the rules and the time each was written, and the scripts are `f1.py` (price map), `f2.py` (ladder sums), `f3.py` (price path), `f9_rest.py` and `f9_carry.py` (resting orders, yesterday's miss), `c_hold.py`, `c1_fill.py`, `c1_tape.py` (the cold lean), `l_hold.py`, `l1_fill.py`, `l1_tape.py`, `l1_depth.py` (the warm lean on lows), `f7.py` (rain), `f8.py` (hourly), `f5k.py` (hourly readings against the daily high).
