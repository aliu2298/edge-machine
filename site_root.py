#!/usr/bin/env python3
"""site_root.py — write public_site/index.html: the site root.

The root is the SofaScore shell and lands on Production. Its visible time is
Central Time. It must NOT contain the tracker stamp "updated YYYY-MM-DD HH:MM UTC":
that form lives on sandbox.html and production.html, and a freshness check
pointed at this page fails closed on purpose. backup-refresh.yml reads those two pages.

The tracker build (sandbox_build.production_and_index) is the only producer of
the summary strip and the Running block. This command does not count tiles and
does not rebuild Running from the ledger. When index.html already carries
production.html's stamp, it is left untouched. Otherwise the tiles, the clock,
and the Running block are copied from those tracker-written pages.
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


def _stamp_token(html):
    match = re.search(
        r'<time datetime="(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z)"', html or "")
    return match.group(1) if match else None


def _swap_time(html, prod_html):
    """Put production.html's clock on the shell without its machine stamp."""
    prod_time = re.search(r'<time datetime="[^"]+"[^>]*>.*?</time>', prod_html, re.S)
    if not prod_time:
        return html
    # A lambda keeps backslashes in the clock text. A plain replacement
    # string would read them as group references.
    return re.sub(
        r'<time datetime="[^"]+"[^>]*>.*?</time>',
        lambda _: prod_time.group(0),
        html,
        count=1,
        flags=re.S,
    )


def _copy_from_tracker(index_html, prod_html):
    """Tiles and clock from production.html. Running stays the tracker block.

    Returns None when index.html has no tracker Running block to copy. The
    caller then writes an empty list rather than reading the ledger.
    """
    if 'class="running-filters"' not in (index_html or ""):
        return None
    try:
        old_tiles = shell_build.tiles_html(index_html)
    except RuntimeError:
        return None
    if old_tiles not in index_html:
        return None
    tiles = shell_build.tiles_html(prod_html)
    return _swap_time(index_html.replace(old_tiles, tiles, 1), prod_html)


def _empty_shell(prod_html, when):
    """Chrome and the production strip, with no Running rows and no ledger read."""
    return shell_build.page(
        when,
        tiles=shell_build.tiles_html(prod_html),
        d={"quotes": []},
        st={"pairs": {}},
        blob={"leads": {}, "pairs": {}},
    )


def main():
    """Copy the shell. Do not rebuild Running from data that is newer than the pages.

    A missing production page falls back to root_stub. The tracker build does
    not use that fallback: it writes index.html beside production.html. A
    failed write leaves the old file.
    """
    now = datetime.datetime.now(datetime.timezone.utc)
    prod_path = os.path.join(os.path.dirname(OUT), "production.html")
    if not os.path.isfile(prod_path):
        text = root_stub(now)
        write_atomic(OUT, text)
        print(f"wrote {OUT} ({fmt.display_updated(now)})")
        return
    with open(prod_path, encoding="utf-8") as fh:
        prod = fh.read()
    when = _clock_from_production(prod, now)
    index = ""
    if os.path.isfile(OUT):
        with open(OUT, encoding="utf-8") as fh:
            index = fh.read()
    prod_token = _stamp_token(prod)
    index_token = _stamp_token(index)
    if prod_token and index_token and prod_token == index_token:
        print(f"left {OUT} untouched ({fmt.display_updated(when)})")
        return
    text = _copy_from_tracker(index, prod)
    if text is None:
        text = _empty_shell(prod, when)
    write_atomic(OUT, text)
    print(f"wrote {OUT} ({fmt.display_updated(when)})")


if __name__ == "__main__":
    main()
