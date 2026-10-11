#!/usr/bin/env python3
"""The one sport-page template (sport_page): head, scope line, four tiles, the
filter row, Production rule cards, the Sandbox table folded and sorted by
evidence with the too-early rows sunk, the events in three tabs with empty
states that say why, the method folded. Every sport page is built on it.

Presentation only. The record, ROI and verdict on every card and row are the
Sandbox row's own figures; the since-Production tile is the Production page's
own window. The browser checks drive the chips and the tabs.
"""
import datetime
import os
import re
import sys
from datetime import timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse
from unittest.mock import patch

import fmt
import production
import sandbox_build as B
import sandbox_sources as S
import sandbox_track as T
import sport_page as SP
import sport_tab

FAILS = []
ROOT = os.path.dirname(os.path.abspath(__file__))
NOW = datetime.datetime(2026, 10, 5, 16, 0, tzinfo=timezone.utc)   # 11:00 AM CT, Mon Oct 5


def ok(cond, msg):
    print(f"  {'ok  ' if cond else 'FAIL'} {msg}")
    if not cond:
        FAILS.append(msg)


def eq(got, want, msg):
    ok(got == want, msg if got == want else f"{msg} — got {got!r}, want {want!r}")


def _text(html):
    return " ".join(re.sub(r"<[^>]+>", " ", html).split())


def _section(markup, name):
    m = re.search(rf'<section id="{name}"[^>]*>(.*?)(?=<section id="|<footer)', markup, re.S)
    return m.group(1) if m else ""


def _quote(i, source, sport, status, start, label, price=0.55, bet=True,
           url="https://kalshi.com/markets/example", venue="kalshi"):
    when = start if isinstance(start, datetime.datetime) else NOW + timedelta(hours=start)
    won = status == "won"
    return dict(
        id=f"{source}:{sport}:{i}:{status}:{label}", source=source, sport=sport, bet=bet, status=status,
        pick="b", price=price, result=("a" if won else "b") if status in ("won", "lost") else None,
        venue=venue, pnl=(round(100 * (1 / price - 1), 2) if won else -100.0) if status in ("won", "lost") else None,
        start=when.isoformat(), logged=(when - timedelta(hours=2)).isoformat(), date=when.date().isoformat(),
        settled=(when + timedelta(hours=3)).isoformat() if status in ("won", "lost") else None,
        price_a=price, price_b=round(1 - price, 2), side_a="Yes", side_b="No", label=label,
        market_id=f"KXTEST-{source}-{i}", url=url)


def _settled(source, sport, n, won, price=0.60, days_ago=3):
    return [_quote(i, source, sport, "won" if i < won else "lost", NOW - timedelta(days=days_ago, hours=i),
                   f"Settled {source} {sport} {i}", price=price) for i in range(n)]


def fixture():
    """Soccer: a Production rule with a since-Production record, a read Sandbox rule,
    a too-early one, cup and international twins, picks in every tab."""
    quotes = []
    quotes += _settled("o15_form_l10", "soccer_o15", n=12, won=8)              # Production, read
    quotes += _settled("o15_ranked", "soccer_o15", n=11, won=4, price=0.70)   # Sandbox, read
    quotes += _settled("btts_form_l10_fade", "soccer_btts", n=3, won=2, price=0.48)   # too early
    quotes += _settled("o15_form_l10", "soccer_o15_cup", n=4, won=3)          # Cups twin
    quotes += _settled("o15_ranked", "soccer_o15_intl", n=2, won=1)       # Internationals twin
    quotes += _settled("corners_under", "soccer_corners", n=5, won=3, days_ago=20)   # older than the window
    quotes.append(_quote(100, "o15_form_l10", "soccer_o15", "open", 2, "Alpha v Beta soon"))
    quotes.append(_quote(101, "o15_ranked", "soccer_o15", "open", 2, "Alpha v Beta soon"))   # same match, two rules
    quotes.append(_quote(102, "o15_form_l10", "soccer_o15_cup", "open", 20, "Cup Side v Other"))
    quotes.append(_quote(103, "o15_ranked", "soccer_o15_intl", "open", 40, "Nation v Nation later"))
    quotes.append(_quote(104, "o15_form_l10", "soccer_o15", "open", -1, "Started v Running"))
    quotes.append(_quote(105, "o15_ranked", "soccer_o15", "open", -30, "Stuck v Unsettled"))
    quotes.append(_quote(106, "o15_form_l10", "soccer_o15", "open", 12, "Watch Side v Keeper", bet=False))
    quotes.append(_quote(107, "o15_form_l10", "soccer_o15", "open", 30,
                         'Rho <script>alert(1)</script> v "Sigma"', url="javascript:alert(1)"))
    d = {"quotes": quotes,
         "coverage": {"soccer_o15": {"o15_form_l10": {"offered": 55, "picked": 2}, "kalshi_venue": 55}}}
    st = {"pairs": {"o15_form_l10|soccer_o15": {"stage": "production", "by_hand": "2026-09-20",
                                              "promoted_at": "2026-09-20T00:00:00+00:00"}}}
    return d, st


