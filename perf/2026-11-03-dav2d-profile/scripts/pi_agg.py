# Share of 1-thread time per DSP family on the pi (data/pi/*.tsv, already
# symbolised against the unstripped cross build), plus estimated speed-ups
# if the C families got NEON. Usage: python3 pi_agg.py ../data/pi
import collections, glob, math, os, re, sys

sys.argv = [sys.argv[0], None] + sys.argv[1:]
exec(open(os.path.join(os.path.dirname(__file__), 'classify.py')).read().split('rows = ')[0])
D = sys.argv[2]


def is_asm(s):
    return bool(re.search(r'neon|sve|dotprod|i8mm', s))


def gmean(v):
    return math.exp(sum(map(math.log, v)) / len(v))


R = {}
for f in sorted(glob.glob(f'{D}/dav2d.*.tsv')):
    c = collections.Counter(); tot = 0
    for l in open(f):
        k, s = l.rstrip('\n').split('\t'); k = int(k); tot += k
        if s.startswith('[k]'):
            continue
        s = s[4:]
        c[(fam(s), 'asm' if is_asm(s) else 'C')] += k
    R[f] = (tot, c)

keys = set(k for _, c in R.values() for k in c)
print(f'pi, {len(R)} streams, mean share of 1-thread CPU time:')
for k in sorted(keys, key=lambda k: -sum(c.get(k, 0) / t for t, c in R.values())):
    v = sum(c.get(k, 0) / t for t, c in R.values()) / len(R)
    if v > 0.004:
        print(f'  {k[0]:38} {k[1]:4} {100 * v:5.1f}%')

# per-family gain of the 8-bit AVX2 asm over C on x86 (agg.py); TMV assumed 2x
FAC = {'GDF': 14.8, 'Wiener (LR)': 12, 'CCSO': 10, 'Deblock': 3, 'TMV projection (load_tmvs)': 2}
for lab, fs in [('GDF', ['GDF']), ('GDF+Wiener', ['GDF', 'Wiener (LR)']),
                ('GDF+Wiener+CCSO+deblock+TMV', list(FAC))]:
    for half in (0, 1):
        sp = []
        for t, c in R.values():
            new = t
            for f in fs:
                x = FAC[f] / (2 if half and f != 'TMV projection (load_tmvs)' else 1)
                new -= c[(f, 'C')] * (1 - 1 / x)
            sp.append(t / new)
        note = 'NEON gains half of AVX2' if half else 'NEON gains as much as AVX2'
        print(f'{lab:30} {note}: {gmean(sp):.2f}x (range {min(sp):.2f}-{max(sp):.2f})')
