# International lanes review (Nov 12 2026)

Every lane that bets on national-team football was replayed on Kalshi's own international history, with the form rules recomputed from results and the filters written down first. No lane changes. Nothing was promoted or pulled.

"Points" is the share of bets won minus the price paid. Returns are per bet after fees, on honest fills.

## Verdicts

| Lane | Stage | Verdict |
|---|---|---|
| Under 3.5 low scoring, internationals | Live | **Keep version 1.** Do not widen it past Nations League and friendlies. |
| Team 1 form, internationals | Live | **Keep version 1.** |
| Team 2+ form, internationals | Live | **Keep.** It almost never fires, so there is nothing to judge. |
| Over 1.5 ranked, internationals | Sandbox | **Keep in the Sandbox.** No edge over backing every match; not a candidate to go live. |
| Team 2+ ranked fade, internationals | Sandbox | Five open bets, none settled. Nothing to judge yet. |

No timing change is needed. No filter held, so there is no version 2.

## Timing: does betting days early cost anything?

Not on the lanes' own bets.

| Lane | Bets | Logged (median hours early) | Price when logged | Price 3h before kickoff |
|---|---|---|---|---|
| Under 3.5 low scoring | 26 | 75 | 77.5c | 77.6c |
| Team 1 form | 8 | 47 | 82.1c | 82.9c |
| Over 1.5 ranked | 17 | 56 | 75.9c | 77.1c |

Early books are wide in general. Three days out the average gap between bid and ask on a totals market is 28.7c, and only 58% of books are within 5c. Three hours out it is 2.9c and 95%. On every match, an early ask is about 4c dearer than the ask near kickoff.

The lanes are protected because the tracker only bets when the book is tight. That rule should stay.

These are form rules: the matches are chosen from results, not from the price. So timing changes only the price paid, not which matches are picked. That is why the Eredivisie problem does not repeat here.

## The replay

Kalshi lists 526 settled international matches with a totals market since May 2026. 425 were matched to a result history: friendlies 161, UEFA Nations League 104, World Cup 90, Concacaf Nations League 70. The other 101 (mostly AFCON qualifiers) have no results on file and were left out.

Entry three hours before kickoff. Discovery is May to July; holdout is September to November.

### Under 3.5 low scoring

| Where | Bets | Won | Price | Return | Every match, same market |
|---|---|---|---|---|---|
| Nations League | 19 | 94.7% | 79.4c | +21.8% | +12.1% (104) |
| Friendlies | 19 | 89.5% | 77.1c | +13.9% | +2.6% (153) |
| World Cup | 4 | 50.0% | 76.5c | −39.6% | −7.0% (90) |
| Concacaf Nations League | 8 | 50.0% | 69.2c | −25.7% | −12.6% (69) |

- On the lane's own two competitions: 38 bets, 35 won, +17.8%. Up in both periods: +6.8% on 12, then +22.9% on 26.
- That replay passes the promotion gate's evidence test (score 2.08). It is a replay, not the lane's record.
- Outside them the rule lost: 6 wins in 12. It should not be widened.
- Under 3.5 on every Nations League match also paid (+12.1% on 104). The rule adds about 15 points of win rate on top.

### Team 1 form

| Where | Bets | Won | Price | Return | Every side, same market |
|---|---|---|---|---|---|
| Nations League | 12 | 100% | 85.9c | +17.1% | −8.5% (205) |
| World Cup | 8 | 87.5% | 77.9c | +11.4% | +1.5% (179) |

20 bets, 19 won, +14.8%. Thin, but up in both periods and well ahead of backing every side.

### Team 2+ form

Two bets in 388 team-matches; both won. Backing every side to score twice returns −17.8%, so that market is dear in general.

### Over 1.5 ranked

The replay made 16 picks and returned −2.2%. Over 1.5 on every international match returns −1.3%. The lane's own record is 10 wins in 13. The replay ranks within a calendar day, which is not exactly how the lane builds its pool, so its own record is the better guide; neither shows an edge.

## Filters tried

For each rule: friendlies against competitive matches, a strong favourite (0.60 or more) against a closer match, home favourite against away favourite, and early against late entry.

Four looked good on the first period. None held on the second.

## Other lanes checked

- The soccer label rules list Nations League totals but have never made an international pick.
- The over 3.5 cheap NO lane has no international entry.
- Retired international scopes, for the record: +0.5 unbeaten (15 wins in 17 when retired), congestion under 2.5 (7 in 17), team 2+ ranked (3 in 16), over 1.5 form (1 in 3).

## Files

Research folder: `~/edge-research/intl_2026-11-12/` (the menu written in advance, the pull, the analysis and its output).
