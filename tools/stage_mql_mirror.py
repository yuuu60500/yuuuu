r"""v2.58: HMI_StageEngine.mqh transliterated line by line into Python (StgOnH4Bar, StgLog, StgPanelRows,
StgStrItemsText, StgQltItemsText, StgWrap / StgRFind; v2.58r4 StgCompactRows, StgM5Row with HMI_ObjectManager's
OM_M5StatusRow counting, StgADRRow), fed the way H4ProcessBar feeds the MQL - the strength and quality
records of the bar (tools/strength_sim.py and tools/quality_sim.py, whose own mirrors checked them against the MQL),
g_ctx / g_ctx_pending / g_ctx_time / g_prot / g_leg_seq from the v2.54 structure model - and compared with
tools/stage_sim.py: every HMI-STG row character for character, every panel string, every wrapped diagnostic row.

It checks the MQL's logic and wording before a compile can - the CHOCH kind carried from the previous bar, the arrow's
leg test, the extreme before the bar, the integer thresholds, the row format, the \uXXXX words, the wrap. It is a hand
transliteration: it cannot see MQL syntax, types or compiler behaviour, and a pass does not replace compiling and
running the indicator.

    python3 tools/stage_mql_mirror.py [<H1 csv>]      scenario series (+ the csv: every bar, and its mirror)
"""
import os
import itertools
import random
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import stage_sim as G                                            # noqa: E402
import quality_sim as Q                                          # noqa: E402
import strength_sim as S                                         # noqa: E402
import h4_protect_sim as P                                       # noqa: E402
import h4_dedup_sim as B                                         # noqa: E402
from h4_dedup_sim import BULL_CTX, BEAR_CTX, TRANS, RANGE, H4, tstr  # noqa: E402

_HERE = os.path.dirname(os.path.abspath(__file__))
MQH = next((d for d in (os.path.join(_HERE, "..", "MQL5", "Indicators", "HMI"), os.path.join(_HERE, "..", "Indicators", "HMI"))
            if os.path.isfile(os.path.join(d, "HMI_StageEngine.mqh"))), None)   # the repository, or a delivery package
if MQH is None:
    sys.exit("HMI_StageEngine.mqh not found next to tools/ (../MQL5/Indicators/HMI or ../Indicators/HMI)")

PT = B.POINT
def StrL(a, b): return int(round((a - b) / PT))
FP = 1000000
SG = ["NODATA", "NOATR", "TRANS", "RANGE", "BUILD", "DEEP", "PUSH", "CONSOL", "PULLBACK"]
RS = ["PROT_BROKEN", "SWING_BROKEN", "TIMEOUT", "NO_PROT", "LEG", "DEEP", "BRK_FAIL", "COUNTER", "CHOP", "MOVE", "RET",
      "BRK", "EFF", "MOM", "OVL"]
AR = ["NA", "UP", "DOWN", "FLAT", "NEW"]
CK = ["-", "BREAK", "FALLBACK", "TIMEOUT", "INIT"]
CK_BREAK, CK_FALLBACK, CK_TIMEOUT, CK_INIT = 1, 2, 3, 4


# ---- the inputs, as the MQL globals stand after StrOnH4Bar / QltOnH4Bar of bar h -----------------------------------
def feed(bars):
    """-> per bar: (ctx, pend, ctx_time, prot_valid, leg_seq, StrRec dict, QltRec dict)"""
    e = P.Engine254(True, None)
    t = Q.Tracker(Q.LEG_START, Q.EV_WIN)
    tidx = {b[0]: k for k, b in enumerate(bars)}
    out = []
    for h in range(len(bars)):
        n0 = len(e.ctx_rows)
        e.process(bars, h)
        q = t.on_bar(bars, h, e, e.ctx_rows[n0:], tidx)
        s = S.score(bars, h, e.ctx)
        sr = dict(state={"OK": 0, "NODIR": 1, "NODATA": 2}[s["state"]], reason={"-": 0, "HISTORY": 1, "ATR": 2}[s["reason"]],
                  trsum=s["T"] or 0, net=s["net"] or 0, recent=s["recent"] or 0, path=s["path"] or 0,
                  score=(s["score"] if s["state"] == "OK" else -1), tier=s["tier"], leg=e.leg)
        d = 1 if e.ctx == BULL_CTX else -1 if e.ctx == BEAR_CTX else 0
        qr = dict(state=q["state"], has_x=q["x"] is not None, anchor_bar=(q["anchor"][0] if q["anchor"] else -1),
                  x=q["x"] or 0, leg=q["leg"] or 0, num_r=q["num_r"] or 0, fail=q["fail"], n=q["n"], s=q["s"], so=q["so"] or 0,
                  rec=q)
        if d != 0 and qr["has_x"]:                       # ext_px as QltOnH4Bar keeps it: a price, max H / min L of a+1 .. h
            a = qr["anchor_bar"]
            ext = bars[a + 1][2] if d == 1 else bars[a + 1][3]
            for i in range(a + 2, h + 1):
                ext = max(ext, bars[i][2]) if d == 1 else min(ext, bars[i][3])
            qr["ext_px"] = ext
        out.append((e.ctx, e.pending if e.ctx == TRANS else e.pending, e.ctx_time, e.prot is not None, e.leg, sr, qr, s))
    return out


