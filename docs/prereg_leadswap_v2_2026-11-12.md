# Lead Swap favourite v2 (lsb-v2) and the Loss Reader retirement — pre-registered 2026-11-12

Status: PAPER ONLY, Sandbox. No orders, nothing in Production, no executor or config change. Frozen before the first window of the record.
Olu's decision of 2026-11-12. Code: `leadswap_v2.py`, `sw15cuts.py` round 3 (`CUT3_AT`), page `swing15_build.py`. Ledger: `data/leadswap_v2_ledger.json`.

## What changes, and when
One instant, `2026-11-12T11:00:00Z` (a window boundary, `sw15cuts.CUT3_AT` = `leadswap_v2.FROM`):

1. **Loss Reader (Rule 1 v2, `sw15-lr1`, Solana) is retired.** Nothing enters after the cut. Its final record: **20 won, 11 lost on 31 bets, −8.0% after fees, 20 v 20.9 priced** (verified from `data/lossreader_ledger.json` at registration). It is worse than the every-window S2 bet on the same windows (−1.8%, 574 bets). Ledger rows stay; the Retired block shows it on one line. (Bitcoin and WTI were cut from it on Nov 10: 36 bets, −20.5%.)
2. **Lead Swap favourite v1 (`lsb-v1`) closes** at the same instant (the favourite and its control stop entering; the swing trade was retired Nov 11). Its headline is the **FULL record with the 16 cut markets counted back in: 414 bets, 348 won, −0.7% after fees** (250 kept-market bets +5.9%, 164 cut-market bets −10.7%; verified from `data/leadswap_ledger.json`, `routing` + `removed_routing`). The +5.9% alone was inflated by cutting the losers after the fact.
3. **Lead Swap favourite v2 (`lsb-v2`) starts** as a FRESH record from the first window opening at or after the cut. The first window is 11:00Z; its picks freeze at about :04, so the first hour's entries can come before the picks froze (the picks use only data to :00; a live version could only act from :05, and the page counts how many entries did).

## The rule (v1's, on three markets)
- Picks: the Lead Swap Board, unchanged. Every hour, every 15-minute series (except `KXCRYPTOLEAD15M`) is ranked by lead swaps per window over the windows that closed in the last 2 hours (needs 4 of 8), ties by the larger minute 0-9 mid range, then ticker. Picks are frozen the first time a run at or after the hour computes them (about :04), from data to :00.
- Trade: a series in the **bottom 3 (most stable)** gets v1's S3 favourite: at minute 10 buy the side over 50c at its ask, filled only on a print at or through it in the next minute, held to settlement, taker fee.
- **Markets: Bitcoin (`KXBTC15M`), WTI Crude Oil (`KXWTI15M`), NEAR (`KXNEAR15M`) only.** The board still ranks every market; a pick on any other market is skipped, with no backfill from the next rank.
- **Control:** the same three markets when they are in the **top 3** by swaps (v1's favourite control, on these markets only), so calm v swingy stays measured.
- **Frozen:** the list is fingerprinted (`MARKETS_SHA256`, checked at every run and by the tests). No further cuts, no exclusion rounds. A change is a new version, never an edit.
- Record: windows opening at or after `FROM`. **Review at 30 bets, decide at 100.** z is cluster-aware (one block in one window is one cluster), as in v1. No backfill, nothing before `FROM` counts.

## Why these three, said honestly
They were chosen **in-sample**, on lsb-v1's own Nov 9-11 forward windows, after the fact: each had 20 or more bets and beat its own every-window S3 bet by 11-18 points, and did far worse when swingy.

| Market | v1 favourite bets | the rule | every-window S3 | when swingy |
|---|---|---|---|---|
| Bitcoin | 64 | +7.1% | −1.4% | −10.5% |
| WTI | 32 | +10.1% | −4.2% | −14.6% |
| NEAR | 23 | +14.5% | −3.8% | −9.4% |

Selecting markets on a record makes that record look good (the same effect inflated the kept-market figure of v1: +5.9% kept against −0.7% in full). These numbers are the **reason to test, not evidence**. Only the fresh forward record from `FROM` counts.

## What would count as a result
Nothing before 30 bets. At 30 (review) it is a direction check. At 100 it is decided: a version that does not beat its own control and is not positive after fees on the fresh record is retired. Three markets over a few days is a small sample; a quiet week proves nothing either way.

## Not changed
`leadswap.py` picks and board, the lsb-v1 exclusion rounds (fingerprinted, untouched), rules A and C (`sw15keep.py`), the v1 baselines, Production, the executor, any stake.