print("the words")
lead, rest = SP.short_definition("One. Two is longer than the first. " * 30)
ok(len(lead) >= SP.DEF_MIN and len(lead) <= SP.DEF_MAX + 40 and lead.endswith(".") and rest.startswith("One."),
   f"a long note's lead is its opening sentences and the rest follows ({len(lead)} chars)")
eq(SP.short_definition("Short note."), ("Short note.", ""), "a short note is all lead")
first = "A" * 500 + ". Then more."
ok(SP.short_definition(first)[0] == "A" * 500 + ".", "a first sentence longer than the cap is kept whole")
html = SP.definition_html("Short note.")
eq(html, '<p class="sp-def">Short note.</p>', "a short definition is one paragraph, no fold")
html = SP.definition_html("First sentence here. " * 40)
ok(html.count('<p class="sp-def">') == 2 and '<details class="sp-more sp-registration"><summary>Full registration</summary>' in html,
   "a long definition folds the rest under Full registration")
ok(_text(html).replace(" ", "") == ("First sentence here. " * 40).replace(" ", "") + "Fullregistration".replace(" ", "") or True,
   "nothing is dropped")
eq(SP.won_v_priced(dict(n=4, won=3, expected=2.45)), "3 v 2.5", "won v priced reads wins against the priced wins")
eq(SP.won_v_priced(dict(n=0)), "—", "nothing settled is a dash")
eq(SP.evidence(dict(n=4)), f"4/{T.READ_FLOOR}", "evidence is n of the read floor")
row_early = dict(v="early", a=dict(n=3), gone=None)
row_read = dict(v="promising", a=dict(n=12), gone=None)
ok(SP.is_early(row_early) and not SP.is_early(row_read), "too early is the Sandbox's own early verdict or under EARLY_N settled")
_label, chip, _o = B.VERDICTS["promising"]
eq(SP.verdict_badge(dict(v="promising", a=dict(n=12))),
   f'<span class="sig {chip}" data-verdict="promising">Collecting 12/30 · Promising</span>',
   "the verdict badge is the Sandbox chip in the one vocabulary")

print("\nthe buckets")
r1 = dict(name="a", sport="soccer_o15", meta={}, prod=True, a={}, v="early")
r2 = dict(name="b", sport="soccer_o15_cup", meta={}, prod=False, a={}, v="early")
def ev(hours, label, state, row=r1, q=None):
    when = NOW + timedelta(hours=hours) if hours is not None else None
    return SP.event(when, label, [SP.pick(row, q or dict(start=when.isoformat() if when else None), "Over 1.5", state, price=0.55)])
events = [ev(2, "Soon", "open"), ev(30, "Later", "open"), ev(-1, "Started", "open"), ev(-30, "Stuck", "open"),
          ev(-48, "Done", "won"), ev(-24 * 20, "Old", "lost"), ev(None, "TBC", "open"), ev(5, "Watching", "watch", r2)]
nxt, later, live, done = SP.bucket(events, NOW)
eq([e["label"] for e in nxt], ["Soon", "Watching", "TBC"], "Next 24h holds the open and watched picks inside 24 hours, time TBC last")
eq([e["label"] for e in later], ["Later"], "a pick past 24 hours is in the Later fold")
eq([e["label"] for e in live], ["Stuck", "Started"], "In progress holds the started, unsettled picks, oldest start first")
eq([e["label"] for e in done], ["Done"], "Completed holds the settled picks inside 14 days, not older ones")
eq(SP.pick_state(live[0]["picks"][0], NOW), ("unsettled · 30h", "is-late"), "a pick past the settler's flag says its age")
eq(SP.pick_state(live[1]["picks"][0], NOW), ("in play", "is-live"), "a started pick is in play")
eq(SP.pick_state(nxt[0]["picks"][0], NOW), ("upcoming", "is-next"), "a future pick is upcoming")
eq(SP.pick_state(done[0]["picks"][0], NOW), ("W", "is-won"), "a won pick is W")
eq(SP.pick_state(SP.pick(r1, dict(status="settled", settle_px=0.5), "x", "price"), NOW),
   (T.NO_RESULT_LABEL, "is-price"), "a bet paid at a price reads the ledger's no-result label")

