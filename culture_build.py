"""The Culture tab, redone 2026-10-27 (Olu): "the cheap strategy is the new standard".

Top to bottom:
  1. the standard, in a few lines: cheap side + resting take-profit
  2. one summary table, a row per cheap-side lane (CHEAP, in order)
  3. the lane cards in the same order, all with the same tiles, per-event rows and trade list
  4. Model lanes: rt_model (revived 2026-10-26 on a fresh record), compact
  5. Archive (collapsed): the old lanes, one line each -- mentions_rate (out of Production
     2026-10-26, still logging on paper under its 2026-10-26 amendment), culture_endgame and
     culture_fav_band (retired 2026-10-24). Nothing is deleted: every ledger row stays and every
     open pick still settles; the page only stops leading with them.

Paper only. The ledgers are written by culture_track.py, culture_production.py and mentions_split.py
(culture.yml, hourly); this page reads them.
"""
import os

import culture_production as CP
import culture_track as K
import fmt
import mentions_split as MS
import site_chrome as C
import sport_page as SP

KEY = "culture"
TITLE = "Edge Machine · Culture"
DESCRIPTION = ("Kalshi culture markets on paper: cheap side + resting take-profit on Trump mentions and album "
               "sales, beside the same entries held.")
# The cheap-side lanes, in page order (weekly mentions strict, wide; monthly strict, wide; album YES, NO).
CHEAP = (MS.STRICT, MS.WIDE, MS.MONTH, MS.MONTH_WIDE, MS.ALBUM, MS.ALBUM_NO)
SECTIONS = (("standard", "Standard"), ("lanes", "Lanes"), ("models", "Model lanes"), ("archive", "Archive"))
# The old lanes, shown in the Archive only (2026-10-27).
ARCHIVE = ("mentions_rate", "culture_endgame", "culture_fav_band")


def per_contract(picks):
    """(won, settled won-or-lost, ROI after fees per contract pooled by cost, or None): the way
    the retirement records were read (2026-10-24)."""
    done = [r for r in picks if r["status"] != "open" and r.get("payout") is not None]
    binary = [r for r in done if r["status"] in ("won", "lost")]
    cost = sum(r["price"] + K.fee(r["price"]) for r in done)
    roi = sum(r["payout"] for r in done) / cost - 1 if cost else None
    return sum(r["status"] == "won" for r in binary), len(binary), roi


def amendment_split(picks):
    """The 2026-10-26 amendment's before/after records (per contract, after fees): an entry logged
    under it carries amended="2026-10-26" (culture_track.AMENDED_2)."""
    before = [r for r in picks if r.get("amended") != K.AMENDED_2]
    after = [r for r in picks if r.get("amended") == K.AMENDED_2]
    return per_contract(before), per_contract(after), sum(r["status"] == "open" for r in before)


def revival_note(key):
    """The revived lane's short note (2026-10-26): its day, a fresh record, and when it is read again."""
    r = K.REVIVED[key]
    return f"revived {r['on']} · fresh record · review at {r['review']}"


def history_split(key, picks):
    """A revived lane: (its fresh record, its pre-retirement history, history still open)."""
    fresh = K.fresh(key, picks)
    ids = {id(r) for r in fresh}
    old = [r for r in picks if id(r) not in ids]
    return per_contract(fresh), per_contract(old), sum(r["status"] == "open" for r in old)


def _rec(r):
    won, n, roi = r
    return (f"{won}/{n} won, {roi * 100:+.1f}% after fees per contract".replace("-", "−")
            if n and roi is not None else "nothing settled yet")


status = MS.status          # the review rule's status line (moved to mentions_split, 2026-10-27)


def summary(states, esc):
    """One row per cheap-side lane, and the strict v wide spread line for the mention lanes."""
    return MS.summary(CHEAP, states, esc, pairs=((MS.STRICT, MS.WIDE, "Weekly mentions"),
                                                  (MS.MONTH, MS.MONTH_WIDE, "Monthly mentions")))


def model_lanes(state, now, esc):
    """rt_model, compact: its fresh record, its pre-retirement history, its last scan."""
    key = "rt_model"
    lane = state["lanes"][key]
    reasons = (lane.get("observations") or {}).get("reasons") or {}
    scan = "; ".join(f"{k}: {v}" for k, v in sorted(reasons.items(), key=lambda x: -x[1]))
    last = lane.get("last_success")
    if K.revived(key, now):
        new, old, old_open = history_split(key, lane["picks"])
        fresh_open = sum(r["status"] == "open" for r in K.fresh(key, lane["picks"]))
        g = K.RETIRED.get(key) or {}
        line = (f'<b>{esc(K.LANES[key])}</b> · {esc(revival_note(key))}. Revived record: {esc(_rec(new))}, '
                f'{fresh_open} open. Pre-retirement history (retired {esc(g.get("on", ""))} at {esc(g.get("at", ""))}, '
                f'not counted): {esc(_rec(old))}{f", {old_open} still open" if old_open else ""}.')
    else:
        line = (f'<b>{esc(K.LANES[key])}</b> · retired {esc(K.RETIRED[key]["on"])}; revived from '
                f'{esc(K.REVIVED[key]["at"][:16].replace("T", " "))}Z.')
    return (f'<p class="sm">{line}</p><p class="sm mut">{esc(K.RULES[key])}</p>'
            f'<p class="sm mut">Last scan {esc(fmt.when(last) if last else "not yet")}'
            + (f' · {esc(scan)}' if scan else "") + (f' · {esc(lane["error"])}' if lane.get("error") else "") + '.</p>')


