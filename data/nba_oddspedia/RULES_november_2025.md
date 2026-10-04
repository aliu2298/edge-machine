# NBA totals rules, pre-registered 2026-10-03

Fixed BEFORE November 2025 data was fetched. Every band, threshold and decision rule comes
from October 2025 only (80 games, 21-31 Oct, season 25/26) and from
`data/nba_oddspedia/totals_2025-10.csv`.

## Three periods

First quarter, first half, and final INCLUDING OVERTIME. There is no regulation-only set:
a totals bet settles including overtime, so regulation-only is not a bet anyone can place
and has no business being a rule. The `ot` column stays in the dataset so the overtime
question can still be asked of the data, but it is not dressed up as a rule.

Nine rules: for each period, the unconditional over plus the two band extremes. Three
slots remain open to reach twelve -- see the note at the end.

## What is being tested

October produced one figure above its own standard error, and a lot that were not:

* THE MONTH-WIDE OVER BIAS looked real. Over hit 58.2% on Q1, 63.7% on the first half and
  58.8% on the final, against a break-even near 52%. The first half at z +2.46 against 50%
  is the only figure in the whole October study above z 2.
* THE SPREAD DID NOTHING. |spread| correlated -0.038 to -0.070 with the actual totals and
  +0.009 to +0.046 with the miss (actual minus line) -- flat on all three periods at n=80.
  The market shades totals down as the mismatch widens (-0.17 to -0.22) and the residual
  after that shading is zero.
* THE CELLS THAT LOOKED STRONG are small and do not order themselves. Q1 clear 72.7% is
  8-3 on eleven games; 1H mismatch 76.9% is 10-3 on thirteen. Read against the month's own
  rate in the same period, both sit inside chance. October's four bands ordered themselves
  in none of the three periods: Q1 ran 53.6, 56.7, 72.7, 60.0; the half 61.9, 62.1, 58.8,
  76.9; the final 65.4, 53.8, 50.0, 66.7.

## Settlement and pricing, identical to the October method

* THE BET IS ALWAYS THE OVER at the bookmaker's own MAIN line for that period, from
  Oddspedia `getMatchMaxOddsByGroup` marketGroupId=4, `odds[<period>].main`. Period 400 is
  the final including overtime, 402 the first half, 410 the first quarter.
* PRICE is the best available over price at that main line (`main.odds.o1`) -- the same
  generous convention October used. Stated plainly because it flatters every rule here: a
  single book would pay less.
* A PUSH VOIDS. Stake returned, bet leaves the denominator. October had one (a Q1 line of
  56 landing exactly 56).
* BREAK-EVEN is 100/price, computed per rule from that rule's own average price. It runs
  51.5% to 53.0%, so a rule must clear roughly 52%, not 50%.
* BANDS USE EACH PERIOD'S OWN MAIN SPREAD (marketGroupId=3): period 300 for the full game,
  302 for the first half, 309 for the first quarter. Using the full-game spread for a
  quarter question was an error in the first October pass and is not repeated. Bands
  respect ties, so games on the same spread cannot land in different bands -- a defect in
  the first quartile-by-rank cut, where |1Q spread| 0.5 appeared in two bands at once.
* SAMPLE is every NBA game in November 2025 (1-30 Nov, Central-time calendar) with a final
  score and a main line for the period in question. Season 81604.

## The bands, fixed from October

    Q1    on |1Q spread|     even <=0.5   mismatch >=3.5
    1H    on |1H spread|     even <=1.0   mismatch >=5.5
    FINAL on |game spread|   even <=2.5   mismatch >=9.5

(The mild and clear bands between them are not rules here. October's figures for them are
on record in this file's history and in the CSV, so adding them later is a stated choice
rather than a rescue.)

## The nine rules

Each is: back the OVER on that period's main line, on every November game meeting the
condition.

