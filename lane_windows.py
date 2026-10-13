#!/usr/bin/env python3
"""lane_windows.py — every ladder lane's entry window, and which reads are due now.

Four lanes enter a Yes at 70-80c 2-3.5 hours before a contract's CLOSE, and each close
is different:

    crypto_fav_band   coin ladders          17:00 ET, every day
    commod_fav_band   WTI                   14:30 ET, weekdays (the commodity calendar)
                      Brent, gold, silver,  17:00 ET, the commodity calendar
                      copper, natural gas
    econ_daily        AAA gas               23:59 ET, every day
                      diesel                01:59 ET, every day
    finance_daily     Treasury yields       15:30 ET, weekdays
                      S&P 500 / Nasdaq-100  16:00 ET, weekdays

GitHub's cron cannot hold a 90-minute window, so the VPS asks for each read by pushing one
line to a stamp file (scripts/vps_window_requests.sh). This module is the one place that
says when those reads are, computed from each lane's own constants so a schedule can
never drift from the rule it serves.

MULTIPLE READS, ONLY WHILE SOMETHING IS STILL UNSELECTED (asked for by Olu, 2026-10-13).
A window gets up to READS reads, READ_EVERY apart. A later read is not asked for once every
series of that close already holds an entry. Each lane's own dedupe still decides what a
read may add: one entry per series per close (crypto, commodities) or per event (the
Daily lanes), so a later read only ever fills a series that had nothing. The rule itself
is unchanged; a read is a time to look, not a new selection.

Usage:
  python3 lane_windows.py            # the windows around now, and the reads due
  python3 lane_windows.py --due      # one "<stamp file>\\t<stamp>" line per read due now
"""
import datetime as dt
import json
import os
import sys
from zoneinfo import ZoneInfo

import sandbox_sources as S

ROOT = os.path.dirname(os.path.abspath(__file__))
ET = ZoneInfo("America/New_York")
READS = 3
READ_EVERY = dt.timedelta(minutes=30)
# A read asked for later than this before the window ends could land after it: a tracker
# run takes a few minutes from the push to the scan.
LAST_ASK = dt.timedelta(minutes=10)
MIN_H, MAX_H = 2.0, 3.5

STAMP = {
    "crypto_fav_band": "data/crypto_window/request.txt",
    "commod_fav_band": "data/commodities_window/request.txt",
    "econ_daily": "data/daily_window/request.txt",
    "finance_daily": "data/daily_window/request.txt",
}
EVERY_DAY = tuple(range(7))
WEEKDAYS = (0, 1, 2, 3, 4)
# The Daily lanes' supported closes, the clocks daily_track.window_reason verifies.
DAILY_CLOSES = (
    ("econ_daily", "AAA gas", (23, 59), EVERY_DAY),
    ("econ_daily", "Diesel", (1, 59), EVERY_DAY),
    ("finance_daily", "Treasury yields", (15, 30), WEEKDAYS),
    ("finance_daily", "S&P 500 / Nasdaq-100", (16, 0), WEEKDAYS),
)
assert (S.CRYPTO_FAV_MIN_H, S.CRYPTO_FAV_MAX_H) == (MIN_H, MAX_H)
assert (S.COMMOD_FAV_MIN_H, S.COMMOD_FAV_MAX_H) == (MIN_H, MAX_H)


def _window(lane, label, close, series=()):
    return dict(lane=lane, label=label, series=tuple(series), close=close,
                start=close - dt.timedelta(hours=MAX_H), end=close - dt.timedelta(hours=MIN_H))


