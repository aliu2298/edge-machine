"""Daily paper lanes rendered by Crypto and Commodities' unchanged sport template.

Econ Daily (2026-10-20): two Production rules, the near-certain lanes (daily_track.NC_LANES,
published by daily_production), and the favourite band below them as a Sandbox rule on its
whole record. Finance Daily (2026-10-20): the favourite band is retired (daily_track.RETIRED)
and the S&P near-certain NO lane (finance_nc.py) is its Sandbox rule.
"""
import datetime as dt
import os
import daily_track as D
import fmt
import site_chrome as C
import sport_page as SP

OLD_NAME = {'econ_daily': 'econ_daily_fav_band', 'finance_daily': 'finance_daily_fav_band'}
OLD_RULE_NAME = 'Favourite band · 3h to the close'
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


def _verdict(html, name, row, text):
    """Replace one rule row's verdict badge, scoped to that row."""
    i = html.find(f'data-source="{name}"')
    if i < 0:
        return html
    j = html.find('</summary>', i)
    seg = html[i:j].replace(SP.verdict_badge(row), f'<span class="sig w">{text}</span>', 1)
    return html[:i] + seg + html[j:]


def _record(picks):
    settled = [r for r in picks if r['status'] != 'open']
    binary = [r for r in settled if r['status'] in ('won', 'lost')]
    days = len({D.instant(r['close']).astimezone(D.ET).date() for r in settled})
    a = dict(n=len(binary), n_price=len(settled)-len(binary), won=sum(r['status']=='won' for r in binary),
             expected=sum(r['price'] for r in binary), n_bets=len(settled), unit='contract',
             roi_fee=sum(r.get('profit',0) for r in settled)/(100*len(settled)) if settled else None)
    return a, days


