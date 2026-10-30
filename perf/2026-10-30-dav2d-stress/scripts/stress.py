"""Stress test: random avmenc tool configs on small clips, decoded by avmdec
(reference) and several dav2d variants. Mismatches and crashes are kept,
localised to the first bad frame/plane, and minimised (greedy flag removal,
then fewer frames).

Decoder variants tell the bug class apart:
  msvc     MSVC build, asm, 1 thread
  msvc_c   same, --cpumask 0 (C only)        -> fails too: C/parse bug
  gcc      GCC build, asm, 1 thread           -> differs from msvc: compiler
  msvc_mt  4 threads, framedelay 4            -> only this: threading bug

Runs on the E-cores at below-normal priority (the P-cores run the sweep).
Resumable; stop with a STOP file or at --stop-at.

  python -I stress.py --workers 6 --stop-at 07:15
  python -I stress.py --n 20 --results dry.jsonl      # quick check
"""
import argparse, datetime as dt, hashlib, json, os, random, re, shutil
import subprocess, threading, time
from pathlib import Path

import psutil

HERE = Path(__file__).resolve().parent
W = HERE.parent
SRC = HERE / "src"
BIN = W / "enc1030/avm_build_windows/Release"
ENC, AVMDEC = BIN / "avmenc.exe", BIN / "avmdec.exe"
D = W / "decoders"
MSVC = D / "build1030-msvc/tools/dav2d.exe"
GCC = D / "build1030-gcc/tools/dav2d.exe"
DECODERS = {
    "msvc": [MSVC, "--threads", "1"],
    "msvc_c": [MSVC, "--threads", "1", "--cpumask", "0"],
    "gcc": [GCC, "--threads", "1"],
    "msvc_mt": [MSVC, "--threads", "4", "--framedelay", "4"],
}
E_CORES = list(range(12, 20))  # --cores overrides
WORK, FAIL = HERE / "work", HERE / "fail"

