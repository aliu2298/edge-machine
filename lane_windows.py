#!/usr/bin/env python3
"""lane_windows.py — every ladder lane's entry window, and which reads are due now.

Four lanes enter a Yes at 70-80c 2-3.5 hours before a contract's CLOSE, and each close
is different:

    crypto_fav_band   coin ladders          17:00 ET, every day
                      (and its siblings: _below, _60, _below_60, 2026-10-18)
    commod_fav_band   WTI                   14:30 ET, weekdays (the commodity calendar)
                      Brent, gold, silver,  17:00 ET, the commodity calendar
                      copper, natural gas
    commod_nc         the same six closes   75-45 min before the close (commod_nc_yes/_no,
                      2026-10-20), read every 10 minutes, so a 15-minute cron asks twice
    econ_daily        AAA gas               23:59 ET, every day
                      diesel                01:59 ET, every day
    finance_daily     Treasury yields       15:30 ET, weekdays
                      S&P 500 / Nasdaq-100  16:00 ET, weekdays

and the first-to-score lanes (2026-10-14), timed to the CENTRAL day and to each kickoff:

    ftts_no_*         the day's pick        09:00-10:30 CT, reads at 09:00, 09:30, 10:00
    ftts_lineup_lag   each kickoff K        K-60 to K-15 min, reads at K-60 and K-40

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
    # The near-certain commodity lanes (2026-10-20) share the commodity stamp: the tracker
    # workflow already triggers on it, and one run serves every lane whose window is open.
    "commod_nc": "data/commodities_window/request.txt",
    "econ_daily": "data/daily_window/request.txt",
    "finance_daily": "data/daily_window/request.txt",
    "ftts_no": "data/ftts_window/request.txt",
    "ftts_lineup_lag": "data/ftts_window/request.txt",
    # 2026-10-17: GitHub's cron never fired either lane on its own (culture.yml's hourly
    # schedule missed five hours in a row; the NBA rules need a read 20-90 min before each tip).
    "nba_rules": "data/nba_window/request.txt",
    "culture": "data/culture_window/request.txt",
    # 2026-10-17: the 21 soccer total-goals label rules (soccer_rules.py), 90-20 min before kickoff.
    "soccer_rules": "data/soccer_rules_window/request.txt",
    # 2026-10-17: the 8 soccer team-scoring label rules (soccer_team_rules.py), same timing.
    "soccer_team_rules": "data/soccer_team_rules_window/request.txt",
}
NBA_FROM, NBA_TO = 90, 20                # minutes before tip-off (nba_rules.WINDOW_MIN)
SOCCER_FROM, SOCCER_TO = 90, 20          # minutes before kickoff (soccer_rules.WINDOW_MIN)
# soccer_rules.SERIES: ESPN league -> Kalshi match total series. Copied, not imported, so this
# module stays light on the VPS; test_soccer_rules.py checks the two agree.
SOCCER_SERIES = {
    "Premier League": "KXEPLTOTAL", "La Liga": "KXLALIGATOTAL", "Bundesliga": "KXBUNDESLIGATOTAL",
    "Serie A": "KXSERIEATOTAL", "Ligue 1": "KXLIGUE1TOTAL", "Eredivisie": "KXEREDIVISIETOTAL",
    "Scottish Premiership": "KXSCOTTISHPREMTOTAL", "MLS": "KXMLSTOTAL",
    "Saudi Pro League": "KXSAUDIPLTOTAL", "Turkish Super Lig": "KXSUPERLIGTOTAL",
    "Champions League": "KXUCLTOTAL", "UEFA Nations League": "KXUEFANLTOTAL",
}
# soccer_rules.BTTS_SERIES (Group BTTS, 2026-10-17), copied for the same reason.
SOCCER_BTTS_SERIES = {
    "Premier League": "KXEPLBTTS", "La Liga": "KXLALIGABTTS", "Bundesliga": "KXBUNDESLIGABTTS",
    "Serie A": "KXSERIEABTTS", "Ligue 1": "KXLIGUE1BTTS", "Eredivisie": "KXEREDIVISIEBTTS",
    "Primeira Liga": "KXLIGAPORTUGALBTTS", "Scottish Premiership": "KXSCOTTISHPREMBTTS",
    "MLS": "KXMLSBTTS", "Saudi Pro League": "KXSAUDIPLBTTS", "Turkish Super Lig": "KXSUPERLIGBTTS",
    "Champions League": "KXUCLBTTS", "Europa League": "KXUELBTTS", "UEFA Nations League": "KXUEFANLBTTS",
}
# soccer_team_rules.SERIES: ESPN league -> Kalshi team-total series. Copied for the same reason;
# test_soccer_team_rules.py checks the two agree.
SOCCER_TEAM_SERIES = {
    "Premier League": "KXEPLTEAMTOTAL", "La Liga": "KXLALIGATEAMTOTAL",
    "Bundesliga": "KXBUNDESLIGATEAMTOTAL", "Serie A": "KXSERIEATEAMTOTAL",
    "Ligue 1": "KXLIGUE1TEAMTOTAL", "MLS": "KXMLSTEAMTOTAL",
    "Champions League": "KXUCLTEAMTOTAL", "Europa League": "KXUELTEAMTOTAL",
}
# sa_o15.LEAGUES (Argentina & Brasileirão over 1.5, 2026-10-18), copied for the same reason;
# test_sa_o15.py checks the two agree. The tracker logs no quotes for these series, so on the VPS
# their kickoffs come from the schedule sa_o15.py writes into its own ledger on every run.
SOCCER_SA_SERIES = {"Liga Profesional": "KXARGPREMDIVTOTAL", "Brasileirão": "KXBRASILEIROTOTAL"}
CT = ZoneInfo("America/Chicago")
FTTS_DAY = ((9, 0), (10, 30))
LINEUP_FROM, LINEUP_TO = 60, 15          # minutes before kickoff
LINEUP_EVERY = dt.timedelta(minutes=20)  # two reads fit before the last-ask cut-off
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
# The near-certain lanes' last-hour window: 75 to 45 minutes before the close. Thirty minutes
# hold three reads only 10 minutes apart, and the last is asked for 5 minutes before the end.
NC_FROM, NC_TO = S.COMMOD_NC_FROM_MIN, S.COMMOD_NC_TO_MIN
NC_EVERY = dt.timedelta(minutes=10)
NC_LAST_ASK = dt.timedelta(minutes=5)


def _window(lane, label, close, series=()):
    return dict(lane=lane, label=label, series=tuple(series), close=close,
                start=close - dt.timedelta(hours=MAX_H), end=close - dt.timedelta(hours=MIN_H))


def _load_ledger(ledger):
    if ledger is not None:
        return ledger
    try:
        with open(os.path.join(ROOT, "data", "sandbox_ledger.json")) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def ftts_kickoffs(now, ledger=None):
    """Distinct first-to-score kickoffs within the next day, from the baseline's logged legs."""
    out = set()
    for q in (_load_ledger(ledger).get("quotes") or []):
        if q.get("sport") != "soccer_ftts" or not q.get("start"):
            continue
        try:
            ko = dt.datetime.fromisoformat(str(q["start"]).replace("Z", "+00:00"))
        except ValueError:
            continue
        if now - dt.timedelta(hours=2) <= ko <= now + dt.timedelta(days=1):
            out.add(ko.astimezone(dt.timezone.utc))
    return sorted(out)


