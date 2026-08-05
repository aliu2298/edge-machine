#!/usr/bin/env python3
"""kalshi_watch.py — track Kalshi's earnings-call MENTION markets.

WHY THIS EXISTS / THE MISS IT CORRECTS
--------------------------------------
Twice (Aug 2 and Aug 5 2026) this project concluded "Kalshi has no company earnings-call
mention markets." That was WRONG. They exist as `KXEARNINGSMENTION<TICKER>` — 159 company
series — and they are filed under the category **"Mentions"**.

The scan missed them because it iterated a HARDCODED list of 10 category names. Kalshi has
**18**, and it files these by market TYPE ("Mentions"), not by subject ("Companies"). The
eight never scanned: Commodities, Crypto, Education, Elections, Entertainment, Exotics,
Mentions, Social, Transportation.

`/series` with **no category filter at all** returns all ~12,500 series in one request, so
guessing category names was never necessary. This module therefore enumerates instead of
assuming — the lesson generalises: never hand-write the key space when the API will list it.

WHAT THE MARKETS LOOK LIKE
--------------------------
Event   `KXEARNINGSMENTIONAMD-26AUG04`  "What will AMD say during their next earnings call?"
Strikes ~17 words/phrases per call ("China", "Agentic AI", "Oracle", "Export Restriction")
Rules   "If <phrase> is said by any <Company> representative (including the operator of the
         call) during the next earnings call (including the Q+A), resolves Yes."
Close   listed close_time is a LONG-STOP (Dec 31 / Jan 31); the real resolution is the call,
        with can_close_early=true — the same pattern as the metric quarterlies.

Usage:  python3 kalshi_watch.py [--quiet]
"""
import json, os, re, sys, time, datetime, urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(ROOT, "data", "kalshi_watch.json")
B = "https://api.elections.kalshi.com/trade-api/v2"
PREFIX = "KXEARNINGSMENTION"
MON = {m: i + 1 for i, m in enumerate(
    ["JAN","FEB","MAR","APR","MAY","JUN","JUL","AUG","SEP","OCT","NOV","DEC"])}


def call_date(event_ticker):
    """Call date from the event ticker (…-26AUG10). The listed close_time is a
    long-stop (Dec 31), so the ticker is the only reliable date source."""
    m = re.search(r"-(\d{2})([A-Z]{3})(\d{2})$", event_ticker or "")
    if not m:
        return None
    try:
        return datetime.date(2000 + int(m.group(1)), MON[m.group(2)],
                             int(m.group(3))).isoformat()
    except (KeyError, ValueError):
        return None
BAND = (0.75, 0.88)          # the clock-out entry band


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
        old = {}

    # enumerate, never guess: one unfiltered call returns every series
    try:
        rows = get(f"{B}/series").get("series") or []
    except Exception as e:
        note("warning", f"kalshi_watch: series listing failed: {e}")
        return 0                                  # never fail the pipeline over a watcher

    cats = sorted({(r.get("category") or "?") for r in rows})
    mention = sorted(r["ticker"] for r in rows
                     if (r.get("ticker") or "").startswith(PREFIX))
    if not quiet:
        print(f"kalshi_watch: {len(rows)} series across {len(cats)} categories; "
              f"{len(mention)} earnings-mention series")

    known = set(old.get("mention_series", []))
    new = [t for t in mention if t not in known]
    if known and new:
        note("warning", f"{len(new)} NEW earnings-mention companies listed: "
                        f"{', '.join(t.replace(PREFIX, '') for t in new[:12])}")

    # which of those currently have OPEN strikes, and how many sit in the entry band
    live, in_band = [], []
    for t in mention:
        try:
            ms = get(f"{B}/markets?series_ticker={t}&status=open&limit=60").get("markets") or []
        except Exception:
            continue
        if not ms:
            continue
        live.append(t)
        for m in ms:
            # Band on the BID, not last-traded. The strategy is maker-only — you join
            # the bid, so that is your actual entry. `last` goes stale: VST "Meta" showed
            # last 0.81 against a 0.71/0.72 book, which would have listed a market as
            # in-band when the real entry was 10c below it.
            try:
                lp = float(m.get("last_price_dollars"))
                bid = float(m.get("yes_bid_dollars"))
            except (TypeError, ValueError):
                continue
            if BAND[0] <= bid <= BAND[1]:
                try:
                    spread = round(float(m.get("yes_ask_dollars")) -
                                   float(m.get("yes_bid_dollars")), 4)
                except (TypeError, ValueError):
                    spread = None
                in_band.append({
                    "company": t.replace(PREFIX, ""),
                    "phrase": m.get("yes_sub_title"),
                    "last": lp,
                    "bid": m.get("yes_bid_dollars"),
                    "ask": m.get("yes_ask_dollars"),
                    "spread": spread,
                    "oi": m.get("open_interest_fp"),
                    "volume": m.get("volume_fp"),
                    "event_ticker": m.get("event_ticker"),
                    "call_date": call_date(m.get("event_ticker")),
                    "ticker": m.get("ticker"),
                    # listed close is a long-stop; the real resolution is the call itself
                    "close_time": m.get("close_time"),
                })
        time.sleep(0.25)

    if not quiet:
        print(f"  {len(live)} companies with open markets; "
              f"{len(in_band)} strikes in the {int(BAND[0]*100)}-{int(BAND[1]*100)}c band")
        for r in sorted(in_band, key=lambda x: -float(x["oi"] or 0))[:12]:
            print(f"    {r['company']:<7} {str(r['phrase'])[:26]:<26} {r['last']:.2f} "
                  f"(bid {r['bid']} / ask {r['ask']}, sp {r['spread']}) oi={r['oi']}")

    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    json.dump({"checked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
               "categories": cats,
               "mention_series": mention,
               "live_series": live,
               "in_band": in_band},
              open(STATE, "w"), indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
