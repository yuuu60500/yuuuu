"""Synthetic MT5 logs for ReloadTest.ps1 (v2.51). Writes one folder per case + cases.json next to this file.

    cd tools/logtests && python3 gen_cases.py      (the generated folders are committed: PowerShell alone can rerun them)
"""
import os, json
T = "2026.10.02 10:00:00.000"
def L(src, payload): return f"{T}  H4M5_Identification ({src})  {payload}"
def tail(inst, run, init): return f",inst={inst}" + (f",run={run},init={init}" if run is not None else "")

def begin(src, b, ver, inst, run, init, frm="2026.09.07 03:40", to="2026.09.30 12:35", warm="2026.09.07 12:00", params="ABCD1234"):
    s = f"HMI-BUILD-BEGIN,USDJPY,m5_bars=5000,h4_bars=500,from={frm},to={to},ver={ver},params={params},inst={inst}" + ("" if b is None else f",build={b}") + f",warmup_end={warm}"
    if run is not None: s += f",run={run},init={init}"
    return L(src, s)
def end(src, b, marks, inst, run, init, liq="READY", liqev=2, unknown=0, liqwait=0, drop=()):
    f = [("marks", marks), ("cycles", 3), ("pois", 4), ("blocks", 5), ("build", b), ("liq", liq), ("liqev", liqev), ("unknown", unknown), ("liqwait", liqwait)]
    s = "HMI-BUILD-END,USDJPY," + ",".join(f"{k}={v}" for k, v in f if k not in drop and v is not None)
    return L(src, s + ("" if "id" in drop else tail(inst, run, init)))
def model(src, tag, t, inst, run, init, cyc, name="CISD"):
    return L(src, f"{tag},USDJPY,MODEL,1,{cyc},{cyc},OB,{name},{t},1.23456,2026.09.10 09:30:00,1.23400" + tail(inst, run, init))
def liq(src, tag, t, lvl, kind, inst, run, init):
    return L(src, f"{tag},USDJPY,LIQ,1,0,0,{lvl},{kind},{t},1.23500,2026.09.10 10:55:00,0" + tail(inst, run, init))
def diag(src, kind, bar, inst, run, init, extra="id=55,dir=1"):
    head, *sub = kind.split(",")                      # real layout: HMI-POI,<sym>,NEW,...
    return L(src, f"{head},USDJPY," + "".join(s + "," for s in sub) + f"{extra},bar={bar}" + tail(inst, run, init))

MK = ["2026.09.10 10:05:00", "2026.09.15 14:35:00", "2026.09.22 08:20:00"]
LQ = [("2026.09.12 09:05:00", "PDH", "SWEEP"), ("2026.09.18 16:10:00", "PWL", "BROKEN")]
SRC = "USDJPY,M5"

def blk(b, ver="2.51", inst="0001", run=7, init=1, marks=MK, liqs=LQ, end_kw=None, with_end=True, row_id=None, diag_id=None,
        frm="2026.09.07 03:40", to="2026.09.30 12:35", warm="2026.09.07 12:00", src=SRC, params="ABCD1234", extra_rows=(), begin_b="same",
        cycles=None, chain=True, names=None):
    rid = row_id or (run, init)
    did = diag_id or (run, init)
    out = [begin(src, b if begin_b == "same" else begin_b, ver, inst, run, init, frm, to, warm, params)]
    if chain:
        out.append(diag(src, "HMI-POI,NEW", "2026.09.08 08:00", inst, *did, extra="id=55,dir=1,lo=1.22700,hi=1.22800,origin=2026.09.08 00:00"))
        out.append(diag(src, "HMI-SESS,START", "2026.09.10 09:55", inst, *did, extra="id=60,poi=55,dir=1"))
        out.append(diag(src, "HMI-BLK,NEW", "2026.09.10 09:58", inst, *did, extra="id=61,sess=60,dir=1,type=OB,counter=0"))
        out.append(diag(src, "HMI-ARM", "2026.09.10 10:00", inst, *did, extra="block=61,sess=60,dir=1"))
    for i, t in enumerate(marks): out.append(model(src, "HMI-BUILD", t, inst, *rid, cyc=(cycles[i] if cycles else 100 + i),
                                                   name=(names[i] if names else "CISD")))
    for (t, l, k) in liqs: out.append(liq(src, "HMI-BUILD", t, l, k, inst, *rid))
    out += list(extra_rows)
    if with_end:
        kw = dict(liqev=len(liqs))
        kw.update(end_kw or {})
        out.append(end(src, kw.pop("b", b), kw.pop("marks", len(marks)), inst, run, init, **kw))
    return out
def start(ver="2.51", inst="0001", run=7, init=1, src=SRC):
    return L(src, f"HMI v{ver} starting on USDJPY PERIOD_M5  instance={inst}" + (f" run={run} init={init}" if run is not None else ""))

C = {}
def case(name, lines, args, expect, forbid=()):
    os.makedirs(name, exist_ok=True)
    open(os.path.join(name, "20261002.log"), "w", encoding="utf-8").write("\n".join(lines) + "\n")
    C[name] = dict(args=args, expect=expect, forbid=list(forbid))

R = ["-Source", SRC]
NOPASS = ["IDENTICAL inside", "AGREE BOTH WAYS", "MODEL IDENTICAL"]
case("n01_ok",             [start()] + blk(1) + blk(2), R, ["IDENTICAL inside the comparable region (3 MODEL + 2 LIQ)"])
case("n02_wrong_end",      [start()] + blk(1, end_kw={"b": 99}) + blk(2, end_kw={"b": 99}), R, ["INCOMPLETE build(s) - no verdict", "END build=99, BEGIN build=1"], NOPASS)
case("n03_marks",          [start()] + blk(1) + blk(2, end_kw={"marks": 5}), R, ["END marks=5 but 3 MODEL row(s)"], NOPASS)
case("n04_end_no_id",      [start()] + blk(1) + blk(2, end_kw={"drop": ("id",)}), R, ["END without run/init"], NOPASS)
case("n05_model_no_id",    [start()] + blk(1) + blk(2, row_id=(None, None)), R, ["row(s) without run/init (HMI-BUILD)"], NOPASS)
case("n06_block_no_id",    [start(run=None)] + blk(1, run=None, init=None) + blk(2, run=None, init=None), R, ["BEGIN without run/init (v2.51 log must carry it)"], NOPASS)
case("n07_no_liqev",       [start()] + blk(1) + blk(2, end_kw={"drop": ("liqev",)}), R, ["END without a valid liqev="], NOPASS)
case("n08_diag_other_id",  [start()] + blk(1) + blk(2, diag_id=(7, 9)), R, ["carry another run/init than the BEGIN (HMI-ARM/HMI-BLK/HMI-POI/HMI-SESS)"], NOPASS)
case("n08c_chain",         [start()] + blk(1) + blk(2, diag_id=(7, 9)), ["-Chain"], ["1 INCOMPLETE build(s) skipped", "block ARMED                       1"])
case("n09_model_other_id", [start()] + blk(1) + blk(2, row_id=(7, 2)), R, ["carry another run/init than the BEGIN (HMI-BUILD)"], NOPASS)
case("n10_waiting",        [start()] + blk(1, liqs=[], end_kw={"liq": "WAITING", "liqwait": 2}) + blk(2), R,
     ["LIQ rows PENDING, MODEL rows compared", "MODEL IDENTICAL inside the comparable region (3 rows)", "pending (liquidity WAITING)"], ["(3 MODEL + 2 LIQ) - no repaint"])
case("n11_dup_begin",      [start()] + blk(1, with_end=False) + blk(2) + blk(3), R, ["no END before the next BEGIN (build 1)", "IDENTICAL inside the comparable region"])
case("n12_missing_end",    [start()] + blk(1) + blk(2, with_end=False), R, ["no END (the log ends inside build 2)"], NOPASS)
case("n13_legacy",         [start("2.48", run=None)] + blk(1, ver="2.48", run=None, init=None, end_kw={"drop": ("liq", "liqev", "unknown", "liqwait")})
                                                   + blk(2, ver="2.48", run=None, init=None, end_kw={"drop": ("liq", "liqev", "unknown", "liqwait")}), R,
     ["IDENTICAL inside the comparable region", "liquidity state not logged"])
case("n14_xver_disjoint",  [start("2.48", run=None)] + blk(1, ver="2.48", run=None, init=None, frm="2026.09.01 00:00", to="2026.09.10 00:00", warm="2026.09.01 08:20",
                                                          marks=["2026.09.05 10:05:00"], liqs=[], end_kw={"drop": ("liq", "liqev", "unknown", "liqwait")})
                           + [start()] + blk(2, frm="2026.09.20 00:00", to="2026.09.30 00:00", warm="2026.09.20 08:20", marks=["2026.09.25 10:05:00"], liqs=[]), R,
     ["NOT COMPARABLE - no common region"], ["0 difference(s)"])
case("n15_xver_moved",     [start("2.48", run=None)] + blk(1, ver="2.48", run=None, init=None, frm="2026.09.05 00:00", end_kw={"drop": ("liq", "liqev", "unknown", "liqwait")})
                           + [start()] + blk(2, frm="2026.09.06 00:00"), R,
     ["DIFFERENT VERSIONS (2.48 / 2.51)", "PENDING REVIEW, not a pass", "use a fixed window"], ["same window and parameters"])
