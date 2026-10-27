"""Regression cases for tools/live_coverage.py (reviewer, v2.54r7 review, 2026-10-20: keep the counterexamples).

Two synthetic UTF-16 log days of one v2.54 instance, written like the MT5 Experts log:
  day 1  build 1 (to 11:55) - live MODEL 12:10, LIQ 12:20, CTX + PROT bar 12:00, edge MODEL 12:30 -
         build 2 (to 12:25, holds all of them) - live LIQ 12:40 before the sleep - last line 11:00 local
  day 2  first build (holds the LIQ 12:40)
Each case alters one thing in a copy and states the exit status the tool must give.

    python3 tools/live_coverage_tests.py [--workdir DIR]
"""
import contextlib, os, subprocess, sys, tempfile

TOOL = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'live_coverage.py')
ID = 'inst=T1,run=100,init=7'


def line(local, msg):
    return f'AB\t0\t{local}\tH4M5_Identification (AUDUSD,M5)\t{msg}'


MODEL = 'AUDUSD,MODEL,1,30,30,OB,MSS,2026.10.19 12:10:00,0.69783,2026.10.19 10:30:00,0.69785'
LIQ = 'AUDUSD,LIQ,-1,0,0,SSL,SWEEP,2026.10.19 12:20:00,0.69700,2026.10.19 12:05:00,0'
EDGE = 'AUDUSD,MODEL,-1,31,31,OB,CISD,2026.10.19 12:30:00,0.69801,2026.10.19 11:50:00,0.69810'
LATE = 'AUDUSD,LIQ,1,0,0,BSL,SWEEP,2026.10.19 12:40:00,0.69900,2026.10.19 12:30:00,0'
CTX = 'HMI-CTX,AUDUSD,BOS,dir=UP,live={},ctx=BULLISH,str=2,messy=0,bar=2026.10.19 12:00,swing=2026.10.15 00:00,' \
      'swing_px=0.69805,close=0.69819,also=0'
PROT = 'HMI-PROT,AUDUSD,ADVANCE,dir=UP,live={},leg=10,bar=2026.10.19 12:00,level=0.69364,swing=2026.10.16 20:00,' \
       'confirm=2026.10.19 08:00,bos=2026.10.19 12:00,age=1,prev=0.69300,cand=0.69364'


def begin(n, to):
    return f'HMI-BUILD-BEGIN,AUDUSD,m5_bars=5000,h4_bars=500,from=2026.09.23 04:00,to={to},ver=2.54,params=461F006E,' \
           f'inst=T1,build={n},warmup_end=2026.09.23 12:20,run=100,init=7'


def end(n, marks, liqev):
    return f'HMI-BUILD-END,AUDUSD,marks={marks},cycles=1,pois=1,blocks=1,build={n},liq=READY,liqev={liqev},unknown=0,' \
           f'liqwait=0,{ID}'


def days():
    d1 = [line('10:00:00.000', begin(1, '2026.10.19 11:55')), line('10:00:00.010', end(1, 0, 0)),
          line('10:05:00.000', CTX.format(1) + ',' + ID), line('10:05:00.000', PROT.format(1) + ',' + ID),
          line('10:10:00.000', 'HMI-LIVE,' + MODEL + ',' + ID), line('10:20:00.000', 'HMI-LIVE,' + LIQ + ',' + ID),
          line('10:30:00.000', 'HMI-LIVE,' + EDGE + ',' + ID),
          line('10:31:00.000', begin(2, '2026.10.19 12:25')),
          line('10:31:00.001', CTX.format(0) + ',' + ID), line('10:31:00.002', PROT.format(0) + ',' + ID),
          line('10:31:00.003', 'HMI-BUILD,' + MODEL + ',' + ID), line('10:31:00.004', 'HMI-BUILD,' + LIQ + ',' + ID),
          line('10:31:00.005', 'HMI-BUILD,' + EDGE + ',' + ID), line('10:31:00.010', end(2, 2, 1)),
          line('10:40:00.000', 'HMI-LIVE,' + LATE + ',' + ID),
          line('11:00:00.000', 'HMI-POI,AUDUSD,TOUCH,id=1,dir=1,bar=2026.10.19 13:00,' + ID)]
    d2 = [line('09:00:00.000', begin(3, '2026.10.20 10:55')),
          line('09:00:00.001', 'HMI-BUILD,' + LATE + ',' + ID), line('09:00:00.010', end(3, 0, 1))]
    return d1, d2


