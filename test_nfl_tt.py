#!/usr/bin/env python3
"""Offline checks for nfl_tt_over_3545 / nfl_tt_over_main (nfl_tt.py) and their NFL page rows."""
import datetime as dt
import sys

import lane_windows as W
import nfl_tt as N
import nfl_tt_build as NB
import sandbox_audit

FAILS = []
UTC = dt.timezone.utc
# Sun Oct 25 2026, 13:00 ET kickoff = 17:00 UTC; now is 60 minutes before.
KO = dt.datetime(2026, 10, 25, 17, 0, tzinfo=UTC)
NOW = KO - dt.timedelta(minutes=60)


def check(label, got, want):
    ok = got == want
    print(f"  {'ok  ' if ok else 'FAIL'} {label}" + ("" if ok else f" (got {got!r}, want {want!r})"))
    if not ok:
        FAILS.append(label)


def game(away="WSH", home="SF", start=KO, gid="1", valid=True, state="pre", week="2026-2-W07"):
    return dict(id=gid, start=start.strftime("%Y-%m-%dT%H:%MZ"), valid=valid, state=state,
                away=away, home=home, week=week)


def rung(tag, team, line, bid, ask, status="active", size="250.00"):
    return dict(ticker=f"{tag}-{team}{int(line + 0.5)}", floor_strike=line, strike_type="greater", status=status,
                yes_sub_title=f"{team} over {line} points", yes_bid_dollars=None if bid is None else f"{bid:.4f}",
                yes_ask_dollars=None if ask is None else f"{ask:.4f}", yes_ask_size_fp=size)


def event(codes="WASSF", day="26OCT25", ladders=None):
    tag = f"KXNFLTEAMTOTAL-{day}{codes}"
    ladders = ladders if ladders is not None else {
        "WAS": {17.5: (0.66, 0.68), 20.5: (0.52, 0.54), 24.5: (0.38, 0.40), 27.5: (0.30, 0.32)},
        "SF": {21.5: (0.61, 0.63), 24.5: (0.49, 0.51), 28.5: (0.41, 0.43), 31.5: (0.27, 0.29)},
    }
    return dict(event_ticker=tag, title="Washington vs San Francisco: Team Total",
                markets=[rung(tag, t, ln, *q) for t, lad in ladders.items() for ln, q in lad.items()])


def lad(pairs):
    """[(strike, market, bid, ask)] from {strike: (bid, ask)}."""
    return [(s, dict(ticker=f"X-T{int(s + 0.5)}"), b, a) for s, (b, a) in sorted(pairs.items())]


print("band 35-45c: 0.35 inclusive, 0.45 exclusive")
for ask, want in ((0.34, False), (0.35, True), (0.40, True), (0.44, True), (0.45, False), (0.46, False)):
    check(f"ask {ask:.2f}", N.in_band(ask), want)

print("\ncheapest in-band rung per team")
r = N.pick_band(lad({24.5: (0.42, 0.44), 27.5: (0.34, 0.36), 30.5: (0.24, 0.26)}))
check("the lowest ask in band (0.36 at 27.5)", r[0], 27.5)
r = N.pick_band(lad({24.5: (0.43, 0.45), 27.5: (0.31, 0.34)}))
check("0.45 and 0.34 are both out: no pick", r, None)
r = N.pick_band(lad({24.5: (0.33, 0.35)}))
check("0.35 exactly is in", r[0], 24.5)
r = N.pick_band([(27.5, dict(ticker="X-T28"), 0.36, 0.38), (24.5, dict(ticker="X-T25"), 0.36, 0.38)])
check("a tie on the ask goes to the lower ticker (strike)", r[0], 24.5)

print("\nmain line: mid nearest 0.50, tie to the lower strike")
r = N.pick_main(lad({20.5: (0.55, 0.57), 23.5: (0.48, 0.50), 26.5: (0.39, 0.41)}))
check("mid 0.49 beats 0.56 and 0.40", r[0], 23.5)
r = N.pick_main(lad({20.5: (0.51, 0.53), 23.5: (0.47, 0.49)}))
check("mids 0.52 and 0.48 tie: the lower strike", r[0], 20.5)
check("an empty ladder: no pick", N.pick_main([]), None)

