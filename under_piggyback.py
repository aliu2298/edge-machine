"""Favourite 1-0 (`fav_one_nil`) and Quiet First Half (`quiet_first_half`): two Sandbox PAPER lanes (2026-11-21). No Production, no live order.

Olu (Nov 21): "send fav 1-0 and quiet first half to sandbox". Both piggyback on the proved under rules A5 (Nations League u3.5), A6 (Premier League u2.5)
and C8 (Nations League u2.5). Whenever one of them would pick a match (its label filter AND its own under price band on the under's NO side at entry,
exactly as flipped_unders.selects), the lane logs ONCE per match, listing the source rules, at the same entry minute (20-90 min before kickoff).
Each lane has its own ledger and a fresh record from 2026-11-21. Review at 10 settled, decide at 30. Graded from Kalshi's settlement.

fav_one_nil  Kalshi correct score (league prefix + SCORE, e.g. KXEPLSCORE): the favourite winning 1-0. The favourite is the higher-priced team on the
             league's game market (prefix + GAME, mid of bid and ask) at entry; no entry if the two are within 2c. Buy YES at the ask; no entry if the
             spread is over 3c or there is no ask. Logs the fav and dog prices and the 0-0 and dog-1-0 asks (for later study).
quiet_first_half  Kalshi first-half BTTS (prefix + 1HBTTS): buy NO at the NO ask (1 - the YES bid), spread 3c or less. No entry when the match has no
             1H BTTS market.
In-sample (hindsight, never counted): fav 1-0 6 of 33 at about 14c, about +27% after fees held; quiet first half 40-1 at 81-87c (A5 26-1 +10%,
A6 10-0 +22%, C8 4-0 +17%).
fav_one_nil also carries a "sell at 2x" SHADOW (shadow_update): sold when a TRADE print reaches 2x the ask, shown beside the hold record.
In-sample for it: hold +27%, 2x +18%, 22 of 33 sold.
"""
import datetime as dt
import json
import os
import urllib.parse

import daily_track as D
import flipped_unders as FU
import o35_cheap_no as O35
import settle_only
import soccer_rules as SR

SOURCES = ("A5", "A6", "C8")
MAX_SPREAD = 0.03
FAV_GAP = 0.02
PREFIX = {lg: SR.SERIES[lg][:-len("TOTAL")] for lg in ("UEFA Nations League", "Premier League")}
LANES = {
    "fav_one_nil": dict(name="Favourite 1-0", suffix="SCORE", side="yes",
                        words="The favourite wins 1-0 (correct score), YES at the ask",
                        in_sample=dict(entries=33, won=6, lost=27, price="about 14c", ret="about +27%", note="held; 67% touched 2x in play", sold=22, shadow_ret="about +18%")),
    "quiet_first_half": dict(name="Quiet First Half", suffix="1HBTTS", side="no",
                             words="First-half BTTS NO at the NO ask",
                             in_sample=dict(entries=41, won=40, lost=1, price="81c to 87c", ret="A5 +10%, A6 +22%, C8 +17%", note="A5 26-1, A6 10-0, C8 4-0")),
}


def path(key):
    return os.path.join(SR.ROOT, "data", f"{key}_ledger.json")


def load(key, p=None):
    p = p or path(key)
    if os.path.exists(p):
        with open(p) as f:
            return json.load(f)
    return {"version": f"{key}-v1", "registered": "2026-11-21", "rules": {"PB": {"picks": []}}, "runs": []}


def selected(league, labs, total_ev, now):
    """The source rules that would pick this match now: label filter AND the under's price band on its NO side (flipped_unders.selects)."""
    out = []
    for k in SOURCES:
        r = SR.RULES[k]
        if SR.in_league(r, league) and SR.matches(r["test"], *labs) and FU.selects(k, SR.market_at(total_ev, r["line"])):
            out.append(k)
    return out


def _quote(m):
    """(bid, ask) or None: an ask, a bid at or above 0, a spread of 3c or less."""
    if not m or m.get("status") not in ("active", "open"):
        return None
    b, a = D.number(m.get("yes_bid_dollars")), D.number(m.get("yes_ask_dollars"))
    if a is None or not 0 < a < 1 or b is None or b < 0 or a - b > MAX_SPREAD + 1e-9:
        return None
    return b, a


