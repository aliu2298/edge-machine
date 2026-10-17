"""The Culture tab (2026-10-16): the four culture lanes on the sport-page template, paper only."""
import datetime as dt
import os

import culture_track as K
import fmt
import site_chrome as C
import sport_page as SP

KEY = "culture"


def _row(key, lane):
    picks = lane["picks"]
    settled = [r for r in picks if r["status"] != "open"]
    binary = [r for r in settled if r["status"] in ("won", "lost")]
    return dict(name=key, sport=KEY, meta={"label": K.LANES[key], "note": K.RULES[key]},
                prod=False, open=sum(r["status"] == "open" for r in picks), since=None, v="waiting",
                a=dict(n=len(binary), n_price=len(settled) - len(binary),
                       won=sum(r["status"] == "won" for r in binary),
                       expected=sum(r["price"] for r in binary), n_bets=len(settled), unit="contract",
                       roi_fee=sum(r.get("profit", 0) for r in settled) / (100 * len(settled)) if settled else None))


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

    def method(_d, _rows, _now):
        inner = ('<p class="sm">Four observation lanes on Kalshi culture markets, registered 2026-10-16 to '
                 'watch, not to trade. Paper entries at the ask with Kalshi\'s 7% fee, settled on Kalshi\'s '
                 'own result. Nothing here is in Production.</p>'
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
                   scope="Culture · Sandbox · paper only", venue="Kalshi", rows=rows, events=events,
                   rule_name=lambda r: K.LANES[r["name"]], market=lambda d, r: "Kalshi",
                   definition=definition, recent=recent, method=method, scoped=False,
                   unit=lambda r: "contract")
    html = SP.page(spec, {"quotes": [], "coverage": {}}, {"pairs": {}}, now, rows=rows)
    for row in rows:
        html = html.replace(SP.verdict_badge(row), '<span class="sig w">Observing · paper</span>')
    return html


def main():
    with open(os.path.join(K.ROOT, "public_site", "culture.html"), "w") as f:
        f.write(build())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
