#!/usr/bin/env python3
"""Offline checks for the fresh-record-at-a-raised-stake rule (2026-11-06, Olu): a pair whose stake the follower raised counts its Production
record, its live fills, its Early count and its sport header from the raise; the record at the earlier stake stays in a fold; a NEW raise starts
a new window by itself, read from the follower's own config, never a hand list."""
import datetime as dt
import sys

import live_caps as LC
import live_caps_publish as LP
import production as P
import production_live as PL
import raised_stakes as RS

FAILS = []


def check(label, got, want):
    ok = got == want
    print(f"  {'ok  ' if ok else 'FAIL'} {label}" + ("" if ok else f" (got {got!r}, want {want!r})"))
    if not ok:
        FAILS.append(label)


print("the source of truth is the follower's config")
cfg = {"stakes": {"a|x": 10}}
stake = lambda c, pair: c["stakes"].get(pair)
caps = LP.compute(["a|x", "b|y"], cfg, lambda c, p: 0.85, lambda c, p: None, lambda p: 0.01, stake, previous={}, now="2026-11-10T12:00:00+00:00")
check("a raised pair carries raised_at, an unraised one does not", ("raised_at" in caps["a|x"], "raised_at" in caps["b|y"]), (True, False))
check("the date is the first export that saw it; the entry carries no stake amount", (caps["a|x"]["raised_at"], sorted(caps["a|x"])), ("2026-11-10T12:00:00+00:00", ["band", "cap", "max_ask", "raised_at"]))
later = LP.compute(["a|x", "b|y"], cfg, lambda c, p: 0.85, lambda c, p: None, lambda p: 0.01, stake, previous=caps, now="2026-11-11T12:00:00+00:00")
check("a later export keeps the first date", later["a|x"]["raised_at"], "2026-11-10T12:00:00+00:00")
cfg2 = {"stakes": {"a|x": 10, "b|y": 10}}
newer = LP.compute(["a|x", "b|y"], cfg2, lambda c, p: 0.85, lambda c, p: None, lambda p: 0.01, stake, previous=later, now="2026-11-12T09:00:00+00:00")
check("a NEW raise starts its own window by itself; the old one is not moved", (newer["a|x"]["raised_at"], newer["b|y"]["raised_at"]), ("2026-11-10T12:00:00+00:00", "2026-11-12T09:00:00+00:00"))
back = LP.compute(["a|x", "b|y"], {"stakes": {}}, lambda c, p: 0.85, lambda c, p: None, lambda p: 0.01, stake, previous=newer, now="2026-11-13T09:00:00+00:00")
check("a pair back at the default stake loses it", [("raised_at" in v) for v in back.values()], [False, False])

print("\nthe window")
G = {"p|s": dict(cap=0.85, max_ask=0.84, band=None, raised_at="2026-11-06T13:39:54+00:00")}
LC.load = lambda path=LC.PATH, _g=G: _g
pair = {"stage": "production", "ready_at": "2026-10-21T23:00:00+00:00", "promoted_at": "2026-10-21T23:00:00+00:00", "by_hand": "2026-10-21"}
v = P.fresh_view("p|s", pair)
check("the record starts at the raise (the stage's own reset clock)", (P.entered_at(v), P.entered_at(pair)), ("2026-11-06T13:39:54+00:00", "2026-10-21T23:00:00+00:00"))
check("the original pair is not altered", pair.get("since"), None)
check("a pair not raised is returned as it came", P.fresh_view("q|t", pair) is pair, True)
early = dict(pair, ready_at="2026-11-08T00:00:00+00:00", promoted_at="2026-11-08T00:00:00+00:00")
check("a raise before the pair entered changes nothing", P.fresh_view("p|s", early) is early, True)
check("the Early count restarts with the raise", P._early_from(v), "2026-11-06")

print("\nthe live fills use the same window, and the earlier ones go to the fold")
orders = [dict(id="a", ko="2026-11-05T19:00", st="won", w=1.0, r=0.3), dict(id="b", ko="2026-11-06T20:00", st="lost", w=1.0, r=-1.0),
          dict(id="c", ko="2026-11-07T15:00", st="won", w=1.0, r=0.5)]
check("since the raise: the last two", [o["id"] for o in PL.window(orders, "2026-11-06T13:39:54+00:00")], ["b", "c"])
check("before the raise: the first", [o["id"] for o in PL.window(orders, "2026-10-21T23:00:00+00:00", "2026-11-06T13:39:54+00:00")], ["a"])
rec_old = PL.record(PL.window(orders, "2026-10-21T23:00:00+00:00", "2026-11-06T13:39:54+00:00"))
fold = PL.raised_fold([("Pair P", "2026-11-06T13:39:54+00:00", dict(n=4, won=3, roi_fee=0.12), rec_old)])
check("the fold names the pair, the raise date and both records, without an amount", ("Pair P" in fold, "Nov 6" in fold, "3–1" in fold, "1–0" in fold, "$" in fold), (True, True, True, True, False))
check("no raised pair, no fold", PL.raised_fold([]), "")

print("\nthe page")
import json
import sandbox_audit
check("the committed caps carry the five raises, and no dollar sign", (sum(1 for g in json.load(open("data/live_caps.json"))["caps"].values() if g.get("raised_at")), "$" in json.dumps(json.load(open("data/live_caps.json")))), (5, False))
check("the fold's words pass the public copy guard", bool(sandbox_audit.COPY_RE.search(fold)), False)

if FAILS:
    print(f"\nFAILED {len(FAILS)}")
    sys.exit(1)
print("ALL PASS")
