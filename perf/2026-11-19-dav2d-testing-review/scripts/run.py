import json, subprocess, os, itertools
from concurrent.futures import ThreadPoolExecutor
DAV = "/srv/compression/cache/av2conf/round5/build/main-cov/tools/dav2d"
sets = json.load(open("sets.json"))
CFG = {"t1": ["--threads", "1"], "t2f1": ["--threads", "2", "--framedelay", "1"], "t2f2": ["--threads", "2", "--framedelay", "2"],
       "t4f4": ["--threads", "4", "--framedelay", "4"], "t1neg": ["--threads", "1", "--negstride"]}
os.makedirs("b", exist_ok=True)
jobs = [(mr, k, c) for mr, s in sets.items() for k in s for c in CFG]
def run(j):
    mr, k, c = j; p, md5 = sets[mr][k][0], sets[mr][k][1]
    o = f"b/{k}.{c}.bin"
    r = subprocess.run([DAV, "-q", "--filmgrain=1", *CFG[c], "-i", "s/" + os.path.basename(p), "--muxer", "md5", "-o", "-"],
                       env={"COV_OUT": o}, capture_output=True, text=True, timeout=600)
    return (mr, k, c, r.stdout.strip()[:32] == md5, r.returncode)
with ThreadPoolExecutor(3) as ex:
    res = list(ex.map(run, jobs))
bad = [r for r in res if not r[3]]
print(len(res), "runs;", len(bad), "md5 mismatches:", bad)
