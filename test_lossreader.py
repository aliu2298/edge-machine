#!/usr/bin/env python3
"""Rule 1 v2 · Loss Reader (lossreader.py, sw15-lr1): the frozen rules, the replay, the comparisons, the page row."""
import datetime as dt
import re
import sys

import lossreader as LR
import sandbox_audit
import swing15 as W
import swing15_build as WB
import sw15cuts as _C2, swing15_build as _WB2, leadswap as _L2
_C2.RETIRED2, _WB2.NARROWED, _L2.TRADES_RETIRED = (), False, {}   # the lane as it ran before the 2026-11-11 narrowing; test_sw15keep.py checks the narrowed page

FAILS = []


def check(why, got, want):
    good = got == want
    print(f"  {'ok  ' if good else 'FAIL'} {why}" + ("" if good else f" — got {got!r}, want {want!r}"))
    if not good:
        FAILS.append(why)


UTC = dt.timezone.utc
T0 = int(dt.datetime(2026, 11, 10, 14, 0, tzinfo=UTC).timestamp())         # 8:00 AM CT, Tuesday
BTC, SOL, WTI = LR.MARKETS


def win(m, i, won, price=0.6, quoted=True, t0=T0):
    roi = None if won is None else round(won / (price + W.fee(price, W.TAKER)) - 1, 4)
    return dict(m=m, t=t0 + i * 900, quoted=quoted, won=won, price=price if quoted else None, roi=roi)


print("the pre-registration")
check("version, markets, triggers, thresholds", (LR.VERSION, LR.MARKETS, LR.TRIGGERS, LR.MIN_TODAY, LR.PRIOR_DAYS,
      round(LR.PRIOR_WEIGHT, 4), LR.STOP_LOSSES, LR.STOP_WINDOWS, LR.REVIEW_AT, LR.DECIDE_BETS, LR.DECIDE_DAYS),
      ("sw15-lr1", ("KXBTC15M", "KXSOL15M", "KXWTI15M"), (0, 1, 2, 3), 4, 3, 0.3333, 2, 4, 30, 100, 5))
check("the start is a window boundary", W._ts(LR.FROM) % 900, 0)

print("\ntriggers and learning")
m = LR.Market()
for i, won in enumerate([0, 0, 1, 0, 0, 0]):
    m.add(T0 + i * 900, won, 0.6)
check("streak and firing: after 3 losses every trigger fires", (m.streak, [m.fires(k) for k in LR.TRIGGERS]), (3, [True] * 4))
check("each observed window keeps the losses in a row before it", [o[3] for o in m.obs], [0, 1, 2, 0, 1, 2])
k, score, table = m.learn(T0 + 6 * 900)
check("scores: trigger 0 sums all six (won − price), trigger 1 the four after a loss",
      (round(table[0][0], 3), table[0][1], round(table[1][0], 3), table[1][1]), (-2.6, 6, (1 - .6) + 3 * -.6, 4))
check("no trigger above 0: Off", (k, score), (None, None))
m2 = LR.Market()
for i, won in enumerate([0, 1, 0, 1, 0, 1, 0, 1]):
    m2.add(T0 + i * 900, won, 0.6)
k2, s2, t2 = m2.learn(T0 + 8 * 900)
check("after-1 wins every time it fires (4 windows today): active, score 4 × 0.4", (k2, round(s2, 3), t2[1][1]), (1, 1.6, 4))
m3 = LR.Market()
for i, won in enumerate([0, 1, 0, 1, 0, 1]):
    m3.add(T0 + i * 900, won, 0.6)
check("fewer than 4 qualifying windows today: Off", m3.learn(T0 + 6 * 900)[0], None)
m4 = LR.Market()
prev = T0 - 86400                                                           # yesterday, the same clock
for i in range(6):
    m4.add(prev + i * 900, 1, 0.5)                                          # +0.5 each yesterday on trigger 0
for i, won in enumerate([1, 0, 1, 0]):
    m4.add(T0 + i * 900, won, 0.5)                                          # 0 net today on trigger 0
k4, s4, t4 = m4.learn(T0 + 4 * 900)
check("the previous 3 days count a third: trigger 0 = 0 + 3.0 / 3", (k4, round(s4, 3)), (0, 1.0))
m5 = LR.Market()
for i in range(6):
    m5.add(T0 - 5 * 86400 + i * 900, 1, 0.5)                                # 5 days ago: outside the 3 days
for i, won in enumerate([1, 0, 1, 0]):
    m5.add(T0 + i * 900, won, 0.5)
check("older than 3 days does not count", m5.learn(T0 + 4 * 900)[0], None)
mid = int(dt.datetime(2026, 11, 10, 6, 0, tzinfo=UTC).timestamp())         # midnight CT
check("the day is Central: 05:59Z is yesterday, 06:00Z today", (LR.ct_day(mid - 60), LR.ct_day(mid)),
      (dt.date(2026, 11, 9), dt.date(2026, 11, 10)))