def sub(old, new, which=0):
    def f(d):
        d = list(d)
        hits = [i for i, x in enumerate(d[which]) if old in x]
        assert len(hits) == 1, (old, hits)
        d[which] = list(d[which])
        d[which][hits[0]] = d[which][hits[0]].replace(old, new)
        return d
    return f


def drop(old, which=0):
    def f(d):
        d = list(d)
        d[which] = [x for x in d[which] if old not in x]
        return d
    return f


# v2.55: HMI-REF at the ARMED bar 12:05 (close 12:10) and HMI-BRK + MODEL on the bar 12:15 (close 12:20), live between
# build 1 (to 11:55) and build 2 (to 12:25), which holds all three; the second day only keeps the runner's two files
REF = 'HMI-REF,AUDUSD,CISD,cycle={},dir=1,live={},armed=2026.10.19 12:10,armed_mp=3,state=OK,level=0.69780,' \
      'ref=2026.10.19 11:50,cand_level=0.69780,run_from=2026.10.19 11:50,run_to=2026.10.19 11:55,brk_bar=-,brk_close=NA,brk_mp=NA'
BRK = 'HMI-BRK,AUDUSD,CISD,cycle={},dir=1,live={},bar=2026.10.19 12:15,close=0.69785,mp=3,prev_bar=2026.10.19 12:10,' \
      'prev_close=0.69781,prev_mp=3,level=0.69780,ref=2026.10.19 11:50'
M255 = 'AUDUSD,MODEL,1,{},{},OB,CISD,2026.10.19 12:20:00,0.69779,2026.10.19 11:50:00,0.69780'


def days255():
    b = lambda n, to: begin(n, to).replace('ver=2.54', 'ver=2.55')
    d1 = [line('10:00:00.000', b(1, '2026.10.19 11:55')), line('10:00:00.010', end(1, 0, 0)),
          line('10:10:00.000', REF.format(30, 1) + ',' + ID), line('10:20:00.000', BRK.format(30, 1) + ',' + ID),
          line('10:20:00.000', 'HMI-LIVE,' + M255.format(30, 30) + ',' + ID),
          line('10:31:00.000', b(2, '2026.10.19 12:25')),
          line('10:31:00.001', REF.format(4, 0) + ',' + ID), line('10:31:00.002', BRK.format(4, 0) + ',' + ID),
          line('10:31:00.003', 'HMI-BUILD,' + M255.format(4, 4) + ',' + ID), line('10:31:00.010', end(2, 1, 0)),
          line('11:00:00.000', 'HMI-POI,AUDUSD,TOUCH,id=1,dir=1,bar=2026.10.19 13:00,' + ID)]
    d2 = [line('09:00:00.000', b(3, '2026.10.20 10:55')), line('09:00:00.010', end(3, 0, 0))]
    return d1, d2


# v2.56: one HMI-STR row for the H4 bar closing 12:00, live between build 1 (to 11:55) and build 2 (to 12:25), which holds
# it; each build also writes its HMI-STR-HIST and the live run one HMI-STR-WAIT - neither is a row to compare
STR = 'HMI-STR,AUDUSD,live={},bar=2026.10.19 12:00,ctx=BULLISH,state=OK,reason=-,def=STR1-N12K3-M3R1-W45.35.20-T35.65,dir=1,' \
      'chg12=1400,chg3=350,path=1400,tr_sum=7000,net=1400,recent=350,s_move=93.333333,s_eff=100.000000,s_mom=70.000000,' \
      'raw=91.000000,score=91,tier=STRONG'
