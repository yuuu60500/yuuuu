"""Offline model of the H4 structure layer, v2.52 vs v2.53 (A-33 BOS de-duplication).

Mirrors, function for function, the H4 half of Phase 0:

  SwingDetect          fractal swings, L = R = 2, confirm_time = close of bar n
  H4DetectBreak        primary = latest confirmed, unprocessed swing; close beyond it by the margin
  H4ConsumeSameDirBroken   (v2.53 only) every other same-direction swing this close breaks
  H4ContextOnBar       RANGE / BULLISH / BEARISH / TRANSITION machine, CHOCH freshness, timeout
  FvgDetect, POIOnBar, POIPush, POIInvalidateOnBar   the H4 POI chain (trend direction gates POIs)

Defaults as shipped: break margin 0.3 pip (5-digit symbol: 3 points), swings 2/2,
OB->FVG 3 bars, POI window 12, POI age 120 H4 bars, transition timeout 18 H4 bars.
M5 is not modelled: POI touches, sessions, blocks and the six models need the M5
chain and are compared in MT5 (ReloadTest -Source <v2.52> -Versus <v2.53>).

    python3 tools/h4_dedup_sim.py                       scenarios (the required checks)
    python3 tools/h4_dedup_sim.py --replay <H1 csv>     real-data replay: H1 -> H4, both versions,
                                                        every difference attributed or flagged

The --replay CSV is any "time,Open,High,Low,Close[,Volume]" hourly file; the one
used for the v2.53 evidence is the EURUSD sample shipped inside backtesting.py
0.6.6 (backtesting/test/EURUSD.csv, 2017-04-19 .. 2018-02-07, sha256 81e97790...).

It models the rules, not MQL5: a pass here does not replace compiling and
running the indicator.
"""
import csv
import datetime as dt
import math
import sys

POINT = 0.00001
MARGIN_PTS = 3                       # 0.3 pip
SW_L = SW_R = 2
OB_FVG_MAX = 3
POI_WINDOW = 12
POI_STORE = 64
POI_AGE = 120
TRANS_MAX = 18
H4 = 4 * 3600
MAX_SW = 128
MAX_FVG = 128

RANGE, BULL_CTX, BEAR_CTX, TRANS = "RANGE", "BULLISH", "BEARISH", "TRANSITION"
UP, DOWN = 1, -1


def mround(x):
    return int(math.floor(abs(x) + 0.5)) * (1 if x >= 0 else -1)


def pts(a, b):
    return mround((a - b) / POINT)


def break_up(price, level, mp):
    return pts(price, level) > mp


def break_down(price, level, mp):
    return pts(price, level) < -mp


def cdir(b):
    return UP if b[4] > b[1] else (DOWN if b[4] < b[1] else 0)


def tstr(t):
    return dt.datetime.fromtimestamp(t, dt.timezone.utc).strftime("%Y.%m.%d %H:%M")