# ---- StgOnH4Bar + StgLog ---------------------------------------------------------------------------------------------
def mirror_rows(bars):
    fd = feed(bars)
    g_str = [x[5] for x in fd]
    trans_kind = 0
    prot_prev = False
    rows, recs = [], []
    for h, (ctx, pending, ctx_time, prot_valid, leg_seq, s, q, _) in enumerate(fd):
        t = bars[h][0] + H4
        if ctx == TRANS and ctx_time == t:
            trans_kind = CK_BREAK if prot_prev else CK_FALLBACK
        r = dict(stage=0, rs=[], dir=0, pend=0, chk=0, prot=-1, has_x=False, has_prev=False, prev_px=0.0, bar_px=0.0,
                 dist=0, refresh=-1, near=-1, arrow=0, ref_score=-1)
        d = 1 if ctx == BULL_CTX else -1 if ctx == BEAR_CTX else 0
        r["dir"] = d
        r["pend"] = pending if ctx == TRANS else 0
        r["chk"] = trans_kind if ctx == TRANS else ((CK_TIMEOUT if ctx_time != 0 else CK_INIT) if ctx == RANGE else 0)
        if d != 0:
            r["prot"] = 1 if prot_valid else 0
        if s["state"] == 0:
            ref_ok = h >= 3 and g_str[h - 3]["state"] == 0
            if ref_ok:
                r["ref_score"] = g_str[h - 3]["score"]
            if not ref_ok or g_str[h - 3]["leg"] != s["leg"]:
                r["arrow"] = 4
            else:
                dl = s["score"] - r["ref_score"]
                r["arrow"] = 1 if dl >= 5 else 2 if dl <= -5 else 3
        if d != 0 and q["has_x"]:
            a = q["anchor_bar"]
            r["has_x"] = True
            r["bar_px"] = bars[h][2] if d == 1 else bars[h][3]
            r["has_prev"] = a + 1 <= h - 1
            if r["has_prev"]:
                e = bars[a + 1][2] if d == 1 else bars[a + 1][3]
                for i in range(a + 2, h):
                    e = max(e, bars[i][2]) if d == 1 else min(e, bars[i][3])
                r["prev_px"] = e
            r["dist"] = d * StrL(q["ext_px"], bars[h][4])
            r["refresh"] = 1 if (r["has_prev"] and d * StrL(r["bar_px"], r["prev_px"]) > 0) else 0
            if s["trsum"] > 0:
                r["near"] = 1 if 56 * r["dist"] <= s["trsum"] else 0
        add = lambda c: r["rs"].append(c) if len(r["rs"]) < 2 else None      # noqa: E731
        if s["state"] == 2:
            r["stage"] = 0 if s["reason"] == 1 else 1
        elif ctx == TRANS:
            r["stage"] = 2
            if r["chk"] == CK_BREAK: add(0)
            if r["chk"] == CK_FALLBACK: add(1)
        elif ctx == RANGE:
            r["stage"] = 3
            if r["chk"] == CK_TIMEOUT: add(2)
        else:
            if r["prot"] != 1: r["stage"] = 4; add(3)
            elif not q["has_x"]: r["stage"] = 4; add(4)
            elif 3 * q["x"] > 2 * q["leg"]: r["stage"] = 5
            elif r["refresh"] == 1 and r["near"] == 1: r["stage"] = 6
            elif r["near"] == 1: r["stage"] = 7
            else: r["stage"] = 8
            m = min(max(14 * s["net"], 0), 3 * s["trsum"])
            e = min(max(s["net"], 0), s["path"])
            qm = min(max(14 * s["recent"], 0), 1 * s["trsum"])
            before = len(r["rs"]); risk = False
            if q["has_x"] and 3 * q["x"] > 2 * q["leg"]: add(5); risk = True
            if q["fail"] > 0: add(6); risk = True
            if qm == 0 and s["recent"] < 0: add(7); risk = True
            if s["path"] > 0 and 100 * e < 35 * s["path"]: add(8); risk = True
            if before == 0 and not risk:
                if 100 * m >= 65 * 3 * s["trsum"]: add(9)
                if q["has_x"] and q["num_r"] >= 70 * q["leg"]: add(10)
                if q["n"] >= 3 and q["s"] == q["n"]: add(11)
                if s["path"] > 0 and 100 * e >= 65 * s["path"]: add(12)
                if 100 * qm >= 65 * 1 * s["trsum"]: add(13)
                if 100 * (11 * FP - q["so"]) >= 70 * 11 * FP: add(14)
        prot_prev = prot_valid
        recs.append(r)
        # --- StgLog
        px = lambda v: f"{v:.5f}"                                           # noqa: E731
        flag = lambda v: "NA" if v < 0 else str(v)                          # noqa: E731
        arr = r["arrow"] != 0
        row = (f"HMI-STG,USDJPY,live=0,bar={tstr(t)},ctx={ctx},stage={SG[r['stage']]},"
               f"reasons={'+'.join(RS[c] for c in r['rs']) or '-'},def={G.DEF_ID},dir={r['dir']},"
               f"pend={'UP' if r['pend'] == 1 else 'DOWN' if r['pend'] == -1 else '-'},chk={CK[r['chk']]},prot={flag(r['prot'])},"
               f"anchor_bar={tstr(bars[q['anchor_bar']][0]) if r['has_x'] else '-'},"
               f"prev_ext={px(r['prev_px']) if r['has_x'] and r['has_prev'] else 'NA'},"
               f"bar_ext={px(r['bar_px']) if r['has_x'] else 'NA'},ext={px(q['ext_px']) if r['has_x'] else 'NA'},"
               f"close={px(bars[h][4])},dist_pts={r['dist'] if r['has_x'] else 'NA'},"
               f"tr_sum={s['trsum'] if s['reason'] != 1 else 'NA'},refresh={flag(r['refresh'])},near={flag(r['near'])},"
               f"arrow={AR[r['arrow']]},ref_bar={tstr(bars[h - 3][0] + H4) if arr and h >= 3 else '-'},"
               f"ref_score={flag(r['ref_score'])},score={s['score'] if s['state'] == 0 else 'NA'},inst=0001,run=7,init=1")
        rows.append(row)
    return rows, recs, fd


