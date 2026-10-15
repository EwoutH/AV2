"""Sweep av2-enc --cpu-used presets: encode time, quality and resources per
(clip, QP, preset). Adapted from bench.py (build path fixed, one encode per
pinned P-core, --threads=1).

Per encode, recorded:
  wall, cpu (user+sys), peak working set     -- encode only, timed
  concurrency (mean busy encoders while it ran)
  PSNR Y/U/V/Avg/Overall                     -- avmenc summary (frame-mean)
  SSIM Y/U/V/All, VMAF mean                  -- ffmpeg on avmdec output
  file bytes, payload bytes (no IVF headers), per-frame times

Quality scoring runs after the encode timer stops, pinned to the E-cores,
so it does not compete with the encodes.

Scheduling: one queue in priority order (--plan night: PLAN below, slowest
jobs first within each entry). A rough cost model, corrected online from
finished jobs, orders the jobs and skips any job that would not finish
before --stop-at. Resumable: finished jobs in the results file are skipped.

Examples:
  python -I sweep.py --plan night --stop-at 07:00
  python -I sweep.py --clips FourPeople_480x270_60 --presets 6 9 --frames 2 \
      --results test.jsonl
"""
import argparse, ctypes, datetime as dt, json, math, re, subprocess
import tempfile, threading, time
import ctypes.wintypes as wt
from collections import defaultdict
from pathlib import Path

import psutil

HERE = Path(__file__).resolve().parent
SRC = HERE.parent / "sources"
BIN = HERE.parent / "avm_build_windows" / "Release"
ENC, DEC = BIN / "avmenc.exe", BIN / "avmdec.exe"
FFMPEG = Path("C:/Program Files/ffmpeg/ffmpeg.exe")
OUT = HERE / "sweep_out"
# i7-12700H: logical 0-11 are the 6 P-cores (2 threads each), 12-19 E-cores
# (checked with GetSystemCpuSetInformation). One encode per physical P-core.
P_CORES = [0, 2, 4, 6, 8, 10]
E_CORES = list(range(12, 20))
QPS = [110, 145, 180, 210]
PRESETS = list(range(10))

# Night plan in priority order: (clips, frames, presets), each x QPS.
# Low-res set first (the main result), then higher resolutions; whatever
# does not fit before --stop-at is skipped. HD runs without s0 (about half
# the cost) so it can afford enough frames that the keyframe does not
# dominate time and bits (at 17 f on 720p it was ~60% of time, ~80% of bits).
PLAN = [
    (["FourPeople_480x270_60", "BlueSky_360p25_v2",
      "Vertical_Bayshore_270x480_2997"], 33, PRESETS),
    (["KristenAndSara_1280x720_60"], 65, PRESETS[1:]),
    (["crowd_run_1080p50"], 33, PRESETS[1:]),
    (["old_town_cross_1080p50"], 33, PRESETS[1:]),  # filler
]
# Repeated after the first plan entry to measure timing drift (rep=1).
CANARY = [("FourPeople_480x270_60", 145, p, 33) for p in (1, 6, 9)]

# Rough cost model, s6 at QP 145 from the 14 Oct bench (keyframe ~100 s/MP,
# inter ~8 s/MP/frame), preset factors from the 3-frame calibration. Only
# used to order jobs and to skip ones that cannot finish in time; corrected
# per clip and per preset from finished jobs.
KEY_S_PER_MP, INTER_S_PER_MP = 100.0, 8.0
QP_F = {110: 1.4, 145: 1.0, 180: 0.75, 210: 0.55}
PRESET_F = {0: 23.1, 1: 8.9, 2: 2.7, 3: 2.5, 4: 2.0, 5: 1.65, 6: 1.0,
            7: 1.05, 8: 1.07, 9: 1.1}

PSNR_RE = re.compile(r"Summary:\s+([\d.]+)" + r"\s*\|\s*([\d.]+)" * 5)
# "POC:     0 [ KEY ]...:  10913 Bytes, 64654.9ms"
POC_RE = re.compile(r"POC:\s+\d+ \[\s*(\w+)\s*\].*?:\s+(\d+)\s+Bytes,"
                    r"\s+([\d.]+)ms")
