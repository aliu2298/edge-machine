#!/usr/bin/env python3
"""Offline checks for the culture lanes (culture_track.py) and the Culture tab (culture_build.py)."""
import datetime as dt
import html as _html
import json
import sys

import culture_build as KB
import culture_track as K
import site_chrome as C

FAILS = []
UTC = dt.timezone.utc
NOW = dt.datetime(2026, 10, 16, 18, 0, tzinfo=UTC)


def check(label, got, want):
    ok = got == want
    print(f"  {'ok  ' if ok else 'FAIL'} {label}" + ("" if ok else f" (got {got!r}, want {want!r})"))
    if not ok:
        FAILS.append(label)


def mkt(t, bid, ask, hours, ev="EV", **kw):
    return dict(dict(ticker=t, event_ticker=ev, status="active", yes_bid_dollars=str(bid), yes_ask_dollars=str(ask),
                     close_time=(NOW + dt.timedelta(hours=hours)).isoformat(), yes_sub_title=t), **kw)


print("favourite bands: one per event, cheapest, inside the window and spread")
evs = [dict(event_ticker="E1", series_ticker="KXX", title="E1", category="Entertainment",
            markets=[mkt("E1-A", 0.72, 0.75, 10, "E1"), mkt("E1-B", 0.70, 0.72, 10, "E1"),
                     mkt("E1-C", 0.20, 0.29, 10, "E1")]),               # NO at 0.80 but spread 9c
       dict(event_ticker="E2", series_ticker="KXX", title="E2", category="Entertainment",
            markets=[mkt("E2-A", 0.73, 0.75, 72, "E2")])]                # outside 48h
picks, counts = K.band_picks(evs, NOW, K.FAV_BAND, K.FAV_SPREAD, K.FAV_HOURS, "favourite band")
check("the cheaper of two in-band contracts on one event", [(p["id"], p["side"], p["price"]) for p in picks],
      [("E1-B", "yes", 0.72)])
check("the wide one and the far one are counted, not picked",
      (counts["no quote or spread too wide"], counts["outside the entry window"]), (1, 1))
no = [dict(evs[0], markets=[mkt("E1-N", 0.22, 0.24, 10, "E1")])]
check("a NO favourite is priced at 1 - the YES bid",
      [(p["side"], p["price"]) for p in K.band_picks(no, NOW, K.FAV_BAND, K.FAV_SPREAD, K.FAV_HOURS, "x")[0]],
      [("no", 0.78)])
end = [dict(evs[0], markets=[mkt("E1-Z", 0.94, 0.95, 5, "E1")])]
check("the endgame lane takes 0.95 inside 24h",
      [p["price"] for p in K.band_picks(end, NOW, K.END_BAND, K.END_SPREAD, K.END_HOURS, "x")[0]], [0.95])

print("\nTrump mentions: the contract's word rules, the rate, the near-certain guard")
rx = K.term_re("Voter ID")
check("plural and possessive count", [bool(rx.search(s)) for s in ("voter IDs", "Voter ID's", "voter  id")],
      [True, True, True])
check("an inflection or a longer word does not", [bool(K.term_re("tax").search(s)) for s in ("taxed", "taxation")],
      [False, False])
check("a slash is either word", K.terms("Zohran / Mamdani"), ["Zohran", "Mamdani"])
pages = {1: [dict(date="2026-10-10", candidate="Donald Trump", text="Mamdani is a disaster"),
             dict(date="2026-09-01", candidate="Donald Trump", text="nothing here"),
             dict(date="2026-06-01", candidate="Donald Trump", text="Mamdani")]}
fb = lambda url: json.dumps({"data": pages.get(int(url.split("page=")[1].split("&")[0]), [])})
check("said days inside 84 days, only where the text holds the word", K.said_days("Mamdani", NOW, fb), ["2026-10-10"])
p, _why = K.mention_prob(["2026-10-10"], NOW - dt.timedelta(days=2), NOW + dt.timedelta(days=3), NOW)
check("one day in 84 over three days left", round(p, 4), round(1 - (1 - 1 / 84) ** 3, 4))
check("said inside this market's window reads 0.98",
      K.mention_prob(["2026-10-15"], NOW - dt.timedelta(days=2), NOW + dt.timedelta(days=3), NOW)[0], 0.98)
mev = [dict(event_ticker="KXTRUMPSAY-26OCT19", series_ticker="KXTRUMPSAY", title="Trump say", category="Mentions",
            markets=[mkt("KXTRUMPSAY-26OCT19-ICE", 0.99, 1.0, 72, "KXTRUMPSAY-26OCT19", custom_strike={"Word": "Iceland"}),
                     mkt("KXTRUMPSAY-26OCT19-MAM", 0.45, 0.48, 72, "KXTRUMPSAY-26OCT19", custom_strike={"Word": "Mamdani"})])]
st = {"words": {}}
mp, mc = K.mention_picks(mev, NOW, st, fb)
check("a 99c market is skipped as already near-certain", mc["already near-certain (under 10c or over 90c)"], 1)
check("a word said once in 84 days, at 45-48c with three days left, is a NO", [(x["id"][-3:], x["side"]) for x in mp],
      [("MAM", "no")])
# The same word at 50-53c (YES mid 0.515) is the news guard's case from 2026-10-24 (model 0.04).
gl = []
mp2, mc2 = K.mention_picks([dict(mev[0], markets=[mkt("KXTRUMPSAY-26OCT19-MAM", 0.50, 0.53, 72, "KXTRUMPSAY-26OCT19",
                                                      custom_strike={"Word": "Mamdani"})])], NOW, {"words": {}}, fb, log=gl)