def archive(state, now, esc):
    """The old lanes, one line each. Every row stays on the ledger; open picks still settle."""
    out = []
    for key in ARCHIVE:
        picks = state["lanes"][key]["picks"]
        open_n = sum(r["status"] == "open" for r in picks)
        rec = _rec(per_contract(picks))
        if key == CP.SOURCE:
            pre, post, _ = amendment_split(picks)
            where = (f"in Production {CP.MOVED_ON} to {CP.DEMOTED_ON}, still logging on paper in the Sandbox under its "
                     f"{K.AMENDED_2} amendment" if not CP.listed(now) else f"in Production since {CP.MOVED_ON}")
            line = f"{where}; record {rec} (before the amendment {_rec(pre)}; from it {_rec(post)}); {open_n} open"
        elif K.retired(key, now):
            g = K.RETIRED[key]
            line = (f"retired {g['on']} at {g['at']}; record now {rec}; {open_n} open still settling" if open_n
                    else f"retired {g['on']} at {g['at']}; final record {rec}")
        else:
            line = f"record {rec}; {open_n} open"
        out.append(f'<li><b>{esc(K.LANES[key])}</b> ({esc(key)}): {esc(line)}.</li>')
    return (f'<details class="fold sec" id="archive"><summary><h2>Archive</h2> <span class="mut sm">· '
            f'{len(ARCHIVE)} old lanes · kept, not deleted</span></summary>'
            '<p class="sm mut">The lanes the Culture page led with before the cheap-side standard. Their ledger rows stay '
            'and their open picks still settle.</p>'
            f'<ul class="sm">{"".join(out)}</ul></details>')


label_cells = MS.label_cells   # phone labels for tables with a <thead> (moved to mentions_split)


def build(state=None, now=None, split_state=None, wide_state=None, month_state=None, month_wide_state=None,
          album_state=None, album_no_state=None):
    state = state if state is not None else K.load()
    now = SP.as_utc(now)
    e = C.esc
    given = {MS.STRICT["lane"]: split_state, MS.WIDE["lane"]: wide_state, MS.MONTH["lane"]: month_state,
             MS.MONTH_WIDE["lane"]: month_wide_state, MS.ALBUM["lane"]: album_state, MS.ALBUM_NO["lane"]: album_no_state}
    states = {cfg["lane"]: given[cfg["lane"]] if given[cfg["lane"]] is not None else MS.load(cfg=cfg) for cfg in CHEAP}
    S = lambda cfg: states[cfg["lane"]]
    standard = (
        '<section id="standard"><h1>Culture</h1>'
        '<p class="lede"><b>Cheap side + resting take-profit.</b></p>'
        '<ul class="sm">'
        '<li>Buy cheap contracts at the event\'s open, at the real ask.</li>'
        '<li>Rest a split sell: half at 2x, half at 3x.</li>'
        '<li>A fill counts only on a traded print.</li>'
        '<li>Every lane is shown next to the same entries held.</li></ul>'
        '<p class="sm mut">Sandbox, paper only, each lane on a fresh record from its first entry: review at 10 settled '
        'events, decide at 30. An event is one outcome: the words of one mention market, or the rungs of one '
        'album ladder, move together, so they count once.</p></section>')
    cards = (MS.section(S(MS.STRICT), e) + MS.compare(S(MS.STRICT), S(MS.WIDE), e) + MS.section(S(MS.WIDE), e, MS.WIDE)
             + MS.section(S(MS.MONTH), e, MS.MONTH)
             + MS.compare(S(MS.MONTH), S(MS.MONTH_WIDE), e, anchor=MS.MONTH["compare_id"], title="Monthly · strict v wide")
             + MS.section(S(MS.MONTH_WIDE), e, MS.MONTH_WIDE)
             + '<p class="sm" id="album-note"><b>Album ladders tested too confident: both tails won more than priced.</b></p>'
             + MS.section(S(MS.ALBUM), e, MS.ALBUM) + MS.section(S(MS.ALBUM_NO), e, MS.ALBUM_NO))
    body = (standard
            + f'<section id="lanes"><h2>Cheap-side lanes</h2>{summary(states, e)}{cards}</section>'
            + f'<section id="models"><h2>Model lanes</h2>{model_lanes(state, now, e)}</section>'
            + archive(state, now, e)
            + '<p class="sm mut">Read hourly by GitHub Actions (culture.yml) from Kalshi public market data and '
              'candles, Rotten Tomatoes and Roll Call Factbase. Paper entries at the ask with Kalshi\'s fees.</p>')
    html = C.document(TITLE, DESCRIPTION, KEY, SECTIONS, C.stamp(now), body,
                      script_src="./site.js", scripts=("./tables.js",))
    return label_cells(html)


def main():
    with open(os.path.join(K.ROOT, "public_site", "culture.html"), "w") as f:
        f.write(build())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
