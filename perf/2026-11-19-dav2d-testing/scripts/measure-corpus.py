"""Measure only public git samples with the existing trace-pc-guard build."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]
SCRATCH = ROOT / 'scratch'
SCRATCH.mkdir(exist_ok=True)
TD = '/srv/compression/projects/dav2d-test-data'
COV = '/srv/compression/cache/av2conf/round5/build/main-cov/tools/dav2d'

def git(*args):
    return subprocess.check_output(['git', '-C', TD, *args])

def manifest(ref):
    rows = []
    for directory in ('avm', 'avm-10bit'):
        s = git('show', f'{ref}:{directory}/meson.build').decode()
        for line in s.splitlines():
            m = re.search(r"\['([^']+)', files\('([^']+)'\), '([a-f0-9]{32})'", line)
            if m:
                name, filename, md5 = m.groups()
                rows.append((name, f'{directory}/{filename}', md5))
    return rows

refs = ['origin/main', 'add-round3-samples', 'add-coverage-samples', 'ci-frame-threads']
results = {}
vectors = {}
for ref in refs:
    rows = manifest(ref)
    union = set()
    size = 0
    for name, filename, md5 in rows:
        data = git('show', f'{ref}:{filename}')
        key = hashlib.sha256(data).hexdigest()
        size += len(data)
        if key not in results:
            sample = SCRATCH / 'sample.obu'
            sample.write_bytes(data)
            covout = SCRATCH / 'edges.bin'
            covout.unlink(missing_ok=True)
            start = time.monotonic()
            proc = subprocess.run([COV, '-q', '--threads', '1', '--filmgrain=1',
                                   '-i', str(sample), '--verify', md5],
                                  env={**os.environ, 'COV_OUT': str(covout)},
                                  capture_output=True, timeout=60)
            if proc.returncode or not covout.exists():
                raise RuntimeError((name, proc.returncode, proc.stderr.decode()))
            vector = covout.read_bytes()
            vectors[key] = {i for i, value in enumerate(vector) if value}
            results[key] = dict(name=name, filename=filename, md5=md5,
                                sha256=key, size=len(data), edges=len(vectors[key]),
                                guards=len(vector), seconds=time.monotonic()-start)
        union |= vectors[key]
    summary = dict(ref=ref, sha=git('rev-parse', ref).decode().strip(),
                   streams=len(rows), bytes=size, hit_guards=len(union),
                   total_guards=len(vector),
                   samples=[results[hashlib.sha256(git('show', f'{ref}:{f}')).hexdigest()]
                            for _, f, _ in rows])
    (ROOT / 'data' / f'corpus-{ref.replace("/", "-")}.json').write_text(json.dumps(summary, indent=2)+'\n')
    print(ref, len(rows), size, len(union), '/', len(vector), flush=True)
