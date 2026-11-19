#!/usr/bin/env python3
"""Randomized worker/frame-delay sweep; null output, separate correctness pass."""
import argparse
import json
import os
from pathlib import Path
import random
import resource
import subprocess
import time


def busy():
    fields = Path('/proc/stat').read_text().splitlines()[0].split()[1:9]
    ticks = list(map(int, fields))
    return (sum(ticks) - ticks[3] - ticks[4]) / os.sysconf('SC_CLK_TCK')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--binary', required=True)
    p.add_argument('--streams', required=True)
    p.add_argument('--stream-dir', required=True)
    p.add_argument('--out', required=True)
    p.add_argument('--reps', type=int, default=3)
    p.add_argument('--limit', type=int, default=130)
    p.add_argument('--verify', action='store_true')
    p.add_argument('--configs', default='1:1,2:1,2:2,3:1,3:2,3:3',
                   help='comma-separated workers:frame-delay pairs')
    a = p.parse_args()
    rows = [line.split('\t') for line in Path(a.streams).read_text().splitlines()
            if line and not line.startswith('#')]
    configs = [tuple(map(int, c.split(':'))) for c in a.configs.split(',')]
    jobs = [(rep, row, nt, fd) for rep in range(1 if a.verify else a.reps)
            for row in rows for nt, fd in configs]
    random.Random(69).shuffle(jobs)
    done = set()
    if Path(a.out).exists():
        for line in Path(a.out).read_text().splitlines():
            r = json.loads(line)
            if r['rc'] == 0:
                done.add((r['rep'], r['stream'], r['threads'], r['framedelay']))
    if not a.verify and os.getloadavg()[0] >= 1:
        raise SystemExit('Machine busy at start (load >= 1)')
    with open(a.out, 'a', buffering=1) as out:
        for idx, (rep, row, nt, fd) in enumerate(jobs):
            if (rep, row[0], nt, fd) in done:
                continue
            argv = [a.binary, '-q', '-i', str(Path(a.stream_dir) / row[0]),
                    '--threads', str(nt), '--framedelay', str(fd),
                    '--filmgrain', '1']
            if a.verify:
                argv += ['--verify', row[4]]
            else:
                argv += ['--muxer', 'null', '--limit', str(a.limit)]
            # Warm filesystem cache before timing. Files are public benchmark streams.
            with open(Path(a.stream_dir) / row[0], 'rb') as stream:
                while stream.read(1024 * 1024):
                    pass
            r0 = resource.getrusage(resource.RUSAGE_CHILDREN)
            b0, t0 = busy(), time.perf_counter()
            run = subprocess.run(argv, stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE, timeout=180)
            wall, b1 = time.perf_counter() - t0, busy()
            r1 = resource.getrusage(resource.RUSAGE_CHILDREN)
            cpu = r1.ru_utime + r1.ru_stime - r0.ru_utime - r0.ru_stime
            foreign = max(0, (b1 - b0 - cpu) / wall)
            result = dict(stream=row[0], threads=nt, framedelay=fd, rep=rep,
                          verify=a.verify, limit=None if a.verify else a.limit,
                          wall_s=wall, cpu_s=cpu, foreign_cores=foreign,
                          session_maxrss_kb=r1.ru_maxrss, rc=run.returncode,
                          stderr=run.stderr.decode(errors='replace'), argv=argv)
            out.write(json.dumps(result) + '\n')
            print(f'{idx+1}/{len(jobs)} t{nt} f{fd} {row[0]} '
                  f'{wall:.3f}s cpu={cpu/wall:.2f} foreign={foreign:.2f} '
                  f'rc={run.returncode}', flush=True)
            if run.returncode:
                raise SystemExit('Decode/verification failed; see output')


if __name__ == '__main__':
    main()
