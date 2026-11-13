# African qualifiers, goals lead: forward check (pre-registered Nov 12 2026)

Observation only. No lane, no bets. Written and committed before any match of the window was played.

## The lead

On the one window Kalshi has settled (48 AFCON qualifier matches, Sep 24 to Oct 6 2026), the market expected too few goals. Backing every match at the ask three hours before kickoff:

| Bet, every match | September result |
|---|---|
| NO on over 3.5 goals | 6.9 points overpriced (48 matches) |
| YES on over 1.5 goals | 7.3 points underpriced (48 matches) |
| YES on a side to score | 9.7 points underpriced (91 sides) |

"Points" is the share of bets won minus the price paid. One window can be luck.

## The forward read

- **Matches:** every AFCON qualifier Kalshi settles from the Nov 12 to 17 2026 window. 24 are listed today: 9 on Nov 12, 12 on Nov 13, 3 on Nov 14. Any more that list in the window are included.
- **Markets:** `KXAFCONTOTAL` rung 4 (over 3.5, the NO side), `KXAFCONTOTAL` rung 2 (over 1.5, the YES side), `KXAFCONTEAMTOTAL` each side's rung 1 (the YES side).
- **Entry:** the ask on the hourly quote three hours before kickoff. Kickoff is the ESPN fixture time.
- **Fills and fees:** the fill simulator's quoted rule: the ask counts unless trade prints refute it; taker fee as the exchange charges it.
- **Clusters:** a match day is one outcome.

## What counts as "held"

The lead holds only if all of these are true on this window:

1. NO on over 3.5 wins less often than its price.
2. YES on over 1.5 wins more often than its price.
3. YES on a side to score wins more often than its price, by 3 points or more.

If any one fails, the lead is dropped as one window's luck. If all hold, it stays a lead: two windows do not make a rule, and any lane would still need a stated selection reason and its own pre-registration.

## Also read, for the record

The four international form rules on the same matches. The verdict to keep African qualifiers out of those lanes changes only if under 3.5 low scoring wins 80% or more of its picks here.

## How it will be run

`~/edge-research/intl_2026-11-12/window_read.sh`, once the matches have settled.

## Note, Nov 12 2026: now also a paper lane

Added the same day, at Olu's request. The read is now also shown on the Soccer page as a Sandbox paper lane (`africa_goals`), so it can be watched as it settles. Nothing above is changed: the same matches, markets, entry, fills and fees, and the same three conditions, judged on this window when it settles.

- The lane logs each bet from the hourly quote three hours before kickoff. The first matches of Nov 12 had kicked off before the lane existed; their bets were filled in from that same hourly quote and are marked as backfilled in the ledger.
- It is an observation lane: paper only, never in Production.
- After this window it keeps running on later African windows, on its own record.

## Addendum, Nov 13 2026: a BTTS row, added after the window opened

Written and committed on Nov 13 2026 before 18:30 UTC, at Olu's request. **Nothing above is changed**: the three bets, their entry and the three "held" conditions stand as written on Nov 12.

**Why a fourth row.** On the September window, YES on both teams to score, every match, at the ask three hours before kickoff: won 54.2% at 38.9c, 15.2 points underpriced (48 matches). It is the same lean seen through another market, not new evidence. Detail: `africa_btts_2026-11-13.md`.

**What was already known when this was written.**

- The window opened on Nov 12. Its Nov 12 matches are finished and three of the Nov 13 matches had kicked off. Their scores are public.
- No November BTTS price or result had been read for this study when this was written. Only the September matches were pulled.
- Because the scores were knowable, those matches are shown and flagged, and **do not count**.

**The row.**

- **Bet:** YES on `KXAFCONBTTS`, every AFCON qualifier, at the ask on the hourly quote three hours before kickoff (ESPN fixture time). Same fills, fees and clusters as the rows above.
- **Counted matches:** those that kick off after 18:30 UTC on Nov 13 2026. Six are listed today: Mali v Rwanda, Egypt v Malawi, Morocco v Niger (Nov 13); Uganda v Botswana, Angola v South Sudan, Algeria v Togo (Nov 14). Any more that list in the window are included.

**What counts as "held" for this row.**

1. The lead itself holds, by the three conditions above. If the lead is dropped, this row is dropped with it.
2. BTTS YES wins more often than its price, by 3 points or more, on the counted matches.
3. With fewer than 10 counted matches the row is "too few to say" whatever it shows, and is read again on the next African window together with this one.

First-half BTTS (`KXAFCON1HBTTS`) is not tracked: on September it was 1.5 points overpriced on the YES side, with a wide book.

**How it will be run.** `~/edge-research/intl_2026-11-12/window_btts.sh`, after `window_read.sh`.
