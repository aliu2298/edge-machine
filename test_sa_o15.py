#!/usr/bin/env python3
"""Offline checks for Argentina & Brasileirão over 1.5 (sa_o15.py) and its page section."""
import datetime as dt
import re
import sys

import lane_windows as W
import sa_o15 as SA
import sa_o15_build as SB
import sandbox_audit

FAILS = []
UTC = dt.timezone.utc
NOW = dt.datetime(2026, 10, 19, 21, 0, tzinfo=UTC)
KO = NOW + dt.timedelta(minutes=60)


def check(label, got, want):
    ok = got == want
    print(f"  {'ok  ' if ok else 'FAIL'} {label}" + ("" if ok else f" (got {got!r}, want {want!r})"))
    if not ok:
        FAILS.append(label)


def fixture(home, away, league="Liga Profesional", ko=KO, played=False):
    return dict(kickoff=ko.strftime("%Y-%m-%dT%H:%MZ"), league=league, home=home, away=away,
                home_goals=None, away_goals=None, played=played, competitive=True)


def ev(series, home, away, day="26OCT19", lines=None, tag=None, title=None):
    lines = lines or {0.5: (0.92, 0.94), 1.5: (0.63, 0.65), 2.5: (0.38, 0.40)}
    tag = tag or f"{series}-{day}{home[:3].upper()}{away[:3].upper()}"
    # The ticker suffix is deliberately NOT the line: Kalshi renumbered it between seasons.
    ms = [dict(ticker=f"{tag}-{i + 4}", title=f"Will over {ln} goals be scored?", status="active",
               yes_bid_dollars=str(b), yes_ask_dollars=str(a)) for i, (ln, (b, a)) in enumerate(sorted(lines.items()))]
    return dict(event_ticker=tag, title=title or f"{home} vs {away}: Total Goals", markets=ms)


print("scope: Argentina and the Brasileirão, nothing else")
check("two leagues, two series", {k: v[1] for k, v in SA.LEAGUES.items()},
      {"Liga Profesional": "KXARGPREMDIVTOTAL", "Brasileirão": "KXBRASILEIROTOTAL"})
check("lane_windows carries the same map", W.SOCCER_SA_SERIES, {k: v[1] for k, v in SA.LEAGUES.items()})
check("a Liga MX or Premier League match is never due",
      SA.due([fixture("A", "B", league="Liga MX"), fixture("C", "D", league="Premier League")], NOW), [])
check("one row per league, judged apart", sorted(SA.ROWS), ["ARG", "BRA"])
check("the note records both research figures",
      ("64/86 (74%)" in SA.__doc__ and "+11.9%" in SA.__doc__ and "43/57 (75%)" in SA.__doc__ and "-3.6%" in SA.__doc__), True)

print("\nnames: exact or whole words, never fuzzy, ambiguity skipped")
check("Junin is Sarmiento (Junín)", SA.same_team("Junin", "Sarmiento (Junín)"), True)
check("Belgrano de Cordoba is Belgrano (Córdoba)", SA.same_team("Belgrano de Cordoba", "Belgrano (Córdoba)"), True)
check("Paranaense is Athletico-PR (alias)", SA.same_team("Paranaense", "Athletico-PR"), True)
check("Racing Avellaneda is Racing Club (alias)", SA.same_team("Racing Avellaneda", "Racing Club"), True)
check("Man City is not Man United", SA.same_team("Man City", "Man United"), False)
check("a 4-letter fragment never matches", SA.same_team("Club", "Racing Club"), False)
f1 = fixture("Estudiantes de La Plata", "San Lorenzo")
f2 = fixture("Estudiantes de Río Cuarto", "Aldosivi")
e1 = ev("KXARGPREMDIVTOTAL", "Estudiantes La Plata", "San Lorenzo de Almagro")
check("the right Estudiantes by its opponent", (SA.find_event(f1, [e1], [f1, f2]) is e1, SA.find_event(f2, [e1], [f1, f2])), (True, None))
amb = ev("KXARGPREMDIVTOTAL", "Gimnasia", "Platense")
g1, g2 = fixture("Gimnasia (Mendoza)", "Platense"), fixture("Gimnasia La Plata", "Platense", ko=KO + dt.timedelta(hours=3))
check("an event two fixtures could claim is skipped", SA.find_event(g1, [amb], [g1, g2]), None)
old = ev("KXBRASILEIROTOTAL", "x", "y", title="Paranaense at Vasco da Gama: Totals")
fb = fixture("Vasco da Gama", "Athletico-PR", league="Brasileirão")
check("the older 'Away at Home: Totals' title reads", SA.find_event(fb, [old], [fb]) is old, True)
check("a day too far is not the match",
      SA.find_event(f1, [ev("KXARGPREMDIVTOTAL", "Estudiantes La Plata", "San Lorenzo", day="26OCT22")], [f1]), None)

