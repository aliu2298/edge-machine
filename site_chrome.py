"""The shared header for every published page.

Sandbox, Production, Trading, and the site root all call header(). Exactly one
link carries aria-current. Method points at the method section on the Sandbox.
"""
import html

import fmt

PAGES = (
    ("sandbox", "Sandbox", "./sandbox.html"),
    ("production", "Production", "./production.html"),
    ("trading", "Trading", "./trading.html"),
    ("method", "Method", "./sandbox.html#method"),
)

VIEW_BUTTON = (
    '<button type="button" id="vw" class="vw" '
    'title="Switch between the phone layout and the full table">Phone view</button>'
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
    """The four links, with aria-current on exactly one."""
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
    """In-page section links. `sections` is (id, label) pairs."""
    if not sections:
        return ""
    links = "".join(f'<a href="#{esc(i)}">{esc(label)}</a>' for i, label in sections)
    return f'<nav class="toc" aria-label="On this page">{links}</nav>'


def stamp(when, machine=True):
    """Visible CT time. Sandbox and Production also carry the tracker UTC stamp."""
    visible = fmt.display_updated(when)
    body = f'<time datetime="{esc(fmt.iso_z(when))}">{esc(visible)}</time>'
    if machine:
        # Lower-case "updated YYYY-MM-DD HH:MM UTC" is what page_freshness reads.
        # The root stub leaves this off so a check pointed at it fails closed.
        body += f'<span class="sr-only">{esc(fmt.machine_stamp(when))}</span>'
    return body


def header(active, sections, stamp_html, tools="", prefix="./"):
    tool = f"{tools}" if tools else ""
    return f"""<a class="skip" href="#content">Skip to content</a>
<header class="site">
<div class="topbar">
<a class="brand" href="{esc(_href("./sandbox.html", prefix))}">Edge Machine</a>
{nav(active, prefix)}
{tool}
<p class="stamp">{stamp_html}</p>
</div>
{toc(sections)}
</header>"""


def document(title, description, active, sections, stamp_html, body,
             script_src=None, extra_head="", tools="", scripts=None, prefix="./"):
    srcs = []
    if script_src:
        srcs.append(script_src)
    for src in scripts or ():
        if src not in srcs:
            srcs.append(src)
    # Sticky column headers read --hdr-h from tables.js. Pages that already
    # pass the script keep their order; the rest gain it.
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
{header(active, sections, stamp_html, tools=tools, prefix=prefix)}
<main id="content" class="wrap">
{body}
</main>{script}
</body>
</html>
"""
