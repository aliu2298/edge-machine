#!/usr/bin/env python3
"""One template for every sport page (redesign, phase 3).

Head, one scope line, four tiles; a filter row whose scope and stage chips drive
the rules and the events together; the Production rules as one compact list, a
row per rule (name, badges, market, record, ROI after fees, won v priced,
evidence n/30, verdict), the first few shown and the rest folded; the Sandbox
rules in the same rows inside a closed fold, sorted by evidence, the too-early
rows greyed and sunk; the events in three tabs, Next 24h, In progress and
Completed (14 days), each empty state saying why; the method folded.

No prose on load. A rule's definition, registration, parameters, dated changes
and recent picks sit in its row's closed "Rule details" fold; nothing in the
Rules section is a sentence until a reader opens one.

Presentation only. Every number is the ledger's own, read through sandbox_build
(pair_list rows, VERDICTS, MIN_N, EARLY_N), sandbox_track (assess, record_text)
and production (the since-Production window, the Early badge). Each sport hands
the template a spec: its rows, the events its rules own, how a rule is named and
defined, and the text of its method fold. Nothing here grades, settles, or
chooses a bet.
"""
import datetime
import re
from datetime import timedelta, timezone

import fmt
import production
import sandbox_build as B
import sandbox_sources as S
import sandbox_track as T
import site_chrome as C

# The events tabs.
NEXT_H = 24
DONE_DAYS = 14
EVIDENCE_FLOOR = T.READ_FLOOR      # "Evidence 4/30"
TOO_EARLY_N = B.EARLY_N            # under this many settled, a Sandbox row is too early
# The verdicts a Sandbox row carries while it has too little to say. Phase 4
# owns the vocabulary; this file only reads it.
EARLY_VERDICTS = ("early", "waiting", "nobets")

TOC = (("rules", "Rules"), ("events", "Events"), ("method", "Method"))
SCOPE_KEYS = {"": "clubs", "_cup": "cups", "_intl": "intl"}
SCOPE_WORDS = {"clubs": S.CLUB_SCOPE_LABEL, "cups": S.SCOPE_LABEL["_cup"], "intl": S.SCOPE_LABEL["_intl"]}
FOOT = "Read-only static export · rebuilt by GitHub Actions · research, not betting advice."
_FAR = datetime.datetime.max.replace(tzinfo=timezone.utc)


def esc(x):
    return C.esc("" if x is None else x)


def as_utc(now):
    if now is None:
        return datetime.datetime.now(timezone.utc)
    if now.tzinfo is None:
        return now.replace(tzinfo=timezone.utc)
    return now.astimezone(timezone.utc)


def instant(raw):
    """A stored timestamp as a UTC instant, or None when it cannot be read."""
    if not raw:
        return None
    try:
        return fmt.chicago(raw).astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError, OSError):
        return None


# ------------------------------------------------------------------ the spec
def spec(**kw):
    """The page description a sport hands the template.

    family, key, title, description, scope: the words. rows: the Sandbox rows
    (sport_tab.family_rows). events(d, rows, now) -> [event]. rule_name(row),
    definition(d, row) -> html, recent(d, row, now) -> html, market(d, row) -> str,
    unit(row) -> 'bet' | 'market-day'. method(d, rows, now) -> (label, hint, html,
    open). venue: the venue word the empty states name. open_picks(d, rows) ->
    int, or None to count the events' open picks. scoped: whether the scope chips
    are drawn when the rows span more than one scope.
    """
    out = dict(
        family="", key="", title="", description="", scope="", venue="Kalshi",
        rule_name=B.rule_name, definition=default_definition, recent=None,
        market=None, unit=lambda row: str((row.get("a") or {}).get("unit") or "bet"),
        method=None, open_picks=None, scoped=True, events=lambda d, rows, now: [],
        extra_rows=lambda d, rows: [],
    )
    out.update(kw)
    return out


def event(when, label, picks, href=None, sub="", key=None):
    """One contest (or one market-day) and the picks the rules have on it."""
    return dict(when=when, label=label, href=href, sub=sub, picks=list(picks),
                key=key or (when.isoformat() if when else "", label))


def pick(row, q, text, state, price=None, legs="", href=None, status=None, settled=None):
    """One rule's position on an event.

    `state` is open / watch / won / lost / void / price. `settled` is the
    settlement instant for a settled pick with no readable start.
    """
    return dict(row=row, q=q, text=text, state=state, price=price, legs=legs,
                href=href if href is not None else (S.market_url(q) if q else None),
                status=status, settled=settled)


