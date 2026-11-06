"""Soccer's own-ledger lanes as rows of the shared sport template (2026-11-05, Olu: one page, laid out like Econ Daily).

Until then the Soccer page drew each own-ledger lane as its own long section: the over 3.5 cheap NO and the two goalless
dips above the rules, the label rules, team scoring, contenders and Argentina & Brasileirao over 1.5 below the events.
Here every one of them is ONE row of the template's Rules (Production) or Sandbox rules table, with the same columns as a
tracker rule, and its words (definition, alternate exits, league splits, version history, in-sample research, every
entry) inside the row's closed "Rule details" fold. Retired ones go in the template's Retired fold.

Presentation only. Each record is counted the way its old section counted it:
  * a label / team / contender / Arg-Bra rule: every settled entry on its own ledger (soccer_rules_build._record:
    won + lost + no result settled, ROI = profit over $100 a settled entry, 7% fee already in the profit);
  * the over 3.5 cheap NO: the v4 record's headline exit, the 10c bid sold at 4x (chaos_replay.stats);
  * a goalless dip: the headline buy's counted fills (arg_dip.summary).
The verdict is sandbox_build.verdict() on that record, and z is the lane's own (independent picks at their price for a
pick lane; by night / by matchday for an in-play lane, as its old section showed it). Nothing here grades or settles.

The entries also become Sandbox-style quotes (source = the row's name, sport = its market), added to the page's copy of
the ledger in memory, so the template's Events tabs and recent picks list them with the tracker's own picks. A
Production lane's quotes are its Production adapter's (soccer_rules_production, soccer_team_rules_production,
o35_production, top5_dip_production), so the "since Production" tile pools exactly what the Production page pools.
"""
import html as _h
import json
import os

import daily_track as D
import fmt

ROOT = os.path.dirname(os.path.abspath(__file__))

SR_MARKET = {"total": None, "btts": "soccer_btts"}      # a total rule's sport is its line's (soccer_o25 / soccer_u35)
INTL_LEAGUES = ("UEFA Nations League",)                 # the label rules' international scope


def esc(x):
    return _h.escape("" if x is None else str(x))


def _read(path):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


# ------------------------------------------------------------------ records
def pick_record(picks):
    """A pick lane's record, counted as its old section counted it, in the template's shape.

    n won + lost, n_price the no-result settles, roi_fee profit over $100 a settled entry (no results included),
    expected the summed price of the won and lost picks, z (won - expected) / sqrt(sum p(1 - p))."""
    done = [p for p in picks if p.get("status") in ("won", "lost", "no_result")]
    binary = [p for p in done if p["status"] in ("won", "lost")]
    won = sum(p["status"] == "won" for p in binary)
    prices = [float(p.get("price") or 0) for p in binary]
    expected = sum(prices)
    var = sum(x * (1 - x) for x in prices)
    return dict(n=len(binary), n_price=len(done) - len(binary), won=won, expected=expected,
                roi_fee=(sum(float(p.get("profit") or 0) for p in done) / (100 * len(done))) if done else None,
                z=((won - expected) / var ** 0.5) if var > 0 else 0.0, n_bets=len(done), unit="bet")


def inplay_record(n, won, roi, z):
    """An in-play lane's headline exit as a template record: no priced-win count (a take-profit exit has none)."""
    return dict(n=int(n or 0), n_price=0, won=int(won or 0), expected=None, roi_fee=roi, z=z if z is not None else 0.0,
                n_bets=int(n or 0), unit="bet")


def verdict(a, retired=False):
    import sandbox_build as B
    return "retired" if retired else B.verdict(a)


# ------------------------------------------------------------------ quotes
def _status(p):
    return {"open": "open", "won": "won", "lost": "lost", "no_result": "settled"}.get(p.get("status"))