case("n16_xver_params",    [start("2.48", run=None)] + blk(1, ver="2.48", run=None, init=None, params="FFFF0000", end_kw={"drop": ("liq", "liqev", "unknown", "liqwait")})
                           + [start()] + blk(2), R, ["NOT COMPARABLE - different parameters"], ["0 difference(s)"])
case("n17_xver_empty",     [start("2.48", run=None)] + blk(1, ver="2.48", run=None, init=None, marks=[], liqs=[], end_kw={"drop": ("liq", "liqev", "unknown", "liqwait")})
                           + [start()] + blk(2, marks=[], liqs=[]), R, ["INSUFFICIENT SAMPLE"], ["0 difference(s)"])
A = "USDJPY#0A48,M5"; B = "USDJPY#0B51,M5"
v48 = blk(1, ver="2.48", inst="0A48", run=None, init=None, end_kw={"drop": ("liq", "liqev", "unknown", "liqwait")})
v51 = blk(1, inst="0B51", run=7, init=3)
case("n18_versus_same",    [start("2.48", "0A48", None)] + v48 + [start("2.51", "0B51", 7, 3)] + v51, ["-Source", A, "-Versus", B],
     ["split as SYMBOL#INSTANCE", "upgrade regression: 0 difference(s) over 3 / 3 MODEL row(s), same window and parameters."])
v51d = blk(1, inst="0B51", run=7, init=3, marks=MK[:2] + ["2026.09.22 08:25:00"])
case("n19_versus_diff",    [start("2.48", "0A48", None)] + v48 + [start("2.51", "0B51", 7, 3)] + v51d, ["-Source", A, "-Versus", B],
     ["upgrade regression: 2 difference(s) over 3 / 3 MODEL row(s)"])
case("n20_wait_inconsistent", [start()] + blk(1) + blk(2, end_kw={"liq": "WAITING", "liqwait": 0}), R, ["END liq=WAITING but liqwait=0"], NOPASS)
case("n21_v250_no_liqwait", [start("2.50")] + blk(1, ver="2.50", end_kw={"drop": ("liqwait",)}) + blk(2, ver="2.50", end_kw={"drop": ("liqwait",)}), R,
     ["IDENTICAL inside the comparable region"])
live_ok  = model(SRC, "HMI-LIVE", "2026.09.30 13:05:00", "0001", 7, 1, 200)
live_noid= model(SRC, "HMI-LIVE", "2026.09.30 13:35:00", "0001", None, None, 201)
b2 = blk(2, init=2, to="2026.09.30 14:00", marks=MK + ["2026.09.30 13:05:00"])
case("n22_live_ok",        [start()] + blk(1) + [live_ok] + [start(init=2)] + b2, ["-LiveVsBuild"], ["AGREE BOTH WAYS on every covered bar (MODEL + LIQ)"])
case("n23_live_noid",      [start()] + blk(1) + [live_ok, live_noid] + [start(init=2)] + b2, ["-LiveVsBuild"],
     ["live rows without run/init 1", "nothing comparable yet - no PASS can be given."], ["AGREE BOTH WAYS"])
case("n24_live_inside",    [start()] + blk(1, extra_rows=[live_ok]) + blk(2), R, ["HMI-LIVE row inside a historical build"], NOPASS)
# ---- v2.52: build= must exist and be a positive integer on BEGIN and END (A-54)
NOB = ("build",)
case("b01_build_both_missing", [start()] + blk(1, begin_b=None, end_kw={"drop": NOB}) + blk(2, begin_b=None, end_kw={"drop": NOB}), R,
     ["BEGIN without a valid build=", "END without a valid build="], NOPASS)
case("b02_build_begin_missing", [start()] + blk(1) + blk(2, begin_b=None), R, ["BEGIN without a valid build="], NOPASS)
case("b03_build_end_missing",   [start()] + blk(1) + blk(2, end_kw={"drop": NOB}), R, ["END without a valid build="], NOPASS)
case("b04_build_bogus",         [start()] + blk("bogus") + blk("bogus"), R, ["BEGIN without a valid build= (bogus)"], NOPASS)
case("b05_build_zero",          [start()] + blk(0) + blk(0), R, ["BEGIN without a valid build= (0)"], NOPASS)
case("b06_build_legacy_243",    [start("2.43", run=None)] + blk(1, ver="2.43", run=None, init=None, begin_b=None, end_kw={"drop": ("build", "liq", "liqev", "unknown", "liqwait")})
                                                     + blk(2, ver="2.43", run=None, init=None, begin_b=None, end_kw={"drop": ("build", "liq", "liqev", "unknown", "liqwait")}), R,
     ["IDENTICAL inside the comparable region"], ["INCOMPLETE"])
# ---- v2.52: a verdict needs a judged sample per category (A-55)
case("w01_waiting_no_model",    [start()] + blk(1, marks=[], liqs=[], end_kw={"liq": "WAITING", "liqwait": 2}) + blk(2, marks=[]), R,
     ["MODEL  INSUFFICIENT SAMPLE", "LIQ    PENDING"], ["IDENTICAL inside", "MODEL IDENTICAL"])
case("w02_ready_no_model",      [start()] + blk(1, marks=[]) + blk(2, marks=[]), R,
     ["MODEL  INSUFFICIENT SAMPLE", "LIQ    IDENTICAL over 2 / 2 row(s)"], ["MODEL IDENTICAL"])
case("w03_ready_no_liq",        [start()] + blk(1, liqs=[]) + blk(2, liqs=[]), R,
     ["MODEL  IDENTICAL over 3 / 3 row(s)", "LIQ    no event on either side", "IDENTICAL inside the comparable region (3 MODEL + 0 LIQ)"])
live_liq = liq(SRC, "HMI-LIVE", "2026.09.30 13:05:00", "PDL", "SWEEP", "0001", 7, 1)
b2w = blk(2, init=2, to="2026.09.30 14:00", liqs=LQ + [("2026.09.30 13:05:00", "PDL", "SWEEP")], end_kw={"liq": "WAITING", "liqwait": 1})
case("w04_live_only_liq_waiting", [start()] + blk(1) + [live_liq] + [start(init=2)] + b2w, ["-LiveVsBuild"],
     ["no judged event (LIQ pending", "nothing comparable yet - no PASS can be given."], ["AGREE BOTH WAYS"])

# ---- v2.53: H4 structure events as a judged category, version attribution (A-56)
def ctx(kind, d, cx, st, bar, sw, px, close, inst="0001", run=7, init=1, live=0, also=None, messy=0, src=SRC):
    s = f"HMI-CTX,USDJPY,{kind},dir={d},live={live},ctx={cx},str={st},messy={messy},bar={bar},swing={sw},swing_px={px},close={close}"
    if also is not None: s += f",also={also}"
    return L(src, s + tail(inst, run, init))
def dedup(kind, d, bar, prim, swings, inst="0001", run=7, init=1, src=SRC, also=None):
    return L(src, f"HMI-CTX-DEDUP,USDJPY,{kind},dir={d},bar={bar},primary={prim},also={len(swings) if also is None else also},swings={'|'.join(swings)}" + tail(inst, run, init))

E1 = ("BOS", "UP", "BULLISH", 1, "2026.09.08 08:00", "2026.09.07 20:00", "1.23000", "1.23100")
E2s = ("BOS", "UP", "BULLISH", 2, "2026.09.08 12:00", "2026.09.06 12:00", "1.22900", "1.23050")   # stale in v2.52
E3 = ("BOS", "UP", "BULLISH", 3, "2026.09.10 08:00", "2026.09.09 16:00", "1.23300", "1.23400")
STALE = "2026.09.06 12:00@1.22900"
def ctx_rows(rows, **kw): return [ctx(*r, **kw) for r in rows]

same = ctx_rows([E1, E3[:3] + (2,) + E3[4:]], also=0)
case("c01_ctx_identical", [start()] + blk(1, extra_rows=same) + blk(2, extra_rows=same), R,
     ["CTX    IDENTICAL over 2 / 2 event(s)", "IDENTICAL inside the comparable region"])
case("c02_ctx_mismatch",  [start()] + blk(1, extra_rows=same) + blk(2, extra_rows=same + ctx_rows([E2s], also=0)), R,
     ["CTX    MISMATCH (1)", "differ INSIDE the comparable region"], ["IDENTICAL inside"])
lctx = ctx(*E3[:4], "2026.09.30 13:00", *E3[5:], live=1, also=0)
bctx = ctx(*E3[:4], "2026.09.30 13:00", *E3[5:], live=0, also=0, init=2)
b2c = blk(2, init=2, to="2026.09.30 14:00", marks=MK + ["2026.09.30 13:05:00"], extra_rows=[bctx])
case("c03_live_ctx_ok",      [start()] + blk(1) + [live_ok, lctx] + [start(init=2)] + b2c, ["-LiveVsBuild"],
     ["AGREE BOTH WAYS on every covered bar (MODEL + LIQ)", "(+ 1 H4 structure event(s))"])
b2n = blk(2, init=2, to="2026.09.30 14:00", marks=MK + ["2026.09.30 13:05:00"])
case("c04_live_ctx_missing", [start()] + blk(1) + [live_ok, lctx] + [start(init=2)] + b2n, ["-LiveVsBuild"],
     ["MISMATCH(ES) on covered bars", "live only  [1->2] CTX"], ["AGREE BOTH WAYS"])

