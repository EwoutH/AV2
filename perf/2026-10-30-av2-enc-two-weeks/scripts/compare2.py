"""Compare av2-enc 89eae123d (14 Oct) and 97e8004e4 (30 Oct) from sweep2.jsonl.

Per clip and preset: BD-rate of new vs old at the same preset (PSNR YUV 6:1:1,
SSIM-Y dB, VMAF) and the encode-time ratio (sum of wall time over the QPs).
Per group: both builds against the old build's s1 (speed/BD-rate frontier).
Also checks the old build against the 14 Oct sweep: same bytes, and time drift.

  python -I compare2.py [--results sweep2.jsonl] [--out compare2_report]
"""
import argparse, json, math
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from analyze_sweep import bd_rate, metric

HERE = Path(__file__).resolve().parent
OLD, NEW = "89eae123d", "97e8004e4"
QPS = (110, 145, 180, 210)
# default dataviz palette, slots 1-2; chrome tokens
C_OLD, C_NEW = "#2a78d6", "#eb6834"
INK, INK2, GRID, SURF = "#0b0b0b", "#52514e", "#e1e0d9", "#fcfcfb"
SHORT = {"FourPeople_480x270_60": "FourPeople 270p",
         "BlueSky_360p25_v2": "BlueSky 360p",
         "Vertical_Bayshore_270x480_2997": "Vertical_Bayshore 270x480",
         "KristenAndSara_1280x720_60": "KristenAndSara 720p"}


def load(path):
    rows = []
    for line in open(path):
        try:
            r = json.loads(line)
        except ValueError:
            continue
        q = r.get("quality") or {}
        if r["rc"] == 0 and q.get("ssim") and q.get("vmaf") is not None:
            rows.append(r)
    return rows