class Engine:
    """bars: list of (open_time, open, high, low, close)."""

    def __init__(self, dedup):
        self.dedup = dedup
        self.sw = []            # dicts: dir, bar_time, confirm, price, swept
        self.fvg = []
        self.poi = []
        self.ctx, self.pending, self.strength, self.messy = RANGE, 0, 0, False
        self.ctx_time, self.ctx_bars = 0, 0
        self.ctx_rows, self.dedup_rows, self.poi_rows = [], [], []
        self.state_after = []   # ctx state after each H4 bar

    # --- swings / fvg ------------------------------------------------------
    def swing_detect(self, r, n):
        c = n - SW_R
        if c - SW_L < 0 or c <= 0 or c >= n:
            return
        hi_ok = lo_ok = True
        for j in range(c - SW_L, c):
            if r[c][2] <= r[j][2]: hi_ok = False
            if r[c][3] >= r[j][3]: lo_ok = False
        for j in range(c + 1, c + SW_R + 1):
            if r[c][2] < r[j][2]: hi_ok = False
            if r[c][3] > r[j][3]: lo_ok = False
        conf = r[n][0] + H4
        for ok, d, px in ((hi_ok, UP, r[c][2]), (lo_ok, DOWN, r[c][3])):
            if ok:
                if len(self.sw) >= MAX_SW:
                    self.sw.pop(0)
                self.sw.append(dict(dir=d, bar_time=r[c][0], confirm=conf, price=px, swept=False))

    def fvg_detect(self, r, n):
        if n < 2:
            return None
        f = None
        if r[n][3] > r[n - 2][2]:
            f = dict(dir=UP, lo=r[n - 2][2], hi=r[n][3])
        elif r[n][2] < r[n - 2][3]:
            f = dict(dir=DOWN, lo=r[n][2], hi=r[n - 2][3])
        if f is None or pts(f["hi"], f["lo"]) <= 0:
            return None
        f["bar_time"], f["confirm"] = r[n][0], r[n][0] + H4
        if len(self.fvg) >= MAX_FVG:
            self.fvg.pop(0)
        self.fvg.append(f)
        return f

    # --- structure ---------------------------------------------------------
    def last_unswept(self, d, vis):
        for i in range(len(self.sw) - 1, -1, -1):
            s = self.sw[i]
            if s["dir"] == d and not s["swept"] and s["confirm"] <= vis:
                return i
        return -1

    def detect_break(self, r, h):
        vis = r[h][0] + H4
        ih = self.last_unswept(UP, vis)
        if ih >= 0 and break_up(r[h][4], self.sw[ih]["price"], MARGIN_PTS):
            return UP, ih
        il = self.last_unswept(DOWN, vis)
        if il >= 0 and break_down(r[h][4], self.sw[il]["price"], MARGIN_PTS):
            return DOWN, il
        return 0, -1

    def consume_same_dir(self, r, h, d, primary):
        vis = r[h][0] + H4
        extra = []
        for i, s in enumerate(self.sw):
            if i == primary or s["dir"] != d or s["swept"] or s["confirm"] > vis:
                continue
            brk = break_up(r[h][4], s["price"], MARGIN_PTS) if d == UP else break_down(r[h][4], s["price"], MARGIN_PTS)
            if brk:
                s["swept"] = True
                extra.append((d, s["bar_time"], s["price"]))
        return extra

    def enter(self, st, pending, t):
        self.ctx, self.pending, self.ctx_time, self.ctx_bars, self.messy = st, pending, t, 0, False

    def ctx_dir(self):
        return UP if self.ctx == BULL_CTX else (DOWN if self.ctx == BEAR_CTX else 0)

    def log(self, kind, d, t, sw, close, also):
        self.ctx_rows.append(dict(kind=kind, dir=d, bar=t, ctx=self.ctx, str=self.strength, messy=self.messy,
                                  swing=(sw["bar_time"] if sw else 0), swing_px=(sw["price"] if sw else 0.0),
                                  close=close, also=also))

    def context_on_bar(self, r, h):
        self.ctx_bars += 1
        t = r[h][0] + H4
        if self.ctx == TRANS and self.ctx_bars > TRANS_MAX:
            self.enter(RANGE, 0, t)
            self.log("TIMEOUT", 0, t, None, r[h][4], 0)
            return
        d, bi = self.detect_break(r, h)
        if d == 0:
            return
        sw = self.sw[bi]
        brk_confirm = sw["confirm"]
        sw["swept"] = True
        extra = self.consume_same_dir(r, h, d, bi) if self.dedup else []
        kind = ""
        if self.ctx == RANGE:
            self.enter(BULL_CTX if d == UP else BEAR_CTX, 0, t); self.strength = 1; kind = "BOS"
        elif self.ctx == BULL_CTX:
            if d == UP: self.strength += 1; kind = "BOS"
            else: self.enter(TRANS, DOWN, t); self.strength = 0; kind = "CHOCH"
        elif self.ctx == BEAR_CTX:
            if d == DOWN: self.strength += 1; kind = "BOS"
            else: self.enter(TRANS, UP, t); self.strength = 0; kind = "CHOCH"
        else:
            fresh = brk_confirm > self.ctx_time
            if d == self.pending:
                if not fresh:
                    kind = "TRANS_SAMELEG"
                else:
                    self.enter(BULL_CTX if d == UP else BEAR_CTX, 0, t); self.strength = 1; kind = "TRANS_OK"
            else:
                self.enter(BULL_CTX if d == UP else BEAR_CTX, 0, t); self.strength = 1; self.messy = True; kind = "TRANS_FAIL"
        self.log(kind, d, t, sw, r[h][4], len(extra))
        if extra:
            self.dedup_rows.append(dict(bar=t, kind=kind, dir=d, primary=(sw["bar_time"], sw["price"]), extra=extra))

    # --- POI ---------------------------------------------------------------
    def poi_push(self, p):
        cap = min(POI_STORE, max(1, POI_WINDOW))
        if len(self.poi) >= cap:
            drop = len(self.poi) - cap
            q = self.poi[drop]
            if not q["out"]:
                self.poi_rows.append(("OUT", q["origin"], q["dir"], p["confirm"]))
            if q["state"] != "INVALID":
                q["state"] = "EXPIRED"
            q["out"] = True
        if len(self.poi) >= POI_STORE:
            k = 0
            while k < len(self.poi) - 1 and not self.poi[k]["out"]:
                k += 1
            if not self.poi[k]["out"]:
                k = 0
            self.poi.pop(k)
        self.poi.append(p)
        self.poi_rows.append(("NEW", p["origin"], p["dir"], p["confirm"]))

    def poi_on_bar(self, r, h, f):
        if f is None or f["dir"] != self.ctx_dir():
            return
        d = f["dir"]
        for o in range(h - 1, max(0, h - OB_FVG_MAX) - 1, -1):
            if cdir(r[o]) != -d:
                continue
            gap = pts(f["lo"], r[o][2]) if d == UP else pts(r[o][3], f["hi"])
            if gap > 0:
                continue
            if any(q["origin"] == r[o][0] and q["dir"] == d for q in self.poi):
                return
            self.poi_push(dict(dir=d, origin=r[o][0], confirm=f["confirm"], hi=r[o][2], lo=r[o][3],
                               state="ACTIVE", out=False))
            return

    def poi_invalidate(self, r, h):
        t = r[h][0] + H4
        for q in self.poi:
            if q["state"] not in ("ACTIVE", "TOUCHED") or q["confirm"] > r[h][0]:
                continue
            dead = break_down(r[h][4], q["lo"], MARGIN_PTS) if q["dir"] == UP else break_up(r[h][4], q["hi"], MARGIN_PTS)
            if dead:
                q["state"] = "INVALID"
                self.poi_rows.append(("INVALID", q["origin"], q["dir"], t))
        for q in self.poi:
            if q["state"] == "ACTIVE" and t - q["confirm"] > POI_AGE * H4:
                q["state"] = "EXPIRED"
                self.poi_rows.append(("EXPIRED", q["origin"], q["dir"], t))

    # --- Phase 0, one closed H4 bar ----------------------------------------
    def process(self, r, h):
        self.swing_detect(r, h)
        self.context_on_bar(r, h)
        f = self.fvg_detect(r, h)
        self.poi_on_bar(r, h, f)
        self.poi_invalidate(r, h)
        self.state_after.append((r[h][0] + H4, self.ctx))


