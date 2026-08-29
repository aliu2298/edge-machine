#!/usr/bin/env python3
"""Export a PUBLIC, read-only picks board to public_site/index.html.

Scope (per user, Jul 25 2026): ONLY the next 3 open picks (when one settles the
next takes its slot) plus a collapsible list of results as picks conclude — no
bankroll/ledger/playbook. Each pick links to its game page on kalshi.com
(looked up from Kalshi's PUBLIC market API at export time; no auth, fail-soft).

Reads ONLY the predictions table. Never touches Kalshi private data (orders,
positions, balances) or any keys — safe to publish the output directory as-is.

Usage:  python3 export_public.py   →  public_site/index.html
Deploy: Netlify site 'edge-machine-picks' (re-run + redeploy after each slate/settle).
"""
import sqlite3, json, html, datetime, os

DB = os.path.join(os.path.dirname(__file__), "predictions.db")
OUT_DIR = os.path.join(os.path.dirname(__file__), "public_site")
# repo-tracked mirror of the predictions table ONLY (see load_rows)
MIRROR = os.path.join(os.path.dirname(__file__), "data", "predictions.json")

SETTLED = ("win", "loss", "half_win", "half_loss", "void")

# Never written to the public repo. The board is world-readable, and these disclose real
# money rather than anything a reader needs — performance is published to a 1-unit stake.
PRIVATE_FIELDS = {"stake"}

def profit(status, odds, stake):
    o, s = (odds or 0), (stake or 0)
    return {"win": s*(o-1), "loss": -s, "void": 0.0,
            "half_win": s/2*(o-1), "half_loss": -s/2}.get(status, 0.0)

PICKS_SHOWN = 3         # visible slots on the board
QUEUE_SIZE = 20         # picks baked into the page; "next" reveals them client-side
RESULTS_BACK_DAYS = 7   # keep concluded picks' results on the board for N days

# Kalshi company-quarterly picks (sport value below) are excluded from the public
# board and feed entirely — that lane has no page of its own.
EARNINGS_SPORT = "kalshi"

# Venue links live in venues.py so the boards, health.py and the slate share ONE matcher
# (see that module for the series/pagination/alias traps it encodes).
from venues import (fetch_kalshi_events, fetch_bovada_events, venue_link,  # noqa: F401
                    kalshi_series_counts, ALIASES, KALSHI_SERIES)


TAG_COLORS = {"best": "#f0b429", "value": "#3fb970", "lean": "#7aa2f7",
              "siege": "#c678dd", "tt-test": "#56b6c2", "coin-flip": "#888",
              "result": "#888"}

def esc(x): return html.escape(str(x if x is not None else ""))

def units(x, sign=False):
    """Render a result in UNITS, never currency.

    PRIVACY: this repo is public, so the board must not disclose real money. Stake sizes
    and dollar P&L are personal financial information — they reveal bankroll and betting
    volume — while conveying nothing a reader needs. Everything is normalised to one unit
    per pick (a win at 1.82 is +0.82u), which preserves the entire analytical picture —
    win rate, ROI, cumulative performance — with no absolute figure attached.

    `stake` is also stripped from data/predictions.json and public_site/picks.json for the
    same reason; see load_rows() and picks_feed().
    """
    if x is None: return "—"
    s = f"{abs(x):.2f}u"
    if x < 0: return f"−{s}"
    return f"+{s}" if sign else s


def profit_units(status, odds):
    """P&L to a ONE-UNIT stake, so absolute money never enters the export."""
    o = odds or 0
    return {"win": o - 1, "loss": -1.0, "void": 0.0,
            "half_win": (o - 1) / 2, "half_loss": -0.5}.get(status, 0.0)

def tone(x): return "pos" if (x or 0) >= 0 else "neg"

def tag_chip(tag):
    if not tag: return ""
    c = TAG_COLORS.get(tag, "#888")
    return f'<span class="chip" style="color:{c};border-color:{c}55;background:{c}18">{esc(tag)}</span>'

