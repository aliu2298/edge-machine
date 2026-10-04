# Oddspedia NBA community consensus, 2025/26 — review

Source: oddspedia.com `/api/v1/` (robots.txt: `Allow: /api/v1/*`), seasonId 81604,
weeks 1-34. Pulled 2026-10-03.

  getLeagueInfo        -> 35 dated weeks (week 35 held no games)
  getMatchList         -> 1,327 games, 1,324 finished, final + quarter scores
  getTipsByConsensus?matchId=  -> archived consensus picks, works on past matches

9,527 consensus picks logged; 8,153 graded (the rest are 1H/1Q, Odd-Even and HT-FT
markets left UNGRADED rather than guessed at, because the pull kept only full-game
scores).

ODDS ARE BEST-ACROSS-BOOKMAKERS (`max_odd`), the most generous price available. That
makes the "do not follow" result stronger and any fade weaker: a fader pays the vig on
the other side, whose price this dataset does not carry.

## Headline

8,153 picks | 52.6% hit | 53.7% implied | ROI -2.17% | z -2.34

They lose to the price they were offered, on a large sample.

## By market

  Spread      3,938   51.3%   -2.04%   z -1.68
  Total       2,835   51.2%   -2.38%   z -1.48
  Moneyline   1,380   59.3%   -2.11%   z -0.71

## By consensus strength — the one real signal

  51-60%        549   +2.64%   z +0.40
  60-75%      3,241   -2.33%   z -1.59
  75-90%      1,897   +1.04%   z +0.75
  90-100%     2,466   -5.51%   z -3.25   <-- worst where they agree most

Splits of the 90-100% cell:
  odd weeks   1,165   -7.86%   z -2.66
  even weeks  1,301   -3.40%   z -1.95
  weeks 1-17  1,766   -8.91%   z -4.31
  weeks 18-34   700   +3.08%   z +0.76   <-- the one failure, on thin volume

Negative in three of four splits, and negative in BOTH halves of the odd/even split,
which is the better-controlled one because it removes the season trend.

## What failed

Over picks looked strong at -5.32% (z -2.53) but are a first-half artefact:
z -4.08 then +1.32. Spread and Total overall fall inside noise once split.

## Caveats

1. Best-odds pricing, as above.
2. Oddspedia's reference bookmakers, NOT Kalshi or Polymarket US. A fade validated here
   need not survive on the venues the bot can reach.
3. NO team totals and NO player props (PRA) exist anywhere in this dataset. Verified on
   an opening-night and a mid-season game: 9 archived markets, none a team total.
4. The 90-100% cell is the best of ~15 buckets looked at. It has not been put through a
   permutation correction, so it is a candidate, not a finding.
5. Volume collapses after week 25 (73, 114, 95, 43, 22, 18, 8, 6, 5 picks).
