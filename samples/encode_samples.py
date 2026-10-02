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
  * Sources download concurrently, smallest first, and only the frames
    that are needed (the full CTC clips are up to several GB each)
  * Each clip's encodes start as soon as that clip has downloaded and the
    build has finished; they don't wait for other (larger) downloads

Requirements (per the AVM README): CMake >= 3.16, Git, Perl, yasm (preferred)
or nasm, and a C/C++ compiler (Visual Studio 2019 16.7+ on Windows).

Usage:
    python encode_samples.py                         # small + 720p + 1080p
    python encode_samples.py --set 1080p --frames 130 --extra-args "--cpu-used=4"
    python encode_samples.py --avm-ref v13.0.0       # pin AVM for reproducibility
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

AVM_REPO = "https://github.com/AOMediaCodec/avm.git"

# media.xiph.org first, then a Debian mirror of it as a fallback.
CTC_BASES = ["https://media.xiph.org/video/aomctc/",
             "https://cdimage.debian.org/mirror/media.xiph.org/video/aomctc/"]


def _paths(cls, name, folders=("test_set_long", "test_set")):
    """Candidate paths for a clip. test_set_long holds the original,
    full-length clips under their original names; test_set holds trimmed,
    sometimes renamed versions. Each candidate is tried in order."""
    return [f"{f}/{cls}/{name}" for f in folders]


# Clips from the AV2 CTC test set: (name, [candidate paths under aomctc/]).
# Only the first frames are downloaded (see download()), so large sources
# cost little. Many are 10-bit, worth covering when benchmarking a decoder.
CLIP_SETS = {
    # Class A5 (270p) and A4 (360p): small, fast smoke tests
    "small": [
        ("FourPeople_480x270_60",
         _paths("a5_270p", "FourPeople_480x270_60", ("test_set",))),
        ("Vertical_Bayshore_270x480_2997",
         _paths("a5_270p", "Vertical_Bayshore_270x480_2997", ("test_set",))),
        ("BlueSky_360p25_v2",
         _paths("a4_360p", "BlueSky_360p25_v2", ("test_set",))),
    ],
    # Class A3 (720p)
    "720p": [
        ("KristenAndSara_1280x720_60",
         _paths("a3_720p", "KristenAndSara_1280x720_60")),
        ("Netflix_DrivingPOV_720p_60fps_10bit_420",
         _paths("a3_720p", "Netflix_DrivingPOV_720p_60fps_10bit_420")),
        ("vidyo4_720p_60fps", _paths("a3_720p", "vidyo4_720p_60fps")),
    ],
    # Class A2 (1080p): heavy motion, texture, 10-bit, and a vertical clip
    "1080p": [
        (n, _paths("a2_2k", n)) for n in (
            "crowd_run_1080p50",
            "old_town_cross_1080p50",
            "RitualDance_1920x1080_60fps_10bit_420",
            "TunnelFlag_1920x1080_60fps_10bit_420",
            "Vertical_bees_2997_1080x1920")
    ],
    # Class A1 (4K, 10-bit): very slow to encode
    "4k": [
        (n, _paths("a1_4k", n)) for n in (
            "Tango_3840x2160_5994fps_10bit_420",
            "FoodMarket2_3840x2160_5994fps_10bit_420")
    ],
}
CLIP_SETS["hd"] = CLIP_SETS["720p"] + CLIP_SETS["1080p"]
CLIP_SETS["all"] = CLIP_SETS["small"] + CLIP_SETS["hd"]  # 4k is opt-in

# AV2 CTC Random Access QPs (CTC v8)
CTC_RA_QPS = [110, 135, 160, 185, 210, 235]

_print_lock = threading.Lock()


def log(msg: str):
    with _print_lock:
        print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


WINDOWS_CRASH_CODES = {
    0xC0000005: "access violation",
    0xC00000FD: "stack overflow",
    0xC0000409: "stack buffer overrun",
    0xC0000017: "out of memory",
}


def describe_exit(code: int) -> str:
    """Windows reports crashes as large exit codes like 3221225477;
    show them as e.g. 'crashed: access violation (0xC0000005)'."""
    u = code & 0xFFFFFFFF
    if u >= 0xC0000000:
        return f"crashed: {WINDOWS_CRASH_CODES.get(u, 'exception')} (0x{u:08X})"
    return f"exit {code}"


