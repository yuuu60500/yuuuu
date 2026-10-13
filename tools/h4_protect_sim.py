"""Offline model of the v2.54 H4 structure rules (BRI-12): protected_level and leg_anchor.

Built on the v2.53 model (h4_dedup_sim.py: swings, BOS de-dup, POI chain unchanged) and
changes only what BRI-12 changes, so a v2.53 vs v2.54 difference here is a BRI-12 difference:

  P-1  candidate     at a BOS that breaks primary swing P: the latest-FORMED opposite swing
                     with  P.bar_time < bar_time,  confirm <= this H4 close,  not processed
  P-2  protected     leg start: candidate or INVALID; later BOS: advance only (bull up / bear
                     down), keep when worse / equal / none; INVALID -> SET when one appears
  P-3  leg_anchor    the same candidate at every BOS, no monotonic rule, log only
  P-4  CHOCH         only a close beyond protected by more than the margin, on that bar;
                     a lower internal swing broken -> processed, INTERNAL row, no state change
  P-5  TRANSITION    TRANS_OK and TRANS_FAIL both need a swing FORMED at or after the CHOCH
                     close (bar_time >= ctx_time) AND confirmed after it (confirm > ctx_time);
                     anything else is TRANS_SAMELEG (consumed, no state change)
  P-6  INVALID       marked; boundary rule P-6b (fallback, default on): CHOCH by the v2.53
                     rule (latest confirmed, unprocessed opposite swing) while INVALID
  P-7  order         timeout -> protected break (pre-bar protected) -> BOS -> internal

    python3 tools/h4_protect_sim.py                      scenarios, both directions
    python3 tools/h4_protect_sim.py --replay <H1 csv>    v2.53 vs v2.54 on real data

It models the rules, not MQL5: a pass here does not replace compiling and running the indicator.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import h4_dedup_sim as B                                     # noqa: E402
from h4_dedup_sim import (UP, DOWN, RANGE, BULL_CTX, BEAR_CTX, TRANS, H4, MARGIN_PTS, TRANS_MAX,  # noqa: E402
                          break_up, break_down, pts, tstr)


def brk(d, close, level):
    return break_up(close, level, MARGIN_PTS) if d == UP else break_down(close, level, MARGIN_PTS)


class Engine254(B.Engine):
    def __init__(self, fallback=True):
        super().__init__(dedup=True)
        self.fallback = fallback
        self.leg = 0
        self.prot = None          # dict(price, bar_time, confirm, bos, set_at) or None (INVALID / no trend)
        self.anchor = None
        self.prot_rows, self.anchor_rows, self.internal_rows = [], [], []
        self.invalid_bars = 0     # trend bars spent with protected INVALID
        self.trend_bars = 0

    # --- P-1 ------------------------------------------------------------------
    def candidate(self, d, primary, t):
        """d = direction of the BOS; the candidate is an opposite swing formed after the
        primary, confirmed by this close, still unprocessed. Latest formed wins."""
        best = None
        for s in self.sw:
            if s["dir"] != -d or s["swept"] or s["confirm"] > t or s["bar_time"] <= primary["bar_time"]:
                continue
            if best is None or s["bar_time"] > best["bar_time"]:
                best = s
        return best

    def plog(self, rows, ev, d, t, lvl, prev=None):
        rows.append(dict(ev=ev, dir=d, leg=self.leg, bar=t,
                         level=(lvl["price"] if lvl else None), swing=(lvl["bar_time"] if lvl else 0),
                         confirm=(lvl["confirm"] if lvl else 0), bos=(lvl["bos"] if lvl else 0),
                         prev=(prev["price"] if prev else None)))

    def on_bos(self, d, primary, t, leg_start):
        c = self.candidate(d, primary, t)
        cand = dict(price=c["price"], bar_time=c["bar_time"], confirm=c["confirm"], bos=t) if c else None
        if leg_start:
            self.leg += 1
            self.prot = cand; self.anchor = cand
            self.plog(self.prot_rows, "SET" if cand else "INVALID", d, t, cand)
            self.plog(self.anchor_rows, "SET" if cand else "INVALID", d, t, cand)
            return
        old = self.prot
        if cand is None:
            self.plog(self.prot_rows, "KEEP_NONE", d, t, old)
        elif old is None:
            self.prot = cand; self.plog(self.prot_rows, "SET", d, t, cand)
        elif (d == UP and pts(cand["price"], old["price"]) > 0) or (d == DOWN and pts(cand["price"], old["price"]) < 0):
            self.prot = cand; self.plog(self.prot_rows, "ADVANCE", d, t, cand, old)
        else:
            self.plog(self.prot_rows, "KEEP_WORSE", d, t, old)
        if cand is None:
            self.plog(self.anchor_rows, "KEEP_NONE", d, t, self.anchor)
        else:
            prev = self.anchor; self.anchor = cand; self.plog(self.anchor_rows, "MOVE" if prev else "SET", d, t, cand, prev)

    def leave_trend(self, ev, d, t):
        self.plog(self.prot_rows, ev, d, t, self.prot)
        self.plog(self.anchor_rows, "RESET", d, t, self.anchor)
        self.prot = None; self.anchor = None

    def find(self, d, lvl):
        for i in range(len(self.sw) - 1, -1, -1):
            s = self.sw[i]
            if s["dir"] == d and s["bar_time"] == lvl["bar_time"] and s["price"] == lvl["price"]:
                return i
        return -1

    # --- one closed H4 bar ------------------------------------------------------
    def context_on_bar(self, r, h):
        self.ctx_bars += 1
        t = r[h][0] + H4
        cl = r[h][4]
        if self.ctx == TRANS and self.ctx_bars > TRANS_MAX:
            self.enter(RANGE, 0, t)
            self.log("TIMEOUT", 0, t, None, cl, 0)
            return
        if self.ctx in (BULL_CTX, BEAR_CTX):
            self.trend_bars += 1
            d = self.ctx_dir()
            if self.prot is None:
                self.invalid_bars += 1
            # P-4 / P-6: failure first, judged with the protected level as it was BEFORE this bar
            if self.prot is not None and brk(-d, cl, self.prot["price"]):
                i = self.find(-d, self.prot)
                sw = self.sw[i] if i >= 0 else dict(bar_time=self.prot["bar_time"], price=self.prot["price"], confirm=self.prot["confirm"], swept=True, dir=-d)
                sw["swept"] = True
                extra = self.consume_same_dir(r, h, -d, i)
                self.leave_trend("BREAK", d, t)
                self.enter(TRANS, -d, t); self.strength = 0
                self.log("CHOCH", -d, t, sw, cl, len(extra))
                if extra: self.dedup_rows.append(dict(bar=t, kind="CHOCH", dir=-d, primary=(sw["bar_time"], sw["price"]), extra=extra))
                return
            if self.prot is None and self.fallback:
                i = self.last_unswept(-d, t)
                if i >= 0 and brk(-d, cl, self.sw[i]["price"]):
                    sw = self.sw[i]; sw["swept"] = True
                    extra = self.consume_same_dir(r, h, -d, i)
                    self.leave_trend("FALLBACK", d, t)
                    self.enter(TRANS, -d, t); self.strength = 0
                    self.log("CHOCH", -d, t, sw, cl, len(extra))
                    if extra: self.dedup_rows.append(dict(bar=t, kind="CHOCH", dir=-d, primary=(sw["bar_time"], sw["price"]), extra=extra))
                    return
            i = self.last_unswept(d, t)
            if i >= 0 and brk(d, cl, self.sw[i]["price"]):
                sw = self.sw[i]; sw["swept"] = True
                extra = self.consume_same_dir(r, h, d, i)
                self.strength += 1
                self.log("BOS", d, t, sw, cl, len(extra))
                if extra: self.dedup_rows.append(dict(bar=t, kind="BOS", dir=d, primary=(sw["bar_time"], sw["price"]), extra=extra))
                self.on_bos(d, sw, t, False)
                return
            i = self.last_unswept(-d, t)
            if i >= 0 and brk(-d, cl, self.sw[i]["price"]):       # an internal swing: processed, no state change
                sw = self.sw[i]; sw["swept"] = True
                extra = self.consume_same_dir(r, h, -d, i)
                self.internal_rows.append(dict(bar=t, dir=-d, swing=sw["bar_time"], swing_px=sw["price"], close=cl,
                                               also=len(extra), prot=(self.prot["price"] if self.prot else None), extra=extra))
            return
        # RANGE / TRANSITION: the v2.53 break detection, with P-5 freshness in TRANSITION
        d, bi = self.detect_break(r, h)
        if d == 0:
            return
        sw = self.sw[bi]
        sw["swept"] = True
        extra = self.consume_same_dir(r, h, d, bi)
        if self.ctx == RANGE:
            self.enter(BULL_CTX if d == UP else BEAR_CTX, 0, t); self.strength = 1; kind = "BOS"
        else:
            fresh = sw["bar_time"] >= self.ctx_time and sw["confirm"] > self.ctx_time
            if not fresh:
                kind = "TRANS_SAMELEG"
            elif d == self.pending:
                self.enter(BULL_CTX if d == UP else BEAR_CTX, 0, t); self.strength = 1; kind = "TRANS_OK"
            else:
                self.enter(BULL_CTX if d == UP else BEAR_CTX, 0, t); self.strength = 1; self.messy = True; kind = "TRANS_FAIL"
        self.log(kind, d, t, sw, cl, len(extra))
        if extra:
            self.dedup_rows.append(dict(bar=t, kind=kind, dir=d, primary=(sw["bar_time"], sw["price"]), extra=extra))
        if kind in ("BOS", "TRANS_OK", "TRANS_FAIL"):
            self.on_bos(d, sw, t, True)


def run254(bars, fallback=True):
    e = Engine254(fallback)
    for h in range(len(bars)):
        e.process(bars, h)
    return e


# ---- scenarios -----------------------------------------------------------------
# A path of pivot centres; every bar is centre +/- W, close = centre. Segments are
# strictly monotonic, so each turn is a fractal swing (L = R = 2) at centre +/- W,
# confirmed at the close of the 2nd bar after it.
W = 0.0005


def path(pivots, t0=None):
    """pivots: [(centre, bars to reach it from the previous pivot), ...]; first entry's bars ignored."""
    cs = [pivots[0][0]]
    for (c, n) in pivots[1:]:
        a = cs[-1]
        cs += [a + (c - a) * k / n for k in range(1, n + 1)]
    t0 = t0 or int(B.dt.datetime(2026, 9, 7, 0, 0, tzinfo=B.dt.timezone.utc).timestamp())
    bars, prev = [], cs[0]
    for i, c in enumerate(cs):
        c = round(c, 5)
        bars.append([t0 + i * H4, prev, round(max(c + W, prev), 5), round(min(c - W, prev), 5), c])
        prev = c
    return bars