def run(bars, dedup):
    e = Engine(dedup)
    for h in range(len(bars)):
        e.process(bars, h)
    return e


# ---- comparison and attribution (the same rules ReloadTest -Versus applies) --
def ctx_key(row, with_str=True):
    k = (row["bar"], row["kind"], row["dir"], row["ctx"], row["swing"], round(row["swing_px"], 5), row["messy"])
    return k + ((row["str"],) if with_str else ())


def multiset_diff(a, b):
    from collections import Counter
    ca, cb = Counter(a), Counter(b)
    return list((ca - cb).elements()), list((cb - ca).elements())


def attribute(old, new):
    """old = v2.52 engine, new = v2.53 engine. Returns a report dict."""
    t_dedup = min([d["bar"] for d in new.dedup_rows], default=None)
    processed_new = {}                     # (dir, swing time) -> bar it was processed in v2.53
    for r in new.ctx_rows:
        if r["swing"]:
            processed_new.setdefault((r["dir"], r["swing"]), r["bar"])
    for d in new.dedup_rows:
        for (dd, st, _) in d["extra"]:
            processed_new.setdefault((dd, st), d["bar"])

    only_old, only_new = multiset_diff([ctx_key(r) for r in old.ctx_rows], [ctx_key(r) for r in new.ctx_rows])
    # same event, strength renumbered
    so, sn = multiset_diff([ctx_key(r, False) for r in old.ctx_rows], [ctx_key(r, False) for r in new.ctx_rows])
    renumbered = len(only_old) - len(so)

    cls = {"suppressed duplicate": 0, "primary re-referenced": 0, "strength renumbered": renumbered,
           "path changed after a de-dup": 0, "UNEXPLAINED": 0}
    unexplained = []
    # same bar, same event, same resulting state, another primary swing: v2.52's primary
    # had already been processed by v2.53 (so it was a duplicate there), and v2.53 names
    # the next swing this close breaks for the first time
    same_event = lambda k: (k[0], k[1], k[2], k[3], k[6])
    new_by_event = {}
    for k in sn:
        new_by_event.setdefault(same_event(k), []).append(k)
    paired_new = set()
    for k in so:
        bar, kind, d, ctx, swing = k[0], k[1], k[2], k[3], k[4]
        p = processed_new.get((d, swing))
        dup = bool(swing) and p is not None and p < bar
        mate = [x for x in new_by_event.get(same_event(k), []) if x not in paired_new]
        if dup and mate:
            cls["primary re-referenced"] += 1; paired_new.add(mate[0])
        elif dup:
            cls["suppressed duplicate"] += 1
        elif t_dedup is not None and bar >= t_dedup:
            cls["path changed after a de-dup"] += 1
        else:
            cls["UNEXPLAINED"] += 1; unexplained.append(("v2.52 only", k))
    for k in sn:
        if k in paired_new:
            continue
        if t_dedup is not None and k[0] >= t_dedup:
            cls["path changed after a de-dup"] += 1
        else:
            cls["UNEXPLAINED"] += 1; unexplained.append(("v2.53 only", k))

    # H4 state timeline
    div, cur = [], None
    for (t, a), (_, b) in zip(old.state_after, new.state_after):
        if a != b and cur is None:
            cur = [t, t, a, b]
        elif a != b:
            cur[1] = t
        elif cur is not None:
            div.append(cur); cur = None
    if cur is not None:
        div.append(cur)
    t_state = div[0][0] if div else None

    po, pn = multiset_diff(old.poi_rows, new.poi_rows)
    poi_unexpl = [x for x in po + pn if t_state is None or x[3] < t_state]
    return dict(t_dedup=t_dedup, cls=cls, unexplained=unexplained, div=div, t_state=t_state,
                poi_old=po, poi_new=pn, poi_unexpl=poi_unexpl)


