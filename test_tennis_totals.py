#!/usr/bin/env python3
"""Offline checks for tennis_atp_low_over (tennis_totals.py) and its Tennis page row."""
import datetime as dt
import sys

import lane_windows as W
import sandbox_audit
import tennis_totals as TT
import tennis_totals_build as TB

FAILS = []
UTC = dt.timezone.utc
NOW = dt.datetime(2026, 10, 21, 9, 0, tzinfo=UTC)
START = NOW + dt.timedelta(minutes=30)


def check(label, got, want):
    ok = got == want
    print(f"  {'ok  ' if ok else 'FAIL'} {label}" + ("" if ok else f" (got {got!r}, want {want!r})"))
    if not ok:
        FAILS.append(label)


def match(a="Francisco Cerundolo", b="Martin Damm", start=START, mid="1", valid=True, state="pre"):
    return dict(id=mid, start=start.strftime("%Y-%m-%dT%H:%MZ"), valid=valid, state=state,
                players=[a, b], tournament="European Open")


def rung(tag, line, bid, ask, status="active", rules="2026 ATP Brussels Round Of 32", size="500.00"):
    return dict(ticker=f"{tag}-{int(line + 0.5)}", floor_strike=line, strike_type="greater", status=status,
                yes_sub_title=f"Over {line} games", yes_bid_dollars=None if bid is None else f"{bid:.4f}",
                yes_ask_dollars=None if ask is None else f"{ask:.4f}", yes_ask_size_fp=size,
                rules_secondary=f"The following market refers to the match in the {rules}.")


def event(a="Martin Damm Jr", b="Francisco Cerundolo", day="26OCT21", ladder=None, series="KXATPGTOTAL", rules=None):
    tag = f"{series}-{day}{a.split()[-1][:3].upper()}{b.split()[-1][:3].upper()}"
    ladder = ladder if ladder is not None else {18.5: (0.80, 0.84), 23.5: (0.45, 0.47), 28.5: (0.21, 0.26)}
    kw = {"rules": rules} if rules else {}
    return dict(event_ticker=tag, title=f"{a} vs {b}: Total Games",
                markets=[rung(tag, ln, *q, **kw) for ln, q in ladder.items()])


print("rung: the highest strike at or below 19.5")
e = event(ladder={19.5: (0.71, 0.74), 24.5: (0.43, 0.45), 14.5: (0.95, 0.97)})
check("19.5 is taken when listed", TT.low_rung(e)[0], 19.5)
e = event(ladder={18.5: (0.80, 0.84), 23.5: (0.45, 0.47)})
check("else 18.5", TT.low_rung(e)[0], 18.5)
e = event(ladder={16.5: (0.89, 0.92), 21.5: (0.49, 0.50)})
check("else 16.5", TT.low_rung(e)[0], 16.5)
e = event(ladder={20.5: (0.70, 0.72), 25.5: (0.40, 0.42)})
check("nothing above 19.5: no rung", TT.low_rung(e), None)
check("a 20.5 rung is never an entry", TT.picks_for(e, match(), NOW), (None, []))
e = event(ladder={19.5: (0.60, 0.62), 14.5: (0.86, 0.88)})
lane, base = TT.picks_for(e, match(), NOW)
check("no fall back to a lower rung when 19.5 is out of band", lane, None)
check("the baseline still takes the in-band 14.5", [p["line"] for p in base], [14.5])
e = event(ladder={19.5: (0.71, 0.74), 18.5: (0.80, 0.83)})
check("a settled 19.5 rung is skipped for the live 18.5",
      TT.low_rung(dict(e, markets=[dict(m, status="settled") if m["floor_strike"] == 19.5 else m
                                   for m in e["markets"]]))[0], 18.5)
check("a whole-number strike is not a rung", TT.strike(dict(floor_strike=19.0, strike_type="greater")), None)
check("the line can come from the title", TT.strike(dict(yes_sub_title="Over 18.5 games")), 18.5)

print("\nprice band 0.70-0.92, both ends inclusive")
for ask, want in ((0.69, False), (0.70, True), (0.84, True), (0.92, True), (0.93, False)):
    check(f"ask {ask:.2f}", TT.in_band(ask), want)
for ask, want in ((0.70, True), (0.92, True), (0.93, False), (0.69, False)):
    e = event(ladder={18.5: (round(ask - 0.03, 2), ask)})
    check(f"entry at ask {ask:.2f}", TT.picks_for(e, match(), NOW)[0] is not None, want)

