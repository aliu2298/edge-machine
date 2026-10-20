#!/usr/bin/env python3
"""The corners split (2026-10-15): total under, Champions League fade, team fade."""
import datetime as dt
import json
import sys

import production as PR
import sandbox_sources as S
import sandbox_track as T

FAILS = []
UTC = dt.timezone.utc


def check(label, got, want):
    ok = got == want
    print(f"  {'ok  ' if ok else 'FAIL'} {label}" + ("" if ok else f" (got {got!r}, want {want!r})"))
    if not ok:
        FAILS.append(label)


NOW = dt.datetime(2026, 10, 17, 12, 0, tzinfo=UTC)
P = {}                                   # market_id -> model P(N+ corners)


def row(code, n, p_over, no_ask, kind="total", league="Premier League", hours=2, team=None, yes_ask=None):
    fam = "TCORNERS" if kind == "team" else "CORNERS"
    lg = "UCL" if league == "Champions League" else "EPL"
    mid = f"KX{lg}{fam}-{code}-{(team or '')[:3].upper()}{n}"
    P[mid] = p_over
    ya = yes_ask if yes_ask is not None else round(1 - no_ask + 0.02, 2)
    return dict(market_id=mid, sport="soccer_corners", venue="kalshi_binary", corner_kind=kind, corner_n=n,
                league=league, espn_home="H" + code, espn_away="A" + code, team=team, opponent=None,
                start=(NOW + dt.timedelta(hours=hours)).isoformat(), date=(NOW + dt.timedelta(hours=hours)).date().isoformat(),
                price_a=ya, price_b=no_ask, price_draw=None, untraded=False, tradeable={"a": True, "b": True},
                label=f"{code} {n}+", side_a="Yes", side_b="No", url="u", volume=0.0)


_model = S.corners_model
S.corners_model = lambda fixtures, r, ko: P.get(r["market_id"])
try:
    print("selection: one rung per match, the largest under edge")
    rows = [row("26OCT17AAABBB", 9, 0.40, 0.45), row("26OCT17AAABBB", 10, 0.30, 0.52),
            row("26OCT17AAABBB", 11, 0.20, 0.65)]
    sel = S.corners_selections("soccer_corners", {"soccer_corners": rows}, fixtures=[], now=NOW, kind="total")
    check("three rungs of one match give one selection", len(sel), 1)
    check("the rung with the largest edge after the fee", sel[0][1]["market_id"].rsplit("-", 1)[1], "10")
    check("no rung under a 5c edge is a selection",
          S.corners_selections("soccer_corners", {"soccer_corners": [row("26OCT17CCCDDD", 9, 0.50, 0.49)]},
                               fixtures=[], now=NOW, kind="total"), [])
    check("outside 4 hours of kickoff nothing is selected",
          S.corners_selections("soccer_corners", {"soccer_corners": [row("26OCT17EEEFFF", 9, 0.3, 0.5, hours=5)]},
                               fixtures=[], now=NOW, kind="total"), [])

    print("\nthe three lanes: market, league and side")
    board = {"soccer_corners": [
        row("26OCT17EPL001", 10, 0.30, 0.52),                                    # EPL total
        row("26OCT17UCL001", 10, 0.30, 0.52, league="Champions League", yes_ask=0.49),  # UCL total
        row("26OCT17EPL002", 5, 0.30, 0.55, kind="team", team="Arsenal", yes_ask=0.47),  # team
    ]}
    tu = S.fetch_corners_total_under("soccer_corners", board, fixtures=[], now=NOW)
    uf = S.fetch_corners_ucl_fade("soccer_corners", board, fixtures=[], now=NOW)
    tf = S.fetch_corners_team_fade("soccer_corners", board, fixtures=[], now=NOW)
    check("total under: the EPL total rung, on NO", [(p["market_id"][:16], p["pick"]) for p in tu], [("KXEPLCORNERS-26O", "b")])
    check("Champions League fade: the UCL total rung, on YES", [(p["market_id"][:16], p["pick"]) for p in uf], [("KXUCLCORNERS-26O", "a")])
    check("team fade: the team rung, on YES", [(p["market_id"][:16], p["pick"]) for p in tf], [("KXEPLTCORNERS-26", "a")])
    check("the total under never takes a Champions League match",
          any("UCL" in p["market_id"] for p in tu), False)
    check("a fade with no tradeable YES is not offered",
          S.fetch_corners_team_fade("soccer_corners", {"soccer_corners": [dict(board["soccer_corners"][2], tradeable={"a": False, "b": True})]},
                                    fixtures=[], now=NOW), [])

    print("\npublish: five a day, one bet a match across all corners lanes, the fade at its YES ask")
    many = [row(f"26OCT17M{i:05d}", 10, 0.30 - i * 0.01, 0.52) for i in range(7)]
    same = row("26OCT17M00006", 5, 0.20, 0.60, kind="team", team="Home", yes_ask=0.42)   # a match the total lane takes
    board = {"soccer_corners": many + [same]}
    _ch, _st, _fx = S.CHALLENGERS, T._started, S._espn_fixtures
    S.CHALLENGERS = {k: S.CHALLENGERS[k] for k in ("corners_total_under", "corners_ucl_fade", "corners_team_fade")}
    T._started = lambda r, now: False
    S._espn_fixtures = lambda: []
    _real_now = S.datetime
    try:
        led = {"quotes": [], "meta": {}, "coverage": {}}
        import unittest.mock as um
        with um.patch.object(S, "datetime", wraps=S.datetime) as m:
            m.now.side_effect = lambda tz=None: NOW
            T.publish(led, board, {}, verbose=False)
            T.publish(led, board, {}, verbose=False)
    finally:
        S.CHALLENGERS, T._started, S._espn_fixtures = _ch, _st, _fx
    tu_bets = [q for q in led["quotes"] if q["source"] == "corners_total_under" and q["bet"]]
    check("five total-under bets on the day, after two runs", len(tu_bets), 5)
    check("the strongest edges first (a lower over probability is a larger under edge)",
          [q["market_id"].split("-")[1] for q in tu_bets], [f"26OCT17M{i:05d}" for i in (6, 5, 4, 3, 2)])
    check("all on NO", {q["pick"] for q in tu_bets}, {"b"})
    tf_bets = [q for q in led["quotes"] if q["source"] == "corners_team_fade" and q["bet"]]
    check("the team fade cannot take a match the total under took in the same run",
          [q["market_id"] for q in tf_bets if "M00006" in q["market_id"]], [])
    fade_only = {"soccer_corners": [row("26OCT17Z00001", 5, 0.20, 0.60, kind="team", team="Home", yes_ask=0.42)]}
    S.CHALLENGERS = {"corners_team_fade": S.fetch_corners_team_fade}
    T._started = lambda r, now: False
    S._espn_fixtures = lambda: []
    try:
        led2 = {"quotes": [], "meta": {}, "coverage": {}}
        with um.patch.object(S, "datetime", wraps=S.datetime) as m:
            m.now.side_effect = lambda tz=None: NOW
            T.publish(led2, fade_only, {}, verbose=False)
    finally:
        S.CHALLENGERS, T._started, S._espn_fixtures = _ch, _st, _fx
    fb = [q for q in led2["quotes"] if q["source"] == "corners_team_fade" and q["bet"]]
    check("a team fade is booked on YES at the YES ask", [(q["pick"], q["price"]) for q in fb], [("a", 0.42)])
    won = dict(fb[0], status="won", result="a")
    check("and settles as a YES: a win when the team reaches N", T.pnl_after_fee(won) > 0, True)
