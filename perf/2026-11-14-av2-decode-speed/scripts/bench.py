"""AV2 decode-speed benchmark runner (stdlib only, runs on the pc and the pi).

Timed runs use null output (see the decoder JSON); correctness is checked
separately by verify_raw.py, so md5/md5_ok are only filled if a decoder prints one.

Each task (decoder, stream, threads) is decoded --reps times. The order is
shuffled within each rep round so slow drift (heat, background work) spreads
over all decoders. Every run records wall time, the child's CPU time and peak
memory, the MD5 check, and how much CPU *other* processes used meanwhile
("foreign" CPU, from /proc/stat minus the child's rusage). A run with too much
foreign CPU is marked disturbed and retried after a pause.

  python bench.py --host pc --decoders decoders.json --streams streams.tsv \
      --threads 1,2,4 --reps 3 --out results.jsonl

decoders.json: {"name": ["argv", "...", "{ivf}", "{threads}"], ...}
streams.tsv:   file<TAB>frames<TAB>width<TAB>height<TAB>md5[<TAB>repeat]   (relative to --stream-dir)
A short stream is decoded `repeat` times back to back within one timed run (one
process per decode), so the run lasts long enough; frames is per decode.
The run is resumable: rows already in --out (same host/decoder/stream/threads/rep)
are skipped.
"""
import argparse, glob, json, os, random, re, subprocess, sys, tempfile, threading, time
from types import SimpleNamespace
from pathlib import Path

MD5_RE = re.compile(r"\b[0-9a-f]{32}\b")
BUSY_UNITS = ["nixos-upgrade.service", "job-*.service", "btrbk-*.service", "nix-gc.service"]


def cpu_busy_jiffies():
    with open("/proc/stat") as f:
        v = [int(x) for x in f.readline().split()[1:]]
    # user nice system idle iowait irq softirq steal
    return v[0] + v[1] + v[2] + v[5] + v[6] + v[7]


def temp_c():
    vals = []
    for p in glob.glob("/sys/class/thermal/thermal_zone*/temp"):
        try:
            vals.append(int(open(p).read()) / 1000)
        except OSError:
            pass
    return max(vals) if vals else None


def busy_units():
    try:
        out = subprocess.run(["systemctl", "list-units", "--state=activating,active",
                              "--no-legend", "--plain", *BUSY_UNITS],
                             capture_output=True, text=True, timeout=10).stdout
    except Exception:
        return []
    return [l.split()[0] for l in out.splitlines() if l.strip()]


class FreqSampler(threading.Thread):
    """Samples the highest current core frequency every 0.5 s."""
    def __init__(self):
        super().__init__(daemon=True)
        self.paths = glob.glob("/sys/devices/system/cpu/cpu[0-9]*/cpufreq/scaling_cur_freq")
        self.samples, self.stop = [], threading.Event()

    def run(self):
        while not self.stop.wait(0.5):
            try:
                self.samples.append(max(int(open(p).read()) for p in self.paths) / 1000)
            except (OSError, ValueError):
                pass