def run(cmd, logfile: Path, cwd=None, capture=False):
    """Run a command, appending its output to a log file so parallel jobs
    don't interleave on the console. Returns stdout if capture=True."""
    with open(logfile, "a", encoding="utf-8", errors="replace") as f:
        f.write("+ " + " ".join(str(c) for c in cmd) + "\n")
        f.flush()
        # errors="replace": tool output on Windows isn't always valid in the
        # console code page, and a decode error shouldn't fail the job.
        r = subprocess.run([str(c) for c in cmd], cwd=cwd,
                           stdout=subprocess.PIPE if capture else f,
                           stderr=f if capture else subprocess.STDOUT,
                           text=True, errors="replace")
        if capture:
            f.write(r.stdout)
    if r.returncode != 0:
        raise RuntimeError(f"{Path(str(cmd[0])).name} failed "
                           f"({describe_exit(r.returncode)}); see {logfile}")
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
# Tests and docs are off: they'd pull in test data and doxygen.
# TensorFlow Lite is off because its build runs bash scripts that break on
# Windows. Experiments that require it are found and disabled automatically
# (see configure_avm).
BASE_CMAKE_ARGS = ["-DCMAKE_BUILD_TYPE=Release", "-DENABLE_TESTS=0",
                   "-DENABLE_DOCS=0", "-DCONFIG_TENSORFLOW_LITE=0",
                   "-DCONFIG_ML_PART_SPLIT=0"]

# When an enabled experiment needs TFLite, AVM silently turns TFLite back on
# and names only one such experiment per configure run, e.g.:
#   --- Enabled CONFIG_TENSORFLOW_LITE, required for CONFIG_DIP_EXT_PRUNING.
TFLITE_DEP_RE = re.compile(
    r"Enabled CONFIG_TENSORFLOW_LITE, required for (CONFIG_\w+)")
MAX_CONFIGURE_ATTEMPTS = 10


def _force_remove(func, path, _exc):
    # Read-only files block rmtree on Windows.
    os.chmod(path, 0o700)
    func(path)


def tflite_disables_path(work: Path) -> Path:
    return work / "avm_tflite_disabled.json"


def learned_disables(work: Path) -> list:
    """Experiments found to need TFLite on earlier runs, so later runs
    configure correctly the first time."""
    try:
        names = json.loads(tflite_disables_path(work).read_text())
    except (OSError, ValueError):
        names = []
    return [f"-D{n}=0" for n in names]


def configure_avm(src: Path, build: Path, flags: list, work: Path,
                  logs: Path) -> list:
    """Run CMake configure. If it fails because an experiment switched
    TFLite back on, disable that experiment and retry from a clean build
    folder. Returns the flags that worked."""
    clog = logs / "configure.log"
    for attempt in range(1, MAX_CONFIGURE_ATTEMPTS + 1):
        clog.unlink(missing_ok=True)
        try:
            run(["cmake", src, *flags], clog, cwd=build)
            return flags
        except RuntimeError:
            text = clog.read_text(encoding="utf-8", errors="replace")
            new = [d for d in dict.fromkeys(TFLITE_DEP_RE.findall(text))
                   if f"-D{d}=0" not in flags]
            if not new:
                raise  # a different configure error; see configure.log
            learned = [f[2:-2] for f in learned_disables(work)]
            for d in new:
                log(f"{d} requires TensorFlow Lite; disabling it and "
                    f"retrying configure (attempt {attempt + 1})")
                flags = flags + [f"-D{d}=0"]
                if d not in learned:
                    learned.append(d)
            tflite_disables_path(work).write_text(json.dumps(learned, indent=2))
            # Start clean so the failed attempt's cache can't interfere.
            shutil.rmtree(build, onerror=_force_remove)
            build.mkdir()
    raise RuntimeError(f"configure still failing after "
                       f"{MAX_CONFIGURE_ATTEMPTS} attempts; see {clog}")


