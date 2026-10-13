#!/usr/bin/env python3
"""
End-to-end AV2 test-video generator (parallel pipeline).

Follows the AVM README and the AV2 Common Test Conditions (CTC):
  * AVM is cloned from the official GitHub repo and built in Release mode
  * Source clips come from the official AV2 CTC test set on media.xiph.org
  * Default QPs are three of the CTC Random Access QPs: 110, 160, 210
  * Each stream is verified with the reference decoder's built-in --md5

Everything overlaps:
  * AVM is built while sources download
  * Sources download concurrently, smallest first, and only the frames
    that are needed (the full CTC clips are up to several GB each)
  * Each clip's encodes start as soon as that clip has downloaded and the
    build has finished; they don't wait for other (larger) downloads

The middle-quality encode of every clip runs first; the other qualities
follow once no middle-quality encode is waiting.

Encodes are admitted by a memory budget rather than by CPU count alone:
each encode's memory is estimated from its resolution, and new encodes
wait until they fit. If psutil is installed (pip install psutil), real
peak memory is measured and the estimate adjusts itself.

Requirements (per the AVM README): CMake >= 3.16, Git, Perl, yasm (preferred)
or nasm, and a C/C++ compiler (Visual Studio 2019 16.7+ on Windows).

Usage:
    python encode_samples.py                         # small + 720p + 1080p
    python encode_samples.py --set 1080p --frames 130 --cpu-used 3
    python encode_samples.py --mem-budget-gb 16      # stricter memory cap
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
import heapq
import itertools
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

try:
    import psutil  # optional: enables measured (adaptive) memory estimates
except ImportError:
    psutil = None

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

# AV2 CTC Random Access QPs (CTC v8). Three of them (high, middle and low
# quality) are plenty for decoder testing; the middle one is encoded first.
CTC_RA_QPS = [110, 135, 160, 185, 210, 235]
DEFAULT_QPS = [110, 160, 210]

_print_lock = threading.Lock()


def log(msg: str):
    with _print_lock:
        print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def fmt_duration(seconds: float) -> str:
    s = int(seconds)
    if s >= 3600:
        return f"{s // 3600}h{s % 3600 // 60:02d}m"
    if s >= 60:
        return f"{s // 60}m{s % 60:02d}s"
    return f"{s}s"


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
        f.write(f"= {describe_exit(r.returncode)}\n")
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

# MSVC 19.51 (Visual Studio 2026 18.10) never finishes compiling
# highbd_variance_avx2.c at /O2: its SSA optimizer loops forever, so the
# whole build hangs. Turning that one optimizer pass off for that one file
# works around it. CMake runs this file right after AVM's project() call
# (CMAKE_PROJECT_INCLUDE), so the AVM checkout itself stays unmodified.
#
# /MAP makes the linker write avmenc.map next to avmenc.exe. It doesn't
# change the code, and lets a crash be traced to a function: Windows logs
# the fault offset (Event Viewer > Application > "Application Error").
MSVC_WORKAROUNDS_CMAKE = """\
if(MSVC AND MSVC_VERSION GREATER_EQUAL 1950)
  set_source_files_properties(
    "${CMAKE_SOURCE_DIR}/avm_dsp/x86/highbd_variance_avx2.c"
    PROPERTIES COMPILE_OPTIONS "/d2SSAOptimizer-")
endif()
if(MSVC)
  string(APPEND CMAKE_EXE_LINKER_FLAGS " /MAP")
