"""The NBA page's lanes in the Econ Daily layout (2026-11-05, Olu): tiles, the stage filter, the Rules table (one row per
lane: the win margin YES split and the NO fade), an empty Sandbox fold; nba_pace_build adds Research, Games, Retired and
the method around it.

Presentation only. Every figure is read from the ledgers nba_layout already read:
  * the record is version 4 (nba_wm_v4prod, from the night of 2026-11-08), else version 3 (nba_wm_v3), the executor's own decisions with the
    fills replayed from prints; older versions sit in the Older versions fold. Two Sandbox rows are the comparison (2026-11-08): the version 3
    YES rule and the 75% NO bid on paper, fresh from the switch night.
    Counted per GAME as the page has always counted it (chaos_replay.stats over the YES entries; nba_wm_v3.no_games for
    the NO fade, a game's filled buckets one row). The Record cell is games won-lost (a game is won when its entries'
    summed profit is positive, the NO fade's own rule); "Entries won" is the entries, which is what Production counts;
  * live fills are the follower's own orders (data/live_record.json, production_live.record). The YES split sells early,
    and until its sell fills are published a held-only count would read as the lane's result, so it says so;
  * the since-Production tiles are the Production page's own record over the lanes' pairs (nba_wm_production).
A table whose ledger was last read well before the newest read on the page carries a "stale" tag with its read time.
"""
import datetime as dt
import html as _h
import os

import chaos_build as CB
import chaos_replay as C
import nba_layout as NL
import nba_wm_bucket_priority as CP
import nba_wm_nofade as N
import nba_wm_nofade_build as NB
import fmt
import mentions_split as MS
import nba_wm_v3 as V3
import nba_wm_v4 as V4
import nba_wm_v4prod as V4P
import sport_page as SP

NO_DIP = V4.NO_DIP
STALE_H = 12                 # a ledger read this long before the newest read on the page is tagged stale
YES_ID, NO_ID = NL.YES_ID, NL.NO_ID
YES3P_ID, NO75_ID = V4.RULE_V3["lane"], V4.NO75_LANE      # the Sandbox comparison lanes: the version 3 YES rule and the 75% NO bid, on paper
SWITCH_ON = V4P.SWITCH_ON
LIVE_KEY = {YES_ID: "nba_wm_yes", NO_ID: "nba_wm_nofade"}
RULE_LINES = {
    YES_ID: ("Entry: buy YES on a 1-5 or 6-10 win margin bucket (either team) at the ask, 10-20c, an hour before the tip.",
             "Exit: rest a sell for half at 2x and half at 3x, filled only by prints strictly through the target from the tip on; "
             "the rest is held to settlement. Production: traded live."),
    NO_ID: ("Entry: after the tip, rest a post-only NO bid at 75% of a bucket's pregame NO price (10-95c); a bucket already at "
            "or under the bid at the tip is no entry.",
            "Exit: sell it back at the pregame price on a print strictly above it, else hold to settlement. Production: traded live."),
}


RULE_LINES_V4 = {
    YES_ID: ("Entry: buy YES on a 1-5, 6-10 or 11-20 win margin bucket (either team) at the ask, 10-20c, an hour before the tip; "
             "skip a game whose favourite's pregame win share is 70% or more.",
             "Exit: rest half at 2x and half at 2.5x of the ask, filled only by prints strictly through the target from the tip on; "
             "the rest is held to settlement. Production: traded live, version 4 from the night of 2026-11-08."),
    NO_ID: ("Entry: after the tip, rest a post-only NO bid at 65% of a bucket's pregame NO price (10-95c); a bucket already at "
            "or under the bid at the tip is no entry.",
            "Exit: sell it back at the pregame price on a print strictly above it, else hold to settlement. "
            "Production: traded live, version 4 from the night of 2026-11-08."),
}
RULE_LINES_PAPER = {
    YES3P_ID: ("Entry: buy YES on a 1-5 or 6-10 win margin bucket (either team) at the ask, 10-20c, an hour before the tip; no matchup skip.",
               "Exit: rest half at 2x and half at 3x, filled only by prints strictly through the target from the tip on; the rest is held. "
               "Sandbox, paper: the version 3 rule, kept running from the night of 2026-11-08 to compare with Production."),
    NO75_ID: ("Entry: after the tip, rest a post-only NO bid at 75% of a bucket's pregame NO price (10-95c); a bucket already at "
              "or under the bid at the tip is no entry.",
              "Exit: sell it back at the pregame price on a print strictly above it, else hold to settlement. "
              "Sandbox, paper: the version 3 rule, kept running from the night of 2026-11-08 to compare with Production."),
}


