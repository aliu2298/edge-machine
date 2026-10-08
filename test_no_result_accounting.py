#!/usr/bin/env python3
"""A bet the venue paid out at a price (a cancelled or abandoned match settled at
50¢ a side) is money in the ROI, a count beside the record, and never a win or a
loss — on every page that shows the status, with the same words.

Covers sandbox_track.assess (n_price, the money), record_text and no_result_label,
the Sandbox settled-list badge and day summary, the home roll's counts and chip
words, and the Production settled list.
"""
import datetime
import json
import os
import re
import sys
from datetime import timedelta, timezone

import sandbox_build as B
import sandbox_track as T
import shell_build

ROOT = os.path.dirname(os.path.abspath(__file__))
NOW = datetime.datetime(2026, 10, 8, 12, 0, tzinfo=timezone.utc)
FAILED = 0


def ok(cond, label):
    global FAILED
    print(f"  {'ok  ' if cond else 'FAIL'} {label}")
    if not cond:
        FAILED += 1


def eq(got, want, label):
    ok(got == want, f"{label} — got {got!r}, want {want!r}")


def _bet(i, status, price, result=None, settle_px=None, hours_ago=30):
    start = NOW - timedelta(hours=hours_ago)
    pnl = {"won": round(100 * (1 / price - 1), 2), "lost": -100.0}.get(status)
    if status == "settled":
        pnl = round(100 * (settle_px / price - 1), 2)
    return dict(
        id=f"q{i}", source="oddspedia", sport="cricket", bet=True, status=status,
        pick="a", price=price, result=result, venue="kalshi", stake=100.0, pnl=pnl,
        settle_px=settle_px, start=start.isoformat(), logged=(start - timedelta(hours=3)).isoformat(),
        settled=(start + timedelta(hours=4)).isoformat() if status != "open" else None,
        date=start.date().isoformat(), price_a=price, price_b=round(1 - price, 2),
        side_a="Alpha", side_b="Beta", label=f"Alpha v Beta {i}", market_id=f"m{i}",
    )


print("assess: a 50¢ payout is money, not a result")
d = {"quotes": [
    _bet(1, "won", 0.40, result="a", hours_ago=60),
    _bet(2, "lost", 0.40, result="b", hours_ago=50),
    _bet(3, "lost", 0.50, result="b", hours_ago=40),
    _bet(4, "settled", 0.40, result="price", settle_px=0.5, hours_ago=30),
    _bet(5, "settled", 0.60, result="price", settle_px=0.5, hours_ago=20),
    _bet(6, "void", 0.40, result="void", hours_ago=10),
]}
a = T.assess(d, "oddspedia", "cricket")
eq((a["n"], a["won"]), (3, 1), "n and won are the wins and losses only")
eq(a["n_price"], 2, "n_price counts the bets paid out at a price")
money = [q for q in d["quotes"] if q["status"] in ("won", "lost", "settled")]
eq(round(a["roi"], 6), round(sum(q["pnl"] for q in money) / 500.0, 6),
   "ROI is every stake's P/L over every stake: cost the entry price, payout 50¢")
eq(round(a["roi_fee"], 6), round(sum(T.pnl_after_fee(q) for q in money) / 500.0, 6),
   "ROI after fees charges the fee on the 50¢ payout the same way")
eq(round(T.pnl_after_fee(d["quotes"][4]), 2), round(100 * (0.5 / (0.60 + 0.07 * 0.60 * 0.40) - 1), 2),
   "a 60¢ entry paid 50¢ is a loss after fees, not a void")
ok(a["roi"] != sum(q["pnl"] for q in money[:3]) / 300.0, "the W–L-only figure is not the ROI")

print("\nthe words")
eq(T.record_text(a), "1–2, 2 no result", "the record names the no-result count beside the W–L")
eq(T.record_text(dict(n=3, won=1)), "1–2", "no no-result bets: the plain W–L")
eq(T.record_text(dict(n=0, won=0, n_price=2)), "0–0, 2 no result", "a lane with only no-result bets says so")
eq(T.record_text(dict(n=0, won=0)), "—", "nothing settled is an em dash")
eq(T.NO_RESULT_LABEL, "No result · paid 50¢", "the shared label")
eq(T.no_result_label(d["quotes"][3]), "No result · paid 50¢", "a 0.5 settlement reads paid 50¢")
eq(T.no_result_label(dict(settle_px=0.35)), "No result · paid 35¢", "another settlement price is printed as stored")
eq(T.no_result_label(None), "No result · paid 50¢", "no row at all falls back to the Kalshi rule")
eq(shell_build.PRICE_LABEL, T.NO_RESULT_LABEL, "the home roll uses the same label")
ok("Settled on price" not in open(os.path.join(ROOT, "shell_build.py")).read()
   and "Settled on price" not in open(os.path.join(ROOT, "cricket_cards.py")).read(),
   "the old label is gone from the builders")

print("\nthe Sandbox settled list")
eq(B._badge(d["quotes"][3]), ("price", "NO RESULT"), "the badge says NO RESULT, not PRICE")
won, n, extra, pl = B._day_summary(d["quotes"][:5])
eq((won, n), (1, 3), "the day summary's W–L leaves the no-result bets out")
eq(extra, " · 2 no result", "and counts them beside it")
eq(round(pl, 2), round(sum(q["pnl"] for q in money), 2), "their P/L is in the day's money")

print("\nthe home roll")
contests = [
    {"bucket": "settled", "cards": [{"status": "W"}, {"status": "L"}, {"status": shell_build.PRICE_LABEL}]},
    {"bucket": "live", "cards": [{"status": "Open"}]},
    {"bucket": "settled", "cards": [{"status": "Void"}, {"status": shell_build.PRICE_LABEL}]},
]
eq(shell_build._roll_counts(contests), (1, 3, 1),
   "open, settled and won counts leave the no-result chips out of settled")
eq(shell_build._roll_no_result(contests), 2, "the no-result chips are counted apart")
eq(shell_build._COMBO_TOKEN[shell_build.PRICE_LABEL], "no result", "a combined chip says 'no result'")
eq(shell_build._SPOKEN[shell_build.PRICE_LABEL], "no result, paid 50 cents", "and is spoken as such")
eq(shell_build._STATUS_TOKEN[shell_build.PRICE_LABEL], "price", "the data-status token is unchanged")

print("\nthe Production settled list")
src = open(os.path.join(ROOT, "production.py")).read()
ok("T.NO_RESULT_LABEL if l['status'] == 'price'" in src and "'paid' if l['status'] == 'price'" not in src,
   "a price lead reads No result · paid 50¢, not 'paid'")
ok("T.record_text(live)" in src, "the since-Production record carries the no-result count")
ok("A tip is unreachable when no Kalshi or Polymarket US market was listed for it" in src,
   "the reachable column is explained in one line")

print(f"\n{'FAILED: ' + str(FAILED) if FAILED else 'all ok'}")
sys.exit(1 if FAILED else 0)
