#!/usr/bin/env python3
"""
Long HD AV2 encodes: an open-ended queue meant to run overnight (or longer)
until it is stopped.

Encodes full-length 720p/1080p clips (capped at 600 frames) in tiers:
  1. QP 135 (a CTC point; roughly VMAF 92-98 at s6), the HD clips of the
     main sample set, plus HD streams that use specific coding tools
     (screen content tuning, film grain, global motion, HDR10, tiles)
  2. QP 135, about 40 more CTC clips (720p, 1080p, 2K)
  3. QP 110, a low-delay stream, and the 1080p clips at the slower
     preset s3 (uses more coding tools)
Tier 1 starts its slowest encodes first, so they finish; tiers 2 and 3
start their cheapest first, to get as many streams as possible. An encode
only starts once every source of the tiers before it has downloaded, so
queue order holds. Each encode is one thread;
--jobs of them run at once, and a new one only starts when there is enough
free memory.

Reuses encode_samples.py for the AVM build and the source downloads, so run
it from this folder. Each finished stream is verified with avmdec --md5 and
its manifest row is written right away, so stopping at any point loses only
the encodes that are still running.

Stopping:
  * Create a file named STOP in the work folder: no new encodes start, the
    running ones finish.
  * Or kill it (and its avmenc processes). Then run with --finalize to cut
    each unfinished .part file back to its last complete frame, verify it
    and keep it in partial/. A normal run does this first as well.
A rerun skips streams that are already in the manifest. Unfinished encodes
start again from frame 0 (avmenc can't resume).

Usage:
    python encode_long.py                # build (if needed) and encode
    python encode_long.py --list         # show the queue, don't encode
    python encode_long.py --finalize     # salvage partial encodes only
"""
import argparse
import os
import re
import struct
import subprocess
import sys
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

import psutil

from encode_samples import (_paths, build_avm, check_tools, download,
                            fmt_duration, log, run_encoder, Progress,
                            MemoryBudget, progress_reporter, y4m_frame_count,
                            y4m_tags)

MAX_FRAMES = 600


@dataclass
class Stream:
    clip: str
    paths: list
    qp: int = 135
    tag: str = ""        # what the stream covers; part of the file name
    args: list = field(default_factory=list)
    speed: int = 6       # s6 is the fastest preset (perf/2026-10-14-...)
    tier: int = 1
    note: str = ""

    @property
    def stem(self):
        tag = f"_{self.tag}" if self.tag else ""
        spd = "" if self.speed == 6 else f"_s{self.speed}"
        return f"{self.clip}{tag}_qp{self.qp}{spd}"


def long_(cls, name):
    return _paths(cls, name)  # test_set_long first, then test_set


def short(cls, name):
    return _paths(cls, name, ("test_set",))


# (clip, paths): natural content, encoded at every QP.
A3_720P = [(n, long_("a3_720p", n)) for n in (
    "KristenAndSara_1280x720_60", "vidyo4_720p_60fps",
    "Netflix_DrivingPOV_720p_60fps_10bit_420")]
A2_1080P = [(n, long_("a2_2k", n)) for n in (
    "crowd_run_1080p50", "old_town_cross_1080p50",
    "RitualDance_1920x1080_60fps_10bit_420",
    "TunnelFlag_1920x1080_60fps_10bit_420", "Vertical_bees_2997_1080x1920")]
OTHER_1080P = [
    ("MINECRAFT_1080p_60_8bit", long_("b1_syn", "MINECRAFT_1080p_60_8bit")),
    ("SolLevanteDragons_sdr_1920x1080_24_10bit",
     short("b1_syn", "SolLevanteDragons_sdr_1920x1080_24_10bit")),
    ("Noise_Ocean_1920x1080_60fps",
     short("e_nonpristine", "Noise_Ocean_1920x1080_60fps")),
]
SCREEN = ["--tune-content=screen"]
SCREEN_CLIPS = [(n, short("b2_scc", n)) for n in (
    "Debugging_1920x1080_30fps_8bit_420", "Slides1_1920x1080_30fps_8bit_420",
    "Wikipedia_1920x1080p30")]

