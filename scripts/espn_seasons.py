#!/usr/bin/env python3
# espn_seasons.py — five seasons of completed matches into data/espn_seasons.json.
#
# The Sandbox's own ESPN cache holds about six months a league, which is enough to count a
# team's last ten games and nothing else. Anything needing a long baseline — how often two
# clubs have met, whether a pairing scores, whether a selection rule beats the teams' own
# long-run rate rather than a six-month slice of it — needs seasons. On two years, 83.5% of
# matches had no prior meeting at all to read against; on five, a third have five or more.
#
# SCORES ONLY. There are no odds in this file, so nothing measured on it can be judged
# against a price: it says what happened, never what it was worth. Every rule the Sandbox
# runs still has to face a real ask.
#
# Re-runnable and idempotent: it rewrites the file from ESPN each time, a month per request,
# and a month that hits the 100-event cap is re-read day by day so a busy month is never
# silently truncated (the same trap streaks_fetch.py documents).
#
# Usage:  python3 scripts/espn_seasons.py
import datetime
import json
import os
import time
import urllib.error
import urllib.request

HOST = "https://site.web.api.espn.com"
UA = {"User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                     "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")}
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "espn_seasons.json")

# The competitions the Sandbox actually prices, plus the two European cups, which is what
# gives cross-league pairs any meeting history at all.
SLUGS = ["eng.1", "esp.1", "ita.1", "ger.1", "fra.1", "ned.1", "por.1", "sco.1", "usa.1",
         "eng.2", "mex.1", "bra.1", "uefa.champions", "uefa.europa", "tur.1", "bel.1"]
START = datetime.date(2021, 7, 1)
MONTH_CAP = 100
NOTE = ("Five seasons of completed matches from ESPN's scoreboard, one row per match: "
        "[competition, date, home, away, home goals, away goals]. Scores only — no odds, so "
        "nothing here can be judged against a price. Rebuilt by scripts/espn_seasons.py.")


def load(path=OUT):
    """[{comp, date, home, away, hs, a_s, tot}] — the file as rows, oldest first."""
    with open(path) as f:
        blob = json.load(f)
    return [dict(comp=c, date=d, home=h, away=a, hs=hs, a_s=a_s, tot=hs + a_s)
            for c, d, h, a, hs, a_s in blob["rows"]]


def get(url, tries=3):
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as f:
                return json.load(f)
        except (urllib.error.HTTPError, urllib.error.URLError, OSError, ValueError):
            if i == tries - 1:
                return {}
            time.sleep(1.5 * (i + 1))
    return {}


def months(a, b):
    m = a.replace(day=1)
    while m <= b:
        yield m
        m = (m.replace(day=28) + datetime.timedelta(days=4)).replace(day=1)


def trim(ev, slug):
    """One finished match, or None. A match still in play has no final score to keep."""
    try:
        c = ev["competitions"][0]
        if "FULL_TIME" not in c["status"]["type"]["name"]:
            return None
        cs = c["competitors"]
        h = next(x for x in cs if x["homeAway"] == "home")
        a = next(x for x in cs if x["homeAway"] == "away")
        return dict(comp=slug, date=ev["date"], id=ev["id"],
                    home=h["team"]["displayName"], away=a["team"]["displayName"],
                    hs=int(h["score"]), a_s=int(a["score"]))
    except (KeyError, IndexError, StopIteration, ValueError, TypeError):
        return None


def main():
    end = datetime.date.today()
    out, seen = [], set()
    base = HOST + "/apis/site/v2/sports/soccer/{}/scoreboard?dates={}"
    for slug in SLUGS:
        n0 = len(out)
        for m in months(START, end):
            data = get(base.format(slug, m.strftime("%Y%m")))
            evs = data.get("events", [])
            if len(evs) >= MONTH_CAP:
                evs = []
                day = m
                nxt = (m.replace(day=28) + datetime.timedelta(days=4)).replace(day=1)
                while day < nxt and day <= end:
                    evs += get(base.format(slug, day.strftime("%Y%m%d"))).get("events", [])
                    day += datetime.timedelta(days=1)
                    time.sleep(0.12)
            for ev in evs:
                r = trim(ev, slug)
                if r and r["id"] not in seen:
                    seen.add(r["id"])
                    out.append(r)
            time.sleep(0.12)
        print(f"{slug:<18}{len(out) - n0:>6} matches", flush=True)
    out.sort(key=lambda r: r["date"])
    blob = dict(note=NOTE, fetched=end.isoformat(), first=out[0]["date"][:10],
                last=out[-1]["date"][:10], matches=len(out),
                competitions=sorted(set(r["comp"] for r in out)),
                rows=[[r["comp"], r["date"][:10], r["home"], r["away"], r["hs"], r["a_s"]]
                      for r in out])
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as f:
        json.dump(blob, f, separators=(",", ":"))
    print(f"total {len(out)} matches, {blob['first']} -> {blob['last']}")


if __name__ == "__main__":
    main()