check("at 50-53c the NO is refused by the news guard, with its reason logged",
      (mp2, mc2["news guard (YES mid over 0.50, model under 0.25)"], [g["reason"] for g in gl]),
      ([], 1, ["news guard: market 0.52 v model 0.04"]))

print("\nRotten Tomatoes: title, page counts, rounding, the model")
check("Kalshi's title, without the suffix", K.rt_name({}, {"title": "Street Fighter Rotten Tomatoes score?"}), "Street Fighter")
search = ('<search-page-media-row cast="x"><a href="https://www.rottentomatoes.com/m/street_fighter_2026" '
          'slot="title">Street Fighter</a></search-page-media-row>'
          '<search-page-media-row><a href="https://www.rottentomatoes.com/tv/street_fighter" slot="title">'
          'Street Fighter</a></search-page-media-row>')
check("the exact-title movie result", K.rt_search("Street Fighter", "movie", lambda u: search),
      "https://www.rottentomatoes.com/m/street_fighter_2026")
check("and the TV one for a TV ladder", K.rt_search("Street Fighter", "tv", lambda u: search),
      "https://www.rottentomatoes.com/tv/street_fighter")
pagehtml = '"criticsScore":{"likedCount":37,"notLikedCount":50,"ratingCount":87,"reviewCount":87,"score":"43"}'
check("liked, reviews and the shown score off the page", K.rt_counts("u", lambda u: pagehtml), (37, 87, 43))
check("rounded half up: 37 of 87 shows 43", K.displayed(37, 87), 43)
check("no reviews still to come: certain either side of the line",
      (K.p_above(37, 87, 0, 42), K.p_above(37, 87, 0, 43)), (1.0, 0.0))
mid = K.p_above(37, 87, 20, 42)
check("with 20 to come it is a real probability", 0.2 < mid < 0.8, True)
snap = lambda h, n: dict(at=(NOW - dt.timedelta(hours=h)).isoformat(), count=n)
check("no bet before 12h of snapshots", K.expected_reviews([snap(6, 80), snap(0, 87)], 87, 40), None)
check("then the measured pace, halved", K.expected_reviews([snap(20, 67), snap(0, 87)], 87, 40), 20)

print("\nsettlement on Kalshi's own result, either side")
lane = {"picks": [dict(id="A", side="yes", price=0.75, status="open"), dict(id="B", side="no", price=0.80, status="open")]}
res = {"A": {"ticker": "A", "status": "finalized", "result": "yes"}, "B": {"ticker": "B", "status": "finalized", "result": "yes"}}
K.settle(lane, NOW, lambda path: {"market": res[path.split("/")[-1]]})
check("a YES on a yes wins, a NO on a yes loses", [r["status"] for r in lane["picks"]], ["won", "lost"])
check("the win is paid after the fee", lane["picks"][0]["profit"], round(100 * (1 / (0.75 + 0.07 * 0.75 * 0.25) - 1), 2))

print("\nthe Culture tab")
check("Culture is in the site navigation", any(k == "culture" for k, _l, _u in C.PAGES), True)
empty = KB.build({"lanes": {k: {"picks": [], "observations": {}, "error": None} for k in K.LANES}}, now=NOW)
check("an empty ledger still builds the page: the standard, the lanes, the model lanes, the archive",
      all(f'id="{i}"' in empty for i in ("standard", "lanes", "models", "archive")), True)

print("\none market, one side, one lane (2026-10-20)")


def pk(t, side, ev="EV", logged="2026-10-16T18:00:00+00:00", status="open", profit=None, **kw):
    return dict(dict(id=t, event=ev, side=side, price=0.75, logged=logged, status=status, profit=profit,
                     close="2026-10-18T00:00:00+00:00", title=t, name=ev, series=str(t).split("-")[0]), **kw)


st = {"lanes": {k: {"picks": []} for k in K.LANES}}
st["lanes"]["rt_model"]["picks"].append(pk("KXRT-WHA-70", "yes", "KXRT-WHA", status="lost", profit=-100.0))
c = __import__("collections").Counter()
K.record(st["lanes"]["culture_endgame"], [pk("KXRT-WHA-70", "no", "KXRT-WHA")], by="event", state=st,
         key="culture_endgame", counts=c)
check("a ticker any lane holds, even settled, is skipped and counted 'held by'",
      (len(st["lanes"]["culture_endgame"]["picks"]), dict(c)), (0, {"held by rt_model": 1}))
c.clear()
K.record(st["lanes"]["culture_fav_band"], [pk("KXRT-WHA-80", "no", "KXRT-WHA")], by="event", state=st,
         key="culture_fav_band", counts=c)
check("another rung of the same RT film bet the other way is a conflict",
      (len(st["lanes"]["culture_fav_band"]["picks"]), dict(c)), (0, {"conflicts with rt_model in the same event": 1}))
c.clear()
K.record(st["lanes"]["culture_fav_band"], [pk("KXRT-WHA-60", "yes", "KXRT-WHA")], by="event", state=st,
         key="culture_fav_band", counts=c)
check("the same direction on another rung is not a conflict", len(st["lanes"]["culture_fav_band"]["picks"]), 1)
st["lanes"]["mentions_rate"]["picks"].append(pk("KXTRUMPSAY-26OCT19-BIBI", "no", "KXTRUMPSAY-26OCT19"))
c.clear()
K.record(st["lanes"]["culture_endgame"], [pk("KXTRUMPSAY-26OCT19-TARI", "yes", "KXTRUMPSAY-26OCT19")], by="event",
         state=st, key="culture_endgame", counts=c)