HIST = 'HMI-STR-HIST,AUDUSD,live=0,def=STR1-N12K3-M3R1-W45.35.20-T35.65,from=2026.07.10 04:00,to={},bars=500,ok=300,' \
       'nodir=186,nodata=14,weak=100,med=100,strong=100,h=' + ';'.join(['3'] * 100) + ';0'
WAIT = 'HMI-STR-WAIT,AUDUSD,live=1,state=NODATA,reason=WAIT,src=H4,last=2026.10.19 08:00'


def days256():
    d1, d2 = days255()
    v = lambda x: x.replace('ver=2.55', 'ver=2.56')
    d1, d2 = [v(x) for x in d1], [v(x) for x in d2]
    i1 = next(k for k, x in enumerate(d1) if 'HMI-BUILD-END' in x and 'build=1,' in x)
    d1 = d1[:i1] + [line('10:00:00.005', HIST.format('2026.10.19 08:00') + ',' + ID)] + d1[i1:]
    i = next(k for k, x in enumerate(d1) if 'HMI-BUILD-BEGIN' in x and 'build=2,' in x)
    d1 = d1[:i] + [line('10:05:00.000', STR.format(1) + ',' + ID), line('10:06:00.000', WAIT + ',' + ID)] + d1[i:]
    j = next(k for k, x in enumerate(d1) if 'HMI-BUILD-END' in x and 'build=2,' in x)
    d1 = d1[:j] + [line('10:31:00.004', STR.format(0) + ',' + ID), line('10:31:00.005', HIST.format('2026.10.19 12:00') + ',' + ID)] + d1[j:]
    return d1, d2


# v2.57: one HMI-QLT row for the same H4 bar, live and in build 2, and an HMI-QLT-HIST per build - not a row to compare
QLT = 'HMI-QLT,AUDUSD,live={},bar=2026.10.19 12:00,ctx=BULLISH,state=OK,reason=-,def=QLT1-B60.5.3.3S1-RA-O12F6-W40.35.25-T40.70,' \
      'dir=1,ev=2026.10.17 12:00@0.69050/START/OK/0.69400|0.69600|0.69400;2026.10.18 00:00@0.69650/BOS/OK/0.70083|0.70300|0.70133;' \
      '2026.10.18 20:00@0.70350/BOS/OK/0.70600|0.70800|0.71000,b_n=3,b_ok=3,b_fail=0,b_pend=0,q_break=100.000000,anchor=0.69750,' \
      'anchor_bar=2026.10.18 16:00,ext=0.71050,close=0.71000,leg_pts=1300,retr_pts=50,q_retrace=100.000000,' \
      'ov=50/483;50/483;217/267;50/383;50/383;167/300;50/450;50/450;50/450;50/450;50/450,ov_sum=2393089,q_overlap=78.244645,' \
      'raw=94.561161,score={},tier=GOOD,sample=LOW'
QHIST = 'HMI-QLT-HIST,AUDUSD,live=0,def=QLT1-B60.5.3.3S1-RA-O12F6-W40.35.25-T40.70,from=2026.07.10 04:00,to={},bars=500,ok=300,' \
        'partial=100,nodir=86,nodata=14,poor=100,fair=100,good=100,few=90,anchor=10,legbad=0,n=10;30;60;100;100;100,h=' + \
        ';'.join(['3'] * 100) + ';0'


