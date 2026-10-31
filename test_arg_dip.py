#!/usr/bin/env python3
"""Offline checks for arg_goalless_dip (arg_dip.py) and its Soccer page section (arg_dip_build.py)."""
import copy
import datetime as dt
import re
import sys

import arg_dip as A
import arg_dip_build as B
import chaos_build
import sandbox_audit

FAILS = []
UTC = dt.timezone.utc


def check(label, got, want):
    ok = got == want
    print(f"  {'ok  ' if ok else 'FAIL'} {label}" + ("" if ok else f" (got {got!r}, want {want!r})"))
    if not ok:
        FAILS.append(label)


def near(label, got, want, tol=1e-6):
    ok = got is not None and abs(got - want) <= tol
    print(f"  {'ok  ' if ok else 'FAIL'} {label}" + ("" if ok else f" (got {got!r}, want {want!r})"))
    if not ok:
        FAILS.append(label)


KICK = int(dt.datetime(2026, 10, 31, 22, 0, tzinfo=UTC).timestamp())
Q_AT = KICK - 3600


def pr(mins, yes, n=10.0):
    """A YES print `mins` minutes after kickoff."""
    return (KICK + mins * 60, yes, n)


print("terms")
check("the pre-registered terms", (A.SERIES, A.STRIKE, A.SINCE, A.FRACTIONS, A.HEADLINE, A.KICKOFF_BACK_H, A.P_LEAD_MIN,
                                   A.MAX_SPREAD, A.MIN_FILL, A.FILL_WINDOW_MIN, A.MAKER, A.REVIEW_N, A.DECIDE_N),
      ("KXARGPREMDIVTOTAL", 0.5, "2026-10-31", (0.65, 0.75, 0.55), 0.65, 4, 60, 0.05, 10, 60, 0.0175, 10, 30))
check("the in-sample window ends before the record begins", A.INSAMPLE[1] < A.SINCE, True)
near("maker fee in and out", A.fee(0.57), 0.0175 * 0.57 * 0.43)
check("a matchday is the event ticker's date", A.matchday("KXARGPREMDIVTOTAL-26OCT31HURTIG"), "2026-10-31")

print("\nP: the pregame ask an hour before kickoff, and its ask check")
cs = [dict(end_period_ts=Q_AT - 600, yes_bid=dict(close_dollars="0.84"), yes_ask=dict(close_dollars="0.87")),
      dict(end_period_ts=Q_AT, yes_bid=dict(close="0.85"), yes_ask=dict(close="0.88")),
      dict(end_period_ts=Q_AT + 120, yes_bid=dict(close_dollars="0.80"), yes_ask=dict(close_dollars="0.83"))]
check("the last minute quote at or before the time (an archived candle's 'close' read as well); later minutes ignored",
      A.pregame_quote(cs, Q_AT), (Q_AT, 0.85, 0.88))
check("no quote: None", A.pregame_quote([], Q_AT), None)
pre = [(Q_AT - 300, 0.88, 5), (Q_AT + 600, 0.88, 6), (Q_AT + 1800, 0.87, 5), (Q_AT + 1200, 0.90, 50)]
pre = sorted(pre)
c = A.p_check(pre, Q_AT, 0.88)
check("verified when 10+ traded at or through P within 60 minutes (a 0.90 print does not count)",
      (c["status"], c["printed"], c["last_trade"]), ("verified", 11, 0.88))
check("unverified under 10", A.p_check([(Q_AT + 600, 0.88, 4)], Q_AT, 0.88)["reason"],
      "4 contracts traded at or through the ask within 60 minutes (under 10)")
check("unverified when P is under half the last trade", A.p_check([(Q_AT - 60, 0.90, 5), (Q_AT + 60, 0.40, 50)], Q_AT, 0.40)["reason"],
      "ask 0.40 under half the last trade 0.90")

print("\nthe buy, the sell, settlement")
P = 0.88
# 65% of 0.88 = 0.57; 75% = 0.66; 55% = 0.48.
prints = [pr(-20, 0.60, 100), pr(5, 0.86), pr(40, 0.66, 4), pr(55, 0.57, 6), pr(60, 0.56, 8), pr(130, 0.55, 99), pr(70, 0.88, 3)]
prints = sorted(prints)
ev = A.evaluate(prints, KICK, P, "yes")
check("limits from P, rounded to the cent", {k: v and v["limit"] for k, v in ev.items()}, {"65": 0.57, "75": 0.66, "55": None})
check("a pre-kickoff print never fills the buy (0.60 at -20')", ev["75"]["fill_at"], KICK + 40 * 60)
check("65%: first touch at 55', 14 contracts at or below within 60 min (the 130' print is outside) -> counted",
      (ev["65"]["fill_at"], ev["65"]["fill_volume"], ev["65"]["counted"]), (KICK + 55 * 60, 14, True))
