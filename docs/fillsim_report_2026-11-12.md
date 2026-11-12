# Paper v live: first report (Nov 12 2026)

One shared fill simulator now exists (`fillsim.py`, rule set **honest-v1**). Every lane with its own engine was re-graded on it from Kalshi trade prints and set beside the live record. No page and no ledger was changed.

All figures are the return per bet after fees, with the number of bets in brackets.

## What we found

1. **Buy-and-hold lanes are honest.** On 366 bets that were both on the page and placed live, the page made −1.7% and live made −1.7%. The price paid was 0.3c better than the price logged, on average (217 winners). The gap is not there.
2. **The gap is in lanes that rest an order or sell early.** Old paper rules let a sale count seconds after the fill, and let a price that only touched the order count as a fill.
3. **The simulator matches live on the same bets.**
   - Over 3.5 cheap NO, 22 bets: page +11.3%, simulator −25.4%, live −26.0%.
   - Top-5 goalless dip, 12 bets: page −10.6%, simulator −9.4%, live −9.4%.
4. **In thin NBA win-margin books, live beat the strict simulator.** There a touch often does fill. So each lane gets two figures: strict ("honest") and "if touches fill". Live landed at the top of that range on both NBA lanes.
5. **Fees.** A taker pays 0.07 × p × (1 − p) per contract, rounded up to a hundredth of a cent. A resting order that fills pays nothing. Paper lanes charge resting orders 1.75%, which live never pays, so those pages read slightly low.

## Lane by lane

| Lane | Page | Honest | If touches fill | Live |
|---|---|---|---|---|
| Over 3.5 cheap NO (v4, as traded live) | +20.6% (42) | −7.2% (42) | +12.6% (45) | −26.0% (22) |
| Over 3.5 cheap NO (v5, cancel at minute 80) | +3.9% (15) | +4.4% (15) | +4.4% (15) | – |
| NBA win margin NO fade | +5.7% (105) | +8.2% (117) | +10.7% (118) | +15.8% (86) |
| NBA win margin YES split | +11.8% (129) | +8.2% (124) | +14.6% (124) | +18.9% (120) |
| Top-5 goalless dip (Sandbox) | +6.3% (32) | +7.7% (32) | +7.7% (32) | – |
| Top-5 goalless dip (the live bids) | −10.6% (12) | −9.4% (12) | −9.4% (12) | −9.4% (12) |
| Argentina goalless dip | +52.5% (2) | +53.7% (2) | +53.7% (2) | – |
| Trump mentions 10c dip bid, hold | −4.0% (41) | −2.4% (41) | +39.5% (43) | – |
| WTI cheap YES split | −60.2% (13) | −59.9% (13) | −59.9% (13) | – |
| AAA gas weekly cheap NO (hold) | +145.3% (6) | +232.8% (3) | +232.8% (3) | – |
| Boxing cheap underdog split | +33.8% (17) | +29.3% (16) | +29.3% (16) | – |
| Challenger cheap side, hold (baseline) | +23.4% (96) | +22.6% (94) | +22.6% (94) | – |
| Challenger won-here, hold | +54.7% (23) | +54.6% (23) | +54.6% (23) | – |

Retired lanes, for the record:

| Lane | Page | Honest |
|---|---|---|
| AAA gas daily cheap NO | −20.4% (19) | −20.1% (19) |
| College football underdog, +50% sell | −14.1% (159) | −7.1% (158) |
| College football home underdog, sell at 4x | −31.4% (11) | −31.1% (11) |
| UFC underdog split | −86.5% (7) | −86.4% (7) |
| Album cheap YES / NO | no counted entry / 3 entries | – |

### The same bets, three ways

Only bets that live really took.

| Lane | Bets | Page | Honest | If touches fill | Live |
|---|---|---|---|---|---|
| Over 3.5 cheap NO | 22 | +11.3% | −25.4% | −11.4% | −26.0% |
| Top-5 goalless dip | 12 | −10.6% | −9.4% | −9.4% | −9.4% |
| NBA NO fade (the live bids) | 84 | – | +11.4% | +15.1% | +15.4% |
| NBA YES split (the live entries) | 112 | – | +8.5% | +16.4% | +15.2% |

## What this changes

- **Over 3.5 cheap NO v4:** the page's +20.6% is −7.2% once a sale must wait 60 seconds. It is already back in the Sandbox. v5 is +4.4% on 15, too few to read.
- **Trump mentions dip hold:** −2.4% strict, +39.5% if touches fill. Two words that only touched 10c both won, and they carry the whole difference. This lane cannot be judged on paper; it needs a saved order book or a small live test.
- **NBA win margin, both lanes:** positive on the page, on both simulator figures and live.
- **Top-5 goalless dip:** the Sandbox record (+7.7% on 32) and the live bids (−9.4% on 12) differ in which matches and prices, not in fills.
- **Boxing, Challenger hold lanes, WTI:** barely move. Their entries were real.
- **AAA gas weekly:** three of six entries fail the ask check. Too few to read.

## How the two free numbers were set

The simulator cannot see the queue at a price, or how long a sale takes to go up. Both were checked against the live record, picking on half the markets and testing on the other half.

- **Queue.** Of 190 posted bids, 96 filled live. "Only a print through the price fills" called 98.9% right on the first half and 97.0% on the second.
- **Touches.** Seven sell legs only touched their target; six sold live. But the tape includes our own fills, so a touch on a live bet partly proves itself. That is why touches are shown as a second figure and not built into the main one.
- **The wait.** With no wait the simulator counted 3 over 3.5 sales that live never got. With 30 to 120 seconds it counted one (a known fault on Nov 1). The lanes' existing 60 seconds is kept.

One call was mine, not the data's: for sells the first half alone favoured "a touch fills". I kept the strict rule as the main figure because those matches were our own prints, and because strict is the one that matched the soccer lanes.

## Not re-graded yet

- 15-Minute lanes and the Trading lanes (own engines, own price sources).
- Eredivisie draw maker (6 entries), MLS tie split and T1-M sell (0 entries each), corners favourite NO, jobless claims, finance.
- Soccer and NBA rule lanes buy and hold. Where they ran live they are in finding 1.

## Tools

- `fillsim.py`: the simulator. `test_fillsim.py`: each known failure as a test (the over 3.5 flash print, the gas opening-minute print, the Album thin ask, the Nov 1 crossed bids, a touch behind the queue).
- `fillsim_calibrate.py`: the queue and wait check above.
- `fillsim_regrade.py`: the lane table. `fillsim_paid.py`: logged price v price paid.
- `fillsim_tape.py`: trade prints with a local cache.

## Next

1. Olu decides which pages switch to the simulator, and whether to show both figures.
2. Bring the remaining lanes onto it.
3. Problem 2: the false-discovery check.
