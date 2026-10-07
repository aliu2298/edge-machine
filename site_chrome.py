"""The shared header for every published page.

Sandbox, Production, Trading, NBA, Soccer, Tennis, Cricket, and the site root
all call header(). Exactly one link carries aria-current. Method points at the
method section on the Sandbox.
"""
import html

import fmt

PAGES = (
    ("sandbox", "Sandbox", "./sandbox.html"),
    ("production", "Production", "./production.html"),
    ("trading", "Trading", "./trading.html"),
    ("nba", "NBA", "./nba.html"),
    ("soccer", "Soccer", "./soccer.html"),
    ("tennis", "Tennis", "./tennis.html"),
    ("cricket", "Cricket", "./cricket.html"),
    ("crypto", "Crypto", "./crypto.html"),
    ("method", "Method", "./sandbox.html#method"),
)

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


def nav(active, prefix="./"):
    """One link per page, with aria-current on exactly one."""
    parts = []
    current = 0
    for key, label, href in PAGES:
        attr = ""
        if key == active:
            attr = ' aria-current="page"'
            current += 1
        parts.append(f'<a href="{esc(_href(href, prefix))}"{attr}>{esc(label)}</a>')
    if current != 1:
        raise ValueError(f"aria-current must mark one page, got {current} for {active!r}")
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
            bits.append('<span class="sep" aria-hidden="true">\u203a</span>')
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
    sub = ("\n" + "\n".join(below)) if below else "\n"
    return f"""<a class="skip" href="#content">Skip to content</a>
<header class="site">
<div class="topbar">
<a class="brand" href="{esc(_href("./sandbox.html", prefix))}">Edge Machine</a>
{nav(active, prefix)}
<p class="stamp">{stamp_html}</p>
</div>{sub}
</header>"""


def document(title, description, active, sections, stamp_html, body,
             script_src=None, extra_head="", tools="", scripts=None, prefix="./",
             crumb=None):
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
    script = "".join(
        f'\n<script src="{esc(_href(src, prefix))}"></script>' for src in srcs)
    extra = f"\n{extra_head}" if extra_head else ""
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)}</title>
<meta name="description" content="{esc(description)}">
<link rel="stylesheet" href="{esc(_href("./site.css", prefix))}">
{CSP}
{REFERRER}{extra}
</head>
<body>
{header(active, sections, stamp_html, tools=tools, prefix=prefix, crumb=crumb)}
<main id="content" class="wrap">
{body}
</main>{script}
</body>
</html>
"""