def esc(x):
    return _h.escape("" if x is None else str(x))


def _t(raw):
    try:
        t = dt.datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return t if t.tzinfo else t.replace(tzinfo=dt.timezone.utc)


def stale_tag(last, latest):
    """A small "stale" tag when `last` (a ledger's last read) is STALE_H+ hours before `latest`, else ""."""
    a, b = _t(last), _t(latest)
    if a is None or b is None or (b - a).total_seconds() < STALE_H * 3600:
        return ""
    return (f' <span class="badge neg stale" title="This table\'s ledger was last read {esc(last)}, before the newest read on the page '
            f'({esc(latest)})">stale · last read {esc(str(last)[:16].replace("T", " "))}Z</span>')


def fold(title, hint, body, ident=None, tag=""):
    return (f'<details class="section-disclosure"{f" id={chr(34)}{esc(ident)}{chr(34)}" if ident else ""}><summary><b>{esc(title)}</b>'
            f'<span>{esc(hint)}</span>{tag}</summary>{body}</details>')


def load_all():
    chaos = C.load() if os.path.exists(C.PATH) else C.empty()
    import production_live as PL
    return chaos, N.load(), V3.load(), PL.load() or {}


def latest_read(chaos, nofade, v3, v4p=None):
    stamps = [_t(x.get("last_run")) for x in (chaos, nofade, v3, v4p) if x]
    stamps = [s for s in stamps if s]
    return max(stamps).isoformat() if stamps else None


# ------------------------------------------------------------------ the records
def games_of(rows):
    """(won, settled) games: a game's entries summed, won when that profit is positive (as nba_wm_v3.no_games counts a game)."""
    by = {}
    for r in rows:
        by[r["event"]] = by.get(r["event"], 0.0) + float(r.get("profit") or 0)
    return sum(1 for p in by.values() if p > 0), len(by)


def yes_record(chaos, v3, v4p=None):
    """(a, entries, entries_won) for the YES split: version 4, the page's headline since 2026-11-08, else version 3 (since 2026-11-04;
    empty before it)."""
    yr = V3.yes_rows(v4p) if (v4p or {}).get("since") else V3.yes_rows(v3) if (v3 or {}).get("since") else []
    s = C.stats(yr)
    gw, gn = games_of(yr)
    return dict(n=gn, won=gw, n_price=0, expected=None, roi_fee=s["roi"], z=s["z"] if s["z"] is not None else 0.0,
                z_known=s["z"] is not None, unit="game"), s["n"], s["won"]


def no_record(nofade, v3, v4p=None):
    head = v4p if (v4p or {}).get("since") else v3
    if (head or {}).get("since"):
        g = V3.no_games(head)
        rows = [r for r in head["rows"].values() if r["lane"] == V3.NO_LANE and not r.get("no_entry") and "profit" in r]
    else:
        g = N.game_rows(nofade["entries"], N.vkey(N.HEAD), None, "v2")
        rows = []
    s = C.stats(g)
    entries = sum(r.get("fills", 1) for r in g)
    won_entries = sum(1 for r in rows if r["profit"] > 0) if rows else None
    return dict(n=s["n"], won=s["won"], n_price=0, expected=None, roi_fee=s["roi"], z=s["z"] if s["z"] is not None else 0.0,
                z_known=s["z"] is not None, unit="game"), entries, won_entries


def live_orders(lane, live, pair=None, since3=None, since4=None):
    """The follower's own trades of this lane: all of them, or (with `pair`) those of the version window that pair reads."""
    import production_live as PL
    orders = ((live or {}).get("lanes") or {}).get(LIVE_KEY[lane]) or []
    if pair:
        win = PL.own_rows(live, pair, since3, since4)
        if win is not None:
            return win
    return orders


