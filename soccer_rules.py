"""Soccer total-goals label rules (2026-10-17): 21 Sandbox paper lanes on Kalshi match totals.

Registered by Olu on 674 matches, Aug 1 - Oct 17 2026, across 12 leagues and the Nations League
(research session 2026-10-17, memory soccer-totals-label-angles). Each team carries a label from
its last 10 COMPETITIVE matches before kickoff (ESPN, data/streaks_raw.json, only games already
played): O+ when it scores per match at least its league's mean goals per team, else O-; D+ when
it concedes at least that mean, else D-. The league mean is over the league's last 400
team-games before kickoff. Fewer than 6 prior matches, or fewer than 40 league team-games,
means no label and no entry. Label pairs are UNORDERED: home and away either way round, and
"v an O+ opponent" means the other team's O label is O+.

Paper only, at the Kalshi price with the 7% fee, settled on Kalshi's own result. Nothing here
is in Production and nothing is placed. One frozen entry per rule per match, taken 90 to 20
minutes before kickoff, inside the rule's price range, spread 5c or less. Over N buys YES at
the ask; Under N buys NO at 1 - the YES bid.

Group A — strong (repeats across leagues, or z >= +2)
  A1  MLS               O-D- v O-D+              Under 3.5  NO  50-75c   20/24, +30%, z +2.12
  A2  Bundesliga        O+D- v O+D-              Over 3.5   YES <=60c    8/8, +77%, z +2.63
  A3  La Liga           O-D- v O-D+              Under 3.5  NO  70-85c   8/8, +27%
  A4  Saudi Pro League  O+D- v O+D-              Over 2.5   YES <=75c    5/5, +42%
  A5  Nations League    either team O-           Under 3.5  NO  65-85c   39/41
  A6  Premier League    an O-D- team v an O+     Under 2.5  NO  <=55c    10/11
  A7  Champions League  either team O+D-         Over 3.5   YES <=55c    10/13
Group B — supported but thin
  B1  MLS               O-D+ v O-D+              Under 3.5  NO  45-70c
  B2  La Liga           O-D+ v O+D-              Over 3.5   YES <=45c
  B3  Eredivisie        an O+D- team v a D-      Over 3.5   YES <=55c
  B4  Scottish Prem     either team O-D-         Under 3.5  NO  60-75c
  B5  Premier League    O+D- v O+D-              Over 2.5   YES <=65c
  B6  Ligue 1           O+D- v O+D-              Over 2.5   YES <=75c
Group C — borderline (one league, z +1 to +1.9)
  C1  MLS               O+D- v O+D+              Over 3.5   YES <=50c
  C2  La Liga           O-D- v O+D-              Over 2.5   YES <=60c
  C3  Serie A           O+D- v O+D+              Over 2.5   YES <=60c
  C4  Serie A           O-D- v O+D-              Over 2.5   YES <=55c
  C5  Saudi Pro League  O-D+ v O-D+              Under 2.5  NO  <=50c
  C6  Ligue 1           an O-D- team v an O+     Under 2.5  NO  <=50c
  C7  Turkish Super Lig O-D+ v O+D-              Under 2.5  NO  <=50c
  C8  Nations League    O-D+ v O-D+              Under 2.5  NO  <=65c

The two patterns behind most of them: O+D- v O+D- goes over (Bundesliga 8/8 over 3.5, Saudi 5/5
over 2.5, EPL 5/7, Eredivisie 4/5 over 3.5, UCL 6/9 over 3.5), and O-D- v O-D+ stays under 3.5
(MLS 20/24, La Liga 8/8, Saudi 5/6, Scotland 3/3, Nations League 7/7). Kalshi totals overall
were about fair in that sample (overs -3%, unders lose to the fee).

THE LINE COMES FROM THE MARKET TITLE ("Will over 2.5 goals be scored?"), never the ticker:
Kalshi renumbered the suffix between seasons (May 2026 -4 meant over 4.5; Oct 2026 -2 means
over 1.5). Kalshi publishes no kickoff, so a match's kickoff is ESPN's, and an event
("Home vs Away: Total Goals") is tied to its ESPN fixture by date (within a day) and by name
similarity (difflib 0.45 or more on both names).
"""
import datetime as dt
import difflib
import json
import os
import re
import urllib.parse

