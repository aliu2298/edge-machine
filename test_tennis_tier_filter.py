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


RESET_LANES = frozenset({
    "tennis_fav_band_3h", "tennis_combo2", "tennis_combo3", "tennis_combo4",
    "pm_combo2", "pm_combo3",
})


def _leg_kept(leg):
    if isinstance(leg, dict):
        tier = leg.get("tier")
        if tier:
            return tier in KEEP
        return S.tennis_tier(leg.get("market_id")) in KEEP
    return S.tennis_tier(leg) in KEEP


def _refused_tour(q):
    """A reset-lane bet on a tour outside the keep set. pm_combo4 is not one."""
    if q.get("source") not in RESET_LANES:
        return False
    legs = q.get("legs") or []
    if legs:
        return any(not _leg_kept(leg) for leg in legs)
    tier = q.get("tier") or S.tennis_tier(q.get("market_id"))
    return tier not in KEEP


def _quote(source, mid, logged, tier=None):
    return dict(id=f"{source}:{mid}", source=source, sport="tennis", bet=True,
                venue="kalshi", market_id=mid, pick="a", price=0.78, price_a=0.78,
                price_b=0.24, status="won", pnl=28.0, stake=100.0, result="a",
                logged=logged, start=logged, settled=logged, tier=tier)


def _reset_fixture():
    clock = "2026-10-02T05:00:00+00:00"
    after = "2026-10-02T06:00:00+00:00"
    before = "2026-10-01T12:00:00+00:00"
    return {"quotes": [
        _quote("tennis_fav_band_3h", "aec-atp-new-bb-2026-10-02", after, "atp"),
        _quote("tennis_fav_band_3h", "aec-wta-new-bb-2026-10-02", after, "wta"),
        _quote("tennis_fav_band_3h", "aec-atp-old-bb-2026-10-01", before, "atp"),
    ], "meta": {}, "_clock": clock}


def _reset_stages():
    return {"pairs": {"tennis_fav_band_3h|tennis": {
        "stage": "sandbox", "since": "2026-10-02T05:00:00+00:00"}}}


