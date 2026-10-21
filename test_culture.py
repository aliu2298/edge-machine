#!/usr/bin/env python3
"""Offline checks for the culture lanes (culture_track.py) and the Culture tab (culture_build.py)."""
import datetime as dt
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
                     mkt("KXTRUMPSAY-26OCT19-MAM", 0.50, 0.53, 72, "KXTRUMPSAY-26OCT19", custom_strike={"Word": "Mamdani"})])]
st = {"words": {}}
mp, mc = K.mention_picks(mev, NOW, st, fb)
check("a 99c market is skipped as already near-certain", mc["already near-certain (under 10c or over 90c)"], 1)
check("a word said once in 84 days, at 50c with three days left, is a NO", [(x["id"][-3:], x["side"]) for x in mp],
      [("MAM", "no")])

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
check("an empty ledger still builds the page with all four lanes",
      all(K.LANES[k] in empty for k in K.LANES) and "Observing · paper" in empty, True)
full = {"lanes": {k: {"picks": [], "observations": {}, "error": None} for k in K.LANES}}
full["lanes"]["rt_model"]["picks"] = [dict(id="KXRT-STRA-42", event="KXRT-STRA", series="KXRT", name="Street Fighter",
                                           title="Above 42", side="yes", price=0.45, close=(NOW + dt.timedelta(days=2)).isoformat(),
                                           logged=NOW.isoformat(), status="open", detail="37/87")]
check("a pick shows on the page", "Street Fighter" in KB.build(full, now=NOW), True)

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

print("\nthe headline counts each market once")
dup = {"lanes": {k: {"picks": []} for k in K.LANES}}
dup["lanes"]["rt_model"]["picks"].append(pk("KXRT-SENS-75", "no", logged="2026-10-17T10:00:00+00:00", status="lost", profit=-100.0))
dup["lanes"]["culture_fav_band"]["picks"].append(pk("KXRT-SENS-75", "yes", logged="2026-10-17T12:00:00+00:00", status="won", profit=30.0))
dup["lanes"]["culture_endgame"]["picks"].append(pk("KXOTHER-1", "no", logged="2026-10-17T12:00:00+00:00", status="won", profit=8.0))
rec, note = KB.pooled(dup)
check("two lanes on one ticker count once (the earliest pick), plus the other market",
      (rec["n"], rec["won"], round(rec["roi_fee"], 3), note), (2, 1, -0.46, "each market once"))
html = KB.build(dup, NOW)
check("the tile says so", "Sandbox record · paper · each market once" in html, True)

print(f"\n{'ALL PASS' if not FAILS else str(len(FAILS)) + ' FAILED'}")
sys.exit(1 if FAILS else 0)
