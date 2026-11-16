"""Round-4 dav2d stress test: random avmenc configs, decoded by avmdec (av2-enc
487d0761) and dav2d main 28e39df9. New against round 3 (stress3.py):

  - 4:2:2 / 4:4:4 sources, 12-bit coding, random crops of the sources (odd and
    tiny sizes), rate control (cbr/vbr/cq, --rt), cropping window, still
    picture header, denoiser film grain, .obu (section 5) output and a few
    header/metadata flags round 3 never set
  - decoders: asm 1t; C with ASan+UBSan 1t (also catches memory errors that
    don't change the MD5); asm with a random thread/framedelay combination
  - known unimplemented features are left out (BRU, RAS --sframe-type=1,
    --resize-mode 2/3); round 3 already tracks those

Resumable (appends to results.jsonl); stop with a STOP file or --stop-at HH:MM.
  python -I stress4.py --workers 3 --stop-at 06:30
"""
import argparse, datetime as dt, hashlib, json, os, random, re, shutil
import subprocess, threading, time, traceback
from pathlib import Path

W = Path(__file__).resolve().parent
PY = "/run/current-system/sw/bin/python"  # the ds env; a nix dev shell python has no numpy
SRC_DIRS = [W.parent / "src_y4m", W / "src_y4m"]
B = W / "build"
ENC, AVMDEC = B / "avm4/avmenc", B / "avm4/avmdec"
DAV_BUILD = os.environ.get("R4_DAV", "main")  # main-1018 = main + !1018 (CfL padding, #86)
DAV, DAVASAN = B / DAV_BUILD / "tools/dav2d", B / f"{DAV_BUILD}-asan/tools/dav2d"
WORK, FAIL, KEEP = W / "work", W / "fail", W / "keep"
ASAN_ENV = dict(os.environ,
                ASAN_OPTIONS="detect_leaks=1:abort_on_error=0:exitcode=86",
                UBSAN_OPTIONS="print_stacktrace=1")

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
    ("--reduced-reference-set", [1]),
    ("--explicit-ref-frame-map", [1]),
    ("--enable-short-refresh-frame-flags", [1]), ("--dpb-size", [8, 16]),
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
    ("--gf-max-pyr-height", [0, 1, 2, 3]),
    ("--max-gf-interval", [2, 4, 8]), ("--enable-overlay", [1]),
    ("--auto-alt-ref", [0]), ("--resize-mode", [1]),
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
    ("--add-sef-for-output", [1]), ("--erp-pruning-level", [0, 6]),
    ("--disable-kf", [None]), ("--row-mt", [0]),
    # new in round 4
    ("--denoise-noise-level", [5, 20, 50]), ("--denoise-block-size", [16, 32]),
    ("--chroma-sample-position", [0, 1, 2]),
    ("--color-primaries", ["bt709", "bt2020"]),
    ("--transfer-characteristics", ["smpte2084", "hlg"]),
    ("--matrix-coefficients", ["bt709", "bt2020ncl"]),
    ("--kf-min-dist", [0, 2]), ("--min-gf-interval", [2, 4]),
    ("--gf-min-pyr-height", [0, 1, 2]), ("--enable-opfl-mv-search", [0, 1]),
    ("--monotonic-output-order", [1]), ("--num-operating-point-sets", [1, 2]),
    ("--enable-banding-metadata", [1]), ("--use-short-metadata", [1]),
    ("--disable-loopfilters-across-tiles", [1]), ("--quant-b-adapt", [1]),
    ("--min-qp", [0, 40]), ("--max-qp", [180, 255]),
]
PRESETS = [(6, 4), (9, 2), (5, 1), (4, 1), (3, 1), (2, .4), (1, .2)]


def supported_flags():
    h = subprocess.run([str(ENC), "--help"], capture_output=True, text=True)
    txt = h.stdout + h.stderr
    keep = [(f, v) for f, v in FLAGS if re.search(re.escape(f) + r"\b", txt)]
    return keep, sorted(set(f for f, _ in FLAGS) - set(f for f, _ in keep))


def sources():
    out = {}
    for d in SRC_DIRS:
        for p in sorted(d.glob("*.y4m")):
            hdr = p.open("rb").readline().decode().split()
            tok = {t[0]: t[1:] for t in hdr[1:]}
            c = tok.get("C", "420")
            out[p.stem] = dict(path=str(p), w=int(tok["W"]), h=int(tok["H"]),
                               hbd="p10" in c, fmt=c[:3])
    return out


