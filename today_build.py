#!/usr/bin/env python3
"""today_build.py — every tracked fixture kicking off today: public_site/today.html.

Its own page rather than a tab, because "what is on tonight" is a different question from
"who is on a run" and gets asked far more often. Burying it three clicks into another board
made the most frequently wanted view the hardest to reach.

THE DAY IS CENTRAL, NOT UTC
---------------------------
A 01:30Z kickoff is the previous evening in the Americas, so a UTC day files it a day late
relative to the time the row itself prints. Every board here renders in Central; the day
boundary has to agree with that or the page contradicts its own timestamps.

Refreshes on its own — the pipeline runs every 6h, so the list empties as the day passes
and fills again overnight. It also states tomorrow's count: opened late in the evening an
almost-empty list reads as a fault rather than as the day being over.

Usage:  python3 today_build.py   →  public_site/today.html
"""
import json, os, html, datetime

import streaks_fetch
import streaks_build as B

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(ROOT, "public_site")
CT = datetime.timezone(datetime.timedelta(hours=-5))    # Central


def esc(x):
    return html.escape(str(x if x is not None else ""))


def gather():
    """(rows, tomorrow_count, leagues) for the current Central day."""
    fixtures = streaks_fetch.load_or_fetch()["fixtures"]
    by_team = B.team_games(fixtures)
    shown = B.team_streaks(by_team, B.MIN_PLAYED_SHOWN)
    rates = B.base_rates(B.team_streaks(by_team))
    league_of, _ = B.team_lookups(by_team, fixtures)

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
        ko = B.kickoff_dt(f)
        if ko is None:
            continue
        d = ko.astimezone(CT).date()
        if d == tomorrow:
            n_tom += 1
        if d != today_ct:
            continue
        h, a = side(f["home"]), side(f["away"])
        rs = [x["rate"] for sd in (h, a) for x in sd["runs"]]
        rows.append({
            "match": f"{f['home']} v {f['away']}", "home": h, "away": a,
            "league": f["league"], "kickoff": f.get("kickoff"), "date": f["date"],
            "played": bool(f.get("played")),
            "final": (f"{f['home_goals']}-{f['away_goals']}"
                      if f.get("played") and f.get("home_goals") is not None else None),
            "best_rate": min(rs) if rs else 1.0, "has_run": bool(rs),
        })

    # a fixture where someone is on a run leads; then by kickoff
    rows.sort(key=lambda r: (not r["has_run"], r["best_rate"], r.get("kickoff") or ""))
    leagues = sorted({r["league"] for r in rows})
    return rows, n_tom, leagues


def page_html(rows, n_tom, leagues, now):
    payload = json.dumps(rows).replace("</", "<\\/")
    btns = "".join(f'<button class="lg" data-lg="{esc(l)}">{esc(l)}</button>'
                   for l in leagues)
    return f"""<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Edge Machine · Today</title>
<meta name="description" content="Every tracked fixture kicking off today, with each side's current runs.">
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
.controls{{position:sticky;top:0;z-index:20;background:var(--bg);
padding:14px 0 10px;margin-top:16px;border-bottom:1px solid var(--bd)}}
.lgs{{display:flex;gap:6px;flex-wrap:wrap}}
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
.hd{{display:flex;align-items:baseline;gap:9px;flex-wrap:wrap;
padding:12px 15px 10px;border-bottom:1px solid var(--bd)}}
.mt{{font-weight:700;font-size:15px;letter-spacing:-.012em}}
.meta{{font-size:11.5px;color:var(--mut);margin-left:auto;white-space:nowrap}}
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
.empty{{color:var(--mut);padding:26px 0;text-align:center;line-height:1.6}}
footer{{margin-top:40px;font-size:12px;color:var(--mut);text-align:center}}
@media (max-width:640px){{
  body{{padding:18px 10px 44px;font-size:14px}}
  h1{{font-size:19px}} .body{{grid-template-columns:1fr;gap:10px}}
  .meta{{margin-left:0;width:100%}}
}}
</style></head><body><div class="wrap">
<h1>Edge Machine · Today</h1>
<div class="sub">Every tracked fixture kicking off today · all times CT · updated {esc(now)}</div>
<div class="nav"><a href="./">Picks</a><a href="./streaks.html">Streaks</a>
<a href="./record.html">Record</a><a class="on" href="./today.html">Today</a></div>

<div class="note">Both sides' current runs, shown against each fixture. Matches where a
team is on a run come first, rarest first. The list empties as the day passes and fills
again overnight — the pipeline refreshes every 6 hours.{
  f' <b>{n_tom} fixture{"" if n_tom == 1 else "s"} tomorrow.</b>' if n_tom else ''}</div>

<div class="controls">
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
const TZ = 'America/Chicago';
const list = document.getElementById('list');
const cnt  = document.getElementById('cnt');
const empty= document.getElementById('empty');
const q    = document.getElementById('q');
let league = '';

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
function rarity(r) {{
  if (r <= 0.10) return ['hot', 'rare · ' + Math.round(r*100) + '%'];
  if (r <= 0.25) return ['mid', 'uncommon · ' + Math.round(r*100) + '%'];
  return ['common', 'common · ' + Math.round(r*100) + '%'];
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
    return `<span class="rare ${{cls}}">${{esc(r.label)}} · ${{r.n}} · ${{
      Math.round(r.rate*100)}}%</span>`;
  }}).join('');
  return `<div class="side"><div class="nm">${{esc(sd.team)}}</div>
    <div class="runs">${{chips || '<span class="norun">no current run</span>'}}</div>
    ${{sd.recent.length ? seq(sd.recent) : ''}}</div>`;
}}
function row(m) {{
  const [cls, txt] = m.played ? ['ft', 'FT ' + (m.final || '')] : countdown(m.kickoff);
  return `<div class="row">
    <div class="hd"><span class="mt">${{esc(m.match)}}</span>
      <span class="cd ${{cls}}" ${{m.played ? '' : `data-ko="${{esc(m.kickoff||'')}}"`}}>${{
        esc(txt)}}</span>
      <span class="meta">${{esc(m.league)}} · ${{esc(when(m.kickoff) || m.date)}}</span></div>
    <div class="body">${{side(m.home)}}${{side(m.away)}}</div>
  </div>`;
}}
function render() {{
  const term = q.value.trim().toLowerCase();
  const rows = ROWS.filter(m => (!league || m.league === league) &&
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
    b.classList.add('on');
    league = b.dataset.lg;
    render();
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
    rows, n_tom, leagues = gather()
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%b %d %Y · %H:%M UTC")
    os.makedirs(OUT_DIR, exist_ok=True)
    out = os.path.join(OUT_DIR, "today.html")
    with open(out, "w") as f:
        f.write(page_html(rows, n_tom, leagues, now))
    print(f"wrote {out}  ({os.path.getsize(out)/1024:.0f} KB) — "
          f"{len(rows)} fixtures today, {n_tom} tomorrow")


if __name__ == "__main__":
    build()
