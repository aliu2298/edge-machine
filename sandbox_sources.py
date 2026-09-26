"""Adapters for the Sandbox Tracker: every prediction source, behind one interface.

The question this file exists to answer is "which prediction source is actually worth
following?", and that question is only answerable if three things are true of every
source: it must state a PROBABILITY (not a pick), on an event that RESOLVES, at a price
that was really available. A tipster page that says "Yankees look good" cannot be scored
against anything, so it is not a source here no matter how well known the site is.

That constraint is what picked the source list. Polymarket is the spine — it is the only
feed that covers all six sports, it carries a tradeable price, and it resolves itself, so
it doubles as the settlement oracle. Everything else is a challenger measured against
that price.

Sources deliberately left UNCONNECTED are still declared in SOURCES with connected=False.
A source that is silently missing looks identical to a source with no edge, and the whole
point of the board is to tell those two apart.
"""

import difflib
import json
import math
import concurrent.futures
import functools
import html
import http.client
import re
import unicodedata
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

# The six sports the board tracks. Key is internal; label is what the page prints.
SPORTS = {
    # Sports first, then the non-sport markets. The key is used throughout as the
    # domain id; "sport" in the code means "one of these", nothing narrower.
    "soccer":       "Soccer",
    "soccer_btts":  "Soccer · BTTS",
    "soccer_o15":   "Soccer · Over 1.5",
    "soccer_o25":   "Soccer · Over 2.5",
    "soccer_team1": "Soccer · Team 1+",
    "soccer_team2": "Soccer · Team 2+",
    "soccer_u35":   "Soccer · Under 3.5",
    "soccer_p05":   "Soccer · Team +0.5",
    "tennis":       "Tennis",
    "table_tennis": "Table Tennis",
    "boxing":       "Boxing",
    "mma":          "MMA",
    "nfl":          "NFL",
    "cricket":      "Cricket",
    "mlb":          "MLB",
    "nhl_rest":     "NHL · Rest",
    "nhl_pl":       "NHL · Puck line",
    "climate":      "Climate",
    "crypto":       "Crypto",
    "economics":    "Economics",
    "commodities":  "Commodities",
    "finance":      "Finance",
    "politics":     "Politics",
    "elections":    "Elections",
}

# Corners (2026-09-19): one domain for Kalshi's total-corner and team-corner ladders. No cup or
# international twin — Kalshi lists corners only for league and Champions League matches.
SPORTS["soccer_corners"] = "Soccer · Corners"

GOALS_SPORTS_ALL = tuple(b + x for b in ("soccer_o15", "soccer_o25", "soccer_team1", "soccer_team2",
                                         "soccer_u35", "soccer_p05")
                         for x in ("", "_cup", "_intl"))

# Each soccer form market gets a Cups and an Internationals twin, listed right after it
# (see SCOPES). Labels read "Soccer · Over 1.5 · Cups" so the page files them under Soccer.
SPORTS = dict(
    [(k, v) for k, v in SPORTS.items() if not k.startswith("soccer_")] [:1]
    + [(k2, v2) for k, v in SPORTS.items() if k.startswith("soccer_") and k != "soccer_corners"
       for k2, v2 in ((k, v), (k + "_cup", v + " · Cups"), (k + "_intl", v + " · Internationals"))]
    + [("soccer_corners", SPORTS["soccer_corners"])]
    + [(k, v) for k, v in SPORTS.items() if not k.startswith("soccer_")][1:])

# Tennis combos (2026-09-21): baskets of the same legs the favourite-band rule takes, bought
# as ONE Kalshi combo contract instead of separately. Its own domain, so a basket can never
# mix into the single-leg tennis record and the two can be read side by side.
SPORTS["tennis_combo"] = "Tennis · Combos"
# The same construction on Polymarket US, which has its own combo builder. A separate domain
# so the two venues' baskets can never pool into one record: they are different contracts at
# different costs, and the whole point is to read them side by side.
SPORTS["tennis_pmcombo"] = "Tennis · PM Combos"

# Polymarket tag slugs, verified live against gamma-api on 2026-09-09: every one of the
# six returns open, tradeable markets. table-tennis is the surprise — Polymarket carries
# a deep book of Ukrainian/WTT singles matches.
PM_TAGS = {
    "soccer": "soccer", "tennis": "tennis", "table_tennis": "table-tennis", "boxing": "boxing",
    "mma": "ufc",
    "nfl": "nfl", "cricket": "cricket", "mlb": "mlb",
}

# ESPN paths, site API (scoreboard) and core API (predictor/odds).
ESPN_PATHS = {
    "nfl": ("football/nfl", "football/leagues/nfl"),
    "mlb": ("baseball/mlb", "baseball/leagues/mlb"),
}

# Kalshi series tickers, verified returning open markets on 2026-09-09.
KALSHI_SERIES = {"nfl": "KXNFLGAME", "mlb": "KXMLBGAME", "tennis": "KXATPMATCH"}

# The registry. `connected` is the honest bit: it says whether this run can actually
# reach the source, not whether the site exists.
SOURCES = {
    "polymarket_us": dict(
        label="Polymarket US", kind="Prediction market", connected=True,
        site="polymarket.us",
        sports=["tennis", "table_tennis", "boxing", "mma", "nfl", "cricket", "mlb"],
        note="The venue since 2026-09-13 — the regulated US exchange, open to US accounts. "
             "Its own midpoint is logged for the Brier column; it cannot beat its own price."),
    "polymarket": dict(
        label="Polymarket (international)", kind="Prediction market", connected=True,
        site="polymarket.com",
        # Listed explicitly. This was once "every domain except soccer", which silently
        # claimed climate, crypto and elections the moment those domains were added —
        # showing a source as covering markets it has never priced.
        sports=["table_tennis", "boxing", "nfl", "cricket", "mlb"],
        retired_sports={"tennis": "Eliminated 2026-09-21: fails in EVERY direction — backing its tennis picks lost 11.3% after fees on 15, and backing the other side lost 4.3%. It points neither way; it only pays the spread."},
        note="The venue until 2026-09-13, now a comparison source: its midpoint against the "
             "Polymarket US / Kalshi ask, backed at a 3pp disagreement like any exchange. "
             "Before the switch it was the benchmark and could not bet."),
    "kalshi": dict(
        label="Kalshi", kind="Prediction market", connected=True,
        site="kalshi.com", sports=["nfl", "tennis", "mlb"],
        note="A second regulated exchange. Where the two exchanges disagree, one of them "
             "is mispriced, and this is the lane that finds out which. MLB was retired "
             "2026-09-18 (1 won v 2.4 priced on 6 settled, z -1.23) and RE-OPENED "
             "2026-09-21 to measure its fade forward: backing the other side of its MLB "
             "picks ran +12.4% on 23 (z +0.85). Re-opened in the Sandbox only."),
    "espn_fpi": dict(
        label="ESPN FPI / Matchup Predictor", kind="Statistical model", connected=True,
        site="espn.com", sports=["nfl", "mlb"],
        note="ESPN's own win probability (gameProjection). A pure model with no money "
             "behind it, which makes it the most likely of the four to be beatable."),
    "draftkings": dict(
        label="DraftKings (via ESPN)", kind="Sportsbook", connected=True,
        site="draftkings.com", sports=["nfl"],
        retired_sports={"mlb": "Eliminated 2026-09-21: fails in EVERY direction — backing its MLB picks lost 5.6% after fees on 7, and backing the other side lost 9.4%. A de-vigged book line is, by design, the market with its margin taken out — there is nothing left to disagree with."},
        note="Closing-ish moneyline, de-vigged to a fair probability. A sportsbook line "
             "is the hardest public number to beat, so this is the ceiling."),
    "covers": dict(
        label="Covers / OddsShark computer picks", kind="Tipster site", connected=True,
        site="covers.com", sports=["nfl", "mlb"],
        note="A published computer pick per game, free and dated. It states a projected "
             "SCORE rather than a probability, so it is backed at the market price with "
             "no edge filter and gets no Brier column — a pick cannot be calibrated. MLB was "
             "retired 2026-09-18 (8 won v 9.4 priced on 16, z -0.73) and RE-OPENED 2026-09-21 "
             "to measure its fade forward (+8.0% on 24, z +0.49). Sandbox only."),
    "cricket_consensus": dict(
        label="Cricket consensus (Oddspedia and Polymarket agree)", kind="Rule", connected=True,
        site="edge-machine", sports=["cricket"],
        note="Pre-registered 2026-09-22, before it logged anything. Back a cricket match only "
             "where the two cricket sources with records — Oddspedia's community tips and "
             "Polymarket's international price — both back the same side, at the going price "
             "the moment they agree. Each source's side is its logged bet on that market, or this "
             "run's opinion read the way it would bet: Oddspedia's pick as it stands, Polymarket's "
             "price only where it clears the 3pp edge. Context, because it is thin: on the three "
             "matches both have bet so far they agreed twice and both won — but those two were "
             "the 0.07 and 0.11 longshots that make up nearly all of both records — and on the "
             "third they disagreed and Oddspedia was right. So this measures whether agreement "
             "is worth more than either source alone, from here on."),
    "oddspedia": dict(
        label="Oddspedia community tips", kind="Tipster site", connected=True,
        site="oddspedia.com", sports=["cricket"],
        note="A public tipster community — named accounts with a visible record — "
             "reduced to a majority consensus per match, because its tipsters routinely "
             "take opposite sides of the same game. The only source found that tips the "
             "niche cricket Polymarket lists. Cloudflare-protected, so it comes through "
             "the headless browser. Tips carry no date, so each is resolved to the "
             "soonest fixture between those two sides."),
    "nws": dict(
        label="National Weather Service", kind="Forecaster", connected=True,
        site="weather.gov", sports=["climate"],
        note="The public forecast for each city, against Kalshi's temperature buckets for "
             "the same city and day. The one non-sport domain with a genuinely "
             "independent forecaster — and it settles overnight, so it reaches a readable "
             "sample in a week rather than months. Retired 2026-09-15 (12 won v 13.6 priced "
             "on 31, z -0.85: the forecast looked already priced in) and RE-OPENED 2026-09-21 "
             "to measure its fade forward: backing against its buckets ran +7.3% on 51 bets, "
             "35 independent outcomes, z +1.23 — the strongest fade among the retired pairs "
             "once its buckets are counted as the single draws they are."),
    "nws_fade": dict(
        label="National Weather Service, the other side", kind="Rule", connected=True,
        site="edge-machine", sports=["climate"],
        note="PAPER TEST, registered 2026-09-25, before it logged anything. Takes the other "
             "side of each pick the NWS lane would make, on the same market, at the same flat "
             "stake the tracker uses for every source. The follow lane is paused; this one is "
             "logged under its own source so the two records never pool. If the follow lane is "
             "turned back on, both may log the same city-day, and duplicate protection will "
             "not stop either one — it is per source. READ POINT: 100 settled independent "
             "outcomes, fixed now. One city-day is one outcome, because the buckets of a "
             "single ladder cannot all happen. Do not retune the side, the stake, or this "
             "number before that many independent outcomes have settled."),
    "btts_market": dict(
        label="Kalshi BTTS price (every match)", kind="Baseline", connected=True,
        site="kalshi.com", sports=["soccer_btts", "soccer_btts_cup", "soccer_btts_intl"],
        note="The market's own midpoint on every Kalshi both-teams-to-score market the Sandbox "
             "lists. Never bets. It is the population a BTTS rule is judged against: what "
             "backing Yes on every match would have made over the same period."),
    "btts_form_l10": dict(
        label="BTTS form rule (both teams 7+ of last 10)", kind="Rule", connected=True,
        site="edge-machine", sports=["soccer_btts", "soccer_btts_cup", "soccer_btts_intl"], baseline="population",
        note="Pre-registered 2026-09-13, with no fitted number. Back Yes at the Kalshi ask on "
             "every match where BOTH teams saw both teams score in at least 7 of their last 10 "
             "competitive games (ESPN results strictly before kickoff). Found in research: "
             "+10pp over the teams' own earlier rate on 77 matches, but inside one period, not "
             "significant across the rules tried, and on 14 priced matches the market already "
             "charged for it. The Sandbox decides."),
    "tennis_fav_band": dict(
        label="Tennis favourite-band rule (priced 0.77-0.81)", kind="Rule", connected=True,
        site="edge-machine", sports=["tennis"], baseline="favourite_population",
        note="NARROWED AGAIN 2026-09-24 to 0.77-0.81, and the clock reset with it. The 0.75-0.77 slice was the whole problem: on 220 settled bets in the 0.75-0.80 band it returned -1.03% alone (74.7% hit against a 75.5c average ask), while 0.77-0.81 returned +9.83% (86.2%, z +2.36) and was the ONLY slice positive in both halves of the record (+11.8% then +7.8%); 0.75-0.77 went -8.3% then +7.0% and every band above 0.81 flipped sign. Weak part stated: that band was chosen after looking at five, and both halves are the same eleven days and largely the same tournaments, so it is a defensible narrowing rather than a proven one — hence the reset. Each quote now also carries its TOUR (S.tennis_tier), which is not a rule: the pre-registered question, fixed today and read in four weeks, is whether a favourite in a shallower field beats the same price in a deeper one. Today that is directionally right and unreadable — ITF men +4.30% on 185, WTA -3.87% on 55 — and contradicted by ATP at +23.99% on 27 bets with no losses, which is what luck looks like. EARLIER: NARROWED AND RESET 2026-09-23, counting from zero. Back the player the exchange "
             "prices between 0.75 and 0.80 (the ask), on every tennis match the Sandbox lists. "
             "It ran on 0.75-0.90 from 2026-09-14 and reached 377-69 over 446 settled, +2.63% "
             "after fees, z +1.68 — but the edge was not spread across that band. 0.75-0.80 "
             "returned +5.5% (149 won v 139.1 priced, z +1.75) on 181 bets; 0.80-0.90 returned "
             "+0.7% on the other 265, which is flat. That is the REVERSE of the "
             "favourite-longshot bias the rule was built on, which says the bias grows as the "
             "price shortens. Two things follow and both are unwelcome: the narrowing was found "
             "IN this record, so it is a fitted claim that none of those 446 bets can test, and "
             "the rule's stated mechanism did not survive its own data. So it left Production "
             "the same day and starts again at zero; the old record stays on file under "
             "Reference. The closing prices were the warning all along — -0.85c a bet over 437 "
             "closes, t -3.66, the market drifting away from its picks while the win record "
             "said otherwise. Judged against backing the favourite on every match over the same "
             "period, so it only counts if this band beats favourites in general."),
    "tennis_fav_band_3h": dict(
        label="Tennis favourite band, entered within 3 hours of the start", kind="Rule",
        connected=True, site="edge-machine", sports=["tennis"], baseline="favourite_population",
        note="PAPER TEST, registered 2026-09-25, before it logged anything. The same selection "
             "as tennis_fav_band — the player priced 0.77-0.81 — and only when the entry is "
             "within 3 hours of the scheduled start. tennis_fav_band is unchanged and keeps "
             "logging every in-band match, including ones more than 3 hours out, so the two "
             "records can be compared. A match that qualifies for both is logged by both. "
             "That overlap is the comparison: duplicate protection is per source, so one "
             "lane's quote cannot block or void the other. Why the window: closing-line "
             "value on the band was about -1.2c on entries 3 or more hours before the start, "
             "and about -0.3c on entries inside 3 hours (in-band n=90, +11.8% after fees)."),
    "tennis_combo2": dict(
        label="Tennis 2-leg combo (favourite-band legs)", kind="Rule", connected=True,
        site="edge-machine", sports=["tennis_combo"], baseline="favourite_population",
        note="NARROWED AND RESET AGAIN 2026-09-24 with the single-leg rule it wraps: its legs "
             "are now priced 0.77-0.81 (0.75-0.80 from 2026-09-23, 0.75-0.90 before), so a basket struck before that date counts "
             "toward nothing here and stays on file under Reference — a basket of narrow legs "
             "is a different contract. Cut each day's "
             "favourite-band legs, in start-time order, into consecutive baskets of 2 and buy "
             "each basket as ONE combo contract, which "
             "pays only if all 2 win. A combo multiplies a rule's edge rather "
             "than averaging it: at m = 1.042 over 238 settled single-leg bets, 2 legs would "
             "run at 8.5% over the price it pays — and at about the same multiple BELOW it if "
             "that edge is really zero, which is why this is in the Sandbox and not in "
             "Production. Kalshi's RFQ was measured first: on 20 real baskets it quoted a "
             "median 0.84% over the product of the legs, far inside the 8.5% the edge could "
             "absorb. The price here is that product plus the measured markup, not a live "
             "quote. " + 'Judged against the SAME legs bet singly — the only question a combo asks is whether bundling beats betting them one at a time, and that comparison is the single-leg tennis record sitting beside it. Each leg sits in one basket of each size and baskets share no match, so each is an independent result, judged per basket like the single-leg rule. Changed 2026-09-21 after two baskets: it first built ONE basket a day from the first legs and left ~55 of ~60 eligible legs unused, so it could not be read for a month.'),
    "tennis_combo3": dict(
        label="Tennis 3-leg combo (favourite-band legs)", kind="Rule", connected=True,
        site="edge-machine", sports=["tennis_combo"], baseline="favourite_population",
        note="NARROWED AND RESET AGAIN 2026-09-24 with the single-leg rule it wraps: its legs "
             "are now priced 0.77-0.81 (0.75-0.80 from 2026-09-23, 0.75-0.90 before), so a basket struck before that date counts "
             "toward nothing here and stays on file under Reference — a basket of narrow legs "
             "is a different contract. Cut each day's "
             "favourite-band legs, in start-time order, into consecutive baskets of 3 and buy "
             "each basket as ONE combo contract, which "
             "pays only if all 3 win. A combo multiplies a rule's edge rather "
             "than averaging it: at m = 1.042 over 238 settled single-leg bets, 3 legs would "
             "run at 13.1% over the price it pays — and at about the same multiple BELOW it if "
             "that edge is really zero, which is why this is in the Sandbox and not in "
             "Production. Kalshi's RFQ was measured first: on 20 real baskets it quoted a "
             "median 1.06% over the product of the legs, far inside the 13.1% the edge could "
             "absorb. The price here is that product plus the measured markup, not a live "
             "quote. " + 'Judged against the SAME legs bet singly — the only question a combo asks is whether bundling beats betting them one at a time, and that comparison is the single-leg tennis record sitting beside it. Each leg sits in one basket of each size and baskets share no match, so each is an independent result, judged per basket like the single-leg rule. Changed 2026-09-21 after two baskets: it first built ONE basket a day from the first legs and left ~55 of ~60 eligible legs unused, so it could not be read for a month.'),
    "tennis_combo4": dict(
        label="Tennis 4-leg combo (favourite-band legs)", kind="Rule", connected=True,
        site="edge-machine", sports=["tennis_combo"], baseline="favourite_population",
        note="NARROWED AND RESET AGAIN 2026-09-24 with the single-leg rule it wraps: its legs "
             "are now priced 0.77-0.81 (0.75-0.80 from 2026-09-23, 0.75-0.90 before), so a basket struck before that date counts toward "
             "nothing here and stays on file under Reference. The same construction as the "
             "2- and 3-leg rules at four legs: each day's favourite-band legs, in start-time order, "
             "cut into consecutive baskets of four, each bought as ONE combo contract that pays "
             "only if all four win. At m = 1.042 a leg, four legs would run at about 1.18 over the "
             "price — and about as far below it if that edge is really zero. Kalshi's RFQ was "
             "measured first: 12 real baskets, 12-18 market makers each, a median 0.66% over the "
             "product of the legs. The price logged is that product plus the measured markup. "
             "Each leg sits in one 4-leg basket and baskets share no match, so each is an "
             "independent result, judged per basket."),
    "pm_combo2": dict(
        label="Tennis 2-leg combo on Polymarket US", kind="Rule", connected=True,
        site="edge-machine", sports=["tennis_pmcombo"], baseline="favourite_population",
        note="PRE-REGISTERED 2026-09-24. The same basket the Kalshi combo rules build, cut "
             "from Polymarket US legs instead. Built because that is where the legs are: after "
             "the 2026-09-23 band narrowing the tennis rule picked 15 of 15 on Polymarket US, "
             "and the Kalshi basket lane went to zero for want of in-band Kalshi legs. In the "
             "0.75-0.80 band it was measured in (the legs follow the single-leg rule and moved to "
             "0.77-0.81 on 2026-09-24, so re-measure) Polymarket US supplied 14.6 in-band "
             "legs a day against Kalshi's "
             "6.3, and returned +6.86% gross a leg (n=146) against Kalshi's +5.45% (n=58). "
             "NEITHER of those leg edges is significant (t +1.66 and +0.81), and a basket "
             "multiplies the error as surely as the edge: if the true edge is zero this does "
             "not return zero, it loses the wrapper and the fee every time. That is what this "
             "lane is for and why it starts here and not in Production. The price is the "
             "product of the legs plus PM_COMBO_MARKUP -- a MODEL, and a thin one: the 2-leg "
             "markup comes from a single pre-match quote read live on 2026-09-24 (2.69% over "
             "the product), against the 20 baskets behind Kalshi's. Re-measure it."),
    "pm_combo3": dict(
        label="Tennis 3-leg combo on Polymarket US", kind="Rule", connected=True,
        site="edge-machine", sports=["tennis_pmcombo"], baseline="favourite_population",
        note="PRE-REGISTERED 2026-09-24. Three legs of the same construction -- each day's "
             "in-band Polymarket US legs in start-time order, cut into consecutive baskets of "
             "three, each bought as ONE combo contract paying only if all three win. Its "
             "3-leg markup is NOT measured: it is extrapolated from the single 2-leg reading "
             "on the shape Kalshi's own constants showed from two legs to three, so the price "
             "is the weakest part of this lane and the first thing to firm up. Judged against "
             "the same legs bet singly, which is the only question a basket asks."),
    "pm_combo4": dict(
        label="Tennis 4-leg combo on Polymarket US", kind="Rule", connected=True,
        site="edge-machine", sports=["tennis_pmcombo"], baseline="favourite_population",
        note="PRE-REGISTERED 2026-09-24. Four legs, same construction, same extrapolated and "
             "unmeasured markup as the 3-leg rule. Four legs compound both the edge and the "
             "error hardest, so this is the rung that answers soonest whether the leg edge is "
             "real -- in either direction."),
    "tt_band_55_60": dict(
        label="Table tennis 0.55-0.60 band (confirmation test)", kind="Rule", connected=False, retired='2026-09-15: the confirmation test answered — on new matches 36 won v 36.3 priced (64 settled, z -0.08, -1.1%). The early spike was noise.',
        site="edge-machine", sports=["table_tennis"], baseline="favourite_population",
        note="Pre-registered 2026-09-14 as a CONFIRMATION test, not a finding. In the first 129 "
             "settled table tennis matches (Sep 13-14, nearly all Setka Cup) players priced "
             "0.55-0.60 won 78.8% against 57.2% priced (+34.5%, z +2.51 on 33) while the bands "
             "either side lost 15-25% — one spike among 11 bands, which chance produces about "
             "that often. Backed on every new match from here to see whether it holds; if it "
             "is noise it will sit at the price. Judged against backing every favourite."),
    "mma_fav_band": dict(
        label="MMA favourite-band rule (priced 0.75-0.90)", kind="Rule", connected=True,
        site="edge-machine", sports=["mma"], baseline="favourite_population",
        note="Pre-registered 2026-09-14: the tennis favourite-band rule applied unchanged to "
             "MMA — back the fighter the exchange prices between 0.75 and 0.90. Not fitted on "
             "MMA at all: the Sandbox had no settled, priced MMA fight when it was added, so "
             "this is a clean test of whether the favourite-longshot bias carries across sports. "
             "Judged against backing the favourite in every fight over the same period. MMA "
             "lists only a handful of fights a week, so it will take months to read."),
    "mlb_fade_streak": dict(
        label="MLB fade-the-streak rule (cold team v hot team, last 10)", kind="Rule",
        connected=True, site="edge-machine", sports=["mlb"],
        note="Pre-registered 2026-09-14. Back the team that won 3 or fewer of its last 10 games "
             "when it plays a team that won 7 or more of its last 10 (regular season, each with "
             "20+ games played, MLB Stats API results strictly before first pitch). Research on "
             "every 2025 and 2026 game at Kalshi's last price before first pitch: the hot team was "
             "priced ~57% and won 51-56%, so backing the cold team made +3.0% on 239 games in "
             "2025 and +4.6% on 149 in 2026 — found in one season, repeated in the next, but "
             "small (z +0.1 and +1.1). Judged against backing the favourite and the underdog on "
             "the same games. Retired 2026-09-18 (2 won v 2.8 priced on 7, z -0.64) and RE-OPENED "
             "2026-09-21 to measure its fade forward (+25.3% on 8, z +0.96). Note what that fade "
             "is: this rule already fades the hot team, so fading IT backs the hot team — which "
             "is close to backing the favourite, a blind rule it is judged against anyway."),
    "goals_market": dict(
        label="Kalshi goals price (every match)", kind="Baseline", connected=True,
        site="kalshi.com", sports=list(GOALS_SPORTS_ALL),
        note="The market's own midpoint on every Kalshi over-1.5 and team-total market the "
             "Sandbox lists. Never bets. The population each goals rule is judged against: "
             "backing Yes on every listed match of that market over the same period."),
    "o15_form_l10": dict(
        label="Over 1.5 form rule (both teams 9+ of last 10)", kind="Rule", connected=True,
        site="edge-machine", sports=["soccer_o15", "soccer_o15_cup", "soccer_o15_intl"], baseline="population",
        note="Pre-registered 2026-09-14 from research fixed before it ran. Back over 1.5 at the "
             "Kalshi ask where BOTH teams' games went over 1.5 in at least 9 of their last 10 "
             "competitive games (10+ games each, ESPN results strictly before kickoff). "
             "Research: 92.9% on 84 matches against the teams' own earlier 81.4%. At real "
             "Kalshi prices in its first week, +2.0% on 20 — the market charges for most of it. "
             "The same rule selects the Leads board's over-1.5 cards since 2026-09-14."),
    "team2_ranked": dict(
        label="Favourite to score 2+, ranked by margin (top 2, 5pp+)", kind="Rule", connected=True,
        site="edge-machine", sports=["soccer_team2", "soccer_team2_cup", "soccer_team2_intl"],
        baseline="population",
        note="PRE-REGISTERED 2026-09-24, before it logged anything. This market has the widest "
             "rankable spread measured here: on 11,152 priced matches the favourite scores "
             "twice 40.3% of the time at a 0.30-0.40 win price and 80.0% at 0.80+, rising "
             "monotonically (+35.4pp end to end, z +20.1, against +12.7pp for over 1.5). AND "
             "RANKING ON THAT WOULD STILL LOSE, which is why it does not. Joining 92 real "
             "Kalshi asks to their own fixture's winner book: a 0.75+ favourite is asked 0.766 "
             "against a true 0.780, a 0.65-0.75 one is asked 0.709 against 0.653, and the mean "
             "margin across all 92 is -3.53pp — the vig, almost exactly. Taking the day's two "
             "biggest mismatches buys at a loss on average however well mismatch predicts. So "
             "it ranks on MARGIN: what the fixture's own winner price says the market is "
             "worth (TEAM2_RATE_BY_FAV, a coarse empirical lookup, not a goals forecast of "
             "ours — the market supplies the probability and only the mapping is ours) minus "
             "what it costs. The top of the board by margin is not the top by mismatch: the "
             "best of those 92 was Malta at a 0.41 favourite priced 0.30 (+16.3pp), which a "
             "mismatch ranker would never have looked at. It fires RARELY on purpose — 15.2% "
             "of the 92 cleared 5pp and 6.5% cleared 8pp, about 1.3 and 0.5 a day — because a "
             "rule firing twice a day here would be buying the -3.53pp average. The low-block "
             "exclusion carries over and fits tighter than it did for over 1.5: a favourite "
             "needs its opponent to concede TWICE. Judged against backing Yes on every listed "
             "score-2+ market."),
    "o15_ranked": dict(
        label="Over 1.5, ranked: the day's top 2 mismatches under 0.80", kind="Rule", connected=True,
        site="edge-machine", sports=["soccer_o15", "soccer_o15_cup", "soccer_o15_intl"],
        baseline="population",
        note="PRE-REGISTERED 2026-09-24, before it logged anything. Every other over-1.5 rule "
             "here is a THRESHOLD -- it takes every match clearing a bar and lands on their "
             "average, which on five seasons is 81.4% against an ask that has averaged 0.850 "
             "and demands 85%. That loses by construction, and o15_form_l10's live -10.4% on "
             "25 bets is what it looks like. This one RANKS: on 401 matchdays with a 20+ "
             "candidate pool (median 45 games), the whole field hit 77.0%, the top 10 80.8%, "
             "the top 2 82.7%, the top 1 84.5% -- ranking is worth ~7.5pp over taking the "
             "board. It ranks on MISMATCH, not on a good fixture: over 1.5 runs 73.7% where "
             "the favourite is 0.30-0.40 and 87.5% where it is 0.80+, monotonically, and "
             "matches with every price above 2.00 go over 4.67pp LESS often than ones with a "
             "clear favourite (z -5.79). The marquee tie is the worst candidate on the board. "
             "The signal is ALREADY PRICED -- against the market's own de-vigged fair the "
             "mismatch buckets sit at +0.81, -0.05, +1.13, +1.08 and -0.58pp, none at z 1.1 "
             "-- so the rule can only earn by paying less than a ranked candidate is worth, "
             "which is what the 0.80 ceiling is for. Backtested at 0.80 the top 2 return "
             "+3.3% and the top 1 +5.7%, against -2.7% and -0.5% at 0.85. Stated plainly: "
             "that backtest ranks on the same five seasons everything else here was fitted "
             "on, so it is a reason to run the rule, not a result. Judged against backing Yes "
             "on every listed over-1.5 market, which is the only question it asks."),
    "o15_cup_mismatch": dict(
        label="Cup mismatch over 1.5 rule (favourite 0.70+ to win)", kind="Rule", connected=True,
        site="edge-machine", sports=["soccer_o15_cup"], baseline="population",
        note="Pre-registered 2026-09-21, before it logged anything. Back over 1.5 at the Kalshi "
             "ask in any cup tie the Sandbox lists where one side's own price to win outright is "
             "0.70 or more at the midpoint, read from the same tie's match-winner markets in the "
             "same run. The claim: a mismatch produces goals, and the market prices a cup tie's "
             "goals too much like a league match's. Where it came from matters, so it is stated: "
             "23 Taça de Portugal over-1.5 markets in one week went over 20 times against 18.1 "
             "priced (z +0.98), and that competition was the only place a cheap-over pattern "
             "survived — found by slicing a sample, which proves nothing. So it applies to every "
             "cup, not only Portugal's, with no cap on the over price. Judged against backing "
             "over 1.5 on every cup tie, so it only counts if the mismatch tells the market "
             "something its over price does not already hold."),
    "team1_form_l5": dict(
        label="Team scores 1+ form rule (5/5 scored, opponent 5/5 conceded)", kind="Rule",
        connected=True, site="edge-machine", sports=["soccer_team1", "soccer_team1_cup", "soccer_team1_intl"], baseline="population",
        note="Pre-registered 2026-09-14. Back a side to score at the Kalshi ask where it "
             "scored in each of its last 5 competitive games and its opponent conceded in each "
             "of theirs (10+ games each). Research: 91.9% on 99 team-games against 77.9% own "
             "earlier rate; 10 of 10 at real Kalshi prices (avg 0.84) in its first week. "
             "In Production since 2026-09-18, moved by hand."),
    "p05_unbeaten": dict(
        label="Team +0.5 unbeaten rule (unbeaten 8+/10, opponent won ≤3/10)", kind="Rule",
        connected=True, site="edge-machine", sports=["soccer_p05", "soccer_p05_cup", "soccer_p05_intl"], baseline="population",
        note="Pre-registered 2026-09-14. Back a team not to lose (+0.5: No on Kalshi's market for "
             "its opponent to win) where the team is unbeaten in 8+ of its last 10 games in this "
             "competition and the opponent won 3 or fewer of its last 10 there (HOF's windows, "
             "10+ games each, ESPN results before kickoff). Research: 82.5% on 97 against the "
             "teams' own earlier 70.6% (z +2.56); none of 1,000 shuffled worlds produced a spread "
             "rule this strong across the six tried; at Kalshi's price just before kickoff 54 of "
             "64 won at ~77% (+11.2% after fees). 37 of those 64 were MLS. Judged against backing "
             "No on every Kalshi win market over the same period."),
    "cmd_market": dict(
        label="Kalshi commodity price (every listed strike)", kind="Baseline", connected=True,
        site="kalshi.com", sports=["commodities"],
        note="The midpoint on every daily oil, metal, gas and gasoline strike this board "
             "lists, logged 6+ hours before it closes. Never a bet — it is the population "
             "the tail rule is measured against, and the answer to 'is this market simply "
             "efficient?' It was: backing whichever side the market favoured won 87.7% "
             "against an 87.5% price over 61 days."),
    "cmd_tail": dict(
        label="Commodity far-tail rule (priced 0.97-0.995)", kind="Rule", connected=False,
        retired="2026-09-21: replaced by the AAA gasoline no-change rule. It was ahead of the "
                "price (+1.9% after fees) but by design backed the near-certain side of every "
                "strike on every ladder: 200-360 bets a day, 442 across 3 market-days, each "
                "risking about 98c to make 2c. Chasing pennies at that volume is not a strategy "
                "worth reading, however long it runs.",
        site="edge-machine", sports=["commodities"], baseline="population",
        note="Pre-registered 2026-09-18. Back the near-certain side of a daily commodity "
             "strike — WTI, Brent, gold, silver, copper, natural gas or AAA retail gasoline — "
             "where it is priced 0.97-0.995 with a two-sided book. Research over 61 days: "
             "99.3% on 778 bets against a 98.3% price, +1.0% after fees; clustered by day and "
             "resampled, +0.3% to +1.5% with no losing world; steady in both halves and at "
             "every band from 0.95 up. The 0.90-0.97 band returned -1.3%, so this is the tail "
             "specifically, not 'back favourites'. It is SELLING TAIL RISK for a penny: five "
             "of 778 bets lost and each cost about sixty wins, in two months that held no "
             "commodity shock. Logged and measured in the Sandbox only."),
    "gas_nochange": dict(
        label="AAA gasoline no-change rule (one bet a day)", kind="Rule", connected=True,
        site="edge-machine", sports=["commodities"], baseline="population", one_per_day=True,
        note="Pre-registered 2026-09-21, before it logged anything. On Kalshi's national AAA "
             "gasoline ladder, project today's figure at yesterday's — no change — and back the "
             "one strike that projection beats by 5c after fees, at an ask of 0.25-0.80, in the "
             "last hours before the ladder closes. At most one bet a day. How it was found is "
             "stated because it decides how far to trust it: AAA gas trends (same direction as "
             "the day before on 78% of 68 days), so a rule betting the trend CONTINUES was "
             "pre-registered first, and it failed — -18.0% following on 39 bets, +2.4% fading: "
             "the market already prices the trend. This variant, projecting no change, ran "
             "+15.0% following and -21.3% fading on 34 (z +1.00), which would mean the market "
             "over-extrapolates the trend. It was found by trying a second version, so that is "
             "in-sample and proves nothing; the forward record decides whether to follow it, "
             "fade it, or neither. Replaces the far-tail rule."),
    "nhl_rest_edge": dict(
        label="NHL rest rule (rested home team v a visitor on a back-to-back)", kind="Rule",
        connected=True, site="edge-machine", sports=["nhl_rest"], baseline="favourite_population",
        note="Pre-registered 2026-09-17, before a game of the 2026-27 season was played, so the "
             "season is a clean out-of-sample test. Back the home team where it has had a day off "
             "or more and the visitor played the night before (the NHL's own schedule; no form is "
             "read). Research over 560 games of 2025-26, priced at Kalshi's last hourly candle "
             "before puck drop: 64.9% on 74 against a 58.3% price, +7.5% after fees, and steady "
             "across the season (+11.1%, -8.5%, +18.7% by period). 74 bets is a hint, not a "
             "result. The moneyline was efficiently priced every other way tried — favourites "
             "-5.2%, underdogs -3.3%, home -4.6%, the 0.60-0.75 band -10.1% — and backing teams "
             "on a 7+/10 win rate returned +0.4%, so this is the one angle that survived. Judged "
             "against backing the favourite on every listed game."),
    "nhl_dog_pl": dict(
        label="NHL underdog +1.5 (observation, not a candidate)", kind="Rule",
        connected=True, site="edge-machine", sports=["nhl_pl"], baseline="population",
        note="Logged 2026-09-17 to settle one question, not because it is expected to pay. Backing "
             "the underdog +1.5 (No on the favourite winning by over 1.5) returned +15.7% across "
             "October and November 2025, when Kalshi's NHL spread market was weeks old, and then "
             "-3.7% in December and January and -6.8% from February as it converged: priced 37.6%, "
             "happened 38.9%. Either that softness comes back when the market relists each "
             "October, in which case it is a seasonal edge worth having, or it does not and the "
             "question is closed. Every listed game is backed, so nothing here is selected."),
    "o25_congestion": dict(
        label="Congestion under 2.5 rule (one side's 2nd game in 4 days)", kind="Rule",
        connected=True, site="edge-machine", sports=["soccer_o25", "soccer_o25_cup", "soccer_o25_intl"],
        baseline="population",
        note="Pre-registered 2026-09-22, before it logged anything, with both thresholds taken "
             "from the study rather than chosen here. Back under 2.5 (No on Kalshi's Over 2.5) "
             "where one side is playing its second competitive match within four days and the "
             "other has had six days or more, read from ESPN kickoffs strictly before this one. "
             "The claim, from Stüttgen (Journal of Sports Economics, 2025) over five Bundesliga "
             "seasons: a congested side attacks less, and defends better at home — the "
             "defensive half replicated in Spain and England, the offensive half did not. Both "
             "point the same way on a total. Backtested AFTER registering, on five seasons of "
             "results (data/espn_seasons.json, scores only — no prices exist for these): on "
             "1,718 qualifying matches it went over 2.5 55.5% of the time against 57.3% from a "
             "goal model built on the clubs\u2019 own scoring and calibrated to be right on "
             "average — \u22121.9pp, z \u22121.63. The right direction, not significant, and "
             "fragile: neighbouring thresholds run from \u22123.6pp to +0.6pp, and the paper\u2019s "
             "per-side mechanism does not cleanly replicate once home advantage is allowed for. "
             "So this is a weak prior forward-tested, not a finding. Fixture calendars are public, "
             "so the price may hold it already. Judged against backing the under on every listed "
             "over-2.5 market, so it only counts if the rest gap tells the market something its "
             "own price does not."),
    "u35_low_scoring": dict(
        label="Under 3.5 low-scoring rule (both teams scored ≤1 in 7+/10)", kind="Rule",
        connected=True, site="edge-machine", sports=["soccer_u35", "soccer_u35_cup", "soccer_u35_intl"], baseline="population",
        note="Pre-registered 2026-09-14. Back under 3.5 goals (No on Kalshi's Over 3.5) where BOTH "
             "teams scored 1 or fewer in at least 7 of their last 10 games in this competition "
             "(HOF's way of counting form; 10+ games each, ESPN results before kickoff). Research: "
             "80.5% on 41 matches against the teams' own earlier 61.7% (z +2.48); at Kalshi's under "
             "price just before kickoff 23 of 27 won at ~71% (+20.2% after fees). The same form "
             "counted across all competitions gave the same answer. Not significant across the 10 "
             "rules tried (13% of shuffled worlds), and all since mid-August — the Sandbox decides. "
             "Judged against backing the under on every Kalshi match."),
    "liga_btts_even": dict(
        label="La Liga BTTS in balanced matches (favourite 1.60-2.00)", kind="Rule",
        connected=True, site="edge-machine", sports=["soccer_btts"], baseline="population",
        note="Pre-registered 2026-09-26, before it logged anything. Back BOTH TEAMS TO SCORE "
             "on a Kalshi La Liga match when that fixture's own three-way board prices the "
             "favourite at a de-vigged 0.470-0.590 — the span of bookmaker decimal 1.60-2.00 "
             "— with the ask at 0.54 or less and the board holding no more than 6%. Research "
             "on 4,940 La Liga matches, 2013/14-2025/26: both teams scored 55.3% against "
             "49.3% implied, league part +4.7pp at z +3.52 on 1,387 matches, train +3.4pp "
             "(z +1.97) and HELD OUT +6.7pp (z +3.15) — larger on the half it never saw. The "
             "favourite's own scoring in the same band is flat at +1.4pp, so the whole effect "
             "is the UNDERDOG getting on the scoresheet, and it shows identically on 'dog to "
             "score 1+' (+4.8pp, z +3.60) which is the same finding seen twice. Note La Liga "
             "is the UNDER league overall (2.64 goals v 2.73 across twelve, every goal line "
             "below its price), so this is a pocket that runs against its own league. WEAK "
             "PART: it does not clear the grid's own bar. Adding team-to-score and BTTS took "
             "the scan to 1,424 cells and a permutation over all 52,999 matches puts "
             "family-wise 5% at |z| >= 4.16; this is 3.52, and the largest cell anywhere is "
             "4.30 in Turkey. Break-even ask is 0.543 at the measured rate, so the 0.54 "
             "ceiling will bite often. ~2.8 bets a matchweek. Judged against backing BTTS on "
             "every match of this market."),
    "liga_u15_dog": dict(
        label="La Liga under 1.5 in heavy mismatches (underdog 7.00+)", kind="Rule",
        connected=True, site="edge-machine", sports=["soccer_o15"], baseline="population",
        note="Pre-registered 2026-09-26, before it logged anything, and the mirror of "
             "liga_btts_even. Back UNDER 1.5 GOALS — the No side of Kalshi's over-1.5 — on a "
             "La Liga match whose own three-way board prices the underdog under a de-vigged "
             "0.135 (bookmaker decimal 7.00+), with the No ask at 0.20 or less and the board "
             "holding no more than 6%. Research on 4,940 matches, 2013/14-2025/26: over 1.5 "
             "landed 79.3% against 82.3% implied, league part -4.2pp at z -3.46 on 967 "
             "matches, train -2.8pp (z -1.90) and HELD OUT -7.4pp (z -3.24). Spain's big "
             "clubs shut minnows out more thoroughly than the price says, and the same band "
             "reads -3.9pp on over 2.5 and -3.4pp on the underdog scoring at all. This is the "
             "OPPOSITE of what the same band does in Turkey (+10.3pp on BTTS) and in "
             "Bundesliga, which is why it is a La Liga lane and not a mismatch lane. WEAK "
             "PARTS: it does not clear the grid's family-wise bar of |z| >= 4.16 (this is "
             "3.46); and the shape of the bet is unlike anything else here — a 20.7% strike "
             "at about five to one, so long losing runs are normal and at ~2 bets a matchweek "
             "the 30-bet floor is roughly fifteen weeks out. Break-even on the No side is "
             "0.204 at the measured rate. Judged against backing the under on every match of "
             "this market."),
    "bund_o35": dict(
        label="Bundesliga over 3.5, every match", kind="Rule", connected=True,
        site="edge-machine", sports=["soccer_u35"], baseline="population",
        note="Pre-registered 2026-09-26, before it logged anything. Back OVER 3.5 GOALS on "
             "every Kalshi Bundesliga match, skipping only a board holding more than 6%. "
             "NOTHING is selected — no band, no form, no model — which is the whole point: "
             "this is the only finding in a 540-cell study that survives its own correction, "
             "and it survives because no cell was picked. Bundesliga 2022/23-2025/26, all "
             "1,224 matches: the league beat its own price on over 3.5 by +3.71pp while the "
             "other eleven leagues ran -0.67pp, a difference of +4.39pp at z +3.01. Counted "
             "as six implicit tests (three goal lines x two eras) that needs 2.64, and it "
             "clears. The same test on 2013/14-2017/18 gives -0.11pp, z -0.09 — so this has a "
             "date, not a story. Mechanism is market lag on a regime shift: Bundesliga goals "
             "went 2.88 to 3.13 to 3.19 across the three eras while the price's implied total "
             "went 2.91 to 3.10 and then stopped, and the other eleven leagues' gap never "
             "left +-1pp. WHY EVERYTHING ELSE WAS REJECTED: a permutation test reshuffling "
             "league labels 300 times over all 52,335 matches showed this grid makes a "
             "maximum |z| of 3.30 half the time from pure noise and needs 4.09 for "
             "family-wise 5%; the largest cell in the real data was 3.44, permutation "
             "p = 0.363. No absolute price ceiling, deliberately — the claim is relative "
             "(+4.4pp over whatever the market says for that match), and a ceiling at the "
             "long-run 37.5% base rate would reject every board Kalshi has quoted. Expect ~9 "
             "bets a matchweek. If the regime reverts, this lane loses and the Sandbox says "
             "so. Judged against backing the over on every match of this market."),
    "bund_o35_draw": dict(
        label="Bundesliga over 3.5, draw priced 3.60-4.00", kind="Rule", connected=True,
        site="edge-machine", sports=["soccer_u35"], baseline="population",
        note="Pre-registered 2026-09-26, as the companion to bund_o35 and judged against it. "
             "Identical bet — over 3.5 on a Kalshi Bundesliga match, 6% hold cap — but only "
             "where that fixture's own three-way board prices the draw at a de-vigged "
             "0.235-0.267, the translation of bookmaker decimal 3.60-4.00. That is where the "
             "league's over-3.5 excess concentrates: +4.0pp over 13 seasons at z +2.82 on "
             "1,188 matches against +1.7pp for the league as a whole. It is NOT proven and "
             "the shape says so — train 13/14-20/21 gives +0.4pp (z +0.24) and the held-out "
             "half +8.7pp (z +3.99), which is a trend appearing mid-sample rather than an "
             "effect present throughout, and it could as easily be drift about to revert. It "
             "also fails the study's own bar: the permutation threshold for a scanned cell in "
             "this grid is |z| >= 4.09 and this is 2.82. bund_o35 keeps logging every match "
             "including these, so a fixture in the band is logged by BOTH lanes and the "
             "overlap is the comparison. If the band adds nothing over the plain league, the "
             "two records converge and this lane is deleted. ~2.7 bets a matchweek."),
    "ere_o15": dict(
        label="Eredivisie over 1.5, underdog priced 3.21-4.00", kind="Rule", connected=True,
        site="edge-machine", sports=["soccer_o15"], baseline="population",
        note="Pre-registered 2026-09-26, before it logged anything. Back OVER 1.5 GOALS on a "
             "Kalshi Eredivisie match when that fixture's own three-way board prices the "
             "underdog at a de-vigged 0.234-0.296 — the translation of bookmaker decimal odds "
             "3.21-4.00, a clear but not overwhelming favourite — and the over-1.5 ask is 0.81 "
             "or less. Nothing else selects it. Research on 3,904 Eredivisie matches with "
             "closing prices (2013/14-2025/26), measured against the over-1.5 probability "
             "implied by each match's own closing over-2.5 price and with the other eleven "
             "leagues' excess in the same band subtracted: all 13 seasons 82.4% against 78.4% "
             "implied, league part +4.0pp, z +3.13; train 13/14-20/21 +3.0pp (z +1.87); HELD "
             "OUT 21/22-25/26 +5.7pp (z +2.73), larger on the half the band never saw. "
             "Positive in all three disjoint eras and in ten of thirteen seasons. THE CASE "
             "AGAINST, stated now rather than later: it is a SPIKE and not a gradient — "
             "disjoint underdog bands read +0.7pp, +4.3pp, -0.1pp, -0.3pp, +1.3pp, and the "
             "correlation between any 1X2 price and the over-1.5 residual is 0.00 both here "
             "and in the other eleven leagues, so there is no mechanism behind it. 60 league x "
             "band cells were scanned and this ranks FIRST at z +3.27 against an expected max "
             "of ~2.86 under noise, while the same field throws off La Liga dog 7.00+ at "
             "z -3.44, a larger deviation nobody has a story for. Expect ~2 bets a matchweek "
             "and a 0.81 ceiling that BINDS often, since Kalshi quotes Eredivisie over-1.5 at "
             "0.84-0.93 on the mismatches it lists most. Judged against backing over 1.5 on "
             "every match of this market over the same period, so it only counts if THIS band "
             "beats overs in general."),
    "ere_draw": dict(
        label="Eredivisie draw band (de-vigged 0.20-0.25)", kind="Rule", connected=True,
        site="edge-machine", sports=["soccer"], baseline="draw_population",
        note="Pre-registered 2026-09-26, before it logged anything, with every number fixed "
             "in advance. Back the TIE on a Kalshi Eredivisie match when the board's own "
             "de-vigged draw probability — price_draw / (price_a + price_draw + price_b) — "
             "sits in 0.20-0.25 and the ask is 0.26 or less. Nothing else selects the match: "
             "no form, no model, no ranker. Research on 3,904 Eredivisie matches with closing "
             "prices (2013/14-2025/26): the band was chosen on the 2013/14-2020/21 half alone, "
             "the best of seven scanned there at +3.5pp over the price, then applied untouched "
             "to the 429 band matches of 2021/22-2025/26 — 28.0% drew against 22.8% priced, "
             "+5.2pp, z +2.39 — and it strengthens again on closing prices only (+5.9pp, "
             "z +3.19). The same band pooled over twelve leagues is EXACTLY fair (z -0.14, "
             "ROI +0.00%), so this is a Dutch-league claim and widening it needs that test "
             "re-run. Eredivisie over 1.5 inside the 3.21-4.00 underdog band is a SEPARATE "
             "and larger finding (+5.7pp held out, z +2.64) and is not part of this rule. "
             "Expect ~2-3 bets a matchweek, a 27-28% strike at ~0.23, twelve-bet "
             "losing runs, and 30 settled bets no sooner than mid-December. Weak parts stated "
             "now: the held-out ROI bootstrap is [-1.2%, +33.9%] and its lower bound touches "
             "zero; 1,114 band matches are thirteen seasons, not 1,114 independent draws, and "
             "four of those thirteen lost money; and Kalshi's Eredivisie book is thin, so if "
             "the ask sits above 0.26 the rule correctly stops firing and there is no lane. "
             "Judged against backing the draw on every three-way match the Sandbox lists over "
             "the same period, so it only counts if THIS band beats draws in general."),
    "team2_form_l10": dict(
        label="Team scores 2+ form rule (7+/10 scored 2+, opponent 7+/10 conceded 2+)",
        kind="Rule", connected=True, site="edge-machine", sports=["soccer_team2", "soccer_team2_cup", "soccer_team2_intl"],
        baseline="population",
        note="Pre-registered 2026-09-14. Back a side to score 2+ at the Kalshi ask where it "
             "scored 2+ in at least 7 of its last 10 competitive games and its opponent "
             "conceded 2+ in at least 7 of theirs. Research: 76.2% on only 21 team-games "
             "against a 45.3% own earlier rate. Measured in the Sandbox; not in Production."),
    "corners_market": dict(
        label="Kalshi corners price (every match)", kind="Baseline", connected=True,
        site="kalshi.com", sports=["soccer_corners"],
        note="The market's own midpoint on every Kalshi total-corner and team-corner rung the Sandbox "
             "lists. Never bets. The population the corners rule is judged against: backing No on "
             "every listed rung over the same period."),
    "corners_under": dict(
        label="Corners under form rule (model beats the No ask by 5c)", kind="Rule", connected=True,
        site="edge-machine", sports=["soccer_corners"], baseline="population",
        note="Pre-registered 2026-09-19. Buy No on a Kalshi total-corner or team-corner rung (\"N+ "
             "corners\") when the form model's chance of UNDER beats the No ask by 5c or more after "
             "fees, within 4 hours of kickoff. Model: each side's corners = the average of its corners "
             "won over its last 10 and its opponent's corners conceded over their last 10 (5+ games "
             "each, ESPN results before kickoff), negative binomial (dispersion 1.28 match, 1.74 "
             "team). Research, 105 Premier League / La Liga / Champions League matches Aug 15 - Sep "
             "19 2026 at the last price before kickoff: backing Over lost at every line (-12.3% per "
             "match); this rule +9.7% on 60 matches (t 0.78), +29.6% at a 10c edge (29 matches, "
             "t 1.62). A lead, not proof. Judged PER MATCH: every rung it buys in one match is one "
             "result."),
    "spot": dict(
        label="Spot price (no-change baseline)", kind="Baseline", connected=True,
        site="coingecko.com", sports=["crypto"],
        note="Today's price carried forward, backing whichever bucket it already sits in. "
             "Not really a forecast — the null hypothesis. A crypto source that cannot "
             "beat assuming nothing changes is not worth connecting."),
    "sportsgambler": dict(
        label="SportsGambler", kind="Tipster site", connected=False, retired='2026-09-15: 20 won v 21.2 priced on 43 settled (z -0.36, -7.0%). Its match tips add nothing over the price.',
        site="sportsgambler.com", sports=["soccer"],
        note="A named analyst's Main Match Prediction per fixture across 14 leagues. Only "
             "its To Win and Draw calls are scored — about one tip in six; the rest are "
             "over/unders, Asian handicaps and BTTS, which settle a different question. "
             "Its tennis, table-tennis, cricket and boxing pages are not scored: they "
             "restate the bookmaker line as prose, so following them only measures the "
             "favourite."),
    "olbg": dict(
        label="OLBG community tips", kind="Tipster site", connected=True,
        site="olbg.com", sports=["boxing", "mma"],
        note="A tipster community whose members post a Win Fight tip per bout. Reduced to "
             "one call per fight: a fighter must be the most popular selection, with at "
             "least three tips and a strict majority of them. Its tipsters compete on "
             "profit and often pile onto the draw at long odds; a fight whose top tip is "
             "the draw is no call, because the venue fight markets are two-way. Boxing, "
             "UFC and other MMA share its one listing page. The only connected tipster "
             "for either."),
    "soccerpredictions": dict(
        label="SoccerPredictions.ai", kind="Tipster site", connected=True,
        site="soccerpredictions.ai", sports=["soccer"],
        note="One published tip per fixture. Only plain Home / Away / Draw calls are "
             "scored; combined tips such as 'Home & Over 2.5' are a different bet and are "
             "dropped rather than read as a result pick."),
    "tennisexplorer": dict(
        label="Tennis Explorer", kind="Tipster site", connected=False,
        site="tennisexplorer.com", sports=["tennis"],
        note="Parser written and kept, but the match page carries a price on only a "
             "handful of rows — most cells are empty. Connecting it would have produced "
             "an almost-always-zero column indistinguishable from a broken feed."),
    "pickwatch": dict(
        label="NFL Pickwatch (expert consensus)", kind="Tipster site", connected=False,
        site="nflpickwatch.com", sports=["nfl"],
        note="Expert consensus is rendered client-side and the useful views sit behind a "
             "paid trial, so there is nothing a plain fetch can read."),
    "forebet": dict(
        label="Forebet", kind="Tipster site", connected=False,
        site="forebet.com", sports=["nfl", "cricket", "tennis"],
        note="Cloudflare returns 403 to any non-browser request, including from GitHub's "
             "runners. Reachable only through a headless browser, which this pipeline "
             "deliberately does not run."),
    "scores24": dict(
        label="Scores24 (editorial tips)", kind="Tipster site", connected=True,
        site="scores24.live", sports=["soccer", "nfl"],
        retired_sports={
            "mlb": "2026-09-18: 12 won v 13.6 priced on 24 settled (z -0.68, -14.9% after fees). "
                   "Eliminated 2026-09-21: fails in EVERY direction — on 36 settled its picks lost 4.5% and backing the other side lost 2.8%.",
            "tennis": "Eliminated 2026-09-21: fails in EVERY direction — backing its tennis picks lost 4.7% after fees on 17, and backing the other side lost 2.9%."},
        note="Named human tipsters publishing a written call per match. Cloudflare 403s "
             "every plain request, so this is the one source fetched through a real "
             "headless browser. Only its MATCH-WINNER tips are scored — its totals and "
             "handicap tips settle on a different question than the market they would "
             "be booked against."),
    "pinnacle": dict(
        label="Pinnacle (via The Odds API)", kind="Sportsbook", connected=True,
        site="pinnacle.com", sports=["soccer", "boxing", "mma", "cricket", "tennis"],
        note="The sharpest book there is — it takes the largest limits and moves on sharp "
             "money rather than shading against the public — de-vigged to a fair "
             "probability and read through The Odds API (ODDS_API_KEY), and backed where it "
             "beats the venue's ask by 3pp. Planned after every other source: the month's "
             "paced credits go first to the sport keys with the most contests no tipster, "
             "model or book covers. Soccer is de-vigged three-way. Coverage is partial: "
             "boxing and MMA well, soccer by league, cricket on majors and internationals, "
             "tennis only at the big tournaments — not ITF or Challenger."),
    "pin_totals": dict(
        label="Pinnacle's goal total v Kalshi's", kind="Sportsbook", connected=True,
        site="pinnacle.com", sports=["soccer_o25", "soccer_o25_cup", "soccer_o25_intl"],
        note="Pre-registered 2026-09-22, before it logged anything. No forecast and no form: "
             "Pinnacle's own over-2.5 price, de-vigged against its under, backed where it beats "
             "the Kalshi ask by 3pp — the standing edge every price source here is held to. "
             "Why: on 152 graded fixtures the book's de-vigged fair was accurate to within a "
             "point on four of five markets and our own model was worse on all five, so the "
             "remaining question is not who forecasts better but whether the young exchange "
             "and the sharp book ever disagree. The same test on the match winner already "
             "failed — 57 soccer quotes, not one reaching 3pp, which is why soccer is retired "
             "from paid match-winner calls — and totals are a different market with a "
             "different book. Only the 2.5 line, because it is the one both venues quote "
             "without paying for alternates. Lines over an hour old are dropped, and a run "
             "buys at most one league key and at most half its paced credits, so the older "
             "match-winner lane keeps its share and the month's budget does not shorten."),
}