print("\nthe replay: one pick, the stop rule, no fills")
# Bitcoin: wins every window from 0..7 (trigger 0 active from window 4); Solana: alternates (after-1 learns later).
ws = [win(BTC, i, 1) for i in range(12)] + [win(SOL, i, i % 2) for i in range(12)]
bets, st = LR.replay(ws)
check("no bet before 4 qualifying windows today; then Bitcoin every window", [(b["m"], (b["t"] - T0) // 900) for b in bets][:3],
      [(BTC, 4), (BTC, 5), (BTC, 6)])
check("one pick per window", len({b["t"] for b in bets}) == len(bets), True)
both = [win(BTC, i, 1) for i in range(6)] + [win(SOL, i, 1, price=0.55) for i in range(6)]
b2, _ = LR.replay(both)
check("two markets fire: the higher score is bet (Solana, cheaper wins score more)", [b["m"] for b in b2], [SOL, SOL])
tie = [win(BTC, i, 1) for i in range(6)] + [win(WTI, i, 1) for i in range(6)]
check("a tie goes to Bitcoin, then Solana, then WTI", [b["m"] for b in LR.replay(tie)[0]], [BTC, BTC])
stop = [win(BTC, i, 1) for i in range(5)] + [win(BTC, 5, 0), win(BTC, 6, 0)] + [win(BTC, i, 1) for i in range(7, 16)]
b3, st3 = LR.replay(stop)
offs = [(b["t"] - T0) // 900 for b in b3]
check("two losing bets in a row (windows 5 and 6): Off for the next 4 windows (7-10), re-learned and back at 11",
      (offs[:3], [i for i in range(7, 11) if i in offs], 11 in offs), ([4, 5, 6], [], True))
nf = [win(BTC, i, 1) for i in range(4)] + [dict(m=BTC, t=T0 + 4 * 900, quoted=True, won=None, price=0.6, roi=None),
                                          win(SOL, 4, 1)]
b4, _ = LR.replay(nf)
check("a picked window S2 could not fill is a no fill, never swapped for another market", [(b["m"], b["status"]) for b in b4],
      [(BTC, "no_fill")])
check("a no-fill window is not an observed result", len(LR.replay(nf)[1]["markets"][BTC].obs), 4)

print("\ncomparisons and the Now line")
every, fixed = LR.compare(stop, T0 + 2 * 900)
check("every bet = every observed window from the start; fixed after 2 = after two observed losses",
      (len(every), [(w["t"] - T0) // 900 for w in fixed]), (14, [7]))
check("stats", LR.stats([win(BTC, 0, 1, .5), win(BTC, 1, 0, .5)])["hits"], 1)
line = LR.now_line(st3, T0 + 10 * 900)
check("the Now line names each market's trigger, and a stop with its return time",
      (line.startswith("Now: Bitcoin Off (2 losing bets; back"), "Solana Off" in line, "WTI Crude Oil Off" in line), (True, True, True))
check("trigger words", [LR.trigger_word(k) for k in (None, 0, 1, 2, 3)], ["Off", "every window", "after 1", "after 2", "after 3"])

print("\nthe page")
state = dict(W.empty(), windows={})
html = WB.section(state)
blk = html.split('id="lossreader"')[1].split('<div class="sw15-lane">')[0]
check("the lane is first, one collapsed row", (html.index('id="lossreader"') < html.index('id="steadyfav"'),
      len(re.findall(r'<details class="sp-rule[^"]*"[^>]*data-source="lossreader"', blk)),
      bool(re.search(r'<details class="sp-rule[^"]*"[^>]* open', blk))), (True, 1, False))
check("one intro line", re.findall(r'sw15-intro">(.*?)</p>', blk),
      [f"Paper · fresh record from {WB._start(LR.FROM)} · review 30, decide 100 bets or 5 trading days"])
check("inside the row: the Now line, today's bets, the split, the comparison books",
      all(x in blk for x in ("Now: Bitcoin", "Today's bets", "doing well · ", "Every bet (S2 on the 3 markets)",
                             "Fixed after 2 losses")), True)
check("the rules and the backtest sit in the How-kept fold", ("Two losing bets in a row" in blk.split("How the record is kept")[1],
      "Backtest (report only" in blk.split("How the record is kept")[1]), (True, True))
check("status and evidence", ("Too early (0/30)" in blk, ">0/100<" in blk), (True, True))
check("the Sandbox index lists it first", WB.index_rows(state)[0]["lane"], "lossreader")
check("no dollar sign, no guarded phrase, no inline style", (re.search(r"\$\d", html), sandbox_audit.COPY_RE.findall(html),
      "style=" in html), (None, [], False))
led = LR.ledger(state, dt.datetime(2026, 11, 10, 6, 0, tzinfo=UTC))
check("the ledger", (led["version"], led["from"], led["record"], led["now_for"] % 900), ("sw15-lr1", LR.FROM, None, 0))

print(f"\n{'ALL PASS' if not FAILS else str(len(FAILS)) + ' FAILED'}")
sys.exit(1 if FAILS else 0)
