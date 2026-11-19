#!/usr/bin/env bash
set -euo pipefail
task_root=$(cd "$(dirname "$0")/.." && pwd)
cd "$task_root/../../"
while systemctl --user is-active --quiet dav2d-threading-ab-core-check.service; do
    sleep 5
done
python - "$task_root/data/ab-core-correctness.jsonl" <<'PY'
import json,sys
rows=[json.loads(l) for l in open(sys.argv[1])]
assert len(rows)==6 and all(r['matches_reference'] for r in rows), rows
PY
common=(
    --baseline "$task_root/.work/ab/baseline-build/tools/dav2d"
    --variant "$task_root/.work/ab/three-pass-build/tools/dav2d"
    --streams "$task_root/data/streams.tsv"
    --stream-dir /srv/compression/cache/av2bench/streams
    --scratch "$task_root/.work/ab/bench-scratch"
    --max-wait 1200
    --max-foreign 0.20
)
python "$task_root/scripts/bench-ab.py" "${common[@]}" \
    --out "$task_root/data/ab-benchmark.jsonl" --configs 2:1,3:1 --reps 3
python "$task_root/scripts/bench-ab.py" "${common[@]}" \
    --out "$task_root/data/ab-control.jsonl" --configs 3:2 --reps 3
