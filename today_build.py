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

Usage:  python3 today_build.py   →  public_site/today.html
"""
import json, os, html, datetime
from zoneinfo import ZoneInfo

import streaks_fetch
import streaks_build as B
import streaks_track as T
import book_track as K

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(ROOT, "public_site")
LEADS_JSON = os.path.join(ROOT, "data", "streaks.json")
CT = ZoneInfo("America/Chicago")

MARKET_SHORT = {"over15": "O 1.5", "over25": "O 2.5", "btts": "BTTS",
                "home2plus": "{home} 2+", "away2plus": "{away} 2+"}


def esc(x):
    return html.escape(str(x if x is not None else ""))


def why_not(home, away, lead_grade):
    """Why a fixture produced no lead — the coverage diagnostic, per fixture."""
    reasons = []
    runs = {}
    for team in (home, away):
        info = lead_grade.get(team)
        if not info:
            reasons.append(f"{team}: no competitive games on record")
            continue
        if info["played"] < B.MIN_PLAYED:
            reasons.append(f"{team}: only {info['played']} game"
                           f"{'' if info['played'] == 1 else 's'} (needs {B.MIN_PLAYED})")
            continue
        r = {k: n for k, n in info["runs"].items() if n >= B.MIN_RUN}
        if not r:
            reasons.append(f"{team}: no run of {B.MIN_RUN}+")
        runs[team] = r
    if not reasons and len(runs) == 2:
        reasons.append("both on a run, but the runs do not pair into a claim")
    return reasons


def gather():
    """(rows, summary, tomorrow_count, leagues) for the current Central day."""
    fixtures = streaks_fetch.load_or_fetch()["fixtures"]
    by_team = B.team_games(fixtures)
    shown = B.team_streaks(by_team, B.MIN_PLAYED_SHOWN)     # browse-grade form
    lead_grade = B.team_streaks(by_team)                     # what find_leads sees
    rates = B.base_rates(lead_grade)
    league_of, _ = B.team_lookups(by_team, fixtures)

    try:
        leads_pub = json.load(open(LEADS_JSON)).get("leads", [])
    except Exception:
        leads_pub = []
    leads_by = {}
    for l in leads_pub:
        leads_by.setdefault((l["date"], l["home"], l["away"]), []).append(l)
    book = {(r["date"], r["home"], r["away"]): r for r in K.load()["rows"].values()}

    now = datetime.datetime.now(datetime.timezone.utc)
    today_ct = now.astimezone(CT).date()
    tomorrow = today_ct + datetime.timedelta(days=1)

    def side(team):
        info = shown.get(team)
        runs = []
        if info:
            runs = sorted(
                ({"key": k, "label": B.STREAK_BY_KEY[k][1], "n": n,
                  "rate": rates[k][min(n, B.FORM_GAMES)]}
                 for k, n in info["runs"].items()),
                key=lambda r: (r["rate"], -r["n"]))
        return {"team": team, "league": league_of.get(team, "—"), "runs": runs,
                "recent": B.form_seq(info["recent"], runs[0]["n"] if runs else 0)
                          if info else []}

    rows, n_tom = [], 0
    for f in fixtures:
        if not f.get("competitive", True):
            continue
        # Competitive FORM feeds (Belgian, Norwegian, Greek, Turkish...) are pulled so a
        # European tie has form on both sides; they are not part of this board.
        if not f.get("lead_source", True):
            continue
        ko = B.kickoff_dt(f)
        if ko is None:
            continue
        d = ko.astimezone(CT).date()
        if d == tomorrow:
            n_tom += 1
        if d != today_ct:
            continue
        key = (f["date"], f["home"], f["away"])
        leads = [{"headline": l["headline"], "price": l.get("price"),
                  "fair": l.get("fair"), "model": l.get("model")}
                 for l in leads_by.get(key, [])]
        bk = book.get(key)
        markets, value = [], []
        if bk:
            for mk in K.MARKETS:
                q = bk["prices"].get(mk)
                if not q:
                    continue
                m = (bk.get("model") or {}).get(mk)
                flag = m is not None and (m - q["fair"]) >= T.VALUE_MARGIN - 1e-9
                markets.append({"mk": mk, "price": q["price"], "fair": q["fair"],
                                "model": m, "value": flag})
                if flag:
                    value.append(mk)
        rows.append({
            "match": f"{f['home']} v {f['away']}", "home": side(f["home"]),
            "away": side(f["away"]), "league": f["league"], "kickoff": f.get("kickoff"),
            "date": f["date"], "played": bool(f.get("played")),
            "final": (f"{f['home_goals']}-{f['away_goals']}"
                      if f.get("played") and f.get("home_goals") is not None else None),
            "leads": leads,
            "why_not": [] if leads else why_not(f["home"], f["away"], lead_grade),
            "markets": markets, "value": value,
            "market_url": B.venue_market_link(f),
        })

    rows.sort(key=lambda r: (r.get("kickoff") or "", r["match"]))
    leagues = sorted({r["league"] for r in rows})
    summary = {
        "fixtures": len(rows),
        "lead_fixtures": sum(1 for r in rows if r["leads"]),
        "priced": sum(1 for r in rows if r["markets"]),
        "value_non_lead": sum(len(r["value"]) for r in rows if not r["leads"]),
        "value_lead": sum(len(r["value"]) for r in rows if r["leads"]),
    }
    return rows, summary, n_tom, leagues


def page_html(rows, summary, n_tom, leagues, now):
    payload = json.dumps(rows).replace("</", "<\\/")
    btns = "".join(f'<button class="lg" data-lg="{esc(l)}">{esc(l)}</button>'
                   for l in leagues)
    s = summary
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
<a class="on" href="./today.html">Today</a><a href="./sandbox.html">Sandbox</a></div>

<div class="note">The whole day, in kickoff order: <b>what the rules picked, what they
passed over, and what the book and the model say about all of it.</b> A fixture with a lead
carries the lead's claim at the price it was captured; a fixture without one says why not.
Every fixture inside 24h carries the book's line on five markets with the book's vig-free
probability and the model's estimate beside it. A market is marked <b>value</b> where the
model beats the book by 5pp or more — that is the pre-registered split the Record page
scores, <b>a hypothesis being counted, not a tip</b>: until it has proved itself there,
a flag means only that the model and the book disagree.{
  f' <b>{n_tom} fixture{"" if n_tom == 1 else "s"} tomorrow.</b>' if n_tom else ''}</div>
<div class="tiles">
  <div class="tile"><b>{s['fixtures']}</b><span>fixtures today</span></div>
  <div class="tile"><b>{s['lead_fixtures']}</b><span>carry a lead</span></div>
  <div class="tile"><b>{s['priced']}</b><span>priced by the book</span></div>
  <div class="tile"><b>{s['value_non_lead']}</b><span>value flags on non-leads</span></div>
  <div class="tile"><b>{s['value_lead']}</b><span>value flags on leads</span></div>
</div>

<div class="controls">
  <div class="lgs"><button class="vw on" data-vw="">All fixtures</button><button class="vw" data-vw="lead">Leads</button><button class="vw" data-vw="rest">Not leads</button><button class="vw" data-vw="value">Model value, no lead</button></div>
  <div class="lgs"><button class="lg on" data-lg="">All leagues</button>{btns}</div>
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
const ROWS = {payload};
const TOM = {n_tom};
const SHORT = {json.dumps(MARKET_SHORT)};
const TZ = 'America/Chicago';
const list = document.getElementById('list');
const cnt  = document.getElementById('cnt');
const empty= document.getElementById('empty');
const q    = document.getElementById('q');
let league = '', view = '';

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
function pc(x) {{ return x == null ? '—' : Math.round(x*100) + '%'; }}
function leadStrip(m) {{
  if (m.leads.length) {{
    return m.leads.map(l => `<div class="strip lead"><span class="lbl">Lead</span>
      <span class="hl">${{esc(l.headline)}}</span>
      ${{l.price ? `<span class="px">@ ${{l.price.toFixed(2)}} · book ${{pc(l.fair)}}${{
        l.model != null ? ' · model ' + pc(l.model) : ''}}</span>` : '<span class="px">not priced yet</span>'}}
    </div>`).join('');
  }}
  return `<div class="strip"><span class="lbl">No lead</span>
    <span class="why">${{esc(m.why_not.join(' · ') || '—')}}</span></div>`;
}}
function bookStrip(m) {{
  if (!m.markets.length) return `<div class="strip"><span class="lbl">Book</span>
    <span class="why">${{m.played ? 'settled' : 'not priced yet — fixtures are priced inside 24h of kickoff'}}</span></div>`;
  const [home, away] = m.match.split(' v ');
  const chips = m.markets.map(k => {{
    const name = SHORT[k.mk].replace('{{home}}', home).replace('{{away}}', away);
    return `<span class="mk${{k.value ? ' val' : ''}}" title="price · book's vig-free probability · model">${{
      esc(name)}} <b>${{k.price.toFixed(2)}}</b> · book ${{pc(k.fair)}}${{
      k.model != null ? ' · model ' + pc(k.model) : ''}}${{k.value ? ' · value' : ''}}</span>`;
  }}).join('');
  return `<div class="strip"><span class="lbl">Book</span>${{chips}}</div>`;
}}
function row(m) {{
  const [cls, txt] = m.played ? ['ft', 'FT ' + (m.final || '')] : countdown(m.kickoff);
  return `<div class="row${{m.leads.length ? ' islead' : ''}}">
    <div class="hd"><span class="mt">${{esc(m.match)}}</span>
      <span class="cd ${{cls}}" ${{m.played ? '' : `data-ko="${{esc(m.kickoff||'')}}"`}}>${{
        esc(txt)}}</span>
      <span class="meta">${{esc(m.league)}} · ${{esc(when(m.kickoff) || m.date)}}</span>
      ${{m.market_url && !m.played ? `<a class="kbtn" href="${{esc(m.market_url)}}" target="_blank" rel="noopener">Bovada ↗</a>` : ''}}</div>
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
  const term = q.value.trim().toLowerCase();
  const rows = ROWS.filter(m => keep(m) && (!league || m.league === league) &&
                                (!term || m.match.toLowerCase().includes(term)));
  list.innerHTML = rows.map(row).join('');
  cnt.textContent = rows.length + ' of ' + ROWS.length;
  empty.textContent = ROWS.length
    ? 'No fixtures match that filter.'
    : 'Nothing on today.' + (TOM ? ` ${{TOM}} fixture${{TOM===1?'':'s'}} tomorrow.` : '');
  empty.style.display = rows.length ? 'none' : '';
}}
for (const b of document.querySelectorAll('.lg')) {{
  b.addEventListener('click', () => {{
    document.querySelectorAll('.lg').forEach(x => x.classList.remove('on'));
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
    rows, summary, n_tom, leagues = gather()
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%b %d %Y · %H:%M UTC")
    os.makedirs(OUT_DIR, exist_ok=True)
    out = os.path.join(OUT_DIR, "today.html")
    with open(out, "w") as f:
        f.write(page_html(rows, summary, n_tom, leagues, now))
    print(f"wrote {out}  ({os.path.getsize(out)/1024:.0f} KB) — "
          f"{summary['fixtures']} fixtures today ({summary['lead_fixtures']} leads, "
          f"{summary['priced']} priced, {summary['value_non_lead']} value flags on "
          f"non-leads), {n_tom} tomorrow")


if __name__ == "__main__":
    build()