# ------------------------------------------------------------------ words
def scope_key(row):
    return SCOPE_KEYS.get(B._scope(row.get("sport") or ""), "clubs")


def stage_key(row):
    return "production" if row.get("prod") else "sandbox"


def is_early(row):
    """A Sandbox row with too little settled to read: greyed and sunk in the table."""
    a = row.get("a") or {}
    return row.get("v") in EARLY_VERDICTS or int(a.get("n") or 0) < TOO_EARLY_N


# ------------------------------------------------------------------ the verdict
# One vocabulary on every page, read off the evidence ladder:
#   Too early            under TOO_EARLY_N settled (no result yet included)
#   Collecting n/30 · Promising | Behind
#                        TOO_EARLY_N up to the read floor, with the lean so far
#   Working | No edge | Proven
#                        at the read floor and over
# The grading is sandbox_build.verdict(), unchanged; only the words are here.
# Removed, Retired and Fails BUILD are not points on the ladder: they say what
# happened to the rule, so they keep their own words.
VERDICT_WORDS = {               # key -> (word, chip class)
    "proven": ("Proven", "y"),
    "working": ("Working", "y"),
    "noedge": ("No edge", "x"),
    "promising": ("Promising", "w"),
    "behind": ("Behind", "n"),
    "early": ("Too early", "n"),
    "waiting": ("Too early", "n"),
    "nobets": ("Too early", "n"),
    "removed": ("Removed from Production", "x"),
    "retired": ("Retired", "x"),
    "build_fail": ("Fails BUILD", "x"),
}
COLLECTING = ("promising", "behind")


def verdict_label(key, n=0, floor=EVIDENCE_FLOOR):
    """(text, chip) for a verdict key at n settled units: 'Collecting 14/30 · Promising'."""
    word, chip = VERDICT_WORDS.get(key, (str(key), "n"))
    if key in COLLECTING and n:
        return f"Collecting {int(n)}/{int(floor)} · {word}", chip
    return word, chip


def verdict_text(row, floor=EVIDENCE_FLOOR):
    """The verdict words alone, for a place that prints text, not a chip."""
    return verdict_label(row["v"], (row.get("a") or {}).get("n") or 0, floor)[0]


def verdict_badge(row, floor=EVIDENCE_FLOOR):
    """The verdict chip every page prints: the Sandbox and sport tables, the rule
    cards, the trading table and the Control Center's scorecard. `row` needs "v"
    and, for the Collecting count, "a" with "n"; `floor` is the read floor of the
    row's own unit (30 settled, or 30 entry days on the trading lane)."""
    text, chip = verdict_label(row["v"], (row.get("a") or {}).get("n") or 0, floor)
    return f'<span class="sig {chip}" data-verdict="{esc(row["v"])}">{esc(text)}</span>'


COMBO_SPORTS = ("tennis_combo", "tennis_pmcombo")


def settled_unit(row):
    """What one settled count is for this rule: a market-day where a day's ladder
    is one result (crypto, commodities), a match for the corners ladder, a basket
    for a combo, a bet otherwise. The count itself is assess()'s n."""
    unit = (row.get("a") or {}).get("unit")
    if unit in ("market-day", "match"):
        return unit
    if B._base_sport(row.get("sport") or "") in COMBO_SPORTS:
        return "basket"
    return "bet"


def unit_count(n, unit):
    """'1 bet', '12 market-days', '3 matches', '4 baskets'."""
    n = int(n or 0)
    if n == 1:
        return f"1 {unit}"
    return f"{n} {unit}{'es' if unit == 'match' else 's'}"


def roi_html(row, grey_under=B.MIN_N):
    a = row["a"]
    if not a.get("n"):
        return '<span class="mut">—</span>'
    klass = "mut" if a["n"] < grey_under else fmt.tone(a["roi_fee"], ".1f", 100)
    return f'<span class="{klass}">{B.pct(a["roi_fee"], sign=True)}</span>'


def won_v_priced(a):
    """'4 v 3.5': wins against the wins the prices implied, or a dash."""
    if not a.get("n"):
        return "—"
    return f'{int(a.get("won") or 0)} v {float(a.get("expected") or 0):.1f}'


def evidence(a):
    return f'{int(a.get("n") or 0)}/{EVIDENCE_FLOOR}'


# A rule's definition is its registration, verbatim. It is only ever drawn inside
# the rule's closed "Rule details" fold: the page shows numbers on load, never prose.
def definition_html(note, extra_class=""):
    """The registered definition as one paragraph, for inside a closed fold."""
    text = " ".join(str(note or "").split())
    if not text:
        return '<p class="sp-def mut">No registered description.</p>'
    return f'<p class="sp-def{(" " + extra_class) if extra_class else ""}">{esc(text)}</p>'


