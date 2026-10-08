"""Presentation helpers for sport-page disclosures. No ledger or model operations."""
import site_chrome as C


def disclosure(title, content, count=None, opened=False, css=""):
    count_html = f'<span>{C.esc(count)}</span>' if count is not None else ""
    return (f'<details class="section-disclosure {C.esc(css)}"{" open" if opened else ""}>'
            f'<summary><b>{C.esc(title)}</b>{count_html}</summary>{content}</details>')


def rule_tiles(a, label, floor):
    """Two stat tiles for ONE rule: its W–L record and its ROI after fees.

    `a` is the Sandbox row's own record. The ROI is grey under `floor` settled
    bets. A page with several rules shows each rule's own figures; nothing here
    pools a record or an ROI across rules, because a pooled ROI across different
    contracts is not a number any rule earned.
    """
    import fmt
    n = int(a.get("n") or 0)
    won = int(a.get("won") or 0)
    rec = f"{won}\u2013{n - won}" if n else "\u2014"
    roi = a.get("roi_fee")
    if n and roi is not None:
        klass = "mut" if n < floor else fmt.tone(roi, ".1f", 100)
        roi_html = f'<b class="{klass}">{fmt.pct(roi, digits=1, sign=True)}</b>'
    else:
        roi_html = '<b class="mut">\u2014</b>'
    name = C.esc(label)
    return (f'<div class="tile"><b>{rec}</b><span>{name} \u00b7 W\u2013L</span></div>'
            f'<div class="tile">{roi_html}<span>{name} \u00b7 ROI after fees</span></div>')
