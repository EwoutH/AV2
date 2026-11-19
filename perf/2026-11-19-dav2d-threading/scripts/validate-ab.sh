#!/usr/bin/env bash
set -euo pipefail
task_root=$(cd "$(dirname "$0")/.." && pwd)
cd "$task_root/../../"
while systemctl --user is-active --quiet dav2d-threading-ab-benchmark-v2.service; do
    sleep 5
done
base="$task_root/.work/ab/baseline-build/tools/dav2d"
variant="$task_root/.work/ab/three-pass-build/tools/dav2d"
public=/srv/compression/cache/av2bench/streams
check="$task_root/scripts/check-ab.py"
python "$check" --baseline "$base" --variant "$variant" \
    --streams perf/2026-11-14-av2-decode-speed/data/streams_all.tsv \
    --stream-dir "$public" --out "$task_root/data/ab-correctness.jsonl"
python - "$task_root/data/ab-correctness.jsonl" <<'PY'
import json,sys
rows=[json.loads(l) for l in open(sys.argv[1])]
assert len(rows)==88 and all(r['matches_reference'] or r.get('matches_baseline') for r in rows), rows
PY
for nt in 2 3; do
    python "$check" --baseline "$base" --variant "$variant" \
        --streams "$task_root/data/testdata.tsv" \
        --stream-dir "$task_root/.work/ab/testdata" --threads "$nt" \
        --out "$task_root/data/ab-testdata-t$nt.jsonl"
done
python "$check" --baseline "$base" --variant "$variant" \
    --streams "$task_root/data/streams.tsv" --stream-dir "$public" \
    --threads 3 --out "$task_root/data/ab-core-t3.jsonl"

san="$task_root/.work/ab/asan-build"
if [ ! -f "$san/build.ninja" ]; then
    CC=clang meson setup "$san" "$task_root/.work/src" \
        --buildtype=debugoptimized --default-library=static \
        -Denable_asm=false -Dtrim_dsp=false -Db_sanitize=address,undefined \
        -Db_lundef=false -Denable_tests=true -Denable_examples=false
fi
ninja -j1 -C "$san" tools/dav2d tests/seek_stress
python "$check" \
    --baseline /srv/compression/cache/av2conf/round5/build/main-asan/tools/dav2d \
    --variant "$san/tools/dav2d" --streams "$task_root/data/testdata.tsv" \
    --stream-dir "$task_root/.work/ab/testdata" --threads 2 \
    --out "$task_root/data/ab-asan-testdata.jsonl"
python "$check" \
    --baseline /srv/compression/cache/av2conf/round5/build/main-asan/tools/dav2d \
    --variant "$san/tools/dav2d" --streams "$task_root/data/streams.tsv" \
    --stream-dir "$public" --threads 2 --limit 16 \
    --out "$task_root/data/ab-asan-core.jsonl"
python "$task_root/scripts/seek-ab.py" --binary "$san/tests/seek_stress" \
    --stream "$public/samples/FourPeople_480x270_60_qp210_130f.ivf" \
    --out "$task_root/data/ab-asan-seek.jsonl"
printf 'VALIDATION-DONE\n'
