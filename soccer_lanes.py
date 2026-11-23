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


# ------------------------------------------------------------------ shadows (shadows.py, 2026-11-21)
def shadow_html(lane, states=None, picks=None):
    """The "Shadows (paper, not counted)" fold of a source lane's row: the BTTS YES shadow and the half-time check, beside the headline.
    Never raises: a ledger that cannot be read leaves the row as it was."""
    try:
        import shadows as SH
        meta = SH.LANES[lane]
        st = (states or {}).get(meta["group"]) or SH.load(meta["group"])
        picks = picks if picks is not None else SH.source_picks(lane)
        p1 = lambda x: "—" if x is None else f"{x * 100:.1f}%"                         # noqa: E731
        pr = lambda x: "—" if x is None else f"{x * 100:+.1f}%".replace("-", "−")     # noqa: E731
        b = SH.btts_stats(st, lane)
        h = SH.ht_stats(st, lane, picks)
        name = "2H BTTS YES" if meta["kind"] == "2h" else "BTTS YES"
        bt = "".join(f'<td class="num" data-l="{k}">{esc(v)}</td>' for k, v in zip(
            ("Shadow", "Matches priced", "No quote", "Won-lost", "Average YES price", "Return after fees"),
            (name + " (shadow)", b["matches"] - b["no_quote"], b["no_quote"], f'{b["won"]}-{b["lost"]}', p1(b["avg_price"]), pr(b["ret"]))))
        ins = meta["in_sample"]["btts"]
        bt = f"<tr>{bt}</tr>" + ('<tr class="mut"><td data-l="Shadow">In-sample, not counted</td><td colspan="5" data-l="Record">' + esc(ins or "no figure") + "</td></tr>")
        btts_tbl = ('<div class="tbl"><table><thead><tr><th>Shadow</th><th>Matches priced</th><th>No quote</th><th>Won-lost</th><th>Average YES price</th>'
                    f'<th>Return after fees</th></tr></thead><tbody>{bt}</tbody></table></div>')
        ht = "".join(f'<td class="num" data-l="{k}">{esc(v)}</td>' for k, v in zip(
            ("Shadow", "Checked", "Sold-held-no bid", "Average price paid", "Shadow return after fees", "Hold return, same entries"),
            ("Half-time check (shadow)", h["checked"], f'{h["sold"]}-{h["held"]}-{h["no_bid"]}', p1(h["avg_price"]), pr(h["ret"]), pr(h["hold_ret"]))))
        ins = meta["in_sample"]["ht"]
        ht = f"<tr>{ht}</tr>" + ('<tr class="mut"><td data-l="Shadow">In-sample, not counted</td><td colspan="5" data-l="Record">' + esc(ins or "no figure") + "</td></tr>")
        ht_tbl = ('<div class="tbl"><table><thead><tr><th>Shadow</th><th>Checked</th><th>Sold-held-no bid</th><th>Average price paid</th>'
                  f'<th>Shadow return after fees</th><th>Hold return, same entries</th></tr></thead><tbody>{ht}</tbody></table></div>')
        words = ("At the entry minute the YES ask on the match's " + ("second-half" if meta["kind"] == "2h" else "full-game") + " BTTS market (spread 3c or less, "
                 "else no quote), held to settlement; one a match. Half-time check: at half-time, "
                 + ("if the backed team has not scored, sell at its team-total YES bid, else hold"
                    if meta["ht"] == "team" else "if 0-0, sell at the over's YES bid, else hold")
                 + "; no bid counts as hold. Half-time is read from ESPN's match events and Kalshi's one-minute bid. Shadows never change the headline record.")
        return ('<details class="section-disclosure"><summary><b>Shadows (paper, not counted)</b><span>2 columns beside the headline</span></summary>'
                f'<p class="sm">{esc(words)}</p>{btts_tbl}{ht_tbl}</details>')
    except Exception as exc:                                    # noqa: BLE001
        print(f"soccer_lanes: shadows {lane} failed: {type(exc).__name__}: {exc}")
        return ""


# ------------------------------------------------------------------ the row
def legs_table(tradeable, every, headline="Legs the follower can take (headline)", all_label="All paper legs, incl. above the live price cap"):
    """The two records of a Production pair whose paper legs are not all tradeable (2026-11-06), one header-row table in the fold:
    the headline (legs inside the follower's price cap and band, live_caps.py) and every leg the rule logged. Nothing is removed from
    the ledger: only the headline filters."""
    heads = ("Settled", "Won", "Priced to win", "ROI after fees")

    def cells(a):
        roi = "—" if a.get("roi_fee") is None else f'{a["roi_fee"] * 100:+.1f}%'.replace("-", "−")
        return (a["n"] + a.get("n_price", 0), a["won"], f'{(a.get("expected") or 0):.1f}', roi)

    body = ""
    for label, a in ((headline, tradeable), (all_label, every)):
        body += (f'<tr><td data-l="Legs">{esc(label)}</td>'
                 + "".join(f'<td class="num" data-l="{h}">{esc(c)}</td>' for h, c in zip(heads, cells(a))) + "</tr>")
    return ('<div class="tbl"><table><thead><tr><th>Legs</th>' + "".join(f'<th class="num">{h}</th>' for h in heads)
            + f'</tr></thead><tbody>{body}</tbody></table></div>')


