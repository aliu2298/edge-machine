"""The NBA page's top half (2026-10-31, Olu: "clumsy"): an "NBA at a glance" table, then one card per ACTIVE lane in one
layout (the rule in a sentence, the live record, folds for other exits, in-sample research and trades), then the win
margin tracker. Presentation only: every figure is read from the same ledgers as before; no rule, record or ledger
changes. Header-row tables, so sandbox_build.label_cells names each cell for the phone cards. No inline style or SVG
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
import nba_wm_v3 as V3

YES_ID, NO_ID = "nba_winmargin_live", "nba_wm_nofade"
V1_ID = "nba_winmargin_split"      # paper version 1 (folded 2026-11-02): its record stays
SAMPLE_ID = "nba_winmargin_split_insample"
# The moneyline underdog (nba_ml_dog_tp50) was demoted to a blind baseline and retired on 2026-11-01: it sits in the
# page's Retired fold (nba_pace_build), not here.

RULES = {
    YES_ID: "Production: traded live. Buy YES on a 1-5 or 6-10 win margin bucket (either team) at the ask, 10-20c, an hour before the tip; "
            "rest a sell for half at 2x and half at 3x, filled only by prints strictly through the target from the tip on; the rest is held.",
    NO_ID: "Production: traded live. After the tip, rest a post-only NO bid at 75% of a bucket's pregame NO price (10-95c) and sell it back "
           "at the pregame price on a print strictly above it, else hold; a bucket already at or under the bid at the tip is no entry.",
}


def esc(x):
    return _h.escape(str(x))


def _pct(v):
    return "—" if v is None else f"{v * 100:+.1f}%"


def _z(v):
    return "—" if v is None else f"{v:+.2f}"


def _lanes(chaos):
    """The ledger's lanes with the config applied; the live YES lane, before its first replay writes it, as an empty fresh record."""
    lanes = dict(CB.with_config(chaos).get("lanes") or {})
    if YES_ID not in lanes:
        try:
            import chaos_lanes
            import datetime as _dt
            cfg = next(x for x in chaos_lanes.LANES if x["id"] == YES_ID)
            lanes[YES_ID] = C.lane_state(dict(lanes={}), cfg, _dt.datetime.now(C.UTC))
        except Exception:                                       # noqa: BLE001
            pass
    return lanes


