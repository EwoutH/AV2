"""Known-feature breakdown of the 12-bit streams where dav2d matches neither avmdec build."""
import collections, json
from pathlib import Path
W = Path(__file__).resolve().parent.parent
tri = [json.loads(l) for l in open(W / "triage.jsonl")]
rec = {json.loads(l)["id"]: json.loads(l) for l in open(W / "r5/recheck.jsonl")}
known = [("--global-error-resilient", "ger"), ("--disable-loopfilters-across-tiles", "lfat"),
         ("--lossless", "lossless"), ("--film-grain-test", "grain"), ("--denoise-noise-level", "grain"),
         ("--enable-fwd-kf", "fwdkf"), ("--enable-mfh-obu-signaling", "mfh?")]
C, rest = collections.Counter(), []
for t in tri:
    if t["avmn_agrees"] or rec[t["id"]]["r5"]["ok"]:
        continue
    c = json.load(open(W / "fail" / t["id"] / "info.json"))["cfg"]
    f = c["flags"]
    if f.get("--enable-cropping-window"):
        continue
    k = next((n for fl, n in known if fl in f), None)
    C[k or "none"] += 1
    if not k:
        rest.append((t["id"], c["src"], c["fmt"], c.get("rc"), c["frames"], sorted(f)))
print(C)
for r in rest[:15]:
    print(r)
