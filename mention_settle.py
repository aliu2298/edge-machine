#!/usr/bin/env python3
"""mention_settle.py — score earnings-call mention picks, and measure calibration.

WHY CALIBRATION AND NOT JUST P&L
--------------------------------
These markets have a high base rate by construction — AMD's Aug 4 call had 16 of 17
phrases said. So a good win rate proves almost nothing: backing everything at 85c would
also "win" most of the time while losing money on the tail. What actually tells us whether
the phrase judgement is any good is whether OUR stated probability matches reality.

So every pick records `our_prob` BEFORE the call. This grades the pick, then reports:
  * P&L         — did the position make money at the price paid
  * Brier score — squared error of our probability vs the outcome, against the base rate
  * calibration — in each probability bucket, predicted vs actual

If our Brier beats "always predict the base rate", the judgement is adding something.
If it doesn't, we are decorating a coin flip and should stop.

Kalshi settles these itself, so grading reads their `result` field rather than us deciding.

Usage:  python3 mention_settle.py [--report]
"""
import json, os, sys, time, datetime, urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__))
PICKS = os.path.join(ROOT, "data", "mention_picks.json")
B = "https://api.elections.kalshi.com/trade-api/v2"


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


def load():
    try:
        return json.load(open(PICKS))
    except Exception:
        return {"picks": []}


def settle(blob):
    """Grade pending picks whose call has passed, using Kalshi's own resolution."""
    today = datetime.date.today()
    graded = 0
    for p in blob.get("picks", []):
        if p.get("status") != "pending":
            continue
        try:
            if datetime.date.fromisoformat(p.get("call_date", "")) > today:
                continue                      # call hasn't happened yet
        except ValueError:
            continue
        tick = p.get("market_ticker")
        if not tick:
            continue
        try:
            m = get(f"{B}/markets/{tick}").get("market", {})
        except Exception as e:
            note("warning", f"mention settle: {tick} lookup failed: {e}")
            continue
        res = (m.get("result") or "").lower()
        if res not in ("yes", "no"):
            continue                          # not settled yet; try again tomorrow

        side = (p.get("side") or "yes").lower()
        won = (res == side)
        entry = float(p.get("entry_price") or 0)
        stake = float(p.get("stake") or 1)
        # binary contract: win pays (1-entry) per unit staked, loss costs entry
        p["result"] = res
        p["won"] = won
        p["pl"] = round(stake * ((1 - entry) if won else -entry), 4)
        p["status"] = "settled"
        p["settled_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
        graded += 1
        print(f"  {p['company']:<7} {str(p['phrase'])[:24]:<24} {side.upper()} @{entry:.2f} "
              f"-> {res.upper()}  {'WIN' if won else 'LOSS'}  pl={p['pl']:+.4f}")
    return graded


def report(blob):
    done = [p for p in blob.get("picks", []) if p.get("status") == "settled"]
    if not done:
        print("  no settled mention picks yet")
        return
    n = len(done)
    wins = sum(1 for p in done if p.get("won"))
    pl = sum(float(p.get("pl") or 0) for p in done)
    staked = sum(float(p.get("stake") or 1) for p in done)
    print(f"\n=== mention picks: {n} settled ===")
    print(f"  record {wins}-{n-wins} ({100*wins/n:.0f}%) | P&L {pl:+.3f}u | "
          f"ROI {100*pl/staked:+.1f}%")

    # calibration — the part that says whether the judgement is real
    scored = [p for p in done if p.get("our_prob") is not None]
    if not scored:
        print("  (no our_prob recorded — cannot measure calibration)")
        return
    outs = [(float(p["our_prob"]), 1 if p.get("won") else 0) for p in scored]
    base = sum(o for _, o in outs) / len(outs)
    brier = sum((q - o) ** 2 for q, o in outs) / len(outs)
    bbase = sum((base - o) ** 2 for _, o in outs) / len(outs)
    skill = 1 - brier / bbase if bbase else 0
    print(f"  Brier {brier:.4f} vs base-rate {bbase:.4f} -> skill {skill:+.3f} "
          f"{'(judgement adding value)' if skill > 0 else '(NO skill — not beating the base rate)'}")
    print(f"  {'bucket':<12}{'n':>4}{'predicted':>11}{'actual':>9}")
    for lo, hi in ((0, .6), (.6, .75), (.75, .85), (.85, .95), (.95, 1.01)):
        sel = [(q, o) for q, o in outs if lo <= q < hi]
        if not sel:
            continue
        pm = sum(q for q, _ in sel) / len(sel)
        am = sum(o for _, o in sel) / len(sel)
        print(f"  {f'{lo:.2f}-{hi:.2f}':<12}{len(sel):>4}{100*pm:>10.0f}%{100*am:>8.0f}%")


def main():
    blob = load()
    if not blob.get("picks"):
        print("no mention picks recorded yet (data/mention_picks.json)")
        return 0
    if "--report" not in sys.argv:
        n = settle(blob)
        blob["updated_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
        json.dump(blob, open(PICKS, "w"), indent=1)
        pend = sum(1 for p in blob["picks"] if p.get("status") == "pending")
        print(f"settled {n}; {pend} still pending")
    report(blob)
    return 0


if __name__ == "__main__":
    sys.exit(main())