# ---------------------------------------------------------------------------
# Paused lanes (2026-09-25). Approved in full; paper only.
# ---------------------------------------------------------------------------
# A paused lane logs no NEW entry. Every row already in the ledger stays, with its
# result and its P/L, and any entry still open keeps settling on the usual grade.
# Nothing here deletes a source, an adapter, or a row.
#
# Re-enable a whole lane by deleting its line. Re-enable one sport of a partial
# pause by deleting that sport from its set. Re-enable NFL for sources that are
# not themselves paused by deleting "nfl" from PAUSED_SPORTS. Both gates apply:
# taking "nfl" out of PAUSED_SPORTS does not resume a source that is paused on
# its own, and taking a source off PAUSED_LANES does not resume NFL.
#
# tt_band_55_60, cmd_tail and sportsgambler were already retired (connected=False)
# before this list. They stay listed, so setting connected=True does not by itself
# resume them — delete the line as well. Their open rows still settle.
#
# Value None pauses every sport. {"keep": {...}} pauses every sport not named.
# {"sports": {...}} pauses only those sports.

PAUSED_LANES = {
    # −6.7% after fees.
    "covers": None,
    # Kalshi, all of it MLB, −19.7% after fees.
    "kalshi": None,
    # Outside soccer is negative. Soccer (n=11, +6.2%) stays.
    "scores24": {"keep": frozenset({"soccer"})},
    # The whole comparison lane, MLB included.
    "polymarket": None,
    "draftkings": None,
    "mlb_fade_streak": None,
    # The follow direction. The other side is nws_fade, which is not paused.
    "nws": None,
    # Already retired. Kept here so reconnecting it does not resume it.
    "tt_band_55_60": None,
    # MMA −11.9%. Boxing, and any other OLBG sport, stays.
    "olbg": {"sports": frozenset({"mma"})},
    # 1 of 6.
    "pinnacle": None,
    # Flat, with tail risk. Already retired; kept here so it cannot resume alone.
    "cmd_tail": None,
    "btts_form_l10": None,
    "o15_form_l10": None,
    # Already retired. Kept here so reconnecting it does not resume it.
    "sportsgambler": None,
    # 3- and 4-leg tennis baskets. The 2-leg lanes (tennis_combo2, pm_combo2) stay.
    "tennis_combo3": None,
    "tennis_combo4": None,
    "pm_combo3": None,
    "pm_combo4": None,
    "nhl_dog_pl": None,
    "gas_nochange": None,
    "oddspedia": None,
    # NFL only. MLB stays.
    "espn_fpi": {"sports": frozenset({"nfl"})},
}

# Every NFL entry, from any lane, including a source that is not listed above.
PAUSED_SPORTS = frozenset({"nfl"})

_NOT_PAUSED = object()


def lane_paused(source, sport):
    """True when (source, sport) must not log a new entry.

    Open entries already in the ledger are not this function's business: grade()
    settles them whether or not the lane is paused. Re-enable by editing
    PAUSED_LANES or PAUSED_SPORTS — see those.
    """
    if sport in PAUSED_SPORTS:
        return True
    spec = PAUSED_LANES.get(source, _NOT_PAUSED)
    if spec is _NOT_PAUSED:
        return False
    if spec is None:
        return True
    if "keep" in spec:
        return sport not in spec["keep"]
    return sport in (spec.get("sports") or ())


def source_fully_paused(source):
    """True when no sport this source logs may take a new entry."""
    sports = (SOURCES.get(source) or {}).get("sports") or ()
    if not sports:
        return lane_paused(source, None)
    return all(lane_paused(source, sp) for sp in sports)


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------

# {source: "ok" | "down: reason"} for the current run, written by the adapters that fetch
# pages. It separates "the site could not be read" from "the site had nothing to say":
# Oddspedia's cricket page once carried exactly two tips, on opposite sides of the same
# match, so its consensus rightly made no call — and a count-based alarm reported the
# feed as broken while the page was loading fine.
FEED_STATUS = {}


def _mark(name, ok, why="unreachable"):
    """Record a source's health; one successful page anywhere makes the source "ok"."""
    if ok:
        FEED_STATUS[name] = "ok"
    elif FEED_STATUS.get(name) != "ok":
        FEED_STATUS[name] = f"down: {why}"


def _mark_urls(name, urls):
    import sandbox_browser as B
    states = [B.STATUS.get(u, "not fetched") for u in urls]
    bad = next((st for st in states if st != "ok"), "not fetched")
    _mark(name, any(st == "ok" for st in states), bad)


def _get(url, tries=3, timeout=20):
    """GET JSON, with a curl fallback.

    urllib is the repo convention and is what works inside GitHub Actions. It is NOT
    what works from this machine: the local sandbox's egress makes ESPN answer urllib
    with 403 while answering curl normally. Falling back rather than switching wholesale
    keeps CI on the path the rest of the repo already uses, and still lets the exact same
    script be run and debugged locally.
    """
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=timeout) as f:
                return json.load(f)
        # OSError covers URLError, timeouts and a dropped connection; HTTPException covers
        # a truncated body; ValueError covers bad JSON. The narrower list this replaced
        # let http.client.RemoteDisconnected through, and one Polymarket hiccup crashed
        # an entire run — no grading, nothing saved.
        except (OSError, http.client.HTTPException, ValueError) as e:
            last = e
            time.sleep(1.2 * (i + 1))
    try:
        out = subprocess.run(
            ["curl", "-s", "--max-time", str(timeout), "-A", UA, url],
            capture_output=True, text=True, timeout=timeout + 10)
        if out.stdout:
            return json.loads(out.stdout)
    except Exception:
        pass
    raise RuntimeError(f"fetch failed [{type(last).__name__}: {last}] {url}")


# ---------------------------------------------------------------------------
# Name matching
# ---------------------------------------------------------------------------

# Words that carry no identity. "red"/"white" stay IN on purpose: dropping them collapses
# Red Sox and White Sox onto the same key, which is exactly the kind of silent mismatch
# that would book a pick against the wrong game.
STOP = {"the", "fc", "at", "vs", "v", "and", "de", "of", "wins", "win"}

# ---------------------------------------------------------------------------
# Team aliases
# ---------------------------------------------------------------------------

# The three feeds name the same team three different ways: Polymarket says "Giants",
# ESPN says "New York Giants", and Kalshi says "New York G". Token overlap alone scores
# that pair at ZERO, which is why the first live run matched 0 of 31 NFL games and looked
# exactly like a source with nothing to say. City alone is not enough either — Kalshi's
# truncated "Los Angeles R" / "Los Angeles C" are only told apart by the trailing letter,
# so the alias has to carry it.
NICKNAMES = {
    "nfl": {
        "cardinals": ["arizona"], "falcons": ["atlanta"], "ravens": ["baltimore"],
        "bills": ["buffalo"], "panthers": ["carolina"], "bears": ["chicago"],
        "bengals": ["cincinnati"], "browns": ["cleveland"], "cowboys": ["dallas"],
        "broncos": ["denver"], "lions": ["detroit"], "packers": ["green bay"],
        "texans": ["houston"], "colts": ["indianapolis"], "jaguars": ["jacksonville"],
        "chiefs": ["kansas city"], "raiders": ["las vegas"],
        "chargers": ["los angeles c"], "rams": ["los angeles r"],
        "dolphins": ["miami"], "vikings": ["minnesota"], "patriots": ["new england"],
        "saints": ["new orleans"], "giants": ["new york g"], "jets": ["new york j"],
        "eagles": ["philadelphia"], "steelers": ["pittsburgh"],
        "49ers": ["san francisco", "niners"], "seahawks": ["seattle"],
        "buccaneers": ["tampa bay", "bucs"], "titans": ["tennessee"],
        "commanders": ["washington"],
    },
    "mlb": {
        "diamondbacks": ["arizona", "dbacks"], "braves": ["atlanta"],
        "orioles": ["baltimore"], "red sox": ["boston"], "cubs": ["chicago c"],
        "white sox": ["chicago w"], "reds": ["cincinnati"], "guardians": ["cleveland"],
        "rockies": ["colorado"], "tigers": ["detroit"], "astros": ["houston"],
        "royals": ["kansas city"], "angels": ["los angeles a"],
        "dodgers": ["los angeles d"], "marlins": ["miami"], "brewers": ["milwaukee"],
        "twins": ["minnesota"], "mets": ["new york m"], "yankees": ["new york y"],
        "athletics": ["oakland", "sacramento", "a s", "as"], "phillies": ["philadelphia"],
        "pirates": ["pittsburgh"], "padres": ["san diego"], "giants": ["san francisco"],
        "mariners": ["seattle"], "cardinals": ["st louis", "saint louis"],
        "rays": ["tampa bay"], "rangers": ["texas"], "blue jays": ["toronto"],
        "nationals": ["washington"],
    },
}


def canon(name, sport):
    """Team name -> canonical nickname, or '' when the sport has no alias table.

    Individual sports (tennis, boxing, table tennis) get '' on purpose: player names
    already agree across feeds, and inventing aliases for them would only create
    false matches between players who share a surname.
    """
    table = NICKNAMES.get(sport)
    if not table:
        return ""
    n = re.sub(r"[^a-z0-9 ]", " ", _fold(name))
    n = " ".join(n.split())
    for nick, alts in table.items():
        if nick in n:
            return nick
        for a in alts:
            if n == a or n.startswith(a + " ") or n == a.replace(" ", ""):
                return nick
    return ""




def _fold(name):
    """Lowercase, accents stripped: "São Paulo" -> "sao paulo", "Köln" -> "koln".

    Without this the non-ASCII letter became a separator — "São" tokenized to a lone
    "s", which the length filter then threw away — so São Paulo could never match
    Sao Paulo, and every Brazilian, German and French club with an accent was at risk.
    """
    s = unicodedata.normalize("NFKD", str(name))
    return s.encode("ascii", "ignore").decode("ascii").lower()


@functools.lru_cache(maxsize=50000)
def tokens(name):
    """Lowercase alphanumeric tokens of a team or player name, minus filler.

    Cached, and frozen so a cached result can never be mutated by a caller. Matching is
    every quote against every fixture, and with soccer on Kalshi that is several
    hundred fixtures a run — recomputing each name thousands of times was the slow part.
    """
    t = re.sub(r"[^a-z0-9 ]", " ", _fold(name))
    return frozenset(w for w in t.split() if w and w not in STOP and len(w) > 1)


def sim(a, b):
    """Overlap of two names, normalised by the SHORTER one.

    Normalising by the shorter side is what lets "Yankees" match "New York Yankees"
    (1.0) while keeping "Boston Red Sox" and "Chicago White Sox" apart (0.33).
    """
    ta, tb = tokens(a), tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / min(len(ta), len(tb))


# ---------------------------------------------------------------------------
# Soccer names
# ---------------------------------------------------------------------------
#
# Soccer is where name matching is most dangerous, because the failure is not a missed
# match but a WRONG one. Clubs share cities (Manchester United / City, Inter / AC Milan,
# PSG / Paris FC, Hertha / Union Berlin), and the NFL/MLB approach — a substring check on
# a nickname — would book an AC Milan tip against Inter ("milan" is inside "inter
# milan"). Three rules replace it:
#
#   1. aliases are matched on WORD boundaries, longest first, so "Inter Milan" resolves
#      before "Milan" can and "internacional" never matches "inter";
#   2. two known clubs are decisive: same key 1.0, different keys 0;
#   3. unknown names only match when one is a SUBSET of the other ("Newcastle" in
#      "Newcastle United"). If each has a word the other lacks, they are two different
#      clubs — which is exactly the Manchester United / Manchester City case.
SOCCER_ALIASES = {
    # England
    "manchester united": ["manchester united", "man united", "man utd", "manchester utd", "man u"],
    "manchester city": ["manchester city", "man city"],
    "tottenham": ["tottenham hotspur", "tottenham", "spurs"],
    "wolverhampton": ["wolverhampton wanderers", "wolverhampton", "wolves"],
    "brighton": ["brighton and hove albion", "brighton hove albion", "brighton"],
    "west ham": ["west ham united", "west ham"],
    "newcastle": ["newcastle united", "newcastle"],
    "nottingham forest": ["nottingham forest", "nottm forest", "nott m forest"],
    "sheffield united": ["sheffield united", "sheffield utd", "sheff utd"],
    "sheffield wednesday": ["sheffield wednesday", "sheff wed"],
    "leeds": ["leeds united", "leeds"],
    "leicester": ["leicester city", "leicester"],
    "ipswich": ["ipswich town", "ipswich"],
    # Spain
    "athletic bilbao": ["athletic club", "athletic bilbao", "bilbao"],
    "atletico madrid": ["atletico madrid", "atl madrid", "atleti", "atletico"],
    "rayo vallecano": ["rayo vallecano", "vallecano", "rayo"],
    "racing santander": ["racing santander", "racing de santander", "santander"],
    "real sociedad": ["real sociedad", "sociedad"],
    "real betis": ["real betis", "betis"],
    "alaves": ["deportivo alaves", "alaves"],
    "celta vigo": ["celta vigo", "celta"],
    # Germany
    "bayern munich": ["bayern munich", "bayern munchen", "fc bayern", "bayern"],
    "rb leipzig": ["rb leipzig", "rasenballsport leipzig", "leipzig"],
    "eintracht frankfurt": ["eintracht frankfurt", "frankfurt"],
    "werder bremen": ["werder bremen", "bremen", "werder"],
    "monchengladbach": ["borussia monchengladbach", "monchengladbach", "mgladbach",
                        "m gladbach", "gladbach"],
    "koln": ["1 fc koln", "fc koln", "koln", "cologne"],
    "dortmund": ["borussia dortmund", "dortmund", "bvb"],
    "leverkusen": ["bayer leverkusen", "leverkusen"],
    "mainz": ["mainz 05", "fsv mainz", "mainz"],
    "hertha": ["hertha berlin", "hertha bsc", "hertha"],
    "union berlin": ["1 fc union berlin", "union berlin"],
    "hamburg": ["hamburger sv", "hamburg", "hsv"],
    "st pauli": ["fc st pauli", "st pauli", "sankt pauli"],
    "schalke": ["schalke 04", "schalke"],
    # Italy
    "inter": ["inter milan", "internazionale", "inter"],
    "milan": ["ac milan", "milan"],
    "roma": ["as roma", "roma"],
    "lazio": ["ss lazio", "lazio"],
    "napoli": ["ssc napoli", "napoli"],
    "parma": ["parma calcio", "parma"],
    "verona": ["hellas verona", "verona"],
    # France
    "psg": ["paris saint germain", "paris sg", "psg"],
    "paris fc": ["paris fc"],
    "rennes": ["stade rennais", "rennes"],
    "brest": ["stade brest 29", "stade brestois", "stade brest", "brest"],
    "strasbourg": ["strasbourg alsace", "rc strasbourg", "strasbourg"],
    "marseille": ["olympique de marseille", "olympique marseille", "marseille"],
    "lyon": ["olympique lyonnais", "olympique lyon", "lyon"],
    "saint etienne": ["saint etienne", "st etienne"],
    # Netherlands
    "psv": ["psv eindhoven", "psv", "eindhoven"],
    "twente": ["fc twente", "twente", "enschede"],
    "az": ["az alkmaar", "az"],
    "go ahead eagles": ["go ahead eagles", "ga eagles"],
    "nec": ["nec nijmegen", "nijmegen", "nec"],
    "fortuna sittard": ["fortuna sittard", "sittard"],
    "pec zwolle": ["pec zwolle", "zwolle"],
    "sparta rotterdam": ["sparta rotterdam", "sparta"],
    "ado den haag": ["ado den haag", "den haag"],
    # USA / MLS
    "la galaxy": ["los angeles galaxy", "la galaxy", "los angeles g", "galaxy"],
    "lafc": ["los angeles fc", "lafc", "los angeles f"],
    "inter miami": ["inter miami cf", "inter miami"],
    "new york city": ["new york city fc", "nycfc", "new york city"],
    "new york red bulls": ["new york red bulls", "ny red bulls", "red bulls", "red bull new york",
                           "new york rb"],
    # Kalshi BTTS event titles (2026-09-13): "DC United", "Ferencvarosi", "Lillestroem"
    "dc united": ["d c united", "dc united"],
    "ferencvaros": ["ferencvaros", "ferencvarosi"],
    "lillestrom": ["lillestrom", "lillestroem"],
    "st louis city": ["st louis city", "saint louis city", "st louis", "saint louis"],
    "real salt lake": ["real salt lake", "salt lake"],
    "cf montreal": ["cf montreal", "montreal"],
    "new england": ["new england revolution", "new england"],
    "chicago fire": ["chicago fire", "chicago"],
    "sporting kc": ["sporting kansas city", "sporting kc"],
    # Mexico
    "club america": ["club america", "america"],
    "pumas": ["pumas unam", "unam", "pumas"],
    "tijuana": ["tijuana de caliente", "club tijuana", "tijuana", "xolos"],
    "atletico san luis": ["atletico san luis", "san luis"],
    "guadalajara": ["chivas guadalajara", "guadalajara", "chivas"],
    "santos laguna": ["santos laguna"],
    # Brazil / South America
    "athletico paranaense": ["athletico paranaense", "atletico paranaense", "paranaense"],
    "atletico mineiro": ["atletico mineiro", "atletico mg"],
    "america mineiro": ["america mineiro", "america mg"],
    "vasco": ["vasco da gama", "vasco"],
    "santos": ["santos fc", "santos"],
    "independiente santa fe": ["independiente santa fe", "independ santa fe"],
}

# Words that name no club on their own. A bare "United" or "City" matching any club
# with that word would be the subset rule's one blind spot.
SOCCER_FILLER = {"fc", "cf", "afc", "sc", "ac", "club", "cd", "ud", "sd", "calcio", "sv",
                 "as", "ss", "ssc", "rc", "ogc", "de", "la", "le", "el", "the"}
SOCCER_GENERIC = {"united", "city", "town", "real", "athletic", "sporting", "rovers",
                  "wanderers", "county", "albion"}


def _phrase(name):
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", _fold(name)).split())


_SOCCER_INDEX = sorted(((_phrase(v), key) for key, vs in SOCCER_ALIASES.items() for v in vs),
                       key=lambda kv: -len(kv[0]))


@functools.lru_cache(maxsize=50000)
def soccer_canon(name):
    """Known club -> canonical key, matched on word boundaries, longest alias first."""
    n = f" {_phrase(name)} "
    for variant, key in _SOCCER_INDEX:
        if f" {variant} " in n:
            return key
    return ""


def soccer_sim(a, b):
    """Two unknown club names: a match only when one is a subset of the other."""
    ta, tb = tokens(a) - SOCCER_FILLER, tokens(b) - SOCCER_FILLER
    if not ta or not tb:
        return 0.0
    if (ta - tb) and (tb - ta):
        return 0.0
    if min((ta, tb), key=len) <= SOCCER_GENERIC:
        return 0.0
    return 1.0


def _score(a, b, sport):
    """How strongly do these two names refer to the same competitor?

    A canonical-nickname hit is decisive (1.0); anything else falls back to token
    overlap. Two DIFFERENT known teams score 0 outright — without that, "Los Angeles
    Rams" and "Los Angeles Chargers" share a city and would otherwise score 0.67.
    """
    if sport == "soccer":
        ca, cb = soccer_canon(a), soccer_canon(b)
        if ca and cb:
            return 1.0 if ca == cb else 0.0
        return soccer_sim(a, b)
    ca, cb = canon(a, sport), canon(b, sport)
    if ca and cb:
        return 1.0 if ca == cb else 0.0
    s = sim(a, b)
    if s == 0 and sport in ("boxing", "mma"):
        # Fighters' names are transliterated, and every feed does it differently: Kalshi
        # and Polymarket write "Mikaelian", OLBG "Mikaeljan", for the same Armenian
        # fighter. A long word spelled almost identically is the same name. Scored below
        # an exact hit, and pair_match still needs BOTH fighters to clear the floor, so a
        # near-miss on one side cannot drag a wrong bout along with it.
        if any(len(x) >= 5 and len(y) >= 5
               and difflib.SequenceMatcher(None, x, y).ratio() >= 0.85
               for x in tokens(a) for y in tokens(b)):
            return 0.75
    return s


