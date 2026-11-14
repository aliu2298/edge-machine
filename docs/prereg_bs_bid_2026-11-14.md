# Before-start bid, fights and NFL: pre-registration (Nov 14 2026)

Sandbox PAPER watches, observation only, never in Production. Written before the first bid they count. The rule is the build spec of the
before-start study (docs PR 455), `nl_dump.replay` is the engine (it reproduces Fable's replay bet for bet). Code: `bs_bid.py`, ledger
`data/bs_bid_ledger.json`, workflow `bs-bid.yml` (replay once after each event settles, from public trade prints; no VPS, nothing live).

> "Before-start bid, fights. Paper only. Rows: UFC, boxing. Read at 50 and at 100 fills a row. Keep = positive return after fees with t of 2 or
> more clustered by card day, and the row still positive counting only the first fill of each fight. Retire = under that at 100 fills. No
> retuning of depth, clock or exit before the 100-fill read."

## Row 3: NFL, "a watch, not a pass"
The same rule on KXNFLGAME. It missed the found-dates bar by a hair (+15.4% on 19 bets, t 1.4) and reads +14.7% on 47 bets over both halves, so it
is judged on its own with the same reads: at 50 and at 100 fills, keep = positive after fees, t of 2 or more clustered by game day, first-fill-only
row still positive; retire = under that at 100. No retuning before then.

## The rule (fixed)
- Kalshi winner markets: KXUFCFIGHT, KXBOXING, KXNFLGAME; both sides of every market.
- The start is Kalshi's own schedule (the milestone listing's `start_date` for the event), not `expected_expiration_time`.
- From the first trade until the cutoff, every whole minute T a bid rests 15c under R, the last trade on the bid's side. None if nothing traded in
  the 10 minutes before T, if R is over 95c, or if the bid would sit under 5c. Live from T + 25 s to T + 85 s.
- Cutoff: fights 12 hours before the scheduled start (the one change from the tested 3 hours; chosen after looking, so the watch judges it).
  NFL 3 hours before it, the tested rule. (The coordinator's note said 12 hours for NFL; the study's spec says 3 for NFL and its schedule is
  accurate, so the tested rule is kept.)
- Fill (honest-v1): only a trade strictly through the bid while it is live; size = what $1 buys, or what traded through.
- Sell: resting at R - 5c, up 60 s after the fill, filled only by a trade strictly through it; taker sale with the taker fee if the price is
  already there. Unsold contracts ride to the result. One position a side of a market at a time.
- Fees: UFC and boxing pay no maker fee (fee_type quadratic); NFL pays 0.0175 x p x (1 - p) on every resting fill (quadratic_with_maker_fees);
  a taker sale pays 0.07 x p x (1 - p).
- Columns: 25 s order delay is the headline, 2 s the comparison; a third column keeps only the first fill of each fight or game (earliest fill
  over every market and side of the event).
- Counts: only bids from Nov 14 2026 12:00 UTC on events from Nov 14. Scored by card day (the event ticker's date).

## Where it shows
Fights page (UFC, boxing) and NFL page, each a section labelled as a paper watch, percentages only.
