"""The NBA page's top half (2026-10-31, Olu: "clumsy"): an "NBA at a glance" table, then one card per ACTIVE lane in one
layout (the rule in a sentence, the live record, folds for other exits, in-sample research and trades), the blind
baselines (2026-11-01), then the win margin tracker. Presentation only: every figure is read from the same ledgers as
before; no rule, record or ledger changes. Header-row tables, so sandbox_build.label_cells names each cell for the phone cards. No inline style or SVG
(the NBA page forbids both). Never breaks the page: nba_pace_build wraps place().
"""
import html as _h
import os

import chaos_build as CB
import chaos_replay as C
import mentions_split as MS
import nba_winmargin_build as WB
import nba_wm_nofade as N
import nba_wm_nofade_build as NB

YES_ID, NO_ID, ML_ID = "nba_winmargin_split", "nba_wm_nofade", "nba_ml_dog_tp50"
SAMPLE_ID = "nba_winmargin_split_insample"
# The moneyline underdog is a BASELINE since 2026-11-01 (Olu: no lane may select blind): its own block under the
# active lanes, out of the glance, with no status.

RULES = {
    YES_ID: "Buy YES on a 1-5 or 6-10 win margin bucket (either team) priced 10-20c an hour before the tip; rest a sell for half at 2x "
            "and half at 3x, filled only by traded prints from the tip on; the rest is held.",
    NO_ID: "After the tip, rest a NO buy at 75% of a bucket's pregame NO price (10-95c) and sell it back at the pregame price on a "
           "traded print, else hold; 85% and 65% are tracked too.",
}


def esc(x):
    return _h.escape(str(x))


def _pct(v):
    return "—" if v is None else f"{v * 100:+.1f}%"


def _z(v):
    return "—" if v is None else f"{v:+.2f}"


def _lanes(chaos):
    return CB.with_config(chaos).get("lanes") or {}


def how_read():
    return ('<details class="section-disclosure" id="how-read"><summary><b>How these lanes are read</b><span>one place for the rules that apply to every card</span></summary>'
            '<ul class="sm"><li>Sandbox, paper only: no orders, replayed from Kalshi\'s trade prints and 1-minute candles.</li>'
            '<li>A buy is at the real ask before the tip (or a resting bid after it); a sell fills only on a traded print.</li>'
            '<li>The split sells half at 2x and half at 3x of the price paid. "Hold" is the same entries kept to settlement.</li>'
            '<li>The outcome is the game: one game is one event however many entries it holds. z is clustered by night.</li>'
            f'<li>Review at {C.REVIEW_N} settled events, decide at {C.PROMOTE_N}. Maker fees on resting orders, taker fees on a market buy.</li>'
            '<li>An entry counts only when its ask was real: 10+ contracts traded at or through it within an hour, and not under half the last trade. The rest are listed as unverified ask and leave the record.</li>'
            '<li>An in-sample row replays the days a rule was chosen on. It is not evidence and is never a headline.</li></ul>'
            f'<p class="sm mut">Every cheap-side lane is also listed in the <a href="./sandbox.html#chaos">Sandbox\'s Chaos index</a>.</p></details>')


def _chaos_row(L):
    r = CB.split_hold(L)
    return dict(events=r["events"], split=r["split"] if r["n_split"] else None, hold=r["hold"], z=r["z"], status=CB.status_of(L, r["events"]), r=r)