def pair_match(a1, a2, b1, b2, sport=None, floor=0.5):
    """Match fixture (a1,a2) against fixture (b1,b2), either way round.

    Returns (score, flipped) or (0, False). Both sides must clear `floor` independently,
    so one strong match cannot drag a wrong opponent along with it. Orientation is not a
    detail: a flipped probability is the exact opposite prediction.
    """
    sa = min(_score(a1, b1, sport), _score(a2, b2, sport))
    sf = min(_score(a1, b2, sport), _score(a2, b1, sport))
    if sa >= floor and sa >= sf:
        return (_score(a1, b1, sport) + _score(a2, b2, sport)) / 2, False
    if sf >= floor:
        return (_score(a1, b2, sport) + _score(a2, b1, sport)) / 2, True
    return 0.0, False


def day(ts):
    """ISO-ish timestamp -> YYYY-MM-DD, or '' if unparseable."""
    if not ts:
        return ""
    s = str(ts).replace("Z", "+00:00").replace(" ", "T", 1)
    try:
        return datetime.fromisoformat(s[:25]).astimezone(timezone.utc).strftime("%Y-%m-%d")
    except ValueError:
        return str(ts)[:10]


def american_to_prob(ml):
    """American moneyline -> implied probability (still carrying vig)."""
    try:
        ml = float(ml)
    except (TypeError, ValueError):
        return None
    if ml == 0:
        return None
    return (-ml) / ((-ml) + 100) if ml < 0 else 100 / (ml + 100)


def devig(p_a, p_b):
    """Strip the bookmaker's margin by normalising the two implied probabilities.

    Without this a book's pair sums to ~1.05 and every one of its quotes looks like an
    edge over a prediction-market price that sums to 1.00 — the book would top the
    leaderboard purely on its own vig.
    """
    if p_a is None or p_b is None:
        return None, None
    tot = p_a + p_b
    if tot <= 0:
        return None, None
    return p_a / tot, p_b / tot


# ---------------------------------------------------------------------------
# Polymarket — universe, prices, and settlement oracle
# ---------------------------------------------------------------------------

GAMMA = "https://gamma-api.polymarket.com"


def _pm_json(v, default):
    """gamma returns outcomes/prices as JSON-encoded STRINGS, not arrays."""
    if isinstance(v, list):
        return v
    try:
        return json.loads(v) if v else default
    except (json.JSONDecodeError, TypeError):
        return default


# Words that mark a market as a PROP rather than the head-to-head result. Props are the
# main way a universe like this quietly rots: "Reds vs. Dodgers" is the moneyline, but so
# is the label on "first inning run scored", and a source's win probability booked against
# an inning prop is scored on a question it never answered.
PROP_WORDS = ("o/u", "over", "under", "handicap", "spread", "total", "margin",
              "inning", "quarter", "half", "set", "first to", "correct score",
              "points", "runs", "goals", "aces", "winner", "series")


def _is_head_to_head(question, side_a, side_b):
    """True only for the market that pays out on the RESULT of the contest."""
    q = str(question).lower()
    # Word-boundary, not substring: a plain `"over" in q` also rejects Vancouver, Dover
    # and Hanover, silently deleting real matchups from the universe.
    if any(re.search(r"\b" + re.escape(w.strip()) + r"\b", q) for w in PROP_WORDS):
        return False
    if {str(side_a).strip().lower(), str(side_b).strip().lower()} & {"over", "under", "yes", "no"}:
        return False
    # Both competitors must actually be named in the question. This is what rejects
    # "Set Handicap: Samsonova (-1.5) vs Siegemund (+1.5)"-style relabelling.
    qt = tokens(q)
    return tokens(side_a) <= qt and tokens(side_b) <= qt


# Per sport, per run. The ledger is committed to git four times a day, so unbounded
# intake is a real cost: uncapped, tennis alone logs ~200 contests a day and the file
# reaches double-digit megabytes within months. Capping by VOLUME rather than by an
# arbitrary slice also improves the sample — a market with $12 of volume is a quoted
# price nobody has tested, and it is the deep books that make a source's error visible.
MAX_PER_SPORT = 40

# Fight nights. Neither venue publishes when a BOUT starts: Polymarket stamps every bout
# with the card's start and Kalshi's estimate is three hours before expected expiration,
# which on a card is hours before the later bouts. Both are safe — too early, never too
# late — but they closed Vanhouter v Akpejiori and Opetaia v Mikaelian to logging hours
# before either fought, with an OLBG consensus on each. Pinnacle prices each bout with its
# own commence time, so boxing and MMA rows are re-timed from it, minus a margin because a
# card runs ahead of schedule when the fights before it end early.
START_FROM_PINNACLE = ("boxing", "mma")
PINNACLE_START_MARGIN_MIN = 30
FIGHT_LOOKBACK_H = 12

# A Polymarket price is only a price when there is a book behind it. gamma's
# `outcomePrices` is a MIDPOINT, and a market that has just been listed shows a midpoint
# near 0.50 with nothing on either side of it. Measured 2026-09-12: boxing bouts logged at
# 0.51-0.515 were 0.88-0.90 hours later, once money arrived (Panin v Linger: $59 traded,
# $49 on the book), and against Pinnacle the logged prices were off by a mean of 20pp in
# boxing and 12pp in cricket — but under 2pp in tennis, where the books are real. The old
# check only caught an exact 0.50/0.50, so 0.51/0.49 sailed through and any source
# backing the favourite would have been paid at a price that never existed.
#
# So a row counts as priced only when the spread is tight AND there is money on the book,
# and a priced row is booked at the ASK — the price a follower would actually pay — not
# at the midpoint. The midpoint is kept, as `mid_a`, for Polymarket's own Brier score.
MAX_SPREAD = 0.05
MIN_LIQUIDITY = 100.0


def pm_book(m):
    """(tradeable, ask_a, ask_b, spread, liquidity) for one gamma market.

    ask_b is 1 - best bid on outcome A: buying B is selling A. Missing or one-sided books
    are never tradeable.
    """
    try:
        bid = float(m.get("bestBid")) if m.get("bestBid") is not None else None
        ask = float(m.get("bestAsk")) if m.get("bestAsk") is not None else None
        spread = float(m.get("spread")) if m.get("spread") is not None else None
    except (TypeError, ValueError):
        return False, None, None, None, 0.0
    try:
        liq = float(m.get("liquidityNum") or m.get("liquidity") or 0)
    except (TypeError, ValueError):
        liq = 0.0
    if bid is None or ask is None or not (0 < bid < ask < 1):
        return False, None, None, spread, liq
    if spread is None:
        spread = ask - bid
    ok = spread <= MAX_SPREAD + 1e-9 and liq >= MIN_LIQUIDITY
    return ok, round(ask, 4), round(1 - bid, 4), round(spread, 4), liq


def fetch_polymarket(sport, horizon_days=4, page=100, max_pages=8, cap=MAX_PER_SPORT,
                     stats=None):
    """Every PRE-MATCH head-to-head market for one sport, one row per contest.

    Three filters carry the integrity of the whole board:

    * paginated. gamma silently caps a page at 100 regardless of the limit asked for, so
      a single call made tennis, cricket and table tennis look EMPTY when each in fact
      has hundreds to thousands of live markets. That near-miss is why the page prints
      per-sport market counts: an empty sport must be visibly empty, not absent.
    * strictly future start. A market that is already in play prices the score, not the
      matchup, so a quote logged against it is not a prediction.
    * one row per contest, highest volume wins. A single game carries dozens of markets
      and only one of them is the moneyline.
    """
    tag = PM_TAGS[sport]
    events = []
    for off in range(0, page * max_pages, page):
        try:
            batch = _get(f"{GAMMA}/events?closed=false&limit={page}&offset={off}&tag_slug={tag}")
        except RuntimeError:
            break
        if not isinstance(batch, list) or not batch:
            break
        events += batch
        if len(batch) < page:
            break

    now = datetime.now(timezone.utc)
    horizon = now + timedelta(days=horizon_days)
    best = {}
    for ev in events:
        for m in ev.get("markets") or []:
            if m.get("closed") or not m.get("acceptingOrders"):
                continue
            outs = _pm_json(m.get("outcomes"), [])
            pxs = _pm_json(m.get("outcomePrices"), [])
            if len(outs) != 2 or len(pxs) != 2:
                continue
            if not _is_head_to_head(m.get("question") or ev.get("title"), outs[0], outs[1]):
                continue
            try:
                pa, pb = float(pxs[0]), float(pxs[1])
            except (TypeError, ValueError):
                continue
            if pa <= 0 or pb <= 0 or abs(pa + pb - 1) > 0.08:
                continue
            # Priced only with a real book behind it — see MAX_SPREAD. An untraded row
            # keeps its midpoints for display, but nothing is logged against it.
            tradeable, ask_a, ask_b, spread, liq = pm_book(m)
            untraded = not tradeable

            when = m.get("gameStartTime") or ev.get("startDate")
            try:
                wdt = datetime.fromisoformat(
                    str(when).replace("Z", "+00:00").replace(" ", "T", 1)[:25])
                if wdt.tzinfo is None:
                    wdt = wdt.replace(tzinfo=timezone.utc)
            except (ValueError, TypeError):
                continue
            # Fight markets list the CARD's start for every bout (a whole Zuffa card at
            # 21:00Z, a Noche UFC main event at 18:00Z that walked out hours later), so a
            # passed start there does not mean the bout has begun. Those rows are kept
            # while the market is open and re-timed from Pinnacle in apply_pinnacle_starts,
            # which drops any it cannot re-time.
            early = (now - timedelta(hours=FIGHT_LOOKBACK_H) if sport in START_FROM_PINNACLE
                     else now - timedelta(minutes=5))
            if not (early <= wdt <= horizon):
                continue

            vol = float(m.get("volumeNum") or 0)
            key = (frozenset({frozenset(tokens(outs[0])), frozenset(tokens(outs[1]))}),
                   wdt.strftime("%Y-%m-%d"))
            row = dict(
                sport=sport,
                market_id=str(m.get("id")),
                label=f"{outs[0]} vs {outs[1]}",
                side_a=str(outs[0]), side_b=str(outs[1]),
                price_a=ask_a if tradeable else pa, price_b=ask_b if tradeable else pb,
                mid_a=pa, spread=spread, liquidity=round(liq, 2),
                start=wdt.isoformat(), date=wdt.strftime("%Y-%m-%d"),
                volume=vol, untraded=untraded,
                url=f"https://polymarket.com/event/{ev.get('slug')}",
            )
            # A priced row always beats an unpriced one for the same contest, whatever
            # the volumes: the unpriced one cannot be logged at all.
            if (key not in best or (untraded, -vol) < (best[key]["untraded"],
                                                       -best[key]["volume"])):
                best[key] = row

    # Priced books first, deepest first, then cut — so the intake cap is never spent on
    # rows that cannot be logged. (Sorting on volume alone let a high-volume market with
    # a 30c spread take a slot from a tight one.)
    rows = sorted(best.values(), key=lambda r: (r["untraded"], -r["volume"], r["start"]))

    # Pre-cap totals, reported separately. The coverage panel exists to answer whether
    # Polymarket really carries these six sports, and answering that with a number the
    # intake cap had already truncated to 40 would be answering a different question.
    if stats is not None:
        stats["listed"] = len(rows)
        stats["priced"] = sum(1 for r in rows if not r["untraded"])

    return rows[:cap] if cap else rows


# ---------------------------------------------------------------------------
# Polymarket US — the venue (2026-09-13)
# ---------------------------------------------------------------------------
#
# Until 2026-09-13 every non-soccer contest was priced and settled on polymarket.com, the
# international exchange, closed to US accounts. A source promoted to Production on .com
# prices would have been judged on a book, a spread and a liquidity no US follower gets — so
# the venue is now Polymarket US (CFTC-
# regulated, USD), and .com stays only as a price-comparison source ("polymarket").
#
# Structure (gateway.polymarket.us, public): sport -> leagues -> events, each event carrying
# its markets. The contest's own market is a two-outcome "winner" market whose best bid and
# ask quote the FIRST outcome; buying the second outcome is selling the first, so its ask
# is 1 - bid — the same arithmetic as .com. Settlement (/v1/markets/{slug}/settlement) is 1
# when the first outcome won, 0 when it lost. An event whose `period` is anything but
# not-started is in play and never quoted.
PMUS = "https://gateway.polymarket.us"
PMUS_SPORT = {"tennis": ("Tennis", None), "table_tennis": ("Table Tennis", None),
              "boxing": ("Boxing", None), "mma": ("MMA", None),
              "cricket": ("Cricket", None), "nfl": ("Football", {"nfl"}),
              "mlb": ("Baseball", {"mlb"})}
PMUS_NOT_WINNER = ("first", "half", "set", "quarter", "period", "inning", "five", "round")
_pmus_leagues = None


def pmus_leagues(sport):
    """League slugs Polymarket US lists for one of our sports (one cached /v2/sports call)."""
    global _pmus_leagues
    if _pmus_leagues is None:
        try:
            _pmus_leagues = {s.get("name"): [l.get("slug") for l in s.get("leagues") or []]
                             for s in (_get(f"{PMUS}/v2/sports") or {}).get("sports") or []}
        except RuntimeError:
            _pmus_leagues = {}
    name, only = PMUS_SPORT.get(sport, (None, None))
    slugs = _pmus_leagues.get(name) or []
    return [s for s in slugs if not only or s in only]


def _pmus_amt(x):
    if isinstance(x, dict):
        x = x.get("value")
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def pmus_book(m):
    """(tradeable, ask_a, ask_b, spread, mid_a) for one Polymarket US winner market."""
    bid, ask = _pmus_amt(m.get("bestBidQuote")), _pmus_amt(m.get("bestAskQuote"))
    if bid is None or ask is None or not (0 < bid < ask < 1):
        return False, None, None, None, None
    spread = round(ask - bid, 4)
    return (spread <= MAX_SPREAD + 1e-9, round(ask, 4), round(1 - bid, 4), spread,
            round((bid + ask) / 2, 4))


def pmus_sides(m):
    """(long outcome, short outcome) for one Polymarket US two-way market.

    The book (bestBid/bestAsk) and the settlement are both the LONG side's, and the long
    side is the one marketSides flags — NOT outcomes[0]. The two agree for tennis but not
    for NFL/MLB: "MIA Dolphins vs SF 49ers" lists outcomes ["49ers", "Dolphins"] while its
    0.10 book is the Dolphins'. Reading outcomes[0] logged the 49ers at the Dolphins' price
    and graded them on the Dolphins' result. outcomes order is the fallback only."""
    outs = [str(o) for o in _pm_json(m.get("outcomes"), [])]
    sides = m.get("marketSides") or []
    longs = [s for s in sides if s.get("long") is True]
    shorts = [s for s in sides if s.get("long") is False]
    if len(sides) == 2 and len(longs) == 1 and len(shorts) == 1:
        name = lambda s: str(s.get("description") or (s.get("team") or {}).get("alias") or "")
        ln, sn = name(longs[0]), name(shorts[0])
        if ln and sn and ln != sn:
            return ln, sn
    return (outs[0], outs[1]) if len(outs) == 2 else (None, None)


def fetch_polymarket_us(sport, horizon_days=4, cap=MAX_PER_SPORT, stats=None):
    """Every pre-match head-to-head contest Polymarket US lists for one sport, as universe rows."""
    now = datetime.now(timezone.utc)
    horizon = now + timedelta(days=horizon_days)
    early = (now - timedelta(hours=FIGHT_LOOKBACK_H) if sport in START_FROM_PINNACLE
             else now - timedelta(minutes=5))
    rows, listed = [], 0
    for slug in pmus_leagues(sport):
        try:
            events = (_get(f"{PMUS}/v2/leagues/{slug}/events?limit=100", tries=2) or {}).get("events") or []
        except RuntimeError:
            continue
        for ev in events:
            if ev.get("closed") or (ev.get("period") not in (None, "", "NS")):
                continue                              # finished, or in play
            winners = [m for m in ev.get("markets") or []
                       if not m.get("closed")
                       and ("winner" in str(m.get("sportsMarketType")) or m.get("sportsMarketType") == "moneyline")
                       and not any(w in str(m.get("sportsMarketType")) for w in PMUS_NOT_WINNER)
                       and len(_pm_json(m.get("outcomes"), [])) == 2]
            if len(winners) != 1:
                continue                              # none, or ambiguous: no guess
            m = winners[0]
            outs = pmus_sides(m)
            when = m.get("gameStartTime") or ev.get("startTime") or ev.get("startDate")
            try:
                wdt = datetime.fromisoformat(str(when).replace("Z", "+00:00"))
            except (ValueError, TypeError):
                continue
            if not (early <= wdt <= horizon):
                continue
            listed += 1
            tradeable, ask_a, ask_b, spread, mid_a = pmus_book(m)
            rows.append(dict(
                sport=sport, venue="polymarket_us", market_id=str(m.get("slug")),
                label=f"{outs[0]} vs {outs[1]}", side_a=str(outs[0]), side_b=str(outs[1]),
                price_a=ask_a if ask_a is not None else 0.5,
                price_b=ask_b if ask_b is not None else 0.5,
                mid_a=mid_a if mid_a is not None else 0.5, spread=spread, liquidity=None,
                start=wdt.isoformat(), date=wdt.strftime("%Y-%m-%d"), volume=0.0,
                untraded=not tradeable, url=f"https://polymarket.us/event/{ev.get('slug')}",
            ))
    rows.sort(key=lambda r: (r["untraded"], r["start"]))
    if stats is not None:
        stats["listed"] = listed
        stats["priced"] = sum(1 for r in rows if not r["untraded"])
    return rows[:cap] if cap else rows


def resolve_polymarket_us(slug):
    """'a' / 'b' / 'void' from Polymarket US's settlement, or None while unsettled."""
    try:
        d = _get(f"{PMUS}/v1/markets/{urllib.parse.quote(str(slug))}/settlement", tries=1)
    except RuntimeError:
        return None                                   # 404 until it settles
    st = (d or {}).get("settlement") if isinstance(d, dict) else None
    try:
        st = float(st)
    except (TypeError, ValueError):
        return None
    return "a" if st >= 0.99 else "b" if st <= 0.01 else "void"


def polymarket_com_probs(sport):
    """polymarket.com's midpoint on every contest it prices — a comparison source since the
    venue moved to Polymarket US. Quotes only priced books; matched onto the US universe."""
    out = []
    for r in fetch_polymarket(sport):
        if r["untraded"]:
            continue
        out.append(dict(a=r["side_a"], b=r["side_b"], prob_a=r.get("mid_a", r["price_a"]),
                        date=r["date"]))
    return out


def resolve_polymarket(market_id):
    """Settlement oracle: has this market resolved, and to which side?

    Returns 'a', 'b', 'void', or None if still open. Polymarket writes the resolution
    back into outcomePrices as a hard 1/0, which is why one feed can settle all six
    sports — ESPN has no boxing or table tennis at all.
    """
    try:
        m = _get(f"{GAMMA}/markets/{market_id}", tries=2)
    except RuntimeError:
        return None
    if not isinstance(m, dict) or not m.get("closed"):
        return None
    pxs = _pm_json(m.get("outcomePrices"), [])
    if len(pxs) != 2:
        return None
    try:
        pa, pb = float(pxs[0]), float(pxs[1])
    except (TypeError, ValueError):
        return None
    if pa >= 0.99 and pb <= 0.01:
        return "a"
    if pb >= 0.99 and pa <= 0.01:
        return "b"
    # Closed without a clean 1/0 — cancelled, or UMA still disputing it. Refund, never
    # guess: booking a coin-flip here would quietly invent P/L.
    return "void"


# ---------------------------------------------------------------------------
# Challenger sources
# ---------------------------------------------------------------------------

MONTHS = {m: i + 1 for i, m in enumerate(
    ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"])}


def kalshi_date(ticker, fallback=None):
    """Game date out of a Kalshi ticker: KXNFLGAME-26SEP21NYGLAR -> 2026-09-21.

    The ticker is the only trustworthy date on the record. `close_time` sits roughly two
    days AFTER kickoff (settlement window, not start), and using it shifted every NFL
    game a week forward — which killed all 31 matches against Polymarket while looking
    like Kalshi simply had no NFL book.
    """
    m = re.search(r"-(\d{2})([A-Z]{3})(\d{2})", str(ticker))
    if m:
        yy, mon, dd = m.groups()
        if mon in MONTHS:
            return f"20{yy}-{MONTHS[mon]:02d}-{int(dd):02d}"
    return day(fallback)


def fetch_kalshi(sport):
    """Kalshi's open markets for one sport, re-paired into two-sided contests.

    Kalshi lists one market PER SIDE ("New York G wins"), so the two legs of a game have
    to be rejoined through the event ticker before they mean anything. The book is also
    cursor-paginated: without following the cursor only the first page arrives, which is
    mostly NEXT week's games and misses the ones actually about to be played.
    """
    series = KALSHI_SERIES.get(sport)
    if not series:
        return []

    markets, cursor = [], ""
    for _ in range(10):
        url = ("https://api.elections.kalshi.com/trade-api/v2/markets"
               f"?limit=200&status=open&series_ticker={series}")
        if cursor:
            url += f"&cursor={cursor}"
        try:
            d = _get(url, tries=2)
        except RuntimeError:
            break
        batch = d.get("markets") or []
        markets += batch
        cursor = d.get("cursor") or ""
        if not cursor or not batch:
            break

    by_event = {}
    for m in markets:
        by_event.setdefault(m.get("event_ticker"), []).append(m)

    out = []
    for ticker, legs in by_event.items():
        if len(legs) != 2:
            continue
        a, b = legs

        def mid(m):
            """Mid of the book, in probability. Falls back to the last trade."""
            for lo, hi in (("yes_bid_dollars", "yes_ask_dollars"), ("yes_bid", "yes_ask")):
                try:
                    x, y = float(m.get(lo)), float(m.get(hi))
                    if x > 0 and y > 0:
                        v = (x + y) / 2
                        return v if v <= 1 else v / 100
                except (TypeError, ValueError):
                    continue
            for k in ("last_price_dollars", "last_price"):
                try:
                    v = float(m.get(k))
                    if v > 0:
                        return v if v <= 1 else v / 100
                except (TypeError, ValueError):
                    continue
            return None

        pa, pb = mid(a), mid(b)
        if pa is None and pb is None:
            continue
        if pa is None:
            pa = 1 - pb
        elif pb is None:
            pb = 1 - pa
        pa, pb = devig(pa, pb)
        if pa is None:
            continue
        out.append(dict(a=str(a.get("yes_sub_title") or a.get("title") or ""),
                        b=str(b.get("yes_sub_title") or b.get("title") or ""),
                        prob_a=pa, date=kalshi_date(ticker, a.get("close_time"))))
    return out


# site.api.espn.com has 403-ed every request since 2026-08-08 — this machine AND the
# GitHub runner, any user-agent. It is a server-side block, not a header problem, and
# streaks_fetch.py hit the same wall and moved to this host. site.web.api serves the
# identical payload. sports.core.api (predictor/odds) is unaffected.
ESPN_SITE = "https://site.web.api.espn.com"


def _espn_events(sport, days=4):
    """ESPN scoreboard events across a small date window."""
    site, _ = ESPN_PATHS[sport]
    seen, evs = set(), []
    base = datetime.now(timezone.utc)
    for i in range(days):
        d = (base + timedelta(days=i)).strftime("%Y%m%d")
        try:
            sb = _get(f"{ESPN_SITE}/apis/site/v2/sports/{site}/scoreboard?dates={d}",
                      tries=2)
        except RuntimeError as e:
            if not evs:
                print(f"  ! espn scoreboard {sport} {d}: {str(e)[:90]}")
            continue
        for ev in sb.get("events") or []:
            if ev.get("id") in seen:
                continue
            seen.add(ev.get("id"))
            evs.append(ev)
    return evs


def _espn_sides(ev):
    """(home_name, away_name, competition_id) for an ESPN event, or None."""
    comps = ev.get("competitions") or []
    if not comps:
        return None
    c = comps[0]
    home = away = None
    for t in c.get("competitors") or []:
        nm = (t.get("team") or {}).get("displayName")
        if t.get("homeAway") == "home":
            home = nm
        elif t.get("homeAway") == "away":
            away = nm
    if not home or not away:
        return None
    return home, away, c.get("id")


def fetch_espn_fpi(sport):
    """ESPN's own win probability (gameProjection) per upcoming game."""
    if sport not in ESPN_PATHS:
        return []
    _, core = ESPN_PATHS[sport]
    out, evs, failed = [], _espn_events(sport), 0
    for ev in evs:
        sides = _espn_sides(ev)
        if not sides:
            continue
        home, away, cid = sides
        try:
            p = _get(f"https://sports.core.api.espn.com/v2/sports/{core}"
                     f"/events/{ev['id']}/competitions/{cid}/predictor", tries=2, timeout=20)
        except RuntimeError as e:
            failed += 1
            if failed == 1:
                print(f"  ! espn_fpi/{sport} predictor unreachable: {str(e)[:90]}")
            continue
        stats = {s.get("name"): s.get("displayValue")
                 for s in (p.get("homeTeam") or {}).get("statistics") or []}
        try:
            proj = float(str(stats.get("gameProjection")).strip()) / 100.0
        except (TypeError, ValueError):
            continue
        if not 0 < proj < 1:
            continue
        out.append(dict(a=home, b=away, prob_a=proj, date=day(ev.get("date"))))
        time.sleep(0.12)
    if evs and not out:
        print(f"  ! espn_fpi/{sport}: {len(evs)} games seen, 0 predictions "
              f"({failed} predictor calls failed)")
    return out


def fetch_draftkings(sport):
    """DraftKings moneyline via ESPN's odds feed, de-vigged."""
    if sport not in ESPN_PATHS:
        return []
    _, core = ESPN_PATHS[sport]
    out, evs, failed = [], _espn_events(sport), 0
    for ev in evs:
        sides = _espn_sides(ev)
        if not sides:
            continue
        home, away, cid = sides
        try:
            o = _get(f"https://sports.core.api.espn.com/v2/sports/{core}"
                     f"/events/{ev['id']}/competitions/{cid}/odds", tries=2, timeout=20)
        except RuntimeError as e:
            failed += 1
            if failed == 1:
                print(f"  ! draftkings/{sport} odds unreachable: {str(e)[:90]}")
            continue
        items = o.get("items") or []
        if not items:
            continue
        it = items[0]
        ph = american_to_prob((it.get("homeTeamOdds") or {}).get("moneyLine"))
        pa = american_to_prob((it.get("awayTeamOdds") or {}).get("moneyLine"))
        ph, _pa = devig(ph, pa)
        if ph is None:
            continue
        out.append(dict(a=home, b=away, prob_a=ph, date=day(ev.get("date"))))
        time.sleep(0.12)
    if evs and not out:
        print(f"  ! draftkings/{sport}: {len(evs)} games seen, 0 lines "
              f"({failed} odds calls failed)")
    return out



# ---------------------------------------------------------------------------
# Tipster sites
# ---------------------------------------------------------------------------
#
# A tipster states a PICK, not a probability. That is scoreable — back the named side at
# the market price, flat stake, and the ROI is as real as anyone else's — but it costs
# two things, and the board says so rather than hiding it: a bare pick gets no Brier
# score (there is no number to be calibrated), and no edge filter (a pick carries no
# claim about how big the disagreement is), so every pick inside the price band is
# backed. That makes a tipster's turnover much higher than a model's, which is exactly
# how tipsters are actually followed.

def _get_html(url, tries=2, timeout=30):
    """GET a page as text. Same urllib-then-curl fallback as the JSON fetcher."""
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": UA,
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Language": "en-US,en;q=0.9",
            })
            with urllib.request.urlopen(req, timeout=timeout) as f:
                return f.read().decode("utf-8", "replace")
        except Exception as e:
            last = e
            time.sleep(1.0 * (i + 1))
    try:
        out = subprocess.run(["curl", "-sL", "--max-time", str(timeout), "-A", UA, url],
                             capture_output=True, text=True, timeout=timeout + 10)
        if out.stdout:
            return out.stdout
    except Exception:
        pass
    raise RuntimeError(f"html fetch failed [{type(last).__name__}: {last}] {url}")


def _text(h):
    """HTML -> collapsed visible text."""
    h = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", h)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", h)))


COVERS_URL = {"nfl": "https://www.covers.com/picks/nfl", "mlb": "https://www.covers.com/picks/mlb"}

# "Predicted Score  SF SF 21.62 @ 28.09 LA ... 49ers vs Rams ·"
# The projected scores come first with team ABBREVIATIONS, then the same matchup is
# repeated with full nicknames. Both are captured and the nicknames are what get matched:
# the abbreviations are ambiguous in exactly the place it matters (LA is both the Rams
# and the Chargers), and a mis-resolved abbreviation books a pick against another team's
# game rather than failing visibly.
COVERS_RE = re.compile(
    r"Predicted Score\s+\S+\s+\S+\s+(\d+\.\d+)\s*@?\s*\S*\s*(\d+\.\d+)\s+\S+"
    r".{0,140}?([A-Za-z0-9 .&'-]{3,28}?)\s+vs\s+([A-Za-z0-9 .&'-]{3,28}?)\s*[\u00b7]")


def fetch_covers(sport):
    """Covers / OddsShark computer picks — a projected score per game, turned into a pick."""
    url = COVERS_URL.get(sport)
    if not url:
        return []
    try:
        txt = _text(_get_html(url))
    except RuntimeError as e:
        print(f"  ! covers/{sport}: {str(e)[:80]}")
        _mark("covers", False, "picks page unreachable")
        return []

    _mark("covers", True)
    out = []
    for sa, sb, na, nb in COVERS_RE.findall(txt):
        try:
            sa, sb = float(sa), float(sb)
        except ValueError:
            continue
        if sa == sb:
            continue                      # a dead-level projection is not a pick
        a, b = na.strip(), nb.strip()
        # The nickname capture can pick up the trailing abbreviation of the block before
        # it ("LA 49ers"). canon() resolves that correctly, but trim it anyway so the
        # label the board prints is the team's actual name.
        a = re.sub(r"^[A-Z]{2,3}\s+(?=[A-Z0-9])", "", a)
        if len(a) < 2 or len(b) < 2:
            continue
        out.append(dict(a=a, b=b, pick="a" if sa > sb else "b", date=None,
                        detail=f"projected {sa:.1f}-{sb:.1f}"))
    return out


TENNIS_EXPLORER = "https://www.tennisexplorer.com/matches/"


def fetch_tennisexplorer(sport):
    """Tennis Explorer's per-match win probabilities.

    Its match table prints each player's forecast as a percentage pair. Anything that
    does not parse into a clean complementary pair is dropped rather than guessed.
    """
    if sport != "tennis":
        return []
    try:
        h = _get_html(TENNIS_EXPLORER)
    except RuntimeError as e:
        print(f"  ! tennisexplorer: {str(e)[:80]}")
        return []

    out = []
    # Rows pair up: the first row is player one, the row after it is the opponent.
    rows = re.findall(r"(?is)<tr[^>]*>(.*?)</tr>", h)
    pending = None
    for r in rows:
        name = re.search(r'(?is)<td class="t-name"[^>]*>\s*(?:<a[^>]*>)?([^<]{3,40})', r)
        prob = re.search(r'(?is)<td class="[^"]*course[^"]*"[^>]*>\s*([\d.]+)\s*</td>', r)
        if not name:
            continue
        nm = name.group(1).strip()
        pr = None
        if prob:
            try:
                pr = float(prob.group(1))
            except ValueError:
                pr = None
        if pending is None:
            pending = (nm, pr)
            continue
        a, pa = pending
        pending = None
        if pa and pr and pa > 1 and pr > 1:
            # Two decimal odds -> de-vigged probabilities.
            ia, ib = 1.0 / pa, 1.0 / pr
            ia, ib = devig(ia, ib)
            if ia:
                out.append(dict(a=a, b=nm, prob_a=ia, date=None))
    return out




# ---------------------------------------------------------------------------
# Kalshi as a VENUE — soccer, and whatever Polymarket does not list
# ---------------------------------------------------------------------------
#
# Polymarket prices and settles six of the seven sports. Where it cannot, Kalshi does the
# same job: all of soccer (Polymarket lists one or two soccer MATCHES a day, in leagues no
# tipster covers, against hundreds of futures) and any individual fight, match or game
# Polymarket is missing. Kalshi lists one yes/no market per outcome — each team, plus a
# Tie in soccer — and finalizes exactly one of them "yes".
KALSHI_API = "https://api.elections.kalshi.com/trade-api/v2/markets"

KALSHI_VENUE_SERIES = {
    "soccer": [
        # top flights tipsters cover most
        "KXEPLGAME", "KXLALIGAGAME", "KXBUNDESLIGAGAME", "KXSERIEAGAME", "KXLIGUE1GAME",
        "KXEREDIVISIEGAME", "KXLIGAPORTUGALGAME", "KXSCOTTISHPREMGAME", "KXBELGIANPLGAME",
        "KXSUPERLIGGAME", "KXSWISSLEAGUEGAME", "KXSLGREECEGAME", "KXDENSUPERLIGAGAME",
        "KXALLSVENSKANGAME", "KXELITESERIENGAME", "KXCZEFLGAME", "KXSRBSLGAME",
        "KXSVNPLGAME", "KXISRPLGAME", "KXSAUDIPLGAME", "KXUAEPLGAME", "KXEGYPLGAME",
        # second tiers
        "KXEFLCHAMPIONSHIPGAME", "KXEFLL1GAME", "KXBUNDESLIGA2GAME", "KXLIGUE2GAME",
        "KXLALIGA2GAME", "KXCZEFNLGAME", "KXSVK2LGAME", "KXISRNLGAME",
        # Americas
        "KXMLSGAME", "KXUSLGAME", "KXCANPLGAME", "KXLIGAMXGAME", "KXLIGAEXPGAME",
        "KXBRASILEIROGAME", "KXBRASILEIROBGAME", "KXBRASILEIROCGAME", "KXCHLLDPGAME",
        "KXPERLIGA1GAME", "KXURYPDGAME", "KXECULPGAME", "KXAPFDDHGAME",
        # Asia
        "KXJLEAGUEGAME", "KXKLEAGUEGAME", "KXK2LEAGUEGAME", "KXCHNSLGAME", "KXCHNL1GAME",
        "KXTHAIL1GAME", "KXMYSLGAME", "KXIDNSLGAME", "KXVLEAGUE1GAME", "KXSGPPLGAME",
        # smaller leagues
        "KXLVAVIRGAME", "KXFROPLGAME",
        # continental and domestic cups
        "KXUCLGAME", "KXUELGAME", "KXCONMEBOLSUDGAME", "KXCONMEBOLLIBGAME",
        "KXCONCACAFCCUPGAME", "KXAFCCLGAME", "KXEFLCUPGAME", "KXFACUPGAME",
        "KXCOPADELREYGAME", "KXCOPADOBRASILGAME", "KXSCOCUPGAME", "KXSVKCUPGAME",
        "KXUSOPENCUPGAME",
    ],
    "tennis": ["KXATPMATCH", "KXATPCHALLENGERMATCH", "KXWTAMATCH"],
    "table_tennis": ["KXTABLETENNIS", "KXTTMATCH", "KXTTELITEGAME", "KXWTTMATCH"],
    "boxing": ["KXBOXING"],
    # UFC bouts, and other promotions' MMA bouts. Verified 2026-09-12: KXUFCFIGHT carries
    # one event per bout with a staggered expected expiration 20 minutes apart.
    "mma": ["KXUFCFIGHT", "KXMMAFIGHT"],
    "cricket": ["KXCPLMATCH", "KXT20MATCH", "KXCRICKETT20IMATCH", "KXCRICKETODIMATCH"],
    "nfl": ["KXNFLGAME"],
    "mlb": ["KXMLBGAME"],
}

# A tip is priced at the YES ASK — what backing it would actually cost — and only where
# the book is tight. Kalshi carries untouched books quoted 0.02 bid / 0.81 ask; a mid of
# 0.415 on one of those is a number nobody could trade at, and T20 cricket is full of
# them.
# De-duplicated on purpose. A series listed twice would load every event's markets twice,
# the event would then appear to have four teams, and it would be skipped without a word.
KALSHI_VENUE_SERIES = {k: list(dict.fromkeys(v)) for k, v in KALSHI_VENUE_SERIES.items()}

KALSHI_MAX_SPREAD = 0.10
KALSHI_FINAL = {"finalized", "settled", "determined"}

_kalshi_open_cache = {}


def _kalshi_open(series):
    """Every open market in one Kalshi series, cursor-paginated, cached per run."""
    if series in _kalshi_open_cache:
        return _kalshi_open_cache[series]
    out, cursor = [], ""
    for _ in range(10):
        url = f"{KALSHI_API}?limit=200&status=open&series_ticker={series}"
        if cursor:
            url += f"&cursor={cursor}"
        try:
            d = _get(url, tries=2, timeout=30)
        except RuntimeError:
            break
        batch = d.get("markets") or []
        out += batch
        cursor = d.get("cursor") or ""
        if not cursor or not batch:
            break
    _kalshi_open_cache[series] = out
    return out


def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _kalshi_code(m):
    return str(m.get("ticker", "")).rsplit("-", 1)[-1]


def _kalshi_is_tie(m):
    return (_kalshi_code(m).upper() == "TIE"
            or str(m.get("yes_sub_title", "")).strip().lower().endswith("tie"))


def _kalshi_name(m):
    # Some cup series prefix every outcome "Reg Time: " — the market settles on 90
    # minutes. The prefix is not part of the club's name.
    return str(m.get("yes_sub_title") or "").replace("Reg Time:", "").strip()


def kalshi_sides(event_ticker, markets):
    """{market code: 'a' | 'b' | 'draw'} for one Kalshi event.

    Side A is the home team: the team code the event suffix STARTS with once the date —
    and, for MLB and cricket, a four-digit start time — is stripped, so
    KXEPLGAME-26SEP06ARSCFC is Arsenal at home. Codes run two to six characters, so the
    suffix can never be split by length. Fetch and settlement both call this one
    function, which is what guarantees a bet placed on side A is settled against the
    same team it was placed on.
    """
    suffix = str(event_ticker).rsplit("-", 1)[-1]
    body = re.sub(r"^\d{2}[A-Z]{3}\d{2}(\d{4})?", "", suffix)
    out = {_kalshi_code(m): "draw" for m in markets if _kalshi_is_tie(m)}
    teams = [_kalshi_code(m) for m in markets if not _kalshi_is_tie(m)]
    if len(teams) != 2:
        return out
    home = [c for c in teams if body.startswith(c)]
    a = home[0] if len(home) == 1 else sorted(teams)[0]
    b = teams[1] if teams[0] == a else teams[0]
    out[a], out[b] = "a", "b"
    return out


