#!/usr/bin/env python3
"""Decode a sample stream with dav2d or rav2d and compare against the manifest.

Usage: decode_test.py <dav2d|rav2d> <decoder binary> <stream.ivf> <manifest.txt>

The manifest MD5 is avmdec's hash of the decoded planes. A mismatch or a
failed decode is reported, not fatal: the decoders may target a different
AV2 version than the AVM commit that made the samples.
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
    decoder, binary, stream, manifest = sys.argv[1:5]
    name = os.path.basename(stream)
    expected = next((line.split("\t")[2].strip() for line in open(manifest)
                     if line.startswith(name + "\t")), None)
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
    verdict = "matches avmdec" if got == expected else f"differs from avmdec {expected}"
    print(f"decode test: {name} md5 {got} ({verdict})")


if __name__ == "__main__":
    main()
