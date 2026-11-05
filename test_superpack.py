#!/usr/bin/env python3
"""Offline checks for Superpack (superpack.py, 2026-11-05, Olu): it copies an active lane's bet when the bet's name is
in the active-lanes board's top 10 as it stood when the bet was logged; one bet per contract; opposite sides skipped;
the two baselines logged the same way; and no bet that settles after an entry can change that entry's ranking."""
import copy
import datetime as dt
import sys

import leaderboard as L
import superpack as SP

FAILS = []
UTC = dt.timezone.utc


def check(label, got, want):
    ok = got == want
    print(f"  {'ok  ' if ok else 'FAIL'} {label}" + ("" if ok else f" (got {got!r}, want {want!r})"))
    if not ok:
        FAILS.append(label)


T0 = dt.datetime(2026, 11, 5, 12, tzinfo=UTC)
iso = lambda h: (T0 + dt.timedelta(hours=h)).isoformat()          # noqa: E731
n_uid = [0]


def b(name, profit, logged_h, settled_h=None, lane="laneA", contract=None, side="yes", sport="Soccer", stamp=True):
    n_uid[0] += 1
    return L.bet((f"u{n_uid[0]}", side), lane, sport, [name], iso(logged_h)[:10], profit, (profit or 0) > 0, src="test",
                 logged=iso(logged_h), settled=(iso(settled_h) if (settled_h is not None and stamp) else None),
                 contract_id=contract or f"C{n_uid[0]}", side=side, price=0.5)


stage = lambda bt: "Sandbox" if bt["lane"] != "retired_lane" else None   # noqa: E731

# History, settled well before the start: Winner FC has 5 wins (top), Loser FC 5 losses (bottom), and 40 names between
# (Mid 39 best ... Mid 00 worst), so the board has a top 20 and a separate bottom 10. Mid 20 is in neither top 10 nor bottom 10.
hist = [b("Winner FC", 1.0, -100 + i, -99 + i) for i in range(5)] + [b("Loser FC", -1.0, -90 + i, -89 + i) for i in range(5)]
for k in range(40):
    hist += [b(f"Mid {k:02d}", 0.01 * (k - 20), -80 + j, -79 + j) for j in range(5)]

print("the first run sets the start and copies nothing")
st = SP.load("/nonexistent/superpack.json")
SP.run(st, T0, bets=hist, stage=stage)
check("since is the first run; nothing decided", (st["since"], st["entries"], st["decided"]), (T0.isoformat(), [], {}))

print("\nthe copy rule")
new = [b("Winner FC", None, 1, contract="K1"),                       # top name: copied
       b("Winner FC", None, 1, contract="K1", lane="laneB"),         # same contract and side from another lane: once
       b("Loser FC", None, 2, contract="K2"),                        # bottom name: the mirror list only
       b("Mid 20", None, 3, contract="K3"),                          # neither: the pool only
       b("Winner FC", None, 4, contract="K4", side="yes"),
       b("Winner FC", None, 4, contract="K4", side="no", lane="laneB"),   # opposite sides: neither
       b("Winner FC", None, 5, contract="K5", lane="retired_lane"),  # not an active lane: never copied
       b("Winner FC", None, -1, contract="K6")]                      # logged before the start: never copied
st2 = SP.run(copy.deepcopy(st), T0 + dt.timedelta(hours=6), bets=hist + new, stage=stage)
check("Superpack entries: the top name's contract, once", [(e["contract"], e["side"], e["lane"]) for e in st2["entries"]],
      [("K1", "yes", "laneA")])
check("the mirror (bottom 10) takes the bottom name", [e["contract"] for e in st2["mirror"]], ["K2"])
check("the pool (every active-lane bet) takes K1, K2, K3 once each, not the opposite pair",
      sorted(e["contract"] for e in st2["pool"]), ["K1", "K2", "K3"])
check("the opposite-side pair is skipped on every list it matched, and logged",
      sorted({(s["list"], s["contract"]) for s in st2["skips"]}), [("entries", "K4"), ("pool", "K4")])
check("the second lane's same bet is a duplicate", st2["decided"][SP.pid(new[1])].get("entries"), "duplicate")
check("a retired lane's bet and a bet from before the start are not decided at all",
      [k for k in st2["decided"] if "retired_lane" in k] + [e["contract"] for e in st2["pool"] if e["contract"] == "K6"], [])
e = st2["entries"][0]
check("the entry copies contract, side, price and the lane's logged time", (e["price"], e["logged"], e["status"]),
      (0.5, iso(1), "open"))
check("it stores the dated top 10 it was chosen on", (e["snapshot"]["as_of"], e["snapshot"]["names"][0]["name"], len(e["snapshot"]["names"])),
      (iso(1), "Winner FC", 10))

print("\nan open entry settles on the copied bet's own result")
settled_new = [dict(x, profit=0.8, won=True, settled=iso(7)) if x["contract_id"] == "K1" and x["lane"] == "laneA" else x for x in new]
st3 = SP.run(copy.deepcopy(st2), T0 + dt.timedelta(hours=8), bets=hist + settled_new, stage=stage)
check("won, at the lane's per-$1 profit", (st3["entries"][0]["status"], st3["entries"][0]["profit"]), ("won", 0.8))
check("nothing is decided twice", len(st3["entries"]), 1)
check("the record", {k: SP.record(st3["entries"])[k] for k in ("entries", "settled", "won", "roi")},
      dict(entries=1, settled=1, won=1, roi=0.8))
