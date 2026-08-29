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
import streaks_track

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
# (a_key, b_key, headline, why, bet) — `why` is the reasoning line; `bet` is the
# machine-checkable claim, so streaks_track.py can grade the lead against the final score
# without a human deciding what the card "meant".
#   team_gte  — the subject team scores >= n         (subject: "a" or "b")
#   team_eq   — the subject team scores exactly n
#   btts      — both teams score
#   total_gte / total_lte — combined goals
PAIRINGS = [
    ("scoring", "leaky",    "{a} to score 2+",
     "{a} have scored 2+ in {ra} straight; {b} have conceded 2+ in {rb} straight.",
     {"kind": "team_gte", "subject": "a", "n": 2}),
    ("scoring", "porous",   "{a} to score",
     "{a} have scored 2+ in {ra} straight; {b} have conceded in {rb} straight.",
     {"kind": "team_gte", "subject": "a", "n": 1}),
    ("btts",    "btts",     "Both teams to score",
     "Both sides are on a BTTS run — {a} {ra} straight, {b} {rb} straight.",
     {"kind": "btts"}),
    ("over25",  "over25",   "Over 2.5 goals",
     "{a} have gone over 2.5 in {ra} straight; {b} in {rb} straight.",
     {"kind": "total_gte", "n": 3}),
    ("under25", "under25",  "Under 2.5 goals",
     "{a} have gone under 2.5 in {ra} straight; {b} in {rb} straight.",
     {"kind": "total_lte", "n": 2}),
    ("solid",   "blanked",  "{b} to fail to score",
     "{a} have kept {ra} straight clean sheets; {b} have failed to score in {rb} straight.",
     {"kind": "team_eq", "subject": "b", "n": 0}),
    ("blanked", "solid",    "{a} to fail to score",
     "{a} have failed to score in {ra} straight; {b} have kept {rb} straight clean sheets.",
     {"kind": "team_eq", "subject": "a", "n": 0}),
]


def esc(x):
    return html.escape(str(x if x is not None else ""))


def form_seq(games, run_len=0):
    """Recent games (newest first) as compact structured entries for the page's score pills.

    `hit` lights exactly the games IN the run — that is, the first `run_len`. It is
    deliberately NOT "does this game satisfy the predicate": a run is a prefix from the most
    recent game, so a qualifying game sitting the far side of a break is not part of it.
    Lighting those too made a 4-game run render as 6-with-a-gap.
    """
    return [{"s": f"{g['gf']}-{g['ga']}", "opp": g["opp"], "h": g["home"],
             "hit": i < run_len}
            for i, g in enumerate(games[:FORM_GAMES])]


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
        for a_key, b_key, headline, why, bet in PAIRINGS:
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
                    "a_label": STREAK_BY_KEY[a_key][1], "b_label": STREAK_BY_KEY[b_key][1],
                    "strength": ra + rb,
                    "base_rate": rate,
                    # resolve the bet's subject to a concrete team now, so grading never
                    # has to re-derive which side "a" referred to
                    "bet": dict(bet, team=(a if bet.get("subject") == "a" else b))
                            if bet.get("subject") else dict(bet),
                    "a_recent": form_seq(sa_["recent"], ra),
                    "b_recent": form_seq(sb_["recent"], rb),
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
        # rarest run first, so the chip the row leads with is the notable one and
        # `runs[0]` is what the form sequence highlights
        runs = sorted(
            ({"key": k, "label": STREAK_BY_KEY[k][1], "n": n,
              "rate": rates[k][min(n, FORM_GAMES)]}
             for k, n in info["runs"].items()),
            key=lambda r: (r["rate"], -r["n"]))
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
            # highlight the rarest run, which is the one the row leads with
            "recent": form_seq(info["recent"], runs[0]["n"] if runs else 0),
        })
    rows.sort(key=lambda r: (r["best_rate"], -r["longest"], r["team"]))
    return rows