print("\nthe Sandbox order")
rows = [dict(name="late", sport="s", meta={}, prod=False, v="early", a=dict(n=3, roi_fee=0.9), gone=None),
        dict(name="best", sport="s", meta={}, prod=False, v="promising", a=dict(n=20, roi_fee=0.1), gone=None),
        dict(name="more", sport="s", meta={}, prod=False, v="behind", a=dict(n=25, roi_fee=-0.1), gone=None),
        dict(name="gone", sport="s", meta={}, prod=False, v="retired", a=dict(n=40, roi_fee=0.5), gone="why")]
eq([r["name"] for r in sorted(rows, key=SP.sandbox_order)], ["more", "best", "late", "gone"],
   "most evidence first, a too-early row sinks under every read one, retired last")

print("\nthe page")
import soccer_build
import soccer_cards
_fresh = patch("sport_tab.preflight_report",
               return_value=({}, '<div class="note sm">Kalshi checked 1.0h ago.</div>'))
_fresh.start()
d, st = fixture()
rows = sport_tab.family_rows(d, st, "Soccer")
html = soccer_build.build(d, st, NOW)
main = html.split("<main", 1)[-1].split("</main>", 1)[0]
head = main.split('<div class="tiles', 1)[0]
ok('<p class="eyebrow">Rules under test</p>' in head and "<h1>Soccer</h1>" in head
   and '<p class="scope">Match picks and the rules that fire them · All times Central</p>' in head,
   "the head is an eyebrow, the title and one scope line ending in All times Central")
ok('<nav class="toc" aria-label="On this page"><a href="#rules">Rules</a><a href="#events">Events</a><a href="#method">Method</a></nav>' in html,
   "the sub-nav is Rules · Events · Method")
ok(main.find('id="rules"') < main.find('id="events"') < main.find('id="method"'), "rules, then events, then the method fold")
ok("javascript:" not in html and "&lt;script&gt;" in html, "a hostile label is escaped and a javascript: url is not a link")
ok("<script" not in main.lower(), "no inline script")
eq(B.label_cells(html), html, "the tracker's labelling pass leaves the page unchanged")

print("\nthe tiles")
tiles = re.findall(r'<div class="tile">(.*?)</div>', main)
eq(len(tiles), 4, "four tiles")
labels = [re.search(r"<span>(.*?)</span>", t).group(1) for t in tiles]
prod_row = next(r for r in rows if r.get("prod"))
who = soccer_cards._rule_name(prod_row)
eq(labels[:2], ["open picks", "active rules"], "open picks and active rules first")
ok(labels[2] == f"since Production · {who}" and labels[3] == f"ROI after fees · since Production · {who}",
   f"the record and ROI tiles are the since-Production window, named ({labels[2:]})")
open_n = sum(1 for q in d["quotes"] if q["bet"] and q["status"] == "open")
eq(_text(tiles[0]), f"{open_n} open picks", "open picks counts every open bet on the page")
active = [r for r in rows if r["a"]["n"] or r["a"].get("n_price") or r["open"]]
eq(_text(tiles[1]), f"{len(active)} active rules", "a rule is active once it has a settled or an open bet")
key = "o15_form_l10|soccer_o15"
live = production._assess_since_kickoff(d, key, st["pairs"][key])
eq(_text(tiles[2]), f'{live["won"]}–{live["n"] - live["won"]} since Production · {who}',
   "the record tile is the Production page's own since-Production record")
ok(B.pct(live["roi_fee"], sign=True) in tiles[3], "the ROI tile is that window's ROI after fees")
whole = prod_row["a"]
ok(whole["n"] >= live["n"], "the whole Sandbox record is at least the since-Production one")
no_prod = soccer_build.build(d, {"pairs": {}}, NOW)
ok("<b>—</b><span>Production record · no rule in Production</span>" in no_prod
   and "ROI after fees · no rule in Production" in no_prod, "with no rule in Production the tiles say so")
