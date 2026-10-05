"""Offline model of the liquidity-history wait (A-47 / A-49 / A-50 / A-53).

Mirrors, function for function, what HMI_LiquidityLevels.mqh and OnTimer do
with the replay history before the M5 window:

  LiqHistoryFloor  earliest bar a program can ever get (server first bar, or
                   the "Max bars in chart" cap = SERIES_FIRSTDATE when capped)
  LiqRequestFrom   where a request may start: the 3-day lead-in, never
                   before the floor (A-53)
  LiqLossKind      unreached item: lost to the floor / lost short (all bars
                   from the request start are in) / pending
  LiqReplay        per item: replayed / lost / pending; WAITING iff pending
  LiqHistoryProbe  timer probe: "" or ARRIVED / BEFORE_FLOOR / SETTLED
  OnTimer          fast probes, then slow ones; never READY without a rebuild

against a modelled terminal. By default the terminal follows the documented
CopyRates behaviour that matters here (A-53):

  - a range reaching past TERMINAL_MAXBARS returns -1 (not a clipped result)
  - an indicator asking for history the terminal must still download gets -1
    at once (the download starts in the background)

Each scenario checks
  1. the first build's classification (lost vs pending)
  2. never READY while an item is still pending
  3. at most one timer-driven rebuild, and that rebuild is READY (no loop)
  4. the final per-item result - for a replayed item the exact bars and ATR
     presence its replay reads - equals a v2.52 build made with all
     accessible history present from the start

    python3 tools/liq_wait_sim.py                     v2.52 logic, strict terminal
    python3 tools/liq_wait_sim.py --logic v2.51       control
    python3 tools/liq_wait_sim.py --logic v2.50       control
    python3 tools/liq_wait_sim.py --lenient           terminal that clips out-of-range
                                                      requests (what v2.51's model did)

It models the rules, not MQL5: a pass here does not replace compiling and
running the indicator. SERIES_SERVER_FIRSTDATE timing, SERIES_FIRSTDATE and
the Bars() / TERMINAL_MAXBARS cap are modelled as documented, not observed.
"""
import datetime as dt
import sys

M5 = 300
DAY = 86400
FAST_TRIES = 60
LENIENT = "--lenient" in sys.argv
LOGIC = sys.argv[sys.argv.index("--logic") + 1] if "--logic" in sys.argv else "v2.52"


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
        """List of bar times, or [] for -1."""
        s = self.series()
        if not LENIENT:
            if not s:
                return []
            if self.maxbars and len(s) >= self.maxbars and t_from < s[0]:
                return []                                   # outside TERMINAL_MAXBARS
            if t_from < self.local_from and self.srv_first < self.local_from:
                return []                                   # must download first
        return [t for t in s if t_from <= t <= t_to]

    def SERVER_FIRSTDATE(self):
        return self.srv_first if self.meta else 0

    def TERMINAL_FIRSTDATE(self):
        return self.local_from or 0

    def SERIES_FIRSTDATE(self):                             # per period: the built M5 series
        s = self.series()
        return s[0] if s else 0

    def Bars(self):
        return len(self.series())


def LiqReplayAvail(bars, atr_mode):
    if not bars:
        return 0
    if atr_mode:
        return bars[14] if len(bars) > 14 else 0
    return bars[0]


def atr_series(bars):
    """Only the bar TIMES matter for this model; 'ATR present' = index >= 14."""
    return [i >= 14 for i in range(len(bars))]


def replayed(lr, start, atr_mode):
    k = next(i for i, t in enumerate(lr) if t >= start)
    return ("replayed", tuple(lr[k:]), tuple(atr_series(lr)[k:]) if atr_mode else ())


# ==== v2.52 (current) ========================================================
def floor52(term):
    srv = term.SERVER_FIRSTDATE()
    cap = term.SERIES_FIRSTDATE() if term.maxbars > 0 and term.Bars() >= term.maxbars else 0
    return srv if srv > cap else cap


def request_from(start, hfloor):
    r = start - 3 * DAY
    return hfloor if hfloor > 0 and r < hfloor else r


def loss_kind(start, got, req, hfloor, m5_first):
    if hfloor > 0 and start < hfloor:
        return 1                                            # before the floor
    if got > 0 and m5_first > 0 and m5_first <= req:
        return 2                                            # every bar from req is in: short for good
    return 0


def replay52(term, items, first, atr_mode):
    res, pend = {}, []
    pre = {k: s for k, s in items.items() if s < first}
    if not pre:
        return res, pend
    hfloor = floor52(term)
    need = min([first] + [s for s in pre.values() if not (hfloor > 0 and s < hfloor)])
    req, lr = 0, []
    if need < first:
        req = request_from(need, hfloor)
        lr = term.CopyRates(req, first - 1)
    avail = LiqReplayAvail(lr, atr_mode) or first
    m5f = term.SERIES_FIRSTDATE()
    for name, start in sorted(pre.items()):
        if start < avail:
            k = loss_kind(start, len(lr), req, hfloor, m5f)
            if k:
                res[name] = ("lost", "floor" if k == 1 else "short")
            else:
                res[name] = ("pending",)
                pend.append(start)
        else:
            res[name] = replayed(lr, start, atr_mode)
    return res, pend


