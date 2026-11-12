"""The top of the Production page (2026-11-11): every lane's LIVE record from its first live bet, in percentages only.

Why: the old table restarted a lane's record at every version change and every stake raise, so NBA read -1.9% (counted from its v4 move) while its
live record since the first night was +18.7%, and a lane that had been retired disappeared with its losses. Here a lane's live record is every
settled live bet it ever placed. A version change or a raise is a small note inside the lane's fold, never a reset of the headline.

PUBLIC PAGE: win-loss records and return per unit staked after fees. No dollar amount, no balance, no stake size, anywhere.
Read-only: nothing here touches a lane, a stake or an order.
"""
import datetime as dt
import html as _h

import production_live as PL

GROUPS = ("NBA", "Soccer", "Crypto · Econ · S&P")
EARLY_N = 10                         # under this many settled bets a return is grey ("too early")
# The own-state lanes the follower runs from its own state files, and the lane a Production pair's live bets are read from.
OWN_RUNNING = ("nba_wm_yes", "nba_wm_nofade", "arg_dip")
OWN_RETIRED = ("o35_cheap_no", "top5_dip")
OWN_GROUP = {"nba_wm_yes": "NBA", "nba_wm_nofade": "NBA", "arg_dip": "Soccer", "o35_cheap_no": "Soccer", "top5_dip": "Soccer"}
OWN_RULE = {
    "nba_wm_yes": "Backs the Yes side of an NBA win-margin bracket and sells in two parts on the way up.",
    "nba_wm_nofade": "Backs No on an NBA win-margin bracket the market overrates.",
    "arg_dip": "Buys over 0.5 goals in an Argentine league match that stays goalless, at a price below its pre-match level, and sells back.",
    "o35_cheap_no": "Backed No on a cheap over 3.5 goals line in soccer, selling into a spike.",
    "top5_dip": "Bought over 1.5 goals in a top-five-league match that stayed goalless, below its pre-match price, and sold back.",
}


PLAIN = {"finance_spx_nc_no": "S&P 500 near-certain NO", "finance_spx_nc_no|finance_daily": "S&P 500 near-certain NO"}


def plain(name):
    """A lane's display name: a raw id becomes words; a registered label is left as it is."""
    n = str(name or "")
    if n in PLAIN:
        return PLAIN[n]
    if n and "_" in n and " " not in n:
        return n.replace("_", " ").capitalize()
    return n


def esc(x):
    return _h.escape(str(x), quote=True)


def group_of(key):
    """The sport group a lane sits in, from its pair key ('source|sport') or its own-state lane name."""
    if key in OWN_GROUP:
        return OWN_GROUP[key]
    sport = key.split("|", 1)[1] if "|" in key else key
    if sport == "nba_wm" or sport.startswith("nba"):
        return "NBA"
    if sport.startswith("soccer"):
        return "Soccer"
    if sport in ("crypto_fav", "econ_daily", "finance_daily"):
        return "Crypto · Econ · S&P"
    return "Other"


def _day(x):
    t = PL._t(x)
    return f"{t:%b} {t.day}" if t else ""


def _first_sentence(text):
    text = " ".join(str(text or "").split())
    if not text:
        return ""
    i = text.find(". ")
    return text if i < 0 else text[:i + 1]


def tally(rows, own):
    """Won, lost, flat, open and the stake-weighted return per unit staked after fees over the SETTLED bets of one lane.

    A pair's orders are won or lost; an own-state lane's trades are W, F (flat, exited within +-2% of cost) or L, as the Production page has
    always classed them. A bet with no weight counts as one unit."""
    won = lost = flat = 0
    num = den = 0.0
    for o in rows:
        if own:
            c = PL.own_class(o)
            if not c:
                continue
            won += c == "W"
            flat += c == "F"
            lost += c == "L"
        else:
            if o.get("st") not in PL.SETTLED:
                continue
            won += o["st"] == "won"
            lost += o["st"] == "lost"
        if o.get("r") is not None:
            w = o.get("w") or 1.0
            num += w * o["r"]
            den += w
    return dict(won=won, lost=lost, flat=flat, n=won + lost + flat, roi=(num / den if den else None), num=num, den=den,
                open=sum(1 for o in rows if o.get("st") == "open"))


