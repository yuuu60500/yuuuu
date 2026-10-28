"""v2.58 final panel - offline model of docs/02 BRI-15: the stage (requirement §7), the reasons (§8), the strength
arrow (§5.4) and the six-row trend panel (§2) of 《HMI 趋势面板改造需求（工程师版）》 (docs/requirements/). Not the MQL
implementation; it fixes what each case must give. Display only (Rule 69): nothing in the H4 / POI / session / MODEL
chain reads it, and it reads only what the strength (BRI-13) and quality (BRI-14) records and the v2.54 context
already hold - it computes no score of its own.

Definition (bar h = the H4 bar just processed; prices in integer points; D = +1 BULLISH / -1 BEARISH after h;
T = the strength record's 14-bar TR sum, so ATR14 = T / 14; x, L, ext = the quality record's retrace items):

  stage, the first that holds (§7):
    NODATA    strength NODATA / HISTORY (fewer than 15 closed H4 bars)                样本不足
    NOATR     strength NODATA / ATR (the 14 TR are all 0)                              不可用
    TRANS     TRANSITION                                                              反转待确认
    RANGE     RANGE                                                                   区间震荡
    BUILD     trend, no legal protected level (P-6a INVALID, no later SET), or the retrace items unavailable
              (quality LEG / SCALE)                                                   结构待完善
    DEEP      3 x > 2 L  (r > 2/3)                                                    深度回撤
    PUSH      refresh and near                                                        延续推进
    CONSOL    near, no refresh                                                        高位整理 (bull) / 低位整理 (bear)
    PULLBACK  otherwise                                                               正常回撤
      refresh  bar h's high (bull) / low (bear) beyond the leg's extreme over bars a+1 .. h-1 (a = leg_anchor bar;
               strictly; no such bar -> no refresh)
      near     dist = D (ext - C[h]) (not clamped), 56 dist <= T  (dist <= 0.25 ATR14)
  reasons, at most two, in this order (§8; strengths only when no state reason and no risk applies):
    state     PROT_BROKEN   TRANSITION opened by an effective close beyond the protected level (P-4)
                            多头保护低点已破 / 空头保护高点已破
              SWING_BROKEN  TRANSITION opened by the P-6b fallback (the leg had no protected level)
                            多头低点已破（无保护点） / 空头高点已破（无保护点）
              TIMEOUT       RANGE entered from a TRANSITION that ran out (InpH4TransitionMaxBars)  过渡超 18 根未确认
              NO_PROT       BUILD without a protected level                         缺少保护点
              LEG           BUILD with the retrace items unavailable                波段长度无效
    risk      DEEP          3 x > 2 L                                               回撤偏深
              BRK_FAIL      a failed event among the quality record's mature events used   近期突破失败
              COUNTER       S_mom = 0 and recent < 0                                近期逆向运行
              CHOP          path > 0 and S_eff < 35  (100 e < 35 path)              价格往返明显
    strength  MOVE          S_move >= 65  (100 m >= 195 T)                          同向推进明显
              RET           Q_retrace >= 70  (num_r >= 70 L)                        回撤较浅
              BRK           n >= 3 and every one held (s = n; with no risk there is no failed event, so a
                            Q_break below 100 never reaches this list)            突破全部守住
              EFF           S_eff >= 65                                             推进效率高
              MOM           S_mom >= 65  (100 q >= 65 T)                            近期推进有力
              OVL           Q_overlap >= 70                                         K 线重叠少
    none in a trend -> 无突出分项; NODATA / NOATR -> —
  arrow (strength OK at h): ref = h - 3; strength OK at ref, the same leg (g_leg_seq) -> d = score(h) - score(ref),
    the displayed integers: d >= 5 UP ↑, d <= -5 DOWN ↓, else FLAT →; otherwise NEW 新趋势

    python3 tools/stage_sim.py                       cases, both directions
    python3 tools/stage_sim.py --replay <H1 csv>     real data: prefix stability, mirror, stage / reason record
"""
import os
import sys
from collections import Counter
from fractions import Fraction as F

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import h4_dedup_sim as B                                        # noqa: E402
import h4_protect_sim as P                                      # noqa: E402
import strength_sim as S                                        # noqa: E402
import quality_sim as Q                                         # noqa: E402
from h4_dedup_sim import BULL_CTX, BEAR_CTX, TRANS, RANGE, H4, tstr  # noqa: E402

NEAR_K = 56                     # 56 dist <= T  <=>  dist <= T / 14 / 4 = 0.25 ATR14 (requirement §7 / §10)
EFF_LOW = 35                    # §8 "方向效率低于 35"
POS_STR, POS_QLT = 65, 70       # strength items / quality items count as high at their score's top tier boundary
ARR_BARS, ARR_DELTA = 3, 5      # §5.4 / §10
TRANS_MAX = 18                  # InpH4TransitionMaxBars default (the TIMEOUT text shows the input's value)
DEF_ID = "STG1-NEAR25-DEEP2.3-EFF35-POS65.70-ARR3.5"
LABEL_MAX = S.LABEL_MAX         # an MT5 OBJ_LABEL shows 63 characters

STAGES = ("NODATA", "NOATR", "TRANS", "RANGE", "BUILD", "DEEP", "PUSH", "CONSOL", "PULLBACK")
REASONS = ("PROT_BROKEN", "SWING_BROKEN", "TIMEOUT", "NO_PROT", "LEG", "DEEP", "BRK_FAIL", "COUNTER", "CHOP",
           "MOVE", "RET", "BRK", "EFF", "MOM", "OVL")
