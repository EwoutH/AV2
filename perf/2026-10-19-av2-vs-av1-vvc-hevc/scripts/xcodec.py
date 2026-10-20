"""AV2 (AVM) vs AV1, VVC, HEVC and AVC encoders on the same source frames.

Every encode is single-threaded and pinned to its own physical P-core (as in
sweep.py, so AVM times from sweep.jsonl are comparable). Bitstreams are
decoded and scored raw-vs-raw with ffmpeg on the E-cores, in a separate pool,
with the same commands as sweep.quality (SSIM, per-frame PSNR, VMAF).

Encoders (all through ffmpeg, except AVM):
  aom   libaom-av1 --end-usage=q (crf), good quality, cpu-used 0/1/3/6
  svt   SVT-AV1 crf, presets 0/2/5/8, tune PSNR
  vvenc VVenC fixed QP, presets slower/medium/faster, QPA off, 10-bit
        internal (its only input format); output rounded to 8 bit here
  x265  crf, placebo/veryslow/medium, tune psnr
  x264  crf, veryslow/medium, tune psnr
  avm   avmenc (av2-enc 89eae123d) fixed QP, via sweep.py
All: one keyframe (keyframe interval above the clip length), no scene cuts,
default GOP structure (random access) of each encoder, 8-bit 4:2:0 output.

Modes:
  --calib    fastest preset of each codec on the sweep clips over a wide
             parameter grid, to map AVM QP to each codec's parameter
  --timing   each config once on FourPeople, for the cost model
  (default)  the comparison plan; --dry-run prints it with estimates
"""
import argparse, datetime as dt, json, queue, subprocess, sys, tempfile
import threading, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import sweep as sw  # noqa: E402

OUT = HERE / "xcodec_out"
FF = [str(sw.FFMPEG), "-hide_banner", "-nostats", "-y"]

LOWRES = ["FourPeople_480x270_60", "BlueSky_360p25_v2",
          "Vertical_Bayshore_270x480_2997"]
HD720 = ["KristenAndSara_1280x720_60"]
HD1080 = ["crowd_run_1080p50", "Motorcycle_1920x1080_30fps_8bit",
          "GlassHalf_1920x1080p_24p_8bit_420",
          "EuroTruckSimulator2_1920x1080p60",
          "Debugging_1920x1080_30fps_8bit_420"]
FRAMES = {**{c: 33 for c in LOWRES + HD1080}, **{c: 65 for c in HD720}}

# (codec, preset) configs, slowest first within a codec.
CONFIGS = {
    "aom": [0, 1, 3, 6],
    "svt": [0, 2, 5, 8],
    "vvenc": [4, 2, 0],          # slower, medium, faster
    "x265": ["placebo", "veryslow", "medium"],
    "x264": ["veryslow", "medium"],
}
FASTEST = {c: p[-1] for c, p in CONFIGS.items()}
AVM_QPS = [110, 145, 180, 210]

# Parameter grids, filled in from --calib (see GRID_NOTE in the write-up):
# seven points per codec spanning about AVM QP 105-215 on the calibration
# clips (AV1 tops out at 63, which is above AVM QP 210 in quality).
GRID = {
    "aom": [20, 28, 36, 44, 52, 58, 63],
    "svt": [20, 28, 36, 44, 52, 58, 63],
    "vvenc": [19, 23, 27, 31, 35, 39, 43],
    "x265": [14, 18, 22, 26, 30, 34, 38],
    "x264": [15, 19, 23, 27, 31, 35, 39],
}


def enc_args(codec, preset, q):
    """ffmpeg output options and file suffix for one encode."""
    if codec == "aom":
        return ["-c:v", "libaom-av1", "-usage", "good", "-cpu-used",
                str(preset), "-crf", str(q), "-b:v", "0", "-g", "9999",
                "-row-mt", "0", "-tiles", "1x1", "-f", "ivf"], ".ivf"
    if codec == "svt":
        return ["-c:v", "libsvtav1", "-preset", str(preset), "-crf", str(q),
                "-g", "9999", "-svtav1-params", "lp=1:tune=1:scd=0",
                "-f", "ivf"], ".ivf"
    if codec == "vvenc":
        return ["-c:v", "libvvenc", "-preset", str(preset), "-qp", str(q),
                "-pix_fmt", "yuv420p10le",
                "-vvenc-params", "qpa=0:intraperiod=1024", "-f", "rawvideo"
                ], ".266"
    if codec == "x265":
        return ["-c:v", "libx265", "-preset", preset, "-tune", "psnr",
                "-crf", str(q), "-x265-params",
                "keyint=9999:min-keyint=9999:scenecut=0:frame-threads=1:"
                "pools=1", "-f", "hevc"], ".hevc"
    if codec == "x264":
        return ["-c:v", "libx264", "-preset", preset, "-tune", "psnr",
                "-crf", str(q), "-g", "9999", "-sc_threshold", "0",
                "-f", "h264"], ".h264"
    raise ValueError(codec)


