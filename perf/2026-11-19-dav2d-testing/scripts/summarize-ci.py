"""Generate the complete job/configuration/cost matrix from captured evidence."""
import csv
import json
from pathlib import Path
import re
import statistics
import yaml

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data'
config = yaml.safe_load((DATA / 'dav2d-ci.yml').read_text())

def resolve(name):
    entry = config[name]
    out = {}
    parents = entry.get('extends', [])
    if isinstance(parents, str):
        parents = [parents]
    for parent in parents:
        out.update(resolve(parent))
    out.update(entry)
    return out

jobs = {}
for filename in sorted(DATA.glob('4935-*-jobs.json')):
    for job in json.loads(filename.read_text()):
        jobs.setdefault(job['name'], []).append(job)

rows = []
for name, versions in sorted(jobs.items(), key=lambda item: (item[1][0]['stage'], item[0])):
    base = name.split(': [')[0]
    entry = resolve(base)
    scripts = entry.get('script', [])
    options = []
    tests = []
    for script in scripts:
        if not isinstance(script, str):
            continue
        if 'meson setup' in script:
            options += re.findall(r'--buildtype\s+\w+|--default-library\s+\w+|--cross-file\s+\S+|-D\S+|--werror', script)
        if 'meson test' in script:
            tests.append(' '.join(script.split()))
    if base in ('test-debian-riscv64', 'test-debian-aarch64-qemu'):
        options = ['inherits release/testdata/logging=false/trim_dsp=false from build artifact']
    environment = ' '.join(f'{k}={v}' for k, v in entry.get('variables', {}).items())
    row = dict(job=name, run_median=round(statistics.median(j['duration'] for j in versions), 2),
               run_min=round(min(j['duration'] for j in versions), 2),
               run_max=round(max(j['duration'] for j in versions), 2),
               queue_median=round(statistics.median(j['queued_duration'] for j in versions), 2),
               tags=','.join(entry.get('tags', [])), environment=environment, options=' '.join(options),
               tests='; '.join(tests) or 'none',
               url=next(j['web_url'] for j in versions if j['pipeline']['id'] == 753287))
    rows.append(row)
with (DATA/'ci-matrix.tsv').open('w') as f:
    writer = csv.DictWriter(f, fieldnames=list(rows[0]), delimiter='\t', lineterminator='\n')
    writer.writeheader()
    writer.writerows(rows)
lines = [
    '# Complete CI job matrix', '',
    'Source: dav2d `2ea62cc8`, upstream pipelines [753097](https://code.videolan.org/videolan/dav2d/-/pipelines/753097), [753262](https://code.videolan.org/videolan/dav2d/-/pipelines/753262), [753287](https://code.videolan.org/videolan/dav2d/-/pipelines/753287). Durations are seconds, median [minimum–maximum]; queue is a separate median. Three observations describe these runs, not a long-term benchmark. Summed job time is runner occupancy, not CPU time or pipeline latency.', '',
    'All 49 expanded jobs are below. Runtime commands are exact after YAML inheritance; `${CROSSFILE}` and `$DEPTH` are expanded by the job matrix shown in the name. Default bitdepths are `8,16` (the latter supports 10/12-bit); default asm is on; default `trim_dsp=if-release`. Only jobs enabling `testdata_tests` clone/register the corpus. `meson test` in a build-only job means headers and, where enabled, checkasm; it does not imply decoding corpus samples.', '',
    '| Job | Run s [range] | Queue s | Build options | Runtime |',
    '|---|---:|---:|---|---|',
]
for r in rows:
    build = ' '.join(x for x in [r['tags'], r['environment'], r['options']] if x)
    lines.append(f"| [{r['job']}]({r['url']}) | {r['run_median']} [{r['run_min']}–{r['run_max']}] | {r['queue_median']} | `{build}` | `{r['tests'].replace('|', '∣')}` |")
(ROOT/'CI-MATRIX.md').write_text('\n'.join(lines)+'\n')
print('Wrote', len(rows), 'job rows')
