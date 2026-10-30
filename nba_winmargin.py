"""NBA Win Margin Tracker (2026-10-29, Olu): an OBSERVATION tracker for Kalshi's win-margin buckets (KXNBAWINMARGIN).
Paper, no orders, and NO buying or selling rule: it records how the cheap bucket contracts trade so the price patterns
can be understood first.

Research (Olu's method, Oct 20-28 2026, every trade this season): a contract bought at ask a reaches 2a about half the
time at fair. Win-margin buckets at 5-35c an hour before the tip clearly do better (1-5 bucket 78%, 6-10 bucket 69%),
and the favourite's buckets best. Spreads, player points, totals and the rest sat at or below 50%.

COLLECTOR. Every settled NBA game (a KXNBAWINMARGIN event; both teams, buckets 1-5, 6-10, 11-20, 21+). TIP = the
KXNBAGAME market's expected_expiration_time minus 3 hours (verified this season against ESPN). Per bucket contract:
  - the bid and ask at one hour before the tip from the 1-minute candles (entry = the ask);
  - every trade print from two hours before the tip (markets/trades, paginated);
  - the settled result.
A contract is ELIGIBLE (the research population, and what the page's tables count) when its entry ask is 5-35c and its
spread is 5c or less.

METRICS, from TRADE prints at or after the entry hour only:
  peak multiple (highest print / entry ask); reached 2x, 3x, 5x (a print at or above k x the ask AT OR AFTER the tip);
  first minute at 2x or more (minutes from the tip); total minutes at 2x or more (a step function: a print holds
  until the next, the last one for a minute); contracts traded at 2x or more; won; won minus the ask.
  A k x target above 99c cannot be reached, so reach rates are taken over the contracts where it can be.

CONDITIONS on each row: bucket; the team's pregame win share (that team's bucket mids at the entry hour, over both
teams'); favourite (55% or more) / toss-up / underdog (under 45%); entry band 5-10, 10-20, 20-35c; home or away (the
Kalshi code is AWAYHOME); the pregame spread (the KXNBASPREAD rung nearest 50c: the team's median winning margin).

COMEBACK UNDERDOG SPREAD LINE (added 2026-10-29, Olu). The dynamics-sheet rerun (Oct 20-28): when a Comeback team
(won 40%+ of 2025-26 games it trailed at half-time) was the underdog, its KXNBASPREAD rungs ("X wins by over N") reached
2x in 7 of 9 games, against 52% of games for other underdogs. Nine games prove nothing, so this line only grows the
sample. Every game's UNDERDOG spread rungs (the KXNBAGAME moneyline mid at the entry hour under 50%; the bucket mids
only when the moneyline has no quote) are read the same way as the buckets (the ask an hour
before the tip, 5-35c, spread 5c or less, then every trade print) into state["spread_rows"], each flagged comeback or
not, so the two groups compare like for like. The Comeback list is FIXED from the 2025-26 profile (COMEBACK below);
re-profiling on this season is a new version, not an edit.

Own ledger data/nba_winmargin_tracker.json; rows are stamped (version, logged). Raw prints are kept for the last three
nights only (the price charts); older rows keep their metrics.
"""
import datetime as dt
import json
import os
import re
import statistics

import chaos_replay as C
import daily_track as D
import o35_cheap_no as O

