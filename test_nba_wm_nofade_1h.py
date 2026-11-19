"""The first-hour NO fade lane: the touch sell rule, the first-hour filter, no backfill, per-fill v per-game, blind row, read rules, the watch line, page copy."""
import collections
import re
import sys

import nba_wm_nofade as N
import nba_wm_nofade_1h as H
import nba_wm_nofade_build as B
import sandbox_audit

FAILED = []


def check(label, got, want):
    ok = got == want
    print(("  ok   " if ok else "  FAIL ") + label + ("" if ok else f" — got {got!r}, want {want!r}"))
    if not ok:
        FAILED.append(label)


TIP = 1_800_000_000
P = 0.40
print("the touch sell rule")
pr = [(TIP + 60, 0.28, 20), (TIP + 120, 0.40, 6), (TIP + 180, 0.40, 5)]
t = N.dip_trade(pr, TIP, P, 0.75, True, True)
check("10+ contracts at the target after the entry sell at the touch; strict does not", (t["sold_at"], t["sold_touch_at"]), (None, TIP + 180))
check("the touch sale pays the target less its fee; the strict row holds to a win", (round(t["profit_touch"] + t["cost"], 4), round(t["profit"] + t["cost"], 4)),
      (round(P - N.fee(P), 4), 1.0))
pr2 = [(TIP + 60, 0.28, 20), (TIP + 120, 0.40, 6), (TIP + 180, 0.40, 3)]
t2 = N.dip_trade(pr2, TIP, P, 0.75, False, True)
check("only 9 at the target: no sale either way", (t2["sold_at"], t2["sold_touch_at"], t2["profit_touch"] == t2["profit"]), (None, None, True))
pr3 = [(TIP + 60, 0.28, 20), (TIP + 90, 0.41, 2)]
t3 = N.dip_trade(pr3, TIP, P, 0.75, False, True)
check("a print above sells under both rules", (t3["sold_at"], t3["sold_touch_at"]), (TIP + 90, TIP + 90))


def fill(at, profit, cost=0.31, touch=None, sold=None):
    return dict(limit=0.3, fill_at=at, printed=20, sold_at=sold, cost=cost, profit=profit, won=profit > 0, reason="x", sold_touch_at=sold, profit_touch=profit if touch is None else touch)


def bucket(tk, P, f75=None, f65=None, no_wins=True, ok=True):
    return dict(id=tk, bucket="1-5", team="AAA", P=P, spread=0.02, ask=dict(status="verified" if ok else "unverified"), no_wins=no_wins,
                fills={"d75": f75, "d65": f65, "d85": None})


def entry(night, tip, buckets, event=None, version=N.VERSION):
    return dict(event=event or f"KXNBAWINMARGIN-{night}", night=night, tip=tip, insample=False, version=version, buckets=buckets)


state = dict(entries=[
    entry("2026-11-18", TIP, [bucket("A", 0.4, fill(TIP + 600, 0.5))], event="old"),                                   # before the first night: no backfill
    entry("2026-11-19", TIP, [bucket("B1", 0.40, fill(TIP + 600, 0.40, sold=TIP + 900)), bucket("B2", 0.42, fill(TIP + 5000, -0.30)),      # B2: a fill after the hour
                              bucket("B3", 0.41, None, fill(TIP + 700, -0.30)), bucket("B4", 0.43, fill(TIP + 800, -0.30), ok=False)], event="g1"),
    entry("2026-11-20", TIP + 86400, [bucket("C1", 0.40, fill(TIP + 86400 + 100, -0.30), no_wins=False), bucket("C2", 0.44, None)], event="g2"),
])
h = H.fills(state, "d75")
check("fills: only the fresh nights, within the hour, ask verified", sorted(r["id"] for _e, r, _f in h), ["B1", "C1"])
check("all-game fills include the late one", sorted(r["id"] for _e, r, _f in H.fills(state, "d75", first_hour=False)), ["B1", "B2", "C1"])
b = H.board(state)
check("per fill is cost-weighted, per game is the mean of game rows; 2 fills, 2 games, 2 nights",
      (b["head"]["fills"], b["head"]["games"], b["head"]["nights"], round(b["head"]["roi_fill"], 4), round(b["head"]["roi_game"], 4)),
      (2, 2, 2, round((0.40 - 0.30) / 0.62, 4), round((0.40 / 0.31 - 0.30 / 0.31) / 2, 4)))
check("the side row is the 65% bid, first hour", b["side"]["fills"], 1)
bl = H.blind_items(state, h)
check("blind: one per pick, never a bucket the 75% bid filled in the hour, same game", [(r["id"] in ("B3", "B2")) for _e, r, _f in bl][:1], [True])
check("blind is deterministic", [r["id"] for _e, r, _f in H.blind_items(state, h)], [r["id"] for _e, r, _f in bl])
check("read: too early", H.read_text(b).startswith("too early (2 of 30"), True)
big = dict(head=dict(fills=30, roi_fill=-0.01, z=1.0, top_night=0.2), all75=dict(roi_fill=0.0), nights=10)
check("read at 30 fills, at or under zero: retire", H.read_text(big).startswith("read at 30 fills: retire"), True)
big["head"] = dict(fills=30, roi_fill=0.08, z=2.5, top_night=0.2)
big["all75"] = dict(roi_fill=0.02)
check("read at 30 fills, above zero, z 2+, beats all-fills, not one night: candidate", "candidate to promote" in H.read_text(big), True)
big["head"]["top_night"] = 0.7
check("one night carries it: stays paper", H.read_text(big).endswith("stays paper"), True)
slow = dict(head=dict(fills=10, roi_fill=0.1, z=1, top_night=0.1), all75=dict(roi_fill=0), nights=30)
check("under one fill a night after 30 nights: retire", H.read_text(slow).startswith("retire: 10 fills in 30 nights"), True)

print("\nthe watch line")
rows = []
for k in range(8):
    night = f"2026-12-{k + 1:02d}"
    for j in range(10):
        rows.append(dict(night=night, ask=0.15, eligible=True, m=dict(first2=30 if j < 4 else None)))
w = H.watch(dict(rows=rows))
check("40% of 10-20c buckets doubled in the hour for a week: flagged", (round(w["week"], 2), w["flag"]), (0.4, True))
rows2 = [r for r in rows if r["night"] < "2026-12-06"]
check("under 7 nights of data: no week figure, no flag", (H.watch(dict(rows=rows2))["week"], H.watch(dict(rows=rows2))["flag"]), (None, False))
check("a double after the hour does not count", H.watch(dict(rows=[dict(night=f"2026-12-0{k}", ask=0.15, eligible=True, m=dict(first2=70)) for k in range(1, 8)]))["week"], 0.0)

print("\nthe page")
html = B.first_hour_block(state, dict(rows=rows))
check("labelled Sandbox paper, percentages only, no guarded phrase, no inline style",
      ("Sandbox paper" in html, re.search(r"\$\d", html), sandbox_audit.COPY_RE.findall(html), "style=" in html), (True, None, [], False))
check("the flag shows", "Flag:" in html, True)
check("an empty ledger still renders", "too early (0 of 30" in B.first_hour_block(dict(entries=[]), {}), True)
import nba_layout
check("the NBA page carries the fold inside the NO fade card", 'id="nofade-1h"' in nba_layout.nofade_card({}, N.load()), True)

if FAILED:
    print(f"\n{len(FAILED)} FAILED")
    sys.exit(1)
print("\nALL PASS")