def row(name, sport, label, market, a, details, *, prod=False, pair=None, open_n=0, gone=None, anchor=None,
        entries="", kind="Rule", note="", legs_html=""):
    """One own-ledger lane in the template's row shape. `details` is the definition html of its fold, `entries`
    its own entries list (shown under the recent picks)."""
    return dict(name=name, sport=sport, meta=dict(label=label, note=note, kind=kind), a=a, prod=prod, pair=pair,
                open=open_n, since=None, v=verdict(a, retired=bool(gone)), gone=gone, anchor=anchor, legs_html=legs_html,
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


def leg_col(pair):
    """For a Production pair: a column naming the legs the follower could not take (above its price cap or outside its band)."""
    import live_caps as LC
    return ("Live guard", lambda p: LC.reason(pair, p.get("price")) or "")


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
                   + (SB.BTTS_NOTE if btts else "") + (shadow_html(key) if key == "A7" else ""))
        labels = ("Labels", lambda p: f'{(p.get("labels") or {}).get("home") or ""} v {(p.get("labels") or {}).get("away") or ""}')
        side = ("Side", lambda p: str(p.get("side") or "").upper())
        contract = ("Contract", lambda p: p.get("title") or "")
        pair = f"{src}|{sport}" if key in RP.PAIRS else None
        import live_caps as LC
        tp, _all = LC.split(pair, picks) if pair else (picks, picks)
        cols = [KICK, MATCH, labels, contract, side, PRICE, RESULT] + ([leg_col(pair)] if pair and len(tp) != len(picks) else [])
        r = row(src, sport, f"{key} · {meta['league'] if meta['league'] != SR.ALL else 'every BTTS league'} · {meta['label']}",
                market, pick_record(tp), details, prod=key in RP.PAIRS, pair=pair,
                open_n=sum(p.get("status") == "open" for p in tp),
                gone=(f"Retired {gone['on']}: {gone['reason']}." if gone else None),
                entries=entries_table(picks, cols),
                legs_html=legs_table(pick_record(tp), pick_record(picks)) if len(tp) != len(picks) else "")
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
        elif key == "T4":
            history.append(f"Production {TRP.T4_PULLED[0]} to {TRP.T4_PULLED[1]}, back in the Sandbox")
        elif key in TRP.PAIRS:
            history.append(f"Production since {TRP.MOVED[key]} (moved by hand)")
        gone = TR.RETIRED.get(key)
        if gone:
            history.append((gone.get("line") or f"Retired {gone['on']}: {gone['reason']}.") + " Its entries stay and settle")
        details = params_html([("Leagues", leagues), ("Group", f"{meta['group']} · {TR.GROUPS[meta['group']]}"),
                               ("Rule", meta["label"]), ("Research", meta.get("evidence")),
                               ("Record", "Paper at the Kalshi price, 7% fee, Kalshi's own settlement"),
                               ("History", " · ".join(history))]) + (shadow_html(key) if key == "T1" else "")
        team = ("Team", lambda p: p.get("team") or "")
        labels = ("Labels", lambda p: f'{(p.get("labels") or {}).get("own") or ""} v {(p.get("labels") or {}).get("opp") or ""}')
        pair = f"{src}|{sport}" if key in TRP.PAIRS else None
        import live_caps as LC
        tp, _all = LC.split(pair, picks) if pair else (picks, picks)
        cols = [KICK, MATCH, team, labels, ("Contract", lambda p: p.get("title") or ""),
                ("Side", lambda p: str(p.get("side") or "").upper()), PRICE, RESULT] + ([leg_col(pair)] if pair and len(tp) != len(picks) else [])
        r = row(src, sport, f"{key} · {leagues} · {meta['label']}", market, pick_record(tp), details,
                prod=key in TRP.PAIRS, pair=pair,
                open_n=sum(p.get("status") == "open" for p in tp),
                gone=((gone.get("line") or f"Retired {gone['on']}: {gone['reason']}.") if gone else None),
                entries=entries_table(picks, cols),
                legs_html=legs_table(pick_record(tp), pick_record(picks)) if len(tp) != len(picks) else "")
        (gone_rows if gone else live).append(r)
        if key not in TRP.PAIRS:
            for p in picks:
                q = pick_quote(src, sport, p, f"{p.get('team') or ''} to score {goals}+",
                               title=TRP.kalshi_title(p))
                if q:
                    quotes.append(dict(q, team=p.get("team"), opponent=p.get("opponent")))
        if key == "T1":                         # T1's paper siblings sit right under it (2026-11-06)
            for sk in TR.SIBLINGS:
                r2, q2 = sibling_row(sk, state)
                live.append(r2)
                quotes += q2
            try:                                # T1-M's 1.5x sell readout, observation only (2026-11-08)
                import t1m_sell15_build
                live.append(t1m_sell15_build.row())
            except Exception as exc:            # noqa: BLE001
                print(f"soccer_lanes: the T1-M 1.5x sell readout failed: {type(exc).__name__}: {exc}")
    return live, gone_rows, quotes


def _sibling_record(picks, since):
    """Settled, won, priced and ROI after fees: the record table in a sibling's fold (its first cell, the record's
    start, is the card title on a phone)."""
    a = pick_record(picks)
    roi = "—" if a["roi_fee"] is None else f'{a["roi_fee"] * 100:+.1f}%'.replace("-", "−")
    open_n = sum(p.get("status") == "open" for p in picks)
    heads = ("Settled", "Won", "Priced to win", "ROI after fees", "Open")
    cells = (a["n"] + a["n_price"], a["won"], f'{a["expected"]:.1f}', roi, open_n)
    return ('<div class="tbl"><table><thead><tr><th>Record from</th>' + "".join(f'<th class="num">{h}</th>' for h in heads)
            + f'</tr></thead><tbody><tr><td data-l="Record from">{esc(since)}</td>'
            + "".join(f'<td class="num" data-l="{h}">{esc(c)}</td>' for h, c in zip(heads, cells))
            + '</tr></tbody></table></div>')


def sibling_row(key, state):
    """T1-H or T1-M (soccer_team_rules.SIBLINGS): one row, its fold = entry, exit, record table, in-sample note
    (folded), entries. Sandbox paper, fresh record from its first entry, one entry a match."""
    import soccer_team_rules as TR
    meta = TR.SIBLINGS[key]
    lane = (state.get("rules", {}).get(key) or {})
    picks = lane.get("picks") or []
    leagues = ", ".join(SHORT.get(x, x) for x in TR.RULES["T1"]["leagues"])
    team = meta["market"] == "team"
    src, sport = f"st_{key.lower()}", ("soccer_team2" if team else "soccer_u35")
    entry_line = ("On a T1 match (own O+D− v opp O+D−), 90–20 min before kickoff: buy the home team's 2+ YES at the ask, "
                  "spread 5c or less, 3–97c" if team else
                  "On a T1 match, 90–20 min before kickoff: buy the match over 3.5 YES at the ask, spread 5c or less, 3–97c")
    skips = lane.get("skips") or {}
    last_skip = max(skips.values(), key=lambda x: x["at"]) if skips else None
    details = (params_html([("Entry", entry_line), ("Exit", "Held to Kalshi's own settlement; 7% fee"),
                            ("Leagues", leagues),
                            ("Count", f"One entry a match · fresh record from {meta['registered']} · review at 10 settled, decide at 30"),
                            ("Skipped", f"{len(skips)} match{'' if len(skips) == 1 else 'es'}, last: {last_skip['match']}, "
                                        f"{last_skip['reason']}" if last_skip else "")])
               + _sibling_record(picks, meta["registered"])
               + '<details class="section-disclosure"><summary><b>In-sample</b><span>why this lane</span></summary>'
               f'<p class="sm mut">{esc(meta["evidence"][0].upper() + meta["evidence"][1:])}. Read on T1\'s own entries, so in-sample; '
               'this lane is judged on its own forward record only.</p></details>')
    side = ("Side", lambda p: str(p.get("side") or "").upper())
    contract = ("Contract", lambda p: p.get("title") or "")
    cols = ([KICK, MATCH, ("Team", lambda p: p.get("team") or ""), contract, PRICE, RESULT] if team
            else [KICK, MATCH, contract, side, PRICE, RESULT])
    market = "Home 2+" if team else "Over 3.5"
    import live_caps as LC
    import soccer_team_rules_production as TRP
    prod = key in TRP.PAIRS                      # in Production since 2026-11-08 (Olu): its record is the tradeable picks since then
    pair = f"{src}|{sport}" if prod else None
    tp = LC.split(pair, picks)[0] if prod else picks
    if prod:
        details = (params_html([("History", f"Production since {TRP.MOVED[key]} (moved by hand); paper keeps running in the Sandbox")]) + details)
    if key == "T1M" and not prod:                # back in the Sandbox 2026-11-12 (Olu); the whole paper record stays here
        details = (params_html([("History", f"Production {TRP.T1M_PULLED[0]} to {TRP.T1M_PULLED[1]}, back in the Sandbox (paper, whole record kept)")]) + details)
    if key == "T1M":                             # the 1.5x sell readout on the same entries (2026-11-08), observation only
        try:
            import t1m_sell15_build
            details += t1m_sell15_build.fold_html()
        except Exception as exc:                 # noqa: BLE001
            print(f"soccer_lanes: the T1-M 1.5x sell readout fold failed: {type(exc).__name__}: {exc}")
    r = row(src, sport, f"{meta['name']} · {meta['label']}", market, pick_record(tp), details, prod=prod, pair=pair,
            open_n=sum(p.get("status") == "open" for p in tp), entries=entries_table(picks, cols))
    r["after"] = "st_t1"                         # shown right under T1 in the rules table
    text = (lambda p: f"{p.get('team') or ''} to score 2+") if team else (lambda p: "over 3.5 goals")
    quotes = []
    for p in ([] if prod else picks):            # a Production pair's quotes come from the adapter (soccer_team_rules_production)
        q = pick_quote(src, sport, p, text(p), title=_team_title(p) if team else None)
        if q:
            quotes.append(dict(q, team=p.get("team"), opponent=p.get("opponent")) if team else q)
    return r, quotes