def default_definition(d, row):
    return definition_html(row["meta"].get("note"))


def stage_badges(row):
    """Production (with its Early count), Frozen, Combo: the chips beside a name."""
    bits = []
    if row.get("prod"):
        bits.append('<span class="badge stage production">Production</span>' + production.early_html(row.get("early")))
    else:
        bits.append('<span class="badge stage">Sandbox</span>')
    frozen = row["meta"].get("frozen")
    if frozen:
        bits.append(f'<span class="badge stage">Frozen {esc(frozen)}</span>')
    if B._base_sport(row.get("sport") or "") in ("tennis_combo", "tennis_pmcombo"):
        bits.append('<span class="badge stage">Combo</span>')
    if row.get("gone") or row.get("v") == "retired":
        bits.append('<span class="badge stage">Retired</span>')
    return " ".join(bits)


# ------------------------------------------------------------------ the tiles
def since_production(d, st, rows):
    """One record across this sport's Production rules since each entered, the way the
    Production page's sport line counts it (production._assess_since_kickoff). Pooled
    only across rules in Production, never with a Sandbox row."""
    pairs = (st or {}).get("pairs") or {}
    lives = []
    names = []
    for row in rows:
        if not row.get("prod"):
            continue
        key = f'{row["name"]}|{row["sport"]}'
        pair = pairs.get(key) or {}
        if production.entered_at(pair) is None:
            continue
        lives.append(production._assess_since_kickoff(d, key, pair))
        names.append(row)
    return production._group_record(lives), names


def sandbox_record(rows):
    """One record across this family's live Sandbox rules, for a page with no rule in Production
    (2026-10-20). Each row's own record pooled, so the ROI after fees is the rows' own (per
    contract), and a day-clustered family (crypto, commodities) stays per market-day as its rows
    are. Baselines and retired rows are left out: they are not rules under test."""
    live = [r for r in rows if not r.get("prod") and not r.get("gone") and r.get("v") != "retired"
            and (r.get("meta") or {}).get("kind") != "Baseline"]
    return production._group_record([r["a"] for r in live]), live


def tiles_html(sp, d, st, rows, open_n):
    active = sum(1 for r in rows if (r["a"].get("n") or r["a"].get("n_price") or r.get("open")))
    rec, prod_rows = since_production(d, st, rows)
    if prod_rows:
        who = (sp["rule_name"](prod_rows[0]) if len(prod_rows) == 1
               else f"{len(prod_rows)} rules")
        label = f"since Production · {who}"
        import tennis_cards
        rec_tile = tennis_cards.record_tile(rec, label)
        n = int(rec.get("n") or 0) + int(rec.get("n_price") or 0)
        if n and rec.get("roi_fee") is not None:
            klass = "mut" if int(rec.get("n") or 0) < production.EARLY_N else fmt.tone(rec["roi_fee"], ".1f", 100)
            roi = f'<b class="{klass}">{B.pct(rec["roi_fee"], sign=True)}</b>'
        else:
            roi = '<b class="mut">—</b>'
        roi_tile = f'<div class="tile">{roi}<span>ROI after fees · since Production</span></div>'
    else:
        # No rule in Production: the Sandbox's own record, labelled as paper so Production is
        # never implied. An em dash only when nothing in the Sandbox has settled either.
        import tennis_cards
        rec, live = sandbox_record(rows)
        rec_tile = tennis_cards.record_tile(rec, "Sandbox record · paper")
        n = int(rec.get("n") or 0) + int(rec.get("n_price") or 0)
        if n and rec.get("roi_fee") is not None:
            klass = "mut" if int(rec.get("n") or 0) < production.EARLY_N else fmt.tone(rec["roi_fee"], ".1f", 100)
            roi = f'<b class="{klass}">{B.pct(rec["roi_fee"], sign=True)}</b>'
        else:
            roi = '<b class="mut">—</b>'
        roi_tile = f'<div class="tile">{roi}<span>ROI after fees · Sandbox, paper</span></div>'
    return (
        '<div class="tiles sp-tiles">'
        f'<div class="tile"><b>{open_n}</b><span>open picks</span></div>'
        f'<div class="tile"><b>{active}</b><span>active rules</span></div>'
        f'{rec_tile}{roi_tile}</div>')


