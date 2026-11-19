#!/usr/bin/env python3
"""Recompute prior scaling and summarize exploratory scheduler diagnostics."""
from collections import defaultdict
import csv
import json
from pathlib import Path
from statistics import geometric_mean as gm, median

ROOT = Path(__file__).resolve().parents[1]
OLD = ROOT.parent / '2026-11-14-av2-decode-speed/data/summary.csv'
g = defaultdict(dict)
for r in csv.DictReader(OLD.open()):
    if r['decoder'] == 'dav2d':
        g[r['host'], r['stream']][int(r['threads'])] = r
out = ['# Reanalysis of 14 November data', '',
       '| Host | Group | Streams | 4t / 1t speed | Average busy cores, 4t | CPU time, 4t / 1t |',
       '|---|---|---:|---:|---:|---:|']
for host in ['pc', 'pi']:
    for label in ['8-bit', '10-bit', 'screen in filename']:
        a = [(v[1], v[4]) for (h, s), v in g.items()
             if h == host and {1, 4} <= v.keys() and
             (('screen' in s) if label.startswith('screen')
              else v[1]['bitdepth'] == label.split('-')[0])]
        vals = [gm(float(x['wall_s']) / float(y['wall_s']) for x, y in a),
                gm(float(y['cpu_s']) / float(y['wall_s']) for x, y in a),
                gm(float(y['cpu_s']) / float(x['cpu_s']) for x, y in a)]
        out.append(f'| {host} | {label} | {len(a)} | {vals[0]:.2f}× | '
                   f'{vals[1]:.2f} | {vals[2]:.2f}× |')
out += ['', 'Geometric means of per-stream ratios. Screen classification uses filenames, '
        'not parsed feature flags. These groups overlap. CPU time includes the main thread.', '']
for file in ['diagnostics.jsonl', 'three-pass-diagnostics.jsonl']:
    if not (ROOT / 'data' / file).exists():
        continue
    out += [f'# {file}', '',
            '| Stream | Workers / frames | Lock held | Lock acquisition wait | Condition wait | Hash matches |',
            '|---|---:|---:|---:|---:|---|']
    for line in (ROOT / 'data' / file).read_text().splitlines():
        r = json.loads(line)
        w = r['workers']
        times = [sum(x[k] for x in w) for k in
                 ['held_ns', 'lock_wait_ns', 'parked_ns']]
        total = sum(times) + sum(sum(t[0] for t in x['tasks']) for x in w)
        pct = [100 * t / total for t in times]
        out.append(f'| {Path(r["stream"]).name} | {r["threads"]} / {r["framedelay"]} | '
                   f'{pct[0]:.2f}% | {pct[1]:.2f}% | {pct[2]:.2f}% | {r["matches"]} |')
    out += ['', 'Shares of aggregate instrumented worker wall time; includes descheduling. '
            'Condition waits include reacquiring the mutex. The main thread, output hashing, '
            'and single-frame initialization are outside this accounting. '
            'This is not a throughput benchmark.', '']
sweep = [json.loads(l) for l in (ROOT / 'data/sweep.jsonl').read_text().splitlines()]
out += ['# Interrupted sweep', '',
        f'{len(sweep)} completed runs; '
        f'{sum(r["foreign_cores"] <= .1 for r in sweep)} with ≤0.10 foreign cores. '
        f'Median foreign CPU: {median(r["foreign_cores"] for r in sweep):.2f} cores. '
        'Incomplete randomized repetitions; no aggregate speed claim is made.', '']
(ROOT / 'data/analysis.md').write_text('\n'.join(out))
print('\n'.join(out))
