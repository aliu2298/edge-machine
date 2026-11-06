"""The Production page's "live v paper" column (2026-11-04): what the follower really bought and how it settled, next to the paper record.

The live side is data/live_record.json (live_record_publish.py, from the follower's own orders: public fields only). The paper side is the
page's own since-Production record. Both are per pair; the gap is listed with its reasons wherever it is more than about one bet.
Read-only: nothing here touches a lane, a stake or an order.
"""
import datetime as dt
import html as _h
import json
import os

import live_caps as LC

ROOT = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(ROOT, "data", "live_record.json")
GAP_BETS = 1.0              # a gap beyond about one bet is explained
SETTLED = ("won", "lost")
LANE_NAMES = {"o35_cheap_no": "Over 3.5 cheap NO", "nba_wm_yes": "NBA win margin YES split", "nba_wm_nofade": "NBA win margin NO fade"}
CLUSTERED = ("commodities_fav", "crypto_fav")    # the paper record counts one result per market-day (a day's rungs grade together)
EXITS = {"o35_cheap_no", "nba_wm_yes"}      # lanes that also sell early: the held-to-settle bets are not the lane's whole result


def esc(x):
    return _h.escape(str(x))


def load(path=PATH):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _t(x):
    try:
        t = dt.datetime.fromisoformat(str(x).replace("Z", "+00:00"))
    except ValueError:
        return None
    return t if t.tzinfo else t.replace(tzinfo=dt.timezone.utc)


def window(orders, since):
    """The orders whose kickoff is at or after `since` (None = all time)."""
    cut = _t(since) if since else None
    if cut is None:
        return list(orders)
    out = []
    for o in orders:
        ko = _t(o.get("ko"))
        if ko is not None and ko >= cut:
            out.append(o)
    return out


def record(orders):
    """Won, lost, open, unfilled, exited early, and the ROI per $1 of the settled bets (stake-weighted)."""
    won = sum(1 for o in orders if o["st"] == "won")
    lost = sum(1 for o in orders if o["st"] == "lost")
    wl = [o for o in orders if o["st"] in SETTLED and o.get("w") and o.get("r") is not None]
    w = sum(o["w"] for o in wl)
    return dict(won=won, lost=lost, n=won + lost, open=sum(1 for o in orders if o["st"] == "open"),
                unfilled=sum(1 for o in orders if o["st"] == "unfilled"), sold=sum(1 for o in orders if o["st"] == "sold"),
                unconfirmed=sum(1 for o in orders if o["st"] == "unconfirmed"),
                roi=(sum(o["w"] * o["r"] for o in wl) / w if w else None))


def link_orders(paper, orders):
    """The follower's early orders carry no paper-bet id (placed before the lead named its Sandbox quote), so they cannot be matched by id.
    Where an order has no id, it is linked to the one unlinked paper bet that kicks off at the same minute (the pair is the same: both
    lists are one pair's). Copies; nothing is altered."""
    out, taken = [], {o["id"] for o in orders if o.get("id")}
    for o in orders:
        if not o.get("id") and o.get("ko"):
            hit = [p for p in paper if p["id"] not in taken and str(p.get("ko") or "")[:16] == str(o["ko"])[:16]]
            if len(hit) == 1:
                taken.add(hit[0]["id"])
                o = dict(o, id=hit[0]["id"], linked_by="kickoff")
        out.append(o)
    return out