check("opposite sides on two DIFFERENT words of one mention event are separate questions",
      (len(st["lanes"]["culture_endgame"]["picks"]), dict(c)), (1, {}))
check("the strike is read off an RT ticker when the row carries none", K.strike_of(pk("KXRT-SENS-75", "yes")), (75.0, "greater"))
check("priority within a scan: mentions, endgame, RT model, favourite band", K.PRIORITY,
      ("mentions_rate", "culture_endgame", "rt_model", "culture_fav_band"))

# A run where two lanes see the same market in one scan: the higher-priority lane gets it.
ev = dict(event_ticker="KXSTEAMTOPSELLER-26OCT20", series_ticker="KXSTEAMTOPSELLER", title="Steam", category="Entertainment",
          markets=[mkt("KXSTEAMTOPSELLER-26OCT20-AIO", 0.05, 0.07, 10, "KXSTEAMTOPSELLER-26OCT20")])


def fake(path):
    if path.startswith("events"):
        return {"events": [ev], "cursor": ""}
    return {"market": {}}


_real_band = K.band_picks
# Both band lanes offered the SAME market in one scan (the bands are disjoint, so stub them).
K.band_picks = lambda events, now, band, spread, hours, lane: (
    [K.entry(ev["markets"][0], ev, "no" if lane == "endgame" else "yes", 0.9, now)], __import__("collections").Counter())
try:
    rs = K.run({"lanes": {k: {"picks": [], "observations": {}, "error": None} for k in K.LANES}}, {}, now=NOW,
               fetch=fake, webfetch=lambda *a, **k: (_ for _ in ()).throw(RuntimeError("offline")))
finally:
    K.band_picks = _real_band
got = {k: [(p["id"], p["side"]) for p in v["picks"]] for k, v in rs["lanes"].items() if v["picks"]}
check("one scan, two lanes on one market: endgame (higher priority) takes it, the favourite band never does", got,
      {"culture_endgame": [("KXSTEAMTOPSELLER-26OCT20-AIO", "no")]})
check("and the favourite band's scan counts why",
      rs["lanes"]["culture_fav_band"]["observations"]["reasons"], {"held by culture_endgame": 1})

print("\nrt_model never claims certainty")
check("P is clamped to 0.05-0.95", K.P_CLAMP, (0.05, 0.95))
_saved = (K.rt_counts, K.expected_reviews, K.p_above)
rev = dict(event_ticker="KXRT-IPL", series_ticker="KXRT", title="I Play Rocky", category="Entertainment",
           markets=[mkt("KXRT-IPL-82", 0.27, 0.29, 30, "KXRT-IPL", floor_strike=82, strike_type="greater")])
try:
    K.rt_counts = lambda url, fetch=None: (90, 100, 90)
    K.expected_reviews = lambda hist, count, hours: 10
    for raw, want in ((1.0, 0.95), (0.0, 0.05)):
        K.p_above = lambda *a, _r=raw: _r
        out, _c = K.rt_picks([rev], NOW, {"rt_urls": {"KXRT-IPL": "u"}}, {}, fetch=None)
        check(f"a raw P of {raw:.2f} is used as {want:.2f}", [p.get("model") for p in out], [want])
finally:
    K.rt_counts, K.expected_reviews, K.p_above = _saved

import re as _re

print("\n2026-10-24: three lanes retired, mentions_rate news guard and edge cap")
RET = dt.datetime(2026, 10, 24, 18, 0, tzinfo=UTC)
check("the three Sandbox lanes are retired on 2026-10-24, mentions_rate is not",
      ({k: K.retired(k, RET) for k in K.LANES}, K.retired("culture_endgame", dt.datetime(2026, 10, 24, 3, 0, tzinfo=UTC))),
      ({"culture_fav_band": True, "culture_endgame": True, "mentions_rate": False, "rt_model": True}, False))
check("the one-market priority list is unchanged", K.PRIORITY,
      ("mentions_rate", "culture_endgame", "rt_model", "culture_fav_band"))


def ledger_with_rows():
    s = {"lanes": {k: {"picks": [], "observations": {}, "error": None} for k in K.LANES}, "rt_urls": {}, "words": {}}
    for k in ("culture_endgame", "culture_fav_band", "rt_model"):
        s["lanes"][k]["picks"] += [pk(f"{k}-OLD", "yes", logged="2026-10-20T00:00:00+00:00", status="won", profit=5.0),
                                   pk(f"{k}-OPEN", "yes", f"{k}-EV", logged="2026-10-21T00:00:00+00:00")]
    return s


ret_state = ledger_with_rows()
before = json.loads(json.dumps({k: ret_state["lanes"][k]["picks"] for k in K.LANES}))
offer = dict(event_ticker="KXOSC-26", series_ticker="KXOSC", title="Oscars", category="Entertainment",
             markets=[mkt("KXOSC-26-A", 0.74, 0.76, 10, "KXOSC-26"), mkt("KXOSC-26-B", 0.93, 0.94, 10, "KXOSC-26")])
word = dict(event_ticker="KXTRUMPSAY-26OCT26", series_ticker="KXTRUMPSAY", title="Trump say", category="Mentions",
            markets=[mkt("KXTRUMPSAY-26OCT26-MAM", 0.45, 0.48, 72, "KXTRUMPSAY-26OCT26", custom_strike={"Word": "Mamdani"},
                         open_time="2026-10-19T14:00:00Z",
                         close_time=(RET + dt.timedelta(hours=72)).isoformat())])
