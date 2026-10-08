"""The Sandbox Tracker ledger: log what each source said, then make it pay for it.

One run does three things, in this order and for a reason:

  collect -> publish   every source's probability on every live matchup, logged BEFORE
                       the event starts and stamped with the price that existed at that
                       moment. This is the whole discipline of the thing. A prediction
                       recorded after kickoff, or scored against a price nobody could
                       still get, is not evidence of anything.
  grade                every logged quote whose market has since resolved, and a bounded
                       re-check of settlements the venue has since corrected.
  score                per-source hit rate, ROI and Brier over the accumulated ledger.

The ledger is append-only and idempotent: a market is quoted ONCE per source, the first
time it is seen. Re-quoting as the price drifts would let a source keep the version of
its opinion that happened to age well, which is the single easiest way to fake an edge.
"""

import difflib
import json
import os
import re
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone

import sandbox_sources as S

LEDGER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "sandbox_ledger.json")
# Markets the settlement audit has seen disagree with the venue. The audit rewrites
# this every networked run and re-asks every id in it until the ledger matches, so a
# mismatch the hourly sample found once cannot vanish when a later sample misses it.
# grade() re-resolves these however old they are. The tracker commits the corrected
# ledger. A separate job, not the audit itself, commits only this file.
MISMATCHES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "settlement_mismatches.json")
_WATCH_FIELDS = ("market_id", "quote_id", "stored", "venue", "venue_result")

NO_RESULT_LABEL = "No result · paid 50¢"


def no_result_label(q=None):
    """The words a bet paid out at a price instead of a result carries.

    Kalshi settles a cancelled, abandoned or no-result match at 50¢ a side, so
    the stake buys 50¢ whichever side it backed. The stored settle_px is printed
    where it differs from that.
    """
    px = (q or {}).get("settle_px")
    if px is None:
        return NO_RESULT_LABEL
    return f"No result · paid {int(round(float(px) * 100))}¢"


def record_text(a):
    """'12–8, 6 no result' from an assess() record, or an em dash with nothing settled.

    Wins and losses are the record. A bet paid out at a price is neither: it is
    money in the ROI (cost the entry price, payout the settlement price) and a
    count beside the record, never a win or a loss.
    """
    n = a.get("n") or 0
    n_price = a.get("n_price") or 0
    if not n and not n_price:
        return "—"
    won = a.get("won") or 0
    rec = f"{won}–{max(0, n - won)}"
    if n_price:
        rec += f", {n_price} no result"
    return rec


def record_html(a):
    """record_text for a table cell: the W–L on the line, the no-result count
    under it in the cell's small muted line, so the count never widens a
    column of a nine-column table past its card (the Production pairs table
    sat 5px inside its card on the CI runner's fonts before this)."""
    n_price = a.get("n_price") or 0
    n = a.get("n") or 0
    if not n and not n_price:
        return "—"
    won = a.get("won") or 0
    line = f"{won}–{max(0, n - won)}"
    if n_price:
        line += f'<div class="sm mut">{n_price} no result</div>'
    return line


STAKE = 100.0        # flat, always. Any staking plan mixes bet-sizing skill into the
                     # source's score, and the question here is only "is it right?".
EDGE_MIN = 0.03      # 3pp. Below this a "disagreement" is just the tick size.
PRICE_FLOOR = 0.05   # Longshots are excluded from BETTING, not from scoring: at 0.02 a
PRICE_CEIL = 0.95    # single fluke pays 50x and one lucky pick would own the board.

# The mirror of that reasoning is why the ceiling exists: at 0.99 a loss costs a hundred
# wins, so anything selling the tail flatters its record for months before the bill arrives.
# One domain is exempt, deliberately. The daily commodity ladders ARE a tail question — the
# research that produced the rule found the ordinary bands efficient and the edge only at
# 0.97+ — so capping them at 0.95 would not make the rule safer, it would leave it unmeasured.
# The risk is handled where it belongs instead: the ROI is after fees, a day's whole ladder
# shares one outcome cluster (one draw, not twenty), and nothing in this domain is published.
PRICE_CEIL_BY_SPORT = {"commodities": 0.995}


def price_band(sport):
    """(floor, ceiling) a bet in this domain may be logged at."""
    return PRICE_FLOOR, PRICE_CEIL_BY_SPORT.get(sport, PRICE_CEIL)

# Below this many settled bets a record is not read at all (the page greys it).
READ_FLOOR = 30

# THE STAMP OF APPROVAL — pre-registered 2026-09-12, before any source had met it. Every
# criterion must hold, for every betting source alike (tipsters, models, books, markets),
# and it is re-judged on every run, so a stamp can be lost as well as won.
#
#   sample     at least MIN_BETS settled bets, spanning at least MIN_DAYS from the first
#              start to the last. (Counted as calendar weeks touched until 2026-09-13,
#              which let "4 weeks" pass after three weeks and a day, and QA's "2 weeks"
#              after a Sunday and a Monday.)
#              One weekend is one draw of the weather, not 36 independent bets: on
#              Sep 12 2026 the tracked leagues drew 34% of the time against a normal ~26%,
#              and a tipster that picks draws looked brilliant for exactly that reason.
#   the price  wins beat the wins the prices paid implied, by Z_MIN standard deviations.
#              With a dozen sources and seven sports under test, a z of 2 turns up by
#              chance, so the bar is set there and the other criteria carry the rest.
#   baseline   ROI beats EVERY blind rule on the same contests — back the favourite, back
#              the underdog, back the draw (three-way only). Each is a fixed rule that
#              ignores the source entirely, so beating all of them means the choices
#              added something. (A first version compared each bet with the blind bet of
#              the same type — the draw for a draw pick — which is the identical bet
#              whenever the pick IS the favourite, so the test could never differ.)
#   no one hit ROI stays positive with its single biggest win removed.
#   both halves ROI is positive in the earlier and the later half of its settled bets.
APPROVAL = dict(min_bets=50, min_days=28, z_min=2.0)

# ---- Stages: Sandbox -> QA (set 2026-09-13) -----------------------------------------------
# Promotion is per (source, sport): a tipster can be in QA for MLB and still in the Sandbox
# for soccer. The QA ENTRY gate is deliberately lighter than the stamp, because QA re-tests
# on FRESH data — only bets logged after the promotion — so a lucky run cannot carry a
# source through twice. Every criterion must hold:
#   30+ settled bets spanning 14+ days · wins beat the price by z >= 1 · beats every blind rule on
#   the same contests · still profitable without its single biggest win.
# In QA, the stamp (APPROVAL) is applied to the fresh data, plus positive closing-line value
# and positive ROI after fees.
#
# TWO STAGES since 2026-09-18, as asked: Sandbox, and Production. There is no QA stage and no
# automatic promotion — a pair reaches Production because it is listed in PAIR_OVERRIDES by
# hand, and that decision is the owner's. What the Sandbox does is measure, so that the
# decision is made on a record rather than on a hunch.
#
# The gates below are no longer a route to anywhere. They stay because they are the honest
# summary of a pair's record — the Sandbox page reports them as "what this pair would have to
# show", and demotion still uses them:
#   * DEMOTION after demote_bets settled bets when EITHER the pair is behind the prices it
#     paid (z < 0) or it does not beat every blind rule on the same contests. And whatever the
#     count, when it has logged no new bet for STALE_DAYS — its source went dark or its season
#     ended — so nothing sits in Production untested.
#   * The closing price no longer demotes: every pair in Production was put there by hand,
#     with its CLV visible on the page. It is reported, not enforced.
#   * Baselines are benchmarks, not forecasters, and are never promoted.
# A demoted pair stays out until it is listed again with a later date.
QA_ENTRY = dict(min_bets=30, min_days=14, z_min=1.0)     # reported on the Sandbox page
QA_DEMOTE = dict(min_bets=30, z_below=0.0)
READY_CLV = dict(min_n=30, min_share=0.5)
# ---- The CLV read (pre-registered 2026-09-22) -----------------------------------------------
# Closing-line value is the only figure here that converges fast enough to judge an efficient
# market in a usable time. A win/loss record carries the outcome's own noise: at a true 2% edge
# on a 0.51 price, z >= 2 needs on the order of 5,000 settled bets, which soccer totals will
# never supply. CLV removes that noise and asks a narrower question — did the price move toward
# this pick before the start — so it reads on tens of bets rather than thousands. The Sandbox's
# own record shows the difference: the tennis favourite-band rule is z +1.91 on 428 settled
# bets (ambiguous) and t -3.61 on 429 closing prices (not ambiguous at all).
#
# It is a DIFFERENT question, not a cheaper version of the same one, and it is only evidence
# where the closing price is real: CLOSE_MAX_LEAD_MIN gates that, and roughly half of settled
# bets have a close fresh enough to count. A rule can beat the close and still lose money, and
# it can make money with no CLV at all. So CLV is read beside the record, never instead of it.
CLV_T = 2.0            # a mean beating the close by this many standard errors
CLV_MIN_N = 20         # ...over at least this many fresh closes
READY_HOLD_DAYS = 7
STALE_DAYS = 21
NEVER_PROMOTED_KINDS = ("Baseline",)

# ---- Per-sport thresholds (2026-09-16) ------------------------------------------------------
# One set of numbers did not fit every sport. The 14-day span exists because one weekend of
# football is one draw of the weather; a tennis rule logs ~50 bets a day across dozens of
# tournaments, so it met every other entry gate in two days and then waited two weeks on the
# calendar alone. High-volume sports therefore drop the calendar and keep a HIGHER bar on the
# price: a stricter z (a sample that big shows a real edge quickly, and it gets four looks a day).
# Every other sport keeps the original numbers. Set before any pair used them.
HIGH_VOLUME_SPORTS = ("tennis", "table_tennis")
SPORT_RULES = {
    # 2026-09-16, as asked: 50 bets to leave the Sandbox, 50 fresh bets in QA, no day span.
    "high": dict(entry=dict(min_bets=50, min_days=0, z_min=1.5),
                 approval=dict(min_bets=50, min_days=0, z_min=2.5),
                 demote_bets=50,
                 # 2026-09-16, as asked: the Sandbox record counts in QA too, so a pair's whole
                 # record since it last entered the Sandbox is judged, not only fresh bets.
                 qa_counts_sandbox=True),
    "standard": dict(entry=QA_ENTRY, approval=APPROVAL, demote_bets=QA_DEMOTE["min_bets"]),
}


# ---- Pairs in Production, each put there by hand ------------------------------------------
# The only way into Production. A pair listed here moves on the next run whatever its record
# says, is judged on that whole record (Sandbox bets included), and starts trading when it
# reaches `production_at` settled bets while profitable after fees — `None` for straight away.
# Demotion still applies: see the note at the top of this file.
PAIR_OVERRIDES = {
    # soccerpredictions — listed 2026-09-21 and taken off the SAME DAY, as asked. It was put
    # here on a record of 105 settled at +5.4% (z +0.56); the tracker run that promoted it
    # also settled 23 more of its bets, which went 7 won against 8.4 priced (-$470), leaving
    # the whole record at 128 settled, 49 won v 47.7 priced, +0.18%, z +0.24. That is level
    # with the price, and the margin the promotion argued from was gone within the hour. This
    # is the pair's second demotion. A third listing needs a reason that is not its ROI.
    # 2026-09-17, as asked. Demoted from QA the day before for the reason that still stands:
    # its closing-line value is -0.07% and it beats the close on 28% of bets, so it wins at
    # prices that were already right (z +1.64 against the 2.5 the old gate asked for). It does
    # clear every other criterion — 149 settled, +6.4% against +3.8% for backing the
    # favourite on every match, profitable in both halves and without its biggest win.
    #   tennis favourite band — REMOVED 2026-09-23, back to the Sandbox, as asked, and its
    #   band narrowed from 0.75-0.90 to 0.75-0.80 at the same time. Over 446 settled it was
    #   +2.63% at z +1.68, but the whole of that sat in the cheap third: 0.75-0.80 ran +5.5%
    #   (z +1.75) on 181 bets and 0.80-0.90 ran +0.7% on 265, which is flat and the reverse of
    #   the favourite-longshot bias it was built on. It was also half as good after promotion
    #   as before it (+1.22% on 274 v +4.89% on 172), and its closing prices had been saying so
    #   for a week: -0.85c a bet over 437 closes, t -3.66. The narrowing was found IN that
    #   record, so it is a new claim and the record cannot test it — hence the reset, and hence
    #   Production is not the place for it until a narrow-band record exists.
    # 2026-09-18, as asked: the two rules that were published from the Leads board move here,
    # so that Production is the single list everything downstream reads.
    #   over 1.5 — REMOVED 2026-09-21, back to the Sandbox. It was the only Production pair
    #   behind the price: 16-5 reads like a winner until you notice the average price is 0.84,
    #   where 76.2% is a losing hit rate (-10.1% after fees, z -1.00). All of the damage sits
    #   in the 0.80 band, which is also most of its volume. The rule is kept and still
    #   measured; what it needs is a different selection, not a different wrapper.
    # 2026-09-18, as asked. 19 settled on the US exchanges at +15.1% (+11.5% after fees) and,
    # unusually, it BEATS THE CLOSE by 6.9c — its picks get dearer after it makes them, which
    # is the opposite of the tennis band. Small and young: one day's span, z +0.82. NFL is
    # listed with it and has yet to settle a bet.
    # espn_fpi — MLB demoted itself on 2026-09-21 ("not beating every blind rule, +3.7% v
    # +9.1% back the favourite"): the edge it was listed on had flattened to +0.5% over 47
    # settled. NFL was only ever listed alongside it, and was left in Production on FOUR settled
    # bets (-57.6%) — a record that cannot say anything either way. Taken off 2026-09-21 as
    # asked. No pair belongs in Production on a sample that small because its sibling once looked good.
    #   team scores 1+ — was on fast-track probation, which no longer exists as a route.
    "team1_form_l5|soccer_team1": dict(moved_on="2026-09-18", production_at=None),
    # 2026-10-01, as asked. The internationals twin, named as its own pair. The
    # league pair above does not cover it, and neither does any other suffix:
    # the cup twin is not listed. Same checks as the league pair.
    "team1_form_l5|soccer_team1_intl": dict(moved_on="2026-10-01", production_at=None),
    # 2026-09-27, as asked, and before the 50-bet stamp. 12 settled on the US exchanges at
    # +203% (z +2.22), clearing every criterion except the sample. Stated plainly because the
    # ROI is not what it looks like: +214pp of it is TWO longshots landing, a 0.07 at +1328
    # and a 0.11 at +809, and the other 10 bets return +30%. So the lane's character is
    # longshot hits, not a steady margin, and its P/L will be lumpy in a way none of the
    # soccer pairs are. cricket was added to ROUTED_SPORTS the same day so the feed can
    # express it at all; before that the feed refused every cricket bet and the listing
    # would have been a label. A Kalshi cricket bet reaches the feed only once its start
    # is verified (start_source "kalshi_milestone"): the milestone, the ticker's Eastern
    # time and any parseable rules time agree, and the match is still pre-match.
    # Otherwise start_source stays unset and placeable() refuses it. Polymarket US
    # cricket carries its own start and is unchanged.
    "oddspedia|cricket": dict(moved_on="2026-09-27", production_at=None),
    # 2026-09-28, as asked. LISTED BUT NOT ACTIONABLE, and that is a fact about the exchange
    # rather than a gap to be closed here, so it is written down instead of quietly retried:
    # Polymarket US publishes no parlay API. Its official SDK (polymarket-us 0.1.2) takes a
    # single `marketSlug` per order and holds no reference to a parlay, combo or basket
    # anywhere in the package, and the public gateway serves no such endpoint. The exchange's
    # own site does have a combo builder, which is why this lane exists and can be PRICED, but
    # nothing reachable acts on one. So placeable() goes on refusing a basket whose legs are
    # not Kalshi markets and no lead is published for it — checked deliberately, since a
    # basket coerced onto one of its legs would be a different contract entirely.
    # The record is also too small to argue from: 4 baskets over 1.1 days, z +0.45, -16.9%
    # without its biggest win, halves -100% then +149%, and nothing new since 2026-09-25.
    # A basket that could actually be acted on has to be the KALSHI twin: Kalshi does publish
    # multivariate_event_collections, KXMVECROSSCATEGORY-R is live, and tennis_combo2 already
    # clears placeable() on 7 leads. What is missing there is downstream, not an exchange.
    #   pm_combo4 — listed 2026-09-28, OUT 2026-10-03. Not on its record: on the fact that
    #   nothing can act on it. Polymarket US publishes no parlay API — its official SDK takes
    #   a single marketSlug per order and holds no reference to a parlay, combo or basket
    #   anywhere in the package, and the gateway serves no such endpoint. The exchange's own
    #   site has a combo builder, which is why the lane can be PRICED, but no reachable
    #   interface places one. Downstream agreed and said so: placeable() refused every
    #   basket whose legs are not Kalshi markets, so in five days as a Production pair it
    #   published zero leads and its Since-Production cell read "nothing in 5d" with no
    #   prospect of ever reading anything else. A pair that cannot be acted on is a label,
    #   and the page should not carry one. Its 4-basket Sandbox record stays on file.
    #   If a basket is ever to be traded it has to be the KALSHI twin: Kalshi does publish
    #   multivariate_event_collections, KXMVECROSSCATEGORY-R is live, and tennis_combo2
    #   already clears placeable(). What is missing there is downstream support, not an
    #   exchange.
    # 2026-09-22, as asked — without waiting for 30 settled. Both are ahead of the price on
    # records too small to read: the MMA favourite band 4-0 (4 won v 3.2 priced, +23.4% after
    # fees, z +1.00), OLBG's boxing tips 3-0 (3 won v 2.7 priced, +11.1%, z +0.59). The
    # demotion net reads their whole record from here. Both keep their Sandbox record.
    # tennis_combo3 — listed 2026-09-23, OUT 2026-09-24, as asked. Not on its record: on the
    # fact that it could not place a bet at all. Its legs must be Kalshi markets, because the
    # basket is quoted through Kalshi's RFQ collection and a Polymarket leg cannot be named in
    # one. Narrowing the tennis band to 0.75-0.80 the same day it was promoted cut the in-band
    # KALSHI legs from 14.1 a day to 6.3, below what a run can see ahead of it, and four
    # consecutive tracker runs built zero baskets while the single-leg rule went on picking 15
    # of 15 on Polymarket US. A pair in Production that cannot fire is worse than no pair: it
    # reads as a live lane and tests nothing.
    #
    # The replacement is pm_combo2/3/4 (SPORTS["tennis_pmcombo"]), the same construction on
    # Polymarket US, where the legs actually are — 14.6 in-band a day against Kalshi's 6.3.
    # It is NOT promoted with this demotion and should not be: it has nothing settled, and
    # placeable() rightly refuses a basket whose legs are not Kalshi markets, so it could not
    # publish a lead today even if listed. It earns a hearing at 30 settled baskets like
    # anything else.
    #   mma_fav_band — listed 2026-09-22, OUT 2026-10-04, removed by Olu. Off every
    #   page, with olbg (boxing and MMA), mlb_fade_streak and nhl_rest_edge. Not a
    #   record call: the lane is taken off the board. The Kalshi-to-Polymarket-US
    #   replacement below stays in place and does not fire, because a removed lane
    #   logs nothing new. The Sandbox rows stay in the ledger.
    # 2026-10-01, as asked. Over 1.5 on the day's top-2 mismatches, internationals
    # only, on Kalshi's over-1.5 Yes. The form-window twin (o15_form_l10) is not
    # listed, and neither is any cup twin. Under 3.5 was not listed on 2026-10-01
    # because those bets are the No side of the over-3.5 market and the feed could
    # only say Yes; that is no longer true — see u35_low_scoring below.
    "o15_ranked|soccer_o15_intl": dict(moved_on="2026-10-01", production_at=None),
    # 2026-10-04, as asked. Under 3.5 goals, internationals only. 18 settled, 17 won
    # against 14.19 priced: +21.4% (+19.6% after fees), z +1.66 over 9.4 days, and it
    # beats its blind rule — backing the under on every Kalshi match returned +2.7% on
    # the same contests, so the rule's part is about +18.7pp. Its closing prices agree,
    # unusually for this Sandbox: +1.17c a bet over 18 closes (t +1.38), beating the
    # close on 12 of 18. Small and one week old, listed on the owner's call.
    #
    # THE FEED HAD TO LEARN A NEW SIDE FOR IT, and that is the honest reason this lane
    # sat unpublished for ten days with the best internationals record in the Sandbox:
    # all 21 of its bets had routed=0, not because anything judged them, but because
    # soccer_u35_intl was not in FEED_BETS and placeable() asked every goals bet for a
    # Yes. An under is the No side of the over-3.5 contract (ticker suffix -4), so
    # FEED_SIDE now carries the side per kind and the lead names its exact contract.
    #
    # WHAT THE ROUTE IS, AND WHAT DOWNSTREAM DOES WITH IT. lead_from_quote puts the
    # contract ticker (the -4 strike) in route.market, "Under 3.5 goals" in
    # route.outcome, and outcome_side "no". That is the No side of Kalshi's over-3.5
    # contract. A routed Kalshi lead does not go through covers() or mapping.NEEDS_SIDE.
    # Those refuse an UNROUTED total_lte only: covers() finds no series suffix for the
    # kind, and NEEDS_SIDE finds no Under price in the verified fields. The routed path
    # looks route.market up as an event ticker. This value is the contract ticker, so
    # that lookup finds no open markets and the lead is refused before any order.
    # The Kalshi order path buys Yes and does not read outcome_side. Rewriting the
    # route into an event ticker plus the Over subtitle would buy Over 3.5, the
    # opposite of the bet. The lead can be taken by hand — Kalshi sells the No on
    # that contract. That downstream change is not made here.
    "u35_low_scoring|soccer_u35_intl": dict(moved_on="2026-10-04", production_at=None),
    #   OLBG boxing — listed 2026-09-22, OUT 2026-09-27, as asked. It went 8-0 on the US
    #   exchanges (+17.4%, +16.3% after fees) and is still taken off, because the win record
    #   is not the point: it backed the FAVOURITE in all nine bets, at prices from 0.64 to
    #   0.95 and a mean of about 0.87, and backing the favourite blindly on those same
    #   contests returned +17.4% too. Exactly the same number. A tipster that ties the blind
    #   rule it is judged against has added nothing — the record is the favourite-longshot
    #   bias, priced, and not the tips. Its closing prices say the same: -8c a bet over 6
    #   closes, so the market moved against the picks while the 8-0 said otherwise. Five of
    #   the nine were also struck on one day, 2026-09-26, so the span is thinner than the
    #   count. The pair keeps its Sandbox record and goes on being measured; what it needs is
    #   evidence it beats favourites, not more favourites that win.
}


def qa_since(pair, sport, key=None):
    """Where a QA pair's judged record starts: its promotion, or — where the sport counts the
    Sandbox record (qa_counts_sandbox) — where its Sandbox record started."""
    if sport_rules(sport).get("qa_counts_sandbox") or key in PAIR_OVERRIDES:
        return pair.get("entry_since")          # None = its whole record
    return pair["promoted_at"]


