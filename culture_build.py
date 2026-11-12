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
import sys
import traceback

import culture_production as CP
import culture_track as K
import fmt
import mentions_split as MS
import site_chrome as C
import sport_page as SP

KEY = "culture"
TITLE = "Edge Machine · Culture"
DESCRIPTION = ("Kalshi culture markets on paper: the Trump mentions dip bid and the Rotten Tomatoes model; the cheap-side "
               "mention and album lanes are retired, kept with their records.")
# The cheap-side lanes, in page order (weekly mentions strict, wide; monthly strict, wide; album YES, NO).
CHEAP = (MS.STRICT, MS.WIDE, MS.MONTH, MS.MONTH_WIDE, MS.ALBUM, MS.ALBUM_NO)
LIVE_CHEAP = tuple(c for c in CHEAP if not c.get("retired"))      # none since 2026-11-11 (the album lanes retired)
GONE_CHEAP = tuple(c for c in CHEAP if c.get("retired"))
GONE_MENTIONS = tuple(c for c in GONE_CHEAP if c not in (MS.ALBUM, MS.ALBUM_NO))   # the weekly and monthly mention lanes (2026-10-31)
GONE_ALBUM = tuple(c for c in GONE_CHEAP if c in (MS.ALBUM, MS.ALBUM_NO))         # the album lanes (2026-11-11)
SECTIONS = (("lanes", "Lanes"), ("retired", "Retired"))
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
    """One row per live cheap-side lane (the album lanes)."""
    return MS.summary(LIVE_CHEAP, states, esc)


def retired_cheap(states, esc):
    """The retired weekly and monthly mention lanes as ONE line in a collapsed fold (2026-11-06, Olu), in the
    Archive's one-line style: names, retired date, final record, reason. Display only: their ledger rows stay and
    any open entry still fills and settles. The record counts valid entries only (unverified asks are left out)."""
    why = GONE_MENTIONS[0]["retired"]
    valid = [e for c in GONE_MENTIONS for e in MS.counted(states[c["lane"]])]
    open_n = sum(not MS.done(e) for c in GONE_MENTIONS for e in states[c["lane"]].get("entries") or [])
    since = min(c["registered"] for c in GONE_MENTIONS)
    if valid:
        r = MS.record(valid)
        rec = (f"{r['entries']} valid entr{'y' if r['entries'] == 1 else 'ies'} since {since}, {r['won']} won, "
               f"split ROI {MS._headline(r['roi'], r)}, hold ROI {MS._headline(r['roi_held'], r)} after fees")
    else:
        rec = f"0 valid entries since {since}"
    names = ", ".join(c["label"].replace("mentions · ", "").replace(" (", " ").rstrip(")") for c in GONE_MENTIONS)
    line = (f"retired {why['on']}; final record {rec}"
            + (f"; {open_n} open entr{'y' if open_n == 1 else 'ies'} still settling" if open_n else "")
            + "; books too thin to pass the spread + ask check")
    return (f'<details class="fold sec" id="retired-cheap"><summary><h3>Mention lanes</h3> <span class="mut sm">· '
            f'{len(GONE_MENTIONS)} cheap-side mention lanes · retired {esc(why["on"])} · kept, not deleted</span></summary>'
            f'<ul class="sm"><li><b>Cheap-side mention lanes</b> ({esc(names)}): {esc(line)}.</li></ul></details>')


