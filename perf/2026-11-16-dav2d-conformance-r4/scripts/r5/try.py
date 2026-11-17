"""Encode a source with avmenc flags and compare avmdec vs dav2d.
  python -I r5/try.py <src.y4m> <out.ivf|obu> [--dav build] [--crop l,r,t,b] -- <avmenc flags>
Prints avmdec md5 (avm4, avmn), dav2d md5 and per-frame first-diff plane."""
import argparse, subprocess, sys, hashlib
from pathlib import Path
W = Path(__file__).resolve().parent.parent
B = W / "build"
sys.path.insert(0, str(W)); import stress4 as s4
ap = argparse.ArgumentParser()
ap.add_argument("src"); ap.add_argument("out")
ap.add_argument("--dav", default="r5"); ap.add_argument("--noenc", action="store_true")
ap.add_argument("flags", nargs="*")
a = ap.parse_args()
out = Path(a.out)
if not a.noenc:
    cmd = [B / "avm4/avmenc", a.src, "-o", out, "--obu" if out.suffix == ".obu" else "--ivf", "--threads=1"] + a.flags
    p = subprocess.run([str(c) for c in cmd], capture_output=True, text=True)
    if p.returncode: print(p.stderr[-800:]); sys.exit(1)
crop = None
for f in a.flags:
    if f.startswith("--enable-cropping-window=1"): crop = [0, 0, 0, 0]
if crop is not None:
    d = dict(f.split("=") for f in a.flags if f.startswith("--crop-win"))
    crop = [int(d.get(f"--crop-win-{s}-offset", 0)) for s in ("left", "right", "top", "bottom")]
ref = s4.first_md5(subprocess.run([str(B / "avm4/avmdec"), str(out), "--rawvideo", "--md5"], capture_output=True).stdout)
refn = s4.first_md5(subprocess.run([str(W.parent / "build/avmn/avmdec"), str(out), "--rawvideo", "--md5"], capture_output=True).stdout)
res = {}
for b in a.dav.split(","):
    y = s4.WORK / f"try_{out.stem}_{b}.y4m"
    dc = [str(B / b / "tools/dav2d"), "-q", "--threads", "1", "--filmgrain", "1", "-i", str(out)]
    if crop:
        p = subprocess.run(dc + ["-o", str(y)], capture_output=True, text=True)
        md5 = s4.cropped_md5(y, crop) if p.returncode == 0 else None
        y.unlink(missing_ok=True)
    else:
        p = subprocess.run(dc + ["--muxer", "md5", "-o", "-"], capture_output=True, text=True)
        md5 = p.stdout.split()[0] if p.returncode == 0 and p.stdout.split() else None
    if md5 is None:
        md5 = f"rc{p.returncode} {' / '.join(p.stderr.strip().splitlines()[-3:])[:160]}"
    res[b] = md5
print(f"size {out.stat().st_size} avm4 {ref} avmn {refn}")
for b, m in res.items():
    print(f"  {b}: {m} {'OK' if m == ref else 'MISMATCH'}")