calls = []
_saved_steps = (K.band_picks, K.rt_picks)
K.band_picks = lambda *a, **k: (calls.append("band"), _saved_steps[0](*a, **k))[1]
K.rt_picks = lambda *a, **k: (calls.append("rt"), _saved_steps[1](*a, **k))[1]


def ret_fetch(path):
    if path.startswith("events"):
        return {"events": [offer, word], "cursor": ""}
    t = urllib.parse.unquote(path.split("/")[-1])
    if t.endswith("-OPEN"):
        return {"market": {"ticker": t, "status": "finalized", "result": "no"}}
    return {"market": {"ticker": t, "status": "active"}}


import urllib.parse
snaps = {}
fb_ret = lambda url: json.dumps({"data": []})            # the word is never in the transcripts: P(said) 0
try:
    K.run(ret_state, snaps, now=RET, fetch=ret_fetch, webfetch=fb_ret)
finally:
    K.band_picks, K.rt_picks = _saved_steps
for k in ("culture_endgame", "culture_fav_band", "rt_model"):
    picks = ret_state["lanes"][k]["picks"]
    check(f"{k}: retired, it logs nothing new and keeps both rows", [p["id"] for p in picks],
          [p["id"] for p in before[k]])
    check(f"{k}: its open pick still settles (a NO result: the YES loses)", [p["status"] for p in picks], ["won", "lost"])
    check(f"{k}: the scan says retired", (ret_state["lanes"][k]["observations"].get("retired"),
                                          ret_state["lanes"][k]["error"]), ("2026-10-24", None))
check("no band scan and no Rotten Tomatoes scan ran, so no snapshot was taken", (calls, snaps), ([], {}))
check("mentions_rate still logs on its own (the priority list with only it active)",
      [(p["id"], p["side"]) for p in ret_state["lanes"]["mentions_rate"]["picks"]], [("KXTRUMPSAY-26OCT26-MAM", "no")])
mm = ret_state["lanes"]["mentions_rate"]["picks"][0]
check("its edge is capped at 0.25 (model edge 0.43), the raw edge kept and the detail says so",
      (mm["edge"], mm["edge_raw"] > 0.25, "edge capped" in mm["detail"], mm["model"], mm["yes_mid"]),
      (0.25, True, True, 0.0, 0.465))
check("and the scan counts the cap", ret_state["lanes"]["mentions_rate"]["observations"]["reasons"].get("edge capped"), 1)

# The five settled losses to 2026-10-24, as the ledger recorded them: NO price, so YES bid = 1 - price;
# the spread is unknown, so the YES mid is read at the bid plus 1c (a 2c spread).
LOSSES = {"Ethanol": (0.21, 0.2081), "Deere": (0.39, 0.0), "Vivek": (0.46, 0.1276),
          "Nobel": (0.68, 0.2548), "Bibi": (0.72, 0.1951)}
got = {w: K.news_guard("no", round(1 - px + 0.01, 2), p) for w, (px, p) in LOSSES.items()}
check("the guard refuses Deere (market 0.62 v model 0.00) and Vivek (0.55 v 0.13), with the reason",
      (got["Deere"], got["Vivek"]), ("news guard: market 0.62 v model 0.00", "news guard: market 0.55 v model 0.13"))
check("threshold raised to 0.25 (2026-10-24): Ethanol (model 0.208) is now refused too",
      (got["Ethanol"], K.news_guard("no", 0.79, 0.208)),
      ("news guard: market 0.80 v model 0.21", "news guard: market 0.79 v model 0.21"))
check("Nobel (market 0.33) and Bibi (market 0.29) still pass: their YES sat under 0.50", (got["Nobel"], got["Bibi"]), (None, None))
check("a normal NO is allowed: YES mid 0.30, model 0.05", K.news_guard("no", 0.30, 0.05), None)
check("the model edge: 0.249 is refused, exactly 0.25 and 0.26 pass (market over 0.50)",
      (K.news_guard("no", 0.70, 0.249), K.news_guard("no", 0.70, 0.25), K.news_guard("no", 0.70, 0.26)),
      ("news guard: market 0.70 v model 0.25", None, None))
check("the market edge is unchanged: mid exactly 0.50 passes, 0.51 is guarded; a YES is never guarded",
      (K.news_guard("no", 0.50, 0.05), K.news_guard("no", 0.51, 0.05) is not None, K.news_guard("yes", 0.70, 0.05)),
      (None, True, None))
check("the thresholds are the registered ones: market 0.50, model 0.25, edge cap 0.25",
      (K.NEWS_GUARD, K.EDGE_CAP), (dict(market_over=0.50, model_under=0.25), 0.25))
check("the edge cap: 0.59 -> 0.25 capped, 0.10 and 0.25 unchanged, 0.03 still under the 5c threshold",
      (K.capped(0.59), K.capped(0.10), K.capped(0.25), K.capped(0.03)[0] < K.EDGE_MIN), ((0.25, True), (0.10, False), (0.25, False), True))
check("the amendment is dated in the lane's registered text, with the raised threshold",
      ("Amended 2026-10-24" in K.RULES["mentions_rate"], "0.25 (news guard, raised from 0.20 on 2026-10-24" in K.RULES["mentions_rate"],
       "under 0.20" in K.RULES["mentions_rate"]), (True, True, False))