A52, B53 = "USDJPY#0A52,M5", "USDJPY#0B53,M5"
def side(ver, inst, init, rows, marks=MK, extra=(), cycles=None, price_at=None, chain=True, names=None):
    blkrows = blk(1, ver=ver, inst=inst, init=init, marks=marks, extra_rows=list(rows) + list(extra), cycles=cycles, chain=chain, names=names)
    if price_at:                                     # A-57 counterexample: one MODEL price changed
        blkrows = [l.replace("1.23456", "9.99900") if ("MODEL" in l and price_at in l) else l for l in blkrows]
    return [start(ver, inst, 7, init)] + blkrows
V = ["-Source", A52, "-Versus", B53]
def old52_rows(e1=E1, inst="0A52"): return [ctx(*e1, inst=inst, init=1), ctx(*E2s, inst=inst, init=1), ctx(*E3, inst=inst, init=1)]
def new53_rows(e1=E1, e3=None, inst="0B53"):
    e3 = e3 or (E3[:3] + (2,) + E3[4:])
    return [ctx(*e1, inst=inst, init=2, also=1), dedup("BOS", "UP", E1[4], "2026.09.07 20:00@1.23000", [STALE], inst=inst, init=2),
            ctx(*e3, inst=inst, init=2, also=0)]
OK_NOT = ["PENDING_ATTRIBUTION - a manual", "UNEXPLAINED - not traced"]
case("c05_versus_dedup_only", side("2.52", "0A52", 1, old52_rows()) + side("2.53", "0B53", 2, new53_rows()), V,
     ["suppressed duplicate               1", "strength renumbered                1", "PENDING_ATTRIBUTION                0", "UNEXPLAINED                        0",
      "H4 state: identical at every event bar", "all 2 difference(s) traced to the BOS de-dup with a concrete link"], OK_NOT)

# c06: v2.52 counts a stale high in TRANSITION (TRANS_FAIL -> BULLISH); v2.53 had processed it and stays in
# TRANSITION. In v2.52 only, the BULLISH bar lets a POI be made, a session start on it, a block, ARMED, a model.
CH = ("CHOCH", "DOWN", "TRANSITION", 0, "2026.09.09 08:00", "2026.09.08 20:00", "1.22950", "1.22900")
TF = ("TRANS_FAIL", "UP", "BULLISH", 1, "2026.09.10 08:00", "2026.09.06 12:00", "1.22900", "1.23000")
def chain52(inst="0A52", blk79="2026.09.11 09:30", extra=()):
    return [diag(SRC, "HMI-POI,NEW",   "2026.09.10 08:00", inst, 7, 1, extra="id=77,dir=1,lo=1.22800,hi=1.22900,origin=2026.09.10 00:00"),
            diag(SRC, "HMI-SESS,START", "2026.09.11 09:05", inst, 7, 1, extra="id=78,poi=77,dir=1"),
            diag(SRC, "HMI-BLK,NEW",   blk79,              inst, 7, 1, extra="id=79,sess=78,dir=1,type=OB,counter=0"),
            diag(SRC, "HMI-ARM",       "2026.09.11 10:00", inst, 7, 1, extra="block=79,sess=78,dir=1")] + list(extra)
ctx52b = [ctx(*E1, inst="0A52", init=1), ctx(*CH, inst="0A52", init=1), ctx(*TF, inst="0A52", init=1, messy=1)]
old52b = ctx52b + chain52()
new53b = [ctx(*E1, inst="0B53", init=2, also=1), dedup("BOS", "UP", E1[4], "2026.09.07 20:00@1.23000", [STALE], inst="0B53", init=2),
          ctx(*CH, inst="0B53", init=2, also=0)]
case("c06_versus_state_divergence", side("2.52", "0A52", 1, old52b, marks=MK + ["2026.09.12 10:05:00"], cycles=[100, 101, 102, 79])
                                    + side("2.53", "0B53", 2, new53b), V,
     ["suppressed duplicate               1", "H4 state differs in 1 interval(s), first from 2026.09.10 08:00",
      "chain differences in the common region: POI 1   SESS 1   BLK 1   ARM 1   MODEL 1",
      "verdicts: explained 6   PENDING_ATTRIBUTION 0   UNEXPLAINED 0", "all 6 difference(s) traced to the BOS de-dup with a concrete link"], OK_NOT)
case("c07_versus_model_unexplained", side("2.52", "0A52", 1, [ctx(*E1, inst="0A52", init=1)], marks=MK + ["2026.09.12 10:05:00"])
                                     + side("2.53", "0B53", 2, [ctx(*E1, inst="0B53", init=2, also=0)]), V,
     ["H4 state: identical at every event bar", "<- before the first H4 direction difference", "1 difference(s) UNEXPLAINED - not traced"], ["traced to the BOS de-dup with a concrete link"])
case("c08_versus_ctx_unexplained", side("2.52", "0A52", 1, old52_rows()) + side("2.53", "0B53", 2, [ctx(*E1, inst="0B53", init=2, also=0), ctx(*E3[:3], 2, *E3[4:], inst="0B53", init=2, also=0)]), V,
     ["CTX UNEXPLAINED                        1", "before the first de-dup the two versions are the same code path", "UNEXPLAINED - not traced"], ["traced to the BOS de-dup with a concrete link"])
# ---- A-57: the reviewer's three counterexamples, plus a model of an unchanged open cycle
case("c11_cx_h4_close_changed", side("2.52", "0A52", 1, old52_rows()) + side("2.53", "0B53", 2, new53_rows(e3=E3[:3] + (2,) + E3[4:7] + ("9.99900",))), V,
     ["the market data differs, the de-dup does not move a close", "UNEXPLAINED - not traced"], ["traced to the BOS de-dup with a concrete link"])
case("c12_cx_first_bos_str9", side("2.52", "0A52", 1, old52_rows()) + side("2.53", "0B53", 2, new53_rows(e1=E1[:3] + (9,) + E1[4:])), V,
     ["str=9 but the strength rule gives 1", "UNEXPLAINED - not traced"], ["traced to the BOS de-dup with a concrete link"])
case("c13_cx_model_price_changed", side("2.52", "0A52", 1, old52b, marks=MK + ["2026.09.12 10:05:00"], cycles=[100, 101, 102, 79])
                                   + side("2.53", "0B53", 2, new53b, price_at="2026.09.15 14:35"), V,
     ["its cycle's ARMED row (block 101) is not in the log", "PENDING_ATTRIBUTION - a manual conclusion"], ["traced to the BOS de-dup with a concrete link"])
case("c14_cx_model_open_cycle", side("2.52", "0A52", 1, old52b, marks=MK + ["2026.09.12 10:05:00"], cycles=[61, 101, 102, 79])
                                + side("2.53", "0B53", 2, new53b, cycles=[61, 101, 102], price_at="2026.09.10 10:05"), V,
     ["same anchor, cycle open in both builds at this bar", "UNEXPLAINED - not traced"], ["traced to the BOS de-dup with a concrete link"])

# ---- A-58: a link is not a lifetime. Each case is c06 (or one of the two
# stories below) with ONE field changed; "ok" cases keep the legal edges.
NOTRACE = ["traced to the BOS de-dup with a concrete link"]
def as_explained(item): return "{:<20} {}".format("explained", item)     # the attribution file's line layout
def v52(rows, marks, cycles, names=None, **kw):
    return side("2.52", "0A52", 1, rows, marks=MK + marks, cycles=[100, 101, 102] + cycles, names=(["CISD"] * 3 + names) if names else None, **kw)
NEW53 = side("2.53", "0B53", 2, new53b)
case("c15_cx_model_before_armed",  v52(old52b, ["2026.09.11 09:35:00"], [79]) + NEW53, V,
     ["outside its parent's lifetime in v2.52: confirmed 2026.09.11 09:35, before its cycle's ARMED 2026.09.11 10:00",
      "verdicts: explained 5   PENDING_ATTRIBUTION 0   UNEXPLAINED 1", "UNEXPLAINED - not traced"],
     NOTRACE + [as_explained("MODEL v2.52 only USDJPY,MODEL,1,79,79,OB,CISD,2026.09.11 09:35:00")])
case("c16_cx_block_before_session", v52(ctx52b + chain52(blk79="2026.09.11 08:30"), ["2026.09.12 10:05:00"], [79]) + NEW53, V,
     ["outside its parent's lifetime in v2.52: confirmed 2026.09.11 08:30, before its session started 2026.09.11 09:05",
      "its parent row (BLK) is UNEXPLAINED above: nothing hanging on it is attributed",
      "verdicts: explained 3   PENDING_ATTRIBUTION 2   UNEXPLAINED 1", "UNEXPLAINED - not traced"],
     NOTRACE + [as_explained("BLK v2.52 only 1|2026.09.10 00:00|1.22800|1.22900|2026.09.11 09:05|1|OB|0|2026.09.11 08:30"),
                as_explained("ARM v2.52 only 1|2026.09.10 00:00|1.22800|1.22900|2026.09.11 09:05|1|OB|0|2026.09.11 08:30")])
# the D-4 exception: PA ENGULFING / REJECTION may confirm on the ARMED bar itself (n == A), nothing else may
PA_ON_A = v52(old52b, ["2026.09.11 10:00:00"], [79], names=["PA ENGULFING"]) + NEW53
case("c17_ok_pa_on_armed_bar",     PA_ON_A, V,
     ["verdicts: explained 6   PENDING_ATTRIBUTION 0   UNEXPLAINED 0", "all 6 difference(s) traced to the BOS de-dup with a concrete link"], OK_NOT)