def sport_rules(sport):
    """The threshold set for `sport` (SPORT_RULES)."""
    return SPORT_RULES["high" if sport in HIGH_VOLUME_SPORTS else "standard"]
STAGES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "stages.json")
# Taker fee per $1 contract at price p, per venue: fee = rate * p * (1 - p). Polymarket US
# charges 0.06, Kalshi 0.07. QA scores what following a source would actually cost.
FEE_RATE = {"polymarket": 0.06, "polymarket_us": 0.06, "kalshi": 0.07, "kalshi_binary": 0.07}

# CLOSING PRICES. The tracker runs every 6h, so its last snapshot before a start could be
# hours early — the first 103 snapshots sat a median 16h before the start. A separate job
# (sandbox_close.py, every 30 minutes) reads the venue's price for just the bets about to
# close and writes CLOSES; this ledger only ever reads that file. Fixed in advance, before
# any CLV was read: a snapshot counts toward closing-line value only when it was taken
# within CLOSE_MAX_LEAD_MIN of the bet's deadline. An older one is kept and shown, never
# scored — a price from the morning is not where the market closed.
CLOSES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "sandbox_closes.json")
# One file per WRITER (2026-09-13). GitHub ran the 30-minute close job 3 times in 13 hours,
# so the snapshot also runs inside the hourly watchdog and every board refresh. Each writes
# only data/sandbox_closes/<writer>.json, so workflows in different concurrency groups
# never commit the same file; load_closes() merges them all, latest snapshot per bet.
CLOSES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "sandbox_closes")
CLOSE_MAX_LEAD_MIN = 60


def now_iso():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


# Every bet leaving the ledger, void included, is archived whole. prune() keeps the
# ledger small by folding old rows into per-source totals, but the stamp and QA are
# judged on individual bets per sport — a rolled-up total cannot say which sport a
# win was in, at what price, or against which blind rule. The whole row goes into a
# month file here (keyed by the month it settled, so old months never change again
# and git stores each once). assess() reads the ledger and the archive together.
# Price-only rows get a compact copy only for an a/b/draw result, for Baseline rows,
# and for one row per contest otherwise. The rest (e.g. result "price", or a contest
# already covered) are rolled up by design because nothing reads them.
ARCHIVE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "sandbox_archive")


def load_archive(path=None):
    """Month files of settled bets copied out of the ledger.

    A file that is not a JSON list fails with that file's name. Skipping it
    would drop a month of bets out of every judgement that reads the archive.
    """
    path = path or ARCHIVE_DIR
    out = []
    if os.path.isdir(path):
        for fn in sorted(os.listdir(path)):
            if not fn.endswith(".json"):
                continue
            fp = os.path.join(path, fn)
            try:
                with open(fp) as f:
                    rows = json.load(f)
            except (OSError, json.JSONDecodeError, UnicodeDecodeError) as e:
                raise RuntimeError(f"malformed archive file {fn}: {e}") from e
            if not isinstance(rows, list):
                raise RuntimeError(
                    f"malformed archive file {fn}: expected a list of bets, "
                    f"got {type(rows).__name__}")
            out += rows
    return out


def all_bets(d):
    """Ledger rows plus archived settled bets — everything a judgement may read.

    This is the raw concatenation, duplicates included. The day-subtotal check
    and the audit both look here for an id that was stored twice. bet_rows()
    is the deduped list the pages count.
    """
    return d["quotes"] + (d.get("_archive") or [])


def _logged_id(q):
    """Sort key that does not depend on which list a row sits in.

    logged alone is not enough. Two Corners rungs can share a logged time, and
    a stable sort would then keep whichever list held the row. id breaks that
    tie the same way before and after a roll-up.
    """
    return (str(q.get("logged") or ""), str(q.get("id") or ""))


# One built list per loaded ledger. hide_removed, hide_refused_tours and a
# roll-up each hand back a new dict with new quotes and archive lists, so they
# miss. A build asks for this about 1,650 times; rebuilding it each time walks
# every live row and every archived row again. The token holds the Python
# object ids of the quotes and archive lists plus both lengths. A status or
# pnl edit on a cached row shows through, because the list holds those row
# objects. An edit to bet, id or logged, or a replaced row object, keeps
# both lengths the same, so the token does not change and the cached list
# is returned as built.
_BET_ROWS_CACHE = {}
_BET_ROWS_MAX = 48


def bet_rows(d):
    """Live quotes plus archived bets, one row per id, sorted by (logged, id).

    The live quote wins a duplicate id. Within the archive the first copy
    wins. Compact price rows are not bets. all_bets() still returns those,
    because a baseline population reads them. A row with no id is kept: there
    is nothing to dedupe it against.

    The order does not depend on which list a row sits in. day_units keeps the
    first same-start rung, so a rung that moves into the archive stays the
    representative it was while it was live. The result is cached for this
    d's quotes and archive lists.
    """
    quotes = d["quotes"]
    archive = d.get("_archive")
    token = (id(quotes), id(archive) if isinstance(archive, list) else 0,
             len(quotes), len(archive) if archive else 0)
    key = id(d)
    hit = _BET_ROWS_CACHE.get(key)
    if hit is not None and hit[0] == token:
        _BET_ROWS_CACHE.pop(key)
        _BET_ROWS_CACHE[key] = hit
        return hit[1]
    seen = set()
    out = []
    for q in all_bets(d):
        if not q.get("bet"):
            continue
        i = q.get("id")
        if i is not None:
            if i in seen:
                continue
            seen.add(i)
        out.append(q)
    out.sort(key=_logged_id)
    if len(_BET_ROWS_CACHE) >= _BET_ROWS_MAX:
        _BET_ROWS_CACHE.pop(next(iter(_BET_ROWS_CACHE)))
    # Pin the lists so a collected ledger cannot have its ids reused under a
    # later dict that happens to share this key.
    _BET_ROWS_CACHE[key] = (token, out, quotes, archive)
    return out


def load():
    if os.path.exists(LEDGER):
        with open(LEDGER) as f:
            d = json.load(f)
        d.setdefault("quotes", [])
        d.setdefault("meta", {})
        d.setdefault("coverage", {})
    else:
        d = {"meta": {"created": now_iso()}, "quotes": [], "coverage": {}}
    d["_archive"] = load_archive()
    # Re-apply the city-day mark on every read. The constant is the rule, the
    # rows keep their original result, and a second read under the same rule
    # changes nothing. A different rule clears the old marks and writes new ones.
    mark_climate_citydays(d)
    return d


def atomic_write_json(path, obj, prefix=".atomic-"):
    """Replace `path` with `obj` as JSON, or leave the previous file untouched.

    The new bytes go to a temp file in the same directory, are flushed and fsynced,
    then moved into place with os.replace. replace on the same filesystem does not
    leave a half-written destination, so a crash mid-write cannot truncate the
    ledger the next run has to read. The temp file is removed if the write fails
    before that replace.
    """
    directory = os.path.dirname(os.path.abspath(path)) or "."
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=prefix, dir=directory)
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(obj, f, indent=1, sort_keys=True)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
        tmp = None
    finally:
        if tmp is not None:
            try:
                os.unlink(tmp)
            except OSError:
                pass


def save(d, archive_dir=None):
    d["meta"]["updated"] = now_iso()
    d["meta"]["runs"] = d["meta"].get("runs", 0) + 1
    dirty = d.pop("_archive_dirty", set())
    archive = d.pop("_archive", None)
    try:
        # Ledger first, archive second. A crash between them leaves the row
        # in retired and not in the archive file. That archive copy is lost:
        # the next prune() cannot re-archive a row that has left the ledger.
        # It does not leave the id in both lists.
        atomic_write_json(LEDGER, d, prefix=".ledger-")
        if dirty and archive is not None:
            save_archive(archive, dirty, archive_dir)
    finally:
        if archive is not None:
            d["_archive"] = archive


def save_archive(archive, months, path=None):
    path = path or ARCHIVE_DIR
    os.makedirs(path, exist_ok=True)
    for month in sorted(months):
        rows = sorted((q for q in archive if str(q.get("settled", ""))[:7] == month),
                      key=lambda q: (q["settled"], q["id"]))
        atomic_write_json(os.path.join(path, f"{month}.json"), rows, prefix=".archive-")


# ---------------------------------------------------------------------------
# Matching challengers onto the Polymarket universe
# ---------------------------------------------------------------------------

def match_quotes(universe, quotes, day_slack=1):
    """Attach each challenger quote to the universe row it is about, ONE-TO-ONE.

    Returns {market_id: ("prob", p) | ("pick", "a"|"b")} oriented to that row.

    Two kinds of opinion arrive here. A model or an exchange gives a PROBABILITY; a
    tipster gives a bare PICK. Both are scoreable for profit, so both are carried — the
    difference only shows up later, in what can be asked of them.

    Two things here are load-bearing.

    Orientation: the challenger may list the fixture the other way round, and a flipped
    probability is not a small error — it is the exact opposite prediction.

    Exclusivity: a day of slack is unavoidable because the feeds disagree on timezone (a
    19:00 ET game is "tomorrow" in UTC), but slack plus a baseball series is a trap. The
    same two teams play on Wednesday AND Thursday, so without exclusivity Wednesday's
    price gets booked against Thursday's game as well — that is how 36 quotes matched 43
    contests on the first run. Pairs are therefore assigned greedily by match strength
    and then date distance, and each quote is consumed at most once.
    """
    out, used_rows, used_quotes = {}, set(), set()
    # A forecast on a yes/no market names the market itself. There are no team names to
    # compare — "83° or above" against "No" means nothing — so those quotes are matched
    # by id and never go near the name matcher.
    index = {r["market_id"]: i for i, r in enumerate(universe)}
    for j, q in enumerate(quotes):
        mid = q.get("market_id")
        if not mid:
            continue
        used_quotes.add(j)
        i = index.get(mid)
        if i is None or i in used_rows:
            continue
        used_rows.add(i)
        out[mid] = (("prob", q["prob_a"]) if q.get("prob_a") is not None
                    else ("pick", q["pick"]))

    cands = []
    for i, row in enumerate(universe):
        if i in used_rows:
            continue
        for j, q in enumerate(quotes):
            if j in used_quotes:
                continue
            score, flipped = S.pair_match(row["side_a"], row["side_b"],
                                          q["a"], q["b"], sport=row["sport"])
            if score <= 0:
                continue
            if q.get("prob_a") is None and q.get("pick") is None:
                continue
            if row["date"] and q.get("date"):
                try:
                    dist = abs((datetime.strptime(row["date"], "%Y-%m-%d")
                                - datetime.strptime(q["date"], "%Y-%m-%d")).days)
                except ValueError:
                    dist = 0
                if dist > day_slack:
                    continue
            else:
                # A dated quote is pinned to its own fixture. An UNDATED one (Oddspedia
                # community tips carry no date) is resolved to the SOONEST fixture
                # between those two sides — the tip is hours old and the universe only
                # holds the next few days, so the nearest game is the one meant. Without
                # this the tie broke on list order, which in a cricket or baseball
                # series is a coin flip between two different games.
                try:
                    dist = max(0, (datetime.strptime(row["date"], "%Y-%m-%d")
                                   .replace(tzinfo=timezone.utc)
                                   - datetime.now(timezone.utc)).days)
                except (ValueError, TypeError):
                    dist = 0
            cands.append((-score, dist, i, j, flipped))

    cands.sort()
    for _neg, _dist, i, j, flipped in cands:
        if i in used_rows or j in used_quotes:
            continue
        used_rows.add(i)
        used_quotes.add(j)
        q = quotes[j]
        if q.get("prob_a") is not None:
            p = q["prob_a"]
            out[universe[i]["market_id"]] = ("prob", 1 - p if flipped else p)
        else:
            side = q["pick"]
            # A draw is the same call whichever way round the fixture is listed.
            if flipped and side in ("a", "b"):
                side = "b" if side == "a" else "a"
            out[universe[i]["market_id"]] = ("pick", side)
    return out


# CONSENSUS PAIRS (2026-09-22). A pair that backs a side only where two named sources both
# back it on the same market. Each source's side comes from a bet it has already logged there
# or from this run's opinion, read the way that source would bet it — a tipster's pick as it
# stands, a probability only where it clears EDGE_MIN against the price. Logged, like a
# tipster, at the going price the moment the two agree.
CONSENSUS = {"cricket_consensus": dict(sport="cricket", sources=("oddspedia", "polymarket"))}


def backed_side(opinion, row):
    """The side an opinion would bet on this row, or None."""
    kind, value = opinion
    if kind == "pick":
        return value
    if row.get("price_draw") is not None:
        return "a" if value - row["price_a"] >= EDGE_MIN else None
    pick, edge, _price = decide(value, row["price_a"], row["price_b"])
    return pick if pick and edge >= EDGE_MIN else None


def consensus_probs(name, rows, source_probs, prior):
    """{market_id: ("pick", side)} where every source of consensus pair `name` backs one side."""
    cfg = CONSENSUS[name]
    by_id = {r["market_id"]: r for r in rows}
    sides = {}
    for src in cfg["sources"]:
        mine = {}
        for q in prior.get((src, cfg["sport"]), ()):
            if q.get("bet") and q.get("pick"):
                mine.setdefault(q["market_id"], q["pick"])
        for mid, opinion in (source_probs.get(src) or {}).items():
            if mid in by_id and mid not in mine:
                side = backed_side(opinion, by_id[mid])
                if side:
                    mine[mid] = side
        sides[src] = mine
    first, *rest = cfg["sources"]
    return {mid: ("pick", side) for mid, side in sides[first].items()
            if mid in by_id and all(sides[o].get(mid) == side for o in rest)}


def decide(prob_a, price_a, price_b):
    """Which side does this probability back, and by how much?

    Returns (pick, edge, price). pick is 'a'/'b'/None.
    """
    edge_a = prob_a - price_a
    edge_b = (1 - prob_a) - price_b
    if edge_a >= edge_b:
        return ("a", edge_a, price_a) if edge_a > 0 else (None, edge_a, price_a)
    return ("b", edge_b, price_b) if edge_b > 0 else (None, edge_b, price_b)


# ---------------------------------------------------------------------------
# Publish
# ---------------------------------------------------------------------------

COMBO_SPORTS = ("tennis_combo", "tennis_pmcombo")


def combo_used_legs(d):
    """{n: leg market ids already in a logged n-leg basket} — see S.tennis_combo_rows.

    Both venues' lanes share one set. A Kalshi leg id (KXATPMATCH-...) is never a Polymarket
    slug, so they cannot block each other; what this does prevent is either lane re-cutting
    its OWN legs into a second basket on a later run, which is the duplication the builder's
    docstring is about. Missing a lane here does not fail loudly — it quietly logs the same
    basket again every three hours.
    """
    used = {}
    for q in d.get("quotes") or []:
        if q.get("sport") in COMBO_SPORTS and q.get("legs"):
            used.setdefault(len(q["legs"]), set()).update(l["market_id"] for l in q["legs"])
    return used


def cricket_verified_log(stats, kept):
    """One line for the Kalshi cricket verified-start log.

    `dropped` mixes two decisions. A status that is not a known pre-match
    string is not a start that has already passed, and the line names each.
    `kept` is how many rows remain after the call, so kept + dropped is the
    number that went in.
    """
    status_n = int(stats.get("dropped_status") or 0)
    started_n = int(stats.get("dropped_started") or 0)
    matched = int(stats.get("matched") or 0)
    dropped = int(stats.get("dropped") or 0)
    unverified = int(stats.get("unverified") or 0)
    return (f"  Cricket       milestones: {matched} of {kept + dropped} "
            f"Kalshi starts verified, {status_n} dropped for status, "
            f"{started_n} already under way, {unverified} unverified")


def collect(verbose=True, combo_used=None):
    """Fetch the universe for every sport. Returns (universe_by_sport, coverage).

    Polymarket is the venue wherever it lists a contest. Kalshi fills in what it does
    not: all of soccer — Polymarket lists one or two soccer MATCHES a day, in leagues no
    tipster covers — and any individual fight, match or game Polymarket is missing in the
    other sports. A contest listed on both stays on Polymarket, so nothing is priced
    twice and no bet can be booked against two different prices for one game.
    """
    universe, coverage = {}, {}
    goals = nhl = None
    for sport in S.SPORTS:
        t0 = time.time()
        # Weather markets are not fetched. Climate is the Kalshi temperature
        # ladder; leaving it out of the universe means that read never runs.
        # Table tennis and MLB venue listings are the same: no kept lane reads them.
        if sport in S.REMOVED_SPORTS or sport in S.REMOVED_VENUE_SPORTS:
            universe[sport] = []
            continue
        # Each venue, for each sport, fails on its own. A dropped connection fetching NFL
        # used to take the whole run down with it — no grading, nothing saved — when the
        # right outcome is one empty sport and everything else carrying on.
        if sport == "tennis_pmcombo":
            # The Polymarket US twin of the Kalshi basket lane. Derived from the same tennis
            # rows, so it costs no fetch; SPORTS lists it after tennis, as tennis_combo is.
            try:
                rows = S.pm_tennis_combo_rows(universe, used=combo_used)
                legs = S.pm_combo_legs_by_day(universe)
            except Exception as e:
                print(f"  ! tennis_pmcombo build failed: {type(e).__name__}: {str(e)[:70]}")
                rows, legs = [], {}
            universe[sport] = rows
            coverage.setdefault(sport, {})["combo"] = len(rows)
            n_legs = sum(len(v) for v in legs.values())
            coverage[sport]["legs"] = n_legs
            if verbose:
                why = ""
                if not rows:
                    lo, hi = S.TENNIS_3H_BAND
                    best = max((len(v) for v in legs.values()), default=0)
                    why = (f" -- {n_legs} in-band Polymarket US legs ({lo:.2f}-{hi:.2f}), most "
                           f"on any one day {best}, smallest basket needs {min(S.COMBO_LEGS)}")
                print(f"  {S.SPORTS[sport]:<13} built {len(rows)} baskets from the day's "
                      f"favourite-band legs{why} ({time.time() - t0:.0f}s)")
            continue
        if sport == "tennis_combo":
            # Derived, never fetched: the baskets are built from the tennis rows this same
            # run already priced, so a leg and the basket holding it always carry the same
            # number. SPORTS lists this domain after tennis, so those rows exist by now.
            try:
                rows = S.tennis_combo_rows(universe, used=combo_used)
                legs = S.combo_legs_by_day(universe)
            except Exception as e:
                print(f"  ! tennis_combo build failed: {type(e).__name__}: {str(e)[:70]}")
                rows, legs = [], {}
            universe[sport] = rows
            coverage.setdefault(sport, {})["combo"] = len(rows)
            # A bare "0 baskets" hides the two reasons it happens -- no in-band Kalshi legs at
            # all, or too few on any one day to cut the smallest basket -- and those need
            # different answers. Say which, so a starved lane cannot look like a broken one.
            n_legs = sum(len(v) for v in legs.values())
            coverage[sport]["legs"] = n_legs
            if verbose:
                why = ""
                if not rows:
                    lo, hi = S.TENNIS_3H_BAND
                    best = max((len(v) for v in legs.values()), default=0)
                    why = (f" -- {n_legs} in-band Kalshi legs ({lo:.2f}-{hi:.2f}), most on any "
                           f"one day {best}, and the smallest basket needs {min(S.COMBO_LEGS)}")
                print(f"  {S.SPORTS[sport]:<13} built {len(rows)} baskets from the day's "
                      f"favourite-band legs{why} ({time.time() - t0:.0f}s)")
            continue
        if sport == "soccer_corners":
            cstats = {}
            try:
                rows = S.fetch_kalshi_corners(stats=cstats)
            except Exception as e:
                print(f"  ! kalshi/soccer_corners failed: {type(e).__name__}: {str(e)[:70]}")
                rows = []
            universe[sport] = rows
            coverage.setdefault(sport, {})["kalshi_venue"] = len(rows)
            if verbose:
                print(f"  {S.SPORTS[sport]:<13} kalshi corners: {cstats.get('listed', 0)} listed, "
                      f"{len(rows)} matched to an ESPN fixture ({time.time() - t0:.0f}s)")
            continue
        if sport in S.BTTS_SPORTS:
            bstats = {}
            try:
                rows = S.fetch_kalshi_btts(stats=bstats, scope=sport[len("soccer_btts"):])
            except Exception as e:
                print(f"  ! kalshi/{sport} failed: {type(e).__name__}: {str(e)[:70]}")
                rows = []
            universe[sport] = rows
            coverage.setdefault(sport, {})["kalshi_venue"] = len(rows)
            if verbose:
                print(f"  {S.SPORTS[sport]:<13} kalshi BTTS: {bstats.get('listed', 0)} listed, "
                      f"{len(rows)} matched to an ESPN fixture ({time.time() - t0:.0f}s)")
            continue
        if sport in S.GOALS_SPORTS:
            if goals is None:                         # one fetch serves all three domains
                gstats = {}
                try:
                    goals = S.fetch_kalshi_goals(stats=gstats)
                except Exception as e:
                    print(f"  ! kalshi/soccer goals failed: {type(e).__name__}: {str(e)[:70]}")
                    goals, gstats = {}, {}
                if verbose:
                    print(f"  Soccer goals  kalshi totals: {gstats.get('listed', 0)} listed, "
                          + ", ".join(f"{len(goals.get(g) or [])} {S.SPORTS[g]}" for g in S.GOALS_SPORTS)
                          + f" matched to an ESPN fixture ({time.time() - t0:.0f}s)")
            universe[sport] = goals.get(sport) or []
            coverage.setdefault(sport, {})["kalshi_venue"] = len(universe[sport])
            continue
        if sport in S.NHL_SPORTS:
            if nhl is None:                           # one fetch serves both NHL domains
                nstats = {}
                try:
                    nhl = S.fetch_nhl(stats=nstats)
                except Exception as e:
                    print(f"  ! kalshi/nhl failed: {type(e).__name__}: {str(e)[:70]}")
                    nhl, nstats = {}, {}
                if verbose:
                    print(f"  NHL           kalshi: {nstats.get('listed', 0)} events listed, "
                          + ", ".join(f"{len(nhl.get(n) or [])} {S.SPORTS[n]}" for n in S.NHL_SPORTS)
                          + f" matched to the NHL schedule ({time.time() - t0:.0f}s)")
            universe[sport] = nhl.get(sport) or []
            coverage.setdefault(sport, {})["kalshi_venue"] = len(universe[sport])
            continue
        if sport in S.KALSHI_BINARY:
            kstats = {}
            try:
                rows = S.fetch_kalshi_binary(sport, stats=kstats)
            except Exception as e:
                print(f"  ! kalshi/{sport} failed: {type(e).__name__}: {str(e)[:70]}")
                rows = []
            universe[sport] = rows
            coverage.setdefault(sport, {})["kalshi_venue"] = len(rows)
            if verbose:
                print(f"  {S.SPORTS[sport]:<13} kalshi yes/no: {kstats.get('listed', 0)} "
                      f"near-dated, {len(rows)} taken ({time.time() - t0:.0f}s)")
            continue
        if sport in ("politics", "elections"):
            # Tracked as domains, but not fetched: Kalshi lists thousands of political
            # questions and almost none resolve inside this board's horizon, so there is
            # nothing here that could settle and be scored.
            universe[sport] = []
            continue

        stats = {}
        try:
            # Polymarket US, not polymarket.com: the venue has to be one a US account can use.
            pm = [] if sport == "soccer" else S.fetch_polymarket_us(sport, stats=stats)
        except Exception as e:
            print(f"  ! polymarket_us/{sport} failed: {type(e).__name__}: {str(e)[:70]}")
            pm = []
        kstats = {}
        try:
            ks = S.fetch_kalshi_venue(sport, stats=kstats)
        except Exception as e:
            print(f"  ! kalshi/{sport} failed: {type(e).__name__}: {str(e)[:70]}")
            ks = []
        if sport == "tennis":
            # Before the dedupe. The tour book is the open Kalshi markets,
            # which apply_pm_atp_tours reads from the cache, not the rows
            # whose estimated start has already been dropped. A Challenger
            # that Polymarket also lists would otherwise leave the universe
            # as the Polymarket row alone, and the atp slug would be the
            # only tour signal left.
            S.apply_pm_atp_tours(pm, ks)
        extra = [k for k in ks if not any(_same_contest(k, p) for p in pm)]
        if sport == "tennis" and extra:
            # Kalshi publishes no start for a tennis match, only an estimate; the schedule
            # confirms it. Unverified rows stay in the universe. tennis_fav_band_3h does
            # not treat the estimate as inside its window. They never reach the
            # Production feed. See S.apply_tennis_starts.
            extra, tstats = S.apply_tennis_starts(extra)
            if verbose and tstats.get("feed"):
                print(f"  Tennis        schedule: {tstats['matched']} of {len(extra) + tstats['dropped']} "
                      f"Kalshi starts verified, {tstats['dropped']} already under way")
        if sport == "mma" and extra:
            # Kalshi publishes no kickoff for a fight, only an estimate, so a Kalshi MMA row
            # is unpublishable until its own milestone agrees. See S.apply_kalshi_mma_starts.
            # An outage leaves the estimate in place and the rows simply stay unverified.
            try:
                extra, mstats = S.apply_kalshi_mma_starts(extra)
                if verbose and mstats.get("feed"):
                    print(f"  MMA           schedule: {mstats['matched']} Kalshi starts verified, "
                          f"{mstats['unverified']} unverified, {mstats['dropped']} already under way")
            except Exception as e:
                print(f"  ! kalshi mma starts failed: {type(e).__name__}: {str(e)[:60]}")
        if sport == "cricket" and extra:
            # The estimate above is only a logging cutoff. A row is publishable once
            # Kalshi's milestone, the ticker and the rules agree. See
            # S.apply_kalshi_cricket_starts. An outage leaves the estimate in place.
            try:
                extra, ct = S.apply_kalshi_cricket_starts(extra)
                if verbose and ct.get("feed"):
                    print(cricket_verified_log(ct, len(extra)))
            except Exception as e:
                print(f"  ! kalshi cricket starts failed: {type(e).__name__}: {str(e)[:60]}")
        universe[sport] = pm + extra
        if sport == "soccer":
            # Kalshi has no kickoff time; ESPN does. See S.apply_espn_starts.
            try:
                universe[sport], et = S.apply_espn_starts(universe[sport])
                if verbose:
                    sh = sorted(abs(x) for x in et["shifts"])
                    print(f"  {S.SPORTS[sport]:<13} start times: {et['matched']} from ESPN, "
                          f"{et['dropped']} dropped as started"
                          + (f", median |shift| {sh[len(sh)//2]:.0f} min, largest {sh[-1]:.0f}"
                             if sh else ""))
            except Exception as e:
                print(f"  ! espn start times failed: {type(e).__name__}: {str(e)[:60]}")
        if sport in S.START_FROM_PINNACLE:
            # Fight nights: re-time every bout from Pinnacle's own commence time. Rows
            # it cannot re-time keep the venue's start and follow the usual rule.
            try:
                universe[sport], rt = S.apply_pinnacle_starts(sport, universe[sport])
            except Exception as e:
                print(f"  ! pinnacle start times/{sport} failed: {type(e).__name__}: "
                      f"{str(e)[:60]}")
                now_ = datetime.now(timezone.utc)
                universe[sport] = [r for r in universe[sport]
                                   if datetime.fromisoformat(str(r["start"]))
                                   >= now_ - timedelta(minutes=5)]
                rt = dict(matched=0, dropped=0, shifts=[])
            if verbose:
                sh = sorted(rt["shifts"])
                med = f", median shift {sh[len(sh) // 2]:+.0f} min" if sh else ""
                print(f"  {S.SPORTS[sport]:<13} start times: {rt['matched']} from Pinnacle, "
                      f"{rt['dropped']} dropped as started{med}")
        cov = coverage.setdefault(sport, {})
        cov["polymarket_us"] = len(pm)
        cov["polymarket_us_listed"] = stats.get("listed", len(pm))
        cov["polymarket_us_priced"] = stats.get("priced", 0)
        cov["kalshi_venue"] = len(extra)
        if verbose:
            print(f"  {S.SPORTS[sport]:<13} polymarket US: {len(pm)} taken | kalshi: "
                  f"{kstats.get('listed', len(ks))} listed, {len(extra)} added "
                  f"({time.time() - t0:.0f}s)")
    return universe, coverage


