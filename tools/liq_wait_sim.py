"""Offline model of the v2.51 liquidity-history wait (A-47 / A-49 / A-50).

Mirrors, function for function, what HMI_LiquidityLevels.mqh and OnTimer do
with the replay history before the M5 window:

  LiqReplayAvail   how far back a replay over the loaded bars is valid
  LiqHistoryFloor  earliest bar a program can ever get (server first bar, or
                   the "Max bars in chart" cap)
  LiqStartLost     is an unreached item lost for good, or only pending?
  LiqReplay        per-item: replayed / lost / pending; WAITING iff pending
  LiqHistoryProbe  timer probe: "" or ARRIVED / BEFORE_FLOOR / SETTLED
  OnTimer          fast probes, then slow ones; never READY without a rebuild

against a modelled terminal whose history arrives late, whose server metadata
reports 0 for a while, whose series may be capped, and whose market has
weekends and holiday closures. Each scenario checks

  1. the first build's classification (lost vs pending) is the right one
  2. the indicator never reports READY while an item is still pending
  3. at most one timer-driven rebuild, and that rebuild is READY (no loop)
  4. the final per-item result - classification, and for a replayed item the
     exact bars and ATR values its replay reads - equals a build made with
     the history present from the start

    python3 tools/liq_wait_sim.py            v2.51 logic
    python3 tools/liq_wait_sim.py --v250     the v2.50 logic, as a control: it
                                             must FAIL the mixed-history and the
                                             late-arrival scenarios

It models the rules, not MQL5: a pass here does not replace compiling and
running the indicator. In particular SERIES_SERVER_FIRSTDATE timing and the
Bars() / TERMINAL_MAXBARS cap are modelled as documented, not observed.
"""
import datetime as dt

M5 = 300
DAY = 86400
FAST_TRIES = 60


def ts(s):
    return int(dt.datetime.strptime(s, "%Y-%m-%d %H:%M").replace(tzinfo=dt.timezone.utc).timestamp())


def calendar(t0, t1, closures=()):
    """M5 bar open times in [t0, t1): Mon-Fri, minus closure ranges."""
    out, t = [], t0 - t0 % M5
    while t < t1:
        wd = dt.datetime.fromtimestamp(t, dt.timezone.utc).weekday()
        if wd < 5 and not any(a <= t < b for a, b in closures):
            out.append(t)
        t += M5
    return out


class Terminal:
    """What a program can read at one moment."""

    def __init__(self, srv_first, now, closures=(), maxbars=0):
        self.all = calendar(srv_first, now, closures)       # the server's M5 history
        self.srv_first = self.all[0]
        self.local_from = None                              # earliest bar held locally
        self.meta = False                                   # SERVER_FIRSTDATE known?
        self.maxbars = maxbars

    def series(self):
        s = [t for t in self.all if self.local_from is not None and t >= self.local_from]
        if self.maxbars and len(s) > self.maxbars:
            s = s[-self.maxbars:]
        return s

    # --- the MQL calls the module makes ------------------------------------
    def CopyRates(self, t_from, t_to):
        return [t for t in self.series() if t_from <= t <= t_to]

    def SERVER_FIRSTDATE(self):
        return self.srv_first if self.meta else 0

    def TERMINAL_FIRSTDATE(self):
        return self.local_from or 0

    def Bars(self):
        return len(self.series())

    def iTime_oldest(self):
        s = self.series()
        return s[0] if s else 0


# ---- mirrors of HMI_LiquidityLevels.mqh ------------------------------------
def LiqReplayAvail(bars, atr_mode):
    if not bars:
        return 0
    if atr_mode:
        return bars[14] if len(bars) > 14 else 0
    return bars[0]


def LiqHistoryFloor(term):
    srv = term.SERVER_FIRSTDATE()
    cap = 0
    tot = term.Bars()
    if term.maxbars > 0 and tot > 0 and tot >= term.maxbars:
        cap = term.iTime_oldest()
    return srv if srv > cap else cap


def LiqStartLost(start, bars, hfloor, term_first):
    if hfloor > 0 and start < hfloor:
        return True
    if bars and hfloor > 0 and bars[0] <= hfloor:
        return True
    if bars and term_first > 0 and term_first <= start - 3 * DAY:
        return True
    return False


def atr_series(bars):
    """Only the bar TIMES matter for this model; 'ATR present' = index >= 14."""
    return [i >= 14 for i in range(len(bars))]


def LiqReplay(term, items, first, atr_mode):
    need = min([first] + [s for s in items.values()])
    res, pend = {}, []
    if need >= first:
        return res, pend
    lr = term.CopyRates(need - 3 * DAY, first - 1)
    avail = LiqReplayAvail(lr, atr_mode) or first
    hfloor = LiqHistoryFloor(term)
    tfst = term.TERMINAL_FIRSTDATE()
    atr = atr_series(lr)
    for name, start in sorted(items.items()):
        if start < avail:
            if LiqStartLost(start, lr, hfloor, tfst):
                res[name] = ("lost",)
            else:
                res[name] = ("pending",)
                pend.append(start)
        else:
            k = next(i for i, t in enumerate(lr) if t >= start)
            res[name] = ("replayed", tuple(lr[k:]), tuple(atr[k:]) if atr_mode else ())
    return res, pend


