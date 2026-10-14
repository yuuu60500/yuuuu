"""Cross-version attribution v2.53 -> v2.54 (BRI-12), offline model of what ReloadTest -Versus does.

Every H4 difference must hang on a concrete row of the logs, never on "it happened after the rule
changed" (reviewer, 2026-10-13). The rules, in the order they are tried:

  facts       a close or a swing price that differs, a str the strength rule cannot give, a v2.54 log
              that contradicts itself (CHOCH without PROT BREAK / FALLBACK; BREAK level != the CHOCH
              swing; FALLBACK in a leg that had a level; INTERNAL whose close breaks the protected level
              or does not break its own swing; TRANS_SAMELEG on a swing formed after the CHOCH)
                                                                        -> UNEXPLAINED
  states equal going into the bar - the difference needs a BRI-12 link ON THIS BAR:
    P-4   v2.54 CHOCH with HMI-PROT BREAK: the leg failed at its protected level (v2.53's event of the
          bar, if any, judged the latest swing / the high first)
    P-4   v2.53 CHOCH whose swing v2.54 processed on this bar as INTERNAL (protected level not broken)
    P-5   v2.53 TRANS_OK / TRANS_FAIL vs v2.54 TRANS_SAMELEG on the same swing, formed before the CHOCH
    P-7   v2.54 CHOCH (FALLBACK) where v2.53 broke the high first on the same close
    swing a row whose swing the other version had processed on an earlier bar (named), and the
          event that then breaks the next swing on the same bar (re-referenced)
          anything else                                                 -> PENDING_ATTRIBUTION
  states differ going into the bar - explained only inside a divergence whose FIRST bar was
          explained above (the state difference is in both logs: the ctx= of each row)
  strength   same event, other str: both follow the rule and every difference since the earlier
          leg start is explained
  H4 POI     NEW in one version only: the H4 direction on its bar differs, in an explained
          divergence, and is the POI's; OUT shifted by such a POI; events of a one-version POI

    python3 tools/h4_protect_attr.py                    seeded synthetic series + guards (tampered logs must not pass)
    python3 tools/h4_protect_attr.py --replay <H1 csv>  v2.53 vs v2.54 on real data, every difference
    python3 tools/h4_protect_attr.py --emit <H1 csv> <out.log>   the same runs as MT5 log lines, for ReloadTest -Versus

Limits: inside a divergence the two state machines are in different states - the tool proves where the
divergence starts and checks each version's own rules (strength, messy, PROT / INTERNAL consistency), it
does not re-derive each row (the log has the closes of event bars only). M5 (sessions, blocks, models) is not
modelled: ReloadTest applies its A-57 / A-58 chain rules there, a direction difference counting only inside
an explained divergence.
"""
import copy
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import h4_dedup_sim as B                                      # noqa: E402
import h4_protect_sim as P                                    # noqa: E402
from h4_dedup_sim import UP, DOWN, RANGE, BULL_CTX, BEAR_CTX, TRANS, MARGIN_PTS, tstr   # noqa: E402

DIRS = {UP: "UP", DOWN: "DOWN", 0: "-"}


def nostr(r):
    """the event itself; str and messy are attributes of the leg, judged separately"""
    return (r["bar"], r["kind"], r["dir"], r["ctx"], r["swing"], round(r["swing_px"], 5), round(r["close"], 5))


def leg_check(rows):
    """strength rule (B.strength_check annotates str_rule / leg) plus the messy rule: CtxEnter clears it,
    TRANS_FAIL sets it, a BOS in the trend and TRANS_SAMELEG keep it. Returns the rows that break either."""
    bad = B.strength_check(rows)
    m = False
    for r in rows:
        k = r["kind"]
        if k in ("CHOCH", "TIMEOUT", "TRANS_OK"):
            m = False
        elif k == "TRANS_FAIL":
            m = True
        elif k == "BOS" and r.get("leg") == r["bar"]:
            m = False                                    # a BOS that starts a leg (from RANGE)
        r["messy_rule"] = m
        if bool(r["messy"]) != m and r not in bad:
            bad.append(r)
    return bad


def label(r):
    return f"{tstr(r['bar'])} {r['kind']} {DIRS[r['dir']]} -> {r['ctx']} swing {tstr(r['swing']) if r['swing'] else '-'}"


