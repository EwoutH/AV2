#!/usr/bin/env python3
"""Summarize accepted paired A/B runs without treating repeats as new streams."""
from collections import defaultdict
import csv
import json
from pathlib import Path
from statistics import geometric_mean, median

root = Path(__file__).resolve().parents[1]
tables = []
summary = []
for filename in ['ab-benchmark.jsonl', 'ab-control.jsonl',
                 'ab-clamped-benchmark.jsonl', 'ab-clamped-control.jsonl',
                 'ab-perf-benchmark.jsonl', 'ab-perf-control.jsonl']:
    path = root / 'data' / filename
    if not path.exists():
        continue
    rows = [json.loads(l) for l in path.read_text().splitlines()]
    groups = defaultdict(list)
    for r in rows:
        if r['accepted']:
            groups[r['stream'], r['threads'], r['framedelay']].append(r)
    expected = 18 if 'control' in filename else 36
    complete = len({(r['rep'], r['stream'], r['threads'], r['framedelay'])
                    for r in rows if r['accepted']}) == expected
    tables += [f'## {filename}', '',
               'Complete planned series.' if complete else 'Incomplete series: exploratory observations only.', '',
               f'{len(rows)} attempted pairs; {sum(r["accepted"] for r in rows)} accepted.', '',
               '| Stream | Workers / delay | Pairs | Speed ratio, median [range] | CPU ratio | Cycle ratio | Instruction ratio | RSS delta |',
               '|---|---:|---:|---:|---:|---:|---:|---:|']
    for (stream, nt, fd), rs in sorted(groups.items()):
        speed = [r['results']['baseline']['wall_s'] / r['results']['three_pass']['wall_s'] for r in rs]
        cpu = [r['results']['three_pass']['cpu_s'] / r['results']['baseline']['cpu_s'] for r in rs]
        rss = [(r['results']['three_pass']['maxrss_kb'] - r['results']['baseline']['maxrss_kb']) / 1024 for r in rs]
        pmu = {}
        for counter in ['cycles', 'instructions']:
            values = [r['results']['three_pass']['perf'][counter]['scaled'] /
                      r['results']['baseline']['perf'][counter]['scaled'] for r in rs
                      if all((r['results'][v].get('perf') or {}).get(counter, {}).get('scaled')
                             for v in ['baseline', 'three_pass'])]
            pmu[counter] = median(values) if values else None
        counters = ['—' if pmu[c] is None else f'{pmu[c]:.3f}' for c in ['cycles', 'instructions']]
        tables.append(f'| {Path(stream).name} | {nt} / {fd} | {len(rs)} | '
                      f'{median(speed):.3f} [{min(speed):.3f}–{max(speed):.3f}] | '
                      f'{median(cpu):.3f} | {counters[0]} | {counters[1]} | {median(rss):+.1f} MiB |')
        summary.append(dict(series=filename, stream=stream, threads=nt, framedelay=fd,
                            pairs=len(rs), speed_ratio=median(speed),
                            speed_min=min(speed), speed_max=max(speed),
                            cpu_ratio=median(cpu), cycle_ratio=pmu['cycles'],
                            instruction_ratio=pmu['instructions'], rss_delta_mib=median(rss)))
    for nt, fd in sorted({(r['threads'], r['framedelay']) for r in rows}):
        selected = [r for r in summary if r['series'] == filename and
                    r['threads'] == nt and r['framedelay'] == fd]
        if selected:
            tables += ['', f'{nt} workers, delay {fd}: geometric mean of per-stream median speed ratios '
                       f'= **{geometric_mean(r["speed_ratio"] for r in selected):.3f}×**, '
                       f'{len(selected)} streams.']
    tables += ['', 'Speed ratio = baseline wall time / variant wall time; >1 favors the variant. '
               'CPU ratio = variant CPU time / baseline CPU time; <1 favors the variant. '
               'Ranges describe the accepted repetitions, not confidence intervals.', '']
if summary:
    with (root / 'data/ab-summary.csv').open('w') as out:
        writer = csv.DictWriter(out, fieldnames=list(summary[0]), lineterminator='\n')
        writer.writeheader()
        writer.writerows(summary)
(root / 'data/ab-summary.md').write_text('\n'.join(tables))
print('\n'.join(tables))