def ftts_windows(now, ledger=None):
    """The No lanes' daily pick window and one lineup window per kickoff, in UTC."""
    out = []
    local = now.astimezone(CT)
    for day in (local.date(), local.date() + dt.timedelta(days=1)):
        (h0, m0), (h1, m1) = FTTS_DAY
        start = dt.datetime(day.year, day.month, day.day, h0, m0, tzinfo=CT).astimezone(dt.timezone.utc)
        end = dt.datetime(day.year, day.month, day.day, h1, m1, tzinfo=CT).astimezone(dt.timezone.utc)
        out.append(dict(lane="ftts_no", label=f"First to score NO picks {day}", series=(),
                        close=end, start=start, end=end, every=READ_EVERY, last_ask=dt.timedelta(0),
                        day=day.isoformat()))
    for ko in ftts_kickoffs(now, ledger):
        out.append(dict(lane="ftts_lineup_lag", label=f"Lineup lag {ko:%H:%M}Z kickoff", series=(),
                        close=ko, start=ko - dt.timedelta(minutes=LINEUP_FROM),
                        end=ko - dt.timedelta(minutes=LINEUP_TO), every=LINEUP_EVERY))
    return out


def nba_tips(now, games=None):
    """Tip-offs of labelled, unplayed NBA games within the next day (data/nba_pace.json)."""
    if games is None:
        try:
            with open(os.path.join(ROOT, "data", "nba_pace.json")) as f:
                games = json.load(f).get("games") or []
        except (OSError, ValueError):
            return []
    out = set()
    for g in games:
        if g.get("completed") or g.get("skipped") or not g.get("start"):
            continue
        try:
            t = dt.datetime.fromisoformat(str(g["start"]).replace("Z", "+00:00"))
        except ValueError:
            continue
        if now - dt.timedelta(hours=2) <= t <= now + dt.timedelta(days=1):
            out.add(t.astimezone(dt.timezone.utc))
    return sorted(out)


