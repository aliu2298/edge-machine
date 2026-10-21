"""Publish Econ Daily's owner-promoted rules on their own collector clock.

The measured record remains paper. Real-money activation is a separate manual
Polybot setting; this module only publishes saved source records.

2026-10-20 (Olu): the favourite band (econ_daily_fav_band) leaves Production for the Sandbox
on its whole record, and the two pre-registered near-certain lanes (daily_track.NC_LANES)
enter Production on a fresh record. The old pair's leads logged while it was in Production
stay in this feed for grading only (lane "retired", never in `pairs`, so nothing follows them);
the pages leave them out.
"""
import datetime as dt
import json
import os
import re
import daily_track as D

# The old lane, now a Sandbox lane. It keeps its whole record (sandbox_track.PAIR_REMOVALS
# names it too, keep_record). No Production listing is left for it, so nothing re-promotes it
# on the removal's own day (#176: a re-listing must be dated strictly after a demotion).
OLD_SOURCE = 'econ_daily_fav_band'
OLD_PAIR = OLD_SOURCE+'|econ_daily'
OLD_PROMOTED = '2026-10-15T03:48:37+00:00'
DEMOTED_ON = '2026-10-20'
# The removal takes effect with tonight's last old-lane window (it shuts 01:59Z): every row the
# old lane logged before this was published while it was in Production.
DEMOTED_AT = '2026-10-21T02:00:00+00:00'

# The near-certain lanes, in Production from 2026-10-20 (00:00 CT), on a fresh record.
NC_PROMOTED = '2026-10-20T05:00:00+00:00'
NC_PAIRS = {lane: lane+'|econ_daily' for lane in D.NC_LANES}
PATH = os.path.join(D.ROOT, 'data', 'econ_production_leads.json')


def pairs():
    return {pair: dict(stage='production', ready_at=NC_PROMOTED, promoted_at=NC_PROMOTED, by_hand=D.NC_REGISTERED)
            for pair in NC_PAIRS.values()}


def _old_pairs():
    return {OLD_PAIR: dict(stage='production', ready_at=OLD_PROMOTED, promoted_at=OLD_PROMOTED, by_hand='2026-10-14')}


def _row(source, r, price, bid, size, pick, payout):
    close, logged = D.instant(r.get('close')), D.instant(r.get('logged'))
    status = {'open':'open','won':'won','lost':'lost','no_result':'settled'}.get(r.get('status'))
    gross = 100*(float(payout)/price-1) if payout is not None else 0
    yes_ask = D.number(r.get('yes_ask')) if pick == 'b' else price
    yes_bid = D.number(r.get('yes_bid')) if pick == 'b' else bid
    return dict(id=source+':'+r['id'],source=source,sport='econ_daily',venue='kalshi_binary',
        market_id=r['id'],event=r['event'],label=r['name'],side_a=r['title'],side_b='No',
        kalshi_title=r['title'],date=close.date().isoformat(),start=close.isoformat(),
        logged=logged.isoformat(),price=price,price_a=yes_ask,price_b=round(1-yes_bid,6) if yes_bid is not None else None,
        price_draw=None,pick=pick,bet=True,stake=100.,status=status,pnl=round(gross,2),
        result='price' if status=='settled' else pick if status=='won' else ('b' if pick=='a' else 'a') if status=='lost' else None,
        settle_px=payout,settled=r.get('settled'),prob_a=None,edge=None,untraded=False,
        start_source='contract_close',spread=round(price-bid,6),liquidity=size*price,url='',
        bid=bid,ask=price,ask_size=size)


def old_quotes(state):
    """The favourite band's rows (now a Sandbox lane), read-only."""
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
        if r.get('status') not in ('open','won','lost','no_result'):continue
        status=r['status']
        payout=r.get('payout',1 if status=='won' else 0 if status=='lost' else None)
        out.append(_row(OLD_SOURCE,r,price,bid,size,'a',payout))
    return out