print("\nthe Culture page's Archive: the old lanes, one line each, records kept")
real = K.load()
OUT = dt.datetime(2026, 10, 26, 18, 0, tzinfo=UTC)          # after Trump mentions left Production
rt = _re.sub(r"\s+", " ", _re.sub(r"<[^>]+>", " ", _html.unescape(KB.build(real, OUT))))
_rh = KB.build(real, OUT)
arch = _re.sub(r"\s+", " ", _re.sub(r"<[^>]+>", " ", _html.unescape(_rh[_rh.find('id="archive"'):])))
check("the live ledger builds; the Archive names mentions_rate, culture_endgame and culture_fav_band, not rt_model",
      ("(mentions_rate)" in arch, "(culture_endgame)" in arch, "(culture_fav_band)" in arch, "(rt_model)" in arch), (True, True, True, False))
check("each retired lane carries its dated retirement and record",
      all(f"retired 2026-10-24 at {K.RETIRED[k]['at']}" in arch for k in ("culture_endgame", "culture_fav_band")), True)
small = ledger_with_rows()
for k in K.RETIRED:
    if k != "mentions_rate":                  # retired 2026-10-31, checked below
        small["lanes"][k]["picks"][0]["payout"] = 1.0
sh = _re.sub(r"\s+", " ", _re.sub(r"<[^>]+>", " ", _html.unescape(KB.build(small, RET))))
check("a retired lane's line gives its record now, per contract, and what still settles",
      sh.count("record now 1/1 won, +31.0% after fees per contract; 1 open still settling"), 2)
check("mentions_rate is in the Archive as out of Production 2026-10-26, still logging on paper",
      "in Production 2026-10-20 to 2026-10-26, still logging on paper in the Sandbox under its 2026-10-26 amendment" in arch, True)
check("the Archive is collapsed", '<details class="fold sec" id="archive">' in KB.build(real, OUT), True)

print("\n2026-10-26: back in the Sandbox, the NO floor and the monthly/company series out")
AM = dt.datetime(2026, 10, 26, 18, 0, tzinfo=UTC)                # after the amendment (17:00Z)
PRE = dt.datetime(2026, 10, 26, 16, 0, tzinfo=UTC)               # the same day, before it
check("the amendment's registered terms", (K.AMENDED_2, K.AMENDED_2_AT, K.NO_FLOOR, K.EXCLUDED_SERIES),
      ("2026-10-26", "2026-10-26T17:00:00+00:00", 0.60, ("KXTRUMPSAYMONTH", "KXTRUMPSAYCOMPANY")))
check("it is live from 17:00Z on 2026-10-26, not before",
      (K.amended_2(PRE), K.amended_2(dt.datetime(2026, 10, 26, 17, 0, tzinfo=UTC)), K.amended_2(AM)), (False, True, True))
check("the news guard and the edge cap are unchanged", (K.NEWS_GUARD, K.EDGE_CAP),
      (dict(market_over=0.50, model_under=0.25), 0.25))
check("the amendment is dated in the lane's registered text",
      ("Amended 2026-10-26: a NO priced under 0.60 is refused" in K.RULES["mentions_rate"],
       "KXTRUMPSAYMONTH" in K.RULES["mentions_rate"], "KXTRUMPSAYCOMPANY" in K.RULES["mentions_rate"],
       "Amended 2026-10-24" in K.RULES["mentions_rate"]), (True, True, True, True))
fb_am = lambda url: json.dumps({"data": [dict(date="2026-10-10", candidate="Donald Trump", text="Mamdani is a disaster")]
                                if "page=1&" in url else []})
_often = [(dt.date(2026, 10, 25) - dt.timedelta(days=i)).isoformat() for i in range(0, 80, 2)]
fb_often = lambda url: json.dumps({"data": [dict(date=d, candidate="Donald Trump", text="Tariff, tariff") for d in _often]
                                   if "page=1&" in url else []})


def wm(series, code, bid, ask, word="Mamdani", at=AM):
    ev = f"{series}-26NOV01"
    return dict(event_ticker=ev, series_ticker=series, title="Trump say", category="Mentions",
                markets=[dict(ticker=f"{ev}-{code}", event_ticker=ev, status="active", yes_bid_dollars=str(bid),
                              yes_ask_dollars=str(ask), close_time=(at + dt.timedelta(hours=72)).isoformat(),
                              open_time=(at - dt.timedelta(days=1)).isoformat(), custom_strike={"Word": word})])


def scan(evs, at=AM, fetch=fb_am):
    out, c = K.mention_picks(evs, at, {"words": {}}, fetch)
    return [(p["id"].split("-")[-1], p["side"], p["price"], p.get("amended")) for p in out], dict(c)


got, c = scan([wm("KXTRUMPSAY", "LOW", 0.45, 0.48)])
check("a NO at 0.55 (YES 45-48c, model 0.04) is refused by the floor, and the scan counts it",
      (got, c.get("NO under 0.60 (floor 2026-10-26)")), ([], 1))
got, _c = scan([wm("KXTRUMPSAY", "EDGE", 0.40, 0.42)])
check("a NO at exactly 0.60 passes, stamped with the amendment", got, [("EDGE", "no", 0.6, "2026-10-26")])
got, _c = scan([wm("KXTRUMPSAY", "OK", 0.30, 0.32)])
check("a NO at 0.70 passes, stamped", got, [("OK", "no", 0.7, "2026-10-26")])
got, _c = scan([wm("KXTRUMPSAY", "TARI", 0.30, 0.33, word="Tariff")], fetch=fb_often)
check("the floor is NO-only: a YES at 0.33 is still bought", got, [("TARI", "yes", 0.33, "2026-10-26")])
got, c = scan([wm("KXTRUMPSAYMONTH", "OK", 0.30, 0.32), wm("KXTRUMPSAYCOMPANY", "OK", 0.30, 0.32),
               wm("KXTRUMPSAYCOUNTRY", "OK", 0.30, 0.32)])