finally:
    S.corners_model = _model

print("\nthe old rule: retired, out of Production, its record not carried over")
check("corners_under no longer runs", "corners_under" in S.CHALLENGERS, False)
check("its retirement is recorded", bool(S.SOURCES["corners_under"].get("retired")), True)
check("corners_under is not a Production pair", "corners_under|soccer_corners" in T.PAIR_OVERRIDES, False)
st = T.load_stages()
check("its stage row is the sandbox, demoted", (st["pairs"]["corners_under|soccer_corners"]["stage"],
                                               bool(st["pairs"]["corners_under|soccer_corners"].get("demoted_at"))), ("sandbox", True))
feed = json.load(open("data/production_leads.json"))
check("the feed names no corners_under lead", [k for k in feed["pairs"] if k.startswith("corners_under")], [])
d = T.load()
# Read on the LIVE ledger, so it asks only about the past: nothing older than the split
# (2026-10-15 06:29Z) is on the new lanes. Their own bets arrive from then on.
check("the three new lanes start with no bets from before the split",
      [q["id"] for q in T.all_bets(d) if q.get("source") in ("corners_total_under", "corners_ucl_fade", "corners_team_fade")
       and str(q.get("logged") or "") < "2026-10-15T06:29"], [])
check("the three new lanes went to Production by hand on 2026-10-15; corners_team_fade came out on 2026-10-20",
      (sorted((k, v["moved_on"]) for k, v in T.PAIR_OVERRIDES.items()
              if k.split("|")[0] in ("corners_total_under", "corners_ucl_fade", "corners_team_fade")),
       T.PAIR_REMOVALS["corners_team_fade|soccer_corners"]),
      ([("corners_total_under|soccer_corners", "2026-10-15"), ("corners_ucl_fade|soccer_corners", "2026-10-15")],
       dict(removed_on="2026-10-20", keep_record=True)))
print("\nthe feed: a fade is the YES of the exact rung, the under the NO")
q = dict(id="corners_team_fade:KXEPLTCORNERS-26OCT17ARSCHE-ARS5", source="corners_team_fade", sport="soccer_corners",
         market_id="KXEPLTCORNERS-26OCT17ARSCHE-ARS5", pick="a", price=0.42, venue="kalshi_binary",
         start="2026-10-17T14:00:00+00:00", logged="2026-10-17T10:00:00+00:00", espn_home="Arsenal", espn_away="Chelsea",
         team="Arsenal", league="Premier League", label="x", side_a="Yes", side_b="No", kalshi_title="Arsenal: 5+",
         status="open", bet=True)
lead = PR.lead_from_quote(q, "corners_team_fade|soccer_corners", "2026-10-15T07:00:00+00:00")
check("team fade lead: '5+ corners · Arsenal', corners_gte 5, the YES of that contract",
      (lead["headline"], lead["bet"], lead["route"]["market"], lead["route"]["outcome_side"]),
      ("5+ corners · Arsenal", {"kind": "corners_gte", "n": 5, "team": "Arsenal"}, "KXEPLTCORNERS-26OCT17ARSCHE-ARS5", "yes"))
q2 = dict(q, source="corners_total_under", market_id="KXEPLCORNERS-26OCT17ARSCHE-10", pick="b", team=None,
          kalshi_title="10+ corners")
lead2 = PR.lead_from_quote(q2, "corners_total_under|soccer_corners", "2026-10-15T07:00:00+00:00")
check("total under lead: 'Under 10 corners', corners_lte 9, the NO", (lead2["headline"], lead2["bet"], lead2["route"]["outcome_side"]),
      ("Under 10 corners", {"kind": "corners_lte", "n": 9}, "no"))

print(f"\n{'ALL PASS' if not FAILS else str(len(FAILS)) + ' FAILED'}")
sys.exit(1 if FAILS else 0)