def live_cell(lane, live, pair=None, since3=None, since4=None):
    """The follower's own fills for this lane, as the Production page reads them (held to settlement). With `pair`, only the version window
    that pair reads (version 4 counts from its first slate, not the older versions' trades)."""
    import production_live as PL
    orders = live_orders(lane, live, pair, since3, since4)
    if not orders:
        return '<span class="mut">—</span>'
    if PL.current_schema(orders):
        # each entry as a trade after fees: the sells the follower logged plus the unsold remainder (2026-11-07)
        t = PL.own_summary(orders, third="2.5x" if pair and pair.startswith("nba_winmargin_v4") else "3x")
        roi = "" if t["roi"] is None else f' <small class="mut">{t["roi"] * 100:+.1f}%</small>'
        legs = f' <small class="mut">· legs 2x {t["legs2"]}, {t["third"]} {t["legs3"]}</small>' if t["split"] else ""
        open_ = f' <small class="mut">· {t["open"]} open</small>' if t["open"] else ""
        return f'{PL.wfl(t)}{roi}{legs}{open_}'
    rec = PL.record(orders)
    tail = f' <small class="mut">· {rec["open"]} open</small>' if rec["open"] else ""
    if LIVE_KEY[lane] in PL.EXITS and not rec["sold"]:
        return f'held {rec["won"]}–{rec["lost"]}, exits pending{tail}'
    roi = "" if rec["roi"] is None or LIVE_KEY[lane] in PL.EXITS else f' <small class="mut">{rec["roi"] * 100:+.1f}%</small>'
    sold = f' <small class="mut">· {rec["sold"]} exited early</small>' if rec["sold"] else ""
    return f'{rec["won"]}–{rec["lost"]}{roi}{sold}{tail}'


# ------------------------------------------------------------------ the rows
def _rec(rows):
    s = C.stats(rows)
    gw, gn = games_of(rows)
    return dict(n=gn, won=gw, n_price=0, expected=None, roi_fee=s["roi"], z=s["z"] if s["z"] is not None else 0.0,
                z_known=s["z"] is not None, unit="game"), s["n"], s["won"]


def v3paper_record(v3p):
    return _rec(V4.yes_rows(v3p or {"rows": {}}))


def no75_record(nofade):
    g = V4.no75_games(nofade)
    s = C.stats(g)
    return dict(n=s["n"], won=s["won"], n_price=0, expected=None, roi_fee=s["roi"], z=s["z"] if s["z"] is not None else 0.0,
                z_known=s["z"] is not None, unit="game"), sum(r.get("fills", 1) for r in g), None


def sandbox_rows(nofade, v3p):
    """The two Sandbox rows are the comparison (2026-11-08): the version 3 YES rule and the 75% NO bid on paper, fresh from the switch night.
    The 2026-11-06 paper lanes of version 4's rules are Production's now and are not listed twice (their ledger stays)."""
    import sandbox_build as B
    out = []
    for lane, (a, n_e, w_e), label, market, anchor in (
            (YES3P_ID, v3paper_record(v3p), "Win margin · YES v3 (paper)", "Win margin · YES", "wm-yes-v3-paper-row"),
            (NO75_ID, no75_record(nofade), "Win margin · NO fade 75% (paper)", "Win margin · NO", "wm-no-75-row")):
        out.append(dict(name=lane, sport="nba_wm", meta=dict(label=label, kind="Rule"), a=a, prod=False, open=0,
                        since=V4.SINCE_V3_PAPER, v=B.verdict(a) if a.get("z_known") or not a["n"] else "early", anchor=anchor,
                        entries=n_e, entries_won=w_e, live=None, market=market, label=label))
    return out


