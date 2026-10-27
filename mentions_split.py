"""Cheap YES on the weekly Trump-mention market, with a split take-profit (2026-10-27, Olu).

A Sandbox PAPER lane, mentions_cheap_yes_split, on Kalshi's weekly "What will Trump say this week?"
event (series KXTRUMPSAY only; not the monthly, company or country series). Its own ledger,
data/mentions_split_ledger.json, read hourly by .github/workflows/culture.yml; shown on the Culture
page beside mentions_rate (culture_build). Fresh record from its first entry.

THE RULE, pre-registered before any entry:
  entry   when a word's market opens, the first quote with a spread of 5c or less inside 6h of the
          open (minute candles, the minute's closing yes_bid / yes_ask); if that quote's YES ask
          is 0.03-0.30, buy YES at that ask. No tight quote inside 6h, or an ask outside the band:
          the word is skipped for the week. One entry per word per week, every word in the event.
  exit    a split resting sell placed at entry: half the stake at 2x the entry price, half at 3x,
          each capped at 0.98 (below 0.99).
  fill    a leg fills only when a TRADE prints at or above its target: the hourly candle's
          price.high_dollars, in a candle that ends after the entry. Never the bid high: on thin
          books it misses fills and invents none.
  hold    a leg not filled is held to Kalshi's settlement (1 or 0).
  fees    taker 0.07 p(1-p) in, maker 0.0175 p(1-p) on a filled leg, nothing at settlement.
  size    the contracts traded from the open to the entry minute (minute candles' volume_fp), and,
          when the lane reads the entry live (within 2h), the YES contracts offered at or under the
          entry price on the book. Olu asked whether the thin opening books take real size.

Research basis (Olu, 60 settled weekly events, Dec 2025 - Oct 2026; held out on the 56 weeks before
Oct 5): cheap YES 3-15c split +65% (27/33 weeks up), 15-30c split +55% (41/53 weeks up); holding
cheap YES was up only 8/33 weeks. Caveat: fills are thin early in the week. Every record here is
paper. Review at 10 settled entries, decide at 30.

Each entry's ROI is per contract after fees; the lane ROI is the mean over entries (equal stake per
entry), beside the same entries held to settlement and with the 2x leg only, for comparison.
"""
import datetime as dt
import html as _html
import json
import os
import re

import daily_track as D

ROOT = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(ROOT, "data", "mentions_split_ledger.json")
LANE = "mentions_cheap_yes_split"
LABEL = "Trump mentions · cheap YES split"
SERIES = "KXTRUMPSAY"
# Fresh record: weekly events opening from here on. KXTRUMPSAY-26NOV02 opened 2026-10-26 04:00Z and
# its opening candles were still served when the lane was built, so its week is the backfill.
START = "2026-10-26T04:00:00+00:00"
REGISTERED = "2026-10-27"
BAND = (0.03, 0.30)
MAX_SPREAD = 0.05
ENTRY_WINDOW_H = 6
LEGS = ((2.0, 0.5), (3.0, 0.5))          # (multiple of entry, share of stake)
CAP = 0.98
TAKER, MAKER = 0.07, 0.0175
LIVE_BOOK_H = 2                          # read the book for size only this soon after the entry
REVIEW_AT, DECIDE_AT = 10, 30
RULE = ("Weekly KXTRUMPSAY only. When a word's market opens, the first quote with a spread of 5c "
        "or less inside 6h of the open; if its YES ask is 0.03-0.30, buy YES at the ask. A split resting "
        "sell placed at entry: half at 2x, half at 3x the entry, each capped at 0.98. A leg fills only "
        "when a trade prints at or above its target (the candle's traded high, never the bid); an "
        "unfilled leg is held to settlement. Taker fee in, maker fee out. One entry per word per week.")

# The wide twin (2026-10-27, Olu, "option 2"): identical except the entry. The first minute quote
# inside 6h of the open whose spread is 10c or less AND whose YES ask is 0.03-0.30; YES bought at
# that ask, the price actually paid, with the legs at 2x and 3x of it. Each entry also records the
# last trade at or before that minute, so the page can show the cost of the spread (ask - last
# trade). Its own ledger and a fresh record from its first entry; the strict lane is unchanged.
WIDE_RULE = ("Weekly KXTRUMPSAY only. The first minute quote inside 6h of a word's open whose spread is "
             "10c or less and whose YES ask is 0.03-0.30: buy YES at that ask. A split resting sell placed "
             "at entry: half at 2x, half at 3x the ask paid, each capped at 0.98. A leg fills only when a "
             "trade prints at or above its target (the candle's traded high, never the bid); an unfilled "
             "leg is held to settlement. Taker fee in, maker fee out. One entry per word per week.")
STRICT = dict(lane=LANE, label="Weekly mentions · strict (5c)", path=PATH, spread=MAX_SPREAD, band_in_quote=False, rule=RULE,
              anchor="mentions-split", skip="no quote with a 5c spread inside 6h", last_trade=False)