def favourite(game_ev):
    """(fav_code, dog_code, fav_mid, dog_mid) from the game market, or None when a side has no quote or the two are within 2c."""
    mids = {}
    for m in game_ev.get("markets") or []:
        code = str(m.get("ticker") or "").rsplit("-", 1)[-1]
        b, a = D.number(m.get("yes_bid_dollars")), D.number(m.get("yes_ask_dollars"))
        if code == "TIE" or a is None or b is None or not 0 < a < 1:
            continue
        mids[code] = (b + a) / 2
    if len(mids) != 2:
        return None
    (c1, m1), (c2, m2) = sorted(mids.items(), key=lambda x: -x[1])
    return None if m1 - m2 < FAV_GAP - 1e-9 else (c1, c2, round(m1, 4), round(m2, 4))


def score_ticker(score_ev, fav, other, goals_fav, goals_other):
    """The correct-score market ticker: the codes come in the event's own order (home first)."""
    tail = str(score_ev["event_ticker"]).rsplit("-", 1)[-1][7:]
    if tail == fav + other:
        mid = f"{fav}{goals_fav}{other}{goals_other}"
    elif tail == other + fav:
        mid = f"{other}{goals_other}{fav}{goals_fav}"
    else:
        return None
    return f"{score_ev['event_ticker']}-{mid}"


def _market(ev, ticker):
    return next((m for m in ev.get("markets") or [] if m.get("ticker") == ticker), None)


def base_pick(key, f, labs, ev_total, srcs, now):
    return dict(id=f"{key}:{ev_total['event_ticker']}", rule="PB", sources=srcs, league=f["league"], event=ev_total["event_ticker"],
                match=f"{f['home']} v {f['away']}", start=f["kickoff"], logged=now.isoformat(), status="open",
                labels=dict(home=labs[0], away=labs[1]))


def pick_fav(f, labs, total_ev, srcs, game_ev, score_ev, now):
    fv = favourite(game_ev) if game_ev else None
    if not fv or not score_ev:
        return None
    fav, dog, fm, dm = fv
    t = score_ticker(score_ev, fav, dog, 1, 0)
    m = _market(score_ev, t) if t else None
    q = _quote(m)
    if not q:
        return None
    b, a = q
    ask = lambda tk: (lambda x: D.number(x.get("yes_ask_dollars")) if x else None)(_market(score_ev, tk))      # noqa: E731
    p = base_pick("fav_one_nil", f, labs, total_ev, srcs, now)
    p.update(ticker=m["ticker"], side="yes", price=round(a, 4), bid=b, ask=a, title=m.get("title") or m.get("yes_sub_title"),
             fav=fav, dog=dog, fav_price=fm, dog_price=dm, ask_0_0=ask(score_ticker(score_ev, fav, dog, 0, 0)),
             ask_dog_1_0=ask(score_ticker(score_ev, fav, dog, 0, 1)),
             why=f"{', '.join(srcs)} pick it · {fav} {fm:.2f} v {dog} {dm:.2f} · fav 1-0 YES {a:.2f}")
    return p


def pick_quiet(f, labs, total_ev, srcs, btts_ev, now):
    m = next((x for x in (btts_ev or {}).get("markets") or [] if str(x.get("ticker") or "").endswith("-BTTS")), None)
    q = _quote(m)
    if not q or not q[0] > 0:
        return None
    b, a = q
    no_ask = round(1 - b, 4)
    p = base_pick("quiet_first_half", f, labs, total_ev, srcs, now)
    p.update(ticker=m["ticker"], side="no", price=no_ask, bid=b, ask=a, title=m.get("title") or m.get("yes_sub_title"),
             why=f"{', '.join(srcs)} pick it · 1H BTTS NO {no_ask:.2f}")
    return p


def due(fixtures, now):
    if settle_only.on():
        return []
    return [f for f in SR.due(fixtures, now) if f.get("league") in PREFIX]


