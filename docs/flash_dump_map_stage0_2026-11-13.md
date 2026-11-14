# Flash dump map, stage 0: where to look (Nov 13 2026)

Research only. No lane, page or Production change. This is stage 0 of a four-stage funnel; each stage stops for Olu's go.

The question: where on Kalshi do trades print far below the surrounding price for a moment and snap back, so that a resting bid catches the dump and resells on the recovery? The one known case is the S&P 500 15-minute market in the seconds after each window opens.

Stage 0 looks at no prices. It maps the exchange and picks about 100 series to screen.

## The map

577 requests: one listing of every series, one pass over every open market, one pass over every market that closed in the last 24 hours, and launch dates for the shortlist.

- **16,441 series** exist; 4,956 had a market open or closed in the last day.
- **About 1.33 billion contracts traded in the last day** (Friday Nov 13). 305 series traded over 100,000; 99 over a million; 20 over ten million.

| Market life | Series | Day volume | Markets closed in 24h |
|---|---|---|---|
| 15 minutes | 28 | 587M | 2,747 |
| Up to an hour or so | 24 | 55M | 63,293 |
| Same day | 235 | 256M | 26,674 |
| Days | 630 | 323M | 8,446 |
| Longer | 4,039 | 109M | 930 |

| Category | Series active | Day volume |
|---|---|---|
| Sports | 1,305 | 643M |
| Crypto | 98 | 560M |
| Commodities | 63 | 77M |
| Elections | 659 | 17M |
| Financials | 645 | 12M |
| Climate and Weather | 207 | 6M |
| Everything else | about 2,000 | 14M |

- BTC 15-minute alone is 427M contracts a day, a third of the exchange.
- **Where a dump is most likely to be catchable** is where markets open often and books start empty: the 15-minute and hourly families (66,000 market opens a day between them) and same-day sports.

## New markets

18 of the 94 shortlisted series first settled a market after Sep 14. The S&P 500 15-minute is the newest by far.

| Series | First market closed | Day volume |
|---|---|---|
| S&P 500 15-minute | Nov 6 | 0.88M |
| Brent 15-minute | Oct 21 | 0.90M |
| Treasury yields 15-minute (2, 5, 10, 30-year) | Oct 19 | 0.16M to 0.26M each |
| USD/CAD, AUD/USD 15-minute | Oct 8 | 0.79M, 0.64M |
| eSoccer, eBasketball games | Oct 8 | 1.86M, 1.30M |
| EUR/USD, USD/JPY, GBP/USD 15-minute | Sep 24 | 0.72M to 0.99M |
| Palladium, Platinum 15-minute | Sep 18 | 1.11M, 1.06M |

Stage 1 asks whether each 15-minute series showed S&P-style opening dumps in its own first week.

## The shortlist: 94 series

All 28 fifteen-minute series, the 14 hourly ones with real volume, the top 26 same-day series, the top 18 whose markets last days, and the top 8 long ones. "Spread" is the median on markets that traded in the last day, where one was open; blank means none was.

**15-minute markets**

