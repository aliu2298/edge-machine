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