# (flag, values). Most tools are on by default, so mostly "off" values.
ON_OFF = """cdef restoration deblocking gdf wiener-nonsep pc-wiener lf-sub-pu
sdp extended-sdp ext-partitions uneven-4way-partitions rect-partitions
tx-partition cfl-intra mhccp ibp mrls intra-dip smooth-intra paeth-intra
angle-delta intra-edge-filter idtx-intra fsc ist inter-ist inter-ddt cctx
flip-idtx tip-refinemv refinemv bawp cwp imp-msk-bld masked-comp
interinter-wedge interintra-comp interintra-wedge smooth-interintra
diff-wtd-comp onesided-comp skip-mode warped-motion warp-causal warp-delta
six-param-warp-delta warp-extend adaptive-mvd flex-mvres joint-mvd
mvd-sign-derive mv-traj ref-frame-mvs tpl-model avg-cdf""".split()
FLAGS = [(f"--enable-{n}", [0]) for n in ON_OFF] + [
    ("--enable-ccso", [0, 1]), ("--enable-cdef-on-skip-txfm", [0, 2]),
    ("--enable-intrabc", [0, 1]), ("--enable-intrabc-ext", [0, 2]),
    ("--enable-palette", [0, 1]), ("--enable-parity-hiding", [0, 1]),
    ("--enable-tcq", [0, 1]), ("--enable-trellis-quant", [0, 2]),
    ("--enable-tip", [0, 2]), ("--enable-opfl-refine", [0, 2, 3]),
    ("--enable-global-motion", [0, 1]), ("--enable-high-motion", [1]),
    ("--enable-refmvbank", [0, 1]), ("--enable-drl-reorder", [0, 2]),
    ("--reduced-ref-frame-mvs-mode", [1]), ("--max-drl-refmvs", [2, 3, 5, 8]),
    ("--max-drl-refbvs", [2, 3, 4]), ("--max-reference-frames", [1, 2, 3, 5]),
    ("--reduced-reference-set", [1]), ("--enable-bru", [1, 2]),
    ("--explicit-ref-frame-map", [1]),
    ("--enable-short-refresh-frame-flags", [1]), ("--dpb-size", [2, 4, 16]),
    ("--frame-parallel", [1]),
    ("--max-partition-size", [8, 16, 32, 64, 128]),
    ("--min-partition-size", [8, 16, 32]), ("--max-pb-aspect-ratio", [2, 4]),
    ("--reduced-tx-part-set", [1]), ("--use-intra-dct-only", [1]),
    ("--use-inter-dct-only", [1]), ("--use-intra-default-tx-only", [1]),
    ("--reduced-tx-type-set", [1]), ("--enable-chroma-dctonly", [1]),
    ("--tile-columns", [1, 2]), ("--tile-rows", [1, 2]),
    ("--num-tile-groups", [2, 3, 4]), ("--sb-size", ["64", "128", "256"]),
    ("--lag-in-frames", [0]), ("--kf-max-dist", [2, 3, 5]),
    ("--enable-fwd-kf", [1]), ("--enable-sframe", [1]),
    ("--sframe-dist", [2, 3, 4]), ("--sframe-mode", [1, 2]),
    ("--sframe-type", [1]), ("--gf-max-pyr-height", [0, 1, 2, 3]),
    ("--max-gf-interval", [2, 4, 8]), ("--enable-overlay", [1]),
    ("--auto-alt-ref", [0]), ("--resize-mode", [1, 2, 3]),
    ("--resize-denominator", [9, 12, 16]),
    ("--resize-kf-denominator", [10, 16]), ("--global-error-resilient", [1]),
    ("--cdf-update-mode", [0, 2]), ("--avg-cdf-type", [0, 1]),
    ("--cross-frame-cdf-init-mode", [0, 1]), ("--enable-ext-seg", [1]),
    ("--aq-mode", [1, 2, 3]), ("--deltaq-mode", [0, 2]),
    ("--enable-qm", [1]), ("--qm-min", [0, 4]), ("--qm-max", [8, 12]),
    ("--enable-chroma-deltaq", [1]), ("--tune-content", ["screen"]),
    ("--tune", ["ssim"]), ("--film-grain-test", list(range(1, 17))),
    ("--monochrome", [None]), ("--lossless", [1]),
    ("--enable-lcr", [1]), ("--enable-operating-point-sets", [1]),
    ("--enable-atlas", [1]), ("--timing-info", ["constant"]),
    ("--enable-mfh-obu-signaling", [1]), ("--scan-type-info", [1]),
    ("--enable-keyframe-filtering", [0, 2]), ("--gdf-unit-matches-sb", [1]),
    ("--ccso-unit-matches-sb", [1]), ("--enable-low-complexity-decode", [1]),
    ("--select-adaptive-ds", [0, 1, 2]), ("--sharpness", [1, 4, 7]),
    ("--add-sef-for-output", [1]), ("--enable-cropping-window", [1]),
    ("--crop-win-right-offset", [2, 8]), ("--crop-win-bottom-offset", [2, 6]),
    ("--erp-pruning-level", [0, 6]), ("--disable-kf", [None]),
]
FLAG_NAMES = [f for f, _ in FLAGS]
PRESETS = [(6, 4), (9, 2), (5, 1), (4, 1), (3, 1), (2, .4), (1, .2)]


def sources():
    out = {}
    for p in sorted(SRC.glob("*.y4m")):
        hdr = p.open("rb").readline().decode().split()
        tok = {t[0]: t[1:] for t in hdr[1:]}
        out[p.stem] = dict(path=p, w=int(tok["W"]), h=int(tok["H"]),
                           hbd="p10" in tok.get("C", ""))
    return out