SSIM_RE = re.compile(r"SSIM Y:([\d.]+).*?U:([\d.]+).*?V:([\d.]+)"
                     r".*?All:([\d.]+)")


# ---- sources ---------------------------------------------------------------
_info = {}


def src_info(clip, fps=False):
    """(width, height) from the y4m header, plus the frame rate ("60/1")
    with fps=True. Only 8-bit 4:2:0 is supported by the quality step, so
    anything else fails here, before the run."""
    if clip not in _info:
        with open(SRC / f"{clip}.y4m", "rb") as f:
            hdr = f.readline().decode().split()
        tok = {t[0]: t[1:] for t in hdr[1:]}
        cs = tok.get("C", "420")
        if not cs.startswith("420") or "p1" in cs:
            raise ValueError(f"{clip}: colourspace C{cs} not supported")
        _info[clip] = (int(tok["W"]), int(tok["H"]),
                       tok["F"].replace(":", "/"))
    w, h, f = _info[clip]
    return (w, h, f) if fps else (w, h)


_raw_lock = threading.Lock()


def src_raw(clip, frames):
    """First `frames` source frames as raw I420, cached in sweep_out/src/."""
    w, h = src_info(clip)
    fs = w * h * 3 // 2
    path = OUT / "src" / f"{clip}_{frames}f.yuv"
    with _raw_lock:
        if not path.exists():
            path.parent.mkdir(exist_ok=True)
            tmp = path.with_suffix(".part")
            with open(SRC / f"{clip}.y4m", "rb") as f, open(tmp, "wb") as o:
                f.readline()  # stream header
                for _ in range(frames):
                    if not f.readline().startswith(b"FRAME"):
                        raise ValueError(f"{clip}: fewer than {frames} frames")
                    o.write(f.read(fs))
            tmp.replace(path)
    return path


# ---- cost model ------------------------------------------------------------
def base_est(job):
    w, h = src_info(job["clip"])
    mp = w * h / 1e6
    return (mp * (KEY_S_PER_MP + INTER_S_PER_MP * (job["frames"] - 1))
            * QP_F.get(job["qp"], 1.0) * PRESET_F.get(job["preset"], 1.0))


class Model:
    """log(actual / base_est) = a[clip] + b[preset], fitted by means."""

    def __init__(self):
        self.res = []  # (clip, preset, log ratio)

    def add(self, job, wall):
        self.res.append((job["clip"], job["preset"],
                         math.log(wall / base_est(job))))

    def factor(self, job):
        if not self.res:
            return 1.0
        by_clip = defaultdict(list)
        for c, _, r in self.res:
            by_clip[c].append(r)
        a = {c: sum(v) / len(v) for c, v in by_clip.items()}
        glob = sum(r for _, _, r in self.res) / len(self.res)
        b = [r - a[c] for c, p, r in self.res if p == job["preset"]]
        return math.exp(a.get(job["clip"], glob)
                        + (sum(b) / len(b) if b else 0.0))

    def est(self, job):
        return base_est(job) * self.factor(job)


# ---- Windows process stats -------------------------------------------------
class _PMC(ctypes.Structure):
    _fields_ = [("cb", wt.DWORD), ("PageFaultCount", wt.DWORD)] + [
        (n, ctypes.c_size_t) for n in (
            "PeakWorkingSetSize", "WorkingSetSize", "QuotaPeakPagedPoolUsage",
            "QuotaPagedPoolUsage", "QuotaPeakNonPagedPoolUsage",
            "QuotaNonPagedPoolUsage", "PagefileUsage", "PeakPagefileUsage")]


_k32 = ctypes.WinDLL("kernel32")
_psapi = ctypes.WinDLL("psapi")
_k32.GetProcessTimes.argtypes = [wt.HANDLE] + [ctypes.POINTER(wt.FILETIME)] * 4
_psapi.GetProcessMemoryInfo.argtypes = [wt.HANDLE, ctypes.POINTER(_PMC),
                                        wt.DWORD]


