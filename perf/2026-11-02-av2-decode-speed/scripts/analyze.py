"""Summaries and figures from data/{pc,pi}.jsonl.

Throughput is in megapixels per second (luma pixels x frames / wall time), so
streams of different sizes can be pooled. Per (host, decoder, stream, threads)
the median over reps is kept, of runs that were not disturbed. A decoder's
speed on a stream counts only if its output matched avmdec (md5_ok); splot
has no MD5 mode and is checked separately (data/verify_*.jsonl).

  python scripts/analyze.py      -> data/summary.csv, figures/*.svg + .png
"""
import csv, json, math, statistics
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent.parent
DATA, FIG = HERE / "data", HERE / "figures"
INK, INK2, GRID, BG = "#0b0b0b", "#52514e", "#e4e3df", "white"
# Fixed categorical slots: colour follows the decoder, never its rank.
DEC = {"avmdec": ("avmdec (AVM reference)", "#2a78d6"),
       "dav2d": ("dav2d", "#eb6834"),
       "dav2d_c": ("dav2d, C only", "#eda100"),
       "rav2d": ("rav2d", "#1baf7a"),
       "rusty_av2d": ("rusty_av2d", "#e87ba4"),
       "splot": ("splot", "#6250d6")}
HOST = {"pc": "pc: Core i5-4590 (4 cores, AVX2)", "pi": "pi: Raspberry Pi 4B (4x Cortex-A72, NEON)"}


def style():
    plt.rcParams.update({
        "figure.facecolor": BG, "axes.facecolor": BG, "axes.edgecolor": INK2,
        "axes.labelcolor": INK, "text.color": INK, "xtick.color": INK2,
        "ytick.color": INK2, "font.size": 10, "svg.fonttype": "none",
        "axes.spines.top": False, "axes.spines.right": False,
        "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.8,
        "axes.axisbelow": True, "legend.frameon": False})


def load():
    verify = {}
    for p in DATA.glob("verify_*.jsonl"):
        for l in open(p):
            r = json.loads(l)
            verify[(r["host"], r["decoder"], r["stream"])] = r["md5_ok"]
    runs = defaultdict(list)
    meta = {}
    for p in sorted(DATA.glob("p[ci].jsonl")):
        for l in open(p):
            r = json.loads(l)
            if not r.get("ok_to_keep", True):
                continue
            k = (r["host"], r["decoder"], r["stream"], r["threads"])
            ok = r["md5_ok"] if r["decoder"] != "splot" else (r["rc"] == 0 and verify.get(k[:3], False))
            runs[k].append((r["wall_s"], ok, r))
            meta[r["stream"]] = (r["frames"], r["width"], r["height"])
    rows = []
    for k, v in runs.items():
        fr, w, h = meta[k[2]]
        wall = statistics.median(x[0] for x in v)
        rows.append(dict(host=k[0], decoder=k[1], stream=k[2], threads=k[3], reps=len(v),
                         frames=fr, width=w, height=h, wall_s=round(wall, 4),
                         wall_min_s=round(min(x[0] for x in v), 4),
                         spread=round((max(x[0] for x in v) - min(x[0] for x in v)) / wall, 4),
                         mpix_s=round(fr * w * h / wall / 1e6, 3),
                         fps=round(fr / wall, 3), correct=all(x[1] for x in v),
                         maxrss_mb=max(x[2]["maxrss_mb"] for x in v),
                         cpu_s=round(statistics.median(x[2]["user_s"] + x[2]["sys_s"] for x in v), 3),
                         disturbed_runs=sum(x[2]["disturbed"] for x in v)))
    return rows


def geomean(xs):
    xs = [x for x in xs if x > 0]
    return math.exp(sum(map(math.log, xs)) / len(xs)) if xs else float("nan")


def save(fig, name):
    for ext in ("svg", "png"):
        fig.savefig(FIG / f"{name}.{ext}", dpi=160, bbox_inches="tight")
    plt.close(fig)


