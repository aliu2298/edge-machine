# Soccer futures longshot NO: pre-registration (Nov 14 2026)

Sandbox PAPER watch, "a watch, not a pass", never in Production. Written before the first entry. The spec is `futures_longshot_no` in the soccer
futures study (docs PR 460), verbatim below. Code `fut_ln.py`, ledger `data/fut_ln_ledger.json`, workflow `fut-ln.yml`; no VPS, nothing live.

> `futures_longshot_no`: on the 1st of each month (Sep-Apr), every league-winner market (EPL, La Liga, Serie A, Bundesliga, Ligue 1,
> Eredivisie, Primeira, Super Lig, Belgian Pro League, EFL Championship) whose YES bid is 3-15c and spread <=10c: paper-buy NO at
> 1 - the YES bid, one entry per market per season, held to settlement, Kalshi taker fee. Its baseline: the same entries on top-4
> and relegation markets (which lose). 19 markets qualify today across 8 leagues; ~20-25 entries a season, so 30 settled entries
> take until mid-2027. Review at 10, decide at 30, with an exact-binomial read (not z) because losses are rare.

## Choices left open by the text, fixed here
- First checkpoint is Dec 1 2026 (the 1st after the build). A run on the 1st to the 3rd of a month takes that month's checkpoint if the 1st was
  missed, using that run's own prices; one checkpoint a month; one entry per market ticker (a ticker is one team in one season).
- Entry price 1 - the YES bid; fee 0.07 x p x (1 - p) on the entry (p = the NO price); nothing at settlement. A market with no ask is skipped.
- Baselines: KXEPLTOP4, KXLALIGATOP4, KXSERIEATOP4, KXBUNDESLIGATOP4, KXLIGUE1TOP4 and the five relegation series, with the same filter. Kept apart.
- The exact binomial: the chance of seeing this many longshot wins or fewer if every longshot won at the probability its own YES bid priced (the exact
  Poisson-binomial tail). Shown at 10 settled entries (review) and 30 (decide). A small chance says the longshots are being over-priced.
- Display (not a rule): next to the return, the capital tied up (average cost of an entry, average days held to Kalshi's expected settlement) and the
  annualised return (1 + return) ^ (365 / days) - 1. One longshot win costs about as many wins as the average loss over the average gain (about 11 in the study).
- Series (winners): KXPREMIERLEAGUE, KXLALIGA, KXSERIEA, KXBUNDESLIGA, KXLIGUE1, KXEREDIVISIE, KXLIGAPORTUGAL, KXSUPERLIG, KXBELGIANPL, KXEFLCHAMPIONSHIP.

## Where it shows
Soccer page, Sandbox section: three rows (the watch and the two baselines), labelled, percentages only.
