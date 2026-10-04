#!/usr/bin/env python3
"""A bad row must not move a number that does not depend on the bad field.

Fixture quotes and leads only. Nothing here reads the live ledger.

An unreadable start stays in the money totals and stays out of the halves
split and the day span. An unreadable kickoff is labeled, sorted last, and
left out of the next-lead tile and the still-to-come count. The audit warns
about an unreadable start; it does not fail the run for one.
"""
import contextlib
import datetime
import io
import re
from datetime import timezone

import fmt
import production
import sandbox_audit as A
import sandbox_build as SB
import sandbox_track as T

FAILS = []
NOW = datetime.datetime(2026, 9, 29, 18, 0, tzinfo=timezone.utc)


def ok(cond, why):
    print(f"  {'ok  ' if cond else 'FAIL'} {why}")
    if not cond:
        FAILS.append(why)


def eq(got, want, why):
    ok(got == want, why if got == want else f"{why} — got {got!r}, want {want!r}")


def _reset_warnings():
    T._BAD_START_SEEN.clear()
    production._BAD_KICKOFF.clear()


def _bet(i, start, pnl, source="lane", sport="tennis", **kw):
    won = pnl > 0
    q = dict(
        id=f"{source}:{i}", source=source, sport=sport, bet=True,
        status="won" if won else "lost", result="a" if won else "b", pick="a",
        pnl=float(pnl), stake=100.0, price=0.55, price_a=0.55, price_b=0.45,
        market_id=f"{source}-m{i}", venue="polymarket",
        logged="2026-08-01T00:00:00+00:00", start=start,
        settled="2026-09-02T00:00:00+00:00",
    )
    q.update(kw)
    return q


def _corrupt(q, how):
    q = dict(q)
    if how == "garbage":
        q["start"] = "garbage"
    elif how == "none":
        q["start"] = None
    elif how == "missing":
        q.pop("start", None)
    elif how == "invalid":
        q["start"] = "2026-99-99T99:99:99Z"
    else:
        raise ValueError(how)
    return q


def _assess(quotes, source, sport):
    err = io.StringIO()
    with contextlib.redirect_stderr(err):
        a = T.assess({"quotes": quotes, "_archive": []}, source, sport)
    return a, err.getvalue()


def _criterion(a, key):
    return next(c[3] for c in a["criteria"] if c[0] == key)


def _lead(match, kickoff, status, present=True):
    lead = {
        "status": status, "pair": "demo|soccer", "league": "Fixture League",
        "match": match, "headline": "Home to win", "price_at_log": 0.55,
    }
    if present:
        lead["kickoff"] = kickoff
    return lead


def _prod(leads):
    blob = {"leads": {str(i): lead for i, lead in enumerate(leads)}, "pairs": {}}
    err = io.StringIO()
    with contextlib.redirect_stderr(err):
        html = production.page({"quotes": []}, {"pairs": {}}, blob, "", now=NOW)
    return html, err.getvalue()


def _section(html, start_id, end_id):
    return html.split(f'id="{start_id}"', 1)[1].split(f'id="{end_id}"', 1)[0]


def _tile(html, label):
    m = re.search(
        rf'<div class="tile"><b(?: class="when")?>(.*?)</b><span>{re.escape(label)}</span>',
        html)
    return m.group(1) if m else None


def test_halves_and_span_ignore_unreadable_starts():
    print("\nunreadable start is out of the halves split and the day span")
    # Middle row. None used to sort first and garbage last, so the two
    # treatments moved this lane's halves to two different places.
    base = [
        _bet(0, "2026-09-01T00:00:00+00:00", 100),
        _bet(1, "2026-09-08T00:00:00+00:00", 50),
        _bet(2, "2026-09-15T00:00:00+00:00", -100),
        _bet(3, "2026-09-22T00:00:00+00:00", 80),
    ]
    other = [
        _bet(0, "2026-09-02T00:00:00+00:00", 40, source="other"),
        _bet(1, "2026-09-12T00:00:00+00:00", -20, source="other"),
        _bet(2, "2026-09-20T00:00:00+00:00", 30, source="other"),
    ]
    readable = [base[0], base[2], base[3]]
    _reset_warnings()
    only, _err = _assess(readable + other, "lane", "tennis")
    other_clean, _err = _assess(base + other, "other", "tennis")
    halves, spans = [], []
    for how in ("none", "missing", "garbage", "invalid"):
        _reset_warnings()
        bad = _corrupt(base[1], how)
        full, err = _assess([base[0], bad, base[2], base[3]] + other, "lane", "tennis")
        halves.append(_criterion(full, "halves"))
        spans.append(full["span_days"])
        eq(full["n"], only["n"] + 1, f"{how}: the bad row still counts in n")
        eq(full["pnl"], only["pnl"] + bad["pnl"], f"{how}: the bad row's P&L still counts")
        ok("::warning::" in err and "unreadable start" in err,
           f"{how}: the build emits a ::warning:: annotation")
        sibling, _err = _assess([base[0], bad, base[2], base[3]] + other, "other", "tennis")
        eq(_criterion(sibling, "halves"), _criterion(other_clean, "halves"),
           f"{how}: a lane with only readable starts keeps its halves")
        eq(sibling["span_days"], other_clean["span_days"],
           f"{how}: a lane with only readable starts keeps its span")
        eq(sibling["pnl"], other_clean["pnl"],
           f"{how}: a lane with only readable starts keeps its P&L")
    eq(len(set(halves)), 1, "None, missing, garbage, and an invalid date share one halves split")
    eq(halves[0], _criterion(only, "halves"),
       "the halves split is the readable rows, in start order")
    eq(len(set(spans)), 1, "None, missing, garbage, and an invalid date share one span")
    eq(spans[0], only["span_days"], "the day span is the readable endpoints")


