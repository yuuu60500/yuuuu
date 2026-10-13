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
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import h4_dedup_sim as B                                     # noqa: E402
from h4_dedup_sim import (UP, DOWN, RANGE, BULL_CTX, BEAR_CTX, TRANS, H4, MARGIN_PTS, TRANS_MAX,  # noqa: E402
                          break_up, break_down, pts, tstr)


def brk(d, close, level, mp=MARGIN_PTS):
    return break_up(close, level, mp) if d == UP else break_down(close, level, mp)


def atr_margins(bars, frac, point=B.POINT, fallback=MARGIN_PTS):
    """MarginH4Pts in ATR_FRAC mode, as HMI_Series.mqh computes it: simple ATR(14) over bars
    <= i (0 for i < 14 -> the pips fallback), round(frac * atr / point)."""
    out = []
    for i in range(len(bars)):
        if i < 14:
            out.append(fallback); continue
        tr = 0.0
        for k in range(i - 13, i + 1):
            pc = bars[k - 1][4]
            tr += max(bars[k][2] - bars[k][3], abs(bars[k][2] - pc), abs(bars[k][3] - pc))
        a = tr / 14.0
        out.append(fallback if a <= 0 else int(math.floor(frac * a / point + 0.5)))
    return out


class Engine254(B.Engine):
    """margins: None = the fixed default margin; else a list, points per H4 bar (ATR mode).
    legacy_p1: the v2.54 development build - the candidate checked only the processed flag and
    internal swings were processed only on bars without a BOS (the reviewer's P1, 2026-10-13)."""
    def __init__(self, fallback=True, margins=None, legacy_p1=False):
        super().__init__(dedup=True)
        self.fallback = fallback
        self.margins = margins
        self.legacy = legacy_p1
        self.tidx = None
        self.leg = 0
        self.prot = None          # dict(price, bar_time, confirm, bos, set_at) or None (INVALID / no trend)
        self.anchor = None
        self.prot_rows, self.anchor_rows, self.internal_rows = [], [], []
        self.invalid_bars = 0     # trend bars spent with protected INVALID
        self.trend_bars = 0

    # --- P-1 ------------------------------------------------------------------
    def mp(self, h):
        return MARGIN_PTS if self.margins is None else self.margins[h]

    # the v2.53 detection, with the margin of the bar (ATR mode varies per bar)
    def detect_break(self, r, h):
        vis = r[h][0] + H4
        ih = self.last_unswept(UP, vis)
        if ih >= 0 and brk(UP, r[h][4], self.sw[ih]["price"], self.mp(h)):
            return UP, ih
        il = self.last_unswept(DOWN, vis)
        if il >= 0 and brk(DOWN, r[h][4], self.sw[il]["price"], self.mp(h)):
            return DOWN, il
        return 0, -1

    def consume_same_dir(self, r, h, d, primary):
        vis = r[h][0] + H4
        extra = []
        for i, s in enumerate(self.sw):
            if i == primary or s["dir"] != d or s["swept"] or s["confirm"] > vis:
                continue
            if brk(d, r[h][4], s["price"], self.mp(h)):
                s["swept"] = True
                extra.append((d, s["bar_time"], s["price"]))
        return extra

    def broken_since(self, s, r, h):
        """has any close after the swing's confirmation, up to bar h, effectively broken it?"""
        k = self.tidx[s["bar_time"]] + 1
        while k <= h:
            if r[k][0] + H4 > s["confirm"] and brk(s["dir"], r[k][4], s["price"], self.mp(k)):
                return True
            k += 1
        return False

    def candidate(self, d, primary, r, h, t):
        """d = direction of the BOS; the candidate is an opposite swing formed after the
        primary, confirmed by this close, still unprocessed and (P1 fix) never effectively
        broken by a close since its confirmation. Latest formed wins."""
        best = None
        for s in self.sw:
            if s["dir"] != -d or s["swept"] or s["confirm"] > t or s["bar_time"] <= primary["bar_time"]:
                continue
            if not self.legacy and self.broken_since(s, r, h):
                continue
            if best is None or s["bar_time"] > best["bar_time"]:
                best = s
        return best

    def internal(self, r, h, d):
        """P-4: every confirmed, unprocessed swing of direction d (opposite to the trend) that
        this close effectively breaks is processed; one row, primary = the latest of them."""
        t = r[h][0] + H4
        last = -1
        for i, s in enumerate(self.sw):
            if s["dir"] == d and not s["swept"] and s["confirm"] <= t and brk(d, r[h][4], s["price"], self.mp(h)):
                last = i
        if last < 0:
            return
        sw = self.sw[last]; sw["swept"] = True
        extra = self.consume_same_dir(r, h, d, last)
        self.internal_rows.append(dict(bar=t, dir=d, swing=sw["bar_time"], swing_px=sw["price"], close=r[h][4],
                                       also=len(extra), prot=(self.prot["price"] if self.prot else None), extra=extra))

    def plog(self, rows, ev, d, t, lvl, prev=None):
        rows.append(dict(ev=ev, dir=d, leg=self.leg, bar=t,
                         level=(lvl["price"] if lvl else None), swing=(lvl["bar_time"] if lvl else 0),
                         confirm=(lvl["confirm"] if lvl else 0), bos=(lvl["bos"] if lvl else 0),
                         prev=(prev["price"] if prev else None)))

    def on_bos(self, d, primary, r, h, t, leg_start):
        c = self.candidate(d, primary, r, h, t)
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
        mp = self.mp(h)
        if self.tidx is None or len(self.tidx) < len(r):
            self.tidx = {b[0]: k for k, b in enumerate(r)}
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
            if self.prot is not None and brk(-d, cl, self.prot["price"], mp):
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
                if i >= 0 and brk(-d, cl, self.sw[i]["price"], mp):
                    sw = self.sw[i]; sw["swept"] = True
                    extra = self.consume_same_dir(r, h, -d, i)
                    self.leave_trend("FALLBACK", d, t)
                    self.enter(TRANS, -d, t); self.strength = 0
                    self.log("CHOCH", -d, t, sw, cl, len(extra))
                    if extra: self.dedup_rows.append(dict(bar=t, kind="CHOCH", dir=-d, primary=(sw["bar_time"], sw["price"]), extra=extra))
                    return
            i = self.last_unswept(d, t)
            if i >= 0 and brk(d, cl, self.sw[i]["price"], mp):
                sw = self.sw[i]; sw["swept"] = True
                extra = self.consume_same_dir(r, h, d, i)
                self.strength += 1
                self.log("BOS", d, t, sw, cl, len(extra))
                if extra: self.dedup_rows.append(dict(bar=t, kind="BOS", dir=d, primary=(sw["bar_time"], sw["price"]), extra=extra))
                if not self.legacy:
                    self.internal(r, h, -d)          # P1 fix: what this close broke is processed BEFORE the level is chosen
                self.on_bos(d, sw, r, h, t, False)
                return
            if self.legacy:
                i = self.last_unswept(-d, t)
                if i >= 0 and brk(-d, cl, self.sw[i]["price"], mp):
                    sw = self.sw[i]; sw["swept"] = True
                    extra = self.consume_same_dir(r, h, -d, i)
                    self.internal_rows.append(dict(bar=t, dir=-d, swing=sw["bar_time"], swing_px=sw["price"], close=cl,
                                                   also=len(extra), prot=(self.prot["price"] if self.prot else None), extra=extra))
            else:
                self.internal(r, h, -d)
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
            if not self.legacy:
                self.internal(r, h, -d)              # P1 fix, the first BOS of a leg too
            self.on_bos(d, sw, r, h, t, True)