def explain(paper, orders, refused, in_feed=None, feed_from=None, pair=None, horizon=None):
    """Why the live record differs from the paper one for a pair, as {reason: count}.

    `paper`  the pair's paper bets since Production: [{id, status}] (status open|won|lost|settled)
    `orders` the live orders in the same window
    `refused` {quote id: category} the follower's refusals of leads that never got an order
    `feed_from` the earliest kickoff the feed still holds for the pair: older paper bets cannot be placed in or out of it
    `in_feed` the quote ids the Production feed carries (None = unknown): a paper bet missing from it never reached the follower"""
    orders = link_orders(paper, orders)
    live = {o["id"]: o for o in orders if o.get("id")}
    out = {}

    def add(why):
        out[why] = out.get(why, 0) + 1

    ids = set()
    for p in paper:
        ids.add(p["id"])
        o = live.get(p["id"])
        if o is None:
            if p["id"] in refused:
                add("refused: " + refused[p["id"]])
            elif pair and p.get("price") is not None and LC.reason(pair, p["price"]):
                add(LC.reason(pair, p["price"]) + " (the follower refuses the leg)")
            elif in_feed is not None and p["id"] not in in_feed:
                ko, cut = _t(p.get("ko")), _t(feed_from or horizon) if (feed_from or horizon) else None
                if cut is not None and ko is not None and ko < cut:
                    add("older than the feed's retained history (settled leads are kept 7 days; cannot tell whether it was published)")
                else:
                    add("never in the feed (the feed publishes fewer bets than the Sandbox grades: reachability, one rung a day, lateness)")
            else:
                add("in the feed, no order and no refusal on record (the follower has not acted on it)")
        elif o["st"] == "unfilled":
            add("order sent, not filled")
        elif o["st"] == "unconfirmed":
            add("order sent, fill not confirmed")
        elif o["st"] == "sold":
            add("exited early (not a held-to-settle bet)")
        elif o["st"] in SETTLED and p["status"] in ("won", "lost") and (o["st"] == "won") != (p["status"] == "won"):
            add("settled the other way (paper and live graded the match differently)")
        elif o["st"] in SETTLED and p["status"] == "open":
            add("live settled from the exchange, paper not graded yet")
        elif o["st"] == "open" and p["status"] in ("won", "lost", "settled"):
            add("paper graded, exchange not settled yet")
    for o in orders:
        if o.get("id") and o["id"] not in ids:
            add("live order outside the paper window (paper has no such bet since Production)")
        elif not o.get("id"):
            add("live order not linked to a paper bet")
    big = [o for o in orders if o["st"] in SETTLED and o.get("w")]
    if big and max(o["w"] for o in big) / min(o["w"] for o in big) > 3:
        out["stake size changed during the window: the live ROI weights the larger, later bets more"] = sum(1 for o in big if o["w"] > 1.5)
    return out


def gap_bets(paper_n, paper_roi, live):
    """The gap between the two records, in bets: the settled-count difference and the ROI difference expressed as bets of return."""
    if live["n"] == 0 and not paper_n:
        return 0.0
    return abs(paper_n - live["n"])


def cells(key, pair_entered, paper, live_blob):
    """(record fragment, ROI fragment, data) to sit under the pair's paper record and ROI, or empty fragments with no data when
    there is no live file. Fragments, not cells: the pairs table is already as wide as its card."""
    if live_blob is None:
        return "", "", None
    p = (live_blob.get("pairs") or {}).get(key)
    if p is None:
        return "", "", None
    orders = window(p["orders"], pair_entered)
    rec = record(orders)
    notes = [f"{rec[k]} {w}" for k, w in (("open", "open"), ("unfilled", "unfilled"), ("sold", "exited early"), ("unconfirmed", "unconfirmed")) if rec[k]]
    rec_frag = (f'<div class="sm live-line" title="the follower\'s own fills, settled by Kalshi">live fills <b>{rec["won"]}–{rec["lost"]}</b>'
                + (f' <span class="mut">· {esc(", ".join(notes))}</span>' if notes else "") + "</div>")
    if rec["roi"] is None:
        roi_frag = '<div class="sm mut live-line">live fills —</div>'
    else:
        tone = "pos" if rec["roi"] > 0 else "neg" if rec["roi"] < 0 else ""
        gap = ""
        if paper.get("roi") is not None and rec["n"]:
            gap = f' <span class="mut">({(rec["roi"] - paper["roi"]) * 100:+.1f}pp v paper)</span>'
        roi_frag = f'<div class="sm live-line">live fills <span class="{tone}">{rec["roi"] * 100:+.1f}%</span>{gap}</div>'
    return rec_frag, roi_frag, dict(orders=orders, rec=rec, refused=p.get("refused") or {})


