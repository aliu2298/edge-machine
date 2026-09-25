#!/usr/bin/env python3
"""Freshness of the published Sandbox and Production pages.

backup-refresh.yml used to read the site root. site_root.py rewrites that redirect
stub on every board refresh, so the root's "updated … UTC" stamp stays new even when
the tracker has stopped. The tracker's own stamp is on these two pages, in the form
written by sandbox_build.py and production.py:

    updated 2026-09-25 13:45 UTC

A missing or unparseable stamp is stale. The root stub's "Sep 25 2026 · 15:50 UTC"
form does not match, so a check pointed at the root fails closed.
"""
from datetime import datetime, timezone

# Takeover still fires at 5h: one missed 3h slot for the primary or the pages.
# The checks that fail the job wait until 7h. Scheduled sandbox-tracker.yml runs
# (cron 11 2-23/3) regularly land about 6h apart when GitHub delays them, so a
# 5h failure there would be red on a normal week. Only a manual dispatch keeps
# the gap under 5h.
TAKEOVER_AFTER_HOURS = 5
FAIL_AFTER_HOURS = 7
STALE_AFTER_HOURS = TAKEOVER_AFTER_HOURS
# GitHub Pages caches the deployed files for about 10 minutes. After deploy,
# refetch inside that window instead of trusting the first response.
RETRY_INTERVAL_SECONDS = 90
RETRY_WINDOW_SECONDS = 10 * 60
PAGES = ("sandbox.html", "production.html")


def parse_stamp(html):
    """First `updated YYYY-MM-DD HH:MM UTC` in `html`, or None if it is missing or not a time."""
    if not html:
        return None
    key = "updated "
    start = 0
    while True:
        i = html.find(key, start)
        if i < 0:
            return None
        raw = html[i + len(key):i + len(key) + 16]
        start = i + len(key)
        if len(raw) < 16 or raw[10] != " " or not html.startswith(" UTC", i + len(key) + 16):
            continue
        try:
            return datetime.strptime(raw, "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)
        except ValueError:
            continue


def freshness(html, now, page, stale_hours=STALE_AFTER_HOURS):
    """(ok, message). ok is False when `page` is older than `stale_hours`, or has no stamp.

    `message` always names `page`. When the stamp parses, it also names the age.
    """
    stamp = parse_stamp(html)
    if stamp is None:
        return False, f"{page} has no readable updated stamp"
    age = (now - stamp).total_seconds() / 3600.0
    msg = (f"{page} is {age:.1f}h old "
           f"(updated {stamp.strftime('%Y-%m-%d %H:%M')} UTC)")
    return age <= stale_hours, msg


def fetch_pages(base_url, stale_hours=STALE_AFTER_HOURS, now=None, opener=None,
                cache_bust=None):
    """(ok, message) for each published page, in PAGES order.

    A page that does not respond is not ok. `message` names the page.
    `cache_bust`, when set, is appended as `?t=<epoch>` so a CDN that is still
    holding the previous deploy is not reused.
    """
    import urllib.request
    if opener is None:
        opener = urllib.request.urlopen
    if now is None:
        now = datetime.now(timezone.utc)
    base = base_url.rstrip("/") + "/"
    results = []
    for page in PAGES:
        url = base + page
        if cache_bust is not None:
            url = f"{url}?t={int(cache_bust)}"
        try:
            with opener(url, timeout=30) as resp:
                body = resp.read().decode("utf-8", "replace")
        except Exception as e:
            results.append((False, f"{page} did not respond ({type(e).__name__})"))
            continue
        results.append(freshness(body, now, page, stale_hours=stale_hours))
    return results


def recheck_exit(results):
    """(exit_code, detail) after takeover, or when takeover did not run.

    Takeover rewrites index.html and redeploys. That cannot rebuild sandbox.html
    or production.html, so a page that is still stale or missing fails the job.
    exit_code is 1 in that case and 0 when every page is fresh. `detail` is the
    freshness messages, which name the page and, when the stamp parsed, its age.
    """
    bad = [msg for ok, msg in results if not ok]
    if bad:
        return 1, "; ".join(bad)
    return 0, "; ".join(msg for _ok, msg in results)


def recheck_until_fresh(base_url, stale_hours=FAIL_AFTER_HOURS, now=None, opener=None,
                        sleep=None, clock=None,
                        interval=RETRY_INTERVAL_SECONDS, window=RETRY_WINDOW_SECONDS):
    """Refetch until both pages are fresh, or `window` seconds have passed.

    The first fetch is immediate. Each later fetch waits `interval` seconds
    (60–90) and every URL carries `?t=<epoch>` from `clock`. `sleep` and `clock`
    are injectable so a test does not wait. Returns (exit_code, detail) from
    the fetch that passed, or from the last fetch if one page is still stale
    when the window runs out.
    """
    import time
    if sleep is None:
        sleep = time.sleep
    if clock is None:
        clock = time.time
    started = clock()
    attempts = int(window // interval) + 1
    code, detail = 1, "no page was fetched"
    for n in range(attempts):
        code, detail = recheck_exit(fetch_pages(
            base_url, stale_hours=stale_hours, now=now, opener=opener,
            cache_bust=clock()))
        if code == 0 or n + 1 == attempts:
            return code, detail
        if clock() - started + interval > window:
            return code, detail
        sleep(interval)
    return code, detail


def _fail_hours():
    import os
    return float(os.environ.get("FAIL_AFTER_HOURS", FAIL_AFTER_HOURS))


def recheck_main(opener=None, now=None, base_url=None):
    """One read of the live pages, judged on FAIL_AFTER_HOURS.

    This is the no-takeover path: nothing was just deployed, so there is no
    CDN window to wait out. Return 1 when either page is still stale or missing.
    """
    import os
    import sys
    base = base_url if base_url is not None else os.environ["BOARD_URL"]
    results = fetch_pages(base, stale_hours=_fail_hours(), now=now, opener=opener)
    code, detail = recheck_exit(results)
    for _ok, msg in results:
        print(msg, file=sys.stderr)
    if code:
        print(f"::error::{detail}", file=sys.stderr)
    return code


def recheck_after_deploy(sleep=None, clock=None, opener=None, now=None, base_url=None):
    """Refetch for about 10 minutes after a Pages deploy.

    Pass as soon as both pages are fresh. Print `::error::` with the page and
    its age only when one is still stale at the end of the window.
    """
    import os
    import sys
    base = base_url if base_url is not None else os.environ["BOARD_URL"]
    code, detail = recheck_until_fresh(
        base, stale_hours=_fail_hours(), now=now, opener=opener,
        sleep=sleep, clock=clock)
    print(detail, file=sys.stderr)
    if code:
        print(f"::error::{detail}", file=sys.stderr)
    return code