def days257():
    d1, d2 = days256()
    v = lambda x: x.replace('ver=2.56', 'ver=2.57')
    d1, d2 = [v(x) for x in d1], [v(x) for x in d2]
    i1 = next(k for k, x in enumerate(d1) if 'HMI-BUILD-END' in x and 'build=1,' in x)
    d1 = d1[:i1] + [line('10:00:00.006', QHIST.format('2026.10.19 08:00') + ',' + ID)] + d1[i1:]
    i = next(k for k, x in enumerate(d1) if 'HMI-STR-WAIT' in x)
    d1 = d1[:i] + [line('10:05:00.001', QLT.format(1, 95) + ',' + ID)] + d1[i:]
    j = next(k for k, x in enumerate(d1) if 'HMI-BUILD-END' in x and 'build=2,' in x)
    d1 = d1[:j] + [line('10:31:00.006', QLT.format(0, 95) + ',' + ID), line('10:31:00.007', QHIST.format('2026.10.19 12:00') + ',' + ID)] + d1[j:]
    return d1, d2


def restart(drop_row=None):
    """the terminal restarted between build 1 and build 2: build 2 onwards carries run=101"""
    def f(d):
        d1, d2 = d
        i = next(k for k, x in enumerate(d1) if 'HMI-BUILD-BEGIN' in x and 'build=2,' in x)
        d1 = d1[:i] + [x.replace(',run=100,', ',run=101,') for x in d1[i:]]
        d2 = [x.replace(',run=100,', ',run=101,') for x in d2]
        if drop_row:                                 # the row goes, and build 2's END counts one MODEL row less
            d1 = [x.replace('marks=2,', 'marks=1,') if 'HMI-BUILD-END' in x and 'build=2,' in x else x
                  for x in d1 if drop_row not in x]
        return [d1, d2]
    return f


def presleep_prot_leg(d):
    """a PROT row logged after the day's last build, in the next day's first build with another leg= only"""
    d1, d2 = d
    row = 'HMI-PROT,AUDUSD,KEEP_NONE,dir=UP,live={},leg={},bar=2026.10.19 12:40,level=0.69364,swing=2026.10.16 20:00,' \
          'confirm=2026.10.19 08:00,bos=2026.10.19 12:00,age=1,prev=NA,cand=NA,' + ID
    i = next(k for k, x in enumerate(d1) if 'HMI-LIVE,AUDUSD,LIQ,1,0,0,BSL' in x)
    d1 = d1[:i + 1] + [line('10:45:00.000', row.format(1, 9))] + d1[i + 1:]
    d2 = d2[:-1] + [line('09:00:00.002', row.format(0, 10))] + d2[-1:]
    return [d1, d2]