def retired_album(states, esc):
    """The retired album lanes (2026-11-11, Olu), one line each with the final record; each lane's entries only when its
    fold is opened. Display only: the ledger rows stay and open entries still fill and settle."""
    if not GONE_ALBUM:
        return ""
    items = []
    for cfg in GONE_ALBUM:
        st = states[cfg["lane"]]
        g = cfg["retired"]
        open_n = sum(not MS.done(x) for x in st.get("entries") or [])
        line = (f"retired {g['on']}; final record {g['at']}"
                + (f"; {open_n} open entr{'y' if open_n == 1 else 'ies'} still settling" if open_n else "") + f"; {g['reason']}")
        items.append(f'<li data-lane="{esc(cfg["lane"])}"><b>{esc(cfg["label"])}</b>: {esc(line)}.'
                     + _fold("Entries", "", MS.section(st, esc, cfg), cfg["anchor"] + "-retired-fold") + '</li>')
    return (f'<details class="fold sec" id="retired-album"><summary><h3>Album lanes</h3> <span class="mut sm">· '
            f'{len(GONE_ALBUM)} cheap-side album lanes · retired {esc(GONE_ALBUM[0]["retired"]["on"])} · kept, not deleted</span></summary>'
            f'<ul class="sm">{"".join(items)}</ul></details>')


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
            if K.retired(key, now):
                g = K.RETIRED[key]
                line = (f"retired {g['on']} at {g['at']}: {g['reason']}; no new entries, the {open_n} open pick"
                        f"{'s' if open_n != 1 else ''} still settle and are graded; record {rec} (before the "
                        f"amendment {_rec(pre)}; from it {_rec(post)})")
        elif K.retired(key, now):
            g = K.RETIRED[key]
            line = (f"retired {g['on']} at {g['at']}; record now {rec}; {open_n} open still settling" if open_n
                    else f"retired {g['on']} at {g['at']}; final record {rec}")
        else:
            line = f"record {rec}; {open_n} open"
        out.append(f'<li><b>{esc(K.LANES[key])}</b> ({esc(key)}): {esc(line)}.</li>')
    return (f'<details class="fold sec" id="archive"><summary><h3>Older lanes</h3> <span class="mut sm">· '
            f'{len(ARCHIVE)} old lanes · kept, not deleted</span></summary>'
            '<p class="sm mut">The lanes the Culture page led with before the cheap-side standard. Their ledger rows stay '
            'and their open picks still settle.</p>'
            f'<ul class="sm">{"".join(out)}</ul></details>')


label_cells = MS.label_cells   # phone labels for tables with a <thead> (moved to mentions_split)


def _dip_hold(dip_state, e):
    """The mentions_dip_hold card (2026-11-01). Never breaks the page, but never vanishes silently either
    (2026-11-04): a failure is printed to the build log with its traceback, and the page keeps the section, so
    the Dip bid link still lands, with a one-line note."""
    try:
        import mentions_dip_hold as DH
        import mentions_dip_hold_build as DB
        return DB.section(dip_state if dip_state is not None else DH.load(), e)
    except Exception:                                           # noqa: BLE001
        print("culture_build: the Dip bid card failed to build:", file=sys.stderr)
        traceback.print_exc()
        return ('<section id="dip-hold"><h2>Dip bid</h2><p class="sm mut">This card could not be built on this run; '
                'its ledger is unchanged and the next run tries again.</p></section>')


def _fold(title, hint, inner, ident=None):
    return (f'<details class="fold sm"{f" id={chr(34)}{ident}{chr(34)}" if ident else ""}><summary><b>{title}</b>'
            f'{f" <span class={chr(34)}mut{chr(34)}>{hint}</span>" if hint else ""}</summary>{inner}</details>')


def _a(n, won, roi):
    """A row's record in the page template's shape: n settled events, won of them up, ROI after fees (None: pending)."""
    return dict(n=n, won=won, n_price=0, expected=None, roi_fee=roi, z=0.0, z_known=False, unit="event")


def _row(name, label, anchor, a, floor, market, **extra):
    return dict(name=name, sport="culture", meta=dict(label=label, kind="Rule"), a=a, prod=False, open=extra.pop("open", 0), since=None, v="early",
                anchor=anchor, label=label, market=market, floor=floor, **extra)


def _pct1(x):
    return "—" if x is None else f"{x * 100:+.1f}%".replace("-", "−")