WIDE = dict(lane="mentions_cheap_yes_split_wide", label="Weekly mentions · wide (10c)",
            path=os.path.join(ROOT, "data", "mentions_split_wide_ledger.json"), spread=0.10,
            band_in_quote=True, rule=WIDE_RULE, anchor="mentions-split-wide",
            skip="no quote with a 10c spread and a YES ask of 0.03-0.30 inside 6h", last_trade=True)
WEEK_NOTE = "the week of KXTRUMPSAY-26NOV02 (opened 2026-10-26 04:00Z) is replayed from its opening candles"
for _c in (STRICT, WIDE):
    _c.update(series=SERIES, start=START, registered=REGISTERED, backfill=WEEK_NOTE, compare_id="mentions-split-compare")

# The MONTHLY market (2026-10-27, Olu): both lanes, the same rules, on KXTRUMPSAYMONTH ("What will Trump
# say in <month>?"; the event closes at the start of the next month, so 26NOV01 is October). Separate
# lane ids, ledgers and fresh records; never KXTRUMPSAYCOMPANY. Research basis (Olu, 14 settled months,
# opening price = the first hour's traded close): cheap YES 3-15c split +116%, 8 of 9 months up;
# 15-30c split +52%, 6 of 9; 3-30c split positive in 10 of 11 months; cheap NO at 15-50c lost.
# KXTRUMPSAYMONTH-26NOV01 (October) opened 2026-10-01 14:00Z and its opening candles were still
# served when the lanes were built, so it is the backfill.
MONTH_SERIES = "KXTRUMPSAYMONTH"
MONTH_START = "2026-10-01T14:00:00+00:00"
MONTH_REGISTERED = "2026-10-27"
MONTH_NOTE = ("the month of KXTRUMPSAYMONTH-26NOV01 (October, opened 2026-10-01 14:00Z) is replayed from its "
              "opening candles")
_monthly = lambda r: r.replace("Weekly KXTRUMPSAY only.", "Monthly KXTRUMPSAYMONTH only.").replace(
    "per word per week", "per word per month")
MONTH = dict(STRICT, lane="mentions_month_split", label="Monthly mentions · strict (5c)",
             path=os.path.join(ROOT, "data", "mentions_month_split_ledger.json"), rule=_monthly(RULE),
             anchor="mentions-month-split", series=MONTH_SERIES, start=MONTH_START,
             registered=MONTH_REGISTERED, backfill=MONTH_NOTE, compare_id="mentions-month-split-compare")
MONTH_WIDE = dict(WIDE, lane="mentions_month_split_wide", label="Monthly mentions · wide (10c)",
                  path=os.path.join(ROOT, "data", "mentions_month_split_wide_ledger.json"), rule=_monthly(WIDE_RULE),
                  anchor="mentions-month-split-wide", series=MONTH_SERIES, start=MONTH_START,
                  registered=MONTH_REGISTERED, backfill=MONTH_NOTE, compare_id="mentions-month-split-compare")
# Album sales (2026-10-27, Olu): album_cheap_rungs on Kalshi's first-week album-equivalent-unit
# ladders, KXALBUMEQUIV ("Above 20K" ...). One entry per rung: the first minute quote inside 6h of
# the rung's open with a spread of 5c or less AND a YES ask of 0.03-0.15, YES bought at that ask.
# 0.15-0.30 is never entered (research: 0/20 won). Two variants on the SAME entries, side by side:
# HOLD to settlement (roi_held) and SPLIT (half at 2x, half at 3x, trade-print fills, else held;
# roi). Research basis (Olu, real asks, 45 settled events, 483 rungs): 3-15c strict 89 entries, 17
# won; hold +259%, split +55% (z 1.6; older / newer half +33% / +99%); 3-15c wide split +56%;
# 15-30c split -84%. Backfill: every event still open when the lane first ran, from its opening
# candles where they are served (backfill_open).
ALBUM_RULE = ("KXALBUMEQUIV only. For each rung, the first minute quote inside 6h of its open with a spread "
              "of 5c or less and a YES ask of 0.03-0.15: buy YES at that ask (never 0.15-0.30). One entry per "
              "rung. HOLD: held to settlement. SPLIT, on the same entries: half resting at 2x, half at 3x the "
              "ask paid, each capped at 0.98, filled only when a trade prints at or above it (the candle's "
              "traded high, never the bid), else held. Taker fee in, maker fee out.")
ALBUM = dict(WIDE, lane="album_cheap_rungs", label="Album · cheap YES",
             path=os.path.join(ROOT, "data", "album_cheap_rungs_ledger.json"), spread=0.05, band=(0.03, 0.15),
             band_in_quote=True, rule=ALBUM_RULE, anchor="album-cheap-rungs", series="KXALBUMEQUIV",
             start="2026-10-27T03:00:00+00:00", registered="2026-10-27", backfill_open=True, hold_variant=True,
             skip="no quote with a 5c spread and a YES ask of 0.03-0.15 inside 6h",
             backfill="every event still open when the lane first ran is replayed from its opening candles "
                      "where Kalshi still serves them", compare_id=None, unit="Event", item="Rung")
