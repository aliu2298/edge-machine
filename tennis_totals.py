#!/usr/bin/env python3
"""ATP total games · low rung · OVER (2026-10-21): a Sandbox PAPER lane, `tennis_atp_low_over`.

Paper only: not in Production, not in the Production feed, no PAIR_OVERRIDES entry, on its own fresh record
(data/tennis_totals_ledger.json). Nothing is placed.

PRE-REGISTERED 2026-10-21. Research on Kalshi KXATPGTOTAL quotes 30 minutes before the ESPN start,
ATP main tour, Jul 31-Oct 17 2026, spread 5c or less. The over on rungs at or below 19.5 games went
59/65 (64 matches), 91% @84c, +6.5% after fee, z +1.48. Aug 15/17 +2%, Sep-Oct 44/48 +8%. Results
agreed with ESPN on 100% of totals. Caveats: z under 2; a thin payoff (one loss costs about 5-6
wins); a smaller ATP sample in August; and an earlier version of this idea (ATP low rung YES) went
5/8 in an August holdout. Read at 30 settled entries; Olu reviews at 10+.

THE RULE
1. Scope: Kalshi's ATP men's singles total-games ladders, series KXATPGTOTAL, nothing else. That
   series is the ATP main tour (Kalshi files Challenger, WTA and doubles under other series), and a
   market whose rules name a Challenger event is refused as well. Start times come from ESPN's ATP
   scoreboard, men's singles only, and only a start ESPN marks as a real time (timeValid): a
   placeholder midnight for an unscheduled day is not a start.
2. Rung: per match, the YES ("over") on the rung with the HIGHEST strike at or below 19.5 games:
   19.5 if it is listed, else 18.5, and so on. Rungs are N.5. A rung above 19.5 is never taken, and
   if the chosen rung fails the price or the spread the match has no entry (no fall back to a
   lower rung: the rung is chosen before its price is looked at).
3. Entry: 15 to 45 minutes before the ESPN start (inclusive), while ESPN still has the match as
   not started. One frozen entry per match (per Kalshi event).
4. Price: the YES ask, 0.70 to 0.92 inclusive. Liquidity: a two-sided quote (bid above 0, ask
   below 1) with spread at most 5c, the research filter. No depth floor, as the current tennis
   lanes (they read only the two-sided, tight quote); the size at the ask is recorded on each
   entry so a depth question can be answered later from the ledger.
5. Settled on Kalshi's official result, profit per $100 after the 7% taker fee 0.07 p (1 - p). A
   retirement or walkover Kalshi settles at a fair price is a no-result entry, kept in the ROI.
   One match per entry, so stats are per entry.
6. Blind baseline: the over on EVERY in-window KXATPGTOTAL rung at or below 19.5 with a YES ask of
   0.70-0.92 and the same two-sided 5c quote, one entry per rung. It shows whether choosing the
   highest such rung adds anything to backing the low rungs blind.

How it runs: tennis-totals.yml, asked for by the VPS from inside each start's window
(scripts/vps_window_requests.sh, lane_windows.tennis_windows), plus an hourly schedule that
settles. Each run writes the next day's valid ATP singles starts into the ledger ("schedule").
"""
import datetime as dt
import json
import os
import re
import unicodedata
import urllib.parse
import urllib.request

import daily_track as D

