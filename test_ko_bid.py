#!/usr/bin/env python3
"""Offline checks for the before-kickoff dump bid (ko_bid.py, 2026-11-14): the 3-hour cutoff from the expiry, bids only before it and after
FROM_TS, the maker fee on club series only, the two rows kept apart, backfill by a later run, the pre-registered read, and a page builder that
makes no venue call and uses no guarded phrase."""
import sys

import daily_track as D
import fillsim as F
import ko_bid as K
import ko_bid_build as KB
import nl_dump as N
import sandbox_audit

FAILS = []


def check(label, got, want):
    ok = got == want
    print(f"  {'ok  ' if ok else 'FAIL'} {label}" + ("" if ok else f" (got {got!r}, want {want!r})"))
    if not ok:
        FAILS.append(label)


print("the cutoff and the series")
check("3 hours before the listed kickoff = expiry minus 6 hours", K.cutoff_of({"expected_expiration_time": "2026-11-14T22:00:00Z"}), int(__import__("datetime").datetime(2026, 11, 14, 16, tzinfo=__import__("datetime").timezone.utc).timestamp()))
check("the cutoff is 16:00 UTC for a 22:00 expiry", K.cutoff_of({"expected_expiration_time": "2026-11-14T22:00:00Z"}) - K.cutoff_of({"expected_expiration_time": "2026-11-14T16:00:00Z"}), 6 * 3600)
check("no expiry, no cutoff", K.cutoff_of({}), None)
check("nine series in two rows", ({g: len(c["series"]) for g, c in K.GROUPS.items()}, K.GROUP_OF["KXEPLGAME"], K.GROUP_OF["KXAFCONGAME"]), ({"national": 4, "club": 5}, "club", "national"))
check("maker fee on the club row only", ({g: K.RULES[c["maker"]].maker_rate for g, c in K.GROUPS.items()}), {"national": 0.0, "club": 0.0175})

print("\nthe replay on a made-up dump")
T0 = K.FROM_TS + 3600                       # a whole minute after FROM_TS
steady = [(T0 + 30 * i, 0.60, 10.0, None) for i in range(25)]
dump = steady + [(T0 + 760, 0.35, 500.0, "no"), (T0 + 840, 0.56, 500.0, "yes")]
CUT = T0 + 3600


def yes(b):
    return [x for x in b["B15_25s"] if x["side"] == "yes"]


nat = yes(K.replay(dump, "yes", "national", CUT))
club = yes(K.replay(dump, "yes", "club", CUT))
check("a bid 15c under the 60c print, filled by the dump and sold at 55c: +22.2% with no maker fee", [(x["L"], x["fill"], x["roi"], x["sold"]) for x in nat], [(0.45, T0 + 760, 0.2222, True)])
check("the club row pays the maker fee on the buy and the sell, so it earns less on the same trades", (len(club) == 1, club[0]["roi"] < nat[0]["roi"]), (True, True))
check("a dump after the cutoff is not bid for", yes(K.replay(dump, "yes", "national", T0 + 600)), [])
check("a bid whose minute is before FROM_TS does not count", yes(K.replay([(t - 7200, p, n, s) for t, p, n, s in dump], "yes", "national", CUT)), [])
check("only the 15c bid, in both delay columns", sorted(K.replay(dump, "yes", "national", CUT)), ["B15_25s", "B15_2s"])

print("\nwhich markets are read, and a late run backfills")
ev = lambda tk, day, ms: dict(event_ticker=f"{tk}-26NOV{day}AAABBB", title="A vs B", markets=ms)
mk = lambda t, res="yes", exp="2026-11-14T22:00:00Z": dict(ticker=t, result=res, yes_sub_title="A", expected_expiration_time=exp)
by = {"KXAFCONGAME": [ev("KXAFCONGAME", "14", [mk("N-1"), mk("N-2", ""), mk("N-3", exp="")]), ev("KXAFCONGAME", "13", [mk("N-0")])],
      "KXEPLGAME": [ev("KXEPLGAME", "21", [mk("C-1", "no")])]}