def status_chip(st):
    m = {"win": ("WIN", "pos"), "half_win": ("½ WIN", "pos"),
         "loss": ("LOSS", "neg"), "half_loss": ("½ LOSS", "neg"),
         "void": ("VOID", "mut"), "pending": ("PENDING", "warn")}
    t, cls = m.get(st, (st or "—", "mut"))
    return f'<span class="st {cls}">{t}</span>'

def short(name, n=14):
    name = name or ""
    return name if len(name) <= n else name[:n-1] + "…"

def grid_html(grid_json):
    """Only the PICKED score-group bucket — the other five are noise on the public board."""
    if not grid_json: return ""
    try: g = json.loads(grid_json)
    except Exception: return ""
    b = g.get("buckets") or {}
    h, a = short(g.get("home", "")), short(g.get("away", ""))
    labels = {"home_low": f"{h} 1-0·2-0·2-1", "away_low": f"{a} 1-0·2-0·2-1",
              "home_big": f"{h} 3-0·3-1·3-2", "away_big": f"{a} 3-0·3-1·3-2",
              "draw": "Draw 1-1·2-2·3-3", "other": "Any other"}
    picked = g.get("picked")
    if picked not in labels: return ""
    v = b.get(picked)
    odds = "" if v is None else f"<b>@{v:g}</b>"
    return (f'<div class="sg"><div class="sg-t">Score group · pred {esc(g.get("pred", ""))}</div>'
            f'<div class="sg-c pk"><span>{esc(labels[picked])}</span>{odds}</div></div>')

def pending_card(r, link_pair):
    ko = esc(r["kickoff"] or "")
    btns = "".join(
        f'<a class="kbtn {cls}" href="{esc(url)}" target="_blank" rel="noopener">{label} ↗</a>'
        for cls, label, url in [("", "Kalshi", link_pair.get("kalshi")),
                                ("bov", "Bovada", link_pair.get("bovada"))] if url)
    btns = f'<span class="btns">{btns}</span>' if btns else ""
    return f"""<div class="card" data-pick="{r["id"]}">
  <div class="row1"><span class="match">{esc(r["match"])}</span>{tag_chip(r["tag"])}{btns}</div>
  <div class="ko"><time data-utc="{ko}">{ko}</time></div>
  <div class="pick">{esc(r["pick"])}</div>
  <div class="nums"><span>@{r["odds"]:g}</span><span>1u stake</span><span>to win {units((r["odds"] or 1)-1)}</span></div>
  {grid_html(r["grid_json"])}
  {f'<div class="why">{esc(r["rationale"])}</div>' if r["rationale"] else ""}
  <button class="nextbtn" data-next="{r["id"]}">✓ Game finished — show next pick</button>
</div>"""

def settled_row(r):
    p = profit_units(r["status"], r["odds"])
    return f"""<tr>
  <td class="mut">{esc(r["event_date"])}</td>
  <td><div class="tmatch">{esc(r["match"])}</div><div class="tres mut">{esc(r["result_note"] or "")}</div></td>
  <td>{esc(r["pick"])}</td>
  <td class="tnum">{r["odds"]:g}</td>
  <td>{tag_chip(r["tag"])}</td>
  <td>{status_chip(r["status"])}</td>
  <td class="tnum {tone(p)}">{units(p, True)}</td>
</tr>"""

def picks_feed(rows):
    """ALL pending picks (not just the QUEUE_SIZE slice shown on the board) with the
    structured fields a downstream settler needs. `id` is the stable dedup key.
    Excludes Kalshi company-quarterly picks (see EARNINGS_SPORT)."""
    # NOTE: `stake` is deliberately absent — see units(). A downstream settler needs the
    # market and price, never how much money was on it.
    return [{"id": r["id"], "event_date": r["event_date"], "sport": r["sport"], "match": r["match"],
             "pick": r["pick"], "market": r["market"], "selection": r["selection"], "line": r["line"],
             "odds": r["odds"], "tag": r["tag"], "rationale": r["rationale"],
             "af_fixture_id": r["af_fixture_id"], "kickoff": r["kickoff"]}
            for r in rows if r["status"] == "pending" and r["sport"] != EARNINGS_SPORT]

