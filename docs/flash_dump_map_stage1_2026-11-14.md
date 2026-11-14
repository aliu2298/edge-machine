# Flash dump map, stage 1: the one-minute screen (Nov 14 2026)

Research only. No lane, page or Production change. Stage 1 of the funnel; it stops here for Olu's pick of series for stage 2.

Run as written down in stage 0 (`flash_dump_map_stage0_2026-11-13.md`): 94 series, up to 50 random markets each, one-minute candles, 8,512 requests through one cached puller, no errors. 4,212 markets screened in the main sample, 2,200 more for the first-week check.

No strategy is tested here. A one-minute candle shows that a low printed, not how many contracts printed there or whether a bid could have been filled.

## What the screen found

**1. The dump rate as defined does not separate markets.** Every 15-minute series shows about 170 to 270 events per 100 markets at the same depth (17 to 18c). That is a 15-minute binary swinging on its own, not a sign of sweeps. By this measure the S&P 500 looks like Solana.

**2. Two added measures do separate them.** Both were added after the table was first read, from the cache, to make the pick possible:

- **Came back:** of all one-minute drops this deep, whatever happened next, the share where the price two minutes later was back within 5c. The dump definition only counts the ones that came back; a resting bid is filled by all of them. So this is the number that matters.
- **Bid marked 2 minutes later:** a bid resting at the trigger level (15c, or 30%, under the price before), valued at the price two minutes later. In cents a contract, before fees and before any question of fills.

**3. National-team soccer stands out.** Half or more of its deep drops come back, against about 30% almost everywhere else.

| Group | Series | Came back (median) | Bid marked 2 min later (median) |
|---|---|---|---|
| Markets lasting weeks (national-team soccer, college football games) | 3 | 47% | +4.3c |
| Markets lasting days | 17 | 32% | +2.4c |
| Same-day markets | 23 | 31% | +1.0c |
| Hourly markets | 8 | 31% | +0.7c |
| 15-minute markets | 28 | 30% | +1.3c |

**4. In game-winner markets the drops are single big sweeps.** They snap back inside the same minute 65% to 86% of the time, in a minute that trades 15 to 1,800 times the market's usual minute. They are not at the open (0% to 1%). In 15-minute markets the "dump" minute is an ordinary minute (1.0 times the usual volume) and snaps back inside the minute 27% to 46% of the time. The S&P 500 is the highest of that family at 55%.

**5. New markets do not dump more.** See the last section.

## The one table

Ranked by "came back". Top 40 of 79 series with at least 25 deep drops; the rest are in the research folder. A star marks a series sampled by random times. "Events per 100 markets", "median depth" and "contracts in that minute" are the pre-registered columns.