def setbar(bars, i, hi=None, lo=None, close=None):
    b = bars[i]
    if close is not None: b[4] = round(close, 5)
    if hi is not None: b[2] = round(hi, 5)
    if lo is not None: b[3] = round(lo, 5)
    b[2] = max(b[2], b[1], b[4]); b[3] = min(b[3], b[1], b[4])
    if i + 1 < len(bars): bars[i + 1][1] = b[4]


def mirror_bars(bars, axis=2.2):
    return [[b[0], round(axis - b[1], 5), round(axis - b[3], 5), round(axis - b[2], 5), round(axis - b[4], 5)] for b in bars]


def at(bars, i):
    return bars[i][0] + H4                       # close time of bar i


def ev(e, kinds=("BOS", "CHOCH", "TRANS_OK", "TRANS_FAIL", "TRANS_SAMELEG", "TIMEOUT")):
    return [(r["kind"], r["dir"], r["bar"]) for r in e.ctx_rows if r["kind"] in kinds]


RESULTS = []


def check(name, cond, detail=""):
    RESULTS.append(bool(cond))
    print(f"{'PASS' if cond else 'FAIL'}  {name}" + ("" if cond else f"\n        !! {detail}"))


def both(name, bars, fn):
    """run fn(engine, bars, d) on the bull case and on its mirror (d = trend direction)."""
    for d, bb in ((UP, bars), (DOWN, mirror_bars(bars))):
        bb = [tuple(b) for b in bb]
        fn(f"{name} [{'bull' if d == UP else 'bear'}]", bb, d)


