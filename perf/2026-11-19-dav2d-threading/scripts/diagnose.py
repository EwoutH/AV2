#!/usr/bin/env python3
"""Collect per-worker diagnostics and check 130-frame hashes against baseline."""
import argparse
import json
from pathlib import Path
import subprocess

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--binary', required=True)
p.add_argument('--reference', required=True)
p.add_argument('--streams', required=True)
p.add_argument('--stream-dir', required=True)
p.add_argument('--out', required=True)
p.add_argument('--configs', default='2:1,2:2')
a = p.parse_args()
configs = [tuple(map(int, c.split(':'))) for c in a.configs.split(',')]
with open(a.out, 'a', buffering=1) as out:
    for line in Path(a.streams).read_text().splitlines():
        if not line or line.startswith('#'):
            continue
        stream = line.split('\t')[0]
        args = ['-q', '-i', str(Path(a.stream_dir) / stream), '--limit', '130',
                '--filmgrain', '1', '--muxer', 'md5', '-o', '-']
        ref = subprocess.run([a.reference, *args, '--threads', '1'],
                             capture_output=True, timeout=180, check=True)
        for nt, fd in configs:
            cmd = [a.binary, *args, '--threads', str(nt), '--framedelay', str(fd)]
            run = subprocess.run(cmd, capture_output=True, timeout=180)
            workers = [json.loads(l) for l in run.stderr.decode().splitlines()
                       if l.startswith('{"held_ns"')]
            result = dict(stream=stream, threads=nt, framedelay=fd,
                          rc=run.returncode, limit=130,
                          md5=run.stdout.decode().strip(),
                          reference_md5=ref.stdout.decode().strip(),
                          matches=run.returncode == 0 and run.stdout == ref.stdout,
                          workers=workers, argv=cmd)
            out.write(json.dumps(result) + '\n')
            print(stream, nt, fd, 'hash', result['matches'],
                  'worker records', len(workers), flush=True)
            if not result['matches'] or len(workers) != nt:
                raise SystemExit(run.stderr.decode())
