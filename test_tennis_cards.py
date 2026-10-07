#!/usr/bin/env python3
"""The Tennis page: four tiles, one picks list, one rules table, one fold.

Presentation only. The verdict word and the ROI text are the Sandbox row's own
figures, compared as strings. Nothing here grades a bet or writes a ledger.
Soccer and Cricket keep their own cards; this file does not change those.
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

FAILS = []
ROOT = os.path.dirname(os.path.abspath(__file__))
NOW = datetime.datetime(2026, 10, 5, 16, 0, tzinfo=timezone.utc)


def _head_sha():
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT, text=True, stderr=subprocess.DEVNULL).strip()
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
    # Open single-match picks. Labels are stored with " v "; the page prints " vs ".
    # The sides name the players, so the pick is a player's name.
    opens = [
        (1, "Alpha v Beta soonest", "Alpha", "Beta"),
        (2, "Gamma v Delta second", "Gamma", "Delta"),
        (30, "Iota v Kappa later", "Iota", "Kappa"),
    ]
    for i, (hours, label, a, b) in enumerate(opens):
        quotes.append(_quote(100 + i, "tennis_fav_band_3h", "tennis", "open", hours, label,
                             side_a=a, side_b=b, venue="polymarket_us",
                             url="https://polymarket.us/event/x"))
    # One already started and still open: in play.
    quotes.append(_quote(110, "tennis_fav_band_3h", "tennis", "open", -1,
                         "Started v Running", side_a="Started", side_b="Running"))
    # Settled today (page clock 16:00Z is 11 AM CT on Oct 5): on the list with W / L.
    quotes.append(_quote(120, "tennis_fav_band_3h", "tennis", "won", -6,
                         "Morning v Winner", side_a="Morning", side_b="Winner"))
    quotes.append(_quote(121, "tennis_fav_band_3h", "tennis", "lost", -5,
                         "Morning v Loser", side_a="Morning", side_b="Loser"))
    # Settled yesterday: in the rule's recent picks, not on the day list.
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
    # Open on Polymarket US, far out, with a hostile label and url.
    quotes.append(_quote(400, "pm_combo2", "tennis_pmcombo", "open", 80,
                         '2-leg tennis combo: Rho <script>alert(1)</script> + "Sigma"', pick="a",
                         side_a="All 2 win", side_b="Any one loses", venue="combo",
                         url="javascript:alert(1)",
                         legs=_legs('Rho <script>alert(1)</script>', '"Sigma"')))
    # A stored fixture with no stake is not a pick and does not make a rule active.
    quotes.append(_quote(500, "tennis_combo4", "tennis_combo", "open", 12,
                         "Watch v Only", bet=False))
    # Baskets struck before the 4-leg rule's reset clock: they keep the row on the
    # page with an empty record, and never reach it as picks.
    for i in range(3):
        quotes.append(_quote(600 + i, "tennis_combo4", "tennis_combo", "won",
                             datetime.datetime(2026, 9, 20, 12 + i, tzinfo=timezone.utc),
                             f"PreresetBasket {i}", price=0.5))
    # Other families must not land on the Tennis page.
    quotes += _settled("o15_form_l10", "soccer_o15", n=4, won=3)
    quotes.append(_quote(900, "o15_form_l10", "soccer_o15", "open", 5, "Soccer Only v Stay"))
    quotes += _settled("oddspedia", "cricket", n=6, won=4, price=0.40)
    stages = {"pairs": {"tennis_combo4|tennis_combo": {"stage": "sandbox", "since": S.TENNIS_COMBO_BAND_SINCE}}}
    return {"quotes": quotes}, stages


def _rows(d, st):
    import sport_tab
    return sport_tab.family_rows(d, st, "Tennis")


def _roi_html(row):
    a = row["a"]
    if not a["n"]:
        return "—"
    thin = a["n"] < B.MIN_N
    klass = "mut" if thin else fmt.tone(a["roi_fee"], ".1f", 100)
    return f'<span class="{klass}">{B.pct(a["roi_fee"], sign=True)}</span>'


def _verdict_html(row):
    label, chip, _order = B.VERDICTS[row["v"]]
    return f'<span class="sig {chip}">{B.esc(label)}</span>'


def _picks(html):
    return re.findall(r'<div class="tn-pick ([^"]*)" data-source="([^"]*)"[^>]*>(.*?)</div>\s*(?=<div class="tn-(?:pick|day)|</div>)',
                      html, re.S)


def _rule_rows(html):
    return re.findall(r'<tr data-source="([^"]+)" data-sport="([^"]+)">(.*?)</tr>', html, re.S)


def _text(fragment):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", fragment)).strip()


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
ok("<h1>Tennis</h1>" in main and "Match-winner picks and combo baskets · times CT" in main,
   "the header is the title and one line")
ok('id="matches"' in main and 'id="rules"' in main and 'id="system"' in main,
   "the page has Matches, Rules and System sections")
toc = re.search(r'<nav class="toc"[^>]*>(.*?)</nav>', html, re.S)
eq(re.findall(r">([^<]+)</a>", toc.group(1)) if toc else None, ["Matches", "Rules", "System"],
   "the jump pills are Matches / Rules / System")
for gone in ('id="today"', 'id="upcoming"', 'id="in-play"', 'id="combos"', "No tracked tennis match",
             "rule-card", "rule-grid", "tennis-combo-grid", "How each rule is defined", "Match center"):
    ok(gone not in main, f"{gone} is gone")
ok(main.count("<h2>") == 2, "two headings: Matches and Rules; System is a fold")
ok("<script" not in main.lower(), "the page body does not grow an inline script")
ok("javascript:" not in html, "a javascript: url is not written")
ok("&lt;script&gt;" in html, "a hostile label is escaped")

print("\ntiles")
tiles = re.findall(r'<div class="tile">(.*?)</div>', main, re.S)
eq(len(tiles), 4, "four stat tiles")
labels = [re.search(r"<span>(.*?)</span>", t).group(1) for t in tiles]
eq(labels, ["open picks", "active rules", "record · active rules", "ROI after fees"],
   "the tiles are open picks · active rules · record · ROI")
open_n = sum(1 for q in d["quotes"] if str(q["sport"]).startswith("tennis")
             and q["bet"] and q["status"] == "open")
eq(_text(tiles[0]), f"{open_n} open picks", "open picks counts every open tennis bet")
active = [r for r in rows if r["a"]["n"] or r["open"]]
eq(_text(tiles[1]), f"{len(active)} active rules", "a rule is active once it has fired")
won = sum(r["a"]["won"] for r in active)
n = sum(r["a"]["n"] for r in active)
eq(_text(tiles[2]), f"{won}–{n - won} record · active rules", "the record is W–L across active rules")
roi = sum((r["a"]["roi_fee"] or 0) * r["a"]["n"] for r in active) / n
ok(B.pct(roi, sign=True) in tiles[3], "ROI after fees is the pooled flat-stake ROI")
ok('class="mut"' in tiles[3], f"the pooled ROI is grey under the read floor ({n} < {B.MIN_N})")

print("\npicks")
picks = _picks(html)
want = sorted(
    (q for q in d["quotes"] if str(q["sport"]).startswith("tennis") and q["bet"]
     and (q["status"] == "open" or fmt.chicago(q["start"]).date() == fmt.chicago(NOW).date())),
    key=lambda q: q["start"])
eq(len(picks), len(want), f"one line per open pick and per pick settled today ({len(want)})")
eq([p[1] for p in picks], [q["source"] for q in want], "picks are chronological, soonest first")
days = re.findall(r'<div class="tn-day">([^<]+)</div>', html)
eq(days, ["Today · Oct 5", "Tomorrow · Oct 6", "Oct 8"], "day headers once per day, in order")
ok("Alpha vs Beta soonest" in html and "Alpha v Beta soonest" not in html,
   "a contest is spelt \"vs\"")
ok("Watch vs Only" not in html, "a stored fixture with no stake is not a pick")
ok("Yesterday vs Gone" not in main.split('id="rules"')[0], "yesterday's settled pick is not on the list")
by_label = {}
for cls, source, body in picks:
    by_label[_text(re.search(r'<span class="tn-match">(.*?)</span>', body, re.S).group(1))] = (cls, body)
alpha = by_label.get("Alpha vs Beta soonest", ("", ""))
ok('<span class="tn-pos"><b>Beta</b></span>' in alpha[1], "the pick is the player's name")
ok(">55¢<" in alpha[1], "the price is in cents")
ok("Favourite band · within 3h of the start" in alpha[1], "the rule name is on the line")
ok('tn-state is-next">upcoming<' in alpha[1], "a future pick is upcoming")
ok('href="https://polymarket.us/event/x"' in alpha[1], "the contest links to its market")
started = by_label.get("Started vs Running", ("", ""))
ok('tn-state is-live">in play<' in started[1], "a started open pick is in play")
ok('is-won">W<' in by_label.get("Morning vs Winner", ("", ""))[1], "a pick won today is W")
ok('is-lost">L<' in by_label.get("Morning vs Loser", ("", ""))[1], "a pick lost today is L")
combo2 = [b for c, s, b in picks if s == "tennis_combo2"]
ok(combo2 and "<b>2-leg combo: Nuno Borges + Federico Cina</b>" in combo2[0],
   "a two-leg basket's pick names both legs")
ok(combo2 and 'class="tn-match"><a href="https://kalshi.com/combos"' in combo2[0]
   and "Combo · Kalshi" in combo2[0], "a basket's contest cell is its venue, linked")
ok(combo2 and 'class="tn-legs"' not in combo2[0], "two legs need no second line")
combo3 = [b for c, s, b in picks if s == "tennis_combo3"]
ok(combo3 and "<b>3-leg combo</b>" in combo3[0] and '<span class="tn-legs">Ann · Bob · Cid</span>' in combo3[0],
   "a three-leg basket lists its legs on one muted line under the pick")
ok("No open pick" not in main, "the empty line is not printed when picks are open")

print("\nrules")
rule_rows = _rule_rows(html)
eq(len(rule_rows), len(rows), f"one table row per tennis lane ({len(rows)})")
active_names = [(r["name"], r["sport"]) for r in active]
inactive_rows = [r for r in rows if (r["name"], r["sport"]) not in active_names]
toggle = re.search(r'<details class="section-disclosure historical tn-inactive"><summary><b>([^<]+)</b>', html)
ok(inactive_rows and all(not r["a"]["n"] and not r["open"] for r in inactive_rows),
   f"the fixture has a never-fired rule ({[r['name'] for r in inactive_rows]})")
eq(toggle.group(1) if toggle else None,
   f"Show {len(inactive_rows)} inactive rule{'s' if len(inactive_rows) != 1 else ''}",
   "the never-fired rules sit behind a Show N inactive rules toggle")
ok("PreresetBasket" not in html, "a basket struck before the reset clock never reaches the page")
before = html.split("tn-inactive", 1)[0]
after = html.split("tn-inactive", 1)[-1]
eq(sorted(s for s, _sp, _b in _rule_rows(before)), sorted(r["name"] for r in active),
   "the open table holds the active rules")
eq(sorted(s for s, _sp, _b in _rule_rows(after)), sorted(r["name"] for r in inactive_rows),
   "the toggle holds the inactive rules")
order = [s for s, _sp, _b in _rule_rows(before)]
by_name = {r["name"]: r for r in rows}
want_order = sorted(order, key=lambda s: (
    not by_name[s]["prod"],
    -(by_name[s]["a"]["roi_fee"] if by_name[s]["a"]["n"] else float("-inf")),
    -by_name[s]["a"]["n"], s))
eq(order, want_order, "active rules are Production first, then by ROI")
head = re.search(r"<tr><th>Rule</th>.*?</tr>", html, re.S)
eq(_text(head.group(0)) if head else None, "Rule Venue Record ROI Verdict Open",
   "the columns are Rule · Venue · Record · ROI · Verdict · Open")
ok("<h3>" not in main, "no per-market H3 groups")
for source, sport, body in rule_rows:
    row = by_name[source]
    ok(_roi_html(row) in body, f"{source} ROI is the Sandbox row's string")
    ok(_verdict_html(row) in body, f"{source} verdict is the Sandbox row's string")
    eq(tennis_cards.roi_html(row), _roi_html(row), f"{source} ROI helper is the lane-row string")
    eq(tennis_cards.verdict_html(row), _verdict_html(row), f"{source} verdict helper is the lane-row string")
    note = (row["meta"].get("note") or "").strip()
    ok(B.esc(note) in body, f"{source} row expands to its registered definition")
    eq(html.count(B.esc(note)), 1, f"{source} definition appears once on the page")
    combo = sport in ("tennis_combo", "tennis_pmcombo")
    eq('<span class="sig n">Combo</span>' in body, combo, f"{source} Combo badge follows the market")
    ok('<details class="tn-rule"><summary>' in body, f"{source} row has a chevron that expands")
cells = {s: re.findall(r"<td[^>]*>(.*?)</td>", b, re.S) for s, _sp, b in rule_rows}
eq(_text(cells["tennis_combo2"][1]), "Kalshi", "a Kalshi basket's venue is Kalshi")
eq(_text(cells["pm_combo2"][1]), "Polymarket US", "a Polymarket US basket's venue is Polymarket US")
eq(_text(cells["tennis_fav_band_3h"][1]), "Kalshi · Polymarket US",
   "the single-match rule names the venues of its own bets")
fav_a = by_name["tennis_fav_band_3h"]["a"]
eq(_text(cells["tennis_fav_band_3h"][2]), f'{fav_a["won"]}–{fav_a["n"] - fav_a["won"]}', "the record cell is W–L")
eq(_text(cells["tennis_fav_band_3h"][5]), "4", "the open cell counts open bets")
eq(_text(cells["tennis_combo4"][5]), "—", "a rule with no open bet shows a dash")
fav = cells["tennis_fav_band_3h"][0]
ok("Yesterday vs Gone" in fav and "Alpha vs Beta soonest" in fav,
   "the expanded rule lists its open and recent settled picks")
ok(fav.count("<li>") <= 4 + tennis_cards.RECENT_LIMIT, "recent picks are capped")

print("\nsystem")
system = re.search(r'<section id="system" class="tn-system">(.*?)</section>', html, re.S).group(1)
ok(system.startswith("\n<details><summary>") and "<details open" not in system,
   "the venue note is a fold, closed by default")
ok('id="listing"' in system, "the Polymarket US listing table is inside the fold")
ok(len(re.findall(r"<p class=\"sm\">", system)) == 2, "the note is two sentences")

print("\nempty ledger")
empty = tennis_build.build({"quotes": []}, {"pairs": {}}, NOW)
for anchor in ("matches", "rules", "system"):
    ok(f'id="{anchor}"' in empty, f"an empty page keeps #{anchor}")
ok('class="tn-pick' not in empty and "No tracked tennis match" not in empty,
   "an empty page has no pick lines and no empty boxes")
nxt = tennis_cards.next_check(NOW)
ok(nxt is not None and nxt > NOW, "the tracker workflow gives a next firing")
ok(f'<p class="tn-empty">No open pick · next check {fmt.when(nxt)}</p>' in empty,
   "the empty state is one line with the next check")
ok("No tennis rule has a record yet." in empty, "no rows is a note, not a table")

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
ok('class="rule-card"' in soc and "Soccer Only vs Stay" in soc, "soccer still renders its own rule cards")
ok("tennis_fav_band_3h" not in soc and "Alpha vs Beta soonest" not in soc,
   "soccer cards do not pick up tennis lanes")
ok('class="rule-card"' in cri and "Oddspedia" in cri, "cricket renders its own cards")
ok("tennis_fav_band_3h" not in cri and "Alpha vs Beta soonest" not in cri,
   "cricket does not pick up tennis lanes")

css = open(os.path.join(ROOT, "public_site", "site.css"), encoding="utf-8").read()
ok(".tn-day {" in css and "position: sticky;" in css.split(".tn-day {", 1)[1].split("}", 1)[0],
   "the day header is sticky")
ok(".tn-pick {" in css and "@media (max-width: 760px)" in css.split(".tn-pick {", 1)[1],
   "the picks list has a phone layout")
ok(".tennis-desk {" in css, "the earlier tennis rules are left in place, not edited")


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
    frows = {s: b for s, _sp, b in _rule_rows(filter_html)}
    ok(tennis_cards.roi_html(fav_row) in frows.get("tennis_fav_band_3h", ""),
       "the favourite-band row ROI is the filtered lane row")
    ok(tennis_cards.roi_html(combo_row) in frows.get("tennis_combo2", ""),
       "the combo row ROI is the filtered lane row")
    ok("KeptOpenAtpLabel" in filter_html, "a kept open bet is on the page")
    ok("Kept Atp Settled 1" in frows.get("tennis_fav_band_3h", ""),
       "a kept settled bet is in the rule's recent picks")
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
