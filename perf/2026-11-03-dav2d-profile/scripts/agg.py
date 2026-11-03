import json,collections,math,sys
d=json.load(open(sys.argv[1]))
def share(b,ten):
    S=collections.defaultdict(list)
    names=[n for n in d if d[n]['ten']==ten]
    for n in names:
        r=d[n][b]; tot=r['tot']
        fams=collections.Counter()
        for k,v in r['g'].items(): fams[k]+=v/tot
        for k in set(x for n2 in names for x in d[n2][b]['g']): S[k].append(fams.get(k,0))
    return {k:sum(v)/len(v) for k,v in S.items()}, len(names)
for ten in (True,False):
    sa,n=share('dav2d',ten); sn,_=share('dav2d_noasm',ten)
    print(f"\n=== {'10' if ten else '8'}-bit, {n} streams: mean share of 1-thread CPU time")
    fams=sorted(set(k.split('|')[0] for k in sa)|set(k.split('|')[0] for k in sn), key=lambda f:-(sa.get(f+'|C',0)+sa.get(f+'|asm',0)))
    print(f"{'family':38} {'asm build: C':>12} {'asm':>6} {'no-asm build':>12}")
    for f in fams:
        print(f"{f:38} {100*sa.get(f+'|C',0):11.1f}% {100*sa.get(f+'|asm',0):5.1f}% {100*(sn.get(f+'|C',0)+sn.get(f+'|asm',0)):11.1f}%")
# time ratio asm/noasm per stream overall and per family (8-bit: asm speed-up per family)
print("\n=== per-family speed-up of the asm build over the no-asm build (geomean over streams, samples on the same 40 frames)")
for ten in (False,True):
    acc=collections.defaultdict(list); tot=[]
    for n in d:
        if d[n]['ten']!=ten: continue
        a=d[n]['dav2d']; c=d[n]['dav2d_noasm']
        tot.append(c['tot']/a['tot'])
        fa=collections.Counter(); fc=collections.Counter()
        for k,v in a['g'].items(): fa[k.split('|')[0]]+=v
        for k,v in c['g'].items(): fc[k.split('|')[0]]+=v
        for f in fc:
            if fa[f]>20 and fc[f]>20: acc[f].append(fc[f]/fa[f])
    g=lambda v: math.exp(sum(map(math.log,v))/len(v))
    print(f"-- {'10' if ten else '8'}-bit: whole decode {g(tot):.2f}x")
    for f,v in sorted(acc.items(),key=lambda x:-g(x[1])): print(f"   {f:38} {g(v):5.2f}x  (n={len(v)})")