def random_config(rng, srcs):
    name = rng.choice(list(srcs))
    s = srcs[name]
    area = s["w"] * s["h"]
    presets = [(p, w) for p, w in PRESETS if p >= 4 or area <= 70000]
    preset = rng.choices([p for p, _ in presets], [w for _, w in presets])[0]
    band = rng.random()
    qp = (rng.randint(0, 60) if band < .2 else rng.randint(61, 199)
          if band < .8 else rng.randint(200, 255))
    if s["hbd"] and rng.random() < .15:
        qp = rng.randint(-48, 0)
    frames = rng.choice([1, 2, 3, 4, 6, 8, 8, 10, 12, 16])
    # half the configs have few flags (easy to triage), half many
    k = rng.choice([1, 2, 3]) if rng.random() < .5 else rng.randint(4, 14)
    flags = {}
    for f, vals in rng.sample(FLAGS, k):
        flags[f] = rng.choice(vals)
    return dict(src=name, preset=preset, qp=qp, frames=frames, flags=flags)


def enc_cmd(cfg, ivf):
    s = SRC / f"{cfg['src']}.y4m"
    cmd = [ENC, s, "-o", ivf, "--ivf", f"--limit={cfg['frames']}",
           "--end-usage=q", f"--qp={cfg['qp']}",
           f"--cpu-used={cfg['preset']}", "--threads=1"]
    for f, v in cfg["flags"].items():
        cmd.append(f if v is None else f"{f}={v}")
    return [str(c) for c in cmd]


def run(cmd, timeout, threads=1, **kw):
    p = subprocess.Popen([str(c) for c in cmd], stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE, **kw)
    try:
        ps = psutil.Process(p.pid)
        ps.cpu_affinity(E_CORES)
        ps.nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
    except psutil.Error:
        pass
    try:
        out, err = p.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        p.kill()
        out, err = p.communicate()
        return "timeout", out.decode(errors="replace"), err.decode(errors="replace")
    return p.returncode, out.decode(errors="replace"), err.decode(errors="replace")


def first_md5(out):
    t = out.split()
    return t[0] if t and re.fullmatch(r"[0-9a-f]{32}", t[0]) else None


def decode_all(ivf, names=None):
    """{decoder: (rc, md5, stderr tail)}; 'ref' is avmdec."""
    res = {}
    rc, out, err = run([AVMDEC, ivf, "--rawvideo", "--md5", "--threads=1"], 300)
    res["ref"] = (rc, first_md5(out) if rc == 0 else None, err[-300:])
    for n, cmd in DECODERS.items():
        if names and n not in names:
            continue
        rc, out, err = run(cmd + ["-q", "--filmgrain", "1", "-i", ivf,
                                  "--muxer", "md5", "-o", "-"], 300)
        res[n] = (rc, first_md5(out) if rc == 0 else None, err[-300:])
    return res


def verdict(res):
    """Failure signature: sorted list of 'dec:kind', or [] when all match.
    None when the reference itself failed (AVM problem, logged apart)."""
    ref = res["ref"]
    if ref[0] != 0 or not ref[1]:
        return None
    bad = []
    for n, (rc, md5, _) in res.items():
        if n == "ref":
            continue
        if rc == "timeout":
            bad.append(f"{n}:hang")
        elif rc != 0:
            bad.append(f"{n}:crash" if isinstance(rc, int) and
                       (rc < 0 or rc > 255) else f"{n}:error")
        elif md5 != ref[1]:
            bad.append(f"{n}:mismatch")
    return sorted(bad)


def attempt(cfg, tag):
    """Encode and decode one config. Returns (row, ivf path or None)."""
    ivf = WORK / f"{tag}.ivf"
    t0 = time.time()
    rc, out, err = run(enc_cmd(cfg, ivf), 1800)
    row = dict(cfg, enc_rc=rc, enc_s=round(time.time() - t0, 1))
    if rc != 0 or not ivf.exists() or ivf.stat().st_size == 0:
        row["enc_err"] = (err.strip().splitlines() or [""])[-1][-200:]
        ivf.unlink(missing_ok=True)
        return row, None
    row["bytes"] = ivf.stat().st_size
    res = decode_all(ivf)
    row["dec"] = {n: [r[0], r[1]] for n, r in res.items()}
    row["errs"] = {n: r[2] for n, r in res.items() if r[0] != 0}
    row["verdict"] = verdict(res)
    return row, ivf


