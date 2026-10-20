"""BRI-08 (v2.55 draft): CISD / MSS on the first effective close beyond the threshold - offline model of the
paired scenarios in docs/02 "BRI-08 修订稿 1". Not the MQL implementation; it fixes what each scenario must give.

Prices are integer points (Appendix B.2). One bar = (open, high, low, close). margin[n] is the break margin of bar n
(MarginM5Pts(n): constant in the PIPS / POINTS modes, per bar in ATR_FRAC). Effective break of level L on bar n:
    bull  close[n] - L >  margin[n]          bear  close[n] - L < -margin[n]          (strict; equal is not a break)

v2.54 (rules as frozen)                               v2.55 (BRI-08)
  CISD reference  Rule 19, no break check               Rule 19 + N/A when an effective break of open[k] happened on a
                                                        bar m in [k+1, A] (each bar with its own margin)
  MSS reference   C1..C5, C5 with margin[A]             C1..C5, C5 with margin[m] of the bar m that is checked
  confirmation    n > A, close[n-1] on the unbroken     n > A, first effective close; close[n-1] is not looked at
                  side of L AND effective close on n
Both: max 1 per cycle (Rule 43), close only (Rule 23), no ARMED-bar confirmation (Rule 18; D-4 is PA only).

Bear scenarios are the exact mirror of the bull ones (every price negated, high <-> low), with the same expected bars.

    python3 tools/bri08_sim.py            all scenarios, both directions, both versions
"""
import sys

NA = 'NA'          # reference rejected at ARMED: the model is N/A for the cycle
NONE = '-'         # reference kept, no confirmation inside the bars given


def cdir(b):
    o, _, _, c = b
    return (c > o) - (c < o)


def brk(d, close, level, mp):
    return (close - level > mp) if d > 0 else (close - level < -mp)


def cisd_ref(bars, d, A, look, margin, v255):
    lo = max(0, A - look + 1)
    j = next((k for k in range(A, lo - 1, -1) if cdir(bars[k]) == -d), None)
    if j is None:
        return None
    k = j
    while k - 1 >= lo and cdir(bars[k - 1]) == -d:
        k -= 1
    level = bars[k][0]
    if v255 and any(brk(d, bars[m][3], level, margin[m]) for m in range(k + 1, A + 1)):
        return None
    return level


def mss_ref(bars, d, A, swings, window, margin, v255):
    lo = max(0, A - window + 1)
    best = None
    for (i, price, conf, sd) in swings:                       # (bar index, price, confirm bar index, +1 high / -1 low)
        if i < lo or sd != d or conf > A:                     # C2, C3, C1
            continue
        if (d > 0 and price <= bars[A][1]) or (d < 0 and price >= bars[A][2]):   # C4
            continue
        if any(brk(d, bars[m][3], price, margin[m] if v255 else margin[A]) for m in range(i + 1, A + 1)):   # C5
            continue
        if best is None or i > best[0]:
            best = (i, price)
    return None if best is None else best[1]


def confirm(bars, d, A, level, margin, v255):
    if level is None:
        return NA
    for n in range(A + 1, len(bars)):
        prev_ok = (bars[n - 1][3] - level <= 0) if d > 0 else (bars[n - 1][3] - level >= 0)
        if brk(d, bars[n][3], level, margin[n]) and (v255 or prev_ok):
            return n
    return NONE


def run(sc, d, v255):
    bars, margin = sc['bars'], sc.get('margin') or [3] * len(sc['bars'])
    if d < 0:
        bars = [(-o, -l, -h, -c) for (o, h, l, c) in bars]
    swings = [(i, p * d, c, sd * d) for (i, p, c, sd) in sc.get('swings', [])]
    A = sc['A']
    out = {}
    if 'cisd' in sc:
        out['CISD'] = confirm(bars, d, A, cisd_ref(bars, d, A, 12, margin, v255), margin, v255)
    if 'mss' in sc:
        out['MSS'] = confirm(bars, d, A, mss_ref(bars, d, A, swings, 60, margin, v255), margin, v255)
    return out


def B(o, c, h=None, l=None):
    return (o, max(o, c) + 1 if h is None else h, min(o, c) - 1 if l is None else l, c)


