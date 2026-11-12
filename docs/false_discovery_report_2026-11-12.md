# Too many tests, too few bets: the false-discovery check (Nov 12 2026)

`fdr_check.py` reads every lane the ledgers hold, active or retired, and asks how many still look good once luck across all of them is counted. Lanes re-graded by the fill simulator are read at their honest figure. No page and no ledger was changed.

Returns are per bet after fees. "Outcome" means one independent result: a day, a slate, a mention week.

## What we found

1. **Nothing clears.** 173 lanes hold 6,371 settled bets. 119 have 10 or more bets. One has a score of 2 or better (soccer rule A6, on 10 bets). Luck alone would give about three. After correcting for the number of lanes, none clears, in the Sandbox or in Production.
2. **The Sandbox as a whole looks like a fair market minus fees.** 43 of the 119 lanes are up. 76 are down. The average score is slightly below zero.
3. **Lanes fall back when they go live.** 11 lanes went live with at least 5 paper bets behind them. Before: +31% on average. After, live: −7% on 158 bets. Four of the 11 stayed up.
4. **30 bets cannot find a normal edge.** One bet's return swings by about 87%. A real +10% edge shows a score of 2 only 9% of the time at 30 bets, against 2% for no edge at all. It needs about 600 bets to show reliably. A +20% edge needs about 150.
5. **So a good-looking lane at 30 bets is usually luck.** If one idea in ten is real, about 3 in 10 lanes that reach a score of 2 at 30 bets are real.

## How many tries

Lanes that left a record, by idea. "Pooled" is every bet of the idea as one record.

| Idea | Lanes | With 10+ bets | Active | Score 2+ | Clear | Bets | Pooled |
|---|---|---|---|---|---|---|---|
| Soccer form and price rules (tracker) | 44 | 27 | 18 | 0 | 0 | 806 | −8.2% |
| Soccer total-goals label rules | 27 | 10 | 16 | 1 | 0 | 254 | −8.0% |
| Tipsters and outside models | 23 | 17 | 0 | 0 | 0 | 954 | −7.3% |
| Cheap side with early sells | 14 | 11 | 3 | 0 | 0 | 468 | −0.7% |
| NBA label and value rules | 12 | 12 | 0 | 0 | 0 | 396 | −10.4% |
| Tennis, fights and US sports bands | 11 | 11 | 0 | 0 | 0 | 1,151 | −1.7% |
| Commodity and economic ladders | 10 | 7 | 6 | 0 | 0 | 1,357 | +0.6% |
| Soccer team-total label rules | 9 | 8 | 6 | 0 | 0 | 166 | −3.6% |
| Culture (mentions, films, albums) | 7 | 4 | 2 | 0 | 0 | 192 | +3.0% |
| Crypto price bands | 6 | 4 | 1 | 0 | 0 | 127 | −1.3% |
| Goalless dips and cheap NO | 4 | 3 | 4 | 0 | 0 | 91 | +1.3% |
| NFL team totals | 3 | 2 | 0 | 0 | 0 | 115 | −6.6% |
| NBA win margin | 2 | 2 | 2 | 0 | 0 | 241 | +8.2% |
| Tennis totals | 1 | 1 | 0 | 0 | 0 | 53 | −9.9% |

Variants tried in research before, or instead of, a lane. These come from the pre-registration docs and research notes, and are context only:

| Idea | Variants tried | Lanes built | Cleared |
|---|---|---|---|
| Soccer spread, correct score and NO shapes | 8,118 | 1 | 0 |
| Streak and lead rules | 655 | 2 | 0 |
| Kalshi Invest big moves | 648 | 4 | 0 |
| Rebound after a slide | 56 | 0 | 0 |
| 15-minute markets, ask by minute and price | 49 | 3 | 0 |
| Nasdaq and gold opening breakouts | 40 | 6 | 0 |
| NBA win margin v5 grid | 21 | 2 | 0 |
| Cheap side by Kalshi category | about 26 | 9 | – |
| Soccer total-goals label angles | 21 | 21 | – |

## The closest lanes

Paper record (honest where re-graded). "Score" is the return over its error, with a whole outcome counted once.

| Lane | Stage | Bets | Outcomes | Return | Score | Older half / newer half | Without its best outcome |
|---|---|---|---|---|---|---|---|
| Soccer rule A6 | Production | 10 | 6 | +75.3% | 2.18 | +111.8% / +38.9% | +62.3% |
| Under 3.5 low scoring, internationals | Production | 17 | 7 | +27.2% | 1.89 | +35.9% / +23.6% | +28.2% |
| Crypto below band | Production | 41 | 24 | +15.8% | 1.80 | +15.4% / +16.2% | +13.5% |
| NBA win margin NO fade | Production | 117 | 9 | +8.2% | 1.53 | +13.3% / +1.3% | +6.0% |
| Commodities favourite band | Sandbox | 68 | 23 | +9.5% | 1.42 | +22.1% / −1.0% | +8.0% |
| MLS fade home | Production | 28 | 12 | +20.6% | 1.26 | +26.4% / +12.9% | +11.9% |
| Team-total rule T1 | Sandbox | 52 | 12 | +17.1% | 1.08 | +9.9% / +23.2% | +3.9% |
| Team 2+ ranked | Production | 27 | 18 | +20.4% | 1.03 | +30.0% / +12.7% | +13.9% |
| NBA win margin YES split | Production | 124 | 8 | +8.2% | 0.79 | +26.9% / −17.8% | +1.4% |

