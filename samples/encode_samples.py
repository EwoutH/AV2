#!/usr/bin/env python3
"""
End-to-end AV2 test-video generator (parallel pipeline).

Follows the AVM README and the AV2 Common Test Conditions (CTC):
  * AVM is cloned from the official GitHub repo and built in Release mode
  * Source clips come from the official AV2 CTC test set on media.xiph.org
  * Default QPs are the CTC Random Access QPs (110..235)
  * Each stream is verified with the reference decoder's built-in --md5

Everything overlaps:
  * AVM is built while sources download
  * Sources download concurrently, smallest first
  * Each clip's encodes start as soon as that clip has downloaded and the
    build has finished; they don't wait for other (larger) downloads

Requirements (per the AVM README): CMake >= 3.16, Git, Perl, yasm (preferred)
or nasm, and a C/C++ compiler (Visual Studio 2019 16.7+ on Windows).

Usage:
    python av2_encode.py                         # small + 720p + 1080p
    python av2_encode.py --set 1080p --frames 130 --extra-args "--cpu-used=4"
    python av2_encode.py --avm-ref v13.0.0       # pin AVM for reproducibility
"""
import argparse
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

AVM_REPO = "https://github.com/AOMediaCodec/avm.git"
CTC_BASE = "https://media.xiph.org/video/aomctc/test_set/"

# Clips from the AV2 CTC test set, as "<class dir>/<file stem>".
# Many are 10-bit, which is worth covering when benchmarking a decoder.
CLIP_SETS = {
    # Class A5 (270p) and A4 (360p): small, fast smoke tests
    "small": ["a5_270p/sparks_elevator_480x270p_60",
              "a4_360p/stockholm_640x360p60",
              "a4_360p/speed_bag_640x360p"],
    # Class A3 (720p)
    "720p": ["a3_720p/KristenAndSara_1280x720_60",
             "a3_720p/Netflix_DrivingPOV_720p_60fps_10bit_420",
             "a3_720p/vidyo4_720p_60fps"],
    # Class A2 (1080p): heavy motion, texture, 10-bit, and a vertical clip
    "1080p": ["a2_2k/crowd_run_1080p50",
              "a2_2k/old_town_cross_1080p50",
              "a2_2k/RitualDance_1920x1080_60fps_10bit_420",
              "a2_2k/TunnelFlag_1920x1080_60fps_10bit_420",
              "a2_2k/Vertical_bees_2997_1080x1920"],
    # Class A1 (4K, 10-bit): several GB per source and very slow to encode
    "4k": ["a1_4k/Tango_3840x2160_5994fps_10bit_420",
           "a1_4k/FoodMarket2_3840x2160_5994fps_10bit_420"],
}
CLIP_SETS["hd"] = CLIP_SETS["720p"] + CLIP_SETS["1080p"]
CLIP_SETS["all"] = CLIP_SETS["small"] + CLIP_SETS["hd"]  # 4k is opt-in

# AV2 CTC Random Access QPs (CTC v8)
CTC_RA_QPS = [110, 135, 160, 185, 210, 235]

_print_lock = threading.Lock()


def log(msg: str):
    with _print_lock:
        print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def run(cmd, logfile: Path, cwd=None, capture=False):
    """Run a command, appending its output to a log file so parallel jobs
    don't interleave on the console. Returns stdout if capture=True."""
    with open(logfile, "a") as f:
        f.write("+ " + " ".join(str(c) for c in cmd) + "\n")
        f.flush()
        r = subprocess.run([str(c) for c in cmd], cwd=cwd,
                           stdout=subprocess.PIPE if capture else f,
                           stderr=f if capture else subprocess.STDOUT,
                           text=True)
        if capture:
            f.write(r.stdout)
    if r.returncode != 0:
        raise RuntimeError(f"{Path(str(cmd[0])).name} failed "
                           f"(exit {r.returncode}); see {logfile}")
    return r.stdout if capture else None