LIVE_M = '10:10:00.000'
CASES = [
    ('unaltered', lambda d: d, 0),
    ('live MODEL direction flipped', sub('HMI-LIVE,AUDUSD,MODEL,1,30', 'HMI-LIVE,AUDUSD,MODEL,-1,30'), 1),
    ('live LIQ direction flipped', sub('HMI-LIVE,AUDUSD,LIQ,-1,0,0,SSL', 'HMI-LIVE,AUDUSD,LIQ,1,0,0,SSL'), 1),
    ('live MODEL price changed', sub('HMI-LIVE,AUDUSD,MODEL,1,30,30,OB,MSS,2026.10.19 12:10:00,0.69783',
                                     'HMI-LIVE,AUDUSD,MODEL,1,30,30,OB,MSS,2026.10.19 12:10:00,0.69784'), 1),
    ('live MODEL run changed', sub(LIVE_M + '\tH4M5_Identification (AUDUSD,M5)\tHMI-LIVE,' + MODEL + ',inst=T1,run=100',
                                   LIVE_M + '\tH4M5_Identification (AUDUSD,M5)\tHMI-LIVE,' + MODEL + ',inst=T1,run=101'), 1),
    ('live PROT leg changed', sub('ADVANCE,dir=UP,live=1,leg=10', 'ADVANCE,dir=UP,live=1,leg=11'), 1),
    ('live CTX missing from the later build', drop('HMI-CTX,AUDUSD,BOS,dir=UP,live=0'), 1),
    ('edge MODEL direction flipped', sub('HMI-LIVE,AUDUSD,MODEL,-1,31', 'HMI-LIVE,AUDUSD,MODEL,1,31'), 1),
    ('pre-sleep LIQ direction flipped', sub('HMI-LIVE,AUDUSD,LIQ,1,0,0,BSL', 'HMI-LIVE,AUDUSD,LIQ,-1,0,0,BSL'), 1),
    ('pre-sleep LIQ init changed', sub('BSL,SWEEP,2026.10.19 12:40:00,0.69900,2026.10.19 12:30:00,0,inst=T1,run=100,init=7',
                                       'BSL,SWEEP,2026.10.19 12:40:00,0.69900,2026.10.19 12:30:00,0,inst=T1,run=100,init=8'), 1),
    ('build END marks wrong', sub('marks=2,', 'marks=3,'), 1),
    ('build never closed', drop('HMI-BUILD-END', 1), 1),
    ('live row cannot be parsed', sub('HMI-LIVE,' + LIQ, 'HMI-LIVE,AUDUSD,LIQ,-1,0,0,SSL,SWEEP,not-a-time'), 1),
    # a terminal restart between two builds of one day (run= changes) is not intraday evidence (A-60): the live rows
    # before it are only checked forward against the build after it
    ('restart between the builds', restart(), 0),
    ('restart, a live row missing from the build after it', restart('HMI-BUILD,' + MODEL), 1),
    # across a sleep, a row that is the same but for leg= (leg counts from each build's own H4 start): PENDING REVIEW
    ('pre-sleep PROT the same but for leg', presleep_prot_leg, 1),
    # v2.55 (--ver 2.55): HMI-REF / HMI-BRK are a category of their own (B8); cycle= is init-relative, not compared
    ('v2.55 unaltered (cycle ids differ)', lambda d: d, 0, '2.55'),
    ('v2.55 live HMI-BRK prev_mp changed', sub('cycle=30,dir=1,live=1,bar=2026.10.19 12:15,close=0.69785,mp=3,'
                                               'prev_bar=2026.10.19 12:10,prev_close=0.69781,prev_mp=3',
                                               'cycle=30,dir=1,live=1,bar=2026.10.19 12:15,close=0.69785,mp=3,'
                                               'prev_bar=2026.10.19 12:10,prev_close=0.69781,prev_mp=4'), 1, '2.55'),
    ('v2.55 live HMI-REF missing', drop('HMI-REF,AUDUSD,CISD,cycle=30,'), 1, '2.55'),
    # v2.56 (--ver 2.56): HMI-STR is a category of its own (STR), judged like CTX on the H4 bar
    ('v2.56 unaltered (HIST / WAIT rows not compared)', lambda d: d, 0, '2.56'),
    ('v2.56 live HMI-STR score changed', sub('HMI-STR,AUDUSD,live=1,bar=2026.10.19 12:00,ctx=BULLISH,state=OK,reason=-,'
                                             'def=STR1-N12K3-M3R1-W45.35.20-T35.65,dir=1,chg12=1400,chg3=350,path=1400,'
                                             'tr_sum=7000,net=1400,recent=350,s_move=93.333333,s_eff=100.000000,'
                                             's_mom=70.000000,raw=91.000000,score=91',
                                             'HMI-STR,AUDUSD,live=1,bar=2026.10.19 12:00,ctx=BULLISH,state=OK,reason=-,'
                                             'def=STR1-N12K3-M3R1-W45.35.20-T35.65,dir=1,chg12=1400,chg3=350,path=1400,'
                                             'tr_sum=7000,net=1400,recent=350,s_move=93.333333,s_eff=100.000000,'
                                             's_mom=70.000000,raw=91.000000,score=90'), 1, '2.56'),
    ('v2.56 live HMI-STR missing from the later build', drop('HMI-STR,AUDUSD,live=0,'), 1, '2.56'),
    # v2.57 (--ver 2.57): HMI-QLT is a category of its own (QLT), judged like STR on the H4 bar
    ('v2.57 unaltered (QLT-HIST rows not compared)', lambda d: d, 0, '2.57'),
    ('v2.57 live HMI-QLT score changed', lambda d: [[x.replace(',score=95,', ',score=94,') if 'HMI-QLT,AUDUSD,live=1,' in x else x
                                                    for x in d[0]], d[1]], 1, '2.57'),
    ('v2.57 live HMI-QLT missing from the later build', drop('HMI-QLT,AUDUSD,live=0,'), 1, '2.57'),
]


