"""The Culture tab (2026-10-16): the four culture lanes on the sport-page template, paper only."""
import datetime as dt
import os

import culture_production as CP
import culture_track as K
import fmt
import site_chrome as C
import sport_page as SP

KEY = "culture"


# Lanes in Production on their own ledger (2026-10-20: Trump mentions, published by
# culture_production.py on its own feed). The page reads them as Production rows through the
# adapter's pair, quotes and stage, the way any own-ledger Production lane is shown.
# 2026-10-26: Trump mentions is back in the Sandbox (CP.DEMOTED_ON), so from CP.DEMOTED_AT on
# nothing is listed and it is an ordinary Sandbox row again, chipped "Removed from Production".
PRODUCTION = {CP.SOURCE: CP.PAIR}


def production(now=None):
    """The lanes in Production at `now`: Trump mentions from 2026-10-20 until CP.DEMOTED_AT."""
    return dict(PRODUCTION) if CP.listed(now) else {}


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


def retired_note(key):
    gone = K.RETIRED[key]
    return (f"Retired {gone['on']} at {gone['at']}: {gone['reason']}. No new entries from that day; its "
            "rows stay and its open picks still settle.")


def per_contract(picks):
    """(won, settled won-or-lost, ROI after fees per contract pooled by cost, or None): the way
    the retirement records were read (2026-10-24)."""
    done = [r for r in picks if r["status"] != "open" and r.get("payout") is not None]
    binary = [r for r in done if r["status"] in ("won", "lost")]
    cost = sum(r["price"] + K.fee(r["price"]) for r in done)
    roi = sum(r["payout"] for r in done) / cost - 1 if cost else None
    return sum(r["status"] == "won" for r in binary), len(binary), roi


def _row(key, lane, now=None, prod=None):
    back = now is not None and K.revived(key, now)
    # A revived lane is judged on its fresh record only (2026-10-26); the rows before it are history.
    picks = K.fresh(key, lane["picks"]) if back else lane["picks"]
    settled = [r for r in picks if r["status"] != "open"]
    binary = [r for r in settled if r["status"] in ("won", "lost")]
    gone = now is not None and K.retired(key, now)
    note = K.RULES[key] + (" " + retired_note(key) if gone else "")
    if back:
        g, r = K.RETIRED.get(key) or {}, K.REVIVED[key]
        note += (f" {revival_note(key).capitalize()}: {r['why']}. It had been retired {g.get('on')} at {g.get('at')}"
                 f" ({g.get('reason')}); those rows stay as its pre-retirement history.") if g else ""
    prod = production(now) if prod is None else prod
    return dict(name=key, sport=KEY, meta={"label": K.LANES[key], "note": note},
                prod=key in prod, pair=prod.get(key), open=sum(r["status"] == "open" for r in picks), since=None,
                v="retired" if gone else "waiting",
                a=dict(n=len(binary), n_price=len(settled) - len(binary),
                       won=sum(r["status"] == "won" for r in binary),
                       expected=sum(r["price"] for r in binary), n_bets=len(settled), unit="contract",
                       roi_fee=sum(r.get("profit", 0) for r in settled) / (100 * len(settled)) if settled else None))


def pooled(state, now=None):
    """The Culture Sandbox record, each MARKET once (2026-10-20), over the lanes not in Production
    (and, given `now`, not retired: a retired lane is not under test). Before the one-market rule two
    lanes could hold the same ticker, sometimes on opposite sides; the ledger keeps both rows,
    and this counts the earliest-logged pick per ticker. -> (record, note)."""
    first = {}
    prod = production(now)
    for key in K.LANES:
        if key in prod:
            continue                    # a Sandbox record: the Production lane is counted on its own
        if now is not None and K.retired(key, now):
            continue
        picks = state["lanes"][key]["picks"]
        for r in (K.fresh(key, picks) if now is not None and K.revived(key, now) else picks):
            if r["id"] not in first or r["logged"] < first[r["id"]]["logged"]:
                first[r["id"]] = r
    settled = [r for r in first.values() if r["status"] != "open"]
    binary = [r for r in settled if r["status"] in ("won", "lost")]
    rec = dict(n=len(binary), n_price=len(settled) - len(binary), won=sum(r["status"] == "won" for r in binary),
               roi_fee=sum(r.get("profit", 0) for r in settled) / (100 * len(settled)) if settled else None)
    return rec, "each market once"


