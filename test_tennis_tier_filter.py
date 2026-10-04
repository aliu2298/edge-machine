#!/usr/bin/env python3
"""The tennis favourite band keeps ATP, WTA Doubles, and UTR only.

tennis_fav_band_3h and every basket lane that cuts legs from that band
refuse every other tour, including ATP Doubles and ATP Challenger qualifying,
which share the letters "atp" and must not match by prefix. The 3-hour lane
backs 0.70-0.85 from 2026-10-04, the baskets 0.77-0.81; the window stays 3 hours.

Fails on main: a dropped tour inside the window is still picked, and a
dropped-tour leg still enters a basket. No network.
"""
import collections
import json
import math
import os
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
    kept_kalshi = _row("KXATPMATCH-26OCT02OK", 0.78, start, "kalshi")
    kept_kalshi["start_source"] = "tennisexplorer"
    rows += [
        kept_kalshi,
        _row("KXATPCHALLENGERMATCH-26OCT02NO", 0.78, start, "kalshi"),
        _row("KXWTAMATCH-26OCT02NO", 0.78, start, "kalshi"),
        _row("KXITFMATCH-26OCT02NO", 0.78, start, "kalshi"),
        _row(_slug("atp"), 0.78, NOW + timedelta(hours=4), "polymarket_us"),
        _row("aec-atp-low-bb-2026-10-02", 0.69, start, "polymarket_us"),
        _row("aec-atp-edge-bb-2026-10-02", 0.70, start, "polymarket_us"),
        _row("aec-atp-high-bb-2026-10-02", 0.85, start, "polymarket_us"),
    ]
    # The second ATP slug above collides with the kept one. Give the late one its own id.
    rows[-4] = _row("aec-atp-late-bb-2026-10-02", 0.78, NOW + timedelta(hours=4), "polymarket_us")
    return S.fetch_tennis_fav_band_3h("tennis", {"tennis": rows}, now=NOW)


def _legs(venue, ids):
    start = NOW + timedelta(hours=2)
    return {"tennis": [_row(mid, 0.78, start + timedelta(hours=i), venue)
                       for i, mid in enumerate(ids)]}


def _settled_before_clock(q):
    """True when this row was settled before the tour clock.

    A missing stamp is not before the clock. A Z suffix is the same instant
    as +00:00, so a grade written that way cannot re-enter the frozen record.
    """
    text = str(q.get("settled") or "").replace("Z", "+00:00")
    # The LOOKED-AT record, which is historical and fixed. Not the reset clock:
    # the reset moved to the merge and this must not move with it.
    return bool(text) and text < S.TENNIS_FAV_EVIDENCE_BEFORE


def _looked_at_rows(d):
    """Won or lost bets on the two tennis bands, settled before the tour clock.

    A void is not in this list. A settlement after the clock is not either,
    so a new grade does not move the looked-at record.
    """
    return [q for q in T.all_bets(d)
            if q.get("source") in ("tennis_fav_band", "tennis_fav_band_3h")
            and q.get("bet") and q.get("status") in ("won", "lost")
            and _settled_before_clock(q)]


def _in_band(price, band):
    """The same cut band_picks uses: lower bound inclusive, upper exclusive."""
    try:
        p = float(price)
    except (TypeError, ValueError):
        return False
    return band[0] <= p < band[1]


def _pair_groups(rows):
    """Market ids that have a looked-at bet on both the parent lane and the 3-hour lane."""
    by = collections.defaultdict(list)
    for q in rows:
        by[q.get("market_id")].append(q)
    both = {"tennis_fav_band", "tennis_fav_band_3h"}
    return {mid: vs for mid, vs in by.items()
            if mid and both <= {q.get("source") for q in vs}}


