"""The Production page's "live v paper" column (2026-11-04): what the follower really bought and how it settled, next to the paper record.

The live side is data/live_record.json (live_record_publish.py, from the follower's own orders: public fields only). The paper side is the
page's own since-Production record. Both are per pair; the gap is listed with its reasons wherever it is more than about one bet.
Read-only: nothing here touches a lane, a stake or an order.
"""
import datetime as dt
import html as _h
import json
import os
import re

import live_caps as LC

ROOT = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(ROOT, "data", "live_record.json")
GAP_BETS = 1.0              # a gap beyond about one bet is explained
SETTLED = ("won", "lost")
LANE_NAMES = {"o35_cheap_no": "Over 3.5 cheap NO", "nba_wm_yes": "NBA win margin YES split", "nba_wm_nofade": "NBA win margin NO fade",
              "top5_dip": "Top-5 goalless dip"}
CLUSTERED = ("commodities_fav", "crypto_fav")    # the paper record counts one result per market-day (a day's rungs grade together)
EXITS = {"o35_cheap_no", "nba_wm_yes"}      # lanes that sell early: an export from before the trades schema counted only their held-to-settle bets
# The Production pairs the follower runs from its own state files (no orders_placed rows), and the live rows each reads: pair key -> (lane in
# data/live_record.json, version window). "v4" = slates from the v4 start on, "v3" = slates from the v3 start up to the v4 start, "v2" = the slates before v3, None = every row.
OWN_PAIRS = {
    "nba_winmargin_v4|nba_wm": ("nba_wm_yes", "v4"), "nba_wm_nofade_v4|nba_wm": ("nba_wm_nofade", "v4"),
    "nba_winmargin_v3|nba_wm": ("nba_wm_yes", "v3"), "nba_wm_nofade_v3|nba_wm": ("nba_wm_nofade", "v3"),
    "nba_winmargin_live|nba_wm": ("nba_wm_yes", "v2"), "nba_wm_nofade|nba_wm": ("nba_wm_nofade", "v2"),
    "o35_cheap_no_wave|soccer_u35": ("o35_cheap_no", None), "top5_goalless_dip_live|soccer_o15": ("top5_dip", None),
}
SLATE_RE = re.compile(r"-(\d{2})([A-Z]{3})(\d{2})[A-Z]{6}-")
MONTHS = {m: i + 1 for i, m in enumerate("JAN FEB MAR APR MAY JUN JUL AUG SEP OCT NOV DEC".split())}


def esc(x):
    return _h.escape(str(x))