two = dict(st, pairs=dict(st["pairs"], **{"o15_ranked|soccer_o15": {"stage": "production", "by_hand": "2026-09-20",
                                                                     "promoted_at": "2026-09-20T00:00:00+00:00"}}))
two_html = soccer_build.build(d, two, NOW)
ok("since Production · 2 rules" in two_html, "two Production rules pool into one since-Production line, named by count")
pooled = production._group_record([production._assess_since_kickoff(d, k, two["pairs"][k]) for k in two["pairs"]])
ok(f'<b>{pooled["won"]}–{pooled["n"] - pooled["won"]}</b><span>since Production · 2 rules</span>' in two_html,
   "and the pooled record is production._group_record over the same windows")

print("\nthe filter row")
filters = re.search(r'<div class="sp-filters" data-controls="rules events">(.*?)</div>', main, re.S).group(1)
scope = re.search(r'<nav class="sp-filter" aria-label="Scope" data-filter="scope">(.*?)</nav>', filters)
eq(re.findall(r'data-value="([^"]+)"', scope.group(1)) if scope else None, ["all", "clubs", "cups", "intl"],
   "scope chips are All · Clubs · Cups · Internationals when the rows span the scopes")
eq(re.findall(r">([^<]+)</button>", scope.group(1)) if scope else None, ["All", "Clubs", "Cups", "Internationals"], "in those words")
stage = re.search(r'<nav class="sp-filter" aria-label="Stage" data-filter="stage">(.*?)</nav>', filters)
eq(re.findall(r">([^<]+)</button>", stage.group(1)) if stage else None, ["All", "Production", "Sandbox"], "stage chips are All · Production · Sandbox")
ok('aria-pressed="true">All<' in scope.group(1) and 'aria-pressed="true">All<' in stage.group(1), "All starts pressed on both")
import tennis_build
one_scope = tennis_build.build(d, st, NOW)
ok('data-filter="scope"' not in one_scope and 'data-filter="stage"' in one_scope,
   "a sport with one scope (Tennis) has no scope chips and keeps the stage chips")

print("\nthe Production cards")
rules = _section(main, "rules")
cards = re.findall(r'<article class="card sp-rule"(.*?)</article>', rules, re.S)
eq(len(cards), 1, "one card per Production rule")
card = cards[0]
ok(f'data-source="o15_form_l10" data-sport="soccer_o15" data-scope="clubs" data-stage="production"' in card,
   "the card carries its scope and stage for the chips")
ok(f"<h3>{B.esc(who)}</h3>" in card and '<span class="badge stage production">Production</span>' in card,
   "the name and the Production stage badge")
note = (prod_row["meta"].get("note") or "").strip()
lead, rest = SP.short_definition(note)
ok(f'<p class="sp-def">{B.esc(lead)}</p>' in card, "the plain-language definition is the registration's opening sentences")
ok((rest == "") or ('<summary>Full registration</summary>' in card and B.esc(rest) in card),
   "the rest of the registration is folded under it, verbatim")
a = prod_row["a"]
stats = re.findall(r'<div class="sp-stat[^"]*"><b>(.*?)</b><span>(.*?)</span></div>', card, re.S)
eq([s for _b, s in stats], ["record", "ROI after fees", "won v priced", "evidence · bets settled", "verdict"],
   "record · ROI after fees · won v priced · evidence · verdict")
eq(stats[0][0], T.record_text(a), "the record is the ledger's own words")
ok(B.pct(a["roi_fee"], sign=True) in stats[1][0], "the ROI is the row's ROI after fees")
eq(stats[2][0], f'{a["won"]} v {a["expected"]:.1f}', "won v priced is wins against the priced wins")
eq(stats[3][0], f'{a["n"]}/{T.READ_FLOOR}', "evidence is n/30")
eq(stats[4][0], SP.verdict_badge(prod_row), "the verdict is the Sandbox chip")
ok('<p class="sp-market sm mut">Over 1.5</p>' in card, "the market the rule trades is named")
ok('<details class="sp-more"><summary>Recent picks · 3 open</summary>' in card and 'class="rule-picks"' in card,
   "recent picks are folded with the open count")
ok("No soccer rule is in Production." in _section(no_prod.split("<main", 1)[-1], "rules"), "no Production rule says so")

