#!/usr/bin/env python3
"""Check the experiment against public reference hashes; compare failures to baseline."""
import argparse
import json
from pathlib import Path
import subprocess
import time

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--baseline', required=True)
p.add_argument('--variant', required=True)
p.add_argument('--streams', required=True)
p.add_argument('--stream-dir', required=True)
p.add_argument('--out', required=True)
p.add_argument('--threads', type=int, default=2)
p.add_argument('--limit', type=int)
a = p.parse_args()
done = set()
if Path(a.out).exists():
    done = {json.loads(l)['stream'] for l in Path(a.out).read_text().splitlines()}
rows = [l.split('\t') for l in Path(a.streams).read_text().splitlines()
        if l and not l.startswith('#')]


def decode(binary, stream, nt):
    cmd = [binary, '-q', '-i', str(Path(a.stream_dir) / stream),
           '--threads', str(nt), '--framedelay', '1', '--filmgrain', '1',
           '--muxer', 'md5', '-o', '-']
    if a.limit:
        cmd += ['--limit', str(a.limit)]
    start = time.monotonic()
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=180)
        return dict(rc=r.returncode, md5=r.stdout.decode().strip(),
                    stderr=r.stderr.decode(errors='replace'),
                    wall_s=time.monotonic() - start, argv=cmd)
    except subprocess.TimeoutExpired:
        return dict(rc=None, timeout=True, argv=cmd)


with open(a.out, 'a', buffering=1) as out:
    for index, row in enumerate(rows):
        stream, _, _, _, expected = row[:5]
        if stream in done:
            continue
        variant = decode(a.variant, stream, a.threads)
        result = dict(stream=stream, expected=None if a.limit else expected,
                      variant=variant, threads=a.threads, limit=a.limit)
        result['has_diagnostics'] = bool(variant.get('stderr'))
        if a.limit or variant['rc'] != 0 or variant.get('md5') != expected or result['has_diagnostics']:
            result['baseline'] = decode(a.baseline, stream, a.threads)
            result['matches_baseline'] = (
                variant['rc'] == result['baseline']['rc'] == 0 and
                variant.get('md5') == result['baseline'].get('md5'))
        result['matches_reference'] = (variant['rc'] == 0 and
                                       variant.get('md5') == expected) if not a.limit else None
        out.write(json.dumps(result) + '\n')
        print(index + 1, '/', len(rows), stream,
              'reference', result['matches_reference'],
              'baseline', result.get('matches_baseline'), flush=True)
