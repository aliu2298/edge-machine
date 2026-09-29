#!/usr/bin/env python3
"""A bad row must not take the site build down.

Fails while assess() raises on a settled bet whose start is garbage, None,
or missing; while production.page raises on a lead whose kickoff is missing
or None; and while a void flagged excluded='nws_cityday' is counted both as
a void and as a city-day repeat.

The build keeps every settled result and P&L. A bad start or kickoff is a
dash and a warning. A flagged void is in exactly one headline bucket.
"""
import contextlib
import datetime
import io
import re
import sys
from datetime import timezone

import fmt
import production
import sandbox_build as SB
import sandbox_track as T

FAILS = []
NOW = datetime.datetime(2026, 9, 29, 18, 0, tzinfo=timezone.utc)
ST = None
CLEAN = None
CLEAN_HEAD = None


def ok(cond, why):
    print(f"  {'ok  ' if cond else 'FAIL'} {why}")
    if not cond:
        FAILS.append(why)


def eq(got, want, why):
    ok(got == want, why if got == want else f"{why} — got {got!r}, want {want!r}")


def _headline(html):
    m = re.search(
        r"([\d,]+) settled on the record(?: · ([\d,]+) void)?"
        r"(?: · ([\d,]+) city-day repeats? set aside)?; older bets are in the archive",
        html)
    if not m:
        return None

    def n(group):
        return int(group.replace(",", "")) if group else 0

    return n(m.group(1)), n(m.group(2)), n(m.group(3))


def _rows(pages, qid):
    needle = f'data-id="{SB.esc(qid)}"'
    found = []
    for page in pages:
        for part in page.split("<tr"):
            if not part:
                continue
            head, _, _rest = part.partition(">")
            if needle not in head:
                continue
            body = part.split("</tr>", 1)[0]
            found.append("<tr" + body + "</tr>")
    return found


def _render(d):
    err = io.StringIO()
    with contextlib.redirect_stderr(err):
        sandbox, _index, weeks = SB.render_pages(now=NOW, d=d, st=ST)
    return [sandbox, *weeks.values()], err.getvalue()


