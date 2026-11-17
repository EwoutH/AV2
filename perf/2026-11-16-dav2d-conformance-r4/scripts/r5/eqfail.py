# eqcheck over the round-4 stress fail/ and keep/ streams (1t): eqfail.py <a> <b> <out>
import json, subprocess, sys, glob
from concurrent.futures import ThreadPoolExecutor
a, b, out = sys.argv[1:4]
R = '/srv/compression/cache/av2conf/round4'
files = sorted(glob.glob(R + '/fail/*/stream.*') + glob.glob(R + '/keep/*/stream.*') + glob.glob(R + '/keep/*.ivf') + glob.glob(R + '/keep/*.obu'))
def md5(dav, f):
    try:
        r = subprocess.run([dav, '-q', '--filmgrain', '1', '--threads', '1', '-i', f, '--muxer', 'md5', '-o', '-'], capture_output=True, text=True, timeout=600)
    except subprocess.TimeoutExpired:
        return None, 'timeout'
    return (r.stdout.split() or [None])[0], r.returncode
def one(f):
    x, y = md5(a, f), md5(b, f)
    return dict(f=f, same=x == y, a=x, b=y)
n = d = 0
with open(out, 'w') as fo, ThreadPoolExecutor(2) as ex:
    for r in ex.map(one, files):
        n += 1; d += not r['same']; fo.write(json.dumps(r) + '\n'); fo.flush()
print(n, 'streams,', d, 'differ')
