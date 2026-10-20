"""BRI-08 (v2.55): CISD / MSS on the first effective close beyond the threshold - offline model of the
paired scenarios in docs/02 "BRI-08 修订稿 2". Not the MQL implementation; it fixes what each scenario must give.

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
MSS swings come from detect_swings() (SwingDetect: left / right 2, strict left, non-strict right), never hand-written;
each MSS scenario states the swings confirmed at A and the check fails when the bars do not produce exactly those.
process() runs bar by bar in the indicator's order - Phase 4 (the active cycle, n > A) before Phase 5 (an ARMED bar
closes the old cycle and freezes the new one) - and returns the event list, so "one mark per cycle and model" is
counted, not inferred from a first hit (reviewer, v2.55 definition review, 2026-10-20).

    python3 tools/bri08_sim.py            all scenarios, both directions, both versions
"""
import sys

NA = 'NA'          # reference rejected at ARMED: the model is N/A for the cycle
NONE = '-'         # reference kept, no confirmation inside the bars given
MODELS = ('CISD', 'MSS')


def cdir(b):
    o, _, _, c = b
    return (c > o) - (c < o)


def brk(d, close, level, mp):
    return (close - level > mp) if d > 0 else (close - level < -mp)


def detect_swings(bars, L=2, R=2):
    """HMI_SwingEngine.mqh SwingDetect: at bar n the pivot c = n - R; strict '>' on the left, '>=' on the right.
    -> [(pivot index, price, confirm bar index, +1 high / -1 low)]"""
    out = []
    for n in range(len(bars)):
        c = n - R
        if c - L < 0 or c <= 0 or c >= n:
            continue
        hi = all(bars[c][1] > bars[j][1] for j in range(c - L, c)) and \
            all(bars[c][1] >= bars[j][1] for j in range(c + 1, c + R + 1))
        lo = all(bars[c][2] < bars[j][2] for j in range(c - L, c)) and \
            all(bars[c][2] <= bars[j][2] for j in range(c + 1, c + R + 1))
        if hi:
            out.append((c, bars[c][1], n, 1))
        if lo:
            out.append((c, bars[c][2], n, -1))
    return out


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
    for (i, price, conf, sd) in swings:
        if i < lo or sd != d or conf > A:                     # C2, C3, C1
            continue
        if (d > 0 and price <= bars[A][1]) or (d < 0 and price >= bars[A][2]):   # C4
            continue
        if any(brk(d, bars[m][3], price, margin[m] if v255 else margin[A]) for m in range(i + 1, A + 1)):   # C5
            continue
        if best is None or i > best[0]:
            best = (i, price)
    return None if best is None else best[1]


def process(sc, d, v255):
    """Bar by bar in the indicator's order: Phase 4 (the active cycle, n > A) before Phase 5 (ARMED on bar n closes the
    old cycle and freezes the new one's references). -> (events [(cycle no, model, bar)], cycles)"""
    bars, margin = sc['bars'], sc.get('margin') or [3] * len(sc['bars'])
    if d < 0:
        bars = [(-o, -l, -h, -c) for (o, h, l, c) in bars]
    swings = detect_swings(bars)
    armed = sc.get('armed') or [sc['A']]
    cycles, ev, act = [], [], None
    for n in range(len(bars)):
        if act is not None and n > act['A']:
            for m in MODELS:
                lvl = act[m]
                if lvl is None or m in act['done']:
                    continue
                prev_ok = (bars[n - 1][3] - lvl <= 0) if d > 0 else (bars[n - 1][3] - lvl >= 0)
                if brk(d, bars[n][3], lvl, margin[n]) and (v255 or prev_ok):
                    act['done'].add(m)
                    ev.append((act['no'], m, n))
        if n in armed:
            act = dict(no=len(cycles) + 1, A=n, done=set(),
                       CISD=cisd_ref(bars, d, n, 12, margin, v255),
                       MSS=mss_ref(bars, d, n, swings, 60, margin, v255))
            cycles.append(act)
    return ev, cycles, swings


