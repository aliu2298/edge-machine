"""Argentina & Brasileirão over 1.5 (2026-10-18): a Sandbox PAPER lane, `sa_o15`.

Paper only: not in Production, not in the Production feed, on its own fresh record
(data/sa_o15_ledger.json). Nothing is placed.

A LEAGUE-CHARACTER lane, like bund_o35: no form, no price band, no selection. It asks whether
Kalshi prices over 1.5 goals in these two leagues below how often it happens.

Research (Oct 18 2026, memory u35-low-scoring-review): over 1.5 YES at Kalshi's ask 30 minutes
before kickoff, every league match, Jan-Oct 2026:

    League                                    Record            Price   After fee   z       Halves
    Argentina (Liga Profesional)              64/86 (74%)       65c     +11.9%      +1.85   +17.2% / +6.7%
    Brasileirão                               43/57 (75%)       77c     -3.6%               +2.2% / -9.5%

Kalshi prices Argentine over 1.5 far cheaper than other leagues (75-88c), and the under 1.5 side
there lost 32%. The Brasileirão is about fair; it is tracked alongside as its own row so the two
are judged apart, never pooled.

PRE-REGISTERED RULE
1. Scope: every Kalshi league match in KXARGPREMDIVTOTAL and KXBRASILEIROTOTAL, nothing else.
2. Bet: YES on the over 1.5 rung. The line comes from the market TITLE ("Will over 1.5 goals be
   scored?"), never the ticker suffix (Kalshi renumbered soccer TOTAL suffixes between seasons).
3. Entry: 90 to 20 minutes before the ESPN kickoff (as soccer_rules), at the YES ask, spread 5c or
   less, fee 0.07 p (1 - p). One frozen entry per match.
4. Matching a Kalshi event ("Home vs Away: Total Goals") to its ESPN fixture: event date within a
   day of the kickoff, and BOTH names equal or whole-word contained (5+ characters) after
   normalising, with a short alias table for names that share no word (Paranaense = Athletico-PR).
   Never fuzzy, and a match two fixtures could claim is skipped: Argentina has two Estudiantes and
   two Gimnasias, and fuzzy matching put Man City on Man United in the contender research.
5. Settled on Kalshi's own result, profit per $100 after the fee. Rows per league: ARG and BRA.

It runs inside soccer-rules.yml on the soccer rules' lane window. Each run also writes the next
14 days of these leagues' kickoffs into its ledger ("schedule"), which is how the VPS, with no
ESPN cache of its own, knows when to ask for a read (lane_windows.sa_kickoffs).
"""
import datetime as dt
import json
import os
import re
import unicodedata

import daily_track as D
import soccer_rules as SR

ROOT = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(ROOT, "data", "sa_o15_ledger.json")
FEE = SR.FEE
WINDOW_MIN = SR.WINDOW_MIN       # (20, 90) minutes before kickoff
LINE = 1.5
NAME_MIN = 5
SCHEDULE_DAYS = 14
# ESPN league name (streaks_fetch) -> (row key, Kalshi match total series)
LEAGUES = {"Liga Profesional": ("ARG", "KXARGPREMDIVTOTAL"),
           "Brasileirão": ("BRA", "KXBRASILEIROTOTAL")}
ROWS = {
    "ARG": dict(league="Argentina", series="KXARGPREMDIVTOTAL",
                evidence="64/86 (74%) @65c, +11.9%, z +1.85 · halves +17.2% / +6.7%"),
    "BRA": dict(league="Brasileirão", series="KXBRASILEIROTOTAL",
                evidence="43/57 (75%) @77c, -3.6% · halves +2.2% / -9.5% · about fair, tracked alongside"),
}
# Kalshi short name -> ESPN name, normalised, for clubs whose two names share no whole word.
ALIASES = {"paranaense": "athletico pr", "atletico paranaense": "athletico pr",
           "atletico mineiro": "atletico mg", "racing avellaneda": "racing club"}


def fee(p):
    return FEE * p * (1 - p)