def probe52(term, pend, first, atr_mode):
    hfloor = floor52(term)
    rec = [s for s in pend if not (hfloor > 0 and s < hfloor)]
    if not rec:
        return "BEFORE_FLOOR"
    target = min(rec)
    req = request_from(target, hfloor)
    tmp = term.CopyRates(req, first - 1)
    if not tmp:
        return ""
    avail = LiqReplayAvail(tmp, atr_mode)
    if avail > 0 and avail <= target:
        return "ARRIVED"
    if loss_kind(target, len(tmp), req, hfloor, term.SERIES_FIRSTDATE()) == 2:
        return "SETTLED"
    return ""


# ==== v2.51 (control) =========================================================
def floor51(term):
    srv = term.SERVER_FIRSTDATE()
    cap = term.SERIES_FIRSTDATE() if term.maxbars > 0 and term.Bars() >= term.maxbars else 0
    return srv if srv > cap else cap


def lost51(start, bars, hfloor, term_first):
    if hfloor > 0 and start < hfloor:
        return True
    if bars and hfloor > 0 and bars[0] <= hfloor:
        return True
    if bars and term_first > 0 and term_first <= start - 3 * DAY:
        return True
    return False


def replay51(term, items, first, atr_mode):
    pre = {k: s for k, s in items.items() if s < first}
    res, pend = {}, []
    if not pre:
        return res, pend
    need = min(pre.values())
    lr = term.CopyRates(need - 3 * DAY, first - 1)          # floor read AFTER the request
    avail = LiqReplayAvail(lr, atr_mode) or first
    hfloor, tfst = floor51(term), term.TERMINAL_FIRSTDATE()
    for name, start in sorted(pre.items()):
        if start < avail:
            if lost51(start, lr, hfloor, tfst):
                res[name] = ("lost",)
            else:
                res[name] = ("pending",)
                pend.append(start)
        else:
            res[name] = replayed(lr, start, atr_mode)
    return res, pend


def probe51(term, pend, first, atr_mode):
    hfloor, tfst = floor51(term), term.TERMINAL_FIRSTDATE()
    rec = [s for s in pend if not lost51(s, [], hfloor, tfst)]
    if not rec:
        return "BEFORE_FLOOR"
    target = min(rec)
    tmp = term.CopyRates(target - 3 * DAY, first - 1)      # not clamped to the floor
    if not tmp:
        return ""
    avail = LiqReplayAvail(tmp, atr_mode)
    if avail > 0 and avail <= target:
        return "ARRIVED"
    if lost51(target, tmp, hfloor, tfst):
        return "SETTLED"
    return ""


# ==== v2.50 (control) =========================================================
def replay50(term, items, first, atr_mode):
    """One verdict for all items, from the OLDEST start only."""
    pre = {k: s for k, s in items.items() if s < first}
    res = {}
    if not pre:
        return res, []
    need = min(pre.values())
    lr = term.CopyRates(need - 3 * DAY, first - 1)
    avail = LiqReplayAvail(lr, atr_mode) or first
    srv = term.SERVER_FIRSTDATE()
    waiting = avail > need and (srv <= 0 or srv <= need)
    for name, start in sorted(pre.items()):
        if start < avail:
            res[name] = ("pending",) if waiting else ("lost",)
        else:
            res[name] = replayed(lr, start, atr_mode)
    return res, ([need] if waiting else [])


def probe50(term, pend, first, atr_mode):
    need = pend[0]
    tmp = term.CopyRates(need - 3 * DAY, first - 1)
    avail = LiqReplayAvail(tmp, atr_mode)
    if avail > 0 and avail <= need:
        return "ARRIVED"
    srv = term.SERVER_FIRSTDATE()
    if srv > 0 and srv > need:
        return "GIVE_UP"                                    # v2.50: READY without a rebuild
    return ""


LOGICS = {"v2.52": (replay52, probe52), "v2.51": (replay51, probe51), "v2.50": (replay50, probe50)}