case("c18_cx_cisd_on_armed_bar",   v52(old52b, ["2026.09.11 10:00:00"], [79]) + NEW53, V,
     ["CISD on its cycle's ARMED bar 2026.09.11 10:00: Phase 4 needs n > A", "UNEXPLAINED - not traced"], NOTRACE)
case("c19_cx_pa_armed_bar_d4_off", PA_ON_A, V + ["-NoArmedBarPA"],
     ["D-4 (PA ENGULFING / REJECTION on the ARMED bar) OFF", "-NoArmedBarPA says D-4 was off", "UNEXPLAINED - not traced"], NOTRACE)
# cycle switch on one bar: the old cycle's Phase 4 model and the new ARMED (Phase 5) share the bar
SW = [diag(SRC, "HMI-BLK,NEW", "2026.09.11 11:30", "0A52", 7, 1, extra="id=80,sess=78,dir=1,type=OB,counter=0"),
      diag(SRC, "HMI-ARM",     "2026.09.12 10:05", "0A52", 7, 1, extra="block=80,sess=78,dir=1")]
case("c20_ok_cycle_switch_same_bar", v52(ctx52b + chain52(extra=SW), ["2026.09.12 10:05:00"], [79]) + NEW53, V,
     ["verdicts: explained 8   PENDING_ATTRIBUTION 0   UNEXPLAINED 0", "all 8 difference(s) traced to the BOS de-dup with a concrete link"], OK_NOT)
case("c21_cx_model_after_cycle_closed", v52(ctx52b + chain52(extra=SW), ["2026.09.12 10:10:00"], [79]) + NEW53, V,
     ["confirmed 2026.09.12 10:10, after the ARMED 2026.09.12 10:05 that closed its cycle", "UNEXPLAINED - not traced"], NOTRACE)
# NEW_SESSION ends the old session at Phase 3, after Phase 1 made that bar's blocks
def chain_ns(blk79="2026.09.11 09:30", inst="0A52"):
    d = lambda k, bar, extra: diag(SRC, k, bar, inst, 7, 1, extra=extra)
    return [d("HMI-POI,NEW",    "2026.09.10 08:00", "id=77,dir=1,lo=1.22800,hi=1.22900,origin=2026.09.10 00:00"),
            d("HMI-POI,NEW",    "2026.09.10 12:00", "id=82,dir=1,lo=1.22600,hi=1.22700,origin=2026.09.10 04:00"),
            d("HMI-SESS,START", "2026.09.11 09:05", "id=78,poi=77,dir=1"),
            d("HMI-BLK,NEW",    blk79,              "id=79,sess=78,dir=1,type=OB,counter=0"),
            d("HMI-SESS,END",   "2026.09.11 09:30", "id=78,poi=77,dir=1,reason=NEW_SESSION"),
            d("HMI-SESS,START", "2026.09.11 09:30", "id=83,poi=82,dir=1"),
            d("HMI-BLK,NEW",    "2026.09.11 09:45", "id=84,sess=83,dir=1,type=OB,counter=0"),
            d("HMI-ARM",        "2026.09.11 10:00", "block=84,sess=83,dir=1")]
case("c22_ok_block_on_new_session_end_bar", v52(ctx52b + chain_ns(), ["2026.09.12 10:05:00"], [84]) + NEW53, V,
     ["verdicts: explained 10   PENDING_ATTRIBUTION 0   UNEXPLAINED 0", "all 10 difference(s) traced to the BOS de-dup with a concrete link"], OK_NOT)
case("c23_cx_block_after_new_session_end", v52(ctx52b + chain_ns(blk79="2026.09.11 09:35"), ["2026.09.12 10:05:00"], [84]) + NEW53, V,
     ["confirmed 2026.09.11 09:35, after its session ended 2026.09.11 09:30 (NEW_SESSION)", "UNEXPLAINED - not traced"], NOTRACE)
# A session in BOTH builds; v2.52 counts a stale low as CHOCH (v2.53 had processed it), so v2.52 ends the
# session by CONTEXT_NEUTRAL and v2.53 goes on: a block after v2.52's end is explained by it, one BEFORE it
# (the session alive in both) is not - a later end does not explain an earlier change.
D1 = ("BOS", "DOWN", "BEARISH", 1, "2026.09.07 08:00", "2026.09.06 16:00", "1.22000", "1.21900")
U1 = ("CHOCH", "UP", "TRANSITION", 0, "2026.09.08 08:00", "2026.09.07 20:00", "1.22600", "1.22700")
U2 = ("TRANS_OK", "UP", "BULLISH", 1, "2026.09.08 16:00", "2026.09.08 12:00", "1.22800", "1.22900")
XS = ("CHOCH", "DOWN", "TRANSITION", 0, "2026.09.10 12:00", "2026.09.06 04:00", "1.22100", "1.22050")     # stale low, v2.52 only
def story(inst, init, ver_new):
    d = lambda k, bar, extra: diag(SRC, k, bar, inst, 7, init, extra=extra)
    return [d("HMI-POI,NEW", "2026.09.08 20:00", "id=91,dir=1,lo=1.22500,hi=1.22600,origin=2026.09.08 12:00"),
            d("HMI-SESS,START", "2026.09.10 02:05", "id=92,poi=91,dir=1")]
def story52():
    return ([ctx(*r, inst="0A52", init=1) for r in (D1, U1, U2, XS)] + story("0A52", 1, False)
            + [diag(SRC, "HMI-SESS,END", "2026.09.10 12:05", "0A52", 7, 1, extra="id=92,poi=91,dir=1,reason=CONTEXT_NEUTRAL")])
def story53(blk93):
    d = lambda k, bar, extra: diag(SRC, k, bar, "0B53", 7, 2, extra=extra)
    return ([ctx(*D1, inst="0B53", init=2, also=1), dedup("BOS", "DOWN", D1[4], "2026.09.06 16:00@1.22000", ["2026.09.06 04:00@1.22100"], inst="0B53", init=2),
             ctx(*U1, inst="0B53", init=2, also=0), ctx(*U2, inst="0B53", init=2, also=0)] + story("0B53", 2, True)
            + [d("HMI-BLK,NEW", blk93, "id=93,sess=92,dir=1,type=OB,counter=0"),
               d("HMI-ARM", "2026.09.10 14:00", "block=93,sess=92,dir=1"),
               d("HMI-SESS,END", "2026.09.11 02:10", "id=92,poi=91,dir=1,reason=TIMEOUT")])
S52 = side("2.52", "0A52", 1, story52(), chain=False)
def S53(blk93): return side("2.53", "0B53", 2, story53(blk93), marks=MK + ["2026.09.10 15:05:00"], cycles=[100, 101, 102, 93], chain=False)
case("c24_ok_session_end_explains_later_block", S52 + S53("2026.09.10 13:30"), V,
     ["v2.52 had ended its session at 2026.09.10 12:05 (CONTEXT_NEUTRAL, explained)", "a session ends once: v2.52 had already ended it at 2026.09.10 12:05",
      "verdicts: explained 6   PENDING_ATTRIBUTION 0   UNEXPLAINED 0", "all 6 difference(s) traced to the BOS de-dup with a concrete link"], OK_NOT)
case("c25_cx_later_end_explains_earlier_block", S52 + S53("2026.09.10 12:00"), V,
     ["v2.52 ended its session only at 2026.09.10 12:05 (CONTEXT_NEUTRAL), after this block", "verdicts: explained 5   PENDING_ATTRIBUTION 1   UNEXPLAINED 0",
      "PENDING_ATTRIBUTION - a manual conclusion"], NOTRACE + [as_explained("BLK v2.53 only")])

# ---- A-61: -Ctx stale-BOS diagnostic. A continuation BOS re-counts an old level only when an earlier close of
# the leg broke that swing AFTER its confirmation and by MORE than the margin; what the log cannot settle is pending.
def margin(pts=3): return L(SRC, f"HMI: effective break margin = 0.0000{pts} price / {pts} points")
ATR = L(SRC, "HMI: break margin mode = ATR_FRAC (0.1000 x ATR14, evaluated per bar)")
LEG0 = ("BOS", "UP", "BULLISH", 1, "2026.09.08 08:00", "2026.09.07 12:00", "1.23000", "1.23100")   # leg begins, close 1.23100
def stale_case(name, e2, head, expect, forbid=()):
    case(name, [start()] + head + blk(1, extra_rows=ctx_rows([LEG0, e2], also=0)), ["-Ctx"], expect, forbid)
CTX_ONE = "of 1 continuation BOS"
NOPROOF = ["PROVEN", "1 re-count"]
def ok0(n=1): return f"A-33 stale BOS  0 suspect(s), 0 pending, of {n} continuation BOS"
CONS0 = "swing consumed twice in one build  0 proven, 0 pending"
stale_case("c26_ctx_new_structure", ("BOS", "UP", "BULLISH", 2, "2026.09.09 12:00", "2026.09.08 16:00", "1.23050", "1.23200"), [margin()],
           [ok0(), CONS0], ["1 suspect", "1 pending"])        # swing formed after the old close
stale_case("c27_ctx_within_margin", ("BOS", "UP", "BULLISH", 2, "2026.09.09 12:00", "2026.09.07 16:00", "1.23098", "1.23200"), [margin()],
           [ok0(), CONS0], ["1 suspect", "1 pending"])        # old close only 2 pt past, margin 3
