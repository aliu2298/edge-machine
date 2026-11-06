"""Soccer team-scoring label rules (2026-10-17): 8 Sandbox paper lanes on Kalshi team totals.

Registered by Olu on 411 matches, Aug 1 - Oct 17 2026, across 8 leagues (research session
2026-10-17, memory soccer-team-scoring-rules). The contracts are Kalshi's team totals,
KX<league>TEAMTOTAL, rungs "<team> over 0.5 / 1.5 / 2.5 goals". Results were checked against ESPN
(1,952 of 1,956 agree), the labels are point in time, and the data has no duplicates. With quotes
over a 5c spread dropped, the patterns still beat a shuffled-label null (7 real patterns against
a null mean of 2.2, p about 0.01).

Labels are soccer_rules.py's exactly: each team's last 10 COMPETITIVE played matches before
kickoff (ESPN, data/streaks_raw.json) against its league's mean goals per team over the
league's last 400 team-games before kickoff. O+ scores at least the mean, else O-; D+ concedes
at least the mean, else D-. Fewer than 6 team matches or 40 league team-games: no label, no
entry. The league is the Kalshi series' league, so a UCL match uses UCL fixtures for the mean.

Unlike the match-total rules the pair is ORDERED: `own` is the team the contract is about and
`opp` its opponent. 2+ is the "over 1.5" rung, 3+ is "over 2.5".

Paper, at the Kalshi price with the 7% fee, settled on Kalshi's own result. Nothing here places
an order. T1 alone moved to Production by hand on 2026-10-24 (soccer_team_rules_production
publishes its entries from this ledger as live $1 leads); T2-T8 stay Sandbox paper. One frozen entry per rule, team and match, taken 90 to
20 minutes before the ESPN kickoff, spread 5c or less, price 3-97c. YES pays the ask; NO pays
1 - the YES bid.

                                                                  evidence, spread <= 5c
  Rule Grp  own v opp       Rung Side  Leagues                    in its leagues            all leagues
  T1   A    O+D- v O+D-     2+   YES   Serie A, UCL, EPL,         38/56, +36%, z 3.17       48/79, +22%
                                       Bundesliga, Ligue 1
  T2   A    O-D- v O-D+     2+   NO    MLS, La Liga, Ligue 1      25/34, +29%               30/43, +20%
  T3   B    O+D- v O-D-     3+   YES   MLS, La Liga, Serie A,     12/24 at a median 23c,    12/27, +83%
                                       Ligue 1                    +105%
  T4   B    O+D- v O-D+     2+   YES   MLS, La Liga, EPL          18/24, +39%               24/36, +22%
  T5   B    O+D- v O+D+     2+   YES   MLS, Serie A, Ligue 1,     20/26, +35%               36/54, +16%
                                       Europa League
  T6   C    O+D+ v O+D-     3+   NO    MLS, EPL, Bundesliga,      21/22 at a median 85c,    31/33, +12%
                                       Serie A                    +16%
  T7   C    O+D+ v O+D+     3+   NO    MLS, La Liga, Bundesliga,  17/17 at 73c, +30%        17/18, +24%
                                       EPL
  T8   C    O+D+ v O-D-     2+   NO    EPL, La Liga, Ligue 1      9/12, +37%                20/33, +14% (the
                                                                                            later half was flat)

WHICH TEAM A MARKET IS ABOUT comes from the ticker: the letters of its last segment (-BOU2 ->
BOU) against the event's pair code, segment 2 after its 7-character date (26OCT18BOUSUN ->
BOUSUN). The pair starting with it is the home team, ending with it the away team; anything
else is skipped. THE LINE COMES FROM THE MARKET TITLE ("Will Bournemouth score over 1.5
goals?"), never the ticker suffix, which Kalshi renumbered between seasons. The Kalshi event
("Home vs Away: Team Total") is tied to its ESPN fixture by soccer_rules.find_event: date
within a day and both names at similarity 0.45 or more.
"""
import datetime as dt
import json
import os
import re