ROOT = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(ROOT, "data", "tennis_totals_ledger.json")
LANE = "tennis_atp_low_over"
BASE = "baseline"
REGISTERED = "2026-10-21"
SERIES = "KXATPGTOTAL"
MAX_STRIKE = 19.5
BAND = (0.70, 0.92)              # YES ask, both ends inclusive
WINDOW_MIN = (15, 45)            # minutes before the ESPN start, both ends inclusive
MAX_SPREAD = 0.05
FEE = 0.07
SCHEDULE_H = 36
EPS = 1e-9
ESPN = "https://site.api.espn.com/apis/site/v2/sports/tennis/atp/scoreboard"
MON = "JAN FEB MAR APR MAY JUN JUL AUG SEP OCT NOV DEC".split()
EVIDENCE = ("59/65 (64 matches), 91% @84c, +6.5% after fee, z +1.48 · Aug 15/17 +2% · Sep-Oct 44/48 +8%")
PREREG = (
    "PRE-REGISTERED 2026-10-21: research on Kalshi KXATPGTOTAL quotes 30 min before the ESPN start, "
    "ATP main tour, Jul 31-Oct 17 2026, spread ≤5c. The over on rungs ≤19.5 went 59/65 (64 matches), "
    "91% @84c, +6.5% after fee, z +1.48. Aug 15/17 +2%, Sep-Oct 44/48 +8%. Results agreed with ESPN on "
    "100% of totals. Caveats: z under 2, a thin payoff (one loss costs about 5-6 wins), a smaller ATP "
    "sample in August, and an earlier version of this idea (ATP low rung YES) went 5/8 in an August "
    "holdout. Read at 30 settled entries; Olu reviews at 10+.")
DEFINITION = (
    "Kalshi ATP men's singles total games (KXATPGTOTAL, ATP main tour only). Per match, back YES "
    "(over) on the rung with the highest strike at or below 19.5 games (19.5 if listed, else 18.5, "
    "and so on). Entry 15-45 minutes before the ESPN start, one frozen entry per match. YES ask "
    "0.70-0.92 inclusive, two-sided quote with spread ≤5c, no depth floor. Settled on Kalshi's "
    "official result after the 7% taker fee. Blind baseline: the over on every in-window rung ≤19.5 "
    "with ask 0.70-0.92 and the same quote. Paper, Sandbox only.")


def fee(p):
    return FEE * p * (1 - p)


def empty():
    return {"version": "tennis-totals-v1", "registered": REGISTERED,
            "rules": {LANE: {"picks": []}, BASE: {"picks": []}}, "runs": [], "schedule": []}


def load(path=PATH):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return empty()


# ---------- ESPN starts ----------

