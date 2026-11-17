"""For 12-bit streams where the two avmdec builds disagree and dav2d doesn't match av2-enc's avmdec: does dav2d match av2-normative?"""
import collections, json, sys
from pathlib import Path
W = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(W))
import stress4 as s4  # noqa: E402
AVMN = W.parent / "build/avmn/avmdec"
tri = [json.loads(l) for l in open(W / "triage.jsonl")]
rec = {json.loads(l)["id"]: json.loads(l) for l in open(W / "r5/recheck.jsonl")}
C = collections.Counter()
for t in tri:
    if t["avmn_agrees"] or rec[t["id"]]["r5"]["ok"]:
        continue
    info = json.load(open(W / "fail" / t["id"] / "info.json"))
    if info["cfg"]["flags"].get("--enable-cropping-window"):
        C["crop (skipped)"] += 1
        continue
    strm = next((W / "fail" / t["id"]).glob("stream.*"))
    n = s4.first_md5(s4.run([AVMN, strm, "--rawvideo", "--md5"], 600)[1])
    d = s4.first_md5(s4.run([W / "build/r5/tools/dav2d", "-q", "--threads", "1", "--filmgrain", "1",
                             "-i", strm, "--muxer", "md5", "-o", "-"], 600)[1])
    C["dav2d == av2-normative" if d == n else "dav2d matches neither"] += 1
print(C)
