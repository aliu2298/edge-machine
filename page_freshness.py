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

STALE_AFTER_HOURS = 5
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


def fetch_pages(base_url, stale_hours=STALE_AFTER_HOURS, now=None, opener=None):
    """(ok, message) for each published page, in PAGES order.

    A page that does not respond is not ok. `message` names the page.
    """
    import urllib.request
    if opener is None:
        opener = urllib.request.urlopen
    if now is None:
        now = datetime.now(timezone.utc)
    base = base_url.rstrip("/") + "/"
    results = []
    for page in PAGES:
        try:
            with opener(base + page, timeout=30) as resp:
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


def recheck_main():
    """Re-read the live pages. Return 1 when either is still stale or missing."""
    import os
    import sys
    hours = float(os.environ.get("STALE_AFTER_HOURS", STALE_AFTER_HOURS))
    results = fetch_pages(os.environ["BOARD_URL"], stale_hours=hours)
    code, detail = recheck_exit(results)
    for _ok, msg in results:
        print(msg, file=sys.stderr)
    if code:
        print(f"::error::{detail}", file=sys.stderr)
    return code