# Cheap NO on the same ladders (2026-10-27, Olu), album_cheap_no, a SEPARATE record: the first minute
# quote inside 6h of the rung's open with a spread of 10c or less (the wide rule) and a NO ask
# (1 - YES bid) of 0.03-0.15; NO bought at that ask (never 0.15-0.30, the band that lost). HOLD and
# SPLIT on the same entries; a NO leg fills when a trade prints at or above it on the NO side, i.e.
# the YES price.low_dollars at or under 1 - target. Research basis (Olu, real asks, 45 events): wide
# 3-15c 20 bets, 8 won, hold +318% (z 2.6), split +67% (z 2.8), halves +54% / +77%; strict 3-15c 42
# bets, 11 won, hold +209%. Album ladders tested too confident: both tails won more than priced.
ALBUM_NO_RULE = ("KXALBUMEQUIV only. For each rung, the first minute quote inside 6h of its open with a spread "
                 "of 10c or less and a NO ask (1 - the YES bid) of 0.03-0.15: buy NO at that ask (never "
                 "0.15-0.30). One entry per rung. HOLD: held to settlement. SPLIT, on the same entries: half "
                 "resting at 2x, half at 3x the NO ask paid, each capped at 0.98, filled only when a trade prints "
                 "at or above it on the NO side (the YES traded low at or under 1 - the target), else held. "
                 "Taker fee in, maker fee out.")
ALBUM_NO = dict(ALBUM, lane="album_cheap_no", label="Album · cheap NO",
                path=os.path.join(ROOT, "data", "album_cheap_no_ledger.json"), spread=0.10, side="no",
                rule=ALBUM_NO_RULE, anchor="album-cheap-no",
                skip="no quote with a 10c spread and a NO ask of 0.03-0.15 inside 6h")
LANES = (STRICT, WIDE, MONTH, MONTH_WIDE, ALBUM, ALBUM_NO)

# COMMODITIES (2026-10-27, Olu): the same cheap-side standard on two daily commodity ladders, shown
# on the Commodities page and read by daily-research.yml (`python3 mentions_split.py commodities`),
# which already reads the gas ladder hourly. Entry is replayed from minute candles, so no window
# stamp is needed: an hourly read finds the first in-band minute after the fact. Only the series'
# OPEN events are listed (open_only; KXWTI keeps a long monthly-style event too), plus any event a
# lane already holds until it settles; an event that opened more than 7 days before the lane first
# saw it is not backfilled (its opening minute candles are no longer served).
#   wti_cheap_yes   KXWTI: YES ask 0.15-0.30, spread 5c or less. Research (Olu, real asks, last 60
#                   events): 216 bets, 72 won; split +29% (z 1.8, halves +40 / +19), hold +36%.
#   gas_cheap_no    KXAAAGASD: NO ask (1 - YES bid) 0.15-0.30, spread 5c or less; a NO leg fills when
#                   the YES traded low is at or under 1 - target. Research: 118 bets, 29 won; split +30%
#                   (z 2.3, halves +27 / +32), hold -3%.
# Every 3-15c band lost, so neither lane enters under 0.15.
_COMMOD_RULE = ("{series} only. For each rung, the first minute quote inside 6h of its open with a spread of 5c or "
                "less and a {side} ask of 0.15-0.30{no_def}: buy {side} at that ask (never under 0.15: that band "
                "lost). HOLD: held to settlement. SPLIT, on the same entries: half resting at 2x, half at 3x of the "
                "ask paid, each capped at 0.98, filled only when a trade prints at or above it{no_fill}, else "
                "held. Taker fee in, maker fee out.")
WTI = dict(WIDE, lane="wti_cheap_yes", label="WTI oil · cheap YES (15-30c)",
           path=os.path.join(ROOT, "data", "wti_cheap_yes_ledger.json"), spread=0.05, band=(0.15, 0.30),
           band_in_quote=True, series="KXWTI", start="2026-10-27T04:00:00+00:00", registered="2026-10-27",
           backfill_open=True, open_only=True, backfill_days=7, anchor="wti-cheap-yes",
           rule=_COMMOD_RULE.format(series="KXWTI (WTI daily)", side="YES", no_def="", no_fill=""),
           skip="no quote with a 5c spread and a YES ask of 0.15-0.30 inside 6h",
           backfill="every event still open when the lane first ran (opened in the last 7 days) is replayed "
                    "from its opening candles", compare_id=None, unit="Event", item="Rung")
GAS = dict(WTI, lane="gas_cheap_no", label="AAA gas · cheap NO (15-30c)", side="no",
           path=os.path.join(ROOT, "data", "gas_cheap_no_ledger.json"), series="KXAAAGASD", anchor="gas-cheap-no",
           rule=_COMMOD_RULE.format(series="KXAAAGASD (AAA national gas daily)", side="NO",
                                    no_def=" (1 - the YES bid)", no_fill=" on the NO side (the YES traded low at "
                                                                          "or under 1 - the target)"),
           skip="no quote with a 5c spread and a NO ask of 0.15-0.30 inside 6h")
