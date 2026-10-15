"""Publish Econ Daily's owner-promoted rule on its own collector clock.

The measured record remains paper. Real-money activation is a separate manual
Polybot setting; this module never places orders or edits bot configuration.
"""
import datetime as dt
import json
import os
import re
import daily_track as D

SOURCE = 'econ_daily_fav_band'
PAIR = SOURCE+'|econ_daily'
PROMOTED = '2026-10-15T03:48:37+00:00'
PATH = os.path.join(D.ROOT, 'data', 'econ_production_leads.json')


def pairs():
    return {PAIR:dict(stage='production',ready_at=PROMOTED,promoted_at=PROMOTED,by_hand='2026-10-14')}


def quotes(state):
    """Read-only adapter; never import/copy rows into the original Sandbox ledger."""
    out=[]
    for r in ((state.get('lanes') or {}).get('econ_daily') or {}).get('picks') or []:
        close,logged=D.instant(r.get('close')),D.instant(r.get('logged'))
        price,bid,size=(D.number(r.get(k)) for k in ('price','bid','size'))
        series=str(r.get('series') or '')
        if (not close or not logged or not (series.startswith('KXAAAGASD') or series=='KXDIESELD' or re.fullmatch(r'KXUST(2|5|7|10|30)A',series))
                or any(v is None for v in (price,bid,size))
                or not D.eligible(dict(ask=price,bid=bid,size=size))
                or not 2 <= (close-logged).total_seconds()/3600 <= 3.5
                or not str(r.get('id') or '').startswith(str(r.get('event') or '')+'-')):
            continue
        status={'open':'open','won':'won','lost':'lost','no_result':'settled'}.get(r.get('status'))
        if status is None:continue
        payout=r.get('payout',1 if status=='won' else 0 if status=='lost' else None)
        gross=100*(float(payout)/price-1) if payout is not None else 0
        out.append(dict(id=SOURCE+':'+r['id'],source=SOURCE,sport='econ_daily',venue='kalshi_binary',
            market_id=r['id'],event=r['event'],label=r['name'],side_a=r['title'],side_b='No',
            kalshi_title=r['title'],date=close.date().isoformat(),start=close.isoformat(),
            logged=logged.isoformat(),price=price,price_a=price,price_b=round(1-bid,6),price_draw=None,
            pick='a',bet=True,stake=100.,status=status,pnl=round(gross,2),
            result='price' if status=='settled' else 'a' if status=='won' else 'b' if status=='lost' else None,
            settle_px=payout,settled=r.get('settled'),prob_a=None,edge=None,untraded=False,
            start_source='contract_close',spread=round(price-bid,6),liquidity=size*price,url='',
            bid=bid,ask=price,ask_size=size))
    return out


def feed(state, now=None, previous=None):
    import production as P
    now=now or dt.datetime.now(dt.timezone.utc)
    lane=(state.get('lanes') or {}).get('econ_daily') or {}
    stamp=D.instant(lane.get('last_success'))
    rows=quotes(state)
    # Failed/stale scans retain settled history but publish no actionable entries.
    healthy=stamp is not None and not lane.get('error') and dt.timedelta(0)<=now-stamp<=dt.timedelta(hours=3)
    if not healthy:rows=[r for r in rows if r['status']!='open']
    built=stamp or D.instant(lane.get('last_run')) or now
    blob=P.build_feed({'quotes':rows}, {'pairs':pairs()}, now=built, previous=previous)
    blob['collector_error']=lane.get('error')
    blob['collector_healthy']=healthy
    return blob


def page_inputs(d, st, blob, state, now=None):
    """Augment page inputs in memory, preserving all original ledger/feed objects."""
    current=feed(state,now=now)
    return (dict(d,quotes=list(d.get('quotes') or [])+quotes(state)),
            dict(st,pairs={**(st.get('pairs') or {}),**pairs()}),
            dict(blob,leads={**(blob.get('leads') or {}),**current['leads']},
                 pairs={**(blob.get('pairs') or {}),**current['pairs']}))


def main():
    import production as P
    previous=P.load_feed(PATH)
    P.save_feed(feed(D.load(),previous=previous),PATH)
    return 0


if __name__=='__main__':raise SystemExit(main())