def consumed(e, with_internal):
    """(dir, swing time) -> (first bar processed, what processed it)"""
    out = {}
    for r in e.ctx_rows:
        if r["swing"]:
            out.setdefault((r["dir"], r["swing"]), (r["bar"], r["kind"]))
    for d in e.dedup_rows:
        for (dd, st, _) in d["extra"]:
            out.setdefault((dd, st), (d["bar"], d["kind"] + " de-dup"))
    if with_internal:
        for it in e.internal_rows:
            out.setdefault((it["dir"], it["swing"]), (it["bar"], "INTERNAL"))
            for (dd, st, _) in it["extra"]:
                out.setdefault((dd, st), (it["bar"], "INTERNAL"))
    return out


def state_before(rows, t):
    s = RANGE
    for r in rows:
        if r["bar"] < t:
            s = r["ctx"]
        else:
            break
    return s


def attribute254(old, new, margin=MARGIN_PTS):
    V = {"explained": [], "PENDING_ATTRIBUTION": [], "UNEXPLAINED": []}
    def say(v, what, why):
        V[v].append((what, why))
    ro = sorted(old.ctx_rows, key=lambda r: r["bar"]); rn = sorted(new.ctx_rows, key=lambda r: r["bar"])

    # ---- facts ----------------------------------------------------------------------
    close_o = {r["bar"]: r["close"] for r in ro}
    px_o = {(r["dir"], r["swing"]): r["swing_px"] for r in ro if r["swing"]}
    for r in rn:
        if r["bar"] in close_o and close_o[r["bar"]] != r["close"]:
            say("UNEXPLAINED", "CTX " + label(r), "H4 close differs - market data, no rule moves a close")
        if r["swing"] and (r["dir"], r["swing"]) in px_o and px_o[(r["dir"], r["swing"])] != r["swing_px"]:
            say("UNEXPLAINED", "CTX " + label(r), "swing price differs - market data")
    bad_ids = set()
    for r in leg_check(ro) + leg_check(rn):
        bad_ids.add(id(r)); say("UNEXPLAINED", "CTX " + label(r), f"str {r['str']} / messy {int(bool(r['messy']))} but the rules give {r['str_rule']} / {int(r['messy_rule'])}")
    prot_at = defaultdict(list)
    for p in new.prot_rows:
        prot_at[p["bar"]].append(p)
    for r in rn:
        if r["kind"] != "CHOCH":
            continue
        ends = [p for p in prot_at[r["bar"]] if p["ev"] in ("BREAK", "FALLBACK")]
        if not ends:
            say("UNEXPLAINED", "CTX v2.54 " + label(r), "a v2.54 CHOCH without HMI-PROT BREAK / FALLBACK on its bar")
        elif ends[0]["ev"] == "BREAK" and ends[0]["level"] != r["swing_px"]:
            say("UNEXPLAINED", "CTX v2.54 " + label(r), f"HMI-PROT BREAK level {ends[0]['level']} is not the CHOCH swing {r['swing_px']}")
    legrows = defaultdict(list)
    for p in new.prot_rows:
        legrows[p["leg"]].append(p)
    for leg, rows in legrows.items():
        for k, p in enumerate(rows):
            if p["ev"] == "FALLBACK" and any(q["level"] is not None for q in rows[:k]):
                say("UNEXPLAINED", f"PROT FALLBACK {tstr(p['bar'])}", "the leg had a protected level - P-6b applies to an INVALID leg only")
    for it in new.internal_rows:
        if it["prot"] is not None and P.brk(it["dir"], it["close"], it["prot"], margin):
            say("UNEXPLAINED", f"INTERNAL {tstr(it['bar'])}", f"close {it['close']} breaks the protected level {it['prot']}: that close is a CHOCH")
        if not P.brk(it["dir"], it["close"], it["swing_px"], margin):
            say("UNEXPLAINED", f"INTERNAL {tstr(it['bar'])}", f"close {it['close']} does not break swing {it['swing_px']}")
    for r in rn:
        if r["kind"] == "TRANS_SAMELEG":
            tch = max([c["bar"] for c in rn if c["kind"] == "CHOCH" and c["bar"] < r["bar"]], default=None)
            if tch is not None and r["swing"] >= tch:
                say("UNEXPLAINED", "CTX v2.54 " + label(r), f"TRANS_SAMELEG on a swing formed at/after the CHOCH close {tstr(tch)} - P-5 would accept it")

    # ---- CTX differences, bar by bar ----------------------------------------------------
    go, gn = defaultdict(list), defaultdict(list)
    for r in ro: go[nostr(r)].append(r)
    for r in rn: gn[nostr(r)].append(r)
    only_o = [r for k in go for r in go[k][len(gn.get(k, [])):]]
    only_n = [r for k in gn for r in gn[k][len(go.get(k, [])):]]
    at_o, at_n = defaultdict(list), defaultdict(list)
    for r in only_o: at_o[r["bar"]].append(r)
    for r in only_n: at_n[r["bar"]].append(r)
    proc_o, proc_n = consumed(old, False), consumed(new, True)
    int_at = defaultdict(list)
    for it in new.internal_rows:
        int_at[it["bar"]].append(it)
    explained = set()
    bar_ok = {}
    # divergence: start bar of the stretch of differing states that bar t sits in
    evbars = sorted({r["bar"] for r in ro} | {r["bar"] for r in rn})
    after_o, after_n = {}, {}
    so = sn = RANGE; io = iN = 0
    for b in evbars:
        while io < len(ro) and ro[io]["bar"] <= b: so = ro[io]["ctx"]; io += 1
        while iN < len(rn) and rn[iN]["bar"] <= b: sn = rn[iN]["ctx"]; iN += 1
        after_o[b], after_n[b] = so, sn
    div_start = {}
    cur, prev_eq = None, True
    for b in evbars:
        eq = after_o[b] == after_n[b]
        if not eq and prev_eq:
            cur = b
        div_start[b] = None if eq else cur
        prev_eq = eq

    def start_of(t):
        """divergence start for a bar t whose states going in differ"""
        prior = [b for b in evbars if b < t]
        return div_start.get(prior[-1]) if prior else None

    for t in sorted(set(at_o) | set(at_n)):
        xs, ys = list(at_o[t]), list(at_n[t])
        bo, bn = state_before(ro, t), state_before(rn, t)
        if bo != bn:
            s0 = start_of(t)
            ok = s0 is not None and bar_ok.get(s0, False)
            for r, who in [(x, "v2.53") for x in xs] + [(y, "v2.54") for y in ys]:
                if ok:
                    explained.add(id(r))
                    say("explained", f"CTX {who} only " + label(r), f"states differ going in (v2.53 {bo} / v2.54 {bn}) since {tstr(s0)}, an explained difference")
                else:
                    say("PENDING_ATTRIBUTION", f"CTX {who} only " + label(r), f"states differ going in (v2.53 {bo} / v2.54 {bn}); the divergence start {tstr(s0) if s0 else '?'} is not explained")
            bar_ok[t] = ok
            continue
        why = {}
        # P-4 protected break / P-6b fallback on a v2.54 CHOCH
        for y in ys:
            if y["kind"] != "CHOCH":
                continue
            ends = [p for p in prot_at[t] if p["ev"] in ("BREAK", "FALLBACK")]
            if ends and ends[0]["ev"] == "BREAK" and ends[0]["level"] == y["swing_px"]:
                why[id(y)] = f"P-4: the leg's protected level {y['swing_px']} broken by close {y['close']} (HMI-PROT BREAK)"
                for x in xs:
                    why.setdefault(id(x), f"P-4 / P-7: on this bar v2.54 judged the leg's failure at its protected level first; v2.53 {x['kind']} by the latest swing")
            elif ends and ends[0]["ev"] == "FALLBACK":
                for x in xs:
                    if x["kind"] == "BOS" and x["dir"] == -y["dir"]:
                        why[id(y)] = "P-7: failure first - v2.54 (INVALID leg, P-6b) broke the latest low before checking the high"
                        why[id(x)] = "P-7: v2.53 checked the high first on the same close"
        # P-4 internal swing
        for x in xs:
            if x["kind"] != "CHOCH" or id(x) in why:
                continue
            for it in int_at[t]:
                swings = [(it["dir"], it["swing"])] + [(d, st) for (d, st, _) in it["extra"]]
                if (x["dir"], x["swing"]) in swings:
                    why[id(x)] = (f"P-4: v2.54 processed swing {tstr(x['swing'])} as internal on this bar (HMI-CTX-INTERNAL), "
                                  f"protected level {it['prot']} not broken by close {it['close']}")
        # P-5 old structure
        for x in xs:
            if x["kind"] not in ("TRANS_OK", "TRANS_FAIL") or id(x) in why:
                continue
            for y in ys:
                if y["kind"] == "TRANS_SAMELEG" and y["dir"] == x["dir"] and y["swing"] == x["swing"]:
                    tch = max([c["bar"] for c in rn if c["kind"] == "CHOCH" and c["bar"] < t], default=None)
                    if tch is not None and x["swing"] < tch:
                        why[id(x)] = why[id(y)] = (f"P-5: swing {tstr(x['swing'])} formed before the CHOCH close {tstr(tch)} - "
                                                   f"old structure resolves no transition in v2.54")
        # both in TRANSITION, opened by different CHOCH bars: the 18-bar limit and the new-structure test
        # (P-5) count from each version's own CHOCH - explained when those CHOCH differences are
        if bo == TRANS:
            cho = max([c["bar"] for c in ro if c["kind"] == "CHOCH" and c["bar"] < t], default=None)
            chn = max([c["bar"] for c in rn if c["kind"] == "CHOCH" and c["bar"] < t], default=None)
            if cho is not None and chn is not None and cho != chn:
                src = at_o[cho] + at_n[cho] + at_o[chn] + at_n[chn]
                if src and all(id(r) in explained for r in src):
                    for r in xs + ys:
                        why.setdefault(id(r), f"the transitions opened at different CHOCH bars (v2.53 {tstr(cho)}, v2.54 {tstr(chn)}, both "
                                              f"explained): the timeout and the new-structure test count from each version's own CHOCH")
        # a swing the other version had processed earlier, and the re-referenced primary
        for r, mine, other, who in [(x, proc_o, proc_n, "v2.54") for x in xs] + [(y, proc_n, proc_o, "v2.53") for y in ys]:
            if id(r) in why or not r["swing"]:
                continue
            p = other.get((r["dir"], r["swing"]))
            if p and p[0] < t:
                why[id(r)] = f"swing {tstr(r['swing'])} was processed by {who} at {tstr(p[0])} ({p[1]})"
        for y in ys:
            if id(y) in why:
                continue
            mate = [x for x in xs if id(x) in why and x["kind"] == y["kind"] and x["dir"] == y["dir"] and x["swing"] != y["swing"]]
            if mate and proc_n.get((y["dir"], y["swing"]), (None,))[0] == t:
                why[id(y)] = f"re-referenced: v2.54 had processed {tstr(mate[0]['swing'])}, so this close breaks {tstr(y['swing'])} first"
        for x in xs:
            if id(x) in why:
                continue
            mate = [y for y in ys if id(y) in why and y["kind"] == x["kind"] and y["dir"] == x["dir"] and y["swing"] != x["swing"]]
            if mate and proc_o.get((x["dir"], x["swing"]), (None,))[0] == t:
                why[id(x)] = f"re-referenced: v2.53 had processed {tstr(mate[0]['swing'])}, so this close breaks {tstr(x['swing'])} first"
        ok = True
        for r, who in [(x, "v2.53") for x in xs] + [(y, "v2.54") for y in ys]:
            if id(r) in why:
                explained.add(id(r)); say("explained", f"CTX {who} only " + label(r), why[id(r)])
            else:
                ok = False; say("PENDING_ATTRIBUTION", f"CTX {who} only " + label(r), "states equal going in, and no BRI-12 row on this bar links it")
        bar_ok[t] = ok

    # ---- leg attributes: str and messy -------------------------------------------------
    # the same event with another str or messy: both follow the rules, so the legs differ - explained
    # when every event difference since the earlier of the two leg starts is explained
    diffs = only_o + only_n
    for k in go:
        for o, w in zip(go[k], gn.get(k, [])):
            if (o["str"] == w["str"] and bool(o["messy"]) == bool(w["messy"])) or id(o) in bad_ids or id(w) in bad_ids:
                continue
            what = "CTX " + label(o) + f" str/messy {o['str']}/{int(bool(o['messy']))} -> {w['str']}/{int(bool(w['messy']))}"
            lo = min(o["leg"], w["leg"])
            window = [r for r in diffs if lo <= r["bar"] <= o["bar"]]
            if window and all(id(r) in explained for r in window):
                say("explained", what, f"legs from {tstr(o['leg'])} / {tstr(w['leg'])}; every difference since is explained")
            else:
                say("PENDING_ATTRIBUTION", what, "leg attribute differs and not every difference since the leg start is explained")

    # ---- H4 POI: the direction gates creation --------------------------------------------
    dir_of = lambda c: UP if c == BULL_CTX else (DOWN if c == BEAR_CTX else 0)
    def dir_at(rows, t):
        s = RANGE
        for r in rows:
            if r["bar"] <= t: s = r["ctx"]
            else: break
        return dir_of(s)
    def explained_div_at(t):
        prior = [b for b in evbars if b <= t]
        if not prior:
            return False
        s0 = div_start.get(prior[-1])
        return s0 is not None and bar_ok.get(s0, False)
    po, pn = B.multiset_diff(old.poi_rows, new.poi_rows)
    new_o = {(x[1], x[2]) for x in old.poi_rows if x[0] == "NEW"}
    new_n = {(x[1], x[2]) for x in new.poi_rows if x[0] == "NEW"}
    t_dir = min([b for b in evbars if dir_of(after_o[b]) != dir_of(after_n[b])], default=None)
    ex_poi, ex_t = set(), []
    ex_out = {}                      # (origin, dir, in old?) -> time of an explained OUT in that version
    for x, has_old in sorted([(x, True) for x in po] + [(x, False) for x in pn], key=lambda z: (z[0][3], z[0][0] != "NEW")):
        kind, origin, d, t = x
        who = "v2.53" if has_old else "v2.54"
        what = f"POI {who} only {kind} origin {tstr(origin)} dir {d:+d} at {tstr(t)}"
        if t_dir is None or t < t_dir:
            say("UNEXPLAINED", what, "before the first H4 direction difference"); continue
        dh, dn = (dir_at(ro, t), dir_at(rn, t)) if has_old else (dir_at(rn, t), dir_at(ro, t))
        in_both = (origin, d) in new_o and (origin, d) in new_n
        if kind == "NEW":
            if dh != dn and dh == d and explained_div_at(t):
                ex_poi.add((origin, d)); ex_t.append(t); say("explained", what, f"H4 direction on its bar: {who} {dh:+d}, the other {dn:+d}, in an explained divergence")
            elif dh != dn and dh == d:
                say("PENDING_ATTRIBUTION", what, "H4 direction differs on its bar, but that divergence is not explained")
            else:
                say("PENDING_ATTRIBUTION", what, "same H4 direction on its bar, or not the POI's")
        elif not in_both:
            say("explained" if (origin, d) in ex_poi else "PENDING_ATTRIBUTION", what,
                "the POI exists in one version only" + (", its creation explained" if (origin, d) in ex_poi else ", creation not explained"))
        elif kind == "OUT" and any(s <= t for s in ex_t):
            ex_out.setdefault((origin, d, not has_old), t)
            say("explained", what, "the POI window is first-in first-out: shifted by an explained one-version POI")
        elif kind in ("INVALID", "EXPIRED") and ex_out.get((origin, d, has_old), t + 1) <= t:
            say("explained", what, f"the other version had dropped this POI from its window at {tstr(ex_out[(origin, d, has_old)])} (OUT, explained): nothing of it happens there afterwards")
        else:
            say("PENDING_ATTRIBUTION", what, f"{kind} of a POI in both versions (the M5 chain decides it - MT5 only)")
    return V


