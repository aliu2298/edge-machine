# Soccer A6 and A7 review (Nov 12 2026)

Review only. No lane, page or Production change. The splits, the tests and the verdict rule were written down before any new result was read.

- **A6** (live): Premier League. A low-scoring, tight team against an attacking opponent: UNDER 2.5 goals, price 55c or less.
- **A7** (live): Champions League. Either team attacking and tight: OVER 3.5 goals, price 55c or less.

"Points" is the share of bets won minus the price paid. "Score" is the result over its error, with a match day counted as one outcome; 2 or more is the bar.

## Verdict

| Lane | Where it is now | Verdict |
|---|---|---|
| A6 | Live | **Recommend back to the Sandbox.** |
| A7 | Live | **Recommend back to the Sandbox.** |

No version 2. Moving them is Olu's decision.

**Why:**

- **Neither rule worked last season,** on Kalshi's own prices and matches it had never seen. A6 lost 17.8% on 71 bets. A7 lost 7.4% on 96, the same 2.1 points behind its price as every match.
- **A6 shows nothing in 13 seasons of bookmaker prices.** Its matches finished under 2.5 about 2 points less often than the price said, in both halves of the history.
- **This season's wins belong to every match, not to the labels.** Since Oct 18 every Premier League under at 55c or less has won 67% of the time at a 43.5c price. Every Champions League over 3.5 has beaten its price by 8 to 14 points since August. The rules add nothing on top.

## 1. Paper, honest fills and live

| Lane | Settled | Won v priced | Page | Honest fills | Live |
|---|---|---|---|---|---|
| A6 | 10 | 8 v 4.5 | +75.3% | +75.3% | +71.7% on 8 |
| A7 | 17 | 10 v 7.7 | +30.9% | +30.9% | +33.2% on 10 |

- Buy-and-hold bets at a quoted ask. No entry was refuted by the trade prints.
- **Live matches the simulator on every bet it took** (8 and 10). There is no paper v live gap.
- A6's record is 6 match days; A7's is 4. A6's score is 2.2, A7's 1.1.

## 2. A6 on bookmaker history

Premier League, 2013/14 to 2025/26. Matches fitting A6's label pair (labels from each team's last 10 league matches), against the closing under 2.5 price with the margin removed.

| Premier League | Matches | Under 2.5 | Price | Points |
|---|---|---|---|---|
| Every match, 2013/14 to 2020/21 | 2,914 | 47.7% | 48.2% | −0.5 |
| A6's pair, 2013/14 to 2020/21 | 562 | 46.1% | 48.0% | −1.9 |
| Every match, 2021/22 to 2025/26 | 1,876 | 43.2% | 44.6% | −1.4 |
| A6's pair, 2021/22 to 2025/26 | 394 | 42.4% | 44.7% | −2.3 |
| Every match, 2026/27 so far | 94 | 53.2% | 43.6% | +9.6 |
| A6's pair, 2026/27 so far | 15 | 80.0% | 44.3% | +35.7 |

- In 956 matches over 13 seasons the pair was a little worse than the price, never better.
- With the 55c price cap it reads −3.0 points, then −1.5.
- The same pair in La Liga, Serie A, the Bundesliga and Ligue 1: −0.8 points, then −1.8.
- **This season is the exception, for everyone.** Every Premier League match is running 9.6 points under the line. The pair's 12 of 15 sits inside that.

## 3. Both rules on Kalshi's own prices

Every listed match, the quote an hour before kickoff, tight books only, the quoted ask and the exchange's fee. Labels are worked out by the lane's own code from ESPN results.

### A6, Premier League under 2.5

| Period | The rule | Every other match at 55c or less |
|---|---|---|
| Last season (Nov 2025 to May 2026) | 71 bets, won 38.0% v 44.6c, **−17.8%** | 184 bets, about level with the price |
| Aug 1 to Oct 17 2026 | 9 bets, won 5, +21.7% | 54 bets, about level |
| Oct 18 on | 7 bets, won 5, +60.4% | 26 bets, won 65% v 43c |
| **All** | **87 bets, −7.4%, score −0.6** | – |

- Last season the rule was 6.6 points worse than its price and 8.5 points worse than every other match.
- Since Oct 18 the rule is 4.9 points ahead of every other match, a score of 0.2: the unders are winning across the league.
- This replay finds 9 qualifying matches in the window the rule was found on (5 won), where the original research found 11 (10 won). It reads one fixed hour before kickoff, so it is not the same pull.

### A7, Champions League over 3.5

| Period | The rule | Every match at 55c or less |
|---|---|---|
| Last season (Nov 2025 to Jul 2026) | 96 bets, won 37.5% v 39.6c, **−7.4%** | 136 bets, −5.9% |
| Aug 1 to Oct 17 2026 | 21 bets, +29.9% | 25 bets, +32.6% |
| Oct 18 on | 21 bets, +18.2% | 25 bets, +17.5% |
| **All** | **138 bets, +2.2%, score 0.2** | 186 bets, +2.4% |

- In every period the rule and every match move together. Over all of it the rule is 1.6 points ahead of the rest, which is nothing.
- The rule fires on 7 matches in 10 last season and 8 in 10 this season, so it is close to "every match" by construction.

## 4. Is any subset real?

No.

- **A6** (low side at home or away; price under 45c or 45c to 55c): all four cells lost.
- **A7** (one side or both; price under 35c or 35c to 55c; league phase, knockouts, qualifiers): nothing clears the correction. The best, one side only, is +12.4% on 75 with a score of 0.8.

## Limits

- **Kalshi history is one earlier season.** Its soccer totals start in Nov 2025.
- **Labels in the replays** come from ESPN league and Champions League results. Domestic cups and the other European cups are missing, and 48 of 592 matches had a side with no label (mostly early-round clubs from leagues ESPN does not list). The lane itself counts every competitive match.
- **A7 has no bookmaker history** in the files used here.
- **61 Kalshi events** could not be matched to an ESPN fixture and are left out.

## Build spec

For whoever builds. **No new lane and no version 2.**

- **Rules, scope, entry timing:** unchanged.
- **The one change from version 1:** none. No filter passed.
- **A6 and A7:** recommended stage is Sandbox paper, records kept. They are published by `PAIRS` in `soccer_rules_production.py`; taking them out is a Production move and needs Olu's go.
- **Retire or keep:** keep as paper until the read below, then retire unless they pass.

### Pre-registration text for the forward check

> A6 and A7, unchanged, Sandbox paper. Each is read once at 40 settled bets counted from Oct 18 2026.
> - A rule stays only if its points beat every other match of its competition, on the same market at 55c or less an hour before kickoff, by 5 or more over the same weeks.
> - Otherwise it is retired: the league's run, not the label, is what paid.
> - No price band, side or stage becomes a rule from that read.

## Files

Research folder: `~/edge-research/a6_a7_review_2026-11-12/` (the menu written in advance, the scripts and their output).
