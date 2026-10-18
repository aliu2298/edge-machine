#!/usr/bin/env python3
"""Offline checks for the title contenders' overs paper lane (contender_overs.py) and its Soccer section."""
import datetime as dt
import sys

import contender_overs as CO
import contender_overs_build as CB
import sandbox_audit

FAILS = []
UTC = dt.timezone.utc
NOW = dt.datetime(2026, 10, 18, 12, 0, tzinfo=UTC)
KO = NOW + dt.timedelta(minutes=45)


def check(label, got, want):
    ok = got == want
    print(f"  {'ok  ' if ok else 'FAIL'} {label}" + ("" if ok else f" (got {got!r}, want {want!r})"))
    if not ok:
        FAILS.append(label)


def champ(quotes, series="KXEREDIVISIE"):
    """{team: (bid, ask)} as an open champion event."""
    return [dict(event_ticker=f"{series}-27", markets=[
        dict(ticker=f"{series}-27-{t[:3].upper()}", yes_sub_title=t, status="active",
             yes_bid_dollars=str(b), yes_ask_dollars=str(a)) for t, (b, a) in quotes.items()])]


ERE = champ({"Eindhoven": (0.43, 0.64), "Feyenoord": (0.23, 0.35), "Ajax": (0.11, 0.24), "Alkmaar": (0.09, 0.10),
             "Enschede": (0.0, 0.60), "Nijmegen": (0.0, 0.04)})


def fixture(home, away, league="Eredivisie", ko=KO, played=False):
    return dict(kickoff=ko.strftime("%Y-%m-%dT%H:%MZ"), league=league, home=home, away=away, played=played,
                competitive=True, home_goals=None, away_goals=None)


def total(series, home, away, day="26OCT18", lines=None):
    lines = lines or {1.5: (0.88, 0.90), 2.5: (0.70, 0.72), 3.5: (0.45, 0.47)}
    tag = f"{series}-{day}{home[:3].upper()}{away[:3].upper()}"
    ms = [dict(ticker=f"{tag}-{i + 2}", title=f"Will over {ln} goals be scored?", status="active",
               yes_bid_dollars=str(b), yes_ask_dollars=str(a)) for i, (ln, (b, a)) in enumerate(sorted(lines.items()))]
    return dict(event_ticker=tag, title=f"{home} vs {away}: Total Goals", markets=ms)


print("contenders: top 3 by champion-market mid at entry, no-bid teams excluded")
top = CO.contenders(ERE)
check("Eindhoven, Feyenoord, Ajax; Enschede's 0-60c (no bid) is not a contender price",
      [(c["team"], c["mid"]) for c in top], [("Eindhoven", 0.535), ("Feyenoord", 0.29), ("Ajax", 0.175)])
check("a closed market is ignored", [c["team"] for c in CO.contenders(
    [dict(markets=[dict(yes_sub_title="Old", status="finalized", yes_bid_dollars="0.9", yes_ask_dollars="0.95")])])], [])

print("\nnames: exact, or whole-word containment of 5+ characters, never fuzzy")
check("Man City is not Man United", CO.same_team("Man City", "Man United"), False)
check("Rennes is not Brest", CO.same_team("Rennes", "Brest"), False)
check("exact match", CO.same_team("SL Benfica", "SL Benfica"), True)
check("Eindhoven inside PSV Eindhoven", CO.same_team("Eindhoven", "PSV Eindhoven"), True)
check("Porto inside FC Porto, accents and case ignored", (CO.same_team("Porto", "FC Porto"), CO.same_team("Guimarães", "guimaraes")), (True, True))
check("a 4-character name must match exactly", CO.same_team("Ajax", "Ajax Cape Town"), False)
check("part of a word is not a match", CO.same_team("Porto", "Portimonense"), False)
check("an empty name never matches", CO.same_team("", "Ajax"), False)

print("\nthe line from the title, and the three variants")
ev = total("KXEREDIVISIETOTAL", "Eindhoven", "Sparta")
picks = CO.picks_for(fixture("PSV Eindhoven", "Sparta Rotterdam"), ev, top, NOW)
check("a contender's match: O15, O25, O35 at the YES ask; the suffix (-2/-3/-4) is not the line",
      [(p["rule"], p["line"], p["side"], p["price"], p["ticker"][-2:]) for p in picks],
      [("O15", 1.5, "yes", 0.9, "-2"), ("O25", 2.5, "yes", 0.72, "-3"), ("O35", 3.5, "yes", 0.47, "-4")])
check("each entry carries the contender in it and the top 3 with mids",
      (picks[0]["contenders_in"], [(c["team"], c["mid"]) for c in picks[0]["contenders"]]),
      (["Eindhoven"], [("Eindhoven", 0.535), ("Feyenoord", 0.29), ("Ajax", 0.175)]))
