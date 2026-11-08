"""The NBA win margin lanes in Production (2026-11-03, Olu, Nov 2): the feeds the follower's executor reads, and the Production
page's pairs. Moved by hand: Win margin YES split (nba_winmargin_live, the chaos lane) and Win margin NO fade (nba_wm_nofade).

The paper lanes keep running unchanged. This file only LISTS the games the live rules apply to, from Kalshi's open win margin
markets (KXNBAWINMARGIN, every bucket of every game), tip = the KXNBAGAME market's expected_expiration_time minus 3 hours (the
tracker's rule). The follower owns every order and pins the money terms itself: it refuses a lead whose terms differ.

  YES split   an hour before the tip, buy YES of a 1-5, 6-10 or 11-20 bucket at the ask when the ask is 10-20c, the spread 5c or less
              and the ask is real (the ask check), and the game's favourite has a pregame win share under 70%; from the tip on rest a
              post-only sell for half at 2x and half at 2.5x of the price paid (a leg fills only on a print through it); the rest is
              held. Unfilled sells are cancelled when the market closes. (Version 4, from the night of 2026-11-08; version 3 was 1-5 and
              6-10 with no matchup skip and sells at 2x and 3x.)
  NO fade     an hour before the tip read P, the NO price (1 - the YES bid; spread 5c or less, P 10-95c). From the tip on rest a
              post-only NO bid at 65% of P (version 3: 75%); when it fills, rest a post-only sell of the NO at P; cancel what is unfilled when the
              market closes; hold an unsold position. A bid that would cross at the tip (the NO price already at or under it) is no
              entry and is never re-posted.

The record on the pages is the replay of the executor's own decisions (nba_wm_v4prod.py, fills from prints) plus its live fills; the older
paper record is version 2 of each lane (strict print-through fills, the post-only cross): paper equals what the follower can do.
Written hourly by the nba-wm-nofade workflow and restamped by the feeds heartbeat. It writes only data/production_nba_wm_*_leads.json.
"""
import datetime as dt
import os
import sys

import chaos_replay as C
import daily_track as D
import nba_winmargin as W
import nba_wm_nofade as N
import nba_wm_v3 as V3
import nba_wm_v4prod as V4P
import production as P

ROOT = os.path.dirname(os.path.abspath(__file__))
YES_PATH = os.path.join(ROOT, "data", "production_nba_wm_leads.json")
NO_PATH = os.path.join(ROOT, "data", "production_nba_wm_nofade_leads.json")
YES_LANE, NO_LANE = "nba_winmargin_live", N.LANE
YES_NAME, NO_NAME = "Win margin YES split (v2)", "Win margin NO fade (v2)"
YES_VERSION, NO_VERSION = V4P.YES_VERSION, V4P.NO_VERSION        # the feeds carry the version the executor pins (v3 from 2026-11-03, v4 from 2026-11-08)
# Version 3 (the executor's own decision snapshots as the entries, nba_wm_v3.py): from its first night the record is v3 and v2 is kept as its own
# labelled block, so there are four pairs, each with its own source id.
YES3_LANE, NO3_LANE = "nba_winmargin_v3", "nba_wm_nofade_v3"
YES3_NAME, NO3_NAME = "Win margin YES split (v3)", "Win margin NO fade (v3)"
# Version 4 (2026-11-08, Olu: the version with the better ROI goes to Production): the same wire lanes, new Production pairs and a fresh record
# from the first night a v4 decision exists (nba_wm_v4prod.py). Version 3's two pairs move into the "Older versions" fold with version 2's.
YES4_LANE, NO4_LANE = "nba_winmargin_v4", "nba_wm_nofade_v4"
YES4_NAME, NO4_NAME = "Win margin YES split (v4)", "Win margin NO fade (v4)"
SWITCH_ON = V4P.SWITCH_ON
MOVED_ON = "2026-11-02"
PROMOTED = "2026-11-02T22:00:00+00:00"        # before the first live order (23:00Z on the first night)
SPORT = "nba_wm"
STAKE_USD = 1.0
YES_BUCKETS = V4P.BUCKETS
YES_MAX_FAV_SHARE = V4P.MAX_FAV_SHARE
YES_BAND = (0.10, 0.20)
YES_MAX_SPREAD = 0.05
YES_SELLS = V4P.SELLS
SELL_CAP = 0.98
NO_DIP = V4P.NO_DIP
NO_P_RANGE = N.P_RANGE
NO_MAX_SPREAD = N.MAX_SPREAD
NO_MIN_LIMIT = N.MIN_LIMIT
LOOKAHEAD_H = 30
GRACE_MIN = 240                 # a started game stays listed through its market close (tip + about 3h)
SKIP_FRESH_MIN = 20
HEALTHY_HOURS = 3
UTC = dt.timezone.utc

