"""Generate reviewable patches against frozen local upstream refs."""
import difflib,json,subprocess as sp
from pathlib import Path
P=Path(__file__).resolve().parents[1]
D=P/'patches';D.mkdir(exist_ok=True)
TD='/srv/compression/projects/dav2d-test-data'
DAV='/srv/compression/projects/dav2d'
refs=json.loads((P/'data/patch-bases.json').read_text())
def get(repo,ref,path): return sp.check_output(['git','-C',repo,'show',f'{ref}:{path}'],text=True)
def diff(path,old,new): return ''.join(difflib.unified_diff(old.splitlines(True),new.splitlines(True),fromfile=f'a/{path}' if old else '/dev/null',tofile=f'b/{path}'))
rows=json.loads((P/'data/baseline.json').read_text())['samples']
listing=''.join(r['filename']+'\n' for r in rows if r['equal'])
helper='''#!/bin/sh
set -eu

data=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
test -s "$data/trace-samples.txt"
while IFS= read -r sample || [ -n "$sample" ]; do
    test -f "$data/$sample"
    echo "Tracing $sample"
    "$1" "$data/$sample" -o /dev/null > avm.log
    "$2" -i "$data/$sample" --muxer=null --threads=1 --quiet > dav2d.log
    test -s avm.log
    test -s dav2d.log
    diff -uw avm.log dav2d.log
    wc -l avm.log
done < "$data/trace-samples.txt"
'''
davci=get(DAV,refs['dav2d'],'.gitlab-ci.yml')
start=davci.index('          files=(',davci.index('test-debian-avm:'))
end=davci.index('\ntest-debian-avx512:',start)
newdav=davci[:start]+'''          sh tests/dav2d-test-data/check-traces.sh \\
              "$PWD/avm/x86-64/avmdec" "$PWD/build/tools/dav2d"
'''+davci[end:]
(D/'01-dav2d-shared-trace-list.patch').write_text(diff('.gitlab-ci.yml',davci,newdav))
tdci=get(TD,refs['testdata'],'.gitlab-ci.yml')
# Reuse the existing trace job's source setup, preserving its trace window.
job=davci[davci.index('test-debian-avm:'):davci.index('\ntest-debian-avx512:')]
script=job[job.index('    script:'):job.index('        - meson setup build')]
script=script.replace('git am ../patches/*.patch','git am ../dav2d/patches/*.patch')
script=script.replace("|' src/", "|' dav2d/src/")
script=script.replace('          git diff\n        - |\n          mkdir x86-64', '          git diff\n        - |\n          mkdir x86-64')
script=script.replace('-DCONFIG_AV2_ENCODER=0','-DCONFIG_AV2_ENCODER=0 -DCONFIG_TESTONLY_12BIT_SUPPORT=1')
# The second git diff runs from the test-data checkout.
last=script.rfind('          git diff\n')
script=script[:last]+script[last:].replace('          git diff\n','          git -C dav2d diff\n',1)
newjob='''test-avm-traces:
    extends: .test-common
    image: registry.videolan.org/vlc-debian-unstable:20260908103441
    artifacts:
        when: on_failure
        paths:
            - avm.log
            - dav2d.log
'''+script+'''        - meson setup build dav2d --buildtype debugoptimized -Dtrim_dsp=false
        - ninja -C build tools/dav2d
        - sh check-traces.sh "$PWD/avm/x86-64/avmdec" "$PWD/build/tools/dav2d"

'''
newtd=tdci.replace('check-samples-listed:\n',newjob+'check-samples-listed:\n')
(D/'02-testdata-shared-trace-list.patch').write_text(diff('trace-samples.txt','',listing)+diff('check-traces.sh','',helper)+diff('.gitlab-ci.yml',tdci,newtd))
(P/'data/patch-bases.json').write_text(json.dumps(refs,indent=2)+'\n')
(P/'scratch/trace-samples.txt').write_text(listing)
(P/'scratch/check-traces.sh').write_text(helper)
(P/'scratch/proposed-testdata-ci.yml').write_text(newtd)
print(refs)