# ------------------------------------------------------------------ the filter row
def scopes_present(rows):
    return sorted({scope_key(r) for r in rows}, key=list(SCOPE_WORDS).index)


def filters_html(sp, rows):
    chips = []
    present = scopes_present(rows) if sp["scoped"] else []
    if len(present) > 1:
        parts = ['<button type="button" data-value="all" aria-pressed="true">All</button>']
        parts += [f'<button type="button" data-value="{k}" aria-pressed="false">{esc(SCOPE_WORDS[k])}</button>'
                  for k in present]
        chips.append(f'<nav class="sp-filter" aria-label="Scope" data-filter="scope">{"".join(parts)}</nav>')
    parts = ['<button type="button" data-value="all" aria-pressed="true">All</button>',
             '<button type="button" data-value="production" aria-pressed="false">Production</button>',
             '<button type="button" data-value="sandbox" aria-pressed="false">Sandbox</button>']
    chips.append(f'<nav class="sp-filter" aria-label="Stage" data-filter="stage">{"".join(parts)}</nav>')
    return f'<div class="sp-filters" data-controls="rules events">{"".join(chips)}</div>'


# ------------------------------------------------------------------ the rules
def _open_count(ev_list, row):
    return sum(1 for e in ev_list for p in e["picks"]
               if p["state"] == "open" and p["row"] is row)


# The Production rows shown before the "Show N more" fold. Header, tiles, filters,
# these rows and the folded Sandbox fit one 1366x768 screen with Events below them.
# Leave room for the event tabs when the shared page navigation wraps. A
# crowded rule list keeps every remaining rule in the existing Show more fold.
PROD_VISIBLE = 4


def row_badges(row):
    """The small badges on a rule's row: Early with its count, Frozen, Combo, Retired.
    The stage is the list a row sits in (the Production list, or the Sandbox fold),
    so the row does not repeat it; data-stage carries it for the chips."""
    bits = []
    if row.get("prod") and row.get("early"):
        bits.append(production.early_html(row.get("early")).strip())
    frozen = row["meta"].get("frozen")
    if frozen:
        # A small badge, the date in its tooltip and in the rule's details.
        bits.append(f'<span class="badge stage" title="Frozen {esc(frozen)}">Frozen</span>')
    if B._base_sport(row.get("sport") or "") in COMBO_SPORTS:
        bits.append('<span class="badge stage">Combo</span>')
    if row.get("gone") or row.get("v") == "retired":
        bits.append('<span class="badge stage">Retired</span>')
    return " ".join(bits)


def record_compact(a):
    """'13–8' on the row, with a no-result count as a small tail: '13–8 +6 n/r'."""
    n, n_price, won = int(a.get("n") or 0), int(a.get("n_price") or 0), int(a.get("won") or 0)
    if not n and not n_price:
        return '<span class="mut">—</span>'
    tail = (f' <small class="mut" title="{n_price} no result">+{n_price} n/r</small>' if n_price else "")
    return f"{won}–{max(0, n - won)}{tail}"


def rule_details(sp, d, row, now, ev_list=()):
    """What a rule says in words: its full name and market, the registered definition
    (parameters, registration, dated changes, anything a sport adds), and its recent
    picks. Drawn only inside the row's closed "Rule details" fold."""
    open_n = _open_count(ev_list, row)
    market = sp["market"](d, row) if sp["market"] else ""
    frozen = row["meta"].get("frozen")
    facts = [esc(market)] if market else []
    if frozen:
        facts.append(f"frozen {esc(frozen)}")
    head = (f'<p class="sp-details-name"><b>{esc(sp["rule_name"](row))}</b>'
            f'{" · " + " · ".join(facts) if facts else ""}</p>')
    recent = sp["recent"](d, row, now) if sp["recent"] else ""
    recent_html = (f'<h4 class="sp-details-sub">Recent picks{f" · {open_n} open" if open_n else ""}</h4>{recent}'
                   if recent else "")
    return f'<div class="sp-details-body">{head}{sp["definition"](d, row)}{recent_html}</div>'


