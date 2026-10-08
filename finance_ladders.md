# Kalshi finance ladders — discovery note (2026-10-08)

> **Status: shelved (2026-10-08).** No Kalshi daily or weekly FX or Treasury ladder had a
> 70–80¢ rung within the 3¢ spread floor in five trading days; spreads on those rungs ran
> 10–71¢. Nothing was registered, scanned or published, and no Finance tab exists.
> **Worth revisiting if** in-window spreads sit at or under 3¢ on several series for a
> week. This note is the record; the survey script it describes was removed with the
> shelving (it is in the history of #100, `finance_discover.py`).

Read-only survey for a Finance favourite-band lane, the same shape as the Crypto lane
(`crypto_fav_band`). Nothing here registers a rule or logs a quote.

**How this was read.** Live, from Kalshi's public API (`api.elections.kalshi.com`, no key,
no orders), by `python3 finance_discover.py --days 5 --only 'AD$|AW$|^KXUST(2|5|7|10|30)A$|^KXNZDUSD$'`
at 2:28 AM ET on Thursday Oct 8. For each series: `/series/{ticker}` for the frequency and
settlement source; `/markets?series_ticker=…` (open and settled) for the ladder shape, the
close and expiration times, and the settlement cadence; hourly candles for every rung of
the last five settled ladders, read inside what would be the entry window (3.5h–2h before
the close), for the spread on rungs asking 70–80¢ and the volume traded on them; and the
live order book for the ask size on in-band rungs of the ladder open at read time. Kalshi
keeps no history of resting size, so size is a live reading only (see the last section).

**Floor tested:** two-sided quote, spread ≤3¢, ask size ≥25, on a Yes rung asking 70–80¢,
inside the window.

## First finding: what the Finance tab's "Daily" filter shows is mostly the WEEKLY series

