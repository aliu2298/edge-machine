# African qualifiers: BTTS (Nov 13 2026)

Research only. No lane, page or Production change. The test and the rule for "leans the same way" were written down before any BTTS price or result was read.

Olu's ask: the Nov 12 study and its forward check left out Kalshi's BTTS markets on African qualifiers. Does BTTS lean the same way as the side-to-score finding?

"Points" is the share of bets won minus the price paid. "Return" is after fees. A match day is one outcome.

## Verdict

**BTTS leans the same way. First-half BTTS does not.**

| Every September match, 3h before kickoff | Bets | Won | Price | Points | Return |
|---|---|---|---|---|---|
| **BTTS, YES** | 48 | 54.2% | 38.9c | **+15.2** | +35.9% |
| BTTS, NO | 48 | 45.8% | 62.1c | −16.3 | −27.6% |
| First-half BTTS, YES | 45 | 20.0% | 21.5c | −1.5 | +13.8% |
| First-half BTTS, NO | 30 | 83.3% | 90.3c | −7.0 | −8.3% |

- BTTS YES clears the bar written in advance (3 points over its price, return above zero). It gets a forward row; the addendum is in `prereg_africa_goals_forward_2026-11-12.md`.
- First-half BTTS does not clear it and its book is wide (12c median spread). It stops here.
- **This is not new evidence.** It is the same 48 matches and the same goals as the side-to-score finding, seen through another market. One window can still be luck.

## Is BTTS a cheaper or richer way to hold the lean?

**About the same price, with more swing.**

| Same 46 matches, YES at the ask | Bets | Won | Price | Points | Return |
|---|---|---|---|---|---|
| A side to score | 89 | 74.2% | 65.7c | +8.4 | +11.9% |
| BTTS | 46 | 52.2% | 39.2c | +12.9 | +28.6% |

- **Price:** the BTTS ask averaged 39.2c. The two side-to-score asks multiplied together come to 40.7c, and to about 37c once the link between the two sides is taken off. So BTTS costs within about 2c of what the two sides imply.
- **The two sides scoring go against each other a little.** Correlation −0.20 in these matches and −0.15 in 156 earlier qualifiers. When one side scores, the other is slightly less likely to. BTTS is worth a few cents less than the plain product for that reason.
- **Book:** BTTS is tight, a 1c spread at the median. 46 of the 48 asks were confirmed by trade prints.
- **Swing:** BTTS wins about half the time at 39c; a side to score wins three times in four at 66c. The same lean pays more per bet on BTTS and loses more often.

## The context that matters most

| AFCON qualifiers | Matches | Home scored | Away scored | Both scored |
|---|---|---|---|---|
| Earlier campaign (ESPN, before Sep 24 2026) | 156 | 65% | 59% | 34.6% |
| September 2026 window | 48 | 77% | 75% | 54.2% |

- The market's 39c is close to the earlier campaign's 35%. September ran far above both.
- So the whole lead (overs, sides to score, BTTS) rests on September being a truer guide than the campaign before it. That is exactly what the forward check is for.

## Where BTTS YES won (September, description only)

| Split | Bets | Points |
|---|---|---|
| BTTS ask under 35c | 10 | +7.3 |
| 35c to under 45c | 32 | +15.8 |
| 45c and over | 4 | +3.8 |
| Favourite's win chance under 0.55 | 15 | +10.7 |
| 0.55 to under 0.70 | 17 | +25.4 |
| 0.70 and over | 14 | +0.1 |

- Without its best match day the row is +10.9 points on 34.
- None of these splits is a rule. They are too small, and they were read after the result.

## Limits

- **One window, eight match days.** The score is 2.2, on the same goals that produced the other three leads.
- **The forward row will be small.** It was added after the November window opened, so only the matches that kick off after the addendum count: six are listed.

## Build spec: BTTS row

For whoever builds. One more row on the existing `africa_goals` Sandbox paper lane (`africa_goals.py`). Observation only, paper only, never in Production. The three existing rows and their conditions do not change.

- **Rule:** YES on both teams to score, every AFCON qualifier Kalshi lists.
- **Market:** `KXAFCONBTTS`, the event's single market.
- **Entry timing:** the ask on the hourly quote three hours before kickoff (ESPN fixture time), ask between 2c and 98c. Same as the other rows.
- **Fills and fees:** the fill simulator's quoted rule; taker fee.
- **Record:** a match day is one outcome. The row is labelled "added Nov 13 2026, after the window opened".
- **What counts:** matches that kick off after 18:30 UTC on Nov 13 2026. Earlier matches of this window may be backfilled from the same hourly quote for display; they are flagged and not counted.
- **Not built:** first-half BTTS (`KXAFCON1HBTTS`).
- **The one change from version 1:** none; this is a new row.
- **Retire or keep:** by the addendum's text.

## Files

Research folder: `~/edge-research/intl_2026-11-12/`. `PREREGISTERED.md` (BTTS addendum, written first), `pull_btts.py`, `btts.py`, `btts_results.txt`, and `window_btts.sh` for the forward read.
