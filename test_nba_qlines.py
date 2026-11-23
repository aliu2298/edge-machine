#!/usr/bin/env python3
"""Offline checks for the NBA quarter lines lane (nba_qlines.py): the tracker (no look-ahead), the gate, the rung rule (harder direction only), one entry for
two qualifying teams, the blind control, drop and re-enter, settlement, the page and the public copy."""
import datetime as dt
import json
import os
import sys

import nba_qlines as Q
import nba_qlines_build as B
import sandbox_audit

FAILS = []
UTC = dt.timezone.utc
ET = Q.ET


def check(label, got, want):
    ok = got == want
    print(f"  {'ok  ' if ok else 'FAIL'} {label}" + ("" if ok else f" (got {got!r}, want {want!r})"))
    if not ok:
        FAILS.append(label)


def game(i, day, home, away, h, a):
    """h, a: period lists."""
    t = dt.datetime.fromisoformat(day + "T19:00:00").replace(tzinfo=ET)
    return dict(id=str(i), t=t.timestamp(), day=day, home=home, away=away, ls={home: h, away: a})


def days(n, start=dt.date(2026, 10, 20)):
    return [(start + dt.timedelta(days=i)).isoformat() for i in range(n)]


# ---- the tracker: hits, games, no look-ahead
print("tracker")
HI, LO = [35, 35, 35, 35], [20, 20, 20, 20]               # 3Q combined 70 (over 53.5 and 64.5 hit, under miss) / 40 (over miss, under hit)
ds = days(12)
games = [game(i, ds[i], "AAA", "BBB", HI, HI) for i in range(10)]
r = Q.team_rows(games, "3Q", "over")
check("10 hits in 10 games qualifies at 100%", (r["AAA"]["hits"], r["AAA"]["n"], r["AAA"]["qualifies"]), (10, 10, True))
check("qualified since the 10th game's day", r["AAA"]["since"], ds[9])
check("9 games is below the floor even at 100%", Q.team_rows(games[:9], "3Q", "over")["AAA"]["qualifies"], False)
r = Q.team_rows(games, "3Q", "over", before=ds[9])
check("no look-ahead: games on or after the night are not counted", (r["AAA"]["n"], r["AAA"]["qualifies"]), (9, False))
check("under counts the other side (total below the line)", Q.team_rows(games, "3Q", "under")["AAA"]["hits"], 0)
check("1H is the first two periods", Q.total(game(1, ds[0], "A", "B", [10, 20, 99, 99], [30, 40, 99, 99]), (1, 2)), 100)
ot = game(2, ds[0], "A", "B", [10, 10, 10, 10, 7], [10, 10, 10, 10, 5])
check("2H counts overtime, 4Q does not", (Q.total(ot, (3, 4), True), Q.total(ot, (4,))), (52, 20))
check("an unscorable game (3 periods) is skipped", Q.hit(game(3, ds[0], "A", "B", [1, 2, 3], [1, 2, 3]), "4Q", "over"), None)

# ---- drop and re-enter
print("\ndrop and re-enter")
seq = games + [game(10, ds[10], "AAA", "BBB", LO, LO)]            # 10/11 = 90.9%, still in
check("10/11 is 91%: still qualifies", Q.team_rows(seq, "3Q", "over")["AAA"]["qualifies"], True)
seq2 = seq + [game(11, ds[11], "AAA", "BBB", LO, LO)]             # 10/12 = 83%: out at once
r = Q.team_rows(seq2, "3Q", "over")
check("10/12 is below 90%: stops at once, no since", (r["AAA"]["qualifies"], r["AAA"]["since"]), (False, None))
more = [game(20 + i, days(30)[12 + i], "AAA", "BBB", HI, HI) for i in range(10)]   # 20/22 = 90.9%
r = Q.team_rows(seq2 + more, "3Q", "over")
check("climbs back: qualifies again, since the game that put it back over the bar", (r["AAA"]["qualifies"], r["AAA"]["since"]), (True, days(30)[19]))

# ---- the rung rule
print("\nrung rule")
def mk(strike, bid, ask, g="BBB@AAA"):
    a, h = g.split("@")
    return dict(ticker=f"KXNBA3QTOTAL-26NOV23{a}{h}-{int(strike + 0.5)}", event_ticker=f"KXNBA3QTOTAL-26NOV23{a}{h}", floor_strike=strike,
                yes_bid_dollars=str(bid), yes_ask_dollars=str(ask))