def fetch_kalshi_venue(sport, horizon_days=4, cap=800, stats=None):
    """Kalshi contests for one sport, as universe rows with Kalshi as the venue.

    The cap is generous on purpose. A Kalshi-venue row adds nothing to the ledger by
    itself — no self-quote is logged against it — so a wide universe costs nothing but
    matching time, while a narrow one silently discards every tip on a fixture it cut.
    """
    now = datetime.now(timezone.utc)
    first = now.strftime("%Y-%m-%d")
    last = (now + timedelta(days=horizon_days)).strftime("%Y-%m-%d")
    # Fetched concurrently. Soccer alone is 69 series, and one after another they took
    # nearly five minutes of a run whose CPU time was under two seconds. Six workers stays
    # well inside Kalshi's public read limits.
    series_list = KALSHI_VENUE_SERIES.get(sport) or []
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        fetched = dict(zip(series_list, pool.map(_kalshi_open, series_list)))
    events = {}
    for series in series_list:
        for m in fetched[series]:
            events.setdefault((series, m.get("event_ticker")), []).append(m)

    rows, listed = [], 0
    for (series, et), ms in events.items():
        date = kalshi_date(et)
        if not (first <= date <= last):
            continue
        sides = kalshi_sides(et, ms)
        by_side = {sides[_kalshi_code(m)]: m for m in ms if _kalshi_code(m) in sides}
        if "a" not in by_side or "b" not in by_side:
            continue
        three_way = sport == "soccer"
        if three_way and "draw" not in by_side:
            continue
        listed += 1

        # Kalshi publishes no kickoff time. Expected expiration sits two to three hours
        # after the start, so three hours before it is a deliberately EARLY estimate:
        # logging stops before the real kickoff, never after it.
        try:
            end = datetime.fromisoformat(
                str(ms[0].get("expected_expiration_time")).replace("Z", "+00:00"))
        except (ValueError, TypeError):
            continue
        start = end - timedelta(hours=3)
        # Fight cards: the 3h-early estimate lands hours before the later bouts, so a
        # passed estimate is kept while the market is open and re-timed from Pinnacle.
        early = (now - timedelta(hours=FIGHT_LOOKBACK_H) if sport in START_FROM_PINNACLE
                 else now - timedelta(minutes=5))
        if start < early:
            continue

        prices, tradeable = {}, {}
        for side, m in by_side.items():
            bid, ask = _num(m.get("yes_bid_dollars")), _num(m.get("yes_ask_dollars"))
            prices[side] = ask
            tradeable[side] = bool(bid is not None and ask is not None and bid > 0
                                   and ask < 1 and ask - bid <= KALSHI_MAX_SPREAD)
        if not prices.get("a") or not prices.get("b"):
            continue

        rows.append(dict(
            sport=sport, venue="kalshi", market_id=et,
            label=f"{_kalshi_name(by_side['a'])} vs {_kalshi_name(by_side['b'])}",
            side_a=_kalshi_name(by_side["a"]), side_b=_kalshi_name(by_side["b"]),
            price_a=prices["a"], price_b=prices["b"],
            price_draw=prices.get("draw") if three_way else None,
            tradeable=tradeable, untraded=not any(tradeable.values()),
            start=start.isoformat(), date=date, volume=0.0,
            url=f"https://kalshi.com/markets/{series.lower()}",
        ))

    rows.sort(key=lambda r: r["start"])
    if stats is not None:
        stats["listed"] = listed
        stats["priced"] = sum(1 for r in rows if not r["untraded"])
    return rows[:cap] if cap else rows


def resolve_kalshi(event_ticker):
    """Settlement oracle for a Kalshi event: 'a', 'b', 'draw', 'void', or None if open.

    The winning side is read through kalshi_sides — the same mapping used when the bet
    was placed — so side A can never quietly change meaning between placing and settling.
    """
    try:
        ms = _get(f"{KALSHI_API}?event_ticker={event_ticker}&limit=20",
                  tries=2, timeout=30).get("markets") or []
    except RuntimeError:
        return None
    if not ms:
        return None
    sides = kalshi_sides(event_ticker, ms)
    yes = [m for m in ms if str(m.get("result")).lower() == "yes"]
    if yes:
        if any(str(m.get("status")).lower() not in KALSHI_FINAL for m in yes):
            return None
        if len(yes) != 1:
            return "void"
        return sides.get(_kalshi_code(yes[0])) or "void"
    if all(str(m.get("status")).lower() in KALSHI_FINAL for m in ms):
        # Everything final and nothing resolved yes: cancelled or voided. Refund it.
        return "void"
    return None


# ---------------------------------------------------------------------------
# Scores24 (behind Cloudflare — needs the headless browser)
# ---------------------------------------------------------------------------

# Every sport this board tracks gets a listing page requested, including the ones that
# turned out to be empty. Scores24 publishes editorial tips per sport, but which sports
# it bothers with moves with the calendar — boxing has nothing on an ordinary Tuesday and
# may well have tips on a fight week. Asking for all six costs one page load each and
# lets the coverage table report an honest zero instead of an omission.
# Verified live: Scores24's cricket, boxing and table-tennis listing pages contain only
# a generic cross-sport rail, no tips of their own. Requesting them cost a page load and
# a Cloudflare challenge each to learn nothing, so they are not requested. Their absence
# is recorded in this source's `sports` list rather than as a nightly empty fetch.
SCORES24_SLUG = {"soccer": "soccer", "tennis": "tennis",
                 "nfl": "american-football", "mlb": "baseball"}
SCORES24_URL = "https://scores24.live/en/predictions/{slug}"


_browser_cache = None


def _browser_pages():
    """Every browser-fetched page, in ONE session, once per process.

    Both Cloudflare-protected sources are scraped together. Two sessions meant two
    browser launches and two sets of challenges for the same wall clock budget, and this
    step is already the slowest thing in the run.
    """
    global _browser_cache
    if _browser_cache is not None:
        return _browser_cache
    import sandbox_browser as B
    # Oddspedia first, and paced. It tolerates roughly one page before it starts serving
    # the interstitial, so whichever of its pages goes last tends to be lost — and its
    # soccer tips are the ones worth protecting, since soccer is where tipsters actually
    # publish. Scores24 is far more tolerant and goes at the back of the queue.
    jobs = ([(ODDSPEDIA_URL.format(slug=s), B.TIPS_JS) for s in ODDSPEDIA_SLUG.values()]
            + [(SCORES24_URL.format(slug=s), B.ROW_JS) for s in SCORES24_SLUG.values()])
    _browser_cache = B.fetch_rows(jobs, pace_ms=6000)
    return _browser_cache


_scores24_cache = None


def _scores24_all():
    """Scrape every sport's listing ONCE per process and cache the result.

    fetch_scores24 is called per sport, but launching a browser six times would pay the
    Cloudflare challenge six times over. One session, one pass, cached.
    """
    global _scores24_cache
    if _scores24_cache is not None:
        return _scores24_cache

    import sandbox_browser as B
    pages = _browser_pages()
    urls = {sport: SCORES24_URL.format(slug=slug) for sport, slug in SCORES24_SLUG.items()}
    _mark_urls("scores24", urls.values())
    _scores24_cache = {}
    for sport, url in urls.items():
        picks = []
        for row in pages.get(url) or []:
            got = B.parse_row(row, SCORES24_SLUG[sport])
            if got:
                picks.append(got)
        _scores24_cache[sport] = picks
    return _scores24_cache


def fetch_scores24(sport):
    """Scores24's published match-winner tips for one sport."""
    if sport not in SCORES24_SLUG:
        return []
    return _scores24_all().get(sport, [])



# ---------------------------------------------------------------------------
# Oddspedia community tips (behind Cloudflare — needs the headless browser)
# ---------------------------------------------------------------------------

# Oddspedia runs a public tipster community: named accounts with a visible tip count and
# running ROI, posting a selection per match. It is the one source found that covers the
# NICHE cricket Polymarket actually lists — European Cricket League sides like Dublin
# Guardians and Belfast Wolves, not just Test nations.
# Cricket only. Oddspedia's community covers the niche cricket nothing else touches, but
# its other sports were empty or duplicated a source already connected — and every extra
# page in one session makes the whole batch more likely to be challenged. Its table
# tennis page was checked repeatedly and carries no tips at all.
# Cricket only, and that is a hard limit rather than a preference: Oddspedia serves
# roughly ONE page per browser session before it starts returning the interstitial —
# reordering and pacing to 6s did not move it. Cricket is the page worth spending that
# single request on, because it is the only source found anywhere that tips the niche
# cricket Polymarket lists. Soccer tips come from Scores24 instead.
ODDSPEDIA_SLUG = {"cricket": "cricket"}
ODDSPEDIA_URL = "https://oddspedia.com/{slug}/tips"

_oddspedia_cache = None


def _oddspedia_all():
    """Scrape every sport's community tips ONCE per process, reduced to a consensus."""
    global _oddspedia_cache
    if _oddspedia_cache is not None:
        return _oddspedia_cache

    import sandbox_browser as B
    pages = _browser_pages()
    urls = {sp: ODDSPEDIA_URL.format(slug=slug) for sp, slug in ODDSPEDIA_SLUG.items()}
    _mark_urls("oddspedia", urls.values())
    _oddspedia_cache = {}
    for sport, url in urls.items():
        tips = [t for t in (B.parse_tip(r) for r in (pages.get(url) or [])) if t]
        _oddspedia_cache[sport] = consensus(tips)
    return _oddspedia_cache


def consensus(tips):
    """Reduce many individual tips to one call per contest.

    Community tipsters contradict each other constantly — on the live cricket page two
    of them had opposite sides of Belfast Wolves vs Amsterdam Flames. Logging both would
    let "Oddspedia" be simultaneously right and wrong about the same match and guarantee
    a ~0% ROI that measured nothing. So the community votes: the majority side is the
    call, and an even split is no call at all rather than a coin flip.
    """
    groups = {}
    for t in tips:
        key = frozenset({frozenset(tokens(t["a"])), frozenset(tokens(t["b"]))})
        g = groups.setdefault(key, dict(a=t["a"], b=t["b"], a_votes=0, b_votes=0,
                                        tipsters=[]))
        # Orient every tip to the FIRST spelling of the fixture seen, since a later
        # tipster may list the same match the other way round.
        flip = sim(t["a"], g["a"]) < sim(t["a"], g["b"])
        side = t["pick"]
        if flip:
            side = "b" if side == "a" else "a"
        g[f"{side}_votes"] += 1
        if t.get("tipster"):
            g["tipsters"].append(t["tipster"])

    out = []
    for g in groups.values():
        if g["a_votes"] == g["b_votes"]:
            continue
        pick = "a" if g["a_votes"] > g["b_votes"] else "b"
        n = g["a_votes"] + g["b_votes"]
        out.append(dict(a=g["a"], b=g["b"], pick=pick, date=None,
                        detail=f"{max(g['a_votes'], g['b_votes'])}/{n} tipsters"
                               + (f" ({', '.join(g['tipsters'][:3])})" if g["tipsters"] else "")))
    return out


def fetch_oddspedia(sport):
    """Oddspedia's community consensus for one sport."""
    if sport not in ODDSPEDIA_SLUG:
        return []
    return _oddspedia_all().get(sport, [])


# ---------------------------------------------------------------------------
# SportsGambler — football match predictions (plain HTTP)
# ---------------------------------------------------------------------------
#
# Every match page carries one "Main Match Prediction" from a named analyst. Only its
# To Win and Draw calls are scored. That is roughly one tip in six: the rest are
# over/unders, Asian handicaps and both-teams-to-score, which settle a different question
# than the result market they would be priced against.
#
# Football only. Its tennis, table-tennis, cricket and boxing pages were checked and are
# not tips at all — they restate the bookmaker line as prose ("odds of -192 that Jorgic
# lands victory"). Scoring those would only ever measure the favourite.
SPORTSGAMBLER = "https://www.sportsgambler.com"
# Only leagues Kalshi prices: a tip on a fixture with no price cannot be scored.
SPORTSGAMBLER_LEAGUES = [
    "premier-league", "la-liga", "bundesliga", "serie-a", "ligue-1", "eredivisie",
    "primeira-liga", "scottish-premiership", "belgium-first-division-a", "super-lig",
    "swiss-super-league", "greece-super-league-1", "denmark-superliga", "allsvenskan",
    "eliteserien", "championship", "league-one", "2-bundesliga", "la-liga-2", "mls",
    "liga-mx", "brazil-serie-a", "brazil-serie-b", "peru-liga-1", "j1-league",
    "k-league-1", "chinese-super-league", "uefa-champions-league", "europa-league",
    "copa-sudamericana", "copa-libertadores", "afc-champions-league", "efl-cup",
    "fa-cup", "copa-del-rey", "copa-do-brasil",
]
SPORTSGAMBLER_MAX_PAGES = 50        # ~1 request a second; this is the slowest source
SG_MATCH_RE = re.compile(
    r'href="(?:https://www\.sportsgambler\.com)?'
    r'(/betting-tips/football/[a-z0-9\-]+-vs-[a-z0-9\-]+-(\d{4}-\d{2}-\d{2})/)"')

_sportsgambler_cache = None

# Set by the tracker before publishing: {sport: universe rows}. None when run standalone.
UNIVERSE = None
SG_SLUG_RE = re.compile(r"/football/(.+?)-vs-(.+?)-prediction")


def sportsgambler_priced(links, rows):
    """Keep only match pages whose fixture a venue actually prices.

    Every SportsGambler tip costs a page load and a polite second, and most of its 36
    league pages list fixtures Kalshi does not carry. A tip on one of those can never be
    scored, so fetching it is pure waiting. The home and away teams are in the URL slug,
    which is enough to check against the universe before spending the request.

    rows=None means no universe is known (a standalone run) and nothing is filtered.
    """
    if rows is None:
        return links
    out = []
    for path, d in links:
        m = SG_SLUG_RE.search(path)
        if not m:
            continue
        home, away = m.group(1).replace("-", " "), m.group(2).replace("-", " ")
        for r in rows:
            try:
                gap = abs((datetime.strptime(r["date"], "%Y-%m-%d")
                           - datetime.strptime(d, "%Y-%m-%d")).days)
            except (ValueError, TypeError):
                continue
            if gap <= 1 and pair_match(r["side_a"], r["side_b"], home, away,
                                       sport="soccer")[0] > 0:
                out.append((path, d))
                break
    return out


def parse_sportsgambler(page):
    """A match page -> {a, b, pick, detail} from its MAIN prediction, or None."""
    head = re.search(r"<h2>\s*([^<]+?)\s+vs\s+([^<]+?)\s+Predictions\s*</h2>", page)
    tip = re.search(r'Main Match Prediction</span>.*?<h3 class="tip--card__title">(.*?)</h3>',
                    page, re.S)
    if not head or not tip:
        return None
    a = html.unescape(head.group(1)).strip()
    b = html.unescape(head.group(2)).strip()
    text = " ".join(html.unescape(re.sub(r"<[^>]+>", " ", tip.group(1))).split())

    if re.match(r"^Draw\s*@", text, re.I):
        return dict(a=a, b=b, pick="draw", detail=text)
    # "@" straight after "To Win" — so "Arsenal To Win & Over 2.5 @" is rejected too.
    m = re.match(r"^(.+?)\s+To Win\s*@", text, re.I)
    if not m:
        return None
    team = m.group(1).strip()
    sa, sb = _score(team, a, "soccer"), _score(team, b, "soccer")
    if max(sa, sb) < 0.5 or sa == sb:
        return None
    return dict(a=a, b=b, pick="a" if sa > sb else "b", detail=text)