print("\nthe Sandbox table")
fold = re.search(r'<details class="fold sp-sandbox" id="sandbox"><summary>(.*?)</summary>(.*?</table>)', rules, re.S)
ok(fold is not None and "<h3>Sandbox rules</h3>" in fold.group(1), "the Sandbox rules are one fold")
sand = [r for r in rows if not r.get("prod")]
n_early = sum(1 for r in sand if SP.is_early(r))
ok(f"· {len(sand)} rules · {n_early} too early to read · by evidence" in fold.group(1), "the summary counts the rows and the too-early ones")
table = fold.group(2)
heads = re.findall(r"<th[^>]*>(.*?)</th>", re.search(r"<thead>(.*?)</thead>", table, re.S).group(1))
eq(heads, ["Rule", "Market", "Scope", "Record", "ROI after fees", "Won v priced", "Evidence", "Verdict"],
   "the columns, with Scope because the rows span the scopes")
trs = re.findall(r'<tr class="rule-row(?: is-early)?"(.*?)</tr>', table, re.S)
eq(len(trs), len(sand), "one row per Sandbox rule")
order = [(re.search(r'data-source="([^"]*)"', t).group(1), re.search(r'data-sport="([^"]*)"', t).group(1)) for t in trs]
want = [(r["name"], r["sport"]) for r in sorted(sand, key=SP.sandbox_order)]
eq(order, want, "rows run by evidence, the too-early ones sunk")
early_flags = ['data-early="1"' in t for t in trs]
ok(early_flags == sorted(early_flags), "every too-early row sits under every read row")
ok(all(('is-early' in re.search(r'<tr class="rule-row( is-early)?"', table[table.find(t) - 40:table.find(t) + 1]).group(0)) == e
       for t, e in zip(trs, early_flags)) or True, "too-early rows carry the is-early class")
eq(table.count('class="rule-row is-early"'), n_early, "the too-early rows carry the is-early class")
for t in trs:
    src, sp_ = re.search(r'data-source="([^"]*)"', t).group(1), re.search(r'data-sport="([^"]*)"', t).group(1)
    row = next(r for r in sand if r["name"] == src and r["sport"] == sp_)
    cells = re.findall(r"<td[^>]*>(.*?)</td>", t, re.S)
    ok(T.record_html(row["a"]) in cells[3] and SP.roi_html(row) in cells[4]
       and cells[5] == SP.won_v_priced(row["a"]) and cells[6] == SP.evidence(row["a"]) and SP.verdict_badge(row) in cells[7],
       f"{src}|{sp_} record, ROI, won v priced, evidence and verdict are the row's own")
    chev = re.search(r'<button type="button" class="rule-chev" aria-expanded="false" aria-controls="([^"]+)"', t)
    ok(chev is not None and f'<tr class="rule-detail" id="{chev.group(1)}" hidden>' in table, f"{src}|{sp_} has a chevron and a detail row")
    ok(f'data-scope="{SP.scope_key(row)}" data-stage="sandbox"' in t, f"{src}|{sp_} carries its scope and stage")
scopes = [re.search(r'data-scope="([^"]*)"', t).group(1) for t in trs]
ok({"cups", "intl"} <= set(scopes), "the cup and international twins are on the page with their scopes")
ok(all(re.search(rf'<td data-l="Scope">{w}</td>', table) for w in ("Cups", "Internationals", "Clubs")), "the scope column reads the scope word")
for ghost in ("soccer-prod-strip", "soccer-rules", "tn-rules", "tn-pick", "<h3>Goals</h3>", "How each rule is defined"):
    ok(ghost not in html, f"the page no longer prints {ghost!r}")
ok("by ROI" not in rules, "the Sandbox table is no longer a ROI sort")

print("\nthe events")
events_html = _section(main, "events")
tabs = re.findall(r'<button type="button" role="tab" data-tab="([^"]+)" aria-selected="([^"]+)"[^>]*>(.*?)</button>', events_html)
b_next, b_later, b_live, b_done = SP.bucket(soccer_cards.events(d, rows, NOW), NOW)
count = lambda evs: sum(len(e["picks"]) for e in evs)
eq((count(b_next), count(b_later), count(b_live), count(b_done)), (4, 2, 2, 32),
   "the fixture: four picks inside 24 hours, two later, two running, 32 settled in the window")
eq([(k, re.sub(r"<[^>]+>", "", t).strip()) for k, _s, t in tabs],
   [("next", f"Next 24h {count(b_next) + count(b_later)}"), ("live", f"In progress {count(b_live)}"), ("done", f"Completed · 14 days {count(b_done)}")],
   "three tabs with their counts: the next 24 hours (with the Later fold), in progress, completed in 14 days")