def glance(chaos, nofade):
    lanes = _lanes(chaos)
    rows = []

    def add(anchor, name, events, split, hold, z, status):
        rows.append(f'<tr><td><a href="#{anchor}"><b>{esc(name)}</b></a></td><td class="num">{events}</td><td class="num">{_pct(split)}</td>'
                    f'<td class="num">{_pct(hold)}</td><td class="num">{_z(z)}</td><td>{esc(status)}</td></tr>')
    if YES_ID in lanes:
        x = _chaos_row(lanes[YES_ID])
        add("wm-yes", "Win margin · YES split (live)", x["events"], x["split"], x["hold"], x["z"], x["status"])
    g = N.game_rows(nofade["entries"], N.vkey(N.HEAD), False)
    s = C.stats(g)
    add("wm-no", "Win margin · NO fade (live)", s["n"], s["roi"], None, s["z"], NB.status(s["n"]))
    return ('<section id="glance"><h2>NBA at a glance</h2>'
            '<p class="shell-kicker">Every active lane · Sandbox, paper only · ROI after fees · NO fade sells back at its pregame price, so it has no hold row</p>'
            '<div class="tbl"><table class="nba-glance"><tr><th>Lane</th><th class="num">Settled events</th><th class="num">Split ROI</th>'
            '<th class="num">Hold ROI</th><th class="num">z (by night)</th><th>Status</th></tr>' + "".join(rows) + "</table></div>"
            + how_read() + "</section>")


def _record(L):
    x = _chaos_row(L)
    r = x["r"]
    return ('<div class="tbl"><table class="chaos-split"><tr><th>Record</th><th class="num">Settled events</th><th class="num">Entries</th>'
            '<th class="num">Won</th><th class="num">Legs filled 2x / 3x</th><th class="num">Split ROI</th><th class="num">Hold ROI</th>'
            '<th class="num">z (by night)</th><th>Status</th></tr>'
            f'<tr><td><b>Split 2x / 3x v the same entries held</b></td><td class="num">{r["events"]}</td><td class="num">{r["entries"]}</td>'
            f'<td class="num">{r["won"]}</td><td class="num">{r["filled_2x"]} / {r["filled_3x"]}</td><td class="num">{_pct(x["split"])}</td>'
            f'<td class="num">{_pct(r["hold"])}</td><td class="num">{_z(r["z"])}</td><td>{esc(x["status"])}</td></tr></table></div>')


def _folds(L, sample=None, extra_sample=""):
    others = [k for k in (L.get("exits") or C.EXITS) if k not in (C.SPLIT, "hold")]
    out = ""
    if others or L.get("sub_bands"):
        inner = (CB.split_table(L) if L.get("sub_bands") else "") + (CB.variant_table(L, skip=(C.SPLIT,)) if others else "")
        out += (f'<details class="section-disclosure"><summary><b>Other exits / variants</b><span>{len(others)} exits'
                f'{" · the sub-band" if L.get("sub_bands") else ""}, each against its hold control</span></summary>{inner}</details>')
    if sample is not None:
        out += ('<details class="section-disclosure" id="' + esc(L["id"]) + '-insample"><summary><b>In-sample research (not evidence)</b>'
                f'<span>{esc(sample.get("since"))} to {esc(sample.get("until") or "the lane\'s first night")}, the days the rule was chosen on</span></summary>'
                '<p class="sm mut">The same rule on the days it was found on. It is NOT evidence and is never the headline.</p>'
                f'{_record(sample)}{CB.variant_table(sample, skip=(C.SPLIT,))}</details>')
    elif extra_sample:
        out += extra_sample
    return out


def lane_card(anchor, title, L, sample=None):
    bad = CB.unverified(L)[0]
    skipped = f'<p class="sm mut">Skipped as unverified ask: {bad}.</p>' if bad else ""
    folds = _folds(L, sample)
    return (f'<section id="{anchor}"><details class="section-disclosure" data-lane="{esc(L["id"])}" open><summary><b>{esc(title)}</b>'
            f'<span>{CB.split_hold(L)["events"]} settled events · fresh record since {esc(L.get("since"))}</span></summary>'
            f'<p class="sm">{esc(RULES[L["id"]])}{(" " + esc(L["caution"])) if L.get("caution") else ""}</p>'
            f'{CB.voided_line(L)}{_record(L)}{CB.basis_line(L)}{skipped}{folds}'
            f'<details class="section-disclosure"><summary><b>Trades</b><span>latest 30 entries · split, T target, S stop, H held to settlement</span></summary>{CB.trade_list(L)}</details>'
            '</details></section>')


