#!/usr/bin/env python3
"""Offline checks for ere_draw_home (2026-11-12): the Eredivisie draw band v2. v1's band and ask cap, the home side the favourite,
kickoff inside 24 hours; a fresh record under its own key; v1 untouched; not in Production."""
import datetime as dt
import sys

import promotion_gate as PG
import sandbox_sources as S

FAILS = []
NOW = dt.datetime(2026, 11, 14, 12, 0, tzinfo=dt.timezone.utc)


def check(label, got, want):
    ok = got == want
    print(f"  {'ok  ' if ok else 'FAIL'} {label}" + ("" if ok else f" (got {got!r}, want {want!r})"))
    if not ok:
        FAILS.append(label)


def row(mid, pa, pd, pb, hours=12.0, **k):
    start = (NOW + dt.timedelta(hours=hours)).isoformat()
    return dict(dict(venue="kalshi", market_id="KXEREDIVISIEGAME-" + mid, price_a=pa, price_draw=pd, price_b=pb, start=start), **k)


def picks(*rows, now=NOW):
    return [p["market_id"][-1] for p in S.fetch_ere_draw_home("soccer", {"soccer": list(rows)}, now)]


print("the rule")
check("home favourite, in the band, inside 24h: backed", picks(row("A", 0.55, 0.24, 0.25)), ["A"])
check("the pick is the draw", {p["pick"] for p in S.fetch_ere_draw_home("soccer", {"soccer": [row("A", 0.55, 0.24, 0.25)]}, NOW)}, {"draw"})
check("away favourite: not backed (v1 still backs it)", (picks(row("B", 0.25, 0.24, 0.55)),
                                                          len(S.fetch_ere_draw("soccer", {"soccer": [row("B", 0.25, 0.24, 0.55)]}))), ([], 1))
check("neither side favoured: not backed", picks(row("C", 0.40, 0.21, 0.40)), [])
check("more than 24h out: not backed", picks(row("D", 0.55, 0.24, 0.25, hours=24.5)), [])
check("exactly 24h out: backed", picks(row("E", 0.55, 0.24, 0.25, hours=24.0)), ["E"])
check("already started: not backed", picks(row("F", 0.55, 0.24, 0.25, hours=-0.5)), [])
check("no kickoff on the row: not backed", picks(dict(row("G", 0.55, 0.24, 0.25), start=None)), [])
check("draw share under the band: not backed", picks(row("H", 0.62, 0.19, 0.20)), [])
check("draw share at 0.25: not backed (the band is half-open, as in v1)", picks(row("I", 0.45, 0.25, 0.30)), [])
check("ask above 0.26: not backed", picks(row("J", 0.58, 0.27, 0.30)), [])
check("another league: not backed", picks(dict(row("K", 0.55, 0.24, 0.25), market_id="KXEPLGAME-K")), [])
check("another venue: not backed", picks(row("L", 0.55, 0.24, 0.25, venue="polymarket_us")), [])
check("an untradeable draw: not backed", picks(row("M", 0.55, 0.24, 0.25, tradeable={"draw": False})), [])
check("an untraded board: not backed", picks(row("N", 0.55, 0.24, 0.25, untraded=True)), [])
check("no other domain has a draw", S.fetch_ere_draw_home("tennis", {"soccer": [row("A", 0.55, 0.24, 0.25)]}, NOW), [])
check("a naive clock is read as UTC", picks(row("A", 0.55, 0.24, 0.25), now=NOW.replace(tzinfo=None)), ["A"])

print("registration")
src = S.SOURCES["ere_draw_home"]
check("registered as a rule on three-way soccer, judged against the draw population", (src["kind"], src["sports"], src["baseline"], src["connected"]),
      ("Rule", ["soccer"], "draw_population", True))
check("wired to its fetcher", S.CHALLENGERS["ere_draw_home"] is S.fetch_ere_draw_home, True)
check("v1 keeps its own fetcher and terms", (S.CHALLENGERS["ere_draw"] is S.fetch_ere_draw, S.ERE_DRAW_BAND, S.ERE_DRAW_MAX_ASK), (True, (0.20, 0.25), 0.26))
check("the note names its pre-registration and its weak parts", all(x in src["note"] for x in ("prereg_ere_draw_v2_2026-11-12.md", "Weak parts", "fresh record")), True)
check("the window is 24 hours", S.ERE_DRAW_HOME_MAX_H, 24.0)

print("not in Production")
check("v2 is not a Production lane", "ere_draw_home|soccer" in PG.production_lanes(), False)
check("the promotion gate can grade it when the time comes", PG.grader("ere_draw_home|soccer") is not None, True)
check("the promotion gate still holds", PG.verify(), [])

print()
if FAILS:
    print(f"{len(FAILS)} FAILED: " + "; ".join(FAILS))
    sys.exit(1)
print("all ere_draw_home checks passed")