# A-62: a break after the calendar estimate is a SUSPECT - the log has no H4 bar series to prove the confirmation
stale_case("c28_ctx_stale_suspect", ("BOS", "UP", "BULLISH", 2, "2026.09.09 12:00", "2026.09.07 16:00", "1.23050", "1.23200"), [margin()],
           ["A-33 stale BOS  1 suspect(s), 0 pending, " + CTX_ONE, "is 50 pt past it (> margin 3) and not before its earliest possible confirmation",
            "confirmed only if no H4 bar is missing in between", CONS0], NOPROOF)
LEGW = ("BOS", "UP", "BULLISH", 1, "2026.09.07 08:00", "2026.09.04 08:00", "1.23000", "1.23100")   # Monday close, weekend before it
case("c29_ctx_stale_weekend", [start(), margin()] + blk(1, extra_rows=ctx_rows([LEGW, ("BOS", "UP", "BULLISH", 2, "2026.09.08 12:00", "2026.09.04 16:00", "1.23050", "1.23200")], also=0)),
     ["-Ctx"], ["A-33 stale BOS  1 suspect(s), 0 pending, " + CTX_ONE], NOPROOF)
LEGW3 = ("BOS", "UP", "BULLISH", 1, "2026.09.09 08:00", "2026.09.04 08:00", "1.23000", "1.23100")   # Wednesday close, > 72 h after the estimate
case("c39_ctx_weekend_over_72h", [start(), margin()] + blk(1, extra_rows=ctx_rows([LEGW3, ("BOS", "UP", "BULLISH", 2, "2026.09.10 12:00", "2026.09.04 16:00", "1.23050", "1.23200")], also=0)),
     ["-Ctx"], ["A-33 stale BOS  1 suspect(s), 0 pending, " + CTX_ONE], NOPROOF)
stale_case("c30_ctx_atr_margin",    ("BOS", "UP", "BULLISH", 2, "2026.09.09 12:00", "2026.09.07 16:00", "1.23050", "1.23200"), [ATR],
           ["A-33 stale BOS  0 suspect(s), 1 pending, " + CTX_ONE, "the margin is per bar (ATR)"], NOPROOF)
stale_case("c31_ctx_no_margin_line", ("BOS", "UP", "BULLISH", 2, "2026.09.09 12:00", "2026.09.07 16:00", "1.23050", "1.23200"), [],
           ["A-33 stale BOS  0 suspect(s), 1 pending, " + CTX_ONE, "the margin is not in the log"], NOPROOF)
# bear side of the two false-positive shapes (mirror): the 2nd BOS's swing formed after the leg's first close;
# the 3rd BOS's swing was confirmed before the 2nd close, which reached only 2 pt past it (margin 3)
LEGD = ("BOS", "DOWN", "BEARISH", 1, "2026.09.08 08:00", "2026.09.07 12:00", "1.23000", "1.22900")
case("c32_ctx_bear_mirror", [start(), margin()] + blk(1, extra_rows=ctx_rows([LEGD, ("BOS", "DOWN", "BEARISH", 2, "2026.09.09 12:00", "2026.09.08 16:00", "1.22950", "1.22800"),
                                                                                ("BOS", "DOWN", "BEARISH", 3, "2026.09.10 12:00", "2026.09.08 20:00", "1.22802", "1.22700")], also=0)),
     ["-Ctx"], [ok0(2)], ["1 suspect", "1 pending"])
# A-62: a price the log does not carry as a finite number is unknown - pending, never read as 0
stale_case("c33_ctx_swing_px_empty", ("BOS", "UP", "BULLISH", 2, "2026.09.09 12:00", "2026.09.07 16:00", "", "1.23200"), [margin()],
           ["A-33 stale BOS  0 suspect(s), 1 pending, " + CTX_ONE, "swing_px '' is missing or not a number"], NOPROOF)
stale_case("c34_ctx_swing_px_bad", ("BOS", "UP", "BULLISH", 2, "2026.09.09 12:00", "2026.09.07 16:00", "BAD", "1.23200"), [margin()],
           ["A-33 stale BOS  0 suspect(s), 1 pending, " + CTX_ONE, "swing_px 'BAD' is missing or not a number"], NOPROOF)
LEGN = LEG0[:7] + ("NaN",)
case("c35_ctx_close_nan", [start(), margin()] + blk(1, extra_rows=ctx_rows([LEGN, ("BOS", "UP", "BULLISH", 2, "2026.09.09 12:00", "2026.09.07 16:00", "1.23050", "1.23200")], also=0)),
     ["-Ctx"], ["A-33 stale BOS  0 suspect(s), 1 pending, " + CTX_ONE, "close 'NaN' at 2026.09.08 08:00 is missing or not a number"], NOPROOF)
# A-62: the proof the log can give - one build consuming the same swing twice
SW_S = ("2026.09.07 12:00", "1.23000")
case("c36_ctx_consumed_twice", [start(), margin()] + blk(1, extra_rows=ctx_rows([LEG0, ("BOS", "UP", "BULLISH", 2, "2026.09.09 12:00") + SW_S + ("1.23200",)], also=0)),
     ["-Ctx"], ["swing consumed twice in one build  1 proven, 0 pending  (1 of 1 build(s) COMPLETE and read)", "PROVEN   2026.09.09 12:00 BOS re-uses swing 2026.09.07 12:00 @ 1.23000 (UP), consumed at 2026.09.08 08:00"])
case("c37_ctx_dedup_then_primary", [start(), margin()] + blk(1, extra_rows=[ctx(*LEG0, also=1), dedup("BOS", "UP", LEG0[4], "2026.09.07 12:00@1.23000", ["2026.09.06 20:00@1.22950"]),
                                                                            ctx("BOS", "UP", "BULLISH", 2, "2026.09.09 12:00", "2026.09.06 20:00", "1.22950", "1.23200", also=0)]),
     ["-Ctx"], ["swing consumed twice in one build  1 proven, 0 pending", "re-uses swing 2026.09.06 20:00 @ 1.22950 (UP), consumed at 2026.09.08 08:00"])
case("c38_ctx_same_swing_two_builds", [start()] + blk(1, extra_rows=ctx_rows([LEG0], also=0)) + blk(2, extra_rows=ctx_rows([LEG0], also=0)),
     ["-Ctx"], ["swing consumed twice in one build  0 proven, 0 pending  (2 of 2 build(s) COMPLETE and read)"], ["PROVEN"])

# A-63: PROVEN only from a COMPLETE build and valid records; anything else is pending with its reason
E2T = ("BOS", "UP", "BULLISH", 2, "2026.09.09 12:00") + SW_S + ("1.23200",)       # re-uses LEG0's swing
NOT_PROVEN = ["PROVEN", "1 proven"]
def twice(**kw): return [start(), margin()] + blk(1, **kw)
case("c40_ctx_twice_other_identity", twice(extra_rows=[ctx(*LEG0, also=0), ctx(*E2T, also=0, run=8, init=2)]), ["-Ctx"],
     ["swing consumed twice in one build  0 proven, 1 pending  (0 of 1 build(s) COMPLETE and read)",
      "INCOMPLETE: 1 row(s) carry another run/init than the BEGIN (HMI-CTX) - not read as proof, 1 candidate re-use(s) in it"], NOT_PROVEN)
case("c41_ctx_twice_end_build", twice(extra_rows=ctx_rows([LEG0, E2T], also=0), end_kw={"b": 99}), ["-Ctx"],
     ["swing consumed twice in one build  0 proven, 1 pending", "INCOMPLETE: END build=99, BEGIN build=1 - not read as proof"], NOT_PROVEN)
case("c42_ctx_twice_no_end", twice(extra_rows=ctx_rows([LEG0, E2T], also=0), with_end=False), ["-Ctx"],
     ["swing consumed twice in one build  0 proven, 1 pending", "INCOMPLETE: no END (the log ends inside build 1) - not read as proof"], NOT_PROVEN)
case("c43_ctx_twice_px_bad", twice(extra_rows=ctx_rows([LEG0[:6] + ("BAD",) + LEG0[7:], E2T[:6] + ("BAD",) + E2T[7:]], also=0)), ["-Ctx"],
     ["swing consumed twice in one build  0 proven, 2 pending  (1 of 1 build(s) COMPLETE and read)",
      "2026.09.08 08:00 BOS consumption record not valid (swing price 'BAD') - left out of the consumed set",
      "2026.09.09 12:00 BOS consumption record not valid (swing price 'BAD')"], NOT_PROVEN)
E2D = ("BOS", "UP", "BULLISH", 2, "2026.09.09 12:00", "2026.09.06 20:00", "1.22950", "1.23200")   # re-uses the de-dup swing of c37
case("c44_ctx_dedup_entry_bad", twice(extra_rows=[ctx(*LEG0, also=1), dedup("BOS", "UP", LEG0[4], "2026.09.07 12:00@1.23000", ["2026.09.06 20:00@BAD"]),
                                                   ctx(*E2D, also=0)]), ["-Ctx"],
     ["swing consumed twice in one build  0 proven, 1 pending", "de-dup entry '2026.09.06 20:00@BAD' not valid (swing price 'BAD')"], NOT_PROVEN)
case("c45_ctx_dedup_missing", twice(extra_rows=[ctx(*LEG0, also=1), ctx(*E2D, also=0)]), ["-Ctx"],
     ["swing consumed twice in one build  0 proven, 1 pending", "2026.09.08 08:00 CTX processed also=1 other swing(s) but the build has no de-dup list for it"], NOT_PROVEN)