def pick_quote(src, sport, p, market_text, title=None):
    """One own-ledger pick as a Sandbox-style quote (the Production adapters' shape), or None when it cannot be read."""
    start, logged, price = D.instant(p.get("start")), D.instant(p.get("logged")), D.number(p.get("price"))
    home, _, away = str(p.get("match") or "").partition(" v ")
    status = _status(p)
    if not start or not logged or price is None or not 0 < price < 1 or not (home and away) or status is None:
        return None
    pick = "a" if p.get("side") == "yes" else "b"
    won_side = pick if status == "won" else ("b" if pick == "a" else "a")
    return dict(
        id=f"{src}:{p.get('ticker') or p.get('id')}", source=src, sport=sport, venue="kalshi_binary",
        market_id=p.get("ticker") or p.get("id"), event=p.get("event"), label=f"{home} v {away}: {market_text}",
        side_a="Yes", side_b="No", kalshi_title=title, league=p.get("league"), espn_home=home, espn_away=away,
        date=start.date().isoformat(), start=start.isoformat(), logged=logged.isoformat(), price=price,
        price_a=price if pick == "a" else None, price_b=price if pick == "b" else None, price_draw=None, pick=pick,
        bet=True, stake=100.0, status=status, pnl=round(float(p.get("profit") or 0), 2) if status != "open" else 0.0,
        result=("price" if status == "settled" else won_side) if status != "open" else None,
        settle_px=p.get("payout"), settled=p.get("settled"), prob_a=None, edge=None, untraded=False,
        start_source="espn", url="", rule=p.get("rule"))


# ------------------------------------------------------------------ the row
def row(name, sport, label, market, a, details, *, prod=False, pair=None, open_n=0, gone=None, anchor=None,
        entries="", kind="Rule", note=""):
    """One own-ledger lane in the template's row shape. `details` is the definition html of its fold, `entries`
    its own entries list (shown under the recent picks)."""
    return dict(name=name, sport=sport, meta=dict(label=label, note=note, kind=kind), a=a, prod=prod, pair=pair,
                open=open_n, since=None, v=verdict(a, retired=bool(gone)), gone=gone, anchor=anchor,
                own=dict(label=label, market=market, details=details, entries=entries))


def params_html(params):
    return '<dl class="sp-params">' + "".join(f"<dt>{esc(k)}</dt><dd>{esc(v)}</dd>" for k, v in params if v) + "</dl>"


def entries_table(picks, cols):
    """Every entry of one rule, newest first, in a closed fold. `cols` = [(head, fn(pick) -> text)]."""
    if not picks:
        return '<p class="sm mut">No entry yet.</p>'
    picks = sorted(picks, key=lambda p: p.get("start") or "", reverse=True)
    head = "".join(f"<th>{esc(h)}</th>" for h, _ in cols)
    body = "".join("<tr>" + "".join(f"<td>{esc(fn(p))}</td>" for _h2, fn in cols) + "</tr>" for p in picks)
    n = len(picks)
    return (f'<details class="section-disclosure"><summary><b>Entries</b><span>{n} entr{"y" if n == 1 else "ies"}</span></summary>'
            f'<div class="tbl"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div></details>')


def _res(p):
    res = {"open": "open", "won": "won", "lost": "lost", "no_result": "no result"}.get(p.get("status"), p.get("status"))
    return res + (f" · ${p['profit']:+.2f}" if p.get("profit") is not None else "")


KICK = ("Kickoff", lambda p: fmt.when(p["start"]) if p.get("start") else "")
MATCH = ("Match", lambda p: p.get("match") or "")
PRICE = ("Price", lambda p: f'{float(p.get("price") or 0) * 100:.0f}c')
RESULT = ("Result", _res)


