#!/usr/bin/env bash
# Decode benchmark on the pi 4B (4x Cortex-A72 @ 1.5 GHz, 2 GB, 1 GB cap for agent),
# 14 Nov 2026. Runs on the pi from ~/av2bench-1114 (bin/, streams/, scripts/, data/).
# Streams are copied to /dev/shm first so SD card reads are never timed.
# Timed runs use null output.
# Launch from the pc:
#   ssh agent@pi.home 'cd ~/av2bench-1114 && nohup setsid scripts/run_pi.sh > run_pi.log 2>&1 < /dev/null &'
# Stopped at 17:45 during phase 3 (the dav2d_noasm phase finished); run_pi_rest.sh ran
# phase 4 with avmdec at 4 threads on the tiled stream only, then the 2 Nov binaries.
set -uo pipefail
cd "$(dirname "$0")/.."
SHM=/dev/shm/av2bench-1114-streams
mkdir -p $SHM && cp -rn streams/. $SHM/
PY=$(nix shell nixpkgs#python3 -c sh -c 'command -v python3')
B="$PY scripts/bench.py --host pi --decoders scripts/decoders_aarch64.json --stream-dir $SHM"
OUT=data/pi.jsonl CORE=data/streams_core_rep.tsv SMALL=data/streams_small_rep.tsv
# No output check on the pi: the pc checks the same source code (conformance is not
# the point of this run).
# 1. Every decoder at 1 thread.
$B --streams $CORE --only avmdec,dav2d,splot --threads 1 --reps 1 --out $OUT
# 2. Thread scaling (avmdec: little multithreading on single-tile streams).
$B --streams $CORE --only dav2d,splot --threads 4 --reps 1 --out $OUT
$B --streams $CORE --only dav2d,splot --threads 2 --reps 1 --out $OUT
# 3. dav2d without asm, 1 thread.
$B --streams $CORE --only dav2d_noasm --threads 1 --reps 1 --out $OUT
# 4. Second repeat at 1 and 4 threads.
$B --streams $CORE --only dav2d,splot --threads 1,4 --reps 2 --out $OUT
$B --streams $CORE --only avmdec --threads 4 --reps 1 --out $OUT
rm -rf $SHM
echo "pi run finished $(date -Is)"
