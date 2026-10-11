#!/usr/bin/env python3
"""The Tennis page on the shared sport template: what tennis_cards hands it.

Presentation only. The record, verdict and ROI are the Sandbox row's own
figures, compared as strings. Every basket's record is on its own row; the
tiles are the since-Production window, never a pool across Sandbox rules.
A refused tour or a pre-reset bet never reaches the page.
"""
import datetime
import os
import re
import subprocess
import sys
import tempfile
from datetime import timedelta, timezone

import fmt
import sandbox_build as B
import sandbox_sources as S
import sandbox_track as T
import sport_page as SP

FAILS = []
ROOT = os.path.dirname(os.path.abspath(__file__))
NOW = datetime.datetime(2026, 10, 5, 16, 0, tzinfo=timezone.utc)   # 11:00 AM CT


def _head_sha():
    try:
        out = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True,
                                      stderr=subprocess.DEVNULL).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"
    return out or "unknown"


SHA = _head_sha()


def ok(cond, msg):
    print(f"  {'ok  ' if cond else 'FAIL'} {msg}")
    if not cond:
        FAILS.append(msg)


def eq(got, want, msg):
    ok(got == want, msg if got == want else f"{msg} — got {got!r}, want {want!r}")


def _text(html):
    return " ".join(re.sub(r"<[^>]+>", " ", html).split())


def _quote(i, source, sport, status, start, label, price=0.55,
           url="https://kalshi.com/markets/example", venue="kalshi", bet=True, **extra):
    when = start if isinstance(start, datetime.datetime) else NOW + timedelta(hours=start)
    won = status == "won"
    q = dict(
        id=f"{source}:{sport}:{i}:{status}:{label}",
        source=source, sport=sport, bet=bet, status=status,
        pick="b", price=price,
        result=("b" if won else "a") if status in ("won", "lost") else None,
        venue=venue,
        pnl=(round(100 * (1 / price - 1), 2) if won else -100.0) if status in ("won", "lost") else None,
        start=when.isoformat(),
        logged=(when - timedelta(hours=2)).isoformat(),
        date=when.date().isoformat(),
        price_a=round(1 - price, 2), price_b=price,
        side_a="Yes", side_b="No",
        label=label,
        market_id=f"m-{source}-{i}",
        url=url,
    )
    q.update(extra)
    return q


def _settled(source, sport, n=4, won=3, price=0.60):
    rows = []
    for i in range(n):
        status = "won" if i < won else "lost"
        rows.append(_quote(
            i, source, sport, status,
            NOW - timedelta(days=3, hours=i),
            f"Settled {source} {i}",
            price=price,
        ))
    return rows


def _legs(*names):
    return [dict(name=n, pick="a", venue="kalshi", market_id=f"leg-{n}",
                 start=(NOW + timedelta(hours=5)).isoformat()) for n in names]