def gap_section(rows, paper_by_pair, in_feed=None, feed_from=None, horizon=None):
    """The 'why they differ' list for the pairs whose settled counts differ by more than about one bet, or whose ROI differs by more
    than one bet's worth of return. `rows`: [(pair label, key, paper settled n, paper roi, data from cells())]."""
    items = []
    for label, key, pn, proi, data in rows:
        if not data:
            continue
        rec = data["rec"]
        big_count = abs(pn - rec["n"]) > GAP_BETS
        big_roi = (proi is not None and rec["roi"] is not None and max(pn, rec["n"]) and
                   abs(rec["roi"] - proi) * max(pn, rec["n"]) > GAP_BETS * 0.5)
        if not (big_count or big_roi):
            continue
        why = explain(paper_by_pair.get(key, []), data["orders"], data["refused"], in_feed, (feed_from or {}).get(key), pair=key, horizon=horizon)
        if key.split("|")[-1] in CLUSTERED:
            days = len({o["ko"][:10] for o in data["orders"] if o["st"] in SETTLED})
            why["the paper record counts one result per market-day (a day's rungs grade together); live counts every order: "
                f"{rec['n']} settled orders over {days} days"] = rec["n"]
        lis = "".join(f"<li>{esc(w)}: <b>{n}</b></li>" for w, n in sorted(why.items(), key=lambda kv: -kv[1])) or "<li>no single cause found in the exported fields</li>"
        roi_txt = lambda x: "—" if x is None else f"{x * 100:+.1f}%"
        items.append(f'<div class="note sm"><b>{esc(label)}</b> · paper {pn} settled, {roi_txt(proi)} · live {rec["won"]}–{rec["lost"]}, '
                     f'{roi_txt(rec["roi"])}<ul>{lis}</ul></div>')
    if not items:
        return ""
    return ('<details class="fold"><summary>Where live and paper differ by more than about one bet</summary>' + "".join(items) + "</details>")


def pulled_table(live_blob, name):
    """Live fills on pairs that are no longer in Production (their own pair, never another scope's), one fold under the lanes table.
    `name(pair)` words the pair as the page does. Settled fills only: won, lost; the rest is counted open or unfilled."""
    import sandbox_sources as S
    pulled = (live_blob or {}).get("pulled") or {}
    # Soccer pairs that left Production, never a removed lane (removed lanes render nowhere).
    pulled = {p: o for p, o in pulled.items() if p.split("|")[-1].startswith("soccer") and not S.lane_removed(*p.split("|", 1))}
    rows = [(p, record(o)) for p, o in pulled.items() if o]
    rows = [(p, r) for p, r in rows if r["won"] or r["lost"] or r["open"]]
    if not rows:
        return ""
    body = ""
    for pair, rec in sorted(rows, key=lambda x: (-x[1]["n"], x[0])):
        roi = "—" if rec["roi"] is None else f'{rec["roi"] * 100:+.1f}%'
        extra = ", ".join(f"{rec[k]} {w}" for k, w in (("open", "open"), ("unfilled", "unfilled"), ("sold", "exited early")) if rec[k]) or "—"
        body += (f'<tr><td>{esc(name(pair))}</td><td class="num"><b>{rec["won"]}–{rec["lost"]}</b></td><td class="num">{roi}</td>'
                 f'<td class="sm mut">{esc(extra)}</td></tr>')
    return ('<details class="fold"><summary>Pairs no longer in Production, live fills (each under its own pair)</summary>'
            '<div class="tbl"><table><thead><tr><th>Pair</th><th class="num">Live W–L</th><th class="num">ROI</th><th>Other</th></tr></thead>'
            f'<tbody>{body}</tbody></table></div></details>')


def lanes_table(live_blob):
    """The own-state lanes (o35, nba_wm), live only: their paper record sits on their own lane pages."""
    if not live_blob or not live_blob.get("lanes"):
        return ""
    body = ""
    for lane, rows in live_blob["lanes"].items():
        rec = record(rows)
        extra = []
        if rec["open"]:
            extra.append(f'{rec["open"]} open')
        if rec["sold"]:
            extra.append(f'{rec["sold"]} exited early')
        roi = ("—" if rec["roi"] is None or lane in EXITS else f'{rec["roi"] * 100:+.1f}%')
        note = "held to settlement only; exits not counted" if lane in EXITS else "held to settlement"
        body += (f'<tr><td>{esc(LANE_NAMES.get(lane, lane))}</td><td class="num"><b>{rec["won"]}–{rec["lost"]}</b></td>'
                 f'<td class="num">{roi}</td><td class="sm mut">{esc(", ".join(extra) or "—")} · {esc(note)}</td></tr>')
    return ('<details class="fold"><summary>Own-state lanes, live (over 3.5 cheap NO, NBA win margin)</summary>'
            '<div class="tbl"><table><thead><tr><th>Lane</th><th class="num">Live W–L</th><th class="num">ROI</th><th>Notes</th></tr></thead>'
            f'<tbody>{body}</tbody></table></div><p class="sm mut">{esc(live_blob.get("lane_note") or "")}</p></details>')
