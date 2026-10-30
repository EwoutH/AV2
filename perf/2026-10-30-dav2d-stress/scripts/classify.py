"""Classify every kept stress failure: original verdict, patched dav2d
(1 thread C + asm, 4 frame threads), minimised flags, and a cause bucket.

  python -I classify.py <patched dav2d.exe> > classify.txt
Writes classify.json next to this script.
"""
import json, re, subprocess, sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
W = HERE.parent
REF = W / "enc1030/avm_build_windows/Release/avmdec.exe"
DAV = Path(sys.argv[1])

# flags covered by dav2d #67 (known unsupported / open upstream)
KNOWN67 = {"--enable-sframe", "--sframe-dist", "--sframe-mode", "--sframe-type",
           "--global-error-resilient", "--resize-mode", "--resize-denominator",
           "--resize-kf-denominator", "--enable-lcr", "--enable-operating-point-sets",
           "--timing-info"}
CROP = {"--enable-cropping-window"}


def md5(cmd, timeout=120):
    try:
        p = subprocess.run([str(c) for c in cmd], capture_output=True, text=True,
                           timeout=timeout)
    except subprocess.TimeoutExpired:
        return "hang"
    t = p.stdout.split()
    if p.returncode == 0 and t and re.fullmatch(r"[0-9a-f]{32}", t[0]):
        return t[0]
    return "crash" if p.returncode not in (0, 1) else "error"


def dav(f, *extra):
    return md5([DAV, "-q", "--filmgrain", "1", *extra, "-i", f, "--muxer", "md5", "-o", "-"])


def main():
    rows = {}
    for name in ("results.jsonl", "results_p.jsonl"):
        if not (HERE / name).exists():
            continue
        for line in open(HERE / name):
            r = json.loads(line)
            rows[r["id"]] = r
    out = []
    for d in sorted((HERE / "fail").iterdir()):
        r = rows.get(d.name)
        if not r:
            continue
        m = r.get("min")
        mflags = m["cfg"]["flags"] if isinstance(m, dict) else None
        f = d / "min.ivf" if (d / "min.ivf").exists() else d / "stream.ivf"
        cfg = m["cfg"] if isinstance(m, dict) and f.name == "min.ivf" else r
        flags = set(cfg["flags"])
        ref = md5([REF, f, "--rawvideo", "--md5", "--threads=1"])
        res = dict(id=d.name, file=f.name, src=cfg["src"], qp=cfg["qp"],
                   preset=cfg["preset"], frames=cfg["frames"], flags=cfg["flags"],
                   verdict=r.get("verdict"), ref_ok=len(ref) == 32)
        if not res["ref_ok"]:
            res["bucket"] = "AVM: avmdec fails on avmenc output"
            out.append(res)
            continue
        c1 = dav(f, "--threads", "1", "--cpumask", "0")
        a1 = dav(f, "--threads", "1")
        mt = dav(f, "--threads", "4", "--framedelay", "4")
        st = lambda x: "ok" if x == ref else x if x in ("hang", "crash", "error") else "mismatch"
        res.update(c=st(c1), asm=st(a1), mt=st(mt))
        low_q = cfg["qp"] <= 45 or "--lossless" in flags
        if flags & CROP:
            b = "not a bug: crop window not applied by dav2d CLI"
        elif res["c"] == res["asm"] == res["mt"] == "ok":
            b = "fixed by night patches"
        elif res["c"] == res["asm"] == "ok" and res["mt"] != "ok":
            b = "threads only (F1 lossless)" if low_q else "threads only (other)"
        elif flags & KNOWN67:
            b = "known upstream (#67: sframe/error-resilient/resize/lcr/ops/timing)"
        elif res["c"] != "ok" and res["asm"] != "ok":
            b = "open: C path"
        else:
            b = "open: asm only" if res["c"] == "ok" else "open: other"
        res["bucket"] = b
        out.append(res)
    json.dump(out, open(HERE / "classify.json", "w"), indent=1)
    cnt = Counter(x["bucket"] for x in out)
    print(f"{len(out)} kept failures")
    for b, n in cnt.most_common():
        print(f"  {n:4d}  {b}")
    print()
    # open C-path ones: group by minimised flag set
    groups = defaultdict(list)
    for x in out:
        if x["bucket"].startswith("open"):
            groups[tuple(sorted(x["flags"]))].append(x)
    for k, xs in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        x = xs[0]
        print(f"{len(xs):3d}x {list(k) or '(defaults)'}  e.g. {x['id']} {x['src']} "
              f"qp{x['qp']} s{x['preset']} {x['frames']}f  C={x['c']} asm={x['asm']} mt={x['mt']}")


if __name__ == "__main__":
    main()