# Streams for specific coding tools (from the coverage experiments).
TOOLS = [
    Stream("Noise_Ocean_1920x1080_60fps",
           short("e_nonpristine", "Noise_Ocean_1920x1080_60fps"),
           tag="filmgrain", args=["--denoise-noise-level=25"],
           note="Denoised, with film grain parameters estimated from the "
                "noise"),
    Stream("Shaky_Walk_1920x1080_25fps",
           short("e_nonpristine", "Shaky_Walk_1920x1080_25fps"),
           tag="globalmotion", args=["--enable-global-motion=1"],
           note="Handheld camera, global motion on (off by default)"),
    Stream("CosmosTreeTrunk_2048x858p24_hdr10",
           short("hdr2_2k", "CosmosTreeTrunk_2048x858p24_hdr10"), tag="hdr10",
           args=["--color-primaries=bt2020",
                 "--transfer-characteristics=smpte2084",
                 "--matrix-coefficients=bt2020ncl"],
           note="HDR10 (PQ, BT.2020) signaled; 2048x858"),
    Stream("old_town_cross_1080p50", long_("a2_2k", "old_town_cross_1080p50"),
           tag="tiles4x2",
           args=["--tile-columns=2", "--tile-rows=1", "--num-tile-groups=4"],
           note="4x2 tiles in 4 tile groups (parallel decoding)"),
]


def both(cls, long_name, short_name):
    """A clip whose test_set_long and test_set files are named differently."""
    return [f"test_set_long/{cls}/{long_name}", f"test_set/{cls}/{short_name}"]


HDR10 = ["--color-primaries=bt2020", "--transfer-characteristics=smpte2084",
         "--matrix-coefficients=bt2020ncl"]

# Clips not in the main sample set yet (tier 2). Full length where
# test_set_long has the clip, else the 130-frame test_set version.
NEW = [
    ("Aerial3200_1920x1080_5994_10bit_420",
     long_("a2_2k", "Aerial3200_1920x1080_5994_10bit_420")),
    ("Boat_1920x1080_60fps_10bit_420",
     both("a2_2k", "Boat_1920x1080_60fps_10bit_420",
          "Boat_1920x1080_5994_10bit_420")),
    ("FoodMarket_1920x1080_60fps_10bit_420",
     both("a2_2k", "FoodMarket_1920x1080_60fps_10bit_420",
          "FoodMarket_1920x1080_5994_10bit_420")),
    ("Skater227_1920x1080_30fps", long_("a2_2k", "Skater227_1920x1080_30fps")),
    ("WorldCup_1920x1080_30p", long_("a2_2k", "WorldCup_1920x1080_30p")),
    ("WorldCup_far_1920x1080_30p",
     long_("a2_2k", "WorldCup_far_1920x1080_30p")),
    ("Vertical_Carnaby_5994_1080x1920",
     both("a2_2k", "Vertical_Carnaby_5994_1080x1920",
          "Vertical_Carnaby_1080x1920_5994")),
    ("pedestrian_area_1080p25",
     both("a2_2k", "pedestrian_area_1080p25", "PedestrianArea_1920x1080p25")),
    ("riverbed_1080p25",
     both("a2_2k", "riverbed_1080p25", "Riverbed_1920x1080p25")),
    ("rush_field_cuts_1080p",
     both("a2_2k", "rush_field_cuts_1080p", "RushFieldCuts_1920x1080_2997")),
    ("Meridian_talk_sdr_1080p_10bit",
     both("a2_2k", "Meridian_talk_sdr_1080p_10bit",
          "MeridianTalk_sdr_1920x1080p_5994_10bit")),
] + [(n, short("a2_2k", n)) for n in (
    "Motorcycle_1920x1080_30fps_8bit", "MountainBike_1920x1080_30fps_8bit",
    "ToddlerFountain_1920x1080_2997fps_10bit_420",
    "TreesAndGrass_1920_1080_30fps_8bit",
    "DinnerSceneCropped_1920x1080_2997fps_10bit_420")] + [
    ("Johnny_1280x720_60", long_("a3_720p", "Johnny_1280x720_60")),
    ("Netflix_RollerCoaster_720p_60fps_10bit_420",
     both("a3_720p", "Netflix_RollerCoaster_720p_60fps_10bit_420",
          "RollerCoaster_1280x720p_5994_10bit_420")),
    ("controlled_burn_720p_420",
     both("a3_720p", "controlled_burn_720p_420",
          "ControlledBurn_1280x720p30_420")),
    ("vidyo3_720p_60fps",
     both("a3_720p", "vidyo3_720p_60fps", "Vidyo3_1280x720p_60fps")),
    ("west_wind_easy_720p_420",
     both("a3_720p", "west_wind_easy_720p_420",
          "WestWindEasy_1280x720p30_420")),
] + [(n, short("b1_syn", n)) for n in (
    "DOTA2_1920x1080_60_8bit_420", "EuroTruckSimulator2_1920x1080p60",
    "GlassHalf_1920x1080p_24p_8bit_420", "Life_1080p30",
    "STARCRAFT_1080p60", "Sniper_1920x1080P_30fps_8bit",
    "WITCHER3_1920x1080_60_8bit_420",
    "SolLevanteFace_sdr_1920x1080_24_10bit")] + [
    (n, short("e_nonpristine", n)) for n in (
        "Artistic_Concert_1920x1080_25fps", "Artistic_Intro_1920x1080_2997fps",
        "MixedCoding_NewsIntroAnchor_1280x720_2997fps",
        "Noise_AnimationCrayon_1920x1080_2398fps",
        "Noise_Soccer_1920x1080_50fps")]