def build_avm(work: Path, ref, jobs: int, logs: Path, cmake_args: list,
              rebuild: bool = False):
    src = work / "avm"
    # One build folder per OS: a Windows and a WSL run sharing this workdir
    # would otherwise keep wiping each other's builds.
    build = work / ("avm_build_windows" if os.name == "nt" else "avm_build_linux")
    legacy = work / "avm_build"  # folder name used by earlier versions
    if legacy.exists() and not build.exists():
        legacy.rename(build)
    if rebuild and build.exists():
        log("--rebuild given: removing the existing AVM build")
        shutil.rmtree(build, onerror=_force_remove)
    blog = logs / "build.log"
    if not src.exists():
        log("Cloning AVM")
        if ref is None:
            run(["git", "clone", "--depth", "1", AVM_REPO, src], blog)
        else:
            run(["git", "clone", AVM_REPO, src], blog)
            run(["git", "checkout", ref], blog, cwd=src)
    commit = run(["git", "rev-parse", "HEAD"], blog, cwd=src,
                 capture=True).strip()

    flags = BASE_CMAKE_ARGS + learned_disables(work) + cmake_args
    exe = ".exe" if os.name == "nt" else ""
    stamp_path = build / "build_stamp.json"
    try:
        stamp = json.loads(stamp_path.read_text())
    except (OSError, ValueError):
        stamp = None
    built = all(any((d / (n + exe)).exists() for d in (build, build / "Release"))
                for n in ("avmenc", "avmdec"))
    if built and stamp is None:
        # A finished build from a version of this script that didn't write
        # stamps. Adopt it instead of spending minutes rebuilding; use
        # --rebuild if it was built with different settings.
        log("Adopting existing AVM build (use --rebuild to force a fresh one)")
        stamp = {"commit": commit, "flags": flags}
        stamp_path.write_text(json.dumps(stamp, indent=2))

    # Re-running CMake configure regenerates AVM's config headers, which
    # makes Visual Studio recompile everything. So skip configure and build
    # entirely when the commit and flags match the last successful build.
    if built and stamp and stamp.get("commit") == commit \
            and stamp.get("flags") == flags:
        log(f"AVM already built at commit {commit[:12]}, skipping build")
    else:
        # No successful build to reuse (or a failed configure left a stale
        # cache), so start from an empty folder.
        if build.exists() and not (built and stamp):
            shutil.rmtree(build, onerror=_force_remove)
        build.mkdir(exist_ok=True)
        stamp_path.unlink(missing_ok=True)
        log(f"Building AVM at commit {commit[:12]} (log: {blog})")
        flags = configure_avm(src, build, flags, work, logs)
        # --config is needed for Visual Studio (multi-config) generators and
        # is ignored by single-config ones like Makefiles/Ninja.
        run(["cmake", "--build", ".", "--config", "Release", "-j", str(jobs)],
            blog, cwd=build)
        stamp_path.write_text(json.dumps({"commit": commit, "flags": flags},
                                         indent=2))
        log(f"Build finished at commit {commit[:12]}")

    # Visual Studio puts binaries in a Release\ subfolder with .exe.
    def find(name):
        for d in (build, build / "Release"):
            if (d / (name + exe)).exists():
                return d / (name + exe)
        raise RuntimeError(f"{name}{exe} not found in {build}")

    enc, dec = find("avmenc"), find("avmdec")
    return enc, dec, commit, flags


# --------------------------------------------------------------------------
# Download
# --------------------------------------------------------------------------
def y4m_frame_bytes(header: bytes) -> int:
    """Bytes of picture data per frame, from a Y4M stream header."""
    tags = {t[:1]: t[1:] for t in header.decode("ascii").split()[1:]}
    w, h = int(tags["W"]), int(tags["H"])
    cs = tags.get("C", "420jpeg")
    m = re.search(r"(?:p|mono)(\d+)$", cs)
    bps = 2 if m and int(m[1]) > 8 else 1
    cw, ch = (w + 1) // 2, (h + 1) // 2
    if cs.startswith("444"):
        samples = 3 * w * h
    elif cs.startswith("422"):
        samples = w * h + 2 * cw * h
    elif cs.startswith("mono"):
        samples = w * h
    else:  # all 4:2:0 variants
        samples = w * h + 2 * cw * ch
    return samples * bps


def y4m_frame_count(path: Path) -> int:
    """Frames in a Y4M file whose frame headers are plain 'FRAME\\n'
    (which is how download() writes them)."""
    with open(path, "rb") as f:
        header = f.readline()
    fb = y4m_frame_bytes(header)
    return (path.stat().st_size - len(header)) // (len(b"FRAME\n") + fb)