def _fixture():
    """Tennis markets, plus one soccer lane and one cricket lane that must stay put."""
    quotes = []
    quotes += _settled("tennis_fav_band_3h", "tennis", n=6, won=4)
    quotes += _settled("tennis_combo2", "tennis_combo", n=4, won=3, price=0.62)
    quotes += _settled("pm_combo2", "tennis_pmcombo", n=5, won=2, price=0.48)
    opens = [
        (1, "Alpha v Beta soonest", "Alpha", "Beta"),
        (2, "Gamma v Delta second", "Gamma", "Delta"),
        (30, "Iota v Kappa later", "Iota", "Kappa"),
    ]
    for i, (hours, label, a, b) in enumerate(opens):
        quotes.append(_quote(100 + i, "tennis_fav_band_3h", "tennis", "open", hours, label,
                             side_a=a, side_b=b, venue="polymarket_us",
                             url="https://polymarket.us/event/x"))
    # One already started and still open: in progress.
    quotes.append(_quote(110, "tennis_fav_band_3h", "tennis", "open", -1,
                         "Started v Running", side_a="Started", side_b="Running"))
    # Settled today: completed, with W / L.
    quotes.append(_quote(120, "tennis_fav_band_3h", "tennis", "won", -6,
                         "Morning v Winner", side_a="Morning", side_b="Winner"))
    quotes.append(_quote(121, "tennis_fav_band_3h", "tennis", "lost", -5,
                         "Morning v Loser", side_a="Morning", side_b="Loser"))
    # Settled yesterday: completed too, under its own day.
    quotes.append(_quote(122, "tennis_fav_band_3h", "tennis", "won", -30,
                         "Yesterday v Gone", side_a="Yesterday", side_b="Gone"))
    # A two-leg basket names both legs in the pick; a three-leg one lists them under it.
    quotes.append(_quote(200, "tennis_combo2", "tennis_combo", "open", 5,
                         "2-leg tennis combo: Nuno Borges + Federico Cina", pick="a",
                         side_a="All 2 win", side_b="Any one loses", venue="combo",
                         url="https://kalshi.com/combos", legs=_legs("Nuno Borges", "Federico Cina")))
    quotes.append(_quote(300, "tennis_combo3", "tennis_combo", "open", 6,
                         "3-leg tennis combo: Ann + Bob + Cid", pick="a",
                         side_a="All 3 win", side_b="Any one loses", venue="combo",
                         url="https://kalshi.com/combos", legs=_legs("Ann", "Bob", "Cid")))
    # Open on Polymarket US, far out, with a hostile url.
    quotes.append(_quote(400, "pm_combo2", "tennis_pmcombo", "open", 80,
                         "2-leg tennis combo: Rho + Sigma", pick="a",
                         side_a="All 2 win", side_b="Any one loses", venue="polymarket_us",
                         url="javascript:alert(1)", legs=_legs("Rho", "Sigma")))
    # A singles pick with a hostile label.
    quotes.append(_quote(130, "tennis_fav_band_3h", "tennis", "open", 7,
                         'Rho <script>alert(1)</script> v "Sigma"', side_a="Rho", side_b="Sigma"))
    # A stored fixture with no stake is not a pick on this page.
    quotes.append(_quote(500, "tennis_fav_band_3h", "tennis", "open", 12,
                         "Watch v Only", side_a="Watch", side_b="Only", bet=False))
    # Other families stay on their own pages.
    quotes += _settled("o15_form_l10", "soccer_o15", n=3, won=2)
    quotes.append(_quote(600, "o15_form_l10", "soccer_o15", "open", 3, "Soccer Only v Stay"))
    quotes += _settled("oddspedia", "cricket", n=3, won=2)
    quotes.append(_quote(700, "oddspedia", "cricket", "open", 3, "Cricket Only v Stay",
                         side_a="Cricket Only", side_b="Stay", venue="polymarket_us"))
    return {"quotes": quotes}, {"pairs": {}}


def _rows(d, st):
    import sport_tab
    return sport_tab.family_rows(d, st, "Tennis")


def _section(markup, name):
    m = re.search(rf'<section id="{name}"[^>]*>(.*?)(?=<section id="|<footer)', markup, re.S)
    return m.group(1) if m else ""


def _picks(markup):
    return re.findall(r'<div class="sp-pick ([^"]*)" data-source="([^"]*)"[^>]*>(.*?)</div>', markup, re.S)


def _rule_rows(markup):
    return re.findall(r'<tr class="rule-row(?: is-early)?" data-source="([^"]*)" data-sport="([^"]*)"[^>]*>(.*?)</tr>', markup, re.S)


print(f"SHA {SHA}")

import tennis_cards
import tennis_build
import cricket_build
import soccer_build

print("\nshape")
d, st = _fixture()
html = tennis_build.build(d, st, NOW)
rows = _rows(d, st)
ok(rows, "the fixture has tennis lanes")
main = html.split("<main", 1)[-1].split("</main>", 1)[0]
ok("<h1>Tennis</h1>" in main and "Match-winner picks and combo baskets · All times Central" in main,
   "the head is the title and one scope line")
ok('id="events"' in main and 'id="rules"' in main and 'id="method"' in main,
   "the page has Rules, Events and Method sections")
toc = re.search(r'<nav class="toc"[^>]*>(.*?)</nav>', html, re.S)
eq(re.findall(r">([^<]+)</a>", toc.group(1)) if toc else None, ["Rules", "Events", "Method"],
   "the jump pills are Rules / Events / Method")
for gone in ('id="today"', 'id="upcoming"', 'id="in-play"', 'id="combos"', "No tracked tennis match",
             "rule-card", "rule-grid", "tennis-combo-grid", "How each rule is defined", "Match center",
             "tn-pick", "tn-rules", "tn-system"):
    ok(gone not in main, f"{gone} is gone")
