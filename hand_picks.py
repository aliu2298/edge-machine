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
    counted = [p for p in state["picks"] if p.get("counted")]
    done = [p for p in counted if p.get("result") in ("won", "lost", "no_result")]
    out = dict(n=len(counted), target=TARGET, landed=sum(p["result"] == "won" for p in done), lost=sum(p["result"] == "lost" for p in done),
               open=sum(p.get("result") in (None, "open") for p in counted), context=sum(not p.get("counted") for p in state["picks"]))
    out["settled"] = len(done)
    out["land_rate"] = out["landed"] / len(done) if done else None
    mult = [p["payout_multiple"] for p in counted if p.get("payout_multiple") is not None]
    out["avg_multiple"] = sum(mult) / len(mult) if mult else None
    rois = [p["value"] / cost_of(p) - 1 for p in done if cost_of(p) and p.get("value") is not None]
    out["return"] = sum(rois) / len(rois) if rois else None
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