| Series | Name | Market life | Closed in 24h | Day volume | Spread | Launch |
|---|---|---|---|---|---|---|
| KXBTC15M | BTC 15 min | 0.25h | 96 | 426.98M | 0.1c | before Sep 14 2026 |
| KXGOLD15M | Gold 15-minute | 0.25h | 87 | 49.28M |  | before Sep 14 2026 |
| KXETH15M | ETH 15 min | 0.25h | 96 | 24.01M |  | before Sep 14 2026 |
| KXXRP15M | XRP 15 min | 0.25h | 96 | 17.15M | 0.6c | before Sep 14 2026 |
| KXSOL15M | SOL 15 min | 0.25h | 96 | 11.88M |  | before Sep 14 2026 |
| KXWTI15M | WTI 15-minute | 0.25h | 95 | 10.84M | 32.0c | before Sep 14 2026 |
| KXSILVER15M | Silver 15-minute | 0.25h | 87 | 7.92M |  | before Sep 14 2026 |
| KXDOGE15M | DOGE 15 min | 0.25h | 96 | 6.97M |  | before Sep 14 2026 |
| KXZEC15M | Zcash 15min | 0.25h | 96 | 5.43M | 0.8c | before Sep 14 2026 |
| KXHYPE15M | HYPE 15 min | 0.25h | 96 | 5.27M | 10.0c | before Sep 14 2026 |
| KXBNB15M | BNB 15 min | 0.25h | 96 | 3.90M |  | before Sep 14 2026 |
| KXNEAR15M | NEAR 15m | 0.25h | 96 | 3.53M |  | before Sep 14 2026 |
| KXNATGAS15M | Natural Gas 15-minute | 0.25h | 95 | 2.77M | 2.0c | before Sep 14 2026 |
| KXCOPPER15M | Copper 15-minute | 0.25h | 87 | 1.97M |  | before Sep 14 2026 |
| KXPALLADIUM15M | Palladium 15-minute | 0.25h | 87 | 1.11M |  | 2026-09-18 |
| KXPLATINUM15M | Platinum 15-minute | 0.25h | 87 | 1.06M |  | 2026-09-18 |
| KXEURUSD15M | 15-minute EURUSD | 0.25h | 87 | 0.99M |  | 2026-09-24 |
| KXUSDJPY15M | Fifteen-min USDJPY | 0.25h | 87 | 0.94M |  | 2026-09-24 |
| KXBRENT15M | Brent 15-minute | 0.25h | 95 | 0.90M | 2.0c | 2026-10-21 |
| KXINX15M | S&P 500 15-minute | 0.25h | 25 | 0.88M |  | 2026-11-06 |
| KXUSDCAD15M | 15-minute USDCAD | 0.25h | 87 | 0.79M |  | 2026-10-08 |
| KXGBPUSD15M | 15-minute GBPUSD | 0.25h | 87 | 0.72M |  | 2026-09-24 |
| KXAUDUSD15M | 15-minute AUDUSD | 0.25h | 87 | 0.64M |  | 2026-10-08 |
| KX10YRRATE15M | 10-year Treasury yield 15-minute | 0.25h | 57 | 0.26M |  | 2026-10-19 |
| KX2YRRATE15M | 2-year Treasury yield 15-minute | 0.25h | 57 | 0.24M |  | 2026-10-19 |
| KX30YRRATE15M | 30-year Treasury yield 15-minute | 0.25h | 57 | 0.23M |  | 2026-10-19 |
| KX5YRRATE15M | 5-year Treasury yield 15-minute | 0.25h | 57 | 0.16M |  | 2026-10-19 |
| KXCRYPTOLEAD15M | Coin Race 15 minutes | 0.25h | 475 | 0.12M | 10.5c | before Sep 14 2026 |

**Hourly markets**

| Series | Name | Market life | Closed in 24h | Day volume | Spread | Launch |
|---|---|---|---|---|---|---|
| KXBTCD | Bitcoin price Above/below | 1.0h | 4374 | 48.69M | 1.0c | before Sep 14 2026 |
| KXBTC | Bitcoin range | 1.0h | 4374 | 1.71M | 2.0c | before Sep 14 2026 |
| KXFAAGROUNDSTOPLIFT | When will the FAA Lift the Ground  | 1.17h | 5 | 1.69M | 3.0c | 2026-11-14 |
| KXETHD | Ethereum price Above/below | 1.0h | 6950 | 1.45M | 1.0c | before Sep 14 2026 |
| KXSOLD | SOL Directional | 1.0h | 6950 | 0.31M | 4.5c | before Sep 14 2026 |
| KXTEMPMIAH | Hourly Directional Miami Temperatu | 1.0h | 240 | 0.29M | 3.0c | before Sep 14 2026 |
| KXTEMPNYCHS | Hourly Directional NYC Temperature | 1.0h | 240 | 0.24M | 3.0c | before Sep 14 2026 |
| KXETH | Ethereum range | 1.0h | 6950 | 0.18M | 4.0c | before Sep 14 2026 |
| KXXRPD | XRP Price above/below | 1.0h | 1775 | 0.13M | 5.5c | before Sep 14 2026 |
| KXTEMPLAXHS | Hourly Directional Coastal LA Temp | 1.0h | 240 | 0.11M | 4.0c | before Sep 14 2026 |
| KXTEMPCHIHS | Hourly Directional Chicago Metro T | 1.0h | 230 | 0.11M | 2.0c | before Sep 14 2026 |
| KXHYPED | Hype Directional | 1.0h | 6950 | 0.03M | 4.0c | before Sep 14 2026 |
| KXBNBD | BNB Directional | 1.0h | 1785 | 0.03M | 5.0c | before Sep 14 2026 |
| KXDOGED | Dogecoin price Above/below | 1.0h | 1165 | 0.03M | 13.0c | before Sep 14 2026 |

**Same-day markets, by volume**

