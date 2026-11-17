import json, collections, sys
res = {}; ok = []
for l in open("results.jsonl"):
    r = json.loads(l)
    if r.get("verdict"): res[r["id"]] = r
    elif r.get("verdict") == []: ok.append(r)
tri = {json.loads(l)["id"]: json.loads(l) for l in open("triage.jsonl")}
mm = []
for l in open("r5/recheck.jsonl"):
    x = json.loads(l)
    if tri[x["id"]]["avmn_agrees"] and not x["r5"]["ok"] and not x["r5-asan"]["ok"]:
        mm.append(res[x["id"]]["cfg"])
def feats(c):
    f = {f"{k}={v}" if k in ("--film-grain-test",) else k for k, v in c["flags"].items()}
    f.add("rc=" + c.get("rc", "q")); f.add("fmt=" + c["fmt"])
    if c.get("obu"): f.add("obu")
    return f
fm = collections.Counter(x for c in mm for x in feats(c))
fo = collections.Counter(x for r in ok for x in feats(r["cfg"]))
print(len(mm), "mismatching;", len(ok), "ok")
rows = []
for k, n in fm.items():
    p = n / len(mm); q = fo[k] / len(ok)
    rows.append((p / max(q, 1e-4), k, n, p, q))
for e, k, n, p, q in sorted(rows, reverse=True)[:25]:
    print(f"{k:40s} in {n:3d} fails ({p:5.1%}) vs {q:5.1%} ok  x{e:.1f}")
# coverage: how many mismatches have none of the top suspects
sus = ["--global-error-resilient", "--enable-sframe", "--enable-cropping-window", "--enable-fwd-kf"]
left = [c for c in mm if not any(s in c["flags"] for s in sus)]
print("without", sus, ":", len(left))
fl = collections.Counter(x for c in left for x in feats(c))
for k, n in fl.most_common(15): print("  ", k, n, f"{fo[k]/len(ok):.1%}")
