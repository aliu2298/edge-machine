"""The Trading page's row layout (2026-11-06): one row per lane, details in a fold, the Econ Daily design.

Each lane is a <details class="sp-rule"> whose summary is one .sp-line on the shared seven tracks
(name, venue, settled, win, avg net, t, status); everything else sits in the fold. No loose text.
"""
import html as _h

HEAD = ("Rule", "Venue", "Settled", "Win", "Avg net", "t", "Status")


def esc(x):
    return _h.escape(str(x))


def _cells(values):
    name, rest = values[0], values[1:]
    out = [f'<span class="sp-cell sp-c-name">{name}</span>']
    for i, (label, v) in enumerate(zip(HEAD[1:], rest)):
        cls = "sp-cell sp-c-market" if i == 0 else ("sp-cell sp-c-verdict" if label == "Status" else "sp-cell num")
        out.append(f'<span class="{cls}" data-l="{esc(label)}">{v}</span>')
    return "".join(out)


def head_line(first="Rule"):
    cells = "".join(
        f'<span class="sp-cell{" sp-c-name" if i == 0 else " sp-c-market" if i == 1 else " sp-c-verdict" if h == "Status" else " num"}">{esc(first if i == 0 else h)}</span>'
        for i, h in enumerate(HEAD))
    return f'<div class="sp-line sp-head-line" aria-hidden="true">{cells}</div>'


def rule(key, name, venue, settled, win, net, t, status, body, badges="", muted=False):
    """One lane row. `name` and `body` are escaped by the caller where needed; the rest are short html."""
    title = f'<span class="sp-chev" aria-hidden="true">›</span><b class="sp-name" title="{esc(name)}">{esc(name)}</b>'
    if badges:
        title += f'<span class="sp-badges">{badges}</span>'
    title += '<span class="sr-only"> · Rule details</span>'
    cls = "sp-rule is-early" if muted else "sp-rule"
    return (f'<details class="{cls}" data-source="{esc(key)}"><summary class="sp-line">'
            f'{_cells([title, esc(venue), settled, win, net, t, status])}</summary>'
            f'<div class="sp-details-body">{body}</div></details>')


def rules_list(rows, first="Rule", key="rules"):
    return f'<div class="sp-rules-list" data-list="{esc(key)}">{head_line(first)}{"".join(rows)}</div>'


def params(pairs):
    """A definition list: [(term, html)]."""
    return '<dl class="sp-params">' + "".join(f"<dt>{esc(k)}</dt><dd>{v}</dd>" for k, v in pairs) + "</dl>"


def fold(summary, inner, cls="fold"):
    return f'<details class="{cls}"><summary>{summary}</summary>{inner}</details>'


def sig(text, tone="n"):
    """A status pill: y (paying), w (watch / review due), n (collecting), x (retired / no edge)."""
    return f'<span class="sig {tone}">{esc(text)}</span>'


def section(sid, title, count_line, inner):
    return (f'<section id="{esc(sid)}" class="sp-section"><div class="sp-section-head"><h2>{esc(title)}</h2>'
            f'<span class="sm mut">{count_line}</span></div>{inner}</section>')