def lane_live(key, live_blob):
    """One Production pair's LIVE record from its first live bet, exactly as build() counts it for the Production page: an own-state pair
    (production_live.OWN_PAIRS) by every trade of its lane, any other pair by every order it placed. Versions and stake raises never reset it.
    The Soccer page's rows and tiles read this, so the two pages agree (2026-11-11)."""
    live_blob = live_blob or {}
    spec = PL.OWN_PAIRS.get(key)
    if spec:
        return tally(list((live_blob.get("lanes") or {}).get(spec[0]) or []), True)
    return tally(list(((live_blob.get("pairs") or {}).get(key) or {}).get("orders") or []), False)


def combine(parts):
    """The combined record of several lanes: counts add, the return is stake-weighted across all their settled bets."""
    num = sum(p["num"] for p in parts)
    den = sum(p["den"] for p in parts)
    return dict(won=sum(p["won"] for p in parts), lost=sum(p["lost"] for p in parts), flat=sum(p["flat"] for p in parts),
                n=sum(p["n"] for p in parts), roi=(num / den if den else None), num=num, den=den, lanes=len(parts))


def build(live_blob, pairs, now=None):
    """Every lane the page shows, from the follower's live record and the Production page's own per-pair facts.

    `pairs` is {pair key: dict(name, sport_label, paper=<Sandbox assess>, raised_at, note)} for the pairs in Production. -> dict(running, waiting,
    retired, tiles) where each lane is dict(key, name, group, live, paper, since, last, notes, rule, paper_roi, clv)."""
    live_blob = live_blob or {}
    lp = live_blob.get("pairs") or {}
    own_rows = live_blob.get("lanes") or {}
    pulled = live_blob.get("pulled") or {}
    notes_by_lane = {}
    lanes = {}

    def add(key, name, group, rows, own, paper, **kw):
        lanes[key] = dict(key=key, name=name, group=group, own=own, rows=rows, live=tally(rows, own), paper=paper, **kw)

    # -- the lanes in Production: a pair's own orders, or the own-state lane its live bets are read from
    for key, meta in sorted(pairs.items()):
        spec = PL.OWN_PAIRS.get(key)
        if spec:
            lane = spec[0]
            cur = lanes.get(lane)
            paper = meta.get("paper") or {}
            if cur is None:
                add(lane, PL.LANE_NAMES.get(lane, meta["name"]), group_of(lane), list(own_rows.get(lane) or []), True,
                    dict(n=paper.get("n") or 0, won=paper.get("won") or 0, roi=paper.get("roi_fee")), notes=[], rule=OWN_RULE.get(lane, ""),
                    clv=None)
            else:
                cur["paper"]["n"] += paper.get("n") or 0
                cur["paper"]["won"] += paper.get("won") or 0
            if meta.get("note"):
                lanes[lane]["notes"].append(meta["note"])
            continue
        paper = meta.get("paper") or {}
        rows = list((lp.get(key) or {}).get("orders") or [])
        rule = _first_sentence(meta.get("rule")) or ""
        add(key, plain(meta["name"]), group_of(key), rows, False, dict(n=paper.get("n") or 0, won=paper.get("won") or 0, roi=paper.get("roi_fee")),
            notes=[meta["note"]] if meta.get("note") else [], rule=rule, clv=meta.get("clv"), market=meta.get("market"))
    # an own-state lane in the file with live rows but no Production pair on the page yet still counts as running
    for lane in OWN_RUNNING:
        if lane not in lanes:
            add(lane, PL.LANE_NAMES.get(lane, lane), group_of(lane), list(own_rows.get(lane) or []), True, dict(n=0, won=0, roi=None),
                notes=[], rule=OWN_RULE.get(lane, ""), clv=None)

    running, waiting = [], []
    for lane in lanes.values():
        lane["since"], lane["last"] = _span(lane["rows"])
        (running if lane["live"]["n"] else waiting).append(lane)

    retired = []
    for key, rows in sorted(pulled.items()):
        rows = list(rows or [])
        src = key.split("|", 1)[0]
        retired.append(dict(key=key, name=plain(_pulled_name(key)), group=group_of(key), own=False, rows=rows, live=tally(rows, False), paper=None,
                            notes=[], rule="", clv=None, market=_pulled_market(key), since=_span(rows)[0], last=_span(rows)[1]))
    for lane in OWN_RETIRED:
        rows = list(own_rows.get(lane) or [])
        retired.append(dict(key=lane, name=PL.LANE_NAMES.get(lane, lane), group=OWN_GROUP[lane], own=True, rows=rows, live=tally(rows, True),
                            paper=None, notes=[], rule=OWN_RULE.get(lane, ""), clv=None, market=None, since=_span(rows)[0], last=_span(rows)[1]))
    retired = [r for r in retired if r["live"]["n"] or r["rows"]]
    key = lambda l: (-(l["live"]["n"]), l["name"])
    running.sort(key=lambda l: (GROUPS.index(l["group"]) if l["group"] in GROUPS else 9, -(l["live"]["roi"] or -9), l["name"]))
    waiting.sort(key=lambda l: l["name"])
    retired.sort(key=lambda l: (l["live"]["roi"] if l["live"]["roi"] is not None else 9, l["name"]))
    tiles = dict(running=combine([l["live"] for l in running]), retired=combine([l["live"] for l in retired if l["live"]["n"]]),
                 everything=combine([l["live"] for l in running + retired if l["live"]["n"]]),
                 n_running=len(running), n_retired=len([r for r in retired if r["live"]["n"]]), n_waiting=len(waiting))
    return dict(running=running, waiting=waiting, retired=retired, tiles=tiles)