def run254(bars, fallback=True, margins=None, legacy_p1=False):
    e = Engine254(fallback, margins, legacy_p1)
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


def installed_broken(e, bars, margins=None):
    """every SET / ADVANCE (protected) and SET / MOVE (anchor): was the level already broken by a
    close after its confirmation, up to and including the bar that installed it?"""
    bad = []
    idx = {b[0] + H4: k for k, b in enumerate(bars)}
    for rows, evs in ((e.prot_rows, ("SET", "ADVANCE")), (e.anchor_rows, ("SET", "MOVE"))):
        for r in rows:
            if r["ev"] not in evs or r["level"] is None:
                continue
            h = idx[r["bar"]]
            for k in range(h + 1):
                if bars[k][0] + H4 <= r["confirm"]:
                    continue
                mpk = MARGIN_PTS if margins is None else margins[k]
                if brk(-r["dir"], bars[k][4], r["level"], mpk):
                    bad.append((r["ev"], tstr(r["bar"]), r["level"], tstr(bars[k][0] + H4))); break
    return bad


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

    # ---- reviewer P1 (2026-10-13): ATR margin shrinks; one close breaks the primary high AND the
    # higher pullback low formed after it. That low must not become protected / anchor.
    # Points over 1.00000: protected B 45 (bar 7), primary P 140 (bar 11), pullback low L 146 (bar 17,
    # above P - earlier closes 148..152 stayed within the 15-point margin); bar 20 (margin 1) closes 143.
    ROWS = [(60, 40, 50), (55, 30, 35), (45, 20, 30), (60, 28, 55), (80, 50, 75), (100, 70, 90), (95, 60, 65),
            (75, 45, 50), (90, 48, 85), (125, 80, 120), (135, 110, 130), (140, 120, 125), (138, 124, 132),
            (139, 131, 135), (150, 134, 148), (153, 147, 150), (152, 147, 148), (154, 146, 149), (155, 147, 152),
            (156, 147, 150), (151, 140, 143), (146, 143, 144), (147, 143, 146), (148, 145, 147)]
    t0 = int(B.dt.datetime(2026, 9, 7, 0, 0, tzinfo=B.dt.timezone.utc).timestamp())
    atrb, prev = [], 1.0 + ROWS[0][2] * 1e-5
    for i, (hi, lo, cl) in enumerate(ROWS):
        atrb.append([t0 + i * H4, round(prev, 5), round(1.0 + hi * 1e-5, 5), round(1.0 + lo * 1e-5, 5), round(1.0 + cl * 1e-5, 5)])
        prev = 1.0 + cl * 1e-5
    MG = [15] * 20 + [1] * (len(ROWS) - 20)

    def lv(bars, d, p_):
        return px(bars, d, round(1.0 + p_ * 1e-5, 5))

    def s_atr(name, bars, d):
        old = run254(bars, margins=MG, legacy_p1=True); new = run254(bars, margins=MG)
        t20, t21 = at(bars, 20), at(bars, 21)
        o = [(r["ev"], r["level"]) for r in old.prot_rows if r["bar"] == t20]
        n = [(r["ev"], r["level"]) for r in new.prot_rows if r["bar"] == t20]
        na = [(r["ev"], r["level"]) for r in new.anchor_rows if r["bar"] == t20]
        it = [x for x in new.internal_rows if x["bar"] == t20]
        ch_o = [x for x in ev(old) if x[0] == "CHOCH" and x[2] == t21]
        ch_n = [x for x in ev(new) if x[0] == "CHOCH"]
        bos = [x for x in ev(new) if x[2] == t20]
        ok = (o == [("ADVANCE", lv(bars, d, 146))] and ch_o                       # the development build: defect reproduced
              and bos == [("BOS", d, t20)] and n == [("KEEP_NONE", lv(bars, d, 45))] and na == [("KEEP_NONE", lv(bars, d, 45))]
              and len(it) == 1 and it[0]["swing_px"] == lv(bars, d, 146) and not ch_n)
        check(name + " P1: a close that breaks the primary and a higher pullback low -> BOS, the low processed (INTERNAL),"
                     " protected / anchor kept; no CHOCH next bar (dev build: installs it, CHOCH)",
              ok, f"dev {o} choch {ch_o} | fixed bos {bos} prot {n} anchor {na} internal {it} choch {ch_n}")
    both("ATR margin shrinks, leg running", atrb, s_atr)

    def s_atr_first(name, bars, d):
        mg = MG[9:]
        old = run254(bars, margins=mg, legacy_p1=True); new = run254(bars, margins=mg)
        t = at(bars, 11)
        o = [(r["ev"], r["level"]) for r in old.prot_rows if r["bar"] == t]
        n = [(r["ev"], r["level"]) for r in new.prot_rows if r["bar"] == t]
        it = [x for x in new.internal_rows if x["bar"] == t]
        k = [x for x in ev(new) if x[0] == "BOS"]
        check(name + " P1: the first BOS of a leg on such a close -> INVALID, not the broken low (dev build: SET it)",
              o == [("SET", lv(bars, d, 146))] and k and k[0][2] == t and n == [("INVALID", None)] and len(it) == 1
              and not [x for x in ev(new) if x[0] == "CHOCH"],
              f"dev {o} | fixed bos {k} prot {n} internal {it} events {ev(new)}")
    s_atr_first("ATR margin shrinks, first BOS of a leg [bull]", [tuple(b) for b in atrb[9:]], UP)

    def s_atr_first_bear(name, bars, d):
        # Mirror image: the same close breaks the primary LOW down and the pullback HIGH up. RANGE / TRANSITION
        # detection is v2.53's, up first - the high wins, so this is a BOS UP of that high (a bull leg), and the
        # bear-side defect cannot arise on a leg's first BOS. Nothing broken is installed either way.
        new = run254(bars, margins=MG[9:])
        k = [x for x in ev(new) if x[0] == "BOS"]
        n = [(r["ev"], r["level"]) for r in new.prot_rows][:1]
        check(name + " P1 mirror: a close breaking both ways in RANGE is a BOS UP (v2.53 order); INVALID, nothing broken installed",
              k and k[0][1] == UP and n == [("INVALID", None)] and not installed_broken(new, bars, MG[9:]), f"{k} {n}")
    s_atr_first_bear("ATR margin shrinks, first BOS of a leg [bear]", [tuple(b) for b in mirror_bars(atrb[9:])], DOWN)

    def s_invariant(name, bars, d):
        for mg, tag in ((None, "fixed margin"), (MG, "per-bar margin")):
            e = run254(bars, margins=mg)
            bad = installed_broken(e, bars, mg)
            if bad:
                check(f"{name} invariant ({tag})", False, f"{bad}"); return
        check(name + " invariant: no level is installed (SET / ADVANCE / MOVE) once a close since its confirmation broke it", True)
    both("installed levels", atrb, s_invariant)

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
    # reviewer P1 (2026-10-13): the development build vs the fix, fixed margin and ATR margin
    print("\nP1 - a level installed although a close since its confirmation had broken it:")
    for tag, mg in (("fixed margin (default 3 points)", None), ("ATR_FRAC 0.20", atr_margins(bars, 0.20))):
        dev = run254(bars, margins=mg, legacy_p1=True); fix = run254(bars, margins=mg)
        bd, bf = installed_broken(dev, bars, mg), installed_broken(fix, bars, mg)
        cd = sum(1 for r in dev.ctx_rows if r["kind"] == "CHOCH"); cf = sum(1 for r in fix.ctx_rows if r["kind"] == "CHOCH")
        sd = sum(1 for (_, a), (_, b) in zip(dev.state_after, fix.state_after) if a != b)
        print(f"  {tag:32s} dev build {len(bd):3d}, fixed {len(bf):3d};  CHOCH dev {cd} / fixed {cf};"
              f"  INTERNAL dev {len(dev.internal_rows)} / fixed {len(fix.internal_rows)};  H4 bars in another state {sd}")
        for x in bd[:3]:
            print(f"      dev: {x[0]} at {x[1]} level {x[2]} - broken by the close of {x[3]}")
        ok_p1 = not bf
        if not ok_p1:
            print("      !! the fixed engine installed a broken level")
    # no repaint
    ok = ok_p1
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