st = K.empty()
n = K.run(st, by, tape=lambda tk: dump)
check("a game before FROM_DAY and a market with no result are left out; a market with no expiry is an error, kept for the next run",
      (n, sorted(st["markets"]), len(st["errors"])), (2, ["C-1", "N-1"], 1))
check("each market lands in its own row", (st["markets"]["N-1"]["group"], st["markets"]["C-1"]["group"]), ("national", "club"))
check("a second run reads nothing new", K.run(st, by, tape=lambda tk: dump), 0)
late = K.empty()
by2 = {"KXAFCONGAME": [ev("KXAFCONGAME", "14", [mk("N-1")])]}
K.run(late, by2, tape=lambda tk: dump)
by2["KXAFCONGAME"].append(ev("KXAFCONGAME", "15", [mk("N-5")]))
check("a later run backfills the market an earlier one never saw", (K.run(late, by2, tape=lambda tk: dump), sorted(late["markets"])), (1, ["N-1", "N-5"]))

print("\nthe record and the read")
rec = K.records(st)
check("two rows, kept apart", (rec["national"]["headline"]["n"] > 0, rec["club"]["headline"]["n"] > 0, rec["national"]["games"], rec["club"]["games"]), (True, True, 1, 1))
check("under 50 fills: too early", rec["national"]["read"].startswith("too early"), True)
big = K.empty()
for i in range(100):
    day = 14 + i % 4
    big["markets"][f"M-{i}"] = dict(event=f"KXAFCONGAME-26NOV{day}G{i}", day=f"2026-11-{day}", series="KXAFCONGAME", group="national", match="A v B", leg="A", result="yes", cutoff=1, prints=9,
                                    bets={N.cell_key("B15", 25): [dict(side="yes", T=1, R=0.6, L=0.45, fill=2, qty=2, part=False, through=10, roi=1.0 if i % 3 else -1.0, sold=True, taker_sell=False, back=True, won=1.0)]})
check("100 fills, positive, score 2 or more, both halves positive: keep", K.records(big)["national"]["read"], "read at 100: keep (positive, score 2 or more, both halves positive)")
half = K.empty()
half["markets"] = {k: dict(v, event=f"KXAFCONGAME-26NOV{14 if int(k[2:]) < 50 else 16}G{k[2:]}", bets={N.cell_key("B15", 25): [dict(v["bets"][N.cell_key("B15", 25)][0], roi=(1.0 if int(k[2:]) < 50 else -0.4))]}) for k, v in big["markets"].items()}
check("positive overall but the second half negative: not kept", K.records(half)["national"]["read"].startswith("read at 100: retire"), True)
for v in big["markets"].values():
    v["bets"][N.cell_key("B15", 25)][0]["roi"] = -0.1
check("negative at 100 fills: retire", K.records(big)["national"]["read"], "read at 100: retire (under the bar at 100 fills)")

print("\nthe page rows")


def _no_call(*a, **k):
    raise AssertionError("the page builder made a venue call")


real = D.get
D.get = _no_call
try:
    rows = KB.rows(K.empty())
    rows_big = KB.rows(st)
finally:
    D.get = real
check("two rows named as paper watches, national first, club marked as untested", ([r["name"] for r in rows], all("paper watch" in r["meta"]["label"] for r in rows), "forward only" in rows[1]["own"]["details"]),
      (["ko_bid_national", "ko_bid_club"], True, True))
text = " ".join(r["own"]["details"] + r["own"]["entries"] + r["own"]["label"] + r["meta"]["note"] for r in rows + rows_big)
check("no guarded phrase, no money words, no weather words", [w for w in ("real " + "money", "the b" + "ot", "follow" + "er", "$", "weath" + "er") if w in text.lower()], [])
check("the audit's phrase scan finds nothing in the rows or the module text",
      (sandbox_audit.COPY_RE.search(text), sandbox_audit.COPY_RE.search(open("ko_bid.py").read() + open("ko_bid_build.py").read() + open("docs/prereg_ko_bid_2026-11-14.md").read())), (None, None))
check("observation rows, nothing open", {(r["meta"]["kind"], r["open"]) for r in rows}, {("Observation", 0)})

print()
if FAILS:
    print(f"{len(FAILS)} FAILED")
    sys.exit(1)
print("all ok")
