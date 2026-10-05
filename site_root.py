#!/usr/bin/env python3
"""site_root.py — write public_site/index.html: the site root.

The root is the SofaScore shell and lands on Production. Its visible time is
Central Time. It must NOT contain the tracker stamp "updated YYYY-MM-DD HH:MM UTC":
that form lives on sandbox.html and production.html, and a freshness check
pointed at this page fails closed on purpose. backup-refresh.yml reads those two pages.

The tracker build (sandbox_build.production_and_index) is the producer of the
summary strip. This command does not count tiles. When production.html is
already beside the output, the shell copies that page's strip and clock.
refresh-boards does not run this command.

Usage:  python3 site_root.py
"""
import datetime
import os
import re

import fmt
import page_freshness
import shell_build

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "public_site", "index.html")


def _as_utc(now):
    """A datetime, or the old 'Sep 25 2026 · 15:50 UTC' string record_build still passes."""
    if isinstance(now, datetime.datetime):
        if now.tzinfo is None:
            return now.replace(tzinfo=datetime.timezone.utc)
        return now.astimezone(datetime.timezone.utc)
    text = str(now).strip()
    for pattern in ("%b %d %Y · %H:%M UTC", "%Y-%m-%d %H:%M UTC"):
        try:
            return datetime.datetime.strptime(text, pattern).replace(tzinfo=datetime.timezone.utc)
        except ValueError:
            continue
    return None


def root_stub(now, d=None, st=None, blob=None):
    """The site root: the shell, with Production selected. Not the watchdog stamp."""
    when = _as_utc(now)
    # An unparseable caller still gets a page. The visible stamp is their text,
    # and the headline clock falls back inside shell_build. No tracker form.
    return shell_build.page(when if when is not None else now, d=d, st=st, blob=blob)


def write_atomic(path, text):
    """Write path via a temp file and os.replace.

    open(path, "w") would truncate the live page before the new bytes exist, so a
    failed build would leave an empty index.html for the next step to publish.
    """
    directory = os.path.dirname(path)
    os.makedirs(directory, exist_ok=True)
    tmp = path + ".tmp"
    try:
        with open(tmp, "w") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except Exception:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def _clock_from_production(html, fallback):
    """The instant production.html was built, so a copy cannot move the clock."""
    match = re.search(r'<time datetime="(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z)"', html)
    if match:
        return datetime.datetime.strptime(
            match.group(1), "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=datetime.timezone.utc)
    parsed = page_freshness.parse_stamp(html)
    return parsed if parsed is not None else fallback


def main():
    """Write the shell. Tiles come from production.html when that page is there.

    A missing production page falls back to root_stub, which still asks
    production.page to count. The tracker build does not use that fallback:
    it passes the tiles it just computed. A failed write leaves the old file.
    """
    now = datetime.datetime.now(datetime.timezone.utc)
    prod_path = os.path.join(os.path.dirname(OUT), "production.html")
    if os.path.isfile(prod_path):
        with open(prod_path, encoding="utf-8") as fh:
            prod = fh.read()
        when = _clock_from_production(prod, now)
        text = shell_build.page(when, tiles=shell_build.tiles_html(prod))
        shown = when
    else:
        text = root_stub(now)
        shown = now
    write_atomic(OUT, text)
    print(f"wrote {OUT} ({fmt.display_updated(shown)})")


if __name__ == "__main__":
    main()
