#!/usr/bin/env python3
"""Offline checks for the Nations League dump bid (nl_dump.py, 2026-11-13): the game day and match from the ticker, the replay on a made-up
dump (fill strictly through, the sell back within 5c, the held row, the last-3-hours bid, the skip rules), which settled markets are read and
which are not, the pre-registered read at 100 and 200 fills, and a page builder that makes no venue call and uses no guarded phrase."""
import sys

import daily_track as D
import nl_dump as N
import nl_dump_build as NB
import sandbox_audit

FAILS = []


def check(label, got, want):
    ok = got == want
    print(f"  {'ok  ' if ok else 'FAIL'} {label}" + ("" if ok else f" (got {got!r}, want {want!r})"))
    if not ok:
        FAILS.append(label)


print("the ticker")
check("the game day", N.event_day("KXUEFANLTOTAL-26NOV14KOSISR"), "2026-11-14")
check("the match", N.match_of("Kosovo vs Israel: Total Goals"), "Kosovo v Israel")
check("no date, no day", N.event_day("KXUEFANLTOTAL"), None)

print("\nthe replay on a made-up dump")
T0 = 1_800_000_000                                           # a whole minute
steady = [(T0 + 30 * i, 0.60, 10.0, None) for i in range(25)]  # 0.60 every 30 s for 12 minutes
dump = steady + [(T0 + 760, 0.35, 500.0, "no"), (T0 + 840, 0.56, 500.0, "yes")]
b = N.replay(dump, "yes")
YES = lambda cell, bb=None: [x for x in (bb or b)[cell] if x["side"] == "yes"]      # the recovery print is also a NO fill, which the rule takes too
y = YES("D20_25s")
check("one YES bid at 40c under the 60c print, filled by the print through it", [(x["side"], x["R"], x["L"], x["fill"]) for x in y], [("yes", 0.6, 0.4, T0 + 760)])
check("sold at 55c (5c under the 60c): 2.5 contracts, +37.5% (15c on 40c) with no fee", (y[0]["sold"], y[0]["roi"], y[0]["back"]), (True, 0.375, True))
check("the held row keeps the same fill and takes the result: +150%", [(x["L"], x["roi"], x["sold"]) for x in YES("H20_25s")], [(0.4, 1.5, False)])
check("15c under: a bid at 45c, same print, sold the same way", [(x["L"], x["roi"]) for x in YES("D15_25s")], [(0.45, round((0.55 - 0.45) / 0.45, 4))])
check("40c under, only in the last 3 hours: the bid at 20c is never reached", b["D40_25s"], [])
check("the recovery print (56c YES = 44c NO) is itself through the NO bid at 45c, and the rule takes that fill too, held to a YES result it loses",
      [(x["side"], x["L"], x["roi"]) for x in b["D20_25s"] if x["side"] == "no"], [("no", 0.45, -1.0)])
lost = YES("H20_25s", N.replay(dump, "no"))
check("held to a NO result: the YES fill loses it all", [x["roi"] for x in lost], [-1.0])
check("a print that is only AT the bid does not fill it (strictly through)", N.replay(steady + [(T0 + 760, 0.40, 500.0, "no")], "yes")["D20_25s"], [])
check("both delay columns fill the same dump, each by the print through the bid", [(x["L"], x["fill"]) for x in YES("D20_2s")], [(0.4, T0 + 760)])
check("no bid over 95c", N.replay([(T0 + 30 * i, 0.97, 10.0, None) for i in range(25)] + [(T0 + 760, 0.30, 500.0, "no")], "yes")["D20_25s"], [])
check("no bid when nothing traded in the last 10 minutes", N.replay([(T0, 0.60, 10.0, None), (T0 + 1500, 0.30, 500.0, "no")], "yes")["D20_25s"], [])
late = [(T0 + 20000 + 30 * i, 0.60, 10.0, None) for i in range(25)] + [(T0 + 20760, 0.15, 500.0, "no"), (T0 + 20900, 0.56, 500.0, "yes")]
check("the 40c row bids inside the last 3 hours of trading: the 20c bid under 60c is reached by a print at 15c",
      [(x["L"], x["fill"]) for x in YES("D40_25s", N.replay(late, "yes"))], [(0.2, T0 + 20760)])
check("a market with one print makes no bet", N.replay([(T0, 0.5, 1.0, None)], "yes")["D20_25s"], [])

