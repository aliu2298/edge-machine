#!/usr/bin/env python3
"""Eight retired trading rules taken off the board the same way a Sandbox lane is.

They do not render, and they do not log or grade a new trade. The rows already
in the ledger stay, count and content. A rule with no trades that is not in
the removed set still renders. No network, and nothing is written.
"""
import copy
import datetime
import os
import sys

import cricket_build
import market_track as MT
import production
import sandbox_build as SB
import sandbox_track as T
import site_root
import soccer_build
import tennis_build

FAILS = []
NOW = datetime.datetime(2026, 10, 4, 12, tzinfo=datetime.timezone.utc)
ROOT = os.path.dirname(os.path.abspath(__file__))
EIGHT = (
    "cr_btc_2200",
    "dt_intraday_mom",
    "sw_52w_breakout",
    "sw_ma_cross_rsi",
    "cr_trend20",
    "dt_orb30",
    "dt_orb30_long",
    "dt_vwap_reclaim",
)
# Closed and open counts on the ledger this test reads. The headline is the
# sum of the rules that stay.
LANE_COUNTS = {
    "cr_btc_2200": (9, 0),
    "dt_intraday_mom": (15, 0),
    "sw_52w_breakout": (2, 11),
    "sw_ma_cross_rsi": (1, 19),
    "cr_trend20": (0, 0),
    "dt_orb30": (158, 0),
    "dt_orb30_long": (56, 0),
    "dt_vwap_reclaim": (153, 0),
}
KEPT = "sw_rsi2_pullback"


def ok(cond, why):
    print(f"  {'ok  ' if cond else 'FAIL'} {why}")
    if not cond:
        FAILS.append(why)


def eq(got, want, why):
    ok(got == want, why if got == want else f"{why} — got {got!r}, want {want!r}")


def bar(day, o, h, l, c, v=2_000_000):
    return {"t": f"{day}T00:00:00Z", "o": o, "h": h, "l": l, "c": c, "v": v}


def _day(offset, first=datetime.date(2025, 1, 1)):
    return (first + datetime.timedelta(days=offset)).isoformat()


def _pages():
    sandbox, index, weeks = SB.render_pages(NOW)
    out = {
        "sandbox.html": sandbox,
        "archive/index.html": index,
        "production.html": production.page(
            T.load(), T.load_stages(), production.load_feed(), "", now=NOW),
        "trading.html": SB.trading_page(NOW),
        "index.html": site_root.root_stub(NOW),
    }
    root = os.path.join(ROOT, "public_site", "index.html")
    with open(root, encoding="utf-8") as f:
        out["public_site/index.html"] = f.read()
    out.update({f"archive/{slug}.html": html for slug, html in weeks.items()})
    out["soccer.html"] = soccer_build.build(now=NOW)
    out["tennis.html"] = tennis_build.build(now=NOW)
    out["cricket.html"] = cricket_build.build(now=NOW)
    return out


def _counts(trades, rule):
    rows = [t for t in trades if t.get("rule") == rule]
    closed = sum(1 for t in rows if t.get("status") == "closed")
    opened = sum(1 for t in rows if t.get("status") == "open")
    return rows, closed, opened


def _board_tiles(trades):
    """Closed and open tiles: the sum of lanes that are not in the removed set.

    Read from the ledger the page renders, so a later close on a lane still
    on the board moves the page and this expectation together.
    """
    kept = [t for t in trades
            if t.get("rule") not in set(EIGHT) and not t.get("research")]
    closed = sum(1 for t in kept if t.get("status") == "closed")
    opened = sum(1 for t in kept if t.get("status") == "open")
    return closed, opened


print("\nthe eight retired rules are the removed set")
removed = getattr(MT, "REMOVED_RULES", None)
ok(removed is not None and set(removed) == set(EIGHT),
   "exactly these eight rules are removed")
retired = {name for name, meta in MT.RULES.items() if meta.get("retired")}
ok(retired == set(EIGHT), "every retired trading rule is one of the eight, and no other rule is")
gate = getattr(MT, "rule_removed", lambda _name: False)
ok(all(gate(name) for name in EIGHT), "the entry gate blocks each of the eight")
ok(not gate(KEPT), "a rule still on the board is not blocked")

print("\nthe ledger rows are unchanged")
ledger = MT.load()
snapshot = copy.deepcopy(ledger["trades"])
for name, (want_closed, want_open) in LANE_COUNTS.items():
    rows, closed, opened = _counts(snapshot, name)
    eq((closed, opened, len(rows)), (want_closed, want_open, want_closed + want_open),
       f"{name} still has {want_closed} closed and {want_open} open")

book = copy.deepcopy(ledger)
# Session bars the opening-range rule would take. Times are UTC, summer hours.
def m5(hhmm, o, h, l, c):
    return {"t": f"2026-09-18T{hhmm}:00Z", "o": o, "h": h, "l": l, "c": c, "v": 100000}

session = [m5(*row) for row in (
    ("13:30", 100, 102, 100, 101), ("13:35", 101, 102, 100, 101),
    ("13:40", 101, 102, 100, 100.5), ("13:45", 100.5, 101, 100, 100.8),
    ("13:50", 100.8, 101.5, 100.2, 101), ("13:55", 101, 102, 100.5, 101.5),
    ("14:00", 101.5, 103, 101.4, 102.5), ("14:05", 102.6, 104, 102.5, 103.5),
    ("14:10", 103.5, 105, 103, 104.5), ("19:55", 104.5, 105, 104, 104.8),
)]
flat = []
for i in range(260):
    flat.append(bar(_day(i), 100, 101, 99, 100))