# Bull form. CISD level L = 100 (open of the oldest bar of the bearish run before A); margin 3 unless given.
RUN = [B(96, 99), B(100, 97), B(97, 95)]           # 0 bull, 1-2 bearish run (k = 1, L = open[1] = 100)
SCEN = [
    dict(id='S01', what='slow crossing: 101, 102, then 104 (each step below the margin)',
         bars=RUN + [B(95, 99), B(99, 101), B(101, 102), B(102, 104)], A=3,
         cisd={'v2.54': NONE, 'v2.55': 6}),
    dict(id='S02', what='slow crossing, dip to 99, then 104: both confirm on the re-cross',
         bars=RUN + [B(95, 99), B(99, 101), B(101, 99), B(99, 104)], A=3,
         cisd={'v2.54': 6, 'v2.55': 6}),
    dict(id='S03', what='clean cross from below on A+1 (unchanged)',
         bars=RUN + [B(95, 99), B(99, 104)], A=3,
         cisd={'v2.54': 4, 'v2.55': 4}),
    dict(id='S04', what='wick: high 110 but close 102, then close 104',
         bars=RUN + [B(95, 99), B(99, 102, h=110), B(102, 104)], A=3,
         cisd={'v2.54': NONE, 'v2.55': 5}),
    dict(id='S05', what='wick from below: close 99 with high 110, then close 104 (unchanged)',
         bars=RUN + [B(95, 99), B(99, 99, h=110), B(99, 104)], A=3,
         cisd={'v2.54': 5, 'v2.55': 5}),
    dict(id='S06', what='close exactly L + margin (103) is not a break; 104 next bar is',
         bars=RUN + [B(95, 99), B(99, 103), B(103, 104)], A=3,
         cisd={'v2.54': NONE, 'v2.55': 5}),
    dict(id='S07', what='A closes exactly at L (100), then 104: both confirm (v2.54 accepts a prev close == L)',
         bars=RUN + [B(95, 100), B(100, 104)], A=3,
         cisd={'v2.54': 4, 'v2.55': 4}),
    dict(id='S08', what='ATR margin falls: 104 with margin 5 (no), 104 again with margin 3 (yes, same price)',
         bars=RUN + [B(95, 99), B(99, 104), B(104, 104, h=106)], A=3, margin=[3, 3, 3, 3, 5, 3],
         cisd={'v2.54': NONE, 'v2.55': 5}),
    dict(id='S09', what='ATR margin rises: 104 with margin 5 (no); 106 with margin 5 (yes)',
         bars=RUN + [B(95, 99), B(99, 104), B(104, 106)], A=3, margin=[3, 3, 3, 3, 5, 5],
         cisd={'v2.54': NONE, 'v2.55': 5}),
    dict(id='S10', what='ATR margin 5: 104 (no), dip 99, 105 = L + margin (no), 106 (v2.55 yes; v2.54 prev 105 > L)',
         bars=RUN + [B(95, 99), B(99, 104), B(104, 99), B(99, 105), B(105, 106)], A=3,
         margin=[3, 3, 3, 3, 5, 3, 5, 5], cisd={'v2.54': NONE, 'v2.55': 7}),
    dict(id='S11', what='A closes between L and the threshold (101); first close beyond it confirms',
         bars=RUN + [B(95, 101), B(101, 104)], A=3,
         cisd={'v2.54': NONE, 'v2.55': 4}),
    dict(id='S12', what='A closes beyond the threshold (104): reference already broken at ARMED',
         bars=RUN + [B(95, 104), B(104, 99), B(99, 104)], A=3,
         cisd={'v2.54': 5, 'v2.55': NA}),
    dict(id='S13', what='a bar between the run and A broke L (close 105), price back to 98 at A, re-cross later',
         bars=RUN + [B(95, 105), B(97, 98), B(98, 104)], A=4,
         cisd={'v2.54': 5, 'v2.55': NA}),
    dict(id='S14', what='a bar between the run and A only reached the zone (102), back at A, then 104',
         bars=RUN + [B(95, 102), B(97, 98), B(98, 104)], A=4,
         cisd={'v2.54': 5, 'v2.55': 5}),
    dict(id='S15', what='pre-ARMED break judged with that bar\'s own ATR margin (close 104, margin 5 then): not broken',
         bars=RUN + [B(95, 104), B(97, 98), B(98, 104)], A=4, margin=[3, 3, 3, 5, 3, 3],
         cisd={'v2.54': 5, 'v2.55': 5}),
    dict(id='S16', what='max 1 per cycle: after the confirmation a dip and a second cross mark nothing',
         bars=RUN + [B(95, 99), B(99, 104), B(104, 98), B(98, 105)], A=3,
         cisd={'v2.54': 4, 'v2.55': 4}),
    dict(id='S17', what='zero margin (XAUUSD default): close == L is not a break, close L + 1 is',
         bars=RUN + [B(95, 99), B(99, 100), B(100, 101)], A=3, margin=[0] * 6,
         cisd={'v2.54': 5, 'v2.55': 5}),
    dict(id='S18', what='zero margin, A closes at L + 1: broken at ARMED -> v2.55 N/A; v2.54 waits for a re-cross',
         bars=RUN + [B(95, 101), B(101, 99), B(99, 101)], A=3, margin=[0] * 6,
         cisd={'v2.54': 5, 'v2.55': NA}),
    dict(id='S19', what='no bearish bar in the lookback: N/A in both',
         bars=[B(90, 92), B(92, 94), B(94, 96), B(96, 99), B(99, 104)], A=3,
         cisd={'v2.54': NA, 'v2.55': NA}),
    # MSS: bull cycle, swing high S at 100 (bar 1, confirmed on bar 3); A = 4 with high below 100.
    dict(id='M01', what='MSS slow crossing: 101, 102, then 104',
         bars=[B(95, 97), B(97, 99, h=100), B(99, 96), B(96, 95), B(95, 97), B(97, 101), B(101, 102), B(102, 104)],
         A=4, swings=[(1, 100, 3, 1)], mss={'v2.54': NONE, 'v2.55': 7}),
    dict(id='M02', what='MSS clean cross (unchanged)',
         bars=[B(95, 97), B(97, 99, h=100), B(99, 96), B(96, 95), B(95, 97), B(97, 104)],
         A=4, swings=[(1, 100, 3, 1)], mss={'v2.54': 5, 'v2.55': 5}),
    dict(id='M03', what='MSS wick then close exactly S + margin then beyond',
         bars=[B(95, 97), B(97, 99, h=100), B(99, 96), B(96, 95), B(95, 97), B(97, 99, h=108), B(99, 103), B(103, 104)],
         A=4, swings=[(1, 100, 3, 1)], mss={'v2.54': NONE, 'v2.55': 7}),
    dict(id='M04', what='C5: a pre-ARMED close 104 with margin 5 on that bar, margin 3 at A -> v2.54 drops the swing, '
                        'v2.55 keeps it (then a re-cross)',
         bars=[B(95, 97), B(97, 99, h=100), B(99, 96), B(96, 104), B(104, 97), B(97, 98), B(98, 106)],
         A=5, swings=[(1, 100, 3, 1)], margin=[3, 3, 3, 5, 3, 3, 3], mss={'v2.54': NA, 'v2.55': 6}),
    dict(id='M05', what='C5 reverse: pre-ARMED close 104 with margin 3 on that bar, margin 5 at A -> v2.54 keeps, '
                        'v2.55 drops',
         bars=[B(95, 97), B(97, 99, h=100), B(99, 96), B(96, 104), B(104, 97), B(97, 98), B(98, 106)],
         A=5, swings=[(1, 100, 3, 1)], margin=[3, 3, 3, 3, 3, 5, 3], mss={'v2.54': 6, 'v2.55': NA}),
    dict(id='M06', what='MSS candidate broken before A in both (close 105): the older unbroken swing is used',
         bars=[B(95, 97), B(97, 107, h=108), B(107, 96), B(96, 99, h=100), B(99, 96), B(96, 105), B(105, 97),
               B(97, 98), B(98, 104), B(104, 112)],
         A=7, swings=[(1, 108, 2, 1), (3, 100, 5, 1)], mss={'v2.54': 9, 'v2.55': 9}),
]


def main():
    ok = bad = 0
    for sc in SCEN:
        for d, side in ((1, 'bull'), (-1, 'bear')):
            for ver in ('v2.54', 'v2.55'):
                got = run(sc, d, ver == 'v2.55')
                for model in ('CISD', 'MSS'):
                    want = sc.get(model.lower())
                    if want is None:
                        continue
                    g, w = got[model], want[ver]
                    good = g == w
                    ok += good
                    bad += not good
                    if not good:
                        print(f'  FAIL {sc["id"]} {side} {ver} {model}: got {g}, want {w}  ({sc["what"]})')
        w = {m: sc[m.lower()] for m in ('CISD', 'MSS') if m.lower() in sc}
        diff = '  <- differs' if any(v['v2.54'] != v['v2.55'] for v in w.values()) else ''
        print(f'  {sc["id"]}  ' + '  '.join(f'{m} v2.54 {v["v2.54"]:>2} v2.55 {v["v2.55"]:>2}' for m, v in w.items())
              + f'   {sc["what"]}{diff}')
    print(f'{ok}/{ok + bad} checks as expected (bull + bear mirror, v2.54 + v2.55)')
    return 0 if bad == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
