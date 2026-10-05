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
import hashlib
import json
import math
import os
import re
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
        _row("aec-atp-late-bb-2026-10-02", 0.78, NOW + timedelta(hours=4), "polymarket_us"),
        _row("aec-atp-low-bb-2026-10-02", 0.69, start, "polymarket_us"),
        _row("aec-atp-edge-bb-2026-10-02", 0.70, start, "polymarket_us"),
        _row("aec-atp-inside-bb-2026-10-02", 0.84, start, "polymarket_us"),
        _row("aec-atp-high-bb-2026-10-02", 0.85, start, "polymarket_us"),
    ]
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


def _fixture_path(name):
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", name)


def _frozen_looked_at():
    """The looked-at bets the note's figures and the overlap rule read.

    A checked-in snapshot under fixtures/, not under data/. The first row of
    each contest is the one the note's figures use. The other lane's bet on
    each overlap is stored after that, so the overlap rule can be run again
    without the live ledger. A later tracker row or a void does not move this
    file.

    Medvedev v Royer (aec-atp-danmed-valroy-2026-09-23): the first stored row
    is the 3-hour copy. The parent row stored after it is the pre-void 'won',
    not the void written on the live ledger later.
    """
    with open(_fixture_path("tennis_fav_looked_at.json")) as fh:
        return json.load(fh)


def _contest_rows(rows):
    """One row per contest: the first stored row of that market.

    A twin of the other lane, appended later in the snapshot, does not replace
    it and does not enter the published figures.
    """
    out = []
    seen = set()
    for q in rows:
        mid = q.get("market_id")
        if not mid or mid in seen:
            continue
        seen.add(mid)
        out.append(q)
    return out


def _frozen_overlaps():
    """The overlap ids the note counted, frozen beside the looked-at snapshot.

    Checked against the overlap rule on that snapshot, not against the length
    of this list.
    """
    with open(_fixture_path("tennis_fav_overlaps.json")) as fh:
        return json.load(fh)


# Each pin is sha256 of that fixture's bytes. Each file is exactly
# json.dumps(obj, indent=2) + "\n". After an edit, rewrite it that way and
# print the new digest; a one-cent change that skips this step fails the pin:
#   python3 -c "import json,hashlib,pathlib; p=pathlib.Path('fixtures/tennis_fav_looked_at.json'); obj=json.loads(p.read_text()); raw=(json.dumps(obj, indent=2)+'\n').encode(); p.write_bytes(raw); print(hashlib.sha256(raw).hexdigest())"
# The overlap list is the same command with fixtures/tennis_fav_overlaps.json.
# The settled-pair list is the same command with fixtures/tennis_settled_pairs.json.
#
# That settled-pair file is every "name|sport" that has ever had a settled
# tradeable bet and that the page rendered when the list was frozen. A
# settled tradeable bet is a ledger or archive row with bet set, a venue in
# TRADEABLE_VENUES, and status won, lost, or settled with result "price".
# Removed lanes are not listed. The test reads the file. It does not rebuild
# the list from SOURCES or from pair_list, so a drop upstream fails until
# the file is edited on purpose. To rebuild after a deliberate removal,
# take the sorted names of that intersection, write them with the command
# above, and pin the digest it prints. Refreshing the list to cover a new
# pair is the same edit; the test does not require it.
LOOKED_AT_SHA256 = "323618ead3340efcbbe70a5752c94581db3bb63fc4911a1446d56067967f7920"
OVERLAPS_SHA256 = "0f3c41a83d4cdf24ac17661616e3dac44c3151e1da5501b67eb8d76c16875419"
SETTLED_PAIRS_SHA256 = "cfa55e451f4744ee6b6b971cf6e0ed616a82474d1d7f0097ca0f867c38a7c695"


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
    utr = _figures(by["utr"])
    eq(len(kept), 78, "frozen kept set is 78 contests")
    eq(round(utr["unit"], 2), 2.45, "frozen UTR unit +2.45 before fees")
    eq(round(wta["unit"], 2), 0.96, "frozen WTA Doubles unit +0.96 before fees")
    eq((round(keep_f["z"], 2), round(keep_f["fade"] * 100, 1), round(keep_f["fade_z"], 2)),
       (2.76, -68.7, -3.06), "frozen kept set: z +2.76 before fees, fade -68.7% / z -3.06")
    eq((round(whole["unit"], 2), round(whole["z"], 2), round(whole["roi"] * 100, 1)),
       (18.49, 1.85, 2.4), "frozen whole band: unit, z, and ROI")
    eq((round(whole["fade"] * 100, 1), round(whole["fade_z"], 2)),
       (-24.1, -2.88), "frozen whole-band fade -24.1% / z -2.88")
    digest = hashlib.sha256(open(_fixture_path("tennis_fav_looked_at.json"), "rb").read()).hexdigest()
    eq(digest, LOOKED_AT_SHA256, "a one-cent edit of the looked-at snapshot changes its sha256")
    days = {q["date"] for q in rows}
    span = (datetime.fromisoformat(max(days)) - datetime.fromisoformat(min(days))).days + 1
    eq((round(len(rows) / span, 1), round(len(kept) / span, 1)),
       (36.0, 4.3), "frozen record: 36.0 contests a day, 4.3 on the kept tours")


