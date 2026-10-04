# Twelve NBA totals rules, pre-registered 2026-10-03

Fixed BEFORE November 2025 data was fetched. Nothing below was chosen with knowledge of
the November result; every band, threshold and decision rule comes from October 2025 only
(80 games, 21-31 Oct, season 25/26) and from the data already in
`data/nba_oddspedia/totals_2025-10.csv`.

## What is being tested

October produced one finding that cleared its own standard error and several that did not:

* THE MONTH-WIDE OVER BIAS was real-looking. Over hit 58.2% on Q1, 63.7% on the 1st half
  (z +2.46 against 50%), 58.8% on the final and 55.0% on regulation, against a break-even
  of about 52%. The 1st half is the only figure in the whole October study above z 2.
* THE SPREAD DID NOTHING. |spread| correlated -0.038 to -0.070 with actual totals and
  +0.009 to +0.046 with the miss (actual minus line), all flat at n=80. The market shades
  totals down for mismatches (-0.17 to -0.22) and the residual after that shading is zero.
* THE BUCKET CELLS that looked strong -- Q1 clear 72.7%, 1H mismatch 76.9%, final mismatch
  66.7% -- are 11, 13 and 12 games. Against the month's own over rate in the same period
  they are all inside chance. The regulation table contradicts a mismatch story outright:
  its middle band went UNDER 10-6 (37.5%) while both ends went over.

So the twelve rules split into one that October supports and eight that October probably
does not, and the comparison between them is the point. If the band rules are only the
month bias in disguise, they will track their unconditional rule and add nothing.

## Settlement and pricing, identical to the October method

* THE BET IS ALWAYS THE OVER at the bookmaker's own MAIN line for that period, taken from
  Oddspedia `getMatchMaxOddsByGroup` marketGroupId=4, `odds[<period>].main`. Period 400 is
  the final including overtime, 402 the first half, 410 the first quarter.
* PRICE is the best available over price at that main line (`main.odds.o1`), the same
  generous convention October used. Stated plainly because it flatters every rule here:
  a single book would pay less.
* A PUSH VOIDS. Stake returned, the bet leaves the denominator. October had one (a Q1 line
  of 56 landing exactly 56).
* BREAK-EVEN is 100/price. At October's average of ~1.92 that is about 52.1%, so a rule
  must clear roughly 52% to make money, not 50%.
* THE SPREAD BANDS use each period's OWN main spread (marketGroupId=3): period 300 for the
  full game, 302 for the first half, 309 for the first quarter. Using the full-game spread
  for a quarter question was an error in the first October pass and is not repeated. Bands
  respect ties -- every game on the same spread lands in the same band.
* SAMPLE is every NBA game in November 2025 (1-30 Nov, Central-time calendar) with a final
  score and a main line for the period in question. Season 81604.

## The bands, fixed from October

    Q1    on |1Q spread|     even <=0.5   mild 1.0-1.5   clear 2.0-3.0   mismatch >=3.5
    1H    on |1H spread|     even <=1.0   mild 1.5-2.5   clear 3.0-4.5   mismatch >=5.5
    GAME  on |game spread|   even <=2.5   mild 3.5-5.5   clear 6.5-8.5   mismatch >=9.5

Final and Regulation share the game-spread bands and differ only in settlement.

## The twelve rules

Each row is: back the OVER on the period's main line, on every game meeting the condition.
`Oct` is October's over rate, `edge` its margin over break-even, `n_exp` the November games
expected from October's band frequency scaled to ~215 games.

