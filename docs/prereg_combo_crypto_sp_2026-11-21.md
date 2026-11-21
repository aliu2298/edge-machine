# Pre-registration: Combo, crypto No + S&P No (Sandbox paper, 2026-11-21)

Written before the first entry. Olu's decision, Nov 20 2026: "convert the leadership page to combo". Spec: `docs/combos_high_hit_2026-11-20.md` ("Build spec", changed Nov 21 after the timing check). Code: `combo_lane.py`, page: `combo_build.py` (combo.html).

## Rule
Crypto No with S&P No, one two-leg paper combo a trading day. Both legs are chosen at the minute the crypto No lane (`crypto_fav_band_below`) logs its pick:
- **Crypto leg:** that lane's own pick for the day (the highest-priced coin if there are several), at the ask the lane logged. A pick logged more than 20 minutes before the combo read is stale, and the day is "no combo".
- **S&P leg:** `finance_nc`'s rule re-run at that minute, not the 12:30 ET pick: the cheapest KXINXU 16:00 ET rung with a No ask of 90c to 98c, a spread of 3c or less and 25 or more contracts. `finance_nc`'s own ledger is not touched.
- **No combo**, with the reason logged, when either leg has no pick at that minute, and at weekends. A weekday with no crypto pick by 14:30 ET is logged "no combo".
- Two legs only. No commodity, economics, soccer or 95c-and-up legs.

## Price and settlement
- Paper price: 0.994 x 1.03 (the crypto-S&P link) x the product of the two No asks, plus the taker fee 0.07 x p x (1 - p). The 0.994 and the 1.03 were fixed from the tape before any combo was scored; 1.03 is the weakest number in the study.
- The combo pays 1 only if both legs win. A void or part-value leg is multiplied by its settled value: no refund.
- Comparison rows, same days: (1) the same two legs as singles at the same minute and asks; (2) each lane's own single record on its ledger.
- Combo legs are bought at the ask, at one minute. A lane that relies on resting bids or target sells cannot be a leg.

## Why, and what does not count
The idea came from 19 days to Nov 19 2026 on which the two legs were priced at different times (17 landed, +23.1%). At one moment only 8 or 9 of those days could be formed (+5% to +30%). None of that counts: **the record starts at zero on the first combo day**, and the 19 replay days are not in it.

## Read
- Read once at **30 settled combos**, against the same two legs as singles.
- Keep only if the combo's return is above zero and its break-even markup is above the paper price on those 30. **Retire** if the combo is at or below the singles, and at once if either lane's own singles go under zero.
- Percentages only on the page. Sandbox paper: no bot, no VPS, no live order.
