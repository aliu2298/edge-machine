#!/usr/bin/env python3
"""The Trading page describes the rules it still shows.

Both crypto lanes are off the board. The lede and the meta description no
longer say the page is testing crypto rules. No live counts, no network,
and nothing is written.
"""
import datetime
import sys

import sandbox_build as SB

FAILS = []
NOW = datetime.datetime(2026, 10, 4, 12, tzinfo=datetime.timezone.utc)
OLD = "Stock and crypto rules under test"
LEDE = "Stock and ETF rules under test, judged per entry day. Paper only."
META = "Stock and ETF rules under test, judged per entry day at real prices."


def ok(cond, why):
    print(f"  {'ok  ' if cond else 'FAIL'} {why}")
    if not cond:
        FAILS.append(why)


def main():
    print("\nthe trading lede and meta match the rules still on the page")
    html = SB.trading_page(NOW)
    ok(OLD not in html, "the old stock-and-crypto sentence is gone from the page and the meta")
    ok(f'<p class="lede">{LEDE}</p>' in html, "the lede names stock and ETF rules")
    ok(f'<meta name="description" content="{META}">' in html,
       "the meta description names stock and ETF rules")
    print(f"\n{'FAILED: ' + str(len(FAILS)) if FAILS else 'trading lede passed'}")
    for item in FAILS:
        print("  -", item)
    return 1 if FAILS else 0


if __name__ == "__main__":
    raise SystemExit(main())