check("75%: 4 + 6 + 8 at or below 0.66 within 60 min = 18 -> counted", (ev["75"]["fill_volume"], ev["75"]["counted"]), (18, True))
check("the sell at P fills on a later print at or above P (0.88 at 70')", (ev["65"]["sold"], ev["65"]["sold_at"]), (True, KICK + 70 * 60))
check("55%: no print reached 0.48: no fill, costs nothing", ev["55"], None)
thin = A.evaluate([pr(30, 0.57, 3), pr(50, 0.57, 2)], KICK, P, "no")["65"]
check("under 10 contracts at or below the limit within 60 min is a thin touch, not counted",
      (thin["counted"], thin["fill_volume"], thin["sold"], thin["payout"]), (False, 5, False, 0.0))
entry = dict(event="KXARGPREMDIVTOTAL-26OCT31AAABBB", matchday="2026-10-31", kickoff=KICK, p=P, result="yes", buys=ev)
r65 = A.rows_of([entry], 0.65)[0]
cost = 0.57 + A.fee(0.57)
near("ROI per fill: sold at P, maker fee both legs", r65["roi"], ((P - A.fee(P)) - cost) / cost)
near("the hold control on the same fill: settles at 1", r65["hold"], (1 - cost) / cost)
held0 = dict(entry, result="no", buys=A.evaluate([pr(55, 0.57, 20)], KICK, P, "no"))
r0 = A.rows_of([held0], 0.65)[0]
near("an unsold fill held to a 0-0 loses the cost", r0["roi"], -1.0)
check("it is marked 0-0", r0["zero"], True)
check("a thin touch is not a row", A.rows_of([dict(entry, buys=dict(A.evaluate([pr(30, 0.57, 3)], KICK, P, "yes")))], 0.65), [])

print("\nthe read: per variant, z by matchday")
check("z needs 3 matchdays", A.z_by_day([(0.2, "a"), (0.1, "b")]), None)
near("z = mean of the matchday means over their standard error", A.z_by_day([(0.2, "a"), (0.4, "a"), (0.1, "b"), (0.0, "c")]),
     (0.3 + 0.1 + 0.0) / 3 / (0.15275252316519464 / 3 ** 0.5))
s = A.summary([entry, held0], 0.65)
check("summary: 2 matches, 2 fills, 1 sold at P, 1 ended 0-0", (s["matches"], s["fills"], s["sold"], s["zero"]), (2, 2, 1, 1))
check("status in filled matches", (A.status(1), A.status(10), A.status(30)),
      ("1 filled match · review at 10, decide at 30", "10 filled matches · review due (10 reached) · decide at 30",
       "30 filled matches · decide now (30 reached)"))

print("\nreplay and run: the record from 2026-10-31, the in-sample block apart")


def market(ev_, status="finalized", result="yes", strike=0.5, kick=KICK):
    return dict(ticker=ev_ + "-1", floor_strike=strike, status=status, result=result, title=ev_ + " title",
                occurrence_datetime=dt.datetime.fromtimestamp(kick + 4 * 3600, UTC).isoformat())


def fake_for(events, pre_px=0.88, live=None, open_events=()):
    live = live if live is not None else [pr(55, 0.57, 20), pr(70, 0.88, 5)]

    def fetch(path):
        if path.startswith("events?series_ticker=KXARGPREMDIVTOTAL&status=settled"):
            return {"events": [dict(event_ticker=e) for e in events], "cursor": ""}
        if path.startswith("events?series_ticker=KXARGPREMDIVTOTAL&status=open"):
            return {"events": [dict(event_ticker=e, title=e + " t", markets=[market(e, "active", "", kick=KICK + 5 * 86400)]) for e in open_events],
                    "cursor": ""}
        if path.startswith("markets?limit=200&event_ticker="):
            e = path.split("event_ticker=")[1].split("&")[0]
            return {"markets": [market(e, strike=1.5), market(e)] if "UNSET" not in e else [market(e, "active", "")], "cursor": ""}
        if "candlesticks" in path:
            e = path.split("/events/")[1].split("/")[0]
            return {"market_tickers": [e + "-1"], "market_candlesticks": [[dict(
                end_period_ts=Q_AT, yes_bid=dict(close_dollars=str(pre_px - 0.02)), yes_ask=dict(close_dollars=str(pre_px)))]]}
        if path.startswith(("markets/trades", "historical/trades")):
            rows = [(Q_AT + 600, pre_px, 30)] + live
            return {"trades": [dict(created_time=dt.datetime.fromtimestamp(t, UTC).isoformat(), yes_price_dollars=str(p),
                                    count_fp=str(n)) for t, p, n in rows], "cursor": ""}
        raise AssertionError(path)
    return fetch


NOW = dt.datetime(2026, 11, 2, 12, tzinfo=UTC)
st = A.load("/nonexistent/arg.json")
evs = ["KXARGPREMDIVTOTAL-26OCT31AAABBB", "KXARGPREMDIVTOTAL-26OCT30OLDOLD", "KXARGPREMDIVTOTAL-26NOV01UNSETX"]
A.run(st, NOW, fake_for(evs, open_events=["KXARGPREMDIVTOTAL-26NOV05NEXTGM", "KXARGPREMDIVTOTAL-26OCT30BEFORE"]))
check("the live run takes matches from 2026-10-31 only; an unsettled one waits",
      ([e["event"] for e in st["entries"]], st["observations"]["waiting"]), (["KXARGPREMDIVTOTAL-26OCT31AAABBB"], 1))