def main():
    # --workdir DIR: write the fixtures there instead of a TemporaryDirectory (a sandbox may refuse its 0700 directory;
    # reviewer, v2.54r8 review)
    work = sys.argv[sys.argv.index('--workdir') + 1] if '--workdir' in sys.argv else None
    ok = 0
    with (contextlib.nullcontext(work) if work else tempfile.TemporaryDirectory()) as tmp:
        os.makedirs(tmp, exist_ok=True)
        for name, alter, want, *ver in CASES:
            ver = ver[0] if ver else '2.54'
            d1, d2 = alter(days257() if ver == '2.57' else days256() if ver == '2.56' else days255() if ver == '2.55' else days())
            paths = []
            for n, d in (('20261019.log', d1), ('20261020.log', d2)):
                p = os.path.join(tmp, n)
                with open(p, 'wb') as fh:
                    fh.write(('\r\n'.join(d) + '\r\n').encode('utf-16'))
                paths.append(p)
            r = subprocess.run([sys.executable, '-I', TOOL, '--ver', ver] + paths, capture_output=True, text=True)
            last = (r.stdout.strip().splitlines() or [''])[-1]
            good = r.returncode == want and (want == 1) == last.startswith('RESULT: NOT PASSED') and not r.stderr
            if name == 'unaltered':
                good = good and 'AUDUSD#T1      20261019       1      1    1    1    1     0        1' in r.stdout \
                    and 'in the later build' in r.stdout and 'both directions agree for LIQ 1' in r.stdout
            if name.startswith('restart, a live row missing'):
                good = good and 'MISSING' in r.stdout and 'input problem' not in last
            if name == 'pre-sleep PROT the same but for leg':
                good = good and 'leg only' in r.stdout and 'missing from live 0, leg only 1' in r.stdout \
                    and 'PENDING REVIEW' in last and 'not matched' not in last
            if name == 'restart between the builds':
                good = good and 'across a terminal restart' in r.stdout and 'AUDUSD#T1      20261019' not in r.stdout
            if name.startswith('v2.55 unaltered'):
                good = good and 'AUDUSD#T1      20261019       1      1    0    0    0    2     0        0' in r.stdout \
                    and 'intraday: MODEL, B8' in r.stdout
            if name == 'live PROT leg changed':
                good = good and 'PENDING REVIEW' in last and 'difference' not in last
            if name.startswith('v2.56 unaltered'):
                good = good and 'AUDUSD#T1      20261019       1      1    0    0    0    2    1     0        0' in r.stdout \
                    and 'intraday: MODEL, B8, STR' in r.stdout
            if name.startswith('v2.57 unaltered'):
                good = good and 'AUDUSD#T1      20261019       1      1    0    0    0    2    1    1     0        0' in r.stdout \
                    and 'intraday: MODEL, B8, STR, QLT' in r.stdout
            ok += good
            print(f'  {"ok  " if good else "FAIL"} {name:40} exit {r.returncode} (want {want})  {last[:70]}')
            if not good:
                print(r.stdout[-1500:], r.stderr[-800:])
    print(f'{ok}/{len(CASES)}')
    return 0 if ok == len(CASES) else 1


if __name__ == '__main__':
    sys.exit(main())