ARROWS = ("UP", "DOWN", "FLAT", "NEW")
RISK = ("DEEP", "BRK_FAIL", "COUNTER", "CHOP")


def stage_rec(d_ctx, pend, chk, prot, s, q, bars_hl, ref):
    """the stage record of one bar.
    d_ctx   the context after h (BULL_CTX / BEAR_CTX / TRANS / RANGE)
    pend    TRANSITION's pending direction (+1 / -1), else 0
    chk     TRANSITION: "BREAK" / "FALLBACK" (how it opened); RANGE: "TIMEOUT" / "INIT"; else "-"
    prot    trend: the protected level exists (bool); else None
    s, q    strength_sim.score() / quality_sim.quality() of h
    bars_hl (prev_ext, bar_ext): the leg's extreme over a+1 .. h-1 (None: no such bar) and bar h's high (bull) /
            low (bear), points; None outside the retrace cases
    ref     (score, same_leg) of the strength record of h - 3 when it is OK, else None"""
    r = dict(stage=None, reasons=[], dir=0, pend=pend, chk=chk, prot=prot, prev_ext=None, bar_ext=None, ext=None,
             close=q["close"], dist=None, T=s["T"], refresh=None, near=None, arrow="NA", ref_score=None,
             score=s["score"])
    if s["state"] == "OK" and ref is not None:
        r["ref_score"] = ref[0]
    if s["state"] == "OK":
        if ref is None or not ref[1]:
            r["arrow"] = "NEW"
        else:
            dl = s["score"] - ref[0]
            r["arrow"] = "UP" if dl >= ARR_DELTA else "DOWN" if dl <= -ARR_DELTA else "FLAT"
    d = 1 if d_ctx == BULL_CTX else -1 if d_ctx == BEAR_CTX else 0
    r["dir"] = d
    if d != 0 and q["x"] is not None:
        prev_ext, bar_ext = bars_hl
        dist = d * (q["ext"] - q["close"])
        r.update(prev_ext=prev_ext, bar_ext=bar_ext, ext=q["ext"], dist=dist,
                 refresh=int(prev_ext is not None and d * (bar_ext - prev_ext) > 0),
                 near=int(NEAR_K * dist <= s["T"]) if s["T"] else None)
    rs = r["reasons"]
    if s["state"] == "NODATA":
        r["stage"] = "NODATA" if s["reason"] == "HISTORY" else "NOATR"
        return r
    if d_ctx == TRANS:
        r["stage"] = "TRANS"
        if chk in ("BREAK", "FALLBACK"):
            rs.append("PROT_BROKEN" if chk == "BREAK" else "SWING_BROKEN")
        return r
    if d_ctx == RANGE:
        r["stage"] = "RANGE"
        if chk == "TIMEOUT":
            rs.append("TIMEOUT")
        return r
    # a trend; strength is OK here (NODATA returned above, NODIR cannot be a trend)
    if not prot:
        r["stage"] = "BUILD"
        rs.append("NO_PROT")
    elif q["x"] is None:
        r["stage"] = "BUILD"
        rs.append("LEG")
    else:
        x, L = q["x"], q["leg"]
        if 3 * x > 2 * L:
            r["stage"] = "DEEP"
        elif r["refresh"] and r["near"]:
            r["stage"] = "PUSH"
        elif r["near"]:
            r["stage"] = "CONSOL"
        else:
            r["stage"] = "PULLBACK"
    T, net, recent, path = s["T"], s["net"], s["recent"], s["path"]
    m = min(max(14 * net, 0), 3 * T)
    e = min(max(net, 0), path)
    qm = min(max(14 * recent, 0), T)
    risks = []
    if q["x"] is not None and 3 * q["x"] > 2 * q["leg"]:
        risks.append("DEEP")
    if q["fail"] > 0:
        risks.append("BRK_FAIL")
    if qm == 0 and recent < 0:
        risks.append("COUNTER")
    if path > 0 and 100 * e < EFF_LOW * path:
        risks.append("CHOP")
    rs.extend(risks)
    if not rs:
        pos = []
        if 100 * m >= POS_STR * 3 * T:
            pos.append("MOVE")
        if q["x"] is not None and q["num_r"] >= POS_QLT * q["leg"]:
            pos.append("RET")
        if q["n"] >= Q.EV_MIN and q["s"] == q["n"]:
            pos.append("BRK")
        if path > 0 and 100 * e >= POS_STR * path:
            pos.append("EFF")
        if 100 * qm >= POS_STR * T:
            pos.append("MOM")
        if 100 * (11 * Q.FP - q["so"]) >= POS_QLT * 11 * Q.FP:
            pos.append("OVL")
        rs.extend(pos)
    del rs[2:]
    return r


