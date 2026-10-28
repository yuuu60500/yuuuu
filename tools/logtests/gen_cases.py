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

# r2 (review of the v2.55 dev, 2026-10-20): a CISD / MSS MODEL row must sit inside its cycle and be the only one
# of its model in that cycle - in both builds - before anything is attributed (ChainLife + one row per cycle and model)
import datetime as _dt
def _plus(t16, m): return (_dt.datetime.strptime(t16, "%Y.%m.%d %H:%M") + _dt.timedelta(minutes=m)).strftime("%Y.%m.%d %H:%M")
_b55 = B8.emit_build(SER, 1, "2.55", "0C55", 2)
_arm = {fld(l, "block"): fld(l, "bar") for l in _b55 if "HMI-ARM," in l}
_m101 = next(l for l in _b55 if ",MODEL,1,101,101,OB,CISD," in l)
_t101 = _m101.split("  ")[-1].split(",")[8]                    # the confirming bar's close, with seconds
def move101(close16):                                          # move cycle 101's v2.55 CISD (MODEL + BRK) to another bar
    def f(lines):
        out = []
        for l in lines:
            if l == _m101:
                l = l.replace(_t101, close16 + ":00")
            elif "HMI-BRK," in l and "cycle=101," in l and ",CISD," in l:
                l = setf(setf(l, "bar", _plus(close16, -5)), "prev_bar", _plus(close16, -10))
            out.append(l)
        return out
    return f
b8case("e17_versus255_confirm_on_armed", b8pair(1, v55=move101(_arm["101"])),
       ["CISD on its cycle's ARMED bar", "Phase 4 needs n > A", "UNEXPLAINED - not traced to BRI-08"], NOT8)
b8case("e18_versus255_confirm_after_next_armed", b8pair(1, v55=move101(_plus(_arm["102"], 5))),
       ["after the ARMED", "that closed its cycle (Rule 15", "UNEXPLAINED - not traced to BRI-08"], NOT8)
def dup101(lines):
    out = []
    for l in lines:
        out.append(l)
        if l == _m101: out.append(l)
    return [setf(l, "marks", str(int(fld(l, "marks")) + 1)) if "HMI-BUILD-END," in l else l for l in out]
b8case("e19_versus255_duplicate_model", b8pair(1, v55=dup101),
       ["a second CISD row for this cycle", "one per cycle and model (Rule 43)", "UNEXPLAINED - not traced to BRI-08"], NOT8)
_noarm = lambda lines: [l for l in lines if not ("HMI-ARM," in l and ",block=101," in l)]
b8case("e20_versus255_armed_missing", b8pair(1, v54=_noarm, v55=_noarm),
       ["its cycle's ARMED row (block 101) is not in the log", "row(s) PENDING_ATTRIBUTION), not a pass"], NOT8 + ["UNEXPLAINED - not traced"])
# the bound itself: the old cycle may confirm ON the bar whose ARMED closes it (Phase 4 before Phase 5) - C01 alone
SER1, SP1 = B8.ladder([s_ for s_ in B8.SCEN if s_["id"] == "C01"])
B8.ladder_check(SER1, SP1, 1)
_ev1 = B8.expected_verdicts(SER1, 1)
_c01 = lambda d: B8.emit_build(SER1, d, "2.54", "0B54", 1) + B8.emit_build(SER1, d, "2.55", "0C55", 2)
b8case("e21_versus255_confirm_on_next_armed_ok", _c01(1),
       [f"verdicts: explained {sum(_ev1.values())}   PENDING_ATTRIBUTION 0   UNEXPLAINED 0", f"    {'B8-SHIFT':<12} {_ev1['SHIFT']:>4}",
        "same cycle, model and reference; v2.55 confirmed already"], ["UNEXPLAINED - not traced", "NOT JUDGED"])

# a terminal restart between two builds (run= changes): not a continuous live stretch - PENDING, never compared (A-60)
_rs = lambda lines: [l.replace(",run=7,", ",run=8,").replace(" run=7 init=", " run=8 init=") for l in lines]
b8case("e22_live255_restart_between_builds", lb1 + LIVE + _rs(lb2[1:]),
       ["terminal restarted between the builds (run 7 -> 8)", "nothing comparable yet - no PASS can be given"], ["AGREE BOTH WAYS"], ["-LiveVsBuild"])

# ---- v2.56 (BRI-13): strength score rows. HMI-STR / HMI-STR-HIST written by tools/strength_sim.py exactly as
# HMI_StrengthEngine.mqh prints them; ReloadTest recomputes every row from its own inputs and must agree with the
# model to the last digit (the exact 35 / 65 boundaries included), find tampering, and judge STR as a category.
import strength_sim as SS
_SB, _SC = SS.engine_series()
def strs(upto=None, live=0, init=1, sub=None, inst="0001"):
    n = len(_SB) if upto is None else upto
    return [L(SRC, SS.str_row(_SB, h, _SC[h], live=live, init=init, inst=inst)) for h in range(sub or 0, n)]
def shist(upto=None, init=1, inst="0001"):
    n = len(_SB) if upto is None else upto
    return [L(SRC, SS.hist_row(_SB, [SS.score(_SB, h, _SC[h]) for h in range(n)], init=init, inst=inst))]
def _bnd():
    out = []
    for i, (b, h, cx) in enumerate(SS.boundary_cases()):
        r = SS.str_row(b, h, cx)
        out.append(setf(L(SRC, r), "bar", f"2026.09.2{i // 10} {i % 10:02d}:00"))
    return out
def s56(b, rows, **kw): return blk(b, ver="2.56", extra_rows=rows, **kw)
def tamper(lines, pick, fn):
    """change the first line pick() selects"""
    out, done = [], False
    for l in lines:
        if not done and pick(l):
            l = fn(l); done = True
        if l is not None: out.append(l)
    return out
_ok_row = lambda l: "HMI-STR," in l and ",state=OK," in l
NOSTR = ["IDENTICAL inside", "AGREE BOTH WAYS", "IDENTICAL apart from the strength rows"]
case("s01_reload_str_identical", [start("2.56")] + s56(1, strs() + shist()) + s56(2, strs() + shist()), R,
     ["STR    IDENTICAL over", "every row recomputes from its inputs", "IDENTICAL inside the comparable region"], ["FAILED", "MISMATCH"])
case("s02_reload_str_row_missing", [start("2.56")] + s56(1, strs() + shist()) + s56(2, tamper(strs(), lambda l: ",bar=2026.09.13 20:00," in l, lambda l: None) + shist()), R,
     ["STR    MISMATCH (1)", "A only  STR STR|bar=2026.09.13 20:00"], NOSTR)
case("s03_reload_str_score_tampered", [start("2.56")] + s56(1, strs() + shist()) + s56(2, tamper(strs(), _ok_row, lambda l: setf(l, "score", str(int(fld(l, "score")) + 1))) + shist()), R,
     ["ROW CHECK(S) FAILED", "recomputed", "strength rows FAILED their check"], NOSTR)
case("s04_reload_str_seff_tampered", [start("2.56")] + s56(1, strs() + shist()) + s56(2, tamper(strs(), _ok_row, lambda l: setf(l, "s_eff", "99.000000")) + shist()), R,
     ["ROW CHECK(S) FAILED", "s_eff=99.000000, recomputed"], NOSTR)
case("s05_reload_str_net_not_dir", [start("2.56")] + s56(1, strs() + shist()) + s56(2, tamper(strs(), lambda l: _ok_row(l) and ",dir=-1," in l, lambda l: setf(l, "dir", "1")) + shist()), R,
     ["ROW CHECK(S) FAILED", "OK with ctx=BEARISH dir=1"], NOSTR)
case("s06_reload_str_nodir_with_score", [start("2.56")] + s56(1, strs() + shist()) + s56(2, tamper(strs(), lambda l: ",state=NODIR," in l, lambda l: setf(l, "score", "50")) + shist()), R,
     ["ROW CHECK(S) FAILED", "NODIR with score=50"], NOSTR)
case("s07_reload_str_hist_ok_wrong", [start("2.56")] + s56(1, strs() + shist()) + s56(2, strs() + tamper(shist(), lambda l: True, lambda l: setf(l, "ok", "35"))), R,
     ["ROW CHECK(S) FAILED", "HIST ok + nodir + nodata = 58, bars=59"], NOSTR)