# --------------------------------------------------------------------------
# Prerequisites
# --------------------------------------------------------------------------
WIN_HINTS = {
    "git": "winget install Git.Git",
    "cmake": "winget install Kitware.CMake",
    "perl": "winget install StrawberryPerl.StrawberryPerl",
    "yasm/nasm": ("winget install NASM.NASM   (or, preferred: download "
                  "yasm win64.exe, rename it to yasm.exe and put it on PATH; "
                  "do NOT use vsyasm.exe)"),
}


def check_tools():
    missing = [t for t in ("git", "cmake", "perl") if not shutil.which(t)]
    # The README prefers yasm but accepts a recent nasm.
    if not (shutil.which("yasm") or shutil.which("nasm")):
        missing.append("yasm/nasm")
    if missing:
        msg = f"Missing required tools: {', '.join(missing)}"
        if os.name == "nt":
            msg += "\nInstall with:\n" + "\n".join(
                f"  {WIN_HINTS[t]}" for t in missing)
            msg += "\nthen open a NEW terminal so PATH updates."
        sys.exit(msg)

    out = subprocess.run(["cmake", "--version"], capture_output=True,
                         text=True).stdout
    m = re.search(r"(\d+)\.(\d+)", out)
    if m and (int(m[1]), int(m[2])) < (3, 16):
        sys.exit(f"CMake {m[0]} found; AVM needs 3.16 or newer.")


# --------------------------------------------------------------------------
# Build
# --------------------------------------------------------------------------
def build_avm(work: Path, ref, jobs: int, logs: Path, cmake_args: list):
    src, build = work / "avm", work / "avm_build"
    blog = logs / "build.log"
    log(f"Building AVM (log: {blog})")
    if not src.exists():
        if ref is None:
            run(["git", "clone", "--depth", "1", AVM_REPO, src], blog)
        else:
            run(["git", "clone", AVM_REPO, src], blog)
            run(["git", "checkout", ref], blog, cwd=src)
    commit = run(["git", "rev-parse", "HEAD"], blog, cwd=src,
                 capture=True).strip()

    # A failed earlier configure leaves a stale CMake cache (e.g. with
    # TensorFlow Lite switched on), so start fresh unless a build succeeded.
    exe_name = "avmenc" + (".exe" if os.name == "nt" else "")
    built = any((d / exe_name).exists() for d in (build, build / "Release"))
    if build.exists() and not built:
        shutil.rmtree(build)
    build.mkdir(exist_ok=True)
    # Tests and docs are off: they'd pull in test data and doxygen.
    # CONFIG_ML_PART_SPLIT is an encoder-only speed feature that drags in a
    # TensorFlow Lite build via bash scripts, which breaks on Windows. It
    # doesn't change the bitstream format, so streams remain valid AV2.
    run(["cmake", src, "-DCMAKE_BUILD_TYPE=Release",
         "-DENABLE_TESTS=0", "-DENABLE_DOCS=0",
         "-DCONFIG_ML_PART_SPLIT=0", "-DCONFIG_TENSORFLOW_LITE=0",
         *cmake_args], blog, cwd=build)
    # --config is needed for Visual Studio (multi-config) generators and is
    # ignored by single-config ones like Makefiles/Ninja.
    run(["cmake", "--build", ".", "--config", "Release", "-j", str(jobs)],
        blog, cwd=build)

    # Visual Studio puts binaries in a Release\ subfolder with .exe.
    exe = ".exe" if os.name == "nt" else ""

    def find(name):
        for d in (build, build / "Release"):
            if (d / (name + exe)).exists():
                return d / (name + exe)
        raise RuntimeError(f"{name}{exe} not found in {build}")

    enc, dec = find("avmenc"), find("avmdec")
    log(f"Build finished at commit {commit[:12]}")
    return enc, dec, commit