# gas_week_cheap_no (2026-10-27, Olu): the daily gas cheap-NO edge on the WEEKLY gas ladder,
# KXAAAGASW ("US gas prices this week"), wide rule: NO ask 0.15-0.30, spread 10c or less. Research
# (Olu, real asks, last 10 settled weeks): 33 entries, 11 won; split +60% (z 2.1, halves +98% / +43%),
# hold +40%; strict 5c split +55% (z 1.7). A small, slow lane: about 3 entries a week.
GAS_WEEK = dict(GAS, lane="gas_week_cheap_no", label="AAA gas weekly · cheap NO (15-30c, 10c spread)",
                path=os.path.join(ROOT, "data", "gas_week_cheap_no_ledger.json"), series="KXAAAGASW",
                spread=0.10, anchor="gas-week-cheap-no",
                rule=_COMMOD_RULE.format(series="KXAAAGASW (US gas prices, weekly)", side="NO",
                                         no_def=" (1 - the YES bid)",
                                         no_fill=" on the NO side (the YES traded low at or under 1 - the target)"
                                         ).replace("a spread of 5c or less", "a spread of 10c or less")
                     + " A small, slow lane: about 3 entries a week.",
                skip="no quote with a 10c spread and a NO ask of 0.15-0.30 inside 6h")
COMMOD_LANES = (WTI, GAS, GAS_WEEK)
GROUPS = {"culture": LANES, "commodities": COMMOD_LANES}


def fee(p, rate):
    return rate * p * (1 - p)


def _num(x):
    return D.number(x)


def _ts(raw):
    t = D.instant(raw)
    return int(t.timestamp()) if t else None


def _iso(ts):
    return dt.datetime.fromtimestamp(ts, dt.timezone.utc).isoformat()


def targets(price):
    """[(multiple, share, target)] for an entry price, each target capped at 0.98, in cents."""
    return [(m, w, round(min(price * m, CAP), 2)) for m, w in LEGS]


def entry_quote(candles, open_ts, cfg=STRICT, detail=False):
    """The first (minute) candle ending inside (open, open + 6h] whose closing quote has a spread of
    5c or less (the wide lane: 10c or less and a YES ask of 0.03-0.30) -> (end_ts, yes_bid, yes_ask,
    contracts traded from the open to then), or None. With detail, a 5th item: (the last trade at or
    before that minute, its candle's end) or (None, None)."""
    traded, last = 0.0, (None, None)
    for c in sorted(candles, key=lambda c: c.get("end_period_ts") or 0):
        end = c.get("end_period_ts")
        if not end or end <= open_ts:
            continue
        if end > open_ts + ENTRY_WINDOW_H * 3600:
            break
        traded += _num(c.get("volume_fp")) or 0.0
        no = cfg.get("side", "yes") == "no"
        px = _num((c.get("price") or {}).get("close_dollars"))
        if px is not None:
            last = (round(1 - px, 4) if no else px, end)
        bid = _num((c.get("yes_bid") or {}).get("close_dollars"))
        ask = _num((c.get("yes_ask") or {}).get("close_dollars"))
        if bid is None or ask is None or not 0 < ask <= 1 or ask - bid > cfg["spread"] + 1e-9:
            continue
        # A NO lane (album_cheap_no) buys the NO: its ask is 1 - the YES bid, its bid 1 - the YES ask.
        if no:
            bid, ask = round(1 - ask, 4), round(1 - bid, 4)
        band = cfg.get("band", BAND)
        if cfg["band_in_quote"] and not band[0] - 1e-9 <= ask <= band[1] + 1e-9:
            continue
        return (end, bid, ask, round(traded, 2)) + ((last,) if detail else ())
    return None


def fill_of(candles, entry_ts, target, side="yes"):
    """(end_ts, target) of the first candle after the entry whose traded high reaches the target. For
    a NO the traded NO high is 1 - the YES traded low: it fills when YES price.low <= 1 - target."""
    for c in sorted(candles, key=lambda c: c.get("end_period_ts") or 0):
        end = c.get("end_period_ts")
        if not end or end <= entry_ts:
            continue
        if side == "no":
            lo = _num((c.get("price") or {}).get("low_dollars"))
            hi = None if lo is None else 1 - lo
        else:
            hi = _num((c.get("price") or {}).get("high_dollars"))
        if hi is not None and hi >= target - 1e-9:
            return end, target
    return None


def book_size(book, price, side="yes"):
    """Contracts of `side` offered at or under `price`: the other side's bids at or over 1 - price."""
    levels = ((book or {}).get("orderbook_fp") or {}).get("yes_dollars" if side == "no" else "no_dollars") or []
    return round(sum(float(q) for p, q in levels if float(p) >= 1 - price - 1e-9), 2)


def settled_payout(m, side="yes"):
    """1 or 0 for `side` once Kalshi has settled the market, else None."""
    if m.get("status") in ("finalized", "settled") and m.get("result") in ("yes", "no"):
        return 1.0 if m["result"] == side else 0.0
    return None


