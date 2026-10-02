#!/usr/bin/env python3
"""
End-to-end AV2 test-video generator (parallel pipeline).

Everything overlaps:
  * AVM (AV2 reference software) is cloned and built while sources download
  * Sources download concurrently, smallest first
  * Each clip's encodes start as soon as that clip has downloaded and the
    build has finished; they don't wait for other (larger) downloads
  * Encodes run in a worker pool; each one is decoded and MD5-checked

Requirements: git, cmake, a C/C++ compiler, python3 (3.9+), internet access.
Usage:
    python3 av2_encode.py                       # all clips (CIF + 720p + 1080p)
    python3 av2_encode.py --set 1080p --frames 120 --extra-args "--cpu-used=6"
    python3 av2_encode.py --encode-jobs 4 --download-jobs 2
"""
import argparse
import hashlib
import os
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

AVM_REPO = "https://github.com/AOMediaCodec/avm.git"
XIPH_BASE = "https://media.xiph.org/video/derf/y4m/"

CLIP_SETS = {
    # 352x288, a few MB each: fast to encode, good for smoke tests
    "cif": ["akiyo_cif", "foreman_cif", "news_cif"],
    # 1280x720 50fps, ~700 MB each source
    "720p": ["720p50_parkrun_ter", "720p50_shields_ter", "720p50_mobcal_ter"],
    # 1920x1080 50fps, ~1.5 GB each source. Varied content for decoder
    # benchmarking: heavy motion/detail (crowd_run, park_joy),
    # water/texture (ducks_take_off), and calmer scenes (old_town_cross).
    "1080p": ["crowd_run_1080p50", "park_joy_1080p50",
              "ducks_take_off_1080p50", "old_town_cross_1080p50"],
}
CLIP_SETS["hd"] = CLIP_SETS["720p"] + CLIP_SETS["1080p"]
CLIP_SETS["all"] = CLIP_SETS["cif"] + CLIP_SETS["hd"]

_print_lock = threading.Lock()


def log(msg: str):
    with _print_lock:
        print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def run(cmd, logfile: Path, cwd=None):
    """Run a command, sending its output to a log file so parallel jobs
    don't interleave on the console."""
    with open(logfile, "a") as f:
        f.write("+ " + " ".join(str(c) for c in cmd) + "\n")
        f.flush()
        r = subprocess.run([str(c) for c in cmd], cwd=cwd,
                           stdout=f, stderr=subprocess.STDOUT)
    if r.returncode != 0:
        raise RuntimeError(f"{Path(str(cmd[0])).name} failed "
                           f"(exit {r.returncode}); see {logfile}")


WIN_HINTS = {
    "git": "winget install Git.Git",
    "cmake": "winget install Kitware.CMake",
    "perl": "winget install StrawberryPerl.StrawberryPerl",
    "nasm": "winget install NASM.NASM",
}


def check_tools():
    # perl generates source files during the build; nasm assembles the
    # x86 SIMD code (without it the encoder is far slower).
    missing = [t for t in ("git", "cmake", "perl", "nasm")
               if shutil.which(t) is None]
    if missing:
        msg = f"Missing required tools: {', '.join(missing)}"
        if os.name == "nt":
            msg += "\nInstall with:\n" + "\n".join(
                f"  {WIN_HINTS[t]}" for t in missing)
            msg += "\nthen open a NEW terminal so PATH updates."
        sys.exit(msg)


# --------------------------------------------------------------------------
# Build
# --------------------------------------------------------------------------
def build_avm(work: Path, ref, jobs: int, logs: Path):
    src, build = work / "avm", work / "avm_build"
    blog = logs / "build.log"
    log(f"Building AVM (log: {blog})")
    if not src.exists():
        if ref is None:
            run(["git", "clone", "--depth", "1", AVM_REPO, src], blog)
        else:
            run(["git", "clone", AVM_REPO, src], blog)
            run(["git", "checkout", ref], blog, cwd=src)
    build.mkdir(exist_ok=True)
    run(["cmake", src, "-DCMAKE_BUILD_TYPE=Release",
         "-DENABLE_TESTS=0", "-DENABLE_DOCS=0"], blog, cwd=build)
    # --config is needed for Visual Studio (multi-config) generators and is
    # ignored by single-config ones like Makefiles/Ninja.
    run(["cmake", "--build", ".", "--config", "Release", "-j", str(jobs)],
        blog, cwd=build)

    # Binary names have varied between AVM versions, and Visual Studio puts
    # them in a Release\ subfolder with an .exe suffix.
    exe = ".exe" if os.name == "nt" else ""

    def find(names):
        for n in names:
            for d in (build, build / "Release"):
                if (d / (n + exe)).exists():
                    return d / (n + exe)
        raise RuntimeError(f"None of {names} found in {build}")

    enc, dec = find(["avmenc", "aomenc"]), find(["avmdec", "aomdec"])
    log(f"Build finished: {enc.name}, {dec.name}")
    return enc, dec


