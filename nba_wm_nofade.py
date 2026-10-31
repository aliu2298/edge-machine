"""NBA win margin NO FADE (2026-10-30, Olu): a resting NO buy at a dip in a win-margin bucket, sold back at the
pregame price. Sandbox PAPER, no live orders. Its own ledger, data/nba_wm_nofade.json.

Research (dip_study_2026-10-30, NBA win margin, Oct 20-28): when a bucket's YES spikes its NO crashes, and the spike
reverts. P = the NO price an hour before the tip (1 - the YES bid), YES spread 5c or less, P 10-95c. After the tip a
resting NO buy at 0.75 x P fills on a print, with at least 10 contracts traded at or under the limit within 60
minutes; then a resting sell at P, else settlement. Maker fees in and out. +14.4% a fill, z +4.4 by night, both
halves positive, 125 fills, 8 nights; 0.85 x P +6.8%, 0.65 x P +15.0%.

RULE, as the study ran it. Same games and tip rule as the win margin tracker (KXNBAGAME expected_expiration - 3h).
Every bucket (both teams, all four buckets) whose NO price an hour before the tip is 10-95c with a YES spread of 5c
or less. The limit is round(d x P, 2) for d = 0.75 (the HEADLINE), 0.85 and 0.65, never under 3c. FILL: the first
trade print at or after the tip with NO at or under the limit, and at least MIN_FILL contracts traded at or under the
limit within 60 minutes of that print (under that the order is "thin": it does not fill). SELL: a later print with NO at
or above P. Not sold = held to settlement (NO pays 1 if the bucket misses). Fees: maker 0.0175 p(1-p) on the buy and
on the sell; none on settlement.

ASK CHECK (#253, the cheap-side rule). The pregame price P must have been real: at least 10 contracts traded at or
through it (NO at or under P) in the 60 minutes after the entry hour, and P not under half the last trade before it.
A bucket that fails stays on the ledger as "unverified ask" with its reason and leaves the record. The book is read
after the game, so the evidence is the prints (source "replayed"); there is no live book to snapshot.

OUTCOME = THE GAME. A game's filled buckets are one row (their cost and profit summed), because a game's buckets
move together. z is clustered by night, never below the independent-games z. Review at 10 settled games with a fill,
decide at 30.

RECORD. Fresh from SINCE (2026-10-31). Nights from SINCE_IN to the day before SINCE are IN-SAMPLE (the rule was chosen
on them): kept, flagged, shown once and apart, never in the headline.
"""
import datetime as dt
import json
import os

import chaos_replay as C
import daily_track as D
import nba_winmargin as W
import o35_cheap_no as O

ROOT = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(ROOT, "data", "nba_wm_nofade.json")
LANE = "nba_wm_nofade"
LABEL = "Win margin · NO fade (buy NO at 75% of pregame, sell back at pregame)"
SERIES = W.SERIES
SINCE = "2026-10-31"
SINCE_IN = "2026-10-20"
VERSION = "nofade-v1"
DIPS = (0.75, 0.85, 0.65)
HEAD = 0.75
P_RANGE = (0.10, 0.95)
MAX_SPREAD = 0.05
MIN_LIMIT = 0.03
MIN_FILL = 10
FILL_WINDOW_MIN = 60
CHECK_MIN, CHECK_WINDOW_MIN, LAST_FLOOR = 10, 60, 0.5
MAX_EVENTS_PER_RUN = 40
REVIEW_N, DECIDE_N = 10, 30
EPS = 1e-9
UTC, ET = dt.timezone.utc, D.ET


def fee(p):
    return 0.0175 * p * (1 - p)


def vkey(d):
    return f"d{round(d * 100)}"


def vlabel(key):
    return f"buy NO at {key[1:]}% of pregame, sell back at pregame"


def ask_check(prints, entry_ts, P):
    """The #253 check on the pregame NO price P from NO prints [(ts, no, count)]: dict(status, reason, printed, last)."""
    before = [p for p in prints if p[0] <= entry_ts]
    last = before[-1][1] if before else None
    if last is not None and P < LAST_FLOOR * last - EPS:
        return dict(status="unverified", reason=f"ask {P:.2f} under half the last trade {last:.2f}", last=last, printed=None, source="replayed")
    after = [p for p in prints if entry_ts < p[0] <= entry_ts + CHECK_WINDOW_MIN * 60 and p[1] <= P + EPS]
    printed = round(sum(p[2] for p in after), 2)
    if printed >= CHECK_MIN:
        return dict(status="verified", how="print", last=last, printed=printed, source="replayed")
    return dict(status="unverified", reason=f"{printed:g} contracts traded at or through the ask within {CHECK_WINDOW_MIN} minutes (under {CHECK_MIN})",
                last=last, printed=printed, source="replayed")


def dip_trade(prints, tip, P, d, no_wins):
    """One variant on one bucket: None when nothing fills (or the fill is thin); else the fill and its outcome.
    `prints` are NO prints [(ts, no, count)] oldest first."""
    limit = round(d * P, 2)
    if limit < MIN_LIMIT or limit >= P:
        return None
    live = [p for p in prints if p[0] >= tip]
    i = next((k for k, p in enumerate(live) if p[1] <= limit + EPS), None)
    if i is None:
        return None
    t0 = live[i][0]
    vol = round(sum(p[2] for p in live[i:] if p[0] <= t0 + FILL_WINDOW_MIN * 60 and p[1] <= limit + EPS), 2)
    if vol < MIN_FILL - EPS:
        return None
    sold = next((p for p in live[i + 1:] if p[1] >= P - EPS), None)
    pay = (P - fee(P)) if sold else (1.0 if no_wins else 0.0)
    cost = limit + fee(limit)
    return dict(limit=limit, fill_at=t0, fill_print=live[i][1], printed=vol, sold_at=sold[0] if sold else None,
                cost=round(cost, 5), profit=round(pay - cost, 5), won=pay > cost, reason="sold" if sold else "settled")