NEW_SCREEN = [(n, short("b2_scc", n)) for n in (
    "BigBuckBunnyStudio1_1920x1080_60fps_10bit_420_020_0149",
    "MissionControlClip1_1920x1080_60fps_10bit_420_0450_0579",
    "MissionControlClip3_1920x1080_60_420", "MobileDeviceScreenSharing",
    "SceneComposition_1", "SceneComposition_2",
    "Slides2r_1920x1080_30fps_8bit_420",
    "Spreadsheet_1920x1080_30fps_8bit_420_130f")]
NEW_HDR = [(n, short("hdr2_2k", n)) for n in (
    "CosmosCaterpillar_2048x858p24_hdr10", "MeridianShore_1920x1080_5994_hdr10",
    "MeridianTalk_1920x1080_5994_hdr10", "SparksTruck_2048x1080_5994_hdr10",
    "SolLevanteDragons_1920x1080p24_hdr10")]


def plan():
    """The queue in order. Tier 1 runs slowest first (so the long encodes
    finish), tiers 2 and 3 cheapest first (as many streams as possible)."""
    natural = A3_720P + A2_1080P + OTHER_1080P
    t1 = [Stream(c, p, 135) for c, p in natural]
    t1 += [Stream(c, p, 135, "screen", SCREEN,
                  note="Screen content tuning (palette, IntraBC)")
           for c, p in SCREEN_CLIPS]
    t1 += TOOLS
    t2 = [Stream(c, p, 135, tier=2) for c, p in NEW]
    t2 += [Stream(c, p, 135, "screen", SCREEN, tier=2,
                  note="Screen content tuning") for c, p in NEW_SCREEN]
    t2 += [Stream(c, p, 135, "hdr10", HDR10, tier=2,
                  note="HDR10 signaled") for c, p in NEW_HDR]
    t2.append(Stream("Shaky_Quad_1920x1080_30fps",
                     short("e_nonpristine", "Shaky_Quad_1920x1080_30fps"),
                     135, "globalmotion", ["--enable-global-motion=1"], tier=2))
    t3 = [Stream("KristenAndSara_1280x720_60",
                 long_("a3_720p", "KristenAndSara_1280x720_60"), 135,
                 "lowdelay", ["--lag-in-frames=0"], tier=3,
                 note="Low delay: no lookahead or frame reordering")]
    t3 += [Stream(c, p, 110, tier=3) for c, p in natural + NEW]
    t3 += [Stream(c, p, 135, speed=3, tier=3) for c, p in A2_1080P]
    t1.sort(key=lambda s: -guess_cost(s))
    t2.sort(key=guess_cost)
    t3.sort(key=guess_cost)
    return t1 + t2 + t3


QP_COST = {110: 1.4, 135: 1.0}


def guess_cost(s: Stream) -> float:
    """Relative encode time, from the clip name alone (before download)."""
    n = s.clip + " ".join(s.paths)
    c = QP_COST.get(s.qp, 1.0) * (2.4 if s.speed == 3 else 1.0)
    c *= 1.8 if re.search(r"10bit|10b|hdr", n) else 1.0
    c *= 0.45 if re.search(r"720", n) else 1.0
    # test_set_long clips are up to 600 frames, test_set ones 130.
    return c * (4.5 if s.paths[0].startswith("test_set_long") else 1.0)


# --------------------------------------------------------------------------
# IVF helpers: cut a partial file back to its last complete frame.
# --------------------------------------------------------------------------
def ivf_truncate(path: Path) -> int:
    """Drop a trailing incomplete frame; returns the number of frames."""
    data_len = path.stat().st_size
    with open(path, "r+b") as f:
        hdr = f.read(32)
        if len(hdr) < 32 or hdr[:4] != b"DKIF":
            return 0
        pos, n = 32, 0
        while True:
            f.seek(pos)
            fh = f.read(12)
            if len(fh) < 12:
                break
            size = struct.unpack("<I", fh[:4])[0]
            if pos + 12 + size > data_len:
                break
            pos += 12 + size
            n += 1
        f.truncate(pos)
    return n