def rows(chaos, nofade, v3, live, v4=None, v4p=None, v3p=None):
    """`v4` is kept for callers of the 2026-11-06 signature (the Sandbox paper ledger of version 4's rules); `v4p` is Production version 4's
    ledger, `v3p` the version 3 YES paper ledger."""
    import nba_wm_production as P
    v4p = v4p if v4p is not None else V4P.load()
    v3p = v3p if v3p is not None else V4.load(None, V4.RULE_V3)
    since, since4 = (v3 or {}).get("since"), (v4p or {}).get("since")
    cur = P.current_version(v3, v4p)
    ya, yn, yw = yes_record(chaos, v3, v4p)
    na, nn, nw = no_record(nofade, v3, v4p)
    yes_lane, no_lane = {"v4": (P.YES4_LANE, P.NO4_LANE), "v3": (P.YES3_LANE, P.NO3_LANE), "v2": (P.YES_LANE, P.NO_LANE)}[cur]
    yes_pair, no_pair = f"{yes_lane}|{P.SPORT}", f"{no_lane}|{P.SPORT}"
    tag = " (v4)" if cur == "v4" else ""
    import sandbox_build as B
    out = []
    for lane, a, n_e, w_e, pair, label, market in (
            (YES_ID, ya, yn, yw, yes_pair, "Win margin · YES split" + tag, "Win margin · YES"),
            (NO_ID, na, nn, nw, no_pair, "Win margin · NO fade" + tag, "Win margin · NO")):
        out.append(dict(name=lane, sport="nba_wm", meta=dict(label=label, kind="Rule"), a=a, prod=True, pair=pair, open=0,
                        # z by night needs 3 nights (chaos_replay.MIN_NIGHTS_Z): until then the record cannot be read either way.
                        since=since4 or since, v=B.verdict(a) if a.get("z_known") or not a["n"] else "early", anchor=("wm-yes" if lane == YES_ID else "wm-no"),
                        entries=n_e, entries_won=w_e, live=live_cell(lane, live, pair, since, since4), market=market, label=label))
    return out + sandbox_rows(nofade, v3p)


def entries_cell(row):
    if not row.get("entries"):
        return '<span class="mut">—</span>'
    won = row.get("entries_won")
    return f'{won if won is not None else "—"}/{row["entries"]}'


# ------------------------------------------------------------------ the folds
def switch_note(v4p):
    """The one-paragraph note on what changed and when, in the Production folds (2026-11-08)."""
    since = (v4p or {}).get("since")
    when = f"from the night of {esc(since)}" if since else f"from the night of {esc(SWITCH_ON)} (its first entries have not settled yet)"
    return ('<p class="sm"><b>What changed.</b> Production moved to version 4 ' + when + ': the YES split also buys the 11-20 bucket, skips games whose '
            'favourite has a 70% or higher pregame win share, and sells half at 2x and half at 2.5x (was 2x and 3x); the NO fade bids at 65% of '
            'the pregame price (was 75%). The record starts fresh. Version 3 stays below under Older versions, and the version 3 YES rule and '
            'the 75% bid keep running on paper in the Sandbox, to compare.</p>')


def bucket_priority_note(v3, v4p):
    """The Bucket Priority note (nba_wm_bucket_priority), once version 4 is the record or any row has been ceded; else nothing."""
    if (v4p or {}).get("since") or any((x or {}).get("ceded") or (x or {}).get("kept") for x in (v3, v4p)):
        return CP.note_html(v3, v4p)
    return ""


def pre_switch_fold(v4, nofade, kind):
    """The Sandbox paper lanes of 2026-11-06 (the version 4 rules before they were Production): the nights before the switch, apart."""
    if kind == "yes":
        rows = [r for r in V4.yes_rows(v4 or {"rows": {}}) if r["night"] < SWITCH_ON]
        body = _block("Version 4 rule on paper", rows, V4.SINCE_YES, "wm-yes-v4-paper",
                      "the tracker's rows as the entries, fills replayed from prints; the nights before the switch")
    else:
        rows = [r for r in V4.no_games(nofade) if r["night"] < SWITCH_ON]
        body = _block("NO fade 65% on paper", rows, V4.SINCE_NO, "wm-no-65-paper", "the 65% bid replayed from prints; the nights before the switch")
    return fold("Sandbox paper before the switch", f"{V4.SINCE_YES} to the night before {SWITCH_ON}, the version 4 rule on paper", body)