case("s08_reload_str_hist_missing", [start("2.56")] + s56(1, strs() + shist()) + s56(2, strs()), R,
     ["ROW CHECK(S) FAILED", "0 HMI-STR-HIST row(s) in build 2 (one expected)"], NOSTR)
case("s09_reload_str_hist_to", [start("2.56")] + s56(1, strs() + shist()) + s56(2, strs() + tamper(shist(), lambda l: True, lambda l: setf(l, "to", "2026.09.17 00:00"))), R,
     ["ROW CHECK(S) FAILED", "but HIST to=2026.09.17 00:00"], NOSTR)
case("s10_reload_str_dup_bar", [start("2.56")] + s56(1, strs() + shist()) + s56(2, strs() + strs(sub=58) + shist()), R,
     ["ROW CHECK(S) FAILED", "bar 2026.09.16 20:00 has 2 HMI-STR rows"], NOSTR)
_d66 = lambda l: l.replace("-T35.65", "-T35.66")
case("s11_reload_str_def_changed", [start("2.56")] + s56(1, strs() + shist()) + s56(2, [_d66(l) for l in strs() + shist()]), R,
     ["STR    NOT COMPARABLE - scoring definition differs", "PENDING REVIEW, not a pass", "strength rows not compared"], NOSTR + ["STR    MISMATCH"])
case("s12_reload_str_def_unknown", [start("2.56")] + s56(1, strs() + shist()) + s56(2, [l.replace("STR1-N12K3", "STR9-N12K3") for l in strs() + shist()]), R,
     ["is not a definition this tool can recompute"], NOSTR)
# the boundary rows recompute exactly (B01-B07: raw 34.5 / 34.96 / 35 / 64.46 / 64.5 / 64.96 / 65), checked through -Str's audit
_bh = [SS.score(b, h, cx) for (b, h, cx) in SS.boundary_cases()]
def _bhist():
    h = [0] * 101
    for r in _bh:
        if r["state"] == "OK": h[r["score"]] += 1
    ok = [r for r in _bh if r["state"] == "OK"]
    t = lambda k: sum(1 for r in ok if r["tier"] == k)
    return L(SRC, f"HMI-STR-HIST,USDJPY,live=0,def={SS.DEF_ID},from=2026.09.20 00:00,to=2026.09.2{(len(_bh) - 1) // 10} {(len(_bh) - 1) % 10:02d}:00,bars={len(_bh)},"
                  f"ok={len(ok)},nodir=0,nodata={len(_bh) - len(ok)},weak={t('WEAK')},med={t('MED')},strong={t('STRONG')},h={';'.join(map(str, h))},inst=0001,run=7,init=1")
case("s13_str_boundaries_recompute", [start("2.56")] + s56(1, _bnd() + [_bhist()]), ["-Str"],
     ["merged  params ABCD1234 " + SS.DEF_ID, "displayed score  P10"], ["CHECK FAILED"])
case("s14_str_boundary_tier_tampered", [start("2.56")] + s56(1, tamper(_bnd(), lambda l: ",raw=65.000000," in l, lambda l: setf(l, "tier", "MED")) + [_bhist()]), ["-Str"],
     ["CHECK FAILED (2)"], [])
# live vs build: the live run's rows on the H4 bars between the builds, both ways
_X, _Y = 40, 50
_tA, _tB = SS.tstr16(_SB[_X - 1][0] + SS.H4), SS.tstr16(_SB[_Y - 1][0] + SS.H4)
def sb(b, n, init, rows=None, **kw):
    return blk(b, ver="2.56", init=init, to=(_tA if n == _X else _tB), extra_rows=(rows if rows is not None else strs(n, init=init) + shist(n, init=init)), **kw)
_LV = strs(_Y, live=1, sub=_X)
case("s15_live_str_ok", [start("2.56")] + sb(1, _X, 1) + _LV + [start("2.56", init=2)] + sb(2, _Y, 2), ["-LiveVsBuild"],
     [f"strength rows compared: {_Y - _X} (STR)", "AGREE BOTH WAYS on every covered bar"], ["MISMATCH(ES)", "FAILED"])
case("s16_live_str_missing", [start("2.56")] + sb(1, _X, 1) + _LV + [start("2.56", init=2)] + sb(2, _Y, 2, rows=tamper(strs(_Y, init=2), lambda l: f",bar={SS.tstr16(_SB[_X + 3][0] + SS.H4)}," in l, lambda l: None) + shist(_Y, init=2)),
     ["-LiveVsBuild"], ["MISMATCH(ES) on covered bars", "live only  [1->2] STR STR|bar=" + SS.tstr16(_SB[_X + 3][0] + SS.H4)], ["AGREE BOTH WAYS"])
_tam = lambda l: setf(l, "score", str(int(fld(l, "score")) + 1))
case("s17_live_str_tampered", [start("2.56")] + sb(1, _X, 1) + tamper(_LV, _ok_row, _tam) + [start("2.56", init=2)] + sb(2, _Y, 2), ["-LiveVsBuild"],
     ["live strength row(s) FAILED the recomputation", "MISMATCH(ES) on covered bars"], ["AGREE BOTH WAYS on every covered bar"])
case("s18_live_str_def_changed", [start("2.56")] + sb(1, _X, 1) + [_d66(l) for l in _LV] + [start("2.56", init=2)] + sb(2, _Y, 2), ["-LiveVsBuild"],
     ["scoring definition differs", "strength rows not compared"], ["strength rows compared:"])
# v2.55 -> v2.56: the strength score is added and nothing else may change
def v55v56(old_rows=(), new_rows=None, new_tweak=None, new_kw=None):
    a = blk(1, ver="2.55", inst="0C55", init=1, extra_rows=list(old_rows))
    nb = blk(1, ver="2.56", inst="0D56", init=2, extra_rows=(strs(init=2, inst="0D56") + shist(init=2, inst="0D56") if new_rows is None else new_rows), **(new_kw or {}))
    if new_tweak: nb = new_tweak(nb)
    return [start("2.55", inst="0C55")] + a + [start("2.56", inst="0D56", init=2)] + nb
VS = ["-Source", "USDJPY#0C55,M5", "-Versus", "USDJPY#0D56,M5"]
case("s19_versus256_additive_ok", v55v56(), VS,
     ["the strength score is added (BRI-13, display only)", "IDENTICAL apart from the strength rows"], ["UNEXPLAINED", "FAILED", "NOT JUDGED"])
case("s20_versus256_chain_row_changed", v55v56(new_tweak=lambda nb: tamper(nb, lambda l: "HMI-ARM," in l, lambda l: l.replace("sess=60", "sess=61"))), VS,
     ["line(s) differ outside the strength rows - UNEXPLAINED", "HMI-ARM,USDJPY,block=61,sess=61"], ["IDENTICAL apart from the strength rows"])
case("s21_versus256_model_changed", v55v56(new_tweak=lambda nb: tamper(nb, lambda l: ",MODEL," in l, lambda l: l.replace(",1.23456,", ",1.23457,"))), VS,
     ["line(s) differ outside the strength rows - UNEXPLAINED", "v2.55 only (1)  HMI-BUILD,USDJPY,MODEL"], ["IDENTICAL apart from the strength rows"])
case("s22_versus256_window_moved", v55v56(new_kw={"frm": "2026.09.07 03:45"}), VS,
     ["NOT JUDGED - the windows differ"], ["IDENTICAL apart from the strength rows"])
case("s23_versus256_str_bad", v55v56(new_tweak=lambda nb: tamper(nb, _ok_row, _tam)), VS,
     ["strength rows FAILED their check (2)", "recomputed 81", "row(s) with score 82 but HIST bin 82 = 1"], ["IDENTICAL apart from the strength rows"])
case("s24_versus256_no_str", v55v56(new_rows=[]), VS,
     ["strength rows FAILED their check (1)", "0 HMI-STR-HIST row(s) in build 1 (one expected)"], ["IDENTICAL apart from the strength rows"])
case("s25_versus256_old_has_str", v55v56(old_rows=strs(inst="0C55")[:1]), VS,
     ["v2.55 build carries 1 strength row(s)"], ["IDENTICAL apart from the strength rows"])