| Series | Name | Market life | Closed in 24h | Day volume | Spread | Launch |
|---|---|---|---|---|---|---|
| KXATPCHALLENGERMATCH | Challenger ATP  | 14.46h | 56 | 74.17M | 1.0c | before Sep 14 2026 |
| KXITFMATCH | ITF Men's Match | 18.37h | 150 | 41.56M | 3.0c | before Sep 14 2026 |
| KXWTAMATCH | WTA Tennis Match | 24.71h | 8 | 22.85M | 1.0c | before Sep 14 2026 |
| KXITFWMATCH | ITF Women's Match | 17.93h | 100 | 18.76M | 2.0c | before Sep 14 2026 |
| KXNCAAMBTOTAL | Men's College Basketball Total Poi | 24.01h | 416 | 9.95M | 2.0c | before Sep 14 2026 |
| KXNCAAMBSPREAD | Men's College Basketball Spread | 24.84h | 325 | 9.10M | 1.0c | before Sep 14 2026 |
| KXNBASPREAD | NBA Spread | 25.04h | 140 | 8.04M | 2.0c | before Sep 14 2026 |
| KXATPMATCH | ATP Tennis Match | 20.29h | 4 | 6.96M | 1.0c | before Sep 14 2026 |
| KXNBATOTAL | NBA Total | 25.04h | 129 | 6.07M | 2.0c | before Sep 14 2026 |
| KXNBAPTS | NBA Player Points | 19.64h | 229 | 5.71M | 1.0c | before Sep 14 2026 |
| KXCS2GAME | Counter-Strike 2 Game | 24.08h | 106 | 4.58M | 3.0c | before Sep 14 2026 |
| KXNCAAWBTOTAL | Women's College Basketball Total P | 25.82h | 607 | 2.63M | 10.5c | before Sep 14 2026 |
| KXWTASETWINNER | WTA Set Winner | 22.95h | 14 | 2.43M |  | before Sep 14 2026 |
| KXNBAREB | NBA Player Rebounds | 20.28h | 255 | 2.11M | 1.0c | before Sep 14 2026 |
| KXNBA3PT | NBA Player Threes | 20.17h | 261 | 1.92M | 2.0c | before Sep 14 2026 |
| KXWTACHALLENGERMATCH | Challenger WTA | 13.67h | 4 | 1.91M |  | before Sep 14 2026 |
| KXESOCCERGAME | eSoccer Game | 2.89h | 1380 | 1.86M | 3.5c | 2026-10-08 |
| KXNBAAST | NBA Player Assists | 19.91h | 190 | 1.75M | 1.0c | before Sep 14 2026 |
| KXITFDOUBLES | ITF Doubles Match | 18.8h | 74 | 1.69M | 43.0c | before Sep 14 2026 |
| KXITFWDOUBLES | ITF Women's Doubles Match | 18.5h | 56 | 1.48M | 21.0c | before Sep 14 2026 |
| KXCS2MAP | Counter-Strike 2 Map Winner  | 24.05h | 156 | 1.48M | 2.0c | before Sep 14 2026 |
| KXATPSETWINNER | ATP Set Winner | 19.59h | 8 | 1.47M | 2.0c | before Sep 14 2026 |
| KXNHLSPREAD | NHL Spread | 3.19h | 82 | 1.39M | 1.0c | before Sep 14 2026 |
| KXATPCHALLENGERDOUBLES | ATP Challenger Doubles Match | 14.74h | 32 | 1.36M | 21.0c | before Sep 14 2026 |
| KXEBASKETBALLGAME | eBasketball Game | 3.04h | 170 | 1.30M |  | 2026-10-08 |
| KXINXU | S&P 500 above/below | 21.0h | 480 | 1.30M | 51.0c | before Sep 14 2026 |

**Markets lasting days, by volume**