YES_RULE = dict(side="yes", entry_before_tip_min=60, band=list(YES_BAND), max_spread=YES_MAX_SPREAD, buckets=list(YES_BUCKETS),
                sells=[dict(multiple=m, share=w) for m, w in YES_SELLS], sell_cap=SELL_CAP, sells_from="tip", stake_usd=STAKE_USD,
                max_favourite_share=YES_MAX_FAV_SHARE)
NO_RULE = dict(side="no", read_before_tip_min=60, bid_from="tip", dip=NO_DIP, p_range=list(NO_P_RANGE), max_spread=NO_MAX_SPREAD,
               min_limit=NO_MIN_LIMIT, sell="pregame", post_only=True, stake_usd=STAKE_USD)


def _tip(suf, fetch):
    """The tip (epoch seconds) of one game: KXNBAGAME's expected_expiration_time minus 3 hours, or None."""
    ms = D.pages(f"markets?limit=5&event_ticker=KXNBAGAME-{suf}", "markets", fetch)
    t = next((x for x in (W._ts(m.get("expected_expiration_time")) for m in ms) if x), None)
    return None if t is None else t - W.TIP_BACK_H * 3600


def games(now, fetch=D.get):
    """[(event, tip, [market])] for every open win margin game whose tip is inside the window, soonest first; plus errors."""
    out, errors = [], []
    lo, hi = now - dt.timedelta(minutes=GRACE_MIN), now + dt.timedelta(hours=LOOKAHEAD_H)
    try:
        events = D.pages(f"events?series_ticker={W.SERIES}&status=open&limit=200&with_nested_markets=true", "events", fetch)
    except Exception as e:                                       # noqa: BLE001
        return [], [f"{W.SERIES}: {str(e)[:80]}"]
    for ev in events:
        tick = ev.get("event_ticker") or ""
        try:
            tip = _tip(tick.split("-", 1)[1], fetch)
        except Exception as e:                                   # noqa: BLE001
            errors.append(f"{tick}: {str(e)[:80]}")
            continue
        if tip is None or not lo.timestamp() <= tip <= hi.timestamp():
            continue
        ms = [m for m in ev.get("markets") or [] if m.get("status") in ("active", "open") and not m.get("result")]
        if ms:
            out.append((tick, tip, ms))
    return sorted(out, key=lambda g: g[1]), errors


def _lead(lane, version, tick, tip, m, rule):
    code = m["ticker"].rsplit("-", 1)[-1]
    return dict(id=f"{lane}:{m['ticker']}", lane=lane, version=version, event=tick, ticker=m["ticker"], team=code[:3],
                bucket=W.bucket_of(m.get("yes_sub_title")), title=m.get("yes_sub_title") or m["ticker"],
                tip=dt.datetime.fromtimestamp(tip, UTC).isoformat(), side=rule["side"], stake_usd=STAKE_USD)


