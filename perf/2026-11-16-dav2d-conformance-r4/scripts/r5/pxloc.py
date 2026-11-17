"""Where do dav2d and avmdec differ?  pxloc.py <stream> [dav2d build]"""
import subprocess, sys, numpy as np
from pathlib import Path
W = Path(__file__).resolve().parent.parent; B = W / "build"
s = sys.argv[1]; b = sys.argv[2] if len(sys.argv) > 2 else "r5"
tmp = Path(sys.argv[3] if len(sys.argv) > 3 else "/tmp")
y, a = tmp / "pl_d.y4m", tmp / "pl_a.yuv"
subprocess.run([str(B / b / "tools/dav2d"), "-q", "--threads", "1", "--filmgrain", "1", "-i", s, "-o", str(y)], check=True)
subprocess.run([str(B / "avm4/avmdec"), s, "--rawvideo", "-o", str(a)], check=True, capture_output=True)
raw = y.read_bytes(); nl = raw.index(b"\n")
tok = {t[:1].decode(): t[1:].decode() for t in raw[:nl].split()[1:]}
w, h, c = int(tok["W"]), int(tok["H"]), tok.get("C", "420")
ssx, ssy = {"420": (1, 1), "422": (1, 0), "444": (0, 0)}[c[:3]]
dt = np.uint16 if "p" in c else np.uint8
cw, ch = (w + ssx) >> ssx, (h + ssy) >> ssy
fr = [np.frombuffer(f[f.index(b"\n") + 1:], dt) for f in raw[nl + 1:].split(b"FRAME")[1:]]
ref = np.fromfile(a, dt); fs = w * h + 2 * cw * ch
print(f"{w}x{h} {c} frames {len(fr)} ref frames {ref.size / fs}")
for i, f in enumerate(fr):
    r = ref[i * fs:(i + 1) * fs]
    o = 0
    for p, (pw, ph) in enumerate([(w, h), (cw, ch), (cw, ch)]):
        d = f[o:o + pw * ph].reshape(ph, pw).astype(int) - r[o:o + pw * ph].reshape(ph, pw)
        o += pw * ph
        ys, xs = np.nonzero(d)
        if len(xs):
            print(f" f{i} p{p}: {len(xs)} px, x {xs.min()}-{xs.max()} y {ys.min()}-{ys.max()} maxabs {abs(d).max()}  cols {np.unique(xs)[:20].tolist()}  rows {np.unique(ys)[:20].tolist()}")
