#!/usr/bin/env python3
"""Offline checks (2026-11-05, Olu): the Soccer page in the Econ Daily layout.

Tiles, the scope and stage filters, the Production rules, the Sandbox rules, Events, the Retired fold, the method.
Every soccer lane is ONE row with the template's columns: the tracker's rules and the own-ledger lanes (label rules,
team scoring, the over 3.5 cheap NO, both goalless dips; the retired contenders and Argentina & Brasileirao over 1.5).
Layout only: each own-ledger row's record is the count its old section showed.
"""
import re
import sys

import arg_dip as A
import arg_dip_build as AB
import chaos_replay as CR
import o35_cheap_no as O
import o35_cheap_no_build as OB
import raised_stakes
import sandbox_audit
import soccer_build
import soccer_lanes as L
import soccer_rules as SR
import soccer_rules_build as SB
import soccer_rules_production as RP
import soccer_team_rules as TR
import soccer_team_rules_production as TRP

FAILS = []


def check(label, got, want):
    ok = got == want
    print(f"  {'ok  ' if ok else 'FAIL'} {label}" + ("" if ok else f" (got {got!r}, want {want!r})"))
    if not ok:
        FAILS.append(label)


html = soccer_build.build()
main = html[html.find("<main"):html.find("</main>")]

print("the layout: Econ Daily's")
check("sections in order: rules, events, retired, method", re.findall(r'<section id="([^"]+)"', main),
      ["rules", "events", "retired", "method"])
check("no stand-alone lane section is left", [x for x in ("cheap-side", "arg-dip", "top5-dip", "label-rules", "team-rules",
                                                         "contender-overs", "sa-o15") if f'<section id="{x}"' in html], [])
check("four tiles, the filters, a Production list and a closed Sandbox fold",
      (main.count('<div class="tile">'), 'data-filter="stage"' in main, 'data-list="production"' in main,
       '<details class="fold sp-sandbox" id="sandbox">' in main), (4, True, True, True))

rows = re.findall(r'<details class="sp-rule[^"]*"(?: id="([^"]+)")? data-source="([^"]+)" data-sport="([^"]+)"[^>]*data-stage="(\w+)"', main)
r_at, e_at, t_at = main.find('id="rules"'), main.find('id="events"'), main.find('id="retired"')
in_rules = re.findall(r'data-source="([^"]+)" data-sport="([^"]+)"[^>]*data-stage="(\w+)"', main[r_at:e_at])
in_retired = re.findall(r'<details class="sp-rule[^"]*"[^>]* data-source="([^"]+)"', main[t_at:])

print("\nevery soccer lane is one row")
srcs = {s for s, _sp, _st in in_rules}
prod = {s for s, _sp, st in in_rules if st == "production"}
for key in SR.RULES:
    src = RP.PAIRS[key][0] if key in RP.PAIRS else f"sr_{key.lower()}"
    where = "retired" if key in SR.RETIRED else "rules"
    check(f"label rule {key}: one row, in {where}", (src in in_retired) if where == "retired" else (src in srcs), True)
for key in TR.RULES:
    src = TRP.PAIRS[key][0] if key in TRP.PAIRS else f"st_{key.lower()}"
    where = "retired" if key in TR.RETIRED else "rules"
    check(f"team rule {key}: one row, in {where}", (src in in_retired) if where == "retired" else (src in srcs), True)
check("the Production label and team rules are Production rows", {RP.PAIRS[k][0] for k in RP.PAIRS} | {TRP.PAIRS[k][0] for k in TRP.PAIRS} <= prod, True)
check("the in-play lanes: the cheap NO (back in the Sandbox 2026-11-06) and the top-5 dip's live lane (back 2026-11-08) are Sandbox rows, with their ended live runs, both dips' paper lanes in the Sandbox",
      ("o35_cheap_no_wave" in prod, "top5_goalless_dip_live" in prod,
       {"arg_goalless_dip", "top5_goalless_dip", "o35_cheap_no_wave", "o35_cheap_no_v5", "o35_cheap_no_wave_live", "top5_dip_live_run"} <= srcs - prod), (False, False, True))
