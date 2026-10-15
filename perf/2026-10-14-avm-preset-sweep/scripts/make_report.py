"""Figures, tables and a flat CSV from sweep.jsonl (the raw results).

Self-contained: needs only sweep.jsonl next to this folder, numpy, scipy and
matplotlib. BD-rate and metric definitions are the same as analyze_sweep.py.

  python make_report.py            # writes ../figures/, ../results.csv
                                   # and prints the tables used in README.md
"""
import csv, json, math
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.ticker import FuncFormatter, NullFormatter
from scipy.interpolate import PchipInterpolator

HERE = Path(__file__).resolve().parent.parent
FIG = HERE / "figures"
QPS = (110, 145, 180, 210)
METRICS = [("psnr", "PSNR YUV 6:1:1"), ("ssim", "SSIM-Y (dB)"),
           ("vmaf", "VMAF")]
SHORT = {"FourPeople_480x270_60": "FourPeople 270p",
         "BlueSky_360p25_v2": "BlueSky 360p",
         "Vertical_Bayshore_270x480_2997": "Vertical_Bayshore 270x480",
         "KristenAndSara_1280x720_60": "KristenAndSara 720p",
         "crowd_run_1080p50": "crowd_run 1080p"}
LOWRES = ["FourPeople_480x270_60", "BlueSky_360p25_v2",
          "Vertical_Bayshore_270x480_2997"]
HD = ["KristenAndSara_1280x720_60"]

# Colours: categorical slots for clips (fixed order), a one-hue blue ramp for
# presets (ordinal: s0 darkest = slowest), text in neutral ink.
CLIP_COL = {"FourPeople_480x270_60": "#2a78d6", "BlueSky_360p25_v2": "#eb6834",
            "Vertical_Bayshore_270x480_2997": "#1baf7a",
            "KristenAndSara_1280x720_60": "#6250d6"}
RAMP = ["#0d366b", "#104281", "#184f95", "#1c5cab", "#256abf", "#2a78d6",
        "#3987e5", "#5598e7", "#6da7ec", "#86b6ef"]  # s0 .. s9
INK, INK2, GRID = "#0b0b0b", "#52514e", "#e4e3df"

# SVG: keep text as text; no timestamp, so reruns give identical files.
SVG_META = {"Date": None}
plt.rcParams.update({
    "figure.facecolor": "white", "axes.facecolor": "white",
    "axes.edgecolor": INK2, "axes.labelcolor": INK, "text.color": INK,
    "xtick.color": INK2, "ytick.color": INK2, "axes.grid": True,
    "grid.color": GRID, "grid.linewidth": 0.8, "axes.spines.top": False,
    "axes.spines.right": False, "font.size": 10, "axes.titlesize": 11,
    "svg.fonttype": "none", "svg.hashsalt": "avm-perf",
    "legend.frameon": False, "lines.linewidth": 2, "lines.markersize": 6})


def bd_rate(r1, m1, r2, m2):
    """Bjontegaard delta rate (%) of curve 2 vs curve 1, PCHIP in the
    log-rate domain over the overlapping quality range."""
    lr1, lr2 = np.log10(r1), np.log10(r2)
    m1, m2 = np.asarray(m1, float), np.asarray(m2, float)
    lo, hi = max(m1.min(), m2.min()), min(m1.max(), m2.max())
    if hi <= lo:
        return float("nan")
    xs = np.linspace(lo, hi, 200)
    o1, o2 = np.argsort(m1), np.argsort(m2)
    f1 = PchipInterpolator(m1[o1], lr1[o1])(xs)
    f2 = PchipInterpolator(m2[o2], lr2[o2])(xs)
    return (10 ** (np.trapezoid(f2 - f1, xs) / (hi - lo)) - 1) * 100


def metric(r, name):
    if name == "psnr":
        y, u, v = r["psnr"][:3]
        return (6 * y + u + v) / 8
    if name == "ssim":
        return -10 * math.log10(max(1 - r["quality"]["ssim"][0], 1e-10))
    return r["quality"]["vmaf"]


def gmean(xs):
    return math.exp(np.mean([math.log(x) for x in xs]))


