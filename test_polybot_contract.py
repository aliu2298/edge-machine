#!/usr/bin/env python3
"""Contract for the two lead files read raw from main.

data/production_leads.json and data/streak_leads.json must stay at those paths
and keep parsing. The production feed must keep the shape a reader already
expects: a `leads` dict keyed by lead id, a parseable `updated_at`, and on every
lead the fields kickoff, price_at_log, pair, status and bet.

A model lane is whatever production.lead_from_quote decides, the gate that
attaches model_prob. This file calls that function. It does not restate the
condition. No network, and the builder check pins build_feed's now= so nothing
here reads the wall clock.
"""
import copy
import datetime
import json
import os
import sys
import tempfile

import production
import sandbox_track as T
import streaks_track

FAILS = []
ROOT = os.path.dirname(os.path.abspath(__file__))
PRODUCTION_REL = os.path.join("data", "production_leads.json")
STREAKS_REL = os.path.join("data", "streak_leads.json")
PRODUCTION = os.path.join(ROOT, PRODUCTION_REL)
STREAKS = os.path.join(ROOT, STREAKS_REL)
# Passed to lead_from_quote only so a pending lead's last_seen is stable.
# The model-lane gate does not read it.
PREDICATE_BUILT = "2000-01-01T00:00:00+00:00"
# Fixed clock for the builder. build_feed writes this into updated_at.
FIXED_NOW = datetime.datetime(2026, 10, 1, 12, 0, tzinfo=datetime.timezone.utc)
LEAD_KEYS = ("kickoff", "price_at_log", "pair", "status", "bet")


def ok(cond, why):
    print(f"  {'ok  ' if cond else 'FAIL'} {why}")
    if not cond:
        FAILS.append(why)


def parse_iso(value):
    """A parseable ISO-8601 timestamp, or ValueError."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"not an ISO-8601 string: {value!r}")
    return datetime.datetime.fromisoformat(value)


def unit_interval(value):
    """A real number strictly between 0 and 1. Booleans are not numbers here."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    return 0 < value < 1


def on_model_lane(quote, pair_key):
    """production.py's own model-lane decision, via lead_from_quote."""
    lead = production.lead_from_quote(quote, pair_key, PREDICATE_BUILT)
    return "model_prob" in lead


def load_json(path):
    with open(path) as f:
        return json.load(f)


def quotes_for_leads(leads):
    """Sandbox quotes for these leads, so the model-lane gate can be called.

    The published lead does not carry prob_a or price_draw. Those stay on the
    quote the builder read. Ledger first, archive only for ids still missing.
    """
    want = set()
    for lead in leads.values():
        if isinstance(lead, dict) and lead.get("sandbox_quote"):
            want.add(lead["sandbox_quote"])
    found = {}
    if not want:
        return found
    with open(T.LEDGER) as f:
        ledger = json.load(f)
    for quote in ledger.get("quotes") or []:
        if isinstance(quote, dict) and quote.get("id") in want:
            found[quote["id"]] = quote
    if len(found) < len(want):
        for quote in T.load_archive():
            if isinstance(quote, dict) and quote.get("id") in want and quote["id"] not in found:
                found[quote["id"]] = quote
    return found


def feed_problems(blob, quotes):
    """Contract violations in one production feed. Empty means it holds.

    `quotes` maps a sandbox quote id to the quote lead_from_quote would have
    seen. Model lanes are decided by calling that function, then requiring
    model_prob on the lead it marks.
    """
    problems = []
    if not isinstance(blob, dict):
        return ["production feed is not a JSON object"]
    if "updated_at" not in blob:
        problems.append("missing updated_at")
    else:
        try:
            parse_iso(blob["updated_at"])
        except (TypeError, ValueError):
            problems.append(f"updated_at is not ISO-8601: {blob.get('updated_at')!r}")
    leads = blob.get("leads")
    if not isinstance(leads, dict):
        problems.append("leads is not a dict keyed by lead id")
        return problems
    for key, lead in leads.items():
        where = f"lead {key!r}"
        if not isinstance(key, str) or not key:
            problems.append(f"leads key is not a lead id: {key!r}")
        if not isinstance(lead, dict):
            problems.append(f"{where} is not an object")
            continue
        if lead.get("id") != key:
            problems.append(f"{where} is not keyed by its lead id")
        missing = [name for name in LEAD_KEYS if name not in lead]
        if missing:
            problems.append(f"{where} missing {', '.join(missing)}")
        if "kickoff" in lead:
            try:
                parse_iso(lead["kickoff"])
            except (TypeError, ValueError):
                problems.append(f"{where} kickoff is not ISO-8601: {lead.get('kickoff')!r}")
        if "price_at_log" in lead and not unit_interval(lead["price_at_log"]):
            problems.append(
                f"{where} price_at_log is not a number in (0, 1): {lead.get('price_at_log')!r}")
        pair = lead.get("pair")
        if "pair" in lead and not (isinstance(pair, str) and pair):
            problems.append(f"{where} pair is not a non-empty string: {pair!r}")
        if "bet" in lead and not isinstance(lead["bet"], dict):
            problems.append(
                f"{where} bet is {type(lead['bet']).__name__}, not the dict the builder writes")
        if "pair" not in lead or not isinstance(lead.get("pair"), str):
            continue
        quote_id = lead.get("sandbox_quote")
        quote = quotes.get(quote_id) if quote_id is not None else None
        if not isinstance(quote, dict):
            problems.append(f"{where} has no quote, so its lane cannot be decided")
            continue
        try:
            model = on_model_lane(quote, lead["pair"])
        except (KeyError, TypeError, ValueError, OverflowError, OSError) as exc:
            problems.append(f"{where} model-lane predicate raised {type(exc).__name__}: {exc}")
            continue
        if not model:
            continue
        if "model_prob" not in lead:
            problems.append(f"{where} is a model-lane lead missing model_prob")
        elif not unit_interval(lead["model_prob"]):
            problems.append(
                f"{where} model_prob is not a number in (0, 1): {lead.get('model_prob')!r}")
    return problems


