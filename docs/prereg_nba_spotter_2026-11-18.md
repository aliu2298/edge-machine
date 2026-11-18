# NBA Spotter (Sandbox, paper): pre-registration, 2026-11-18

Requested by Olu via the Edge Machine Coordinator, 2026-11-18 ("come up with a way to track this in sandbox"). Paper only: no orders and no live switch.
Source: Fable's spotter research (nba_stars_2026-11-18: SPOTTER.md, sp_data.py, sp_fit.py, tonight_board.py). Code: `nba_spotter.py`, page `nba_spotter_build.py`,
workflow `.github/workflows/nba-spotter.yml`, ledger `data/nba_spotter_ledger.json`, frozen files `data/spotter/`.

## What the research found (disk only, Nov 7 to 16, picks frozen before results were joined)
Hold board +1.4 points a contract (+3%, t 0.7, blind -1.7); spike board sold at 2x +4.0 (+9%, t 0.7, blind -4.0). Neither reached t 2: NOT PASSED.
The model barely moves off the price; Kalshi's ask was right at both ends of the calibration. This lane is the forward test, from the first night it runs.

## The model is frozen
`data/spotter/model.json` carries the hold and spike models exactly as fitted on Oct 20 to Nov 6 2026 (sha256 of the two models in the file; the test recomputes it)
and the research's constants (pull toward the middle, night spreads, standardised-night tables). NO REFIT, ever, inside this lane. A refit is a new lane.
`data/spotter/last.json` is last season's box scores (per player), `data/spotter/games.json` this season's, extended each run from ESPN's finished games.
`test_nba_spotter.py` checks the engine reproduces Fable's Nov 18 board (model chances and reasons to 1e-5) from `data/spotter/regression.json`.

## Inputs at entry time only
The ask and bid (read 80 to 35 minutes before each tip; the VPS stamps for NBA tips ask at about 75), the ESPN injury report's Out list (instead of the research's
did-not-appear stand-in), box scores to date, last season, the ESPN spread. A listed-Out player is never entered. Day-to-day players are not excluded.

## The two boards (each also has a blind control)
Universe: every Kalshi player prop (KXNBAPTS, KXNBA3PT, KXNBAREB, KXNBAAST, KXNBAPRA) rung with a two-sided quote, spread 5c or less, ask 5c to 60c, a player the model can project.
- **spotter_hold**: model chance minus ask of 5 points or more; ranked by that gap; up to 8 a night, one a player-stat. Held to settlement.
- **spotter_spike**: asks of 49c or less, ranked by the spike model's chance minus 50% (the fair ceiling at a 2x sale); up to 8 a night, one a player-stat. A paper resting sell at
  2x the ask (rounded to the cent). Held to settlement if it never sells.
- One deviation from the research's whole-night ranking: games are read as they come up to tip, so a pick is final when its game is read. Each game may take at most 4 per board
  (the first game of a night cannot take all 8). Games read in the SAME run are ranked together (largest gap first), so a catch-up run is not decided by tip order. Picks are never replaced later.
  First night (Nov 18): a manual first run read six games at once before this joint ranking existed, so its 8 hold and 8 spike picks came from the first two games by tip order; they stand as entered and are graded like any other pick (disclosed here, not hidden).
- **Blind controls** (spotter_hold_blind, spotter_spike_blind): for each pick, one rung drawn at random (seed fixed by the pick) from the same game's priced rungs within 3c of the
  pick's ask (the nearest price if none), never one of the board's players, 49c or less for the spike control; same exit. Price mix matches by construction.

## Fills and money (honest rules)
Bought at the ask, taker fee 7% x p x (1 - p) per contract (the exchange grid). The sell fills only on a LATER trade print strictly above the target, no sooner than 25 seconds after
the entry; the fee is charged on both legs (stricter than a resting fill). Unsold: held to settlement. Settled from Kalshi's result.

## The read
Once, at 200 graded picks per board (about 3 to 4 weeks). Keep only if: return after fees above zero, t 2 or better by night (nights are the clusters), AND 2 or more points
a contract over the board's blind control. Anything else: not kept. No early read, no mid-way retune, no changes to the rules above.