# ------------------------------------------------------------------ the label rules (soccer_rules.py)
def label_rows(state=None):
    """The total-goals and BTTS label rules: (live rows, retired rows, quotes for the non-Production rows)."""
    import soccer_rules as SR
    import soccer_rules_build as SB
    import soccer_rules_production as RP
    state = state if state is not None else (SR.load() if os.path.exists(SR.PATH) else {"rules": {}})
    live, gone_rows, quotes = [], [], []
    for key, meta in SR.RULES.items():
        picks = (state.get("rules", {}).get(key) or {}).get("picks") or []
        btts = meta["market"] == "btts"
        line = meta.get("line")
        intl = meta["league"] in INTL_LEAGUES
        if key in RP.PAIRS:
            src, sport, _n = RP.PAIRS[key]
        else:
            src = f"sr_{key.lower()}"
            sport = "soccer_btts" if btts else ("soccer_u35" if line == 3.5 else "soccer_o25")
            sport += "_intl" if intl else ""
        market = (("BTTS" if meta["side"] == "yes" else "BTTS · No") if btts
                  else f'{"Over" if meta["side"] == "yes" else "Under"} {line:g}')
        league = (f"All {len(SR.MARKETS[meta['market']])} BTTS leagues" if meta["league"] == SR.ALL else meta["league"])
        history = []
        if key in RP.PAIRS:
            history.append(f"Production since {RP.moved_on(key)} (moved by hand)")
        if key in RP.PULLED:
            history.append(f"Production {RP.PULLED[key][0]} to {RP.PULLED[key][1]}, back in the Sandbox on its whole record")
        if key == "D3":
            history.append("Production 2026-10-21 to 2026-10-28, back in the Sandbox")
        gone = SR.RETIRED.get(key)
        if gone:
            history.append(f"Retired {gone['on']}: {gone['reason']}. Its entries stay and settle")
        details = (params_html([("League", league), ("Group", f"{meta['group']} · {SR.GROUPS[meta['group']]}"),
                                ("Rule", meta["label"]), ("Research", meta.get("evidence")),
                                ("Record", "Paper at the Kalshi price, 7% fee, Kalshi's own settlement"),
                                ("History", " · ".join(history))])
                   + (SB.BTTS_NOTE if btts else ""))
        labels = ("Labels", lambda p: f'{(p.get("labels") or {}).get("home") or ""} v {(p.get("labels") or {}).get("away") or ""}')
        side = ("Side", lambda p: str(p.get("side") or "").upper())
        contract = ("Contract", lambda p: p.get("title") or "")
        r = row(src, sport, f"{key} · {meta['league'] if meta['league'] != SR.ALL else 'every BTTS league'} · {meta['label']}",
                market, pick_record(picks), details, prod=key in RP.PAIRS, pair=f"{src}|{sport}" if key in RP.PAIRS else None,
                open_n=sum(p.get("status") == "open" for p in picks),
                gone=(f"Retired {gone['on']}: {gone['reason']}." if gone else None),
                entries=entries_table(picks, [KICK, MATCH, labels, contract, side, PRICE, RESULT]))
        (gone_rows if gone else live).append(r)
        if key not in RP.PAIRS:
            text = "both teams to score" if btts else f"over {line:g} goals"
            quotes += [q for q in (pick_quote(src, sport, p, text, "Both Teams To Score" if btts else None)
                                   for p in picks) if q]
    return live, gone_rows, quotes


# ------------------------------------------------------------------ team scoring (soccer_team_rules.py)
SHORT = {"Premier League": "EPL", "Champions League": "UCL", "Europa League": "UEL"}


