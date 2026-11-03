#!/usr/bin/env bash
# usage: prof.sh <build> <stream> <limit>   (run inside: nix shell nixpkgs#perf)
# Writes perf sample counts per symbol, 1 thread, to $OUT/<build>.<stream>.tsv
set -e
W=/srv/compression/cache/av2bench; T=${OUT:-$PWD/prof}; mkdir -p $T
b=$1; s=$2; n=$(basename $s .ivf)
perf record -q -F 1000 -o $T/$b.$n.data -- $W/build/x86_64/$b/tools/dav2d -q -i $W/streams/$s --muxer null -o - --threads 1 --limit $3 >/dev/null 2>&1
perf report -i $T/$b.$n.data --no-children --sort sym -F sample,sym --stdio -t $'\t' 2>/dev/null | grep -v '^#' | grep -v '^$' > $T/$b.$n.tsv
rm $T/$b.$n.data