def rule_row(sp, d, row, now, scoped, ev_list=()):
    """One rule on one line: name and badges, market, (scope,) record, ROI after fees,
    won v priced, evidence n/30, verdict. The row is the summary of a closed
    <details> named "Rule details"; opening it shows the words."""
    a = row["a"]
    early = (not row.get("prod")) and is_early(row)
    name = sp["rule_name"](row)
    # With a Scope column the name drops its scope suffix ("· Clubs"): the column says it.
    shown_name = name
    if scoped:
        suffix = f" · {SCOPE_WORDS[scope_key(row)]}"
        if shown_name.endswith(suffix):
            shown_name = shown_name[:-len(suffix)]
    market = sp["market"](d, row) if sp["market"] else ""
    scope_cell = (f'<span class="sp-cell sp-c-scope" data-l="Scope">{esc(SCOPE_WORDS[scope_key(row)])}</span>'
                  if scoped else "")
    badges = row_badges(row)
    return (
        f'<details class="sp-rule{" is-early" if early else ""}" data-source="{esc(row["name"])}" '
        f'data-sport="{esc(row["sport"])}" data-scope="{scope_key(row)}" data-stage="{stage_key(row)}"'
        f'{" data-early=\"1\"" if early else ""}>'
        f'<summary class="sp-line{" is-scoped" if scoped else ""}">'
        f'<span class="sp-cell sp-c-name"><span class="sp-chev" aria-hidden="true">›</span>'
        f'<b class="sp-name" title="{esc(name)}">{esc(shown_name)}</b>'
        f'{f"<span class=\"sp-badges\">{badges}</span>" if badges else ""}'
        f'<span class="sr-only"> · Rule details</span></span>'
        f'<span class="sp-cell sp-c-market" data-l="Market">{esc(market) or "—"}</span>{scope_cell}'
        f'<span class="sp-cell num" data-l="Record">{record_compact(a)}</span>'
        f'<span class="sp-cell num" data-l="ROI after fees">{roi_html(row)}</span>'
        f'<span class="sp-cell num" data-l="Won v priced">{esc(won_v_priced(a))}</span>'
        f'<span class="sp-cell num" data-l="Evidence">{esc(evidence(a))}</span>'
        f'<span class="sp-cell sp-c-verdict" data-l="Verdict">{verdict_badge(row)}</span>'
        f'</summary>{rule_details(sp, d, row, now, ev_list)}</details>')


def list_head(scoped, first="Rule"):
    scope = '<span class="sp-cell sp-c-scope">Scope</span>' if scoped else ""
    return (f'<div class="sp-line sp-head-line{" is-scoped" if scoped else ""}" aria-hidden="true">'
            f'<span class="sp-cell sp-c-name">{esc(first)}</span><span class="sp-cell sp-c-market">Market</span>{scope}'
            f'<span class="sp-cell num">Record</span><span class="sp-cell num">ROI after fees</span>'
            f'<span class="sp-cell num">Won v priced</span><span class="sp-cell num">Evidence</span>'
            f'<span class="sp-cell sp-c-verdict">Verdict</span></div>')


def sandbox_order(row):
    """Most evidence first; a too-early row sinks under every read one; retired last."""
    a = row["a"]
    retired = bool(row.get("gone")) or row.get("v") == "retired"
    roi = a["roi_fee"] if a.get("n") and a.get("roi_fee") is not None else float("-inf")
    return (retired, is_early(row), -int(a.get("n") or 0), -roi, sp_name(row))


production_order = sandbox_order


def sp_name(row):
    return B.rule_name(row)


def rules_html(sp, d, rows, now, ev_list):
    prod = sorted((r for r in rows if r.get("prod")), key=production_order)
    sand = sorted((r for r in rows if not r.get("prod")), key=sandbox_order)
    scoped = sp["scoped"] and len(scopes_present(rows)) > 1
    family = esc(sp["family"].lower())
    if prod:
        shown = "".join(rule_row(sp, d, r, now, scoped, ev_list) for r in prod[:PROD_VISIBLE])
        rest = prod[PROD_VISIBLE:]
        more = ""
        if rest:
            more = (f'<details class="fold sp-more-rules"><summary>Show {len(rest)} more Production '
                    f'rule{"s" if len(rest) != 1 else ""}</summary>'
                    f'{"".join(rule_row(sp, d, r, now, scoped, ev_list) for r in rest)}</details>')
        prod_html = (f'<div class="sp-rules-list sp-prod" data-list="production">'
                     f'{list_head(scoped, "Production rule")}{shown}{more}</div>')
    else:
        prod_html = f'<p class="sp-empty" data-empty="production">No {family} rule is in Production.</p>'
    n_early = sum(1 for r in sand if is_early(r))
    if sand:
        body = "".join(rule_row(sp, d, r, now, scoped, ev_list) for r in sand)
        count = f'{len(sand)} rule{"s" if len(sand) != 1 else ""}'
        if n_early:
            count += f' · {n_early} too early to read'
        sand_html = (f'<details class="fold sp-sandbox" id="sandbox"><summary><h3>Sandbox rules</h3>'
                     f'<span class="sm mut">· {esc(count)} · by evidence</span></summary>'
                     f'<div class="sp-rules-list" data-list="sandbox">{list_head(scoped)}{body}</div></details>')
    else:
        sand_html = f'<p class="sp-empty" data-empty="sandbox">No {family} rule is in the Sandbox.</p>'
    count = (f'{len(prod)} in Production · {len(sand)} in the Sandbox' if rows
             else "no rule has a record yet")
    return (f'<section id="rules" class="sp-section">'
            f'<div class="sp-section-head"><h2>Rules</h2><span class="sm mut">{esc(count)}</span></div>'
            f'{prod_html}{sand_html}</section>')