import daily_track as D

ROOT = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(ROOT, "data", "soccer_rules_ledger.json")
FEE = 0.07
WINDOW_MIN = (20, 90)            # minutes before kickoff
MAX_SPREAD = 0.05
FORM_N, FORM_MIN = 10, 6         # last 10 competitive matches; at least 6
LEAGUE_N, LEAGUE_MIN = 400, 40   # league mean over the last 400 team-games; at least 40
NAME_MIN = 0.45
ET = D.ET
MON = "JAN FEB MAR APR MAY JUN JUL AUG SEP OCT NOV DEC".split()

# ESPN league name (streaks_fetch) -> Kalshi match total-goals series.
SERIES = {
    "Premier League": "KXEPLTOTAL", "La Liga": "KXLALIGATOTAL", "Bundesliga": "KXBUNDESLIGATOTAL",
    "Serie A": "KXSERIEATOTAL", "Ligue 1": "KXLIGUE1TOTAL", "Eredivisie": "KXEREDIVISIETOTAL",
    "Scottish Premiership": "KXSCOTTISHPREMTOTAL", "MLS": "KXMLSTOTAL",
    "Saudi Pro League": "KXSAUDIPLTOTAL", "Turkish Super Lig": "KXSUPERLIGTOTAL",
    "Champions League": "KXUCLTOTAL", "UEFA Nations League": "KXUEFANLTOTAL",
}
GROUPS = {"A": "Strong · repeats across leagues, or z ≥ +2",
          "B": "Supported but thin",
          "C": "Borderline · one league, z +1 to +1.9"}


def _r(league, test, line, side, lo, hi, words, evidence=""):
    return dict(league=league, test=test, line=line, side=side, lo=lo, hi=hi, evidence=evidence,
                label=f"{words} · {'Over' if side == 'yes' else 'Under'} {line} · "
                      f"{side.upper()} {'≤' + str(round(hi * 100)) if lo == 0 else f'{round(lo * 100)}-{round(hi * 100)}'}c")


