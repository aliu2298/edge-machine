#!/usr/bin/env python3
"""NBA win margin NO fade (2026-10-30): the dip rule, fills and sells on prints, the ask check, game rows, the fresh /
in-sample split, and the card beside the YES split."""
import sys

import chaos_replay as C
import nba_wm_nofade as N
import nba_wm_nofade_build as B
import sandbox_audit

FAILS = []


def check(label, got, want):
    ok = got == want
    print(f"  {'ok  ' if ok else 'FAIL'} {label}" + ("" if ok else f" (got {got!r}, want {want!r})"))
    if not ok:
        FAILS.append(label)


TIP = 1_800_000_000
ENTRY = TIP - 3600
mf = N.fee

print("the dip trade (NO prints, [(ts, no price, contracts)])")
P = 0.40                                   # limit at 75% = 0.30
pr = [(TIP + 60, 0.38, 5), (TIP + 120, 0.29, 6), (TIP + 180, 0.30, 5), (TIP + 600, 0.41, 3)]
t = N.dip_trade(pr, TIP, P, 0.75, True)
check("fills on the first print at or under 0.30, 11 contracts at or under it within the hour; sold on the later 0.41 print",
      (t["limit"], t["fill_at"], t["printed"], t["reason"], t["sold_at"]), (0.30, TIP + 120, 11, "sold", TIP + 600))
check("profit = pregame less its maker fee, less the limit and its maker fee",
      round(t["profit"], 5), round(P - mf(P) - 0.30 - mf(0.30), 5))
pr2 = [(TIP + 120, 0.29, 6), (TIP + 180, 0.35, 5)]
check("a fill with only 6 contracts at or under the limit is thin: no fill", N.dip_trade(pr2, TIP, P, 0.75, True), None)
pr3 = [(TIP - 60, 0.20, 50), (TIP + 120, 0.29, 20), (TIP + 200, 0.33, 4)]
t3 = N.dip_trade(pr3, TIP, P, 0.75, True)
check("a print before the tip never fills; not sold = settles: NO pays 1 when the bucket misses, 0 when it hits",
      (t3["fill_at"], t3["reason"], round(t3["profit"] + t3["cost"], 4), round(N.dip_trade(pr3, TIP, P, 0.75, False)["profit"] + t3["cost"], 4)),
      (TIP + 120, "settled", 1.0, 0.0))
check("the sell needs a LATER print at or above P: an earlier one does not sell, so the fill settles",
      N.dip_trade([(TIP + 10, 0.45, 5), (TIP + 60, 0.30, 20)], TIP, 0.40, 0.75, True)["reason"], "settled")
check("a limit under 3c is not placed", N.dip_trade(pr, TIP, 0.10, 0.25, True), None)

print("\nthe ask check (#253) on the pregame price")
good = [(ENTRY - 300, 0.41, 2), (ENTRY + 600, 0.40, 12)]
check("10+ contracts at or under P in the hour after, P not under half the last trade: verified", N.ask_check(good, ENTRY, 0.40)["status"], "verified")
check("only 4 contracts: unverified, with the reason", (N.ask_check([(ENTRY + 600, 0.40, 4)], ENTRY, 0.40)["status"],
                                                          "under 10" in N.ask_check([(ENTRY + 600, 0.40, 4)], ENTRY, 0.40)["reason"]), ("unverified", True))
check("P under half the last trade: unverified", N.ask_check([(ENTRY - 60, 0.90, 5), (ENTRY + 60, 0.40, 50)], ENTRY, 0.40)["status"], "unverified")

print("\nevaluate: eligibility and rows")
mk = [dict(ticker="KXNBAWINMARGIN-26OCT31WASCLE-CLE1TO5", yes_sub_title="Cleveland wins by 1-5 points", result="no"),
      dict(ticker="KXNBAWINMARGIN-26OCT31WASCLE-WAS1TO5", yes_sub_title="Washington wins by 1-5 points", result="yes"),
      dict(ticker="KXNBAWINMARGIN-26OCT31WASCLE-CLE21PLUS", yes_sub_title="Cleveland wins by 21+ points", result="no"),
      dict(ticker="KXNBAWINMARGIN-26OCT31WASCLE-WAS6TO10", yes_sub_title="Washington wins by 6-10 points", result="no")]
entry = {mk[0]["ticker"]: (0.58, 0.60),    # P = 0.42, spread 2c: in
         mk[1]["ticker"]: (0.30, 0.40),    # spread 10c: out
         mk[2]["ticker"]: (0.02, 0.04)}    # P = 0.98: out (above 95c)
tr = {mk[0]["ticker"]: good + [(TIP + 100, 0.30, 15)]}
rows = N.evaluate(mk, entry, tr, TIP, "now")
check("only the tight, 10-95c bucket becomes a row (the wide spread, the 98c NO and the unquoted bucket are left out)",
      [r["id"].split("-")[-1] for r in rows], ["CLE1TO5"])
check("its P is 1 - the YES bid and the 75% limit is 0.32", (rows[0]["P"], rows[0]["fills"]["d75"]["limit"]), (0.42, 0.32))