case("c46_ctx_dedup_count", twice(extra_rows=[ctx(*LEG0, also=2), dedup("BOS", "UP", LEG0[4], "2026.09.07 12:00@1.23000", ["2026.09.06 20:00@1.22950"], also=2)]), ["-Ctx"],
     ["swing consumed twice in one build  0 proven, 2 pending", "de-dup row says also='2' but lists 1 swing(s)", "CTX says also=2, its de-dup list has 1"], NOT_PROVEN)
LEGACY_END = {"drop": ("liq", "liqev", "unknown", "liqwait")}
case("c47_ctx_twice_legacy_no_identity", [start("2.48", run=None), margin()] + blk(1, ver="2.48", run=None, init=None, end_kw=LEGACY_END,
                                                                                 extra_rows=ctx_rows([LEG0, E2T], also=0, run=None, init=None)), ["-Ctx"],
     ["swing consumed twice in one build  0 proven, 1 pending", "no run/init identity (v2.48 log) - not read as proof, 1 candidate re-use(s) in it"], NOT_PROVEN)

# v2.54 (BRI-12 P-4): HMI-CTX-INTERNAL rows consume swings too - a later re-use is a proof, an invalid one pending
def internal(d, bar, sw, px, close, swings=(), also=None, prot="1.22950", inst="0001", run=7, init=1, src=SRC):
    return L(src, f"HMI-CTX-INTERNAL,USDJPY,dir={d},live=0,ctx=BULLISH,bar={bar},swing={sw},swing_px={px},close={close},"
                  f"also={len(swings) if also is None else also},swings={'|'.join(swings)},prot={prot}" + tail(inst, run, init))
I_SW = ("2026.09.08 16:00", "1.23020")
CH_I = ("CHOCH", "DOWN", "TRANSITION", 0, "2026.09.10 12:00") + I_SW + ("1.22900",)
def twice54(rows): return [start("2.54"), margin()] + blk(1, ver="2.54", extra_rows=rows)
case("c48_ctx_internal_then_choch", twice54([ctx(*LEG0, also=0), internal("DOWN", "2026.09.09 08:00", *I_SW, "1.23010"), ctx(*CH_I, also=0)]), ["-Ctx"],
     ["swing consumed twice in one build  1 proven, 0 pending",
      "PROVEN   2026.09.10 12:00 CHOCH re-uses swing 2026.09.08 16:00 @ 1.23020 (DOWN), consumed at 2026.09.09 08:00"])
case("c49_ctx_internal_px_bad", twice54([ctx(*LEG0, also=0), internal("DOWN", "2026.09.09 08:00", I_SW[0], "BAD", "1.23010"), ctx(*CH_I, also=0)]), ["-Ctx"],
     ["swing consumed twice in one build  0 proven, 1 pending", "internal record '2026.09.08 16:00@BAD' not valid (swing price 'BAD')"], NOT_PROVEN)
case("c50_ctx_internal_count", twice54([ctx(*LEG0, also=0), internal("DOWN", "2026.09.09 08:00", *I_SW, "1.23010", swings=["2026.09.08 04:00@1.23040"], also=2)]), ["-Ctx"],
     ["swing consumed twice in one build  0 proven, 1 pending", "internal row says also='2' but lists 1 swing(s)"], NOT_PROVEN)
case("c51_ctx_internal_list_reused", twice54([ctx(*LEG0, also=0), internal("DOWN", "2026.09.09 08:00", *I_SW, "1.23010", swings=["2026.09.08 04:00@1.23040"]),
                                               ctx("CHOCH", "DOWN", "TRANSITION", 0, "2026.09.10 12:00", "2026.09.08 04:00", "1.23040", "1.22900", also=0)]), ["-Ctx"],
     ["swing consumed twice in one build  1 proven, 0 pending", "re-uses swing 2026.09.08 04:00 @ 1.23040 (DOWN), consumed at 2026.09.09 08:00"])
case("c52_ctx_internal_ok", twice54([ctx(*LEG0, also=0), internal("DOWN", "2026.09.09 08:00", *I_SW, "1.23010", swings=["2026.09.08 04:00@1.23040"])]), ["-Ctx"],
     ["swing consumed twice in one build  0 proven, 0 pending  (1 of 1 build(s) COMPLETE and read)"], NOT_PROVEN)

# v2.54r2 (reviewer P1): a level installed by the very close that broke it is a log-provable defect
def prot(tag, ev, d, bar, level, inst="0001", run=7, init=1, src=SRC, leg=1, live=0):
    return L(src, f"{tag},USDJPY,{ev},dir={d},live={live},leg={leg},bar={bar},level={level},swing=2026.09.09 08:00,confirm=2026.09.10 00:00,"
                  f"bos={bar},age=3,prev=NA,cand={level}" + tail(inst, run, init))
PB = "2026.09.10 08:00"
def installed(d, close, level, head):
    sw = ("2026.09.08 12:00", "1.00140") if d == "UP" else ("2026.09.08 12:00", "1.19860")
    rows = [ctx("BOS", d, "BULLISH" if d == "UP" else "BEARISH", 2, PB, *sw, close, also=0),
            prot("HMI-PROT", "ADVANCE", d, PB, level), prot("HMI-ANCHOR", "MOVE", d, PB, level)]
    return [start("2.54")] + head + blk(1, ver="2.54", extra_rows=rows)
case("c53_prot_installed_broken", installed("UP", "1.00143", "1.00146", [margin(1)]), ["-Ctx"],
     ["level installed already broken  2 proven, 0 pending  (2 SET / ADVANCE / MOVE row(s))",
      "2026.09.10 08:00 HMI-PROT ADVANCE level 1.00146 (UP leg) - the close 1.00143 of that bar is 3 pt past it (> margin 1): installed already broken"])
case("c54_prot_installed_broken_bear", installed("DOWN", "1.19857", "1.19854", [margin(1)]), ["-Ctx"],
     ["level installed already broken  2 proven, 0 pending", "HMI-ANCHOR MOVE level 1.19854 (DOWN leg) - the close 1.19857 of that bar is 3 pt past it"])
case("c55_prot_installed_within_margin", installed("UP", "1.00143", "1.00146", [margin(3)]), ["-Ctx"],
     ["level installed already broken  0 proven, 0 pending  (2 SET / ADVANCE / MOVE row(s))"], ["installed already broken  1", "installed already broken  2"])
case("c56_prot_installed_atr", installed("UP", "1.00143", "1.00146", [ATR]), ["-Ctx"],
     ["level installed already broken  0 proven, 2 pending", "close 1.00143 is 3 pt past it, the margin is per bar (ATR)"], ["installed already broken  1", "installed already broken  2"])
case("c57_prot_installed_ok", installed("UP", "1.00143", "1.00045", [margin(1)]), ["-Ctx"],
     ["level installed already broken  0 proven, 0 pending"], ["PROVEN"])

# v2.54: PROT / ANCHOR / INTERNAL rows are a judged category in the reload and live-vs-build comparisons
def prows(level="1.00045", leg=1, **kw):
    return [prot("HMI-PROT", "SET", "UP", PB, level, leg=leg, **kw), prot("HMI-ANCHOR", "SET", "UP", PB, level, leg=leg, **kw),
            internal("DOWN", PB, *I_SW, "1.23010", **{k: v for k, v in kw.items() if k in ("run", "init", "inst")})]
R54 = lambda b, rows, **kw: blk(b, ver="2.54", extra_rows=rows, **kw)
case("p01_reload_prot_identical", [start("2.54")] + R54(1, prows()) + R54(2, prows()), R,
     ["PROT   IDENTICAL over 3 / 3 row(s) (PROT / ANCHOR / INTERNAL)", "IDENTICAL inside the comparable region"])
case("p02_reload_prot_mismatch", [start("2.54")] + R54(1, prows()) + R54(2, prows(level="1.00050")), R,
     ["PROT   MISMATCH (4)", "differ INSIDE the comparable region", "A only  PROT HMI-PROT|SET|"], ["IDENTICAL inside"])
case("p03_reload_prot_leg_only", [start("2.54")] + R54(1, prows()) + R54(2, prows(leg=2)), R,
     ["PROT   same rows, leg numbered differently on 2 - PENDING REVIEW", "PENDING REVIEW, not a pass",
      "2 protected-level row(s) the same but for the leg number"], ["IDENTICAL inside", "PROT   MISMATCH"])
case("p04_reload_prot_none_v254", [start("2.54")] + R54(1, []) + R54(2, []), R,
     ["PROT   no row on either side (nothing judged)"], ["PROT   IDENTICAL"])
PL = "2026.09.30 13:00"
lprot = prot("HMI-PROT", "ADVANCE", "UP", PL, "1.00045", live=1, leg=4)
def b2p(rows): return blk(2, init=2, to="2026.09.30 14:00", marks=MK + ["2026.09.30 13:05:00"], extra_rows=rows)
case("p05_live_prot_ok", [start()] + blk(1) + [live_ok, lprot] + [start(init=2)] + b2p([prot("HMI-PROT", "ADVANCE", "UP", PL, "1.00045", init=2, leg=4)]),
     ["-LiveVsBuild"], ["protected-level rows compared: 1 (PROT / ANCHOR / INTERNAL)", "AGREE BOTH WAYS on every covered bar"], ["MISMATCH(ES)", "leg number"])
