# Eredivisie draw band v2: pre-registration (Nov 12 2026)

Sandbox paper lane `ere_draw_home`. A fresh record from Nov 12 2026. Version 1 (`ere_draw`) keeps its own record and stays as the comparison. Nothing is promoted by this document.

## The rule

Back the TIE on a Kalshi Eredivisie match (`KXEREDIVISIEGAME`) when all of these hold:

1. The draw's share of the three asks is 0.20 to under 0.25 (version 1's band).
2. The draw ask is 0.26 or less (version 1's cap).
3. **The home side is the favourite**: its ask is above the away side's.
4. **Kickoff is 24 hours away or less.**

One bet per match, at the ask, held to settlement.

## Why these two terms

**Home favourite.** A stated selection reason, not a price band alone. Inside the band the draw has beaten its price where the home side is favoured, and not where the away side is:

| Period | Prices | Home favourite | Away favourite |
|---|---|---|---|
| 2013/14 to 2020/21 | Bookmaker close | +1.5 points (443) | +4.0 points (263) |
| 2021/22 to 2025/26 | Bookmaker close | +8.8 points (264) | −0.8 points (168) |
| 2025/26 | Kalshi, 3h before kickoff | +15.8 points (46) | +1.6 points (32) |
| 2026/27 so far | Kalshi, 3h before kickoff | +18.9 points (31) | −12.5 points (19) |

"Points" is the share of matches drawn minus the price paid. Season by season the home favourite was ahead in each of the last five seasons and in five of the nine before, by smaller margins.

**Inside 24 hours.** The research prices are closing prices. Version 1 logs its bets a median 4.5 days before kickoff. On Kalshi's own history the band read 4.5 days out is flat (+0.7 points on 50); read 24 hours or 3 hours out it is +9.0 and +8.8 points (127 and 128 bets). The 4.5-day comparison was not on the menu written in advance; it is a correction to match the research, with that figure as support.

## How it was chosen

The menu was written before any filtered result was read (`PREREGISTERED.md` in the research folder, with its addendum).

- Eight filters were tried. Five on 13 seasons of bookmaker prices: low total, draw-prone teams, home favourite, close match, price drift. Three on Kalshi's history: entry at 24h v 3h, draw price fell, home favourite.
- Keep rule: a filter must beat version 1 by 2 points on the discovery period, then again on the holdout with a filtered-v-rest score of 2 or more.
- On the bookmaker history no filter passed. Home favourite failed there because the first eight seasons did not show it.
- On Kalshi's history (discovery 2025/26, holdout 2026/27) home favourite passed: +18.9 points against version 1's +7.0, filtered-v-rest score 2.56.

## Replay on Kalshi's history (not the record)

Entry 24 hours before kickoff, honest fills, every settled match from Dec 2025 to Nov 8 2026.

| | Bets | Match days | Drew | Price | Return |
|---|---|---|---|---|---|
| Version 2 | 76 | 58 | 38.2% | 23.2c | +55.6% |
| Version 2, 2025/26 | 45 | 34 | 35.6% | 23.3c | +44.7% |
| Version 2, 2026/27 | 31 | 24 | 41.9% | 23.2c | +71.3% |
| Version 1, same entry time | 127 | 76 | 32.3% | 23.3c | +30.4% |
| Away favourite, same entry time | 51 | 42 | 23.5% | 23.5c | −7.0% |

The replay passes the promotion gate's evidence test (score 2.42, both halves up, up without its best day). The replay is not the lane's record: the gate reads the fresh record, which starts at zero.

## Weak parts, stated now

- In the eight seasons before 2021/22 the home favourite was no better than the away favourite. This is a recent pattern, not a law.
- It is one of eight filters tried, on top of the band itself.
- The Kalshi 2025/26 season is the same matches as the last season of the bookmaker holdout. Only 2026/27 (31 bets) is new evidence.
- A fair draw at 23c wins about one bet in four. Runs of ten losses will happen.

## How it will be judged

- Against version 1 over the same period, and against backing the draw on every three-way match listed.
- Review at 10 settled bets, read at 30. About 2 bets a matchweek, so 30 bets is about four months.
- Going live needs the promotion gate (`promotion_gate.py`): a positive honest return on its own entries and the evidence test, or Olu's recorded waiver.
