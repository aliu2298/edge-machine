"""The Sandbox's index of the paper watches (2026-11-14, Olu: "the NFL before kickoff should be in the sandbox so I can see it. Cricket also should be in the
sandbox so I can know what's going on"). One row a watch: what it watches, how much it has seen, its record so far and where its full section lives. Every
watch keeps its own card on its own sport page; this only indexes them. Presentation only: nothing here grades, replays or calls the venue, no rule, record or
start date changes. Percentages only. A watch that cannot be read is left out, never the page.

Columns: Watch · Page · Events seen · Fills · Return after fees · Status. "Events seen" is the events replayed so far (each is replayed once, after it settles),
so a watch that has seen events but filled nothing reads "12 events seen, 0 fills yet", and one with no settled event yet reads "none settled yet".
"""
import html as _html

import bs_bid as B
import ko_bid as K
import mentions_dump as MD
import nl_dump as N


def esc(x):
    return _html.escape(str(x), quote=True)


def _pct(x):
    return "—" if x is None else f"{x * 100:+.1f}%".replace("-", "−")


def _status(events, fills, read):
    if not events:
        return "Waiting for the first event to settle"
    if not fills:
        return f"{events} event{'s' if events != 1 else ''} seen, 0 fills yet"
    return read[0].upper() + read[1:]


def _row(lane, label, href, page, events, fills, roi, read):
    return dict(lane=lane, label=label, href=href, page=page, events=events, fills=fills, roi=roi if fills else None, status=_status(events, fills, read))


def rows():
    out = []
    try:
        st = B.load()
        rec = B.records(st)
        where = {"ufc": ("./fights.html#bs-bid-ufc", "Fights"), "boxing": ("./fights.html#bs-bid-boxing", "Fights"),
                 "nfl": ("./nfl.html#bs-bid-nfl", "NFL"), "cricket": ("./cricket.html#bs-bid-cricket", "Cricket")}
        for g, (href, page) in where.items():
            r = rec[g]
            out.append(_row(f"bs_bid_{g}", f"{B.GROUPS[g]['label']} · before-start bid · paper watch", href, page, r["games"], r["headline"]["n"], r["headline"]["roi"], r["read"]))
    except Exception:                                           # noqa: BLE001
        pass
    try:
        st = K.load()
        rec = K.records(st)
        for g, cfg in K.GROUPS.items():
            r = rec[g]
            out.append(_row(f"ko_bid_{g}", f"{cfg['label']} · before-kickoff bid · paper watch", f"./soccer.html#ko-bid-{g}", "Soccer", r["games"],
                            r["headline"]["n"], r["headline"]["roi"], r["read"]))
    except Exception:                                           # noqa: BLE001
        pass
    try:
        st = N.load()
        rec = N.records(st)
        r = rec["D20"]
        out.append(_row("nl_dump_d20", "Nations League total goals · dump bid · paper watch", "./soccer.html#nl-dump-d20", "Soccer", rec["games"], r["headline"]["n"],
                        r["headline"]["roi"], r["read"]))
    except Exception:                                           # noqa: BLE001
        pass
    try:
        st = MD.load()
        rec = MD.records(st)
        r = rec[MD.HEAD_ROW]
        out.append(_row("mentions_dump_m20", "Mentions · dump bid · paper watch", "./culture.html#dump-bid", "Culture", rec["events"], r["headline"]["n"],
                        r["headline"]["roi"], r["read"]))
    except Exception:                                           # noqa: BLE001
        pass
    return out


def index_html():
    rs = rows()
    if not rs:
        return ""
    body = "".join(
        f'<tr data-lane="{esc(r["lane"])}"><td><b>{esc(r["label"])}</b></td><td><a href="{esc(r["href"])}">{esc(r["page"])}</a></td>'
        f'<td class="num">{r["events"]}</td><td class="num">{r["fills"]}</td><td class="num">{_pct(r["roi"])}</td><td>{esc(r["status"])}</td></tr>' for r in rs)
    return ('<section id="paper-watches"><h2>Paper watches</h2><p class="shell-kicker">Bids resting under the last trade, replayed once after each event settles · '
            'fills only on a trade strictly through the bid · the record is the 25-second order delay · paper · not in Production</p>'
            '<div class="tbl"><table class="watch-index"><tr><th>Watch</th><th>Page</th><th class="num">Events seen</th><th class="num">Fills</th>'
            '<th class="num">Return after fees</th><th>Status</th></tr>' + body + '</table></div></section>')