def summary(V):
    return {k: len(v) for k, v in V.items()}


# ---- guards: a tampered v2.54 log must not pass -------------------------------------------
def guards(bars):
    old = B.run(bars, True); base = P.run254(bars)
    ok = 0; n = 0
    def check(name, mutate, want):
        nonlocal ok, n
        n += 1
        new = copy.deepcopy(base); mutate(new)
        V = attribute254(old, new)
        got = "UNEXPLAINED" if V["UNEXPLAINED"] else ("PENDING_ATTRIBUTION" if V["PENDING_ATTRIBUTION"] else "explained")
        good = (got == want) if want != "not explained" else got != "explained"
        ok += good
        print(f"{'PASS' if good else 'FAIL'}  guard: {name:72s} -> {got} (want {want})")
    first = lambda e, k: next(r for r in e.ctx_rows if r["kind"] == k)
    def drop_internal(e):
        # the INTERNAL row that explains a v2.53-only CHOCH
        a = attribute254(old, base)
        for (what, why) in a["explained"]:
            if "HMI-CTX-INTERNAL" in why:
                t = next(it["bar"] for it in base.internal_rows if tstr(it["bar"]) in what)
                e.internal_rows[:] = [it for it in e.internal_rows if it["bar"] != t]; return
    def prot_broken(e):
        it = next(it for it in e.internal_rows if it["prot"] is not None)
        it["prot"] = it["close"] + (0.001 if it["dir"] == DOWN else -0.001)
    def break_level(e):
        p = next(p for p in e.prot_rows if p["ev"] == "BREAK"); p["level"] = round(p["level"] + 0.0005, 5)
    def drop_break(e):
        p = next(p for p in e.prot_rows if p["ev"] == "BREAK"); e.prot_rows.remove(p)
    def sameleg_late(e):
        r = next(r for r in e.ctx_rows if r["kind"] == "TRANS_SAMELEG")
        tch = max(c["bar"] for c in e.ctx_rows if c["kind"] == "CHOCH" and c["bar"] < r["bar"])
        r["swing"] = tch + 4 * 3600
    def close_moved(e):
        r = first(e, "CHOCH"); r["close"] = round(r["close"] + 0.01, 5)
    def str_wrong(e):
        r = first(e, "BOS"); r["str"] = 9
    t_dir = min(t for (t, a), (_, b) in zip(old.state_after, base.state_after)
                if (UP if a == BULL_CTX else DOWN if a == BEAR_CTX else 0) != (UP if b == BULL_CTX else DOWN if b == BEAR_CTX else 0))
    k0 = max(k for k, b in enumerate(bars) if b[0] + 4 * 3600 < t_dir)
    def poi_same_dir(e):
        e.poi_rows.append(("NEW", bars[k0 - 2][0], UP, bars[k0][0] + 4 * 3600))
    check("untouched v2.54 run", lambda e: None, "explained")
    check("INTERNAL row behind a v2.53-only CHOCH removed", drop_internal, "not explained")
    check("INTERNAL row whose close breaks its protected level", prot_broken, "UNEXPLAINED")
    check("PROT BREAK level is not the CHOCH swing", break_level, "UNEXPLAINED")
    check("v2.54 CHOCH without its PROT BREAK row", drop_break, "UNEXPLAINED")
    check("TRANS_SAMELEG on a swing formed after the CHOCH", sameleg_late, "UNEXPLAINED")
    check("H4 close of an event bar changed", close_moved, "UNEXPLAINED")
    check("first BOS logged with str 9", str_wrong, "UNEXPLAINED")
    check("POI made in v2.54 only, before any H4 direction difference", poi_same_dir, "UNEXPLAINED")
    return ok, n


