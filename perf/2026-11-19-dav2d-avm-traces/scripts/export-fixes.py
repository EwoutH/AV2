"""Keep source fixes separate from the CI-only debug toggles."""
import difflib,subprocess as sp
from pathlib import Path
P=Path(__file__).resolve().parents[1]
T=Path('/srv/compression/cache/av2conf/round5/trace')
def diff(path,old,new):
 return f'diff --git a/{path} b/{path}\n'+('new file mode 100644\n' if not old else '')+''.join(difflib.unified_diff(old.splitlines(True),new.splitlines(True),fromfile=f'a/{path}' if old else '/dev/null',tofile=f'b/{path}'))
path='src/recon_tmpl.c';old=(T/'dav2d'/path).read_text();new=(P/'scratch/dav2d'/path).read_text()
(P/'patches/03-dav2d-prediction-traces.patch').write_text(diff(path,old,new))
avm=''
for path in ['av2/decoder/obu_ci.c','av2/common/tip.c','av2/decoder/decodeframe.c','av2/decoder/obu.c','av2/decoder/decodemv.c','av2/decoder/obu_fgm.c']:
 avm+=diff(path,(T/'avm'/path).read_text(),(P/'scratch/avm'/path).read_text())
mail='''From: Ewout ter Hoeven <15776622+EwoutH@users.noreply.github.com>
Date: Thu, 19 Nov 2026 22:00:00 +0100
Subject: [PATCH] Align debug output with the selected dav2d trace region

Limit TIP dumps to output pictures in the selected region, and inter
prediction dumps to the first 64x64 chunk. Print suffix metadata headers
and derived segment IDs, correct the color labels, and use zero for
absent chroma grain multipliers.

---
'''+avm
name='patches/0006-Align-debug-output-with-the-selected-dav2d-trace.patch'
(P/'patches/04-avm-debug-output.patch').write_text(diff(name,'',mail))
(P/'scratch/avm-fixes.mbox').write_text(mail)
for name in ['dav2d','avm']:
 toggles=sp.check_output(['git','-C',str(T/name),'diff'],text=True)
 (P/'data'/f'{name}-ci-debug-enables.patch').write_text(toggles)
