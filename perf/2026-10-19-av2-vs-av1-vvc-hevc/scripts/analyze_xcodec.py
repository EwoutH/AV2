"""Analyze the cross-codec run: BD-rate and encode time of every encoder
config against an anchor, per clip and per clip group, plus figures.

Inputs: sweep.jsonl (AVM presets on the sweep clips) and xcodec_main.jsonl.
Output: xcodec_report/summary.txt, results.csv, figures/*.svg.

  python analyze_xcodec.py [--anchor aom:0]
"""
import argparse, csv, json, math
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker
import numpy as np
from scipy.interpolate import PchipInterpolator

from nal_sizes import SEI, nal_types

HERE = Path(__file__).resolve().parent
OUT = HERE / "xcodec_report"

GROUPS = {
    "lowres": ["FourPeople_480x270_60", "BlueSky_360p25_v2",
               "Vertical_Bayshore_270x480_2997"],
    "720p": ["KristenAndSara_1280x720_60"],
    "1080p": ["crowd_run_1080p50", "Motorcycle_1920x1080_30fps_8bit",
              "GlassHalf_1920x1080p_24p_8bit_420",
              "EuroTruckSimulator2_1920x1080p60",
              "Debugging_1920x1080_30fps_8bit_420"],
    # every config ran on crowd_run; the slowest ones only there
    "1080p crowd_run": ["crowd_run_1080p50"],
}
FRAMES = {c: (65 if c.startswith("Kristen") else 33)
          for g in GROUPS.values() for c in g}
SHORT = {"FourPeople_480x270_60": "FourPeople", "BlueSky_360p25_v2": "BlueSky",
         "Vertical_Bayshore_270x480_2997": "Vertical_Bayshore",
         "KristenAndSara_1280x720_60": "KristenAndSara",
         "crowd_run_1080p50": "crowd_run",
         "Motorcycle_1920x1080_30fps_8bit": "Motorcycle",
         "GlassHalf_1920x1080p_24p_8bit_420": "GlassHalf",
         "EuroTruckSimulator2_1920x1080p60": "EuroTruck",
         "Debugging_1920x1080_30fps_8bit_420": "Debugging"}

# codec -> (label, colour, marker); colours: validated categorical slots 1-6
CODEC = {"avm": ("AVM (AV2)", "#2a78d6", "o"),
         "aom": ("libaom (AV1)", "#eb6834", "s"),
         "svt": ("SVT-AV1", "#1baf7a", "D"),
         "vvenc": ("VVenC (VVC)", "#eda100", "^"),
         "x265": ("x265 (HEVC)", "#e87ba4", "v"),
         "x264": ("x264 (AVC)", "#008300", "P")}
VVENC_NAME = {"4": "slower", "3": "slow", "2": "medium", "1": "fast",
              "0": "faster"}
INK, INK2, GRID = "#0b0b0b", "#52514e", "#e4e3df"
METRICS = ["psnr", "ssim", "vmaf"]
MNAME = {"psnr": "PSNR-YUV", "ssim": "SSIM-Y (dB)", "vmaf": "VMAF"}


def label(codec, preset):
    p = str(preset)
    if codec == "avm":
        return f"AVM s{p}"
    if codec == "aom":
        return f"libaom cpu{p}"
    if codec == "svt":
        return f"SVT-AV1 p{p}"
    if codec == "vvenc":
        return f"VVenC {VVENC_NAME[p]}"
    return f"{codec} {p}"


# ---- load ------------------------------------------------------------------
def load():
    pts = defaultdict(list)  # (clip, codec, preset) -> [point]
    for line in open(HERE / "sweep.jsonl"):
        r = json.loads(line)
        q = r.get("quality") or {}
        if r["rep"] or r["rc"] or q.get("vmaf") is None:
            continue
        if r["frames"] != FRAMES.get(r["clip"]):
            continue
        pts[(r["clip"], "avm", str(r["preset"]))].append(dict(
            q=r["qp"], bytes=r["payload"], wall=r["wall"],
            psnr=r["psnr"][:3], ssim=q["ssim"], vmaf=q["vmaf"]))
    xf = HERE / "xcodec_main.jsonl"
    for line in (open(xf) if xf.exists() else []):
        r = json.loads(line)
        if r["rc"] or r.get("vmaf") is None or r.get("dec_frames") != r["frames"]:
            continue
        key = (r["clip"], r["codec"], str(r["preset"]))
        if any(p["q"] == r["q"] for p in pts[key]):
            continue
        pts[key].append(dict(q=r["q"], bytes=payload(r), wall=r["wall"],
                             psnr=r["psnr"], ssim=r["ssim"], vmaf=r["vmaf"]))
    return pts