# ---- scenarios ---------------------------------------------------------------
def build(rows, t0=dt.datetime(2026, 9, 7, 0, 0, tzinfo=dt.timezone.utc)):
    out, prev = [], None
    for i, (hi, lo, cl) in enumerate(rows):
        op = prev if prev is not None else cl
        out.append((int(t0.timestamp()) + i * H4, op, max(hi, op, cl), min(lo, op, cl), cl))
        prev = cl
    return out


def mirror(rows, axis=2.2):
    return [(round(axis - lo, 5), round(axis - hi, 5), round(axis - cl, 5)) for (hi, lo, cl) in rows]


# three confirmed, unprocessed highs 1.1000 / 1.1010 / 1.1020, one push to 1.1050,
# price stays above them; then a new swing high (1.1080) forms and is broken.
PUSH = [
    (1.0960, 1.0940, 1.0950), (1.0970, 1.0945, 1.0960), (1.1000, 1.0950, 1.0965),   # 2: high A 1.1000
    (1.0985, 1.0950, 1.0960), (1.0980, 1.0945, 1.0955), (1.0990, 1.0950, 1.0970),
    (1.1010, 1.0960, 1.0985),                                                       # 6: high B 1.1010
    (1.1000, 1.0960, 1.0975), (1.0995, 1.0955, 1.0965), (1.1005, 1.0960, 1.0980),
    (1.1020, 1.0965, 1.0990),                                                       # 10: high C 1.1020
    (1.1010, 1.0970, 1.0985), (1.1005, 1.0965, 1.0980),
    (1.1060, 1.0980, 1.1050),                                                       # 13: the push, closes beyond A B C
    (1.1058, 1.1040, 1.1045), (1.1048, 1.1035, 1.1040),                             # 14-15: stays above, no new push
    (1.1052, 1.1030, 1.1045), (1.1080, 1.1040, 1.1060),                             # 17: new high D 1.1080
    (1.1070, 1.1045, 1.1055), (1.1065, 1.1040, 1.1050),
    (1.1100, 1.1050, 1.1095),                                                       # 20: breaks D (and the 1.1060 push top)
    (1.1098, 1.1070, 1.1090), (1.1095, 1.1065, 1.1085),                             # 21-22: stays above
]
# v2.52 re-counts on 14 (B, crossed on 13) and 21 (the 1.1060 push top, crossed on 20). On 15 and
# 22 a newer swing confirmed that very bar (13, 20) is the latest and shadows the rest - so A
# 1.1000 is still unprocessed in v2.52 at the end, a stale level waiting to be counted.
# an older lower high A 1.1000 and a newer higher high B 1.1020 (latest): a close between them
# is not a structure event in either version; the close beyond B is one event and takes A with it
SHADOW = [
    (1.0960, 1.0940, 1.0950), (1.0970, 1.0945, 1.0960), (1.1000, 1.0950, 1.0965),   # 2: A 1.1000
    (1.0985, 1.0950, 1.0960), (1.0980, 1.0945, 1.0955), (1.0990, 1.0950, 1.0975),
    (1.1020, 1.0960, 1.0990),                                                       # 6: B 1.1020 (latest)
    (1.1010, 1.0960, 1.0985), (1.1005, 1.0955, 1.0980),
    (1.1012, 1.0990, 1.1010),                                                       # 9: closes beyond A, below B
    (1.1015, 1.0995, 1.1005), (1.1040, 1.1000, 1.1030),                             # 11: closes beyond B
    (1.1038, 1.1015, 1.1025), (1.1035, 1.1012, 1.1020),
]


