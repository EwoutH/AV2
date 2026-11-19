"""Audit a frozen public test-data ref with original or experimental trace binaries."""
import argparse
import difflib
import hashlib
import json
from pathlib import Path
import re
import subprocess as sp
import time

P = Path(__file__).resolve().parents[1]
T = Path('/srv/compression/cache/av2conf/round5/trace')
TD = '/srv/compression/projects/dav2d-test-data'
a = argparse.ArgumentParser()
a.add_argument('--variant', choices=['baseline', 'fixed'], required=True)
a.add_argument('--ref', default='a6aa3b48debdd20d2d6405a3fde68fe2a344bbb2')
args = a.parse_args()
ref = sp.check_output(['git', '-C', TD, 'rev-parse', args.ref], text=True).strip()
bins = [T/'avm-x86-12/avmdec', T/'dav2d-build/tools/dav2d'] if args.variant == 'baseline' else [P/'scratch/avm-build/avmdec', P/'scratch/dav2d-build/tools/dav2d']
work = P/'scratch'/args.variant
work.mkdir(exist_ok=True)
rows = []
for directory in ['avm', 'avm-10bit']:
    manifest = sp.check_output(['git','-C',TD,'show', f'{ref}:{directory}/meson.build'], text=True)
    for name, filename, md5 in re.findall(r"\['([^']+)', files\('([^']+)'\), '([a-f0-9]{32})'", manifest):
        blob = sp.check_output(['git','-C',TD,'show', f'{ref}:{directory}/{filename}'])
        sample = work/filename
        sample.write_bytes(blob)
        cmds = [[str(bins[0]), str(sample), '-o', '/dev/null'], [str(bins[1]), '-i', str(sample), '--muxer=null','--threads=1','--quiet']]
        times, codes, logs = [], [], []
        for label, cmd in zip(['avm', 'dav2d'], cmds):
            start = time.monotonic()
            proc = sp.run(cmd, capture_output=True, timeout=90)
            times.append(time.monotonic()-start)
            codes.append(proc.returncode)
            logs.append(proc.stdout.decode().splitlines(keepends=True))
            (work/f'{name}.{label}.txt').write_bytes(proc.stdout)
        equal = sp.run(['diff','-uw',str(work/f'{name}.avm.txt'),str(work/f'{name}.dav2d.txt')], stdout=sp.DEVNULL).returncode == 0
        checks = []
        # Independent full-output MD5s; traces only cover a selected region/window.
        avm = sp.run([str(bins[0]), '--md5','--rawvideo',str(sample)],capture_output=True,timeout=90)
        hashes = re.findall(rb'^([a-f0-9]{32})  -$', avm.stdout, re.M)
        checks.append(avm.returncode == 0 and hashes == [md5.encode()])
        dav = sp.run([str(bins[1]), '-q','--threads=1','--filmgrain=1','-i',str(sample),'--verify',md5],stdout=sp.DEVNULL,stderr=sp.PIPE,timeout=90)
        checks.append(dav.returncode == 0)
        diff = ''.join(difflib.unified_diff(*logs, fromfile='avm', tofile='dav2d', n=1))
        (P/'data'/f'{args.variant}-{name}.diff').write_text(diff[:8000])
        rows.append(dict(name=name, filename=f'{directory}/{filename}', expected_md5=md5, md5_ok=checks, returncodes=codes, equal=equal, seconds=times, sha256=hashlib.sha256(blob).hexdigest()))
        print(name, 'equal' if equal else 'DIFF', 'MD5', checks,flush=True)
provenance = {str(b): hashlib.sha256(b.read_bytes()).hexdigest() for b in bins}
(P/'data'/f'{args.variant}.json').write_text(json.dumps(dict(testdata_ref=ref,binaries=provenance,samples=rows),indent=2)+'\n')
