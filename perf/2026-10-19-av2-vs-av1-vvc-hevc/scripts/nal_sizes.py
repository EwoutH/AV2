"""Annex-B NAL unit byte totals per type for .h264/.hevc/.266 files."""
import re, sys
from collections import Counter
from pathlib import Path

def nal_types(path):
    d = Path(path).read_bytes()
    starts = [m.start() for m in re.finditer(b"\x00\x00\x01", d)]
    out = Counter()
    for i, s in enumerate(starts):
        e = starts[i + 1] if i + 1 < len(starts) else len(d)
        nal = d[s + 3:e].rstrip(b"\x00")
        ext = Path(path).suffix
        if ext == ".h264": t = nal[0] & 0x1f
        elif ext == ".hevc": t = (nal[0] >> 1) & 0x3f
        else: t = (nal[1] >> 3) & 0x1f  # VVC: nal_unit_type in 2nd byte
        out[t] += len(nal) + 3
    return out

SEI = {".h264": {6}, ".hevc": {39, 40}, ".266": {23, 24}}
if __name__ == "__main__":
    for p in sys.argv[1:]:
        c = nal_types(p); sei = sum(v for k, v in c.items() if k in SEI[Path(p).suffix])
        print(f"{Path(p).name:60s} total={sum(c.values()):8d} sei={sei:6d} types={dict(c)}")