def events(e, kinds=("BOS", "CHOCH", "TRANS_OK", "TRANS_FAIL")):
    return [(r["bar"], r["kind"], r["dir"], r["also"]) for r in e.ctx_rows if r["kind"] in kinds]


def idx_of(bars, t):
    return next(i for i, b in enumerate(bars) if b[0] + H4 == t)


def scenario(name, rows, expect_new, expect_old_extra):
    bars = build(rows)
    old, new = run(bars, False), run(bars, True)
    ev_new = [(idx_of(bars, t), k, d, a) for (t, k, d, a) in events(new)]
    ev_old = [(idx_of(bars, t), k, d) for (t, k, d, a) in events(old)]
    rep = attribute(old, new)
    errs = []
    if ev_new != expect_new:
        errs.append(f"v2.53 events {ev_new} != {expect_new}")
    extra_old = [e for e in ev_old if (e[0], e[1], e[2]) not in [(x[0], x[1], x[2]) for x in ev_new]]
    if [e[0] for e in extra_old] != expect_old_extra:
        errs.append(f"v2.52-only event bars {[e[0] for e in extra_old]} != {expect_old_extra}")
    if rep["cls"]["UNEXPLAINED"]:
        errs.append(f"unexplained differences {rep['unexplained']}")
    print(f"{'PASS' if not errs else 'FAIL'}  {name}")
    print(f"        v2.53 events (bar, kind, dir, also): {ev_new}")
    print(f"        v2.52 events (bar, kind, dir):       {ev_old}")
    print(f"        attribution: {rep['cls']}")
    for e in errs:
        print(f"        !! {e}")
    return not errs


def prefix_stable(bars, dedup, step=25):
    """No repaint: a run cut at bar k must hold exactly the events the full run had by then."""
    full = run(bars, dedup)
    for k in range(SW_L + SW_R + 3, len(bars) + 1, step):
        part = run(bars[:k], dedup)
        cut = bars[k - 1][0] + H4
        if [ctx_key(r) for r in part.ctx_rows] != [ctx_key(r) for r in full.ctx_rows if r["bar"] <= cut]:
            return False, k
        if part.poi_rows != [p for p in full.poi_rows if p[3] <= cut]:
            return False, k
    return True, None


def load_h1(path):
    rows = []
    with open(path) as f:
        rd = csv.reader(f)
        next(rd)
        for r in rd:
            t = dt.datetime.strptime(r[0], "%Y-%m-%d %H:%M:%S").replace(tzinfo=dt.timezone.utc)
            rows.append((int(t.timestamp()), float(r[1]), float(r[2]), float(r[3]), float(r[4])))
    h4 = {}
    for (t, o, hi, lo, c) in rows:
        k = t - t % H4
        if k not in h4:
            h4[k] = [k, o, hi, lo, c]
        else:
            b = h4[k]; b[2] = max(b[2], hi); b[3] = min(b[3], lo); b[4] = c
    return [tuple(v) for k, v in sorted(h4.items())]


def shift_stability(bars, dedup, shifts=range(1, 31), settle=60):
    """Live vs rebuild, H4 side: a rebuild's H4 window starts later than the run that
    produced the live rows. Compare a run started k bars later with the base run on
    every event after `settle` bars of the shorter history. Returns (shifts with any
    difference, differing rows in total)."""
    base = run(bars, dedup)
    bad, rows = 0, 0
    for k in shifts:
        part = run(bars[k:], dedup)
        cut = bars[k + settle][0] + H4
        a = [ctx_key(r) for r in base.ctx_rows if r["bar"] > cut]
        b = [ctx_key(r) for r in part.ctx_rows if r["bar"] > cut]
        x, y = multiset_diff(a, b)
        if x or y:
            bad += 1; rows += len(x) + len(y)
    return bad, rows