def _team_title(p):
    import soccer_team_rules_production as TRP
    return TRP.kalshi_title(p)


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
                               ("History", " · ".join(hist))]) + shadow_html(key)
        r = row(f"sa_o15_{key.lower()}", "soccer_o15", f"{meta['league']} over 1.5 · every match", "Over 1.5", pick_record(picks),
                details, open_n=sum(p.get("status") == "open" for p in picks),
                gone=(f"Retired {gone['on']}: {gone['reason']}." if gone else None),
                entries=entries_table(picks, [KICK, MATCH, PRICE, RESULT]))
        (gone_rows if gone else live).append(r)
    return live, gone_rows


def btts_sa_rows(state=None):
    """Brazil and Argentina BTTS YES (btts_sa.py, 2026-11-16): both leagues, each league, and the BTTS NO control. Percentages only."""
    import btts_sa as BS
    state = state if state is not None else (BS.load() if os.path.exists(BS.PATH) else {"rules": {}})
    allp = [p for lane in (state.get("rules") or {}).values() for p in lane.get("picks") or []]
    pct = ("Result", lambda p: _res_pct(p))
    live = []
    for key, label, keep in BS.ROWS:
        picks = [p for p in allp if keep(p)]
        control = key == "no"
        details = params_html([
            ("Leagues", "Brazil Serie A and Argentina Primera" if key in ("all", "no") else label),
            ("Rule", ("BTTS NO at the ask" if control else "BTTS YES at the ask") + ", every match, no selection, 20 to 90 minutes "
                     "before kickoff, spread 5c or less, after fees"),
            ("Pre-registered", BS.PREREG),
            ("Research", "The control: the opposite side on the same matches" if control else
             f"A lead, not a tested rule: {BS.EVIDENCE}"),
            ("Record", "Paper at the Kalshi price, 7% fee. A fresh record from the first entry"),
        ])
        live.append(row(f"btts_sa_{key}", "soccer_btts", f"{label} · BTTS {'NO' if control else 'YES'} · every match",
                        "BTTS", pick_record(picks), details, open_n=sum(p.get("status") == "open" for p in picks),
                        entries=entries_table(picks, [KICK, MATCH, PRICE, pct])))
        if key != "all":
            live[-1]["after"] = "btts_sa_all"          # the league rows and the control sit right under the combined row
    return live, []


def _cells(heads, cells):
    """A source-rule table row: the first (label) cell is plain text that wraps, the rest are numbers."""
    return "".join(f'<td{"" if i == 0 else " class=" + chr(34) + "num" + chr(34)} data-l="{h}">{esc(c)}</td>' for i, (h, c) in enumerate(zip(heads, cells)))


# ------------------------------------------------------------------ the shadows as lane cards (2026-11-22, Olu: "I want to see them like I see the other ones")
# Four Sandbox cards: T1 2H BTTS YES, T1 half-time sell, A7 2H BTTS YES, A7 half-time sell. Paper. The Argentina and Brasileirao shadows are held back
# (their source rows were retired Nov 3 and cannot fire). A card never changes its source lane's record.
SHADOW_CARDS = (
    ("T1", "btts", "shadow_t1_2h_btts", "T1 2H BTTS YES (shadow)", "soccer_btts", "2H BTTS YES"),
    ("T1", "ht", "shadow_t1_ht_sell", "T1 half-time sell (shadow)", "soccer_team1", "Half-time sell"),
    ("A7", "btts", "shadow_a7_2h_btts", "A7 2H BTTS YES (shadow)", "soccer_btts", "2H BTTS YES"),
    ("A7", "ht", "shadow_a7_ht_sell", "A7 half-time sell (shadow)", "soccer_u35", "Half-time sell"),
)
SHADOW_SOURCE = {"T1": "T1 (team 1+ form, the home or away team to score)", "A7": "A7 (Champions League over 3.5 goals)"}


def _shadow_picks(st, lane, kind):
    """The shadow's entries as pick-shaped dicts: status won / lost / no_result / open / no_quote / pending / unavailable, profit in percent of a $100 stake."""
    out = []
    if kind == "btts":
        for r in st["btts"].values():
            if r["lane"] != lane:
                continue
            if not r.get("quote"):
                out.append(dict(id=r["event"], match=r["match"], start=r["start"], price=None, status="no_quote", profit=None, detail="no quote"))
            else:
                out.append(dict(id=r["event"], match=r["match"], start=r["start"], price=r["price"], status=r["status"], profit=r.get("profit"),
                                detail="held to settlement"))
        return out
    for r in st["ht"].values():
        if r["lane"] != lane:
            continue
        if r["status"] == "pending":
            out.append(dict(id=r["pick"], match=r["match"], start=r["start"], price=r["price"], status="pending", profit=None, detail="half-time not read yet"))
        elif r["status"] == "unavailable":
            out.append(dict(id=r["pick"], match=r["match"], start=r["start"], price=r["price"], status="unavailable", profit=None, detail="no half-time data"))
        else:
            act = r.get("action")
            detail = (f'sold at {float(r["bid"]) * 100:.0f}c at half-time ({r.get("score")})' if act == "sell"
                      else f'no bid at half-time ({r.get("score")}): held' if act == "no_bid" else f'held ({r.get("score")})')
            prof = r.get("profit")
            status = ("won" if prof > 0 else "lost") if prof is not None else "open"
            out.append(dict(id=r["pick"], match=r["match"], start=r["start"], price=r["price"], status=status, profit=prof, detail=detail))
    return out


def shadow_cards(states=None):
    """[dict(name, sport, label, market, lane, kind, picks, a, hold, in_sample)] for the four cards. Never raises: an unreadable ledger gives none."""
    out = []
    try:
        import shadows as SH
        for lane, kind, name, label, sport, market in SHADOW_CARDS:
            meta = SH.LANES[lane]
            st = (states or {}).get(meta["group"]) or SH.load(meta["group"])
            picks = _shadow_picks(st, lane, kind)
            hold = None
            if kind == "ht":
                hold = SH.ht_stats(st, lane, SH.source_picks(lane))["hold_ret"]
            out.append(dict(name=name, sport=sport, label=label, market=market, lane=lane, kind=kind, picks=picks, a=pick_record(picks), hold=hold,
                            in_sample=meta["in_sample"]["btts" if kind == "btts" else "ht"], no_quote=sum(p["status"] == "no_quote" for p in picks)))
    except Exception as exc:                                    # noqa: BLE001
        print(f"soccer_lanes: shadow cards failed: {type(exc).__name__}: {exc}")
    return out


