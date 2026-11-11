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


def swing15_html():
    """The 15-Minute Swing section (swing15_build.py, 2026-11-08), first on the tab. Never breaks the page."""
    try:
        import swing15_build
        inner = swing15_build.section()
    except Exception as exc:                                    # noqa: BLE001
        inner = (f'<h2 class="dm-title">15-Minute Swing</h2>'
                 f'<p class="sm mut">This section could not be built ({esc(type(exc).__name__)}).</p>')
    return f'<section id="swing15" class="dm-group" data-sp-group="swing15">\n{inner}\n</section>'


def econ_weekly_html():
    """The Econ weekly block (jobless_build.py, 2026-11-11), at the end of the Econ section. Never breaks the page."""
    try:
        import jobless_build
        return "\n" + jobless_build.section()
    except Exception as exc:                                    # noqa: BLE001
        return (f'\n<section id="econ-weekly"><h3>Econ weekly</h3>'
                f'<p class="sm mut">This block could not be built ({esc(type(exc).__name__)}).</p></section>')


def body_html(parts):
    links = " · ".join(f'<a href="#{g}">{esc(label)}</a>' for g, label, _f in GROUPS)
    out = [f'<h1>{TITLE}</h1>\n<p class="lede">Kalshi daily-close ladders, one section per group: {links}. '
           f'Every rule keeps its own record, stage and folds. Paper unless a row says Production.</p>',
           swing15_html()]
    for g, label, _f in GROUPS:
        out.append(f'<section id="{g}" class="dm-group" data-sp-group="{g}">\n{parts[g]}\n</section>')
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
