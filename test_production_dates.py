#!/usr/bin/env python3
"""Production day groups follow the America/Chicago calendar, not the UTC date.

The Starts and Kickoff cells are fmt.when (Chicago day and CT clock). These
tests fail while Coming up still buckets a row by the UTC date, while a day
label is not "Today · Oct 7" / "Tomorrow · Oct 8" / "Oct 9", and while
Recently settled prints a UTC date instead of the Chicago kickoff.
"""
import datetime
import re
import sys
from datetime import timezone

import fmt
import production

FAILS = []


def ok(cond, why):
    print(f"  {'ok  ' if cond else 'FAIL'} {why}")
    if not cond:
        FAILS.append(why)


def eq(got, want, why):
    ok(got == want, why if got == want else f"{why} — got {got!r}, want {want!r}")


def _lead(match, kickoff, status="pending"):
    return {
        "status": status,
        "kickoff": kickoff,
        "pair": "demo|soccer",
        "league": "Fixture League",
        "match": match,
        "headline": "Home to win",
        "price_at_log": 0.55,
    }


def _page(leads, now):
    blob = {"leads": {str(i): lead for i, lead in enumerate(leads)}, "pairs": {}}
    return production.page({"quotes": []}, {"pairs": {}}, blob, "", now=now)


def _section(html, start_id, end_id):
    return html.split(f'id="{start_id}"', 1)[1].split(f'id="{end_id}"', 1)[0]


def _coming_label(html, match):
    """The day fold's label ("Today · Sep 27"), without its "· N leads" count."""
    section = _section(html, "coming-up", "recent")
    for summary, body in re.findall(
        r'<details class="fold"(?: open)?>\s*<summary>(.*?)</summary>(.*?)</details>',
        section,
        re.S,
    ):
        # The match is printed as "A vs B" (fmt.contest), whatever the lead stored.
        if fmt.contest(match) not in body:
            continue
        text = re.sub(r"<span\b.*?</span>", " ", summary, flags=re.S)
        return re.sub(r"<[^>]+>", " ", text).strip()
    return None


def _rows(section):
    return [row for row in re.findall(r"<tr>(.*?)</tr>", section, re.S) if "<td" in row]


def _settled_date(html, match):
    """The first (Kickoff) cell of the settled row for `match`."""
    section = _section(html, "recent", "held-back")
    for row in _rows(section):
        if fmt.contest(match) not in row:
            continue
        cell = re.findall(r"<td\b[^>]*>(.*?)</td>", row, re.S)[0]
        return re.sub(r"<[^>]+>", "", cell).strip()
    return None


def test_a_evening_cdt_lands_under_today():
    """2026-09-28T01:00Z is 8:00 PM CDT on Sep 27, so it is Today at 18:00Z."""
    print("\ntest_a_evening_cdt_lands_under_today")
    now = datetime.datetime(2026, 9, 27, 18, 0, tzinfo=timezone.utc)
    evening = "Evening FC v Night Owls"
    later = "Afternoon FC v Daylight"
    html = _page([
        _lead(evening, "2026-09-28T01:00Z"),
        _lead(later, "2026-09-28T20:00Z"),
    ], now)
    coming = _section(html, "coming-up", "recent")
    eq(_coming_label(html, evening), "Today · Sep 27",
       "(a) 2026-09-28T01:00Z (8:00 PM CDT Sep 27) lands under Today · Sep 27")
    eq(_coming_label(html, later), "Tomorrow · Sep 28",
       "(a) the next Chicago afternoon stays under Tomorrow · Sep 28")
    eq(len(_rows(coming)), 2, "(a) both coming-up rows are still on the page")
    ok("<th>Starts</th>" in coming, "(a) the first coming-up column is Starts")
    ok("Sep 27, 8:00 PM CT" in coming,
       "(a) the evening row shows the Chicago day and clock, Sep 27, 8:00 PM CT")
    ok("Evening FC vs Night Owls" in coming and "Evening FC v Night Owls" not in coming,
       "(a) the match is printed as A vs B")
    ok("2026-09-28" not in coming, "(a) no ISO date is printed in Coming up")
    ok("updated 2026-09-27 18:00 UTC" in html,
       "(a) the hidden UTC updated stamp is unchanged")
    # tables.js only measures the sticky header. It must not be an inline script,
    # and it must be the only script on the page.
    _scripts = re.findall(r"<script\b([^>]*)>(.*?)</script>", html, re.I | re.S)
    ok(len(_scripts) == 1 and 'src="./tables.js"' in _scripts[0][0]
       and not _scripts[0][1].strip(),
       "(a) the only script is same-origin tables.js, with no inline body")