print("\none market, one lane: the overlap hand-off")
ladder = lad({20.5: (0.56, 0.59), 23.5: (0.43, 0.44), 26.5: (0.30, 0.33)})
band = N.pick_band(ladder)
check("3545 takes the 0.44 rung", band[0], 23.5)
check("its mid 0.435 is also nearest 50c", N.pick_main(ladder)[0], 23.5)
check("so the main line takes the next nearest (mid 0.575)", N.pick_main(ladder, band)[0], 20.5)
p = N.picks_for(event(ladders={"WAS": {20.5: (0.56, 0.59), 23.5: (0.43, 0.44), 26.5: (0.30, 0.33)}}), game(), NOW)
check("in a run the two lanes never share a ticker",
      ({x["ticker"] for x in p[N.LANE_BAND]} & {x["ticker"] for x in p[N.LANE_MAIN]}), set())

print("\nteams from the ticker suffix, and the ESPN <-> Kalshi codes")
g = game()
check("...-SF15 is SF", N.team_of("KXNFLTEAMTOTAL-26OCT19WASSF-SF15", g), "SF")
check("...-WAS21 is ESPN's WSH", N.team_of("KXNFLTEAMTOTAL-26OCT19WASSF-WAS21", g), "WSH")
check("...-WSH21 is WSH too", N.team_of("KXNFLTEAMTOTAL-26OCT19WSHSF-WSH21", g), "WSH")
check("a team not in the game is nobody", N.team_of("KXNFLTEAMTOTAL-26OCT19WASSF-KC21", g), None)
check("a suffix without a strike is nobody", N.team_of("KXNFLTEAMTOTAL-26OCT19WASSF-SF", g), None)
check("LAR reads Kalshi LA and LAR", N.codes("LAR"), {"LAR", "LA"})
check("JAX reads Kalshi JAC and JAX", N.codes("JAX"), {"JAX", "JAC"})
check("WSH reads Kalshi WAS and WSH", N.codes("WSH"), {"WSH", "WAS"})
check("the tag splits into date and codes", N.event_tag("KXNFLTEAMTOTAL-26OCT19WASSF"),
      (dt.date(2026, 10, 19), "WASSF"))
check("away+home order matches", N.fits(event("WASSF"), game()), True)
check("home+away order matches", N.fits(event("SFWAS"), game()), True)
check("ESPN code in the tag matches too", N.fits(event("WSHSF"), game()), True)
check("LA / JAC aliases", (N.fits(event("LAJAC"), game("LAR", "JAX")), N.fits(event("JACLA"), game("LAR", "JAX"))),
      (True, True))
check("another pair does not", N.fits(event("WASDAL"), game()), False)
check("the date is the ET date (00:15Z Mon is Sunday night)",
      N.fits(event(day="26OCT25"), game(start=dt.datetime(2026, 10, 26, 0, 15, tzinfo=UTC))), True)
check("so the UTC date does not match",
      N.fits(event(day="26OCT26"), game(start=dt.datetime(2026, 10, 26, 0, 15, tzinfo=UTC))), False)
check("ladders split per team (ESPN codes)", sorted(N.ladders(event(), game())), ["SF", "WSH"])

print("\nentry window: 45-75 minutes before kickoff, inclusive")
for mins, want in ((44, False), (45, True), (60, True), (75, True), (76, False), (-5, False)):
    check(f"{mins} min before", [x["id"] for x in N.due([game(start=NOW + dt.timedelta(minutes=mins))], NOW)],
          ["1"] if want else [])