def tag(j):
    return f"{j['clip']}_{j['codec']}_p{j['preset']}_q{j['q']}_{j['frames']}f"


def raw_in(clip, frames):
    w, h, fps = sw.src_info(clip, fps=True)
    return ["-f", "rawvideo", "-pix_fmt", "yuv420p", "-video_size",
            f"{w}x{h}", "-framerate", fps, "-i",
            str(sw.src_raw(clip, frames))]


# ---- encode ----------------------------------------------------------------
def encode_ff(j, cpu):
    args, ext = enc_args(j["codec"], j["preset"], j["q"])
    out = OUT / (tag(j) + ext)
    log = OUT / (tag(j) + ".log")
    cmd = FF + ["-loglevel", "verbose", "-filter_threads", "1"] + \
        raw_in(j["clip"], j["frames"]) + ["-threads", "1"] + args + [str(out)]
    t0 = time.perf_counter()
    with open(log, "w") as lf:
        p = subprocess.Popen(cmd, stdout=lf, stderr=subprocess.STDOUT)
        sw.pin(p, [cpu])
        p.wait()
    wall = time.perf_counter() - t0
    cpu_s, peak = sw.proc_stats(p)
    res = dict(rc=p.returncode, wall=round(wall, 2), cpu=round(cpu_s, 2),
               peak_mb=round(peak / 2**20, 1))
    if p.returncode or not out.exists():
        return res, None
    payload = sw.ivf_payload(out)[0] if ext == ".ivf" else out.stat().st_size
    log.unlink(missing_ok=True)
    return dict(res, bytes=out.stat().st_size, payload=payload), out


def recover_avm(ivf, log):
    """An AVM encode that finished but was not recorded (the 20 Oct run lost
    two to a bug in this script): rebuild its result from the avmenc log.
    Wall time = log creation to last write; CPU and peak memory unknown."""
    if not (ivf.exists() and log.exists()):
        return None
    out = log.read_text(errors="replace")
    m = sw.PSNR_RE.findall(out)
    if not m:
        return None
    st = log.stat()
    poc = sw.POC_RE.findall(out)
    wall = st.st_mtime - st.st_birthtime
    return dict(rc=0, wall=round(wall, 2), cpu=None, peak_mb=None,
                psnr=[float(x) for x in m[-1][1:]],
                frame_ms=[(t, float(ms)) for t, _, ms in poc],
                frame_bytes=[(t, int(b)) for t, b, _ in poc], recovered=True)


def encode_avm(j, cpu):
    sj = dict(clip=j["clip"], qp=j["q"], preset=j["preset"],
              frames=j["frames"], rep=0)
    ivf, log = sw.OUT / f"{sw.tag(sj)}.ivf", sw.OUT / f"{sw.tag(sj)}.log"
    r = recover_avm(ivf, log) or sw.encode(sj, cpu, ivf, log, lambda: 0)
    res = dict(rc=r["rc"], wall=r["wall"], cpu=r["cpu"], peak_mb=r["peak_mb"],
               psnr_avmenc=r["psnr"], frame_bytes=r["frame_bytes"],
               **({"recovered": True} if r.get("recovered") else {}))
    if r["rc"] or not r["psnr"]:
        return res, None
    log.unlink(missing_ok=True)
    return dict(res, bytes=ivf.stat().st_size,
                payload=sw.ivf_payload(ivf)[0]), ivf


# ---- score -----------------------------------------------------------------
def decode(j, bs, tmp):
    """Decoded 8-bit I420 file. AVM: avmdec. Others: ffmpeg; VVenC's 10-bit
    output is rounded to 8 bit here ((x + 2) >> 2), not by swscale, which
    could dither."""
    dec = tmp / "dec.yuv"
    if j["codec"] == "avm":
        rc, _, _ = sw.run_on([str(sw.DEC), str(bs), "--rawvideo", "-o",
                              str(dec)], sw.E_CORES)
        return dec if rc == 0 else None
    tenbit = j["codec"] == "vvenc"
    raw = tmp / ("dec10.yuv" if tenbit else "dec.yuv")
    rc, _, _ = sw.run_on(FF + ["-loglevel", "error", "-i", str(bs), "-f",
                               "rawvideo", "-pix_fmt",
                               "yuv420p10le" if tenbit else "yuv420p",
                               str(raw)], sw.E_CORES)
    if rc or not raw.exists():
        return None
    if tenbit:
        x = np.fromfile(raw, dtype="<u2")
        ((x.astype(np.uint32) + 2) >> 2).clip(0, 255).astype(
            np.uint8).tofile(dec)
        raw.unlink()
    return dec


