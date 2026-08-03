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
import sqlite3, json, html, datetime, os, re, time, unicodedata, urllib.request, urllib.error

DB = os.path.join(os.path.dirname(__file__), "predictions.db")
OUT_DIR = os.path.join(os.path.dirname(__file__), "public_site")
# repo-tracked mirror of the predictions table ONLY (see load_rows)
MIRROR = os.path.join(os.path.dirname(__file__), "data", "predictions.json")

SETTLED = ("win", "loss", "half_win", "half_loss", "void")

def profit(status, odds, stake):
    o, s = (odds or 0), (stake or 0)
    return {"win": s*(o-1), "loss": -s, "void": 0.0,
            "half_win": s/2*(o-1), "half_loss": -s/2}.get(status, 0.0)

PICKS_SHOWN = 3         # visible slots on the board
QUEUE_SIZE = 20         # picks baked into the page; "next" reveals them client-side
RESULTS_BACK_DAYS = 7   # keep concluded picks' results on the board for N days

# Boards are kept SEPARATE (user directive Aug 2 2026): index.html is sports only,
# earnings.html is the Kalshi company-quarterlies lane. Picks split on this sport value.
EARNINGS_SPORT = "kalshi"

# ---------------------------------------------------------------- venue links
# Public, unauthenticated feeds only. Extend the lists as leagues open.
KALSHI_API = "https://api.elections.kalshi.com/trade-api/v2/events"
KALSHI_SERIES = ["KXBRASILEIROGAME", "KXMLSGAME", "KXUEFAGAME",
                 # per-match GAME series for the rest of the 10 tracked leagues
                 "KXEPLGAME", "KXLALIGAGAME", "KXBUNDESLIGAGAME", "KXSERIEAGAME",
                 "KXLIGUE1GAME", "KXEREDIVISIEGAME", "KXLIGAPORTUGALGAME", "KXUCLGAME"]
BOVADA_API = "https://www.bovada.lv/services/sports/event/coupon/events/A/description/soccer"
BOVADA_LEAGUES = ["north-america/united-states/mls",
                  "south-america/brazil/brasileirao-serie-a",
                  "international-club/uefa-champions-league",
                  "international-club/uefa-europa-league"]
# our team-name token → alternate token some venues use (tried alongside the raw token)
ALIASES = {"athletico": "paranaense", "angeles": "lafc"}
MONTHS = {m: i+1 for i, m in enumerate(
    ["JAN","FEB","MAR","APR","MAY","JUN","JUL","AUG","SEP","OCT","NOV","DEC"])}

def _norm(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9 ]", " ", s.lower())

def _get_json(url):
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"})
    with urllib.request.urlopen(req, timeout=10) as f:
        return json.load(f)

KALSHI_CACHE = os.path.join(os.path.dirname(__file__), "data", ".kalshi_events.json")
KALSHI_CACHE_TTL = 3600          # seconds
_KALSHI_MEM = None


def _kalshi_series_events(series, tries=4):
    """One series, with backoff on 429. Kalshi rate-limits hard once you query
    ~10 series back-to-back, and a silent failure just makes links disappear."""
    for i in range(tries):
        try:
            # no status filter: events leave "open" at kickoff, but their pages
            # keep working (and show the result) — the date check scopes matches
            return _get_json(f"{KALSHI_API}?series_ticker={series}&limit=200").get("events") or []
        except urllib.error.HTTPError as e:
            if e.code == 429 and i < tries - 1:
                time.sleep(1.5 * (i + 1))
                continue
            print(f"  (kalshi lookup skipped for {series}: {e})")
            return []
        except Exception as e:
            print(f"  (kalshi lookup skipped for {series}: {e})")
            return []
    return []


def fetch_kalshi_events():
    """[(url, title, date)] for Kalshi game events. Cached on disk so the two board
    builders in one CI run share a single fetch instead of doubling the request count."""
    global _KALSHI_MEM
    if _KALSHI_MEM is not None:
        return _KALSHI_MEM
    try:
        st = os.path.getmtime(KALSHI_CACHE)
        if time.time() - st < KALSHI_CACHE_TTL:
            raw = json.load(open(KALSHI_CACHE))
            _KALSHI_MEM = [(u, t, datetime.date.fromisoformat(d) if d else None)
                           for u, t, d in raw]
            print(f"  (kalshi events from cache: {len(_KALSHI_MEM)})")
            return _KALSHI_MEM
    except Exception:
        pass

    out = []
    for n, series in enumerate(KALSHI_SERIES):
        if n:
            time.sleep(0.4)                      # pace: stay under the rate limit
        events = _kalshi_series_events(series)
        for ev in events:
            t = ev.get("event_ticker") or ""
            m = re.search(r"-(\d{2})([A-Z]{3})(\d{2})", t)  # -26JUL25...
            d = None
            if m:
                yy, mon, dd = m.groups()
                try: d = datetime.date(2000+int(yy), MONTHS[mon], int(dd))
                except (KeyError, ValueError): pass
            out.append((f"https://kalshi.com/events/{t}", ev.get("title") or "", d))
    try:
        os.makedirs(os.path.dirname(KALSHI_CACHE), exist_ok=True)
        with open(KALSHI_CACHE, "w") as f:
            json.dump([(u, t, d.isoformat() if d else None) for u, t, d in out], f)
    except Exception:
        pass
    _KALSHI_MEM = out
    return out

