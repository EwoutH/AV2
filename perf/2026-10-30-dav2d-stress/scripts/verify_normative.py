"""Decode each kept failure with av2-enc avmdec, av2-normative avmdec and
dav2d (C, 1 thread); print which agree."""
import json, re, subprocess, sys
from pathlib import Path
W = Path(__file__).resolve().parent.parent
ENC = W / "enc1030/avm_build_windows/Release/avmdec.exe"
NOR = W / "normative1030/build/Release/avmdec.exe"
DAV = W / "decoders/build1030-msvc/tools/dav2d.exe"
def md5(cmd):
    try:
        p = subprocess.run([str(c) for c in cmd], capture_output=True, text=True, timeout=300)
    except subprocess.TimeoutExpired:
        return "timeout"
    t = p.stdout.split()
    return t[0][:8] if p.returncode == 0 and t and re.fullmatch(r"[0-9a-f]{32}", t[0]) else f"rc{p.returncode}"
out = {}
for d in sorted((Path(__file__).parent / "fail").iterdir()):
    for name in ("min.ivf", "stream.ivf"):
        f = d / name
        if not f.exists():
            continue
        e = md5([ENC, f, "--rawvideo", "--md5", "--threads=1"])
        n = md5([NOR, f, "--rawvideo", "--md5", "--threads=1"])
        v = md5([DAV, "-q", "--threads", "1", "--cpumask", "0", "--filmgrain", "1", "-i", f, "--muxer", "md5", "-o", "-"])
        cls = ("enc==nor" if e == n else "ENC!=NOR") + (" dav==nor" if v == n else " dav!=nor")
        out[f"{d.name}/{name}"] = dict(enc=e, nor=n, dav=v, cls=cls)
        print(f"{d.name}/{name:10s} enc={e} nor={n} dav_c={v}  {cls}", flush=True)
json.dump(out, open(Path(__file__).parent / "verify_normative.json", "w"), indent=1)