def _span(rows):
    kos = sorted(str(o.get("ko") or "") for o in rows if o.get("ko"))
    return (kos[0] if kos else None), (kos[-1] if kos else None)


def _pulled_name(key):
    import sandbox_sources as S
    src, _, sport = key.partition("|")
    try:
        return S.scoped_rule(src, sport)
    except Exception:                                            # noqa: BLE001
        return src


def _pulled_market(key):
    import sandbox_sources as S
    sport = key.partition("|")[2]
    return S.SPORTS.get(sport) or S.OWN_LEDGER_SPORTS.get(sport) or None


# ---------------------------------------------------------------------------------------------- html
def _pct(x, n=None):
    if x is None:
        return '<span class="mut">—</span>'
    cls = "mut" if (n is not None and n < EARLY_N) else ("pos" if x > 0 else "neg" if x < 0 else "mut")
    return f'<span class="{cls}">{x * 100:+.1f}%</span>'


def _paper_wl(paper):
    if not paper or not paper.get("n"):
        return "—"
    return f'{paper["won"]}–{paper["n"] - paper["won"]}'


def _lane(l, retired=False):
    live = l["live"]
    bits = []
    if l["since"]:
        bits.append(f'Live since {esc(_day(l["since"]))}')
    if l["last"]:
        bits.append(f'last bet {esc(_day(l["last"]))}')
    lines = [f'<p class="sm">{" · ".join(bits)}</p>'] if bits else []
    if live["flat"]:
        lines.append(f'<p class="sm mut">{live["flat"]} more closed flat (within 2% of cost), not counted as a win or a loss.</p>')
    if live["open"]:
        lines.append(f'<p class="sm mut">{live["open"]} bet{"s" if live["open"] != 1 else ""} still open.</p>')
    for n in l.get("notes") or []:
        lines.append(f'<p class="sm mut">{esc(n)}</p>')
    if l.get("rule"):
        lines.append(f'<p class="sm">Rule: {esc(l["rule"])}</p>')
    if l.get("market"):
        lines.append(f'<p class="sm mut">Market: {esc(l["market"])}.</p>')
    if not retired and l.get("paper") is not None:
        p = l["paper"]
        bit = f'Paper (same rule, graded without placing bets): {_paper_wl(p)}'
        if p.get("roi") is not None and p.get("n"):
            bit += f', {p["roi"] * 100:+.1f}% after fees'
        lines.append(f'<p class="sm mut">{esc(bit)}.</p>')
    if l.get("clv"):
        lines.append(f'<p class="sm mut">Price move after the bet was logged: {esc(l["clv"])}.</p>')
    paper = ("" if retired else f'<span class="lp mut">{esc(_paper_wl(l.get("paper")))}</span>')
    body = "".join(lines) or '<p class="sm mut">Nothing more to say yet.</p>'
    return (f'<details class="lane"><summary><span class="ln">{esc(l["name"])}</span>'
            f'<span class="lw">{live["won"]}–{live["lost"]}</span><span class="lr">{_pct(live["roi"], live["n"])}</span>{paper}</summary>'
            f'<div class="lane-body">{body}</div></details>')


