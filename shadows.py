"""Three SHADOW columns on existing over lanes (2026-11-21, Olu: "send the three shadows to sandbox"). Paper only, Sandbox.

No new selection and no change to any headline record: this module only READS the source lanes' ledgers and keeps its own
(data/shadows_soccer_ledger.json for A7, ARG, BRA; data/shadows_team_ledger.json for T1: each runs in its source lane's workflow, right after it).

1) btts2h  2H BTTS YES on T1 (soccer_team_rules) and A7 (soccer_rules): at the entry minute, the YES ask on the league's second-half BTTS
            (series prefix + 2HBTTS), spread 3c or less, else "no quote". One per MATCH (T1 can pick two teams in one match). Held to settlement.
   btts     BTTS YES on sa_o15 ARG (KXARGPREMDIVBTTS) and BRA (KXBRASILEIROBTTS), same rule and spread. Held. BRA has no in-sample figure.
2) ht       Half-time check on T1, A7 and sa_o15 ARG + BRA. At half-time: A7 / ARG / BRA, 0-0 => "sell" at the over's YES bid (minus fee),
            else "hold"; T1, the backed team has not scored by half-time => "sell" at that team-total YES bid, else "hold". No bid => "no bid",
            treated as hold. Shadow return = the sell proceeds for sell rows, the settled result for hold rows, shown beside the hold return.
HALF-TIME DATA: ESPN's match summary keyEvents (the "halftime" event's wall clock; period-1 scoring plays by team) and Kalshi's 1-minute candles
(yes_bid close of the minute ending at that instant). Read after the match, so no live feed is needed; a match ESPN cannot give is "unavailable".
Prices and fees as everywhere: ask paid, taker fee 0.07 p (1 - p) on the entry and on a sell. Percentages only on the page.
"""
import datetime as dt
import json
import os
import urllib.parse

import daily_track as D
import settle_only
import soccer_rules as SR

REGISTERED = "2026-11-21"
MAX_SPREAD = 0.03
MAX_AGE_MIN = 25                 # a source pick logged longer ago than this is not "the entry minute" any more
HT_AFTER_MIN = 75                # half-time data is read once the match is at least this old
GIVE_UP_H = 12                   # then the half is "unavailable"
UTC = dt.timezone.utc
FEE = SR.fee

LANES = {
    "T1": dict(group="team", ledger="soccer_team_rules_ledger.json", rule="T1", kind="2h", ht="team",
               in_sample=dict(btts="14-13 at 43c, +17%", ht="the backed team scoreless at half-time won 6 of 24")),
    "A7": dict(group="soccer", ledger="soccer_rules_ledger.json", rule="A7", kind="2h", ht="zero",
               in_sample=dict(btts="9-8 at 38c, +35%", ht="0-0 at half-time came good 0 of 4")),
    "ARG": dict(group="soccer", ledger="sa_o15_ledger.json", rule="ARG", kind="full", ht="zero", series="KXARGPREMDIVBTTS",
                in_sample=dict(btts="18-14 at 47c, +15%", ht="0-0 at half-time came good 4 of 9")),
    "BRA": dict(group="soccer", ledger="sa_o15_ledger.json", rule="BRA", kind="full", ht="zero", series="KXBRASILEIROBTTS",
                in_sample=dict(btts=None, ht=None)),
}
GROUPS = {"soccer": os.path.join(SR.ROOT, "data", "shadows_soccer_ledger.json"), "team": os.path.join(SR.ROOT, "data", "shadows_team_ledger.json")}


def load(group, path=None):
    path = path or GROUPS[group]
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return {"version": "shadows-v1", "group": group, "registered": REGISTERED, "btts": {}, "ht": {}, "runs": []}


def source_picks(lane, root=SR.ROOT):
    meta = LANES[lane]
    try:
        with open(os.path.join(root, "data", meta["ledger"])) as f:
            return (json.load(f).get("rules", {}).get(meta["rule"]) or {}).get("picks") or []
    except (OSError, ValueError):
        return []


def _quote(m):
    """(bid, ask) or None: an ask under 1, a bid of 0 or more, a spread of 3c or less, an open market."""
    if not m or m.get("status") not in ("active", "open"):
        return None
    b, a = D.number(m.get("yes_bid_dollars")), D.number(m.get("yes_ask_dollars"))
    if a is None or not 0 < a < 1 or b is None or b < 0 or a - b > MAX_SPREAD + 1e-9:
        return None
    return b, a


def fixture_of(p):
    home, _, away = str(p.get("match") or "").partition(" v ")
    return dict(home=home, away=away, kickoff=p.get("start"), league=p.get("league"))


def btts_series(lane, p):
    meta = LANES[lane]
    if meta["kind"] == "full":
        return meta["series"]
    return SR.SERIES[p["league"]][:-len("TOTAL")] + "2HBTTS"