# ------------------------------------------------------------------ the events
STATE_WORD = {"open": ("upcoming", "is-next"), "watch": ("watching", "is-watch"),
              "won": ("W", "is-won"), "lost": ("L", "is-lost"), "void": ("Void", "is-void"),
              "price": (T.NO_RESULT_LABEL, "is-price")}


def pick_state(p, now):
    """(word, class) for one pick on the page clock: in play from the start, unsettled
    with its age past the settler's own flag, W / L / Void / No result once settled."""
    if p["state"] == "open":
        when = instant((p["q"] or {}).get("start"))
        if when is not None and when <= now:
            age = (now - when).total_seconds() / 3600
            if age > T.OVERDUE_H:
                return f"unsettled · {age:.0f}h", "is-late"
            return "in play", "is-live"
        return STATE_WORD["open"]
    if p["state"] == "price":
        return T.no_result_label(p["q"]), "is-price"
    return STATE_WORD.get(p["state"], (p["state"], "is-none"))


def _pick_html(sp, p, now):
    word, cls = pick_state(p, now)
    row = p["row"]
    text = esc(p["text"]) or "—"
    if p["href"] and p["state"] != "watch":
        text = B.safe_href(p["href"], p["text"])
    price = fmt.cents(p["price"]) if p["price"] is not None else "—"
    legs = f'<span class="sp-legs">{esc(p["legs"])}</span>' if p["legs"] else ""
    prod = ' <span class="badge stage production">Production</span>' if row.get("prod") else ""
    return (f'<div class="sp-pick {cls}" data-source="{esc(row["name"])}" data-sport="{esc(row["sport"])}" '
            f'data-scope="{scope_key(row)}" data-stage="{stage_key(row)}">'
            f'<span class="sp-pos">{text}{legs}</span>'
            f'<span class="sp-price">{esc(price)}</span>'
            f'<span class="sp-pick-rule">{esc(sp["rule_name"](row))}{prod}</span>'
            f'<span class="sp-state {cls}">{esc(word)}</span></div>')


def _event_html(sp, e, now, tab):
    when = e["when"]
    if when is None:
        clock = '<span class="sp-tbc">time TBC</span>'
    else:
        clock = esc(fmt.clock(when))
    live = tab == "live"
    scopes = " ".join(sorted({scope_key(p["row"]) for p in e["picks"]}))
    stages = " ".join(sorted({stage_key(p["row"]) for p in e["picks"]}))
    label = B.safe_href(e["href"], e["label"]) if e["href"] else esc(e["label"])
    sub = f'<small>{esc(e["sub"])}</small>' if e["sub"] else ""
    picks = "".join(_pick_html(sp, p, now) for p in e["picks"])
    return (f'<div class="sp-event{" is-live" if live else ""}" data-scopes="{scopes}" data-stages="{stages}">'
            f'<div class="sp-when">{clock}</div>'
            f'<div class="sp-what">{label}{sub}</div>'
            f'<div class="sp-picks">{picks}</div></div>')


def _day_of(e):
    if e["when"] is not None:
        return fmt.chicago(e["when"]).date()
    q = (e["picks"][0]["q"] if e["picks"] else None) or {}
    raw = q.get("date")
    if isinstance(raw, str):
        try:
            return datetime.date.fromisoformat(raw.strip()[:10])
        except ValueError:
            return None
    return None


def _day_label(day, today):
    text = f"{day.strftime('%a')} {fmt._MONTHS[day.month - 1]} {day.day}"
    delta = (day - today).days
    if delta == 0:
        return f"{text}<small>Today</small>"
    if delta == 1:
        return f"{text}<small>Tomorrow</small>"
    if delta == -1:
        return f"{text}<small>Yesterday</small>"
    return text


