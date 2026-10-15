"""P-core vs E-core benchmark for avmenc on an i7-12700H.

Logical CPUs: 0-11 are the 6 P-cores with HT pairs (0/1, 2/3, ...),
12-19 the 8 E-cores. Each test starts a set of slots; every slot runs the
same fixed encode job pinned to its CPU and records its wall and CPU time.
When a slot's timed job ends, it runs filler encodes until all slots are
done, so the load stays constant. Per-core clocks are sampled with typeperf.
"""
import csv, io, json, statistics, subprocess, sys, threading, time
from pathlib import Path
import psutil

REL = Path(r"C:\Users\Ewout\Documents\GitHub\AV2\samples\av2_work\avm_build_windows\Release")
SRC = Path(r"C:\Users\Ewout\Documents\GitHub\AV2\samples\av2_work\sources")
ENC = str(REL / "avmenc.exe")
OUT = Path(sys.argv[1]); OUT.mkdir(exist_ok=True)
ONLY = sys.argv[2:]

JOBS = {  # name: (source, frames)
    "270p8":  ("FourPeople_480x270_60.y4m", 33),
    "270p10": ("SparksElevator_480x270p_5994_10bit.y4m", 33),
    "720p8":  ("vidyo4_720p_60fps.y4m", 9),
}
P_PHYS, P_HT, E = [0, 2, 4, 6, 8, 10], [1, 3, 5, 7, 9, 11], list(range(12, 20))

TESTS = [  # (name, job, slot cpus; None = unpinned)
    ("iso P",            "270p8",  [2]),
    ("iso E",            "270p8",  [12]),
    ("iso P",            "270p10", [2]),
    ("iso E",            "270p10", [12]),
    ("iso P",            "720p8",  [2]),
    ("iso E",            "720p8",  [12]),
    ("6 P",              "270p8",  P_PHYS),
    ("8 E",              "270p8",  E),
    ("6 P + 8 E",        "270p8",  P_PHYS + E),
    ("12 P+HT",          "270p8",  P_PHYS + P_HT),
    ("20 all",           "270p8",  P_PHYS + P_HT + E),
    ("14 unpinned",      "270p8",  [None] * 14),
    ("20 unpinned",      "270p8",  [None] * 20),
]


def cmd(job, out):
    src, frames = JOBS[job]
    return [ENC, str(SRC / src), "-o", str(out), "--ivf", "--end-usage=q",
            "--qp=160", "--cpu-used=6", "--threads=1", f"--limit={frames}"]


def clock_sampler(stop, samples):
    """Actual MHz per logical CPU, every 2 s (Processor Frequency x % Performance)."""
    ctrs = [r"\Processor Information(0,*)\Processor Frequency",
            r"\Processor Information(0,*)\% Processor Performance"]
    p = subprocess.Popen(["typeperf", *ctrs, "-si", "2"], stdout=subprocess.PIPE,
                         text=True, errors="replace")
    header = None
    for line in p.stdout:
        if stop.is_set():
            break
        row = next(csv.reader(io.StringIO(line)), None)
        if not row or len(row) < 3:
            continue
        if header is None:
            header = row
            continue
        try:
            vals = [float(x) for x in row[1:]]
        except ValueError:
            continue
        freq, perf = {}, {}
        for h, v in zip(header[1:], vals):
            inst = h.split("(")[1].split(")")[0]
            if not inst.startswith("0,") or inst.endswith("_Total"):
                continue
            cpu = int(inst.split(",")[1])
            (freq if h.endswith("Frequency") else perf)[cpu] = v
        samples.append({c: freq[c] * perf.get(c, 0) / 100 for c in freq})
    p.kill()


def run_test(name, job, cpus):
    done = {}
    stop_fill = threading.Event()
    procs, lock = [], threading.Lock()

    def slot(i, cpu):
        def start(out):
            p = subprocess.Popen(cmd(job, out), stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL)
            with lock:
                procs.append(p)
            if cpu is not None:
                psutil.Process(p.pid).cpu_affinity([cpu])
            return p
        t0 = time.perf_counter()
        p = start(OUT / f"s{i}.ivf")
        ps = psutil.Process(p.pid)
        cpu_t = 0.0
        while p.poll() is None:
            try:
                ct = ps.cpu_times(); cpu_t = ct.user + ct.system
            except psutil.Error:
                pass
            time.sleep(0.2)
        wall = time.perf_counter() - t0
        done[i] = {"cpu": cpu, "wall": wall, "cpu_time": cpu_t, "rc": p.returncode}
        while not stop_fill.is_set():  # keep the load on until all are done
            f = start(OUT / f"f{i}.ivf")
            while f.poll() is None and not stop_fill.is_set():
                time.sleep(0.2)
            if f.poll() is None:
                f.kill()

    stop_clk, samples = threading.Event(), []
    clk = threading.Thread(target=clock_sampler, args=(stop_clk, samples), daemon=True)
    clk.start()
    ths = [threading.Thread(target=slot, args=(i, c)) for i, c in enumerate(cpus)]
    for t in ths:
        t.start()
    while len(done) < len(cpus):
        time.sleep(0.5)
    stop_fill.set()
    with lock:
        for p in procs:
            if p.poll() is None:
                p.kill()
    for t in ths:
        t.join()
    stop_clk.set()

    frames = JOBS[job][1]
    rows = [done[i] for i in sorted(done)]
    bad = [r for r in rows if r["rc"] != 0]
    def kind(c):
        return "?" if c is None else ("E" if c >= 12 else ("P" if c % 2 == 0 else "HT"))
    # mean clock per kind over the period when every slot was still busy
    clocks = {}
    if samples:
        mid = samples[1:-1] or samples
        for k, cs in (("P", P_PHYS), ("HT", P_HT), ("E", E)):
            busy = [c for c in cs if c in [r["cpu"] for r in rows]] or cs
            clocks[k] = statistics.mean(s[c] for s in mid for c in busy if c in s)
    by = {}
    for r in rows:
        by.setdefault(kind(r["cpu"]), []).append(r["wall"])
    thru = sum(frames * 60 / r["wall"] for r in rows)
    parts = ", ".join(f"{k}: {statistics.mean(v):6.1f}s/job ({frames*60/statistics.mean(v):5.1f} f/min)"
                      for k, v in by.items())
    clk_s = " ".join(f"{k}~{v:.0f}MHz" for k, v in clocks.items())
    print(f"{name:13s} {job:7s} slots={len(cpus):2d} total {thru:6.1f} f/min | {parts} | {clk_s}"
          + (f" | {len(bad)} FAILED" if bad else ""), flush=True)
    with open(OUT / "pe_results.jsonl", "a") as f:
        f.write(json.dumps({"test": name, "job": job, "slots": rows,
                            "clocks_mhz": clocks, "total_fpm": thru}) + "\n")
    time.sleep(10)  # cool down between tests


if __name__ == "__main__":
    for name, job, cpus in TESTS:
        if not ONLY or any(o in f"{name} {job}" for o in ONLY):
            run_test(name, job, cpus)
