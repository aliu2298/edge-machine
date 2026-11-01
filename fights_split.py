"""Fights: two Sandbox PAPER lanes on the cheap side + resting take-profit standard (2026-10-26, Olu).

  boxing_cheap_dog   Kalshi KXBOXING (boxing match winner): the fighter whose YES ask is 0.03-0.15
                     with a spread of 5c or less, about one hour before the fight starts.
  ufc_dog            Kalshi KXUFCFIGHT: the fighter whose YES ask is 0.15-0.30, spread 5c or less,
                     about one hour before the fight starts.

THE STANDARD is mentions_split.py's (Culture and Commodities pages): buy the cheap side at the real
ask, rest a split sell (half at 2x, half at 3x of the ask paid, each capped at 0.98), a leg fills
ONLY when a TRADE prints at or above its target (the MINUTE candle's price.high_dollars, never the
bid high), an unfilled leg is held to settlement, HOLD is recorded on the same entries, taker fee
0.07 p(1-p) in, maker fee 0.0175 p(1-p) out. This module reuses its targets, fills, grading, record,
card and summary; only the entry differs, because a fight has a start rather than an open.

THE START. Kalshi publishes each fight's scheduled start as a milestone (milestones endpoint,
related_event_ticker; type boxing_match / mma_match; start_date). That is the clock a live system
would have, so the entry is replayed from it, never from the price path: the first minute candle
ending in the 15 minutes after (start - 60 minutes) whose closing quote has a spread of 5c or less
and whose YES ask is in the lane's band. No such minute: the fighter is skipped, with the reason.
Only candles up to the entry minute are read for the entry; the start only places that minute on
the clock. A schedule can move: until its entry window has passed a fight's milestone is re-read
each run when it is under four hours away.

RECORD per entry: the ask paid, the spread, the last trade at or before the entry minute (and the
cost of the spread, ask - last trade), the contracts traded from the window's start to the entry,
the YES contracts offered at or under the ask on the book when it is read before the fight, and,
for EVERY FILL, the contracts traded in that minute (leg.fill_volume), so the page shows whether
real size traded at the target. Boxing is the lane that exists for that question.

HOURLY: fights.yml reads every open fight (and any it still holds an unsettled entry on). Entry is
replayed from the minute candles after the fact, so no window stamp is needed. BACKFILL: a fight
still open when a lane first runs is replayed from its candles if its entry minute is within six
days (older minute candles are no longer served). Each lane has its own ledger and a fresh record.

Research basis (Olu): boxing, 134 matches, 31 entries at 3-15c, 0 won, but 24 traded 2x at some
point: split +53% (z 3.0) if brief in-fight spikes fill, -81% counting only hourly closes. UFC, 169
fights, 16 entries at 15-30c, 8 won: hold +97%, split +28% (hourly-close version +18%). Review at
10 settled events (fights), decide at 30. An entry counts only when its ask was there (mentions_split's
entry-validity rule, 2026-10-30): a book of 10+ at entry, or 10+ traded through it within 60 minutes.
"""
import datetime as dt
import json
import os

import daily_track as D
import mentions_split as MS

ROOT = os.path.dirname(os.path.abspath(__file__))
REGISTERED = "2026-10-26"
ENTRY_LEAD_MIN = 60                     # buy about this long before the scheduled start
ENTRY_GRACE_MIN = 15                    # ... at the first qualifying minute in this window
REFRESH_H = 4                           # re-read a fight's schedule while its entry window is under this far off
BACKFILL_DAYS = 6
MAX_SPREAD = 0.05
CHUNK_MIN = 3000                        # minute candles per request

_BASIS = ("About one hour before a fight's scheduled start (Kalshi's milestone), the first minute in the next "
          "15 with a spread of 5c or less and a YES ask of {lo}-{hi}: buy that fighter YES at the ask. A split "
          "resting sell placed at entry: half at 2x, half at 3x the ask paid, each capped at 0.98. A leg fills "
          "only when a trade prints at or above its target (the minute candle's traded high, never the bid); an "
          "unfilled leg is held to settlement. HOLD is recorded on the same entries. Taker fee in, maker fee "
          "out.")
BOXING = dict(
    lane="boxing_cheap_dog", label="Boxing · cheap dog (3-15c)", series="KXBOXING", band=(0.03, 0.15),
    path=os.path.join(ROOT, "data", "boxing_cheap_dog_ledger.json"), spread=MAX_SPREAD, band_in_quote=True,
    registered=REGISTERED, start="2026-10-26T00:00:00+00:00", anchor="boxing-cheap-dog",
    rule="KXBOXING (boxing match winner) only. " + _BASIS.format(lo="0.03", hi="0.15")
         + " Every fill records the traded volume of its minute.",
    skip="no quote with a 5c spread and a YES ask of 0.03-0.15 in the hour-before window",
    outside_text="YES ask outside 0.03-0.15", skipped_noun="Fighters", unit="Fight", item="Fighter",
    last_trade=True, side="yes", compare_id=None, hold_variant=True,
    backfill="fights still open when the lane first ran are replayed from their minute candles where Kalshi "
             "still serves them (entry minute within six days)",
    research="Research (134 matches): 31 entries, 0 won, but 24 traded at 2x or more at some point. Split +53% "
             "(z 3.0) if brief in-fight spikes fill; -81% counting only hourly closes. This lane exists to measure "
             "whether minute-level spikes really fill, so every fill records the traded volume of its minute.")