check("no contender in the match: nothing", CO.picks_for(fixture("Utrecht", "Sparta"), total("KXEREDIVISIETOTAL", "Utrecht", "Sparta"), top, NOW), [])
check("Alkmaar (4th) is not a contender", CO.picks_for(fixture("AZ", "Sparta"), total("KXEREDIVISIETOTAL", "Alkmaar", "Sparta"), top, NOW), [])
wide = total("KXEREDIVISIETOTAL", "Ajax", "Utrecht", lines={1.5: (0.80, 0.90), 2.5: (0.70, 0.72)})
check("a spread over 5c skips that line only", [p["rule"] for p in CO.picks_for(fixture("Ajax", "Utrecht"), wide, top, NOW)], ["O25"])

print("\nthe window, freezing and settlement")
fx = [fixture("PSV Eindhoven", "Sparta Rotterdam", ko=NOW + dt.timedelta(minutes=m)) for m in (45, 120, 10)] + \
     [fixture("Porto", "Arouca", league="Primeira Liga"), fixture("Ajax", "PSV", played=True), fixture("Lyon", "Nice", league="Ligue 1")]
check("due: 45 minutes out in scope; 2 hours, 10 minutes, played and Ligue 1 are not",
      [(f["home"], f["kickoff"]) for f in CO.due(fx, NOW)],
      [("PSV Eindhoven", KO.strftime("%Y-%m-%dT%H:%MZ")), ("Porto", KO.strftime("%Y-%m-%dT%H:%MZ"))])
POR = champ({"Porto": (0.46, 0.54), "SL Benfica": (0.29, 0.41), "Sporting CP": (0.09, 0.13), "Viseu": (0.0, 0.18), "Braga": (0.02, 0.03)},
            "KXLIGAPORTUGAL")
events = {"KXEREDIVISIE": ERE, "KXLIGAPORTUGAL": POR,
          "KXEREDIVISIETOTAL": [total("KXEREDIVISIETOTAL", "Eindhoven", "Sparta")],
          "KXLIGAPORTUGALTOTAL": [total("KXLIGAPORTUGALTOTAL", "Porto", "Arouca")]}


def fake(path):
    if path.startswith("events?"):
        series = path.split("series_ticker=")[1].split("&")[0]
        return {"events": events.get(series, [])}
    t = path.split("/")[-1]
    return {"market": {"ticker": t, "status": "finalized", "result": "yes" if t.endswith(("-2", "-3")) else "no"}}


st = CO.load("/nonexistent/contender.json")
new = CO.run(st, CO.due(fx, NOW), NOW, fake)
check("both matches enter all three variants", sorted(new),
      sorted(f"{v}:{e}" for v in CO.VARIANTS for e in ("KXEREDIVISIETOTAL-26OCT18EINSPA", "KXLIGAPORTUGALTOTAL-26OCT18PORARO")))
CO.run(st, CO.due(fx, NOW), NOW + dt.timedelta(minutes=30), fake)
check("a second read adds nothing: one frozen entry per variant per match", sum(len(v["picks"]) for v in st["rules"].values()), 6)
o15 = st["rules"]["O15"]["picks"][0]
o35 = st["rules"]["O35"]["picks"][0]
check("settled on Kalshi's result, profit per $100 after the fee",
      (o15["status"], o15["profit"], o35["status"], o35["profit"]),
      ("won", round(100 * (1 / (0.9 + CO.fee(0.9)) - 1), 2), "lost", -100.0))
check("the run log", {k: st["runs"][0][k] for k in ("due", "matched", "qualifying", "new")}, dict(due=2, matched=2, qualifying=2, new=6))

print("\nthe Soccer page section")
html = CB.section(st)
check("its id and heading", ('<section id="contender-overs">' in html, "Title contenders' matches · overs (paper)" in html), (True, True))
check("one compact rule row per variant", [f'data-rule="{k}"' in html for k in CO.VARIANTS], [True] * 3)
check("the record columns", all(c in html for c in ("Settled", "Won", "ROI after fee", "Open")), True)
check("entries show the contender and the top 3 at entry", ("Eindhoven 54c" in html, "<td>Porto</td>" in html), (True, True))
check("not in Production", "not in Production" in html, True)
check("an empty ledger says how entries arrive", "No entries yet" in CB.section({"rules": {}}), True)
check("the copy passes the audit's guarded phrases",
      sandbox_audit.COPY_RE.search(html + CB.section({"rules": {}}) + open("contender_overs.py").read()), None)
import soccer_build
page = soccer_build.place_label_rules('<nav class="toc"><a href="#events">Events</a></nav><section id="events"></section>'
                                      '<section id="method"></section><footer>', soccer_build._contender_section())
check("the Soccer page places it before the method and links it",
      (page.index('id="contender-overs"') < page.index('id="method"'), 'href="#contender-overs"' in page), (True, True))

print(f"\n{'ALL PASS' if not FAILS else str(len(FAILS)) + ' FAILED'}")
sys.exit(1 if FAILS else 0)