ok(main.count("<h2>") == 2, "two headings: Rules and Events; Method is a fold")
ok("<script" not in main.lower(), "the page body does not grow an inline script")
ok("javascript:" not in html, "a javascript: url is not written")
ok("&lt;script&gt;" in html, "a hostile label is escaped")
ok('data-filter="scope"' not in html and 'data-filter="stage"' in html, "one scope, so only the stage chips")

print("\ntiles")
tiles = re.findall(r'<div class="tile">(.*?)</div>', main, re.S)
eq(len(tiles), 4, "four stat tiles")
labels = [re.search(r"<span>(.*?)</span>", t).group(1) for t in tiles]
eq(labels, ["open picks", "active rules", "Production record · no rule in Production", "ROI after fees · no rule in Production"],
   "with nothing in Production the record and ROI tiles say so")
open_n = sum(1 for q in d["quotes"] if str(q["sport"]).startswith("tennis")
             and q["bet"] and q["status"] == "open")
eq(_text(tiles[0]), f"{open_n} open picks", "open picks counts every open tennis bet")
active = [r for r in rows if r["a"]["n"] or r["open"]]
eq(_text(tiles[1]), f"{len(active)} active rules", "a rule is active once it has fired")
single = next(r for r in rows if r["name"] == "tennis_fav_band_3h")
prod_st = {"pairs": {"tennis_fav_band_3h|tennis": {"stage": "production", "by_hand": "2026-09-20",
                                                   "promoted_at": "2026-09-20T00:00:00+00:00"}}}
prod_html = tennis_build.build(d, prod_st, NOW)
who = tennis_cards.rule_name(single)
import production
live = production._assess_since_kickoff(d, "tennis_fav_band_3h|tennis", prod_st["pairs"]["tennis_fav_band_3h|tennis"])
ok(f'<b>{live["won"]}–{live["n"] - live["won"]}</b><span>since Production · {who}</span>' in prod_html,
   "with the band in Production the record tile is its since-Production W–L, named")
ok(f"ROI after fees · since Production · {who}" in prod_html, "and the ROI tile is that window's ROI")
pooled = sum(r["a"]["n"] for r in active)
ok(f"{sum(r['a']['won'] for r in active)}–{pooled - sum(r['a']['won'] for r in active)}" not in _text("".join(re.findall(r'<div class="tile">(.*?)</div>', prod_html))),
   "no tile pools the combo baskets into the singles record")

print("\nevents")
events = _section(main, "events")
picks = _picks(events)
by_lane = {(r["name"], r["sport"]): r for r in rows}
want = sorted(
    (q for q in d["quotes"] if str(q["sport"]).startswith("tennis") and q["bet"]
     and (q["status"] == "open" or q["status"] in ("won", "lost"))
     and (q["source"], q["sport"]) in by_lane and tennis_cards._kept(q, by_lane[(q["source"], q["sport"])])),
    key=lambda q: q["start"])
eq(len(picks), len(want), f"one line per open pick and per pick settled in the window, on the lane clocks ({len(want)})")
nxt = events.split('id="events-live"', 1)[0]
done = events.split('id="events-done"', 1)[1]
days = re.findall(r'<h4 class="sp-day-head">([^<]+)', nxt)
eq(days, ["Mon Oct 5", "Tue Oct 6", "Thu Oct 8"], "day heads once per day, soonest first; Later holds the far ones")
ok('<h4 class="sp-day-head">Mon Oct 5<small>Today</small></h4>' in nxt, "today is marked")
ok("Alpha vs Beta soonest" in html and "Alpha v Beta soonest" not in html, "a contest is spelt \"vs\"")
ok("Watch vs Only" not in html, "a stored fixture with no stake is not a pick")
ok("Yesterday vs Gone" in done and "Sun Oct 4" in done, "yesterday's settled pick is on the Completed tab under its day")
by_label = {}
for cls, source, body in picks:
    by_label[source + "|" + _text(body)[:40]] = (cls, body)
alpha = next(b for c, s_, b in picks if "Beta" in b and s_ == "tennis_fav_band_3h")
ok('<span class="sp-pos"><a href="https://polymarket.us/event/x" rel="noopener noreferrer" target="_blank">Beta</a></span>' in alpha
   or ('<span class="sp-pos">' in alpha and ">Beta<" in alpha and 'href="https://polymarket.us/event/x"' in alpha),
   "the pick is the player's name, linked to its market")
