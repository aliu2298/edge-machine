#!/usr/bin/env python3
"""First team to score: the Kalshi feed, the three lanes, the daily cap, and their read windows."""
import datetime as dt
import sys
from zoneinfo import ZoneInfo

import lane_windows as W
import sandbox_sources as S
import sandbox_track as T

FAILS = []
UTC = dt.timezone.utc
CT = ZoneInfo("America/Chicago")


def check(label, got, want):
    ok = got == want
    print(f"  {'ok  ' if ok else 'FAIL'} {label}" + ("" if ok else f" (got {got!r}, want {want!r})"))
    if not ok:
        FAILS.append(label)


def close(label, got, want, tol=0.01):
    check(label, abs(got - want) <= tol, True)


print("the fair price from a match-winner row")
f = S.ftts_fair(dict(price_a=0.36, price_draw=0.28, price_b=0.36))
close("an even match: each side about equally likely to score first", f["a"], f["b"], 0.005)
close("and the three outcomes sum to one", f["a"] + f["b"] + f["none"], 1.0, 1e-6)
f = S.ftts_fair(dict(price_a=0.70, price_draw=0.18, price_b=0.12))
check("a strong favourite is the likelier first scorer", f["a"] > 0.6 > f["b"], True)
check("a placeholder price gives no fair price", S.ftts_fair(dict(price_a=1.0, price_draw=0.1, price_b=0.1)), None)


def game(code, home, away, ko, pa=0.50, pd=0.27, pb=0.27, lg="EPL"):
    return dict(market_id=f"KX{lg}GAME-{code}", venue="kalshi", label=f"{home} vs {away}",
                side_a=home, side_b=away, price_a=pa, price_draw=pd, price_b=pb, start=ko.isoformat(),
                tickers={"a": f"KX{lg}GAME-{code}-{home[:3].upper()}", "b": f"KX{lg}GAME-{code}-{away[:3].upper()}",
                         "draw": f"KX{lg}GAME-{code}-TIE"}, league="Premier League")


def legs(code, home, away, ya_h, ya_a, lg="EPL", spread=0.01):
    ev = f"KX{lg}FTTS-{code}"
    out = []
    for leg, ya in ((home[:3].upper(), ya_h), (away[:3].upper(), ya_a), ("NONE", 0.06)):
        out.append(dict(ticker=f"{ev}-{leg}", event_ticker=ev, yes_ask_dollars=str(ya),
                        yes_bid_dollars=str(round(ya - spread, 2)),
                        no_ask_dollars=str(round(1 - ya + spread, 2)), no_bid_dollars=str(round(1 - ya, 2))))
    return out


NOW = dt.datetime(2026, 10, 17, 14, 30, tzinfo=CT).astimezone(UTC)      # Saturday 09:30 CT
KO1 = NOW + dt.timedelta(minutes=40)
KO2 = NOW + dt.timedelta(hours=5)
uni = {"soccer": [game("26OCT17ARSCHE", "Arsenal", "Chelsea", KO1, 0.55, 0.25, 0.22),
                  game("26OCT17LIVEVE", "Liverpool", "Everton", KO2, 0.62, 0.22, 0.18),
                  game("26OCT17NOFTTS", "Brighton", "Fulham", KO2)]}
book = {"KXEPLFTTS": legs("26OCT17ARSCHE", "Arsenal", "Chelsea", 0.50, 0.40)
                     + legs("26OCT17LIVEVE", "Liverpool", "Everton", 0.62, 0.30)}
_open0 = S._kalshi_open
S._kalshi_open = lambda series: book.get(series, [])
try:
    rows = S.fetch_kalshi_ftts(uni, stats={})
finally:
    S._kalshi_open = _open0
print("\nthe feed: Kalshi FTTS legs joined to the match-winner rows")
check("two team legs per joined fixture, No Goal never a row, an unlisted fixture skipped",
      sorted(r["market_id"].split("-", 1)[1] for r in rows),
      ["26OCT17ARSCHE-ARS", "26OCT17ARSCHE-CHE", "26OCT17LIVEVE-EVE", "26OCT17LIVEVE-LIV"])
ars = next(r for r in rows if r["market_id"].endswith("-ARS"))
check("a leg carries its fixture's kickoff, its Central date and the event", (ars["start"], ars["date"], ars["event"]),
      (KO1.isoformat(), "2026-10-17", "KXEPLFTTS-26OCT17ARSCHE"))
