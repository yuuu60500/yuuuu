"""v2.56 strength score (docs/02 BRI-13 draft) - offline model of the definition and its paired scenarios.

Not the MQL implementation; it fixes what each scenario must give and measures the offline distribution the
provisional thresholds come from. Display only (Rule 69): the score never feeds a rule, so nothing here
touches the H4 / POI / session / MODEL chain - the H4 context comes from the unchanged v2.54 model.

Definition (all prices in integer points, so Python and MQL agree to the last digit):

  bar h          the H4 bar just closed and processed by the context engine; d = +1 BULLISH, -1 BEARISH
                 after processing h (RANGE / TRANSITION -> NODIR)
  NODATA         h < 14 (fewer than 15 closed H4 bars: TR of bar h-13 needs the close of h-14), or T = 0
  net            C[h] - C[h-12]                       (12 closes, the last 12 H4 bars)
  T              sum of TR[k], k = h-13 .. h          (= 14 x ATR(14) in points, as SeriesComputeATR)
                 TR[k] = max(H-L, |H - C[k-1]|, |L - C[k-1]|)
  x              d * net                              (progress in the context direction)
  S              x <= 0 -> 0 ;  else min(100, floor((700 x + T) / (2 T)))
                 = round-half-up of 100 * (x / ATR) / CAP with CAP = 4 ATR (350 x / T, exact integers)
  tier           S = 0 NONE (no progress) ; 1 .. T1-1 WEAK ; T1 .. T2-1 MED ; >= T2 STRONG

    python3 tools/strength_sim.py                       scenarios, both directions
    python3 tools/strength_sim.py --replay <H1 csv>     real data: prefix stability, mirror, distribution
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import h4_dedup_sim as B                                        # noqa: E402
import h4_protect_sim as P                                      # noqa: E402
from h4_dedup_sim import BULL_CTX, BEAR_CTX, TRANS, RANGE, H4, tstr  # noqa: E402

CAP_X2 = 700          # 2 * 350: S = 350 x / T  <=>  100 * (x / ATR) / 4
WINDOW = 12           # closes
ATR_N = 14
T1, T2 = 34, 64       # provisional tier thresholds (offline EURUSD, see --replay); MT5 distribution decides


def p(v):
    return int(round(v / B.POINT))


def tr_pts(bars, k):
    pc = bars[k - 1][4]
    hi, lo = bars[k][2], bars[k][3]
    return max(p(hi - lo), abs(p(hi - pc)), abs(p(lo - pc)))


def score(bars, h, ctx):
    """-> dict(state, dir, S, tier, net, T). Uses bars[h-14 .. h] only."""
    r = dict(state="NODATA", dir=0, S=None, tier="NA", net=None, T=None)
    if h < ATR_N:
        return r
    T = sum(tr_pts(bars, k) for k in range(h - ATR_N + 1, h + 1))
    net = p(bars[h][4] - bars[h - WINDOW][4])
    r.update(net=net, T=T)
    if T <= 0:
        return r
    d = 1 if ctx == BULL_CTX else -1 if ctx == BEAR_CTX else 0
    if d == 0:
        r["state"] = "NODIR"
        return r
    x = d * net
    S = 0 if x <= 0 else min(100, (CAP_X2 * x + T) // (2 * T))
    r.update(state="OK", dir=d, S=S, tier=tier(S))
    return r


def tier(S):
    return "NONE" if S == 0 else "WEAK" if S < T1 else "MED" if S < T2 else "STRONG"


# ---- scenario bars --------------------------------------------------------------------------------------------
BASE = 1.10000
T0 = int(B.dt.datetime(2026, 9, 7, 0, 0, tzinfo=B.dt.timezone.utc).timestamp())


def make(closes, wicks):
    """closes / wicks in points from BASE; wicks[k] = (up, down) beyond max(o, c) / min(o, c); o = previous close,
    so TR[k] = |dC| + up + down for k >= 1."""
    bars = []
    for i, c in enumerate(closes):
        o = closes[i - 1] if i else c
        up, dn = wicks[i]
        bars.append((T0 + i * H4, round(BASE + o * B.POINT, 5), round(BASE + (max(o, c) + up) * B.POINT, 5),
                     round(BASE + (min(o, c) - dn) * B.POINT, 5), round(BASE + c * B.POINT, 5)))
    return bars


def target(x, T, n=15, pre=None):
    """n bars, last = h = n - 1; flat until h-12, then 12 rising steps summing to x (x may be negative: falling);
    wicks of bars h-13 .. h fill T - |x| exactly. pre: closes to put before (bars 0 .. h-15 when n > 15)."""
    h = n - 1
    closes = [0] * n
    steps = [x // WINDOW] * WINDOW
    steps[-1] += x - sum(steps)
    for i, s in enumerate(steps):
        closes[h - WINDOW + 1 + i] = closes[h - WINDOW + i] + s
    if pre:
        for i, c in enumerate(pre):
            closes[i] = c
    rest = T - sum(abs(closes[k] - closes[k - 1]) for k in range(h - ATR_N + 1, h + 1))
    assert rest >= 0, (x, T)
    wicks = [(5, 5)] * n
    q, m = divmod(rest, ATR_N)
    for j, k in enumerate(range(h - ATR_N + 1, h + 1)):
        e = q + (1 if j < m else 0)
        wicks[k] = (e - e // 2, e // 2)
    return make(closes, wicks)


def mirror(bars):
    return [tuple(b) for b in P.mirror_bars(bars)]


RESULTS = []
ROWS = []


def check(name, cond, detail=""):
    RESULTS.append(bool(cond))
    print(f"{'PASS' if cond else 'FAIL'}  {name}" + ("" if cond else f"\n        !! {detail}"))


def pair(name, bars, h, ctx_bull, want):
    """bull case with ctx_bull, mirrored bars with the mirrored context; want = (state, S, tier) for both."""
    flip = {BULL_CTX: BEAR_CTX, BEAR_CTX: BULL_CTX}
    for nm, bb, cx in (("bull", bars, ctx_bull), ("bear", mirror(bars), flip.get(ctx_bull, ctx_bull))):
        r = score(bb, h, cx)
        got = (r["state"], r["S"], r["tier"])
        check(f"{name} [{nm}]  -> {got[0]} S={got[1]} {got[2]}", got == want,
              f"want {want}, got {got} (net {r['net']}, T {r['T']})")
        if nm == "bull":
            ROWS.append((name, cx, r["net"], r["T"], got))


def scenarios():
    print("== definition scenarios (each also mirrored: bear bars + BEARISH = same result) ==")
    b = target(700, 7000)
    pair("S01 15 bars, h = 14: first bar with a score", b, 14, BULL_CTX, ("OK", 35, "MED"))
    pair("S01 h = 13: 14 bars -> NODATA", b, 13, BULL_CTX, ("NODATA", None, "NA"))
    flat = make([0] * 15, [(0, 0)] * 15)
    pair("S02 T = 0 (15 identical bars) -> NODATA, not 0", flat, 14, BULL_CTX, ("NODATA", None, "NA"))
    pair("S03 net = 0 -> 0 NONE", target(0, 7000), 14, BULL_CTX, ("OK", 0, "NONE"))
    pair("S03 net against the context (-400) -> 0 NONE, never negative", target(-400, 7000), 14, BULL_CTX, ("OK", 0, "NONE"))
    pair("S04 x / T = 2 / 7 (4 ATR) -> 100", target(2000, 7000), 14, BULL_CTX, ("OK", 100, "STRONG"))
    pair("S04 6.5 ATR -> capped at 100", target(3250, 7000), 14, BULL_CTX, ("OK", 100, "STRONG"))
    pair("S04 99.5 exactly -> 100 (half up)", target(1990, 7000), 14, BULL_CTX, ("OK", 100, "STRONG"))
    pair("S04 99.45 -> 99", target(1989, 7000), 14, BULL_CTX, ("OK", 99, "STRONG"))
    pair("S05 0.5 exactly -> 1 WEAK (smallest positive)", target(10, 7000), 14, BULL_CTX, ("OK", 1, "WEAK"))
    pair("S05 0.45 -> 0 NONE", target(9, 7000), 14, BULL_CTX, ("OK", 0, "NONE"))
    pair("S06 33.5 -> 34 = T1 MED", target(670, 7000), 14, BULL_CTX, ("OK", 34, "MED"))
    pair("S06 33.45 -> 33 WEAK", target(669, 7000), 14, BULL_CTX, ("OK", 33, "WEAK"))
    pair("S07 63.5 -> 64 = T2 STRONG", target(1270, 7000), 14, BULL_CTX, ("OK", 64, "STRONG"))
    pair("S07 63.45 -> 63 MED", target(1269, 7000), 14, BULL_CTX, ("OK", 63, "MED"))
    up = target(1400, 7000)
    pair("S08 same bars, opposite context (rise under BEARISH) -> 0 NONE", up, 14, BEAR_CTX, ("OK", 0, "NONE"))
    pair("S08 same bars, own context -> 70 STRONG", up, 14, BULL_CTX, ("OK", 70, "STRONG"))
    pair("S09 RANGE -> NODIR", up, 14, RANGE, ("NODIR", None, "NA"))
    pair("S09 TRANSITION -> NODIR", up, 14, TRANS, ("NODIR", None, "NA"))
    r = score(up, 14, TRANS)
    check("S09 NODIR still logs net / T", r["net"] == 1400 and r["T"] == 7000, str(r))

    print("\n== window: which bars the score reads ==")
    long_ = target(1400, 7000, n=20, pre=[0, 300, -500, 900, 50])   # h = 19; bars 0 .. 4 differ from the flat start
    base = score(long_, 19, BULL_CTX)
    check(f"S10 bars before h-14 do not count (bars 0 .. 4 changed) -> S {base['S']}", base["S"] == 70, str(base))
    mod = list(long_)
    t, o, hi, lo, c = mod[19 - 14]
    mod[19 - 14] = (t, o, hi + 2000 * B.POINT, lo, c)               # h-14: only its close enters (TR of h-13)
    check("S10 a wick on h-14 does not count (only its close enters TR[h-13])", score(mod, 19, BULL_CTX)["S"] == 70)
    mod = list(long_)
    t, o, hi, lo, c = mod[19 - 14]
    mod[19 - 14] = (t, o, max(hi, c + 0.00300), lo, round(c + 0.00300, 5))   # close of h-14 raised 300 points
    check("S10 the close of h-14 counts (gap into h-13 enlarges TR[h-13])", score(mod, 19, BULL_CTX)["T"] > 7000)
    mod = list(long_)
    t, o, hi, lo, c = mod[19 - 13]
    mod[19 - 13] = (t, o, round(hi + 0.00100, 5), lo, c)
    r2 = score(mod, 19, BULL_CTX)
    check(f"S10 a wick on h-13 counts (TR window) -> T {r2['T']}, S {r2['S']}", r2["T"] == 7100 and r2["S"] == 69, str(r2))
    nxt = long_ + [(long_[-1][0] + H4, long_[-1][4], 1.2, 1.0, 1.15)]
    check("S11 a later bar never changes the score of h (no future)", score(nxt, 19, BULL_CTX) == base)
    ep = list(long_)
    t, o, hi, lo, c = ep[19 - 12]
    ep[19 - 12] = (t, o, hi, round(lo - 0.00200, 5), round(c - 0.00200, 5))   # spike close at h-12 (the endpoint)
    r3 = score(ep, 19, BULL_CTX)
    check(f"S12 the close of h-12 is an endpoint: 200 points lower -> net {r3['net']}, S {r3['S']} (known sensitivity)",
          r3["net"] == 1600 and r3["S"] != 70, str(r3))
    gap = target(700, 7000)
    t, o, hi, lo, c = gap[10]
    gap[10] = (t, round(o + 0.00300, 5), round(hi + 0.00300, 5), round(min(lo + 0.00300, c), 5), c)   # opens 300 above C[9]
    rg = score(gap, 14, BULL_CTX)
    check(f"S13 a gap counts through the previous close (TR, not H-L) -> T {rg['T']}", rg["T"] > 7000, str(rg))

    print("\n== with the H4 context engine (v2.54 rules, unchanged in v2.55 / v2.56) ==")
    piv = [(1.1000, 0), (1.1100, 6), (1.1040, 3), (1.1160, 6), (1.1100, 3), (1.1220, 6), (1.1050, 8), (1.1110, 3),
           (1.0990, 6), (1.1040, 3), (1.0930, 6), (1.0980, 3), (1.0870, 5)]
    bars = [tuple(x) for x in P.path(piv)]
    for nm, bb in (("bull", bars), ("bear", mirror(bars))):
        e = P.run254(bb)
        st = {t: s for t, s in e.state_after}
        evs = [(r["kind"], r["bar"]) for r in e.ctx_rows]
        ch = [t for k, t in evs if k == "CHOCH"]
        ok = [t for k, t in evs if k in ("TRANS_OK", "TRANS_FAIL")]
        bos = [t for k, t in evs if k == "BOS"]
        idx = {bb[i][0] + H4: i for i in range(len(bb))}
        c1 = bool(ch)
        for t in ch:
            c1 &= score(bb, idx[t], st[t])["state"] == "NODIR" and score(bb, idx[t] - 1, st[t - H4])["state"] == "OK"
        check(f"E01 [{nm}] CHOCH bar -> NODIR on that bar; the bar before is scored ({len(ch)} CHOCH)", c1,
              f"events {[(k, tstr(t)) for k, t in evs]}")
        c2 = bool(ok)
        for t in ok:
            r = score(bb, idx[t], st[t])
            c2 &= r["state"] == "OK" and r["dir"] == (1 if st[t] == BULL_CTX else -1)
        check(f"E02 [{nm}] TRANS_OK / TRANS_FAIL bar -> scored in the new direction on that bar ({len(ok)})", c2,
              f"events {[(k, tstr(t)) for k, t in evs]}")
        trend = [h for h in range(ATR_N, len(bb)) if st[bb[h][0] + H4] in (BULL_CTX, BEAR_CTX)]
        c3 = bool(bos) and all(score(bb, h, st[bb[h][0] + H4])["state"] == "OK" for h in trend)
        check(f"E03 [{nm}] every trend bar from h = 14 is scored, BOS bars included ({len(trend)} bars, {len(bos)} BOS)", c3)
    # str independence: two histories, identical last 15 bars, different BOS counts before -> same S
    a = target(1400, 7000, n=40, pre=[0] * 25)
    bpre = [((i % 6) * 120 - 300) for i in range(25)]
    b2 = target(1400, 7000, n=40, pre=bpre)
    check("E04 identical last 15 bars, different history before -> identical score (independent of `str` / leg)",
          score(a, 39, BULL_CTX) == score(b2, 39, BULL_CTX))


def replay(path_csv):
    bars = B.load_h1(path_csv)
    print(f"replay {path_csv}: {len(bars)} H4 bars {tstr(bars[0][0])} .. {tstr(bars[-1][0])}")
    e = P.run254(bars)
    st = [s for _, s in e.state_after]
    rows = [score(bars, h, st[h]) for h in range(len(bars))]
    # prefix: the score of h from a run that ends at h
    bad = 0
    for h in range(40, len(bars), 37):
        ep = P.run254(bars[:h + 1])
        if score(bars[:h + 1], h, ep.state_after[-1][1]) != rows[h]:
            bad += 1
    check(f"R1 prefix: score of h from bars[:h+1] equals the full run (every 37th bar from 40)", bad == 0, f"{bad} differ")
    mb = mirror(bars)
    em = P.run254(mb)
    flip = {BULL_CTX: BEAR_CTX, BEAR_CTX: BULL_CTX}
    smis = sum(1 for (_, a), (_, b) in zip(e.state_after, em.state_after) if flip.get(a, a) != b)
    mrows = [score(mb, h, em.state_after[h][1]) for h in range(len(mb))]
    dif = sum(1 for a, b in zip(rows, mrows) if (a["state"], a["S"]) != (b["state"], b["S"]))
    check(f"R2 mirror: mirrored bars give the mirrored context on every bar and the same score ({dif} differ, "
          f"context {smis} differ)", dif == 0 and smis == 0)
    from collections import Counter
    c = Counter(r["state"] for r in rows)
    ok = [r for r in rows if r["state"] == "OK"]
    pos = sorted(r["S"] for r in ok if r["S"] > 0)
    xs = sorted(14 * r["dir"] * r["net"] / r["T"] for r in ok)          # x / ATR

    def pct(v, q):
        k = (len(v) - 1) * q / 100.0
        f = int(k); cc = min(f + 1, len(v) - 1)
        return v[f] + (v[cc] - v[f]) * (k - f)
    print(f"\nstates: OK {c['OK']} / NODIR {c['NODIR']} / NODATA {c['NODATA']}")
    print("x / ATR on OK bars: " + "  ".join(f"P{q} {pct(xs, q):.2f}" for q in (10, 25, 33, 50, 67, 75, 90, 95)) +
          f"  (<= 0: {sum(1 for v in xs if v <= 0)} of {len(xs)})")
    print(f"S on OK bars: S = 0 {len(ok) - len(pos)}, S = 100 {sum(1 for v in pos if v == 100)} "
          f"({100.0 * sum(1 for v in pos if v == 100) / len(ok):.1f}% of OK bars; CAP = 4 ATR ~ P90 of x / ATR)")
    print("S > 0: " + "  ".join(f"P{q} {pct(pos, q):.1f}" for q in (33, 50, 67)) +
          f"  -> provisional T1 = round(P33) = {round(pct(pos, 33))}, T2 = round(P67) = {round(pct(pos, 67))}")
    tc = Counter(r["tier"] for r in ok)
    print("tiers (T1 = %d, T2 = %d): " % (T1, T2) + "  ".join(f"{k} {tc[k]}" for k in ("NONE", "WEAK", "MED", "STRONG")))
    return all(RESULTS)


def main():
    if len(sys.argv) > 2 and sys.argv[1] == "--replay":
        ok = replay(sys.argv[2])
    else:
        scenarios()
        print("\nscenario inputs (bull case): name / context / net / T / result")
        for r in ROWS:
            print(f"  {r[0][:58]:58s} {r[1]:10s} net {str(r[2]):>6s}  T {str(r[3]):>5s}  {r[4]}")
        ok = all(RESULTS)
    print(f"\n{sum(RESULTS)}/{len(RESULTS)} {'PASS' if ok else 'FAIL'}")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