print("\ngame rows: one row per game, only verified buckets, fresh and in-sample apart")
def bucket(ok, roi_cost, roi_profit, sold=False):
    return dict(id="x", ask=dict(status="verified" if ok else "unverified"),
                fills={"d75": dict(cost=roi_cost, profit=roi_profit, sold_at=1 if sold else None)})
entries = [dict(event="E1", night="2026-10-31", insample=False, buckets=[bucket(True, 0.3, 0.15, True), bucket(True, 0.3, -0.3), bucket(False, 0.3, 9)]),
           dict(event="E2", night="2026-11-01", insample=False, buckets=[bucket(True, 0.2, 0.1, True)]),
           dict(event="E0", night="2026-10-25", insample=True, buckets=[bucket(True, 0.3, 0.3, True)])]
g = N.game_rows(entries, "d75", False)
check("two fresh games; E1 sums its two verified buckets (the unverified one is out)",
      ([r["event"] for r in g], g[0]["fills"], round(g[0]["profit"], 3), round(g[0]["cost"], 3)), (["E1", "E2"], 2, -0.15, 0.6))
check("the in-sample game is apart", [r["event"] for r in N.game_rows(entries, "d75", True)], ["E0"])
check("counts: verified and unverified buckets", N.counts(entries, False), dict(games=2, verified=3, unverified=1))

print("\nthe run: fresh from 2026-10-31, in-sample before it")
import datetime as dt
EVA, EVB = "KXNBAWINMARGIN-26OCT30AAABBB", "KXNBAWINMARGIN-26OCT31CCCDDD"
real_list, real_markets, real_pages = N.C.list_events, N.C.event_markets, N.D.pages
real_candles, real_trades = N.C.fetch_candles, N.O.fetch_trades
import nba_winmargin as W
N.C.list_events = lambda *a, **k: [EVA, EVB]
N.C.event_markets = lambda ev, f: ([dict(ticker=ev + "-AAA1TO5", yes_sub_title="A wins by 1-5 points", result="no")], False)
N.D.pages = lambda path, key, f: [dict(ticker="KXNBAGAME-x", expected_expiration_time="2026-11-01T03:30:00Z" if "31" in path else "2026-10-31T03:30:00Z")]
N.C.fetch_candles = lambda s, ev, ms, lo, hi, f, a: {ms[0]["ticker"]: [dict(end_period_ts=hi - 60, yes_bid=dict(close_dollars="0.5800"), yes_ask=dict(close_dollars="0.6000"))]}
N.O.fetch_trades = lambda t, ts, f: []
try:
    st = N.load("/nonexistent/path.json")
    N.run(st, dt.datetime(2026, 11, 1, 12, tzinfo=dt.timezone.utc), lambda p: {})
finally:
    N.C.list_events, N.C.event_markets, N.D.pages, N.C.fetch_candles, N.O.fetch_trades = real_list, real_markets, real_pages, real_candles, real_trades
check("Oct 30's game is in-sample, Oct 31's is fresh; a run records both once", sorted((e["night"], e["insample"]) for e in st["entries"]),
      [("2026-10-30", True), ("2026-10-31", False)])
check("the ledger starts 2026-10-31 with the study window from 2026-10-20", (st["since"], st["since_in"]), ("2026-10-31", "2026-10-20"))

print("\nthe card")
state = dict(entries=entries, last_run="x", error=None)
chaos = dict(lanes={"nba_winmargin_split": dict(id="nba_winmargin_split", since="2026-10-30", trades=[
    dict(event="E1", ticker="x", exit_key="split", roi=1.0, cost=0.2, profit=0.2, night="2026-10-31", won=True, reason="split"),
    dict(event="E9", ticker="y", exit_key="split", roi=-1.0, cost=0.2, profit=-0.2, night="2026-11-01", won=False, reason="split")])})
html = B.card(state, chaos)
check("headline row first, then 85% and 65%, in the lane's own order",
      [r for r in ("d75", "d85", "d65") if f'data-variant="{r}"' in html] , ["d75", "d85", "d65"])
check("the YES split row sits next to the NO fade row, with the overlap of games",
      ("YES split" in html, "NO fade" in html, "2 with a NO fade fill" in html, "<b>1 with both</b>" in html), (True, True, True, True))
check("the in-sample result is its own fold, labelled not evidence", ('id="nofade-insample"' in html, "NOT evidence" in html), (True, True))
check("the ask-check skip is stated", "Skipped as unverified ask: 1 of 4" in html, True)
check("no inline style or svg (the NBA page forbids both)", ("style=" in html, "<svg" in html), (False, False))
check("public copy passes the guard", sandbox_audit.COPY_RE.search(html), None)
check("the Sandbox index row links to the NBA page", ("nba.html#cheap-side" in B.index_row(state), 'data-lane="nba_wm_nofade"' in B.index_row(state)), (True, True))

print("\n" + ("ALL PASS" if not FAILS else f"{len(FAILS)} FAILED"))
sys.exit(1 if FAILS else 0)