check("an invalid time is never due", N.due([game(valid=False)], NOW), [])
check("a started game is never due", N.due([game(state="in")], NOW), [])
check("lane_windows copies the window", (W.NFL_TO, W.NFL_FROM), N.WINDOW_MIN)
wins = W.nfl_windows(NOW, [KO])
check("one window per kickoff, K-75 to K-45", (wins[0]["start"], wins[0]["end"]),
      (KO - dt.timedelta(minutes=75), KO - dt.timedelta(minutes=45)))
check("its stamp file", W.STAMP["nfl_tt"], "data/nfl_tt_window/request.txt")
check("windows() with no kickoffs adds no NFL window (offline)",
      [w for w in W.windows(NOW) if w["lane"] == "nfl_tt"], [])
lines = W.stamp_lines(KO - dt.timedelta(minutes=70), ledger={}, games=[], fixtures=[], nfl=[KO])
check("a read is asked for 70 min before", lines.get("data/nfl_tt_window/request.txt"), f"nfl_tt {KO.isoformat()} read 1")
lines = W.stamp_lines(KO - dt.timedelta(minutes=58), ledger={}, games=[], fixtures=[], nfl=[KO])
check("a second read at 58 min before", lines.get("data/nfl_tt_window/request.txt"), f"nfl_tt {KO.isoformat()} read 2")
lines = W.stamp_lines(KO - dt.timedelta(minutes=50), ledger={}, games=[], fixtures=[], nfl=[KO])
check("no ask inside the last 10 minutes of the window", "data/nfl_tt_window/request.txt" in lines, False)
check("the VPS script accepts the stamp path",
      "data/nfl_tt_window/request.txt" in open("scripts/vps_window_requests.sh").read(), True)
check("the workflow listens on the stamp", "data/nfl_tt_window/**" in open(".github/workflows/nfl-tt.yml").read(), True)

print("\nspread: two-sided, 5c or less")
check("5c spread counts", N.quote(rung("X", "SF", 24.5, 0.40, 0.45)), (0.40, 0.45))
check("6c spread does not", N.quote(rung("X", "SF", 24.5, 0.38, 0.44)), None)
check("no bid does not", N.quote(rung("X", "SF", 24.5, None, 0.44)), None)
check("a zero bid does not", N.quote(rung("X", "SF", 24.5, 0.0, 0.04)), None)
e = event(ladders={"SF": {24.5: (0.36, 0.42), 28.5: (0.39, 0.41)}})
p = N.picks_for(e, game(), NOW)
check("a wide in-band rung is never picked: the tight one is", [x["line"] for x in p[N.LANE_BAND]], [28.5])
check("a wide rung is not in the baseline either", [x["line"] for x in p[N.BASE]], [28.5])
check("no depth floor: a 1-contract ask still enters",
      N.picks_for(dict(event(ladders={}), markets=[rung("KXNFLTEAMTOTAL-26OCT25WASSF", "SF", 28.5, 0.41, 0.43, size="1.00")]),
                  game(), NOW)[N.LANE_BAND][0]["ask_size"], 1.0)
check("a whole-number strike is not a rung", N.strike(dict(floor_strike=24.0, strike_type="greater")), None)
check("a settled rung is skipped",
      N.ladders(dict(e, markets=[dict(m, status="settled") for m in e["markets"]]), game()), {})

print("\none frozen entry per lane per team per game")
state = N.empty()
evs = [event()]
fetch_open = lambda path: {"events": evs} if path.startswith("events") else {"market": {"status": "active"}}
log1 = N.run(state, [game()], NOW, fetch=fetch_open)
log2 = N.run(state, [game()], NOW + dt.timedelta(minutes=10), fetch=fetch_open)
check("entered once: 2 teams x 2 lanes", (len(log1), len(log2)), (4, 0))
band = {p["team"]: p for p in state["rules"][N.LANE_BAND]["picks"]}
main = {p["team"]: p for p in state["rules"][N.LANE_MAIN]["picks"]}
check("3545: WSH 24.5 @0.40, SF 28.5 @0.43", ((band["WSH"]["line"], band["WSH"]["price"]), (band["SF"]["line"], band["SF"]["price"])),
      ((24.5, 0.40), (28.5, 0.43)))