| # | Rule | Period | Condition | Oct O-U-P | Oct over% | b/e | Oct edge | n_exp |
|---|---|---|---|---|---|---|---|---|
| R1 | `q1_all`   | 1st quarter | every game | 46-33-1 | 58.2% | 51.9% | +6.3pp | ~210 |
| R2 | `q1_even`  | 1st quarter | \|1Q sp\| <= 0.5 | 15-13-1 | 53.6% | 51.7% | +1.9pp | ~78 |
| R3 | `q1_mis`   | 1st quarter | \|1Q sp\| >= 3.5 | 6-4-0 | 60.0% | 52.4% | +7.6pp | ~27 |
| R4 | `h1_all`   | 1st half | every game | 51-29-0 | 63.7% | 52.6% | +11.1pp | ~215 |
| R5 | `h1_even`  | 1st half | \|1H sp\| <= 1.0 | 13-8-0 | 61.9% | 53.0% | +8.9pp | ~56 |
| R6 | `h1_mis`   | 1st half | \|1H sp\| >= 5.5 | 10-3-0 | 76.9% | 52.6% | +24.3pp | ~35 |
| R7 | `fin_all`  | Final inc OT | every game | 47-33-0 | 58.8% | 51.8% | +6.9pp | ~215 |
| R8 | `fin_even` | Final inc OT | \|game sp\| <= 2.5 | 17-9-0 | 65.4% | 51.7% | +13.7pp | ~70 |
| R9 | `fin_mis`  | Final inc OT | \|game sp\| >= 9.5 | 8-4-0 | 66.7% | 51.5% | +15.2pp | ~32 |

## Pre-registered decision rules

Applied in this order, on the November record alone.

1. **BREAK-EVEN.** A rule fails outright below 100/avg price for its own cell. Necessary,
   not sufficient.

2. **EVERY BAND RULE MUST BEAT ITS OWN UNCONDITIONAL RULE.** R2 and R3 must beat R1, R5 and
   R6 must beat R4, R8 and R9 must beat R7 -- on over rate, in November. This is the whole
   test and the reason the unconditional rules are in the nine. A band that merely clears
   break-even while its unconditional sibling does the same has shown nothing: it is the
   month bias with a smaller sample, which is what every October band cell turns out to be
   when read against the month's own rate.

3. **z >= 2 AGAINST THE PRICE** for an unconditional rule to be called a finding, computed
   as (overs - sum(1/price)) / sqrt(sum p(1-p)) on November's own bets. Not against 50%:
   against what the prices implied, which is the project's standard.

4. **DIRECTION MUST HOLD.** A rule landing on the other side of break-even from October is
   dead whatever its ROI. This is the test `nhl_dog_pl` failed when +15.7% became -3.7%
   and -6.8%, and `bund_o35_draw` failed when four of seven lines flipped sign.

5. **NO RE-BANDING, NO FLIPPING.** If a band misses, a different band is a new study on the
   same data and is recorded as such. A losing cell is not re-read as an under.

## Weaknesses, stated before the result

* OCTOBER IS THE WORST MONTH TO GENERALISE FROM. Eleven days, new rotations, books working
  from last season's priors. An over bias in the first fortnight is among the likeliest
  things in sport to be an artefact, and November is exactly where it should die.
* MULTIPLICITY. Nine rules on one month. At a 52% break-even the best of nine fair rules
  clears +10pp on n=30 a large share of the time by luck alone. R3, R6 and R9 run at n~30
  and cannot be findings on their own whatever they print. R1, R4 and R7 at n~215 are the
  figures that carry weight.
* BEST-ODDS PRICING. Every edge quoted is the most generous version.
* NOTHING HERE IS ON A VENUE THE BOT CAN REACH. These are Oddspedia's bookmakers. Kalshi
  holds no NBA history at all and its preseason totals book ran a 19c median spread against
  this study's ~2c implied cost. A rule that works here may be unplaceable, which is the
  cricket lesson: a pair promoted on +142.8% over 30 bets where only the 11 reachable ones
  carried it.

## What would make this worth building

An unconditional rule that clears z 2 in November as well as October, on the same period,
with the band rules adding nothing. That would say the 25/26 NBA totals market opened too
low and stayed too low -- worth a third month and then a venue check. Anything less is a
month of noise and gets recorded as such.

## The three open slots

Nine rules follow from three per period across three periods. Three slots are unfilled.
They are NOT being filled by guesswork: the candidates on the table are the mild and clear
bands (which would complete each period's gradient), a first-quarter-to-first-half
carry-over condition, or an OT-frequency rule on the final. That is the owner's choice and
is left open rather than decided here.
