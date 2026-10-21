"""Daily paper lanes rendered by Crypto and Commodities' unchanged sport template."""
import datetime as dt
import os
import daily_track as D
import fmt
import site_chrome as C
import sport_page as SP


RETIRED_NOTE = (' Retired 2026-10-20: research on 94 settled KXINXU/KXNASDAQ100U 16:00 ET ladders, '
                'Aug 14–Oct 20 2026, at the same settings gave 54/78 @73¢, −6.4% after fee, halves '
                '−28% / +9%; the YES side loses in 8 of 9 price bands. It logs nothing new and its records are kept.')


def _evidence(html, name, n, text):
    """Rewrite one rule row's Evidence cell, scoped to that row."""
    i = html.find(f'data-source="{name}"')
    if i < 0:
        return html
    j = html.find('</summary>', i)
    seg = html[i:j].replace(f'data-l="Evidence">{n}/30</span>', f'data-l="Evidence">{text}</span>')
    return html[:i] + seg + html[j:]


def build(key, state=None, now=None, nc=None):
    state = state if state is not None else D.load()
    lane = state['lanes'][key]
    now = SP.as_utc(now)
    promoted = key == "econ_daily"
    picks = lane['picks']
    settled = [r for r in picks if r['status'] != 'open']
    binary = [r for r in settled if r['status'] in ('won', 'lost')]
    days = len({D.instant(r['close']).astimezone(D.ET).date() for r in settled})
    row = dict(name=key+'_fav_band', sport=key, meta={'label':'Daily favourite band', 'note':D.RULE},
               prod=promoted, open=sum(r['status']=='open' for r in picks), since=None, v='waiting',
               a=dict(n=len(binary), n_price=len(settled)-len(binary), won=sum(r['status']=='won' for r in binary),
                      expected=sum(r['price'] for r in binary), n_bets=len(settled), unit='contract',
                      roi_fee=sum(r.get('profit',0) for r in settled)/(100*len(settled)) if settled else None))
    e = C.esc
    # Finance Daily (2026-10-20): the favourite band is retired (daily_track.RETIRED) and the
    # S&P near-certain NO lane (finance_nc.py) is its Sandbox rule. Econ Daily is unchanged.
    finance = key == 'finance_daily'
    rows, nrow, nc_picks = [row], None, []
    if finance:
        import finance_nc as N
        nc = nc if nc is not None else N.load()
        nc_picks = nc.get('picks') or []
        row['v'] = 'retired'
        row['meta'] = dict(row['meta'], note=D.RULE + RETIRED_NOTE)
        nrow = dict(name=N.KEY, sport=key, meta={'label': N.LABEL, 'note': N.NOTE, 'kind': 'Rule'},
                    prod=False, open=sum(r['status'] == 'open' for r in nc_picks), since=None, v='waiting',
                    a=N.record(nc_picks))
        rows.append(nrow)

    def scan():
        last = lane.get('last_success')
        clock = fmt.when(last) if last else 'Not scanned yet'
        return '<p class="sm mut">Last successful scan '+e(clock)+f' · {len(lane["catalog"])} series discovered</p>' + (
            '<p role="status" class="sm">'+e(lane['error'])+' · existing records retained.</p>' if lane.get('error') else '')

    def definition(_d, r):
        if nrow is not None and r is nrow:
            params = [('Entry', 'NO at 90–98¢ (1 − yes bid), 2–3.5h before the 16:00 ET close'),
                      ('Selection', 'Cheapest in-band KXINXU rung, H1600 event only; one per day, ties by ticker'),
                      ('Liquidity', 'Two-sided quote, ≤3¢ spread, 25+ contracts at the NO ask'),
                      ('Record', 'Paper only · official settlement · 7% fee · per market-day · read at 30')]
            return '<dl class="sp-params">'+''.join(f'<dt>{e(k)}</dt><dd>{e(v)}</dd>' for k,v in params)+'</dl>'+SP.definition_html(N.NOTE)
        params = [('Entry','YES 70–80¢, 2–3.5h before the close'),
                  ('Selection','Cheapest qualifying threshold per event; ties by ticker'),
                  ('Liquidity','≤3¢ spread, 25+ contracts at the ask'),
                  ('Record','Paper only · official final settlement')]
        return '<dl class="sp-params">'+''.join(f'<dt>{e(k)}</dt><dd>{e(v)}</dd>' for k,v in params)+'</dl>'+SP.definition_html(row['meta']['note'])

    def events(_d, rows, _now):
        out = []
        for owner, r in [(row, x) for x in picks] + [(nrow, x) for x in nc_picks]:
            q = dict(r, source=owner['name'], sport=key, market_id=r['id'], start=r['close'],
                     url='https://kalshi.com/markets/'+r['series'].lower()+'#'+r['event'].lower())
            status = {'open':'open','won':'won','lost':'lost','no_result':'price'}[r['status']]
            result = ('paper · '+str(r['status']).replace('_',' ') +
                      (f" · ${r['profit']:+.2f}" if r.get('profit') is not None else ''))
            out.append(SP.event(D.instant(r['close']), r['name'],
                [SP.pick(owner,q,r['title'],status,price=r['price'],status=result)], key=r['id']))
        return out

    def nc_scan():
        last, obs = nc.get('last_success'), nc.get('observation') or {}
        text = 'Last successful scan ' + (fmt.when(last) if last else 'Not scanned yet')
        if obs:
            text += f' · {obs.get("listed", 0)} KXINXU contracts listed, {obs.get("eligible", 0)} in band'
        return '<p class="sm mut">'+e(text)+'</p>' + (
            '<p role="status" class="sm">'+e(nc['error'])+' · existing records retained.</p>' if nc.get('error') else '')

    def method(_d, _rows, _now):
        observations = ''.join(f'<tr><td>{e(x["series"])}</td><td class="num">{x["listed"]}</td><td class="num">{x["eligible"]}</td><td>{e("; ".join(f"{k}: {v}" for k,v in x["reasons"].items()) or "Qualifying quotes found")}</td></tr>' for x in lane['observations'])
        catalog = ''.join(f'<li>{e(m["name"])} · {e(m["series"])} · {"supported" if D.supported(m["series"]) else "observed only — unsupported close/outcome"}</li>' for m in lane['catalog'])
        inner = scan()+f'<p class="sm">{len(settled)} settled contracts across {days} market-days. Correlated thresholds and series are not independent evidence. The complete in-band baseline is retained for comparison. No automatic Production promotion or proven-edge verdict.</p>'
        inner += '<details><summary>Scan reasons &amp; coverage</summary><div class="tbl"><table><thead><tr><th>Series</th><th>Listed</th><th>Eligible</th><th>Reason</th></tr></thead><tbody>'+observations+'</tbody></table></div></details>'
        inner += '<details><summary>Supported catalog</summary><ul>'+ (catalog or '<li>Catalog populates on the first successful scan.</li>')+'</ul></details>'
        if finance:
            base = N.baseline_record(nc.get('baseline') or [])
            reasons = '; '.join(f'{k}: {v}' for k, v in ((nc.get('observation') or {}).get('reasons') or {}).items())
            roi = '' if base['roi_fee'] is None else f', {100*base["roi_fee"]:+.1f}% after fees per market-day'
            inner += ('<h4 class="sp-details-sub">'+e(N.LABEL)+'</h4>'+nc_scan()+
                      f'<p class="sm">{nrow["a"]["n_bets"]} of {N.READ_AT} market-days settled. Blind baseline '
                      f'(every in-band rung in the window): {base["contracts"]} settled contracts on {base["days"]} '
                      f'market-days{roi}.</p>' + (f'<p class="sm mut">Last scan: {e(reasons)}</p>' if reasons else '')
                      + '<p class="sm">Favourite band · 3h to the close: retired 2026-10-20. The scan still reads it '
                      'for coverage but logs nothing new, and its records are kept as they are.</p>')
        inner += '<p class="sm">Public reads collected hourly by GitHub Actions; the existing Sandbox Tracker publishes the saved ledger. Source scan time and page build time are separate. No Research Lab history imported.</p>'
        return 'Method', 'scan reasons · catalog · paper records', inner, False

    coverage = {key: {'daily': {'offered':sum(x['listed'] for x in lane['observations']),
                               'picked':sum(x['eligible'] for x in lane['observations'])}}} if lane.get('last_success') else {}
    spec = SP.spec(family=D.LANES[key],key=key,title='Edge Machine · '+D.LANES[key],
                   description=('S&P 500 near-certain NO, 90–98¢, 2–3.5h before the close; paper only.' if finance else D.RULE),
                   scope=('S&P near-certain NO · paper only' if finance else
                          'Daily favourite-band thresholds · '+('Production' if promoted else 'paper only')),venue='Kalshi',rows=rows,
                   events=events,rule_name=lambda r:(N.LABEL if nrow is not None and r is nrow else 'Favourite band · 3h to the close'),
                   market=lambda d,r:'Kalshi',definition=definition,
                   recent=lambda d,r,n:(nc_scan() if nrow is not None and r is nrow else scan()),
                   method=method,scoped=False,unit=lambda r:'contract')
    data, stages = {'quotes':[], 'coverage':coverage}, {'pairs':{}}
    if promoted:
        import daily_production as DP
        data['quotes'] = DP.quotes(state)
        stages['pairs'] = DP.pairs()
    html = SP.page(spec, data, stages, now, rows=rows)
    if finance:
        nc_days = len({N.day_of(r) for r in nc_picks if r['status'] != 'open'})
        html = _evidence(html, row['name'], len(binary), f'{days}/30 market-days')
        html = _evidence(html, nrow['name'], nrow['a']['n'], f'{nc_days}/{N.READ_AT} market-days')
        return html.replace(SP.verdict_badge(nrow), '<span class="sig w">Paper record · not graded</span>')
    # Keep the template's design while preserving this lane's existing record semantics:
    # contract wins are descriptive; market-days are the evidence clock, not an edge test.
    html = html.replace(f'data-l="Evidence">{len(binary)}/30</span>',f'data-l="Evidence">{days}/30 market-days</span>')
    html = html.replace(SP.verdict_badge(row), '<span class="sig w">'+('Production · paper record' if promoted else 'Paper record · not graded')+'</span>')
    return html


def main():
    state=D.load()
    for key in D.LANES:
        with open(os.path.join(D.ROOT,'public_site',key+'.html'),'w') as f:f.write(build(key,state))
    return 0

if __name__=='__main__':raise SystemExit(main())