Live records, on their own:

| Lane | Live bets | Outcomes | Return | Score |
|---|---|---|---|---|
| NBA win margin NO fade | 86 | 9 | +15.8% | 2.37 |
| NBA win margin YES split | 120 | 9 | +18.9% | 1.82 |
| Crypto below band | 16 | 16 | +24.1% | 1.69 |
| Commodities favourite band (pulled) | 25 | 17 | +11.5% | 1.00 |
| MLS fade home | 18 | 8 | +14.0% | 0.59 |
| Team 2+ ranked | 23 | 16 | +9.1% | 0.41 |

None of these clears once the 17 live records are corrected together. The NBA NO fade is the strongest thing on the site: positive on paper, on the simulator and live. It has run 9 nights.

### Went live: before and after

| Lane | Paper before | Live after |
|---|---|---|
| Eredivisie draw | +52.0% (5) | −4.3% (17) |
| Under 3.5 low scoring, clubs | +44.9% (5) | −13.1% (21) |
| MLS fade home | +33.0% (10) | +14.0% (18) |
| Crypto below band | +31.8% (6) | +24.1% (16) |
| Bundesliga over 3.5 | +30.7% (7) | −42.4% (10) |
| Soccer rule A7 | +27.6% (7) | +33.2% (10) |
| Team 2+ form | +23.6% (5) | −13.2% (17) |
| Congestion under 2.5 | +23.4% (24) | −40.7% (12) |
| Team-total rule T1 | +22.4% (18) | −28.5% (6) |
| Soccer rule D3 | +22.0% (16) | +5.1% (15) |
| BTTS form fade | +18.0% (11) | −30.8% (16) |
| **All, weighted by live bets** | **+31.3%** | **−7.0% (158)** |

## Proposed promotion gate

The aim is fewer lanes, more bets on each, and no promotion on luck. Retiring stays as it is: any time, at 10 bets or more.

**Step 1: Sandbox to a live trial at the smallest stake.** All of:

- The rule and its baseline were written down before the record began. One headline variant per idea.
- If it rests an order or sells early, the record is the fill simulator's strict figure.
- 30 or more settled bets, on 10 or more separate outcomes.
- Up in both halves, and still up with its best outcome removed.
- Beats its baseline.
- Score of 2 or better.

A lane that passes is on trial, not proven. Most lanes that pass step 1 will still be luck (finding 5).

**Step 2: trial to proven. Needed before any stake rise.** All of:

- A fresh record from the day it went live. 100 or more live bets on 20 or more outcomes.
- Live score of 2 or better on that record alone, and up in both halves.
- Live return inside the simulator's range (strict to touch), so the fills are understood.
- Clears the Sandbox-wide check (`fdr_check.py`) on its whole record.

**During the trial.** Read at 20, 50 and 100 live bets only. Pull it if it is down at 50, or below −20% at 20.

**Budget.** A lane that cannot reach 100 bets in three months is pooled with its sister lanes or dropped.

### Where today's lanes stand on step 1

No active lane passes. The nearest:

| Lane | What is missing |
|---|---|
| Crypto below band (41 bets) | Score 1.80, needs 2 |
| Team-total rule T1 (52 bets) | Score 1.08 |
| NBA win margin NO fade (117 bets) | 9 outcomes, needs 10; score 1.53 on paper (2.37 live) |
| Commodities favourite band (68 bets) | Newer half is down; score 1.42 |
| MLS fade home (28 bets) | 2 bets short; score 1.26 |
| Team 2+ ranked (27 bets) | 3 bets short; score 1.03 |
| Soccer rule A6 (10 bets) | 20 bets and 4 outcomes short |

## How the check works

- **Score.** Mean return over its standard error. The error is the larger of the plain one and one that lets a whole outcome move together. It is never smaller than a fair lane of the same shape would have: without that floor, 15 wins out of 15 at 93c scored 9, when it happens one time in three.
- **Correction.** Two ways, which agree. Benjamini-Hochberg across every lane with 10 or more bets. And a shuffled Sandbox: each outcome's result is flipped at random, 2,000 times, and a lane must beat the best lane of the shuffled site. That best lane scores 2.5 in a typical shuffle and 3.6 one time in ten.

## Limits

- The 15-Minute and Trading lanes are not in the check: two days of data, or no per-bet ledger.
- The research-variant counts are hand-entered from docs and notes. They are not used in the correction, which is why the correction is, if anything, too kind.
- Paper and live records of one lane are the same bets, so they cannot be added together.
- Whole-ledger history is used, not each lane's record since its last reset.

## Tools

`fdr_check.py` (the check, families, shrinkage, power, step 1 of the gate), `test_fdr_check.py`.

```bash
python3 fdr_check.py --regrade regrade.json
```
