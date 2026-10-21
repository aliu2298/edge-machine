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
    return next(w for w in W.windows(now, ledger={"quotes": []}, games=[], fixtures=[]) if w["lane"] == lane and label_part in w["label"]
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
lanes_sat = {(w["lane"], w["label"]) for w in W.windows(sat, ledger={"quotes": []}, games=[], fixtures=[])
             if w["close"].date() == dt.date(2026, 10, 17) and w["lane"] != "culture"}
check("Saturday: crypto, gas/diesel (and the near-certain YES hour) and the first-to-score NO pick, "
      "no Treasury, index or commodity",
      sorted(l for l, _ in lanes_sat), ["crypto_fav_band", "econ_daily", "econ_daily", "econ_nc_yes", "ftts_no"])

print("\nthe near-certain YES lane (2026-10-20): 75-45 min before 23:59 ET, reads 10 min apart")
nc = [w for w in W.windows(at(2026, 10, 21, 2, 0), ledger={"quotes": []}, games=[], fixtures=[])
      if w["lane"] == "econ_nc_yes" and w["close"] == at(2026, 10, 21, 3, 59)]
check("one window, 02:44-03:14Z for the 03:59Z close", [(w["start"], w["end"]) for w in nc],
      [(at(2026, 10, 21, 2, 44), at(2026, 10, 21, 3, 14))])
for minute, want in ((1, [1]), (16, [2]), (25, [3]), (27, [])):
    t = at(2026, 10, 21, 2, 44) + dt.timedelta(minutes=minute)
    got = [k for w, k in W.due(t, ledger={"quotes": []}, games=[], fixtures=[]) if w["lane"] == "econ_nc_yes"]
    check(f"near-certain YES at window start + {minute} min -> reads {want}", got, want)
check("its stamp file", W.STAMP["econ_nc_yes"], "data/daily_window/request.txt")

print("\nup to three reads, 30 minutes apart, none in the last 10 minutes")
for minute, want in ((29, [1]), (35, [2]), (65, [3]), (82, []), (95, [])):
    t = at(2026, 10, 13, 17, 30) + dt.timedelta(minutes=minute - 0)
    got = sorted(k for w, k in W.due(t, ledger={"quotes": []}, games=[], fixtures=[]) if w["lane"] == "crypto_fav_band")
    check(f"crypto at window start + {minute} min -> reads {want}", got, want)
check("before the window: nothing due",
      [k for w, k in W.due(at(2026, 10, 13, 17, 29), ledger={"quotes": []}, games=[], fixtures=[]) if w["lane"] == "crypto_fav_band"], [])

print("\na later read is not asked for once every series of that close holds an entry")
coins = sorted(S.COINS)
some = {"quotes": [dict(source="crypto_fav_band", bet=True, market_id=f"{c}-26OCT1317-T1")
                   for c in coins[:2]]}
# Every coin entered in all four sibling crypto lanes (2026-10-18): only then is a later read dropped.
LANES4 = W.WINDOW_LANES["crypto_fav_band"]
allc = {"quotes": [dict(source=lane, bet=True, market_id=f"{c}-26OCT1317-T1")
                   for c in coins for lane in LANES4]}
yes_only = {"quotes": [dict(source="crypto_fav_band", bet=True, market_id=f"{c}-26OCT1317-T1")
                       for c in coins]}
t = at(2026, 10, 13, 18, 5)
check("two of five coins entered: read 2 is still due",
      [k for w, k in W.due(t, some, [], []) if w["lane"] == "crypto_fav_band"], [2])
check("all five entered: no read is asked for",
      [k for w, k in W.due(t, allc, [], []) if w["lane"] == "crypto_fav_band"], [])
check("all five entered in the Yes lane only: the No and 0.60-0.70 lanes still get read 2",
      [k for w, k in W.due(t, yes_only, [], []) if w["lane"] == "crypto_fav_band"], [2])
check("the crypto window serves four sibling lanes", len(LANES4), 4)
check("an entry on another day's close does not count",
      [k for w, k in W.due(t, {"quotes": [dict(q, market_id=q["market_id"].replace("1317", "1217"))
                                           for q in allc["quotes"]]}, [], []) if w["lane"] == "crypto_fav_band"], [2])

print("\nstamps: one file per workflow, a crypto and a commodity read in one push")
lines = W.stamp_lines(at(2026, 10, 13, 17, 35), ledger={"quotes": []}, games=[], fixtures=[])
lines.pop("data/culture_window/request.txt", None)      # the hourly culture read (2026-10-17), tested below
check("17:35Z: crypto and commodities stamps both written, and the index window's daily stamp",
      sorted(lines), ["data/commodities_window/request.txt", "data/crypto_window/request.txt",
                      "data/daily_window/request.txt"])
check("the stamp names lane, close and read", lines["data/crypto_window/request.txt"],
      "crypto_fav_band 2026-10-13T21:00:00+00:00 read 1")
lines = W.stamp_lines(at(2026, 10, 13, 16, 35), ledger={"quotes": []}, games=[], fixtures=[])
check("16:35Z: the Treasury and index reads share the daily stamp",
      lines["data/daily_window/request.txt"].count("finance_daily"), 2)


print("\nNBA rules and culture reads (2026-10-17)")
nba = [dict(start="2026-10-20T19:00Z", completed=False), dict(start="2026-10-20T23:30Z", completed=False),
       dict(start="2026-10-20T20:00Z", completed=True)]
got = lambda h, m: sorted(k for w, k in W.due(at(2026, 10, 20, h, m), {"quotes": []}, nba, []) if w["lane"] == "nba_rules")
check("a 19:00Z tip: read 1 at 17:35, read 2 at 18:05, nothing at 18:45 (20 min out) or 16:00",
      (got(17, 35), got(18, 5), got(18, 45), got(16, 0)), ([1], [2], [], []))
check("a finished game asks for nothing", [w for w in W.nba_windows(at(2026, 10, 20, 18, 30), nba) if w["close"].hour == 20], [])
cl = [k for w, k in W.due(at(2026, 10, 20, 9, 41), {"quotes": []}, [], []) if w["lane"] == "culture"]
check("culture is read once every hour", cl, [1])
st = W.stamp_lines(at(2026, 10, 20, 17, 35), {"quotes": []}, nba, [])
check("both go to their own stamp files",
      ("data/nba_window/request.txt" in st, "data/culture_window/request.txt" in st), (True, True))

print("\nsoccer label rules (2026-10-17): one window per kickoff, from the fixtures passed in")
soc = [dict(kickoff="2026-10-18T14:00Z", league="Premier League", played=False),
       dict(kickoff="2026-10-18T14:00Z", league="Bundesliga", played=False),
       dict(kickoff="2026-10-18T16:00Z", league="Liga MX", played=False),
       dict(kickoff="2026-10-18T18:00Z", league="MLS", played=True)]
sg = lambda h, m: sorted(k for w, k in W.due(at(2026, 10, 18, h, m), {"quotes": []}, [], soc) if w["lane"] == "soccer_rules")
check("two 14:00Z kickoffs share one window: read 1 at 12:35, read 2 at 13:05, nothing at 13:45",
      (sg(12, 35), sg(13, 5), sg(13, 45)), ([1], [2], []))
check("an untracked league or a played match asks for nothing", (sg(14, 35), sg(16, 35)), ([], []))
check("the soccer stamp file", W.stamp_lines(at(2026, 10, 18, 12, 35), {"quotes": []}, [], soc).get("data/soccer_rules_window/request.txt"),
      "soccer_rules 2026-10-18T14:00:00+00:00 read 1")
led = {"quotes": [dict(source="goals_market", event="KXEPLTOTAL-26OCT18BOUSUN", start="2026-10-18T14:00:00+00:00"),
                  dict(source="goals_market", event="KXLIGAMXTOTAL-26OCT18AMECRU", start="2026-10-18T16:00:00+00:00")]}
W._fixtures_cache = lambda: []          # the VPS: no fixtures cache, and never the live file here
check("without a fixtures cache (the VPS) the tracker's goals_market kickoffs stand in, tracked series only",
      [t.isoformat() for t in W.soccer_kickoffs(at(2026, 10, 18, 12, 0), None, led)], ["2026-10-18T14:00:00+00:00"])

print("\nsoccer team-scoring rules (2026-10-17): their own window and stamp, their own leagues")
tg = lambda h, m: sorted(k for w, k in W.due(at(2026, 10, 18, h, m), {"quotes": []}, [], soc) if w["lane"] == "soccer_team_rules")
check("the 14:00Z EPL/Bundesliga kickoff: read 1 at 12:35, read 2 at 13:05", (tg(12, 35), tg(13, 5), tg(13, 45)), ([1], [2], []))
check("its stamp file", W.stamp_lines(at(2026, 10, 18, 12, 35), {"quotes": []}, [], soc).get("data/soccer_team_rules_window/request.txt"),
      "soccer_team_rules 2026-10-18T14:00:00+00:00 read 1")
uel = [dict(kickoff="2026-10-23T19:00Z", league="Europa League", played=False)]
check("a Europa League kickoff opens a team-rules window",
      "soccer_team_rules" in {w["lane"] for w, _ in W.due(at(2026, 10, 23, 17, 35), {"quotes": []}, [], uel)}, True)
tled = {"quotes": [dict(source="goals_market", market_id="KXUELTEAMTOTAL-26OCT23ROMPLZ-ROM2", start="2026-10-23T19:00:00+00:00"),
                   dict(source="goals_market", market_id="KXUECLTEAMTOTAL-26OCT23AAABBB-AAA1", start="2026-10-23T17:00:00+00:00")]}
check("on the VPS the team-total quotes stand in (by market id), tracked series only",
      [t.isoformat() for t in W.soccer_kickoffs(at(2026, 10, 23, 12, 0), None, tled, W.SOCCER_TEAM_SERIES)],
      ["2026-10-23T19:00:00+00:00"])

print(f"\n{'ALL PASS' if not FAILS else str(len(FAILS)) + ' FAILED'}")
sys.exit(1 if FAILS else 0)