def score(j, bs):
    w, h, fps = sw.src_info(j["clip"], fps=True)
    with tempfile.TemporaryDirectory(dir=OUT) as td:
        tmp = Path(td)
        dec = decode(j, bs, tmp)
        if dec is None or not dec.exists():
            return dict(dec_ok=False)
        n_dec = dec.stat().st_size // (w * h * 3 // 2)
        raw = ["-f", "rawvideo", "-pix_fmt", "yuv420p", "-video_size",
               f"{w}x{h}", "-framerate", fps, "-i"]
        inputs = raw + [str(dec)] + raw + [str(sw.src_raw(j["clip"],
                                                          j["frames"]))]
        ff = [str(sw.FFMPEG), "-hide_banner", "-nostats", "-filter_threads",
              "1"]
        _, _, err = sw.run_on(ff + inputs + [
            "-lavfi", "[1:v]split[r1][r2];[0:v][r1]ssim[d];"
            "[d][r2]psnr=stats_file=psnr.log", "-f", "null", "-"],
            sw.E_CORES, cwd=tmp)
        sm = sw.SSIM_RE.findall(err)
        planes = {"y": [], "u": [], "v": []}
        plog = tmp / "psnr.log"
        if plog.exists():
            for line in plog.read_text().splitlines():
                kv = dict(t.split(":", 1) for t in line.split() if ":" in t)
                for p in planes:
                    v = kv.get(f"psnr_{p}")
                    if v and v != "inf":
                        planes[p].append(float(v))
        rc, _, _ = sw.run_on(ff + inputs + [
            "-lavfi", "[0:v][1:v]libvmaf=n_threads=1:log_fmt=json:"
            "log_path=vmaf.json", "-f", "null", "-"], sw.E_CORES, cwd=tmp)
        vlog = tmp / "vmaf.json"
        vmaf = (json.loads(vlog.read_text())["pooled_metrics"]["vmaf"]["mean"]
                if rc == 0 and vlog.exists() else None)
    # frame-mean PSNR per plane, as avmenc reports it
    psnr = [sum(v) / len(v) if v else None for v in planes.values()]
    return dict(dec_ok=True, dec_frames=n_dec, psnr=psnr,
                ssim=[float(x) for x in sm[-1]] if sm else None, vmaf=vmaf)


# ---- plan ------------------------------------------------------------------
def job(clip, codec, preset, q):
    return dict(clip=clip, frames=FRAMES[clip], codec=codec, preset=preset,
                q=q)


def key(j):
    return (j["clip"], j["frames"], j["codec"], str(j["preset"]), j["q"])


def plan_calib():
    wide = {"aom": [12, 20, 28, 36, 44, 52, 60],
            "svt": [12, 20, 28, 36, 44, 52, 60],
            "vvenc": [17, 22, 27, 32, 37, 42, 47, 52],
            "x265": [13, 18, 23, 28, 33, 38, 43, 48],
            "x264": [13, 18, 23, 28, 33, 38, 43, 48]}
    return [job(c, k, FASTEST[k], q) for c in LOWRES + HD720
            for k in CONFIGS for q in wide[k]]


def plan_timing():
    mid = {"aom": 32, "svt": 32, "vvenc": 32, "x265": 28, "x264": 28}
    return [job("FourPeople_480x270_60", k, p, mid[k])
            for k in CONFIGS for p in CONFIGS[k]]


def plan_main():
    """Priority order. 1: every other codec on the sweep clips (AVM data
    exists for s0/s1-s9). 2: 1080p clips, AVM s6 and all others. 3: AVM s3
    on 1080p (s1 would be ~4 h per encode)."""
    jobs = [job(c, k, p, q) for c in LOWRES + HD720 for k in CONFIGS
            for p in CONFIGS[k] for q in GRID[k]]
    # 1080p (20 Oct, after measuring): libaom cpu-used 0, VVenC slower and
    # x265 placebo take 30-70 min per 1080p encode, so they run on crowd_run
    # only, and AVM s3 on two clips. Without the highest-quality grid point
    # (the slowest; above AVM QP 110 in quality on these clips).
    slow = {("aom", 0), ("vvenc", 4), ("x265", "placebo")}
    for c in HD1080:
        jobs += [job(c, "avm", 6, q) for q in AVM_QPS]
        jobs += [job(c, k, p, q) for k in CONFIGS for p in CONFIGS[k]
                 if (k, p) not in slow for q in GRID[k][1:]]
    jobs += [job("crowd_run_1080p50", k, p, q) for k, p in sorted(slow, key=str)
             for q in GRID[k][1:]]
    jobs += [job(c, "avm", 3, q) for c in HD1080[:2] for q in AVM_QPS]
    return jobs


