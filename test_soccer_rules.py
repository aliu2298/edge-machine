#!/usr/bin/env python3
"""Offline checks for the 21 soccer total-goals label rules (soccer_rules.py) and their page section."""
import datetime as dt
import sys

import lane_windows as W
import soccer_rules as SR
import soccer_rules_build as SB

FAILS = []
UTC = dt.timezone.utc
NOW = dt.datetime(2026, 10, 18, 12, 0, tzinfo=UTC)
KO = NOW + dt.timedelta(minutes=45)


def check(label, got, want):
    ok = got == want
    print(f"  {'ok  ' if ok else 'FAIL'} {label}" + ("" if ok else f" (got {got!r}, want {want!r})"))
    if not ok:
        FAILS.append(label)


def played(home, away, hg, ag, days_ago, league="Premier League", competitive=True):
    t = KO - dt.timedelta(days=days_ago)
    return dict(kickoff=t.strftime("%Y-%m-%dT%H:%MZ"), league=league, home=home, away=away,
                home_goals=hg, away_goals=ag, played=True, competitive=competitive)


def history(team, scored, conceded, n=10, league="Premier League", start=1):
    """n played matches for `team`, each scoring `scored` and conceding `conceded`."""
    return [played(team, f"Opp{team}{i}", scored, conceded, start + i, league) for i in range(n)]


def filler(league="Premier League", n=40, goals=(2, 1)):
    """League games between other clubs: n matches at `goals`, a league mean of 1.5 per team."""
    return [played(f"X{i}", f"Y{i}", goals[0], goals[1], 30 + i % 20, league) for i in range(n)]


def fixture(home, away, league="Premier League", ko=KO):
    return dict(kickoff=ko.strftime("%Y-%m-%dT%H:%MZ"), league=league, home=home, away=away,
                home_goals=None, away_goals=None, played=False, competitive=True)


def ev(series, home, away, day="26OCT18", lines=None):
    lines = lines or {2.5: (0.48, 0.50), 3.5: (0.30, 0.32)}
    tag = f"{series}-{day}{home[:3].upper()}{away[:3].upper()}"
    # The suffix is deliberately NOT the line: Kalshi renumbered it between seasons.
    ms = [dict(ticker=f"{tag}-{i + 7}", title=f"Will over {ln} goals be scored?", status="active",
               yes_bid_dollars=str(b), yes_ask_dollars=str(a)) for i, (ln, (b, a)) in enumerate(sorted(lines.items()))]
    return dict(event_ticker=tag, title=f"{home} vs {away}: Total Goals", markets=ms)


print("labels: last 10 competitive matches against the league mean, point in time")
fx = filler() + history("Alpha", 1, 1) + history("Beta", 2, 2)
check("league mean is goals per team over the league's games before kickoff",
      round(SR.league_mean(fx, "Premier League", KO), 3), round((40 * 3 + 10 * 2 + 10 * 4) / 120, 3))
check("Alpha scoring 1 and conceding 1 against a 1.5 mean is O-D-", SR.label(fx, "Alpha", "Premier League", KO), "O-D-")
check("Beta scoring 2 and conceding 2 is O+D+", SR.label(fx, "Beta", "Premier League", KO), "O+D+")
late = fx + [played("Alpha", "Late", 9, 0, -1)]
check("a match after kickoff is never read", SR.label(late, "Alpha", "Premier League", KO), "O-D-")
fr = fx + [played("Alpha", f"F{i}", 6, 0, 0.5, competitive=False) for i in range(5)]
check("friendlies (competitive False) are not form", SR.label(fr, "Alpha", "Premier League", KO), "O-D-")
old = history("Gamma", 0, 0, n=5, start=20) + history("Gamma", 3, 0, n=10, start=1)
check("only the last 10 count: ten recent 3-0 wins make Gamma O+D-",
      SR.label(filler() + old, "Gamma", "Premier League", KO), "O+D-")
check("fewer than 6 prior matches: no label", SR.label(filler() + history("Thin", 2, 0, n=5), "Thin", "Premier League", KO), None)
check("fewer than 40 league team-games: no label",
      SR.label(filler(n=5) + history("Delta", 1, 1, n=6, league="MLS"), "Delta", "Premier League", KO), None)
check("labels() reads both teams of a fixture", SR.labels(fx, fixture("Alpha", "Beta")), ("O-D-", "O+D+"))