def _band_overlap_ids(d):
    """Contests with a non-void looked-at bet in each lane, inside that lane's band.

    Read from the ledger with the band constants, not from a pinned total.
    A void, an archive roll-up, or a settlement after the clock leaves this
    set and the reported pairs together. Moving a band edge by one cent
    drops a row priced on the old edge from this set only.
    """
    parent = S.fav_band("tennis")
    wide = S.TENNIS_3H_BAND
    out = set()
    for mid, vs in _pair_groups(_looked_at_rows(d)).items():
        parents = [q for q in vs if q.get("source") == "tennis_fav_band"]
        wides = [q for q in vs if q.get("source") == "tennis_fav_band_3h"]
        if (all(_in_band(q.get("price"), parent) for q in parents)
                and all(_in_band(q.get("price"), wide) for q in wides)):
            out.add(mid)
    return out


def _contests(d):
    """One row per contest settled before the tour clock.

    A parent-lane bet wins the overlap with the 3-hour lane. A bet the
    tracker grades after the clock stays out, so the looked-at record does
    not move when an open row settles.
    """
    raw = _looked_at_rows(d)
    by = collections.defaultdict(list)
    for q in raw:
        by[q["market_id"]].append(q)
    out = []
    for vs in by.values():
        parent = next((q for q in vs if q.get("source") == "tennis_fav_band"), None)
        chosen = parent if parent is not None else next(iter(vs), None)
        if chosen is not None:
            out.append(chosen)
    return out, len(raw) - len(out)


def _edge_overlap_book():
    """Edge contests at the registered bounds, not read back from the constants.

    Parent 0.77 is the inclusive lower edge of 0.77-0.81. A parent at 0.76
    with a 3-hour copy at 0.78 is not an overlap: the child price is inside
    the wide band and the parent is not. The 3-hour lane's 0.70 is the
    inclusive lower edge of 0.70-0.85, 0.84 sits one cent inside the exclusive
    cap, and 0.85 is that cap so it is not an overlap. A voided twin is not
    an overlap either. Moving any of those edges by one cent changes which
    of these contests qualify.
    """
    def q(source, status, mid, price):
        return dict(id=f"{source}:{mid}", source=source, sport="tennis", bet=True,
                    market_id=mid, status=status, price=price,
                    settled="2026-09-01T00:00:00+00:00")
    return {"quotes": [
        q("tennis_fav_band", "won", "edge-contest", 0.77),
        q("tennis_fav_band_3h", "won", "edge-contest", 0.77),
        q("tennis_fav_band", "void", "void-contest", 0.77),
        q("tennis_fav_band_3h", "won", "void-contest", 0.77),
        q("tennis_fav_band", "won", "wide-lo", 0.78),
        q("tennis_fav_band_3h", "won", "wide-lo", 0.70),
        q("tennis_fav_band", "won", "wide-inside", 0.78),
        q("tennis_fav_band_3h", "won", "wide-inside", 0.84),
        q("tennis_fav_band", "won", "wide-hi", 0.78),
        q("tennis_fav_band_3h", "won", "wide-hi", 0.85),
        q("tennis_fav_band", "won", "parent-below", 0.76),
        q("tennis_fav_band_3h", "won", "parent-below", 0.78),
    ]}


def _lane_sport(name):
    return next(iter((S.SOURCES.get(name) or {}).get("sports") or []), None)


def _kept_settled_since(d, name, sport, since):
    """Kept-tour bets on this lane that the page record counts from the clock."""
    return [q for q in T.all_bets(d)
            if q.get("source") == name and q.get("sport") == sport
            and q.get("bet") and q.get("status") in ("won", "lost")
            and not T.climate_excluded(q) and not S.tennis_refused_row(q)
            and str(q.get("logged") or "") >= since
            and (q.get("venue") or "polymarket") in T.TRADEABLE_VENUES]


def _kept_open(d, name, sport):
    """Kept-tour open bets the page's open column counts. Quotes only."""
    return [q for q in (d.get("quotes") or [])
            if q.get("source") == name and q.get("sport") == sport
            and q.get("bet") and q.get("status") == "open"
            and not T.climate_excluded(q) and not S.tennis_refused_row(q)]