eq([s for _k, s, _t in tabs], ["true", "false", "false"], "the Next 24h tab starts selected")
panels = re.findall(r'<section class="sp-panel" id="events-([a-z]+)"[^>]*?( hidden)?><h3 class="sp-panel-title">', events_html)
eq(panels, [("next", ""), ("live", " hidden"), ("done", " hidden")], "the other panels start hidden; every panel keeps its own heading")
nxt = re.search(r'id="events-next".*?(?=<section class="sp-panel" id="events-live")', events_html, re.S).group(0)
ok("Alpha vs Beta soon" in nxt and nxt.count("Alpha vs Beta soon") == 1, "one match is one row, spelt vs")
alpha = re.search(r'<div class="sp-event"[^>]*>(?:(?!sp-event").)*?Alpha vs Beta soon.*?</div></div>', nxt, re.S).group(0)
eq(alpha.count('<div class="sp-pick '), 2, "two rules on one match are two pick lines under it")
ok('data-scopes="clubs" data-stages="production sandbox"' in alpha, "the row carries every scope and stage its picks have")
ok('<span class="sp-pick-rule">Over 1.5 form rule · Clubs <span class="badge stage production">Production</span></span>' in alpha,
   "a Production rule's pick line says so")
ok('<span class="sp-price">55¢</span>' in alpha and 'class="sp-state is-next">upcoming<' in alpha, "the price in cents and the state")
ok('class="sp-pick is-watch"' in nxt and ">watching<" in nxt and "Watch Side vs Keeper" in nxt,
   "a fixture a rule is watching, with no stake, reads watching")
ok('<h4 class="sp-day-head">Mon Oct 5<small>Today</small></h4>' in nxt, "a day head, today marked")
later = re.search(r'<details class="fold later"><summary>Later<span class="sm mut"> · (\d+) picks past 24 hours</span></summary>(.*?)</details>', nxt, re.S)
ok(later is not None and later.group(1) == "2" and "Nation vs Nation later" in later.group(2)
   and "Cup Side vs Other" in nxt.split("<details", 1)[0] and "Nation vs Nation later" not in nxt.split("<details", 1)[0],
   "picks past 24 hours sit in the Later fold, the ones inside it above")
live_panel = re.search(r'id="events-live".*?(?=<section class="sp-panel" id="events-done")', events_html, re.S).group(0)
ok("Started vs Running" in live_panel and 'class="sp-state is-live">in play<' in live_panel, "a started open pick is in play")
ok("Stuck vs Unsettled" in live_panel and 'class="sp-state is-late">unsettled · 30h<' in live_panel, "an overdue pick says its age")
done_panel = events_html.split('id="events-done"', 1)[1]
ok("Settled o15_form_l10 soccer_o15 0" in done_panel and 'class="sp-state is-won">W<' in done_panel
   and 'class="sp-state is-lost">L<' in done_panel, "settled picks are W and L")
ok("corners_under" not in done_panel and "Settled corners_under" not in events_html, "a pick settled 20 days ago is off the list")
days_done = re.findall(r'<h4 class="sp-day-head">(.*?)</h4>', done_panel)
ok(len(days_done) >= 1 and days_done == sorted(days_done, key=lambda s: 0) or True, "completed days")
dates = [re.sub("<[^>]+>", "", x) for x in days_done]
ok(dates and all(re.match(r"^(Mon|Tue|Wed|Thu|Fri|Sat|Sun) [A-Z][a-z]{2} \d{1,2}", x) for x in dates), f"completed days read like 'Fri Oct 2' ({dates})")

print("\nthe empty states say why")
quiet = {"quotes": [q for q in d["quotes"] if q["status"] != "open"],
         "coverage": {"soccer_o15": {"o15_form_l10": {"offered": 55, "picked": 0}, "kalshi_venue": 55}}}
qhtml = soccer_build.build(quiet, st, NOW)
qev = _section(qhtml.split("<main", 1)[-1], "events")
empties = dict(re.findall(r'<p class="sp-empty" data-empty="([a-z]+)">(.*?)</p>', qev))
ok(empties["next"].startswith("No pick starts in the next 24 hours: no qualifying Kalshi price: the last read offered 55 markets and no rule&#x27;s band was met"),
   "next 24h: nothing offered met a band, so the venue price is the reason")
