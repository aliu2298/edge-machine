"""Production feed build gap (2026-11-02): data/feed_gap.json says whether data/production_leads.json went more than
GAP_HOURS without a build in the last 24 hours. The commits that touch the file are the builds (the Sandbox
Tracker commits it each time it runs); GitHub's cron skips runs, so a gap is real and silent: on Nov 1 the 25 hours
around it showed hourly builds, but a stretch like that is exactly what nobody would see until a lead was missed.

Status only, no amounts: {"checked": ISO, "status": "green"|"amber", "gap_hours": float, "gap_from": ISO, "gap_to": ISO}.
The twice-daily health check reads it for its Production feed line; the feeds heartbeat writes it and prints a
::warning:: annotation. Read-only on GitHub (the public commits API).
"""
import datetime as dt
import json
import os
import sys
import urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(ROOT, "data", "feed_gap.json")
FEED = "data/production_leads.json"
REPO = "aliu2298/edge-machine"
GAP_HOURS = 2.0
WINDOW_HOURS = 24


def gaps(times, now, window=WINDOW_HOURS):
    """[(from, to, hours)] between consecutive builds inside the window, the stretch since the last build to `now`
    included. `times` are build instants in any order."""
    lo = now - dt.timedelta(hours=window)
    ts = sorted(t for t in times if t >= lo)
    edges = [lo] + ts + [now] if ts else [lo, now]
    return [(a, b, (b - a).total_seconds() / 3600) for a, b in zip(edges, edges[1:])]


def status(times, now, gap_hours=GAP_HOURS):
    worst = max(gaps(times, now), key=lambda g: g[2])
    return dict(checked=now.replace(microsecond=0).isoformat(), status="amber" if worst[2] > gap_hours else "green",
                gap_hours=round(worst[2], 1), gap_from=worst[0].replace(microsecond=0).isoformat(),
                gap_to=worst[1].replace(microsecond=0).isoformat())


def fetch_builds(now, opener=urllib.request.urlopen):
    since = (now - dt.timedelta(hours=WINDOW_HOURS + 2)).strftime("%Y-%m-%dT%H:%M:%SZ")
    out, page = [], 1
    while page <= 5:
        url = f"https://api.github.com/repos/{REPO}/commits?path={FEED}&since={since}&per_page=100&page={page}"
        req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json",
                                                    **({"Authorization": "Bearer " + os.environ["GH_AUTH"]} if os.environ.get("GH_AUTH") else {})})
        with opener(req, timeout=30) as r:
            rows = json.load(r)
        out += [dt.datetime.fromisoformat(x["commit"]["committer"]["date"].replace("Z", "+00:00")) for x in rows]
        if len(rows) < 100:
            break
        page += 1
    return out


def main():
    now = dt.datetime.now(dt.timezone.utc)
    try:
        times = fetch_builds(now)
    except Exception as e:                                      # noqa: BLE001  a failed read says nothing about the feed
        print(f"::notice title=Feed gap check skipped::{type(e).__name__}")
        return 0
    s = status(times, now)
    os.makedirs(os.path.dirname(PATH), exist_ok=True)
    with open(PATH, "w") as f:
        json.dump(s, f, indent=1)
    if s["status"] == "amber":
        print(f"::warning title=Production feed build gap::{s['gap_hours']}h without a build ({s['gap_from']} to {s['gap_to']})")
    print("feed gap:", s)
    return 0


if __name__ == "__main__":
    sys.exit(main())
