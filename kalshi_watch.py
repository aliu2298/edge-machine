#!/usr/bin/env python3
"""kalshi_watch.py — watch for Kalshi listing NEW market types we want but don't have yet.

Currently watching for: **company earnings-call MENTION markets** ("what will they say on
the call"). As of 2026-08-05 these DO NOT EXIST — a scan of 8,055 series across every
category found say/mention products only in Politics and Sports:

    KXSBMENTION       annual   "What will the commentators say during the Big Game?"
    KXVANCEINGRAHAM   one_off  "What will J.D. Vance say on Ingraham Angle tonight?"
    KXWHBRIEFING      custom   WH briefing room people mentioned

All are hand-built one-offs around a single broadcast, not a systematic product line, and
all currently carry zero active markets. So the earnings board cannot be switched to
call-mention content today; there is nothing to point it at.

Rather than re-running that scan by hand every few weeks, this records the set of company
series and reports anything new that looks verbal (mention/say/word/phrase). Run it from
the daily workflow: the day Kalshi lists one, it says so.

Usage:  python3 kalshi_watch.py [--quiet]
"""
import json, os, re, sys, time, urllib.request, urllib.parse

ROOT = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(ROOT, "data", "kalshi_watch.json")
B = "https://api.elections.kalshi.com/trade-api/v2"

# categories where a company earnings-call market would plausibly be filed
CATEGORIES = ["Companies", "Financials"]
# Tokens suggesting a market resolves on WORDS SPOKEN rather than a reported number.
# Word-bounded on purpose: a bare "CALL" matched "MicroStrategy margijn called" (a MARGIN
# call — a collateral event, nothing verbal), and "GUIDANCE" matches ordinary financial
# forecast markets. Both produced false alarms, which is how a watcher gets ignored.
VERBAL_RE = re.compile(
    r"\b(MENTIONS?|MENTIONED|SAYS?|SAID|WORDS?|PHRASES?|SPEAKS?|SPOKEN|UTTERS?|"
    r"EARNINGS[- ]CALL|CONFERENCE[- ]CALL)\b")
# already known and explicitly not what we want (politics/sports one-offs)
KNOWN_NON_COMPANY = {"KXSBMENTION", "KXVANCEINGRAHAM", "KXWHBRIEFING", "KXWHBRIEFINGEY",
                     "KXNWSAYLOR", "KXPRESTALK", "KXINAUGSPEAK", "KXSPEAKER",
                     "KXSPEAKERVOTE", "KXSOTHLEAVE", "KXELONDJTSAY", "KXELONMJ",
                     "KXWORDNYTTARIFF", "KXSTATEMENTCOUNTSWIFTTRUMP",
                     "KXMSTRMARGIN"}   # "margijn called" = margin call, not speech


def note(level, msg):
    print(f"::{level}::{msg}" if os.environ.get("GITHUB_ACTIONS") else f"  [{level.upper()}] {msg}")


def get(url, tries=3):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "edge-machine/1.0"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except Exception:
            if i == tries - 1:
                raise
            time.sleep(1.5 * (i + 1))
    return {}


def main():
    quiet = "--quiet" in sys.argv
    try:
        old = json.load(open(STATE))
    except Exception:
        old = {"series": [], "verbal": []}
    seen = set(old.get("series", []))

    current, verbal = set(), []
    for cat in CATEGORIES:
        try:
            rows = get(f"{B}/series?category={urllib.parse.quote(cat)}").get("series") or []
        except Exception as e:
            note("warning", f"kalshi_watch: {cat} lookup failed: {e}")
            return 0                     # never fail the pipeline over a watcher
        for s in rows:
            t = (s.get("ticker") or "").upper()
            current.add(t)
            blob = f"{t} {(s.get('title') or '').upper()}"
            if t not in KNOWN_NON_COMPANY and VERBAL_RE.search(blob):
                verbal.append((t, s.get("title")))
        time.sleep(0.3)

    new_series = sorted(current - seen) if seen else []
    prev_verbal = set(old.get("verbal", []))
    new_verbal = [(t, ti) for t, ti in verbal if t not in prev_verbal]

    if not quiet:
        print(f"kalshi_watch: {len(current)} company/financial series "
              f"({len(new_series)} new since last run)")

    for t, ti in new_verbal:
        note("warning", f"NEW verbal-style market listed: {t} — \"{ti}\". "
                        f"If this resolves on what a company SAYS on its earnings call, "
                        f"the call-mention lane just became buildable.")
    if verbal and not new_verbal and not quiet:
        print(f"  {len(verbal)} verbal-ish series already known, none new")
    if not verbal and not quiet:
        print("  no company earnings-call mention markets exist yet (expected)")

    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    json.dump({"checked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
               "series": sorted(current),
               "verbal": sorted({t for t, _ in verbal})}, open(STATE, "w"), indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