# test: ("pair", x, y) = one team has x and the other has y, either way round;
#       ("either", x) = at least one team has x. A part is a full label ("O+D-"), an O half
#       ("O+") or a D half ("D-").
RULES = {
    "A1": _r("MLS", ("pair", "O-D-", "O-D+"), 3.5, "no", 0.50, 0.75, "O−D− v O−D+", "20/24, +30%, z +2.12"),
    "A2": _r("Bundesliga", ("pair", "O+D-", "O+D-"), 3.5, "yes", 0, 0.60, "O+D− v O+D−", "8/8, +77%, z +2.63"),
    "A3": _r("La Liga", ("pair", "O-D-", "O-D+"), 3.5, "no", 0.70, 0.85, "O−D− v O−D+", "8/8, +27%"),
    "A4": _r("Saudi Pro League", ("pair", "O+D-", "O+D-"), 2.5, "yes", 0, 0.75, "O+D− v O+D−", "5/5, +42%"),
    "A5": _r("UEFA Nations League", ("either", "O-"), 3.5, "no", 0.65, 0.85, "Either team O−", "39/41"),
    "A6": _r("Premier League", ("pair", "O-D-", "O+"), 2.5, "no", 0, 0.55, "An O−D− team v an O+ opponent", "10/11"),
    "A7": _r("Champions League", ("either", "O+D-"), 3.5, "yes", 0, 0.55, "Either team O+D−", "10/13"),
    "B1": _r("MLS", ("pair", "O-D+", "O-D+"), 3.5, "no", 0.45, 0.70, "O−D+ v O−D+"),
    "B2": _r("La Liga", ("pair", "O-D+", "O+D-"), 3.5, "yes", 0, 0.45, "O−D+ v O+D−"),
    "B3": _r("Eredivisie", ("pair", "O+D-", "D-"), 3.5, "yes", 0, 0.55, "An O+D− team v a D− opponent"),
    "B4": _r("Scottish Premiership", ("either", "O-D-"), 3.5, "no", 0.60, 0.75, "Either team O−D−"),
    "B5": _r("Premier League", ("pair", "O+D-", "O+D-"), 2.5, "yes", 0, 0.65, "O+D− v O+D−"),
    "B6": _r("Ligue 1", ("pair", "O+D-", "O+D-"), 2.5, "yes", 0, 0.75, "O+D− v O+D−"),
    "C1": _r("MLS", ("pair", "O+D-", "O+D+"), 3.5, "yes", 0, 0.50, "O+D− v O+D+"),
    "C2": _r("La Liga", ("pair", "O-D-", "O+D-"), 2.5, "yes", 0, 0.60, "O−D− v O+D−"),
    "C3": _r("Serie A", ("pair", "O+D-", "O+D+"), 2.5, "yes", 0, 0.60, "O+D− v O+D+"),
    "C4": _r("Serie A", ("pair", "O-D-", "O+D-"), 2.5, "yes", 0, 0.55, "O−D− v O+D−"),
    "C5": _r("Saudi Pro League", ("pair", "O-D+", "O-D+"), 2.5, "no", 0, 0.50, "O−D+ v O−D+"),
    "C6": _r("Ligue 1", ("pair", "O-D-", "O+"), 2.5, "no", 0, 0.50, "An O−D− team v an O+ opponent"),
    "C7": _r("Turkish Super Lig", ("pair", "O-D+", "O+D-"), 2.5, "no", 0, 0.50, "O−D+ v O+D−"),
    "C8": _r("UEFA Nations League", ("pair", "O-D+", "O-D+"), 2.5, "no", 0, 0.65, "O−D+ v O−D+"),
}


def fee(p):
    return FEE * p * (1 - p)


def load(path=PATH):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return {"version": "soccer-rules-v1", "rules": {k: {"picks": []} for k in RULES}, "runs": []}


# ---------- labels ----------

def _ko(f):
    return D.instant(f.get("kickoff"))


def _key(f, side):
    return str(f.get(f"{side}_id") or f.get(side))


def league_mean(fixtures, league, before):
    """Mean goals per team over the league's last 400 team-games before `before`, or None."""
    games = sorted(((t, f) for f in fixtures if f.get("league") == league and f.get("played")
                    and (t := _ko(f)) and t < before and f.get("home_goals") is not None), key=lambda x: x[0])
    goals = []
    for _t, f in reversed(games):
        goals += [f["home_goals"], f["away_goals"]]
        if len(goals) >= LEAGUE_N:
            break
    goals = goals[:LEAGUE_N]
    return sum(goals) / len(goals) if len(goals) >= LEAGUE_MIN else None


def form(fixtures, key, before):
    """(scored, conceded, n) per match over the team's last 10 competitive played matches."""
    games = []
    for f in fixtures:
        if not f.get("played") or not f.get("competitive") or f.get("home_goals") is None:
            continue
        t = _ko(f)
        if not t or t >= before:
            continue
        if _key(f, "home") == key:
            games.append((t, f["home_goals"], f["away_goals"]))
        elif _key(f, "away") == key:
            games.append((t, f["away_goals"], f["home_goals"]))
    games = sorted(games, key=lambda g: g[0])[-FORM_N:]
    if len(games) < FORM_MIN:
        return None
    return sum(g[1] for g in games) / len(games), sum(g[2] for g in games) / len(games), len(games)


def label(fixtures, key, league, before, mean=None):
    mean = league_mean(fixtures, league, before) if mean is None else mean
    fm = form(fixtures, key, before)
    if mean is None or fm is None:
        return None
    return ("O+" if fm[0] >= mean else "O-") + ("D+" if fm[1] >= mean else "D-")


