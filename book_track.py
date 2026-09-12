#!/usr/bin/env python3
"""book_track.py — price EVERY tracked fixture inside a day of kickoff, grade it, and ask
where the book is wrong: by market, by league, by price band, and by team.

WHY EVERY FIXTURE, NOT JUST LEADS
---------------------------------
The leads ledger only observes a team while it is on a run — exactly the condition under
which its next result regresses — so a per-team record built from leads would confound
the team with the streak all over again. It is also slow (one lead a week per team) and
picks its own sample. This ledger takes every competitive fixture in the pull once it is
within PRICE_WINDOW_H of kickoff, whatever the form on either side, so it is a general
calibration ledger for the book: the same rows answer which LEAGUES pay at the price,
which PRICE BANDS, home v away, and whether model.py's Brier beats the book's on a sample
nobody hand-picked. The per-team "paid at the price" tag is a drill-down on that.

THE TEST
--------
Per segment, pooled across markets: hits against EXPECTED hits, where expected is the sum
of the book's vig-free probabilities. Excess = hits - sum(fair); z = excess / sqrt(sum
fair*(1-fair)). That is the honest test of "beat the book" — ROI is shown for the money
view but at n=10 its standard deviation is ~24pp, so z is the number to read. A team is
tagged PAYING only past TEAM_FLOOR observations and z >= TEAM_Z, and every table says how
many teams were tested, because with ~230 teams about six reach z=2 by chance alone.

Same discipline as streaks_track: a fixture is priced ONCE, only BEFORE kickoff, and the
model's probability is logged at the same instant. A row graded after the fact is never
re-priced.

Usage:  python3 book_track.py            record + grade + print the report
"""
import json, os, math, datetime, collections

ROOT = os.path.dirname(os.path.abspath(__file__))
LEDGER = os.path.join(ROOT, "data", "book_ledger.json")

PRICE_WINDOW_H = 24        # a fixture is priced once it is this close to kickoff
MAX_FETCHES = 80           # per build, ~1.5s each (venues.PRICE_PACE_S)
VOID_AFTER_DAYS = 7        # no final score by then: postponed or moved
VALUE_MARGIN = 0.05        # model beats book fair by this much = "value" (pre-registered)
TEAM_FLOOR = 20            # observations before a team may carry a tag
TEAM_Z = 2.0               # and the excess must be this many sigmas over the book
BAND_EDGES = (0.4, 0.5, 0.6, 0.7, 0.8, 0.9)

MARKETS = ("over15", "over25", "btts", "home2plus", "away2plus")
MARKET_LABEL = {"over15": "Over 1.5 goals", "over25": "Over 2.5 goals",
                "btts": "Both teams to score", "home2plus": "Home side scores 2+",
                "away2plus": "Away side scores 2+"}


def utc_now():
    return datetime.datetime.now(datetime.timezone.utc)


def _dt(iso):
    if not iso:
        return None
    try:
        return datetime.datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return None


def fixture_id(f):
    return f"{f['date']}|{f['home']}|{f['away']}"


def outcome(mk, hg, ag):
    return {"over15": hg + ag >= 2, "over25": hg + ag >= 3,
            "btts": hg >= 1 and ag >= 1, "home2plus": hg >= 2, "away2plus": ag >= 2}[mk]


# ---------------------------------------------------------------- ledger
def load(path=LEDGER):
    if os.path.exists(path):
        try:
            blob = json.load(open(path))
            blob.setdefault("rows", {})
            return blob
        except Exception:
            pass
    return {"rows": {}}


def save(blob, path=LEDGER):
    blob["updated_at"] = utc_now().isoformat(timespec="seconds")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(blob, f, indent=1, sort_keys=True)


def quotes_from(book):
    """Flatten venues.parse_bovada_prices() output to this ledger's market keys."""
    if not book:
        return {}
    q = {mk: dict(book[mk]) for mk in ("over15", "over25", "btts") if book.get(mk)}
    team = book.get("team") or {}
    for side, mk in (("home", "home2plus"), ("away", "away2plus")):
        t = (team.get(side) or {}).get("over15")
        if t:
            q[mk] = dict(t)
    return q