# ---- the same runs written as MT5 log lines, so ReloadTest -Versus can be held to these verdicts ----
def synth_bars(n=700, seed=54, t0=None, base=1.10000):
    """deterministic H4 random walk with drifting trends (weekend gaps not modelled)"""
    import random
    rnd = random.Random(seed)
    t0 = t0 or int(B.dt.datetime(2026, 1, 5, 0, 0, tzinfo=B.dt.timezone.utc).timestamp())
    out, px, drift = [], base, 0.0
    for i in range(n):
        if i % 40 == 0:
            drift = rnd.choice((-1, 1)) * rnd.uniform(0.00005, 0.0004)
        o = px
        c = o + drift + rnd.gauss(0, 0.0012)
        hi = max(o, c) + abs(rnd.gauss(0, 0.0006)); lo = min(o, c) - abs(rnd.gauss(0, 0.0006))
        out.append((t0 + i * 4 * 3600, round(o, 5), round(hi, 5), round(lo, 5), round(c, 5)))
        px = c
    return out


def emit_lines(bars, e, ver, inst, init, sym="USDJPY", src="USDJPY,M5"):
    """the structure rows one build of `ver` writes for engine run e (HMI_H4ContextEngine.mqh formats)"""
    T = "2026.10.02 10:00:00.000"
    tail = f",inst={inst},run=7,init={init}"
    L = lambda payload: f"{T}  H4M5_Identification ({src})  {payload}{tail}"
    f5 = lambda x: f"{x:.5f}"
    D = {UP: "UP", DOWN: "DOWN", 0: "-"}
    rows = []                                      # (bar, order, line)
    for r in e.ctx_rows:
        sw, sp = (tstr(r["swing"]), f5(r["swing_px"])) if r["swing"] else ("", "")
        rows.append((r["bar"], 0, L(f"HMI-CTX,{sym},{r['kind']},dir={D[r['dir']]},live=0,ctx={r['ctx']},str={r['str']},messy={int(bool(r['messy']))},"
                                   f"bar={tstr(r['bar'])},swing={sw},swing_px={sp},close={f5(r['close'])},also={r['also']}")))
    for d in e.dedup_rows:
        lst = "|".join(f"{tstr(st)}@{f5(px)}" for (_, st, px) in d["extra"])
        rows.append((d["bar"], 1, L(f"HMI-CTX-DEDUP,{sym},{d['kind']},dir={D[d['dir']]},bar={tstr(d['bar'])},primary={tstr(d['primary'][0])}@{f5(d['primary'][1])},"
                                   f"also={len(d['extra'])},swings={lst}")))
    if hasattr(e, "prot_rows"):
        st_at = {t: s for (t, s) in e.state_after}
        for it in e.internal_rows:
            lst = "|".join(f"{tstr(st)}@{f5(px)}" for (_, st, px) in it["extra"])
            rows.append((it["bar"], 2, L(f"HMI-CTX-INTERNAL,{sym},dir={D[it['dir']]},live=0,ctx={st_at.get(it['bar'], RANGE)},bar={tstr(it['bar'])},"
                                        f"swing={tstr(it['swing'])},swing_px={f5(it['swing_px'])},close={f5(it['close'])},also={it['also']},swings={lst},"
                                        f"prot={f5(it['prot']) if it['prot'] is not None else 'NA'}")))
        for tag, rr in (("HMI-PROT", e.prot_rows), ("HMI-ANCHOR", e.anchor_rows)):
            for p in rr:
                lv = p["level"] is not None
                rows.append((p["bar"], 3, L(f"{tag},{sym},{p['ev']},dir={D[p['dir']]},live=0,leg={p['leg']},bar={tstr(p['bar'])},"
                                           f"level={f5(p['level']) if lv else 'NA'},swing={tstr(p['swing']) if lv else '-'},confirm={tstr(p['confirm']) if lv else '-'},"
                                           f"bos={tstr(p['bos']) if lv else '-'},age=-1,prev={f5(p['prev']) if p['prev'] is not None else 'NA'},cand=NA")))
    hl = {b[0]: (b[2], b[3]) for b in bars}
    ids, nid = {}, [100]
    for (kind, origin, d, t) in e.poi_rows:
        key = (origin, d)
        if kind == "NEW":
            nid[0] += 1; ids[key] = nid[0]
            hi, lo = hl[origin]
            rows.append((t, 4, L(f"HMI-POI,{sym},NEW,id={ids[key]},dir={d},lo={f5(lo)},hi={f5(hi)},origin={tstr(origin)},bar={tstr(t)}")))
        else:
            rows.append((t, 4, L(f"HMI-POI,{sym},{kind},id={ids.get(key, 0)},dir={d},bar={tstr(t)}")))
    return [l for (_, _, l) in sorted(rows, key=lambda z: (z[0], z[1]))]