def px(bars, d, v):
    """price v of the bull case, as seen in the case of direction d"""
    return v if d == UP else round(2.2 - v, 5)


def scenarios():
    # Base leg: low A centre 1.1000 (bar 0 area), high H1 1.1100 (bar 5), pullback L1 1.1040 (bar 8),
    # BOS of H1 (close 1.1130 at bar 12), high H2 1.1160 (bar 14), pullback L2 1.1100 (bar 17),
    # BOS of H2 (bar ~21). Swings: H1 = 1.1105, L1 = 1.1035, H2 = 1.1165, L2 = 1.1095.
    def leg(l2=1.1100, tail=None):
        p = [(1.1050, 0), (1.1000, 2), (1.1100, 5), (1.1040, 3), (1.1160, 6), (l2, 3), (1.1230, 6)]
        return path(p + (tail or []))
    base = leg()
    i_h1, i_l1, i_h2, i_l2 = 7, 10, 16, 19

    def first_bos(e, d):
        return next(r for r in e.ctx_rows if r["kind"] == "BOS")

    def s_advance(name, bars, d):
        e = run254(bars)
        p = [(r["ev"], r["level"]) for r in e.prot_rows]
        want = [("SET", px(bars, d, round(1.1040 - W, 5))), ("ADVANCE", px(bars, d, round(1.1100 - W, 5)))]
        check(name + " P-1/P-2: first BOS sets protected at L1, next BOS advances to the higher L2", p[:2] == want, f"{p} != {want}")
    both("legal new point", base, s_advance)

    def s_keep(name, bars, d):
        e = run254(bars)
        p = [(r["ev"], r["level"]) for r in e.prot_rows][:2]
        a = [(r["ev"], r["level"]) for r in e.anchor_rows][:2]
        l1, l2 = px(bars, d, round(1.1040 - W, 5)), px(bars, d, round(1.10380 - W, 5))
        ok = p == [("SET", l1), ("KEEP_WORSE", l1)] and a == [("SET", l1), ("MOVE", l2)]
        ch = [x for x in ev(e) if x[0] == "CHOCH"]
        check(name + " P-2/P-3: worse candidate keeps protected, anchor takes it; close within margin no CHOCH",
              ok and not ch, f"prot {p} anchor {a} choch {ch}")
    worse = leg(l2=1.10380)                            # L2 centre 1.10380, swing 1.10330 (wick under L1 1.10350)
    setbar(worse, i_l2, close=1.10348)                 # close 2 points under L1: past the raw price, not the margin (3)
    both("worse candidate", worse, s_keep)

    def s_wick(name, bars, d):
        e = run254(bars)
        ch = [x for x in ev(e) if x[0] == "CHOCH"]
        check(name + " P-4: wick through protected, close back inside -> no CHOCH", not ch, f"{ch}")
    wick = leg(tail=[(1.1170, 4), (1.1260, 6)])
    k = 25 + 2                                         # a bar after the 2nd BOS: wick to 1.1080 (< L2 1.1095), close 1.1180
    setbar(wick, k, lo=1.1080, close=wick[k][4])
    both("wick", wick, s_wick)

    def s_break(name, bars, d):
        e = run254(bars)
        ch = [x for x in ev(e) if x[0] == "CHOCH"]
        want_t = at(bars, k2)
        br = [r for r in e.prot_rows if r["ev"] == "BREAK"]
        ok = len(ch) == 1 and ch[0][2] == want_t and br and br[0]["bar"] == want_t and br[0]["level"] == px(bars, d, round(1.1100 - W, 5))
        st = [s for (tt, s) in e.state_after if tt == want_t]
        check(name + " P-4: close beyond protected by more than the margin -> CHOCH and TRANSITION on that bar",
              ok and st == [TRANS], f"choch {ch} at {tstr(want_t)} break {br[:1]} state {st}")
    brkb = leg(tail=[(1.1170, 4), (1.1060, 5)])        # falls through L2 1.1095 (protected) - first close under 1.10947 is CHOCH
    k2 = next(i for i in range(26, len(brkb)) if brkb[i][4] < 1.10950 - 0.00003)
    both("effective break", brkb, s_break)

    def s_internal(name, bars, d):
        e = run254(bars); old = B.run(bars, True)
        ch = [x for x in ev(e) if x[0] == "CHOCH"]
        ch_old = [x for x in ev(old) if x[0] == "CHOCH"]
        it = e.internal_rows
        check(name + " P-4: internal swing above protected broken -> processed, INTERNAL row, no CHOCH (v2.53: CHOCH)",
              not ch and len(it) == 1 and it[0]["swing_px"] == px(bars, d, 1.1145) and ch_old,
              f"v2.54 choch {ch} internal {it} | v2.53 choch {ch_old}")
    # after the 2nd BOS (protected L2 1.1095): high 1.1260, internal low 1.1150 (swing 1.1145), up to 1.1200, down to 1.1120
    inter = leg(tail=[(1.1260, 4), (1.1150, 4), (1.1200, 3), (1.1120, 3), (1.1300, 6)])
    both("internal low", inter, s_internal)

    # high H1 1.1100 (swing 1.1105, bar 7), two bars down to 1.1070, the third bar closes beyond H1: the dip low
    # (bar 9) confirms one bar AFTER the BOS. The only unprocessed low before the BOS is 1.0995 (bar 2), formed
    # BEFORE the broken high - the old draft (latest unprocessed low before the BOS bar) would have taken it.
    FAST = [(1.1050, 0), (1.1000, 2), (1.1100, 5), (1.1070, 2), (1.1140, 1)]
    def s_missing(name, bars, d):
        e = run254(bars, fallback=False)
        p = [(r["ev"], r["level"]) for r in e.prot_rows]
        bos_t = at(bars, 10)
        older = [s for s in e.sw if s["dir"] == -d and s["bar_time"] < bars[7][0] and s["confirm"] <= bos_t]
        check(name + " P-1/P-6: no pullback swing between the broken high and the BOS -> INVALID; the older swing is not used",
              p[:1] == [("INVALID", None)] and older, f"{p} older {older}")
    both("missing point", path(FAST + [(1.1150, 1), (1.1160, 1)]), s_missing)

    def s_future(name, bars, d):
        e = run254(bars, fallback=False)
        p = [(r["ev"], r["level"]) for r in e.prot_rows][:2]
        l1 = px(bars, d, round(1.1040 - W, 5))
        check(name + " P-1: at a later BOS, a pullback swing confirmed only after that BOS close is not a candidate (KEEP_NONE)",
              p == [("SET", l1), ("KEEP_NONE", l1)], f"{p}")
    # base leg up to H2 (1.1165, bar 16); dip to 1.1120 in 2 bars (bar 18); the next bar closes beyond H2
    fut = path([(1.1050, 0), (1.1000, 2), (1.1100, 5), (1.1040, 3), (1.1160, 6), (1.1120, 2), (1.1200, 1), (1.1210, 1), (1.1220, 1)])
    both("future-confirmed", fut, s_future)

    def s_conf_same(name, bars, d):
        e = run254(bars, fallback=False)
        first = e.prot_rows[0]
        check(name + " P-7: a pullback swing confirmed at the BOS close itself is a candidate",
              first["ev"] == "SET" and first["level"] == px(bars, d, round(1.1070 - W, 5)), f"{e.prot_rows[:2]}")
    # dip low at bar 9 (1.1070); bars 10, 11 rise; bar 11 closes beyond H1 (1.1105) -> confirmation and BOS on one close
    same = path([(1.1050, 0), (1.1000, 2), (1.1100, 5), (1.1070, 2), (1.1110, 2), (1.1150, 2)])
    setbar(same, 11, close=1.1112)
    both("confirmed on the BOS bar", same, s_conf_same)

    # ---- P-5: after a CHOCH, only structure formed AND confirmed after the CHOCH close resolves the transition
    def trans_case(after):
        # protected L1 1.1035 broken at the fall to 1.1010; then `after`
        return path([(1.1050, 0), (1.1000, 2), (1.1100, 5), (1.1040, 3), (1.1160, 6), (1.1010, 6)] + after)
    def choch_t(e):
        return next(r["bar"] for r in e.ctx_rows if r["kind"] == "CHOCH")

    def s_old_low(name, bars, d):
        e = run254(bars); t = choch_t(e)
        k = [x for x in ev(e) if x[2] > t][:1]
        check(name + " P-5: the CHOCH bar's own low, confirmed after the CHOCH, broken -> TRANS_SAMELEG, not TRANS_OK",
              k and k[0][0] == "TRANS_SAMELEG", f"{k}")
    # fall bottoms right after the CHOCH bar: low formed on/before the CHOCH bar, confirmed after; small bounce, then break it
    oldlow = trans_case([(1.1040, 2), (1.0980, 3)])
    both("old low after CHOCH", oldlow, s_old_low)

    def s_new_low(name, bars, d):
        e = run254(bars); t = choch_t(e)
        k = [x for x in ev(e) if x[2] > t and x[0] != "TRANS_SAMELEG"][:1]
        check(name + " P-5: a low formed and confirmed after the CHOCH, effectively broken -> TRANS_OK",
              k and k[0][0] == "TRANS_OK", f"{[x for x in ev(e) if x[2] > t]}")
    newlow = trans_case([(1.1060, 3), (1.1030, 3), (1.1055, 3), (1.0950, 6)])       # lower high 1.1060 < 1.1065: no recovery
    both("new low after CHOCH", newlow, s_new_low)

    def s_old_high(name, bars, d):
        e = run254(bars); old = B.run(bars, True); t = choch_t(e)
        k = [x for x in ev(e) if x[2] > t][:1]
        ko = [x for x in ev(old) if x[2] > choch_t(old)][:1]
        check(name + " P-5: a pre-CHOCH high broken back -> TRANS_SAMELEG, not TRANS_FAIL (v2.53: TRANS_FAIL)",
              k and k[0][0] == "TRANS_SAMELEG" and ko and ko[0][0] == "TRANS_FAIL", f"v2.54 {k} v2.53 {ko}")
    # after the CHOCH, straight back up through the pre-CHOCH high H2 (1.1165) - no new high formed in between
    oldhigh = trans_case([(1.1200, 8)])
    both("old high after CHOCH", oldhigh, s_old_high)

    def s_new_high(name, bars, d):
        e = run254(bars); t = choch_t(e)
        k = [x for x in ev(e) if x[2] > t and x[0] != "TRANS_SAMELEG"][:1]
        check(name + " P-5: a high formed and confirmed after the CHOCH, effectively broken -> TRANS_FAIL",
              k and k[0][0] == "TRANS_FAIL", f"{[x for x in ev(e) if x[2] > t]}")
    newhigh = trans_case([(1.1080, 3), (1.1050, 3), (1.1130, 4)])
    both("new high after CHOCH", newhigh, s_new_high)

    def s_first_bar(name, bars, d):
        e = run254(bars); t = choch_t(e)
        sw = [s for s in e.sw if s["dir"] == -d and s["bar_time"] == t]
        k = [x for x in ev(e) if x[2] > t and x[0] != "TRANS_SAMELEG"][:1]
        check(name + " P-5: a swing on the first bar after the CHOCH (opens at the CHOCH close) counts as new",
              sw and k and k[0][0] == "TRANS_OK", f"swing at CHOCH close {sw} events {[x for x in ev(e) if x[2] > t]}")
    # the CHOCH is the bar that closes under L1; make the NEXT bar the low of the move
    fb = path([(1.1050, 0), (1.1000, 2), (1.1100, 5), (1.1040, 3), (1.1160, 6), (1.1020, 7), (1.1060, 3), (1.0990, 4)])
    ci = next(i for i in range(17, len(fb)) if fb[i][4] < 1.1035 - 0.00003)
    # bar ci closes under L1 (CHOCH); bar ci+1 makes the swing low, then up 2+ bars, then a fall through it
    lowc = fb[ci][4] - 0.0020
    for j, c in ((ci + 1, lowc), (ci + 2, lowc + 0.0020), (ci + 3, lowc + 0.0035), (ci + 4, lowc + 0.0010), (ci + 5, lowc - 0.0030)):
        if j < len(fb):
            fb[j] = [fb[j][0], fb[j - 1][4], round(c + W, 5), round(c - W, 5), round(c, 5)]
    fb = fb[:ci + 6]
    both("first bar after CHOCH", fb, s_first_bar)

    def s_fallback(name, bars, d):
        on, off = run254(bars, fallback=True), run254(bars, fallback=False)
        c_on = [x for x in ev(on) if x[0] == "CHOCH"]; c_off = [x for x in ev(off) if x[0] == "CHOCH"]
        fb = [r for r in on.prot_rows if r["ev"] == "FALLBACK"]
        check(name + " P-6b: protected INVALID, latest opposite swing broken -> CHOCH (FALLBACK); without P-6b no CHOCH",
              len(c_on) == 1 and fb and not c_off and off.internal_rows, f"on {c_on} {fb} | off {c_off} internal {off.internal_rows}")
    # missing-point leg (INVALID), then a pullback low forms (1.1150) and price falls through it
    fbk = path(FAST + [(1.1200, 4), (1.1150, 3), (1.1180, 3), (1.1100, 4)])
    both("fallback", fbk, s_fallback)

    def s_reset(name, bars, d):
        e = run254(bars)
        legs = sorted({r["leg"] for r in e.prot_rows})
        after = [r for r in e.prot_rows if r["leg"] == legs[-1]]
        check(name + " P-2/P-5: a new leg after TRANS_OK starts its own protected (SET / INVALID), not the old leg's",
              len(legs) >= 2 and after and after[0]["ev"] in ("SET", "INVALID") and after[0]["bar"] > choch_t(e), f"{e.prot_rows}")
    both("new leg", newlow, s_reset)

    def s_prefix(name, bars, d):
        full = run254(bars)
        for k in range(8, len(bars) + 1):
            part = run254(bars[:k]); cut = bars[k - 1][0] + H4
            a = [B.ctx_key(r) for r in part.ctx_rows]; b = [B.ctx_key(r) for r in full.ctx_rows if r["bar"] <= cut]
            pa = [(r["ev"], r["bar"], r["level"]) for r in part.prot_rows]; pb = [(r["ev"], r["bar"], r["level"]) for r in full.prot_rows if r["bar"] <= cut]
            if a != b or pa != pb:
                check(name + " no repaint", False, f"cut at bar {k}"); return
        check(name + " no repaint: a run cut at any bar holds exactly the events and protected rows the full run had", True)
    both("prefix", inter, s_prefix)