check("the stamp table's quote form: $100 a bet", [(q["status"], q["pnl"], q["source"]) for q in SP.quotes(st3)], [("won", 80.0, "superpack")])

print("\nno look-ahead: a bet settling after an entry never changes that entry's ranking")
t = T0 + dt.timedelta(hours=10)
late = [b("Rising FC", 5.0, -50 + i, 11 + i) for i in range(5)]    # five big wins, all settling AFTER t
top_before, _ = SP.board_at(t, hist, st, stage)
top_with_late, _ = SP.board_at(t, hist + late, st, stage)
check("the board at t is the same with or without bets that settle after t", SP.names_of(top_before) == SP.names_of(top_with_late), True)
check("and Rising FC is not in it", ("Soccer", "Rising FC") in SP.names_of(top_with_late), False)
top_after, _ = SP.board_at(T0 + dt.timedelta(hours=20), hist + late, st, stage)
check("once they have settled it is", ("Soccer", "Rising FC") in SP.names_of(top_after), True)
nostamp = [b("Rising FC", 5.0, -50 + i, -40 + i, stamp=False) for i in range(5)]   # settled long ago, but no stamp
st4 = copy.deepcopy(st)
st4["seen_settled"].clear()
SP.run(st4, T0 + dt.timedelta(hours=12), bets=hist + nostamp, stage=stage)
top_ns, _ = SP.board_at(T0 + dt.timedelta(hours=11), hist + nostamp, st4, stage)
check("a bet with no settled stamp counts only from the run that first saw it settled",
      ("Soccer", "Rising FC") in SP.names_of(top_ns), False)
copy_after = SP.run(copy.deepcopy(st), T0 + dt.timedelta(hours=30),
                    bets=hist + late + [b("Rising FC", None, 10, contract="R1")], stage=stage)
check("a Rising FC bet logged before those settles is not copied, even when decided later",
      [x["contract"] for x in copy_after["entries"]], [])

print("\nthe registration")
check("dated and versioned", (SP.REGISTERED, SP.VERSION, SP.TOP_K), ("2026-11-05", 1, 10))
check("the rule text names the copy, the snapshot, one bet per contract and the ladder",
      all(w in SP.RULE for w in ("top 10", "same contract, side and price", "bets settled before then only",
                                  "opposite sides make none", "review at 10 settled", "decide at 30")), True)
check("the weakness is stated", ("2 of 6" in SP.WEAKNESS, "1 of 2" in SP.WEAKNESS), (True, True))

print("\nwhere it lives: the Leaderboard card, the Sandbox index and the stamp table; paper only")
import re
import leaderboard_build as LB
import production as P
import sandbox_audit
import sandbox_build as B
import sandbox_track as T
html = LB.build()
a, sp, t = html.find('<section id="active"'), html.find('<section id="superpack"'), html.find('<section id="top"')
card = html[sp:t]
check("the card sits below the active board, above the all-lanes view", 0 < a < sp < t, True)
check("it carries the rule, both baselines, the weakness and the persistence note",
      ("Pre-registered 2026-11-05" in card, "Baseline (a) · every active-lane bet" in card, "Baseline (b) · the bottom 10" in card,
       "Weakness." in card, "next week" in card), (True, True, True, True, True))
check("paper only, and it says so", "not in Production and in no feed" in card, True)
check("the nav pill for it", 'href="#superpack"' in html, True)
idx = B.build()
check("a row in the Sandbox's lane index, linking to its card", ('<tr data-lane="superpack"' in idx, "./leaderboard.html#superpack" in idx), (True, True))
k = idx.find("Stamp of approval")
check("a row in the stamp-of-approval table", __import__("html").escape(SP.LABEL) in idx[k:idx.find("</table>", k)], True)
check("not a Production pair, not a registry source the tracker would fetch", ("superpack" in {p_.split("|")[0] for p_ in P.production_pairs(T.load_stages())},
                                                                              "superpack" in __import__("sandbox_sources").SOURCES), (False, False))
wf = open(".github/workflows/sandbox-tracker.yml").read()
check("the Sandbox Tracker runs it after the lanes log and before the page build, and commits its ledger",
      (wf.find("python3 sandbox_track.py") < wf.find("python3 superpack.py") < wf.find("python3 sandbox_build.py"),
       "git add data/superpack_ledger.json" in wf), (True, True))
check("the committed ledger: registered, started, nothing copied before its start", (lambda d: (d["registered"], bool(d["since"]),
      all((e.get("logged") or "") >= d["since"] for e in d["entries"])))(SP.load()), ("2026-11-05", True, True))
check("no guarded phrase in its copy", sandbox_audit.COPY_RE.search(card + SP.RULE + SP.WEAKNESS + SP.LABEL), None)

print(f"\n{'ALL PASS' if not FAILS else str(len(FAILS)) + ' FAILED'}")
sys.exit(1 if FAILS else 0)
