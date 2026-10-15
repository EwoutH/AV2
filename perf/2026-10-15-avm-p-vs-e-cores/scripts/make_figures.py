"""Figures and tables for the P-core vs E-core test, from results.jsonl.

Prints the Markdown tables used in README.md and writes figures/*.svg.
"""
import json
import statistics
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent.parent
FIG = HERE / "figures"
FRAMES = {"270p8": 33, "270p10": 33, "720p8": 9}
JOB_NAME = {"270p8": "270p 8-bit", "270p10": "270p 10-bit", "720p8": "720p 8-bit"}

# Same style as the preset sweep. Categorical slots in fixed order:
# P-core blue, hyperthread green, E-core orange; unpinned is neutral gray.
COL = {"P": "#2a78d6", "HT": "#1baf7a", "E": "#eb6834", "?": "#8a8984"}
LABEL = {"P": "P-core", "HT": "P-core hyperthread", "E": "E-core",
         "?": "unpinned (any core)"}
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
    "legend.frameon": False})


def kind(cpu):
    if cpu is None:
        return "?"
    return "E" if cpu >= 12 else ("P" if cpu % 2 == 0 else "HT")


rows = [json.loads(l) for l in open(HERE / "results.jsonl")]
for r in rows:
    f = FRAMES[r["job"]]
    r["by"] = {}
    for s in r["slots"]:
        r["by"].setdefault(kind(s["cpu"]), []).append(f * 60 / s["wall"])
    r["total"] = sum(sum(v) for v in r["by"].values())

iso = {(r["test"].split()[1], r["job"]): r for r in rows if r["test"].startswith("iso")}
loaded = [r for r in rows if not r["test"].startswith("iso")]
base = next(r for r in loaded if r["test"] == "6 P")["total"]

# ---- tables ---------------------------------------------------------------
print("| Source | P-core | E-core | E-core speed vs P-core |")
print("|---|--:|--:|--:|")
for job in FRAMES:
    p, e = iso[("P", job)], iso[("E", job)]
    pw, ew = p["slots"][0]["wall"], e["slots"][0]["wall"]
    print(f"| {JOB_NAME[job]}, {FRAMES[job]} frames | {pw:.0f} s | {ew:.0f} s "
          f"| {pw / ew:.0%} |")
print()
print("| Layout | Slots | Total (frames/min) | vs 6 P-cores | Per slot (frames/min) "
      "| Clock P / E (MHz) |")
print("|---|--:|--:|--:|---|---|")
for r in loaded:
    per = ", ".join(f"{LABEL[k]} {statistics.mean(v):.1f}" for k, v in r["by"].items())
    c = r["clocks_mhz"]
    clk = f"{c['P']:.0f} / {c['E']:.0f}"
    print(f"| {r['test']} | {len(r['slots'])} | {r['total']:.0f} "
          f"| {r['total'] / base - 1:+.0%} | {per} | {clk} |")

# ---- figure 1: throughput per layout, split by core type ------------------
fig, ax = plt.subplots(figsize=(7.5, 3.6))
order = list(reversed(loaded))
for y, r in enumerate(order):
    left = 0
    for k in ("P", "HT", "E", "?"):
        if k not in r["by"]:
            continue
        w = sum(r["by"][k])
        ax.barh(y, w, left=left, height=0.62, color=COL[k],
                edgecolor="white", linewidth=2)
        left += w
    ax.text(left + 6, y, f"{r['total']:.0f}", va="center", fontsize=9, color=INK)
ax.set_yticks(range(len(order)), [r["test"] for r in order])
ax.set_xlabel("Throughput, frames per minute (270p 8-bit, 1 thread per encode)")
ax.set_xlim(0, 480)
ax.grid(axis="y", visible=False)
ax.set_axisbelow(True)
handles = [plt.Rectangle((0, 0), 1, 1, color=COL[k]) for k in ("P", "HT", "E", "?")]
ax.legend(handles, [LABEL[k] for k in ("P", "HT", "E", "?")], ncol=4,
          loc="lower left", bbox_to_anchor=(0, 1.0), fontsize=9,
          handlelength=1, columnspacing=1.2)
fig.tight_layout()
fig.savefig(FIG / "throughput_by_layout.svg", metadata=SVG_META)

# ---- figure 2: E-core speed as a share of P-core speed --------------------
bars = [(f"{JOB_NAME[j]},\nalone", iso[("E", j)]["by"]["E"][0] / iso[("P", j)]["by"]["P"][0])
        for j in FRAMES]
mixed = next(r for r in loaded if r["test"] == "6 P + 8 E")
bars.append(("270p 8-bit,\nall 14 cores busy",
             statistics.mean(mixed["by"]["E"]) / statistics.mean(mixed["by"]["P"])))
fig, ax = plt.subplots(figsize=(6.5, 3.2))
xs = range(len(bars))
ax.bar(xs, [v * 100 for _, v in bars], width=0.55, color=COL["E"],
       edgecolor="white", linewidth=2)
for x, (_, v) in zip(xs, bars):
    ax.text(x, v * 100 + 2, f"{v:.0%}", ha="center", fontsize=9, color=INK)
ax.axhline(100, color=COL["P"], lw=1.5, ls="--")
ax.text(len(bars) - 0.5, 101.5, "P-core = 100%", ha="right", va="bottom",
        fontsize=9, color=INK2)
ax.set_xticks(list(xs), [b for b, _ in bars])
ax.set_ylabel("E-core speed, % of P-core")
ax.set_ylim(0, 115)
ax.grid(axis="x", visible=False)
ax.set_axisbelow(True)
fig.tight_layout()
fig.savefig(FIG / "e_vs_p_speed.svg", metadata=SVG_META)
print("\nfigures written to", FIG)