def record(fixtures, blob, link_for, fetch, model=None, now=None):
    """Price fixtures entering the window. `link_for(f)` -> venue URL or None;
    `fetch(link)` -> parsed book or None. Returns (blob, n_priced, n_fetched)."""
    import model as M
    now = now or utc_now()
    horizon = now + datetime.timedelta(hours=PRICE_WINDOW_H)
    n_priced = n_fetched = 0
    for f in sorted(fixtures, key=lambda f: f.get("kickoff") or ""):
        if f.get("played") or not f.get("competitive", True):
            continue
        ko = _dt(f.get("kickoff"))
        if ko is None or ko <= now or ko > horizon:
            continue
        fid = fixture_id(f)
        if fid in blob["rows"]:
            continue
        if n_fetched >= MAX_FETCHES:
            break
        link = link_for(f)
        if not link:
            continue
        n_fetched += 1
        q = quotes_from(fetch(link))
        if not q:
            continue                              # no line yet: retried next build
        row = {"id": fid, "date": f["date"], "kickoff": f["kickoff"],
               "league": f["league"], "lead_source": bool(f.get("lead_source", True)),
               "home": f["home"], "away": f["away"],
               "prices": q, "priced_at": now.isoformat(timespec="seconds"),
               "status": "pending"}
        if model is not None and M.known(model, f["home"]) and M.known(model, f["away"]):
            p = M.probs(model, f["home"], f["away"], f["league"])
            row["model"] = {mk: round(p[mk], 4) for mk in q if mk in p}
        blob["rows"][fid] = row
        n_priced += 1
    return blob, n_priced, n_fetched


def grade(fixtures, blob, now=None):
    now = now or utc_now()
    results = {}
    for f in fixtures:
        if f.get("played") and f.get("home_goals") is not None:
            results[fixture_id(f)] = (f["home_goals"], f["away_goals"])
    n = 0
    for fid, r in blob["rows"].items():
        if r["status"] != "pending":
            continue
        if fid not in results:
            ko = _dt(r.get("kickoff"))
            if ko and (now - ko).days > VOID_AFTER_DAYS:
                r["status"] = "void"
                r["note"] = "no final score found — postponed, or the fixture moved"
                n += 1
            continue
        hg, ag = results[fid]
        r["final"] = f"{hg}-{ag}"
        r["result"] = {mk: outcome(mk, hg, ag) for mk in r["prices"]}
        r["pnl"] = {mk: (round(r["prices"][mk]["price"] - 1, 4) if hit else -1.0)
                    for mk, hit in r["result"].items()}
        r["status"] = "graded"
        r["graded_at"] = now.isoformat(timespec="seconds")
        n += 1
    return blob, n


# ---------------------------------------------------------------- measurement
def _obs(blob):
    """One observation per (graded row, market): what the book said, what happened."""
    out = []
    for r in blob["rows"].values():
        if r.get("status") != "graded":
            continue
        for mk, hit in r["result"].items():
            out.append({"row": r, "mk": mk, "hit": bool(hit),
                        "fair": r["prices"][mk]["fair"], "price": r["prices"][mk]["price"],
                        "pnl": r["pnl"][mk], "model": (r.get("model") or {}).get(mk)})
    return out


def _agg(obs):
    n = len(obs)
    if not n:
        return None
    hits = sum(1 for o in obs if o["hit"])
    exp = sum(o["fair"] for o in obs)
    var = sum(o["fair"] * (1 - o["fair"]) for o in obs)
    z = (hits - exp) / math.sqrt(var) if var > 0 else 0.0
    d = {"n": n, "hits": hits, "rate": hits / n, "fair": exp / n, "expected": exp,
         "excess": hits - exp, "z": z, "pnl": sum(o["pnl"] for o in obs),
         "roi": sum(o["pnl"] for o in obs) / n}
    mod = [o for o in obs if o["model"] is not None]
    if mod:
        d["n_model"] = len(mod)
        d["brier_model"] = sum((o["model"] - o["hit"]) ** 2 for o in mod) / len(mod)
        d["brier_book"] = sum((o["fair"] - o["hit"]) ** 2 for o in mod) / len(mod)
        d["model_better"] = d["brier_model"] < d["brier_book"]
    return d


def team_index(blob):
    """team -> pooled record against the book. Fixture-level markets count for both
    sides (they share the observation); a side's own 2+ counts for that side only."""
    per = collections.defaultdict(list)
    for o in _obs(blob):
        r = o["row"]
        if o["mk"] == "home2plus":
            per[r["home"]].append(o)
        elif o["mk"] == "away2plus":
            per[r["away"]].append(o)
        else:
            per[r["home"]].append(o)
            per[r["away"]].append(o)
    out = {}
    for t, obs in per.items():
        a = _agg(obs)
        a["paying"] = a["n"] >= TEAM_FLOOR and a["z"] >= TEAM_Z
        out[t] = a
    return out