print("\nspread: two-sided, 5c or less")
check("5c spread enters", TT.quote(rung("X", 18.5, 0.79, 0.84)), (0.79, 0.84))
check("6c spread does not", TT.quote(rung("X", 18.5, 0.78, 0.84)), None)
check("no bid does not", TT.quote(rung("X", 18.5, None, 0.84)), None)
check("a zero bid does not", TT.quote(rung("X", 18.5, 0.0, 0.84)), None)
check("an ask of 1 does not", TT.quote(rung("X", 18.5, 0.97, 1.0)), None)
check("no depth floor: a 1-contract ask still enters",
      TT.picks_for(event(ladder={18.5: (0.80, 0.84)}) | {}, match(), NOW)[0] is not None
      and TT.picks_for(dict(event(), markets=[dict(m, yes_ask_size_fp="1.00") for m in event()["markets"]]),
                       match(), NOW)[0]["ask_size"] == 1.0, True)

print("\nentry window: 15-45 minutes before the ESPN start, inclusive")
for mins, want in ((14, False), (15, True), (30, True), (45, True), (46, False), (-5, False)):
    check(f"{mins} min before", [m["id"] for m in TT.due([match(start=NOW + dt.timedelta(minutes=mins))], NOW)],
          ["1"] if want else [])
check("a placeholder start (timeValid false) is never due", TT.due([match(valid=False)], NOW), [])
check("a started match is never due", TT.due([match(state="in")], NOW), [])
check("a TBD player is never due", TT.due([match(b="TBD")], NOW), [])
check("lane_windows copies the window", (W.TENNIS_TO, W.TENNIS_FROM), TT.WINDOW_MIN)
wins = W.tennis_windows(NOW, [START])
check("one window per start, K-45 to K-15", (wins[0]["start"], wins[0]["end"]),
      (START - dt.timedelta(minutes=45), START - dt.timedelta(minutes=15)))
check("its stamp file", W.STAMP["tennis_totals"], "data/tennis_totals_window/request.txt")
check("windows() with no starts adds no tennis window (offline)",
      [w for w in W.windows(NOW) if w["lane"] == "tennis_totals"], [])
lines = W.stamp_lines(START - dt.timedelta(minutes=40), ledger={}, games=[], fixtures=[], tennis=[START])
check("a read is asked for 40 min before",
      lines.get("data/tennis_totals_window/request.txt"), f"tennis_totals {START.isoformat()} read 1")
lines = W.stamp_lines(START - dt.timedelta(minutes=20), ledger={}, games=[], fixtures=[], tennis=[START])
check("no ask inside the last 10 minutes of the window", "data/tennis_totals_window/request.txt" in lines, False)
check("the VPS script accepts the stamp path",
      "data/tennis_totals_window/request.txt" in open("scripts/vps_window_requests.sh").read(), True)

print("\nATP only: KXATPGTOTAL, no Challenger, singles only")
check("an ATP event is in scope", TT.atp_event(event()), True)
check("a WTA total series is not", TT.atp_event(event(series="KXWTAGTOTAL")), False)
check("a Challenger event is not", TT.atp_event(event(rules="2026 ATP Challenger Lyon Round Of 32")), False)
check("the series is KXATPGTOTAL", TT.SERIES, "KXATPGTOTAL")
espn = {"events": [{"name": "European Open", "groupings": [
    {"grouping": {"slug": "mens-singles"}, "competitions": [
        {"id": "9", "startDate": "2026-10-21T09:30Z", "timeValid": True, "status": {"type": {"state": "pre"}},
         "type": {"slug": "mens-singles"},
         "competitors": [{"athlete": {"displayName": "Francisco Cerundolo"}}, {"athlete": {"displayName": "Martin Damm"}}]}]},
    {"grouping": {"slug": "mens-doubles"}, "competitions": [
        {"id": "10", "startDate": "2026-10-21T09:30Z", "timeValid": True, "status": {"type": {"state": "pre"}},
         "type": {"slug": "mens-doubles"}, "competitors": [{}, {}]}]}]}]}
got = TT.espn_matches(NOW, fetch=lambda url: espn)
check("ESPN: men's singles only, deduped across the two day pages", [(m["id"], m["players"]) for m in got],
      [("9", ["Francisco Cerundolo", "Martin Damm"])])

print("\nmatching an ESPN match to its Kalshi event")
check("Martin Damm Jr is Martin Damm", TT.same_player("Martin Damm Jr", "Martin Damm"), True)
check("Francisco is not Juan Manuel Cerundolo", TT.same_player("Francisco Cerundolo", "Juan Manuel Cerundolo"), False)
check("accents and hyphens", TT.same_player("Felix Auger-Aliassime", "Félix Auger Aliassime"), True)
e = event()
check("found either way round", TT.find_event(match(), [e]) is e, True)
check("a postponed listing (Oct 18 ticker, Oct 21 start) still matches",
      TT.find_event(match(), [event(day="26OCT18")]) is not None, True)
check("a listing from another week does not", TT.find_event(match(), [event(day="26OCT08")]), None)
check("two events for one match: skipped", TT.find_event(match(), [e, event(day="26OCT20")]), None)

