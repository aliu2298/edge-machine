#!/usr/bin/env python3
"""production.py — the Production stage: the pairs put here by hand, and their bets.

    Sandbox -> Production (by hand)

A (source, sport) pair is IN PRODUCTION because it was put there BY HAND: listed in
sandbox_track.PAIR_OVERRIDES, on the record the Sandbox measured. Nothing promotes itself
(2026-09-18). A pair leaves the same way, or on its own when it stops working — no new bet in
STALE_DAYS, behind the prices it paid, or beaten by a blind rule on the same contests.

data/production_leads.json is the machine-readable feed. It has the Leads ledger's shape —
{"leads": {id: lead}, "updated_at", "board_built_at"} — so anything that reads one reads both:

  * every bet a Production pair logs AFTER it entered Production, and only bets the feed can
    express as a standard claim (sandbox_track.placeable): a soccer result (home, away or draw)
    on a Kalshi GAME market, or Yes on a soccer goals market, in a mapped league
  * and only with a VERIFIED kickoff (start_source "espn"). Kalshi publishes no kickoff and
    its estimate has been a day off both ways; a kickoff listed too late would publish a
    match already in play as upcoming. Held back and counted.
  * bet {"kind": "match_result", "side": "home" | "away" | "draw"} (home = the Kalshi event's first
    side, sandbox_sources.kalshi_sides), or {"kind": "total_gte", "n": 2} /
    {"kind": "team_gte", "n": 1 | 2, "team": ...} — the Leads board's own bet vocabulary
  * status pending / hit / miss / void / price from the Sandbox settlement.
    A price payout is the amount the venue paid. It is not a hit, a miss, or a void.
  * last_seen_at == board_built_at on every lead still open; a lead whose pair has left
    Production is dropped from the file, which reads as withdrawn

An empty feed is normal until the first pair arrives. This file only ever changes when the
tracker runs (every 3h).
"""
import datetime, html, json, os, sys

import fmt
import sandbox_sources as S
import sandbox_track as T
import site_chrome

ROOT = os.path.dirname(os.path.abspath(__file__))
FEED = os.path.join(ROOT, "data", "production_leads.json")
KEEP_SETTLED_DAYS = 7          # settled leads stay in the feed this long, so results can be joined
STATUS = {"open": "pending", "won": "hit", "lost": "miss", "void": "void", "settled": "price"}


def esc(x):
    return html.escape(str(x if x is not None else ""))


def production_pairs(st):
    """{"source|sport": pair} for every pair in Production and trading."""
    return {k: p for k, p in (st.get("pairs") or {}).items()
            if p.get("stage") == "production" and p.get("ready_at")}


def entered_at(pair):
    """When the pair's Production record starts."""
    return pair.get("ready_at") or pair.get("promoted_at")


def route_label(pair):
    return f"moved by hand on {pair['by_hand']}" if pair.get("by_hand") else "moved by hand"


def _one_instant(value):
    """One timestamp as a UTC instant, or None when it cannot be parsed or converted.

    An out-of-range instant (year 1 at midnight UTC, converted into a zone
    behind UTC) raises OverflowError. A malformed string raises ValueError.
    Callers show a placeholder or skip the quote; they do not crash.
    """
    try:
        dt = datetime.datetime.fromisoformat(str(value))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=datetime.timezone.utc)
        return dt.astimezone(datetime.timezone.utc)
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def _kickoff(q):
    """The EARLIEST credible UTC start for this bet, or None when none parses.

    A row can carry two times that do not agree. `start` is the one a source may have
    adjusted — Pinnacle re-times a fight from the card — and `venue_start` is the route
    venue's own time for this contest. On 2026-10-03 ten open bets disagreed, four of
    them with `start` LATER than the venue's: Pinnacle put a UFC bout at the card's
    23:30Z while Polymarket US listed that bout at 21:30Z, and a boxing row was three
    hours late. Publishing the later time is the dangerous direction, because a consumer
    measures its own cutoff backwards from this field: at 30 minutes before 23:30Z the
    feed still called that pick open for ninety minutes after the fight had begun, and
    Polymarket US keeps a fight market trading throughout. Only a price ceiling stood
    between the feed and a bet placed on a result already half known.

    So the feed takes the EARLIER of the two, always. Being early costs a bet that was
    never placed; being late buys into a contest whose outcome is partly settled, and
    that is not a risk a paper record can price. `start` alone is used when it is the
    only one that parses, which is the common case.
    """
    cands = [t for t in (_one_instant(q.get("start")), _one_instant(q.get("venue_start")))
             if t is not None]
    return min(cands) if cands else None