def load(path=None):
    try:
        with open(PATH if path is None else path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _t(x):
    try:
        t = dt.datetime.fromisoformat(str(x).replace("Z", "+00:00"))
    except ValueError:
        return None
    return t if t.tzinfo else t.replace(tzinfo=dt.timezone.utc)


def window(orders, since, until=None):
    """The orders whose kickoff is at or after `since` (None = all time) and before `until` (None = no end)."""
    cut = _t(since) if since else None
    end = _t(until) if until else None
    if cut is None and end is None:
        return list(orders)
    out = []
    for o in orders:
        ko = _t(o.get("ko"))
        if ko is not None and (cut is None or ko >= cut) and (end is None or ko < end):
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


def slate(row):
    """The night an own-state row belongs to: the date code of an NBA ticker (26NOV04 = 2026-11-04, the US night, so a late tip cannot fall into the
    next one), else the kickoff's date."""
    m = SLATE_RE.search(str(row.get("id") or ""))
    if m and m.group(2) in MONTHS:
        return f"20{m.group(1)}-{MONTHS[m.group(2)]:02d}-{m.group(3)}"
    return str(row.get("ko") or "")[:10]


def current_schema(rows):
    """True when every row is a trade as the publisher now writes it (carries its source). An export from before that (sells not counted, held
    to settlement only) is not shown as a live record: the page keeps its old cells until the next publish."""
    return all("src" in r for r in rows)


def own_rows(live_blob, key, v3_since=None, v4_since=None):
    """The live trades of an own-state Production pair (OWN_PAIRS), or None when the pair is not one or the file has no such lane.
    Version 4 is the slates from `v4_since`, version 3 the ones from `v3_since` up to it, version 2 the ones before version 3 (all of them when
    there is no version 3)."""
    spec = OWN_PAIRS.get(key)
    if spec is None or not live_blob:
        return None
    lane, ver = spec
    rows = (live_blob.get("lanes") or {}).get(lane)
    if rows is None or not current_schema(rows):
        return None
    if ver == "v4":
        return [r for r in rows if v4_since and slate(r) >= v4_since]
    if ver == "v3":
        return [r for r in rows if v3_since and slate(r) >= v3_since and not (v4_since and slate(r) >= v4_since)]
    if ver == "v2":
        return [r for r in rows if not v3_since or slate(r) < v3_since]
    return list(rows)


FLAT = 0.02                 # flat (F): within +-2% of cost before OR after fees; W: above +2% after fees and not flat; L: the rest
FLAT_NOTE = "F = flat, within ±2% of cost before or after fees. Flat = exited at cost; the entry fee still counts in ROI"


def own_class(o):
    """'W', 'F' or 'L' for one settled own-state result, by its return after fees (None while open)."""
    r, g = o.get("r"), o.get("g")
    if o["st"] not in ("won", "flat", "lost") or r is None:
        return None                      # an open trade is in no bucket
    if abs(r) <= FLAT + 1e-9 or (g is not None and abs(g) <= FLAT + 1e-9):
        return "F"
    return "W" if r > FLAT else "L"


def own_summary(rows, third="3x"):
    """An own-state lane's live record as TRADES after exchange fees: W = realised return above +2% (a bet sold at its target is won whatever the
    market later did), F = flat within +-2%, L = below -2%; stake-weighted ROI over every settled trade; the legs filled (YES split) and the
    same entries held to settlement."""
    done = [o for o in rows if own_class(o)]
    won = sum(1 for o in done if own_class(o) == "W")
    flat = sum(1 for o in done if own_class(o) == "F")
    wl = [o for o in done if o.get("w")]
    w = sum(o["w"] for o in wl)
    hold = [o for o in done if o.get("hold_r") is not None and o.get("w")]
    hw = sum(o["w"] for o in hold)
    return dict(won=won, flat=flat, lost=len(done) - won - flat, n=len(done), open=sum(1 for o in rows if o["st"] == "open"),
                roi=(sum(o["w"] * o["r"] for o in wl) / w if w else None),
                legs2=sum(1 for o in done if "2x" in (o.get("legs") or "")), legs3=sum(1 for o in done if third in (o.get("legs") or "")), third=third,
                sold_any=sum(1 for o in done if o.get("legs")), reconstructed=sum(1 for o in rows if o.get("src") == "reconstructed"),
                hold_roi=(sum(o["w"] * o["hold_r"] for o in hold) / hw if hw else None), hold_n=len(hold), split=any(o.get("hold_r") is not None for o in done))


def wfl(summ):
    lost = summ["lost"] if "lost" in summ else summ["n"] - summ["won"] - summ.get("flat", 0)
    return f'{summ["won"]}–{summ.get("flat", 0)}–{lost}'


def own_live(live, summ):
    """The pair's since-Production counts replaced by the live trades': n settled, won, flat, ROI after fees (no no-result bets)."""
    return dict(live, n=summ["n"], won=summ["won"], flat=summ["flat"], n_price=0, roi_fee=summ["roi"], wfl=True)


def own_detail(summ):
    """The short list under a pair in its details fold: legs filled and the held control (YES split), early exits, open trades, reconstructed
    rows. The held-to-settlement figure is over exactly the settled trades the record next to it counts."""
    bits = []
    if summ["split"]:
        bits.append(f'legs filled: 2x {summ["legs2"]} · {summ.get("third", "3x")} {summ["legs3"]} of {summ["n"]}')
        if summ["hold_roi"] is not None:
            bits.append(f'same {summ["hold_n"]} entries held to settlement: {summ["hold_roi"] * 100:+.1f}%')
    elif summ["n"]:
        bits.append(f'sold early: {summ["sold_any"]} of {summ["n"]}')
    if summ["open"]:
        bits.append(f'{summ["open"]} open, not counted above')
    if summ["reconstructed"]:
        bits.append(f'{summ["reconstructed"]} reconstructed from the exchange order list')
    return "; ".join(bits) or "—"


def details_fold(items):
    """One fold per sport block for the own-state pairs: `items` [(pair name, summary)]. Carries the one-line W–F–L definition."""
    if not items:
        return ""
    lis = "".join(f"<li><b>{esc(n)}</b> · {esc(own_detail(s))}</li>" for n, s in items)
    return (f'<details class="fold"><summary>Live record details</summary><p class="sm mut">{esc(FLAT_NOTE)}.</p><ul class="sm">{lis}</ul></details>')


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


def fill_window(live_blob, key, since):
    """(the pair's own live orders from `since`, its exported block) when there is a live file, else (None, None). A pair absent from the file has placed
    nothing the file knows of, so it reads as no orders."""
    if not live_blob:
        return None, None
    p = (live_blob.get("pairs") or {}).get(key) or {}
    return window(p.get("orders") or [], since), p


def fill_live(live, rec):
    """The pair's since-Production counts replaced by the follower's own fills (2026-11-07): settled orders won/lost, ROI per $1 staked after the
    exchange's charged fees. The paper record stays in the Sandbox column."""
    return dict(live, n=rec["won"] + rec["lost"], won=rec["won"], flat=0, n_price=0, roi_fee=rec["roi"], wfl=False, fills=True)


def fill_fragment(rec):
    """The small line under a live record: orders still running, placed but unfilled, sold early, unconfirmed."""
    notes = [f"{rec[k]} {w}" for k, w in (("open", "running"), ("unfilled", "unfilled"), ("sold", "exited early"), ("unconfirmed", "unconfirmed")) if rec[k]]
    return f'<div class="sm mut live-line">{esc(" · ".join(notes))}</div>' if notes else ""


# Why a Production pair has placed nothing. Written once, from the follower's own ledger and the feed's history, for the pairs whose cause is
# known; the others are worded from their refusals or from the feed (no_orders_reason).
NO_ORDERS_WHY = {
    "u35_low_scoring|soccer_u35_intl": (
        "The only internationals fixtures since it moved (Oct 5–6, eight leads) were refused: their routes named a market where the exchange expects "
        "an event, so the follower found nothing open to buy. That was fixed on Oct 11 and there have been no internationals fixtures since "
        "(the next window is mid-November), so nothing has been tried on the fixed route yet."),
}


def no_orders_reason(key, refused, n_leads):
    """One line on why the pair has no live order: a known cause, else its refusals, else the feed's lead count."""
    if key in NO_ORDERS_WHY:
        return NO_ORDERS_WHY[key]
    if refused:
        cats = {}
        for c in refused.values():
            cats[c] = cats.get(c, 0) + 1
        top = ", ".join(f"{c} ({n})" for c, n in sorted(cats.items(), key=lambda kv: -kv[1])[:3])
        return f"Every lead was refused by the follower: {top}."
    if n_leads:
        return f"{n_leads} lead{'s' if n_leads != 1 else ''} in the feed, none bought yet."
    return "No qualifying fixture has reached the feed since the pair moved."


def no_orders_fold(rows):
    """One fold under the pairs table: each pair with no live order and the one-line reason. `rows`: [(label, reason)]."""
    if not rows:
        return ""
    body = "".join(f'<tr><td><b>{esc(label)}</b></td><td class="sm">{esc(why)}</td></tr>' for label, why in sorted(rows))
    return (f'<details class="fold"><summary>No live orders yet<span class="mut sm">· {len(rows)} pair{"s" if len(rows) != 1 else ""}</span></summary>'
            f'<div class="tbl"><table><thead><tr><th>Pair</th><th>Why nothing has been placed</th></tr></thead><tbody>{body}</tbody></table></div></details>')


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


# Non-soccer pairs whose live fills stay listed after the pair went back to the Sandbox (2026-11-08: the commodities favourite band).
HISTORY_SPORTS = ("commodities_fav",)
ENDED_LANES = {"o35_cheap_no": "Nov 6", "top5_dip": "Nov 8"}      # own-state lanes back in the Sandbox: their live fills stay as history


def pulled_table(live_blob, name):
    """Live fills on pairs that are no longer in Production (their own pair, never another scope's), one fold under the lanes table.
    `name(pair)` words the pair as the page does. Settled fills only: won, lost; the rest is counted open or unfilled."""
    import sandbox_sources as S
    pulled = (live_blob or {}).get("pulled") or {}
    # Soccer pairs that left Production, never a removed lane (removed lanes render nowhere).
    pulled = {p: o for p, o in pulled.items() if (p.split("|")[-1].startswith("soccer") or p.split("|")[-1] in HISTORY_SPORTS)
              and not S.lane_removed(*p.split("|", 1))}
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


def raised_fold(rows):
    """The record at the earlier stake, one fold under the pairs table (2026-11-06): for each pair whose stake was raised, the paper record and the
    live fills from its entry to the raise. The table above counts from the raise. `rows`: [(name, raised_at, paper assess, live record)]. No amount."""
    if not rows:
        return ""
    body = ""
    for name, at, paper, live in sorted(rows, key=lambda r: r[0]):
        paper_roi = "—" if paper.get("roi_fee") is None or not paper.get("n") else f'{paper["roi_fee"] * 100:+.1f}%'
        live_roi = "—" if live["roi"] is None else f'{live["roi"] * 100:+.1f}%'
        d = dt.date.fromisoformat(str(at)[:10])
        body += (f'<tr><td>{esc(name)}</td><td>{esc(f"{d:%b} {d.day}")}</td>'
                 f'<td class="num"><b>{paper["won"]}–{paper["n"] - paper["won"]}</b></td><td class="num">{paper_roi}</td>'
                 f'<td class="num"><b>{live["won"]}–{live["lost"]}</b></td><td class="num">{live_roi}</td></tr>')
    return ('<details class="fold"><summary>Raised-stake pairs, the record at the earlier stake</summary>'
            '<div class="tbl"><table><thead><tr><th>Pair</th><th>Stake raised</th><th class="num">Paper W–L</th><th class="num">Paper ROI</th>'
            f'<th class="num">Live W–L</th><th class="num">Live ROI</th></tr></thead><tbody>{body}</tbody></table></div>'
            '<p class="sm mut">Entry to the raise. The Since Production columns above count from the raise.</p></details>')


def lanes_table(live_blob):
    """The own-state lanes (o35, nba_wm, the top-5 dip), live only: their paper record sits on their own lane pages.

    Each entry is a trade after the exchange's fees: the sells the follower logged (or, before 2026-11-06 18:07Z, the exchange order list's) plus
    the unsold remainder at settlement. Settled trades only: W above +2% after fees and not flat, F within +-2% of cost before or after fees, L the
    rest. The cells are the record and ROI; the notes sit in the fold under the table."""
    if not live_blob or not live_blob.get("lanes"):
        return ""
    body, notes = "", []
    for lane, rows in live_blob["lanes"].items():
        if not rows or not current_schema(rows):
            continue
        rec = own_summary(rows)
        roi = "—" if rec["roi"] is None else f'{rec["roi"] * 100:+.1f}%'
        name = LANE_NAMES.get(lane, lane) + (f" · back in the Sandbox {ENDED_LANES[lane]}" if lane in ENDED_LANES else "")
        body += (f'<tr><td>{esc(name)}</td><td class="num"><b>{wfl(rec)}</b></td><td class="num">{roi}</td></tr>')
        notes.append(f"<li><b>{esc(name)}</b> · {esc(own_detail(rec))}</li>")
    if not body:
        return ""
    return ('<details class="fold"><summary>Own-state lanes, live fills (NBA win margin; over 3.5 cheap NO and the top-5 dip stay as history)</summary>'
            '<div class="tbl"><table><thead><tr><th>Lane</th><th class="num">Live W–F–L</th><th class="num">ROI</th></tr></thead>'
            f'<tbody>{body}</tbody></table></div><p class="sm mut">{esc(FLAT_NOTE)}.</p><ul class="sm">{"".join(notes)}</ul>'
            f'<p class="sm mut">{esc(live_blob.get("lane_note") or "")}</p></details>')