ok(">55¢<" in alpha, "the price is in cents")
ok("Favourite band · within 3h of the start" in alpha, "the rule name is on the line")
ok('sp-state is-next">upcoming<' in alpha, "a future pick is upcoming")
started = next(b for c, s_, b in picks if 'is-live' in c)
ok('sp-state is-live">in play<' in started, "a started open pick is in play")
ok("Started vs Running" in events.split('id="events-live"', 1)[1].split('id="events-done"', 1)[0], "and sits on the In progress tab")
ok('is-won">W<' in done and "Morning vs Winner" in done, "a pick won today is W")
ok('is-lost">L<' in done and "Morning vs Loser" in done, "a pick lost today is L")
combo2 = [b for c, s_, b in picks if s_ == "tennis_combo2"]
ok(combo2 and ">2-leg combo: Nuno Borges + Federico Cina<" in combo2[0],
   "a two-leg basket's pick names both legs")
ok("Combo · Kalshi" in nxt, "a basket's contest cell is its venue")
ok(combo2 and 'class="sp-legs"' not in combo2[0], "two legs need no second line")
combo3 = [b for c, s_, b in picks if s_ == "tennis_combo3"]
ok(combo3 and ">3-leg combo<" in combo3[0] and '<span class="sp-legs">Ann · Bob · Cid</span>' in combo3[0],
   "a three-leg basket lists its legs on one muted line under the pick")
ok('data-empty="next"' not in events, "the empty line is not printed when picks are open")
later = re.search(r'<details class="fold later"><summary>Later<span class="sm mut"> · (\d+) picks past 24 hours</span>', nxt)
ok(later is not None and later.group(1) == "2" and nxt.find("Iota vs Kappa later") > nxt.find("<details"),
   "the picks past 24 hours (Iota, the Polymarket basket) sit in the Later fold")

print("\nrules")
rules = _section(main, "rules")
ok("No tennis rule is in Production." in rules, "with nothing in Production the cards say so")
rule_rows = _rule_rows(rules)
eq(len(rule_rows), len(rows), f"one table row per tennis lane ({len(rows)})")
by_name = {r["name"]: r for r in rows}
order = [s_ for s_, _sp, _b in rule_rows]
eq(order, [r["name"] for r in sorted(rows, key=SP.sandbox_order)], "rows run by evidence, the too-early ones sunk")
ok(f'· {len(rows)} rules · {sum(1 for r in rows if SP.is_early(r))} too early to read · by evidence' in rules,
   "the fold's summary counts the rows and the too-early ones")
head = re.search(r"<thead>(.*?)</thead>", rules, re.S).group(1)
eq(re.findall(r"<th[^>]*>(.*?)</th>", head), ["Rule", "Market", "Record", "ROI after fees", "Won v priced", "Evidence", "Verdict"],
   "the columns are Rule · Market · Record · ROI after fees · Won v priced · Evidence · Verdict")