# ---- the engine run: what the MQL engine holds after each processed bar ------------------------------------------
def run(bars, margins=None):
    """-> [stage rec per bar], [strength], [quality], [ctx], engine"""
    e = P.Engine254(True, margins)
    t = Q.Tracker(Q.LEG_START, Q.EV_WIN)
    tidx = {b[0]: k for k, b in enumerate(bars)}
    out, strs, qrecs, ctxs, legs = [], [], [], [], []
    prot_prev = False
    trans_kind = "-"
    for h in range(len(bars)):
        n0 = len(e.ctx_rows)
        e.process(bars, h)
        q = t.on_bar(bars, h, e, e.ctx_rows[n0:], tidx)
        s = S.score(bars, h, e.ctx)
        tclose = bars[h][0] + H4
        if e.ctx == TRANS and e.ctx_time == tclose:
            trans_kind = "BREAK" if prot_prev else "FALLBACK"
        chk = (trans_kind if e.ctx == TRANS else ("TIMEOUT" if e.ctx_time != 0 else "INIT") if e.ctx == RANGE else "-")
        d = 1 if e.ctx == BULL_CTX else -1 if e.ctx == BEAR_CTX else 0
        hl = None
        if d != 0 and q["x"] is not None:
            a = q["anchor"][0]
            prev = [Q.H(bars, i) if d == 1 else Q.L_(bars, i) for i in range(a + 1, h)]
            prev_ext = (max(prev) if d == 1 else min(prev)) if prev else None
            hl = (prev_ext, Q.H(bars, h) if d == 1 else Q.L_(bars, h))
        ref = None
        if s["state"] == "OK" and h >= ARR_BARS and strs[h - ARR_BARS]["state"] == "OK":
            ref = (strs[h - ARR_BARS]["score"], legs[h - ARR_BARS] == e.leg)
        r = stage_rec(e.ctx, e.pending if e.ctx == TRANS else 0, chk, (e.prot is not None) if d else None, s, q, hl, ref)
        r["anchor"] = q["anchor"]
        r["close"] = Q.C(bars, h)
        out.append(r)
        strs.append(s); qrecs.append(q); ctxs.append(e.ctx); legs.append(e.leg)
        prot_prev = e.prot is not None
    return out, strs, qrecs, ctxs, e


# ---- panel text (display; HMI_StageEngine.mqh must give the same) --------------------------------------------------
ZH_STAGE = {"NODATA": "样本不足", "NOATR": "不可用", "TRANS": "反转待确认", "RANGE": "区间震荡", "BUILD": "结构待完善",
            "DEEP": "深度回撤", "PUSH": "延续推进", "PULLBACK": "正常回撤"}
ZH_REASON = {"TIMEOUT": f"过渡超 {TRANS_MAX} 根未确认", "NO_PROT": "缺少保护点", "LEG": "波段长度无效",
             "DEEP": "回撤偏深", "BRK_FAIL": "近期突破失败", "COUNTER": "近期逆向运行", "CHOP": "价格往返明显",
             "MOVE": "同向推进明显", "RET": "回撤较浅", "BRK": "突破全部守住",
             "EFF": "推进效率高", "MOM": "近期推进有力", "OVL": "K 线重叠少"}
ZH_ARROW = {"UP": "↑", "DOWN": "↓", "FLAT": "→", "NEW": "新趋势"}
LABELS = ("H4 趋势", "趋势强度", "趋势质量", "当前阶段", "主要原因", "数据截至")


def stage_zh(r):
    if r["stage"] == "CONSOL":
        return "高位整理" if r["dir"] == 1 else "低位整理"
    return ZH_STAGE[r["stage"]]


def reason_zh(code, r):
    if code == "PROT_BROKEN":            # pending DOWN: a bull leg's protected low broke
        return "多头保护低点已破" if r["pend"] == -1 else "空头保护高点已破"
    if code == "SWING_BROKEN":
        return "多头低点已破（无保护点）" if r["pend"] == -1 else "空头高点已破（无保护点）"
    return ZH_REASON[code]


def strength_value(s, arrow, wait):
    if wait:
        return f"等待数据（上次有效结果 {S.ZH_TIER[s['tier']]} · {s['score']}/100）" if s and s["state"] == "OK" else "等待数据"
    if s["state"] == "NODATA":
        return "样本不足（H4 不足 15 根）" if s["reason"] == "HISTORY" else "不可用（ATR 无效）"
    if s["state"] == "NODIR":
        return "暂不评级"
    return f"{S.ZH_TIER[s['tier']]} · {s['score']}/100 {ZH_ARROW[arrow]}"


def quality_value(q, wait):
    if wait:
        return f"等待数据（上次有效结果 {Q.ZH_TIER[q['tier']]} · {q['score']}/100）" if q and q["state"] == "OK" else "等待数据"
    if q["state"] == "NODATA":
        return "样本不足（H4 不足 12 根）"
    if q["state"] == "NODIR":
        return "暂不评级"
    if q["state"] == "PARTIAL":
        head = "样本不足" if "FEW" in q["reason"].split("+") else "不可用"
        return f"{head}（{Q._why(q)}）  局部表现 {Q._local(q)}"
    return f"{Q.ZH_TIER[q['tier']]} · {q['score']}/100（{Q._sample(q)}）"


def panel_rows(r, s, q, ctx, when, wait=False, ready=True):
    """the trend panel, six (label, value, colour) rows; colour: BULL / BEAR / TRANS / RANGE for the direction row,
    else BASE. r, s, q = the stage, strength and quality records of the last processed bar (None before any);
    when = its close time; wait = a series did not deliver (the strength WAIT state)"""
    if not ready or r is None:
        vals = ["等待数据"] * 4 + ["—", "等待数据"]
        return [(lab, v, "BASE") for lab, v in zip(LABELS, vals)]
    if wait:
        vals = ["等待数据", strength_value(s, None, True), quality_value(q, True), "等待数据", "—",
                f"上次有效结果 {when} H4 收盘（服务器时间）"]
        return [(lab, v, "BASE") for lab, v in zip(LABELS, vals)]
    if ctx == BULL_CTX:
        dv, dc = "▲ 多头", "BULL"
    elif ctx == BEAR_CTX:
        dv, dc = "▼ 空头", "BEAR"
    elif ctx == TRANS:
        dv, dc = "过渡 · " + ("偏多待确认" if r["pend"] == 1 else "偏空待确认"), "TRANS"
    else:
        dv, dc = "区间震荡", "RANGE"
    if r["reasons"]:
        why = "，".join(reason_zh(c, r) for c in r["reasons"])
    else:
        why = "无突出分项" if r["dir"] != 0 else "—"
    vals = [dv, strength_value(s, r["arrow"], False), quality_value(q, False), stage_zh(r), why,
            f"{when} H4 收盘（服务器时间）"]
    return [(lab, v, dc if i == 0 else "BASE") for i, (lab, v) in enumerate(zip(LABELS, vals))]