rows = [json.loads(l) for l in (HERE / "sweep.jsonl").read_text().splitlines()
        if l.strip()]
main = [r for r in rows if r["rc"] == 0 and not r["rep"]]
by = defaultdict(dict)  # (clip, preset) -> {qp: row}
for r in main:
    by[(r["clip"], r["preset"])][r["qp"]] = r


def full(c, p):
    return len(by.get((c, p), {})) == len(QPS)


def series(c, p):
    return [by[(c, p)][q] for q in QPS]


def bd(c, p, m, ref):
    a, b = series(c, ref), series(c, p)
    return bd_rate([r["payload"] for r in a], [metric(r, m) for r in a],
                   [r["payload"] for r in b], [metric(r, m) for r in b])


def wall(c, p, kind="all"):
    if kind == "all":
        return sum(r["wall"] for r in series(c, p))
    return sum(ms for r in series(c, p) for t, ms in r["frame_ms"]
               if (t == "KEY") == (kind == "key")) / 1000


def log_x(ax):
    ax.set_xscale("log")
    ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:g}"))
    ax.xaxis.set_minor_formatter(NullFormatter())


# ---- flat CSV of every encode ---------------------------------------------
FIELDS = ["clip", "width", "height", "frames", "qp", "preset", "rep",
          "payload_bytes", "kbps", "psnr_y", "psnr_u", "psnr_v",
          "psnr_yuv611", "ssim_y", "ssim_y_db", "vmaf", "wall_s", "cpu_s",
          "peak_mb", "key_ms", "inter_ms_mean", "key_bytes", "encode_fps"]