def _days_html(sp, events, now, tab, newest_first=False):
    today = fmt.chicago(now).date()
    days, undated = {}, []
    for e in events:
        day = _day_of(e)
        (undated if day is None else days.setdefault(day, [])).append(e)
    blocks = []
    for day in sorted(days, reverse=newest_first):
        rows_html = "".join(_event_html(sp, e, now, tab) for e in days[day])
        blocks.append(f'<section class="sp-day"><h4 class="sp-day-head">{_day_label(day, today)}</h4>{rows_html}</section>')
    if undated:
        rows_html = "".join(_event_html(sp, e, now, tab) for e in undated)
        blocks.append(f'<section class="sp-day"><h4 class="sp-day-head">Date TBC</h4>{rows_html}</section>')
    return "".join(blocks)


def bucket(events, now):
    """(next24, later, live, done): the events each tab lists, in its own order."""
    end = now + timedelta(hours=NEXT_H)
    floor = now - timedelta(days=DONE_DAYS)
    nxt, later, live, done = [], [], [], []
    for e in events:
        pending = [p for p in e["picks"] if p["state"] in ("open", "watch")]
        settled = [p for p in e["picks"] if p["state"] not in ("open", "watch")]
        when = e["when"]
        if pending:
            pe = dict(e, picks=pending)
            if when is None or when > now:
                (nxt if when is None or when <= end else later).append(pe)
            else:
                if any(p["state"] == "open" for p in pending):
                    live.append(dict(e, picks=[p for p in pending if p["state"] == "open"]))
        if settled:
            kept = []
            for p in settled:
                at = when or p.get("settled") or instant((p["q"] or {}).get("settled"))
                if at is None or at >= floor:
                    kept.append(p)
            if kept:
                done.append(dict(e, picks=kept))
    by_when = lambda e: (e["when"] or _FAR, e["label"])
    nxt.sort(key=by_when)
    later.sort(key=by_when)
    live.sort(key=by_when)
    done.sort(key=lambda e: (e["when"] or datetime.datetime.min.replace(tzinfo=timezone.utc), e["label"]), reverse=True)
    return nxt, later, live, done


def _count(events):
    return sum(len(e["picks"]) for e in events)


def coverage_reason(sp, d, rows, idle, now):
    """Why the next 24 hours are empty, from the last run's stored coverage.

    'no qualifying {venue} price' when the venue offered markets and no rule's band
    was met; 'no {venue} market listed' when it offered none; 'history still warming'
    when rules are registered and have never met a qualifying contest; 'no read stored'
    when the ledger has no coverage for the sport at all.
    """
    cov = d.get("coverage") or {}
    sports = {r["sport"] for r in rows} | {s for lane in idle for s in lane.get("sports", ())}
    offered = picked = 0
    seen = False
    for sport in sports:
        cell = cov.get(sport) or {}
        for name, value in cell.items():
            if isinstance(value, dict):
                seen = True
                offered += int(value.get("offered") or 0)
                picked += int(value.get("picked") or 0)
    venue = sp["venue"]
    never = [r for r in rows if not (r["a"].get("n") or r["a"].get("n_price") or r.get("open"))]
    if not seen:
        why = "no read is stored for this sport yet"
    elif offered and not picked:
        why = f"no qualifying {venue} price: the last read offered {offered} market{'s' if offered != 1 else ''} and no rule's band was met"
    elif not offered:
        why = f"no {venue} market was listed on the last read"
    else:
        why = f"the last read picked {picked} of {offered} markets; none starts in the next {NEXT_H} hours"
    if never or idle:
        n = len(never) + len(idle)
        why += f" · history still warming for {n} rule{'s' if n != 1 else ''} that has not met a qualifying contest"
    import tennis_cards
    nxt = tennis_cards.next_check(now)
    if nxt is not None:
        why += f" · next check {fmt.when(nxt)}"
    return why


