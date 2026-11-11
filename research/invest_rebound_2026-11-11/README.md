# Rebound after a slide — research (2026-11-11)

`PREREGISTRATION.md` was fixed before any result was computed (sha256 in `prereg.sha256`). `research.py` ran it on
Alpaca SIP 1-minute regular-hours bars for the 58 Kalshi Invest stocks, 2023-01-03 .. 2026-11-11; `analyze.py` wrote
`table.md` (56 variants against B1, the same slides with no support cue, and B2, random entry).

Result: **nothing clears**. 0 CLEARS, 0 WATCH. No variant beat B1 in the first research half (0 of 56); 9 did in the
second; 38 did in the holdout only because B1 lost there (−0.62% for the 5-day slide). Only one variant was positive in
the holdout (+0.05%). Best by research margin: 5-day slide · strong support · selling slows · halfway target, +0.12% a
trade v B1 +0.12% (t −0.12), holdout −0.42% v −0.62%.

Worked examples (`examples.py`): NVDA Nov 10 — the slide reached Monday's low 170.24 (three methods agree) at 09:42 ET,
selling slowed at 09:59, the rule bought at 173.15 and was stopped at 168.54 (1% under support) at 10:49 as NVDA broke to
165.89: −3.0%; the no-support baseline bought at 09:43 and held to +1.1%. SPCX's regular-hours bars never fell 5% under
the 24-hour high this week (worst −4.3%): its slide was mostly outside regular hours, which the research cannot see and
the live lanes (rebound.py, every open minute of Kalshi's reference price) do — the 24-hour lane bought SPCX at the
138.95 support on Nov 11 and hit its target, +1.8% (in-sample).

The bars (~1 GB) stay in ~/edge-research/invest_rebound_2026-11-11 and ~/edge-research/invest_bigmove_2026-11-06/bars.