def replay(path):
    bars = load_h1(path)
    print(f"replay {path}: {len(bars)} H4 bars {tstr(bars[0][0])} .. {tstr(bars[-1][0])}")
    old, new = run(bars, False), run(bars, True)
    rep = attribute(old, new)
    n_ev = lambda e, k: sum(1 for r in e.ctx_rows if r["kind"] == k)
    print("\nstructure events          v2.52   v2.53")
    for k in ("BOS", "CHOCH", "TRANS_OK", "TRANS_FAIL", "TRANS_SAMELEG", "TIMEOUT"):
        print(f"  {k:22s} {n_ev(old, k):6d}  {n_ev(new, k):6d}")
    print(f"  de-duplicated bars           -  {len(new.dedup_rows):6d}   (extra swings processed: {sum(len(d['extra']) for d in new.dedup_rows)})")
    print(f"  max strength           {max([r['str'] for r in old.ctx_rows] or [0]):6d}  {max([r['str'] for r in new.ctx_rows] or [0]):6d}")
    print(f"\nfirst de-dup bar: {tstr(rep['t_dedup']) if rep['t_dedup'] else '-'}")
    print("CTX differences (v2.52 vs v2.53), by cause:")
    for k, v in rep["cls"].items():
        print(f"  {k:32s} {v}")
    print(f"\nH4 state divergence intervals: {len(rep['div'])}")
    for (a, b, so, sn) in rep["div"][:20]:
        print(f"  {tstr(a)} .. {tstr(b)}   v2.52 {so:10s} v2.53 {sn}")
    tot = sum(1 for (t, a), (_, b) in zip(old.state_after, new.state_after) if a != b)
    print(f"  H4 bars in a different state: {tot} of {len(bars)}")
    print(f"\nPOI events only in v2.52: {len(rep['poi_old'])}, only in v2.53: {len(rep['poi_new'])}")
    for x in sorted(rep["poi_old"] + rep["poi_new"], key=lambda x: x[3])[:20]:
        side = "v2.52" if x in rep["poi_old"] else "v2.53"
        print(f"  {side} {x[0]:8s} origin {tstr(x[1])} dir {x[2]:+d} at {tstr(x[3])}")
    print(f"  POI differences before the first state divergence (unexplained): {len(rep['poi_unexpl'])}")
    ok_new, k_new = prefix_stable(bars, True)
    ok_old, k_old = prefix_stable(bars, False)
    print(f"\nprefix stability (cut every 25 bars; no event or POI changes when later bars arrive): "
          f"v2.53 {'OK' if ok_new else 'BROKEN at ' + str(k_new)}, v2.52 {'OK' if ok_old else 'BROKEN at ' + str(k_old)}")
    for ver, dd in (("v2.52", False), ("v2.53", True)):
        b, n = shift_stability(bars, dd)
        print(f"window start moved 1..30 H4 bars (events after 60 bars of settle): {ver} {b} of 30 shifts differ, {n} row(s)")
    bad = rep["cls"]["UNEXPLAINED"] + len(rep["poi_unexpl"]) + (0 if ok_new else 1)
    print(f"\n{'ALL DIFFERENCES TRACE TO BOS DE-DUPLICATION' if bad == 0 else 'UNEXPLAINED: ' + str(bad)}")
    return bad == 0


if __name__ == "__main__":
    if "--replay" in sys.argv:
        sys.exit(0 if replay(sys.argv[sys.argv.index("--replay") + 1]) else 1)
    ok = 0
    ok += scenario("bull: one close beyond three old highs, price stays -> one BOS; new swing broken -> new BOS",
                   PUSH, [(13, "BOS", UP, 2), (20, "BOS", UP, 1)], [14, 21])
    ok += scenario("bear: mirror image", mirror(PUSH), [(13, "BOS", DOWN, 2), (20, "BOS", DOWN, 1)], [14, 21])
    ok += scenario("shadowed: close between an older lower high and the latest high is no event; beyond -> one",
                   SHADOW, [(11, "BOS", UP, 1)], [12])
    ok += scenario("shadowed, bear mirror", mirror(SHADOW), [(11, "BOS", DOWN, 1)], [12])
    print(f"\n{ok}/4 scenarios as expected")
    sys.exit(0 if ok == 4 else 1)
