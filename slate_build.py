#!/usr/bin/env python3
"""slate_build.py — render the three live picks to public_site/index.html.

The board is three cards, laid out as playing cards: 2:3 proportions, a corner index
(market abbreviation over a suit pip, mirrored upside-down at the foot) and a stamped face
once the result is known. Suggestive rather than literal — the card shape organises the
information, it does not become the point.

Card reads top to bottom the way the pick was reasoned: what the bet is, which fixture,
when it kicks off, then the evidence underneath it. Rarity sits at the foot, because it is
the caveat on the claim rather than the claim itself.

Nothing here decides anything. Selection, grading and the ledger all live in slate.py;
this module only draws what that produced.

Usage:  python3 slate_build.py   →  public_site/index.html
"""
import json, os, html, datetime

import slate as S
import streaks_fetch

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(ROOT, "public_site")

# bet kind -> (corner abbreviation, suit pip). Suits distinguish market families at a
# glance; they carry no ranking, they are just the card's index.
MARKETS = {
    "btts":         ("BTTS", "♥"),
    "total_gte:3":  ("O2.5", "♠"),
    "total_gte:2":  ("O1.5", "♠"),
    "total_lte:2":  ("U2.5", "♣"),
    "team_gte:2":   ("2+",   "♦"),
    "team_gte:1":   ("1+",   "♦"),
    "team_eq:0":    ("0",    "♦"),
}


def esc(x):
    return html.escape(str(x if x is not None else ""))


def market_index(bet):
    return MARKETS.get(S.T.bet_key(bet), ("PICK", "★"))


def rarity_class(r):
    if r <= 0.10:
        return "hot", f"rare · {round(r*100)}%"
    if r <= 0.25:
        return "mid", f"uncommon · {round(r*100)}%"
    return "common", f"common · {round(r*100)}%"


def seq_html(games, limit=6):
    """Compact score pills. Dashed = preseason friendly, lit = inside the run."""
    out = []
    for g in games[:limit]:
        cls = "sc"
        if g.get("hit"):
            cls += " hit"
        if g.get("comp") is False:
            cls += " fr"
        out.append(f'<span class="{cls}" title="{esc(g["s"])} '
                   f'{"home" if g.get("h") else "away"} v {esc(g.get("opp"))}">'
                   f'{esc(g["s"])}</span>')
    return f'<div class="seq">{"".join(out)}</div>'


def market_link(p):
    """Resolve the pick's market URL AT RENDER TIME, not from the ledger.

    A pick is locked at draw — runs, rarity, the bet spec — because those are the claim
    being judged. The venue link is not part of that claim, it is a convenience, and
    freezing it broke on the Kalshi->Bovada switch: three live picks kept their stored
    Kalshi URLs under a "Bovada" label, which is worse than having no link at all.
    Resolving live means a venue change takes effect immediately for picks already drawn.
    """
    try:
        from venues import fetch_bovada_events, venue_link
        return venue_link(p["match"].replace(" v ", " vs "),
                          p.get("kickoff") or p.get("date"), fetch_bovada_events())
    except Exception:
        return None


def card_html(p):
    abbr, pip = market_index(p["bet"])
    rcls, rtxt = rarity_class(p["base_rate"])
    live = p["status"] == "live"
    stamp = ""
    if not live:
        st = p["status"]
        final = f'<span>{esc(p["final"])}</span>' if p.get("final") else ""
        stamp = f'<div class="stamp {st}">{esc(st.upper())}{final}</div>'
    mkt = market_link(p)
    kalshi = (f'<a class="kbtn" href="{esc(mkt)}" target="_blank" '
              f'rel="noopener">Bovada ↗</a>' if mkt else "")
    ko = esc(p.get("kickoff") or "")
    return f"""<div class="pcard {'live' if live else 'done'}">
  <div class="idx tl"><b>{esc(abbr)}</b><i>{pip}</i></div>
  <div class="idx br"><b>{esc(abbr)}</b><i>{pip}</i></div>
  <div class="pipmark">{pip}</div>
  {stamp}
  <div class="pbody">
    <div class="phead">{esc(p["headline"])}</div>
    <div class="pfx">{esc(p["match"])}</div>
    <div class="pmeta">{esc(p["league"])} · <time data-ko="{ko}">{ko[5:16].replace("T"," ")}</time></div>
    {f'<div class="pcd" data-cd="{ko}"></div>' if live else ''}
    <div class="pev">
      <div class="leg"><span>{esc(p["a"])}</span>
        <em>{esc(p.get("a_label") or "")} · {p["a_run"]}</em></div>
      {seq_html(p.get("a_recent", []))}
      <div class="leg"><span>{esc(p["b"])}</span>
        <em>{esc(p.get("b_label") or "")} · {p["b_run"]}</em></div>
      {seq_html(p.get("b_recent", []))}
    </div>
  </div>
  <div class="pfoot">
    <span class="rare {rcls}">{esc(rtxt)}</span>{kalshi}
  </div>
</div>"""