def still_fails(cfg, sig_decs, tag):
    """Re-encode cfg; True if any of sig_decs still fails the same way."""
    row, ivf = attempt(cfg, tag)
    if ivf:
        ivf.unlink(missing_ok=True)
    v = row.get("verdict")
    return bool(v) and any(s in v for s in sig_decs), row


def minimise(cfg, sig, tag, deadline):
    """Greedy: drop flags one at a time, then fewer frames, then faster
    preset, keeping the failure. Returns (min cfg, tries)."""
    cur, tries = json.loads(json.dumps(cfg)), 0
    # cheap reductions first so the flag tries run faster
    if cur["preset"] != 9:
        cand = dict(cur, preset=9)
        ok, _ = still_fails(cand, sig, f"{tag}_m{tries}")
        tries += 1
        if ok:
            cur = cand
    for fr in (1, 2, 3, 4, 6, 8, 10, 12):
        if fr >= cur["frames"] or time.time() > deadline:
            break
        cand = dict(cur, frames=fr)
        ok, _ = still_fails(cand, sig, f"{tag}_m{tries}")
        tries += 1
        if ok:
            cur = cand
            break
    for f in list(cur["flags"]):
        if time.time() > deadline:
            break
        cand = dict(cur, flags={k: v for k, v in cur["flags"].items() if k != f})
        ok, _ = still_fails(cand, sig, f"{tag}_m{tries}")
        tries += 1
        if ok:
            cur = cand
    return cur, tries