ROOT = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(ROOT, "data", "nba_winmargin_tracker.json")
SERIES = "KXNBAWINMARGIN"
SINCE = "2026-10-20"
VERSION = "wm-v1"
TIP_BACK_H = 3
ENTRY_H = 1
TRADES_FROM_H = 2
ASK_RANGE = (0.05, 0.35)
MAX_SPREAD = 0.05
FAV, DOG = 0.55, 0.45
BANDS = ((0.05, 0.10, "5-10c"), (0.10, 0.20, "10-20c"), (0.20, 0.351, "20-35c"))
BUCKETS = ("1-5", "6-10", "11-20", "21+")
KEEP_PATH_NIGHTS = 3
MAX_EVENTS_PER_RUN = 80
FAIR = {2: 0.50, 3: 0.33, 5: 0.20}
HOLD_MIN = 10
# Comeback teams, Kalshi codes: won 40%+ of the 2025-26 games they trailed at half-time (the NBA dynamics sheet).
COMEBACK = frozenset({"SAS", "OKC", "DEN", "MIN", "BOS", "HOU", "NYK", "CLE"})
SPREAD_VERSION = "wm-spread-v1"
UTC, ET = dt.timezone.utc, D.ET


def _ts(raw):
    t = D.instant(raw)
    return int(t.timestamp()) if t else None


def night_of(ts):
    return dt.datetime.fromtimestamp(ts, UTC).astimezone(ET).date().isoformat()


def bucket_of(title, ticker=""):
    m = re.search(r"by (\d+(?:-\d+|\+))", title or "")
    return m.group(1) if m else None


def band_of(a):
    return next((lbl for lo, hi, lbl in BANDS if lo - 1e-9 <= a < hi), None)


def role_of(p):
    return "favourite" if p >= FAV else "underdog" if p < DOG else "toss-up"


def entry_quote(candles, entry_ts):
    """(bid, ask) of the last 1-minute candle ending at or before the entry hour (+1 minute) with both quotes."""
    best = None
    for c in sorted(candles or [], key=lambda c: c.get("end_period_ts") or 0):
        end = c.get("end_period_ts")
        if not end or end > entry_ts + 60:
            continue
        bid = D.number((c.get("yes_bid") or {}).get("close_dollars"))
        ask = D.number((c.get("yes_ask") or {}).get("close_dollars"))
        if bid is not None and ask is not None and ask > 0:
            best = (bid, ask)
    return best


def metrics(prints, tip, ask):
    """Per-contract metrics from trade prints [(ts, price, contracts)] at or after the entry hour. None with no prints."""
    tr = [p for p in prints if p[0] >= tip - ENTRY_H * 3600]
    if not tr or not ask:
        return None
    end = tr[-1][0] + 60
    out = dict(peak=round(max(p[1] for p in tr) / ask, 3), prints=len(tr))
    for k in (2, 3, 5):
        hit = next((p for p in tr if p[0] >= tip and p[1] >= k * ask - 1e-9), None)
        out[f"reach{k}"] = None if k * ask > 0.99 + 1e-9 else hit is not None
        out[f"first{k}"] = None if hit is None else round((hit[0] - tip) / 60, 1)
    above, vol = 0.0, 0.0
    for p, nxt in zip(tr, tr[1:] + [(end, 0, 0)]):
        if p[0] >= tip and p[1] >= 2 * ask - 1e-9:
            above += (nxt[0] - p[0]) / 60
            vol += p[2]
    out.update(above2=round(above, 1), vol2=round(vol, 1))
    return out


def yes_prints(rows):
    """[(ts, yes price, contracts)] oldest first from /markets/trades rows (o35_cheap_no.prints_of gives NO prices)."""
    return [(ts, round(1 - no, 4), n) for ts, no, n in O.prints_of(rows)]


def team_shares(quotes):
    """{team code: pregame win share} from the mids of each team's bucket quotes, normalised over both teams."""
    s = {}
    for team, (bid, ask) in quotes:
        s[team] = s.get(team, 0.0) + (bid + ask) / 2
    tot = sum(s.values())
    return {t: v / tot for t, v in s.items()} if tot > 0 else {}


def spread_of(mkts, candles, entry_ts):
    """The spread rung nearest 50c at the entry hour: (team, margin) or None."""
    best = None
    for m in mkts:
        q = entry_quote(candles.get(m["ticker"]), entry_ts)
        k = D.number(m.get("floor_strike"))
        if q is None or k is None:
            continue
        mid = (q[0] + q[1]) / 2
        if best is None or abs(mid - 0.5) < best[0]:
            best = (abs(mid - 0.5), m.get("yes_sub_title") or "", k)
    if not best:
        return None
    team = re.sub(r" wins by.*", "", best[1]).strip()
    return dict(team=team, margin=best[2])