check("the monthly and company series are not entered; the country series still is",
      (got, c.get("monthly or company series (excluded 2026-10-26)")),
      ([("OK", "no", 0.7, "2026-10-26")], 2))
got, _c = scan([wm("KXTRUMPSAY", "LOW", 0.45, 0.48, at=PRE), wm("KXTRUMPSAYMONTH", "OK", 0.30, 0.32, at=PRE)], at=PRE)
check("before 17:00Z the old rule still runs: the 0.55 NO and the monthly market, neither stamped",
      got, [("LOW", "no", 0.55, None), ("OK", "no", 0.7, None)])
# The floor sits before the news guard: a NO the market prices over 0.50 is never cheaper than 0.50,
# so every news-guard case under 0.60 is now the floor's.
got, c = scan([wm("KXTRUMPSAY", "NEWS", 0.50, 0.53)])
check("a 0.50 NO (YES mid 0.515) is the floor's refusal now, not the guard's",
      (got, c.get("NO under 0.60 (floor 2026-10-26)"), c.get("news guard (YES mid over 0.50, model under 0.25)")),
      ([], 1, None))

print("\n2026-10-26: existing rows untouched, the record split at the amendment")
rows = [pk("KXTRUMPSAY-26OCT26-A", "no", logged="2026-10-25T10:00:00+00:00", status="lost", profit=-100.0, payout=0, price=0.30),
        pk("KXTRUMPSAY-26OCT26-B", "no", logged="2026-10-26T16:41:00+00:00", status="open", price=0.13),
        pk("KXTRUMPSAY-26NOV02-C", "no", logged="2026-10-26T17:41:00+00:00", status="won", profit=10.0, payout=1,
           price=0.88, amended="2026-10-26")]
amst = {"lanes": {k: {"picks": [], "observations": {}, "error": None} for k in K.LANES}, "words": {}}
amst["lanes"]["mentions_rate"]["picks"] = json.loads(json.dumps(rows))
pre, post, pre_open = KB.amendment_split(amst["lanes"]["mentions_rate"]["picks"])
check("before: the unstamped rows (a 13c NO logged the same morning stays open); after: the stamped one",
      (pre[:2], post[:2], pre_open), ((0, 1), (1, 1), 1))
held = json.loads(json.dumps(amst["lanes"]["mentions_rate"]["picks"]))
K.run(amst, {}, now=AM, fetch=lambda path: {"events": [], "cursor": ""} if path.startswith("events")
      else {"market": {"ticker": path.split("/")[-1], "status": "active"}}, webfetch=fb_am)
check("a scan after the amendment leaves every existing row as it was (open ones still open)",
      [(r["id"], r["status"], r["price"]) for r in amst["lanes"]["mentions_rate"]["picks"]],
      [(r["id"], r["status"], r["price"]) for r in held])
ah = _re.sub(r"\s+", " ", _re.sub(r"<[^>]+>", " ", _html.unescape(KB.build(amst, AM))))
check("its Archive line gives the record before and after the amendment, and what is open",
      ("before the amendment 0/1 won" in ah, "from it 1/1 won" in ah, "; 1 open." in ah), (True, True, True))

print("\n2026-10-26: rt_model revived on a fresh record, its snapshot collector back on")
REV = dt.datetime(2026, 10, 27, 1, 0, tzinfo=UTC)               # after the revival (00:00Z)
EVE = dt.datetime(2026, 10, 26, 23, 0, tzinfo=UTC)              # the same evening, before it
check("the revival's registered terms; the retirement stays as dated history",
      (K.REVIVED["rt_model"]["on"], K.REVIVED["rt_model"]["at"], K.REVIVED["rt_model"]["review"], K.RT_LINE_GAP,
       K.RETIRED["rt_model"]["on"], K.RETIRED["rt_model"]["at"]),
      ("2026-10-26", "2026-10-27T00:00:00+00:00", 10, 1.0, "2026-10-24", "2/4 won, −25.7% after fees"))
check("retired until the revival, live from it; the other two stay retired",
      ({k: K.retired(k, EVE) for k in K.LANES}, {k: K.retired(k, REV) for k in K.LANES}),
      ({"culture_fav_band": True, "culture_endgame": True, "mentions_rate": False, "rt_model": True},
       {"culture_fav_band": True, "culture_endgame": True, "mentions_rate": False, "rt_model": False}))
check("the amendment is dated in the lane's registered text",
      "Amended 2026-10-26 (revived on a fresh record): a rung is skipped when the current score (liked / reviews x 100) "
      "is within 1 point of its line" in K.RULES["rt_model"], True)
check("the 1-point skip: Above 70 at 71 and the Above 75 at 75 (both losses), 69 v 70; not 72 v 70 or 73.5 v 75",
      [K.near_line(l, 100, s) for l, s in ((71, 70), (75, 75), (69, 70), (72, 70))] + [K.near_line(147, 200, 75)],
      [True, True, True, False, False])
check("exactly 1 point (76 of 100 v 75) is skipped",
      K.near_line(76, 100, 75), True)