# --------------------------------------------------------------------------
# Verify and record
# --------------------------------------------------------------------------
MANIFEST_HEADER = ("# file\tbytes\tmd5(decoded, avmdec --md5)\t"
                   "encoder settings\tencode time (s)\tpeak memory (GB)\n")
_manifest_lock = threading.Lock()


def verify(dec: Path, path: Path, jlog: Path):
    """Decode with avmdec; returns (md5, shown frames)."""
    r = subprocess.run([str(dec), str(path), "--md5", "--summary"],
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                       text=True, errors="replace")
    with open(jlog, "a", encoding="utf-8") as f:
        f.write(f"+ avmdec --md5 --summary {path.name}\n{r.stdout}"
                f"= exit {r.returncode}\n")
    md5 = re.search(r"\b[0-9a-f]{32}\b", r.stdout)
    shown = re.search(r"(\d+) decoded frames/(\d+) showed frames", r.stdout)
    if r.returncode or not (md5 and shown):
        raise RuntimeError(f"avmdec failed on {path.name}; see {jlog}")
    return md5[0], int(shown[2])


def append_manifest(manifest: Path, row):
    with _manifest_lock:
        with open(manifest, "a", encoding="utf-8") as f:
            f.write("\t".join(str(x) for x in row) + "\n")


def read_manifest(manifest: Path) -> dict:
    """Stem (name without the frame count) -> row."""
    done = {}
    if manifest.exists():
        for line in manifest.read_text(encoding="utf-8").splitlines():
            if line and not line.startswith("#"):
                name = line.split("\t")[0]
                done[re.sub(r"_\d+f\.ivf$", "", name)] = line
    return done


def init_manifest(manifest: Path, commit: str, flags: list):
    if not manifest.exists():
        manifest.write_text(f"# AVM commit: {commit}\n"
                            f"# CMake flags: {' '.join(flags)}\n"
                            + MANIFEST_HEADER, encoding="utf-8")


def finalize(ctx):
    """Salvage .part files left by a killed run into partial/."""
    for part in sorted(ctx.out.glob("*.ivf.part")):
        stem = part.name[:-len(".ivf.part")]
        jlog = ctx.logs / f"{stem}.log"
        n = ivf_truncate(part)
        if n == 0:
            log(f"Removing empty {part.name}")
            part.unlink()
            continue
        try:
            md5, shown = verify(ctx.dec, part, jlog)
        except RuntimeError as e:
            log(f"Keeping {part.name} as is: {e}")
            continue
        final = ctx.partial / f"{stem}_{shown}f.ivf"
        os.replace(part, final)
        append_manifest(ctx.partial / "manifest.txt",
                        (final.name, final.stat().st_size, md5,
                         "partial (encode stopped)", "", ""))
        log(f"Salvaged {final.name} ({shown} frames)")