def _same_contest(a, b, day_slack=1):
    """Is Kalshi row `a` the same contest as Polymarket row `b`?

    This check errs toward YES — the opposite of tipster matching — because the two
    mistakes are not equal. Calling two contests the same wrongly drops one gap-fill
    game. Calling one contest two different ones puts the same game in the universe
    twice, once per venue, and a source can then be logged against the Polymarket copy
    in one run and the Kalshi copy in the next: one bet, counted twice. Kalshi's "A's"
    against Polymarket's "Athletics", and "Mikaelyan" against "Mikaelian", both slipped
    through the strict matcher exactly that way.
    """
    try:
        dist = abs((datetime.strptime(a["date"], "%Y-%m-%d")
                    - datetime.strptime(b["date"], "%Y-%m-%d")).days)
        if dist > day_slack:
            return False
    except (ValueError, TypeError):
        pass
    score, _ = S.pair_match(a["side_a"], a["side_b"], b["side_a"], b["side_b"],
                            sport=a["sport"])
    if score > 0:
        return True
    return ((_loosely_same(a["side_a"], b["side_a"]) and _loosely_same(a["side_b"], b["side_b"]))
            or (_loosely_same(a["side_a"], b["side_b"])
                and _loosely_same(a["side_b"], b["side_a"])))


def _loosely_same(x, y, ratio=0.8):
    """Share a word, or have a long word spelled almost the same (a transliteration)."""
    tx, ty = S.tokens(x), S.tokens(y)
    if tx & ty:
        return True
    return any(difflib.SequenceMatcher(None, p, q).ratio() >= ratio
               for p in tx for q in ty if len(p) > 3 and len(q) > 3)


def _started(row, now):
    """Has this contest started (or is its start unreadable)? Either way, no quote."""
    try:
        start = datetime.fromisoformat(str(row["start"]))
    except (KeyError, TypeError, ValueError):
        return True
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    return start <= now


def pinnacle_retired(d, n=None):
    """Sports where Pinnacle has PINNACLE_RETIRE_N quotes and never once reached the edge."""
    n = n or S.PINNACLE_RETIRE_N
    seen = {}
    for q in d["quotes"]:
        if q["source"] != "pinnacle" or q["status"] == "void":
            continue
        k = seen.setdefault(q["sport"], [0, False])
        k[0] += 1
        k[1] = k[1] or bool(q.get("bet"))
    return {sp for sp, (cnt, bet) in seen.items() if cnt >= n and not bet}


def _listed_pmus(row):
    """True when `row` is a Polymarket US quote a follower could trade."""
    if row.get("venue") != "polymarket_us" or row.get("untraded"):
        return False
    for side in ("a", "b"):
        if row.get(f"price_{side}") is None:
            continue
        if (row.get("tradeable") or {}).get(side, True):
            return True
    return False


def _band_side(row, sport):
    """The side whose ask sits in this sport's favourite band, when that side is tradeable."""
    lo, hi = S.fav_band(sport)
    if row.get("price_draw") is not None:
        return None
    for side in ("a", "b"):
        price = row.get(f"price_{side}")
        if price is None or not (lo <= float(price) < hi):
            continue
        if not (row.get("tradeable") or {}).get(side, True):
            continue
        return side
    return None


def _pmus_for_fight(rows, quote):
    """The tradeable Polymarket US row for `quote`'s fight, or None."""
    sport = quote.get("sport")
    for row in rows:
        if not _listed_pmus(row):
            continue
        other = row if row.get("sport") else dict(row, sport=sport)
        if _same_contest_quote(quote, other):
            return row
    return None


def _clock():
    """Wall clock. A test may replace this so time can pass during a fetch."""
    return datetime.now(timezone.utc)


def _as_utc(now):
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return now


def _replacement_ready(row, now):
    """True when this Polymarket US row can be logged as the favourite-band bet.

    Listed, priced inside the band, and not started. An out-of-band ask, or a
    fight Polymarket US has already started, is not a replacement.
    """
    if row.get("venue") != "polymarket_us" or row.get("untraded"):
        return False
    if _band_side(row, row.get("sport") or "mma") is None:
        return False
    return not _started(row, now)


def _prior_blocks(name, prior_q, row, now):
    """Does an existing quote stop a new one on the same contest?

    A Kalshi MMA bet retired as unplaceable blocks every further entry except the
    one Polymarket US replacement. An open Kalshi bet blocks too, unless this row
    is the replacement that will be logged in the same pass. Any other quote,
    including any other retirement, still blocks. Two live entries on one fight
    never both pass.
    """
    if name == "mma_fav_band" and row.get("venue") == "polymarket_us":
        if prior_q.get("note") == KALSHI_UNPLACEABLE:
            return False
        if (prior_q.get("venue") == "kalshi" and prior_q.get("status") == "open"
                and prior_q.get("bet") and not _started(prior_q, now)
                and _replacement_ready(row, now)):
            return False
    return True


def _retire_replaced_kalshi(d, row, stamp, now):
    """Retire the open Kalshi bet this Polymarket US row is replacing.

    Called only once that replacement is about to be logged. A fight Polymarket
    US has already started, an ask outside the band, or a paused lane leaves the
    Kalshi row untouched. `stamp` is the publish-start clock, not the log time.
    """
    if S.lane_paused("mma_fav_band", "mma") or not _replacement_ready(row, now):
        return 0
    probe = dict(row, sport=row.get("sport") or "mma")
    n = 0
    for q in d.get("quotes") or []:
        if (q.get("source") != "mma_fav_band" or q.get("sport") != "mma"
                or q.get("venue") != "kalshi" or q.get("status") != "open"
                or not q.get("bet")):
            continue
        if _started(q, now) or not _same_contest_quote(q, probe):
            continue
        q["status"] = "void"
        q["bet"] = False
        q["stake"] = 0.0
        q["pnl"] = 0.0
        q["result"] = None
        q["note"] = KALSHI_UNPLACEABLE
        q["settled"] = stamp
        n += 1
    return n


# KXBTCD-26OCT0617-T84750 -> series KXBTCD, close 26OCT0617. The strike is the
# tail. Two rungs of one coin's close share the series and this token.
_COIN_CLOSE_RE = re.compile(r"^([A-Z0-9]+)-(\d{2}[A-Z]{3}\d{4})(?:-|$)")


def _book_fields(r):
    """bid, ask and ask size from a Kalshi universe row's own market, for a lane that
    registers store_book. Missing numbers stay out rather than being written as None."""
    m = r.get("market") or {}
    out = {}
    bid, ask = S._num(m.get("yes_bid_dollars")), S._num(m.get("yes_ask_dollars"))
    size = S._num(m.get("yes_ask_size_fp"))
    if size is None:
        size = S._num(m.get("yes_ask_size"))
    if bid is not None:
        out["bid"] = round(bid, 4)
    if ask is not None:
        out["ask"] = round(ask, 4)
    if size is not None:
        out["ask_size"] = size
    return out


def _coin_close(market_id):
    """Series and close token from a Kalshi coin ticker, or None.

    'KXBTCD-26OCT0617-T84750' -> ('KXBTCD', '26OCT0617'). A decimal strike
    (T119.9999) stays outside the token. A ticker with no date-hour token
    does not match; the id gate still applies to it.
    """
    m = _COIN_CLOSE_RE.match(str(market_id or "").strip().upper())
    if not m:
        return None
    return m.group(1), m.group(2)


def publish(d, universe, coverage, verbose=True, now=None):
    """Log one quote per (source, market) for every source with an opinion."""
    # Retirement uses one clock, taken as publish begins. Each new quote is
    # checked and stamped at the moment it is logged. A fetch that runs past a
    # start must not log that contest against the earlier clock, and must not
    # back-date `logged` so retire_late misses it. A caller that passes `now`
    # pins both, so a frozen test does not read the wall clock.
    pinned = now is not None
    opened = _as_utc(now) if pinned else _clock()
    retire_stamp = opened.replace(microsecond=0).isoformat()

    def log_now():
        if pinned:
            return opened
        return _as_utc(_clock())

    seen = {q["id"] for q in d["quotes"]}
    # What each source has already said, by contest — so a contest listed under a new market
    # id (a venue switch, or the same game on two exchanges) is never quoted twice.
    # Voids do not block, except an MMA favourite-band retirement: that one still
    # blocks a second bet, unless it is the Kalshi row this run just marked unplaceable
    # and the new row is its Polymarket US replacement.
    prior = {}
    for q in d["quotes"]:
        if q.get("status") == "void" and not (
                q.get("source") == "mma_fav_band" and q.get("sport") == "mma"):
            continue
        prior.setdefault((q["source"], q["sport"]), []).append(q)
    # crypto_fav_band: one bet per coin per close. The id gate is the ticker,
    # and the ticker includes the strike, so the next rung is a new id. The
    # key is the series plus the date-hour token. A row already in the ledger,
    # the archive, or logged earlier in this pass blocks the new candidate.
    # The first row keeps the price it was logged at. No other lane sets
    # one_per_coin_close, so this set stays empty for them.
    coin_close = {}
    for q in d["quotes"] + (d.get("_archive") or []):
        src = q.get("source")
        if not (S.SOURCES.get(src) or {}).get("one_per_coin_close"):
            continue
        key = _coin_close(q.get("market_id"))
        if key:
            coin_close.setdefault(src, set()).add(key)
    added = 0
    # Adapters that pay per page (SportsGambler) read this to skip fixtures no venue
    # prices — a page that can never be scored is not worth a polite second of waiting.
    S.UNIVERSE = universe
    S.FEED_STATUS.clear()
    S.reset_examined()
    # nws and nws_fade share one forecast read. Cleared here so a previous run's
    # picks cannot be reused, and again on the way out.
    S.clear_nws_run()

    # Contests some covering source (tipster, model, book, forecaster) has ever quoted.
    covering = {n for n, m in S.SOURCES.items() if m["kind"] in S.COVERING_KINDS}
    covered = {}
    for q in d["quotes"]:
        if q["source"] in covering:
            covered.setdefault(q["sport"], set()).add(q["market_id"])
    per_sport = {}

    for sport, rows in universe.items():
        if not rows:
            # Nothing on the board. Record 0 of 0 for each lane that would have
            # read this sport, so an empty offer is distinct from a missing cell.
            for name in S.CHALLENGERS:
                if sport not in S.SOURCES[name]["sports"]:
                    continue
                if S.fetch_skipped(name, sport):
                    continue
                coverage.setdefault(sport, {})[name] = {"picked": 0, "offered": 0}
            continue
        by_id = {r["market_id"]: r for r in rows}

        # The market itself. Priced at its own price, so its edge is 0 by construction
        # and it never bets — it is here for the Brier column, as the accuracy bar every
        # challenger has to clear.
        # Only where Polymarket IS the venue. A Kalshi-venue row carries Kalshi's price,
        # and a Polymarket "self-quote" at someone else's price would be a fiction.
        # Its probability is the MIDPOINT: the row's price_a is now the ask a follower
        # pays, and scoring the market's own accuracy on an ask would add half the spread
        # to every Brier term.
        # The exchange's own midpoint, under the exchange's own name: Polymarket US rows as
        # "polymarket_us"; a row with no venue, or "polymarket", is polymarket.com (the
        # venue before 2026-09-13) and keeps the name it always had.
        source_probs = {"polymarket_us": {}, "polymarket": {}}
        for r in rows:
            v = r.get("venue", "polymarket")
            if v in source_probs:
                source_probs[v][r["market_id"]] = ("prob", r.get("mid_a", r["price_a"]))

        for name, fetch in S.CHALLENGERS.items():
            if sport not in S.SOURCES[name]["sports"]:
                continue
            # A removed lane is not fetched. A source the pause list silences on
            # every sport is not fetched either. A partial pause still fetches:
            # OLBG boxing is logged from that same pass. ESPN FPI NFL is fetched;
            # its MLB lane is not.
            if S.fetch_skipped(name, sport):
                continue
            t0 = time.time()
            try:
                quotes = fetch(sport)
            except Exception as e:                      # never let one dead feed kill the run
                print(f"  ! {name}/{sport} fetch failed: {str(e)[:70]}")
                quotes = []
            # Kalshi cannot be scored where Kalshi IS the venue: its opinion and the
            # price it would be measured against are the same number.
            pool = (rows if name != "kalshi"
                    else [r for r in rows if r.get("venue", "polymarket") != "kalshi"])
            if name == "polymarket":
                # polymarket.com is a comparison source, not the venue: only against rows
                # priced on another exchange.
                pool = [r for r in pool if r.get("venue", "polymarket") != "polymarket"]
            matched = match_quotes(pool, quotes)
            source_probs[name] = matched
            # A lane that counted its own series reports that count, including
            # zero. Any other source was offered the pool match_quotes saw.
            offered = S.take_examined(name, sport)
            if offered is None:
                offered = len(pool)
            coverage.setdefault(sport, {})[name] = {"picked": len(matched), "offered": int(offered)}
            if name in covering:
                covered.setdefault(sport, set()).update(matched)
            if verbose:
                print(f"  {S.SPORTS[sport]:<13} {name}: {len(quotes)} quotes -> "
                      f"{len(matched)} matched ({time.time() - t0:.0f}s)")
        per_sport[sport] = (by_id, source_probs)

    # Pinnacle LAST and across every sport at once, so its credits go to the contests
    # nothing above covered. A fully paused lane spends nothing: a paid call whose
    # quotes would be thrown away is not a measurement.
    t0 = time.time()
    if S.source_fully_paused("pinnacle"):
        pin = {}
        if verbose:
            print("  pinnacle: paused, no new entries and no paid call")
    else:
        try:
            pin = S.plan_pinnacle(universe, covered, retired=pinnacle_retired(d))
        except Exception as e:
            print(f"  ! pinnacle plan failed: {type(e).__name__}: {str(e)[:70]}")
            pin = {}
    for sport, quotes in pin.items():
        if sport not in per_sport:
            continue
        by_id, source_probs = per_sport[sport]
        matched = match_quotes(universe[sport], quotes)
        source_probs["pinnacle"] = matched
        coverage.setdefault(sport, {})["pinnacle"] = {
            "picked": len(matched), "offered": len(universe.get(sport) or [])}
        if verbose:
            unc = sum(1 for mid in matched if mid not in (covered.get(sport) or set()))
            print(f"  {S.SPORTS[sport]:<13} pinnacle: {len(quotes)} quotes -> {len(matched)} "
                  f"matched, {unc} on contests nothing else covers")
    if verbose and S.ODDS_USAGE:
        u = S.ODDS_USAGE
        print(f"  pinnacle credits: {u.get('calls', 0)}/{u.get('allowance', '?')} paid calls, "
              f"{u.get('remaining', '?')} left, {u.get('stale', 0)} stale lines skipped "
              f"({time.time() - t0:.0f}s)")

    # Consensus pairs, once every source has spoken for this run and before anything is logged.
    for name, cfg in CONSENSUS.items():
        if cfg["sport"] in per_sport and (S.SOURCES.get(name) or {}).get("connected"):
            by_id, source_probs = per_sport[cfg["sport"]]
            source_probs[name] = consensus_probs(name, list(by_id.values()), source_probs, prior)
            coverage.setdefault(cfg["sport"], {})[name] = {
                "picked": len(source_probs[name]), "offered": len(by_id)}

    for sport, (by_id, source_probs) in per_sport.items():
        for name, probs in source_probs.items():
            for mid, opinion in probs.items():
                # A pause stops a new entry and nothing else. Logging the row with
                # the stake cleared would still consume the one quote a source gets
                # on a market, so turning the lane back on could not enter it.
                # Rows already in the ledger are not read here; grade() settles
                # them as before. See S.PAUSED_LANES.
                if S.lane_paused(name, sport):
                    continue
                qid = f"{name}:{mid}"
                if qid in seen:
                    continue
                r = by_id[mid]
                # mma_fav_band only. Polymarket US is the venue when it lists the fight.
                # Kalshi is used only when it does not. Every other rule keeps the
                # universe order it had: first row logged, the other blocked as the
                # same contest.
                if (name == "mma_fav_band" and r.get("venue") != "polymarket_us"
                        and _pmus_for_fight(by_id.values(), dict(r, sport=sport))):
                    continue
                probe = dict(sport=sport, start=r["start"], side_a=r["side_a"], side_b=r["side_b"],
                             market_id=mid, venue=r.get("venue", "polymarket"))
                # Per source, on purpose. tennis_fav_band and tennis_fav_band_3h
                # may both log one match, and nws_fade may log the market nws would
                # have logged. That overlap is the comparison. Neither quote is a
                # duplicate of the other, and neither can void the other.
                at = log_now()
                if any(_same_contest_quote(p, probe) and _prior_blocks(name, p, r, at)
                       for p in prior.get((name, sport), ())):
                    continue
                # A rule registered as one bet a day gets one bet a day, even when two runs
                # fall inside its window and prices have moved it onto a different strike.
                if (S.SOURCES.get(name) or {}).get("one_per_day") and any(
                        p.get("date") == r["date"] for p in prior.get((name, sport), ())):
                    continue
                # Per coin per close, for a lane that registers the flag. A
                # different coin, or the same coin on a later close, still logs.
                if (S.SOURCES.get(name) or {}).get("one_per_coin_close"):
                    key = _coin_close(mid)
                    if key and key in coin_close.get(name, ()):
                        continue
                # Strictly before the start, for every source and every venue, checked at
                # the moment of logging. The venue feeds keep a contest for five minutes
                # past its start to absorb clock skew, and that window let a tip on Al
                # Wahda v Sharjah be logged 74 seconds after kickoff — it won, +$178. A
                # quote logged once play has begun is not a prediction.
                if _started(r, at):
                    continue
                # No book, no quote — for ANY source, not just the market's own. A quote
                # is logged once and never revised, so logging a tip against a placeholder
                # price would freeze it at a price that never existed. Skipping instead
                # leaves the contest to be quoted on a later run, once money arrives and
                # the price is real — still before the start, so still a prediction.
                if r["untraded"]:
                    continue

                kind, value = opinion
                if kind == "prob":
                    prob_a = value
                    if r.get("price_draw") is not None:
                        # Three-way. 1 - P(home) is not P(away); it also contains the
                        # draw, so the usual complement would invent an away-side edge
                        # out of draw probability. Only the quoted side is evaluated.
                        edge = prob_a - r["price_a"]
                        pick, price = ("a", r["price_a"]) if edge > 0 else (None, r["price_a"])
                    else:
                        pick, edge, price = decide(prob_a, r["price_a"], r["price_b"])
                    has_edge = pick is not None and edge >= EDGE_MIN
                else:
                    # A bare pick carries no claim about HOW WRONG the price is, so
                    # there is no edge to threshold. It is simply backed at the going
                    # price — which is how a tipster is actually followed, and it means
                    # a tipster turns over far more bets than a model does.
                    prob_a, pick = None, value
                    if pick == "draw":
                        price = r.get("price_draw")
                    else:
                        price = r["price_a"] if pick == "a" else r["price_b"]
                    edge, has_edge = None, True
                # An untraded 0.50/0.50 book is a placeholder, not a price. Scoring a
                # source against it would manufacture a 'edge' out of nothing.
                # Liquidity is per OUTCOME: on Kalshi one side of an event can be a tight
                # book while another is an untraded 0.02/0.81 placeholder.
                tradeable = (r.get("tradeable") or {}).get(pick, True) if pick else False
                lo, hi = price_band(sport)
                bet = bool(pick and has_edge and not r["untraded"] and tradeable
                           and price is not None and lo <= price <= hi)
                # Retire the Kalshi row only in the same pass that logs its
                # Polymarket US replacement. The retired time is the clock from
                # the start of publish; `logged` on the new row is `at`.
                if name == "mma_fav_band" and bet and r.get("venue") == "polymarket_us":
                    _retire_replaced_kalshi(d, dict(r, sport=sport), retire_stamp, at)
                _tier = (S.tennis_logged_tier(r, mid) if str(sport).startswith("tennis") else None)
                d["quotes"].append(dict(
                    id=qid, source=name, sport=sport, market_id=mid,
                    label=r["label"], side_a=r["side_a"], side_b=r["side_b"],
                    url=r["url"], date=r["date"], start=r["start"],
                    logged=at.replace(microsecond=0).isoformat(),
                    prob_a=round(prob_a, 4) if prob_a is not None else None,
                    price_a=round(r["price_a"], 4), price_b=round(r["price_b"], 4),
                    price_draw=(round(r["price_draw"], 4)
                                if r.get("price_draw") is not None else None),
                    pick=pick, edge=round(edge, 4) if edge is not None else None,
                    price=round(price, 4) if pick and price is not None else None,
                    bet=bet, stake=STAKE if bet else 0.0, untraded=r["untraded"],
                    venue=r.get("venue", "polymarket"),
                    spread=r.get("spread"), liquidity=r.get("liquidity"),
                    # Fight rows: where the start came from, and the venue's own, so a
                    # re-timed bout can be audited against the real walk-out later.
                    start_source=r.get("start_source"), venue_start=r.get("venue_start"),
                    # Soccer yes/no rows: the ESPN fixture and side the market is about, so a
                    # Production lead can name them without re-matching.
                    **{k: r[k] for k in ("league", "espn_home", "espn_away", "team", "opponent")
                       if r.get(k) and r.get("venue") == "kalshi_binary"},
                    # A combo basket carries its legs, because that is the only thing that
                    # can settle it later. Stored on the quote rather than looked up again,
                    # so the basket is judged on exactly the legs it was bought with.
                    **({"legs": r["legs"]} if r.get("legs") else {}),
                    # Tennis: which tour. An atp-league Polymarket row carries the
                    # resolved tour, not the slug. Unknown stays unstamped rather
                    # than being written down as ATP.
                    **({"tier": _tier} if _tier else {}),
                    **({"tour": r.get("tour")} if r.get("tour") in S.TENNIS_TIERS else {}),
                    # The book a rung was taken at, for a lane that registers
                    # store_book (commod_fav_band). Every other lane's row is as before.
                    **(_book_fields(r) if (S.SOURCES.get(name) or {}).get("store_book") else {}),
                    # Pinnacle only: was this a contest nothing else had covered? That is
                    # the Pinnacle-versus-venue rule's own lane, reported separately.
                    uncovered=(mid not in (covered.get(sport) or set())
                               if name == "pinnacle" else None),
                    status="open", pnl=0.0, result=None, settled=None,
                ))
                seen.add(qid)
                prior.setdefault((name, sport), []).append(d["quotes"][-1])
                if (S.SOURCES.get(name) or {}).get("one_per_coin_close"):
                    key = _coin_close(mid)
                    if key:
                        coin_close.setdefault(name, set()).add(key)
                added += 1

    snapped = snap_closing(d, universe)

    d["coverage"] = coverage
    d["feed_status"] = dict(S.FEED_STATUS)
    if S.ODDS_USAGE:
        d["meta"]["odds_api"] = dict(S.ODDS_USAGE, at=now_iso())
    if verbose:
        print(f"  logged {added} new quotes, closing price refreshed on {snapped} open bets")
    S.clear_nws_run()
    return added


