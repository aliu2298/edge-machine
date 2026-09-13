#!/usr/bin/env python3
"""today_build.py — every tracked fixture kicking off today, as the leads' CONTROL GROUP:
public_site/today.html.

WHAT THIS PAGE IS FOR
---------------------
The Leads board shows the fixtures the rules picked. Record measures them against "what
would have happened anyway" — but nowhere could you SEE the rest of the day's fixtures next
to the picked ones. This page is that set: every fixture on the Central day, in kickoff
order, marked as a lead or not, with the reason it is not, and with the book's line and
the model's probability on every one of them whether the rules fired or not. The same
numbers a lead card carries, on the fixtures the rules passed over.

Two things follow from that:

  * SORTED BY KICKOFF, not rarity. Rarity is shown on the chip, but every measurement on
    this board says a rare run predicts nothing beyond the team's own rate, so it must not
    decide the order of a "tonight" page.
  * MODEL-VALUE FLAGS ARE A TEST, NOT A TIP. A fixture is flagged where model.py beats the
    book's vig-free probability by streaks_track.VALUE_MARGIN — the same pre-registered
    split Record scores. Until that split has proved itself there, a flag is a hypothesis
    being counted, and the page says so.

THE DAY IS CENTRAL, NOT UTC
---------------------------
A 01:30Z kickoff is the previous evening in the Americas. Every board here renders in
Central; the day boundary has to agree with that or the page contradicts its own
timestamps. America/Chicago via zoneinfo, NOT a fixed UTC-5: the page's JavaScript uses
the IANA zone, and a fixed offset disagreed with it by an hour after the November change,
filing an 11:30pm CST kickoff on the next day.

WHAT IT READS, AND WHY
----------------------
  * LEADS FROM THE LEDGER (streak_leads.json, read-only), not the published board: the
    board lists upcoming leads only, so a lead vanished at kickoff and its fixture then
    claimed "no lead". Leads published this build but not yet logged are merged in.
  * IN-PLAY GAMES FROM THE LEDGERS. The ESPN feed keeps scheduled and finished games
    only; a match in progress is back-filled from the book and lead ledgers.
  * RESULTS. Graded leads and book markets carry hit/miss and flat-unit P/L, and a
    scoreboard sets leads beside every market the book priced, split by lead fixtures.
  * WHY-NOT ON FORM AT KICKOFF, so a finished game is not explained by its own result.
  * TOMORROW is a second tab: the evening board was otherwise all full-time scores.

Usage:  python3 today_build.py   →  public_site/today.html
"""
import json, os, html, datetime
from zoneinfo import ZoneInfo

import streaks_fetch
import streaks_build as B
import streaks_track as T
import book_track as K
import venue_book as VB

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(ROOT, "public_site")
LEADS_JSON = os.path.join(ROOT, "data", "streaks.json")
CT = ZoneInfo("America/Chicago")

MARKET_SHORT = {"over15": "O 1.5", "over25": "O 2.5", "btts": "BTTS",
                "home2plus": "{home} 2+", "away2plus": "{away} 2+"}


def esc(x):
    return html.escape(str(x if x is not None else ""))


def form_before(by_team, team, date):
    """The team's games before `date` — its form as it stood at kickoff. A played fixture
    judged on today's form would count its own result, and a lead that did not fire would
    be explained by a run the match itself started or broke."""
    return [g for g in by_team.get(team, []) if g["date"] < date]


def why_not(home, away, by_team, date):
    """Why a fixture produced no lead — the coverage diagnostic, per fixture, on the form
    each side carried into it."""
    reasons, runs = [], {}
    for team in (home, away):
        games = form_before(by_team, team, date)
        if not games:
            reasons.append(f"{team}: no competitive games on record")
            continue
        if len(games) < B.MIN_PLAYED:
            reasons.append(f"{team}: only {len(games)} game"
                           f"{'' if len(games) == 1 else 's'} (needs {B.MIN_PLAYED})")
            continue
        r = {}
        for key, _label, _side, pred in B.STREAKS:
            n = B.run_length(games, pred)
            if n >= B.MIN_RUN:
                r[key] = n
        if not r:
            reasons.append(f"{team}: no run of {B.MIN_RUN}+")
        runs[team] = r
    if not reasons and len(runs) == 2:
        reasons.append("both on a run, but the runs do not pair into a claim")
    return reasons


