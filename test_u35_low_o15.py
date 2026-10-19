#!/usr/bin/env python3
"""Offline checks for u35_low_o15 (2026-10-18): u35_low_scoring's matches, backed over 1.5, clubs only."""
import sys
from datetime import datetime, timedelta, timezone

import sandbox_audit
import sandbox_sources as S
import sandbox_track as T

FAILS = []


def check(label, got, want):
    ok = got == want
    print(f"  {'ok  ' if ok else 'FAIL'} {label}" + ("" if ok else f" (got {got!r}, want {want!r})"))
    if not ok:
        FAILS.append(label)


KO = datetime(2026, 10, 25, 13, 0, tzinfo=timezone.utc)


def played(home, away, hg, ag, days, league="La Liga"):
    return dict(home=home, away=away, home_goals=hg, away_goals=ag, played=True, competitive=True,
                kickoff=(KO - timedelta(days=days)).strftime("%Y-%m-%dT%H:%MZ"), league=league)


# Tight and Blunt score 0-1 in every one of their last 10 league games; Loose scores 3.
fx = []
for i in range(10):
    fx.append(played("Tight FC", f"T{i}", 1, 0, i + 1))
    fx.append(played("Blunt FC", f"B{i}", 0, 0, i + 1))
    fx.append(played("Loose FC", f"L{i}", 3, 3, i + 1))
    fx.append(played("Tight FC", f"C{i}", 4, 0, i + 1, league="Copa del Rey"))   # another competition


def row(mid, home, away, ask=0.70, bid=0.68, sport="soccer_o15", league="La Liga", tradeable=True):
    return dict(market_id=mid, sport=sport, start=KO.isoformat(), date=KO.strftime("%Y-%m-%d"), league=league,
                espn_home=home, espn_away=away, price_a=ask, price_b=round(1 - bid, 2), mid_a=round((ask + bid) / 2, 4),
                tradeable={"a": tradeable, "b": tradeable}, side_a="Yes", side_b="No")


print("the trigger is u35_low_scoring's own, on the same matches")
uni = {"soccer_u35": [row("KXLALIGATOTAL-26OCT25TIGBLU-4", "Tight FC", "Blunt FC", sport="soccer_u35"),
                      row("KXLALIGATOTAL-26OCT25TIGLOO-4", "Tight FC", "Loose FC", sport="soccer_u35")],
       "soccer_o15": [row("KXLALIGATOTAL-26OCT25TIGBLU-2", "Tight FC", "Blunt FC"),
                      row("KXLALIGATOTAL-26OCT25TIGLOO-2", "Tight FC", "Loose FC")]}
u35 = S.fetch_u35_low_scoring("soccer_u35", universe=uni, fixtures=fx)
o15 = S.fetch_u35_low_o15("soccer_o15", universe=uni, fixtures=fx)
check("u35_low_scoring backs the under on Tight v Blunt only", u35, [dict(market_id="KXLALIGATOTAL-26OCT25TIGBLU-4", pick="b")])
check("u35_low_o15 backs the OVER 1.5 (Yes) on the same match only", o15, [dict(market_id="KXLALIGATOTAL-26OCT25TIGBLU-2", pick="a")])
check("one predicate decides both", [S.u35_low_selected(r, KO, fx) for r in uni["soccer_o15"]], [True, False])
check("form is this competition's: the Copa del Rey 4-0s do not make Tight FC high-scoring",
      S.u35_low_selected(uni["soccer_o15"][0], KO, fx), True)
check("a game after kickoff is never read", S.u35_low_selected(
    uni["soccer_o15"][0], KO, fx + [played("Tight FC", f"F{i}", 5, 0, -1 - i) for i in range(5)]), True)
check("fewer than 10 games in the competition: no pick",
      S.u35_low_selected(row("x", "Tight FC", "New FC"), KO, fx + [played("New FC", "N", 0, 0, 2)]), False)

print("\nthe price: the Yes ask, Yes book 5c or tighter")
check("a 2c-wide book at a 0.70 ask is entered", S.fetch_u35_low_o15(
    "soccer_o15", {"soccer_o15": [row("m", "Tight FC", "Blunt FC", 0.70, 0.68)]}, fx), [dict(market_id="m", pick="a")])
check("exactly 5c wide is entered", len(S.fetch_u35_low_o15(
    "soccer_o15", {"soccer_o15": [row("m", "Tight FC", "Blunt FC", 0.70, 0.65)]}, fx)), 1)
check("6c wide is not (the universe itself allows 10c)", S.fetch_u35_low_o15(
    "soccer_o15", {"soccer_o15": [row("m", "Tight FC", "Blunt FC", 0.70, 0.64)]}, fx), [])