# ---------------------------------------------------------------- rendering
def page_html(leads, teams, track, meta, leagues, now):
    payload = json.dumps(leads).replace("</", "<\\/")
    teams_payload = json.dumps(teams).replace("</", "<\\/")
    track_payload = json.dumps(track).replace("</", "<\\/")
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
details.how{{margin-top:15px;border:1px solid var(--bd);border-radius:10px;
background:var(--card)}}
details.how summary{{cursor:pointer;list-style:none;user-select:none;
font-size:12.5px;font-weight:600;color:var(--mut);padding:10px 14px}}
details.how summary::-webkit-details-marker{{display:none}}
details.how summary::before{{content:"▸";display:inline-block;margin-right:8px;
transition:transform .15s;color:var(--mut)}}
details.how[open] summary::before{{transform:rotate(90deg)}}
details.how summary:hover{{color:var(--fg)}}
.howbody{{padding:0 14px 13px 32px;font-size:12.5px;color:var(--mut);line-height:1.6}}
.howbody p{{margin:0 0 8px}}
.howbody p:last-child{{margin-bottom:0}}
.howbody b{{color:var(--fg);font-weight:600}}
.controls{{position:sticky;top:0;z-index:20;background:var(--bg);
padding:14px 0 10px;margin-top:18px;border-bottom:1px solid var(--bd)}}
.tabs{{display:flex;gap:6px;margin-bottom:10px}}
.tb{{font:inherit;font-size:12.5px;font-weight:800;color:var(--mut);cursor:pointer;
background:none;border:1px solid var(--bd);border-radius:9px;padding:7px 15px;transition:all .12s}}
.tb:hover{{color:var(--fg);border-color:var(--mut)}}
.tb.on{{color:var(--fg);background:#161b26;border-color:var(--mut)}}
.trow{{background:var(--card);border:1px solid var(--bd);border-radius:11px;
margin-bottom:9px;overflow:hidden}}
.th{{display:flex;align-items:baseline;gap:9px;flex-wrap:wrap;
padding:12px 15px 10px;border-bottom:1px solid var(--bd)}}
.tn{{font-weight:700;font-size:15px;letter-spacing:-.012em}}
.tl{{font-size:11.5px;color:var(--mut);margin-left:auto;white-space:nowrap}}
.tbody{{padding:11px 15px 12px}}
.tnx{{font-size:12px;color:var(--mut);margin-top:10px;
padding-top:9px;border-top:1px solid var(--bd)}}
.tnx b{{color:var(--fg);font-weight:600}}
.truns{{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:9px}}
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
/* --- card: fixture header → evidence → the lead, in that order --- */
.card{{background:var(--card);border:1px solid var(--bd);border-radius:12px;
margin-bottom:11px;overflow:hidden}}
.chd{{display:flex;align-items:baseline;gap:10px;flex-wrap:wrap;
padding:13px 15px 11px;border-bottom:1px solid var(--bd)}}
.fx{{font-weight:700;font-size:15px;letter-spacing:-.012em}}
.fxm{{font-size:11.5px;color:var(--mut);margin-left:auto;white-space:nowrap}}
.ev{{padding:11px 15px 3px}}
.leg{{display:flex;align-items:baseline;gap:9px;flex-wrap:wrap;margin-bottom:7px}}
.lgn{{font-size:13px;font-weight:700;min-width:0}}
.lgr{{font-size:11px;font-weight:700;letter-spacing:.02em;border-radius:999px;
padding:2px 8px;border:1px solid;white-space:nowrap}}
.lgr.a{{color:var(--pos);border-color:#3fb97055;background:#3fb97014}}
.lgr.b{{color:var(--acc);border-color:#7aa2f755;background:#7aa2f714}}
.seq{{display:flex;gap:4px;flex-wrap:wrap;margin:0 0 11px}}
.sc{{font-size:11px;font-weight:700;font-variant-numeric:tabular-nums;
border-radius:5px;padding:2px 6px;background:#0c1017;border:1px solid var(--bd);
color:var(--mut);cursor:default}}
.sc.hit{{color:var(--fg);border-color:#3fb97044;background:#3fb9700f}}
/* the lead — its own section, after the evidence that supports it */
.lead{{display:flex;align-items:center;gap:10px;flex-wrap:wrap;
padding:11px 15px;background:#0c1017;border-top:1px solid var(--bd)}}
.lbl{{font-size:9.5px;font-weight:800;letter-spacing:.09em;color:var(--mut);
text-transform:uppercase;white-space:nowrap}}
.hl{{font-weight:800;font-size:14.5px;color:var(--warn);letter-spacing:-.01em}}
.rare{{font-size:10px;font-weight:800;border-radius:999px;padding:2px 8px;
border:1px solid;margin-left:auto;white-space:nowrap}}
.rare.hot{{color:var(--warn);border-color:#f0b42955;background:#f0b42914}}
.rare.mid{{color:var(--mut);border-color:var(--bd)}}
.rare.common{{color:var(--neg);border-color:#e06c7544;background:#e06c750f}}
/* --- track record --- */
.tr-note{{font-size:12.5px;color:var(--mut);line-height:1.6;background:var(--card);
border:1px solid var(--bd);border-radius:10px;padding:12px 14px;margin-bottom:12px}}
.tr-note b{{color:var(--fg);font-weight:600}}
.tiles{{display:flex;gap:9px;flex-wrap:wrap;margin-bottom:13px}}
.tile{{flex:1;min-width:104px;background:var(--card);border:1px solid var(--bd);
border-radius:10px;padding:11px 13px}}
.tile b{{display:block;font-size:19px;font-weight:800;font-variant-numeric:tabular-nums}}
.tile span{{font-size:11px;color:var(--mut)}}
.tbl{{background:var(--card);border:1px solid var(--bd);border-radius:11px;
overflow-x:auto;margin-bottom:13px}}
table{{width:100%;border-collapse:collapse;font-size:12.5px}}
th{{text-align:left;font-size:10px;text-transform:uppercase;letter-spacing:.07em;
color:var(--mut);padding:9px 11px;border-bottom:1px solid var(--bd);white-space:nowrap}}
td{{padding:9px 11px;border-bottom:1px solid #1a1f2b;white-space:nowrap}}
tr:last-child td{{border-bottom:none}}
.num{{font-variant-numeric:tabular-nums;text-align:right}}
.sig{{font-size:9.5px;font-weight:800;letter-spacing:.05em;border-radius:999px;
padding:2px 7px;border:1px solid}}
.sig.y{{color:var(--pos);border-color:#3fb97055;background:#3fb97014}}
.sig.n{{color:var(--mut);border-color:var(--bd)}}
.empty{{color:var(--mut);padding:26px 0;text-align:center;line-height:1.6}}
footer{{margin-top:40px;font-size:12px;color:var(--mut);text-align:center}}
@media (max-width:560px){{
  body{{padding:18px 10px 44px;font-size:14px}}
  h1{{font-size:19px}} .hl{{font-size:14px}}
  .fxm{{margin-left:0;width:100%}}
  .rare{{margin-left:0}}
}}
</style></head><body><div class="wrap">
<h1>Edge Machine · Streaks</h1>
<div class="sub">Teams on a run, matched against a next opponent who is soft in the same
place · updated {esc(now)}</div>
<div class="nav"><a href="./">Sports</a><a class="on" href="./streaks.html">Streaks</a></div>

<details class="how">
<summary>A run only counts when the opponent is soft in the same place — how this works</summary>
<div class="howbody">
<p>A streak on its own is not an edge; plenty of good sides score freely. What is shown here
is the <b>confluence</b>: one team's run meeting the other's matching weakness in a fixture
not yet played.</p>
<p>Every lead carries a <b>rarity</b> chip — the share of tracked teams currently on a run
that long. When that share is high the pattern is ordinary, and the chip says so. Leads are
sorted rarest first, not longest.</p>
<p>Form is measured across <b>all</b> tracked competitions (last {FORM_GAMES} games, minimum
{MIN_PLAYED} played), because form does not reset when a side walks into a European tie.</p>
<p>Confluences are genuinely rare — a whole league can have none on a given day. <b>All teams
on a run</b> browses the raw runs instead. Leads to look at: not picks, and not betting
advice.</p>
</div>
</details>

<div class="controls">
  <div class="tabs">
    <button class="tb on" data-tab="leads">Leads</button>
    <button class="tb" data-tab="teams">All teams on a run</button>
    <button class="tb" data-tab="track">Track record</button>
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
const TRACK = {track_payload};
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
// Recent results as compact pills, newest LEFT. Games inside the run are lit; the rest
// are dimmed, so the streak is visible at a glance instead of spelled out in prose.
function seq(games) {{
  return `<div class="seq">` + games.map(g =>
    `<span class="sc${{g.hit ? ' hit' : ''}}" title="${{esc(g.s)}} ${{g.h ? 'home' : 'away'}}`
    + ` v ${{esc(g.opp)}}">${{esc(g.s)}}</span>`).join('') + `</div>`;
}}
function leg(name, label, n, side, games) {{
  return `<div class="leg"><span class="lgn">${{esc(name)}}</span>`
       + `<span class="lgr ${{side}}">${{esc(label)}} · ${{n}} straight</span></div>`
       + seq(games);
}}
function card(l) {{
  const [cls, txt] = rarity(l.base_rate);
  return `<div class="card">
    <div class="chd">
      <span class="fx">${{esc(l.match)}}</span>
      <span class="fxm">${{esc(l.league)}} · ${{esc(when(l.kickoff) || l.date)}}</span>
    </div>
    <div class="ev">
      ${{leg(l.a, l.a_label, l.a_run, 'a', l.a_recent)}}
      ${{leg(l.b, l.b_label, l.b_run, 'b', l.b_recent)}}
    </div>
    <div class="lead">
      <span class="lbl">Lead</span>
      <span class="hl">${{esc(l.headline)}}</span>
      <span class="rare ${{cls}}">${{esc(txt)}}</span>
    </div>
  </div>`;
}}
function teamRow(t) {{
  const chips = t.runs.map(r => {{
    const [cls] = rarity(r.rate);
    return `<span class="rare ${{cls}}" style="margin-left:0">${{esc(r.label)}} · ${{r.n}}`
         + ` straight · ${{Math.round(r.rate*100)}}%</span>`;
  }}).join('');
  const n = t.next
    ? `<div class="tnx">Next: <b>${{esc(t.next.home ? 'vs ' + t.next.opp
                                                   : 'away to ' + t.next.opp)}}</b>`
      + ` · ${{esc(when(t.next.kickoff) || t.next.date)}} · ${{esc(t.next.league)}}</div>`
    : `<div class="tnx">No fixture scheduled in the next 14 days</div>`;
  return `<div class="trow">
    <div class="th"><span class="tn">${{esc(t.team)}}</span>
      <span class="tl">${{esc(t.league)}} · ${{t.played}} games</span></div>
    <div class="tbody">
      <div class="truns">${{chips}}</div>
      ${{seq(t.recent)}}
      ${{n}}
    </div>
  </div>`;
}}
const BETNAME = {{
  'btts': 'Both teams to score', 'total_gte:3': 'Over 2.5 goals',
  'total_lte:2': 'Under 2.5 goals', 'team_gte:2': 'Team to score 2+',
  'team_gte:1': 'Team to score', 'team_eq:0': 'Team to fail to score'
}};
function resultTable(rows) {{
  return `<div class="tbl"><table>
    <tr><th>Bet</th><th class="num">n</th><th class="num">hits</th><th class="num">rate</th>
        <th class="num">baseline</th><th class="num">lift</th><th></th></tr>
    ${{rows.map(r => `<tr>
      <td>${{esc(BETNAME[r.kind] || r.kind)}}</td>
      <td class="num">${{r.n}}</td>
      <td class="num">${{r.hits}}</td>
      <td class="num">${{Math.round(r.rate*100)}}%</td>
      <td class="num mut" title="league-adjusted${{r.global_base != null
        ? '; global ' + Math.round(r.global_base*100) + '%' : ''}}">${{
        r.base == null ? '—' : Math.round(r.base*100) + '%'}}</td>
      <td class="num ${{r.lift == null ? '' : (r.lift >= 0 ? 'pos' : 'neg')}}">${{
        r.lift == null ? '—' : (r.lift >= 0 ? '+' : '') + (r.lift*100).toFixed(1) + 'pp'}}</td>
      <td><span class="sig ${{r.significant ? 'y' : 'n'}}">${{
        r.significant ? 'SIGNIFICANT' : 'not sig'}}</span></td>
    </tr>`).join('')}}</table></div>`;
}}
function trackView() {{
  const t = TRACK;
  const note = `<div class="tr-note">This board carries no odds, so this is <b>not</b>
    profit and cannot be. What it measures is whether flagging a fixture beats not flagging
    it: each lead's hit rate against the same outcome's <b>league-adjusted baseline</b>.
    The adjustment matters — BTTS leads cluster in high-scoring leagues, and comparing them
    to a global rate would credit the streak for what is really the schedule.
    <b>Lift is the number that counts</b>; a hit rate alone is not evidence, and a lift is
    only called significant when its 95% interval clears the baseline.</div>`;

  let out = note;

  // Backtest first: it is the only section with a real sample early on.
  if (t.backtest_n) {{
    out += `<h2>Backtest · same rules replayed over past fixtures</h2>`
        + `<div class="tr-note">Walk-forward over ${{t.population_fixtures}} played
           fixtures: for each one, form is computed <b>only from games before it</b>, then
           graded on the actual result. No lookahead. ${{
             t.backtest_any_sig
               ? 'At least one bet type clears its baseline — but several are tested at once, so some separation is expected by chance.'
               : '<b>No bet type clears its baseline.</b> On this sample the confluence is not distinguishable from the population — no measurable edge yet.'}}</div>`
        + `<div class="tiles">
             <div class="tile"><b>${{t.backtest_n}}</b><span>Leads replayed</span></div>
             <div class="tile"><b>${{Math.round(t.backtest_rate*100)}}%</b><span>Hit rate</span></div>
           </div>`
        + resultTable(t.backtest_rows);
  }}

  out += `<h2>Live ledger · leads logged when published</h2>`;
  if (!t.graded) {{
    out += `<div class="empty">Nothing graded yet — ${{t.pending}} lead${{
      t.pending === 1 ? '' : 's'}} pending.<br>They settle automatically as their fixtures
      are played.</div>`;
    return out;
  }}
  out += `<div class="tiles">
    <div class="tile"><b>${{t.graded}}</b><span>Graded</span></div>
    <div class="tile"><b>${{Math.round(t.overall_rate*100)}}%</b><span>Hit rate</span></div>
    <div class="tile"><b>${{t.pending}}</b><span>Pending</span></div>
    <div class="tile"><b>${{t.void}}</b><span>Void</span></div>
  </div>` + resultTable(t.rows);
  if (t.recent.length) {{
    out += `<h2>Recently graded</h2><div class="tbl"><table>
      <tr><th>Date</th><th>Match</th><th>Lead</th><th class="num">Final</th><th></th></tr>
      ${{t.recent.map(e => `<tr>
        <td class="mut">${{esc(e.date)}}</td><td>${{esc(e.match)}}</td>
        <td>${{esc(e.headline)}}</td><td class="num">${{esc(e.final || '—')}}</td>
        <td><span class="sig ${{e.status === 'hit' ? 'y' : 'n'}}">${{
          esc(e.status.toUpperCase())}}</span></td></tr>`).join('')}}
      </table></div>`;
  }}
  return out;
}}
function render() {{
  const term = q.value.trim().toLowerCase();
  let rows, total, html_;
  if (tab === 'track') {{
    list.innerHTML = trackView();
    cnt.textContent = TRACK.graded + ' graded';
    empty.style.display = 'none';
    return;
  }}
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
    // the league/team filters describe fixtures, which the track view does not list
    const hide = tab === 'track' ? 'none' : '';
    document.querySelector('.lgs').style.display = hide;
    document.querySelector('.srch').style.display = hide ? 'none' : 'flex';
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

    # Log what is being published and settle anything now finished. Recording happens at
    # publish time so the ledger holds the claim as it was actually made, not a later
    # rationalisation of it.
    ledger, added = streaks_track.record(leads)
    ledger, newly_graded = streaks_track.grade(fixtures, ledger)
    streaks_track.save(ledger)
    track = streaks_track.report(fixtures, ledger)
    print(f"  ledger: +{added} new, {newly_graded} graded now, "
          f"{track['graded']} settled / {track['pending']} pending")

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
        f.write(page_html(leads, teams, track, meta, leagues, now))

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