def proc_stats(p):
    """CPU seconds (user+kernel) and peak working set of an exited Popen,
    read from its process handle (exact, no sampling)."""
    h = wt.HANDLE(int(p._handle))
    t = [wt.FILETIME() for _ in range(4)]
    _k32.GetProcessTimes(h, *map(ctypes.byref, t))
    sec = lambda f: ((f.dwHighDateTime << 32) | f.dwLowDateTime) / 1e7
    pmc = _PMC(cb=ctypes.sizeof(_PMC))
    _psapi.GetProcessMemoryInfo(h, ctypes.byref(pmc), pmc.cb)
    return sec(t[2]) + sec(t[3]), pmc.PeakWorkingSetSize


def pin(p, cpus):
    try:
        psutil.Process(p.pid).cpu_affinity(cpus)
    except psutil.Error:
        pass


def run_on(cmd, cpus, **kw):
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                         text=True, errors="replace", **kw)
    pin(p, cpus)
    out, err = p.communicate()
    return p.returncode, out, err


# ---- one job ---------------------------------------------------------------
def ivf_payload(path):
    """Sum of frame payload sizes (IVF: 32-byte file header, then a 12-byte
    header per frame) and the number of frames."""
    d = path.read_bytes()
    off, total, n = int.from_bytes(d[6:8], "little"), 0, 0
    while off + 12 <= len(d):
        sz = int.from_bytes(d[off:off + 4], "little")
        total, n, off = total + sz, n + 1, off + 12 + sz
    return total, n


def encode(job, cpu, ivf, log, busy):
    cmd = [str(ENC), str(SRC / f"{job['clip']}.y4m"), "-o", str(ivf), "--ivf",
           f"--limit={job['frames']}", "--end-usage=q", f"--qp={job['qp']}",
           f"--cpu-used={job['preset']}", "--threads=1", "--psnr=1"]
    conc = []
    t0 = time.perf_counter()
    with open(log, "w") as lf:
        p = subprocess.Popen(cmd, stdout=lf, stderr=subprocess.STDOUT)
        pin(p, [cpu])
        while True:
            try:
                p.wait(timeout=2)
                break
            except subprocess.TimeoutExpired:
                conc.append(busy())
    wall = time.perf_counter() - t0
    cpu_s, peak = proc_stats(p)
    out = Path(log).read_text(errors="replace")
    m = PSNR_RE.findall(out)
    poc = POC_RE.findall(out)
    return dict(rc=p.returncode, wall=round(wall, 2), cpu=round(cpu_s, 2),
                peak_mb=round(peak / 2**20, 1),
                conc=round(sum(conc) / len(conc), 2) if conc else None,
                # [Y, U, V, Avg, Overall]; per-plane values are frame means
                psnr=[float(x) for x in m[-1][1:]] if m else None,
                frame_ms=[(t, float(ms)) for t, _, ms in poc],
                frame_bytes=[(t, int(b)) for t, b, _ in poc])