UFC = dict(
    BOXING, lane="ufc_dog", label="UFC · dog (15-30c)", series="KXUFCFIGHT", band=(0.15, 0.30),
    path=os.path.join(ROOT, "data", "ufc_dog_ledger.json"), anchor="ufc-dog",
    rule="KXUFCFIGHT (UFC fight winner) only. " + _BASIS.format(lo="0.15", hi="0.30"),
    skip="no quote with a 5c spread and a YES ask of 0.15-0.30 in the hour-before window",
    outside_text="YES ask outside 0.15-0.30",
    research="Research (169 fights): 16 entries, 8 won. Hold +97%; split +28% (the hourly-close version +18%). "
             "HOLD and SPLIT are shown side by side.")
LANES = (BOXING, UFC)


def _ts(raw):
    return MS._ts(raw)


def _iso(ts):
    return MS._iso(ts)


def load(cfg):
    st = MS.load(cfg=cfg)
    st.setdefault("starts", {})
    return st


def milestone_start(event, fetch):
    """The scheduled start (epoch seconds) of the one boxing / MMA milestone that names `event`, or None.
    Zero milestones is a missing start; more than one is ambiguous, and both give None."""
    d = fetch(f"milestones?related_event_ticker={event}&limit=10")
    found = [m for m in (d.get("milestones") or []) if event in (m.get("related_event_tickers") or [])
             or event in (m.get("primary_event_tickers") or [])]
    found = [m for m in found if m.get("type") in ("boxing_match", "mma_match") and _ts(m.get("start_date"))]
    return _ts(found[0]["start_date"]) if len(found) == 1 else None


def fight_start(state, event, now_ts, fetch, entered=False):
    """The fight's start, from the cache; read from the milestone the first time and, while the entry
    window is still ahead or just behind, again each run once the fight is under REFRESH_H away."""
    cached = state["starts"].get(event)
    c_ts = _ts(cached) if cached else None
    if c_ts is not None and (entered or now_ts < c_ts - REFRESH_H * 3600 or now_ts >= c_ts - (ENTRY_LEAD_MIN - ENTRY_GRACE_MIN) * 60):
        return c_ts
    got = milestone_start(event, fetch)
    if got is not None:
        state["starts"][event] = _iso(got)
        return got
    return c_ts


def minute_candles(event, lo, hi, fetch, series):
    """{ticker: [minute candles]} from lo to hi, in requests of at most CHUNK_MIN minutes."""
    out, a = {}, lo
    while a < hi:
        b = min(hi, a + CHUNK_MIN * 60)
        for t, cs in MS.candles(event, a, b, fetch, minutes=1, series=series).items():
            out.setdefault(t, []).extend(cs)
        a = b
    return out


def entry_for(cs, start_ts, cfg):
    """(end_ts, bid, ask, traded, (last trade, its end)) for the entry, or None: the first minute candle
    ending after start - 60 minutes and within ENTRY_GRACE_MIN of it, never at or after the start, whose
    closing quote is tight and in the band. Candles past the window are not read."""
    lo = start_ts - ENTRY_LEAD_MIN * 60
    hi = min(lo + ENTRY_GRACE_MIN * 60, start_ts - 60)
    return MS.entry_quote([c for c in cs if (c.get("end_period_ts") or 0) <= hi], lo, cfg, detail=True)


def list_events(fetch, series, now_ts):
    """The events a run evaluates: every open one, plus those that closed or settled within BACKFILL_DAYS.

    Listing only open events missed any fight that started and finalized between two runs (GitHub's hourly cron
    ran 6 times in 24 hours on 2026-10-31, and 11 fights were never seen): an entry is replayed from the minute
    candles, which are served for BACKFILL_DAYS, so a settled fight whose entry minute is still served is
    evaluated exactly once like any other (an entry or a skip, legs from the prints, then settled)."""
    opened = MS.events(fetch, series, open_only=True)
    seen = {e.get("event_ticker") for e in opened}
    since = now_ts - (BACKFILL_DAYS + 1) * 86400
    recent = D.pages(f"events?series_ticker={series}&status=closed,settled&min_close_ts={since}"
                     "&with_nested_markets=true&limit=200", "events", fetch)
    return opened + [e for e in recent if e.get("event_ticker") not in seen]