print("\nrule tests: unordered pairs, either-team, an O+ opponent")
check("A1 MLS O-D- v O-D+ either way round",
      (SR.applicable("MLS", "O-D-", "O-D+"), SR.applicable("MLS", "O-D+", "O-D-")), (["A1"], ["A1"]))
check("A6 EPL: an O-D- team v an O+ opponent (O+D+ or O+D-), not v O-D+",
      (SR.applicable("Premier League", "O+D+", "O-D-"), "A6" in SR.applicable("Premier League", "O-D-", "O+D-"),
       SR.applicable("Premier League", "O-D-", "O-D+")), (["A6"], True, []))
check("A5 Nations League: either team O-",
      ("A5" in SR.applicable("UEFA Nations League", "O+D+", "O-D+"), SR.applicable("UEFA Nations League", "O+D+", "O+D-")),
      (True, []))
check("B3 Eredivisie: O+D- v any D- opponent", SR.applicable("Eredivisie", "O-D-", "O+D-"), ["B3"])
check("a rule never fires outside its league", SR.applicable("Serie A", "O-D-", "O-D+"), [])
check("EPL O+D- v O+D-: B5 only", SR.applicable("Premier League", "O+D-", "O+D-"), ["B5"])
check("every rule names a league with a Kalshi series, and lane_windows has the same map",
      (all(r["league"] in SR.SERIES for r in SR.RULES.values()), W.SOCCER_SERIES == SR.SERIES, len(SR.RULES)), (True, True, 21))

print("\nthe line comes from the title, never the ticker")
m = dict(ticker="KXEPLTOTAL-26OCT18BOUSUN-2", title="Will over 1.5 goals be scored?")
check("suffix -2 with 'over 1.5' in the title is 1.5", SR.line_of(m), 1.5)
check("the yes subtitle is read when the title has no line",
      SR.line_of(dict(ticker="X-4", title="Total", yes_sub_title="Over 4.5 goals scored")), 4.5)
e = ev("KXEPLTOTAL", "Bournemouth", "Sunderland")
check("market_at picks by title line", SR.market_at(e, 3.5)["title"], "Will over 3.5 goals be scored?")

print("\nmatching a Kalshi event to its ESPN fixture")
f = fixture("AFC Bournemouth", "Sunderland")
check("by date and both names", SR.find_event(f, [ev("KXEPLTOTAL", "Leeds United", "Everton"), e])["event_ticker"], e["event_ticker"])
check("a day too far is not the match", SR.find_event(f, [ev("KXEPLTOTAL", "Bournemouth", "Sunderland", day="26OCT21")]), None)
check("one name right is not enough", SR.find_event(f, [ev("KXEPLTOTAL", "Bournemouth", "Chelsea")]), None)
check("event date reads the tag", SR.event_date("KXEPLTOTAL-26OCT18BOUSUN"), dt.date(2026, 10, 18))

print("\nprice bands: Over buys YES at the ask, Under buys NO at 1 - bid")
labs = ("O-D-", "O+D+")                 # A6 EPL: Under 2.5, NO <= 55c
fe = fixture("AFC Bournemouth", "Sunderland")
p = SR.picks_for(fe, labs, ev("KXEPLTOTAL", "Bournemouth", "Sunderland", lines={2.5: (0.48, 0.50)}), NOW)
check("A6: bid 48c -> NO at 52c, inside <=55c", [(x["rule"], x["side"], x["price"], x["line"], x["group"]) for x in p],
      [("A6", "no", 0.52, 2.5, "A")])
check("bid 40c -> NO at 60c, outside", SR.picks_for(fe, labs, ev("KXEPLTOTAL", "Bournemouth", "Sunderland", lines={2.5: (0.40, 0.42)}), NOW), [])
check("spread over 5c: no quote, no entry",
      SR.picks_for(fe, labs, ev("KXEPLTOTAL", "Bournemouth", "Sunderland", lines={2.5: (0.44, 0.52)}), NOW), [])
bf = fixture("Bayer Leverkusen", "SC Freiburg", league="Bundesliga")
over = lambda b, a: SR.picks_for(bf, ("O+D-", "O+D-"), ev("KXBUNDESLIGATOTAL", "Leverkusen", "Freiburg", lines={3.5: (b, a)}), NOW)
check("A2: Over 3.5 YES at the 45c ask inside <=60c; a 62c ask is outside",
      ([(x["rule"], x["side"], x["price"]) for x in over(0.43, 0.45)], over(0.60, 0.62)), ([("A2", "yes", 0.45)], []))
