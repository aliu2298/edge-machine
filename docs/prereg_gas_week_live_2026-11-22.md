# AAA gas weekly cheap NO in Production — 2026-11-22 (Olu: "yes, move gas weekly to Production at $1")

Pair `gas_week_cheap_no|gas_week`, feed `data/gas_week_production_leads.json`, module `gas_week_production.py`. Written before the first live entry.

**Rule (unchanged, not retuned).** The Sandbox paper lane `gas_week_cheap_no` (mentions_split.GAS_WEEK): on the weekly KXAAAGASW ladder, for each
rung, the first minute quote inside 6h of the rung's open with a spread of 10c or less and a NO ask (1 − the YES bid) of 0.15–0.30; buy the NO
at that ask; HOLD to settlement. The ask check must have verified the entry. About 3 entries a week on one weekly event.

**What live adds.** The follower buys the NO at the REAL ask when it reads the listing, only if that ask is still 15–30c and the book is 10c wide
or less, one order per rung, $1 a bet, held to settlement. A listing is on offer for 4 hours after the paper entry was logged; replayed entries
(logged 3h+ after their own minute) and entries logged before 2026-11-22 21:00Z are never listed. The 2x/3x split stays a secondary shadow line on
the paper lane; nothing sells.

**Record.** Fresh live record from 2026-11-22 21:00Z. A week is one outcome (the rungs of a weekly event move together). Paper record on the day
of promotion: 14 entries, 3 of 3 settled weeks positive, +81.2% held; honest figure +123% on 6 confirmed (3 outcomes, score 1.74). The evidence
test is waived by Olu (record in data/promotion_gate.json). Review at 8 settled live weeks, decide at 10+.

**Risks said plainly.** Thin sample; the paper entry minute is not the live buy minute (the live buy is at the ask the follower reads, which can
be worse, and is skipped when it is out of band); cheap NOs lose most of the time and win big, so a week can lose all its rungs.