def _check_overlap_ids(rows, overlap_ids):
    """The overlap fixture's ids, recomputed from the looked-at snapshot.

    The set is the overlap rule on those rows, every id is one of those
    contests, and the file's sha256 is pinned. A swapped, dropped, or added
    id fails the set, and a bogus id also fails membership.
    """
    recomputed = _band_overlap_ids({"quotes": rows})
    got = set(overlap_ids)
    extra = sorted(got - recomputed)
    missing = sorted(recomputed - got)
    eq(got, recomputed,
       "the overlap ids are the overlap rule on the looked-at snapshot"
       + (f" — not an overlap: {extra}" if extra else "")
       + (f" — missing: {missing}" if missing else ""))
    markets = {q.get("market_id") for q in rows}
    outside = sorted(i for i in got if i not in markets)
    ok(not outside, "every overlap id is in the looked-at snapshot"
       + (f" — {outside}" if outside else ""))
    digest = hashlib.sha256(open(_fixture_path("tennis_fav_overlaps.json"), "rb").read()).hexdigest()
    eq(digest, OVERLAPS_SHA256, "an edit of the overlap id list changes its sha256")


def _has_phrase(note, phrase):
    """True when phrase occurs as its own tokens.

    A bare substring is not enough: '9 contests' is inside '19 contests', and
    '-24.1%' is still present after it trades places with '-68.7%'. The
    character before the phrase must not be a word character. The character
    after must not be a word character or a decimal continuation ('.' then a
    digit): 'on those 9.5' is not 'on those 9', and '(z -2.88.1' is not
    '(z -2.88'.
    """
    return re.search(r"(?<!\w)" + re.escape(phrase) + r"(?!\w|\.\d)", note) is not None


def _fade_pct(fade):
    """A fade ROI in percent, with the sign.

    ':.1f' prints a positive fade with no plus. '-' is not a word character,
    so that unsigned text matches a '-x%' already in the note. ':+.1f' does not.
    """
    return f"{fade * 100:+.1f}"


def _note_phrases(rows, overlap_ids):
    """The published note's frozen figures, in the note's own words.

    The numbers come from the frozen snapshot. ATP's backed-side z is pinned
    on the snapshot; the note does not print that z. The WTA Doubles ROI sits
    on the 'rests on {n} contests' sentence, so a second copy of the same ROI
    elsewhere does not satisfy it.
    """
    by = collections.defaultdict(list)
    for q in rows:
        by[_tier(q)].append(q)
    kept = [q for q in rows if _tier(q) in KEEP]
    atp = _figures(by["atp"])
    utr = _figures(by["utr"])
    wta = _figures(by["wtadb"])
    keep_f = _figures(kept)
    whole = _figures(rows)
    _rate, span = _per_day(rows)
    kept_rate = round(len(kept) / span, 1)
    return (
        f"{len(rows)} distinct contests already logged ({len(overlap_ids)} that the parent lane and this lane both bet, counted once)",
        f"On the {span} days those contests cover, that was {_rate:.1f} contests a day",
        f"the kept tours were {kept_rate:.1f}",
        f"{len(kept)} contests, z {keep_f['z']:+.2f} before fees",
        f"WTA Doubles rests on {wta['n']} contests, ROI {wta['roi'] * 100:+.1f}% after fees",
        f"{_fade_pct(wta['fade'])}% on those {wta['n']}",
        f"{_fade_pct(whole['fade'])}% on the whole band (z {whole['fade_z']:+.2f}",
        f"{_fade_pct(keep_f['fade'])}% on the kept set (z {keep_f['fade_z']:+.2f}",
        f"ATP {atp['unit']:+.2f}, UTR {utr['unit']:+.2f}, WTA Doubles {wta['unit']:+.2f}",
    )


