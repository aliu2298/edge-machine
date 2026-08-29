#!/usr/bin/env python3
"""streaks_build.py — find teams on an unusual run whose next opponent is a matching soft
touch, and render them to public_site/streaks.html.

THE IDEA
--------
"Barcelona have scored 2+ in six straight, and their next opponent concedes 2+ in most
games." A streak alone is not a lead — plenty of good teams score freely. The lead is the
CONFLUENCE: one side's run meets the other side's complementary weakness in a fixture that
has not been played yet.

FORM IS CROSS-COMPETITION, DELIBERATELY
---------------------------------------
A team's form is their last N games across EVERY tracked competition, not just the one the
next fixture belongs to. Two reasons: it is how form actually works (Barcelona's scoring
touch does not reset when they walk into a European tie), and it is the only thing that
works early season — UCL/UEL sides have ~2 European games played, so a competition-scoped
form model would have nothing to say about them at all.

EVERY STREAK IS SHOWN WITH ITS BASE RATE
----------------------------------------
This repo has already falsified three "signals" that looked good until they were measured
([[tips-lane-no-edge]]). The trap each time was reading a pattern without asking how often
that pattern shows up by chance. So every run here is rendered next to the share of tracked
teams currently on a run that long. A 5-game scoring streak that 20% of the league is also
on is not a lead, and the board says so rather than letting the card imply otherwise.

Nothing here places or stages a bet — these are leads to look at, not picks.

Usage:  python3 streaks_build.py [--force]   →  public_site/streaks.html
"""
import json, os, sys, html, datetime, collections

import streaks_fetch

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(ROOT, "public_site")
DATA_OUT = os.path.join(ROOT, "data", "streaks.json")

FORM_GAMES = 6        # window a streak is measured over
MIN_RUN = 3           # shorter than this is noise, not a run
MIN_PLAYED = 5        # a team needs this many games before we say anything about them
TOP_LEADS = 120       # cards baked into the page; the league filter narrows from here

# ---------------------------------------------------------------- streak definitions
# Each: (key, label, side, predicate over one game from THAT team's perspective).
# `side` marks what the run says about the team — "attack" runs pair with an opponent's
# "defence" weakness, and vice versa. That pairing is what makes a lead.
STREAKS = [
    ("scoring",  "scored 2+",           "attack",  lambda gf, ga: gf >= 2),
    ("scoring1", "scored in",           "attack",  lambda gf, ga: gf >= 1),
    ("blanked",  "failed to score",     "attack",  lambda gf, ga: gf == 0),
    ("leaky",    "conceded 2+",         "defence", lambda gf, ga: ga >= 2),
    ("porous",   "conceded in",         "defence", lambda gf, ga: ga >= 1),
    ("solid",    "clean sheet",         "defence", lambda gf, ga: ga == 0),
    ("btts",     "both teams scored",   "game",    lambda gf, ga: gf >= 1 and ga >= 1),
    ("over25",   "over 2.5 goals",      "game",    lambda gf, ga: gf + ga >= 3),
    ("under25",  "under 2.5 goals",     "game",    lambda gf, ga: gf + ga <= 2),
]
STREAK_BY_KEY = {s[0]: s for s in STREAKS}

# A lead = team-A run + team-B run that point the same way.
# (a_key, b_key, headline, why) — `why` is rendered as the reasoning line on the card.
PAIRINGS = [
    ("scoring", "leaky",    "{a} to score 2+",
     "{a} have scored 2+ in {ra} straight; {b} have conceded 2+ in {rb} straight."),
    ("scoring", "porous",   "{a} to score",
     "{a} have scored 2+ in {ra} straight; {b} have conceded in {rb} straight."),
    ("btts",    "btts",     "Both teams to score",
     "Both sides are on a BTTS run — {a} {ra} straight, {b} {rb} straight."),
    ("over25",  "over25",   "Over 2.5 goals",
     "{a} have gone over 2.5 in {ra} straight; {b} in {rb} straight."),
    ("under25", "under25",  "Under 2.5 goals",
     "{a} have gone under 2.5 in {ra} straight; {b} in {rb} straight."),
    ("solid",   "blanked",  "{b} to fail to score",
     "{a} have kept {ra} straight clean sheets; {b} have failed to score in {rb} straight."),
    ("blanked", "solid",    "{a} to fail to score",
     "{a} have failed to score in {ra} straight; {b} have kept {rb} straight clean sheets."),
]


