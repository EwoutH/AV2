"""Check each independent print fix against the original 14-sample trace list."""
import json,subprocess as sp,time
from pathlib import Path
P=Path(__file__).resolve().parents[1]
S=P/'scratch';D=S/'publish-dav2d';T=Path('/srv/compression/cache/av2conf/round5/trace')
entries=json.loads((P/'data/printing-branches.json').read_text())
paths=[('dav2d','src/recon_tmpl.c')]+[('avm',e['avm_path']) for e in entries if e['kind']=='avm']
original={(repo,file):(T/repo/file).read_text() for repo,file in paths}
saved={(repo,file):(S/repo/file).read_text() for repo,file in paths}
def write(repo,file,content):
 path=S/repo/file
 if path.read_text()!=content:path.write_text(content)
def build(label):
 with (S/(label+'-build.log')).open('wb') as log:
  for repo,target in [('avm','avmdec'),('dav2d','tools/dav2d')]:
   sp.run(['ninja','-j3','-C',str(S/(repo+'-build')),target],stdout=log,stderr=sp.STDOUT,check=True,timeout=180)
results=[]
try:
 for e in entries:
  for (repo,file),content in original.items():write(repo,file,content)
  content=sp.check_output(['git','-C',str(D),'show',e['sha']+':'+e['path']])
  if e['kind']=='dav2d':write('dav2d',e['path'],content.decode())
  else:
   sp.run(['git','-C',str(S/'avm'),'apply','-'],input=content,check=True)
  start=time.monotonic();build(e['branch'])
  with (S/(e['branch']+'-trace.log')).open('wb') as log:
   result=sp.run(['sh',str(S/'publish-dav2d-test-data/check-traces.sh'),str(S/'avm-build/avmdec'),str(S/'dav2d-build/tools/dav2d')],cwd=S,stdout=log,stderr=sp.STDOUT,timeout=90)
  assert result.returncode==0,(e['branch'],result.returncode)
  row=dict(branch=e['branch'],sha=e['sha'],trace_samples=14,success=True,seconds=time.monotonic()-start);results.append(row)
  print(json.dumps(row),flush=True)
finally:
 for (repo,file),content in saved.items():write(repo,file,content)
 build('restore-combined')
(P/'data/printing-individual-validation.json').write_text(json.dumps(results,indent=2)+'\n')
print('All eight fixes independently preserve the original 14 trace comparisons; combined source restored.',flush=True)
