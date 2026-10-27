"""Live vs build coverage by category, from raw MT5 Experts logs (evidence helper, read-only).

ReloadTest -LiveVsBuild judges live rows against the next rebuild; this script reports, per instance and
per day, HOW MANY live rows of each category were compared, so the acceptance table can name the
categories that have a sample and the ones that do not (reviewer, v2.54r6 review, 2026-10-16):

    MODEL  HMI-LIVE ...,MODEL,...                LIQ   HMI-LIVE ...,LIQ,...
    CTX    HMI-CTX ...,live=1,...                PROT  HMI-PROT / HMI-ANCHOR / HMI-CTX-INTERNAL ...,live=1,...
    B8     (--ver 2.55 and later) HMI-REF / HMI-BRK ...,live=1,...  - judged on the bars MODEL rows are (their time is
           the ARMED / confirming bar's close); cycle= is left out of the key like a MODEL row's ids
    STR    (--ver 2.56 and later) HMI-STR ...,live=1,...  - the strength score of one H4 bar (bar= its close), judged
           like CTX; HMI-STR-HIST (one per build) and HMI-STR-WAIT (a waiting episode, live only) are not rows to compare
    QLT    (--ver 2.57 and later) HMI-QLT ...,live=1,...  - the quality score of one H4 bar, judged like STR;
           HMI-QLT-HIST (one per build) is not a row to compare

Intraday: consecutive COMPLETE builds of one instance in one log file (one local day, no sleep in
between), same params digest. The live rows logged between them, whose run/init must be the earlier
build's, are compared both ways with the later build's rows of the same window:
    MODEL / LIQ  event time >= earlier 'to' + 10 min (the earlier build covers up to 'to' + 5) and <= later 'to'
    CTX / PROT / STR / QLT   bar > earlier 'to' and <= later 'to'
Keys drop live= / inst= / run= / init= and, for MODEL / LIQ, only the cycle and block ids (init-relative) -
symbol, category and direction stay, as in the reviewer's independent parser; str= and leg= are kept.
Every live row must carry the run/init of the build it follows (checked when the log is read).

Across a sleep (A-60): a stretch from the last build of a day to the first build of the next log file
is not live evidence; nor is a stretch between two builds of one day whose run= differs (the terminal was
restarted in between) - its live rows are only checked forward against the build after the restart. For the rows logged before the sleep it is still checked, and printed apart:
    forward  every live row after the day's last build is in the next first build (exact / leg only / missing)
    reverse  next first build rows with event time after the day's last 'to' and at least 10 min before the
             day's last log line (+ server offset) - the part the terminal provably ran - are all live rows
It is reported as cross-sleep evidence for the reviewer to weigh, never as an intraday PASS.
Live rows at the edges of a stretch (an event stamped after the later build's 'to', which a build still holds up to
'to' + 5 min) are not counted; they are listed with the build that holds them.
Exit status 1, and a last line RESULT: NOT PASSED, when the input has a problem (a build that is incomplete or never
closed, an END without BEGIN, a live row whose run/init is not its build's, a row that cannot be parsed), a compared
intraday row differs, an edge row is in neither build, or a cross-sleep row is not matched (a leg-only match counts as
not matched: it is reported as PENDING REVIEW, as ReloadTest does, and the RESULT is not a pass). An intraday PROT row that
differs only in leg= is likewise PENDING REVIEW, counted apart from the differences (v2.56 run, 2026-10-26). Zero differences on the
compared rows alone is not a pass.

    python3 tools/live_coverage.py [--ver 2.56] [--offset 2] LOG [LOG ...]    (logs in date order)
"""
import argparse, collections, datetime as dt, re, sys

CATS = ('MODEL', 'LIQ', 'CTX', 'PROT')


def kv(msg):
    return dict(x.split('=', 1) for x in msg.split(',') if '=' in x)


def T(s):
    return dt.datetime.strptime(s.strip()[:16], '%Y.%m.%d %H:%M')


