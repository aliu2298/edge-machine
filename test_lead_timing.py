#!/usr/bin/env python3
"""Late Production leads (2026-10-14).

On Oct 13 "Arsenal v Lille — Arsenal to score 2+" (team2_ranked) first reached the feed at
18:34:55Z for a 19:00Z kickoff, 25 minutes ahead; the follower skips anything under 30, so
nobody could act on it. The rule decided late by its own definition (the favourite's win
price crossed the 0.80 bucket edge minutes before kickoff), so new Production leads now need a 45-minute first-publication window. Historical
late leads retain their original audit timing:

  * every lead carries published_at (its first appearance in the feed, carried run to
    run), published_min_before_kickoff and published_late (under production.LATE_MIN);
  * each pair carries timing: how many leads were timed, how many came in under the
    60-minute target, and the late ones;
  * incidents before the preventative guard are addressed and removed from active warnings;
    a recurrence after deployment still raises Production and Control Center warnings;
  * Tennis Explorer is read for today AND tomorrow, so a Kalshi tennis basket's legs are
    confirmed the day before rather than minutes before a late-evening match.
No network.
"""
import datetime
import sys
from datetime import timedelta, timezone

import control_center as CC
import production as PR
import sandbox_sources as S

FAILS = []
KO = datetime.datetime(2026, 10, 13, 19, 0, tzinfo=timezone.utc)


def ok(cond, why):
    print(f"  {'ok  ' if cond else 'FAIL'} {why}")
    if not cond:
        FAILS.append(why)


def eq(got, want, why):
    ok(got == want, why if got == want else f"{why} — got {got!r}, want {want!r}")


def _iso(t):
    return t.isoformat()


print("when a lead was first published")
eq(PR.LATE_MIN, 30, "late is under 30 minutes: the follower skips anything closer")
eq(PR.TARGET_MIN, 60, "the target is an hour")
built = "2026-10-13T18:34:55+00:00"
eq(PR._published_at("x", {"leads": {"x": {"published_at": "2026-10-12T08:00:00+00:00"}}}, "2026-10-12T07:59:00+00:00", built),
   "2026-10-12T08:00:00+00:00", "a stamp from the previous feed is kept, run after run")
eq(PR._published_at("x", {"leads": {"x": {}}}, "2026-10-13T15:04:17+00:00", built), "2026-10-13T15:04:17+00:00",
   "a lead the previous feed carried without a stamp takes its bet's logged time")
eq(PR._published_at("x", {"leads": {}}, "2026-10-13T15:04:17+00:00", built), built,
   "a lead the previous feed did not carry is new: this build")
eq(PR._published_at("x", None, "2026-10-13T15:04:17+00:00", built), "2026-10-13T15:04:17+00:00",
   "with no previous feed, the logged time")


def _lead(lid, ko, pair="team2_ranked|soccer_team2", match="Arsenal v Lille", headline="Arsenal to score 2+"):
    return {"id": lid, "kickoff": ko.strftime("%Y-%m-%dT%H:%MZ"), "pair": pair, "match": match, "headline": headline}


leads = {"late": _lead("late", KO), "near": _lead("near", KO + timedelta(minutes=20)),
         "fine": _lead("fine", KO + timedelta(hours=5)), "backfill": _lead("backfill", KO - timedelta(hours=2))}
previous = {"leads": {"fine": {"published_at": "2026-10-13T09:00:00+00:00"}, "backfill": {}}}
PR.stamp_timing(leads, previous, {"backfill": ("2026-10-13T18:00:00+00:00", 0.5)}, built)
eq((leads["late"]["published_min_before_kickoff"], leads["late"]["published_late"]), (25, True),
   "first published 25 minutes before kickoff: late")
eq((leads["near"]["published_min_before_kickoff"], leads["near"]["published_late"]), (45, False),
   "45 minutes ahead is inside the hour but not late")
eq((leads["fine"]["published_at"], leads["fine"]["published_min_before_kickoff"], leads["fine"]["published_late"]),
   ("2026-10-13T09:00:00+00:00", 900, False), "a lead stamped this morning keeps its stamp and its fifteen hours")
eq((leads["backfill"]["published_min_before_kickoff"], leads["backfill"]["published_late"]), (None, False),
   "a lead first seen after its kickoff was never on offer: neither early nor late")
t = PR.pair_timing(leads, "team2_ranked|soccer_team2")
eq((t["timed"], t["under_target"], [x["id"] for x in t["late"]]), (3, 2, ["late"]),
   "the pair counts three timed leads, two under the hour, one late")
eq(PR.timing_problem(t), None, "pre-fix incidents are addressed, with their timing retained")
eq(PR.timing_problem({"late": []}), None, "a pair with no late lead has nothing to say")