def emit_case(bars, sym="USDJPY", src="USDJPY,M5"):
    """two side-by-side builds, v2.53 (inst 0A53) and v2.54 (inst 0B54), plus the model's verdict counts"""
    old, new = B.run(bars, True), P.run254(bars)
    V = summary(attribute254(old, new))
    frm, to = tstr(bars[0][0]), tstr(bars[-1][0] + 4 * 3600)
    T = "2026.10.02 10:00:00.000"
    def build(ver, inst, init, e):
        L = lambda payload: f"{T}  H4M5_Identification ({src})  {payload}"
        idt = f",run=7,init={init}"
        head = [L(f"HMI v{ver} starting on {sym} PERIOD_M5  instance={inst} run=7 init={init}"),
                L(f"HMI-BUILD-BEGIN,{sym},m5_bars=5000,h4_bars={len(bars)},from={frm},to={to},ver={ver},params=461F006E,inst={inst},build=1,warmup_end={frm}{idt}")]
        mk = [L(f"HMI-BUILD,{sym},MODEL,1,100,100,OB,CISD,{tstr(bars[-3][0])}:00,1.23456,{tstr(bars[-4][0])}:00,1.23400,inst={inst}{idt}")]
        end = [L(f"HMI-BUILD-END,{sym},marks=1,cycles=1,pois=0,blocks=0,build=1,liq=READY,liqev=0,unknown=0,liqwait=0,inst={inst}{idt}")]
        return head + emit_lines(bars, e, ver, inst, init, sym, src) + mk + end
    margin = [f"{T}  H4M5_Identification ({src})  HMI: effective break margin = 0.00003 price / 3 points"]
    return margin + build("2.53", "0A53", 1, old) + build("2.54", "0B54", 2, new), V