def btts_record(lane, p, events, now):
    """The BTTS YES quote at the entry minute for the pick's match, or a "no quote" record."""
    f = fixture_of(p)
    ev = SR.find_event(f, events)
    base = dict(lane=lane, event=p["event"], match=p["match"], start=p["start"], recorded=now.isoformat(), kind=LANES[lane]["kind"], status="open")
    m = next((x for x in (ev or {}).get("markets") or [] if str(x.get("ticker") or "").endswith("-BTTS")), None)
    q = _quote(m)
    if not q:
        return dict(base, quote=False)
    return dict(base, quote=True, ticker=m["ticker"], price=round(q[1], 4), bid=q[0])


def settle_btts(r, now, fetch=D.get):
    if not r.get("quote") or r["status"] != "open":
        return
    m = fetch("markets/" + urllib.parse.quote(r["ticker"], safe="")).get("market", {})
    if m.get("ticker") != r["ticker"]:
        raise ValueError("settlement ticker mismatch")
    px = D.payout(m)
    if px is None:
        return
    r.update(payout=px, profit=round(100 * (px / (r["price"] + FEE(r["price"])) - 1), 2),
             status="won" if px == 1 else "lost" if px == 0 else "no_result", settled=now.isoformat())


# ---------- half-time ----------

def espn_half(fx, get):
    """{ht_ts, goals: {team_id: period-1 goals}} for a fixture from ESPN, or None. `get` fetches an ESPN JSON url."""
    import streaks_fetch as S
    ko = D.instant(fx.get("kickoff"))
    if not ko:
        return None
    ids = {str(fx.get("home_id")), str(fx.get("away_id"))}
    eid = None
    for d in (ko, ko - dt.timedelta(days=1)):
        sb = get(f"{S.HOST}/apis/site/v2/sports/soccer/{fx['league_slug']}/scoreboard?dates={d:%Y%m%d}")
        for e in sb.get("events") or []:
            comp = (e.get("competitions") or [{}])[0]
            if {str((c.get("team") or {}).get("id")) for c in comp.get("competitors") or []} == ids:
                eid = e.get("id")
        if eid:
            break
    if not eid:
        return None
    s = get(f"{S.HOST}/apis/site/v2/sports/soccer/{fx['league_slug']}/summary?event={eid}")
    ht_ts, goals = None, {i: 0 for i in ids}
    for k in s.get("keyEvents") or []:
        typ = (k.get("type") or {}).get("type")
        if typ == "halftime" and k.get("wallclock"):
            ht_ts = int(D.instant(k["wallclock"]).timestamp())
        if k.get("scoringPlay") and (k.get("period") or {}).get("number") == 1:
            tid = str((k.get("team") or {}).get("id"))
            if tid in goals:
                goals[tid] += 1
    return dict(ht_ts=ht_ts, goals=goals) if ht_ts else None


def bid_at(ticker, ts, fetch):
    """The market's YES bid (close) of the minute ending at or just before `ts`, or None."""
    series = ticker.split("-")[0]
    d = fetch(f"series/{series}/markets/{urllib.parse.quote(ticker, safe='')}/candlesticks?start_ts={ts - 600}&end_ts={ts + 60}&period_interval=1")
    best = None
    for c in d.get("candlesticks") or []:
        end = c.get("end_period_ts")
        b = D.number((c.get("yes_bid") or {}).get("close_dollars"))
        if end is not None and end <= ts + 30 and b is not None:
            best = (end, b) if best is None or end > best[0] else best
    return best[1] if best else None


def ht_decision(lane, p, half, fx):
    """(score text, backed/total goals, scoreless) from the half-time data."""
    g = half["goals"]
    if LANES[lane]["ht"] == "team":
        tid = str(fx["home_id"] if p.get("team_side") == "home" else fx["away_id"])
        return f"{g.get(str(fx['home_id']), 0)}-{g.get(str(fx['away_id']), 0)}", g.get(tid, 0) == 0
    return f"{g.get(str(fx['home_id']), 0)}-{g.get(str(fx['away_id']), 0)}", sum(g.values()) == 0


def resolve_ht(lane, p, r, fixtures, now, fetch=D.get, get=None):
    """Fill one pending half-time record once the match is old enough. A sell row's profit is final here; hold rows read the source pick later."""
    start = D.instant(p.get("start"))
    if not start or (now - start).total_seconds() < HT_AFTER_MIN * 60 or r["status"] != "pending":
        return
    fx = next((x for x in fixtures if x.get("league") == p.get("league") and x.get("kickoff") == p.get("start")
               and f"{x.get('home')} v {x.get('away')}" == p.get("match")), None)
    half = None
    if fx:
        half = espn_half(fx, get)
    if not half:
        if (now - start).total_seconds() > GIVE_UP_H * 3600:
            r["status"] = "unavailable"
        return
    score, scoreless = ht_decision(lane, p, half, fx)
    r.update(ht_ts=half["ht_ts"], score=score, scoreless=scoreless)
    if not scoreless:
        r.update(status="done", action="hold")
        return
    bid = bid_at(p["ticker"], half["ht_ts"], fetch)
    if not bid or bid <= 0:
        r.update(status="done", action="no_bid")
        return
    cost = float(p["price"]) + FEE(float(p["price"]))
    r.update(status="done", action="sell", bid=bid, profit=round(100 * ((bid - FEE(bid)) / cost - 1), 2))


