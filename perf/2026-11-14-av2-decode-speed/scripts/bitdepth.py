"""Bit depth and chroma format of each stream, from the Y4M header of its first
decoded frame (dav2d -l 1). Writes data/stream_format.tsv.

  python bitdepth.py <dav2d> <stream-dir> data/streams_all.tsv > data/stream_format.tsv
"""
import re, subprocess, sys
from pathlib import Path

dav2d, sdir, lst = sys.argv[1], Path(sys.argv[2]), sys.argv[3]
print("# file\tbitdepth\tchroma")
for line in open(lst):
    if line.startswith("#") or not line.strip():
        continue
    f = line.split("\t")[0]
    out = subprocess.run([dav2d, "-q", "-i", str(sdir / f), "-l", "1", "--muxer", "yuv4mpeg2", "-o", "-"],
                         capture_output=True).stdout[:200].split(b"\n")[0].decode(errors="replace")
    m = re.search(r" C(\d{3})(?:p(\d+))?", out)
    print(f"{f}\t{(m.group(2) or '8') if m else '?'}\t{m.group(1) if m else '?'}")