# reviewer, v2.56 dev review P2: a build scores an H4 bar only after processing it - From < bar <= To (BEGIN's M5 times);
# its histogram's to= never after To. The two counterexamples of the review, then the same in a same-version reload.
_last = SS.tstr16(_SB[-1][0] + SS.H4)
def _after(nb):
    return [setf(l, "to", "2026.10.01 00:00") if "HMI-STR-HIST," in l else
            (setf(l, "bar", "2026.10.01 00:00") if "HMI-STR," in l and f",bar={_last}," in l else l) for l in nb]
_first = SS.tstr16(_SB[0][0] + SS.H4)
def _before(nb):
    return [setf(l, "bar", "2026.09.06 00:00") if "HMI-STR," in l and f",bar={_first}," in l else l for l in nb]
case("s26_versus256_str_after_window", v55v56(new_tweak=_after), VS,
     ["strength rows FAILED their check", "HMI-STR bar=2026.10.01 00:00 outside the build's processed M5 window (2026.09.07 03:40 .. 2026.09.30 12:35]",
      "HIST to=2026.10.01 00:00 after the build's last M5 bar 2026.09.30 12:35"], ["IDENTICAL apart from the strength rows"])
case("s27_versus256_str_before_window", v55v56(new_tweak=_before), VS,
     ["strength rows FAILED their check", "HMI-STR bar=2026.09.06 00:00 outside the build's processed M5 window"], ["IDENTICAL apart from the strength rows"])
case("s28_reload_str_after_window", [start("2.56")] + s56(1, strs() + shist()) + _after(s56(2, strs() + shist())), R,
     ["ROW CHECK(S) FAILED", "B: HMI-STR bar=2026.10.01 00:00 outside the build's processed M5 window"], NOSTR)
# MT5 run 2026-10-26: the v2.55 XAUUSD charts waited for liquidity history once (10-22) and keep attempt=1 in every later
# HMI-LIQ-REPLAY line (g_lh_attempts resets at OnInit only, A-50); the v2.56 charts attached today have 0. That alone is
# instance metadata - shown, not a difference; any other REPLAY field still is.
_REP = "HMI-LIQ-REPLAY,USDJPY,need_from=2026.07.02 04:00,req_from=2026.06.29 04:00,got=18558,err=0,fail=-,have_from=2026.06.29 04:00,floor=2025.05.29 21:25,m5_first=2025.05.29 21:25,capped=1,unknown=0,short=0,waiting=0,wait_from=none,state=READY,attempt={}"
def _rep(att, inst, init, got="18558"): return L(SRC, _REP.format(att).replace("got=18558", f"got={got}") + f",inst={inst},run=7,init={init}")
def v55v56r(att_old, att_new, got_new="18558"):
    a = blk(1, ver="2.55", inst="0C55", init=1, extra_rows=[_rep(att_old, "0C55", 1)])
    nb = blk(1, ver="2.56", inst="0D56", init=2, extra_rows=[_rep(att_new, "0D56", 2, got_new)] + strs(init=2, inst="0D56") + shist(init=2, inst="0D56"))
    return [start("2.55", inst="0C55")] + a + [start("2.56", inst="0D56", init=2)] + nb
case("s29_versus256_replay_attempt_only", v55v56r(1, 0), VS,
     ["instance metadata, not compared: 2 HMI-LIQ-REPLAY line(s) differ in attempt= only", "v2.55  attempt=1", "v2.56  attempt=0",
      "IDENTICAL apart from the strength rows"], ["UNEXPLAINED"])
case("s30_versus256_replay_other_field", v55v56r(1, 0, got_new="18559"), VS,
     ["line(s) differ outside the strength rows - UNEXPLAINED", "got=18559"], ["IDENTICAL apart from the strength rows", "instance metadata, not compared"])
# v2.56 run 2026-10-26/27: the terminal slept between the last build of one day and the first of the next, with the same
# run (hibernation). Two builds in different log files are not a provable live stretch (A-60): PENDING, never compared.
# The files are read in date-name order (MT5 names them YYYYMMDD.log), whatever their write times.
def case_files(name, files, args, expect, forbid=()):
    os.makedirs(name, exist_ok=True)
    for fn, lines in files.items():
        open(os.path.join(name, fn), "w", encoding="utf-8").write("\n".join(lines) + "\n")
    C[name] = dict(args=args, expect=expect, forbid=list(forbid))
_n1 = blk(1, ver="2.56", init=1, to=_tA, extra_rows=strs(_X, init=1) + shist(_X, init=1))
_n2 = blk(2, ver="2.56", init=1, to=_tB, extra_rows=strs(_Y, init=1) + shist(_Y, init=1))
case_files("s31_live_str_across_log_files", {"20261002.log": [start("2.56")] + _n1, "20261003.log": _n2}, ["-LiveVsBuild", "-Days", "2"],
           ["the builds are in different log files (20261002.log -> 20261003.log)", "nothing comparable yet - no PASS can be given"],
           ["MISMATCH(ES)", "AGREE BOTH WAYS"])
case("s32_live_str_same_file_build_only", [start("2.56")] + _n1 + _n2, ["-LiveVsBuild"],
     ["MISMATCH(ES) on covered bars", "build only [1->2] STR"], ["AGREE BOTH WAYS"])
# ---- v2.57 (BRI-14): quality rows. One model run (tools/quality_sim.py on synthetic bars, seed 3: OK in all three tiers,
# NODIR, FEW, FEW+ANCHOR, failed breaks, five-event samples, a moved anchor under a kept protected level) written as the MQL writes it: the build's structure rows
# (HMI-CTX / PROT / ANCHOR / INTERNAL, h4_protect_attr.emit_lines), HMI-STR and HMI-QLT on the bars inside the M5
# window, both histograms. ReloadTest recomputes every QLT row, checks it against the build's own structure rows and
# judges QLT as a category; the counterexamples are single-field tampering and rows that are self-consistent but
# built on the wrong inputs (an event left out, the anchor moved, protected_level used as the anchor, a leg after its CHOCH).
import quality_sim as QS
_QB = PA.synth_bars(300, 3)
_QE, _QR, _QS, _QC = QS.run(_QB)
_QW = 150                                                    # first H4 bar logged (its close is after the first M5 open)
def _qt(h): return HB.tstr(_QB[h][0] + 4 * 3600)             # H4 close time
def _struct(upto, inst, init, live=False):
    out = []
    for l in PA.emit_lines(_QB, _QE, "2.57", inst, init):
        b = HB.dt.datetime.strptime(l.split(",bar=")[1].split(",")[0], "%Y.%m.%d %H:%M")
        bt = int(b.replace(tzinfo=HB.dt.timezone.utc).timestamp())
        if bt <= _QB[upto - 1][0] + 4 * 3600:
            out.append(l.replace(",live=0,", ",live=1,") if live else l)
    return out
def _bars_between(lines, lo, hi):
    """structure lines with lo < bar <= hi (H4 indices, close times)"""
    a, b = _QB[lo][0] + 4 * 3600, _QB[hi][0] + 4 * 3600
    out = []
    for l in lines:
        t = int(HB.dt.datetime.strptime(l.split(",bar=")[1].split(",")[0], "%Y.%m.%d %H:%M").replace(tzinfo=HB.dt.timezone.utc).timestamp())
        if a < t <= b: out.append(l)
    return out
def qrows(lo, hi, live=0, inst="0001", init=1, recs=None):
    rr = recs or _QR
    return [L(SRC, QS.qlt_row(_QB, h, _QC[h], rr[h], live=live, inst=inst, init=init)) for h in range(lo, hi)]
def srows(lo, hi, live=0, inst="0001", init=1):
    return [L(SRC, SS.str_row(_QB, h, _QC[h], live=live, inst=inst, init=init, rec=_QS[h])) for h in range(lo, hi)]
def qhists(upto, inst="0001", init=1):
    return [L(SRC, SS.hist_row(_QB, _QS[:upto], inst=inst, init=init)), L(SRC, QS.qhist_row(_QB, _QR[:upto], inst=inst, init=init))]
