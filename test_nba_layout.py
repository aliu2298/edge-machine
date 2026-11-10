#!/usr/bin/env python3
"""The NBA page in the Econ Daily layout (2026-11-05, Olu; it replaced the 2026-10-31 glance + lane cards):
tiles, the stage filter, Rules (one row per lane: the win margin YES split and NO fade), an empty Sandbox fold, Research
(observation only), Games, Retired, the method. Presentation only: the rows read the version 3 record the cards
headlined, and the Chaos index rows read the same."""
import json
import os
import re
import sys

import chaos_build as CB
import chaos_replay as C
import nba_layout as L
import nba_pace_build as NB
import nba_page as P
import nba_wm_nofade_build as NFB
import nba_wm_v3 as V3
import nba_wm_v4prod as V4P
import sandbox_audit

FAILS = []


def check(label, got, want):
    ok = got == want
    print(f"  {'ok  ' if ok else 'FAIL'} {label}" + ("" if ok else f" (got {got!r}, want {want!r})"))
    if not ok:
        FAILS.append(label)


if not os.path.exists(NB.SRC):
    print("no pace data; layout checks skipped")
    sys.exit(0)
page = NB.build(json.load(open(NB.SRC)))
main = page[page.find("<main"):]
ids = re.findall(r'<section id="([^"]+)"', main)
print("order")
check("rules, research (tracker, ladder), games (next 24h, results, teams), retired, method",
      ids, ["rules", "research", "tracker", "ladder", "games", "matchups", "graded", "teams", "retired", "method"])
check("the jump pills: Rules, Research, Games, Retired, Method",
      re.findall(r'href="#([^"]+)"', re.findall(r'<nav class="toc".*?</nav>', page, re.S)[0]), ["rules", "research", "games", "retired", "method"])
check("five tiles: open bets, active lanes, since-Production record and ROI, live record",
      [re.sub(r"<[^>]+>", "", t) for t in re.findall(r'<div class="tile"><b[^>]*>.*?</b><span>(.*?)</span>', main)][:5],
      ["open bets · live", "active lanes", "since Production · entries", "ROI after fees · since Production",
       [x for x in re.findall(r'<div class="tile"><b[^>]*>.*?</b><span>(.*?)</span>', main)][4]])
check("a stage filter (no scope chips)", ('data-filter="stage"' in main, 'data-filter="scope"' in main), (True, False))

print("\nthe Rules table")
r = main[main.find('<section id="rules"'):main.find('<section id="research"')]
rule_rows = re.findall(r'<details class="sp-rule[^"]*" id="([^"]+)" data-source="([^"]+)"[^>]*data-stage="(\w+)"', r)
check("one Production row per lane, linked as #wm-yes and #wm-no",
      sorted(x for x in rule_rows if x[2] == "production"),      # ranked by sample size, so the pair's order moves with the data
      [("wm-no", "nba_wm_nofade", "production"), ("wm-yes", "nba_winmargin_live", "production")])
check("two Sandbox rows (2026-11-08): the comparison, the version 3 YES rule and the 75% NO bid on paper",
      sorted((x[1], x[2]) for x in rule_rows if x[2] == "sandbox"), [("nba_wm_nofade_75", "sandbox"), ("nba_wm_yes_v3", "sandbox")])
check("columns: lane, market, record (games), entries won, ROI after fees, live fills, won v priced, evidence, verdict",
      [re.sub(r"<[^>]+>", "", c) for c in re.findall(r'<span class="sp-cell[^"]*">(.*?)</span>', r[r.find("sp-head-line"):r.find("</div>", r.find("sp-head-line"))])],
      ["Production rule", "Market", "Record (games)", "Entries won", "ROI after fees", "Live fills", "Won v priced", "Evidence", "Verdict"])
check("the Sandbox fold lists the two paper lanes", ("No NBA rule is in the Sandbox." in r, "Sandbox rules" in r), (False, True))
v3 = V3.load()
_v4p = V4P.load()
cur = _v4p if _v4p.get("since") else v3     # the record the page headlines: version 4 once it has a first night, else version 3
if cur.get("since"):
    yr = V3.yes_rows(cur)
    s = C.stats(yr)
    def _row(i):                       # one rule row, whatever order the rows are ranked in
        a = r.find(f'id="{i}"'); b = r.find('<details class="sp-rule', a + 1)
        return r[a:b if b > 0 else len(r)]
    yes = _row("wm-yes")
    check("YES: the version 3 record the card headlined (entries won, ROI, games for evidence)",
          (re.search(r'data-l="Entries won">([^<]*)<', yes).group(1), f'{s["won"]}/{s["n"]}',
           f'{len({x["event"] for x in yr})}/30' in yes), (f'{s["won"]}/{s["n"]}', f'{s["won"]}/{s["n"]}', True))
    g = V3.no_games(cur)
    no = _row("wm-no")
    check("NO fade: the version 3 games and ROI", (f'{C.stats(g)["n"]}/30' in no, L._pct(C.stats(g)["roi"]).replace("-", "−") in no
                                                     or L._pct(C.stats(g)["roi"]) in no), (True, True))
live = json.load(open("data/live_record.json")) if os.path.exists("data/live_record.json") else {}
yes_orders = (live.get("lanes") or {}).get("nba_wm_yes") or []
if yes_orders and all("src" in o for o in yes_orders):
    seg = r[r.find('id="wm-yes"'):r.find('<details class="sp-rule', r.find('id="wm-yes"') + 1)]
    check("YES live fills: the trades schema reads W–F–L, never 'exits pending'", ("exits pending" in seg, "legs 2x" in seg), (False, True))