def random_config(rng, srcs, flags):
    fmt = rng.choices(["420", "422", "444"], [85, 10, 5])[0]  # 422/444 low until #101 (chroma on inter frames) is fixed
    name = rng.choice([n for n, s in srcs.items() if s["fmt"] == fmt])
    s = srcs[name]
    cfg = dict(src=name, fmt=fmt)
    w, h = s["w"], s["h"]
    if rng.random() < .15:  # random crop: odd and tiny sizes
        cw = rng.choice([rng.randint(1, 24), rng.randint(16, w)])
        ch = rng.choice([rng.randint(1, 24), rng.randint(16, h)])
        cw, ch = min(cw, w), min(ch, h)
        cfg["crop_src"] = [cw, ch, rng.randint(0, w - cw), rng.randint(0, h - ch)]
        w, h = cw, ch
    area = w * h
    presets = [(p, wt) for p, wt in PRESETS if p >= 4 or area <= 70000]
    cfg["preset"] = rng.choices([p for p, _ in presets], [wt for _, wt in presets])[0]
    band = rng.random()
    qp = (rng.randint(0, 60) if band < .2 else rng.randint(61, 199)
          if band < .8 else rng.randint(200, 255))
    bd12 = rng.random() < .15
    if (s["hbd"] or bd12) and rng.random() < .15:
        qp = rng.randint(-48 if not bd12 else -96, 0)
    cfg["qp"] = qp
    cfg["frames"] = rng.choice([1, 2, 3, 4, 6, 8, 8, 10, 12, 16, 20])
    k = rng.choice([1, 2, 3]) if rng.random() < .5 else rng.randint(4, 14)
    fl = {f: rng.choice(v) for f, v in rng.sample(flags, k)}
    if bd12:
        fl["--bit-depth"] = 12
        fl["--input-bit-depth"] = 10 if s["hbd"] else 8
    rc = rng.choices(["q", "cbr", "vbr", "cq", "rt"], [70, 8, 8, 6, 8])[0]
    cfg["rc"] = rc
    if rc in ("cbr", "vbr", "cq", "rt"):
        fl["--target-bitrate"] = rng.choice([30, 100, 300, 1000])
    if rc == "vbr" and rng.random() < .5:
        fl["--passes"] = 2
    if rng.random() < .05:
        cfg["frames"] = 1
        fl["--full-still-picture-hdr"] = None
    if (rng.random() < .08 and "--monochrome" not in fl and "crop_src" not in cfg
            and not any(f.startswith("--resize") for f in fl) and w >= 32 and h >= 32):
        fl["--enable-cropping-window"] = 1
        for side in ("left", "right", "top", "bottom"):
            fl[f"--crop-win-{side}-offset"] = 2 * rng.randint(0, 4)
    cfg["obu"] = rng.random() < .1
    cfg["flags"] = fl
    return cfg


def enc_cmd(cfg, src, out):
    rc = cfg.get("rc", "q")
    cmd = [ENC, src, "-o", out, "--obu" if cfg.get("obu") else "--ivf",
           f"--limit={cfg['frames']}", f"--cpu-used={cfg['preset']}", "--threads=1"]
    if rc == "rt":
        cmd += ["--rt", "--end-usage=cbr"]
    elif rc == "q":
        cmd += ["--end-usage=q", f"--qp={cfg['qp']}"]
    else:
        cmd += [f"--end-usage={rc}"] + ([f"--qp={cfg['qp']}"] if rc == "cq" else [])
    for f, v in cfg["flags"].items():
        cmd.append(f if v is None else f"{f}={v}")
    return [str(c) for c in cmd]


def run(cmd, timeout, env=None):
    try:
        p = subprocess.run([str(c) for c in cmd], capture_output=True, env=env,
                           timeout=timeout, preexec_fn=lambda: os.nice(10))
    except subprocess.TimeoutExpired:
        return "timeout", b"", ""
    return p.returncode, p.stdout, p.stderr.decode(errors="replace")


def first_md5(out):
    t = out.decode(errors="replace").split()
    return t[0] if t and re.fullmatch(r"[0-9a-f]{32}", t[0]) else None