check("an untradeable Yes book is not", S.fetch_u35_low_o15(
    "soccer_o15", {"soccer_o15": [row("m", "Tight FC", "Blunt FC", tradeable=False)]}, fx), [])

print("\nthe over-1.5 rung is read from the market's wording, never the ticker")
g0 = KO - timedelta(days=2)
up = [dict(home="Tight FC", away="Blunt FC", kickoff=KO.strftime("%Y-%m-%dT%H:%MZ"), played=False,
           home_goals=None, away_goals=None, league="La Liga")]


def km(ticker, words, ask, bid):
    return dict(ticker=ticker, yes_sub_title=words, status="active", event_ticker=ticker.rsplit("-", 1)[0],
                yes_ask_dollars=str(ask), yes_bid_dollars=str(bid), no_ask_dollars=str(round(1 - bid, 2)),
                no_bid_dollars=str(round(1 - ask, 2)))


# Suffixes deliberately NOT the line: Kalshi renumbered them between seasons.
evs = {"KXLALIGATOTAL": [{"event_ticker": "KXLALIGATOTAL-26OCT25TIGBLU", "title": "Tight FC vs Blunt FC: Total Goals",
                          "markets": [km("KXLALIGATOTAL-26OCT25TIGBLU-7", "Over 2.5 goals scored", 0.45, 0.44),
                                      km("KXLALIGATOTAL-26OCT25TIGBLU-9", "Over 1.5 goals scored", 0.71, 0.70),
                                      km("KXLALIGATOTAL-26OCT25TIGBLU-3", "Over 3.5 goals scored", 0.22, 0.21)]}]}
guni = S.fetch_kalshi_goals(fixtures=fx + up, now=g0, events_by_series=evs)
picks = S.fetch_u35_low_o15("soccer_o15", guni, fx + up)
check("the pick is the 'Over 1.5 goals scored' contract at its 0.71 ask",
      [(p["market_id"], p["pick"], next(r for r in guni["soccer_o15"] if r["market_id"] == p["market_id"])["price_a"]) for p in picks],
      [("KXLALIGATOTAL-26OCT25TIGBLU-9", "a", 0.71)])

print("\nclubs only: internationals and cups are never entered")
check("registered on soccer_o15 alone", S.SOURCES["u35_low_o15"]["sports"], ["soccer_o15"])
for sp in ("soccer_o15_intl", "soccer_o15_cup"):
    check(f"{sp} returns nothing even with a qualifying row",
          S.fetch_u35_low_o15(sp, {sp: [row("m", "Tight FC", "Blunt FC", sport=sp)]}, fx), [])
check("the Champions League is a club scope (soccer_o15 league frags)", "UCL" in S.BTTS_LEAGUES, True)

print("\nentry, freezing and settlement are the tracker's own, as for every rule")
check("the tracker runs it (CHALLENGERS)", "u35_low_o15" in S.CHALLENGERS, True)
check("no one-per-day or day cap: every qualifying match is entered once",
      [S.SOURCES["u35_low_o15"].get(k) for k in ("one_per_day", "day_cap")], [None, None])
check("the same universe twice gives the same single pick (the tracker logs source:market once)",
      S.fetch_u35_low_o15("soccer_o15", guni, fx + up) == picks and len(picks) == 1, True)
check("Kalshi 'yes' settles side a (the over, won); 'no' side b (lost)",
      (S.classify_kalshi_market({"status": "finalized", "result": "yes"}),
       S.classify_kalshi_market({"status": "finalized", "result": "no"})), ("a", "b"))
check("a Sandbox lane, not a Production pair, on a fresh record",
      ("u35_low_o15|soccer_o15" in T.PAIR_OVERRIDES, ("u35_low_o15", "soccer_o15") in S.LANE_RESETS), (False, False))
check("judged against backing the over on every Kalshi match", S.SOURCES["u35_low_o15"]["baseline"], "population")

print("\nthe label and note")
src = S.SOURCES["u35_low_o15"]
check("label", src["label"], "Low-scoring picks → over 1.5 (clubs)")
check("the note says it is post-hoc and a forward test", ("POST-HOC" in src["note"], "forward test" in src["note"]), (True, True))
check("no guarded public phrase in the label or note", sandbox_audit.COPY_RE.findall(src["label"] + " " + src["note"]), [])

print(f"\n{'ALL PASS' if not FAILS else str(len(FAILS)) + ' FAILED'}")
sys.exit(1 if FAILS else 0)