def feeds(now, fetch=D.get):
    """(yes feed, no feed): one lead per bucket contract of every game in the window (the follower decides at the tip
    minus an hour, from the live book, which of them qualify)."""
    gs, errors = games(now, fetch)
    stamp = now.replace(microsecond=0).isoformat()
    yes = dict(lane=YES_LANE, name=YES_NAME, version=YES_VERSION, moved_on=MOVED_ON, updated_at=stamp, rule=YES_RULE, errors=errors, leads=[])
    no = dict(lane=NO_LANE, name=NO_NAME, version=NO_VERSION, moved_on=MOVED_ON, updated_at=stamp, rule=NO_RULE, errors=errors, leads=[])
    for tick, tip, ms in gs:
        for m in ms:
            if W.bucket_of(m.get("yes_sub_title")) in YES_BUCKETS:
                yes["leads"].append(_lead(YES_LANE, YES_VERSION, tick, tip, m, YES_RULE))
            no["leads"].append(_lead(NO_LANE, NO_VERSION, tick, tip, m, NO_RULE))
    return yes, no


# --- the Production page ---------------------------------------------------------------------------------------
def v3_since(v3):
    """The first night of version 3 (the first night a decision snapshot exists), or None before it."""
    return (v3 or {}).get("since")


def v4_since(v4):
    """The first night of version 4 (the first night an executor decision pinned to wm-*-v4 exists), or None before it."""
    return (v4 or {}).get("since")


def pairs(v3=None, v4=None):
    """The Production pairs: version 2 from MOVED_ON; version 3, once it has started, from its own first night (2026-11-04, not the day the
    lanes first went live), so its 'moved' date and its since-Production window are its own; version 4 the same, from its first night."""
    out = {f"{lane}|{SPORT}": dict(stage="production", ready_at=PROMOTED, promoted_at=PROMOTED, by_hand=MOVED_ON) for lane in (YES_LANE, NO_LANE)}
    for since, lanes in ((v3_since(v3), (YES3_LANE, NO3_LANE)), (v4_since(v4), (YES4_LANE, NO4_LANE))):
        if since:
            start = f"{since}T00:00:00+00:00"
            out.update({f"{lane}|{SPORT}": dict(stage="production", ready_at=start, promoted_at=start, by_hand=since) for lane in lanes})
    return out


def older_pairs(v3=None, v4=None):
    """The pairs that ended when the next version started, kept on the page in an 'Older versions' fold: version 2's two once version 3
    started, and version 3's two as well once version 4 has. Empty before version 3."""
    out = set()
    if v3_since(v3) or v4_since(v4):
        out |= {f"{lane}|{SPORT}" for lane in (YES_LANE, NO_LANE)}
    if v4_since(v4):
        out |= {f"{lane}|{SPORT}" for lane in (YES3_LANE, NO3_LANE)}
    return out


def current_version(v3=None, v4=None):
    """"v4", "v3" or "v2": the version Production is on, from the ledgers' first nights."""
    return "v4" if v4_since(v4) else ("v3" if v3_since(v3) else "v2")


def _team_bucket(ticker):
    code = ticker.rsplit("-", 1)[-1]
    import re
    m = re.match(r"([A-Z]+?)(\d+TO\d+|\d+PLUS|\d+)", code)
    return (code[:3], (m.group(2).replace("TO", "-").replace("PLUS", "+") if m else code[3:]))


def _title(ticker):
    team, bucket = _team_bucket(ticker)
    return f"{team} wins by {bucket}"


def _codes(event):
    tail = str(event or "").rsplit("-", 1)[-1][7:]
    return (tail[:3], tail[3:]) if len(tail) >= 6 else (None, None)


def _quote(lane, pick, ticker, event, tip, logged, price, roi, won_side_yes, label):
    start = dt.datetime.fromtimestamp(tip, UTC)
    return dict(
        id=f"{lane}:{ticker}", source=lane, sport=SPORT, venue="kalshi_binary", market_id=ticker, event=event, label=label,
        side_a=_title(ticker), side_b="No", kalshi_title=_title(ticker), league="NBA", date=start.date().isoformat(),
        start=start.isoformat(), logged=dt.datetime.fromtimestamp(logged, UTC).isoformat(), price=price,
        price_a=price if pick == "a" else None, price_b=price if pick == "b" else None, price_draw=None, pick=pick, bet=True,
        stake=100.0, status="won" if roi > 0 else "lost", pnl=round(roi * 100, 2), pnl_fee_override=round(roi * 100, 2),
        result="a" if won_side_yes else "b", settle_px=None, settled=None, prob_a=None, edge=None, untraded=False,
        start_source="espn", url="", espn_home=_codes(event)[1], espn_away=_codes(event)[0])


