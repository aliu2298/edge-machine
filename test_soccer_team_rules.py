#!/usr/bin/env python3
"""Offline checks for the 8 soccer team-scoring label rules (soccer_team_rules.py) and their page section."""
import datetime as dt
import re
import sys

import lane_windows as W
import sandbox_audit
import soccer_rules as SR
import soccer_team_rules as TR
import soccer_team_rules_build as TB

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
    return [played(team, f"Opp{team}{i}", scored, conceded, start + i, league) for i in range(n)]


def filler(league="Premier League", n=40, goals=(2, 1)):
    """League games between other clubs: n matches at `goals`, a mean near 1.5 per team."""
    return [played(f"X{i}", f"Y{i}", goals[0], goals[1], 30 + i % 20, league) for i in range(n)]


def fixture(home, away, league="Premier League", ko=KO):
    return dict(kickoff=ko.strftime("%Y-%m-%dT%H:%MZ"), league=league, home=home, away=away,
                home_goals=None, away_goals=None, played=False, competitive=True)


def ev(series, home, away, day="26OCT18", quotes=None):
    """A team-total event. quotes: {(code, line): (bid, ask)}; the suffix digit is NOT the line."""
    hc, ac = home[:3].upper(), away[:3].upper()
    quotes = quotes or {(hc, 1.5): (0.45, 0.47), (ac, 1.5): (0.30, 0.32)}
    tag = f"{series}-{day}{hc}{ac}"
    names = {hc: home, ac: away}
    ms = [dict(ticker=f"{tag}-{code}{i + 5}", title=f"Will {names[code]} score over {ln} goals?", status="active",
               yes_bid_dollars=str(b), yes_ask_dollars=str(a)) for i, ((code, ln), (b, a)) in enumerate(sorted(quotes.items()))]
    return dict(event_ticker=tag, title=f"{home} vs {away}: Team Total", markets=ms)


print("labels: soccer_rules' labels, point in time")
fx = filler() + history("Alpha", 2, 1) + history("Beta", 2, 1)
check("Alpha scoring 2, conceding 1 against a ~1.5 mean is O+D-", SR.label(fx, "Alpha", "Premier League", KO), "O+D-")
late = fx + [played("Alpha", "Late", 0, 9, -1), played("Alpha", "Same", 0, 9, 0)]
check("matches at or after kickoff are never read (strictly before)", SR.label(late, "Alpha", "Premier League", KO), "O+D-")
check("fewer than 6 prior matches: no label",
      SR.label(filler() + history("Thin", 2, 0, n=5), "Thin", "Premier League", KO), None)
check("fewer than 40 league team-games: no label",
      SR.label(filler(n=19) + history("Delta", 2, 1, n=6, league="MLS"), "Delta", "MLS", KO), None)
ucl = filler("Champions League", goals=(4, 3)) + history("Alpha", 2, 1, league="Premier League")
check("the league mean is the series' league: Alpha's 2-1s against a UCL mean of 3.5 are O-D-",
      SR.label(ucl, "Alpha", "Champions League", KO), "O-D-")

print("\nwhich team a market is about, from the ticker")
check("pair BOUSUN, -BOU2 is home", TR.side_of("KXEPLTEAMTOTAL-26OCT18BOUSUN-BOU2"), "home")
check("pair BOUSUN, -SUN1 is away", TR.side_of("KXEPLTEAMTOTAL-26OCT18BOUSUN-SUN1"), "away")
check("a code at neither end is skipped", TR.side_of("KXEPLTEAMTOTAL-26OCT18BOUSUN-USU1"), None)
check("a malformed ticker is skipped", TR.side_of("KXEPLTEAMTOTAL-BOU2"), None)

print("\nthe line comes from the title, never the ticker")
check("suffix 3 with 'over 1.5' in the title is 1.5",
      TR.line_of(dict(ticker="KXEPLTEAMTOTAL-26OCT18BOUSUN-BOU3", title="Will Bournemouth score over 1.5 goals?")), 1.5)
check("no 'over N goals' wording: no line", TR.line_of(dict(ticker="X-BOU2", title="Bournemouth to score")), None)
e = ev("KXEPLTEAMTOTAL", "Bournemouth", "Sunderland", quotes={("BOU", 1.5): (0.45, 0.47), ("BOU", 2.5): (0.2, 0.22),
                                                              ("SUN", 1.5): (0.3, 0.32)})
check("market_for picks team and title line", TR.market_for(e, "home", 2.5)["title"], "Will Bournemouth score over 2.5 goals?")

print("\nrules: ordered own v opp, scoped to their leagues")
check("8 rules, groups A A B B B C C C", [TR.RULES[k]["group"] for k in sorted(TR.RULES)], list("AABBBCCC"))
spec = {"T1": ("O+D-", "O+D-", 1.5, "yes"), "T2": ("O-D-", "O-D+", 1.5, "no"), "T3": ("O+D-", "O-D-", 2.5, "yes"),
        "T4": ("O+D-", "O-D+", 1.5, "yes"), "T5": ("O+D-", "O+D+", 1.5, "yes"), "T6": ("O+D+", "O+D-", 2.5, "no"),
        "T7": ("O+D+", "O+D+", 2.5, "no"), "T8": ("O+D+", "O-D-", 1.5, "no")}