def page_html(*, title, heading, subtitle, pend, settled, links, nav, now):
    """Render the public sports board — queue and results table."""
    page = f"""<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<meta name="description" content="Public read-only board — paper-tracked research, not betting advice.">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<style>
:root{{--bg:#0a0d14;--card:#10141d;--bd:#232936;--fg:#eef2f7;--mut:#8b94a7;
--pos:#3fb970;--neg:#e06c75;--warn:#f0b429}}
*{{box-sizing:border-box;margin:0}}
body{{background:var(--bg);color:var(--fg);font:15px/1.45 Inter,system-ui,sans-serif;
letter-spacing:-.011em;-webkit-font-smoothing:antialiased;padding:28px 16px 60px}}
.wrap{{max-width:860px;margin:0 auto}}
h1{{font-size:22px;font-weight:800;letter-spacing:-.02em}}
h2{{font-size:13px;font-weight:700;text-transform:uppercase;letter-spacing:.08em;color:var(--mut);margin:34px 0 12px}}
.sub{{color:var(--mut);font-size:13px;margin-top:4px}}
.mut{{color:var(--mut)}}.pos{{color:var(--pos)}}.neg{{color:var(--neg)}}.warn{{color:var(--warn)}}
.tnum{{font-variant-numeric:tabular-nums}}
.card{{background:var(--card);border:1px solid var(--bd);border-radius:12px;padding:16px;margin-bottom:12px}}
.row1{{display:flex;align-items:center;gap:8px;flex-wrap:wrap}}
.match{{font-weight:700;font-size:16px}}
.ko{{font-size:12px;color:var(--mut);margin-top:2px}}
.pick{{margin-top:8px;font-weight:600;color:var(--warn)}}
.nums{{display:flex;flex-wrap:wrap;gap:6px 16px;font-size:13px;color:var(--mut);margin-top:4px;font-variant-numeric:tabular-nums}}
.why{{font-size:12.5px;color:var(--mut);margin-top:10px;border-left:2px solid var(--bd);padding-left:10px}}
.nextbtn{{margin-top:12px;font:inherit;font-size:12px;font-weight:700;color:var(--mut);
background:none;border:1px dashed var(--bd);border-radius:8px;padding:7px 13px;cursor:pointer;width:100%}}
.nextbtn:hover{{color:var(--fg);border-color:var(--mut)}}
.chip{{font-size:10.5px;font-weight:700;text-transform:uppercase;letter-spacing:.05em;
border:1px solid;border-radius:999px;padding:2px 8px}}
.st{{font-size:10.5px;font-weight:800;letter-spacing:.05em}}
.sg{{margin-top:12px}}.sg-t{{font-size:11px;text-transform:uppercase;letter-spacing:.07em;color:var(--mut);margin-bottom:6px}}
.sg-c{{display:inline-flex;align-items:center;gap:10px;font-size:12px;
background:#0c1017;border:1px solid var(--bd);border-radius:8px;padding:6px 11px}}
.sg-c b{{font-variant-numeric:tabular-nums;color:var(--fg)}}
.sg-c.pk{{border-color:var(--pos);color:var(--fg);background:#12211a}}
table{{width:100%;border-collapse:collapse;font-size:13px}}
th{{text-align:left;font-size:10.5px;text-transform:uppercase;letter-spacing:.07em;color:var(--mut);
padding:6px 8px;border-bottom:1px solid var(--bd)}}
td{{padding:8px;border-bottom:1px solid #1a1f2b;vertical-align:top}}
.tmatch{{font-weight:600}}.tres{{font-size:11.5px}}
.tbl{{background:var(--card);border:1px solid var(--bd);border-radius:12px;padding:6px 10px;overflow-x:auto}}
.btns{{margin-left:auto;display:flex;gap:6px}}
.kbtn{{font-size:11.5px;font-weight:700;color:#7aa2f7;text-decoration:none;
border:1px solid #7aa2f755;background:#7aa2f714;border-radius:999px;padding:4px 11px;white-space:nowrap}}
.kbtn:hover{{background:#7aa2f72a}}
.kbtn.bov{{color:#e8564f;border-color:#e8564f55;background:#e8564f14}}
.kbtn.bov:hover{{background:#e8564f2a}}
details.res summary{{display:flex;align-items:center;gap:8px;cursor:pointer;list-style:none;user-select:none}}
details.res summary::-webkit-details-marker{{display:none}}
details.res summary h2{{margin:34px 0 12px}}
details.res .caret{{color:var(--mut);margin-top:22px;transition:transform .15s}}
details.res[open] .caret{{transform:rotate(90deg)}}
footer{{margin-top:40px;font-size:12px;color:var(--mut);text-align:center}}
.nav{{display:flex;gap:8px;margin-top:14px}}
.nav a{{font-size:12px;font-weight:700;text-decoration:none;color:var(--mut);
border:1px solid var(--bd);border-radius:999px;padding:5px 13px}}
.nav a:hover{{color:var(--fg);border-color:var(--mut)}}
.nav a.on{{color:var(--fg);border-color:var(--mut);background:#161b26}}
.mtbl{{background:var(--card);border:1px solid var(--bd);border-radius:12px;padding:6px 10px;overflow-x:auto}}
.mco{{font-weight:700}}
.mph{{color:var(--warn);font-weight:600}}
.msp{{font-size:11px;color:var(--mut)}}
.mlink{{font-size:11px;font-weight:700;color:#3fb970;text-decoration:none;
border:1px solid #3fb97055;background:#3fb97014;border-radius:999px;padding:3px 9px;white-space:nowrap}}
.mlink:hover{{background:#3fb9702a}}
.note{{font-size:12px;color:var(--mut);margin:-4px 0 14px;line-height:1.5}}
.mday{{margin-bottom:16px}}
.mdate{{font-size:12px;font-weight:800;letter-spacing:.04em;text-transform:uppercase;
color:var(--fg);border-bottom:1px solid var(--bd);padding-bottom:5px;margin-bottom:8px}}
.mrow{{background:var(--card);border:1px solid var(--bd);border-radius:10px;
padding:10px 12px;margin-bottom:7px}}
.mhead{{display:flex;align-items:center;gap:8px;flex-wrap:wrap}}
.mco{{font-weight:800;font-size:13px}}
.mph{{color:var(--warn);font-weight:700;font-size:14px}}
.msp{{font-size:11px;color:var(--mut)}}
.mlean{{font-size:11px;color:var(--mut);border:1px solid var(--bd);border-radius:999px;padding:2px 8px}}
.vtake{{font-size:10.5px;font-weight:800;color:var(--pos);border:1px solid #3fb97055;
background:#3fb97014;border-radius:999px;padding:2px 8px}}
.vthin{{font-size:10.5px;font-weight:800;color:var(--warn);border:1px solid #f0b42955;
background:#f0b42914;border-radius:999px;padding:2px 8px}}
.vpass{{font-size:10.5px;font-weight:800;color:var(--mut);border:1px solid var(--bd);
border-radius:999px;padding:2px 8px}}
.vheld{{font-size:10.5px;font-weight:800;color:#0a0d14;background:var(--pos);
border-radius:999px;padding:2px 8px}}
.fmt{{font-size:10px;border-radius:999px;padding:2px 8px;border:1px solid}}
.fmt.fgood{{color:var(--pos);border-color:#3fb97044;background:#3fb9700f}}
.fmt.fbad{{color:var(--neg);border-color:#e06c7544;background:#e06c750f}}
.fmt.funk{{color:var(--mut);border-color:var(--bd)}}
.mwhy{{font-size:12.5px;color:var(--mut);margin-top:7px;border-left:2px solid var(--bd);
padding-left:10px;line-height:1.5}}
.mlink{{font-size:11px;font-weight:700;color:#3fb970;text-decoration:none;
border:1px solid #3fb97055;background:#3fb97014;border-radius:999px;padding:3px 9px;
white-space:nowrap;margin-left:auto}}
.mlink:hover{{background:#3fb9702a}}
@media (max-width:540px){{
  body{{padding:18px 10px 44px;font-size:14px}}
  h1{{font-size:19px}}
  .card{{padding:13px}}
  .match{{font-size:15px}}
  .btns{{margin-left:0;width:100%;justify-content:flex-start;margin-top:2px}}
  .kbtn{{padding:5px 12px}}
  th,td{{padding:6px 5px;font-size:12px}}
  .why{{font-size:12px}}
}}
</style></head><body><div class="wrap">
<h1>{heading}</h1>
<div class="sub">{subtitle} · updated {now}</div>
{nav}
<h2>Current picks <span id="qleft"></span></h2>
{"".join(pending_card(r, links[r["id"]]) for r in pend) or '<div class="mut">No open picks right now — check back after the next slate.</div>'}
<div class="mut" id="qempty" style="display:none">Queue finished — check back after the next slate.</div>
<details class="res">
<summary><h2>Recent results ({len(settled)})</h2><span class="caret">▸</span></summary>
{f'''<div class="tbl"><table>
<tr><th>Date</th><th>Match</th><th>Pick</th><th>Odds</th><th>Lane</th><th>Result</th><th>P&amp;L to 1u</th></tr>
{"".join(settled_row(r) for r in settled)}
</table></div>''' if settled else '<div class="mut">Nothing settled in the last week.</div>'}
</details>
<footer>Read-only static export · picks are paper-tracked research, not betting advice.</footer>
</div>
<script>
for (const t of document.querySelectorAll("time[data-utc]")) {{
  const d = new Date(t.dataset.utc);
  if (!isNaN(d)) t.textContent = d.toLocaleString([], {{weekday:"short",month:"short",day:"numeric",hour:"numeric",minute:"2-digit"}});
}}
// Pick queue: {QUEUE_SIZE} picks are baked in; show {PICKS_SHOWN} at a time.
// "Game finished — show next pick" hides the card (remembered per device via
// localStorage) and the next queued pick takes the slot. No redeploy needed.
(function () {{
  const KEY = "em-done-picks", SHOW = {PICKS_SHOWN};
  let done = new Set(JSON.parse(localStorage.getItem(KEY) || "[]"));
  const cards = [...document.querySelectorAll(".card[data-pick]")];
  function refresh() {{
    let shown = 0;
    for (const c of cards) {{
      const vis = !done.has(c.dataset.pick) && shown < SHOW;
      c.style.display = vis ? "" : "none";
      if (vis) shown++;
    }}
    const left = cards.filter(c => !done.has(c.dataset.pick)).length;
    document.getElementById("qleft").textContent = `(${{shown}} of ${{left}} queued)`;
    document.getElementById("qempty").style.display = left ? "none" : "";
  }}
  for (const b of document.querySelectorAll(".nextbtn")) {{
    b.addEventListener("click", () => {{
      done.add(b.dataset.next);
      localStorage.setItem(KEY, JSON.stringify([...done]));
      refresh();
    }});
  }}
  refresh();
}})();
</script></body></html>"""
    return page