| # | Rule | Period | Condition | Oct over% | Oct edge | n_exp |
|---|---|---|---|---|---|---|
| R1 | `q1_over_all`   | 1st quarter | every game | 58.2% (46-33) | +6.3pp | ~210 |
| R2 | `q1_over_even`  | 1st quarter | \|1Q spread\| <= 0.5 | 53.6% (15-13) | +1.9pp | ~78 |
| R3 | `q1_over_mis`   | 1st quarter | \|1Q spread\| >= 3.5 | 60.0% (6-4) | +7.6pp | ~27 |
| R4 | `h1_over_all`   | 1st half | every game | 63.7% (51-29) | +11.1pp | ~215 |
| R5 | `h1_over_even`  | 1st half | \|1H spread\| <= 1.0 | 61.9% (13-8) | +8.9pp | ~56 |
| R6 | `h1_over_mis`   | 1st half | \|1H spread\| >= 5.5 | 76.9% (10-3) | +24.3pp | ~35 |
| R7 | `fin_over_all`  | Final inc OT | every game | 58.8% (47-33) | +6.9pp | ~215 |
| R8 | `fin_over_even` | Final inc OT | \|game spread\| <= 2.5 | 65.4% (17-9) | +13.7pp | ~70 |
| R9 | `fin_over_mis`  | Final inc OT | \|game spread\| >= 9.5 | 66.7% (8-4) | +15.2pp | ~32 |
| R10 | `reg_over_all`  | Regulation | every game | 55.0% (44-36) | +3.2pp | ~215 |
| R11 | `reg_over_even` | Regulation | \|game spread\| <= 2.5 | 65.4% (17-9) | +13.7pp | ~70 |
| R12 | `reg_over_mis`  | Regulation | \|game spread\| >= 9.5 | 66.7% (8-4) | +15.2pp | ~32 |

R10-R12 settle on regulation only (overtime points stripped) against the SAME final line
the book published. That is not a bet anyone can place -- no book offers "regulation only"
at the full-game line -- and it is included as a DIAGNOSTIC, to separate a scoring effect
from an overtime effect. October's final-incl-OT over rate was 58.8% against regulation's
55.0%, and six of eighty games going to OT added 186 points between them. If R7 repeats
and R10 does not, the October over bias was mostly overtime.

## Pre-registered decision rules

Applied in this order, and decided on the November record alone.

1. **BREAK-EVEN.** A rule fails outright if its November over rate is below 100/avg price.
   Clearing it is necessary, not sufficient.

2. **THE BAND RULES MUST BEAT THEIR OWN UNCONDITIONAL RULE.** This is the whole test and
   the reason the unconditional rules are in the twelve. R2, R3 must beat R1; R5, R6 must
   beat R4; R8, R9 must beat R7; R11, R12 must beat R10 -- on over rate, in November. A
   band rule that merely clears break-even while its unconditional sibling does the same
   has shown nothing: it is the month bias with a smaller sample. October's band cells all
   fail this test retrospectively, which is why the expectation here is that they fail
   again.

3. **z >= 2 AGAINST THE PRICE** for an unconditional rule to be called a finding, computed
   as (overs - sum(1/price)) / sqrt(sum p(1-p)) on November's own bets. Not against 50%:
   against what the prices implied, which is the project's standard and about 52%.

4. **DIRECTION MUST HOLD.** A rule whose November over rate falls on the other side of
   break-even from October is dead, whatever its ROI. This is the test `nhl_dog_pl` failed
   when +15.7% became -3.7% and -6.8%, and the one `bund_o35_draw` failed when four of its
   seven lines flipped sign.

5. **NO RE-BANDING.** If a band misses, the answer is not a different band. The bands above
   are final for this test. Any re-cut is a new study on the same data and is recorded as
   such.

## Weaknesses, stated before the result

* OCTOBER IS THE WORST MONTH TO GENERALISE FROM. Eleven days, new rotations, books working
  from last season's priors. An over bias in the first fortnight is the most likely thing
  in sport to be an artefact, and November is exactly where it should die if it is one.
* MULTIPLICITY. Twelve rules on one month. At break-even roughly 52%, the best of twelve
  independent fair rules clears +10pp on n=30 about half the time. The unconditional rules
  at n~215 are far less exposed to this than the mismatch rules at n~30, so weight them
  accordingly and do not read R3, R6, R9 or R12 as findings on their own.
* BEST-ODDS PRICING, as above. Every ROI quoted is the most generous version.
* R10-R12 ARE NOT TRADEABLE. Diagnostic only.
* NOTHING HERE IS ON A VENUE THE BOT CAN REACH. These are Oddspedia's bookmakers. Kalshi
  has no NBA history at all and its totals book in preseason ran a 19c median spread
  against this study's ~2c implied cost. A rule that works here may be unplaceable.

## What would make this worth building

An unconditional over rule that clears z 2 in November as well as October, on the same
period, with the band rules adding nothing. That would say the 25/26 NBA totals market
opened too low and stayed too low -- a claim worth taking to a third month and then to a
venue check. Anything less is a month of noise and should be recorded as such.