# ---- StgPanelRows / items / wrap, with the \\uXXXX macros read from the .mqh files and decoded as HMI_U does ---------
ZH = {}
for f in ("HMI_StrengthEngine.mqh", "HMI_QualityEngine.mqh", "HMI_StageEngine.mqh"):
    for m in re.finditer(r'#define (ZH_\w+)\s+"([^"]*)"', open(os.path.join(MQH, f), encoding="utf-8").read()):
        ZH[m.group(1)] = re.sub(r'\\\\u([0-9A-Fa-f]{4})', lambda x: chr(int(x.group(1), 16)), m.group(2))
U = lambda k: ZH[k]                                                          # noqa: E731
def rnd(num, den): return (2 * num + den) // (2 * den)
STZ = {"WEAK": "ZH_WEAK", "MED": "ZH_MED", "STRONG": "ZH_STRONG"}
QTZ = {"POOR": "ZH_POOR", "FAIR": "ZH_FAIR", "GOOD": "ZH_GOOD"}
TRANS_MAX = 18


def qlocal(q, sep):                                     # QltLocal (v2.57, mirror-checked)
    out = ""
    if q["n"] >= 3: out += U("ZH_BRK") + " " + str(rnd(100 * q["s"], q["n"]))
    if q["q_retrace"] is not None: out += ("" if out == "" else sep) + U("ZH_RET") + " " + str(rnd(q["num_r"], q["leg"]))
    out += ("" if out == "" else sep) + U("ZH_OVL") + " " + str(rnd(100 * (11 * FP - q["so"]), 11 * FP))
    return out