print("\nthe Arsenal lead, through build_feed")
q = dict(id="team2_ranked:KXUCLTEAMTOTAL-26OCT13ARSLIL-ARS2", source="team2_ranked", sport="soccer_team2",
         market_id="KXUCLTEAMTOTAL-26OCT13ARSLIL-ARS2", venue="kalshi_binary", pick="a", price=0.74,
         price_a=0.74, price_b=0.27, side_a="Yes", side_b="No", bet=True, status="open",
         start=_iso(KO), logged="2026-10-13T18:33:10+00:00", start_source="espn", league="Champions League",
         espn_home="Arsenal", espn_away="Lille", team="Arsenal", label="Arsenal v Lille: Arsenal to score 2+",
         kalshi_title="Arsenal over 1.5 goals")
early = dict(q, id="team2_ranked:KXLALIGATEAMTOTAL-26OCT14AAABBB-AAA2", market_id="KXLALIGATEAMTOTAL-26OCT14AAABBB-AAA2",
             start=_iso(KO + timedelta(days=1)), logged="2026-10-13T09:00:00+00:00", espn_home="Alpha", espn_away="Beta",
             team="Alpha", league="La Liga")
st = {"pairs": {"team2_ranked|soccer_team2": {"stage": "production", "by_hand": "2026-10-11",
                                             "ready_at": "2026-10-11T00:00:00+00:00",
                                             "promoted_at": "2026-10-11T00:00:00+00:00"}}}
now = datetime.datetime(2026, 10, 13, 18, 34, 55, tzinfo=timezone.utc)
prev = PR.build_feed({"quotes": [early]}, st, now=now - timedelta(minutes=30), previous={"leads": {}})
feed = PR.build_feed({"quotes": [early, q]}, st, now=now, previous=prev)
by = {l["match"]: l for l in feed["leads"].values()}
ok("Arsenal v Lille" not in by, "the newly qualifying Arsenal lead is withheld before publication")
eq(feed["late_publication_skipped"], 1, "the withheld pick is counted")
eq(by["Alpha v Beta"]["published_at"], prev["updated_at"], "the earlier lead keeps the time it first appeared")
page = PR.page({"quotes": [early, q]}, st, feed, "", now=now)
ok("1 first qualified too close to the start" in page, "Production explains the withheld pick")
# A deployed feed may contain a historical late lead. Preserve the fact and clear its active warning.
legacy = PR.lead_from_quote(q, "team2_ranked|soccer_team2", built)
legacy["published_at"] = built
feed = PR.build_feed({"quotes": [early, q]}, st, now=now,
                     previous={"leads": {legacy["id"]: legacy}})

timing = feed["pairs"]["team2_ranked|soccer_team2"]["timing"]
eq([x["minutes"] for x in timing["late"]], [25], "the pair's timing names the late lead")
state, why = PR.pair_health("team2_ranked|soccer_team2", [q], 2, feed["pairs"], now=now, timing=timing)
eq(state, "ok", "the addressed Arsenal incident no longer makes Production red")
page = PR.page({"quotes": [early, q]}, st, feed, "", now=now)
ok("published late — too close to kickoff to act on" not in page, "the addressed warning is removed from Production")
ok(timing["late"][0]["addressed"], "the original late incident remains marked addressed in feed history")
eq(next(l for l in feed["leads"].values() if l["match"] == "Arsenal v Lille")["published_at"], built,
   "original publication time is preserved")

print("\nthe Control Center clears addressed warnings but flags recurrences")
items = [i for i in CC._attention({"quotes": []}, st, {}, now, None, None, blob=feed) if i["kind"] == "late"]
eq(items, [], "the addressed Arsenal warning is removed from active attention")
future_ko = KO + timedelta(days=3)
future_pub = future_ko - timedelta(minutes=26)
recurrence = dict(legacy, kickoff=_iso(future_ko), published_at=_iso(future_pub), published_late=True,
                  published_min_before_kickoff=26)
future_feed = {"leads": {recurrence["id"]: recurrence}}
future_timing = PR.pair_timing(future_feed["leads"], "team2_ranked|soccer_team2")
ok(PR.timing_problem(future_timing) is not None, "a new incident after the fix still raises a Production warning")
items = [i for i in CC._attention({"quotes": []}, st, {}, future_pub, None, None, blob=future_feed) if i["kind"] == "late"]
eq(len(items), 1, "a post-fix recurrence still needs Control Center attention")
ok("Arsenal v Lille" in items[0]["text"], "the recurrence names the affected fixture")
ok(PR.late_issue_active(dict(recurrence, published_at=None)), "unknown publication time cannot hide a warning")
eq(CC.KIND_LABEL["late"], "Published late", "labelled as such")
from sandbox_audit import COPY_RE
ok(not COPY_RE.search(items[0]["text"]), "warning uses the pages' own vocabulary")
later = future_ko + timedelta(hours=CC.LATE_LEAD_HOURS + 2)
eq([i for i in CC._attention({"quotes": []}, st, {}, later, None, None, blob=future_feed) if i["kind"] == "late"], [],
   "a recurrence still expires from attention after the existing window")

