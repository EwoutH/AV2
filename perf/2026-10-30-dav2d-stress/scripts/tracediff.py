import sys
def load(p):
    L = [l.rstrip() for l in open(p, errors='replace')]
    return [l.strip() for l in L if l.strip() and not l.startswith(('OBU', 'HDR', 'SEQHDR', 'decode_tile', 'Decoded', 'dav2d'))]
a = load(sys.argv[1]); b = load(sys.argv[2])
print(len(a), len(b))
for k, (x, y) in enumerate(zip(a, b)):
    if x != y:
        print('first diff at line', k)
        blocks = [l for l in a[:k] if l.startswith(('decode_sb', 'decode_b'))][-2:]
        frames = sum(1 for l in a[:k] if 'decode_sb[y=0,x=0,bs=' in l and 'plane=yuv' in l and l.startswith('decode_sb'))
        print('approx SB-(0,0) count before (frame idx-ish):', frames)
        print('last blocks:', *blocks, sep='\n  ')
        for j in range(max(0, k - 8), k + 3): print('AVM', a[j] if j < len(a) else '')
        print('---')
        for j in range(max(0, k - 8), k + 3): print('DAV', b[j] if j < len(b) else '')
        break
else:
    print('identical over', min(len(a), len(b)))