def qwhy(q):                                            # QltWhy (v2.57, mirror-checked)
    rs = q["reason"].split("+"); out = ""
    if "FEW" in rs:
        out = U("ZH_MATURE") + " " + str(q["n"]) + "/3"
        if q["pend"] > 0: out += U("ZH_COMMA") + U("ZH_PENDING") + " " + str(q["pend"])
    if "ANCHOR" in rs: out += ("" if out == "" else U("ZH_SEMI")) + U("ZH_NOANCHOR")
    if "LEG" in rs or "SCALE" in rs: out += ("" if out == "" else U("ZH_SEMI")) + U("ZH_LEGBAD")
    return out


def stage_zh(r):
    k = r["stage"]
    if k == 0: return U("ZH_FEW")
    if k == 1: return U("ZH_NA")
    if k == 2: return U("ZH_TRANS")
    if k == 3: return U("ZH_RANGE")
    if k == 4: return U("ZH_SG_BUILD")
    if k == 5: return U("ZH_SG_DEEP")
    if k == 6: return U("ZH_SG_PUSH")
    if k == 7: return U("ZH_SG_HIGH" if r["dir"] == 1 else "ZH_SG_LOW")
    return U("ZH_SG_PULL")


def reason_zh(c, r):
    if c == 0: return U("ZH_R_BULLPROT" if r["pend"] == -1 else "ZH_R_BEARPROT")
    if c == 1: return U("ZH_R_BULLSW" if r["pend"] == -1 else "ZH_R_BEARSW") + U("ZH_R_NOPROT_SFX")
    if c == 2: return U("ZH_R_TIMEOUT_A") + " " + str(TRANS_MAX) + " " + U("ZH_R_TIMEOUT_B")
    return U(["", "", "", "ZH_R_NOPROT", "ZH_LEGBAD", "ZH_R_DEEP", "ZH_R_BRKFAIL", "ZH_R_COUNTER", "ZH_R_CHOP", "ZH_R_MOVE",
              "ZH_R_RET", "ZH_R_BRK", "ZH_R_EFF", "ZH_R_MOM", "ZH_R_OVL"][c])


def strength_value(s, sm, arrow, wait):
    if wait:
        if s["state"] != 0: return U("ZH_WAIT")
        return (U("ZH_WAIT") + U("ZH_LP") + U("ZH_LASTOK") + " " + U(STZ[s["tier"]]) + " " + U("ZH_DOT") + " " +
                str(s["score"]) + "/100" + U("ZH_RP"))
    if s["state"] == 2:
        return (U("ZH_FEW") + U("ZH_LP") + U("ZH_FEW15") + U("ZH_RP") if s["reason"] == 1
                else U("ZH_NA") + U("ZH_LP") + U("ZH_ATRBAD") + U("ZH_RP"))
    if s["state"] == 1: return U("ZH_NORATE")
    a = {1: "ZH_ARR_UP", 2: "ZH_ARR_DN", 3: "ZH_ARR_FLAT"}.get(arrow, "ZH_ARR_NEW")
    return U(STZ[s["tier"]]) + " " + U("ZH_DOT") + " " + str(s["score"]) + "/100 " + U(a)


def quality_value(q, wait):
    if wait:
        if q["state"] != "OK": return U("ZH_WAIT")
        return (U("ZH_WAIT") + U("ZH_LP") + U("ZH_LASTOK") + " " + U(QTZ[q["tier"]]) + " " + U("ZH_DOT") + " " +
                str(q["score"]) + "/100" + U("ZH_RP"))
    if q["state"] == "NODATA": return U("ZH_FEW") + U("ZH_LP") + U("ZH_FEW12") + U("ZH_RP")
    if q["state"] == "NODIR": return U("ZH_NORATE")
    if q["state"] == "PARTIAL":
        return (U("ZH_FEW" if "FEW" in q["reason"].split("+") else "ZH_NA") + U("ZH_LP") + qwhy(q) + U("ZH_RP") + "  " +
                U("ZH_LOCAL") + " " + qlocal(q, " " + U("ZH_DOT") + " "))
    return (U(QTZ[q["tier"]]) + " " + U("ZH_DOT") + " " + str(q["score"]) + "/100" + U("ZH_LP") +
            ("5 " + U("ZH_TIMES_EV") if q["sample"] == "FIVE" else U("ZH_LOWSMP") + " " + str(q["n"]) + " " + U("ZH_TIMES_BRK")) +
            U("ZH_RP"))


