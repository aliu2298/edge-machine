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

## The screen: who beats the pre-tip price?
Asked for after the rule test: which players beat or spike over their pre-tip prices often, and under what conditions.
All 27 nights from Oct 20 to Nov 16, contracts at 5c to 60c, one number a player-game. Descriptive, not a rule test.

![Leaderboard](nba_star_props/STARS_leaderboard.png)

- **The number of beaters is what luck gives.** Points: 22 players at +10 points a bet or better; shuffling players across
  the same games gives 22 (16 to 28). Threes: 26 against 20 (15 to 26). The spread between players equals the luck spread.
- **Spike leaders are the same story.** Points: 9 players at +15 over fair against 11 by luck. Threes: 5 against 3.

![Persistence](nba_star_props/STARS_persist.png)

- **Beaters do not keep beating.** To Nov 6 against Nov 7 to 16: correlation -0.10 (points, 148 players) and -0.09 (threes,
  129). The top 20 to Nov 6 averaged +22, then -2 (points); +21, then -6 (threes).

![Spike examples](nba_star_props/STARS_spikes.png)

### Conditions
Every player pooled (points; threes read the same way). Excess is landed minus the ask, in points a bet.

| Condition (known before the game) | Player-games | Excess | Spike against fair |
|---|---|---|---|
| Home | 1,258 | -1.7 | -6.4 |
| Away | 1,228 | -1.8 | -6.1 |
| Second night of a back-to-back | 412 | -0.4 | -2.8 |
| Opponent leaky (worst third) | 550 | -3.8 | -9.5 |
| Opponent stingy (best third) | 546 | -2.9 | -9.5 |
| A top-2 scorer on his team is out | 1,535 | -1.4 | -5.8 |
| Team favoured by 8+ | 433 | -1.7 | -5.9 |
| Team an underdog by 8+ | 365 | -2.2 | -7.8 |
| Top scorer of his game in 3+ of last 5 | 67 | -1.8 | -2.0 |
| Minutes up 4+ on last season | 121 | +2.7 (t 0.9) | -5.8 |
| Scoring up 3+ on last season | 138 | -1.4 | -8.9 |

No condition is above zero by more than noise.

The top 10 point beaters (Davion Mitchell, Brook Lopez, Daniss Jenkins, Luka, Klay Thompson, Saddiq Bey, Tre Jones, Scottie
Barnes, Duncan Robinson, Ajay Mitchell), 113 games:

| Condition | Their games | Their excess |
|---|---|---|
| Home / away | 55 / 58 | +28 / +15 |
| Back-to-back / rested | 19 / 94 | +17 / +22 |
| Leaky / stingy opponent | 19 / 19 | +11 / +25 |
| Top-2 teammate out / in | 93 / 20 | +19 / +31 |
| Favoured by 5+ / close / underdog by 5+ | 38 / 59 / 16 | +21 / +20 / +28 |
| Played 32+ minutes / under 28 | 49 / 48 | +29 / +12 |

- Their beats are spread across every condition; none of the splits is large for its count.
- What most of them share is a bigger role than last season (Davion Mitchell 16.7 points a game against 9.3, Luka 39.0
  against 33.5, Barnes 24.2 against 18.1, Ajay Mitchell 20.1 against 13.6). But across every player, "scoring up on last
  season" seen before the game does not beat the price: once the rise is visible, the price has it.
