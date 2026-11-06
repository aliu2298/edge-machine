"""The NBA page's lanes in the Econ Daily layout (2026-11-05, Olu): tiles, the stage filter, the Rules table (one row per
lane: the win margin YES split and the NO fade), an empty Sandbox fold; nba_pace_build adds Research, Games, Retired and
the method around it.

Presentation only. Every figure is read from the ledgers nba_layout already read:
  * the record is version 3 (nba_wm_v3: the executor's own decisions, fills replayed from prints) once it has started,
    counted per GAME as the page has always counted it (chaos_replay.stats over the YES entries; nba_wm_v3.no_games for
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
import nba_wm_nofade as N
import nba_wm_nofade_build as NB
import fmt
import nba_wm_v3 as V3
import sport_page as SP

STALE_H = 12                 # a ledger read this long before the newest read on the page is tagged stale
YES_ID, NO_ID = NL.YES_ID, NL.NO_ID
LIVE_KEY = {YES_ID: "nba_wm_yes", NO_ID: "nba_wm_nofade"}
RULE_LINES = {
    YES_ID: ("Entry: buy YES on a 1-5 or 6-10 win margin bucket (either team) at the ask, 10-20c, an hour before the tip.",
             "Exit: rest a sell for half at 2x and half at 3x, filled only by prints strictly through the target from the tip on; "
             "the rest is held to settlement. Production: traded live."),
    NO_ID: ("Entry: after the tip, rest a post-only NO bid at 75% of a bucket's pregame NO price (10-95c); a bucket already at "
            "or under the bid at the tip is no entry.",
            "Exit: sell it back at the pregame price on a print strictly above it, else hold to settlement. Production: traded live."),
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


def latest_read(chaos, nofade, v3):
    stamps = [_t(x.get("last_run")) for x in (chaos, nofade, v3) if x]
    stamps = [s for s in stamps if s]
    return max(stamps).isoformat() if stamps else None


# ------------------------------------------------------------------ the records
def games_of(rows):
    """(won, settled) games: a game's entries summed, won when that profit is positive (as nba_wm_v3.no_games counts a game)."""
    by = {}
    for r in rows:
        by[r["event"]] = by.get(r["event"], 0.0) + float(r.get("profit") or 0)
    return sum(1 for p in by.values() if p > 0), len(by)


def yes_record(chaos, v3):
    """(a, entries, entries_won) for the YES split: version 3, the page's headline since 2026-11-04 (empty before it)."""
    yr = V3.yes_rows(v3) if (v3 or {}).get("since") else []
    s = C.stats(yr)
    gw, gn = games_of(yr)
    return dict(n=gn, won=gw, n_price=0, expected=None, roi_fee=s["roi"], z=s["z"] if s["z"] is not None else 0.0,
                z_known=s["z"] is not None, unit="game"), s["n"], s["won"]


def no_record(nofade, v3):
    if (v3 or {}).get("since"):
        g = V3.no_games(v3)
        rows = [r for r in v3["rows"].values() if r["lane"] == V3.NO_LANE and not r.get("no_entry") and "profit" in r]
    else:
        g = N.game_rows(nofade["entries"], N.vkey(N.HEAD), None, "v2")
        rows = []
    s = C.stats(g)
    entries = sum(r.get("fills", 1) for r in g)
    won_entries = sum(1 for r in rows if r["profit"] > 0) if rows else None
    return dict(n=s["n"], won=s["won"], n_price=0, expected=None, roi_fee=s["roi"], z=s["z"] if s["z"] is not None else 0.0,
                z_known=s["z"] is not None, unit="game"), entries, won_entries


def live_cell(lane, live):
    """The follower's own fills for this lane, as the Production page reads them (held to settlement)."""
    import production_live as PL
    orders = ((live or {}).get("lanes") or {}).get(LIVE_KEY[lane]) or []
    if not orders:
        return '<span class="mut">—</span>'
    rec = PL.record(orders)
    tail = f' <small class="mut">· {rec["open"]} open</small>' if rec["open"] else ""
    if LIVE_KEY[lane] in PL.EXITS and not rec["sold"]:
        return f'held {rec["won"]}–{rec["lost"]}, exits pending{tail}'
    roi = "" if rec["roi"] is None or LIVE_KEY[lane] in PL.EXITS else f' <small class="mut">{rec["roi"] * 100:+.1f}%</small>'
    sold = f' <small class="mut">· {rec["sold"]} exited early</small>' if rec["sold"] else ""
    return f'{rec["won"]}–{rec["lost"]}{roi}{sold}{tail}'


