r"""v2.57: HMI_QualityEngine.mqh transliterated line by line into Python (QltOnH4Bar, QltLog, QltPanelText,
QltPanelShort), fed by the v2.54 structure model the way H4ProcessBar feeds the MQL (the break this bar took, g_leg_seq,
g_anchor), and compared with tools/quality_sim.py: every HMI-QLT row character for character, every panel string.

It checks the MQL's logic and wording before a compile can - the incremental tracker, the latest-five selection, the
extreme after the anchor bar, the integer composite, the row format, the \uXXXX words. It is a hand transliteration:
it cannot see MQL syntax, types or compiler behaviour, and a pass does not replace compiling and running the indicator.

    python3 tools/quality_mql_mirror.py [<H1 csv>]      scenario series (+ the csv: every bar, and its mirror)
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import quality_sim as Q                                          # noqa: E402
import h4_protect_sim as P                                       # noqa: E402
import h4_dedup_sim as B                                         # noqa: E402
from h4_dedup_sim import BULL_CTX, BEAR_CTX, H4, tstr            # noqa: E402

_HERE = os.path.dirname(os.path.abspath(__file__))
MQH = next((d for d in (os.path.join(_HERE, "..", "MQL5", "Indicators", "HMI"), os.path.join(_HERE, "..", "Indicators", "HMI"))
            if os.path.isfile(os.path.join(d, "HMI_QualityEngine.mqh"))), None)   # the repository, or a delivery package
if MQH is None:
    sys.exit("HMI_QualityEngine.mqh not found next to tools/ (../MQL5/Indicators/HMI or ../Indicators/HMI)")

# ---- QltOnH4Bar + QltLog (StrL = the MQL StrL: round((a - b) / _Point)) ------------------------------------------
PT = B.POINT
def StrL(a, b): return int(round((a - b) / PT))
FP = 1000000; LCD = 1320000

def mirror_rows(bars):
    e = P.Engine254(True, None)
    tidx = {b[0]: k for k, b in enumerate(bars)}
    qev = []; qleg = -1
    rows = []
    for h in range(len(bars)):
        n0 = len(e.ctx_rows)
        e.process(bars, h)
        new = e.ctx_rows[n0:]
        ctx = e.ctx
        d = 1 if ctx == BULL_CTX else -1 if ctx == BEAR_CTX else 0
        brk = [r for r in new if r["kind"] in ("BOS", "TRANS_OK", "TRANS_FAIL")]
        brk_h = h if brk else -1
        brk_dir = brk[0]["dir"] if brk else 0
        brk_px = brk[0]["swing_px"] if brk else 0.0
        if d == 0:
            qleg = -1; qev = []
        else:
            started = e.leg != qleg
            if started: qleg = e.leg; qev = []
            if brk_h == h and brk_dir == d:
                qev.append(dict(k=h, start=started, level=brk_px))
            qev = [x for x in qev if h - x["k"] <= 59]
        H = lambda i: bars[i][2]; L = lambda i: bars[i][3]; C = lambda i: bars[i][4]
        def outcome(x):
            if h - x["k"] < 3: return 0
            for j in range(x["k"] + 1, x["k"] + 4):
                if d * StrL(C(j), x["level"]) < 0: return 2
            return 1
        r = dict(state="NODATA", reason=0, n=0, s=0, fail=0, pend=0, sample="-", so=0, has_anchor=False, anchor_bar=-1,
                 ext=None, leg=None, x=None, num_r=None, has_x=False, num=0, den=1, score=-1, tier="NA", dir=0)
        pairs = []
        if h >= 11:
            so = 0
            for i in range(h - 10, h + 1):
                inter = max(0, StrL(min(H(i), H(i - 1)), max(L(i), L(i - 1))))
                uni = StrL(max(H(i), H(i - 1)), min(L(i), L(i - 1)))
                pairs.append((inter, uni))
                so += FP if uni == 0 else (FP * inter) // uni
            r["so"] = so
            if d == 0:
                r["state"] = "NODIR"
            else:
                r["dir"] = d
                mature = sum(1 for x in qev if h - x["k"] >= 3)
                m = 0
                for x in qev:
                    res = outcome(x)
                    if res == 0: r["pend"] += 1; continue
                    m += 1
                    if m <= mature - 5: continue
                    r["n"] += 1
                    if res == 1: r["s"] += 1
                    else: r["fail"] += 1
                if r["n"] >= 3: r["sample"] = "FIVE" if r["n"] == 5 else "LOW"
                else: r["sample"] = "FEW"; r["reason"] |= 1
                if e.anchor is None:
                    r["reason"] |= 2
                else:
                    a = tidx[e.anchor["bar_time"]]
                    r["has_anchor"] = True; r["anchor_px"] = e.anchor["price"]; r["anchor_bar"] = a
                    ext = H(a + 1) if d == 1 else L(a + 1)
                    for i in range(a + 2, h + 1):
                        ext = max(ext, H(i)) if d == 1 else min(ext, L(i))
                    r["ext"] = ext
                    r["leg"] = d * StrL(ext, e.anchor["price"])
                    if r["leg"] <= 0: r["reason"] |= 4
                    elif r["leg"] > 10 ** 10: r["reason"] |= 8
                    else:
                        x = min(max(d * StrL(ext, C(h)), 0), r["leg"])
                        r["x"] = x; r["num_r"] = Q.retrace_num(x, r["leg"]); r["has_x"] = True
                if r["reason"]:
                    r["state"] = "PARTIAL"
                else:
                    r["state"] = "OK"
                    r["den"] = LCD * r["leg"]
                    r["num"] = 40 * r["s"] * (LCD // r["n"]) * r["leg"] + 462000 * r["num_r"] + 3 * (11 * FP - r["so"]) * r["leg"]
                    r["score"] = (2 * r["num"] + r["den"]) // (2 * r["den"])
                    r["tier"] = "POOR" if r["num"] < 40 * r["den"] else "FAIR" if r["num"] < 70 * r["den"] else "GOOD"
        # --- QltLog
        st = r["state"]
        trend = st in ("OK", "PARTIAL"); data = st != "NODATA"; ok = st == "OK"
        brkv = trend and r["n"] >= 3
        legv = trend and r["has_anchor"] and 0 <= r["anchor_bar"] < h
        reason = "HISTORY" if st == "NODATA" else "-" if st != "PARTIAL" else "+".join(
            n for bit, n in ((1, "FEW"), (2, "ANCHOR"), (4, "LEG"), (8, "SCALE")) if r["reason"] & bit)
        px = lambda v: f"{v:.5f}"
        def evlist():
            mature = sum(1 for x in qev if h - x["k"] >= 3)
            out = []; m = 0
            for x in qev:
                res = outcome(x)
                if res != 0:
                    m += 1
                    if m <= mature - 5: continue
                obs = "|".join(px(C(j)) for j in range(x["k"] + 1, min(x["k"] + 3, h) + 1))
                out.append(f"{tstr(bars[x['k']][0] + H4)}@{px(x['level'])}/{'START' if x['start'] else 'BOS'}/"
                           f"{['PEND', 'OK', 'FAIL'][res]}/{obs or '-'}")
            return ";".join(out) or "-"
        d6 = lambda v: f"{v:.6f}"
        row = (f"HMI-QLT,USDJPY,live=0,bar={tstr(bars[h][0] + H4)},ctx={ctx},state={st},reason={reason},def={Q.DEF_ID},"
               f"dir={r['dir']},ev={evlist() if trend else '-'},b_n={r['n']},b_ok={r['s']},b_fail={r['fail']},b_pend={r['pend']},"
               f"q_break={d6(100.0 * r['s'] / r['n']) if brkv else 'NA'},"
               f"anchor={px(r['anchor_px']) if trend and r['has_anchor'] else 'NA'},"
               f"anchor_bar={tstr(bars[r['anchor_bar']][0]) if trend and r['has_anchor'] else '-'},"
               f"ext={px(r['ext']) if legv else 'NA'},close={px(C(h))},leg_pts={r['leg'] if legv else 'NA'},"
               f"retr_pts={r['x'] if r['has_x'] else 'NA'},q_retrace={d6(r['num_r'] / r['leg']) if r['has_x'] else 'NA'},"
               f"ov={';'.join(f'{i}/{u}' for i, u in pairs) if data else 'NA'},ov_sum={r['so'] if data else 'NA'},"
               f"q_overlap={d6(100.0 * (11 * FP - r['so']) / (11 * FP)) if data else 'NA'},"
               f"raw={d6(r['num'] / r['den']) if ok else 'NA'},score={r['score'] if ok else 'NA'},tier={r['tier']},"
               f"sample={r['sample']},inst=0001,run=7,init=1")
        rows.append(row)
    return rows

def compare(name, bars):
    bars = [tuple(b) for b in bars]
    mine = mirror_rows(bars)
    _, recs, _, ctxs = Q.run(bars)
    model = [Q.qlt_row(bars, h, ctxs[h], recs[h]) for h in range(len(bars))]
    bad = [(h, a, b) for h, (a, b) in enumerate(zip(mine, model)) if a != b]
    print(f"{name}: {len(bars)} bars, {len(bad)} rows differ")
    for h, a, b in bad[:3]:
        fa, fb = a.split(","), b.split(",")
        print("  bar", h, [(x, y) for x, y in zip(fa, fb) if x != y][:4])
    return len(bad)


# ---- QltPanelText / QltPanelShort, with the \\uXXXX macros read from the .mqh files and decoded as HMI_U does ------
ZH = {}
for f in (os.path.join(MQH, 'HMI_StrengthEngine.mqh'), os.path.join(MQH, 'HMI_QualityEngine.mqh')):
    for m in re.finditer(r'#define (ZH_\w+)\s+"([^"]*)"', open(f, encoding='utf-8').read()):
        ZH[m.group(1)] = re.sub(r'\\\\u([0-9A-Fa-f]{4})', lambda x: chr(int(x.group(1), 16)), m.group(2))
U = lambda k: ZH[k]
def rnd(num, den): return (2 * num + den) // (2 * den)
def bits(r):
    rs = r["reason"].split("+") if r["state"] == "PARTIAL" else []
    return ("FEW" in rs, "ANCHOR" in rs, "LEG" in rs or "SCALE" in rs)
def local(r, sep):
    out = ""
    if r["n"] >= 3: out += U("ZH_BRK") + " " + str(rnd(100 * r["s"], r["n"]))
    if r["q_retrace"] is not None: out += ("" if out == "" else sep) + U("ZH_RET") + " " + str(rnd(r["num_r"], r["leg"]))
    out += ("" if out == "" else sep) + U("ZH_OVL") + " " + str(rnd(100 * (11 * Q.FP - r["so"]), 11 * Q.FP))
    return out
def why(r):
    few, anc, leg = bits(r); out = ""
    if few:
        out = U("ZH_MATURE") + " " + str(r["n"]) + "/3"
        if r["pend"] > 0: out += U("ZH_COMMA") + U("ZH_PENDING") + " " + str(r["pend"])
    if anc: out += ("" if out == "" else U("ZH_SEMI")) + U("ZH_NOANCHOR")
    if leg: out += ("" if out == "" else U("ZH_SEMI")) + U("ZH_LEGBAD")
    return out
TZ = {"POOR": "ZH_POOR", "FAIR": "ZH_FAIR", "GOOD": "ZH_GOOD"}
def full(r, ctx, wait, when):
    head = U("ZH_QUALITY") + "  "
    if r is None: return head + U("ZH_WAIT")
    if wait:
        if r["state"] != "OK": return head + U("ZH_WAIT")
        return (head + U("ZH_WAIT") + U("ZH_LP") + U("ZH_LASTOK") + " " + U(TZ[r["tier"]]) + " " + U("ZH_DOT") + " " +
                str(r["score"]) + "/100" + U("ZH_COMMA") + when + " H4 " + U("ZH_CLOSE") + U("ZH_RP"))
    if r["state"] == "NODATA": return head + U("ZH_FEW") + U("ZH_LP") + U("ZH_FEW12") + U("ZH_RP")
    if r["state"] == "NODIR": return head + U("ZH_NORATE") + U("ZH_LP") + U("ZH_RANGE" if ctx == "RANGE" else "ZH_TRANS") + U("ZH_RP")
    if r["state"] == "PARTIAL":
        return (head + U("ZH_FEW" if bits(r)[0] else "ZH_NA") + U("ZH_LP") + why(r) + U("ZH_RP") + "  " + U("ZH_LOCAL") + " " +
                local(r, " " + U("ZH_DOT") + " "))
    return (head + U(TZ[r["tier"]]) + " " + U("ZH_DOT") + " " + str(r["score"]) + "/100" + U("ZH_LP") +
            ("5 " + U("ZH_TIMES_EV") if r["sample"] == "FIVE" else U("ZH_LOWSMP") + " " + str(r["n"]) + " " + U("ZH_TIMES_BRK")) + U("ZH_RP"))
def short(r, ctx, wait, when):
    head = U("ZH_QLT_SHORT") + " "
    if r is None or wait: return head + U("ZH_WAIT")
    if r["state"] == "NODATA": return head + U("ZH_FEW")
    if r["state"] == "NODIR": return head + U("ZH_NORATE")
    if r["state"] == "PARTIAL":
        return head + (U("ZH_FEW") + " " + str(r["n"]) + "/3" if bits(r)[0] else U("ZH_NA")) + "   " + U("ZH_LOCAL_S") + " " + local(r, " ")
    return head + U(TZ[r["tier"]]) + " " + str(r["score"]) + "/100   " + ("5 " + U("ZH_TIMES_EV") if r["sample"] == "FIVE" else U("ZH_LOWSMP"))


def panels(bars):
    _, recs, _, ctxs = Q.run(bars)
    bad = n = 0
    for h, r in enumerate(recs):
        for w in (False, True):
            for a, b in ((full(r, ctxs[h], w, "2026.10.26 12:00"), Q.panel_text(r, ctxs[h], w, "2026.10.26 12:00")),
                         (short(r, ctxs[h], w, ""), Q.compact_text(r, ctxs[h], w, ""))):
                n += 1
                bad += a != b
    return n, bad


def main():
    series = []
    stair = P.path([(1.1050, 0), (1.1000, 2), (1.1100, 5), (1.1040, 3), (1.1160, 6), (1.1100, 3), (1.1230, 6), (1.1180, 3),
                    (1.1300, 6), (1.1250, 3), (1.1370, 6), (1.1330, 3), (1.1440, 6), (1.1400, 3), (1.1510, 6), (1.1470, 3),
                    (1.1580, 6), (1.1540, 3)])
    tc = lambda after: P.path([(1.1050, 0), (1.1000, 2), (1.1100, 5), (1.1040, 3), (1.1160, 6), (1.1010, 6)] + after)   # noqa: E731
    fast = [(1.1050, 0), (1.1000, 2), (1.1100, 5), (1.1070, 2), (1.1140, 1)]
    series += [("staircase", stair), ("CHOCH then TRANS_OK", tc([(1.1060, 3), (1.1030, 3), (1.1055, 3), (1.0950, 6)])),
               ("CHOCH then TRANS_FAIL", tc([(1.1080, 3), (1.1050, 3), (1.1130, 4)])),
               ("INVALID anchor", P.path(fast + [(1.1150, 1), (1.1160, 1), (1.1220, 3), (1.1180, 3), (1.1260, 4), (1.1230, 3),
                                                  (1.1300, 4), (1.1270, 3), (1.1340, 4)])),
               ("failing breaks", Q.cbars([0, -100, -200, -300, -200, -100, 0, 100, 200, 300, 250, 200, 150, 200, 300, 340, 320,
                                           400, 480, 470, 460, 515, 505, 600, 680, 670, 660, 715, 705, 800, 880, 870, 860, 915,
                                           905, 905, 905, 865, 925, 1025, 965], 30))]
    if len(sys.argv) > 1:
        series.append((os.path.basename(sys.argv[1]), B.load_h1(sys.argv[1])))
    rows = rbad = pn = pbad = 0
    for nm, bb in series:
        for tag, b in (("", [tuple(x) for x in bb]), (" mirror", Q.mirror(bb))):
            k = compare(nm + tag, b)
            rows += len(b); rbad += k
            n, bad = panels(b)
            pn += n; pbad += bad
    print(f"HMI-QLT rows: {rows} compared, {rbad} differ;  panel strings: {pn} compared, {pbad} differ")
    ok = rbad == 0 and pbad == 0
    print("PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
