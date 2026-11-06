#!/usr/bin/env python3
"""Offline checks (2026-11-06, Olu): Corners total · favourite-side NO (v2), a Sandbox paper lane.

Pre-registered: match-total corner rungs in every corners league (Champions League included); a match whose own Kalshi
1X2 board has a 0.55+ de-vigged favourite (no board: skipped, the reason logged); the LOWEST rung with a No ask of
0.60+ and a No book 5c or tighter, within 4h, never a No under 0.30, one a match. The entry is a maker No bid at the ask
less 2c until kickoff, filled only by a print STRICTLY below it, maker fee, held; the same rung at the taker ask is the
comparison row. Five a day, one bet a match across corners lanes, read after corners_total_under and
corners_ucl_fade. corners_total_under is unchanged. On the Soccer page: one row right under Corners total under.
"""
import datetime as dt
import inspect
import re
import sys
import unittest.mock as um

import corners_fav_no as C
import corners_fav_no_build as CB
import sandbox_audit
import sandbox_sources as S
import sandbox_track as T

FAILS = []
UTC = dt.timezone.utc
NOW = dt.datetime(2026, 11, 7, 12, 0, tzinfo=UTC)


def check(label, got, want):
    ok = got == want
    print(f"  {'ok  ' if ok else 'FAIL'} {label}" + ("" if ok else f" (got {got!r}, want {want!r})"))
    if not ok:
        FAILS.append(label)


def rung(code, n, no_ask, yes_ask=None, lg="EPL", league="Premier League", hours=2, kind="total"):
    fam = "TCORNERS" if kind == "team" else "CORNERS"
    ya = round(1 - no_ask + 0.02, 2) if yes_ask is None else yes_ask
    ko = NOW + dt.timedelta(hours=hours)
    return dict(market_id=f"KX{lg}{fam}-{code}-{n}", sport="soccer_corners", venue="kalshi_binary", corner_kind=kind,
                corner_n=n, league=league, espn_home="H" + code[-3:], espn_away="A" + code[-3:], start=ko.isoformat(),
                date=ko.date().isoformat(), price_a=ya, price_b=no_ask, price_draw=None, untraded=False,
                tradeable={"a": True, "b": True}, label=f"{code} {n}+", side_a="Yes", side_b="No", url="u", volume=0.0)


def board(code, home, draw, away, lg="EPL"):
    return dict(sport="soccer", venue="kalshi", market_id=f"KX{lg}GAME-{code}", price_a=home, price_b=away,
                price_draw=draw, start=(NOW + dt.timedelta(hours=2)).isoformat(), untraded=False)


def ladder(code, lg="EPL", league="Premier League", hours=2, asks=((7, 0.30), (8, 0.45), (9, 0.58), (10, 0.66), (11, 0.78),
                                                                    (12, 0.88))):
    return [rung(code, n, a, lg=lg, league=league, hours=hours) for n, a in asks]


print("the board: the match's own Kalshi 1X2, found by the corners ticker's event code, de-vigged")
U = {"soccer": [board("26NOV07ARSBUR", 0.70, 0.20, 0.12)], "soccer_corners": []}
p = S.kalshi_1x2(U, rung("26NOV07ARSBUR", 9, 0.6))
check("home 0.70 / draw 0.20 / away 0.12 sum 1.02, de-vigged", tuple(round(x, 3) for x in p), (0.686, 0.196, 0.118))
check("a team rung of the same match finds the same board", S.kalshi_1x2(U, rung("26NOV07ARSBUR", 5, 0.6, kind="team")) == p, True)
check("no board for another match", S.kalshi_1x2(U, rung("26NOV07CHEMUN", 9, 0.6)), None)

print("\nthe rung: the lowest with a No ask of 0.60+ and a No book 5c or tighter")
rg = lambda rows: S.cfn_rung(rows)[0]   # noqa: E731
check("asks 0.30 / 0.45 / 0.58 / 0.66 / 0.78 / 0.88: the 10+ rung at 0.66 (the cheapest No at or above 60c)",
      rg(ladder("26NOV07ARSBUR"))["corner_n"], 10)
