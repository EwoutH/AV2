import json, glob, re, collections
import numpy as np
gm = {int(k): v for k, v in json.load(open("gmap.json")).items()}
N = 19423
def ld(f):
    a = np.frombuffer(open(f, "rb").read(), np.uint8).astype(bool); return a[:N] if len(a) >= N else np.pad(a, (0, N - len(a)))
sets = json.load(open("sets.json"))
def U(names, cfgs):
    v = np.zeros(N, bool)
    for n in names:
        for c in cfgs: v |= ld(f"b/{n}.{c}.bin")
    return v
up = list(sets["upstream"]); pend = [k for m in ("!6", "!9", "!10", "!11", "!8") for k in sets[m]]
ci_cfgs = ["t1", "t2f1", "t2f2", "t1neg"]  # what CI runs on test data today (t1 in test-debian, t2f* in tsan/avx512, neg)
st = collections.OrderedDict()
st["upstream t1 (CI coverage job)"] = U(up, ["t1"])
st["upstream, all CI flag sets"] = U(up, ci_cfgs)
st["upstream, + t4f4"] = U(up, ci_cfgs + ["t4f4"])
for m in ("!6", "!9", "!10", "!11", "!8"):
    prev = list(st.values())[-1]
    st[f"+ {m} ({len(sets[m])})"] = prev | U(list(sets[m]), ci_cfgs + ["t4f4"])
arch = np.zeros(N, bool)
for f in glob.glob("/srv/compression/cache/av2conf/round5/cov/bins/v*.bin"): arch |= ld(f)
for f in glob.glob("/srv/compression/cache/av2conf/round5/cov/re/*.bin"): arch |= ld(f)
st["+ r4 archive (3779 streams, t1)"] = list(st.values())[-1] | arch
mapped = np.zeros(N, bool); mapped[[k for k in gm if k < N]] = True
for k, v in st.items(): print(f"{k:40s} {int((v & mapped).sum()):6d} / {int(mapped.sum())}")
def fil(k): return re.sub(r".*wt-rd5main/", "", gm[k][1].split(":")[0])
final = list(st.values())[-1]
cats = {"ci": st["upstream, all CI flag sets"], "mt4": st["upstream, + t4f4"], "pend": list(st.values())[-2], "all": final}
rows = collections.defaultdict(lambda: [0] * 5)
for k in gm:
    if k >= N: continue
    f = fil(k); r = rows[f]; r[0] += 1
    if cats["ci"][k]: r[1] += 1
    elif cats["pend"][k]: r[2] += 1
    elif final[k]: r[3] += 1
    else: r[4] += 1
print(f"\n{'file':34s} {'edges':>6s} {'CI':>6s} {'+MRs/mt4':>8s} {'+arch':>6s} {'never':>6s}")
for f, r in sorted(rows.items(), key=lambda x: -(x[1][0] - x[1][1]))[:30]:
    print(f"{f:34s} {r[0]:6d} {r[1]:6d} {r[2]:8d} {r[3]:6d} {r[4]:6d}")
np.save("ci.npy", cats["ci"]); np.save("pend.npy", cats["pend"]); np.save("all.npy", final); np.save("ci_t1.npy", st["upstream t1 (CI coverage job)"])
