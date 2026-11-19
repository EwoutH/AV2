import json, subprocess, os, sys
from concurrent.futures import ThreadPoolExecutor
B = "/srv/compression/cache/av2conf/testreview"
sets = json.load(open("sets.json"))
CFG = {"t1": ["--threads", "1"], "t2f2": ["--threads", "2", "--framedelay", "2"], "t4f4": ["--threads", "4", "--framedelay", "4"],
       "t3f3neg": ["--threads", "3", "--framedelay", "3", "--negstride"]}
BUILDS = {"msan": [], "ubsan": [], "asan-c": ["--cpumask", "0"]}
env = dict(os.environ, MSAN_OPTIONS="exitcode=1", UBSAN_OPTIONS="print_stacktrace=1:halt_on_error=1", ASAN_OPTIONS="detect_leaks=0")
skip = {"avm.testsrc.176x144.l80.clk-kf70", "avm.testsrc.176x144.l2.ger"}
jobs = [(b, mr, k, c) for b in BUILDS for mr, s in sets.items() for k in s if k not in skip for c in CFG]
def run(j):
    b, mr, k, c = j; p, md5 = sets[mr][k][0], sets[mr][k][1]
    r = subprocess.run([f"{B}/b-{b.split('-')[0]}/tools/dav2d", "-q", "--filmgrain=1", *BUILDS[b], *CFG[c], "-i", "s/" + os.path.basename(p),
                        "--muxer", "md5", "-o", "-"], env=env, capture_output=True, text=True, timeout=1200)
    ok = r.returncode == 0 and r.stdout.strip()[:32] == md5
    return dict(b=b, mr=mr, k=k, c=c, ok=ok, rc=r.returncode, md5=r.stdout.strip()[:32], err=r.stderr[-3000:] if not ok else "")
with ThreadPoolExecutor(int(sys.argv[1]) if len(sys.argv) > 1 else 1) as ex:
    res = list(ex.map(run, jobs))
json.dump(res, open("san.json", "w"), indent=0)
bad = [r for r in res if not r["ok"]]
print(len(res), "runs,", len(bad), "failures")
for r in bad: print(r["b"], r["mr"], r["k"], r["c"], r["rc"], r["err"][-400:].replace("\n", " | "))