# ---- the indicator around it (OnCalculate first build + OnTimer) ------------
def run(sc, logic, max_attempts=200):
    replay, probe = LOGICS[logic]
    term = sc["term"]()
    term.local_from = sc["local_at_start"]
    term.meta = sc.get("meta_at", 0) == 0
    first, items, atr = sc["first"], sc["items"], sc.get("atr", False)

    res, pend = replay(term, items, first, atr)
    first_build = {k: v[0] for k, v in res.items()}
    log = [f"build 1: {'WAITING' if pend else 'READY'} {first_build}"]
    rebuilds, attempt, slow, loop = 0, 0, False, False
    while pend and attempt < max_attempts:
        attempt += 1
        if attempt == sc.get("meta_at", -1):
            term.meta = True
        if attempt == sc.get("arrive_at", -1):
            term.local_from = term.srv_first
        why = probe(term, pend, first, atr)
        if logic == "v2.50" and (why == "GIVE_UP" or (not why and attempt >= FAST_TRIES)):
            log.append(f"attempt {attempt}: {why or 'MAX_TRIES'} -> READY without rebuild")
            pend = []
            break
        if why:
            res, pend = replay(term, items, first, atr)
            rebuilds += 1
            log.append(f"attempt {attempt}: {why} -> rebuild {rebuilds} -> {'WAITING' if pend else 'READY'}")
            if pend:
                loop = True
                if rebuilds >= 3:
                    break
            continue
        if attempt == FAST_TRIES:
            slow = True
            log.append(f"attempt {attempt}: SLOW (still WAITING)")
    if pend and not loop and attempt >= max_attempts:
        log.append(f"attempt {attempt}: still WAITING")
    state = "WAITING" if pend else "READY"

    ref_term = sc["term"]()
    ref_term.local_from, ref_term.meta = ref_term.srv_first, True
    ref, _ = replay52(ref_term, items, first, atr)
    return dict(first_build=first_build, final=res, ref=ref, state=state, rebuilds=rebuilds,
                slow=slow, loop=loop, log=log)


def norm(res):
    """What the indicator actually holds: pending and lost are both UNKNOWN."""
    return {k: (("unknown",) if v[0] in ("pending", "lost") else v) for k, v in res.items()}


def check(name, sc, r):
    errs = []
    if r["first_build"] != sc["expect_first"]:
        errs.append(f"first build {r['first_build']} != {sc['expect_first']}")
    if r["state"] != sc["expect_state"]:
        errs.append(f"final state {r['state']} != {sc['expect_state']}")
    if r["loop"]:
        errs.append("a rebuild came back WAITING (rebuild loop)")
    if r["rebuilds"] > sc.get("max_rebuilds", 1):
        errs.append(f"{r['rebuilds']} timer rebuilds")
    if r["state"] == "READY" and norm(r["final"]) != norm(r["ref"]):
        errs.append("final result differs from all-history-present")
    if sc.get("expect_slow") is not None and r["slow"] != sc["expect_slow"]:
        errs.append(f"slow={r['slow']}")
    print(f"{'PASS' if not errs else 'FAIL'}  {name}")
    for line in r["log"]:
        print(f"        {line}")
    for e in errs:
        print(f"        !! {e}")
    if r["state"] == "READY":
        fin = {k: (v[0] + ('/' + v[1] if len(v) == 2 else '')) for k, v in r["final"].items()}
        print(f"        final {fin}")
    return not errs


NOW = ts("2026-09-30 12:00")
FIRST = ts("2026-09-21 00:00")                      # window starts Monday 21 Sep
CAP_0914 = len(calendar(ts("2026-09-14 00:00"), NOW))   # Max bars that put the cap at Mon 14 Sep 00:00


def capped(srv):
    return lambda: Terminal(ts(srv), NOW, maxbars=CAP_0914)


SC = {
    "S1 mixed: A before server history, B recoverable": dict(
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
    "S5 Max bars cap lands after B, download late": dict(
        term=capped("2026-09-01 00:00"), local_at_start=FIRST, arrive_at=2,
        first=FIRST, items={"B": ts("2026-09-10 00:00"), "E": ts("2026-09-16 00:00")},
        expect_first={"B": "pending", "E": "pending"}, expect_state="READY"),
    "S6 ATR: start right after a 4-day closure": dict(
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
    # ---- A-53: the reviewer's two capacity cases (all history already loaded)
    "R1 cap 14 Sep, A 10 Sep, B 16 Sep: B's lead-in reaches past the cap": dict(
        term=capped("2026-09-01 00:00"), local_at_start=ts("2026-09-01 00:00"),
        first=FIRST, items={"A": ts("2026-09-10 00:00"), "B": ts("2026-09-16 00:00")},
        expect_first={"A": "lost", "B": "replayed"}, expect_state="READY", max_rebuilds=0),
    "R2 cap 14 Sep, A 10 Sep, B 18 Sep: probe fits, A widens the rebuild": dict(
        term=capped("2026-09-01 00:00"), local_at_start=ts("2026-09-01 00:00"),
        first=FIRST, items={"A": ts("2026-09-10 00:00"), "B": ts("2026-09-18 00:00")},
        expect_first={"A": "lost", "B": "replayed"}, expect_state="READY", max_rebuilds=0),
    "R3 ATR, cap 14 Sep, C 5 bars after the cap, D 16 Sep, download late": dict(
        term=capped("2026-09-01 00:00"), local_at_start=FIRST, arrive_at=2, atr=True,
        first=FIRST, items={"C": ts("2026-09-14 00:25"), "D": ts("2026-09-16 00:00")},
        expect_first={"C": "pending", "D": "pending"}, expect_state="READY"),
}

if __name__ == "__main__":
    print(f"logic: {LOGIC}   terminal: {'lenient (clips out-of-range requests)' if LENIENT else 'strict (documented -1 paths)'}")
    ok = 0
    for name, sc in SC.items():
        ok += check(name, sc, run(sc, LOGIC))
    print(f"\n{ok}/{len(SC)} scenarios as expected")
