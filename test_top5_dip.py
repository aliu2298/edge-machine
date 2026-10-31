#!/usr/bin/env python3
"""Offline checks for top5_goalless_dip (top5_dip.py on the arg_dip.py engine) and its Soccer page section."""
import copy
import datetime as dt
import re
import sys

import arg_dip as A
import arg_dip_build as B
import chaos_build
import sandbox_audit
import top5_dip as T

FAILS = []
UTC = dt.timezone.utc
CFG = T.TOP5


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


KICK = int(dt.datetime(2026, 10, 31, 15, 0, tzinfo=UTC).timestamp())
Q_AT = KICK - 3600


def pr(mins, yes, n=10.0, secs=0):
    """A YES print `mins` minutes (and `secs` seconds) after kickoff."""
    return (KICK + mins * 60 + secs, yes, n)


print("terms")
check("the pre-registered terms", (CFG["series"], CFG["strike"], CFG["since"], CFG["fractions"], CFG["headline"],
                                   CFG["held"], CFG["p_range"], CFG["insample"]),
      (("KXEPLTOTAL", "KXLALIGATOTAL", "KXSERIEATOTAL", "KXBUNDESLIGATOTAL", "KXLIGUE1TOTAL", "KXUCLTOTAL"), 1.5,
       "2026-10-31", (0.55, 0.65), 0.55, True, (0.10, 0.95), ("2026-08-01", "2026-10-30")))
check("the held rule's terms and the shared engine terms", (A.HELD_WINDOW_MIN, A.HELD_SPAN_S, A.HELD_CONTRACTS, A.MIN_FILL,
                                                             A.FILL_WINDOW_MIN, A.MAKER, A.KICKOFF_BACK_H, A.P_LEAD_MIN),
      (5, 120, 50, 10, 60, 0.0175, 4, 60))
check("the in-sample window ends before the record begins", CFG["insample"][1] < CFG["since"], True)
check("Argentina keeps its own rule: no held flag, its own series and fractions",
      (A.ARG["held"], A.ARG["series"], A.ARG["fractions"], A.ARG["headline"]), (False, ("KXARGPREMDIVTOTAL",), (0.65, 0.75, 0.55), 0.65))
check("a lane's series is read from the event ticker", A.series_of("KXEPLTOTAL-26OCT31CFCMUN"), "KXEPLTOTAL")
check("every series has a league name", sorted(T.LEAGUES) == sorted(CFG["series"]), True)

print("\nthe buy: a fill must also HOLD")
P = 0.80
# 55% of 0.80 = 0.44; 65% = 0.52.
spread_out = A.evaluate([pr(30, 0.44, 6), pr(32, 0.44, 6)], KICK, P, "yes", CFG)["55"]
check("10+ at or below in 60 min, prints spanning 2 minutes: held, counted",
      (spread_out["fill_volume"], spread_out["held"], spread_out["counted"]), (12, True, True))
burst = A.evaluate([pr(30, 0.44, 30), pr(30, 0.43, 25, secs=20)], KICK, P, "yes", CFG)["55"]
check("50+ contracts within 5 minutes holds even inside a minute", (burst["held"], burst["counted"]), (True, True))
stray = A.evaluate([pr(30, 0.44, 12), pr(30, 0.70, 5, secs=40), pr(45, 0.47, 5)], KICK, P, "yes", CFG)["55"]
check("a single stray print of 12 (10+ but under 50, no 2-minute span): thin touch, not counted",
      (stray["fill_volume"], stray["held"], stray["counted"]), (12, False, False))
late = A.evaluate([pr(30, 0.44, 12), pr(36, 0.44, 5)], KICK, P, "yes", CFG)["55"]
check("a second print at the limit after the 5-minute window does not make it hold", (late["held"], late["counted"]), (False, False))
few = A.evaluate([pr(30, 0.44, 3), pr(33, 0.44, 3)], KICK, P, "no", CFG)["55"]
check("held but under 10 contracts in 60 min: still a thin touch", (few["held"], few["counted"]), (True, False))
check("Argentina's evaluate is unchanged: the stray 12 counts there (no held rule)",
      A.evaluate([pr(30, 0.57, 12)], KICK, 0.88, "yes")["65"]["counted"], True)
both = A.evaluate([pr(20, 0.52, 20), pr(23, 0.52, 5), pr(40, 0.44, 60), pr(70, 0.80, 5)], KICK, P, "no", CFG)
check("both fractions read on the same prints; the sell at P fills on the 70' print",
      ({k: (v["limit"], v["counted"], v["sold"]) for k, v in both.items()}), {"55": (0.44, True, True), "65": (0.52, True, True)})
