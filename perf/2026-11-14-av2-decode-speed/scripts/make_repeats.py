"""Add a repeat count to the stream lists, so that every timed run lasts long enough.

A stream with fewer than TARGET luma megapixels (width x height x frames) is
decoded k = ceil(TARGET / mpix) times back to back in one timed run (bench.py
runs the decoder k times). 400 Mpix is about 1.6 s for the fastest decoder on
the pc (dav2d, 4 threads, ~250 Mpix/s).

Looped IVF files (the temporal units copied k times) were tried first: avmdec
and splot decode them to k copies of the original output, but dav2d 6fbce209
rejects most frames after the first copy ("Error parsing frame header").

  python scripts/make_repeats.py      (from the test folder)
  -> data/streams_{all,core,small}_rep.tsv
"""
import math
from pathlib import Path

TARGET = 400e6
D = Path(__file__).resolve().parent.parent / "data"
for name in ("all", "core", "small"):
    out = ["# file\tframes\twidth\theight\tpixel_md5(avmdec --rawvideo --md5)\trepeat\n"]
    for l in open(D / f"streams_{name}.tsv"):
        if l.startswith("#") or not l.strip():
            continue
        c = l.rstrip("\n").split("\t")
        k = max(1, math.ceil(TARGET / (int(c[1]) * int(c[2]) * int(c[3]))))
        out.append("\t".join(c[:5] + [str(k)]) + "\n")
    (D / f"streams_{name}_rep.tsv").write_text("".join(out))
    print(name, len(out) - 1)