def grade(e):
    """Fill in an entry's P/L once every leg is resolved (filled, or held to settlement). Per contract,
    after fees, ROI on the entry cost; beside it the same entry held to settlement and with the 2x
    leg only (the held figure once the market settles)."""
    cost = e["price"] + fee(e["price"], TAKER)
    proceeds = lambda leg: (leg["target"] - fee(leg["target"], MAKER) if leg.get("filled_at")
                            else leg.get("settled_px"))
    legs = e["legs"]
    if any(proceeds(l) is None for l in legs):
        e["status"] = "open"
        return e
    split = sum(l["share"] * proceeds(l) for l in legs) - cost
    e.update(status="settled" if e.get("payout") is not None else "filled",
             pnl=round(split, 4), roi=round(split / cost, 4), roi_2x=round((proceeds(legs[0]) - cost) / cost, 4))
    if e.get("payout") is not None:
        e["roi_held"] = round((e["payout"] - cost) / cost, 4)
    return e


def done(e):
    """Nothing left to happen to it: the market has settled (both legs filled still waits, for the
    held comparison)."""
    return e.get("payout") is not None


def load(path=None, cfg=STRICT):
    path = path or cfg["path"]
    try:
        with open(path) as f:
            s = json.load(f)
    except FileNotFoundError:
        s = {}
    s.setdefault("lane", cfg["lane"])
    s.setdefault("entries", [])
    s.setdefault("skips", {})
    s.setdefault("events", {})
    return s


def events(fetch, series=SERIES, open_only=False):
    return D.pages(f"events?series_ticker={series}{'&status=open' if open_only else ''}&with_nested_markets=true"
                   "&limit=200", "events", fetch)


def held_events(state, listed, fetch):
    """The events a lane holds an unsettled entry on that the open-events list no longer carries."""
    out = []
    for tick in sorted({e["event"] for e in state["entries"] if not done(e)} - set(listed)):
        d = fetch(f"events/{tick}?with_nested_markets=true")
        ev = dict(d.get("event") or {}, event_ticker=tick)
        ev["markets"] = (d.get("event") or {}).get("markets") or d.get("markets") or []
        out.append(ev)
    return out


def candles(event, start_ts, end_ts, fetch, minutes=60, series=SERIES):
    d = fetch(f"series/{series}/events/{event}/candlesticks?start_ts={start_ts}&end_ts={end_ts}"
              f"&period_interval={minutes}")
    return dict(zip(d.get("market_tickers") or [], d.get("market_candlesticks") or []))