def team_rows(state=None):
    import soccer_team_rules as TR
    import soccer_team_rules_production as TRP
    state = state if state is not None else (TR.load() if os.path.exists(TR.PATH) else {"rules": {}})
    live, gone_rows, quotes = [], [], []
    for key, meta in TR.RULES.items():
        picks = (state.get("rules", {}).get(key) or {}).get("picks") or []
        goals = meta["goals"]
        if key in TRP.PAIRS:
            src, sport, _n = TRP.PAIRS[key]
        else:
            src, sport = f"st_{key.lower()}", ("soccer_team2" if goals == 2 else "soccer_team3")
        market = f"Team {goals}+" if meta["side"] == "yes" else f"Team under {goals}"
        leagues = ", ".join(SHORT.get(x, x) for x in meta["leagues"])
        history = []
        if key == "T1":
            history.append(f"Production {TRP.T1_MOVED_ON} to {TRP.PULLED_ON}, back in the Sandbox")
            history.append("Re-read at 50 settled (Olu, 2026-11-01)")
        elif key == "T5":
            history.append(f"Production {TRP.T5_PULLED[0]} to {TRP.T5_PULLED[1]}, back in the Sandbox")
        elif key in TRP.PAIRS:
            history.append(f"Production since {TRP.MOVED[key]} (moved by hand)")
        gone = TR.RETIRED.get(key)
        if gone:
            history.append(f"Retired {gone['on']}: {gone['reason']}. Its entries stay and settle")
        details = params_html([("Leagues", leagues), ("Group", f"{meta['group']} · {TR.GROUPS[meta['group']]}"),
                               ("Rule", meta["label"]), ("Research", meta.get("evidence")),
                               ("Record", "Paper at the Kalshi price, 7% fee, Kalshi's own settlement"),
                               ("History", " · ".join(history))])
        team = ("Team", lambda p: p.get("team") or "")
        labels = ("Labels", lambda p: f'{(p.get("labels") or {}).get("own") or ""} v {(p.get("labels") or {}).get("opp") or ""}')
        r = row(src, sport, f"{key} · {leagues} · {meta['label']}", market, pick_record(picks), details,
                prod=key in TRP.PAIRS, pair=f"{src}|{sport}" if key in TRP.PAIRS else None,
                open_n=sum(p.get("status") == "open" for p in picks),
                gone=(f"Retired {gone['on']}: {gone['reason']}." if gone else None),
                entries=entries_table(picks, [KICK, MATCH, team, labels, ("Contract", lambda p: p.get("title") or ""),
                                              ("Side", lambda p: str(p.get("side") or "").upper()), PRICE, RESULT]))
        (gone_rows if gone else live).append(r)
        if key not in TRP.PAIRS:
            for p in picks:
                q = pick_quote(src, sport, p, f"{p.get('team') or ''} to score {goals}+",
                               title=TRP.kalshi_title(p))
                if q:
                    quotes.append(dict(q, team=p.get("team"), opponent=p.get("opponent")))
    return live, gone_rows, quotes


# ------------------------------------------------------------------ contenders and Argentina & Brasileirao (all retired)
def contender_rows(state=None):
    import contender_overs as CO
    state = state if state is not None else (CO.load() if os.path.exists(CO.PATH) else {"rules": {}})
    live, gone_rows = [], []
    for key, v in CO.VARIANTS.items():
        picks = (state.get("rules", {}).get(key) or {}).get("picks") or []
        gone = CO.RETIRED.get(key)
        details = params_html([("Leagues", "Eredivisie, Primeira"), ("Rule", f"Contender's match · {v['words']}"),
                               ("Contenders", "The top 3 of the open Kalshi champion market by mid at entry, teams with no bid left out"),
                               ("Research", v["evidence"]), ("Record", "Paper at the Kalshi price, 7% fee"),
                               ("History", f"Retired {gone['on']}: {gone['reason']}. Its entries stay and settle" if gone else "")])
        contender = ("Contender", lambda p: ", ".join(p.get("contenders_in") or []))
        tops = ("Top 3 at entry (mid)", lambda p: ", ".join(f"{c['team']} {c['mid'] * 100:.0f}c" for c in p.get("contenders") or []))
        r = row(f"co_{key.lower()}", "soccer_o15" if v["line"] == 1.5 else ("soccer_o25" if v["line"] == 2.5 else "soccer_u35"),
                f"Contenders {key} · Eredivisie, Primeira · {v['words']}", f"Over {v['line']:g}", pick_record(picks), details,
                open_n=sum(p.get("status") == "open" for p in picks),
                gone=(f"Retired {gone['on']}: {gone['reason']}." if gone else None),
                entries=entries_table(picks, [KICK, MATCH, contender, tops, PRICE, RESULT]))
        (gone_rows if gone else live).append(r)
    return live, gone_rows