def ct_day(ko):
    return ko.astimezone(CT).date() if ko else None


def lead_view(e):
    """One ledger lead as the page shows it: the claim, the price its own market was
    captured at, and — once graded — whether it landed and what it paid."""
    claim = T.claim_market(e.get("bet") or {})
    q = (e.get("prices") or {}).get(claim) if claim else None
    settled = (e.get("pnl") or {}).get(claim) if claim else None
    status = e.get("status", "pending")
    return {"headline": e["headline"], "status": status, "claim": claim,
            "price": q["price"] if q else None, "fair": q["fair"] if q else None,
            "model": (e.get("model") or {}).get(claim) if q else None,
            "pnl": settled["pnl"] if settled and status in ("hit", "miss") else None,
            "note": e.get("note")}


def tally(bets):
    """[(hit, pnl-or-None)] -> {n, hits, priced, pnl}. Units are summed over priced bets
    only; hit rate is over every graded one."""
    priced = [p for _h, p in bets if p is not None]
    return {"n": len(bets), "hits": sum(1 for h, _p in bets if h),
            "priced": len(priced), "pnl": round(sum(priced), 2)}


def scoreboard(rows):
    """The control group, scored: graded leads against every priced market the book
    carried that day, split by whether the fixture had a lead, and the model's flags."""
    leads, all_mk, on_lead, off_lead, flags = [], [], [], [], []
    for r in rows:
        for l in r["leads"]:
            if l["status"] in ("hit", "miss"):
                leads.append((l["status"] == "hit", l["pnl"]))
        for m in r["markets"]:
            if m.get("hit") is None:
                continue
            b = (m["hit"], m["pnl"])
            all_mk.append(b)
            (on_lead if r["leads"] else off_lead).append(b)
            if m["value"]:
                flags.append(b)
    return [
        {"label": "Leads — their own claim", "key": "leads", **tally(leads)},
        {"label": "Every market the book priced", "key": "all", **tally(all_mk)},
        {"label": "… on fixtures with a lead", "key": "on", **tally(on_lead)},
        {"label": "… on fixtures without one", "key": "off", **tally(off_lead)},
        {"label": "Model value flags", "key": "flags", **tally(flags)},
    ]


def day_rows(day, fixtures, by_team, shown, rates, league_of, ledger, published, book,
             now):
    """Every fixture on the Central `day`. The ESPN feed keeps only scheduled and finished
    games, so a match in progress drops out of it until full time; the book ledger and the
    lead ledger both hold the fixture already, and fill that gap as "in play"."""
    def side(team, date):
        games = form_before(by_team, team, date)
        runs = []
        if len(games) >= B.MIN_PLAYED_SHOWN:
            for key, _label, _s, pred in B.STREAKS:
                n = B.run_length(games, pred)
                if n >= B.MIN_RUN:
                    runs.append({"key": key, "label": B.STREAK_BY_KEY[key][1], "n": n,
                                 "rate": rates[key][min(n, B.FORM_GAMES)]})
            runs.sort(key=lambda r: (r["rate"], -r["n"]))
        return {"team": team, "league": league_of.get(team, "—"), "runs": runs,
                "recent": B.form_seq(games[:B.FORM_GAMES], runs[0]["n"] if runs else 0)
                          if len(games) >= B.MIN_PLAYED_SHOWN else []}

    fx = {}
    for f in fixtures:
        if not f.get("competitive", True) or not f.get("lead_source", True):
            continue
        if ct_day(B.kickoff_dt(f)) == day:
            fx[(f["date"], f["home"], f["away"])] = dict(f, in_feed=True)
    for src in (book.values(), ledger.values()):
        for e in src:
            if e.get("lead_source") is False:
                continue
            key = (e["date"], e["home"], e["away"])
            if key in fx or ct_day(B.kickoff_dt(e)) != day:
                continue
            fx[key] = {"date": e["date"], "home": e["home"], "away": e["away"],
                       "league": e.get("league", "—"), "kickoff": e.get("kickoff"),
                       "played": False, "in_feed": False}

    leads_by = {}
    for e in ledger.values():
        leads_by.setdefault((e["date"], e["home"], e["away"]), {})[e["headline"]] = e
    for l in published:                          # published this build, not yet logged
        leads_by.setdefault((l["date"], l["home"], l["away"]), {}).setdefault(
            l["headline"], dict(l, status="pending"))

    rows = []
    for key, f in fx.items():
        ko = B.kickoff_dt(f)
        played = bool(f.get("played"))
        state = "ft" if played else ("live" if ko and ko <= now else "upcoming")
        leads = [lead_view(e) for e in leads_by.get(key, {}).values()]
        bk = book.get(key)
        graded = bool(bk and bk.get("status") == "graded")
        markets, value = [], []
        for mk in (K.MARKETS if bk else ()):
            q = bk["prices"].get(mk)
            if not q:
                continue
            m = (bk.get("model") or {}).get(mk)
            flag = m is not None and (m - q["fair"]) >= T.VALUE_MARGIN - 1e-9
            hit = (bk.get("result") or {}).get(mk) if graded else None
            markets.append({"mk": mk, "price": q["price"], "fair": q["fair"], "model": m,
                            "value": flag, "hit": hit,
                            "pnl": (bk.get("pnl") or {}).get(mk) if hit is not None else None})
            if flag:
                value.append(mk)
        final = (f"{f['home_goals']}-{f['away_goals']}"
                 if played and f.get("home_goals") is not None else (bk or {}).get("final"))
        rows.append({
            "match": f"{f['home']} v {f['away']}", "home": side(f["home"], f["date"]),
            "away": side(f["away"], f["date"]), "league": f["league"],
            "kickoff": f.get("kickoff"), "date": f["date"], "played": played,
            "state": state, "in_feed": f["in_feed"], "final": final,
            "leads": leads,
            "why_not": [] if leads else why_not(f["home"], f["away"], by_team, f["date"]),
            "markets": markets, "value": value,
            "market_url": next((u for u in (VB.market_url(m) for m in
                                (bk or {}).get("prices", {}).values()) if u), None),
        })
    rows.sort(key=lambda r: (r.get("kickoff") or "", r["match"]))
    return rows