def qbuild(b, upto=300, ver="2.57", inst="0001", init=1, qlt=True, tweak=None):
    rows = _struct(upto, inst, init) + srows(_QW, upto, inst=inst, init=init)
    if qlt: rows += qrows(_QW, upto, inst=inst, init=init)
    rows += [qhists(upto, inst, init)[0]] + ([qhists(upto, inst, init)[1]] if qlt else [])
    if tweak: rows = tweak(rows)
    to = HB.tstr(_QB[upto - 1][0] + 5 * 3600)
    return blk(b, ver=ver, inst=inst, init=init, marks=[], liqs=[], chain=False, frm=HB.tstr(_QB[_QW][0]), to=to,
               warm=HB.tstr(_QB[_QW][0]), extra_rows=rows)
def qq(h, ctx=None, events=None, anchor=None, keep_anchor=True):
    """a quality row of bar h recomputed by the model from other inputs (self-consistent, wrong on purpose)"""
    r = _QR[h]
    ev = events if events is not None else [(k, kind, lv) for (k, kind, lv, _, _) in r["ev"]]
    an = anchor if anchor is not None else (r["anchor"] if keep_anchor else None)
    return QS.quality(_QB, h, ctx or _QC[h], ev, an)
def qswap(h, rec, init=2):
    """replace bar h's quality row (in build 2, init 2) by the one from rec"""
    new = L(SRC, QS.qlt_row(_QB, h, _QC[h], rec, init=init))
    return lambda rows: [new if (",bar=" + _qt(h) + ",") in l and "HMI-QLT," in l else l for l in rows]
_h5 = next(h for h in range(_QW + 10, 300) if _QR[h]["n"] == 5 and _QR[h]["state"] == "OK")
_hf = next(h for h in range(_QW, 300) if any(ev[3] == "FAIL" for ev in _QR[h]["ev"]) and _QR[h]["state"] in ("OK", "PARTIAL"))
_hok = next(h for h in range(_QW, 300) if _QR[h]["state"] == "OK")
_qrow = lambda h: (lambda l: "HMI-QLT," in l and (",bar=" + _qt(h) + ",") in l)
NOQ = ["IDENTICAL inside", "AGREE BOTH WAYS", "IDENTICAL apart from the quality rows"]
QB1, QB2 = qbuild(1), qbuild(2, init=2)
case("q01_reload_qlt_identical", [start("2.57")] + QB1 + [start("2.57", init=2)] + QB2, R,
     ["QLT    IDENTICAL over", "every row recomputes and agrees with its build's HMI-CTX / HMI-ANCHOR rows", "IDENTICAL inside the comparable region"],
     ["FAILED", "MISMATCH"])
case("q02_reload_qlt_row_missing", [start("2.57")] + QB1 + [start("2.57", init=2)] + qbuild(2, init=2, tweak=lambda rr: tamper(rr, _qrow(_hok), lambda l: None)), R,
     ["QLT    MISMATCH (1)", f"A only  QLT QLT|anchor="], NOQ)
case("q03_reload_qlt_score_tampered", [start("2.57")] + QB1 + [start("2.57", init=2)] + qbuild(2, init=2, tweak=lambda rr: tamper(rr, _qrow(_hok), lambda l: setf(l, "score", str(int(fld(l, "score")) + 1)))), R,
     ["ROW CHECK(S) FAILED", f"B: {_qt(_hok)}: score=", "quality rows FAILED their check"], NOQ)
def _flip_outcome(l):
    ev = fld(l, "ev")
    return setf(l, "ev", ev.replace("/FAIL/", "/OK/", 1))
case("q04_reload_qlt_outcome_tampered", [start("2.57")] + QB1 + [start("2.57", init=2)] + qbuild(2, init=2, tweak=lambda rr: tamper(rr, _qrow(_hf), _flip_outcome)), R,
     ["ROW CHECK(S) FAILED", "OK, recomputed FAIL"], NOQ)
def _close_shift(l):
    """the first mature OK event's last listed close moved 1 point further in the trend direction: the outcome stays,
    the row recomputes - only the close of that bar's own quality row shows it"""
    d = int(fld(l, "dir")); evs = fld(l, "ev").split(";")
    for i, e in enumerate(evs):
        p = e.split("/")
        if p[2] == "OK":
            cs = p[3].split("|"); cs[-1] = f"{float(cs[-1]) + d * 0.00001:.5f}"; p[3] = "|".join(cs); evs[i] = "/".join(p); break
    return setf(l, "ev", ";".join(evs))
_hc = next(h for h in range(_QW + 70, 300) if any(ev[3] == "OK" and ev[0] >= _QW for ev in _QR[h]["ev"]))
case("q05_reload_qlt_event_close", [start("2.57")] + QB1 + [start("2.57", init=2)] + qbuild(2, init=2, tweak=lambda rr: tamper(rr, _qrow(_hc), _close_shift)), R,
     ["ROW CHECK(S) FAILED", "the quality row of that bar has"], NOQ)
def _level_shift(l):
    evs = fld(l, "ev").split(";"); p = evs[0].split("@"); t, rest = p[0], p[1].split("/", 1)
    evs[0] = f"{t}@{float(rest[0]) - int(fld(l, 'dir')) * 0.00001:.5f}/{rest[1]}"
    return setf(l, "ev", ";".join(evs))
case("q06_reload_qlt_event_level", [start("2.57")] + QB1 + [start("2.57", init=2)] + qbuild(2, init=2, tweak=lambda rr: tamper(rr, _qrow(_h5), _level_shift)), R,
     ["ROW CHECK(S) FAILED", "but HMI-CTX"], NOQ)
_ev5 = [(k, kind, lv) for (k, kind, lv, res, _) in _QR[_h5]["ev"]]
_mat5 = [e for e, x in zip(_ev5, _QR[_h5]["ev"]) if x[3] != "PEND"]
_drop = qq(_h5, events=[e for e in _ev5 if e != _mat5[2]])
case("q07_reload_qlt_event_left_out", [start("2.57")] + QB1 + [start("2.57", init=2)] + qbuild(2, init=2, tweak=qswap(_h5, _drop)), R,
     ["ROW CHECK(S) FAILED", f"break {_qt(_mat5[2][0])} of the current leg is not listed but is newer than a listed mature event"], NOQ)
_an = _QR[_hok]["anchor"]
_moved = qq(_hok, anchor=(_an[0], _an[1] - _QR[_hok]["dir"] * 10))
case("q08_reload_qlt_anchor_moved", [start("2.57")] + QB1 + [start("2.57", init=2)] + qbuild(2, init=2, tweak=qswap(_hok, _moved)), R,
     ["ROW CHECK(S) FAILED", "but the latest HMI-ANCHOR row gives"], NOQ)
# the two roles merged again: the retrace measured from protected_level where the leg's anchor has moved (BRI-14 C-6)
def _levels_at(h, rows):
    t = _QB[h][0] + 4 * 3600
    last = [r for r in rows if r["bar"] <= t]
    return last[-1] if last else None
_tidx = {b[0]: k for k, b in enumerate(_QB)}
_hp = next(h for h in range(_QW, 300) if _QR[h]["state"] in ("OK", "PARTIAL") and _QR[h]["anchor"] is not None and
           (_levels_at(h, _QE.prot_rows) or {}).get("level") is not None and
           abs((_levels_at(h, _QE.prot_rows) or {})["level"] - _levels_at(h, _QE.anchor_rows)["level"]) > 1e-9)
_pr = _levels_at(_hp, _QE.prot_rows)
_prot_as_anchor = qq(_hp, anchor=(_tidx[_pr["swing"]], QS.p(_pr["level"])))
case("q09_reload_qlt_protected_as_anchor", [start("2.57")] + QB1 + [start("2.57", init=2)] + qbuild(2, init=2, tweak=qswap(_hp, _prot_as_anchor)), R,
     ["ROW CHECK(S) FAILED", f"{_qt(_hp)}: anchor=", "but the latest HMI-ANCHOR row gives"], NOQ)
# a leg that goes on after its CHOCH: the CHOCH bar scored as if the trend still stood
_hx = next(h for h in range(_QW + 1, 300) if _QC[h] == "TRANSITION" and _QC[h - 1] in ("BULLISH", "BEARISH") and _QR[h - 1]["state"] in ("OK", "PARTIAL"))
_after_choch = qq(_hx, ctx=_QC[_hx - 1], events=[(k, kind, lv) for (k, kind, lv, _, _) in _QR[_hx - 1]["ev"]], anchor=_QR[_hx - 1]["anchor"])
def _swap_ctx(h, rec):
    new = L(SRC, QS.qlt_row(_QB, h, _QC[h - 1], rec, init=2))
    return lambda rows: [new if (",bar=" + _qt(h) + ",") in l and "HMI-QLT," in l else l for l in rows]
