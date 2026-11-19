#!/usr/bin/env python3
"""Paired, resumable null-output A/B benchmark with competing-CPU rejection.

Starts at load < 1 and < 0.10 busy cores. Later admission checks use idle-window
CPU activity so the benchmark's own recent load average does not stall it.
"""
import argparse
from datetime import datetime
import json
import math
import os
from pathlib import Path
import random
import threading
import subprocess
import time


def busy():
    v = list(map(int, Path('/proc/stat').read_text().splitlines()[0].split()[1:9]))
    return (sum(v) - v[3] - v[4]) / os.sysconf('SC_CLK_TCK')


def frequency():
    vals = []
    for p in Path('/sys/devices/system/cpu').glob('cpu[0-9]*/cpufreq/scaling_cur_freq'):
        try:
            vals.append(int(p.read_text()) / 1000)
        except OSError:
            pass
    return vals


def run(cmd, repeat, scratch, timeout=180):
    cpu = 0.0
    rss = 0
    timed_out = threading.Event()
    freq = [frequency()]
    samples_done = threading.Event()

    def sample():
        while not samples_done.wait(.25):
            freq.append(frequency())

    sampler = threading.Thread(target=sample, daemon=True)
    sampler.start()
    with open(scratch / 'stdout', 'w+b') as out, open(scratch / 'stderr', 'w+b') as err:
        b0, start = busy(), time.perf_counter()
        rc = 0
        for _ in range(repeat):
            proc = subprocess.Popen(cmd, stdout=out, stderr=err)

            def kill(proc=proc):
                timed_out.set()
                proc.kill()

            timer = threading.Timer(max(.01, timeout - (time.perf_counter() - start)), kill)
            timer.start()
            _, status, usage = os.wait4(proc.pid, 0)
            timer.cancel()
            proc.returncode = rc = os.waitstatus_to_exitcode(status)
            cpu += usage.ru_utime + usage.ru_stime
            rss = max(rss, usage.ru_maxrss)
            if rc or timed_out.is_set():
                break
        wall = time.perf_counter() - start
        b1 = busy()
        samples_done.set()
        sampler.join()
        err.seek(0)
        stderr = err.read().decode(errors='replace')
    return dict(wall_s=wall, cpu_s=cpu, maxrss_kb=rss, rc=rc,
                timeout=timed_out.is_set(), stderr=stderr,
                foreign_cores=max(0, (b1 - b0 - cpu) / wall),
                frequency_mhz=freq)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--baseline', required=True)
    p.add_argument('--variant', required=True)
    p.add_argument('--streams', required=True)
    p.add_argument('--stream-dir', required=True)
    p.add_argument('--out', required=True)
    p.add_argument('--scratch', required=True)
    p.add_argument('--configs', default='2:1,3:1')
    p.add_argument('--reps', type=int, default=3)
    p.add_argument('--limit', type=int, default=130)
    p.add_argument('--min-seconds', type=float, default=1.2)
    p.add_argument('--max-foreign', type=float, default=.10)
    p.add_argument('--max-wait', type=float, default=3600)
    a = p.parse_args()
    scratch = Path(a.scratch)
    scratch.mkdir(parents=True, exist_ok=True)
    binaries = dict(baseline=a.baseline, three_pass=a.variant)
    rows = [l.split('\t') for l in Path(a.streams).read_text().splitlines()
            if l and not l.startswith('#')]
    configs = [tuple(map(int, c.split(':'))) for c in a.configs.split(',')]
    rng = random.Random(617)
    jobs = [(rep, row, nt, fd) for rep in range(a.reps)
            for row in rows for nt, fd in configs]
    rng.shuffle(jobs)
    done = set()
    if Path(a.out).exists():
        for line in Path(a.out).read_text().splitlines():
            r = json.loads(line)
            if r.get('accepted'):
                done.add((r['rep'], r['stream'], r['threads'], r['framedelay']))
    admitted = False
    deadline = time.monotonic() + a.max_wait

    def quiet():
        nonlocal admitted
        while True:
            b0, t0 = busy(), time.monotonic()
            time.sleep(2)
            cores = (busy() - b0) / (time.monotonic() - t0)
            load = os.getloadavg()[0]
            if cores <= a.max_foreign and (admitted or load < 1):
                admitted = True
                return
            if time.monotonic() >= deadline:
                raise SystemExit('Quiet-machine deadline reached; results are resumable')
            print(f'Waiting: load={load:.2f}, busy={cores:.2f} cores', flush=True)
            time.sleep(15)

    def argv(name, row, nt, fd):
        return [binaries[name], '-q', '-i', str(Path(a.stream_dir) / row[0]),
                '--threads', str(nt), '--framedelay', str(fd), '--filmgrain', '1',
                '--muxer', 'null', '--limit', str(a.limit)]

    repeats = {}
    with open(a.out, 'a', buffering=1) as out:
        for rep, row, nt, fd in jobs:
            key = (rep, row[0], nt, fd)
            if key in done:
                continue
            # Cache warming is outside every timed pair.
            with open(Path(a.stream_dir) / row[0], 'rb') as stream:
                while stream.read(1024 * 1024):
                    pass
            for attempt in range(4):
                quiet()
                # A single-thread calibration amortizes process startup on tiny streams.
                if row[0] not in repeats:
                    cal = run(argv('baseline', row, 1, 1), 1, scratch)
                    if cal['rc'] or cal['stderr']:
                        raise SystemExit(f'Calibration decode failed: {cal}')
                    repeats[row[0]] = max(1, math.ceil(a.min_seconds * 3 / cal['wall_s']))
                    if cal['foreign_cores'] > a.max_foreign:
                        del repeats[row[0]]
                        continue
                    quiet()
                names = list(binaries)
                rng.shuffle(names)
                results = {}
                for name in names:
                    results[name] = run(argv(name, row, nt, fd), repeats[row[0]], scratch)
                accepted = all(r['rc'] == 0 and not r['stderr'] and
                               r['foreign_cores'] <= a.max_foreign
                               for r in results.values())
                result = dict(rep=rep, stream=row[0], threads=nt, framedelay=fd,
                              limit=a.limit, repeat=repeats[row[0]], attempt=attempt,
                              order=names, results=results, accepted=accepted,
                              timestamp=datetime.now().astimezone().isoformat(),
                              affinity=sorted(os.sched_getaffinity(0)))
                out.write(json.dumps(result) + '\n')
                print(key, 'accepted', accepted, 'ratio',
                      round(results['baseline']['wall_s'] / results['three_pass']['wall_s'], 3),
                      flush=True)
                if any(r['rc'] or r['stderr'] for r in results.values()):
                    raise SystemExit('Decoder error; see output')
                if accepted:
                    done.add(key)
                    break
            else:
                raise SystemExit('Repeated disturbed measurements; stopped for later resume')


if __name__ == '__main__':
    main()
