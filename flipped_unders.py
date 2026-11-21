"""Flipped Unders (2026-11-21): a Sandbox PAPER lane, `flipped_unders`. Paper only: no Production, no live order.

Olu (Nov 21): whenever soccer rule C5 (Saudi Pro League u2.5), C6 (Ligue 1 u2.5), C7 (Super Lig u2.5) or B4 (Scottish Premiership u3.5)
selects a match by its label filter, at the same entry time (20 to 90 minutes before kickoff, soccer_rules.WINDOW_MIN), take the OPPOSITE
side: YES on the over at that rule's line, at the YES ask, held to settlement. Own fresh record from 2026-11-21 (data/flipped_unders_ledger.json).

Selection is exactly what the rule would have picked (Olu via the Coordinator, Nov 21): the label filter (league + the two teams' labels) AND the
rule's own price band, checked on the under's NO side at entry (NO price = 1 - the line's YES bid, spread 5c or less), as soccer_rules.picks_for does.
The entry is then the over: YES at the YES ask, the same line. A source rule that is retired keeps its selector running for this lane only (its own
ledger and record are untouched). One entry per match: if two source rules select the same match it is logged once with both in `sources`.

Why: on the four under rules' past picks the unders went 1-14 and the overs 14-1, about +80% after fees (C5 3-0, C6 5-0, C7 2-0, B4 4-1, Oct 18
to Nov 7). That is a hindsight sample from rules kept because they failed, so IN_SAMPLE is shown as its own row and never counted.
Review at 10 settled, decide at 30. Runs inside soccer-rules.yml on the soccer rules' lane window and reuses soccer_rules' labels, event matcher,
quote and settlement.
"""
import datetime as dt
import json
import os

import daily_track as D
import settle_only
import soccer_rules as SR

KEY = "flipped_unders"
NAME = "Flipped Unders"
REGISTERED = "2026-11-21"
PATH = os.path.join(SR.ROOT, "data", "flipped_unders_ledger.json")
SOURCES = ("C5", "C6", "C7", "B4")
REVIEW_AT = 10
DECIDE_AT = 30
IN_SAMPLE = {                     # over-side results on the four rules' past picks, Oct 18 to Nov 7 2026: hindsight, never counted
    "window": "Oct 18 to Nov 7 2026", "return": "about +80%",
    "by_rule": {"C5": (3, 0), "C6": (5, 0), "C7": (2, 0), "B4": (4, 1)},     # (won, lost) of the over side
}


def fee(p):
    return SR.fee(p)


def load(path=PATH):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return {"version": "flipped-unders-v1", "registered": REGISTERED, "rules": {"FU": {"picks": []}}, "runs": []}


def sources_for(league, a, b):
    """The source rules whose label filter selects this league and pair of labels, retired or not."""
    return [k for k in SOURCES if SR.in_league(SR.RULES[k], league) and SR.matches(SR.RULES[k]["test"], a, b)]


def due(fixtures, now):
    if settle_only.on():
        return []                                # a settle-only pass adds no entries
    leagues = {SR.RULES[k]["league"] for k in SOURCES}
    return [f for f in SR.due(fixtures, now) if f.get("league") in leagues]


def selects(rule, m):
    """True when `rule` would pick this match at entry: the line is quoted (spread 5c or less) and the under's NO price is inside the rule's band."""
    q = SR.quote(m) if m else None
    if not q:
        return False
    r = SR.RULES[rule]
    px = round(1 - q[0], 4)                                     # the under's NO side, as soccer_rules.picks_for prices it
    return r["lo"] - 1e-9 <= px <= r["hi"] + 1e-9


