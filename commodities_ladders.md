# Kalshi daily commodity ladders — discovery note (2026-10-08)

Read-only survey for a Commodities favourite-band lane, the same shape as the Crypto
lane (`crypto_fav_band`). Nothing here registers a rule or logs a quote.

**How this was read.** This session's network policy denies `api.elections.kalshi.com`
(the egress gateway answers 403 to the CONNECT), so the public API could not be called
from here. The facts below come from the repo's own ledger instead: the `commodities`
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

## Unverified from this environment (needs one live read before registration)

- **Settlement source per series** (the `settlement_sources` field on `/series`): not
  stored in the ledger and not readable from here. Likely CME/NYMEX settlements for WTI
  and natural gas and a 5 PM reference print for the metals and Brent, but that is a
  guess and is not written into the registration until read.
- **Ask size** at the window: the tracker gates on a two-sided book but does not store
  `yes_ask_size_fp`, so the 25-contract floor cannot be checked against history. The
  crypto scanner reads it live and refuses below 25; the commodity scanner will do the
  same, and the first week of logged quotes will show how often that floor bites.
- **The Friday gap** above.

To take the live read, allow `api.elections.kalshi.com` for this environment (the
cloud environment's network settings, under Allowed domains), or run
`python3 -c 'import sandbox_sources as S; print(S.kalshi_series("Commodities", ("daily",)))'`
from a machine that can reach it.
