"""mentions_dip_hold: Trump mentions, a resting 10c YES bid held to settlement (2026-11-01, Olu). Sandbox PAPER, no live orders.

RESEARCH (mentions_exits_2026-11-01, 9 settled weekly KXTRUMPSAY events, Aug 31 to Oct 26 2026, verified on trades): a
resting YES bid at 10c all week, HELD to settlement, made +54% (z 3.4, 7 of 9 weeks up; 134 fills, 21 said, against a
10.2% break-even); at 15c +28%, at 20c +23%. 2x / 3x / 4x sells added nothing (-11% to +15%). Buying at the open ask loses.

PRE-REGISTERED RULE (this module implements exactly ~/edge-research/mentions_exits_2026-11-01/trade_check.py):
  SCOPE   The weekly series KXTRUMPSAY only, every word market in the event, one entry per word per week.
  ENTRY   A YES bid rests at 10c (the headline; 15c is tracked as a comparison line) from the word's open. It is a DIP buy:
          only a word whose FIRST trade after the open prints ABOVE the bid qualifies. The bid FILLS at its limit at the
          first trade print at or under the bid, but only when 10+ contracts trade at or under the bid within 60 minutes of
          that print (the held-fill rule), counted from the markets/trades prints, never candle lows. A word already said, or a
          market closed, before a fill has no entry (no print can come after the close).
  EXIT    HOLD to Kalshi's settlement. No sell variants.
  FEES    Maker 0.0175 p(1-p) on the entry, none at settlement. ROI is per contract after fees, the equal-stake mean over entries.
  COUNT   By EVENT (week): one week is one independent outcome. The record counts weeks whose entries have ALL settled (a word
          said early settles early, so a half-settled week would read as all winners). Review at 10 settled weeks, decide at 30.
  RECORD  Fresh from the week of KXTRUMPSAY-26NOV02 (opened 2026-10-26 04:00Z), replayed from its trades as the backfill: the
          bid would have rested from the open. The 9 research weeks are shown once, apart, as in-sample.

Own ledger data/mentions_dip_hold_ledger.json: per word market its first trade after the open and every print at or under 15c
(small), read incrementally with min_ts; a settled market is read once more after it settles, then never again.
"""
import datetime as dt
import json
import os

import daily_track as D
import mentions_split as MS
import o35_cheap_no as O

ROOT = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(ROOT, "data", "mentions_dip_hold_ledger.json")
LANE = "mentions_dip_hold"
LABEL = "Trump mentions · 10c dip bid, hold"
SERIES = "KXTRUMPSAY"
START = "2026-10-26T04:00:00+00:00"
FIRST_EVENT = "KXTRUMPSAY-26NOV02"
BIDS = (0.10, 0.15)
HEAD = 0.10
MIN_FILL = 10
WINDOW_S = 3600
MAX_BID = max(BIDS)
MIN_Z_EVENTS = 3
EPS = 1e-9
UTC = dt.timezone.utc
RESEARCH = dict(weeks=9, rows=((0.10, 134, "+54%", "3.4", "7 / 9"), (0.15, 123, "+28%", "2.5", "7 / 9"), (0.20, 120, "+23%", "2.1", "8 / 9")),
                won10=21, breakeven10="10.2%")


def key(bid):
    return f"{round(bid * 100)}"


def _ts(raw):
    return MS._ts(raw)


def cost_of(bid):
    return bid + MS.fee(bid, MS.MAKER)


def fill_state(m, bid, now_ts):
    """One word market against one bid, from its stored first trade and prints at or under MAX_BID:
    state in waiting | no_dip | checking | filled | unfilled. Pure: nothing here touches the network."""
    if m.get("first_px") is None:
        return dict(state="unfilled" if m.get("final") else "waiting")
    if m["first_px"] <= bid + EPS:
        return dict(state="no_dip", first_px=m["first_px"])
    lows = [p for p in m.get("lows") or [] if p[1] <= bid + EPS]
    pending = False
    for i, (t, px, n) in enumerate(lows):
        vol = sum(x[2] for x in lows[i:] if x[0] <= t + WINDOW_S)
        if vol >= MIN_FILL - EPS:
            return dict(state="filled", fill_ts=t, fill_px=px, contracts=round(vol, 2))
        if t + WINDOW_S > now_ts and not m.get("final"):
            pending = True                 # its hour is still running: more contracts may print
    return dict(state="checking" if pending else ("unfilled" if m.get("final") else "waiting"))


def payout(m):
    """1 or 0 once Kalshi has settled the word, else None."""
    if m.get("status") in ("finalized", "settled") and m.get("result") in ("yes", "no"):
        return 1.0 if m["result"] == "yes" else 0.0
    return None


def entries(state, bid, now_ts=None):
    """Filled bids at `bid`, one per word market: event, word, fill time, contracts at the fill, payout, ROI (None until settled)."""
    now_ts = now_ts or int(dt.datetime.now(UTC).timestamp())
    out = []
    for tick, ev in sorted((state.get("events") or {}).items()):
        for t, m in sorted((ev.get("markets") or {}).items()):
            f = fill_state(m, bid, now_ts)
            if f["state"] != "filled":
                continue
            pay = payout(m)
            c = cost_of(bid)
            out.append(dict(event=tick, ticker=t, word=m.get("word") or t, bid=bid, fill_ts=f["fill_ts"], fill_px=f["fill_px"],
                            contracts=f["contracts"], payout=pay, roi=None if pay is None else (pay - c) / c))
    return out