_rs = (K.rt_counts, K.expected_reviews, K.p_above)
lad = dict(event_ticker="KXRT-REV", series_ticker="KXRT", title="Revival Film", category="Entertainment",
           markets=[dict(ticker=f"KXRT-REV-{s}", event_ticker="KXRT-REV", status="active", yes_bid_dollars=str(b),
                         yes_ask_dollars=str(a), close_time=(REV + dt.timedelta(hours=30)).isoformat(),
                         floor_strike=s, strike_type="greater")
                    for s, b, a in ((90, 0.50, 0.53), (82, 0.27, 0.29))])
try:
    K.rt_counts = lambda url, fetch=None: (181, 200, 91)       # score 90.5: within 1 of 90, 8.5 over 82
    K.expected_reviews = lambda hist, count, hours: 10
    K.p_above = lambda liked, count, future, strike: 0.95 if strike == 82 else 0.50
    out, c = K.rt_picks([lad], REV, {"rt_urls": {"KXRT-REV": "u"}}, {}, fetch=None)
    check("after the revival: the 90 rung (score 90.5) is skipped and counted, the 82 rung is entered, stamped",
          ([(p["id"], p["side"], p.get("revived")) for p in out], c.get("within 1 point of the line")),
          ([("KXRT-REV-82", "yes", "2026-10-26")], 1))
    only = dict(lad, markets=[lad["markets"][0]])
    out, c = K.rt_picks([only], REV, {"rt_urls": {"KXRT-REV": "u"}}, {}, fetch=None)
    check("a ladder whose only rung sits on the line logs nothing, and is not read as 'collecting pace'",
          (out, c.get("within 1 point of the line"), c.get("collecting review pace (12h of snapshots)")), ([], 1, None))
    K.p_above = lambda liked, count, future, strike: 0.95
    out, c = K.rt_picks([only], EVE, {"rt_urls": {"KXRT-REV": "u"}}, {}, fetch=None)
    check("before the revival the skip does not apply and nothing is stamped",
          [(p["id"], p.get("revived")) for p in out], [("KXRT-REV-90", None)])
finally:
    K.rt_counts, K.expected_reviews, K.p_above = _rs

_h = lambda hrs_ago, n: dict(at=(REV - dt.timedelta(hours=hrs_ago)).isoformat(), count=n)
check("the pace needs 12h inside the last 24h: two-day-old snapshots and one fresh read give no pace yet",
      (K.expected_reviews([_h(70, 100), _h(56, 110), _h(0, 120)], 120, 30),
       K.expected_reviews([_h(14, 100), _h(0, 128)], 128, 30)), (None, 30))

print("\n2026-10-26: the collector runs again with the lane")
rt_ev = dict(lad, markets=[dict(lad["markets"][1])])
srch = ('<search-page-media-row><a href="https://www.rottentomatoes.com/m/revival_film" slot="title">Revival Film</a>'
        '</search-page-media-row>')
pg_rt = '"criticsScore":{"likedCount":181,"reviewCount":200,"score":"91"}'
web_rt = lambda url: srch if "search?" in url else pg_rt
fetch_rt = lambda path: ({"events": [rt_ev], "cursor": ""} if path.startswith("events")
                         else {"market": {"ticker": path.split("/")[-1], "status": "active"}})
fresh_state = lambda: {"lanes": {k: {"picks": [], "observations": {}, "error": None} for k in K.LANES},
                       "rt_urls": {}, "words": {}}
for when, want in ((EVE, False), (REV, True)):
    snaps_rt, st_rt = {}, fresh_state()
    K.run(st_rt, snaps_rt, now=when, fetch=fetch_rt, webfetch=web_rt)
    got = snaps_rt.get("KXRT-REV") or []
    check(f"{when:%Y-%m-%d %H:%MZ}: " + ("the snapshot collector runs" if want else "still retired, no snapshot"),
          (len(got) == 1, (got[0]["liked"], got[0]["count"]) if got else None,
           st_rt["lanes"]["rt_model"]["observations"].get("retired")),
          (True, (181, 200), None) if want else (False, None, "2026-10-24"))
check("  and the first revived scan says why it waits: 12h of snapshots before any bet",
      st_rt["lanes"]["rt_model"]["observations"]["reasons"], {"collecting review pace (12h of snapshots)": 1})
wf = open(".github/workflows/culture.yml").read()
check("culture.yml runs the scan hourly and saves the snapshots",
      ("cron: '41 * * * *'" in wf, "run: python3 culture_track.py" in wf, "data/rt_snapshots.json" in wf.split("git add", 1)[1]),
      (True, True, True))

print("\n2026-10-26: the fresh record and the pre-retirement history, apart")
rv = fresh_state()
rv["lanes"]["rt_model"]["picks"] = [
    pk("KXRT-OLD-70", "yes", "KXRT-OLD", logged="2026-10-20T00:00:00+00:00", status="lost", profit=-100.0, payout=0),
    pk("KXRT-OLD-60", "yes", "KXRT-OLD", logged="2026-10-21T00:00:00+00:00", status="won", profit=30.0, payout=1),
    pk("KXRT-OLD2-80", "no", "KXRT-OLD2", logged="2026-10-22T00:00:00+00:00"),
    pk("KXRT-NEW-82", "yes", "KXRT-NEW", logged="2026-10-27T01:00:00+00:00", status="won", profit=30.0, payout=1,
       revived="2026-10-26")]
held_rt = json.loads(json.dumps(rv["lanes"]["rt_model"]["picks"]))
check("the fresh record is the stamped entry alone", [p["id"] for p in K.fresh("rt_model", rv["lanes"]["rt_model"]["picks"])],
      ["KXRT-NEW-82"])
