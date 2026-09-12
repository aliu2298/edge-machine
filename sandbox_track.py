"""The Sandbox Tracker ledger: log what each source said, then make it pay for it.

One run does three things, in this order and for a reason:

  collect -> publish   every source's probability on every live matchup, logged BEFORE
                       the event starts and stamped with the price that existed at that
                       moment. This is the whole discipline of the thing. A prediction
                       recorded after kickoff, or scored against a price nobody could
                       still get, is not evidence of anything.
  grade                every logged quote whose market has since resolved.
  score                per-source hit rate, ROI and Brier over the accumulated ledger.

The ledger is append-only and idempotent: a market is quoted ONCE per source, the first
time it is seen. Re-quoting as the price drifts would let a source keep the version of
its opinion that happened to age well, which is the single easiest way to fake an edge.
"""

import difflib
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone

import sandbox_sources as S

LEDGER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "sandbox_ledger.json")

STAKE = 100.0        # flat, always. Any staking plan mixes bet-sizing skill into the
                     # source's score, and the question here is only "is it right?".
EDGE_MIN = 0.03      # 3pp. Below this a "disagreement" is just the tick size.
PRICE_FLOOR = 0.05   # Longshots are excluded from BETTING, not from scoring: at 0.02 a
PRICE_CEIL = 0.95    # single fluke pays 50x and one lucky pick would own the board.

# Below this many settled bets a record is not read at all (the page greys it).
READ_FLOOR = 30

# THE STAMP OF APPROVAL — pre-registered 2026-09-12, before any source had met it. Every
# criterion must hold, for every betting source alike (tipsters, models, books, markets),
# and it is re-judged on every run, so a stamp can be lost as well as won.
#
#   sample     at least MIN_BETS settled bets, across at least MIN_WEEKS different weeks.
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
APPROVAL = dict(min_bets=50, min_weeks=4, z_min=2.0)


def now_iso():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load():
    if os.path.exists(LEDGER):
        with open(LEDGER) as f:
            d = json.load(f)
        d.setdefault("quotes", [])
        d.setdefault("meta", {})
        d.setdefault("coverage", {})
        return d
    return {"meta": {"created": now_iso()}, "quotes": [], "coverage": {}}


def save(d):
    d["meta"]["updated"] = now_iso()
    d["meta"]["runs"] = d["meta"].get("runs", 0) + 1
    os.makedirs(os.path.dirname(LEDGER), exist_ok=True)
    with open(LEDGER, "w") as f:
        json.dump(d, f, indent=1, sort_keys=True)


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

