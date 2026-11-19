"""Recreate experimental sources from the frozen local clones; never overwrite them."""
import json
from pathlib import Path
import subprocess as sp
P=Path(__file__).resolve().parents[1]
S=P/'scratch';S.mkdir(exist_ok=True)
refs=json.loads((P/'data/patch-bases.json').read_text())
sources=[('dav2d','/srv/compression/projects/dav2d',refs['dav2d']),('avm','/srv/compression/cache/av2conf/round5/trace/avm','9123f33bfcd363293b21fa9082637a20ebb6881c'),('td-proposal','/srv/compression/projects/dav2d-test-data',refs['testdata'])]
if any((S/name).exists() for name,_,_ in sources):
 raise SystemExit('Source folders already exist in scratch; use the existing prepared trees.')
for name,source,ref in sources:
 sp.run(['git','clone','--shared',source,str(S/name)],check=True)
 sp.run(['git','-C',str(S/name),'checkout','--detach',ref],check=True)
for name,patch in [('dav2d','03-dav2d-prediction-traces.patch'),('dav2d','04-avm-debug-output.patch'),('td-proposal','02-testdata-shared-trace-list.patch')]:
 sp.run(['git','-C',str(S/name),'apply','--whitespace=nowarn',str(P/'patches'/patch)],check=True)
sp.run(['git','-C',str(S/'avm'),'am',str(S/'dav2d/patches/0006-Align-debug-output-with-the-selected-dav2d-trace.patch')],check=True)
for name in ['dav2d','avm']:
 sp.run(['git','-C',str(S/name),'apply',str(P/'data'/f'{name}-ci-debug-enables.patch')],check=True)
