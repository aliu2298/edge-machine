"""public_site/daily_markets.html — the Kalshi daily-close ladder lanes on ONE tab (2026-11-08, as asked by Olu).

Crypto, Commodities, Econ and Finance (S&P) were four tabs. This is a PAGE merge, not a lane change: each group's
page is built exactly as before by its own builder (crypto_build, commodities_build, daily_build), so every rule
row, record, Production / Sandbox / Retired split and fold is the same. Only the page's body is lifted out, its ids
prefixed with the group key (two groups both have #rules, #events, #method), its heading demoted to h2, and the
four bodies stacked under one header. tables.js wires each group's filters and event tabs on their own
([data-sp-group]).

The old URLs stay: crypto.html, commodities.html, econ_daily.html and finance_daily.html are written as small
redirect pages to their anchor here, so links in emails, routines and old pages keep working.
"""
import datetime
import html as _h
import os
import re

import site_chrome as C

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "public_site", "daily_markets.html")
KEY = "daily_markets"
TITLE = "Daily Markets"
# (anchor, label, the old page's file). Order is the nav's old order.
GROUPS = (
    ("crypto", "Crypto", "crypto.html"),
    ("commodities", "Commodities", "commodities.html"),
    ("econ", "Econ", "econ_daily.html"),
    ("finance", "Finance (S&P)", "finance_daily.html"),
)
MAIN_OPEN = '<main id="content" class="wrap">'


def esc(x):
    return _h.escape(str(x))


def _builders():
    import commodities_build
    import crypto_build
    import daily_build
    return {
        "crypto": lambda now: crypto_build.build(now=now),
        "commodities": lambda now: commodities_build.build(now=now),
        "econ": lambda now: daily_build.build("econ_daily", now=now),
        "finance": lambda now: daily_build.build("finance_daily", now=now),
    }


def scoped_body(page_html, group):
    """The page's <main> body with every id (and every in-page reference to one) prefixed `group-`."""
    a = page_html.index(MAIN_OPEN) + len(MAIN_OPEN)
    b = page_html.rindex("</main>")
    body = re.sub(r"<footer>.*?</footer>\s*", "", page_html[a:b], flags=re.S)
    ids = set(re.findall(r'\bid="([^"]+)"', body))

    def ref(m):
        names = m.group(2).split()
        if not any(n in ids for n in names):
            return m.group(0)
        return f'{m.group(1)}="{" ".join(f"{group}-{n}" if n in ids else n for n in names)}"'
    body = re.sub(r'\b(id|aria-controls|aria-labelledby|for)="([^"]+)"', ref, body)
    body = re.sub(r'href="#([^"]+)"', lambda m: f'href="#{group}-{m.group(1)}"' if m.group(1) in ids else m.group(0), body)
    for role in ("rules", "events"):
        body = body.replace(f'<section id="{group}-{role}"', f'<section id="{group}-{role}" data-sp-role="{role}"', 1)
    # One h1 on the page: each group's own title becomes its section heading.
    body = re.sub(r"<h1>(.*?)</h1>", r'<h2 class="dm-title">\1</h2>', body, count=1, flags=re.S)
    return body.strip()


# ---------------------------------------------------------------------------------------------------- the fold shell (2026-11-11)
# Olu: "almost everything is collapsible… it's so much scrolling, almost endless" (13,400 px, ~70% of it the Completed event lists
# open in every group). LAYOUT ONLY: every lane, rule, record and ledger is the one its own builder wrote. Each section is now one
# closed fold whose line carries its record; inside, the running rules come first, the Completed list folds behind a count line, an
# empty Next 24h / In progress tab is left out, and the page opens with one tile per section (percentages only).
TILE_RE = re.compile(r'<div class="tile"><b(?: class="[^"]*")?>(.*?)</b><span>(.*?)</span></div>', re.S)
WL_RE = re.compile(r"^(\d+)–(\d+)$")
PCT_RE = re.compile(r"^[+−-]?\d+(?:\.\d+)?%$")


def _text(x):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", x)).strip()


def _close(html, start, tag="section"):
    """The index just past the </tag> that closes the <tag ...> opened at `start` (nesting counted)."""
    depth, pos = 0, start
    pat = re.compile(rf"<(/?){tag}\b[^>]*>")
    for m in pat.finditer(html, start):
        depth += -1 if m.group(1) else 1
        if depth == 0:
            return m.end()
    return len(html)


