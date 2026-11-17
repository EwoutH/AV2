"""Archive the round-4 stress streams + configs as a reusable dav2d regression set.

  python -I archive.py <dest>
Writes <dest>/streams/<id>.{ivf,obu} (kept passing streams and failing streams),
<dest>/src/<id>.y4m (random crops used by failing configs), <dest>/manifest.jsonl.
"""
import json, shutil, sys
from pathlib import Path
W = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(W))
import stress4 as s4  # noqa: E402
dest = Path(sys.argv[1])
(dest / "streams").mkdir(parents=True, exist_ok=True)
(dest / "src").mkdir(exist_ok=True)
tri = {json.loads(l)["id"]: json.loads(l) for l in open(W / "triage.jsonl")}
rec = {json.loads(l)["id"]: json.loads(l) for l in open(W / "r5/recheck.jsonl")}
clusters = {i: k for k, v in json.load(open(W / "r5/clusters.json")).items() for i in v}
byid = {}
for l in open(W / "results.jsonl"):
    r = json.loads(l)
    if r["id"] not in byid or r.get("verdict"):
        byid[r["id"]] = r
n = 0
with open(dest / "manifest.jsonl", "w") as fo:
    for i, r in sorted(byid.items()):
        if r.get("verdict") is None:
            continue
        cfg = r["cfg"]
        ext = "obu" if cfg.get("obu") else "ivf"
        if r["verdict"] == []:
            src_strm = W / "keep" / f"{i}.{ext}"
        else:
            src_strm = next((W / "fail" / i).glob("stream.*"), None)
        if not src_strm or not src_strm.exists():
            continue
        shutil.copy2(src_strm, dest / "streams" / f"{i}.{ext}")
        src_y4m = cfg["src"] + ".y4m"
        crop_src = W / "fail" / i / "src.y4m"
        if crop_src.exists():
            shutil.copy2(crop_src, dest / "src" / f"{i}.y4m")
            src_y4m = f"src/{i}.y4m"
        fl = cfg["flags"]
        row = dict(id=i, stream=f"streams/{i}.{ext}", src=src_y4m, fmt=cfg["fmt"],
                   bitdepth=fl.get("--bit-depth", "src"), frames=cfg["frames"],
                   crop=[fl[f"--crop-win-{s}-offset"] for s in ("left", "right", "top", "bottom")]
                   if fl.get("--enable-cropping-window") else None,
                   avmenc_args=s4.enc_cmd(cfg, "SRC.y4m", f"OUT.{ext}")[1:],
                   md5_avm_487d0761=r["res"]["ref"][1],
                   status_main_28e39df9_1018=("ok" if r["verdict"] == [] else r["verdict"]))
        if i in tri:
            row["avmn_14f43e4c_agrees"] = tri[i]["avmn_agrees"]
        if i in rec:
            row["main_7b187849_mrs_ok"] = rec[i]["r5"]["ok"] and rec[i]["r5-asan"]["ok"]
            row["cause_17nov"] = clusters.get(i, "fixed or ubsan-only" if rec[i]["r5"]["ok"] else "ref-disagreement")
        fo.write(json.dumps(row) + "\n")
        n += 1
print(n, "streams archived")