def _open_first(paths: list):
    """Open the first candidate path that exists on any mirror."""
    tried = []
    for rel in paths:
        for base in CTC_BASES:
            url = f"{base}{rel}.y4m"
            try:
                return urllib.request.urlopen(url, timeout=60), url
            except urllib.error.HTTPError as e:
                tried.append(f"{url} ({e.code})")
            except urllib.error.URLError as e:
                tried.append(f"{url} ({e.reason})")
    raise RuntimeError("not found at any of:\n    " + "\n    ".join(tried))


def _read_exact(r, n: int) -> bytes:
    buf = bytearray()
    while len(buf) < n:
        chunk = r.read(min(n - len(buf), 1 << 20))
        if not chunk:
            break
        buf += chunk
    return bytes(buf)


def download(name: str, paths: list, dest_dir: Path, frames: int) -> Path:
    """Fetch only the first `frames` frames of a clip. Y4M is a header line
    followed by frames, so the download simply stops once it has enough,
    instead of fetching multi-GB files in full."""
    out = dest_dir / f"{name}.y4m"
    try:
        if out.exists() and y4m_frame_count(out) >= frames:
            log(f"Already have {out.name}")
            return out
        r, url = _open_first(paths)
        log(f"Downloading {frames} frames of {name}")
        t0 = time.time()
        tmp = out.with_name(out.name + ".part")
        got = 0
        with r, open(tmp, "wb") as f:
            header = r.readline()
            if not header.startswith(b"YUV4MPEG2 "):
                raise RuntimeError(f"{url} is not a Y4M file")
            fb = y4m_frame_bytes(header)
            f.write(header)
            while got < frames:
                if not r.readline().startswith(b"FRAME"):
                    break  # end of clip
                data = _read_exact(r, fb)
                if len(data) < fb:
                    break  # truncated last frame
                f.write(b"FRAME\n")
                f.write(data)
                got += 1
        if got == 0:
            raise RuntimeError(f"no frames read from {url}")
        os.replace(tmp, out)
        note = "" if got == frames else f" (clip only has {got})"
        log(f"Downloaded {name}: {got} frames, "
            f"{out.stat().st_size / 1e6:.0f} MB in {time.time() - t0:.0f}s"
            f"{note}")
        return out
    except Exception as e:
        # Report right away, not only after the AVM build finishes.
        log(f"ERROR downloading {name}: {e}")
        raise


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
        os.replace(tmp, out)
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
                    help="Clip paths under aomctc/, e.g. test_set_long/a2_2k/crowd_run_1080p50")
    ap.add_argument("--frames", type=int, default=65,
                    help="Frames per encode (65 = one CTC GOP)")
    ap.add_argument("--qp", type=int, nargs="+", default=CTC_RA_QPS,
                    help="Quantizer values (default: AV2 CTC RA QPs)")
    ap.add_argument("--container", choices=["ivf", "obu"], default="ivf",
                    help="ivf (default) or raw Section 5 .obu as the CTC uses")
    ap.add_argument("--avm-ref", default=None,
                    help="AVM tag/commit to build (default: latest main)")
    ap.add_argument("--rebuild", action="store_true",
                    help="Delete the AVM build and build it from scratch")
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
    if args.clips:
        clips = [(Path(c).name, [c]) for c in args.clips]
    else:
        clips = CLIP_SETS[args.set]
    extra = args.extra_args.split()

    results, errors = [], []
    with ThreadPoolExecutor(1) as build_pool, \
         ThreadPoolExecutor(args.download_jobs) as dl_pool, \
         ThreadPoolExecutor(args.encode_jobs) as enc_pool:

        build_fut = build_pool.submit(build_avm, work, args.avm_ref,
                                      args.build_jobs, logs,
                                      args.cmake_args.split(), args.rebuild)
        dl_futs = {dl_pool.submit(download, name, paths, sources, args.frames): name
                   for name, paths in clips}

        try:
            enc, dec, commit, cmake_flags = build_fut.result()
        except Exception as e:
            dl_pool.shutdown(cancel_futures=True)
            sys.exit(f"Build failed: {e}")

        enc_futs = []
        for fut in as_completed(dl_futs):
            clip = dl_futs[fut]
            try:
                src = fut.result()
            except Exception as e:
                errors.append(f"download {clip}: {e}")  # already logged
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
        f.write(f"# CMake flags: {' '.join(cmake_flags)}\n")
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