check("main: WSH 20.5 (mid .53), SF 24.5 (mid .50)", (main["WSH"]["line"], main["SF"]["line"]), (20.5, 24.5))
check("ids are lane:event:team", band["SF"]["id"], f"{N.LANE_BAND}:{evs[0]['event_ticker']}:SF")
check("week recorded", band["SF"]["week"], "2026-2-W07")
check("lead time recorded", band["SF"]["lead_min"], 60.0)
check("baseline: every quoted rung once", len(state["rules"][N.BASE]["picks"]), 8)
check("schedule written", state["schedule"], [KO.isoformat()])
check("one Kalshi event per game: two candidates skip it", N.find_event(game(), [event(), event("SFWAS")]), None)

print("\nsettlement on Kalshi's result, after the 7% fee")
def fetch_settled(result):
    def f(path):
        if path.startswith("events"):
            return {"events": []}
        if result == "fair":
            return {"market": {"status": "settled", "result": "", "settlement_value_dollars": "0.5000"}}
        return {"market": {"status": "settled", "result": result}}
    return f
p0 = band["SF"]
for result, status, profit in (("yes", "won", round(100 * (1 / (0.43 + 0.07 * 0.43 * 0.57) - 1), 2)),
                               ("no", "lost", -100.0),
                               ("fair", "no_result", round(100 * (0.5 / (0.43 + 0.07 * 0.43 * 0.57) - 1), 2))):
    s = N.empty()
    s["rules"][N.LANE_BAND]["picks"].append(dict(p0, status="open"))
    N.run(s, [], NOW + dt.timedelta(hours=5), fetch=fetch_settled(result))
    q = s["rules"][N.LANE_BAND]["picks"][0]
    check(f"{result}: {status} at {profit}", (q["status"], q["profit"]), (status, profit))
check("the fee is 0.07 p (1 - p)", round(N.fee(0.40), 6), round(0.07 * 0.40 * 0.60, 6))

print("\nstats clustered by NFL week")
rows = ([dict(price=0.4, status="won", week="W1", profit=140.0)] * 4 + [dict(price=0.4, status="lost", week="W2", profit=-100.0)] * 4)
a = N.stats(rows)
check("n, won, weeks", (a["n"], a["won"], a["weeks"]), (8, 4, 2))
clus = (4 * 0.6) ** 2 + (4 * -0.4) ** 2
check("the clustered variance (sum of squared week residuals) sets the z", round(a["z"], 6),
      round((4 - 3.2) / clus ** 0.5, 6))
check("which is weaker than the independent z here", abs(a["z"]) < abs(a["z_iid"]), True)
mixed = [dict(price=0.4, status=s, week="W1") for s in ("won", "lost", "won", "lost", "lost")]
a = N.stats(mixed)
check("a week whose residuals cancel never beats the independent variance", round(a["z"], 6), round(a["z_iid"], 6))
a = N.stats([dict(price=0.4, status="won", profit=140.0, week="W1"), dict(price=0.4, status="no_result", profit=-10.0, week="W1"),
             dict(price=0.4, status="open", week="W2")])
check("stats: n, no result, open", (a["n"], a["n_price"], a["open"]), (1, 1, 1))
check("ROI over every settled entry", round(a["roi_fee"], 4), round(130 / 200, 4))
check("a missing week falls back to the ET Tue-Mon week",
      (N.week_of(game(week=None, start=dt.datetime(2026, 10, 23, 0, 15, tzinfo=UTC))),
       N.week_of(game(week=None, start=dt.datetime(2026, 10, 27, 0, 15, tzinfo=UTC)))),
      ("wk-2026-10-20", "wk-2026-10-20"))
