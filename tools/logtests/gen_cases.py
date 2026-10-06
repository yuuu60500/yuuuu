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
    return L(src, f"{kind},USDJPY,{extra},bar={bar}" + tail(inst, run, init))

MK = ["2026.09.10 10:05:00", "2026.09.15 14:35:00", "2026.09.22 08:20:00"]
LQ = [("2026.09.12 09:05:00", "PDH", "SWEEP"), ("2026.09.18 16:10:00", "PWL", "BROKEN")]
SRC = "USDJPY,M5"

def blk(b, ver="2.51", inst="0001", run=7, init=1, marks=MK, liqs=LQ, end_kw=None, with_end=True, row_id=None, diag_id=None,
        frm="2026.09.07 03:40", to="2026.09.30 12:35", warm="2026.09.07 12:00", src=SRC, params="ABCD1234", extra_rows=(), begin_b="same"):
    rid = row_id or (run, init)
    did = diag_id or (run, init)
    out = [begin(src, b if begin_b == "same" else begin_b, ver, inst, run, init, frm, to, warm, params)]
    out.append(diag(src, "HMI-POI,NEW", "2026.09.08 08:00", inst, *did))
    out.append(diag(src, "HMI-SESS,START", "2026.09.10 09:55", inst, *did, extra="id=60,poi=55,dir=1"))
    out.append(diag(src, "HMI-BLK,NEW", "2026.09.10 09:58", inst, *did, extra="id=61,sess=60,dir=1,type=OB,counter=0"))
    out.append(diag(src, "HMI-ARM", "2026.09.10 10:00", inst, *did, extra="block=61,sess=60,dir=1"))
    for i, t in enumerate(marks): out.append(model(src, "HMI-BUILD", t, inst, *rid, cyc=100 + i))
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
def dedup(kind, d, bar, prim, swings, inst="0001", run=7, init=1, src=SRC):
    return L(src, f"HMI-CTX-DEDUP,USDJPY,{kind},dir={d},bar={bar},primary={prim},also={len(swings)},swings={'|'.join(swings)}" + tail(inst, run, init))

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
def side(ver, inst, init, rows, marks=MK, extra=()):
    return [start(ver, inst, 7, init)] + blk(1, ver=ver, inst=inst, init=init, marks=marks, extra_rows=list(rows) + list(extra))
V = ["-Source", A52, "-Versus", B53]
old52 = [ctx(*E1, inst="0A52", init=1), ctx(*E2s, inst="0A52", init=1), ctx(*E3, inst="0A52", init=1)]
new53 = [ctx(*E1, inst="0B53", init=2, also=1), dedup("BOS", "UP", E1[4], "2026.09.07 20:00@1.23000", [STALE], inst="0B53", init=2),
         ctx(*E3[:3], 2, *E3[4:], inst="0B53", init=2, also=0)]
case("c05_versus_dedup_only", side("2.52", "0A52", 1, old52) + side("2.53", "0B53", 2, new53), V,
     ["suppressed duplicate               1", "strength renumbered                1", "UNEXPLAINED                        0",
      "H4 state: identical at every event bar", "upgrade regression: 0 difference(s) over 3 / 3 MODEL row(s), same window and parameters."])
CH = ("CHOCH", "DOWN", "TRANSITION", 0, "2026.09.09 08:00", "2026.09.08 20:00", "1.22950", "1.22900")
TF = ("TRANS_FAIL", "UP", "BULLISH", 1, "2026.09.10 08:00", "2026.09.06 12:00", "1.22900", "1.23000")
poi52 = diag(SRC.replace("USDJPY,M5", "USDJPY,M5"), "HMI-POI,NEW", "2026.09.10 08:00", "0A52", 7, 1, extra="id=77,dir=1,lo=1.22800,hi=1.22900,origin=2026.09.10 00:00")
old52b = [ctx(*E1, inst="0A52", init=1), ctx(*CH, inst="0A52", init=1), ctx(*TF, inst="0A52", init=1, messy=1), poi52]
new53b = [ctx(*E1, inst="0B53", init=2, also=1), dedup("BOS", "UP", E1[4], "2026.09.07 20:00@1.23000", [STALE], inst="0B53", init=2),
          ctx(*CH, inst="0B53", init=2, also=0)]
case("c06_versus_state_divergence", side("2.52", "0A52", 1, old52b, marks=MK + ["2026.09.12 10:05:00"]) + side("2.53", "0B53", 2, new53b), V,
     ["suppressed duplicate               1", "H4 state differs in 1 interval(s), first from 2026.09.10 08:00",
      "before the first H4 state difference (UNEXPLAINED): 0", "every one after an H4 state difference caused by the BOS de-dup"],
     ["UNEXPLAINED                        1"])
case("c07_versus_model_unexplained", side("2.52", "0A52", 1, [ctx(*E1, inst="0A52", init=1)], marks=MK + ["2026.09.12 10:05:00"])
                                     + side("2.53", "0B53", 2, [ctx(*E1, inst="0B53", init=2, also=0)]), V,
     ["H4 state: identical at every event bar", "before the first H4 state difference (UNEXPLAINED): 1",
      "upgrade regression: 1 difference(s) over 4 / 3 MODEL row(s)"], ["caused by the BOS de-dup"])
case("c08_versus_ctx_unexplained", side("2.52", "0A52", 1, old52) + side("2.53", "0B53", 2, [ctx(*E1, inst="0B53", init=2, also=0), ctx(*E3[:3], 2, *E3[4:], inst="0B53", init=2, also=0)]), V,
     ["UNEXPLAINED                        1", "but 1 structure / chain difference(s) are UNEXPLAINED"])

# strength number only: same event, same swing, same state, str counted from another H4 start
same_s = ctx_rows([E1, E3[:3] + (5,) + E3[4:]], also=0)
case("c09_ctx_strength_only", [start()] + blk(1, extra_rows=same) + blk(2, extra_rows=same_s), R,
     ["same events, strength numbered differently on 1 - PENDING REVIEW", "PENDING REVIEW, not a pass"], ["IDENTICAL inside", "CTX    MISMATCH"])
bctx_s = ctx(*E3[:3], 7, "2026.09.30 13:00", *E3[5:], live=0, also=0, init=2)
b2s = blk(2, init=2, to="2026.09.30 14:00", marks=MK + ["2026.09.30 13:05:00"], extra_rows=[bctx_s])
case("c10_live_ctx_strength_only", [start()] + blk(1) + [live_ok, lctx] + [start(init=2)] + b2s, ["-LiveVsBuild"],
     ["AGREE BOTH WAYS on every covered bar", "1 H4 event(s) agree on swing and state but not on the strength number"], ["MISMATCH(ES)"])

json.dump(C, open("cases.json", "w"), indent=1)
print(len(C), "cases")