def build(state=None, now=None):
    state = state if state is not None else K.load()
    now = SP.as_utc(now)
    prod = production(now)
    rows = [_row(k, state["lanes"][k], now, prod) for k in K.LANES]
    gone = [k for k in K.LANES if K.retired(k, now)]
    by = {r["name"]: r for r in rows}
    e = C.esc

    def events(_d, _rows, _now):
        out = []
        for key in K.LANES:
            for r in state["lanes"][key]["picks"]:
                q = dict(r, source=key, sport=KEY, market_id=r["id"], start=r["close"],
                         url="https://kalshi.com/markets/" + str(r.get("series") or "").lower())
                status = {"open": "open", "won": "won", "lost": "lost", "no_result": "price"}[r["status"]]
                result = "paper · " + r["status"].replace("_", " ") + (
                    f" · ${r['profit']:+.2f}" if r.get("profit") is not None else "")
                text = f"{r['side'].upper()} · {r.get('title') or ''}"
                out.append(SP.event(K.ts(r["close"]), r.get("name") or r["id"],
                                    [SP.pick(by[key], q, text, status, price=r["price"], status=result)],
                                    sub=r.get("detail", ""), key=key + ":" + r["id"]))
        return out

    def definition(_d, row):
        return SP.definition_html(row["meta"]["note"])

    def recent(_d, row, _now):
        lane = state["lanes"][row["name"]]
        last = lane.get("last_success")
        reasons = (lane.get("observations") or {}).get("reasons") or {}
        txt = "; ".join(f"{k}: {v}" for k, v in sorted(reasons.items(), key=lambda x: -x[1]))
        if row["name"] in gone:
            g = K.RETIRED[row["name"]]
            won, n, roi = per_contract(lane["picks"])
            rec = (f"record now {won}/{n} won, {roi * 100:+.1f}% after fees per contract".replace("-", "−")
                   if n and roi is not None else "no settled entry")
            left = (f'{row["open"]} open pick{"s" if row["open"] != 1 else ""} still '
                    f'settle{"s" if row["open"] == 1 else ""}') if row["open"] else "nothing left open"
            return (f'<p class="sm"><b>Retired {e(g["on"])}</b> at {e(g["at"])} · {e(rec)} · '
                    f'{e(g["reason"])}. No new entries; {left}.</p>'
                    '<p class="sm mut">Last settlement read ' + e(fmt.when(last) if last else "not yet") + '</p>' +
                    ('<p role="status" class="sm">' + e(lane["error"]) + ' · existing records retained.</p>'
                     if lane.get("error") else ''))
        guarded = (lane.get("observations") or {}).get("news_guard") or []
        if guarded:
            txt += ("; " if txt else "") + "; ".join(f"{g.get('word')}: {g.get('reason')}" for g in guarded[:8])
        extra = ""
        if K.revived(row["name"], now):
            g = K.RETIRED.get(row["name"]) or {}
            rec = lambda r: (f"{r[0]}/{r[1]} won, {r[2] * 100:+.1f}% after fees per contract".replace("-", "−")
                             if r[1] and r[2] is not None else "nothing settled yet")
            new, old, old_open = history_split(row["name"], lane["picks"])
            extra = (f'<p class="sm"><b>{e(revival_note(row["name"]).capitalize())}</b>. Revived record: {e(rec(new))}. '
                     f'Pre-retirement history (retired {e(g.get("on", ""))} at {e(g.get("at", ""))}, not counted): '
                     f'{e(rec(old))}{f", {old_open} still open" if old_open else ""}.</p>')
        elif row["name"] == CP.SOURCE and not CP.listed(now):
            rec = lambda r: (f"{r[0]}/{r[1]} won, {r[2] * 100:+.1f}% after fees per contract".replace("-", "−")
                             if r[1] and r[2] is not None else "nothing settled yet")
            pre, post, pre_open = amendment_split(lane["picks"])
            extra = (f'<p class="sm"><b>Removed from Production {e(CP.DEMOTED_ON)}</b> (moved {e(CP.MOVED_ON)}), '
                     f'back in the Sandbox on its whole record. {e(CP.removed_note(state).split(": ", 1)[1])}</p>'
                     f'<p class="sm">Before the {e(K.AMENDED_2)} amendment: {e(rec(pre))}'
                     f'{f", {pre_open} still open" if pre_open else ""}. From {e(K.AMENDED_2)} (NO floor '
                     f'{K.NO_FLOOR:.2f}, monthly and company series out): {e(rec(post))}.</p>')
        return extra + ('<p class="sm mut">Last successful scan ' + e(fmt.when(last) if last else "not yet") +
                (' · ' + e(txt) if txt else '') + '</p>' +
                ('<p role="status" class="sm">' + e(lane["error"]) + ' · existing records retained.</p>'
                 if lane.get("error") else ''))

    def empty_reason(_d, _rows, _idle, now_):
        """Why nothing closes in the next 24 hours, from the culture ledger's own last scan."""
        scans = [K.ts(l.get("last_success")) for l in state["lanes"].values() if l.get("last_success")]
        last = max(scans) if scans else None
        opened = [r for l in state["lanes"].values() for r in l["picks"] if r["status"] == "open"]
        later = sorted(t for t in (K.ts(r["close"]) for r in opened) if t and t > now_)
        if last is None:
            return "no culture scan is stored yet"
        why = f"the last culture scan ({fmt.when(last)}) holds {len(opened)} open pick{'s' if len(opened) != 1 else ''}"
        return why + (f"; the next closes {fmt.when(later[0])}" if later else "; none closes ahead")

    def method(_d, _rows, _now):
        retired_html = "".join(
            f'<li>{e(K.LANES[k])}: retired {e(K.RETIRED[k]["on"])} at {e(K.RETIRED[k]["at"])}; '
            f'{e(K.RETIRED[k]["reason"])}.</li>' for k in gone)
        listed = CP.listed(now)
        inner = ('<p class="sm">Four observation lanes on Kalshi culture markets, registered 2026-10-16 to '
                 'watch, not to trade. Paper entries at the ask with Kalshi\'s 7% fee, settled on Kalshi\'s '
                 'own result. ' +
                 ('Trump mentions has been in Production since 2026-10-20, moved by hand; its '
                  'full record stays here and the Production page counts it from that day. The other three '
                  'lanes are paper only.' if listed else
                  f'Trump mentions was in Production from {CP.MOVED_ON} to {CP.DEMOTED_ON}, moved by hand both '
                  'ways; it is back in the Sandbox on its whole record, and every lane here is paper only.') +
                 '</p>' +
                 (f'<p class="sm">Retired by hand: no new entries, their rows stay and their open picks '
                  f'still settle.</p><ul class="sm">{retired_html}</ul>' if gone else '') +
                 "".join(f'<p class="sm">{e(K.LANES[k])}, {e(revival_note(k))}: retired {e(K.RETIRED[k]["on"])} at '
                         f'{e(K.RETIRED[k]["at"])}, back in the Sandbox because {e(K.REVIVED[k]["why"])}. Its Rotten '
                         'Tomatoes snapshot collector runs again with it, hourly. From the revival a rung whose '
                         'current score is within 1 point of its line is skipped. Only entries logged from the '
                         'revival count; the rows before it are shown as its pre-retirement history.</p>'
                         for k in K.REVIVED if K.revived(k, now)) +
                 (f'<p class="sm">Trump mentions, amended {e(K.AMENDED)}: a NO is refused when Kalshi\'s YES mid '
                  'is over 0.50 and the model\'s P(said) under 0.25 (the news guard, for a word that has just '
                  'become news and so reads low in an 84-day rate; prompted by the lane\'s five settled losses '
                  'to that day, all NOs: Ethanol, Deere, Vivek, Nobel, Bibi; threshold raised to 0.25 on '
                  '2026-10-24, from 0.20), and the edge that meets the 5c threshold is capped at 0.25. Entries '
                  'logged before the amendment are unchanged.</p>'
                  if now.date().isoformat() >= K.AMENDED else '') +
                 (f'<p class="sm">Trump mentions, amended {e(K.AMENDED_2)}, back in the Sandbox: a NO priced under '
                  f'{K.NO_FLOOR:.2f} is refused (no bet against a word the market prices as more than 40% likely '
                  'to be said), and the monthly (KXTRUMPSAYMONTH) and company (KXTRUMPSAYCOMPANY) series are no '
                  'longer entered; the news guard and the edge cap are unchanged. Prompted by its Sandbox record '
                  'to that day, 35 settled, 23 won, \u22124.7% after fees: the NOs under 0.80 lost (\u22127.7% on 20), the '
                  '0.90-0.95 NOs won 5 of 5, and the losses were mostly contrarian NOs at 18-51c on words that '
                  'became news while the model read 21-43%. Entries logged before the amendment stay and settle; '
                  'the row\'s details give the record before and after it.</p>'
                  if now.date().isoformat() >= K.AMENDED_2 else '') +
                 '<p class="sm">Measured before the build on 4,558 settled culture markets (Aug 11 – Oct 16): '
                 '24h before the close about 70% sit under 5c or over 95c, so the favourite band held 8 events '
                 'in two months (7-1, z +0.94) and the 90-97c end 57 (98.2% won, z +1.20). Kalshi closes a '
                 'mentions market the moment the word is said. Rotten Tomatoes counts are not kept historically, '
                 'so the model\'s own hourly snapshots are its history; it bets nothing until 12h of them exist '
                 'for a film.</p>'
                 '<p class="sm">Read hourly by GitHub Actions (culture.yml) from Kalshi, Rotten Tomatoes and '
                 'Roll Call Factbase public pages.</p>')
        return "Method", ("four observation lanes · paper" if not gone
                          else f"four observation lanes · {len(gone)} retired"), inner, False

    spec = SP.spec(family="Culture", key=KEY, title="Edge Machine · Culture",
                   description="Kalshi culture markets: favourite bands, Trump mentions and Rotten Tomatoes.",
                   scope=(("Culture · Trump mentions in Production, three lanes on paper" if not gone else
                           f"Culture · Trump mentions in Production, {len(gone)} lane{'s' if len(gone) != 1 else ''} "
                           f"retired {K.RETIRED[gone[0]]['on']}") if prod else
                          f"Culture · Trump mentions on paper, out of Production {CP.DEMOTED_ON}"
                          + (f", {len(gone)} lane{'s' if len(gone) != 1 else ''} retired {K.RETIRED[gone[0]]['on']}"
                             if gone else "")),
                   venue="Kalshi", rows=rows, events=events,
                   rule_name=lambda r: K.LANES[r["name"]], market=lambda d, r: "Kalshi",
                   definition=definition, recent=recent, method=method, scoped=False,
                   unit=lambda r: "contract", pooled=lambda _rows: pooled(state, now),
                   deadline=True, empty_reason=empty_reason)
    # The Production lane's own quotes and stage, so the template's since-Production tiles and
    # the Production list read it like any staged pair (culture_production is read-only).
    html = SP.page(spec, {"quotes": CP.quotes(state), "coverage": {}}, {"pairs": CP.pairs(now)}, now, rows=rows)
    # Each row's verdict chip says what it is: Production since its move, observing on paper, or
    # retired on its day (the reason in its tooltip and its details). Replaced inside each row's
    # own block, the row named by the block's data-source.
    out, pos = [], 0
    while True:
        head = html.find('<details class="sp-rule', pos)
        if head == -1:
            break
        end = html.find("</details>", head)
        block = html[head:end]
        tag = block[:block.find(">")]
        prod = 'data-stage="production"' in tag
        row = next((r for r in rows if f'data-source="{r["name"]}"' in tag), None)
        if row is not None and row["v"] == "retired":
            gone_on = K.RETIRED[row["name"]]
            chip = (f'<span class="sig x" data-verdict="retired" title="{e(gone_on["reason"])}">'
                    f'Retired · {e(gone_on["on"])}</span>')
        elif row is not None and row["name"] == CP.SOURCE and not CP.listed(now):
            chip = (f'<span class="sig x" data-verdict="removed" title="Back in the Sandbox on its whole record, '
                    f'amended {K.AMENDED_2}">Removed from Production · {CP.DEMOTED_ON}</span>')
        elif row is not None and K.revived(row["name"], now):
            chip = (f'<span class="sig w" data-verdict="revived" title="{e(K.REVIVED[row["name"]]["why"])}">'
                    f'Observing · paper · {e(revival_note(row["name"]))}</span>')
        else:
            chip = (f'<span class="sig w">Production · since {CP.MOVED_ON}</span>' if prod
                    else '<span class="sig w">Observing · paper</span>')
        if row is not None:
            block = block.replace(SP.verdict_badge(row), chip)
        out.append(html[pos:head] + block)
        pos = end
    return "".join(out) + html[pos:]


def main():
    with open(os.path.join(K.ROOT, "public_site", "culture.html"), "w") as f:
        f.write(build())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