| Rank | Series | Name | Market life | Day volume | Markets | Deep drops seen | Came back | Bid marked 2 min later | Events per 100 markets | Median depth | Snapped inside the minute | Contracts in that minute |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | KXCONCACAFNLGAME | CONCACAF Nations League Game | 187.82h | 5.9M | 50 | 516 | 59% | +5.6c | 454 | 12c | 77% | 3252 |
| 2 | KXNFLTD | Pro Football Touchdowns | 96.11h | 9.5M | 50 | 121 | 56% | +5.7c | 104 | 11c | 65% | 1155 |
| 3 | KXAFCONGAME | AFCON Game Winner | 353.9h | 6.4M | 50 | 315 | 51% | +4.3c | 242 | 15c | 69% | 1651 |
| 4 | KXINTLFRIENDLYGAME | International Friendly Game | 182.11h | 9.6M | 50 | 315 | 49% | +4.0c | 228 | 12c | 75% | 3032 |
| 5 | KXUEFANLGAME | UEFA Nations League Game | 357.58h | 16.3M | 50 | 261 | 47% | +4.7c | 202 | 17c | 86% | 5179 |
| 6 | KXUEFANLTOTAL | Point Total | 169.58h | 3.7M | 50 | 240 | 44% | +5.7c | 200 | 18c | 62% | 819 |
| 7 | KXNFLFIRSTTD | Pro Football First Touchdown | 94.14h | 4.6M | 50 | 40 | 42% | +4.8c | 22 | 15c | 36% | 509 |
| 8 | KXATPMATCH | ATP Tennis Match | 20.29h | 7.0M | 50 | 317 | 39% | +3.2c | 200 | 12c | 67% | 16210 |
| 9 | KXNBAPTS* | NBA Player Points | 19.64h | 5.7M | 50 | 189 | 39% | +4.0c | 126 | 15c | 46% | 311 |
| 10 | KXNBAGAME | NBA Game | 123.81h | 48.2M | 50 | 318 | 36% | +3.4c | 140 | 12c | 73% | 65163 |
| 11 | KXNFLRSHYDS | Pro Football Rushing Yards | 91.12h | 4.0M | 50 | 180 | 36% | +4.9c | 122 | 17c | 41% | 138 |
| 12 | KXTEMPCHIHS* | Hourly Directional Chicago M | 1.0h | 0.1M | 50 | 86 | 36% | +2.3c | 92 | 16c | 22% | 28 |
| 13 | KXNCAAFGAME | College Football Game | 338.72h | 32.4M | 50 | 351 | 35% | +2.7c | 166 | 12c | 65% | 4597 |
| 14 | KXCS2GAME | Counter-Strike 2 Game | 24.08h | 4.6M | 50 | 261 | 35% | +2.5c | 124 | 12c | 52% | 1372 |
| 15 | KXINX15M | S&P 500 15-minute | 0.25h | 0.9M | 50 | 326 | 35% | +3.1c | 274 | 18c | 55% | 2049 |
| 16 | KXNCAAMBTOTAL* | Men's College Basketball Tot | 24.01h | 10.0M | 15 | 113 | 35% | +4.0c | 233 | 15c | 69% | 2702 |
| 17 | KXUSDCAD15M | 15-minute USDCAD | 0.25h | 0.8M | 50 | 262 | 34% | +2.5c | 206 | 17c | 35% | 136 |
| 18 | KXWTAMATCH | WTA Tennis Match | 24.71h | 22.9M | 50 | 230 | 33% | +1.5c | 104 | 12c | 52% | 14594 |
| 19 | KXNBASPREAD | NBA Spread | 25.04h | 8.0M | 50 | 198 | 33% | +3.1c | 102 | 16c | 49% | 1801 |
| 20 | KXSILVER15M | Silver 15-minute | 0.25h | 7.9M | 50 | 269 | 33% | +2.3c | 194 | 17c | 44% | 2304 |
| 21 | KXODIMATCH | Men's ODI Cricket Match | 56.51h | 7.4M | 50 | 319 | 33% | +1.3c | 126 | 7c | 68% | 2408 |
| 22 | KXITFDOUBLES | ITF Doubles Match | 18.8h | 1.7M | 50 | 242 | 33% | +1.7c | 148 | 15c | 42% | 788 |
| 23 | KXSOL15M | SOL 15 min | 0.25h | 11.9M | 50 | 342 | 32% | +3.4c | 270 | 18c | 41% | 3130 |
| 24 | KXITFWMATCH | ITF Women's Match | 17.93h | 18.8M | 50 | 139 | 32% | -0.6c | 42 | 7c | 48% | 2376 |
| 25 | KXZEC15M | Zcash 15min | 0.25h | 5.4M | 50 | 297 | 32% | +1.7c | 254 | 17c | 38% | 1200 |
| 26 | KXTEMPMIAH* | Hourly Directional Miami Tem | 1.0h | 0.3M | 50 | 99 | 32% | -0.1c | 66 | 11c | 39% | 61 |
| 27 | KXNCAAWBGAME | Women's College Basketball G | 97.81h | 13.0M | 50 | 189 | 32% | +1.4c | 80 | 8c | 57% | 505 |
| 28 | KXNFLGAME | NFL Game | 239.22h | 63.4M | 50 | 372 | 32% | +2.3c | 144 | 12c | 85% | 102272 |
| 29 | KXATPCHALLENGERDOUBLES | ATP Challenger Doubles Match | 14.74h | 1.4M | 50 | 225 | 32% | +1.8c | 114 | 15c | 30% | 460 |
| 30 | KXNFLSPREAD | Pro Football Spread | 170.27h | 13.7M | 50 | 279 | 32% | +2.0c | 124 | 16c | 73% | 2561 |
| 31 | KX10YRRATE15M | 10-year Treasury yield 15-mi | 0.25h | 0.3M | 50 | 179 | 32% | +1.2c | 132 | 17c | 30% | 48 |
| 32 | KXTEMPLAXHS* | Hourly Directional Coastal L | 1.0h | 0.1M | 50 | 44 | 32% | +2.5c | 34 | 15c | 53% | 51 |
| 33 | KXGOLD15M | Gold 15-minute | 0.25h | 49.3M | 50 | 320 | 32% | +1.9c | 252 | 17c | 40% | 17278 |
| 34 | KXCOPPER15M | Copper 15-minute | 0.25h | 2.0M | 50 | 286 | 31% | +2.0c | 202 | 17c | 42% | 924 |
| 35 | KXATPCHALLENGERMATCH | Challenger ATP  | 14.46h | 74.2M | 50 | 270 | 31% | +1.0c | 116 | 10c | 69% | 9073 |
| 36 | KXWTACHALLENGERMATCH | Challenger WTA | 13.67h | 1.9M | 50 | 209 | 31% | +1.0c | 96 | 10c | 50% | 10107 |
| 37 | KXGBPUSD15M | 15-minute GBPUSD | 0.25h | 0.7M | 50 | 280 | 31% | +1.6c | 214 | 17c | 37% | 251 |
| 38 | KXTEMPNYCHS* | Hourly Directional NYC Tempe | 1.0h | 0.2M | 50 | 87 | 31% | +3.5c | 60 | 16c | 33% | 78 |
| 39 | KXNHLSPREAD | NHL Spread | 3.19h | 1.4M | 50 | 129 | 31% | +1.8c | 74 | 15c | 51% | 1047 |
| 40 | KXWTI15M | WTI 15-minute | 0.25h | 10.8M | 50 | 295 | 31% | +2.0c | 222 | 17c | 46% | 5461 |

