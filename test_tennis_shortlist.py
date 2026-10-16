"""Offline selector/publisher regressions: books, rollover, reruns and no old entries."""
import copy
from datetime import datetime, timedelta, timezone
import sandbox_sources as S
import sandbox_track as T
import tennis_shortlist as TS
import production as P

NOW = datetime(2026, 10, 14, 5, 30, tzinfo=timezone.utc)  # 00:30 Central
def row(i, p=.70):
    return dict(market_id=f"aec-utr-a{i}-b{i}-2026-10-14", venue="polymarket_us", sport="tennis",
                side_a=f"A{i}", side_b=f"B{i}", label=f"A{i} vs B{i}", url="https://polymarket.us",
                date="2026-10-14", start=(NOW+timedelta(hours=1)).isoformat(),
                price_a=p, price_b=1-p+.01, spread=.01, untraded=False)
def payload(p=.70, qty=1000, age=0):
    return dict(marketData=dict(state="MARKET_STATE_OPEN", transactTime=(NOW-timedelta(seconds=age)).isoformat(),
                bids=[dict(px={"value":str(p-.01)}, qty=str(qty))],
                offers=[dict(px={"value":str(p)}, qty=str(qty))]))
rows=[row(i,p) for i,p in enumerate([.74,.70,.73,.71])]
books={r['market_id']:payload(r['price_a']) for r in rows}
fetch=lambda mid: books[mid]
picks, eligible, audit=TS.select(rows, [], NOW, fetch)
assert [r['price'] for r in picks]==[.70,.71,.73]
assert len(eligible)==4 and [r['reason'] for r in audit].count('daily cap')==1
prior=[dict(r, source=TS.NAME, bet=True, logged=NOW.isoformat()) for r in picks]
assert TS.select(rows, prior, NOW, fetch)[0]==[]
assert len(TS.select(rows, prior[:2], NOW, fetch)[0])==1
archive=copy.deepcopy(prior)
archive[0]['status']='void'
assert TS.select(rows, archive, NOW, fetch)[0]==[]  # void is not a quota refund
assert TS.day('2026-10-14T04:59:00+00:00')=='2026-10-13'
assert TS.day('2026-10-14T05:00:00+00:00')=='2026-10-14'
assert TS.read_book(payload(age=301),'a',NOW) is None
assert TS.read_book(payload(qty=1),'a',NOW) is not None  # no depth floor since 2026-10-15
assert TS.read_book(payload(p=.75),'a',NOW) is None
assert TS.read_book({},'a',NOW) is None
no=payload(p=.30)
no['marketData']['bids'][0]['px']['value']='.29'
assert TS.read_book(no,'b',NOW)['price']==.71
wide=payload();wide['marketData']['bids'][0]['px']['value']='.65'
assert TS.read_book(wide,'a',NOW) is None
assert TS.select(rows, [], NOW, lambda mid: {})[0]==[]
for old in ['tennis_fav_band','tennis_fav_band_3h','tennis_combo2','tennis_combo3','tennis_combo4','pm_combo2','pm_combo3','pm_combo4']:
    assert S.source_fully_paused(old)
assert 'tennis_combo2|tennis_combo' not in T.PAIR_OVERRIDES
assert 'tennis_utr_shortlist_v1|tennis' in T.PAIR_OVERRIDES

# Exercise the actual publisher with public calls replaced by deterministic fixtures.
saved=(S._get,S.CHALLENGERS,T.CONSENSUS,T.snap_closing)
try:
    S._get=lambda url,tries=1: books[url.split('/')[-2]]
    S.CHALLENGERS={TS.NAME:lambda sport: []}
    T.CONSENSUS={}
    T.snap_closing=lambda *a,**kw:0
    d=dict(quotes=[],meta={},retired={})
    universe={'tennis':copy.deepcopy(rows)}
    T.publish(d,universe,{},verbose=False,now=NOW)
    chosen=[q for q in d['quotes'] if q.get('source')==TS.NAME]
    controls=[q for q in d['quotes'] if q.get('source')==TS.POOL]
    assert len(chosen)==3 and len(controls)==4 and not any(q['bet'] for q in controls)
    assert all(q['ask_size']==1000 and q['book_at'] for q in chosen)
    assert all(P.start_verified(q) and T.placeable(q) for q in chosen)
    T.publish(d,universe,{},verbose=False,now=NOW)
    assert len([q for q in d['quotes'] if q.get('source')==TS.NAME])==3
finally:
    S._get,S.CHALLENGERS,T.CONSENSUS,T.snap_closing=saved
print('PASS: shortlist ranking, book gates, Central day cap, persistent reruns, controls and Production routing')

# 2026-10-15: a thin best level (7 contracts, as live UTR books show) is still eligible.
thin = TS.read_book(payload(.72, qty=7), "a", NOW)
assert thin and thin["ask_size"] == 7, thin
print("thin UTR book is eligible: ok")