def run(states, fixtures, now=None, fetch=D.get):
    """`states` = {lane key: ledger state}. One read of the source rules' selection feeds both lanes."""
    now = now or dt.datetime.now(dt.timezone.utc)
    for st in states.values():
        st.setdefault("rules", {}).setdefault("PB", {"picks": []})
    seen = {k: {p["event"] for p in st["rules"]["PB"]["picks"]} for k, st in states.items()}
    log = {k: [] for k in states}
    errs, cache = [], {}
    stats = dict(due=0, selected=0)

    def events(series):
        if series not in cache:
            cache[series] = SR.series_events(series, fetch)
        return cache[series]

    for f in due(fixtures, now):
        stats["due"] += 1
        labs = SR.labels(fixtures, f)
        if not all(labs):
            continue
        pre = PREFIX[f["league"]]
        try:
            total_ev = SR.find_event(f, events(SR.SERIES[f["league"]]))
            if not total_ev:
                continue
            srcs = selected(f["league"], labs, total_ev, now)
            if not srcs:
                continue
            stats["selected"] += 1
            for key in states:
                if total_ev["event_ticker"] in seen[key]:
                    continue
                if key == "fav_one_nil":
                    p = pick_fav(f, labs, total_ev, srcs, SR.find_event(f, events(pre + "GAME")), SR.find_event(f, events(pre + "SCORE")), now)
                else:
                    p = pick_quiet(f, labs, total_ev, srcs, SR.find_event(f, events(pre + "1HBTTS")), now)
                if p:
                    states[key]["rules"]["PB"]["picks"].append(p)
                    seen[key].add(p["event"])
                    log[key].append(p["id"])
        except Exception as e:                                  # noqa: BLE001
            errs.append(f"{f['home']} v {f['away']}: {str(e)[:80]}")
    for key, st in states.items():
        e2 = errs + SR.settle(st, now, fetch)
        if key == "fav_one_nil":
            for p in st["rules"]["PB"]["picks"]:
                try:
                    shadow_update(p, now, fetch)
                except Exception as e:                          # noqa: BLE001
                    e2.append(f"shadow {p['id']}: {str(e)[:60]}")
        st["last_run"] = now.isoformat()
        st["error"] = "; ".join(e2)[:1000] or None
        st["runs"] = (st.get("runs") or [])[-50:] + [dict(at=now.isoformat(), new=len(log[key]), **stats)]
    return log


SELL_MULT = 2.0
SELL_CAP = 0.99


def shadow_update(p, now, fetch=D.get):
    """The "sell at 2x" SHADOW beside fav_one_nil's hold record (Coordinator, Nov 21). A pick is sold, on paper, when any TRADE print on its
    correct-score market at or after kickoff reaches 2x the entry ask (capped at 99c): trade prints, never bid highs (the resting-sell rule).
    Sold: return = (target - fee) over (ask + fee), both legs at the taker fee (conservative). Unsold: the settled hold result. The headline stays HOLD."""
    sh = p.setdefault("shadow", dict(target=round(min(SELL_MULT * float(p["price"]), SELL_CAP), 4), sold=False))
    start = D.instant(p.get("start"))
    if sh.get("final") or sh["sold"] or not start or start > now:
        return
    since = max(int(start.timestamp()), int(sh.get("checked_ts") or 0))
    rows = O35.fetch_trades(urllib.parse.quote(p["ticker"], safe=""), since, fetch)
    hit = [(O35._ts(t.get("created_time")), D.number(t.get("yes_price_dollars"))) for t in rows]
    hit = sorted((ts, px) for ts, px in hit if ts is not None and px is not None and ts >= start.timestamp() and px >= sh["target"] - 1e-9)
    if hit:
        sh.update(sold=True, sold_at=dt.datetime.fromtimestamp(hit[0][0], dt.timezone.utc).isoformat(), sold_px=hit[0][1])
        cost = float(p["price"]) + FU.fee(float(p["price"]))
        sh["profit"] = round(100 * ((sh["target"] - FU.fee(sh["target"])) / cost - 1), 2)
    elif p.get("status") in ("won", "lost", "no_result"):
        sh.update(final=True, profit=p.get("profit"))               # never reached 2x on a trade: the hold result
    sh["checked_ts"] = int(now.timestamp())


def shadow_record(picks):
    """(entries with a shadow result, sold at 2x, mean shadow return) for the picks that are sold or settled."""
    done = [p for p in picks if (p.get("shadow") or {}).get("profit") is not None]
    sold = sum(bool(p["shadow"].get("sold")) for p in done)
    return len(done), sold, (sum(p["shadow"]["profit"] for p in done) / (100 * len(done))) if done else None


def by_source(picks):
    return {k: FU.record([p for p in picks if k in (p.get("sources") or [])]) for k in SOURCES}


def main():
    import streaks_fetch
    states = {k: load(k) for k in LANES}
    fixtures = streaks_fetch.load_or_fetch()["fixtures"]
    log = run(states, fixtures)
    for k, st in states.items():
        tmp = path(k) + ".tmp"
        with open(tmp, "w") as f:
            json.dump(st, f, indent=1, sort_keys=True)
            f.write("\n")
        os.replace(tmp, path(k))
        print(k, "run", st["runs"][-1], "new", log[k], "error", st["error"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
