# Econ Daily and Finance Daily

These are paper-only migrations of Research Lab's `daily-v1` rule. The catalog is discovered from Kalshi's public daily Economics and Financials series; it is not fixed at eleven series. Only the supported closing thresholds enter the paper rule. Unsupported series remain visible in scan coverage. The existing AAA forecasting rule is unchanged.

Entry: YES 70–80 cents, spread at most three cents, at least 25 contracts at the ask verified from a two-sided fixed-point order book, 2–3.5 hours before the supported contract close. Buy the cheapest qualifying threshold per event, breaking ties by ticker, and freeze that first entry. All qualifying thresholds are also retained as the baseline. No range, weekly, publication-lag-rate or already-observed extrema contracts are entered. Each series scan must be complete before ranking; missing pages or books retain existing records and produce a visible error.

Settlement uses the same market's official final result or scalar payout. Closed-but-unsettled markets remain open in the paper ledger. The $100 paper stake and reference fee model match Research Lab; they are not fills. Correlated thresholds and series do not count as independent samples. The pages display settled contracts and market-days separately and do not declare an edge from the raw win count.

`daily-research.yml` scans hourly at :17 UTC and owns `data/daily_ledger.json`. It needs only GitHub Actions' existing repository-scoped `GITHUB_TOKEN` to save that file. All market requests are public and receive no credentials. Only one run writes this ledger; conflicts fail visibly rather than dropping records. Existing Sandbox Tracker builds and publishes the two pages from the saved ledger on its next run. The displayed successful-scan time is the source clock, distinct from the page-build time. GitHub may delay scheduled jobs.

No private Site credentials, old Research Lab records, Production selections, Polybot exports or trading settings are migrated. Research Lab remains stopped.

Validation: `python test_daily_research.py`, `python test_control_center.py`, `python test_site_shell.py`.