def load(path=PATH):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return {"version": "sa-o15-v1", "rules": {k: {"picks": []} for k in ROWS}, "runs": [], "schedule": []}


# ---------- names ----------

def norm(name):
    s = unicodedata.normalize("NFKD", str(name or "")).encode("ascii", "ignore").decode().lower()
    # "de" carries no name: Kalshi's "Belgrano de Cordoba" is ESPN's "Belgrano (Córdoba)".
    s = " ".join(w for w in re.sub(r"[^a-z0-9 ]", " ", s).split() if w != "de")
    return ALIASES.get(s, s)


def same_team(a, b):
    """Equal after normalising, or the shorter name (5+ characters) is whole words of the longer."""
    x, y = norm(a), norm(b)
    if not x or not y:
        return False
    if x == y:
        return True
    short, long_ = (x, y) if len(x) <= len(y) else (y, x)
    return len(short) >= NAME_MIN and f" {short} " in f" {long_} "


def event_teams(ev):
    """[home, away] from "Home vs Away: Total Goals", or the older "Away at Home: Totals"."""
    title = str(ev.get("title") or "").split(":")[0]
    parts = [p.strip() for p in re.split(r"\s+vs\.?\s+", title)]
    if len(parts) == 2:
        return parts
    parts = [p.strip() for p in re.split(r"\s+at\s+", title)]
    return parts[::-1] if len(parts) == 2 else None


def find_event(f, events, fixtures=()):
    """The Kalshi event for one ESPN fixture, or None.

    Date within a day of the kickoff, both names matching, home and away either way round. If the
    event would match another unplayed fixture of the same league as well, it is ambiguous and
    skipped rather than guessed."""
    if D.instant(f.get("kickoff")) is None:
        return None

    def fits(ev, fx):
        d, names = SR.event_date(ev.get("event_ticker")), event_teams(ev)
        k = D.instant(fx.get("kickoff"))
        if not d or not names or k is None or abs((d - k.astimezone(SR.ET).date()).days) > 1:
            return False
        return any(same_team(h, fx["home"]) and same_team(a, fx["away"])
                   for h, a in ((names[0], names[1]), (names[1], names[0])))

    hits = [ev for ev in events if fits(ev, f)]
    if len(hits) != 1:
        return None
    ev = hits[0]
    others = [x for x in fixtures if x is not f and x.get("league") == f.get("league") and not x.get("played")
              and (x.get("home"), x.get("away"), x.get("kickoff")) != (f.get("home"), f.get("away"), f.get("kickoff"))]
    if any(fits(ev, x) for x in others):
        return None
    return ev


# ---------- entries ----------

def pick_for(f, ev, now):
    key = LEAGUES[f["league"]][0]
    m = SR.market_at(ev, LINE)
    q = SR.quote(m) if m else None
    if not q:
        return None
    b, a = q
    return dict(id=f"{key}:{ev['event_ticker']}", rule=key, league=f["league"], event=ev["event_ticker"],
                match=f"{f['home']} v {f['away']}", start=f["kickoff"], ticker=m["ticker"], line=LINE,
                side="yes", price=round(a, 4), bid=b, ask=a, title=m.get("title") or m.get("yes_sub_title"),
                logged=now.isoformat(), status="open", why=f"{ROWS[key]['league']} over {LINE} YES {a:.2f}")


def due(fixtures, now):
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
    for k in ROWS:
        state["rules"].setdefault(k, {"picks": []})
    seen = {p["id"] for lane in state["rules"].values() for p in lane["picks"]}
    log, errs, totals = [], [], {}
    stats = dict(due=0, matched=0, quoted=0)
    for f in due(fixtures, now):
        stats["due"] += 1
        series = LEAGUES[f["league"]][1]
        try:
            if series not in totals:
                totals[series] = SR.series_events(series, fetch)
            ev = find_event(f, totals[series], fixtures)
            if not ev:
                continue
            stats["matched"] += 1
            p = pick_for(f, ev, now)
            if not p:
                continue
            stats["quoted"] += 1
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
