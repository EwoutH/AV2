"""Untimed output check: stream the decoder's raw planar output into an MD5 and compare it with the avmdec pixel
MD5 (column 5 of the stream list). Not timed; the speed runs use null output.

  python verify_raw.py --host pc --out data/verify_pc.jsonl --stream-dir DIR \
      --streams data/streams_core.tsv -- splot decode {ivf} --output-format raw -o -
"""
import argparse, hashlib, json, subprocess, tempfile, time
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("--host", required=True)
ap.add_argument("--decoder", default="splot")
ap.add_argument("--streams", required=True)
ap.add_argument("--stream-dir", default=".")
ap.add_argument("--out", required=True)
ap.add_argument("cmd", nargs="+")
a = ap.parse_args()

for line in open(a.streams):
    if line.startswith("#") or not line.strip():
        continue
    f = line.rstrip("\n").split("\t")
    argv = [x.replace("{ivf}", str(Path(a.stream_dir) / f[0])) for x in a.cmd]
    h, n = hashlib.md5(), 0
    # stderr goes to a file: a decoder that prints many errors would fill a pipe
    # and block while we are still reading stdout.
    with tempfile.TemporaryFile() as fe:
        p = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=fe)
        while chunk := p.stdout.read(1 << 20):
            h.update(chunk); n += len(chunk)
        rc = p.wait()
        fe.seek(0); err = fe.read().decode(errors="replace")
    md5 = h.hexdigest() if rc == 0 else None
    row = dict(host=a.host, decoder=a.decoder, stream=f[0], rc=rc, md5=md5,
               md5_ok=md5 == f[4], bytes=n, err_tail=err[-300:] if rc else "",
               ts=time.strftime("%Y-%m-%dT%H:%M:%S%z"))
    print(json.dumps(row), flush=True)
    with open(a.out, "a") as fo:
        fo.write(json.dumps(row) + "\n")