def yes_panel(chaos, nofade, v3, latest, v4p=None, v4=None):
    lanes = NL._lanes(chaos)
    L = lanes.get(YES_ID)
    since = (v3 or {}).get("since")
    since4 = (v4p or {}).get("since")
    ch_tag = stale_tag(chaos.get("last_run"), latest)
    nf_tag = stale_tag(nofade.get("last_run"), latest)
    if since4:
        head = NL._v3_block("Version 4", V3.yes_rows(v4p), since4, "wm-yes-v4")
    else:
        head = (NL._v3_block("Version 3", V3.yes_rows(v3), since, "wm-yes-v3") if since else (NL._record(L) if L else ""))
    out = "".join(f'<p class="sm sp-rule-line">{esc(x)}</p>' for x in (RULE_LINES_V4 if since4 else RULE_LINES)[YES_ID]) + switch_note(v4p) + bucket_priority_note(v3, v4p) + head
    cur_rows = V3.yes_rows(v4p) if since4 else (V3.yes_rows(v3) if since else [])
    if cur_rows:
        yr = cur_rows
        hold = (sum(r["hold_roi"] for r in yr) / len(yr)) if yr else None
        hold_line = (f'<p class="sm">Version {4 if since4 else 3} · the same {len(yr)} entries held to settlement: '
                     f'{NL._pct(hold)} after fees (the split headline is {NL._pct(C.stats(yr)["roi"])}).</p>')
    else:
        hold_line = ""
    if L:
        bad = CB.unverified(L)[0]
        out += CB.basis_line(L) + (f'<p class="sm mut">Skipped as unverified ask: {bad}.</p>' if bad else "")
        others = [k for k in (L.get("exits") or C.EXITS) if k not in (C.SPLIT,)]
        out += fold("Alternate exits", "hold, sell all at 2x and the other exits, each against its hold control",
                    hold_line + (CB.variant_table(L, skip=(C.SPLIT,)) if others else ""), tag=ch_tag)
        v1 = lanes.get(NL.V1_ID)
        older = (fold(f"Version 3 (to the night before {since4})", "executor decisions, fills from prints; its record stays",
                      NL._v3_block("Version 3", V3.yes_rows(v3), since, "wm-yes-v3"), ident="wm-yes-v3-fold") if since4 else "")
        older += (fold(f"Version 2 (to the night before {since})" if since else "Version 2", "entries judged from prints; its record stays",
                       CB.voided_line(L) + NL._record(L), ident="wm-yes-v2", tag=ch_tag) if since else "")
        if v1 is not None:
            older += fold("Paper version 1 (folded)", f"{v1.get('since')} to 2026-11-01 · sells filled on a print at the target",
                          '<p class="sm mut">The paper lane before it mirrored live orders. Its record stays as it was; it is not the '
                          f'Production record.</p>{NL._record(v1)}', ident="wm-yes-v1")
        out += fold("Older versions", "version 3, version 2 and paper version 1" if since4 else "version 2 and paper version 1", older)
        out += pre_switch_fold(v4, nofade, "yes")
        sample = lanes.get(NL.SAMPLE_ID)
        if sample is not None:
            out += fold("In-sample research (not evidence)", f"{sample.get('since')} to {sample.get('until') or 'the first night'}, the days the rule was chosen on",
                        '<p class="sm mut">The same rule on the days it was found on. It is NOT evidence and is never the headline.</p>'
                        + NL._record(sample) + CB.variant_table(sample, skip=(C.SPLIT,)), ident=f"{YES_ID}-insample")
    out += fold("YES / NO overlap", "the two lanes side by side, and the games where both traded", NB.side_by_side(nofade, chaos), tag=nf_tag)
    if L:
        out += fold("Last 30 trades", "split, T target, S stop, H held to settlement", CB.trade_list(L), tag=ch_tag)
    return out