# --------------------------------------------------------------------------
# Download
# --------------------------------------------------------------------------
def download(clip: str, dest_dir: Path) -> Path:
    out = dest_dir / f"{Path(clip).name}.y4m"
    if out.exists():
        log(f"Already have {out.name}")
        return out
    url = f"{CTC_BASE}{clip}.y4m"
    tmp = out.with_suffix(".part")
    log(f"Downloading {clip}")
    t0 = time.time()
    with urllib.request.urlopen(url) as r, open(tmp, "wb") as f:
        shutil.copyfileobj(r, f, length=1 << 20)
    tmp.rename(out)
    mb = out.stat().st_size / 1e6
    log(f"Downloaded {out.name} ({mb:.0f} MB in {time.time() - t0:.0f}s)")
    return out


# --------------------------------------------------------------------------
# Encode + verify
# --------------------------------------------------------------------------
def encode_job(enc, dec, src: Path, out: Path, frames: int, qp: int,
               container: str, extra: list, logs: Path):
    jlog = logs / f"{out.stem}.log"
    if out.exists():
        log(f"Skipping encode, {out.name} exists")
    else:
        log(f"Encoding {out.name}")
        t0 = time.time()
        tmp = out.with_name(out.name + ".part")
        fmt = ["--obu"] if container == "obu" else ["--ivf"]
        run([enc, src, "-o", tmp, *fmt, f"--limit={frames}",
             "--end-usage=q", f"--qp={qp}", *extra], jlog)
        tmp.rename(out)
        log(f"Encoded {out.name} in {time.time() - t0:.0f}s")

    # The reference decoder's --md5 hashes the decoded frames directly,
    # avoiding multi-GB raw output files. Compare dav2d against this later.
    stdout = run([dec, out, "--md5"], jlog, capture=True)
    m = re.search(r"\b[0-9a-f]{32}\b", stdout)
    if not m:
        raise RuntimeError(f"No MD5 in decoder output; see {jlog}")
    return out.name, out.stat().st_size, m[0]


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
                    help="CTC clips as <class>/<name>, e.g. a2_2k/crowd_run_1080p50")
    ap.add_argument("--frames", type=int, default=65,
                    help="Frames per encode (65 = one CTC GOP)")
    ap.add_argument("--qp", type=int, nargs="+", default=CTC_RA_QPS,
                    help="Quantizer values (default: AV2 CTC RA QPs)")
    ap.add_argument("--container", choices=["ivf", "obu"], default="ivf",
                    help="ivf (default) or raw Section 5 .obu as the CTC uses")
    ap.add_argument("--avm-ref", default=None,
                    help="AVM tag/commit to build (default: latest main)")
    ap.add_argument("--cmake-args", default="",
                    help="Extra CMake configure flags, quoted as one string")
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

        build_fut = build_pool.submit(build_avm, work, args.avm_ref,
                                      args.build_jobs, logs,
                                      args.cmake_args.split())
        dl_futs = {dl_pool.submit(download, c, sources): c for c in clips}

        try:
            enc, dec, commit = build_fut.result()
        except Exception as e:
            dl_pool.shutdown(cancel_futures=True)
            sys.exit(f"Build failed: {e}")

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
                out = out_dir / (f"{src.stem}_qp{qp}_{args.frames}f"
                                 f".{args.container}")
                enc_futs.append(enc_pool.submit(
                    encode_job, enc, dec, src, out, args.frames, qp,
                    args.container, extra, logs))

        for fut in as_completed(enc_futs):
            try:
                results.append(fut.result())
            except Exception as e:
                errors.append(str(e))
                log(f"ERROR: {e}")

    results.sort()
    manifest = out_dir / "manifest.txt"
    with open(manifest, "w") as f:
        # Record exactly what produced these streams.
        f.write(f"# AVM commit: {commit}\n")
        f.write(f"# frames={args.frames} extra_args='{args.extra_args}'\n")
        f.write("# file\tbytes\tmd5(decoded, avmdec --md5)\n")
        for name, size, md5 in results:
            f.write(f"{name}\t{size}\t{md5}\n")

    print("\nEncoded streams:")
    for name, size, md5 in results:
        print(f"  {name:60s} {size / 1024:9.1f} KiB  {md5}")
    print(f"Manifest: {manifest}\nLogs:     {logs}")
    if errors:
        print(f"\n{len(errors)} failure(s):")
        for e in errors:
            print(f"  {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
