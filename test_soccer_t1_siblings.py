#!/usr/bin/env python3
"""Offline checks (2026-11-06, Olu): T1's two Sandbox paper siblings in the team-rules engine.

T1-H takes only the home team's 2+ YES on T1's matches; T1-M buys the match over 3.5 YES on the same matches, one bet a
match. Both read T1's own predicate (soccer_team_rules.fires / t1_sides), so they cannot drift from it; T1 is unchanged.
Same entry as T1 (90-20 min before kickoff, spread 5c or less, 3-97c, YES at the ask). A missing market, rung or quote
is a logged skip. Paper only. On the Soccer page each is one row right under T1, its detail in the row's fold.
"""
import datetime as dt
import inspect
import re
import sys

import sandbox_audit
import soccer_build as SBLD
import soccer_lanes as L
import soccer_team_rules as TR
import soccer_team_rules_production as TRP
FAILS = []
UTC = dt.timezone.utc
NOW = dt.datetime(2026, 10, 18, 12, 0, tzinfo=UTC)
KO = NOW + dt.timedelta(minutes=45)


# The fixture helpers of test_soccer_team_rules.py (copied: importing it would run it).
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




def check(label, got, want):
    ok = got == want
    print(f"  {'ok  ' if ok else 'FAIL'} {label}" + ("" if ok else f" (got {got!r}, want {want!r})"))
    if not ok:
        FAILS.append(label)


def total_ev(home, away, day="26OCT18", rungs=None, series="KXEPLTOTAL"):
    """A match-total event; rungs: {line: (bid, ask)}."""
    rungs = {2.5: (0.48, 0.50), 3.5: (0.27, 0.29)} if rungs is None else rungs
    tag = f"{series}-{day}{home[:3].upper()}{away[:3].upper()}"
    ms = [dict(ticker=f"{tag}-{int(ln)}", title=f"{home} vs {away}: Totals", yes_sub_title=f"Over {ln} goals scored",
               status="active", yes_bid_dollars=str(b), yes_ask_dollars=str(a)) for ln, (b, a) in rungs.items()]
    return dict(event_ticker=tag, title=f"{home} vs {away}: Totals", markets=ms)


print("\none predicate: T1's own")
check("fires() is the test applicable() uses for every rule", "fires(k, league, own, opp)" in inspect.getsource(TR.applicable), True)
check("a T1 match: both teams O+D- in a T1 league; T1 takes both sides",
      (TR.t1_sides("Premier League", ("O+D-", "O+D-")), TR.t1_sides("La Liga", ("O+D-", "O+D-")),
       TR.t1_sides("Premier League", ("O+D-", "O-D+"))), (["home", "away"], [], []))
check("the siblings read t1_sides, not their own labels or leagues",
      ('t1_sides(f["league"], labs)' in inspect.getsource(TR.t1h_pick), 't1_sides(f["league"], labs)' in inspect.getsource(TR.t1m_pick),
       "leagues" in TR.SIBLINGS["T1H"], "leagues" in TR.SIBLINGS["T1M"]), (True, True, False, False))
check("T1 itself is unchanged", (TR.RULES["T1"]["own"], TR.RULES["T1"]["opp"], TR.RULES["T1"]["line"], TR.RULES["T1"]["side"],
                                 TR.RULES["T1"]["leagues"]),
      ("O+D-", "O+D-", 1.5, "yes", ("Serie A", "Champions League", "Premier League", "Bundesliga", "Ligue 1")))
check("two siblings, registered today, neither a Production pair",
      ([m["name"] for m in TR.SIBLINGS.values()], {m["registered"] for m in TR.SIBLINGS.values()}, set(TR.SIBLINGS) & set(TRP.PAIRS)),
      (["T1-H", "T1-M"], {"2026-11-06"}, set()))
check("a fresh ledger carries both lanes", sorted(TR.load("/nonexistent/x.json")["rules"]), sorted(list(TR.RULES) + ["T1H", "T1M"]))

print("\nthe run")
fx = filler() + history("Alpha", 2, 1) + history("Beta", 2, 1)
game = fx + [fixture("Alpha", "Beta")]
kal = ev("KXEPLTEAMTOTAL", "Alpha", "Beta", quotes={("ALP", 1.5): (0.50, 0.52), ("BET", 1.5): (0.40, 0.42)})
results = {}


def make_fetch(total):
    def fetch(path):
        if path.startswith("events?"):
            if "series_ticker=KXEPLTEAMTOTAL" in path:
                return {"events": [kal]}
            if "series_ticker=KXEPLTOTAL" in path:
                return {"events": [total] if total else []}
            return {"events": []}
        t = path.split("/")[-1]
        return {"market": {"ticker": t, "status": "finalized", "result": results[t]} if t in results
                else {"ticker": t, "status": "active"}}
    return fetch


st = TR.load("/nonexistent/ledger.json")
new = TR.run(st, game, NOW, make_fetch(total_ev("Alpha", "Beta")))
check("T1 on both teams, T1-H on the home team, T1-M on the match", sorted(new),
      ["T1:KXEPLTEAMTOTAL-26OCT18ALPBET:away", "T1:KXEPLTEAMTOTAL-26OCT18ALPBET:home",
       "T1H:KXEPLTEAMTOTAL-26OCT18ALPBET:home", "T1M:KXEPLTOTAL-26OCT18ALPBET"])
h = st["rules"]["T1H"]["picks"][0]
t1_home = next(p for p in st["rules"]["T1"]["picks"] if p["team_side"] == "home")
check("T1-H: the home 2+ YES at the 52c ask, the same contract T1 took on the home side",
      (h["rule"], h["team"], h["side"], h["price"], h["ticker"]), ("T1H", "Alpha", "yes", 0.52, t1_home["ticker"]))
