#!/usr/bin/env python3
"""Decode a sample stream with dav2d or rav2d and compare against avmdec.

Usage: decode_test.py <dav2d|rav2d> <decoder binary> <stream.ivf> <avmdec>

Both sides are MD5s of the decoded planes only: `avmdec --rawvideo --md5`
for the reference, dav2d's md5 muxer, and the frame data of rav2d's Y4M
output. (The sample manifests hold `avmdec --md5` without --rawvideo, which
hashes avmdec's Y4M output *including* its headers, so it never matches
another decoder.) A mismatch or a failed decode is reported, not fatal.
"""
import hashlib
import os
import re
import subprocess
import sys


def y4m_payload_md5(path):
    """MD5 of the frame data in a Y4M file, skipping the stream and frame headers."""
    md5 = hashlib.md5()
    with open(path, "rb") as f:
        header = f.readline()
        params = dict((p[:1], p[1:]) for p in header.split()[1:])
        w, h = int(params[b"W"]), int(params[b"H"])
        cs = params.get(b"C", b"420jpeg")
        bps = 2 if re.search(rb"(p|mono)\d+$", cs) else 1  # e.g. 420p10
        cw, ch = (w + 1) // 2, (h + 1) // 2  # 4:2:0
        if cs.startswith(b"444"):
            cw, ch = w, h
        elif cs.startswith(b"422"):
            ch = h
        elif cs.startswith(b"mono"):
            cw = ch = 0
        frame = (w * h + 2 * cw * ch) * bps
        while f.readline().startswith(b"FRAME"):
            md5.update(f.read(frame))
    return md5.hexdigest()


def main():
    decoder, binary, stream, avmdec = sys.argv[1:5]
    name = os.path.basename(stream)
    ref = subprocess.run([avmdec, stream, "--rawvideo", "--md5"],
                         capture_output=True, text=True)
    expected = ref.stdout.split()[0] if ref.returncode == 0 and ref.stdout.strip() else None
    print(f"reference: avmdec --rawvideo --md5: {expected} (exit {ref.returncode})")
    if decoder == "dav2d":
        cmd = [binary, "-i", stream, "--muxer", "md5", "-o", "decoded.md5"]
    else:
        cmd = [binary, stream, "-o", "decoded.y4m"]
    print("command:", " ".join(cmd))
    result = subprocess.run(cmd, capture_output=True, text=True)
    print(result.stdout + result.stderr)
    if result.returncode != 0:
        print(f"decode test: {name} failed (exit {result.returncode})")
        return
    if decoder == "dav2d":
        got = open("decoded.md5").read().split()[0]
    else:
        got = y4m_payload_md5("decoded.y4m")
    if expected is None:
        verdict = "no avmdec reference"
    else:
        verdict = "matches avmdec" if got == expected else f"differs from avmdec {expected}"
    print(f"decode test: {name} md5 {got} ({verdict})")


if __name__ == "__main__":
    main()