case("q10_reload_qlt_after_choch", [start("2.57")] + QB1 + [start("2.57", init=2)] + qbuild(2, init=2, tweak=_swap_ctx(_hx, _after_choch)), R,
     ["ROW CHECK(S) FAILED", f"{_qt(_hx)}: ctx={_QC[_hx - 1]} but the build's HMI-CTX rows leave TRANSITION"], NOQ)
_qh = lambda l: "HMI-QLT-HIST," in l
case("q11_reload_qlt_hist_ok_wrong", [start("2.57")] + QB1 + [start("2.57", init=2)] + qbuild(2, init=2, tweak=lambda rr: tamper(rr, _qh, lambda l: setf(l, "ok", str(int(fld(l, "ok")) - 1)))), R,
     ["ROW CHECK(S) FAILED", "QLT-HIST ok + partial + nodir + nodata ="], NOQ)
case("q12_reload_qlt_hist_missing", [start("2.57")] + QB1 + [start("2.57", init=2)] + qbuild(2, init=2, tweak=lambda rr: tamper(rr, _qh, lambda l: None)), R,
     ["ROW CHECK(S) FAILED", "0 HMI-QLT-HIST row(s) in build 2 (one expected)"], NOQ)
case("q13_reload_qlt_dup_bar", [start("2.57")] + QB1 + [start("2.57", init=2)] + qbuild(2, init=2, tweak=lambda rr: rr + qrows(_hok, _hok + 1, init=2)), R,
     ["ROW CHECK(S) FAILED", f"bar {_qt(_hok)} has 2 HMI-QLT rows"], NOQ)
# another window in the def: not compared (no MISMATCH); the build's own rows are then checked against ITS window - with 61
# bars a break 60 bars back should have been listed, so the structure check reports it (it reads the row's def)
_qd71 = lambda l: l.replace("QLT1-B60.", "QLT1-B61.")
case("q14_reload_qlt_def_changed", [start("2.57")] + QB1 + [start("2.57", init=2)] + qbuild(2, init=2, tweak=lambda rr: [_qd71(l) for l in rr]), R,
     ["QLT    NOT COMPARABLE - quality definition differs", "of the current leg is inside the window but not listed"], NOQ + ["QLT    MISMATCH"])
case("q15_reload_qlt_def_unknown", [start("2.57")] + QB1 + [start("2.57", init=2)] + qbuild(2, init=2, tweak=lambda rr: [l.replace("QLT1-B60", "QLT9-B60") for l in rr]), R,
     ["is not a definition this tool can recompute"], NOQ)
_lastq = _qt(299)
case("q16_reload_qlt_after_window", [start("2.57")] + QB1 + [start("2.57", init=2)] + qbuild(2, init=2, tweak=lambda rr: tamper(rr, _qrow(299), lambda l: setf(l, "bar", "2026.12.31 00:00"))), R,
     ["ROW CHECK(S) FAILED", "HMI-QLT bar=2026.12.31 00:00 outside the build's processed M5 window"], NOQ)
def _start_as_bos(l):
    return setf(l, "ev", fld(l, "ev").replace("/START/", "/BOS/", 1))
_hs = next(h for h in range(_QW, 300) if _QR[h]["ev"] and _QR[h]["ev"][0][1] == "START" and _QR[h]["ev"][0][0] >= _QW)
case("q17_reload_qlt_start_flag", [start("2.57")] + QB1 + [start("2.57", init=2)] + qbuild(2, init=2, tweak=lambda rr: tamper(rr, _qrow(_hs), _start_as_bos)), R,
     ["ROW CHECK(S) FAILED", "marked BOS, the leg opens at"], NOQ)
def _ov_shift(l):
    ov = fld(l, "ov").split(";"); i, u = ov[0].split("/"); ov[0] = f"{int(i) + 1}/{int(u) + 1}"
    return setf(l, "ov", ";".join(ov))
case("q18_reload_qlt_overlap_tampered", [start("2.57")] + QB1 + [start("2.57", init=2)] + qbuild(2, init=2, tweak=lambda rr: tamper(rr, _qrow(_hok), _ov_shift)), R,
     ["ROW CHECK(S) FAILED", "ov_sum="], NOQ)
_hr = next(h for h in range(_QW, 300) if _QR[h]["x"] is not None and 0 < _QR[h]["x"] < _QR[h]["leg"])
case("q19_reload_qlt_retrace_tampered", [start("2.57")] + QB1 + [start("2.57", init=2)] + qbuild(2, init=2, tweak=lambda rr: tamper(rr, _qrow(_hr), lambda l: setf(l, "retr_pts", str(int(fld(l, "retr_pts")) + 1)))), R,
     ["ROW CHECK(S) FAILED", "retr_pts="], NOQ)
# live vs build, with the exact 40 / 70 boundaries (quality_sim C01-C04) as live rows: they must recompute to the digit
_X2, _Y2 = 200, 230
def _live(lo, hi, tweak=None):
    rows = _bars_between(_struct(hi, "0001", 1, live=True), lo - 1, hi - 1) + srows(lo, hi, live=1) + qrows(lo, hi, live=1)
    return tweak(rows) if tweak else rows
def qlb(b, upto, init, tweak=None): return qbuild(b, upto=upto, init=init, tweak=tweak)
case("q20_live_qlt_ok", [start("2.57")] + qlb(1, _X2, 1) + _live(_X2, _Y2) + [start("2.57", init=2)] + qlb(2, _Y2, 2), ["-LiveVsBuild"],
     [f"quality rows compared: {_Y2 - _X2} (QLT)", "AGREE BOTH WAYS on every covered bar"], ["MISMATCH(ES)", "FAILED"])
_okL = lambda l: "HMI-QLT," in l and ",state=OK," in l
case("q21_live_qlt_tampered", [start("2.57")] + qlb(1, _X2, 1) + _live(_X2, _Y2, lambda rr: tamper(rr, _okL, lambda l: setf(l, "score", str(int(fld(l, "score")) + 1)))) + [start("2.57", init=2)] + qlb(2, _Y2, 2),
     ["-LiveVsBuild"], ["live quality row(s) FAILED the recomputation", "MISMATCH(ES) on covered bars"], ["AGREE BOTH WAYS on every covered bar"])
case("q22_live_qlt_build_missing", [start("2.57")] + qlb(1, _X2, 1) + _live(_X2, _Y2) + [start("2.57", init=2)] + qlb(2, _Y2, 2, tweak=lambda rr: tamper(rr, _qrow(_X2 + 5), lambda l: None)),
     ["-LiveVsBuild"], ["MISMATCH(ES) on covered bars", "live only  [1->2] QLT"], ["AGREE BOTH WAYS"])
def _bnd_rows(tier_to=None):
    """the four boundary cases as live rows of bars _X2+2 .. _X2+5 (their bars shifted in time to end there)"""
    out = {}
    for i, args in enumerate(((680, 320, 900, 600), (680, 320, 840, 570), (900, 100, 1008, 808, (4,)), (900, 100, 1008, 820, (4,)))):
        bb, h, evs, an = QS.comp_case(*args)
        dt_ = _QB[_X2 + 2 + i][0] - bb[h][0]
        bb = [(b[0] + dt_,) + tuple(b[1:]) for b in bb]
        r = QS.quality(bb, h, BULL_Q, evs, an)
        l = L(SRC, QS.qlt_row(bb, h, BULL_Q, r, live=1))
        if tier_to and i == 1: l = setf(l, "tier", tier_to)
        out[_qt(_X2 + 2 + i)] = l
    return lambda rows: [out.get(fld(l, "bar"), l) if "HMI-QLT," in l else l for l in rows]
BULL_Q = "BULLISH"
case("q23_live_qlt_boundaries_recompute", [start("2.57")] + qlb(1, _X2, 1) + _live(_X2, _Y2, _bnd_rows()) + [start("2.57", init=2)] + qlb(2, _Y2, 2), ["-LiveVsBuild"],
     ["8 MISMATCH(ES) on covered bars", "live only  [1->2] QLT"], ["FAILED the recomputation"])
