#!/usr/bin/env python3
"""Plot the completed frequency-hinted, PMU-counted series and unchanged control."""
import csv
from pathlib import Path

root = Path(__file__).resolve().parents[1]
rows = list(csv.DictReader((root / 'data/ab-summary.csv').open()))
main = [r for r in rows if r['series'] == 'ab-perf-benchmark.jsonl']
control = [r for r in rows if r['series'] == 'ab-perf-control.jsonl']
if len(main) != 12 or len(control) != 6 or any(int(r['pairs']) != 3 for r in main + control):
    raise SystemExit('Plot deferred: planned primary/control series incomplete')

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

streams = sorted({r['stream'] for r in main})
labels = {
    'Netflix_Driving': 'DrivingPOV · 720p · 10-bit',
    'Noise_Ocean': 'Ocean + grain · 1080p',
    'Slides1': 'Slides · 1080p',
    'crowd_run': 'Crowd · 1080p',
    'old_town': 'Old town · 1080p · 4×2 tiles',
    'FourPeople': 'FourPeople · 270p',
}
fig, ax = plt.subplots(figsize=(10, 5.5))
for nt, color, offset in [(2, '#1674a5', -.13), (3, '#d77224', .13)]:
    selected = {r['stream']: r for r in main if int(r['threads']) == nt}
    for i, stream in enumerate(streams):
        r = selected[stream]
        value = float(r['speed_ratio'])
        ax.errorbar(value, i + offset,
                    xerr=[[value - float(r['speed_min'])], [float(r['speed_max']) - value]],
                    fmt='o', color=color, capsize=3,
                    label=f'{nt} workers, one frame' if i == 0 else None)
for i, stream in enumerate(streams):
    r = next(r for r in control if r['stream'] == stream)
    ax.scatter(float(r['speed_ratio']), i + .32, marker='x', color='#777777',
               label='3 workers, two-frame control' if i == 0 else None)
ax.axvline(1, color='#777777', linestyle='--', linewidth=1)
ax.set_yticks(range(len(streams)),
              [next(v for k, v in labels.items() if k in s) for s in streams])
ax.invert_yaxis()
ax.set_xlabel('Variant throughput / baseline throughput (higher is faster)')
ax.set_title('Three-pass decoding with one frame in flight')
ax.grid(axis='x', alpha=.2)
ax.legend(loc='best', fontsize=8)
fig.text(.01, .01, 'i5-4590 · GCC 16.2 · uclamp min=max=1024 · '
         '130 frames/process · bars: range of 3 accepted paired runs', fontsize=8)
fig.tight_layout(rect=(0, .04, 1, 1))
out = root / 'figures'
out.mkdir(exist_ok=True)
for suffix in ['svg', 'png']:
    fig.savefig(out / f'ab-throughput.{suffix}', dpi=150)
