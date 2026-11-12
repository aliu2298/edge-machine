"""African qualifiers goals check (2026-11-12): a Sandbox PAPER observation lane, `africa_goals`.

Paper only. An observation lane: never in Production, no feed, nothing placed. Its own record
(data/africa_goals_ledger.json), from the Nov 12 2026 window on.

It is the forward read of docs/prereg_africa_goals_forward_2026-11-12.md, made visible (Olu, Nov 12 2026). On the one
window Kalshi had settled (48 AFCON qualifiers, Sep 24 to Oct 6 2026) the market expected too few goals. The rules below
are that document's, unchanged, and its three "held" conditions are still judged on the Nov 12 to 17 window.

THE THREE BETS, on every AFCON qualifier Kalshi lists (no selection):
    U35   NO  on KXAFCONTOTAL over 3.5 goals        September: 6.9 points overpriced on 48 matches
    O15   YES on KXAFCONTOTAL over 1.5 goals        September: 7.3 points underpriced on 48 matches
    T1    YES on KXAFCONTEAMTOTAL, each side's over 0.5 goals (rung 1)
                                                    September: 9.7 points underpriced on 91 sides

ENTRY: the ask on the HOURLY quote three hours before the ESPN kickoff: the last hourly candle that ends at or before
kickoff - 3h (and no more than six hours before that) with a two-sided quote. YES pays the ask; NO pays 1 - the bid. A
price outside 2c to 98c is not bet. Because the entry is that hourly quote, a run that comes late logs the same price as
a run on time. A bet logged after its kickoff is marked `backfilled` in the ledger.

FILLS AND FEES: the fill simulator's QUOTED rule (fillsim.py): the ask counts unless the trade prints refute it, read
on the prints between the entry and kickoff. A refuted entry is kept as "no fill" and is not in the record. The taker
fee is the exchange's.

CLUSTERS: a match day is one outcome (the score in `record` uses the wider of the per-bet and the per-day error).

MATCHING a Kalshi event to its ESPN fixture: both names equal after normalising (a short alias table, never fuzzy),
home and away either way round, and Kalshi's own kickoff estimate within six hours of ESPN's. The reverse fixture is
played four days later with the sides swapped, so the names alone are not enough.

It runs inside soccer-p4.yml, the hourly read the server already asks for. Nothing on the server changes.
"""
import dataclasses
import datetime as dt
import json
import os
import re
import unicodedata
import urllib.parse

import daily_track as D
import fillsim as F
import soccer_rules as SR

ROOT = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(ROOT, "data", "africa_goals_ledger.json")
UTC = dt.timezone.utc
TOTAL, TEAM = "KXAFCONTOTAL", "KXAFCONTEAMTOTAL"
SLUG, LEAGUE = "caf.nations_qual", "AFCON Qualifying"
FROM = "2026-11-12"                 # the fresh record: kickoffs on or after this UTC day
ENTRY_H = 3.0                       # hours before the ESPN kickoff
QUOTE_BACK_S = 6 * 3600             # the hourly quote may be this old at the entry, no older
QUOTE_LAG_S = 300                   # the hour's candle is read this long after the entry time, so it is final
PRICE_MIN, PRICE_MAX = 0.02, 0.98
KICK_BEFORE_EXPIRY_S = 4 * 3600     # Kalshi's totals expire about four hours after kickoff
KICK_SLACK_S = 6 * 3600
LOOK_BACK_DAYS, LOOK_AHEAD_DAYS = 10, 3
PREREG = "docs/prereg_africa_goals_forward_2026-11-12.md"

ROWS = {
    "U35": dict(label="NO on over 3.5 goals", market="Under 3.5", series=TOTAL, side="no", line=3.5, sport="soccer_u35_intl",
                lead="6.9 points overpriced on 48 matches", held="wins less often than its price"),
    "O15": dict(label="YES on over 1.5 goals", market="Over 1.5", series=TOTAL, side="yes", line=1.5, sport="soccer_o15_intl",
                lead="7.3 points underpriced on 48 matches", held="wins more often than its price"),
    "T1": dict(label="YES on each side to score", market="Team 1+", series=TEAM, side="yes", line=0.5, sport="soccer_team1_intl",
               lead="9.7 points underpriced on 91 sides", held="wins more often than its price, by 3 points or more"),
}
# Kalshi name -> ESPN name, normalised, where the two share no exact form.
ALIASES = {"congo republic": "congo", "republic of congo": "congo", "congo brazzaville": "congo",
           "dr congo": "congo dr", "democratic republic of congo": "congo dr", "cote d ivoire": "ivory coast",
           "cabo verde": "cape verde", "the gambia": "gambia", "swaziland": "eswatini"}