def _shadow_entries(c):
    picks = c["picks"]
    price = ("Price", lambda p: "no quote" if p["status"] == "no_quote" else (f'{float(p["price"]) * 100:.0f}c' if p.get("price") is not None else ""))
    res = ("Result", lambda p: {"no_quote": "no quote", "pending": "waiting", "unavailable": "no half-time data"}.get(p["status"], _res_pct(p)))
    cols = [KICK, MATCH, price, ("What happened", lambda p: p.get("detail") or ""), res]
    newest = sorted(picks, key=lambda p: p.get("start") or "", reverse=True)[:5]
    if newest:
        recent = ('<div class="sp-recent"><ul class="sm">' + "".join(
            f'<li>{esc(fmt.when(p["start"]) if p.get("start") else "")} · {esc(p["match"])} · {esc(price[1](p))} · {esc(res[1](p))}</li>' for p in newest)
            + "</ul></div>")
    else:
        recent = '<p class="sm mut">No pick yet.</p>'
    return recent + entries_table(picks, cols)


def shadow_rows(states=None):
    """The four shadow cards as Sandbox rows of the Soccer page (the template's own row shape)."""
    import shadows as SH
    p1 = lambda x: "—" if x is None else f"{x * 100:.1f}%"                         # noqa: E731
    out = []
    for c in shadow_cards(states):
        lane, kind = c["lane"], c["kind"]
        meta = SH.LANES[lane]
        words = (("At the entry minute, the YES ask on the match's " + ("second-half" if meta["kind"] == "2h" else "full-game") + " both-teams-to-score market "
                  "(spread 3c or less, else no quote), held to settlement; one a match.") if kind == "btts" else
                 ("At half-time, " + ("if the backed team has not scored, sell at its team-total YES bid, else hold" if meta["ht"] == "team"
                                      else "if the match is 0-0, sell at the over's YES bid, else hold") + "; no bid counts as hold. Half-time is read from ESPN's match "
                  "events and Kalshi's one-minute bid. Counted as the sell (or the held result) against the source entry's price."))
        params = [("Source lane", SHADOW_SOURCE[lane]),
                  ("Shadow", words),
                  ("Record", "Paper, 7% fee, Kalshi's own settlement, fresh from 2026-11-21. It does not change the source lane's record or its Production status. "
                             "Review at 10 settled, decide at 30."),
                  ("In-sample, not counted", c["in_sample"] or "no figure")]
        if kind == "ht":
            params.append(("Same entries held", f'{("—" if c["hold"] is None else f"{c["hold"] * 100:+.1f}%".replace("-", "−"))} (the source lane\'s own result on the entries checked)'))
        else:
            params.append(("No quote", f'{c["no_quote"]} match{"es" if c["no_quote"] != 1 else ""} had no tradable quote at the entry minute and are shown as no quote'))
        r = row(c["name"], c["sport"], c["label"], c["market"], c["a"], params_html(params),
                open_n=sum(p["status"] in ("open", "pending") for p in c["picks"]), anchor=c["name"], entries=_shadow_entries(c),
                note=f'A shadow of {lane}: it does not change {lane}\'s record.')
        r["own"]["entries_only"] = True
        out.append(r)
    return out


def shadows_index_html():
    """The Sandbox page's index of the shadow cards: one row each, linking to its card on the Soccer page."""
    cs = shadow_cards()
    if not cs:
        return ""
    pr = lambda x: "—" if x is None else f"{x * 100:+.1f}%".replace("-", "−")     # noqa: E731
    body = ""
    for c in cs:
        a = c["a"]
        seen = len(c["picks"])
        status = f'{a["n"]} of 30 settled · paper, not counted'
        body += (f'<tr data-lane="{esc(c["name"])}"><td><b>{esc(c["label"])}</b></td><td><a href="./soccer.html#{esc(c["name"])}">Soccer</a></td>'
                 f'<td class="num">{seen}</td><td class="num">{a["won"]}-{a["n"] - a["won"]}</td><td class="num">{esc(pr(a["roi_fee"]))}</td><td>{esc(status)}</td></tr>')
    return ('<section id="shadows-index"><h2>Shadows</h2><p class="shell-kicker">Half-time sells and second-half BTTS on T1 and A7 · each card is on the Soccer page '
            'with its entries · never changes its source lane\'s record · paper · not in Production</p>'
            '<div class="tbl"><table class="shadow-index"><tr><th>Shadow</th><th>Page</th><th class="num">Entries</th><th class="num">Won-lost</th>'
            '<th class="num">Return after fees</th><th>Status</th></tr>' + body + '</table></div></section>')


def flipped_rows(state=None):
    """Flipped Unders (flipped_unders.py, 2026-11-21): the over side of C5/C6/C7/B4's selections, paper. Percentages only."""
    import flipped_unders as FU
    state = state if state is not None else (FU.load() if os.path.exists(FU.PATH) else {"rules": {"FU": {"picks": []}}})
    picks = (state.get("rules", {}).get("FU") or {}).get("picks") or []
    p1 = lambda x: "—" if x is None else f"{x * 100:.1f}%"
    pr = lambda x: "—" if x is None else f"{x * 100:+.1f}%".replace("-", "−")
    heads = ("Source rule", "Entries", "Won-lost", "Hit rate", "Average YES price", "Break-even after fees", "Return after fees")
    body = ""
    for k, r in FU.by_source(picks).items():
        cells = (k, r["entries"], f'{r["won"]}-{r["lost"]}', p1(r["hit"]), p1(r["avg_price"]), p1(r["break_even"]), pr(r["ret"]))
        body += "<tr>" + _cells(heads, cells) + "</tr>"
    ins = FU.IN_SAMPLE
    w = sum(v[0] for v in ins["by_rule"].values())
    l = sum(v[1] for v in ins["by_rule"].values())
    cells = (f'In-sample, not counted ({ins["window"]})', w + l, f"{w}-{l}", p1(w / (w + l)), "—", "—", ins["return"])
    body += '<tr class="mut">' + _cells(heads, cells) + "</tr>"
    table = ('<div class="tbl"><table><thead><tr>' + "".join(f"<th>{h}</th>" for h in heads) + f"</tr></thead><tbody>{body}</tbody></table></div>")
    details = params_html([
        ("Leagues", "Saudi Pro League, Ligue 1, Turkish Super Lig, Scottish Premiership"),
        ("Rule", "When label rule C5 (Saudi u2.5), C6 (Ligue 1 u2.5), C7 (Super Lig u2.5) or B4 (Scottish u3.5) selects a match by its label "
                 "filter and its own under price band (checked on the under's NO side at entry), 20 to 90 minutes before kickoff, take the opposite "
                 "side: YES on the over at that rule's line, at the YES ask, held to settlement. One entry a match; two source rules on one match are logged once with both listed. A retired source rule keeps "
                 "its selector running for this lane only."),
        ("Research", "On the four under rules' past picks the unders went 1-14 and the overs 14-1, about +80% after fees. A hindsight sample "
                     "from rules kept because they failed: it is not counted."),
        ("Record", "Paper at the Kalshi price, 7% fee, fresh from 2026-11-21. Review at 10 settled, decide at 30."),
    ]) + table
    r = row("flipped_unders", "soccer_o25", "Flipped Unders · C5 C6 C7 B4 selections · over YES", "Over 2.5 / 3.5", pick_record(picks), details,
            open_n=sum(p.get("status") == "open" for p in picks),
            entries=entries_table(picks, [KICK, MATCH, ("Source rules", lambda p: ", ".join(p.get("sources") or [])), ("Line", lambda p: f'Over {p["line"]:g}'),
                                          PRICE, ("Result", lambda p: _res_pct(p))]))
    r["top"] = True
    return [r]


