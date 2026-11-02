#!/usr/bin/env bash
# Overnight decode benchmark on the pc (i5-4590, 4 cores). Phases go from most
# to least important, so a partial night still gives a usable dataset.
# Resumable: rerunning skips rows already in the output files.
# Launch detached:  systemd-run --user --unit av2bench-pc scripts/run_pc.sh
set -uo pipefail
D=$(cd "$(dirname "$0")/.." && pwd)
S=/srv/compression/cache/av2bench/streams
B="python3 $D/scripts/bench.py --host pc --decoders $D/scripts/decoders_x86_64.json --stream-dir $S"
OUT=$D/data/pc.jsonl

# 1. Thread scaling on the core set, every decoder (rav2d last: slowest).
$B --streams $D/data/streams_core.tsv --only avmdec,dav2d,dav2d_c --threads 1,2,3,4 --reps 3 --out $OUT
$B --streams $D/data/streams_core.tsv --only rav2d --threads 1,4 --reps 3 --out $OUT
# 2. Whole corpus, the two main decoders, 1 and 4 threads.
$B --streams $D/data/streams_all.tsv --only avmdec,dav2d --threads 1,4 --reps 3 --out $OUT
# 3. Whole corpus, C-only dav2d, 1 thread (what the x86 asm buys per stream).
$B --streams $D/data/streams_all.tsv --only dav2d_c --threads 1 --reps 2 --out $OUT
echo "pc run finished $(date -Is)"
