# NBA game primer: what drives a game's flow, and how big each thing really is (Nov 17 2026, version 1)

Research only. Olu: "learn the game first… looking at the prices or creating filters is kind of pointless if you don't understand
the game." This is the first deliverable of the NBA plan. No price was used anywhere in it.

Each mechanism gets a plain explanation, a check on the data, and a label: **sizeable**, **small**, or **myth**. Only the
sizeable ones become filters.

**Version 1 is built from what is on disk: quarter scores and box scores for all 1,231 games of 2025-26 (and 68 of 2026-27).
Six items need play-by-play, which is not on disk. They are marked "needs play-by-play" and wait for an ESPN pull.**

![stage 0](nba_game_primer/NBA_stage0.png)

## The short list

| Mechanism | Label | The number |
|---|---|---|
| Three-point shooting luck | **Sizeable** | 8.5 points a team a game; explains a third of how far results land from expectation |
| Overall team strength, in every quarter | **Sizeable** | The better team gains 2.3 points a quarter in quarters 1 to 3, 1.1 in the fourth |
| Bench quality | **Sizeable** | Bench plus-minus carries (+0.69); the bench plays 39% of minutes |
| Pace | **Sizeable** for totals | Carries (+0.81); explains 29% of a game's total |
| Fast and slow starters (first quarter) | **Sizeable** | First-quarter net carries (+0.73) |
| Blowout minutes | **Sizeable** | Starters lose 5 minutes each in 30-point games; triple-double regulars drop from 20% to 12% |
| Triple-doubles and points leaders are a few players | **Sizeable** | Top 8 players have 63% of triple-doubles; carries (+0.94) |
| Trailing team in garbage time | **Small to sizeable** | A team 15+ down after three wins the fourth on points 56% |
| A favourite a little behind at half | **Small** | Wins the third quarter 64%, by 3.6 points; wins the game 56% |
| Rest (second night of a back-to-back) | **Small** | -1.5 points against a rested opponent; stars sit 9 points more often |
| Home court | **Small** | +1.7 points, 55% of wins; largest in the first quarter |
| Overtime in even matchups | **Small** | 6.1% against 4.4% overall |
| "A strong third-quarter team" | **Myth** | Does not carry (+0.19; nothing beyond overall strength) |
| Close-game teams, blowout teams | **Myth** | Do not carry (+0.03, +0.01) |
| End-game fouling lifts fourth-quarter totals | **Myth** | The fourth is the lowest-scoring quarter, in close games most of all |
| A star in foul trouble sinks the team | **Unclear** | 5 or 6 fouls in 8% of star games; team -2.9 points, but when the fouls came is not known |
| Rotation timing, runs and timeouts, luck fading inside a game, the bonus, when starters are pulled, clutch time, opening tip | **Needs play-by-play** | |

## 1. Strength shows in every quarter, and there is no special third quarter

A better team is better all game: more talent on the floor in every stint. The check: the team with the better recent record
(by 3+ points a game) outscores the other by 2.25 in the first quarter, 2.33 in the second, 2.26 in the third and 1.10 in the fourth
(823 games). The fourth is smaller because leaders rest starters and trailing teams press.

So the third quarter is not where favourites do something special. What Olu saw is real but has a simpler cause: a favourite that
is 1 to 9 behind at half is still the better team, so it tends to win what is left. It wins the third quarter 64% of the time by
3.6 points, and the game 56%. A favourite 10+ behind at half wins only 24%: by then the hole is real.

Which teams "own" the third quarter? None, reliably. A team's third-quarter record in its first 41 games says almost nothing about
its last 41 (+0.19), and nothing at all once overall strength is taken out (-0.09). **Myth as a team trait.**

## 2. Rotations and benches (timing needs play-by-play)

Coaches play starters about 31 minutes each and bring bench units in late in the first quarter and early in the second, then again
late in the third. Those bench minutes are where a deep team gains and a thin one bleeds.

- Starters play 62% of a team's minutes, the bench 39%.
- Bench quality is a stable trait: bench plus-minus carries from the first half of the season to the second (+0.69), bench scoring
  (+0.79) and the bench's share of minutes (+0.84) too.
- The gap between a team's bench and its starters also carries, more weakly (+0.42). Largest in 2025-26: Detroit, San Antonio and
  Denver had starters far better than their benches; Sacramento, Washington and Brooklyn the reverse.
- **Sizeable.** A team with a strong starting five and a weak bench should sag when the bench is on. Exactly when that is, minute
  by minute, **needs play-by-play** (substitution times).

## 3. Three-point shooting luck

Teams take about 37 threes a game. Whether they make 11 or 16 is mostly luck on the night, and each is worth 3 points.

- A team's threes land 8.5 points above or below its own season rate in a typical game.
- The gap in that luck between the two teams explains 34% of how far the final margin lands from what the teams' records expected.
  When the home team out-shoots its norm by 9+ points more than the visitor, it beats expectation by 9.6; the reverse, -13.2.