def items_rows(s, q):
    """PANEL_FULL's item rows on the diagnostic panel: the strength items (strength OK) and the quality items shown
    as 局部表现 (trend bars), half-up rounded; None when the row is not shown"""
    si = qi = None
    if s is not None and s["state"] == "OK":
        T, net, recent, path = s["T"], s["net"], s["recent"], s["path"]
        m, e, qm = min(max(14 * net, 0), 3 * T), min(max(net, 0), path), min(max(14 * recent, 0), T)
        si = (f"强度分项  净推进 {Q.rnd(F(100 * m, 3 * T))} · 效率 {Q.rnd(F(100 * e, path)) if path else 0}"
              f" · 动量 {Q.rnd(F(100 * qm, T))}")
    if q is not None and q["state"] in ("OK", "PARTIAL"):
        qi = f"质量分项  {Q._local(q)}"
    return si, qi


def wrap(text, limit=LABEL_MAX, indent="    "):
    """the diagnostic panel's long rows (CYCLE, POI, LIQ HISTORY, the TRANSITION summary): a row longer than the label
    limit is cut at the last gap that keeps the piece within it - a " | " gap first, then a two-space gap, then any
    space - but only where the piece keeps at least half the limit; the separator itself is dropped and the rest goes
    on an indented row. A single word longer than the limit is cut (the panel's own words never are)."""
    out, cur = [], text
    while len(cur) > limit:
        cut, skip = -1, 0
        for sep in ("|", "  "):
            k = cur.rfind(sep, 0, limit + 1)
            if k >= limit // 2:
                cut, skip = k, len(sep)
                break
        if cut < 0:
            k = cur.rfind(" ", 0, limit + 1)
            if k > len(indent):
                cut, skip = k, 1
        if cut < 0:
            out.append(cur[:limit]); cur = indent + cur[limit:]
            continue
        out.append(cur[:cut].rstrip()); cur = indent + cur[cut + skip:].lstrip()
    out.append(cur)
    return out


# ---- log rows, formatted as the MQL engine is to print them (for tools/logtests) -----------------------------------
def px(v):
    return "NA" if v is None else f"{v * B.POINT:.5f}"


def stg_row(bars, h, ctx, r, live=0, sym="USDJPY", inst="0001", run_=7, init=1):
    na = lambda v: "NA" if v is None else str(v)                     # noqa: E731
    a = r.get("anchor")
    trend_x = r["dist"] is not None
    return (f"HMI-STG,{sym},live={live},bar={tstr(bars[h][0] + H4)},ctx={ctx},stage={r['stage']},"
            f"reasons={'+'.join(r['reasons']) or '-'},def={DEF_ID},dir={r['dir']},"
            f"pend={'UP' if r['pend'] == 1 else 'DOWN' if r['pend'] == -1 else '-'},chk={r['chk']},"
            f"prot={'NA' if r['prot'] is None else int(r['prot'])},"
            f"anchor_bar={tstr(bars[a[0]][0]) if (trend_x and a) else '-'},prev_ext={px(r['prev_ext'])},"
            f"bar_ext={px(r['bar_ext'])},ext={px(r['ext'])},close={px(r['close'])},dist_pts={na(r['dist'])},"
            f"tr_sum={na(r['T'])},refresh={na(r['refresh'])},near={na(r['near'])},arrow={r['arrow']},"
            f"ref_bar={tstr(bars[h - ARR_BARS][0] + H4) if r['arrow'] != 'NA' and h >= ARR_BARS else '-'},"
            f"ref_score={na(r['ref_score'])},score={na(r['score'])},inst={inst},run={run_},init={init}")


def stg_hist_row(bars, recs, sym="USDJPY", inst="0001", run_=7, init=1):
    st = Counter(r["stage"] for r in recs)
    rc = Counter(c for r in recs for c in r["reasons"])
    ac = Counter(r["arrow"] for r in recs)
    return (f"HMI-STG-HIST,{sym},live=0,def={DEF_ID},from={tstr(bars[0][0] + H4)},to={tstr(bars[len(recs) - 1][0] + H4)},"
            f"bars={len(recs)}," + ",".join(f"{k.lower()}={st[k]}" for k in STAGES) +
            ",rs=" + ";".join(str(rc[k]) for k in REASONS) + "," +
            ",".join(f"{k.lower()}={ac[k]}" for k in ARROWS) + f",inst={inst},run={run_},init={init}")


# ---- cases ---------------------------------------------------------------------------------------------------------
RESULTS = []


def check(name, cond, detail=""):
    RESULTS.append(bool(cond))
    print(f"{'PASS' if cond else 'FAIL'}  {name}" + ("" if cond else f"\n        !! {detail}"))


