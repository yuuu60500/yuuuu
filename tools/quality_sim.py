"""v2.57 quality score - offline model of docs/02 BRI-14 定义稿 (《HMI 趋势面板改造需求（工程师版）》§6, docs/requirements/,
with the §6.1 / §4.2 rulings in docs/02 「裁决记录 —— 工程师规则决策补充（2026-09-24）」). Not the MQL implementation;
it fixes what each scenario must give.
Display only (Rule 69): nothing in the H4 / POI / session / MODEL chain reads it. The H4 context, the BOS events and
leg_anchor come from the unchanged v2.54 model (tools/h4_protect_sim.py; BRI-12 P-3 already logs leg_anchor).

Definition, all prices in integer points, exact integer arithmetic (overlap pairs in fixed point, 1e-6):

  bar h        the H4 bar just processed by the context engine; D = +1 BULLISH / -1 BEARISH after processing h
  NODATA       h < 11 (the overlap item needs 12 closed H4 bars)
  NODIR        RANGE / TRANSITION after processing h (a broken leg publishes no quality of its old direction)
  events       every break in the trend direction that belongs to the current leg: the leg's opening break (RANGE BOS,
               TRANS_OK, TRANS_FAIL) and each continuation BOS; frozen level = the primary swing's price (HMI-CTX swing_px)
  Q_break      event e at bar k: observed on closes k+1 .. k+3; FAIL if any of them is beyond the level against D
               (D x (C - level) < 0; equal is not a failure), else OK. Mature at h >= k+3 - not before, a failure seen
               early waits too. Used: the latest 5 mature events with k >= h-59 (the latest 60 H4 bars), current leg only.
               n < 3 -> no Q_break, no total (FEW).  Q_break = 100 s / n
  Q_retrace    leg_anchor (BRI-12 P-3, NOT protected_level): swing bar a, price A. ext = max H (bull) / min L (bear) over
               bars a+1 .. h.  L = D (ext - A), x = D (ext - C[h]) clamped to 0 .. L.  no anchor -> ANCHOR, L <= 0 -> LEG
               3x <= L: 100 ; 3x <= 2L: (160 L - 180 x) / L ; else 120 (L - x) / L        (r = x / L: 1/3 -> 100, 2/3 -> 40, 1 -> 0)
  Q_overlap    pairs (i-1, i), i = h-10 .. h (11 pairs in the latest 12 bars): I = max(0, min H - max L), U = max H - min L,
               o = floor(1e6 I / U), U = 0 -> o = 1e6.  So = sum o.  Q_overlap = 100 (11e6 - So) / 11e6
  raw          0.40 Q_break + 0.35 Q_retrace + 0.25 Q_overlap = num / den,  den = 1320000 L,
               num = 40 s (1320000 / n) L + 7 num_r 66000 + 3 (11e6 - So) L
  score        (2 num + den) // (2 den)  (display only)
  tier         from the UNROUNDED raw: < 40 POOR ; < 70 FAIR ; >= 70 GOOD
  PARTIAL      trend, data valid, total not available: reasons FEW / ANCHOR / LEG (joined by +); the valid items are shown
               as 局部表现, nothing is filled in (no 50, no 100, no renormalised weights)

    python3 tools/quality_sim.py                       scenarios, both directions
    python3 tools/quality_sim.py --replay <H1 csv>     real data: prefix stability, mirror, sample / distribution record
"""
import os
import sys
from collections import Counter
from fractions import Fraction as F

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import h4_dedup_sim as B                                        # noqa: E402
import h4_protect_sim as P                                      # noqa: E402
import strength_sim as S                                        # noqa: E402
from h4_dedup_sim import BULL_CTX, BEAR_CTX, TRANS, RANGE, H4, tstr  # noqa: E402

EV_WIN, EV_MAX, EV_OBS, EV_MIN = 60, 5, 3, 3   # event window (H4 bars), latest mature events used, observation, minimum
OV_BARS = 12                                     # 11 adjacent pairs
FP = 10 ** 6                                     # overlap fixed point
W_BRK, W_RET, W_OVL = 40, 35, 25                 # percent; sum 100
T_FAIR, T_GOOD = 40, 70                          # tiers on the unrounded raw score
LEG_START = True                                 # the leg's opening break counts as an event (BRI-14 C-1)
DEF_ID = "QLT1-B60.5.3.3S1-RA-O12F6-W40.35.25-T40.70"
LEG_MAX = 10 ** 10                               # points; beyond this the int64 composite could overflow -> SCALE
LCD = 1320000                                    # lcm(60, 20, 440000): 60 for s / n, 20 for 35 / 100, 440000 for overlap


def p(v):
    return int(round(v / B.POINT))


def H(bars, i): return p(bars[i][2])
def L_(bars, i): return p(bars[i][3])
def C(bars, i): return p(bars[i][4])