def LiqHistoryProbe(term, pend, first, atr_mode):
    hfloor = LiqHistoryFloor(term)
    tfst = term.TERMINAL_FIRSTDATE()
    target = 0
    for s in pend:
        if not LiqStartLost(s, [], hfloor, tfst) and (target == 0 or s < target):
            target = s
    if target == 0:
        return "BEFORE_FLOOR"
    tmp = term.CopyRates(target - 3 * DAY, first - 1)
    if not tmp:
        return ""
    avail = LiqReplayAvail(tmp, atr_mode)
    if avail > 0 and avail <= target:
        return "ARRIVED"
    if LiqStartLost(target, tmp, hfloor, tfst):
        return "SETTLED"
    return ""


# ---- v2.50, for the control run ----------------------------------------------
def LiqReplay_v250(term, items, first, atr_mode):
    """One verdict for all items, from the OLDEST start only."""
    need = min([first] + [s for s in items.values()])
    res = {}
    if need >= first:
        return res, []
    lr = term.CopyRates(need - 3 * DAY, first - 1)
    avail = LiqReplayAvail(lr, atr_mode) or first
    srv = term.SERVER_FIRSTDATE()
    waiting = avail > need and (srv <= 0 or srv <= need)
    atr = atr_series(lr)
    for name, start in sorted(items.items()):
        if start < avail:
            res[name] = ("pending",) if waiting else ("lost",)
        else:
            k = next(i for i, t in enumerate(lr) if t >= start)
            res[name] = ("replayed", tuple(lr[k:]), tuple(atr[k:]) if atr_mode else ())
    return res, ([need] if waiting else [])


def probe_v250(term, pend, first, atr_mode):
    need = pend[0]
    tmp = term.CopyRates(need - 3 * DAY, first - 1)
    avail = LiqReplayAvail(tmp, atr_mode)
    if avail > 0 and avail <= need:
        return "ARRIVED"
    srv = term.SERVER_FIRSTDATE()
    if srv > 0 and srv > need:
        return "GIVE_UP"                 # v2.50: READY without a rebuild
    return ""


# ---- the indicator around it (OnCalculate first build + OnTimer) ------------
V250 = False


def run(sc, max_attempts=200):
    term = sc["term"]()
    term.local_from = sc["local_at_start"]
    term.meta = sc.get("meta_at", 0) == 0
    first, items, atr = sc["first"], sc["items"], sc.get("atr", False)

    replay = LiqReplay_v250 if V250 else LiqReplay
    res, pend = replay(term, items, first, atr)
    first_build = {k: v[0] for k, v in res.items()}
    log = [f"build 1: {'WAITING' if pend else 'READY'} {first_build}"]
    rebuilds, attempt, slow, ever_false_ready = 0, 0, False, False
    while pend and attempt < max_attempts:
        attempt += 1
        if attempt == sc.get("meta_at", -1):
            term.meta = True
        if attempt == sc.get("arrive_at", -1):
            term.local_from = term.srv_first
        why = (probe_v250 if V250 else LiqHistoryProbe)(term, pend, first, atr)
        if V250 and (why == "GIVE_UP" or (not why and attempt >= FAST_TRIES)):
            log.append(f"attempt {attempt}: {why or 'MAX_TRIES'} -> READY without rebuild")
            pend = []                    # v2.50 set READY here; the items stay UNKNOWN
            break
        if why:
            res, pend = replay(term, items, first, atr)
            rebuilds += 1
            log.append(f"attempt {attempt}: {why} -> rebuild -> {'WAITING' if pend else 'READY'}")
            if pend:
                ever_false_ready = True     # a rebuild that does not settle = a loop
            break
        if attempt == FAST_TRIES:
            slow = True
            log.append(f"attempt {attempt}: SLOW (still WAITING)")
    final_state = "WAITING" if pend else "READY"

    ref_term = sc["term"]()
    ref_term.local_from, ref_term.meta = ref_term.srv_first, True
    ref, _ = LiqReplay(ref_term, items, first, atr)
    return dict(first_build=first_build, final=res, ref=ref, state=final_state, rebuilds=rebuilds,
                attempts=attempt, slow=slow, loop=ever_false_ready, log=log)


def norm(res):
    """What the indicator actually holds: pending and lost are both UNKNOWN."""
    return {k: (("unknown",) if v[0] in ("pending", "lost") else v) for k, v in res.items()}