def close_deadline(q):
    """The last moment `q`'s contest could be quoted — where its closing price belongs.

    The start, for contests. A yes/no market's "start" is its expiry, and each domain stops
    accepting quotes lead_h before it (a temperature market two hours from expiry has
    effectively happened), so its close is that cut-off: a price taken after it has the
    answer in it and would make every forecaster look like it beat the close."""
    try:
        start = datetime.fromisoformat(str(q["start"]))
    except (KeyError, TypeError, ValueError):
        return None
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    if q.get("venue") == "kalshi_binary":
        start -= timedelta(hours=(S.KALSHI_BINARY.get(q.get("sport")) or {}).get("lead_h", 0))
    return start


def close_lead_min(q):
    """Minutes between the closing snapshot and the deadline, or None."""
    if q.get("close_price") is None or not q.get("close_at"):
        return None
    dl = close_deadline(q)
    try:
        at = datetime.fromisoformat(str(q["close_at"]))
    except (TypeError, ValueError):
        return None
    return None if dl is None else (dl - at).total_seconds() / 60


def fresh_close(q):
    """Does this bet's closing price count toward CLV? See CLOSE_MAX_LEAD_MIN."""
    lead = close_lead_min(q)
    return lead is not None and 0 <= lead <= CLOSE_MAX_LEAD_MIN


def _read_closes(path):
    try:
        with open(path) as f:
            blob = json.load(f)
        blob.setdefault("closes", {})
        return blob
    except (OSError, ValueError):
        return {"closes": {}}


def load_closes(path=None, directory=None):
    """One writer's file when `path` is given; otherwise every writer's, merged — the latest
    snapshot per bet wins (apply_closes still refuses anything after the deadline)."""
    if path:
        return _read_closes(path)
    directory = directory or CLOSES_DIR
    files = [CLOSES] + ([os.path.join(directory, f) for f in sorted(os.listdir(directory))
                         if f.endswith(".json")] if os.path.isdir(directory) else [])
    merged = {}
    for fp in files:
        for qid, c in _read_closes(fp)["closes"].items():
            if qid not in merged or str(c.get("at")) > str(merged[qid].get("at")):
                merged[qid] = c
    return {"closes": merged}


def apply_closes(d, closes):
    """Merge the close job's snapshots into the ledger: the later snapshot before the
    deadline wins, whichever job took it. Returns the number of bets updated."""
    n = 0
    by_id = {q["id"]: q for q in d["quotes"]}
    for qid, c in (closes.get("closes") or {}).items():
        q = by_id.get(qid)
        if (not q or not q.get("bet") or c.get("price") is None or S.removed_row(q)
                or q.get("note") == KALSHI_UNPLACEABLE):
            continue
        if q.get("close_at") and str(q["close_at"]) >= str(c["at"]):
            continue
        dl = close_deadline(q)
        if dl is None or datetime.fromisoformat(str(c["at"])) > dl:
            continue
        q["close_price"], q["close_at"] = c["price"], c["at"]
        n += 1
    return n


def snap_closing(d, universe, now=None):
    """Record the venue's current price for the backed side of every open bet.

    Refreshed on every run until the contest starts, so the value left behind is the last
    snapshot before the start: the closing price. A bet bought below where the market closed
    (close_price > price) beat the close — the earliest sign of a real edge, readable long
    before enough results settle to judge ROI. Only the same venue's price counts, and only
    while that side's book is tradeable; a vanished or untraded row leaves the last good
    snapshot in place. Returns the number of bets updated.
    """
    now = now or datetime.now(timezone.utc)
    stamp = now.replace(microsecond=0).isoformat()
    rows = {r["market_id"]: r for rs in universe.values() for r in rs}
    n = 0
    for q in d["quotes"]:
        if S.removed_row(q) or q.get("note") == KALSHI_UNPLACEABLE:
            continue
        if q["status"] != "open" or not q.get("bet") or not q.get("pick"):
            continue
        r = rows.get(q["market_id"])
        dl = close_deadline(q)
        if (not r or r.get("untraded") or _started(r, now) or dl is None or dl <= now
                or r.get("venue", "polymarket") != q.get("venue", "polymarket")):
            continue
        pick = q["pick"]
        price = (r.get("price_draw") if pick == "draw"
                 else r["price_a"] if pick == "a" else r["price_b"])
        if price is None or not (r.get("tradeable") or {}).get(pick, True):
            continue
        q["close_price"], q["close_at"] = round(price, 4), stamp
        n += 1
    return n


# ---------------------------------------------------------------------------
# Grade
# ---------------------------------------------------------------------------

# A stored a/b/draw is a side. `void` is not one we will overwrite a side with:
# Polymarket uses it for "closed, but not a clean 1/0" (cancelled, or still
# disputed), and a None is "the venue did not answer". Neither may replace a
# win or a loss. A later decisive side may still replace a stored void.
DECISIVE_RESULTS = ("a", "b", "draw")
# Re-asking every settled market every run is a few thousand calls (about 7,000
# distinct markets in a week, mostly table tennis and Kalshi binaries). Bets
# settled inside this window are a couple of hundred reads, one per market, and
# that one read corrects every quote on the market — the bet's P&L and the
# venue self-quote whose Brier uses the same result. Anything older is re-asked
# only when the audit has put it on the watch list.
REGRADE_HOURS = 48
REGRADE_CAP = 150          # per venue, a spike must not turn the window into a full scan
# 'settled' is a price payout: finished, but not a win, a loss, or a void.
_SETTLED = ("won", "lost", "graded", "void", "settled")
_STORED_RESULTS = ("a", "b", "draw", "void", "price")


def load_settlement_watch(path=None):
    """Rows the audit is still holding open. A missing or unreadable file is an empty list."""
    path = path or MISMATCHES
    try:
        with open(path) as f:
            data = json.load(f)
    except (OSError, ValueError):
        return []
    rows, seen = [], set()
    for row in (data.get("markets") or []) if isinstance(data, dict) else []:
        if not isinstance(row, dict) or not row.get("market_id"):
            continue
        key = (row.get("venue"), row["market_id"])
        if key in seen:
            continue
        seen.add(key)
        rows.append({k: row.get(k) for k in _WATCH_FIELDS})
    return rows


def settlement_watch_keys(path=None):
    """(venue, market_id) pairs grade() re-resolves however long ago they settled."""
    return {(r.get("venue"), r["market_id"]) for r in load_settlement_watch(path)}


def save_settlement_watch(rows, path=None):
    """Rewrite the watch list. The audit is the only caller; grade() only reads it.

    The new list is written to a temp file in the same directory and then moved into
    place. A crash mid-write must not leave a truncated file: the next run would read
    that as an empty list and forget every mismatch it was supposed to keep failing on.
    """
    path = path or MISMATCHES
    seen, markets = set(), []
    for row in rows:
        mid = row.get("market_id")
        key = (row.get("venue"), mid)
        if not mid or key in seen:
            continue
        seen.add(key)
        markets.append({k: row[k] for k in _WATCH_FIELDS if row.get(k) is not None})
    markets.sort(key=lambda r: (str(r.get("venue") or ""), str(r["market_id"])))
    atomic_write_json(path, {"markets": markets}, prefix=".settlement-watch-")


def _resolve_market(q):
    """The venue's current answer for one quote: 'a'/'b'/'draw'/'void', or None."""
    venue, mid = q.get("venue"), q.get("market_id")
    if venue == "combo":
        return S.resolve_combo(q.get("legs") or [])
    if venue == "kalshi":
        return S.resolve_kalshi(mid)
    if venue == "kalshi_binary":
        return S.resolve_kalshi_market(mid)
    if venue == "polymarket_us":
        return S.resolve_polymarket_us(mid)
    if venue == "espn":
        return None
    return S.resolve_polymarket(mid)


def _apply_result(q, res, stamp):
    """Record one venue result: status, P/L, and the stamp.

    The same rules as a first grading. Brier is not stored on the quote — score()
    and prune() both read `result` — so rewriting it is what corrects the score.
    A no-bet quote is scored and never staked. A draw beats a side bet; it is
    not a refund. A ('price', settlement) answer pays the side's fair price:
    result 'price', status 'settled', settle_px the amount that side was paid.
    That is a payout, counted in P/L, and it is not a win, a loss, or a void.
    A row that already has a settled time keeps it. Only a first settlement,
    a row that never had one, is stamped now. Rewriting the time would move
    the bet onto today's page and restart its retention clock.
    """
    settlement = S._price_result(res)
    if settlement is not None:
        paid = round(S.price_paid(q.get("pick"), res), 6)
        q["result"] = "price"
        q["settle_px"] = paid
        if not q.get("settled"):
            q["settled"] = stamp
        q["status"] = "settled"
        if q.get("bet") and q.get("price"):
            q["pnl"] = round(float(q["stake"]) * (paid / float(q["price"]) - 1.0), 2)
        else:
            q["pnl"] = 0.0
        return
    q.pop("settle_px", None)
    q["result"] = res
    if not q.get("settled"):
        q["settled"] = stamp
    if res == "void":
        q["status"] = "void"
        q["pnl"] = 0.0
    elif not q["bet"]:
        # Scored for accuracy, never staked. Kept as a distinct status so a
        # no-bet quote can never be mistaken for a losing one.
        q["status"] = "graded"
        q["pnl"] = 0.0
    elif q["pick"] == res:
        # Compared BEFORE any draw handling. The previous version asked "was it a
        # draw?" first and marked every bet on a drawn match lost — which would
        # have scored a correct Draw tip as a loss.
        q["status"] = "won"
        q["pnl"] = round(q["stake"] * (1.0 / q["price"] - 1.0), 2)
    else:
        # Includes a side backed in a match that was drawn: in a three-way market
        # the draw beats it as surely as defeat does, and it is never refunded.
        q["status"] = "lost"
        q["pnl"] = -q["stake"]


def _regrade_markets(quotes, now, watched, skip_ids):
    """One quote per market worth asking the venue about again.

    A market qualifies when a bet on it settled inside REGRADE_HOURS, or when
    the audit is watching it. Quotes grade() just settled in this same call are
    skipped: their answer is already this run's. The cap keeps a volume spike
    from turning the window into a scan of every settled row; watched markets
    are never dropped to make room.
    """
    cutoff = (now - timedelta(hours=REGRADE_HOURS)).replace(microsecond=0).isoformat()
    chosen = {}
    for q in quotes:
        if id(q) in skip_ids or q.get("status") not in _SETTLED:
            continue
        if q.get("note") == KALSHI_UNPLACEABLE:
            continue
        if q.get("venue") == "espn" or not q.get("market_id"):
            continue
        if q.get("result") not in _STORED_RESULTS:
            continue
        key = (q.get("venue"), q.get("market_id"))
        flagged = key in watched
        recent = bool(q.get("bet") and q.get("status") in ("won", "lost", "void", "settled")
                      and (q.get("settled") or "") >= cutoff)
        if not flagged and not recent:
            continue
        prev = chosen.get(key)
        # A basket settles from the legs on the quote. Keep a copy that has them.
        if prev is None or (q.get("legs") and not prev[0].get("legs")):
            chosen[key] = (q, flagged, q.get("settled") or "")
    out = []
    by_venue = {}
    for key, item in chosen.items():
        by_venue.setdefault(key[0], []).append(item)
    for rows in by_venue.values():
        out.extend(q for q, flagged, _s in rows if flagged)
        recent = sorted(((q, s) for q, flagged, s in rows if not flagged), key=lambda qs: qs[1])
        out.extend(q for q, _s in recent[:REGRADE_CAP])
    return out


def _kalshi_price_regrade(q):
    """True when a price re-grade is a Kalshi settlement.

    A kalshi or kalshi_binary quote qualifies. A basket qualifies only when at
    least one leg is one of those venues. A basket whose legs are all
    Polymarket US does not: a later pass leaves its settle_px alone and does
    not turn a note-free void into a price, which is how grade() treated it
    before this branch. An open Polymarket US quote still settles at the price
    on the first pass.
    """
    venue = q.get("venue")
    if venue in ("kalshi", "kalshi_binary"):
        return True
    if venue != "combo":
        return False
    return any(leg.get("venue") in ("kalshi", "kalshi_binary")
               for leg in (q.get("legs") or []))


def grade(d, verbose=True, now=None, mismatches=None):
    """Settle every open quote, then correct a settled one whose venue has revised.

    `mismatches` overrides the watch file (tests pass a set). None reads it.
    A market is re-read when a bet on it settled inside REGRADE_HOURS, or when
    its (venue, market_id) is in that set. Anything older, and not listed, is
    left as stored. A re-resolved None or void never replaces a stored side.
    A Kalshi price, or a basket with a Kalshi leg, may replace a void that has
    no note and no city-day flag. It does not replace a win or a loss. A
    Polymarket US quote, and a basket whose legs are all Polymarket US, are
    not re-priced. Returns how many open quotes settled this call; corrections
    are counted separately in the log.
    """
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    watched = settlement_watch_keys() if mismatches is None else set(mismatches)
    resolved, settled = {}, 0
    # Settled at the top of this call, from the venue, moments ago. Re-asking
    # them would double every settlement read the run already made.
    just_settled = {id(q) for q in d["quotes"] if q.get("status") == "open"}

    for q in d["quotes"]:
        if q["status"] != "open":
            continue
        # Weather stays as stored: no settlement read, no status or price change.
        # A Kalshi MMA bet retired as unplaceable is not graded, even if a later
        # edit put it back to open.
        if S.removed_row(q) or q.get("note") == KALSHI_UNPLACEABLE:
            continue
        if q.get("venue") == "espn":
            # Soccer was priced on ESPN + DraftKings until that venue was retired for
            # Kalshi. Nothing can settle a quote on it any more, and the one bet it left
            # behind was also re-logged on Kalshi — kept open it would sit unsettled for
            # ever AND count that tip twice. Refunded, never guessed.
            q["status"], q["result"], q["pnl"] = "void", "void", 0.0
            q["settled"] = now_iso()
            settled += 1
            continue
        # Don't ask about a market that cannot possibly have finished yet.
        try:
            start = datetime.fromisoformat(q["start"])
            if start.tzinfo is None:
                start = start.replace(tzinfo=timezone.utc)
            if now < start + timedelta(hours=2):
                continue
        except (ValueError, TypeError, KeyError):
            pass

        mid = q["market_id"]
        if mid not in resolved:
            # A basket has no market of its own to ask: it is settled by its legs, and only
            # once every one of them has. Cached per basket like any other market, so the
            # two- and three-leg sources never re-resolve the same legs.
            resolved[mid] = _resolve_market(q)
        res = resolved[mid]
        if res is None:
            continue
        _apply_result(q, res, now_iso())
        settled += 1

    regraded = 0
    results = {}
    for q in _regrade_markets([q for q in d["quotes"] if not S.removed_row(q)],
                              now, watched, just_settled):
        key = (q.get("venue"), q.get("market_id"))
        if key not in results:
            results[key] = _resolve_market(q)
    for q in d["quotes"]:
        if (S.removed_row(q) or q.get("note") == KALSHI_UNPLACEABLE
                or id(q) in just_settled or q.get("status") not in _SETTLED):
            continue
        res = results.get((q.get("venue"), q.get("market_id")))
        # A Kalshi scalar, or a basket with a Kalshi leg, may replace a void or
        # correct a stored price. A Polymarket US quote, and a basket whose
        # legs are all Polymarket US, fall through and are not re-priced. A
        # duplicate, a late log, a pre-gate void, or a city-day flag carries a
        # note or a mark and stays as it is. A win or a loss is not replaced.
        if S._price_result(res) is not None and _kalshi_price_regrade(q):
            if q.get("note") or climate_excluded(q):
                continue
            if q.get("result") not in ("void", "price"):
                continue
            new_paid = round(S.price_paid(q.get("pick"), res), 6)
            if (q.get("result") == "price" and q.get("settle_px") is not None
                    and abs(float(q["settle_px"]) - new_paid) <= 1e-9):
                continue
            _apply_result(q, res, now_iso())
            regraded += 1
            continue
        # None, void, or any other non-side must not overwrite a stored win/loss.
        # A decisive side that merely repeats the stored result is not a correction.
        if res not in DECISIVE_RESULTS or res == q.get("result"):
            continue
        _apply_result(q, res, now_iso())
        regraded += 1

    if verbose:
        print(f"  settled {settled} quotes" + (f", regraded {regraded}" if regraded else ""))
    return settled


# ---------------------------------------------------------------------------
# Score
# ---------------------------------------------------------------------------

def _folded_totals(q):
    """The retired totals prune() adds when it folds this one row."""
    quotes, bets, settled, won = 1, 0, 0, 0
    staked = pnl = brier_sum = 0.0
    brier_n = 0
    if q.get("bet"):
        bets = 1
    if q.get("status") in ("won", "lost") and not climate_excluded(q):
        settled = 1
        won = 1 if q.get("status") == "won" else 0
        staked = q.get("stake") or 0.0
        pnl = q.get("pnl") or 0.0
    elif (q.get("bet") and q.get("result") == "price" and q.get("status") == "settled"
          and not climate_excluded(q)):
        staked = q.get("stake") or 0.0
        pnl = q.get("pnl") or 0.0
    if (q.get("result") in ("a", "b") and not q.get("untraded")
            and q.get("prob_a") is not None and not climate_excluded(q)):
        brier_sum = (q["prob_a"] - (1.0 if q["result"] == "a" else 0.0)) ** 2
        brier_n = 1
    return dict(quotes=quotes, bets=bets, settled=settled, won=won,
                staked=staked, pnl=pnl, brier_sum=brier_sum, brier_n=brier_n)


def _still_live_folded(d):
    """Per source, what retired already counted for an id that is still live.

    The archive copy is the row prune() folded. The live quote wins, so those
    totals are taken back out and the quote is counted on its own. save()
    writes the ledger before the archive, so a crash between those writes
    leaves the row in retired and not in the archive file. That archive
    copy is lost: the next prune() cannot re-archive a row that has left
    the ledger.
    """
    live = {q.get("id") for q in d["quotes"] if q.get("id") is not None}
    seen = set()
    acc = {}
    for q in d.get("_archive") or []:
        i = q.get("id")
        if i is None or i not in live or i in seen:
            continue
        seen.add(i)
        piece = _folded_totals(q)
        bucket = acc.setdefault(q.get("source"), dict(
            quotes=0, bets=0, settled=0, won=0, staked=0.0, pnl=0.0,
            brier_sum=0.0, brier_n=0))
        for k in bucket:
            bucket[k] += piece[k]
    return acc