def run(state, now=None, fetch=D.get, cfg=BOXING, ask_rule=True):
    now = now or dt.datetime.now(dt.timezone.utc)
    now_ts = int(now.timestamp())
    state.setdefault("starts", {})
    obs = dict(at=now.isoformat(), events=0, entered=0, skipped=0, filled=0, waiting=0, no_start=0)
    have = {e["id"] for e in state["entries"]}
    listed = list_events(fetch, cfg["series"], now_ts)
    evs = listed + MS.held_events(state, [x.get("event_ticker") for x in listed], fetch)
    for ev in evs:
        tick = ev.get("event_ticker")
        ms = [m for m in ev.get("markets") or [] if m.get("ticker")]
        if not ms:
            continue
        mine = [e for e in state["entries"] if e["event"] == tick]
        start_ts = fight_start(state, tick, now_ts, fetch, entered=bool(mine))
        if start_ts is None:
            obs["no_start"] += 1
            continue
        if tick not in state["events"] and start_ts - ENTRY_LEAD_MIN * 60 < now_ts - BACKFILL_DAYS * 86400:
            continue                                          # its entry minute candles are no longer served
        if tick not in state["events"] and start_ts < _ts(REGISTERED + "T00:00:00+00:00"):
            continue                                          # before the lane existed: the record starts fresh
        lo = start_ts - ENTRY_LEAD_MIN * 60
        window_end = lo + ENTRY_GRACE_MIN * 60
        pending = [m for m in ms if m["ticker"] not in have and m["ticker"] not in state["skips"]]
        if pending and now_ts < window_end + 60:
            obs["waiting"] += 1                               # the entry window is not over yet
            pending = []
        if not pending and not any(not MS.done(e) for e in mine):
            continue
        state["events"].setdefault(tick, now.isoformat())
        obs["events"] += 1
        by = {m["ticker"]: m for m in ms}
        need_lo = min([lo - 60] + [(_ts(e["entry_at"]) or lo) - 60 for e in mine if not MS.done(e)])
        cs = minute_candles(tick, need_lo, now_ts - now_ts % 60, fetch, cfg["series"]) if (pending or mine) else {}
        for m in pending:
            word = m.get("yes_sub_title") or m["ticker"]
            q = entry_for(cs.get(m["ticker"]) or [], start_ts, cfg)
            if q is None:
                if not cs.get(m["ticker"]) and now_ts < window_end + 3600:
                    obs["waiting"] += 1                       # candles may lag; look again next hour
                else:
                    state["skips"][m["ticker"]] = dict(event=tick, word=word, reason=cfg["skip"], start=_iso(start_ts))
                    obs["skipped"] += 1
                continue
            end, bid, ask, vol, (last_px, last_at) = q
            e = dict(id=m["ticker"], event=tick, word=word, side="yes", entry_at=_iso(end), price=ask, bid=bid,
                     spread=round(ask - bid, 4), traded_to_entry=vol, logged=now.isoformat(),
                     fight_start=_iso(start_ts), minutes_to_start=round((start_ts - end) / 60, 1),
                     last_trade=last_px, last_trade_at=_iso(last_at) if last_at else None,
                     spread_cost=round(ask - last_px, 4) if last_px is not None else None,
                     legs=[dict(multiple=mult, share=w, target=t) for mult, w, t in MS.targets(ask)], payout=None)
            if now_ts < start_ts:                             # the book only means something before the fight
                # The book as the engine takes the entry (2026-10-30): verifies the ask when it shows MS.MIN_SIZE.
                try:
                    e["book"] = MS.book_snapshot(fetch(f"markets/{m['ticker']}/orderbook"), ask, "yes", now.isoformat())
                    e["book_size"], e["book_at"] = e["book"]["at_or_under"], now.isoformat()
                except Exception:                              # noqa: BLE001
                    e["book_size"] = None
            state["entries"].append(e)
            have.add(e["id"])
            mine.append(e)
            obs["entered"] += 1
        for e in mine:
            if MS.done(e):
                continue
            c = [x for x in cs.get(e["id"]) or [] if (x.get("end_period_ts") or 0) <= now_ts]
            for leg in e["legs"]:
                if not leg.get("filled_at"):
                    f = MS.fill_of(c, _ts(e["entry_at"]), leg["target"], "yes", detail=True)
                    if f:
                        leg["filled_at"], leg["fill_px"], leg["fill_volume"] = _iso(f[0]), f[1], f[2]
                        obs["filled"] += 1
            pay = MS.settled_payout(by.get(e["id"]) or {}, "yes")
            if pay is not None:
                e["payout"] = pay
                e["settled"] = e.get("settled") or now.isoformat()
                for leg in e["legs"]:
                    if not leg.get("filled_at"):
                        leg["settled_px"] = pay
            MS.grade(e)
    # The entry-validity rule (2026-10-30), as on the Culture and Commodities lanes.
    errs = MS.check_asks(state, now, fetch, cfg) if ask_rule else []
    obs.update(unverified=sum(MS.check_status(e) == "unverified" for e in state["entries"]))
    state["observations"] = obs
    state["last_success"] = now.isoformat()
    state["error"] = ("ask check: " + "; ".join(errs))[:300] if errs else None
    return state


def main(argv=None):
    for cfg in LANES:
        state = load(cfg)
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
