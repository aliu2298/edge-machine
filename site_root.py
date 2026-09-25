#!/usr/bin/env python3
"""site_root.py — write public_site/index.html: the site root.

The root forwards visitors to the Sandbox and carries this run's "updated ... UTC" stamp.
That stamp is NOT what the backup watchdog reads: site_root.py rewrites this stub on
every refresh, so it stays new even when the tracker is dead. backup-refresh.yml reads
the tracker's stamp on sandbox.html and production.html instead. The root format stays
"updated Mon DD YYYY · HH:MM UTC" so a check pointed at it on purpose fails closed.

Usage:  python3 site_root.py
"""
import datetime
import os

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "public_site", "index.html")


def root_stub(now):
    """The site root: forwards to the Sandbox. Not the watchdog's freshness stamp."""
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Edge Machine</title>
<meta http-equiv="refresh" content="0; url=./sandbox.html">
<style>body{{background:#0a0d14;color:#8b94a7;font:14px system-ui,sans-serif;padding:28px}}a{{color:#7aa2f7}}</style>
</head><body><p>Edge Machine · updated {now} — <a href="./sandbox.html">Sandbox</a> ·
<a href="./production.html">Production</a></p>
<script>location.replace("./sandbox.html")</script></body></html>"""


def main():
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%b %d %Y · %H:%M UTC")
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as f:
        f.write(root_stub(now))
    print(f"wrote {OUT} (updated {now})")


if __name__ == "__main__":
    main()