def cropped_md5(y4m, crop):
    """MD5 of a dav2d y4m output with the sequence cropping window applied."""
    data = y4m.read_bytes()
    nl = data.index(b"\n")
    tok = {t[:1]: t[1:] for t in data[:nl].decode().split()[1:]}
    w, h, c = int(tok["W"]), int(tok["H"]), tok.get("C", "420")
    bpp = 2 if "p1" in c else 1
    ssx, ssy = {"420": (1, 1), "422": (1, 0), "444": (0, 0)}.get(c[:3], (1, 1))
    l, r, t, b = crop
    cw, chh = (w + ssx) >> ssx, (h + ssy) >> ssy
    planes = [(w, h, 0, 0), (cw, chh, ssx, ssy), (cw, chh, ssx, ssy)]
    if c.startswith("mono"):
        planes = planes[:1]
    m, pos = hashlib.md5(), nl + 1
    while pos < len(data):
        pos = data.index(b"\n", pos) + 1
        for pw, ph, sx, sy in planes:
            x0, x1 = l >> sx, pw - (r >> sx)
            y0, y1 = t >> sy, ph - (b >> sy)
            for y in range(y0, y1):
                o = pos + (y * pw + x0) * bpp
                m.update(data[o:o + (x1 - x0) * bpp])
            pos += pw * ph * bpp
    return m.hexdigest()


def decoders(rng):
    t = rng.choice([2, 3, 4, 6])
    fd = rng.choice([1, 2, 3, 4, t])
    return {"asm": ([DAV, "--threads", "1"], None, 120),
            "asan": ([DAVASAN, "--threads", "1"], ASAN_ENV, 600),
            f"mt{t}f{fd}": ([DAV, "--threads", str(t), "--framedelay", str(fd)], None, 120)}


def decode_all(strm, cfg, rng, tag):
    res = {}
    rc, out, err = run([AVMDEC, strm, "--rawvideo", "--md5", "--threads=1"], 600)
    res["ref"] = (rc, first_md5(out) if rc == 0 else None, err[-300:])
    fl = cfg["flags"]
    crop = None
    if fl.get("--enable-cropping-window"):
        crop = [fl[f"--crop-win-{s}-offset"] for s in ("left", "right", "top", "bottom")]
    for n, (cmd, env, to) in decoders(rng).items():
        if crop:
            y4m = WORK / f"{tag}_{n}.y4m"
            rc, out, err = run(cmd + ["-q", "--filmgrain", "1", "-i", strm, "-o", y4m], to, env)
            md5 = cropped_md5(y4m, crop) if rc == 0 else None
            y4m.unlink(missing_ok=True)
        else:
            rc, out, err = run(cmd + ["-q", "--filmgrain", "1", "-i", strm,
                                      "--muxer", "md5", "-o", "-"], to, env)
            md5 = first_md5(out) if rc == 0 else None
        san = bool(re.search(r"runtime error:|AddressSanitizer|LeakSanitizer", err))
        res[n] = (rc, md5, err[-1500:] if san else err[-300:], san)
    return res


def verdict(res):
    ref = res["ref"]
    if ref[0] != 0 or not ref[1]:
        return None
    bad = []
    for n, r in res.items():
        if n == "ref":
            continue
        rc, md5, _, san = r
        if san:
            bad.append(f"{n}:sanitizer")
        if rc == "timeout":
            bad.append(f"{n}:hang")
        elif rc != 0 and not san:
            bad.append(f"{n}:crash" if rc < 0 else f"{n}:error")
        elif rc == 0 and md5 != ref[1]:
            bad.append(f"{n}:mismatch")
    return sorted(bad)


def worker(wid, rng, srcs, flags, args, lock, results, counter):
    errs = 0
    while True:
        if (W / "STOP").exists():
            return
        try:
            if one_config(wid, rng, srcs, flags, args, lock, results, counter) is False:
                return
            errs = 0
        except Exception:
            errs += 1
            with lock:
                print(f"worker {wid}: config failed ({errs} in a row)\n{traceback.format_exc()}", flush=True)
                with open(W / "worker_errors.log", "a") as f:
                    f.write(traceback.format_exc() + "\n")
            if errs >= 10:
                print(f"worker {wid}: giving up", flush=True)
                return


