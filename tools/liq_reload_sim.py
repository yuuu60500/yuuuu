"""Offline model of the liquidity lifecycle across a reload (BRI-09 / A-39).

A rebuild whose M5 window starts later must hold the same level state, and
so produce the same SWEEP / BROKEN events, as a run that started earlier -
inside the rebuild's comparable region (real warm-up end + 24 h).

Three ways of handling the stretch before the first M5 bar are modelled:
  v2.42  none: every level starts INTACT at the window start
  v2.46  M5 window trimmed to an H4 boundary + H4 pre-scan, threshold taken
         from window bar 0 (ATR 0 there -> pips fallback)
  v2.47  shared M5 untouched; replay on the M5 bars before the window, each
         with its own ATR(14); window bars 0..13 borrow replay bars for ATR
under two margin modes (PIPS, ATR_FRAC). Levels: PDH/PDL/PWH/PWL/PMH/PML from
H4 aggregated from the M5 bars; S-3 judgement (beyond by margin, close back
within N bars = SWEEP, else BROKEN).

    python3 tools/liq_reload_sim.py

It models the rules, not MQL5: a pass here does not replace compiling and
running the indicator.
"""
import datetime as dt
import random

PT = 0.00001
N_RECLAIM = 3
WARM = 100
PIPS_PTS = 3            # 0.3 pip on a 5-digit symbol
ATR_FRAC = 0.5
M5 = dt.timedelta(minutes=5)


def make_bars(seed):
    random.seed(seed)
    bars, t, px = [], dt.datetime(2026, 6, 1), 1.1000
    while t < dt.datetime(2026, 9, 30):
        if t.weekday() < 5:
            o = px
            c = o + random.gauss(0, 0.0004)
            h = max(o, c) + abs(random.gauss(0, 0.0002))
            l = min(o, c) - abs(random.gauss(0, 0.0002))
            bars.append((t, o, h, l, c))
            px = c
        t += M5
    return bars


def atr_series(bars):
    """ATR(14) exactly as SeriesComputeATR: 0 for the first 14 bars."""
    out = [0.0] * len(bars)
    for i in range(14, len(bars)):
        s = 0.0
        for k in range(i - 13, i + 1):
            pc = bars[k - 1][4]
            s += max(bars[k][2] - bars[k][3], abs(bars[k][2] - pc), abs(bars[k][3] - pc))
        out[i] = s / 14.0
    return out


def margin(atr, mode):
    if mode == 'ATR' and atr > 0:
        return round(ATR_FRAC * atr / PT)
    return PIPS_PTS


def pts(a, b):
    return round((a - b) / PT)