def run(state, now=None, fetch=D.get, cfg=STRICT):
    now = now or dt.datetime.now(dt.timezone.utc)
    now_ts = int(now.timestamp())
    start_ts = _ts(cfg["start"])
    obs = dict(at=now.isoformat(), events=0, entered=0, skipped=0, filled=0, waiting=0)
    have = {e["id"] for e in state["entries"]}
    evs = events(fetch, cfg["series"], cfg.get("open_only", False))
    if cfg.get("open_only"):
        evs = evs + held_events(state, [x.get("event_ticker") for x in evs], fetch)
    for ev in evs:
        tick = ev.get("event_ticker")
        ms = [m for m in ev.get("markets") or [] if _ts(m.get("open_time"))]
        if not ms:
            continue
        if min(_ts(m["open_time"]) for m in ms) < start_ts:
            # A lane that backfills OPEN events (album_cheap_rungs): an event that opened before the
            # lane's start is taken only if it still had an open market when the lane first saw it,
            # and then kept (state["events"]) until everything on it settles.
            if not (cfg.get("backfill_open") and (tick in state["events"]
                                                  or any(m.get("status") in ("active", "open") for m in ms))):
                continue
            # backfill_days: only events opened that recently (older opening candles are not served).
            if (tick not in state["events"] and cfg.get("backfill_days") is not None
                    and min(_ts(m["open_time"]) for m in ms) < now_ts - cfg["backfill_days"] * 86400):
                continue
        state["events"].setdefault(tick, now.isoformat())
        obs["events"] += 1
        lo = min(_ts(m["open_time"]) for m in ms)
        cs, entry_cs = None, None
        mine = [e for e in state["entries"] if e["event"] == tick]
        pending = [m for m in ms if m["ticker"] not in have and m["ticker"] not in state["skips"]
                   and now_ts >= _ts(m["open_time"]) + 3600]
        if pending:
            # Minute candles per opening time (a ladder can add rungs days after its first ones).
            entry_cs = {}
            for o_ in sorted({_ts(m["open_time"]) for m in pending}):
                hi = min(now_ts, o_ + ENTRY_WINDOW_H * 3600 + 60)
                got = candles(tick, o_, hi - hi % 60, fetch, minutes=1, series=cfg["series"])
                for m in pending:
                    if _ts(m["open_time"]) == o_:
                        entry_cs[m["ticker"]] = got.get(m["ticker"]) or []
        if pending or any(not done(e) for e in mine):
            cs = candles(tick, lo, now_ts - now_ts % 60, fetch, series=cfg["series"])
        by = {m["ticker"]: m for m in ms}
        for m in pending:
            o = _ts(m["open_time"])
            q = entry_quote(entry_cs.get(m["ticker"]) or [], o, cfg, detail=True)
            word = (m.get("custom_strike") or {}).get("Word") or m.get("yes_sub_title") or m["ticker"]
            if q is None:
                if now_ts >= o + ENTRY_WINDOW_H * 3600:
                    state["skips"][m["ticker"]] = dict(event=tick, word=word, reason=cfg["skip"])
                    obs["skipped"] += 1
                else:
                    obs["waiting"] += 1
                continue
            end, bid, ask, vol, (last_px, last_at) = q
            band = cfg.get("band", BAND)
            if not band[0] - 1e-9 <= ask <= band[1] + 1e-9:
                state["skips"][m["ticker"]] = dict(event=tick, word=word, reason=f"YES ask {ask:.2f} outside 0.03-0.30",
                                                   at=_iso(end))
                obs["skipped"] += 1
                continue
            e = dict(id=m["ticker"], event=tick, word=word, side=cfg.get("side", "yes"), entry_at=_iso(end), price=ask,
                     bid=bid, spread=round(ask - bid, 4), traded_to_entry=vol, logged=now.isoformat(),
                     legs=[dict(multiple=mult, share=w, target=t) for mult, w, t in targets(ask)], payout=None)
            if cfg["last_trade"]:
                e.update(last_trade=last_px, last_trade_at=_iso(last_at) if last_at else None,
                         spread_cost=round(ask - last_px, 4) if last_px is not None else None)
            if now_ts - end <= LIVE_BOOK_H * 3600:
                try:
                    e["book_size"] = book_size(fetch(f"markets/{m['ticker']}/orderbook"), ask, cfg.get("side", "yes"))
                    e["book_at"] = now.isoformat()
                except Exception:                              # noqa: BLE001
                    e["book_size"] = None
            state["entries"].append(e)
            have.add(e["id"])
            mine.append(e)
            obs["entered"] += 1
        for e in mine:
            if done(e):
                continue
            c = [x for x in (cs or {}).get(e["id"]) or [] if (x.get("end_period_ts") or 0) <= now_ts]
            for leg in e["legs"]:
                if not leg.get("filled_at"):
                    f = fill_of(c, _ts(e["entry_at"]), leg["target"], e.get("side", "yes"))
                    if f:
                        leg["filled_at"], leg["fill_px"] = _iso(f[0]), f[1]
                        obs["filled"] += 1
            pay = settled_payout(by.get(e["id"]) or {}, e.get("side", "yes"))
            if pay is not None:
                e["payout"] = pay
                e["settled"] = e.get("settled") or now.isoformat()
                for leg in e["legs"]:
                    if not leg.get("filled_at"):
                        leg["settled_px"] = pay
            grade(e)
    state["observations"] = obs
    state["last_success"] = now.isoformat()
    state["error"] = None
    return state


# ------------------------------------------------------------------ the record
def record(entries):
    """The lane's record over entries whose split is resolved: n, legs filled at 2x / 3x, and the ROI
    after fees (mean over entries, equal stake) for the split, the same entries held, and 2x only."""
    graded = [e for e in entries if e.get("roi") is not None]
    held = [e["roi_held"] for e in graded if e.get("roi_held") is not None]
    two = [e["roi_2x"] for e in graded if e.get("roi_2x") is not None]
    mean = lambda xs: sum(xs) / len(xs) if xs else None
    return dict(entries=len(entries), resolved=len(graded), won=sum(e.get("payout") == 1 for e in entries),
                settled=sum(e.get("payout") is not None for e in entries),
                filled_2x=sum(bool(e["legs"][0].get("filled_at")) for e in entries),
                filled_3x=sum(bool(e["legs"][1].get("filled_at")) for e in entries),
                roi=mean([e["roi"] for e in graded]), roi_held=mean(held), n_held=len(held),
                roi_2x=mean(two), n_2x=len(two))


def weeks(entries):
    out = {}
    for e in entries:
        out.setdefault(e["event"], []).append(e)
    return [(k, record(v)) for k, v in sorted(out.items(), reverse=True)]