BAD_STATUS = ("POSTPONED", "CANCEL", "ABANDON", "SUSPEND", "DELAY", "FORFEIT")
TEAM_RE = re.compile(r"^(.*?)\s+over\s+0\.5\s+goals", re.I)


def load(path=PATH):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return {"version": "africa-goals-v1", "rules": {k: {"picks": []} for k in ROWS}, "skips": {}, "runs": []}


# ---------- names and fixtures ----------

def norm(name):
    s = unicodedata.normalize("NFKD", str(name or "")).encode("ascii", "ignore").decode().lower()
    s = " ".join(re.sub(r"[^a-z0-9 ]", " ", s).split())
    return ALIASES.get(s, s)


def same_team(a, b):
    x, y = norm(a), norm(b)
    return bool(x) and x == y


def fixture_of(ev):
    """One ESPN scoreboard event -> dict(home, away, kickoff), or None. A postponed or cancelled match is dropped; a match
    in play or finished is kept (its kickoff is still the fact the entry is timed from)."""
    try:
        comp = ev["competitions"][0]
        status = str(comp["status"]["type"]["name"]).upper()
        sides = {c["homeAway"]: c["team"]["displayName"] for c in comp["competitors"]}
        home, away = sides["home"], sides["away"]
    except (KeyError, IndexError, TypeError):
        return None
    k = D.instant(ev.get("date"))
    if k is None or any(w in status for w in BAD_STATUS):
        return None
    return dict(home=home, away=away, kickoff=k.astimezone(UTC).isoformat(), league=LEAGUE)


def fetch_fixtures(now, get=None):
    """ESPN's AFCON qualifier fixtures around `now`, read a month at a time (ESPN refuses date ranges)."""
    import streaks_fetch as SF
    get = get or SF.get
    lo, hi = now - dt.timedelta(days=LOOK_BACK_DAYS), now + dt.timedelta(days=LOOK_AHEAD_DAYS)
    out, seen = [], set()
    for key in sorted({lo.strftime("%Y%m"), hi.strftime("%Y%m")}):
        data = get(f"{SF.HOST}/apis/site/v2/sports/soccer/{SLUG}/scoreboard?dates={key}")
        for ev in data.get("events") or []:
            f = fixture_of(ev)
            if f and ev.get("id") not in seen:
                seen.add(ev.get("id"))
                out.append(f)
    return out


def event_kick(ev):
    """Kalshi's own kickoff estimate (epoch seconds) from the totals' expected expiry, or None."""
    for m in ev.get("markets") or []:
        t = D.instant(m.get("expected_expiration_time"))
        if t and SR.line_of(m) in (1.5, 3.5):
            return t.timestamp() - KICK_BEFORE_EXPIRY_S
    return None


def find_fixture(ev, fixtures):
    """The ESPN fixture of one Kalshi totals event, or None. Exactly one fixture may fit."""
    names, est = SR.event_teams(ev), event_kick(ev)
    if not names or est is None:
        return None
    hits = []
    for f in fixtures:
        k = D.instant(f.get("kickoff"))
        if k is None or abs(k.timestamp() - est) > KICK_SLACK_S:
            continue
        if any(same_team(h, f["home"]) and same_team(a, f["away"]) for h, a in ((names[0], names[1]), (names[1], names[0]))):
            hits.append(f)
    return hits[0] if len(hits) == 1 else None


# ---------- Kalshi reads ----------

def series_events(fetch):
    """Every KXAFCONTOTAL event Kalshi serves, open, closed or settled, with its markets."""
    out, errs = {}, []
    for status in ("open", "closed", "settled"):
        try:
            for ev in D.pages(f"events?series_ticker={TOTAL}&status={status}&with_nested_markets=true&limit=200", "events", fetch):
                out.setdefault(ev["event_ticker"], ev)
        except Exception as e:                                  # noqa: BLE001
            errs.append(f"events {status}: {str(e)[:80]}")
    return list(out.values()), errs


def team_markets(suffix, fetch):
    for path in (f"markets?event_ticker={TEAM}-{suffix}&limit=100", f"historical/markets?event_ticker={TEAM}-{suffix}&limit=100"):
        try:
            ms = fetch(path).get("markets") or []
            if ms:
                return ms
        except Exception:                                       # noqa: BLE001
            continue
    return []