def _check_note_quotes(note, rows, overlap_ids):
    """The published note quotes these frozen figures, each in its own words."""
    for phrase in _note_phrases(rows, overlap_ids):
        ok(_has_phrase(note, phrase), f"the 3-hour note quotes the frozen record: {phrase}")


def _check_phrase_guards(rows, overlap_ids):
    """The three phrase guards. Each fails on the looser check it replaces."""
    short = "-60.6% on those 9"
    ok(not _has_phrase("returned -60.6% on those 9.5, next", short),
       "on those 9.5 is not on those 9")
    ok(_has_phrase("returned -60.6% on those 9, next", short),
       "on those 9 still matches when the next character is a comma")
    ok(not _has_phrase("(z -2.88.1 on the fade", "(z -2.88"),
       "a z of -2.88.1 is not z -2.88")
    phrases = _note_phrases(rows, overlap_ids)
    wta_line = next(p for p in phrases if p.startswith("WTA Doubles rests on"))
    ok(", ROI " in wta_line and wta_line.endswith("% after fees"),
       "the WTA Doubles phrase includes its ROI")
    stray = ("UTR was ROI +12.0% after fees. "
             "WTA Doubles rests on 9 contests, ROI +13.0% after fees.")
    ok(not _has_phrase(stray, wta_line),
       "a stray ROI +12.0% after fees does not satisfy the WTA Doubles line")
    ok(_has_phrase(
        "WTA Doubles rests on 9 contests, ROI +12.0% after fees: a direction",
        wta_line),
       "the WTA Doubles line matches when the ROI sits on that sentence")
    ok(_fade_pct(-0.241) == "-24.1", "a negative fade still prints with its minus")
    pos = _fade_pct(0.241)
    ok(pos == "+24.1", "a positive fade prints with a plus")
    # The z is left off on purpose. A full phrase whose z also differs would
    # miss the leak: '-' is not a word character, so unsigned "24.1%" matches
    # inside "-24.1%".
    ok(not _has_phrase("-24.1% on the whole band (z -2.88",
                       f"{pos}% on the whole band"),
       "a positive fade does not match a minus-sign phrase")


def _check_record_clock_note(note):
    """The page record is the merge. 05:00 is only the looked-at cutoff.

    The old sentence called 05:00 the clock and said nothing was logged on
    the kept tours between that clock and the widening. Two kept-tour bets
    were logged in the author-to-merge gap, so that claim is false when the
    clock is read as 05:00.
    """
    record = "2026-10-02T16:34:37Z"
    evidence = "2026-10-02T05:00:00Z"
    ok(f"page record restarts at {record}" in note,
       "the note says the page record restarts at the merge")
    ok(f"{evidence} is the looked-at cutoff" in note,
       "05:00 stays as the looked-at cutoff for the 648-contest figures")
    ok("not the page record" in note,
       "the note says the 05:00 cutoff is not the page record")
    ok(f"The clock starts {evidence}" not in note,
       "the note does not say the clock starts at 05:00")
    ok("Nothing was logged on the kept tours between the 2026-10-02 tour clock" not in note,
       "the note does not claim nothing was logged against the unnamed tour clock")
    ok(re.search(r"(?:clock starts|record restarts at|page record restarts at)\s*"
                 + re.escape(evidence), note) is None,
       "05:00 is not the record clock")
    ok("stay on file under the old rule" in note and "do not count in the record" in note,
       "the note says the author-to-merge gap bets stay on file and do not count")


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


def _frozen_settled_pairs():
    """The settled-pair names, frozen beside the looked-at snapshot.

    A checked-in list under fixtures/, not a walk of SOURCES. Editing it is
    how a pair leaves the check. Losing the pair from the page is not.
    """
    with open(_fixture_path("tennis_settled_pairs.json")) as fh:
        return json.load(fh)


def _check_settled_pairs(rendered):
    """Every listed pair still renders. The list is not pair_list's output.

    A pair with no settled bet can render and stay off the list. A listed
    pair that the page drops fails here, including a drop upstream of
    pair_list. The sha pin is the file's bytes.
    """
    listed = set(_frozen_settled_pairs())
    missing = sorted(listed - set(rendered))
    ok(not missing, "every frozen settled pair still renders"
       + (f" — dropped: {missing}" if missing else ""))
    ok(set(rendered) - listed,
       "the settled-pair list is not every rendered pair")
    digest = hashlib.sha256(
        open(_fixture_path("tennis_settled_pairs.json"), "rb").read()).hexdigest()
    eq(digest, SETTLED_PAIRS_SHA256,
       "an edit of the settled-pair list changes its sha256")