e0 = st["entries"][0]
check("the entry: P 0.88 from the quote an hour before kickoff, checked, 65% filled and sold at P",
      (e0["p"], e0["p_check"]["status"], e0["buys"]["65"]["counted"], e0["buys"]["65"]["sold"], e0["kickoff"]),
      (0.88, "verified", True, True, KICK))
check("watching next lists the open matches the record will count (not one dated before it)", [u["event"] for u in st["upcoming"]], ["KXARGPREMDIVTOTAL-26NOV05NEXTGM"])
A.run(st, NOW + dt.timedelta(hours=1), fake_for(evs))
check("a second run does not replay a match", len(st["entries"]), 1)
thin_st = A.load("/nonexistent/arg2.json")
A.run(thin_st, NOW, fake_for(["KXARGPREMDIVTOTAL-26OCT31CCCDDD"], live=[]))
check("no live print at the limit: the match is seen, no fill", (len(thin_st["entries"]), A.summary(thin_st["entries"], 0.65)["fills"]), (1, 0))
bad_st = A.load("/nonexistent/arg3.json")


def unverified_fetch(path):
    f = fake_for(["KXARGPREMDIVTOTAL-26OCT31EEEFFF"])
    if path.startswith(("markets/trades", "historical/trades")):
        return {"trades": [], "cursor": ""}
    return f(path)


A.run(bad_st, NOW, unverified_fetch)
check("a pregame ask nothing traded through is skipped with its reason",
      (bad_st["entries"], next(iter(bad_st["skips"].values())).split(":")[0]), ([], "pregame ask unverified"))

ins = A.load("/nonexistent/arg4.json")
A.run(ins, NOW, fake_for(["KXARGPREMDIVTOTAL-26SEP21GGGHHH", "KXARGPREMDIVTOTAL-26OCT31AAABBB"]), backfill=True)
check("the backfill fills state['insample'] from its window only, never the record",
      ([e["event"] for e in ins["insample"]["entries"]], ins["entries"], ins["insample"]["built"] is not None),
      (["KXARGPREMDIVTOTAL-26SEP21GGGHHH"], [], True))

print("\nthe Soccer page section")
page_state = copy.deepcopy(st)
page_state["insample"] = ins["insample"]
h = B.section(page_state)
t = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", h))
check("the section: its id, the rule note, the out-of-sample line, the live variant table with every column",
      ('<section id="arg-dip">' in h, "every league match" in t, "Brasileirão over 0.5" in t and "Argentina-only watch" in t,
       'id="arg-dip-live"' in h, all(x in t for x in ("Matches seen", "Buys filled (fill rate)", "Sold at P", "Ended 0-0",
                                                       "ROI per fill", "Hold, same fills", "z (by matchday)"))),
      (True, True, True, True, True))
check("the headline row first, then the variants", re.findall(r'data-variant="(\d+)"', h[:h.find('id="arg-dip-insample"')]),
      ["65", "75", "55"])
check("the summary line reads the live record only", "1 matches seen · 1 bought at 65% · 1 sold at P · 1 filled match" in t, True)
check("the in-sample block is collapsed, labelled, and separate", (
    '<details class="section-disclosure" id="arg-dip-insample">' in h, "not evidence, never in the record" in t,
    'id="arg-dip-insample-table"' in h), (True, True, True))
check("the index row reads the live record only", (B.index_row(page_state)["fills"], B.index_row(page_state)["href"]),
      (1, "./soccer.html#arg-dip"))
empty = B.section(A.load("/nonexistent/none.json"))
check("an empty ledger renders, with no in-sample block", ("No match has settled since the record began" in empty,
                                                             "arg-dip-insample" in empty), (True, False))
shell = '<main><section id="cheap-side"><h2>x</h2></section><section id="leagues">y</section></main>'
placed = B.place(shell, page_state)
check("placed right after the page's cheap-side section, before the rest",
      placed.find('id="cheap-side"') < placed.find('id="arg-dip"') < placed.find('id="leagues"'), True)
import sandbox_build
sbx = sandbox_build.chaos_html()
check("the Sandbox lists it in its own Resting in-play buys section, after the Chaos section and not inside it",
      ('<section id="in-play">' in sbx, 'data-lane="arg_goalless_dip"' in sbx, "./soccer.html#arg-dip" in sbx,
       sbx.find('id="in-play"') > sbx.find("</section>"), 'data-lane="arg_goalless_dip"' in chaos_build.section()),
      (True, True, True, True, False))
check("public copy passes the guard", sandbox_audit.COPY_RE.search(t), None)

print(f"\n{'ALL PASS' if not FAILS else str(len(FAILS)) + ' FAILED'}")
sys.exit(1 if FAILS else 0)