G = dict(id="9", tip=dt.datetime(2026, 11, 23, 23, 0, tzinfo=UTC), home="AAA", away="BBB")
ladder = {"3Q": [mk(50.5, .80, .82), mk(52.5, .60, .62), mk(54.5, .40, .42), mk(55.5, .30, .32), mk(56.5, .20, .22), mk(64.5, .50, .52), mk(63.5, .46, .48), mk(62.5, .30, .33), mk(66.5, .70, .72)]}
x, why = Q.pick_rung(ladder, G, "3Q", "over")
check("over 53.5 not listed: the nearest HIGHER rung (54.5), never the lower 52.5", (x["rung"], x["offset"], x["price"], x["side"]), (54.5, 1, 0.42, "yes"))
x, why = Q.pick_rung(ladder, G, "3Q", "under")
check("under 64.5 listed: the exact line, NO price = 1 - YES bid", (x["rung"], x["offset"], x["price"], x["side"]), (64.5, 0, 0.5, "no"))
lad2 = {"3Q": [mk(66.5, .70, .72), mk(61.5, .2, .22)]}
x, why = Q.pick_rung(lad2, G, "3Q", "under")
check("under: only a HIGHER rung (66.5) or one 3 away below (61.5): 61.5 is 3 points harder, used", (x["rung"], x["offset"]), (61.5, 3))
x, why = Q.pick_rung({"3Q": [mk(66.5, .70, .72)]}, G, "3Q", "under")
check("under: a higher rung is never taken", (x, why), (None, "no rung within 3 points"))
x, why = Q.pick_rung({"3Q": [mk(52.5, .6, .62)]}, G, "3Q", "over")
check("over: a lower rung is never taken", (x, why), (None, "no rung within 3 points"))
x, why = Q.pick_rung({"3Q": [mk(53.5, .40, .50)]}, G, "3Q", "over")
check("a wide spread (10c) is no entry", (x, why), (None, "wide"))
x, why = Q.pick_rung({"3Q": [mk(54.5, .40, .42, "ZZZ@AAA")]}, G, "3Q", "over")
check("another game's market is not used", (x, why), (None, "no market"))

# ---- entries: one for two qualifying teams, blind in every game, nothing for non-qualifying
print("\nentries")
doc = {"games": [game(i, ds[i], "AAA", "BBB", HI, HI) for i in range(10)] + [game(100 + i, ds[i], "CCC", "DDD", LO, LO) for i in range(10)]}
st = Q.empty()
now = dt.datetime(2026, 11, 23, 22, 30, tzinfo=UTC)
mk3 = {s: [] for s in Q.SECTIONS}
mk3["3Q"] = [mk(53.5, .60, .62), mk(64.5, .50, .52), mk(53.5, .60, .62, "DDD@CCC"), mk(64.5, .50, .52, "DDD@CCC")]
g1 = dict(id="1", tip=dt.datetime(2026, 11, 23, 23, 0, tzinfo=UTC), home="AAA", away="BBB")
g2 = dict(id="2", tip=dt.datetime(2026, 11, 23, 23, 0, tzinfo=UTC), home="CCC", away="DDD")
new = Q.look_many(st, doc, [g1, g2], mk3, now)
over = st["rules"]["qlines_3Q_over"]["picks"]
check("both AAA and BBB qualify on 3Q over: ONE entry", (len(over), over[0]["qualifying"], over[0]["game_id"]), (1, ["AAA", "BBB"], "1"))
check("an over buys the YES ask", (over[0]["side"], over[0]["price"]), ("yes", 0.62))
check("no entry for the game whose teams do not qualify", [p["game_id"] for p in over], ["1"])
check("the blind control covers BOTH games", sorted(p["game_id"] for p in st["rules"]["qlines_3Q_over_blind"]["picks"]), ["1", "2"])
und_rows = st["rules"]["qlines_3Q_under"]["picks"]
check("under: only the LO game (CCC, DDD at 10/10 below 64.5) enters, one entry, NO at 1 - bid; blind in both games",
      ([(p["game_id"], p["qualifying"], p["side"], p["price"]) for p in und_rows], len(st["rules"]["qlines_3Q_under_blind"]["picks"])), ([("2", ["CCC", "DDD"], "no", 0.5)], 2))
check("a section with no markets enters nothing", len(st["rules"]["qlines_1Q_over_blind"]["picks"]), 0)
check("each game is read once and logged", sorted(st["looks"]), ["1", "2"])
check("the lane row points at its blind row", over[0]["matches"] in [p["id"] for p in st["rules"]["qlines_3Q_over_blind"]["picks"]], True)
check("due(): only a game 15-40 minutes out and not yet read",
      [g["id"] for g in Q.due([dict(g1, tip=now + dt.timedelta(minutes=30)), dict(g2, tip=now + dt.timedelta(minutes=50)),
                               dict(g1, id="3", tip=now + dt.timedelta(minutes=10))], now, {})], ["1"])
# the gate is as of the night: games finished earlier the same night do not count
today_game = game(500, "2026-11-23", "AAA", "BBB", LO, LO)
doc2 = {"games": doc["games"] + [today_game]}
st2 = Q.empty()
Q.look_many(st2, doc2, [g1], mk3, now)
check("a game played TONIGHT is not in the gate (still one entry)", len(st2["rules"]["qlines_3Q_over"]["picks"]), 1)
tr = {"games": [game(i, ds[i], "AAA", "BBB", HI, HI) for i in range(9)]}
st3 = Q.empty()
Q.look_many(st3, tr, [g1], mk3, now)
check("9 games: no entry (the floor)", len(st3["rules"]["qlines_3Q_over"]["picks"]), 0)

