"""Prepare independent print-only branches without changing the trace list."""
from pathlib import Path
import subprocess as sp,difflib,json,email.utils,datetime
P=Path(__file__).resolve().parents[1]
D=P/'scratch/publish-dav2d'
T=Path('/srv/compression/cache/av2conf/round5/trace')
def run(*args):return sp.check_output(['git','-C',str(D),*args],text=True).strip()
def diff(path,old,new):return ''.join(difflib.unified_diff(old.splitlines(True),new.splitlines(True),fromfile=f'a/{path}',tofile=f'b/{path}'))
old=(T/'dav2d/src/recon_tmpl.c').read_text()
palette=old.replace('''        if (BLOCK_TO_DEBUG && DEBUG_B_PIXELS)
            hex_dump(dst, f->cur.p.stride[0], imin(f->bw - t->bx, bw4) * 4,
                     imin(f->bh - t->by, bh4) * 4, "y-pal-pred");
''','')
mark='''    if (eob != -1) {
        const int mask_idx = bx4 >> 4;'''
palette=palette.replace(mark,'''    if (b->intra && !b->intrabc && b->pal_sz &&
        BLOCK_TO_DEBUG && DEBUG_B_PIXELS)
    {
        hex_dump(dst, f->cur.p.stride[0], tw, th, "y-pal-pred");
    }

'''+mark)
scaling=old
start=scaling.index('        if (DEBUG_BLOCK_INFO)\n            printf("Off ');end=scaling.index('        const int w =',start)
scaling=scaling[:start]+scaling[end:]
scaling=scaling.replace('            if (DEBUG_BLOCK_INFO) printf("Emu\\n");\n','')
entries=[
 dict(branch='debug-palette-tx',title='debug: dump palette predictions per transform',body='Move the luma palette dump after coefficient decoding and use the\ntransform dimensions, matching the AVM trace. Leave palette prediction\nitself at block level.',path='src/recon_tmpl.c',content=palette,kind='dav2d'),
 dict(branch='debug-scaled-mc',title='debug: remove unmatched scaled-MC diagnostics',body='The scaled-MC offset and edge-emulation prints have no counterpart in\nthe AVM trace. Remove them while retaining the prediction and\nreconstruction dumps.',path='src/recon_tmpl.c',content=scaling,kind='dav2d')]
for branch,title,path,body in [
 ('avm-debug-color','avm: fix color-description trace labels','av2/decoder/obu_ci.c','Pass transfer characteristics and matrix coefficients in the order of\nthe printf labels. The parsed color values are unchanged.'),
 ('avm-debug-tip','avm: select TIP output-picture dumps','av2/common/tip.c','Dump the synthetic TIP picture here only when it is an output picture,\nand apply BLOCK_TO_DEBUG to its chunks. Reference predictions remain\ncovered by ordinary block dumps, as in dav2d.'),
 ('avm-debug-inter-region','avm: limit inter-prediction dumps to the selected region','av2/decoder/decodeframe.c','For a selected large block, dump only its first 64x64 prediction chunk,\nmatching the region selected by the dav2d instrumentation.'),
 ('avm-debug-suffix','avm: print suffix metadata OBU headers','av2/decoder/obu.c','Print the header for accepted suffix metadata and padding OBUs in the\nsecond OBU-reading loop, as in the main loop.'),
 ('avm-debug-segid','avm: print derived segment IDs','av2/decoder/decodemv.c','Print the spatially predicted segment ID before the skipped-block\nearly return. No entropy read is added.'),
 ('avm-debug-grain','avm: print zero for absent chroma grain fields','av2/decoder/obu_fgm.c','Print zero for absent chroma grain multipliers and offsets instead of\nsubtracting the signed bias from an unsigned default-zero value.')]:
 original=(T/'avm'/path).read_text();fixed=(P/'scratch/avm'/path).read_text()
 change='diff --git a/'+path+' b/'+path+'\n'+diff(path,original,fixed)
 mail='From: Ewout ter Hoeven <15776622+EwoutH@users.noreply.github.com>\nDate: '+email.utils.format_datetime(datetime.datetime.now(datetime.timezone.utc))+'\nSubject: [PATCH] '+title.removeprefix('avm: ')+'\n\n'+body+'\n\n---\n'+change
 filename='patches/0006-'+branch.removeprefix('avm-debug-')+'-trace.patch'
 entries.append(dict(branch=branch,title=title,body=body,path=filename,content=mail,kind='avm',avm_path=path))
for e in entries:
 exists=sp.run(['git','-C',str(D),'show-ref','--verify','--quiet','refs/heads/'+e['branch']]).returncode==0
 if exists:
  run('switch',e['branch'])
  assert run('log','-1','--format=%s')==e['title']
 else:
  run('switch','-c',e['branch'],'upstream/main')
  (D/e['path']).write_text(e['content'])
  run('add',e['path'])
  if e['kind']=='dav2d': run('diff','--cached','--check')
  run('commit','-m',e['title'],'-m',e['body'])
 e['sha']=run('rev-parse','HEAD')
 e.pop('content')
 print(e['branch'],e['sha'][:10])
run('switch','ci-avm-traces')
(P/'data/printing-branches.json').write_text(json.dumps(entries,indent=2)+'\n')