with open(HERE / "results.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(FIELDS)
    for r in sorted(rows, key=lambda r: (r["clip"], r["qp"], r["preset"],
                                         r["rep"])):
        fps = {"FourPeople_480x270_60": 60, "BlueSky_360p25_v2": 25,
               "Vertical_Bayshore_270x480_2997": 29.97,
               "KristenAndSara_1280x720_60": 60,
               "crowd_run_1080p50": 50}[r["clip"]]
        inter = [ms for t, ms in r["frame_ms"] if t != "KEY"]
        w.writerow([
            r["clip"], r["w"], r["h"], r["frames"], r["qp"], r["preset"],
            r["rep"], r["payload"],
            round(r["payload"] * 8 / (r["frames"] / fps) / 1000, 2),
            *r["psnr"][:3], round(metric(r, "psnr"), 4),
            r["quality"]["ssim"][0], round(metric(r, "ssim"), 4),
            round(r["quality"]["vmaf"], 3), r["wall"], r["cpu"], r["peak_mb"],
            sum(ms for t, ms in r["frame_ms"] if t == "KEY"),
            round(np.mean(inter), 1),
            sum(b for t, b in r["frame_bytes"] if t == "KEY"),
            round(r["frames"] / r["wall"], 4)])

# ---- tables ---------------------------------------------------------------
print(f"{len(main)} encodes (+{len(rows) - len(main)} repeats)\n")


def group_table(clips, ref, presets):
    print(f"| preset | time vs s{ref} | BD PSNR | BD SSIM | BD VMAF |")
    print("|---|--:|--:|--:|--:|")
    for p in presets:
        t = gmean([wall(c, p) / wall(c, ref) for c in clips])
        bds = [np.mean([bd(c, p, m, ref) for c in clips]) for m, _ in METRICS]
        print(f"| s{p} | {t:.2f}x | " + " | ".join(f"{v:+.1f}%" for v in bds)
              + " |")
    print()


for ref in (1, 6):
    print(f"## low-res (3 clips), ref s{ref}")
    group_table(LOWRES, ref, range(10))
    print(f"## KristenAndSara 720p, ref s{ref}")
    group_table(HD, ref, range(1, 10))

print("## per clip, BD-rate PSNR vs s1 / time vs s1")
clips4 = LOWRES + HD
print("| preset | " + " | ".join(SHORT[c] for c in clips4) + " |")
print("|---|" + "--:|" * len(clips4))
for p in range(10):
    cells = [f"{bd(c, p, 'psnr', 1):+.1f}% / {wall(c, p) / wall(c, 1):.2f}x"
             if full(c, p) else "-" for c in clips4]
    print(f"| s{p} | " + " | ".join(cells) + " |")
print()

print("## seconds per frame (sum of wall over 4 QPs / frames), peak MB")
print("| preset | " + " | ".join(SHORT[c] for c in clips4) + " |")
print("|---|" + "--:|" * len(clips4))
for p in range(10):
    cells = []
    for c in clips4:
        if not full(c, p):
            cells.append("-")
            continue
        rs = series(c, p)
        spf = sum(r["wall"] for r in rs) / sum(r["frames"] for r in rs)
        cells.append(f"{spf:.1f} s / {max(r['peak_mb'] for r in rs):.0f} MB")
    print(f"| s{p} | " + " | ".join(cells) + " |")
print()

print("## time by QP relative to QP 145 (geomean over all complete series)")
for q in QPS:
    xs = [by[k][q]["wall"] / by[k][145]["wall"] for k in by if full(*k)]
    print(f"QP {q}: {gmean(xs):.2f}x (n={len(xs)})")
print()

print("## key / inter frame time vs s1 (geomean over 4 clips; s0: 3 clips)")
for p in range(10):
    cs = [c for c in clips4 if full(c, p)]
    k = gmean([wall(c, p, "key") / wall(c, 1, "key") for c in cs])
    i = gmean([wall(c, p, "inter") / wall(c, 1, "inter") for c in cs])
    ksh = np.mean([wall(c, p, "key") / (wall(c, p, "key")
                                        + wall(c, p, "inter")) for c in cs])
    print(f"s{p}: key {k:.3f} inter {i:.3f} key share of time {ksh:.0%}")
print()

print("## crowd_run 1080p (incomplete): per-QP points")
print("| QP | preset | time (s) | payload (kB) | PSNR-Y | VMAF |")
print("|--:|---|--:|--:|--:|--:|")
for r in sorted((r for r in main if r["clip"] == "crowd_run_1080p50"),
                key=lambda r: (r["qp"], r["preset"])):
    print(f"| {r['qp']} | s{r['preset']} | {r['wall']:.0f} | "
          f"{r['payload'] / 1000:.0f} | {r['psnr'][0]:.2f} | "
          f"{r['quality']['vmaf']:.2f} |")
print()

print("## repeated encodes")
for r in rows:
    if r["rep"]:
        r0 = by[(r["clip"], r["preset"])][r["qp"]]
        print(f"{r['clip']} QP {r['qp']} s{r['preset']}: {r0['wall']:.1f} s "
              f"-> {r['wall']:.1f} s ({r['wall'] / r0['wall'] - 1:+.1%})")

# ---- figure 1: speed vs BD-rate, one line per clip --------------------------
FIG.mkdir(exist_ok=True)
fig, axes = plt.subplots(1, 3, figsize=(15, 5.2))
for ax, (m, label) in zip(axes, METRICS):
    for c in clips4:
        ps = [p for p in range(10) if full(c, p)]
        xs = [wall(c, p) / wall(c, 1) for p in ps]
        ys = [bd(c, p, m, 1) for p in ps]
        ax.plot(xs, ys, "-o", color=CLIP_COL[c], label=SHORT[c],
                mec="white", mew=1.2, zorder=3)
    # preset labels above the highest clip; s7 and s8 sit between s6 and
    # s9 and would collide
    for p in (0, 1, 2, 3, 4, 5, 6, 9):
        cs = [c for c in clips4 if full(c, p)]
        x = gmean([wall(c, p) / wall(c, 1) for c in cs])
        y = max(bd(c, p, m, 1) for c in cs)
        ax.annotate(f"s{p}", (x, y), xytext=(0, 7), textcoords="offset points",
                    ha="center", fontsize=9, color=INK2)
    ax.axhline(0, color=INK2, lw=0.8, zorder=1)
    log_x(ax)
    ax.set_xlabel("encode time relative to s1 (log)")
    ax.set_title(f"BD-rate vs s1, {label}", loc="left")
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:+.0f}%"))
axes[0].legend(loc="upper right")
fig.suptitle("AVM av2-enc: encode time vs bitrate cost of each --cpu-used "
             "preset (lower left is better)", x=0.01, ha="left",
             fontsize=12)
