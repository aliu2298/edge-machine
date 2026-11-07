# Earnings & news calls: pre-registered families

Registered 2026-11-07, before the first prediction. Sandbox, paper only, forward only.
These definitions are frozen. `test_earnings_news.py` pins this file's SHA-256, so editing it fails the
tests. A change is a NEW family with a new key and a fresh record. No existing family is edited
after the fact, and no prediction is edited or deleted.

## What counts

- A prediction counts only if it is written to `data/earnings_news.json` with its `logged_at`
  timestamp BEFORE its entry, and its entry is the first honest fill AFTER `logged_at`.
  The git commit that adds it is the public proof of the timestamp.
- Everything is graded on the Kalshi Invest perp of the same stock, at 1x, no leverage.

## Honest fill (every family, entry and exit)

- An Up entry buys at the ASK and a Down entry sells at the BID. The quote is the close of the first
  1-minute candle that ends at or after the due time.
- The quote counts as filled only when a public trade prints AT OR THROUGH it within 5 minutes
  (at or above the ask for a buy, at or below the bid for a sell). Otherwise the next quote 5 minutes
  later is tried, up to 6 quotes (30 minutes). If none fills, the prediction is `no_fill`. It stays on the
  record but carries no return.
- The exit is the same rule on the other side: sell at the bid (Up) or buy at the ask (Down).
- Fees: 0.12% of notional per side (taker), on entry and exit. Funding is not charged; the record says so.
- net return = side x (exit - entry) / entry - 0.24%.

## Baselines (the same entry and exit times, the same fill rule)

1. always-Up on the same stock;
2. a random direction on the same stock (a coin seeded by the prediction id, fixed when the prediction
   is logged);
3. the SPY perp Up (the market over the same window; Kalshi lists no sector ETFs).

Each family is judged on the paired difference against each baseline: mean of (call net minus baseline
net), its standard error and z. Review at 10 settled predictions, decide at 30. "Paying" needs
z >= 2 against EVERY baseline at 30.

## Earnings calendar

The next report date and time comes from Nasdaq's public earnings calendar. On 2026-11-07 it matched
Kalshi's Insights tab for NVDA ("Nov 17, 2026 · After close"). "pre-market" reports are taken at
07:00 ET on the report date. "after-hours" reports are taken at 16:05 ET. "not-supplied" is treated
as pre-market, the earliest it could be. The REACTION SESSION D is the report date for a pre-market
report and the next trading day for an after-hours one. P is the last 16:00 ET close before the report.

## The families

### F1 `kpi_drift`: Kalshi KPI ladder drift into the report

- Scope: an Invest stock whose quarterly Kalshi KPI ladder resolves AT this report. That is a
  `Financials`/`Companies` event whose series is `KX<SYMBOL>` (not the annual `KX<SYMBOL>A`, and not the
  monthly card-spend / foot-traffic series), with an event-ticker date code in the report month.
- Read: each rung's YES probability is its mid when the spread is 0.20 or less; a wider rung is
  dropped. The read must keep at least 3 rungs, and they must straddle 50%. The probabilities are made
  monotone, and the ladder median is where they cross 50%, interpolated linearly. The width is the
  distance between the 25% and 75% crossings, or between the outermost rungs when a crossing is
  missing.
- Signal: compare the read at log time against the EARLIEST read taken at least 5 days before the
  report. If the median rose by at least 0.25 x the earlier width, the call is Up. If it fell by at least
  that much, the call is Down. Otherwise the stock is logged as `no_call`.
- Log window: the first run from 30 to 6 hours before the report.
- Entry: the first honest fill after logging. Exit: 16:00 ET on the reaction session D.

### F2a `runup`: drift into the report

- Every reporting Invest stock is called Up from 16:00 ET five trading sessions before P to P. It is
  logged at least 1 hour before that entry. Its edge is read against the SPY baseline: does the stock beat
  the market into its report?

### F2b `post_drift`: post-earnings drift

- On the reaction session D, the first run at or after 15:00 ET measures the reaction R as the perp mid
  now over the perp mid at P, minus 1.
- If |R| >= 2%, the call is the sign of R. Otherwise the stock is logged as `no_call`.
- Entry: the first honest fill after logging. Exit: 16:00 ET five trading sessions after D.

### F3 `news`: news-cycle calls

- A structured call: stock, direction, horizon (1h, 1d or 5d), confidence (0.5 to 1.0), a one-line
  reason, the source URL and the source's own publish timestamp.
- It is logged only when the news is MATERIAL, which means all three of the following:
  - it is specific to the company;
  - it was published at most 6 hours before logging;
  - it is one of: a guidance change or pre-announcement, M&A, a regulatory or legal ruling, a major
    contract or customer won or lost, an executive departure, a recall, an outage or a safety event, or a
    capital action (a buyback, an offering, an index change).
  Opinion pieces, market wraps and analyst price-target notes are NOT material.
- The price is the one at the moment the call was logged, not when the headline appeared. A public
  headline we read later is not an edge; the record shows that.
- Entry: the first honest fill after logging. A call made while the perp is closed enters at the
  reopen. Exit: entry plus the horizon (1h = 60 minutes; 1d = the same clock time on the next trading
  day; 5d = five trading days later).

### F4 `sentiment`: Kalshi trader sentiment extremes

- Once per trading day, the first run at or after 15:00 ET reads every Equities perp with at least
  $500,000 of 24h notional volume. Its crowd share is the taker LONG share of 24h taker volume: the
  "Up x%" that the Insights tab shows.
- A share of 0.65 or more is called Up (FOLLOW the crowd). A share of 0.35 or less is called Down.
- Entry: the first honest fill after logging. Exit: the same clock time on the next trading day.
- The page also shows the FADE (the opposite side) on the same entries. It is the mirror of the follow
  record and pays the costs too.

## Review

At 10 settled predictions a family is reviewed: lean and z. At 30 it is decided:
- paying: z >= 2 against every baseline;
- no edge: anything else.
Nothing reaches Production from this file.