def esc(x):
    return html.escape(str(x if x is not None else ""))


def team_games(fixtures):
    """team -> [game dicts], most recent first. One played fixture yields two rows, one
    from each side's perspective, so `gf`/`ga` are always that team's own goals."""
    by_team = collections.defaultdict(list)
    for f in fixtures:
        if not f["played"]:
            continue
        hg, ag = f["home_goals"], f["away_goals"]
        if hg is None or ag is None:
            continue
        by_team[f["home"]].append({"date": f["date"], "opp": f["away"], "home": True,
                                   "gf": hg, "ga": ag, "league": f["league"]})
        by_team[f["away"]].append({"date": f["date"], "opp": f["home"], "home": False,
                                   "gf": ag, "ga": hg, "league": f["league"]})
    for t in by_team:
        by_team[t].sort(key=lambda g: g["date"], reverse=True)
    return by_team


def run_length(games, pred):
    """Consecutive games from the most recent backwards satisfying pred, capped at the
    form window. Counting from the most recent is the point — an old run that has since
    been broken is not current form."""
    n = 0
    for g in games[:FORM_GAMES]:
        if pred(g["gf"], g["ga"]):
            n += 1
        else:
            break
    return n


def team_streaks(by_team):
    """team -> {streak_key: run_length} for teams with enough games played."""
    out = {}
    for team, games in by_team.items():
        if len(games) < MIN_PLAYED:
            continue
        runs = {}
        for key, _label, _side, pred in STREAKS:
            r = run_length(games, pred)
            if r >= MIN_RUN:
                runs[key] = r
        out[team] = {"runs": runs, "played": len(games),
                     "recent": games[:FORM_GAMES]}
    return out


def base_rates(streaks):
    """streak_key -> {run_length: share of tracked teams currently on a run >= that long}.

    This is the honesty check. Without it a card saying "scored 2+ in 5 straight" reads as
    remarkable when it may be entirely ordinary.
    """
    total = len(streaks) or 1
    rates = {}
    for key, _l, _s, _p in STREAKS:
        per_len = {}
        for n in range(MIN_RUN, FORM_GAMES + 1):
            hits = sum(1 for t in streaks.values() if t["runs"].get(key, 0) >= n)
            per_len[n] = hits / total
        rates[key] = per_len
    return rates


def find_leads(fixtures, streaks, rates):
    """Upcoming fixtures where both sides' runs point the same way."""
    leads = []
    today = datetime.date.today().isoformat()
    for f in fixtures:
        if f["played"] or (f["date"] or "") < today:
            continue
        home, away = f["home"], f["away"]
        sh, sa = streaks.get(home), streaks.get(away)
        if not sh or not sa:
            continue
        for a_key, b_key, headline, why in PAIRINGS:
            # try both orientations: home as "A", then away as "A"
            for (a, b, sa_, sb_) in ((home, away, sh, sa), (away, home, sa, sh)):
                ra = sa_["runs"].get(a_key, 0)
                rb = sb_["runs"].get(b_key, 0)
                if ra < MIN_RUN or rb < MIN_RUN:
                    continue
                # Rarity of the WEAKER leg is what makes the pair notable — a pairing is
                # only as unusual as its most ordinary half.
                rate = max(rates[a_key][min(ra, FORM_GAMES)],
                           rates[b_key][min(rb, FORM_GAMES)])
                leads.append({
                    "date": f["date"], "kickoff": f["kickoff"], "league": f["league"],
                    "match": f"{f['home']} v {f['away']}",
                    "home": f["home"], "away": f["away"],
                    "headline": headline.format(a=a, b=b),
                    "why": why.format(a=a, b=b, ra=ra, rb=rb),
                    "a": a, "b": b, "a_run": ra, "b_run": rb,
                    "a_key": a_key, "b_key": b_key,
                    "strength": ra + rb,
                    "base_rate": rate,
                    "a_recent": [f"{g['gf']}-{g['ga']} {'H' if g['home'] else 'A'} v {g['opp']}"
                                 for g in sa_["recent"][:FORM_GAMES]],
                    "b_recent": [f"{g['gf']}-{g['ga']} {'H' if g['home'] else 'A'} v {g['opp']}"
                                 for g in sb_["recent"][:FORM_GAMES]],
                })
    # RAREST first, not longest. The question is "who is on an unusual run", and a
    # 6-game run that a quarter of the league is also on answers it worse than a shorter
    # one almost nobody has. Length breaks ties.
    leads.sort(key=lambda x: (x["base_rate"], -x["strength"], x["date"]))
    # One card per team-per-direction-per-fixture. Without this, `scoring+leaky` and
    # `scoring+porous` both fire on the same fixture — conceding 2+ implies conceding 1+,
    # so the porous version is strictly the weaker restatement of the same lead. Sorting
    # rarest-first above means the sharper one is the survivor.
    #
    # SYMMETRIC pairings (btts+btts, over25+over25, ...) additionally need an
    # order-insensitive key: both orientations describe the identical lead about the
    # identical fixture, and keying on `a` alone let each fixture emit the card twice.
    seen, uniq = set(), []
    for l in leads:
        if l["a_key"] == l["b_key"]:
            k = (l["match"], l["a_key"])              # orientation carries no information
        else:
            k = (l["match"], l["a"], l["a_key"])
        if k in seen:
            continue
        seen.add(k)
        uniq.append(l)
    return uniq


