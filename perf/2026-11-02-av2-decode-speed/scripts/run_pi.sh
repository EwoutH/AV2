#!/usr/bin/env bash
# Decode benchmark on the pi 4B (4x Cortex-A72 @ 1.5 GHz, 2 GB, 1 GB cap for agent).
# Runs on the pi from ~/av2bench, which holds bin/, streams/, scripts/ and data/.
# Streams are copied to /dev/shm first so SD card reads never get timed.
# Launch from the pc:
#   ssh pi 'cd ~/av2bench && nohup setsid scripts/run_pi.sh > run_pi.log 2>&1 &'
set -uo pipefail
cd "$(dirname "$0")/.."
SHM=/dev/shm/av2bench-streams
mkdir -p $SHM && cp -rn streams/. $SHM/
PY="nix shell nixpkgs#python3 -c python3"
B="$PY scripts/bench.py --host pi --decoders scripts/decoders_aarch64.json --stream-dir $SHM"
OUT=data/pi.jsonl

$B --streams data/streams_core.tsv --only avmdec,dav2d,dav2d_c --threads 1,2,4 --reps 3 --out $OUT
$B --streams data/streams_core.tsv --only rav2d,rav2d_noasm --threads 1 --reps 2 --out $OUT
$B --streams data/streams_core.tsv --only dav2d --threads 3 --reps 3 --out $OUT
echo "pi run finished $(date -Is)"