# --------------------------------------------------------------------------
# Download
# --------------------------------------------------------------------------
def download(clip: str, dest_dir: Path) -> Path:
    out = dest_dir / f"{clip}.y4m"
    if out.exists():
        log(f"Already have {out.name}")
        return out
    url = f"{XIPH_BASE}{clip}.y4m"
    tmp = out.with_suffix(".part")
    log(f"Downloading {clip}")
    t0 = time.time()
    with urllib.request.urlopen(url) as r, open(tmp, "wb") as f:
        shutil.copyfileobj(r, f, length=1 << 20)
    tmp.rename(out)
    mb = out.stat().st_size / 1e6
    log(f"Downloaded {clip} ({mb:.0f} MB in {time.time() - t0:.0f}s)")
    return out


# --------------------------------------------------------------------------
# Encode + verify
# --------------------------------------------------------------------------
def encode_job(enc, dec, src: Path, ivf: Path, frames: int, qp: int,
               extra: list, logs: Path):
    jlog = logs / f"{ivf.stem}.log"
    if ivf.exists():
        log(f"Skipping encode, {ivf.name} exists")
    else:
        log(f"Encoding {ivf.name}")
        t0 = time.time()
        tmp = ivf.with_suffix(".ivf.part")
        run([enc, src, "-o", tmp, f"--limit={frames}",
             "--end-usage=q", f"--qp={qp}", *extra], jlog)
        tmp.rename(ivf)
        log(f"Encoded {ivf.name} in {time.time() - t0:.0f}s")

    # Decode with the reference decoder and hash the output, giving a
    # known-good checksum to compare dav2d against later.
    yuv = ivf.with_suffix(".yuv")
    run([dec, ivf, "--rawvideo", "-o", yuv], jlog)
    h = hashlib.md5()
    with open(yuv, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    yuv.unlink()  # raw output is large; keep only the hash
    return ivf.name, ivf.stat().st_size, h.hexdigest()


# --------------------------------------------------------------------------
# Main pipeline
# --------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--workdir", default="av2_work")
    ap.add_argument("--set", choices=sorted(CLIP_SETS), default="all",
                    help="Predefined clip set (ignored if --clips is given)")
    ap.add_argument("--clips", nargs="+", default=None,
                    help="Explicit Xiph derf clip names (without .y4m)")
    ap.add_argument("--frames", type=int, default=60)
    ap.add_argument("--qp", type=int, nargs="+", default=[85, 135, 185],
                    help="Quantizer values (0-255 scale)")
    ap.add_argument("--avm-ref", default=None, help="AVM tag/commit to build")
    ap.add_argument("--build-jobs", type=int, default=os.cpu_count() or 4)
    ap.add_argument("--download-jobs", type=int, default=3)
    ap.add_argument("--encode-jobs", type=int, default=os.cpu_count() or 4,
                    help="Concurrent encoder processes")
    ap.add_argument("--extra-args", default="",
                    help="Extra encoder flags, quoted as one string")
    args = ap.parse_args()

    check_tools()
    work = Path(args.workdir).resolve()
    sources, out_dir, logs = work / "sources", work / "encoded", work / "logs"
    for d in (work, sources, out_dir, logs):
        d.mkdir(exist_ok=True)
    clips = args.clips or CLIP_SETS[args.set]
    extra = args.extra_args.split()

    results, errors = [], []
    with ThreadPoolExecutor(1) as build_pool, \
         ThreadPoolExecutor(args.download_jobs) as dl_pool, \
         ThreadPoolExecutor(args.encode_jobs) as enc_pool:

        # Kick off the build and all downloads at once. Clips are submitted
        # in list order (small first), so small sources arrive early.
        build_fut = build_pool.submit(build_avm, work, args.avm_ref,
                                      args.build_jobs, logs)
        dl_futs = {dl_pool.submit(download, c, sources): c for c in clips}

        try:
            enc, dec = build_fut.result()
        except Exception as e:
            dl_pool.shutdown(cancel_futures=True)
            sys.exit(f"Build failed: {e}")

        # As each download completes, queue that clip's encodes right away.
        enc_futs = []
        for fut in as_completed(dl_futs):
            clip = dl_futs[fut]
            try:
                src = fut.result()
            except Exception as e:
                errors.append(f"download {clip}: {e}")
                log(f"ERROR downloading {clip}: {e}")
                continue
            for qp in args.qp:
                ivf = out_dir / f"{clip}_qp{qp}_{args.frames}f.ivf"
                enc_futs.append(enc_pool.submit(
                    encode_job, enc, dec, src, ivf, args.frames, qp, extra, logs))

        for fut in as_completed(enc_futs):
            try:
                results.append(fut.result())
            except Exception as e:
                errors.append(str(e))
                log(f"ERROR: {e}")

    results.sort()
    manifest = out_dir / "manifest.txt"
    with open(manifest, "w") as f:
        for name, size, md5 in results:
            f.write(f"{name}\t{size}\t{md5}\n")

    print("\nEncoded streams:")
    for name, size, md5 in results:
        print(f"  {name:45s} {size / 1024:9.1f} KiB  md5(decoded)={md5}")
    print(f"Manifest: {manifest}\nLogs:     {logs}")
    if errors:
        print(f"\n{len(errors)} failure(s):")
        for e in errors:
            print(f"  {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