# ------------------------------------------------------------------ the rows
def rows(chaos, nofade, v3, live):
    import nba_wm_production as P
    since = (v3 or {}).get("since")
    ya, yn, yw = yes_record(chaos, v3)
    na, nn, nw = no_record(nofade, v3)
    yes_pair = f"{P.YES3_LANE if since else P.YES_LANE}|{P.SPORT}"
    no_pair = f"{P.NO3_LANE if since else P.NO_LANE}|{P.SPORT}"
    import sandbox_build as B
    out = []
    for lane, a, n_e, w_e, pair, label, market in (
            (YES_ID, ya, yn, yw, yes_pair, "Win margin · YES split", "Win margin · YES"),
            (NO_ID, na, nn, nw, no_pair, "Win margin · NO fade", "Win margin · NO")):
        out.append(dict(name=lane, sport="nba_wm", meta=dict(label=label, kind="Rule"), a=a, prod=True, pair=pair, open=0,
                        # z by night needs 3 nights (chaos_replay.MIN_NIGHTS_Z): until then the record cannot be read either way.
                        since=since, v=B.verdict(a) if a.get("z_known") or not a["n"] else "early", anchor=("wm-yes" if lane == YES_ID else "wm-no"),
                        entries=n_e, entries_won=w_e, live=live_cell(lane, live), market=market, label=label))
    return out


def entries_cell(row):
    if not row.get("entries"):
        return '<span class="mut">—</span>'
    won = row.get("entries_won")
    return f'{won if won is not None else "—"}/{row["entries"]}'