check("each rule's labels, rung and side", {k: (r["own"], r["opp"], r["line"], r["side"]) for k, r in TR.RULES.items()}, spec)
leagues = {"T1": {"Serie A", "Champions League", "Premier League", "Bundesliga", "Ligue 1"},
           "T2": {"MLS", "La Liga", "Ligue 1"}, "T3": {"MLS", "La Liga", "Serie A", "Ligue 1"},
           "T4": {"MLS", "La Liga", "Premier League"}, "T5": {"MLS", "Serie A", "Ligue 1", "Europa League"},
           "T6": {"MLS", "Premier League", "Bundesliga", "Serie A"}, "T7": {"MLS", "La Liga", "Bundesliga", "Premier League"},
           "T8": {"Premier League", "La Liga", "Ligue 1"}}
for k, want in leagues.items():
    r = TR.RULES[k]
    fires = {lg for lg in TR.SERIES if k in TR.applicable(lg, r["own"], r["opp"])}
    check(f"{k} fires in exactly its leagues", fires, want)
check("the pair is ordered: O-D+ v O-D- is not T2", TR.applicable("MLS", "O-D+", "O-D-"), [])
check("a league without a series never fires", TR.applicable("Eredivisie", "O+D-", "O+D-"), [])
check("lane_windows carries the same series map", W.SOCCER_TEAM_SERIES, TR.SERIES)

print("\nentries: YES at the ask, NO at 1 - bid, spread and price gates")
f = fixture("AFC Bournemouth", "Sunderland")
# Bournemouth O+D- v Sunderland O-D+ in the EPL: T4 (Bournemouth 2+ YES); Sunderland O-D+ v O+D-: nothing.
p = TR.picks_for(f, ("O+D-", "O-D+"), e, NOW)
check("T4 on the home team: YES at the 47c ask on its over 1.5",
      [(x["rule"], x["team_side"], x["side"], x["price"], x["line"], x["group"], x["team"]) for x in p],
      [("T4", "home", "yes", 0.47, 1.5, "B", "AFC Bournemouth")])
# Bournemouth O-D- v Sunderland O+D+ in La Liga terms: T8 (Sunderland own O+D+ v O-D-, 2+ NO) on the away team.
lf = fixture("Bournemouth", "Sunderland", league="La Liga")
le = ev("KXLALIGATEAMTOTAL", "Bournemouth", "Sunderland")
p = TR.picks_for(lf, ("O-D-", "O+D+"), le, NOW)
check("T8 on the away team: NO at 1 - 30c bid = 70c", [(x["rule"], x["team_side"], x["side"], x["price"]) for x in p],
      [("T8", "away", "no", 0.7)])
wide = ev("KXLALIGATEAMTOTAL", "Bournemouth", "Sunderland", quotes={("SUN", 1.5): (0.30, 0.36)})
check("a 6c spread: no entry", TR.picks_for(lf, ("O-D-", "O+D+"), wide, NOW), [])
edge = ev("KXLALIGATEAMTOTAL", "Bournemouth", "Sunderland", quotes={("SUN", 1.5): (0.30, 0.35)})
check("a 5c spread is allowed", [x["rule"] for x in TR.picks_for(lf, ("O-D-", "O+D+"), edge, NOW)], ["T8"])
cheap = ev("KXLALIGATEAMTOTAL", "Bournemouth", "Sunderland", quotes={("SUN", 1.5): (0.98, 0.99)})
check("NO at 2c is under the 3c floor: no entry", TR.picks_for(lf, ("O-D-", "O+D+"), cheap, NOW), [])
check("T4 does not fire in Serie A", TR.picks_for(fixture("Bournemouth", "Sunderland", league="Serie A"),
                                                  ("O+D-", "O-D+"), e, NOW), [])

print("\ntiming, freezing and settlement")
fxs = fx + [fixture("Alpha", "Beta", ko=NOW + dt.timedelta(minutes=m)) for m in (45, 120, 10)]
check("due: 45 minutes out yes, 2 hours out no, 10 minutes out no",
      [x["kickoff"] for x in TR.due(fxs, NOW)], [(NOW + dt.timedelta(minutes=45)).strftime("%Y-%m-%dT%H:%MZ")])
check("a league without team rules is never due", TR.due([fixture("A", "B", league="Eredivisie")], NOW), [])
game = fx + [fixture("Alpha", "Beta")]
kal = ev("KXEPLTEAMTOTAL", "Alpha", "Beta", quotes={("ALP", 1.5): (0.50, 0.52), ("BET", 1.5): (0.40, 0.42)})