def load(path=None):
    try:
        with open(path or PATH) as f:
            s = json.load(f)
    except FileNotFoundError:
        s = {}
    s.setdefault("since", SINCE)
    s.setdefault("version", VERSION)
    s.setdefault("rows", [])
    s.setdefault("seen", {})
    s.setdefault("skips", {})
    s.setdefault("spread_rows", [])
    s.setdefault("spread_seen", {})
    return s


def game_rows(event, markets, tip, entry, trades_of, spread, now):
    """The tracker rows of one game. `entry` {ticker: (bid, ask)}, `trades_of` {ticker: [(ts, price, count)]}."""
    code = event.split("-", 1)[1][7:]                       # AWAYHOME after the date, e.g. 26OCT29WASCLE -> WASCLE
    away, home = code[:3], code[3:]
    teams = {m["ticker"]: re.search(r"-([A-Z]+)\d", m["ticker"]).group(1) for m in markets}
    share = team_shares([(teams[t], q) for t, q in entry.items()])
    rows = []
    for m in markets:
        t = m["ticker"]
        q = entry.get(t)
        if q is None:
            continue
        bid, ask = q
        spr = round(ask - bid, 4)
        elig = ASK_RANGE[0] - 1e-9 <= ask <= ASK_RANGE[1] + 1e-9 and spr <= MAX_SPREAD + 1e-9
        p = share.get(teams[t])
        prints = trades_of.get(t) or []
        row = dict(id=t, event=event, night=night_of(tip), tip=tip, team=teams[t], side="home" if teams[t] == home else "away",
                   bucket=bucket_of(m.get("yes_sub_title")), bid=bid, ask=ask, spread=spr, eligible=elig,
                   team_share=None if p is None else round(p, 4), role=None if p is None else role_of(p),
                   band=band_of(ask) if elig else None, won=m.get("result") == "yes",
                   spread_line=spread, logged=now.isoformat(), version=VERSION)
        row["m"] = metrics(prints, tip, ask) if elig else None
        row["path"] = [[p0[0] - tip, round(p0[1] * 100), round(p0[2])] for p0 in prints if p0[0] >= tip - ENTRY_H * 3600] if elig else []
        rows.append(row)
    return rows


def ml_shares(gm, candles, entry_ts):
    """{team code: pregame win share} from the KXNBAGAME moneyline mids at the entry hour (the research's underdog)."""
    q = {}
    for m in gm:
        t = m.get("ticker") or ""
        e = entry_quote(candles.get(t), entry_ts)
        if e:
            q[t.rsplit("-", 1)[-1]] = (e[0] + e[1]) / 2
    tot = sum(q.values())
    return {k: v / tot for k, v in q.items()} if len(q) == 2 and tot > 0 else {}


def spread_rows(event, sp, entry_of, share, tip, trades_of, now):
    """The underdog's spread rungs of one game. `sp` the KXNBASPREAD markets, `entry_of` {ticker: (bid, ask)},
    `share` {team code: pregame win share}, `trades_of(ticker)` -> [(ts, price, count)]."""
    if not share:
        return []
    dog = min(share, key=share.get)
    if share[dog] >= 0.5:
        return []
    rows = []
    for m in sp:
        t = m["ticker"]
        mt = re.match(r"([A-Z]+)\d", t.rsplit("-", 1)[-1])
        if not mt or mt.group(1) != dog or t not in entry_of:
            continue
        bid, ask = entry_of[t]
        spr = round(ask - bid, 4)
        elig = ASK_RANGE[0] - 1e-9 <= ask <= ASK_RANGE[1] + 1e-9 and spr <= MAX_SPREAD + 1e-9
        prints = trades_of(t) if elig else []
        rows.append(dict(id=t, event=event, night=night_of(tip), tip=tip, team=dog, comeback=dog in COMEBACK,
                         team_share=round(share[dog], 4), line=D.number(m.get("floor_strike")), bid=bid, ask=ask, spread=spr,
                         eligible=elig, band=band_of(ask) if elig else None, won=m.get("result") == "yes",
                         m=metrics(prints, tip, ask) if elig else None,
                         path=[[p0[0] - tip, round(p0[1] * 100), round(p0[2])] for p0 in prints if p0[0] >= tip - ENTRY_H * 3600],
                         logged=now.isoformat(), version=SPREAD_VERSION))
    return rows