def page_html(live, report, horizon, now):
    cards = "".join(card_html(p) for p in live)
    for _ in range(S.SLATE_SIZE - len(live)):
        cards += ('<div class="pcard empty"><div class="pbody">'
                  '<div class="eslot">No qualifying pick</div>'
                  '<div class="emsg">A slot opens as soon as a confluence appears on an '
                  'unplayed fixture.</div></div></div>')

    rows = "".join(
        f"""<tr><td class="mut">{esc((p.get("kickoff") or p["date"])[:10])}</td>
        <td>{esc(p["match"])}</td><td>{esc(p["headline"])}</td>
        <td class="num">{esc(p.get("final") or "—")}</td>
        <td><span class="st {p['status']}">{esc(p['status'].upper())}</span></td></tr>"""
        for p in report["history"][:40])

    perf = ""
    if report["graded"]:
        perf = "".join(
            f"""<tr><td>{esc(MARKETS.get(r['kind'], ('?',))[0])}</td>
            <td class="num">{r['n']}</td><td class="num">{r['hits']}</td>
            <td class="num">{round(r['rate']*100)}%</td>
            <td class="num mut">{'—' if r['base'] is None else str(round(r['base']*100))+'%'}</td>
            <td class="num {'pos' if (r['lift'] or 0) >= 0 else 'neg'}">
              {'—' if r['lift'] is None else ('+' if r['lift'] >= 0 else '')+format(r['lift']*100,'.1f')+'pp'}</td>
            <td><span class="sig {'y' if r['significant'] else 'n'}">
              {'SIGNIFICANT' if r['significant'] else 'not sig'}</span></td></tr>"""
            for r in report["rows"])

    hz = ("" if not horizon else
          f"next {horizon} day{'' if horizon == 1 else 's'}")

    return f"""<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Edge Machine · Picks</title>
<meta name="description" content="Three auto-drawn picks, graded on the final score. Research, not betting advice.">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<style>
:root{{--bg:#0a0d14;--card:#10141d;--bd:#232936;--fg:#eef2f7;--mut:#8b94a7;
--pos:#3fb970;--neg:#e06c75;--warn:#f0b429;--acc:#7aa2f7}}
*{{box-sizing:border-box;margin:0}}
body{{background:var(--bg);color:var(--fg);font:15px/1.45 Inter,system-ui,sans-serif;
letter-spacing:-.011em;-webkit-font-smoothing:antialiased;padding:28px 16px 60px}}
.wrap{{max-width:1000px;margin:0 auto}}
h1{{font-size:22px;font-weight:800;letter-spacing:-.02em}}
h2{{font-size:13px;font-weight:700;text-transform:uppercase;letter-spacing:.08em;
color:var(--mut);margin:34px 0 12px}}
.sub{{color:var(--mut);font-size:13px;margin-top:4px}}
.mut{{color:var(--mut)}}.pos{{color:var(--pos)}}.neg{{color:var(--neg)}}
.nav{{display:flex;gap:8px;margin-top:14px;flex-wrap:wrap}}
.nav a{{font-size:12px;font-weight:700;text-decoration:none;color:var(--mut);
border:1px solid var(--bd);border-radius:999px;padding:5px 13px}}
.nav a:hover{{color:var(--fg);border-color:var(--mut)}}
.nav a.on{{color:var(--fg);border-color:var(--mut);background:#161b26}}
.note{{font-size:12.5px;color:var(--mut);line-height:1.6;background:var(--card);
border:1px solid var(--bd);border-radius:10px;padding:12px 14px;margin-top:15px}}
.note b{{color:var(--fg);font-weight:600}}

/* ---- the three cards ---- */
.hand{{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;margin-top:22px}}
.pcard{{position:relative;min-height:430px;background:var(--card);
border:1px solid var(--bd);border-radius:14px;padding:16px 14px;
display:flex;flex-direction:column;overflow:hidden;
box-shadow:0 1px 0 #ffffff08 inset, 0 6px 18px #0006}}
.pcard.done{{opacity:.72}}
.pcard.empty{{border-style:dashed;box-shadow:none;justify-content:center;text-align:center}}
/* corner index, mirrored at the foot like a real card */
.idx{{position:absolute;font-weight:800;line-height:1;color:var(--mut);
display:flex;flex-direction:column;align-items:center;gap:2px}}
.idx b{{font-size:10.5px;letter-spacing:.04em}}
.idx i{{font-style:normal;font-size:13px}}
.idx.tl{{top:11px;left:11px}}
.idx.br{{bottom:11px;right:11px;transform:rotate(180deg)}}
.pipmark{{position:absolute;left:50%;top:58%;transform:translate(-50%,-50%);
font-size:120px;line-height:1;color:var(--fg);opacity:.035;pointer-events:none;
user-select:none;z-index:0}}
.pbody{{position:relative;z-index:1;flex:1;display:flex;flex-direction:column;
min-height:0;padding:22px 4px 0;overflow:hidden}}
.phead{{font-size:16px;font-weight:800;color:var(--warn);letter-spacing:-.015em;
line-height:1.25}}
.pfx{{font-size:13px;font-weight:600;margin-top:8px;line-height:1.3}}
.pmeta{{font-size:11px;color:var(--mut);margin-top:3px}}
.pcd{{font-size:11.5px;font-weight:800;color:var(--warn);margin-top:8px;
font-variant-numeric:tabular-nums}}
.pcd.later{{color:var(--mut)}}
.pev{{margin-top:16px}}
.leg{{display:flex;align-items:baseline;gap:6px;font-size:11.5px;margin-top:7px}}
.leg span{{font-weight:700;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
.leg em{{font-style:normal;color:var(--mut);font-size:10.5px;white-space:nowrap;
margin-left:auto}}
.seq{{display:flex;gap:3px;flex-wrap:wrap;margin-top:4px}}
.sc{{font-size:10px;font-weight:700;font-variant-numeric:tabular-nums;border-radius:4px;
padding:1px 4px;background:#0c1017;border:1px solid var(--bd);color:var(--mut)}}
.sc.hit{{color:var(--fg);border-color:#3fb97044;background:#3fb9700f}}
.sc.fr{{border-style:dashed}}
.pfoot{{position:relative;z-index:1;display:flex;align-items:center;gap:8px;flex-wrap:wrap;
padding-top:12px;margin-top:auto;border-top:1px solid var(--bd);
padding-right:34px}}   /* 34px keeps clear of the mirrored corner index */
.rare{{font-size:10px;font-weight:800;border-radius:999px;padding:2px 8px;border:1px solid}}
.rare.hot{{color:var(--warn);border-color:#f0b42955;background:#f0b42914}}
.rare.mid{{color:var(--mut);border-color:var(--bd)}}
.rare.common{{color:var(--neg);border-color:#e06c7544;background:#e06c750f}}
.kbtn{{font-size:10.5px;font-weight:700;color:var(--acc);text-decoration:none;
border:1px solid #7aa2f755;background:#7aa2f714;border-radius:999px;padding:2px 9px;
margin-left:auto}}
.kbtn:hover{{background:#7aa2f72a}}
.eslot{{font-size:13px;font-weight:700;color:var(--mut)}}
.emsg{{font-size:11.5px;color:var(--mut);margin-top:7px;line-height:1.5;padding:0 6px}}
/* result stamp */
.stamp{{position:absolute;top:50%;left:50%;z-index:2;
transform:translate(-50%,-50%) rotate(-14deg);
font-size:26px;font-weight:800;letter-spacing:.06em;padding:6px 16px;
border:3px solid;border-radius:8px;text-align:center;pointer-events:none;
background:#0a0d14cc}}
.stamp span{{display:block;font-size:12px;font-weight:700;letter-spacing:.02em;
margin-top:3px;opacity:.85}}
.stamp.hit{{color:var(--pos);border-color:var(--pos)}}
.stamp.miss{{color:var(--neg);border-color:var(--neg)}}
.stamp.void{{color:var(--mut);border-color:var(--mut)}}

/* ---- tables ---- */
.tbl{{background:var(--card);border:1px solid var(--bd);border-radius:11px;
overflow-x:auto;margin-bottom:13px}}
table{{width:100%;border-collapse:collapse;font-size:12.5px}}
th{{text-align:left;font-size:10px;text-transform:uppercase;letter-spacing:.07em;
color:var(--mut);padding:9px 11px;border-bottom:1px solid var(--bd);white-space:nowrap}}
td{{padding:9px 11px;border-bottom:1px solid #1a1f2b;white-space:nowrap}}
tr:last-child td{{border-bottom:none}}
.num{{font-variant-numeric:tabular-nums;text-align:right}}
.st{{font-size:9.5px;font-weight:800;letter-spacing:.05em;border-radius:999px;
padding:2px 7px;border:1px solid}}
.st.hit{{color:var(--pos);border-color:#3fb97055;background:#3fb97014}}
.st.miss{{color:var(--neg);border-color:#e06c7555;background:#e06c7514}}
.st.void{{color:var(--mut);border-color:var(--bd)}}
.sig{{font-size:9.5px;font-weight:800;border-radius:999px;padding:2px 7px;border:1px solid}}
.sig.y{{color:var(--pos);border-color:#3fb97055;background:#3fb97014}}
.sig.n{{color:var(--mut);border-color:var(--bd)}}
.tiles{{display:flex;gap:9px;flex-wrap:wrap;margin-bottom:13px}}
.tile{{flex:1;min-width:104px;background:var(--card);border:1px solid var(--bd);
border-radius:10px;padding:11px 13px}}
.tile b{{display:block;font-size:19px;font-weight:800;font-variant-numeric:tabular-nums}}
.tile span{{font-size:11px;color:var(--mut)}}
footer{{margin-top:40px;font-size:12px;color:var(--mut);text-align:center}}
@media (max-width:820px){{
  .hand{{grid-template-columns:1fr;gap:14px}}
  .pcard{{min-height:0}}
  .pbody{{padding-top:26px}}
  .pev{{margin-top:16px}}
}}
</style></head><body><div class="wrap">
<h1>Edge Machine</h1>
<div class="sub">Three picks drawn automatically from streak confluences · graded on the
final score · all times CT · updated {esc(now)}</div>
<div class="nav"><a class="on" href="./">Picks</a><a href="./streaks.html">Streaks</a>
<a href="./record.html">Record</a></div>

<div class="hand">{cards}</div>

<div class="note">Picks are drawn from the <b>Streaks</b> board: one team's run meeting the
next opponent's matching weakness. Rarest first, <b>one pick per fixture and one per
team</b>, so the three are independent rather than three angles on the same match. A slot
refills as soon as its pick settles{f' · currently reaching {hz}' if hz else ''}.
Every pick is <b>locked when drawn</b> — the runs behind it keep moving, so the card shows
what was claimed at the time, not a tidier version found later.
<b>No edge is claimed.</b> Results are judged against the rate the teams involved manage
anyway — not a league average, which would credit the pick for team quality.
Research, not betting advice.</div>

<div class="note">Results live on the <a href="./record.html">Record</a>
page — graded picks, leads and on-fire runs, each against what those teams do anyway.</div>

<footer>Read-only static export · picks are auto-drawn research, not betting advice.</footer>
</div>
<script>
const TZ='America/Chicago';
for (const t of document.querySelectorAll('time[data-ko]')) {{
  const d=new Date(t.dataset.ko);
  if(!isNaN(d)) t.textContent=d.toLocaleString('en-US',{{timeZone:TZ,weekday:'short',
    month:'short',day:'numeric',hour:'numeric',minute:'2-digit'}});
}}
function countdown(iso){{
  const d=new Date(iso); if(isNaN(d)) return ['later',''];
  let ms=d-new Date();
  if(ms<=0) return ['later', ms>-2.5*3600*1000 ? 'kicked off' : 'played'];
  const mins=Math.floor(ms/60000), days=Math.floor(mins/1440),
        hrs=Math.floor((mins%1440)/60), m=mins%60;
  const txt = days>0 ? `in ${{days}}d ${{hrs}}h`
            : hrs>0  ? `in ${{hrs}}h ${{String(m).padStart(2,'0')}}m`
            :          `in ${{m}}m`;
  return [mins<=720?'soon':'later', txt];
}}
function tick(){{
  for(const el of document.querySelectorAll('.pcd[data-cd]')){{
    const [cls,txt]=countdown(el.dataset.cd);
    el.textContent=txt; el.className='pcd '+cls;
  }}
}}
tick(); setInterval(tick,30000);
</script></body></html>"""


def build():
    fixtures = streaks_fetch.load_or_fetch()["fixtures"]
    blob, graded, drawn = S.run(fixtures)
    S.save(blob)
    rep = S.report(fixtures, blob)
    live = S.live_picks(blob)
    hz = S.horizon_days(blob)
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%b %d %Y · %H:%M UTC")

    os.makedirs(OUT_DIR, exist_ok=True)
    out = os.path.join(OUT_DIR, "index.html")
    with open(out, "w") as f:
        f.write(page_html(live, rep, hz, now))
    print(f"  slate: graded {graded}, drew {len(drawn)}, {len(live)} live")
    print(f"wrote {out}  ({os.path.getsize(out)/1024:.0f} KB) — "
          f"{rep['graded']} graded, {len(rep['history'])} settled")


if __name__ == "__main__":
    build()