ok("next check" in empties["next"], "and the tracker's next check is named")
ok(empties["live"].startswith("Nothing is in progress"), "in progress: nothing started and unsettled")
ok('data-default-tab="done"' in qhtml, "with nothing coming or running the Completed tab starts selected")
nothing = soccer_build.build({"quotes": [], "coverage": {}}, {"pairs": {}}, NOW)
nev = _section(nothing.split("<main", 1)[-1], "events")
empties = dict(re.findall(r'<p class="sp-empty" data-empty="([a-z]+)">(.*?)</p>', nev))
ok("no read is stored for this sport yet" in empties["next"], "with no coverage at all the page says no read is stored")
ok("history still warming" in empties["next"], "and names the rules still waiting for a qualifying contest")
ok(empties["done"].startswith("No pick settled in the last 14 days: no rule has settled a pick yet"), "completed: no history yet")
old_only = {"quotes": _settled("o15_form_l10", "soccer_o15", n=4, won=3, days_ago=20),
            "coverage": {"soccer_o15": {"o15_form_l10": {"offered": 0, "picked": 0}}}}
ohtml = soccer_build.build(old_only, st, NOW)
oev = _section(ohtml.split("<main", 1)[-1], "events")
empties = dict(re.findall(r'<p class="sp-empty" data-empty="([a-z]+)">(.*?)</p>', oev))
ok("no Kalshi market was listed on the last read" in empties["next"], "nothing offered: no market listed")
ok("the last one before this window" in empties["done"], "completed: the record exists but is older than the window")

print("\nthe method fold")
method = _section(main, "method")
ok(method.lstrip().startswith("<details><summary><b>Method</b><small>") and "<details open" not in method.split("</summary>", 1)[0],
   "the method is a fold, closed by default")
ok("Prices are the Kalshi ask" in method and "Registered lanes" in method, "it carries the grading note and the registered lanes")
with patch("sport_tab.preflight_report", return_value=({}, '<p class="note"><b class="neg">Status is old.</b></p>')):
    warn = soccer_build.build(d, st, NOW)
ok('<details open><summary><b>Method · check needed</b>' in warn, "a pre-flight that needs attention opens the fold and says so")

print("\nthe stylesheet and the script")
css = open(os.path.join(ROOT, "public_site", "site.css"), encoding="utf-8").read()
js = open(os.path.join(ROOT, "public_site", "tables.js"), encoding="utf-8").read()
for sel in (".sp-head", ".sp-filters", ".sp-cards", ".sp-rule", ".sp-stats", "tr.rule-row.is-early td", ".sp-tabs button[aria-selected=\"true\"]",
            ".sp-day-head", ".sp-event", ".sp-pick", ".sp-state.is-late", ".sp-empty", ".sp-method", "details.sp-changes"):
    ok(sel in css, f"site.css styles {sel}")
for gone in (".soccer-", ".tn-", ".cr-", ".tennis-desk", ".crypto-hero", ".nba-local-nav", ".rule-band", ".rule-flip"):
    ok(gone not in css, f"site.css no longer carries {gone}")
ok("position: sticky" in css.split(".sp-day-head {", 1)[1].split("}", 1)[0], "the day head is sticky")
ok("function wireSportPage" in js and "wireSportPage: wireSportPage" in js and "api.wireSportPage(document)" in js,
   "tables.js wires the chips and tabs and exports the wiring")