m = st["rules"]["T1M"]["picks"][0]
check("T1-M: the over 3.5 rung (not 2.5) YES at the 29c ask, line 3.5, labels kept",
      (m["rule"], m["ticker"], m["line"], m["side"], m["price"], m["labels"]),
      ("T1M", "KXEPLTOTAL-26OCT18ALPBET-3", 3.5, "yes", 0.29, {"home": "O+D-", "away": "O+D-"}))
TR.run(st, game, NOW + dt.timedelta(minutes=20), make_fetch(total_ev("Alpha", "Beta")))   # still inside the window
check("a second read adds nothing: one entry a match for each", (len(st["rules"]["T1H"]["picks"]), len(st["rules"]["T1M"]["picks"])), (1, 1))
results.update({m["ticker"]: "yes", h["ticker"]: "no"})
TR.run(st, game, NOW + dt.timedelta(hours=4), make_fetch(total_ev("Alpha", "Beta")))
check("settled on Kalshi's own result, after the fee", (m["status"], m["profit"], h["status"], h["profit"]),
      ("won", round(100 * (1 / (0.29 + TR.fee(0.29)) - 1), 2), "lost", -100.0))

print("\nskips are logged, not silent")
for label, total, want in (
        ("no match-total event", None, "no Kalshi match-total event for the match"),
        ("no 3.5 rung", total_ev("Alpha", "Beta", rungs={2.5: (0.48, 0.50)}), "no open over 3.5 rung on the match total"),
        ("a 6c spread", total_ev("Alpha", "Beta", rungs={3.5: (0.25, 0.31)}), "match over 3.5: no quote with a spread of 5c or less"),
        ("a 2c ask", total_ev("Alpha", "Beta", rungs={3.5: (0.01, 0.02)}), "match over 3.5: ask 0.02 outside 3-97c")):
    s2 = TR.load("/nonexistent/ledger.json")
    TR.run(s2, game, NOW, make_fetch(total))
    sk = list((s2["rules"]["T1M"].get("skips") or {}).values())
    check(f"T1-M, {label}: no entry, the reason logged; T1 and T1-H still enter",
          (s2["rules"]["T1M"]["picks"], [x["reason"] for x in sk], len(s2["rules"]["T1"]["picks"]), len(s2["rules"]["T1H"]["picks"])),
          ([], [want], 2, 1))
s3 = TR.load("/nonexistent/ledger.json")
TR.run(s3, game, NOW, make_fetch(total_ev("Alpha", "Beta", rungs={3.5: (0.25, 0.31)})))
TR.run(s3, game, NOW + dt.timedelta(minutes=20), make_fetch(total_ev("Alpha", "Beta")))   # 25 min before kickoff
check("a later read inside the window that finds the quote enters, and clears the skip",
      (len(s3["rules"]["T1M"]["picks"]), s3["rules"]["T1M"].get("skips")), (1, {}))
not_t1 = filler() + history("Alpha", 2, 1) + history("Beta", 0, 2) + [fixture("Alpha", "Beta")]
s4 = TR.load("/nonexistent/ledger.json")
TR.run(s4, not_t1, NOW, make_fetch(total_ev("Alpha", "Beta")))
check("not a T1 match: no sibling entry and no skip", (s4["rules"]["T1H"]["picks"], s4["rules"]["T1M"]["picks"],
                                                      s4["rules"]["T1H"].get("skips"), s4["rules"]["T1M"].get("skips")),
      ([], [], None, None))

print("\nnot published: paper only")
check("the Production feed reads its pairs only", [q for q in TRP.quotes(st) if q.get("rule") in ("T1H", "T1M")], [])

print("\nthe Soccer page: one row each, right under T1")
html = SBLD.build()
rules = html[html.find('<section id="rules"'):html.find('<section id="events"')]
order = [x for x in re.findall(r'data-source="([^"]+)"', rules)]
i = order.index("st_t1")
check("T1, then T1-H, then T1-M", order[i:i + 3], ["st_t1", "st_t1h", "st_t1m"])
check("one row each", (order.count("st_t1h"), order.count("st_t1m")), (1, 1))
check("no new section or heading", (html.count('<section id="'), "T1-H</h" in html), (SBLD.build().count('<section id="'), False))
live, _gone, _q = L.team_rows(st)
rows = {r["name"]: r for r in live}
for src, market in (("st_t1h", "Home 2+"), ("st_t1m", "Over 3.5")):
    d = rows[src]["own"]["details"]
    check(f"{src}: its fold has the entry line, exit line, record table and a closed In-sample note",
          (rows[src]["own"]["market"], "<dt>Entry</dt>" in d, "<dt>Exit</dt>" in d, "<th class=\"num\">Priced to win</th>" in d,
           '<details class="section-disclosure"><summary><b>In-sample</b>' in d, "review at 10 settled, decide at 30" in d),
          (market, True, True, True, True, True))
    check(f"{src}: Sandbox, after its own record", (rows[src]["prod"], rows[src]["a"]["n"], rows[src]["after"]), (False, 1, "st_t1"))
check("the T1-M record table reads its ledger (1 settled, 1 won, priced 0.3)",
      re.findall(r'<td class="num" data-l="[^"]+">([^<]*)</td>', rows["st_t1m"]["own"]["details"]), ["1", "1", "0.3", f"{m['profit']:+.1f}%", "0"])
check("no guarded phrase in the copy", sandbox_audit.COPY_RE.search(rows["st_t1h"]["own"]["details"] + rows["st_t1m"]["own"]["details"]
                                                                     + str(TR.SIBLINGS)), None)

print(f"\n{'ALL PASS' if not FAILS else str(len(FAILS)) + ' FAILED'}")
sys.exit(1 if FAILS else 0)