def category(c):
    if c[0] in ('HMI-BUILD', 'HMI-LIVE'):
        return c[2] if len(c) > 2 and c[2] in ('MODEL', 'LIQ') else None
    return {'HMI-CTX': 'CTX', 'HMI-PROT': 'PROT', 'HMI-ANCHOR': 'PROT', 'HMI-CTX-INTERNAL': 'PROT',
            'HMI-REF': 'B8', 'HMI-BRK': 'B8', 'HMI-STR': 'STR', 'HMI-QLT': 'QLT'}.get(c[0])


def event_time(c, f):
    if c[0] == 'HMI-REF':                     # v2.55: the ARMED bar's close, as a MODEL row's time
        return T(f['armed'])
    if c[0] == 'HMI-BRK':                     # bar= is an M5 open time; the confirming bar closes 5 min later
        return T(f['bar']) + dt.timedelta(minutes=5)
    return T(c[8]) if c[0] in ('HMI-BUILD', 'HMI-LIVE') else T(f['bar'])


def key(c, f, drop=()):
    if c[0] in ('HMI-BUILD', 'HMI-LIVE'):
        z = [x for x in c[1:] if not x.startswith(('inst=', 'run=', 'init='))]
        return ('MODEL/LIQ', z[1]) + tuple(z[:3] + z[5:])       # symbol, category, direction; not cycle / block id
    skip = ('live', 'inst', 'run', 'init') + (('cycle',) if c[0] in ('HMI-REF', 'HMI-BRK') else ())   # cycle= is init-relative
    sub = {'HMI-STR': 'STR', 'HMI-QLT': 'QLT'}.get(c[0], c[2])        # HMI-STR / HMI-QLT have no event kind: c[2] is live=
    return (c[0], sub) + tuple(sorted((k, v) for k, v in f.items() if k not in skip + drop))


class Row:
    __slots__ = ('local', 'cat', 'time', 'c', 'f', 'msg')

    def __init__(self, local, c, f, msg):
        self.local, self.c, self.f, self.msg = local, c, f, msg
        self.cat = category(c)
        self.time = event_time(c, f)

    def key(self, drop=()):
        return key(self.c, self.f, drop)


def read_log(path, ver):
    """-> (builds per instance in order, last local time of the file, problems)"""
    text = open(path, 'rb').read().decode('utf-16')
    seq = collections.defaultdict(list)
    open_b = {}
    problems = []
    last_local = None
    for ln in text.splitlines():
        p = ln.split('\t')
        if len(p) >= 3 and re.match(r'\d\d:\d\d:\d\d', p[2]):
            last_local = p[2]
        m = re.search(r'(HMI-[A-Z-]+),', ln)
        if not m:
            continue
        msg = ln[m.start():]
        c = msg.split(',')
        f = kv(msg)
        src = c[1] + '#' + f.get('inst', '')
        if c[0] == 'HMI-BUILD-BEGIN':
            if src in open_b:
                problems.append(f'{src}: BEGIN at {p[2]} while build {open_b[src]["head"].get("build")} is open')
            open_b[src] = dict(head=f, local=p[2], rows=[], live=[], status='OPEN')
            continue
        if c[0] == 'HMI-BUILD-END':
            b = open_b.pop(src, None)
            if b is None:
                problems.append(f'{src}: END without BEGIN at {p[2]}')
                continue
            why = []
            if f.get('build') != b['head'].get('build'):
                why.append('build no.')
            if (f.get('run'), f.get('init')) != (b['head'].get('run'), b['head'].get('init')):
                why.append('run/init')
            if any((r.f.get('run'), r.f.get('init')) != (b['head'].get('run'), b['head'].get('init')) for r in b['rows']):
                why.append('row run/init')
            for cat, field in (('MODEL', 'marks'), ('LIQ', 'liqev')):
                if str(sum(r.cat == cat for r in b['rows'])) != f.get(field):
                    why.append(field)
            b['status'] = 'COMPLETE' if not why else 'INCOMPLETE (' + ', '.join(why) + ')'
            if b['head'].get('ver') == ver:
                seq[src].append(b)
                if why:
                    problems.append(f'{src}: build {b["head"].get("build")} at {b["local"]} {b["status"]}')
            continue
        cat = category(c)
        if not cat:
            continue
        live = src not in open_b and (c[0] == 'HMI-LIVE' or f.get('live') == '1')
        if src not in open_b and not (live and seq.get(src)):
            continue
        try:
            r = Row(p[2], c, f, msg)
        except (IndexError, KeyError, ValueError):
            problems.append(f'{src}: row at {p[2]} cannot be parsed: {msg[:80]}')
            continue
        if src in open_b:
            open_b[src]['rows'].append(r)
        else:
            b = seq[src][-1]
            if (f.get('run'), f.get('init')) != (b['head'].get('run'), b['head'].get('init')):
                problems.append(f'{src}: live row at {p[2]} run/init {f.get("run")}/{f.get("init")} is not its build\'s '
                                f'{b["head"].get("run")}/{b["head"].get("init")} (build {b["head"].get("build")} at {b["local"]})')
            b['live'].append(r)
    problems += [f'{s}: BEGIN at {b["local"]} never closed' for s, b in open_b.items()]
    return seq, last_local, problems