def labels(fixtures, f):
    """(home label, away label) at kickoff, point in time, or (None, None)."""
    t = _ko(f)
    mean = league_mean(fixtures, f["league"], t) if t else None
    if mean is None:
        return None, None
    return (label(fixtures, _key(f, "home"), f["league"], t, mean),
            label(fixtures, _key(f, "away"), f["league"], t, mean))


def has(lab, part):
    if len(part) == 4:
        return lab == part
    return (lab[:2] if part[0] == "O" else lab[2:]) == part


def matches(test, a, b):
    if test[0] == "either":
        return has(a, test[1]) or has(b, test[1])
    _, x, y = test
    return (has(a, x) and has(b, y)) or (has(a, y) and has(b, x))


def applicable(league, a, b):
    if not a or not b:
        return []
    return [k for k, r in RULES.items() if r["league"] == league and matches(r["test"], a, b)]


# ---------- Kalshi ----------

LINE_RE = re.compile(r"over\s+(\d+(?:\.\d+)?)\s+goals", re.I)


def line_of(m):
    """The goals line from the market's own words. The ticker suffix is never read."""
    for text in (m.get("title"), m.get("yes_sub_title")):
        hit = LINE_RE.search(str(text or ""))
        if hit:
            return float(hit.group(1))
    return None


def quote(m):
    b, a = D.number(m.get("yes_bid_dollars")), D.number(m.get("yes_ask_dollars"))
    if b is None or a is None or not 0 < b < a < 1 or a - b > MAX_SPREAD + 1e-9:
        return None
    return b, a


def _norm(name):
    s = re.sub(r"[^a-z0-9 ]", " ", str(name).lower())
    s = re.sub(r"\b(fc|cf|sc|afc|ac|club|de|the)\b", " ", s)
    return " ".join(s.split())


# Kalshi names ESPN's spelling cannot reach. Most short forms (PSG, "Los Angeles F", Enschede)
# are already in the repo's soccer alias table, sandbox_sources._score.
ALIASES = {"al suqoor": "neom"}


def similar(a, b):
    """difflib on the cleaned names, or the repo's alias-aware soccer score, whichever is higher."""
    x, y = _norm(a), _norm(b)
    x, y = ALIASES.get(x, x), ALIASES.get(y, y)
    if not x or not y:
        return 0.0
    if x in y or y in x:
        return 1.0
    best = difflib.SequenceMatcher(None, x, y).ratio()
    try:
        import sandbox_sources
        best = max(best, sandbox_sources._score(a, b, "soccer"))
    except Exception:                                           # noqa: BLE001
        pass
    return best


def event_date(ticker):
    """KXEPLTOTAL-26OCT18BOUSUN -> 2026-10-18."""
    m = re.match(r"^[A-Z0-9]+-(\d{2})([A-Z]{3})(\d{2})", str(ticker))
    if not m or m.group(2) not in MON:
        return None
    return dt.date(2000 + int(m.group(1)), MON.index(m.group(2)) + 1, int(m.group(3)))


def event_teams(ev):
    title = str(ev.get("title") or "").split(":")[0]
    parts = [p.strip() for p in re.split(r"\s+vs\.?\s+", title)]
    return parts if len(parts) == 2 else None


def find_event(f, events):
    """The Kalshi event for one ESPN fixture: date within a day, both names 0.45 or closer."""
    t = _ko(f)
    day = t.astimezone(ET).date() if t else None
    best = None
    for ev in events:
        d, names = event_date(ev.get("event_ticker")), event_teams(ev)
        if not d or not names or day is None or abs((d - day).days) > 1:
            continue
        for h, a in ((names[0], names[1]), (names[1], names[0])):
            sh, sa = similar(h, f["home"]), similar(a, f["away"])
            if sh >= NAME_MIN and sa >= NAME_MIN and (best is None or sh + sa > best[0]):
                best = (sh + sa, ev)
    return best[1] if best else None


