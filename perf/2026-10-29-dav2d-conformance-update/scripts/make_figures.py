"""Figures for the 29 Oct update, from the results of both reports.

Steps are measured on the 260 streams of the first report. The MSVC build
with only the MSVC fix (0001) has no row for one stream; the gcc build of the
same commit stands in for it (the two agree on the other 259).

  python scripts/make_figures.py
"""
import json
import re
from collections import Counter
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent.parent
OLD = HERE.parent / "2026-10-20-av2-decoder-conformance" / "conform.jsonl"
OUT = HERE / "figures"
INK, INK2, BG = "#0b0b0b", "#52514e", "white"
STATUS = [("match", "Match", "#0ca30c"), ("mismatch", "Mismatch", "#fab219"),
          ("error", "Error (gave up)", "#ec835a"), ("crash", "Crash", "#d03b3b")]
COLOR = {s: c for s, _, c in STATUS}
TRUNCATED = "crowd_run_1080p50_qp110_s4_33f.ivf"
# (label, results file, decoder name or None for the only decoder)
STEPS = [
    ("20 Oct nightly (MSVC)", OLD, "dav2d_nightly_msvc"),
    ("+ MSVC fix (#74)", OLD, "dav2d_msvc_patch1"),
    ("+ DRL, LR, deblock fixes\n(#70, #71, #72, #73)", OLD, "dav2d_patched_msvc"),
    ("29 Oct nightly: upstream,\nall fixes but #72", HERE / "conform_nightly.jsonl", None),
    ("+ !947 (#72)", HERE / "conform_main_mr947.jsonl", None),
]


def load(path):
    return [json.loads(l) for l in open(path)]


def outcome(r, ref):
    if r["md5"] and r["md5"] == ref:
        return "match"
    if r["md5"]:
        return "mismatch"
    return "crash" if r["rc"] not in (0, 1) else "error"


def steps():
    old = load(OLD)
    ref = {r["stream"]: r["md5"] for r in old if r["decoder"] == "reference"}
    kind = {r["stream"]: r["set"] for r in old}
    streams = sorted(s for s in ref if s != TRUNCATED)
    fallback = {r["stream"]: outcome(r, ref[r["stream"]])
                for r in old if r["decoder"] == "dav2d_gcc"}
    out = []
    for label, path, dec in STEPS:
        res = {r["stream"]: outcome(r, ref[r["stream"]]) for r in load(path)
               if r["decoder"] != "reference" and (dec is None or r["decoder"] == dec)
               and r["stream"] in ref}
        out.append((label, {s: res.get(s) or fallback[s] for s in streams}))
    return streams, kind, out


def group(stream, kind):
    m = re.search(r"_s(\d)_", stream)
    if m:
        return int(m.group(1))
    return 6 if kind == "hd" else 9   # hd set: --cpu-used=6, samples: 9


def style():
    plt.rcParams.update({
        "figure.facecolor": BG, "axes.facecolor": BG, "axes.edgecolor": INK2,
        "axes.labelcolor": INK, "text.color": INK, "xtick.color": INK2,
        "ytick.color": INK2, "font.size": 10, "svg.fonttype": "none",
        "axes.spines.top": False, "axes.spines.right": False})


def legend(ax, y=1.0):
    handles = [plt.Rectangle((0, 0), 1, 1, color=c) for _, _, c in STATUS]
    ax.legend(handles, [l for _, l, _ in STATUS], ncol=4, frameon=False,
              loc="lower left", bbox_to_anchor=(0, y), fontsize=9,
              handlelength=1, columnspacing=1.2)


def stairs(streams, data):
    n = len(streams)
    fig, ax = plt.subplots(figsize=(8.6, 3.6))
    for i, (_, res) in enumerate(data):
        c = Counter(res.values())
        left = 0
        for s, _, col in STATUS:
            v = c[s]
            if not v:
                continue
            ax.barh(i, v, left=left, height=0.62, color=col, edgecolor=BG, linewidth=2)
            if v >= 14:
                ax.text(left + v / 2, i, str(v), ha="center", va="center",
                        fontsize=9, color=INK)
            left += v
        small = [f"{c[st]} {lab.split(' ')[0].lower()}"
                 for st, lab, _ in STATUS[1:] if 0 < c[st] < 14]
        if small:
            ax.text(n + 3, i, " + ".join(small), ha="left", va="center",
                    fontsize=8.5, color=INK2)
    ax.set_yticks(range(len(data)), [l for l, _ in data], fontsize=9)
    ax.invert_yaxis()
    ax.set_xlim(0, n)
    ax.set_xlabel(f"streams (of the {n} from the 20 Oct report)")
    ax.tick_params(axis="y", length=0)
    ax.spines["left"].set_visible(False)
    legend(ax)
    ax.set_title("dav2d output vs avmdec after each fix", loc="left",
                 fontsize=10.5, pad=26)
    fig.tight_layout()
    fig.savefig(OUT / "fix_steps.svg", bbox_inches="tight")


def grid(streams, kind, data):
    order = sorted(streams, key=lambda s: (group(s, kind[s]), kind[s], s))
    groups = Counter(group(s, kind[s]) for s in order)
    fig, ax = plt.subplots(figsize=(8.6, 2.9))
    gap, x, xs, starts = 3, 0, [], {}
    prev = None
    for s in order:
        g = group(s, kind[s])
        if prev is not None and g != prev:
            x += gap
        if g not in starts:
            starts[g] = x
        xs.append(x)
        x += 1
        prev = g
    for i, (_, res) in enumerate(data):
        for s, xi in zip(order, xs):
            ax.add_patch(plt.Rectangle((xi, i + 0.08), 1, 0.84,
                                       color=COLOR[res[s]], linewidth=0))
    ax.set_xlim(0, x)
    ax.set_ylim(len(data), 0)
    ax.set_yticks([i + 0.5 for i in range(len(data))],
                  [l.replace("\n", " ") for l, _ in data], fontsize=8.5)
    ax.set_xticks([starts[g] + groups[g] / 2 for g in sorted(groups)],
                  [f"{g}\n({groups[g]})" for g in sorted(groups)], fontsize=8.5)
    ax.set_xlabel("avmenc --cpu-used (streams)")
    ax.tick_params(length=0)
    for sp in ("left", "bottom"):
        ax.spines[sp].set_visible(False)
    legend(ax, 1.02)
    ax.set_title("Streams fixed at each step, one column per stream",
                 loc="left", fontsize=10.5, pad=24)
    fig.tight_layout()
    fig.savefig(OUT / "per_stream.svg", bbox_inches="tight")


if __name__ == "__main__":
    style()
    OUT.mkdir(exist_ok=True)
    s, k, d = steps()
    stairs(s, d)
    grid(s, k, d)
    for label, res in d:
        print(label.replace("\n", " "), dict(Counter(res.values())))