print("\nthe line comes from the title; YES at the ask; spread 5c or less")
fa = fixture("Deportivo Riestra", "Unión (Santa Fe)")
p = SA.pick_for(fa, ev("KXARGPREMDIVTOTAL", "Riestra", "Union Santa Fe"), NOW)
check("over 1.5 YES at the 65c ask, ticker suffix ignored", (p["line"], p["side"], p["price"], p["rule"], p["ticker"][-2:]),
      (1.5, "yes", 0.65, "ARG", "-5"))
check("a wide over 1.5 book: no entry", SA.pick_for(fa, ev("KXARGPREMDIVTOTAL", "Riestra", "Union Santa Fe",
                                                          lines={1.5: (0.58, 0.65)}), NOW), None)
check("no price band: an 88c over 1.5 still enters",
      SA.pick_for(fa, ev("KXARGPREMDIVTOTAL", "Riestra", "Union Santa Fe", lines={1.5: (0.87, 0.88)}), NOW)["price"], 0.88)

print("\nentry window, freezing, settlement, per-league rows")
fxs = [fixture("Deportivo Riestra", "Unión (Santa Fe)", ko=NOW + dt.timedelta(minutes=m)) for m in (60, 120, 10)]
check("due: 60 minutes out yes, 2 hours out no, 10 minutes out no", len(SA.due(fxs, NOW)), 1)
arg = fixture("Deportivo Riestra", "Unión (Santa Fe)")
bra = fixture("Corinthians", "Vitória", league="Brasileirão")
kal = {"KXARGPREMDIVTOTAL": [ev("KXARGPREMDIVTOTAL", "Riestra", "Union Santa Fe")],
       "KXBRASILEIROTOTAL": [ev("KXBRASILEIROTOTAL", "Corinthians", "Vitoria", lines={1.5: (0.70, 0.72)})]}


def fake(path):
    if path.startswith("events?"):
        return {"events": next((v for k, v in kal.items() if f"series_ticker={k}&" in path), [])}
    return {"market": {"ticker": path.split("/")[-1], "status": "finalized",
                       "result": "yes" if "ARG" in path else "no"}}


import soccer_rules as SR                                       # noqa: E402
SR.D.pages = lambda path, key, fetch: fetch(path).get(key) or []
st = SA.load("/nonexistent/sa.json")
new = SA.run(st, [arg, bra], NOW, fake)
check("one entry per league", sorted(i.split(":")[0] for i in new), ["ARG", "BRA"])
SA.run(st, [arg, bra], NOW + dt.timedelta(minutes=30), fake)
check("a second read adds nothing: one frozen entry per match", sum(len(v["picks"]) for v in st["rules"].values()), 2)
a_row, b_row = st["rules"]["ARG"]["picks"][0], st["rules"]["BRA"]["picks"][0]
check("settled on Kalshi's result: ARG yes wins after the fee, BRA no loses",
      (a_row["status"], a_row["profit"], b_row["status"], b_row["profit"]),
      ("won", round(100 * (1 / (0.65 + SA.fee(0.65)) - 1), 2), "lost", -100.0))
check("the run writes the next 14 days of these kickoffs for the VPS",
      st["schedule"], sorted({dt.datetime.fromisoformat(f["kickoff"].replace("Z", "+00:00")).isoformat() for f in (arg, bra)}))

print("\nlane windows: these kickoffs ask for a soccer rules read")
sa_fx = [fixture("Deportivo Riestra", "Unión (Santa Fe)", ko=dt.datetime(2026, 10, 20, 0, 15, tzinfo=UTC))]
due = lambda h, m, fx=sa_fx: sorted(k for w, k in W.due(dt.datetime(2026, 10, 19, h, m, tzinfo=UTC), {"quotes": []}, [], fx)
                                    if w["lane"] == "soccer_rules")
check("a 00:15Z kickoff: read 1 at 22:50, read 2 at 23:20, none at 23:58", (due(22, 50), due(23, 20), due(23, 58)), ([1], [2], []))
W._fixtures_cache = lambda: []
W._sa_schedule = lambda: ["2026-10-20T00:15:00+00:00"]
check("on the VPS (no ESPN cache) the ledger's schedule stands in",
      [t.isoformat() for t in W.sa_kickoffs(dt.datetime(2026, 10, 19, 22, 0, tzinfo=UTC))], ["2026-10-20T00:15:00+00:00"])

print("\nthe page section")
html = SB.section(st)
check("its id and heading", ('<section id="sa-o15">' in html, "Argentina &amp; Brasileirão over 1.5 (paper)" in html), (True, True))
rows = re.findall(r'<div class="sp-line is-label" data-rule="([^"]+)">(.*?)</div>', html)
check("compact rows, one per league, figures labelled",
      ([k for k, _ in rows], all('data-l="ROI"' in b for _, b in rows)), (["ARG", "BRA"], True))
check("the per-league records show", ("Argentina" in html, "Brasileirão" in html), (True, True))
check("public copy passes the guard", sandbox_audit.COPY_RE.search(html + SA.__doc__) is None, True)
check("an empty ledger says how entries arrive", "No entries yet" in SB.section({"rules": {}}), True)

print(f"\n{'ALL PASS' if not FAILS else str(len(FAILS)) + ' FAILED'}")
sys.exit(1 if FAILS else 0)
