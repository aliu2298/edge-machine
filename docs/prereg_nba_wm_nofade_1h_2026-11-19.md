# NBA win margin, NO fade in the first hour only: pre-registration (Nov 19 2026)

Written BEFORE the first entry. Sandbox PAPER only: no live order, no live-trading switch, no VPS or config change. The two live win-margin lanes are untouched
and stay live until a replacement exists (Olu).

Source: the deep look at the two win-margin lanes (docs/nba_win_margin_deep_look_2026-11-19.md, "filtered version worth a paper row").

## Rule
- **Entry:** a post-only NO bid at 75% of the bucket's pregame NO price (price an hour before the tip, 1 minus the YES bid), live from the tip to
  60 minutes after it, then cancelled. Every bucket (both teams), pregame NO price 10-95c, YES spread 5c or less, and the ask check the version 4
  entry uses (10+ contracts traded at or through the price in the hour after the read, and not under half the last trade). Same fill rules as the
  NO fade replay: a fill needs a print strictly under the bid with 10+ contracts under it within an hour; a bid that would cross at the tip is no entry.
- **Side row:** the same, at 65%, on the same buckets.
- **Exit:** sell back at the pregame price on a print, else held to settlement. Maker fees in and out.
- **Paper sell rule (the fix):** a sell is also filled at the touch when 10 or more contracts trade AT the target after the entry, as live sells are.
  The strict version (a print strictly above the target) is shown beside it. Results are shown per fill and per game.
- **Built as a filter** on nba_wm_nofade.py's replay, which already records each bucket's 65% / 75% / 85% fill with its fill time; a fill counts
  here when it came within 60 minutes of the tip.

## Comparisons, same nights
1. The same buckets with the version 4 full-game 65% bid (already graded) and the 75% bid all game.
2. A blind row: for each first-hour fill, one random bucket of the same game within 3c of its pregame NO price (never a bucket the 75% bid filled in the
   first hour), bought at the pregame NO price (taker fee) and held to settlement; seeded by the fill's ticker.

## Record and read
- Fresh record from the first slate after the merge (night 2026-11-19, ET). No backfill: nothing earlier counts.
- Read once, at 30 fills. Promote only if the per-fill return is above zero after fees, t (by night) is 2 or better, it beats the all-fills 75%
  version on the same nights, and no single night carries more than half the profit.
- Retire at 30 fills if the return is at or under zero; or after 30 nights if fills stay under one a night.

## Disclosed
- The 75% level was chosen after looking. On Nov 1 to 18 it was +24.0% on 49 first-hour fills (t 5.6), but only +8.0% on 11 fills since Nov 8, and fills fell from
  about 7 a night to 1. This record is its own forward test.
- Fourth-quarter fills at 75% never paid in any period, which is why the bid is cancelled at 60 minutes.

## The YES watch line (not a lane)
Each week: the share of 10-20c buckets (tracker rows, ask 10-20c) whose price doubled within 60 minutes of the tip (m.first2, minutes to the first print at
2x the ask). By this measure: 44% on Oct 20-31 and 11% on Nov 8-18. The page flags it if the last 7 nights are above 30%.
