#!/usr/bin/env bash
# Follow-up (3 Nov, 05:30): dav2d built with -Denable_asm=false. In release builds
# dav2d sets TRIM_DSP_FUNCTIONS, which always enables the target's baseline SIMD
# (NEON on aarch64, SSE2 on x86-64), so `--cpumask 0` is not C-only there.
#   pc:  scripts/run_extra.sh pc        (from the perf folder)
#   pi:  scripts/run_extra.sh pi        (from ~/av2bench)
set -uo pipefail
cd "$(dirname "$0")/.."
if [ "$1" = pc ]; then
  python3 scripts/bench.py --host pc --decoders scripts/decoders_x86_64.json \
    --stream-dir /srv/compression/cache/av2bench/streams --streams data/streams_core.tsv \
    --only dav2d_noasm --threads 1 --reps 2 --out data/pc.jsonl
else
  SHM=/dev/shm/av2bench-streams; mkdir -p $SHM && cp -rn streams/. $SHM/
  PY=$(nix shell nixpkgs#python3 -c sh -c 'command -v python3')
  $PY scripts/bench.py --host pi --decoders scripts/decoders_aarch64.json --stream-dir $SHM \
    --max-foreign 0.25 --streams data/streams_core.tsv --only dav2d_noasm --threads 1 --reps 1 --out data/pi.jsonl
  rm -rf $SHM
fi
echo "extra run finished $(date -Is)"