def market_at(ev, line):
    for m in ev.get("markets") or []:
        if line_of(m) == line and m.get("status") in ("active", "open"):
            return m
    return None


def entry(rule, f, ev, m, px, b, a, labs, now):
    r = RULES[rule]
    side = r["side"]
    return dict(id=f"{rule}:{ev['event_ticker']}", rule=rule, group=rule[0], league=f["league"],
                event=ev["event_ticker"], match=f"{f['home']} v {f['away']}", start=f["kickoff"],
                ticker=m["ticker"], line=r["line"], side=side, price=round(px, 4), bid=b, ask=a,
                title=m.get("title") or m.get("yes_sub_title"), logged=now.isoformat(), status="open",
                labels=dict(home=labs[0], away=labs[1]),
                why=f"{f['home']} {labs[0]} v {f['away']} {labs[1]} · "
                    f"{'Over' if side == 'yes' else 'Under'} {r['line']} {side.upper()} {px:.2f}")


def picks_for(f, labs, ev, now):
    out = []
    for rule in applicable(f["league"], *labs):
        r = RULES[rule]
        m = market_at(ev, r["line"])
        q = quote(m) if m else None
        if not q:
            continue
        b, a = q
        px = a if r["side"] == "yes" else round(1 - b, 4)
        if r["lo"] - 1e-9 <= px <= r["hi"] + 1e-9:
            out.append(entry(rule, f, ev, m, px, b, a, labs, now))
    return out


# ---------- the run ----------

def due(fixtures, now):
    """Unplayed fixtures in the rules' leagues kicking off 20-90 minutes from now."""
    out = []
    for f in fixtures:
        if f.get("played") or f.get("league") not in SERIES:
            continue
        t = _ko(f)
        if t and WINDOW_MIN[0] * 60 <= (t - now).total_seconds() <= WINDOW_MIN[1] * 60:
            out.append(f)
    return out


def series_events(series, fetch):
    return D.pages(f"events?series_ticker={series}&status=open&limit=200&with_nested_markets=true",
                   "events", fetch)


def settle(state, now, fetch):
    errs = []
    for lane in state["rules"].values():
        for row in lane["picks"]:
            if row["status"] != "open":
                continue
            try:
                m = fetch("markets/" + urllib.parse.quote(row["ticker"], safe="")).get("market", {})
                px = D.payout(m)
                if px is None:
                    continue
                pay = px if row["side"] == "yes" else 1 - px
                row.update(payout=pay, profit=round(100 * (pay / (row["price"] + fee(row["price"])) - 1), 2),
                           status="won" if pay == 1 else "lost" if pay == 0 else "no_result", settled=now.isoformat())
            except Exception as e:                              # noqa: BLE001
                errs.append(row["id"] + ": " + str(e)[:80])
    return errs


def run(state, fixtures, now=None, fetch=D.get):
    now = now or dt.datetime.now(dt.timezone.utc)
    for k in RULES:
        state["rules"].setdefault(k, {"picks": []})
    seen = {p["id"] for lane in state["rules"].values() for p in lane["picks"]}
    log, errs, cache = [], [], {}
    stats = dict(due=0, labelled=0, candidates=0, matched=0)
    for f in due(fixtures, now):
        stats["due"] += 1
        labs = labels(fixtures, f)
        if not all(labs):
            continue
        stats["labelled"] += 1
        if not applicable(f["league"], *labs):
            continue
        stats["candidates"] += 1
        series = SERIES[f["league"]]
        try:
            if series not in cache:
                cache[series] = series_events(series, fetch)
            ev = find_event(f, cache[series])
            if not ev:
                continue
            stats["matched"] += 1
            for p in picks_for(f, labs, ev, now):
                if p["id"] in seen:
                    continue
                state["rules"][p["rule"]]["picks"].append(p)
                seen.add(p["id"])
                log.append(p["id"])
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