espn = {"events": [{"id": "77", "date": "2026-10-23T00:15Z", "shortName": "NE @ CHI", "week": {"number": 7},
                    "season": {"type": 2, "year": 2026},
                    "competitions": [{"date": "2026-10-23T00:15Z", "timeValid": True, "status": {"type": {"state": "pre"}},
                                      "competitors": [{"homeAway": "home", "team": {"abbreviation": "CHI"}},
                                                      {"homeAway": "away", "team": {"abbreviation": "NE"}}]}]}]}
got = N.espn_games(NOW, fetch=lambda url: espn)
check("ESPN: deduped across day pages, codes and week key", [(x["id"], x["away"], x["home"], x["week"]) for x in got],
      [("77", "NE", "CHI", "2026-2-W07")])

print("\nthe NFL page rows")
s = N.empty()
s["rules"][N.LANE_BAND]["picks"] = [dict(band["SF"], status="won", profit=120.0), dict(band["WSH"], status="open")]
for lane in N.LANES:
    row = NB.row_html(lane, s)
    check(f"{lane}: named as registered", N.NAMES[lane] in row and f'data-source="{lane}"' in row, True)
    check(f"{lane}: a Sandbox rule row", 'data-stage="sandbox"' in row and 'class="sp-rule' in row, True)
row = NB.row_html(N.LANE_BAND, s)
check("record and evidence cells", ('data-l="Record">1–0' in row, 'data-l="Evidence">1/30' in row), (True, True))
check("the pre-registered text is in the details", "72/144" in row and "2026-10-21" in row and "16/22" in row, True)
check("the main line's text", "100/185" in NB.row_html(N.LANE_MAIN, s) and "27/42" in NB.row_html(N.LANE_MAIN, s), True)
empty = ('<section id="rules" class="sp-section"><div class="sp-section-head"><h2>Rules</h2>'
         '<span class="sm mut">1 in Production · 0 in the Sandbox</span></div>'
         '<p class="sp-empty" data-empty="sandbox">No nfl rule is in the Sandbox.</p></section><footer>')
out = NB.place(empty, s)
check("the empty NFL Sandbox gets a list with both rows",
      ('data-list="sandbox"' in out, "sp-empty" in out, out.count('<details class="sp-rule')), (True, False, 2))
check("the fold counts them, too early", "· 2 rules · 2 too early to read · by evidence" in out, True)
check("the Rules head counts them", "1 in Production · 2 in the Sandbox" in out, True)
check("3545 first, then the main line", out.index(N.NAMES[N.LANE_BAND]) < out.index(N.NAMES[N.LANE_MAIN]), True)
page = ('<section id="rules"><details class="fold sp-sandbox" id="sandbox"><summary><h3>Sandbox rules</h3>'
        '<span class="sm mut">· 3 rules · 1 too early to read · by evidence</span></summary><div class="sp-rules-list" data-list="sandbox">'
        '<div class="sp-line sp-head-line"></div><details class="sp-rule"><summary></summary>'
        '<div class="sp-details-body"></div></details></div></details></section><footer></footer>')
out = NB.place(page, s)
check("an existing list: appended, counts bumped", "· 5 rules · 3 too early to read · by evidence" in out
      and out.index(N.NAMES[N.LANE_BAND]) < out.index("</section>"), True)
import nfl_build
built = nfl_build.build()
check("the built NFL page carries both rows", all(f'data-source="{x}"' in built for x in N.LANES), True)
check("no guarded phrase in the lanes' copy",
      sandbox_audit.COPY_RE.search(NB.row_html(N.LANE_BAND, s) + NB.row_html(N.LANE_MAIN, s)
                                   + open("nfl_tt.py").read() + open("nfl_tt_build.py").read()), None)

print("\nSandbox only")
import sandbox_sources as S
for lane in N.LANES:
    check(f"{lane} is not a Sandbox-ledger source", lane in S.SOURCES, False)
    check(f"{lane} is not in the Production overrides", lane in open("production.py").read(), False)

print()
if FAILS:
    print(f"{len(FAILS)} FAILED: {FAILS}")
    sys.exit(1)
print("all ok")