def start_verified(q):
    """Is this bet's start time a real start rather than an estimate?

    Kalshi publishes a DATE for a soccer fixture, not a kickoff, so soccer leads are held
    back until an ESPN fixture has confirmed the time — otherwise a bet could be published
    on a match already under way. Polymarket US publishes the match start itself, which is
    where the tennis lane's times come from.
    """
    if q.get("venue") == "combo":
        # A basket inherits the verification of its WORST leg -- the builder already reduced
        # them to one -- because it cannot be bought once any single leg has started.
        # kalshi_milestone is a cricket source. It counts on a basket only when every
        # leg that carries it is cricket. A tennis basket, or a basket with no such
        # leg, does not become verified by wearing that source.
        source = q.get("start_source")
        if source not in T.VERIFIED_STARTS:
            return False
        if source != "kalshi_milestone":
            return True
        carriers = [l for l in (q.get("legs") or [])
                    if isinstance(l, dict)
                    and l.get("start_source", "kalshi_milestone") == "kalshi_milestone"]
        return bool(carriers) and all(l.get("sport") == "cricket" for l in carriers)
    if q.get("sport") in T.ROUTED_SPORTS:
        # Polymarket US publishes the contest's own start; a Kalshi row has one only once
        # something has confirmed it (the tennis schedule, an ESPN fixture, or, for
        # cricket, Kalshi's own milestone once it agrees with the ticker and the rules).
        # kalshi_milestone is a cricket source. On any other sport it is not a start.
        source = q.get("start_source")
        verified = (source in T.VERIFIED_STARTS
                    and (source != "kalshi_milestone" or q.get("sport") == "cricket"))
        return q.get("venue") == "polymarket_us" or verified
    return q.get("start_source") == "espn"


def lead_from_quote(q, pair_key, built):
    """One Sandbox bet as a feed lead."""
    ko = _kickoff(q)
    if ko is None:
        raise ValueError("kickoff is missing or out of range")
    label = S.SOURCES.get(q["source"], {}).get("label", q["source"]).split(" (")[0]
    date = ko.date().isoformat()
    if q.get("venue") == "combo":
        legs = q.get("legs") or []
        home = away = None
        headline = f"{len(legs)}-leg combo: " + " + ".join(str(l.get("name"))[:18] for l in legs)
        bet = {"kind": "combo", "n": len(legs), "all_must_win": True}
    elif q["sport"] in T.FEED_BETS:
        bet = dict(T.FEED_BETS[q["sport"]])
        home, away = q["espn_home"], q["espn_away"]
        if bet["kind"] == "team_gte":
            bet["team"] = q["team"]
            headline = f"{q['team']} to score {bet['n']}+"
        elif bet["kind"] == "total_lte":
            # total_lte n means n goals or fewer, i.e. under (n + 0.5).
            headline = f"Under {bet['n'] + 0.5:g} goals"
        else:
            headline = f"Over {bet['n'] - 0.5:g} goals"
    elif True:
        home, away = q["side_a"], q["side_b"]
        side = {"a": "home", "b": "away", "draw": "draw"}[q["pick"]]
        bet = {"kind": "match_result", "side": side}
        headline = "Draw" if side == "draw" else f"{home if side == 'home' else away} to win"
    # A sport with no league table to look the fixture up in carries the venue's own market
    # instead, so a follower buys the contract this bet was priced on rather than one found
    # by matching two player names across two sites.
    route = None
    if q.get("venue") == "combo":
        # A basket has no market to hit. The route therefore says what to ASK for, not what
        # to buy: the collection, each leg and its side, and max_price -- the most this bet
        # is worth paying, which is the product of the legs plus the markup Kalshi's RFQ was
        # measured at. A quote above that is a different bet, and the resting book (7.4% and
        # 9.8% worse on the only baskets that had an ask) is never it.
        route = {"venue": "kalshi", "instrument": "combo", "how": "request_quote",
                 "collection": S.COMBO_COLLECTION,
                 "max_price": round(float(q["price"]), 4),
                 "legs": [{"market": l["market_id"], "name": l.get("name"),
                           "side": "yes" if l["pick"] == "a" else "no",
                           "starts": str(l.get("start"))[:16]} for l in (q.get("legs") or [])]}
    elif q["sport"] in T.FEED_BETS and bet["kind"] == "total_lte":
        # An under is the No side of the over market, and Kalshi lists one contract per
        # STRIKE inside the totals event -- the -4 ticker is over 3.5, the -3 over 2.5.
        # So the lead names the exact contract it was priced on and says which side to
        # take, rather than leaving a follower to pick a strike and then invert it. Every
        # other FEED_BETS lane is a plain Yes on a market its headline fully identifies,
        # and keeps no route.
        route = {"venue": "kalshi", "market": q["market_id"],
                 "outcome": headline, "outcome_side": "no"}
    elif q["sport"] in T.ROUTED_SPORTS:
        # Kalshi lists a market per player inside one event, so backing either player is a
        # plain Yes on that player's market. Polymarket lists ONE market with two outcomes,
        # so the second player is the No side of it.
        route = {"venue": q["venue"], "market": q["market_id"],
                 "outcome": home if q["pick"] == "a" else away,
                 "outcome_side": "yes" if (q["pick"] == "a" or q["venue"] == "kalshi") else "no"}
    lead = {
        "id": (f"{date}|{q['market_id']}|{headline} · {label}" if home is None
               else f"{date}|{home}|{away}|{headline} · {label}"),
        "date": date, "kickoff": ko.strftime("%Y-%m-%dT%H:%MZ"),
        "league": S.quote_league(q) or (S.SPORTS.get(q["sport"]) if q["sport"] in T.ROUTED_SPORTS else None),
        "match": headline if home is None else f"{home} v {away}",
        "home": home, "away": away, "headline": headline,
        "bet": bet,
        "status": STATUS.get(q["status"], "void"),
        "first_seen": str(q["logged"])[:10],
        "source": q["source"], "sport": q["sport"], "pair": pair_key, "lane": "production",
        "sandbox_quote": q["id"], "price_at_log": q.get("price"), "edge_at_log": q.get("edge"),
    }
    # A model pair's claim is a PROBABILITY, and that is what a follower should judge today's
    # price against — not how far the price has drifted since the Sandbox wrote it down days
    # earlier. Two-way markets only: in a three-way one 1 - P(home) also holds the draw.
    if q.get("prob_a") is not None and q.get("edge") is not None and q.get("price_draw") is None:
        pa = float(q["prob_a"])
        lead["model_prob"] = round(pa if q["pick"] == "a" else 1.0 - pa, 4)
    if route:
        lead["route"] = route
    if lead["status"] == "pending":
        lead["last_seen"] = built[:10]
        lead["last_seen_at"] = built
    return lead