# ---- real data -------------------------------------------------------------------
def replay(path_csv):
    bars = B.load_h1(path_csv)
    print(f"replay {path_csv}: {len(bars)} H4 bars {tstr(bars[0][0])} .. {tstr(bars[-1][0])}")
    v53 = B.run(bars, True)
    v54 = run254(bars, True)
    v54n = run254(bars, False)
    n = lambda e, k: sum(1 for r in e.ctx_rows if r["kind"] == k)
    print("\nstructure events          v2.53   v2.54   v2.54 without P-6b")
    for k in ("BOS", "CHOCH", "TRANS_OK", "TRANS_FAIL", "TRANS_SAMELEG", "TIMEOUT"):
        print(f"  {k:22s} {n(v53, k):6d}  {n(v54, k):6d}  {n(v54n, k):6d}")
    print(f"  INTERNAL (no state change)    -  {len(v54.internal_rows):6d}  {len(v54n.internal_rows):6d}")
    for e, nm in ((v54, "v2.54"), (v54n, "v2.54 without P-6b")):
        from collections import Counter
        c = Counter(r["ev"] for r in e.prot_rows)
        print(f"\n{nm} protected events: " + ", ".join(f"{k} {c[k]}" for k in ("SET", "ADVANCE", "KEEP_WORSE", "KEEP_NONE", "INVALID", "BREAK", "FALLBACK")))
        legs = {}
        for r in e.prot_rows:
            legs.setdefault(r["leg"], []).append(r["ev"])
        inv_legs = sum(1 for v in legs.values() if v[0] == "INVALID")
        print(f"  legs {len(legs)}, starting INVALID {inv_legs}; trend bars {e.trend_bars}, of them with protected INVALID {e.invalid_bars}"
              f" ({100.0 * e.invalid_bars / max(1, e.trend_bars):.0f}%)")
        ends = Counter(v[-1] for v in legs.values() if v[-1] in ("BREAK", "FALLBACK"))
        print(f"  legs ended by BREAK {ends['BREAK']}, by FALLBACK {ends['FALLBACK']}")
    # time in each state
    from collections import Counter
    for e, nm in ((v53, "v2.53"), (v54, "v2.54"), (v54n, "v2.54 w/o P-6b")):
        c = Counter(s for (_, s) in e.state_after)
        print(f"  {nm:15s} H4 bars  " + "  ".join(f"{k} {c[k]}" for k in (BULL_CTX, BEAR_CTX, TRANS, RANGE)))
    diff = sum(1 for (t, a), (_, b) in zip(v53.state_after, v54.state_after) if a != b)
    dird = sum(1 for (t, a), (_, b) in zip(v53.state_after, v54.state_after)
               if (a in (BULL_CTX, BEAR_CTX) or b in (BULL_CTX, BEAR_CTX)) and a != b)
    print(f"\nH4 bars in a different state v2.53 vs v2.54: {diff} of {len(bars)} ({dird} where at least one side is trending)")
    po, pn = B.multiset_diff(v53.poi_rows, v54.poi_rows)
    print(f"POI events only in v2.53: {len(po)}, only in v2.54: {len(pn)}  (NEW only v2.53 {sum(1 for x in po if x[0]=='NEW')}, only v2.54 {sum(1 for x in pn if x[0]=='NEW')})")
    print(f"max strength v2.53 {max(r['str'] for r in v53.ctx_rows)}, v2.54 {max(r['str'] for r in v54.ctx_rows)}")
    # no repaint
    ok = True
    for k in range(40, len(bars) + 1, 25):
        part = run254(bars[:k]); cut = bars[k - 1][0] + H4
        if [B.ctx_key(r) for r in part.ctx_rows] != [B.ctx_key(r) for r in v54.ctx_rows if r["bar"] <= cut] or \
           [(r["ev"], r["bar"], r["level"]) for r in part.prot_rows] != [(r["ev"], r["bar"], r["level"]) for r in v54.prot_rows if r["bar"] <= cut]:
            ok = False; print(f"  prefix BROKEN at {k}"); break
    print(f"prefix stability (cut every 25 bars): {'OK' if ok else 'BROKEN'}")
    return ok


if __name__ == "__main__":
    if "--replay" in sys.argv:
        sys.exit(0 if replay(sys.argv[sys.argv.index("--replay") + 1]) else 1)
    scenarios()
    print(f"\n{sum(RESULTS)}/{len(RESULTS)} checks as expected")
    sys.exit(0 if all(RESULTS) else 1)