case("q24_live_qlt_boundary_tier_tampered", [start("2.57")] + qlb(1, _X2, 1) + _live(_X2, _Y2, _bnd_rows("GOOD")) + [start("2.57", init=2)] + qlb(2, _Y2, 2), ["-LiveVsBuild"],
     ["1 live quality row(s) FAILED the recomputation", "tier=GOOD, recomputed FAIR"], [])
# v2.56 -> v2.57: the quality score is added and nothing else may change (HMI-STR included)
def v56v57(old_tweak=None, new_tweak=None, new_qlt=True, frm_new=None):
    a = qbuild(1, ver="2.56", inst="0D56", init=1, qlt=False, tweak=old_tweak)
    nb = qbuild(1, ver="2.57", inst="0E57", init=2, qlt=new_qlt, tweak=new_tweak)
    if frm_new: nb = [setf(l, "from", frm_new) if "HMI-BUILD-BEGIN," in l else l for l in nb]
    return [start("2.56", inst="0D56")] + a + [start("2.57", inst="0E57", init=2)] + nb
VQ = ["-Source", "USDJPY#0D56,M5", "-Versus", "USDJPY#0E57,M5"]
case("q25_versus257_additive_ok", v56v57(), VQ,
     ["the quality score is added (BRI-14, display only)", "IDENTICAL apart from the quality rows"], ["UNEXPLAINED", "FAILED", "NOT JUDGED"])
_strL = lambda l: "HMI-STR," in l and ",state=OK," in l
case("q26_versus257_str_changed", v56v57(new_tweak=lambda rr: tamper(rr, _strL, lambda l: setf(l, "score", str(int(fld(l, "score")) + 1)))), VQ,
     ["line(s) differ outside the quality rows - UNEXPLAINED", "HMI-STR,USDJPY"], ["IDENTICAL apart from the quality rows"])
case("q27_versus257_ctx_changed", v56v57(new_tweak=lambda rr: tamper(rr, lambda l: "HMI-CTX," in l and ",BOS," in l, lambda l: setf(l, "close", "1.00000"))), VQ,
     ["line(s) differ outside the quality rows - UNEXPLAINED", "HMI-CTX,USDJPY,BOS"], ["IDENTICAL apart from the quality rows"])
case("q28_versus257_qlt_bad", v56v57(new_tweak=lambda rr: tamper(rr, _qrow(_hok), lambda l: setf(l, "score", str(int(fld(l, "score")) + 1)))), VQ,
     ["quality rows FAILED their check", "score="], ["IDENTICAL apart from the quality rows"])
case("q29_versus257_no_qlt", v56v57(new_qlt=False), VQ,
     ["quality rows FAILED their check (2)", "STR / QLT H4 bars differ: 150 bar(s) with HMI-STR but no HMI-QLT",
      "0 HMI-QLT-HIST row(s) in build 1 (one expected)"], ["IDENTICAL apart from the quality rows"])
case("q30_versus257_old_has_qlt", v56v57(old_tweak=lambda rr: rr + qrows(_hok, _hok + 1, inst="0D56", init=1)), VQ,
     ["v2.56 build carries 1 quality row(s)"], ["IDENTICAL apart from the quality rows"])
case("q31_qlt_dist", [start("2.57")] + QB1, ["-Qlt"],
     ["merged  params ABCD1234 " + QS.DEF_ID, "tiers of the scored bars", "mature events used on the trend bars"], ["CHECK FAILED"])
# reviewer, v2.57 dev review (two P2): live vs build never checked the builds' own quality output (q32: both QLT-HIST
# bars=999, rows untouched - "AGREE BOTH WAYS" before); and quality rows missing from BOTH builds left the reload
# verdict IDENTICAL (q33: all of them; q34: one bar). Every processed H4 bar of a v2.57 build has an STR and a QLT row:
# the two bar sets must be the same (q36: an STR row missing instead). The live-vs-build build check covers STR too (q35).
_bars999 = lambda rr: [setf(l, "bars", "999") if "HMI-QLT-HIST," in l else l for l in rr]
case("q32_live_qlt_build_hist_corrupt", [start("2.57")] + qlb(1, _X2, 1, tweak=_bars999) + _live(_X2, _Y2) + [start("2.57", init=2)] + qlb(2, _Y2, 2, tweak=_bars999),
     ["-LiveVsBuild"], ["build score check(s) FAILED", "build 1 QLT: QLT-HIST ok + partial + nodir + nodata =", "build 2 QLT: QLT-HIST ok + partial + nodir + nodata ="],
     ["AGREE BOTH WAYS"])
_noqlt = lambda rr: [l for l in rr if "HMI-QLT," not in l]
case("q33_reload_qlt_rows_missing_both", [start("2.57")] + qbuild(1, tweak=_noqlt) + [start("2.57", init=2)] + qbuild(2, init=2, tweak=_noqlt), R,
     ["STR / QLT H4 bars differ: 150 bar(s) with HMI-STR but no HMI-QLT", "quality rows FAILED their check"], ["IDENTICAL inside"])
_h34 = _QW + 60
_no34 = lambda rr: [l for l in rr if not _qrow(_h34)(l)]
case("q34_reload_qlt_row_missing_both", [start("2.57")] + qbuild(1, tweak=_no34) + [start("2.57", init=2)] + qbuild(2, init=2, tweak=_no34), R,
     [f"STR / QLT H4 bars differ: 1 bar(s) with HMI-STR but no HMI-QLT ({_qt(_h34)})", "quality rows FAILED their check"], ["IDENTICAL inside"])
_strok = lambda rr: [setf(l, "ok", str(int(fld(l, "ok")) + 1)) if "HMI-STR-HIST," in l else l for l in rr]
case("q35_live_str_build_hist_corrupt", [start("2.57")] + qlb(1, _X2, 1, tweak=_strok) + _live(_X2, _Y2) + [start("2.57", init=2)] + qlb(2, _Y2, 2, tweak=_strok),
     ["-LiveVsBuild"], ["build score check(s) FAILED", "build 1 STR: HIST ok + nodir + nodata ="], ["AGREE BOTH WAYS"])
_nostr = lambda rr: [l for l in rr if not ("HMI-STR," in l and (",bar=" + _qt(_h34) + ",") in l)]
case("q36_reload_str_row_missing_both", [start("2.57")] + qbuild(1, tweak=_nostr) + [start("2.57", init=2)] + qbuild(2, init=2, tweak=_nostr), R,
     [f"0 bar(s) with HMI-STR but no HMI-QLT, 1 with HMI-QLT but no HMI-STR ({_qt(_h34)})"], ["IDENTICAL inside"])

# ---- v2.58 (BRI-15): stage rows. One model run (tools/stage_sim.py on synthetic bars, seed 20: TRANSITION opened by
# the protected level and by the P-6b fallback, a RANGE after a timeout, BUILD / DEEP / PUSH / CONSOL / PULLBACK, every
# arrow) written as the MQL writes it: the build's structure rows, HMI-STR, HMI-QLT and HMI-STG on the bars inside the
# M5 window, the three histograms. ReloadTest recomputes every STG row from its bar's STR / QLT rows, checks it against
# the build's own structure rows and judges STG as a category; the counterexamples are single-field tampering and rows
# that recompute but stand on the wrong inputs (how a TRANSITION opened, a RANGE's start, the arrow's leg, the reference
# score, the extreme before the bar).
import stage_sim as GS
_GB = PA.synth_bars(300, 20)
_GR, _GSR, _GQR, _GC, _GE = GS.run(_GB)
def _gt(h): return HB.tstr(_GB[h][0] + 4 * 3600)
def _gstruct(upto, inst, init, live=False):
    out = []
    for l in PA.emit_lines(_GB, _GE, "2.58", inst, init):
        b = HB.dt.datetime.strptime(l.split(",bar=")[1].split(",")[0], "%Y.%m.%d %H:%M")
        bt = int(b.replace(tzinfo=HB.dt.timezone.utc).timestamp())
        if bt <= _GB[upto - 1][0] + 4 * 3600:
            out.append(l.replace(",live=0,", ",live=1,") if live else l)
    return out
