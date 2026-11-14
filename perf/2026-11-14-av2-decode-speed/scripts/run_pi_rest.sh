#!/usr/bin/env bash
# The rest of the pi run, as executed from 17:45 on 14 Nov: run_pi.sh was stopped
# during phase 3 (dav2d_noasm) to save time; this script waits for that phase's
# bench.py (PID given as $1), then runs phase 4 with avmdec at 4 threads on the
# 4x2-tile stream only (avmdec gains nothing from threads on single-tile streams),
# then the 2 Nov binaries (run_pi_extra.sh's step).
set -uo pipefail
cd "$(dirname "$0")/.."
while kill -0 "$1" 2>/dev/null; do sleep 30; done
SHM=/dev/shm/av2bench-1114-streams
mkdir -p $SHM && cp -rn streams/. $SHM/
PY=$(nix shell nixpkgs#python3 -c sh -c 'command -v python3')
B="$PY scripts/bench.py --host pi --decoders scripts/decoders_aarch64.json --stream-dir $SHM"
OUT=data/pi.jsonl CORE=data/streams_core_rep.tsv
grep -e '^#' -e tiles4x2 $CORE > data/streams_tiles_rep.tsv
# 4. Second repeat at 1 and 4 threads; avmdec at 4 threads on the tiled stream.
$B --streams $CORE --only dav2d,splot --threads 1,4 --reps 2 --out $OUT
$B --streams data/streams_tiles_rep.tsv --only avmdec --threads 4 --reps 1 --out $OUT
# 5. The 2 Nov dav2d and splot binaries (~/av2bench/bin), 1 thread.
$B --streams $CORE --only dav2d_nov2,splot_nov2 --threads 1 --reps 1 --out $OUT
rm -rf $SHM
echo "pi run finished $(date -Is)"