def lane_counts(blob, quotes):
    """(leads, model lanes, pick lanes) using lead_from_quote's decision."""
    leads = blob.get("leads") or {}
    model = pick = 0
    for key, lead in leads.items():
        if not isinstance(lead, dict):
            continue
        quote = quotes.get(lead.get("sandbox_quote"))
        if not isinstance(quote, dict) or not isinstance(lead.get("pair"), str):
            continue
        if on_model_lane(quote, lead["pair"]):
            model += 1
        else:
            pick += 1
    return len(leads), model, pick


def _quote(source, sport, market, pick, price, start, **extra):
    quote = dict(
        id=f"{source}:{market}", source=source, sport=sport, bet=True,
        venue="polymarket_us", market_id=market, side_a="Home Side", side_b="Away Side",
        pick=pick, price=price, status="open", start=start,
        logged="2026-10-01T00:00:00+00:00", prob_a=None, edge=None, price_draw=None,
    )
    quote.update(extra)
    return quote


def written_fixture():
    """Run the production-feed writer on a two-lead ledger, at a fixed now=.

    The ledger is built here. Nothing in this path opens data/.
    """
    # MMA favourite-band left the board on 2026-10-04. Oddspedia cricket is a
    # pick lane that stays, so the writer still has one of each kind to emit.
    pick = _quote("oddspedia", "cricket", "aec-fixture-pick", "b", 0.80,
                  "2026-10-03T22:00:00+00:00")
    # NFL stays on the board, so this is still a model lane the writer emits.
    # MLB is the same source with the lane removed: it must not reach the feed.
    model = _quote("espn_fpi", "nfl", "aec-fixture-model", "a", 0.55,
                   "2026-10-03T23:00:00+00:00", prob_a=0.62, edge=0.07)
    removed = _quote("espn_fpi", "mlb", "aec-fixture-removed", "a", 0.55,
                     "2026-10-03T23:30:00+00:00", prob_a=0.62, edge=0.07)
    stages = {"pairs": {
        "oddspedia|cricket": {"stage": "production", "ready_at": "2026-09-01T00:00:00+00:00",
                              "by_hand": "2026-09-01"},
        "espn_fpi|nfl": {"stage": "production", "ready_at": "2026-09-01T00:00:00+00:00",
                         "by_hand": "2026-09-01"},
        "espn_fpi|mlb": {"stage": "production", "ready_at": "2026-09-01T00:00:00+00:00",
                         "by_hand": "2026-09-01"},
    }}
    import builtins
    data_dir = os.path.join(ROOT, "data")
    saved_open = builtins.open

    def refuse_data(path, *args, **kwargs):
        target = path if isinstance(path, (str, os.PathLike)) else None
        if target is not None:
            absolute = os.path.abspath(target)
            if absolute == data_dir or absolute.startswith(data_dir + os.sep):
                raise AssertionError(f"builder touched {absolute}")
        return saved_open(path, *args, **kwargs)

    builtins.open = refuse_data
    try:
        blob = production.build_feed({"quotes": [pick, model, removed]}, stages, now=FIXED_NOW)
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "production_leads.json")
            production.save_feed(blob, path)
            written = load_json(path)
    finally:
        builtins.open = saved_open
    return written, {pick["id"]: pick, model["id"]: model}


