from playwright.sync_api import sync_playwright
import json, sys
UA=("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36")
TEAMS=["Columbus Crew","FC Cincinnati","Houston Dynamo","Austin FC"]
JS="""async (name) => {
  const H={'x-requested-with':'XMLHttpRequest'};
  const sleep=ms=>new Promise(r=>setTimeout(r,ms));
  const g=async u=>{await sleep(40);try{const r=await fetch('https://api.sofascore.com'+u,{headers:H});return r.ok?await r.json():null;}catch(e){return null;}};
  const num=v=>{const n=parseFloat(String(v).replace('%',''));return isNaN(n)?null:n;};
  const s=await g('/api/v1/search/all?q='+encodeURIComponent(name));
  const t=(s&&s.results||[]).find(x=>x.type==='team'&&x.entity.sport&&x.entity.sport.slug==='football');
  if(!t)return {err:'no team'};
  const id=t.entity.id, realname=t.entity.name;
  const ev=await g('/api/v1/team/'+id+'/events/last/0');
  const fin=(ev&&ev.events||[]).filter(e=>e.status&&e.status.code===100).slice(-6);
  let a={gp:0,cf:0,ca:0,gf:0,ga:0,pf:0,pa:0};
  for(const e of fin){
    const home=e.homeTeam.id===id;
    const st=await g('/api/v1/event/'+e.id+'/statistics');
    const all=st&&st.statistics&&st.statistics.find(x=>x.period==='ALL'); if(!all)continue;
    let ck=null,bp=null;
    for(const gr of all.groups)for(const it of gr.statisticsItems){if(it.name==='Corner kicks')ck=it;if(it.name==='Ball possession')bp=it;}
    if(!ck)continue;
    const mc=num(home?ck.home:ck.away),oc=num(home?ck.away:ck.home); if(mc==null)continue;
    a.gp++;a.cf+=mc;a.ca+=oc;a.gf+=(home?e.homeScore.current:e.awayScore.current)||0;a.ga+=(home?e.awayScore.current:e.homeScore.current)||0;
    if(bp){a.pf+=num(home?bp.home:bp.away)||0;a.pa+=num(home?bp.away:bp.home)||0;}
  }
  const n=a.gp; return n?{name:realname,id,gp:n,cf:+(a.cf/n).toFixed(1),ca:+(a.ca/n).toFixed(1),gf:+(a.gf/n).toFixed(1),ga:+(a.ga/n).toFixed(1),poss_f:+(a.pf/n).toFixed(1),poss_a:+(a.pa/n).toFixed(1)}:{id,err:'no stats'};
}"""
out={}
with sync_playwright() as p:
    b=p.chromium.launch(headless=True)
    pg=b.new_page(user_agent=UA)
    pg.goto("https://www.sofascore.com/", wait_until="domcontentloaded", timeout=45000)
    pg.wait_for_timeout(2500)
    for nm in TEAMS:
        try: out[nm]=pg.evaluate(JS, nm)
        except Exception as e: out[nm]={'err':str(e)[:60]}
    b.close()
print(json.dumps(out))
