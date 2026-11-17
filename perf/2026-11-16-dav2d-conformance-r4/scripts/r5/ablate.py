"""Re-encode a failing stress config with some flags dropped and compare.
  python -I r5/ablate.py <id[,id..]|@cluster> <drop-prefix[,..]|-> [--dav r5] [--workers 3]
Output: id, fails with full config?, fails with flags dropped?"""
import argparse, json, re, subprocess, sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
W = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(W)); import stress4 as s4
B = W / "build"
def check(cfg, src, tag, dav):
    out = s4.WORK / f"ab_{tag}.{'obu' if cfg.get('obu') else 'ivf'}"
    rc, _, _ = s4.run(s4.enc_cmd(cfg, src, out), 1800)
    if rc != 0: return "encfail"
    try:
        ref = s4.first_md5(s4.run([s4.AVMDEC, out, "--rawvideo", "--md5"], 600)[1])
        fl = cfg["flags"]
        crop = ([fl[f"--crop-win-{s}-offset"] for s in ("left", "right", "top", "bottom")]
                if fl.get("--enable-cropping-window") else [0, 0, 0, 0])
        y = s4.WORK / f"ab_{tag}.y4m"
        rc, _, err = s4.run([B / dav / "tools/dav2d", "-q", "--threads", "1", "--filmgrain", "1", "-i", out, "-o", y], 600)
        md5 = s4.cropped_md5(y, crop) if rc == 0 else None
        y.unlink(missing_ok=True)
        return "ok" if md5 == ref else ("mismatch" if rc == 0 else f"rc{rc}")
    finally:
        out.unlink(missing_ok=True)
def one(i, drops, dav):
    r = json.load(open(W / "fail" / i / "info.json"))
    cfg = r["cfg"]; d = W / "fail" / i
    src = str(d / "src.y4m") if (d / "src.y4m").exists() else s4.sources()[cfg["src"]]["path"]
    full = check(cfg, src, i + "f", dav)
    res = {"id": i, "full": full}
    for dp in drops:
        pre = dp.split("+")
        c2 = dict(cfg, flags={k: v for k, v in cfg["flags"].items() if not any(k.startswith(p) for p in pre)})
        res[dp] = check(c2, src, i + "d", dav) if c2["flags"] != cfg["flags"] else "n/a"
    return res
ap = argparse.ArgumentParser(); ap.add_argument("ids"); ap.add_argument("drops")
ap.add_argument("--dav", default="r5"); ap.add_argument("--workers", type=int, default=3)
a = ap.parse_args()
ids = json.load(open(W / "r5/clusters.json"))[a.ids[1:]] if a.ids.startswith("@") else a.ids.split(",")
drops = [] if a.drops == "-" else a.drops.split(",")
with ThreadPoolExecutor(a.workers) as ex:
    for r in ex.map(lambda i: one(i, drops, a.dav), ids):
        print(json.dumps(r), flush=True)