def lane_rows(states, state, now, dip_state, e):
    """(rows, details): one row per live lane, in page order, and each row's closed details. The header tiles read these rows."""
    rows, details = [], {}
    try:
        import mentions_dip_hold as DH
        import mentions_dip_hold_build as DB
        ds = dip_state if dip_state is not None else DH.load()
        h, c = DH.record(ds, DH.HEAD), DH.record(ds, 0.15)
        rows.append(_row("mentions_dip_hold", "Trump mentions · 10c dip bid, hold", "dip-hold-row",
                         _a(h["settled_events"], h["up"], h["roi"] if h["settled_events"] else None), 10, "Trump mentions",
                         open=h["open"], comparison=f'15c bid {_pct1(c["roi"]) if c["settled_events"] else "pending"}',
                         entries=h["entries"]))
        details["mentions_dip_hold"] = DB.body(ds, e)
    except Exception:                                           # noqa: BLE001
        print("culture_build: the Dip bid card failed to build:", file=sys.stderr)
        traceback.print_exc()
        rows.append(_row("mentions_dip_hold", "Trump mentions · 10c dip bid, hold", "dip-hold-row", _a(0, 0, None), 10, "Trump mentions", comparison="could not be built", entries=0))
        details["mentions_dip_hold"] = ('<p class="sm mut">This lane could not be built on this run; its ledger is unchanged and the next run tries again.</p>')
    for cfg in LIVE_CHEAP:
        st = states[cfg["lane"]]
        es = MS.counted(st)
        r, w = MS.record(es), MS.week_record(es)
        hold = cfg.get("headline") == "hold"
        roi = r["roi_held"] if hold else r["roi"]
        done = r["settled_events"]
        rows.append(_row(cfg["lane"], cfg["label"], cfg["anchor"] + "-row", _a(done, w["positive"], roi if done else None), MS.REVIEW_AT, "Album" if "Album" in cfg["label"] else "Mentions",
                         open=r["entries"] - r["settled"],
                         comparison=("split " if hold else "held ") + (_pct1(r["roi"] if hold else r["roi_held"]) if done else "pending"), entries=r["entries"]))
        note = ('<p class="sm"><b>Album ladders tested too confident: both tails won more than priced.</b></p>' if cfg in (MS.ALBUM, MS.ALBUM_NO) else "")
        details[cfg["lane"]] = note + _fold("Entries, rule and checks", "", MS.section(st, e, cfg), cfg["anchor"] + "-fold")
    try:
        lane = state["lanes"]["rt_model"]
        if K.revived("rt_model", now):
            new, old, _o = history_split("rt_model", lane["picks"])
            fresh_open = sum(x["status"] == "open" for x in K.fresh("rt_model", lane["picks"]))
            rows.append(_row("rt_model", K.LANES["rt_model"], "rt-model-row", _a(new[1], new[0], new[2]), MS.REVIEW_AT, "Rotten Tomatoes", open=fresh_open,
                             comparison=f"before revival {_pct1(old[2])}", entries=new[1] + fresh_open))
        else:
            rows.append(_row("rt_model", K.LANES["rt_model"], "rt-model-row", _a(0, 0, None), MS.REVIEW_AT, "Rotten Tomatoes", comparison="retired, revived later", entries=0))
        details["rt_model"] = _fold("Record, rule and last scan", "", model_lanes(state, now, e), "rt-model-card")
    except Exception:                                           # noqa: BLE001
        print("culture_build: the model lane row failed to build:", file=sys.stderr)
        traceback.print_exc()
    return rows, details


def tiles(rows):
    """The header tiles, summed from the lane rows so they cannot disagree with them."""
    open_n = sum(r["open"] for r in rows)
    entries = sum(r.get("entries", 0) for r in rows)
    done = sum(r["a"]["n"] for r in rows)
    return ('<div class="tiles sp-tiles">'
            f'<div class="tile"><b>{len(rows)}</b><span>active lanes</span></div>'
            f'<div class="tile"><b>{entries}</b><span>entries</span></div>'
            f'<div class="tile"><b>{open_n}</b><span>open</span></div>'
            f'<div class="tile"><b>{done}</b><span>settled events</span></div></div>')