NAV_SPORTS = ('<div class="nav"><a class="on" href="./">Sports</a>'
              '<a href="./streaks.html">Streaks</a></div>')


def load_rows():
    """Picks come from predictions.db on the Mac, or data/predictions.json in CI.

    ONLY the `predictions` table is ever mirrored into the repo. predictions.db also
    holds kalshi_orders / kalshi_bets / kalshi_config — private trading data that must
    never reach the public repo — so the raw .db stays gitignored and we export just
    this one table.

    STAKE IS STRIPPED FROM THE MIRROR. The repo is public, and stake sizes are personal
    financial information: 125 picks at $10-$75 disclose bankroll and betting volume to
    anyone who reads the file. Nothing on the board needs them — results render to one
    unit (see units()) — so the money never leaves this machine. `stake` stays available
    in memory for the local tracker; only the published copy drops it.
    """
    if os.path.exists(DB):
        c = sqlite3.connect(DB); c.row_factory = sqlite3.Row
        # NOTE: archived=1 only hides picks from the tracker's daily board — the
        # ledger/stats keep them (matches /api/stats), so no archived filter here.
        rows = [dict(r) for r in c.execute("SELECT * FROM predictions ORDER BY id DESC")]
        c.close()
        public = [{k: v for k, v in r.items() if k not in PRIVATE_FIELDS} for r in rows]
        os.makedirs(os.path.dirname(MIRROR), exist_ok=True)
        with open(MIRROR, "w") as f:                    # keep the repo copy in step
            json.dump({"exported_at": datetime.datetime.now(datetime.timezone.utc)
                       .isoformat(timespec="seconds"), "count": len(public),
                       "note": "stake omitted: results are published to a 1-unit stake",
                       "picks": public},
                      f, indent=1, default=str)
        print(f"  mirrored {len(public)} picks -> {MIRROR} (stake withheld)")
        return rows
    if os.path.exists(MIRROR):
        print(f"  no predictions.db — reading {MIRROR}")
        return json.load(open(MIRROR)).get("picks", [])
    raise SystemExit("no predictions.db and no data/predictions.json — nothing to build")


