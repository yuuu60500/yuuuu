"""v2.56 strength score - offline model of docs/02 BRI-13 修订稿 2 (the three-item formula of the original requirement,
《HMI 趋势面板改造需求（工程师版）》§5, docs/requirements/). Not the MQL implementation; it fixes what each scenario must give.
Display only (Rule 69): nothing in the H4 / POI / session / MODEL chain reads the score, so the H4 context comes from the
unchanged v2.54 model (BRI-08 did not touch H4).

Definition, all prices in integer points (pts = round(price difference / point)), exact integer arithmetic:

  bar h        the H4 bar just processed by the context engine; D = +1 BULLISH / -1 BEARISH after processing h
  NODATA       reason HISTORY: h < 14 (ATR14 needs 15 closed H4 bars) ; reason ATR: T = 0
               (reason WAIT - series not synced - is a panel state, never a processed bar: see panel_text)
  NODIR        RANGE / TRANSITION after processing h
  chg12, chg3  C[h] - C[h-12], C[h] - C[h-3]          net = D x chg12, recent = D x chg3
  path         sum |C[i] - C[i-1]|, i = h-11 .. h
  T            sum TR[k], k = h-13 .. h  (= 14 x ATR14, SeriesComputeATR's TR)
  S_move       100 x clamp(net / 3A, 0, 1)   = 100 m / 3T,  m = min(max(14 net, 0), 3T)
  S_eff        100 x clamp(max(net, 0) / path, 0, 1) = 100 e / path, e = min(max(net, 0), path); path = 0 -> 0
  S_mom        100 x clamp(recent / A, 0, 1) = 100 r / T,   r = min(max(14 recent, 0), T)
  raw          0.45 S_move + 0.35 S_eff + 0.20 S_mom = num / den
               path > 0: num = (15 m + 20 r) path + 35 e T,  den = T path ;  path = 0: num = 15 m + 20 r, den = T
  score        floor(raw + 1/2) = (2 num + den) // (2 den)     (display only)
  tier         from the UNROUNDED raw: raw < 35 WEAK ; 35 <= raw < 65 MED ; raw >= 65 STRONG  (0 is WEAK)

    python3 tools/strength_sim.py                       scenarios, both directions
    python3 tools/strength_sim.py --replay <H1 csv>     real data: prefix stability, mirror, distribution record
"""
import copy
import os
import sys
from fractions import Fraction as F

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import h4_dedup_sim as B                                        # noqa: E402
import h4_protect_sim as P                                      # noqa: E402
from h4_dedup_sim import BULL_CTX, BEAR_CTX, TRANS, RANGE, H4, tstr  # noqa: E402

N, K, ATR_N = 12, 3, 14
W_MOVE, W_EFF, W_MOM = 45, 35, 20      # percent; sum 100
MOVE_ATR, MOM_ATR = 3, 1               # full marks: net 3 ATR, recent 1 ATR
T_MED, T_STRONG = 35, 65               # tiers on the unrounded raw score
DEF_ID = "STR1-N12K3-M3R1-W45.35.20-T35.65"   # STR rows carry it; a different id = not comparable


def p(v):
    return int(round(v / B.POINT))


def tr_pts(bars, k):
    pc = bars[k - 1][4]
    return max(p(bars[k][2] - bars[k][3]), abs(p(bars[k][2] - pc)), abs(p(bars[k][3] - pc)))


