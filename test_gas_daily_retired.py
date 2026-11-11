#!/usr/bin/env python3
"""Gas daily cheap NO retired (Olu, 2026-11-11); sells on the gas lanes count only on prints 60s+ after the entry."""
import datetime as dt
import html
import sys

import commodities_build as CB
import mentions_split as MS

UTC = dt.timezone.utc
FAILS = []


def check(why, got, want):
    good = got == want
    print(f"  {'ok  ' if good else 'FAIL'} {why}" + ("" if good else f" — got {got!r}, want {want!r}"))
    if not good:
        FAILS.append(why)


print("the retirement")
check("gas daily retired 2026-11-11 (Eastern), the weekly lane NOT (no inherited key)",
      (MS.GAS["retired"]["on"], MS.retired(MS.GAS, dt.datetime(2026, 11, 11, 4, tzinfo=UTC)),
       MS.retired(MS.GAS, dt.datetime(2026, 11, 11, 5, tzinfo=UTC)), "retired" in MS.GAS_WEEK,
       MS.retired(MS.GAS_WEEK, dt.datetime(2026, 12, 1, tzinfo=UTC))), ("2026-11-11", False, True, False, False))
check("live and retired commodity lanes", ([c["lane"] for c in MS.LIVE_COMMOD], [c["lane"] for c in MS.GONE_COMMOD]),
      (["gas_week_cheap_no"], ["wti_cheap_yes", "gas_cheap_no"]))
check("the reason and the flagged page figure", (MS.GAS["retired"]["reason"].startswith("No edge held or swung: 19 bets, hold −9%"),
      "+4.2%" in MS.GAS["retired"]["note"], "Nov 8 and Nov 11" in MS.GAS["retired"]["note"]), (True, True, True))
check("both gas lanes count sells only on prints 60s or more after the entry",
      (MS.GAS["fill_gap_s"], MS.GAS_WEEK["fill_gap_s"], MS.WTI.get("fill_gap_s")), (60, 60, None))

print("\nthe 60-second fill rule")
H = int(dt.datetime(2026, 11, 11, 14, tzinfo=UTC).timestamp())          # the hour 13:00-14:00 ends here
entry = H - 3600 + 3 * 60                                                  # entry at 13:03
no_low = lambda end, yes_low: dict(end_period_ts=end, price=dict(low_dollars=yes_low))   # NO high = 1 - YES low
hourly = [no_low(H, 0.40), no_low(H + 3600, 0.90), no_low(H + 7200, 0.60)]                # NO highs 0.60, 0.10, 0.40
early = lambda lo, hi: [no_low(H - 3600 + 2 * 60, 0.40), no_low(H - 3600 + 4 * 60, 0.95)]  # 13:02 print, 13:04 nothing
late = lambda lo, hi: [no_low(H - 3600 + 2 * 60, 0.40), no_low(H - 3600 + 15 * 60, 0.40)]  # and a 13:15 print
check("a print one minute BEFORE the entry is not a fill; the next print that gets there is (16:00)",
      MS.fill_late(hourly, entry, 0.34, "no", early), (H + 7200, 0.34))
check("a print 12 minutes after the entry is", MS.fill_late(hourly, entry, 0.34, "no", late), (H - 3600 + 15 * 60, 0.34))
check("a print inside the first 60 seconds is not", MS.fill_late(
      hourly, entry, 0.34, "no", lambda lo, hi: [no_low(entry + 60, 0.40)]), (H + 7200, 0.34))
check("the old rule (whole entry hour) would have filled at 14:00", MS.fill_of(hourly, entry, 0.34, "no"), (H, 0.34))

print("\nre-reading recorded fills (once)")
calls = []


def fetch(url):
    calls.append(url)
    mins = "period_interval=1" in url
    cs = early(0, 0) if mins else hourly
    return dict(market_tickers=["M"], market_candlesticks=[cs])


e = dict(id="M", event="EV", side="no", entry_at=MS._iso(entry), price=0.17, payout=1.0, settled=MS._iso(H + 9000),
         legs=[dict(multiple=2.0, share=0.5, target=0.34, filled_at=MS._iso(H), fill_px=0.34),
               dict(multiple=3.0, share=0.5, target=0.51, filled_at=MS._iso(H), fill_px=0.51)])
st = dict(entries=[e])
cfg = dict(MS.GAS_WEEK)
n = MS.recheck_fills(st, cfg, fetch, H + 20000)
check("both legs re-read: 2x moves to 16:00, 3x (never traded there again) is held to settlement",
      (n, e["legs"][0]["filled_at"], e["legs"][1].get("filled_at"), e["legs"][1]["settled_px"]),
      (2, MS._iso(H + 7200), None, 1.0))
k = len(calls)
check("checked once: a second pass fetches nothing", (MS.recheck_fills(st, cfg, fetch, H + 20000), len(calls) - k), (0, 0))

print("\nthe Commodities page")
ch = html.unescape(CB.build())
j = ch.find('<section id="retired"')
check("gas daily's card and its note in the Retired fold; weekly above it",
      (j > 0, 'id="gas-cheap-no"' in ch[j:], 'id="gas-week-cheap-no"' in ch[:j], "split −20.5%" in ch[j:],
       "at least 60 seconds after the entry" in ch[j:]), (True, True, True, True, True))

print(f"\n{'ALL PASS' if not FAILS else str(len(FAILS)) + ' FAILED'}")
sys.exit(1 if FAILS else 0)