def quality(job, ivf, tmp):
    """Decode with avmdec, score against the source with ffmpeg (SSIM, VMAF).
    Everything single-threaded on the E-cores."""
    w, h, fps = src_info(job["clip"], fps=True)
    dec = tmp / "dec.yuv"
    rc, _, _ = run_on([str(DEC), str(ivf), "--rawvideo", "-o", str(dec)],
                      E_CORES)
    if rc or not dec.exists() or dec.stat().st_size == 0:
        return dict(dec_rc=rc, ssim=None, vmaf=None)
    n_dec = dec.stat().st_size // (w * h * 3 // 2)
    # Both inputs raw with identical parameters. With the y4m source,
    # ffmpeg paired frames differently from run to run (29.97 fps clip),
    # even with frame-index timestamps; raw vs raw is deterministic.
    raw = ["-f", "rawvideo", "-pix_fmt", "yuv420p", "-video_size",
           f"{w}x{h}", "-framerate", fps, "-i"]
    inputs = raw + [str(dec)] + raw + [str(src_raw(job["clip"],
                                                   job["frames"]))]
    ff = [str(FFMPEG), "-hide_banner", "-nostats", "-filter_threads", "1"]
    # Run from the temp dir with relative log names: a drive letter's colon
    # would end a filter option early.
    # SSIM, then per-frame PSNR on the same pair as an alignment check
    # against avmenc's PSNR (ssim passes its first input through).
    _, _, err = run_on(ff + inputs + [
        "-lavfi", "[1:v]split[r1][r2];[0:v][r1]ssim[d];"
        "[d][r2]psnr=stats_file=psnr.log", "-f", "null", "-"], E_CORES,
        cwd=tmp)
    sm = SSIM_RE.findall(err)
    plog = tmp / "psnr.log"
    fy = re.findall(r"psnr_y:([\d.]+|inf)", plog.read_text()) \
        if plog.exists() else []
    fy = [float(x) for x in fy if x != "inf"]
    # VMAF: libvmaf writes a JSON log with the pooled mean.
    rc, _, _ = run_on(ff + inputs + [
        "-lavfi", "[0:v][1:v]libvmaf=n_threads=1:log_fmt=json:"
        "log_path=vmaf.json", "-f", "null", "-"], E_CORES, cwd=tmp)
    vlog = tmp / "vmaf.json"
    vmaf = (json.loads(vlog.read_text())["pooled_metrics"]["vmaf"]["mean"]
            if rc == 0 and vlog.exists() else None)
    dec.unlink(missing_ok=True)
    return dict(dec_rc=0, dec_frames=n_dec,
                ssim=[float(x) for x in sm[-1]] if sm else None,
                # frame-mean PSNR-Y, same definition as avmenc's
                ff_psnr_y=sum(fy) / len(fy) if fy else None, vmaf=vmaf)


def tag(job):
    return (f"{job['clip']}_qp{job['qp']}_s{job['preset']}_{job['frames']}f"
            + (f"_rep{job['rep']}" if job["rep"] else ""))


def run_job(job, cpu, busy):
    ivf, log = OUT / f"{tag(job)}.ivf", OUT / f"{tag(job)}.log"
    w, h = src_info(job["clip"])
    res = dict(job, w=w, h=h, **encode(job, cpu, ivf, log, busy))
    if res["rc"] or not res["psnr"]:
        return dict(res, bytes=None, payload=None, quality=None)
    payload, npk = ivf_payload(ivf)
    with tempfile.TemporaryDirectory(dir=OUT) as td:
        q = quality(job, ivf, Path(td))
    log.unlink(missing_ok=True)  # logs are kept only for failures
    return dict(res, bytes=ivf.stat().st_size, payload=payload, packets=npk,
                quality=q)


# ---- planning --------------------------------------------------------------
def key(j):
    return (j["clip"], j["qp"], j["preset"], j["frames"], j["rep"])


def complete(r):
    q = r.get("quality") or {}
    return r["rc"] == 0 and q.get("ssim") and q.get("vmaf") is not None


def build_jobs(a):
    mk = lambda c, q, p, f, rep=0: dict(clip=c, qp=q, preset=p, frames=f,
                                        rep=rep)
    if a.plan == "night":
        entries = [[mk(c, q, p, f) for c in cs for q in QPS for p in ps]
                   for cs, f, ps in PLAN]
        # Canary: same encodes again, right after the first entry.
        entries.insert(1, [mk(c, q, p, f, 1) for c, q, p, f in CANARY])
    else:
        entries = [[mk(c, q, p, a.frames) for c in a.clips for q in a.qps
                    for p in a.presets]]
    jobs = []
    for e in entries:  # slowest first within each entry
        jobs += sorted(e, key=base_est, reverse=True)
    for j in jobs:
        src_info(j["clip"])  # fail now on unsupported or missing sources
    return jobs