def piggyback_rows(states=None):
    """Favourite 1-0 and Quiet First Half (under_piggyback.py, 2026-11-21): paper lanes on A5/A6/C8's selections. Percentages only."""
    import under_piggyback as UP
    import flipped_unders as FU
    p1 = lambda x: "—" if x is None else f"{x * 100:.1f}%"
    pr = lambda x: "—" if x is None else f"{x * 100:+.1f}%".replace("-", "−")
    base_heads = ("Source rule", "Entries", "Won-lost", "Hit rate", "Average price paid", "Break-even after fees", "Return after fees")
    out = []

    def table(hd, rows, ins_cells):
        body = "".join("<tr>" + _cells(hd, c) + "</tr>" for c in rows) + '<tr class="mut">' + _cells(hd, ins_cells) + "</tr>"
        return ('<div class="tbl"><table><thead><tr>' + "".join(f"<th>{h}</th>" for h in hd) + f"</tr></thead><tbody>{body}</tbody></table></div>")

    for key, meta in UP.LANES.items():
        st = (states or {}).get(key) or (UP.load(key) if os.path.exists(UP.path(key)) else {"rules": {"PB": {"picks": []}}})
        picks = (st.get("rules", {}).get("PB") or {}).get("picks") or []
        ins = meta["in_sample"]
        rows, srows = [], []
        for k, r in UP.by_source(picks).items():
            rows.append((k, r["entries"], f'{r["won"]}-{r["lost"]}', p1(r["hit"]), p1(r["avg_price"]), p1(r["break_even"]), pr(r["ret"])))
            mine = [p for p in picks if k in (p.get("sources") or [])]
            if key == "fav_one_nil":
                n_s, sold, sret = UP.shadow_record(mine)
                srows.append((k, f"{sold} of {n_s}" if n_s else "—", pr(sret)))
            else:
                u = UP.u15_record(mine)
                srows.append((k, f'{u["won"]}-{u["lost"]}' + (f' ({u["no_quote"]} no quote)' if u["no_quote"] else ""), p1(u["avg_price"]), pr(u["ret"])))
        table_html = table(base_heads, rows, ("In-sample, not counted", ins["entries"], f'{ins["won"]}-{ins["lost"]}', p1(ins["won"] / ins["entries"]), ins["price"], "—", ins["ret"]))
        if key == "fav_one_nil":
            table_html += "<h4>Sell at 2x (shadow)</h4>" + table(("Source rule", "Sold at 2x", "2x return after fees"), srows, ("In-sample, not counted", f'{ins["sold"]} of {ins["entries"]}', ins["shadow_ret"]))
        else:
            u = ins["u15"]
            table_html += "<h4>1H under 1.5 (shadow)</h4>" + table(("Source rule", "Won-lost", "Average price", "Return after fees"), srows, ("In-sample, not counted", f'{u["won"]}-{u["lost"]}', u["price"], u["ret"]))
        details = params_html([
            ("Leagues", "UEFA Nations League and Premier League"),
            ("Rule", "When under rule A5 (Nations League u3.5), A6 (Premier League u2.5) or C8 (Nations League u2.5) would pick a match (its label "
                     "filter and its own under price band on the NO side at entry), log once, 20 to 90 minutes before kickoff, with the source rules listed. "
                     + meta["words"] + ", held to settlement."
                     + (" The favourite is the higher-priced team on the game market; no entry if the two are within 2c; the spread must be 3c or less."
                        if key == "fav_one_nil" else " Spread 3c or less; no entry when the match has no first-half BTTS market.")),
            ("Research", f'A hindsight sample from the proved under rules, not counted: {ins["note"]}.'),
            ("Record", "Paper at the Kalshi price, 7% fee, Kalshi's own settlement, fresh from 2026-11-21. Review at 10 settled, decide at 30."),
            ] + ([("Shadow", "First-half under 1.5 at the same minute: the NO ask on the 1H total over 1.5 (spread 3c or less, else no quote), "
                             "held to settlement, shown beside the BTTS NO record, never the headline.")] if key == "quiet_first_half" else [])
              + ([("Shadow", "A sell at 2x the entry ask (capped at 99c) shown beside the hold record, never the headline: sold when a trade print after "
                             "kickoff reaches it, else the settled result; taker fee on both legs.")] if key == "fav_one_nil" else [])) + table_html
        cols = [KICK, MATCH, ("Source rules", lambda p: ", ".join(p.get("sources") or [])), ("Side", lambda p: str(p.get("side") or "").upper()), PRICE,
                ("Result", lambda p: _res_pct(p))]
        if key == "fav_one_nil":
            cols.append(("2x shadow", lambda p: ("sold at 2x" if (p.get("shadow") or {}).get("sold") else "not sold") if p.get("shadow") else ""))
        out.append(row(key, "soccer_o25", f"{meta['name']} · A5 A6 C8 selections", "Correct score" if key == "fav_one_nil" else "1H BTTS",
                       pick_record(picks), details, open_n=sum(p.get("status") == "open" for p in picks), entries=entries_table(picks, cols)))
        out[-1]["top"] = True
    return out


def _res_pct(p):
    res = {"open": "open", "won": "won", "lost": "lost", "no_result": "no result"}.get(p.get("status"), p.get("status"))
    return res + (f" · {float(p['profit']):+.0f}%" if p.get("profit") is not None else "")


# ------------------------------------------------------------------ the African qualifiers goals check (africa_goals.py)
# 2026-11-16 (Olu): the every-match rows are split into legs. Their records stay on the page.
AFRICA_RETIRED = "Retired Nov 16 by Olu: split into Production legs / v2."
def _pct(x, digits=1):
    return "—" if x is None else f"{x * 100:+.{digits}f}%".replace("-", "−")


def _africa_windows(picks):
    """[(label, picks)] by international window: match days more than 10 days apart start a new one."""
    import datetime as dt
    days = sorted({str(p.get("start") or "")[:10] for p in picks if p.get("start")})
    groups = []
    for d in days:
        day = dt.date.fromisoformat(d)
        if groups and (day - groups[-1][-1]).days <= 10:
            groups[-1].append(day)
        else:
            groups.append([day])
    out = []
    for g in groups:
        label = f"{g[0]:%b} {g[0].day}" + (f" to {g[-1]:%b} {g[-1].day}" if g[-1] != g[0] else "") + f" {g[-1].year}"
        keys = {x.isoformat() for x in g}
        out.append((label, [p for p in picks if str(p.get("start") or "")[:10] in keys]))
    return out