fig.tight_layout()
fig.savefig(FIG / "speed_vs_bdrate.svg", metadata=SVG_META)
plt.close(fig)

# ---- figure 2: seconds per frame per preset ---------------------------------
fig, ax = plt.subplots(figsize=(8, 4.8))
for c in clips4:
    ps = [p for p in range(10) if full(c, p)]
    spf = [sum(r["wall"] for r in series(c, p))
           / sum(r["frames"] for r in series(c, p)) for p in ps]
    ax.plot(ps, spf, "-o", color=CLIP_COL[c], label=SHORT[c], mec="white",
            mew=1.2)
    ax.annotate(SHORT[c], (ps[-1], spf[-1]), xytext=(6, 0),
                textcoords="offset points", va="center", fontsize=9,
                color=INK)
ax.set_yscale("log")
ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:g}"))
ax.set_xticks(range(10), [f"s{p}" for p in range(10)])
ax.set_xlim(-0.3, 12.5)
ax.set_xlabel("--cpu-used preset")
ax.set_ylabel("seconds per frame (log)")
ax.set_title("Encode time per frame, 1 thread, mean over QP 110-210",
             loc="left")
ax.legend(loc="upper right")
fig.tight_layout()
fig.savefig(FIG / "seconds_per_frame.svg", metadata=SVG_META)
plt.close(fig)

# ---- figure 3: key vs inter frame speedup -----------------------------------
fig, ax = plt.subplots(figsize=(8, 4.8))
for kind, col, name in (("key", "#eb6834", "keyframe"),
                        ("inter", "#2a78d6", "inter frames")):
    ps, ys = [], []
    for p in range(10):
        cs = [c for c in clips4 if full(c, p)]
        ps.append(p)
        ys.append(gmean([wall(c, p, kind) / wall(c, 1, kind) for c in cs]))
    ax.plot(ps, ys, "-o", color=col, label=name, mec="white", mew=1.2)
    ax.annotate(name, (ps[-1], ys[-1]), xytext=(6, 0),
                textcoords="offset points", va="center", fontsize=9)
ax.set_yscale("log")
ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:g}"))
ax.set_xticks(range(10), [f"s{p}" for p in range(10)])
ax.set_xlim(-0.3, 10.5)
ax.set_xlabel("--cpu-used preset")
ax.set_ylabel("time relative to s1 (log)")
ax.set_title("Keyframe vs inter-frame encode time (geomean over 4 clips)",
             loc="left")
ax.legend(loc="upper right")
fig.tight_layout()
fig.savefig(FIG / "key_vs_inter_time.svg", metadata=SVG_META)
plt.close(fig)

# ---- figure 4: RD curves per clip -------------------------------------------
for c in clips4:
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.6))
    for ax, (m, label) in zip(axes, METRICS):
        for p in range(10):
            if not full(c, p):
                continue
            rs = series(c, p)
            ax.plot([r["payload"] * 8 / r["frames"] / 1000 for r in rs],
                    [metric(r, m) for r in rs], "-o", color=RAMP[p],
                    lw=2.6 if p in (1, 6) else 1.3, ms=4,
                    label=f"s{p}" + {0: " (default)", 1: " (BD ref)",
                                     6: " (fastest)"}.get(p, ""))
        log_x(ax)
        ax.set_xlabel("kbit per frame (log)")
        ax.set_title(label, loc="left")
    axes[0].legend(fontsize=8, ncol=2)
    fig.suptitle(f"RD curves, {SHORT[c]} ({series(c, 1)[0]['frames']} "
                 f"frames, QP 110/145/180/210)", x=0.01, ha="left",
                 fontsize=12)
    fig.tight_layout()
    fig.savefig(FIG / f"rd_{c}.svg", metadata=SVG_META)
    plt.close(fig)
print(f"\nwrote {FIG} and {HERE / 'results.csv'}")
