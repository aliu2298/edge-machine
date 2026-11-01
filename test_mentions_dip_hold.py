#!/usr/bin/env python3
"""mentions_dip_hold (2026-11-01): the pre-registered rule, the held fill, the record by week, the incremental read, the page card."""
import datetime as dt
import sys

import culture_build
import mentions_dip_hold as M
import mentions_dip_hold_build as B
import mentions_split as MS
import sandbox_audit

FAILS = []


def check(label, got, want):
    ok = got == want
    print(f"  {'ok  ' if ok else 'FAIL'} {label}" + ("" if ok else f" (got {got!r}, want {want!r})"))
    if not ok:
        FAILS.append(label)


OPEN = 1_800_000_000
H = 3600


def mk(first, lows, final=False, **kw):
    return dict(dict(word="W", open_ts=OPEN, first_px=first, first_ts=OPEN + 60, lows=[list(x) for x in lows], final=final), **kw)


NOW = OPEN + 10 * 86400
print("the entry: a dip buy only")
check("a word whose first trade is at or under the bid never qualifies, even if it later fills",
      M.fill_state(mk(0.10, [(OPEN + 100, 0.08, 50)]), 0.10, NOW)["state"], "no_dip")
check("a word whose first trade is above the bid and later prints 50 contracts at 9c fills", M.fill_state(mk(0.30, [(OPEN + H, 0.09, 50)]), 0.10, NOW)["state"], "filled")
check("no trade at all yet: waiting", M.fill_state(mk(None, []), 0.10, NOW)["state"], "waiting")

print("\nthe held fill: 10+ contracts at or under the bid within 60 minutes of the print")
t = OPEN + 5 * H
f = M.fill_state(mk(0.30, [(t, 0.10, 6), (t + 600, 0.09, 5)]), 0.10, NOW)
check("6 then 5 contracts inside the hour: filled at the first print, 11 contracts", (f["state"], f["fill_ts"], f["contracts"]), ("filled", t, 11))
check("6 contracts only, market final: no entry (a thin print is not a fill)", M.fill_state(mk(0.30, [(t, 0.10, 6)], final=True), 0.10, NOW)["state"], "unfilled")
check("the second 5 contracts print 61 minutes later: outside the hour, no fill",
      M.fill_state(mk(0.30, [(t, 0.10, 6), (t + H + 60, 0.10, 5)], final=True), 0.10, NOW)["state"], "unfilled")
check("a thin first print, then a later print that does reach 10: the fill is the LATER print",
      (lambda x: (x["state"], x["fill_ts"]))(M.fill_state(mk(0.30, [(t, 0.10, 3), (t + 2 * H, 0.10, 12)]), 0.10, NOW)), ("filled", t + 2 * H))
check("a thin print whose hour is still running is 'checking', not a verdict",
      M.fill_state(mk(0.30, [(NOW - 600, 0.10, 6)]), 0.10, NOW)["state"], "checking")
check("the same prints judged at 15c: a 12c print fills the 15c bid, not the 10c bid",
      (M.fill_state(mk(0.30, [(t, 0.12, 20)], final=True), 0.15, NOW)["state"], M.fill_state(mk(0.30, [(t, 0.12, 20)], final=True), 0.10, NOW)["state"]),
      ("filled", "unfilled"))

print("\nan unfilled word, and a word said before any fill")
state = dict(events={"KXTRUMPSAY-26NOV02": dict(markets={
    "A": mk(0.30, [], final=True, status="finalized", result="no", word="Unfilled"),
    "B": mk(0.40, [], final=True, status="finalized", result="yes", word="SaidFirst", close_ts=OPEN + H),
    "C": mk(0.30, [(t, 0.10, 20)], final=True, status="finalized", result="yes", word="Said"),
    "D": mk(0.30, [(t, 0.09, 20)], final=True, status="finalized", result="no", word="Missed")})})
es = M.entries(state, 0.10, NOW)
check("only the two words with a held fill are entries; the unfilled and the said-before-fill words are not", sorted(e["word"] for e in es), ["Missed", "Said"])
c = M.cost_of(0.10)
check("cost = the bid + the maker fee; settled yes pays 1, no pays 0",
      {e["word"]: round(e["roi"], 4) for e in es}, {"Said": round((1 - c) / c, 4), "Missed": -1.0})
check("the maker fee is 0.0175 p(1-p)", round(c, 5), round(0.10 + 0.0175 * 0.10 * 0.90, 5))

print("\nthe incremental read")
m = dict(word="W", open_ts=OPEN, close_ts=OPEN + 10 * H)
rows = [dict(created_time=dt.datetime.fromtimestamp(OPEN + s, dt.timezone.utc).isoformat().replace("+00:00", "Z"), yes_price_dollars=p,
             count_fp=str(n), trade_id=i) for s, p, n, i in ((-30, "0.05", 9, "pre"), (100, "0.40", 5, "a"), (200, "0.09", 7, "b"), (300, "0.50", 2, "c"),
                                                              (11 * H, "0.02", 99, "late"))]
n1 = M.ingest(m, rows)
check("a print before the open and one after the close are ignored; the first trade after the open is kept",
      (n1, m["first_px"], [p[1] for p in m["lows"]]), (3, 0.40, [0.09]))
