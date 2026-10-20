"""Decoder speed: avmdec vs dav2d on HD AV2 streams, 1 thread and all threads.

Run on an idle machine. Each (decoder, stream, threads) is decoded `--reps`
times to a null/MD5 sink; the median wall time is kept, and the MD5 is
checked against avmdec so only correct decodes count.

  python bench_decode.py [--reps 3]
"""
import argparse, json, statistics, subprocess, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
W = HERE.parent
AVMDEC = HERE / "avm/avm-windows-x64/avmdec.exe"
DAV2D = HERE / "build-msvc/tools/dav2d.exe"          # patched, MSVC + asm
DAV2D_C = (DAV2D, ["--cpumask", "0"])                 # same build, C only
STREAMS = [  # (file, frames) from the HD set (--cpu-used 6, QP 135)
    "KristenAndSara_1280x720_60_qp135_600f.ivf",
    "vidyo4_720p_60fps_qp135_600f.ivf",
    "crowd_run_1080p50_qp135_500f.ivf",
    "Motorcycle_1920x1080_30fps_8bit_qp135_130f.ivf",
    "EuroTruckSimulator2_1920x1080p60_qp135_130f.ivf",
]
THREADS = [1, 20]


def run(cmd):
    t0 = time.perf_counter()
    p = subprocess.run([str(c) for c in cmd], capture_output=True, text=True)
    return time.perf_counter() - t0, p


def md5_of(name, p):
    out = (p.stdout or "").split()
    return out[0] if p.returncode == 0 and out else None


def cmd_for(dec, ivf, threads):
    if dec == "avmdec":
        return [AVMDEC, ivf, "--rawvideo", "--md5", f"--threads={threads}"]
    exe, extra = (DAV2D, []) if dec == "dav2d" else DAV2D_C
    return [exe, "-q", "-i", ivf, "--muxer", "md5", "-o", "-",
            "--threads", str(threads)] + extra


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--out", default=str(HERE / "bench_decode.jsonl"))
    a = ap.parse_args()
    hd = W / "hd_long/encoded"
    for name in STREAMS:
        ivf = hd / name
        if not ivf.exists():
            print("missing", name)
            continue
        frames = int(name.rsplit("_", 1)[1].rstrip("f.ivf").rstrip("f"))
        ref = None
        for dec in ("avmdec", "dav2d", "dav2d_c"):
            for th in THREADS:
                if dec == "dav2d_c" and th != 1:
                    continue
                times, md5 = [], None
                for _ in range(a.reps):
                    t, p = run(cmd_for(dec, ivf, th))
                    md5 = md5_of(dec, p)
                    times.append(t)
                if dec == "avmdec" and th == 1:
                    ref = md5
                row = dict(stream=name, frames=frames, decoder=dec, threads=th,
                           wall=round(statistics.median(times), 3),
                           fps=round(frames / statistics.median(times), 2),
                           md5_ok=md5 == ref and md5 is not None,
                           times=[round(x, 3) for x in times])
                print(json.dumps(row), flush=True)
                with open(a.out, "a") as f:
                    f.write(json.dumps(row) + "\n")


if __name__ == "__main__":
    main()
