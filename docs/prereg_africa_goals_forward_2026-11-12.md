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