def summarize(rows):
    leads = [l for r in rows for l in r["leads"]]
    return {
        "fixtures": len(rows),
        "lead_fixtures": sum(1 for r in rows if r["leads"]),
        "leads": len(leads),
        "leads_priced": sum(1 for l in leads if l["price"] is not None),
        "priced": sum(1 for r in rows if r["markets"]),
        "live": sum(1 for r in rows if r["state"] == "live"),
        "value_non_lead": sum(len(r["value"]) for r in rows if not r["leads"]),
        "value_lead": sum(len(r["value"]) for r in rows if r["leads"]),
        "board": scoreboard(rows),
    }


def gather(now=None, fixtures=None, ledger=None, published=None, book=None):
    """{"today": {...}, "tomorrow": {...}, "leagues": [...]} for the current Central day
    and the next. Every input can be passed in, so the tests run without the network."""
    now = now or datetime.datetime.now(datetime.timezone.utc)
    if fixtures is None:
        fixtures = streaks_fetch.load_or_fetch()["fixtures"]
    if ledger is None:
        ledger = T.load().get("leads", {})
    if published is None:
        try:
            published = json.load(open(LEADS_JSON)).get("leads", [])
        except Exception:
            published = []
    if book is None:
        book = K.load()["rows"]
    book = {(r["date"], r["home"], r["away"]): r for r in book.values()}
    by_team = B.team_games(fixtures)
    rates = B.base_rates(B.team_streaks(by_team))
    league_of, _ = B.team_lookups(by_team, fixtures)

    today_ct = now.astimezone(CT).date()
    out = {}
    for name, day in (("today", today_ct), ("tomorrow", today_ct + datetime.timedelta(days=1))):
        rows = day_rows(day, fixtures, by_team, None, rates, league_of, ledger, published,
                        book, now)
        out[name] = {"date": day.isoformat(), "rows": rows, "summary": summarize(rows)}
    out["leagues"] = sorted({r["league"] for d in ("today", "tomorrow")
                             for r in out[d]["rows"]})
    return out


