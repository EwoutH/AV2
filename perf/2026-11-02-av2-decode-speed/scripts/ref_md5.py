"""Reference MD5s from avmdec, the AV2 reference decoder.

The release manifests hold `avmdec --md5` of the Y4M output (headers included).
This decodes each stream twice with avmdec: once as Y4M (must reproduce the
manifest: the stream still decodes as when it was made) and once as raw
pixels (`--rawvideo --md5`, the hash dav2d and rav2d also print). It rewrites
the stream lists with the pixel MD5 in column 5 and the Y4M check in column 6.

  python ref_md5.py <avmdec> <stream-dir> data/streams_all.tsv data/streams_core.tsv
"""
import re, subprocess, sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

avmdec, sdir, lists = sys.argv[1], Path(sys.argv[2]), sys.argv[3:]
MD5 = re.compile(r"\b[0-9a-f]{32}\b")


def md5(args):
    p = subprocess.run([avmdec, *args], capture_output=True, text=True)
    m = MD5.findall(p.stdout)
    return m[0] if p.returncode == 0 and m else None


def ref(row):
    ivf = str(sdir / row[0])
    y4m = md5([ivf, "--md5"])
    pix = md5([ivf, "--rawvideo", "--md5"])
    return row[0], pix, "y4m_ok" if y4m == row[4] else f"y4m_MISMATCH:{y4m}"


rows = {}
for lst in lists:
    for line in open(lst):
        if not line.startswith("#") and line.strip():
            f = line.rstrip("\n").split("\t")
            rows[f[0]] = f
with ThreadPoolExecutor(4) as ex:
    res = {name: (pix, chk) for name, pix, chk in ex.map(ref, rows.values())}
for lst in lists:
    out = ["# file\tframes\twidth\theight\tpixel_md5(avmdec --rawvideo --md5)\tmanifest_y4m_check"]
    for line in open(lst):
        if line.startswith("#") or not line.strip():
            continue
        f = line.rstrip("\n").split("\t")
        pix, chk = res[f[0]]
        out.append("\t".join(f[:4] + [pix or "NONE", chk]))
        if chk != "y4m_ok" or not pix:
            print("CHECK", f[0], pix, chk, file=sys.stderr)
    Path(lst).write_text("\n".join(out) + "\n")
print("done", len(res))