def fetch_bovada_events():
    """[(url, title, date)] for upcoming Bovada soccer events. Empty on failure."""
    out = []
    for league in BOVADA_LEAGUES:
        try:
            groups = _get_json(f"{BOVADA_API}/{league}?marketFilterId=def&preMatchOnly=true&lang=en")
        except Exception as e:
            print(f"  (bovada lookup skipped for {league}: {e})")
            continue
        for grp in groups or []:
            for ev in grp.get("events") or []:
                d = None
                if ev.get("startTime"):
                    d = datetime.datetime.fromtimestamp(
                        ev["startTime"]/1000, datetime.timezone.utc).date()
                # The API's `link` is relative to the /sports app root — without
                # the prefix Bovada renders "page not found".
                out.append((f"https://www.bovada.lv/sports{ev.get('link','')}",
                            ev.get("description") or "", d))
    return out

def venue_link(match, kickoff, events):
    """URL of the venue's game page for `match`, or None if no confident match."""
    try:
        ko = datetime.date.fromisoformat((kickoff or "")[:10])
    except ValueError:
        return None
    sides = re.split(r"\s+vs?\.?\s+", match or "", flags=re.I)
    if len(sides) != 2: return None
    def side_hits(side, nt):
        for tok in _norm(side).split():
            cands = [tok, ALIASES.get(tok, tok)]
            if any(len(c) >= 4 and c in nt for c in cands):
                return True
        return False
    for url, title, d in events:
        if d is None or abs((d - ko).days) > 1: continue  # listing dates are ET/UTC-fuzzy
        nt = _norm(title)
        if all(side_hits(s, nt) for s in sides):
            return url
    return None

TAG_COLORS = {"best": "#f0b429", "value": "#3fb970", "lean": "#7aa2f7",
              "siege": "#c678dd", "tt-test": "#56b6c2", "coin-flip": "#888",
              "result": "#888"}

def esc(x): return html.escape(str(x if x is not None else ""))

def usd(x, sign=False):
    if x is None: return "—"
    s = f"${abs(x):,.2f}"
    if x < 0: return f"−{s}"
    return f"+{s}" if sign else s

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

def pending_card(r, link_pair, *, show_grid=True, done_label="✓ Game finished — show next pick"):
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
  <div class="nums"><span>@{r["odds"]:g}</span><span>{usd(r["stake"])} stake</span><span>to win {usd((r["stake"] or 0)*((r["odds"] or 1)-1))}</span></div>
  {grid_html(r["grid_json"]) if show_grid else ""}
  {f'<div class="why">{esc(r["rationale"])}</div>' if r["rationale"] else ""}
  <button class="nextbtn" data-next="{r["id"]}">{done_label}</button>
</div>"""

def settled_row(r):
    p = profit(r["status"], r["odds"], r["stake"])
    return f"""<tr>
  <td class="mut">{esc(r["event_date"])}</td>
  <td><div class="tmatch">{esc(r["match"])}</div><div class="tres mut">{esc(r["result_note"] or "")}</div></td>
  <td>{esc(r["pick"])}</td>
  <td class="tnum">{r["odds"]:g}</td>
  <td class="tnum">{usd(r["stake"])}</td>
  <td>{tag_chip(r["tag"])}</td>
  <td>{status_chip(r["status"])}</td>
  <td class="tnum {tone(p)}">{usd(p, True)}</td>