case("p06_live_prot_missing", [start()] + blk(1) + [live_ok, lprot] + [start(init=2)] + b2p([]),
     ["-LiveVsBuild"], ["MISMATCH(ES) on covered bars", "live only  [1->2] PROT HMI-PROT|ADVANCE|"], ["AGREE BOTH WAYS"])
case("p07_live_prot_leg_only", [start()] + blk(1) + [live_ok, lprot] + [start(init=2)] + b2p([prot("HMI-PROT", "ADVANCE", "UP", PL, "1.00045", init=2, leg=1)]),
     ["-LiveVsBuild"], ["AGREE BOTH WAYS on every covered bar", "1 protected-level row(s) agree but for the leg number - PENDING REVIEW"], ["MISMATCH(ES)"])
case("p08_live_prot_other_id", [start()] + blk(1) + [live_ok, prot("HMI-PROT", "ADVANCE", "UP", PL, "1.00045", live=1, init=9)] + [start(init=2)]
     + b2p([prot("HMI-PROT", "ADVANCE", "UP", PL, "1.00045", init=2)]),
     ["-LiveVsBuild"], ["from another run/init than build 1 1", "nothing comparable yet - no PASS can be given."], ["AGREE BOTH WAYS"])

# ---- v2.54 (BRI-12) cross-version attribution: the offline model's runs written as logs. ReloadTest -Versus
# must give exactly the model's verdicts (tools/h4_protect_attr.py); tampered v2.54 logs must not pass.
import sys as _sys
_sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import h4_protect_attr as PA, h4_dedup_sim as HB, h4_protect_sim as HP          # noqa: E402
SB = PA.synth_bars(700, 37)
LINES, VM = PA.emit_case(SB)
VS = ["-Source", "USDJPY#0A53,M5", "-Versus", "USDJPY#0B54,M5"]
NOT_TRACED = ["traced to BRI-12 (protected level / new structure) with a concrete link"]
def vcase(name, lines, expect, forbid=()):
    os.makedirs(name, exist_ok=True)
    open(os.path.join(name, "20261002.log"), "w", encoding="utf-8").write("\n".join(lines) + "\n")
    C[name] = dict(args=VS, expect=expect, forbid=list(forbid))
vcase("v01_versus254_model", LINES,
      [f"verdicts: explained {VM['explained']}   PENDING_ATTRIBUTION 0   UNEXPLAINED 0",
       f"all {VM['explained']} difference(s) traced to BRI-12 (protected level / new structure) with a concrete link",
       "CTX P-4 protected level / internal", "CTX P-5 old structure"], ["PENDING_ATTRIBUTION - a manual", "UNEXPLAINED - not traced"])
_old, _new = HB.run(SB, True), HP.run254(SB)
_V = PA.attribute254(_old, _new)
def _is54(l): return "inst=0B54" in l
def _bar(l): return l.split("bar=")[1].split(",")[0]
def drop(pred):
    out, done = [], False
    for l in LINES:
        if not done and _is54(l) and pred(l): done = True; continue
        out.append(l)
    assert done; return out
def edit(pred, fn):
    out, done = [], False
    for l in LINES:
        if not done and _is54(l) and pred(l): l = fn(l); done = True
        out.append(l)
    assert done; return out
_tI = next(w.split(" only ")[1].split(" CHOCH")[0] for (w, why) in _V["explained"] if "HMI-CTX-INTERNAL" in why)   # bar of a v2.53 CHOCH that INTERNAL explains
vcase("v02_versus254_internal_removed", drop(lambda l: "HMI-CTX-INTERNAL," in l and _bar(l) == _tI),
      ["states equal going in, and no BRI-12 row on this bar links it", "the divergence start is not explained"], NOT_TRACED)
def _prot_broken(l):
    c = float(l.split("close=")[1].split(",")[0]); d = l.split("dir=")[1].split(",")[0]
    return l.replace("prot=" + l.split("prot=")[1].split(",")[0], "prot=" + f"{c + (0.0001 if d == 'DOWN' else -0.0001):.5f}")
vcase("v03_versus254_internal_prot_broken", edit(lambda l: "HMI-CTX-INTERNAL," in l and "prot=NA" not in l, _prot_broken),
      ["pt past the protected level", "that close is a CHOCH", "UNEXPLAINED - not traced"], NOT_TRACED)
vcase("v04_versus254_break_level", edit(lambda l: l.split("  ")[-1].startswith("HMI-PROT,USDJPY,BREAK,"),
                                        lambda l: l.replace("level=" + l.split("level=")[1].split(",")[0], "level=9.99999")),
      ["is not the CHOCH swing", "UNEXPLAINED - not traced"], NOT_TRACED)
vcase("v05_versus254_choch_no_prot", drop(lambda l: l.split("  ")[-1].startswith("HMI-PROT,USDJPY,BREAK,")),
      ["a v2.54 CHOCH without HMI-PROT BREAK / FALLBACK on its bar", "UNEXPLAINED - not traced"], NOT_TRACED)
_sl = next(r for r in _new.ctx_rows if r["kind"] == "TRANS_SAMELEG")
_tch = max(r["bar"] for r in _new.ctx_rows if r["kind"] == "CHOCH" and r["bar"] < _sl["bar"])
vcase("v06_versus254_sameleg_late", edit(lambda l: ",TRANS_SAMELEG," in l and _bar(l) == HB.tstr(_sl["bar"]),
                                         lambda l: l.replace("swing=" + HB.tstr(_sl["swing"]), "swing=" + HB.tstr(_tch))),
      ["TRANS_SAMELEG on a swing formed at / after the CHOCH close", "UNEXPLAINED - not traced"], NOT_TRACED)
vcase("v07_versus254_messy_flip", edit(lambda l: "HMI-CTX,USDJPY,BOS," in l and "messy=0" in l and "str=1," not in l,
                                       lambda l: l.replace("messy=0", "messy=1")),
      ["but the rule gives 0 from this build's own events", "UNEXPLAINED - not traced"], NOT_TRACED)
_fb = next(p for p in _new.prot_rows if p["ev"] == "FALLBACK")
vcase("v08_versus254_fallback_with_level", edit(lambda l: l.split("  ")[-1].startswith("HMI-PROT,USDJPY,INVALID,") and f"leg={_fb['leg']}," in l,
                                                lambda l: l.replace("level=NA", "level=1.10000")),
      ["P-6b applies to an INVALID leg only", "UNEXPLAINED - not traced"], NOT_TRACED)
# A-68: the compared region starts after the H4 history - a POI made before it in one build only must still
# explain its OUT / EXPIRED / INVALID inside it (creation judged silently by the same rule)
LINES_W, _ = PA.emit_case(SB, warm_idx=250)
vcase("v09_versus254_poi_before_region", LINES_W,
      ["PENDING_ATTRIBUTION 0   UNEXPLAINED 0", "traced to BRI-12 (protected level / new structure) with a concrete link"],
      ["PENDING_ATTRIBUTION - a manual", "UNEXPLAINED - not traced"])
# A-67: -Ctx keeps each instance's own chain; two instances of one symbol must not be read as one leg,
# and each instance's break margin is its own (the margin notice follows its "starting on" line)
B2 = ("BOS", "UP", "BULLISH", 1, "2026.09.08 04:00", "2026.09.06 12:00", "1.22900", "1.22950")
B3 = ("BOS", "UP", "BULLISH", 2, "2026.09.09 12:00", "2026.09.07 16:00", "1.23050", "1.23200")
TWO = ([start("2.53", "0A53", 7, 1), margin()] + blk(1, ver="2.53", inst="0A53", init=1, extra_rows=ctx_rows([LEG0], also=0, inst="0A53", init=1))
       + [start("2.54", "0B54", 7, 2), ATR] + blk(1, ver="2.54", inst="0B54", init=2, extra_rows=ctx_rows([B2, B3], also=0, inst="0B54", init=2)))
case("c58_ctx_two_instances", TWO, ["-Ctx"],
     ["USDJPY#0A53", "USDJPY#0B54", "A-33 stale BOS  0 suspect(s), 0 pending, of 1 continuation BOS  (margin per bar (ATR)"],
     ["1 suspect", "SUSPECT"])

# strength number only: same event, same swing, same state, str counted from another H4 start
same_s = ctx_rows([E1, E3[:3] + (5,) + E3[4:]], also=0)
case("c09_ctx_strength_only", [start()] + blk(1, extra_rows=same) + blk(2, extra_rows=same_s), R,
     ["same events, strength numbered differently on 1 - PENDING REVIEW", "PENDING REVIEW, not a pass"], ["IDENTICAL inside", "CTX    MISMATCH"])
bctx_s = ctx(*E3[:3], 7, "2026.09.30 13:00", *E3[5:], live=0, also=0, init=2)
b2s = blk(2, init=2, to="2026.09.30 14:00", marks=MK + ["2026.09.30 13:05:00"], extra_rows=[bctx_s])
case("c10_live_ctx_strength_only", [start()] + blk(1) + [live_ok, lctx] + [start(init=2)] + b2s, ["-LiveVsBuild"],
     ["AGREE BOTH WAYS on every covered bar", "1 H4 event(s) agree on swing and state but not on the strength number"], ["MISMATCH(ES)"])

