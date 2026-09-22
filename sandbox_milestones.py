#!/usr/bin/env python3
"""sandbox_milestones.py — tell the owner when a Sandbox record reaches a size worth deciding on.

Each watch names a pair, a start date, and a number of settled bets. When the pair's bets
logged since that date reach the number, the watch reports what they say — following the
pair, and backing the other side of the same bets — and, in GitHub Actions, opens an issue
that mentions the owner, which GitHub sends by email. A watch fires once: it looks for its own
issue first, open or closed, and says nothing if it is already there.

Run from the audit workflow. It reads the ledger and writes nothing to it.
Usage:  python3 sandbox_milestones.py [--dry-run]
"""
import json
import os
import subprocess
import sys

import sandbox_track as T

OWNER = "aliu2298"
WATCHES = [
    dict(key="nws-fade-10", source="nws", sport="climate", since="2026-09-21", settled=10,
         title="Sandbox: National Weather Service has 10 settled bets since the fade started",
         why="NWS was re-opened on 2026-09-21 to test whether backing the OTHER side of its "
             "calls is the right direction. Decide: follow, fade, or neither."),
]


def status(d, w):
    """(settled bets since the watch's date, a plain-text report of both directions)."""
    bets = [q for q in T.all_bets(d) if q["source"] == w["source"] and q["sport"] == w["sport"]
            and q.get("bet") and q["status"] in ("won", "lost") and q["logged"] >= w["since"]]
    n = len(bets)
    if not n:
        return 0, ""
    won = sum(1 for q in bets if q["status"] == "won")
    exp = sum(q["price"] for q in bets)
    follow = sum(T.pnl_after_fee(q) for q in bets) / (n * T.STAKE)
    f_rows = [(q["price_b"] if q["pick"] == "a" else q["price_a"], q["status"] == "lost", q) for q in bets
              if (q["price_b"] if q["pick"] == "a" else q["price_a"])]
    cost = sum(p + T.FEE_RATE.get(q.get("venue") or "polymarket", 0.07) * p * (1 - p) for p, _w, q in f_rows)
    fade = (sum(1 for _p, w_, _q in f_rows if w_) - cost) / cost if cost else None
    whole = T.faded(d, w["source"], w["sport"], venues=T.TRADEABLE_VENUES)
    a = T.assess(d, w["source"], w["sport"], venues=T.TRADEABLE_VENUES)
    lines = [
        f"Since {w['since']}: {n} settled.",
        f"  Following: {won} won against {exp:.1f} the prices implied, {follow * 100:+.1f}% after fees.",
        f"  Fading (the other side of the same bets): "
        + (f"{fade * 100:+.1f}% after fees." if fade is not None else "no opposite price to measure."),
        f"Whole record: following {a['won']}/{a['n']} ({(a.get('roi_fee') or 0) * 100:+.1f}% after fees, "
        f"z {a['z']:+.2f}); fading {(whole.get('roi') or 0) * 100:+.1f}% "
        f"({whole.get('outcomes', whole.get('n', 0))} independent outcomes, z {whole.get('z', 0):+.2f}).",
    ]
    return n, "\n".join(lines)


def already_raised(title):
    try:
        out = subprocess.run(["gh", "issue", "list", "--state", "all", "--search", f"in:title \"{title}\"",
                              "--json", "title"], capture_output=True, text=True, check=True).stdout
        return any(i.get("title") == title for i in json.loads(out or "[]"))
    except (OSError, subprocess.CalledProcessError, ValueError):
        return True          # cannot tell: stay quiet rather than raise the same issue twice


def main():
    dry = "--dry-run" in sys.argv or os.environ.get("GITHUB_ACTIONS") != "true"
    d = T.load()
    for w in WATCHES:
        n, report = status(d, w)
        print(f"[{w['key']}] {n}/{w['settled']} settled since {w['since']}")
        if n < w["settled"]:
            continue
        body = f"@{OWNER} {w['why']}\n\n```\n{report}\n```\n\nThe Sandbox page shows both directions in its \"If faded\" column."
        if dry:
            print("  would raise:", w["title"]); print(body)
            continue
        if already_raised(w["title"]):
            print("  already raised")
            continue
        subprocess.run(["gh", "issue", "create", "--title", w["title"], "--body", body], check=True)
        print("  raised")
    return 0


if __name__ == "__main__":
    sys.exit(main())