def test_b_after_dst_cst_evening_is_nov_2():
    """2026-11-03T02:30Z is 8:30 PM CST on Nov 2, after the Nov 1 fall-back."""
    print("\ntest_b_after_dst_cst_evening_is_nov_2")
    now = datetime.datetime(2026, 11, 2, 18, 0, tzinfo=timezone.utc)
    match = "Fall Back FC v Standard Time"
    html = _page([_lead(match, "2026-11-03T02:30Z")], now)
    coming = _section(html, "coming-up", "recent")
    eq(_coming_label(html, match), "Today · Nov 2",
       "(b) 2026-11-03T02:30Z is 8:30 PM CST on Nov 2 and lands under Today · Nov 2")
    ok("Nov 2, 8:30 PM CT" in coming, "(b) the row shows Nov 2, 8:30 PM CT")
    ok("Nov 3" not in coming and "03 Nov" not in coming,
       "(b) neither the group nor the row shows the UTC date Nov 3")
    # 05:30Z is 11:30 PM CST on Nov 2, and 12:30 AM CDT on Nov 3. A fixed
    # UTC−5 offset would file this under Tomorrow.
    late = "Late CST Hour v Offset"
    late_html = _page([_lead(late, "2026-11-03T05:30Z")], now)
    late_coming = _section(late_html, "coming-up", "recent")
    eq(_coming_label(late_html, late), "Today · Nov 2",
       "(b) 2026-11-03T05:30Z stays on Nov 2 CST, not the next CDT date")
    ok("Nov 2, 11:30 PM CT" in late_coming, "(b) that row is Nov 2, 11:30 PM CT")


def test_today_label_uses_chicago_build_date():
    """'Today' is the Chicago date of the build, including after midnight UTC."""
    print("\ntest_today_label_uses_chicago_build_date")
    # 03:30Z Sep 28 is 10:30 PM CDT on Sep 27. A 1:00 PM CDT kickoff on Sep 28
    # is Tomorrow in Chicago and Today in UTC.
    now = datetime.datetime(2026, 9, 28, 3, 30, tzinfo=timezone.utc)
    match = "Next Chicago Day v UTC Same Day"
    html = _page([_lead(match, "2026-09-28T18:00Z")], now)
    eq(_coming_label(html, match), "Tomorrow · Sep 28",
       "today is the Chicago date of the build time")
    # 05:30Z Nov 3 is 11:30 PM CST on Nov 2. Noon CST on Nov 3 is Tomorrow.
    winter = datetime.datetime(2026, 11, 3, 5, 30, tzinfo=timezone.utc)
    winter_match = "Noon After Fallback v CST"
    winter_html = _page([_lead(winter_match, "2026-11-03T18:00Z")], winter)
    eq(_coming_label(winter_html, winter_match), "Tomorrow · Nov 3",
       "after DST ends, today is still the Chicago date of the build time")
    # Two days out gets no word, just the Chicago day.
    far = "Day After v Plain Date"
    far_html = _page([_lead(far, "2026-09-29T18:00Z")], now)
    eq(_coming_label(far_html, far), "Sep 29",
       "a kickoff two Chicago days out is labeled by its date alone")


def test_c_settled_date_column_is_chicago():
    """A kickoff at 2026-09-28T03:00Z is 10:00 PM CDT on Sep 27.

    The Kickoff cell is fmt.when: the Chicago day and the CT clock.
    """
    print("\ntest_c_settled_date_column_is_chicago")
    now = datetime.datetime(2026, 9, 28, 16, 0, tzinfo=timezone.utc)
    moved = "Settled Night v Late Kick"
    same = "Settled Afternoon v Same Date"
    html = _page([
        _lead(moved, "2026-09-28T03:00Z", status="hit"),
        _lead(same, "2026-09-27T18:00Z", status="miss"),
    ], now)
    recent = _section(html, "recent", "held-back")
    ok("<th>Kickoff</th>" in recent, "(c) the first settled column is Kickoff")
    eq(_settled_date(html, moved), "Sep 27, 10:00 PM CT",
       "(c) a settled row at 2026-09-28T03:00Z shows Kickoff Sep 27, 10:00 PM CT")
    eq(_settled_date(html, same), "Sep 27, 1:00 PM CT",
       "(c) a kickoff already on that Chicago date shows Sep 27, 1:00 PM CT")
    ok("2026-09-27" not in recent and "2026-09-28" not in recent,
       "(c) no ISO date is printed in Recently settled")
    ok("Settled Night vs Late Kick" in recent, "(c) the settled match is printed as A vs B")
    eq(len(_rows(recent)), 2, "(c) both settled rows are still on the page")
    ok("landed" in recent and "missed" in recent,
       "(c) hit and miss labels are unchanged")
    ok("updated 2026-09-28 16:00 UTC" in html,
       "(c) the hidden UTC updated stamp is unchanged")


if __name__ == "__main__":
    test_a_evening_cdt_lands_under_today()
    test_b_after_dst_cst_evening_is_nov_2()
    test_today_label_uses_chicago_build_date()
    test_c_settled_date_column_is_chicago()
    if FAILS:
        print(f"\n{len(FAILS)} FAILED")
        sys.exit(1)
    print("\nall passed")