def _africa_window_table(picks):
    import africa_goals as AG
    heads = ("Settled", "Match days", "Won", "Price paid", "Points", "Return after fees")
    body = ""
    for label, ps in _africa_windows(picks):
        a = AG.record(ps)
        n = a["n"]
        cells = (n, a["days"], f"{a['won'] / n * 100:.1f}%" if n else "—", f"{a['price'] * 100:.1f}c" if n else "—",
                 f"{a['excess'] * 100:+.1f}".replace("-", "−") if n else "—", _pct(a["roi_fee"]) if n else "—")
        body += (f'<tr><td data-l="Window">{esc(label)}</td>'
                 + _cells(heads, cells) + "</tr>")
    if not body:
        return ""
    return ('<div class="tbl"><table><thead><tr><th>Window</th>' + "".join(f'<th class="num">{h}</th>' for h in heads)
            + f'</tr></thead><tbody>{body}</tbody></table></div>'
            '<p class="sm mut">Points: the share of bets won minus the price paid.</p>')


def africa_rows(state=None):
    """The African qualifiers goals check: one row per bet type and the combined row, pinned near the top of the Sandbox
    list. An observation lane (a pre-registered forward check): never in Production, so every row is a Sandbox row."""
    import africa_goals as AG
    state = state if state is not None else AG.load()

    def result(p):
        res = {"open": "open", "won": "won", "lost": "lost", "no_result": "no result", "no_fill": "no fill"}.get(p.get("status"), "")
        return res + (f" · {_pct(p['profit'] / 100)}" if p.get("profit") is not None else "")

    cols = [KICK, MATCH, ("Bet", lambda p: (f"{p['team']} to score" if p.get("team") else AG.ALL_ROWS[p["rule"]]["label"])),
            PRICE, ("Entry", lambda p: "backfilled" if p.get("backfilled") else "logged before kickoff"), ("Result", result)]
    shared = [("Matches", "Every AFCON qualifier Kalshi lists. No selection"),
              ("Entry", "The ask on the hourly quote three hours before the ESPN kickoff. A bet logged after its kickoff is marked backfilled"),
              ("Fills and fees", "The ask counts unless trade prints refute it; a refuted entry is left out. Exchange taker fee"),
              ("Score", "A match day counts as one outcome"),
              ("Stage", "Observation only. A pre-registered forward check, never in Production"),
              # In words, not the file path: a long unbreakable path widened the page on a phone (test_site_layout).
              ("Pre-registered", "Nov 12 2026, before the first match of the window was played")]
    note = "Observation lane: a pre-registered forward check on one lead. Paper, never in Production."
    rows = []
    for key, meta in AG.ROWS.items():
        picks = AG.picks_of(state, key)
        details = (params_html([("Bet", f"{meta['label']}, at the ask, held to settlement"),
                                ("The lead", f"September window: {meta['lead']}"),
                                ("Holds if", f"On the Nov 12 to 17 window it {meta['held']}")] + shared)
                   + _africa_window_table(picks))
        r = row(f"africa_goals_{key.lower()}", meta["sport"], f"African qualifiers · {meta['label']} · every match", meta["market"],
                AG.record(picks), details, open_n=sum(p.get("status") == "open" for p in picks),
                entries=entries_table(picks, cols), kind="Observation", note=note, anchor=f"africa-goals-{key.lower()}")
        r["pin"], r["after"] = True, "africa_goals_all"      # the three bet types sit right under the combined row
        r["gone"], r["v"], r["scope"] = AFRICA_RETIRED, "retired", "intl"
        rows.append(r)
    every = AG.picks_of(state)
    details = (params_html([("Bet", "The three bets below, pooled: NO on over 3.5, YES on over 1.5, YES on each side to score"),
                            ("Holds if", "All three conditions hold on the Nov 12 to 17 window. If one fails the lead is dropped")] + shared)
               + _africa_window_table(every))
    r = row("africa_goals_all", "soccer_goals_intl", "African qualifiers · all three goal bets", "Goals", AG.record(every), details,
            open_n=sum(p.get("status") == "open" for p in every), entries=entries_table(every, cols), kind="Observation",
            note=note, anchor="africa-goals")
    r["pin"] = True
    r["gone"], r["v"], r["scope"] = AFRICA_RETIRED, "retired", "intl"
    # The BTTS row, added Nov 13 2026 after the window opened (africa_goals.BTTS). Its own row, apart from the pooled one: it counts only
    # kickoffs after 18:30 UTC Nov 13, and the window's earlier matches are shown here, flagged, and left out of every figure.
    bt = AG.picks_of(state, "BTTS")
    inc = AG.counted(bt)
    bcols = cols[:4] + [("Counts", lambda p: "counts" if p.get("counted", True) else "shown, not counted (kicked off before 18:30 UTC Nov 13)")] + cols[4:]
    bshared = [x for x in shared if x[0] != "Pre-registered"] + [
        ("Pre-registered", "Addendum of Nov 13 2026, written before 18:30 UTC. The three rows' rules are unchanged"),
        ("Counts", "Only matches that kick off after 18:30 UTC on Nov 13 2026. Earlier matches of the window are shown and flagged, never counted"),
        ("Not tracked", "First-half both teams to score")]
    bdet = (params_html([("Bet", f"{AG.BTTS['label']}, at the ask, held to settlement"), ("Added", AG.BTTS_LABEL),
                         ("The lead", f"September window: {AG.BTTS['lead']}. The same lean seen through another market, not new evidence"),
                         ("Holds if", "On the counted matches it wins more often than its price, by 3 points or more. Under 10 counted matches it is too few to say, "
                                      "and is read again on the next African window")] + bshared)
            + _africa_window_table(inc))
    import africa_goals_production as AFP
    src, sport, name = AFP.PAIRS["BTTS"]
    bdet = (params_html([("History", "Added Nov 13 2026 as an every-match observation row; a Production leg Nov 16 to Nov 17 2026 (Olu); back in the Sandbox Nov 17 until it "
                                     "has real team and matchup filters, since it is a blind selection. The record continues, with no reset")]) + bdet)
    rb = row(src, sport, f"{name} · every match", AG.BTTS["market"], AG.record(bt), bdet,
             open_n=sum(p.get("status") == "open" for p in inc), entries=entries_table(bt, bcols), kind="Rule",
             note="Sandbox paper. Post-hoc split of the Nov 12 to 14 window; nothing here is proof.", anchor="africa-goals-btts")
    rb["pin"], rb["scope"] = True, "intl"
    rows.append(rb)
    rows += africa_leg_rows(state, cols)
    for x in [r] + rows:            # the fold lists the lane's own entries; it has no tracker picks to show above them
        x["own"]["entries_only"] = True
    return [r] + rows


