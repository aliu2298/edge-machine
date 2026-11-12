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

## The promotion gate (adopted Nov 12)

Olu's decision: the honest figure is a gate only. Pages do not change, and no honest or "if touches fill" figure is shown on them.

**The rule.** A lane may move from the Sandbox to Production only if, on its own entries graded by the fill simulator's strict rules:

1. Its return after fees is positive. Nothing waives this.
2. It passes the evidence test: 30 or more settled bets on 10 or more separate outcomes, up in both halves, still up without its best outcome, and a score of 2 or better. Olu can waive this test for a named lane; the waiver (who, when, why) is written into that lane's record.

**How it is enforced.** `test_promotion_gate.py` runs on every pull request. It lists every lane the code puts in Production and fails if one has no passing record in `data/promotion_gate.json`. A promotion is a code change, so it cannot merge without its record. A new Production feed the gate does not know also fails the test.

**How a lane is graded.**

- A lane that rests an order or sells early: the simulator's strict rules, from trade prints.
- A buy-and-hold lane: every bet at its logged price and the exchange's real fee, less any bet whose price the trade prints refute. The record also counts how many bets the prints confirmed.

**To promote a lane:**

```bash
python3 promotion_gate.py check "source|scope"
```

That writes the lane's honest figure to the record. The "if touches fill" figure is kept there as a note only; the gate never reads it.

**Lanes already live** are not pulled by the gate. Two of them fail rule 1 today, and both are for Olu to decide:

| Live lane | Honest return | Bets |
|---|---|---|
| Soccer rule C3 (Serie A over 2.5) | −16.9% | 4 |
| T1-M (T1 matches, over 3.5) | −17.6% | 2 |

Every other live lane has a positive honest return. None of the 23 passes the evidence test yet:

| Live lane | Page | Honest | Bets (confirmed) | Outcomes | Score |
|---|---|---|---|---|---|
| Soccer rule A6 | +75.3% | +75.3% | 10 (9) | 6 | 2.18 |
| Under 3.5 low scoring, internationals | +27.2% | +27.2% | 17 (10) | 7 | 1.89 |
| Crypto below band | +15.8% | +15.5% | 40 (29) | 24 | 1.73 |
| Soccer rule C4 | +60.8% | +60.8% | 6 (6) | 5 | 1.54 |
| NBA win margin NO fade | +5.7% | +8.2% | 117 | 9 | 1.53 |
| MLS fade home | +20.6% | +20.6% | 28 (24) | 12 | 1.26 |
| Team 1 form, internationals | +19.7% | +19.7% | 7 (5) | 4 | 1.18 |
| Team-total rule T7 | +17.7% | +17.7% | 12 (1) | 5 | 1.15 |
| Soccer rule A7 | +30.9% | +30.9% | 17 (17) | 4 | 1.08 |
| S&P 500 near-certain NO | +7.5% | +7.5% | 15 (15) | 15 | 1.06 |
| Argentina goalless dip | +52.5% | +53.7% | 2 | 2 | 1.04 |
| Team 2+ ranked | +20.4% | +20.4% | 27 (22) | 18 | 1.03 |
| Under 3.5 low scoring, cups | +48.8% | +48.8% | 2 (0) | 2 | 0.99 |
| T1-H | +47.5% | +47.5% | 2 (1) | 2 | 0.97 |
| UCL corners fade | +28.3% | +28.3% | 6 (3) | 4 | 0.94 |
| First team to score NO 70-80 | +16.3% | +16.3% | 8 (1) | 4 | 0.80 |
| NBA win margin YES split | +11.8% | +8.2% | 124 | 8 | 0.79 |
| Soccer rule A3 | +27.1% | +27.1% | 2 (1) | 2 | 0.74 |
| Soccer rule A2 | +28.7% | +28.7% | 4 (4) | 4 | 0.67 |
| Economic daily, near-certain YES | +4.4% | +4.4% | 9 (9) | 8 | 0.63 |
| Team 2+ form, internationals | +21.8% | +21.8% | 1 (1) | 1 | 0.47 |
| T1-M | −17.6% | −17.6% | 2 (2) | 2 | −0.21 |
| Soccer rule C3 | −16.9% | −16.9% | 4 (4) | 4 | −0.35 |

Sandbox lanes graded so far: commodities favourite band +8.2% honest on 64 (newer half down), Eredivisie draw +22.6% on 29, T1 +17.1% on 52, top-5 dip +7.7% on 32. Each has a positive return and fails the evidence test, so each would need a waiver to go live.

### Still proposed, not adopted

- **Proven status before a stake rise:** a fresh live record of 100 or more bets on 20 or more outcomes, a live score of 2 or better, live return inside the simulator's range, and clearing the Sandbox-wide check.
- **Trial reads** at 20, 50 and 100 live bets only; pull the lane if it is down at 50.

## How the check works

- **Score.** Mean return over its standard error. The error is the larger of the plain one and one that lets a whole outcome move together. It is never smaller than a fair lane of the same shape would have: without that floor, 15 wins out of 15 at 93c scored 9, when it happens one time in three.
- **Correction.** Two ways, which agree. Benjamini-Hochberg across every lane with 10 or more bets. And a shuffled Sandbox: each outcome's result is flipped at random, 2,000 times, and a lane must beat the best lane of the shuffled site. That best lane scores 2.5 in a typical shuffle and 3.6 one time in ten.

## Limits

- The 15-Minute and Trading lanes are not in the check: two days of data, or no per-bet ledger.
- The research-variant counts are hand-entered from docs and notes. They are not used in the correction, which is why the correction is, if anything, too kind.
- Paper and live records of one lane are the same bets, so they cannot be added together.
- Whole-ledger history is used, not each lane's record since its last reset.

## Tools

`fdr_check.py` (the check, families, shrinkage, power, the evidence test), `test_fdr_check.py`.
`promotion_gate.py` (the gate and its record), `test_promotion_gate.py` (the enforcement).

```bash
python3 fdr_check.py --regrade regrade.json
```
