"""The shared header for every published page.

Sandbox, Production, Trading, NBA, Soccer, Tennis, Cricket, Crypto, the site
root and the archive all call header() through document(). One shell: the
brand (always the site root), the page pills, the stamp, then the per-page
section nav or a breadcrumb. Exactly one link carries aria-current; on the
root that link is the brand. Method points at the method section on the Sandbox.
"""
import html

import fmt

SITE_NAME = "Edge Machine"
SITE_URL = "https://aliu2298.github.io/edge-machine/"

PAGES = (
    ("sandbox", "Overview", "./sandbox.html"),
    ("production", "Production", "./production.html"),
    ("trading", "Trading", "./trading.html"),
    ("nba", "NBA", "./nba.html"),
    ("nfl", "NFL", "./nfl.html"),
    ("soccer", "Soccer", "./soccer.html"),
    ("tennis", "Tennis", "./tennis.html"),
    ("cricket", "Cricket", "./cricket.html"),
    ("crypto", "Crypto", "./crypto.html"),
    ("commodities", "Commodities", "./commodities.html"),
    ("econ_daily", "Econ Daily", "./econ_daily.html"),
    ("finance_daily", "Finance Daily", "./finance_daily.html"),
    ("culture", "Culture", "./culture.html"),
    ("method", "Method", "./sandbox.html#method"),
)
SPORT_KEYS = ("nba", "nfl", "soccer", "tennis", "cricket", "crypto", "commodities")
# The file each page key is published as, for the canonical and og:url tags.
PAGE_FILES = {
    "index": "index.html",
    "sandbox": "sandbox.html",
    "production": "production.html",
    "trading": "trading.html",
    "nba": "nba.html",
    "nfl": "nfl.html",
    "soccer": "soccer.html",
    "tennis": "tennis.html",
    "cricket": "cricket.html",
    "crypto": "crypto.html",
    "commodities": "commodities.html",
    "econ_daily": "econ_daily.html",
    "finance_daily": "finance_daily.html",
    "culture": "culture.html",
}

# Fixed-width segmented control. The label is the current choice (aria-pressed),
# not the choice you would switch to. It lives in the table tools, not the header.
VIEW_TOGGLE = (
    '<div id="vw" class="view-toggle" role="group" aria-label="Layout">'
    '<button type="button" data-view="cards" aria-pressed="false">Cards</button>'
    '<button type="button" data-view="table" aria-pressed="true">Table</button>'
    '</div>'
)


def esc(x):
    return html.escape(str(x))


def _root(prefix):
    """'./' or '../'. A missing prefix is the site root, same as './'."""
    if not prefix:
        return "./"
    if not prefix.endswith("/"):
        prefix += "/"
    return prefix


def _href(path, prefix):
    """Rewrite a './' link for a page that lives in a subdirectory."""
    root = _root(prefix)
    if path.startswith("./"):
        return root + path[2:]
    return path


# Same-origin only. No inline script, no inline style, no third-party host.
CSP = (
    '<meta http-equiv="Content-Security-Policy" content="default-src \'self\'; '
    'script-src \'self\'; style-src \'self\'; img-src \'self\' data:; '
    'base-uri \'none\'; form-action \'none\'">'
)
REFERRER = '<meta name="referrer" content="no-referrer">'
# Both themes are drawn; the device's own preference picks one, the toggle the other.
COLOR_SCHEME = '<meta name="color-scheme" content="dark light">'


def title_for(page):
    """'Edge Machine · <Page>'. A title already in that form is kept."""
    text = str(page or "").strip()
    if not text:
        return SITE_NAME
    if text == SITE_NAME or text.startswith(SITE_NAME + " · "):
        return text
    return f"{SITE_NAME} · {text}"


# The market pages sit in one "Markets" menu from 641px up (2026-10-16): thirteen pills had
# wrapped onto two rows at 1280px and four on a tablet. Every link stays in nav.main in the same
# order, so the phone's single swipe row (site.css, max-width 640px) still shows each one inline.
MARKET_GROUP = ("nba", "nfl", "soccer", "tennis", "cricket", "crypto", "commodities",
                "econ_daily", "finance_daily", "culture")


def nav(active, prefix="./"):
    """One link per page, with aria-current on exactly one.

    The site root ("index") is the brand, not a pill, so no pill is current there. The
    market pages are wrapped in a menu whose button names the current one, if any.
    """
    parts, group = [], []
    current = 0
    for key, label, href in PAGES:
        attr = ""
        if key == active:
            attr = ' aria-current="page"'
            current += 1
        link = f'<a href="{esc(_href(href, prefix))}"{attr}>{esc(label)}</a>'
        if key in MARKET_GROUP:
            group.append(link)
            if len(group) == len(MARKET_GROUP):
                here = next((lbl for k, lbl, _h in PAGES if k == active and k in MARKET_GROUP), None)
                parts.append(
                    f'<span class="nav-group{" is-current" if here else ""}">'
                    f'<button type="button" class="nav-more" aria-expanded="false" aria-controls="nav-markets">'
                    f'{esc(here or "Markets")}<span class="nav-caret" aria-hidden="true"></span></button>'
                    f'<span class="nav-menu" id="nav-markets">{"".join(group)}</span></span>')
            continue
        parts.append(link)
    expected = 0 if active == "index" else 1
    if current != expected:
        raise ValueError(f"aria-current must mark {expected} page, got {current} for {active!r}")
    return f'<nav class="main" aria-label="Pages">{"".join(parts)}</nav>'