e = dict(event="KXEPLTOTAL-26OCT31CFCMUN", matchday="2026-10-31", kickoff=KICK, p=P, result="no", buys=both, league="EPL")
r = A.rows_of([e], 0.55)[0]
cost = 0.44 + A.fee(0.44)
near("ROI per fill: sold at P, maker fee both legs", r["roi"], ((P - A.fee(P)) - cost) / cost)
near("the hold control: the match ended under 2 goals, the same fill held loses its cost", r["hold"], -1.0)
check("the row carries its league", r["league"], "EPL")

print("\nreplay and run over six series")


def market(ev_, status="finalized", result="yes", strike=1.5, kick=KICK):
    return dict(ticker=f"{ev_}-{int(strike + 0.5)}", floor_strike=strike, status=status, result=result, title=ev_ + " title",
                occurrence_datetime=dt.datetime.fromtimestamp(kick + 4 * 3600, UTC).isoformat())


def fake_for(by_series, pre_px=0.80, live=None, open_by_series=None, calls=None):
    live = live if live is not None else [pr(40, 0.44, 60), pr(70, 0.80, 5)]
    open_by_series = open_by_series or {}

    def fetch(path):
        if calls is not None:
            calls.append(path)
        if path.startswith("events?series_ticker="):
            ser = path.split("series_ticker=")[1].split("&")[0]
            if "status=settled" in path:
                return {"events": [dict(event_ticker=x) for x in by_series.get(ser, [])], "cursor": ""}
            return {"events": [dict(event_ticker=x, title=x + " t", markets=[market(x, "active", "", kick=KICK + 5 * 86400),
                                                                              market(x, "active", "", strike=2.5, kick=KICK + 5 * 86400)])
                               for x in open_by_series.get(ser, [])], "cursor": ""}
        if path.startswith("markets?limit=200&event_ticker="):
            x = path.split("event_ticker=")[1].split("&")[0]
            if "UNSET" in x:
                return {"markets": [market(x, "active", "")], "cursor": ""}
            return {"markets": [market(x, strike=0.5), market(x), market(x, strike=2.5)], "cursor": ""}
        if "candlesticks" in path:
            ser, x = path.split("series/")[1].split("/")[0], path.split("/events/")[1].split("/")[0]
            assert ser == A.series_of(x), (ser, x)                       # candles asked of the event's own series
            px = 0.97 if "DEAR" in x else pre_px
            return {"market_tickers": [x + "-2"], "market_candlesticks": [[dict(
                end_period_ts=Q_AT, yes_bid=dict(close_dollars=str(round(px - 0.02, 2))), yes_ask=dict(close_dollars=str(px)))]]}
        if path.startswith(("markets/trades", "historical/trades")):
            px = 0.97 if "DEAR" in path else pre_px
            rows = [(Q_AT + 600, px, 30)] + live
            return {"trades": [dict(created_time=dt.datetime.fromtimestamp(t, UTC).isoformat(), yes_price_dollars=str(p),
                                    count_fp=str(n)) for t, p, n in rows], "cursor": ""}
        raise AssertionError(path)
    return fetch


NOW = dt.datetime(2026, 11, 2, 12, tzinfo=UTC)
st = T.load("/nonexistent/top5.json")
calls = []
A.run(st, NOW, fake_for({"KXEPLTOTAL": ["KXEPLTOTAL-26OCT31CFCMUN", "KXEPLTOTAL-26OCT30OLDOLD"],
                         "KXSERIEATOTAL": ["KXSERIEATOTAL-26OCT31BFCMON", "KXSERIEATOTAL-26NOV01UNSETX"],
                         "KXUCLTOTAL": ["KXUCLTOTAL-26OCT31DEARMA"]},
                        open_by_series={"KXLALIGATOTAL": ["KXLALIGATOTAL-26NOV05NEXTGM"], "KXEPLTOTAL": ["KXEPLTOTAL-26OCT30BEFORE"]},
                        calls=calls), cfg=CFG)
check("every series is listed, settled and open", sorted({c.split("series_ticker=")[1].split("&")[0] for c in calls if c.startswith("events?")}),
      sorted(CFG["series"]))
check("the live run takes matches from 2026-10-31 in every series; an unsettled one waits",
      (sorted(x["event"] for x in st["entries"]), st["observations"]["waiting"]),
      (["KXEPLTOTAL-26OCT31CFCMUN", "KXSERIEATOTAL-26OCT31BFCMON"], 1))
e0 = next(x for x in st["entries"] if x["event"].startswith("KXSERIEATOTAL"))
check("the entry reads the over 1.5 rung, P 0.80, its league, the 55% buy held, counted and sold at P",
      (e0["id"], e0["p"], e0["league"], e0["buys"]["55"]["held"], e0["buys"]["55"]["counted"], e0["buys"]["55"]["sold"], e0["version"]),
      ("KXSERIEATOTAL-26OCT31BFCMON-2", 0.80, "Serie A", True, True, True, "top5dip-v1"))
check("a pregame ask over 95c is skipped with its reason", st["skips"].get("KXUCLTOTAL-26OCT31DEARMA"), "pregame ask 0.97 outside 10-95c")
check("watching next lists open matches across series from the record date on (over 1.5 rung)",
      [u["event"] for u in st["upcoming"]], ["KXLALIGATOTAL-26NOV05NEXTGM"])