def report(blob):
    obs = _obs(blob)
    rows = blob["rows"].values()
    by_market = []
    for mk in MARKETS:
        a = _agg([o for o in obs if o["mk"] == mk])
        if a:
            by_market.append(dict(a, market=mk, label=MARKET_LABEL[mk]))
    by_league = []
    for lg in sorted({o["row"]["league"] for o in obs}):
        a = _agg([o for o in obs if o["row"]["league"] == lg])
        by_league.append(dict(a, league=lg))
    by_league.sort(key=lambda r: -r["n"])
    by_venue = []
    for label, sel in (("Home side scores 2+", lambda o: o["mk"] == "home2plus"),
                       ("Away side scores 2+", lambda o: o["mk"] == "away2plus")):
        a = _agg([o for o in obs if sel(o)])
        if a:
            by_venue.append(dict(a, label=label))
    bands = []
    edges = (0.0,) + BAND_EDGES + (1.0,)
    for lo, hi in zip(edges, edges[1:]):
        a = _agg([o for o in obs if lo <= o["fair"] < hi])
        if a:
            bands.append(dict(a, lo=lo, hi=hi))
    modelled = [o for o in obs if o["model"] is not None]
    value = _agg([o for o in modelled if o["model"] - o["fair"] >= VALUE_MARGIN - 1e-9])
    rest = _agg([o for o in modelled if o["model"] - o["fair"] < VALUE_MARGIN - 1e-9])
    teams = team_index(blob)
    ranked = sorted(teams.items(), key=lambda kv: -kv[1]["z"])
    return {
        "fixtures": len(blob["rows"]),
        "graded": sum(1 for r in rows if r.get("status") == "graded"),
        "pending": sum(1 for r in rows if r.get("status") == "pending"),
        "void": sum(1 for r in rows if r.get("status") == "void"),
        "observations": len(obs),
        "overall": _agg(obs),
        "by_market": by_market, "by_league": by_league, "by_venue": by_venue,
        "bands": bands, "value": value, "rest": rest, "margin": VALUE_MARGIN,
        "teams_tested": len(teams), "team_floor": TEAM_FLOOR, "team_z": TEAM_Z,
        "paying": [(t, a) for t, a in ranked if a["paying"]],
        "top_teams": [(t, a) for t, a in ranked if a["n"] >= TEAM_FLOOR][:8],
        "bottom_teams": [(t, a) for t, a in reversed(ranked) if a["n"] >= TEAM_FLOOR][:5],
    }


def run(fixtures, blob=None, now=None):
    """One cycle: grade what finished, then price what has entered the window."""
    import model as M
    from venues import fetch_bovada_events, venue_link, fetch_bovada_prices
    blob = load() if blob is None else blob
    blob, graded = grade(fixtures, blob, now)
    events = fetch_bovada_events()
    mdl = M.fit(fixtures)

    def link_for(f):
        if not events:
            return None
        return venue_link(f"{f['home']} vs {f['away']}", f.get("kickoff") or f.get("date"),
                          events)
    blob, priced, fetched = record(fixtures, blob, link_for, fetch_bovada_prices, mdl, now)
    return blob, graded, priced, fetched


if __name__ == "__main__":
    import streaks_fetch
    fx = streaks_fetch.load_or_fetch()["fixtures"]
    b, graded, priced, fetched = run(fx)
    save(b)
    r = report(b)
    print(f"book ledger: {r['fixtures']} fixtures | graded now {graded} | "
          f"priced now {priced} ({fetched} fetched) | {r['pending']} pending, "
          f"{r['graded']} graded, {r['void']} void")
    if r["overall"]:
        o = r["overall"]
        print(f"overall: {o['n']} observations, hit {o['rate']:.1%} v book {o['fair']:.1%}, "
              f"excess {o['excess']:+.1f} (z {o['z']:+.2f}), ROI {o['roi']:+.1%}")
        print(f"{'market':22s}{'n':>5}{'hit':>7}{'book':>7}{'z':>7}{'ROI':>8}")
        for m in r["by_market"]:
            print(f"{m['label']:22s}{m['n']:5d}{m['rate']:7.1%}{m['fair']:7.1%}{m['z']:+7.2f}{m['roi']:+8.1%}")
        if r["paying"]:
            print("PAYING:", ", ".join(f"{t} (n={a['n']}, z {a['z']:+.1f})" for t, a in r["paying"]))
        else:
            print(f"no team past the floor with z >= {TEAM_Z} ({r['teams_tested']} tested)")