def group_stats(body):
    """{rules, open, wl, won, lost, record_label, roi} read from the group's own four tiles (the numbers its builder wrote)."""
    block = re.search(r'<div class="tiles sp-tiles">.*?</div></div>', body, re.S)      # the group's OWN four tiles, not a later block's
    tiles = [(_text(b), _text(l)) for b, l in TILE_RE.findall(block.group(0) if block else "")]
    out = dict(rules=None, open=None, won=None, lost=None, wl=None, label="", roi=None)
    for b, l in tiles:
        if l.startswith("open picks"):
            out["open"] = b
        elif l.startswith("active rules"):
            out["rules"] = b
        elif WL_RE.match(b):
            m = WL_RE.match(b)
            out.update(won=int(m.group(1)), lost=int(m.group(2)), wl=b, label=l)
        elif PCT_RE.match(b) and l.startswith("ROI"):
            out["roi"] = b
    return out


def rules_stats(body, group):
    """The section's running rules added up AS THEIR ROWS COUNT THEM (Production and Sandbox lists together): W–L summed, the return
    weighted by bets. A row in another unit (a weekly rule, '2–0 wks') is left out. None when the section has no such row."""
    a = body.find(f'<section id="{group}-rules"')
    if a < 0:
        return None
    sec = body[a:_close(body, a)]
    won = lost = rows = 0
    num = den = 0.0
    for m in re.finditer(r'<details class="sp-rule[^"]*".*?</summary>', sec, re.S):
        cells = {k: _text(v) for k, v in re.findall(r'data-l="([^"]+)">(.*?)</span>(?=<span class="sp-cell|</summary>)', m.group(0), re.S)}
        rec = WL_RE.match(cells.get("Record", ""))
        if not rec:
            continue
        w, l = int(rec.group(1)), int(rec.group(2))
        won += w
        lost += l
        rows += 1
        r = re.match(r"^([+−-]?\d+(?:\.\d+)?)%", cells.get("ROI after fees", ""))
        if r and w + l:
            num += (w + l) * float(r.group(1).replace("−", "-"))
            den += w + l
    if not won + lost:
        return None
    return dict(won=won, lost=lost, wl=f"{won}–{lost}", rules=str(rows), roi=(f"{num / den:+.1f}%".replace("-", "−") if den else None))


def win_pct(won, lost):
    return f"{100 * won / (won + lost):.0f}%" if won is not None and (won + lost) else None


def sum_line(stats):
    """'78% won · 7–2 · +13.7% return', or 'no settled bets yet'."""
    pct = win_pct(stats["won"], stats["lost"])
    if pct is None:
        return "no settled bets yet"
    bits = [f"{pct} won", stats["wl"]]
    if stats["roi"]:
        bits.append(f'{stats["roi"]} return')
    return " · ".join(bits)


def swing15_stats(inner):
    """The 15-Minute section's record over the rules it counts (not the observation row, not the watch row): W–L summed, the return
    weighted by bets (a unit stake each)."""
    won = lost = 0
    num = den = 0.0
    live = inner.split('<div class="sw15-lane">')[1] if '<div class="sw15-lane">' in inner else inner     # the running rules, not the archive lane
    for m in re.finditer(r'<details class="sp-rule[^"]*" id="sw15-[^"]*".*?</summary>', live, re.S):
        row = m.group(0)
        cells = {k: _text(v) for k, v in re.findall(r'data-l="([^"]+)">(.*?)</span>(?=<span class="sp-cell|</summary>)', row, re.S)}
        status = cells.get("Status", "").lower()
        rec = WL_RE.match(cells.get("Record", ""))
        if not rec or status.startswith("observation") or status.startswith("watch"):
            continue
        w, l = int(rec.group(1)), int(rec.group(2))
        won += w
        lost += l
        r = cells.get("Return after fees", "").replace("−", "-").replace("%", "")
        try:
            num += (w + l) * float(r)
            den += w + l
        except ValueError:
            pass
    return dict(rules=None, open=None, won=won if won + lost else None, lost=lost, wl=f"{won}–{lost}", label="",
                roi=(f"{num / den:+.1f}%".replace("-", "−") if den else None))