- By team (its players' contracts): best Detroit +6.5, worst Milwaukee -8.4; the size expected from 30 teams.

Not pulled: rebounds, assists and points+rebounds+assists (about 630 requests each), team totals (about 250 to 420 a series).

## Lists by category: who beat their pre-tip price
Points, threes, rebounds, assists, and points + rebounds + assists. Same format in each: the ask one hour before tip, contracts
at 5c to 60c, one number a player-game, players with 8+ games. "Luck at this rank" is what the player in that rank shows when
players are shuffled across the same games. Descriptive, not a rule test.

![Lists](nba_star_props/STARS_lists.png)

- **Across all five categories 9 players are clear of chance (t of 2 or better); luck gives 9.**
- The best player in each category is inside what the luckiest player shows.
- Early leaders fall back in every category: the top 20 to Nov 6 made +15 to +22, then -2 to -6.
- Davion Mitchell is near the top of three lists (points, threes, assists) and stayed above zero after Nov 6 on 5 games. His
  minutes rose from 29 to 36 a game. One player; a watch, not a rule.

Contracts at 5-60c an hour before tip. Excess = share landed minus the ask, points a bet, one number a player-game. t = by game. Spike = traded above double after tip, against the fair ceiling (half).

### POINTS: 2486 player-games, 171 players with 8+ games; every contract -1.8 a bet

- Players at t 2 or better: **1**; luck alone gives 2 (0 to 4). At +10 or better: 22; luck 22 (16 to 28).
- Do they keep it? To Nov 6 v Nov 7-16: correlation -0.10 (148 players); top 20 early +22, then -2.
- Contracts at 49c or less traded above double 44% of the time (fair ceiling 50%).

| # | Player | Games | Paid | Landed | Excess | t | Luck at this rank | To Nov 6 | Nov 7-16 | Spike v fair |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | Davion Mitchell (MIA) | 14 | 25c | 57% | +32 | +3.6 | +27 (+21 to +38) | +38 (9) | +21 (5) | +19 |
| 2 | Brook Lopez (LAC) | 11 | 27c | 53% | +26 | +1.9 | +24 (+19 to +31) | +25 (7) | +27 (4) | +14 |
| 3 | Daniss Jenkins (DET) | 10 | 28c | 52% | +24 | +1.5 | +22 (+18 to +28) | +13 (6) | +39 (4) | +10 |
| 4 | Luka Dončić (LAL) | 12 | 33c | 53% | +20 | +1.5 | +20 (+17 to +25) | +31 (9) | -15 (3) | +29 |
| 5 | Klay Thompson (MIA) | 13 | 27c | 46% | +19 | +1.5 | +19 (+15 to +23) | +11 (9) | +37 (4) | +27 |
| 6 | Saddiq Bey (NO) | 12 | 28c | 47% | +19 | +1.5 | +18 (+15 to +22) | +36 (6) | +1 (6) | +8 |
| 7 | Tre Jones (CHI) | 10 | 31c | 50% | +19 | +1.7 | +17 (+14 to +21) | +22 (8) | +4 (2) | +13 |
| 8 | Scottie Barnes (TOR) | 9 | 30c | 48% | +19 | +1.2 | +17 (+14 to +20) | +12 (8) | +72 (1) | +17 |
| 9 | Duncan Robinson (DET) | 12 | 31c | 49% | +18 | +1.4 | +16 (+13 to +19) | +34 (8) | -15 (4) | +8 |
| 10 | Ajay Mitchell (OKC) | 10 | 28c | 45% | +17 | +1.2 | +15 (+13 to +18) | +36 (7) | -27 (3) | +10 |
| 11 | Aday Mara (OKC) | 9 | 23c | 39% | +16 | +1.5 | +15 (+12 to +17) | -5 (4) | +33 (5) | +11 |
| 12 | Jaime Jaquez Jr. (MIL) | 14 | 31c | 46% | +16 | +1.4 | +14 (+12 to +16) | +14 (9) | +18 (5) | +12 |
| 13 | Yaxel Lendeborg (GS) | 14 | 30c | 44% | +14 | +1.2 | +14 (+11 to +16) | +18 (9) | +7 (5) | +12 |
| 14 | Aaron Wiggins (ATL) | 11 | 28c | 42% | +14 | +1.2 | +13 (+11 to +16) | +23 (8) | -10 (3) | +10 |
| 15 | De'Andre Hunter (SAC) | 10 | 26c | 40% | +14 | +0.9 | +13 (+10 to +15) | +10 (7) | +22 (3) | +13 |

Worst 5: Scoot Henderson -18 (t -4.6, 12); Draymond Green -18 (t -5.5, 11); DeMar DeRozan -19 (t -2.1, 11); Ryan Rollins -20 (t -2.9, 12); Josh Hart -23 (t -5.1, 10)

### THREES: 2167 player-games, 148 players with 8+ games; every contract -0.9 a bet

- Players at t 2 or better: **3**; luck alone gives 2 (0 to 5). At +10 or better: 26; luck 20 (15 to 26).
- Do they keep it? To Nov 6 v Nov 7-16: correlation -0.09 (129 players); top 20 early +21, then -6.
- Contracts at 49c or less traded above double 38% of the time (fair ceiling 50%).

| # | Player | Games | Paid | Landed | Excess | t | Luck at this rank | To Nov 6 | Nov 7-16 | Spike v fair |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | Aaron Wiggins (ATL) | 11 | 35c | 61% | +26 | +2.5 | +27 (+21 to +38) | +36 (8) | -1 (3) | +23 |
| 2 | Lauri Markkanen (UTAH) | 8 | 31c | 56% | +25 | +1.6 | +24 (+18 to +30) | +25 (8) | - | +12 |
| 3 | Luka Dončić (LAL) | 12 | 34c | 58% | +23 | +2.2 | +21 (+17 to +27) | +35 (9) | -10 (3) | +25 |
| 4 | Desmond Bane (ORL) | 12 | 32c | 53% | +21 | +1.7 | +20 (+16 to +24) | +17 (8) | +28 (4) | +14 |
| 5 | Davion Mitchell (MIA) | 14 | 26c | 46% | +20 | +2.0 | +19 (+15 to +22) | +27 (9) | +8 (5) | +13 |
| 6 | Kyrie Irving (DAL) | 11 | 35c | 55% | +20 | +1.2 | +18 (+14 to +21) | +21 (7) | +19 (4) | +0 |
| 7 | Sam Hauser (BOS) | 10 | 34c | 52% | +18 | +1.7 | +17 (+14 to +20) | +12 (7) | +32 (3) | +24 |
| 8 | Klay Thompson (MIA) | 13 | 33c | 51% | +18 | +1.4 | +16 (+13 to +19) | +10 (9) | +36 (4) | +8 |
| 9 | Saddiq Bey (NO) | 13 | 28c | 45% | +17 | +1.5 | +15 (+13 to +18) | +16 (7) | +19 (6) | -1 |
| 10 | Evan Mobley (CLE) | 12 | 20c | 37% | +17 | +1.4 | +15 (+12 to +17) | +26 (9) | -11 (3) | -1 |
| 11 | Jaime Jaquez Jr. (MIL) | 14 | 22c | 38% | +16 | +1.9 | +14 (+12 to +17) | +14 (9) | +20 (5) | +8 |
| 12 | Stephon Castle (SA) | 14 | 31c | 46% | +15 | +1.3 | +14 (+11 to +16) | +24 (9) | -1 (5) | +0 |
| 13 | De'Anthony Melton (GS) | 14 | 29c | 43% | +13 | +1.1 | +13 (+11 to +15) | +17 (9) | +7 (5) | +1 |
| 14 | Grayson Allen (CHA) | 13 | 34c | 46% | +12 | +1.0 | +13 (+10 to +15) | +12 (10) | +12 (3) | +4 |
| 15 | Alperen Sengun (HOU) | 10 | 22c | 34% | +12 | +2.1 | +12 (+10 to +14) | +14 (4) | +11 (6) | +2 |

Worst 5: AJ Dybantsa -17 (t -4.9, 11); Draymond Green -19 (t -2.3, 10); Sam Merrill -22 (t -1.9, 8); Brandon Miller -23 (t -2.5, 11); Bilal Coulibaly -28 (t -11.0, 8)

### REBOUNDS: 2384 player-games, 165 players with 8+ games; every contract -1.2 a bet

- Players at t 2 or better: **3**; luck alone gives 2 (0 to 5). At +10 or better: 19; luck 24 (18 to 31).
- Do they keep it? To Nov 6 v Nov 7-16: correlation -0.07 (142 players); top 20 early +22, then -3.
- Contracts at 49c or less traded above double 39% of the time (fair ceiling 50%).

| # | Player | Games | Paid | Landed | Excess | t | Luck at this rank | To Nov 6 | Nov 7-16 | Spike v fair |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | Ausar Thompson (DET) | 11 | 34c | 64% | +30 | +2.9 | +29 (+23 to +38) | +35 (7) | +21 (4) | +19 |
| 2 | Jaden McDaniels (MIN) | 14 | 32c | 61% | +29 | +3.1 | +25 (+20 to +32) | +34 (10) | +16 (4) | +25 |
| 3 | Cedric Coward (MEM) | 13 | 35c | 59% | +24 | +2.2 | +23 (+19 to +28) | +32 (8) | +11 (5) | +21 |
| 4 | Ace Bailey (UTAH) | 14 | 38c | 58% | +20 | +1.8 | +21 (+18 to +26) | +30 (9) | +3 (5) | +8 |
| 5 | AJ Dybantsa (WSH) | 11 | 35c | 55% | +20 | +1.6 | +20 (+17 to +24) | +27 (5) | +14 (6) | +18 |
| 6 | Giannis Antetokounmpo (MIA) | 14 | 34c | 48% | +14 | +1.4 | +19 (+16 to +23) | +22 (9) | -1 (5) | +27 |
| 7 | Anthony Black (ORL) | 10 | 27c | 40% | +13 | +1.1 | +18 (+15 to +22) | +14 (5) | +13 (5) | +15 |
| 8 | De'Anthony Melton (GS) | 12 | 27c | 40% | +13 | +1.7 | +17 (+15 to +21) | +24 (7) | -3 (5) | -4 |
| 9 | Aday Mara (OKC) | 11 | 34c | 47% | +13 | +0.9 | +17 (+14 to +20) | +13 (6) | +13 (5) | +5 |
| 10 | Franz Wagner (ORL) | 12 | 38c | 50% | +12 | +1.2 | +16 (+14 to +19) | +4 (7) | +23 (5) | +0 |
| 11 | Jonathan Kuminga (MIN) | 13 | 36c | 47% | +12 | +0.9 | +16 (+13 to +18) | +9 (9) | +18 (4) | -8 |
| 12 | RJ Barrett (TOR) | 13 | 37c | 49% | +12 | +0.8 | +15 (+13 to +18) | +11 (9) | +13 (4) | -5 |
| 13 | Derik Queen (NO) | 14 | 35c | 46% | +11 | +1.0 | +14 (+12 to +17) | +28 (9) | -18 (5) | -4 |
| 14 | Dyson Daniels (ATL) | 14 | 33c | 44% | +11 | +1.1 | +14 (+12 to +16) | +6 (10) | +23 (4) | +1 |
| 15 | Isaiah Hartenstein (OKC) | 14 | 37c | 48% | +11 | +0.9 | +13 (+12 to +16) | +8 (9) | +16 (5) | -5 |

Worst 5: Aaron Gordon -17 (t -1.5, 12); Bam Adebayo -18 (t -2.2, 14); Caleb Wilson -18 (t -1.5, 10); Scoot Henderson -19 (t -7.6, 8); Daniel Gafford -22 (t -2.7, 13)

### ASSISTS: 2049 player-games, 139 players with 8+ games; every contract -1.9 a bet

- Players at t 2 or better: **2**; luck alone gives 2 (0 to 4). At +10 or better: 14; luck 17 (12 to 23).
- Do they keep it? To Nov 6 v Nov 7-16: correlation +0.01 (124 players); top 20 early +18, then -3.
- Contracts at 49c or less traded above double 39% of the time (fair ceiling 50%).

| # | Player | Games | Paid | Landed | Excess | t | Luck at this rank | To Nov 6 | Nov 7-16 | Spike v fair |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | Davion Mitchell (MIA) | 14 | 31c | 57% | +26 | +2.5 | +27 (+20 to +36) | +26 (9) | +27 (5) | +21 |
| 2 | Myles Turner (MIL) | 9 | 30c | 56% | +25 | +2.1 | +23 (+18 to +29) | +29 (5) | +21 (4) | +22 |
| 3 | Jamal Shead (TOR) | 9 | 35c | 56% | +21 | +1.7 | +21 (+17 to +25) | +29 (7) | -6 (2) | +21 |
| 4 | Alperen Sengun (HOU) | 13 | 32c | 53% | +20 | +1.9 | +19 (+15 to +23) | +42 (7) | -5 (6) | +7 |
| 5 | Franz Wagner (ORL) | 13 | 29c | 46% | +17 | +1.2 | +18 (+15 to +21) | +19 (8) | +14 (5) | +22 |
| 6 | Anthony Black (ORL) | 10 | 30c | 47% | +16 | +1.2 | +17 (+14 to +20) | +13 (5) | +20 (5) | +25 |
| 7 | Peyton Watson (CLE) | 12 | 32c | 46% | +14 | +1.5 | +16 (+13 to +19) | +26 (7) | -3 (5) | -39 |
| 8 | Draymond Green (GS) | 11 | 36c | 50% | +14 | +1.3 | +15 (+12 to +18) | +30 (6) | -5 (5) | +10 |
| 9 | Jeremiah Fears (NO) | 14 | 27c | 40% | +14 | +1.4 | +14 (+12 to +17) | +7 (8) | +23 (6) | +12 |
| 10 | Cedric Coward (MEM) | 12 | 26c | 39% | +13 | +1.1 | +14 (+11 to +17) | -8 (7) | +42 (5) | +12 |
| 11 | Keyonte George (UTAH) | 13 | 36c | 49% | +13 | +1.0 | +13 (+11 to +16) | +6 (9) | +28 (4) | +14 |
| 12 | Quentin Grimes (LAL) | 10 | 23c | 35% | +12 | +1.0 | +12 (+10 to +15) | +15 (8) | +2 (2) | -5 |
| 13 | Ausar Thompson (DET) | 11 | 29c | 41% | +12 | +1.0 | +12 (+10 to +15) | +16 (7) | +4 (4) | -5 |
| 14 | Darius Acuff Jr. (SAC) | 11 | 35c | 45% | +11 | +0.7 | +12 (+10 to +14) | +13 (8) | +6 (3) | +0 |
| 15 | Jaden McDaniels (MIN) | 14 | 21c | 30% | +9 | +0.9 | +11 (+9 to +14) | +17 (10) | -12 (4) | +8 |

Worst 5: Scottie Barnes -21 (t -1.6, 9); Scoot Henderson -21 (t -2.7, 10); Wendell Carter Jr. -21 (t -3.1, 11); P.J. Washington -24 (t -2.7, 11); Jakob Poeltl -25 (t -2.6, 8)

### POINTS + REBOUNDS + ASSISTS: 1292 player-games, 71 players with 8+ games; every contract -3.3 a bet

- Players at t 2 or better: **0**; luck alone gives 1 (0 to 3). At +10 or better: 15; luck 12 (8 to 17).
- Do they keep it? To Nov 6 v Nov 7-16: correlation -0.12 (54 players); top 20 early +15, then -2.
- Contracts at 49c or less traded above double 40% of the time (fair ceiling 50%).

| # | Player | Games | Paid | Landed | Excess | t | Luck at this rank | To Nov 6 | Nov 7-16 | Spike v fair |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | Paul George (BOS) | 9 | 37c | 63% | +26 | +1.6 | +31 (+22 to +43) | +21 (5) | +31 (4) | +17 |
| 2 | Darryn Peterson (UTAH) | 8 | 44c | 67% | +22 | +1.6 | +26 (+19 to +34) | +14 (3) | +27 (5) | +17 |
| 3 | Karl-Anthony Towns (NY) | 10 | 42c | 62% | +20 | +1.6 | +23 (+17 to +30) | +1 (5) | +39 (5) | +21 |
| 4 | Donovan Mitchell (CLE) | 10 | 46c | 65% | +19 | +1.2 | +21 (+15 to +26) | +10 (5) | +28 (5) | +7 |
| 5 | Darius Acuff Jr. (SAC) | 10 | 42c | 60% | +18 | +1.2 | +19 (+14 to +24) | +35 (6) | -8 (4) | +20 |
| 6 | Tyrese Maxey (PHI) | 13 | 44c | 62% | +18 | +1.5 | +17 (+12 to +22) | +31 (8) | -3 (5) | +11 |
| 7 | Keyonte George (UTAH) | 8 | 40c | 56% | +16 | +1.0 | +16 (+11 to +20) | +26 (5) | -2 (3) | +0 |
| 8 | Walker Kessler (LAL) | 11 | 37c | 52% | +15 | +1.0 | +14 (+10 to +19) | +17 (7) | +10 (4) | +22 |
| 9 | Franz Wagner (ORL) | 11 | 40c | 53% | +13 | +0.9 | +13 (+9 to +18) | -18 (6) | +50 (5) | +5 |
| 10 | Tyler Herro (MIL) | 11 | 42c | 55% | +12 | +0.7 | +12 (+9 to +16) | +33 (8) | -43 (3) | +12 |
| 11 | Cameron Boozer (MEM) | 12 | 46c | 58% | +12 | +0.9 | +11 (+8 to +15) | +23 (7) | -3 (5) | -21 |
| 12 | Miles Bridges (PHX) | 9 | 38c | 50% | +12 | +0.7 | +10 (+7 to +14) | +54 (3) | -10 (6) | -6 |
| 13 | Luka Dončić (LAL) | 11 | 41c | 52% | +11 | +0.7 | +10 (+6 to +13) | +22 (8) | -20 (3) | +18 |
| 14 | Deni Avdija (POR) | 11 | 43c | 53% | +10 | +1.0 | +9 (+5 to +13) | +24 (6) | -6 (5) | +20 |
| 15 | Jaylen Brown (PHI) | 11 | 44c | 55% | +10 | +0.8 | +8 (+5 to +11) | +10 (6) | +11 (5) | +11 |

Worst 5: Jalen Johnson -21 (t -1.6, 8); Joel Embiid -24 (t -1.6, 9); Nikola Jokić -28 (t -2.5, 10); Scoot Henderson -32 (t -4.7, 8); LaMelo Ball -34 (t -5.3, 12)

## Also found
- Kalshi listed no star points or threes contracts before Nov 18 2025. This October is the only season opening it has priced,
  so an early-season catch-up cannot be checked on an earlier season.
- One lead, not a result: where the season average says 8+ above the ask and the last five do **not** (a cold run the price
  has followed down), held contracts made +17% on 72 player-games (points) and +22% on 64 (threes). It is the reverse of the
  form idea. It needs 100+ unseen player-games in each series before it means anything.

## Build spec
None. Rule: none. Scope: none. Nothing to retire or keep.