import daily_track as D
import soccer_rules as SR

ROOT = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(ROOT, "data", "soccer_team_rules_ledger.json")
FEE = SR.FEE
WINDOW_MIN = SR.WINDOW_MIN       # (20, 90) minutes before kickoff
MAX_SPREAD = SR.MAX_SPREAD
PRICE_LO, PRICE_HI = 0.03, 0.97

# ESPN league name (streaks_fetch) -> Kalshi team-total series.
SERIES = {
    "Premier League": "KXEPLTEAMTOTAL", "La Liga": "KXLALIGATEAMTOTAL",
    "Bundesliga": "KXBUNDESLIGATEAMTOTAL", "Serie A": "KXSERIEATEAMTOTAL",
    "Ligue 1": "KXLIGUE1TEAMTOTAL", "MLS": "KXMLSTEAMTOTAL",
    "Champions League": "KXUCLTEAMTOTAL", "Europa League": "KXUELTEAMTOTAL",
}
GROUPS = {"A": "Strongest · holds in its leagues and across all of them",
          "B": "Supported · fewer entries",
          "C": "NO side · an O+D+ team held under its rung"}
EPL, LIGA, BUNDES, SERIEA, L1, MLS, UCL, UEL = ("Premier League", "La Liga", "Bundesliga", "Serie A",
                                                "Ligue 1", "MLS", "Champions League", "Europa League")


def _r(group, own, opp, goals, side, leagues, evidence):
    words = lambda x: x.replace("-", "−")
    return dict(group=group, own=own, opp=opp, line=goals - 0.5, goals=goals, side=side,
                leagues=tuple(leagues), evidence=evidence,
                label=f"{words(own)} v {words(opp)} · team {goals}+ goals · {side.upper()}")


RULES = {
    "T1": _r("A", "O+D-", "O+D-", 2, "yes", (SERIEA, UCL, EPL, BUNDES, L1), "38/56, +36%, z 3.17 · all leagues 48/79, +22%"),
    "T2": _r("A", "O-D-", "O-D+", 2, "no", (MLS, LIGA, L1), "25/34, +29% · all leagues 30/43, +20%"),
    "T3": _r("B", "O+D-", "O-D-", 3, "yes", (MLS, LIGA, SERIEA, L1), "12/24 at a median 23c, +105% · all leagues 12/27, +83%"),
    "T4": _r("B", "O+D-", "O-D+", 2, "yes", (MLS, LIGA, EPL), "18/24, +39% · all leagues 24/36, +22%"),
    "T5": _r("B", "O+D-", "O+D+", 2, "yes", (MLS, SERIEA, L1, UEL), "20/26, +35% · all leagues 36/54, +16%"),
    "T6": _r("C", "O+D+", "O+D-", 3, "no", (MLS, EPL, BUNDES, SERIEA), "21/22 at a median 85c, +16% · all leagues 31/33, +12%"),
    "T7": _r("C", "O+D+", "O+D+", 3, "no", (MLS, LIGA, BUNDES, EPL), "17/17 at 73c, +30% · all leagues 17/18, +24%"),
    "T8": _r("C", "O+D+", "O-D-", 2, "no", (EPL, LIGA, L1), "9/12, +37% · all leagues 20/33, +14%, later half flat"),
}


def fee(p):
    return FEE * p * (1 - p)


def load(path=PATH):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return {"version": "soccer-team-rules-v1", "rules": {k: {"picks": []} for k in LANES}, "runs": []}


def fires(rule, league, own, opp):
    """THE test of whether `rule` fires for the team labelled `own` against an opponent labelled `opp`. T1, T1-H
    and T1-M all ask it for T1, so the siblings cannot drift from T1's selection (2026-11-06)."""
    r = RULES[rule]
    return bool(own and opp) and league in r["leagues"] and r["own"] == own and r["opp"] == opp


