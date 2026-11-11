# Jobless claims NO 70-85c before the release — paper lane, pre-registered 2026-11-11

Status: SANDBOX PAPER ONLY. No order is placed. Frozen on 2026-11-11 (Olu's decision, via the coordinator), before the
first entry. Lane `jobless_no_70_85`, module `jobless_claims.py`, ledger `data/jobless_claims_ledger.json`.

**This is a price-band test.** It selects by price only, with no filter yet (the no-blind-selection rule). It is judged as
a test of the price band, not as a filtered lane.

## Rule
- **Series:** Kalshi `KXJOBLESSCLAIMS`, the weekly initial jobless claims ladder. Each rung is "claims ≥ X".
  - The release is the US Labor Department's weekly print, normally Thursday 8:30 ET.
  - In holiday weeks it moves, e.g. Wednesday before Thanksgiving. The lane anchors on each event's own Kalshi
    `close_time` (8:29 ET, one minute before the print), never on the weekday.
- **Entry window:** from 3h to 1h before the event's close, i.e. about 05:29-07:29 ET on a normal week. This is the study's
  pre-release replay.
- **Entry:** for each rung, the first minute in the window whose two-sided quote has a spread of 10c or less and whose NO
  ask is 70-85c (both ends inclusive). Buy NO at that ask.
  - One entry per rung, frozen.
  - Replayed from Kalshi's 1-minute candles, so the time of the read never changes a price.
- **Exit:** hold to settlement. No sells.
- **Fees:** taker fee in, 0.07 · p · (1 − p) per contract.
- **Honest fill (the cheap-side lanes' ask check, `chaos_replay.entry_check`):** an entry counts only if both hold:
  - 10 or more contracts traded at or through its ask within 60 minutes after the entry.
  - The ask is not under half the last trade before it.
  - Entries that fail are listed as unverified and left out of the record.
- **Comparison line:** the YES side on the same ladder, same window, same 70-85c band, same rules. It is shown beside the
  lane and is never the lane.

## Record
- Fresh from the first release on or after 2026-11-12 (`SINCE`). No backfill: the study weeks are evidence, not record.
- **Judged by weeks.** One release is one cluster.
  - weeks settled
  - weeks positive
  - mean week ROI: each week's mean held ROI per contract, after fees
  - z over weeks: the mean over its standard error, from 3 weeks
  - won v priced: wins against the sum of prices paid
- Review at 8 settled weeks, decide at 12. Olu decides.

## Evidence (econ weekly study, 2026-11-11; in-sample, NOT counted)
Last 10 settled weeks; pre-release entry, under the same band and spread rules.
- **NO 70-85c:** 8 weeks with an entry. Won 8 of 8 against 6.2 priced. Hold +28%.
  - Older half +27%, newer half +29%.
  - +26% without the best week.
  - Weekly z +1.54.
- **YES 70-85c, same ladder:** −39%. The edge, if real, is one-sided.
- **Cheap rungs (1-14c):** won 1 of 35 before the release. The ladder looks too wide, not overconfident.
- **Caveat:** 10 weeks is thin, and z +1.54 is weak. This is a reason to test, not a result.

Full study: `~/Predictions/econ_weekly_table.md` and `~/Predictions/econ_weekly_joblessclaims.png` (outside the repo).