def test_warning_clips_and_parses_iso_shaped_dates():
    print("\nunreadable start warning is an annotation and clips the value")
    _reset_warnings()
    huge = "Z" * 200_000
    err = io.StringIO()
    with contextlib.redirect_stderr(err):
        bad = T.note_unreadable_start({"id": "huge", "start": huge})
    text = err.getvalue()
    ok(bad, "a non-timestamp start is unreadable")
    ok(text.startswith("::warning::"), "the warning is a GitHub Actions annotation")
    ok(huge not in text and ("Z" * 80) in text and ("Z" * 81) not in text,
       "a 200 KB start is clipped to 80 characters")

    _reset_warnings()
    err = io.StringIO()
    with contextlib.redirect_stderr(err):
        bad = T.note_unreadable_start({"id": "shaped", "start": "2026-99-99T99:99:99Z"})
    text = err.getvalue()
    ok(bad and "::warning::" in text and "2026-99-99T99:99:99Z" in text,
       "an invalid date that looks like a timestamp warns")

    _reset_warnings()
    err = io.StringIO()
    with contextlib.redirect_stderr(err):
        bad = T.note_unreadable_start({"id": "naive", "start": "2026-09-01T00:00:00"})
    ok(not bad and err.getvalue() == "", "a naive timestamp is UTC and is not a warning")


def test_naive_endpoint_does_not_crash():
    print("\nnaive start on an endpoint is UTC")
    _reset_warnings()
    quotes = [
        _bet(0, "2026-09-01T00:00:00", 100),
        _bet(1, "2026-09-11T00:00:00+00:00", -40),
    ]
    try:
        a, err = _assess(quotes, "lane", "tennis")
    except Exception as e:
        ok(False, f"naive endpoint crashed: {type(e).__name__}: {e}")
        return
    eq(a["span_days"], 10.0, "naive UTC to an aware end is 10 days")
    eq(a["n"], 2, "both rows still count")
    ok("unreadable start" not in err, "a naive start is readable")


def test_price_row_non_string_start():
    print("\nprice row whose start is not a string")
    _reset_warnings()
    quotes = [
        _bet(0, "2026-09-01T00:00:00+00:00", 20),
        _bet(1, "2026-09-05T00:00:00+00:00", -5, status="settled", result="price",
             settle_px=0.4),
        _bet(2, 12345, -7, status="settled", result="price", settle_px=0.4),
    ]
    try:
        a, err = _assess(quotes, "lane", "tennis")
    except Exception as e:
        ok(False, f"non-string price start crashed: {type(e).__name__}: {e}")
        return
    eq(a["pnl"], 20 - 5 - 7, "the price row's P&L still counts")
    ok("::warning::" in err, "the non-string start warns")


def test_day_unit_representative_ignores_bad_start():
    print("\nday-unit representative is the earliest readable rung")
    early = _bet(0, "2026-09-01T00:00:00+00:00", 80, source="fixcrypto", sport="crypto",
                 market_id="KXSOLD-26SEP01-T100", date="2026-09-01",
                 price=0.70, price_a=0.40, price_b=0.70, result="b", pick="b")
    late = _bet(1, "2026-09-01T06:00:00+00:00", 40, source="fixcrypto", sport="crypto",
                market_id="KXSOLD-26SEP01-T110", date="2026-09-01",
                price=0.80, price_a=0.80, price_b=0.30, result="a", pick="a")
    _reset_warnings()
    clean, _err = _assess([early, late], "fixcrypto", "crypto")
    _reset_warnings()
    bad_late = _corrupt(late, "none")
    moved, err = _assess([early, bad_late], "fixcrypto", "crypto")
    eq(_criterion(moved, "baseline"), _criterion(clean, "baseline"),
       "a None start does not change the blind baseline")
    eq(moved["pnl"], clean["pnl"], "the day's P&L is unchanged")
    ok("::warning::" in err, "the bad rung warns")


