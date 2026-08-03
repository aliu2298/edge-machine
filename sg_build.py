#!/usr/bin/env python3
"""sg_build.py — render data/sg_picks.json to public_site/tips.html.

Third, separate board (boards are deliberately not merged): sportsgambler's own
published predictions. Shows exactly the three tracked items per match —
projected score, both-teams-to-score, and the site's main tip — plus results.

Usage:  python3 sg_build.py
"""
import json, os, html, datetime

# Reuse export_public.py's Kalshi lookup so the link logic lives in exactly one
# place (same series list, same team-token matcher, same fail-soft behaviour).
try:
    from export_public import fetch_kalshi_events, venue_link
except Exception:            # keep the board buildable if that import ever breaks
    fetch_kalshi_events = lambda: []
    venue_link = lambda *a, **k: None

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, "data", "sg_picks.json")
OUT = os.path.join(ROOT, "public_site", "tips.html")
RESULTS_BACK_DAYS = 14


def esc(s):
    return html.escape(str(s)) if s is not None else ""


def money(x, sign=False):
    if x is None:
        return "—"
    s = f"{abs(x):.2f}u"
    return ("−" + s) if x < 0 else (("+" + s) if sign else s)


RES_CLS = {"win": "pos", "half_win": "pos", "hit": "pos",
           "loss": "neg", "half_loss": "neg", "miss": "neg",
           "push": "mut", "ungraded": "mut"}
RES_TXT = {"win": "WIN", "half_win": "½ WIN", "loss": "LOSS", "half_loss": "½ LOSS",
           "push": "PUSH", "ungraded": "UNGRADED", "hit": "HIT", "miss": "MISS"}


def chip(v):
    if not v:
        return ""
    return f'<span class="st {RES_CLS.get(v,"mut")}">{RES_TXT.get(v, v.upper())}</span>'


def facts(p):
    """The three tracked items, rendered as a compact fact row."""
    out = []
    if p.get("proj_score"):
        od = f' <b>@{esc(p["proj_score_odds"])}</b>' if p.get("proj_score_odds") else ""
        out.append(f'<div class="f"><span class="fl">Projected score</span>'
                   f'<span class="fv">{esc(p["proj_score"])}{od} {chip(p.get("proj_result"))}</span></div>')
    if p.get("btts_yes_odds"):
        imp = p.get("btts_implied")
        form = f' · form {esc(" / ".join(p.get("btts_form", [])[:2]))}' if p.get("btts_form") else ""
        act = f' → actual {esc(p["btts_actual"])}' if p.get("btts_actual") else ""
        out.append(f'<div class="f"><span class="fl">Both teams to score</span>'
                   f'<span class="fv">Yes {esc(p["btts_yes_odds"])} / No {esc(p["btts_no_odds"])}'
                   f' · implies <b>{esc(imp)}</b>{form}{act} {chip(p.get("btts_result"))}</span></div>')
    return "".join(out)


def card(p, kalshi_url=None):
    dec = p.get("tip_odds_decimal")
    decs = f' <span class="mut">({dec:g} dec)</span>' if dec else ""
    pl = p.get("tip_pl")
    plh = (f'<span class="{"pos" if pl > 0 else "neg" if pl < 0 else "mut"}">{money(pl, True)}</span>'
           if pl is not None else '<span class="mut">—</span>')
    fin = (f'<span class="fin">FT {esc(p["final_score"])}</span>' if p.get("final_score") else "")
    kal = (f'<a class="kbtn kal" href="{esc(kalshi_url)}" target="_blank" rel="noopener">Kalshi ↗</a>'
           if kalshi_url else "")
    return f"""<div class="card">
  <div class="row1"><span class="match">{esc(p.get("match"))}</span>
    <span class="lg">{esc(p.get("league"))}</span>{fin}
    <span class="btns">{kal}<a class="kbtn" href="{esc(p.get("url"))}" target="_blank" rel="noopener">Source ↗</a></span></div>
  <div class="ko">{esc(p.get("kickoff_text") or p.get("date") or "")}</div>
  <div class="tip">{esc(p.get("tip_text") or "no tip published")}{decs}
    {chip(p.get("tip_result"))} {plh}</div>
  {facts(p)}
</div>"""