def _assess_since_kickoff(d, key, pair):
    """US-exchange record for contests that kick off at or after this pair entered.

    The feed publishes a bet when `_kickoff(q).isoformat() >= entered_at(pair)`.
    `assess` windows on `logged`, so this copies the ledger and the archive,
    keeps only this pair's rows in that kickoff window, and calls `assess`
    with the log window open. A row with no readable kickoff is not in it.
    """
    source, sport = key.split("|", 1)
    entered = entered_at(pair)

    def kept(rows):
        out = []
        for q in rows or ():
            if q.get("source") != source or q.get("sport") != sport:
                continue
            ko = _kickoff(q)
            if ko is not None and entered is not None and ko.isoformat() >= entered:
                out.append(q)
        return out

    window = {"quotes": kept(d.get("quotes")), "_archive": kept(d.get("_archive"))}
    return T.assess(window, source, sport, since=None, venues=T.TRADEABLE_VENUES)


def _sandbox_record(d, key, since):
    # `since` is entered_at(pair). The record counts the contest, not the log.
    a = _assess_since_kickoff(d, key, {"ready_at": since})
    r = lambda x: round(x, 4) if isinstance(x, float) else x
    return {"sandbox_n": a["n"], "sandbox_roi": r(a["roi"]), "sandbox_roi_fee": r(a["roi_fee"]),
            "sandbox_clv": r(a["clv"])}


def prune_feed(path=None, st=None):
    """Strip every lead from a pair that is no longer in Production. Returns how many went.

    The feed is rebuilt from scratch on each tracker run, so it is correct three hours after
    a demotion. Three hours is too long: this file is the one thing here that reaches past a
    web page, and a follower reading it has no way to know a pair was taken off the list an
    hour ago. On 2026-09-23 the tennis band left Production and the feed went on naming 285
    of its open leads until the next run.

    Two holes, one fix. This runs BEFORE anything else in a tracker run, so a demotion
    committed since the last one takes effect immediately rather than at the end; and it runs
    again if build_feed throws, because the old file staying put is exactly the failure that
    would otherwise go unnoticed -- the run prints a warning and the stale feed keeps being
    served.

    It reads the file and the stage registry only. No ledger, no network, nothing that can
    fail in a way that leaves a demoted pair published.
    """
    path = path or FEED
    try:
        with open(path) as f:
            blob = json.load(f)
    except (OSError, ValueError):
        return 0
    live = set(production_pairs(st if st is not None else T.load_stages()))
    leads = blob.get("leads") or {}
    gone = [i for i, l in leads.items() if l.get("pair") not in live]
    stale_pairs = [k for k in (blob.get("pairs") or {}) if k not in live]
    if not gone and not stale_pairs:
        return 0
    for i in gone:
        del leads[i]
    for k in stale_pairs:
        del blob["pairs"][k]
    blob["pruned_at"] = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat()
    save_feed(blob, path)
    return len(gone)


def build_feed(d, st, now=None):
    """The Production feed as a dict. Pure: `d` is the Sandbox ledger, `st` the stage registry."""
    now = now or datetime.datetime.now(datetime.timezone.utc)
    built = now.replace(microsecond=0).isoformat()
    # A removed lane never reaches the feed, even if a stage file still names it.
    # Hiding the page is not enough: this file is what a follower reads.
    pairs = {}
    for key, pair in production_pairs(st).items():
        source, _, sport = str(key).partition("|")
        if S.lane_removed(source, sport):
            continue
        pairs[key] = pair
    leads, skipped, unverified = {}, 0, 0
    for key, pair in pairs.items():
        source, sport = key.split("|", 1)
        for q in T.all_bets(d):
            if S.lane_removed(q.get("source"), q.get("sport")):
                continue
            # The pair key is the whole match. team1_form_l5|soccer_team1_intl is
            # its own pair; a _cup sport, or any other suffix, does not satisfy it.
            if q["source"] != source or q["sport"] != sport or not q.get("bet"):
                continue
            try:
                ko = _kickoff(q)
            except (KeyError, TypeError, ValueError, OverflowError, OSError):
                continue
            if ko is None:
                continue
            # Published on the CONTEST, not on when the bet was written down. A pair moved
            # into Production has usually logged the next few days' fixtures already — under
            # a "logged since entry" rule those matches were never published at all, and the
            # lane sat silent for a day for no reason. What matters is that the pair was in
            # Production when the match was played.
            if ko.isoformat() < entered_at(pair):
                continue
            if q["status"] == "open" and ko <= now:
                continue                              # started: nothing left to act on
            if q["status"] != "open" and ko < now - datetime.timedelta(days=KEEP_SETTLED_DAYS):
                continue
            if not T.placeable(q):
                skipped += 1
                continue
            if not start_verified(q):
                unverified += 1
                continue
            lead = lead_from_quote(q, key, built)
            leads[lead["id"]] = lead
    return {
        "updated_at": built, "board_built_at": built, "stage": "production",
        # The Sandbox's own record for each pair since it entered Production, counted on
        # kickoff — the same contest the leads use — at the logged price, so a follower's
        # real fills can be compared with it.
        "pairs": {k: dict({"ready_at": p.get("ready_at"), "promoted_at": p.get("promoted_at"),
                           "entered_at": entered_at(p), "route": route_label(p),
                           "by_hand": p.get("by_hand")},
                          **_sandbox_record(d, k, entered_at(p)))
                  for k, p in pairs.items()},
        "leads": leads, "unlisted_skipped": skipped, "unverified_kickoff_skipped": unverified,
    }