def africa_leg_rows(state, cols):
    """The legs split out of the every-match rows (2026-11-16, Olu): the underdog leg (Sandbox again since 2026-11-17), the Sandbox legs and the two control rows.
    Subsets of the ledger's own entries (africa_goals.leg_picks), judged the same way. Percentages only."""
    import africa_goals as AG
    import africa_goals_production as AFP
    src, sport, name = AFP.PAIRS["DOG"]
    both = "Observation rows split from the every-match rows; the entry and the price are unchanged"
    pre = ("Pre-registered", "Nov 16 2026, before any new match: post hoc, found on the Nov 12 to 14 window after it was seen")
    spec = [
        ("DOG", src, sport, name, "Team 1+", False, None, "Rule",
         [("Bet", "YES on the underdog to score: the side whose to-score YES ask is under 60c, at the ask, held to settlement"),
          ("Evidence", "Post hoc, on the Nov 12 to 14 window: 14 of 21 at an average price of 39c. September: each side to score was 9.7 points underpriced on 91 sides"),
          ("Stage", "A Production leg Nov 16 to Nov 17 2026 (Olu); back in the Sandbox Nov 17 until it has real team and matchup filters, since it is a blind "
                    "selection. The record continues, with no reset"), pre]),
        ("U35_80", "afq_u35_80", "soccer_u35_intl", "African qualifiers · NO on over 3.5 when the NO ask is 80c or more", "Under 3.5", False, None, "Rule",
         [("Bet", "NO on over 3.5 goals only when the NO ask is 80c or more, at the ask, held to settlement"),
          ("Evidence", "Post hoc, on the Nov 12 to 14 window: 7 of 7. In the September window the same filter went 22 of 29 at 83c, about 10% under break-even"),
          ("Stage", "Sandbox paper, not in Production: the two windows disagree"), pre]),
        ("O15_V2", "afq_o15_v2", "soccer_o15_intl", "African qualifiers · YES on over 1.5 when the favourite's to-score ask is 90c or more", "Over 1.5", False, None, "Rule",
         [("Bet", "YES on over 1.5 goals only when the favourite's to-score YES ask is 90c or more (a clear mismatch), at the ask, held to settlement"),
          ("In sample", "The same rule on the Nov 12 to 14 matches: see the second line below. Shown, never counted"),
          ("Record", "Fresh: only matches that kick off on or after Nov 16 2026 count. The every-match over 1.5 row was +3.7%"), pre]),
        ("CTRL_FAV", "afq_ctrl_fav", "soccer_team1_intl", "African qualifiers · control: the favourite to score at 85c or more", "Team 1+", False, None, "Baseline",
         [("Bet", "YES on the favourite to score when its ask is 85c or more. A baseline for the underdog leg, not a lane"),
          ("Evidence", "Nov 12 to 14: 14 of 15, about break-even at that price"), pre]),
        ("CTRL_U35", "afq_ctrl_u35", "soccer_u35_intl", "African qualifiers · control: NO on over 3.5 when the NO ask is under 80c", "Under 3.5", False, None, "Baseline",
         [("Bet", "NO on over 3.5 goals when the NO ask is under 80c. The other side of the 80c split; a baseline, not a lane"), pre]),
    ]
    out = []
    for leg, name_id, sp, label, market, prod, pair, kind, params in spec:
        picks = AG.leg_picks(state, leg)
        extra = ""
        if leg == "O15_V2":
            ins = AG.in_sample_picks(state)
            a = AG.record(ins)
            extra = (f'<p class="sm mut">In sample, Nov 12 to 14 (not counted): {a["won"]} of {a["n"]} won, {_pct(a["roi_fee"])} after fees.</p>'
                     + _africa_window_table(ins))
            picks = [p for p in ins if str(p.get("start") or "") >= AG.V2_FROM[:10]]
        details = params_html([("Rule", both)] + params + [("Matches", "Every AFCON qualifier Kalshi lists"),
                                                           ("Entry", "The ask on the hourly quote three hours before the ESPN kickoff")]) + _africa_window_table(picks) + extra
        r = row(name_id, sp, label, market, AG.record(picks), details, prod=prod, pair=pair, open_n=sum(p.get("status") == "open" for p in picks),
                entries=entries_table(picks, cols), kind=kind, note=both + ".", anchor=f"africa-{leg.lower().replace('_', '-')}")
        r["pin"], r["scope"] = True, "intl"
        out.append(r)
    return out


# ------------------------------------------------------------------ the in-play lanes
def o35_row(state=None):
    import chaos_replay as CR
    import o35_cheap_no as O
    import o35_cheap_no_build as OB
    import o35_production as OP
    state = state if state is not None else (O.load() if os.path.exists(O.PATH) else O.load("/nonexistent"))
    entries = [e for e in state.get("entries") or [] if e.get("version") == O.VERSION]
    s = CR.stats([r for r in O.trade_rows(entries, field="honest") if r["variant"] == OB.HEAD])
    return row(OP.LANE, OP.SPORT, f"{O.LABEL}", "Under 3.5 · in-play",
               inplay_record(s["n"], s["won"], s["roi"], s["z"]), OB.panel(state), prod=False, pair=None, gone=O35_RETIRED["original"],
               anchor="cheap-side", kind="In-play",
               note=f"Record: v4 re-scored under the honesty rules, headline exit (bid {round(O.HEADLINE * 100)}c, sell at {O.HEAD_MULT:g}x).")


def o35_v5_row(state=None):
    import chaos_replay as CR
    import o35_cheap_no as O
    import o35_cheap_no_build as OB
    import o35_production as OP
    state = state if state is not None else (O.load() if os.path.exists(O.PATH) else O.load("/nonexistent"))
    es = [e for e in state.get("entries") or [] if e.get("night", "") >= O.SINCE_V5 and "v5" in e]
    s = CR.stats([r for r in O.trade_rows(es, field="v5") if r["variant"] == OB.HEAD])
    return row("o35_cheap_no_v5", OP.SPORT, O.V5_LABEL, "Under 3.5 · in-play",
               inplay_record(s["n"], s["won"], s["roi"], s["z"]), OB.v5_panel(state), prod=False, pair=None, gone=O35_RETIRED["v5"],
               anchor="o35-v5", kind="In-play", note="Record: the 10c bid cancelled at minute 80, sell at 4x, honest rules, fresh from 2026-11-06.")


# 2026-11-16 (Olu): the over 3.5 cheap NO is retired, all three rows (o35_cheap_no.RETIRED_ON stops new games; the rows and their records stay).
O35_RETIRED = {"original": "Retired Nov 16 by Olu: 52 bets, -17.6% after fees",
               "v5": "Retired Nov 16 by Olu: 23 bets, -32.2% after fees",
               "live": "Retired Nov 16 by Olu: 21 fills, -33.0% after fees"}
# The live run of o35, 2026-11-01 to 2026-11-06, kept as its own row (Olu, Nov 6: back to the Sandbox until it works properly).
O35_LIVE = dict(fills=21, sold=4, roi=-0.33, ended="2026-11-06")


def o35_live_row():
    import o35_production as OP
    L = O35_LIVE
    a = inplay_record(L["fills"], L["sold"], L["roi"], None)
    details = params_html([
        ("Run", f"Traded live on Kalshi from {OP.MOVED_ON} to {L['ended']} in a small fixed size; execution switched off {L['ended']}, the lane is paper only again."),
        ("Result", f"{L['fills']} fills, {L['sold']} sold at 40c, the rest held and lost: {L['roi'] * 100:+.0f}% after fees on the fills. Final, not updated."),
        ("Why it stopped", "Paper showed sells printing within a minute of the fill; live fills came 68 to 131 minutes in, behind the queue. "
                           "The paper lane is being re-scored under queue and latency rules before it returns."),
    ])
    return row("o35_cheap_no_wave_live", OP.SPORT, "Over 3.5 cheap NO · live run (ended)", "Under 3.5 · in-play", a, details,
               prod=False, pair=None, kind="In-play", note="The follower's own fills, closed.", gone=O35_RETIRED["live"])