def quotes(state):
    """The near-certain lanes' rows as ledger quotes; never copied into the Sandbox ledger.
    A row that does not meet its own lane's registered terms is not published."""
    out=[]
    nc=state.get('nc') or {}
    for lane,spec in D.NC_LANES.items():
        for r in (nc.get(lane) or {}).get('picks') or []:
            close,logged=D.instant(r.get('close')),D.instant(r.get('logged'))
            price,bid,size=(D.number(r.get(k)) for k in ('price','bid','size'))
            if (not close or not logged or r.get('series') not in D.NC_SERIES or r.get('side')!=spec['side']
                    or any(v is None for v in (price,bid,size))
                    or not D.nc_eligible(dict(ask=price,bid=bid,size=size),lane)
                    or not spec['minutes'][0] <= (close-logged).total_seconds()/60 <= spec['minutes'][1]
                    or not str(r.get('id') or '').startswith(str(r.get('event') or '')+'-')
                    or (spec['side']=='no' and (D.number(r.get('yes_bid')) is None or D.number(r.get('yes_ask')) is None))):
                continue
            if r.get('status') not in ('open','won','lost','no_result'):continue
            status=r['status']
            payout=r.get('payout',1 if status=='won' else 0 if status=='lost' else None)
            out.append(_row(lane,r,price,bid,size,'a' if spec['side']=='yes' else 'b',payout))
    return out


def _healthy(lane, now):
    stamp=D.instant(lane.get('last_success'))
    return stamp, stamp is not None and not lane.get('error') and dt.timedelta(0)<=now-stamp<=dt.timedelta(hours=3)


def feed(state, now=None, previous=None):
    import production as P
    now=now or dt.datetime.now(dt.timezone.utc)
    nc=state.get('nc') or {}
    stamps,healthy=[],True
    for lane in D.NC_LANES:
        stamp,ok=_healthy(nc.get(lane) or {},now)
        stamps.append(stamp);healthy=healthy and ok
    rows=quotes(state)
    # Failed/stale scans retain settled history but publish no actionable entries.
    if not healthy:rows=[r for r in rows if r['status']!='open']
    built=min([s for s in stamps if s] or [None]) if all(stamps) else None
    built=built or now
    blob=P.build_feed({'quotes':rows}, {'pairs':pairs()}, now=built, previous=previous)
    # The retired favourite band: its Production-era leads, kept for grading the positions a
    # follower already holds. Never in `pairs`, so a follower that checks the pairs block cannot
    # act on one.
    old=[q for q in old_quotes(state) if str(q['logged'])<DEMOTED_AT]
    if old:
        retired=P.build_feed({'quotes':old}, {'pairs':_old_pairs()}, now=built, previous=previous)
        for lid,lead in retired['leads'].items():
            # Settled leads only: a pending one would be a lead with nothing to act on.
            if lid not in blob['leads'] and lead.get('status')!='pending':
                blob['leads'][lid]=dict(lead,lane='retired',retired_on=DEMOTED_ON)
    errors=[(nc.get(l) or {}).get('error') for l in D.NC_LANES]
    blob['collector_error']='; '.join(e for e in errors if e) or None
    blob['collector_healthy']=healthy
    return blob


def _live_leads(leads):
    return {k:v for k,v in (leads or {}).items() if v.get('lane')!='retired'}


def page_inputs(d, st, blob, state, now=None):
    """Augment page inputs in memory, preserving all original ledger/feed objects."""
    current=feed(state,now=now)
    return (dict(d,quotes=list(d.get('quotes') or [])+quotes(state)),
            dict(st,pairs={**(st.get('pairs') or {}),**pairs()}),
            dict(blob,leads={**(blob.get('leads') or {}),**_live_leads(current['leads'])},
                 pairs={**(blob.get('pairs') or {}),**current['pairs']}))


def main():
    import production as P
    previous=P.load_feed(PATH)
    P.save_feed(feed(D.load(),previous=previous),PATH)
    return 0


if __name__=='__main__':raise SystemExit(main())
