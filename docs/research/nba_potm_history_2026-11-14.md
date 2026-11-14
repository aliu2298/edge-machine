# NBA Player of the Month: does a clear leader hold? (5 seasons of public history, 2026-11-14)
Research only. No lane, no rule change, no orders. Question from Olu: "If someone is already at 70%, there isn't a lot of swinging, so do previous months show that holds?"
Follows [#459](nba_potm_2026-11-14.md) (Kalshi has no settled months, so this uses public history). Model written down BEFORE any stats were pulled:
[prereg](nba_potm_history_prereg_2026-11-14.md).

## Data
- 50 awards: 2021-22 to 2025-26, windows Oct/Nov, Dec, Jan, Feb, Mar (Mar 1 to season end), East and West (Basketball-Reference awards page).
- Field: each season's top 45 scorers (Basketball-Reference per-game page) with their game logs (225 public pages, 4s apart).
- Race rebuilt at day 7, 14, 21, 28 of each window and at month end using only games on or before that date: z(PPG)+0.5 z(RPG)+0.5 z(APG), times (0.5 + team win% over the games he played), softmax inside the conference = "implied win probability". Same score as #459.
- Fixed before looking. One parser bug found and fixed along the way (bold tags hid the league's top scorers from the field); no model change after seeing winners.

## Results (n = 50 awards, so every rate is about plus or minus 13 points)
| checkpoint | leader won | winner in top 2 | winner in top 3 | leader still leader at month end |
|---|---|---|---|---|
| day 7 | 28% | 46% | 52% | 18 of 50 |
| day 14 | 30% | 54% | 70% | 28 of 50 |
| day 21 | 42% | 62% | 76% | 36 of 50 |
| day 28 | 40% | 64% | 74% | 41 of 50 |
| month end (ceiling of this model) | 30% | 68% | 78% | n/a |

Oct/Nov windows (the one running now, about 6 weeks): leader won 2 of 10 at day 14, 3 of 10 at day 21.

### Does a "70% favourite" hold? (leader grouped by the probability the model gave)
| implied by model | n (checkpoints 14/21/28 pooled) | actually won | 95% range |
|---|---|---|---|
| under 35% | 45 | 33% | 21-48% |
| 35-50% | 47 | 43% | 30-57% |
| 50-65% | 22 | 32% | 16-53% |
| 65% and up (avg 77%) | 36 | 39% | 25-55% |

Day 21 alone: the 13 leaders priced 65%+ won 5. By stat lead size at day 21: small gap 8 of 16, middle 8 of 16, largest third 5 of 18. A bigger statistical lead did NOT mean a safer lead.
(Pooled rows reuse the same 50 awards at three dates, so they are not independent.)

## What the misses look like (exploratory, found after seeing winners)
- When the stat leader at day 21 lost (29 awards, winner in the field), the winner had the better team record in 21 and the higher scoring average in only 10. Voters lean on team success; a points/rebounds/assists score underweights it.
- Voter fatigue is not visible: a leader who had won the month before won 3 of 7, one who had not won 15 of 33.
- Late swings are common: the model's day-14 leader is still leading at month end in only 28 of 50, day-21 in 36 of 50.

## Charts
- `nba_potm_history_hold_rates_2026-11-14.png`: hold rate by checkpoint (left), implied vs realised (right).
- `nba_potm_history_race_examples_2026-11-14.png`: one month that held (Feb 2021-22 West, Dončić) and one late swing (Feb 2022-23 East, Antetokounmpo leading at 95% in the model, Brunson won). Both picked by a fixed rule (highest implied probability at day 14 among leads that held to month end / that lost), not by eye.

## Verdict for Olu (plain language)
1. Past months do NOT show a 70% favourite holding if the favourite is defined by stats. A leader the numbers called 77% won about 4 in 10, and that rate did not rise as the lead grew. No checkpoint, even day 28, was safe: the stat leader won only 40%.
2. The winner is usually in the top 2 by day 21 (62%) and top 3 (76%), so the field narrows but the pick inside it is not settled by the stat race.
3. Team record seems to decide close calls. A Kalshi 70c on a player is only fair if the market is pricing record and narrative, which this stats-only model cannot see. If the 70c favourite is a stats leader on a middling team, history says too dear. If the favourite is the top of a top team, this study is silent.
4. Olu's instinct (prices look fair, not much swinging) is right for the market, but the history here says the leader swings more than it feels like: 22 of 50 day-14 leaders were not leading by month end.
Not proven: n is 50, intervals are wide, the model is a weak stand-in for voters (it picks the winner at month end only 30%), and nothing here is a Kalshi price.

## Next, only if Olu wants it (no build)
Hold out 2018-19 and 2019-20 and test one voter-like rule decided now: among the stat top 3, the best team record leads. That is the one idea this study produced, and it was found in-sample, so it needs fresh seasons before anyone trusts it. About 15 minutes of public pulls.
Scripts and data: `~/edge-research/nba_potm_history_2026-11-14/` (analyze.py, report.py, pull_logs.py, mkfield.py).