def sa_rows(state=None):
    import sa_o15 as SA
    state = state if state is not None else (SA.load() if os.path.exists(SA.PATH) else {"rules": {}})
    live, gone_rows = [], []
    for key, meta in SA.ROWS.items():
        picks = (state.get("rules", {}).get(key) or {}).get("picks") or []
        gone = SA.RETIRED.get(key)
        hist = ["Production 2026-10-21 to 2026-10-27, back in the Sandbox"] if key == "ARG" else []
        if gone:
            hist.append(f"Retired {gone['on']}: {gone['reason']}. Its entries stay and settle")
        details = params_html([("League", meta["league"]), ("Rule", "Every league match · over 1.5 goals · YES at the ask, no selection"),
                               ("Research", meta["evidence"]), ("Record", "Paper at the Kalshi price, 7% fee; the two leagues are judged apart"),
                               ("History", " · ".join(hist))])
        r = row(f"sa_o15_{key.lower()}", "soccer_o15", f"{meta['league']} over 1.5 · every match", "Over 1.5", pick_record(picks),
                details, open_n=sum(p.get("status") == "open" for p in picks),
                gone=(f"Retired {gone['on']}: {gone['reason']}." if gone else None),
                entries=entries_table(picks, [KICK, MATCH, PRICE, RESULT]))
        (gone_rows if gone else live).append(r)
    return live, gone_rows


# ------------------------------------------------------------------ the in-play lanes
def o35_row(state=None):
    import chaos_replay as CR
    import o35_cheap_no as O
    import o35_cheap_no_build as OB
    import o35_production as OP
    state = state if state is not None else (O.load() if os.path.exists(O.PATH) else O.load("/nonexistent"))
    entries = [e for e in state.get("entries") or [] if e.get("version") == O.VERSION]
    s = CR.stats([r for r in O.trade_rows(entries) if r["variant"] == OB.HEAD])
    return row(OP.LANE, OP.SPORT, f"{O.LABEL}", "Under 3.5 · in-play",
               inplay_record(s["n"], s["won"], s["roi"], s["z"]), OB.panel(state), prod=True, pair=f"{OP.LANE}|{OP.SPORT}",
               anchor="cheap-side", kind="In-play",
               note=f"Record: the v4 record's headline exit (bid {round(O.HEADLINE * 100)}c, sell at {O.HEAD_MULT:g}x).")


def dip_row(page):
    import arg_dip as A
    import arg_dip_build as AB
    state = AB.load_state(page)
    cfg = page["cfg"]
    entries = [e for e in state.get("entries") or [] if e.get("buys") is not None]
    s = A.summary(entries, cfg["headline"])
    won = sum(1 for r in A.rows_of(entries, cfg["headline"]) if r["roi"] > 0)
    strike = "0.5" if page is AB.ARG_PAGE else "1.5"
    return row(cfg["lane"], "soccer_o15" if strike == "1.5" else "soccer", cfg["label"],
               f"Over {strike} · in-play", inplay_record(s["fills"], won, s["roi"], s["z"]),
               AB.panel(state, page), anchor=page["id"], kind="In-play",
               note=f"Record: the headline buy's counted fills (buy at {A.vkey(cfg['headline'])}% of the pregame ask P, sell at P).")