</tr>"""

def picks_feed(rows):
    """ALL pending picks (not just the QUEUE_SIZE slice shown on the board) with the
    structured fields a downstream settler needs. `id` is the stable dedup key.
    SPORTS ONLY — earnings live on their own page/feed (see EARNINGS_SPORT)."""
    return [{"id": r["id"], "event_date": r["event_date"], "sport": r["sport"], "match": r["match"],
             "pick": r["pick"], "market": r["market"], "selection": r["selection"], "line": r["line"],
             "odds": r["odds"], "stake": r["stake"], "tag": r["tag"], "rationale": r["rationale"],
             "af_fixture_id": r["af_fixture_id"], "kickoff": r["kickoff"]}
            for r in rows if r["status"] == "pending" and r["sport"] != EARNINGS_SPORT]

def page_html(*, title, heading, subtitle, pend, settled, links, nav, now,
              show_grid=True, done_label="✓ Game finished — show next pick",
              empty_msg="No open picks right now — check back after the next slate."):
    """Render one board. Called once per lane (sports / earnings) — the boards are
    deliberately separate, so each gets its own page, queue and results table."""
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
{"".join(pending_card(r, links[r["id"]], show_grid=show_grid, done_label=done_label) for r in pend) or f'<div class="mut">{empty_msg}</div>'}
<div class="mut" id="qempty" style="display:none">Queue finished — check back after the next slate.</div>
<details class="res">
<summary><h2>Recent results ({len(settled)})</h2><span class="caret">▸</span></summary>
{f'''<div class="tbl"><table>
<tr><th>Date</th><th>Match</th><th>Pick</th><th>Odds</th><th>Stake</th><th>Lane</th><th>Result</th><th>P&amp;L</th></tr>
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
              '<a href="./earnings.html">Earnings</a><a href="./tips.html">Tips</a></div>')
NAV_EARN = ('<div class="nav"><a href="./">Sports</a>'
            '<a class="on" href="./earnings.html">Earnings</a><a href="./tips.html">Tips</a></div>')


def load_rows():
    """Picks come from predictions.db on the Mac, or data/predictions.json in CI.

    ONLY the `predictions` table is ever mirrored into the repo. predictions.db also
    holds kalshi_orders / kalshi_bets / kalshi_config — private trading data that must
    never reach the public repo — so the raw .db stays gitignored and we export just
    this one table. Every field below is already shown on the public board.
    """
    if os.path.exists(DB):
        c = sqlite3.connect(DB); c.row_factory = sqlite3.Row
        # NOTE: archived=1 only hides picks from the tracker's daily board — the
        # ledger/stats keep them (matches /api/stats), so no archived filter here.
        rows = [dict(r) for r in c.execute("SELECT * FROM predictions ORDER BY id DESC")]
        c.close()
        os.makedirs(os.path.dirname(MIRROR), exist_ok=True)
        with open(MIRROR, "w") as f:                    # keep the repo copy in step
            json.dump({"exported_at": datetime.datetime.now(datetime.timezone.utc)
                       .isoformat(timespec="seconds"), "count": len(rows), "picks": rows},
                      f, indent=1, default=str)
        print(f"  mirrored {len(rows)} picks -> {MIRROR}")
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

    def lane(is_earnings):
        sel = [r for r in rows if (r["sport"] == EARNINGS_SPORT) == is_earnings]
        pend = sorted([r for r in sel if r["status"] == "pending"],
                      key=lambda r: r["kickoff"] or "")[:QUEUE_SIZE]
        settled = [r for r in sel if r["status"] in SETTLED and day_of(r, "settled_at") >= back]
        return pend, settled

    os.makedirs(OUT_DIR, exist_ok=True)

    # ---- sports board (index.html) ----
    pend, settled = lane(False)
    links = links_for(pend)
    out = os.path.join(OUT_DIR, "index.html")
    with open(out, "w") as f:
        f.write(page_html(title="Edge Machine · Picks", heading="Edge Machine",
                          subtitle=f"The next {PICKS_SHOWN} picks + results as they conclude",
                          pend=pend, settled=settled, links=links, nav=NAV_SPORTS, now=now))
    print(f"wrote {out}  ({os.path.getsize(out)/1024:.0f} KB) — {len(pend)} sports picks, "
          f"{len(settled)} results (≥{back})")

    # ---- earnings board (earnings.html) ----
    epend, esettled = lane(True)
    elinks = links_for(epend)
    eout = os.path.join(OUT_DIR, "earnings.html")
    with open(eout, "w") as f:
        f.write(page_html(title="Edge Machine · Earnings", heading="Edge Machine · Earnings",
                          subtitle="Company quarterlies — entry timed to the report date",
                          pend=epend, settled=esettled, links=elinks, nav=NAV_EARN, now=now,
                          show_grid=False,
                          done_label="✓ Reported — show next",
                          empty_msg="No open earnings positions — check back next reporting week."))
    print(f"wrote {eout}  ({os.path.getsize(eout)/1024:.0f} KB) — {len(epend)} earnings picks, "
          f"{len(esettled)} results (≥{back})")

    # ---- sports-only machine feed ----
    feed = picks_feed(rows)
    feed_out = os.path.join(OUT_DIR, "picks.json")
    with open(feed_out, "w") as f: json.dump(feed, f, indent=1)
    print(f"wrote {feed_out}  ({len(feed)} pending sports picks — earnings excluded)")

if __name__ == "__main__":
    build()