# ---- v2.55 BRI-08: -Versus v2.54 -> v2.55, the B8 category in reload and live vs build ----------------------------
# The logs come from tools/bri08_sim.py: every scenario of docs/02 "BRI-08 修订稿 2" in one ladder series, its v2.54 and
# v2.55 builds as the MQL writes them (ARM, HMI-REF, MODEL, HMI-BRK). ladder_check() proves each scenario gives in the
# series what it gives alone; the expected verdict counts are the scenario table's (expected_verdicts()).
import bri08_sim as B8                                                                  # noqa: E402
SER, SPANS = B8.ladder(B8.SCEN)
V8 = ["-Source", "USDJPY#0B54,M5", "-Versus", "USDJPY#0C55,M5"]
NOT8 = ["traced to BRI-08 (first effective close) with a concrete link"]
def b8pair(d, v54=None, v55=None):
    a = B8.emit_build(SER, d, "2.54", "0B54", 1); b = B8.emit_build(SER, d, "2.55", "0C55", 2)
    return (v54(a) if v54 else a) + (v55(b) if v55 else b)
def b8case(name, lines, expect, forbid=(), args=V8):
    os.makedirs(name, exist_ok=True)
    open(os.path.join(name, "20261002.log"), "w", encoding="utf-8").write("\n".join(lines) + "\n")
    C[name] = dict(args=args, expect=expect, forbid=list(forbid))
for d, nm in ((1, "bull"), (-1, "bear")):
    B8.ladder_check(SER, SPANS, d)
    ev = B8.expected_verdicts(SER, d); tot = sum(ev.values())
    b8case(f"e0{1 if d > 0 else 2}_versus255_{nm}", b8pair(d),
           [f"verdicts: explained {tot}   PENDING_ATTRIBUTION 0   UNEXPLAINED 0", f"all {tot} difference(s) traced to BRI-08 (first effective close) with a concrete link",
            f"    {'B8-C5':<12} {ev['C5']:>4}", f"    {'B8-SLOW':<12} {ev['SLOW']:>4}", f"    {'B8-SHIFT':<12} {ev['SHIFT']:>4}", f"    {'B8-NA':<12} {ev['NA']:>4}",
            "other rows that differ: 0"], ["UNEXPLAINED - not traced", "NOT JUDGED"])
def one(pred, fn):                       # change the first line pred() picks, exactly once
    def f(lines):
        out, done = [], False
        for l in lines:
            if not done and pred(l): l = fn(l); done = True
            if l is not None: out.append(l)
        assert done; return out
    return f
def fld(l, k): return l.split(f",{k}=")[1].split(",")[0]
def setf(l, k, v): return l.replace(f",{k}={fld(l, k)},", f",{k}={v},", 1)
_slow = lambda l: l.split("  ")[-1].startswith("HMI-BRK,") and fld(l, "prev_close") > fld(l, "level")          # bull: prev past the level
b8case("e03_versus255_prev_not_in_zone", b8pair(1, v55=one(_slow, lambda l: setf(l, "prev_close", fld(l, "level")))),
       ["is not between the level", "v2.54 would confirm on this bar too", "UNEXPLAINED - not traced to BRI-08"], NOT8)
b8case("e04_versus255_na_brk_not_beyond", b8pair(1, v55=one(lambda l: "state=NA_BROKEN" in l, lambda l: setf(l, "brk_close", fld(l, "cand_level")))),
       ["NA_BROKEN, but brk_close", "UNEXPLAINED - not traced to BRI-08"], NOT8)
_c5 = lambda l: ",MSS," in l and "HMI-REF," in l and "c5diff=-" not in l
b8case("e05_versus255_c5diff_missing", b8pair(1, v55=one(_c5, lambda l: l.replace(",c5diff=" + l.split(",c5diff=")[1].split(",")[0], ",c5diff=-"))),
       ["without a c5diff entry that decides it", "UNEXPLAINED - not traced to BRI-08"], NOT8)
def _c5bad(l):
    e = l.split(",c5diff=")[1].split(",")[0].split(";")[0]; parts = e.split("/")      # time@px / chk / close / mp / oXnY
    parts[3] = "0" if parts[4] == "o1n0" else str(int(parts[3]) + 20)                      # make its own-margin judgement flip
    return l.replace(",c5diff=" + e, ",c5diff=" + "/".join(parts))
b8case("e06_versus255_c5diff_arith", b8pair(1, v55=one(_c5, _c5bad)), ["does not hold", "UNEXPLAINED - not traced to BRI-08"], NOT8)
b8case("e07_versus255_other_row", b8pair(1, v55=one(lambda l: "HMI-ARM," in l, lambda l: l.replace("sess=60", "sess=61"))),
       ["BRI-08 changes CISD / MSS only: this row must be the same in both builds", "UNEXPLAINED - not traced to BRI-08"], NOT8)
b8case("e08_versus255_brk_missing", b8pair(1, v55=one(lambda l: "HMI-BRK," in l, lambda l: None)),
       ["no HMI-BRK row for this confirmation", "UNEXPLAINED - not traced to BRI-08"], NOT8)
# B8-SHIFT whose v2.54 row is moved EARLIER than v2.55's: not the re-cross
_sh = B8.process(SER, 1, False)
_t = lambda i: (__import__("datetime").datetime(2026, 9, 10) + __import__("datetime").timedelta(minutes=5 * i)).strftime("%Y.%m.%d %H:%M")
_e4 = {(c, m): n for (c, m, n) in _sh[0]}; _e5 = {(c, m): n for (c, m, n) in B8.process(SER, 1, True)[0]}
_k = next(k for k in _e4 if k in _e5 and _e4[k] > _e5[k])
_row = f"OB,{_k[1]},{_t(_e4[_k] + 1)}:00"
b8case("e09_versus255_shift_earlier", b8pair(1, v54=one(lambda l: _row in l and f",{100 + _k[0]},{100 + _k[0]}," in l,
                                                          lambda l: l.replace(_row, f"OB,{_k[1]},{_t(_e5[_k] - 1)}:00"))),
       ["not the later re-cross of the same reference", "UNEXPLAINED - not traced to BRI-08"], NOT8)
b8case("e10_versus255_window_moved", b8pair(1, v55=one(lambda l: "HMI-BUILD-BEGIN," in l, lambda l: setf(l, "from", "2026.09.09 23:55"))),
       ["NOT JUDGED - the two builds start at different bars", "NOT JUDGED (window moved), not a pass"], NOT8)
b8case("e11_versus255_ref_missing", b8pair(1, v55=one(lambda l: "HMI-REF," in l and ",CISD," in l, lambda l: None)),
       ["no HMI-REF CISD row for this cycle", "UNEXPLAINED - not traced to BRI-08"], NOT8)
b8case("e12_versus255_model_level", b8pair(1, v55=one(lambda l: ",MODEL," in l and ",CISD," in l,
                                                      lambda l: l.replace("," + l.split(",")[-4] + ",inst=", ",1.29999,inst="))),
       ["are not HMI-REF's", "UNEXPLAINED - not traced to BRI-08"], NOT8)
# reload (same version) and live vs build: HMI-REF / HMI-BRK are a judged category (B8)
def trunc(n): return dict(bars=SER["bars"][:n], margin=SER["margin"][:n], armed=[a for a in SER["armed"] if a < n], A=SER["armed"][0])
R8 = ["-Source", "USDJPY,M5"]
b1, b2 = B8.emit_build(SER, 1, "2.55", "0C55", 2, build=1), B8.emit_build(SER, 1, "2.55", "0C55", 2, build=2)
b8case("e13_reload255_identical", b1 + b2[1:], ["B8     IDENTICAL over", "IDENTICAL inside the comparable region"], ["MISMATCH"], R8)
b8case("e14_reload255_ref_changed", b1 + one(lambda l: "HMI-REF," in l, lambda l: setf(l, "armed_mp", "9"))(b2[1:]),
       ["B8     MISMATCH (2)", "differ INSIDE the comparable region"], ["IDENTICAL inside"], R8)
X, Y = 60, 175
lb1 = B8.emit_build(trunc(X + 1), 1, "2.55", "0C55", 2, build=1)
lb2 = B8.emit_build(trunc(Y + 1), 1, "2.55", "0C55", 2, build=2)
def _live(lines):
    out = []
    for l in lines:
        p = l.split("  ")[-1]
        if p.startswith(("HMI-REF,", "HMI-BRK,")):
            t = (fld(l, "armed") if p.startswith("HMI-REF,") else fld(l, "bar"))
            out.append((t, l.replace(",live=0,", ",live=1,")))
        elif p.startswith("HMI-BUILD,") and ",MODEL," in p:
            out.append((p.split(",")[7][:16], l.replace("HMI-BUILD,", "HMI-LIVE,")))
    lo = _t(X + 1)                                            # rows of bars after build 1's last bar
    return [l for (t, l) in out if t >= lo]
LIVE = _live(lb2[2:-1])
assert any("HMI-BRK," in l for l in LIVE) and any("HMI-REF," in l for l in LIVE)
b8case("e15_live255_ok", lb1 + LIVE + lb2[1:], ["BRI-08 rows compared:", "AGREE BOTH WAYS on every covered bar"], ["MISMATCH(ES)"], ["-LiveVsBuild"])
b8case("e16_live255_brk_missing", lb1 + one(lambda l: "HMI-BRK," in l, lambda l: None)(LIVE) + lb2[1:],
       ["MISMATCH(ES) on covered bars", "build only [1->2] B8 HMI-BRK"], ["AGREE BOTH WAYS"], ["-LiveVsBuild"])

json.dump(C, open("cases.json", "w"), indent=1)
print(len(C), "cases")
