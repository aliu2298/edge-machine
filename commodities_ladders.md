# Kalshi daily commodity ladders — discovery note (2026-10-08)

Read-only survey for a Commodities favourite-band lane, the same shape as the Crypto
lane (`crypto_fav_band`). Nothing here registers a rule or logs a quote.

**How this was read.** When first written, this session's network policy denied
`api.elections.kalshi.com`, so the survey below came from the repo's own ledger; the host
was opened the same morning and the open questions at the end were answered live. The
ledger survey: the `commodities`
domain already asks Kalshi for every *daily* series in the Commodities category
(`KALSHI_BINARY["commodities"]`, `freq=("daily",)`) and has logged every rung of every
ladder since 2026-09-18 — 4,881 rows across 7 series as of this morning. That list is
exactly the enumeration asked for, minus the three things the ledger cannot see,
which are marked **unverified** below and need one live read before registration.

## Series that settle once per trading day on a nested "Above $X" ladder

| Series | Commodity | Close (ET) | Ticker shape | Rungs/day (median, range) | Spread (median, p90) | Days seen | 70–80¢ rung present |
|---|---|---|---|---|---|---|---|
| `KXWTI` | WTI crude | **2:30 PM** (18:30Z), ticker hour `14` | `KXWTI-26OCT0814-T81.49` | 30 (18–31), $0.50 steps | 3¢, 4¢ | 15 of 15 weekdays, **Mon–Fri** | 15 of 15 days, median 2 rungs |
| `KXBRENTD` | Brent crude | 5:00 PM (21:00Z), ticker hour `17` | `KXBRENTD-26OCT0817-T…` | 20 (20–20) | 4¢, 4¢ | 12, **Mon–Thu only** | 11 of 12 days, median 2 |
| `KXGOLDD` | Gold | 5:00 PM (21:00Z) | `KXGOLDD-26OCT0817-T4006` | 32 (26–40), $10 steps | 3¢, 4¢ | 12, **Mon–Thu only** | 12 of 12 days, median 2 |
| `KXSILVERD` | Silver | 5:00 PM (21:00Z) | `KXSILVERD-26OCT0817-T…` | 29 (25–38) | 4¢, 4¢ | 12, **Mon–Thu only** | 12 of 12 days, median 2 |
| `KXCOPPERD` | Copper | 5:00 PM (21:00Z) | `KXCOPPERD-26OCT0817-T…` | 28 (14–40) | 4¢, 4¢ | 12, **Mon–Thu only** | 9 of 12 days, median 1 |
| `KXNATGASD` | Natural gas | 5:00 PM (21:00Z) | `KXNATGASD-26OCT0817-T3.030` | 48 (27–62), $0.005–0.045 steps | 4¢, **8¢** | 12, **Mon–Thu only** | 12 of 12 days, median 6 |

Every one of these is a `T`-ladder of `strike_type: greater` markets: the `T` value is the
floor, and the venue titles the rung "Above $X" / "$X or above", the same nesting as the
coin ladders (one move settles every rung at or below it, so two rungs on one commodity
are one bet counted twice).

Spreads are from the rows the tracker logged, which it does about **29 hours** before the
close (the domain's `lead_h=6` floor, read on the previous day's run). Inside the 2–3.5h
window the book is usually tighter, not wider, but that is an expectation, not a
measurement; the only earlier study (61 days, 6h before close) found a two-sided book on
46% of sampled strikes.

## Excluded

| Series | Why |
|---|---|
| `KXAAAGASD` + 21 state series (`KXAAAGASDxx`) | AAA retail gasoline: `between` **buckets**, not an "Above" ladder; closes 10:00 AM ET on a published daily average, listed 7 days a week. Already its own lane (`gas_nochange`). |
| 15-minute / hourly coin-style series, weekly ranges (`KXGOLDW` "Gold price tomorrow" and kin), monthly and annual | Not `frequency: daily`, so the commodities domain never fetches them; not surveyed. |

## Where the shape differs from Crypto — things the registration has to say

1. **Two close times, not one.** WTI closes at **2:30 PM ET**; the other five close at
   5:00 PM ET. The crypto lane's single 13:15 CT read cannot serve WTI: its window
   (3.5h–2h before 2:30 PM ET) is **10:00 AM–11:30 AM CT**. The 5:00 PM ET group shares
   the crypto window (**12:30–2:00 PM CT**). So the scanner needs **two reads a day**.
2. **Fridays.** In three weeks of ledger the 5:00 PM ET series (Brent, gold, silver, copper,
   natural gas) listed **Monday to Thursday only**; WTI listed Friday too. If that holds,
   a "trading day" for the lane is Mon–Fri for WTI and Mon–Thu for the rest, and the
   planned 30 market-days will take about seven weeks. **Unverified live** — it may be a
   listing gap in the ledger rather than Kalshi's calendar.
3. **Rung spacing is coarse on crude and gold** ($0.50 and $10) and fine on natural gas
   (as little as $0.005), so natural gas usually has several in-band rungs and copper
   sometimes none. "Lowest-priced rung in band, one per commodity" still picks exactly one.
4. **Natural gas books are wider** (p90 spread 8¢ against 4¢ elsewhere): the ≤3¢ spread
   floor will refuse it more often than the others. Nothing to change; worth expecting.
