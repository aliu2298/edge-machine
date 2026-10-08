"""Presentation helpers for sport-page disclosures. No ledger or model operations."""
import site_chrome as C


def disclosure(title, content, count=None, opened=False, css=""):
    count_html = f'<span>{C.esc(count)}</span>' if count is not None else ""
    return (f'<details class="section-disclosure {C.esc(css)}"{" open" if opened else ""}>'
            f'<summary><b>{C.esc(title)}</b>{count_html}</summary>{content}</details>')