def collect(verbose=True):
    """Fetch the universe for every sport. Returns (universe_by_sport, coverage).

    Polymarket is the venue wherever it lists a contest. Kalshi fills in what it does
    not: all of soccer — Polymarket lists one or two soccer MATCHES a day, in leagues no
    tipster covers — and any individual fight, match or game Polymarket is missing in the
    other sports. A contest listed on both stays on Polymarket, so nothing is priced
    twice and no bet can be booked against two different prices for one game.
    """
    universe, coverage = {}, {}
    for sport in S.SPORTS:
        t0 = time.time()
        # Each venue, for each sport, fails on its own. A dropped connection fetching NFL
        # used to take the whole run down with it — no grading, nothing saved — when the
        # right outcome is one empty sport and everything else carrying on.
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
            pm = [] if sport == "soccer" else S.fetch_polymarket(sport, stats=stats)
        except Exception as e:
            print(f"  ! polymarket/{sport} failed: {type(e).__name__}: {str(e)[:70]}")
            pm = []
        kstats = {}
        try:
            ks = S.fetch_kalshi_venue(sport, stats=kstats)
        except Exception as e:
            print(f"  ! kalshi/{sport} failed: {type(e).__name__}: {str(e)[:70]}")
            ks = []
        extra = [k for k in ks if not any(_same_contest(k, p) for p in pm)]
        universe[sport] = pm + extra
        cov = coverage.setdefault(sport, {})
        cov["polymarket"] = len(pm)
        cov["polymarket_listed"] = stats.get("listed", len(pm))
        cov["polymarket_priced"] = stats.get("priced", 0)
        cov["kalshi_venue"] = len(extra)
        if verbose:
            print(f"  {S.SPORTS[sport]:<13} polymarket: {len(pm)} taken | kalshi: "
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


def publish(d, universe, coverage, verbose=True):
    """Log one quote per (source, market) for every source with an opinion."""
    seen = {q["id"] for q in d["quotes"]}
    added = 0
    # Adapters that pay per page (SportsGambler) read this to skip fixtures no venue
    # prices — a page that can never be scored is not worth a polite second of waiting.
    S.UNIVERSE = universe
    S.FEED_STATUS.clear()

    for sport, rows in universe.items():
        if not rows:
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
        source_probs = {"polymarket": {r["market_id"]: ("prob", r.get("mid_a", r["price_a"]))
                                       for r in rows
                                       if r.get("venue", "polymarket") == "polymarket"}}

        for name, fetch in S.CHALLENGERS.items():
            if sport not in S.SOURCES[name]["sports"]:
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
            matched = match_quotes(pool, quotes)
            source_probs[name] = matched
            coverage.setdefault(sport, {})[name] = len(matched)
            if verbose:
                print(f"  {S.SPORTS[sport]:<13} {name}: {len(quotes)} quotes -> "
                      f"{len(matched)} matched ({time.time() - t0:.0f}s)")

        for name, probs in source_probs.items():
            for mid, opinion in probs.items():
                qid = f"{name}:{mid}"
                if qid in seen:
                    continue
                r = by_id[mid]
                # Strictly before the start, for every source and every venue, checked at
                # the moment of logging. The venue feeds keep a contest for five minutes
                # past its start to absorb clock skew, and that window let a tip on Al
                # Wahda v Sharjah be logged 74 seconds after kickoff — it won, +$178. A
                # quote logged once play has begun is not a prediction.
                if _started(r, datetime.now(timezone.utc)):
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
                bet = bool(pick and has_edge and not r["untraded"] and tradeable
                           and price is not None and PRICE_FLOOR <= price <= PRICE_CEIL)
                d["quotes"].append(dict(
                    id=qid, source=name, sport=sport, market_id=mid,
                    label=r["label"], side_a=r["side_a"], side_b=r["side_b"],
                    url=r["url"], date=r["date"], start=r["start"],
                    logged=now_iso(),
                    prob_a=round(prob_a, 4) if prob_a is not None else None,
                    price_a=round(r["price_a"], 4), price_b=round(r["price_b"], 4),
                    price_draw=(round(r["price_draw"], 4)
                                if r.get("price_draw") is not None else None),
                    pick=pick, edge=round(edge, 4) if edge is not None else None,
                    price=round(price, 4) if pick and price is not None else None,
                    bet=bet, stake=STAKE if bet else 0.0, untraded=r["untraded"],
                    venue=r.get("venue", "polymarket"),
                    spread=r.get("spread"), liquidity=r.get("liquidity"),
                    status="open", pnl=0.0, result=None, settled=None,
                ))
                seen.add(qid)
                added += 1

    d["coverage"] = coverage
    d["feed_status"] = dict(S.FEED_STATUS)
    if S.ODDS_USAGE:
        d["meta"]["odds_api"] = dict(S.ODDS_USAGE, at=now_iso())
    if verbose:
        print(f"  logged {added} new quotes")
    return added


# ---------------------------------------------------------------------------
# Grade
# ---------------------------------------------------------------------------

def grade(d, verbose=True):
    """Settle every open quote whose market has resolved."""
    now = datetime.now(timezone.utc)
    resolved, settled = {}, 0

    for q in d["quotes"]:
        if q["status"] != "open":
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
            venue = q.get("venue")
            resolved[mid] = (S.resolve_kalshi(mid) if venue == "kalshi"
                             else S.resolve_kalshi_market(mid) if venue == "kalshi_binary"
                             else S.resolve_polymarket(mid))
        res = resolved[mid]
        if res is None:
            continue

        q["result"] = res
        q["settled"] = now_iso()
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
        settled += 1

    if verbose:
        print(f"  settled {settled} quotes")
    return settled


# ---------------------------------------------------------------------------
# Score
# ---------------------------------------------------------------------------

def score(d, sport=None):
    """Per-source table over the ledger. ROI from bets, Brier from every graded quote."""
    out = {}
    for name, meta in S.SOURCES.items():
        rows = [q for q in d["quotes"] if q["source"] == name
                and (sport is None or q["sport"] == sport)]
        bets = [q for q in rows if q["bet"]]
        done = [q for q in bets if q["status"] in ("won", "lost")]
        won = [q for q in done if q["status"] == "won"]
        staked = sum(q["stake"] for q in done)
        pnl = sum(q["pnl"] for q in done)

        # An untraded 0.50/0.50 book is excluded from Brier as well as from betting.
        # Table tennis is overwhelmingly made of these, and scoring a flat 0.5 against a
        # coin flip would bury every real forecast under 0.25s that mean nothing.
        # Brier needs a probability. A tipster that only names a side has nothing to
        # calibrate, so it gets no Brier column rather than a fabricated 0/1 stand-in.
        briered = [q for q in rows if q["status"] in ("won", "lost", "graded")
                   and q.get("result") in ("a", "b") and not q.get("untraded")
                   and q.get("prob_a") is not None]
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
                n_quotes += r["quotes"]; n_bets += r["bets"]
                n_done += r["settled"]; n_won += r["won"]
                staked += r["staked"]; pnl += r["pnl"]
                brier_sum += r["brier_sum"]; brier_n += r["brier_n"]

        out[name] = dict(
            label=meta["label"], kind=meta["kind"], connected=meta["connected"],
            site=meta["site"], note=meta["note"],
            quotes=n_quotes, open=len([q for q in rows if q["status"] == "open"]),
            bets=n_bets, settled=n_done, won=n_won,
            hit=(n_won / n_done) if n_done else None,
            staked=staked, pnl=pnl,
            roi=(pnl / staked) if staked else None,
            brier=(brier_sum / brier_n) if brier_n else None, brier_n=brier_n,
            avg_edge=(sum(q["edge"] for q in bets if q.get("edge") is not None)
                      / max(1, sum(1 for q in bets if q.get("edge") is not None))
                      if any(q.get("edge") is not None for q in bets) else None),
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
    if price is None or not (PRICE_FLOOR <= price <= PRICE_CEIL):
        return None
    return round(STAKE * (1.0 / price - 1.0), 2) if q["result"] == side else -STAKE


def baselines(d, sport=None):
    """The two blind strategies across every contest the ledger holds a result for.

    Each contest counted ONCE, priced at its earliest quote — the first moment any source
    looked at it, before the start. Void and late quotes are ignored.
    Returns {kind: dict(n, won, pnl, roi, expected)}.
    """
    first = {}
    for q in d["quotes"]:
        if q.get("status") == "void" or (sport and q["sport"] != sport):
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


def assess(d, name, sport=None):
    """Judge one source (optionally in one sport) against APPROVAL.

    Returns dict(status, criteria=[(key, label, passed, detail)], and the metrics).
    status: "unproven" under READ_FLOOR settled bets; "approved" when every criterion
    holds; "failing" when it is readable and not ahead of the price at all; else "watch".
    """
    bets = sorted((q for q in d["quotes"] if q["source"] == name and q.get("bet")
                   and q["status"] in ("won", "lost")
                   and (sport is None or q["sport"] == sport)),
                  key=lambda q: q["start"])
    n = len(bets)
    won = sum(1 for q in bets if q["status"] == "won")
    pnl = sum(q["pnl"] for q in bets)
    roi = pnl / (n * STAKE) if n else None
    expected = sum(q["price"] for q in bets)
    var = sum(q["price"] * (1 - q["price"]) for q in bets)
    z = (won - expected) / var ** 0.5 if var > 0 else 0.0
    weeks = len({datetime.fromisoformat(q["start"]).isocalendar()[:2] for q in bets})

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
    beats_all = bool(blind) and all(own > base for _k, own, base in blind)
    hardest = max(blind, key=lambda t: t[2] - t[1]) if blind else None
    base_roi = hardest[2] if hardest else None
    own_roi = hardest[1] if hardest else None

    top = max((q["pnl"] for q in bets if q["status"] == "won"), default=0.0)
    roi_wo_top = ((pnl - top) / ((n - 1) * STAKE)) if n > 1 else None
    half = n // 2
    roi_h1 = (sum(q["pnl"] for q in bets[:half]) / (half * STAKE)) if half else None
    roi_h2 = (sum(q["pnl"] for q in bets[half:]) / ((n - half) * STAKE)) if n - half else None

    A = APPROVAL
    criteria = [
        ("sample", f"{A['min_bets']}+ settled bets over {A['min_weeks']}+ weeks",
         n >= A["min_bets"] and weeks >= A["min_weeks"], f"{n} bets, {weeks} week{'s' if weeks != 1 else ''}"),
        ("price", f"wins beat the price by z ≥ {A['z_min']:g}",
         n > 0 and z >= A["z_min"], f"{won} won v {expected:.1f} priced, z {z:+.2f}"),
        ("baseline", "beats every blind rule on the same contests",
         beats_all,
         (f"{own_roi*100:+.1f}% v {base_roi*100:+.1f}% back the {hardest[0]}"
          if hardest else "no comparable contests")),
        ("one_hit", "still profitable without its biggest win",
         roi_wo_top is not None and roi_wo_top > 0,
         f"{roi_wo_top*100:+.1f}% without it" if roi_wo_top is not None else "—"),
        ("halves", "profitable in both halves of its record",
         bool(roi_h1 and roi_h2 and roi_h1 > 0 and roi_h2 > 0),
         (f"{roi_h1*100:+.1f}% then {roi_h2*100:+.1f}%" if roi_h1 is not None
          and roi_h2 is not None else "—")),
    ]
    if n < READ_FLOOR:
        status = "unproven"
    elif all(c[2] for c in criteria):
        status = "approved"
    elif (roi or 0) <= 0 or z <= 0:
        status = "failing"
    else:
        status = "watch"
    return dict(status=status, criteria=criteria, n=n, won=won, roi=roi, pnl=pnl,
                z=z, weeks=weeks, base_roi=base_roi, own_roi=own_roi)


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
        if q.get("status") == "void":
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


def prune(d, retain_days=RETAIN_DAYS, verbose=True):
    """Fold long-settled quotes into per-source totals and drop the rows.

    The ledger is rewritten and committed four times a day, so every row kept is a row
    re-stored in git forever. Left alone this grows by roughly a megabyte a week. Old
    rows are therefore rolled up rather than deleted: the lifetime record survives in
    `retired`, only the per-contest detail is discarded, and nothing OPEN is ever touched.
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(days=retain_days)).isoformat()
    keep, rolled = [], 0
    ret = d.setdefault("retired", {})

    for q in d["quotes"]:
        if q["status"] == "open" or not q.get("settled") or q["settled"] >= cutoff:
            keep.append(q)
            continue
        r = ret.setdefault(q["source"], dict(quotes=0, bets=0, settled=0, won=0,
                                             staked=0.0, pnl=0.0,
                                             brier_sum=0.0, brier_n=0))
        r["quotes"] += 1
        if q["bet"]:
            r["bets"] += 1
        if q["status"] in ("won", "lost"):
            r["settled"] += 1
            r["won"] += 1 if q["status"] == "won" else 0
            r["staked"] += q["stake"]
            r["pnl"] += q["pnl"]
        if (q.get("result") in ("a", "b") and not q.get("untraded")
                and q.get("prob_a") is not None):
            r["brier_sum"] += (q["prob_a"] - (1.0 if q["result"] == "a" else 0.0)) ** 2
            r["brier_n"] += 1
        rolled += 1

    d["quotes"] = keep
    if verbose and rolled:
        print(f"  rolled up {rolled} settled quotes older than {retain_days}d")
    return rolled


def main():
    print("Sandbox Tracker")
    d = load()
    retire_pre_gate(d)
    retire_late(d)
    # Stage timings are printed so a slow run in CI names its own culprit. The first
    # run with soccer on Kalshi took 14.6 minutes against 3 before it, with only 25s of
    # CPU — all of it waiting on the network, and no log line said where.
    t0 = time.time()
    print(" collecting…")
    universe, coverage = collect()
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
    save(d)

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
    return 0


if __name__ == "__main__":
    sys.exit(main())
