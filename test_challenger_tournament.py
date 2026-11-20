"""challenger_tournament / challenger_production: the rules-text tournament, the picks, the feed (2026-11-20). No network."""
import datetime as dt

import challenger_production as CP
import challenger_tournament as T

FAILS = []


def check(label, got, want):
    ok = got == want
    print(("  ok   " if ok else "  FAIL ") + label + ("" if ok else f" — got {got!r}, want {want!r}"))
    if not ok:
        FAILS.append(label)


def rules(t, rnd):
    return f"If A wins the A vs B professional tennis match in the 2026 {t} {rnd} after a ball has been played, then the market resolves to Yes."


for rnd in ("Quarterfinal", "1/16 Finals", "Round Of 32", "Qualification Round 1", "Final"):
    check("the round is cut off the name: " + rnd, T.parse_rules(rules("ATP Challenger Helsinki", rnd)), "ATP Challenger Helsinki")
check("no tournament in the text -> None", T.parse_rules("Something else"), None)


def ev(tk, a, b, comp, tourn, res=("yes", "no"), settled="2026-11-10T10:00:00Z", start="2026-11-10T09:00:00Z"):
    ms = [dict(ticker=f"{tk}-{n}", yes_sub_title=n, result=r, settlement_ts=settled, occurrence_datetime=start, status="finalized",
               rules_primary=rules(tourn, "Round Of 32")) for n, r in ((a, res[0]), (b, res[1]))]
    return dict(event_ticker=tk, product_metadata={"competition": comp}, markets=ms)


gen = "ATP Challenger"
check("a named competition is used as is", T.tournament(ev("E1", "Aa", "Bb", "ATP Challenger Lima", "ATP Challenger Lima")), "ATP Challenger Lima")
check("the bare name falls back to the rules text", T.tournament(ev("E1", "Aa", "Bb", gen, "ATP Challenger Lima")), "ATP Challenger Lima")
bad = ev("E1", "Aa", "Bb", gen, "ATP Challenger Lima")
bad["markets"][1]["rules_primary"] = rules("ATP Challenger Kobe", "Final")
check("two markets that disagree -> no tournament, the caller skips", T.tournament(bad), None)

earlier = ev("E0", "Winner", "Loser", gen, "ATP Challenger Lima")
other_week = ev("E9", "Other", "Another", gen, "ATP Challenger Kobe")
today = ev("E2", "Winner", "Fresh", gen, "ATP Challenger Lima", res=(None, None), settled=None, start="2026-11-12T09:00:00Z")
cut = dt.datetime(2026, 11, 12, 8, tzinfo=dt.timezone.utc).timestamp()
got = T.picks(today, cut, [earlier, other_week])
check("the player who won here, against one who has not played here, is picked", [(p[1], p[2]) for p in got], [("Winner", "Fresh")])
check("a win at a different tournament does not count", T.picks(ev("E3", "Other", "Fresh", gen, "ATP Challenger Lima", res=(None, None), settled=None), cut, [earlier, other_week]), [])
both = ev("E4", "Winner", "Loser", gen, "ATP Challenger Lima", res=(None, None), settled=None)
check("an opponent who already played here blocks the pick", T.picks(both, cut, [earlier]), [])

named = [ev(f"KXATPCHALLENGERMATCH-26NOV10{i}", n1, n2, c, c, start=st, settled=se) for i, (n1, n2, c, st, se) in enumerate([
    ("Winner", "Loser", "ATP Challenger Lima", "2026-11-10T09:00:00Z", "2026-11-10T11:00:00Z"),
    ("Other", "Another", "ATP Challenger Kobe", "2026-11-10T09:00:00Z", "2026-11-10T11:00:00Z"),
    ("Winner", "Zed", "ATP Challenger Lima", "2026-11-10T14:00:00Z", "2026-11-10T16:00:00Z")])]
r = T.replay(named, dt.date(2026, 11, 1), dt.date(2026, 11, 30))
check("the replay finds the rules text and the named field agree", (r["events"], r["same_tournament"], r["same_picks"]), (3, 3, 3))

# the feed: a listed pick becomes a Kalshi lead naming its market, with the band published
now = dt.datetime(2026, 11, 21, 14, 0, tzinfo=dt.timezone.utc)
event = dict(event_ticker="KXATPCHALLENGERMATCH-26NOV21AAABBB", product_metadata={"competition": gen}, markets=[])
a, b = dict(ticker="KXATPCHALLENGERMATCH-26NOV21AAABBB-AAA"), dict(ticker="KXATPCHALLENGERMATCH-26NOV21AAABBB-BBB")
q = CP._quote(event, a, b, "Alpha Player", "Beta Player", int((now + dt.timedelta(hours=2)).timestamp()), now, 0.24)
state = {"quotes": {q["id"]: q}, "last_run": now.isoformat(), "error": None}
blob = CP.feed(state, now=now + dt.timedelta(minutes=5))
lead = next(iter(blob["leads"].values()))
check("the lead names the player's contract on Kalshi, Yes", (lead["route"]["market"], lead["route"]["outcome_side"], lead["route"]["venue"]), (a["ticker"], "yes", "kalshi"))
check("the lead is a match result for the home side, in the Tennis league", (lead["bet"], lead["league"], lead["pair"]), ({"kind": "match_result", "side": "home"}, "Tennis", "challenger_won_here|tennis"))
check("the band the follower enforces is published", blob["bands"], {"challenger_won_here|tennis": [0.15, 0.3]})
stale = CP.feed(dict(state, last_run=(now - dt.timedelta(hours=5)).isoformat()), now=now + dt.timedelta(minutes=5))
check("an open pick is not published when the scan is stale", stale["leads"], {})

print(f"\n{'ALL PASS' if not FAILS else str(len(FAILS)) + ' FAILED'}")
raise SystemExit(1 if FAILS else 0)
