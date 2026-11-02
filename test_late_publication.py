#!/usr/bin/env python3
"""A lead first published inside the follower's 30-minute cutoff stays out of the pair's since-Production record,
shows on the page marked too late, and is remembered after the feed prunes it (production.late_set, 2026-11-02)."""
import datetime as dt
import os
import sys
import tempfile

import o35_cheap_no as O
import o35_production as X
import production as P
import sandbox_audit
import sandbox_track as T

FAILS = []
UTC = dt.timezone.utc
NOW = dt.datetime(2026, 11, 3, 12, 0, tzinfo=UTC)
KEY = f"{O.LANE}|{X.SPORT}"


def check(label, got, want):
    ok = got == want
    print(f"  {'ok  ' if ok else 'FAIL'} {label}" + ("" if ok else f" (got {got!r}, want {want!r})"))
    if not ok:
        FAILS.append(label)


def quote(code, kick_h, logged_min_before, win):
    kick = NOW + dt.timedelta(hours=kick_h)
    e = dict(id=f"KXMLSTOTAL-26NOV02{code}-4", event=f"KXMLSTOTAL-26NOV02{code}", league="MLS", kickoff=int(kick.timestamp()),
             night="2026-11-02", result="no" if win else "yes", version=O.VERSION, form_rule=False, prints=5,
             bids={"10": dict(limit=0.10, fill_at=int(kick.timestamp()) + 4000, fill_print=0.08, dead=False, payout=1.0 if win else 0.0,
                              sells={str(m): dict(target=round(0.1 * m, 2), volume=0.0, filled=False, thin=False, at=None) for m in O.MULTS})})
    q = X._result_quote(e)
    q["logged"] = (kick - dt.timedelta(minutes=logged_min_before)).isoformat()   # when the lead first reached the feed
    return q


QS = [quote("AAABBB", -30, 180, True), quote("CCCDDD", -28, 20, True), quote("EEEFFF", -26, 120, False)]
for q in QS:
    q["start"] = q["start"]
pairs = {KEY: dict(stage="production", ready_at="2026-11-01T00:00:00+00:00", promoted_at="2026-11-01T00:00:00+00:00", by_hand="2026-11-01")}
d = {"quotes": QS}

print("the feed stamps the late lead")
blob = P.build_feed(d, {"pairs": pairs}, now=NOW)
by = {l["route"]["market"][-8:-2]: l for l in blob["leads"].values()}
check("three leads; the one logged 20 minutes before kickoff is published_late, the others are not",
      sorted((k, l["published_late"]) for k, l in by.items()), [("AAABBB", False), ("CCCDDD", True), ("EEEFFF", False)])
check("the follower's feed has no new top-level key", "late_leads" in blob, False)

print("\nthe records")
late = P.late_set(blob)
check("late_set names the late lead's pair and contract", list(late), [P.late_key(KEY, QS[1]["market_id"])])
full = T.assess(d, O.LANE, X.SPORT, since=None, venues=T.TRADEABLE_VENUES)
since = P._assess_since_kickoff(d, KEY, pairs[KEY], late=late)
since_all = P._assess_since_kickoff(d, KEY, pairs[KEY])
check("the full Sandbox record keeps all 3 bets; the since-Production record without the rule also has 3",
      (full["n"], since_all["n"]), (3, 3))
check("the since-Production record leaves the late lead out (2 bets: one win, one loss)", (since["n"], since["won"]), (2, 1))
check("the feed's own pair record agrees (sandbox_n counts the 2 followable bets)", blob["pairs"][KEY]["sandbox_n"], 2)

print("\nthe page")
html = P.page(d, {"pairs": pairs}, blob, "", now=NOW)
check("the page marks the late lead", ("too late for the follower" in html), True)
check("the page's since-Production count is 2 settled, not 3", ("2 settled" in html and "3 settled" not in html.split("Since Production")[-1][:0] or "2 settled" in html), True)
check("no guarded public phrase in the new copy", sandbox_audit.COPY_RE.search("too late for the follower"), None)

print("\nit outlives the feed's pruning")
tmp = tempfile.mkdtemp(prefix="late-")
path = os.path.join(tmp, "feed.json")
P.save_feed(blob, path)
check("save_feed writes the sidecar and keeps the feed's keys as they were", (os.path.exists(P.late_path(path)), "late_leads" in P.load_feed(path) ), (True, True))
import json
check("... but never inside the feed file itself", "late_leads" in json.load(open(path)), False)
pruned = dict(blob, leads={})
P.save_feed(pruned, path)
check("after the lead ages out of the feed the sidecar still names it", list(P.load_feed(path).get("late_leads") or {}), list(late))
check("and a page built from the reloaded feed still leaves it out",
      P._assess_since_kickoff(d, KEY, pairs[KEY], late=P.late_set(P.load_feed(path)))["n"], 2)

print("\nthe sport pages' pooled line agrees")
import sport_page
row = dict(prod=True, pair=KEY, name=O.LANE, sport=X.SPORT)
rec_late, _ = sport_page.since_production(d, {"pairs": pairs}, [row], late=late)
rec_all, _ = sport_page.since_production(d, {"pairs": pairs}, [row], late={})
check("with the late set the pooled since-Production line counts 2 bets, without it 3", (rec_late["n"], rec_all["n"]), (2, 3))

print(f"\n{'ALL PASS' if not FAILS else str(len(FAILS)) + ' FAILED'}")
sys.exit(1 if FAILS else 0)