def score(d, sport=None):
    """Per-source table over the ledger. ROI from bets, Brier from every graded quote.

    A single-sport view adds archived bets the ledger no longer holds. The
    roll-up total is not kept per sport, so those bets would otherwise vanish
    from this view. The all-sport view does not add them: `retired` already
    holds the lifetime totals, and adding the archive on top would count the
    same bets twice. An id that is still in the ledger is not counted again
    through `retired`: the live row wins. save() writes the ledger before
    the archive, so a crash between those writes does not leave the id in
    both lists.
    """
    still_live = _still_live_folded(d) if sport is None else {}
    # Edges are not stored on retired. The archive row still has one, so the
    # all-sport average does not move when a bet rolls up.
    archived_for_edge = {}
    if sport is None:
        seen_edge = {q.get("id") for q in d["quotes"] if q.get("id") is not None}
        for q in d.get("_archive") or []:
            if not q.get("bet"):
                continue
            i = q.get("id")
            if i is not None and i in seen_edge:
                continue
            if i is not None:
                seen_edge.add(i)
            archived_for_edge.setdefault(q.get("source"), []).append(q)
    extra = []
    if sport is not None:
        seen = {q.get("id") for q in d["quotes"] if q.get("id") is not None}
        for q in d.get("_archive") or []:
            if not q.get("bet") or q.get("sport") != sport:
                continue
            i = q.get("id")
            # The same id can sit in the archive twice. The first copy wins,
            # which is the rule bet_rows uses. The live quote already won above.
            if i is not None and i in seen:
                continue
            if i is not None:
                seen.add(i)
            extra.append(q)
    out = {}
    for name, meta in S.SOURCES.items():
        rows = [q for q in d["quotes"] if q["source"] == name
                and (sport is None or q["sport"] == sport)]
        if extra:
            rows.extend(q for q in extra if q["source"] == name)
        bets = [q for q in rows if q["bet"]]
        done = [q for q in bets if q["status"] in ("won", "lost") and not climate_excluded(q)]
        # A price payout is money. It is not a win or a loss, so it stays out of
        # the hit rate, and out of Brier below (that filter wants a side).
        # A repeat city-day mark is out of both, the way a void is: the row stays,
        # its P/L does not.
        priced = [q for q in bets if q.get("status") == "settled" and q.get("result") == "price"
                  and not climate_excluded(q)]
        won = [q for q in done if q["status"] == "won"]
        staked = sum(q["stake"] for q in done) + sum(q["stake"] for q in priced)
        pnl = sum(q["pnl"] for q in done) + sum(q["pnl"] for q in priced)

        # An untraded 0.50/0.50 book is excluded from Brier as well as from betting.
        # Table tennis is overwhelmingly made of these, and scoring a flat 0.5 against a
        # coin flip would bury every real forecast under 0.25s that mean nothing.
        # Brier needs a probability. A tipster that only names a side has nothing to
        # calibrate, so it gets no Brier column rather than a fabricated 0/1 stand-in.
        briered = [q for q in rows if q["status"] in ("won", "lost", "graded")
                   and q.get("result") in ("a", "b") and not q.get("untraded")
                   and q.get("prob_a") is not None and not climate_excluded(q)]
        n_quotes, n_bets, n_done, n_won = len(rows), len(bets), len(done), len(won)
        brier_sum = sum((q["prob_a"] - (1.0 if q["result"] == "a" else 0.0)) ** 2
                        for q in briered)
        brier_n = len(briered)

        # Lifetime totals include quotes already rolled up and dropped. Without this the
        # board would silently RESET every source's record at the retention horizon.
        # Skipped for a single-sport view, since the rollup is not kept per sport.
        if sport is None:
            r = (d.get("retired") or {}).get(name)
            if r:
                piece = still_live.get(name) or {}
                # Take the overlap back out only when retired is large enough
                # to hold it. An archive row that was never folded is not in
                # these totals, and pulling it out would shrink a different bet.
                holds = (not piece or (
                    r["quotes"] >= piece["quotes"] and r["bets"] >= piece["bets"]
                    and r["settled"] >= piece["settled"] and r["won"] >= piece["won"]
                    and r["staked"] + 1e-6 >= piece["staked"]
                    and r["brier_n"] >= piece["brier_n"]))
                if not holds:
                    piece = {}
                n_quotes += r["quotes"] - piece.get("quotes", 0)
                n_bets += r["bets"] - piece.get("bets", 0)
                n_done += r["settled"] - piece.get("settled", 0)
                n_won += r["won"] - piece.get("won", 0)
                staked += r["staked"] - piece.get("staked", 0.0)
                pnl += r["pnl"] - piece.get("pnl", 0.0)
                brier_sum += r["brier_sum"] - piece.get("brier_sum", 0.0)
                brier_n += r["brier_n"] - piece.get("brier_n", 0)

        edge_rows = bets + archived_for_edge.get(name, [])
        edges = [q["edge"] for q in edge_rows if q.get("edge") is not None]
        out[name] = dict(
            label=meta["label"], kind=meta["kind"], connected=meta["connected"],
            site=meta["site"], note=meta["note"],
            quotes=n_quotes, open=len([q for q in rows if q["status"] == "open"
                                        and not climate_excluded(q)]),
            bets=n_bets, settled=n_done, won=n_won,
            hit=(n_won / n_done) if n_done else None,
            staked=staked, pnl=pnl,
            roi=(pnl / staked) if staked else None,
            brier=(brier_sum / brier_n) if brier_n else None, brier_n=brier_n,
            avg_edge=(sum(edges) / len(edges)) if edges else None,
        )
    return out


# ---------------------------------------------------------------------------
# Baselines and the stamp of approval
# ---------------------------------------------------------------------------

BLIND_KINDS = ("favourite", "underdog", "draw")


def blind_pnl(q, kind):
    """P/L of a blind strategy on the contest behind quote `q`, at q's own prices.

    kind = "draw" backs the draw (three-way only); "favourite" backs whichever side the
    venue priced higher; "underdog" the side it priced lower. Same contest, same moment, same prices and the same price band
    as the source it is compared with — so the only thing that differs is the choice.
    None when the strategy has no bet there or the contest has no clean result.
    """
    if q.get("result") not in ("a", "b", "draw"):
        return None
    if kind == "draw":
        side, price = "draw", q.get("price_draw")
    else:
        pa, pb = q.get("price_a"), q.get("price_b")
        if pa is None or pb is None:
            return None
        fav = ("a", pa) if pa >= pb else ("b", pb)
        dog = ("b", pb) if pa >= pb else ("a", pa)
        side, price = fav if kind == "favourite" else dog
    lo, hi = price_band(q.get("sport"))
    if price is None or not (lo <= price <= hi):
        return None
    return round(STAKE * (1.0 / price - 1.0), 2) if q["result"] == side else -STAKE


def baselines(d, sport=None):
    """The two blind strategies across every contest the ledger holds a result for.

    Each contest counted ONCE, priced at its earliest quote — the first moment any source
    looked at it, before the start. Void and late quotes are ignored.
    Returns {kind: dict(n, won, pnl, roi, expected)}.

    Archived bets are scanned after the live quotes, and only when that id is
    not already in the ledger. Compact price rows are not bets, so they stay
    out: the table on current data is the live quotes alone. A logged-time tie
    keeps the live quote.
    """
    seen = {q.get("id") for q in d["quotes"] if q.get("id") is not None}
    scan = list(d["quotes"])
    for q in d.get("_archive") or []:
        if not q.get("bet"):
            continue
        i = q.get("id")
        if i is not None and i in seen:
            continue
        scan.append(q)
    first = {}
    for q in scan:
        if q.get("status") == "void" or climate_excluded(q) or (sport and q["sport"] != sport):
            continue
        if q.get("venue") == "kalshi_binary" or q.get("result") not in ("a", "b", "draw"):
            continue
        cur = first.get(q["market_id"])
        if cur is None or q["logged"] < cur["logged"]:
            first[q["market_id"]] = q
    out = {}
    for kind in BLIND_KINDS:
        rows = [(q, blind_pnl(q, kind)) for q in first.values()]
        rows = [(q, p) for q, p in rows if p is not None]
        n = len(rows)
        pnl = sum(p for _q, p in rows)
        exp = 0.0
        for q, _p in rows:
            exp += (q["price_draw"] if kind == "draw" else
                    max(q["price_a"], q["price_b"]) if kind == "favourite" else
                    min(q["price_a"], q["price_b"]))
        out[kind] = dict(n=n, won=sum(1 for _q, p in rows if p > 0), pnl=pnl,
                         roi=(pnl / (n * STAKE)) if n else None, expected=exp)
    return out


def pnl_after_fee(q):
    """A settled bet's P/L if the taker fee had been paid on top of the price.

    A win pays 1. A price payout pays settle_px, and the fee comes off the same
    way: the stake buys `paid` at `price + fee` instead of at `price`.
    """
    p = q["price"]
    fee = FEE_RATE.get(q.get("venue") or "polymarket", 0.07) * p * (1 - p)
    if q["status"] == "won":
        return round(STAKE * (1.0 / (p + fee) - 1.0), 2)
    if q.get("result") == "price" and q.get("settle_px") is not None:
        return round(STAKE * (float(q["settle_px"]) / (p + fee) - 1.0), 2)
    return -STAKE


# A cluster whose logged prices sum to 1 or more is left with no variance by P(1-P), and
# there are two very different reasons that happens. Below this share of a record it is read
# as incoherent data and those clusters are dropped from the z; above it, the grouping itself
# is wrong and no z is produced at all. `spot` before crypto joined S.DAY_CLUSTERED sat at
# 15/17 = 88%; `nws`, whose weather buckets really are exclusive and whose sums pass 1 only
# because two quotes on one city-day were logged hours apart, sits at 5/77 = 6%.
MAX_DEGENERATE = 0.20


class DegenerateCluster(Exception):
    """Too much of a record is clusters that P(1-P) leaves with no variance.

    Raised rather than worked around, because it means the outcomes were grouped wrongly and
    every z over that grouping is inflated. See cluster_stats.
    """


def cluster_stats(clusters):
    """Wins, expectation and variance over mutually exclusive outcome clusters.

    `clusters`: {key: [(p_draw, price, won), ...]} keyed by S.outcome_cluster. At most one
    bet in a cluster can land, so its wins are ONE 0/1 draw with probability P = the sum of
    its `p_draw` and variance P(1-P) — not the sum of p(1-p), which would treat one day's
    weather as two coin flips. A singleton is p(1-p) exactly.

    `p_draw` and `price` are the same number for a pair's own record, and DIFFER for its
    fade. Fading two exclusive buckets priced 0.30 means paying 0.72 twice, and the fade
    wins 2 of them when neither bucket lands and 1 when one does: a win count of
    2 - Bernoulli(0.60), whose variance is the RULE's 0.60 x 0.40, not the fade's
    1.44. So the fade passes the rule's prices as `p_draw` and its own as `price`. Reading
    P off the fade's prices would also make every such cluster look degenerate below.

    A cluster holding more than one bet whose prices sum to 1 or more is left with zero
    variance, and the old code summed that straight into the total. It is not a
    near-certainty to wave through, it is a contradiction, and waving it through is what
    inflated `spot` to z +10.40: the cluster's excess wins went into the NUMERATOR while it
    contributed NOTHING to the denominator. Such clusters are dropped from all three figures
    here — numerator included, which is the part that matters — and returned in `dropped`.

    Two distinct things produce them, and only the share tells them apart:

      * NESTED rungs, wrongly grouped as exclusive. A coin or commodity ladder, where
        "$100 or above" and "$112 or above" both land on one move: `spot` had eight rungs of
        one SOL day summing to 4.68, and 15 of its 17 clusters were degenerate. The premise
        of the cluster is simply false, dropping would discard the record, and the remedy is
        to name that sport in S.DAY_CLUSTERED so it is judged per market-day instead.
      * INCOHERENT prices on genuinely exclusive rungs. `nws` backed 103°-104° at 0.70 and
        101°-102° at 0.87 on one Austin day: no simultaneous book prices two exclusive
        buckets at 1.57, and the sum only passes 1 because the two quotes were logged hours
        apart as the forecast moved. Exactly one of them could land and exactly one did. The
        cluster carries no usable expectation, but the other 72 do.

    So: above MAX_DEGENERATE of the clusters, raise DegenerateCluster — the grouping is
    wrong and no z is honest. At or below it, drop them and say how many.

    Returns dict(won, expected, var, outcomes, dropped, n) over the clusters KEPT.
    """
    keep, dropped = {}, []
    for key, rows in clusters.items():
        P = min(1.0, sum(float(d) for d, _p, _w in rows))
        if P * (1.0 - P) <= 0.0 and len(rows) > 1:
            dropped.append(key)
        else:
            keep[key] = (rows, P)
    if clusters and len(dropped) > MAX_DEGENERATE * len(clusters):
        raise DegenerateCluster(
            f"{len(dropped)} of {len(clusters)} outcome clusters hold several bets whose "
            f"prices sum to 1 or more, leaving them no variance — past "
            f"{MAX_DEGENERATE:.0%}, so these outcomes are grouped wrongly and no z over "
            f"them is honest. If the rungs can all land together, as a coin or commodity "
            f"ladder's can, name the sport in S.DAY_CLUSTERED. First: {dropped[0]!r}.")
    return dict(
        won=sum(1 for rows, _P in keep.values() for _d, _p, w in rows if w),
        expected=sum(float(p) for rows, _P in keep.values() for _d, p, _w in rows),
        var=sum(P * (1.0 - P) for _rows, P in keep.values()),
        outcomes=len(keep), dropped=len(dropped), n=sum(len(r) for r, _P in keep.values()))


# Provisional, until the owner picks. One named switch for the whole scorer.
#   first — earliest logged quote. Ties: lesser market_id, then lesser id.
#   last  — latest quote logged strictly before that quote's start. Ties:
#           lesser market_id, then lesser id. A quote logged at or after start
#           is not a reading. If every quote on the city-day is past start,
#           the city-day is not scored. start is the market start, not close_at.
#   best  — lowest price paid for the side that was bet. Ties: earliest logged,
#           then lesser market_id, then lesser id.
# Collapse is per lane: nws and nws_fade are separate, one quote per city-day
# event (outcome_cluster, for example KXHIGHCHI-26SEP26). The quote that is
# not kept is marked excluded="nws_cityday", with a note naming the kept id
# and this rule. The row stays. Its result, prices and P/L stay, so a later
# rule is a re-run of mark_climate_citydays: old marks clear, new ones land.
# Totals skip the mark the way they skip a void.
# Set to "last" on 2026-10-01, no longer provisional. A city-day's repeat quotes are not one
# bet re-priced: all 29 of them are DIFFERENT buckets, because the forecast moved (Austin
# 2026-09-12 read 103-104 in the morning and 101-102 that evening). So the rule chooses which
# FORECAST to score, not which price, and only one bucket can land. "first" scores the reading
# the forecaster had already revised away, which measures staleness; "last" scores the one it
# stood behind at the event, which is how a forecaster is normally judged. It moves nws from
# -27.8% to -1.5% and the verdict does not change under any of the three — it is behind the
# price in all of them. NOTE the lanes each pick their kept quote independently, so nws and
# nws_fade can land on different buckets of one city-day (2 of their 8 shared days). That is
# correct per lane — each is scored on what it actually bet — but it means a lane-v-lane
# comparison on a single city-day is not always like for like.
CLIMATE_KEEP_RULE = "last"
CLIMATE_KEEP_RULES = ("first", "last", "best")
_CLIMATE_LANES = ("nws", "nws_fade")


def _climate_lane(q):
    return q.get("source") in _CLIMATE_LANES and q.get("sport") == "climate"


def _climate_pick(qs, rule):
    """The one non-void quote this city-day keeps under `rule`, or None.

    A void is never the kept bet. It is already off the record, and choosing
    it would mark the real quotes as the repeats.
    """
    if rule not in CLIMATE_KEEP_RULES:
        raise ValueError(f"CLIMATE_KEEP_RULE must be one of {CLIMATE_KEEP_RULES}, not {rule!r}")
    qs = [q for q in qs if q.get("status") != "void"]
    if not qs:
        return None
    ident = lambda q: (str(q.get("market_id") or ""), str(q.get("id") or ""))
    logged = lambda q: str(q.get("logged") or "")
    if rule == "first":
        return min(qs, key=lambda q: (logged(q),) + ident(q))
    if rule == "last":
        elig = [q for q in qs if not q.get("start") or logged(q) < str(q["start"])]
        if not elig:
            return None
        latest = max(logged(q) for q in elig)
        tied = [q for q in elig if logged(q) == latest]
        return min(tied, key=ident)
    # best: cheapest price on the side that was bet.
    return min(qs, key=lambda q: (float(q["price"]) if q.get("price") is not None else 1.0,
                                  logged(q)) + ident(q))


def one_climate_reading(bets, rule=None):
    """One temperature reading per city-day per lane (nws, nws_fade).

    `rule` defaults to CLIMATE_KEEP_RULE. See that constant for first / last /
    best. Any other source is left untouched, so a nested ladder and YES bets
    on one city-day whose prices sum past 1 still raise DegenerateCluster.
    """
    rule = CLIMATE_KEEP_RULE if rule is None else rule
    if not any(_climate_lane(q) for q in bets):
        return list(bets)
    groups = {}
    for q in bets:
        if _climate_lane(q):
            groups.setdefault((q.get("source"), S.outcome_cluster(q)), []).append(q)
    keep = set()
    for qs in groups.values():
        chosen = _climate_pick(qs, rule)
        if chosen is not None:
            keep.add(id(chosen))
    return [q for q in bets if not _climate_lane(q) or id(q) in keep]


CLIMATE_EXCLUDED = "nws_cityday"
_CLIMATE_NOTE_PREFIX = "nws city-day: kept "


def climate_excluded(q):
    """True when this row is a repeat city-day quote left out of every total."""
    return q.get("excluded") == CLIMATE_EXCLUDED


def _climate_note(kept_id, rule):
    return f"{_CLIMATE_NOTE_PREFIX}{kept_id} under {rule}"


def _our_climate_note(note):
    return isinstance(note, str) and note.startswith(_CLIMATE_NOTE_PREFIX)


def _clear_climate_mark(q):
    """Drop a mark this rule wrote. A note from anywhere else stays."""
    changed = False
    if q.get("excluded") == CLIMATE_EXCLUDED:
        q.pop("excluded", None)
        changed = True
    if _our_climate_note(q.get("note")):
        q.pop("note", None)
        changed = True
    return changed


def _set_climate_mark(q, kept_id, rule):
    """Mark one dropped row. Result, prices, status and P/L are not written."""
    note = _climate_note(kept_id, rule)
    changed = False
    if q.get("excluded") != CLIMATE_EXCLUDED:
        q["excluded"] = CLIMATE_EXCLUDED
        changed = True
    # A note this marker did not write is quote data. Leave it.
    if q.get("note") and not _our_climate_note(q.get("note")):
        return changed
    if q.get("note") != note:
        q["note"] = note
        changed = True
    return changed


def mark_climate_citydays(d, rule=None):
    """Mark repeat nws / nws_fade quotes on one city-day. Idempotent.

    One bet per lane per event stays unmarked. The others get
    excluded='nws_cityday' and a note naming the kept id and the rule.
    Running again under the same rule changes nothing. Running under a
    different rule clears the old marks and writes the new ones. A row that
    is no longer a repeat loses the mark. Returns how many rows changed.
    """
    rule = CLIMATE_KEEP_RULE if rule is None else rule
    if rule not in CLIMATE_KEEP_RULES:
        raise ValueError(f"CLIMATE_KEEP_RULE must be one of {CLIMATE_KEEP_RULES}, not {rule!r}")
    live = {id(q) for q in d.get("quotes") or []}
    rows = [q for q in all_bets(d) if q.get("bet") and _climate_lane(q)]
    grouped = {}
    for q in rows:
        grouped.setdefault((q.get("source"), S.outcome_cluster(q)), []).append(q)
    seen, changed = set(), 0
    for qs in grouped.values():
        chosen = _climate_pick(qs, rule)
        kept_id = chosen.get("id") if chosen is not None else "none"
        for q in qs:
            seen.add(id(q))
            # A void is never the kept bet and never a marked repeat.
            if q.get("status") == "void" or (chosen is not None and q is chosen):
                moved = _clear_climate_mark(q)
            else:
                moved = _set_climate_mark(q, kept_id, rule)
            if not moved:
                continue
            changed += 1
            if id(q) not in live:
                month = str(q.get("settled") or "")[:7]
                if month:
                    d.setdefault("_archive_dirty", set()).add(month)
    for q in all_bets(d):
        if id(q) in seen or not (climate_excluded(q) or _our_climate_note(q.get("note"))):
            continue
        if _clear_climate_mark(q):
            changed += 1
            if id(q) not in live:
                month = str(q.get("settled") or "")[:7]
                if month:
                    d.setdefault("_archive_dirty", set()).add(month)
    return changed


