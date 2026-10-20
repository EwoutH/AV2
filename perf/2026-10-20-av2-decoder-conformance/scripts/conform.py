"""Decode every local AV2 stream with each decoder; compare pixel MD5s.

Reference: `avmdec --rawvideo --md5` from the AVM build that made the stream
(MD5 of the decoded planes only). Note `avmdec --md5` without --rawvideo
hashes its Y4M output *including* the Y4M headers, which is what the sample
manifests store, so those cannot be compared with other decoders directly.

Decoders: dav2d (md5 muxer), rav2d (Y4M payload MD5, headers skipped),
avmdec nightly. Runs on the E-cores at below-normal priority, resumable.

  python conform.py [--jobs 3]
"""
import argparse, hashlib, json, subprocess, sys, tempfile, threading, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import psutil

HERE = Path(__file__).resolve().parent
W = HERE.parent
E_CORES = list(range(12, 20))
TMP = Path(tempfile.gettempdir())

AVMDEC_89E = W / "avm_build_windows/Release/avmdec.exe"         # av2-enc 89eae123d
AVMDEC_9C7 = W / "hd_long/avm_build_windows/Release/avmdec.exe"  # av2-enc 9c72cb56a
DECODERS = {
    "avmdec_nightly": HERE / "avm/avm-windows-x64/avmdec.exe",    # f1328e2ad1
    "dav2d_nightly_msvc": HERE / "dav2d/dav2d-windows-x64/dav2d.exe",
    "dav2d_gcc": HERE / "build-gcc/tools/dav2d.exe",
    "dav2d_patched_gcc": HERE / "build-gcc-fix/tools/dav2d.exe",
    "dav2d_patched_msvc": HERE / "build-msvc/tools/dav2d.exe",
    "rav2d_nightly": HERE / "rav2d/rav2d-windows-x64/rav2d.exe",
}


def streams():
    """(path, set, reference avmdec)."""
    out = [(p, "samples", AVMDEC_89E) for p in sorted((W / "encoded").glob("*.ivf"))]
    out += [(p, "hd", AVMDEC_9C7) for p in sorted((W / "hd_long/encoded").glob("*.ivf"))]
    out += [(p, "sweep", AVMDEC_89E) for p in sorted((W / "bench/sweep_out").glob("*.ivf"))]
    # skip streams still being written (the cross-codec run adds AVM encodes)
    return [x for x in out if time.time() - x[0].stat().st_mtime > 600]


def run(cmd, timeout=7200):
    p = subprocess.Popen([str(c) for c in cmd], stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE)
    try:
        ps = psutil.Process(p.pid)
        ps.cpu_affinity(E_CORES)
        ps.nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
    except psutil.Error:
        pass
    t0 = time.perf_counter()
    out, err = p.communicate(timeout=timeout)
    return p.returncode, out.decode(errors="replace"), \
        err.decode(errors="replace"), time.perf_counter() - t0


def y4m_payload_md5(path):
    md5, n = hashlib.md5(), 0
    with open(path, "rb") as f:
        hdr = dict((t[:1], t[1:]) for t in f.readline().split()[1:])
        w, h = int(hdr[b"W"]), int(hdr[b"H"])
        cs = hdr.get(b"C", b"420")
        bps = 2 if b"p1" in cs else 1
        fs = (w * h + 2 * ((w + 1) // 2) * ((h + 1) // 2)) * bps
        while f.readline().startswith(b"FRAME"):
            md5.update(f.read(fs))
            n += 1
    return md5.hexdigest(), n


def decode_md5(name, exe, ivf):
    if name.startswith("avmdec"):
        rc, out, err, t = run([exe, ivf, "--rawvideo", "--md5", "--threads=1"])
        return rc, out.split()[0] if rc == 0 and out.strip() else None, t, err
    if name.startswith("dav2d"):
        rc, out, err, t = run([exe, "-q", "--threads", "1", "--filmgrain", "1", "-i", ivf,
                               "--muxer", "md5", "-o", "-"])
        return rc, out.split()[0] if rc == 0 and out.strip() else None, t, err
    with tempfile.TemporaryDirectory() as td:
        y4m = Path(td) / "out.y4m"
        rc, out, err, t = run([exe, "-t", "1", "-o", y4m, ivf])
        md5 = y4m_payload_md5(y4m)[0] if rc == 0 and y4m.exists() else None
        return rc, md5, t, err


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--jobs", type=int, default=3)
    ap.add_argument("--results", default=str(HERE / "conform.jsonl"))
    a = ap.parse_args()
    res = Path(a.results)
    done = set()
    if res.exists():
        done = {(r["stream"], r["decoder"]) for r in map(json.loads, open(res))}
    lock = threading.Lock()
    todo = []
    for ivf, kind, ref in streams():
        todo.append((ivf, kind, "reference", ref))
        todo += [(ivf, kind, n, e) for n, e in DECODERS.items()]
    todo = [x for x in todo if (x[0].name, x[2]) not in done]
    # small streams first so partial results cover many streams
    todo.sort(key=lambda x: x[0].stat().st_size)
    print(f"{len(todo)} decodes to run", flush=True)

    def job(x):
        ivf, kind, name, exe = x
        try:
            rc, md5, t, err = decode_md5(
                "avmdec" if name == "reference" else name, exe, ivf)
        except subprocess.TimeoutExpired:
            rc, md5, t, err = -1, None, None, "timeout"
        row = dict(stream=ivf.name, set=kind, decoder=name, rc=rc, md5=md5,
                   wall=t and round(t, 2), bytes=ivf.stat().st_size,
                   err=err[-300:] if rc else None)
        with lock:
            with open(res, "a") as f:
                f.write(json.dumps(row) + "\n")
        print(f"{name:20s} {ivf.name:60s} rc={rc} {md5}", flush=True)

    with ThreadPoolExecutor(a.jobs) as ex:
        list(ex.map(job, todo))
    print("all done", flush=True)


if __name__ == "__main__":
    main()
