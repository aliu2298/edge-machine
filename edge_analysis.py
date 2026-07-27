#!/usr/bin/env python3
"""edge_analysis.py <results_raw.txt> — league edge report from FootyStats fixture-page text.
Parses 'Team F.FF\\nH - A\\nFT\\nF.FF Team\\noddsH\\noddsD\\noddsA' blocks (get_page_text dump)."""
import re, sys
from collections import Counter

txt=open(sys.argv[1]).read()
pat=re.compile(r"([A-Za-zÀ-ÿ .]+?) \d\.\d\d\n(\d+) - (\d+)\nFT\n\d\.\d\d ([A-Za-zÀ-ÿ .]+?)\n(\d+\.\d+)\n(\d+\.\d+)\n(\d+\.\d+)")
rows=[(m.group(1).strip(),int(m.group(2)),int(m.group(3)),m.group(4).strip(),
       float(m.group(5)),float(m.group(6)),float(m.group(7))) for m in pat.finditer(txt)]
n=len(rows); print(f"parsed {n} completed matches\n")
hw=sum(1 for r in rows if r[1]>r[2]); dr=sum(1 for r in rows if r[1]==r[2]); aw=n-hw-dr
print(f"RESULT SPLIT: home {100*hw//n}% | draw {100*dr//n}% | away {100*aw//n}%")
tg=[r[1]+r[2] for r in rows]
print(f"GOALS: avg {sum(tg)/n:.2f} | under 2.5: {100*sum(1 for t in tg if t<3)//n}% | BTTS: {100*sum(1 for r in rows if r[1]>0 and r[2]>0)//n}%")
print(f"\nFAVORITE ANALYSIS (flat 1u):")
print(f"{'bucket':<12}{'n':>4}{'win%':>6}{'ML ROI':>8}{'by2+%':>7}")
for lo,hi,label in [(1.0,1.35,"<=1.35"),(1.35,1.55,"1.36-1.55"),(1.55,1.75,"1.56-1.75"),(1.75,2.00,"1.76-2.00"),(2.00,2.40,"2.01-2.40")]:
    sel=[]
    for h,hs,as_,a,oh,od,oa in rows:
        fo=min(oh,oa)
        if lo<fo<=hi:
            mg=(hs-as_) if oh<=oa else (as_-hs)
            sel.append((fo,mg))
    if not sel: continue
    nn=len(sel); w=sum(1 for f,m in sel if m>0)
    roi=sum((f-1) if m>0 else -1 for f,m in sel)/nn*100
    cov=sum(1 for f,m in sel if m>=2)
    print(f"{label:<12}{nn:>4}{100*w//nn:>5}%{roi:>7.1f}%{100*cov//nn:>6}%")
print(f"\nFAVORITE BY VENUE:")
for venue in ("home","away"):
    sel=[(min(oh,oa),(hs-as_) if oh<=oa else (as_-hs)) for h,hs,as_,a,oh,od,oa in rows if (oh<=oa)==(venue=="home")]
    if not sel: continue
    nn=len(sel); w=sum(1 for o,m in sel if m>0)
    roi=sum((o-1) if m>0 else -1 for o,m in sel)/nn*100
    print(f"  {venue} favs: n={nn} win {100*w//nn}% | ML ROI {roi:+.1f}%")
def bucket(hs,as_):
    if hs==as_: return "draw 1-1/2-2/3-3" if (hs,as_) in {(1,1),(2,2),(3,3)} else "draw 0-0/other"
    w,l=max(hs,as_),min(hs,as_)
    if (w,l) in {(1,0),(2,0),(2,1)}: return "win-low"
    if (w,l) in {(3,0),(3,1),(3,2)}: return "win-big(3-x)"
    return "win-other(4+)"
cnt=Counter(bucket(r[1],r[2]) for r in rows)
print(f"\nSCORELINE GROUPS:")
for k,v in cnt.most_common(): print(f"  {k:<18}{v:>4}  ({100*v//n}%)")
top=Counter((r[1],r[2]) for r in rows).most_common(6)
print("  top scores:", ", ".join(f"{h}-{a}×{c}" for (h,a),c in top))
sel=[(min(oh,oa),(hs-as_) if oh<=oa else (as_-hs)) for h,hs,as_,a,oh,od,oa in rows]
print(f"\nFAV +0.5 (win-or-draw): {100*sum(1 for o,m in sel if m>=0)//n}%")
big=[(o,m) for o,m in sel if o<=1.50]
if big: print(f"BIG FAVS (<=1.50): n={len(big)} win {100*sum(1 for o,m in big if m>0)//len(big)}% | by2+ {100*sum(1 for o,m in big if m>=2)//len(big)}%")
