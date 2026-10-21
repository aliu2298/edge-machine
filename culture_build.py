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
PRODUCTION = {CP.SOURCE: CP.PAIR}


def _row(key, lane):
    picks = lane["picks"]
    settled = [r for r in picks if r["status"] != "open"]
    binary = [r for r in settled if r["status"] in ("won", "lost")]
    return dict(name=key, sport=KEY, meta={"label": K.LANES[key], "note": K.RULES[key]},
                prod=key in PRODUCTION, pair=PRODUCTION.get(key), open=sum(r["status"] == "open" for r in picks), since=None, v="waiting",
                a=dict(n=len(binary), n_price=len(settled) - len(binary),
                       won=sum(r["status"] == "won" for r in binary),
                       expected=sum(r["price"] for r in binary), n_bets=len(settled), unit="contract",
                       roi_fee=sum(r.get("profit", 0) for r in settled) / (100 * len(settled)) if settled else None))


def pooled(state):
    """The Culture Sandbox record, each MARKET once (2026-10-20), over the lanes not in Production.
    Before the one-market rule two
    lanes could hold the same ticker, sometimes on opposite sides; the ledger keeps both rows,
    and this counts the earliest-logged pick per ticker. -> (record, note)."""
    first = {}
    for key in K.LANES:
        if key in PRODUCTION:
            continue                    # a Sandbox record: the Production lane is counted on its own
        for r in state["lanes"][key]["picks"]:
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
    rows = [_row(k, state["lanes"][k]) for k in K.LANES]
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
        return SP.definition_html(K.RULES[row["name"]])

    def recent(_d, row, _now):
        lane = state["lanes"][row["name"]]
        last = lane.get("last_success")
        reasons = (lane.get("observations") or {}).get("reasons") or {}
        txt = "; ".join(f"{k}: {v}" for k, v in sorted(reasons.items(), key=lambda x: -x[1]))
        return ('<p class="sm mut">Last successful scan ' + e(fmt.when(last) if last else "not yet") +
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
        inner = ('<p class="sm">Four observation lanes on Kalshi culture markets, registered 2026-10-16 to '
                 'watch, not to trade. Paper entries at the ask with Kalshi\'s 7% fee, settled on Kalshi\'s '
                 'own result. Trump mentions has been in Production since 2026-10-20, moved by hand; its '
                 'full record stays here and the Production page counts it from that day. The other three '
                 'lanes are paper only.</p>'
                 '<p class="sm">Measured before the build on 4,558 settled culture markets (Aug 11 – Oct 16): '
                 '24h before the close about 70% sit under 5c or over 95c, so the favourite band held 8 events '
                 'in two months (7-1, z +0.94) and the 90-97c end 57 (98.2% won, z +1.20). Kalshi closes a '
                 'mentions market the moment the word is said. Rotten Tomatoes counts are not kept historically, '
                 'so the model\'s own hourly snapshots are its history; it bets nothing until 12h of them exist '
                 'for a film.</p>'
                 '<p class="sm">Read hourly by GitHub Actions (culture.yml) from Kalshi, Rotten Tomatoes and '
                 'Roll Call Factbase public pages.</p>')
        return "Method", "four observation lanes · paper", inner, False

    spec = SP.spec(family="Culture", key=KEY, title="Edge Machine · Culture",
                   description="Kalshi culture markets: favourite bands, Trump mentions and Rotten Tomatoes.",
                   scope="Culture · Trump mentions in Production, three lanes on paper", venue="Kalshi", rows=rows, events=events,
                   rule_name=lambda r: K.LANES[r["name"]], market=lambda d, r: "Kalshi",
                   definition=definition, recent=recent, method=method, scoped=False,
                   unit=lambda r: "contract", pooled=lambda _rows: pooled(state),
                   deadline=True, empty_reason=empty_reason)
    # The Production lane's own quotes and stage, so the template's since-Production tiles and
    # the Production list read it like any staged pair (culture_production is read-only).
    html = SP.page(spec, {"quotes": CP.quotes(state), "coverage": {}}, {"pairs": CP.pairs()}, now, rows=rows)
    # Each row's verdict chip says what it is: Production since its move, or observing on paper.
    # Replaced inside each row's own block (every row's chip is the same string before this).
    out, pos = [], 0
    while True:
        head = html.find('<details class="sp-rule', pos)
        if head == -1:
            break
        end = html.find("</details>", head)
        block = html[head:end]
        prod = 'data-stage="production"' in block[:block.find(">")]
        chip = (f'<span class="sig w">Production · since {CP.MOVED_ON}</span>' if prod
                else '<span class="sig w">Observing · paper</span>')
        for row in rows:
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