def faded(d, name, sport=None, venues=None):
    """What the OTHER side of this pair's bets would have done — dict(n, won, expected, roi, z).

    Not a strategy, a diagnostic. A rule whose fade is strongly positive is not merely
    failing to find an edge, it is pointing at the wrong side, which is a different and
    much more useful complaint: the selection works and the direction is inverted.

    It is NOT the rule's own return with the sign flipped. Both sides of a book are sold
    above fair, so the two asks sum to more than 1 and a fade of a merely average rule
    loses that overround plus its own fee. A fade only shows a profit where the rule is
    wrong by more than the cost of being on either side.

    Three-way contests are skipped (n=0): the opposite of "back the home side" is the away
    side AND the draw, so there is no single other side to price.

    Judged in the same units assess() uses, because the z is only honest if the outcomes
    are counted the way they actually fall:
      * a domain judged per market-day (S.DAY_CLUSTERED) collapses to one unit a day. Its
        rungs are nested ("above $2.89" and "above $2.95" come in together), so summing
        them as one draw is as wrong as counting them as independent ones.
      * elsewhere, variance is taken per outcome cluster. A temperature ladder's buckets
        cannot both come in, so the rule hits at most one of the k it backed and the fade
        wins k or k-1: one 0/1 draw of variance P(1-P), P the rule's summed prices. That
        covariance is NEGATIVE, so counting the buckets as independent overstated the
        variance and understated the z — NWS reads +1.23 correctly counted, not +0.92.
    """
    bets = [q for q in bet_rows(d) if q["source"] == name
            and q["status"] in ("won", "lost") and not climate_excluded(q)
            and (sport is None or q["sport"] == sport)
            and q.get("price_draw") is None and q.get("pick") in ("a", "b")
            and (venues is None or (q.get("venue") or "polymarket") in venues)]
    rows = []
    for q in bets:
        other = "b" if q["pick"] == "a" else "a"
        price = q.get(f"price_{other}")
        if price:
            p = float(price)
            f = FEE_RATE.get(q.get("venue") or "polymarket", 0.07)
            w = q.get("result") == other
            rows.append(dict(q=q, p=p, fee=f, won=w,
                             pnl=(STAKE * (1.0 / (p + f * p * (1 - p)) - 1.0)) if w else -STAKE))
    if not rows:
        return dict(n=0, won=0, expected=0.0, roi=None, z=0.0, outcomes=0)
    cost = sum(r["p"] + r["fee"] * r["p"] * (1 - r["p"]) for r in rows)
    roi = (sum(1 for r in rows if r["won"]) - cost) / cost

    # As in assess: follow each bet's own sport, so sport=None is not a way around this.
    if sport in S.DAY_CLUSTERED or any(r["q"]["sport"] in S.DAY_CLUSTERED for r in rows):
        days = {}
        for r in rows:
            key = (S.market_day(r["q"]) if r["q"]["sport"] in S.DAY_CLUSTERED
                   else S.outcome_cluster(r["q"]))
            days.setdefault(key, []).append(r)
        units = [(sum(r["p"] for r in rs) / len(rs), sum(r["pnl"] for r in rs) / len(rs) > 0)
                 for rs in days.values()]
        won = sum(1 for _p, w in units if w)
        exp = sum(p for p, _w in units)
        var = sum(p * (1 - p) for p, _w in units)
        return dict(n=len(units), won=won, expected=exp, roi=roi, outcomes=len(units),
                    unit="market-day", n_bets=len(rows),
                    z=(won - exp) / var ** 0.5 if var > 0 else 0.0)

    clusters = {}
    for r in rows:
        clusters.setdefault(S.outcome_cluster(r["q"]), []).append(
            (r["q"]["price"], r["p"], r["won"]))
    c = cluster_stats(clusters)
    # n and roi stay over every bet: the money is the money. Only the z is taken over the
    # clusters that survived, and `dropped` says how many did not.
    return dict(n=len(rows), won=sum(1 for r in rows if r["won"]),
                expected=sum(r["p"] for r in rows), roi=roi, outcomes=c["outcomes"],
                z_dropped=c["dropped"],
                z=(c["won"] - c["expected"]) / c["var"] ** 0.5 if c["var"] > 0 else 0.0)


# ---- Per-competition records (2026-09-22) ---------------------------------------------------
# A soccer rule does not meet one market; it meets a different one in every competition. Across
# the two years of ESPN results the Sandbox keeps, the Bundesliga scored 3.49 goals a game and
# Serie A 2.38, and on the Sandbox's own quotes both sides of a cup market cost about 6.6%
# against 1.5% on a league match winner. Pooling that into a single row can bury a rule that
# works in one league inside an average saying it does not, and can hide a rule that is only
# ever paying a toll. So a pair is split by the competition its bets were actually struck in.
#
# The split is DESCRIPTIVE and never a verdict. Cutting a record eleven ways multiplies the
# looks, and the best slice always looks good: across 47 league-by-market cells of the market's
# own prices, five beat |z| 1.5 where chance alone produces six, and none reached |z| 2 where
# chance produces two. Nothing here promotes, demotes or retires a pair — the verdict column
# goes on reading the whole record.

def league_split(d, name, sport=None, venues=None, since=None):
    """A pair's record per competition, best first: [dict(league, n, won, expected, ...)].

    Each entry carries the same figures the sport tables use — wins against what the prices
    implied, return after fees, and what backing the other side of those same bets would have
    returned — so a league row reads exactly like a pair row, only thinner.

    The settled list is the one assess() counts. `since` is the pair's stage clock: a bet
    logged earlier is not in the card's n, so it is not in this split either. A refused
    tennis tour is left out the same way, including a price payout. A sport in
    S.DAY_CLUSTERED is counted with day_units, the same collapse assess() uses, so a
    corners league's n is matches and n_bets is the rungs. The other side stays priced
    per bet, because each rung has its own ask.
    """
    bets = [q for q in bet_rows(d) if q["source"] == name
            and q["status"] in ("won", "lost") and not climate_excluded(q)
            and not S.tennis_refused_row(q)
            and (sport is None or q["sport"] == sport)
            and (since is None or q["logged"] >= since)
            and (venues is None or (q.get("venue") or "polymarket") in venues)]
    priced = [q for q in bet_rows(d) if q["source"] == name
              and q.get("status") == "settled" and q.get("result") == "price"
              and not climate_excluded(q)
              and not S.tennis_refused_row(q)
              and (sport is None or q["sport"] == sport)
              and (since is None or q["logged"] >= since)
              and (venues is None or (q.get("venue") or "polymarket") in venues)]
    by = {}
    for q in bets:
        by.setdefault(S.display_league(q) or "Other competitions", []).append(q)
    price_by = {}
    for q in priced:
        price_by.setdefault(S.display_league(q) or "Other competitions", []).append(q)
    # Same units assess() returns. soccer_corners is a match, the other clustered
    # sports a market-day. Anything else stays one row per bet.
    clustered = sport in S.DAY_CLUSTERED
    unit = ("match" if sport == "soccer_corners" else "market-day") if clustered else "bet"
    out = []
    for lg in list(dict.fromkeys(list(by) + list(price_by))):
        qs = by.get(lg) or []
        pq = price_by.get(lg) or []
        counted = day_units(qs) if clustered and qs else qs
        n = len(counted)
        won = sum(1 for q in counted if q["status"] == "won")
        exp = sum(q["price"] for q in counted)
        var = sum(q["price"] * (1 - q["price"]) for q in counted)
        # The other side of the same bets, priced at ITS OWN ask — never this row's price with
        # the sign flipped, which would hand the fade a spread it in fact also has to pay.
        rows = []
        for q in qs:
            other = "b" if q["pick"] == "a" else "a"
            p = q.get("price_" + other)
            if q.get("price_draw") is None and q.get("pick") in ("a", "b") and p:
                f = FEE_RATE.get(q.get("venue") or "polymarket", 0.07)
                rows.append((float(p), f, q.get("result") == other))
        cost = sum(p + f * p * (1 - p) for p, f, _w in rows)
        stake_n = n + len(pq)
        # A collapsed day already averaged the fee per rung (day_units pnl_fee). Charging
        # pnl_after_fee on that row would bill a losing day the whole stake.
        fee_pnl = (sum(q["pnl_fee"] if clustered else pnl_after_fee(q) for q in counted)
                   + sum(pnl_after_fee(q) for q in pq))
        out.append(dict(
            league=lg, n=n, won=won, expected=exp, edge=((won - exp) / n) if n else 0.0,
            z=(won - exp) / var ** 0.5 if var > 0 else 0.0,
            roi_fee=(fee_pnl / (stake_n * STAKE)) if stake_n else None,
            n_bets=len(qs), unit=unit,
            fade_n=len(rows), fade_won=sum(1 for _p, _f, w in rows if w),
            fade_expected=sum(p for p, _f, _w in rows),
            fade_roi=((sum(1 for _p, _f, w in rows if w) - cost) / cost) if cost else None))
    return sorted(out, key=lambda r: (-r["edge"], -r["n"]))


def market_cost(d, sports, venues=None):
    """(hold, quotes) for one market: what both its sides cost above 100, pooled.

    The same reading league_cost gives per competition, taken per MARKET instead, because
    that is the other way a rule's toll varies and the bigger of the two: a league match
    winner costs about 1.5% and a side to score 1+ about 4.7%, on the same fixtures.
    """
    v = [q["price_a"] + q["price_b"] - 1.0 for q in all_bets(d)
         if q["sport"] in sports and (S.SOURCES.get(q["source"]) or {}).get("kind") in NEVER_PROMOTED_KINDS
         and q.get("price_a") and q.get("price_b")
         and (venues is None or (q.get("venue") or "polymarket") in venues)]
    return (sum(v) / len(v), len(v)) if v else (None, 0)


def league_cost(d, sports, venues=None):
    """What both sides of a market cost above 100, per competition — {league: (hold, n)}.

    Read from the never-betting baseline rows, which quote every listed market whether or not
    a rule bet on it, so the toll is measured across the whole board rather than only where a
    rule happened to act. It is the floor every rule in that competition has to clear before it
    earns anything, and it is not small or uniform.
    """
    out = {}
    for q in all_bets(d):
        if (q["sport"] not in sports
                or (S.SOURCES.get(q["source"]) or {}).get("kind") not in NEVER_PROMOTED_KINDS
                or not q.get("price_a") or not q.get("price_b")
                or (venues is not None and (q.get("venue") or "polymarket") not in venues)):
            continue
        out.setdefault(S.display_league(q) or "Other competitions", []).append(
            q["price_a"] + q["price_b"] - 1.0)
    return {k: (sum(v) / len(v), len(v)) for k, v in out.items()}


# ---- QA judges only bets on the exchanges a follower can use (2026-09-13) --------------------
# The Sandbox's non-soccer venue was polymarket.com until 2026-09-13, an international exchange
# unavailable to US accounts. QA entry, readiness and demotion count only bets on these venues;
# the .com record stays on the Sandbox page (and in the Sandbox's own stamp) but never moves a pair.
# "combo" since 2026-09-22: a tennis basket is a Kalshi combo, which a US account can buy, and
# leaving it off this list had silently kept every settled basket out of its own record.
TRADEABLE_VENUES = ("polymarket_us", "kalshi", "kalshi_binary", "combo")

# The claim each soccer yes/no domain publishes to the Production feed, in the Leads board's
# bet vocabulary.
# Sports the feed publishes by ROUTE — the venue's own market id and outcome — because there
# is no league table to find the contest in. Soccer is not here: its leads are found by league
# and club name, which is what the Kalshi and Polymarket league maps are for.
# mma and boxing since 2026-09-22, so the pairs moved to Production can publish. A Kalshi
# fight still needs a verified start (VERIFIED_STARTS) — Kalshi's own is an estimate, and a
# bout can walk out well after its card begins — so until one exists only Polymarket US
# fights, which carry their own start, reach the feed.
# cricket since 2026-09-27, so oddspedia|cricket can publish. Kalshi still has no start
# the feed will trust on sight. A cricket row is verified only when its cricket_match
# milestone, the Eastern HHMM in the event ticker, and the rules sentence all agree.
# The rules sentence has to be Kalshi's whole template, and the EDT/EST label has
# to be the one America/New_York is on. No rules text is not agreement. The status,
# when Kalshi states one, has to be exactly "Match Scheduled", "Match Scheduled -
# Pre Match Service", or "Toss Pending". Any other status drops the row. A missing
# status leaves start_source unset. That source is "kalshi_milestone". A
# disagreement or a missing milestone leaves start_source unset and the feed
# refuses the bet — a T20 can begin well after the listed time, and a wrong start
# is worse than no start. Polymarket US carries its own.
ROUTED_SPORTS = ("tennis", "mlb", "nfl", "mma", "boxing", "cricket")
# start_source values that mean a real start time, not the venue's estimate.
# kalshi_milestone is cricket and MMA only, each after its own checker agrees.
VERIFIED_STARTS = ("tennisexplorer", "espn", "mlb", "kalshi_milestone")

# Each sport is named here. A _cup twin and every other suffix are absent on purpose:
# membership is this dict, not a stripped suffix.
#
# THE SIDE IS PART OF THE KIND, which is why soccer_u35_intl could not simply be added.
# total_gte and team_gte are Yes contracts: the rule buys the thing the market is named
# after. total_lte is the UNDER, and Kalshi lists no under contract -- it is the No side of
# the very same over market, so the quote's pick is "b" and FEED_SIDE below says so once,
# here, rather than at each place that reads a bet. Added 2026-10-04 with
# u35_low_scoring|soccer_u35_intl, which had logged 18 settled bets that nothing could
# publish because the feed knew only how to say Yes.
FEED_BETS = {"soccer_o15": {"kind": "total_gte", "n": 2},
             "soccer_o15_intl": {"kind": "total_gte", "n": 2},
             "soccer_team1": {"kind": "team_gte", "n": 1},
             "soccer_team1_intl": {"kind": "team_gte", "n": 1},
             "soccer_team2": {"kind": "team_gte", "n": 2},
             "soccer_u35_intl": {"kind": "total_lte", "n": 3}}

# Which side of the named market each kind buys, as the Sandbox records a pick.
FEED_SIDE = {"total_gte": "a", "team_gte": "a", "total_lte": "b"}


def feed_pick(sport):
    """The only pick the feed can publish for `sport`, or None when it carries no bet."""
    bet = FEED_BETS.get(sport)
    return FEED_SIDE[bet["kind"]] if bet else None


def placeable(q):
    """Is this bet one the Production feed can publish as a standard claim? Today: a soccer
    result (home, away or draw) on a Kalshi GAME market in a mapped league
    (S.KALSHI_GAME_LEAGUES), or a soccer goals market (FEED_BETS) in one of those leagues,
    on the one side that kind names (FEED_SIDE -- Yes for an over or a team total, No for
    an under, since Kalshi lists no under contract). Nothing else — no tennis, MLB, NFL, cricket, table tennis, fights,
    BTTS, weather or crypto yet. A "production-ready" pair whose bets the feed cannot express
    is a label, not a result anyone can follow."""
    if q.get("sport") == "soccer":
        # Draws since 2026-09-16: a draw is claimed as Kalshi's Tie contract on the same GAME event.
        return (q.get("pick") in ("a", "b", "draw") and q.get("venue") == "kalshi"
                and S.quote_league(q) is not None)
    if q.get("sport") in FEED_BETS:
        # The side is fixed by the kind (FEED_SIDE), not chosen per bet: an over market's
        # Yes and its No are two different claims, and only one of them is the rule's.
        return (q.get("pick") == feed_pick(q["sport"]) and q.get("venue") == "kalshi_binary"
                and S.quote_league(q) is not None and bool(q.get("espn_home") and q.get("espn_away"))
                and (FEED_BETS[q["sport"]]["kind"] != "team_gte" or bool(q.get("team"))))
    # A basket. It is publishable because the feed can say exactly what to ask for -- the
    # legs, which side of each, and the most it is worth paying -- even though there is no
    # single market to hit. Every leg must be a Kalshi market, since that is where the
    # collection lives, and the basket's own price is the ceiling.
    if q.get("venue") == "combo":
        legs = q.get("legs") or []
        return bool(
            q.get("pick") == "a" and legs and len(legs) in S.COMBO_MARKUP
            and q.get("price") and 0 < float(q["price"]) < 1
            and all(l.get("venue") == "kalshi" and l.get("market_id") and l.get("pick") in ("a", "b")
                    and l.get("name") for l in legs))
    if q.get("sport") in ROUTED_SPORTS:
        # A contest with no league table to look a fixture up in: the lead carries the market
        # it was priced on and which outcome to back. Polymarket US lists a match as ONE
        # market with two outcomes, so the second side is the No side of that same market;
        # Kalshi lists a market per side, so either is a plain Yes — but only once something
        # has confirmed when the contest starts. For cricket that confirmation is
        # start_source "kalshi_milestone", and that source counts for cricket only.
        # Every other Kalshi sport still needs a verified start from outside Kalshi.
        # An estimate is not enough.
        if not (q.get("pick") in ("a", "b") and bool(q.get("market_id"))
                and bool(q.get("side_a")) and bool(q.get("side_b"))):
            return False
        source = q.get("start_source")
        # kalshi_milestone counts for cricket and MMA, each verified by its own checker and
        # each for its own reason. Cricket takes the milestone instant neat because a T20
        # begins late; MMA subtracts PINNACLE_START_MARGIN_MIN because a fight card walks out
        # early. Every other Kalshi sport still needs a start from outside Kalshi.
        kalshi_ok = (source in VERIFIED_STARTS
                     and (source != "kalshi_milestone"
                          or q.get("sport") in ("cricket", "mma")))
        return q.get("venue") == "polymarket_us" or (q.get("venue") == "kalshi" and kalshi_ok)
    return False


_BAD_START_SEEN = set()
_WARN_CLIP = 80


def _clip_shown(value, limit=_WARN_CLIP):
    """A log-safe slice of a raw field. A 200 KB start must not enter the log."""
    if not isinstance(value, str):
        value = repr(value)
    value = value.replace("\r", " ").replace("\n", " ")
    if len(value) <= limit:
        return value
    return value[:limit] + "…"