def toc(sections):
    """In-page section links. `sections` is (id, label) pairs.

    A single link is the page's own heading, not a nav, so it is left out.
    """
    if not sections or len(tuple(sections)) < 2:
        return ""
    links = "".join(f'<a href="#{esc(i)}">{esc(label)}</a>' for i, label in sections)
    return f'<nav class="toc" aria-label="On this page">{links}</nav>'


def breadcrumb(parts):
    """A short trail. `parts` is (label, href or None); the last item is not a link.

    The current crumb carries aria-current. nav.main still marks exactly one page.
    """
    if not parts:
        return ""
    bits = []
    for label, href in parts:
        if bits:
            bits.append('<span class="sep" aria-hidden="true">›</span>')
        if href:
            bits.append(f'<a href="{esc(href)}">{esc(label)}</a>')
        else:
            bits.append(f'<span class="here" aria-current="page">{esc(label)}</span>')
    return f'<nav class="crumbs" aria-label="Breadcrumb">{"".join(bits)}</nav>'


def stamp(when, machine=True):
    """Visible CT time. Sandbox and Production also carry the tracker UTC stamp."""
    visible = fmt.display_updated(when)
    body = f'<time datetime="{esc(fmt.iso_z(when))}">{esc(visible)}</time>'
    if machine:
        # Lower-case "updated YYYY-MM-DD HH:MM UTC" is what page_freshness reads.
        # The shell leaves this off so a check pointed at the root fails closed.
        body += f'<span class="sr-only">{esc(fmt.machine_stamp(when))}</span>'
    return body


def header(active, sections, stamp_html, tools="", prefix="./", crumb=None):
    """Brand, main nav and stamp, then the section nav or a breadcrumb.

    `tools` is accepted so older callers keep working, and ignored. The view
    toggle sits next to the table search, not in this bar.
    """
    del tools
    below = [part for part in (
        breadcrumb(crumb) if crumb else "",
        toc(sections),
    ) if part]
    # The second row: the section nav or the breadcrumb, and the theme toggle
    # at its right end. The toggle lives here, not in the top bar, so the ten
    # page pills keep their room beside the brand and the stamp, and a phone's
    # scrolling pill row keeps its full width.
    sub = ("\n" + "\n".join(below)) if below else ""
    toggle = ('<button type="button" class="theme-toggle" data-theme-toggle '
              'aria-label="Switch theme" title="Switch between the light and dark theme">Theme</button>')
    brand_current = ' aria-current="page"' if active == "index" else ""
    return f"""<a class="skip" href="#content">Skip to content</a>
<header class="site">
<div class="topbar">
<a class="brand" href="{esc(_href("./index.html", prefix))}"{brand_current}>Edge Machine</a>
{nav(active, prefix)}
<p class="stamp">{stamp_html}</p>
</div>
<div class="subbar">{sub}
{toggle}
</div>
</header>"""


def sports_header(active, stamp_html, prefix="./"):
    """The sport pages used to carry a third header. They use the one shell now."""
    return header(active, (), stamp_html, prefix=prefix)


def head_meta(title, description, active, prefix="./"):
    """Icon, canonical, Open Graph and Twitter cards. Same-origin assets only."""
    icon = esc(_href("./favicon.svg", prefix))
    parts = [
        f'<link rel="icon" href="{icon}" type="image/svg+xml">',
        f'<link rel="apple-touch-icon" href="{icon}">',
        f'<meta property="og:site_name" content="{esc(SITE_NAME)}">',
        '<meta property="og:type" content="website">',
        f'<meta property="og:title" content="{esc(title)}">',
        f'<meta property="og:description" content="{esc(description)}">',
        '<meta name="twitter:card" content="summary">',
        f'<meta name="twitter:title" content="{esc(title)}">',
        f'<meta name="twitter:description" content="{esc(description)}">',
    ]
    file = PAGE_FILES.get(active)
    if file and _root(prefix) == "./":
        url = SITE_URL + ("" if file == "index.html" else file)
        parts.insert(2, f'<link rel="canonical" href="{esc(url)}">')
        parts.append(f'<meta property="og:url" content="{esc(url)}">')
    return "\n".join(parts)


def document(title, description, active, sections, stamp_html, body,
             script_src=None, extra_head="", tools="", scripts=None, prefix="./",
             crumb=None, sports=False, body_class=""):
    srcs = []
    if script_src:
        srcs.append(script_src)
    for src in scripts or ():
        if src not in srcs:
            srcs.append(src)
    # Sticky column headers read --hdr-h from tables.js. Pages that already
    # pass the script keep their order; the rest gain it. Production stays on
    # tables.js alone: that file also scrolls the active phone-nav pill.
    if "./tables.js" not in srcs:
        srcs.append("./tables.js")
    if sports:
        srcs.append("./sports.js")
    script = "".join(
        f'\n<script src="{esc(_href(src, prefix))}"></script>' for src in srcs)
    extra = f"\n{extra_head}" if extra_head else ""
    title = title_for(title)
    classes = []
    if sports:
        classes.append(f"sports-page sport-{esc(active)}")
    if body_class:
        classes.append(esc(body_class))
    body_attr = f' class="{" ".join(classes)}"' if classes else ""
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)}</title>
<meta name="description" content="{esc(description)}">
<link rel="stylesheet" href="{esc(_href("./site.css", prefix))}">
{head_meta(title, description, active, prefix)}
{CSP}
{REFERRER}
{COLOR_SCHEME}{extra}
</head>
<body{body_attr}>
{header(active, sections, stamp_html, tools=tools, prefix=prefix, crumb=crumb)}
<main id="content" class="wrap">
{body}
</main>{script}
</body>
</html>
"""
