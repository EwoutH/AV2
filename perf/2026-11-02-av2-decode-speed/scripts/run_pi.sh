#!/usr/bin/env bash
# Decode benchmark on the pi 4B (4x Cortex-A72 @ 1.5 GHz, 2 GB, 1 GB cap for agent).
# Runs on the pi from ~/av2bench, which holds bin/, streams/, scripts/ and data/.
# Streams are copied to /dev/shm first so SD card reads never get timed.
# Launch from the pc:
#   ssh agent@pi.home 'cd ~/av2bench && nohup setsid scripts/run_pi.sh > run_pi.log 2>&1 < /dev/null &'
set -uo pipefail
cd "$(dirname "$0")/.."
SHM=/dev/shm/av2bench-streams
mkdir -p $SHM && cp -rn streams/. $SHM/
PY=$(nix shell nixpkgs#python3 -c sh -c 'command -v python3')
B="$PY scripts/bench.py --host pi --decoders scripts/decoders_aarch64.json --stream-dir $SHM"
OUT=data/pi.jsonl

# 1. Headline: every fast decoder at 1 thread.
$B --streams data/streams_core.tsv --only avmdec,dav2d,dav2d_c,splot --threads 1 --reps 2 --out $OUT
# 2. Thread scaling (avmdec only 4: little multithreading on single-tile streams).
$B --streams data/streams_core.tsv --only dav2d,dav2d_c,splot --threads 2,3,4 --reps 2 --out $OUT
$B --streams data/streams_core.tsv --only avmdec --threads 4 --reps 2 --out $OUT
# 3. Slow decoders.
$B --streams data/streams_core.tsv --only rav2d --threads 1 --reps 1 --out $OUT
$B --streams data/streams_small.tsv --only rusty_av2d --threads 1 --reps 1 --out $OUT
# 4. A third rep for the fast decoders.
$B --streams data/streams_core.tsv --only avmdec,dav2d,dav2d_c,splot --threads 1 --reps 3 --out $OUT
$B --streams data/streams_core.tsv --only dav2d,dav2d_c,splot --threads 2,3,4 --reps 3 --out $OUT
# 5. splot correctness, untimed.
$PY scripts/verify_raw.py --host pi --stream-dir $SHM --streams data/streams_core.tsv \
  --out data/verify_pi.jsonl -- ./bin/splot decode {ivf} --output-format raw -o - > /dev/null
rm -rf $SHM
echo "pi run finished $(date -Is)"