def http_json(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": "edge-machine-paper-tennis"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def espn_matches(now=None, fetch=http_json):
    """Men's singles matches on ESPN's ATP scoreboard for today and tomorrow (UTC), deduped by id.

    Each is {id, start, valid, state, players: [name, name], tournament}. Doubles are a different
    grouping and are never read."""
    now = now or dt.datetime.now(dt.timezone.utc)
    out = {}
    for day in (now.date(), now.date() + dt.timedelta(days=1)):
        d = fetch(f"{ESPN}?dates={day:%Y%m%d}")
        for e in d.get("events") or []:
            for g in e.get("groupings") or []:
                if (g.get("grouping") or {}).get("slug") != "mens-singles":
                    continue
                for c in g.get("competitions") or []:
                    if (c.get("type") or {}).get("slug", "mens-singles") != "mens-singles":
                        continue
                    names = [((x.get("athlete") or {}).get("displayName") or "") for x in c.get("competitors") or []]
                    out[str(c.get("id"))] = dict(
                        id=str(c.get("id")), start=c.get("startDate") or c.get("date"),
                        valid=bool(c.get("timeValid")),
                        state=((c.get("status") or {}).get("type") or {}).get("state"),
                        players=names, tournament=e.get("name"))
    return list(out.values())


def start_of(m):
    return D.instant(str(m.get("start") or "").replace("Z", "+00:00"))


def real_match(m):
    """Two named players and a start ESPN marks as a real time."""
    names = m.get("players") or []
    return (len(names) == 2 and all(n and n.strip().upper() != "TBD" for n in names)
            and bool(m.get("valid")) and start_of(m) is not None)


def schedule(matches, now):
    """Valid starts of unstarted ATP singles matches over the next SCHEDULE_H hours, ISO UTC, sorted."""
    out = set()
    for m in matches:
        t = start_of(m)
        if real_match(m) and m.get("state") == "pre" and now - dt.timedelta(hours=1) <= t <= now + dt.timedelta(hours=SCHEDULE_H):
            out.add(t.astimezone(dt.timezone.utc).isoformat())
    return sorted(out)


# ---------- names ----------

SUFFIX = {"jr", "sr", "ii", "iii", "iv"}


def tokens(name):
    s = unicodedata.normalize("NFKD", str(name or "")).encode("ascii", "ignore").decode().lower()
    return [w for w in re.sub(r"[^a-z ]", " ", s).split() if w not in SUFFIX]


def same_player(a, b):
    """Same surname (last word) and same first initial, or the same set of words (name order).

    "Martin Damm Jr" is ESPN's "Martin Damm"; "Francisco Cerundolo" is not "Juan Manuel Cerundolo"."""
    x, y = tokens(a), tokens(b)
    if not x or not y:
        return False
    if x == y or sorted(x) == sorted(y):
        return True
    return x[-1] == y[-1] and x[0][0] == y[0][0] and len(x[-1]) >= 3


def event_players(ev):
    title = str(ev.get("title") or "").split(":")[0]
    parts = [p.strip() for p in re.split(r"\s+vs\.?\s+", title)]
    return parts if len(parts) == 2 else None


def event_date(ticker):
    """KXATPGTOTAL-26OCT21DAMCER -> 2026-10-21 (the listing date; a postponed match keeps it)."""
    m = re.match(r"^[A-Z0-9]+-(\d{2})([A-Z]{3})(\d{2})", str(ticker))
    if not m or m.group(2) not in MON:
        return None
    return dt.date(2000 + int(m.group(1)), MON.index(m.group(2)) + 1, int(m.group(3)))


def atp_event(ev):
    """True for a KXATPGTOTAL event whose markets do not name a Challenger event."""
    if not str(ev.get("event_ticker") or "").startswith(SERIES + "-"):
        return False
    text = " ".join(str(m.get("rules_primary") or "") + " " + str(m.get("rules_secondary") or "")
                    for m in ev.get("markets") or [])
    return "challenger" not in text.lower()


def fits(ev, m):
    names, d, t = event_players(ev), event_date(ev.get("event_ticker")), start_of(m)
    if not names or not d or t is None or not real_match(m):
        return False
    # Listed a day or two ahead; a postponed match keeps its listing date (seen: Oct 18 -> Oct 21).
    if not -1 <= (t.date() - d).days <= 5:
        return False
    a, b = m["players"]
    return ((same_player(names[0], a) and same_player(names[1], b))
            or (same_player(names[0], b) and same_player(names[1], a)))


def find_event(m, events, matches=()):
    """The one Kalshi event for an ESPN match, or None. Ambiguous either way is skipped."""
    hits = [ev for ev in events if fits(ev, m)]
    if len(hits) != 1:
        return None
    others = [x for x in matches if x is not m and x.get("id") != m.get("id")]
    if any(fits(hits[0], x) for x in others):
        return None
    return hits[0]


# ---------- rungs and quotes ----------

LINE_RE = re.compile(r"over\s+(\d+(?:\.\d+)?)\s+games", re.I)


def strike(mk):
    """The rung's games line: floor_strike, else the title's "Over N.5 games". N.5 only."""
    v = D.number(mk.get("floor_strike"))
    if v is None:
        for text in (mk.get("yes_sub_title"), mk.get("title")):
            hit = LINE_RE.search(str(text or ""))
            if hit:
                v = float(hit.group(1))
                break
    if v is None or abs((v % 1) - 0.5) > EPS:
        return None
    if mk.get("strike_type") not in (None, "", "greater"):
        return None
    return v


def rungs(ev):
    """[(strike, market)] for the event's active over rungs, lowest first."""
    out = []
    for mk in ev.get("markets") or []:
        if str(mk.get("status") or "").lower() not in ("active", "open"):
            continue
        s = strike(mk)
        if s is not None:
            out.append((s, mk))
    return sorted(out, key=lambda x: (x[0], str(x[1].get("ticker"))))


def low_rung(ev):
    """The rung with the highest strike at or below MAX_STRIKE, or None."""
    low = [x for x in rungs(ev) if x[0] <= MAX_STRIKE + EPS]
    return low[-1] if low else None


def quote(mk):
    """(bid, ask) for a two-sided YES quote with spread at most 5c, else None."""
    b, a = D.number(mk.get("yes_bid_dollars")), D.number(mk.get("yes_ask_dollars"))
    if b is None or a is None or not 0 < b < a < 1 or a - b > MAX_SPREAD + EPS:
        return None
    return b, a


def in_band(a):
    return BAND[0] - EPS <= a <= BAND[1] + EPS


def in_window(m, now):
    t = start_of(m)
    if t is None:
        return False
    lead = (t - now).total_seconds()
    return WINDOW_MIN[0] * 60 <= lead <= WINDOW_MIN[1] * 60


def entry(rule, ev, m, s, mk, b, a, now):
    t = start_of(m)
    eid = f"{LANE}:{ev['event_ticker']}" if rule == LANE else f"{BASE}:{mk['ticker']}"
    return dict(id=eid, rule=rule, event=ev["event_ticker"], ticker=mk["ticker"], line=s, side="yes",
                match=" v ".join(m["players"]), espn_id=m.get("id"), tournament=m.get("tournament"),
                start=t.astimezone(dt.timezone.utc).isoformat(), lead_min=round((t - now).total_seconds() / 60, 1),
                price=round(a, 4), bid=b, ask=a, ask_size=D.number(mk.get("yes_ask_size_fp")),
                title=mk.get("yes_sub_title") or mk.get("title"), logged=now.isoformat(), status="open",
                why=f"over {s} YES {a:.2f}")


def picks_for(ev, m, now):
    """(lane entry or None, [baseline entries]) for one matched, in-window match."""
    lane = None
    low = low_rung(ev)
    if low:
        s, mk = low
        q = quote(mk)
        if q and in_band(q[1]):
            lane = entry(LANE, ev, m, s, mk, q[0], q[1], now)
    base = []
    for s, mk in rungs(ev):
        if s > MAX_STRIKE + EPS:
            continue
        q = quote(mk)
        if q and in_band(q[1]):
            base.append(entry(BASE, ev, m, s, mk, q[0], q[1], now))
    return lane, base


def due(matches, now):
    return [m for m in matches if real_match(m) and m.get("state") == "pre" and in_window(m, now)]


# ---------- settlement ----------

def settle(state, now, fetch):
    errs = []
    for lane in state["rules"].values():
        for row in lane["picks"]:
            if row["status"] != "open":
                continue
            try:
                mk = fetch("markets/" + urllib.parse.quote(row["ticker"], safe="")).get("market", {})
                pay = D.payout(mk)
                if pay is None:
                    continue
                row.update(payout=pay, profit=round(100 * (pay / (row["price"] + fee(row["price"])) - 1), 2),
                           status="won" if pay == 1 else "lost" if pay == 0 else "no_result", settled=now.isoformat())
            except Exception as e:                              # noqa: BLE001
                errs.append(row["id"] + ": " + str(e)[:80])
    return errs


def stats(picks):
    """n (won+lost), n_price (no result), won, expected (sum of prices, won+lost), z, roi_fee (all settled)."""
    wl = [p for p in picks if p["status"] in ("won", "lost")]
    done = wl + [p for p in picks if p["status"] == "no_result"]
    won = sum(p["status"] == "won" for p in wl)
    exp = sum(p["price"] for p in wl)
    var = sum(p["price"] * (1 - p["price"]) for p in wl)
    return dict(n=len(wl), n_price=len(done) - len(wl), won=won, expected=exp,
                z=(won - exp) / var ** 0.5 if var > 0 else 0.0,
                roi_fee=sum(p.get("profit") or 0 for p in done) / (100 * len(done)) if done else None,
                open=sum(p["status"] == "open" for p in picks))


# ---------- the run ----------

def run(state, matches, now=None, fetch=D.get):
    now = now or dt.datetime.now(dt.timezone.utc)
    for k in (LANE, BASE):
        state["rules"].setdefault(k, {"picks": []})
    seen = {p["id"] for lane in state["rules"].values() for p in lane["picks"]}
    log, errs = [], []
    st = dict(due=0, matched=0, entered=0, baseline=0)
    todo = due(matches, now)
    events = None
    if todo:
        try:
            events = [ev for ev in D.pages(f"events?series_ticker={SERIES}&status=open&limit=200&with_nested_markets=true",
                                           "events", fetch) if atp_event(ev)]
        except Exception as e:                                  # noqa: BLE001
            errs.append(f"{SERIES}: {str(e)[:80]}")
    for m in todo if events is not None else ():
        st["due"] += 1
        ev = find_event(m, events, matches)
        if not ev:
            continue
        st["matched"] += 1
        lane, base = picks_for(ev, m, now)
        if lane and lane["id"] not in seen:
            state["rules"][LANE]["picks"].append(lane)
            seen.add(lane["id"])
            log.append(lane["id"])
            st["entered"] += 1
        for p in base:
            if p["id"] not in seen:
                state["rules"][BASE]["picks"].append(p)
                seen.add(p["id"])
                st["baseline"] += 1
    errs += settle(state, now, fetch)
    state["schedule"] = schedule(matches, now)
    state["last_run"] = now.isoformat()
    state["error"] = "; ".join(errs)[:1000] or None
    state["runs"] = (state.get("runs") or [])[-50:] + [dict(at=now.isoformat(), new=len(log), **st)]
    return log


def board(matches, now=None, fetch=D.get):
    """What the scanner sees now: matched ATP matches with a rung at or below 19.5 (a probe, no writes)."""
    now = now or dt.datetime.now(dt.timezone.utc)
    events = [ev for ev in D.pages(f"events?series_ticker={SERIES}&status=open&limit=200&with_nested_markets=true",
                                   "events", fetch) if atp_event(ev)]
    out = []
    for m in matches:
        if not real_match(m) or m.get("state") != "pre":
            continue
        ev = find_event(m, events, matches)
        low = low_rung(ev) if ev else None
        if not low:
            continue
        q = quote(low[1])
        out.append(dict(match=" v ".join(m["players"]), start=m["start"], line=low[0],
                        bid=q[0] if q else None, ask=q[1] if q else None,
                        qualifies=bool(q and in_band(q[1]))))
    return sorted(out, key=lambda r: r["start"]), len(events)


def main(argv=None):
    import sys
    argv = sys.argv[1:] if argv is None else argv
    out = argv[argv.index("--out") + 1] if "--out" in argv else PATH
    now = dt.datetime.now(dt.timezone.utc)
    matches = espn_matches(now)
    if "--board" in argv:
        rows, n_ev = board(matches, now)
        print(f"{n_ev} open {SERIES} events; {len(rows)} ESPN-matched upcoming matches with a rung <= {MAX_STRIKE}")
        for r in rows:
            print(f"  {r['start']}  {r['match']:45} over {r['line']}  bid {r['bid']} ask {r['ask']}  "
                  f"{'IN BAND' if r['qualifies'] else '-'}")
        return 0
    state = load(out)
    new = run(state, matches, now)
    tmp = out + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f, indent=1, sort_keys=True)
        f.write("\n")
    os.replace(tmp, out)
    print("run", state["runs"][-1], "new", new, "schedule", len(state["schedule"]), "error", state["error"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