def _stamp_row(table, label):
    needle = f"<b>{label}</b>"
    for part in table.split("<tr>"):
        head = part.split("</tr>", 1)[0]
        if needle in head:
            return head
    return ""


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
    rows = SB.pair_list(d, st)
    shown = {(r["name"], r["v"], r["a"]["n"]) for r in rows}
    by_name = {r["name"]: r for r in rows}
    ok(("tennis_fav_band_3h", "waiting", 0) in shown,
       "the 3-hour lane still renders, waiting, with none of the old bets in its record")
    ok(("tennis_combo2", "waiting", 0) in shown and ("pm_combo2", "waiting", 0) in shown,
       "the two-leg lanes still render, waiting")
    ok(("pm_combo3", "waiting", 0) in shown,
       "pm_combo3 renders as Waiting with no bets in the record")
    ok(by_name.get("pm_combo3", {}).get("open") == 0,
       "pm_combo3 has no open bet and still stays on the page")
    # The same rule lists the two Kalshi baskets that were already empty under
    # the September band clock. They are not removed lanes.
    ok(("tennis_combo3", "waiting", 0) in shown and ("tennis_combo4", "waiting", 0) in shown,
       "tennis_combo3 and tennis_combo4 render as Waiting with no bets yet")
    counted = [r for r in rows if r["sport"] not in S.DAY_CLUSTERED]
    eq(len(counted), 45,
       "[records] counts pm_combo3 plus the two already-empty Kalshi baskets")
    ok(not any(name in ("nws", "nws_fade", "covers") for name, _v, _n in shown),
       "removed lanes stay off the page")
    ok(any(S.tennis_tier(q.get("market_id")) == "atpdb"
           for q in T.all_bets(d) if q.get("status") in ("won", "lost")),
       "dropped-tour bets are still on file")

    print("\ndropped-tour bets leave every rendered table and stay in the data")
    refused = [q for q in T.all_bets(d) if _refused_tour(q)]
    h3 = [q for q in refused if q.get("source") == "tennis_fav_band_3h"]
    eq(sum(1 for q in h3 if q.get("status") in ("won", "lost")), 65,
       "65 settled 3-hour bets are on dropped tours")
    eq(sum(1 for q in h3 if q.get("status") == "open"), 7,
       "7 open 3-hour bets are on dropped tours")
    ok(all(q["id"] in {x.get("id") for x in T.all_bets(d)} for q in refused),
       "every refused-tour row is still in the loaded ledger")
    html, index, weeks = SB.render_pages(d=d, st=st)
    blob = "\n".join([html, index, *weeks.values()])
    leaked = [q["id"] for q in refused if f'data-id="{q["id"]}"' in blob]
    ok(not leaked, "no refused-tour bet is a row on the sandbox page or an archive page"
       + (f" — {len(leaked)} rows, first {leaked[0]}" if leaked else ""))
    kept_open = [q for q in T.all_bets(d)
                 if q.get("source") == "tennis_fav_band_3h" and q.get("status") == "open"
                 and not _refused_tour(q)]
    eq([q["id"] for q in kept_open],
       ["tennis_fav_band_3h:aec-atp-alemol-karkha-2026-10-01"],
       "the one open kept-tour 3-hour bet stays a rendered row")
    ok(f'data-id="{kept_open[0]["id"]}"' in html,
       "that kept-tour open bet is on the sandbox page")
    p4 = [q for q in T.all_bets(d)
          if q.get("source") == "pm_combo4" and q.get("status") in ("won", "lost")]
    eq(len(p4), 4, "pm_combo4's four settled baskets are still the record")
    ok(all(f'data-id="{q["id"]}"' in blob for q in p4),
       "pm_combo4's baskets stay on the rendered page")
    ok(all(not _refused_tour(q) for q in p4),
       "pm_combo4 is not treated as a reset lane")
    judge = T.assess(d, "pm_combo4", "tennis_pmcombo", venues=T.TRADEABLE_VENUES)
    eq((judge["won"], judge["n"] - judge["won"]), (2, 2),
       "pm_combo4 is still 2-2 on its whole record")
    eq((by_name.get("tennis_fav_band_3h") or {}).get("fade", {}).get("n"), 0,
       "the 3-hour If-faded cell is the empty post-reset set")
    eq((by_name.get("pm_combo2") or {}).get("open"), 0,
       "pm_combo2's open baskets are refused tours, so the open column is empty")
    ok(("pm_combo2", "waiting", 0) in shown,
       "pm_combo2 still renders as Waiting once those open baskets leave the table")
    whole_fade = T.faded(d, "tennis_fav_band_3h", "tennis", venues=T.TRADEABLE_VENUES)
    ok(whole_fade["n"] > 0,
       "T.faded() on the 3-hour lane, called the way every other lane is, still reads the whole book")
    other = T.faded(d, "pm_combo4", "tennis_pmcombo", venues=T.TRADEABLE_VENUES)
    eq(other["n"], 4, "T.faded() on pm_combo4 is still its four baskets")

    print("\na post-reset kept bet counts, and a dropped tour does not")
    fx = _reset_fixture()
    fx_rows = {r["name"]: r for r in SB.pair_list(fx, _reset_stages())}
    fx_lane = fx_rows.get("tennis_fav_band_3h") or {"a": {}, "fade": {}}
    eq((fx_lane["a"].get("n"), fx_lane["a"].get("won")),
       (1, 1), "only the post-reset kept-tour bet is in the 3-hour record")
    eq(fx_lane.get("fade", {}).get("n"), 1,
       "If faded on that lane is the same one bet")
    eq(T.faded(fx, "tennis_fav_band_3h", "tennis", venues=T.TRADEABLE_VENUES)["n"], 3,
       "T.faded() itself still counts the dropped tour and the pre-reset bet")
    fx_html, fx_index, fx_weeks = SB.render_pages(d=fx, st=_reset_stages())
    fx_blob = "\n".join([fx_html, fx_index, *fx_weeks.values()])
    ok('data-id="tennis_fav_band_3h:aec-atp-new-bb-2026-10-02"' in fx_blob,
       "the post-reset kept bet is rendered")
    ok('data-id="tennis_fav_band_3h:aec-wta-new-bb-2026-10-02"' not in fx_blob,
       "the post-reset dropped tour is not rendered")
    ok('data-id="tennis_fav_band_3h:aec-atp-old-bb-2026-10-01"' in fx_blob,
       "a pre-reset kept-tour bet stays in the settled table and out of the record")
    label = "Tennis 3-leg combo on Polymarket US"
    table_rows = [part for part in html.split("<tr>") if label in part.split("</tr>", 1)[0]]
    ok(any("Waiting for results" in part for part in table_rows),
       "the sandbox page shows pm_combo3 as Waiting for results")

    print("\nthe stamp counts a reset lane only from the tour clock")
    page = SB.hide_refused_tours(SB.hide_removed(d))
    stamp = SB.approval_table(page, T.score(page), full=d)
    empty = "0 bets over 0 days"
    for name in ("tennis_fav_band_3h", "tennis_combo2", "tennis_combo3",
                 "tennis_combo4", "pm_combo2", "pm_combo3"):
        row = _stamp_row(stamp, S.SOURCES[name]["label"])
        ok(bool(row) and empty in row and "NO READ" in row,
           f"{name}'s stamp is the empty record since the tour clock")
    h3 = _stamp_row(stamp, S.SOURCES["tennis_fav_band_3h"]["label"])
    ok("20 bets" not in h3 and "18 won" not in h3 and "+14.3%" not in h3,
       "the 3-hour stamp does not carry the pre-clock kept-tour record")
    combo2 = _stamp_row(stamp, S.SOURCES["pm_combo2"]["label"])
    ok("+58.1%" not in combo2 and "3 bets over 2 days" not in combo2,
       "pm_combo2's stamp does not carry the pre-clock +58.1% on 3")
    kept4 = _stamp_row(stamp, S.SOURCES["pm_combo4"]["label"])
    ok("4 bets over 1 day" in kept4 and "2 won v 1.6 priced" in kept4,
       "pm_combo4's stamp is still its whole record")
    other = T.assess(SB.stamp_ledger(d, "mma_fav_band"), "mma_fav_band")
    ok(other["criteria"][0][3] in _stamp_row(stamp, S.SOURCES["mma_fav_band"]["label"]),
       "a lane off the tour clock still shows its whole record on the stamp")
    fx_page = SB.hide_refused_tours(fx)
    fx_stamp = SB.approval_table(fx_page, T.score(fx_page), full=fx)
    fx_row = _stamp_row(fx_stamp, S.SOURCES["tennis_fav_band_3h"]["label"])
    ok("1 bets over 0 days" in fx_row and "1 won v 0.8 priced" in fx_row,
       "the stamp counts the post-reset kept bet and not the pre-reset one")

    print(f"\n{'FAILED: ' + str(len(FAILS)) if FAILS else 'tennis tier filter passed'}")
    for item in FAILS:
        print(f"  - {item}")
    return 1 if FAILS else 0


if __name__ == "__main__":
    raise SystemExit(main())