ok("<h3>" not in rules.split("<details", 1)[0], "no per-market H3 groups")
ok("PreresetBasket" not in html, "a basket struck before the reset clock never reaches the page")
for source, sport, body in rule_rows:
    row = by_name[source]
    ok(SP.roi_html(row) in body, f"{source} ROI is the Sandbox row's string")
    ok(SP.verdict_badge(row) in body, f"{source} verdict is the Sandbox row's string")
    eq(tennis_cards.roi_html(row).replace('<span class="mut">', "").replace("</span>", "") if not row["a"]["n"] else tennis_cards.roi_html(row),
       SP.roi_html(row).replace('<span class="mut">', "").replace("</span>", "") if not row["a"]["n"] else SP.roi_html(row),
       f"{source} ROI helper is the lane-row string")
    chev = re.search(r'aria-controls="([^"]+)"', body)
    detail = re.search(rf'<tr class="rule-detail" id="{chev.group(1)}" hidden>(.*?)</tr>', rules, re.S) if chev else None
    ok(detail is not None, f"{source} row has a chevron that expands")
    cell = detail.group(1) if detail else ""
    note = (row["meta"].get("note") or "").strip()
    lead, rest = SP.short_definition(note)
    ok(B.esc(lead) in cell, f"{source} row expands to its registered definition")
    ok(not rest or B.esc(rest) in cell, f"{source} the rest of the registration is folded, verbatim")
    changes = row["meta"].get("changes") or []
    if changes:
        ok(f'<details class="sp-changes"><summary>Changes · {len(changes)}</summary>' in cell,
           f"{source} dated changes are folded under the definition")
        ok(all(B.esc(c) in cell for c in changes), f"{source} every change entry is on the page, verbatim")
        ok(cell.index('<dl class="sp-params">') < cell.index('<p class="sp-def') < cell.index('<details class="sp-changes">'),
           f"{source} reads parameters, then the current definition, then the folded changes")
        ok(cell.find("WIDENED") == -1 or cell.find("WIDENED") > cell.find('<details class="sp-changes">'),
           f"{source} no reset text comes before the current definition")
    if source in S.TENNIS_FROZEN_RULES:
        ok('<span class="badge stage">Frozen 2026-10-08</span>' in body, f"{source} row carries the Frozen badge")
        ok(S.TENNIS_FROZEN_LINE in note, f"{source} definition ends with the FROZEN line")
        ok("<dt>Backs</dt>" in cell and "<dt>Venue</dt>" in cell, f"{source} prints its current parameters")
        if sport == "tennis":
            ok("70–85¢" in cell and "within 3h" in cell and "ATP, WTA Doubles, UTR" in cell,
               f"{source} parameters are the band, window and tours from the registered constants")
        else:
            legs = int(source[-1])
            ok(f"{legs} favourite-band legs as one contract" in cell, f"{source} parameters name its leg count")
            ok(("extrapolated" in cell) == (sport == "tennis_pmcombo" and legs > 2),
               f"{source} says whether its markup was measured")
    combo = sport in ("tennis_combo", "tennis_pmcombo")
    eq('<span class="badge stage">Combo</span>' in body, combo, f"{source} Combo badge follows the market")
cells = {s_: re.findall(r"<td[^>]*>(.*?)</td>", b, re.S) for s_, _sp, b in rule_rows}
eq(_text(cells["tennis_combo2"][1]), "Kalshi", "a Kalshi basket's venue is Kalshi")
eq(_text(cells["pm_combo2"][1]), "Polymarket US", "a Polymarket US basket's venue is Polymarket US")
eq(_text(cells["tennis_fav_band_3h"][1]), "Kalshi · Polymarket US",
   "the single-match rule names the venues of its own bets")
fav_a = by_name["tennis_fav_band_3h"]["a"]
eq(_text(cells["tennis_fav_band_3h"][2]), f'{fav_a["won"]}–{fav_a["n"] - fav_a["won"]}', "the record cell is W–L")
ok("· 5 open" in cells["tennis_fav_band_3h"][0], "the rule cell counts open bets")
ok("open" not in cells["pm_combo2"][0].split("</b>", 1)[1].split("<td", 1)[0] or "· 1 open" in cells["pm_combo2"][0], "the basket row counts its one open bet")
fav_detail = re.search(r'<tr class="rule-detail" id="' + re.search(r'aria-controls="([^"]+)"', cells["tennis_fav_band_3h"][0]).group(1) + r'" hidden>(.*?)</tr>', rules, re.S).group(1)
ok("Yesterday vs Gone" in fav_detail and "Alpha vs Beta soonest" in fav_detail,
   "the expanded rule lists its open and recent settled picks")
recent = re.search(r'<ul class="rule-picks">(.*?)</ul>', fav_detail, re.S)
ok(recent is not None and recent.group(1).count("<li") <= 5 + tennis_cards.RECENT_LIMIT, "recent picks are capped at the open ones plus the limit")

print("\nmethod")
method = _section(main, "method")
ok(method.lstrip().startswith("<details><summary>") and "<details open" not in method.split("</summary>", 1)[0],
   "the venue note is a fold, closed by default")
ok('id="listing"' in method, "the Polymarket US listing table is inside the fold")
ok(len(re.findall(r"<p class=\"sm\">", method)) == 2, "the note is two sentences")

print("\nempty ledger")
empty = tennis_build.build({"quotes": []}, {"pairs": {}}, NOW)
for anchor in ("events", "rules", "method"):
    ok(f'id="{anchor}"' in empty, f"an empty page keeps #{anchor}")
ok('class="sp-pick' not in empty and "No tracked tennis match" not in empty,
   "an empty page has no pick lines and no empty boxes")