def test_production_unknown_kickoff():
    print("\nproduction pending kickoff unknown")
    _reset_warnings()
    real = [
        _lead("First Real", "2026-09-30T20:00Z", "pending"),
        _lead("Second Real", "2026-10-01T20:00Z", "pending"),
        _lead("Third Real", "2026-10-02T20:00Z", "pending"),
    ]
    try:
        html, err = _prod(real + [
            _lead("None Pending", None, "pending"),
            _lead("Missing Pending", None, "pending", present=False),
            _lead("Garbage Pending", "garbage", "pending"),
        ])
    except Exception as e:
        ok(False, f"pending page crashed: {type(e).__name__}: {e}")
        return
    coming = _section(html, "coming-up", "recent")
    eq(_tile(html, "leads still to come"), "3",
       "an unreadable kickoff is not a lead still to come")
    eq(_tile(html, "next lead (CT)"), fmt.when("2026-09-30T20:00Z"),
       "the next-lead tile is the soonest readable kickoff")
    for match in ("First Real", "Second Real", "Third Real",
                  "None Pending", "Missing Pending", "Garbage Pending"):
        ok(match in coming, f"{match} is on Coming up")
    ok(coming.count("kickoff unknown") >= 3, "each unreadable kickoff is labeled kickoff unknown")
    last_real = coming.index("Third Real")
    for match in ("None Pending", "Missing Pending", "Garbage Pending"):
        ok(coming.index(match) > last_real, f"{match} sorts after the readable kickoffs")
    ok("::warning::" in err and "unreadable kickoff" in err,
       "the page emits a ::warning:: annotation")

    print("\nproduction settled kickoff stays visible past 25")
    _reset_warnings()
    settled = [
        _lead(f"Settled {i:02d}", f"2026-08-{i:02d}T18:00Z", "hit")
        for i in range(1, 30)
    ]
    settled.append(_lead("Ghost Row", None, "miss"))
    try:
        html, err = _prod(settled)
    except Exception as e:
        ok(False, f"settled page crashed: {type(e).__name__}: {e}")
        return
    recent = _section(html, "recent", "held-back")
    ok("Ghost Row" in recent, "a settled lead with no kickoff stays on Recently settled")
    ok("kickoff unknown" in recent, "the settled row is labeled kickoff unknown")
    ok("Settled 29" in recent, "the newest readable kickoff stays on the list")
    ok("::warning::" in err, "the settled page emits a ::warning:: annotation")


def test_audit_warns_on_unreadable_start():
    print("\naudit counts an unreadable start as a warning")
    paid = round(100.0 * (1 / 0.55 - 1), 2)
    good = _bet(0, "2026-09-01T00:00:00+00:00", paid)
    bad = _corrupt(_bet(1, "2026-09-02T00:00:00+00:00", -100), "none")
    rep = A.Report()
    A.check_bets({"quotes": [good, bad], "meta": {}}, rep)
    warned = [m for c, m in rep.warnings if c == "bets"]
    ok(warned and "1 bet" in warned[0] and bad["id"] in warned[0],
       "the audit warns and names the bet")
    ok(not rep.errors, "an unreadable start does not fail the audit")
    clean = A.Report()
    A.check_bets({"quotes": [good], "meta": {}}, clean)
    ok(not clean.warnings and not clean.errors, "a readable start adds no audit warning")


def test_flagged_void_one_bucket():
    print("\nflagged void is in one headline bucket")
    void = dict(id="v1", bet=True, status="void", result=None, pnl=0.0, price=0.5,
                stake=100.0, source="team2_form_l10", sport="soccer_team2", pick="a", side_a="Home",
                label="Flagged void", market_id="m-void", venue="polymarket",
                logged="2026-09-01T00:00:00+00:00", start="2026-09-02T00:00:00+00:00",
                settled="2026-09-03T00:00:00+00:00",
                excluded=T.CLIMATE_EXCLUDED, note="nws city-day: kept other under first")
    city = dict(void, id="c1", status="lost", result="b", pnl=-100.0, label="City repeat")
    quotes = [void, city]
    n_void = sum(1 for q in quotes if q["status"] == "void" and q["bet"])
    n_city = sum(1 for q in quotes if q.get("bet") and SB._cityday_repeat(q))
    eq((n_void, n_city), (1, 1), "the void stays a void and the lost repeat stays a city-day")
    ok(not SB._cityday_repeat(void), "a flagged void is not a city-day repeat")
    rows, n = SB.settled_rows({"quotes": quotes})
    eq(n, 1, "the flagged void is the one settled row")
    eq(rows.count('data-id="v1"'), 1, "the flagged void appears once")
    ok("VOID" in rows and fmt.money(0) in rows, "the flagged void keeps its result and P&L")


if __name__ == "__main__":
    print("bad rows")
    test_halves_and_span_ignore_unreadable_starts()
    test_warning_clips_and_parses_iso_shaped_dates()
    test_naive_endpoint_does_not_crash()
    test_price_row_non_string_start()
    test_day_unit_representative_ignores_bad_start()
    test_production_unknown_kickoff()
    test_audit_warns_on_unreadable_start()
    test_flagged_void_one_bucket()
    if FAILS:
        print(f"\n{len(FAILS)} FAILED")
        raise SystemExit(1)
    print("\nall passed")
