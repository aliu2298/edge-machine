# Challenger underdog who has won here: live in Production, pre-registered 2026-11-20

Moved by hand (Olu, Nov 20: "Use option 2 in production", evidence test waived by Olu the same day). Registered before the first live order.

**Rule (unchanged idea, one change of source).** Back the ATP Challenger player priced 15-30c (spread 5c or less) about an hour before the match who has already won a match at this tournament (qualifying counts), when the opponent has not played one there. Held to settlement, no sells. $1 a bet, the default stake (no per-pair stake entry).

**What changed.** Kalshi stopped naming the tournament in the event's competition field on Nov 11. The tournament is read from the market rules text instead ("... in the 2026 ATP Challenger Helsinki Quarterfinal ..."), which still names it. The Sandbox paper lane keeps its own reading and runs on as the control.

**Gate (a data check, run before going live).** Over the named era (events Nov 1-10, 476 events with a named tournament): the rules-text tournament equalled the named field on 476 of 476, the same picks came out on 476 of 476 events (93 with a pick), and 29 of 29 paper trades were reproduced. Bar was 95%. Live open events: every one of 617 parses.

**Entry.** The feed lists a pick up to 3 hours before the scheduled start; the filter does not depend on price. The follower buys only inside the last hour and a quarter before the start, at the ask, inside the 15-30c band. Kalshi's scheduled start can be later or earlier than the real one, so the entry hour is approximate; the follower's price band and its own timing window stand between a started match and an order.

**Record.** Fresh live record from the first live day. Counted from the follower's own orders, after fees.

**Read.** Review at 10 live settled bets. Decide at 30. No change to the rule before then.

**Disclosed.** Honest-grade on the paper lane: +33.2% on 32 bets, 9 outcomes, score 0.91 (the evidence test failed on outcomes and score, waived). The named era carried the record (+37.9% on 29); the generic era (Nov 11 on, a broader filter) was -10.4% on 9.

**First live day:** Saturday 2026-11-21 (UTC). The live record counts matches from 2026-11-21 00:00 UTC; the follower is switched on only after both PRs are merged and the host is backed up.