def picks_for(f, labs, ev, srcs, now):
    """One entry for the match, or []: YES on the over at the first selecting rule's line, at the ask. `srcs` are the label-selected rules;
    those whose price band the under misses at entry are dropped, so the entry follows exactly the matches the rules would have picked."""
    chosen = [k for k in srcs if selects(k, SR.market_at(ev, SR.RULES[k]["line"]))]
    if not chosen:
        return []
    line = SR.RULES[chosen[0]]["line"]
    m = SR.market_at(ev, line)
    b, a = SR.quote(m)
    both = [k for k in chosen if SR.RULES[k]["line"] == line]
    return [dict(id=f"FU:{ev['event_ticker']}:{line}", rule="FU", sources=both, league=f["league"], event=ev["event_ticker"],
                 match=f"{f['home']} v {f['away']}", start=f["kickoff"], ticker=m["ticker"], line=line, side="yes",
                 price=round(a, 4), bid=b, ask=a, under_no=round(1 - b, 4), title=m.get("title") or m.get("yes_sub_title"),
                 logged=now.isoformat(), status="open", labels=dict(home=labs[0], away=labs[1]),
                 why=f"{', '.join(both)} would pick {f['home']} {labs[0]} v {f['away']} {labs[1]} (under NO {1 - b:.2f}) · flipped: over {line} YES {a:.2f}")]


def run(state, fixtures, now=None, fetch=D.get):
    now = now or dt.datetime.now(dt.timezone.utc)
    state.setdefault("rules", {}).setdefault("FU", {"picks": []})
    picks = state["rules"]["FU"]["picks"]
    seen = {p["event"] for p in picks}
    log, errs, cache = [], [], {}
    stats = dict(due=0, selected=0, matched=0)
    for f in due(fixtures, now):
        stats["due"] += 1
        labs = SR.labels(fixtures, f)
        if not all(labs):
            continue
        srcs = sources_for(f["league"], *labs)
        if not srcs:
            continue
        stats["selected"] += 1
        series = SR.SERIES[f["league"]]
        try:
            if series not in cache:
                cache[series] = SR.series_events(series, fetch)
            ev = SR.find_event(f, cache[series])
            if not ev:
                continue
            stats["matched"] += 1
            if ev["event_ticker"] in seen:
                continue
            for p in picks_for(f, labs, ev, srcs, now):
                picks.append(p)
                seen.add(p["event"])
                log.append(p["id"])
        except Exception as e:                                  # noqa: BLE001
            errs.append(f"{f['home']} v {f['away']}: {str(e)[:80]}")
    errs += SR.settle(state, now, fetch)
    state["last_run"] = now.isoformat()
    state["error"] = "; ".join(errs)[:1000] or None
    state["runs"] = (state.get("runs") or [])[-50:] + [dict(at=now.isoformat(), new=len(log), **stats)]
    return log


def record(picks):
    """Entries, won-lost, hit rate, average YES price paid, break-even after fees, return after fees (all as fractions) for a list of picks.
    Break-even is the hit rate at which a YES at the average price plus its fee returns nothing: the mean of price + fee."""
    done = [p for p in picks if p.get("status") in ("won", "lost", "no_result")]
    won = sum(p["status"] == "won" for p in done)
    lost = sum(p["status"] == "lost" for p in done)
    out = dict(entries=len(picks), settled=len(done), won=won, lost=lost, open=len(picks) - len(done))
    out["hit"] = won / (won + lost) if won + lost else None
    prices = [float(p["price"]) for p in picks]
    out["avg_price"] = sum(prices) / len(prices) if prices else None
    out["break_even"] = sum(x + fee(x) for x in prices) / len(prices) if prices else None
    out["ret"] = sum(float(p.get("profit") or 0) for p in done) / (100 * len(done)) if done else None
    return out


def by_source(picks):
    """{rule: record} for each source rule, a pick that two rules selected counting under both."""
    return {k: record([p for p in picks if k in (p.get("sources") or [])]) for k in SOURCES}


def verdict(n):
    if n < REVIEW_AT:
        return f"too early ({n} of {REVIEW_AT} settled for the review, {DECIDE_AT} to decide)"
    return f"review ({n} settled)" if n < DECIDE_AT else f"decide ({n} settled)"


def main(argv=None):
    import sys
    import streaks_fetch
    argv = sys.argv[1:] if argv is None else argv
    out = argv[argv.index("--out") + 1] if "--out" in argv else PATH
    state = load(out)
    fixtures = streaks_fetch.load_or_fetch()["fixtures"]
    new = run(state, fixtures)
    tmp = out + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f, indent=1, sort_keys=True)
        f.write("\n")
    os.replace(tmp, out)
    print("run", state["runs"][-1], "new", new, "error", state["error"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