print("\nfirst-publication boundary and persistence")
from copy import deepcopy
paper = {"quotes": [q]}
original = deepcopy(paper)
for seconds, count in ((45*60, 1), (45*60-1, 0), (30*60, 0), (26*60, 0)):
    at = KO - timedelta(seconds=seconds)
    fresh = PR.build_feed(paper, st, now=at, previous={"leads": {}})
    eq(len(fresh["leads"]), count, f"first publish with {seconds} seconds remaining")
    if not count:
        withheld = fresh
# Missing previous feed must not use an old paper log to bypass the guard.
stale_log = dict(q, logged="2026-10-13T09:00:00+00:00")
eq(len(PR.build_feed({"quotes": [stale_log]}, st, now=now)["leads"]), 0,
   "old logged time cannot bypass the guard when previous feed is missing")
# Once withheld it remains absent when settled; paper ledger remains untouched.
settled = dict(q, status="hit")
next_feed = PR.build_feed({"quotes": [settled]}, st, now=KO+timedelta(hours=2), previous=withheld)
eq(len(next_feed["leads"]), 0, "withheld pick cannot return as a settled Production lead")
eq(next_feed["late_publication_skipped"], 1, "withheld audit survives refresh and settlement")
eq(paper, original, "the cutoff never changes the paper ledger")
# An early publication is retained when refreshed inside the cutoff.
at = KO - timedelta(hours=2)
first = PR.build_feed(paper, st, now=at, previous={"leads": {}})
refresh = PR.build_feed(paper, st, now=now, previous=first)
eq(set(refresh["leads"]), set(first["leads"]), "early lead survives refresh with 25 minutes left")
eq(refresh["late_publication_skipped"], 0, "refresh is not counted as a late first publication")
eq(next(iter(refresh["leads"].values()))["published_at"], first["updated_at"], "refresh preserves first-publication time")
# A slow routing lookup cannot rely on the clock captured at build start.
from unittest.mock import patch
RealDateTime = datetime.datetime
class BuildClock(RealDateTime):
    reads = iter((KO - timedelta(minutes=50), KO - timedelta(minutes=26)))
    @classmethod
    def now(cls, tz=None):
        return next(cls.reads)
with patch.object(PR.datetime, "datetime", BuildClock):
    slow = PR.build_feed(paper, st, previous={"leads": {}})
eq(len(slow["leads"]), 0, "clock is rechecked after routing, before publication")
eq(slow["updated_at"], _iso(KO - timedelta(minutes=26)), "feed stamp reflects the completed build")
expired = PR.build_feed({"quotes": []}, st, now=KO+timedelta(days=PR.KEEP_SETTLED_DAYS+1), previous=next_feed)
eq(expired["publication_withheld"], {}, "old withheld audit expires with the settled-history window")

print("\nTennis Explorer, today and tomorrow")
today = datetime.date(2026, 10, 14)
eq(S.tennis_schedule_url(), S.TENNIS_EXPLORER, "today's page is the bare URL, as before")
eq(S.tennis_schedule_url(today + timedelta(days=1)),
   S.TENNIS_EXPLORER + "?type=all&year=2026&month=10&day=15", "tomorrow's is its date")


def _page(a, b, hhmm):
    return (f'<tr><td class="first time">{hhmm}</td><td class="t-name"><a>{a}</a></td></tr>'
            f'<tr><td class="t-name"><a>{b}</a></td></tr>')


pages = {S.tennis_schedule_url(): _page("Sinner J.", "Medvedev D.", "12:00"),
         S.tennis_schedule_url(today + timedelta(days=1)): _page("Alcaraz C.", "Zverev A.", "01:30")}
got = S.tennis_starts(getter=lambda url: pages[url], today=today)
eq([(a, b, t.isoformat()) for a, b, t in got],
   [("Sinner J.", "Medvedev D.", "2026-10-14T10:00:00+00:00"), ("Alcaraz C.", "Zverev A.", "2026-10-14T23:30:00+00:00")],
   "both days are read, each converted from Prague time on its own date")


def _no_tomorrow(url):
    if url == S.tennis_schedule_url():
        return pages[url]
    raise RuntimeError("tomorrow's page is down")


eq(len(S.tennis_starts(getter=_no_tomorrow, today=today)), 1, "tomorrow's page failing leaves today's schedule, as before")


def _none(url):
    raise RuntimeError("down")


eq(S.tennis_starts(getter=_none, today=today), [], "today's failing is no schedule at all, never a guess")

print()
if FAILS:
    print(f"{len(FAILS)} FAILED")
    sys.exit(1)
print("all passed")