def nba_windows(now, games=None):
    """One NBA label-rules window per tip-off: 90 to 20 minutes before, read every 30 minutes."""
    return [dict(lane="nba_rules", label=f"NBA rules {t:%H:%M}Z tip", series=(), close=t,
                 start=t - dt.timedelta(minutes=NBA_FROM), end=t - dt.timedelta(minutes=NBA_TO),
                 every=READ_EVERY) for t in nba_tips(now, games)]


def _when(v):
    try:
        t = dt.datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except ValueError:
        return None
    return t.astimezone(dt.timezone.utc) if t.tzinfo else None


def _fixtures_cache():
    try:
        with open(os.path.join(ROOT, "data", "streaks_raw.json")) as f:
            return json.load(f).get("fixtures") or []
    except (OSError, ValueError):
        return []


def soccer_kickoffs(now, fixtures=None, ledger=None, series_map=None):
    """Kickoffs within the next day of unplayed matches in the soccer rules' leagues.

    From the ESPN fixtures cache (data/streaks_raw.json) when there is one. The VPS clone has
    no cache (it is not committed), so the tracker's own goals_market quotes, which log every
    Kalshi match total and team total with ESPN's kickoff, fill in from data/sandbox_ledger.json,
    and its btts_market quotes do the same for the BTTS series (Group BTTS). Quotes are read by
    event or, when they carry none, by market id. Tests pass `fixtures` (and `ledger`) and read
    neither file. `series_map` narrows it to one lane's league -> series map (the team-scoring
    rules); without it the total-goals and BTTS maps both count."""
    if series_map is None:
        maps = {"goals_market": SOCCER_SERIES, "btts_market": SOCCER_BTTS_SERIES}
    else:
        maps = {"goals_market": series_map}
    starts = []
    if fixtures is None:
        fixtures = _fixtures_cache()
        series = {src: tuple(s + "-" for s in mp.values()) for src, mp in maps.items()}
        for q in (_load_ledger(ledger).get("quotes") or []):
            tag = str(q.get("event") or q.get("market_id") or "")
            if q.get("source") in series and tag.startswith(series[q["source"]]):
                starts.append(q.get("start"))
    for f in fixtures:
        if not f.get("played") and any(f.get("league") in mp for mp in maps.values()):
            starts.append(f.get("kickoff"))
    out = set()
    for v in starts:
        t = _when(v) if v else None
        if t and now - dt.timedelta(hours=2) <= t <= now + dt.timedelta(days=1):
            out.add(t)
    return sorted(out)


def _sa_schedule():
    try:
        with open(os.path.join(ROOT, "data", "sa_o15_ledger.json")) as f:
            return json.load(f).get("schedule") or []
    except (OSError, ValueError):
        return []


def sa_kickoffs(now, fixtures=None):
    """Kickoffs within the next day in Argentina and the Brasileirão (sa_o15, 2026-10-18).

    From the fixtures passed in (tests) or, live, the ESPN cache plus sa_o15's own schedule."""
    starts = []
    if fixtures is None:
        fixtures = _fixtures_cache()
        starts += _sa_schedule()
    starts += [f.get("kickoff") for f in fixtures if not f.get("played") and f.get("league") in SOCCER_SA_SERIES]
    out = set()
    for v in starts:
        t = _when(v) if v else None
        if t and now - dt.timedelta(hours=2) <= t <= now + dt.timedelta(days=1):
            out.add(t)
    return sorted(out)


def soccer_windows(now, fixtures=None, ledger=None):
    """One soccer label-rules window per kickoff: 90 to 20 minutes before, read every 30 minutes.

    The same stamp serves sa_o15's Argentine and Brazilian matches (soccer-rules.yml runs it)."""
    kicks = sorted(set(soccer_kickoffs(now, fixtures, ledger)) | set(sa_kickoffs(now, fixtures)))
    return [dict(lane="soccer_rules", label=f"Soccer rules {t:%H:%M}Z kickoff", series=(), close=t,
                 start=t - dt.timedelta(minutes=SOCCER_FROM), end=t - dt.timedelta(minutes=SOCCER_TO),
                 every=READ_EVERY) for t in kicks]


def soccer_team_windows(now, fixtures=None, ledger=None):
    """One team-scoring rules window per kickoff in the team rules' leagues, same timing."""
    return [dict(lane="soccer_team_rules", label=f"Team rules {t:%H:%M}Z kickoff", series=(), close=t,
                 start=t - dt.timedelta(minutes=SOCCER_FROM), end=t - dt.timedelta(minutes=SOCCER_TO),
                 every=READ_EVERY) for t in soccer_kickoffs(now, fixtures, ledger, SOCCER_TEAM_SERIES)]


