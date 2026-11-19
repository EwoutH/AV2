#!/usr/bin/env bash
set -uo pipefail
task_root=$(cd "$(dirname "$0")/.." && pwd)
while systemctl --user is-active --quiet dav2d-threading-ab-validation-v2.service; do
    sleep 5
done
BENCH_SERIES=ab-perf PERF_COUNTS=1 uclampset -m 1024 -M 1024 \
    bash "$task_root/scripts/run-ab.sh"
result=$?
python "$task_root/scripts/analyze-ab.py"
python "$task_root/scripts/summarize-checks.py"
python - "$task_root/data/ab-run-status.json" "$result" <<'PY'
from datetime import datetime
import json,sys
from pathlib import Path
p=Path(sys.argv[1]); root=p.parent
counts={}
for name, expected in [('ab-perf-benchmark.jsonl',36), ('ab-perf-control.jsonl',18)]:
    rows=[json.loads(l) for l in (root/name).read_text().splitlines()] if (root/name).exists() else []
    count=len({(r['rep'],r['stream'],r['threads'],r['framedelay']) for r in rows if r['accepted']})
    counts[name]=dict(accepted_pairs=count,expected_pairs=expected,complete=count==expected)
p.write_text(json.dumps(dict(exit_code=int(sys.argv[2]),timing=counts,
    updated=datetime.now().astimezone().isoformat()),indent=2)+'\n')
PY
exit "$result"