def evaluate(markets, entry, trades_of, tip, now_iso):
    """The bucket rows of one game. `entry` {ticker: (yes bid, yes ask)}, `trades_of` {ticker: NO prints}."""
    entry_ts = tip - W.ENTRY_H * 3600
    rows = []
    for m in markets:
        t = m["ticker"]
        q = entry.get(t)
        if q is None:
            continue
        bid, ask = q
        P = round(1 - bid, 4)
        spread = round(ask - bid, 4)
        if spread > MAX_SPREAD + EPS or not P_RANGE[0] - EPS <= P <= P_RANGE[1] + EPS:
            continue
        prints = trades_of.get(t) or []
        chk = ask_check(prints, entry_ts, P)
        no_wins = m.get("result") == "no"
        rows.append(dict(id=t, bucket=W.bucket_of(m.get("yes_sub_title")), team=t.rsplit("-", 1)[-1][:3], P=P, spread=spread, ask=chk,
                         no_wins=no_wins, fills={vkey(d): dip_trade(prints, tip, P, d, no_wins) for d in DIPS}))
    return rows


def game_rows(entries, variant, insample=None):
    """One row per game with a fill under the ask rule, in the shape chaos_replay.stats reads."""
    out = []
    for e in entries:
        if insample is not None and bool(e.get("insample")) != insample:
            continue
        fills = [r["fills"][variant] for r in e["buckets"] if r["ask"]["status"] == "verified" and r["fills"].get(variant)]
        if not fills:
            continue
        cost = sum(f["cost"] for f in fills)
        profit = sum(f["profit"] for f in fills)
        out.append(dict(event=e["event"], night=e["night"], fills=len(fills), cost=cost, profit=profit, roi=profit / cost,
                        won=profit > 0, reason="game", sold=sum(1 for f in fills if f["sold_at"])))
    return out


def counts(entries, insample=None):
    """Games read, buckets that passed the ask check, buckets that failed it."""
    es = [e for e in entries if insample is None or bool(e.get("insample")) == insample]
    ok = sum(1 for e in es for r in e["buckets"] if r["ask"]["status"] == "verified")
    bad = sum(1 for e in es for r in e["buckets"] if r["ask"]["status"] != "verified")
    return dict(games=len(es), verified=ok, unverified=bad)


def load(path=None):
    try:
        with open(path or PATH) as f:
            s = json.load(f)
    except FileNotFoundError:
        s = {}
    s.setdefault("lane", LANE)
    s.setdefault("since", SINCE)
    s.setdefault("since_in", SINCE_IN)
    s.setdefault("version", VERSION)
    s.setdefault("entries", [])
    s.setdefault("seen", {})
    s.setdefault("skips", {})
    return s


def run(state, now=None, fetch=D.get):
    now = now or dt.datetime.now(UTC)
    since = dt.date.fromisoformat(state["since_in"])
    obs = dict(at=now.isoformat(), new=0, waiting=0, errors=[])
    try:
        events = C.list_events(SERIES, since, fetch, until=now.astimezone(ET).date())
    except Exception as e:                                       # noqa: BLE001
        events = []
        obs["errors"].append(f"listing: {str(e)[:80]}")
    done = 0
    for event in events:
        if event in state["seen"] or event in state["skips"] or done >= MAX_EVENTS_PER_RUN:
            continue
        try:
            markets, archived = C.event_markets(event, fetch)
            if not markets or any(m.get("result") not in ("yes", "no") for m in markets):
                obs["waiting"] += 1
                continue
            suf = event.split("-", 1)[1]
            gm = D.pages(f"markets?limit=5&event_ticker=KXNBAGAME-{suf}", "markets", fetch)
            tip = next((x for x in (W._ts(m.get("expected_expiration_time")) for m in gm) if x), None)
            if tip is None:
                state["skips"][event] = "no KXNBAGAME tip time"
                continue
            tip -= W.TIP_BACK_H * 3600
            night = W.night_of(tip)
            if night < state["since_in"]:
                state["seen"][event] = "before the first night"
                continue
            entry_ts = tip - W.ENTRY_H * 3600
            cs = C.fetch_candles(SERIES, event, markets, entry_ts - 1800, entry_ts + 60, fetch, archived)
            entry = {t: q for t, q in ((t, W.entry_quote(c, entry_ts)) for t, c in cs.items()) if q}
            trades_of = {t: O.prints_of(O.fetch_trades(t, entry_ts - 3600, fetch)) for t in entry}
        except Exception as e:                                   # noqa: BLE001
            obs["errors"].append(f"{event}: {str(e)[:80]}")
            continue
        state["entries"].append(dict(event=event, night=night, tip=tip, insample=night < state["since"],
                                     buckets=evaluate(markets, entry, trades_of, tip, now.isoformat()),
                                     logged=now.isoformat(), version=VERSION))
        state["seen"][event] = now.isoformat()
        obs["new"] += 1
        done += 1
    state["last_run"] = now.isoformat()
    state["error"] = "; ".join(obs["errors"])[:600] or None
    state["observations"] = obs
    return state


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
    print(LANE, "games", len(st["entries"]), "this run", st.get("observations"), "error", st.get("error"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