def check(name, sc, r):
    errs = []
    if r["first_build"] != sc["expect_first"]:
        errs.append(f"first build {r['first_build']} != {sc['expect_first']}")
    if r["state"] != sc["expect_state"]:
        errs.append(f"final state {r['state']} != {sc['expect_state']}")
    if r["rebuilds"] > 1 or r["loop"]:
        errs.append("more than one timer rebuild / rebuild did not settle")
    if r["state"] == "READY" and norm(r["final"]) != norm(r["ref"]):
        errs.append("final result differs from history-present-from-start")
    if sc.get("expect_slow") is not None and r["slow"] != sc["expect_slow"]:
        errs.append(f"slow={r['slow']}")
    print(f"{'PASS' if not errs else 'FAIL'}  {name}")
    for line in r["log"]:
        print(f"        {line}")
    for e in errs:
        print(f"        !! {e}")
    return not errs


NOW = ts("2026-09-30 12:00")
FIRST = ts("2026-09-21 00:00")                      # window starts Monday 21 Sep

SC = {
    "S1 mixed: A before server history, B recoverable (reviewer case)": dict(
        term=lambda: Terminal(ts("2026-09-07 00:00"), NOW), local_at_start=FIRST, arrive_at=3,
        first=FIRST, items={"A": ts("2026-09-01 00:00"), "B": ts("2026-09-10 00:00")},
        expect_first={"A": "lost", "B": "pending"}, expect_state="READY"),
    "S1b same, server metadata 0 until attempt 5, bars at attempt 8": dict(
        term=lambda: Terminal(ts("2026-09-07 00:00"), NOW), local_at_start=FIRST, meta_at=5, arrive_at=8,
        first=FIRST, items={"A": ts("2026-09-01 00:00"), "B": ts("2026-09-10 00:00")},
        expect_first={"A": "pending", "B": "pending"}, expect_state="READY"),
    "S2 bars arrive at attempt 61, after the fast phase": dict(
        term=lambda: Terminal(ts("2026-09-01 00:00"), NOW), local_at_start=FIRST, arrive_at=61,
        first=FIRST, items={"B": ts("2026-09-10 00:00")},
        expect_first={"B": "pending"}, expect_state="READY", expect_slow=True),
    "S3 server lacks every start (metadata late)": dict(
        term=lambda: Terminal(ts("2026-09-15 00:00"), NOW), local_at_start=FIRST, meta_at=2,
        first=FIRST, items={"A": ts("2026-09-01 00:00"), "B": ts("2026-09-10 00:00")},
        expect_first={"A": "pending", "B": "pending"}, expect_state="READY"),
    "S4 ATR: C inside the server's first 14 bars, D two days later": dict(
        term=lambda: Terminal(ts("2026-09-07 00:00"), NOW), local_at_start=FIRST, arrive_at=2, atr=True,
        first=FIRST, items={"C": ts("2026-09-07 00:25"), "D": ts("2026-09-09 00:00")},
        expect_first={"C": "pending", "D": "pending"}, expect_state="READY"),
    "S5 Max bars in chart caps the series after B's start": dict(
        term=lambda: Terminal(ts("2026-09-01 00:00"), NOW, maxbars=len(calendar(ts("2026-09-14 00:00"), NOW))),
        local_at_start=FIRST, arrive_at=2,
        first=FIRST, items={"B": ts("2026-09-10 00:00"), "E": ts("2026-09-16 00:00")},
        expect_first={"B": "pending", "E": "pending"}, expect_state="READY"),
    "S6 ATR: start right after a 4-day closure (no 15 bars in the lead-in)": dict(
        term=lambda: Terminal(ts("2026-08-31 00:00"), NOW, closures=[(ts("2026-09-10 00:00"), ts("2026-09-14 06:00"))]),
        local_at_start=FIRST, arrive_at=2, atr=True,
        first=FIRST, items={"G": ts("2026-09-14 06:00"), "H": ts("2026-09-16 00:00")},
        expect_first={"G": "pending", "H": "pending"}, expect_state="READY"),
    "S7 bars never arrive: WAITING throughout, slow after 60": dict(
        term=lambda: Terminal(ts("2026-09-01 00:00"), NOW), local_at_start=FIRST,
        first=FIRST, items={"B": ts("2026-09-10 00:00")},
        expect_first={"B": "pending"}, expect_state="WAITING", expect_slow=True),
    "S8 history present from the start: READY, no timer": dict(
        term=lambda: Terminal(ts("2026-09-01 00:00"), NOW), local_at_start=ts("2026-09-01 00:00"),
        first=FIRST, items={"B": ts("2026-09-10 00:00")},
        expect_first={"B": "replayed"}, expect_state="READY"),
}

if __name__ == "__main__":
    import sys
    V250 = "--v250" in sys.argv
    print("logic:", "v2.50 (control)" if V250 else "v2.51")
    ok = 0
    for name, sc in SC.items():
        r = run(sc)
        ok += check(name, sc, r)
        if sc["expect_state"] == "READY":
            fin = {k: v[0] for k, v in r["final"].items()}
            print(f"        final {fin}  == history-from-start: {norm(r['final']) == norm(r['ref'])}")
    print(f"\n{ok}/{len(SC)} scenarios as expected")