def team_rows(streaks, by_team, fixtures, rates):
    """Every tracked team with its current runs — the browse view.

    This exists because a confluence is genuinely rare: the Premier League currently has
    exactly one side on a conceded-2+ run, so the leads list is legitimately empty there.
    Suppressing a whole league rather than showing its actual form would be the wrong
    answer, so the runs are browsable on their own terms.
    """
    # A team's league is where they play most — so Barcelona reads "La Liga", not
    # "Champions League", regardless of which competition their next fixture is in.
    league_of = {}
    for team, games in by_team.items():
        c = collections.Counter(g["league"] for g in games)
        if c:
            league_of[team] = c.most_common(1)[0][0]

    # next scheduled fixture per team, so a run has somewhere to point
    today = datetime.date.today().isoformat()
    nxt = {}
    for f in sorted((x for x in fixtures if not x["played"] and (x["date"] or "") >= today),
                    key=lambda x: x["date"]):
        for t, opp in ((f["home"], f["away"]), (f["away"], f["home"])):
            nxt.setdefault(t, {"opp": opp, "date": f["date"], "kickoff": f["kickoff"],
                               "league": f["league"], "home": t == f["home"]})

    rows = []
    for team, info in streaks.items():
        runs = [{"key": k, "label": STREAK_BY_KEY[k][1], "n": n,
                 "rate": rates[k][min(n, FORM_GAMES)]}
                for k, n in sorted(info["runs"].items(), key=lambda kv: -kv[1])]
        if not runs:
            continue
        rows.append({
            "team": team,
            "league": league_of.get(team, "—"),
            "played": info["played"],
            "runs": runs,
            "best_rate": min(r["rate"] for r in runs),
            "longest": max(r["n"] for r in runs),
            "next": nxt.get(team),
            "recent": [f"{g['gf']}-{g['ga']} {'H' if g['home'] else 'A'} v {g['opp']}"
                       for g in info["recent"][:FORM_GAMES]],
        })
    rows.sort(key=lambda r: (r["best_rate"], -r["longest"], r["team"]))
    return rows