def _events_fold(body, group):
    """Events: an empty Next 24h / In progress tab and panel are left out; Completed folds behind a count line."""
    a = body.find(f'<section id="{group}-events"')
    if a < 0:
        return body
    b = _close(body, a)
    ev = body[a:b]
    for tab in ("next", "live"):
        m = re.search(rf'<button type="button" role="tab" data-tab="{tab}"[^>]*>(?:(?!</button>).)*?<span class="sp-count">0</span></button>', ev, re.S)
        if not m:
            continue                                            # something is in it: the tab stays
        ev = ev.replace(m.group(0), "", 1)
        pa = ev.find(f'<section class="sp-panel" id="{group}-events-{tab}"')
        if pa >= 0:
            ev = ev[:pa] + ev[_close(ev, pa):]
    # the Completed panel's content folds behind its count
    pa = ev.find(f'<section class="sp-panel" id="{group}-events-done"')
    if pa >= 0:
        pe = _close(ev, pa)
        panel = ev[pa:pe]
        head_end = panel.index(">") + 1
        m = re.match(r'<h3 class="sp-panel-title">(.*?)</h3>', panel[head_end:], re.S)
        title = _text(m.group(1)) if m else "Completed · 14 days"
        inner = panel[head_end + (m.end() if m else 0):-len("</section>")]
        n = re.search(rf'data-tab="done"[^>]*>(?:(?!</button>).)*?<span class="sp-count">(\d+)</span>', ev, re.S)
        count = n.group(1) if n else str(inner.count('class="sp-pick '))
        folded = (f'{panel[:head_end]}<details class="fold dm-done"><summary>{esc(title)} · <span class="sp-count">{count}</span> bets</summary>'
                  f'{inner}</details></section>')
        ev = ev[:pa] + folded + ev[pe:]
        # With the other tabs gone the strip would hold one button that repeats the fold's own line: leave it out.
        if len(re.findall(r'<button type="button" role="tab"', ev)) <= 1:
            ev = re.sub(r'<div class="sp-tabs".*?</div>', "", ev, count=1, flags=re.S)
    return body[:a] + ev + body[b:]


def section_shell(group, label, body, stats):
    """One closed fold per group: its name and record on the line, the group's own content inside."""
    m = re.search(r'<div class="sp-head">.*?</div>', body, re.S)
    scope = re.search(r'<p class="scope">(.*?)</p>', m.group(0), re.S) if m else None
    if m:
        body = body.replace(m.group(0), "", 1)
    t = re.search(r'<div class="tiles sp-tiles">.*?</div></div>', body, re.S)
    if t:
        body = body.replace(t.group(0), "", 1)
    body = _events_fold(body, group)
    bits = []
    if stats.get("rules") is not None:
        r = stats["rules"]
        bits.append(f'{esc(r)} rule{"" if r == "1" else "s"} running')
    if stats.get("open") is not None:
        bits.append(f'{esc(stats["open"])} open pick{"" if stats["open"] == "1" else "s"}')
    if stats.get("label"):
        bits.append(f'{esc(stats["wl"])} {esc(stats["label"])}')
    lede = f'<p class="sm mut dm-line">{" · ".join(bits)}</p>' if bits else ""
    scope_html = f'<p class="scope">{scope.group(1)}</p>' if scope else ""
    return (f'<details class="fold sec dm-sec"><summary><h2 class="dm-title">{esc(label)}</h2>'
            f'<span class="mut sm">· {esc(sum_line(stats))}</span></summary>\n{scope_html}{lede}\n{body.strip()}\n</details>')


def summary_tiles(entries):
    """One tile per section, in page order: win % big, then the W–L and the return. Each opens its section."""
    out = []
    for anchor, label, stats in entries:
        pct = win_pct(stats.get("won"), stats.get("lost"))
        sub = " · ".join(x for x in (stats.get("wl") if pct else None, f'{stats["roi"]} return' if pct and stats.get("roi") else None) if x)
        out.append(f'<a class="tile" href="#{anchor}"><b>{pct or "—"}</b><span>{esc(label)}</span>'
                   f'<span class="sub sm">{esc(sub) if sub else "no settled bets yet"}</span></a>')
    return f'<div class="tiles tiles5" id="dm-summary">{"".join(out)}</div>'


def swing15_html():
    """The 15-Minute Swing section (swing15_build.py, 2026-11-08), first on the tab. Never breaks the page."""
    try:
        import swing15_build
        inner = swing15_build.section()
    except Exception as exc:                                    # noqa: BLE001
        inner = (f'<h2 class="dm-title">15-Minute Swing</h2>'
                 f'<p class="sm mut">This section could not be built ({esc(type(exc).__name__)}).</p>')
    stats = swing15_stats(inner)
    m = re.match(r'\s*<h2 class="dm-title">(.*?)</h2>', inner, re.S)
    title = _text(m.group(1)) if m else "15-Minute"
    rest = inner[m.end():] if m else inner
    shell = (f'<details class="fold sec dm-sec"><summary><h2 class="dm-title">{esc(title)}</h2>'
             f'<span class="mut sm">· paper · {esc(sum_line(stats))}</span></summary>\n{rest.strip()}\n</details>')
    swing15_html.stats = stats
    return f'<section id="swing15" class="dm-group" data-sp-group="swing15">\n{shell}\n</section>'