nxt_check = tennis_cards.next_check(NOW)
ok(nxt_check is not None and nxt_check > NOW, "the tracker workflow gives a next firing")
ok(f"next check {fmt.when(nxt_check)}" in empty, "the Next 24h empty state names the next check")
ok("history still warming" in empty, "and says the registered rules are waiting for a qualifying contest")

print("\nnext check")
with tempfile.TemporaryDirectory() as tmp:
    wf = os.path.join(tmp, "wf.yml")
    with open(wf, "w", encoding="utf-8") as fh:
        fh.write('on:\n  schedule:\n    - cron: "11 2-23/3 * * *"\n    - cron: "11 18 * * *"\n')
    at = datetime.datetime(2026, 10, 7, 17, 30, tzinfo=timezone.utc)
    eq(tennis_cards.next_check(at, wf), datetime.datetime(2026, 10, 7, 18, 11, tzinfo=timezone.utc),
       "the extra 18:11 slot is read")
    at = datetime.datetime(2026, 10, 7, 23, 30, tzinfo=timezone.utc)
    eq(tennis_cards.next_check(at, wf), datetime.datetime(2026, 10, 8, 2, 11, tzinfo=timezone.utc),
       "after the last slot the next one is tomorrow")
    eq(tennis_cards.next_check(at, os.path.join(tmp, "missing.yml")), None,
       "a missing workflow is None, not a crash")

print("\ncricket and soccer stay on their own pages")
soc = soccer_build.build(d, st, NOW)
cri = cricket_build.build(d, st, NOW)
ok("Soccer Only vs Stay" not in html and "oddspedia" not in html.lower(),
   "the tennis page does not pick up soccer or cricket lanes")
ok('class="sp-sandbox-table"' in soc and "Soccer Only vs Stay" in soc,
   "soccer renders its own rules table and events")
ok("tennis_fav_band_3h" not in soc and "Alpha vs Beta soonest" not in soc,
   "soccer does not pick up tennis lanes")
ok('class="sp-sandbox-table"' in cri and "Oddspedia" in cri, "cricket renders its own rules table")
ok("tennis_fav_band_3h" not in cri and "Alpha vs Beta soonest" not in cri,
   "cricket does not pick up tennis lanes")

css = open(os.path.join(ROOT, "public_site", "site.css"), encoding="utf-8").read()
ok(".sp-day-head {" in css and "position: sticky;" in css.split(".sp-day-head {", 1)[1].split("}", 1)[0],
   "the day head is sticky")
ok(".sp-pick {" in css and "@media (max-width: 760px)" in css.split(".sp-pick {", 1)[1],
   "the picks list has a phone layout")
ok(".tn-" not in css and ".tennis-desk" not in css, "the earlier tennis rules are retired with the pages that used them")


def _filtered_quote(i, source, sport, status, logged, label, league, tier, market_id,
                    bet=True, start=None):
    """One tennis quote. `logged` is the reset clock's own comparison string."""
    when = start or logged
    won = status == "won"
    price = 0.55
    return dict(
        id=f"filter:{source}:{market_id}",
        source=source, sport=sport, bet=bet, status=status,
        pick="b", price=price,
        result="b" if status in ("won", "lost") and won else ("a" if status in ("won", "lost") else None),
        venue="kalshi",
        pnl=(round(100 * (1 / price - 1), 2) if won else -100.0) if status in ("won", "lost") else None,
        start=when, logged=logged, date=logged[:10],
        price_a=price, price_b=round(1 - price, 2),
        side_a="Yes", side_b="No",
        label=label, league=league, tier=tier,
        market_id=market_id,
        url="https://kalshi.com/markets/example",
    )


print("\nrefused tours and pre-reset rows stay off the tennis page")
fav_clock = S.TENNIS_FAV_KEEP_SINCE
combo_clock = S.TENNIS_COMBO_BAND_SINCE
fav_after = "2026-10-03T12:00:00+00:00"
fav_before = "2026-10-01T12:00:00+00:00"
combo_after = "2026-10-04T12:00:00+00:00"
combo_before = "2026-10-03T18:00:00+00:00"
KEPT_N = 2
GHOST_N = 4
filter_quotes = []
for i in range(KEPT_N):
    filter_quotes.append(_filtered_quote(
        i, "tennis_fav_band_3h", "tennis", "won", fav_after,
        f"Kept Atp Settled {i}", "ATP Kept League", "atp",
        f"aec-atp-kept-settled-{i}"))
    filter_quotes.append(_filtered_quote(
        i, "tennis_combo2", "tennis_combo", "won", combo_after,
        f"Kept Combo Settled {i}", "ATP Kept Combo", "atp",
        f"aec-atp-kept-combo-{i}"))