def windows(now):
    """Every lane's windows whose close is within a day of `now`, soonest start first. UTC."""
    if now.tzinfo is None:
        now = now.replace(tzinfo=dt.timezone.utc)
    et = now.astimezone(ET)
    out = []
    for day in (et.date() - dt.timedelta(days=1), et.date(), et.date() + dt.timedelta(days=1)):
        close = dt.datetime(day.year, day.month, day.day, S.CRYPTO_FAV_CLOSE_ET, 0, tzinfo=ET)
        out.append(_window("crypto_fav_band", "Crypto 17:00 ET", close, S.COINS))
        groups = {}
        for series in S.COMMOD_FAV_SERIES:
            groups.setdefault(S.commod_fav_close_et(series), []).append(series)
        for (h, m), series in sorted(groups.items()):
            if not S.commod_fav_trading_day(day, series[0]):
                continue
            close = dt.datetime(day.year, day.month, day.day, h, m, tzinfo=ET)
            out.append(_window("commod_fav_band", f"Commodities {h:02d}:{m:02d} ET", close, series))
        for lane, label, (h, m), weekdays in DAILY_CLOSES:
            if day.weekday() not in weekdays:
                continue
            close = dt.datetime(day.year, day.month, day.day, h, m, tzinfo=ET)
            out.append(_window(lane, f"{label} {h:02d}:{m:02d} ET", close))
    out = [dict(w, close=w["close"].astimezone(dt.timezone.utc),
                start=w["start"].astimezone(dt.timezone.utc),
                end=w["end"].astimezone(dt.timezone.utc)) for w in out]
    return sorted(out, key=lambda w: (w["start"], w["lane"]))


def _close_token(close):
    """'26OCT1317' for a 17:00 ET close on 2026-10-13: the token the ladder tickers carry."""
    et = close.astimezone(ET)
    return f"{et:%y}{et.strftime('%b').upper()}{et:%d}{et:%H}"


def entered_series(lane, close, ledger=None):
    """Series of this lane already holding an entry for this close (crypto, commodities)."""
    if lane not in ("crypto_fav_band", "commod_fav_band"):
        return set()
    if ledger is None:
        try:
            with open(os.path.join(ROOT, "data", "sandbox_ledger.json")) as f:
                ledger = json.load(f)
        except (OSError, ValueError):
            return set()
    token = _close_token(close)
    got = set()
    for q in (ledger.get("quotes") or []) + (ledger.get("_archive") or []):
        if q.get("source") != lane or not q.get("bet"):
            continue
        parts = str(q.get("market_id") or "").split("-")
        if len(parts) >= 2 and parts[1].startswith(token[:7]):
            got.add(parts[0])
    return got


def due(now, ledger=None):
    """[(window, read number)] for every read to ask for at `now`."""
    out = []
    for w in windows(now):
        if not (w["start"] <= now <= w["end"] - LAST_ASK):
            continue
        k = int((now - w["start"]) / READ_EVERY)
        if k >= READS:
            continue
        if w["series"] and set(w["series"]) <= entered_series(w["lane"], w["close"], ledger):
            continue                       # every series already entered: nothing left to read for
        out.append((w, k + 1))
    return out


def stamp_lines(now, ledger=None):
    """{stamp file: stamp text} for the reads due now. One file can serve several windows."""
    lines = {}
    for w, k in due(now, ledger):
        text = f"{w['lane']} {w['close'].isoformat()} read {k}"
        path = STAMP[w["lane"]]
        lines[path] = "\n".join(sorted(set((lines.get(path) or "").splitlines()) | {text})).strip()
    return lines


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    now = dt.datetime.now(dt.timezone.utc)
    if "--due" in argv:
        for path, text in sorted(stamp_lines(now).items()):
            print(f"{path}\t{text.replace(chr(10), ' | ')}")
        return 0
    for w in windows(now):
        if w["end"] < now - dt.timedelta(hours=6):
            continue
        print(f"{w['lane']:16} {w['label']:32} window {w['start'].astimezone(ET):%a %H:%M}-"
              f"{w['end'].astimezone(ET):%H:%M} ET  close {w['close'].astimezone(ET):%H:%M} ET")
    print("due now:", [f"{w['lane']} read {k}" for w, k in due(now)] or "none")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