def next_stop(hhmm):
    h, m = map(int, hhmm.split(":"))
    now = dt.datetime.now()
    t = now.replace(hour=h, minute=m, second=0, microsecond=0)
    return (t if t > now else t + dt.timedelta(days=1)).timestamp()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", choices=["night"])
    ap.add_argument("--clips", nargs="+")
    ap.add_argument("--presets", nargs="+", type=int, default=PRESETS)
    ap.add_argument("--qps", nargs="+", type=int, default=QPS)
    ap.add_argument("--frames", type=int)
    ap.add_argument("--results", default="sweep.jsonl")
    ap.add_argument("--stop-at", help="HH:MM local; jobs that would not "
                    "finish by then (by the cost model) are skipped")
    ap.add_argument("--dry-run", action="store_true",
                    help="print the plan and its estimated cost, then exit")
    a = ap.parse_args()
    if not a.plan and not (a.clips and a.frames):
        ap.error("give --plan night, or --clips and --frames")
    OUT.mkdir(exist_ok=True)
    results = HERE / a.results
    stop = next_stop(a.stop_at) if a.stop_at else None

    model, done = Model(), set()
    if results.exists():
        for line in results.read_text().splitlines():
            try:
                r = json.loads(line)
            except ValueError:  # half-written line after a crash
                continue
            if complete(r):
                done.add(key(r))
                if not r["rep"]:
                    model.add(r, r["wall"])
    jobs = [j for j in build_jobs(a) if key(j) not in done]
    total = len(jobs)
    est = sum(model.est(j) for j in jobs)
    print(f"{total} jobs to run ({len(done)} already done); cost model: "
          f"{est / 3600:.1f} CPU-h, ~{est / len(P_CORES) / 3600:.1f} h on "
          f"{len(P_CORES)} cores" + (f"; stop at "
          f"{dt.datetime.fromtimestamp(stop):%a %H:%M}" if stop else ""),
          flush=True)
    if a.dry_run:
        per = defaultdict(float)
        for j in jobs:
            per[(j["clip"], j["frames"], j["rep"])] += model.est(j)
        for (c, f, rep), s in per.items():
            print(f"  {c} {f}f{' rep' if rep else ''}: {s / 3600:.1f} CPU-h")
        longest = max(jobs, key=model.est)
        print(f"  longest job: {tag(longest)} {model.est(longest) / 3600:.1f} h")
        return

    lock = threading.Lock()
    state = dict(n=0, busy=0)
    busy = lambda: state["busy"]

    def take():
        """Next job in priority order that fits before the stop time."""
        with lock:
            for i, j in enumerate(jobs):
                e = model.est(j)
                if stop is None or time.time() + 1.15 * e < stop:
                    state["busy"] += 1
                    return jobs.pop(i), e
        return None, None

    def worker(cpu):
        while True:
            job, e = take()
            if job is None:
                return
            r = run_job(job, cpu, busy)
            with lock:
                state["busy"] -= 1
                state["n"] += 1
                if complete(r) and not r["rep"]:
                    model.add(r, r["wall"])
                with open(results, "a") as f:
                    f.write(json.dumps(r) + "\n")
                q = r["quality"] or {}
                print(f"{time.strftime('%H:%M')} [{state['n']}/{total}] "
                      f"{tag(job)}: {r['wall']:.0f}s (est {e:.0f}) "
                      f"{r['payload']} B psnr_y={r['psnr'] and r['psnr'][0]}"
                      f" ssim_y={q.get('ssim') and q['ssim'][0]} "
                      f"vmaf={q.get('vmaf') and round(q['vmaf'], 2)} "
                      f"peak={r['peak_mb']:.0f}MB rc={r['rc']}", flush=True)

    ts = [threading.Thread(target=worker, args=(c,)) for c in P_CORES]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    left = defaultdict(int)
    for j in jobs:
        left[j["clip"]] += 1
    print("SWEEP DONE" + (f"; skipped (would not finish by stop time): "
                          f"{dict(left)}" if left else ""), flush=True)


if __name__ == "__main__":
    main()