def how_read():
    return ('<details class="section-disclosure" id="how-read"><summary><b>How these lanes are read</b><span>one place for the rules that apply to every card</span></summary>'
            '<ul class="sm"><li>Both lanes are in Production: traded live. The record on this page is paper that mirrors what the live orders can do, replayed from Kalshi\'s trade prints and 1-minute candles.</li>'
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


def _v3_block(title, rows, since, ident):
    """Version 3's record (the executor's own decision snapshots as the entries): the headline once it has started."""
    s = C.stats(rows)
    events = len({r["event"] for r in rows})
    return (f'<div class="v3-block" id="{ident}"><p class="sm"><b>{esc(title)}</b> · from {esc(since)}: the entries are the executor\'s own T-1h decisions, the fills replayed from prints</p>'
            '<div class="tbl"><table><tr><th>Record</th><th class="num">Settled events</th><th class="num">Entries</th><th class="num">Won</th>'
            '<th class="num">ROI after fees</th><th class="num">z (by night)</th><th>Status</th></tr>'
            f'<tr><td><b>{esc(title)}</b></td><td class="num">{events}</td><td class="num">{s["n"]}</td><td class="num">{s["won"]}</td><td class="num">{_pct(s["roi"])}</td>'
            f'<td class="num">{_z(s["z"])}</td><td>{esc(MS.status(events))}</td></tr></table></div></div>')


def glance(chaos, nofade, v3=None):
    lanes = _lanes(chaos)
    rows = []
    since = (v3 or {}).get("since")

    def add(anchor, name, events, split, hold, z, status):
        rows.append(f'<tr><td><a href="#{anchor}"><b>{esc(name)}</b></a></td><td class="num">{events}</td><td class="num">{_pct(split)}</td>'
                    f'<td class="num">{_pct(hold)}</td><td class="num">{_z(z)}</td><td>{esc(status)}</td></tr>')
    if since:
        yr = V3.yes_rows(v3)
        ys = C.stats(yr)
        add("wm-yes", "Win margin · YES split (Production, v3)", len({r["event"] for r in yr}), ys["roi"], (sum(r["hold_roi"] for r in yr) / len(yr)) if yr else None, ys["z"],
            MS.status(len({r["event"] for r in yr})))
        g = V3.no_games(v3)
        s = C.stats(g)
        add("wm-no", "Win margin · NO fade (Production, v3)", s["n"], s["roi"], None, s["z"], NB.status(s["n"]))
    else:
        if YES_ID in lanes:
            x = _chaos_row(lanes[YES_ID])
            add("wm-yes", "Win margin · YES split (Production)", x["events"], x["split"], x["hold"], x["z"], x["status"])
        g = N.game_rows(nofade["entries"], N.vkey(N.HEAD), None, "v2")
        s = C.stats(g)
        add("wm-no", "Win margin · NO fade (Production)", s["n"], s["roi"], None, s["z"], NB.status(s["n"]))
    return ('<section id="glance"><h2>NBA at a glance</h2>'
            '<p class="shell-kicker">Every active lane · Production · the paper record live orders can match · ROI after fees · NO fade sells back at its pregame price, so it has no hold row</p>'
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


def _head_record(L, v3):
    """The YES card's record: version 3 as the headline once it has started, version 2 then as its own labelled fold; else the lane's record."""
    since = (v3 or {}).get("since")
    if not since:
        return f"{CB.voided_line(L)}{_record(L)}"
    return (_v3_block("Version 3", V3.yes_rows(v3), since, "wm-yes-v3")
            + f'<details class="section-disclosure" id="wm-yes-v2"><summary><b>Version 2 (to the night before {esc(since)})</b><span>entries judged from prints; its record stays</span></summary>'
              f'{CB.voided_line(L)}{_record(L)}</details>')


def lane_card(anchor, title, L, sample=None, v1=None, v3=None):
    bad = CB.unverified(L)[0]
    skipped = f'<p class="sm mut">Skipped as unverified ask: {bad}.</p>' if bad else ""
    folds = _folds(L, sample)
    if v1 is not None:
        folds += ('<details class="section-disclosure" id="wm-yes-v1"><summary><b>Paper version 1 (folded)</b>'
                  f'<span>{esc(v1.get("since"))} to 2026-11-01 · sells filled on a print at the target</span></summary>'
                  '<p class="sm mut">The paper lane before it mirrored live orders (a resting sell fills only through its target). '
                  f'Its record stays as it was; it is not the Production record.</p>{_record(v1)}</details>')
    return (f'<section id="{anchor}"><details class="section-disclosure" data-lane="{esc(L["id"])}" open><summary><b>{esc(title)}</b>'
            f'<span>{CB.split_hold(L)["events"]} settled events · fresh record since {esc(L.get("since"))}</span></summary>'
            f'<p class="sm">{esc(RULES.get(L["id"], ""))}{(" " + esc(L["caution"])) if L.get("caution") else ""}</p>'
            f'{_head_record(L, v3)}{CB.basis_line(L)}{skipped}{folds}'
            f'<details class="section-disclosure"><summary><b>Trades</b><span>latest 30 entries · split, T target, S stop, H held to settlement</span></summary>{CB.trade_list(L)}</details>'
            '</details></section>')


def _nofade_record(nofade, v3, since):
    """Version 3 as the headline once it has started, version 2 then as its own labelled fold; else version 2's headline row."""
    if not since:
        return NB.variant_rows(nofade, False, dips=(N.HEAD,), phase="v2")
    return (_v3_block("Version 3", V3.no_games(v3), since, "wm-no-v3")
            + f'<details class="section-disclosure" id="wm-no-v2"><summary><b>Version 2 (to the night before {esc(since)})</b><span>entries judged from prints; its record stays</span></summary>'
              f'{NB.variant_rows(nofade, False, dips=(N.HEAD,), phase="v2")}</details>')


def nofade_card(chaos, nofade, v3=None):
    head = N.vkey(N.HEAD)
    since = (v3 or {}).get("since")
    c = N.counts(nofade["entries"], None, "v2")
    i = N.counts(nofade["entries"], True)
    g = N.game_rows(nofade["entries"], head, None, "v2")
    c1 = N.counts(nofade["entries"], None, "v1")
    last = nofade.get("last_run")
    v1 = ('<details class="section-disclosure" id="nofade-v1"><summary><b>Paper version 1 (folded)</b>'
          f'<span>{esc(N.SINCE)} to {esc(N.V2_FROM)}, fills and sells on a print at the price · {c1["games"]} games read</span></summary>'
          '<p class="sm mut">The paper lane before it mirrored live orders (a post-only bid, fills and sells strictly through the price). '
          f'Its record stays as it was; it is not the Production record.</p>{NB.variant_rows(nofade, False, dips=(N.HEAD,), phase="v1")}</details>')
    insample = ('<details class="section-disclosure" id="nofade-insample"><summary><b>In-sample research (not evidence)</b>'
                f'<span>{esc(N.SINCE_IN)} to {esc(N.SINCE)}, the days the rule was chosen on</span></summary>'
                f'<p class="sm mut">The same rule on Oct 20-30. {i["games"]} games read, {i["unverified"]} of {i["unverified"] + i["verified"]} buckets skipped as unverified ask. '
                f'NOT evidence, never the headline.</p>{NB.variant_rows(nofade, True)}</details>')
    return (f'<section id="wm-no"><details class="section-disclosure" data-lane="{N.LANE}" open><summary><b>Win margin · NO fade</b>'
            f'<span>{len(g)} settled events · fresh record since {esc(N.V2_FROM)}</span></summary>'
            f'<p class="sm">{esc(RULES[NO_ID])}</p>'
            f'{_nofade_record(nofade, v3, since)}'
            f'<p class="sm mut">Skipped as unverified ask: {c["unverified"]} of {c["unverified"] + c["verified"]} buckets.</p>'
            f'<p class="sm"><b>Next to the YES split</b></p>{NB.side_by_side(nofade, chaos)}'
            f'<details class="section-disclosure"><summary><b>Other exits / variants</b><span>85% and 65% of pregame</span></summary>'
            f'{NB.variant_rows(nofade, False, dips=tuple(d for d in N.DIPS if d != N.HEAD), phase="v2")}</details>'
            f'{insample}{v1}'
            f'<details class="section-disclosure"><summary><b>Trades</b><span>latest 30 games with a fill · the headline row</span></summary>{NB.trade_list(nofade)}</details>'
            f'<p class="sm mut">Last read {esc(last or "not yet")}{(" · " + esc(nofade["error"])) if nofade.get("error") else ""}.</p>'
            '</details></section>')


def cheap_side(chaos=None, nofade=None, v3=None):
    """The active lane cards, in order, inside the section the Sandbox index links to (#cheap-side)."""
    chaos = chaos if chaos is not None else (C.load() if os.path.exists(C.PATH) else C.empty())
    nofade = nofade if nofade is not None else N.load()
    lanes = _lanes(chaos)
    cards = ""
    if YES_ID in lanes:
        cards += lane_card("wm-yes", "Win margin · YES split", lanes[YES_ID], lanes.get(SAMPLE_ID), lanes.get(V1_ID), v3)
    cards += nofade_card(chaos, nofade, v3)
    return f'<section id="cheap-side"><h2>Active lanes</h2><p class="shell-kicker">One card each · the rule, the live record, then folds</p>{cards}</section>'


def build(chaos=None, nofade=None, tracker=None, v3=None):
    chaos = chaos if chaos is not None else (C.load() if os.path.exists(C.PATH) else C.empty())
    nofade = nofade if nofade is not None else N.load()
    v3 = v3 if v3 is not None else V3.load()
    return glance(chaos, nofade, v3) + cheap_side(chaos, nofade, v3) + WB.section(tracker)


def place(html, chaos=None, nofade=None, tracker=None, v3=None):
    """Insert the glance, the lane cards and the tracker before Upcoming. Never breaks the page."""
    try:
        import sandbox_build
        sec = sandbox_build.label_cells(build(chaos, nofade, tracker, v3))
        at = html.find('<section id="matchups"')
        if at < 0:
            at = html.find("<section id=", html.find("<main"))
        return html[:at] + sec + html[at:] if at >= 0 else html
    except Exception:                                           # noqa: BLE001
        return html