| Series | Name | Market life | Closed in 24h | Day volume | Spread | Launch |
|---|---|---|---|---|---|---|
| KXNFLGAME | NFL Game | 239.22h | 2 | 63.38M | 1.0c | before Sep 14 2026 |
| KXNBAGAME | NBA Game | 123.81h | 8 | 48.17M | 1.0c | before Sep 14 2026 |
| KXNCAAMBGAME | Men's College Basketball Game | 95.81h | 54 | 24.10M | 1.0c | before Sep 14 2026 |
| KXNCAAFSPREAD | College Football Spread | 119.81h | 65 | 14.77M | 1.0c | before Sep 14 2026 |
| KXNFLSPREAD | Pro Football Spread | 170.27h | 24 | 13.73M | 1.0c | before Sep 14 2026 |
| KXNHLGAME | NHL Game | 168.51h | 20 | 13.32M | 2.0c | before Sep 14 2026 |
| KXNCAAWBGAME | Women's College Basketball Game | 97.81h | 94 | 12.98M | 4.0c | before Sep 14 2026 |
| KXINTLFRIENDLYGAME | International Friendly Game | 182.11h | 18 | 9.58M | 1.0c | before Sep 14 2026 |
| KXNFLTD | Pro Football Touchdowns | 96.11h | 49 | 9.48M | 1.0c | before Sep 14 2026 |
| KXODIMATCH | Men's ODI Cricket Match | 56.51h | 8 | 7.38M | 4.0c | before Sep 14 2026 |
| KXNFLTOTAL | Pro Football Total Points | 170.18h | 21 | 7.13M | 1.0c | before Sep 14 2026 |
| KXPGATOUR | PGA Tour | 115.48h | 2 | 6.59M | 0.2c | before Sep 14 2026 |
| KXNCAAFTOTAL | College Football Total Points | 119.81h | 49 | 6.38M | 1.0c | before Sep 14 2026 |
| KXCONCACAFNLGAME | CONCACAF Nations League Game | 187.82h | 15 | 5.87M | 2.0c | 2026-09-24 |
| KXNFLFIRSTTD | Pro Football First Touchdown | 94.14h | 27 | 4.59M | 1.0c | before Sep 14 2026 |
| KXNFLRSHYDS | Pro Football Rushing Yards | 91.12h | 67 | 3.97M | 3.0c | before Sep 14 2026 |
| KXUEFANLTOTAL | Point Total | 169.58h | 70 | 3.66M | 2.0c | 2026-09-24 |
| KXNFLRECYDS | Pro Football Receiving Yards | 96.22h | 150 | 3.59M | 3.0c | before Sep 14 2026 |

**Long markets, by volume**

| Series | Name | Market life | Closed in 24h | Day volume | Spread | Launch |
|---|---|---|---|---|---|---|
| KXNCAAFGAME | College Football Game | 338.72h | 4 | 32.41M | 1.0c | before Sep 14 2026 |
| KXUEFANLGAME | UEFA Nations League Game | 357.58h | 30 | 16.33M | 1.0c | before Sep 14 2026 |
| KXAFCONGAME | AFCON Game Winner | 353.9h | 36 | 6.42M | 1.0c | before Sep 14 2026 |
| KXMLBALMVP | Pro Baseball American League MVP | 6801.56h | 49 | 5.60M |  | before Sep 14 2026 |
| KXMLBNLMVP | Pro Baseball National League MVP | 6802.28h | 53 | 4.68M |  | before Sep 14 2026 |
| SENATEAK | Alaska Senate race | 31692.5h | 0 | 3.61M | 2.6c | unknown |
| KXSENATEDEMLEAD | Who will win the next Senate Democ | 27168.0h | 0 | 2.32M | 0.3c | unknown |
| KXFEDDECISION | Fed meeting | 15255.98h | 0 | 2.23M | 2.0c | before Sep 14 2026 |

## Stage 1, as it will be run (written down before any candle is read)

- **Sample:** 50 markets a series, drawn at random from those that closed between Sep 15 and Nov 13 with any volume. One one-minute candle request each. About 4,900 requests in all, through one throttled puller with a disk cache; nothing is fetched twice and no second pull runs beside it.
- **A dump:** a minute whose trade low is under both the price before it and the price after it by at least 15c, or by at least 30% of the lower of the two (and by 5c in any case), where the price after is back within 5c of the price before. "Before" is the last traded close in the 5 minutes before; "after" the first traded close in the 2 minutes after.
- **A spike** is the mirror: the same on the NO side.
- **An opening dump** is one in a market's first two traded minutes, measured against the price after only.
- **Per series:** dumps and spikes per 100 markets and per 10,000 traded minutes, depth, share at the open, minutes since the open, contracts traded in that minute, spread, hour of day, and the series' age.
- **New-market check:** every 15-minute series, 40 random markets from its first 7 days against 40 from its latest 7.
- **Output:** one table, rate by depth by volume. No strategy is tested in stage 1.
- **Limit, stated now:** a one-minute candle shows that a low printed, not how many contracts printed there. Only stage 2 (trade prints, the fill simulator, an order delay) can say whether a dump could be caught.

## A correction to the Challenger study

`challenger_underdog_study_2026-11-13.md` says Kalshi lists no ITF matches. That is wrong. The ITF series exist and are large (men's about 42M contracts a day, women's about 19M). My listing request for them failed at its paging limit and I read the failure as "none". They were not part of that study. Its results for ATP and WTA Challengers stand.

## Files

Research folder: `~/edge-research/flashdump_2026-11-13/`. `PREREGISTERED.md` (plan and stage 1 definitions), `kpull.py` (the one cached, throttled puller), `stage0a.py` to `stage0e.py`, `map.json` (one row a series), `shortlist.json`.
