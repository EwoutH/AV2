"""Characterise the stress failures where avmdec (av2-enc 487d0761) and av2-normative disagree."""
import collections, json
from pathlib import Path
W = Path(__file__).resolve().parent.parent
res = {}
for l in open(W / "results.jsonl"):
    r = json.loads(l)
    if r.get("verdict"):
        res[r["id"]] = r
tri = [json.loads(l) for l in open(W / "triage.jsonl")]
rec = {json.loads(l)["id"]: json.loads(l) for l in open(W / "r5/recheck.jsonl")}
C, F = collections.Counter(), collections.Counter()
for t in tri:
    if t["avmn_agrees"]:
        continue
    c = res[t["id"]]["cfg"]
    f = c["flags"]
    C[(c["fmt"], "12bit" if f.get("--bit-depth") == 12 else "8/10",
       "crop" if f.get("--enable-cropping-window") else "")] += 1
    C[("r5 matches avm4", rec[t["id"]]["r5"]["ok"])] += 1
    for k in f:
        F[k] += 1
for k, n in C.most_common():
    print(n, k)
print(F.most_common(8))