def no_panel(chaos, nofade, v3, latest, v4p=None, v4=None):
    since = (v3 or {}).get("since")
    since4 = (v4p or {}).get("since")
    nf_tag = stale_tag(nofade.get("last_run"), latest)
    c = N.counts(nofade["entries"], None, "v2")
    i = N.counts(nofade["entries"], True)
    c1 = N.counts(nofade["entries"], None, "v1")
    head = (NL._v3_block("Version 4", V3.no_games(v4p), since4, "wm-no-v4") if since4 else
            NL._v3_block("Version 3", V3.no_games(v3), since, "wm-no-v3") if since
            else NB.variant_rows(nofade, False, dips=(N.HEAD,), phase="v2"))
    out = "".join(f'<p class="sm sp-rule-line">{esc(x)}</p>' for x in (RULE_LINES_V4 if since4 else RULE_LINES)[NO_ID]) + switch_note(v4p) + bucket_priority_note(v3, v4p) + head
    out += f'<p class="sm mut">Skipped as unverified ask: {c["unverified"]} of {c["unverified"] + c["verified"]} buckets.</p>'
    out += fold("Alternate exits", f"the NO bid at 85% and {'75%' if since4 else '65%'} of pregame ({'65%' if since4 else '75%'} is the rule); it sells back at pregame, so no hold row",
                NB.variant_rows(nofade, False, dips=tuple(x for x in N.DIPS if x != (V4P.NO_DIP if since4 else N.HEAD)), phase="v2"), tag=nf_tag)
    older = (fold(f"Version 3 (to the night before {since4})", "executor decisions, fills from prints; its record stays",
                  NL._v3_block("Version 3", V3.no_games(v3), since, "wm-no-v3"), ident="wm-no-v3-fold") if since4 else "")
    older += (fold(f"Version 2 (to the night before {since})", "entries judged from prints; its record stays",
                   NB.variant_rows(nofade, False, dips=(N.HEAD,), phase="v2"), ident="wm-no-v2", tag=nf_tag) if since else "")
    older += fold("Paper version 1 (folded)", f"{N.SINCE} to {N.V2_FROM}, fills and sells on a print at the price · {c1['games']} games read",
                  '<p class="sm mut">The paper lane before it mirrored live orders. Its record stays as it was; it is not the Production record.</p>'
                  + NB.variant_rows(nofade, False, dips=(N.HEAD,), phase="v1"), ident="nofade-v1")
    out += fold("Older versions", "version 3, version 2 and paper version 1" if since4 else "version 2 and paper version 1", older)
    out += pre_switch_fold(v4, nofade, "no")
    out += fold("In-sample research (not evidence)", f"{N.SINCE_IN} to {N.SINCE}, the days the rule was chosen on",
                f'<p class="sm mut">The same rule on Oct 20-30. {i["games"]} games read, {i["unverified"]} of {i["unverified"] + i["verified"]} '
                'buckets skipped as unverified ask. NOT evidence, never the headline.</p>' + NB.variant_rows(nofade, True), ident="nofade-insample")
    out += fold("YES / NO overlap", "the two lanes side by side, and the games where both traded", NB.side_by_side(nofade, chaos), tag=nf_tag)
    out += fold("Last 30 trades", "games with a fill · the headline row", NB.trade_list(nofade), tag=nf_tag)
    last = nofade.get("last_run")
    out += f'<p class="sm mut">NO fade ledger last read {esc(last or "not yet")}{(" · " + esc(nofade["error"])) if nofade.get("error") else ""}.</p>'
    return out


def _block(title, rows, since, ident, intro):
    """A Sandbox lane's record table (the columns of the version 3 block), counted per game."""
    s = C.stats(rows)
    events = len({r["event"] for r in rows})
    return (f'<div class="v3-block" id="{ident}"><p class="sm"><b>{esc(title)}</b> · from {esc(since)}: {esc(intro)}</p>'
            '<div class="tbl"><table><tr><th>Record</th><th class="num">Settled events</th><th class="num">Entries</th><th class="num">Won</th>'
            '<th class="num">ROI after fees</th><th class="num">z (by night)</th><th>Status</th></tr>'
            f'<tr><td><b>{esc(title)}</b></td><td class="num">{events}</td><td class="num">{s["n"]}</td><td class="num">{s["won"]}</td>'
            f'<td class="num">{NL._pct(s["roi"])}</td><td class="num">{NL._z(s["z"])}</td><td>{esc(MS.status(events))}</td></tr></table></div></div>')


