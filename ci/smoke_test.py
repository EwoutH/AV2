#!/usr/bin/env python3
"""
Smoke test for a freshly built avmenc/avmdec pair: encode a tiny synthetic
clip, decode it, and print the MD5 of the decoded frames.

Usage: python smoke_test.py <avmenc> <avmdec> [workdir]

The clip is generated here (a moving gradient), so the test needs no
downloads and gives every platform the same input. The stream size and
MD5 on the last lines end up in the build info, which makes differences
between platforms visible.
"""
import re
import subprocess
import sys
import tempfile
from pathlib import Path

WIDTH, HEIGHT, FRAMES = 176, 144, 5


def write_clip(path: Path):
    with open(path, "wb") as f:
        f.write(f"YUV4MPEG2 W{WIDTH} H{HEIGHT} F30:1 Ip A1:1 C420jpeg\n"
                .encode())
        for n in range(FRAMES):
            f.write(b"FRAME\n")
            f.write(bytes((x + 2 * y + 8 * n) & 0xFF
                          for y in range(HEIGHT) for x in range(WIDTH)))
            for plane in (3, 5):  # U, V
                f.write(bytes((plane * x + y + 4 * n) & 0xFF
                              for y in range(HEIGHT // 2)
                              for x in range(WIDTH // 2)))


def run(cmd):
    print("+ " + " ".join(str(c) for c in cmd), flush=True)
    r = subprocess.run([str(c) for c in cmd], stdout=subprocess.PIPE,
                       stderr=subprocess.STDOUT, text=True, errors="replace")
    print(r.stdout, flush=True)
    if r.returncode != 0:
        sys.exit(f"{Path(str(cmd[0])).name} failed with exit code "
                 f"{r.returncode & 0xFFFFFFFF:#x}")
    return r.stdout


def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    enc, dec = Path(sys.argv[1]), Path(sys.argv[2])
    work = Path(sys.argv[3] if len(sys.argv) > 3 else tempfile.mkdtemp())
    work.mkdir(parents=True, exist_ok=True)
    clip, stream = work / "smoke.y4m", work / "smoke.ivf"
    write_clip(clip)
    run([enc, clip, "-o", stream, "--ivf", f"--limit={FRAMES}",
         "--end-usage=q", "--qp=160", "--cpu-used=6"])
    if stream.stat().st_size < 100:
        sys.exit(f"{stream} is only {stream.stat().st_size} bytes")
    m = re.search(r"\b[0-9a-f]{32}\b", run([dec, stream, "--md5"]))
    if not m:
        sys.exit("no MD5 in avmdec output")
    print(f"stream bytes: {stream.stat().st_size}")
    print(f"decoded md5: {m[0]}")


if __name__ == "__main__":
    main()