def localise(ivf, outdir, dec="msvc_c"):
    """First differing frame and plane between avmdec and dav2d msvc_c
    (per-frame raw files). Returns a dict or None."""
    a, b = outdir / "avm", outdir / "dav"
    for d in (a, b):
        shutil.rmtree(d, ignore_errors=True)
        d.mkdir(parents=True)
    run([AVMDEC, ivf, "--rawvideo", "-o", a / "f_%w_%h_%4.yuv"], 300)
    run(DECODERS[dec] + ["-q", "--filmgrain", "1", "-i", ivf, "-o",
                              b / "f_%w_%h_%n.yuv"], 300)
    key = lambda p: int(p.stem.split("_")[-1])
    fa, fb = sorted(a.glob("*.yuv"), key=key), sorted(b.glob("*.yuv"), key=key)
    info = dict(frames_avm=len(fa), frames_dav=len(fb))
    for i, (x, y) in enumerate(zip(fa, fb)):
        _, w, h, _ = x.stem.split("_")
        w, h = int(w), int(h)
        da, db = x.read_bytes(), y.read_bytes()
        if da == db:
            continue
        info.update(frame=i, size_avm=f"{w}x{h}",
                    size_dav="x".join(y.stem.split("_")[1:3]))
        if len(da) != len(db):
            info["note"] = f"frame bytes differ {len(da)} vs {len(db)}"
            break
        cw, ch = (w + 1) // 2, (h + 1) // 2
        bps = len(da) // (w * h + 2 * cw * ch) or 1
        planes = [("Y", w, h), ("U", cw, ch), ("V", cw, ch)]
        off, diffs = 0, {}
        for pn, pw, ph in planes:
            n = pw * ph * bps
            pa, pb = da[off:off + n], db[off:off + n]
            if pa != pb:
                idx = [j for j in range(0, n, bps) if pa[j:j + bps] != pb[j:j + bps]]
                px = [j // bps for j in idx]
                xs, ys = [p % pw for p in px], [p // pw for p in px]
                diffs[pn] = dict(count=len(px), first=(xs[0], ys[0]),
                                 bbox=(min(xs), min(ys), max(xs), max(ys)))
            off += n
        info["planes"] = diffs
        break
    else:
        if len(fa) == len(fb):
            info["note"] = "per-frame outputs equal (md5 path differs)"
    shutil.rmtree(a, ignore_errors=True)
    shutil.rmtree(b, ignore_errors=True)
    return info


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--n", type=int, help="stop after n configs")
    ap.add_argument("--seed", type=int, default=20261030)
    ap.add_argument("--results", default="results.jsonl")
    ap.add_argument("--stop-at", help="HH:MM local")
    ap.add_argument("--cores", help="e.g. 0-11 (default: E-cores 12-19)")
    ap.add_argument("--prefix", default="c", help="id prefix, e.g. p for a second run")
    ap.add_argument("--min-budget", type=float, default=900,
                    help="max seconds spent minimising one failure")
    a = ap.parse_args()
    global E_CORES
    if a.cores:
        lo, hi = map(int, a.cores.split("-"))
        E_CORES = list(range(lo, hi + 1))
    for d in (WORK, FAIL):
        d.mkdir(exist_ok=True)
    srcs = sources()
    res_path = HERE / a.results
    start_i = sum(1 for _ in open(res_path)) if res_path.exists() else 0
    stop = None
    if a.stop_at:
        h, m = map(int, a.stop_at.split(":"))
        now = dt.datetime.now()
        t = now.replace(hour=h, minute=m, second=0, microsecond=0)
        stop = (t if t > now else t + dt.timedelta(days=1)).timestamp()
    lock = threading.Lock()
    state = dict(i=start_i, n=0, fails=0)
    minimal = []  # minimised flag sets already found (dedupe)

    def done():
        return ((stop and time.time() > stop) or (HERE / "STOP").exists()
                or (a.n and state["n"] >= a.n))

    def worker():
        while not done():
            with lock:
                i = state["i"]
                state["i"] += 1
                state["n"] += 1
            # deterministic per index, so a resumed run continues the sequence
            cfg = random_config(random.Random(a.seed * 1000003 + i), srcs)
            tag = f"{a.prefix}{i:06d}"
            row, ivf = attempt(cfg, tag)
            row["id"] = tag
            v = row.get("verdict")
            if ivf and (v or v is None):
                fd = FAIL / tag
                fd.mkdir(exist_ok=True)
                shutil.copy(ivf, fd / "stream.ivf")
                (fd / "cmd.txt").write_text(" ".join(enc_cmd(cfg, "stream.ivf")) + "\n")
                if v:
                    sig = v
                    mism = [x.split(":")[0] for x in v if x.endswith("mismatch")]
                    ldec = "msvc_c" if "msvc_c" in mism else (mism or ["msvc_c"])[0]
                    row["where"] = localise(ivf, fd, ldec) if mism else None
                    flags = set(cfg["flags"])
                    known = any(set(m) <= flags and ms == sig
                                for m, ms in minimal)
                    if not known and (not stop or time.time() + 300 < stop):
                        mcfg, tries = minimise(cfg, sig, tag,
                                               time.time() + a.min_budget)
                        mrow, mivf = attempt(mcfg, tag + "_min")
                        row["min"] = dict(cfg=mcfg, tries=tries,
                                          verdict=mrow.get("verdict"))
                        if mivf:
                            shutil.move(mivf, fd / "min.ivf")
                            (fd / "min_cmd.txt").write_text(
                                " ".join(enc_cmd(mcfg, "min.ivf")) + "\n")
                            if mism:
                                row["min"]["where"] = localise(fd / "min.ivf", fd, ldec)
                        with lock:
                            minimal.append((list(mcfg["flags"]), sig))
                    else:
                        row["min"] = "skipped (flags cover a known minimal set)"
                (fd / "row.json").write_text(json.dumps(row, indent=1))
            if ivf:
                ivf.unlink(missing_ok=True)
            with lock:
                if v:
                    state["fails"] += 1
                with open(res_path, "a") as f:
                    f.write(json.dumps(row) + "\n")
                print(f"{time.strftime('%H:%M:%S')} {tag} {cfg['src']} "
                      f"s{cfg['preset']} qp{cfg['qp']} {cfg['frames']}f "
                      f"{len(cfg['flags'])} flags enc={row['enc_rc']} "
                      f"{row.get('enc_s')}s verdict={v} "
                      f"[fails {state['fails']}/{state['n']}]", flush=True)

    ts = [threading.Thread(target=worker) for _ in range(a.workers)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    print("STRESS DONE", flush=True)


if __name__ == "__main__":
    main()
