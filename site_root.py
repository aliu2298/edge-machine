#!/usr/bin/env python3
"""site_root.py — write public_site/index.html: the site root.

The root forwards visitors to the Sandbox. Its visible time is Central Time.
It must NOT contain the tracker stamp "updated YYYY-MM-DD HH:MM UTC": that form
lives on sandbox.html and production.html, and a freshness check pointed at
this stub fails closed on purpose. backup-refresh.yml reads those two pages.

Usage:  python3 site_root.py
"""
import datetime
import os

import fmt
import site_chrome

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


def root_stub(now):
    """The site root: forwards to the Sandbox. Not the watchdog's freshness stamp."""
    when = _as_utc(now)
    if when is None:
        # Unparseable caller text. Show it, and do not invent the tracker form.
        stamp_html = site_chrome.esc(str(now))
    else:
        stamp_html = site_chrome.stamp(when, machine=False)
    visible = fmt.display_updated(when) if when is not None else str(now)
    body = f"""<h1>Edge Machine</h1>
<p class="lede">{site_chrome.esc(visible)}</p>
<p><a href="./sandbox.html">Continue to the Sandbox</a></p>
"""
    return site_chrome.document(
        "Edge Machine",
        "Which rules and tipsters are making money, and which are failing.",
        "sandbox",
        (("content", "Sandbox"),),
        stamp_html,
        body,
        script_src="./root.js",
        extra_head='<meta http-equiv="refresh" content="0; url=./sandbox.html">',
    )


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


def main():
    now = datetime.datetime.now(datetime.timezone.utc)
    write_atomic(OUT, root_stub(now))
    print(f"wrote {OUT} ({fmt.display_updated(now)})")


if __name__ == "__main__":
    main()
