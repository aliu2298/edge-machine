# Pre-registration: Brazil and Argentina BTTS YES (paper), Nov 16 2026

Olu approved a paper row on Nov 16 2026. Paper only: no live pairing, not in Production. Spec and evidence:
`docs/btts_brazil_argentina_2026-11-16.md` (a lead from a reference row, not a tested rule).

> Brazil and Argentina BTTS YES. Paper. Every Serie A and Primera match, YES at the ask 20 to 90 minutes before kickoff, spread 5c or less, after fees. Scored by match day. Read at 50 and 100 bets. Held if it is positive with a clustered z of 2 or more at 100 bets. Retired if it is negative at 100.

- Scope: `KXBRASILEIROBTTS` and `KXARGPREMDIVBTTS`, one market a match (ticker ends `-BTTS`).
- Rows: both leagues (main), Brazil, Argentina, and BTTS NO at its ask as the control.
- Kickoff: the ESPN fixture matched to the Kalshi event by both team names (the market's occurrence time minus 4 hours agrees).
- Fresh record from the first entry; code in `btts_sa.py`, ledger `data/btts_sa_ledger.json`, page rows on the Soccer page.
