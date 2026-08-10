#!/usr/bin/env python3
"""kalshi_settle.py — grade the metric-quarterly pick cards from Kalshi's own resolution.

THE GAP THIS CLOSES
-------------------
Quarterly picks are stored in predictions.db with market `kalshi_yes`, and app.py's
grade() returns None for that market — by design, since a soccer scoreline cannot settle
an earnings threshold. The intent was "settle manually". In practice nobody did: all 7
picks sat pending 3-6 days after their calls had already resolved on Kalshi. The board
showed an untouched queue while every market behind it was finalised.

Kalshi resolves these itself, so grading is a lookup, not a judgement:
  ext_link  -> event ticker (e.g. KXLYFT-26AUGRIDES)
  pick text -> the strike we backed ("above 251M rides @ 85c")
  match the strike against each market's floor_strike, read its `result`.

Strike matching is exact on floor_strike after unit expansion (k/M/B, $ and commas
stripped). If no market matches within a tight tolerance the pick is LEFT PENDING rather
than graded against a neighbouring strike — settling one rung off would be worse than not
settling at all.

Usage:  python3 kalshi_settle.py [--dry-run]
"""
import json, os, re, sqlite3, sys, time, datetime, urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(ROOT, "predictions.db")
MIRROR = os.path.join(ROOT, "data", "predictions.json")
B = "https://api.elections.kalshi.com/trade-api/v2"
UNITS = {"k": 1e3, "m": 1e6, "b": 1e9}


def note(level, msg):
    print(f"::{level}::{msg}" if os.environ.get("GITHUB_ACTIONS") else f"  [{level.upper()}] {msg}")


def get(url, tries=3):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "edge-machine/1.0"})
            with urllib.request.urlopen(req, timeout=25) as r:
                return json.load(r)
        except Exception:
            if i == tries - 1:
                raise
            time.sleep(1.5 * (i + 1))
    return {}


def strike_of(pick_text):
    """Numeric strike from a pick like 'YES — above 178k locations @ 77c'.

    Deliberately anchored on 'above' so the trailing '@ 85c' price can never be mistaken
    for the strike — that ambiguity is exactly how a pick would settle against the wrong
    rung of the ladder.
    """
    m = re.search(r"above\s*\$?\s*([\d,]+(?:\.\d+)?)\s*([kmb])?", (pick_text or "").lower())
    if not m:
        return None
    val = float(m.group(1).replace(",", ""))
    return val * UNITS.get(m.group(2) or "", 1)


def event_markets(event_ticker):
    for st in ("settled", "finalized", "closed"):
        try:
            ms = get(f"{B}/markets?event_ticker={event_ticker}&status={st}&limit=60").get("markets") or []
        except Exception:
            ms = []
        if ms:
            return ms
    return []


def main():
    dry = "--dry-run" in sys.argv
    if not os.path.exists(DB):
        print("no predictions.db (CI has only the mirror) — kalshi settling runs locally")
        return 0
    c = sqlite3.connect(DB); c.row_factory = sqlite3.Row
    rows = c.execute("SELECT * FROM predictions WHERE sport='kalshi' AND status='pending'").fetchall()
    print(f"{len(rows)} pending quarterly picks")
    graded = 0

    for r in rows:
        ev = (r["ext_link"] or "").rsplit("/", 1)[-1]
        want = strike_of(r["pick"])
        if not ev or want is None:
            note("warning", f"#{r['id']} {r['match']}: no event ticker or unparseable strike "
                            f"({r['pick']!r}) — left pending")
            continue
        ms = event_markets(ev)
        if not ms:
            print(f"  #{r['id']} {r['match'][:34]:<34} not resolved on Kalshi yet")
            continue
        hit = None
        for m in ms:
            fs = m.get("floor_strike")
            try:
                if fs is not None and abs(float(fs) - want) <= max(1.0, want * 1e-6):
                    hit = m
                    break
            except (TypeError, ValueError):
                continue
        if hit is None:
            strikes = ", ".join(str(m.get("floor_strike")) for m in ms[:6])
            note("warning", f"#{r['id']} {r['match']}: strike {want:,.0f} matched no market "
                            f"(ladder: {strikes}) — LEFT PENDING rather than settled a rung off")
            continue
        res = (hit.get("result") or "").lower()
        if res not in ("yes", "no"):
            print(f"  #{r['id']} {r['match'][:34]:<34} market found, not yet resolved")
            continue

        sel = (r["selection"] or "yes").lower()
        won = (res == sel)
        status = "win" if won else "loss"
        pl = (r["stake"] or 0) * ((r["odds"] or 1) - 1) if won else -(r["stake"] or 0)
        print(f"  #{r['id']} {r['match'][:34]:<34} strike {want:,.0f} -> {res.upper():<3} "
              f"{status.upper():<4} pl={pl:+.2f}")
        graded += 1
        if not dry:
            c.execute("UPDATE predictions SET status=?, result_note=?, settled_at=? WHERE id=?",
                      (status, f"{hit.get('yes_sub_title')} -> {res}",
                       datetime.datetime.now().isoformat(timespec="seconds"), r["id"]))
        time.sleep(0.25)

    if not dry:
        c.commit()
    c.close()
    print(f"\n{'would grade' if dry else 'graded'} {graded}; "
          f"{len(rows)-graded} still pending")
    return 0


if __name__ == "__main__":
    sys.exit(main())