def window(cat, a_to, b_to):
    lo = T(a_to) + (dt.timedelta(minutes=10) if cat in ('MODEL', 'LIQ', 'B8') else dt.timedelta(seconds=1))
    return lo, T(b_to)


def compare(live, rows):
    lv, bd = collections.Counter(live), collections.Counter(rows)
    return sum(lv.values()), sum(((lv - bd) + (bd - lv)).values())


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--ver', default='2.54')
    ap.add_argument('--offset', type=float, default=2.0, help='server time minus local time, hours')
    ap.add_argument('logs', nargs='+')
    a = ap.parse_args()

    days = []
    input_bad = 0
    for path in a.logs:
        seq, last_local, problems = read_log(path, a.ver)
        name = re.sub(r'\.log$', '', path.replace('\\', '/').rsplit('/', 1)[-1])
        days.append((name, seq, last_local, problems))
        input_bad += len(problems)
        for pr in problems:
            print(f'  {name}: {pr}')

    srcs = sorted({s for _, seq, _, _ in days for s in seq})
    try:
        cats = CATS + (('B8',) if float(a.ver) >= 2.55 else ()) + (('STR',) if float(a.ver) >= 2.56 else ()) + \
            (('QLT',) if float(a.ver) >= 2.57 else ())             # v2.55 BRI-08 / v2.56 BRI-13 / v2.57 BRI-14
    except ValueError:
        cats = CATS
    cols = lambda c: ' '.join(f'{c[k]:{5 if k == "MODEL" else 4}}' for k in cats)
    total = collections.defaultdict(collections.Counter)
    diffs = 0
    legpend = 0
    edges = []
    restarts = []
    print(f'== intraday live vs build, v{a.ver} instances (rows compared per category / differences)')
    print(f'  {"instance":14} {"day":10} pairs  ' + ' '.join(f'{k:>{5 if k == "MODEL" else 4}}' for k in cats) + '  diff  outside  leg only')
    for src in srcs:
        for name, seq, _, _ in days:
            bb = [b for b in seq.get(src, []) if b['status'] == 'COMPLETE']
            if not bb:
                continue
            n = collections.Counter()
            d = 0
            pairs = 0
            outside = 0
            lg = 0
            for x, y in zip(bb, bb[1:]):
                if x['head']['params'] != y['head']['params']:
                    continue
                if x['head'].get('run') != y['head'].get('run'):     # the terminal restarted in between: like a sleep (A-60)
                    restarts.append((src, name, x, y))
                    continue
                if any((r.f.get('run'), r.f.get('init')) != (x['head']['run'], x['head']['init']) for r in x['live']):
                    print(f'  {src} {name}: live row run/init differs from build {x["head"]["build"]} - stretch skipped')
                    continue
                pairs += 1
                used = set()
                for cat in cats:
                    lo, hi = window(cat, x['head']['to'], y['head']['to'])
                    inw = [r for r in x['live'] if r.cat == cat and lo <= r.time <= hi]
                    lv = [r.key() for r in inw]
                    bd = [r.key() for r in y['rows'] if r.cat == cat and lo <= r.time <= hi]
                    k, dd = compare(lv, bd)
                    if cat == 'PROT':
                        # the same row but for leg= (legs count from each build's own H4 start, and a rebuild after an
                        # H4 close starts one bar later, A-59): PENDING REVIEW as in ReloadTest, not a difference
                        _, dn = compare([r.key(('leg',)) for r in inw],
                                        [r.key(('leg',)) for r in y['rows'] if r.cat == cat and lo <= r.time <= hi])
                        lg += (dd - dn) // 2
                        dd = dn
                    n[cat] += k
                    d += dd
                    used.update(id(r) for r in inw)
                rest = [r for r in x['live'] if id(r) not in used]
                outside += len(rest)
                later = collections.Counter(r.key() for r in y['rows'])
                earlier = collections.Counter(r.key() for r in x['rows'])
                for r in rest:
                    edges.append((src, name, r, 'in the later build' if later[r.key()] else
                                  ('in the earlier build' if earlier[r.key()] else 'IN NEITHER BUILD'), y))
            if pairs:
                total[src].update(n)
                diffs += d
                legpend += lg
                print(f'  {src:14} {name:10} {pairs:5}  {cols(n)}  {d:4}  {outside:7}  {lg:8}')
    print('  total')
    for src in srcs:
        t = total[src]
        print(f'  {src:14} {"":10} {"":5}  {cols(t)}')
    print(f'  differences on compared rows: {diffs}' + (f'   (+ {legpend} PROT row(s) the same but for leg= - PENDING REVIEW)' if legpend else ''))
    print('  ("outside": live rows of a stretch whose event time is at its edges; not counted, listed below)')
    edge_bad = 0
    edge_ok = collections.defaultdict(collections.Counter)
    if edges:
        print('\n== edge rows (outside the judged window, not counted in the table)')
    for src, name, r, v, y in edges:
        edge_bad += v == 'IN NEITHER BUILD'
        if v != 'IN NEITHER BUILD':
            edge_ok[src][r.cat] += 1
        print(f'  {src} {name}  live {r.local}  {r.cat:5} {v:20} later build {y["local"]} local to={y["head"]["to"]}  {r.msg[:90]}')

    rbad = 0
    if restarts:
        print('\n== across a terminal restart (A-60) - two builds of one day with another run= in between: not intraday evidence;')
        print('   the live rows before the restart are checked forward against the build after it')
    for src, name, x, y in restarts:
        exact = collections.Counter(r.key() for r in y['rows'])
        print(f'  {src} {name}: build {x["head"].get("build")} {x["local"]} (run {x["head"].get("run")}) -> build {y["head"].get("build")} '
              f'{y["local"]} (run {y["head"].get("run")}): {len(x["live"])} live row(s)')
        for r in x['live']:
            v = 'exact' if exact[r.key()] else 'MISSING'
            rbad += v == 'MISSING'
            print(f'    forward  {r.local}  {r.cat:5} {v:8}  {r.msg[:110]}')
    print(f'\n== across a sleep (A-60) - rows logged after the last build of a day, checked against the next first build')
    xs = collections.defaultdict(collections.Counter)
    found = False
    xbad = 0
    xleg = 0
    for i, (name, seq, last_local, _) in enumerate(days):
        name2, seq2 = (days[i + 1][0], days[i + 1][1]) if i + 1 < len(days) else ('', {})
        for src in srcs:
            bb = [b for b in seq.get(src, []) if b['status'] == 'COMPLETE']
            nb = [b for b in seq2.get(src, []) if b['status'] == 'COMPLETE']
            if not bb or not bb[-1]['live']:
                continue
            found = True
            x = bb[-1]
            print(f'  {src} {name}: {len(x["live"])} live row(s) after the last build ({x["local"]} local, to={x["head"]["to"]})')
            if not nb:
                print(f'    no complete build of it in {name2} - not checked' if name2 else '    no later log - not checked')
                continue
            y = nb[0]
            same = x['head']['params'] == y['head']['params'] and \
                (x['head']['run'], x['head']['init']) == (y['head']['run'], y['head']['init'])
            print(f'    next first build {name2} {y["local"]} local, to={y["head"]["to"]}, params {y["head"]["params"]}'
                  f'{"" if same else "  - params or run/init differ, not checked"}')
            if not same:
                continue
            exact = collections.Counter(r.key() for r in y['rows'])
            noleg = collections.Counter(r.key(('leg',)) for r in y['rows'])
            ok = 0
            fleg = 0
            for r in x['live']:
                v = 'exact' if exact[r.key()] else ('leg only' if noleg[r.key(('leg',))] else 'MISSING')
                ok += v == 'exact'
                fleg += v == 'leg only'
                print(f'    forward  {r.local}  {r.cat:5} {v:8}  {r.msg[:110]}')
            awake = dt.datetime.strptime(x['head']['to'][:10] + ' ' + last_local[:8], '%Y.%m.%d %H:%M:%S') + \
                dt.timedelta(hours=a.offset)
            lo, hi = T(x['head']['to']), awake - dt.timedelta(minutes=10)
            lv = collections.Counter(r.key() for r in x['live'])
            lvn = collections.Counter(r.key(('leg',)) for r in x['live'])
            want = [r for r in y['rows'] if lo < r.time <= hi]
            miss = [r for r in want if not lv[r.key()]]
            rleg = [r for r in miss if lvn[r.key(('leg',))]]          # the same row but for leg= (counted forward already)
            miss = [r for r in miss if not lvn[r.key(('leg',))]]
            print(f'    reverse  awake window {lo:%m-%d %H:%M} .. {hi:%H:%M} server (last line {last_local[:8]} local): '
                  f'{len(want)} build row(s) {dict(collections.Counter(r.cat for r in want))}, missing from live {len(miss)}'
                  + (f', leg only {len(rleg)}' if rleg else ''))
            for r in miss:
                print(f'      missing  {r.msg[:110]}')
            xbad += (len(x['live']) - ok - fleg) + len(miss)
            xleg += fleg
            if ok == len(x['live']) and not miss:
                xs[src].update(r.cat for r in x['live'])
    if not found:
        print('  none')
    for src in sorted(xs):
        print(f'  {src}: both directions agree for ' + ', '.join(f'{c} {xs[src][c]}' for c in cats if xs[src][c]))

    print(f'\n== category coverage, v{a.ver}')
    for src in srcs:
        t = total[src]
        have = [c for c in cats if t[c]]
        only_x = [c for c in cats if not t[c] and xs[src][c]]
        only_e = [c for c in cats if not t[c] and edge_ok[src][c]]
        none = [c for c in cats if not t[c] and not xs[src][c] and not edge_ok[src][c]]
        print(f'  {src:14} intraday: {", ".join(have) or "-":24} across a sleep only: {", ".join(only_x) or "-":18} '
              f'edge only: {", ".join(only_e) or "-":12} no sample: {", ".join(none) or "-"}')
    if xbad:
        print(f'  across a sleep: {xbad} row(s) not matched - see above')
    xbad += rbad
    bad = [f'{n} {w}' for n, w in ((input_bad, 'input problem(s)'), (diffs, 'difference(s) on compared rows'),
                                    (legpend, 'intraday PROT row(s) the same but for leg= - PENDING REVIEW (A-59: the rebuild\'s H4 '
                                              'window starts later)'),
                                    (edge_bad, 'edge row(s) in neither build'), (xbad, 'cross-sleep / restart row(s) not matched'),
                                    (xleg, 'cross-sleep row(s) the same but for leg= - PENDING REVIEW (leg counts from each '
                                           "build's own H4 start, which moved)")) if n]
    print('\nRESULT: ' + ('NOT PASSED - ' + '; '.join(bad) if bad else
                          'inputs complete, 0 differences (categories without a sample are listed above, not passed)'))
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