def why_text(r):                                        # StgWhyText
    why = ""
    for i, c in enumerate(r["rs"]): why += ("" if i == 0 else U("ZH_COMMA")) + reason_zh(c, r)
    if why == "": why = U("ZH_R_NONE" if r["dir"] != 0 else "ZH_DASH")
    return why


def panel_rows(r, s, q, ctx, wait, ready=True):         # StgPanelRows (v2.58r4: STG_FULL_ROWS = 5)
    lab = [U("ZH_LAB_DIR"), U("ZH_STRENGTH"), U("ZH_QUALITY"), U("ZH_LAB_STAGE"), U("ZH_LAB_WHY")]
    ck = ["BASE"] * 5
    if not ready:
        return list(zip(lab, [U("ZH_WAIT")] * 4 + [U("ZH_DASH")], ck))
    if wait:
        val = [U("ZH_WAIT"), strength_value(s, None, r["arrow"], True), quality_value(q, True), U("ZH_WAIT"), U("ZH_DASH")]
        return list(zip(lab, val, ck))
    if ctx == BULL_CTX: v0 = U("ZH_UP_TRI") + " " + U("ZH_BULL"); ck[0] = "BULL"
    elif ctx == BEAR_CTX: v0 = U("ZH_DN_TRI") + " " + U("ZH_BEAR"); ck[0] = "BEAR"
    elif ctx == TRANS:
        v0 = U("ZH_TRANS_HEAD") + " " + U("ZH_DOT") + " " + U("ZH_PEND_UP" if r["pend"] == 1 else "ZH_PEND_DN"); ck[0] = "TRANS"
    else: v0 = U("ZH_RANGE"); ck[0] = "RANGE"
    val = [v0, strength_value(s, None, r["arrow"], False), quality_value(q, False), stage_zh(r), why_text(r)]
    if s["state"] == 0: ck[1] = {"STRONG": "HIGH", "MED": "MID", "WEAK": "LOW"}[s["tier"]]
    if q["state"] == "OK": ck[2] = {"GOOD": "HIGH", "FAIR": "MID", "POOR": "LOW"}[q["tier"]]
    return list(zip(lab, val, ck))


# ---- v2.58r4 PANEL_COMPACT: StgStrengthShort / StgQualityShort / StgCompactRows / StgM5Row / StgADRRow --------------
def strength_short(s, arrow):
    c = "BASE"
    if s["state"] == 2: return U("ZH_FEW" if s["reason"] == 1 else "ZH_NA"), c
    if s["state"] == 1: return U("ZH_NORATE"), c
    c = "HIGH" if s["tier"] == "STRONG" else ("MID" if s["tier"] == "MED" else "LOW")
    a = (U("ZH_ARR_UP") if arrow == 1 else (U("ZH_ARR_DN") if arrow == 2 else (U("ZH_ARR_FLAT") if arrow == 3 else " " + U("ZH_ARR_NEW"))))
    return U(STZ[s["tier"]]) + str(s["score"]) + "/100" + a, c


def quality_short(q):
    c = "BASE"
    if q["state"] == "NODATA": return U("ZH_FEW"), c
    if q["state"] == "NODIR": return U("ZH_NORATE"), c
    if q["state"] == "PARTIAL":
        return (U("ZH_FEW") + " " + str(q["n"]) + "/" + "3" if "FEW" in q["reason"].split("+") else U("ZH_NA")), c
    c = "HIGH" if q["tier"] == "GOOD" else ("MID" if q["tier"] == "FAIR" else "LOW")
    return U(QTZ[q["tier"]]) + str(q["score"]) + "/100" + (" " + U("ZH_LOWSMP") if q["sample"] == "LOW" else ""), c