new_rec, old_rec, old_open = KB.history_split("rt_model", rv["lanes"]["rt_model"]["picks"])
check("history_split: revived 1/1; history 1/2 with one still open", (new_rec[:2], old_rec[:2], old_open), ((1, 1), (1, 2), 1))
_rv = KB.build(rv, REV)
_txt = lambda h: _re.sub(r"\s+", " ", _re.sub(r"<[^>]+>", " ", _html.unescape(h)))
models = _txt(_rv[_rv.find('id="models"'):_rv.find('id="archive"')])
rvh = _txt(_rv)
check("the page: rt_model under Model lanes with the note, both records apart; not in the Archive",
      ("revived 2026-10-26 · fresh record · review at 10" in models, "Revived record: 1/1 won" in models,
       "Pre-retirement history (retired 2026-10-24 at 2/4 won, −25.7% after fees, not counted): 1/2 won" in models,
       "1 still open" in models, "(rt_model)" in _txt(_rv[_rv.find('id="archive"'):])), (True, True, True, True, False))
check("the ledger rows are untouched by the page", rv["lanes"]["rt_model"]["picks"], held_rt)
check("before the revival the Model lanes line says retired, with the revival time",
      "Rotten Tomatoes model · retired 2026-10-24; revived from 2026-10-27 00:00Z." in
      _re.sub(r"\s+", " ", _re.sub(r"<[^>]+>", " ", KB.build(rv, EVE))), True)

print("\nTrump mentions (mentions_rate) retired 2026-10-31: no new entries, open picks keep settling")
check("retired with its record and reason; Eastern date gate",
      (K.RETIRED["mentions_rate"]["on"], K.RETIRED["mentions_rate"]["at"], K.retired("mentions_rate", dt.datetime(2026, 10, 31, 3, 0, tzinfo=UTC)),
       K.retired("mentions_rate", dt.datetime(2026, 10, 31, 5, 0, tzinfo=UTC))), ("2026-10-31", "23/38 won, −8.8% after fees", False, True))
gone = ledger_with_rows()
gone["lanes"]["mentions_rate"]["picks"].append(pk("KXTRUMPSAY-26OCT30-OPEN", "no", "KXTRUMPSAY-26OCT30", logged="2026-10-29T00:00:00+00:00"))
LATE = dt.datetime(2026, 11, 1, 12, 0, tzinfo=UTC)
K.run(gone, {}, now=LATE, fetch=ret_fetch, webfetch=fb_ret)
mr = gone["lanes"]["mentions_rate"]
check("a scan after the date logs no new Trump entry (the open word market is not entered), and the lane's scan says retired",
      ([p["id"] for p in mr["picks"]], mr["observations"].get("retired")), (["KXTRUMPSAY-26OCT30-OPEN"], "2026-10-31"))
check("its open pick still settles (a NO on a market that resolved no: won)", [p["status"] for p in mr["picks"]], ["won"])
check("the Archive line says retired, no new entries, with the record and what still settles",
      "retired 2026-10-31 at 23/38 won, −8.8% after fees" in _re.sub(r"\s+", " ", _re.sub(r"<[^>]+>", " ", _html.unescape(KB.build(gone, LATE)[KB.build(gone, LATE).find('id="archive"'):]))), True)

print("\nthe events listing: past D.pages' default 100 pages (21,232 open events on 2026-10-31), the RT model's scan root cause")
import daily_track as _D
def _paged(n_pages):
    def f(path):
        cur = int(path.split("&cursor=")[1].split("&")[0]) if "&cursor=" in path else 0
        evs = [dict(event_ticker=f"E{cur}-{i}", category="Entertainment" if i == 0 else "Sports") for i in range(3)]
        return {"events": evs, "cursor": str(cur + 1) if cur + 1 < n_pages else ""}
    return f
raised = None
try:
    _D.pages("events?status=open&limit=200", "events", _paged(150))
except ValueError as _e:
    raised = str(_e)
check("the default cap still raises on a listing that does not end in 100 pages", raised, "Pagination limit reached; no entries from this scan")
got = K.culture_events(_paged(150))
check("culture_events reads a 150-page listing to the end and keeps only the Culture categories", (len(got), K.EVENT_PAGES), (150, 400))
raised = None
try:
    K.culture_events(_paged(500))
except ValueError as _e:
    raised = str(_e)
check("a listing that still does not end inside the new cap raises, as before", raised, "Pagination limit reached; no entries from this scan")

print("\na timed-out read is retried like a 5xx (the heavy events listing timed out once on 2026-10-31)")
class _R:
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def read(self, *a): return b'{"events": [], "cursor": ""}'
_n = []
def _op(req, timeout=0):
    _n.append(1)
    if len(_n) < 3:
        raise TimeoutError("The read operation timed out")
    return _R()
_slept = []
check("two timeouts then a good read returns the page, after two backoffs",
      (_D.get("events?x=1", sleep=_slept.append, clock=lambda: 0.0, opener=_op), len(_n), [s for s in _slept if s >= 1]), ({"events": [], "cursor": ""}, 3, [1, 2]))
_n.clear()
def _bad(req, timeout=0):
    raise TimeoutError("always")
_err = None
try:
    _D.get("events?x=1", sleep=lambda s: None, clock=lambda: 0.0, opener=_bad)
except TimeoutError as e:
    _err = str(e)
check("a read that never recovers still raises after the last attempt", _err, "always")

print(f"\n{'ALL PASS' if not FAILS else str(len(FAILS)) + ' FAILED'}")
sys.exit(1 if FAILS else 0)