def candles(series, ticker, lo, hi, fetch):
    """Hourly candles as [(end ts, bid, ask)], from the live endpoint or, once archived, the historical one."""
    tk = urllib.parse.quote(ticker, safe="")
    for path in (f"series/{series}/markets/{tk}/candlesticks", f"historical/markets/{tk}/candlesticks"):
        try:
            cs = fetch(f"{path}?start_ts={int(lo)}&end_ts={int(hi)}&period_interval=60").get("candlesticks") or []
        except Exception:                                       # noqa: BLE001
            continue
        if cs:
            def px(c, k):
                x = c.get(k) or {}
                return D.number(x.get("close_dollars", x.get("close")))
            return [(c.get("end_period_ts"), px(c, "yes_bid"), px(c, "yes_ask")) for c in cs]
    return []


def quote_at(cs, t):
    """(bid, ask, candle end) of the last hourly candle ending in (t - 6h, t + 60s] with a two-sided quote, or None."""
    best = None
    for e, b, a in cs or []:
        if e and t - QUOTE_BACK_S < e <= t + 60 and b is not None and a is not None and 0 < a <= 1 and 0 <= b < a:
            if best is None or e > best[2]:
                best = (b, a, e)
    return best


# ---------- entries ----------

def wanted(ev, fetch):
    """[(row key, series, market, team name or None)] for one Kalshi totals event: the two totals rungs by their own words,
    and each side's over 0.5 from the team-total board."""
    out = []
    for key in ("U35", "O15"):
        m = next((m for m in ev.get("markets") or [] if SR.line_of(m) == ROWS[key]["line"]), None)
        if m:
            out.append((key, TOTAL, m, None))
    for m in team_markets(ev["event_ticker"].split("-", 1)[1], fetch):
        hit = TEAM_RE.match(str(m.get("yes_sub_title") or ""))
        if hit:
            out.append(("T1", TEAM, m, hit.group(1).strip()))
    return out


def pick_for(key, series, m, team, f, ev, now, fetch):
    """(pick, None) or (None, why not). The entry is the hourly quote at kickoff - 3h, whenever the run comes."""
    k = D.instant(f["kickoff"])
    t = k.timestamp() - ENTRY_H * 3600
    q = quote_at(candles(series, m["ticker"], t - QUOTE_BACK_S - 3600, t + 60, fetch), t)
    if not q:
        return None, "no two-sided hourly quote at the entry"
    b, a, end = q
    side = ROWS[key]["side"]
    price = round(a if side == "yes" else 1 - b, 4)
    if not PRICE_MIN <= price <= PRICE_MAX:
        return None, f"price {price:.2f} outside 2c to 98c"
    return dict(id=f"{key}:{m['ticker']}", rule=key, league=LEAGUE, event=ev["event_ticker"], match=f"{f['home']} v {f['away']}",
                start=f["kickoff"], ticker=m["ticker"], series=series, line=ROWS[key]["line"], side=side, team=team,
                price=price, bid=b, ask=a, entry_at=dt.datetime.fromtimestamp(t, UTC).isoformat(),
                quote_end=dt.datetime.fromtimestamp(end, UTC).isoformat(),
                title=m.get("title") or m.get("yes_sub_title"), logged=now.isoformat(), backfilled=now > k,
                how="hourly quote 3h before kickoff" + (", logged after kickoff" if now > k else ""), status="open"), None


def due(f, now):
    k = D.instant(f.get("kickoff"))
    if k is None or k.astimezone(UTC).date().isoformat() < FROM:
        return False
    since = (now - k).total_seconds()
    return -(ENTRY_H * 3600 - QUOTE_LAG_S) <= since <= LOOK_BACK_DAYS * 86400


# ---------- settlement ----------

def _tape(ticker, fetch):
    import fillsim_tape as T
    return T.tape(ticker, fetch, settled=True)


def grade(row, pay, prints):
    """One settled bet under the QUOTED rule: the prints between the entry and kickoff may refute the ask."""
    t, k = D.instant(row["entry_at"]).timestamp(), D.instant(row["start"]).timestamp()
    rules = dataclasses.replace(F.QUOTED, entry_window_s=int(max(3600, k - t)))
    s = F.trade(prints, row["side"], dict(kind="taker", ts=t, price=row["price"]), [], payout=pay, rules=rules)
    if s["status"] != "settled":
        return dict(status="no_fill", fill="refuted", why=s.get("why"), payout=pay, profit=None)
    return dict(status="won" if pay == 1 else "lost" if pay == 0 else "no_result", fill=s["entry"]["status"], payout=pay,
                profit=round(100 * s["roi"], 2))


def settle(state, now, fetch, tape=_tape):
    errs, n = [], 0
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
                row.update(grade(row, pay, tape(row["ticker"], fetch)), settled=now.isoformat())
                n += 1
            except Exception as e:                              # noqa: BLE001
                errs.append(row["id"] + ": " + str(e)[:80])
    return n, errs


