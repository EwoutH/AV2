"""Analyse sweep.jsonl: RD curves per clip, BD-rate vs encode time (Pareto).

Metrics (BD-rate on payload bytes, i.e. without IVF headers):
  PSNR  YUV 6:1:1 of avmenc's per-plane frame-mean PSNR
  SSIM  Y, in dB (-10 log10(1 - SSIM)), from ffmpeg
  VMAF  libvmaf v0.6.1 pooled mean, at native resolution (the model assumes
        1080p viewing, so for the low-res clips treat it as relative only)
BD-rate: PCHIP in the log-rate domain, as in analyze.py. Negative = fewer
bits than the reference preset at the same quality.

Charts per resolution group use only presets that ran on every clip of the
group; their time axis is the geometric mean over clips of encode time
relative to the reference. Per-clip charts use absolute seconds.

Writes PNGs and summary.txt into ./sweep_report/.
"""
import argparse, json, math
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.ticker import NullFormatter, ScalarFormatter
from scipy.interpolate import PchipInterpolator

HERE = Path(__file__).resolve().parent
OUTDIR = HERE / "sweep_report"
METRICS = [("psnr", "PSNR YUV 6:1:1 (dB)"), ("ssim", "SSIM Y (dB)"),
           ("vmaf", "VMAF")]


def bd_rate(r1, m1, r2, m2):
    """Bjontegaard delta rate (%) of curve 2 vs curve 1. NaN if no overlap."""
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


def group(r):
    return "hd" if r["w"] * r["h"] >= 1280 * 720 else "lowres"


def pareto_front(pts):
    """pts: {name: (x, y)}, minimise both. Returns the non-dominated names."""
    return [n for n, (x, y) in pts.items()
            if not any(x2 <= x and y2 <= y and (x2, y2) != (x, y)
                       for m, (x2, y2) in pts.items() if m != n)]