def run(state, group, fixtures, now=None, fetch=D.get, get=None, events=None):
    """One pass for a group: record the entry-minute quotes of new source picks, settle, resolve half-times."""
    now = now or dt.datetime.now(UTC)
    errs, cache = [], {}
    new_entries = not settle_only.on()
    for lane, meta in LANES.items():
        if meta["group"] != group:
            continue
        for p in source_picks(lane):
            logged = D.instant(p.get("logged"))
            if not logged or logged.date().isoformat() < REGISTERED:
                continue
            key = f"{lane}:{p['event']}"
            fresh = (now - logged).total_seconds() <= MAX_AGE_MIN * 60
            try:
                if new_entries and fresh and key not in state["btts"]:
                    series = btts_series(lane, p)
                    if series not in cache:
                        cache[series] = (events or (lambda s: SR.series_events(s, fetch)))(series)
                    state["btts"][key] = btts_record(lane, p, cache[series], now)
                if new_entries and fresh and p["id"] not in state["ht"]:
                    state["ht"][p["id"]] = dict(lane=lane, pick=p["id"], match=p["match"], start=p["start"], status="pending", price=p["price"])
            except Exception as e:                              # noqa: BLE001
                errs.append(f"{p['id']}: {str(e)[:70]}")
    for r in state["btts"].values():
        try:
            settle_btts(r, now, fetch)
        except Exception as e:                                  # noqa: BLE001
            errs.append(f"btts {r['event']}: {str(e)[:70]}")
    byid = {p["id"]: p for lane in LANES for p in source_picks(lane)}
    for pid, r in state["ht"].items():
        p = byid.get(pid)
        if not p:
            continue
        try:
            resolve_ht(r["lane"], p, r, fixtures, now, fetch, get)
        except Exception as e:                                  # noqa: BLE001
            errs.append(f"ht {pid}: {str(e)[:70]}")
        if r["status"] == "done" and r.get("action") != "sell" and p.get("status") in ("won", "lost", "no_result"):
            r["profit"] = p.get("profit")                       # a hold row ends on the settled result
            r["settled"] = True
    state["last_run"] = now.isoformat()
    state["error"] = "; ".join(errs)[:800] or None
    state["runs"] = (state.get("runs") or [])[-50:] + [dict(at=now.isoformat(), btts=len(state["btts"]), ht=len(state["ht"]))]
    return state


# ---------- records ----------

def btts_stats(state, lane):
    rows = [r for r in state["btts"].values() if r["lane"] == lane]
    priced = [r for r in rows if r.get("quote")]
    done = [r for r in priced if r["status"] in ("won", "lost", "no_result")]
    return dict(matches=len(rows), no_quote=len(rows) - len(priced), won=sum(r["status"] == "won" for r in done), lost=sum(r["status"] == "lost" for r in done),
                avg_price=(sum(r["price"] for r in priced) / len(priced)) if priced else None,
                ret=(sum(r["profit"] for r in done) / (100 * len(done))) if done else None)


def ht_stats(state, lane, picks):
    """Checked, sold, held, no bid, the shadow return and the hold return on the same finished rows."""
    byid = {p["id"]: p for p in picks}
    rows = [r for r in state["ht"].values() if r["lane"] == lane and r["status"] == "done"]
    fin = [r for r in rows if r.get("profit") is not None and byid.get(r["pick"])]
    hold = [byid[r["pick"]].get("profit") for r in fin if byid[r["pick"]].get("profit") is not None]
    return dict(checked=len(rows), sold=sum(r.get("action") == "sell" for r in rows), held=sum(r.get("action") == "hold" for r in rows),
                no_bid=sum(r.get("action") == "no_bid" for r in rows), pending=sum(r["status"] == "pending" for r in state["ht"].values() if r["lane"] == lane),
                avg_price=(sum(float(r["price"]) for r in fin) / len(fin)) if fin else None,
                ret=(sum(r["profit"] for r in fin) / (100 * len(fin))) if fin else None,
                hold_ret=(sum(hold) / (100 * len(hold))) if hold else None)


def save(state, group):
    path = GROUPS[group]
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f, indent=1, sort_keys=True)
        f.write("\n")
    os.replace(tmp, path)


def main(argv=None):
    import sys
    import streaks_fetch
    group = (argv if argv is not None else sys.argv[1:])[0]
    state = load(group)
    fixtures = streaks_fetch.load_or_fetch()["fixtures"]
    run(state, group, fixtures, get=streaks_fetch.get)
    save(state, group)
    print(group, state["runs"][-1], "error", state["error"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