def _fade_count(d, name, sport, since):
    """Bets If-faded would count once the book is cut to the clock."""
    n = 0
    for q in _kept_settled_since(d, name, sport, since):
        if q.get("price_draw") is not None or q.get("pick") not in ("a", "b"):
            continue
        other = "b" if q.get("pick") == "a" else "a"
        if q.get("price_" + other):
            n += 1
    return n


def _leg_market(leg):
    row = leg if isinstance(leg, dict) else next(iter(leg), None)
    return row.get("market_id") if isinstance(row, dict) else None


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


def _spec_figures(rows):
    """The same P/L rule as _figures, written out so the two can be compared.

    A later void changes the rows both sides read. It does not change a
    pinned total.
    """
    n = len(rows)
    unit = won = exp = var = fee = 0.0
    fw = fexp = fvar = fpnl = 0.0
    fn = 0
    for q in rows:
        p = float(q["price"])
        won_bet = q.get("status") == "won"
        unit += (1.0 - p) if won_bet else -p
        won += 1 if won_bet else 0
        exp += p
        var += p * (1.0 - p)
        fee += T.pnl_after_fee(q)
        other = "b" if q.get("pick") == "a" else "a"
        fp = q.get("price_" + other)
        if not fp:
            continue
        fp = float(fp)
        fn += 1
        hit = q.get("result") == other
        rate = T.FEE_RATE.get(q.get("venue") or "polymarket", 0.07)
        fw += 1 if hit else 0
        fexp += fp
        fvar += fp * (1.0 - fp)
        fpnl += T.STAKE * (1.0 / (fp + rate * fp * (1.0 - fp)) - 1.0) if hit else -T.STAKE
    return dict(n=n, unit=unit, z=(won - exp) / math.sqrt(var),
                roi=fee / (n * T.STAKE),
                fade=fpnl / (fn * T.STAKE),
                fade_z=(fw - fexp) / math.sqrt(fvar))


def _rounded(fig):
    return (fig["n"], round(fig["unit"], 2), round(fig["z"], 2),
            round(fig["roi"] * 100, 1), round(fig["fade"] * 100, 1),
            round(fig["fade_z"], 2))


def _frozen_looked_at():
    """The looked-at contests the note's figures were read from.

    A checked-in snapshot under fixtures/, not under data/. A later tracker
    row or a void on the live ledger does not move this file, so the note's
    maths stay pinned to these contests.
    """
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "fixtures", "tennis_fav_looked_at.json")
    with open(path) as fh:
        return json.load(fh)


def _check_frozen_note(rows):
    """The published note figures, asserted only against the frozen snapshot."""
    by = collections.defaultdict(list)
    for q in rows:
        by[_tier(q)].append(q)
    kept = [q for q in rows if _tier(q) in KEEP]
    atp = _figures(by["atp"])
    wta = _figures(by["wtadb"])
    keep_f = _figures(kept)
    whole = _figures(rows)
    eq(_rounded(_figures(rows)), _rounded(_spec_figures(rows)),
       "the frozen snapshot follows the same rule on both implementations")
    eq(len(rows), 648, "the frozen looked-at record is 648 contests")
    eq((round(atp["unit"], 2), round(atp["z"], 2), round(atp["roi"] * 100, 1)),
       (6.35, 2.33, 15.5), "frozen ATP: unit +6.35, z +2.33, ROI +15.5% after fees")
    eq((wta["n"], round(wta["roi"] * 100, 1), round(wta["fade"] * 100, 1)),
       (9, 12.0, -60.6), "frozen WTA Doubles: 9 contests, +12.0% after fees, fade -60.6%")
    eq((round(keep_f["z"], 2), round(keep_f["fade"] * 100, 1), round(keep_f["fade_z"], 2)),
       (2.76, -68.7, -3.06), "frozen kept set: z +2.76 before fees, fade -68.7% / z -3.06")
    eq((round(whole["fade"] * 100, 1), round(whole["fade_z"], 2)),
       (-24.1, -2.88), "frozen whole-band fade -24.1% / z -2.88")
    days = {q["date"] for q in rows}
    span = (datetime.fromisoformat(max(days)) - datetime.fromisoformat(min(days))).days + 1
    eq((round(len(rows) / span, 1), round(len(kept) / span, 1)),
       (36.0, 4.3), "frozen record: 36.0 contests a day, 4.3 on the kept tours")