def compact_rows(r, s, q, ctx, wait, ready=True):
    seg = []                                            # (row, text, colour) as StgSeg appends them
    add = lambda row, t, c: seg.append((row, t, c))     # noqa: E731
    if not ready or wait:
        add(0, "H4 ", "LAB"); add(0, U("ZH_WAIT"), "BASE")
        add(1, U("ZH_STR_SHORT") + " ", "LAB"); add(1, U("ZH_WAIT"), "BASE"); add(1, U("ZH_BAR"), "LAB")
        add(1, U("ZH_QLT_SHORT") + " ", "LAB"); add(1, U("ZH_WAIT"), "BASE")
        add(2, U("ZH_WHY_SHORT") + " ", "LAB"); add(2, U("ZH_DASH"), "BASE")
    else:
        add(0, "H4 ", "LAB")
        if ctx == BULL_CTX: add(0, U("ZH_BULL"), "BULL")
        elif ctx == BEAR_CTX: add(0, U("ZH_BEAR"), "BEAR")
        elif ctx == TRANS: add(0, U("ZH_TRANS_HEAD") + U("ZH_DOT") + U("ZH_LEAN_UP" if r["pend"] == 1 else "ZH_LEAN_DN"), "TRANS")
        else: add(0, U("ZH_RANGE"), "RANGE")
        if not (ctx == RANGE and r["stage"] == 3):
            add(0, U("ZH_BAR"), "LAB"); add(0, stage_zh(r), "BASE")
        add(1, U("ZH_STR_SHORT") + " ", "LAB")
        sv, c = strength_short(s, r["arrow"]); add(1, sv, c)
        add(1, U("ZH_BAR"), "LAB"); add(1, U("ZH_QLT_SHORT") + " ", "LAB")
        qv, c = quality_short(q); add(1, qv, c)
        add(2, U("ZH_WHY_SHORT") + " ", "LAB"); add(2, why_text(r), "BASE")
    rows = [[], [], []]
    for row, t, c in seg: rows[row].append((t, c))
    return rows


def m5_row(ready, cyc_on, armed, done, pend, anchor_bad, ctx_chg, sess_on, sess_t, trend):
    if not ready: return "M5 " + U("ZH_WAIT")
    if cyc_on and pend > 0:
        t = ("M5 " + U("ZH_M5_TRACK") + U("ZH_LP") + armed + " " + U("ZH_M5_FROM") + U("ZH_RP") + U("ZH_M5_DONE") + " " +
             str(done) + " " + U("ZH_M5_ITEM") + " " + U("ZH_DOT") + " " + U("ZH_PENDING") + " " + str(pend) + " " + U("ZH_M5_ITEM"))
        if anchor_bad: t += " " + U("ZH_DOT") + " " + U("ZH_M5_ANCHOR")
        if ctx_chg: t += " " + U("ZH_DOT") + " " + U("ZH_M5_CTX")
        return t
    head = "M5 " + U("ZH_M5_IDLE") + " " + U("ZH_DOT") + " "
    if sess_on: return head + U("ZH_M5_POI") + U("ZH_LP") + sess_t + U("ZH_RP") + U("ZH_COMMA") + U("ZH_M5_WAITBLK")
    return head + U("ZH_M5_WAITPOI" if trend else "ZH_M5_PAUSE")


def om_m5(ready, results, armed, anc, chg, sess_on, sess_t, trend):   # OM_M5StatusRow (cycle state -> StgM5Row)
    cyc_on = results is not None
    done = pend = 0
    if cyc_on:
        for m in results:
            if m == "CONFIRMED": done += 1
            if m == "PENDING": pend += 1
    return m5_row(ready, cyc_on, armed if cyc_on else "", done, pend, anc if cyc_on else False, chg if cyc_on else False,
                  sess_on, sess_t, trend)


def adr_row(ok, pct, left, exhausted):
    if not ok: return U("ZH_ADR_TODAY") + U("ZH_COLON") + U("ZH_WAIT")
    return (U("ZH_ADR_TODAY") + " " + pct + "% " + U("ZH_DOT") + " " + U("ZH_ADR_LEFT") + " " + left + " pip" +
            (U("ZH_LP") + U("ZH_ADR_EXH") + U("ZH_RP") if exhausted else ""))


