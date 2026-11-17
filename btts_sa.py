"""Brazil and Argentina BTTS YES (2026-11-16): a Sandbox PAPER lane, `btts_sa`.

Paper only: not in Production, no live pairing. Its own fresh record (data/btts_sa_ledger.json).
Olu approved the row Nov 16 2026 (spec docs/btts_brazil_argentina_2026-11-16.md, pre-registration
docs/prereg_btts_bra_arg_2026-11-16.md).

PRE-REGISTERED RULE (verbatim):
Brazil and Argentina BTTS YES. Paper. Every Serie A and Primera match, YES at the ask 20 to 90
minutes before kickoff, spread 5c or less, after fees. Scored by match day. Read at 50 and 100 bets.
Held if it is positive with a clustered z of 2 or more at 100 bets. Retired if it is negative at 100.

Evidence (a lead, not a tested rule): 384 bets, 53.6% at 47.2c, +6.4 points, +10.2%, positive in both
halves; Argentina carries it.

Mechanics, the sa_o15 template: ESPN fixtures matched to the Kalshi event by both names (sa_o15.find_event,
never fuzzy, ambiguity skipped); one BTTS market a match (ticker ends -BTTS); entry 20 to 90 minutes
before kickoff at the ask, spread 5c or less, fee 0.07 p (1 - p); one frozen entry per match; settled on
Kalshi's own result. Rows: YES (every match; shown as both leagues, Brazil, Argentina) and the NO control
(BTTS NO at its ask, same matches). The ledger's schedule is the next 14 days of kickoffs for the VPS
(lane_windows.btts_kickoffs); it runs inside soccer-rules.yml on the soccer rules' lane window.
"""
import datetime as dt
import json
import os

import daily_track as D
import sa_o15
import settle_only
import soccer_rules as SR

ROOT = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(ROOT, "data", "btts_sa_ledger.json")
FEE = SR.FEE
WINDOW_MIN = SR.WINDOW_MIN       # (20, 90) minutes before kickoff
SCHEDULE_DAYS = 14
# ESPN league name -> (row key, Kalshi BTTS series)
LEAGUES = {"Liga Profesional": ("ARG", "KXARGPREMDIVBTTS"),
           "Brasileirão": ("BRA", "KXBRASILEIROBTTS")}
RULES = ("YES", "NO")            # YES is the lane, NO the control
PREREG = ("Brazil and Argentina BTTS YES. Paper. Every Serie A and Primera match, YES at the ask 20 to 90 minutes before "
          "kickoff, spread 5c or less, after fees. Scored by match day. Read at 50 and 100 bets. Held if it is positive "
          "with a clustered z of 2 or more at 100 bets. Retired if it is negative at 100.")
EVIDENCE = "384 bets, won 53.6% at 47.2c, +6.4 points, +10.2% after fees, positive in both halves; Argentina carries it"
# (row key, label, which picks): the page's four rows
ROWS = (("all", "Brazil and Argentina", lambda p: p["rule"] == "YES"),
        ("bra", "Brazil", lambda p: p["rule"] == "YES" and p["league_key"] == "BRA"),
        ("arg", "Argentina", lambda p: p["rule"] == "YES" and p["league_key"] == "ARG"),
        ("no", "BTTS NO control", lambda p: p["rule"] == "NO"))


def fee(p):
    return FEE * p * (1 - p)


def retired(key, now=None):
    """Nothing is retired yet: the pre-registered read is at 50 and 100 bets."""
    return False


def load(path=PATH):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return {"version": "btts-sa-v1", "rules": {k: {"picks": []} for k in RULES}, "runs": [], "schedule": []}


def quote(m, side):
    """(bid, ask) of the side, spread 5c or less, or None."""
    if side == "yes":
        return SR.quote(m)
    return SR.quote(dict(yes_bid_dollars=m.get("no_bid_dollars"), yes_ask_dollars=m.get("no_ask_dollars")))


def picks_for(f, ev, now):
    """The YES entry and the NO control for one match, each only if its own book is quotable."""
    m = SR.market_at(ev, None, "btts")
    if not m:
        return []
    key = LEAGUES[f["league"]][0]
    out = []
    for rule, side in (("YES", "yes"), ("NO", "no")):
        q = quote(m, side)
        if not q:
            continue
        b, a = q
        out.append(dict(id=f"{rule}:{ev['event_ticker']}", rule=rule, league=f["league"], league_key=key,
                        event=ev["event_ticker"], match=f"{f['home']} v {f['away']}", start=f["kickoff"],
                        ticker=m["ticker"], side=side, price=round(a, 4), bid=b, ask=a,
                        logged=now.isoformat(), status="open",
                        why=f"{'Brazil' if key == 'BRA' else 'Argentina'} BTTS {side.upper()} {a:.2f}"))
    return out


def due(fixtures, now):
    if settle_only.on():
        return []                                # a settle-only pass adds no entries
    out = []
    for f in fixtures:
        if f.get("played") or f.get("league") not in LEAGUES:
            continue
        t = D.instant(f.get("kickoff"))
        if t and WINDOW_MIN[0] * 60 <= (t - now).total_seconds() <= WINDOW_MIN[1] * 60:
            out.append(f)
    return out


def schedule(fixtures, now):
    """Kickoffs of unplayed matches in the two leagues over the next 14 days, ISO UTC, sorted."""
    out = set()
    for f in fixtures:
        if f.get("played") or f.get("league") not in LEAGUES:
            continue
        t = D.instant(f.get("kickoff"))
        if t and now - dt.timedelta(hours=2) <= t <= now + dt.timedelta(days=SCHEDULE_DAYS):
            out.add(t.astimezone(dt.timezone.utc).isoformat())
    return sorted(out)


def run(state, fixtures, now=None, fetch=D.get):
    now = now or dt.datetime.now(dt.timezone.utc)
    for k in RULES:
        state["rules"].setdefault(k, {"picks": []})
    seen = {p["id"] for lane in state["rules"].values() for p in lane["picks"]}
    log, errs, series_cache = [], [], {}
    stats = dict(due=0, matched=0, quoted=0)
    for f in due(fixtures, now):
        stats["due"] += 1
        series = LEAGUES[f["league"]][1]
        try:
            if series not in series_cache:
                series_cache[series] = SR.series_events(series, fetch)
            ev = sa_o15.find_event(f, series_cache[series], fixtures)
            if not ev:
                continue
            stats["matched"] += 1
            ps = picks_for(f, ev, now)
            if not ps:
                continue
            stats["quoted"] += 1
            for p in ps:
                if p["id"] in seen:
                    continue
                state["rules"][p["rule"]]["picks"].append(p)
                seen.add(p["id"])
                log.append(p["id"])
        except Exception as e:                                  # noqa: BLE001
            errs.append(f"{f['home']} v {f['away']}: {str(e)[:80]}")
    errs += SR.settle(state, now, fetch)
    state["schedule"] = schedule(fixtures, now)
    state["last_run"] = now.isoformat()
    state["error"] = "; ".join(errs)[:1000] or None
    state["runs"] = (state.get("runs") or [])[-50:] + [dict(at=now.isoformat(), new=len(log), **stats)]
    return log


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
    print("run", state["runs"][-1], "new", new, "schedule", len(state["schedule"]), "error", state["error"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
