#!/usr/bin/env python3
"""Offline checks (2026-11-04, Olu): the leaderboard's active-lanes view, its team names, and the site nav.

1. Each nav link label appears once on every page. #254 put the Leaderboard in the Markets menu, so on its own page
   the menu button read "Leaderboard" beside its link; it is a top-level pill now.
2. Every NBA and NFL code a ledger writes is named (WSH showed as "WSH match"), and a game-total pick is a match bet.
3. The active-lanes view counts only lanes active now, from each engine's own registry status.
"""
import datetime as dt
import re
import sys

import leaderboard as L
import leaderboard_build as LB
import sandbox_audit
import sandbox_build as B
import site_chrome as C

FAILS = []


def check(label, got, want):
    ok = got == want
    print(f"  {'ok  ' if ok else 'FAIL'} {label}" + ("" if ok else f" (got {got!r}, want {want!r})"))
    if not ok:
        FAILS.append(label)


print("the nav: each label once on every page")
for key in ["index"] + [k for k, _l, _h in C.PAGES]:
    nav = C.nav(key)
    labels = re.findall(r"<a [^>]*>([^<]+)</a>", nav) + re.findall(r'class="nav-more"[^>]*>([^<]+)<', nav)
    check(f"{key}: no label twice (links and the Markets button)", sorted({x for x in labels if labels.count(x) > 1}), [])
lb_nav = C.nav("leaderboard")
check("on the Leaderboard page the button reads Markets, highlighted, and Leaderboard is named once and current",
      (re.findall(r'class="nav-more"[^>]*>([^<]+)<', lb_nav), "nav-group is-current" in lb_nav, len(re.findall(r">Leaderboard<", lb_nav)),
       bool(re.search(r'href="\./leaderboard\.html" aria-current="page">Leaderboard<', lb_nav))), (["Markets"], True, 1, True))
check("on a page outside the menu the button is not highlighted", "nav-group is-current" in C.nav("sandbox"), False)
check("Method is still the last pill", re.findall(r"<a [^>]*>([^<]+)</a>", lb_nav)[-1], "Method")

print("\nteam names: every NBA and NFL code a ledger writes is named")
for code in ("WSH", "WAS", "GS", "NO", "NY", "SA", "UTAH", "PHX", "LAC", "BKN"):
    check(f"NBA {code}", L.nba_name(code) != code and " " in L.nba_name(code), True)
check("WSH is the Washington Wizards", L.nba_name("WSH"), "Washington Wizards")
for code in ("ARI", "ATL", "BAL", "BUF", "CAR", "CHI", "CIN", "CLE", "DAL", "DEN", "DET", "GB", "HOU", "IND", "JAX", "KC",
             "LAC", "LAR", "LV", "MIA", "MIN", "NE", "NO", "NYG", "NYJ", "PHI", "PIT", "SEA", "SF", "TB", "TEN", "WSH"):
    check(f"NFL {code}", L.nfl_name(code) != code, True)
check("the same code in two leagues keeps its league's name", (L.nba_name("NO"), L.nfl_name("NO")),
      ("New Orleans Pelicans", "New Orleans Saints"))
bets, *_ = L.collect_bets()
for sport in ("NBA",):
    bare = sorted({n for b in bets if b["sport"] == sport for n in b["entities"] if re.fullmatch(r"[A-Z]{2,4}", n)})
    check(f"no bare {sport} code left on any bet", bare, [])
nfl_bare = sorted({n for b in bets if str(b["lane"]).startswith("nfl_tt") for n in b["entities"] if re.fullmatch(r"[A-Z]{2,4}", n)})
check("no bare NFL code left on an NFL team-total bet", nfl_bare, [])
check("a game-total pick (team 'game') is a match bet for both teams, never a name called 'game'",
      [b for b in bets if "game" in b["entities"]], [])
fixture = {"nba_rules_ledger.json": {"rules": {"R5": {"picks": [dict(id="R5:X", side="no", status="won", profit=105.0,
                                                                    team="game", match="SAC @ WSH", start="2026-10-22T02:30Z")]}}}}
got = L.collect_rule_bets({}, lambda name: fixture.get(name, {}))
check("the fixture: both teams, named, as a match", [(b["entities"], b["kind"]) for b in got],
      [(["Sacramento Kings", "Washington Wizards"], "match")])

print("\nthe active-lanes view: lanes active now, by each engine's own status")
now = dt.datetime(2026, 11, 5, 12, tzinfo=dt.timezone.utc)
stage = L.lane_stages(now)
mk = lambda **kw: dict(dict(uid=("x", "a"), lane="?", sport="Soccer", entities=["X"], day="2026-11-01", profit=0.1,  # noqa: E731
                            won=True, kind="team", src=None, scope=None), **kw)