def applicable(league, own, opp):
    """Rules that fire for the team labelled `own` against an opponent labelled `opp`."""
    if not own or not opp:
        return []
    return [k for k in RULES if fires(k, league, own, opp)]


def t1_sides(league, labs):
    """The sides T1 takes in a match ("home", "away"); a match is a T1 match when this is not empty."""
    return [team for team, own, opp in (("home", labs[0], labs[1]), ("away", labs[1], labs[0]))
            if fires("T1", league, own, opp)]


# T1's two Sandbox paper siblings (2026-11-06, Olu). T1 itself is unchanged and decides at 50 settled.
#   T1-H  the home team's 2+ YES only, on T1's matches: on T1's first 48 forward bets home went 17/24 v 13.4
#         priced, +38.8% (z 1.58); away 11/24 v 11.2, −9.9%.
#   T1-M  the match total over 3.5 YES (KX<league>TOTAL, the over 3.5 rung) on the same matches, one bet a match:
#         both teams scored 2+ in 8 of T1's 24 matches (33%) v about 24% implied by the two team prices.
# The same entry as T1: 90-20 minutes before kickoff, spread 5c or less, 3-97c, YES at the ask. Fresh records from
# their first entry, one entry per match, review at 10 settled, decide at 30. A missing market, rung or quote is a
# logged skip. Paper only: neither is a Production pair.
SIBLINGS = {
    "T1H": dict(name="T1-H", parent="T1", registered="2026-11-06", market="team", line=1.5, goals=2, side="yes",
                label="T1 matches, home team 2+ goals · YES",
                evidence="T1's first 48 forward bets: home 17/24 v 13.4 priced, +38.8% (z 1.58); away 11/24 v 11.2, −9.9%"),
    "T1M": dict(name="T1-M", parent="T1", registered="2026-11-06", market="total", line=3.5, side="yes",
                label="T1 matches, match over 3.5 · YES",
                evidence="both teams scored 2+ in 8 of T1's 24 matches (33%) v about 24% implied by the two team prices"),
}
LANES = tuple(RULES) + tuple(SIBLINGS)


# ---------- Kalshi ----------

LINE_RE = re.compile(r"over (\d+(?:\.\d+)?) goals", re.I)


def line_of(m):
    """The goals line from the market's own words. The ticker suffix is never read."""
    for text in (m.get("title"), m.get("yes_sub_title")):
        hit = LINE_RE.search(str(text or ""))
        if hit:
            return float(hit.group(1))
    return None


def side_of(ticker):
    """'home', 'away' or None: KXEPLTEAMTOTAL-26OCT18BOUSUN-BOU2 is about the home team."""
    parts = str(ticker).split("-")
    if len(parts) < 3 or len(parts[1]) <= 7:
        return None
    pair, code = parts[1][7:], re.sub(r"[^A-Z]", "", parts[-1].upper())
    if not code or code == pair:
        return None
    if pair.startswith(code):
        return "home"
    if pair.endswith(code):
        return "away"
    return None


def market_for(ev, team, line):
    """The open market on `team` ('home'/'away') at `line`, or None."""
    for m in ev.get("markets") or []:
        if m.get("status") in ("active", "open") and side_of(m.get("ticker")) == team and line_of(m) == line:
            return m
    return None


def entry(rule, f, ev, m, team, px, b, a, labs, now):
    r = RULES[rule]
    own_lab, opp_lab = (labs[0], labs[1]) if team == "home" else (labs[1], labs[0])
    own, opp = (f["home"], f["away"]) if team == "home" else (f["away"], f["home"])
    return dict(id=f"{rule}:{ev['event_ticker']}:{team}", rule=rule, group=r["group"], league=f["league"],
                event=ev["event_ticker"], match=f"{f['home']} v {f['away']}", team=own, opponent=opp,
                team_side=team, start=f["kickoff"], ticker=m["ticker"], line=r["line"], side=r["side"],
                price=round(px, 4), bid=b, ask=a, title=m.get("title") or m.get("yes_sub_title"),
                sub=m.get("yes_sub_title"),
                logged=now.isoformat(), status="open", labels=dict(own=own_lab, opp=opp_lab),
                why=f"{own} {own_lab} v {opp} {opp_lab} · {r['goals']}+ {r['side'].upper()} {px:.2f}")


