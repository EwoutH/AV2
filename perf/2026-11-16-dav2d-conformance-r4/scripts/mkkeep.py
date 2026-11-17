"""Manifest of the passing stress4 streams in round4/keep/ for pidec.py on the pi (keep_manifest.json).
Skips cropping-window configs (dav2d's md5 is uncropped there). pc md5s: asm 1t, asan (C) and the mt mode.
  python -I mkkeep.py; rsync -a ../keep keep_manifest.json agent@pi.home:av2conf-r4/
  ssh agent@pi.home 'cd ~/av2conf-r4 && nohup setsid nice -n 19 sh -c "$(nix shell nixpkgs#python3 -c sh -c \"command -v python3\") pidec.py keep_manifest.json keep keep.jsonl" > keep.log 2>&1 < /dev/null &'
"""
import json
from pathlib import Path
R = Path("/srv/compression/cache/av2conf/round4")
man = []
for l in open(R / "results.jsonl"):
    r = json.loads(l)
    if r.get("verdict") != [] or r["cfg"]["flags"].get("--enable-cropping-window"):
        continue
    f = R / "keep" / f"{r['id']}.{'obu' if r['cfg'].get('obu') else 'ivf'}"
    if not f.exists():
        continue
    res = r["res"]
    mt = next(v[1] for k, v in res.items() if k.startswith("mt"))
    man.append(dict(name=f.name, ref=res["ref"][1], pc1t=res["asm"][1], pcc=res["asan"][1], pcmt4=mt))
json.dump(man, open(R / "pi/keep_manifest.json", "w"), indent=0)
print(len(man), "streams")