# --------------------------------------------------------------------------
# Encode
# --------------------------------------------------------------------------
def encode(ctx, s: Stream, rank: int, src_fut, earlier: list):
    # Wait for the sources of all earlier tiers too, so a stream whose
    # source happens to be on disk already can't jump ahead of a tier.
    for f in earlier:
        try:
            f.result()
        except Exception:
            pass  # that stream is skipped; logged by download()
    src = src_fut.result()  # this clip's download
    with open(src, "rb") as f:
        tags = y4m_tags(f.readline())
    mpix = int(tags["W"]) * int(tags["H"]) / 1e6
    frames = min(MAX_FRAMES, y4m_frame_count(src))
    jlog = ctx.logs / f"{s.stem}.log"
    tmp = ctx.out / f"{s.stem}.ivf.part"
    # Queue position is the priority: a stream whose source arrives late
    # still goes before the later ones.
    held = ctx.budget.acquire(mpix, rank)
    try:
        if ctx.stop.exists():
            log(f"STOP file found, not starting {s.stem}")
            return
        # Leave headroom for everything else on the machine.
        while psutil.virtual_memory().available < 3e9 + held * 1e9:
            time.sleep(30)
        jlog.unlink(missing_ok=True)
        settings = (f"--end-usage=q --qp={s.qp} --cpu-used={s.speed} "
                    f"--threads=1 {' '.join(s.args)}").strip()
        ctx.progress.start(s.stem, frames, held)
        log(f"Encoding {s.stem}: {frames} frames, {settings}")
        t0 = time.time()
        ok = False
        try:
            peak = run_encoder(
                [ctx.enc, src, "-o", tmp, "--ivf", f"--limit={frames}",
                 "--end-usage=q", f"--qp={s.qp}", f"--cpu-used={s.speed}",
                 "--threads=1", *s.args], jlog, s.stem, ctx.progress)
            ok = True
        finally:
            ctx.progress.finish(s.stem, ok)
        el = time.time() - t0
        md5, shown = verify(ctx.dec, tmp, jlog)
        if shown != frames:
            raise RuntimeError(f"{s.stem}: decoded {shown} frames, "
                               f"expected {frames}")
        final = ctx.out / f"{s.stem}_{shown}f.ivf"
        os.replace(tmp, final)
        append_manifest(ctx.manifest, (final.name, final.stat().st_size, md5,
                                       settings, f"{el:.0f}", f"{peak:.2f}"))
        ctx.budget.observe(mpix, peak)
        log(f"Encoded {final.name} in {fmt_duration(el)} "
            f"({frames / el:.3f} fps, peak {peak:.1f} GB, "
            f"{final.stat().st_size / 1024:.0f} KiB)")
    finally:
        ctx.budget.release(held)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--workdir", default="av2_work/hd_long")
    ap.add_argument("--sources", default="av2_work/sources",
                    help="Source clip folder (shared with encode_samples.py)")
    ap.add_argument("--jobs", type=int, default=14,
                    help="Encodes at once, one thread each (default 14: "
                         "one per physical core, see perf/2026-10-15-...)")
    ap.add_argument("--mem-budget-gb", type=float, default=26)
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--finalize", action="store_true",
                    help="Only salvage partial encodes, then exit")
    args = ap.parse_args()

    queue = plan()
    if args.list:
        for s in queue:
            print(f"tier {s.tier}  {s.stem:60s} {s.note}")
        return

    check_tools()
    work = Path(args.workdir).resolve()
    sources = Path(args.sources).resolve()
    out, partial, logs = work / "encoded", work / "partial", work / "logs"
    for d in (out, partial, logs, sources):
        d.mkdir(parents=True, exist_ok=True)
    enc, dec, commit, flags = build_avm(work, None, os.cpu_count() or 4,
                                        logs, [])
    log(f"AVM {commit[:12]}: {enc}")
    manifest = out / "manifest.txt"
    init_manifest(manifest, commit, flags)
    init_manifest(partial / "manifest.txt", commit, flags)
    budget = MemoryBudget(args.mem_budget_gb, 0.5, 0.6, args.jobs)
    ctx = argparse.Namespace(enc=enc, dec=dec, out=out, partial=partial,
                             logs=logs, manifest=manifest,
                             stop=work / "STOP", budget=budget,
                             progress=Progress(budget))
    finalize(ctx)
    if args.finalize:
        return

    done = read_manifest(manifest)
    queue = [s for s in queue if s.stem not in done]
    log(f"{len(done)} streams already done, {len(queue)} to encode")

    stop_rep = threading.Event()
    threading.Thread(target=progress_reporter, daemon=True,
                     args=(ctx.progress, 600, stop_rep)).start()
    errors = []
    # Downloads run in queue order, each clip once (as many frames as any
    # stream needs); each encode starts once its own clip is there. The
    # budget, not the pool size, decides how many encodes run at once.
    with ThreadPoolExecutor(6) as dl_pool, \
         ThreadPoolExecutor(len(queue) or 1) as pool:
        # Clips already complete on disk are ready at once; the others
        # download smallest first within the earliest tier, so encodes can
        # start soon.
        first = {}
        for s in queue:
            first.setdefault(s.clip, s)
        srcs = {}
        for c, s in sorted(first.items(),
                           key=lambda kv: (kv[1].tier, guess_cost(kv[1]))):
            y4m = sources / f"{c}.y4m"
            if y4m.exists() and (
                    y4m.with_name(y4m.name + ".whole").exists()
                    or y4m_frame_count(y4m) >= MAX_FRAMES):
                srcs[c] = Future()
                srcs[c].set_result(y4m)
            else:
                srcs[c] = dl_pool.submit(download, c, s.paths, sources,
                                         MAX_FRAMES)
        futs = {}
        for rank, s in enumerate(queue):
            ctx.progress.add_job()
            earlier = {srcs[e.clip] for e in queue if e.tier < s.tier}
            futs[pool.submit(encode, ctx, s, rank, srcs[s.clip],
                             list(earlier))] = s
        for f, s in futs.items():
            try:
                f.result()
            except Exception as e:
                errors.append(f"{s.stem}: {e}")
                log(f"ERROR {s.stem}: {e}")
    stop_rep.set()
    log(f"Queue finished. Manifest: {manifest}")
    if errors:
        print(f"\n{len(errors)} failure(s):\n  " + "\n  ".join(errors))
        sys.exit(1)


if __name__ == "__main__":
    main()