endif()
"""


def msvc_workaround_flags(work: Path) -> list:
    if os.name != "nt":
        return []
    path = work / "avm_msvc_workarounds.cmake"
    path.write_text(MSVC_WORKAROUNDS_CMAKE)
    return [f"-DCMAKE_PROJECT_INCLUDE={path.as_posix()}"]


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
    # build.log is appended to across runs; mark where this run starts.
    with open(blog, "a", encoding="utf-8") as f:
        f.write(f"\n===== Run started {time.strftime('%Y-%m-%d %H:%M:%S')} "
                f"=====\n")
    if not src.exists():
        log("Cloning AVM")
        if ref is None:
            run(["git", "clone", "--depth", "1", AVM_REPO, src], blog)
        else:
            run(["git", "clone", AVM_REPO, src], blog)
            run(["git", "checkout", ref], blog, cwd=src)
    commit = run(["git", "rev-parse", "HEAD"], blog, cwd=src,
                 capture=True).strip()

    flags = (BASE_CMAKE_ARGS + msvc_workaround_flags(work)
             + learned_disables(work) + cmake_args)
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
def y4m_tags(header: bytes) -> dict:
    return {t[:1]: t[1:] for t in header.decode("ascii").split()[1:]}


def y4m_frame_bytes(header: bytes) -> int:
    """Bytes of picture data per frame, from a Y4M stream header."""
    tags = y4m_tags(header)
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


def y4m_megapixels(path: Path) -> float:
    with open(path, "rb") as f:
        tags = y4m_tags(f.readline())
    return int(tags["W"]) * int(tags["H"]) / 1e6


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
    # Marks a file holding the whole clip, for clips shorter than --frames;
    # without it those would look incomplete and be re-downloaded every run.
    whole = out.with_name(out.name + ".whole")
    try:
        if out.exists() and (whole.exists() or y4m_frame_count(out) >= frames):
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
        if got < frames:
            whole.touch()
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
# Encoder speed setting
# --------------------------------------------------------------------------
# avmenc --help describes --cpu-used with its range, aomenc-style, e.g.
#   --cpu-used=<arg>  Speed setting (0..6 in good mode, ...)
CPU_USED_RANGE_RE = re.compile(r"--cpu-used=\S*\s+[^\n]*?\((\d+)\.\.(\d+)")
FALLBACK_CPU_USED = 4


def pick_cpu_used(enc: Path, logs: Path):
    """Pick a speed preset about two thirds of the way to the fastest end
    of the encoder's good-quality range: much faster than the CTC's
    slowest setting, while still exercising most coding tools (which is
    what a decoder benchmark needs). Returns (value, range or None)."""
    r = subprocess.run([str(enc), "--help"], capture_output=True,
                       text=True, errors="replace")
    text = r.stdout + r.stderr
    (logs / "avmenc_help.txt").write_text(text, encoding="utf-8")
    m = CPU_USED_RANGE_RE.search(text)
    if not m:
        return FALLBACK_CPU_USED, None
    lo, hi = int(m[1]), int(m[2])
    return round(lo + (hi - lo) * 2 / 3), (lo, hi)


# --------------------------------------------------------------------------
# Memory budget
# --------------------------------------------------------------------------
def total_ram_bytes():
    if psutil:
        return psutil.virtual_memory().total
    if os.name == "nt":
        import ctypes

        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong),
                        ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong),
                        ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong),
                        ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong),
                        ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]

        s = MEMORYSTATUSEX()
        s.dwLength = ctypes.sizeof(s)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(s)):
            return s.ullTotalPhys
        return None
    try:
        return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
    except (ValueError, OSError, AttributeError):
        return None


class MemoryBudget:
    """Starts encodes in priority order (then submission order), at most
    max_running at a time, while their estimated memory fits in the
    budget. An encode larger than the whole budget still runs, but
    only on its own. Estimates are base + per-megapixel cost; once a 720p+
    encode has been measured (needs psutil), the estimate is scaled to match
    the worst measurement seen, plus a 20% margin."""

    LEARN_MIN_MPIX = 0.9  # small clips are dominated by fixed overhead

    def __init__(self, budget_gb, base_gb, per_mpix_gb, max_running):
        self.budget, self.base, self.per_mpix = budget_gb, base_gb, per_mpix_gb
        self.max_running = max_running
        self.scale = None  # learned correction factor
        self.used = 0.0
        self.running = 0
        self.queue = []  # heap of (priority, seq, ticket)
        self.seq = itertools.count()
        self.cond = threading.Condition()

    def _estimate(self, mpix):
        est = self.base + self.per_mpix * mpix
        return est * self.scale if self.scale else est

    def acquire(self, mpix, priority=0) -> float:
        """Wait for a turn. Lower priority values go first."""
        entry = (priority, next(self.seq), object())
        with self.cond:
            heapq.heappush(self.queue, entry)
            while True:
                need = self._estimate(mpix)
                if self.queue[0] is entry and \
                        self.running < self.max_running and (
                        self.running == 0 or self.used + need <= self.budget):
                    break
                self.cond.wait()
            heapq.heappop(self.queue)
            self.used += need
            self.running += 1
            self.cond.notify_all()
            return need

    def release(self, held: float):
        with self.cond:
            self.used -= held
            self.running -= 1
            self.cond.notify_all()

    def observe(self, mpix, peak_gb):
        if mpix < self.LEARN_MIN_MPIX or peak_gb <= 0:
            return
        with self.cond:
            ratio = peak_gb / (self.base + self.per_mpix * mpix) * 1.2
            old = self.scale
            self.scale = max(self.scale or 0, ratio) if old else ratio
            if self.scale != old:
                log(f"Memory estimate updated from a measured peak of "
                    f"{peak_gb:.1f} GB: now ~{self._estimate(2.07):.1f} GB "
                    f"per 1080p encode")
            self.cond.notify_all()

    def waiting(self) -> int:
        with self.cond:
            return len(self.queue)


# --------------------------------------------------------------------------
# Progress reporting
# --------------------------------------------------------------------------
class Progress:
    """Tracks every encode and periodically prints one status line per
    running encode: frames done, percent, speed and ETA."""

    def __init__(self, budget: MemoryBudget):
        self.lock = threading.Lock()
        self.active = {}
        self.total_jobs = self.finished = self.failed = 0
        self.budget = budget

    def add_job(self):
        with self.lock:
            self.total_jobs += 1

    def start(self, name, total_frames, mem_gb):
        with self.lock:
            self.active[name] = {"n": 0, "total": total_frames,
                                 "t0": time.time(), "mem": mem_gb}

    def update(self, name, frames_done):
        with self.lock:
            if name in self.active:
                self.active[name]["n"] = frames_done

    def finish(self, name, ok=True):
        with self.lock:
            self.active.pop(name, None)
            self.finished += 1
            self.failed += not ok

    def report(self):
        with self.lock:
            if not self.active:
                return
            now = time.time()
            lines = [f"Progress: {self.finished}/{self.total_jobs} encodes done"
                     f"{f' ({self.failed} failed)' if self.failed else ''}, "
                     f"{len(self.active)} running, "
                     f"{self.budget.waiting()} queued, "
                     f"~{self.budget.used:.0f}/{self.budget.budget:.0f} GB "
                     f"budgeted"]
            width = max(len(n) for n in self.active)
            for name, a in sorted(self.active.items()):
                el = now - a["t0"]
                n, total = a["n"], a["total"]
                if n == 0:
                    status = f"starting... ({fmt_duration(el)} elapsed)"
                else:
                    fps = n / el
                    eta = (total - n) / fps if fps > 0 else 0
                    status = (f"{n:>5}/{total:<5} {100 * n / total:3.0f}%  "
                              f"{fps:6.2f} fps  elapsed {fmt_duration(el)}, "
                              f"ETA {fmt_duration(eta)}")
                lines.append(f"    {name:<{width}}  {status}")
        log("\n".join(lines))


def progress_reporter(progress: Progress, interval: float,
                      stop: threading.Event):
    while not stop.wait(interval):
        progress.report()


# --------------------------------------------------------------------------
# Encode + verify
# --------------------------------------------------------------------------
# avmenc prints one line per coded frame, in coding order, e.g.
#   POC:     4 [INTER][Level:2][Q:160]:   164 Bytes, 10280.7ms  [...] 1280x720
# so progress is the number of such lines seen. (When its output is a pipe
# they arrive in bursts of a few frames, as the C runtime buffers stdout.)
ENC_PROGRESS_RE = re.compile(r"POC:\s+\d+ ")


def run_encoder(cmd, logfile: Path, name: str, progress: Progress) -> float:
    """Run the encoder while streaming its status output: progress is
    parsed as it arrives, only the final status of each line goes to the
    log (instead of thousands of carriage-return updates), and peak memory
    is sampled if psutil is available. Returns peak memory in GB (0 if
    unknown)."""
    peak = 0
    with open(logfile, "a", encoding="utf-8", errors="replace") as f:
        f.write("+ " + " ".join(str(c) for c in cmd) + "\n")
        f.flush()
        p = subprocess.Popen([str(c) for c in cmd], stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT)
        proc = None
        if psutil:
            try:
                proc = psutil.Process(p.pid)
            except psutil.Error:
                pass
        pending = ""
        frames_done = 0
        while True:
            chunk = p.stdout.read1(65536)
            if not chunk:
                break
            pending += chunk.decode("utf-8", errors="replace")
            *lines, pending = pending.split("\n")
            for line in lines:
                if ENC_PROGRESS_RE.match(line):
                    frames_done += 1
                    progress.update(name, frames_done)
                # Strip the CR of a Windows CRLF first; otherwise the "last
                # carriage-return update" of every line would be empty.
                f.write(line.rstrip("\r").rsplit("\r", 1)[-1] + "\n")
            pending = pending.rsplit("\r", 1)[-1]
            f.flush()  # keep the log readable while the encode runs
            if proc:
                try:
                    mi = proc.memory_info()
                    # peak_wset (Windows) also catches peaks between samples
                    peak = max(peak, getattr(mi, "peak_wset", 0), mi.rss)
                except psutil.Error:
                    pass
        if pending.strip():
            f.write(pending + "\n")
        rc = p.wait()
        # Record how the process ended in the log, not only on the console.
        f.write(f"= {describe_exit(rc)}\n")
    if rc != 0:
        raise RuntimeError(f"{Path(str(cmd[0])).name} failed "
                           f"({describe_exit(rc)}); see {logfile}")
    return peak / 1e9


def encode_job(ctx, src: Path, out: Path, qp: int, priority: int):
    jlog = ctx.logs / f"{out.stem}.log"
    name = out.stem
    if out.exists():
        log(f"Skipping encode, {out.name} exists")
        ctx.progress.finish(name)
    else:
        mpix = y4m_megapixels(src)
        total = min(ctx.frames, y4m_frame_count(src))
        held = ctx.budget.acquire(mpix, priority)
        ctx.progress.start(name, total, held)
        log(f"Encoding {out.name} (est. {held:.1f} GB)")
        t0 = time.time()
        ok = False
        tmp = out.with_name(out.name + ".part")
        try:
            fmt =["--obu"] if ctx.container == "obu" else ["--ivf"]
            speed = [] if ctx.cpu_used is None else [f"--cpu-used={ctx.cpu_used}"]
            peak = run_encoder(
                [ctx.enc, src, "-o", tmp, *fmt, f"--limit={ctx.frames}",
                 "--end-usage=q", f"--qp={qp}", *speed, *ctx.extra],
                jlog, name, ctx.progress)
            os.replace(tmp, out)
            ok = True
            el = time.time() - t0
            mem = f", peak {peak:.1f} GB" if peak else ""
            log(f"Encoded {out.name} in {fmt_duration(el)} "
                f"({total / el:.2f} fps{mem})")
            ctx.budget.observe(mpix, peak)
        finally:
            if not ok:
                tmp.unlink(missing_ok=True)  # don't leave partial streams
            ctx.budget.release(held)
            ctx.progress.finish(name, ok)

    # The reference decoder's --md5 hashes the decoded frames directly,
    # avoiding multi-GB raw output files. Compare dav2d against this later.
    stdout = run([ctx.dec, out, "--md5"], jlog, capture=True)
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
    ap.add_argument("--frames", type=int, default=600,
                    help="Frames per encode (65 = one CTC GOP)")
    ap.add_argument("--qp", type=int, nargs="+", default=DEFAULT_QPS,
                    help="Quantizer values; the middle one is encoded first "
                         "for every clip (default: 110 160 210, from the "
                         "AV2 CTC RA set)")
    ap.add_argument("--cpu-used", default="auto",
                    help="Encoder speed preset; higher is faster. 'auto' "
                         "(default) picks one ~2/3 of the way to the fastest "
                         "end of the encoder's good-quality range")
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
    ap.add_argument("--encode-jobs", type=int,
                    default=max(1, (os.cpu_count() or 4) // 2),
                    help="Most encodes running at once; the memory "
                         "budget usually limits further (default: half the "
                         "CPU threads)")
    ap.add_argument("--mem-budget-gb", type=float, default=None,
                    help="Memory the encodes may use together "
                         "(default: 75%% of physical RAM)")
    ap.add_argument("--mem-per-mpix-gb", type=float, default=1.5,
                    help="Starting estimate of encoder memory per megapixel "
                         "(plus 0.5 GB base); refined automatically if "
                         "psutil is installed")
    ap.add_argument("--progress-interval", type=float, default=30,
                    help="Seconds between progress reports")
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

    ram = total_ram_bytes()
    if args.mem_budget_gb:
        budget_gb = args.mem_budget_gb
    elif ram:
        budget_gb = ram / 1e9 * 0.75
    else:
        budget_gb = 16.0
        log("Couldn't detect RAM size; using a 16 GB budget "
            "(set --mem-budget-gb to change)")
    budget = MemoryBudget(budget_gb, 0.5, args.mem_per_mpix_gb,
                          args.encode_jobs)
    progress = Progress(budget)
    log(f"Memory budget for encodes: {budget_gb:.0f} GB"
        f"{f' of {ram / 1e9:.0f} GB' if ram else ''}; up to "
        f"{args.encode_jobs} encodes at once"
        + ("" if psutil else " (pip install psutil for measured, "
                             "self-adjusting memory estimates)"))

    # The middle QP (median of the list) goes first for every clip; the
    # other QPs only start when no middle-QP encode is waiting.
    qps = sorted(dict.fromkeys(args.qp))
    mid_qp = qps[(len(qps) - 1) // 2]
    later = [q for q in qps if q != mid_qp]
    log(f"QPs: {mid_qp} (middle quality) first for every clip"
        + (f", then {', '.join(map(str, later))}" if later else ""))

    results, errors = [], []
    stop_reporter = threading.Event()
    with ThreadPoolExecutor(1) as build_pool, \
         ThreadPoolExecutor(args.download_jobs) as dl_pool, \
         ThreadPoolExecutor(len(clips) * len(qps)) as enc_pool:

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

        # Speed preset. A --cpu-used inside --extra-args takes precedence.
        if any(a.startswith("--cpu-used") for a in extra):
            cpu_used, speed_note = None, "set via --extra-args"
        elif args.cpu_used == "auto":
            cpu_used, rng = pick_cpu_used(enc, logs)
            speed_note = (f"--cpu-used={cpu_used} (auto, from range "
                          f"{rng[0]}..{rng[1]})" if rng else
                          f"--cpu-used={cpu_used} (auto; couldn't read the "
                          f"range from avmenc --help, so using a common "
                          f"middle value)")
        else:
            cpu_used = int(args.cpu_used)
            speed_note = f"--cpu-used={cpu_used}"
        log(f"Encoder speed: {speed_note}")

        ctx = argparse.Namespace(enc=enc, dec=dec, frames=args.frames,
                                 container=args.container, extra=extra,
                                 logs=logs, cpu_used=cpu_used, budget=budget,
                                 progress=progress)
        reporter = threading.Thread(target=progress_reporter, daemon=True,
                                    args=(progress, args.progress_interval,
                                          stop_reporter))
        reporter.start()

        enc_futs = []
        for fut in as_completed(dl_futs):
            clip = dl_futs[fut]
            try:
                src = fut.result()
            except Exception as e:
                errors.append(f"download {clip}: {e}")  # already logged
                continue
            # One thread per encode: threads just wait in the budget queue,
            # which (not the pool) decides order and how many run, so a
            # middle-QP encode submitted later still overtakes queued
            # encodes at other QPs.
            for qp in [mid_qp] + later:
                out = out_dir / (f"{src.stem}_qp{qp}_{args.frames}f"
                                 f".{args.container}")
                progress.add_job()
                enc_futs.append(enc_pool.submit(
                    encode_job, ctx, src, out, qp, 0 if qp == mid_qp else 1))

        for fut in as_completed(enc_futs):
            try:
                results.append(fut.result())
            except Exception as e:
                errors.append(str(e))
                log(f"ERROR: {e}")
        stop_reporter.set()

    results.sort()
    manifest = out_dir / "manifest.txt"
    with open(manifest, "w") as f:
        # Record exactly what produced these streams.
        f.write(f"# AVM commit: {commit}\n")
        f.write(f"# CMake flags: {' '.join(cmake_flags)}\n")
        f.write(f"# frames={args.frames} speed: {speed_note} "
                f"extra_args='{args.extra_args}'\n")
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