def run(state, now=None, fetch=D.get):
    now = now or dt.datetime.now(UTC)
    since = dt.date.fromisoformat(state["since"])
    obs = dict(at=now.isoformat(), new=0, waiting=0, errors=[])
    try:
        events = C.list_events(SERIES, since, fetch, until=now.astimezone(ET).date())
    except Exception as e:                                       # noqa: BLE001
        events = []
        obs["errors"].append(f"listing: {str(e)[:80]}")
    done = 0
    for event in events:
        need_wm = event not in state["seen"] and event not in state["skips"]
        need_sp = event not in state["spread_seen"] and event not in state["skips"]
        if not (need_wm or need_sp) or done >= MAX_EVENTS_PER_RUN:
            continue
        sp_rows = None
        try:
            markets, archived = C.event_markets(event, fetch)
            if not markets or any(m.get("result") not in ("yes", "no") for m in markets):
                obs["waiting"] += 1
                continue
            suf = event.split("-", 1)[1]
            gm = D.pages(f"markets?limit=5&event_ticker=KXNBAGAME-{suf}", "markets", fetch)
            tip = next((x for x in (_ts(m.get("expected_expiration_time")) for m in gm) if x), None)
            if tip is None:
                state["skips"][event] = "no KXNBAGAME tip time"
                continue
            tip -= TIP_BACK_H * 3600
            if night_of(tip) < state["since"]:
                state["seen"][event] = state["spread_seen"][event] = "before the tracker's first night"
                continue
            entry_ts = tip - ENTRY_H * 3600
            cs = C.fetch_candles(SERIES, event, markets, entry_ts - 1800, entry_ts + 60, fetch, archived)
            entry = {t: q for t, q in ((t, entry_quote(c, entry_ts)) for t, c in cs.items()) if q}
            trades_of = {t: yes_prints(O.fetch_trades(t, tip - TRADES_FROM_H * 3600, fetch)) for t in entry} if need_wm else {}
            spread = None
            try:
                sp = D.pages(f"markets?limit=200&event_ticker=KXNBASPREAD-{suf}", "markets", fetch)
                scs = C.fetch_candles("KXNBASPREAD", f"KXNBASPREAD-{suf}", sp, entry_ts - 1800, entry_ts + 60, fetch, False) if sp else {}
                spread = spread_of(sp, scs, entry_ts)
                if need_sp:
                    try:
                        share = ml_shares(gm, C.fetch_candles("KXNBAGAME", f"KXNBAGAME-{suf}", gm, entry_ts - 1800, entry_ts + 60, fetch, False), entry_ts)
                    except Exception:                        # noqa: BLE001
                        share = {}
                    if not share:                            # no moneyline quote: fall back to the bucket mids
                        teams = {m["ticker"]: re.search(r"-([A-Z]+)\d", m["ticker"]).group(1) for m in markets}
                        share = team_shares([(teams[t], q) for t, q in entry.items()])
                    sentry = {t: q for t, q in ((t, entry_quote(c, entry_ts)) for t, c in scs.items()) if q}
                    sp_rows = spread_rows(event, sp, sentry, share, tip,
                                          lambda t: yes_prints(O.fetch_trades(t, tip - TRADES_FROM_H * 3600, fetch)), now)
            except Exception as e:                               # noqa: BLE001
                spread = None
                if need_sp:
                    obs["errors"].append(f"{event} spread: {str(e)[:80]}")
        except Exception as e:                                   # noqa: BLE001
            obs["errors"].append(f"{event}: {str(e)[:80]}")
            continue
        if need_wm:
            state["rows"] += game_rows(event, markets, tip, entry, trades_of, spread, now)
            state["seen"][event] = now.isoformat()
            obs["new"] += 1
        if sp_rows is not None:
            state["spread_rows"] += sp_rows
            state["spread_seen"][event] = now.isoformat()
            obs["spread_new"] = obs.get("spread_new", 0) + 1
        done += 1
    cutoff = (now.astimezone(ET).date() - dt.timedelta(days=KEEP_PATH_NIGHTS)).isoformat()
    for r in state["rows"] + state["spread_rows"]:
        # The ask check (leaderboard.tracker_ask_ok, the #253 print test) is stamped while the path is still
        # kept, so a row stays checkable after its path is cleared. Rows already cleared stay unstamped.
        if r.get("ask_ok") is None and r.get("path") and r.get("eligible") and r.get("m"):
            import leaderboard
            r["ask_ok"] = bool(leaderboard.tracker_ask_ok(dict(r, ask_ok=None)))
        if r["night"] < cutoff:
            r["path"] = []
    state["last_run"] = now.isoformat()
    state["error"] = "; ".join(obs["errors"])[:600] or None
    state["observations"] = obs
    return state