for i in range(GHOST_N):
    filter_quotes.append(_filtered_quote(
        i, "tennis_fav_band_3h", "tennis", "won", fav_after,
        f"GhostRefusedRow {i}", "GhostRefusedLeague", "wta",
        f"aec-wta-ghostrefused-{i}"))
    filter_quotes.append(_filtered_quote(
        i, "tennis_fav_band_3h", "tennis", "won", fav_before,
        f"GhostPreresetRow {i}", "GhostPreresetLeague", "atp",
        f"aec-atp-ghostprereset-{i}"))
    filter_quotes.append(_filtered_quote(
        i, "tennis_combo2", "tennis_combo", "won", combo_after,
        f"GhostComboRefused {i}", "GhostComboRefused", "wta",
        f"aec-wta-ghostcomborefused-{i}"))
    filter_quotes.append(_filtered_quote(
        i, "tennis_combo2", "tennis_combo", "lost", combo_before,
        f"GhostComboPrereset {i}", "GhostComboPrereset", "atp",
        f"aec-atp-ghostcomboprereset-{i}"))
filter_quotes.append(_filtered_quote(
    0, "tennis_fav_band_3h", "tennis", "open", fav_after,
    "GhostRefusedOpenLabel", "GhostRefusedLeague", "wta",
    "aec-wta-ghostrefused-open",
    start=(NOW + timedelta(hours=2)).isoformat()))
filter_quotes.append(_filtered_quote(
    1, "tennis_fav_band_3h", "tennis", "open", fav_after,
    "KeptOpenAtpLabel", "ATP Kept League", "atp",
    "aec-atp-kept-open",
    start=(NOW + timedelta(hours=3)).isoformat()))
filter_d = {"quotes": filter_quotes}
filter_st = {"pairs": {
    "tennis_fav_band_3h|tennis": {"stage": "sandbox", "since": fav_clock},
    "tennis_combo2|tennis_combo": {"stage": "sandbox", "since": combo_clock},
}}
filter_html = tennis_build.build(filter_d, filter_st, NOW)
filter_rows = _rows(filter_d, filter_st)
by_lane = {(r["name"], r["sport"]): r for r in filter_rows}
fav_row = by_lane.get(("tennis_fav_band_3h", "tennis"))
combo_row = by_lane.get(("tennis_combo2", "tennis_combo"))
ok(fav_row is not None and combo_row is not None,
   "the filtered fixture still lists the favourite band and the 2-leg combo")
if fav_row and combo_row:
    eq(fav_row["a"]["n"], KEPT_N, "the favourite-band record counts only kept tours logged after the reset")
    eq(combo_row["a"]["n"], KEPT_N, "the combo record counts only kept tours logged after its reset")
    frows = {s_: b for s_, _sp, b in _rule_rows(filter_html)}
    ok(SP.roi_html(fav_row) in frows.get("tennis_fav_band_3h", ""),
       "the favourite-band row ROI is the filtered lane row")
    ok(SP.roi_html(combo_row) in frows.get("tennis_combo2", ""),
       "the combo row ROI is the filtered lane row")
    ok("KeptOpenAtpLabel" in filter_html, "a kept open bet is on the page")
    ok("Kept Atp Settled 1" in filter_html, "a kept settled bet is on the page")
for ghost in ("GhostRefusedLeague", "GhostPreresetLeague",
              "GhostComboRefused", "GhostComboPrereset",
              "GhostRefusedRow", "GhostPreresetRow",
              "GhostRefusedOpenLabel",
              "aec-wta-ghostrefused", "aec-atp-ghostprereset",
              "aec-wta-ghostcomborefused", "aec-atp-ghostcomboprereset"):
    ok(ghost not in filter_html, f"{ghost} never reaches the tennis page")
ok("By competition" not in filter_html, "tennis does not add the soccer by-competition panel")
ok("within 3 hours of the scheduled start" in filter_html, "the 3-hour definition stays on the page")

if FAILS:
    print(f"\nSHA {SHA} FAILED {len(FAILS)}")
    sys.exit(1)
print(f"\nSHA {SHA} PASSED")