# ---------------------------------------------------------------- rendering
def page_html(leads, teams, meta, leagues, now):
    payload = json.dumps(leads).replace("</", "<\\/")
    teams_payload = json.dumps(teams).replace("</", "<\\/")
    league_btns = "".join(
        f'<button class="lg" data-lg="{esc(l)}">{esc(l)}</button>' for l in leagues)
    return f"""<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Edge Machine · Streaks</title>
<meta name="description" content="Teams on an unusual run whose next opponent is a matching soft touch. Research, not betting advice.">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<style>
:root{{--bg:#0a0d14;--card:#10141d;--bd:#232936;--fg:#eef2f7;--mut:#8b94a7;
--pos:#3fb970;--neg:#e06c75;--warn:#f0b429;--acc:#7aa2f7}}
*{{box-sizing:border-box;margin:0}}
body{{background:var(--bg);color:var(--fg);font:15px/1.45 Inter,system-ui,sans-serif;
letter-spacing:-.011em;-webkit-font-smoothing:antialiased;padding:28px 16px 60px}}
.wrap{{max-width:920px;margin:0 auto}}
h1{{font-size:22px;font-weight:800;letter-spacing:-.02em}}
h2{{font-size:13px;font-weight:700;text-transform:uppercase;letter-spacing:.08em;color:var(--mut);margin:30px 0 12px}}
.sub{{color:var(--mut);font-size:13px;margin-top:4px}}
.mut{{color:var(--mut)}}.pos{{color:var(--pos)}}.neg{{color:var(--neg)}}.warn{{color:var(--warn)}}
.nav{{display:flex;gap:8px;margin-top:14px;flex-wrap:wrap}}
.nav a{{font-size:12px;font-weight:700;text-decoration:none;color:var(--mut);
border:1px solid var(--bd);border-radius:999px;padding:5px 13px}}
.nav a:hover{{color:var(--fg);border-color:var(--mut)}}
.nav a.on{{color:var(--fg);border-color:var(--mut);background:#161b26}}
.note{{font-size:12.5px;color:var(--mut);margin:14px 0 0;line-height:1.55;
border-left:2px solid var(--bd);padding-left:11px}}
.controls{{position:sticky;top:0;z-index:20;background:var(--bg);
padding:14px 0 10px;margin-top:18px;border-bottom:1px solid var(--bd)}}
.tabs{{display:flex;gap:6px;margin-bottom:10px}}
.tb{{font:inherit;font-size:12.5px;font-weight:800;color:var(--mut);cursor:pointer;
background:none;border:1px solid var(--bd);border-radius:9px;padding:7px 15px;transition:all .12s}}
.tb:hover{{color:var(--fg);border-color:var(--mut)}}
.tb.on{{color:var(--fg);background:#161b26;border-color:var(--mut)}}
.trow{{background:var(--card);border:1px solid var(--bd);border-radius:11px;
padding:13px 15px;margin-bottom:9px}}
.th{{display:flex;align-items:baseline;gap:9px;flex-wrap:wrap}}
.tn{{font-weight:800;font-size:15px}}
.tl{{font-size:11.5px;color:var(--mut)}}
.tnx{{font-size:12px;color:var(--mut);margin-top:4px}}
.tnx b{{color:var(--fg);font-weight:600}}
.lgs{{display:flex;gap:6px;flex-wrap:wrap}}
.lg{{font:inherit;font-size:11.5px;font-weight:700;color:var(--mut);cursor:pointer;
background:none;border:1px solid var(--bd);border-radius:999px;padding:5px 12px;
transition:all .12s}}
.lg:hover{{color:var(--fg);border-color:var(--mut)}}
.lg.on{{color:#0a0d14;background:var(--acc);border-color:var(--acc)}}
.srch{{margin-top:9px;display:flex;gap:8px;align-items:center}}
.srch input{{flex:1;font:inherit;font-size:13px;color:var(--fg);background:var(--card);
border:1px solid var(--bd);border-radius:9px;padding:8px 12px;outline:none}}
.srch input:focus{{border-color:var(--acc)}}
.srch input::placeholder{{color:var(--mut)}}
.cnt{{font-size:11.5px;color:var(--mut);white-space:nowrap;font-variant-numeric:tabular-nums}}
.card{{background:var(--card);border:1px solid var(--bd);border-radius:12px;
padding:15px;margin-bottom:11px}}
.r1{{display:flex;align-items:baseline;gap:9px;flex-wrap:wrap}}
.hl{{font-weight:800;font-size:16px;color:var(--warn)}}
.mt{{font-size:13px;font-weight:600}}
.meta{{font-size:11.5px;color:var(--mut);margin-top:3px}}
.why{{font-size:13px;margin-top:9px;line-height:1.5}}
.runs{{display:flex;gap:7px;flex-wrap:wrap;margin-top:9px}}
.rn{{font-size:10.5px;font-weight:800;letter-spacing:.03em;border-radius:999px;
padding:3px 9px;border:1px solid}}
.rn.a{{color:var(--pos);border-color:#3fb97055;background:#3fb97014}}
.rn.b{{color:var(--acc);border-color:#7aa2f755;background:#7aa2f714}}
.rare{{font-size:10.5px;font-weight:800;border-radius:999px;padding:3px 9px;border:1px solid}}
.rare.hot{{color:var(--warn);border-color:#f0b42955;background:#f0b42914}}
.rare.mid{{color:var(--mut);border-color:var(--bd)}}
.rare.common{{color:var(--neg);border-color:#e06c7544;background:#e06c750f}}
.forms{{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:11px}}
.fm{{background:#0c1017;border:1px solid var(--bd);border-radius:9px;padding:9px 11px}}
.fmt{{font-size:10.5px;font-weight:800;text-transform:uppercase;letter-spacing:.05em;
color:var(--mut);margin-bottom:5px}}
.fmr{{font-size:11.5px;font-variant-numeric:tabular-nums;color:var(--mut);line-height:1.7}}
.empty{{color:var(--mut);padding:26px 0;text-align:center}}
footer{{margin-top:40px;font-size:12px;color:var(--mut);text-align:center}}
@media (max-width:560px){{
  body{{padding:18px 10px 44px;font-size:14px}}
  h1{{font-size:19px}} .card{{padding:13px}} .hl{{font-size:15px}}
  .forms{{grid-template-columns:1fr}}
}}
</style></head><body><div class="wrap">
<h1>Edge Machine · Streaks</h1>
<div class="sub">Teams on a run, matched against a next opponent who is soft in the same
place · updated {esc(now)}</div>
<div class="nav"><a href="./">Sports</a><a class="on" href="./streaks.html">Streaks</a></div>

<div class="note">A streak on its own is not an edge — plenty of good sides score freely.
What is shown here is the <b>confluence</b>: one team's run meeting the other's matching
weakness in a fixture not yet played. Every card carries a <b>rarity</b> chip — the share of
tracked teams currently on a run that long. When that share is high the pattern is ordinary,
and the chip says so. Form is measured across <b>all</b> tracked competitions
(last {FORM_GAMES} games, minimum {MIN_PLAYED} played), because form does not reset when a
side walks into a European tie. Leads to look at — not picks, and not betting advice.</div>

<div class="controls">
  <div class="tabs">
    <button class="tb on" data-tab="leads">Leads</button>
    <button class="tb" data-tab="teams">All teams on a run</button>
  </div>
  <div class="lgs">
    <button class="lg on" data-lg="">All leagues</button>{league_btns}
  </div>
  <div class="srch">
    <input id="q" type="search" placeholder="Filter by team… (e.g. Barcelona)" autocomplete="off">
    <span class="cnt" id="cnt"></span>
  </div>
</div>

<div id="list"></div>
<div class="empty" id="empty" style="display:none"></div>

<footer>{esc(meta)} · read-only static export · research, not betting advice.</footer>
</div>
<script>
const LEADS = {payload};
const TEAMS = {teams_payload};
const list = document.getElementById('list');
const cnt  = document.getElementById('cnt');
const empty= document.getElementById('empty');
const q    = document.getElementById('q');
let league = '';
let tab    = 'leads';

function rarity(r) {{
  if (r <= 0.10) return ['hot',    'rare · ' + Math.round(r*100) + '% of teams'];
  if (r <= 0.25) return ['mid',    'uncommon · ' + Math.round(r*100) + '% of teams'];
  return           ['common', 'common · ' + Math.round(r*100) + '% of teams'];
}}
function esc(s) {{
  return String(s).replace(/[&<>"']/g, c => (
    {{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c]));
}}
function when(iso) {{
  const d = new Date(iso);
  if (isNaN(d)) return '';
  return d.toLocaleString([], {{weekday:'short', month:'short', day:'numeric',
                               hour:'numeric', minute:'2-digit'}});
}}
function card(l) {{
  const [cls, txt] = rarity(l.base_rate);
  return `<div class="card">
    <div class="r1"><span class="hl">${{esc(l.headline)}}</span></div>
    <div class="mt">${{esc(l.match)}}</div>
    <div class="meta">${{esc(l.league)}} · ${{esc(when(l.kickoff) || l.date)}}</div>
    <div class="why">${{esc(l.why)}}</div>
    <div class="runs">
      <span class="rn a">${{esc(l.a)}} · ${{l.a_run}} straight</span>
      <span class="rn b">${{esc(l.b)}} · ${{l.b_run}} straight</span>
      <span class="rare ${{cls}}">${{esc(txt)}}</span>
    </div>
    <div class="forms">
      <div class="fm"><div class="fmt">${{esc(l.a)}} — last ${{l.a_recent.length}}</div>
        <div class="fmr">${{l.a_recent.map(esc).join('<br>')}}</div></div>
      <div class="fm"><div class="fmt">${{esc(l.b)}} — last ${{l.b_recent.length}}</div>
        <div class="fmr">${{l.b_recent.map(esc).join('<br>')}}</div></div>
    </div>
  </div>`;
}}
function teamRow(t) {{
  const chips = t.runs.map(r => {{
    const [cls] = rarity(r.rate);
    return `<span class="rare ${{cls}}">${{esc(r.label)}} · ${{r.n}} straight`
         + ` <span class="mut">(${{Math.round(r.rate*100)}}%)</span></span>`;
  }}).join('');
  const n = t.next
    ? `<div class="tnx">Next: <b>${{esc(t.next.home ? 'vs ' + t.next.opp
                                                   : 'away to ' + t.next.opp)}}</b>`
      + ` · ${{esc(when(t.next.kickoff) || t.next.date)}} · ${{esc(t.next.league)}}</div>`
    : `<div class="tnx mut">No fixture scheduled in the next 14 days</div>`;
  return `<div class="trow">
    <div class="th"><span class="tn">${{esc(t.team)}}</span>
      <span class="tl">${{esc(t.league)}} · ${{t.played}} games</span></div>
    ${{n}}
    <div class="runs">${{chips}}</div>
    <div class="fm" style="margin-top:10px">
      <div class="fmt">Last ${{t.recent.length}}</div>
      <div class="fmr">${{t.recent.map(esc).join(' &nbsp;·&nbsp; ')}}</div></div>
  </div>`;
}}
function render() {{
  const term = q.value.trim().toLowerCase();
  let rows, total, html_;
  if (tab === 'leads') {{
    total = LEADS.length;
    rows = LEADS.filter(l => (!league || l.league === league) &&
                             (!term || l.match.toLowerCase().includes(term)));
    html_ = rows.map(card).join('');
    empty.textContent = league
      ? 'No confluences in ' + league + ' right now — both sides of a fixture have to be '
        + 'on matching runs, which is genuinely rare. Try "All teams on a run".'
      : 'No leads match that filter.';
  }} else {{
    total = TEAMS.length;
    rows = TEAMS.filter(t => (!league || t.league === league) &&
                             (!term || t.team.toLowerCase().includes(term)));
    html_ = rows.map(teamRow).join('');
    empty.textContent = 'No teams match that filter.';
  }}
  list.innerHTML = html_;
  cnt.textContent = rows.length + ' of ' + total;
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
for (const b of document.querySelectorAll('.tb')) {{
  b.addEventListener('click', () => {{
    document.querySelectorAll('.tb').forEach(x => x.classList.remove('on'));
    b.classList.add('on');
    tab = b.dataset.tab;
    render();
  }});
}}
q.addEventListener('input', render);
render();
</script></body></html>"""