def fake(path):
    if path.startswith("events?"):
        return {"events": [kal] if "series_ticker=KXEPLTEAMTOTAL" in path else []}
    won = path.endswith("ALP5")
    return {"market": {"ticker": path.split("/")[-1], "status": "finalized", "result": "yes" if won else "no"}}


st = TR.load("/nonexistent/ledger.json")
new = TR.run(st, game, NOW, fake)
check("Alpha O+D- v Beta O+D- in the EPL: T1 on both teams", sorted(new),
      ["T1:KXEPLTEAMTOTAL-26OCT18ALPBET:away", "T1:KXEPLTEAMTOTAL-26OCT18ALPBET:home"])
TR.run(st, game, NOW + dt.timedelta(minutes=30), fake)
check("a second read adds nothing: one frozen entry per rule, team and match", len(st["rules"]["T1"]["picks"]), 2)
rows = {r["team_side"]: r for r in st["rules"]["T1"]["picks"]}
check("settled on Kalshi's result: home YES 52c won, profit per $100 after fee",
      (rows["home"]["status"], rows["home"]["profit"]), ("won", round(100 * (1 / (0.52 + TR.fee(0.52)) - 1), 2)))
check("away YES lost $100", (rows["away"]["status"], rows["away"]["profit"]), ("lost", -100.0))
check("the entry stores group and labels", (rows["home"]["group"], rows["home"]["labels"]), ("A", {"own": "O+D-", "opp": "O+D-"}))
check("the run log counts due, labelled, candidate and matched",
      {k: st["runs"][0][k] for k in ("due", "labelled", "candidates", "matched")}, dict(due=1, labelled=1, candidates=1, matched=1))

print("\nthe page section")
html = TB.section(st)
check("all 8 rules are listed, in groups A, B and C",
      (all(f"<b>{k}</b>" in html for k in TR.RULES), all(f"Group {g}" in html for g in "ABC")), (True, True))
# Compact layout (2026-10-18): one grid line per rule on the Rules section's own classes, the
# figures labelled for the phone, each group a section disclosure with only Group A open.
lines = re.findall(r'<div class="sp-line is-label" data-rule="([^"]+)">(.*?)</div>', html)
check("team rules: one compact line per rule, no table rows", (sorted(k for k, _ in lines) == sorted(TR.RULES), "<tr><td><b>" + 'T1' in html), (True, False))
check("team rules: every figure carries its phone label",
      all(all(f'data-l="{l}"' in body for l in ("Settled", "Won", "ROI", "Open")) for _, body in lines), True)
check("team rules: evidence rides muted after the definition, whole in the tooltip",
      ('<small class="mut">' in html, 'title="' in html), (True, True))
folds = re.findall(r'<details class="section-disclosure label-group" data-group="([^"]+)"( open)?>', html)
check("team rules: each group is a disclosure, only Group A open", [(g, bool(o)) for g, o in folds], [(g, g == "A") for g in TR.GROUPS])
check("team rules: a group's summary carries its count and record",
      re.search(r'<b>Group B</b><span>\d+ rules · \d+ settled · \d+ won', html) is not None, True)
check("its own id and heading", ('<section id="team-rules">' in html, "<h2>Team scoring rules</h2>" in html), (True, True))
check("says paper and not in Production", "paper · not in Production" in html, True)
check("the columns", all(c in html for c in ("Settled", "Won", "ROI after fee", "Open", "latest 25")), True)
check("entries carry the team and labels", ("Alpha v Beta" in html, "O+D- v O+D-" in html), (True, True))
check("an empty ledger says how entries arrive", "No entries yet" in TB.section({"rules": {}}), True)
check("the copy passes the audit's guarded phrases", sandbox_audit.COPY_RE.search(html + TB.section({"rules": {}})), None)
import soccer_build
check("the Soccer page builder adds the section", "team-rules" in soccer_build._team_rules_section(), True)
page = soccer_build.place_label_rules(
    '<nav class="toc" aria-label="On this page"><a href="#rules">Rules</a><a href="#events">Events</a>'
    '<a href="#method">Method</a></nav><section id="rules"></section><section id="events" class="sp-section"></section>'
    '<section id="method"></section><footer>', '<section id="label-rules"></section><section id="team-rules"></section>')
check("the rule sections sit after the events list and before the method fold, not under the footer",
      page.index('id="events"') < page.index('id="label-rules"') < page.index('id="team-rules"') < page.index('id="method"'), True)
check("the table of contents links both", ('href="#label-rules"' in page, 'href="#team-rules"' in page), (True, True))
check("without an events section they still land above the footer",
      soccer_build.place_label_rules("<main></main><footer>", "<section id=\"x\"></section>"), '<main></main><section id="x"></section><footer>')

print(f"\n{'ALL PASS' if not FAILS else str(len(FAILS)) + ' FAILED'}")
sys.exit(1 if FAILS else 0)
