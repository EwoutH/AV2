#!/usr/bin/env python3
"""Exercise the existing upstream seek/flush stress tool under sanitizers."""
import argparse
import json
import subprocess

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--binary', required=True)
p.add_argument('--stream', required=True)
p.add_argument('--out', required=True)
a = p.parse_args()
with open(a.out, 'a', buffering=1) as out:
    for nt in [2, 3]:
        argv = [a.binary, '-q', '-i', a.stream,
                '--threads', str(nt), '--framedelay', '1']
        try:
            run = subprocess.run(argv, capture_output=True, timeout=180)
            row = dict(threads=nt, rc=run.returncode,
                       stderr=run.stderr.decode(errors='replace'), argv=argv)
        except subprocess.TimeoutExpired:
            row = dict(threads=nt, rc=None, timeout=True, argv=argv)
        out.write(json.dumps(row) + '\n')
        print(row, flush=True)