close("and the fair price for ITS side", ars["fair_yes"], S.ftts_fair(uni["soccer"][0])["a"], 1e-3)
check("YES and NO are both priced from the venue's asks", (ars["price_a"], ars["price_b"]), (0.5, 0.51))
fu = {"soccer_ftts": rows}

print("\nlineup lag: YES 15-60 min out where the fit beats ask + fee by 3c")
fit = {r["market_id"]: r["fair_yes"] for r in rows}
cheap = [dict(r, price_a=round(r["fair_yes"] - 0.06, 2)) for r in rows]
lag = S.fetch_ftts_lineup_lag("soccer_ftts", {"soccer_ftts": cheap}, NOW)
check("only the fixture 40 minutes out, one leg for it", [p["market_id"].split("-", 1)[1][:13] for p in lag], ["26OCT17ARSCHE"])
check("backed on YES", lag[0]["pick"], "a")
at_fit = [dict(r, price_a=round(r["fair_yes"], 2)) for r in rows]
check("nothing when the asks are at the fit", S.fetch_ftts_lineup_lag("soccer_ftts", {"soccer_ftts": at_fit}, NOW), [])
just = [dict(r, price_a=round(r["fair_yes"] - S._ftts_fee(r["fair_yes"]) - 0.02, 2)) for r in rows]
check("nor at a 2c edge: the bar is 3c after the fee",
      S.fetch_ftts_lineup_lag("soccer_ftts", {"soccer_ftts": just}, NOW), [])
check("nothing 10 minutes before kickoff", S.fetch_ftts_lineup_lag("soccer_ftts", {"soccer_ftts": cheap}, KO1 - dt.timedelta(minutes=10)), [])
check("nothing 90 minutes out",
      S.fetch_ftts_lineup_lag("soccer_ftts", {"soccer_ftts": cheap}, KO1 - dt.timedelta(minutes=90)), [])

print("\nthe NO lanes: band, the 09:00 CT start, the hour of lead, one per match, the best five")


def no_row(i, no, edge, mins=180, day="2026-10-17", ev=None):
    p = round(no, 2)
    fair_no = p + S._ftts_fee(p) + edge
    return dict(market_id=f"KXEPLFTTS-26OCT17M{i:02d}-T{i % 2}", event=ev or f"KXEPLFTTS-26OCT17M{i:02d}",
                price_a=round(1 - p + 0.01, 2), price_b=p, fair_yes=round(1 - fair_no, 4),
                start=(NOW + dt.timedelta(minutes=mins)).isoformat(), date=day,
                tradeable={"a": True, "b": True})


band = [no_row(i, 0.72 + i * 0.005, 0.01 * i) for i in range(8)]
picks = S.fetch_ftts_no_70_80("soccer_ftts", {"soccer_ftts": band}, NOW)
check("the five largest fit edges, best first", [p["market_id"][-6:-3] for p in picks], ["M07", "M06", "M05", "M04", "M03"])
check("all on NO", {p["pick"] for p in picks}, {"b"})
check("nothing before 09:00 Central",
      S.fetch_ftts_no_70_80("soccer_ftts", {"soccer_ftts": band}, NOW.replace(hour=13)), [])
edge_rows = [no_row(1, 0.70, 0.02), no_row(2, 0.6999, 0.02), no_row(3, 0.80, 0.02), no_row(4, 0.81, 0.02), no_row(5, 0.60, 0.02)]
check("0.70-0.80 takes 0.70 and 0.80, not 0.81",
      sorted(p["market_id"][-6:-3] for p in S.fetch_ftts_no_70_80("soccer_ftts", {"soccer_ftts": edge_rows}, NOW)),
      ["M01", "M02", "M03"])
check("0.60-0.70 takes 0.60, and NOT 0.70, which belongs to the upper band",
      sorted(p["market_id"][-6:-3] for p in S.fetch_ftts_no_60_70("soccer_ftts", {"soccer_ftts": [no_row(1, 0.70, 0.02), no_row(5, 0.60, 0.02)]}, NOW)),
      ["M05"])