def lanes_section(rows, details):
    """The Lanes list: one closed row per lane (name, market, record, result, comparison, stage), details inside."""
    sp = SP.spec(family="Culture", key="culture", title=TITLE, scoped=False, rule_name=lambda r: r["label"], market=lambda d, r: r.get("market") or "",
                 definition=lambda d, r: details.get(r["name"], ""), recent=None, record_head="Record (events)",
                 extra_cols=(("record", "Entries", lambda r: str(r.get("entries", 0))), ("roi", "Comparison", lambda r: e_(r.get("comparison") or "—"))))
    body_ = "".join(SP.rule_row(sp, {}, r, None, False) for r in rows)
    return (f'<section id="lanes" class="sp-section"><div class="sp-section-head"><h2>Lanes</h2><span class="sm mut">{len(rows)} active · '
            f'review at 10 events, decide at 30</span></div>'
            f'<div class="sp-rules-list" data-list="sandbox">{SP.list_head(False, "Lane", sp)}{body_}</div></section>')


e_ = C.esc


def build(state=None, now=None, split_state=None, wide_state=None, month_state=None, month_wide_state=None,
          album_state=None, album_no_state=None, dip_state=None):
    state = state if state is not None else K.load()
    now = SP.as_utc(now)
    e = C.esc
    given = {MS.STRICT["lane"]: split_state, MS.WIDE["lane"]: wide_state, MS.MONTH["lane"]: month_state,
             MS.MONTH_WIDE["lane"]: month_wide_state, MS.ALBUM["lane"]: album_state, MS.ALBUM_NO["lane"]: album_no_state}
    states = {cfg["lane"]: given[cfg["lane"]] if given[cfg["lane"]] is not None else MS.load(cfg=cfg) for cfg in CHEAP}
    rows, details = lane_rows(states, state, now, dip_state, e)
    gone = (f'<section id="retired" class="sp-section"><details class="fold sec" id="retired-all"><summary><h2>Retired</h2> <span class="mut sm">'
            f'· {len(GONE_MENTIONS)} mention lanes, {len(GONE_ALBUM)} album lanes, {len(ARCHIVE)} older lanes · kept, not deleted</span></summary>'
            f'{retired_cheap(states, e)}{retired_album(states, e)}{archive(state, now, e)}</details></section>')
    body = ('<section id="standard"><h1>Culture</h1>'
            '<p class="lede">Kalshi culture markets, paper only.</p>'
            + _fold("How it works", "", '<ul class="sm"><li>Each lane enters at the real price and is judged after Kalshi\'s fees.</li>'
                    '<li>A fill counts only on a traded print.</li><li>Each row\'s rule sits in its fold.</li></ul>'
                    '<p class="sm mut">Each lane starts a fresh record at its first entry: review at 10 settled events, decide at 30. '
                    'An event is one outcome: the words of one mention market move together, so they count once.</p>')
            + tiles(rows) + '</section>'
            + lanes_section(rows, details)
            + gone
            + _fold("Method", "where the data comes from", '<p class="sm mut">Read hourly by GitHub Actions (culture.yml) from Kalshi public market data and '
                    'candles, Rotten Tomatoes and Roll Call Factbase. Paper entries at the ask with Kalshi\'s fees.</p>'))
    html = C.document(TITLE, DESCRIPTION, KEY, SECTIONS, C.stamp(now), body,
                      script_src="./site.js", scripts=("./tables.js",))
    return label_cells(html)


def main():
    with open(os.path.join(K.ROOT, "public_site", "culture.html"), "w") as f:
        f.write(build())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