def overlap_pairs(bars, h):
    out = []
    for i in range(h - OV_BARS + 2, h + 1):
        inter = max(0, min(H(bars, i), H(bars, i - 1)) - max(L_(bars, i), L_(bars, i - 1)))
        union = max(H(bars, i), H(bars, i - 1)) - min(L_(bars, i), L_(bars, i - 1))
        out.append((inter, union, FP if union == 0 else FP * inter // union))
    return out


def retrace_num(x, leg):
    """Q_retrace = retrace_num / leg, x already clamped to 0 .. leg"""
    if 3 * x <= leg:
        return 100 * leg
    if 3 * x <= 2 * leg:
        return 160 * leg - 180 * x
    return 120 * (leg - x)


def outcome(bars, k, level, d, h):
    """the event at bar k, seen from bar h: PEND (h < k+3), else OK / FAIL. Also returns the closes observed so far."""
    obs = [C(bars, j) for j in range(k + 1, min(k + EV_OBS, h) + 1)]
    if h - k < EV_OBS:
        return "PEND", obs
    return ("FAIL" if any(d * (c - level) < 0 for c in obs) else "OK"), obs


def quality(bars, h, ctx, events, anchor, win=EV_WIN):
    """-> dict. events: [(k, kind, level_pts)] - the trend-direction breaks of the current leg up to h, oldest first;
    anchor: None or (a, A) = leg_anchor swing bar index and price (points) after processing h.
    Reads closes k+1 .. k+3 of each event, H / L of bars a+1 .. h and h-11 .. h; nothing after h."""
    r = dict(state="NODATA", reason="HISTORY", dir=0, ev=[], n=0, s=0, fail=0, pend=0, q_break=None,
             anchor=None, ext=None, close=None, leg=None, x=None, q_retrace=None, num_r=None,
             ov=None, so=None, q_overlap=None, raw=None, score=None, tier="NA", sample="-")
    if h < OV_BARS - 1:
        return r
    r["ov"] = overlap_pairs(bars, h)
    r["so"] = sum(o for _, _, o in r["ov"])
    r["q_overlap"] = F(100 * (11 * FP - r["so"]), 11 * FP)
    d = 1 if ctx == BULL_CTX else -1 if ctx == BEAR_CTX else 0
    if d == 0:
        r.update(state="NODIR", reason="-")
        return r
    r["dir"] = d
    reasons = []
    # --- Q_break
    used = []
    for (k, kind, lvl) in events:
        if h - k > win - 1:
            continue                                  # older than the latest 60 bars
        res, obs = outcome(bars, k, lvl, d, h)
        r["ev"].append((k, kind, lvl, res, obs))
        if res == "PEND":
            r["pend"] += 1
        else:
            used.append(res)
    used = used[-EV_MAX:]
    r["n"], r["s"], r["fail"] = len(used), used.count("OK"), used.count("FAIL")
    r["ev"] = [e for e in r["ev"] if e[3] == "PEND"] + [e for e in r["ev"] if e[3] != "PEND"][-EV_MAX:]
    r["ev"].sort(key=lambda e: e[0])
    if r["n"] >= EV_MIN:
        r["q_break"] = F(100 * r["s"], r["n"])
        r["sample"] = "FIVE" if r["n"] == EV_MAX else "LOW"
    else:
        reasons.append("FEW")
        r["sample"] = "FEW"
    # --- Q_retrace
    r["close"] = C(bars, h)
    if anchor is None:
        reasons.append("ANCHOR")
    else:
        a, A = anchor
        ext = max(H(bars, i) for i in range(a + 1, h + 1)) if d == 1 else min(L_(bars, i) for i in range(a + 1, h + 1))
        leg = d * (ext - A)
        r.update(anchor=(a, A), ext=ext, leg=leg)
        if leg <= 0:
            reasons.append("LEG")
        elif leg > LEG_MAX:
            reasons.append("SCALE")
        else:
            x = min(max(d * (ext - r["close"]), 0), leg)
            r.update(x=x, num_r=retrace_num(x, leg), q_retrace=F(retrace_num(x, leg), leg))
    if reasons:
        r.update(state="PARTIAL", reason="+".join(reasons))
        return r
    n, s, leg, so = r["n"], r["s"], r["leg"], r["so"]
    num = W_BRK * s * (LCD // n) * leg + 7 * r["num_r"] * (LCD // 20) + 3 * (11 * FP - so) * leg
    den = LCD * leg
    raw = F(num, den)
    assert raw == F(W_BRK, 100) * r["q_break"] + F(W_RET, 100) * r["q_retrace"] + F(W_OVL, 100) * r["q_overlap"]
    assert 2 * num + den < 2 ** 63
    r.update(state="OK", reason="-", raw=raw, score=(2 * num + den) // (2 * den), tier=tier(raw), num=num, den=den)
    return r


def tier(raw):
    return "POOR" if raw < T_FAIR else "FAIR" if raw < T_GOOD else "GOOD"


def rnd(fr):
    """display rounding, half up, of a non-negative Fraction"""
    return (2 * fr.numerator + fr.denominator) // (2 * fr.denominator)


# ---- the tracker: what the MQL engine keeps between bars (events of the current leg, nothing else) --------------
class Tracker:
    """fed after each processed H4 bar with the v2.54 engine's state; keeps the current leg's events"""

    def __init__(self, leg_start=LEG_START, win=EV_WIN):
        self.leg_start, self.win = leg_start, win
        self.leg = None
        self.events = []

    def on_bar(self, bars, h, e, new_rows, tidx):
        ctx = e.ctx
        d = 1 if ctx == BULL_CTX else -1 if ctx == BEAR_CTX else 0
        if d == 0:
            self.leg, self.events = None, []
        else:
            started = e.leg != self.leg
            if started:
                self.leg, self.events = e.leg, []
            for row in new_rows:
                if row["kind"] in ("BOS", "TRANS_OK", "TRANS_FAIL") and row["dir"] == d:
                    kind = ("START" if started else "BOS")
                    if kind == "BOS" or self.leg_start:
                        self.events.append((h, kind, p(row["swing_px"])))
            self.events = [ev for ev in self.events if h - ev[0] <= self.win - 1]
        anchor = None
        if d != 0 and e.anchor is not None:
            anchor = (tidx[e.anchor["bar_time"]], p(e.anchor["price"]))
        return quality(bars, h, ctx, list(self.events), anchor, self.win)


def run(bars, leg_start=LEG_START, margins=None, win=EV_WIN):
    """-> engine, [quality rec per bar], [strength rec per bar], [ctx per bar]"""
    e = P.Engine254(True, margins)
    t = Tracker(leg_start, win)
    tidx = {b[0]: k for k, b in enumerate(bars)}
    recs, strs, ctxs = [], [], []
    for h in range(len(bars)):
        n0 = len(e.ctx_rows)
        e.process(bars, h)
        recs.append(t.on_bar(bars, h, e, e.ctx_rows[n0:], tidx))
        strs.append(S.score(bars, h, e.ctx))
        ctxs.append(e.ctx)
    return e, recs, strs, ctxs


# ---- panel text (display; the MQL wording must match) ------------------------------------------------------------
ZH_TIER = {"POOR": "较差", "FAIR": "一般", "GOOD": "良好"}
LABEL_MAX = S.LABEL_MAX


def _sample(r):
    return "5 次事件" if r["sample"] == "FIVE" else f"低样本 {r['n']} 次突破"


def _why(r):
    """why there is no total (PARTIAL): the Q_break sample first, then the anchor"""
    parts = []
    rs = r["reason"].split("+")
    if "FEW" in rs:
        parts.append(f"成熟突破 {r['n']}/{EV_MIN}" + (f"，待确认 {r['pend']}" if r["pend"] else ""))
    if "ANCHOR" in rs:
        parts.append("无波段锚点")
    if "LEG" in rs or "SCALE" in rs:
        parts.append("波段长度无效")
    return "；".join(parts)


def _local(r, sep=" · "):
    it = []
    if r["q_break"] is not None:
        it.append(f"突破 {rnd(r['q_break'])}")
    if r["q_retrace"] is not None:
        it.append(f"回撤 {rnd(r['q_retrace'])}")
    if r["q_overlap"] is not None:
        it.append(f"重叠 {rnd(r['q_overlap'])}")
    return sep.join(it)


def panel_text(rec, ctx, wait, when):
    """FULL panel line. rec = quality() of the last processed bar (None before any); when = its close time."""
    if wait or rec is None:
        if rec is not None and rec["state"] == "OK":
            return f"趋势质量  等待数据（上次有效结果 {ZH_TIER[rec['tier']]} · {rec['score']}/100，{when} H4 收盘）"
        return "趋势质量  等待数据"
    if rec["state"] == "NODATA":
        return "趋势质量  样本不足（H4 不足 12 根）"
    if rec["state"] == "NODIR":
        return "趋势质量  暂不评级（" + ("区间震荡" if ctx == RANGE else "反转待确认") + "）"
    if rec["state"] == "PARTIAL":
        head = "样本不足" if "FEW" in rec["reason"].split("+") else "不可用"
        return f"趋势质量  {head}（{_why(rec)}）  局部表现 {_local(rec)}"
    return f"趋势质量  {ZH_TIER[rec['tier']]} · {rec['score']}/100（{_sample(rec)}）"


def compact_text(rec, ctx, wait, when):
    """PANEL_COMPACT's quality row (the third row; strength and the H4 close stay on the second)"""
    if wait or rec is None:
        return "质量 等待数据"
    if rec["state"] == "NODATA":
        return "质量 样本不足"
    if rec["state"] == "NODIR":
        return "质量 暂不评级"
    if rec["state"] == "PARTIAL":
        head = f"样本不足 {rec['n']}/{EV_MIN}" if "FEW" in rec["reason"].split("+") else "不可用"
        return f"质量 {head}   局部 {_local(rec, ' ')}"
    return f"质量 {ZH_TIER[rec['tier']]} {rec['score']}/100   " + ("5 次事件" if rec["sample"] == "FIVE" else "低样本")


# ---- scenario helpers ----------------------------------------------------------------------------------------------
T0 = int(B.dt.datetime(2026, 9, 7, 0, 0, tzinfo=B.dt.timezone.utc).timestamp())
BASE = 1.10000


def cbars(closes, w=20, wick=None):
    """closes in points from BASE; o = previous close; H / L = body +/- w (wick: {i: (up, down)})"""
    out = []
    for i, c in enumerate(closes):
        o = closes[i - 1] if i else c
        up, dn = (wick or {}).get(i, (w, w))
        out.append((T0 + i * H4, round(BASE + o * B.POINT, 5), round(BASE + (max(o, c) + up) * B.POINT, 5),
                    round(BASE + (min(o, c) - dn) * B.POINT, 5), round(BASE + c * B.POINT, 5)))
    return out


def obars(rows):
    """explicit bars: rows of (high, low, close[, open]) in points from BASE; open = previous close unless given"""
    out, prev = [], rows[0][2]
    for i, row in enumerate(rows):
        hi, lo, cl = row[:3]
        o = row[3] if len(row) > 3 else prev
        out.append((T0 + i * H4, round(BASE + o * B.POINT, 5), round(BASE + max(hi, o, cl) * B.POINT, 5),
                    round(BASE + min(lo, o, cl) * B.POINT, 5), round(BASE + cl * B.POINT, 5)))
        prev = cl
    return out


def mirror(bars):
    return [tuple(b) for b in P.mirror_bars(bars)]


MP = p(2.2)                                       # mirror axis in points: price v <-> MP - v


def mev(events):
    return [(k, kind, MP - lv) for (k, kind, lv) in events]


def manch(anchor):
    return None if anchor is None else (anchor[0], MP - anchor[1])


def comp_case(R, s, L, x, fails=()):
    """bars rising s a bar with range R (I/U constant); events at 1, 4, 7 with levels just under their bar's high;
    a failing event's next close sits on the next bar's low; anchor at h-2 with price ext - L; close = ext - x.
    -> bars, h, events, anchor (the composite-boundary cases C01-C05; tools/logtests reuses them)"""
    h = 13
    rows = [(s * i + R, s * i, s * i + R - 1, s * i) for i in range(h + 1)]
    evs = [(k, "BOS", p(BASE) + s * k + R - 2) for k in (1, 4, 7)]
    for k in fails:
        rows[k + 1] = (rows[k + 1][0], rows[k + 1][1], rows[k + 1][1], rows[k + 1][1])
    ext = s * h + R
    rows[h] = (ext, s * h, ext - x, s * h)
    return obars(rows), h, evs, (h - 2, p(BASE) + ext - L)


RESULTS = []
SAME = ("state", "reason", "n", "s", "fail", "pend", "q_break", "leg", "x", "q_retrace", "so", "q_overlap", "raw", "score",
        "tier", "sample")


def check(name, cond, detail=""):
    RESULTS.append(bool(cond))
    print(f"{'PASS' if cond else 'FAIL'}  {name}" + ("" if cond else f"\n        !! {detail}"))


def f6(v):
    return "NA" if v is None else f"{float(v):.6f}"


def fmt(r):
    if r["state"] in ("NODATA", "NODIR"):
        return f"{r['state']}/{r['reason']}"
    return (f"{r['state']}/{r['reason']} n{r['n']} ok{r['s']} pend{r['pend']} brk {f6(r['q_break'])} ret {f6(r['q_retrace'])}"
            f" ovl {f6(r['q_overlap'])} raw {f6(r['raw'])} {r['score']} {r['tier']}")


def unit(name, bars, h, events, anchor, want, extra=None):
    """quality() on the bull inputs (BULLISH) and on their mirror (BEARISH): want = dict of expected fields for both;
    every field in SAME must agree between the two"""
    rb = quality(bars, h, BULL_CTX, events, anchor)
    rs = quality(mirror(bars), h, BEAR_CTX, mev(events), manch(anchor))
    for nm, r in (("bull", rb), ("bear", rs)):
        ok = all(r[k] == v for k, v in want.items()) and (extra is None or extra(r))
        if nm == "bear":
            ok = ok and all(r[k] == rb[k] for k in SAME)
        check(f"{name} [{nm}]  {fmt(r)}", ok, f"want {want}")
    return rb


def series(name, bars, fn, leg_start=LEG_START):
    """run the engine + tracker on the bull bars and on their mirror; fn(tag, bars, e, recs, strs, ctxs) checks one
    direction; every bar's SAME fields must agree between the two"""
    out = []
    for nm, bb in (("bull", [tuple(b) for b in bars]), ("bear", mirror(bars))):
        e, recs, strs, ctxs = run(bb, leg_start)
        fn(f"{name} [{nm}]", bb, e, recs, strs, ctxs)
        out.append(recs)
    dif = [h for h, (a, b) in enumerate(zip(*out)) if any(a[k] != b[k] for k in SAME)]
    check(f"{name}: bull and bear agree on every bar ({len(out[0])} bars)", not dif, f"bars {dif[:5]}")
    return out[0]


def scenarios():
    # ---- Q_break (inputs given directly: closes rise 10 points a bar, event at bar k breaks a level at C[k] - 5) ----
    print("== Q_break: observation, maturity, failure, sample size (BULLISH and the mirrored BEARISH) ==")
    up = [10 * i for i in range(80)]

    def ev(*ks, kind="BOS"):
        return [(k, ("START" if j == 0 and kind == "START" else "BOS"), p(BASE) + 10 * k - 5) for j, k in enumerate(ks)]
    A = (0, p(BASE) - 50)                             # an anchor far below: Q_retrace 100 throughout
    bars = cbars(up)
    unit("B01 three mature successes, one event 1 bar old: n 3 (pending not counted) -> 100, low sample", bars, 20,
         ev(5, 9, 13, 19), A, dict(state="OK", n=3, s=3, pend=1, q_break=100, sample="LOW"))
    c = list(up); c[11] = 9 * 10 - 5 - 1               # bar 11 = 2nd observation bar of the event at 9: 1 point under
    unit("B02 one close 1 point back under the level (no margin) -> FAIL: 2 / 3", cbars(c), 20, ev(5, 9, 13), A,
         dict(state="OK", n=3, s=2, fail=1, q_break=F(200, 3)))
    c = list(up); c[11] = 9 * 10 - 5
    unit("B03 a close exactly at the level is not a failure", cbars(c), 20, ev(5, 9, 13), A, dict(n=3, s=3, q_break=100))
    c = list(up); c[18] = 17 * 10 - 5 - 30             # event at 17 fails on its FIRST observation bar
    for h, want in ((18, dict(n=2, pend=1, s=2)), (19, dict(n=2, pend=1, s=2)), (20, dict(n=3, pend=0, s=2, fail=1))):
        unit(f"B04 failure seen at k+1 stays pending until k+3 (h = {h})", cbars(c), h, ev(5, 9, 17), A,
             dict(want, state=("OK" if want["n"] >= 3 else "PARTIAL")))
    for k_list, n in (((), 0), ((5,), 1), ((5, 9), 2)):
        unit(f"B05 {n} mature event(s) -> PARTIAL / FEW: no Q_break, no total (not 0, not 50, not 100)", bars, 20,
             ev(*k_list) + ev(19), A, dict(state="PARTIAL", reason="FEW", n=n, pend=1, q_break=None, raw=None, score=None,
                                          tier="NA", sample="FEW"))
    c = list(up); c[4] = 3 * 10 - 5 - 1               # the OLDEST of six mature events fails
    unit("B06 six mature events: the latest 5 count (the oldest, a failure, drops out) -> 100, 5 次事件", cbars(c), 25,
         ev(3, 6, 9, 12, 15, 18), A, dict(n=5, s=5, q_break=100, sample="FIVE"))
    unit("B06 five of them: the failure is in -> 80", cbars(c), 25, ev(3, 6, 9, 12, 15), A, dict(n=5, s=4, q_break=80))
    unit("B07 an event 59 bars back is inside the 60-bar window", bars, 70, ev(11, 30, 50), A, dict(n=3, state="OK"))
    unit("B07 an event 60 bars back is outside -> 2 events, FEW", bars, 70, ev(10, 30, 50), A,
         dict(n=2, state="PARTIAL", reason="FEW"))

    # ---- Q_retrace (bars 1 .. 10 rise to the extreme 300 points over the anchor; bar 11 closes x under it) ----------
    print("\n== Q_retrace: leg_anchor, extreme after the anchor bar, piecewise score ==")
    ok3 = ev(2, 4, 6)

    def rbars(x, ext=300, a_high=40, wick_hi=None):
        rows = [(a_high, 0, 20)] + [(30 * i, 30 * i - 40, 30 * i - 10) for i in range(1, 11)]
        rows.append((wick_hi if wick_hi is not None else max(ext - 10, ext - x), ext - x - 10, ext - x))
        return obars(rows)
    for x, want in ((0, 100), (100, 100), (101, F(160 * 300 - 180 * 101, 300)), (150, 70), (200, 40),
                    (250, 20), (300, 0), (330, 0)):
        unit(f"R01 leg 300, close {x} under the extreme (r = {F(x, 300)}) -> Q_retrace {float(want):.4f}", rbars(x), 11, ok3,
             (0, p(BASE)), dict(leg=300, x=min(x, 300), q_retrace=want))
    unit("R02 the anchor bar's own high (500) is not the extreme: the extreme is taken from the next bar on",
         rbars(150, a_high=500), 11, ok3, (0, p(BASE)), dict(leg=300, q_retrace=70))
    unit("R03 a wick-only new high (350, close 290): the extreme is the high -> leg 350, x 60",
         rbars(10, wick_hi=350), 11, ok3, (0, p(BASE)), dict(leg=350, x=60, q_retrace=100))
    unit("R04 no leg_anchor (INVALID leg) -> PARTIAL / ANCHOR; Q_break and Q_overlap still shown", rbars(150), 11, ok3, None,
         dict(state="PARTIAL", reason="ANCHOR", q_retrace=None, q_break=100, raw=None))
    unit("R05 extreme not beyond the anchor (leg 0) -> PARTIAL / LEG", rbars(150), 11, ok3, (0, p(BASE) + 300),
         dict(state="PARTIAL", reason="LEG", leg=0, q_retrace=None))
    unit("R06 FEW and no anchor -> both reasons", rbars(150), 11, ev(2, 4), None, dict(state="PARTIAL", reason="FEW+ANCHOR"))

    # ---- Q_overlap -----------------------------------------------------------------------------------------------
    print("\n== Q_overlap: 11 adjacent pairs of the latest 12 bars, fixed point 1e-6 per pair ==")

    def steps(R, s, n=14):
        return obars([(s * i + R, s * i, s * i + R // 2, s * i) for i in range(n)])     # open at the low: no gap filled
    unit("O01 every bar above the previous one (gap): overlap 0 -> 100", steps(50, 100), 13, ok3, (0, p(BASE) - 50),
         dict(q_overlap=100, so=0))
    unit("O02 identical bars: overlap 1 -> 0", steps(100, 0), 13, ok3, (0, p(BASE) - 50), dict(q_overlap=0, so=11 * FP))
    unit("O03 range 90, step 30: I 60 / U 120 = 0.5 -> 50", steps(90, 30), 13, ok3, (0, p(BASE) - 50), dict(q_overlap=50))
    unit("O04 zero-range bars at one price (U = 0): overlap 1 by definition -> 0; data valid (not NODATA)",
         steps(0, 0), 13, ok3, (0, p(BASE) - 50), dict(q_overlap=0, state="OK"))
    alt = obars([(100, 0, 50) if i % 2 == 0 else (50, 50, 50) for i in range(14)])
    unit("O05 a zero-range bar inside the previous range: I = 0 -> overlap 0 (literal formula; BRI-14 C-5)", alt, 13, ok3,
         (0, p(BASE) - 50), dict(q_overlap=100, so=0))
    unit("O06 I / U = 1/3 every pair: floor(1e6 / 3) = 333333 -> 66.666700 (exact 66.6667 only to 1e-6)",
         steps(100, 50), 13, ok3, (0, p(BASE) - 50), dict(so=11 * 333333, q_overlap=F(100 * (11 * FP - 11 * 333333), 11 * FP)))
    o7 = obars([(90, 0, 45, 0), (900, 800, 850, 800)] + [(30 * i + 90, 30 * i, 30 * i + 45, 30 * i) for i in range(2, 14)])
    unit("O07 only the latest 12 bars count: bar 1 (h-12) far away -> Q_overlap unchanged (50)", o7, 13, ok3,
         (0, p(BASE) - 50), dict(q_overlap=50))

    # ---- composite: tiers on the unrounded score, display rounded half up ---------------------------------------------
    print("\n== composite 0.40 / 0.35 / 0.25, tiers 40 / 70 on the unrounded score ==")

    for nm, args, want in (
            ("C01 Q_break 100, Q_retrace 40, Q_overlap 64 -> raw exactly 70 -> 70 GOOD", (680, 320, 900, 600), (F(70), 70, "GOOD")),
            ("C02 Q_retrace 270/7 -> raw exactly 69.5 -> shows 70, tier FAIR", (680, 320, 840, 570), (F(139, 2), 70, "FAIR")),
            ("C03 Q_break 200/3, Q_retrace 500/21, Q_overlap 20 -> raw exactly 40 -> 40 FAIR", (900, 100, 1008, 808, (4,)),
             (F(40), 40, "FAIR")),
            ("C04 Q_retrace 470/21 -> raw exactly 39.5 -> shows 40, tier POOR", (900, 100, 1008, 820, (4,)),
             (F(79, 2), 40, "POOR"))):
        b, h, evs, an = comp_case(*args)
        unit(nm, b, h, evs, an, dict(state="OK", raw=want[0], score=want[1], tier=want[2]))
    b, h, evs, an = comp_case(680, 320, 900, 600)
    base = quality(b, h, BULL_CTX, evs, an)
    b2, _, evs2, an2 = comp_case(680, 320, 900, 600, fails=(4,))
    one = quality(b2, h, BULL_CTX, evs2, an2)
    check("C05 one failure among three: only Q_break moves (100 -> 66.67), raw falls 40/3",
          one["q_retrace"] == base["q_retrace"] and one["q_overlap"] == base["q_overlap"] and
          base["raw"] - one["raw"] == F(40, 3), f"{fmt(base)} | {fmt(one)}")
    unit("D01 h = 10 (11 bars): NODATA / HISTORY", cbars(up), 10, ev(2, 4, 6), A, dict(state="NODATA", reason="HISTORY"))
    rr = quality(cbars(up), 20, RANGE, ev(5, 9, 13), A)
    rt = quality(cbars(up), 20, TRANS, ev(5, 9, 13), A)
    check("X01 RANGE / TRANSITION: NODIR, no item but the overlap record", rr["state"] == rt["state"] == "NODIR" and
          rr["q_break"] is None and rr["q_retrace"] is None and rr["q_overlap"] is not None, f"{fmt(rr)} {fmt(rt)}")
    xb = quality(cbars(up), 20, BEAR_CTX, ev(5, 9, 13), (0, p(BASE) + 2000))
    check(f"X02 the same rising bars and levels under BEARISH: every close is above the level -> every event fails ({fmt(xb)})",
          xb["n"] == 3 and xb["s"] == 0 and xb["q_break"] == 0, fmt(xb))

    # ---- with the H4 structure engine (v2.54 rules, unchanged since): events, legs and leg_anchor come from it ------
    print("\n== with the H4 context engine: events, legs, leg_anchor (bull, and the mirror as bear) ==")
    stair = P.path([(1.1050, 0), (1.1000, 2), (1.1100, 5), (1.1040, 3), (1.1160, 6), (1.1100, 3), (1.1230, 6), (1.1180, 3),
                    (1.1300, 6), (1.1250, 3), (1.1370, 6), (1.1330, 3), (1.1440, 6), (1.1400, 3), (1.1510, 6), (1.1470, 3),
                    (1.1580, 6), (1.1540, 3)])

    def e01(tag, bars, e, recs, strs, ctxs):
        kinds = [(r["ev"][-1][0], r["ev"][-1][1]) for h, r in enumerate(recs) if r["ev"] and r["ev"][-1][0] == h]
        check(f"E01 {tag} events: the leg's opening break (START, bar 14) and each continuation BOS (23, 31, 40, 49, 58, 67)",
              kinds == [(14, "START"), (23, "BOS"), (31, "BOS"), (40, "BOS"), (49, "BOS"), (58, "BOS"), (67, "BOS")], f"{kinds}")
        want = {13: ("NODIR", 0, 0), 14: ("PARTIAL", 0, 1), 16: ("PARTIAL", 0, 1), 17: ("PARTIAL", 1, 0),
                26: ("PARTIAL", 2, 0), 33: ("PARTIAL", 2, 1), 34: ("OK", 3, 0), 43: ("OK", 4, 0), 52: ("OK", 5, 0),
                61: ("OK", 5, 0)}
        got = {h: (recs[h]["state"], recs[h]["n"], recs[h]["pend"]) for h in want}
        check(f"E01 {tag} a BOS matures 3 bars later; total from the 3rd mature event (bar 34, 低样本); 5 次事件 from bar 52",
              got == want and recs[34]["sample"] == "LOW" and recs[52]["sample"] == "FIVE", f"{got}")
        check(f"E01 {tag} bar 61: six mature events, the latest five (23 .. 58) count; bar 14 drops out",
              [x[0] for x in recs[61]["ev"]] == [23, 31, 40, 49, 58], f"{recs[61]['ev']}")
        r = recs[37]
        check(f"E01 {tag} bar 37: anchor = the swing low 1750 (bar 28) from BOS 31; extreme 3050 -> leg 1300, x 550 -> "
              f"Q_retrace 160 - 180 x 550/1300 = {float(F(160 * 1300 - 180 * 550, 1300)):.4f}",
              (r["leg"], r["x"], r["q_retrace"]) == (1300, 550, F(160 * 1300 - 180 * 550, 1300)), fmt(r))
    st = series("staircase", stair, e01)

    def e01s0(tag, bars, e, recs, strs, ctxs):
        check(f"E10 {tag} without the opening break (def S0) the 3rd mature event comes at bar 43, not 34",
              recs[34]["state"] == "PARTIAL" and recs[42]["state"] == "PARTIAL" and recs[43]["state"] == "OK",
              f"{fmt(recs[34])} | {fmt(recs[43])}")
    series("staircase, def S0", stair, e01s0, leg_start=False)

    allfail = cbars([0, -100, -200, -300, -200, -100, 0, 100, 200, 300, 250, 200, 150, 200, 300, 340, 320, 400, 480, 470,
                     460, 515, 505, 600, 680, 670, 660, 715, 705, 800, 880, 870, 860, 915, 905, 905, 905, 865, 925, 1025,
                     965], 30)

    def e02(tag, bars, e, recs, strs, ctxs):
        r = recs[30]
        check(f"E02 {tag} every break slips back under its level within 3 bars (1 to 10 points, no margin): bar 30 "
              f"n 3, 0 OK -> Q_break 0 (not FEW, not excluded)",
              (r["state"], r["n"], r["s"], r["q_break"]) == ("OK", 3, 0, 0) and [x[3] for x in r["ev"]] == ["FAIL"] * 3,
              fmt(r))
        r, s_ = recs[40], strs[40]
        check(f"E11 {tag} bar 40: strength {s_['score']} {s_['tier']} with quality {f6(r['raw'])} {r['tier']} "
              f"(breaks 0/4 held, overlap {f6(r['q_overlap'])}, retrace {f6(r['q_retrace'])}) - 强度强但质量差",
              s_["tier"] == "STRONG" and r["tier"] == "POOR" and r["n"] == 4 and r["s"] == 0, fmt(r))
    series("failing breaks", allfail, e02)

    def m02(tag, bars, e, recs, strs, ctxs):
        r, s_ = recs[36], strs[36]
        check(f"E12 {tag} staircase bar 36 (third bar of a normal pullback): strength {s_['score']} {s_['tier']}, "
              f"quality {f6(r['raw'])} {r['tier']} (3/3 breaks held, r {float(F(r['x'], r['leg'])):.3f}) - 强度一般但质量好",
              s_["tier"] == "MED" and r["tier"] == "GOOD", fmt(r))
    series("orderly pullback", stair, m02)

    def trans_case(after):
        return P.path([(1.1050, 0), (1.1000, 2), (1.1100, 5), (1.1040, 3), (1.1160, 6), (1.1010, 6)] + after)

    def e03(tag, bars, e, recs, strs, ctxs):
        ch = [k for k, b in enumerate(bars) if any(x["kind"] == "CHOCH" and x["bar"] == b[0] + H4 for x in e.ctx_rows)]
        k = ch[0]
        check(f"E03 {tag} protected low broken at bar {k}: that bar NODIR (no quality of the old direction); bar before "
              f"{recs[k - 1]['state']}", ch == [22] and recs[k]["state"] == "NODIR" and recs[k - 1]["state"] == "PARTIAL" and
              all(recs[j]["state"] == "NODIR" for j in range(22, 33)), f"{ch} {fmt(recs[k])}")
        r = recs[33]
        check(f"E04 {tag} TRANS_OK at bar 33: new leg in the other direction - its own opening break only (pending), "
              f"the old leg's event (bar 14) gone, the new leg's anchor", ctxs[33] in (BULL_CTX, BEAR_CTX) and
              [x[:2] for x in r["ev"]] == [(33, "START")] and r["anchor"] is not None and r["anchor"][0] > 22, fmt(r))
        check(f"E04 {tag} bars 34 / 35 break again: three pending events, none mature -> FEW 0/3, 待确认 3; bar 37: 2 mature, 1 pending",
              (recs[35]["n"], recs[35]["pend"]) == (0, 3) and (recs[37]["n"], recs[37]["pend"]) == (2, 1), fmt(recs[35]))
    series("CHOCH then TRANS_OK", trans_case([(1.1060, 3), (1.1030, 3), (1.1055, 3), (1.0950, 6)]), e03)

    def e05(tag, bars, e, recs, strs, ctxs):
        r = recs[30]
        check(f"E05 {tag} TRANS_FAIL at bar 30: same direction as the old leg, still a new leg - the old leg's mature "
              f"success (bar 14) is not inherited: n 0, pending 1", ctxs[30] == ctxs[21] and recs[21]["n"] == 1 and
              (r["n"], r["pend"]) == (0, 1) and [x[0] for x in r["ev"]] == [30], fmt(r))
    series("CHOCH then TRANS_FAIL", trans_case([(1.1080, 3), (1.1050, 3), (1.1130, 4)]), e05)

    def leg(l2=1.1100, tail=None):
        return P.path([(1.1050, 0), (1.1000, 2), (1.1100, 5), (1.1040, 3), (1.1160, 6), (l2, 3), (1.1230, 6)] + (tail or []))
    worse = leg(l2=1.10380, tail=[(1.1150, 4), (1.1240, 3)])
    P.setbar(worse, 19, close=1.10348)               # 2 points beyond the anchor / protected 1.10350: inside the margin

    def e06(tag, bars, e, recs, strs, ctxs):
        r = recs[19]
        check(f"E06 {tag} bar 19 closes 2 points beyond the anchor (within the margin, no CHOCH): x > leg, clamped -> "
              f"Q_retrace 0", (r["state"], r["x"], r["leg"], r["q_retrace"]) == ("PARTIAL", 1300, 1300, 0), fmt(r))
        pr = [x["ev"] for x in e.prot_rows if x["bar"] == bars[23][0] + H4]
        an = [x for x in e.anchor_rows if x["bar"] == bars[23][0] + H4]
        r = recs[29]
        a_px = MP - p(BASE) - 330 if ctxs[29] == BEAR_CTX else p(BASE) + 330
        check(f"E06 {tag} BOS at 23: protected KEEP_WORSE (stays 1.10350), leg_anchor MOVE to 1.10330; bar 29 measures "
              f"from the anchor: leg 2020, x 850 -> {float(F(160 * 2020 - 180 * 850, 2020)):.4f} (from protected it would "
              f"be leg 2000)", pr == ["KEEP_WORSE"] and [x["ev"] for x in an] == ["MOVE"] and r["anchor"][1] == a_px and
              (r["leg"], r["x"], r["q_retrace"]) == (2020, 850, F(160 * 2020 - 180 * 850, 2020)), f"{pr} {fmt(r)}")
    series("anchor moves, protected kept", worse, e06)

    FAST = [(1.1050, 0), (1.1000, 2), (1.1100, 5), (1.1070, 2), (1.1140, 1)]
    inval = P.path(FAST + [(1.1150, 1), (1.1160, 1), (1.1220, 3), (1.1180, 3), (1.1260, 4), (1.1230, 3), (1.1300, 4),
                           (1.1270, 3), (1.1340, 4)])

    def e07(tag, bars, e, recs, strs, ctxs):
        inv = [x["ev"] for x in e.anchor_rows][:2]
        check(f"E07 {tag} leg opens with no legal pullback point (anchor INVALID): bars 14 .. 20 PARTIAL FEW+ANCHOR, "
              f"no retrace item; the BOS at 21 sets the anchor -> retrace from bar 21",
              inv == ["INVALID", "SET"] and all(recs[j]["reason"] == "FEW+ANCHOR" and recs[j]["q_retrace"] is None
                                                for j in range(14, 21)) and recs[21]["q_retrace"] is not None, f"{inv}")
    series("INVALID anchor", inval, e07)

    print("\n== no future, read only ==")
    bad, total = 0, 0
    for bars in (stair, allfail, trans_case([(1.1060, 3), (1.1030, 3), (1.1055, 3), (1.0950, 6)]), worse, inval):
        for bb in ([tuple(b) for b in bars], mirror(bars)):
            full = run(bb)[1]
            for h in range(len(bb)):
                total += 1
                if run(bb[:h + 1])[1][-1] != full[h]:
                    bad += 1
    check(f"E08 every bar of every engine scenario: the record from bars[:h+1] equals the full run ({total} bars)",
          bad == 0, f"{bad} differ")
    same = True
    for bars in (stair, allfail, worse, inval):
        bb = [tuple(b) for b in bars]
        e0 = P.run254(bb)
        e1 = run(bb)[0]
        same = same and (e0.ctx_rows, e0.prot_rows, e0.anchor_rows, e0.internal_rows) == \
            (e1.ctx_rows, e1.prot_rows, e1.anchor_rows, e1.internal_rows)
    check("E09 quality reads only: context, PROT, ANCHOR and INTERNAL rows identical with and without it", same)

    print("\n== panel (display; the MQL wording must match) ==")
    t1 = "2026.10.26 12:00"
    _, sr, _, sc = run([tuple(b) for b in stair])
    _, ir, _, ic = run([tuple(b) for b in inval])
    check("P01 total with 3 or 4 mature events: tier, score, 低样本 and the count",
          panel_text(sr[34], sc[34], False, t1) == "趋势质量  良好 · 95/100（低样本 3 次突破）" and
          compact_text(sr[34], sc[34], False, t1) == "质量 良好 95/100   低样本")
    check("P02 five mature events: 5 次事件 (no claim of statistical confidence)",
          panel_text(sr[52], sc[52], False, t1) == "趋势质量  良好 · 95/100（5 次事件）" and
          compact_text(sr[52], sc[52], False, t1) == "质量 良好 95/100   5 次事件")
    check("P03 fewer than 3 mature: 样本不足 with the count and the pending events; no total; the valid items as 局部表现",
          panel_text(sr[33], sc[33], False, t1) == "趋势质量  样本不足（成熟突破 2/3，待确认 1）  局部表现 回撤 100 · 重叠 78" and
          compact_text(sr[33], sc[33], False, t1) == "质量 样本不足 2/3   局部 回撤 100 重叠 78" and
          panel_text(sr[14], sc[14], False, t1) == "趋势质量  样本不足（成熟突破 0/3，待确认 1）  局部表现 回撤 100 · 重叠 79")
    check("P04 no anchor as well: both reasons, no retrace item",
          panel_text(ir[14], ic[14], False, t1) == "趋势质量  样本不足（成熟突破 1/3；无波段锚点）  局部表现 重叠 81")
    ra = quality(rbars(150), 11, BULL_CTX, ok3, None)
    check("P05 enough breaks but no anchor: 不可用, Q_break shown as a local item",
          panel_text(ra, BULL_CTX, False, t1) == "趋势质量  不可用（无波段锚点）  局部表现 突破 100 · 重叠 81" and
          compact_text(ra, BULL_CTX, False, t1) == "质量 不可用   局部 突破 100 重叠 81")
    check("P06 RANGE / TRANSITION / history",
          panel_text(sr[13], RANGE, False, t1) == "趋势质量  暂不评级（区间震荡）" and
          panel_text(sr[13], TRANS, False, t1) == "趋势质量  暂不评级（反转待确认）" and
          panel_text(sr[5], sc[5], False, t1) == "趋势质量  样本不足（H4 不足 12 根）" and
          compact_text(sr[13], RANGE, False, t1) == "质量 暂不评级" and compact_text(sr[5], sc[5], False, t1) == "质量 样本不足")
    check("P07 waiting: the last valid total with its time; after a PARTIAL / NODIR bar no number",
          panel_text(sr[34], sc[34], True, t1) == "趋势质量  等待数据（上次有效结果 良好 · 95/100，2026.10.26 12:00 H4 收盘）" and
          panel_text(sr[33], sc[33], True, t1) == "趋势质量  等待数据" and panel_text(None, RANGE, True, "") == "趋势质量  等待数据"
          and compact_text(sr[34], sc[34], True, t1) == "质量 等待数据")
    worst = dict(sr[33], n=2, pend=3, reason="FEW+ANCHOR", q_break=None, q_retrace=None, q_overlap=F(100))
    worst2 = dict(sr[33], n=2, pend=3, reason="FEW", q_retrace=F(100), q_overlap=F(100))
    worst3 = dict(sr[34], tier="FAIR", score=100, n=4)
    worst4 = dict(worst, reason="FEW+LEG")
    rows = [f(r, BULL_CTX, w, t1) for f in (panel_text, compact_text) for r in (worst, worst2, worst3, worst4, ra)
            for w in (False, True)]
    longest = max(rows, key=len)
    check(f"P08 every quality row fits an OBJ_LABEL ({LABEL_MAX} characters; longest {len(longest)}: {longest})",
          len(longest) <= LABEL_MAX)


# ---- log rows, formatted as the MQL engine is to print them (BRI-14 Q-9; for tools/logtests) -----------------------
def px(v):
    return f"{v * B.POINT:.5f}"


def qlt_row(bars, h, ctx, r, live=0, sym="USDJPY", inst="0001", run=7, init=1):
    na = lambda v, f=str: "NA" if v is None else f(v)                # noqa: E731
    evs = ";".join(f"{tstr(bars[k][0] + H4)}@{px(lv)}/{kind}/{res}/" + ("|".join(px(c) for c in obs) or "-")
                   for (k, kind, lv, res, obs) in r["ev"]) or "-"
    ov = ";".join(f"{i}/{u}" for i, u, _ in r["ov"]) if r["ov"] else "NA"
    a = r["anchor"]
    return (f"HMI-QLT,{sym},live={live},bar={tstr(bars[h][0] + H4)},ctx={ctx},state={r['state']},reason={r['reason']},"
            f"def={DEF_ID},dir={r['dir']},ev={evs},b_n={r['n']},b_ok={r['s']},b_fail={r['fail']},b_pend={r['pend']},"
            f"q_break={f6(r['q_break'])},anchor={'NA' if a is None else px(a[1])},"
            f"anchor_bar={'-' if a is None else tstr(bars[a[0]][0])},ext={na(r['ext'], px)},close={px(C(bars, h))},"
            f"leg_pts={na(r['leg'])},retr_pts={na(r['x'])},q_retrace={f6(r['q_retrace'])},ov={ov},"
            f"ov_sum={na(r['so'])},q_overlap={f6(r['q_overlap'])},raw={f6(r['raw'])},score={na(r['score'])},"
            f"tier={r['tier']},sample={r['sample']},inst={inst},run={run},init={init}")


def qhist_row(bars, recs, sym="USDJPY", inst="0001", run=7, init=1):
    """recs: quality() of every processed bar 0 .. len(recs)-1"""
    hist = [0] * 101
    ok = [r for r in recs if r["state"] == "OK"]
    for r in ok:
        hist[r["score"]] += 1
    n = lambda st: sum(1 for r in recs if r["state"] == st)            # noqa: E731
    t = lambda k: sum(1 for r in ok if r["tier"] == k)                  # noqa: E731
    rs = lambda k: sum(1 for r in recs if r["state"] == "PARTIAL" and k in r["reason"].split("+"))  # noqa: E731
    nd = [sum(1 for r in recs if r["state"] in ("OK", "PARTIAL") and r["n"] == k) for k in range(EV_MAX + 1)]
    return (f"HMI-QLT-HIST,{sym},live=0,def={DEF_ID},from={tstr(bars[0][0] + H4)},to={tstr(bars[len(recs) - 1][0] + H4)},"
            f"bars={len(recs)},ok={len(ok)},partial={n('PARTIAL')},nodir={n('NODIR')},nodata={n('NODATA')},"
            f"poor={t('POOR')},fair={t('FAIR')},good={t('GOOD')},few={rs('FEW')},anchor={rs('ANCHOR')},"
            f"legbad={rs('LEG') + rs('SCALE')},n={';'.join(map(str, nd))},h={';'.join(map(str, hist))},"
            f"inst={inst},run={run},init={init}")


def replay(path_csv):
    bars = B.load_h1(path_csv)
    print(f"replay {path_csv}: {len(bars)} H4 bars {tstr(bars[0][0])} .. {tstr(bars[-1][0])}")
    e, recs, strs, ctxs = run(bars)
    bad = 0
    for h in range(40, len(bars), 37):
        if run(bars[:h + 1])[1][-1] != recs[h]:
            bad += 1
    check("R1 prefix: the record of h from bars[:h+1] equals the full run (every 37th bar from 40)", bad == 0, f"{bad} differ")
    mrecs = run(mirror(bars))[1]
    dif = sum(1 for a, b in zip(recs, mrecs) if any(a[k] != b[k] for k in SAME))
    check(f"R2 mirror: mirrored bars give the same record on every bar ({dif} differ)", dif == 0)

    def pct(v, q):
        v = sorted(v)
        k = (len(v) - 1) * q / 100.0
        f = int(k); cc = min(f + 1, len(v) - 1)
        return v[f] + (v[cc] - v[f]) * (k - f)
    trend = [r for r in recs if r["state"] in ("OK", "PARTIAL")]
    ok = [r for r in recs if r["state"] == "OK"]
    c = Counter((r["state"], r["reason"]) for r in recs)
    print("\nrecord only - nothing below changes the definition")
    print("states: " + ", ".join(f"{st}/{rs} {n}" for (st, rs), n in sorted(c.items())))
    print(f"trend bars {len(trend)}: total available {len(ok)} ({100.0 * len(ok) / len(trend):.1f}%)")
    print("mature events used (n) over trend bars: " + "  ".join(f"n={k} {sum(1 for r in trend if r['n'] == k)}"
                                                           for k in range(EV_MAX + 1)))
    evs = {(k, res) for r in trend for (k, _, _, res, _) in r["ev"] if res != "PEND"}
    print(f"distinct mature events: OK {sum(1 for _, x in evs if x == 'OK')}  FAIL {sum(1 for _, x in evs if x == 'FAIL')}")
    print("sparsity, the same bars under other event rules (Q_break available = n >= 3):")
    for nm, ls, win in (("definition: leg, 60 bars, opening break counts (S1)", True, EV_WIN),
                        ("without the opening break (S0)", False, EV_WIN),
                        ("original 12-bar window, S1", True, 12), ("original 12-bar window, S0", False, 12)):
        rr = recs if (ls, win) == (True, EV_WIN) else run(bars, ls, win=win)[1]
        tb = [r for r in rr if r["state"] in ("OK", "PARTIAL")]
        print(f"  {nm:52s} {sum(1 for r in tb if r['n'] >= EV_MIN):5d} / {len(tb)} "
              f"({100.0 * sum(1 for r in tb if r['n'] >= EV_MIN) / len(tb):5.1f}%)")
    print("items over bars with a total:")
    for nm, key in (("Q_break", "q_break"), ("Q_retrace", "q_retrace"), ("Q_overlap", "q_overlap"), ("raw", "raw")):
        v = [float(r[key]) for r in ok]
        print(f"  {nm:9s} " + "  ".join(f"P{q} {pct(v, q):6.2f}" for q in (10, 25, 50, 75, 90)) +
              f"   = 0: {sum(1 for x in v if x == 0)}  = 100: {sum(1 for x in v if x == 100)}")
    tc = Counter(r["tier"] for r in ok)
    print(f"  tiers (40 / 70 on raw): POOR {tc['POOR']}  FAIR {tc['FAIR']}  GOOD {tc['GOOD']}  of {len(ok)}")
    ct = Counter((s_["tier"], r["tier"]) for s_, r in zip(strs, recs) if r["state"] == "OK" and s_["state"] == "OK")
    print("strength tier x quality tier (bars with both): " +
          "  ".join(f"{a}/{b} {ct[(a, b)]}" for a in ("WEAK", "MED", "STRONG") for b in ("POOR", "FAIR", "GOOD")))
    return all(RESULTS)


def main():
    if len(sys.argv) > 2 and sys.argv[1] == "--replay":
        ok = replay(sys.argv[2])
    else:
        scenarios()
        ok = all(RESULTS)
    print(f"\n{sum(RESULTS)}/{len(RESULTS)} {'PASS' if ok else 'FAIL'}")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