n2 = M.ingest(m, rows)
check("reading the same rows again adds nothing (the boundary second is deduplicated)", (n2, m["n_prints"]), (0, 3))

print("\nthe record: weeks are the outcome, an unsettled week is not counted")
def week(tick, results, bid=0.10):
    return tick, dict(markets={f"{tick}-{i}": mk(0.30, [(t, 0.09, 20)], final=r is not None, status="finalized" if r is not None else "active",
                                                  result=r, word=f"w{i}") for i, r in enumerate(results)})
st2 = dict(events=dict([week("KXTRUMPSAY-26NOV02", ["yes", "no", "no"]), week("KXTRUMPSAY-26NOV09", ["no", "no"]),
                        week("KXTRUMPSAY-26NOV16", ["no", None])]))
r = M.record(st2, 0.10, NOW)
check("3 weeks entered, 2 settled (the third still has an unsettled word), 7 entries, 2 of them... won once",
      (r["events"], r["settled_events"], r["entries"], r["open"], r["won"], r["settled"]), (3, 2, 7, 1, 1, 5))
check("ROI is the mean over the entries of settled weeks; z needs 3 settled weeks", (round(r["roi"], 4), r["z"]),
      (round((1 * (1 - c) / c + 4 * -1.0) / 5, 4), None))
st3 = dict(events=dict([week("KXTRUMPSAY-26NOV02", ["yes", "no"]), week("KXTRUMPSAY-26NOV09", ["no", "no"]), week("KXTRUMPSAY-26NOV16", ["yes", "no"])]))
check("with 3 settled weeks z is a number and weeks up counts the weeks above 0", (M.record(st3, 0.10, NOW)["z"] is not None, M.record(st3, 0.10, NOW)["up"]), (True, 2))
check("the 15c line is judged on the same words", M.record(st3, 0.15, NOW)["entries"], 6)

print("\nthe run: fresh from the week of 26NOV02, one read per open market, a settled market is read once more then never")
EV, OLD = "KXTRUMPSAY-26NOV02", "KXTRUMPSAY-26OCT26"
iso = lambda s: dt.datetime.fromtimestamp(s, dt.timezone.utc).isoformat().replace("+00:00", "Z")
START = M._ts(M.START)
calls = []


def market(ev, w, open_s, status="active", result=""):
    return dict(ticker=f"{ev}-{w}", event_ticker=ev, open_time=iso(open_s), close_time=iso(START + 9 * 86400), status=status, result=result,
                custom_strike=dict(Word=w), yes_sub_title=w)


def fake(path):
    calls.append(path)
    if path.startswith("events?"):
        return dict(events=[dict(event_ticker=EV, markets=[market(EV, "AAA", START), market(EV, "BBB", START, "finalized", "yes")]),
                            dict(event_ticker=OLD, markets=[market(OLD, "OLD", START - 7 * 86400)])])
    if path.startswith("markets/trades"):
        return dict(trades=[dict(created_time=iso(START + 600), yes_price_dollars="0.40", count_fp="5", trade_id="x1"),
                            dict(created_time=iso(START + 4000), yes_price_dollars="0.08", count_fp="30", trade_id="x2")])
    raise AssertionError(path)


st = M.load("/nonexistent")
M.run(st, dt.datetime.fromtimestamp(START + 86400, dt.timezone.utc), fake)
check("only the week opened on or after the lane's start is read", sorted(st["events"]), [EV])
check("both words filled at 10c; BBB (settled yes) is final, AAA is not", (M.record(st, 0.10, START + 86400)["entries"], st["events"][EV]["markets"][f"{EV}-BBB"].get("final"),
      st["events"][EV]["markets"][f"{EV}-AAA"].get("final")), (2, True, None))
n = len([c for c in calls if c.startswith("markets/trades")])
M.run(st, dt.datetime.fromtimestamp(START + 90000, dt.timezone.utc), fake)
check("the next read fetches trades for the open word only, with min_ts (incremental)",
      (len([c for c in calls if c.startswith("markets/trades")]) - n, "min_ts=" in calls[-1]), (1, True))

print("\nthe page card")
html = culture_build.build(dip_state=st)
check("on the Culture page, above the cheap-side lanes, with its pill", (html.find('id="dip-hold"') > 0, html.find('id="dip-hold"') < html.find('id="lanes"'),
      'href="#dip-hold"' in html), (True, True, True))
card = html[html.find('<section id="dip-hold"'):html.find('<section id="lanes"')]
check("labelled, rule in one line, 10c headline then 15c comparison", ("Trump mentions · 10c dip bid, hold" in card, card.find("10c bid · hold") < card.find("15c bid · hold")), (True, True))
check("the research is a collapsed fold marked in-sample", ('id="dip-research"' in card, "<details class=\"fold sm\" id=\"dip-research\">" in card, "in-sample" in card), (True, True, True))
check("this week's entries list both bids, with contracts at the fill", ("Contracts at 10c fill" in card, "Contracts at 15c fill" in card), (True, True))
check("no inline style or SVG; public copy passes the guard", ("style=" in card, "<svg" in card, sandbox_audit.COPY_RE.search(card)), (False, False, None))

print("\n" + ("ALL PASS" if not FAILS else f"{len(FAILS)} FAILED"))
sys.exit(1 if FAILS else 0)