def _wired_pairs(d, st, include_retired=True):
    """The source|sport pairs the listing rule renders, from the wiring.

    Walks SOURCES with the same keep-or-skip rule pair_list uses: removed
    lanes stay off, a baseline does not render, and a pair appears once it
    has bet, is a cup or international twin, is a consensus row, or carries
    a reset that still has a record. pair_list itself is not called, so a
    later edit that drops one rendered pair fails here. A pair added to the
    wiring is expected without a new literal.
    """
    out = set()
    for name, meta in S.SOURCES.items():
        if name in S.REMOVED_SOURCES:
            continue
        if meta.get("kind") in T.NEVER_PROMOTED_KINDS:
            continue
        sports = list(meta["sports"]) if meta["connected"] else []
        gone = {} if not include_retired else dict(
            {sp: why for sp, why in (meta.get("retired_sports") or {}).items()},
            **({sp: meta["retired"] for sp in meta["sports"]}
               if not meta["connected"] and meta.get("retired") else {}))
        for sport in sports + [sp for sp in gone if sp not in sports]:
            if S.lane_removed(name, sport):
                continue
            group, _a, _qa, _open_n, _last, pair = SB.pair_status(d, st, name, sport)
            reset_row = bool(pair.get("since")) and bool(
                T.assess(d, name, sport, venues=T.TRADEABLE_VENUES)["n"])
            scope = next((x for x in S.SCOPE_LABEL if str(sport).endswith(x)), "")
            if (group is None and not scope
                    and name not in T.CONSENSUS and not reset_row):
                continue
            out.add(f"{name}|{sport}")
    return out


def main():
    print("\nkept tours are an exact set, not a prefix")
    eq(getattr(S, "TENNIS_FAV_KEEP", None), KEEP,
       "the keep set is exactly ATP, WTA Doubles, and UTR")
    eq(S.BAND_BY_SPORT["tennis"], (0.77, 0.81), "the price band is still 0.77-0.81")
    eq(S.TENNIS_3H_BAND, (0.70, 0.85), "the 3-hour band is still 0.70-0.85")
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
                    "aec-atp-edge-bb-2026-10-02", "aec-atp-inside-bb-2026-10-02"]),
       "0.70 and 0.84 are picked; 0.69 and 0.85 are not")
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
    raw = _frozen_looked_at()
    frozen = _contest_rows(raw)
    overlaps = _frozen_overlaps()
    _check_frozen_note(frozen)
    _check_note_quotes(note, frozen, overlaps)
    _check_phrase_guards(frozen, overlaps)
    _check_record_clock_note(note)
    _check_overlap_ids(raw, overlaps)

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
    rendered = {f"{r['name']}|{r['sport']}" for r in rows}
    wired = _wired_pairs(d, st)
    missing = sorted(wired - rendered)
    extra = sorted(rendered - wired)
    eq(rendered, wired,
       "the rendered pairs are the wired pairs, by name"
       + (f" — dropped: {missing}" if missing else "")
       + (f" — not wired: {extra}" if extra else ""))
    _check_settled_pairs(rendered)
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
    judge = T.assess(d, "pm_combo4", "tennis_pmcombo", venues=T.TRADEABLE_VENUES)
    won4 = sum(q.get("status") == "won" for q in p4)
    eq(len(p4), judge["n"], "pm_combo4's settled baskets are the record assess counts")
    eq(won4, judge["won"], "pm_combo4's wins are those baskets")
    eq(len(p4) - won4, judge["n"] - judge["won"], "pm_combo4's losses are the rest of that record")
    ok(all(f'data-id="{q["id"]}"' in blob for q in p4),
       "pm_combo4's baskets stay on the rendered page")
    ok(all(not _refused_tour(q) for q in p4),
       "pm_combo4 is not treated as a reset lane")
    whole_fade = T.faded(d, "tennis_fav_band_3h", "tennis", venues=T.TRADEABLE_VENUES)
    ok(whole_fade["n"] > 0,
       "T.faded() on the 3-hour lane, called the way every other lane is, still reads the whole book")
    other = T.faded(d, "pm_combo4", "tennis_pmcombo", venues=T.TRADEABLE_VENUES)
    eq(other["n"], len(p4), "T.faded() on pm_combo4 counts those same baskets")
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
    span4 = judge["span_days"]
    day4 = "day" if round(span4) == 1 else "days"
    ok(f"{judge['n']} bets over {span4:.0f} {day4}" in kept4
       and f"{judge['won']} won v {judge['expected']:.1f} priced" in kept4,
       "pm_combo4's stamp quotes the record assess reads")
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