def one_config(wid, rng, srcs, flags, args, lock, results, counter):
    if (W / "STOP").exists():
        return False
    if args.stop_dt and dt.datetime.now() >= args.stop_dt:
        return False
    with lock:
        counter[0] += 1
        i = counter[0]
        if args.n and i > args.n:
            return False
    tag = f"{args.prefix}{i:06d}"
    cfg = random_config(rng, srcs, flags)
    src = srcs[cfg["src"]]["path"]
    tmp_src = None
    if "crop_src" in cfg:
        tmp_src = WORK / f"{tag}_src.y4m"
        cw, ch, x, y = cfg["crop_src"]
        subprocess.run([PY, "-I", str(W / "tools/y4mfmt.py"), src, str(tmp_src),
                        cfg["fmt"], str(cw), str(ch), str(x), str(y),
                        "--frames", str(cfg["frames"])], check=True)
        src = tmp_src
    strm = WORK / f"{tag}.{'obu' if cfg.get('obu') else 'ivf'}"
    t0 = time.time()
    rc, _, err = run(enc_cmd(cfg, src, strm), 1800)
    row = dict(id=tag, cfg=cfg, enc_rc=rc, enc_s=round(time.time() - t0, 1))
    if rc != 0:
        row["enc_err"] = err[-300:]
    else:
        res = decode_all(strm, cfg, rng, tag)
        v = verdict(res)
        row["verdict"] = v
        row["res"] = {k: [r[0], r[1]] for k, r in res.items()}
        if v is None:
            row["ref_err"] = res["ref"][2]
        if v:
            d = FAIL / tag
            d.mkdir(parents=True, exist_ok=True)
            shutil.copy(strm, d / f"stream{strm.suffix}")
            if tmp_src:
                shutil.copy(tmp_src, d / "src.y4m")
            (d / "info.json").write_text(json.dumps(
                dict(row, cmd=enc_cmd(cfg, d / "src.y4m" if tmp_src else src,
                                      d / f"stream{strm.suffix}"),
                     err={k: r[2] for k, r in res.items()}), indent=1))
    if row.get("verdict") == [] and strm.exists():
        KEEP.mkdir(exist_ok=True)
        strm.rename(KEEP / strm.name)  # passing streams, decoded on the pi later
    strm.unlink(missing_ok=True)
    if tmp_src:
        tmp_src.unlink(missing_ok=True)
    with lock:
        with open(results, "a") as f:
            f.write(json.dumps(row) + "\n")
        print(tag, row.get("verdict", f"enc {rc}"), cfg["src"], cfg["preset"],
              cfg["qp"], cfg["frames"], cfg.get("rc"), cfg["flags"], flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--n", type=int, default=0)
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--prefix", default="v")
    ap.add_argument("--stop-at", default=None)
    ap.add_argument("--results", default="results.jsonl")
    args = ap.parse_args()
    args.stop_dt = None
    if args.stop_at:
        h, m = map(int, args.stop_at.split(":"))
        now = dt.datetime.now()
        args.stop_dt = now.replace(hour=h, minute=m, second=0)
        if args.stop_dt <= now:
            args.stop_dt += dt.timedelta(days=1)
    WORK.mkdir(exist_ok=True)
    FAIL.mkdir(exist_ok=True)
    flags, gone = supported_flags()
    print("flags unknown to this avmenc (skipped):", gone, flush=True)
    srcs = sources()
    results = W / args.results
    done = sum(1 for _ in open(results)) if results.exists() else 0
    seed = args.seed if args.seed is not None else int(time.time())
    print("seed", seed, flush=True)
    pre = WORK / "preflight.y4m"
    any_src = next(v for v in srcs.values() if v["fmt"] == "420")["path"]
    subprocess.run([PY, "-I", str(W / "tools/y4mfmt.py"), any_src, str(pre), "420", "17", "9", "0", "0",
                    "--frames", "2"], check=True)
    for b in (ENC, AVMDEC, DAV, DAVASAN):
        assert Path(b).exists(), b
    pre.unlink()
    lock, counter = threading.Lock(), [done]
    ts = [threading.Thread(target=worker, args=(
        k, random.Random(seed * 100 + k), srcs, flags, args, lock, results,
        counter)) for k in range(args.workers)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()


if __name__ == "__main__":
    main()
