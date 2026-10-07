# November 2025 result: all nine rules failed

Pre-registration: `RULES_november_2025.md`, committed 447e4ee0 BEFORE this data was
fetched. Data: `totals_2025-11.csv`, 219 games, 1-30 Nov, season 81604, all finished, all
with quarter scores and main lines on all three periods, zero fetch errors, zero ordering
violations (q1 <= h1 <= final on every row). 13 games went to overtime. Scored twice --
once in the browser, once independently in Python -- and the two agree to the decimal.

## The scorecard

| # | Rule | Oct over% | Nov over% | n | b/e | edge | ROI | z | Verdict |
|---|---|---|---|---|---|---|---|---|---|
| R1 | `q1_all`   | 58.2% | 50.2% | 219 | 52.3% | -2.1 | -3.91% | -0.62 | DEAD |
| R2 | `q1_even`  | 53.6% | 49.0% | 51 | 52.4% | -3.4 | -6.01% | -0.48 | DEAD |
| R3 | `q1_mis`   | 60.0% | 53.3% | 45 | 52.4% | +1.0 | +2.08% | +0.13 | survives, trivially |
| R4 | `h1_all`   | 63.7% | 48.4% | 219 | 52.6% | -4.2 | -7.95% | -1.24 | DEAD |
| R5 | `h1_even`  | 61.9% | 44.1% | 35 | 52.5% | -8.3 | -15.87% | -0.98 | DEAD |
| R6 | `h1_mis`   | 76.9% | 55.6% | 64 | 52.7% | +2.9 | +5.12% | +0.45 | survives, trivially |
| R7 | `fin_all`  | 58.8% | 47.9% | 219 | 51.5% | -3.6 | -7.04% | -1.07 | DEAD |
| R8 | `fin_even` | 65.4% | 46.5% | 43 | 51.5% | -5.0 | -9.57% | -0.66 | DEAD |
| R9 | `fin_mis`  | 66.7% | 47.1% | 68 | 51.6% | -4.6 | -8.90% | -0.76 | DEAD |

Seven of nine died on decision rule 4 -- direction must hold. They landed on the other side
of break-even from October, which kills them whatever the ROI. R3 and R6 cleared break-even
and beat their own unconditional rule, so they pass the mechanical tests; at z +0.13 and
+0.45 they are indistinguishable from nothing and are not findings.

## Why: the market was calibrated in November and had not been in October

                October               November
          line  actual   miss     line  actual   miss
  Q1     58.33   60.06  +1.74    58.79   58.87  +0.08
  1H    115.44  118.28  +2.83   116.56  116.70  +0.14
  Final 231.30  234.88  +3.57   232.45  233.06  +0.61

October's lines missed low by 1.7 to 3.6 points. November's missed by 0.08 to 0.61. The
flagship October figure -- the first-half over at 63.7%, z +2.46, the only thing in that
month above z 2 -- came back at 48.4%. The books were slow for eleven days and then they
were not, which is what an opening-fortnight artefact looks like and exactly what the
pre-registered weakness section said to expect.

## The spread did nothing again, and incoherently

November's own full gradient, each period on its own spread:

  Q1     even 49.0%   mild 54.1%   clear 45.2%   mismatch 53.3%
  1H     even 44.1%   mild 50.0%   clear 41.4%   mismatch 55.6%
  Final  even 46.5%   mild 54.4%   clear 43.1%   mismatch 47.1%

Not monotone in any period, so decision rule 3 fails everywhere. And the ordering does not
match October's: the `clear` band is the WORST of the four in all three periods here, while
in October it was the best for Q1 (72.7% -> 45.2%). Two months, two different orderings,
neither monotone. That is the signature of no effect.

## What I got wrong, recorded because it was written down first

The pre-registration predicted the band rules would fail and the unconditional rules had
the only chance. THE REVERSE HAPPENED: all three unconditional rules died and the only two
survivors are both mismatch bands. Given z +0.13 and +0.45 the honest reading is that both
survivors are noise rather than a signal I mis-called -- but the prediction was wrong in
direction and that is on the record.

The band-frequency extrapolation was also unreliable. Expected n against actual: R6 ~35 ->
64, R9 ~32 -> 68. November's spreads ran wider than October's, so the mismatch bands
roughly doubled. Projecting band frequencies from eleven days does not work.

## Standing conclusion

There is no NBA totals edge in this data, on any of the three periods, with or without a
spread condition. October's over bias was an opening-fortnight artefact and did not
survive its first out-of-sample month. Under decision rule 5 no re-banding or flipping is
permitted on this data, so the nine rules are closed.

What the two months DO establish, and it is worth keeping:

* The NBA totals market is well calibrated once the season settles -- 0.08 to 0.61 points
  of bias across 219 games. That is a much harder market than the niche cricket and
  Turkish-mismatch pockets this project has found edges in, and it argues against
  returning to NBA game and period totals without a genuinely new idea rather than a
  re-cut of this one.
* The dataset is reusable: 299 games across two months with main lines, best odds and
  three spreads per game, in `totals_2025-10.csv` and `totals_2025-11.csv`.

A third month would test nothing the second did not already answer: the direction rule has
already fired on seven of nine, and the two survivors are inside noise. Any further NBA
work should start from a different hypothesis, not from these bands.