def build(key, state=None, now=None, nc=None):
    state = state if state is not None else D.load()
    lane = state['lanes'][key]
    now = SP.as_utc(now)
    econ = key == "econ_daily"
    finance = key == 'finance_daily'
    near = {n: dict({'picks': [], 'observations': [], 'error': None}, **((state.get('nc') or {}).get(n) or {}))
            for n in D.NC_LANES} if econ else {}
    old_picks = lane['picks']
    old_a, old_days = _record(old_picks)
    old_row = dict(name=OLD_NAME[key], sport=key, meta={'label':'Daily favourite band', 'note':D.RULE},
                   prod=False, open=sum(r['status']=='open' for r in old_picks), since=None, v='waiting', a=old_a)
    rows, lane_picks = [], {}
    if econ:
        for name, spec in D.NC_LANES.items():
            picks = near[name]['picks']
            a, _days = _record(picks)
            rows.append(dict(name=name, sport=key, meta={'label':spec['label'], 'note':D.NC_RULE[name],
                                                         'frozen':D.NC_REGISTERED},
                             prod=True, open=sum(r['status']=='open' for r in picks), since=None, v='waiting', a=a))
            lane_picks[name] = picks
    rows.append(old_row)
    lane_picks[old_row['name']] = old_picks
    nrow, nc_picks, N = None, [], None
    if finance:
        import finance_nc as N
        nc = nc if nc is not None else N.load()
        nc_picks = nc.get('picks') or []
        old_row['v'] = 'retired'
        old_row['meta'] = dict(old_row['meta'], note=D.RULE + RETIRED_NOTE)
        nrow = dict(name=N.KEY, sport=key, meta={'label': N.LABEL, 'note': N.NOTE, 'kind': 'Rule'},
                    prod=False, open=sum(r['status'] == 'open' for r in nc_picks), since=None, v='waiting',
                    a=N.record(nc_picks))
        rows.append(nrow)
    all_picks = [r for picks in lane_picks.values() for r in picks]
    settled_all = [r for r in all_picks if r['status'] != 'open']
    days_all = len({D.instant(r['close']).astimezone(D.ET).date() for r in settled_all})
    e = C.esc
    by_name = {r['name']: r for r in rows}

    def rule_name(r):
        if nrow is not None and r is nrow:
            return N.LABEL
        return D.NC_LANES[r['name']]['label'] if r['name'] in D.NC_LANES else OLD_RULE_NAME

    def scan():
        last = lane.get('last_success')
        clock = fmt.when(last) if last else 'Not scanned yet'
        errs = [lane.get('error')] + [near[n].get('error') for n in near]
        errs = [x for x in errs if x]
        return '<p class="sm mut">Last successful scan '+e(clock)+f' · {len(lane["catalog"])} series discovered</p>' + (
            ''.join('<p role="status" class="sm">'+e(x)+' · existing records retained.</p>' for x in errs))

    def nc_scan():
        last, obs = nc.get('last_success'), nc.get('observation') or {}
        text = 'Last successful scan ' + (fmt.when(last) if last else 'Not scanned yet')
        if obs:
            text += f' · {obs.get("listed", 0)} KXINXU contracts listed, {obs.get("eligible", 0)} in band'
        return '<p class="sm mut">'+e(text)+'</p>' + (
            '<p role="status" class="sm">'+e(nc['error'])+' · existing records retained.</p>' if nc.get('error') else '')

    def definition(_d, r):
        if nrow is not None and r is nrow:
            params = [('Entry', 'NO at 90–98¢ (1 − yes bid), 2–3.5h before the 16:00 ET close'),
                      ('Selection', 'Cheapest in-band KXINXU rung, H1600 event only; one per day, ties by ticker'),
                      ('Liquidity', 'Two-sided quote, ≤3¢ spread, 25+ contracts at the NO ask'),
                      ('Record', 'Paper only · official settlement · 7% fee · per market-day · read at 30')]
            return '<dl class="sp-params">'+''.join(f'<dt>{e(k)}</dt><dd>{e(v)}</dd>' for k,v in params)+'</dl>'+SP.definition_html(N.NOTE)
        if r['name'] in D.NC_LANES:
            spec = D.NC_LANES[r['name']]
            lo, hi = spec['band']
            side = spec['side'].upper()
            params = [('Entry', f'{side} {lo*100:.0f}–{hi*100:.0f}¢ inclusive, {spec["window"]}'),
                      ('Series', 'AAA national gas (KXAAAGASD) and diesel (KXDIESELD) daily ladders'),
                      ('Selection', 'Cheapest qualifying rung per event; ties to the lower ticker; '
                                    'one market, one lane (this pair and its twin never hold the same rung; the last-hour YES takes it first)'),
                      ('Liquidity', f'≤3¢ spread, 25+ contracts at the {side} ask'),
                      ('Record', 'Production from 2026-10-20, fresh record · official Kalshi settlement · 7% fee')]
            note = ' '.join((D.NC_RULE[r['name']], D.NC_RESEARCH[r['name']], D.NC_WHY, D.NC_CAVEAT[r['name']]))
        else:
            params = [('Entry','YES 70–80¢, 2–3.5h before the close'),
                      ('Selection','Cheapest qualifying threshold per event; ties by ticker'),
                      ('Liquidity','≤3¢ spread, 25+ contracts at the ask'),
                      ('Record','Paper only · official final settlement')]
            note = r['meta']['note'] + (' Back to the Sandbox 2026-10-20 on its whole record (it had been in '
                                        'Production since 2026-10-14); replaced there by the two near-certain lanes.'
                                        if econ else '')
        return '<dl class="sp-params">'+''.join(f'<dt>{e(k)}</dt><dd>{e(v)}</dd>' for k,v in params)+'</dl>'+SP.definition_html(note)

    def events(_d, _rows, _now):
        out = []
        owned = [(by_name[name], r) for name, picks in lane_picks.items() for r in picks]
        owned += [(nrow, r) for r in nc_picks]
        for owner, r in owned:
            q = dict(r, source=owner['name'], sport=key, market_id=r['id'], start=r['close'],
                     url='https://kalshi.com/markets/'+r['series'].lower()+'#'+r['event'].lower())
            status = {'open':'open','won':'won','lost':'lost','no_result':'price'}[r['status']]
            result = ('paper · '+str(r['status']).replace('_',' ') +
                      (f" · ${r['profit']:+.2f}" if r.get('profit') is not None else ''))
            text = ('NO · ' if r.get('side') == 'no' and owner['name'] in D.NC_LANES else '') + str(r['title'])
            out.append(SP.event(D.instant(r['close']), r['name'],
                [SP.pick(owner,q,text,status,price=r['price'],status=result)], key=owner['name']+':'+r['id']))
        return out

    def method(_d, _rows, _now):
        obs = [('Favourite band', x) for x in lane['observations']]
        for name in near:
            obs += [(D.NC_LANES[name]['label'], x) for x in near[name].get('observations') or []]
        observations = ''.join(f'<tr><td>{e(who)}</td><td>{e(x["series"])}</td><td class="num">{x["listed"]}</td><td class="num">{x["eligible"]}</td><td>{e("; ".join(f"{k}: {v}" for k,v in x["reasons"].items()) or "Qualifying quotes found")}</td></tr>' for who, x in obs)
        catalog = ''.join(f'<li>{e(m["name"])} · {e(m["series"])} · {"supported" if D.supported(m["series"]) else "observed only — unsupported close/outcome"}{" · near-certain lanes" if econ and m["series"] in D.NC_SERIES else ""}</li>' for m in lane['catalog'])
        inner = scan()+f'<p class="sm">{len(settled_all)} settled contracts across {days_all} market-days. Correlated thresholds and series are not independent evidence. The complete in-band baseline is retained for comparison. No automatic Production promotion or proven-edge verdict.</p>'
        inner += '<details><summary>Scan reasons &amp; coverage</summary><div class="tbl"><table><thead><tr><th>Rule</th><th>Series</th><th>Listed</th><th>Eligible</th><th>Reason</th></tr></thead><tbody>'+observations+'</tbody></table></div></details>'
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
        inner += '<p class="sm">Public reads collected hourly by GitHub Actions, and inside each entry window on request from the VPS; the existing Sandbox Tracker publishes the saved ledger. Source scan time and page build time are separate. No Research Lab history imported.</p>'
        return 'Method', 'scan reasons · catalog · paper records', inner, False

    observed = list(lane['observations']) + [x for n in near for x in near[n].get('observations') or []]
    coverage = {key: {'daily': {'offered':sum(x['listed'] for x in observed),
                               'picked':sum(x['eligible'] for x in observed)}}} if lane.get('last_success') else {}
    if econ:
        description = D.NC_RULE['econ_nc_yes']+' '+D.NC_RULE['econ_nc_no']
        scope = 'Near-certain AAA gas and diesel rungs · Production'
    elif finance:
        description = 'S&P 500 near-certain NO, 90–98¢, 2–3.5h before the close; paper only.'
        scope = 'S&P near-certain NO · paper only'
    else:
        description, scope = D.RULE, 'Daily favourite-band thresholds · paper only'
    spec = SP.spec(family=D.LANES[key],key=key,title='Edge Machine · '+D.LANES[key],description=description,
                   scope=scope,venue='Kalshi',rows=rows,
                   events=events,rule_name=rule_name,
                   market=lambda d,r:'Kalshi',definition=definition,
                   recent=lambda d,r,n:(nc_scan() if nrow is not None and r is nrow else scan()),
                   method=method,scoped=False,unit=lambda r:'contract')
    data, stages = {'quotes':[], 'coverage':coverage}, {'pairs':{}}
    if econ:
        import daily_production as DP
        data['quotes'] = DP.quotes(state)
        stages['pairs'] = DP.pairs()
    html = SP.page(spec, data, stages, now, rows=rows)
    # Keep the template's design while preserving these lanes' record semantics:
    # contract wins are descriptive; market-days are the evidence clock, not an edge test.
    for r in rows:
        if nrow is not None and r is nrow:
            nc_days = len({N.day_of(x) for x in nc_picks if x['status'] != 'open'})
            html = _evidence(html, r['name'], r['a']['n'], f'{nc_days}/{N.READ_AT} market-days')
            html = _verdict(html, r['name'], r, 'Paper record · not graded')
            continue
        _a, days = _record(lane_picks[r['name']])
        html = _evidence(html, r['name'], r['a']['n'], f'{days}/30 market-days')
        if r.get('v') != 'retired':
            html = _verdict(html, r['name'], r, 'Production · paper record' if r['prod'] else 'Paper record · not graded')
    return html


def main():
    state=D.load()
    for key in D.LANES:
        with open(os.path.join(D.ROOT,'public_site',key+'.html'),'w') as f:f.write(build(key,state))
    return 0

if __name__=='__main__':raise SystemExit(main())