print("\none frozen entry per match")
state = TT.empty()
evs = [event()]
fetch_open = lambda path: {"events": evs} if path.startswith("events") else {"market": {"status": "active"}}
log1 = TT.run(state, [match()], NOW, fetch=fetch_open)
log2 = TT.run(state, [match()], NOW + dt.timedelta(minutes=10), fetch=fetch_open)
check("entered once", (len(log1), len(log2)), (1, 0))
p = state["rules"][TT.LANE]["picks"][0]
check("the entry is the 18.5 YES at the ask", (p["line"], p["side"], p["price"], p["id"]),
      (18.5, "yes", 0.84, f"{TT.LANE}:{e['event_ticker']}"))
check("lead time recorded", p["lead_min"], 30.0)
check("baseline logged once per rung", len(state["rules"][TT.BASE]["picks"]), 1)
check("schedule written", state["schedule"], [START.isoformat()])

print("\nsettlement on Kalshi's result, after the 7% fee")
def fetch_settled(result):
    def f(path):
        if path.startswith("events"):
            return {"events": []}
        if result == "fair":
            return {"market": {"status": "settled", "result": "", "settlement_value_dollars": "0.6000"}}
        return {"market": {"status": "settled", "result": result}}
    return f
for result, status, profit in (("yes", "won", round(100 * (1 / (0.84 + 0.07 * 0.84 * 0.16) - 1), 2)),
                               ("no", "lost", -100.0),
                               ("fair", "no_result", round(100 * (0.6 / (0.84 + 0.07 * 0.84 * 0.16) - 1), 2))):
    s = TT.empty()
    s["rules"][TT.LANE]["picks"].append(dict(p, status="open"))
    TT.run(s, [], NOW + dt.timedelta(hours=3), fetch=fetch_settled(result))
    q = s["rules"][TT.LANE]["picks"][0]
    check(f"{result}: {status} at {profit}", (q["status"], q["profit"]), (status, profit))
check("the fee is 0.07 p (1 - p)", round(TT.fee(0.84), 6), round(0.07 * 0.84 * 0.16, 6))
a = TT.stats([dict(price=0.84, status="won", profit=10.0), dict(price=0.80, status="lost", profit=-100.0),
              dict(price=0.84, status="no_result", profit=-30.0), dict(price=0.85, status="open")])
check("stats: n, no result, won, open", (a["n"], a["n_price"], a["won"], a["open"]), (2, 1, 1, 1))
check("stats: ROI over every settled entry", round(a["roi_fee"], 4), round(-120 / 300, 4))

print("\nthe Tennis page row")
s = TT.empty()
s["rules"][TT.LANE]["picks"] = [dict(p, status="won", profit=10.5), dict(p, id="x", status="open")]
row = TB.row_html(s)
check("named as registered", TB.NAME in row and f'data-source="{TT.LANE}"' in row, True)
check("a Sandbox rule row", 'data-stage="sandbox"' in row and 'class="sp-rule' in row, True)
check("record and evidence cells", ('data-l="Record">1–0' in row, 'data-l="Evidence">1/30' in row), (True, True))
check("the pre-registered text is in the details", "59/65 (64 matches)" in row and "2026-10-21" in row, True)
page = ('<section id="rules"><details class="fold sp-sandbox" id="sandbox"><summary><h3>Sandbox rules</h3>'
        '<span class="sm mut">· 7 rules · by evidence</span></summary><div class="sp-rules-list" data-list="sandbox">'
        '<div class="sp-line sp-head-line"></div><details class="sp-rule"><summary></summary>'
        '<div class="sp-details-body"></div></details></div></details></section><footer></footer>')
out = TB.place(page, s)
check("placed at the end of the Sandbox list", out.index(TB.NAME) > out.index('<details class="sp-rule">')
      and out.index(TB.NAME) < out.index("</section>"), True)
check("the Sandbox count includes it, too early", "· 8 rules · 1 too early to read · by evidence" in out, True)
out = TB.place(page.replace("· 7 rules ·", "· 7 rules · 4 too early to read ·"), s)
check("an existing too-early count is bumped", "· 8 rules · 5 too early to read · by evidence" in out, True)
empty = '<section id="rules"><p class="sp-empty" data-empty="sandbox">No tennis rule is in the Sandbox.</p></section><footer>'
out = TB.place(empty, s)
check("a page with no Sandbox list gets one", 'data-list="sandbox"' in out and TB.NAME in out and "sp-empty" not in out, True)
check("no guarded phrase in the lane's copy",
      sandbox_audit.COPY_RE.search(row + open("tennis_totals.py").read() + open("tennis_totals_build.py").read()), None)

print("\nSandbox only")
import sandbox_sources as S
check("not a Sandbox-ledger source (no Production, no live pair)", TT.LANE in S.SOURCES, False)
check("not in the Production overrides", TT.LANE in open("production.py").read(), False)

print()
if FAILS:
    print(f"{len(FAILS)} FAILED: {FAILS}")
    sys.exit(1)
print("all ok")