def main(argv=None):
    import sys
    argv = sys.argv[1:] if argv is None else argv
    for cfg in GROUPS[argv[0] if argv else "culture"]:
        state = load(cfg=cfg)
        try:
            run(state, cfg=cfg)
        except Exception as e:                                 # noqa: BLE001
            state["error"] = (type(e).__name__ + ": " + str(e))[:300]
        os.makedirs(os.path.dirname(cfg["path"]), exist_ok=True)
        tmp = cfg["path"] + ".tmp"
        with open(tmp, "w") as f:
            json.dump(state, f, indent=1, sort_keys=True)
            f.write("\n")
        os.replace(tmp, cfg["path"])
        o = state.get("observations") or {}
        print(cfg["lane"], "entries", len(state["entries"]), "skips", len(state["skips"]), "this run", o,
              "error", state.get("error"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


# ------------------------------------------------------------------ the Culture page card
def _pct(x):
    return "—" if x is None else f"{x * 100:+.1f}%".replace("-", "−")


def _px(x):
    return "—" if x is None else f"{x:.2f}".replace("-", "\u2212")


def compare(strict, wide, esc, anchor="mentions-split-compare", title="Strict v wide"):
    """Strict v wide, one line: entries, ROI after fees, average spread paid (ask - bid at entry)."""
    def part(name, st):
        es = st.get("entries") or []
        r = record(es)
        sp = [e["spread"] for e in es if e.get("spread") is not None]
        return (f"{name}: {r['entries']} entr{'y' if r['entries'] == 1 else 'ies'}, ROI after fees {_pct(r['roi'])} "
                f"({r['resolved']} resolved), average spread paid {_px(sum(sp) / len(sp)) if sp else '—'}")
    return (f'<p class="sm" id="{anchor}"><b>{esc(title)}</b> · {esc(part("strict (5c)", strict))} · '
            f'{esc(part("wide (10c)", wide))}.</p>')


def _pl(x):
    return "—" if x is None else f"{x:+.3f}".replace("-", "\u2212")


def section(state, esc, cfg=STRICT):
    """The lane's card on the Culture page: tiles, per-week rows and the trade list."""
    es = state.get("entries") or []
    r = record(es)
    o = state.get("observations") or {}
    # One tile set for every cheap-side card (the Culture page redo, 2026-10-27).
    shown = (("entries", r["entries"]), ("settled", r["settled"]), ("won", r["won"]),
             ("ROI after fees · split", _pct(r["roi"])), ("ROI after fees · held", _pct(r["roi_held"])),
             ("legs filled 2x / 3x", f'{r["filled_2x"]} / {r["filled_3x"]}'))
    tiles = "".join(f'<div class="tile"><b>{esc(str(v))}</b><span>{esc(k)}</span></div>' for k, v in shown)
    wk = "".join(f'<tr><td>{esc(k)}</td><td class="num">{w["entries"]}</td><td class="num">{w["filled_2x"]}</td>'
                 f'<td class="num">{w["filled_3x"]}</td><td class="num">{w["resolved"]}</td>'
                 f'<td class="num">{_pct(w["roi"])}</td><td class="num">{_pct(w["roi_held"])}</td>'
                 f'<td class="num">{_pct(w["roi_2x"])}</td></tr>' for k, w in weeks(es))
    leg = lambda l: (f'{l["target"]:.2f} filled {esc(l["filled_at"][:16].replace("T", " "))}Z' if l.get("filled_at")
                     else f'{l["target"]:.2f} held, settled {l["settled_px"]:.0f}' if l.get("settled_px") is not None
                     else f'{l["target"]:.2f} resting')
    size = lambda e: (f'{e["traded_to_entry"]:g} traded to entry' if e.get("traded_to_entry") is not None else "") + (
        f' · {e["book_size"]:g} on the book' if e.get("book_size") is not None else "")
    trades = "".join(
        f'<tr><td>{esc(e["event"].rsplit("-", 1)[-1])}</td><td>{esc(e["word"])}</td>'
        f'<td>{esc(e["entry_at"][:16].replace("T", " "))}Z</td><td class="num">{e["price"]:.2f}</td>'
        + f'<td class="num">{_px(e.get("last_trade"))}</td><td class="num">{_px(e.get("spread_cost"))}</td>' +
        f'<td>{esc(size(e))}</td><td>{esc(leg(e["legs"][0]))}</td><td>{esc(leg(e["legs"][1]))}</td>'
        f'<td class="num">{_pl(e.get("pnl"))}</td>'
        f'<td class="num">{_pct(e.get("roi"))}</td></tr>'
        for e in sorted(es, key=lambda e: e["entry_at"], reverse=True))
    skips = state.get("skips") or {}
    why = {}
    for v in skips.values():
        k = cfg["skip"] if v["reason"].startswith("no quote") else "YES ask outside 0.03-0.30"
        why[k] = why.get(k, 0) + 1
    unit, item = cfg.get("unit", "Week"), cfg.get("item", "Word")
    head = (f'<thead><tr><th>{unit}</th><th class="num">Entries</th><th class="num">2x filled</th><th class="num">3x filled</th>'
            '<th class="num">Resolved</th><th class="num">ROI split</th><th class="num">Held</th><th class="num">2x only</th></tr></thead>')
    thead = (f'<thead><tr><th>{unit}</th><th>{item}</th><th>Entry (UTC)</th><th class="num">{cfg.get("side", "yes").upper()} ask paid</th>'
             + '<th class="num">Last trade</th><th class="num">Cost of the spread</th>'
             + '<th>Size</th><th>2x leg</th><th>3x leg</th><th class="num">P/L per contract</th><th class="num">ROI</th></tr></thead>')
    cols = 11
    return (f'<section class="lane-card" id="{cfg["anchor"]}"><h3>{esc(cfg["label"])}</h3>'
            f'<p class="sm"><b>Sandbox · paper · fresh record from its first entry · review at {REVIEW_AT}, decide at '
            f'{DECIDE_AT}</b> ({r["resolved"]} resolved). Registered {cfg["registered"]}; {cfg["backfill"]}.</p>'
            f'<p class="sm">{esc(cfg["rule"])}</p><div class="tiles">{tiles}</div>'
            '<p class="sm mut">ROI is per contract after fees, the mean over resolved entries (equal stake per entry). '
            'Held: the same entries to settlement. 2x only: the same entries with one sell at 2x.</p>'
            f'<div class="tbl"><table>{head}<tbody>{wk or "<tr><td colspan=8>No entry yet.</td></tr>"}</tbody></table></div>'
            f'<div class="tbl"><table>{thead}<tbody>{trades or f"<tr><td colspan={cols}>No entry yet.</td></tr>"}</tbody></table></div>'
            f'<p class="sm mut">Words skipped: {len(skips)}'
            + (" (" + "; ".join(f"{k}: {v}" for k, v in sorted(why.items())) + ")" if why else "")
            + (f'. Last read {esc(str(state.get("last_success"))[:16].replace("T", " "))}Z' if state.get("last_success") else ". Not read yet")
            + (f' · {esc(state["error"])}' if state.get("error") else "") + '.</p></section>')


# ------------------------------------------------------------------ shared page parts (2026-10-27)
def status(settled):
    """Where a lane stands against the review rule: review at 10 settled, decide at 30."""
    if settled >= DECIDE_AT:
        return f"{settled} settled · decide now (30 reached)"
    if settled >= REVIEW_AT:
        return f"{settled} settled · review due (10 reached) · decide at 30"
    return f"{settled} settled · review at 10, decide at 30"


def avg_spread(state):
    sp = [e["spread"] for e in state.get("entries") or [] if e.get("spread") is not None]
    return sum(sp) / len(sp) if sp else None


def _sp(x):
    return _px(x) if x is not None else "—"


def summary(cfgs, states, esc, pairs=()):
    """The cheap-side summary table: one row per lane in `cfgs` (states keyed by lane id), then, for each
    (strict, wide, name) in `pairs`, the strict v wide average spread paid."""
    rows = []
    for cfg in cfgs:
        st = states[cfg["lane"]]
        r = record(st.get("entries") or [])
        rows.append(
            f'<tr><td><a href="#{esc(cfg["anchor"])}">{esc(cfg["label"])}</a></td>'
            f'<td class="num">{r["entries"]}</td><td class="num">{r["settled"]}</td><td class="num">{r["won"]}</td>'
            f'<td class="num">{_pct(r["roi"])}</td><td class="num">{_pct(r["roi_held"])}</td>'
            f'<td class="num">{r["filled_2x"]} / {r["filled_3x"]}</td><td class="num">{_sp(avg_spread(st))}</td>'
            f'<td>{esc(status(r["settled"]))}</td></tr>')
    spread_line = "".join(
        f'{w}, strict v wide average spread paid {_sp(avg_spread(states[a["lane"]]))} v '
        f'{_sp(avg_spread(states[b["lane"]]))}. '
        for a, b, w in pairs)
    return ('<div class="tbl"><table class="culture-summary"><thead><tr><th>Lane</th><th class="num">Entries</th>'
            '<th class="num">Settled</th><th class="num">Won</th><th class="num">Split ROI</th><th class="num">Hold ROI</th>'
            '<th class="num">Legs filled 2x / 3x</th><th class="num">Avg spread paid</th><th>Status</th></tr></thead>'
            f'<tbody>{"".join(rows)}</tbody></table></div>'
            f'<p class="sm mut" id="spread-paid">{esc(spread_line)}ROI is after fees, the mean per entry (equal '
            'stake); split ROI counts entries whose two legs are resolved, hold ROI entries whose market has '
            'settled.</p>')


_esc = lambda x: _html.escape(str(x), quote=True)
_TABLE = re.compile(r"<table([^>]*)>(.*?)</table>", re.S)


def label_cells(page):
    """Name every body cell for its column (data-l), for the phone layout, which stacks each row into
    a card under 760px. sandbox_build.label_cells leaves tables that already have a <thead> alone,
    and every table here has one, so the Culture page labels its own (one header row, no colspans
    except a full-width "No entry yet." row, which is left as it is)."""
    def table(m):
        body = m.group(2)
        heads = [re.sub(r"<[^>]+>", "", x) for x in re.findall(r"<th[^>]*>(.*?)</th>", body.split("</thead>", 1)[0], re.S)]
        if "</thead>" not in body:
            return m.group(0)
        head, rest = body.split("</thead>", 1)

        def row(rm):
            cells = iter(heads)
            return re.sub(r"<td(?![^>]*colspan)([^>]*)>", lambda c: f'<td{c.group(1)} data-l="{_esc(next(cells, ""))}">',
                          rm.group(0))
        return f"<table{m.group(1)}>{head}</thead>" + re.sub(r"<tr>.*?</tr>", row, rest, flags=re.S) + "</table>"
    return _TABLE.sub(table, page)
