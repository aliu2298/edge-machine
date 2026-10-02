#!/usr/bin/env python3
"""The tennis favourite band keeps ATP, WTA Doubles, and UTR only.

tennis_fav_band_3h and every basket lane that cuts legs from that band
refuse every other tour, including ATP Doubles and ATP Challenger qualifying,
which share the letters "atp" and must not match by prefix. The price band
stays 0.77-0.81 and the window stays 3 hours.

Fails on main: a dropped tour inside the window is still picked, and a
dropped-tour leg still enters a basket. No network.
"""
import collections
import math
from datetime import datetime, timedelta, timezone

import sandbox_build as SB
import sandbox_sources as S
import sandbox_track as T

FAILS = []
KEEP = frozenset({"atp", "wtadb", "utr"})
DROPPED = ("wta", "atpch", "atpcq", "itfme", "itfwo", "atpdb", "lavercup")
BASKETS = ("tennis_combo2", "tennis_combo3", "tennis_combo4",
           "pm_combo2", "pm_combo3", "pm_combo4")
NOW = datetime(2026, 10, 2, 12, 0, tzinfo=timezone.utc)


def ok(cond, why):
    print(f"  {'ok  ' if cond else 'FAIL'} {why}")
    if not cond:
        FAILS.append(why)


def eq(got, want, why):
    ok(got == want, why if got == want else f"{why} — got {got!r}, want {want!r}")


def _row(mid, price, start, venue):
    return dict(market_id=mid, sport="tennis", side_a="Player A", side_b="Player B",
                price_a=price, price_b=round(1 - price + 0.02, 2), price_draw=None,
                tradeable={"a": True, "b": True}, untraded=False, start=start.isoformat(),
                date=start.strftime("%Y-%m-%d"), venue=venue, label="A vs B",
                volume=1.0, url="", mid_a=price)


def _slug(tier):
    return f"aec-{tier}-aa-bb-2026-10-02"


def _picks():
    start = NOW + timedelta(hours=2)
    rows = [_row(_slug(t), 0.78, start, "polymarket_us") for t in ("atp", "wtadb", "utr") + DROPPED]
    rows += [
        _row("KXATPMATCH-26OCT02OK", 0.78, start, "kalshi"),
        _row("KXATPCHALLENGERMATCH-26OCT02NO", 0.78, start, "kalshi"),
        _row("KXWTAMATCH-26OCT02NO", 0.78, start, "kalshi"),
        _row("KXITFMATCH-26OCT02NO", 0.78, start, "kalshi"),
        _row(_slug("atp"), 0.78, NOW + timedelta(hours=4), "polymarket_us"),
        _row("aec-atp-low-bb-2026-10-02", 0.76, start, "polymarket_us"),
        _row("aec-atp-high-bb-2026-10-02", 0.81, start, "polymarket_us"),
    ]
    # The second ATP slug above collides with the kept one. Give the late one its own id.
    rows[-3] = _row("aec-atp-late-bb-2026-10-02", 0.78, NOW + timedelta(hours=4), "polymarket_us")
    return S.fetch_tennis_fav_band_3h("tennis", {"tennis": rows}, now=NOW)


def _legs(venue, ids):
    start = NOW + timedelta(hours=2)
    return {"tennis": [_row(mid, 0.78, start + timedelta(hours=i), venue)
                       for i, mid in enumerate(ids)]}


def _contests(d):
    """One row per contest. A parent-lane bet wins the overlap with the 3-hour lane."""
    raw = [q for q in T.all_bets(d)
           if q.get("source") in ("tennis_fav_band", "tennis_fav_band_3h")
           and q.get("bet") and q.get("status") in ("won", "lost")]
    by = collections.defaultdict(list)
    for q in raw:
        by[q["market_id"]].append(q)
    out = []
    for vs in by.values():
        parent = [q for q in vs if q["source"] == "tennis_fav_band"]
        out.append(parent[0] if parent else vs[0])
    return out, len(raw) - len(out)


def _tier(q):
    return q.get("tier") or S.tennis_tier(q["market_id"]) or "none"


def _figures(rows):
    """Contract P/L and z before fees. ROI and the flat-$100 fade are after fees."""
    n = len(rows)
    unit = won = exp = var = fee = 0.0
    fw = fexp = fvar = fpnl = 0.0
    fn = 0
    for q in rows:
        p = float(q["price"])
        hit = q["status"] == "won"
        unit += (1.0 - p) if hit else -p
        won += int(hit)
        exp += p
        var += p * (1.0 - p)
        fee += T.pnl_after_fee(q)
        other = "b" if q["pick"] == "a" else "a"
        fp = q.get("price_" + other)
        if not fp:
            continue
        fp = float(fp)
        fn += 1
        fad = q.get("result") == other
        rate = T.FEE_RATE.get(q.get("venue") or "polymarket", 0.07)
        fw += int(fad)
        fexp += fp
        fvar += fp * (1.0 - fp)
        fpnl += (T.STAKE * (1.0 / (fp + rate * fp * (1.0 - fp)) - 1.0) if fad else -T.STAKE)
    return dict(n=n, unit=unit, z=(won - exp) / math.sqrt(var),
                roi=fee / (n * T.STAKE),
                fade=fpnl / (fn * T.STAKE),
                fade_z=(fw - fexp) / math.sqrt(fvar))