# ---------- the run ----------

def run(state, fixtures, now=None, fetch=D.get, tape=_tape):
    now = now or dt.datetime.now(UTC)
    for k in ROWS:
        state["rules"].setdefault(k, {"picks": []})
    skips = state.setdefault("skips", {})
    seen = {p["id"] for lane in state["rules"].values() for p in lane["picks"]}
    events, errs = series_events(fetch)
    log, unmatched = [], []
    stats = dict(events=0, matched=0, due=0, skipped=0)
    for ev in events:
        d = SR.event_date(ev.get("event_ticker"))
        if not d or d.isoformat() < FROM:
            continue
        stats["events"] += 1
        f = find_fixture(ev, fixtures)
        if not f:
            unmatched.append(str(ev.get("title") or ev.get("event_ticker"))[:60])
            continue
        stats["matched"] += 1
        if not due(f, now):
            continue
        stats["due"] += 1
        try:
            for key, series, m, team in wanted(ev, fetch):
                pid = f"{key}:{m['ticker']}"
                if pid in seen or pid in skips:
                    continue
                p, why = pick_for(key, series, m, team, f, ev, now, fetch)
                if not p:
                    skips[pid] = dict(why=why, match=f"{f['home']} v {f['away']}", at=now.isoformat())
                    stats["skipped"] += 1
                    continue
                state["rules"][key]["picks"].append(p)
                seen.add(pid)
                log.append(pid)
        except Exception as e:                                  # noqa: BLE001
            errs.append(f"{ev.get('event_ticker')}: {str(e)[:80]}")
    settled, serrs = settle(state, now, fetch, tape)
    errs += serrs
    state["last_run"] = now.isoformat()
    state["unmatched"] = unmatched[:40]
    state["error"] = "; ".join(errs)[:1000] or None
    state["runs"] = (state.get("runs") or [])[-50:] + [dict(at=now.isoformat(), new=len(log), settled=settled, **stats)]
    return log


# ---------- the record ----------

def picks_of(state, key=None):
    """One row's picks, or every pick (the combined row)."""
    rules = state.get("rules") or {}
    return [p for k in ([key] if key else list(ROWS)) for p in (rules.get(k) or {}).get("picks") or []]


def record(picks):
    """A row's record in the page template's shape, a match day counted as one outcome.

    n won + lost, n_price the no-result settles, roi_fee the mean return after fees, expected the summed price, excess the
    share won minus the mean price, z that excess over the wider of the per-bet and the per-match-day error. Open and
    no-fill bets are not in it."""
    done = [p for p in picks if p.get("status") in ("won", "lost", "no_result")]
    binary = [p for p in done if p["status"] in ("won", "lost")]
    n = len(binary)
    won = sum(p["status"] == "won" for p in binary)
    prices = [float(p["price"]) for p in binary]
    out = dict(n=n, n_price=len(done) - n, won=won, expected=sum(prices), n_bets=len(done), unit="bet", days=0, excess=None,
               price=(sum(prices) / n) if n else None, z=0.0,
               roi_fee=(sum(float(p.get("profit") or 0) for p in done) / (100 * len(done))) if done else None)
    if not n:
        return out
    x = [(p["status"] == "won") - float(p["price"]) for p in binary]
    mean = sum(x) / n
    # Each match day's summed (won - price) is one draw around zero when the prices are fair. Not demeaned: with every bet on
    # one day a demeaned sum is zero by construction, and the day would count for nothing.
    days = {}
    for p, v in zip(binary, x):
        day = str(p.get("start") or "")[:10]
        days[day] = days.get(day, 0.0) + v
    se = max(sum(q * (1 - q) for q in prices) ** 0.5 / n, sum(v * v for v in days.values()) ** 0.5 / n)
    return dict(out, days=len(days), excess=mean, z=(mean / se) if se else 0.0)


def main(argv=None):
    import sys
    argv = sys.argv[1:] if argv is None else argv
    out = argv[argv.index("--out") + 1] if "--out" in argv else PATH
    state = load(out)
    now = dt.datetime.now(UTC)
    try:
        fixtures = fetch_fixtures(now)
    except Exception as e:                                      # noqa: BLE001
        print("ESPN fixtures could not be read:", str(e)[:120])
        return 0
    new = run(state, fixtures, now)
    tmp = out + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f, indent=1, sort_keys=True)
        f.write("\n")
    os.replace(tmp, out)
    print("run", state["runs"][-1], "new", len(new), "unmatched", state["unmatched"], "error", state["error"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
