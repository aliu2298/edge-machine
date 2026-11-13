# Warm lean on daily lows: pre-registration

Pre-registration for the Sandbox paper lane `l1` (climate_lanes.py), committed 2026-11-13 with the build. **Copied unchanged from the study's drafts**
(Fable, Kalshi climate study, parts 1 and 2: docs/climate_study_part1_2026-11-12.md, docs/climate_study_part2_2026-11-13.md, and the rule text written
with its time in `~/edge-research/climate_2026-11-12/RULES.md`). Olu's decision, 2026-11-13: both lanes go to the Sandbox as paper. No rule is changed
by the build. Fresh record from the first entry.

Build notes (how the code reads the rules, not rule changes): the favourite is the first highest mid in bracket order; "all six brackets quoted" means an
ask on every bracket; fees are fillsim's honest-v1 taker fee on the quoted NO price; the run acts only between 22:00 and 22:50 Eastern and logs how late it
started; a city-day is one outcome; the forecast run used is logged on every Cold-lean row.

## Rule text as written before the unseen months were read

## L1, the warm lean on daily lows (mirror of C1). Written 2026-11-13T01:53Z; the lows holdout (Jul 1 to Nov 11 2026) has not been read for anything.

Reason: on the found period the low landed cooler than the evening-before favourite on 28.6% of city-days and warmer on 25.7%
(highs: warmer 30% v cooler 24%). Read together: the evening-before market under-prices the day's range at both ends.
Rule: at 10:00 pm ET the day before, buy NO at 1 minus the YES bid on the bracket two WARMER than the favourite. All low series. Hold.
Found period (Dec 13 2025 to Jun 30 2026, 20 series): +1.9% on 1,146, t 2.17, 4 of 7 months up, 14 of 20 cities up. NO price median 92c.
Control: NO on the bracket two cooler, same read: -0.4% on 2,110.
Weak on the found period: one cell at t 2.2, not steady by month. Tested because it is the one mirrored prediction of C1, not as a pick from the map.
Pass mark, holdout read once: return above zero, t 1.5 or more (city-day), and above the control. Otherwise it fails and is not re-cut.

### L1 result, read once 2026-11-13T01:55Z
PASSES. Holdout Jul 1 to Nov 11 2026, 21 series: +2.1% on 1,021 (won 97.2% at 95.4c), t 2.96, every month up (Jul +2.9, Aug +2.7, Sep +1.8, Oct +0.4, Nov +3.7).
Control (NO two cooler): -2.1% on 2,178. Low v favourite on the holdout: cooler 28.4%, warmer 19.9%.
Fills: worst bid of the next hour +0.8% (t 1.2). Trade prints, 250 sampled: 33 verified, 216 unconfirmed, 1 refuted; no trade in the next hour on 59% of nights.
Depth, one snapshot Nov 13 01:55Z (9pm ET): 13 ladders with a bracket two warmer, 3 to 95 contracts at the best YES bid, median 19.
Holdouts opened so far in this study: C1 pass, C2 fail, R1 fail, L1 pass.


## Build spec: warm lean on lows, version 1

For whoever builds. A second row of the same Sandbox paper lane, or its own lane; nothing else changes.

- **Rule:** at 10:00 pm ET the day before, on each city's next-day low ladder with all six brackets quoted, the favourite is the bracket with the highest mid price. Take the bracket two warmer. Buy NO at 1 minus the YES bid, taker fee, hold to settlement.
- **Skip** when there is no bracket two warmer, the YES bid is 0, or fewer than six brackets are quoted.
- **Scope:** the 21 daily-low series: KXLOWTNYC, KXLOWTCHI, KXLOWTMIA, KXLOWTAUS, KXLOWTDEN, KXLOWTLAX, KXLOWTPHIL, KXLOWTATL, KXLOWTBOS, KXLOWTDAL, KXLOWTDC, KXLOWTHOU, KXLOWTLV, KXLOWTMIN, KXLOWTNOLA, KXLOWTOKC, KXLOWTPHX, KXLOWTSAN, KXLOWTSATX, KXLOWTSEA, KXLOWTSFO.
- **Entry timing:** one read at 10:00 pm ET, from the live book. Log the YES bid, the contracts at that bid, and the favourite's bracket. The logged depth matters more here than on highs.
- **Control row, same time, same page:** NO on the bracket two cooler. It should lose.
- **Record:** a city-day is one outcome. Paper only.
- **The one change from version 1:** none; this is version 1.
- **Retire or keep:** by the text below.

### Pre-registration text for the forward check

> Warm lean on lows, version 1, Sandbox paper. Read once at 500 settled bets (about ten weeks).
> - Keep if the return after fees is above zero and above the control row's (NO on the bracket two cooler).
> - Retire if it is zero or below, or not above the control.
> - Stop early and review if the return is below −3% at 150 settled bets.
> - Also report the share of entries with fewer than 10 contracts at the bid. It does not decide keep or retire; it says how much could be traded.
> - No city is dropped or added, and the read time is not moved, before that read.