## A suggested pick for stage 2

Olu picks. This is what the table points to, 14 series:

| Why | Series |
|---|---|
| National-team soccer, the clearest signal | CONCACAF Nations League game, AFCON game, international friendly game, UEFA Nations League game, UEFA Nations League total |
| Pro football props | Touchdowns, first touchdown, rushing yards |
| Tennis and basketball | ATP match, NBA player points, NBA game |
| 15-minute, as the known case and its nearest neighbours | S&P 500, Solana, XRP |

Two things to decide with the pick:

- **Club soccer was not screened.** Nov 13 fell in an international break, so the club leagues had almost no volume that day and missed the shortlist. If national-team soccer is picked, the big club game series should be added to stage 2. That costs a few listing requests.
- **Stage 2 size.** Trade prints for about 50 to 100 markets a series, 14 to 18 series: roughly 2,000 to 4,000 requests, more for the busiest markets. The fill-simulator cache already holds some.

## What stage 2 has to settle

- **Can the bid be there?** A sweep fills better bids first. Prints show how much traded through each level.
- **Is it a goal or a sweep?** In soccer a real goal moves the price for good, and a disallowed goal moves it back. The earlier dip study flagged NO-side soccer dips as single prints or video-review reversals. A resting bid is filled by both kinds.
- **The cost of being wrong.** Half the deep drops do not come back. The +4c to +6c mark is an average over both, before fees.
- **Found on older dates, confirmed once on later ones**, with the fill simulator's honest rule and an order delay, as for rule C.

## New markets: first week against latest week

Every 15-minute series, 40 random markets from its first 7 days and 40 from its latest 7. Events per 100 markets, depth, and the share at the open.

- **No series dumped more when it was new.** 20 of 27 show more events now than in their first week. BTC went from 78 to 270 per 100 markets, ETH from 15 to 282: their first-week markets barely traded.
- The S&P 500, the newest, is the same in both (212 and 200).
- So "new market" is not a signal a candle screen can see. What makes the S&P different shows only in the prints.