# Rules retired by hand (2026-10-31, Olu): no new entry from the dated day on (Eastern); the ledger rows
# stay and keep settling. T1, T5 and T7 (Production pairs) and the other rules behave exactly as before.
RETIRED = {
    "T6": dict(on="2026-10-31", reason="10 won, 5 lost at about 82c, −23.0% after fees on 15 bets; retired by Olu"),
    "T8": dict(on="2026-10-31", reason="3 won, 8 lost, −51.6% after fees on 11 bets; retired by Olu"),
    "T2": dict(on="2026-11-01", reason="4 won of 10, −21.8% after fees at the 10-bet review; research was +29%"),
}


def retired(rule, now):
    """True once `rule` is retired as of `now` (its dated day, Eastern, or later)."""
    r = RETIRED.get(rule)
    return bool(r) and now.astimezone(SR.ET).date().isoformat() >= r["on"]


def picks_for(f, labs, ev, now):
    out = []
    for team, own, opp in (("home", labs[0], labs[1]), ("away", labs[1], labs[0])):
        for rule in applicable(f["league"], own, opp):
            if retired(rule, now):
                continue
            r = RULES[rule]
            m = market_for(ev, team, r["line"])
            q = SR.quote(m) if m else None
            if not q:
                continue
            b, a = q
            px = a if r["side"] == "yes" else round(1 - b, 4)
            if PRICE_LO - 1e-9 <= px <= PRICE_HI + 1e-9:
                out.append(entry(rule, f, ev, m, team, px, b, a, labs, now))
    return out


def _skip(state, key, f, reason, now):
    """A sibling's logged skip for one match (kept to the latest 200)."""
    lane = state["rules"][key]
    skips = lane.setdefault("skips", {})
    skips[f"{f['home']} v {f['away']} · {f['kickoff']}"] = dict(match=f"{f['home']} v {f['away']}", league=f["league"],
                                                               start=f["kickoff"], reason=reason, at=now.isoformat())
    if len(skips) > 200:
        for k in sorted(skips, key=lambda k: skips[k]["at"])[:len(skips) - 200]:
            del skips[k]


def _quoted(m, what):
    """(bid, ask) for a YES at the ask inside the entry rules, or the skip reason."""
    if not m:
        return None, f"no open {what} market"
    q = SR.quote(m)
    if not q:
        return None, f"{what}: no quote with a spread of 5c or less"
    if not PRICE_LO - 1e-9 <= q[1] <= PRICE_HI + 1e-9:
        return None, f"{what}: ask {q[1]:.2f} outside 3-97c"
    return q, None


def t1h_pick(f, labs, ev, now):
    """T1-H on one T1 match: (entry or None, skip reason or None). Not a T1 match with T1 on the home side: (None, None)."""
    if "home" not in t1_sides(f["league"], labs):
        return None, None
    if not ev:
        return None, "no Kalshi team-total event for the match"
    m = market_for(ev, "home", SIBLINGS["T1H"]["line"])
    q, why = _quoted(m, "home team over 1.5")
    if not q:
        return None, why
    p = entry("T1", f, ev, m, "home", q[1], q[0], q[1], labs, now)
    p.update(id=f"T1H:{ev['event_ticker']}:home", rule="T1H")
    return p, None