flat[-1] = bar(flat[-1]["t"][:10], 100, 106, 100, 105, v=5_000_000)
flat.append(bar("2025-09-18", 105, 106, 104, 105))
btc = [
    {"t": "2026-09-24T21:00:00Z", "o": 99, "h": 99, "l": 99, "c": 99, "v": 1},
    {"t": "2026-09-24T22:00:00Z", "o": 100, "h": 101, "l": 99, "c": 100.5, "v": 1},
    {"t": "2026-09-24T23:00:00Z", "o": 100.5, "h": 102, "l": 100, "c": 101.8, "v": 1},
    {"t": "2026-09-25T00:00:00Z", "o": 102, "h": 102, "l": 101, "c": 101.5, "v": 1},
]
MT.scan({"AAA": flat, "SPY": flat}, book, rules=MT.RULES)
MT.scan_day({"AAA": session, "SPY": session}, book, rules=MT.RULES)
MT.scan_hours({"BTC/USD": btc}, book, rules=MT.RULES, research_before="2026-09-19")
fresh = {"trades": [], "meta": {}}
MT.scan_day({"AAA": session, "SPY": session}, fresh, rules=MT.RULES)
MT.scan_hours({"BTC/USD": btc}, fresh, research_before="2026-09-19")
MT.scan({"AAA": flat}, fresh, rules=MT.RULES)
by_id_before = {t["id"]: t for t in snapshot if t.get("rule") in set(EIGHT)}
by_id_after = {t["id"]: t for t in book["trades"] if t.get("rule") in set(EIGHT)}
eq(set(by_id_after), set(by_id_before), "no removed rule gains or loses a trade id")
eq(by_id_after, by_id_before, "every removed rule's trades keep the same content")
eq([t for t in fresh["trades"] if t.get("rule") in set(EIGHT)], [],
   "a fresh book logs nothing on the eight, even when the scan is handed every rule")

open_row = next(t for t in snapshot if t.get("rule") == "sw_52w_breakout" and t.get("status") == "open")
grade_book = {"trades": [copy.deepcopy(open_row)], "meta": {}}
entry = open_row["entry_day"]
bars = [bar(entry, 100, 101, 99, 100)]
for i in range(1, 45):
    day = (datetime.date.fromisoformat(entry) + datetime.timedelta(days=i)).isoformat()
    bars.append(bar(day, 50, 51, 40, 45))
before_grade = copy.deepcopy(grade_book["trades"][0])
MT.grade({open_row["symbol"]: bars, "SPY": bars}, grade_book)
eq(grade_book["trades"][0], before_grade, "grading leaves an open removed trade unchanged")

print("\na rule still on the board still enters and still renders")
kept_book = {"trades": [], "meta": {}}
rise = []
for i in range(215):
    p = 100 + i * 0.1
    rise.append(bar(_day(i), p, p * 1.01, p * 0.99, p))
rise.append(bar("2025-08-04", 121.0, 122, 120, 121.5))
n_kept = MT.scan({"SPY": rise}, kept_book)
ok(n_kept > 0 and any(t.get("rule") == "etf_overnight" for t in kept_book["trades"]),
   "the overnight rule, which is not removed, still logs a trade")
ok(all(t.get("rule") not in set(EIGHT) for t in kept_book["trades"]),
   "that same scan does not log one of the eight")

print("\nthe eight are hidden on every built page, and an empty lane is not")
pages = _pages()
labels = {name: MT.RULES[name]["label"] for name in EIGHT}
for name, html in pages.items():
    hit = next((rule for rule in EIGHT if rule in html), None)
    if hit is None:
        hit = next((labels[rule] for rule in EIGHT if labels[rule] in html), None)
    ok(hit is None, f"{name} does not show a removed trading rule" + (f" ({hit})" if hit else ""))
trading = pages["trading.html"]
ok(MT.RULES[KEPT]["label"] in trading, "a rule still on the board is on the trading page")
logged, opened = _board_tiles(snapshot)
ok(f'<div class="tile"><b>{logged:,}</b><span>trades logged</span></div>' in trading
   and f'<div class="tile"><b>{opened:,}</b><span>open now</span></div>' in trading,
   "the trading headline counts only the rules still on the board")

saved_rules = MT.RULES
try:
    MT.RULES = dict(saved_rules)
    MT.RULES["zz_empty_untested"] = dict(
        lane="swing", label="Empty untested lane",
        signal=lambda h: False, exit=lambda _after, _entry: None,
        note="Registered with no trades. Emptiness is not removal.",
    )
    shown = SB.trading_page(NOW)
finally:
    MT.RULES = saved_rules
ok("Empty untested lane" in shown, "a rule with no trades still renders")
ok("zz_empty_untested" in shown, "and its id is on the page")

print(f"\n{'FAILED: ' + str(len(FAILS)) if FAILS else 'trading lane removal passed'}")
for item in FAILS:
    print("   -", item)
sys.exit(1 if FAILS else 0)