def srec(T=1400, net=200, recent=100, path=400, score=60, tier="MED", state="OK", reason="-"):
    """a strength record with the items stage_rec reads (the score and tier are given, not computed: the arrow and the
    panel read them as they stand)"""
    return dict(state=state, reason=reason, T=T, net=net, recent=recent, path=path, score=score, tier=tier,
                dir=1, s_move=None, s_eff=None, s_mom=None)


def qrec(leg=300, x=50, ext=2000, n=3, s=3, fail=0, so=6_000_000, state="OK", reason="-", pend=0, score=70,
         tier="GOOD", sample="LOW"):
    q = dict(state=state, reason=reason, n=n, s=s, fail=fail, pend=pend, leg=leg, x=x, ext=ext,
             close=(ext - x if x is not None else 1900), so=so, score=score, tier=tier, sample=sample,
             q_break=(F(100 * s, n) if n >= Q.EV_MIN else None), q_overlap=F(100 * (11 * Q.FP - so), 11 * Q.FP))
    q["num_r"] = None if x is None else Q.retrace_num(x, leg)
    q["q_retrace"] = None if x is None else F(q["num_r"], leg)
    return q


def flip(q):
    """the same quality record seen in a bear leg: prices mirrored (ext, close), distances unchanged"""
    m = dict(q)
    m["ext"] = None if q["ext"] is None else Q.MP - q["ext"]
    m["close"] = Q.MP - q["close"]
    return m


def case(name, want_stage, want_reasons, s, q, prot=True, hl=(1990, 2000), ref=(55, True), want_arrow=None,
         ctx=BULL_CTX, pend=0, chk="-"):
    """stage_rec on the bull inputs and on their bear mirror: stage, reasons, arrow and the refresh / near flags must
    be the expected ones in both"""
    out = []
    for nm in ("bull", "bear"):
        if nm == "bull":
            r = stage_rec(ctx, pend, chk, prot if ctx in (BULL_CTX, BEAR_CTX) else None, s, q, hl, ref)
        else:
            c2 = BEAR_CTX if ctx == BULL_CTX else BULL_CTX if ctx == BEAR_CTX else ctx
            hl2 = None if hl is None else (None if hl[0] is None else Q.MP - hl[0], Q.MP - hl[1])
            r = stage_rec(c2, -pend, chk, prot if ctx in (BULL_CTX, BEAR_CTX) else None, s, flip(q), hl2, ref)
        ok = r["stage"] == want_stage and r["reasons"] == want_reasons and (want_arrow is None or r["arrow"] == want_arrow)
        check(f"{name} [{nm}]  {r['stage']} {'+'.join(r['reasons']) or '-'} {r['arrow']}"
              f"  refresh {r['refresh']} near {r['near']}", ok,
              f"want {want_stage} {want_reasons} {want_arrow}")
        out.append(r)
    return out


