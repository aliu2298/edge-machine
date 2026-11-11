# Rebound after a slide — pre-registration (fixed 2026-11-11 ~17:55Z, before any result was computed)

Paper research only. 1x, no leverage. Venue the rule would trade: Kalshi Invest stock perps (Up only).
Olu's point: a 5-10% drop alone is not a setup. The rule must see the slide reach SUPPORT and the support HOLD.

## Universe and data
- The 58 Kalshi Invest perps of the 2026-11-06 list (`symbols.txt`, SPY and QQQ included).
- Alpaca SIP 1-minute bars, split-adjusted, regular hours 09:30–16:00 ET, 2023-01-03 → 2026-11-11 (the cached
  2026-11-06 pull plus 2026-11-06 → 2026-11-11). Daily, hourly, 30-, 15- and 5-minute bars are built from them.
- LIMITATION (stated up front): the research sees regular hours only. Overnight and pre-market moves appear as the
  next session's opening gap. The live lane reads Kalshi's reference price in every open minute, overnight included.

## Periods
- Research half 1: 2023-01-03 → 2024-06-30
- Research half 2: 2024-07-01 → 2026-08-07
- Holdout (read once, after the research table): 2026-08-10 → 2026-11-11 (~3 months)

## 1. The slide (precondition), evaluated at each 1-minute close
- **24h version (S24):** close ≤ 0.95 × the highest high of the trailing 24 calendar hours.
- **5-day version (S5D):** close ≤ 0.90 × the highest high of the trailing 5 sessions (today included).
- The slide's high H = that maximum. One trade per stock per session (S24) / per 5 sessions (S5D).

## 2. Support levels (all from data that closed before the minute being read)
- P_D: daily 5-bar pivot lows (a low below the 2 sessions either side), last 120 sessions, confirmed 2 sessions later.
- P_H: hourly 5-bar pivot lows, last 20 sessions, confirmed 2 hours later.
- PDL: the prior session's low. PWL: the prior calendar week's low.
- MA50, MA200: 50- and 200-session simple averages of daily closes (to yesterday).
- GAP: the prior close before a gap-up of 1%+ (session open ≥ 1.01 × prior close), last 60 sessions (the gap-fill level).
- RND: round numbers — multiples of 1 (< $50), 5 ($50–200), 10 ($200–1,000), 50 (> $1,000).
Only levels below the slide high and above 0.80 × H count.
- **Touch:** a 1-minute bar whose low is within 0.75% of a level (|low − L| ≤ 0.0075 L), while the slide holds.
- **Strength:** the number of distinct methods (P_D, P_H, PDL, PWL, MA50, MA200, GAP — RND not counted) with a level
  within 0.75% of L, plus 1 if the daily low touched within 0.75% of L on an earlier session in the last 60 (tested
  before). **Strong** = strength ≥ 2.
- When several levels are touched in one minute, L = the highest one touched.

## 3. Confirmation — the menu (enter only after one; never on the first touch)
Within 120 regular-hours minutes after the touch, with no 1-minute close below 0.995 L before it (the support failing):
- **C1a hold 15:** 15 minutes after the touch with no 1-minute close more than 0.5% below L.
- **C1b hold 30:** the same for 30 minutes.
- **C2 higher low (5-min):** after the lowest 5-minute bar since the touch, two later completed 5-minute bars with
  higher lows.
- **C3 reclaim:** a 1-minute close above the highest high of the 30 minutes before the touch.
- **C4 selling slows:** a completed 15-minute RSI(14) below 30 followed by a higher one (turning up), OR a completed
  5-minute bar with volume ≥ 2 × the average of the prior 20, a lower wick ≥ 50% of its range and a close in its
  upper half.
- **ANY1:** the first of C1a, C2, C3, C4. **ANY2:** the first minute two different ones (of C1a, C2, C3, C4) have both occurred.
Entry: the open of the 1-minute bar after the confirmation.

## 4. Exits
- Stop: 1% below the support level (0.99 L), resting; filled at the level, or at a bar's open if it opens through it.
- Target (two versions): **T_half** = halfway back to the slide's high, L + 0.5 (H − L); **T_break** = the lowest
  support level above entry × 1.01 that lies below H (the level it broke down through); if none, T_half.
- If one bar touches both, the STOP is taken (conservative).
- Time stop: S24 → 390 regular-hours minutes (1 day); S5D → 1,950 (5 days). Exit at the close of the last bar.
- Positions carry overnight (stock-perp funding is 0% today; not charged).

## Cost
Kalshi taker fee 0.12% of notional a side + 0.03% half-spread a side = **0.30% round trip** on every trade (as the
2026-11-06 big-move research). The live lane is graded on Kalshi's own quotes and prints with the honest-fill rule.

## Variants (the multiple-testing count)
2 slides × 7 confirmations × 2 support filters (all, strong only) × 2 targets = **56 variants**.

## Baselines
- **B1 — the same slides, no support cue (required; the no-blind-selection rule):** buy at the first minute the slide
  condition holds (per stock, per session / per 5 sessions), stop 3% below entry, T_half from entry (entry + 0.5 (H −
  entry)), same time stop, same cost.
- **B2 — random entry:** for each rule trade, the same minute of day on a random other session of the same stock within
  ±30 sessions, the same stop and target distances in %, the same time stop and cost.

## Statistics
Returns are averaged per entry DATE first (slides cluster on market-wide days); t is over dates.

## A variant CLEARS only if all hold
1. n ≥ 30 trades across the two research halves;
2. average net > 0 AND above B1's average net in half 1, in half 2 and in the holdout;
3. research t (variant v B1, date-clustered means, Welch) ≥ 3.1 (one-sided Bonferroni 5% over 56).
Variants that pass 1–2 with t ≥ 2 are WATCH. Ranked on research margin over B1.

## Then
Worked examples: SPCX and NVDA this week (Nov 9–11): their slides, the support levels, touches, confirmations, and
what each top variant would have done. The best variant(s) that clear go on trading.html as a fresh paper record;
if none clears, the top 1–2 run as observation-only lanes, labelled so.
