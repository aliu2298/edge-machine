# NBA star points and threes: buying players in form (Nov 18 2026)

**Verdict: no edge.** Buying a player whose last five games say more than his price loses, held to the end or sold into a
spike. The price already carries what recent form says. Build spec: none.

![Rules](nba_star_props/STARS_form.png)

![Price against form](nba_star_props/STARS_price.png)

## The idea
Players in form (Luka was the example: cheap before tip, 40 nearly every night, his threes spiking) should beat their price,
and their cheap contracts should trade up during the game even when they miss.

## What was tested
- **Games:** Oct 29 to Nov 16 2026, 133 games, 18 nights. Every player with 5+ games this season. 7,355 contracts.
- **Price:** the ask one hour before tip, contracts at 5c to 60c, bid-ask gap 5c or less. Fees charged.
- **In form:** the chance implied by his last 5 games is 8+ points above the ask.
- **Leader cue:** he was his game's top scorer in 3 or more of his last 5.
- **Two exits:** held to the end; or a resting sale at 2x or 3x, filled only on a later trade above the target.
- Rules were written before any price was read. Luka is shown apart because he prompted the idea.

## Results (return per contract after fees; player-games in brackets)

| Row | Held | Sold at 2x | Sold at 3x |
|---|---|---|---|
| Points, in form | -20% (387) | -21% (368) | -23% (306) |
| Points, in form + leader | -16% (43) | -23% (43) | -2% (37) |
| Points, same rule on the season average | -11% (266) | -12% (247) | -12% (187) |
| Points, every contract, no rule | -11% (1,550) | -19% (1,523) | -18% (1,443) |
| Threes, in form | -7% (378) | -13% (363) | -19% (309) |
| Threes, in form + leader | -6% (28) | -11% (27) | +11% (25) |
| Threes, same rule on the season average | -3% (245) | -7% (230) | -17% (183) |
| Threes, every contract, no rule | -5% (1,352) | -18% (1,314) | -24% (1,230) |
| Luka only, points, every contract | +63% (7) | +48% (7) | +92% (7) |
| Luka only, threes, every contract | +41% (7) | +54% (7) | +64% (6) |

- The in-form rows have the same sign in both parts of the window (to Nov 9, and Nov 10 to 16).
- The two leader rows above zero or near it rest on 25 and 37 player-games; neither is distinguishable from nothing.

## Why
- **Box scores, no prices:** where a player's last 5 ran 8+ points hotter than his season average, last 5 said 43%, the
  season average said 29%, and 29% happened (775 point contracts; threes 43% / 30% / 30%). The next game follows the season
  average, not the last five.
- **The price is right:** where last 5 said 54% and the ask was 33c, 28% landed. Where last 5 said 19% and the ask was 35c,
  35% landed.
- **Spikes:** in-form contracts reached double 41% (points) and 44% (threes) of the time; a fair contract can reach it at most
  50% of the time. Triple: 26% and 27% against 33%. Cheap contracts do not trade up more often than their price implies.
- **Beating the price does not carry over:** of 121 players, the best fifth to Nov 9 (+19 points a bet) made +0.2 from
  Nov 10 to 16.

## Luka
His 40+ ask went from 19-24c in October to 30-45c in November, and 40+ landed 7 of 12. His 5+ threes ask went from 32c to
about 50c, landing 10 of 12. He was cheap in October and the price has been catching up. Over this window he is 9th of 165
players at +17 points a bet; with no edge at all the luckiest of 165 would show about +23. One player cannot be told from luck.

## Also found
- Kalshi listed no star points or threes contracts before Nov 18 2025. This October is the only season opening it has priced,
  so an early-season catch-up cannot be checked on an earlier season.
- One lead, not a result: where the season average says 8+ above the ask and the last five do **not** (a cold run the price
  has followed down), held contracts made +17% on 72 player-games (points) and +22% on 64 (threes). It is the reverse of the
  form idea. It needs 100+ unseen player-games in each series before it means anything.

## Build spec
None. Rule: none. Scope: none. Nothing to retire or keep.