| Series | First market | First 7 days: per 100 markets | depth | at the open | Latest 7 days: per 100 markets | depth | at the open |
|---|---|---|---|---|---|---|---|
| KXXRP15M | 2026-02-11 | 300 (40) | 17c | 19% | 195 (40) | 18c | 37% |
| KXNATGAS15M | 2026-08-27 | 292 (40) | 17c | 31% | 255 (40) | 16c | 31% |
| KXCOPPER15M | 2026-08-27 | 255 (40) | 17c | 27% | 248 (40) | 18c | 32% |
| KXINX15M | 2026-11-05 | 212 (40) | 18c | 41% | 200 (40) | 18c | 38% |
| KXGOLD15M | 2026-07-31 | 210 (40) | 18c | 42% | 230 (40) | 18c | 43% |
| KXBRENT15M | 2026-10-21 | 210 (40) | 16c | 26% | 202 (40) | 17c | 25% |
| KXZEC15M | 2026-06-30 | 198 (40) | 17c | 41% | 282 (40) | 17c | 36% |
| KXAUDUSD15M | 2026-10-07 | 178 (40) | 18c | 37% | 185 (40) | 17c | 28% |
| KXDOGE15M | 2026-03-18 | 175 (40) | 18c | 31% | 312 (40) | 17c | 32% |
| KXHYPE15M | 2026-03-18 | 172 (40) | 18c | 26% | 233 (40) | 17c | 37% |
| KXPALLADIUM15M | 2026-09-17 | 172 (40) | 17c | 20% | 228 (40) | 16c | 29% |
| KXBNB15M | 2026-03-18 | 165 (40) | 17c | 17% | 228 (40) | 18c | 44% |
| KXUSDCAD15M | 2026-10-07 | 160 (40) | 18c | 38% | 230 (40) | 18c | 24% |
| KXSILVER15M | 2026-07-31 | 152 (40) | 20c | 49% | 188 (40) | 17c | 45% |
| KXNEAR15M | 2026-06-30 | 152 (40) | 21c | 43% | 233 (40) | 18c | 38% |
| KXPLATINUM15M | 2026-09-17 | 148 (40) | 16c | 20% | 165 (40) | 17c | 30% |
| KXUSDJPY15M | 2026-09-23 | 132 (40) | 16c | 32% | 188 (40) | 17c | 32% |
| KXWTI15M | 2026-07-31 | 130 (40) | 17c | 44% | 242 (40) | 18c | 38% |
| KXEURUSD15M | 2026-09-23 | 125 (40) | 17c | 28% | 245 (40) | 17c | 32% |
| KXGBPUSD15M | 2026-09-23 | 92 (40) | 15c | 22% | 168 (40) | 16c | 33% |
| KXBTC15M | 2025-12-10 | 78 (40) | 16c | 39% | 270 (40) | 18c | 34% |
| KXSOL15M | 2026-01-09 | 68 (40) | 18c | 63% | 217 (40) | 17c | 38% |
| KX2YRRATE15M | 2026-10-19 | 60 (40) | 18c | 38% | 148 (40) | 17c | 20% |
| KX10YRRATE15M | 2026-10-19 | 55 (40) | 18c | 45% | 150 (40) | 18c | 30% |
| KX30YRRATE15M | 2026-10-19 | 32 (40) | 17c | 23% | 202 (40) | 19c | 35% |
| KX5YRRATE15M | 2026-10-19 | 25 (40) | 18c | 30% | 115 (40) | 15c | 28% |
| KXETH15M | 2025-12-11 | 15 (40) | 26c | 67% | 282 (40) | 17c | 37% |

## Limits

- **Candles, not prints.** "Came back" uses the traded price two minutes later, not a bid.
- **The two deciding measures were added after the first table was read.** They describe; they do not confirm anything. Stage 2 is the test.
- **One sample, September 15 to November 13.** National-team soccer is two international windows.
- **Dense series were sampled by time** and some returned fewer than 50 markets (the hourly crypto ladders, college-basketball lines).
- **Markets longer than 72 hours** were screened on their last 72 hours.

## Files

Research folder: `~/edge-research/flashdump_2026-11-13/`. `PREREGISTERED.md` (definitions and the notes on what was added and when), `stage1.py` (sample and screen), `stage1_table.py`, `stage1_snap.py`, `stage1_back.py`, `stage1_onetable.md` (all 79 rows), `stage1_table.md` (the pre-registered ranking, 92 series), `stage1_newmarket.md`.