mf = fixture("FC Cincinnati", "Columbus Crew", league="MLS")
a1 = lambda b: SR.picks_for(mf, ("O-D+", "O-D-"), ev("KXMLSTOTAL", "Cincinnati", "Columbus", lines={3.5: (b, b + 0.02)}), NOW)
check("A1 band 50-75c: NO at 52c in, 45c out, 77c out",
      ([x["price"] for x in a1(0.48)], a1(0.55), a1(0.23)), ([0.52], [], []))

print("\ntiming, freezing and settlement")
fxs = fx + [fixture("Alpha", "Beta", ko=NOW + dt.timedelta(minutes=m)) for m in (45, 120, 10)]
check("due: 45 minutes out yes, 2 hours out no, 10 minutes out no",
      [x["kickoff"] for x in SR.due(fxs, NOW)], [(NOW + dt.timedelta(minutes=45)).strftime("%Y-%m-%dT%H:%MZ")])
check("a league without rules is never due", SR.due([fixture("A", "B", league="Liga MX")], NOW), [])
game = fx + [fixture("Alpha", "Beta")]
kal = ev("KXEPLTOTAL", "Alpha", "Beta", lines={2.5: (0.47, 0.49)})
calls = []


def fake(path):
    calls.append(path)
    if path.startswith("events?"):
        return {"events": [kal] if "series_ticker=KXEPLTOTAL" in path else []}
    return {"market": {"ticker": path.split("/")[-1], "status": "finalized", "result": "no"}}


st = {"rules": {k: {"picks": []} for k in SR.RULES}}
new = SR.run(st, game, NOW, fake)
check("Alpha O-D- v Beta O+D+ in the EPL: one A6 entry at NO 53c", [(i.split(":")[0], st["rules"]["A6"]["picks"][0]["price"]) for i in new],
      [("A6", 0.53)])
SR.run(st, game, NOW + dt.timedelta(minutes=30), fake)
check("a second read adds nothing: one frozen entry per rule per match", sum(len(v["picks"]) for v in st["rules"].values()), 1)
row = st["rules"]["A6"]["picks"][0]
check("settled on Kalshi's result: NO on a 'no' result wins, profit after fee",
      (row["status"], row["profit"]), ("won", round(100 * (1 / (0.53 + SR.fee(0.53)) - 1), 2)))
check("the run log counts due, labelled, candidate and matched", {k: st["runs"][0][k] for k in ("due", "labelled", "candidates", "matched")},
      dict(due=1, labelled=1, candidates=1, matched=1))
lost = {"rules": {"A2": {"picks": [dict(id="x", ticker="T", side="yes", price=0.4, status="open")]}}}
SR.settle(lost, NOW, lambda p: {"market": {"status": "finalized", "result": "no"}})
check("a YES on a 'no' result loses $100", (lost["rules"]["A2"]["picks"][0]["status"], lost["rules"]["A2"]["picks"][0]["profit"]), ("lost", -100.0))

print("\nlane windows: one window per kickoff, from the fixtures passed in")
lw = [fixture("Alpha", "Beta", ko=dt.datetime(2026, 10, 18, 14, 0, tzinfo=UTC)),
      fixture("P", "Q", league="Liga MX", ko=dt.datetime(2026, 10, 18, 15, 0, tzinfo=UTC))]
got = lambda h, mi: sorted(k for w, k in W.due(dt.datetime(2026, 10, 18, h, mi, tzinfo=UTC), {"quotes": []}, [], lw)
                           if w["lane"] == "soccer_rules")
check("a 14:00Z kickoff: read 1 at 12:35, read 2 at 13:05, nothing at 13:45 or 12:00; Liga MX never",
      (got(12, 35), got(13, 5), got(13, 45), got(12, 0)), ([1], [2], [], []))
check("its stamp file", "data/soccer_rules_window/request.txt" in W.stamp_lines(
    dt.datetime(2026, 10, 18, 12, 35, tzinfo=UTC), {"quotes": []}, [], lw), True)

print("\nthe page section")
html = SB.section(st)
check("all 21 rules are listed, in groups A, B and C",
      (all(f"<b>{k}</b>" in html for k in SR.RULES), all(f"Group {g}" in html for g in "ABC")), (True, True))
check("and the entries table carries the match and labels", ("Alpha v Beta" in html, "O-D- v O+D+" in html), (True, True))
check("an empty ledger says how entries arrive", "No entries yet" in SB.section({"rules": {}}), True)

print(f"\n{'ALL PASS' if not FAILS else str(len(FAILS)) + ' FAILED'}")
sys.exit(1 if FAILS else 0)
