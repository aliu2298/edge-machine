"""Title contenders' matches · overs (2026-10-18): a Sandbox PAPER lane, `contender_overs`.

Paper only: not in Production, not in the Production feed, on its own fresh record
(data/contender_overs_ledger.json). Nothing is placed.

Research (Oct 18 2026, memory title-contender-markets). Contenders were ranked POINT IN TIME: the
top 3 by Kalshi league-champion market mid 36 hours before each match (Olu's requirement; ranking by
today's table was hindsight). In matches involving a contender, the goals lines paid in the
Eredivisie and Primeira on every line, with the same clubs:

    League                              Over 1.5            Over 2.5            Over 3.5
    Eredivisie (Ajax/Feyenoord/PSV)     25/25 @90c, +10%    22/25 @74c, +17%    20/25 @54c, +45%
    Primeira (Benfica/Porto/Sporting)   19/19 @82c, +20%    15/19 @61c, +26%    10/19 @38c, +31%

The Eredivisie also led the earlier league-wide totals research; pooled over 9 leagues, over 2.5 in
contender matches was +8.2%, z +2.17. The contender win and team-2+ edges were hindsight (+1.7% and
+1.9% point in time), so they are NOT part of this lane.

PRE-REGISTERED RULE
1. Scope: Kalshi Eredivisie and Liga Portugal league matches only (KXEREDIVISIETOTAL,
   KXLIGAPORTUGALTOTAL).
2. Contenders, point in time: at entry, read the open champion market (KXEREDIVISIE,
   KXLIGAPORTUGAL), rank teams by mid ((yes_bid + yes_ask) / 2), ignoring any team with no bid
   (a 0-11c quote with nobody bidding is not a contender price). The top 3 are contenders; a match
   qualifies if either side is one. Names match exactly, or by containment of 5+ characters on
   whole words after normalising (never fuzzy: fuzzy matching put Man City on Man United and
   Rennes on Brest in the research).
3. Bets: three variants, separate rows per qualifying match: over 1.5, over 2.5 and over 3.5 YES on
   the match's total-goals market. The line comes from the market TITLE, never the ticker suffix
   (Kalshi renumbered soccer TOTAL suffixes between seasons).
4. Entry: 90 to 20 minutes before the ESPN kickoff (as soccer_rules), at the YES ask, spread 5c or
   less, fee 0.07 p (1 - p). One frozen entry per variant per match, carrying the contender list and
   their mids so the point-in-time choice can be audited.
5. Settled on Kalshi's own result, profit per $100 after the fee.

It runs inside soccer-rules.yml on the soccer rules' lane window (both leagues are in it), after
soccer_rules.py, and reuses that module's quote, event matcher and settlement.
"""
import datetime as dt
import json
import os
import re
import unicodedata

import daily_track as D
import soccer_rules as SR

ROOT = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(ROOT, "data", "contender_overs_ledger.json")
FEE = SR.FEE
WINDOW_MIN = SR.WINDOW_MIN       # (20, 90) minutes before kickoff
TOP_N = 3
NAME_MIN = 5
# ESPN league name (streaks_fetch) -> (Kalshi champion series, Kalshi match total series)
LEAGUES = {"Eredivisie": ("KXEREDIVISIE", "KXEREDIVISIETOTAL"),
           "Primeira Liga": ("KXLIGAPORTUGAL", "KXLIGAPORTUGALTOTAL")}
VARIANTS = {
    "O15": dict(line=1.5, words="Over 1.5 goals · YES", evidence="Eredivisie 25/25 @90c +10% · Primeira 19/19 @82c +20%"),
    "O25": dict(line=2.5, words="Over 2.5 goals · YES", evidence="Eredivisie 22/25 @74c +17% · Primeira 15/19 @61c +26%"),
    "O35": dict(line=3.5, words="Over 3.5 goals · YES", evidence="Eredivisie 20/25 @54c +45% · Primeira 10/19 @38c +31%"),
}


def fee(p):
    return FEE * p * (1 - p)


def load(path=PATH):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return {"version": "contender-overs-v1", "rules": {k: {"picks": []} for k in VARIANTS}, "runs": []}


# ---------- names ----------

def norm(name):
    s = unicodedata.normalize("NFKD", str(name or "")).encode("ascii", "ignore").decode().lower()
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", s).split())