def page_html(data, now):
    payload = json.dumps(data).replace("</", "<\\/")
    btns = "".join(f'<button class="lg lgf" data-lg="{esc(l)}">{esc(l)}</button>'
                   for l in data["leagues"])
    n_tom = data["tomorrow"]["summary"]["fixtures"]
    return f"""<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Edge Machine · Today</title>
<meta name="description" content="Every tracked fixture kicking off today — the leads' control group, with the book's line and the model on every one.">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<style>
:root{{--bg:#0a0d14;--card:#10141d;--bd:#232936;--fg:#eef2f7;--mut:#8b94a7;
--pos:#3fb970;--neg:#e06c75;--warn:#f0b429;--acc:#7aa2f7}}
*{{box-sizing:border-box;margin:0}}
body{{background:var(--bg);color:var(--fg);font:15px/1.45 Inter,system-ui,sans-serif;
letter-spacing:-.011em;-webkit-font-smoothing:antialiased;padding:28px 16px 60px}}
.wrap{{max-width:960px;margin:0 auto}}
h1{{font-size:22px;font-weight:800;letter-spacing:-.02em}}
.sub{{color:var(--mut);font-size:13px;margin-top:4px}}
.mut{{color:var(--mut)}}
.nav{{display:flex;gap:8px;margin-top:14px;flex-wrap:wrap}}
.nav a{{font-size:12px;font-weight:700;text-decoration:none;color:var(--mut);
border:1px solid var(--bd);border-radius:999px;padding:5px 13px}}
.nav a:hover{{color:var(--fg);border-color:var(--mut)}}
.nav a.on{{color:var(--fg);border-color:var(--mut);background:#161b26}}
.note{{font-size:12.5px;color:var(--mut);line-height:1.6;background:var(--card);
border:1px solid var(--bd);border-radius:10px;padding:12px 14px;margin-top:15px}}
.note b{{color:var(--fg);font-weight:600}}
.tiles{{display:flex;gap:9px;flex-wrap:wrap;margin-top:12px}}
.tile{{flex:1;min-width:110px;background:var(--card);border:1px solid var(--bd);
border-radius:10px;padding:10px 13px}}
.tile b{{display:block;font-size:19px;font-weight:800;font-variant-numeric:tabular-nums}}
.tile span{{font-size:11px;color:var(--mut)}}
.controls{{position:sticky;top:0;z-index:20;background:var(--bg);
padding:14px 0 10px;margin-top:16px;border-bottom:1px solid var(--bd)}}
.lgs{{display:flex;gap:6px;flex-wrap:wrap}}
.lgs+.lgs{{margin-top:8px}}
.lg{{font:inherit;font-size:11.5px;font-weight:700;color:var(--mut);cursor:pointer;
background:none;border:1px solid var(--bd);border-radius:999px;padding:5px 12px}}
.lg:hover{{color:var(--fg);border-color:var(--mut)}}
.lg.on{{color:#0a0d14;background:var(--acc);border-color:var(--acc)}}
.srch{{margin-top:9px;display:flex;gap:8px;align-items:center}}
.srch input{{flex:1;font:inherit;font-size:13px;color:var(--fg);background:var(--card);
border:1px solid var(--bd);border-radius:9px;padding:8px 12px;outline:none}}
.srch input:focus{{border-color:var(--acc)}}
.cnt{{font-size:11.5px;color:var(--mut);white-space:nowrap;font-variant-numeric:tabular-nums}}
.row{{background:var(--card);border:1px solid var(--bd);border-radius:11px;
margin-bottom:9px;overflow:hidden}}
.row.islead{{border-color:#7aa2f766}}
.hd{{display:flex;align-items:baseline;gap:9px;flex-wrap:wrap;
padding:12px 15px 10px;border-bottom:1px solid var(--bd)}}
.mt{{font-weight:700;font-size:15px;letter-spacing:-.012em}}
.meta{{font-size:11.5px;color:var(--mut);margin-left:auto;white-space:nowrap}}
.kbtn{{font-size:11px;font-weight:700;color:var(--acc);text-decoration:none;
border:1px solid #7aa2f755;background:#7aa2f714;border-radius:999px;padding:3px 10px;
white-space:nowrap}}
.kbtn:hover{{background:#7aa2f72a}}
.cd{{font-size:11px;font-weight:800;border-radius:999px;padding:2px 8px;border:1px solid;
white-space:nowrap;font-variant-numeric:tabular-nums}}
.cd.soon{{color:var(--warn);border-color:#f0b42955;background:#f0b42914}}
.cd.later{{color:var(--mut);border-color:var(--bd)}}
.cd.ft{{color:var(--pos);border-color:#3fb97055;background:#3fb97014}}
.body{{padding:12px 15px;display:grid;grid-template-columns:1fr 1fr;gap:14px}}
.side{{min-width:0}}
.nm{{font-size:13px;font-weight:700;margin-bottom:6px}}
.runs{{display:flex;gap:5px;flex-wrap:wrap;margin-bottom:6px}}
.rare{{font-size:10px;font-weight:800;border-radius:999px;padding:2px 8px;border:1px solid}}
.rare.hot{{color:var(--warn);border-color:#f0b42955;background:#f0b42914}}
.rare.mid{{color:var(--mut);border-color:var(--bd)}}
.rare.common{{color:var(--neg);border-color:#e06c7544;background:#e06c750f}}
.norun{{font-size:11px;color:var(--mut);font-style:italic}}
.seq{{display:flex;gap:3px;flex-wrap:wrap}}
.sc{{font-size:10px;font-weight:700;font-variant-numeric:tabular-nums;border-radius:4px;
padding:1px 5px;background:#0c1017;border:1px solid var(--bd);color:var(--mut)}}
.sc.hit{{color:var(--fg);border-color:#3fb97044;background:#3fb9700f}}
.sc.fr{{border-style:dashed;border-color:#f0b42966;color:var(--warn)}}
.strip{{display:flex;gap:8px;flex-wrap:wrap;align-items:center;padding:9px 15px;
border-top:1px solid var(--bd);font-size:12px}}
.lbl{{font-size:9.5px;font-weight:800;letter-spacing:.08em;text-transform:uppercase;
color:var(--mut)}}
.lead .lbl{{color:var(--acc)}}
.hl{{font-weight:700}}
.px{{font-size:11px;font-weight:700;color:var(--mut);font-variant-numeric:tabular-nums;
white-space:nowrap}}
.why{{color:var(--mut);font-size:11.5px}}
.mk{{font-size:11px;font-weight:700;font-variant-numeric:tabular-nums;border-radius:999px;
padding:2px 9px;border:1px solid var(--bd);color:var(--mut);white-space:nowrap}}
.mk b{{color:var(--fg)}}
.mk.val{{color:var(--pos);border-color:#3fb97055;background:#3fb97014}}
.mk.val b{{color:var(--pos)}}
.mk.hit{{border-color:#3fb97055}} .mk.miss{{opacity:.55}}
.res{{font-size:10px;font-weight:800;border-radius:4px;padding:1px 6px;margin-left:4px}}
.res.hit{{color:var(--pos);background:#3fb97018}} .res.miss{{color:var(--neg);background:#e06c7518}}
.res.void,.res.pending{{color:var(--mut);background:#8b94a714}}
.cd.live{{color:var(--acc);border-color:#7aa2f755;background:#7aa2f714}}
.days{{display:flex;gap:6px;margin-bottom:8px}}
.board{{margin-top:12px;background:var(--card);border:1px solid var(--bd);border-radius:10px;
overflow-x:auto}}
.board table{{width:100%;border-collapse:collapse;font-size:12.5px;font-variant-numeric:tabular-nums}}
.board th,.board td{{padding:7px 12px;text-align:right;white-space:nowrap;border-bottom:1px solid var(--bd)}}
.board th{{font-size:10px;letter-spacing:.06em;text-transform:uppercase;color:var(--mut);font-weight:800}}
.board th:first-child,.board td:first-child{{text-align:left}}
.board tr:last-child td{{border-bottom:0}}
.board .pos{{color:var(--pos)}} .board .neg{{color:var(--neg)}}
.board caption{{caption-side:top;text-align:left;padding:10px 12px 2px;font-size:11.5px;color:var(--mut)}}
.empty{{color:var(--mut);padding:26px 0;text-align:center;line-height:1.6}}
footer{{margin-top:40px;font-size:12px;color:var(--mut);text-align:center}}
@media (max-width:640px){{
  body{{padding:18px 10px 44px;font-size:14px}}
  h1{{font-size:19px}} .body{{grid-template-columns:1fr;gap:10px}}
  .meta{{margin-left:0;width:100%}}
}}
</style></head><body><div class="wrap">
<h1>Edge Machine · Today</h1>
<div class="sub">Every tracked fixture kicking off today · the leads' control group · all times CT · updated {esc(now)}</div>
<div class="nav"><a href="./">Leads</a>
<a href="./streaks.html">Streaks</a><a href="./record.html">Record</a>
<a class="on" href="./today.html">Today</a><a href="./sandbox.html">Sandbox</a><a href="./qa.html">QA</a></div>

<div class="note">The whole day, in kickoff order: <b>what the rules picked, what they
passed over, and what the book and the model say about all of it.</b> A fixture with a lead
carries the lead's claim at the price it was captured; a fixture without one says why not.
Every fixture inside 24h carries the book's line on five markets with the book's vig-free
probability and the model's estimate beside it. A market is marked <b>value</b> where the
model beats the book by 5pp or more — that is the pre-registered split the Record page
scores, <b>a hypothesis being counted, not a tip</b>: until it has proved itself there,
a flag means only that the model and the book disagree. Once a game is over every lead
and every market is marked <b>hit</b> or <b>miss</b> with what it paid at a flat 1 unit, and
the scoreboard sets the day's leads beside everything the book priced.{
  f' <b>{n_tom} fixture{"" if n_tom == 1 else "s"} tomorrow.</b>' if n_tom else ''}</div>
<div class="tiles" id="tiles"></div>
<div class="board" id="board"></div>

<div class="controls">
  <div class="days"><button class="dy lg on" data-dy="today">Today</button><button class="dy lg" data-dy="tomorrow">Tomorrow</button></div>
  <div class="lgs"><button class="vw lg on" data-vw="">All fixtures</button><button class="vw lg" data-vw="lead">Leads</button><button class="vw lg" data-vw="rest">Not leads</button><button class="vw lg" data-vw="value">Model value, no lead</button></div>
  <div class="lgs"><button class="lg lgf on" data-lg="">All leagues</button>{btns}</div>
  <div class="srch">
    <input id="q" type="search" placeholder="Filter by team…" autocomplete="off">
    <span class="cnt" id="cnt"></span>
  </div>
</div>

<div id="list"></div>
<div class="empty" id="empty" style="display:none"></div>

<footer>Read-only static export · research, not betting advice.</footer>
</div>
<script>
const DATA = {payload};
const SHORT = {json.dumps(MARKET_SHORT)};
const TZ = 'America/Chicago';
const list = document.getElementById('list');
const cnt  = document.getElementById('cnt');
const empty= document.getElementById('empty');
const q    = document.getElementById('q');
let league = '', view = '', day = 'today';

function esc(s) {{
  return String(s).replace(/[&<>"']/g, c => (
    {{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c]));
}}
function when(iso) {{
  const d = new Date(iso);
  if (isNaN(d)) return '';
  return d.toLocaleString('en-US', {{timeZone: TZ, weekday:'short', hour:'numeric',
                                    minute:'2-digit'}});
}}
function countdown(iso) {{
  const d = new Date(iso); if (isNaN(d)) return ['later',''];
  let ms = d - new Date();
  if (ms <= 0) return ['later', ms > -2.5*3600*1000 ? 'kicked off' : 'played'];
  const mins = Math.floor(ms/60000), hrs = Math.floor(mins/60), m = mins % 60;
  return [mins <= 720 ? 'soon' : 'later',
          hrs > 0 ? `in ${{hrs}}h ${{String(m).padStart(2,'0')}}m` : `in ${{m}}m`];
}}
function pctOf(r) {{ const p = Math.round(r*100); return p === 0 && r > 0 ? '<1%' : p + '%'; }}
function rarity(r) {{
  if (r <= 0.10) return ['hot', 'rare · ' + pctOf(r)];
  if (r <= 0.25) return ['mid', 'uncommon · ' + pctOf(r)];
  return ['common', 'common · ' + pctOf(r)];
}}
function seq(games) {{
  return `<div class="seq">` + games.map(g =>
    `<span class="sc${{g.hit ? ' hit' : ''}}${{g.comp === false ? ' fr' : ''}}"`
    + ` title="${{esc(g.s)}} ${{g.h ? 'home' : 'away'}} v ${{esc(g.opp)}}">${{esc(g.s)}}</span>`
  ).join('') + `</div>`;
}}
function side(sd) {{
  const chips = sd.runs.slice(0,2).map(r => {{
    const [cls] = rarity(r.rate);
    return `<span class="rare ${{cls}}">${{esc(r.label)}} · ${{r.n}} · ${{pctOf(r.rate)}}</span>`;
  }}).join('');
  return `<div class="side"><div class="nm">${{esc(sd.team)}}</div>
    <div class="runs">${{chips || '<span class="norun">no current run</span>'}}</div>
    ${{sd.recent.length ? seq(sd.recent) : ''}}</div>`;
}}
function units(x) {{ return (x > 0 ? '+' : '') + x.toFixed(2); }}
function res(status, pnl, note) {{
  if (status === 'pending') return '';
  const txt = status === 'void' ? 'void' : status + (pnl != null ? ' ' + units(pnl) : '');
  return `<span class="res ${{status}}"${{note ? ` title="${{esc(note)}}"` : ''}}>${{esc(txt)}}</span>`;
}}
function pc(x) {{ return x == null ? '—' : Math.round(x*100) + '%'; }}
function leadStrip(m) {{
  if (m.leads.length) {{
    return m.leads.map(l => `<div class="strip lead"><span class="lbl">Lead</span>
      <span class="hl">${{esc(l.headline)}}</span>
      ${{l.price ? `<span class="px">@ ${{l.price.toFixed(2)}} · book ${{pc(l.fair)}}${{
        l.model != null ? ' · model ' + pc(l.model) : ''}}</span>` :
        `<span class="px">${{l.claim ? (m.state === 'upcoming' ? 'not priced yet' : 'never priced') : 'no priced market for this claim'}}</span>`}}
      ${{res(l.status, l.pnl, l.note)}}
    </div>`).join('');
  }}
  return `<div class="strip"><span class="lbl">No lead</span>
    <span class="why">${{esc(m.why_not.join(' · ') || '—')}}</span></div>`;
}}
function bookStrip(m) {{
  if (!m.markets.length) return `<div class="strip"><span class="lbl">Book</span>
    <span class="why">${{m.state === 'upcoming' ? 'not priced yet — fixtures are priced inside 24h of kickoff' : 'not priced before kickoff'}}</span></div>`;
  const [home, away] = m.match.split(' v ');
  const chips = m.markets.map(k => {{
    const name = SHORT[k.mk].replace('{{home}}', home).replace('{{away}}', away);
    const st = k.hit == null ? '' : (k.hit ? ' hit' : ' miss');
    return `<span class="mk${{k.value ? ' val' : ''}}${{st}}" title="price · book's vig-free probability · model">${{
      esc(name)}} <b>${{k.price.toFixed(2)}}</b> · book ${{pc(k.fair)}}${{
      k.model != null ? ' · model ' + pc(k.model) : ''}}${{k.value ? ' · value' : ''}}${{
      k.hit == null ? '' : res(k.hit ? 'hit' : 'miss', k.pnl)}}</span>`;
  }}).join('');
  return `<div class="strip"><span class="lbl">Book</span>${{chips}}</div>`;
}}
function liveText(iso) {{
  const ms = new Date() - new Date(iso);
  return ms < 2.5*3600*1000 ? 'in play' : 'awaiting result';
}}
function tiles(s) {{
  const t = [[s.fixtures, day === 'today' ? 'fixtures today' : 'fixtures tomorrow'],
             [s.lead_fixtures, 'carry a lead'],
             [`${{s.leads_priced}}/${{s.leads}}`, 'leads priced'],
             [s.priced, 'priced by the book'],
             [s.value_non_lead, 'value flags on non-leads'],
             [s.value_lead, 'value flags on leads']];
  if (s.live) t.splice(1, 0, [s.live, 'in play']);
  return t.map(([b, l]) => `<div class="tile"><b>${{esc(b)}}</b><span>${{esc(l)}}</span></div>`).join('');
}}
function board(rows) {{
  if (!rows.some(r => r.n)) return '';
  const body = rows.map(r => {{
    const roi = r.priced ? r.pnl / r.priced : null;
    const cls = x => x == null || x === 0 ? '' : (x > 0 ? 'pos' : 'neg');
    return `<tr><td>${{esc(r.label)}}</td><td>${{r.n}}</td><td>${{r.hits}}</td>
      <td>${{r.n ? Math.round(100*r.hits/r.n) + '%' : '—'}}</td><td>${{r.priced}}</td>
      <td class="${{cls(r.pnl)}}">${{r.priced ? units(r.pnl) : '—'}}</td>
      <td class="${{cls(roi)}}">${{roi == null ? '—' : (roi > 0 ? '+' : '') + Math.round(100*roi) + '%'}}</td></tr>`;
  }}).join('');
  return `<table><caption>Scoreboard · games finished so far · flat 1 unit · units and ROI over priced bets only · one day proves nothing</caption>
    <tr><th></th><th>Graded</th><th>Hits</th><th>Hit %</th><th>Priced</th><th>Units</th><th>ROI</th></tr>${{body}}</table>`;
}}
function row(m) {{
  const [cls, txt] = m.played ? ['ft', 'FT ' + (m.final || '')]
    : m.state === 'live' ? ['live', m.final ? 'FT ' + m.final : liveText(m.kickoff)]
    : countdown(m.kickoff);
  return `<div class="row${{m.leads.length ? ' islead' : ''}}">
    <div class="hd"><span class="mt">${{esc(m.match)}}</span>
      <span class="cd ${{cls}}" ${{m.state === 'upcoming' ? `data-ko="${{esc(m.kickoff||'')}}"` : ''}}>${{
        esc(txt)}}</span>
      <span class="meta">${{esc(m.league)}} · ${{esc(when(m.kickoff) || m.date)}}</span>
      ${{m.market_url && m.state === 'upcoming' ? `<a class="kbtn" href="${{esc(m.market_url)}}" target="_blank" rel="noopener">Market ↗</a>` : ''}}</div>
    <div class="body">${{side(m.home)}}${{side(m.away)}}</div>
    ${{leadStrip(m)}}${{bookStrip(m)}}
  </div>`;
}}
function keep(m) {{
  if (view === 'lead') return m.leads.length > 0;
  if (view === 'rest') return m.leads.length === 0;
  if (view === 'value') return m.leads.length === 0 && m.value.length > 0;
  return true;
}}
function render() {{
  const D = DATA[day], ROWS = D.rows, TOM = DATA.tomorrow.rows.length;
  document.getElementById('tiles').innerHTML = tiles(D.summary);
  const bd = board(D.summary.board);
  document.getElementById('board').innerHTML = bd;
  document.getElementById('board').hidden = !bd;
  const term = q.value.trim().toLowerCase();
  const rows = ROWS.filter(m => keep(m) && (!league || m.league === league) &&
                                (!term || m.match.toLowerCase().includes(term)));
  list.innerHTML = rows.map(row).join('');
  cnt.textContent = rows.length + ' of ' + ROWS.length;
  empty.textContent = ROWS.length
    ? 'No fixtures match that filter.'
    : (day === 'today' ? 'Nothing on today.' + (TOM ? ` ${{TOM}} fixture${{TOM===1?'':'s'}} tomorrow.` : '')
                  : 'Nothing on tomorrow.');
  empty.style.display = rows.length ? 'none' : '';
}}
for (const b of document.querySelectorAll('.dy')) {{
  b.addEventListener('click', () => {{
    document.querySelectorAll('.dy').forEach(x => x.classList.remove('on'));
    b.classList.add('on'); day = b.dataset.dy; render();
  }});
}}
for (const b of document.querySelectorAll('.lgf')) {{
  b.addEventListener('click', () => {{
    document.querySelectorAll('.lgf').forEach(x => x.classList.remove('on'));
    b.classList.add('on'); league = b.dataset.lg; render();
  }});
}}
for (const b of document.querySelectorAll('.vw')) {{
  b.addEventListener('click', () => {{
    document.querySelectorAll('.vw').forEach(x => x.classList.remove('on'));
    b.classList.add('on'); view = b.dataset.vw; render();
  }});
}}
q.addEventListener('input', render);
render();
setInterval(() => {{
  for (const el of document.querySelectorAll('.cd[data-ko]')) {{
    const [cls, txt] = countdown(el.dataset.ko);
    el.textContent = txt; el.className = 'cd ' + cls;
  }}
}}, 30000);
</script></body></html>"""


def build():
    data = gather()
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%b %d %Y · %H:%M UTC")
    os.makedirs(OUT_DIR, exist_ok=True)
    out = os.path.join(OUT_DIR, "today.html")
    with open(out, "w") as f:
        f.write(page_html(data, now))
    t = data["today"]["summary"]
    print(f"wrote {out}  ({os.path.getsize(out)/1024:.0f} KB) — "
          f"{t['fixtures']} fixtures today ({t['lead_fixtures']} with leads, "
          f"{t['leads_priced']}/{t['leads']} leads priced, {t['live']} in play, "
          f"{t['priced']} priced, {t['value_non_lead']} value flags on non-leads), "
          f"{data['tomorrow']['summary']['fixtures']} tomorrow")


if __name__ == "__main__":
    build()