def _sportsgambler_all():
    global _sportsgambler_cache
    if _sportsgambler_cache is not None:
        return _sportsgambler_cache
    now = datetime.now(timezone.utc)
    days = {(now + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(5)}

    links, seen, loaded = [], set(), 0
    for league in SPORTSGAMBLER_LEAGUES:
        try:
            index = _get_html(f"{SPORTSGAMBLER}/betting-tips/football/{league}-predictions/")
        except RuntimeError as e:
            print(f"  ! sportsgambler/{league}: {str(e)[:80]}")
            continue
        loaded += 1
        for path, d in SG_MATCH_RE.findall(index):
            if d in days and path not in seen:
                seen.add(path)
                links.append((path, d))
        time.sleep(0.6)

    _mark("sportsgambler", loaded > 0, "no league page loaded")
    rows = (UNIVERSE or {}).get("soccer") if UNIVERSE is not None else None
    priced = sportsgambler_priced(links, rows)
    todo = sorted(priced, key=lambda x: x[1])[:SPORTSGAMBLER_MAX_PAGES]
    print(f"  sportsgambler: {len(links)} fixtures in horizon, {len(priced)} priced, "
          f"fetching {len(todo)}")
    out = []
    for path, d in todo:
        try:
            page = _get_html(SPORTSGAMBLER + path)
        except RuntimeError:
            continue
        got = parse_sportsgambler(page)
        if got:
            got["date"] = d
            out.append(got)
        time.sleep(0.6)
    _sportsgambler_cache = out
    return out


def fetch_sportsgambler(sport):
    return _sportsgambler_all() if sport == "soccer" else []


# ---------------------------------------------------------------------------
# SoccerPredictions.ai (plain HTTP)
# ---------------------------------------------------------------------------
SOCCERPREDICTIONS_URLS = ["https://soccerpredictions.ai/soccer-predictions/",
                          "https://soccerpredictions.ai/"]
SP_LINK_RE = re.compile(
    r'<a href="(https://soccerpredictions\.ai/[^"]+-prediction-date-(\d{4}-\d{2}-\d{2}))"'
    r'[^>]*>(.*?)</a>', re.S)
# Only the plain result calls. "Home & Over 2.5" is a different, combined bet.
SP_PICK = {"home": "a", "away": "b", "draw": "draw"}

_soccerpredictions_cache = None


def parse_soccerpredictions(page):
    """Listing page -> [{a, b, pick, date, detail}] for plain Home / Away / Draw tips.

    Each row is parsed inside its own <a>…</a>, so a malformed row can never borrow the
    team names of the row after it.
    """
    out, seen = [], set()
    for url, d, inner in SP_LINK_RE.findall(page):
        names = re.findall(r'tipscell__text__name">([^<]+)<', inner)
        tip = re.search(r'tipscell--score"><div class="tipscell__text fw-500"><span>([^<]+)</span>',
                        inner)
        if len(names) != 2 or not tip or url in seen:
            continue
        pick = SP_PICK.get(" ".join(tip.group(1).split()).lower())
        if not pick:
            continue
        seen.add(url)
        out.append(dict(a=html.unescape(names[0]).strip(), b=html.unescape(names[1]).strip(),
                        pick=pick, date=d, detail=tip.group(1).strip()))
    return out


def fetch_soccerpredictions(sport):
    global _soccerpredictions_cache
    if sport != "soccer":
        return []
    if _soccerpredictions_cache is None:
        rows, seen, loaded = [], set(), 0
        for url in SOCCERPREDICTIONS_URLS:
            try:
                page = _get_html(url, timeout=25)
            except RuntimeError as e:
                print(f"  ! soccerpredictions: {str(e)[:80]}")
                continue
            loaded += 1
            for r in parse_soccerpredictions(page):
                key = (r["a"], r["b"], r["date"])
                if key not in seen:
                    seen.add(key)
                    rows.append(r)
        _mark("soccerpredictions", loaded > 0, "site unreachable")
        _soccerpredictions_cache = rows
    return _soccerpredictions_cache


# ---------------------------------------------------------------------------
# Non-sport markets: one row per yes/no contract
# ---------------------------------------------------------------------------
#
# A sports contest has two named sides. A Kalshi question does not — it is a single
# yes/no contract ("Will the maximum temperature be 77-78° on Sep 12?"), so each market
# becomes its own contest: side A is the outcome happening, side B is it not happening,
# each priced at its own ask.
#
# Series are chosen by Kalshi's own `frequency` field. Daily ones are what make this
# worth tracking: they settle overnight, so a forecaster reaches a readable sample in a
# week where the soccer tipsters need months. Politics and Elections are deliberately
# absent here — Kalshi lists 2,335 political series and 4 of them are daily; the rest
# are one-off questions resolving months out, and nothing would settle inside a horizon
# this board can measure.
# Kalshi city series -> the point the NWS forecast is taken from (the airport the market
# settles on, not the city centre: Kalshi settles NY on Central Park, LAX on the airport).
NWS_CITIES = {
    "KXHIGHNY": (40.7790, -73.9692), "KXHIGHCHI": (41.7860, -87.7524),
    "KXHIGHMIA": (25.7884, -80.3167), "KXHIGHAUS": (30.1830, -97.6800),
    "KXHIGHDEN": (39.8466, -104.6562), "KXHIGHLAX": (33.9382, -118.3866),
    "KXHIGHPHIL": (39.8683, -75.2311),
}

# Kalshi soccer GAME series -> the board's league name. A Production lead carries the board's
# league name, so a reader of the feed can find the same Kalshi market from it.
KALSHI_GAME_LEAGUES = {
    "KXEPLGAME": "Premier League", "KXLALIGAGAME": "La Liga", "KXSERIEAGAME": "Serie A",
    "KXBUNDESLIGAGAME": "Bundesliga", "KXLIGUE1GAME": "Ligue 1",
    "KXUCLGAME": "Champions League", "KXUELGAME": "Europa League", "KXMLSGAME": "MLS",
    "KXEREDIVISIEGAME": "Eredivisie", "KXLIGAPORTUGALGAME": "Primeira Liga",
    "KXSAUDIPLGAME": "Saudi Pro League", "KXSCOTTISHPREMGAME": "Scottish Premiership",
    "KXBRASILEIROGAME": "Brasileirão",
}


def quote_league(q):
    """The board league name for a Kalshi soccer quote, or None."""
    if q.get("venue") == "kalshi":
        return KALSHI_GAME_LEAGUES.get(str(q.get("market_id") or "").split("-")[0])
    if q.get("venue") == "kalshi_binary" and q.get("sport") in GOALS_SPORTS:
        return q.get("league") if q.get("league") in KALSHI_GAME_LEAGUES.values() else None
    return None


# The rest of Kalshi's soccer series, for naming a competition when the board has no league
# name for it — a tipster's lead can land on the Swiss Super League or the Scottish Cup, and
# filing those under "other" would hide a whole competition's record. The names are the
# venue's OWN series titles, read from its /series endpoint on 2026-09-22 rather than guessed
# from the ticker, so a competition is named the way the exchange names it. DISPLAY ONLY:
# unlike KALSHI_GAME_LEAGUES these never reach a Production lead.
SERIES_LEAGUES = {
    "KXEFLCHAMPIONSHIPGAME": "EFL Championship", "KXLALIGA2GAME": "LaLiga 2",
    "KXSWISSLEAGUEGAME": "Swiss Super League", "KXEFLL1GAME": "EFL League One",
    "KXBUNDESLIGA2GAME": "Bundesliga 2", "KXBELGIANPLGAME": "Belgian Pro League",
    "KXBRASILEIROBGAME": "Brasileiro Serie B", "KXSUPERLIGGAME": "Turkish Super Lig",
    "KXALLSVENSKANGAME": "Allsvenskan", "KXPERLIGA1GAME": "Peru Liga 1",
    "KXLIGAMXGAME": "Liga MX", "KXKLEAGUEGAME": "Korea K League",
    "KXK2LEAGUEGAME": "Korea K-League 2", "KXJLEAGUEGAME": "Japan J League",
    "KXELITESERIENGAME": "Eliteserien", "KXCONMEBOLLIBGAME": "CONMEBOL Libertadores",
    "KXSVK2LGAME": "Slovakian 2. Liga", "KXTHAIL1GAME": "Thai League 1",
    "KXSCOCUPGAME": "Scottish Cup", "KXECULPGAME": "Ecuador Liga Pro",
    "KXAFCCLGAME": "AFC Champions League", "KXEGYPLGAME": "Egyptian Premier League",
    "KXCONMEBOLSUDGAME": "CONMEBOL Sudamericana", "KXFROPLGAME": "Faroe Islands Premier League",
    "KXUELBTTS": "Europa League", "KXEFLCUPGAME": "EFL Cup",
}


def market_url(q):
    """Where to send a reader to see THIS contest — not the series it belongs to.

    Every Kalshi row has been logged with the SERIES page as its link
    (kalshi.com/markets/kxserieatotal), which opens on whatever event that series happens to
    list first. So a link on a Torino v Roma bet led to somebody else's match, and a reader
    checking the record against the venue was checking the wrong game.

    Kalshi routes an event by its ticker in the fragment and needs no slug, so the link is
    derived from the row's own market id rather than stored: the id IS the event ticker on a
    game market, and on a yes/no market the event is the id without its strike
    (KXEPLTOTAL-26SEP15GOALEA-2 -> KXEPLTOTAL-26SEP15GOALEA). Derived at render time on
    purpose — that repairs every row already in the ledger without rewriting one of them.
    """
    venue, mid = q.get("venue"), str(q.get("market_id") or "")
    if venue not in ("kalshi", "kalshi_binary") or "-" not in mid:
        return q.get("url") or ""
    event = mid.rsplit("-", 1)[0] if venue == "kalshi_binary" and mid.count("-") >= 2 else mid
    return f"https://kalshi.com/markets/{mid.split('-')[0].lower()}#{event.lower()}"


def display_league(q):
    """The competition a quote belongs to, for grouping a record by league — None if unknown.

    The board's own league name first, so a Kalshi row and an ESPN row for the same
    competition land in the same group and are not split into two.
    """
    return (q.get("league") or quote_league(q)
            or SERIES_LEAGUES.get(str(q.get("market_id") or "").split("-")[0]))


NWS_CITY_NAMES = {"KXHIGHNY": "New York", "KXHIGHCHI": "Chicago", "KXHIGHMIA": "Miami",
                  "KXHIGHAUS": "Austin", "KXHIGHDEN": "Denver", "KXHIGHLAX": "Los Angeles",
                  "KXHIGHPHIL": "Philadelphia"}


def display_label(q):
    """A quote's label, with the city added to a weather market's. Kalshi titles every city's
    bucket identically ("Will the maximum temperature be 80-81° on Sep 13?"), so New York and
    Los Angeles read as the same market. Applied at render, so old ledger rows get it too."""
    label = str(q.get("label") or "")
    city = NWS_CITY_NAMES.get(str(q.get("market_id") or "").split("-")[0])
    return f"{city}: {label}" if city and not label.startswith(city) else label


def outcome_cluster(q):
    """Quotes that cannot all win together share a cluster. A Kalshi yes/no ladder (one
    series, one day) is a set of mutually exclusive buckets — at most one can land — so two
    bets on New York's high for Sep 13 are one draw of the weather, not two."""
    # Not the soccer goals markets: both sides of a team total can land, and one over-1.5
    # market is the whole event.
    if q.get("venue") == "kalshi_binary" and q.get("market_id") and q.get("sport") not in GOALS_SPORTS:
        return str(q["market_id"]).rsplit("-", 1)[0]
    return q.get("id") or ("row", id(q))          # no id: every quote is its own outcome


# ELIMINATED (2026-09-21): pairs that fail in EVERY direction — their picks lose after fees
# AND backing the other side of the same bets loses too. That is the exact signature of a
# pair carrying no information: with no skill, both sides of a book lose, because the spread
# is paid whichever way you face. A retired pair still sits in its sport; an eliminated one is
# moved out of the sport sections entirely, into its own collapsed list at the bottom. Its
# bets stay on record and in the page's reconciliation — out of sight, never out of the count.
ELIMINATED = {("scores24", "mlb"), ("scores24", "tennis"), ("polymarket", "tennis"), ("draftkings", "mlb")}


# Sports judged per MARKET-DAY rather than per bet. A commodity ladder's "above $X" rungs
# all land together, and the 22 state gas-price series move with one national price, so a
# day of gas bets is ONE result, not 222 (2026-09-19: the first gas day would otherwise have
# read "220-2, proven edge" off a single quiet night).
DAY_CLUSTERED = ("commodities", "soccer_corners")


def market_day(q):
    """'KXAAAGASD|20260919' — every state's gas series on one day share a key."""
    series = str(q.get("market_id") or "").split("-")[0]
    if q.get("sport") == "soccer_corners":
        # Every total- and team-corner rung of one match is one result (per MATCH, not per day).
        code = (str(q.get("market_id") or "").split("-") + ["", ""])[1]
        return f"CORNERS|{code}"
    fam = "KXAAAGASD" if series.startswith("KXAAAGASD") else series
    return f"{fam}|{str(q.get('date') or '').replace('-', '')}"


# Kalshi daily coin series -> CoinGecko id.
COINS = {"BTCD": "bitcoin", "ETHD": "ethereum", "KXSOLD": "solana",
         "KXLINKD": "chainlink", "KXXRP": "ripple", "KXXLM": "stellar",
         "KXZECD": "zcash", "KXNEAR": "near", "KXHYPED": "hyperliquid"}

# Where a forecaster exists, the series are named explicitly rather than taken from the
# category. Selecting a whole category and then capping by soonest expiry starved the
# markets that can actually be scored: the climate cap filled with overnight-low markets
# and the crypto cap with Shiba Inu strikes, and both forecasters produced nothing. The
# tracked-only domains still take a category slice, since nothing prices them yet.
KALSHI_BINARY = {
    "climate":     dict(series=list(NWS_CITIES), lead_h=12, cap=80),
    "crypto":      dict(series=list(COINS), lead_h=2, cap=60),
    "economics":   dict(category="Economics",   freq=("daily",), lead_h=6, cap=30),
    # Seven commodity ladders a day (WTI, Brent, gold, silver, copper, natural gas, retail
    # gasoline), each 20-65 strikes: take the soonest ladder of each, not 80 of the first.
    # The 21 STATE gasoline series are dropped (2026-09-21). They move with the national
    # average, only the retired far-tail rule ever used them, and at ~17 strikes each they
    # filled the 400 cap before gold, silver, copper, natural gas or Brent could enter —
    # and could one day have pushed out the national ladder the gas rule depends on.
    "commodities": dict(category="Commodities", freq=("daily",), lead_h=6, cap=400,
                        ladders_per_series=1, drop_series=r"^KXAAAGASD[A-Z]{2}$"),
    "finance":     dict(category="Financials",  freq=("daily",), lead_h=6, cap=30),
}

_series_cache = {}


def kalshi_series(category, freqs):
    """Tickers in one Kalshi category at the given frequencies."""
    key = (category, freqs)
    if key in _series_cache:
        return _series_cache[key]
    try:
        ser = _get("https://api.elections.kalshi.com/trade-api/v2/series?category="
                   + urllib.parse.quote(category), tries=2, timeout=30).get("series") or []
    except RuntimeError:
        ser = []
    _series_cache[key] = [s["ticker"] for s in ser if str(s.get("frequency")) in freqs]
    return _series_cache[key]


def market_range(m):
    """(low, high) the market pays out on; None on either side means unbounded."""
    lo, hi = _num(m.get("floor_strike")), _num(m.get("cap_strike"))
    kind = str(m.get("strike_type"))
    if kind == "greater":
        return (lo, None)
    if kind == "less":
        return (None, hi)
    if kind == "between":
        return (lo, hi)
    return (None, None) if lo is None and hi is None else (lo, hi)


def in_range(value, m):
    """Would a reading of `value` settle this market YES?

    The boundaries are not uniform, and reading them wrongly is how a forecast silently
    matches nothing. Kalshi's own wording is the spec: a "between" market titled
    "77° to 78°" INCLUDES 77 and 78; a "greater" market with floor 82 is titled "83° or
    above", so 82 does not count; a "less" market with cap 75 is "74° or below", so 75
    does not count. Treating every floor as exclusive dropped New York, Chicago and LA
    on the days their forecast landed exactly on a bucket edge.
    """
    kind = str(m.get("strike_type"))
    lo, hi = _num(m.get("floor_strike")), _num(m.get("cap_strike"))
    if kind == "greater":
        return lo is not None and value > lo
    if kind == "less":
        return hi is not None and value < hi
    if kind == "between":
        return (lo is None or value >= lo) and (hi is None or value <= hi)
    return None


def fetch_kalshi_binary(domain, horizon_days=4, stats=None):
    """Every near-dated yes/no market in one domain, as universe rows.

    `lead_h` is an integrity rule, not tuning. A daily high-temperature market that
    expires in two hours has already effectively happened — the afternoon peak is in —
    and a forecast logged against it would be scored on something already known. Each
    domain therefore only accepts markets with real uncertainty still left in them.
    """
    cfg = KALSHI_BINARY.get(domain)
    if not cfg:
        return []
    now = datetime.now(timezone.utc)
    horizon = now + timedelta(days=horizon_days)
    earliest = now + timedelta(hours=cfg["lead_h"])
    series = cfg.get("series") or kalshi_series(cfg["category"], cfg["freq"])
    if cfg.get("drop_series"):
        series = [x for x in series if not re.match(cfg["drop_series"], x)]

    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        fetched = dict(zip(series, pool.map(_kalshi_open, series)))

    rows, listed = [], 0
    for s in series:
        for m in fetched.get(s) or []:
            try:
                exp = datetime.fromisoformat(
                    str(m.get("expected_expiration_time")).replace("Z", "+00:00"))
            except (ValueError, TypeError):
                continue
            if not (earliest <= exp <= horizon):
                continue
            listed += 1
            ya, yb = _num(m.get("yes_ask_dollars")), _num(m.get("yes_bid_dollars"))
            na, nb = _num(m.get("no_ask_dollars")), _num(m.get("no_bid_dollars"))
            if ya is None or na is None:
                continue
            tight = lambda bid, ask: bool(bid is not None and ask is not None and bid > 0
                                          and ask < 1 and ask - bid <= KALSHI_MAX_SPREAD)
            tradeable = {"a": tight(yb, ya), "b": tight(nb, na)}
            rows.append(dict(
                sport=domain, venue="kalshi_binary", market_id=m["ticker"],
                label=display_label(dict(label=str(m.get("title") or m["ticker"])[:90],
                                         market_id=m["ticker"])),
                side_a=str(m.get("yes_sub_title") or "Yes"), side_b="No",
                price_a=ya, price_b=na, price_draw=None,
                tradeable=tradeable, untraded=not any(tradeable.values()),
                start=exp.isoformat(), date=exp.strftime("%Y-%m-%d"), volume=0.0,
                series=s, market=m,
                url=f"https://kalshi.com/markets/{s.lower()}"))

    rows.sort(key=lambda r: r["start"])
    # Cap whole ladders, never part of one. A yes/no series is a set of mutually
    # exclusive buckets, and slicing it mid-ladder can remove exactly the bucket a
    # forecast lands in — which silently dropped four of the seven weather cities while
    # looking like the forecaster simply had no opinion.
    groups, order = {}, []
    for r in rows:
        key = (r["series"], r["date"])
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(r)
    # A flat cap taken in expiry order hands the whole allowance to whichever series closes
    # first: commodities has seven ladders a day, WTI closes at 18:30 and the rest at 21:00,
    # so an 80-market cap logged WTI and nothing else. `ladders_per_series` keeps the soonest
    # ladders of EACH series instead, so every commodity is actually measured.
    per_series = cfg.get("ladders_per_series")
    kept, taken = [], {}
    for key in order:
        if per_series is not None:
            if taken.get(key[0], 0) >= per_series:
                continue
            taken[key[0]] = taken.get(key[0], 0) + 1
        elif len(kept) >= cfg["cap"]:
            break
        kept += groups[key]
    if per_series is not None and cfg.get("cap"):
        kept = kept[:cfg["cap"]] if len(kept) > cfg["cap"] else kept

    if stats is not None:
        stats["listed"] = listed
        stats["priced"] = sum(1 for r in kept if not r["untraded"])
        stats["ladders"] = len(set((r["series"], r["date"]) for r in kept))
    return kept


# ---------------------------------------------------------------------------
# Soccer both-teams-to-score on Kalshi (2026-09-13)
# ---------------------------------------------------------------------------
BTTS_LEAGUES = {                 # Kalshi fragment -> board league name (ESPN form exists)
    "EPL": "Premier League", "LALIGA": "La Liga", "SERIEA": "Serie A",
    "BUNDESLIGA": "Bundesliga", "LIGUE1": "Ligue 1", "UCL": "Champions League",
    "UEL": "Europa League", "MLS": "MLS", "EREDIVISIE": "Eredivisie",
    "LIGAPORTUGAL": "Primeira Liga", "SAUDIPL": "Saudi Pro League",
    "SCOTTISHPREM": "Scottish Premiership",
}
# CUPS and INTERNATIONALS (2026-09-19). The same six form rules, applied to cup ties and to
# national teams as SEPARATE Sandbox pairs — "soccer_o15_cup", "soccer_o15_intl" and so on —
# so their records never mix with the league rules', and nothing reaches Production unless it
# is moved there by hand. Kalshi series with goals markets, checked 2026-09-19 against what
# Kalshi has actually listed; Copa del Rey and Coupe de France are left out (Kalshi has listed
# almost no goals markets for either). The Nations League series exists but had never listed a
# goals market by that date: it is wired so the rules act the day Kalshi lists one.
CUP_FRAGS = {
    "UECL": "UEFA Conference League", "EFLCUP": "EFL Cup", "FACUP": "FA Cup",
    "DFBPOKAL": "DFB Pokal", "COPPAITALIA": "Coppa Italia", "TACAPORT": "Taça de Portugal",
    "KNVBCUP": "KNVB Cup", "SCOCUP": "Scottish Cup", "LEAGUESCUP": "Leagues Cup",
    "USOPENCUP": "US Open Cup", "CONMEBOLLIB": "Copa Libertadores",
    "CONMEBOLSUD": "Copa Sudamericana", "AFCCL": "AFC Champions League",
    # Added 2026-09-21 for the cup mismatch rule: the two cups built on top-flight clubs
    # visiting sides several divisions down. Both list over-1.5 and match-winner markets.
    "COPADELREY": "Copa del Rey", "COUPEDEFRANCE": "Coupe de France",
}
INTL_FRAGS = {"UEFANL": "UEFA Nations League", "INTLFRIENDLY": "International Friendly"}
SCOPES = (("", BTTS_LEAGUES, "league"), ("_cup", CUP_FRAGS, "cup"), ("_intl", INTL_FRAGS, "intl"))
SCOPE_LABEL = {"_cup": "Cups", "_intl": "Internationals"}
SCOPE_NOTE = {
    "_cup": ("CUPS PAIR — the same rule applied only to cup ties ({}). Form is every competitive "
             "game (league and cup, lower tiers included), 90-minute results only. A separate "
             "record from the league rule; not in Production."),
    "_intl": ("INTERNATIONALS PAIR — the same rule applied only to national teams ({}). Form is a "
              "national team's internationals over two years, friendlies included, 90-minute "
              "results only. A separate record from the league rule; not in Production."),
}
BTTS_SPORTS = ("soccer_btts", "soccer_btts_cup", "soccer_btts_intl")

BTTS_FORM_WINDOW = 10
BTTS_FORM_MIN = 7


def _espn_fixtures():
    try:
        import streaks_fetch
        return streaks_fetch.load_or_fetch()["fixtures"]
    except Exception:
        return []


def fetch_kalshi_btts(horizon_days=4, fixtures=None, now=None, stats=None, events_by_series=None, scope=""):
    """Kalshi soccer BTTS markets as yes/no universe rows, each tied to its ESPN fixture.

    A row is kept only when the Kalshi event (home first) matches an upcoming ESPN fixture
    within 3 days: that fixture gives the real kickoff (Kalshi publishes none) and the club
    names the form rule looks up. Side a = Yes, side b = No, each at its own ask, tradeable
    only while that side's book is tight. Settled by resolve_kalshi_market."""
    now = now or datetime.now(timezone.utc)
    fixtures = _espn_fixtures() if fixtures is None else fixtures
    upcoming = []
    for f in fixtures:
        if f.get("played") or not f.get("kickoff"):
            continue
        try:
            ko = datetime.fromisoformat(str(f["kickoff"]).replace("Z", "+00:00"))
        except ValueError:
            continue
        if now < ko <= now + timedelta(days=horizon_days):
            upcoming.append((ko, f))
    rows, listed = [], 0
    _sfx, frags, comp = next(x for x in SCOPES if x[0] == scope)
    upcoming = [(ko, f) for ko, f in upcoming if f.get("comp", "league") == comp]
    for frag, league in frags.items():
        series = f"KX{frag}BTTS"
        if events_by_series is not None:
            events = events_by_series.get(series, [])
        else:
            try:
                events = (_get(f"https://api.elections.kalshi.com/trade-api/v2/events?series_ticker={series}"
                               f"&status=open&limit=200&with_nested_markets=true", tries=2, timeout=30)
                          or {}).get("events") or []
            except RuntimeError:
                continue
        for ev in events:
            title = str(ev.get("title") or "").split(":")[0]
            parts = [p.strip() for p in title.replace(" vs. ", " vs ").split(" vs ")]
            m = next((x for x in ev.get("markets") or [] if str(x.get("ticker", "")).endswith("-BTTS")), None)
            if len(parts) != 2 or not m or str(m.get("status", "")).lower() not in ("active", "open"):
                continue
            listed += 1
            best = None
            for ko, f in upcoming:
                score, flip = pair_match(parts[0], parts[1], f["home"], f["away"], sport="soccer")
                if score > 0 and not flip and (best is None or score > best[0]):
                    best = (score, ko, f)
            if not best:
                continue
            _s, ko, f = best
            ya, yb, na, nb = (_num(m.get("yes_ask_dollars")), _num(m.get("yes_bid_dollars")),
                              _num(m.get("no_ask_dollars")), _num(m.get("no_bid_dollars")))
            if ya is None or na is None:
                continue
            tight = lambda bid, ask: bool(bid is not None and ask is not None and bid > 0
                                          and ask < 1 and ask - bid <= KALSHI_MAX_SPREAD)
            tradeable = {"a": tight(yb, ya), "b": tight(nb, na)}
            rows.append(dict(
                sport="soccer_btts" + scope, venue="kalshi_binary", market_id=m["ticker"], comp=comp,
                label=f"{f['home']} v {f['away']}: both teams to score",
                side_a="Yes", side_b="No", price_a=ya, price_b=na, price_draw=None,
                mid_a=round((ya + (yb if yb is not None else ya)) / 2, 4),
                tradeable=tradeable, untraded=not any(tradeable.values()),
                start=ko.isoformat(), date=ko.strftime("%Y-%m-%d"), volume=0.0,
                start_source="espn", league=league, espn_home=f["home"], espn_away=f["away"],
                url=f"https://kalshi.com/markets/{series.lower()}"))
    rows.sort(key=lambda r: r["start"])
    if stats is not None:
        stats["listed"] = listed
        stats["priced"] = sum(1 for r in rows if not r["untraded"])
    return rows


def btts_form(fixtures, team, before, window=BTTS_FORM_WINDOW):
    """(both-teams-scored count, games) over `team`'s last `window` competitive games that
    kicked off strictly before `before`. ESPN results only."""
    games = []
    for f in fixtures:
        if (not f.get("played") or f.get("home_goals") is None or not f.get("competitive", True)
                or team not in (f.get("home"), f.get("away")) or not f.get("kickoff")):
            continue
        try:
            ko = datetime.fromisoformat(str(f["kickoff"]).replace("Z", "+00:00"))
        except ValueError:
            continue
        if ko < before:
            games.append((ko, f["home_goals"] > 0 and f["away_goals"] > 0))
    games.sort()
    last = [b for _k, b in games[-window:]]
    return sum(last), len(last)


def fetch_btts_market(sport, universe=None):
    """The Kalshi BTTS midpoint on every listed match — never a bet (edge 0 by construction)."""
    rows = (universe if universe is not None else (UNIVERSE or {})).get(sport) or []
    return [dict(market_id=r["market_id"], prob_a=r.get("mid_a", r["price_a"])) for r in rows]


def fetch_btts_form_l10(sport, universe=None, fixtures=None):
    """The pre-registered rule: back Yes where BOTH teams are 7+ of their last 10."""
    rows = (universe if universe is not None else (UNIVERSE or {})).get(sport) or []
    fixtures = _espn_fixtures() if fixtures is None else fixtures
    out = []
    for r in rows:
        try:
            ko = datetime.fromisoformat(str(r["start"]))
        except (KeyError, ValueError):
            continue
        hb, hn = btts_form(fixtures, r.get("espn_home"), ko)
        ab, an = btts_form(fixtures, r.get("espn_away"), ko)
        if hn >= BTTS_FORM_WINDOW and an >= BTTS_FORM_WINDOW and hb >= BTTS_FORM_MIN and ab >= BTTS_FORM_MIN:
            out.append(dict(market_id=r["market_id"], pick="a"))
    return out


# ---------------------------------------------------------------------------
# Soccer goals markets on Kalshi (2026-09-14): over 1.5, a side to score 1+, a side to score 2+
# ---------------------------------------------------------------------------
# Three domains, one per market, so each rule is judged against the population of ITS OWN
# market (backing Yes on every listed match) and never pooled with another line.
#   soccer_o15    KX{LEAGUE}TOTAL      "Over 1.5 goals scored"
#   soccer_team1  KX{LEAGUE}TEAMTOTAL  "{Team} over 0.5 goals"   (one row per side)
#   soccer_team2  KX{LEAGUE}TEAMTOTAL  "{Team} over 1.5 goals"
# Kalshi lists no team totals for the Eredivisie or Primeira Liga (checked 2026-09-14); those
# fixtures simply produce no team rows.
NHL_SPORTS = ("nhl_rest", "nhl_pl")
GOALS_BASE = ("soccer_o15", "soccer_o25", "soccer_team1", "soccer_team2", "soccer_u35", "soccer_p05")
GOALS_SPORTS = GOALS_BASE + tuple(b + x for x in ("_cup", "_intl") for b in GOALS_BASE)

# The three rules found in the ESPN research of 2026-09-13 (530 matches, cutoffs fixed before
# the run). Every count is over COMPETITIVE games that kicked off strictly before the match,
# and each team must have GOALS_MIN_GAMES of them. Nothing here is tuned after that run.
GOALS_MIN_GAMES = 10
O15_WINDOW, O15_MIN = 10, 9            # both teams' games went over 1.5 in 9+ of the last 10
TEAM1_WINDOW = 5                       # side scored in 5/5, opponent conceded in 5/5
TEAM2_WINDOW, TEAM2_MIN = 10, 7        # side scored 2+ in 7+/10, opponent conceded 2+ in 7+/10


def _upcoming_espn(fixtures, now, horizon_days):
    out = []
    for f in fixtures:
        if f.get("played") or not f.get("kickoff"):
            continue
        try:
            ko = datetime.fromisoformat(str(f["kickoff"]).replace("Z", "+00:00"))
        except ValueError:
            continue
        if now < ko <= now + timedelta(days=horizon_days):
            out.append((ko, f))
    return out


def _kalshi_open_events(series, events_by_series=None):
    if events_by_series is not None:
        return events_by_series.get(series, [])
    try:
        return (_get(f"https://api.elections.kalshi.com/trade-api/v2/events?series_ticker={series}"
                     f"&status=open&limit=200&with_nested_markets=true", tries=2, timeout=30)
                or {}).get("events") or []
    except RuntimeError:
        return []


def _espn_fixture_for(ev, upcoming):
    """The upcoming ESPN fixture a Kalshi soccer event ("Home vs Away: ...") is about, or None."""
    title = str(ev.get("title") or "").split(":")[0]
    parts = [p.strip() for p in title.replace(" vs. ", " vs ").split(" vs ")]
    if len(parts) != 2:
        return None
    best = None
    for ko, f in upcoming:
        score, flip = pair_match(parts[0], parts[1], f["home"], f["away"], sport="soccer")
        if score > 0 and not flip and (best is None or score > best[0]):
            best = (score, ko, f)
    return best[1:] if best else None


def _yes_no_row(m, sport, label, ko, f, league, series, **extra):
    """One Kalshi yes/no market as a universe row (side a = Yes, side b = No), or None."""
    ya, yb, na, nb = (_num(m.get("yes_ask_dollars")), _num(m.get("yes_bid_dollars")),
                      _num(m.get("no_ask_dollars")), _num(m.get("no_bid_dollars")))
    if ya is None or na is None:
        return None
    tight = lambda bid, ask: bool(bid is not None and ask is not None and bid > 0
                                  and ask < 1 and ask - bid <= KALSHI_MAX_SPREAD)
    tradeable = {"a": tight(yb, ya), "b": tight(nb, na)}
    return dict(
        sport=sport, venue="kalshi_binary", market_id=m["ticker"], label=label,
        side_a="Yes", side_b="No", price_a=ya, price_b=na, price_draw=None,
        mid_a=round((ya + (yb if yb is not None else ya)) / 2, 4),
        tradeable=tradeable, untraded=not any(tradeable.values()),
        start=ko.isoformat(), date=ko.strftime("%Y-%m-%d"), volume=0.0,
        start_source="espn", league=league, espn_home=f["home"], espn_away=f["away"],
        url=f"https://kalshi.com/markets/{series.lower()}", **extra)


def fetch_kalshi_goals(horizon_days=4, fixtures=None, now=None, stats=None, events_by_series=None):
    """{sport: rows} for the three goals domains, each row tied to its ESPN fixture (the real
    kickoff and the club names the rules look up). Settled by resolve_kalshi_market."""
    now = now or datetime.now(timezone.utc)
    fixtures = _espn_fixtures() if fixtures is None else fixtures
    upcoming = _upcoming_espn(fixtures, now, horizon_days)
    out = {s: [] for s in GOALS_SPORTS}
    listed = 0
    for sfx, frags, comp in SCOPES:
        # A league series is matched only to league fixtures, a cup series to cup ties, an
        # international one to internationals: two clubs can meet in the league and the cup
        # within days, and the market must land on the right match.
        up = [(ko, f) for ko, f in upcoming if f.get("comp", "league") == comp]
        for frag, league in frags.items():
            series = f"KX{frag}TOTAL"
            for ev in _kalshi_open_events(series, events_by_series):
                hit = _espn_fixture_for(ev, up)
                # soccer_u35 is the Over 3.5 market itself: side a = Yes (over), side b = No (under),
                # and soccer_o25 is the Over 2.5 market the same way. Kalshi lists 0.5 through 5.5 on
                # every TOTAL event; 2.5 is added (2026-09-22) because it is the line Pinnacle quotes
                # as its main total, so it is the only one the two venues can be compared on without
                # paying for alternate lines — and it is where a match is least decided in advance.
                for line, sport in (("over 1.5", "soccer_o15" + sfx), ("over 2.5", "soccer_o25" + sfx),
                                    ("over 3.5", "soccer_u35" + sfx)):
                    m = next((x for x in ev.get("markets") or []
                              if line in str(x.get("yes_sub_title") or "").lower()
                              and str(x.get("status", "")).lower() in ("active", "open")), None)
                    if not m:
                        continue
                    listed += 1
                    row = hit and _yes_no_row(m, sport, f"{hit[1]['home']} v {hit[1]['away']}: {line} goals",
                                              hit[0], hit[1], league, series, comp=comp)
                    if row:
                        out[sport].append(row)
            # soccer_p05: each side's win market on the GAME event. Side a = Yes (that side wins),
            # side b = No — the OTHER team does not lose, i.e. the other team +0.5. The row's
            # `team` is that other team (the +0.5 side), `opponent` the market's own side.
            series = f"KX{frag}GAME"
            for ev in _kalshi_open_events(series, events_by_series):
                hit = _espn_fixture_for(ev, up)
                for m in ev.get("markets") or []:
                    if _kalshi_is_tie(m) or str(m.get("status", "")).lower() not in ("active", "open"):
                        continue
                    listed += 1
                    if not hit:
                        continue
                    ko, f = hit
                    who = str(m.get("yes_sub_title") or "")
                    sh, sa = _score(who, f["home"], "soccer"), _score(who, f["away"], "soccer")
                    if max(sh, sa) < 0.5 or sh == sa:
                        continue
                    winner, other = (f["home"], f["away"]) if sh > sa else (f["away"], f["home"])
                    row = _yes_no_row(m, "soccer_p05" + sfx, f"{f['home']} v {f['away']}: {winner} to win (No = {other} +0.5)",
                                      ko, f, league, series, team=other, opponent=winner, comp=comp)
                    if row:
                        out["soccer_p05" + sfx].append(row)
            series = f"KX{frag}TEAMTOTAL"
            for ev in _kalshi_open_events(series, events_by_series):
                hit = _espn_fixture_for(ev, up)
                for m in ev.get("markets") or []:
                    sub = str(m.get("yes_sub_title") or "")
                    line = sub.lower().rsplit(" over ", 1)
                    if len(line) != 2 or str(m.get("status", "")).lower() not in ("active", "open"):
                        continue
                    sport = {"0.5 goals": "soccer_team1" + sfx, "1.5 goals": "soccer_team2" + sfx}.get(line[1].strip())
                    if not sport:
                        continue
                    listed += 1
                    if not hit:
                        continue
                    ko, f = hit
                    who = sub[:len(line[0])]
                    sh, sa = _score(who, f["home"], "soccer"), _score(who, f["away"], "soccer")
                    if max(sh, sa) < 0.5 or sh == sa:
                        continue                          # cannot tell which side the market is about
                    team, opp = (f["home"], f["away"]) if sh > sa else (f["away"], f["home"])
                    n = 1 if sport.startswith("soccer_team1") else 2
                    row = _yes_no_row(m, sport, f"{f['home']} v {f['away']}: {team} to score {n}+",
                                      ko, f, league, series, team=team, opponent=opp, comp=comp)
                    if row:
                        out[sport].append(row)
    for rows in out.values():
        rows.sort(key=lambda r: r["start"])
    if stats is not None:
        stats["listed"] = listed
        stats["priced"] = sum(1 for rows in out.values() for r in rows if not r["untraded"])
    return out


def team_form(fixtures, team, before, pred, window, league=None):
    """(games where pred(goals_for, goals_against) held, games) over `team`'s last `window`
    competitive games that kicked off strictly before `before`, plus the total available.
    `league`: count only games in that competition (HOF's way of counting form)."""
    games = []
    for f in fixtures:
        if (not f.get("played") or f.get("home_goals") is None or not f.get("competitive", True)
                or team not in (f.get("home"), f.get("away")) or not f.get("kickoff")
                or (league is not None and f.get("league") != league)):
            continue
        try:
            ko = datetime.fromisoformat(str(f["kickoff"]).replace("Z", "+00:00"))
        except ValueError:
            continue
        if ko < before:
            gf, ga = ((f["home_goals"], f["away_goals"]) if f["home"] == team
                      else (f["away_goals"], f["home_goals"]))
            games.append((ko, gf, ga))
    games.sort()
    last = games[-window:]
    return sum(1 for _k, gf, ga in last if pred(gf, ga)), len(last), len(games)


def _rule_rows(sport, universe):
    rows = (universe if universe is not None else (UNIVERSE or {})).get(sport) or []
    for r in rows:
        try:
            yield r, datetime.fromisoformat(str(r["start"]))
        except (KeyError, ValueError):
            continue


FAV_BAND = (0.75, 0.90)
# Narrowed for TENNIS on 2026-09-23, and for tennis only. Over 446 settled bets the whole
# 0.75-0.90 band was +2.63% after fees at z +1.68, but split by price the edge was not spread
# across it: 0.75-0.80 ran +5.5% (149 won v 139.1 priced, z +1.75) on 181 bets, while
# 0.80-0.85 and 0.85-0.90 were +0.6% and +0.8% on 265 bets between them -- flat, and inside
# the noise. That is the opposite of the favourite-longshot story the rule was built on,
# which predicts the bias grows as the price shortens.
#
# The narrowing was found in that record, so it is NOT a result: it is a new claim, fitted to
# the data it came from, and the only way to learn anything from it is to start again. The
# pair is therefore taken out of Production and its clock reset, so nothing it did on the
# wide band counts toward the narrow one. MMA keeps the full band -- its record is four bets
# and there is nothing in it to narrow on.
# NARROWED AGAIN 2026-09-24, from 0.75-0.80. The 0.75-0.77 slice was the whole problem: on
# 220 settled bets in the old band it returned -1.03% on its own (74.7% hit against a 75.5c
# average ask) while 0.77-0.81 returned +9.83% (86.2%, z +2.36) and was the ONLY slice
# positive in both halves of the record -- +11.8% then +7.8%, where 0.75-0.77 went -8.3% then
# +7.0% and every band above 0.81 flipped sign.
#
# Said plainly, because it is the weak part: that band was chosen after looking at five of
# them, and the two "halves" are the same eleven days and largely the same tournaments. It is
# a defensible narrowing, not a proven one, which is why it resets the clock exactly as the
# last one did. A 0.77-0.81 record is not a 0.75-0.80 record and counting them together would
# hide both.
BAND_BY_SPORT = {"tennis": (0.77, 0.81)}

# ---- Phase 2: the tier travels with the row ------------------------------------------------
# Every tennis market id already says which tour it belongs to -- Polymarket US slugs read
# "aec-{tier}-{players}-{date}" and Kalshi's read "KX{TOUR}MATCH-..." -- but nothing carried
# it onto the quote, so the record could not be split by tour without re-parsing ids after the
# fact. Stamped here so it accumulates from today.
#
# It is deliberately NOT a rule yet. The pre-registered hypothesis, fixed now and read later:
# a favourite in a SHALLOWER field is more dominant than the same price in a deeper one, so
# lower tiers should beat higher ones at equal price. Today's record is directionally right
# and nowhere near readable -- ITF men +4.30% on 185, WTA -3.87% on 55 -- and flatly
# contradicted by ATP at +23.99% on 27 bets with zero losses, which is what luck looks like.
# Four weeks of stamped rows decides it; fitting a tier rule to 27 bets would not.
TENNIS_TIERS = {"atp": "ATP", "wta": "WTA", "atpch": "ATP Challenger", "atpcq": "ATP Ch. Qual",
                "itfme": "ITF Men", "itfwo": "ITF Women", "atpdb": "ATP Doubles",
                "wtadb": "WTA Doubles", "utr": "UTR"}
_KALSHI_TENNIS_TIER = (("KXATPCHALLENGERMATCH", "atpch"), ("KXATPMATCH", "atp"),
                       ("KXWTAMATCH", "wta"), ("KXITFMATCH", "itfme"))


def tennis_tier(market_id):
    """The tour a tennis market belongs to, read off its id, or None.

    Longest Kalshi prefix first: "KXATPCHALLENGERMATCH" also starts with neither "KXATPMATCH"
    nor "KXWTAMATCH", but an id scheme that gains a shorter overlapping prefix later would
    silently mis-tier every Challenger, so the order is fixed here rather than left to chance.
    """
    m = str(market_id or "")
    if m.startswith("aec-"):
        t = (m.split("-") + ["", ""])[1].lower()
        return t if t in TENNIS_TIERS else None
    for pre, tier in _KALSHI_TENNIS_TIER:
        if m.startswith(pre):
            return tier
    return None


def fav_band(sport):
    """The favourite band this sport backs. See BAND_BY_SPORT."""
    return BAND_BY_SPORT.get(str(sport).split("_")[0], FAV_BAND)
TT_BAND = (0.55, 0.60)


def band_picks(sport, band, universe=None):
    """Back the side whose ask sits in `band` (lower bound inclusive, upper exclusive)."""
    out = []
    for r in (universe if universe is not None else (UNIVERSE or {})).get(sport) or []:
        for side in ("a", "b"):
            p = r.get(f"price_{side}")
            if p is not None and band[0] <= p < band[1] and r.get("price_draw") is None:
                out.append(dict(market_id=r["market_id"], pick=side))
                break
    return out


# ---------------------------------------------------------------------------
# The Eredivisie draw band — pre-registered 2026-09-26
# ---------------------------------------------------------------------------
# One league, one market, one price band, and nothing else. Kalshi lists an Eredivisie match
# as three Yes/No contracts; this backs the Tie when the board's own opinion of the draw,
# with Kalshi's margin removed, sits in ERE_DRAW_BAND.
#
# Why the band and not the whole league: measured on 3,904 Eredivisie matches with closing
# prices, 2013/14-2025/26 (football-data.co.uk). The band was chosen on the 2013/14-2020/21
# half ALONE — it was the best of seven overlapping bands scanned there, at +3.5pp over the
# de-vigged price — and then applied untouched to 2021/22-2025/26, which it had never seen:
# 429 matches, 28.0% drew against 22.8% priced, +5.2pp, z +2.39. It strengthened out of
# sample, and strengthened again when restricted to matches carrying a true closing price
# (+5.9pp, z +3.19). Overfitting decays under both of those; this did the opposite.
#
# Why Eredivisie and not soccer: the SAME band pooled over all twelve leagues in that data
# set is exactly fair — 22.8% drew against 22.9% priced, z -0.14, ROI +0.00%. This is a
# Dutch-league fact, not a draw fact, and the lane must never be widened without re-running
# that test. Turkey (-3.0pp) and Belgium (-4.0pp) sit at the other end and are NOT a rule:
# train sign predicted test sign in only 7 of 12 leagues, which is a coin flip.
#
# What is NOT in the rule, and deliberately: no form, no model, no ranker. The band was split
# four ways in the held-out half — closest half, widest half, cheapest draws, priciest draws —
# and every quarter returned +12% to +20%. The edge is the band itself, spread evenly, so any
# filter bolted on can only subtract. The other markets Kalshi lists for Eredivisie were swept
# on the same 3,904 matches against a benchmark corrected on the other eleven leagues and are
# flat: BTTS +0.1pp, Over 2.5 -0.1pp, Over 3.5 +0.8pp, team-to-score -0.2pp.
#
# Over 1.5 is the exception and the first reading of it here was WRONG. League-wide it looks
# spent (+1.9pp in 2013-2021, +0.5pp in 2021-2026), but that average hides its shape: inside
# the underdog band 3.21-4.00 it runs +3.7pp on the train half and +5.7pp on the held-out half
# (z +2.64), while the other eleven leagues sit at exactly zero in the same band. That is a
# separate and larger lane, not this one. Corrected 2026-09-26.
ERE_DRAW_SERIES = "KXEREDIVISIEGAME"
ERE_DRAW_BAND = (0.20, 0.25)
# Break-even, not a fitted number: at the band's measured 27% strike and Kalshi's
# 0.07*p*(1-p) fee, an ask of 0.266 returns exactly zero. This is the safety rail below it.
# A 0.25 de-vigged draw quotes near 0.255 on a normal 2% board, so it should rarely bind;
# when it does, the book is wide and the bet is not the one that was measured.
ERE_DRAW_MAX_ASK = 0.26


def devig_draw(r):
    """The draw's share of a three-way board with the venue's margin removed, or None."""
    pa, pdr, pb = r.get("price_a"), r.get("price_draw"), r.get("price_b")
    if pa is None or pdr is None or pb is None:
        return None
    total = float(pa) + float(pdr) + float(pb)
    return (float(pdr) / total) if total > 0 else None


def ere_draw_picks(universe=None):
    """Back the Tie on every Kalshi Eredivisie match whose de-vigged draw sits in the band."""
    out = []
    for r in (universe if universe is not None else (UNIVERSE or {})).get("soccer") or []:
        if r.get("venue") != "kalshi":
            continue
        if not str(r.get("market_id") or "").startswith(ERE_DRAW_SERIES):
            continue
        # Default True, as every other reader of this field does.
        if r.get("untraded") or not (r.get("tradeable") or {}).get("draw", True):
            continue
        p = devig_draw(r)
        if p is None or not (ERE_DRAW_BAND[0] <= p < ERE_DRAW_BAND[1]):
            continue
        if float(r["price_draw"]) > ERE_DRAW_MAX_ASK:
            continue
        out.append(dict(market_id=r["market_id"], pick="draw"))
    return out


def fetch_ere_draw(sport, universe=None):
    """ERE_DRAW_BAND, Eredivisie only. Three-way soccer is the only domain that has a draw."""
    if sport != "soccer":
        return []
    return ere_draw_picks(universe)


# ---------------------------------------------------------------------------
# Eredivisie over 1.5, by the underdog's price — pre-registered 2026-09-26
# ---------------------------------------------------------------------------
# The second Eredivisie lane, and a different market from ere_draw: back OVER 1.5 GOALS when
# the same fixture's three-way board prices the underdog inside ERE_O15_DOG_BAND. The band is
# the de-vig of bookmaker decimal odds 3.21-4.00 — a clear but not overwhelming favourite.
#
# Measured on 3,904 Eredivisie matches with closing prices, 2013/14-2025/26, against the
# over-1.5 probability implied by the same match's closing over-2.5 price, with the other
# eleven leagues' own excess in the same band SUBTRACTED so only the league-specific part
# is counted. All 13 seasons: 82.4% against 78.4% implied, league part +4.0pp, z +3.13.
# Train 13/14-20/21: +3.0pp (z +1.87). Held out 21/22-25/26: +5.7pp (z +2.73) — larger on
# the half the band never saw. Ten of thirteen seasons finished above implied, and the cell
# is positive in all three disjoint eras (+4.0pp, +2.3pp, +6.9pp).
#
# THE CASE AGAINST, recorded here so the record is judged against an honest prior. This is a
# SPIKE, not a gradient. Disjoint underdog bands across the same 13 seasons read +0.7pp,
# +4.3pp, -0.1pp, -0.3pp, +1.3pp — everything either side of it is flat, and the correlation
# between any 1X2 price and the over-1.5 residual is 0.00 in Eredivisie AND in the other
# eleven leagues. So there is no mechanism, only a bucket. Worse, 60 league x band cells were
# scanned and this one ranks FIRST at z +3.27 against an expected maximum of ~2.86 under pure
# noise — and the same field throws off La Liga's dog 7.00+ at z -3.44, a LARGER deviation in
# a direction nobody has a story for. A field that produces that can produce this. The lane
# exists because the Sandbox settles it forward on bets nobody has seen, which is the only
# thing that can separate the two, not because the backtest proved it.
#
# ere_draw's band was re-checked against this and they are different markets on mostly
# different fixtures; neither is a filter on the other, and both log independently.
ERE_O15_TOTAL = "KXEREDIVISIETOTAL"
ERE_O15_GAME = "KXEREDIVISIEGAME"
# De-vigged underdog win probability. This is the mechanical translation of the registered
# 3.21-4.00 decimal band at Eredivisie's measured 6.2% three-way hold, so it carries to a
# 2%-hold venue unchanged. A slightly different window (0.230-0.290) scores better on the
# same data (z +3.39 v +3.13); it was NOT taken, because choosing it after seeing that is
# refitting the band on the evidence meant to test it.
ERE_O15_DOG_BAND = (0.234, 0.296)
# Break-even, not fitted: at the band's measured 82.4% and Kalshi's 0.07*p*(1-p) fee, an ask
# of 0.816 returns exactly zero. Kalshi quoted Eredivisie over-1.5 at 0.84-0.93 on the big
# mismatches it lists most often, so this ceiling is expected to BIND often and that is the
# point — above it the bet being measured is not the bet being offered.
ERE_O15_MAX_ASK = 0.81


def _ere_code(market_id):
    """'KXEREDIVISIETOTAL-26SEP18GROZWO-2' -> '26SEP18GROZWO'; one fixture's markets share it."""
    return (str(market_id or "").split("-") + ["", ""])[1]


def ere_o15_dogs(universe=None):
    """{fixture code: de-vigged underdog win probability} off the Kalshi Eredivisie 3-way board."""
    out = {}
    for r in (universe if universe is not None else (UNIVERSE or {})).get("soccer") or []:
        if r.get("venue") != "kalshi":
            continue
        if not str(r.get("market_id") or "").startswith(ERE_O15_GAME):
            continue
        pa, pdr, pb = r.get("price_a"), r.get("price_draw"), r.get("price_b")
        if pa is None or pdr is None or pb is None:
            continue
        total = float(pa) + float(pdr) + float(pb)
        if total <= 0:
            continue
        out[_ere_code(r.get("market_id"))] = min(float(pa), float(pb)) / total
    return out


def ere_o15_picks(sport, universe=None):
    """Back over 1.5 on a Kalshi Eredivisie total when its own winner board prices the dog in band."""
    uni = universe if universe is not None else (UNIVERSE or {})
    dogs = ere_o15_dogs(uni)
    out = []
    for r in uni.get(sport) or []:
        if r.get("venue") != "kalshi_binary":
            continue
        if not str(r.get("market_id") or "").startswith(ERE_O15_TOTAL):
            continue
        # Default True, as every other reader of this field does.
        if r.get("untraded") or not (r.get("tradeable") or {}).get("a", True):
            continue
        p = dogs.get(_ere_code(r.get("market_id")))
        if p is None or not (ERE_O15_DOG_BAND[0] <= p < ERE_O15_DOG_BAND[1]):
            continue
        ask = r.get("price_a")
        if ask is None or float(ask) > ERE_O15_MAX_ASK:
            continue
        out.append(dict(market_id=r["market_id"], pick="a"))
    return out


def fetch_ere_o15(sport, universe=None):
    """ERE_O15_DOG_BAND, Eredivisie league matches only. No cup or international twin exists."""
    if sport != "soccer_o15":
        return []
    return ere_o15_picks(sport, universe)


# ---------------------------------------------------------------------------
# Bundesliga over 3.5 — pre-registered 2026-09-26. Two lanes, wide and narrow.
# ---------------------------------------------------------------------------
# THE FINDING, and it is the only one in a 540-cell study that survives its own correction.
# Bundesliga scores more than its price says, on the over-3.5 line, and only recently:
#
#            2022/23-2025/26   n=1224   Bundesliga +3.71pp   other 11 leagues -0.67pp
#                                       difference +4.39pp,  z +3.01
#            2013/14-2017/18   n=1530   difference -0.11pp,  z -0.09
#
# No band was chosen for that test and no cell was picked — it is the whole league on one
# line. Count it as six implicit tests (three goal lines x two eras) and it needs z >= 2.64;
# it clears. Everything else in the study does not, and the reason is worth keeping: a
# permutation test that reshuffled league labels 300 times across all 52,335 matches found
# that this grid produces a maximum |z| of 3.30 HALF THE TIME from pure noise, and needs
# 4.09 for family-wise 5%. The largest cell anywhere in the real data was 3.44 — permutation
# p = 0.363. Backtest magnitude proves nothing here. What makes this one different is that it
# was not selected, and that the early era is flat, so it has a date rather than a story.
#
# The mechanism is market lag on a regime shift. Bundesliga goals went 2.88 -> 3.13 -> 3.19
# across the three eras while the price's implied total went 2.91 -> 3.10 -> 3.10 and stopped
# following. Over the same eras the other eleven leagues' gap never left +-1pp.
#
# TWO LANES, deliberately. bund_o35 takes every match — nothing selected, so nothing to
# discount. bund_o35_draw takes only the draw-price band where the effect concentrates,
# which is a real but unproven refinement (z +2.82 over 13 seasons, and +0.4pp train against
# +8.7pp held out — the TREND shape, not the replicating one). A match in the band is logged
# by BOTH, and that overlap is the comparison: if the band adds nothing, the two records
# converge and the narrow lane is deleted.
BUND_O35_TOTAL = "KXBUNDESLIGATOTAL"
BUND_O35_GAME = "KXBUNDESLIGAGAME"
# De-vigged draw probability. The mechanical translation of bookmaker decimal 3.60-4.00 at
# Bundesliga's measured hold: the matches in that decimal band span exactly 0.2351-0.2669.
BUND_O35_DRAW_BAND = (0.235, 0.267)
# NOT an absolute price ceiling, on purpose. This lane's claim is RELATIVE — +4.4pp over
# whatever the market says for that match — so a fixed ceiling would be measuring the wrong
# thing. At Kalshi's typical over-3.5 ask of 0.41 against a de-vigged 0.40 the bet returns
# about +6.5% net, while an absolute ceiling set at the long-run 37.5% base rate would have
# rejected every Bundesliga board Kalshi has actually quoted. The guard that belongs here is
# against a WIDE book, where the ask is not the price: skip anything holding more than this.
# Kalshi's over-3.5 markets have averaged +3.33%.
BUND_O35_MAX_HOLD = 0.06


def _bund_o35_rows(sport, universe):
    """The Kalshi Bundesliga over-3.5 rows, gated on liquidity and book width."""
    out = []
    for r in (universe or {}).get(sport) or []:
        if r.get("venue") != "kalshi_binary":
            continue
        if not str(r.get("market_id") or "").startswith(BUND_O35_TOTAL):
            continue
        # Default True, as every other reader of this field does.
        if r.get("untraded") or not (r.get("tradeable") or {}).get("a", True):
            continue
        a, b = r.get("price_a"), r.get("price_b")
        # Rounded: prices arrive in whole cents, but 0.50 + 0.56 - 1.0 is 0.06000000000000005
        # in binary floating point, which rejected a board holding exactly the cap.
        if a is None or b is None or round(float(a) + float(b) - 1.0, 6) > BUND_O35_MAX_HOLD:
            continue
        out.append(r)
    return out


def bund_o35_draws(universe=None):
    """{fixture code: de-vigged draw probability} off the Kalshi Bundesliga three-way board."""
    out = {}
    for r in (universe if universe is not None else (UNIVERSE or {})).get("soccer") or []:
        if r.get("venue") != "kalshi":
            continue
        if not str(r.get("market_id") or "").startswith(BUND_O35_GAME):
            continue
        pa, pdr, pb = r.get("price_a"), r.get("price_draw"), r.get("price_b")
        if pa is None or pdr is None or pb is None:
            continue
        total = float(pa) + float(pdr) + float(pb)
        if total <= 0:
            continue
        out[_ere_code(r.get("market_id"))] = float(pdr) / total
    return out


def fetch_bund_o35(sport, universe=None):
    """Back over 3.5 on every Kalshi Bundesliga match. Nothing is selected."""
    if sport != "soccer_u35":
        return []
    uni = universe if universe is not None else (UNIVERSE or {})
    return [dict(market_id=r["market_id"], pick="a") for r in _bund_o35_rows(sport, uni)]


# ---------------------------------------------------------------------------
# La Liga — pre-registered 2026-09-26. Two lanes pointing in OPPOSITE directions.
# ---------------------------------------------------------------------------
# La Liga is the under league of the twelve: 2.64 goals a game against an all-league 2.73,
# and every goal line sits below its price (-0.9pp, -1.1pp, -1.2pp on over 1.5/2.5/3.5).
# But the league splits in two, and the split is what makes it worth two lanes:
#
#   HEAVY MISMATCHES score LESS than priced. With the underdog under a de-vigged 0.135,
#   over 1.5 lands 79.3% against 82.3% implied - league part -4.2pp, z -3.46, and it
#   STRENGTHENS out of sample (train -2.8pp, held out -7.4pp). Spain's big clubs shut
#   minnows out more thoroughly than the market charges for.
#
#   BALANCED MATCHES produce MORE from the underdog than priced. With the favourite inside
#   a de-vigged 0.470-0.590, both teams score 55.3% against 49.3% implied - +4.7pp, z +3.52,
#   train +3.4pp and held out +6.7pp. The favourite's own scoring is flat (+1.4pp): the
#   whole effect is the weaker side getting on the scoresheet.
#
# NEITHER CLEARS THE GRID'S OWN BAR, and both notes say so. Adding team-to-score and BTTS
# took the scan to 1,424 cells; a permutation reshuffling league labels 200 times over all
# 52,999 matches puts the family-wise 5% threshold at |z| >= 4.16, and the largest cell
# anywhere in the real data is 4.30 (Turkey, not Spain). These two are 3.52 and 3.46. They
# are built on the same footing as the Eredivisie and Bundesliga lanes - they replicate
# across both halves - not because the backtest proved them.
#
# A note on the statistic, because it changed an answer here: z is computed against the
# IMPLIED rate, not the observed one. Using the observed rate degenerates on near-certain
# lines - a band where every favourite scored returned a z of 15,424 - and two of the top
# cells in the first pass were that artifact and nothing else.
LIGA_BTTS = "KXLALIGABTTS"
LIGA_TOTAL = "KXLALIGATOTAL"
LIGA_GAME = "KXLALIGAGAME"
# De-vigged FAVOURITE win probability. The mechanical span of bookmaker decimal 1.60-2.00
# in La Liga, which is exactly 0.4702-0.6002.
LIGA_BTTS_FAV_BAND = (0.470, 0.590)
# Break-even, not fitted: at the band's measured 55.3% BTTS rate and Kalshi's 0.07*p*(1-p)
# fee, an ask of 0.543 returns zero.
LIGA_BTTS_MAX_ASK = 0.54
# De-vigged UNDERDOG win probability. The span of decimal 7.00+ in La Liga tops out at
# 0.1371; 0.135 is the round number inside it.
LIGA_U15_DOG_MAX = 0.135
# Break-even on the NO side: under 1.5 landed 20.7% in this band, so 0.204 returns zero.
LIGA_U15_MAX_ASK = 0.20
# Both lanes skip a board holding more than this. Kalshi's soccer binaries average ~3.4%.
LIGA_MAX_HOLD = 0.06


def liga_fav_dog(universe=None):
    """{fixture code: (de-vigged favourite prob, de-vigged underdog prob)} off the La Liga board."""
    out = {}
    for r in (universe if universe is not None else (UNIVERSE or {})).get("soccer") or []:
        if r.get("venue") != "kalshi":
            continue
        if not str(r.get("market_id") or "").startswith(LIGA_GAME):
            continue
        pa, pdr, pb = r.get("price_a"), r.get("price_draw"), r.get("price_b")
        if pa is None or pdr is None or pb is None:
            continue
        total = float(pa) + float(pdr) + float(pb)
        if total <= 0:
            continue
        out[_ere_code(r.get("market_id"))] = (max(float(pa), float(pb)) / total,
                                              min(float(pa), float(pb)) / total)
    return out


def _liga_rows(sport, universe, series, side):
    """La Liga rows on one Kalshi series, gated on liquidity and book width."""
    out = []
    for r in (universe or {}).get(sport) or []:
        if r.get("venue") != "kalshi_binary":
            continue
        if not str(r.get("market_id") or "").startswith(series):
            continue
        # Default True, as every other reader of this field does.
        if r.get("untraded") or not (r.get("tradeable") or {}).get(side, True):
            continue
        a, b = r.get("price_a"), r.get("price_b")
        if a is None or b is None or round(float(a) + float(b) - 1.0, 6) > LIGA_MAX_HOLD:
            continue
        out.append(r)
    return out


def fetch_liga_btts_even(sport, universe=None):
    """Back BTTS Yes in a La Liga match the board prices as roughly balanced."""
    if sport != "soccer_btts":
        return []
    uni = universe if universe is not None else (UNIVERSE or {})
    board = liga_fav_dog(uni)
    out = []
    for r in _liga_rows(sport, uni, LIGA_BTTS, "a"):
        pf = (board.get(_ere_code(r.get("market_id"))) or (None, None))[0]
        if pf is None or not (LIGA_BTTS_FAV_BAND[0] <= pf < LIGA_BTTS_FAV_BAND[1]):
            continue
        if float(r["price_a"]) > LIGA_BTTS_MAX_ASK:
            continue
        out.append(dict(market_id=r["market_id"], pick="a"))
    return out


def fetch_liga_u15_dog(sport, universe=None):
    """Back UNDER 1.5 (No on Kalshi's over 1.5) in a La Liga heavy mismatch.

    A 20% strike at about five to one. Expect long losing runs; at ~2 bets a matchweek the
    30-bet floor is roughly fifteen weeks away.
    """
    if sport != "soccer_o15":
        return []
    uni = universe if universe is not None else (UNIVERSE or {})
    board = liga_fav_dog(uni)
    out = []
    for r in _liga_rows(sport, uni, LIGA_TOTAL, "b"):
        pd_ = (board.get(_ere_code(r.get("market_id"))) or (None, None))[1]
        if pd_ is None or pd_ >= LIGA_U15_DOG_MAX:
            continue
        if float(r["price_b"]) > LIGA_U15_MAX_ASK:
            continue
        out.append(dict(market_id=r["market_id"], pick="b"))
    return out


def fetch_bund_o35_draw(sport, universe=None):
    """bund_o35's bet, only where the winner board prices the draw in BUND_O35_DRAW_BAND.

    bund_o35 is NOT filtered and keeps logging every Bundesliga match, so a fixture in the
    band is logged by both lanes under two sources and the two records can be read side by
    side. Duplicate protection is per source, so that overlap is intended, not a fault.
    """
    if sport != "soccer_u35":
        return []
    uni = universe if universe is not None else (UNIVERSE or {})
    draws = bund_o35_draws(uni)
    out = []
    for r in _bund_o35_rows(sport, uni):
        p = draws.get(_ere_code(r.get("market_id")))
        if p is None or not (BUND_O35_DRAW_BAND[0] <= p < BUND_O35_DRAW_BAND[1]):
            continue
        out.append(dict(market_id=r["market_id"], pick="a"))
    return out


# ---------------------------------------------------------------------------
# Tennis combos — pre-registered 2026-09-21
# ---------------------------------------------------------------------------
# A combo pays only if EVERY leg wins, so it multiplies the edge instead of averaging it:
# if a rule's hit rate beats the price it pays by a factor m, an n-leg basket beats its own
# price by m**n. The tennis favourite-band rule has run at m = 1.042 over 238 settled bets,
# which would be 1.085 at two legs and 1.131 at three. That cuts BOTH ways and is the whole
# point of sandboxing it: if m is really 1.0, the basket loses about three times as fast.
#
# The cost of the wrapper was measured before a line of this was written. On 2026-09-21,
# 20 baskets built from that day's real in-band legs were quoted by Kalshi's RFQ (7-14
# market makers answered each one): the quote sat a median 0.84% over the product of the
# legs at two legs and 1.06% at three. Those are COMBO_MARKUP below. The same baskets' own
# resting order books were far worse — 1 of 20 had any ask at all, at +7.4% and +9.8% — so
# a live version of this must request a quote and must never take the book.
#
# The price logged here is therefore the product of the legs' asks plus that measured
# markup: a modelled cost, not a live quote, because the RFQ needs credentials that must
# not reach a CI runner. It is re-measurable at any time by the same method, and if this
# lane earns its keep the upgrade is to price it on the VPS the way the trading lane runs.
COMBO_LEGS = (2, 3, 4)
# Measured, Kalshi RFQ: 2 and 3 legs on 2026-09-21 (20 baskets), 4 legs on 2026-09-22 (12
# baskets, 12-18 makers each). The 4-leg figure sitting below the 3-leg one is day-to-day
# noise across different legs, not a cheaper wrapper; each size uses its own measurement.
COMBO_MARKUP = {2: 0.0084, 3: 0.0106, 4: 0.0066}
# The Kalshi collection a basket is built in. Checked open on 2026-09-23, and it is the one
# the markup above was measured through. A basket is not a market you can hit: you name the
# legs to this collection and ASK for a quote. The same baskets' resting order books were
# 7.4% and 9.8% worse on the one occasion any of them had an ask at all, so a follower who
# takes the book instead of asking is not making this bet.
COMBO_COLLECTION = "KXMVECROSSCATEGORY-R"


# ---------------------------------------------------------------------------
# Polymarket US combos — pre-registered 2026-09-24
# ---------------------------------------------------------------------------
# Kalshi is not the only venue with baskets. Polymarket US ships a "Build a Combo" builder
# covering ATP, WTA, ITF, Davis Cup, UTR and both doubles draws, priced by its own
# gateway.combos.v1.CombosService/ValidateCombo. That matters because the tennis rule picks
# almost entirely on Polymarket US -- every one of its 15 bets after the 2026-09-23 band
# narrowing -- while the Kalshi basket lane starved to zero for want of in-band Kalshi legs.
#
# Why this lane exists at all: the legs there are BOTH more plentiful and better. In the
# 0.75-0.80 band, Polymarket US supplied 14.6 in-band legs a day against Kalshi's 6.3, and
# returned +6.86% gross a leg (n=146) against Kalshi's +5.45% (n=58). A basket multiplies the
# leg edge, so that gap compounds -- and so does the error, which is the whole risk here and
# the reason this starts in the Sandbox rather than Production. NEITHER leg edge is
# significant (t +1.66 and +0.81). If the true edge is zero a basket does not return zero, it
# loses the full wrapper-and-fee drag every time.
#
# MEASURED ON TWO BASKETS, WHICH IS STILL THE WEAK POINT. Both read live on 2026-09-24:
#   NFL, pre-match, 2 legs: 1.43x + 1.17x, $25 -> $40.73 = 1.6292x  ->  +2.69% over the
#     product. Exact, because the venue shows per-leg multipliers for NFL.
#   Tennis, in-play, 2 legs: 72% + 66% -> 2.08x  ->  +1.17% central, but tennis rows show
#     only whole-number percentages, so rounding puts it anywhere in -0.3% to +2.7%.
# Kalshi's constants come from 20 RFQ baskets. Two is not 20, and the tennis one is the
# imprecise one, so this stays provisional. The constant keeps the DEARER of the two: pricing
# the basket as more expensive than it may be makes this lane's returns conservative, and
# under-claiming is the safe direction for a lane whose whole risk is over-claiming an edge.
# The three- and four-leg figures are EXTRAPOLATED from it on Kalshi's observed 2->3 shape
# (0.84% -> 1.06%, a factor of 1.26) and are not measurements at all.
#
# A WARNING FOR WHOEVER RE-MEASURES THIS. The payout is rendered by an animated digit reel.
# A value read while the button says "Updating" is a frame, not a price: 1.32x came up for
# BOTH a 3-leg tennis basket and a 2-leg NFL one that settled at 1.63x, and reading it as
# real produced an imaginary +38% markup and a tidy story about in-play margins to explain
# it. Take the number from the settled DOM text, never from a screenshot mid-animation.
#
# Priced as a model, not a live quote, for the same reason the Kalshi lane is: the real
# number lives behind the account's logged-in session on web.polymarket.us, and that must
# never reach a CI runner.
PM_COMBO_MARKUP = {2: 0.0269, 3: 0.0339, 4: 0.0427}
PM_COMBO_MEASURED = {2: True, 3: False, 4: False}


def pm_combo_legs_by_day(universe=None):
    """{date: [(row, side, price)]} — basket legs on POLYMARKET US, the mirror of
    combo_legs_by_day. Same band, same one-leg-per-match rule, the other venue."""
    rows = (universe if universe is not None else (UNIVERSE or {})).get("tennis") or []
    lo, hi = fav_band("tennis")
    by_day = {}
    for r in rows:
        if r.get("venue") != "polymarket_us":
            continue
        if r.get("untraded") or r.get("price_draw") is not None:
            continue
        for side in ("a", "b"):
            p = r.get(f"price_{side}")
            if p is None or not (r.get("tradeable") or {}).get(side, True):
                continue
            if lo <= p < hi:
                by_day.setdefault(r.get("date"), []).append((r, side, float(p)))
                break
    return by_day


def combo_legs_by_day(universe=None):
    """{date: [(row, side, price)]} — the legs a basket may be cut from, KALSHI ONLY.

    Every leg must be a Kalshi market. A basket is not a market anyone can hit: you name its
    legs to COMBO_COLLECTION and ask for a quote, and that collection lives on Kalshi, so a
    Polymarket leg cannot go in one. `sandbox_track.placeable` enforces the same rule at the
    other end, and would reject any basket built from one.

    That used to happen BY ACCIDENT and it cost a day of Production. Polymarket rows carry no
    "tradeable" key at all (fetch_polymarket_us sets only `untraded`), and the price check
    below read a missing key as untradeable, so Polymarket legs were dropped silently -- every
    one of the first 115 legs ever used was a Kalshi leg and nothing said why. When the tennis
    band narrowed to 0.75-0.80 on 2026-09-23 the in-band Kalshi legs fell below two, the pool
    emptied, and the build printed a bare "0 baskets" while tennis_fav_band went on picking
    Polymarket legs happily. The venue rule is stated outright here, and the caller reports
    the leg count when it cannot fill a basket.

    The band is the tennis rule's own -- the legs ARE its picks -- so it moves with it. A
    basket of 0.75-0.80 legs is not the same contract as one of 0.75-0.90 legs, which is why
    narrowing the band resets these records too.
    """
    rows = (universe if universe is not None else (UNIVERSE or {})).get("tennis") or []
    lo, hi = fav_band("tennis")
    by_day = {}
    for r in rows:
        if r.get("venue") != "kalshi":
            continue
        if r.get("untraded") or r.get("price_draw") is not None:
            continue
        for side in ("a", "b"):
            p = r.get(f"price_{side}")
            # Default True, as every other reader of this field does: a row that does not
            # say is tradeable. The venue check above is what keeps the pool honest.
            if p is None or not (r.get("tradeable") or {}).get(side, True):
                continue
            if lo <= p < hi:
                by_day.setdefault(r.get("date"), []).append((r, side, float(p)))
                break                      # one leg per match: the sides cannot both win
    return by_day


def tennis_combo_rows(universe=None, now=None, used=None):
    """Baskets of each day's favourite-band legs: every eligible leg, each in at most one
    basket of a given size.

    Built, never chosen: the day's eligible legs sort by start time (market id breaks a
    tie) and are cut into consecutive baskets of n, so there is no way to pick a nicer
    basket after the fact. Baskets share no match, which is what makes each one an
    independent result — judged per basket, the way the single-leg rule is judged per bet.

    `used` is {n: leg market ids already in a logged basket of that size}. The tracker runs
    every three hours and matches drop out of the universe as they start, so cutting the
    remaining legs afresh each run would put a leg into two baskets. Legs already used are
    skipped instead. A basket's id is derived from its legs, so it is the same basket
    whichever run builds it. (Until 2026-09-21 this built ONE basket a day per size, from
    the first n legs, and left ~55 of a typical day's ~60 eligible legs unused.)
    """
    return _basket_rows(combo_legs_by_day(universe), used, COMBO_MARKUP,
                        sport="tennis_combo", prefix="combo", url="https://kalshi.com/combos")


def pm_tennis_combo_rows(universe=None, now=None, used=None):
    """The same baskets, cut from POLYMARKET US legs and priced with PM_COMBO_MARKUP.

    Identical construction to tennis_combo_rows on purpose: same band, same start-time
    order, same consecutive cutting, so the two venues' records are comparable and any
    difference between them is the venues, not the rule. See PM_COMBO_MARKUP for what the
    price is and how weakly the markup is measured.
    """
    return _basket_rows(pm_combo_legs_by_day(universe), used, PM_COMBO_MARKUP,
                        sport="tennis_pmcombo", prefix="pmcombo",
                        url="https://polymarket.us")


def _basket_rows(by_day, used, markup, sport, prefix, url):
    """Cut day-grouped legs into consecutive baskets. Shared by both venues' lanes."""
    import hashlib
    used = used or {}
    out = []
    for day, group in sorted(by_day.items()):
        group.sort(key=lambda t: (str(t[0].get("start")), str(t[0]["market_id"])))
        for n in COMBO_LEGS:
            free = [t for t in group if t[0]["market_id"] not in (used.get(n) or ())]
            for i in range(0, len(free) - n + 1, n):
                pick = free[i:i + n]
                prod = 1.0
                for _r, _side, p in pick:
                    prod *= p
                price = round(prod * (1 + markup[n]), 4)
                names = " + ".join(str(r["side_a"] if sd == "a" else r["side_b"])[:22]
                                   for r, sd, _ in pick)
                key = hashlib.sha1("|".join(sorted(r["market_id"] for r, _, _ in pick))
                                   .encode()).hexdigest()[:10]
                out.append(dict(
                    sport=sport, venue="combo", market_id=f"{prefix}{n}:{day}:{key}",
                    label=f"{n}-leg tennis combo: {names}",
                    side_a=f"All {n} win", side_b="Any one loses",
                    price_a=price, price_b=round(1 - price, 4), mid_a=price,
                    spread=None, liquidity=None, volume=0.0, untraded=False,
                    tradeable={"a": True, "b": True},
                    start=min(str(r["start"]) for r, _, _ in pick),
                    # A basket is only as verified as its WORST leg: one leg whose start is
                    # an estimate makes the whole basket's start an estimate, because the
                    # basket cannot be bought after any leg has begun.
                    start_source=(None if any(not r.get("start_source") for r, _, _ in pick)
                                  else sorted({str(r["start_source"]) for r, _, _ in pick})[0]),
                    date=day, url=url,
                    # The leg's own NAME travels with it. A basket is bought by naming its
                    # legs to the venue, and "KXATPMATCH-26SEP24MARBOL yes" is not something
                    # a reader can check against the match they think they are backing.
                    legs=[dict(market_id=r["market_id"], pick=sd,
                               venue=r.get("venue", "polymarket"),
                               name=str(r["side_a"] if sd == "a" else r["side_b"]),
                               start=str(r["start"]))
                          for r, sd, _ in pick],
                ))
    return out


def fetch_tennis_combo2(sport, universe=None):
    """Buy the day's two-leg basket."""
    return [dict(market_id=r["market_id"], pick="a")
            for r in ((universe if universe is not None else (UNIVERSE or {})).get(sport) or [])
            if str(r["market_id"]).startswith("combo2:")]


def fetch_tennis_combo3(sport, universe=None):
    """Buy the day's three-leg basket."""
    return [dict(market_id=r["market_id"], pick="a")
            for r in ((universe if universe is not None else (UNIVERSE or {})).get(sport) or [])
            if str(r["market_id"]).startswith("combo3:")]


def fetch_tennis_combo4(sport, universe=None):
    """Buy the day's four-leg baskets."""
    return [dict(market_id=r["market_id"], pick="a")
            for r in ((universe if universe is not None else (UNIVERSE or {})).get(sport) or [])
            if str(r["market_id"]).startswith("combo4:")]


def fetch_pm_combo2(sport, universe=None):
    """Buy the day's two-leg Polymarket US basket."""
    return [dict(market_id=r["market_id"], pick="a")
            for r in ((universe if universe is not None else (UNIVERSE or {})).get(sport) or [])
            if str(r["market_id"]).startswith("pmcombo2:")]


def fetch_pm_combo3(sport, universe=None):
    """Buy the day's three-leg Polymarket US basket."""
    return [dict(market_id=r["market_id"], pick="a")
            for r in ((universe if universe is not None else (UNIVERSE or {})).get(sport) or [])
            if str(r["market_id"]).startswith("pmcombo3:")]


def fetch_pm_combo4(sport, universe=None):
    """Buy the day's four-leg Polymarket US baskets."""
    return [dict(market_id=r["market_id"], pick="a")
            for r in ((universe if universe is not None else (UNIVERSE or {})).get(sport) or [])
            if str(r["market_id"]).startswith("pmcombo4:")]


def resolve_combo(legs):
    """'a' if every leg won, 'b' if one lost, 'void' if a leg voided, None while any is open."""
    if not legs:
        return None
    lost = False
    for leg in legs:
        v = leg.get("venue")
        res = (resolve_kalshi(leg["market_id"]) if v == "kalshi"
               else resolve_kalshi_market(leg["market_id"]) if v == "kalshi_binary"
               else resolve_polymarket_us(leg["market_id"]) if v == "polymarket_us"
               else resolve_polymarket(leg["market_id"]))
        if res == "void":
            return "void"              # a voided leg is refunded, so the basket is too
        if res is None:
            return None                # still running: a basket is never settled early
        if res != leg["pick"]:
            lost = True
    return "b" if lost else "a"


# ---------------------------------------------------------------------------
# Verified start times for tennis (2026-09-17)
# ---------------------------------------------------------------------------
# Kalshi's tennis markets carry no start. What they carry is an expected END
# (`occurrence_datetime` / expected_expiration_time), measured at +160 to +180 minutes after
# Polymarket's start on 7 matches listed by both venues. fetch_kalshi_venue turns that into a
# start by subtracting three hours — a deliberately early ESTIMATE, good to within minutes in
# practice, but an estimate, and a lead published on one could be a match already under way.
#
# Polymarket cannot supply the missing time either: a Kalshi row only survives the venue
# dedupe when Polymarket does NOT list that contest, so the rows that need a start are
# exactly the ones Polymarket has never heard of.
#
# Tennis Explorer publishes the schedule itself, in Prague time. Measured the same way — 15
# matches it shares with Polymarket — 13 landed within a minute of Polymarket's start once
# converted, and the two that did not were matches Polymarket had moved. That is the same
# job ESPN does for soccer kickoffs, so it is used the same way: a Kalshi tennis row is
# publishable only once this has confirmed when the match actually starts.
TENNIS_TZ = "Europe/Prague"
TENNIS_START_MAX_H = 4          # a start this far from Kalshi's estimate is a different match
_tennis_starts = None


def tennis_starts(refresh=False):
    """[(player a, player b, start UTC)] from Tennis Explorer's schedule. Cached per run."""
    global _tennis_starts
    if _tennis_starts is not None and not refresh:
        return _tennis_starts
    from zoneinfo import ZoneInfo
    try:
        h = _get_html(TENNIS_EXPLORER)
    except RuntimeError as e:
        print(f"  ! tennisexplorer schedule: {str(e)[:70]}")
        return []
    day = datetime.now(ZoneInfo(TENNIS_TZ)).date()
    out, pending = [], None
    for r in re.findall(r"(?is)<tr[^>]*>(.*?)</tr>", h):
        if "t-name" not in r:
            continue
        nm = re.search(r'(?is)<td class="t-name"[^>]*>\s*(?:<a[^>]*>)?([^<]{3,40})', r)
        tm = re.search(r'(?is)<td[^>]*class="[^"]*time[^"]*"[^>]*>\s*([0-9]{1,2}:[0-9]{2})', r)
        if not nm:
            continue
        if tm:                                   # first row of the pair carries the time
            pending = (nm.group(1).strip(), tm.group(1))
        elif pending:
            a, t = pending
            pending = None
            hh, mm = (int(x) for x in t.split(":"))
            local = datetime(day.year, day.month, day.day, hh, mm, tzinfo=ZoneInfo(TENNIS_TZ))
            out.append((a, nm.group(1).strip(), local.astimezone(timezone.utc)))
    _tennis_starts = out
    return out


def apply_tennis_starts(rows, schedule=None, now=None):
    """Give Kalshi tennis rows a real start time. -> (rows, stats).

    A row keeps Kalshi's estimate and stays unpublishable unless the schedule names the same
    two players and the start it gives sits BEFORE Kalshi's expected end and within
    TENNIS_START_MAX_H of it. A match that has already started is dropped, which is the whole
    point of doing this. Fail-soft: no schedule, no change.
    """
    now = now or datetime.now(timezone.utc)
    sched = tennis_starts() if schedule is None else schedule
    if not sched:
        return rows, dict(matched=0, dropped=0, feed=False)
    kept, matched, dropped = [], 0, 0
    for r in rows:
        if r.get("venue") != "kalshi":
            kept.append(r)
            continue
        try:
            est = datetime.fromisoformat(str(r["start"]))
        except (KeyError, TypeError, ValueError):
            kept.append(r)
            continue
        if est.tzinfo is None:
            est = est.replace(tzinfo=timezone.utc)
        best = None
        for a, b, ko in sched:
            score, flip = pair_match(r["side_a"], r["side_b"], a, b, sport="tennis")
            # Either side of the estimate: three-hours-before-the-expected-end lands a little
            # early as often as a little late, and a one-sided window threw away every match
            # whose real start was the later of the two.
            if score <= 0 or abs(est - ko) > timedelta(hours=TENNIS_START_MAX_H):
                continue
            if best is None or score > best[0]:
                best = (score, ko)
        if not best:
            kept.append(r)                        # unverified: logged, never published
            continue
        ko = best[1]
        if ko <= now:
            dropped += 1                          # under way already
            continue
        matched += 1
        kept.append(dict(r, start=ko.isoformat(), date=ko.strftime("%Y-%m-%d"),
                         start_source="tennisexplorer", venue_start=est.isoformat()))
    return kept, dict(matched=matched, dropped=dropped, feed=True)


def fetch_tennis_fav_band(sport, universe=None):
    """The sport's own favourite band: narrowed for tennis, the full band for MMA."""
    return band_picks(sport, fav_band(sport), universe)


# The comparison window for tennis_fav_band_3h. Fixed 2026-09-25 with the lane.
TENNIS_FAV_3H = timedelta(hours=3)


def fetch_tennis_fav_band_3h(sport, universe=None, now=None):
    """tennis_fav_band's band, only when the start is within TENNIS_FAV_3H.

    tennis_fav_band itself is not filtered. A match inside the window is returned
    here AND there; publish logs both, under two sources. See that source's note.
    """
    if sport != "tennis":
        return []
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    uni = universe if universe is not None else (UNIVERSE or {})
    near = []
    for r in uni.get(sport) or []:
        try:
            start = datetime.fromisoformat(str(r.get("start")))
        except (TypeError, ValueError):
            continue
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        lead = start - now
        if timedelta(0) < lead <= TENNIS_FAV_3H:
            near.append(r)
    return band_picks(sport, fav_band("tennis"), {sport: near})


def fetch_tt_band(sport, universe=None):
    """TT_BAND, table tennis only — a confirmation test of one suspect band (see SOURCES)."""
    return band_picks(sport, TT_BAND, universe)


MLB_STREAK_WINDOW, MLB_HOT, MLB_COLD, MLB_MIN_GAMES = 10, 7, 3, 20
_MLB_GAMES = None


def mlb_games(season=None, refresh=False):
    """Completed regular-season games this season from the MLB Stats API, oldest first:
    [{"start", "home", "away", "home_runs", "away_runs"}]. Cached for the run."""
    global _MLB_GAMES
    if _MLB_GAMES is not None and not refresh:
        return _MLB_GAMES
    now = datetime.now(timezone.utc)
    season = season or now.year
    try:
        d = _get(f"https://statsapi.mlb.com/api/v1/schedule?sportId=1&gameType=R"
                 f"&startDate={season}-03-01&endDate={now.strftime('%Y-%m-%d')}", tries=2, timeout=60) or {}
    except RuntimeError:
        return []
    out = []
    for day in d.get("dates") or []:
        for g in day.get("games") or []:
            h, a = (g.get("teams") or {}).get("home") or {}, (g.get("teams") or {}).get("away") or {}
            if (g.get("status") or {}).get("codedGameState") != "F" or h.get("score") is None or a.get("score") is None:
                continue
            out.append(dict(start=g["gameDate"], home=h["team"]["name"], away=a["team"]["name"],
                            home_runs=h["score"], away_runs=a["score"]))
    out.sort(key=lambda g: g["start"])
    _MLB_GAMES = out
    return out


def mlb_form(games, team, before):
    """(wins in the last MLB_STREAK_WINDOW games, games played this season) for the MLB Stats API
    team best matching `team`, from games that started strictly before `before`."""
    names = {g["home"] for g in games} | {g["away"] for g in games}
    scored = sorted(((_score(team, n, "mlb"), n) for n in names), reverse=True)
    if not scored or scored[0][0] < 0.8 or (len(scored) > 1 and scored[1][0] == scored[0][0]):
        return None, 0
    name = scored[0][1]
    cut = before.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M")
    mine = [g for g in games if name in (g["home"], g["away"]) and g["start"][:16] < cut]
    wins = [(g["home_runs"] > g["away_runs"]) == (g["home"] == name) for g in mine]
    return sum(wins[-MLB_STREAK_WINDOW:]), len(mine)


def fetch_mlb_fade_streak(sport, universe=None, games=None):
    """Back the cold team (<= MLB_COLD of its last 10) against a hot one (>= MLB_HOT of 10)."""
    games = mlb_games() if games is None else games
    rows = list(_rule_rows(sport, universe))
    out = []
    for r, ko in rows:
        if ko.tzinfo is None:
            ko = ko.replace(tzinfo=timezone.utc)
        # Only each team's NEXT listed game. Form is read now, so a bet on game 2 or 3 of a series
        # would use form that game 1 is about to change — and repeat the same bet three times.
        # The later games are picked up by later runs, once the games before them are final.
        teams = (r["side_a"], r["side_b"])
        if any(o is not r and o2 < ko and any(_score(t, x, "mlb") >= 0.8 for t in teams for x in (o["side_a"], o["side_b"]))
               for o, o2 in ((o, o2 if o2.tzinfo else o2.replace(tzinfo=timezone.utc)) for o, o2 in rows)):
            continue
        wa, na = mlb_form(games, r["side_a"], ko)
        wb, nb = mlb_form(games, r["side_b"], ko)
        if wa is None or wb is None or min(na, nb) < MLB_MIN_GAMES:
            continue
        if wa <= MLB_COLD and wb >= MLB_HOT:
            out.append(dict(market_id=r["market_id"], pick="a"))
        elif wb <= MLB_COLD and wa >= MLB_HOT:
            out.append(dict(market_id=r["market_id"], pick="b"))
    return out


# ---------------------------------------------------------------------------
# NHL (registered 2026-09-17, before the 2026-27 season starts)
# ---------------------------------------------------------------------------
# Research: 560 games of the 2025-26 season, priced off Kalshi's last hourly candle before
# puck drop, scored after fees against blind baselines.
#   - The moneyline is efficiently priced in every slice (favourite -5.2%, underdog -3.3%,
#     home -4.6%, the 0.60-0.75 band -10.1%). Nothing to bet there.
#   - Form does not travel: backing a team on a 7+/10 win rate returned +0.4% against its
#     price, the same regression to the mean the soccer streak work found.
#   - Rest does. A rested home team against a visitor on the second night of a back-to-back
#     won 64.9% against a 58.3% price (n=74, +7.5%), and it did not decay across the season
#     (+11.1%, -8.5%, +18.7% by period). 74 bets is a hint, not a result, which is what the
#     Sandbox is for. Cutoffs below were fixed before this rule logged anything.
#   - The underdog +1.5 looked strong (+15.7% over October and November) and then died once
#     Kalshi's NHL spread market had traded for a few weeks: -3.7% in December and January,
#     -6.8% from February. That is an early-season pricing artifact, not an edge. It is
#     logged as an OBSERVATION only, to find out whether the softness returns when the
#     market relists each October.
NHL_API = "https://api-web.nhle.com/v1"
NHL_B2B_MAX_DAYS = 1.6           # the second night of a back-to-back
NHL_RESTED_MIN_DAYS = 1.9        # a day off or more
# Kalshi writes five clubs with shorter codes than the NHL does.
NHL_CODES = {"LAK": "LA", "NJD": "NJ", "TBL": "TB", "SJS": "SJ"}
# Preseason games are listed weeks early and quoted at 0.65 on BOTH sides. A pair of asks
# that sums to more than this is a placeholder, not a price, and is not logged.
NHL_MAX_OVERROUND = 1.15
_nhl_schedule = None


def _nhl_tight(m, side):
    """Is this side of a Kalshi market actually quoted (a real bid under a real ask)?"""
    ask = _num(m.get("yes_ask_dollars") if side == "a" else m.get("no_ask_dollars"))
    bid = _num(m.get("yes_bid_dollars") if side == "a" else m.get("no_bid_dollars"))
    return bool(bid is not None and ask is not None and bid > 0 and ask < 1
                and ask - bid <= KALSHI_MAX_SPREAD)


def nhl_schedule(now=None, refresh=False):
    """Every NHL game in the fortnight around today, oldest first, from the NHL's own API:
    [{"start", "home", "away", "state"}] with Kalshi's team codes. Cached for the run.

    Two weeks is the whole requirement: the rule needs yesterday's games (to know who is on
    a back-to-back) and the next few days (the games being priced)."""
    global _nhl_schedule
    if _nhl_schedule is not None and not refresh:
        return _nhl_schedule
    now = now or datetime.now(timezone.utc)
    out, seen = [], set()
    for back in (7, 0):
        day = (now - timedelta(days=back)).strftime("%Y-%m-%d")
        try:
            d = _get(f"{NHL_API}/schedule/{day}", tries=2, timeout=30) or {}
        except RuntimeError:
            continue
        for week in d.get("gameWeek") or []:
            for g in week.get("games") or []:
                if g.get("id") in seen:
                    continue
                seen.add(g.get("id"))
                code = lambda t: NHL_CODES.get(str(t.get("abbrev")), str(t.get("abbrev")))
                try:
                    start = datetime.fromisoformat(str(g["startTimeUTC"]).replace("Z", "+00:00"))
                except (KeyError, TypeError, ValueError):
                    continue
                out.append(dict(start=start, home=code(g.get("homeTeam") or {}),
                                away=code(g.get("awayTeam") or {}),
                                state=str(g.get("gameState") or "")))
    _nhl_schedule = sorted(out, key=lambda g: g["start"])
    return _nhl_schedule


def nhl_rest_days(games, team, before):
    """Days between `team`'s previous game and `before`, or None when the schedule does not
    reach back far enough to say (the first days of a season, or a missing feed)."""
    prev = [g["start"] for g in games
            if g["start"] < before and team in (g["home"], g["away"])]
    if not prev:
        return None
    return (before - max(prev)).total_seconds() / 86400


def fetch_nhl(horizon_days=4, now=None, stats=None, schedule=None):
    """{"nhl_rest": [moneyline rows], "nhl_pl": [puck-line rows]} from Kalshi's open NHL
    markets, each row tied to the NHL's own scheduled start.

    Side A of a moneyline row is whichever side kalshi_sides calls A — the same mapping
    settlement uses — so a bet cannot change meaning between being placed and being graded.
    The puck-line row is the FAVOURITE's "wins by over 1.5" market: Yes is the favourite
    covering, No is the underdog +1.5.
    """
    now = now or datetime.now(timezone.utc)
    horizon = now + timedelta(days=horizon_days)
    games = nhl_schedule(now) if schedule is None else schedule
    stats = stats if stats is not None else {}
    out = {"nhl_rest": [], "nhl_pl": []}

    def game_for(codes, est):
        """The NHL game a Kalshi event is about: same two clubs, starting within a day."""
        best = None
        for g in games:
            if {g["home"], g["away"]} != set(codes) or abs((g["start"] - est).days) > 1:
                continue
            if best is None or abs(g["start"] - est) < abs(best["start"] - est):
                best = g
        return best

    events = {}
    for m in _kalshi_open("KXNHLGAME") + _kalshi_open("KXNHLSPREAD"):
        events.setdefault(str(m.get("event_ticker") or ""), []).append(m)
    for et, ms in events.items():
        series = et.split("-")[0]
        est = kalshi_date(et)
        try:
            est = datetime.fromisoformat(f"{est}T00:00:00+00:00")
        except (TypeError, ValueError):
            continue
        stats["listed"] = stats.get("listed", 0) + 1
        if series == "KXNHLGAME":
            sides = kalshi_sides(et, ms)
            by_side = {sides.get(_kalshi_code(m)): m for m in ms if sides.get(_kalshi_code(m)) in ("a", "b")}
            if len(by_side) != 2:
                continue
            g = game_for([_kalshi_code(m) for m in by_side.values()], est)
            if not g or not (now < g["start"] <= horizon):
                continue
            pa, pb = _num(by_side["a"].get("yes_ask_dollars")), _num(by_side["b"].get("yes_ask_dollars"))
            if pa is None or pb is None or pa + pb > NHL_MAX_OVERROUND:
                continue          # preseason books quote both sides at 0.65: not a price
            code_of = {_kalshi_code(m): k for k, m in by_side.items()}
            home_side = code_of.get(g["home"])
            label = (f"{_kalshi_name(by_side['b' if home_side == 'a' else 'a'])} at "
                     f"{_kalshi_name(by_side[home_side])}") if home_side else \
                    f"{_kalshi_name(by_side['a'])} v {_kalshi_name(by_side['b'])}"
            out["nhl_rest"].append(dict(
                sport="nhl_rest", venue="kalshi", market_id=et, label=label,
                side_a=_kalshi_name(by_side["a"]), side_b=_kalshi_name(by_side["b"]),
                code_a=_kalshi_code(by_side["a"]), code_b=_kalshi_code(by_side["b"]),
                price_a=pa, price_b=pb, price_draw=None,
                tradeable={s: _nhl_tight(by_side[s], s) for s in ("a", "b")},
                untraded=not any(_nhl_tight(by_side[s], s) for s in ("a", "b")),
                start=g["start"].isoformat(), date=g["start"].strftime("%Y-%m-%d"),
                volume=0.0, nhl_home=g["home"], nhl_away=g["away"], start_source="nhl",
                url=f"https://kalshi.com/markets/{series.lower()}"))
        else:
            cover = [m for m in ms if "over 1.5" in str(m.get("yes_sub_title") or "")]
            if len(cover) != 2:
                continue
            g = game_for([re.sub(r"\d+$", "", _kalshi_code(m)) for m in cover], est)
            if not g or not (now < g["start"] <= horizon):
                continue
            priced = [(m, _num(m.get("yes_ask_dollars")), _num(m.get("no_ask_dollars"))) for m in cover]
            if any(p is None or n is None for _m, p, n in priced):
                continue
            m, ya, na = max(priced, key=lambda x: x[1])                   # the favourite's market
            if ya + na > NHL_MAX_OVERROUND:
                continue
            out["nhl_pl"].append(dict(
                sport="nhl_pl", venue="kalshi_binary", market_id=m["ticker"],
                label=str(m.get("yes_sub_title") or m["ticker"])[:90],
                side_a="Yes", side_b="No", price_a=ya, price_b=na, price_draw=None,
                tradeable={"a": _nhl_tight(m, "a"), "b": _nhl_tight(m, "b")},
                untraded=not (_nhl_tight(m, "a") or _nhl_tight(m, "b")),
                start=g["start"].isoformat(), date=g["start"].strftime("%Y-%m-%d"),
                volume=0.0, nhl_home=g["home"], nhl_away=g["away"], start_source="nhl",
                url=f"https://kalshi.com/markets/{series.lower()}"))
    return out


def fetch_nhl_rest_edge(sport, universe=None, schedule=None):
    """Back the HOME team where it has had a day off or more and the visitor played last
    night. Rest is known from the schedule days ahead; nothing here reads form."""
    games = nhl_schedule() if schedule is None else schedule
    out = []
    for r, ko in _rule_rows(sport, universe):
        if ko.tzinfo is None:
            ko = ko.replace(tzinfo=timezone.utc)
        home, away = r.get("nhl_home"), r.get("nhl_away")
        rest_h, rest_a = nhl_rest_days(games, home, ko), nhl_rest_days(games, away, ko)
        if rest_h is None or rest_a is None:
            continue
        if rest_h >= NHL_RESTED_MIN_DAYS and rest_a <= NHL_B2B_MAX_DAYS:
            pick = "a" if r.get("code_a") == home else "b" if r.get("code_b") == home else None
            if pick:
                out.append(dict(market_id=r["market_id"], pick=pick))
    return out


def fetch_nhl_dog_pl(sport, universe=None):
    """Back the underdog +1.5 (No on the favourite winning by over 1.5) on every listed game.
    An observation, not a candidate rule — see the note above."""
    return [dict(market_id=r["market_id"], pick="b") for r, _ko in _rule_rows(sport, universe)]


# ---------------------------------------------------------------------------
# Daily commodities (registered 2026-09-18)
# ---------------------------------------------------------------------------
# Kalshi lists a daily ladder of "Above $X" strikes on WTI, Brent, gold, silver, copper,
# natural gas and AAA retail gasoline. Research over 61 days (2026-07-13 to 09-17), pricing
# every sampled strike 6h before close — the lead this domain already logs at:
#   - The market is EFFICIENT where it is normally traded. Backing whichever side the market
#     favours won 87.7% against an 87.5% price: the spread and the fee, nothing else.
#   - The favourite-longshot bias is real in mid-price — 5c longshots landed 2-4% — but the
#     spread swallows it: the 0.90-0.97 band returned -1.3%.
#   - The FAR TAIL is the exception. Sides priced 0.97-0.995 won 99.3% against 98.3% priced
#     (+1.0% after fees), on 778 bets over 224 day-commodity clusters. Clustered by day and
#     resampled 4,000 times, the ROI interval was +0.3% to +1.5% and no resampled world lost
#     money. It held in both halves (+1.4%, +0.8%) and at every band from 0.95 up.
# Only 46% of sampled strikes had a two-sided book; an untraded strike quotes 0.99 against a
# 1c bid, and reading that as a price is what made natural gas look like a 30-point edge. The
# spread gate in fetch_kalshi_binary is therefore load-bearing here, not hygiene.
#
# WHAT THIS RULE IS: selling the far tail for a penny. Five of 778 bets lost, each costing
# ~60 wins, and two months contained no commodity shock. That is exactly the shape that looks
# good until it does not, which is why it is logged and measured rather than traded.
CMD_BAND = (0.97, 0.995)


# ---------------------------------------------------------------------------
# AAA gasoline no-change rule — pre-registered 2026-09-21
# ---------------------------------------------------------------------------
# Replaces the far-tail rule, which backed the near-certain side of every strike on every
# ladder: 200-360 bets a day for a penny each. This makes at most ONE bet a day, at prices
# where a win pays 25% or more.
#
# How it was found, stated in full because it decides how far to trust it. The national AAA
# average moves slowly and keeps moving the same way: over 68 days it went the same direction
# as the day before 78% of the time (z +4.5), the only one of seven daily commodities to do so.
# A rule was pre-registered to bet that the trend CONTINUES, and it failed its backtest:
# -18.0% following on 39 bets (-12.5% and -24.4% in the two halves), +2.4% fading. The market
# already prices the trend, and better — pump prices follow wholesale gasoline with a lag, and
# a model that only reads gas's own past cannot see that.
#
# This rule is the variant that projects NO change: tomorrow at yesterday's figure. It ran
# +15.0% following and -21.3% fading on 34 bets (z +1.00) — the two directions disagreeing
# cleanly, the shape a real signal has. The claim is that the market over-extrapolates the gas
# trend. But it was found by trying a second version after the first failed, so it is an
# in-sample result, not evidence. The forward record is the test.
#
# The rule is the backtested variant exactly: the projection is yesterday's figure; sigma is
# the residual sd of today's change on yesterday's, fitted on days strictly before; the
# chance of a strike is Phi((projection - strike) / sigma); the bet is the side beating its
# ask by 5c after the Kalshi fee, asks 0.25-0.80, on a two-sided book; one strike a day, the
# largest edge; and only in the last hours before the ladder closes, which is when the
# backtest priced it (02:00 UTC, the ladder closing 03:59) and when the book is deepest.
GAS_SERIES = "KXAAAGASD"          # the national average; the 21 state series move with it
GAS_EDGE = 0.05
GAS_BAND = (0.25, 0.80)
GAS_MIN_HIST = 14
GAS_WINDOW_H = 4
_gas_hist = None


def gas_history(refresh=False):
    """[(date, value)] of the national AAA average from Kalshi's settled daily ladders.

    Sorted by DATE. Sorted by event ticker it reads AUG before JUL, which is how the first
    backtest of this rule fitted itself on future days and printed a fake +33.6%.
    """
    global _gas_hist
    if _gas_hist is not None and not refresh:
        return _gas_hist
    out, cur = {}, None
    for _ in range(3):
        q = {"series_ticker": GAS_SERIES, "with_nested_markets": "true", "limit": 200}
        if cur:
            q["cursor"] = cur
        try:
            d = _get("https://api.elections.kalshi.com/trade-api/v2/events?" + urllib.parse.urlencode(q),
                     tries=2, timeout=30)
        except RuntimeError:
            break
        for e in (d or {}).get("events") or []:
            ms = e.get("markets") or []
            vals = {m.get("expiration_value") for m in ms if m.get("expiration_value") not in (None, "")}
            if ms and len(vals) == 1:
                try:
                    out[max(str(m.get("close_time") or "") for m in ms)[:10]] = float(vals.pop())
                except ValueError:
                    pass
        cur = (d or {}).get("cursor")
        if not cur:
            break
    _gas_hist = sorted(out.items())
    return _gas_hist


def _gas_sigma(vals):
    """Residual sd of today's change on yesterday's (slope through the origin), or None."""
    d = [vals[i] - vals[i - 1] for i in range(1, len(vals))]
    pairs = [(d[i - 1], d[i]) for i in range(1, len(d))]
    if len(pairs) < GAS_MIN_HIST:
        return None
    sxx = sum(a * a for a, _ in pairs)
    lam = sum(a * b for a, b in pairs) / sxx if sxx else 0.0
    res = [b - lam * a for a, b in pairs]
    return math.sqrt(sum(r * r for r in res) / (len(res) - 1))


def fetch_gas_nochange(sport, universe=None, history=None, now=None):
    """At most one bet a day on the national AAA ladder: the strike yesterday's figure misprices most."""
    now = now or datetime.now(timezone.utc)
    rows = [r for r in ((universe if universe is not None else (UNIVERSE or {})).get(sport) or [])
            if r.get("series") == GAS_SERIES and (r.get("market") or {}).get("strike_type") == "greater"]
    if not rows:
        return []
    hist = sorted(gas_history() if history is None else history)   # by date, whatever it arrived as
    by_day, out = {}, []
    for r in rows:
        by_day.setdefault(r["date"], []).append(r)
    for day, ladder in sorted(by_day.items()):
        try:
            close = datetime.fromisoformat(str(ladder[0]["market"]["close_time"]).replace("Z", "+00:00"))
            prev = (datetime.fromisoformat(day) - timedelta(days=1)).strftime("%Y-%m-%d")
        except (KeyError, ValueError, TypeError):
            continue
        if not (close - timedelta(hours=GAS_WINDOW_H) <= now < close):
            continue                            # only in the last hours before the ladder closes
        prior = [(dt, v) for dt, v in hist if dt < day]
        if not prior or prior[-1][0] != prev:
            continue                            # yesterday's figure is not out: never guess it
        sd = _gas_sigma([v for _dt, v in prior])
        if not sd:
            continue
        proj, best = prior[-1][1], None
        for r in ladder:
            try:
                p_yes = 0.5 * (1 + math.erf((proj - float(r["market"]["floor_strike"])) / sd / math.sqrt(2)))
            except (KeyError, TypeError, ValueError):
                continue
            for side, p_mod, ask in (("a", p_yes, r.get("price_a")), ("b", 1 - p_yes, r.get("price_b"))):
                if ask is None or not (r.get("tradeable") or {}).get(side):
                    continue
                if not GAS_BAND[0] <= ask <= GAS_BAND[1]:
                    continue
                edge = p_mod - ask - 0.07 * ask * (1 - ask)
                if edge >= GAS_EDGE and (best is None or edge > best[0]):
                    best = (edge, r["market_id"], side)
        if best:
            out.append(dict(market_id=best[1], pick=best[2]))
    return out


def fetch_cmd_tail(sport, universe=None):
    """Back the near-certain side of a daily commodity strike, priced in CMD_BAND."""
    lo, hi = CMD_BAND
    out = []
    for r in (universe if universe is not None else (UNIVERSE or {})).get(sport) or []:
        for side in ("a", "b"):
            p = r.get(f"price_{side}")
            if p is None or not (r.get("tradeable") or {}).get(side):
                continue
            if lo <= p <= hi:
                out.append(dict(market_id=r["market_id"], pick=side))
                break                      # one bet per strike: the two sides cannot both win
    return out


def fetch_cmd_market(sport, universe=None):
    """The Kalshi price on every listed daily commodity strike — never a bet, the population
    the tail rule is judged against."""
    rows = (universe if universe is not None else (UNIVERSE or {})).get(sport) or []
    return [dict(market_id=r["market_id"], prob_a=r.get("mid_a", r["price_a"])) for r in rows]


def fetch_goals_market(sport, universe=None):
    """The Kalshi midpoint on every listed goals market — never a bet (edge 0 by construction)."""
    rows = (universe if universe is not None else (UNIVERSE or {})).get(sport) or []
    return [dict(market_id=r["market_id"], prob_a=r.get("mid_a", r["price_a"])) for r in rows]


CORNER_FRAGS = {"EPL": "Premier League", "LALIGA": "La Liga", "SERIEA": "Serie A",
                "BUNDESLIGA": "Bundesliga", "LIGUE1": "Ligue 1", "MLS": "MLS",
                "UCL": "Champions League", "LIGAMX": "Liga MX"}
CORNERS_LEAD_H = 4              # the research priced the last book before kickoff
CORNERS_EDGE = 0.05             # pre-registered: model beats the No ask by 5c after fees
CORNERS_MIN_GAMES = 5
CORNERS_DISP = {"total": 1.28, "team": 1.74}     # variance / mean, ESPN 7,631 matches


def fetch_kalshi_corners(horizon_days=4, fixtures=None, now=None, stats=None, events_by_series=None):
    """Kalshi total-corner ("N+ corners") and team-corner ("Team: N+") rungs as yes/no rows, each
    tied to its ESPN league fixture. Side a = Yes (N or more), side b = No."""
    now = now or datetime.now(timezone.utc)
    fixtures = _espn_fixtures() if fixtures is None else fixtures
    upcoming = [(ko, f) for ko, f in _upcoming_espn(fixtures, now, horizon_days)
                if f.get("comp", "league") == "league"]
    rows, listed = [], 0
    for frag, league in CORNER_FRAGS.items():
        for kind, series in (("total", f"KX{frag}CORNERS"), ("team", f"KX{frag}TCORNERS")):
            for ev in _kalshi_open_events(series, events_by_series):
                hit = _espn_fixture_for(ev, upcoming)
                for m in ev.get("markets") or []:
                    sub_ = str(m.get("yes_sub_title") or "")
                    mm = re.search(r"(\d+)\+", sub_)
                    if not mm or str(m.get("status", "")).lower() not in ("active", "open"):
                        continue
                    listed += 1
                    if not hit:
                        continue
                    ko, f = hit
                    n = int(mm.group(1))
                    extra = dict(corner_kind=kind, corner_n=n)
                    if kind == "team":
                        who = sub_.split(":")[0]
                        sh, sa = _score(who, f["home"], "soccer"), _score(who, f["away"], "soccer")
                        if max(sh, sa) < 0.5 or sh == sa:
                            continue
                        team, opp = (f["home"], f["away"]) if sh > sa else (f["away"], f["home"])
                        extra.update(team=team, opponent=opp)
                        label = f"{f['home']} v {f['away']}: {team} {n}+ corners"
                    else:
                        label = f"{f['home']} v {f['away']}: {n}+ corners"
                    row = _yes_no_row(m, "soccer_corners", label, ko, f, league, series, **extra)
                    if row:
                        rows.append(row)
    rows.sort(key=lambda r: r["start"])
    if stats is not None:
        stats["listed"] = listed
        stats["priced"] = sum(1 for r in rows if not r["untraded"])
    return rows


def corner_form(fixtures, team, before, window=10):
    """(avg corners won, avg corners conceded, games) over `team`'s last `window` competitive games
    with corners reported, strictly before `before`."""
    games = []
    for f in fixtures:
        if (not f.get("played") or f.get("home_corners") is None or f.get("away_corners") is None
                or not f.get("competitive", True) or team not in (f.get("home"), f.get("away"))
                or not f.get("kickoff")):
            continue
        try:
            ko = datetime.fromisoformat(str(f["kickoff"]).replace("Z", "+00:00"))
        except ValueError:
            continue
        if ko < before:
            won, conc = ((f["home_corners"], f["away_corners"]) if f["home"] == team
                         else (f["away_corners"], f["home_corners"]))
            games.append((ko, won, conc))
    games.sort()
    last = games[-window:]
    if not last:
        return None, None, 0
    return sum(g[1] for g in last) / len(last), sum(g[2] for g in last) / len(last), len(last)


def nb_at_least(n, mean, disp):
    """P(X >= n), negative binomial with this mean and variance = disp x mean (Poisson at disp 1)."""
    if mean <= 0:
        return 0.0 if n > 0 else 1.0
    if disp <= 1.0001:
        return 1 - sum(math.exp(-mean) * mean ** k / math.factorial(k) for k in range(n))
    p = 1 / disp
    r = mean * p / (1 - p)
    pmf = lambda k: math.exp(math.lgamma(k + r) - math.lgamma(k + 1) - math.lgamma(r)
                             + r * math.log(p) + k * math.log(1 - p))
    return 1 - sum(pmf(k) for k in range(n))


def corners_model(fixtures, r, ko):
    """The form model's P(N+ corners) for one corners row, or None without enough history."""
    def side(team, opp):
        w, _c, n1 = corner_form(fixtures, team, ko)
        _w, c, n2 = corner_form(fixtures, opp, ko)
        if n1 < CORNERS_MIN_GAMES or n2 < CORNERS_MIN_GAMES:
            return None
        return (w + c) / 2
    if r.get("corner_kind") == "team":
        lam = side(r.get("team"), r.get("opponent"))
    else:
        lh, la = side(r.get("espn_home"), r.get("espn_away")), side(r.get("espn_away"), r.get("espn_home"))
        lam = None if lh is None or la is None else lh + la
    if lam is None:
        return None
    return nb_at_least(int(r["corner_n"]), lam, CORNERS_DISP[r.get("corner_kind", "total")])


def fetch_corners_under(sport, universe=None, fixtures=None, now=None):
    """Buy No where the model's P(under) beats the No ask by CORNERS_EDGE after the Kalshi fee."""
    fixtures = _espn_fixtures() if fixtures is None else fixtures
    now = now or datetime.now(timezone.utc)
    out = []
    for r, ko in _rule_rows(sport, universe):
        if not (now < ko <= now + timedelta(hours=CORNERS_LEAD_H)):
            continue
        if not (r.get("tradeable") or {}).get("b"):
            continue
        p = corners_model(fixtures, r, ko)
        if p is None:
            continue
        no_ask = float(r["price_b"])
        fee = 0.07 * no_ask * (1 - no_ask)
        if (1 - p) - no_ask - fee >= CORNERS_EDGE:
            out.append(dict(market_id=r["market_id"], pick="b"))
    return out


def fetch_corners_market(sport, universe=None):
    """The Kalshi midpoint on every listed corners rung — never a bet."""
    rows = (universe if universe is not None else (UNIVERSE or {})).get(sport) or []
    return [dict(market_id=r["market_id"], prob_a=r.get("mid_a", r["price_a"])) for r in rows]


# ---------------------------------------------------------------------------
# Cup mismatch over 1.5 — pre-registered 2026-09-21
# ---------------------------------------------------------------------------
# A cup can pair a top-flight club with a side three divisions below it. The claim is that a
# mismatch produces goals and the market prices a cup tie's goals too much like a league
# match's. The mismatch is read from the tie's OWN match-winner markets, in the same run as
# the over-1.5 price, so nothing here is known only after kickoff and nothing is fitted.
#
# The threshold is set on the mechanism, before any result was looked at: the favourite's
# own win price at the midpoint, 0.70 or more. A draw takes a fifth to a quarter of a soccer
# match, so a side priced 0.70 outright leaves its opponent roughly 5-10%. There is no cap
# on the over-1.5 price. The idea came from Taça de Portugal overs priced 0.70-0.77, and
# capping to that band would fit the rule to the one sample it was found in.
CUP_MISMATCH_FAV = 0.70


def _fixture_code(r):
    """('Taça de Portugal', '26SEP19IMOTON'): one tie's markets share this across series."""
    return (r.get("league"), (str(r.get("market_id") or "").split("-") + ["", ""])[1])


def fetch_o15_cup_mismatch(sport, universe=None):
    """Back over 1.5 in a cup tie where one side is priced CUP_MISMATCH_FAV+ to win outright."""
    uni = universe if universe is not None else (UNIVERSE or {})
    # The tie's match-winner markets are the +0.5 domain's rows: "X to win", Yes = X wins.
    # Read only from a real book. An empty one (a 0.80 ask over no bid, as the Copa del Rey's
    # preliminary round sat five days out) has a midpoint that is pure placeholder, and one
    # of those reading 0.70+ beside a properly priced over would invent a mismatch.
    wins = {}
    for r in uni.get(sport.replace("soccer_o15", "soccer_p05")) or []:
        p = r.get("mid_a", r.get("price_a"))
        if p is not None and not r.get("untraded") and (r.get("tradeable") or {}).get("a", True):
            wins.setdefault(_fixture_code(r), []).append(float(p))
    return [dict(market_id=r["market_id"], pick="a") for r, _ko in _rule_rows(sport, universe)
            if max(wins.get(_fixture_code(r)) or [0.0]) >= CUP_MISMATCH_FAV]


# ---------------------------------------------------------------------------
# Over 1.5, RANKED — pre-registered 2026-09-24
# ---------------------------------------------------------------------------
# Every other over-1.5 rule here is a THRESHOLD: it takes every match clearing a bar and
# lands on their average. On five seasons that average is 81.4%, against a Kalshi ask that
# has averaged 0.850 and so demands 85% — losing by construction before any bad luck, which
# is what o15_form_l10's live -10.4% on 25 bets is.
#
# This one RANKS instead. On 401 matchdays with 20+ candidates (median pool 45 games, which
# is an ordinary international or midweek slate), taking every candidate hit 77.0%, the top
# 10 hit 80.8%, the top 2 hit 82.7% and the top 1 hit 84.5%. Ranking is worth about 7.5pp
# over taking the field, and no threshold rule can collect it.
#
# WHAT IT RANKS ON, AND WHY NOT THE OBVIOUS THING. Goals come from MISMATCHES, not from good
# matches. Over five seasons and 11,153 priced matches, over-1.5 runs 73.7% where the
# favourite is 0.30-0.40 to win and 87.5% where it is 0.80+, rising monotonically the whole
# way; matches with every price above 2.00 go over 1.5 4.67pp LESS often than matches with a
# clear favourite (z -5.79). A competitive marquee tie is the worst over-1.5 candidate on the
# board, not the best. So the rank is the favourite's own de-vigged win probability, read
# from the same fixture's match-winner markets in the same run -- the generalisation of
# o15_cup_mismatch from cups to everything.
#
# AND THE SIGNAL IS ALREADY PRICED, WHICH IS THE POINT OF THE CEILING. Against the market's
# own de-vigged fair, the mismatch buckets sit at +0.81, -0.05, +1.13, +1.08 and -0.58pp --
# nothing reaching z 1.1. Ranking on it beats the field but not the price, so this rule can
# only earn from paying LESS than the ranked candidate is worth. Hence O15_RANK_MAX_ASK: it
# fires on the top O15_RANK_TAKE of a day's board and only under the ceiling. Backtested at
# 0.80 the top 2 return +3.3% and the top 1 +5.7%, against -2.7% and -0.5% at 0.85.
#
# The ceiling leaves a real choice rather than starving the lane: of 191 Kalshi over-1.5 asks
# the Sandbox has logged (median 0.820), 43% sit at or under 0.80, so a 45-game slate still
# offers about 19 candidates to rank.
#
# Judged against the same population every goals rule is: backing Yes on every listed
# over-1.5 market. That is the only question it asks -- whether ranking and a ceiling beat
# taking the board.
O15_RANK_TAKE, O15_RANK_MAX_ASK, O15_RANK_MIN_POOL = 2, 0.80, 6
# A mismatch only makes goals if the underdog LEAKS them. Strong attack against a leaky
# defence scores freely; strong attack against a low block does not, and that fixture is the
# trap this rule would otherwise walk into, because it ranks HIGH on mismatch while being a
# poor over-1.5 bet. Pre-registered as one test on 2026-09-24, from the mechanism rather than
# by searching: within mismatches (fav 0.60+), an underdog that conceded 2+ in 7+ of its last
# 10 gives 83.15% over 1.5 against 80.56% for the rest (+2.59pp, z +1.31) -- nearly twice
# what the mirror-image SCORING form of the underdog was worth (+1.41pp, z +0.67).
#
# The rule takes the EXCLUSION, not the selection. The tempting cell is "conceded 2+ in 8-10
# of 10" at +5.91pp, but that is n=153 and one of four buckets I looked at. The exclusion
# below rests on n=616 and is a NEGATIVE signal, which is far harder to manufacture by
# searching because it is not selecting on the outcome you want: underdogs conceding 2+ in
# fewer than 4 of their last 10 went over 1.5 just 78.41%, -2.61pp on the mismatch baseline
# (z -1.65). Dropping them lifts the selection to 81.68%, worth about +0.8pp of ROI under
# the ceiling; taking the leaky cell instead would claim +2.7pp on a quarter of the evidence.
#
# The signal is PRICED (leaky v the market's own fair: +1.13pp, z +0.49), which does not
# matter here. This rule earns by buying a high-probability event under a ceiling, so
# anything that raises the true probability of what gets SELECTED converts into ROI whether
# the market knows it or not.
O15_RANK_MIN_LEAK = 4               # underdog must have conceded 2+ in 4+ of its last 10


def rank_o15_candidates(sport, universe=None):
    """[(fav_prob, underdog, row)] for one over-1.5 domain, best-ranked first.

    The rank is the favourite's de-vigged win probability on the same fixture, taken from the
    match-winner rows the +0.5 domain carries. A fixture with no readable winner book is not
    ranked at all rather than ranked at zero: an unpriced tie is unknown, not competitive.

    On a +0.5 row, `opponent` is the side whose win probability price_a gives ("Maldives to
    win (No = China +0.5)" carries team=China, opponent=Maldives), so the dearest row's
    `team` IS the underdog. Read it from there rather than re-deriving it from the label.
    """
    uni = universe if universe is not None else (UNIVERSE or {})
    wins = {}
    for r in uni.get(str(sport).replace("soccer_o15", "soccer_p05")) or []:
        p = r.get("mid_a", r.get("price_a"))
        if p is not None and not r.get("untraded") and (r.get("tradeable") or {}).get("a", True):
            wins.setdefault(_fixture_code(r), []).append((float(p), r.get("team")))
    out = []
    for r, _ko in _rule_rows(sport, universe):
        w = wins.get(_fixture_code(r))
        if not w:
            continue
        fav, dog = max(w, key=lambda t: t[0])
        out.append((fav, dog, r))
    out.sort(key=lambda t: (-t[0], str(t[2].get("market_id"))))
    return out


def underdog_leaks(dog, ko, fixtures):
    """Did the underdog concede 2+ in O15_RANK_MIN_LEAK+ of its last 10? See O15_RANK_MIN_LEAK.

    An underdog whose form cannot be read is KEPT, not dropped. This rule lives on
    international weeks, where a third of sides have not played ten competitive games in the
    cache at all; dropping every one of them would silently starve the lane rather than
    filter it. The cost is that the exclusion simply does not apply there, which is the
    honest failure — it never claims a fixture passed a test it could not run.
    """
    if not dog:
        return True
    n, _seen, total = team_form(fixtures, dog, ko, lambda gf, ga: ga >= 2, O15_WINDOW)
    if total < GOALS_MIN_GAMES:
        return True
    return n >= O15_RANK_MIN_LEAK


# ---------------------------------------------------------------------------
# A team to score 2+, ranked by MARGIN — pre-registered 2026-09-24
# ---------------------------------------------------------------------------
# The widest rankable spread of any market measured here: over 11,152 priced matches the
# favourite scores twice 40.3% of the time when it is a 0.30-0.40 shot and 80.0% when it is
# 0.80+, rising monotonically the whole way (+35.4pp end to end, z +20.1, against +12.7pp for
# over 1.5). That makes the winner market a strong INDEPENDENT ranker for this one.
#
# AND RANKING ON IT WOULD STILL LOSE, WHICH IS WHY THIS RANKS ON SOMETHING ELSE. Joining 92
# real Kalshi "favourite to score 2+" asks to their own fixture's winner book: a 0.75+
# favourite is asked 0.766 against a true 0.780, a 0.65-0.75 one is asked 0.709 against 0.653.
# Mean margin across all 92 is -3.53pp and the median -3.70pp -- the vig, almost exactly. Take
# the day's two biggest mismatches and you buy at a loss on average, however well the
# mismatch predicts.
#
# So the rank is the MARGIN: what the mismatch says the market is worth, minus what it costs.
# TEAM2_RATE_BY_FAV is that mapping, measured on the 11,152 matches and deliberately coarse --
# it is a lookup from the market's OWN winner price to an empirical rate, not a goals forecast
# of our own. That matters: this project's shrunk-Poisson model lost to the book on all five
# markets it was tried on, and the difference here is that nothing is being predicted. The
# market supplies the probability; only the mapping to "scores twice" is ours.
#
# The top of the board by margin is NOT the top by mismatch, which is the whole point: the
# best of the 92 was Malta at a 0.41 favourite priced 0.30 (+16.3pp), which a mismatch ranker
# would never have looked at, beside Lithuania at 0.76 priced 0.62 (+16.0pp).
#
# Expect it to fire rarely and that is deliberate: 15.2% of those 92 cleared 5pp of margin,
# 6.5% cleared 8pp -- about 1.3 and 0.5 a day at the board sizes we see. A rule that fires
# twice a day here would be buying the -3.53pp average.
# Monotonic by construction, because the mapping is only meaningful if it is. The measured
# 0.40-0.45 and 0.45-0.50 buckets came back at 0.449 (n=2,020) and 0.448 (n=1,704) -- the same
# number, and encoding that inversion would have said a STRONGER favourite scores twice less
# often. Merged into one 0.40-0.50 bucket at the pooled 0.449 rather than carried as signal.
TEAM2_RATE_BY_FAV = ((0.80, 0.800), (0.75, 0.765), (0.70, 0.698), (0.65, 0.677),
                     (0.60, 0.607), (0.55, 0.560), (0.50, 0.522), (0.40, 0.449),
                     (0.00, 0.403))
TEAM2_RANK_TAKE, TEAM2_RANK_MIN_MARGIN = 2, 0.05


def team2_expected_rate(fav_prob):
    """How often a favourite of this strength scores twice. See TEAM2_RATE_BY_FAV."""
    for lo, rate in TEAM2_RATE_BY_FAV:
        if fav_prob >= lo:
            return rate
    return TEAM2_RATE_BY_FAV[-1][1]


def rank_team2_candidates(sport, universe=None):
    """[(margin, fav_prob, underdog, row)] — the favourite's own score-2+ market, best margin
    first. Only the FAVOURITE's market is a candidate: the mapping is measured on favourites,
    and the underdog's own score-2+ rate is a different number entirely (it FALLS with
    mismatch, 70.3% to 50.9%, where the favourite's rises)."""
    uni = universe if universe is not None else (UNIVERSE or {})
    wins = {}
    for r in uni.get(str(sport).replace("soccer_team2", "soccer_p05")) or []:
        p = r.get("mid_a", r.get("price_a"))
        if p is not None and not r.get("untraded") and (r.get("tradeable") or {}).get("a", True):
            wins.setdefault(_fixture_code(r), []).append((float(p), r.get("team")))
    out = []
    for r, _ko in _rule_rows(sport, universe):
        w = wins.get(_fixture_code(r))
        ask = r.get("price_a")
        if not w or ask is None or r.get("untraded"):
            continue
        if not (r.get("tradeable") or {}).get("a", True):
            continue
        fav_prob, dog = max(w, key=lambda t: t[0])
        # On a +0.5 row `team` is the side being backed +0.5, i.e. the UNDERDOG of that pair.
        # This market names a team too; it is a candidate only when that team is the favourite.
        if not r.get("team") or r.get("team") == dog:
            continue
        out.append((team2_expected_rate(fav_prob) - float(ask), fav_prob, dog, r))
    out.sort(key=lambda t: (-t[0], str(t[3].get("market_id"))))
    return out


def fetch_team2_ranked(sport, universe=None, fixtures=None):
    """Back the favourite to score 2+ where the price is furthest below what its own winner
    price says it is worth, skipping low blocks."""
    fixtures = _espn_fixtures() if fixtures is None else fixtures
    out = []
    for margin, _fav, dog, r in rank_team2_candidates(sport, universe):
        if margin < TEAM2_RANK_MIN_MARGIN:
            break                      # sorted, so nothing below here clears it either
        try:
            ko = datetime.fromisoformat(str(r["start"]))
        except (KeyError, ValueError):
            continue
        # A favourite needs its opponent to concede TWICE. The low-block exclusion is a
        # tighter fit here than it was for over 1.5, where one goal from either side did.
        if not underdog_leaks(dog, ko, fixtures):
            continue
        out.append(dict(market_id=r["market_id"], pick="a"))
        if len(out) >= TEAM2_RANK_TAKE:
            break
    return out


def fetch_o15_ranked(sport, universe=None, fixtures=None):
    """Back over 1.5 on the day's top-ranked mismatches, under the ceiling, skipping low blocks.

    The ceiling and the exclusion are applied BEFORE the ranking, not after. Ranking first and
    then dropping what is too dear or too defensive would let a day's two best candidates fall
    away and leave the rule idle beside twenty it never considered.
    """
    fixtures = _espn_fixtures() if fixtures is None else fixtures
    ranked = []
    for fav, dog, r in rank_o15_candidates(sport, universe):
        if r.get("price_a") is None or float(r["price_a"]) > O15_RANK_MAX_ASK:
            continue
        if r.get("untraded") or not (r.get("tradeable") or {}).get("a", True):
            continue
        try:
            ko = datetime.fromisoformat(str(r["start"]))
        except (KeyError, ValueError):
            continue
        if not underdog_leaks(dog, ko, fixtures):
            continue
        ranked.append((fav, r))
    if len(ranked) < O15_RANK_MIN_POOL:
        return []                      # no pool, no choice, no rule
    return [dict(market_id=r["market_id"], pick="a")
            for _f, r in ranked[:O15_RANK_TAKE]]


def fetch_o15_form_l10(sport, universe=None, fixtures=None):
    """Back over 1.5 where BOTH teams' games went over 1.5 in 9+ of their last 10."""
    fixtures = _espn_fixtures() if fixtures is None else fixtures
    over = lambda gf, ga: gf + ga >= 2
    out = []
    for r, ko in _rule_rows(sport, universe):
        h, _hn, hall = team_form(fixtures, r.get("espn_home"), ko, over, O15_WINDOW)
        a, _an, aall = team_form(fixtures, r.get("espn_away"), ko, over, O15_WINDOW)
        if min(hall, aall) >= GOALS_MIN_GAMES and h >= O15_MIN and a >= O15_MIN:
            out.append(dict(market_id=r["market_id"], pick="a"))
    return out


def _team_rule(sport, universe, fixtures, n, window, need):
    fixtures = _espn_fixtures() if fixtures is None else fixtures
    out = []
    for r, ko in _rule_rows(sport, universe):
        s, _sn, sall = team_form(fixtures, r.get("team"), ko, lambda gf, ga: gf >= n, window)
        c, _cn, call = team_form(fixtures, r.get("opponent"), ko, lambda gf, ga: ga >= n, window)
        if min(sall, call) >= GOALS_MIN_GAMES and s >= need and c >= need:
            out.append(dict(market_id=r["market_id"], pick="a"))
    return out


P05_WINDOW, P05_UNBEATEN_MIN, P05_OPP_WINS_MAX = 10, 8, 3


def _form_league(r):
    """The competition the +0.5 and under-3.5 rules count form in: the row's own league (HOF's
    way) — except for cup ties and internationals, where no team plays 10 games in one
    competition, so every competitive game counts (the cup and international pairs only)."""
    return None if r.get("comp") in ("cup", "intl") else r.get("league")


def fetch_p05_unbeaten(sport, universe=None, fixtures=None):
    """Back a team +0.5 (No on its opponent winning) where the team is unbeaten in 8+ of its last
    10 games in this competition and the opponent won 3 or fewer of its last 10 there."""
    fixtures = _espn_fixtures() if fixtures is None else fixtures
    out = []
    for r, ko in _rule_rows(sport, universe):
        lg = _form_league(r)
        u, _un, uall = team_form(fixtures, r.get("team"), ko, lambda gf, ga: gf >= ga, P05_WINDOW, league=lg)
        w, _wn, wall = team_form(fixtures, r.get("opponent"), ko, lambda gf, ga: gf > ga, P05_WINDOW, league=lg)
        if min(uall, wall) >= P05_WINDOW and u >= P05_UNBEATEN_MIN and w <= P05_OPP_WINS_MAX:
            out.append(dict(market_id=r["market_id"], pick="b"))
    return out


# Fixture congestion (2026-09-22). Stüttgen, Journal of Sports Economics 2025: over five
# Bundesliga seasons a side playing its second competitive match within four days shows
# reduced offensive strength, and improved defensive strength at home; the defensive half
# replicated in Spain and England, the offensive half did not. Both signs push the same way
# on a match total — fewer goals — which makes it a rule that can be stated in one line and
# cannot be tuned after the fact.
#
# It is here because it is the only situational signal on goals with a peer-reviewed effect
# and NO published test against a price. Fixture calendars are public and the market has had
# them for as long as anyone; the honest prior is that this is already in the number and the
# rule returns the toll. That is worth finding out for the cost of counting days.
#
# Both thresholds are the paper's, not ours: "within four days" is its own definition, and the
# rested side must have had six or more so the two sides are actually in different states
# rather than a day apart. Cups and internationals count as competitive games, because a
# midweek cup tie is exactly the congestion the paper is about.
CONGEST_GAP_D = 4.0            # the congested side's previous match kicked off within this
CONGEST_REST_D = 6.0           # the opponent's previous match was at least this long ago


def days_rest(fixtures, team, before):
    """Days from `team`'s last completed competitive kickoff to `before`, or None if unknown.

    None matters: a side with no earlier match on file is not a rested side, it is a side we
    cannot see, and the rule must decline rather than guess.
    """
    last = None
    for f in fixtures:
        if (not f.get("played") or not f.get("competitive", True) or not f.get("kickoff")
                or team not in (f.get("home"), f.get("away"))):
            continue
        try:
            ko = datetime.fromisoformat(str(f["kickoff"]).replace("Z", "+00:00"))
        except ValueError:
            continue
        if ko < before and (last is None or ko > last):
            last = ko
    return None if last is None else (before - last).total_seconds() / 86400


def fetch_o25_congestion(sport, universe=None, fixtures=None):
    """Back UNDER 2.5 (No on Kalshi's Over 2.5) where one side is playing its second
    competitive match within four days and the other has had six days or more."""
    fixtures = _espn_fixtures() if fixtures is None else fixtures
    out = []
    for r, ko in _rule_rows(sport, universe):
        h = days_rest(fixtures, r.get("espn_home"), ko)
        a = days_rest(fixtures, r.get("espn_away"), ko)
        if h is None or a is None:
            continue
        if ((h < CONGEST_GAP_D and a >= CONGEST_REST_D)
                or (a < CONGEST_GAP_D and h >= CONGEST_REST_D)):
            out.append(dict(market_id=r["market_id"], pick="b"))
    return out


U35_WINDOW, U35_MIN, U35_MAX_SCORED = 10, 7, 1


def fetch_u35_low_scoring(sport, universe=None, fixtures=None):
    """Back UNDER 3.5 (No on Kalshi's Over 3.5) where BOTH teams scored 1 or fewer in 7+ of their
    last 10 games in this competition, each with 10+ such games."""
    fixtures = _espn_fixtures() if fixtures is None else fixtures
    low = lambda gf, ga: gf <= U35_MAX_SCORED
    out = []
    for r, ko in _rule_rows(sport, universe):
        lg = _form_league(r)
        h, _hn, hall = team_form(fixtures, r.get("espn_home"), ko, low, U35_WINDOW, league=lg)
        a, _an, aall = team_form(fixtures, r.get("espn_away"), ko, low, U35_WINDOW, league=lg)
        if min(hall, aall) >= U35_WINDOW and h >= U35_MIN and a >= U35_MIN:
            out.append(dict(market_id=r["market_id"], pick="b"))
    return out


def fetch_team1_form_l5(sport, universe=None, fixtures=None):
    """Back a side to score where it scored in each of its last 5 and the opponent conceded in
    each of its last 5."""
    return _team_rule(sport, universe, fixtures, 1, TEAM1_WINDOW, TEAM1_WINDOW)


def fetch_team2_form_l10(sport, universe=None, fixtures=None):
    """Back a side to score 2+ where it scored 2+ in 7+ of its last 10 and the opponent
    conceded 2+ in 7+ of its last 10."""
    return _team_rule(sport, universe, fixtures, 2, TEAM2_WINDOW, TEAM2_MIN)


def resolve_kalshi_market(ticker):
    """Settle one yes/no market: 'a' (YES), 'b' (NO), 'void', or None while open."""
    try:
        d = _get(f"https://api.elections.kalshi.com/trade-api/v2/markets/{ticker}",
                 tries=2, timeout=20)
    except RuntimeError:
        return None
    m = d.get("market") if isinstance(d, dict) else None
    if not m:
        return None
    if str(m.get("status")).lower() not in KALSHI_FINAL:
        return None
    result = str(m.get("result")).lower()
    return {"yes": "a", "no": "b"}.get(result, "void")


def venue_price(q, closing=False):
    """The price backing `q`'s side would cost right now on its own venue, or None.

    For the closing-price job: one targeted read per bet instead of a whole sport's
    universe. The same books and the same tradeability rules as the fetchers — the ask,
    and only while that side's book is tight — so a closing price is comparable with the
    price the bet was logged at. None when the market is closed, the book is untradeable,
    or the read fails; the last good snapshot then stands.

    `closing`: this read is a closing snapshot, not a price anyone would enter at, which
    changes one rule. An ENTRY is refused on a book with no bid — you could buy it and
    never sell it. A CLOSE is not a trade; it is the record of where the market ended, and
    a contract the market has written off to a cent has an ask and no bid almost by
    definition. Refusing those lost the whole weather lane: every one of the National
    Weather Service's 60 settled bets, including all 29 since the fade began, had no
    closing price on file for this reason and nothing else. Worse, it lost them
    ASYMMETRICALLY — a bid vanishes when a contract collapses, so the prices being
    discarded were the ones that had moved hardest AGAINST the pick, and the CLV that
    survived was flattered. The spread cap still applies, so a zero bid is only accepted
    where the ask is inside it: a written-off contract counts, an empty mid-range book
    still does not.
    """
    venue, pick = q.get("venue") or "polymarket", q.get("pick")
    if venue == "combo":
        # A basket has no book of its own: it is priced the way it was logged, as the
        # product of its legs' asks plus the measured wrapper markup. So its close is that
        # same sum taken again now — and a basket is only as priceable as its thinnest leg.
        legs = q.get("legs") or []
        markup = COMBO_MARKUP.get(len(legs))
        if markup is None or pick not in ("a", "b"):
            return None
        prod = 1.0
        for leg in legs:
            p = venue_price(dict(leg), closing=closing)
            if p is None:
                return None
            prod *= p
        price = min(0.9999, round(prod * (1 + markup), 4))
        return price if pick == "a" else round(1 - price, 4)
    try:
        if venue == "polymarket_us":
            d = (_get(f"{PMUS}/v1/markets/{urllib.parse.quote(str(q['market_id']))}/bbo", tries=2,
                      timeout=20) or {}).get("marketData") or {}
            bid, ask = _pmus_amt(d.get("bestBid")), _pmus_amt(d.get("bestAsk"))
            if bid is None or ask is None or not (0 < bid < ask < 1) or ask - bid > MAX_SPREAD + 1e-9:
                return None
            return round(ask, 4) if pick == "a" else round(1 - bid, 4) if pick == "b" else None
        if venue == "polymarket":
            m = _get(f"{GAMMA}/markets/{q['market_id']}", tries=2, timeout=20)
            if not isinstance(m, dict) or m.get("closed") or not m.get("acceptingOrders"):
                return None
            ok, ask_a, ask_b, _sp, _liq = pm_book(m)
            return (ask_a if pick == "a" else ask_b if pick == "b" else None) if ok else None
        if venue == "kalshi":
            et = q["market_id"]
            ms = (_get(f"{KALSHI_API}?event_ticker={et}", tries=2, timeout=20) or {}).get("markets") or []
            sides = kalshi_sides(et, ms)
            m = next((m for m in ms if sides.get(_kalshi_code(m)) == pick), None)
            if not m or str(m.get("status")).lower() not in ("open", "active"):
                return None
            bid, ask = _num(m.get("yes_bid_dollars")), _num(m.get("yes_ask_dollars"))
        elif venue == "kalshi_binary":
            m = (_get(f"{KALSHI_API}/{q['market_id']}", tries=2, timeout=20) or {}).get("market")
            if not m or str(m.get("status")).lower() not in ("open", "active"):
                return None
            side = "yes" if pick == "a" else "no"
            bid, ask = _num(m.get(f"{side}_bid_dollars")), _num(m.get(f"{side}_ask_dollars"))
        else:
            return None
    except (RuntimeError, KeyError, TypeError, AttributeError):
        return None
    if bid is None or ask is None or not (0 < ask < 1) or ask - bid > KALSHI_MAX_SPREAD:
        return None
    if bid <= 0 and not closing:
        return None                 # nothing to sell into: fine to record, not to enter on
    return round(ask, 4)


def closing_price(q):
    """venue_price for a closing snapshot. See the `closing` argument there."""
    return venue_price(q, closing=True)


# ---------------------------------------------------------------------------
# The National Weather Service — a real forecaster, on daily markets
# ---------------------------------------------------------------------------
#
# The one non-sport domain with a genuine independent forecaster. NWS publishes a daily
# high for each city; Kalshi prices mutually exclusive buckets for the same city and day.
# The forecast therefore picks exactly one bucket, at a real price, and it settles the
# next morning.
NWS_UA = "sandbox-tracker (github.com/aliu2298/edge-machine)"
_nws_cache = {}


def nws_highs(lat, lon):
    """{date: forecast high F} for one point, from the NWS daytime periods."""
    key = (round(lat, 3), round(lon, 3))
    if key in _nws_cache:
        return _nws_cache[key]
    out = {}
    try:
        point = _get(f"https://api.weather.gov/points/{lat},{lon}", tries=2, timeout=20)
        url = point["properties"]["forecast"]
        for per in _get(url, tries=2, timeout=20)["properties"]["periods"]:
            if per.get("isDaytime") and per.get("temperatureUnit") == "F":
                out[str(per["startTime"])[:10]] = float(per["temperature"])
    except (RuntimeError, KeyError, TypeError, ValueError) as e:
        print(f"  ! nws {lat},{lon}: {type(e).__name__}")
    _nws_cache[key] = out
    return out


def _most_uncertain(rows):
    """Of several markets a forecast settles YES, the one still genuinely in doubt.

    Ladder series carry a dozen strikes at once and a forecast settles most of them
    trivially — spot at $102 makes "$58 or above" a certainty priced at 1.00, which is
    both untradeable and says nothing. The market nearest a coin flip is the one the
    forecast is actually being tested on.
    """
    return min(rows, key=lambda r: (not (r.get("tradeable") or {}).get("a", True),
                                    abs((r.get("price_a") or 0.5) - 0.5)))


def _nws_forecast_picks(domain):
    """One pick per city per day: the bucket the NWS forecast lands in.

    The network read. publish() and nws_picks share one result per run, so this
    runs once even when both the follow lane and nws_fade want it.
    """
    if domain != "climate":
        return []
    groups = {}
    for r in (UNIVERSE or {}).get("climate") or []:
        series = r.get("series")
        if series not in NWS_CITIES:
            continue
        temp = nws_highs(*NWS_CITIES[series]).get(kalshi_date(r["market_id"]))
        if temp is None or not in_range(temp, r["market"]):
            continue
        # One pick per city per day: betting NO on the other seven buckets would be seven
        # near-certainties at prices the band rejects anyway.
        groups.setdefault((series, r["date"], round(temp)), []).append(r)
    return [dict(market_id=_most_uncertain(rs)["market_id"], pick="a",
                 detail=f"NWS forecast {t}F")
            for (_s, _d, t), rs in groups.items()]


# Picks for the publish in progress. Cleared by clear_nws_run at each end of publish.
_nws_run = {}


def clear_nws_run():
    """Forget the shared NWS picks. The next reader fetches again."""
    _nws_run.clear()


def nws_picks(domain):
    """Follow-lane picks for this run. Computed once; nws and nws_fade both read them."""
    if domain not in _nws_run:
        _nws_run[domain] = _nws_forecast_picks(domain)
    return _nws_run[domain]


def fetch_nws(domain):
    """The follow lane. A copy, so a later reader cannot change the shared picks."""
    return [dict(p) for p in nws_picks(domain)]


# Fixed 2026-09-25, before nws_fade logged an entry. One city-day is one outcome
# (outcome_cluster). Do not change this number, or the side fetch_nws_fade takes,
# before this many independent outcomes have settled.
NWS_FADE_READ_N = 100


def fetch_nws_fade(domain):
    """The other side of each pick fetch_nws would make. Same markets, same stake.

    Reads nws_picks, the same list the follow lane uses, so a run does not fetch
    the forecast twice. The side is the opposite of the follow lane and nothing
    else. Do not retune it before NWS_FADE_READ_N settled independent outcomes.
    """
    out = []
    for p in nws_picks(domain):
        side = p.get("pick")
        if side == "a":
            flip = "b"
        elif side == "b":
            flip = "a"
        else:
            continue
        out.append(dict(p, pick=flip, detail=f"other side of {p.get('detail') or 'NWS'}"))
    return out


# ---------------------------------------------------------------------------
# Spot price — the "nothing changes" baseline
# ---------------------------------------------------------------------------
#
# Not a forecast so much as the null hypothesis: today's price, carried forward. If a
# crypto market cannot be beaten by assuming no change, nothing subtler is worth adding.
_spot_cache = {}


def spot_price(coin):
    if coin in _spot_cache:
        return _spot_cache[coin]
    try:
        d = _get("https://api.coingecko.com/api/v3/simple/price?ids="
                 f"{coin}&vs_currencies=usd", tries=2, timeout=20)
        _spot_cache[coin] = float(d[coin]["usd"])
    except (RuntimeError, KeyError, TypeError, ValueError):
        _spot_cache[coin] = None
    return _spot_cache[coin]


def fetch_spot(domain):
    """Back the bucket today's spot price already sits in."""
    if domain != "crypto":
        return []
    groups = {}
    for r in (UNIVERSE or {}).get("crypto") or []:
        coin = COINS.get(r.get("series"))
        price = spot_price(coin) if coin else None
        if price is None or not in_range(price, r["market"]):
            continue
        groups.setdefault((r["series"], r["date"], round(price, 2)), []).append(r)
    return [dict(market_id=_most_uncertain(rs)["market_id"], pick="a",
                 detail=f"spot ${p:,.2f}")
            for (_s, _d, p), rs in groups.items()]


# ---------------------------------------------------------------------------
# OLBG community tips — boxing (plain HTTP)
# ---------------------------------------------------------------------------
#
# OLBG runs a tipster community: named accounts post a tip per fight, and the boxing
# listing prints each fight's MOST POPULAR "Win Fight" selection with its share of the
# tips ("9/14 Win Tips"). One page covers every upcoming card, so a run costs one request;
# robots.txt allows it for any user agent.
#
# Three things about this community decide the rule, all seen on the live page on
# 2026-09-12:
#   * its tipsters compete on PROFIT, so the most popular selection is often the draw at
#     15/1 or 17/1 (10 of 14 tips on Magsayo v Cortes). The venue boxing markets are
#     two-way and cannot back a draw, so a fight whose top tip is the draw is no call —
#     reading its second choice would put words in the community's mouth.
#   * a thin fight carries one or two tips. One account is not a consensus.
#   * the page lists UFC and other MMA bouts under the same boxing path. They cannot match
#     a boxing contest in the venue universe, so they fall away at matching.
# So a fight is a call only when a FIGHTER is the most popular selection, with at least
# OLBG_MIN_TIPS tips and a strict majority of them. A plurality (10 of 25 on Garcia v Benn,
# the rest split between Benn and the draw) is not a majority and is no call.
# Boxing, UFC and other MMA share one listing (OLBG sport 16). The page cannot tell them
# apart, so both sports read the same calls and matching sorts a bout into its sport.
OLBG_URLS = {"boxing": "https://www.olbg.com/betting-tips/Boxing/16",
             "mma": "https://www.olbg.com/betting-tips/Boxing/16"}
OLBG_MIN_TIPS = 3
_olbg_cache = {}


def parse_olbg(page):
    """OLBG listing page -> [{a, b, pick, date, detail}] for clear fighter consensus only."""
    out = []
    for block in re.split(r'<div class="grd tip', page)[1:]:
        name = re.search(r'itemprop="name">([^<]+)<', block)
        when = re.search(r'itemprop="startDate" datetime="([^"]+)"', block)
        sel = re.search(r'<div class="rw sel">.*?<h4[^>]*>([^<]+)</h4>\s*.*?'
                        r'<p class="truncate text-sm">([^<]+)</p>', block, re.S)
        tips = re.search(r'>(\d+)/(\d+) Win Tips<', block)
        if not (name and when and sel and tips):
            continue
        sides = re.split(r"\s+v\s+", html.unescape(name.group(1)).strip(), maxsplit=1)
        if len(sides) != 2:
            continue
        a, b = (x.strip() for x in sides)
        choice, market = html.unescape(sel.group(1)).strip(), sel.group(2).strip()
        n, total = int(tips.group(1)), int(tips.group(2))
        if market.lower() != "win fight" or total < OLBG_MIN_TIPS or n * 2 <= total:
            continue
        if choice.lower() in ("draw", "draw or technical draw"):
            continue
        if choice == a or (choice != b and sim(choice, a) > sim(choice, b)):
            pick = "a"
        else:
            pick = "b"
        out.append(dict(a=a, b=b, pick=pick, date=day(when.group(1)),
                        detail=f"{choice} {n}/{total} tips"))
    return out


def fetch_olbg(sport):
    if sport not in OLBG_URLS:
        return []
    url = OLBG_URLS[sport]
    if url not in _olbg_cache:
        try:
            page = _get_html(url, timeout=25)
        except RuntimeError as e:
            print(f"  ! olbg/{sport}: {str(e)[:80]}")
            _mark("olbg", False, "page unreachable")
            _olbg_cache[url] = []
            return []
        # A Cloudflare interstitial answers 200 with no rows. Say so, rather than report
        # "no consensus" for a page that was never actually read.
        if 'class="grd tip' not in page:
            wall = re.search(r"(?i)just a moment|challenge-platform|cf-chl", page)
            _mark("olbg", False, "Cloudflare challenge" if wall else "no tip rows on the page")
            _olbg_cache[url] = []
            return []
        _mark("olbg", True)
        _olbg_cache[url] = parse_olbg(page)
    return _olbg_cache[url]


# ---------------------------------------------------------------------------
# Pinnacle, through The Odds API
# ---------------------------------------------------------------------------
#
# Pinnacle closed its own public API on 2025-07-23. The Odds API carries its lines under
# the bookmaker key "pinnacle" (EU region) behind a keyed, documented, paid-or-free-tier
# API, which is the legitimate route — the pinnacle.com site's own guest endpoint answers
# too, but it is undocumented and Pinnacle does not serve US customers, so it is not used.
#
# CREDITS. /v4/sports and /v4/sports/{key}/events are free; /odds costs one credit per
# market per region, and `bookmakers=pinnacle` counts as one region. The free tier is 500
# a month and this workflow runs four times a day, so every paid call is earned: a sport
# key is only priced when its free event list has a contest inside the horizon that the
# venue universe actually lists, at most ODDS_MAX_CALLS per run, and never once the
# account is down to ODDS_RESERVE credits.
#
# THE KEY never appears in a log line: it travels in the query string, so errors are
# reported by status code alone, never by URL.

ODDS_API = "https://api.the-odds-api.com/v4"
ODDS_GROUPS = {"boxing": "Boxing", "mma": "Mixed Martial Arts", "cricket": "Cricket",
               "tennis": "Tennis", "soccer": "Soccer"}
# Sports whose venue markets are three-way: Pinnacle's draw price stays IN the de-vig there,
# because the venue row prices the draw separately and "home" must mean home, not "not away".
ODDS_THREE_WAY = ("soccer",)
# Pinnacle lines older than this are not logged. The Odds API warns its bookmaker odds can
# lag the bookmaker's site; a venue that has already moved on news would otherwise look like
# an edge against a price Pinnacle itself has abandoned.
PINNACLE_MAX_AGE_MIN = 60
# Which kinds count as "someone already covers this contest". Prediction markets do not:
# Kalshi quoting a Polymarket contest is another price, not a forecast.
COVERING_KINDS = ("Tipster site", "Statistical model", "Sportsbook", "Forecaster", "Baseline")
ODDS_HORIZON_DAYS = 4          # the same horizon the venue universe is fetched over
ODDS_MAX_CALLS = 4             # hard ceiling per run, whatever the budget says
ODDS_RESERVE = 25              # never spend the last few credits
# The free tier is 500 credits a month and they reset on the 1st (the-odds-api.com FAQ).
# A flat per-run cap cannot make that last: it does not know how many days are left, and
# every manual dispatch spends like a scheduled run — the first evening spent 17 credits in
# five runs, four of them dispatched by hand. So each run is allowed its fair share of what
# remains: (remaining - reserve) / runs left until the reset, where runs left assumes the
# four scheduled runs a day PLUS ODDS_RUN_SLACK for manual ones, and the reset is taken a
# day late in case it lands on the 1st in a timezone behind UTC.
ODDS_RUNS_PER_DAY = 8          # = the tracker's cron (every 3h); pacing divides by it
# Where Pinnacle has nothing to add, stop paying for it. Fixed before it was applied: once a
# sport has PINNACLE_RETIRE_N Pinnacle quotes in the ledger and not one of them disagreed
# with the venue by the betting edge, that sport's venue already prices like Pinnacle and a
# paid call there buys a quote that can never be a bet. The first 35 soccer quotes against
# Kalshi had a largest gap of 1.3pp. Re-judged every run from the retained ledger, so a
# sport comes back if its old quotes age out. A key with no uncovered contest is never paid
# for either; credits not spent stay in the balance, and the pacing hands them to later runs.
PINNACLE_RETIRE_N = 30
ODDS_RUN_SLACK = 1.25
ODDS_USAGE = {}                # {"remaining", "used", "calls"} for this run, for the page
_odds_sports = None


def _odds_key():
    import os
    return os.environ.get("ODDS_API_KEY", "").strip()


def _odds_get(path, params):
    """GET one Odds API endpoint -> (json, headers). Raises RuntimeError without the URL."""
    key = _odds_key()
    q = urllib.parse.urlencode(dict(params, apiKey=key))
    req = urllib.request.Request(f"{ODDS_API}{path}?{q}", headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=25) as f:
            return json.load(f), dict(f.headers)
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HTTP {e.code} on {path}") from None
    except (OSError, http.client.HTTPException, ValueError) as e:
        raise RuntimeError(f"{type(e).__name__} on {path}") from None


def odds_allowance(remaining, now=None):
    """Paid calls this run may make so `remaining` credits last until the monthly reset."""
    if remaining is None:
        return 1                                   # balance unknown: spend cautiously
    now = now or datetime.now(timezone.utc)
    nxt = (datetime(now.year + (now.month == 12), now.month % 12 + 1, 1, tzinfo=timezone.utc)
           + timedelta(days=1))
    runs_left = max(1.0, (nxt - now).total_seconds() / 86400 * ODDS_RUNS_PER_DAY
                    * ODDS_RUN_SLACK)
    return max(0, min(ODDS_MAX_CALLS, int((remaining - ODDS_RESERVE) // runs_left)))


def _odds_note_usage(headers):
    for h, k in (("x-requests-remaining", "remaining"), ("x-requests-used", "used")):
        v = next((val for name, val in headers.items() if name.lower() == h), None)
        if v is not None:
            try:
                ODDS_USAGE[k] = int(float(v))
            except ValueError:
                pass


def pinnacle_line(event):
    """(prices {name: decimal}, last_update datetime|None) for Pinnacle's h2h, or (None, None)."""
    for bk in event.get("bookmakers") or []:
        if bk.get("key") != "pinnacle":
            continue
        for mk in bk.get("markets") or []:
            if mk.get("key") != "h2h":
                continue
            prices = {o.get("name"): o.get("price") for o in mk.get("outcomes") or []
                      if o.get("name")}
            stamp = mk.get("last_update") or bk.get("last_update")
            try:
                upd = datetime.fromisoformat(str(stamp).replace("Z", "+00:00")) if stamp else None
            except ValueError:
                upd = None
            return prices, upd
    return None, None


def pinnacle_prob(event, side_a, three_way=False):
    """De-vigged Pinnacle probability that `side_a` wins, from one /odds event.

    Two-way (boxing, MMA, tennis, cricket): a draw outcome is dropped before normalising —
    the venue markets are two-way and a draw there resolves as neither side.
    Three-way (soccer): the draw stays in the normalisation, because the venue prices the
    draw separately and the home side's probability must not absorb it.
    Returns None when Pinnacle has no usable h2h line on the event.
    """
    prices, _upd = pinnacle_line(event)
    if not prices:
        return None
    try:
        inv = {n: 1 / float(p) for n, p in prices.items() if p}
    except (TypeError, ValueError, ZeroDivisionError):
        return None
    if side_a not in inv:
        return None
    if three_way:
        if len(inv) != 3 or not any(str(n).lower() == "draw" for n in inv):
            return None
        return inv[side_a] / sum(inv.values())
    two = {n: v for n, v in inv.items() if str(n).lower() != "draw"}
    others = [v for n, v in two.items() if n != side_a]
    if len(others) != 1:
        return None
    pa, _pb = devig(two[side_a], others[0])
    return pa


def plan_pinnacle(universe, covered=None, now=None, retired=None):
    """Pinnacle quotes for every sport it covers, spending credits where nothing else looks.

    One pass across ALL sports rather than one sport at a time, so the run's credit
    allowance goes to the sport keys with the most contests that no tipster, model or book
    has covered — not to whichever sport the loop happens to reach first. Event lists are
    free; each paid /odds call prices a whole key, and every contest it returns is quoted,
    covered or not, since that costs nothing more.

    `covered` is {sport: set(market_id)} of contests some covering source already has.
    `retired` is the set of sports no paid call goes to (see PINNACLE_RETIRE_N).
    Returns {sport: [quote]}.
    """
    now = now or datetime.now(timezone.utc)
    covered = covered or {}
    retired = set(retired or ())
    out = {sp: [] for sp in universe if sp in ODDS_GROUPS and sp not in retired}
    ODDS_USAGE["retired"] = sorted(sp for sp in universe if sp in ODDS_GROUPS and sp in retired)
    if not out:
        return out
    if not _odds_key():
        _mark("pinnacle", False, "no ODDS_API_KEY in the environment")
        return out
    _odds_keys(next(iter(out)))                 # free: loads the sport list and the balance
    # Checked before any event list is read: past this point a readable list marks the feed
    # "ok", and the page would then never say why no prices arrived.
    if ODDS_USAGE.get("remaining") is not None and ODDS_USAGE["remaining"] < ODDS_RESERVE:
        _mark("pinnacle", False, f"credit reserve reached ({ODDS_USAGE['remaining']} left)")
        return out
    window = dict(commenceTimeFrom=now.strftime("%Y-%m-%dT%H:%M:%SZ"),
                  commenceTimeTo=(now + timedelta(days=ODDS_HORIZON_DAYS))
                  .strftime("%Y-%m-%dT%H:%M:%SZ"))

    # 1. Free: which keys carry contests the venue universe lists with a real price, and how
    #    many of those contests are uncovered.
    candidates = []
    for sport in out:
        rows = [r for r in (universe.get(sport) or []) if not r.get("untraded")]
        if not rows:
            continue
        cov = covered.get(sport) or set()
        for key in _odds_keys(sport):
            try:
                events, _h = _odds_get(f"/sports/{key}/events", window)
            except RuntimeError as e:
                _mark("pinnacle", False, str(e))
                continue
            _mark("pinnacle", True)
            listed = uncovered = 0
            for r in rows:
                if any(pair_match(r["side_a"], r["side_b"], ev.get("home_team", ""),
                                  ev.get("away_team", ""), sport=sport)[0] > 0
                       for ev in events):
                    listed += 1
                    uncovered += r.get("market_id") not in cov
            if uncovered:
                candidates.append((uncovered, listed, sport, key))

    # 2. Paid: most uncovered contests first, then most listed. Never past the run's share.
    candidates.sort(key=lambda c: (-c[0], -c[1]))
    if "allowance" not in ODDS_USAGE:
        ODDS_USAGE["allowance"] = odds_allowance(ODDS_USAGE.get("remaining"), now)
    ODDS_USAGE["planned"] = [dict(sport=sp, key=k, uncovered=u, listed=l)
                             for u, l, sp, k in candidates]
    for uncovered, listed, sport, key in candidates:
        if ODDS_USAGE.get("calls", 0) >= ODDS_USAGE["allowance"]:
            if ODDS_USAGE["allowance"] == 0:
                _mark("pinnacle", False, "credit budget paced out until the monthly reset")
            break
        if ODDS_USAGE.get("remaining") is not None and ODDS_USAGE["remaining"] < ODDS_RESERVE:
            break                               # reached mid-run, after a paid call
        try:
            odds, headers = _odds_get(f"/sports/{key}/odds",
                                      dict(window, bookmakers="pinnacle", markets="h2h",
                                           oddsFormat="decimal", dateFormat="iso"))
        except RuntimeError as e:
            _mark("pinnacle", False, str(e))
            continue
        ODDS_USAGE["calls"] = ODDS_USAGE.get("calls", 0) + 1
        ODDS_USAGE.setdefault("spent_on", []).append(dict(sport=sport, key=key,
                                                          uncovered=uncovered))
        _odds_note_usage(headers)
        for ev in odds:
            home, away = ev.get("home_team"), ev.get("away_team")
            _prices, upd = pinnacle_line(ev)
            if upd is not None and (now - upd).total_seconds() > PINNACLE_MAX_AGE_MIN * 60:
                ODDS_USAGE["stale"] = ODDS_USAGE.get("stale", 0) + 1
                continue
            p = pinnacle_prob(ev, home, three_way=sport in ODDS_THREE_WAY)
            if p is None or not home or not away:
                continue
            out[sport].append(dict(a=home, b=away, prob_a=p, date=day(ev.get("commence_time"))))
    return out


def fetch_pinnacle(sport):
    """One sport's Pinnacle quotes, for callers outside the planned publish pass."""
    return plan_pinnacle({sport: (UNIVERSE or {}).get(sport) or []}).get(sport, [])


# ---------------------------------------------------------------------------
# Pinnacle's goal total against Kalshi's (2026-09-22)
# ---------------------------------------------------------------------------
# The forecasting lane is finished: on 152 graded fixtures the book's de-vigged fair price
# was accurate to within a point on four of five markets, and our own model was worse than
# it on all five. What is NOT finished is the PRICE. Kalshi is a young exchange with a wide
# book; Pinnacle is the sharpest there is. Where the two disagree on the same line, one of
# them is wrong, and it costs nothing to find out which — no model, no forecast, no form.
#
# This is the same test the h2h lane already ran and LOST: 57 soccer match-winner quotes
# against Kalshi never once reached the 3pp edge, so soccer is retired from paid h2h calls.
# That result is about the match winner only. Totals are a different market with a different
# book, and the comparison has never been made, here or (as far as the literature goes)
# anywhere. If it comes back like the h2h one did, that is an answer too, and a cheap one.
#
# 2.5 ONLY, and that is not a preference. The Odds API returns one main total per bookmaker,
# and Pinnacle's is almost always 2.5; every other line would need the alternate-totals
# market, which costs another credit per call. So the two venues are compared where they
# already quote the same number — which is also the line where a match is least decided in
# advance, and therefore where a real disagreement has the most room to show.
PIN_TOTALS_POINT = 2.5
PIN_TOTALS_MAX_CALLS = 1       # per run, and only out of what the h2h pass leaves unspent


def pinnacle_total_prob(event, point):
    """De-vigged Pinnacle probability that the match goes OVER `point`, or None.

    Only the exact line is read. A 2.5 quote is not evidence about a 2.75 market, and
    converting between them needs a goal model — which is the thing this lane exists to
    avoid relying on.
    """
    for bk in event.get("bookmakers") or []:
        if bk.get("key") != "pinnacle":
            continue
        for mk in bk.get("markets") or []:
            if mk.get("key") != "totals":
                continue
            over = under = None
            for o in mk.get("outcomes") or []:
                try:
                    if float(o.get("point")) != float(point):
                        continue
                except (TypeError, ValueError):
                    continue
                if str(o.get("name")).lower() == "over":
                    over = o.get("price")
                elif str(o.get("name")).lower() == "under":
                    under = o.get("price")
            if not over or not under:
                return None
            try:
                pa, _pb = devig(1 / float(over), 1 / float(under))
            except (TypeError, ValueError, ZeroDivisionError):
                return None
            return pa
    return None


def plan_pinnacle_totals(universe, now=None):
    """Pinnacle's main goal total for the fixtures Kalshi lists an over-2.5 market on.

    Spends only what the h2h pass leaves of the run's paced allowance, and at most
    PIN_TOTALS_MAX_CALLS, so adding this lane cannot shorten the month's credits. The event
    list that picks WHICH key to buy is free and already cached by pinnacle_events().
    Returns {sport: [{market_id, prob_a}]}.
    """
    now = now or datetime.now(timezone.utc)
    out = {}
    rows = [(sp, r) for sp in universe if sp.split("_cup")[0].split("_intl")[0] == "soccer_o25"
            for r in (universe.get(sp) or []) if not r.get("untraded") and r.get("espn_home")]
    if not rows or not _odds_key():
        return out
    events = pinnacle_events("soccer")               # free; also loads the credit balance
    if not events:
        return out
    if ODDS_USAGE.get("remaining") is not None and ODDS_USAGE["remaining"] < ODDS_RESERVE:
        _mark("pinnacle", False, f"credit reserve reached ({ODDS_USAGE['remaining']} left)")
        return out
    if "allowance" not in ODDS_USAGE:
        ODDS_USAGE["allowance"] = odds_allowance(ODDS_USAGE.get("remaining"), now)
    # Half the run's allowance at most, and never more than one call. This lane is fetched
    # with the other challengers, which is BEFORE the match-winner pass plans its spending —
    # so without a cap a new test would quietly take the credits an established lane was
    # already using. On a one-credit run the integer halving gives this lane nothing and the
    # older one keeps it, which is the right way round.
    left = min(PIN_TOTALS_MAX_CALLS, ODDS_USAGE["allowance"] // 2)
    if left <= 0:
        return out

    # Which Odds API key covers most of the fixtures Kalshi has priced. One row is matched to
    # at most one event, so a key cannot be credited twice for the same fixture.
    hits = {}
    for sp, r in rows:
        best = None
        for ev in events:
            score, _flip = pair_match(r["espn_home"], r["espn_away"], ev["a"], ev["b"], sport="soccer")
            if score > 0 and (best is None or score > best[0]):
                best = (score, ev)
        if best:
            hits.setdefault(best[1]["key"], []).append((sp, r, best[1]))
    window = dict(commenceTimeFrom=now.strftime("%Y-%m-%dT%H:%M:%SZ"),
                  commenceTimeTo=(now + timedelta(days=ODDS_HORIZON_DAYS)).strftime("%Y-%m-%dT%H:%M:%SZ"))
    for key, want in sorted(hits.items(), key=lambda kv: -len(kv[1]))[:left]:
        try:
            odds, headers = _odds_get(f"/sports/{key}/odds",
                                      dict(window, bookmakers="pinnacle", markets="totals",
                                           oddsFormat="decimal", dateFormat="iso"))
        except RuntimeError as e:
            _mark("pinnacle", False, str(e))
            continue
        ODDS_USAGE["calls"] = ODDS_USAGE.get("calls", 0) + 1
        ODDS_USAGE.setdefault("totals_on", []).append(dict(key=key, listed=len(want)))
        _odds_note_usage(headers)
        for sp, r, _ev in want:
            for e2 in odds:
                if pair_match(r["espn_home"], r["espn_away"], e2.get("home_team", ""),
                              e2.get("away_team", ""), sport="soccer")[0] <= 0:
                    continue
                # A line Pinnacle has already moved on is not a disagreement with Kalshi,
                # it is a stale number; the h2h lane drops those for the same reason.
                _p, upd = pinnacle_line(e2)
                stamp = next((m.get("last_update") for bk in e2.get("bookmakers") or []
                              if bk.get("key") == "pinnacle"
                              for m in bk.get("markets") or [] if m.get("key") == "totals"), None)
                try:
                    upd = datetime.fromisoformat(str(stamp).replace("Z", "+00:00")) if stamp else upd
                except ValueError:
                    pass
                if upd is not None and (now - upd).total_seconds() > PINNACLE_MAX_AGE_MIN * 60:
                    ODDS_USAGE["stale"] = ODDS_USAGE.get("stale", 0) + 1
                    break
                prob = pinnacle_total_prob(e2, PIN_TOTALS_POINT)
                if prob is not None:
                    out.setdefault(sp, []).append(dict(market_id=r["market_id"], prob_a=prob))
                break
    return out


_pin_totals_cache = {}


def fetch_pin_totals(sport, universe=None):
    """Pinnacle's over-2.5 probability on every Kalshi over-2.5 market it also prices.

    Planned once per run across all three scopes, because one paid call covers a whole
    league key and the league's cup ties may sit in another domain.
    """
    uni = universe if universe is not None else (UNIVERSE or {})
    key = id(uni)
    if key not in _pin_totals_cache:
        _pin_totals_cache.clear()
        try:
            _pin_totals_cache[key] = plan_pinnacle_totals(uni)
        except Exception as e:                      # a dead feed must not stop the run
            print(f"  ! pinnacle totals plan failed: {type(e).__name__}: {str(e)[:70]}")
            _pin_totals_cache[key] = {}
    return _pin_totals_cache[key].get(sport, [])


def _odds_keys(sport):
    """Active, non-outright Odds API sport keys for one of our sports (free /sports)."""
    global _odds_sports
    if _odds_sports is None:
        try:
            _odds_sports, headers = _odds_get("/sports", {})
            _odds_note_usage(headers)
        except RuntimeError as e:
            _mark("pinnacle", False, str(e))
            _odds_sports = []
    return [s["key"] for s in _odds_sports
            if s.get("group") == ODDS_GROUPS.get(sport) and s.get("active")
            and not s.get("has_outrights")]


_pinnacle_event_cache = {}


def pinnacle_events(sport):
    """[{a, b, start}] for every event the Odds API lists in `sport`. Free: /events only.

    Cached per sport for the run, so re-timing the universe and pricing it share one call.
    """
    if sport in _pinnacle_event_cache:
        return _pinnacle_event_cache[sport]
    out = []
    if _odds_key() and sport in ODDS_GROUPS:
        now = datetime.now(timezone.utc)
        window = dict(commenceTimeFrom=(now - timedelta(hours=FIGHT_LOOKBACK_H))
                      .strftime("%Y-%m-%dT%H:%M:%SZ"),
                      commenceTimeTo=(now + timedelta(days=ODDS_HORIZON_DAYS))
                      .strftime("%Y-%m-%dT%H:%M:%SZ"))
        for key in _odds_keys(sport):
            try:
                events, _h = _odds_get(f"/sports/{key}/events", window)
            except RuntimeError as e:
                _mark("pinnacle", False, str(e))
                continue
            for ev in events:
                try:
                    st = datetime.fromisoformat(str(ev["commence_time"]).replace("Z", "+00:00"))
                except (KeyError, TypeError, ValueError):
                    continue
                out.append(dict(a=ev.get("home_team", ""), b=ev.get("away_team", ""),
                                start=st, key=key))
    _pinnacle_event_cache[sport] = out
    return out


def apply_pinnacle_starts(sport, rows, events=None, now=None):
    """Re-time fight rows from Pinnacle's per-bout commence time. Returns (rows, stats).

    A row matched to a Pinnacle event gets start = commence - PINNACLE_START_MARGIN_MIN
    and start_source "pinnacle". A row with no match keeps its venue start, and is dropped
    if that start has already passed — exactly the rule every other sport runs under, so
    an un-retimed bout can never be logged later than before.
    """
    now = now or datetime.now(timezone.utc)
    events = pinnacle_events(sport) if events is None else events
    kept, matched, shifts = [], 0, []
    for r in rows:
        best = None
        for ev in events:
            score, _flip = pair_match(r["side_a"], r["side_b"], ev["a"], ev["b"], sport=sport)
            if score > 0 and (best is None or score > best[0]):
                best = (score, ev)
        venue_start = datetime.fromisoformat(str(r["start"]))
        if venue_start.tzinfo is None:
            venue_start = venue_start.replace(tzinfo=timezone.utc)
        if best:
            st = best[1]["start"] - timedelta(minutes=PINNACLE_START_MARGIN_MIN)
            # Never trust a match that disagrees with the venue by more than a day: two
            # bouts between the same surnames on different cards is a wrong match.
            if abs((st - venue_start).total_seconds()) <= 24 * 3600:
                shifts.append((st - venue_start).total_seconds() / 60)
                r = dict(r, start=st.isoformat(), date=st.strftime("%Y-%m-%d"),
                         start_source="pinnacle", venue_start=venue_start.isoformat())
                matched += 1
                kept.append(r)
                continue
        if venue_start >= now - timedelta(minutes=5):
            kept.append(dict(r, start_source="venue"))
    return kept, dict(matched=matched, dropped=len(rows) - len(kept), shifts=shifts)


ESPN_MATCH_DAYS = 3


def apply_espn_starts(rows, fixtures=None, now=None):
    """Re-time Kalshi soccer rows from ESPN's kickoff. Returns (rows, stats).

    Kalshi publishes no kickoff: a soccer row's start is its expected expiration minus three
    hours, and its ticker date can be a placeholder — Torino v Roma was listed for Sep 13 at
    10:30 while ESPN had it on Sep 14 at 16:30. ESPN's fixture feed (the one the boards use)
    has the real kickoff, so a row matched to an ESPN fixture — same two clubs, home first,
    within ESPN_MATCH_DAYS — takes that kickoff (start_source "espn", the Kalshi estimate
    kept as venue_start). A row whose ESPN fixture has started or finished is dropped. An
    unmatched row keeps Kalshi's estimate under the usual rule. Fail-soft: no ESPN feed, no
    change.
    """
    now = now or datetime.now(timezone.utc)
    if fixtures is None:
        try:
            import streaks_fetch
            fixtures = streaks_fetch.load_or_fetch()["fixtures"]
        except Exception:
            return rows, dict(matched=0, dropped=0, shifts=[], feed=False)
    fx = []
    for f in fixtures:
        try:
            ko = datetime.fromisoformat(str(f.get("kickoff")).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            continue
        fx.append((ko, f))
    kept, matched, shifts = [], 0, []
    for r in rows:
        try:
            est = datetime.fromisoformat(str(r["start"]))
        except (KeyError, TypeError, ValueError):
            kept.append(r)
            continue
        if est.tzinfo is None:
            est = est.replace(tzinfo=timezone.utc)
        best, second = None, None
        for ko, f in fx:
            if abs((ko - est).total_seconds()) > ESPN_MATCH_DAYS * 86400:
                continue
            score, flip = pair_match(r["side_a"], r["side_b"], f["home"], f["away"], sport="soccer")
            if score <= 0 or flip:
                continue
            if best is None or score > best[0]:
                best, second = (score, ko, f), best
            elif second is None or score > second[0]:
                second = (score, ko, f)
        if best and not (second and abs(best[0] - second[0]) < 1e-9 and second[1] != best[1]):
            _score, ko, f = best
            if f.get("played") or ko <= now:
                continue                              # already under way or finished
            shifts.append((ko - est).total_seconds() / 60)
            matched += 1
            kept.append(dict(r, start=ko.isoformat(), date=ko.strftime("%Y-%m-%d"),
                             start_source="espn", venue_start=est.isoformat()))
            continue
        kept.append(r)
    return kept, dict(matched=matched, dropped=len(rows) - len(kept), shifts=shifts, feed=True)


# Pinnacle is not in here: it is planned across every sport after these have run, so its
# credits go to the contests none of them cover (plan_pinnacle, called from publish).
CHALLENGERS = {
    "polymarket": polymarket_com_probs,
    "btts_market": fetch_btts_market,
    "btts_form_l10": fetch_btts_form_l10,
    "goals_market": fetch_goals_market,
    "corners_market": fetch_corners_market,
    "corners_under": fetch_corners_under,
    "tennis_fav_band": fetch_tennis_fav_band,
    "tennis_fav_band_3h": fetch_tennis_fav_band_3h,
    "tennis_combo2": fetch_tennis_combo2,
    "tennis_combo3": fetch_tennis_combo3,
    "tennis_combo4": fetch_tennis_combo4,
    "pm_combo2": fetch_pm_combo2,
    "pm_combo3": fetch_pm_combo3,
    "pm_combo4": fetch_pm_combo4,
    "mma_fav_band": fetch_tennis_fav_band,          # the same band, another sport
    "tt_band_55_60": fetch_tt_band,
    "mlb_fade_streak": fetch_mlb_fade_streak,
    "o15_form_l10": fetch_o15_form_l10,
    "o15_cup_mismatch": fetch_o15_cup_mismatch,
    "o15_ranked": fetch_o15_ranked,
    "team2_ranked": fetch_team2_ranked,
    "team1_form_l5": fetch_team1_form_l5,
    "team2_form_l10": fetch_team2_form_l10,
    "liga_btts_even": fetch_liga_btts_even,
    "liga_u15_dog": fetch_liga_u15_dog,
    "bund_o35": fetch_bund_o35,
    "bund_o35_draw": fetch_bund_o35_draw,
    "ere_o15": fetch_ere_o15,
    "ere_draw": fetch_ere_draw,
    "u35_low_scoring": fetch_u35_low_scoring,
    "o25_congestion": fetch_o25_congestion,
    "pin_totals": fetch_pin_totals,
    "p05_unbeaten": fetch_p05_unbeaten,
    "cmd_tail": fetch_cmd_tail,
    "gas_nochange": fetch_gas_nochange,
    "cmd_market": fetch_cmd_market,
    "nhl_rest_edge": fetch_nhl_rest_edge,
    "nhl_dog_pl": fetch_nhl_dog_pl,
    "olbg": fetch_olbg,
    "kalshi": fetch_kalshi,
    "espn_fpi": fetch_espn_fpi,
    "draftkings": fetch_draftkings,
    "covers": fetch_covers,
    "scores24": fetch_scores24,
    "oddspedia": fetch_oddspedia,
    "sportsgambler": fetch_sportsgambler,
    "soccerpredictions": fetch_soccerpredictions,
    "nws": fetch_nws,
    "nws_fade": fetch_nws_fade,
    "spot": fetch_spot,
}# Retired sources (connected=False, with a `retired` reason) are dropped from the run: they log
# nothing new, while their open bets still settle and their record stays on the board.
CHALLENGERS = {k: v for k, v in CHALLENGERS.items() if SOURCES[k]["connected"]}