def _compare(rows_by_label):
    """[(label, game rows)] as a small table: games, ROI after fees, z by night, nights."""
    body = ""
    for label, g in rows_by_label:
        s = C.stats(g)
        body += (f'<tr><td><b>{esc(label)}</b></td><td class="num">{s["n"]}</td><td class="num">{NL._pct(s["roi"])}</td>'
                 f'<td class="num">{NL._z(s["z"])}</td><td class="num">{s["nights"]}</td></tr>')
    return ('<div class="tbl"><table><tr><th>Row</th><th class="num">Games</th><th class="num">ROI after fees</th>'
            f'<th class="num">z (by night)</th><th class="num">Nights</th></tr>{body}</table></div>')


def yes3p_panel(v3p):
    yr = V4.yes_rows(v3p)
    out = "".join(f'<p class="sm sp-rule-line">{esc(x)}</p>' for x in RULE_LINES_PAPER[YES3P_ID])
    out += ('<p class="sm mut">This row is the comparison: Production moved to version 4 on the night of ' + esc(SWITCH_ON) + ', and this is what the version 3 YES rule '
            'would have done since, on paper, with its own fresh record.</p>')
    out += _block("Version 3 on paper", yr, V4.SINCE_V3_PAPER, "wm-yes-v3-paper", "the tracker's rows as the entries, fills replayed from prints")
    hold = (sum(r["hold_roi"] for r in yr) / len(yr)) if yr else None
    f2, f3 = sum(1 for r in yr if r["filled_2x"]), sum(1 for r in yr if r["filled_3x"])
    out += fold("Alternate exits", "the same entries held to settlement",
                f'<p class="sm">The same {len(yr)} entries held: {NL._pct(hold)} after fees (the split headline is {NL._pct(C.stats(yr)["roi"])}). '
                f'Legs filled: 2x {f2}, 3x {f3}.</p>')
    return out


def no75_panel(nofade, latest):
    nf_tag = stale_tag(nofade.get("last_run"), latest)
    out = "".join(f'<p class="sm sp-rule-line">{esc(x)}</p>' for x in RULE_LINES_PAPER[NO75_ID])
    out += ('<p class="sm mut">This row is the comparison: Production moved to the 65% bid on the night of ' + esc(SWITCH_ON) + ', and this is the 75% bid on the '
            'same games, on paper, with its own fresh record.</p>')
    out += _block("NO fade 75%", V4.no75_games(nofade), V4.SINCE_V3_PAPER, "wm-no-75",
                  "the 75% bid replayed from prints under the follower's strict rules")
    c = N.counts([e for e in nofade["entries"] if e["night"] >= V4.SINCE_V3_PAPER and N.phase_of(e["night"]) == "v2"], None, "v2")
    out += f'<p class="sm mut">Skipped as unverified ask: {c["unverified"]} of {c["unverified"] + c["verified"]} buckets.</p>'
    out += fold("Alternate exits", "the 65% bid (the Production rule) on the same nights; it sells back at pregame, so no hold row",
                _compare([("NO fade · 75%", V4.no75_games(nofade)), ("NO fade · 65%", V4.no_games(nofade, V4P.NO_DIP, V4.SINCE_V3_PAPER))]), tag=nf_tag)
    return out


