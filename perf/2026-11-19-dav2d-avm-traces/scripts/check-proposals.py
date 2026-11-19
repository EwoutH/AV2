"""Exercise the shared runner and measure its added trace-loop cost locally."""
import json,statistics,subprocess as sp,time,os
from pathlib import Path
P=Path(__file__).resolve().parents[1]
td=P/'scratch/td-proposal'
original=[Path('/srv/compression/cache/av2conf/round5/trace/avm-x86-12/avmdec'),Path('/srv/compression/cache/av2conf/round5/trace/dav2d-build/tools/dav2d')]
fixed=[P/'scratch/avm-build/avmdec',P/'scratch/dav2d-build/tools/dav2d']
rows=json.loads((P/'data/baseline.json').read_text())['samples']
sets={'original6':[r['filename'] for r in rows if r['equal'] and '64x64' in r['filename'] and 'v15.0.0' in r['filename']], 'baseline14':[r['filename'] for r in rows if r['equal']], 'fixed34':[r['filename'] for r in json.loads((P/'data/fixed.json').read_text())['samples'] if r['equal']]}
assert [len(sets[x]) for x in sets]==[6,14,34]
work=P/'scratch/runner';work.mkdir(exist_ok=True)
def run(bins):
 return sp.run(['sh',str(td/'check-traces.sh'),*map(str,bins)],cwd=work,stdout=sp.DEVNULL,stderr=sp.DEVNULL,timeout=90).returncode
listing=td/'trace-samples.txt';saved=listing.read_text();results={}
try:
 load=os.getloadavg();assert load[0]<1,load
 for name,files in sets.items():
  bins=fixed if name=='fixed34' else original
  listing.write_text('\n'.join(files)+'\n')
  times=[]
  for _ in range(5):
   start=time.monotonic();assert run(bins)==0;times.append(time.monotonic()-start)
  results[name]=dict(samples=len(files),seconds=times,median_seconds=statistics.median(times))
 # Smoke-check real failure modes, including a final line without a newline.
 listing.write_text(sets['baseline14'][0]);assert run(original)==0
 listing.write_text('');assert run(original)!=0
 listing.write_text('avm/missing.obu\n');assert run(original)!=0
 mismatch=next(r['filename'] for r in rows if r['name']=='avm.testsrc.176x144.l8.sframe')
 listing.write_text(mismatch+'\n');assert run(fixed)!=0
 listing.write_text(sets['baseline14'][0]+'\n');assert run([Path('/bin/false'),original[1]])!=0
 # Install the expanded candidate only after exercising the baseline proposal.
 listing.write_text(saved)
 sp.run(['git','-C',str(td),'apply',str(P/'patches/05-testdata-expand-after-fixes.patch')],check=True)
 assert run(fixed)==0
finally:
 listing.write_text(saved)
(P/'data/runner-validation.json').write_text(json.dumps(dict(load_before=load,sets=results,checks=['14 original traces pass','34 fixed traces pass','last line without newline passes','empty list fails','missing sample fails','real trace mismatch fails','decoder failure fails']),indent=2)+'\n')
print(json.dumps(results,indent=2))