def left_rows():
    """every combination of the inputs of the diagnostic panel's compact rows, mirror vs model"""
    n = bad = 0
    res_sets = [None] + [list(x) for x in itertools.product(("PENDING", "CONFIRMED", "NA"), repeat=6)]   # the six models
    for ready in (False, True):
        for full in res_sets:
            for anc in (False, True):
                for chg in (False, True):
                    for sess in (None, "10.28 12:40"):
                        for trend in (False, True):
                            a = om_m5(ready, full, "10.28 13:05", anc, chg, sess is not None, sess or "", trend)
                            b = G.m5_row(ready, None if full is None else dict(armed="10.28 13:05", results=full, anchor=anc, ctx=chg),
                                         sess, trend)
                            n += 1; bad += a != b
    for ok in (False, True):
        for pct, left in (("0", "85.3"), ("47", "45.2"), ("100", "0.0"), ("112", "0.0")):
            for ex in (False, True):
                n += 1; bad += adr_row(ok, pct, left, ex) != G.adr_row(ok, pct, left, ex)
    n += 1; bad += U("ZH_LIQ_WAIT") != G.LIQ_WAIT_ROW
    return n, bad


def str_items(s):
    if s["state"] != 0: return None
    m = min(max(14 * s["net"], 0), 3 * s["trsum"]); e = min(max(s["net"], 0), s["path"]); q = min(max(14 * s["recent"], 0), s["trsum"])
    eff = rnd(100 * e, s["path"]) if s["path"] > 0 else 0
    return (U("ZH_STR_ITEMS") + "  " + U("ZH_I_MOVE") + " " + str(rnd(100 * m, 3 * s["trsum"])) + " " + U("ZH_DOT") + " " +
            U("ZH_I_EFF") + " " + str(eff) + " " + U("ZH_DOT") + " " + U("ZH_I_MOM") + " " + str(rnd(100 * q, s["trsum"])))


def qlt_items(q):
    if q["state"] not in ("OK", "PARTIAL"): return None
    return U("ZH_QLT_ITEMS") + "  " + qlocal(q, " " + U("ZH_DOT") + " ")


def rfind(s, sub, lim):                                 # StgRFind
    best, ls, frm = -1, len(sub), 0
    while True:
        k = s.find(sub, frm)
        if k < 0 or k + ls > lim + 1: break
        best = k; frm = k + 1
    return best


def stg_wrap(text):                                     # StgWrap
    out, cur, ind, lim = [], text, "    ", 63
    while len(cur) > lim:
        cut, skip = -1, 0
        k = rfind(cur, "|", lim)
        if k >= lim // 2: cut, skip = k, 1
        else:
            k = rfind(cur, "  ", lim)
            if k >= lim // 2: cut, skip = k, 2
        if cut < 0:
            k = rfind(cur, " ", lim)
            if k > len(ind): cut, skip = k, 1
        if cut < 0:
            out.append(cur[:lim]); cur = ind + cur[lim:]; continue
        out.append(cur[:cut].rstrip()); cur = ind + cur[cut + skip:].lstrip()
    out.append(cur)
    return out


def compare(name, bars):
    bars = [tuple(b) for b in bars]
    mine, mrecs, fd = mirror_rows(bars)
    recs, strs, qrecs, ctxs, _ = G.run(bars)
    model = [G.stg_row(bars, h, ctxs[h], recs[h]) for h in range(len(bars))]
    bad = [(h, a, b) for h, (a, b) in enumerate(zip(mine, model)) if a != b]
    print(f"{name}: {len(bars)} bars, {len(bad)} rows differ")
    for h, a, b in bad[:3]:
        fa, fb = a.split(","), b.split(",")
        print("  bar", h, [(x, y) for x, y in zip(fa, fb) if x != y][:4])
    pn = pbad = 0
    for h in range(len(bars)):
        s, q = fd[h][5], fd[h][6]["rec"]
        for w in (False, True):
            a = panel_rows(mrecs[h], s, q, ctxs[h], w)
            b = G.panel_rows(recs[h], strs[h], qrecs[h], ctxs[h], wait=w)
            pn += 1; pbad += a != b
            a = compact_rows(mrecs[h], s, q, ctxs[h], w)                   # v2.58r4
            b = G.compact_rows(recs[h], strs[h], qrecs[h], ctxs[h], wait=w)
            pn += 1; pbad += a != b
        pn += 2
        pbad += (panel_rows(None, None, None, RANGE, False, ready=False) != G.panel_rows(None, None, None, RANGE, ready=False))
        pbad += (compact_rows(None, None, None, RANGE, False, ready=False) != G.compact_rows(None, None, None, RANGE, ready=False))
        si, qi = G.items_rows(strs[h], qrecs[h])
        pn += 2; pbad += (str_items(s) != si) + (qlt_items(q) != qi)
    print(f"{'':{len(name)}}  panel strings: {pn} compared, {pbad} differ")
    return len(bad), pn, pbad