def replay(path_csv):
    bars = B.load_h1(path_csv)
    print(f"replay {path_csv}: {len(bars)} H4 bars {tstr(bars[0][0])} .. {tstr(bars[-1][0])}")
    old, new = B.run(bars, True), P.run254(bars)
    V = attribute254(old, new)
    s = summary(V)
    print(f"verdicts: explained {s['explained']}   PENDING_ATTRIBUTION {s['PENDING_ATTRIBUTION']}   UNEXPLAINED {s['UNEXPLAINED']}")
    by = defaultdict(int)
    for (what, why) in V["explained"]:
        key = why.split(":")[0] if why.startswith(("P-", "re-ref")) else ("swing processed earlier" if why.startswith("swing ") else
              ("inside an explained divergence" if why.startswith("states differ") else why.split(";")[0][:40]))
        by[(what.split()[0], key)] += 1
    for (kind, key), k in sorted(by.items()):
        print(f"  explained  {kind:5s} {key:40s} {k}")
    for v in ("UNEXPLAINED", "PENDING_ATTRIBUTION"):
        for (what, why) in V[v][:15]:
            print(f"  {v:20s} {what}  <- {why}")
    print()
    g, n = guards(bars)
    print(f"\n{g}/{n} attribution guards as expected")
    return s["UNEXPLAINED"] == 0 and g == n