# ------------------------------------------------------------------ the folds
def yes_panel(chaos, nofade, v3, latest):
    lanes = NL._lanes(chaos)
    L = lanes.get(YES_ID)
    since = (v3 or {}).get("since")
    ch_tag = stale_tag(chaos.get("last_run"), latest)
    nf_tag = stale_tag(nofade.get("last_run"), latest)
    head = (NL._v3_block("Version 3", V3.yes_rows(v3), since, "wm-yes-v3") if since else (NL._record(L) if L else ""))
    out = "".join(f'<p class="sm sp-rule-line">{esc(x)}</p>' for x in RULE_LINES[YES_ID]) + head
    if since:
        yr = V3.yes_rows(v3)
        hold = (sum(r["hold_roi"] for r in yr) / len(yr)) if yr else None
        hold_line = (f'<p class="sm">Version 3 · the same {len(yr)} entries held to settlement: '
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
        older = (fold(f"Version 2 (to the night before {since})" if since else "Version 2", "entries judged from prints; its record stays",
                      CB.voided_line(L) + NL._record(L), ident="wm-yes-v2", tag=ch_tag) if since else "")
        if v1 is not None:
            older += fold("Paper version 1 (folded)", f"{v1.get('since')} to 2026-11-01 · sells filled on a print at the target",
                          '<p class="sm mut">The paper lane before it mirrored live orders. Its record stays as it was; it is not the '
                          f'Production record.</p>{NL._record(v1)}', ident="wm-yes-v1")
        out += fold("Older versions", "version 2 and paper version 1", older)
        sample = lanes.get(NL.SAMPLE_ID)
        if sample is not None:
            out += fold("In-sample research (not evidence)", f"{sample.get('since')} to {sample.get('until') or 'the first night'}, the days the rule was chosen on",
                        '<p class="sm mut">The same rule on the days it was found on. It is NOT evidence and is never the headline.</p>'
                        + NL._record(sample) + CB.variant_table(sample, skip=(C.SPLIT,)), ident=f"{YES_ID}-insample")
    out += fold("YES / NO overlap", "the two lanes side by side, and the games where both traded", NB.side_by_side(nofade, chaos), tag=nf_tag)
    if L:
        out += fold("Last 30 trades", "split, T target, S stop, H held to settlement", CB.trade_list(L), tag=ch_tag)
    return out


def no_panel(chaos, nofade, v3, latest):
    since = (v3 or {}).get("since")
    nf_tag = stale_tag(nofade.get("last_run"), latest)
    c = N.counts(nofade["entries"], None, "v2")
    i = N.counts(nofade["entries"], True)
    c1 = N.counts(nofade["entries"], None, "v1")
    head = (NL._v3_block("Version 3", V3.no_games(v3), since, "wm-no-v3") if since
            else NB.variant_rows(nofade, False, dips=(N.HEAD,), phase="v2"))
    out = "".join(f'<p class="sm sp-rule-line">{esc(x)}</p>' for x in RULE_LINES[NO_ID]) + head
    out += f'<p class="sm mut">Skipped as unverified ask: {c["unverified"]} of {c["unverified"] + c["verified"]} buckets.</p>'
    out += fold("Alternate exits", "the NO bid at 85% and 65% of pregame (75% is the rule); it sells back at pregame, so no hold row",
                NB.variant_rows(nofade, False, dips=tuple(x for x in N.DIPS if x != N.HEAD), phase="v2"), tag=nf_tag)
    older = (fold(f"Version 2 (to the night before {since})", "entries judged from prints; its record stays",
                  NB.variant_rows(nofade, False, dips=(N.HEAD,), phase="v2"), ident="wm-no-v2", tag=nf_tag) if since else "")
    older += fold("Paper version 1 (folded)", f"{N.SINCE} to {N.V2_FROM}, fills and sells on a print at the price · {c1['games']} games read",
                  '<p class="sm mut">The paper lane before it mirrored live orders. Its record stays as it was; it is not the Production record.</p>'
                  + NB.variant_rows(nofade, False, dips=(N.HEAD,), phase="v1"), ident="nofade-v1")
    out += fold("Older versions", "version 2 and paper version 1", older)
    out += fold("In-sample research (not evidence)", f"{N.SINCE_IN} to {N.SINCE}, the days the rule was chosen on",
                f'<p class="sm mut">The same rule on Oct 20-30. {i["games"]} games read, {i["unverified"]} of {i["unverified"] + i["verified"]} '
                'buckets skipped as unverified ask. NOT evidence, never the headline.</p>' + NB.variant_rows(nofade, True), ident="nofade-insample")
    out += fold("YES / NO overlap", "the two lanes side by side, and the games where both traded", NB.side_by_side(nofade, chaos), tag=nf_tag)
    out += fold("Last 30 trades", "games with a fill · the headline row", NB.trade_list(nofade), tag=nf_tag)
    last = nofade.get("last_run")
    out += f'<p class="sm mut">NO fade ledger last read {esc(last or "not yet")}{(" · " + esc(nofade["error"])) if nofade.get("error") else ""}.</p>'
    return out


# ------------------------------------------------------------------ the tiles
def tiles(rows_, d, st, live):
    """Open bets (live), active lanes, the since-Production record and ROI (the Production page's own, every pair of the
    two lanes: version 2 to the night before version 3, version 3 since), and the live record (held to settlement)."""
    import nba_wm_production as P
    import production
    import production_live as PL
    import sandbox_build as B
    import tennis_cards
    pseudo = [dict(name=k.split("|")[0], sport=k.split("|")[1], prod=True, pair=k) for k in P.pairs(None) | P.pairs({"since": "x"})]
    rec, _names = SP.since_production(d, st, pseudo)
    n = int(rec.get("n") or 0)
    roi = ('<b class="mut">—</b>' if not n or rec.get("roi_fee") is None else
           f'<b class="{"mut" if n < production.EARLY_N else fmt.tone(rec["roi_fee"], ".1f", 100)}">{B.pct(rec["roi_fee"], sign=True)}</b>')
    orders = [o for k in LIVE_KEY.values() for o in ((live or {}).get("lanes") or {}).get(k) or []]
    lrec = PL.record(orders) if orders else None
    yes_pending = not PL.record(((live or {}).get("lanes") or {}).get("nba_wm_yes") or [])["sold"]
    live_big = f'{lrec["won"]}–{lrec["lost"]}' if lrec and lrec["n"] else "—"
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


def rules_section(chaos=None, nofade=None, v3=None, live=None, now=None):
    """(tiles_and_filters_html, rules_html, rows): the head figures and the Rules section. Never raises for a lane:
    a lane whose fold fails says so inside its fold."""
    if chaos is None or nofade is None or v3 is None or live is None:
        c0, n0, v0, l0 = load_all()
        chaos, nofade, v3, live = chaos or c0, nofade or n0, v3 or v0, live if live is not None else l0
    now = now or dt.datetime.now(dt.timezone.utc)
    rows_ = rows(chaos, nofade, v3, live)
    latest = latest_read(chaos, nofade, v3)
    details = {}
    for lane, fn in ((YES_ID, yes_panel), (NO_ID, no_panel)):
        try:
            details[lane] = fn(chaos, nofade, v3, latest)
        except Exception as exc:                                # noqa: BLE001
            details[lane] = f'<p class="sm mut">This lane\'s details could not be built ({esc(type(exc).__name__)}).</p>'
    sp = spec(rows_, details)
    import nba_wm_production as P
    d, st, _blob = P.page_inputs({"quotes": []}, {"pairs": {}}, {"leads": {}, "pairs": {}}, chaos, nofade, now=now, v3=v3)
    head = tiles(rows_, d, st, live) + SP.filters_html(sp, rows_)
    return head, SP.rules_html(sp, d, rows_, now, []), rows_