def curve(rows, clip, preset, build, m):
    pts = sorted((r["qp"], r["payload"], metric(r, m), r["wall"]) for r in rows
                 if r["clip"] == clip and r["preset"] == preset
                 and r["build"] == build)
    if [p[0] for p in pts] != list(QPS):
        return None
    return dict(rate=[p[1] for p in pts], q=[p[2] for p in pts],
                wall=sum(p[3] for p in pts))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", default="sweep2.jsonl")
    ap.add_argument("--out", default="compare2_report")
    a = ap.parse_args()
    out = HERE / a.out
    out.mkdir(exist_ok=True)
    rows = load(HERE / a.results)
    clips = [c for c in SHORT if any(r["clip"] == c for r in rows)]
    lines = [f"{len(rows)} complete encodes ({OLD} vs {NEW})", ""]
    table = []  # per clip/preset
    for clip in clips:
        lines.append(f"## {SHORT[clip]}")
        lines.append("preset | time new/old | BD PSNR | BD SSIM | BD VMAF "
                     "| old vs old-s1: time, BD PSNR | new vs old-s1: time, BD PSNR")
        ref = {m: curve(rows, clip, 1, OLD, m) for m in ("psnr", "ssim", "vmaf")}
        for p in range(1, 10):
            co = {m: curve(rows, clip, p, OLD, m) for m in ("psnr", "ssim", "vmaf")}
            cn = {m: curve(rows, clip, p, NEW, m) for m in ("psnr", "ssim", "vmaf")}
            if not co["psnr"] or not cn["psnr"]:
                continue
            bd = {m: bd_rate(co[m]["rate"], co[m]["q"], cn[m]["rate"], cn[m]["q"])
                  for m in co}
            t = cn["psnr"]["wall"] / co["psnr"]["wall"]
            row = dict(clip=clip, preset=p, time_ratio=t, **{f"bd_{m}": v for m, v in bd.items()},
                       wall_old=co["psnr"]["wall"], wall_new=cn["psnr"]["wall"])
            if ref["psnr"]:
                for tag, c in (("old", co), ("new", cn)):
                    row[f"{tag}_vs_s1_time"] = c["psnr"]["wall"] / ref["psnr"]["wall"]
                    row[f"{tag}_vs_s1_bd"] = bd_rate(ref["psnr"]["rate"], ref["psnr"]["q"],
                                                     c["psnr"]["rate"], c["psnr"]["q"])
            table.append(row)
            f = lambda k: f"{row[k]:.2f}x" if k in row else "-"
            g = lambda k: f"{row[k]:+.1f}%" if k in row and not math.isnan(row[k]) else "-"
            lines.append(f"s{p} | {t:.2f}x | {bd['psnr']:+.1f}% | {bd['ssim']:+.1f}% | "
                         f"{bd['vmaf']:+.1f}% | {f('old_vs_s1_time')}, {g('old_vs_s1_bd')} | "
                         f"{f('new_vs_s1_time')}, {g('new_vs_s1_bd')}")
        lines.append("")

    # group means (geometric for time, arithmetic for BD)
    groups = {"low-res (3 clips)": [c for c in clips if "1280" not in c],
              "720p (KristenAndSara)": [c for c in clips if "1280" in c]}
    summary = {}
    lines.append("## Group means (time: geometric mean of ratios)")
    for gname, gclips in groups.items():
        for p in range(1, 10):
            rs = [r for r in table if r["clip"] in gclips and r["preset"] == p]
            if len(rs) != len(gclips) or not rs:
                continue
            gm = lambda k: math.exp(sum(math.log(r[k]) for r in rs) / len(rs))
            am = lambda k: sum(r[k] for r in rs) / len(rs)
            s = dict(time_ratio=gm("time_ratio"), bd_psnr=am("bd_psnr"),
                     bd_ssim=am("bd_ssim"), bd_vmaf=am("bd_vmaf"))
            if all("old_vs_s1_time" in r for r in rs):
                for tag in ("old", "new"):
                    s[f"{tag}_t"] = gm(f"{tag}_vs_s1_time")
                    s[f"{tag}_bd"] = am(f"{tag}_vs_s1_bd")
            summary[(gname, p)] = s
            lines.append(f"{gname} s{p}: new is {1 / s['time_ratio']:.2f}x as fast, "
                         f"BD PSNR {s['bd_psnr']:+.1f}% SSIM {s['bd_ssim']:+.1f}% "
                         f"VMAF {s['bd_vmaf']:+.1f}%")
    lines.append("")

    # old build vs the 14 Oct sweep: bytes identical? time drift?
    old14 = {}
    for line in open(HERE / "sweep.jsonl"):
        try:
            r = json.loads(line)
        except ValueError:
            continue
        if r["rc"] == 0 and not r["rep"]:
            old14[(r["clip"], r["qp"], r["preset"], r["frames"])] = r
    same, diff, drift = 0, 0, []
    for r in rows:
        if r["build"] != OLD:
            continue
        o = old14.get((r["clip"], r["qp"], r["preset"], r["frames"]))
        if not o:
            continue
        if o["payload"] == r["payload"]:
            same += 1
        else:
            diff += 1
        drift.append(r["wall"] / o["wall"])
    if drift:
        gmd = math.exp(sum(map(math.log, drift)) / len(drift))
        lines.append(f"## Old build vs 14 Oct sweep\n{same} encodes with identical "
                     f"payload size, {diff} different; wall time now/then: geometric "
                     f"mean {gmd:.3f}, range {min(drift):.2f}-{max(drift):.2f}")
    (out / "summary.txt").write_text("\n".join(lines) + "\n")
    json.dump([dict(r) for r in table], open(out / "table.json", "w"), indent=1)
    print("\n".join(lines))

    # figure: time vs BD-rate (PSNR) vs old s1, one panel per group
    panels = [g for g in groups if any((g, p) in summary and "old_t" in summary[(g, p)]
                                       for p in range(1, 10))]
    if not panels:
        return
    plt.rcParams.update({"font.family": "sans-serif", "font.size": 10,
                         "axes.edgecolor": GRID, "axes.labelcolor": INK2,
                         "xtick.color": INK2, "ytick.color": INK2,
                         "text.color": INK})
    fig, axes = plt.subplots(1, len(panels), figsize=(5.2 * len(panels), 4.2),
                             sharey=True, squeeze=False)
    for ax, g in zip(axes[0], panels):
        ax.set_facecolor(SURF)
        for tag, col, mk, label in (("old", C_OLD, "o", f"14 Oct ({OLD})"),
                                    ("new", C_NEW, "s", f"30 Oct ({NEW})")):
            pts = [(p, summary[(g, p)][f"{tag}_t"], summary[(g, p)][f"{tag}_bd"])
                   for p in range(1, 10) if (g, p) in summary and f"{tag}_t" in summary[(g, p)]]
            xs, ys = [x for _, x, _ in pts], [y for _, _, y in pts]
            ax.plot(xs, ys, color=col, lw=2, marker=mk, ms=7, mec=SURF, mew=1.5,
                    label=label, zorder=3)
            # the new build's s6-s9 are identical encodes: label that point once
            same69 = tag == "new" and len({round(y, 3) for p, x, y in pts if p >= 6}) == 1
            for p, x, y in pts:
                if p in (1, 3, 6) or (p == 9 and not same69):
                    lab = "s6-s9" if (p == 6 and same69) else f"s{p}"
                    ax.annotate(lab, (x, y), textcoords="offset points",
                                xytext=(6, -12 if tag == "new" else 6), fontsize=8, color=INK2)
        ax.set_xscale("log")
        ax.xaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{v:g}"))
        ax.set_title(g, fontsize=10, color=INK, loc="left")
        ax.set_xlabel("Encode time, relative to 14 Oct s1 (log)")
        ax.grid(True, color=GRID, lw=0.6)
        ax.axhline(0, color=INK2, lw=0.8)
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
    axes[0][0].set_ylabel("BD-rate vs 14 Oct s1, PSNR (%)")
    axes[0][0].legend(frameon=False, fontsize=9, loc="upper right")
    fig.patch.set_facecolor(SURF)
    fig.tight_layout()
    fig.savefig(out / "speed_vs_bdrate_old_new.svg")
    fig.savefig(out / "speed_vs_bdrate_old_new.png", dpi=150)


if __name__ == "__main__":
    main()
