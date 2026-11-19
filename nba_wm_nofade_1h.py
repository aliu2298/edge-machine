"""NBA win margin, NO fade in the FIRST HOUR only (2026-11-19, Olu). Sandbox PAPER; no live order, no config change.

Rule (docs/prereg_nba_wm_nofade_1h_2026-11-19.md, written before the first entry; from Fable's deep look, PR #495):
  entry   a post-only NO bid at 75% of the bucket's pregame NO price, live from the tip to 60 minutes after it, then cancelled.
          Every bucket, pregame NO price 10-95c, YES spread 5c or less, and the ask check (the version 4 entry check, as stamped
          on the NO fade ledger's rows). Side row: the same at 65%.
  exit    sell back at the pregame price on a print, else held to settlement. Maker fees in and out.
  paper   a sell also counts as filled at the touch when 10+ contracts trade AT the target after the entry (live sells do); the
          strict figures (a print strictly above) are shown beside it. Results are shown PER FILL and per game.
  record  fresh from FROM_NIGHT, no backfill. Read once at 30 fills. Retire at or under zero then, or if fills stay under one a
          night for 30 nights.
It is a FILTER on nba_wm_nofade.py's replay: that ledger already records every bucket's 75% / 85% / 65% fill with its fill time.
Compared with: the same nights' all-fills 65% (the version 4 full-game bid) and all-fills 75%, and a blind row (a random bucket of the
same game within 3c of the fill's NO price, bought at the pregame price and held).
"""
import collections
import hashlib
import math
import random
import statistics

import chaos_replay as C
import fillsim as F
import nba_wm_nofade as N

LANE = "nba_wm_nofade_1h"
LABEL = "Win margin · NO fade, first hour only"
FROM_NIGHT = "2026-11-19"                  # the first slate after the merge
WINDOW_S = 3600
HEAD, SIDE = N.vkey(0.75), N.vkey(0.65)
READ_AT = 30
MIN_PER_NIGHT, NIGHTS_TO_JUDGE = 1.0, 30
BLIND_BAND = 0.03
EPS = 1e-9
WATCH_ABOVE, WATCH_NIGHTS = 0.30, 7
WATCH_BAND = (0.10, 0.20)
mean = statistics.mean


def _entries(state):
    return [e for e in state["entries"] if e["night"] >= FROM_NIGHT and e.get("version") == N.VERSION]


def _first_hour(e, f):
    return f is not None and f["fill_at"] - e["tip"] <= WINDOW_S + EPS


def fills(state, key, first_hour=True):
    """[(entry, bucket row, fill)] on the fresh record: ask check passed; with `first_hour`, filled within an hour of the tip."""
    out = []
    for e in _entries(state):
        for r in e["buckets"]:
            f = (r.get("fills") or {}).get(key)
            if f and r["ask"]["status"] == "verified" and (not first_hour or _first_hour(e, f)):
                out.append((e, r, f))
    return out


def profit_of(f, touch=True):
    return f.get("profit_touch", f["profit"]) if touch else f["profit"]


def stats(items, touch=True):
    """Per fill and per game on [(entry, row, fill)]: fills, sold, per-fill return after fees, games, per-game return, z by night, nights."""
    if not items:
        return dict(fills=0, sold=0, roi_fill=None, games=0, roi_game=None, z=None, nights=0, win_nights=0, top_night=None)
    cost = sum(f["cost"] for _e, _r, f in items)
    prof = sum(profit_of(f, touch) for _e, _r, f in items)
    sold = sum(1 for _e, _r, f in items if (f.get("sold_touch_at") if touch else f["sold_at"]))
    g = collections.defaultdict(lambda: [0.0, 0.0, None])
    for e, _r, f in items:
        x = g[e["event"]]
        x[0] += f["cost"]
        x[1] += profit_of(f, touch)
        x[2] = e["night"]
    rows = [dict(event=k, night=v[2], roi=v[1] / v[0], profit=v[1], cost=v[0], won=v[1] > 0) for k, v in g.items()]
    nm = collections.defaultdict(list)
    for r in rows:
        nm[r["night"]].append(r["roi"])
    night_means = [mean(v) for v in nm.values()]
    z = None
    if len(night_means) >= 3 and statistics.stdev(night_means) > 0:
        z = mean(night_means) / (statistics.stdev(night_means) / math.sqrt(len(night_means)))
    by_night = collections.defaultdict(float)
    for e, _r, f in items:
        by_night[e["night"]] += profit_of(f, touch)
    top = max(by_night.values()) / prof if prof > 0 and by_night else None
    return dict(fills=len(items), sold=sold, roi_fill=prof / cost, games=len(rows), roi_game=mean([r["roi"] for r in rows]), z=z, nights=len(nm),
                win_nights=sum(1 for v in nm.values() if mean(v) > 0), top_night=top)