def test_files_exist_and_parse():
    print("\nthe two lead files are at their paths and parse")
    ok(os.path.isfile(PRODUCTION), f"{PRODUCTION_REL} exists")
    ok(os.path.isfile(STREAKS), f"{STREAKS_REL} exists")
    ok(production.FEED == PRODUCTION, "production.FEED is data/production_leads.json")
    ok(streaks_track.LEDGER == STREAKS, "streaks_track.LEDGER is data/streak_leads.json")
    try:
        feed = load_json(PRODUCTION)
        ok(True, "production_leads.json parses as JSON")
    except (OSError, ValueError) as exc:
        feed = None
        ok(False, f"production_leads.json parses as JSON ({exc})")
    try:
        load_json(STREAKS)
        ok(True, "streak_leads.json parses as JSON")
    except (OSError, ValueError) as exc:
        ok(False, f"streak_leads.json parses as JSON ({exc})")
    if not isinstance(feed, dict):
        ok(False, "production_leads.json is a JSON object")
        return
    quotes = quotes_for_leads(feed.get("leads") or {})
    problems = feed_problems(feed, quotes)
    if problems:
        for problem in problems:
            ok(False, f"published feed: {problem}")
    else:
        ok(True, "published production_leads.json satisfies the contract")
    n, model, pick = lane_counts(feed, quotes)
    print(f"  published leads: {n}, model lanes: {model}, pick lanes: {pick}")


def test_builder_writes_both_lanes():
    print("\nthe writer emits one model-lane lead and one pick-lane lead")
    written, quotes = written_fixture()
    ok(written["updated_at"] == "2026-10-01T12:00:00+00:00",
       "updated_at is the fixed now=, not the wall clock")
    problems = feed_problems(written, quotes)
    if problems:
        for problem in problems:
            ok(False, f"builder feed: {problem}")
    else:
        ok(True, "the written feed satisfies the contract")
    n, model, pick = lane_counts(written, quotes)
    ok(model >= 1, f"the fixture writes a model-lane lead (got {model})")
    ok(pick >= 1, f"the fixture writes a pick-lane lead (got {pick})")
    model_leads = [lead for lead in written["leads"].values()
                   if on_model_lane(quotes[lead["sandbox_quote"]], lead["pair"])]
    ok(all("model_prob" in lead and unit_interval(lead["model_prob"]) for lead in model_leads),
       "each model-lane lead has model_prob in (0, 1)")
    ok(all(lead.get("pair") != "espn_fpi|mlb" and lead.get("sport") != "mlb"
           for lead in written["leads"].values()),
       "a removed lane does not reach the feed")
    ok("espn_fpi|mlb" not in written.get("pairs", {}),
       "a removed Production pair is left out of the feed")
    return written, quotes


def test_breaks_fail(written, quotes):
    print("\na broken contract fails")
    no_stamp = copy.deepcopy(written)
    del no_stamp["updated_at"]
    stamp_problems = feed_problems(no_stamp, quotes)
    ok(any("updated_at" in problem for problem in stamp_problems),
       "dropping updated_at fails the contract")

    no_price = copy.deepcopy(written)
    price_lead = next(iter(no_price["leads"].values()))
    del price_lead["price_at_log"]
    price_problems = feed_problems(no_price, quotes)
    ok(any("price_at_log" in problem for problem in price_problems),
       "dropping price_at_log fails the contract")

    no_prob = copy.deepcopy(written)
    model_key = next(key for key, lead in no_prob["leads"].items()
                     if on_model_lane(quotes[lead["sandbox_quote"]], lead["pair"]))
    del no_prob["leads"][model_key]["model_prob"]
    prob_problems = feed_problems(no_prob, quotes)
    ok(any("model_prob" in problem for problem in prob_problems),
       "dropping model_prob from a model-lane lead fails the contract")
    return stamp_problems, price_problems, prob_problems


