#!/usr/bin/env bash
# Decode benchmark on the pc (i5-4590, 4 cores), 14 Nov 2026. Phases go from most
# to least important, so a partial run still gives a usable dataset.
# Timed runs use null output; a quick untimed output check (verify_raw.py
# hashes raw output and compares it with the avmdec pixel MD5) covers the core set.
# Resumable: rerunning skips rows already in the output files.
set -uo pipefail
D=$(cd "$(dirname "$0")/.." && pwd)
S=/srv/compression/cache/av2bench/streams   # the 88 sample streams (unchanged since 2 Nov)
X=/srv/compression/cache/av2bench-1114/build/x86_64
B="python3 $D/scripts/bench.py --host pc --decoders $D/scripts/decoders_x86_64.json --stream-dir $S"
OUT=$D/data/pc.jsonl
CORE=$D/data/streams_core_rep.tsv ALL=$D/data/streams_all_rep.tsv SMALL=$D/data/streams_small_rep.tsv
V() {  # list, decoder name, command...
  local l=$1 n=$2; shift 2
  python3 $D/scripts/verify_raw.py --host pc --decoder "$n" --stream-dir $S --streams "$l" \
    --out $D/data/verify_pc.jsonl -- "$@" > /dev/null
}

# 0. Sanity check of the output on the core set (untimed), 4 threads; rusty_av2d on
#    the small streams. Conformance is not the point of this run.
V $CORE dav2d_t4 $X/dav2d/tools/dav2d -q -i {ivf} --muxer yuv -o - --threads 4 --filmgrain 1
V $CORE splot_t4 $X/splot/release/splot decode {ivf} --output-format raw -o - --threads 4
V $SMALL rusty_av2d_t1 $X/rusty_av2d/release/dav1d -q -i {ivf} --muxer yuv -o - --threads 1 --filmgrain 1
# 1. Core set, thread scaling.
$B --streams $CORE --only avmdec --threads 1,4 --reps 3 --out $OUT
$B --streams $CORE --only dav2d,splot --threads 1,2,3,4 --reps 3 --out $OUT
$B --streams $CORE --only dav2d_noasm --threads 1 --reps 2 --out $OUT
# 2. Cost of the output sink: raw output to /dev/null vs the null modes.
$B --streams $CORE --only dav2d_yuvnull,splot_null,avmdec_rawnull --threads 1 --reps 1 --out $OUT
# 3. rusty_av2d on the small streams.
$B --streams $SMALL --only rusty_av2d --threads 1 --reps 1 --out $OUT
# 4. Whole corpus at 1 and 4 threads.
$B --streams $ALL --only dav2d,splot --threads 1,4 --reps 1 --out $OUT
$B --streams $ALL --only avmdec --threads 1 --reps 1 --out $OUT
echo "pc run finished $(date -Is)"
