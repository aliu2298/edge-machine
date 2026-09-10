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

import json
import os
import sys
from datetime import datetime, timedelta, timezone

import sandbox_sources as S

LEDGER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "sandbox_ledger.json")

STAKE = 100.0        # flat, always. Any staking plan mixes bet-sizing skill into the
                     # source's score, and the question here is only "is it right?".
EDGE_MIN = 0.03      # 3pp. Below this a "disagreement" is just the tick size.
PRICE_FLOOR = 0.05   # Longshots are excluded from BETTING, not from scoring: at 0.02 a
PRICE_CEIL = 0.95    # single fluke pays 50x and one lucky pick would own the board.


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

    Returns {market_id: prob_a_oriented_to_that_row}.

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
    cands = []
    for i, row in enumerate(universe):
        for j, q in enumerate(quotes):
            score, flipped = S.pair_match(row["side_a"], row["side_b"],
                                          q["a"], q["b"], sport=row["sport"])
            if score <= 0:
                continue
            dist = 0
            if row["date"] and q.get("date"):
                try:
                    dist = abs((datetime.strptime(row["date"], "%Y-%m-%d")
                                - datetime.strptime(q["date"], "%Y-%m-%d")).days)
                except ValueError:
                    dist = 0
                if dist > day_slack:
                    continue
            cands.append((-score, dist, i, j, flipped))

    cands.sort()
    used_rows, used_quotes, out = set(), set(), {}
    for _neg, _dist, i, j, flipped in cands:
        if i in used_rows or j in used_quotes:
            continue
        used_rows.add(i)
        used_quotes.add(j)
        p = quotes[j]["prob_a"]
        out[universe[i]["market_id"]] = 1 - p if flipped else p
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
    """Fetch every source across every sport. Returns (universe_by_sport, coverage)."""
    universe, coverage = {}, {}
    for sport in S.SPORTS:
        stats = {}
        rows = S.fetch_polymarket(sport, stats=stats)
        universe[sport] = rows
        traded = stats.get("priced", 0)
        # Both numbers are kept because they answer different questions: how many
        # contests Polymarket LISTS, and how many of them anyone is actually pricing.
        # Table tennis lists hundreds and prices a couple of dozen.
        coverage.setdefault(sport, {})["polymarket"] = len(rows)
        coverage[sport]["polymarket_listed"] = stats.get("listed", len(rows))
        coverage[sport]["polymarket_priced"] = traded
        if verbose:
            print(f"  {S.SPORTS[sport]:<13} polymarket: {stats.get('listed', 0)} listed, "
                  f"{traded} priced, {len(rows)} taken")
    return universe, coverage


def publish(d, universe, coverage, verbose=True):
    """Log one quote per (source, market) for every source with an opinion."""
    seen = {q["id"] for q in d["quotes"]}
    added = 0

    for sport, rows in universe.items():
        if not rows:
            continue
        by_id = {r["market_id"]: r for r in rows}

        # The market itself. Priced at its own price, so its edge is 0 by construction
        # and it never bets — it is here for the Brier column, as the accuracy bar every
        # challenger has to clear.
        source_probs = {"polymarket": {r["market_id"]: r["price_a"] for r in rows}}

        for name, fetch in S.CHALLENGERS.items():
            if sport not in S.SOURCES[name]["sports"]:
                continue
            try:
                quotes = fetch(sport)
            except Exception as e:                      # never let one dead feed kill the run
                print(f"  ! {name}/{sport} fetch failed: {str(e)[:70]}")
                quotes = []
            matched = match_quotes(rows, quotes)
            source_probs[name] = matched
            coverage.setdefault(sport, {})[name] = len(matched)
            if verbose:
                print(f"  {S.SPORTS[sport]:<13} {name}: {len(quotes)} quotes -> "
                      f"{len(matched)} matched")

        for name, probs in source_probs.items():
            for mid, prob_a in probs.items():
                qid = f"{name}:{mid}"
                if qid in seen:
                    continue
                r = by_id[mid]
                # An untouched 50/50 book is not a forecast. It is already barred from
                # betting and from Brier, so logging it only grows the ledger — and it
                # is nearly half of every run, almost all of it table tennis.
                if r["untraded"] and name == "polymarket":
                    continue
                pick, edge, price = decide(prob_a, r["price_a"], r["price_b"])
                # An untraded 0.50/0.50 book is a placeholder, not a price. Scoring a
                # source against it would manufacture a 'edge' out of nothing.
                bet = bool(pick and edge >= EDGE_MIN and not r["untraded"]
                           and PRICE_FLOOR <= price <= PRICE_CEIL)
                d["quotes"].append(dict(
                    id=qid, source=name, sport=sport, market_id=mid,
                    label=r["label"], side_a=r["side_a"], side_b=r["side_b"],
                    url=r["url"], date=r["date"], start=r["start"],
                    logged=now_iso(),
                    prob_a=round(prob_a, 4),
                    price_a=round(r["price_a"], 4), price_b=round(r["price_b"], 4),
                    pick=pick, edge=round(edge, 4),
                    price=round(price, 4) if pick else None,
                    bet=bet, stake=STAKE if bet else 0.0, untraded=r["untraded"],
                    status="open", pnl=0.0, result=None, settled=None,
                ))
                seen.add(qid)
                added += 1

    d["coverage"] = coverage
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
            resolved[mid] = S.resolve_polymarket(mid)
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
            q["status"] = "won"
            q["pnl"] = round(q["stake"] * (1.0 / q["price"] - 1.0), 2)
        else:
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
        briered = [q for q in rows if q["status"] in ("won", "lost", "graded")
                   and q.get("result") in ("a", "b") and not q.get("untraded")]
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
            avg_edge=(sum(q["edge"] for q in bets) / len(bets)) if bets else None,
        )
    return out


RETAIN_DAYS = 45


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
        if q.get("result") in ("a", "b") and not q.get("untraded"):
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
    print(" collecting…")
    universe, coverage = collect()
    print(" publishing…")
    publish(d, universe, coverage)
    print(" grading…")
    grade(d)
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