def outcome(sc, d, v255, model):
    """single-cycle form: the confirmation bar, NA (reference rejected) or NONE"""
    ev, cycles, _ = process(sc, d, v255)
    if cycles[0][model] is None:
        return NA
    hit = [n for (c, m, n) in ev if c == 1 and m == model]
    return hit[0] if hit else NONE


def B(o, c, h=None, l=None):
    return (o, max(o, c) + 1 if h is None else h, min(o, c) - 1 if l is None else l, c)


# Bull form. CISD level L = 100 (open of the oldest bar of the bearish run before A); margin 3 unless given.
RUN = [B(96, 99), B(100, 97), B(97, 95)]           # 0 bull, 1-2 bearish run (k = 1, L = open[1] = 100)
PRE = [(95, 98, 94, 97), (97, 99, 96, 98), (98, 100, 96, 97), (97, 98, 95, 96), (96, 97, 94, 95)]
MSS_C5 = PRE + [(95, 105, 94, 104), (104, 106, 96, 97), (97, 99, 96, 98), (98, 107, 97, 106)]   # reviewer, 2026-10-20
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
    dict(id='S20', what='B8-SHIFT: 101, 104 (v2.55), dip 98, 104 again (v2.54 on the re-cross)',
         bars=RUN + [B(95, 99), B(99, 101), B(101, 104), B(104, 98), B(98, 104)], A=3,
         cisd={'v2.54': 7, 'v2.55': 5}),
    # MSS: swings come from detect_swings() (SwingDetect, left / right 2), never hand-written. PRE gives the swing
    # high 100 at bar 2, confirmed at bar 4 (left highs 98, 99; right 98, 97); ARMED bars keep their high below 100.
    dict(id='M01', what='MSS slow crossing: 101, 102, then 104',
         bars=PRE + [B(95, 97), B(97, 101), B(101, 102), B(102, 104)], A=5, highs=[(2, 100, 4)],
         mss={'v2.54': NONE, 'v2.55': 8}),
    dict(id='M02', what='MSS clean cross (unchanged)',
         bars=PRE + [B(95, 97), B(97, 104)], A=5, highs=[(2, 100, 4)],
         mss={'v2.54': 6, 'v2.55': 6}),
    dict(id='M03', what='MSS wick (high 108, close 99), close exactly S + margin (103), then 104',
         bars=PRE + [B(95, 97), B(97, 99, h=108), B(99, 103), B(103, 104)], A=5, highs=[(2, 100, 4)],
         mss={'v2.54': NONE, 'v2.55': 8}),
    dict(id='M04', what='C5 keeps (reviewer fixture): bar 5 closes 104 after the swing is confirmed, its own margin 5, '
                        'margin 3 at A -> v2.54 drops the swing, v2.55 keeps it; bar 6 high 106 is not confirmed at A',
         bars=MSS_C5, A=7, highs=[(2, 100, 4)], margin=[3, 3, 3, 3, 3, 5, 3, 3, 3],
         mss={'v2.54': NA, 'v2.55': 8}),
    dict(id='M05', what='C5 drops (reviewer fixture): bar 5 own margin 3, margin 5 at A -> v2.54 keeps, v2.55 drops',
         bars=MSS_C5, A=7, highs=[(2, 100, 4)], margin=[3, 3, 3, 3, 3, 3, 3, 5, 3],
         mss={'v2.54': 8, 'v2.55': NA}),
    dict(id='M06', what='newer swing 100 eaten before A (close 105), the older 108 is used; bar 12 high 107 '
                        'not confirmed at A',
         bars=[B(100, 103), B(103, 105), B(105, 107, h=108), B(107, 104), B(104, 100), B(100, 94), B(94, 95),
               B(95, 97), B(97, 99, h=100), B(99, 96), B(96, 95), B(95, 105), B(105, 97, h=107), B(97, 98),
               B(98, 104), B(104, 112)],
         A=13, highs=[(2, 108, 4), (8, 100, 10)], mss={'v2.54': 15, 'v2.55': 15}),
    # Two cycles: the old cycle is checked on the new ARMED bar (Phase 4) before that bar arms the new one (Phase 5).
    dict(id='C01', what='cycle switch: v2.55 confirms cycle 1 early and cycle 2 on its own level; v2.54 confirms cycle 1 '
                        'on the bar that arms cycle 2, and cycle 2 never',
         bars=RUN + [B(95, 99), B(99, 101), B(101, 104), B(104, 98), B(98, 105), B(105, 108)], armed=[3, 7],
         models=('CISD',), events={'v2.54': [(1, 'CISD', 7)], 'v2.55': [(1, 'CISD', 5), (2, 'CISD', 8)]}),
    dict(id='C02', what='cycle switch on the same level: the bar arming cycle 2 confirms cycle 1 (v2.55); cycle 2 '
                        'references the same run, already broken on its ARMED bar -> N/A, no second mark',
         bars=RUN + [B(95, 99), B(99, 101), B(101, 104), B(104, 99), B(99, 104)], armed=[3, 5],
         models=('CISD',), events={'v2.54': [(2, 'CISD', 7)], 'v2.55': [(1, 'CISD', 5)]}),
    dict(id='C03', what='max 1 per cycle over the whole series: three crosses, one mark each version',
         bars=RUN + [B(95, 99), B(99, 104), B(104, 98), B(98, 105), B(105, 97), B(97, 106)], armed=[3],
         models=('CISD',), events={'v2.54': [(1, 'CISD', 4)], 'v2.55': [(1, 'CISD', 4)]}),
]