def culture_windows(now):
    """The culture lanes read once an hour, every hour (culture.yml)."""
    h = now.replace(minute=0, second=0, microsecond=0)
    return [dict(lane="culture", label=f"Culture {h:%H}:00Z", series=(), close=h + dt.timedelta(hours=1),
                 start=h, end=h + dt.timedelta(hours=1), every=dt.timedelta(hours=1), last_ask=dt.timedelta(0))]


def ftts_day_full(day, ledger=None):
    """True once BOTH No lanes hold FTTS_NO_PICKS bets for that Central day."""
    n = {"ftts_no_70_80": 0, "ftts_no_60_70": 0}
    for q in (_load_ledger(ledger).get("quotes") or []):
        if q.get("source") in n and q.get("bet") and q.get("date") == day:
            n[q["source"]] += 1
    return all(v >= S.FTTS_NO_PICKS for v in n.values())


def windows(now, ledger=None, games=None, fixtures=None):
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
            out.append(dict(lane="commod_nc", label=f"Commodities last hour {h:02d}:{m:02d} ET",
                            series=tuple(series), close=close,
                            start=close - dt.timedelta(minutes=NC_FROM),
                            end=close - dt.timedelta(minutes=NC_TO),
                            every=NC_EVERY, last_ask=NC_LAST_ASK))
        for lane, label, (h, m), weekdays in DAILY_CLOSES:
            if day.weekday() not in weekdays:
                continue
            close = dt.datetime(day.year, day.month, day.day, h, m, tzinfo=ET)
            out.append(_window(lane, f"{label} {h:02d}:{m:02d} ET", close))
    out = [dict(w, close=w["close"].astimezone(dt.timezone.utc),
                start=w["start"].astimezone(dt.timezone.utc),
                end=w["end"].astimezone(dt.timezone.utc)) for w in out]
    out += ftts_windows(now, ledger)
    out += nba_windows(now, games)
    out += soccer_windows(now, fixtures, ledger)
    out += soccer_team_windows(now, fixtures, ledger)
    out += culture_windows(now)
    return sorted(out, key=lambda w: (w["start"], w["lane"]))


def _close_token(close):
    """'26OCT1317' for a 17:00 ET close on 2026-10-13: the token the ladder tickers carry."""
    et = close.astimezone(ET)
    return f"{et:%y}{et.strftime('%b').upper()}{et:%d}{et:%H}"


# The lanes one window reads for (2026-10-18). The crypto window serves four sibling lanes
# (Yes and No, 0.70-0.80 and 0.60-0.70); a later read is skipped only once a series holds an
# entry in EVERY one of them, so the Yes lane filling first never cuts off the No lanes' reads.
WINDOW_LANES = {
    "crypto_fav_band": ("crypto_fav_band", "crypto_fav_band_below", "crypto_fav_band_60",
                        "crypto_fav_band_below_60"),
    "commod_fav_band": ("commod_fav_band",),
    "commod_nc": S.COMMOD_NC_LANES,
}


def entered_series(lane, close, ledger=None):
    """Series holding an entry for this close in every lane the window serves (crypto, commodities)."""
    if lane not in WINDOW_LANES:
        return set()
    if ledger is None:
        try:
            with open(os.path.join(ROOT, "data", "sandbox_ledger.json")) as f:
                ledger = json.load(f)
        except (OSError, ValueError):
            return set()
    token = _close_token(close)
    got = {name: set() for name in WINDOW_LANES[lane]}
    for q in (ledger.get("quotes") or []) + (ledger.get("_archive") or []):
        if q.get("source") not in got or not q.get("bet"):
            continue
        parts = str(q.get("market_id") or "").split("-")
        if len(parts) >= 2 and parts[1].startswith(token[:7]):
            got[q["source"]].add(parts[0])
    return set.intersection(*got.values())


def due(now, ledger=None, games=None, fixtures=None):
    """[(window, read number)] for every read to ask for at `now`."""
    out = []
    for w in windows(now, ledger, games, fixtures):
        if not (w["start"] <= now <= w["end"] - w.get("last_ask", LAST_ASK)):
            continue
        k = int((now - w["start"]) / w.get("every", READ_EVERY))
        if k >= READS:
            continue
        if w["series"] and set(w["series"]) <= entered_series(w["lane"], w["close"], ledger):
            continue                       # every series already entered: nothing left to read for
        if w["lane"] == "ftts_no" and ftts_day_full(w["day"], ledger):
            continue                       # both No lanes already hold their five for the day
        out.append((w, k + 1))
    return out


def stamp_lines(now, ledger=None, games=None, fixtures=None):
    """{stamp file: stamp text} for the reads due now. One file can serve several windows."""
    lines = {}
    for w, k in due(now, ledger, games, fixtures):
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