- It is luck, not form: it does not carry to the next game at all (0.00).
- **Sizeable; the largest single driver measured.** The open question for in-game prices: does a hot first half cool in the second?
  If it does, a favourite behind at half because the underdog shot the lights out is the best version of Olu's idea. **Needs
  play-by-play** (threes by half).

## 4. Fouls, the bonus, and the end of close games

Fouls matter three ways: a star who must sit, free throws once a team is in the bonus, and deliberate fouling by the trailing team
in the last minute.

- Stars (each team's top two scorers) finish with 5 or 6 fouls in 8% of their games. Their team does 2.9 points worse than expected
  in those games, but they do not play fewer minutes (+1.3), and physical, close games produce both fouls and poor results.
  **Unclear** until play-by-play shows when the fouls came.
- Deliberate fouling does not make fourth quarters high-scoring. With the game within 5 after three quarters the fourth averages
  54.1 points, against 57.7 for the first three quarters of the same games. The fourth is the slowest quarter in every game state.
  **Myth** for quarter totals.
- It does stretch final margins: half of the games that were within 5 after three quarters end 7 or more apart. That matters for
  win-margin and spread markets, not totals.
- The bonus and last-minute sequences **need play-by-play**.

## 5. Blowouts and comebacks

Once a lead is safe the coach sits the starters. The trailing team's bench then plays the leader's bench.

- Starters average 31.2 minutes in games decided by under 10, 27.5 in 20-point games, 25.8 in 30-point games.
- Fourth-quarter scoring does not change: 55.3 points when 20+ apart after three, 55.3 otherwise. **Myth** that garbage time is
  high-scoring.
- The trailing team does slightly win garbage time: 15+ down after three, it wins the fourth on points 56% of the time.
  **Small to sizeable** for a fourth-quarter spread.
- Comebacks are rare and not a team skill: a team 15+ down at half wins 6%, and wins the second half on points only 51% of the
  time. 15+ down after one quarter: 8%.
- The exact lead and time at which starters come out **needs play-by-play**.

## 6. Close games and overtime

- 14% of games end within 3 points, 29% within 6. Overtime is 4.4% of games.
- Matchup closeness matters a little: 6.1% of even matchups go to overtime, 3.9% of lopsided ones. **Small.**
- "Close-game teams" do not exist in the data: a team's rate of close games does not carry (+0.03), nor its overtime rate (+0.20).
  **Myth.**
- Clutch-time patterns and pre-game spreads **need play-by-play and the ESPN game summary**.

## 7. Rest and schedule

- Second night of a back-to-back against a rested opponent: 1.5 points worse than expected, 47% of wins (257 team-games). **Small.**
- Stars sit more on those nights: they play in 66% of them, against 75% of other games. That part is public before tip.
- When inactive news lands relative to tip is not in ESPN data and is not measured here.

## 8. Home court and pace

- Home teams win 55% and outscore visitors by 1.7 points; the edge is largest in the first quarter (+0.67). **Small.**
- Pace is a stable team trait (carries +0.81) and explains 29% of a game's total points; shooting explains the rest.
  Scoring efficiency carries too (+0.66). **Sizeable** for totals.
- First-quarter starts carry (+0.73), mostly because good teams are good early as well.
- Officiating crews: not on disk; only worth checking if the pull brings them.

## 9. Player specials

- Triple-doubles belong to a few players (Jokic in 52% of his games; the top 8 have 63% of all of them) and the rate carries
  strongly (+0.94). A triple-double needs minutes: 36.3 on average.
- Blowouts cut them: the regulars reach one in 20% of games decided by under 10 and 12% of games decided by 20+. **Sizeable.**
- The game's leading scorer is often the same few players (Gilgeous-Alexander and Doncic in over 70% of their games). **Sizeable.**
- Opening tip and first shot **need play-by-play**. Kalshi's first-basket market has no volume, so this is low priority.

## What this changes in the plan

Written into the pre-registration before any price was seen:
- The filter for Olu's favourite-dip idea is **overall strength** (a favourite 8+ points a game better), not third-quarter strength.
- **New filter: three-point luck at half.** The underdog's threes are 9+ points above its own rate at the break. Visible live from
  the halftime box score.
- Triple-double specialists get a second row that skips likely blowouts.
- No fourth-quarter total rule from fouling or garbage time. The trailing team on the fourth-quarter spread after a blowout stays.
- A rotation timing filter (bench stints) is left open until substitution times are measured.

## What the play-by-play pull would add

One ESPN request a game (about 1,460 for 2025-26 plus this season to date). It answers: when starters sit and return; how often
8-0 and 10-0 runs happen, in which quarters, and what follows a timeout; whether three-point luck fades inside a game; the bonus
and last-minute fouling; the lead and time at which starters are pulled; clutch time; pre-game spreads and officials.

Data and scripts: `~/edge-research/nba_quarters_2026-11-17/` (`stage0.py`, `stage0.md`, `primer_box.py`, `primer_box.md`, `PREREGISTERED.md`).