def same_team(a, b):
    """Exact after normalising, or the shorter name (5+ characters) is whole words of the longer.

    Never fuzzy: 'Man City' is not 'Man United' and 'Rennes' is not 'Brest'."""
    x, y = norm(a), norm(b)
    if not x or not y:
        return False
    if x == y:
        return True
    short, long_ = (x, y) if len(x) <= len(y) else (y, x)
    return len(short) >= NAME_MIN and f" {short} " in f" {long_} "


# ---------- contenders, point in time ----------

def contenders(champ_events):
    """Top TOP_N teams of the open champion market by mid, no-bid teams excluded.

    [dict(team, mid, bid, ask, ticker)], highest mid first."""
    rows = []
    for ev in champ_events or []:
        for m in ev.get("markets") or []:
            if m.get("status") not in ("active", "open"):
                continue
            b, a = D.number(m.get("yes_bid_dollars")), D.number(m.get("yes_ask_dollars"))
            if not b or b <= 0 or a is None or a <= 0:
                continue
            rows.append(dict(team=m.get("yes_sub_title") or m.get("title"), mid=round((b + a) / 2, 4), bid=b, ask=a,
                             ticker=m.get("ticker")))
    rows.sort(key=lambda r: -r["mid"])
    return rows[:TOP_N]


def contender_in(ev, top):
    """The contenders (by name) playing in the Kalshi event, or []."""
    names = SR.event_teams(ev) or []
    return [c["team"] for c in top if any(same_team(c["team"], n) for n in names)]


# ---------- entries ----------

def picks_for(f, ev, top, now):
    hits = contender_in(ev, top)
    if not hits:
        return []
    out = []
    for key, v in VARIANTS.items():
        m = SR.market_at(ev, v["line"])
        q = SR.quote(m) if m else None
        if not q:
            continue
        b, a = q
        out.append(dict(id=f"{key}:{ev['event_ticker']}", rule=key, league=f["league"], event=ev["event_ticker"],
                        match=f"{f['home']} v {f['away']}", start=f["kickoff"], ticker=m["ticker"], line=v["line"],
                        side="yes", price=round(a, 4), bid=b, ask=a, title=m.get("title") or m.get("yes_sub_title"),
                        logged=now.isoformat(), status="open", contenders_in=hits,
                        contenders=[dict(team=c["team"], mid=c["mid"], bid=c["bid"], ask=c["ask"]) for c in top],
                        why=f"{', '.join(hits)} in a top-{TOP_N} title spot · over {v['line']} YES {a:.2f}"))
    return out


def due(fixtures, now):
    out = []
    for f in fixtures:
        if f.get("played") or f.get("league") not in LEAGUES:
            continue
        t = D.instant(f.get("kickoff"))
        if t and WINDOW_MIN[0] * 60 <= (t - now).total_seconds() <= WINDOW_MIN[1] * 60:
            out.append(f)
    return out


def champion_events(series, fetch):
    return D.pages(f"events?series_ticker={series}&status=open&limit=200&with_nested_markets=true", "events", fetch)


def run(state, fixtures, now=None, fetch=D.get):
    now = now or dt.datetime.now(dt.timezone.utc)
    for k in VARIANTS:
        state["rules"].setdefault(k, {"picks": []})
    seen = {p["id"] for lane in state["rules"].values() for p in lane["picks"]}
    log, errs, champs, totals = [], [], {}, {}
    stats = dict(due=0, matched=0, qualifying=0)
    for f in due(fixtures, now):
        stats["due"] += 1
        champ_series, total_series = LEAGUES[f["league"]]
        try:
            if champ_series not in champs:
                champs[champ_series] = contenders(champion_events(champ_series, fetch))
            if total_series not in totals:
                totals[total_series] = SR.series_events(total_series, fetch)
            ev = SR.find_event(f, totals[total_series])
            if not ev:
                continue
            stats["matched"] += 1
            new = picks_for(f, ev, champs[champ_series], now)
            if new or contender_in(ev, champs[champ_series]):
                stats["qualifying"] += 1
            for p in new:
                if p["id"] in seen:
                    continue
                state["rules"][p["rule"]]["picks"].append(p)
                seen.add(p["id"])
                log.append(p["id"])
        except Exception as e:                                  # noqa: BLE001
            errs.append(f"{f['home']} v {f['away']}: {str(e)[:80]}")
    errs += SR.settle(state, now, fetch)
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
    print("run", state["runs"][-1], "new", new, "error", state["error"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