def events_html(sp, d, rows, now, ev_list, idle):
    nxt, later, live, done = bucket(ev_list, now)
    counts = dict(next=_count(nxt) + _count(later), live=_count(live), done=_count(done))
    default = "next" if (nxt or later) else ("live" if live else ("done" if done else "next"))
    tabs = "".join(
        f'<button type="button" role="tab" data-tab="{key}" aria-selected="{"true" if key == default else "false"}" '
        f'aria-controls="events-{key}" id="tab-{key}">{label} <span class="sp-count">{counts[key]}</span></button>'
        for key, label in (("next", f"Next {NEXT_H}h"), ("live", "In progress"), ("done", f"Completed · {DONE_DAYS} days")))
    # Next 24h.
    if nxt:
        next_body = _days_html(sp, nxt, now, "next")
    else:
        next_body = (f'<p class="sp-empty" data-empty="next">No pick starts in the next {NEXT_H} hours: '
                     f'{esc(coverage_reason(sp, d, rows, idle, now))}.</p>')
    if later:
        n = _count(later)
        next_body += (f'<details class="fold later"><summary>Later<span class="sm mut"> · {n} pick{"s" if n != 1 else ""} '
                      f'past {NEXT_H} hours</span></summary>{_days_html(sp, later, now, "next")}</details>')
    # In progress.
    if live:
        live_body = _days_html(sp, live, now, "live")
    else:
        soon = nxt[0] if nxt else (later[0] if later else None)
        tail = f" Next start {fmt.when(soon['when'])}." if soon and soon["when"] else ""
        live_body = f'<p class="sp-empty" data-empty="live">Nothing is in progress: no open pick has started and not settled.{esc(tail)}</p>'
    # Completed.
    if done:
        done_body = _days_html(sp, done, now, "done", newest_first=True)
    else:
        ever = any((r["a"].get("n") or r["a"].get("n_price")) for r in rows)
        why = ("the rules have settled picks, the last one before this window" if ever
               else "no rule has settled a pick yet, so there is no history to show")
        done_body = f'<p class="sp-empty" data-empty="done">No pick settled in the last {DONE_DAYS} days: {esc(why)}.</p>'
    panels = (
        f'<section class="sp-panel" id="events-next" role="tabpanel" aria-labelledby="tab-next" data-tab="next"'
        f'{"" if default == "next" else " hidden"}><h3 class="sp-panel-title">Next {NEXT_H}h</h3>{next_body}</section>'
        f'<section class="sp-panel" id="events-live" role="tabpanel" aria-labelledby="tab-live" data-tab="live"'
        f'{"" if default == "live" else " hidden"}><h3 class="sp-panel-title">In progress</h3>{live_body}</section>'
        f'<section class="sp-panel" id="events-done" role="tabpanel" aria-labelledby="tab-done" data-tab="done"'
        f'{"" if default == "done" else " hidden"}><h3 class="sp-panel-title">Completed · {DONE_DAYS} days</h3>{done_body}</section>')
    total = counts["next"] + counts["live"] + counts["done"]
    return (f'<section id="events" class="sp-section" data-default-tab="{default}">'
            f'<div class="sp-section-head"><h2>Events</h2><span class="sm mut">{total} pick{"s" if total != 1 else ""}</span></div>'
            f'<div class="sp-tabs" role="tablist" aria-label="Events">{tabs}</div>{panels}</section>')


# ------------------------------------------------------------------ the method
def method_html(label, hint, inner, opened=False):
    return (f'<section id="method" class="sp-method">'
            f'<details{" open" if opened else ""}><summary><b>{esc(label)}</b><small>{esc(hint)}</small></summary>'
            f'<div>{inner}</div></details></section>')


# ------------------------------------------------------------------ the page
def body(sp, d, st, now, rows=None, idle=()):
    now = as_utc(now)
    rows = rows if rows is not None else sp["rows"]
    ev_list = sp["events"](d, rows, now)
    open_n = (sp["open_picks"](d, rows) if sp["open_picks"]
              else sum(1 for e in ev_list for p in e["picks"] if p["state"] == "open"))
    label, hint, inner, opened = sp["method"](d, rows, now) if sp["method"] else ("Method", "", "", False)
    return (
        f'<div class="sp-head"><p class="eyebrow">Rules under test</p><h1>{esc(sp["family"])}</h1>'
        f'<p class="scope">{esc(sp["scope"])} · All times Central</p></div>\n'
        f'{tiles_html(sp, d, st, rows, open_n)}\n'
        f'{filters_html(sp, rows)}\n'
        f'{rules_html(sp, d, rows, now, ev_list)}\n'
        f'{events_html(sp, d, rows, now, ev_list, idle)}\n'
        f'{method_html(label, hint, inner, opened)}\n'
        f'<footer>{FOOT}</footer>\n')


def page(sp, d=None, st=None, now=None, rows=None, idle=()):
    """The whole document for one sport, cells labelled for the phone cards."""
    now = as_utc(now)
    d = d if d is not None else T.load()
    st = st if st is not None else T.load_stages()
    html = C.document(
        sp["title"], sp["description"], sp["key"], TOC, C.stamp(now),
        body(sp, d, st, now, rows=rows, idle=idle),
        script_src="./site.js", scripts=("./tables.js",), sports=True)
    return B.label_cells(html)