EXT = {"x264": ".h264", "x265": ".hevc", "vvenc": ".266"}


def payload(r):
    """Rate in bytes. IVF: frame payloads. Annex-B: the stream without SEI
    NAL units (x264 and x265 write their whole option string into an SEI,
    0.7-2.3 kB, which is a large share of a small 33-frame stream)."""
    ext = EXT.get(r["codec"])
    if not ext:
        return r["payload"]
    f = (HERE / "xcodec_out" / f"{r['clip']}_{r['codec']}_p{r['preset']}_"
         f"q{r['q']}_{r['frames']}f{ext}")
    c = nal_types(f)
    return sum(v for k, v in c.items() if k not in SEI[ext])


def mval(p, m):
    if m == "psnr":
        y, u, v = p["psnr"][:3]
        return (6 * y + u + v) / 8
    if m == "ssim":
        return -10 * math.log10(max(1 - p["ssim"][0], 1e-10))
    return p["vmaf"]


def curve(ps, m):
    """Monotone RD curve: points sorted by rate, keeping only points that
    improve quality (drops non-monotone points at the extremes, e.g. VMAF
    saturating near 100)."""
    s = sorted(ps, key=lambda p: p["bytes"])
    out = []
    for p in s:
        if not out or mval(p, m) > mval(out[-1], m) + 1e-9:
            out.append(p)
    return out


def bd_rate(a, b, m, min_overlap=0.5):
    """BD-rate (%) of b vs a (PCHIP, log rate) over the overlap of their
    quality ranges; nan if the overlap is under min_overlap of a's range."""
    ca, cb = curve(a, m), curve(b, m)
    if len(ca) < 3 or len(cb) < 3:
        return float("nan")
    ma = np.array([mval(p, m) for p in ca]); mb = np.array([mval(p, m) for p in cb])
    lo, hi = max(ma.min(), mb.min()), min(ma.max(), mb.max())
    if hi <= lo or (hi - lo) < min_overlap * (ma.max() - ma.min()):
        return float("nan")
    xs = np.linspace(lo, hi, 200)
    fa = PchipInterpolator(ma, np.log10([p["bytes"] for p in ca]))(xs)
    fb = PchipInterpolator(mb, np.log10([p["bytes"] for p in cb]))(xs)
    return (10 ** (np.trapezoid(fb - fa, xs) / (hi - lo)) - 1) * 100


def time_ratio(a, b, m="psnr"):
    """Encode time of b / a at equal quality: log(wall) interpolated against
    quality at 5 levels across the common range, geometric mean."""
    ca, cb = curve(a, m), curve(b, m)
    ma = np.array([mval(p, m) for p in ca]); mb = np.array([mval(p, m) for p in cb])
    lo, hi = max(ma.min(), mb.min()), min(ma.max(), mb.max())
    if hi <= lo:
        return float("nan")
    xs = np.linspace(lo, hi, 7)[1:-1]
    ta = np.interp(xs, ma, np.log([p["wall"] for p in ca]))
    tb = np.interp(xs, mb, np.log([p["wall"] for p in cb]))
    return float(np.exp(np.mean(tb - ta)))


def gmean(xs):
    xs = [x for x in xs if x == x]
    return math.exp(np.mean(np.log(xs))) if xs else float("nan")


def amean(xs):
    xs = [x for x in xs if x == x]
    return float(np.mean(xs)) if xs else float("nan")