def score(bars, h, ctx):
    """-> dict; reads bars[h-14 .. h] only."""
    r = dict(state="NODATA", reason="HISTORY", dir=0, chg12=None, chg3=None, path=None, T=None,
             net=None, recent=None, s_move=None, s_eff=None, s_mom=None, raw=None, score=None, tier="NA")
    if h < ATR_N:
        return r
    c = lambda i: bars[i][4]                                   # noqa: E731
    T = sum(tr_pts(bars, k) for k in range(h - ATR_N + 1, h + 1))
    r.update(chg12=p(c(h) - c(h - N)), chg3=p(c(h) - c(h - K)),
             path=sum(abs(p(c(i) - c(i - 1))) for i in range(h - N + 1, h + 1)), T=T)
    if T <= 0:
        r["reason"] = "ATR"
        return r
    d = 1 if ctx == BULL_CTX else -1 if ctx == BEAR_CTX else 0
    if d == 0:
        r.update(state="NODIR", reason="-")
        return r
    net, recent, path = d * r["chg12"], d * r["chg3"], r["path"]
    m = min(max(14 * net, 0), MOVE_ATR * T)
    e = min(max(net, 0), path)
    q = min(max(14 * recent, 0), MOM_ATR * T)
    # W_MOVE / (100 MOVE_ATR) = 15 / 100 ... kept general: raw = W_MOVE m / (MOVE_ATR T) + W_EFF e / path + W_MOM q / (MOM_ATR T)
    if path > 0:
        num = (W_MOVE * m * MOM_ATR + W_MOM * q * MOVE_ATR) * path + W_EFF * e * T * MOVE_ATR * MOM_ATR
        den = T * path * MOVE_ATR * MOM_ATR
    else:
        num, den = W_MOVE * m * MOM_ATR + W_MOM * q * MOVE_ATR, T * MOVE_ATR * MOM_ATR
    raw = F(num, den)
    r.update(state="OK", reason="-", dir=d, net=net, recent=recent,
             s_move=F(100 * m, MOVE_ATR * T), s_eff=(F(100 * e, path) if path else F(0)), s_mom=F(100 * q, MOM_ATR * T),
             raw=raw, score=(2 * num + den) // (2 * den), tier=tier(raw))
    return r


def tier(raw):
    return "WEAK" if raw < T_MED else "MED" if raw < T_STRONG else "STRONG"


ZH_TIER = {"WEAK": "弱", "MED": "中等", "STRONG": "强"}


def panel_text(rec, ctx, wait, when):
    """the strength line of the panel (HMI_StrengthEngine.mqh StrPanelText). rec = score() of the last processed bar
    (None before any), when = its close time. Waiting: the last processed bar's score as the last valid result, with
    its time - only when that bar was scored; after a RANGE / TRANSITION bar no earlier direction's score is shown."""
    if wait or rec is None:
        if rec is not None and rec["state"] == "OK":
            return f"趋势强度  等待数据（上次有效结果 {ZH_TIER[rec['tier']]} · {rec['score']}/100，{when} H4 收盘）"
        return "趋势强度  等待数据"
    if rec["state"] == "NODATA":
        return "趋势强度  样本不足（H4 不足 15 根）" if rec["reason"] == "HISTORY" else "趋势强度  不可用（ATR 无效）"
    if rec["state"] == "NODIR":
        return "趋势强度  暂不评级（" + ("区间震荡" if ctx == RANGE else "反转待确认") + "）"
    return f"趋势强度  {ZH_TIER[rec['tier']]} · {rec['score']}/100   数据截至 {when} H4 收盘"


def compact_text(rec, ctx, wait, when):
    """PANEL_COMPACT's strength row (StrPanelShort + StrPanelAsOf, v2.56r4): the score and its H4 close on one row"""
    if wait or rec is None:
        return "强度 等待数据"
    if rec["state"] == "NODATA":
        short = "强度 样本不足" if rec["reason"] == "HISTORY" else "强度 不可用"
    elif rec["state"] == "NODIR":
        short = "强度 暂不评级"
    else:
        short = f"强度 {ZH_TIER[rec['tier']]} {rec['score']}/100"
    return short + f"   数据截至 {when} H4 收盘"


LABEL_MAX = 63          # an MT5 OBJ_LABEL shows this many characters; the rest is cut off


# ---- scenario bars ---------------------------------------------------------------------------------------------
BASE = 1.10000
T0 = int(B.dt.datetime(2026, 9, 7, 0, 0, tzinfo=B.dt.timezone.utc).timestamp())


def make(closes, wicks):
    """closes / wicks in points from BASE; o = previous close, so TR[k] = |dC| + up + down for k >= 1."""
    bars = []
    for i, c in enumerate(closes):
        o = closes[i - 1] if i else c
        up, dn = wicks[i]
        bars.append((T0 + i * H4, round(BASE + o * B.POINT, 5), round(BASE + (max(o, c) + up) * B.POINT, 5),
                     round(BASE + (min(o, c) - dn) * B.POINT, 5), round(BASE + c * B.POINT, 5)))
    return bars


def from_steps(steps, T=7000, pre=None):
    """the last 12 close-to-close steps (bars h-11 .. h; bars 0 .. h-12 flat unless pre gives closes for bars 0 ..),
    wicks of bars h-13 .. h fill T exactly. h = len(pre or 3 flat) + 11."""
    closes = list(pre) if pre else [0, 0, 0]
    for s in steps:
        closes.append(closes[-1] + s)
    h = len(closes) - 1
    travel = sum(abs(closes[k] - closes[k - 1]) for k in range(h - ATR_N + 1, h + 1))
    q, m = divmod(T - travel, ATR_N)
    assert q >= 0, (T, travel)
    wicks = [(0, 0)] * len(closes)
    for j, k in enumerate(range(h - ATR_N + 1, h + 1)):
        v = q + (1 if j < m else 0)
        wicks[k] = (v - v // 2, v // 2)
    return make(closes, wicks)


def target(net, path, recent, T=7000):
    """12 steps with C[h]-C[h-12] = net, sum |dC| = path, C[h]-C[h-3] = recent: a zig-zag of (path - |net-recent| -
    |recent|) / 2 up and down in the first 9 steps, the rest straight."""
    a = net - recent
    z2 = path - abs(a) - abs(recent)
    assert z2 >= 0 and z2 % 2 == 0, (net, path, recent)
    z = z2 // 2
    first = [z, -z] + split(a, 7)
    return from_steps(first + split(recent, 3), T)


def split(x, n):
    s = [int(x / n)] * n
    s[-1] += x - sum(s)
    return s


def mirror(bars):
    return [tuple(b) for b in P.mirror_bars(bars)]


RESULTS = []
ROWS = []


def check(name, cond, detail=""):
    RESULTS.append(bool(cond))
    print(f"{'PASS' if cond else 'FAIL'}  {name}" + ("" if cond else f"\n        !! {detail}"))


def fmt(r):
    if r["state"] != "OK":
        return f"{r['state']}/{r['reason']}"
    return f"move {float(r['s_move']):.2f} eff {float(r['s_eff']):.2f} mom {float(r['s_mom']):.2f} raw {float(r['raw']):.4f}"


def pair(name, bars, h, ctx_bull, want, sub=None):
    """bull case with ctx_bull, mirrored bars with the mirrored context; want = (state, score, tier) for both;
    sub = (s_move, s_eff, s_mom) exact when given."""
    flip = {BULL_CTX: BEAR_CTX, BEAR_CTX: BULL_CTX}
    got_b = None
    for nm, bb, cx in (("bull", bars, ctx_bull), ("bear", mirror(bars), flip.get(ctx_bull, ctx_bull))):
        r = score(bb, h, cx)
        got = (r["state"], r["score"], r["tier"])
        ok = got == want and (sub is None or (r["s_move"], r["s_eff"], r["s_mom"]) == tuple(F(x) for x in sub))
        if nm == "bull":
            got_b = r
        else:
            ok = ok and all(r[k] == got_b[k] for k in ("state", "reason", "raw", "score", "tier", "net", "recent", "path", "T"))
        check(f"{name} [{nm}] -> {got[0]} {got[1]} {got[2]}  ({fmt(r)})", ok,
              f"want {want} sub {sub}, got {got} {fmt(r)}")
    ROWS.append((name, ctx_bull, got_b))
    return got_b


def scenarios():
    print("== the reviewer's three cases (2026-10-26; same increments as its 同净推进同ATR_对照行情.csv) ==")
    pair("V01 steady progress: net 1400, path 1400, recent +350", from_steps([116] * 8 + [122] + [116, 116, 118]), 14,
         BULL_CTX, ("OK", 91, "STRONG"), (F(280, 3), 100, 70))
    pair("V02 same net and ATR, recent pullback: path 3400, recent -1000", from_steps([266] * 8 + [272] + [-333, -333, -334]),
         14, BULL_CTX, ("OK", 56, "MED"), (F(280, 3), F(700, 17), 0))
    pair("V03 net 0, recent recovery +500 -> 20, not 0", from_steps([-55] * 8 + [-60] + [166, 166, 168]), 14,
         BULL_CTX, ("OK", 20, "WEAK"), (0, 0, 100))

    print("\n== each item moves on its own (T = 7000 = 14 x 500 unless noted) ==")
    a = pair("I01 base: net 900, path 1500, recent 300", target(900, 1500, 300), 14, BULL_CTX, ("OK", 60, "MED"),
             (60, 60, 60))
    b = pair("I01 path 2700 (more back and forth): only S_eff falls", target(900, 2700, 300), 14, BULL_CTX,
             ("OK", 51, "MED"), (60, F(100, 3), 60))
    c = pair("I02 recent 100 (same net, path): only S_mom falls", target(900, 1500, 100), 14, BULL_CTX,
             ("OK", 52, "MED"), (60, 60, 20))
    d = pair("I03 T 14000 (ATR doubled, same closes): S_move, S_mom halve, S_eff stays", target(900, 1500, 300, T=14000), 14,
             BULL_CTX, ("OK", 41, "MED"), (30, 60, 30))
    check("I01-I03 only the named item differs from the base",
          (a["s_move"], a["s_mom"]) == (b["s_move"], b["s_mom"]) and a["s_eff"] != b["s_eff"] and
          (a["s_move"], a["s_eff"]) == (c["s_move"], c["s_eff"]) and a["s_mom"] != c["s_mom"] and
          a["s_eff"] == d["s_eff"] and a["s_move"] != d["s_move"] and a["s_mom"] != d["s_mom"])

    print("\n== caps, signs ==")
    pair("C01 net exactly 3 ATR (1500), straight: S_move 100", target(1500, 1500, 375), 14, BULL_CTX, ("OK", 95, "STRONG"),
         (100, 100, 75))
    pair("C01 net 2400 > 3 ATR: S_move capped at 100", target(2400, 2400, 600), 14, BULL_CTX, ("OK", 100, "STRONG"),
         (100, 100, 100))
    pair("C02 recent exactly 1 ATR (500): S_mom 100", target(600, 1000, 500), 14, BULL_CTX, ("OK", 59, "MED"),
         (40, 60, 100))
    pair("C03 net -300, recent +500: only S_mom -> 20 (total not zeroed by net <= 0)", target(-300, 1300, 500), 14,
         BULL_CTX, ("OK", 20, "WEAK"), (0, 0, 100))
    pair("C04 everything against the context: 0, tier WEAK (0 is WEAK, not a separate state)", target(-900, 900, -300), 14,
         BULL_CTX, ("OK", 0, "WEAK"), (0, 0, 0))

    print("\n== tiers on the unrounded score, display rounded half up ==")
    pair("B01 raw 34.5 exactly -> shows 35, tier WEAK", target(500, 1000, 50), 14, BULL_CTX, ("OK", 35, "WEAK"))
    pair("B02 raw 34.96 -> shows 35, tier WEAK", target(500, 1250, 149), 14, BULL_CTX, ("OK", 35, "WEAK"))
    pair("B03 raw 35 exactly -> 35 MED", target(500, 1250, 150), 14, BULL_CTX, ("OK", 35, "MED"))
    pair("B04 raw 64.46 -> 64 MED", target(1000, 2000, 424), 14, BULL_CTX, ("OK", 64, "MED"))
    pair("B05 raw 64.5 exactly -> shows 65, tier MED", target(1000, 2000, 425), 14, BULL_CTX, ("OK", 65, "MED"))
    pair("B06 raw 64.96 -> shows 65, tier MED", target(1000, 1750, 374), 14, BULL_CTX, ("OK", 65, "MED"))
    pair("B07 raw 65 exactly -> 65 STRONG", target(1000, 1750, 375), 14, BULL_CTX, ("OK", 65, "STRONG"))
    for nm, args, want in (("B01", (500, 1000, 50), F(69, 2)), ("B03", (500, 1250, 150), F(35)),
                           ("B05", (1000, 2000, 425), F(129, 2)), ("B07", (1000, 1750, 375), F(65))):
        r = score(target(*args), 14, BULL_CTX)
        check(f"{nm} raw is exactly {want} (no float on the boundary)", r["raw"] == want, str(r["raw"]))

    print("\n== data, direction ==")
    v1 = from_steps([116] * 8 + [122] + [116, 116, 118])
    pair("D01 h = 13 (14 bars): NODATA HISTORY", v1, 13, BULL_CTX, ("NODATA", None, "NA"))
    check("D01 HISTORY reason", score(v1, 13, BULL_CTX)["reason"] == "HISTORY")
    flat = make([0] * 15, [(0, 0)] * 15)
    pair("D02 15 identical bars (T = 0): NODATA ATR, not 0", flat, 14, BULL_CTX, ("NODATA", None, "NA"))
    check("D02 ATR reason", score(flat, 14, BULL_CTX)["reason"] == "ATR")
    still = make([0] * 15, [(20, 20)] * 15)
    pair("D03 closes all equal, bars have range (path = 0, T > 0): valid, S_eff 0 -> 0 WEAK", still, 14, BULL_CTX,
         ("OK", 0, "WEAK"), (0, 0, 0))
    pair("X01 same bars under BEARISH: 0 WEAK (direction decides)", v1, 14, BEAR_CTX, ("OK", 0, "WEAK"))
    pair("X02 RANGE: NODIR", v1, 14, RANGE, ("NODIR", None, "NA"))
    pair("X02 TRANSITION: NODIR", v1, 14, TRANS, ("NODIR", None, "NA"))
    r = score(v1, 14, TRANS)
    check("X02 NODIR still records chg12 / chg3 / path / T", (r["chg12"], r["chg3"], r["path"], r["T"]) == (1400, 350, 1400, 7000),
          str(r))

    print("\n== window: which bars the score reads (h = 19) ==")
    long_ = from_steps([116] * 8 + [122] + [116, 116, 118], pre=[0, 300, -500, 900, 50, 0, 0, 0])
    base = score(long_, 19, BULL_CTX)
    check(f"W01 bars before h-14 do not count (bars 0 .. 4 changed): {base['score']}", base["score"] == 91, fmt(base))

    def setb(bs, i, dc=0, dhi=0, dlo=0):
        bs = list(bs)
        t, o, hi, lo, c = bs[i]
        c2 = round(c + dc * B.POINT, 5)
        bs[i] = (t, o, round(max(hi + dhi * B.POINT, c2), 5), round(min(lo - dlo * B.POINT, c2), 5), c2)
        return bs
    check("W02 a wick on h-14 does not count", score(setb(long_, 5, dhi=2000), 19, BULL_CTX) == base)
    w3 = score(setb(long_, 5, dc=300), 19, BULL_CTX)
    check(f"W03 the close of h-14 counts through TR[h-13]: T {w3['T']} (was {base['T']}), net unchanged",
          w3["T"] > base["T"] and w3["net"] == base["net"] and w3["path"] == base["path"], fmt(w3))
    nxt = long_ + [(long_[-1][0] + H4, long_[-1][4], 1.2, 1.0, 1.15)]
    check("W04 a later bar never changes the score of h (no future)", score(nxt, 19, BULL_CTX) == base)
    w5 = score(setb(long_, 16, dc=-200), 19, BULL_CTX)                 # bar h-3: the recent endpoint (and two path steps)
    check(f"W05 C[h-3] 200 lower: recent {w5['recent']}, net {w5['net']} unchanged, path {w5['path']}",
          w5["recent"] == base["recent"] + 200 and w5["net"] == base["net"] and w5["s_move"] == base["s_move"], fmt(w5))
    w6 = score(setb(long_, 7, dc=-200), 19, BULL_CTX)                  # bar h-12: the net endpoint, first path step
    check(f"W06 C[h-12] 200 lower: net {w6['net']} (+200), path {w6['path']} (+200), recent unchanged",
          w6["net"] == base["net"] + 200 and w6["path"] == base["path"] + 200 and w6["recent"] == base["recent"], fmt(w6))

    print("\n== with the H4 context engine (v2.54 rules; unchanged in v2.55 / v2.56) ==")
    piv = [(1.1000, 0), (1.1100, 6), (1.1040, 3), (1.1160, 6), (1.1100, 3), (1.1220, 6), (1.1050, 8), (1.1110, 3),
           (1.0990, 6), (1.1040, 3), (1.0930, 6), (1.0980, 3), (1.0870, 5)]
    bars = [tuple(x) for x in P.path(piv)]
    for nm, bb in (("bull", bars), ("bear", mirror(bars))):
        before = copy.deepcopy(bb)
        e = P.run254(bb)
        st = {t: s for t, s in e.state_after}
        evs = [(r["kind"], r["bar"]) for r in e.ctx_rows]
        ch = [t for k, t in evs if k == "CHOCH"]
        ok = [t for k, t in evs if k in ("TRANS_OK", "TRANS_FAIL")]
        bos = [t for k, t in evs if k == "BOS"]
        idx = {bb[i][0] + H4: i for i in range(len(bb))}
        rows_before = copy.deepcopy(e.ctx_rows)
        recs = {h: score(bb, h, st[bb[h][0] + H4]) for h in range(len(bb))}
        c1 = bool(ch) and all(recs[idx[t]]["state"] == "NODIR" and recs[idx[t] - 1]["state"] == "OK" for t in ch)
        check(f"E01 [{nm}] CHOCH bar -> NODIR on that bar; the bar before is scored ({len(ch)} CHOCH)", c1,
              f"events {[(k, tstr(t)) for k, t in evs]}")
        c2 = bool(ok) and all(recs[idx[t]]["state"] == "OK" and recs[idx[t]]["dir"] == (1 if st[t] == BULL_CTX else -1)
                              for t in ok)
        check(f"E02 [{nm}] TRANS_OK / TRANS_FAIL bar -> scored in the new direction on that bar ({len(ok)})", c2)
        trend = [h for h in range(ATR_N, len(bb)) if st[bb[h][0] + H4] in (BULL_CTX, BEAR_CTX)]
        c3 = bool(bos) and all(recs[h]["state"] == "OK" for h in trend)
        check(f"E03 [{nm}] every trend bar from h = 14 is scored, BOS bars included ({len(trend)} bars, {len(bos)} BOS)", c3)
        check(f"E05 [{nm}] scoring reads only: bars and context events unchanged after scoring every bar",
              bb == before and e.ctx_rows == rows_before)
    a2 = from_steps([116] * 8 + [122] + [116, 116, 118], pre=[0] * 28)
    b2 = from_steps([116] * 8 + [122] + [116, 116, 118], pre=[((i % 6) * 120 - 300) for i in range(25)] + [0, 0, 0])
    check("E04 identical last 15 bars, different history before -> identical score (independent of BOS count / leg)",
          score(a2, len(a2) - 1, BULL_CTX) == score(b2, len(b2) - 1, BULL_CTX))

    print("\n== panel line (display; same rules in MQL) ==")
    ok_rec = score(v1, 14, BULL_CTX)
    t1 = "2026.10.26 12:00"
    check("P01 OK: tier word, score and the H4 close time",
          panel_text(ok_rec, BULL_CTX, False, t1) == "趋势强度  强 · 91/100   数据截至 2026.10.26 12:00 H4 收盘")
    check("P02 waiting after a scored bar: says so, gives it as the last valid result with its time",
          panel_text(ok_rec, BULL_CTX, True, t1) == "趋势强度  等待数据（上次有效结果 强 · 91/100，2026.10.26 12:00 H4 收盘）")
    check("P03 waiting before any bar", panel_text(None, RANGE, True, "") == "趋势强度  等待数据")
    check("P04 HISTORY / ATR", panel_text(score(v1, 13, BULL_CTX), BULL_CTX, False, t1) == "趋势强度  样本不足（H4 不足 15 根）"
          and panel_text(score(flat, 14, BULL_CTX), BULL_CTX, False, t1) == "趋势强度  不可用（ATR 无效）")
    check("P05 RANGE / TRANSITION: no number",
          panel_text(score(v1, 14, RANGE), RANGE, False, t1) == "趋势强度  暂不评级（区间震荡）" and
          panel_text(score(v1, 14, TRANS), TRANS, False, t1) == "趋势强度  暂不评级（反转待确认）")
    check("P06 waiting after a RANGE bar: no earlier direction's score", panel_text(score(v1, 14, RANGE), RANGE, True, t1) == "趋势强度  等待数据")
    check("P07 COMPACT row: score and H4 close together; waiting: no time",
          compact_text(ok_rec, BULL_CTX, False, t1) == "强度 强 91/100   数据截至 2026.10.26 12:00 H4 收盘" and
          compact_text(ok_rec, BULL_CTX, True, t1) == "强度 等待数据")
    worst = dict(ok_rec, tier="MED", score=100)                     # the longest tier word and score
    rows = [panel_text(worst, BULL_CTX, w, t1) for w in (False, True)] + [compact_text(worst, BULL_CTX, False, t1)] + \
           [f(score(v1, 13, BULL_CTX), BULL_CTX, False, t1) for f in (panel_text, compact_text)] + \
           [f(score(flat, 14, BULL_CTX), BULL_CTX, False, t1) for f in (panel_text, compact_text)] + \
           [f(score(v1, 14, c), c, False, t1) for f in (panel_text, compact_text) for c in (RANGE, TRANS)]
    longest = max(rows, key=len)
    check(f"P08 every strength row fits an OBJ_LABEL ({LABEL_MAX} characters; longest {len(longest)}: {longest})",
          len(longest) <= LABEL_MAX)


# ---- log rows, formatted as HMI_StrengthEngine.mqh prints them (for tools/logtests) -------------------------------
def tstr16(t):
    return tstr(t)


def str_row(bars, h, ctx, live=0, sym="USDJPY", inst="0001", run=7, init=1, rec=None):
    r = rec or score(bars, h, ctx)
    ok, raw = r["state"] == "OK", r["reason"] != "HISTORY"
    na = lambda v, cond, f=str: (f(v) if cond else "NA")              # noqa: E731
    d6 = lambda v: f"{float(v):.6f}"                                   # noqa: E731
    return (f"HMI-STR,{sym},live={live},bar={tstr16(bars[h][0] + H4)},ctx={ctx},state={r['state']},reason={r['reason']},"
            f"def={DEF_ID},dir={r['dir']},chg12={na(r['chg12'], raw)},chg3={na(r['chg3'], raw)},path={na(r['path'], raw)},"
            f"tr_sum={na(r['T'], raw)},net={na(r['net'], ok)},recent={na(r['recent'], ok)},s_move={na(r['s_move'], ok, d6)},"
            f"s_eff={na(r['s_eff'], ok, d6)},s_mom={na(r['s_mom'], ok, d6)},raw={na(r['raw'], ok, d6)},score={na(r['score'], ok)},"
            f"tier={r['tier']},inst={inst},run={run},init={init}")


def hist_row(bars, recs, sym="USDJPY", inst="0001", run=7, init=1):
    """recs: score() of every processed bar 0 .. len(recs)-1"""
    h = [0] * 101
    ok = [r for r in recs if r["state"] == "OK"]
    for r in ok:
        h[r["score"]] += 1
    n = lambda st: sum(1 for r in recs if r["state"] == st)            # noqa: E731
    t = lambda k: sum(1 for r in ok if r["tier"] == k)                  # noqa: E731
    return (f"HMI-STR-HIST,{sym},live=0,def={DEF_ID},from={tstr16(bars[0][0] + H4)},to={tstr16(bars[len(recs) - 1][0] + H4)},"
            f"bars={len(recs)},ok={len(ok)},nodir={n('NODIR')},nodata={n('NODATA')},weak={t('WEAK')},med={t('MED')},"
            f"strong={t('STRONG')},h={';'.join(map(str, h))},inst={inst},run={run},init={init}")


def engine_series():
    """the E-scenario path: bars, the context after each bar (v2.54 engine)"""
    piv = [(1.1000, 0), (1.1100, 6), (1.1040, 3), (1.1160, 6), (1.1100, 3), (1.1220, 6), (1.1050, 8), (1.1110, 3),
           (1.0990, 6), (1.1040, 3), (1.0930, 6), (1.0980, 3), (1.0870, 5)]
    bars = [tuple(x) for x in P.path(piv)]
    e = P.run254(bars)
    return bars, [s for _, s in e.state_after]


def boundary_cases():
    """(bars, h, ctx) of the exact-boundary and reviewer scenarios, for row-level recomputation tests"""
    out = [(from_steps([116] * 8 + [122] + [116, 116, 118]), 14, BULL_CTX),
           (from_steps([266] * 8 + [272] + [-333, -333, -334]), 14, BULL_CTX),
           (from_steps([-55] * 8 + [-60] + [166, 166, 168]), 14, BULL_CTX)]
    for a in ((500, 1000, 50), (500, 1250, 149), (500, 1250, 150), (1000, 2000, 424), (1000, 2000, 425),
              (1000, 1750, 374), (1000, 1750, 375), (-300, 1300, 500), (-900, 900, -300), (2400, 2400, 600)):
        out.append((target(*a), 14, BULL_CTX))
    out += [(mirror(b), h, BEAR_CTX) for (b, h, _) in out]
    out.append((make([0] * 15, [(0, 0)] * 15), 14, BULL_CTX))           # NODATA / ATR
    out.append((make([0] * 15, [(20, 20)] * 15), 14, BULL_CTX))         # path 0, valid
    return out


def replay(path_csv):
    bars = B.load_h1(path_csv)
    print(f"replay {path_csv}: {len(bars)} H4 bars {tstr(bars[0][0])} .. {tstr(bars[-1][0])}")
    e = P.run254(bars)
    st = [s for _, s in e.state_after]
    rows = [score(bars, h, st[h]) for h in range(len(bars))]
    bad = 0
    for h in range(40, len(bars), 37):
        ep = P.run254(bars[:h + 1])
        if score(bars[:h + 1], h, ep.state_after[-1][1]) != rows[h]:
            bad += 1
    check("R1 prefix: score of h from bars[:h+1] equals the full run (every 37th bar from 40)", bad == 0, f"{bad} differ")
    mb = mirror(bars)
    em = P.run254(mb)
    flip = {BULL_CTX: BEAR_CTX, BEAR_CTX: BULL_CTX}
    smis = sum(1 for (_, a), (_, b) in zip(e.state_after, em.state_after) if flip.get(a, a) != b)
    mrows = [score(mb, h, em.state_after[h][1]) for h in range(len(mb))]
    dif = sum(1 for a, b in zip(rows, mrows) if (a["state"], a["raw"]) != (b["state"], b["raw"]))
    check(f"R2 mirror: mirrored bars give the mirrored context and the same raw score on every bar ({dif} differ, "
          f"context {smis} differ)", dif == 0 and smis == 0)
    from collections import Counter
    c = Counter((r["state"], r["reason"]) for r in rows)
    ok = [r for r in rows if r["state"] == "OK"]

    def pct(v, q):
        v = sorted(v)
        k = (len(v) - 1) * q / 100.0
        f = int(k); cc = min(f + 1, len(v) - 1)
        return v[f] + (v[cc] - v[f]) * (k - f)
    print("\nstates: " + ", ".join(f"{s}/{r} {n}" for (s, r), n in sorted(c.items())))
    print("distribution record (not a calibration; thresholds stay 35 / 65 unless a definition revision says otherwise):")
    for nm, key in (("raw", "raw"), ("S_move", "s_move"), ("S_eff", "s_eff"), ("S_mom", "s_mom")):
        v = [float(r[key]) for r in ok]
        print(f"  {nm:7s} " + "  ".join(f"P{q} {pct(v, q):6.2f}" for q in (10, 25, 33, 50, 67, 75, 90)) +
              f"   = 0: {sum(1 for x in v if x == 0)}  = 100: {sum(1 for x in v if x == 100)}")
    tc = Counter(r["tier"] for r in ok)
    print(f"  tiers (35 / 65 on raw): WEAK {tc['WEAK']}  MED {tc['MED']}  STRONG {tc['STRONG']}  of {len(ok)}")
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