def top5_live_row(live_ledger, now):
    """The top-5 goalless dip in Production (top5_dip_production, 2026-11-05): its record is the paper record that follows
    the follower's own decisions (top5_dip_live), counted per counted fill as the Production page counts it."""
    import top5_dip_production as TP
    qs = [q for q in TP.quotes(live_ledger or {}, {}) if q["status"] != "open"]
    n = len(qs)
    a = inplay_record(n, sum(q["status"] == "won" for q in qs), (sum(q["pnl"] for q in qs) / (100 * n)) if n else None, None)
    details = params_html([
        ("Rule", "An hour before kickoff the follower reads the YES ask P of the over 1.5 rung; from kickoff it rests one "
                 "post-only YES bid at 55% of P, a small fixed size a match; on a fill, a resting sell at P; an unsold "
                 "position is held to settlement. A bid that would cross the book is no entry. Never chases."),
        ("Leagues", "Premier League, La Liga, Serie A, Bundesliga, Ligue 1, Champions League"),
        ("Record", f"Production from {TP.MOVED_ON}, fresh: the paper record that follows the follower's own decisions. "
                   "The research record is the Sandbox row Top-5 goalless dip."),
    ])
    return row(TP.LANE, TP.SPORT, TP.NAME, "Over 1.5 · in-play", a, details, prod=True,
               pair=f"{TP.LANE}|{TP.SPORT}", kind="In-play")


# ------------------------------------------------------------------ everything
def rows_and_inputs(d, st, now):
    """(live rows, retired rows, d, st): the own-ledger lanes as rows, and the page's ledger and stages with their
    quotes and Production pairs added in memory. A lane that fails to read is left out, never the page."""
    live, gone, extra = [], [], []
    for fn in (label_rows, team_rows):
        try:
            lv, gn, qs = fn()
            live, gone, extra = live + lv, gone + gn, extra + qs
        except Exception as exc:                                # noqa: BLE001
            print(f"soccer_lanes: {fn.__name__} failed: {type(exc).__name__}: {exc}")
    for fn in (contender_rows, sa_rows):
        try:
            lv, gn = fn()
            live, gone = live + lv, gone + gn
        except Exception as exc:                                # noqa: BLE001
            print(f"soccer_lanes: {fn.__name__} failed: {type(exc).__name__}: {exc}")
    blob = {"leads": {}, "pairs": {}}
    d = dict(d, quotes=list(d.get("quotes") or []) + extra)
    # The Production lanes' own adapters: their quotes feed the Events tabs and the since-Production tile.
    try:
        import soccer_rules_production as RP
        d, st, blob = RP.page_inputs(d, st, blob, *RP.load_states(), now=now)
    except Exception as exc:                                    # noqa: BLE001
        print(f"soccer_lanes: soccer_rules_production failed: {type(exc).__name__}: {exc}")
    try:
        import soccer_team_rules as TR
        import soccer_team_rules_production as TRP
        d, st, blob = TRP.page_inputs(d, st, blob, TR.load(), now=now)
    except Exception as exc:                                    # noqa: BLE001
        print(f"soccer_lanes: soccer_team_rules_production failed: {type(exc).__name__}: {exc}")
    try:
        import o35_production as OP
        live.append(o35_row())
        d, st, blob = OP.page_inputs(d, st, blob, _read(os.path.join(ROOT, "data", "o35_cheap_no_ledger.json")) or {}, now=now)
    except Exception as exc:                                    # noqa: BLE001
        print(f"soccer_lanes: the over 3.5 cheap NO failed: {type(exc).__name__}: {exc}")
    try:
        import arg_dip_build as AB
        live.append(dip_row(AB.ARG_PAGE))
    except Exception as exc:                                    # noqa: BLE001
        print(f"soccer_lanes: the Argentina dip failed: {type(exc).__name__}: {exc}")
    try:
        import arg_dip_build as AB
        live.append(dip_row(AB.TOP5_PAGE))
    except Exception as exc:                                    # noqa: BLE001
        print(f"soccer_lanes: the top-5 dip failed: {type(exc).__name__}: {exc}")
    try:
        import top5_dip_production as TP
        ledger = _read(os.path.join(ROOT, "data", "top5_dip_live.json")) or {}
        live.append(top5_live_row(ledger, now))
        d, st, blob = TP.page_inputs(d, st, blob, ledger, now=now)
    except Exception as exc:                                    # noqa: BLE001
        print(f"soccer_lanes: the top-5 dip in Production failed: {type(exc).__name__}: {exc}")
    return live, gone, d, st