elif yes_orders and not any(o["st"] == "sold" for o in yes_orders):
    check("YES live fills: held only, exits pending, until its sell fills are published",
          "exits pending" in r[r.find('id="wm-yes"'):r.find('id="wm-no"')], True)

print("\neach row's fold: the rule in two lines, the record, then collapsed sub-panels")
for anchor, want in (("wm-yes", ("Alternate exits", "Older versions", "In-sample research (not evidence)", "YES / NO overlap", "Last 30 trades")),
                     ("wm-no", ("Alternate exits", "Older versions", "In-sample research (not evidence)", "YES / NO overlap", "Last 30 trades"))):
    body = r[r.find(f'id="{anchor}"'):]
    nxt = body.find('<details class="sp-rule', 10)
    body = body[:nxt if nxt > 0 else len(body)]
    check(f"{anchor}: closed on load", re.search(rf'<details class="sp-rule[^"]*" id="{anchor}"[^>]*>', r).group(0).endswith(" open>"), False)
    check(f"{anchor}: two rule lines", body.count('class="sm sp-rule-line"'), 2)
    check(f"{anchor}: the sub-panels, in order", [t for t in re.findall(r"<summary><b>([^<]+)</b>", body) if t in want], list(want))
    check(f"{anchor}: no sub-panel starts open", [d for d in re.findall(r"<details[^>]*>", body)[1:] if " open" in d], [])
import nba_wm_nofade as N
nf = N.load()
latest = P.latest_read(C.load(), nf or {}, v3)
if P.stale_tag(nf.get("last_run"), latest):
    check("a table read well before the newest read on the page carries a stale tag with its read time",
          f'stale · last read {str(nf["last_run"])[:16].replace("T", " ")}Z' in r, True)
check("stale_tag: none inside the window, one past it",
      (P.stale_tag("2026-11-05T10:00:00+00:00", "2026-11-05T20:00:00+00:00"), bool(P.stale_tag("2026-11-04T22:15:00+00:00", "2026-11-05T23:52:00+00:00"))),
      ("", True))

print("\nresearch, games, retired, method")
res = main[main.find('<section id="research"'):main.find('<section id="games"')]
check("Research is one collapsed block, observation only, holding the tracker, the comeback line and the ladder",
      (res.split(">", 2)[1].startswith('<details class="fold nba-research"'), "observation only" in res, 'id="tracker"' in res,
       'id="comeback-spread"' in res, 'id="ladder"' in res), (True, True, True, True, True))
gm = main[main.find('<section id="games"'):main.find('<section id="retired"')]
check("Games: Next 24h, Results and the team reference, each folded (Upcoming starts collapsed, 2026-10-28)",
      ("<summary><b>Next 24h</b>" in gm, '<details class="section-disclosure nba-upcoming">' in gm,
       '<details class="section-disclosure nba-results">' in gm, '<details class="section-disclosure nba-teams">' in gm), (True, True, True, True))
ret = main[main.find('<section id="retired"'):main.find('<section id="method"')]
check("Retired is collapsed, one line per lane", ("nba-retired" in ret and " open" not in ret.split("<summary>")[0],
                                                   ret.count("<li data-lane=") == len(NB._retired_items())), (True, True))
check("the moneyline underdog's line is there with its record and reason",
      ('<li data-lane="nba_ml_dog_tp50"' in ret, "36 settled events, 10 won" in ret, "fair in 3 periods" in ret), (True, True, True))
meth = main[main.find('<section id="method"'):]
check("the method fold holds How these lanes are read", ('id="how-read"' in meth, " open" in meth.split("<summary>")[0]), (True, False))

print("\nthe Chaos index reads the record the NBA page headlines")
idx = CB.index(list(CB.with_config(C.load()).get("lanes", {}).values()))
cells = lambda lane: [re.sub(r"<[^>]+>", "", c) for c in re.findall(r"<td[^>]*>(.*?)</td>", re.search(rf'<tr data-lane="{lane}">(.*?)</tr>', idx, re.S).group(1))]  # noqa: E731
check("every index row has the header's 8 cells", {len(cells(x)) for x in ("nba_winmargin_live", "nba_wm_nofade")}, {8})
if cur.get("since"):
    g = V3.no_games(cur)
    fills = [x for x in cur["rows"].values() if x["lane"] == V3.NO_LANE and not x.get("no_entry") and "profit" in x]
    check("NO fade: v3 entries, games, entries won, ROI",
          cells("nba_wm_nofade")[2:6], [str(len(fills)), str(C.stats(g)["n"]), str(sum(1 for x in fills if x["profit"] > 0)), NFB.pct(C.stats(g)["roi"])])
    yr = V3.yes_rows(cur)
    check("YES split: v3 entries, games, won, ROI",
          cells("nba_winmargin_live")[2:6], [str(len(yr)), str(len({x["event"] for x in yr})), str(C.stats(yr)["won"]), CB._pct(C.stats(yr)["roi"], sign=True)])
check("the index links land on the new rows", (CB.home_href("nba_winmargin_live"), CB.home_href("nba_ml_dog_tp50"), './nba.html#wm-no' in NFB.index_row()),
      ("./nba.html#wm-yes", "./nba.html#retired", True))

print("\nstyle rules")
check("no inline style or SVG in the lanes (the NBA page forbids both)", ("style=" in r, "<svg" in r), (False, False))
check("public copy passes the guard", sandbox_audit.COPY_RE.search(r + res + meth), None)

print("\n" + ("ALL PASS" if not FAILS else f"{len(FAILS)} FAILED"))
sys.exit(1 if FAILS else 0)