# ---------- summaries ----------

def eligible(rows):
    return [r for r in rows if r.get("eligible") and r.get("m")]


def summarize(rows):
    """n, mean ask, reach rates (over contracts where the multiple can be reached), held 10+ minutes, medians over the
    contracts that reached 2x, and won minus ask."""
    n = len(rows)
    if not n:
        return dict(n=0)
    out = dict(n=n, ask=statistics.mean(r["ask"] for r in rows))
    for k in (2, 3, 5):
        able = [r for r in rows if r["m"].get(f"reach{k}") is not None]
        out[f"r{k}"] = sum(1 for r in able if r["m"][f"reach{k}"]) / len(able) if able else None
    hit = [r for r in rows if r["m"].get("first2") is not None]
    out["held"] = sum(1 for r in rows if r["m"]["above2"] >= HOLD_MIN) / n
    out["first"] = statistics.median(r["m"]["first2"] for r in hit) if hit else None
    out["above"] = statistics.median(r["m"]["above2"] for r in hit) if hit else None
    out["vol"] = statistics.median(r["m"]["vol2"] for r in hit) if hit else None
    out["edge"] = sum(1 for r in rows if r["won"]) / n - out["ask"]
    return out


def by_game(rows):
    """(games, games where any eligible rung reached 2x)."""
    g = {}
    for r in rows:
        g[r["event"]] = g.get(r["event"], False) or bool(r["m"].get("reach2"))
    return len(g), sum(g.values())


def halves(rows):
    rows = sorted(rows, key=lambda r: (r["tip"], r["id"]))
    k = len(rows) // 2
    return (summarize(rows[:k]), summarize(rows[k:])) if len(rows) >= 4 else (None, None)


def main():
    st = load()
    try:
        run(st)
    except Exception as e:                                       # noqa: BLE001
        st["error"] = (type(e).__name__ + ": " + str(e))[:300]
    os.makedirs(os.path.dirname(PATH), exist_ok=True)
    tmp = PATH + ".tmp"
    with open(tmp, "w") as f:
        json.dump(st, f, indent=1, sort_keys=True)
        f.write("\n")
    os.replace(tmp, PATH)
    print("nba_winmargin rows", len(st["rows"]), "games", len(st["seen"]), "this run", st.get("observations"), "error", st.get("error"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
