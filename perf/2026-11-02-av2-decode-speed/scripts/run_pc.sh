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

# 1. Core set, thread scaling 1-4.
$B --streams $D/data/streams_core.tsv --only avmdec,dav2d,dav2d_c,splot --threads 1,2,3,4 --reps 3 --out $OUT
# 2. Slow decoders: rav2d (threads only parallelize output and film grain) on the
#    core set; rusty_av2d (~3 fps at 270p) only on the four small streams.
$B --streams $D/data/streams_core.tsv --only rav2d --threads 1 --reps 2 --out $OUT
$B --streams $D/data/streams_small.tsv --only rusty_av2d --threads 1 --reps 1 --out $OUT
# 3. Whole corpus, avmdec and dav2d, 1 and 4 threads.
$B --streams $D/data/streams_all.tsv --only avmdec,dav2d --threads 1,4 --reps 3 --out $OUT
# 4. Whole corpus, C-only dav2d and splot, 1 thread.
$B --streams $D/data/streams_all.tsv --only dav2d_c,splot --threads 1 --reps 2 --out $OUT
# 5. splot correctness (no MD5 mode): raw output -> MD5, untimed.
python3 $D/scripts/verify_raw.py --host pc --stream-dir $S --streams $D/data/streams_all.tsv \
  --out $D/data/verify_pc.jsonl -- /srv/compression/cache/av2bench/build/x86_64/splot/release/splot \
  decode {ivf} --output-format raw -o - > /dev/null
echo "pc run finished $(date -Is)"