def cases():
    # ---- stage priority (§7) ---------------------------------------------------------------------------------------
    base_s = srec()                       # S_move = 100*min(2800,4200)/4200 = 66.7 ; S_eff 50 ; S_mom 100 ; T 1400 -> near <= 25
    case("S01 strength NODATA / HISTORY before everything (TRANSITION too)", "NODATA", [],
         srec(state="NODATA", reason="HISTORY", T=None), qrec(state="NODATA", x=None), ctx=TRANS, pend=-1, chk="BREAK",
         hl=None, ref=None, want_arrow="NA")
    case("S02 strength NODATA / ATR", "NOATR", [], srec(state="NODATA", reason="ATR", T=0), qrec(state="NODATA", x=None),
         hl=None, ref=None, want_arrow="NA")
    case("S03 TRANSITION opened by the protected level: 多头保护低点已破", "TRANS", ["PROT_BROKEN"],
         srec(state="NODIR"), qrec(state="NODIR", x=None), ctx=TRANS, pend=-1, chk="BREAK", hl=None, ref=None,
         want_arrow="NA")
    case("S04 TRANSITION opened by the P-6b fallback", "TRANS", ["SWING_BROKEN"], srec(state="NODIR"),
         qrec(state="NODIR", x=None), ctx=TRANS, pend=1, chk="FALLBACK", hl=None, ref=None)
    case("S05 RANGE after a TRANSITION timed out", "RANGE", ["TIMEOUT"], srec(state="NODIR"), qrec(state="NODIR", x=None),
         ctx=RANGE, chk="TIMEOUT", hl=None, ref=None)
    case("S06 RANGE at the start of history: no reason", "RANGE", [], srec(state="NODIR"), qrec(state="NODIR", x=None),
         ctx=RANGE, chk="INIT", hl=None, ref=None)
    case("S07 trend without a protected level: 结构待完善 / 缺少保护点 (+ the first risk)", "BUILD", ["NO_PROT", "COUNTER"],
         srec(recent=-10), qrec(state="PARTIAL", reason="ANCHOR", x=None, leg=None, ext=None), prot=False, hl=None)
    case("S08 trend, protected level, retrace unavailable (LEG): 结构待完善 / 波段长度无效", "BUILD", ["LEG"],
         base_s, qrec(state="PARTIAL", reason="LEG", x=None, leg=0), hl=None)
    case("S09 r > 2/3 (3x = 2L + 1): 深度回撤 even on a new extreme", "DEEP", ["DEEP"],
         base_s, qrec(leg=300, x=201, ext=2000), hl=(1990, 2000))
    case("S10 r = 2/3 exactly is not deep; a new high 200 above the close is not near: 正常回撤 (Q_retrace 40: no RET)",
         "PULLBACK", ["MOVE", "BRK"], base_s, qrec(leg=300, x=200, ext=2000), hl=(1990, 2000))
    case("S11 new extreme, close 25 below it (56 x 25 = 1400 = T): 延续推进", "PUSH", ["MOVE", "RET"],
         base_s, qrec(leg=300, x=25, ext=2000), hl=(1999, 2000))
    case("S12 new extreme, close 26 below (56 x 26 > T): 正常回撤 - a wick high is not a push", "PULLBACK", ["MOVE", "RET"],
         base_s, qrec(leg=300, x=26, ext=2000), hl=(1999, 2000))
    case("S13 high equal to the earlier extreme is no refresh: near -> 高位整理", "CONSOL", ["MOVE", "RET"],
         base_s, qrec(leg=300, x=10, ext=2000), hl=(2000, 2000))
    case("S14 first bar after the anchor: no earlier extreme, no refresh -> 高位整理", "CONSOL", ["MOVE", "RET"],
         base_s, qrec(leg=300, x=10, ext=2000), hl=(None, 2000))
    case("S15 below the extreme, not near: 正常回撤", "PULLBACK", ["MOVE", "RET"], base_s, qrec(leg=300, x=60, ext=2000),
         hl=(2000, 1980))
    # ---- reasons (§8) ----------------------------------------------------------------------------------------------
    case("R01 risks in order, at most two: 回撤偏深 + 近期突破失败 (逆向 / 往返 dropped)", "DEEP", ["DEEP", "BRK_FAIL"],
         srec(recent=-50, path=2000), qrec(leg=300, x=250, n=3, s=2, fail=1))
    case("R02 a failed mature event: 近期突破失败 even with n < 3 (FEW)", "PULLBACK", ["BRK_FAIL"],
         base_s, qrec(state="PARTIAL", reason="FEW", n=2, s=1, fail=1, x=60), hl=(2000, 1980))
    case("R03 S_mom = 0 with recent = 0 is not 逆向; recent = -1 is", "PULLBACK", ["COUNTER"],
         srec(recent=-1), qrec(x=60), hl=(2000, 1980))
    case("R04 recent = 0: S_mom 0 but no counter-move -> no risk; strengths shown", "PULLBACK", ["MOVE", "RET"],
         srec(recent=0), qrec(x=60), hl=(2000, 1980))
    case("R05 S_eff exactly 35 (100 e = 35 path) is not 往返; 34.9 is", "PULLBACK", ["MOVE", "RET"],
         srec(net=140, path=400, T=600), qrec(x=60), hl=(2000, 1980))
    case("R06 S_eff 34.75 (e 139 / path 400): 价格往返明显", "PULLBACK", ["CHOP"],
         srec(net=139, path=400, T=600), qrec(x=60), hl=(2000, 1980))
    case("R07 path 0: S_eff 0 is not called 往返 (no movement at all)", "PULLBACK", ["RET", "BRK"],
         srec(net=0, recent=0, path=0, T=600), qrec(x=60, so=7_000_000), hl=(2000, 1980))
    case("R08 S_move exactly 65 (100 m = 195 T): 同向推进明显", "PULLBACK", ["MOVE", "RET"],
         srec(net=195, recent=0, path=400, T=1400), qrec(x=60), hl=(2000, 1980))
    case("R09 S_move just under 65: no MOVE; next strengths in order", "PULLBACK", ["RET", "BRK"],
         srec(net=194, recent=0, path=400, T=1400), qrec(x=60), hl=(2000, 1980))
    case("R10 Q_retrace exactly 70 (r = 1/2): 回撤较浅", "PULLBACK", ["RET", "BRK"],
         srec(net=0, recent=0, path=0), qrec(leg=300, x=150), hl=(2000, 1850))
    case("R11 Q_retrace 69.4 (x 151): no RET", "PULLBACK", ["BRK"],
         srec(net=0, recent=0, path=0), qrec(leg=300, x=151), hl=(2000, 1850))
    case("R12 3 of 4 held (Q_break 75): the failure is a risk, so no strength is listed", "PULLBACK", ["BRK_FAIL"],
         srec(net=0, recent=0, path=0), qrec(leg=300, x=151, n=4, s=3, fail=1), hl=(2000, 1850))
    case("R13 n = 3, all held: 突破全部守住; n = 2 all held (FEW) is not listed (R14)", "PULLBACK", ["BRK"],
         srec(net=0, recent=0, path=0), qrec(leg=300, x=151, n=3, s=3), hl=(2000, 1850))
    case("R14 S_eff, S_mom and Q_overlap at their boundaries (65 / 65 / 70)", "PULLBACK", ["EFF", "MOM"],
         srec(net=65, recent=65, path=100, T=1400), qrec(leg=300, x=151, n=2, s=2, state="PARTIAL", reason="FEW",
                                                         so=3_300_000), hl=(2000, 1850))
    case("R15 only Q_overlap high: K 线重叠少", "PULLBACK", ["OVL"],
         srec(net=0, recent=0, path=0, T=1400), qrec(leg=300, x=151, n=2, s=2, state="PARTIAL", reason="FEW",
                                                       so=3_300_000), hl=(2000, 1850))
    case("R16 Q_overlap 69.99: nothing high -> 无突出分项 (empty list)", "PULLBACK", [],
         srec(net=0, recent=0, path=0, T=1400), qrec(leg=300, x=151, n=2, s=2, state="PARTIAL", reason="FEW",
                                                       so=3_300_001), hl=(2000, 1850))
    case("R17 a state reason blocks the strengths: BUILD with nothing else", "BUILD", ["NO_PROT"],
         base_s, qrec(state="PARTIAL", reason="ANCHOR", x=None, leg=None, ext=None), prot=False, hl=None)
    # ---- arrow (§5.4) ----------------------------------------------------------------------------------------------
    for nm, ref, want in (("A01 +5: ↑", (55, True), "UP"), ("A02 +4: →", (56, True), "FLAT"),
                          ("A03 -5: ↓", (65, True), "DOWN"), ("A04 -4: →", (64, True), "FLAT"),
                          ("A05 another leg 3 bars ago: 新趋势", (20, False), "NEW"),
                          ("A06 no OK score 3 bars ago: 新趋势", None, "NEW")):
        case(nm, "PULLBACK", ["MOVE", "RET"], srec(score=60), qrec(x=60), hl=(2000, 1980), ref=ref, want_arrow=want)

    # ---- the panel (§2) --------------------------------------------------------------------------------------------
    t1 = "2026.10.28 16:00"
    s_ok = dict(srec(score=76, tier="STRONG"))
    q_ok = qrec(score=82, tier="GOOD", sample="FIVE", n=5, s=5, x=20)
    r = stage_rec(BULL_CTX, 0, "-", True, s_ok, q_ok, (1999, 2000), (71, True))
    rows = panel_rows(r, s_ok, q_ok, BULL_CTX, t1)
    want = [("H4 趋势", "▲ 多头", "BULL"), ("趋势强度", "强 · 76/100 ↑", "BASE"), ("趋势质量", "良好 · 82/100（5 次事件）", "BASE"),
            ("当前阶段", "延续推进", "BASE"), ("主要原因", "同向推进明显，回撤较浅", "BASE"),
            ("数据截至", "2026.10.28 16:00 H4 收盘（服务器时间）", "BASE")]
    check("P01 the requirement's normal example (§2): six rows", rows == want, f"{rows}")
    rb = stage_rec(BEAR_CTX, 0, "-", True, s_ok, flip(q_ok), (Q.MP - 1999, Q.MP - 1990), (71, True))
    rows = panel_rows(rb, s_ok, flip(q_ok), BEAR_CTX, t1)
    check("P02 bear mirror: ▼ 空头 red, 低位整理", rows[0] == ("H4 趋势", "▼ 空头", "BEAR") and rows[3][1] == "低位整理",
          f"{rows}")
    sn = srec(state="NODIR")
    qn = qrec(state="NODIR", x=None)
    rt = stage_rec(TRANS, -1, "BREAK", None, sn, qn, None, None)
    rows = panel_rows(rt, sn, qn, TRANS, t1)
    want = [("H4 趋势", "过渡 · 偏空待确认", "TRANS"), ("趋势强度", "暂不评级", "BASE"), ("趋势质量", "暂不评级", "BASE"),
            ("当前阶段", "反转待确认", "BASE"), ("主要原因", "多头保护低点已破", "BASE"),
            ("数据截至", "2026.10.28 16:00 H4 收盘（服务器时间）", "BASE")]
    check("P03 the requirement's transition example (§2)", rows == want, f"{rows}")
    rr = stage_rec(RANGE, 0, "TIMEOUT", None, sn, qn, None, None)
    rows = panel_rows(rr, sn, qn, RANGE, t1)
    check("P04 RANGE: 区间震荡 grey, 暂不评级 both, the timeout as reason",
          rows[0] == ("H4 趋势", "区间震荡", "RANGE") and rows[1][1] == rows[2][1] == "暂不评级" and
          rows[4][1] == f"过渡超 {TRANS_MAX} 根未确认", f"{rows}")
    rows = panel_rows(r, s_ok, q_ok, BULL_CTX, t1, wait=True)
    check("P05 waiting: no current value, the last valid result named as such with its time",
          [v for _, v, _ in rows] == ["等待数据", "等待数据（上次有效结果 强 · 76/100）", "等待数据（上次有效结果 良好 · 82/100）",
                                      "等待数据", "—", f"上次有效结果 {t1} H4 收盘（服务器时间）"], f"{rows}")
    rows = panel_rows(None, None, None, RANGE, t1, ready=False)
    check("P06 before the first build: 等待数据 everywhere, no time",
          [v for _, v, _ in rows] == ["等待数据"] * 4 + ["—", "等待数据"], f"{rows}")
    qp = qrec(state="PARTIAL", reason="FEW", n=2, s=1, fail=1, pend=1, x=0, leg=300, so=5_561_920)
    rp = stage_rec(BEAR_CTX, 0, "-", True, s_ok, flip(qp), (Q.MP - 1999, Q.MP - 2000), None)
    rows = panel_rows(rp, s_ok, flip(qp), BEAR_CTX, t1)
    check("P07 partial quality as in v2.57 (局部表现), 新趋势 arrow",
          rows[2][1] == "样本不足（成熟突破 2/3，待确认 1）  局部表现 回撤 100 · 重叠 49" and rows[1][1].endswith("新趋势"),
          f"{rows}")
    sx = srec(state="NODATA", reason="HISTORY", T=None)
    rx = stage_rec(RANGE, 0, "INIT", None, sx, qrec(state="NODATA", x=None), None, None)
    rows = panel_rows(rx, sx, qrec(state="NODATA", x=None), RANGE, t1)
    check("P08 history too short: 样本不足 on strength, quality and stage; reason —",
          [v for _, v, _ in rows][1:5] == ["样本不足（H4 不足 15 根）", "样本不足（H4 不足 12 根）", "样本不足", "—"], f"{rows}")
    # every value with its label fits one OBJ_LABEL, and the longest reason pair as well
    longest = max(["，".join(reason_zh(c, dict(pend=p_)) for c in (a, b)) for a in REASONS for b in REASONS
                   for p_ in (1, -1)], key=len)
    sets = ((r, s_ok, q_ok, BULL_CTX), (rb, s_ok, flip(q_ok), BEAR_CTX), (rt, sn, qn, TRANS), (rr, sn, qn, RANGE),
            (rp, s_ok, flip(qp), BEAR_CTX), (rx, sx, qrec(state="NODATA", x=None), RANGE))
    allrows = [f"{lab}  {v}" for rr_, ss_, qq_, cc_ in sets for w_ in (False, True)
               for lab, v, _ in panel_rows(rr_, ss_, qq_, cc_, t1, wait=w_)] + [f"主要原因  {longest}"]
    worst = max(allrows, key=len)
    check(f"P09 every trend panel row fits an OBJ_LABEL ({LABEL_MAX}; longest {len(worst)}: {worst})",
          len(worst) <= LABEL_MAX)
    # ---- the diagnostic panel's long rows ----------------------------------------------------------------------
    cyc = ("CYCLE #1582 BEAR    CISD OK  MSS OK  BPR OK  PA ENGULFING OK  PA REJECTION OK  PA BREAK-RETEST OK"
           "   [ANCHOR INVALIDATED]   [CTX CHANGED]")
    poi = "H4 POI: 0 ACTIVE / 13 REJECTED-BY-GAP   |   M5 BLOCK GAP-REJECTED: 125"
    ok = True
    for t in (cyc, poi, "TRANSITION (pending UP)   BOS 0 CLEAN   |   POI 0   |   no session   |   LIQ WAITING"):
        w = wrap(t)
        joined = " ".join(x.strip() for x in w)
        ok = ok and all(len(x) <= LABEL_MAX for x in w) and [x for x in joined.split() if x != "|"] == \
            [x for x in t.split() if x != "|"] and all(len(x) >= LABEL_MAX // 2 for x in w[:-1])
        print("        " + " / ".join(w))
    check("P10 wrap: every piece within 63 characters and at least half of it, nothing but a | lost, split between words", ok)


def replay(path_csv):
    bars = B.load_h1(path_csv)
    print(f"replay {path_csv}: {len(bars)} H4 bars {tstr(bars[0][0])} .. {tstr(bars[-1][0])}")
    recs, strs, qrecs, ctxs, e = run(bars)
    keys = ("stage", "reasons", "arrow", "refresh", "near", "dist", "chk", "prot", "ref_score", "pend")
    bad = 0
    for h in range(40, len(bars), 37):
        rr = run(bars[:h + 1])[0][-1]
        if any(rr[k] != recs[h][k] for k in keys):
            bad += 1
    check("R1 prefix: the stage record of h from bars[:h+1] equals the full run (every 37th bar from 40)", bad == 0,
          f"{bad} differ")
    mrecs = run(Q.mirror(bars))[0]
    sym = ("stage", "reasons", "arrow", "refresh", "near", "dist", "chk", "prot", "ref_score")
    dif = [h for h, (a, b) in enumerate(zip(recs, mrecs)) if any(a[k] != b[k] for k in sym) or a["dir"] != -b["dir"]
           or a["pend"] != -b["pend"]]
    check(f"R2 mirror: mirrored bars give the same stage, reasons and arrow on every bar ({len(dif)} differ)", not dif,
          f"bars {dif[:5]}")
    t1 = "2026.01.01 00:00"
    longest = max((f"{lab}  {v}" for h in range(len(bars)) for lab, v, _ in
                   panel_rows(recs[h], strs[h], qrecs[h], ctxs[h], t1)), key=len)
    check(f"R3 every panel row of the replay fits an OBJ_LABEL (longest {len(longest)}: {longest})", len(longest) <= LABEL_MAX)
    trend = [r for r in recs if r["dir"] != 0]
    seen = {r["stage"] for r in recs}
    print("\nrecord only - nothing below changes the definition")
    c = Counter(r["stage"] for r in recs)
    print("stages: " + "  ".join(f"{k} {c[k]}" for k in STAGES))
    print(f"trend bars {len(trend)}: " + "  ".join(f"{k} {c[k]} ({100.0 * c[k] / len(trend):.1f}%)"
                                                  for k in ("BUILD", "DEEP", "PUSH", "CONSOL", "PULLBACK")))
    rc = Counter(x for r in recs for x in r["reasons"])
    print("reasons: " + "  ".join(f"{k} {rc[k]}" for k in REASONS))
    n0 = sum(1 for r in trend if not r["reasons"])
    print(f"trend bars with no reason (无突出分项): {n0}")
    ac = Counter(r["arrow"] for r in recs)
    print("arrows: " + "  ".join(f"{k} {ac[k]}" for k in ARROWS))
    check(f"R4 every stage but NOATR occurs on real data ({len(seen)} of {len(STAGES)})",
          seen >= set(STAGES) - {"NOATR"}, f"missing {set(STAGES) - seen}")
    return all(RESULTS)


def main():
    if len(sys.argv) > 2 and sys.argv[1] == "--replay":
        ok = replay(sys.argv[2])
    else:
        cases()
        ok = all(RESULTS)
    print(f"\n{sum(RESULTS)}/{len(RESULTS)} {'PASS' if ok else 'FAIL'}")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
