import sys, re, glob, os, collections
D = sys.argv[1]
TEN = {'Skater227','DinnerSceneCropped','TunnelFlag','Netflix_DrivingPOV','MissionControlClip1','CosmosTreeTrunk','SparksTruck','RitualDance'}
FAM = [
 ('GDF', r'gdf|compute_gradient_row'),
 ('Wiener (LR)', r'wiener|calc_features|add_features|lr_|restoration'),
 ('CCSO', r'ccso'),
 ('Deblock', r'deblock|setup_thr|create_db_mask|lpf|loopfilter'),
 ('CDEF', r'cdef'),
 ('TMV projection (load_tmvs)', r'load_tmvs|check_traj|tip_projection|tip_fill_holes|tip_smoothen|fill_gap'),
 ('Other refmvs (spatial MV)', r'refmvs|add_spatial|splat|_mv_|scan_|add_tpl|mvstack|reset_sb'),
 ('Inter pred (MC/warp/opfl/TIP)', r'rmv_|put_|prep_|avg|mask|blend|warp|emu_edge|morph|opfl|sad|^mc|mc\.|mc_|tip_pred|obmc|bilin|8tap|refine'),
 ('Inverse transform (itx/stx/cctx)', r'itx|txfm|inv_|_dct|_adst|idtx|stx|cctx|identity|flipadst|wht'),
 ('Intra pred', r'ipred|cfl|pal|intra|dip|smooth|paeth|z[123]_|mhccp|dc_'),
 ('Film grain', r'grain|fg[yu]'),
 ('Entropy decode + parse', r'msac|decode_|read_|parse|coef|get_|ctx|obu'),
]
def fam(s):
    for n, r in FAM:
        if re.search(r, s): return n
    return 'Other'
def isasm(s): return bool(re.search(r'_(sse2|ssse3|sse4|avx2|avx512icl)\b|_(sse2|ssse3|sse4|avx2|avx512icl)\.|^\.\.@', s))
rows = collections.defaultdict(dict)
for f in glob.glob(f'{D}/dav2d*.tsv'):
    b, n = os.path.basename(f)[:-4].split('.', 1)
    short = n.split('_')[0]
    if short == 'Netflix': short = 'Netflix_DrivingPOV'
    tot = 0; g = collections.Counter()
    for l in open(f):
        p = l.rstrip('\n').split('\t')
        if len(p) < 2: continue
        c = int(p[0]); s = p[1].split('] ')[-1].strip(); tot += c
        if '[k]' in p[1]: g[('Kernel', 'k')] += c; continue
        g[(fam(s), 'asm' if isasm(s) else 'C')] += c
    rows[b][n] = (short in TEN, tot, g)
import json
out = {}
for b in rows:
    for n, (ten, tot, g) in rows[b].items():
        out.setdefault(n, {'ten': ten})[b] = {'tot': tot, 'g': {f'{k[0]}|{k[1]}': v for k, v in g.items()}}
json.dump(out, open(sys.argv[2], 'w'), indent=1)