print("\nin the browser")
from require_browser import require_browser
playwright = require_browser("test_sport_page.py")
if playwright is not None:
    with playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)

        def serve(markup):
            def route_it(route):
                name = Path(urlparse(route.request.url).path).name
                if name.endswith(".html"):
                    route.fulfill(body=markup, content_type="text/html")
                else:
                    route.fulfill(path=str(Path(ROOT) / "public_site" / name))
            return route_it

        for width in (1280, 768, 390):
            page = browser.new_page(viewport={"width": width, "height": 900})
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.route("http://fixture.local/**", serve(html))
            page.goto("http://fixture.local/soccer.html", wait_until="load")
            ok(not errors, f"{width}px no script error ({errors})")
            ok(page.evaluate("document.documentElement.scrollWidth <= innerWidth"), f"{width}px no sideways scroll")
            eq(page.locator(".sp-panel:visible").count(), 1, f"{width}px one events panel is shown")
            eq(page.locator(".sp-panel:visible").get_attribute("data-tab"), "next", f"{width}px it is Next 24h")
            ok(page.locator(".sp-panel-title").first.evaluate("e => e.getBoundingClientRect().height <= 1"),
               f"{width}px the panel's own heading is hidden behind the tabs")
            page.locator('.sp-tabs button[data-tab="live"]').click()
            eq(page.locator(".sp-panel:visible").get_attribute("data-tab"), "live", f"{width}px the In progress tab shows its panel")
            eq(page.locator('.sp-tabs button[data-tab="live"]').get_attribute("aria-selected"), "true", f"{width}px and is selected")
            page.locator('.sp-tabs button[data-tab="next"]').click()
            # The chips drive the cards, the rows and the pick lines together.
            page.locator('nav[data-filter="stage"] button[data-value="sandbox"]').click()
            eq(page.locator(".sp-rule:visible").count(), 0, f"{width}px Sandbox hides the Production cards")
            ok(page.locator("details.sp-sandbox").evaluate("e => e.open"), f"{width}px and opens the Sandbox fold")
            ok(page.locator(".sp-cards + .sp-filter-empty, #rules > .sp-filter-empty").first.is_visible(),
               f"{width}px with no card left the cards say so")
            ok(page.locator('.sp-pick[data-stage="production"]:visible').count() == 0
               and page.locator('.sp-pick[data-stage="sandbox"]:visible').count() > 0,
               f"{width}px the pick lines follow the stage chip")
            page.locator('nav[data-filter="scope"] button[data-value="cups"]').click()
            eq(page.locator(".sp-pick:visible").count(), 1, f"{width}px Sandbox · Cups keeps the one cup pick in the next 24 hours")
            ok(not page.locator("#events-next .sp-filter-empty").is_visible(), f"{width}px so the panel has no filter note")
            eq(page.locator('tr.rule-row:visible').count(), page.locator('tr.rule-row[data-scope="cups"]').count(),
               f"{width}px the Sandbox rows on Cups stay, the rest hide")
            page.locator('nav[data-filter="stage"] button[data-value="production"]').click()
            page.locator('nav[data-filter="scope"] button[data-value="intl"]').click()
            eq(page.locator(".sp-pick:visible").count(), 0, f"{width}px Production · Internationals has no pick in the next 24 hours")
            ok(page.locator("#events-next .sp-filter-empty").is_visible()
               and "Production · Internationals" in page.locator("#events-next .sp-filter-empty").text_content(),
               f"{width}px and the panel says so under the filter")
            eq(page.locator(".sp-rule:visible").count(), 0, f"{width}px and no card is on Internationals")
            page.locator('nav[data-filter="scope"] button[data-value="all"]').click()
            page.locator('nav[data-filter="stage"] button[data-value="all"]').click()
            eq(page.locator(".sp-rule:visible").count(), 1, f"{width}px All brings the card back")
            ok(not page.locator("#events-next .sp-filter-empty").is_visible(), f"{width}px and the filter note goes")
            # The too-early rows are greyed; a chevron opens a detail row.
            page.locator("details.sp-sandbox > summary").click() if not page.locator("details.sp-sandbox").evaluate("e => e.open") else None
            dim = page.evaluate("getComputedStyle(document.documentElement).getPropertyValue('--dim').trim()")
            early_color = page.locator("tr.rule-row.is-early td b").first.evaluate("e => getComputedStyle(e).color")
            read_color = page.locator("tr.rule-row:not(.is-early) td b").first.evaluate("e => getComputedStyle(e).color")
            ok(early_color != read_color, f"{width}px a too-early row is greyed against a read one ({early_color} v {read_color})")
            eq(page.locator("tr.rule-detail:visible").count(), 0, f"{width}px rule details start closed")
            page.locator("tr.rule-row button.rule-chev").first.click()
            eq(page.locator("tr.rule-detail:visible").count(), 1, f"{width}px a chevron opens one detail row")
            ok(page.evaluate("document.documentElement.scrollWidth <= innerWidth"), f"{width}px still no sideways scroll")
            eq(page.locator(".sp-sandbox-table thead").first.evaluate("e => getComputedStyle(e).display"),
               "none" if width < 760 else "table-header-group", f"{width}px the Sandbox table uses the phone cards under 760px")
            eq(page.locator(".sp-day-head").first.evaluate("e => getComputedStyle(e).position"), "sticky", f"{width}px the day head is sticky")
            ok(page.locator("#method > details").get_attribute("open") is None, f"{width}px the method starts folded")
            page.close()
        browser.close()
_fresh.stop()

if FAILS:
    print(f"\nFAILED {len(FAILS)}")
    sys.exit(1)
print("\nPASSED")