def _check_note_quotes(note, rows):
    """The 3-hour note quotes this frozen record. The live ledger is not read."""
    by = collections.defaultdict(list)
    for q in rows:
        by[_tier(q)].append(q)
    kept = [q for q in rows if _tier(q) in KEEP]
    atp = _figures(by["atp"])
    wta = _figures(by["wtadb"])
    keep_f = _figures(kept)
    whole = _figures(rows)
    phrases = (
        f"ATP {atp['unit']:+.2f}",
        f"z {keep_f['z']:+.2f} before fees",
        f"{wta['n']} contests",
        f"{wta['roi'] * 100:+.1f}%",
        f"{wta['fade'] * 100:.1f}%",
        f"z {whole['fade_z']:+.2f} on the fade prices before fees",
        f"z {keep_f['fade_z']:+.2f} on the fade prices before fees",
    )
    for phrase in phrases:
        ok(phrase in note, f"the 3-hour note quotes the frozen record: {phrase}")


def _per_day(rows):
    """Contests a day: the rows divided by the inclusive span of their dates."""
    days = {q["date"] for q in rows}
    span = (datetime.fromisoformat(max(days)) - datetime.fromisoformat(min(days))).days + 1
    return round(len(rows) / span, 1), span


def _check_looked_at(d):
    """The looked-at record, derived from this ledger. No pinned totals."""
    rows, overlaps = _contests(d)
    markets = {q.get("market_id") for q in _looked_at_rows(d)}
    eq(len(rows), len(markets), "the contest count is one row per looked-at market")
    reported = set(_pair_groups(_looked_at_rows(d)))
    expected = _band_overlap_ids(d)
    outside = sorted(reported - expected)
    extra = sorted(expected - reported)
    ok(not outside and not extra,
       "every parent/3-hour overlap is a non-void pair inside both bands"
       + (f" — priced outside a band: {outside}" if outside else "")
       + (f" — in both bands but not reported: {extra}" if extra else ""))
    eq(overlaps, len(reported), "the overlap count is the size of that set")
    void_ids = {q.get("id") for q in T.all_bets(d)
                if q.get("source") in ("tennis_fav_band", "tennis_fav_band_3h")
                and q.get("status") == "void"}
    counted = {q.get("id") for vs in _pair_groups(_looked_at_rows(d)).values() for q in vs}
    ok(void_ids.isdisjoint(counted), "no voided row is counted as an overlap")
    eq(_band_overlap_ids(_edge_overlap_book()),
       {"edge-contest", "wide-lo", "wide-inside"},
       "0.77 and 0.70 and 0.84 are overlaps; 0.85, a void, and a parent at 0.76 are not")
    by = collections.defaultdict(list)
    for q in rows:
        by[_tier(q)].append(q)
    kept = [q for q in rows if _tier(q) in KEEP]
    for name, group in (("ATP", by["atp"]), ("WTA Doubles", by["wtadb"]),
                        ("kept set", kept), ("whole band", rows)):
        eq(_rounded(_figures(group)), _rounded(_spec_figures(group)),
           f"{name} figures are the looked-at rows under the same rule")
    rate, _span = _per_day(rows)
    days = {q["date"] for q in rows}
    span = (datetime.fromisoformat(max(days)) - datetime.fromisoformat(min(days))).days + 1
    eq((rate, round(len(kept) / span, 1)),
       (round(len(rows) / span, 1), round(len(kept) / span, 1)),
       "contests a day are the looked-at rows over the span of their dates")


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
    # Derived from the constant, never a literal hour: the clock moved once already
    # (05:00 -> the 16:34 merge) and a fixture pinned to the old hour hid that.
    clock = S.TENNIS_FAV_KEEP_SINCE
    after = "2026-10-02T17:00:00+00:00"
    before = "2026-10-01T12:00:00+00:00"
    return {"quotes": [
        _quote("tennis_fav_band_3h", "aec-atp-new-bb-2026-10-02", after, "atp"),
        _quote("tennis_fav_band_3h", "aec-wta-new-bb-2026-10-02", after, "wta"),
        _quote("tennis_fav_band_3h", "aec-atp-old-bb-2026-10-01", before, "atp"),
    ], "meta": {}, "_clock": clock}