if __name__ == "__main__":
    if "--emit" in sys.argv:                       # --emit <H1 csv> <out .log>: real-data run as a log, verdicts printed
        i = sys.argv.index("--emit")
        lines, V = emit_case(B.load_h1(sys.argv[i + 1]))
        open(sys.argv[i + 2], "w", encoding="utf-8").write("\n".join(lines) + "\n")
        print(f"model verdicts: explained {V['explained']}   PENDING_ATTRIBUTION {V['PENDING_ATTRIBUTION']}   UNEXPLAINED {V['UNEXPLAINED']}")
        sys.exit(0)
    if "--replay" in sys.argv:
        sys.exit(0 if replay(sys.argv[sys.argv.index("--replay") + 1]) else 1)
    # no data file needed: the seeded series tools/logtests v01-v08 are built from
    bars = synth_bars(700, 37)
    s = summary(attribute254(B.run(bars, True), P.run254(bars)))
    print(f"synthetic H4 series (seed 37, {len(bars)} bars): explained {s['explained']}   PENDING_ATTRIBUTION {s['PENDING_ATTRIBUTION']}   UNEXPLAINED {s['UNEXPLAINED']}")
    g, n = guards(bars)
    print(f"\n{g}/{n} attribution guards as expected")
    sys.exit(0 if (g == n and s["UNEXPLAINED"] == 0 and s["PENDING_ATTRIBUTION"] == 0) else 1)