# ------------------------------------------------------------------ the tiles
def tiles(rows_, d, st, live, v3=None, v4p=None):
    """Open bets (live), active lanes, the since-Production record and ROI (the Production page's own, every pair of the
    two lanes: each version from its own first night), and the live record of the version Production is on."""
    import nba_wm_production as P
    import production
    import production_live as PL
    import sandbox_build as B
    import tennis_cards
    pseudo = [dict(name=k.split("|")[0], sport=k.split("|")[1], prod=True, pair=k) for k in P.pairs(None) | P.pairs({"since": "x"}, {"since": "x"})]
    rec, _names = SP.since_production(d, st, pseudo)
    n = int(rec.get("n") or 0)
    roi = ('<b class="mut">—</b>' if not n or rec.get("roi_fee") is None else
           f'<b class="{"mut" if n < production.EARLY_N else fmt.tone(rec["roi_fee"], ".1f", 100)}">{B.pct(rec["roi_fee"], sign=True)}</b>')
    s3, s4 = (v3 or {}).get("since"), (v4p or {}).get("since")
    cur = P.current_version(v3, v4p)
    lanes_ = {"v4": (P.YES4_LANE, P.NO4_LANE), "v3": (P.YES3_LANE, P.NO3_LANE), "v2": (P.YES_LANE, P.NO_LANE)}[cur]
    orders = [o for lane, k in zip(lanes_, (YES_ID, NO_ID)) for o in live_orders(k, live, f"{lane}|{P.SPORT}", s3, s4)]
    lrec = PL.record(orders) if orders else None
    yes_pending = not PL.record(live_orders(YES_ID, live, f"{lanes_[0]}|{P.SPORT}", s3, s4) or [])["sold"]
    live_big = f'{lrec["won"]}–{lrec["lost"]}' if lrec and lrec["n"] else "—"
    if orders and PL.current_schema(orders):
        live_big = PL.wfl(PL.own_summary(orders))
        live_label = "live record · W–F–L, trades after fees"
    else:
        live_label = "live record · held to settlement" + (" · YES exits pending" if yes_pending else "")
    return ('<div class="tiles sp-tiles">'
            f'<div class="tile"><b>{lrec["open"] if lrec else 0}</b><span>open bets · live</span></div>'
            f'<div class="tile"><b>{sum(1 for r in rows_ if r.get("v") != "retired")}</b><span>active lanes</span></div>'
            f'{tennis_cards.record_tile(rec, "since Production · entries")}'
            f'<div class="tile">{roi}<span>ROI after fees · since Production</span></div>'
            f'<div class="tile"><b>{esc(live_big)}</b><span>{esc(live_label)}</span></div></div>')


# ------------------------------------------------------------------ the section
def spec(rows_, details):
    return SP.spec(
        family="NBA", key="nba", title="Edge Machine · NBA", scoped=False,
        rule_name=lambda r: r.get("label") or r["name"], market=lambda d, r: r.get("market") or "",
        definition=lambda d, r: details.get(r["name"], ""), recent=None,
        record_head="Record (games)",
        extra_cols=(("record", "Entries won", entries_cell), ("roi", "Live fills", lambda r: r.get("live") or "—")))


def rules_section(chaos=None, nofade=None, v3=None, live=None, now=None, v4=None, v4p=None, v3p=None):
    """(tiles_and_filters_html, rules_html, rows): the head figures and the Rules section. Never raises for a lane:
    a lane whose fold fails says so inside its fold."""
    if chaos is None or nofade is None or v3 is None or live is None:
        c0, n0, v0, l0 = load_all()
        chaos, nofade, v3, live = chaos or c0, nofade or n0, v3 or v0, live if live is not None else l0
    now = now or dt.datetime.now(dt.timezone.utc)
    v4 = v4 if v4 is not None else V4.load()
    v4p = v4p if v4p is not None else V4P.load()
    v3p = v3p if v3p is not None else V4.load(None, V4.RULE_V3)
    rows_ = rows(chaos, nofade, v3, live, v4, v4p, v3p)
    latest = latest_read(chaos, nofade, v3, v4p)
    details = {}
    for lane, fn in ((YES_ID, lambda: yes_panel(chaos, nofade, v3, latest, v4p, v4)), (NO_ID, lambda: no_panel(chaos, nofade, v3, latest, v4p, v4)),
                     (YES3P_ID, lambda: yes3p_panel(v3p)), (NO75_ID, lambda: no75_panel(nofade, latest))):
        try:
            details[lane] = fn()
        except Exception as exc:                                # noqa: BLE001
            details[lane] = f'<p class="sm mut">This lane\'s details could not be built ({esc(type(exc).__name__)}).</p>'
    sp = spec(rows_, details)
    import nba_wm_production as P
    d, st, _blob = P.page_inputs({"quotes": []}, {"pairs": {}}, {"leads": {}, "pairs": {}}, chaos, nofade, now=now, v3=v3, v4=v4p)
    head = tiles(rows_, d, st, live, v3, v4p) + SP.filters_html(sp, rows_)
    return head, SP.rules_html(sp, d, rows_, now, []), rows_