print("\nwhich markets are read")
events = [dict(event_ticker="KXUEFANLTOTAL-26NOV13AAABBB", title="A vs B: Total Goals", markets=[dict(ticker="X-1", result="yes")]),
          dict(event_ticker="KXUEFANLTOTAL-26NOV14CCCDDD", title="C vs D: Total Goals",
               markets=[dict(ticker="Y-1", result="yes"), dict(ticker="Y-2", result="no"), dict(ticker="Y-3", result=""), dict(ticker="Y-4", result="yes")]),
          dict(event_ticker="KXUEFANLTOTAL-26NOV15EEEFFF", title="E vs F: Total Goals", markets=[dict(ticker="Z-1", result="no")])]
st = N.empty()
st["markets"]["Y-4"] = dict(event="x", day="2026-11-14", match="", result="yes", prints=1, bets={})
check("a game before FROM, a market with no result and a market already read are left out",
      [m["ticker"] for _ev, m in N.todo(events, st)], ["Y-1", "Y-2", "Z-1"])
n = N.run(st, events, tape=lambda tk: dump if tk == "Y-1" else [])
check("run reads each once and the ledger keeps all four rows of each", (n, sorted(st["markets"]), sorted(st["markets"]["Y-1"]["bets"])),
      (3, ["Y-1", "Y-2", "Y-4", "Z-1"], sorted(f"{k}_{d}s" for k in N.ROWS for d in N.DELAYS)))
check("an empty tape is read as no bets, not an error", (st["errors"], st["markets"]["Y-2"]["prints"]), ([], 0))
check("a second run reads nothing new", N.run(st, events, tape=lambda tk: dump), 0)
boom = N.empty()
check("a failing pull is skipped and kept for the next run", (N.run(boom, events, tape=lambda tk: 1 / 0), len(boom["errors"]), boom["markets"]), (0, 4, {}))

print("\nthe record and the read")
rec = N.records(st)
check("the headline column holds the two fills (YES and NO side) of one game: one cluster", (rec["D20"]["headline"]["n"], rec["D20"]["headline"]["clusters"]), (2, 1))
check("under 100 fills the read says too early", rec["D20"]["read"].startswith("too early (2 of 100 fills"), True)
big = N.empty()
for i in range(120):
    big["markets"][f"M-{i}"] = dict(event=f"KXUEFANLTOTAL-26NOV{14 + i % 4}G{i}", day=f"2026-11-{14 + i % 4}", match="A v B", line="Over 2.5", result="yes", prints=9,
                                    bets={N.cell_key("D20", 25): [dict(side="yes", T=1, R=0.6, L=0.4, fill=2, qty=2.5, part=False, through=10, roi=1.0 if i % 3 else -1.0,
                                                                       sold=bool(i % 3), taker_sell=False, back=True, won=1.0)]})
big_rec = N.records(big)["D20"]
check("at 120 fills, positive with a score of 2 or more is kept", (big_rec["headline"]["n"], big_rec["read"]), (120, "read at 100: keep (positive, score 2 or more)"))
for k in big["markets"].values():
    k["bets"][N.cell_key("D20", 25)][0]["roi"] = -0.1
check("negative at 100 fills is retired", N.records(big)["D20"]["read"], "read at 100: retire (not positive with a score of 2 or more)")

print("\nthe page rows")


def _no_call(*a, **k):
    raise AssertionError("the page builder made a venue call")


real = D.get
D.get = _no_call
try:
    rows = NB.rows(N.empty())
    rows_big = NB.rows(big)
finally:
    D.get = real
check("four rows, the 20c row first and named as a paper watch", ([r["name"] for r in rows], "paper watch" in rows[0]["meta"]["label"]),
      (["nl_dump_d20", "nl_dump_d15", "nl_dump_h20", "nl_dump_d40"], True))
text = " ".join(r["own"]["details"] + r["own"]["entries"] + r["own"]["label"] + r["meta"]["note"] for r in rows + rows_big)
check("no guarded phrase, no money words, no weather words", [w for w in ("real " + "money", "the " + "bot", "follow" + "er", "$", "weath" + "er") if w in text.lower()], [])
check("the audit's phrase scan finds nothing in the rows or the module text",
      (sandbox_audit.COPY_RE.search(text), sandbox_audit.COPY_RE.search(open("nl_dump.py").read() + open("nl_dump_build.py").read()
                                                                        + open("docs/prereg_nl_dump_2026-11-13.md").read())), (None, None))
check("the rows are observation rows and open nothing", {(r["meta"]["kind"], r["open"]) for r in rows}, {("Observation", 0)})

print()
if FAILS:
    print(f"{len(FAILS)} FAILED")
    sys.exit(1)
print("all ok")