def main():
    style(); FIG.mkdir(exist_ok=True)
    rows = load()
    with open(DATA / "summary.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader(); w.writerows(sorted(rows, key=lambda r: (r["host"], r["decoder"], r["stream"], r["threads"])))
    core = {l.split("\t")[0] for l in open(DATA / "streams_core.tsv") if not l.startswith("#")}
    by = {(r["host"], r["decoder"], r["stream"], r["threads"]): r for r in rows}
    hosts = [h for h in HOST if any(r["host"] == h for r in rows)]
    out = []

    # Table 1 + figure 1: speed relative to avmdec, 1 thread, core set, paired per stream.
    out.append("## Speed vs avmdec, 1 thread, core set (geomean over streams both decoded correctly)\n")
    out.append("| host | decoder | streams | Mpix/s (geomean) | x avmdec |\n|---|---|---|---|---|")
    rel = defaultdict(dict)
    for h in hosts:
        for d in DEC:
            pairs = [(by[(h, d, s, 1)], by[(h, "avmdec", s, 1)]) for s in core
                     if (h, d, s, 1) in by and (h, "avmdec", s, 1) in by]
            good = [(a, b) for a, b in pairs if a["correct"] and b["correct"]]
            if not good:
                continue
            ratio = geomean([b["wall_s"] / a["wall_s"] for a, b in good])
            rel[h][d] = ratio
            out.append(f"| {h} | {d} | {len(good)}/{len(pairs)} | {geomean([a['mpix_s'] for a, _ in good]):.1f} | {ratio:.2f} |")
    fig, axes = plt.subplots(1, len(hosts), figsize=(5.2 * len(hosts), 3.0), sharex=True, squeeze=False)
    for ax, h in zip(axes[0], hosts):
        ds = [d for d in DEC if d in rel[h]]
        ys = range(len(ds))[::-1]
        ax.hlines(list(ys), 0, [rel[h][d] for d in ds], color=GRID, lw=2)
        for y, d in zip(ys, ds):
            ax.plot(rel[h][d], y, "o", ms=8, color=DEC[d][1], mec=BG, mew=2)
            ax.annotate(f"{rel[h][d]:.2f}x", (rel[h][d], y), xytext=(7, 0), textcoords="offset points",
                        va="center", color=INK, fontsize=9)
        ax.set_yticks(list(ys), [DEC[d][0] for d in ds])
        ax.set_xscale("log"); ax.axvline(1, color=INK2, lw=1, ls=":")
        ax.set_title(HOST[h], fontsize=10, loc="left")
        ax.set_xlabel("decode speed relative to avmdec (1 thread, log scale)")
        ax.grid(axis="y", visible=False)
    save(fig, "speed_vs_avmdec")

    # Figure 2: thread scaling on the core set (geomean Mpix/s per thread count).
    out.append("\n## Thread scaling, core set (geomean Mpix/s over streams decoded correctly at every thread count)\n")
    out.append("| host | decoder | " + " | ".join(f"{t} thr" for t in (1, 2, 3, 4)) + " |\n|---|---|---|---|---|---|")
    fig, axes = plt.subplots(1, len(hosts), figsize=(5.2 * len(hosts), 3.4), squeeze=False)
    for ax, h in zip(axes[0], hosts):
        for d in DEC:
            ts = sorted({r["threads"] for r in rows if r["host"] == h and r["decoder"] == d})
            if len(ts) < 2:
                continue
            ss = [s for s in core if all((h, d, s, t) in by and by[(h, d, s, t)]["correct"] for t in ts)]
            if not ss:
                continue
            ys = [geomean([by[(h, d, s, t)]["mpix_s"] for s in ss]) for t in ts]
            ax.plot(ts, ys, "-o", lw=2, ms=8, color=DEC[d][1], mec=BG, mew=2, label=DEC[d][0])
            ax.annotate(DEC[d][0], (ts[-1], ys[-1]), xytext=(6, 0), textcoords="offset points",
                        va="center", fontsize=9, color=INK)
            cells = {t: f"{y:.1f}" for t, y in zip(ts, ys)}
            out.append(f"| {h} | {d} | " + " | ".join(cells.get(t, "") for t in (1, 2, 3, 4)) + " |")
        ax.set_xticks([1, 2, 3, 4]); ax.set_xlabel("threads"); ax.set_ylabel("Mpix/s (geomean)")
        ax.set_ylim(bottom=0); ax.set_title(HOST[h], fontsize=10, loc="left")
        ax.legend(loc="upper left", fontsize=8)
    save(fig, "thread_scaling")

    # Figure 3: per-stream dav2d / avmdec on the pc, whole corpus, 1 and 4 threads.
    for t in (1, 4):
        pts = sorted(((by[("pc", "avmdec", s, t)]["wall_s"] / by[("pc", "dav2d", s, t)]["wall_s"], s)
                      for (h, d, s, tt) in by if h == "pc" and d == "dav2d" and tt == t
                      and ("pc", "avmdec", s, t) in by and by[("pc", "dav2d", s, t)]["correct"]
                      and by[("pc", "avmdec", s, t)]["correct"]), reverse=True)
        if not pts:
            continue
        out.append(f"\n## pc, whole corpus, {t} thread(s): dav2d vs avmdec over {len(pts)} streams\n")
        out.append(f"geomean {geomean([p[0] for p in pts]):.2f}x, median {statistics.median(p[0] for p in pts):.2f}x, "
                   f"range {pts[-1][0]:.2f}x ({pts[-1][1]}) to {pts[0][0]:.2f}x ({pts[0][1]})")
        if t == 1:
            fig, ax = plt.subplots(figsize=(7, 0.17 * len(pts) + 1))
            ys = range(len(pts))[::-1]
            ax.hlines(list(ys), 0, [p[0] for p in pts], color=GRID, lw=2)
            ax.plot([p[0] for p in pts], list(ys), "o", ms=6, color=DEC["dav2d"][1], mec=BG, mew=1.5)
            ax.set_yticks(list(ys), [p[1].split("/", 1)[1].removesuffix(".ivf") for p in pts], fontsize=6.5)
            ax.set_xlabel("dav2d speed relative to avmdec, 1 thread (pc)")
            ax.set_xlim(left=0); ax.grid(axis="y", visible=False)
            save(fig, "dav2d_vs_avmdec_per_stream")

    # Correctness table.
    out.append("\n## Correctness (streams whose output matched avmdec, any thread count)\n")
    out.append("| host | decoder | matched | of |\n|---|---|---|---|")
    for h in hosts:
        for d in DEC:
            st = defaultdict(lambda: True)
            for r in rows:
                if r["host"] == h and r["decoder"] == d:
                    st[r["stream"]] &= r["correct"]
            if st:
                out.append(f"| {h} | {d} | {sum(st.values())} | {len(st)} |")
    (DATA / "summary.md").write_text("\n".join(out) + "\n")
    print("\n".join(out))


if __name__ == "__main__":
    main()