5. **Correlation.** Gold and silver, and WTI and Brent, move together. A day where both
   members of a pair fire is reported per commodity and judged with that stated, as the
   Crypto method does for the coins. Natural gas and copper are closer to independent of
   the pairs. The measured within-day correlation for the five coins (+0.76) has no
   commodity equivalent on file yet; it should be measured from the ledger's graded
   rungs before the first read, not assumed.

## Open questions, answered from the live API (2026-10-08, 06:00Z, read-only)

The host was opened later the same morning. Read from `/series?category=Commodities`
and `/events?series_ticker=…` (open, settled and closed), before the lane logged anything.

1. **Settlement source per series — answered.**

   | Series | `settlement_sources` | Rule text (from the market) |
   |---|---|---|
   | `KXWTI` | ICE | "the daily settlement price for WTI crude oil (front-month contract) on <date> is above $X" — the 14:30 ET settlement |
   | `KXBRENTD` | Pyth – Brent | "the close price of the 1-minute candlestick for brent crude oil on <date> at 5:00 PM EDT is above $X" |
   | `KXGOLDD` | Pyth – Gold | same form, gold USD/t.oz |
   | `KXSILVERD` | Pyth – Silver | same form, silver USD/t.oz |
   | `KXCOPPERD` | Pyth – Copper | same form, copper USD/lb |
   | `KXNATGASD` | Pyth – NATGAS | same form, natural gas USD/MMBtu |

   Close times confirmed: WTI `expected_expiration_time` 18:30Z, the other five 21:00Z.
   Every open event is a `greater` ladder (`yes_sub_title` "Above $X"), as built.

2. **Ask size at the 70–80¢ rungs — pre-market snapshot only; the in-window figure
   comes from the lane's own rows.** Read at 02:00 ET, eight to fifteen hours before the
   closes, so this is NOT the window measurement the rule is judged at:

   | Series | In-band rungs now | Spread | Ask size |
   |---|---|---|---|
   | KXWTI (Oct 8) | 2 | 1¢ | 13, 215 |
   | KXWTI (Oct 9) | 2 | 3–4¢ | 550, 4,000 |
   | KXBRENTD | 2 | 1¢ | 58, 58 |
   | KXGOLDD | 2 | 1¢ | 12, 29 |
   | KXSILVERD | 1 | 1¢ | 2 |
   | KXCOPPERD | 1 | 1¢ | 15.5 |
   | KXNATGASD | 6 | 3–4¢ | 71–575 |

   Overnight the books are tight (1¢) and thin (metals 2–29 contracts), which is what a
   25-contract floor would refuse; what they look like inside 10:00–11:30 AM CT and
   12:30–2:00 PM CT is exactly what the lane now records (`bid`, `ask`, `ask_size` on
   every row it takes, `store_book`). Read the first week's rows before drawing anything.

3. **The Friday gap is Kalshi's calendar — answered.** Settled and closed events since
   each series began: WTI 855 since 2022-09 (Mon–Thu ~190 each, Fri 94); Brent, gold,
   silver, copper and natural gas 107–112 each since 2026-03, **Monday to Thursday only,
   zero Fridays** (two or three Sunday events each, early experiments the trading-day rule
   refuses anyway). Friday's 17:00 ET close is listed under the **weekly** series
   (`KXGOLDW-26OCT0917`, "Gold price on October 09, 2026 at 5:00 PM EDT?", 40 `greater`
   rungs, the same Pyth rule). Those weekly tickers are **not** in this registration: the
   approved lane is the six daily series, so for the 17:00 group a Friday is no market-day,
   and the 30-day read is about seven weeks as registered. Adding the Friday weekly ladders
   as the same bet is a possible follow-up, not a change made here.

## Decisions taken at registration (2026-10-08)

- All six series, every crypto parameter copied unchanged (band, window, lowest rung,
  one per commodity per close, 3¢ / 25 floor measured inside the window, 30-day read).
- Two reads a day: WTI in 10:00–11:30 AM CT, the 17:00 ET group in 12:30–2:00 PM CT.
  `scripts/vps_commodities_window.sh` asks for each from inside its window and defers
  to the crypto request when that has already covered the 17:00 window.
- A market-day is a trading day: weekends and NYSE holidays (`COMMOD_FAV_HOLIDAYS`, the
  same set `market_track.NYSE_HOLIDAYS` keeps) are no market-day; a rung listed on one
  is refused.
- One outcome per trading day across all six (`market_day` → `COMMODFAV|date`).

## Co-movement, measured from the ledger's graded rungs (2026-10-08)

The settlement of a day's ladder lies between the highest rung that resolved Yes and
the lowest that resolved No; day-over-day log returns from that midpoint, pairs with
8–10 settled days each (natural gas has 5–7 and is not readable yet):

| Pair | n | Correlation | Sign agreement |
|---|---|---|---|
| Gold / Silver | 10 | **+0.89** | 90% |
| WTI / Brent | 8 | **+0.84** | 75% |
| Silver / Copper | 10 | +0.85 | 90% |
| Gold / Copper | 10 | +0.70 | 80% |
| WTI / Gold | 10 | −0.27 | 30% |
| WTI / Copper | 10 | −0.61 | 10% |
| Brent / metals | 8 | −0.2 to −0.3 | 38% |

So the pairs are real and the pairs are not one cluster with each other. A day is
still judged as one outcome across all six, which errs toward too little evidence
rather than too much, and is stated in the registration.