def main():
    ok = bad = 0

    def check(good, msg):
        nonlocal ok, bad
        ok += good
        bad += not good
        if not good:
            print('  FAIL ' + msg)

    for sc in SCEN:
        for d, side in ((1, 'bull'), (-1, 'bear')):
            for ver in ('v2.54', 'v2.55'):
                v255 = ver == 'v2.55'
                ev, cycles, swings = process(sc, d, v255)
                # invariants: at most one mark per cycle and model; only after that cycle's ARMED bar
                seen = [(c, m) for (c, m, _) in ev]
                check(len(seen) == len(set(seen)), f'{sc["id"]} {side} {ver}: a model marked twice in one cycle {ev}')
                check(all(n > cycles[c - 1]['A'] for (c, _, n) in ev), f'{sc["id"]} {side} {ver}: mark on or before A')
                if 'highs' in sc:                     # the MSS fixture's swings are reachable and the ones stated
                    got = [(i, p, cf) for (i, p, cf, sd) in swings if sd == d and cf <= sc['A']]
                    want = [(i, p * d, cf) for (i, p, cf) in sc['highs']]
                    check(got == want, f'{sc["id"]} {side}: confirmed swings at A {got}, stated {want}')
                if 'events' in sc:
                    got = [e for e in ev if e[1] in sc['models']]
                    check(got == sc['events'][ver], f'{sc["id"]} {side} {ver}: events {got}, want {sc["events"][ver]}')
                for model in MODELS:
                    want = sc.get(model.lower())
                    if want is not None:
                        g = outcome(sc, d, v255, model)
                        check(g == want[ver], f'{sc["id"]} {side} {ver} {model}: got {g}, want {want[ver]} ({sc["what"]})')
        if 'events' in sc:
            w = sc['events']
            print(f'  {sc["id"]}  events v2.54 {w["v2.54"]}  v2.55 {w["v2.55"]}   {sc["what"]}')
            continue
        w = {m: sc[m.lower()] for m in MODELS if m.lower() in sc}
        diff = '  <- differs' if any(v['v2.54'] != v['v2.55'] for v in w.values()) else ''
        print(f'  {sc["id"]}  ' + '  '.join(f'{m} v2.54 {v["v2.54"]:>2} v2.55 {v["v2.55"]:>2}' for m, v in w.items())
              + f'   {sc["what"]}{diff}')
    print(f'{ok}/{ok + bad} checks as expected ({len(SCEN)} scenarios, bull + bear mirror, v2.54 + v2.55; '
          f'one mark per cycle and model, marks after A, MSS swings from SwingDetect)')
    return 0 if bad == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