def econ_weekly_html():
    """The Econ weekly block (jobless_build.py, 2026-11-11), at the end of the Econ section. Never breaks the page."""
    try:
        import jobless_build
        return ('\n<details class="fold dm-weekly"><summary>Econ weekly</summary>' + jobless_build.section().replace("<h3>Econ weekly</h3>", "", 1) + "</details>")
    except Exception as exc:                                    # noqa: BLE001
        return (f'\n<section id="econ-weekly"><h3>Econ weekly</h3>'
                f'<p class="sm mut">This block could not be built ({esc(type(exc).__name__)}).</p></section>')


def body_html(parts):
    links = " · ".join(f'<a href="#{g}">{esc(label)}</a>' for g, label, _f in GROUPS)
    sw = swing15_html()
    entries = [("swing15", "15-Minute", getattr(swing15_html, "stats", dict(won=None, lost=0, wl="", roi=None)))]
    shells = []
    for g, label, _f in GROUPS:
        stats = group_stats(parts[g])
        # One basis for every tile (2026-11-11): the running rules added up as their rows below count them, Production and Sandbox
        # together. The builders' own tiles mix bases (since Production for Crypto, Econ and Finance; the Sandbox record for Commodities).
        rs = rules_stats(parts[g], g)
        if rs:
            stats.update(won=rs["won"], lost=rs["lost"], wl=rs["wl"], roi=rs["roi"], rules=rs["rules"], label="together")
        entries.append((g, label, stats))
        shells.append(f'<section id="{g}" class="dm-group" data-sp-group="{g}">\n{section_shell(g, label, parts[g], stats)}\n</section>')
    out = [f'<h1>{TITLE}</h1>\n<p class="lede">Kalshi daily-close ladders, one closed section per group: {links}. '
           f'Each tile adds up the section\'s running rules, Production and Sandbox, as their rows below count them (a market-day or an event is one bet); '
           f'the return is the average per bet after fees. Paper unless a row says Production.</p>',
           summary_tiles(entries), sw] + shells
    out.append(f"<footer>{esc(_foot())}</footer>")
    return "\n".join(out) + "\n"


def _foot():
    import sport_page
    return sport_page.FOOT


def build(now=None, builders=None):
    now = now or datetime.datetime.now(datetime.timezone.utc)
    builders = builders or _builders()
    parts = {}
    for g, label, _f in GROUPS:
        try:
            parts[g] = scoped_body(builders[g](now), g)
            if g == "econ":
                parts[g] += econ_weekly_html()
        except Exception as exc:                                # noqa: BLE001  one group never takes the page down
            parts[g] = (f'<h2 class="dm-title">{esc(label)}</h2>'
                        f'<p class="sm mut">This section could not be built ({esc(type(exc).__name__)}).</p>')
    import sandbox_build as B
    html = C.document(
        f"{C.SITE_NAME} · {TITLE}",
        "Kalshi daily-close ladder lanes in one tab: crypto, commodities, econ and finance, each rule's record per market-day.",
        KEY, (("swing15", "15-Minute"),) + tuple((g, label) for g, label, _f in GROUPS), C.stamp(now), body_html(parts),
        script_src="./site.js", scripts=("./tables.js",), sports=True)
    return B.label_cells(html)


def redirect_page(group, label, old_file):
    """A moved page: sends the old URL to its anchor on Daily Markets. Same CSP as every page; no script."""
    target = f"./daily_markets.html#{group}"
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(C.title_for(label))} · moved to {TITLE}</title>
<meta http-equiv="refresh" content="0; url={esc(target)}">
<link rel="canonical" href="{esc(C.SITE_URL + 'daily_markets.html#' + group)}">
<meta name="robots" content="noindex">
{C.CSP}
{C.REFERRER}
{C.COLOR_SCHEME}
<link rel="stylesheet" href="./site.css">
<link rel="icon" href="./favicon.svg" type="image/svg+xml">
</head>
<body>
<main id="content" class="wrap">
<h1>{esc(label)} moved</h1>
<p class="lede">{esc(label)} is now a section of <a href="{esc(target)}">{TITLE}</a>. This page ({esc(old_file)}) forwards there.</p>
</main>
</body>
</html>
"""


def write(now=None, out_dir=None):
    out_dir = out_dir or os.path.dirname(OUT)
    paths = []
    page = build(now)
    path = os.path.join(out_dir, "daily_markets.html")
    with open(path + ".tmp", "w") as f:
        f.write(page)
    os.replace(path + ".tmp", path)
    paths.append(path)
    for g, label, old in GROUPS:
        p = os.path.join(out_dir, old)
        with open(p + ".tmp", "w") as f:
            f.write(redirect_page(g, label, old))
        os.replace(p + ".tmp", p)
        paths.append(p)
    return paths


if __name__ == "__main__":
    for p in write():
        print("wrote", p)