def _start_instant(q):
    """Aware UTC start, or None when `start` cannot be read.

    A naive timestamp is UTC, the same reading production._kickoff uses.
    An ISO-shaped string that is not a real instant (month 99, hour 99)
    is None: the shape alone is not a time.
    """
    raw = q.get("start")
    if not isinstance(raw, str) or not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw)
    except (ValueError, TypeError, OverflowError, OSError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _start_key(q):
    """Order a bet by its start text. Every unreadable start sorts last, together.

    A readable start is the raw string under a shared prefix, so a ledger of
    real timestamps sorts exactly as it did when the key was the raw string.
    None, a missing key, and a garbage string share one key.
    """
    raw = q.get("start")
    if isinstance(raw, str) and _start_instant(q) is not None:
        return (0, raw)
    return (1, "")


def _warn_unreadable_start(q):
    if "start" not in q:
        shown = "missing"
    else:
        raw = q.get("start")
        shown = "None" if raw is None else _clip_shown(raw)
    token = (q.get("id"), shown)
    if token in _BAD_START_SEEN:
        return
    _BAD_START_SEEN.add(token)
    # GitHub Actions reads ::warning:: from stderr as well as stdout.
    print(f"::warning::{q.get('id')!r} has unreadable start ({shown}); "
          f"left out of start-dependent checks", file=sys.stderr)


def note_unreadable_start(q):
    """Warn once when `start` is missing or will not parse. The bet is kept.

    The check is a real parse, so an invalid date that only looks like a
    timestamp warns too. A naive timestamp is UTC and is not a warning.
    The row stays in the money totals; span and the halves split skip it.
    """
    if _start_instant(q) is not None:
        return False
    _warn_unreadable_start(q)
    return True


def _span_days(bets):
    """Days from the first start to the last.

    Callers pass bets whose starts read. Both ends are aware, so a naive
    timestamp does not raise against an aware one. When both ends parse,
    this is the same subtraction as reading them directly.
    """
    if len(bets) < 2:
        return 0.0
    first, last = _start_instant(bets[0]), _start_instant(bets[-1])
    if first is None or last is None:
        parsed = [dt for dt in (_start_instant(q) for q in bets) if dt is not None]
        if len(parsed) < 2:
            return 0.0
        first, last = parsed[0], parsed[-1]
    return (last - first).total_seconds() / 86400


def day_units(bets):
    """Collapse bets into one flat bet per market-day (S.market_day): priced at the day's
    average price, paying the day's average P/L, won when that is positive. The unit a
    commodity rule is judged on — see S.DAY_CLUSTERED."""
    days = {}
    for q in bets:
        days.setdefault(S.market_day(q), []).append(q)
    out = []
    for key, qs in days.items():
        pnl = sum(q["pnl"] for q in qs) / len(qs)
        # Fees are charged per RUNG and then averaged, exactly as pnl is. Taking
        # pnl_after_fee of the collapsed row instead would charge a losing day the whole
        # stake: pnl_after_fee returns -STAKE for a loss, which is right for one bet and
        # wrong for a day whose rungs mostly won. KXWTI|20260921 lost $11.17 over 23 rungs,
        # not $100, and charging three such days $100 each is what published cmd_tail at
        # roi +0.28% and roi_fee -15.28% at the same time.
        pnl_fee = sum(pnl_after_fee(q) for q in qs) / len(qs)
        readable = [q for q in qs if _start_instant(q) is not None]
        for q in qs:
            if _start_instant(q) is None:
                note_unreadable_start(q)
        # The representative is the earliest readable start, which is the rung
        # base copies when every start reads. A bad start must not take its place.
        readable.sort(key=lambda q: q["start"])
        rep = readable[0] if readable else qs[0]
        starts = [q["start"] for q in readable]
        out.append(dict(rep, id=key, market_id=key.replace("|", "_"),
                        price=sum(q["price"] for q in qs) / len(qs), pnl=pnl,
                        pnl_fee=pnl_fee, stake=STAKE,
                        status="won" if pnl > 0 else "lost", rungs=len(qs),
                        start=min(starts) if starts else "",
                        logged=min(q["logged"] for q in qs)))
    return sorted(out, key=_start_key)


def clv_read(n, t):
    """What the closing prices say on their own: "ahead"|"behind"|"level"|None (too few).

    Deliberately three-valued. "level" is a real answer — a rule that neither beats nor loses
    to the close is taking the price the market ends up at, which is what most of them do —
    and it must not be confused with not yet knowing.
    """
    if n < CLV_MIN_N or t is None:
        return None
    return "ahead" if t >= CLV_T else "behind" if t <= -CLV_T else "level"


def assess(d, name, sport=None, since=None, venues=None, until=None):
    """Judge one source (optionally in one sport) against APPROVAL.

    `venues`: count only bets on these venues (QA passes TRADEABLE_VENUES).

    Returns dict(status, criteria=[(key, label, passed, detail)], and the metrics).
    status: "unproven" under READ_FLOOR settled bets; "approved" when every criterion
    holds; "failing" when it is readable and not ahead of the price at all; else "watch".
    """
    bets = [q for q in bet_rows(d) if q["source"] == name
            and q["status"] in ("won", "lost") and not climate_excluded(q)
            and not S.tennis_refused_row(q)
            and (sport is None or q["sport"] == sport)
            and (since is None or q["logged"] >= since)
            and (until is None or q["logged"] < until)
            and (venues is None or (q.get("venue") or "polymarket") in venues)]
    for q in bets:
        note_unreadable_start(q)
    bets = sorted(bets, key=_start_key)
    # n_bets is every bet still on the record. A void is not, and neither is a
    # repeat city-day quote: mark_climate_citydays has already set its flag.
    n_bets = len(bets)
    price_bets = [q for q in bet_rows(d) if q["source"] == name
                  and q.get("status") == "settled" and q.get("result") == "price"
                  and not climate_excluded(q)
                  and not S.tennis_refused_row(q)
                  and (sport is None or q["sport"] == sport)
                  and (since is None or q["logged"] >= since)
                  and (until is None or q["logged"] < until)
                  and (venues is None or (q.get("venue") or "polymarket") in venues)]
    for q in price_bets:
        note_unreadable_start(q)
    price_bets = sorted(price_bets, key=_start_key)
    # Day-clustering follows each bet's OWN sport, not the `sport` argument. The all-sport
    # view passes sport=None, which is not in DAY_CLUSTERED, so before 2026-09-27 a source's
    # combined row took the per-bet path and published exactly the z its own sport row was
    # day-clustered to avoid. `spot` is single-sport, so its headline figure WAS that hole.
    day_collapsed = False
    if bets:
        clustered = [q for q in bets if q["sport"] in S.DAY_CLUSTERED]
        if clustered:
            day_collapsed = True
            rest = [q for q in bets if q["sport"] not in S.DAY_CLUSTERED]
            bets = sorted(day_units(clustered) + rest, key=_start_key)
    n = len(bets)
    won = sum(1 for q in bets if q["status"] == "won")
    # Price payouts are in the money totals and out of n, won, and z.
    pnl_wl = sum(q["pnl"] for q in bets)
    pnl = pnl_wl + sum(q["pnl"] for q in price_bets)
    money_stake = (n * STAKE) + sum(float(q.get("stake") or 0.0) for q in price_bets)
    roi = pnl / money_stake if money_stake else None
    expected = sum(q["price"] for q in bets)
    # Significance counts INDEPENDENT outcomes. Bets that cannot all win together (two
    # buckets of one weather ladder) form one cluster, and cluster_stats turns those into the
    # variance of the win count: one 0/1 draw per cluster rather than one per bet, which
    # would treat one day's weather as two coin flips. It drops a cluster that P(1-P) leaves
    # with no variance, and raises once too many of them are, so a nested ladder that does
    # not belong in this path cannot quietly hand back a z — see S.DAY_CLUSTERED.
    clusters = {}
    for q in bets:
        clusters.setdefault(S.outcome_cluster(q), []).append(
            (q["price"], q["price"], q["status"] == "won"))
    c = cluster_stats(clusters)
    var = c["var"]
    n_eff = c["outcomes"]
    # A COLLAPSED DAY is not a 0/1 draw at the rung price, and scoring it as one is what read
    # cmd_tail at z -4.81 while its money was flat. day_units marks a day "won" when its
    # AVERAGE P/L is positive, which needs nearly every rung to land: on a 213-rung gas day
    # at most 3-4 rungs may lose and 3.8 are expected, so the day is close to a coin flip —
    # not the 98.2% event its average rung price implies. Comparing 15 day-wins against the
    # summed rung prices (17.7) is comparing two different things.
    #
    # So a day-clustered record is judged on MONEY. A fairly priced bet returns zero in
    # expectation — p·S·(1/p − 1) + (1−p)·(−S) = 0 — so the day's expected return is zero
    # whatever the rungs' correlation, which is the part no binomial model can get right
    # (a coin ladder's rungs move together, 22 state gas series do not). The statistic is the
    # mean day return over its own standard error, and the dispersion across days carries the
    # correlation without assuming it. cmd_tail reads t +0.34, which is its +0.28%.
    day_t = None
    if day_collapsed or sport in S.DAY_CLUSTERED:
        rets = [q["pnl"] / STAKE for q in bets]
        if len(rets) > 1:
            mean_r = sum(rets) / len(rets)
            sd = (sum((x - mean_r) ** 2 for x in rets) / (len(rets) - 1)) ** 0.5
            day_t = (mean_r / (sd / len(rets) ** 0.5)) if sd else 0.0
    # `won` and `expected` above are the whole record, and stay that way for the hit rate and
    # the money. The z is taken only over the clusters cluster_stats kept, so a contradictory
    # one cannot put its excess wins in the numerator while contributing nothing below.
    z_dropped = c["dropped"]
    z = (c["won"] - c["expected"]) / var ** 0.5 if var > 0 else 0.0
    if day_t is not None:
        z = day_t                      # money, not day-wins — see above
    # Halves and the day span read the clock. A row whose start will not parse
    # stays in n, won, and P&L, and stays out of those two checks, so a lane
    # whose starts all read is unchanged.
    timed = [q for q in bets if _start_instant(q) is not None]
    span_days = _span_days(timed)
    weeks = int(span_days // 7)

    # Against each blind rule on the contests where that rule has a bet, the source's own
    # ROI on exactly those contests. The hardest of them is the one reported.
    blind = []
    for kind in BLIND_KINDS:
        pairs = [(q, blind_pnl(q, kind)) for q in bets]
        pairs = [(q, b) for q, b in pairs if b is not None]
        if not pairs:
            continue
        k = len(pairs) * STAKE
        blind.append((kind, sum(q["pnl"] for q, _b in pairs) / k, sum(b for _q, b in pairs) / k))
    # A RULE that always backs one side (the BTTS form rule backs Yes, and Yes is usually the
    # favourite on the matches it picks) would be "back the favourite" on its own contests by
    # construction, so the same-contest test could never tell it apart. Its blind rule is
    # therefore the POPULATION: backing the same side on EVERY contest of that market over
    # the same period (logged by the market's own never-betting source). Set per source with
    # baseline="population"; nothing else changes.
    if (S.SOURCES.get(name) or {}).get("baseline") == "population" and bets:
        pop_source = next((n for n, m in S.SOURCES.items()
                           if m.get("kind") == "Baseline" and set(m["sports"]) & {q["sport"] for q in bets}), None)
        sides = {q["pick"] for q in bets}
        pop = [q for q in all_bets(d) if q["source"] == pop_source and q["sport"] in {b["sport"] for b in bets}
               and q.get("result") in ("a", "b") and (since is None or q["logged"] >= since)
               and (venues is None or (q.get("venue") or "polymarket") in venues)]
        pnls = []
        for q in pop:
            for side in sides:
                price = q.get("price_a") if side == "a" else q.get("price_b")
                lo, hi = price_band(q.get("sport"))
                if price is not None and lo <= price <= hi:
                    pnls.append(STAKE * (1.0 / price - 1.0) if q["result"] == side else -STAKE)
        own = sum(q["pnl"] for q in bets) / (len(bets) * STAKE)
        blind = ([(f"{'Yes' if sides == {'a'} else 'the same side'} on every match", own,
                   sum(pnls) / (len(pnls) * STAKE))] if pnls else [])
    # A PRICE-BAND rule (back whoever the market prices 0.75-0.90) is "back the favourite" on
    # every one of its own contests, so it too needs a population: backing the FAVOURITE on
    # every contest of the sport over the same period, one quote per contest.
    if (S.SOURCES.get(name) or {}).get("baseline") == "favourite_population" and bets:
        seen_c, fav = set(), []
        # The FIRST price logged for each contest, whether that row is still in the ledger or was
        # folded into the archive — so pruning never changes which price a contest is judged at.
        for q in sorted(all_bets(d), key=_logged_id):
            if (q["sport"] not in {b["sport"] for b in bets} or q.get("result") not in ("a", "b")
                    or q["market_id"] in seen_c or (since is not None and q["logged"] < since)
                    or (venues is not None and (q.get("venue") or "polymarket") not in venues)):
                continue
            pnl_f = blind_pnl(q, "favourite")
            if pnl_f is not None:
                seen_c.add(q["market_id"])
                fav.append(pnl_f)
        own = sum(q["pnl"] for q in bets) / (len(bets) * STAKE)
        blind = [("the favourite on every match", own, sum(fav) / (len(fav) * STAKE))] if fav else []
    # A DRAW-band rule backs the draw on every contest it touches, so the same-contest "back
    # the draw" blind above IS that rule by construction and could never tell it apart. Its
    # population is the same one in spirit as favourite_population: backing the DRAW on every
    # three-way contest the Sandbox listed over the same period, one quote per contest, inside
    # the same price band. Set with baseline="draw_population". Note this pools ALL three-way
    # soccer, not just the rule's own competition — a harder test than the league-only one,
    # and the only one with enough contests to read.
    if (S.SOURCES.get(name) or {}).get("baseline") == "draw_population" and bets:
        seen_c, drawn = set(), []
        for q in sorted(all_bets(d), key=_logged_id):
            if (q["sport"] not in {b["sport"] for b in bets}
                    or q.get("result") not in ("a", "b", "draw")
                    or q.get("price_draw") is None
                    or q["market_id"] in seen_c or (since is not None and q["logged"] < since)
                    or (venues is not None and (q.get("venue") or "polymarket") not in venues)):
                continue
            pnl_d = blind_pnl(q, "draw")
            if pnl_d is not None:
                seen_c.add(q["market_id"])
                drawn.append(pnl_d)
        own = sum(q["pnl"] for q in bets) / (len(bets) * STAKE)
        blind = [("the draw on every match", own, sum(drawn) / (len(drawn) * STAKE))] if drawn else []
    beats_all = bool(blind) and all(own > base for _k, own, base in blind)
    hardest = max(blind, key=lambda t: t[2] - t[1]) if blind else None
    base_roi = hardest[2] if hardest else None
    own_roi = hardest[1] if hardest else None

    top = max((q["pnl"] for q in bets if q["status"] == "won"), default=0.0)
    roi_wo_top = ((pnl_wl - top) / ((n - 1) * STAKE)) if n > 1 else None
    half_n = len(timed)
    half = half_n // 2
    roi_h1 = (sum(q["pnl"] for q in timed[:half]) / (half * STAKE)) if half else None
    roi_h2 = (sum(q["pnl"] for q in timed[half:]) / ((half_n - half) * STAKE)) if half_n - half else None

    A = sport_rules(sport)["approval"]
    criteria = [
        ("sample", f"{A['min_bets']}+ settled bets" + (f" spanning {A['min_days']}+ days" if A['min_days'] else ""),
         n_eff >= A["min_bets"] and span_days >= A["min_days"],
         f"{n} bets" + (f" ({n_eff} independent)" if n_eff != n else "")
         + f" over {span_days:.0f} day{'' if round(span_days) == 1 else 's'}"),
        ("price", f"wins beat the price by z ≥ {A['z_min']:g}",
         n > 0 and z >= A["z_min"], f"{won} won v {expected:.1f} priced, z {z:+.2f}"),
        ("baseline", "beats every blind rule on the same contests",
         beats_all,
         (f"{own_roi*100:+.1f}% v {base_roi*100:+.1f}% back "
          f"{'' if 'every match' in hardest[0] else 'the '}{hardest[0]}"
          if hardest else "no comparable contests")),
        ("one_hit", "still profitable without its biggest win",
         roi_wo_top is not None and roi_wo_top > 0,
         f"{roi_wo_top*100:+.1f}% without it" if roi_wo_top is not None else "—"),
        ("halves", "profitable in both halves of its record",
         bool(roi_h1 and roi_h2 and roi_h1 > 0 and roi_h2 > 0),
         (f"{roi_h1*100:+.1f}% then {roi_h2*100:+.1f}%" if roi_h1 is not None
          and roi_h2 is not None else "—")),
    ]
    if n_eff < READ_FLOOR:
        status = "unproven"
    elif all(c[2] for c in criteria):
        status = "approved"
    elif (roi or 0) <= 0 or z <= 0:
        status = "failing"
    else:
        status = "watch"
    # A collapsed day carries its own pnl_fee, feed per rung before averaging. Falling back
    # to pnl_after_fee on the collapsed row would charge a losing day the whole stake.
    pnl_fee = (sum(q["pnl_fee"] if "pnl_fee" in q else pnl_after_fee(q) for q in bets)
               + sum(pnl_after_fee(q) for q in price_bets))
    # CLIMATE CARRIES NO READABLE CLV. Its close_price is captured near the event, by which
    # time the temperature is largely settled, so the close tracks the RESULT rather than the
    # price: bought 0.21 closed 0.06 lost, bought 0.34 closed 0.53 won. Both nws and nws_fade
    # read -26c to -30c a bet on a book whose median hold is 1.00% — the tightest here — and
    # both sides of a 1% book cannot be 26c worse than fair. It was being published as
    # "t -4.40 · 7 closes", which restates that the bets lost and reads as if it were evidence
    # about the entry price. No CLV is reported for climate rather than a misleading one.
    clv = ([] if sport == "climate"
           else [q["close_price"] - q["price"] for q in bets if fresh_close(q)])
    # The spread of the moves, not just their average: a mean of +1c means one thing when the
    # moves are all +1c and another when they run from -20c to +22c. t is that mean over its
    # own standard error, which is what makes CLV readable long before the win record is.
    clv_sd = (sum((c - sum(clv) / len(clv)) ** 2 for c in clv) / len(clv)) ** 0.5 if len(clv) > 1 else None
    clv_t = ((sum(clv) / len(clv)) / (clv_sd / len(clv) ** 0.5)) if clv_sd else None
    return dict(status=status, criteria=criteria, n=n, sport=sport, won=won, roi=roi, pnl=pnl,
                n_price=len(price_bets),
                n_bets=n_bets, unit=("match" if sport == "soccer_corners" else
                                     "market-day" if sport in S.DAY_CLUSTERED or day_collapsed else
                                     "bet"),
                z=z, weeks=weeks, span_days=span_days, n_eff=n_eff, z_dropped=z_dropped,
                base_roi=base_roi, own_roi=own_roi, expected=expected,
                roi_fee=(pnl_fee / money_stake) if money_stake else None,
                clv=(sum(clv) / len(clv)) if clv else None, clv_n=len(clv),
                clv_sd=clv_sd, clv_t=clv_t, clv_read=clv_read(len(clv), clv_t),
                routed=sum(1 for q in bets if placeable(q)),
                clv_beat=(sum(1 for c in clv if c > 0) / len(clv)) if clv else None)


def qa_entry(a):
    """[(key, label, passed, detail)] for the QA entry gate, from an assess() result."""
    c = {k: (p, det) for k, _l, p, det in a["criteria"]}
    E = sport_rules(a.get("sport"))["entry"]
    return [
        ("sample", f"{E['min_bets']}+ settled bets" + (f" spanning {E['min_days']}+ days" if E['min_days'] else ""),
         a.get("n_eff", a["n"]) >= E["min_bets"] and a["span_days"] >= E["min_days"],
         f"{a['n']} bets over {a['span_days']:.0f} day{'' if round(a['span_days']) == 1 else 's'}"),
        ("price", f"wins beat the price by z ≥ {E['z_min']:g}", a["n"] > 0 and a["z"] >= E["z_min"],
         f"{a['won']} won v {a['expected']:.1f} priced, z {a['z']:+.2f}"),
        ("baseline", "beats every blind rule on the same contests", *c["baseline"]),
        ("one_hit", "still profitable without its biggest win", *c["one_hit"]),
    ]


def clv_sample(a):
    """Is there enough closing-price evidence to judge CLV at all? See READY_CLV."""
    return (a["clv"] is not None and a["clv_n"] >= READY_CLV["min_n"]
            and a["clv_n"] >= READY_CLV["min_share"] * a["n"])


def ready_gate(a):
    """Production-ready, judged on QA's fresh data: the stamp, positive CLV, positive after fees."""
    stamp = [(k, l, p, det) for k, l, p, det in a["criteria"]]
    return stamp + [
        ("clv", f"beats the closing price by t ≥ {CLV_T:g} ({READY_CLV['min_n']}+ closes, "
                f"{READY_CLV['min_share']:.0%}+ of bets)",
         clv_sample(a) and a["clv"] > 0 and (a.get("clv_t") or 0) >= CLV_T,
         (f"{a['clv']*100:+.1f}¢ on {a['clv_n']} of {a['n']} bets, t {a.get('clv_t') or 0:+.2f}, "
          f"{a['clv_beat']:.0%} beat the close"
          if a["clv"] is not None else "no closing prices yet")),
        ("route", "every one of these bets is a standard exchange market the feed can publish",
         a["n"] > 0 and a.get("routed", 0) == a["n"],
         (f"{a.get('routed', 0)} of {a['n']} bets are a publishable exchange market"
          + ("" if a.get("routed", 0) == a["n"] else " — see sandbox_track.placeable"))
         if a["n"] else "—"),
        ("fees", "profitable after the taker fee",
         a["roi_fee"] is not None and a["roi_fee"] > 0,
         f"{a['roi_fee']*100:+.1f}% after fees" if a["roi_fee"] is not None else "—"),
    ]


def load_stages(path=None):
    path = path or STAGES
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return {"pairs": {}, "events": []}


def save_stages(st, path=None):
    path = path or STAGES
    atomic_write_json(path, st, prefix=".stages-")


def _snapshot(a):
    return {k: (round(v, 4) if isinstance(v, float) else v) for k, v in a.items()
            if k in ("n", "weeks", "span_days", "z", "roi", "roi_fee", "base_roi", "own_roi", "clv", "clv_n")}


def _last_logged(d, name, sport, since):
    """Latest `logged` of any bet (open or settled) for the pair since `since`, or None."""
    ts = [q["logged"] for q in all_bets(d)
          if q["source"] == name and q["sport"] == sport and q.get("bet")
          and (q.get("venue") or "polymarket") in TRADEABLE_VENUES
          and q["status"] != "void" and q["logged"] >= since]
    return max(ts) if ts else None


def demote_reason(d, name, sport, pair, a, now):
    """Why a QA pair goes back to the Sandbox this run, or None."""
    since = pair["promoted_at"]
    last = _last_logged(d, name, sport, since) or since
    if now - datetime.fromisoformat(last) >= timedelta(days=STALE_DAYS):
        return f"no new bet in {STALE_DAYS} days"
    if a["n"] < sport_rules(sport)["demote_bets"]:
        return None
    if a["z"] < QA_DEMOTE["z_below"]:
        return f"fresh QA record behind the price, z {a['z']:+.2f}"
    base = dict((k, (p, det)) for k, _l, p, det in a["criteria"])["baseline"]
    if not base[0]:
        return f"not beating every blind rule ({base[1]})"
    # The closing price is REPORTED on the page, not enforced. Every pair in Production was
    # put there by hand with its CLV visible, so the number is an argument for taking it off
    # the list, not a reason for the tracker to do it. Losing to the prices actually paid, not
    # beating the blind rules, and going quiet all still demote.
    return None


def evaluate_stages(d, st, now=None, verbose=True):
    """Move the pairs listed in PAIR_OVERRIDES into Production; demote the ones that stop
    working. There is no automatic promotion: listing a pair is the decision.

    Every change is appended to st["events"] with the evidence it was made on. Returns the
    list of changes made this run.
    """
    now = (now or datetime.now(timezone.utc)).replace(microsecond=0)
    now_s = now.isoformat()
    changes = []
    for name, meta in S.SOURCES.items():
        if not meta["connected"] or meta.get("kind") in NEVER_PROMOTED_KINDS:
            continue
        for sport in meta["sports"]:
            key = f"{name}|{sport}"
            pair = st["pairs"].get(key) or dict(stage="sandbox", since=None)
            ov = PAIR_OVERRIDES.get(key)
            # A move made AFTER a demotion cancels it — that is a decision taken with the
            # demotion known — while an older listing cannot resurrect a pair demoted since.
            # The demotion also reset the pair's clock, so cancelling it restores the whole
            # record: what a pair did in the Sandbox counts towards Production.
            if ov and pair.get("demoted_at") and ov["moved_on"] >= str(pair["demoted_at"])[:10]:
                pair = {k: v for k, v in pair.items() if k not in ("demoted_at", "since")}

            if pair["stage"] == "sandbox":
                if not ov or pair.get("demoted_at"):
                    if pair.get("since") or key in st["pairs"]:
                        st["pairs"][key] = pair
                    continue
                a = assess(d, name, sport, since=pair.get("since"), venues=TRADEABLE_VENUES)
                pair = dict(stage="production", promoted_at=now_s, entry=_snapshot(a),
                            entry_since=pair.get("since"), by_hand=ov["moved_on"])
                changes.append(dict(pair=key, to="production", at=now_s, evidence=_snapshot(a),
                                    reason=f"moved to Production by hand on {ov['moved_on']}"))
                # With no threshold, it is ready from THIS run. Waiting for the next one would
                # mean a pair listed by hand sits idle for three hours for no reason.
                if ov.get("production_at") is None:
                    pair = dict(pair, ready_since=now_s, ready_at=now_s)
                    changes.append(dict(pair=key, to="ready", at=now_s, evidence=_snapshot(a),
                                        reason="moved by hand — ready from this run"))
            elif pair["stage"] in ("production", "qa"):       # "qa": a stage saved before the change
                pair = dict(pair, stage="production")
                if not ov:
                    # Taken off the list by hand: back to the Sandbox, still measured.
                    # demoted_at rides along so the page can still show the record it was
                    # removed ON. Without it the pair's window restarts empty and reads as a
                    # brand-new source, and sandbox_build's "removed" branch -- written for
                    # exactly this -- never fires. Only the automatic net was setting it, so
                    # every by-hand removal (olbg|boxing, pm_combo4) lost its history.
                    pair = dict(stage="sandbox", since=now_s, demoted_at=now_s)
                    changes.append(dict(pair=key, to="sandbox", at=now_s,
                                        reason="taken off the Production list by hand"))
                    st["pairs"][key] = pair
                    continue
                a = assess(d, name, sport, since=qa_since(pair, sport, key), venues=TRADEABLE_VENUES)
                why = demote_reason(d, name, sport, pair, a, now)
                if why:
                    pair = dict(stage="sandbox", since=now_s, demoted_at=now_s)
                    changes.append(dict(pair=key, to="sandbox", at=now_s, evidence=_snapshot(a),
                                        reason=why))
                else:
                    # With no threshold set, listing the pair IS the decision: it is ready
                    # from this run. Judging it on a handful of Sandbox bets first would be the
                    # tracker second-guessing a call that is not its to make — demotion is the
                    # safety net, and it reads the whole record. With a threshold, the pair
                    # waits for that many settled bets AND for the record to be profitable.
                    need = ov.get("production_at")
                    ok = True if need is None else (a["n"] >= need and (a["roi_fee"] or 0) > 0)
                    if ok and not pair.get("ready_at"):
                        pair = dict(pair, ready_since=now_s, ready_at=now_s)
                        changes.append(dict(
                            pair=key, to="ready", at=now_s, evidence=_snapshot(a),
                            reason=(f"reached {need} settled bets, profitable after fees" if need
                                    else "moved by hand — ready from this run")))
                    elif not ok and pair.get("ready_at"):
                        changes.append(dict(pair=key, to="unready", at=now_s, evidence=_snapshot(a),
                                            reason="no longer profitable after fees"))
                        pair = {k: v for k, v in pair.items() if k not in ("ready_since", "ready_at")}
            if pair.get("stage") != "sandbox" or pair.get("since") or key in st["pairs"]:
                st["pairs"][key] = pair
    st["events"].extend(changes)
    st["updated"] = now_s
    if verbose:
        for c in changes:
            print(f"  stage: {c['pair']} -> {c['to']}")
    return changes


RETAIN_DAYS = 45

# Sports whose Polymarket prices were measured to be placeholders before the book gate
# existed (MAX_SPREAD in sandbox_sources): boxing and cricket against Pinnacle, table
# tennis at 91% of rows logged within 0.47-0.53. Tennis, MLB and NFL books were real
# (tennis within 2pp of Pinnacle), so their history is left alone.
PRE_GATE_SPORTS = ("boxing", "cricket", "table_tennis")
PRE_GATE_NOTE = "pre-gate: logged at an unverified Polymarket placeholder price"


LATE_NOTE = "logged at or after the start: not a prediction"


def retire_late(d, verbose=True):
    """Void every quote logged at or after its contest's start, whatever its result.

    The rule publish() now enforces, applied to what was logged before it was. Idempotent.
    Returns the number voided.
    """
    voided = 0
    for q in d["quotes"]:
        if S.removed_row(q) or q.get("status") == "void":
            continue
        try:
            late = (datetime.fromisoformat(q["logged"]) >= datetime.fromisoformat(q["start"]))
        except (KeyError, TypeError, ValueError):
            continue
        if late:
            q["status"], q["pnl"], q["note"] = "void", 0.0, LATE_NOTE
            q["settled"] = q.get("settled") or now_iso()
            voided += 1
    if verbose and voided:
        print(f"  late quotes: voided {voided} logged at or after the start")
    return voided


SAME_CONTEST_H = 3          # doubleheaders start 3.5h+ apart; one contest never moves more
# Table tennis leagues (Setka Cup, TT Elite) replay the same pairing within the same evening,
# so there two quotes are one contest only if their starts agree to the minute-scale.
SAME_CONTEST_H_BY_SPORT = {"table_tennis": 10 / 60}
# Kalshi stores a placeholder start, measured 4.5 to 8.5 hours off the real start. Twelve
# hours covers that slip and still leaves a series (the next game, a day later) alone.
# It is too wide for a doubleheader, so baseball does not use it.
PLACEHOLDER_H = 12
# Same two names can be two different contests inside one day: a baseball doubleheader
# or series game, and a table-tennis rematch. Those keep the tight window only.
SAME_DAY_REPLAY = frozenset({"mlb", "table_tennis"})
DUPLICATE_SINCE = "2026-09-13T21:00:00+00:00"   # the venue switch; settled history is not rewritten
DUPLICATE_NOTE = "duplicate: this source already had a quote on this contest on another venue"
# An open MMA favourite-band bet booked on Kalshi cannot be published: Kalshi has no
# verified start for a fight. When Polymarket US lists that fight before the start,
# the Kalshi row is retired with this note and one fresh Polymarket US entry replaces it.
KALSHI_UNPLACEABLE = "kalshi_unplaceable"
_KX_DATE = re.compile(r"-(\d{2})(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)(\d{2})")
_ISO_DATE = re.compile(r"(20\d{2}-\d{2}-\d{2})")
_GAME_TAG = re.compile(r"-(dh\d+|g\d+)$", re.I)
_MONTH_NUM = {"JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
              "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12}


def _kalshi_sourced(q):
    """A row priced on Kalshi, or carrying a Kalshi ticker, whose start may be a placeholder."""
    if q.get("venue") in ("kalshi", "kalshi_binary"):
        return True
    return str(q.get("market_id") or "").startswith("KX")


def _game_tag(q):
    """dh1 / dh2 / g2 when the market id names one game of a doubleheader."""
    m = _GAME_TAG.search(str(q.get("market_id") or ""))
    return m.group(1).lower() if m else None


def _separate_games(a, b):
    """True when both ids name a game of a doubleheader and they are not the same game."""
    ta, tb = _game_tag(a), _game_tag(b)
    return bool(ta and tb and ta != tb)


def _iso_day(text):
    s = str(text or "")[:10]
    if len(s) == 10 and s[4] == "-" and s[7] == "-":
        try:
            datetime.strptime(s, "%Y-%m-%d")
        except ValueError:
            return None
        return s
    return None


def _event_dates(q):
    """Calendar days that name this contest: the row's date, and any date encoded in its id.

    The start is not included. A Kalshi placeholder start is the thing that is wrong, so
    using it as the event date would make two different games look like one whenever the
    placeholder happened to land on the other game's day.
    """
    out = set()
    day = _iso_day(q.get("date"))
    if day:
        out.add(day)
    mid = str(q.get("market_id") or "")
    m = _KX_DATE.search(mid)
    if m:
        mon = _MONTH_NUM.get(m.group(2))
        if mon:
            out.add(f"20{m.group(1)}-{mon:02d}-{m.group(3)}")
    for found in _ISO_DATE.findall(mid):
        if _iso_day(found):
            out.add(found)
    if not out:
        try:
            start = datetime.fromisoformat(str(q["start"]))
        except (KeyError, TypeError, ValueError):
            start = None
        if start is not None:
            out.add(start.date().isoformat())
    return out


def _dates_compatible(a, b, slack_days=1):
    """Same event date, or one day apart when a placeholder start crosses midnight."""
    da, db = _event_dates(a), _event_dates(b)
    if not da or not db:
        return True
    if da & db:
        return True
    for x in da:
        for y in db:
            try:
                gap = abs((datetime.strptime(x, "%Y-%m-%d") - datetime.strptime(y, "%Y-%m-%d")).days)
            except ValueError:
                continue
            if gap <= slack_days:
                return True
    return False


def _id_scheme(q):
    """How the market id is spelled. A venue switch mints a new scheme for the same contest."""
    mid = str(q.get("market_id") or "")
    if mid.startswith("KX"):
        return "kalshi_ticker"
    if mid.startswith("aec-"):
        return "aec"
    if mid.isdigit():
        return "numeric"
    return "other"


def _cross_venue_ids(a, b):
    """Two ids for one contest: different venue, or the same venue under a different id scheme."""
    if a.get("market_id") == b.get("market_id"):
        return False
    if (a.get("venue") or "") != (b.get("venue") or ""):
        return True
    return _id_scheme(a) != _id_scheme(b)


def _same_contest_quote(a, b):
    """Are two quotes about the same contest, whatever venue or market id each carries?

    Participants have to match, and so does the event date. A start within three hours is
    enough on its own (a doubleheader's two games are further apart than that). A Kalshi
    placeholder can sit 4.5 to 8.5 hours off the real start, so when one row is Kalshi's
    the same participants on the same event date still count out to twelve hours. Baseball
    and table tennis do not get that wider window: a doubleheader, a series game, and a
    rematch are different contests that share names.
    """
    if a.get("sport") != b.get("sport"):
        return False
    if _separate_games(a, b):
        return False
    try:
        gap = abs((datetime.fromisoformat(str(a["start"])) -
                   datetime.fromisoformat(str(b["start"]))).total_seconds())
    except (KeyError, TypeError, ValueError):
        return False
    sport = a.get("sport")
    tight = SAME_CONTEST_H_BY_SPORT.get(sport, SAME_CONTEST_H) * 3600
    # A yes/no market, and a combo basket, is identified by its id alone. Every basket is
    # named "All n win" v "Any one loses", so matching on side names made every basket of a
    # day look like the same contest and dropped all but the first.
    if a.get("venue") in ("kalshi_binary", "combo") or b.get("venue") in ("kalshi_binary", "combo"):
        return gap <= tight and a.get("market_id") == b.get("market_id")
    wide = (sport not in SAME_DAY_REPLAY and gap <= PLACEHOLDER_H * 3600
            and (_kalshi_sourced(a) or _kalshi_sourced(b))
            and _dates_compatible(a, b))
    if gap > tight and not wide:
        return False
    score, _flip = S.pair_match(a.get("side_a"), a.get("side_b"), b.get("side_a"), b.get("side_b"),
                                sport=sport)
    return score > 0


def settled_cross_venue_dups(quotes):
    """Settled bets that repeat an earlier settled bet on the same contest, another venue.

    The earliest logged bet is the one that stands. Later copies are the ones to void.
    A doubleheader, a series game, and a table-tennis rematch are not pairs: they fail
    `_same_contest_quote`. Returns [(later, kept), ...] in log order of the later bet.
    """
    seen, rows = set(), []
    for q in quotes:
        i = q.get("id")
        if i in seen:
            continue
        seen.add(i)
        rows.append(q)
    by, pairs = {}, []
    for q in sorted(rows, key=lambda q: q.get("logged") or ""):
        if not q.get("bet") or q.get("status") not in ("won", "lost"):
            continue
        pool = by.setdefault((q.get("source"), q.get("sport")), [])
        earlier = next((p for p in pool
                        if _cross_venue_ids(p, q) and _same_contest_quote(p, q)), None)
        if earlier is not None:
            pairs.append((q, earlier))
            continue
        pool.append(q)
    return pairs


def retire_venue_duplicates(d, verbose=True):
    """Void a quote when the SAME source already had one on the same contest on another venue.

    A quote is logged once per (source, market id). When the venue moved from polymarket.com
    to Polymarket US on 2026-09-13, every contest got a new market id, and the first run
    re-quoted 98 contests its sources had already priced on .com — 20 as a second bet on the
    same game. The earliest quote stands (logged once, never revised); later ones are voided.
    publish() now refuses them up front. Idempotent. Returns the number voided.
    """
    by = {}
    for q in sorted(d["quotes"], key=lambda q: q.get("logged") or ""):
        if S.removed_row(q) or q.get("status") == "void":
            continue
        pool = by.setdefault((q["source"], q["sport"]), [])
        if (q.get("status") == "open" and (q.get("logged") or "") >= DUPLICATE_SINCE
                and any(p.get("market_id") != q.get("market_id") and _same_contest_quote(p, q)
                        for p in pool)):
            q["status"], q["pnl"], q["note"] = "void", 0.0, DUPLICATE_NOTE
            q["settled"] = q.get("settled") or now_iso()
            continue
        pool.append(q)
    voided = sum(1 for q in d["quotes"] if q.get("note") == DUPLICATE_NOTE)
    if verbose and voided:
        print(f"  venue duplicates: {voided} voided in total")
    return voided


# The map is the row to void -> the row that stands.
# Castaneda: the earlier Polymarket US row stands. pair_match has to agree.
# Medvedev v Royer: Kalshi was logged first (2026-09-24T07:39:55Z, +28.21)
# and the Polymarket US copy later (2026-09-26T06:43:41Z, +26.58). The starts
# are 26.8h apart, so this one is pinned instead of matched.
SETTLED_DUP_VOIDS = {
    "mma_fav_band:KXUFCFIGHT-26SEP26CASHEI": "mma_fav_band:aec-ufc-johcas-alaten-2026-09-26",
    "tennis_fav_band:aec-atp-danmed-valroy-2026-09-23": "tennis_fav_band:KXATPMATCH-26SEP25MEDROY",
}
# Pinned void ids skip pair_match. Same lane, same side_a and side_b, same
# pick, both settled won or lost bets. The contest window is not widened.
SETTLED_DUP_PINNED = frozenset({
    "tennis_fav_band:aec-atp-danmed-valroy-2026-09-23",
})


def _ledger_row(d, row_id):
    """The quote with this id, or the archived copy when the quote has rolled up."""
    for q in d.get("quotes") or []:
        if q.get("id") == row_id:
            return q, False
    for q in d.get("_archive") or []:
        if q.get("id") == row_id:
            return q, True
    return None, False


def _unroll_voided_archive(d, q, old_status, old_pnl):
    """A pruned bet was folded into retired. Voiding it takes that P/L back out."""
    r = (d.get("retired") or {}).get(q.get("source"))
    if not r:
        return
    r["settled"] = r.get("settled", 0) - 1
    if old_status == "won":
        r["won"] = r.get("won", 0) - 1
    r["staked"] = round(r.get("staked", 0.0) - float(q.get("stake") or 0.0), 2)
    r["pnl"] = round(r.get("pnl", 0.0) - float(old_pnl or 0.0), 2)
    if (q.get("result") in ("a", "b") and not q.get("untraded")
            and q.get("prob_a") is not None):
        term = (q["prob_a"] - (1.0 if q["result"] == "a" else 0.0)) ** 2
        r["brier_sum"] = r.get("brier_sum", 0.0) - term
        r["brier_n"] = r.get("brier_n", 0) - 1


def _pinned_same_side(later, kept):
    """True when both rows name the same competitors and bet the same side."""
    return (later.get("side_a") == kept.get("side_a")
            and later.get("side_b") == kept.get("side_b")
            and later.get("side_a") not in (None, "")
            and later.get("side_b") not in (None, "")
            and later.get("pick") == kept.get("pick"))


def void_listed_settled_dups(d, verbose=True):
    """Void the rows named in SETTLED_DUP_VOIDS when they are the same contest.

    Both rows have to be in the ledger, in the same lane, betting the same
    pick, and settled won or lost. A Castaneda entry also needs pair_match to
    agree. A pinned entry (Medvedev v Royer) needs the same side_a and side_b
    instead, because its starts are outside the contest window. The settled
    time stays. The note is 'dup of <kept id>'. A row already voided is left
    alone, so a second call changes nothing.
    """
    n = 0
    for void_id, kept_id in SETTLED_DUP_VOIDS.items():
        later, later_archived = _ledger_row(d, void_id)
        kept, _kept_archived = _ledger_row(d, kept_id)
        if later is None or kept is None:
            continue
        if (later.get("source"), later.get("sport")) != (kept.get("source"), kept.get("sport")):
            continue
        if not later.get("bet") or not kept.get("bet"):
            continue
        if later.get("status") not in ("won", "lost") or kept.get("status") not in ("won", "lost"):
            continue
        if void_id in SETTLED_DUP_PINNED:
            if not _pinned_same_side(later, kept):
                continue
        else:
            score, _flip = S.pair_match(later.get("side_a"), later.get("side_b"),
                                        kept.get("side_a"), kept.get("side_b"),
                                        sport=later.get("sport"))
            if not score or later.get("pick") != kept.get("pick"):
                continue
        old_status, old_pnl = later.get("status"), later.get("pnl")
        settled = later.get("settled")
        later["status"] = "void"
        later["pnl"] = 0.0
        later["note"] = f"dup of {kept_id}"
        later["settled"] = settled
        if later_archived:
            _unroll_voided_archive(d, later, old_status, old_pnl)
            month = str(settled or "")[:7]
            if month:
                d.setdefault("_archive_dirty", set()).add(month)
        n += 1
    if verbose and n:
        print(f"  settled duplicates: voided {n}")
    return n


def retire_pre_gate(d, now=None, verbose=True):
    """One rule, applied blind to outcomes, for quotes logged before the book gate.

    A Polymarket-venue quote in a PRE_GATE_SPORTS sport that carries no `spread` was
    priced off a midpoint with no book check. It cannot be verified after the fact, so:

      * not yet started -> removed, so the contest is quoted again under the gate on the
        next run, at a real price and still before the start;
      * started or settled -> voided with PRE_GATE_NOTE: no stake, no P/L, no Brier.

    Idempotent: removed rows are gone and voided rows are skipped. Returns (removed, voided).
    """
    now = now or datetime.now(timezone.utc)
    keep, removed, voided = [], 0, 0
    for q in d["quotes"]:
        if S.removed_row(q):
            keep.append(q)
            continue
        pre_gate = (q.get("venue", "polymarket") == "polymarket"
                    and q.get("sport") in PRE_GATE_SPORTS and "spread" not in q
                    and q.get("note") != PRE_GATE_NOTE)
        if not pre_gate:
            keep.append(q)
            continue
        try:
            start = datetime.fromisoformat(q["start"])
            if start.tzinfo is None:
                start = start.replace(tzinfo=timezone.utc)
        except (KeyError, TypeError, ValueError):
            start = now
        if q["status"] == "open" and start > now:
            removed += 1
            continue
        q["status"], q["pnl"], q["note"] = "void", 0.0, PRE_GATE_NOTE
        q["settled"] = q.get("settled") or now_iso()
        voided += 1
        keep.append(q)
    d["quotes"] = keep
    if verbose and (removed or voided):
        print(f"  pre-gate prices: removed {removed} unstarted quotes for re-quoting, "
              f"voided {voided} started or settled")
    return removed, voided


PRICE_RETAIN_DAYS = 7
# Fields a population baseline reads (assess: baseline="population" / "favourite_population").
COMPACT_FIELDS = ("id", "source", "sport", "market_id", "venue", "logged", "start", "settled",
                  "result", "price_a", "price_b", "price_draw", "status")


def prune(d, retain_days=RETAIN_DAYS, verbose=True, price_days=PRICE_RETAIN_DAYS):
    """Fold long-settled quotes into per-source totals and drop the rows.

    Every bet leaving the ledger, void included, is archived whole (ARCHIVE_DIR).
    The ledger is rewritten and committed four times a day, so every row kept is a row
    re-stored in git forever. Left alone this grows by roughly a megabyte a week. Old
    rows are therefore rolled up rather than deleted: the lifetime record survives in
    `retired`, only the per-contest detail is discarded, and nothing OPEN is ever touched.

    Price-only rows (bet=False: the venues' own prices, Baselines, models below the edge) are
    three quarters of the ledger and are folded after `price_days` (2026-09-15) instead of
    `retain_days`. Their Brier sample survives in the totals. Price-only rows get a compact
    copy only for an a/b/draw result, for Baseline rows, and for one row per contest
    otherwise. The rest (e.g. result "price", or a contest already covered) are rolled up
    by design because nothing reads them.
    """
    now = datetime.now(timezone.utc)
    cutoff = (now - timedelta(days=retain_days)).isoformat()
    price_cutoff = (now - timedelta(days=price_days)).isoformat()
    keep, rolled = [], 0
    ret = d.setdefault("retired", {})
    archived = {x["id"] for x in d.get("_archive") or []}
    contests = {(x.get("sport"), x.get("market_id")) for x in d.get("_archive") or [] if x.get("compact")}

    def to_archive(row):
        d.setdefault("_archive", []).append(row)
        archived.add(row["id"])
        d.setdefault("_archive_dirty", set()).add(str(row["settled"])[:7])

    for q in d["quotes"]:
        if S.removed_row(q):
            keep.append(q)
            continue
        horizon = cutoff if q.get("bet") else price_cutoff
        if q["status"] == "open" or not q.get("settled") or q["settled"] >= horizon:
            keep.append(q)
            continue
        # A row with no id cannot be archived or folded up: the archive is keyed
        # by id, and dropping the row would lose it. This has to run before the
        # bet branch. A void older than the horizon is a bet, and that branch
        # reads q["id"].
        if not q.get("id"):
            keep.append(q)
            # GitHub Actions reads ::warning:: from stderr as well as stdout.
            print(f"::warning::row with no id kept in the ledger"
                  f" ({q.get('source') or '?'}/{q.get('market_id') or '?'})",
                  file=sys.stderr)
            continue
        if q.get("bet"):
            if q["id"] not in archived:
                to_archive(q)
        elif (not q.get("bet") and q.get("result") in ("a", "b", "draw") and q.get("price_a") is not None
              and q["id"] not in archived):
            baseline = (S.SOURCES.get(q["source"]) or {}).get("kind") == "Baseline"
            if baseline or (q.get("sport"), q.get("market_id")) not in contests:
                to_archive(dict({k: q.get(k) for k in COMPACT_FIELDS}, bet=False, compact=True))
                contests.add((q.get("sport"), q.get("market_id")))
        r = ret.setdefault(q["source"], dict(quotes=0, bets=0, settled=0, won=0,
                                             staked=0.0, pnl=0.0,
                                             brier_sum=0.0, brier_n=0))
        r["quotes"] += 1
        if q["bet"]:
            r["bets"] += 1
        if q["status"] in ("won", "lost") and not climate_excluded(q):
            r["settled"] += 1
            r["won"] += 1 if q["status"] == "won" else 0
            r["staked"] += q["stake"]
            r["pnl"] += q["pnl"]
        elif (q.get("bet") and q.get("result") == "price" and q.get("status") == "settled"
              and not climate_excluded(q)):
            # The money stays in the lifetime total. The win count does not move.
            r["staked"] += q["stake"]
            r["pnl"] += q["pnl"]
        if (q.get("result") in ("a", "b") and not q.get("untraded")
                and q.get("prob_a") is not None and not climate_excluded(q)):
            r["brier_sum"] += (q["prob_a"] - (1.0 if q["result"] == "a" else 0.0)) ** 2
            r["brier_n"] += 1
        rolled += 1

    d["quotes"] = keep
    if verbose and rolled:
        print(f"  rolled up {rolled} settled quotes (bets older than {retain_days}d, price-only rows older than {price_days}d)")
    return rolled


def main():
    print("Sandbox Tracker")
    # The feed first, before anything slow. A pair demoted since the last run is still named
    # in it until it is rebuilt, and the rebuild is at the END of a run that takes minutes.
    # The feed is the one artefact here that reaches past a web page, so it stops naming a
    # demoted pair now rather than in ten minutes' time.
    try:
        import production
        n_pruned = production.prune_feed()
        if n_pruned:
            print(f" production feed: dropped {n_pruned} lead(s) from pairs no longer in Production")
    except Exception as e:
        # Soft-fail, and only here. This prune drops leads the rebuild at the end of
        # the run would drop anyway; bailing out would also skip grading. A failure
        # of that rebuild is not soft: main() returns non-zero so the job does not
        # publish a feed that was left as it was.
        print(f"  ! production feed prune failed: {type(e).__name__}: {str(e)[:80]}")
    d = load()
    print(f" closing prices merged from the close job: {apply_closes(d, load_closes())}")
    retire_pre_gate(d)
    retire_late(d)
    retire_venue_duplicates(d)
    void_listed_settled_dups(d)
    # Stage timings are printed so a slow run in CI names its own culprit. The first
    # run with soccer on Kalshi took 14.6 minutes against 3 before it, with only 25s of
    # CPU — all of it waiting on the network, and no log line said where.
    t0 = time.time()
    print(" collecting…")
    universe, coverage = collect(combo_used=combo_used_legs(d))
    print(f"  ({time.time() - t0:.0f}s)")
    t1 = time.time()
    print(" publishing…")
    publish(d, universe, coverage)
    print(f"  ({time.time() - t1:.0f}s)")
    t2 = time.time()
    print(" grading…")
    grade(d)
    print(f"  ({time.time() - t2:.0f}s, run total {time.time() - t0:.0f}s)")
    prune(d)
    # After grading and pruning, so a quote that settled this run is marked
    # before it is saved, including one that just moved to the archive.
    # Same rule, nothing to write. A changed rule clears and re-marks.
    n_city = mark_climate_citydays(d)
    if n_city:
        print(f"  climate city-days: re-marked {n_city} quote(s) under {CLIMATE_KEEP_RULE}")
    save(d)
    st = load_stages()
    evaluate_stages(d, st)
    save_stages(st)
    # Production: the machine-readable feed of Production leads, next to the Leads ledger.
    # The ledger is already saved above. A failed rebuild returns non-zero so the
    # workflow commits that data, skips the Pages deploy, and still fails the job.
    # Returning 0 used to publish the previous feed on a green run.
    feed_failed = False
    try:
        import production
        feed = production.build_feed(d, st)
        production.save_feed(feed)
        print(f" production: {len(feed['pairs'])} pair(s), "
              f"{sum(1 for l in feed['leads'].values() if l['status'] == 'pending')} open lead(s), "
              f"{feed['unlisted_skipped']} unpublishable and {feed['unverified_kickoff_skipped']} "
              f"unverified-kickoff bet(s) held back")
    except Exception as e:
        feed_failed = True
        # A failed rebuild leaves the OLD feed on disk, which is the dangerous failure.
        # Whatever else is wrong, it must not go on naming a pair that is no longer
        # in Production — and the run must not look successful.
        print(f"  ! production feed failed: {type(e).__name__}: {str(e)[:80]}")
        try:
            import production
            dropped = production.prune_feed(st=st)
            print(f"  ! feed left as it was, minus {dropped} lead(s) from demoted pairs")
        except Exception as e2:
            print(f"  ! and the feed could not be pruned either: {type(e2).__name__}")

    print("\n source                     quotes  bets  settled   hit      ROI   Brier")
    for name, s in score(d).items():
        if not s["connected"]:
            continue
        hit = f"{s['hit']*100:5.1f}%" if s["hit"] is not None else "    —"
        roi = f"{s['roi']*100:+6.1f}%" if s["roi"] is not None else "     —"
        br = f"{s['brier']:.4f}" if s["brier"] is not None else "     —"
        print(f" {s['label']:<26}{s['quotes']:>6}{s['bets']:>6}{s['settled']:>9}"
              f"  {hit}  {roi}  {br}")
    print(f"\n ledger: {LEDGER} ({len(d['quotes'])} quotes total)")
    if feed_failed:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