def record(state, bid, now_ts=None):
    """The lane's record at one bid: entries, settled weeks (every entry of the week settled), won, ROI after fees (mean over the
    entries of settled weeks, equal stake), z by week (None under 3 weeks or no spread), weeks up."""
    es = entries(state, bid, now_ts)
    by = {}
    for e in es:
        by.setdefault(e["event"], []).append(e)
    done = {k: v for k, v in by.items() if all(e["payout"] is not None for e in v)}
    rois = [e["roi"] for v in done.values() for e in v]
    wk = [sum(e["roi"] for e in v) / len(v) for v in done.values()]
    z = None
    if len(wk) >= MIN_Z_EVENTS:
        mean = sum(wk) / len(wk)
        sd = (sum((x - mean) ** 2 for x in wk) / (len(wk) - 1)) ** 0.5
        z = mean / (sd / len(wk) ** 0.5) if sd > 1e-9 else None
    return dict(entries=len(es), open=sum(e["payout"] is None for e in es), events=len(by), settled_events=len(done),
                settled=len(rois), won=sum(e["payout"] == 1 for v in done.values() for e in v),
                roi=sum(rois) / len(rois) if rois else None, z=z, up=sum(x > 0 for x in wk), weeks=len(wk))


def load(path=None):
    try:
        with open(path or PATH) as f:
            s = json.load(f)
    except FileNotFoundError:
        s = {}
    s.setdefault("lane", LANE)
    s.setdefault("since", START)
    s.setdefault("events", {})
    return s


def ingest(m, rows):
    """Fold new /markets/trades rows into a market's state: its first trade after the open, and every print at or under MAX_BID
    while the market was open. Rows older than what was already read, and repeats at the boundary second, are skipped."""
    open_ts, close_ts = m["open_ts"], m.get("close_ts")
    seen = set(m.get("edge_ids") or [])
    last = m.get("last_ts") or open_ts
    fresh = []
    for r in rows:
        ts = _ts(r.get("created_time"))
        yes = D.number(r.get("yes_price_dollars"))
        n = D.number(r.get("count_fp")) or 0.0
        if ts is None or yes is None or ts <= open_ts or ts < last:
            continue
        if ts == last and r.get("trade_id") in seen:
            continue
        if close_ts and ts > close_ts + 1:
            continue                       # nothing can fill after the market closed
        fresh.append((ts, round(yes, 4), n, r.get("trade_id")))
    for ts, px, n, _id in sorted(fresh, key=lambda x: x[0]):
        if m.get("first_px") is None:
            m["first_px"], m["first_ts"] = px, ts
        if px <= MAX_BID + EPS:
            m.setdefault("lows", []).append([ts, px, n])
        m["n_prints"] = m.get("n_prints", 0) + 1
    if fresh:
        top = max(f[0] for f in fresh)
        m["edge_ids"] = sorted({f[3] for f in fresh if f[0] == top and f[3]} | (seen if top == last else set()))
        m["last_ts"] = top
    return len(fresh)


def listed(fetch, state):
    """Open KXTRUMPSAY events, plus any event the ledger holds that still has an unsettled market."""
    evs = MS.events(fetch, SERIES, open_only=True)
    have = {e.get("event_ticker") for e in evs}
    for tick, ev in sorted((state.get("events") or {}).items()):
        if tick in have or all(m.get("final") for m in (ev.get("markets") or {}).values()):
            continue
        d = fetch(f"events/{tick}?with_nested_markets=true")
        x = dict(d.get("event") or {}, event_ticker=tick)
        x["markets"] = (d.get("event") or {}).get("markets") or d.get("markets") or []
        evs.append(x)
    return evs


def run(state, now=None, fetch=D.get):
    now = now or dt.datetime.now(UTC)
    now_ts = int(now.timestamp())
    start = _ts(START)
    obs = dict(at=now.isoformat(), events=0, markets=0, prints=0, errors=[])
    for ev in listed(fetch, state):
        tick = ev.get("event_ticker")
        ms = [x for x in ev.get("markets") or [] if _ts(x.get("open_time"))]
        if not ms or min(_ts(x["open_time"]) for x in ms) < start:
            continue
        rec = state["events"].setdefault(tick, dict(first_seen=now.isoformat(), markets={}))
        obs["events"] += 1
        for x in ms:
            t = x["ticker"]
            m = rec["markets"].setdefault(t, dict(word=(x.get("custom_strike") or {}).get("Word") or x.get("yes_sub_title") or t,
                                                  open_ts=_ts(x["open_time"])))
            if m.get("final"):
                continue
            m.update(status=x.get("status"), result=x.get("result"), close_ts=_ts(x.get("close_time")))
            try:
                rows = O.fetch_trades(t, m.get("last_ts") or m["open_ts"], fetch)
            except Exception as e:                                   # noqa: BLE001
                obs["errors"].append(f"{t}: {str(e)[:80]}")
                continue
            obs["prints"] += ingest(m, rows)
            obs["markets"] += 1
            if payout(m) is not None:
                m["final"] = True              # read once after it settled: never again
    state["observations"] = obs
    state["last_success"] = now.isoformat()
    state["error"] = "; ".join(obs["errors"])[:300] or None
    return state


def main():
    st = load()
    try:
        run(st)
    except Exception as e:                                           # noqa: BLE001
        st["error"] = (type(e).__name__ + ": " + str(e))[:300]
    os.makedirs(os.path.dirname(PATH), exist_ok=True)
    tmp = PATH + ".tmp"
    with open(tmp, "w") as f:
        json.dump(st, f, indent=1, sort_keys=True)
        f.write("\n")
    os.replace(tmp, PATH)
    r = record(st, HEAD)
    print(LANE, "events", len(st["events"]), "10c entries", r["entries"], "this run", st.get("observations"), "error", st.get("error"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
