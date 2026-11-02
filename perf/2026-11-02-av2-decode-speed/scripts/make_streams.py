"""Build streams.tsv (file, frames, width, height, md5) from the release manifests.

Width/height come from the IVF header; frames and MD5 from the manifests
(MD5 = avmdec --rawvideo --md5 of the decoded output).
  python make_streams.py <streams-dir> > streams.tsv
"""
import re, struct, sys
from pathlib import Path

root = Path(sys.argv[1])
print("# file\tframes\twidth\theight\tmd5")
for man in sorted(root.glob("*/*manifest.txt")):
    for line in open(man):
        if line.startswith("#") or not line.strip():
            continue
        f = line.rstrip("\r\n").split("\t")
        name, md5 = f[0], f[2]
        ivf = man.parent / name
        hdr = ivf.read_bytes()[:32]
        assert hdr[:4] == b"DKIF", ivf
        w, h = struct.unpack("<HH", hdr[12:16])
        frames = int(re.search(r"_(\d+)f\.ivf$", name).group(1))
        print(f"{man.parent.name}/{name}\t{frames}\t{w}\t{h}\t{md5}")