def wraps():
    rng = random.Random(58)
    words = ["CYCLE", "#1582", "BEAR", "CISD", "OK", "MSS", "N/A", "BPR", "PA", "ENGULFING", "REJECTION", "BREAK-RETEST",
             "[ANCHOR", "INVALIDATED]", "[CTX", "CHANGED]", "H4", "POI:", "13", "REJECTED-BY-GAP", "|", "M5", "BLOCK",
             "GAP-REJECTED:", "125", "SESSION", "16:40", "LIQ", "WAITING", "TRANSITION", "(pending", "UP)", "level(s)",
             "SUPERCALIFRAGILISTICEXPIALIDOCIOUS-AND-THEN-SOME-MORE-WORDS-JOINED-TOGETHER-TO-PASS-63-CHARS"]
    seps = [" ", "  ", "   ", "   |   ", "  |  "]
    n = bad = 0
    for _ in range(4000):
        k = rng.randint(1, 30)
        t = words[rng.randrange(len(words))]
        for _ in range(k):
            t += seps[rng.randrange(len(seps))] + words[rng.randrange(len(words))]
        n += 1
        bad += stg_wrap(t) != G.wrap(t)
    return n, bad


def main():
    series = []
    stair = P.path([(1.1050, 0), (1.1000, 2), (1.1100, 5), (1.1040, 3), (1.1160, 6), (1.1100, 3), (1.1230, 6), (1.1180, 3),
                    (1.1300, 6), (1.1250, 3), (1.1370, 6), (1.1330, 3), (1.1440, 6), (1.1400, 3), (1.1510, 6), (1.1470, 3),
                    (1.1580, 6), (1.1540, 3)])
    tc = lambda after: P.path([(1.1050, 0), (1.1000, 2), (1.1100, 5), (1.1040, 3), (1.1160, 6), (1.1010, 6)] + after)   # noqa: E731
    fast = [(1.1050, 0), (1.1000, 2), (1.1100, 5), (1.1070, 2), (1.1140, 1)]
    long_t = [(1.1050, 0), (1.1000, 2), (1.1100, 5), (1.1040, 3), (1.1160, 6), (1.1010, 6)] + \
             [(1.1060, 2), (1.1030, 2)] * 12
    series += [("staircase", stair), ("CHOCH then TRANS_OK", tc([(1.1060, 3), (1.1030, 3), (1.1055, 3), (1.0950, 6)])),
               ("CHOCH then TRANS_FAIL", tc([(1.1080, 3), (1.1050, 3), (1.1130, 4)])),
               ("TRANSITION timing out into RANGE", P.path(long_t)),
               ("INVALID anchor", P.path(fast + [(1.1150, 1), (1.1160, 1), (1.1220, 3), (1.1180, 3), (1.1260, 4), (1.1230, 3),
                                                  (1.1300, 4), (1.1270, 3), (1.1340, 4)])),
               ("failing breaks", Q.cbars([0, -100, -200, -300, -200, -100, 0, 100, 200, 300, 250, 200, 150, 200, 300, 340, 320,
                                           400, 480, 470, 460, 515, 505, 600, 680, 670, 660, 715, 705, 800, 880, 870, 860, 915,
                                           905, 905, 905, 865, 925, 1025, 965], 30))]
    if len(sys.argv) > 1:
        series.append((os.path.basename(sys.argv[1]), B.load_h1(sys.argv[1])))
    rows = rbad = pn = pbad = 0
    seen = set()
    for nm, bb in series:
        for tag, b in (("", [tuple(x) for x in bb]), (" mirror", Q.mirror(bb))):
            k, n, bad = compare(nm + tag, b)
            rows += len(b); rbad += k; pn += n; pbad += bad
            seen |= {r["stage"] for r in G.run([tuple(x) for x in b])[0]}
    wn, wbad = wraps()
    ln, lbad = left_rows()
    print(f"HMI-STG rows: {rows} compared, {rbad} differ;  panel strings: {pn} compared, {pbad} differ;  "
          f"wrapped rows: {wn} random texts, {wbad} differ;  compact diagnostic rows (r4): {ln} input sets, {lbad} differ")
    print(f"stages met: {', '.join(s for s in G.STAGES if s in seen)}")
    ok = rbad == 0 and pbad == 0 and wbad == 0 and lbad == 0
    print("PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