def save_feed(blob, path=None):
    """Replace the published feed, or leave the previous file untouched.

    production_leads.json is what the site serves. A crash mid-write must not
    truncate it to empty for the next reader.
    """
    path = path or FEED
    T.atomic_write_json(path, blob, prefix=".feed-")


def load_feed(path=None):
    try:
        with open(path or FEED) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {"leads": {}, "pairs": {}}


def _day_label(day, today):
    """'Today · Oct 7', 'Tomorrow · Oct 8', or 'Oct 9' for a kickoff date.

    The same month-day form the rest of the site prints, with a word for
    today and tomorrow only.
    """
    delta = (day - today).days
    text = f"{fmt._MONTHS[day.month - 1]} {day.day}"
    if delta == 0:
        return f"Today · {text}"
    if delta == 1:
        return f"Tomorrow · {text}"
    return text


EARLY_N = 10      # under this many settled bets an ROI is shown grey and marked too early


def _tone(x, n, digits=1):
    """Colour class for a percent, following the displayed digits.

    No sample, or a value that rounds to 0 at `digits`, is neutral. -0.04%
    shown as 0.0% is mut, not neg.
    """
    if not n or x is None:
        return "mut"
    return fmt.tone(x, spec=f".{digits}f", scale=100)


# Shown when a kickoff cannot be parsed or converted. The row stays on the page.
PLACEHOLDER_DATE = "—"


def _chicago_day(value):
    """America/Chicago calendar date, or None if the instant cannot be converted.

    fmt.chicago uses zoneinfo, so CDT and CST both apply. OverflowError is a
    real outcome for an out-of-range timestamp, not a bad string.
    """
    try:
        return fmt.chicago(value).date()
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def _ct_date(kickoff):
    """YYYY-MM-DD of the kickoff on the Chicago calendar."""
    day = _chicago_day(kickoff)
    return day.isoformat() if day is not None else PLACEHOLDER_DATE


def _ct_clock(kickoff):
    """The kickoff clock in CT."""
    try:
        return fmt.clock(kickoff)
    except (ValueError, TypeError, OverflowError, OSError):
        return PLACEHOLDER_DATE


def _ct_when(kickoff):
    try:
        return fmt.when(kickoff)
    except (ValueError, TypeError, OverflowError, OSError):
        return PLACEHOLDER_DATE


_BAD_KICKOFF = set()
_KICKOFF_UNKNOWN = "kickoff unknown"


def _clip_shown(value, limit=80):
    """A log-safe slice of a raw kickoff. Newlines would break a workflow command."""
    if not isinstance(value, str):
        value = repr(value)
    value = value.replace("\r", " ").replace("\n", " ")
    if len(value) <= limit:
        return value
    return value[:limit] + "…"


# A Production pair is GREEN or RED. Green means everything it has logged lately reached
# the feed and it is still publishing. Red means a fault, and a fault here is the dangerous
# kind: it is SILENT. A bet the feed cannot express is simply dropped -- no error, no row, no
# trace on the page -- which is how mma_fav_band ran for weeks with seven of twenty-one bets
# unreachable and cricket with nineteen of thirty, both unnoticed until someone went looking.
#
# Red fires on three faults, each of which would otherwise pass unseen:
#   dropped  a bet logged inside HEALTH_WINDOW_DAYS that placeable() refuses. The pair had an
#            opinion and nothing downstream could act on it.
#   dark     no leads in the feed AND nothing logged in the window. Not merely quiet: quiet
#            with nothing to show for it.
#   unwired  the pair is listed in Production but missing from the feed's own pairs map, so
#            the two halves disagree about what is live.
# A pair that is merely WAITING -- publishing leads, declining on price, between fixtures --
# is green. A light that cries wolf is a light that gets ignored, so quiet alone is not a
# fault; the Since-Production cell already says how quiet.
HEALTH_WINDOW_DAYS = 7


