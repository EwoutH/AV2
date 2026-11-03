import json,collections,math,sys
d=json.load(open(sys.argv[1]))
g=lambda v: math.exp(sum(map(math.log,v))/len(v))
F8={'GDF':14.83,'Wiener (LR)':11.96,'CCSO':10,'Deblock':2.95,'Inverse transform (itx/stx/cctx)':10}
def fam_c(r):
    c=collections.Counter()
    for k,v in r['g'].items():
        f,t=k.split('|')
        if t=='C': c[f]+=v
    return c
for label,fams in [('GDF only',['GDF']),('GDF+Wiener',['GDF','Wiener (LR)']),('GDF+Wiener+CCSO+deblock+itx',list(F8))]:
    sp=[]
    for n in d:
        if not d[n]['ten']: continue
        r=d[n]['dav2d']; c=fam_c(r); t=r['tot']
        new=t-sum(c[f] for f in fams)+sum(c[f]/F8[f] for f in fams)
        sp.append(t/new)
    print(f"10-bit, port {label}: {g(sp):.2f}x (range {min(sp):.2f}-{max(sp):.2f}) -> ~{0.63*g(sp):.2f}x avmdec")
for n in d:
    r=d[n]['dav2d']; c=fam_c(r)
    print(f"{n[:40]:40} {'10' if d[n]['ten'] else ' 8'} GDF_C {100*c['GDF']/r['tot']:5.1f}% LR_C {100*c['Wiener (LR)']/r['tot']:5.1f}% TMV {100*c['TMV projection (load_tmvs)']/r['tot']:5.1f}% FG {100*c['Film grain']/r['tot']:5.1f}%")
# load_tmvs 8-bit: what if 2x / removed
for k in (2,4):
    sp=[]
    for n in d:
        if d[n]['ten']: continue
        r=d[n]['dav2d']; c=fam_c(r)['TMV projection (load_tmvs)']; t=r['tot']
        sp.append(t/(t-c+c/k))
    print(f"8-bit load_tmvs {k}x faster: {g(sp):.3f}x overall (max {max(sp):.2f})")
