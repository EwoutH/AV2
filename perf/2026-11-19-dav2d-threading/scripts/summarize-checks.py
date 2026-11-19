#!/usr/bin/env python3
"""Summarize completed checks, keeping output matches separate from diagnostics."""
import json
from pathlib import Path
import re

root = Path(__file__).resolve().parents[1]
out = ['# Output and sanitizer checks', '',
       '| File | Completed / planned | Reference matches | Baseline-only matches | Diagnostics |',
       '|---|---:|---:|---:|---:|']
for name, planned in [('ab-core-correctness.jsonl', 6), ('ab-correctness.jsonl', 88),
                      ('ab-core-t3.jsonl', 6), ('ab-testdata-t2.jsonl', 16),
                      ('ab-testdata-t3.jsonl', 16), ('ab-asan-testdata.jsonl', 16),
                      ('ab-asan-core.jsonl', 6)]:
    p = root / 'data' / name
    rows = [json.loads(l) for l in p.read_text().splitlines()] if p.exists() else []
    ref = sum(r.get('matches_reference') is True for r in rows)
    same = sum(not r.get('matches_reference') and r.get('matches_baseline') is True for r in rows)
    diagnostic = sum(bool(r['variant'].get('stderr')) or r['variant']['rc'] != 0 for r in rows)
    out.append(f'| {name} | {len(rows)} / {planned} | {ref} | {same} | {diagnostic} |')
    for r in rows:
        if r['variant']['rc'] != 0 or not (r.get('matches_reference') or r.get('matches_baseline')):
            out += ['', f'Investigate `{name}`: `{r["stream"]}`.']
p = root / 'data/ab-asan-seek.jsonl'
if p.exists():
    rows = [json.loads(l) for l in p.read_text().splitlines()]
    sanitizer = re.compile('AddressSanitizer|UndefinedBehaviorSanitizer|LeakSanitizer|runtime error:')
    clean = sum(r['rc'] == 0 and not sanitizer.search(r.get('stderr', '')) for r in rows)
    out += ['', f'Seek/flush tool: {clean}/{len(rows)} runs exited successfully with no '
            'sanitizer diagnostic. The upstream tool does not verify output hashes and '
            'can return success after ordinary decoder errors; this is a lifecycle/sanitizer check.']
out += ['', 'ASan/UBSan checks use C code with assembly disabled. They do not establish '
        'race freedom. Prefix comparisons cover 16 output frames; the other output checks '
        'decode complete streams. Missing results are pending, not passes.', '']
(root / 'data/ab-checks.md').write_text('\n'.join(out))
print('\n'.join(out))
