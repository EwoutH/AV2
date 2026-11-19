"""Recheck the CI trace comparison on public samples; retain only summaries."""
import json
from pathlib import Path
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]
SCRATCH = ROOT / 'scratch'
TRACE = Path('/srv/compression/cache/av2conf/round5/trace')
TD = '/srv/compression/projects/dav2d-test-data'
rows = json.loads((ROOT / 'data/corpus-add-coverage-samples.json').read_text())['samples']
out = []
for row in rows:
    sample = SCRATCH / 'sample.obu'
    sample.write_bytes(subprocess.check_output(['git', '-C', TD, 'show',
                                               f"add-coverage-samples:{row['filename']}"]))
    start = time.monotonic()
    codes = []
    for name, cmd in [
        ('avm', [str(TRACE/'avm-x86-12/avmdec'), str(sample), '-o', '/dev/null']),
        ('dav2d', [str(TRACE/'dav2d-build/tools/dav2d'), '-i', str(sample),
                   '--muxer=null', '--threads=1', '--quiet'])]:
        with (SCRATCH / f'{name}.log').open('wb') as log:
            proc = subprocess.run(cmd, stdout=log, stderr=subprocess.PIPE, timeout=90)
        codes.append(proc.returncode)
    diff = subprocess.run(['diff', '-uw', str(SCRATCH/'avm.log'), str(SCRATCH/'dav2d.log')],
                          stdout=subprocess.DEVNULL).returncode
    result = dict(name=row['name'], filename=row['filename'], returncodes=codes,
                  trace_equal=diff == 0, seconds=time.monotonic()-start,
                  avm_bytes=(SCRATCH/'avm.log').stat().st_size,
                  dav2d_bytes=(SCRATCH/'dav2d.log').stat().st_size)
    out.append(result)
    print(row['name'], codes, diff == 0, flush=True)
(ROOT/'data/traces.json').write_text(json.dumps(out, indent=2)+'\n')