def run_once(argv, timeout, repeat=1):
    """Run one decode, or `repeat` decodes back to back (short streams), timed as
    one run; returns rc, timed_out, wall, stdout, stderr, busy CPU s of the whole
    machine, temps, freq samples and the children's summed rusage."""
    hz = os.sysconf("SC_CLK_TCK")
    fs = FreqSampler(); fs.start()
    t_before, b0 = temp_c(), cpu_busy_jiffies()
    ru = SimpleNamespace(ru_utime=0.0, ru_stime=0.0, ru_maxrss=0)
    rc, timed_out = 0, threading.Event()
    with tempfile.TemporaryFile() as fo, tempfile.TemporaryFile() as fe:
        t0 = time.perf_counter()
        deadline = t0 + timeout
        for _ in range(repeat):
            p = subprocess.Popen(argv, stdout=fo, stderr=fe)
            # Block in wait4 (no polling, which would show up as foreign CPU); a
            # timer thread kills the decoder on timeout.
            def kill(p=p):
                timed_out.set(); p.kill()
            timer = threading.Timer(max(0.0, deadline - time.perf_counter()), kill); timer.start()
            _, status, r = os.wait4(p.pid, 0)
            timer.cancel()
            p.returncode = rc = os.waitstatus_to_exitcode(status)
            ru.ru_utime += r.ru_utime; ru.ru_stime += r.ru_stime
            ru.ru_maxrss = max(ru.ru_maxrss, r.ru_maxrss)
            if rc or timed_out.is_set():
                break
        wall = time.perf_counter() - t0
        b1 = cpu_busy_jiffies()
        fo.seek(0); fe.seek(0)
        out, err = fo.read().decode(errors="replace"), fe.read().decode(errors="replace")
    fs.stop.set(); fs.join()
    return rc, timed_out.is_set(), wall, out, err, (b1 - b0) / hz, t_before, temp_c(), fs.samples, ru


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", required=True)
    ap.add_argument("--decoders", required=True)
    ap.add_argument("--only", default="", help="comma list of decoder names to run")
    ap.add_argument("--streams", required=True)
    ap.add_argument("--stream-dir", default=".")
    ap.add_argument("--threads", default="1")
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--out", required=True)
    ap.add_argument("--timeout", type=float, default=3600)
    ap.add_argument("--max-foreign", type=float, default=0.10,
                    help="max foreign CPU, in cores averaged over the run")
    ap.add_argument("--retries", type=int, default=4)
    ap.add_argument("--seed", type=int, default=1)
    a = ap.parse_args()

    decoders = json.load(open(a.decoders))
    if a.only:
        decoders = {k: v for k, v in decoders.items() if k in a.only.split(",")}
    streams = []
    for line in open(a.streams):
        if line.startswith("#") or not line.strip():
            continue
        c = line.rstrip("\n").split("\t")
        f, fr, w, h, md5 = c[:5]
        streams.append(dict(stream=f, frames=int(fr), width=int(w), height=int(h), md5=md5,
                            repeat=int(c[5]) if len(c) > 5 else 1))
    threads = [int(t) for t in a.threads.split(",")]

    done = set()
    if os.path.exists(a.out):
        for l in open(a.out):
            r = json.loads(l)
            if r.get("ok_to_keep", True):
                done.add((r["host"], r["decoder"], r["stream"], r["threads"], r["rep"]))

    rng = random.Random(a.seed)
    total = len(decoders) * len(streams) * len(threads) * a.reps
    n = len(done)
    for rep in range(a.reps):
        tasks = [(d, s, t) for d in decoders for s in streams for t in threads]
        rng.shuffle(tasks)
        for dec, s, th in tasks:
            key = (a.host, dec, s["stream"], th, rep)
            if key in done:
                continue
            argv = [x.replace("{ivf}", str(Path(a.stream_dir) / s["stream"]))
                     .replace("{threads}", str(th)) for x in decoders[dec]]
            for attempt in range(a.retries + 1):
                while (bu := busy_units()):
                    print(f"  waiting for {bu}", file=sys.stderr, flush=True)
                    time.sleep(20)
                rc, to, wall, out, err, busy, tb, ta, freqs, ru = run_once(argv, a.timeout, s["repeat"])
                user, sys_ = ru.ru_utime, ru.ru_stime
                foreign = max(0.0, busy - user - sys_)
                disturbed = foreign / wall > a.max_foreign
                m = MD5_RE.findall(out) or MD5_RE.findall(err)
                md5 = m[-1] if m and rc == 0 else None
                row = dict(host=a.host, decoder=dec, stream=s["stream"], repeat=s["repeat"],
                           frames=s["frames"] * s["repeat"],
                           width=s["width"], height=s["height"], threads=th, rep=rep,
                           attempt=attempt, wall_s=round(wall, 4), user_s=round(user, 3),
                           sys_s=round(sys_, 3), maxrss_mb=round(ru.ru_maxrss / 1024, 1),
                           foreign_cores=round(foreign / wall, 3), disturbed=disturbed,
                           rc=rc, timeout=to, md5=md5, md5_ok=(md5 == s["md5"]) if md5 else None,
                           temp_before=tb, temp_after=ta,
                           freq_mhz_mean=round(sum(freqs) / len(freqs)) if freqs else None,
                           freq_mhz_min=round(min(freqs)) if freqs else None,
                           fps=round(s["frames"] * s["repeat"] / wall, 3),
                           ok_to_keep=not disturbed or attempt == a.retries,
                           ts=time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                           err_tail=err[-300:] if rc else "")
                with open(a.out, "a") as f:
                    f.write(json.dumps(row) + "\n")
                if not disturbed:
                    break
                print(f"  disturbed ({row['foreign_cores']} cores foreign), retry",
                      file=sys.stderr, flush=True)
                time.sleep(30)
            n += 1
            print(f"[{n}/{total}] {dec} t{th} r{rep} {s['stream']}: {row['fps']} fps "
                  f"md5_ok={row['md5_ok']} foreign={row['foreign_cores']}", flush=True)


if __name__ == "__main__":
    main()