def h4_of(bars):
    out = {}
    for (t, o, h, l, c) in bars:
        k = t.replace(hour=t.hour // 4 * 4, minute=0)
        if k not in out:
            out[k] = [k, o, h, l, c]
        else:
            out[k][2] = max(out[k][2], h); out[k][3] = min(out[k][3], l); out[k][4] = c
    return [tuple(v) for v in sorted(out.values())]


def day(t): return t.replace(hour=0, minute=0)
def week(t): return day(t) - dt.timedelta(days=(day(t).weekday() + 1) % 7)   # Sunday start
def month(t): return t.replace(day=1, hour=0, minute=0)
def prev_month(t): return (month(t) - dt.timedelta(days=1)).replace(day=1)


def judge(L, b, mp, idx):
    """S-3 on one bar. Returns 'S' / 'B' when the level resolves."""
    if L['st'] in ('S', 'B', 'U'):
        return None
    t, o, h, l, c = b
    if L['st'] == 'I':
        if not (pts(h, L['p']) > mp if L['side'] > 0 else pts(l, L['p']) < -mp):
            return None
        L['st'], L['pi'] = 'P', idx
    back = pts(c, L['p']) <= 0 if L['side'] > 0 else pts(c, L['p']) >= 0
    if back:
        L['st'] = 'S'
    elif idx - L['pi'] >= N_RECLAIM:
        L['st'] = 'B'
    else:
        return None
    return L['st']


def run(allbars, H4, start, variant, mode):
    m5 = [b for b in allbars if b[0] >= start]
    if variant == 'v2.46':                      # trimmed to an H4 boundary
        while m5[0][0].hour % 4 or m5[0][0].minute:
            m5 = m5[1:]
    first = m5[0][0]
    watr = atr_series(m5)
    pre = [b for b in allbars if b[0] < first]  # what a replay can load
    patr = atr_series(pre)
    seam = pre[-14:] + m5[:14]                  # v2.47: window ATR for n < 14

    def win_atr(n):
        if variant == 'v2.47' and n < 14:
            s = 0.0
            for k in range(n - 13 + 14, n + 14 + 1):
                pc = seam[k - 1][4]
                s += max(seam[k][2] - seam[k][3], abs(seam[k][2] - pc), abs(seam[k][3] - pc))
            return s / 14.0
        return watr[n]

    h4 = [x for x in H4 if x[0] >= start - dt.timedelta(days=83)]
    keys, lv, ev, hp = [None] * 3, {}, [], 0
    for n, b in enumerate(m5):
        t = b[0]
        while hp < len(h4) and h4[hp][0] + dt.timedelta(hours=4) <= t:
            hp += 1
        cons = h4[:hp]

        def hilo(a, z):
            if not h4 or h4[0][0] > a:
                return None
            s = [x for x in cons if a <= x[0] < z]
            return (max(x[2] for x in s), min(x[3] for x in s)) if s else None

        for ki, k in enumerate((day(t), week(t), month(t))):
            if keys[ki] == k:
                continue
            keys[ki] = k
            if ki == 0:
                ds = sorted({day(x[0]) for x in cons if day(x[0]) < k and day(x[0]).weekday() != 6})
                r = hilo(ds[-1], ds[-1] + dt.timedelta(days=1)) if ds else None
                names = ('PDH', 'PDL')
            elif ki == 1:
                r = hilo(k - dt.timedelta(days=7), k); names = ('PWH', 'PWL')
            else:
                r = hilo(prev_month(t), k); names = ('PMH', 'PML')
            for side, nm in ((1, names[0]), (-1, names[1])):
                if r is None:
                    lv.pop(nm, None); continue
                L = dict(side=side, p=r[0] if side > 0 else r[1], st='I', pi=None, frm=k)
                if k < first and variant == 'v2.46':
                    mp0 = margin(watr[0], mode)
                    for x in cons:
                        if k <= x[0] < first and (pts(x[2], L['p']) > mp0 if side > 0 else pts(x[3], L['p']) < -mp0):
                            L['st'] = 'U'; break
                if k < first and variant == 'v2.47':
                    for r_i, pb in enumerate(pre):
                        if pb[0] >= k and judge(L, pb, margin(patr[r_i], mode), r_i - len(pre)):
                            break
                lv[nm] = L
        for nm, L in lv.items():
            k = judge(L, b, margin(win_atr(n), mode), n)
            if k and n >= WARM:
                ev.append((t, nm, k, L['frm']))
    return ev, m5[WARM][0]


def continuous(allbars, H4, mode):
    """The reference: one run started long before any window checked."""
    ev, _ = run(allbars, H4, dt.datetime(2026, 7, 1), 'v2.47', mode)
    return ev


if __name__ == '__main__':
    starts = (dt.datetime(2026, 9, 2, 9, 5), dt.datetime(2026, 9, 9, 2, 35), dt.datetime(2026, 9, 16, 5, 50))
    seeds = range(1, 7)
    data = {s: make_bars(s) for s in seeds}
    H4s = {s: h4_of(data[s]) for s in seeds}
    for mode in ('PIPS', 'ATR'):
        refs = {s: continuous(data[s], H4s[s], mode) for s in seeds}
        for variant in ('v2.42', 'v2.46', 'v2.47'):
            bad = total = 0
            example = None
            for s in seeds:
                for st in starts:
                    ev, wend = run(data[s], H4s[s], st, variant, mode)
                    lim = wend + dt.timedelta(hours=24)
                    a = {e for e in refs[s] if e[0] >= lim}
                    b = {e for e in ev if e[0] >= lim}
                    total += 1
                    if a != b:
                        bad += 1
                        if example is None:
                            d = sorted(a ^ b)[0]
                            example = f"seed {s} start {st:%m.%d %H:%M}: {d[1]} {d[2]} at {d[0]:%m.%d %H:%M} ({'rebuild only' if d in b else 'continuous only'})"
            print(f"{mode:4s} {variant}  rebuilds {total:2d}  mismatching {bad:2d}" + (f"   e.g. {example}" if example else ""))
