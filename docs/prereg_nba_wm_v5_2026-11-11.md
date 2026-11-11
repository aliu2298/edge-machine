# NBA win margin v5 — paper candidates, pre-registered 2026-11-11

Status: PAPER ONLY. Production keeps running version 4 + Bucket Priority bp-v3 (executor `f2b89e0`, edge #393). Nothing here touches the executor,
the config or the live feeds. Frozen before the first night, on Olu's decision of 2026-11-11 (option b).

Record starts fresh on the Nov 11 (ET) slate (`SINCE = 2026-11-11`). Review at 10 nights, decide at 30 entries.

## YES v5 (paper lane `nba_wm_yes_v5`, version `wm-yes-v5-paper`)
- Buckets: 6-10 and 11-20 only (either team). No 1-5, no 21+.
- Entry / fill rules: identical to v4 — YES ask 10-20c, spread <= 5c, tracker ask check (10+ contracts at or through the ask in the hour after), one hour before the tip, taker buy with the taker fee.
- Favourite skip ON: a game whose favourite's pregame win share is 0.70 or more is skipped.
- Sells: half at 2x and half at 2.5x of the ask (cap 98c), each filled only by a print STRICTLY through the target from the tip on; unfilled legs settle.

## NO v5 (paper lane `nba_wm_nofade_v5`, version `wm-nofade-v5-paper`)
- Post-only NO bid at 65% of the bucket's pregame NO price (the v4 bid and all its fill rules: strict prints, verified ask, sell back at pregame on a print strictly above it, else settle).
- Buckets: 1-5 and 6-10 plus the alternate ladder (11+, 11-15, 16-25, 26+). No 11-20 on the main ladder and no 21+.

## Comparison (same games, same fill rules as the page replay)
- Each v5 row is shown beside the matching live v4 row; inside its panel the v4 rule is replayed on (a) the same games v5 traded and (b) all of v4's games since the start.
- Replays are paper, from the tracker (YES) and the NO fade ledger (NO), not the executor's decisions; Production's own decision-based record is the live v4 row.

## Decision rule
- Review at 10 nights. Decide at 30 entries (YES) / 30 games (NO). A v5 lane is promoted only if it beats the v4 rule on the same games, is positive after fees, and is not carried by one night. Olu decides.

## Why these cells (research of 2026-11-11, not evidence)
Offline grid of 12 YES and 9 NO cells over Oct 20 - Nov 10: no cell cleared the pre-set bar (positive in both halves and Nov 8+, and ahead of v4). These two were the closest. Most of the sample is the sample v4 was chosen on, and Nov 8+ is 2-3 nights, so the grid is a reason to test, not a result.