def blind_items(state, picks):
    """One blind bucket per pick: a random verified bucket of the same game within 3c of the pick's pregame NO price, not a bucket the
    75% bid filled in the first hour, bought at the pregame NO price (a taker buy) and held to settlement. Returns [(entry, row, fill)]."""
    out = []
    for e, r, _f in picks:
        taken = {x["id"] for x in e["buckets"] if _first_hour(e, (x.get("fills") or {}).get(HEAD)) and x["ask"]["status"] == "verified"}
        pool = [x for x in e["buckets"] if x["ask"]["status"] == "verified" and x["id"] not in taken]
        near = [x for x in pool if abs(x["P"] - r["P"]) <= BLIND_BAND + EPS] or (
            [x for x in pool if abs(x["P"] - r["P"]) <= min(abs(y["P"] - r["P"]) for y in pool) + EPS] if pool else [])
        if not near:
            continue
        seed = int(hashlib.sha256(f"{LANE}:{r['id']}".encode()).hexdigest()[:12], 16)
        b = random.Random(seed).choice(sorted(near, key=lambda x: x["id"]))
        cost = b["P"] + F.fee(b["P"])
        prof = (1.0 if b["no_wins"] else 0.0) - cost
        out.append((e, b, dict(cost=cost, profit=prof, sold_at=None, sold_touch_at=None)))
    return out


def board(state):
    """The record of the lane and its comparisons, all on the fresh record."""
    head, side = fills(state, HEAD), fills(state, SIDE)
    nights = sorted({e["night"] for e in _entries(state)})
    allsets = {}
    for key in (HEAD, SIDE):
        allsets[key] = fills(state, key, first_hour=False)
    return dict(head=stats(head), side=stats(side), head_strict=stats(head, touch=False), all75=stats(allsets[HEAD]), all65=stats(allsets[SIDE]),
                blind=stats(blind_items(state, head), touch=False), games=len(_entries(state)), nights=len(nights), night_list=nights)


def read_text(b):
    n = b["head"]["fills"]
    nights = b["nights"]
    s = b["head"]
    if n >= READ_AT:
        if s["roi_fill"] is None or s["roi_fill"] <= 0:
            return f"read at {READ_AT} fills: retire (at or under zero after fees)"
        beats = b["all75"]["roi_fill"] is not None and s["roi_fill"] > b["all75"]["roi_fill"]
        ok = (s["z"] or 0) >= 2 and beats and (s["top_night"] is None or s["top_night"] < 0.5)
        return "read at 30 fills: candidate to promote (above zero, z 2+, above the all-fills version, not one night)" if ok else "read at 30 fills: stays paper"
    if nights >= NIGHTS_TO_JUDGE and n < MIN_PER_NIGHT * nights:
        return f"retire: {n} fills in {nights} nights (under one a night)"
    return f"too early ({n} of {READ_AT} fills, {nights} night{'s' if nights != 1 else ''}; read once at {READ_AT})"


# ---------------------------------------------------------------- the YES watch line
def watch(tracker, today=None):
    """Share of 10-20c buckets whose price doubled in the first hour after the tip, by night, from the tracker rows (m.first2 = minutes
    from the tip to the first print at 2x the ask). Returns dict(nights=[(night, n, share)], week=share or None, flag=bool)."""
    by = collections.defaultdict(lambda: [0, 0])
    for r in tracker.get("rows") or []:
        m = r.get("m")
        if not m or not r.get("eligible", True) or not WATCH_BAND[0] - EPS <= r.get("ask", 0) <= WATCH_BAND[1] + EPS:
            continue
        by[r["night"]][0] += 1
        if m.get("first2") is not None and m["first2"] <= WINDOW_S / 60:
            by[r["night"]][1] += 1
    nights = [(k, v[0], v[1] / v[0]) for k, v in sorted(by.items()) if v[0]]
    last = nights[-WATCH_NIGHTS:]
    tot = sum(n for _k, n, _s in last)
    week = sum(s * n for _k, n, s in last) / tot if tot and len(last) >= WATCH_NIGHTS else None
    return dict(nights=nights, week=week, flag=week is not None and week > WATCH_ABOVE)
