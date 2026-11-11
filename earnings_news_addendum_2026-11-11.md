# Earnings & news calls — addendum 2026-11-11 (Olu)

`earnings_news_families.md` is the SHA-pinned pre-registration and is NOT edited. These decisions sit beside it.

1. **F3 news calls retired** (2026-11-11), with 0 calls ever. Reason: never ran — there is no automated news reader,
   and a public headline read late is not an edge. `earnings_news.py news` now refuses to log a call.
2. **F2a drift into the report is a comparison line, not a strategy.** It buys every reporting stock with no
   selection, so under the no-blind-selection rule it is the baseline the other families must beat. It keeps
   logging and grading exactly as before; the page shows it as "Comparison · buy every reporting stock", with no
   review or decide stage, and does not count it among the running rules.
3. **F1 KPI drift, F2b post-earnings drift and F4 trader sentiment run on unchanged** through this earnings season and
   are judged after the Nov 12 – Dec 1 earnings run.
4. **A report date that moves voids the old call.** When a stock's report date in the calendar changes, a prediction
   for the OLD date that has not entered yet is marked `void` (reason "report date moved"); it is never deleted.
   First case: Alibaba, `runup:BABA:2026-11-24` (logged Nov 7) is void; `runup:BABA:2026-11-19` (logged Nov 9) stands.