The 12 FX "Above X … 5pm ET tomorrow" cards and the `kxust2a`/`kxust7a` Treasury cards
seen on the Kalshi UI are the **weekly** series (`KX…AW`, "GBPUSD Weekly"; `KXUST…A`,
"UST 10 Year Weekly"). They settle **once a week, on Friday**, and showed under "Daily"
on Thursday night only because Friday was tomorrow. Kalshi also runs true **daily**
series for the same instruments under the `…AD` tickers, which settle **Monday to
Thursday** (Friday's slot is the weekly contract). So:

| Group | Daily series (Mon–Thu) | Weekly series (Fri) |
|---|---|---|
| FX "above" ladders | `KXGBPUSDAD`, `KXUSDJPYAD`, `KXUSDCHFAD`, `KXUSDCADAD`, `KXUSDNOKAD`, `KXUSDBRLAD`, `KXNZDUSDAD`, `KXAUDUSDAD`, `KXUSDINRAD` (9). `KXEURUSDAD` exists but has never settled; there is no USDMXN or USDSEK daily series. | `KXEURUSDAW`, `KXGBPUSDAW`, `KXUSDJPYAW`, `KXUSDCHFAW`, `KXUSDCADAW`, `KXUSDMXNAW`, `KXUSDNOKAW`, `KXUSDSEKAW`, `KXUSDBRLAW`, `KXAUDUSDAW`, `KXUSDINRAW`, `KXNZDUSD` (12) |
| Treasury yield ladders | `KXUST2AD`, `KXUST5AD`, `KXUST7AD`, `KXUST10AD`, `KXUST30AD` (5) | `KXUST2A`, `KXUST5A`, `KXUST7A`, `KXUST10A`, `KXUST30A` (5) |

## Close time and settlement source (confirmed from the API)

| Series | Frequency field | Settles | Close = expiration (ET) | Settlement source | Rungs | Shape |
|---|---|---|---|---|---|---|
| FX `…AD` (9) | `daily` | Mon–Thu, 18 of the last 30 days | **5:00 PM ET** (21:00Z) | Pyth price feed for the pair ("Pyth - GBPUSD" …) | 20 | `greater` ("above X"), nested |
| FX `…AW` (12) | `weekly` | Friday only, 5 of the last 30 days | **5:00 PM ET Friday** (21:00Z) | Pyth price feed for the pair | 20 (USDBRL, USDNOK, USDSEK 40; USDMXN 50) | `greater`, nested |
| Treasury `…AD` (5) | `one_off` (Kalshi's field; they list daily) | Mon–Thu, 18 of the last 30 days | **3:30 PM ET** (19:30Z) | U.S. Department of the Treasury daily par yield curve | 15 | `greater` ("X% or above"), nested |
| Treasury `…A` (5) | `daily` (Kalshi's field; they list weekly) | Friday only | **3:30 PM ET Friday** (19:30Z) | U.S. Department of the Treasury | 15 | `greater`, nested |

The "2:30 PM" on the Treasury cards is 3:30 PM ET shown in Central time: both `close_time`
and `expected_expiration_time` are 19:30Z. The 5:00 PM ET FX close is the same clock as
the Crypto lane's close, so the crypto window (12:30–2:00 PM CT) would serve FX; the
Treasury window is 12:00–1:30 PM ET (11:00 AM–12:30 PM CT).

Note the daily FX ladder is **not listed overnight**: at 2:28 AM ET Thursday none of the nine
had an open ladder although all nine settled at 5 PM Wednesday. The UI lists them during the
US morning, which is after the Crypto scanner's first read but well before the window.

## Liquidity in the window, last five settled ladders (Sep 30 – Oct 7 daily; Sep 4 – Oct 2 weekly)

"In-band rung-hours" is the number of (rung, hour) candles inside the window whose Yes ask
was 70–80¢; "tight" is how many of those had a spread ≤3¢. Spread is on those candles.

| Series | Days with a tight in-band rung | In-band rung-hours (5 days) | Spread on in-band rungs, median / best | Volume on in-band rungs in the window | Ladder volume per day | Verdict |
|---|---|---|---|---|---|---|
| **FX daily** `KXGBPUSDAD` | 0 of 5 | 0 | — | 0 | 0–1,215 (three of five days 0) | almost never |
| `KXUSDJPYAD` | 0 of 5 | 0 | — | 0 | 0–262 | almost never |
| `KXUSDCADAD` | 0 of 5 | 0 | — | 0 | 0–3,979 | almost never |
| `KXAUDUSDAD` | 0 of 5 | 0 | — | 0 | 0–882 | almost never |
| `KXNZDUSDAD` | 0 of 5 | 0 | — | 0 | 0–637 | almost never |
| `KXUSDCHFAD` | 0 of 5 | 0 | — | 0 | 0–245 | almost never |
| `KXUSDBRLAD`, `KXUSDNOKAD`, `KXUSDINRAD` | 0 of 5 | 0 | — | 0 | 0 on every day | almost never (no trade at all) |
| **Treasury daily** `KXUST5AD` | 0 of 5 | 5 | 14¢ / 10¢ | 2–407 per day it appeared | 7,289–12,971 | almost never |
| `KXUST7AD` | 0 of 5 | 6 | 17.5¢ / 12¢ | 17–490 | 3,761–20,316 | almost never |
| `KXUST30AD` | 0 of 5 | 5 | 18.5¢ / 14¢ | 0–376 | 6,810–24,039 | almost never |
| `KXUST2AD` | 0 of 5 | 2 | 23¢ / 19¢ | 154–556 | 6,704–13,358 | almost never |
| `KXUST10AD` | 0 of 5 | 1 | 36¢ / 36¢ | 24 | 45,380–87,873 | almost never |
| **FX weekly** `KXEURUSDAW` | 0 of 5 | 2 | 29¢ / 23¢ | 0–9 | 8,217–90,054 | almost never |
| `KXUSDJPYAW` | 0 of 5 | 3 | 42¢ / 8¢ | 0–55 | 2,564–15,704 | almost never |
| `KXGBPUSDAW` | 0 of 5 | 5 | 46¢ / 15¢ | 0 | 2,617–7,823 | almost never |
| `KXUSDCADAW` | 0 of 5 | 4 | 53¢ / 41¢ | 0–52 | 5,894–12,312 | almost never |
| `KXUSDSEKAW` | **1 of 5** (Sep 4, one hour at 2¢) | 4 | 41¢ / 2¢ | 0 | 2,142–5,105 | marginal |
| `KXUSDCHFAW`, `KXUSDNOKAW`, `KXUSDBRLAW`, `KXAUDUSDAW`, `KXNZDUSD`, `KXUSDINRAW`, `KXUSDMXNAW` | 0 of 5 | 0–8 | 37–71¢ / 19–71¢ | 0–29 | 438–16,570 | almost never |
| **Treasury weekly** `KXUST2A`, `KXUST5A`, `KXUST7A`, `KXUST10A`, `KXUST30A` | 0 of 5 each | 1–4 | 25–70¢ / 19–58¢ | 0–629 | 4,387–28,017 | almost never |

Live book at 2:28 AM ET Thursday (outside the window, for size only): the daily Treasury
ladders carry real resting size on in-band rungs — `KXUST2AD` 4.75% ask 78¢ / bid 59¢ /
**300** contracts; the monthly `KXUST5AM` rungs show 400 — but at spreads of 11–21¢. The
weekly FX in-band rungs show sizes of 0.01–2 contracts at spreads of 11–56¢.

## What this means for the rule as specified

1. **No series passes the floor on a typical day.** Across 31 series and five settled
   ladders each, exactly one (rung, hour) in one series (`KXUSDSEKAW`, Sep 4) had an
   in-band rung with a spread ≤3¢ inside the window. The Crypto floor was set against
   books that quote 1–3¢ wide; these books quote 10–70¢ wide on the rungs the rule wants.
2. **The nearest misses are the daily Treasury 5Y, 7Y and 30Y ladders**: an in-band rung
   exists in the window on most days, with hundreds of contracts resting, but the best
   spread seen was 10¢ and the median 14–19¢. At a 10¢ spread the taker pays the whole
   favourite-longshot margin and more, so loosening the floor to let them in would change
   what the rule measures, not just how often it fires.
3. **The daily FX ladders are empty.** Zero in-band quotes in the window on every pair
   and every day, and three pairs with no trade at all in five days. They are listed, and
   nobody is quoting them.
4. **The weekly FX ladders are the traded ones** (EURUSD 25–90k contracts a week) but they
   are a different bet from the Crypto rule: one settlement a week, so 30 independent
   market-days would take 30 weeks, and the Friday 5 PM close means the window sits in
   Friday afternoon only.
5. **One factor, as expected.** All nine daily FX pairs are USD crosses and the five
   yields are one curve, so a day where several fire is one bet per group; the
   registration would say so (per instrument reported, per group judged), as the Crypto
   method does. With no series passing the floor this is moot until the floor is
   decided.

**Recommendation:** do not register the Finance lane on the Crypto floor; it would log
"no entry" nearly every day and read nothing in 30 market-days. The two defensible
alternatives are (a) register it anyway with the Crypto floor as a measured null (cheap,
honest, and the first week of logged quotes tests this note), or (b) register the daily
Treasury 5Y/7Y/30Y ladders with a wider floor stated up front (for example ≤10¢ spread,
size ≥25, which the live book suggests they can meet) and judge against backing every
in-band rung as Crypto does. Either is the owner's call, not this note's.

## Not read: size inside the window (shelved before the in-window reads)

Kalshi keeps no history of resting size, so the "ask ≥25" half of the floor is only
readable from the live book inside the window itself. The survey script's `--no-history --only 'AD$'` mode at 12:00–1:30 PM ET would read the
daily Treasury books, and at 1:30–3:00 PM ET the daily FX books (if listed); on a Friday
afternoon `--only 'AW$|^KXUST(2|5|7|10|30)A$'` would read the weekly ones. Those reads were
scheduled and then cancelled when the lane was shelved. Spread already fails the floor on the days read
above, so size cannot rescue those days; it decides only whether alternative (b) is
realistic.

## Out of scope, as asked

Range buckets (`KXEURUSD`, `KXUSDJPY` at 10 AM, `KXINX`, `KXNASDAQ100` at 4 PM: `between`
strikes, not nested), the up/down coins (`KXINXDUD`, `KXNASDAQDUD`, `KXEURUSDD`,
`KXGBPUSDD`, `KXUSDJPYD`: one market, ~50/50), the 10Y path contracts, the monthly
(`KXUST…AM`) and year-end (`KXUST10YRRATE27`, `KXUST30YRRATE27`) Treasury ladders, and the
spread contracts (`KX10Y2Y`, `KX10Y2YDATE`). The hourly and 15-minute Treasury and FX
series (`KX10YRRATEH`, `KX2YRRATE15M`, `AUDUSDH` …) have no open markets.