def logx(ax):
    ax.set_xscale("log")
    ax.xaxis.set_major_formatter(ScalarFormatter())
    ax.xaxis.set_minor_formatter(NullFormatter())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", default="sweep.jsonl")
    ap.add_argument("--ref", type=int, default=1,
                    help="reference preset for BD-rate and relative time")
    a = ap.parse_args()
    OUTDIR.mkdir(exist_ok=True)
    rows = []
    for line in (HERE / a.results).read_text().splitlines():
        try:
            rows.append(json.loads(line))
        except ValueError:
            pass
    ok = [r for r in rows if r["rc"] == 0 and (r.get("quality") or {})
          .get("ssim") and r["quality"].get("vmaf") is not None]
    main_rows = [r for r in ok if not r.get("rep")]
    failed = [r for r in rows if r["rc"] != 0]

    # by[clip][preset][qp] = row
    by = defaultdict(lambda: defaultdict(dict))
    for r in main_rows:
        by[r["clip"]][r["preset"]][r["qp"]] = r
    clips = sorted(by, key=lambda c: (group(next(iter(by[c][min(by[c])]
                                                       .values()))), c))
    grp = {c: group(next(iter(by[c][min(by[c])].values()))) for c in clips}
    frames = {c: next(iter(by[c][min(by[c])].values()))["frames"]
              for c in clips}
    presets = sorted({p for c in by for p in by[c]})
    print(f"{len(main_rows)} encodes, {len(failed)} failed; presets "
          f"{presets}; ref s{a.ref}")

    def pair(clip, p):
        """(cur, ref) rows on common QPs, or None unless >= 4 QPs."""
        ref, cur = by[clip].get(a.ref, {}), by[clip].get(p, {})
        qps = sorted(set(ref) & set(cur))
        return ([cur[q] for q in qps], [ref[q] for q in qps]) \
            if len(qps) >= 4 else None

    def bd(clip, p, m):
        c = pair(clip, p)
        if c is None:
            return float("nan")
        cur, ref = c
        return bd_rate([r["payload"] for r in ref], [metric(r, m) for r in ref],
                       [r["payload"] for r in cur], [metric(r, m) for r in cur])

    def wall(clip, p, inter_only=False):
        rs = pair(clip, p)[0]
        if inter_only:
            return sum(ms for r in rs for t, ms in r["frame_ms"]
                       if t != "KEY") / 1000
        return sum(r["wall"] for r in rs)

    def rel_time(clip, p, inter_only=False):
        return wall(clip, p, inter_only) / wall(clip, a.ref, inter_only)

    cmap = plt.get_cmap("viridis")
    color = {p: cmap(i / max(1, len(presets) - 1))
             for i, p in enumerate(presets)}

    # ---- 1. RD curves per clip ---------------------------------------------
    for clip in clips:
        fig, axes = plt.subplots(1, 3, figsize=(15, 4.6))
        for ax, (m, label) in zip(axes, METRICS):
            for p in presets:
                if p not in by[clip]:
                    continue
                rs = sorted(by[clip][p].values(), key=lambda r: r["qp"])
                ax.plot([r["payload"] / 1000 for r in rs],
                        [metric(r, m) for r in rs], "o-", color=color[p],
                        lw=2.4 if p == a.ref else 1.2, ms=4,
                        label=f"s{p}" + (" (ref)" if p == a.ref else ""))
            logx(ax)
            ax.set_xlabel(f"payload (kB, {frames[clip]} frames)")
            ax.set_ylabel(label)
            ax.grid(alpha=0.3)
        axes[0].legend(fontsize=8, ncol=2)
        fig.suptitle(f"RD curves: {clip}")
        fig.tight_layout()
        fig.savefig(OUTDIR / f"rd_{clip}.png", dpi=130)
        plt.close(fig)

    # ---- 2. Pareto charts --------------------------------------------------
    def scatter(ax, xy, xlabel, ylabel):
        front = pareto_front(xy)
        for p, (x, y) in xy.items():
            ax.scatter(x, y, s=50, zorder=3,
                       color="C3" if p in front else "C0",
                       marker="*" if p == a.ref else "o")
            ax.annotate(f"s{p}", (x, y), textcoords="offset points",
                        xytext=(5, 4), fontsize=9)
        fx = sorted(front, key=lambda p: xy[p][0])
        ax.plot([xy[p][0] for p in fx], [xy[p][1] for p in fx], "C3--",
                lw=1, zorder=2)
        ax.axhline(0, color="gray", lw=0.8)
        logx(ax)
        ax.set_xlabel(xlabel)
        ax.set_ylabel(ylabel)
        ax.grid(alpha=0.3)

    group_stats = {}
    for g in ("lowres", "hd"):
        full = {c: {p for p in presets if pair(c, p)} for c in clips
                if grp[c] == g and pair(c, a.ref)}
        if not full:
            continue
        # Presets complete on the most complete clips; clips missing any of
        # them (e.g. a filler clip cut off at the stop time) are left out
        # of the group chart but still get their own per-clip chart.
        best = max(len(s) for s in full.values())
        req = set.intersection(*[s for s in full.values() if len(s) == best])
        cs = [c for c, s in full.items() if s >= req]
        ps = sorted(req)
        st = {p: dict(t=math.exp(np.mean([math.log(rel_time(c, p))
                                          for c in cs])),
                      **{m: float(np.mean([bd(c, p, m) for c in cs]))
                         for m, _ in METRICS}) for p in ps}
        group_stats[g] = (cs, st)
        fig, axes = plt.subplots(1, 3, figsize=(15, 4.8))
        for ax, (m, label) in zip(axes, METRICS):
            scatter(ax, {p: (s["t"], s[m]) for p, s in st.items()},
                    f"encode time relative to s{a.ref} (geomean, log)",
                    f"BD-rate vs s{a.ref} (%), {label}")
        fig.suptitle(f"Speed vs BD-rate, {g} ({len(cs)} clips: "
                     f"{', '.join(c.split('_')[0] for c in cs)}). Red = "
                     f"Pareto front, lower-left is better")
        fig.tight_layout()
        fig.savefig(OUTDIR / f"pareto_{g}.png", dpi=130)
        plt.close(fig)

    cs = [c for c in clips if pair(c, a.ref)]
    if cs:
        fig, axes = plt.subplots(len(cs), 3, figsize=(15, 3.6 * len(cs)),
                                 squeeze=False)
        for row, c in zip(axes, cs):
            ps = [p for p in presets if pair(c, p)]
            for ax, (m, label) in zip(row, METRICS):
                scatter(ax, {p: (wall(c, p), bd(c, p, m)) for p in ps},
                        "encode time, 4 QPs (s, log)", f"BD {label} (%)")
            row[0].set_title(f"{c} ({frames[c]} f)", loc="left", fontsize=10)
        fig.tight_layout()
        fig.savefig(OUTDIR / "pareto_per_clip.png", dpi=110)
        plt.close(fig)

    # ---- 3. Tables ---------------------------------------------------------
    L = [f"Reference s{a.ref}. BD-rate % on payload bytes; negative = fewer "
         f"bits. time = sum over 4 QPs; rel = time / ref time; inter = same "
         f"for inter frames only.", ""]
    for g, (gcs, st) in group_stats.items():
        L.append(f"== {g}: mean over {len(gcs)} clips (geomean for time) ==")
        L.append(f"{'preset':>6} {'rel':>6} {'inter':>6} {'BD PSNR':>8} "
                 f"{'BD SSIM':>8} {'BD VMAF':>8}")
        for p, s in st.items():
            inter = math.exp(np.mean([math.log(rel_time(c, p, True))
                                      for c in gcs]))
            L.append(f"{'s' + str(p):>6} {s['t']:6.3f} {inter:6.3f} "
                     f"{s['psnr']:+8.2f} {s['ssim']:+8.2f} {s['vmaf']:+8.2f}")
        L.append("")
    L.append("== per clip ==")
    L.append("key%t / key%b: share of encode time / of bits in the keyframe "
             "(mean over QPs)")
    L.append(f"{'clip':32} {'preset':>6} {'time s':>8} {'rel':>6} "
             f"{'key%t':>5} {'key%b':>5} {'BD PSNR':>8} {'BD SSIM':>8} "
             f"{'BD VMAF':>8} {'peakMB':>7} {'conc':>5}")

    def key_share(rs, field):
        sh = []
        for r in rs:
            v = r.get(field) or []
            tot = sum(x for _, x in v)
            if tot:
                sh.append(sum(x for t, x in v if t == "KEY") / tot)
        return 100 * np.mean(sh) if sh else float("nan")

    for c in cs:
        for p in presets:
            if not pair(c, p):
                continue
            rs = pair(c, p)[0]
            conc = [r["conc"] for r in rs if r.get("conc")]
            L.append(f"{c:32} {'s' + str(p):>6} {wall(c, p):8.0f} "
                     f"{rel_time(c, p):6.3f} {key_share(rs, 'frame_ms'):5.0f} "
                     f"{key_share(rs, 'frame_bytes'):5.0f} "
                     f"{bd(c, p, 'psnr'):+8.2f} {bd(c, p, 'ssim'):+8.2f} "
                     f"{bd(c, p, 'vmaf'):+8.2f} "
                     f"{max(r['peak_mb'] for r in rs):7.0f} "
                     f"{np.mean(conc) if conc else float('nan'):5.1f}")
        L.append("")
    incomplete = [(c, p, sorted(by[c][p])) for c in clips for p in by[c]
                  if not pair(c, p)]
    if incomplete:
        L.append("Incomplete (fewer than 4 QPs, or no reference): " + ", ".join(
            f"{c.split('_')[0]} s{p} {q}" for c, p, q in incomplete))
    reps = [r for r in ok if r.get("rep")]
    if reps:
        L.append("== timing drift: repeated encodes (rep / first run) ==")
        for r in reps:
            r0 = by[r["clip"]].get(r["preset"], {}).get(r["qp"])
            if r0:
                L.append(f"  {r['clip']} qp{r['qp']} s{r['preset']}: "
                         f"{r0['wall']:.1f}s -> {r['wall']:.1f}s "
                         f"({r['wall'] / r0['wall']:.3f}x), conc "
                         f"{r0.get('conc')} -> {r.get('conc')}")
    # Alignment check: ffmpeg's frame-mean PSNR-Y on the decoded frames must
    # match avmenc's, and all frames must decode. A misaligned frame pair
    # costs several dB, so 0.05 dB is a tight bound.
    bad = [r for r in ok if r["quality"].get("dec_frames") != r["frames"]
           or r["quality"].get("ff_psnr_y") is None
           or abs(r["quality"]["ff_psnr_y"] - r["psnr"][0]) > 0.05]
    L.append(f"Alignment check (ffmpeg vs avmenc PSNR-Y within 0.05 dB, all "
             f"frames decoded): {len(ok) - len(bad)}/{len(ok)} OK")
    for r in bad:
        L.append(f"  CHECK {r['clip']} qp{r['qp']} s{r['preset']}: avmenc "
                 f"{r['psnr'][0]:.2f} ffmpeg {r['quality'].get('ff_psnr_y')} "
                 f"frames {r['quality'].get('dec_frames')}/{r['frames']}")
    if failed:
        L.append("Failed encodes: " + ", ".join(
            f"{r['clip'].split('_')[0]} qp{r['qp']} s{r['preset']} rc={r['rc']}"
            for r in failed))
    text = "\n".join(L)
    (OUTDIR / "summary.txt").write_text(text + "\n")
    print(text)
    print(f"\nWrote {OUTDIR}")


if __name__ == "__main__":
    main()