def grows(lo, hi, live=0, inst="0001", init=1, stg=True):
    out = []
    for h in range(lo, hi):
        out.append(L(SRC, SS.str_row(_GB, h, _GC[h], live=live, inst=inst, init=init, rec=_GSR[h])))
        out.append(L(SRC, QS.qlt_row(_GB, h, _GC[h], _GQR[h], live=live, inst=inst, init=init)))
        if stg: out.append(L(SRC, GS.stg_row(_GB, h, _GC[h], _GR[h], live=live, inst=inst, init=init)))
    return out
def ghists(upto, inst="0001", init=1, stg=True):
    out = [L(SRC, SS.hist_row(_GB, _GSR[:upto], inst=inst, init=init)), L(SRC, QS.qhist_row(_GB, _GQR[:upto], inst=inst, init=init))]
    if stg: out.append(L(SRC, GS.stg_hist_row(_GB, _GR[:upto], inst=inst, init=init)))
    return out
def gbuild(b, upto=300, ver="2.58", inst="0001", init=1, stg=True, tweak=None):
    rows = _gstruct(upto, inst, init) + grows(_QW, upto, inst=inst, init=init, stg=stg) + ghists(upto, inst, init, stg)
    if tweak: rows = tweak(rows)
    to = HB.tstr(_GB[upto - 1][0] + 5 * 3600)
    return blk(b, ver=ver, inst=inst, init=init, marks=[], liqs=[], chain=False, frm=HB.tstr(_GB[_QW][0]), to=to,
               warm=HB.tstr(_GB[_QW][0]), extra_rows=rows)
_grow = lambda h: (lambda l: "HMI-STG," in l and (",bar=" + _gt(h) + ",") in l)
def _gfirst(pred, lo=_QW + 4): return next(h for h in range(lo, 300) if pred(_GR[h]))
_gpb = _gfirst(lambda r: r["stage"] == "PULLBACK" and len(r["reasons"]) == 2)
_gtr = _gfirst(lambda r: r["stage"] == "TRANS" and r["chk"] == "BREAK")
_grg = _gfirst(lambda r: r["stage"] == "RANGE" and r["chk"] == "TIMEOUT")
_gfl = _gfirst(lambda r: r["arrow"] == "FLAT")
_gup = _gfirst(lambda r: r["arrow"] in ("UP", "DOWN"))
_gnr = _gfirst(lambda r: r["near"] == 0 and r["stage"] == "PULLBACK")
_gpe = next(h for h in range(_QW + 4, 300) if _GR[h]["prev_ext"] is not None and _GR[h - 1]["ext"] is not None and
            _GR[h - 1].get("anchor") == _GR[h].get("anchor") and _GR[h]["refresh"] == 1)
NOG = ["IDENTICAL inside", "AGREE BOTH WAYS", "IDENTICAL apart from the stage rows"]
GB1, GB2 = gbuild(1), gbuild(2, init=2)
case("g01_reload_stg_identical", [start("2.58")] + GB1 + [start("2.58", init=2)] + GB2, R,
     ["STG    IDENTICAL over 150 / 150 row(s) (stage / reasons / arrow)", "every row recomputes from its bar's HMI-STR / HMI-QLT",
      "QLT    IDENTICAL over", "IDENTICAL inside the comparable region"], ["FAILED", "MISMATCH"])
case("g02_reload_stg_row_missing", [start("2.58")] + GB1 + [start("2.58", init=2)] + gbuild(2, init=2, tweak=lambda rr: tamper(rr, _grow(_gpb), lambda l: None)), R,
     ["STG    MISMATCH (1)", f"STR / STG H4 bars differ: 1 bar(s) with HMI-STR but no HMI-STG ({_gt(_gpb)})"], NOG)
case("g03_reload_stg_stage_tampered", [start("2.58")] + GB1 + [start("2.58", init=2)] + gbuild(2, init=2, tweak=lambda rr: tamper(rr, _grow(_gpb), lambda l: setf(l, "stage", "PUSH"))), R,
     ["ROW CHECK(S) FAILED", f"B: {_gt(_gpb)}: stage=PUSH, recomputed PULLBACK", "stage rows FAILED their check"], NOG)
case("g04_reload_stg_reasons_tampered", [start("2.58")] + GB1 + [start("2.58", init=2)] + gbuild(2, init=2, tweak=lambda rr: tamper(rr, _grow(_gpb), lambda l: setf(l, "reasons", "+".join(reversed(fld(l, "reasons").split("+")))))), R,
     ["ROW CHECK(S) FAILED", f"{_gt(_gpb)}: reasons="], NOG)
case("g05_reload_stg_arrow_tampered", [start("2.58")] + GB1 + [start("2.58", init=2)] + gbuild(2, init=2, tweak=lambda rr: tamper(rr, _grow(_gup), lambda l: setf(l, "arrow", "FLAT"))), R,
     ["ROW CHECK(S) FAILED", f"{_gt(_gup)}: arrow=FLAT, scores"], NOG)
case("g06_reload_stg_near_tampered", [start("2.58")] + GB1 + [start("2.58", init=2)] + gbuild(2, init=2, tweak=lambda rr: tamper(rr, _grow(_gnr), lambda l: setf(l, "near", "1"))), R,
     ["ROW CHECK(S) FAILED", f"{_gt(_gnr)}: near=1, recomputed 0"], NOG)
def _prev_lower(l):
    """the extreme before the bar moved 1 point back (the bar still refreshes it: the row recomputes) - only the previous bar's
    stage row, same anchor, shows it"""
    return setf(l, "prev_ext", f"{float(fld(l, 'prev_ext')) - int(fld(l, 'dir')) * 0.00001:.5f}")
case("g07_reload_stg_prev_ext_wrong", [start("2.58")] + GB1 + [start("2.58", init=2)] + gbuild(2, init=2, tweak=lambda rr: tamper(rr, _grow(_gpe), _prev_lower)), R,
     ["ROW CHECK(S) FAILED", f"{_gt(_gpe)}: prev_ext=", "but the bar before"], NOG)
def _as_fallback(l):
    return setf(setf(l, "chk", "FALLBACK"), "reasons", "SWING_BROKEN")
case("g08_reload_stg_trans_kind_wrong", [start("2.58")] + GB1 + [start("2.58", init=2)] + gbuild(2, init=2, tweak=lambda rr: tamper(rr, _grow(_gtr), _as_fallback)), R,
     ["ROW CHECK(S) FAILED", f"{_gt(_gtr)}: chk=FALLBACK but the CHOCH at", "has HMI-PROT BREAK"], NOG)
def _as_init(l):
    return setf(setf(l, "chk", "INIT"), "reasons", "-")
case("g09_reload_stg_range_kind_wrong", [start("2.58")] + GB1 + [start("2.58", init=2)] + gbuild(2, init=2, tweak=lambda rr: tamper(rr, _grow(_grg), _as_init)), R,
     ["ROW CHECK(S) FAILED", f"{_gt(_grg)}: chk=INIT but the build's HMI-CTX rows give TIMEOUT"], NOG)
case("g10_reload_stg_arrow_new_same_leg", [start("2.58")] + GB1 + [start("2.58", init=2)] + gbuild(2, init=2, tweak=lambda rr: tamper(rr, _grow(_gfl), lambda l: setf(l, "arrow", "NEW"))), R,
     ["ROW CHECK(S) FAILED", f"{_gt(_gfl)}: arrow NEW but no leg opened after"], NOG)
def _ref_moved(l):
    """the reference score moved by one and the arrow kept consistent with it: the row recomputes, the build's own HMI-STR
    row of the reference bar does not agree"""
    rs = int(fld(l, "ref_score")) + 1; dl = int(fld(l, "score")) - rs
    return setf(setf(l, "ref_score", str(rs)), "arrow", "UP" if dl >= 5 else "DOWN" if dl <= -5 else "FLAT")
case("g11_reload_stg_ref_score_wrong", [start("2.58")] + GB1 + [start("2.58", init=2)] + gbuild(2, init=2, tweak=lambda rr: tamper(rr, _grow(_gfl), _ref_moved)), R,
     ["ROW CHECK(S) FAILED", f"{_gt(_gfl)}: ref_score=", "but HMI-STR of"], NOG)