wide = ladder("26NOV07ARSBUR", asks=((10, 0.66), (11, 0.78)))
wide[0] = dict(wide[0], price_a=0.41)          # No book: 0.66 - (1 - 0.41) = 7c
check("a 7c No book is passed over for the next rung up", rg(wide)["corner_n"], 11)
check("exactly 5c is in", S.cfn_spread(rung("X-1", 10, 0.66, yes_ask=0.39)), 0.05)
check("no rung at 0.60+: none, with why", S.cfn_rung(ladder("26NOV07ARSBUR", asks=((7, 0.3), (8, 0.59)))),
      (None, "no rung with a No ask of 0.60 or more and a No book 5c or tighter"))
check("the lowest qualifying rung's No above 0.95: the match is skipped (a pricier rung is never taken instead)",
      S.cfn_rung(ladder("26NOV07ARSBUR", asks=((8, 0.59), (13, 0.97), (14, 0.98)))),
      (None, "the lowest 0.60+ rung (13+) has a No ask of 0.97, over 0.95"))
check("0.95 itself is in", rg(ladder("26NOV07ARSBUR", asks=((12, 0.95),)))["corner_n"], 12)
check("every number fixed", (S.CFN_FAV_MIN, S.CFN_NO_MIN, S.CFN_NO_MAX, S.CFN_NO_FLOOR, S.CFN_NO_SPREAD, S.CFN_BID_UNDER,
                             S.CORNERS_LEAD_H), (0.55, 0.60, 0.95, 0.30, 0.05, 0.02, 4))

print("\nthe rule: a clear favourite, total rungs, every corners league, skips logged")
S.LANE_SKIPS.clear()
U = {"soccer": [board("26NOV07ARSBUR", 0.70, 0.20, 0.12), board("26NOV07LIVEVE", 0.40, 0.28, 0.36),
                board("26NOV07RMABAR", 0.30, 0.25, 0.48, lg="UCL")],
     "soccer_corners": (ladder("26NOV07ARSBUR") + ladder("26NOV07LIVEVE") + ladder("26NOV07CHEMUN")
                        + ladder("26NOV07RMABAR", lg="UCL", league="Champions League")
                        + ladder("26NOV07TOTWHU", hours=5) + [rung("26NOV07ARSBUR", 6, 0.62, kind="team")])}
U["soccer"].append(board("26NOV07TOTWHU", 0.80, 0.12, 0.10))
picks = S.fetch_corners_fav_no("soccer_corners", U, now=NOW)
check("the 0.69 favourite enters at its 10+ rung; 0.40 and a 0.47 away favourite do not",
      [(x["market_id"], x["pick"]) for x in picks], [("KXEPLCORNERS-26NOV07ARSBUR-10", "b")])
U["soccer"][2] = board("26NOV07RMABAR", 0.20, 0.22, 0.60, lg="UCL")
picks = S.fetch_corners_fav_no("soccer_corners", U, now=NOW)
check("the Champions League is included: an away favourite of 0.59 qualifies",
      sorted(x["market_id"] for x in picks), ["KXEPLCORNERS-26NOV07ARSBUR-10", "KXUCLCORNERS-26NOV07RMABAR-10"])
check("never a team rung", any("TCORNERS" in x["market_id"] for x in picks), False)
sk = S.take_skips().get("corners_fav_no") or {}
reasons = {k.split(":")[1]: v["reason"] for k, v in sk.items()}
check("skips logged with why: no board, no clear favourite; outside 4h is not considered",
      (reasons.get("26NOV07CHEMUN"), reasons.get("26NOV07LIVEVE", "")[:20], "26NOV07TOTWHU" in reasons),
      ("no Kalshi 1X2 board for the match", "no clear favourite: ", False))
check("take_skips empties the run's log", S.take_skips(), {})

