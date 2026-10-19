"""Live vs build coverage by category, from raw MT5 Experts logs (evidence helper, read-only).

ReloadTest -LiveVsBuild judges live rows against the next rebuild; this script reports, per instance and
per day, HOW MANY live rows of each category were compared, so the acceptance table can name the
categories that have a sample and the ones that do not (reviewer, v2.54r6 review, 2026-10-16):

    MODEL  HMI-LIVE ...,MODEL,...                LIQ   HMI-LIVE ...,LIQ,...
    CTX    HMI-CTX ...,live=1,...                PROT  HMI-PROT / HMI-ANCHOR / HMI-CTX-INTERNAL ...,live=1,...

Intraday: consecutive COMPLETE builds of one instance in one log file (one local day, no sleep in
between), same params digest. The live rows logged between them, whose run/init must be the earlier
build's, are compared both ways with the later build's rows of the same window:
    MODEL / LIQ  event time >= earlier 'to' + 10 min (the earlier build covers up to 'to' + 5) and <= later 'to'
    CTX / PROT   bar > earlier 'to' and <= later 'to'
Keys drop live= / inst= / run= / init= and, for MODEL / LIQ, the cycle and block ids (as the reviewer's
independent parser does); str= and leg= are kept.

Across a sleep (A-60): a stretch from the last build of a day to the first build of the next log file
is not live evidence. For the rows logged before the sleep it is still checked, and printed apart:
    forward  every live row after the day's last build is in the next first build (exact / leg only / missing)
    reverse  next first build rows with event time after the day's last 'to' and at least 10 min before the
             day's last log line (+ server offset) - the part the terminal provably ran - are all live rows
It is reported as cross-sleep evidence for the reviewer to weigh, never as an intraday PASS.
Exit status 1 when a compared intraday row differs or a cross-sleep row is not matched (a leg-only match counts as
not matched here; ReloadTest treats it as PENDING REVIEW).

    python3 tools/live_coverage.py [--ver 2.54] [--offset 2] LOG [LOG ...]    (logs in date order)
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
    return {'HMI-CTX': 'CTX', 'HMI-PROT': 'PROT', 'HMI-ANCHOR': 'PROT', 'HMI-CTX-INTERNAL': 'PROT'}.get(c[0])


def event_time(c, f):
    return T(c[8]) if c[0] in ('HMI-BUILD', 'HMI-LIVE') else T(f['bar'])


def key(c, f, drop=()):
    if c[0] in ('HMI-BUILD', 'HMI-LIVE'):
        z = [x for x in c[1:] if not x.startswith(('inst=', 'run=', 'init='))]
        return ('MODEL/LIQ', z[1]) + tuple(z[:1] + z[5:])
    return (c[0], c[2]) + tuple(sorted((k, v) for k, v in f.items() if k not in ('live', 'inst', 'run', 'init') + drop))


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
        r = Row(p[2], c, f, msg)
        if src in open_b:
            open_b[src]['rows'].append(r)
        elif seq.get(src) and (c[0] == 'HMI-LIVE' or f.get('live') == '1'):
            seq[src][-1]['live'].append(r)
    problems += [f'{s}: BEGIN at {b["local"]} never closed' for s, b in open_b.items()]
    return seq, last_local, problems


def window(cat, a_to, b_to):
    lo = T(a_to) + (dt.timedelta(minutes=10) if cat in ('MODEL', 'LIQ') else dt.timedelta(seconds=1))
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
    for path in a.logs:
        seq, last_local, problems = read_log(path, a.ver)
        name = re.sub(r'\.log$', '', path.replace('\\', '/').rsplit('/', 1)[-1])
        days.append((name, seq, last_local, problems))
        for pr in problems:
            print(f'  {name}: {pr}')

    srcs = sorted({s for _, seq, _, _ in days for s in seq})
    total = collections.defaultdict(collections.Counter)
    diffs = 0
    print(f'== intraday live vs build, v{a.ver} instances (rows compared per category / differences)')
    print(f'  {"instance":14} {"day":10} pairs  {"MODEL":>5} {"LIQ":>4} {"CTX":>4} {"PROT":>4}  diff  outside')
    for src in srcs:
        for name, seq, _, _ in days:
            bb = [b for b in seq.get(src, []) if b['status'] == 'COMPLETE']
            if not bb:
                continue
            n = collections.Counter()
            d = 0
            pairs = 0
            outside = 0
            for x, y in zip(bb, bb[1:]):
                if x['head']['params'] != y['head']['params']:
                    continue
                if any((r.f.get('run'), r.f.get('init')) != (x['head']['run'], x['head']['init']) for r in x['live']):
                    print(f'  {src} {name}: live row run/init differs from build {x["head"]["build"]} - stretch skipped')
                    continue
                pairs += 1
                used = 0
                for cat in CATS:
                    lo, hi = window(cat, x['head']['to'], y['head']['to'])
                    lv = [r.key() for r in x['live'] if r.cat == cat and lo <= r.time <= hi]
                    bd = [r.key() for r in y['rows'] if r.cat == cat and lo <= r.time <= hi]
                    k, dd = compare(lv, bd)
                    n[cat] += k
                    d += dd
                    used += len(lv)
                outside += len(x['live']) - used
            if pairs:
                total[src].update(n)
                diffs += d
                print(f'  {src:14} {name:10} {pairs:5}  {n["MODEL"]:5} {n["LIQ"]:4} {n["CTX"]:4} {n["PROT"]:4}  {d:4}  {outside:7}')
    print('  total')
    for src in srcs:
        t = total[src]
        print(f'  {src:14} {"":10} {"":5}  {t["MODEL"]:5} {t["LIQ"]:4} {t["CTX"]:4} {t["PROT"]:4}')
    print(f'  differences on compared rows: {diffs}')
    print('  ("outside": live rows of a stretch whose event time is at its edges and is not judged)')

    print(f'\n== across a sleep (A-60) - rows logged after the last build of a day, checked against the next first build')
    xs = collections.defaultdict(collections.Counter)
    found = False
    xbad = 0
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
            for r in x['live']:
                v = 'exact' if exact[r.key()] else ('leg only' if noleg[r.key(('leg',))] else 'MISSING')
                ok += v == 'exact'
                print(f'    forward  {r.local}  {r.cat:5} {v:8}  {r.msg[:110]}')
            awake = dt.datetime.strptime(x['head']['to'][:10] + ' ' + last_local[:8], '%Y.%m.%d %H:%M:%S') + \
                dt.timedelta(hours=a.offset)
            lo, hi = T(x['head']['to']), awake - dt.timedelta(minutes=10)
            lv = collections.Counter(r.key() for r in x['live'])
            want = [r for r in y['rows'] if lo < r.time <= hi]
            miss = [r for r in want if not lv[r.key()]]
            print(f'    reverse  awake window {lo:%m-%d %H:%M} .. {hi:%H:%M} server (last line {last_local[:8]} local): '
                  f'{len(want)} build row(s) {dict(collections.Counter(r.cat for r in want))}, missing from live {len(miss)}')
            for r in miss:
                print(f'      missing  {r.msg[:110]}')
            xbad += (len(x['live']) - ok) + len(miss)
            if ok == len(x['live']) and not miss:
                xs[src].update(r.cat for r in x['live'])
    if not found:
        print('  none')
    for src in sorted(xs):
        print(f'  {src}: both directions agree for ' + ', '.join(f'{c} {xs[src][c]}' for c in CATS if xs[src][c]))

    print(f'\n== category coverage, v{a.ver}')
    for src in srcs:
        t = total[src]
        have = [c for c in CATS if t[c]]
        only_x = [c for c in CATS if not t[c] and xs[src][c]]
        none = [c for c in CATS if not t[c] and not xs[src][c]]
        print(f'  {src:14} intraday: {", ".join(have) or "-":24} across a sleep only: {", ".join(only_x) or "-":18} '
              f'no sample: {", ".join(none) or "-"}')
    if xbad:
        print(f'  across a sleep: {xbad} row(s) not matched - see above')
    return 0 if diffs == 0 and xbad == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