# ---- settle
print("\nsettle")
row = dict(over[0], status="open")
Q.settle_row(row, 1.0)
c = 0.62 + Q.fee(0.62)
check("over wins when YES pays: profit 1 - cost", (row["status"], row["profit"]), ("won", round(1 - c, 4)))
und = dict(id="u", rule="qlines_3Q_under", side="no", price=0.5, night="2026-11-23", status="open")
Q.settle_row(und, 1.0)
check("an under (NO) loses when YES pays", (und["status"], und["payout"], und["profit"] < 0), ("lost", 0.0, True))
und2 = dict(und, status="open")
Q.settle_row(und2, 0.0)
check("an under (NO) wins when YES does not pay", (und2["status"], und2["payout"]), ("won", 1.0))


class FakeFetch:
    def __init__(self, result):
        self.result = result

    def __call__(self, path):
        return {"market": dict(status="settled", result=self.result)}


st4 = {"rules": {"qlines_3Q_over": {"picks": [dict(over[0], status="open")]}}}
errs = Q.settle(st4, now + dt.timedelta(hours=6), FakeFetch("yes"))
check("settle() grades a finished game from Kalshi's result", (errs, st4["rules"]["qlines_3Q_over"]["picks"][0]["status"]), ([], "won"))
st5 = {"rules": {"qlines_3Q_over": {"picks": [dict(over[0], status="open")]}}}
Q.settle(st5, now, FakeFetch("yes"))
check("an unfinished game is left open", st5["rules"]["qlines_3Q_over"]["picks"][0]["status"], "open")
check("status text reads n of 10, then 30", (Q.status_text(3), Q.status_text(12), Q.status_text(31)),
      ("3 of 10 settled · read at 10", "12 settled · first read (10) due · next at 30", "31 settled · second read (30) due"))

# ---- the config and the live data
print("\nconfig")
check("six sections, all with both lines (the half lines are live)", [(s, Q.LINES[s]["over"], Q.LINES[s]["under"]) for s in Q.SECTIONS],
      [("1Q", 51.5, 59.5), ("2Q", 50.5, 63.5), ("3Q", 53.5, 64.5), ("4Q", 48.5, 62.5), ("1H", 104.5, 119.5), ("2H", 100.5, 115.5)])
check("24 lanes (6 sections x 2 directions x lane and blind)", len(Q.ALL_LANES), 24)
check("the bar and the floor are config", (Q.THRESHOLD, Q.MIN_GAMES), (0.9, 10))
live = Q.load_games()["games"]
if len(live) >= 200:
    TOP = lambda s, d: {t: f"{v['hits']}/{v['n']}" for t, v in Q.team_rows(live, s, d, before="2026-11-23").items() if v["qualifies"]}   # noqa: E731
    check("Nov 22 sanity (3Q over 53.5): MIL 17/17, MEM 16/17, PHX 14/15", {t: TOP("3Q", "over").get(t) for t in ("MIL", "MEM", "PHX")},
          {"MIL": "17/17", "MEM": "16/17", "PHX": "14/15"})
    check("Nov 22 sanity: 4Q under 62.5 SAC 16/16, 1Q under 59.5 MIL 16/17", (TOP("4Q", "under").get("SAC"), TOP("1Q", "under").get("MIL")), ("16/16", "16/17"))

# ---- the page
print("\npage")
html = B.section(st, doc)
check("six collapsed folds, none open", (html.count('class="fold nba-qline"'), " open" in html.replace("section-disclosure", "")), (6, False))
check("the sections in order", [s for s in ("1q", "2q", "3q", "4q", "1h", "2h") if f'id="qlines-{s}"' in html], ["1q", "2q", "3q", "4q", "1h", "2h"])
check("the lane record sits beside its blind control", "Blind control" in html and "Qualifying now" in html, True)
check("the 3Q table lists the qualifying teams with hits/games", "10/10" in html and "AAA" in html, True)
check("n of 10 shows", "of 10 settled" in html, True)
idx = B.index_html(st)
check("the Sandbox index links each section", all(f"./nba.html#qlines-{s}" in idx for s in ("1q", "2q", "3q", "4q", "1h", "2h")), True)
bad = [m.group(0) for m in sandbox_audit.COPY_RE.finditer(html + idx)]
check("public copy passes the guard", bad, [])
check("no inline style or SVG", ("style=" in html or "<svg" in html), False)
check("an empty ledger still renders", "<h2>NBA quarter lines (Sandbox)</h2>" in B.section(Q.empty(), {"games": []}), True)

print("\nALL PASS" if not FAILS else f"\n{len(FAILS)} FAILED: {FAILS}")
sys.exit(1 if FAILS else 0)
