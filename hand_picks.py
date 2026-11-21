"""Hand picks · learning log (2026-11-21): the running record of picks placed by hand, shown on the Combo page.

data/hand_picks.json is written by pull request: {"picks": [{id, placed_at, kind (combo|single), legs: [{ticker, label, side (yes|no), ask, bid}],
combo_price, payout_multiple, counted (true | false for context picks), result (won|lost|open|no_result)}]}.
This module settles each open pick from Kalshi's market results, leg by leg: a combo wins only if every leg wins, and a void or part-value
leg is multiplied in at its settled value. Counted picks feed the record; context picks are listed and not counted. Public reads only.
"""
import json
import os
import urllib.parse

import daily_track as D

PATH = os.path.join(D.ROOT, "data", "hand_picks.json")
TARGET = 10                       # counted picks the log is built for
MARKETS = (("1Q", "1Q totals"), ("1H", "1H totals"), ("PRA", "Player PRA"))   # the market types a counted leg can be


def market_of(leg):
    """A leg's market type: its own "market" field (1Q / 1H / PRA), else read from the ticker or label; None if it cannot be told."""
    m = str(leg.get("market") or "").upper()
    if m in dict(MARKETS):
        return m
    t = (str(leg.get("ticker") or "") + " " + str(leg.get("label") or "")).upper()
    if "PRA" in t or "POINTS+REB" in t.replace(" ", ""):
        return "PRA"
    if "1H" in t or "FIRST HALF" in t or "1ST HALF" in t:
        return "1H"
    if "1Q" in t or "FIRST QUARTER" in t or "1ST QUARTER" in t:
        return "1Q"
    return None


def is_counted(p):
    """Counted picks are 2-leg combos only; anything else (a single, a 3-leg test) is context and never enters a stat."""
    return bool(p.get("counted")) and p.get("kind") == "combo" and len(p.get("legs") or []) == 2


def load(path=PATH):
    try:
        with open(path) as f:
            d = json.load(f)
    except (OSError, ValueError):
        return {"picks": []}
    d.setdefault("picks", [])
    return d


def leg_value(leg, fetch=D.get):
    """The bought side's settled value (yes: the yes payout, no: 1 - it), or None while the market is not final."""
    t = leg["ticker"]
    m = fetch("markets/" + urllib.parse.quote(t, safe="")).get("market", {})
    if m.get("ticker") != t:
        raise ValueError("settlement ticker mismatch " + t)
    yes = D.payout(m)
    if yes is None:
        return None
    return round(yes if leg.get("side") == "yes" else 1 - yes, 6)


def settle(state, fetch=D.get):
    """Settle every open pick whose legs are all final. Returns the errors; a leg that cannot be read leaves its pick open."""
    errors = []
    for p in state["picks"]:
        if p.get("result") not in (None, "open"):
            continue
        try:
            vals = [leg_value(leg, fetch) for leg in p.get("legs") or []]
        except Exception as e:                                  # noqa: BLE001
            errors.append(f"{p.get('id')}: {str(e)[:80]}")
            continue
        for leg, v in zip(p.get("legs") or [], vals):
            if v is not None:
                leg["value"] = v
        if not vals or any(v is None for v in vals):
            continue
        value = 1.0
        for v in vals:
            value *= v
        p["value"] = round(value, 6)
        p["result"] = "won" if value == 1 else "lost" if value == 0 else "no_result"
    return errors


def cost_of(p):
    c = p.get("combo_price")
    if c is None and p.get("legs"):
        c = p["legs"][0].get("ask")
    return c


def record(state):
    """Counted picks only: n, landed, lost, open, land rate, average payout multiple, return per pick."""
    counted = [p for p in state["picks"] if is_counted(p)]
    done = [p for p in counted if p.get("result") in ("won", "lost", "no_result")]
    out = dict(n=len(counted), target=TARGET, landed=sum(p["result"] == "won" for p in done), lost=sum(p["result"] == "lost" for p in done),
               open=sum(p.get("result") in (None, "open") for p in counted), context=sum(not is_counted(p) for p in state["picks"]))
    out["settled"] = len(done)
    out["land_rate"] = out["landed"] / len(done) if done else None
    mult = [p["payout_multiple"] for p in counted if p.get("payout_multiple") is not None]
    out["avg_multiple"] = sum(mult) / len(mult) if mult else None
    rois = [p["value"] / cost_of(p) - 1 for p in done if cost_of(p) and p.get("value") is not None]
    out["return"] = sum(rois) / len(rois) if rois else None
    split = {}
    for key, name in MARKETS:
        vals = [leg.get("value") for p in counted for leg in p["legs"] if market_of(leg) == key]
        fin = [v for v in vals if v is not None]
        split[key] = dict(name=name, legs=len(vals), won=sum(v == 1 for v in fin), lost=sum(v == 0 for v in fin), open=len(vals) - len(fin),
                          rate=(sum(v == 1 for v in fin) / len(fin)) if fin else None)
    out["by_market"] = split
    return out


def main():
    state = load()
    errors = settle(state)
    tmp = PATH + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f, indent=2, sort_keys=True, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp, PATH)
    print("hand picks", len(state["picks"]), "errors", errors)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