def build():
    if not os.path.exists(DATA):
        print("no data/sg_picks.json — run sg_scrape.py first")
        return
    blob = json.load(open(DATA))
    picks = blob.get("picks", [])
    today = datetime.date.today()
    back = (today - datetime.timedelta(days=RESULTS_BACK_DAYS)).isoformat()

    kal_events = fetch_kalshi_events()
    def klink(p):
        return venue_link(p.get("match", "").replace(" v ", " vs "),
                          p.get("date"), kal_events)

    pend = sorted([p for p in picks if p.get("status") == "pending"],
                  key=lambda p: (p.get("date") or "", p.get("match") or ""))
    done = sorted([p for p in picks if p.get("status") == "settled"
                   and (p.get("date") or "") >= back],
                  key=lambda p: (p.get("date") or ""), reverse=True)

    tips = [p for p in done if p.get("tip_pl") is not None]
    total = sum(p["tip_pl"] for p in tips)
    wins = sum(1 for p in done if p.get("tip_result") in ("win", "half_win"))
    graded = sum(1 for p in done if p.get("tip_result") not in (None, "ungraded"))
    roi = (100 * total / len(tips)) if tips else 0
    pj = [p for p in done if p.get("proj_result")]
    bt = [p for p in done if p.get("btts_result")]
    upd = (blob.get("updated_at") or "")[:16].replace("T", " ")

    page = f"""<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Edge Machine · Tips</title>
<meta name="description" content="Published football predictions, tracked and settled automatically.">
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
.mut{{color:var(--mut)}}.pos{{color:var(--pos)}}.neg{{color:var(--neg)}}
.nav{{display:flex;gap:8px;margin-top:14px;flex-wrap:wrap}}
.nav a{{font-size:12px;font-weight:700;text-decoration:none;color:var(--mut);
border:1px solid var(--bd);border-radius:999px;padding:5px 13px}}
.nav a:hover{{color:var(--fg);border-color:var(--mut)}}
.nav a.on{{color:var(--fg);border-color:var(--mut);background:#161b26}}
.tiles{{display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:10px;margin-top:18px}}
.tile{{background:var(--card);border:1px solid var(--bd);border-radius:12px;padding:12px 14px}}
.tile b{{display:block;font-size:19px;font-weight:800;font-variant-numeric:tabular-nums}}
.tile span{{font-size:10.5px;text-transform:uppercase;letter-spacing:.07em;color:var(--mut)}}
.card{{background:var(--card);border:1px solid var(--bd);border-radius:12px;padding:15px;margin-bottom:11px}}
.row1{{display:flex;align-items:center;gap:8px;flex-wrap:wrap}}
.match{{font-weight:700;font-size:16px}}
.lg{{font-size:10.5px;font-weight:700;text-transform:uppercase;letter-spacing:.05em;
color:var(--mut);border:1px solid var(--bd);border-radius:999px;padding:2px 8px}}
.fin{{font-size:12px;font-weight:700;color:var(--fg);background:#161b26;
border-radius:6px;padding:2px 8px;font-variant-numeric:tabular-nums}}
.ko{{font-size:12px;color:var(--mut);margin-top:3px}}
.tip{{margin-top:9px;font-weight:600;color:var(--warn)}}
.st{{font-size:10.5px;font-weight:800;letter-spacing:.05em;margin-left:4px}}
.f{{display:flex;gap:10px;font-size:12.5px;margin-top:7px;flex-wrap:wrap}}
.fl{{color:var(--mut);min-width:150px}}
.fv{{color:var(--fg);font-variant-numeric:tabular-nums}}
.btns{{margin-left:auto;display:flex;gap:6px;flex-wrap:wrap}}
.kbtn.kal{{color:#3fb970;border-color:#3fb97055;background:#3fb97014}}
.kbtn.kal:hover{{background:#3fb9702a}}
.kbtn{{font-size:11.5px;font-weight:700;color:#7aa2f7;text-decoration:none;
border:1px solid #7aa2f755;background:#7aa2f714;border-radius:999px;padding:4px 11px}}
.kbtn:hover{{background:#7aa2f72a}}
footer{{margin-top:40px;font-size:12px;color:var(--mut);text-align:center}}
@media (max-width:540px){{body{{padding:18px 10px 44px;font-size:14px}}h1{{font-size:19px}}
.card{{padding:13px}}.match{{font-size:15px}}.btns{{margin-left:0;width:100%}}.fl{{min-width:0}}}}
</style></head><body><div class="wrap">
<h1>Edge Machine · Tips</h1>
<div class="sub">Published predictions from sportsgambler.com — scraped and settled automatically ·
data updated {esc(upd)} UTC</div>
<div class="nav"><a href="./">Sports</a><a href="./earnings.html">Earnings</a>
<a class="on" href="./tips.html">Tips</a></div>

<div class="tiles">
  <div class="tile"><b class="{'pos' if total >= 0 else 'neg'}">{money(total, True)}</b><span>Tip P&amp;L</span></div>
  <div class="tile"><b>{roi:+.1f}%</b><span>ROI</span></div>
  <div class="tile"><b>{wins}/{graded}</b><span>Tips won</span></div>
  <div class="tile"><b>{sum(1 for p in pj if p['proj_result']=='hit')}/{len(pj)}</b><span>Exact score</span></div>
  <div class="tile"><b>{sum(1 for p in bt if p['btts_result']=='hit')}/{len(bt)}</b><span>BTTS called</span></div>
</div>

<h2>Upcoming ({len(pend)})</h2>
{"".join(card(p, klink(p)) for p in pend) or '<div class="mut">No upcoming fixtures in the tracked leagues.</div>'}

<h2>Settled ({len(done)})</h2>
{"".join(card(p, klink(p)) for p in done) or '<div class="mut">Nothing settled yet.</div>'}

<footer>Predictions are sportsgambler.com's, not ours · settled from ESPN final scores ·
paper-tracked research, not betting advice.</footer>
</div></body></html>"""

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as f:
        f.write(page)
    print(f"wrote {OUT}  ({os.path.getsize(OUT)/1024:.0f} KB) — "
          f"{len(pend)} upcoming, {len(done)} settled, tip P&L {money(total, True)}")


if __name__ == "__main__":
    build()