check("the Eredivisie draw is a row", "ere_draw" in srcs, True)
check("contenders and Argentina & Brasileirao over 1.5 are in the Retired fold",
      {"co_o15", "co_o25", "co_o35", "sa_o15_arg", "sa_o15_bra"} <= set(in_retired), True)
check("Turkey's two lanes are in the Retired fold", {"turkey_o25_dog", "turkey_btts_dog"} <= set(in_retired), True)
check("no row twice in the rule tables", len(in_rules), len(set(in_rules)))
check("the old links still land on their rows", {i for i, *_ in rows if i} >= {"cheap-side", "arg-dip", "top5-dip"}, True)

print("\nlayout only: each record is its old section's count")
st = SR.load()
for key in SR.RULES:
    picks = (st["rules"].get(key) or {}).get("picks") or []
    n, won, roi = SB._record(picks)
    a = L.pick_record(picks)
    check(f"{key}: settled, won and ROI as the section counted them", (a["n"] + a["n_price"], a["won"], a["roi_fee"]), (n, won, roi))
o = O.load()
entries = [e for e in o["entries"] if e.get("version") == O.VERSION]
s = CR.stats([r for r in O.trade_rows(entries, field="honest") if r["variant"] == OB.HEAD])
cheap = L.o35_row(o)["a"]
check("the cheap NO's record is the headline exit, re-scored under the honesty rules (filled, won, ROI)", (cheap["n"], cheap["won"], cheap["roi_fee"]), (s["n"], s["won"], s["roi"]))
for page in AB.PAGES:
    ps = AB.load_state(page)
    es = [e for e in ps.get("entries") or [] if e.get("buys") is not None]
    sm = A.summary(es, page["cfg"]["headline"])
    a = L.dip_row(page)["a"]
    check(f"{page['id']}: the headline buy's fills and ROI", (a["n"], a["roi_fee"]), (sm["fills"], sm["roi"]))
check("an in-play exit has no priced-win count: a dash", re.search(
    r'data-source="o35_cheap_no_wave".*?data-l="Won v priced">([^<]*)<', main, re.S).group(1), "—")

print("\nthe row's fold holds the words, collapsed")
k = main.find('id="cheap-side"')
fold = main[k:main.find('</details>', main.find('class="sp-details-body"', k))]
check("the cheap NO row is closed on load", main[k - 40:k].count(" open") == 0 and ' open' not in main[k:k + 30], True)
for word in ("<b>Exits</b>", "<b>Honest re-score by version</b>", "<b>Live run</b>", "<b>Before the honesty rules</b>", "<b>Fills</b>", "First-half fills", "v3", "v2", "v1"):
    check(f"its fold has {word!r}", word in OB.panel(o), True)
check("the dips' folds carry the buy levels and the in-sample research",
      all("<b>Buy levels</b>" in AB.panel(AB.load_state(p), p) for p in AB.PAGES)
      and 'id="top5-dip-insample"' in AB.panel(AB.load_state(AB.TOP5_PAGE), AB.TOP5_PAGE), True)
check("a label rule's fold lists every entry", "<b>Entries</b>" in main, True)

print("\nraised stake: a badge, no amount")
check("mls_fade_home carries it", bool(re.search(r'data-source="mls_fade_home" data-sport="soccer_p05"[^>]*data-stage="production">'
                                                 r'.*?Raised stake</span>', main[:main.find("</summary>", main.find('data-source="mls_fade_home"'))], re.S)), True)
check("only listed pairs carry it", main.count(">Raised stake<"),
      sum(1 for s_, sp, stg in set(in_rules) if stg == "production" and raised_stakes.raised(f"{s_}|{sp}")))
check("no guarded phrase or dollar amount in the badge or the method note",
      (sandbox_audit.COPY_RE.search(main[main.find('id="method"'):]), "$" in ">Raised stake<"), (None, False))

print(f"\n{'ALL PASS' if not FAILS else str(len(FAILS)) + ' FAILED'}")
sys.exit(1 if FAILS else 0)