def build():
    rows = load_rows()

    today = datetime.date.today()
    back = (today - datetime.timedelta(days=RESULTS_BACK_DAYS)).isoformat()
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%b %d %Y · %H:%M UTC")

    def day_of(r, field):  # "2026-07-25T21:30Z" / "2026-07-25" → "2026-07-25"
        return (r[field] or r["event_date"] or "")[:10]

    kalshi_events = fetch_kalshi_events()
    bovada_events = fetch_bovada_events()

    def links_for(pend):
        links = {}
        for r in pend:
            if r.get("ext_link"):   # direct market link stored on the pick (Kalshi quarterlies)
                links[r["id"]] = {"kalshi": r["ext_link"], "bovada": None}
                continue
            ko = r["kickoff"] or r["event_date"]
            links[r["id"]] = {"kalshi": venue_link(r["match"], ko, kalshi_events),
                              "bovada": venue_link(r["match"], ko, bovada_events)}
            for venue, url in links[r["id"]].items():
                if not url:
                    print(f"  (no {venue} match found for: {r['match']})")
        return links

    def lane():
        sel = [r for r in rows if r["sport"] != EARNINGS_SPORT]
        pend = sorted([r for r in sel if r["status"] == "pending"],
                      key=lambda r: r["kickoff"] or "")[:QUEUE_SIZE]
        settled = [r for r in sel if r["status"] in SETTLED and day_of(r, "settled_at") >= back]
        return pend, settled

    os.makedirs(OUT_DIR, exist_ok=True)

    # ---- sports board (index.html) ----
    pend, settled = lane()
    links = links_for(pend)
    out = os.path.join(OUT_DIR, "index.html")
    with open(out, "w") as f:
        f.write(page_html(title="Edge Machine · Picks", heading="Edge Machine",
                          subtitle=f"The next {PICKS_SHOWN} picks + results as they conclude",
                          pend=pend, settled=settled, links=links, nav=NAV_SPORTS, now=now))
    print(f"wrote {out}  ({os.path.getsize(out)/1024:.0f} KB) — {len(pend)} sports picks, "
          f"{len(settled)} results (≥{back})")

    # ---- sports-only machine feed ----
    feed = picks_feed(rows)
    feed_out = os.path.join(OUT_DIR, "picks.json")
    with open(feed_out, "w") as f: json.dump(feed, f, indent=1)
    print(f"wrote {feed_out}  ({len(feed)} pending sports picks — earnings excluded)")

if __name__ == "__main__":
    build()