def _pick(d, status, result=None, sport=None):
    rows = [q for q in d["quotes"]
            if q.get("bet") and q.get("status") == status
            and isinstance(q.get("pnl"), (int, float)) and q.get("id")
            and (result is None or q.get("result") == result)
            and (sport is None or q.get("sport") == sport)]
    if not rows:
        raise SystemExit(f"no settled {status} row to corrupt")
    return rows[len(rows) // 2]


def _apply_start(q, how):
    if how == "garbage":
        q["start"] = "garbage"
    elif how == "none":
        q["start"] = None
    elif how == "missing":
        q.pop("start", None)
    else:
        raise ValueError(how)


def _check_settled(status, how, result=None, sport=None):
    label = status if result is None else f"{status}/{result}"
    if sport:
        label = f"{label} {sport}"
    print(f"\nsettled {label}, start {how}")
    d = T.load()
    q = _pick(d, status, result=result, sport=sport)
    pnl, qid = q["pnl"], q["id"]
    klass, badge = SB._badge(q)
    _apply_start(q, how)
    try:
        pages, err = _render(d)
    except Exception as e:
        ok(False, f"build failed on {label} start {how}: {type(e).__name__}: {e}")
        return
    rows = _rows(pages, qid)
    eq(len(rows), 1, f"{qid} still appears once")
    if rows:
        ok(fmt.money(pnl) in rows[0], f"P&L still {fmt.money(pnl)}")
        ok(f'class="st {klass}"' in rows[0] and f">{badge}<" in rows[0],
           f"result still {badge}")
    eq(_headline(pages[0]), CLEAN_HEAD, "settled / void / city-day totals unchanged")
    ok("unreadable start" in err, "the build logs a warning and continues")


def test_bad_starts():
    cases = [
        ("won", "garbage", None, None),
        ("won", "none", None, None),
        ("won", "missing", None, None),
        ("lost", "garbage", None, None),
        ("lost", "none", None, None),
        ("lost", "missing", None, None),
        ("void", "garbage", None, None),
        ("void", "none", None, None),
        ("void", "missing", None, None),
        ("settled", "garbage", "price", None),
        ("settled", "none", "price", None),
        ("settled", "missing", "price", None),
        ("won", "none", None, "crypto"),
        ("won", "missing", None, "commodities"),
    ]
    for status, how, result, sport in cases:
        _check_settled(status, how, result=result, sport=sport)


def _lead(match, kickoff, status, present=True):
    lead = {
        "status": status,
        "pair": "demo|soccer",
        "league": "Fixture League",
        "match": match,
        "headline": "Home to win",
        "price_at_log": 0.55,
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


def test_production_kickoff():
    print("\nproduction pending kickoff missing or None")
    try:
        html, err = _prod([
            _lead("Good Pending", "2026-09-30T20:00Z", "pending"),
            _lead("None Pending", None, "pending"),
            _lead("Missing Pending", None, "pending", present=False),
            _lead("Garbage Pending", "garbage", "pending"),
        ])
    except Exception as e:
        ok(False, f"pending page crashed: {type(e).__name__}: {e}")
    else:
        coming = _section(html, "coming-up", "recent")
        for match in ("Good Pending", "None Pending", "Missing Pending", "Garbage Pending"):
            ok(match in coming, f"{match} is on Coming up")
        ok(">—<" in coming or ">—</td>" in coming,
           "an unreadable kickoff shows a dash")
        ok("unreadable kickoff" in err, "the page logs a warning and continues")

    print("\nproduction settled kickoff missing or None")
    try:
        html, err = _prod([
            _lead("Good Settled", "2026-09-20T20:00Z", "hit"),
            _lead("None Settled", None, "miss"),
            _lead("Missing Settled", None, "price", present=False),
            _lead("Garbage Settled", "not-a-kickoff", "hit"),
        ])
    except Exception as e:
        ok(False, f"settled page crashed: {type(e).__name__}: {e}")
    else:
        recent = _section(html, "recent", "held-back")
        for match in ("Good Settled", "None Settled", "Missing Settled", "Garbage Settled"):
            ok(match in recent, f"{match} is on Recently settled")
        ok("landed" in recent and "missed" in recent and "paid" in recent,
           "hit, miss, and price labels are unchanged")
        ok("unreadable kickoff" in err, "the page logs a warning and continues")


def test_flagged_void_one_bucket():
    print("\nflagged void is in one headline bucket")
    d = T.load()
    q = _pick(d, "void")
    qid, pnl = q["id"], q["pnl"]
    q["excluded"] = T.CLIMATE_EXCLUDED
    q["note"] = "nws city-day: kept other under first"
    try:
        pages, _err = _render(d)
    except Exception as e:
        ok(False, f"build failed on a flagged void: {type(e).__name__}: {e}")
        return
    got = _headline(pages[0])
    eq(got, CLEAN_HEAD,
       "flagging a void does not change settled / void / city-day")
    rows = _rows(pages, qid)
    eq(len(rows), 1, f"flagged void {qid} appears once")
    if rows:
        ok(fmt.money(pnl) in rows[0], f"flagged void P&L still {fmt.money(pnl)}")
        ok('class="st void"' in rows[0] and ">VOID<" in rows[0],
           "flagged void is still a void")
    if got is not None and CLEAN_HEAD is not None:
        # Same three numbers means it did not enter the city-day count and
        # did not leave the void count. The row above is that one bucket.
        ok(got[2] == CLEAN_HEAD[2] and got[1] == CLEAN_HEAD[1],
           "the flagged void is not in a second headline bucket")


if __name__ == "__main__":
    print("bad rows")
    ST = T.load_stages()
    d = T.load()
    try:
        CLEAN, _err = _render(d)
    except Exception as e:
        print(f"  FAIL clean build: {type(e).__name__}: {e}")
        sys.exit(1)
    CLEAN_HEAD = _headline(CLEAN[0])
    if CLEAN_HEAD is None:
        print("  FAIL clean page has no settled headline")
        sys.exit(1)
    print(f"  clean headline settled/void/city-day {CLEAN_HEAD[0]:,} / "
          f"{CLEAN_HEAD[1]:,} / {CLEAN_HEAD[2]:,}")
    test_bad_starts()
    test_production_kickoff()
    test_flagged_void_one_bucket()
    if FAILS:
        print(f"\n{len(FAILS)} FAILED")
        sys.exit(1)
    print("\nall passed")