def _head(retired=False):
    return ('<div class="lane-head"><span class="ln">Lane</span><span class="lw">Live</span><span class="lr">Return</span>'
            + ('' if retired else '<span class="lp">Paper</span>') + '</div>')


def _group(title, lanes, retired=False, opened=True):
    rec = combine([l["live"] for l in lanes if l["live"]["n"]]) if any(l["live"]["n"] for l in lanes) else None
    head = (f'<span class="mut sm">· {_pct(rec["roi"], rec["n"])} · {rec["won"]}–{rec["lost"]} · '
            f'{len(lanes)} lane{"s" if len(lanes) != 1 else ""}</span>') if rec else f'<span class="mut sm">· {len(lanes)} lane{"s" if len(lanes) != 1 else ""}</span>'
    return (f'<details class="fold lanes"{" open" if opened else ""}><summary><h3>{esc(title)}</h3>{head}</summary>'
            f'{_head(retired)}{"".join(_lane(l, retired) for l in lanes)}</details>')


def _waiting_lane(l):
    bits = []
    if l["live"]["open"]:
        bits.append(f'{l["live"]["open"]} bet{"s" if l["live"]["open"] != 1 else ""} placed, none settled yet')
    else:
        bits.append("No live bet yet")
    paper = l.get("paper") or {}
    lines = [f'<p class="sm">{esc(" · ".join(bits))}.</p>']
    for n in l.get("notes") or []:
        lines.append(f'<p class="sm mut">{esc(n)}</p>')
    if l.get("rule"):
        lines.append(f'<p class="sm">Rule: {esc(l["rule"])}</p>')
    if paper.get("n"):
        lines.append(f'<p class="sm mut">Paper (same rule, graded without placing bets): {_paper_wl(paper)}.</p>')
    return (f'<details class="lane"><summary><span class="ln">{esc(l["name"])}</span><span class="lw mut">0–0</span>'
            f'<span class="lr mut">—</span><span class="lp mut">{esc(_paper_wl(paper))}</span></summary><div class="lane-body">{"".join(lines)}</div></details>')


def tile(label, rec, extra=""):
    if not rec or not rec["n"]:
        return f'<div class="tile"><b class="mut">—</b><span>{esc(label)}</span></div>'
    return (f'<div class="tile"><b>{_pct(rec["roi"])}</b><span>{esc(label)}</span>'
            f'<span class="sub sm">{rec["won"]}–{rec["lost"]}{esc(extra)}</span></div>')


def tiles_html(model):
    t = model["tiles"]
    return ('<div class="tiles tiles3">'
            + tile("Lanes running now", t["running"], f' · {t["n_running"]} lanes')
            + tile("Retired lanes", t["retired"], f' · {t["n_retired"]} lanes')
            + tile("All lanes ever", t["everything"], f' · {t["n_running"] + t["n_retired"]} lanes')
            + '</div>')


def section_html(model, now=None):
    """The lane section: sport groups of running lanes, then 'Waiting for the first live bet', then 'Retired lanes'. Every group folds."""
    by = {g: [] for g in GROUPS}
    for l in model["running"]:
        by.setdefault(l["group"], []).append(l)
    parts = [_group(g, by[g]) for g in GROUPS if by.get(g)]
    parts += [_group(g, ls) for g, ls in by.items() if g not in GROUPS and ls]
    if model["waiting"]:
        w = model["waiting"]
        parts.append(f'<details class="fold lanes"><summary><h3>Waiting for the first live bet</h3>'
                     f'<span class="mut sm">· {len(w)} lane{"s" if len(w) != 1 else ""}</span></summary>'
                     f'{_head()}{"".join(_waiting_lane(l) for l in w)}</details>')
    r = model["retired"]
    if r:
        parts.append(_group("Retired lanes", r, retired=True, opened=False))
    return "".join(parts)
