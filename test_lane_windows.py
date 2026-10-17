#!/usr/bin/env python3
"""lane_windows: every ladder lane's window, measured to its own close, and the reads due."""
import datetime as dt
import sys

import lane_windows as W
import sandbox_sources as S

FAILS = []
UTC = dt.timezone.utc


def check(label, got, want):
    ok = got == want
    print(f"  {'ok  ' if ok else 'FAIL'} {label}" + ("" if ok else f" (got {got!r}, want {want!r})"))
    if not ok:
        FAILS.append(label)


def at(y, mo, d, h, mi):
    return dt.datetime(y, mo, d, h, mi, tzinfo=UTC)


def win(now, lane, label_part):
    """The next window of that lane whose close is still ahead of `now`."""
    return next(w for w in W.windows(now, ledger={"quotes": []}) if w["lane"] == lane and label_part in w["label"]
                and w["close"] > now)


print("each window is 2-3.5h before ITS OWN close (Tuesday 2026-10-13, daylight time)")
now = at(2026, 10, 13, 12, 0)
for lane, part, start, end in (
        ("crypto_fav_band", "Crypto", at(2026, 10, 13, 17, 30), at(2026, 10, 13, 19, 0)),
        ("commod_fav_band", "14:30", at(2026, 10, 13, 15, 0), at(2026, 10, 13, 16, 30)),
        ("commod_fav_band", "17:00", at(2026, 10, 13, 17, 30), at(2026, 10, 13, 19, 0)),
        ("finance_daily", "Treasury", at(2026, 10, 13, 16, 0), at(2026, 10, 13, 17, 30)),
        ("finance_daily", "S&P", at(2026, 10, 13, 16, 30), at(2026, 10, 13, 18, 0)),
        ("econ_daily", "AAA gas", at(2026, 10, 14, 0, 29), at(2026, 10, 14, 1, 59)),
        ("econ_daily", "Diesel", at(2026, 10, 14, 2, 29), at(2026, 10, 14, 3, 59))):
    w = win(now, lane, part)
    check(f"{w['label']}: {start:%H:%M}-{end:%H:%M}Z", (w["start"], w["end"]), (start, end))

print("\nthe crypto window is measured to the 21:00Z CLOSE, not the 21:05Z expiry")
row = dict(start="2026-10-13T21:05:00+00:00", market=dict(close_time="2026-10-13T21:00:00Z"))
check("_ladder_close reads close_time", S._ladder_close(row), at(2026, 10, 13, 21, 0))
check("and falls back to start without a market payload",
      S._ladder_close(dict(start="2026-10-13T21:05:00+00:00")), at(2026, 10, 13, 21, 5))

print("\nthe clock change moves every window with its exchange (2026-11-02, standard time)")
w = win(at(2026, 11, 2, 12, 0), "crypto_fav_band", "Crypto")
check("crypto: 18:30-20:00Z after the change", (w["start"], w["end"]),
      (at(2026, 11, 2, 18, 30), at(2026, 11, 2, 20, 0)))

print("\nweekday and calendar rules")
sat = at(2026, 10, 17, 12, 0)
# An empty ledger: the lineup windows come from the real ledger's kickoffs, which this test must
# not depend on (it read real Oct 17 fixtures once they were logged).
lanes_sat = {(w["lane"], w["label"]) for w in W.windows(sat, ledger={"quotes": []}, games=[])
             if w["close"].date() == dt.date(2026, 10, 17) and w["lane"] != "culture"}
check("Saturday: crypto, gas/diesel and the first-to-score NO pick, no Treasury, index or commodity",
      sorted(l for l, _ in lanes_sat), ["crypto_fav_band", "econ_daily", "econ_daily", "ftts_no"])

print("\nup to three reads, 30 minutes apart, none in the last 10 minutes")
for minute, want in ((29, [1]), (35, [2]), (65, [3]), (82, []), (95, [])):
    t = at(2026, 10, 13, 17, 30) + dt.timedelta(minutes=minute - 0)
    got = sorted(k for w, k in W.due(t, ledger={"quotes": []}) if w["lane"] == "crypto_fav_band")
    check(f"crypto at window start + {minute} min -> reads {want}", got, want)
check("before the window: nothing due",
      [k for w, k in W.due(at(2026, 10, 13, 17, 29), ledger={"quotes": []}) if w["lane"] == "crypto_fav_band"], [])

print("\na later read is not asked for once every series of that close holds an entry")
coins = sorted(S.COINS)
some = {"quotes": [dict(source="crypto_fav_band", bet=True, market_id=f"{c}-26OCT1317-T1")
                   for c in coins[:2]]}
allc = {"quotes": [dict(source="crypto_fav_band", bet=True, market_id=f"{c}-26OCT1317-T1")
                   for c in coins]}
t = at(2026, 10, 13, 18, 5)
check("two of five coins entered: read 2 is still due",
      [k for w, k in W.due(t, some) if w["lane"] == "crypto_fav_band"], [2])
check("all five entered: no read is asked for",
      [k for w, k in W.due(t, allc) if w["lane"] == "crypto_fav_band"], [])
check("an entry on another day's close does not count",
      [k for w, k in W.due(t, {"quotes": [dict(q, market_id=q["market_id"].replace("1317", "1217"))
                                           for q in allc["quotes"]]}) if w["lane"] == "crypto_fav_band"], [2])

print("\nstamps: one file per workflow, a crypto and a commodity read in one push")
lines = W.stamp_lines(at(2026, 10, 13, 17, 35), ledger={"quotes": []}, games=[])
lines.pop("data/culture_window/request.txt", None)      # the hourly culture read (2026-10-17), tested below
check("17:35Z: crypto and commodities stamps both written, and the index window's daily stamp",
      sorted(lines), ["data/commodities_window/request.txt", "data/crypto_window/request.txt",
                      "data/daily_window/request.txt"])
check("the stamp names lane, close and read", lines["data/crypto_window/request.txt"],
      "crypto_fav_band 2026-10-13T21:00:00+00:00 read 1")
lines = W.stamp_lines(at(2026, 10, 13, 16, 35), ledger={"quotes": []})
check("16:35Z: the Treasury and index reads share the daily stamp",
      lines["data/daily_window/request.txt"].count("finance_daily"), 2)


print("\nNBA rules and culture reads (2026-10-17)")
nba = [dict(start="2026-10-20T19:00Z", completed=False), dict(start="2026-10-20T23:30Z", completed=False),
       dict(start="2026-10-20T20:00Z", completed=True)]
got = lambda h, m: sorted(k for w, k in W.due(at(2026, 10, 20, h, m), {"quotes": []}, nba) if w["lane"] == "nba_rules")
check("a 19:00Z tip: read 1 at 17:35, read 2 at 18:05, nothing at 18:45 (20 min out) or 16:00",
      (got(17, 35), got(18, 5), got(18, 45), got(16, 0)), ([1], [2], [], []))
check("a finished game asks for nothing", [w for w in W.nba_windows(at(2026, 10, 20, 18, 30), nba) if w["close"].hour == 20], [])
cl = [k for w, k in W.due(at(2026, 10, 20, 9, 41), {"quotes": []}, []) if w["lane"] == "culture"]
check("culture is read once every hour", cl, [1])
st = W.stamp_lines(at(2026, 10, 20, 17, 35), {"quotes": []}, nba)
check("both go to their own stamp files",
      ("data/nba_window/request.txt" in st, "data/culture_window/request.txt" in st), (True, True))

print(f"\n{'ALL PASS' if not FAILS else str(len(FAILS)) + ' FAILED'}")
sys.exit(1 if FAILS else 0)