def ere_draw_maker_row(state=None):
    """Eredivisie draw band, maker entry (ere_draw_maker.py, 2026-11-06): one Sandbox row right under ere_draw, its comparison
    with ere_draw's taker result inside the row's fold. The record is the settled fills since the lane began."""
    import ere_draw_maker as M
    import ere_draw_maker_build as MB
    state = state if state is not None else (M.load() if os.path.exists(M.PATH) else M.empty())
    r = row(M.LANE, "soccer", M.LABEL, "Match winner", M.record(state), MB.panel(state), prod=False, pair=None,
            anchor="ere-draw-maker", kind="Rule", note="Record: the settled fills, maker fee, held to settlement; beside ere_draw's taker result.")
    r["after"] = M.PARENT
    return r


def mls_tie_row(state=None):
    """MLS pre-match tie with a split 2x/3x sell (mls_tie_split.py, 2026-11-07): one Sandbox row. The record is the settled
    entries since the lane began, split exit, after fees."""
    import mls_tie_split as M
    import mls_tie_split_build as MB
    state = state if state is not None else M.load()
    s = M.summary(state.get("entries") or [])
    return row(M.LANE, "soccer", M.LABEL, "Match winner · Tie", inplay_record(s["n"], s["won"], s["roi"], s["z"]), MB.panel(state),
               prod=False, pair=None, anchor="mls-tie", kind="In-play",
               note="Record: the split sell (half at 2x, half at 3x) on the settled entries, taker in, maker out.")


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
        ("History", f"First Production run {TP.FIRST_RUN[0]} to {TP.FIRST_RUN[1]} (12 live fills, -9.4%), back in the Sandbox, and back in Production {TP.MOVED_ON} "
                    "(Olu) on the replay evidence: same rule, no change to the engine, the held-fill rule or the 55% bid."),
        ("Review", "Pre-registered: read once at 100 honest fills counted from Nov 20 2026. Retire if the honest return on those fills is zero or below. "
                   "Keep if above zero (a score of 2 is not required at 100). Also record the share of fills where the price did not fall a further 5c "
                   "within ten minutes: under 15% means the source of the profit has gone and the lane is reviewed again. "
                   "No league or price band is dropped or added before that read."),
    ])
    if TP.ENDED_ON:                          # back in the Sandbox: its own closed row, the live run as history
        details = params_html([
            ("Run", f"Traded live on Kalshi from {TP.FIRST_RUN[0]} to {TP.ENDED_ON} in a small fixed size; the feed names no match since {TP.ENDED_ON}, "
                    "so no new bid is opened. A position already held settles on its own."),
            ("Record", "The paper record that followed the follower's own decisions during the run, per counted fill; the research record is the Sandbox row Top-5 goalless dip, which keeps running."),
            ("History", "Out of Production Nov 16 (Olu): Sandbox research row z 0.05, newer half +0.3%; the 100-fill read continues on paper."),
        ])
        return row("top5_dip_live_run", TP.SPORT, "Top-5 goalless dip · live run (ended)", "Over 1.5 · in-play", a, details,
                   prod=False, pair=None, kind="In-play", note="The follower's own decisions, closed.")
    return row(TP.LANE, TP.SPORT, TP.NAME, "Over 1.5 · in-play", a, details, prod=True,
               pair=f"{TP.LANE}|{TP.SPORT}", kind="In-play")


def arg_live_row(live_ledger, now):
    """The top-5 goalless dip in Production (arg_dip_production, 2026-11-05): its record is the paper record that follows
    the follower's own decisions (arg_dip_live), counted per counted fill as the Production page counts it."""
    import arg_dip_production as TP
    qs = [q for q in TP.quotes(live_ledger or {}, {}) if q["status"] != "open"]
    n = len(qs)
    a = inplay_record(n, sum(q["status"] == "won" for q in qs), (sum(q["pnl"] for q in qs) / (100 * n)) if n else None, None)
    details = params_html([
        ("Rule", "An hour before kickoff the follower reads the YES ask P of the over 0.5 rung; from kickoff it rests one "
                 "post-only YES bid at 65% of P, a small fixed size a match; on a fill, a resting sell at P; an unsold "
                 "position is held to settlement. A bid that would cross the book is no entry. Never chases."),
        ("Leagues", "Argentine league"),
        ("Record", f"Production from {TP.MOVED_ON}, fresh: the paper record that follows the follower's own decisions. "
                   "The research record is the Sandbox row Argentina goalless dip."),
    ])
    return row(TP.LANE, TP.SPORT, TP.NAME, "Over 0.5 · in-play", a, details, prod=True,
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
    for fn in (contender_rows, sa_rows, btts_sa_rows, lambda: (flipped_rows() + piggyback_rows() + shadow_rows(), [])):
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
        live += africa_rows()
    except Exception as exc:                                    # noqa: BLE001
        print(f"soccer_lanes: the African qualifiers goals check failed: {type(exc).__name__}: {exc}")
    try:
        import nl_dump_build
        live += nl_dump_build.rows()
    except Exception as exc:                                    # noqa: BLE001
        print(f"soccer_lanes: the Nations League dump bid failed: {type(exc).__name__}: {exc}")
    try:
        import ko_bid_build
        live += ko_bid_build.rows()
    except Exception as exc:                                    # noqa: BLE001
        print(f"soccer_lanes: the before-kickoff dump bid failed: {type(exc).__name__}: {exc}")
    try:
        import fut_ln_build
        live += fut_ln_build.rows()
    except Exception as exc:                                    # noqa: BLE001
        print(f"soccer_lanes: the futures longshot NO watch failed: {type(exc).__name__}: {exc}")
    try:
        import o35_production as OP
        live.append(o35_row())
        live.append(o35_v5_row())
        live.append(o35_live_row())
        d, st, blob = OP.page_inputs(d, st, blob, _read(os.path.join(ROOT, "data", "o35_cheap_no_ledger.json")) or {}, now=now)
    except Exception as exc:                                    # noqa: BLE001
        print(f"soccer_lanes: the over 3.5 cheap NO failed: {type(exc).__name__}: {exc}")
    try:
        import soccer_p4_build
        live += soccer_p4_build.rows()
    except Exception as exc:                                    # noqa: BLE001
        print(f"soccer_lanes: the phase-4 WATCH lanes failed: {type(exc).__name__}: {exc}")
    try:
        live.append(ere_draw_maker_row())
    except Exception as exc:                                    # noqa: BLE001
        print(f"soccer_lanes: the Eredivisie draw maker failed: {type(exc).__name__}: {exc}")
    try:
        live.append(mls_tie_row())
    except Exception as exc:                                    # noqa: BLE001
        print(f"soccer_lanes: the MLS tie split failed: {type(exc).__name__}: {exc}")
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
    try:
        import arg_dip_production as AP
        ledger = _read(os.path.join(ROOT, "data", "arg_dip_live.json")) or {}
        live.append(arg_live_row(ledger, now))
        d, st, blob = AP.page_inputs(d, st, blob, ledger, now=now)
    except Exception as exc:                                    # noqa: BLE001
        print(f"soccer_lanes: the Argentina dip in Production failed: {type(exc).__name__}: {exc}")
    # A row built already retired (the Nations League watch, the over 3.5 cheap NO, 2026-11-16) goes to the Retired fold.
    gone += [r for r in live if r.get("gone")]
    live = [r for r in live if not r.get("gone")]
    return live, gone, d, st
