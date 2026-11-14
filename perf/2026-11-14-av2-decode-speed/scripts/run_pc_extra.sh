#!/usr/bin/env bash
# Follow-up on the pc after run_pc.sh: the 2 Nov binaries (cache/av2bench/build/x86_64:
# avmdec d953d2e, dav2d 9b5d2f6e, splot b682f58; generic x86-64 C flags) with today's
# null sinks, so that code changes since 2 Nov can be told apart from the change of
# method (null output instead of MD5, x86-64-v3 builds).
set -uo pipefail
D=$(cd "$(dirname "$0")/.." && pwd)
B="python3 $D/scripts/bench.py --host pc --decoders $D/scripts/decoders_x86_64.json --stream-dir /srv/compression/cache/av2bench/streams"
$B --streams $D/data/streams_core_rep.tsv --only avmdec_nov2 --threads 1 --reps 1 --out $D/data/pc.jsonl
$B --streams $D/data/streams_core_rep.tsv --only dav2d_nov2,splot_nov2 --threads 1,4 --reps 1 --out $D/data/pc.jsonl
echo "pc extra run finished $(date -Is)"
