"""Full-stream C coverage proxy, not coverage of the selected debug window."""
import hashlib,json,os,subprocess as sp
from pathlib import Path
P=Path(__file__).resolve().parents[1]
C=Path('/srv/compression/cache/av2conf/round5/build/main-cov/tools/dav2d')
base=json.loads((P/'data/baseline.json').read_text())['samples']
vectors={}; rows=[]
for r in base:
 out=P/'scratch/coverage.bin'
 out.unlink(missing_ok=True)
 p=sp.run([str(C),'-q','--threads=1','--filmgrain=1','-i',str(P/'scratch/baseline'/Path(r['filename']).name),'--verify',r['expected_md5']],env={**os.environ,'COV_OUT':str(out)},stdout=sp.DEVNULL,stderr=sp.PIPE,timeout=60)
 if p.returncode: raise RuntimeError((r['name'],p.stderr.decode()))
 v=out.read_bytes(); vectors[r['filename']]={i for i,b in enumerate(v) if b}
 rows.append(dict(filename=r['filename'],guards_hit=len(vectors[r['filename']]),verify_ok=True))
sets={'original6':[r['filename'] for r in base if r['equal'] and '64x64' in r['filename'] and 'v15.0.0' in r['filename']], 'baseline14':[r['filename'] for r in base if r['equal']], 'all38':[r['filename'] for r in base]}
for label in ['fixed-first','fixed']:
 f=P/'data'/f'{label}.json'
 if f.exists(): sets[label]=[r['filename'] for r in json.loads(f.read_text())['samples'] if r['equal']]
res={}
for name, files in sets.items():
 hit=set().union(*(vectors[f] for f in files))
 res[name]=dict(streams=len(files),guards_hit=len(hit),added_over_original6=len(hit-set().union(*(vectors[f] for f in sets['original6']))))
(P/'data/coverage.json').write_text(json.dumps(dict(binary_sha256=hashlib.sha256(C.read_bytes()).hexdigest(),guards=len(v),sets=res,samples=rows),indent=2)+'\n')
print(json.dumps(res,indent=2))