def yes_quotes(chaos, before=None):
    """The live YES lane's counted split entries (settled), from the chaos ledger: one quote per entry. Read-only. `before`: only nights
    earlier than that (version 2 once version 3 has started)."""
    L = ((chaos or {}).get("lanes") or {}).get(YES_LANE) or {}
    out = []
    for t in C.counted(L.get("trades") or [], L):
        if t.get("exit_key") != C.SPLIT or str(t.get("night") or "") < MOVED_ON or (before and str(t["night"]) >= before):
            continue
        out.append(_quote(YES_LANE, "a", t["ticker"], t["event"], t["start_ts"], t["entry_ts"], t["entry"], t["roi"], bool(t.get("side_won")),
                          f"{t['event'].split('-', 1)[-1]} · {_title(t['ticker'])} (buy YES, split sell)"))
    return out


def no_quotes(nofade, before=None):
    """The live NO fade's verified fills (settled, version 2), one quote per filled bucket. Read-only. `before` as in yes_quotes."""
    out = []
    key = N.vkey(N.HEAD)
    for e in (nofade or {}).get("entries") or []:
        if N.phase_of(e["night"]) != "v2" or (before and e["night"] >= before):
            continue
        for r in e["buckets"]:
            f = (r.get("fills") or {}).get(key)
            if not f or (r.get("ask") or {}).get("status") != "verified":
                continue
            roi = f["profit"] / f["cost"]
            out.append(_quote(NO_LANE, "b", r["id"], e["event"], e["tip"], f["fill_at"], f["limit"], roi, not r["no_wins"],
                              f"{e['event'].split('-', 1)[-1]} · {_title(r['id'])} (NO fade)"))
    return out


def v3_quotes(v3, before=None):
    """Version 3's settled entries (the executor's snapshots, fills replayed from prints), as quotes under their own source ids.
    `before`: only nights earlier than that (version 3 once version 4 has started)."""
    return _ledger_quotes(v3, YES3_LANE, NO3_LANE, before)


def v4_quotes(v4):
    """Version 4's settled entries, as quotes under the v4 source ids."""
    return _ledger_quotes(v4, YES4_LANE, NO4_LANE, None)


def _ledger_quotes(state, yes_src, no_src, before):
    out = []
    for r in (state or {}).get("rows", {}).values():
        if r.get("no_entry") or "roi" not in r or (before and str(r.get("night") or "") >= before):
            continue
        if r["lane"] == YES_LANE:
            out.append(_quote(yes_src, "a", r["ticker"], r["event"], r["tip"], _epoch(r.get("decided_at")) or r["tip"], r["ask"], r["roi"], r["result"] == "yes",
                              f"{r['event'].split('-', 1)[-1]} · {_title(r['ticker'])} (buy YES, split sell)"))
        else:
            out.append(_quote(no_src, "b", r["ticker"], r["event"], r["tip"], r.get("fill_at") or r["tip"], r["limit"], r["roi"], r["result"] == "yes",
                              f"{r['event'].split('-', 1)[-1]} · {_title(r['ticker'])} (NO fade)"))
    return out


def _epoch(raw):
    t = D.instant(raw)
    return int(t.timestamp()) if t else None