# ---- report ----------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--anchor", default="aom:1")
    a = ap.parse_args()
    anc = tuple(a.anchor.split(":"))
    pts = load()
    OUT.mkdir(exist_ok=True)
    (OUT / "figures").mkdir(exist_ok=True)
    configs = sorted({(c, p) for (_, c, p) in pts},
                     key=lambda k: (list(CODEC).index(k[0]),
                                    {"placebo": -2, "veryslow": -1}.get(k[1], 0)
                                    if k[0] in ("x264", "x265") else
                                    -int(k[1]) if k[0] == "vvenc" else int(k[1])))
    rows, lines = [], []
    lines.append(f"Anchor {label(*anc)}. BD-rate % on payload bytes (negative ="
                 " fewer bits at equal quality). time = encode time / anchor at"
                 " equal PSNR-YUV (1 thread each).")
    per = {}  # (clip, config) -> dict
    for g, clips in GROUPS.items():
        for clip in clips:
            A = pts.get((clip, *anc))
            if not A:
                continue
            for cfg in configs:
                B = pts.get((clip, *cfg))
                if not B or len(B) < 3:
                    continue
                d = {m: bd_rate(A, B, m) for m in METRICS}
                d["time"] = time_ratio(A, B)
                d["spf"] = gmean([p["wall"] / FRAMES[clip] for p in B])
                d["n"] = len(B)
                per[(clip, cfg)] = d
                rows.append(dict(group=g, clip=clip, codec=cfg[0], preset=cfg[1],
                                 config=label(*cfg), points=len(B),
                                 **{f"bd_{m}": round(d[m], 2) for m in METRICS},
                                 time_vs_anchor=round(d["time"], 3),
                                 sec_per_frame=round(d["spf"], 3)))
    summary = {}
    for g, clips in GROUPS.items():
        have = [c for c in clips if (c, anc) in per]
        if not have:
            continue
        lines.append(f"\n== {g}: mean over {len(have)} clip(s) "
                     f"({', '.join(SHORT[c] for c in have)}) ==")
        lines.append(f"{'config':18s} {'clips':>5s} {'time':>8s} "
                     + " ".join(f"{'BD ' + MNAME[m]:>13s}" for m in METRICS))
        for cfg in configs:
            ds = [per[(c, cfg)] for c in have if (c, cfg) in per]
            # only configs measured on every clip of the group, so that the
            # group means compare like with like
            if len(ds) < len(have):
                continue
            s = dict(time=gmean([d["time"] for d in ds]), n=len(ds),
                     **{m: amean([d[m] for d in ds]) for m in METRICS})
            summary[(g, cfg)] = s
            lines.append(f"{label(*cfg):18s} {len(ds):5d} {s['time']:8.3f} "
                         + " ".join(f"{s[m]:+13.2f}" for m in METRICS))
    lines.append("\n== per clip ==")
    for (clip, cfg), d in per.items():
        lines.append(f"{SHORT[clip]:18s} {label(*cfg):18s} n={d['n']} "
                     f"time={d['time']:8.3f} s/frame={d['spf']:8.2f} "
                     + " ".join(f"{m}={d[m]:+7.2f}" for m in METRICS))
    (OUT / "summary.txt").write_text("\n".join(lines) + "\n")
    md = []
    for g, clips in GROUPS.items():
        have = [c for c in clips if (c, anc) in per]
        if not have:
            continue
        md.append(f"**{g}** ({', '.join(SHORT[c] for c in have)})\n")
        md.append("| Encoder | Clips | Time vs anchor | BD PSNR-YUV | BD SSIM-Y | BD VMAF |")
        md.append("|---|---:|---:|---:|---:|---:|")
        for cfg in configs:
            sm = summary.get((g, cfg))
            if not sm:
                continue
            t = sm["time"]
            ts = f"{t:.0f}x" if t >= 10 else f"{t:.2f}x" if t >= 1 else f"{t:.2g}x"
            md.append(f"| {label(*cfg)} | {sm['n']} | {ts} | "
                      + " | ".join(f"{sm[m]:+.1f}%" for m in METRICS) + " |")
        md.append("")
    (OUT / "tables.md").write_text("\n".join(md))
    with open(OUT / "results.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print("\n".join(lines[:60]))
    figures(pts, summary, configs, anc)


def style():
    plt.rcParams.update({
        "figure.facecolor": "white", "axes.facecolor": "white",
        "axes.edgecolor": INK2, "axes.labelcolor": INK, "text.color": INK,
        "xtick.color": INK2, "ytick.color": INK2, "axes.grid": True,
        "grid.color": GRID, "grid.linewidth": 0.8, "axes.spines.top": False,
        "axes.spines.right": False, "font.size": 10, "svg.fonttype": "none",
        "lines.linewidth": 2})


def speed_panel(ax, summary, configs, g, m):
    """Encode time vs BD-rate for one clip group and metric."""
    for codec, (name, col, mk) in CODEC.items():
        cs = [c for c in configs if c[0] == codec and (g, c) in summary]
        if not cs:
            continue
        xs = [summary[(g, c)]["time"] for c in cs]
        ys = [summary[(g, c)][m] for c in cs]
        ax.plot(xs, ys, color=col, marker=mk, markersize=7,
                markeredgecolor="white", markeredgewidth=1.2,
                label=name, zorder=3)
        # label the slowest and fastest config of each codec
        for c, x, y in ((cs[0], xs[0], ys[0]), (cs[-1], xs[-1], ys[-1])):
            ax.annotate(label(*c).split(" ", 1)[1], (x, y),
                        textcoords="offset points", xytext=(5, 4),
                        fontsize=7.5, color=INK2)
    ax.set_xscale("log")
    ax.axhline(0, color=INK2, linewidth=0.8, zorder=1)


def group_title(summary, anc, g):
    n = summary[(g, anc)]["n"]
    return f"{g} ({n} clip{'s' if n > 1 else ''})"


def figures(pts, summary, configs, anc):
    style()
    groups = [g for g in GROUPS if any((g, c) in summary for c in configs)]
    xlabel = f"encode time relative to {label(*anc)} (log)"
    for m in ("psnr", "vmaf"):
        fig, axes = plt.subplots(1, len(groups), figsize=(4.6 * len(groups), 4.4),
                                 squeeze=False)
        for ax, g in zip(axes[0], groups):
            speed_panel(ax, summary, configs, g, m)
            ax.set_title(group_title(summary, anc, g), fontsize=10.5)
            ax.set_xlabel(xlabel)
        axes[0][0].set_ylabel(f"BD-rate vs {label(*anc)}, {MNAME[m]} (%)")
        axes[0][-1].legend(fontsize=8, frameon=False, loc="best")
        fig.tight_layout()
        fig.savefig(OUT / "figures" / f"speed_vs_bdrate_{m}.svg")
        plt.close(fig)
    # PSNR and VMAF stacked, one column per clip group
    fig, axes = plt.subplots(2, len(groups), figsize=(4.6 * len(groups), 8.2),
                             squeeze=False, sharex="col")
    for row, m in enumerate(("psnr", "vmaf")):
        for ax, g in zip(axes[row], groups):
            speed_panel(ax, summary, configs, g, m)
            if row == 0:
                ax.set_title(group_title(summary, anc, g), fontsize=10.5)
            else:
                ax.set_xlabel(xlabel)
        axes[row][0].set_ylabel(f"BD-rate vs {label(*anc)}, {MNAME[m]} (%)")
    axes[0][-1].legend(fontsize=8, frameon=False, loc="best")
    fig.tight_layout()
    fig.savefig(OUT / "figures" / "speed_vs_bdrate.svg")
    fig.savefig(OUT / "figures" / "speed_vs_bdrate.png", dpi=300)
    plt.close(fig)
    # RD curves: slowest preset of each codec, one panel per clip
    clips = list(dict.fromkeys(c for g in GROUPS.values() for c in g
                               if any((c, *cf) in pts for cf in configs)))
    ncol = 3
    nrow = math.ceil(len(clips) / ncol)
    fig, axes = plt.subplots(nrow, ncol, figsize=(13, 3.6 * nrow), squeeze=False)
    for ax, clip in zip(axes.flat, clips):
        for codec, (name, col, mk) in CODEC.items():
            cs = [c for c in configs if c[0] == codec and (clip, *c) in pts]
            if codec == "avm":  # s1 where available, else slowest present
                cs = sorted(cs, key=lambda c: (c[1] != "1", int(c[1])))
            if not cs:
                continue
            c = cs[0]
            cv = curve(pts[(clip, *c)], "psnr")
            kbps = [p["bytes"] * 8 / 1000 for p in cv]
            ax.plot(kbps, [mval(p, "psnr") for p in cv], color=col, marker=mk,
                    markersize=5, markeredgecolor="white", markeredgewidth=0.8,
                    label=label(*c))
        ax.set_xscale("log")
        # matplotlib labels minor ticks when a log axis spans under a decade;
        # those labels overlap
        ax.xaxis.set_minor_formatter(matplotlib.ticker.NullFormatter())
        ax.set_title(SHORT[clip], fontsize=10)
        ax.set_xlabel(f"kbit per {FRAMES[clip]} frames (log)")
        ax.set_ylabel("PSNR-YUV (dB)")
        ax.legend(fontsize=7, frameon=False)
    for ax in list(axes.flat)[len(clips):]:
        ax.axis("off")
    fig.tight_layout()
    fig.savefig(OUT / "figures" / "rd_curves.svg")
    fig.savefig(OUT / "figures" / "rd_curves.png", dpi=300)
    plt.close(fig)


if __name__ == "__main__":
    main()
