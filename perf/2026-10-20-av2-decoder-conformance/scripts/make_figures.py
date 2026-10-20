"""Figures for the decoder write-up, from conform.jsonl and bench_decode.jsonl.

  python scripts/make_figures.py
"""
import json
from collections import Counter, defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker

HERE = Path(__file__).resolve().parent.parent
OUT = HERE / "figures"
INK, INK2, GRID, BG = "#0b0b0b", "#52514e", "#e4e3df", "white"

# status palette: match / mismatch / error / crash
STATUS = [("match", "Match", "#0ca30c"), ("mismatch", "Mismatch", "#fab219"),
          ("error", "Error (gave up)", "#ec835a"), ("crash", "Crash", "#d03b3b")]
DECODERS = [("avmdec_nightly", "avmdec (AVM nightly)"),
            ("dav2d_nightly_msvc", "dav2d nightly (MSVC)"),
            ("dav2d_gcc", "dav2d, gcc build"),
            ("dav2d_patched_gcc", "dav2d + 5 patches"),
            ("rav2d_nightly", "rav2d nightly")]
# speed: categorical slots 1-4
SPEED = [("avmdec", 1, "avmdec, 1 thread", "#2a78d6"),
         ("dav2d_c", 1, "dav2d C only, 1 thread", "#eda100"),
         ("dav2d", 1, "dav2d, 1 thread", "#eb6834"),
         ("dav2d", 20, "dav2d, 20 threads", "#1baf7a")]
SHORT = {"KristenAndSara": "KristenAndSara 720p", "vidyo4": "vidyo4 720p",
         "crowd_run": "crowd_run 1080p", "Motorcycle": "Motorcycle 1080p",
         "EuroTruckSimulator2": "EuroTruck 1080p"}


def style():
    plt.rcParams.update({
        "figure.facecolor": BG, "axes.facecolor": BG, "axes.edgecolor": INK2,
        "axes.labelcolor": INK, "text.color": INK, "xtick.color": INK2,
        "ytick.color": INK2, "font.size": 10, "svg.fonttype": "none",
        "axes.spines.top": False, "axes.spines.right": False})


def conformance():
    by = defaultdict(dict)
    for line in open(HERE / "conform.jsonl"):
        r = json.loads(line)
        by[r["stream"]][r["decoder"]] = r
    counts = {}
    for key, _ in DECODERS:
        c = Counter()
        for d in by.values():
            r, ref = d[key], d["reference"]["md5"]
            c["match" if r["md5"] == ref else "crash" if r["rc"] not in (0, 1)
              else "error" if r["rc"] else "mismatch"] += 1
        counts[key] = c
    n = len(by)

    fig, ax = plt.subplots(figsize=(8.6, 3.4))
    for i, (key, _) in enumerate(DECODERS):
        left = 0
        for s, _, col in STATUS:
            v = counts[key][s]
            if not v:
                continue
            ax.barh(i, v, left=left, height=0.62, color=col,
                    edgecolor=BG, linewidth=2)
            if v >= 14:  # label segments wide enough to hold a number
                ax.text(left + v / 2, i, str(v), ha="center", va="center",
                        fontsize=9, color=INK)
            left += v
        # segments too narrow to see: name them at the bar's end
        small = [f"{counts[key][st]} {lab.split(' ')[0].lower()}"
                 for st, lab, _ in STATUS[1:] if 0 < counts[key][st] < 3]
        if small:
            ax.text(left - 3, i, " + ".join(small), ha="right", va="center",
                    fontsize=8.5, color="white")
    ax.set_yticks(range(len(DECODERS)), [l for _, l in DECODERS])
    ax.invert_yaxis()
    ax.set_xlim(0, n)
    ax.set_xlabel(f"streams (of {n})")
    ax.tick_params(axis="y", length=0)
    ax.spines["left"].set_visible(False)
    handles = [plt.Rectangle((0, 0), 1, 1, color=c) for _, _, c in STATUS]
    ax.legend(handles, [l for _, l, _ in STATUS], ncol=4, frameon=False,
              loc="lower left", bbox_to_anchor=(0, 1.0), fontsize=9,
              handlelength=1, columnspacing=1.2)
    ax.set_title("Decoded output vs avmdec --rawvideo --md5", loc="left",
                 fontsize=10.5, pad=26)
    fig.tight_layout()
    fig.savefig(OUT / "conformance.svg")
    return fig


def speed():
    rows = [json.loads(l) for l in open(HERE / "bench_decode.jsonl")]
    streams = list(dict.fromkeys(r["stream"] for r in rows))
    fps = {(r["stream"], r["decoder"], r["threads"]): r["fps"] for r in rows}
    fig, ax = plt.subplots(figsize=(8.6, 4.6))
    h = 0.19
    for j, (dec, th, label, col) in enumerate(SPEED):
        ys = [i + (j - 1.5) * (h + 0.02) for i in range(len(streams))]
        vs = [fps[(s, dec, th)] for s in streams]
        ax.barh(ys, vs, height=h, color=col, label=label)
        for y, v in zip(ys, vs):
            ax.text(v * 1.04, y, f"{v:.0f}" if v >= 20 else f"{v:.1f}",
                    va="center", fontsize=7.5, color=INK2)
    ax.set_xscale("log")
    ax.set_xlim(3, 600)
    ticks = [5, 10, 20, 50, 100, 200, 500]
    ax.set_xticks(ticks, [str(t) for t in ticks])
    ax.xaxis.set_minor_locator(matplotlib.ticker.NullLocator())
    ax.set_yticks(range(len(streams)),
                  [SHORT[s.split("_1")[0].split("_720p")[0]] for s in streams])
    ax.invert_yaxis()
    ax.set_xlabel("frames per second (log)")
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.tick_params(axis="y", length=0)
    ax.spines["left"].set_visible(False)
    ax.legend(ncol=4, frameon=False, loc="lower left", bbox_to_anchor=(0, 1.0),
              fontsize=8.5, handlelength=1, columnspacing=1)
    ax.set_title("Decode speed, AVM --cpu-used=6 QP 135 streams, i7-12700H",
                 loc="left", fontsize=10.5, pad=26)
    fig.tight_layout()
    fig.savefig(OUT / "decode_speed.svg")
    return fig


if __name__ == "__main__":
    style()
    OUT.mkdir(exist_ok=True)
    conformance()
    speed()
