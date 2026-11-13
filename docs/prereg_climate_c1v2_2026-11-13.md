# Cold lean on daily highs, version 2: pre-registration

Pre-registration for the Sandbox paper lane `c1v2` (climate_lanes.py), committed 2026-11-13 with the build. **Copied unchanged from the study's drafts**
(Fable, Kalshi climate study, parts 1 and 2: docs/climate_study_part1_2026-11-12.md, docs/climate_study_part2_2026-11-13.md, and the rule text written
with its time in `~/edge-research/climate_2026-11-12/RULES.md`). Olu's decision, 2026-11-13: both lanes go to the Sandbox as paper. No rule is changed
by the build. Fresh record from the first entry.

Build notes (how the code reads the rules, not rule changes): the favourite is the first highest mid in bracket order; "all six brackets quoted" means an
ask on every bracket; fees are fillsim's honest-v1 taker fee on the quoted NO price; the run acts only between 22:00 and 22:50 Eastern and logs how late it
started; a city-day is one outcome; the forecast run used is logged on every Cold-lean row.

## Rule text as written before the unseen months were read

## C1 and C2, the cold lean (daily highs). Written 2026-11-12 23:03Z, holdout not yet read for anything.
Why: on the discovery period the high came in warmer than the evening-before favourite 30% of the time and cooler 24%, in every month
and in 17 of 21 cities. The bracket two cooler than the favourite was priced 7.7c at mid and won 4.3%.
- C1 (taker): at 10:00 pm ET the day before, with all six brackets quoted, find the favourite (highest mid). On the bracket two cooler,
  buy NO at 1 minus the YES bid, pay the taker fee, hold to settlement. All 21 cities, every day. Skip if there is no such bracket or
  the YES bid is 0.
- C2 (resting): same bracket and time; rest a sale of YES at the ask (a NO bid at 1 minus the ask), no fee; it counts only if a later
  hourly candle shows the YES bid above that price before 10am local on the day; hold to settlement.
Discovery: C1 +2.3% a bet on 2,865, score 4.6 (city-day and calendar day), every month up. C2 +3.2% on 1,605 fills of 2,899, score 3.9.
Pass on the holdout: return above zero with a score of 1.5+ by city-day. Nothing is retuned. Reported too, not rules: the 17 cities
without Denver, Las Vegas, Phoenix and San Antonio; the 4pm ET and 6am reads; NO price bands.

## C1f, the cold lean filtered by the public forecast. Written 2026-11-13T04:30Z; no part 2 test has read the unseen months.

Part 2 on the found months: forecast v price (48 cells), midnight days (20), tilt (24): no registered cell passes. The market beats the NBS
forecast alone at every read, and the forecast's tilt is more than priced.
What the tilt table showed, against my registered guess: the cold lean (NO two cooler at d-1 10pm ET) pays where the forecast is NOT above the
favourite. Found months, 18 cities with forecasts: forecast below the favourite +4.3% on 607 (t 3.4); inside +1.9% on 1,386 (t 2.9);
above -0.2% on 319. Same order at d-1 4pm ET (+3.7%, +1.9%, -2.7%). I had registered the opposite ("take it when the forecast agrees"): that fails.
Reason offered: the public forecast is a daytime max built from smooth hourly values and reads low (official high beats the top hourly
reading on 62% of days). Buyers who follow it bid the cool brackets. When the forecast itself is above the favourite, nobody is bidding them.
Forecast = latest NBS run at least 2 hours old: max(daytime max, 3-hourly temps inside the standard-time day), plus the city's mean shift fitted on found months.
"Below/inside/above" = that number against the favourite bracket's edges.
Rules (two, the family's limit):
 C1f-a: C1, skipped when the forecast is above the favourite.
 C1f-b: C1, taken only when the forecast is below the favourite.
Pass mark each, unseen months read once: return above zero, t 1.5 or more, and above the return of the C1 bets it leaves out.
Lows: the same split on L1 is not mirrored and is small (above +0.7% on 477, inside +2.8% on 405, below +3.8% on 119). No lows filter is tested.

### C1f result, read once 2026-11-13T04:30Z
Unseen months Jul 1 to Nov 11 2026, 18 cities with forecasts. C1 itself on these bets: +1.4% on 1,730 (t 2.5).
C1f-a (skip forecast above): +1.7% on 1,601, t 2.94; the 129 bets it leaves out: -2.5%. PASSES. Months: Jul +3.4, Aug +1.4, Sep +2.2, Oct +0.2, Nov +1.9.
C1f-b (only forecast below): +1.9% on 574, t 1.78; the 1,156 it leaves out: +1.1%. Passes the mark, barely; October -1.3%. Not worth the lost bets: reported, not recommended.
Unseen periods read in this study: C1 pass, C2 fail, R1 fail, L1 pass, C1f-a pass, C1f-b marginal pass.

## Build spec: cold lean on highs, version 2

For whoever builds. A Sandbox paper lane. This replaces the version 1 spec in part 1.

- **Rule:** at 10:00 pm ET the day before, on each city's next-day high ladder with all six brackets quoted, the favourite is the bracket with the highest mid price. Take the bracket two cooler. Buy NO at 1 minus the YES bid, taker fee, hold to settlement.
- **Skip** when there is no bracket two cooler, the YES bid is 0, fewer than six brackets are quoted, **or the public forecast is above the favourite**.
- **The one change from version 1:** the forecast skip.
  - Forecast: the newest NBM station text run (NBS) for the city's station that is at least 2 hours old. Take the larger of its daytime max for the day and its 3-hourly temperatures inside the day (midnight to midnight, local standard time). Add the city's shift from `c1f_shifts.json` (all within 0.4 of a degree; 0 for a city not listed).
  - "Above the favourite" means that number is more than half a degree over the favourite bracket's top. If the favourite is the open-ended top bracket, it is never above.
  - If no forecast can be read, take the bet and mark the row "no forecast".
- **Scope:** the 21 daily-high series listed in part 1. Stations: NYC KNYC, Chicago KMDW, Miami KMIA, Austin KAUS, Denver KDEN, Los Angeles KLAX, Philadelphia KPHL, Atlanta KATL, Boston KBOS, Dallas KDFW, Washington KDCA, Houston KHOU, Las Vegas KLAS, Minneapolis KMSP, New Orleans KMSY, Oklahoma City KOKC, Phoenix KPHX, San Diego KSAN, San Antonio KSAT, Seattle KSEA, San Francisco KSFO.
- **Entry timing:** one read at 10:00 pm ET, from the live book. Log the YES bid, the contracts at that bid, the favourite's bracket, the forecast and its run time.
- **Control rows, same time, same page:** (a) NO on the bracket two warmer; (b) the skipped bets, recorded but not counted in the lane.
- **Record:** a city-day is one outcome. Paper only.
- **Retire or keep:** by the text below.

### Pre-registration text for the forward check

> Cold lean on highs, version 2, Sandbox paper. Read once at 1,000 settled bets (about eleven weeks).
> - Keep if the return after fees is above zero and above control (a), NO on the bracket two warmer.
> - Retire if it is zero or below, or not above control (a).
> - The skip is kept if the skipped bets, control (b), returned less than the lane. If they returned more, the lane goes back to version 1 on the same record and the skip is dropped.
> - Stop early and review if the return is below −3% at 300 settled bets.
> - No city is dropped or added, and the read time is not moved, before that read.

The warm lean on lows keeps its part 1 spec and pre-registration text unchanged.
