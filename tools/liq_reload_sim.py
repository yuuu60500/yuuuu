"""Offline model of the v2.45 liquidity lifecycle (HMI_LiquidityLevels.mqh).

Checks the reload requirement: a rebuild whose M5 window starts later must
produce exactly the events a run that started earlier produced, inside the
rebuild's comparable region (after its warm-up + 24 h). Random-walk M5 bars,
H4 aggregated from them, PD/PW/PM levels from consumed H4 bars, S-3 judgement
(beyond by margin, close back within N bars = SWEEP, else BROKEN), and the
v2.45 H4 pre-scan for the stretch before the first M5 bar.

    python3 tools/liq_reload_sim.py            # v2.45 vs the v2.42 behaviour
It models the rules, not MQL5 itself: a pass here does not replace compiling
and running the indicator.
"""
import datetime as dt
CORE = r'''
import random, datetime as dt
random.seed(SEED)
PT=0.00001; MP=3; N=3; WARM=100
# synthetic M5 bars, weekdays only, from 2026-06-01
bars=[]; t=dt.datetime(2026,6,1); px=1.1000
while t < dt.datetime(2026,9,30):
    if t.weekday()<5:
        o=px; c=o+random.gauss(0,0.0004); h=max(o,c)+abs(random.gauss(0,0.0002)); l=min(o,c)-abs(random.gauss(0,0.0002))
        bars.append((t,o,h,l,c)); px=c
    t+=dt.timedelta(minutes=5)
def h4_of(b):
    out={}
    for (t,o,h,l,c) in b:
        k=t.replace(hour=t.hour//4*4,minute=0)
        if k not in out: out[k]=[k,o,h,l,c]
        else: out[k][2]=max(out[k][2],h); out[k][3]=min(out[k][3],l); out[k][4]=c
    return [tuple(v) for v in sorted(out.values())]
H4=h4_of(bars)
pts=lambda a,b: round((a-b)/PT)
def day(t): return t.replace(hour=0,minute=0)
def wk(t): d=day(t); return d-dt.timedelta(days=(d.weekday()+1)%7)   # Sunday start
def mon(t): return t.replace(day=1,hour=0,minute=0)
def prevmon(t): m=mon(t); return (m-dt.timedelta(days=1)).replace(day=1)
def run(m5start):
    m5=[b for b in bars if b[0]>=m5start]
    # align to H4 boundary
    while m5[0][0].hour%4 or m5[0][0].minute: m5=m5[1:]
    first=m5[0][0]; h4=[x for x in H4 if x[0]>=m5start-dt.timedelta(days=83)]
    keys=[None]*3; lv={}; ev=[]
    def consumed(t): return [x for x in h4 if x[0]+dt.timedelta(hours=4)<=t]
    def hilo(a,b,cons):
        if not h4 or h4[0][0]>a: return None
        s=[x for x in cons if a<=x[0]<b]
        return (max(x[2] for x in s),min(x[3] for x in s)) if s else None
    def prescan(name,side,price,frm,cons):
        if frm>=first: return 'I'
        if h4[0][0]>frm: return 'U'
        for x in cons:
            if frm<=x[0]<first and (pts(x[2],price)>MP if side>0 else pts(x[3],price)<-MP): return 'U'
        return 'I'
    for n,(t,o,h,l,c) in enumerate(m5):
        cons=consumed(t)
        for ki,(k,prevf,names) in enumerate([(day(t),None,('PDH','PDL')),(wk(t),None,('PWH','PWL')),(mon(t),None,('PMH','PML'))]):
            if keys[ki]!=k:
                keys[ki]=k
                if ki==0:
                    ds=sorted({day(x[0]) for x in cons if day(x[0])<k and day(x[0]).weekday()!=6})
                    r=hilo(ds[-1],ds[-1]+dt.timedelta(days=1),cons) if ds else None
                elif ki==1: r=hilo(k-dt.timedelta(days=7),k,cons)
                else: r=hilo(prevmon(t),k,cons)
                for side,nm in ((1,names[0]),(-1,names[1])):
                    if r is None: lv.pop(nm,None); continue
                    p=r[0] if side>0 else r[1]
                    lv[nm]=dict(side=side,p=p,st=prescan(nm,side,p,k,cons),pi=None,frm=k)
        for nm,L in lv.items():
            if L['st'] in ('S','B','U'): continue
            if L['st']=='I':
                if not (pts(h,L['p'])>MP if L['side']>0 else pts(l,L['p'])<-MP): continue
                L['st']='P'; L['pi']=n
            back = pts(c,L['p'])<=0 if L['side']>0 else pts(c,L['p'])>=0
            if back: L['st']='S'
            elif n-L['pi']>=N: L['st']='B'
            else: continue
            if n>=WARM: ev.append((t,nm,L['st'],L['frm']))
    return ev, m5[WARM][0]
'''

def check(prescan=True, seeds=range(1, 9)):
    global SEED
    bad = total = 0
    for seed in seeds:
        g = {'SEED': seed}
        code = CORE if prescan else CORE.replace("st=prescan(nm,side,p,k,cons)", "st='I'")
        exec(code, g)
        cont, _ = g['run'](dt.datetime(2026, 7, 1))
        for start in (dt.datetime(2026, 9, 2, 9, 0), dt.datetime(2026, 9, 9, 2, 0), dt.datetime(2026, 9, 16, 5, 0)):
            reb, wend = g['run'](start)
            lim = wend + dt.timedelta(hours=24)
            total += 1
            if {e for e in cont if e[0] >= lim} != {e for e in reb if e[0] >= lim}:
                bad += 1
    return total, bad

if __name__ == '__main__':
    for flag, name in ((True, 'v2.45 (H4 pre-scan)'), (False, 'v2.42 (no pre-scan)')):
        t, b = check(flag)
        print(f"{name:22s} rebuilds {t}  mismatching {b}")