print("\nregistered, ordered after the two match-total lanes, capped and locked like them")
meta = S.SOURCES["corners_fav_no"]
check("its terms", (meta["kind"], meta["sports"], meta["one_per_corners_fixture"], meta["day_cap"], meta["label"]),
      ("Rule", ["soccer_corners"], True, 5, "Corners total · favourite-side NO (v2)"))
order = list(S.CHALLENGERS)
check("read after corners_total_under and corners_ucl_fade", order.index("corners_total_under") < order.index("corners_ucl_fade")
      < order.index("corners_fav_no"), True)
check("corners_total_under is unchanged (still its own model rule)", "corners_selections(sport, universe, fixtures, now, kind=\"total\", ucl=False)"
      in inspect.getsource(S.fetch_corners_total_under), True)
_ch, _st, _fx = S.CHALLENGERS, T._started, S._espn_fixtures
S.CHALLENGERS = {k: S.CHALLENGERS[k] for k in ("corners_total_under", "corners_fav_no")}
T._started = lambda r, now: False
S._espn_fixtures = lambda: []
_sel = S.corners_selections
many = {"soccer": [board(f"26NOV07M{i:05d}", 0.75, 0.15, 0.12) for i in range(8)],
        "soccer_corners": [r for i in range(8) for r in ladder(f"26NOV07M{i:05d}")] + ladder("26NOV07NOBOARD")}
taken = "26NOV07M00000"
S.corners_selections = lambda sport, universe=None, fixtures=None, now=None, kind=None, ucl=None: (
    [(0.08, next(r for r in many["soccer_corners"] if taken in r["market_id"] and r["corner_n"] == 8))] if ucl is False else [])
try:
    led = {"quotes": [], "meta": {}, "coverage": {}}
    with um.patch.object(S, "datetime", wraps=S.datetime) as m:
        m.now.side_effect = lambda tz=None: NOW
        T.publish(led, many, {}, verbose=False)
        T.publish(led, many, {}, verbose=False)
finally:
    S.CHALLENGERS, T._started, S._espn_fixtures, S.corners_selections = _ch, _st, _fx, _sel
fav = [q for q in led["quotes"] if q["source"] == "corners_fav_no" and q["bet"]]
check("five a day after two runs, all on No at the taker ask", (len(fav), {q["pick"] for q in fav}, {q["price"] for q in fav}),
      (5, {"b"}, {0.66}))
check("the match corners_total_under took stays its own", [q["market_id"] for q in fav if taken in q["market_id"]], [])
check("one bet a match", len({q["market_id"].split("-")[1] for q in fav}), 5)
check("the run keeps its skip log on the ledger (meta lane_skips)",
      [v["reason"] for v in led["meta"]["lane_skips"]["corners_fav_no"].values()], ["no Kalshi 1X2 board for the match"])

print("\nthe maker bid: the ask - 2c, filled only by a print strictly below it, before kickoff")
q = dict(fav[0], logged=(NOW - dt.timedelta(hours=2)).isoformat(), start=NOW.isoformat())
lo, ko = int((NOW - dt.timedelta(hours=2)).timestamp()), int(NOW.timestamp())
calls = []


def trades(prints):
    def fetch(path):
        calls.append(path)
        return {"trades": [dict(created_time=dt.datetime.fromtimestamp(t, UTC).isoformat(), no_price_dollars=str(px),
                                count_fp="5") for t, px in prints], "cursor": ""}
    return fetch


check("the bid is the ask less 2c", C.bid_of(0.66), 0.64)
at_bid = C.check(q, NOW + dt.timedelta(hours=3), trades([(lo + 60, 0.64), (lo + 120, 0.65)]))
check("a print AT the bid only touches it: not filled", (at_bid["bid"], at_bid["filled"]), (0.64, False))
below = C.check(q, NOW + dt.timedelta(hours=3), trades([(lo + 60, 0.65), (lo + 600, 0.63)]))
check("a print strictly below fills it, at the bid's time", (below["filled"], below["fill_px"]), (True, 0.63))
late = C.check(q, NOW + dt.timedelta(hours=3), trades([(ko + 60, 0.40)]))
check("a print after kickoff never fills it (the bid is pulled at kickoff)", late["filled"], False)
check("the trades are asked for between selection and kickoff only", f"min_ts={lo}&max_ts={ko}" in calls[-1], True)
check("nothing is read before kickoff", C.check(q, NOW - dt.timedelta(minutes=5), trades([])), None)