def t1m_pick(f, labs, ev, now):
    """T1-M on one T1 match: (entry or None, skip reason or None); (None, None) when it is not a T1 match."""
    if not t1_sides(f["league"], labs):
        return None, None
    if not ev:
        return None, "no Kalshi match-total event for the match"
    m = SR.market_at(ev, SIBLINGS["T1M"]["line"])
    q, why = _quoted(m, "match over 3.5")
    if not q:
        return None, why if m else "no open over 3.5 rung on the match total"
    b, a = q
    return dict(id=f"T1M:{ev['event_ticker']}", rule="T1M", group="A", league=f["league"], event=ev["event_ticker"],
                match=f"{f['home']} v {f['away']}", start=f["kickoff"], ticker=m["ticker"], line=3.5, side="yes",
                price=round(a, 4), bid=b, ask=a, title=m.get("title") or m.get("yes_sub_title"), logged=now.isoformat(),
                status="open", labels=dict(home=labs[0], away=labs[1]),
                why=f"{f['home']} {labs[0]} v {f['away']} {labs[1]} · over 3.5 YES {a:.2f}"), None


# ---------- the run ----------

def due(fixtures, now):
    """Unplayed fixtures in the team rules' leagues kicking off 20-90 minutes from now."""
    out = []
    for f in fixtures:
        if f.get("played") or f.get("league") not in SERIES:
            continue
        t = D.instant(f.get("kickoff"))
        if t and WINDOW_MIN[0] * 60 <= (t - now).total_seconds() <= WINDOW_MIN[1] * 60:
            out.append(f)
    return out


def settle(state, now, fetch):
    """Kalshi's own result, profit per $100 after the fee (soccer_rules.settle, same ledger shape)."""
    return SR.settle(state, now, fetch)


def run(state, fixtures, now=None, fetch=D.get):
    now = now or dt.datetime.now(dt.timezone.utc)
    for k in LANES:
        state["rules"].setdefault(k, {"picks": []})
    seen = {p["id"] for lane in state["rules"].values() for p in lane["picks"]}
    log, errs, cache = [], [], {}
    stats = dict(due=0, labelled=0, candidates=0, matched=0)
    for f in due(fixtures, now):
        stats["due"] += 1
        labs = SR.labels(fixtures, f)
        if not all(labs):
            continue
        stats["labelled"] += 1
        if not (applicable(f["league"], labs[0], labs[1]) or applicable(f["league"], labs[1], labs[0])):
            continue
        stats["candidates"] += 1
        series = SERIES[f["league"]]
        try:
            if series not in cache:
                cache[series] = SR.series_events(series, fetch)
            ev = SR.find_event(f, cache[series])
            picks = []
            if ev:
                stats["matched"] += 1
                picks = picks_for(f, labs, ev, now)
            sib = [("T1H", lambda: t1h_pick(f, labs, ev, now))]
            if t1_sides(f["league"], labs):
                total = SR.SERIES.get(f["league"])
                if total and total not in cache:
                    cache[total] = SR.series_events(total, fetch)
                tev = SR.find_event(f, cache[total]) if total else None
                sib.append(("T1M", lambda: t1m_pick(f, labs, tev, now)))
            for key, pick in sib:
                p, why = pick()
                if p:
                    picks.append(p)
                elif why and not any(x["id"].startswith(key + ":") and x.get("match") == f"{f['home']} v {f['away']}"
                                     and x.get("start") == f["kickoff"] for x in state["rules"][key]["picks"]):
                    _skip(state, key, f, why, now)
            for p in picks:
                if p["id"] in seen:
                    continue
                state["rules"][p["rule"]]["picks"].append(p)
                seen.add(p["id"])
                log.append(p["id"])
                (state["rules"][p["rule"]].get("skips") or {}).pop(f"{f['home']} v {f['away']} · {f['kickoff']}", None)
        except Exception as e:                                  # noqa: BLE001
            errs.append(f"{f['home']} v {f['away']}: {str(e)[:80]}")
    errs += settle(state, now, fetch)
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
    for k, lane in state["rules"].items():
        if lane["picks"]:
            print(k, "picks", len(lane["picks"]), "open", sum(p["status"] == "open" for p in lane["picks"]))
    print("run", state["runs"][-1], "new", new, "error", state["error"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
