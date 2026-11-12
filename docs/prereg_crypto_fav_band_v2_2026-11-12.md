# Crypto favourite band v2 (`crypto_fav_band_v2`) — pre-registered 2026-11-12

Status: SANDBOX PAPER ONLY. Not in Production, no feed, no bot change, no stake. Frozen before the first entry. Olu's decision of 2026-11-12.

## What it is
The Yes twin of the live crypto lane, **the same rule as `crypto_fav_band`, unchanged**, on a **fresh record**:
- Back the YES on a Kalshi coin-directional rung priced **0.70-0.80 inclusive** (a rung below the coin's price), the rung's YES ask.
- Entered **2-3.5 hours before the 17:00 ET close**, measured to the contract close; up to three reads per window, 30 minutes apart.
- **One bet per coin per close**, the **lowest-priced** rung in band, equal prices to the lower ticker. The same five coins (BTC, ETH, SOL, XRP, HYPE).
- Liquidity floor: a two-sided YES quote, a spread of 3c or less, 25 contracts on the ask. Taker fee on entry, held to settlement.
- Record: the first window after deploy onward (it is its own source, `crypto_fav_band_v2`, so nothing before it counts). **Review at 30 settled, decide at 100.** An outcome is a day across all coins, as for the other crypto lanes.
- `crypto_fav_band`'s own record stays exactly as it was, as its own retired line (retired 2026-11-03).

## Why it is back, and what that is worth
The Crypto lanes review of 2026-11-12 (PR #421, `docs/crypto_lanes_review_2026-11-12.md`) replayed the Yes twin on Kalshi's daily 17:00 ET coin ladders since June 1, one pick per coin and close, honest fills:

| Period | Bets | Return after fees |
|---|---|---|
| Jun 1 to Aug 10 (a window nobody had looked at) | 63 | +11.1% |
| Aug 11 to Oct 17 (where the rule was found) | 59 | +13.5% |
| Oct 18 to Nov 11 | 12 | −0.7% |
| All | 134 | +11.1% |

That is the same as the live No lane (+11.4% on 131 over the same months). The lane was retired on 2026-11-03 on a short record read in its weakest stretch: the review counts 25 won in 35 (−6.2%); the Sandbox page shows 15–8 on 23 market-days (−7.8%) since its start.

**Stated honestly:** the replay is a reason to test, not a result. The twin was brought back after looking at how it did in the months it was gone, and the last 12 bets of the replay were flat; the review itself says no filter passed and the clean windows reach a score of 1.43 against the 2 the promotion gate asks for. The record that counts for v2 starts at zero from the first entry after deploy.

## What would count as a result
Nothing before 30 settled. At 30 it is a direction check; at 100 it is decided against its own price (the effective price at mid-band is about 0.763 after the taker fee, so the band has to beat its price by about 1.3 points to break even) and against the live No lane. A version that does not beat its price on the fresh record is retired again.

## Not changed
`crypto_fav_band` and its record, the live crypto lane and its Production feed, the other crypto lanes, any stake.