A.run(st, NOW + dt.timedelta(hours=1), fake_for({"KXEPLTOTAL": ["KXEPLTOTAL-26OCT31CFCMUN"]}), cfg=CFG)
check("a second run does not replay a match", len(st["entries"]), 2)
thin_st = T.load("/nonexistent/top5b.json")
A.run(thin_st, NOW, fake_for({"KXLIGUE1TOTAL": ["KXLIGUE1TOTAL-26OCT31LILRCL"]}, live=[pr(40, 0.44, 12), pr(70, 0.80, 5)]), cfg=CFG)
s_thin = A.summary(thin_st["entries"], 0.55)
check("a stray single print at the limit: the match is seen, a thin touch, no fill", (s_thin["matches"], s_thin["fills"], s_thin["thin"]), (1, 0, 1))

ins = T.load("/nonexistent/top5c.json")
A.run(ins, NOW, fake_for({"KXEPLTOTAL": ["KXEPLTOTAL-26SEP20MCISUN", "KXEPLTOTAL-26OCT31CFCMUN"],
                          "KXBUNDESLIGATOTAL": ["KXBUNDESLIGATOTAL-26JUL20PREPRE"]}), backfill=True, cfg=CFG)
check("the backfill fills state['insample'] from its window only, never the record",
      ([x["event"] for x in ins["insample"]["entries"]], ins["entries"], ins["insample"]["built"] is not None),
      (["KXEPLTOTAL-26SEP20MCISUN"], [], True))

print("\nthe Soccer page section")
page_state = copy.deepcopy(st)
page_state["insample"] = ins["insample"]
h = B.section(page_state, B.TOP5_PAGE)
t = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", h))
check("the section: its own id, the rule note, the out-of-sample line, the live variant table with every column",
      ('<section id="top5-dip">' in h, "every match" in t and "the low price held" in t, "Brasileirão over 0.5" in t,
       'id="top5-dip-live"' in h, all(x in t for x in ("Matches seen", "Buys filled (fill rate)", "Thin touches", "Sold at P",
                                                       "Ended under 2 goals", "ROI per fill", "Hold, same fills", "z (by matchday)"))),
      (True, True, True, True, True))
check("the headline row (55%) first, then the 65% variant",
      re.findall(r'data-variant="(\d+)"', h[:h.find('id="top5-dip-insample"')]), ["55", "65"])
check("the by-league split lists every league, the live record only",
      (re.findall(r'data-league="([^"]+)"', h[h.find('id="top5-dip-leagues"'):h.find('id="top5-dip-insample"')]),
       'id="top5-dip-leagues"' in h),
      (["EPL", "La Liga", "Serie A", "Bundesliga", "Ligue 1", "UCL"], True))
check("the summary line reads the live record only", "2 matches seen · 2 bought at 55% · 2 sold at P · 2 filled matches" in t, True)
check("the in-sample block is collapsed, labelled, separate, and names the research's +12.1%", (
    '<details class="section-disclosure" id="top5-dip-insample">' in h, "not evidence, never in the record" in t,
    'id="top5-dip-insample-table"' in h, "+12.1% per fill" in t), (True, True, True, True))
check("the index row reads the live record only", (B.index_row(page_state, B.TOP5_PAGE)["fills"],
                                                   B.index_row(page_state, B.TOP5_PAGE)["href"]), (2, "./soccer.html#top5-dip"))
empty = B.section(T.load("/nonexistent/none.json"), B.TOP5_PAGE)
check("an empty ledger renders, with no in-sample block and no league table",
      ("No match has settled since the record began" in empty, "top5-dip-insample" in empty, "top5-dip-leagues" in empty),
      (True, False, False))
shell = '<main><section id="cheap-side"><h2>x</h2></section><section id="leagues">y</section></main>'
placed = B.place(shell)
check("placed right after the page's cheap-side section, after Argentina, before the rest",
      placed.find('id="cheap-side"') < placed.find('id="arg-dip"') < placed.find('id="top5-dip"') < placed.find('id="leagues"'), True)
import sandbox_build
sbx = sandbox_build.chaos_html()
check("the Sandbox's Resting in-play buys section lists both lanes, Argentina first; the Chaos section does not",
      ('<section id="in-play">' in sbx, 0 < sbx.find('data-lane="arg_goalless_dip"') < sbx.find('data-lane="top5_goalless_dip"'),
       "./soccer.html#top5-dip" in sbx, 'data-lane="top5_goalless_dip"' in chaos_build.section()),
      (True, True, True, False))
check("public copy passes the guard", sandbox_audit.COPY_RE.search(t), None)

print(f"\n{'ALL PASS' if not FAILS else str(len(FAILS)) + ' FAILED'}")
sys.exit(1 if FAILS else 0)
