#!/usr/bin/env python3
"""AAA gas weekly cheap NO in Production (2026-11-22, Olu): what is listed, what the lead says, how it is graded."""
import copy
import datetime as dt
import sys

import gas_week_production as G
import production as P

UTC = dt.timezone.utc
FAILS = []


def check(why, got, want):
    ok = got == want
    print(f"  {'ok  ' if ok else 'FAIL'} {why}" + ("" if ok else f" — got {got!r}, want {want!r}"))
    if not ok:
        FAILS.append(why)


def at(h, m=0, day=23):
    return dt.datetime(2026, 11, day, h, m, tzinfo=UTC)


def entry(tid="KXAAAGASW-26NOV30-3.5000", price=0.21, entered=(15, 8), logged=(17, 1), status="open", check_="verified", payout=None, day=23):
    return {"id": tid, "side": "no", "word": "Above " + tid.rsplit("-", 1)[1], "price": price, "spread": 0.03,
            "entry_at": at(*entered, day=day).isoformat(), "logged": at(*logged, day=day).isoformat(), "status": status, "payout": payout,
            "settled": None, "ask_check": {"status": check_, "how": "book"}}


FETCH = lambda url: {"market": {"close_time": "2026-11-30T04:59:00Z"}}                       # noqa: E731
print("what is listed")
NOW = at(17, 20)
check("a fresh verified NO entry logged after promotion", G.listable(entry(), NOW), True)
check("an unverified ask is never listed", G.listable(entry(check_="unverified"), NOW), False)
check("an entry logged before the promotion is not listed", G.listable(entry(day=21, logged=(17, 1)), at(17, 20, day=21)), False)
check("a replayed entry (logged 3h+ after its own minute) is not listed", G.listable(entry(entered=(9, 0), logged=(17, 1)), NOW), False)
check("an offer older than OFFER_H is over", G.listable(entry(), at(21, 5)), False)
check("a YES entry is not this lane", G.listable(dict(entry(), side="yes"), NOW), False)

print("\nthe lead")
st = G.scan(NOW, {"quotes": {}, "last_run": None, "error": None}, source={"entries": [entry(), entry(price=0.30, check_="unverified", tid="KXAAAGASW-26NOV30-3.5200")]}, fetch=FETCH)
check("only the verified entry is in the ledger", sorted(st["quotes"]), ["gas_week_cheap_no:KXAAAGASW-26NOV30-3.5000"])
blob = G.feed(st, now=NOW, heartbeat=True)
check("one lead, pending", [(l["status"], l["pair"], l["bet"]) for l in blob["leads"].values()],
      [("pending", "gas_week_cheap_no|gas_week", {"kind": "gasw_no"})])
lead = next(iter(blob["leads"].values()))
check("it is the NO of the named contract at the ask the rule logged",
      (lead["route"]["venue"], lead["route"]["market"], lead["route"]["event"], lead["route"]["outcome_side"], lead["route"]["price_at_log"], lead["price_at_log"]),
      ("kalshi", "KXAAAGASW-26NOV30-3.5000", "KXAAAGASW-26NOV30", "no", 0.21, 0.21))
check("kickoff is the end of the offer (logged + 4h), the close rides along",
      (lead["kickoff"], lead["closes"], lead["league"]), ("2026-11-23T21:01Z", "2026-11-30T04:59:00Z", "AAA gas weekly"))
check("the headline says No", lead["headline"], "Above 3.5000: No")
check("the pair carries its sandbox record and a band", blob["bands"], {"gas_week_cheap_no|gas_week": [0.15, 0.30]})

print("\nthe offer ends")
late = G.feed(st, now=at(21, 30), heartbeat=True)
check("after the offer an open listing leaves the feed", list(late["leads"]), [])
check("a stale collector lists nothing open", list(G.feed(dict(st, last_run=at(10).isoformat()), now=NOW, heartbeat=True)["leads"]), [])

print("\ngrading from the paper lane's settlement")
won = G.scan(at(23, 0, day=30), copy.deepcopy(st), source={"entries": [dict(entry(), status="settled", payout=1.0, settled="2026-11-30T05:10:00+00:00")]}, fetch=FETCH)
q = won["quotes"]["gas_week_cheap_no:KXAAAGASW-26NOV30-3.5000"]
check("a NO that pays is won at its price", (q["status"], q["result"], q["pnl"]), ("won", "b", round(100 * (1 / 0.21 - 1), 2)))
lost = G.scan(at(23, 0, day=30), copy.deepcopy(st), source={"entries": [dict(entry(), status="settled", payout=0.0, settled="2026-11-30T05:10:00+00:00")]}, fetch=FETCH)
check("a NO that does not is lost the stake", (lambda x: (x["status"], x["pnl"]))(lost["quotes"]["gas_week_cheap_no:KXAAAGASW-26NOV30-3.5000"]), ("lost", -100.0))
check("the paper lane's own ledger is never written here", G.SOURCE_LEDGER != G.LEDGER, True)

print("\nthe pair is a live Production pair on a fresh record")
check("registered by name, from 2026-11-22", (G.PAIR, G.PROMOTED[:10], G.MOVED_ON, G.STAKE), ("gas_week_cheap_no|gas_week", "2026-11-22", "2026-11-22", 100.0))
check("the sport is the gas week sport, not a daily-close ladder", (G.SPORT in P.T.GASW_SPORTS, G.SPORT in P.T.LADDER_SPORTS), (True, False))

print(f"\n{'ALL PASS' if not FAILS else str(len(FAILS)) + ' FAILED'}")
sys.exit(1 if FAILS else 0)