def pair_health(key, bets, lead_count, feed_pairs, now=None, window_days=HEALTH_WINDOW_DAYS):
    """(state, reason) for one Production pair: "ok" or "bad", and why.

    `bets` is every bet the pair has logged, `lead_count` how many leads it has in the feed,
    `feed_pairs` the feed's own pairs map. Pure: it takes what it needs rather than reading
    files, so the faults can be tested without a ledger.
    """
    now = now or datetime.datetime.now(datetime.timezone.utc)
    cut = (now - datetime.timedelta(days=window_days)).isoformat()
    if feed_pairs is not None and key not in feed_pairs:
        return "bad", "listed in Production but missing from the feed"
    recent = [q for q in bets if str(q.get("logged") or "") >= cut]
    dropped = [q for q in recent if not T.placeable(q)]
    if dropped:
        return "bad", (f"{len(dropped)} of {len(recent)} recent bets cannot be published "
                       f"— the feed drops them silently")
    if not lead_count and not recent:
        return "bad", f"no leads and nothing logged in {window_days}d"
    return "ok", ("publishing" if lead_count else "nothing to publish yet")


def _days_since(when, now=None):
    """Whole days from `when` to now, or None when `when` is unreadable.

    Used only to say how long a Production pair has gone without logging a bet.
    """
    if not when:
        return None
    try:
        t = datetime.datetime.fromisoformat(str(when).replace("Z", "+00:00"))
    except ValueError:
        return None
    if t.tzinfo is None:
        t = t.replace(tzinfo=datetime.timezone.utc)
    now = now or datetime.datetime.now(datetime.timezone.utc)
    return max(0, int((now - t).total_seconds() // 86400))


def _kickoff_known(lead):
    """True when the kickoff parses. A naive timestamp is UTC, via fmt.chicago."""
    raw = lead.get("kickoff")
    if not isinstance(raw, str) or not raw:
        return False
    try:
        fmt.chicago(raw)
    except (TypeError, ValueError, OverflowError, OSError):
        return False
    return True


def _kickoff_key(lead):
    """Order a lead by its kickoff text. Every unreadable kickoff sorts last.

    A readable kickoff is the raw string under a shared prefix, so a feed of
    real timestamps sorts exactly as it did when the key was the raw field.
    None, a missing key, and a garbage string share one key.
    """
    raw = lead.get("kickoff")
    if isinstance(raw, str) and _kickoff_known(lead):
        return (0, raw)
    return (1, "")


def _note_kickoff(lead):
    """Warn once when a lead's kickoff is missing or will not parse.

    The lead stays on the page, labeled kickoff unknown. It is not a lead
    still to come and it does not set the next-lead tile.
    """
    missing = "kickoff" not in lead
    raw = None if missing else lead.get("kickoff")
    if _kickoff_known(lead):
        return
    shown = "missing" if missing else ("None" if raw is None else _clip_shown(raw))
    token = (lead.get("id") or lead.get("match"), shown)
    if token in _BAD_KICKOFF:
        return
    _BAD_KICKOFF.add(token)
    print(f"::warning::lead {lead.get('match')!r} has unreadable kickoff ({shown}); "
          f"shown as kickoff unknown", file=sys.stderr)


def _pending_to_come(lead, now_str):
    """A pending lead still to show. An unreadable kickoff is not in the past."""
    if lead["status"] != "pending":
        return False
    if not _kickoff_known(lead):
        return True
    return lead.get("kickoff") >= now_str


def _without_weather(d):
    """Page copy. Stored quotes stay in the ledger file."""
    if not d:
        return d
    out = dict(d)
    if d.get("quotes"):
        out["quotes"] = [q for q in d["quotes"] if not S.removed_row(q)]
    if d.get("_archive"):
        out["_archive"] = [q for q in d["_archive"] if not S.removed_row(q)]
    return out


def _weather_pair(key):
    source, _, sport = str(key).partition("|")
    return S.lane_removed(source, sport)


def _coming_up_count(n_leads, n_days):
    """'3 leads over 2 days', or a plain 'nothing scheduled' instead of '0 leads over 0 days'."""
    if not n_leads:
        return "nothing scheduled"
    return (f"{n_leads} lead{'s' if n_leads != 1 else ''} over "
            f"{n_days} day{'s' if n_days != 1 else ''}")


def _held_count(held):
    return "nothing held back" if not held else str(held)


def _held_note(held, blob):
    unlisted = blob.get("unlisted_skipped", 0)
    unverified = blob.get("unverified_kickoff_skipped", 0)
    if not held:
        return ('<div class="note">Every bet these pairs logged was published. A bet is held '
                'back only when it cannot be expressed as a standard market, or when its '
                'start time is not yet verified.</div>')
    return (f'<div class="note">{held} bet{"s" if held != 1 else ""} from these pairs '
            f'{"were" if held != 1 else "was"} not published: {unlisted} cannot be expressed '
            f'as a standard market, and {unverified} {"are" if unverified != 1 else "is"} '
            f'waiting for a verified start time. A lead is only published once its start '
            f'has been confirmed.</div>')


def page(d, st, blob, style, now=None):
    """public_site/production.html — shares the Sandbox stylesheet.

    Organised as the questions a visitor actually asks, in order: what is in Production and on
    what evidence, what is coming up and when, how the recent leads have landed, what was held
    back, and — folded away — how a pair gets here. Written for a public page: it describes
    published leads and the record behind them, never anything that acts on them.
    """
    now_dt = now or datetime.datetime.now(datetime.timezone.utc)
    today = _chicago_day(now_dt)
    # Headlines and the lead list use the page copy. The record on each card
    # is assessed on the unfiltered ledger, the same one the tracker reads,
    # so a hidden row cannot move a kept pair's numbers.
    raw = d
    d = _without_weather(d)
    pairs = {k: v for k, v in production_pairs(st).items() if not _weather_pair(k)}
    # The display name, with its scope where two Production rules share one name
    # ("Team scores 1+ form rule · Clubs" and "· Internationals"). The pair key and
    # the lead ids keep the plain label.
    name = lambda key: S.scoped_rule(*(key.split("|", 1) + [None])[:2]) if "|" in key else S.scoped_rule(key)
    sport_of = lambda key: S.SPORTS.get(key.split("|")[1], key.split("|")[1])
    label = lambda key: f"{name(key)} · {sport_of(key)}"
    pct = lambda x: fmt.pct(x, digits=1, sign=True)
    tone = lambda x, n: _tone(x, n, digits=1)
    leads = [l for l in blob.get("leads", {}).values()
             if not S.removed_row(l) and not _weather_pair(l.get("pair") or "")]
    for lead in leads:
        _note_kickoff(lead)
    now_str = now_dt.strftime("%Y-%m-%dT%H:%MZ")
    pending = sorted((l for l in leads if _pending_to_come(l, now_str)), key=_kickoff_key)
    # Unreadable kickoffs sort last. They stay on the page and out of the
    # "still to come" count and the next-lead tile.
    upcoming = [l for l in pending if _kickoff_known(l)]
    unknown_up = [l for l in pending if not _kickoff_known(l)]
    landed = [l for l in leads if l["status"] in ("hit", "miss")]
    settled_known = sorted(
        (l for l in leads if l["status"] in ("hit", "miss", "price") and _kickoff_known(l)),
        key=lambda l: l["kickoff"], reverse=True)
    settled_unknown = [l for l in leads
                       if l["status"] in ("hit", "miss", "price") and not _kickoff_known(l)]

    # ---- the pairs, each with the evidence it was moved on and what it has done since ----
    cards = []
    for key, pair in sorted(pairs.items(), key=lambda kv: (sport_of(kv[0]), name(kv[0]))):
        source, sport = key.split("|", 1)
        since = entered_at(pair)
        # The SAME window the Sandbox page reads (the pair's stage clock), so the two pages
        # never show two different records for one rule.
        whole = T.assess(raw, source, sport, since=pair.get("since"), venues=T.TRADEABLE_VENUES)
        live = _assess_since_kickoff(raw, key, pair)
        mine = [l for l in leads if l.get("pair") == key]
        to_come = sum(1 for l in mine if l in upcoming)
        clv = fmt.signed_cents(whole["clv"])
        # WHY the Since-Production record is empty, which "none yet" alone hid. Three pairs
        # read "— none yet" at once and they meant three different things: one had two bets
        # running and nothing settled, one had logged nothing in two days, and one cannot be
        # executed at all. A pair idling is a thing to act on; a pair waiting is not, and the
        # column has to tell them apart.
        # Same inclusive kickoff test as _assess_since_kickoff. Open and priced-out
        # rows never enter the settled record, and the note under it counts the contest.
        mine_since = []
        for q in (raw.get("quotes") or []):
            if q.get("source") != source or q.get("sport") != sport:
                continue
            ko = _kickoff(q)
            if ko is not None and since is not None and ko.isoformat() >= since:
                mine_since.append(q)
        open_since = sum(1 for q in mine_since if q.get("bet") and q.get("status") == "open")
        # PICKED BUT NOT BACKED is its own state, and the first version of this cell missed
        # it. team1_form_l5 on the internationals read "nothing in 2d" while it had picked
        # Spain to score at 0.99 and the Netherlands at 0.97 -- both refused by PRICE_CEIL,
        # which is the rule working, not idling. A lane declining on price has an opinion;
        # a lane seeing no board has none, and the column must not call them the same thing.
        priced_out = sum(1 for q in mine_since if not q.get("bet"))
        # REACHABLE: of this pair's bets, how many the feed could ever publish. A pair can be
        # promoted on a record only partly visible downstream -- cricket was moved on +142.8%
        # across 30 bets of which 11 were reachable, and those 11 return +270% while the other
        # 19 return +2.5%. Two lanes under one name. Nothing on this page said so, so it had
        # to be dug out. The gate still judges the whole record; this only shows the gap.
        # bet_rows, not all_bets. Two cases are counted once. An id in both the
        # live ledger and the archive, for example from a bad merge, keeps the
        # live row. An id repeated inside the archive, for example a doubled
        # archive file, keeps the first archive copy. save() writes the ledger
        # before the archive, so a crash between those writes leaves the row in
        # retired and not in the archive file. It does not leave a duplicate.
        # all_bets stays the raw list everywhere else (the feed, the day check,
        # the audit).
        all_bets = [q for q in T.bet_rows(raw)
                    if q.get("source") == source and q.get("sport") == sport and q.get("bet")]
        reach_n = sum(1 for q in all_bets if T.placeable(q))
        reach = (f"{reach_n} of {len(all_bets)}" if all_bets else "—")
        reach_tone = "" if not all_bets or reach_n == len(all_bets) else "neg"
        state, why = pair_health(key, all_bets, len(mine), (blob.get("pairs") or None))
        light = ("<b class=\"pos\">\u25cf</b>" if state == "ok" else "<b class=\"neg\">\u25cf</b>")
        idle_days = _days_since(since)
        if live["n"]:
            since_note = f"{live['n']} settled"
        elif open_since:
            since_note = f"{open_since} running"
        elif priced_out:
            since_note = f"{priced_out} priced out"
        elif idle_days is not None:
            since_note = f"nothing in {idle_days}d"
        else:
            since_note = "none yet"
        cards.append(f"""<tr>
<td><b>{esc(name(key))}</b><div class="sm mut">{esc(sport_of(key))} · moved {esc(str(pair.get('by_hand') or since or '')[:10])}</div></td>
<td class="num">{whole['n']}<div class="sm mut">settled</div></td>
<td class="num"><span class="{tone(whole['roi_fee'], whole['n'])}">{pct(whole['roi_fee'])}</span><div class="sm mut">after fees</div></td>
<td class="num">{clv}<div class="sm mut">v the close</div></td>
<td class="num">{f"{live['won']}–{live['n'] - live['won']}" if live['n'] else '—'}<div class="sm mut">{esc(since_note)}</div></td>
<td class="num"><span class="{tone(live['roi_fee'], live['n'] >= EARLY_N)}">{pct(live['roi_fee'])}</span>{'<div class="sm mut">too early</div>' if 0 < live['n'] < EARLY_N else ''}</td>
<td class="num">{light}<div class="sm mut">{esc(why)}</div></td>
<td class="num"><span class="{reach_tone}">{reach}</span><div class="sm mut">reachable</div></td>
<td class="num"><b>{to_come}</b></td></tr>""")
    pairs_html = (f"""<div class="tbl"><table>
<tr><th rowspan="2">Pair</th><th colspan="3" class="grp">Sandbox record (US exchanges)</th>
<th colspan="2" class="grp">Since Production</th><th rowspan="2" class="num">Live</th><th rowspan="2" class="num">Reaches<br>the feed</th><th rowspan="2" class="num">Leads<br>to come</th></tr>
<tr><th class="num">Bets</th><th class="num">ROI</th><th class="num">CLV</th><th class="num">Record</th><th class="num">ROI</th></tr>
{''.join(cards)}</table></div>""" if cards else
        '<div class="note">Nothing is in Production. A pair arrives here by hand, on the record '
        'the Sandbox measured.</div>')

    # ---- what is coming up, a table per day ----
    by_day = {}
    for l in upcoming:
        # A bad kickoff still gets a row. Dropping it would hide the lead.
        by_day.setdefault(_chicago_day(l.get("kickoff")), []).append(l)
    days_html = ""
    known = sorted((day, ls) for day, ls in by_day.items() if day is not None)
    unknown = by_day.get(None)
    ordered = known + ([(None, unknown)] if unknown else [])
    for i, (day, ls) in enumerate(ordered):
        rows = "".join(
            f"""<tr><td class="mut">{esc(_ct_when(l.get('kickoff')))}</td><td>{esc(l.get('league') or sport_of(l['pair']))}</td>
<td>{esc(fmt.contest(l['match']))}</td><td><b>{esc(l['headline'])}</b></td><td class="mut">{esc(name(l['pair']))}</td>
<td class="num">{fmt.cents(l['price_at_log']) if l.get('price_at_log') else '—'}</td></tr>"""
            for l in ls)
        # Each day folds; the soonest one starts open, since that is what a visitor came for.
        label = PLACEHOLDER_DATE if day is None else _day_label(day, today)
        days_html += (f"""<details class="fold"{' open' if i == 0 else ''}><summary>{esc(label)}
<span class="mut sm">· {len(ls)} lead{'s' if len(ls) != 1 else ''}</span></summary>
<div class="tbl"><table><tr><th>Starts</th><th>Competition</th><th>Match</th><th>Lead</th><th>From</th>
<th class="num">Logged at</th></tr>{rows}</table></div></details>""")
    if unknown_up:
        rows = "".join(
            f"""<tr><td class="mut">{_KICKOFF_UNKNOWN}</td><td>{esc(l.get('league') or sport_of(l['pair']))}</td>
<td>{esc(fmt.contest(l['match']))}</td><td><b>{esc(l['headline'])}</b></td><td class="mut">{esc(name(l['pair']))}</td>
<td class="num">{fmt.cents(l['price_at_log']) if l.get('price_at_log') else '—'}</td></tr>"""
            for l in unknown_up)
        days_html += (f"""<details class="fold"><summary>{_KICKOFF_UNKNOWN}
<span class="mut sm">· {len(unknown_up)} lead{'s' if len(unknown_up) != 1 else ''}</span></summary>
<div class="tbl"><table><tr><th>Starts</th><th>Competition</th><th>Match</th><th>Lead</th><th>From</th>
<th class="num">Logged at</th></tr>{rows}</table></div></details>""")
    upcoming_html = days_html or ('<div class="note">Nothing is scheduled. A lead appears here when a '
                                  'Production pair logs a bet on a contest with a verified start time.</div>')

    # ---- how the recent ones landed ----
    # The 25 newest readable kickoffs, then every settled lead whose kickoff
    # cannot be read, so a missing kickoff cannot fall off the end of the list.
    recent = settled_known[:25] + settled_unknown
    rec_rows = "".join(
        f"""<tr><td class="mut">{esc(_ct_when(l.get('kickoff')) if _kickoff_known(l) else _KICKOFF_UNKNOWN)}</td><td>{esc(fmt.contest(l['match']))}</td>
<td>{esc(l['headline'])}</td><td class="mut">{esc(name(l['pair']))}</td>
<td class="num"><span class="{'pos' if l['status'] == 'hit' else ('mut' if l['status'] == 'price' else 'neg')}">{'landed' if l['status'] == 'hit' else ('paid' if l['status'] == 'price' else 'missed')}</span></td></tr>"""
        for l in recent)
    hits = sum(1 for l in landed if l["status"] == "hit")
    recent_html = (f"""<div class="tbl"><table><tr><th>Kickoff</th><th>Match</th><th>Lead</th><th>From</th>
<th class="num">Result</th></tr>{rec_rows}</table></div>""" if rec_rows else
                   '<div class="note">Nothing has settled since these pairs were moved.</div>')

    nxt = _ct_when(upcoming[0].get("kickoff")) if upcoming else "None scheduled"
    held = blob.get("unlisted_skipped", 0) + blob.get("unverified_kickoff_skipped", 0)
    # `style` used to be the Sandbox page's inline stylesheet. The shared site.css
    # replaced it. The argument stays so existing callers do not break.
    del style
    body = f"""<h1>Production</h1>
<p class="lede">The pairs moved here by hand, and the leads they publish.</p>

<div class="tiles">
<div class="tile"><b>{len(pairs)}</b><span>pairs in Production</span></div>
<div class="tile"><b>{len(upcoming)}</b><span>leads still to come</span></div>
<div class="tile"><b>{hits}/{len(landed)}</b><span>recent leads landed</span></div>
<div class="tile"><b class="when">{esc(nxt)}</b><span>{'next lead (CT)' if upcoming else 'next lead · none logged yet'}</span></div>
</div>

<section id="pairs">
<details class="fold sec" open><summary><h2>Pairs</h2> <span class="mut sm">· {len(pairs)}</span></summary>
<p class="sm mut">Each pair's Sandbox record on the US exchanges — the same numbers the Sandbox page shows —
and its record since it entered Production. Under {EARLY_N} settled bets an ROI is grey: one win at 0.46 reads
+117%, and means nothing yet. CLV is the closing price minus the price at logging: positive means its leads got
dearer after they were published.</p>
{pairs_html}</details>
</section>

<section id="coming-up">
<details class="fold sec" open><summary><h2>Coming up</h2> <span class="mut sm">· {_coming_up_count(len(upcoming), len(by_day))}</span></summary>
{upcoming_html}</details>
</section>

<section id="recent">
<details class="fold sec" open><summary><h2>Recently settled</h2> <span class="mut sm">· {hits} of {len(landed)} landed</span></summary>
{recent_html}</details>
</section>

<section id="held-back">
<details class="fold sec"><summary><h2>Held back</h2> <span class="mut sm">· {_held_count(held)}</span></summary>
{_held_note(held, blob)}</details>
</section>

<section id="how">
<details class="fold sec"><summary><h2>How a pair gets here</h2></summary>
<div class="note">Nothing promotes itself. Every source and rule starts in the <a href="./sandbox.html">Sandbox</a>,
logged before the start at the price available then and graded on the real result. A pair — one source in
one sport — is moved into Production by hand, on that record. It leaves the same way, or on its own when it
stops working: no new bet for {T.STALE_DAYS} days, behind the prices it logged at, or beaten by a blind rule
on the same contests. Every lead a Production pair logs is published to
<code>data/production_leads.json</code>.</div></details>
</section>

<footer>Read-only static export · rebuilt by GitHub Actions · research, not betting advice.</footer>
"""
    return site_chrome.document(
        "Edge Machine · Production",
        "The pairs moved into Production by hand, and their published leads.",
        "production",
        (("pairs", "Pairs"), ("coming-up", "Coming up"), ("recent", "Recently settled"),
         ("held-back", "Held back"), ("how", "How a pair gets here")),
        site_chrome.stamp(now_dt),
        body,
    )


def main(argv=None):
    """`python3 production.py --prune-feed` — drop leads from pairs no longer in Production.

    For a demotion made by hand: the feed stops naming the pair straight away, without
    waiting for a tracker run. Prints what it dropped, and says so when there was nothing.
    """
    import sys
    argv = sys.argv[1:] if argv is None else argv
    if "--prune-feed" not in argv:
        print(__doc__.strip().splitlines()[0])
        print("usage: python3 production.py --prune-feed")
        return 2
    st = T.load_stages()
    live = sorted(production_pairs(st))
    n = prune_feed(st=st)
    print(f"in Production: {', '.join(live) if live else 'nothing'}")
    print(f"dropped {n} lead(s) from pairs no longer in Production"
          if n else "feed already names only Production pairs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
