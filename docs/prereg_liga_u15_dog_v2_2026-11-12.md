# La Liga under 1.5 in heavy mismatches v2: pre-registration (Nov 12 2026)

Sandbox paper lane `liga_u15_dog_24h`. A fresh record from Nov 12 2026. Version 1 (`liga_u15_dog`) is retired the same day and keeps its own record. Nothing is promoted by this document.

## The rule

Back UNDER 1.5 goals (the NO side of Kalshi's over 1.5, `KXLALIGATOTAL`) on a La Liga match when all of these hold:

1. The match's own three-way board prices the underdog under 0.135, with the margin removed (version 1's cut).
2. The NO ask is 0.20 or less (version 1's cap).
3. The over 1.5 board holds no more than 6%, and the NO side has a tight book (version 1's terms).
4. **Kickoff is 24 hours away or less.**

One bet per match, at the ask, held to settlement.

Terms 1 to 3 are version 1's selection, unchanged. Term 4 is the only change.

## Entry timing

- The kickoff is the one ESPN lists. Kalshi's own start time is an estimate, so a match with no ESPN kickoff is not bet.
- The tracker checks the board on each run. The bet is logged on the first run inside the 24 hours where terms 1 to 3 hold. If the ask is above the cap at first and comes down later, it is logged then.
- Nothing is logged after kickoff.

## Why this one change

Version 1 logged its bets a median 4 days before kickoff. The price there is worse.

| Entry before kickoff | Bets | Won | Price | Return |
|---|---|---|---|---|
| 94 hours (where version 1 logged) | 18 | 11.1% | 13.6c | −24.8% |
| 24 hours | 21 | 19.0% | 12.2c | +36.7% |
| 3 hours | 21 | 14.3% | 12.2c | +6.1% |

Replay of the rule on Kalshi's own La Liga history, honest fills, returns per bet after fees. On the same 20 matches the NO ask was 15.4c four days out and 12.1c three hours out. That 3c is about a quarter of the stake.

Source: `docs/mls_laliga_review_2026-11-12.md`.

## Weak parts, stated now

- **The replay shows a better price, not an edge.** Three or four wins in about twenty bets settle nothing.
- **Version 1's own case against itself still stands.** In 2025/26 these matches went over 1.5 more often than priced, the opposite of the idea.
- **Long losing runs are normal.** The under wins about one bet in five.
- **No filter was added.** The review tried filters on this lane and none held.
- The 24-hour and 3-hour replays differ by one win. Nothing here says 24 hours is better than 3.

## Version 1's final record

3 wins in 9 paper bets, 3 won against 1.2 priced, +112.2% after fees. Never in Production. No open bets.

## How it will be judged

- Against backing the under on every La Liga match of this market over the same period.
- Review at 10 settled bets. Read at 30. At about 2 bets a matchweek, 30 bets is roughly fifteen weeks.
- Going live needs the promotion gate (`promotion_gate.py`): a positive honest-fill return on its own entries, and the evidence test or Olu's recorded waiver.