_gh = lambda l: "HMI-STG-HIST," in l
case("g12_reload_stg_hist_wrong", [start("2.58")] + GB1 + [start("2.58", init=2)] + gbuild(2, init=2, tweak=lambda rr: tamper(rr, _gh, lambda l: setf(l, "pullback", str(int(fld(l, "pullback")) + 1)))), R,
     ["ROW CHECK(S) FAILED", "STG-HIST stages sum to"], NOG)
case("g13_reload_stg_hist_missing", [start("2.58")] + GB1 + [start("2.58", init=2)] + gbuild(2, init=2, tweak=lambda rr: tamper(rr, _gh, lambda l: None)), R,
     ["ROW CHECK(S) FAILED", "0 HMI-STG-HIST row(s) in build 2 (one expected)"], NOG)
case("g14_reload_stg_def_changed", [start("2.58")] + GB1 + [start("2.58", init=2)] + gbuild(2, init=2, tweak=lambda rr: [l.replace("STG1-NEAR25-", "STG1-NEAR30-") for l in rr]), R,
     ["STG    NOT COMPARABLE - stage definition differs"], NOG + ["STG    MISMATCH"])
case("g15_reload_stg_prot_flag", [start("2.58")] + GB1 + [start("2.58", init=2)] + gbuild(2, init=2, tweak=lambda rr: tamper(rr, _grow(_gpb), lambda l: setf(setf(setf(l, "prot", "0"), "stage", "BUILD"), "reasons", "NO_PROT"))), R,
     ["ROW CHECK(S) FAILED", f"{_gt(_gpb)}: prot=0 but HMI-QLT reason="], NOG)
case("g16_reload_stg_dist_tampered", [start("2.58")] + GB1 + [start("2.58", init=2)] + gbuild(2, init=2, tweak=lambda rr: tamper(rr, _grow(_gnr), lambda l: setf(l, "dist_pts", str(int(fld(l, "dist_pts")) + 1)))), R,
     ["ROW CHECK(S) FAILED", f"{_gt(_gnr)}: dist_pts="], NOG)
case("g17_reload_stg_tr_sum_copy", [start("2.58")] + GB1 + [start("2.58", init=2)] + gbuild(2, init=2, tweak=lambda rr: tamper(rr, _grow(_gpb), lambda l: setf(l, "tr_sum", str(int(fld(l, "tr_sum")) + 1)))), R,
     ["ROW CHECK(S) FAILED", f"{_gt(_gpb)}: tr_sum="], NOG)
# live vs build
def _glive(lo, hi, tweak=None):
    rows = _bars_between_g(_gstruct(hi, "0001", 1, live=True), lo - 1, hi - 1) + grows(lo, hi, live=1)
    return tweak(rows) if tweak else rows
def _bars_between_g(lines, lo, hi):
    a, b = _GB[lo][0] + 4 * 3600, _GB[hi][0] + 4 * 3600
    out = []
    for l in lines:
        t = int(HB.dt.datetime.strptime(l.split(",bar=")[1].split(",")[0], "%Y.%m.%d %H:%M").replace(tzinfo=HB.dt.timezone.utc).timestamp())
        if a < t <= b: out.append(l)
    return out
def glb(b, upto, init, tweak=None): return gbuild(b, upto=upto, init=init, tweak=tweak)
case("g18_live_stg_ok", [start("2.58")] + glb(1, _X2, 1) + _glive(_X2, _Y2) + [start("2.58", init=2)] + glb(2, _Y2, 2), ["-LiveVsBuild"],
     [f"stage rows compared: {_Y2 - _X2} (STG)", "AGREE BOTH WAYS on every covered bar"], ["MISMATCH(ES)", "FAILED"])
_gL = lambda l: "HMI-STG," in l and ",stage=PULLBACK," in l
case("g19_live_stg_tampered", [start("2.58")] + glb(1, _X2, 1) + _glive(_X2, _Y2, lambda rr: tamper(rr, _gL, lambda l: setf(l, "stage", "DEEP"))) + [start("2.58", init=2)] + glb(2, _Y2, 2),
     ["-LiveVsBuild"], ["live stage row(s) FAILED the recomputation", "MISMATCH(ES) on covered bars"], ["AGREE BOTH WAYS on every covered bar"])
case("g20_live_stg_build_missing", [start("2.58")] + glb(1, _X2, 1) + _glive(_X2, _Y2) + [start("2.58", init=2)] + glb(2, _Y2, 2, tweak=lambda rr: tamper(rr, _grow(_X2 + 5), lambda l: None)),
     ["-LiveVsBuild"], ["MISMATCH(ES) on covered bars", "live only  [1->2] STG"], ["AGREE BOTH WAYS"])
_stgbars = lambda rr: [setf(l, "bars", "999") if "HMI-STG-HIST," in l else l for l in rr]
case("g21_live_stg_build_hist_corrupt", [start("2.58")] + glb(1, _X2, 1, tweak=_stgbars) + _glive(_X2, _Y2) + [start("2.58", init=2)] + glb(2, _Y2, 2, tweak=_stgbars),
     ["-LiveVsBuild"], ["build score check(s) FAILED", "build 1 STG: STG-HIST stages sum to"], ["AGREE BOTH WAYS"])
# v2.57 -> v2.58: the stage rows are added and nothing else may change (HMI-STR and HMI-QLT included)
def v57v58(old_tweak=None, new_tweak=None, new_stg=True):
    a = gbuild(1, ver="2.57", inst="0D57", init=1, stg=False, tweak=old_tweak)
    nb = gbuild(1, ver="2.58", inst="0E58", init=2, stg=new_stg, tweak=new_tweak)
    return [start("2.57", inst="0D57")] + a + [start("2.58", inst="0E58", init=2)] + nb
VG = ["-Source", "USDJPY#0D57,M5", "-Versus", "USDJPY#0E58,M5"]
case("g22_versus258_additive_ok", v57v58(), VG,
     ["the stage, reasons and strength arrow are added (BRI-15, display only)", "IDENTICAL apart from the stage rows"], ["UNEXPLAINED", "FAILED", "NOT JUDGED"])
_qok = lambda l: "HMI-QLT," in l and ",state=OK," in l
case("g23_versus258_qlt_changed", v57v58(new_tweak=lambda rr: tamper(rr, _qok, lambda l: setf(l, "score", str(int(fld(l, "score")) + 1)))), VG,
     ["line(s) differ outside the stage rows - UNEXPLAINED", "HMI-QLT,USDJPY"], ["IDENTICAL apart from the stage rows"])
case("g24_versus258_stg_bad", v57v58(new_tweak=lambda rr: tamper(rr, _grow(_gpb), lambda l: setf(l, "stage", "PUSH"))), VG,
     ["stage rows FAILED their check", "stage=PUSH, recomputed PULLBACK"], ["IDENTICAL apart from the stage rows"])
case("g25_versus258_no_stg", v57v58(new_stg=False), VG,
     ["stage rows FAILED their check (2)", "STR / STG H4 bars differ: 150 bar(s) with HMI-STR but no HMI-STG",
      "0 HMI-STG-HIST row(s) in build 1 (one expected)"], ["IDENTICAL apart from the stage rows"])
case("g26_versus258_old_has_stg", v57v58(old_tweak=lambda rr: rr + [L(SRC, GS.stg_row(_GB, _gpb, _GC[_gpb], _GR[_gpb], inst="0D57", init=1))]), VG,
     ["v2.57 build carries 1 stage row(s)"], ["IDENTICAL apart from the stage rows"])
case("g27_stg_dist", [start("2.58")] + GB1, ["-Stg"],
     ["merged  params ABCD1234 " + GS.DEF_ID, "trend stages", "reasons       PROT_BROKEN"], ["CHECK FAILED"])
_nostg = lambda rr: [l for l in rr if "HMI-STG," not in l]
case("g28_reload_stg_rows_missing_both", [start("2.58")] + gbuild(1, tweak=_nostg) + [start("2.58", init=2)] + gbuild(2, init=2, tweak=_nostg), R,
     ["STR / STG H4 bars differ: 150 bar(s) with HMI-STR but no HMI-STG", "stage rows FAILED their check"], ["IDENTICAL inside"])
json.dump(C, open("cases.json", "w"), indent=1)
print(len(C), "cases")