cases = [
    ("a Production pair", mk(src="sandbox", lane="team2_ranked", scope="soccer_team2"), "Production"),
    ("its Sandbox twin", mk(src="sandbox", lane="team2_ranked", scope="soccer_team2_cup"), "Sandbox"),
    ("a retired scope (team +0.5 unbeaten, tagged RETIRED in the stamp table)", mk(src="sandbox", lane="p05_unbeaten", scope="soccer_p05_cup"), None),
    ("a retired source (Turkey over 2.5)", mk(src="sandbox", lane="turkey_o25_dog", scope="soccer_o25"), None),
    ("a tipster source", mk(src="sandbox", lane="olbg", scope="boxing"), None),
    ("a baseline source", mk(src="sandbox", lane="spot", scope="crypto"), None),
    ("a soccer rule in Production (A6)", mk(src="soccer_rules_ledger.json", lane="A6"), "Production"),
    ("a retired soccer rule (D3)", mk(src="soccer_rules_ledger.json", lane="D3"), None),
    ("a retired sa_o15 row", mk(src="sa_o15_ledger.json", lane="ARG"), None),
    ("the NFL team-total over 35-45c", mk(src="nfl_tt_ledger.json", lane="nfl_tt_over_3545"), "Sandbox"),
    ("a retired NBA rule", mk(src="nba_rules_ledger.json", lane="R1"), None),
    ("econ near-certain YES (Production)", mk(src="daily", lane="econ_nc_yes"), "Production"),
    ("finance daily (retired)", mk(src="daily", lane="finance_daily"), None),
    ("a retired culture lane", mk(src="culture", lane="mentions_rate"), None),
    ("the gas cheap NO lane", mk(src="contract", lane="gas_cheap_no_ledger.json"), "Sandbox"),
    ("WTI cheap YES (retired)", mk(src="contract", lane="wti_cheap_yes_ledger.json"), None),
    ("the boxing baseline", mk(src="contract", lane="boxing_cheap_dog_ledger.json"), None),
    ("a chaos baseline", mk(src="contract", lane="cfb_dog_tp50"), None),
    ("the over 3.5 cheap NO wave (Production)", mk(src="contract", lane="o35_cheap_no"), "Production"),
    ("an unknown source", mk(src="elsewhere", lane="x"), None),
]
for label, b, want in cases:
    check(label, stage(b), want)
check("the stamp table's RETIRED tag and the view agree: no RETIRED-tagged source is active",
      [n for n in ("p05_unbeaten", "turkey_o25_dog", "turkey_btts_dog", "o25_congestion", "tennis_fav_band_3h", "mls_away_band_fade")
       if B.source_retired(n) and any(stage(mk(src="sandbox", lane=n, scope=sc)) for sc in ("soccer_p05_cup", "soccer_o25", "soccer_btts", "tennis", "soccer_p05"))],
      [])

ab = L.active_board(bets, stage)
check("only active-lane bets are counted", (ab["bets"] + ab["left_out"], ab["bets"] < len(bets)), (len(bets), True))
check("the threshold is 5 settled bets", (L.ACTIVE_MIN_BETS, all(s["n"] >= 5 for s in ab["top"] + ab["bottom"])), (5, True))
check("top 20 and bottom 10, no name in both", (len(ab["top"]) <= 20, len(ab["bottom"]) <= 10,
                                                {s["name"] for s in ab["top"]} & {s["name"] for s in ab["bottom"]}), (True, True, set()))
check("the top is ordered by profit, the bottom from the worst", (
    [s["profit"] for s in ab["top"]] == sorted((s["profit"] for s in ab["top"]), reverse=True),
    [s["profit"] for s in ab["bottom"]] == sorted(s["profit"] for s in ab["bottom"])), (True, True))
check("every lane mark is Production or Sandbox", {st for s in ab["top"] + ab["bottom"] for _ln, st in s["lane_marks"]} <= {"Production", "Sandbox"}, True)
check("the persistence line is computed on the active bets", ab["persistence"] == L.profit_persistence(
    [b for b in bets if stage(b)]), True)

print("\nthe page: the active view first, the all-lanes view unchanged below it")
html = LB.build(now=now)
a, t, d = html.find('<section id="active"'), html.find('<section id="top"'), html.find('<section id="detail"')
check("order: active, all lanes, spike detail", 0 < a < t < d, True)
sec = html[a:t]
check("the columns", re.findall(r"<th[^>]*>([^<]+)</th>", sec)[:9],
      ["#", "Name", "Sport", "Bets", "Won", "Profit at $1 after fees", "ROI", "Profitable weeks", "Lanes"])
check("a top 20 and a bottom 10", ("<h2>Top 20</h2>" in sec, "<h2>Bottom 10</h2>" in sec), (True, True))
check("an ROI under 10 bets is greyed, and one on 10+ is not",
      (any(s["n"] < 10 for s in ab["top"]) <= ('data-l="ROI"><span class="mut">' in sec),
       any(s["n"] >= 10 for s in ab["top"]) <= bool(re.search(r'data-l="ROI">[+−-]', sec))), (True, True))
check("the persistence line says it is descriptive", "descriptive, not a pick list" in sec, True)
check("P and S marks", ('">P</span>' in sec, '">S</span>' in sec), (True, True))
check("the all-lanes view keeps its copy", "retired lanes included" in html[t:d], True)
check("no guarded phrase, no dollar balance beyond per-$1 profit", sandbox_audit.COPY_RE.search(sec), None)

print(f"\n{'ALL PASS' if not FAILS else str(len(FAILS)) + ' FAILED'}")
sys.exit(1 if FAILS else 0)