def avm_done():
    """AVM results already in sweep.jsonl, keyed like ours."""
    done = set()
    for line in open(HERE / "sweep.jsonl"):
        r = json.loads(line)
        if r["rep"] == 0 and sw.complete(r):
            done.add((r["clip"], r["frames"], "avm", str(r["preset"]),
                      r["qp"]))
    return done


# Cost model: seconds per megapixel-frame per config at QP-mid, from
# --timing on FourPeople (filled in after the timing run; AVM from the sweep).
SPMF = {}


def est(j):
    w, h = sw.src_info(j["clip"])
    mpf = w * h / 1e6 * j["frames"]
    s = SPMF.get((j["codec"], str(j["preset"])), 10.0)
    return s * mpf


# ---- run -------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--calib", action="store_true")
    ap.add_argument("--timing", action="store_true")
    ap.add_argument("--results", default=None)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--stop-at", help="HH:MM: start no job that would not "
                    "finish by then (by the cost model)")
    ap.add_argument("--scorers", type=int, default=4)
    a = ap.parse_args()

    mode = "calib" if a.calib else "timing" if a.timing else "main"
    res_path = Path(a.results or HERE / f"xcodec_{mode}.jsonl")
    jobs = {"calib": plan_calib, "timing": plan_timing,
            "main": plan_main}[mode]()
    if mode == "main" and (HERE / "xcodec_spmf.json").exists():
        SPMF.update({tuple(k.split("|")): v for k, v in json.loads(
            (HERE / "xcodec_spmf.json").read_text()).items()})
    done = avm_done()
    if res_path.exists():
        done |= {key(r) for r in map(json.loads, open(res_path))
                 if r.get("vmaf") is not None}
    todo = [j for j in jobs if key(j) not in done]
    total = sum(map(est, todo))
    print(f"{mode}: {len(jobs)} jobs, {len(jobs) - len(todo)} done, "
          f"{len(todo)} to run, ~{total / 3600:.1f} CPU-h, "
          f"~{total / len(sw.P_CORES) / 3600:.1f} h on "
          f"{len(sw.P_CORES)} cores", flush=True)
    if a.dry_run:
        for j in todo:
            print(f"  {tag(j):70s} ~{est(j) / 60:7.1f} min")
        return

    stop = sw.next_stop(a.stop_at) if a.stop_at else None
    OUT.mkdir(exist_ok=True)
    q, lock = queue.Queue(), threading.Lock()
    for j in todo:
        q.put(j)
    pool = ThreadPoolExecutor(a.scorers)
    pending = []

    def finish(j, res, bs):
        try:
            sc = score(j, bs) if bs else {}
        except Exception as e:  # keep the run going; record the failure
            sc = dict(score_error=repr(e))
        row = dict(j, **res, **sc, w=sw.src_info(j["clip"])[0],
                   h=sw.src_info(j["clip"])[1],
                   t=dt.datetime.now().isoformat(timespec="seconds"))
        if j["codec"] == "avm" and res.get("psnr_avmenc"):
            row["psnr"] = res["psnr_avmenc"][:3]
        with lock:
            with open(res_path, "a") as f:
                f.write(json.dumps(row) + "\n")
        v = row.get("vmaf")
        print(f"[{dt.datetime.now():%H:%M:%S}] {tag(j)} rc={res['rc']} "
              f"{res['wall']:.0f}s {res.get('payload')}B psnr_y="
              f"{row.get('psnr') and round(row['psnr'][0], 2)} "
              f"vmaf={v and round(v, 2)} frames={row.get('dec_frames')}",
              flush=True)

    def worker(cpu):
        while True:
            try:
                j = q.get_nowait()
            except queue.Empty:
                return
            if stop and time.time() + est(j) > stop:
                print(f"skip (stop-at): {tag(j)}", flush=True)
                continue
            enc = encode_avm if j["codec"] == "avm" else encode_ff
            res, bs = enc(j, cpu)
            with lock:
                pending.append(pool.submit(finish, j, res, bs))

    ts = [threading.Thread(target=worker, args=(c,)) for c in sw.P_CORES]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    for f in pending:
        f.result()
    pool.shutdown()
    print(f"[{dt.datetime.now():%H:%M:%S}] all done", flush=True)


if __name__ == "__main__":
    main()