def nofade_card(chaos, nofade):
    head = N.vkey(N.HEAD)
    c = N.counts(nofade["entries"], False)
    i = N.counts(nofade["entries"], True)
    g = N.game_rows(nofade["entries"], head, False)
    last = nofade.get("last_run")
    insample = ('<details class="section-disclosure" id="nofade-insample"><summary><b>In-sample research (not evidence)</b>'
                f'<span>{esc(N.SINCE_IN)} to {esc(N.SINCE)}, the days the rule was chosen on</span></summary>'
                f'<p class="sm mut">The same rule on Oct 20-30. {i["games"]} games read, {i["unverified"]} of {i["unverified"] + i["verified"]} buckets skipped as unverified ask. '
                f'NOT evidence, never the headline.</p>{NB.variant_rows(nofade, True)}</details>')
    return (f'<section id="wm-no"><details class="section-disclosure" data-lane="{N.LANE}" open><summary><b>Win margin · NO fade</b>'
            f'<span>{len(g)} settled events · fresh record since {esc(N.SINCE)}</span></summary>'
            f'<p class="sm">{esc(RULES[NO_ID])}</p>'
            f'{NB.variant_rows(nofade, False, dips=(N.HEAD,))}'
            f'<p class="sm mut">Skipped as unverified ask: {c["unverified"]} of {c["unverified"] + c["verified"]} buckets.</p>'
            f'<p class="sm"><b>Next to the YES split</b></p>{NB.side_by_side(nofade, chaos)}'
            f'<details class="section-disclosure"><summary><b>Other exits / variants</b><span>85% and 65% of pregame</span></summary>'
            f'{NB.variant_rows(nofade, False, dips=tuple(d for d in N.DIPS if d != N.HEAD))}</details>'
            f'{insample}'
            f'<details class="section-disclosure"><summary><b>Trades</b><span>latest 30 games with a fill · the headline row</span></summary>{NB.trade_list(nofade)}</details>'
            f'<p class="sm mut">Last read {esc(last or "not yet")}{(" · " + esc(nofade["error"])) if nofade.get("error") else ""}.</p>'
            '</details></section>')


def cheap_side(chaos=None, nofade=None):
    """The active lane cards, in order, inside the section the Sandbox index links to (#cheap-side)."""
    chaos = chaos if chaos is not None else (C.load() if os.path.exists(C.PATH) else C.empty())
    nofade = nofade if nofade is not None else N.load()
    lanes = _lanes(chaos)
    cards = ""
    if YES_ID in lanes:
        cards += lane_card("wm-yes", "Win margin · YES split", lanes[YES_ID], lanes.get(SAMPLE_ID))
    cards += nofade_card(chaos, nofade)
    return f'<section id="cheap-side"><h2>Active lanes</h2><p class="shell-kicker">One card each · the rule, the live record, then folds</p>{cards}</section>'


def baselines(chaos=None):
    """The blind moneyline underdog population, replayed every night as the bar a filtered underdog lane must beat."""
    chaos = chaos if chaos is not None else (C.load() if os.path.exists(C.PATH) else C.empty())
    L = _lanes(chaos).get(ML_ID)
    if not L or not L.get("baseline"):
        return ""
    return ('<section id="ml-dog"><h2>Baselines</h2><p class="shell-kicker">Blind, price band only · not a lane · '
            'a filtered lane must beat it</p>' + CB.baseline_block(L) + '</section>')


def build(chaos=None, nofade=None, tracker=None):
    chaos = chaos if chaos is not None else (C.load() if os.path.exists(C.PATH) else C.empty())
    nofade = nofade if nofade is not None else N.load()
    return glance(chaos, nofade) + cheap_side(chaos, nofade) + baselines(chaos) + WB.section(tracker)


def place(html, chaos=None, nofade=None, tracker=None):
    """Insert the glance, the lane cards and the tracker before Upcoming. Never breaks the page."""
    try:
        import sandbox_build
        sec = sandbox_build.label_cells(build(chaos, nofade, tracker))
        at = html.find('<section id="matchups"')
        if at < 0:
            at = html.find("<section id=", html.find("<main"))
        return html[:at] + sec + html[at:] if at >= 0 else html
    except Exception:                                           # noqa: BLE001
        return html