def _open_quote(lane, pick, lead):
    tip = D.instant(lead.get("tip"))
    if tip is None:
        return None
    price = None
    return dict(
        id=f"{lane}:{lead['ticker']}", source=lane, sport=SPORT, venue="kalshi_binary", market_id=lead["ticker"], event=lead.get("event"),
        label=f"{str(lead.get('event')).split('-', 1)[-1]} · {_title(lead['ticker'])}", side_a=_title(lead["ticker"]), side_b="No",
        kalshi_title=_title(lead["ticker"]), league="NBA", date=tip.date().isoformat(), start=tip.isoformat(), logged=tip.isoformat(),
        price=0.15 if pick == "a" else 0.5, price_a=None, price_b=None, price_draw=None, pick=pick, bet=True, stake=100.0, status="open",
        pnl=0.0, result=None, settle_px=None, settled=None, prob_a=None, edge=None, untraded=False, start_source="espn", url="",
        espn_home=_codes(lead.get("event"))[1], espn_away=_codes(lead.get("event"))[0])


def page_inputs(d, st, blob, chaos, nofade, now=None, yes_feed=None, no_feed=None, v3=None, v4=None):
    """Augment page inputs in memory; the original ledgers, stage and feeds are untouched (a test pins the follower's feeds byte for byte).
    The record is the paper lanes' version 2; the upcoming list is the feeds' own leads, only while a feed is fresh."""
    now = now or dt.datetime.now(UTC)
    yes_feed = yes_feed if yes_feed is not None else (P.load_feed(YES_PATH) or {})
    no_feed = no_feed if no_feed is not None else (P.load_feed(NO_PATH) or {})
    since, since4 = v3_since(v3), v4_since(v4)
    rows = yes_quotes(chaos, since or since4) + no_quotes(nofade, since or since4) + (v3_quotes(v3, since4) if since else []) + (v4_quotes(v4) if since4 else [])
    cur = current_version(v3, v4)
    open_lanes = {"v4": ((YES4_LANE, "a", yes_feed), (NO4_LANE, "b", no_feed)), "v3": ((YES3_LANE, "a", yes_feed), (NO3_LANE, "b", no_feed)),
                  "v2": ((YES_LANE, "a", yes_feed), (NO_LANE, "b", no_feed))}[cur]
    for lane, pick, feed_ in open_lanes:
        stamp = D.instant((feed_ or {}).get("updated_at"))
        if stamp is None or not dt.timedelta(0) <= now - stamp <= dt.timedelta(hours=HEALTHY_HOURS):
            continue
        done = {q["market_id"] for q in rows if q["source"] == lane}
        for lead in (feed_ or {}).get("leads") or []:
            if pick == "a" and cur != "v4" and lead.get("bucket") == "11-20":
                continue                                   # the feed already lists version 4's third bucket; version 3 does not trade it
            q = _open_quote(lane, pick, lead) if lead.get("ticker") not in done else None
            if q:
                rows.append(q)
    current = P.build_feed({"quotes": rows}, {"pairs": pairs(v3, v4)}, now=now)
    return (dict(d, quotes=list(d.get("quotes") or []) + rows),
            dict(st, pairs={**(st.get("pairs") or {}), **pairs(v3, v4)}),
            dict(blob, leads={**(blob.get("leads") or {}), **current["leads"]},
                 pairs={**(blob.get("pairs") or {}), **current["pairs"]}))


def main(argv=None):
    heartbeat = "--heartbeat" in (sys.argv[1:] if argv is None else argv)
    ages = [P.feed_age_min(p) for p in (YES_PATH, NO_PATH)]
    if heartbeat and all(a is not None and a < SKIP_FRESH_MIN for a in ages):
        print("nba win margin feeds are", round(max(ages)), "min old; left alone")
        return 0
    now = dt.datetime.now(UTC)
    yes, no = feeds(now)
    if yes["errors"] and not yes["leads"]:
        print("nba win margin feeds not written: the event listing failed:", yes["errors"][:2])
        return 1
    P.save_feed(yes, YES_PATH)
    P.save_feed(no, NO_PATH)
    print("nba win margin feeds:", len(yes["leads"]), "YES leads,", len(no["leads"]), "NO leads,", len(yes["errors"]), "errors")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