# build_feed on the fixture above, at FIXED_NOW, as main 0dfa4d35 writes it,
# with the four sandbox-record fields removed. Those four may change. Leads
# (every lead, every field), updated_at, and every other key may not.
_MAIN_FEED_ASIDE_FROM_SANDBOX = json.loads(r"""
{
  "board_built_at": "2026-10-01T12:00:00+00:00",
  "leads": {
    "2026-10-03|Home Side|Away Side|Away Side to win · Oddspedia community tips": {
      "away": "Away Side",
      "bet": {"kind": "match_result", "side": "away"},
      "date": "2026-10-03",
      "edge_at_log": null,
      "first_seen": "2026-10-01",
      "headline": "Away Side to win",
      "home": "Home Side",
      "id": "2026-10-03|Home Side|Away Side|Away Side to win · Oddspedia community tips",
      "kickoff": "2026-10-03T22:00Z",
      "lane": "production",
      "last_seen": "2026-10-01",
      "last_seen_at": "2026-10-01T12:00:00+00:00",
      "league": "Cricket",
      "match": "Home Side v Away Side",
      "pair": "oddspedia|cricket",
      "price_at_log": 0.8,
      "route": {
        "market": "aec-fixture-pick",
        "outcome": "Away Side",
        "outcome_side": "no",
        "venue": "polymarket_us"
      },
      "sandbox_quote": "oddspedia:aec-fixture-pick",
      "source": "oddspedia",
      "sport": "cricket",
      "status": "pending"
    },
    "2026-10-03|Home Side|Away Side|Home Side to win · ESPN FPI / Matchup Predictor": {
      "away": "Away Side",
      "bet": {"kind": "match_result", "side": "home"},
      "date": "2026-10-03",
      "edge_at_log": 0.07,
      "first_seen": "2026-10-01",
      "headline": "Home Side to win",
      "home": "Home Side",
      "id": "2026-10-03|Home Side|Away Side|Home Side to win · ESPN FPI / Matchup Predictor",
      "kickoff": "2026-10-03T23:00Z",
      "lane": "production",
      "last_seen": "2026-10-01",
      "last_seen_at": "2026-10-01T12:00:00+00:00",
      "league": "NFL",
      "match": "Home Side v Away Side",
      "model_prob": 0.62,
      "pair": "espn_fpi|nfl",
      "price_at_log": 0.55,
      "route": {
        "market": "aec-fixture-model",
        "outcome": "Home Side",
        "outcome_side": "yes",
        "venue": "polymarket_us"
      },
      "sandbox_quote": "espn_fpi:aec-fixture-model",
      "source": "espn_fpi",
      "sport": "nfl",
      "status": "pending"
    }
  },
  "pairs": {
    "espn_fpi|nfl": {
      "by_hand": "2026-09-01",
      "entered_at": "2026-09-01T00:00:00+00:00",
      "promoted_at": null,
      "ready_at": "2026-09-01T00:00:00+00:00",
      "route": "moved by hand on 2026-09-01"
    },
    "oddspedia|cricket": {
      "by_hand": "2026-09-01",
      "entered_at": "2026-09-01T00:00:00+00:00",
      "promoted_at": null,
      "ready_at": "2026-09-01T00:00:00+00:00",
      "route": "moved by hand on 2026-09-01"
    }
  },
  "stage": "production",
  "unlisted_skipped": 0,
  "unverified_kickoff_skipped": 0,
  "updated_at": "2026-10-01T12:00:00+00:00"
}
""")
SANDBOX_RECORD_FIELDS = ("sandbox_n", "sandbox_roi", "sandbox_roi_fee", "sandbox_clv")


def _aside_from_sandbox(blob):
    """A copy of a feed with the four sandbox-record numbers removed."""
    out = copy.deepcopy(blob)
    for pair in (out.get("pairs") or {}).values():
        if isinstance(pair, dict):
            for field in SANDBOX_RECORD_FIELDS:
                pair.pop(field, None)
    return out


def _canonical(blob):
    return json.dumps(blob, sort_keys=True, separators=(",", ":"))


def test_feed_matches_main_aside_from_sandbox_record():
    print("\nbuild_feed matches main except the sandbox record fields")
    written, _quotes = written_fixture()
    got = _canonical(_aside_from_sandbox(written))
    want = _canonical(_MAIN_FEED_ASIDE_FROM_SANDBOX)
    ok(got == want,
       "leads (every lead, every field), updated_at and every other key are "
       "byte-identical to main; only pairs.*.sandbox_n / sandbox_roi / "
       "sandbox_roi_fee / sandbox_clv may differ")
    ok(written["updated_at"] == FIXED_NOW.replace(microsecond=0).isoformat(),
       "updated_at is still the fixed now=")
    ok(set(written) == set(_MAIN_FEED_ASIDE_FROM_SANDBOX),
       "the top-level keys are unchanged")
    for key, pair in written.get("pairs", {}).items():
        missing = [name for name in SANDBOX_RECORD_FIELDS if name not in pair]
        ok(not missing, f"{key} still carries the sandbox record fields")


def main():
    test_files_exist_and_parse()
    written, quotes = test_builder_writes_both_lanes()
    test_breaks_fail(written, quotes)
    test_feed_matches_main_aside_from_sandbox_record()
    if FAILS:
        print(f"\n{len(FAILS)} FAILED")
        for item in FAILS:
            print("   -", item)
        sys.exit(1)
    print("\nall passed")


if __name__ == "__main__":
    main()