def main():
    print("\nkept tours are an exact set, not a prefix")
    eq(getattr(S, "TENNIS_FAV_KEEP", None), KEEP,
       "the keep set is exactly ATP, WTA Doubles, and UTR")
    eq(S.BAND_BY_SPORT["tennis"], (0.77, 0.81), "the price band is still 0.77-0.81")
    eq(S.TENNIS_FAV_3H, timedelta(hours=3), "the window is still 3 hours")
    eq(S.tennis_tier("aec-atpdb-aa-bb-2026-10-02"), "atpdb", "ATP Doubles resolves as atpdb")
    eq(S.tennis_tier("aec-atpcq-aa-bb-2026-10-02"), "atpcq", "Challenger qualifying resolves as atpcq")
    eq(S.tennis_tier("aec-atpch-aa-bb-2026-10-02"), "atpch", "the Challenger resolves as atpch")
    eq(S.tennis_tier("KXATPCHALLENGERMATCH-26OCT02NO"), "atpch",
       "the long Kalshi prefix is still the Challenger, not ATP")
    eq(S.tennis_tier("aec-lavercup-aa-bb-2026-10-02"), None, "Laver Cup stays an unknown tour")
    kept_fn = getattr(S, "tennis_fav_kept", lambda mid: True)
    for tier in KEEP:
        ok(kept_fn(_slug(tier)) is True, f"{tier} is kept")
    for tier in DROPPED:
        ok(kept_fn(_slug(tier)) is False, f"{tier} is refused")
    ok(kept_fn("KXATPMATCH-26OCT02OK") is True, "a Kalshi ATP match is kept")
    ok(kept_fn("KXATPCHALLENGERMATCH-26OCT02NO") is False, "a Challenger is not kept as ATP")

    print("\nthe 3-hour lane picks only the kept tours, inside the same window and band")
    got = sorted(q["market_id"] for q in _picks())
    eq(got, sorted([_slug("atp"), _slug("wtadb"), _slug("utr"), "KXATPMATCH-26OCT02OK"]),
       "ATP, WTA Doubles, UTR, and a Kalshi ATP match; nothing else")
    ok(_slug("atpdb") not in got and _slug("atpcq") not in got,
       "ATP Doubles and Challenger qualifying are refused inside the window")

    print("\nevery basket lane cuts legs from that same kept set")
    eq(tuple(BASKETS), ("tennis_combo2", "tennis_combo3", "tennis_combo4",
                        "pm_combo2", "pm_combo3", "pm_combo4"),
       "six basket lanes cut from this band")
    for name in BASKETS:
        ok(S.SOURCES[name]["connected"], f"{name} stays connected")
        ok("ATP, WTA Doubles, or UTR" in S.SOURCES[name]["note"],
           f"{name} says which tours a leg may come from")
    kalshi_ids = ["KXATPMATCH-A", "KXATPCHALLENGERMATCH-B", "KXWTAMATCH-C", "KXITFMATCH-D"]
    kalshi = [leg[0]["market_id"]
              for legs in S.combo_legs_by_day(_legs("kalshi", kalshi_ids)).values() for leg in legs]
    eq(kalshi, ["KXATPMATCH-A"], "a Kalshi basket refuses Challenger, WTA, and ITF legs")
    pm_ids = [_slug(t) for t in ("atp", "atpdb", "atpcq", "wta", "wtadb", "utr", "lavercup")]
    pm = sorted(leg[0]["market_id"]
                for legs in S.pm_combo_legs_by_day(_legs("polymarket_us", pm_ids)).values()
                for leg in legs)
    eq(pm, sorted([_slug("atp"), _slug("wtadb"), _slug("utr")]),
       "a Polymarket basket refuses Doubles, qualifying, WTA, and Laver Cup")
    mixed = _legs("kalshi", ["KXATPMATCH-A", "KXATPMATCH-B", "KXATPCHALLENGERMATCH-C"])
    baskets = S.tennis_combo_rows(mixed)
    two = [r for r in baskets if r["market_id"].startswith("combo2:")]
    eq(len(two), 1, "two kept legs still make one two-leg basket")
    ok(all(S.tennis_tier(leg["market_id"]) == "atp" for r in two for leg in r["legs"]),
       "that basket holds no Challenger leg")
    dropped_only = _legs("polymarket_us", [_slug("atpdb"), _slug("atpcq")])
    eq(S.pm_tennis_combo_rows(dropped_only), [],
       "a day of only dropped tours builds no basket")

    print("\nthe note labels the looked-at record, and the ledger still says those figures")
    note = S.SOURCES["tennis_fav_band_3h"]["note"]
    ok("If faded" not in note and "If-faded" not in note,
       "the note does not label a figure as the page If-faded column")
    ok("flat $100 stake on the opposite side at its own price, after fees" in note,
       "the fade ROI is labeled as a flat $100 stake on the opposite side, after fees")
    ok("z -2.88 on the fade prices before fees" in note
       and "z -3.06 on the fade prices before fees" in note,
       "the fade z is labeled as the fade prices before fees")
    ok("z +2.76 before fees" in note and "not a significance test" in note,
       "the kept-set z is before fees and is not offered as a significance test")
    ok("does not survive UTR" in note, "the note says the deeper-field idea does not survive UTR")
    ok("9 contests" in note and "+12.0%" in note and "-60.6%" in note,
       "WTA Doubles is named as 9 contests, a direction")
    ok("ATP +6.35" in note and "before fees: one contract, pay the price, receive 1" in note,
       "the unit P/L is before fees, one contract")
    d = T.load()
    rows, overlaps = _contests(d)
    eq((len(rows), overlaps), (648, 27), "648 contests, 27 parent/3-hour overlaps")
    by = collections.defaultdict(list)
    for q in rows:
        by[_tier(q)].append(q)
    kept = [q for q in rows if _tier(q) in KEEP]
    whole = _figures(rows)
    keep_f = _figures(kept)
    wta_d = _figures(by["wtadb"])
    atp = _figures(by["atp"])
    eq((round(atp["unit"], 2), round(atp["z"], 2), round(atp["roi"] * 100, 1)),
       (6.35, 2.33, 15.5), "ATP unit P/L and z before fees, ROI after fees")
    eq((wta_d["n"], round(wta_d["roi"] * 100, 1), round(wta_d["fade"] * 100, 1)),
       (9, 12.0, -60.6), "WTA Doubles: 9 contests, +12.0% after fees, fade -60.6%")
    eq((round(keep_f["z"], 2), round(keep_f["fade"] * 100, 1), round(keep_f["fade_z"], 2)),
       (2.76, -68.7, -3.06), "kept set: z +2.76 before fees, fade -68.7% / z -3.06")
    eq((round(whole["fade"] * 100, 1), round(whole["fade_z"], 2)),
       (-24.1, -2.88), "whole band fade -24.1% / z -2.88, flat $100 on the other side")
    days = {q["date"] for q in rows}
    span = (datetime.fromisoformat(max(days)) - datetime.fromisoformat(min(days))).days + 1
    eq((round(len(rows) / span, 1), round(len(kept) / span, 1)),
       (36.0, 4.3), "36.0 contests a day, 4.3 on the kept tours")

    print("\nthe page record restarts; the ledger rows stay")
    st = T.load_stages()
    since = getattr(S, "TENNIS_FAV_KEEP_SINCE", None)
    eq(since, "2026-10-02T05:00:00+00:00", "the clock is a fixed instant after every logged bet")
    for key in ("tennis_fav_band_3h|tennis", "tennis_combo2|tennis_combo",
                "tennis_combo3|tennis_combo", "tennis_combo4|tennis_combo",
                "pm_combo2|tennis_pmcombo", "pm_combo3|tennis_pmcombo"):
        pair = (st.get("pairs") or {}).get(key) or {}
        eq((pair.get("stage"), pair.get("since")), ("sandbox", since),
           f"{key} counts from the tour cut, in the Sandbox")
    prod = (st.get("pairs") or {}).get("pm_combo4|tennis_pmcombo") or {}
    eq(prod.get("stage"), "production", "pm_combo4 stays in Production")
    ok(prod.get("entry_since") is None and "since" not in prod,
       "pm_combo4's judged record is still its whole record")
    eq(sorted(T.PAIR_OVERRIDES),
       ["mma_fav_band|mma", "o15_ranked|soccer_o15_intl", "oddspedia|cricket",
        "pm_combo4|tennis_pmcombo", "team1_form_l5|soccer_team1",
        "team1_form_l5|soccer_team1_intl"],
       "the Production list is unchanged")
    shown = {(r["name"], r["v"], r["a"]["n"]) for r in SB.pair_list(d, st)}
    ok(("tennis_fav_band_3h", "waiting", 0) in shown,
       "the 3-hour lane still renders, waiting, with none of the old bets in its record")
    ok(("tennis_combo2", "waiting", 0) in shown and ("pm_combo2", "waiting", 0) in shown,
       "the two-leg lanes still render, waiting")
    ok(not any(name == "pm_combo3" for name, _v, _n in shown),
       "pm_combo3 has no open bet after the clock, so it is not listed")
    ok(not any(name in ("nws", "nws_fade", "covers") for name, _v, _n in shown),
       "removed lanes stay off the page")
    ok(any(S.tennis_tier(q.get("market_id")) == "atpdb"
           for q in T.all_bets(d) if q.get("status") in ("won", "lost")),
       "dropped-tour bets are still on file")

    print(f"\n{'FAILED: ' + str(len(FAILS)) if FAILS else 'tennis tier filter passed'}")
    for item in FAILS:
        print(f"  - {item}")
    return 1 if FAILS else 0


if __name__ == "__main__":
    raise SystemExit(main())