def _reset_stages():
    return {"pairs": {"tennis_fav_band_3h|tennis": {
        "stage": "sandbox", "since": S.TENNIS_FAV_KEEP_SINCE}}}


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
    eq(got, sorted([_slug("atp"), _slug("wtadb"), _slug("utr"), "KXATPMATCH-26OCT02OK",
                    "aec-atp-edge-bb-2026-10-02"]),
       "ATP, WTA Doubles, UTR, a Kalshi ATP match, and an ask at 0.70; nothing else")
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
    kalshi = [mid for legs in S.combo_legs_by_day(_legs("kalshi", kalshi_ids)).values()
              for leg in legs if (mid := _leg_market(leg))]
    eq(kalshi, ["KXATPMATCH-A"], "a Kalshi basket refuses Challenger, WTA, and ITF legs")
    pm_ids = [_slug(t) for t in ("atp", "atpdb", "atpcq", "wta", "wtadb", "utr", "lavercup")]
    pm = sorted(mid for legs in S.pm_combo_legs_by_day(_legs("polymarket_us", pm_ids)).values()
                for leg in legs if (mid := _leg_market(leg)))
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
    ok(note.count("on the fade prices before fees") >= 2,
       "the fade z is labeled as the fade prices before fees")
    ok("before fees" in note and "not a significance test" in note,
       "the kept-set z is before fees and is not offered as a significance test")
    ok("does not survive UTR" in note, "the note says the deeper-field idea does not survive UTR")
    ok("WTA Doubles" in note and "a direction, not a result" in note,
       "WTA Doubles is named as a direction, not a result")
    ok("before fees: one contract, pay the price, receive 1" in note,
       "the unit P/L is before fees, one contract")
    d = T.load()
    _check_looked_at(d)
    frozen = _frozen_looked_at()
    _check_frozen_note(frozen)
    _check_note_quotes(note, frozen)

    print("\nthe page record restarts; the ledger rows stay")
    st = T.load_stages()
    since = getattr(S, "TENNIS_FAV_KEEP_SINCE", None)
    # The clock is the moment the filter REACHED MAIN, not the moment it was written.
    # It was first set to 05:00 while the commits sat on a branch until the 16:34 merge,
    # so two bets the OLD unnarrowed rule had chosen opened the fresh record at -35.9%.
    # A reset begins where the behaviour changed.
    eq(since, "2026-10-02T16:34:37+00:00",
       "the clock is the merge that put the narrowed selection on main")
    ok(all(str(q.get("logged") or "") < since
           for q in T.all_bets(json.load(open(T.LEDGER)))
           if q.get("source") == "tennis_fav_band_3h" and q.get("bet")
           and not S.tennis_fav_kept(q.get("market_id"))),
       "no bet on a refused tour was logged after the clock")
    for key in ("tennis_fav_band_3h|tennis", "tennis_combo2|tennis_combo",
                "tennis_combo3|tennis_combo", "tennis_combo4|tennis_combo",
                "pm_combo2|tennis_pmcombo", "pm_combo3|tennis_pmcombo"):
        pair = (st.get("pairs") or {}).get(key) or {}
        # The baskets restarted again when their legs widened to 0.70-0.85.
        want = since if key.startswith("tennis_fav_band_3h") else S.TENNIS_COMBO_BAND_SINCE
        eq((pair.get("stage"), pair.get("since")), ("sandbox", want),
           f"{key} counts from its latest reset, in the Sandbox")
    # pm_combo4 left Production on 2026-10-03 (no parlay API to act on), but it is still
    # NOT on the tour clock: its record stays whole, which is what this asserts.
    prod = (st.get("pairs") or {}).get("pm_combo4|tennis_pmcombo") or {}
    ok("pm_combo4" not in S.TENNIS_FAV_RESET,
       "pm_combo4 is off the tour clock, so its record is not restarted by the tour cut")
    ok(prod.get("since") != S.TENNIS_FAV_KEEP_SINCE,
       "and it does not carry the tour-cut clock")
    eq(sorted(T.PAIR_OVERRIDES),
       ["o15_ranked|soccer_o15_intl", "oddspedia|cricket",
        "team1_form_l5|soccer_team1", "team1_form_l5|soccer_team1_intl",
        "u35_low_scoring|soccer_u35_intl"],
       "the Production list no longer carries pm_combo4")
    rows = SB.pair_list(d, st)
    by_name = {r["name"]: r for r in rows}
    counted = [r for r in rows if r["sport"] not in S.DAY_CLUSTERED]
    eq(len(counted), 40,
       "[records] drops the five lanes taken off the board on 2026-10-04")
    ok(not any(r["name"] in ("nws", "nws_fade", "covers") for r in rows),
       "removed lanes stay off the page")
    ok(any(S.tennis_tier(q.get("market_id")) == "atpdb"
           for q in T.all_bets(d) if q.get("status") in ("won", "lost")),
       "dropped-tour bets are still on file")

    print("\ndropped-tour bets leave every rendered table and stay in the data")
    refused = [q for q in T.all_bets(d) if _refused_tour(q)]
    h3 = [q for q in refused if q.get("source") == "tennis_fav_band_3h"]
    logged_before = [q for q in h3 if str(q.get("logged") or "") < since]
    # The count is whatever it is; what must hold is that EVERY refused-tour bet
    # predates the clock. One logged after it would mean the filter is not gating.
    eq(len(logged_before), len(h3),
       f"all {len(h3)} dropped-tour 3-hour bets were logged before the clock")
    ok(not [q for q in h3 if str(q.get("logged") or "") >= since],
       "and none was logged after it — a refused tour after the clock means the filter is not gating")
    ok(all(q["id"] in {x.get("id") for x in T.all_bets(d)} for q in refused),
       "every refused-tour row is still in the loaded ledger")
    html, index, weeks = SB.render_pages(d=d, st=st)
    blob = "\n".join([html, index, *weeks.values()])
    leaked = [q["id"] for q in refused if f'data-id="{q["id"]}"' in blob]
    first_leaked = next(iter(leaked), None)
    ok(not leaked, "no refused-tour bet is a row on the sandbox page or an archive page"
       + (f" — {len(leaked)} rows, first {first_leaked}" if first_leaked else ""))
    for name in ("tennis_fav_band_3h", "tennis_combo2", "tennis_combo3",
                 "tennis_combo4", "pm_combo2", "pm_combo3"):
        sport = _lane_sport(name)
        row = by_name.get(name) or {}
        ok(bool(row), f"{name} still renders")
        want_n = len(_kept_settled_since(d, name, sport, since))
        eq((row.get("a") or {}).get("n"), want_n,
           f"{name}'s record n is its kept-tour bets settled since the clock")
        opens = _kept_open(d, name, sport)
        eq(row.get("open"), len(opens),
           f"{name}'s open column is its kept-tour open bets")
        if want_n == 0:
            eq(row.get("v"), "waiting",
               f"{name} with nothing settled since the clock is Waiting")
        eq((row.get("fade") or {}).get("n"), _fade_count(d, name, sport, since),
           f"{name}'s If-faded n is the kept-tour bets settled since the clock")
        for q in opens:
            ok(f'data-id="{q["id"]}"' in html,
               f"kept-tour open bet {q['id']} is on the sandbox page")
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
    whole_fade = T.faded(d, "tennis_fav_band_3h", "tennis", venues=T.TRADEABLE_VENUES)
    ok(whole_fade["n"] > 0,
       "T.faded() on the 3-hour lane, called the way every other lane is, still reads the whole book")
    other = T.faded(d, "pm_combo4", "tennis_pmcombo", venues=T.TRADEABLE_VENUES)
    eq(other["n"], 4, "T.faded() on pm_combo4 is still its four baskets")
    label = "Tennis 3-leg combo on Polymarket US"
    table_rows = [part for part in html.split("<tr>") if label in part.split("</tr>", 1)[0]]
    ok(bool(table_rows), "pm_combo3 is on the sandbox page")
    if ((by_name.get("pm_combo3") or {}).get("a") or {}).get("n") == 0:
        ok(any("Waiting for results" in part for part in table_rows),
           "an empty pm_combo3 record renders as Waiting for results")

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

    print("\nthe stamp counts a reset lane only from the tour clock")
    page = SB.hide_refused_tours(SB.hide_removed(d))
    stamp = SB.approval_table(page, T.score(page), full=d)
    for name in ("tennis_fav_band_3h", "tennis_combo2", "tennis_combo3",
                 "tennis_combo4", "pm_combo2", "pm_combo3"):
        judged = T.assess(SB.stamp_ledger(d, name), name, since=since)
        sample = next((c[3] for c in judged["criteria"] if c[0] == "sample"), None)
        row = _stamp_row(stamp, S.SOURCES[name]["label"])
        ok(bool(row) and sample is not None and sample in row,
           f"{name}'s stamp sample is its record since the tour clock")
        if judged["status"] == "unproven":
            ok("NO READ" in row, f"{name}'s stamp is still NO READ")
    h3_row = _stamp_row(stamp, S.SOURCES["tennis_fav_band_3h"]["label"])
    ok("20 bets" not in h3_row and "18 won" not in h3_row and "+14.3%" not in h3_row,
       "the 3-hour stamp does not carry the pre-clock kept-tour record")
    combo2 = _stamp_row(stamp, S.SOURCES["pm_combo2"]["label"])
    ok("+58.1%" not in combo2 and "3 bets over 2 days" not in combo2,
       "pm_combo2's stamp does not carry the pre-clock +58.1% on 3")
    kept4 = _stamp_row(stamp, S.SOURCES["pm_combo4"]["label"])
    ok("4 bets over 1 day" in kept4 and "2 won v 1.6 priced" in kept4,
       "pm_combo4's stamp is still its whole record")
    other = T.assess(SB.stamp_ledger(d, "oddspedia"), "oddspedia")
    sample = next((c[3] for c in other["criteria"] if c[0] == "sample"), None)
    ok(sample is not None and sample in _stamp_row(stamp, S.SOURCES["oddspedia"]["label"]),
       "a lane off the tour clock still shows its whole record on the stamp")
    fx_page = SB.hide_refused_tours(fx)
    fx_stamp = SB.approval_table(fx_page, T.score(fx_page), full=fx)
    fx_row = _stamp_row(fx_stamp, S.SOURCES["tennis_fav_band_3h"]["label"])
    ok("1 bets over 0 days" in fx_row and "1 won v 0.8 priced" in fx_row,
       "the stamp counts the post-reset kept bet and not the pre-reset one")

    print("\nthe audit leaves a refused row out of a reset lane's recount")
    import sandbox_audit as A
    rep = A.Report()
    A.check_records(_reset_fixture(), _reset_stages(), rep)
    record_errs = [msg for check, msg in rep.errors if check == "records"]
    first_err = next(iter(record_errs), None)
    ok(not record_errs,
       "check_records matches the page when a post-clock bet is a refused tour"
       + (f" — {first_err}" if first_err else ""))

    print(f"\n{'FAILED: ' + str(len(FAILS)) if FAILS else 'tennis tier filter passed'}")
    for item in FAILS:
        print(f"  - {item}")
    return 1 if FAILS else 0


if __name__ == "__main__":
    raise SystemExit(main())
