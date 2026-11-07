# Kalshi Invest big-move grid — pre-registration (fixed 2026-11-06, before any result was read)

Paper research only. 1x, no leverage. Venue the rules would trade: Kalshi Invest stock perps (Up/Down).

## Universe and data
- The 58 Kalshi Invest equity perps with status `active` on 2026-11-06 (`symbols.txt`; includes SPY and QQQ).
- Underlying stock history: Alpaca SIP 1-minute bars, split-adjusted, regular hours 9:30–16:00 ET only,
  2023-01-01 → 2026-11-06. Minutes with no trade have no bar; hold lengths are counted in bars.

## Periods
- Research half 1: 2023-01-01 → 2024-06-30
- Research half 2: 2024-07-01 → 2025-12-31
- Holdout: 2026-01-01 → 2026-11-06 (read once, after the research table)

## Events (the ENTRY grid) — look-ahead free
Move size X ∈ {3%, 5%, 8%}, measured three ways:
- **1h**: close of minute t v the close 60 bars earlier in the same session. The first minute of the day that crosses X
  (per stock, day, direction, size). Entry: open of the next bar.
- **1 trading day**: close of the 15:55 bar v the previous session's last close. Entry: open of the 15:56 bar.
- **gap** (overnight or weekend): the session's first open v the previous session's last close. Entry: open of the 9:31 bar.
Direction: **drop** (move ≤ −X) or **jump** (move ≥ +X).
Action: **fade** (drop→Up, jump→Down) or **follow** (drop→Down, jump→Up).

## Exits (the EXIT grid)
Take-profit ∈ {2, 4, 8}%, stop ∈ {2, 4}%, max hold ∈ {1h = 60 bars, 1d = 390 bars, 5d = 1950 bars}.
TP and stop are resting levels: filled at the level, or at the bar's open if the bar opens through it.
If one bar touches both, the STOP is taken (conservative). Else exit at the close of the last bar of the hold.
Positions carry overnight (stock funding is 0% today; not charged).

## Cost
Kalshi taker fee 0.12% of notional a side + 0.03% half-spread a side = **0.30% round trip**, charged on every trade.

## Grid size — the multiple-testing count
3 sizes × 3 windows × 2 directions × 2 actions × 3 TP × 2 stops × 3 holds = **648 cells**.

## Baseline (random entry, same stocks and dates)
For every event, 5 random entries on the SAME stock and SAME session, at a uniformly random bar
(for gap/day events: any bar 9:31–15:56; for 1h events: any bar from the 61st of the session), same side, same exit,
same cost. The event's baseline is the mean of its 5. **Margin** = event net − baseline net.

## Statistics
Per-event returns are averaged per entry DATE first (moves cluster on market days); t is over dates.

## A cell CLEARS only if all hold
1. n ≥ 30 events across the two research halves;
2. average net > 0 AND margin > 0 in half 1, in half 2, and in the holdout;
3. research margin t ≥ 3.8 (one-sided Bonferroni, 5% over 648 cells).
Cells with t ≥ 2 that pass 1–2 are reported as WATCH only. Cells are ranked on research margin.

## Venue angle (forward only, not part of this grid)
Kalshi perp price v the stock's reference price, minute by minute; a Kalshi-only move (perp moves ≥ X while
the reference does not) is logged with its snap-back over the next 5/15/60 minutes.

## Amendment A1 (2026-11-06, after the first run, before any rule was chosen)
The first run's baseline drew its 5 random entries from the event's OWN session. For "day" events (entry 15:56) and
most 1h events those entries came BEFORE the move, so the baseline carried the move itself: baselines near −1% made
every fade read +1% "margin" at t ≈ 10 while its own net was negative. That baseline is replaced for every cell alike:
the event's own minute of day on 5 random OTHER sessions of the same stock within ±30 sessions (same stock, same era,
same time of day, same side, same exit, same cost). The v1 output is kept as grid_v1_sameday_baseline.json. Nothing
else changes: the grid, the periods, the cost and the clearing bar are as registered.
