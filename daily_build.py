"""Static daily research pages from the paper ledger; never contacts a venue."""
import datetime as dt
import os
import daily_track as D
import fmt
import site_chrome as C

def build(key, state=None, now=None):
    state=state if state is not None else D.load()
    lane=state['lanes'][key]; now=now or dt.datetime.now(dt.timezone.utc)
    rows=lane['picks']; settled=[r for r in rows if r['status']!='open']
    open_rows=[r for r in rows if r['status']=='open']
    days=len({D.instant(r['close']).astimezone(D.ET).date() for r in settled})
    roi=sum(r.get('profit',0) for r in settled)/len(settled) if settled else None
    e=C.esc
    cards=[]
    for label, items in [('Next 24 hours',[r for r in open_rows if now<D.instant(r['close'])<=now+dt.timedelta(hours=24)]),
                         ('Awaiting settlement',[r for r in open_rows if D.instant(r['close'])<=now]),
                         ('Completed results',settled[::-1])]:
        content=''
        for r in items:
            status=e(r['status'].replace('_',' ')); profit=r.get('profit')
            content+=f'<article class="sp-event"><h3>{e(r["name"])}</h3><p>{e(r["title"])}</p><p>{fmt.chicago(r["close"]).strftime("%b %d, %I:%M %p CT")} · YES {r["price"]*100:.0f}¢ · {status}'+(f' · ${profit:+.2f}' if profit is not None else '')+f'</p><details><summary>Entry & contract</summary><p>{e(r["id"])} · logged {e(r["logged"])} · bid {r["bid"]*100:.0f}¢ · ask size {r["size"]:g}</p></details></article>'
        cards.append(f'<section><h2>{label} · {len(items)}</h2>{content or "<p>No paper entries in this view.</p>"}</section>')
    observations=''.join(f'<tr><td>{e(x["series"])}</td><td>{x["listed"]}</td><td>{x["eligible"]}</td><td>{e("; ".join(f"{k}: {v}" for k,v in x["reasons"].items()) or "Qualifying quotes found")}</td></tr>' for x in lane['observations'])
    catalog=''.join(f'<li>{e(m["name"])} · {e(m["series"])} · {"supported" if D.supported(m["series"]) else "observed only — unsupported close/outcome"}</li>' for m in lane['catalog'])
    title=D.LANES[key]; source=lane.get('last_success') or 'Not scanned yet'
    body=f'''<div class="eyebrow">PAPER RESEARCH · DAILY-V1</div><h1>{title}</h1>
<p>Favourite-band daily thresholds · times Central · no orders or Production exports</p>
<div class="tiles"><div class="tile"><b>{len(open_rows)}</b><p>Open picks</p></div><div class="tile"><b>{len(settled)}</b><p>Settled contracts</p></div><div class="tile"><b>{days}/30</b><p>Settled market-days · collecting evidence</p></div><div class="tile"><b>{f"{roi:+.1f}%" if roi is not None else "—"}</b><p>Modelled ROI after fees · paper</p></div></div>
<p>Last successful scan: {e(source)}</p>{'<p role="status">'+e(lane['error'])+' · existing records retained.</p>' if lane.get('error') else ''}
<section id="rules"><details><summary>Rule & supported markets</summary><p>{e(D.RULE)}</p><p>Each day's contracts can move together. Contract win counts are not independent evidence. Full in-band baseline retained for later comparison; this page does not declare a proven edge.</p><ul>{catalog or '<li>Catalog will populate on the first scan.</li>'}</ul></details></section>
<section id="events">{''.join(cards)}</section>
<section id="scan"><details><summary>Scan reasons & coverage</summary><div class="tbl"><table><thead><tr><th>Series</th><th>Listed</th><th>Eligible</th><th>Reason</th></tr></thead><tbody>{observations}</tbody></table></div></details></section>
<footer>Research Lab rule migrated to GitHub · prospective paper records only · no historical Research Lab results imported.</footer>'''
    stamp=f'<time datetime="{now.isoformat()}">Updated {fmt.chicago(now.isoformat()).strftime("%b %d, %I:%M %p CT")}</time>'
    return C.document('Edge Machine · '+title,D.RULE,key,(('rules','Rules'),('events','Events'),('scan','Scan reasons')),stamp,body)

def main():
    state=D.load()
    for key in D.LANES:
        path=os.path.join(D.ROOT,'public_site',key+'.html')
        with open(path,'w') as f:f.write(build(key,state))
    return 0

if __name__=='__main__':raise SystemExit(main())