print("\nthe records: maker headline, taker comparison, fill rate, after fees")
d = {"quotes": [dict(fav[0], status="won", result="b"), dict(fav[1], status="lost", result="a"),
                dict(fav[2], status="won", result="b"), dict(fav[3], status="open")]}
st = {"bids": {fav[0]["id"]: dict(bid=0.64, filled=True), fav[1]["id"]: dict(bid=0.64, filled=True),
               fav[2]["id"]: dict(bid=0.64, filled=False)}}
rec = C.records(d, st)
m, t = rec["maker"], rec["taker"]
check("maker: 3 bids placed, 2 filled, 1 unfilled, 1 waiting; 2 settled, 1 won", (m["placed"], m["filled"], m["unfilled"],
      m["waiting"], m["n"], m["won"]), (3, 2, 1, 1, 2, 1))
check("maker ROI after the maker fee at 64c", round(m["roi"], 4), round((1 / (0.64 + C.maker_fee(0.64)) - 1 - 1) / 2, 4))
check("taker split by the maker bid: filled 2 settled (1 won), not filled 1 settled (1 won); waiting not counted",
      ((rec["taker_filled"]["n"], rec["taker_filled"]["won"]), (rec["taker_unfilled"]["n"], rec["taker_unfilled"]["won"])),
      ((2, 1), (1, 1)))
check("taker: every entry at 66c, 3 settled, 2 won, 1 open, after the taker fee",
      (t["n"], t["won"], t["open"], round(t["roi"], 4)), (3, 2, 1, round((2 * (1 / (0.66 + C.taker_fee(0.66)) - 1) - 1) / 3, 4)))

print("\nthe Soccer page: one row right under Corners total under")
import soccer_build as SBLD
html = SBLD.build()
rules = html[html.find('<section id="rules"'):html.find('<section id="events"')]
names = re.findall(r'data-source="([^"]+)"', rules)
i = names.index("corners_total_under")
check("Corners total under, then this lane", names[i:i + 2], ["corners_total_under", "corners_fav_no"])
check("one row", names.count("corners_fav_no"), 1)
check("not listed among the idle lanes", "Corners total · favourite-side NO (v2)" in html[html.find('<section id="method"'):], False)
r = CB.row(d, [], st)
det = r["own"]["details"]
check("its fold: entry, exit, the maker-v-taker table with the fill rate and the filled/unfilled taker split, a closed In-sample note",
      ("<dt>Entry</dt>" in det and "the LOWEST N whose No ask is 0.60 or more" in det and "above 0.95 the match is skipped" in det,
       "<dt>Exit</dt>" in det, "Maker: No bid at the ask − 2c (headline)" in det,
       "Taker: the same rung at the No ask, every selected match (comparison)" in det, "2 of 3 (67%)" in det,
       "Taker, on the matches the bid filled" in det and "Taker, on the matches the bid did not fill" in det,
       '<details class="section-disclosure"><summary><b>In-sample</b>' in det, "z +0.97" in det),
      (True,) * 8)
check("its headline is the maker record", (r["a"]["n"], r["a"]["won"], r["after"], r["prod"]), (2, 1, "corners_total_under", False))
check("no guarded phrase", sandbox_audit.COPY_RE.search(det + meta["note"] + CB.IN_SAMPLE), None)

print(f"\n{'ALL PASS' if not FAILS else str(len(FAILS)) + ' FAILED'}")
sys.exit(1 if FAILS else 0)
