# African qualifier legs (2026-11-16)

Olu's call, Nov 16 2026, relayed by the Edge Machine Coordinator. The every-match rows of the African qualifiers goals check are split into legs.
Every leg is a FILTER on entries the lane already logs (`africa_goals.leg_picks`): the same entry, the same price, the same result. Nothing is
re-entered and the pre-registered rows' own records are untouched.

**Entry (unchanged):** the ask on the hourly quote three hours before the ESPN kickoff, every AFCON qualifier Kalshi lists, held to settlement,
the exchange's taker fee, the fill simulator's QUOTED rule (a refuted ask is left out).

**Honesty about the evidence:** all of these splits were found on the Nov 12 to 14 window AFTER it was seen. They are post hoc. The paper
figures below are why they were picked, not proof. The evidence test was waived for the two Production legs (data/promotion_gate.json).

## Production (a trial at the default small stake, a fresh live record from the first live bet)

- **afq_dog_score** — YES on the underdog to score: the side whose to-score YES ask (KXAFCONTEAMTOTAL over 0.5) is under 60c.
  Paper: 14 of 21 at an average of 39c. September window: each side to score was 9.7 points underpriced on 91 sides. Follower band 2c to 60c.
- **afq_btts** — YES on both teams to score, every match (KXAFCONBTTS). Paper: 3 of 6 at 31c. September: 54.2% at 38.9c.
  Counts only matches after 18:30 UTC Nov 13 (the addendum of Nov 13).

## Sandbox paper, fresh records

- **afq_u35_80** — NO on over 3.5 goals only when the NO ask is 80c or more. Paper 7 of 7 on Nov 12 to 14; the SAME filter in the September
  window went 22 of 29 at 83c, about 10% under break-even. The two windows disagree, so it is NOT in Production until Olu says so.
- **afq_o15_v2** — YES on over 1.5 goals only when the favourite's to-score YES ask (the higher of the match's two) is 90c or more. In sample
  on the Nov 12 to 14 matches: about 12 of 13 (the ledger's own figure is shown on the row, not counted). Counts only matches that kick off
  on or after Nov 16 2026. The every-match over 1.5 row was +3.7%.
- **Controls (baselines, not lanes):** the favourite to score at 85c or more (14 of 15, break-even at that price) and NO on over 3.5 when the
  NO ask is under 80c.

## Retired Nov 16 by Olu: split into Production legs / v2

NO on over 3.5 every match (-17.8% on 24), YES on each side to score every match, YES on over 1.5 every match, and the pooled all-three row.
Their records stay on the page. The every-match both-teams-to-score row is the afq_btts leg.

## Idle by design

The window closes Nov 17 and Kalshi may list no African qualifier until the next window, about March 2027. The legs and the feed are built to
fire on their own then: the feed is valid and names no match in between.

## Read

No pre-set read for a Production leg beyond the usual: retire if the honest return is zero or below at the next window's end. Percentages only.