check("a fixture under an hour away is skipped",
      S.fetch_ftts_no_70_80("soccer_ftts", {"soccer_ftts": [no_row(1, 0.75, 0.05, mins=45)]}, NOW), [])
check("another Central day's fixture is skipped",
      S.fetch_ftts_no_70_80("soccer_ftts", {"soccer_ftts": [no_row(1, 0.75, 0.05, day="2026-10-18")]}, NOW), [])
two = [no_row(1, 0.75, 0.02, ev="KXEPLFTTS-26OCT17SAME"), no_row(2, 0.74, 0.04, ev="KXEPLFTTS-26OCT17SAME")]
check("one leg per match: the larger edge", [p["market_id"][-6:-3] for p in S.fetch_ftts_no_70_80("soccer_ftts", {"soccer_ftts": two}, NOW)], ["M02"])

print("\npublish: the daily cap of five and one leg per match, across runs")


def urow(i, day="2026-10-17", ev=None):
    r = no_row(i, 0.75, 0.01 * (10 - i), day=day, ev=ev)
    return dict(r, sport="soccer_ftts", venue="kalshi_binary", label=f"M{i}", side_a="Yes", side_b="No",
                price_draw=None, untraded=False, url="u", volume=0.0)


urows = [urow(i) for i in range(7)] + [urow(9, ev="KXEPLFTTS-26OCT17M00")]
_ch = S.CHALLENGERS
_started = T._started
S.CHALLENGERS = {"ftts_no_70_80": lambda sp: [dict(market_id=r["market_id"], pick="b") for r in urows]}
T._started = lambda r, now: False
try:
    led = {"quotes": [], "meta": {}, "coverage": {}}
    T.publish(led, {"soccer_ftts": urows}, {}, verbose=False)
    first = [q["market_id"][-6:-3] for q in led["quotes"] if q["source"] == "ftts_no_70_80" and q["bet"]]
    T.publish(led, {"soccer_ftts": urows}, {}, verbose=False)
    again = [q["market_id"][-6:-3] for q in led["quotes"] if q["source"] == "ftts_no_70_80" and q["bet"]]
finally:
    S.CHALLENGERS, T._started = _ch, _started
check("five bets on the day, in the rule's order", first, ["M00", "M01", "M02", "M03", "M04"])
check("a later run adds none once five are logged", again, first)
check("the second leg of a match already bet is never logged",
      any(q["market_id"].endswith("M09-T1") for q in led["quotes"]), False)

print("\nread windows")
d0 = dt.date(2026, 10, 17)
for h, m, want in ((8, 55, []), (9, 5, [1]), (9, 35, [2]), (10, 5, [3]), (10, 35, [])):
    t = dt.datetime(2026, 10, 17, h, m, tzinfo=CT).astimezone(UTC)
    got = [k for w, k in W.due(t, ledger={"quotes": []}) if w["lane"] == "ftts_no" and w["day"] == "2026-10-17"]
    check(f"NO-lane reads at {h:02d}:{m:02d} CT -> {want}", got, want)
full = {"quotes": [dict(source=s, bet=True, date="2026-10-17") for s in ("ftts_no_70_80", "ftts_no_60_70") for _ in range(5)]}
check("no read once both NO lanes hold five that day",
      [k for w, k in W.due(dt.datetime(2026, 10, 17, 9, 35, tzinfo=CT).astimezone(UTC), ledger=full) if w["lane"] == "ftts_no"], [])
ko = dt.datetime(2026, 10, 17, 19, 0, tzinfo=UTC)
led2 = {"quotes": [dict(sport="soccer_ftts", start=ko.isoformat(), source="ftts_market")]}
for mins, want in ((65, []), (58, [1]), (45, [1]), (35, [2]), (22, []), (10, [])):
    t = ko - dt.timedelta(minutes=mins)
    got = [k for w, k in W.due(t, ledger=led2) if w["lane"] == "ftts_lineup_lag"]
    check(f"lineup reads {mins} min before kickoff -> {want}", got, want)
lines = W.stamp_lines(ko - dt.timedelta(minutes=55), ledger=led2)
check("the lineup read goes to the first-to-score stamp", "data/ftts_window/request.txt" in lines, True)

print(f"\n{'ALL PASS' if not FAILS else str(len(FAILS)) + ' FAILED'}")
sys.exit(1 if FAILS else 0)