def build(force=False):
    blob = streaks_fetch.load_or_fetch(force=force)
    fixtures = blob["fixtures"]

    by_team = team_games(fixtures)
    streaks = team_streaks(by_team)
    rates = base_rates(streaks)
    leads = find_leads(fixtures, streaks, rates)[:TOP_LEADS]
    teams = team_rows(streaks, by_team, fixtures, rates)

    # League buttons must cover BOTH views, so draw them from the teams index too —
    # scoping them to fixtures alone hid every league that had runs but no confluence.
    leagues = sorted({f["league"] for f in fixtures if not f["played"]} |
                     {t["league"] for t in teams})
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%b %d %Y · %H:%M UTC")
    meta = (f"{len(streaks)} teams with {MIN_PLAYED}+ games · "
            f"{sum(1 for f in fixtures if not f['played'])} upcoming fixtures scanned")

    os.makedirs(OUT_DIR, exist_ok=True)
    out = os.path.join(OUT_DIR, "streaks.html")
    with open(out, "w") as f:
        f.write(page_html(leads, teams, meta, leagues, now))

    # machine-readable companion, same shape the page consumes
    with open(DATA_OUT, "w") as f:
        json.dump({"built_at": datetime.datetime.now(datetime.timezone.utc)
                   .isoformat(timespec="seconds"),
                   "teams_tracked": len(streaks), "leads": leads, "teams": teams,
                   "base_rates": {k: {str(n): round(v, 4) for n, v in d.items()}
                                  for k, d in rates.items()}}, f, indent=1)

    print(f"wrote {out}  ({os.path.getsize(out)/1024:.0f} KB) — {len(leads)} leads, "
          f"{len(teams)} teams on a run, across {len(leagues)} leagues")
    print(f"wrote {DATA_OUT}")
    return leads


if __name__ == "__main__":
    build(force="--force" in sys.argv)
