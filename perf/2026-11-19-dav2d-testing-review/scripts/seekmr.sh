# seek_stress (ASan) on !1136+!1137 over small IVFs; every run capped at 1G, no swap.
cd /srv/compression/cache/av2conf/testreview
B=$PWD/b-mr-asan/tests/seek_stress
OUT=$PWD/seek/mr; mkdir -p $OUT
BASH=/run/current-system/sw/bin/bash
FILES="$(ls /srv/compression/cache/av2conf/round4/r5/repro/*.ivf /srv/compression/cache/av2conf/round5/smoke/*.ivf /srv/compression/cache/av2conf/round4/i444/r4*.ivf /srv/compression/cache/av2conf/round5/trace/kfL80.ivf)
/srv/compression/cache/av2bench/streams/samples/Vertical_Bayshore_270x480_2997_qp210_130f.ivf
/srv/compression/cache/av2bench/streams/samples/FourPeople_480x270_60_qp210_130f.ivf"
n=0
for f in $FILES; do
  for t in "--threads 1" "--threads 2 --framedelay 2" "--threads 4 --framedelay 4"; do
    n=$((n+1)); tag=$(basename $f .ivf)_$(echo $t | tr -d ' -')
    systemd-run --user --unit=tr-seekmr-$n -p MemoryMax=1G -p MemorySwapMax=0 -p Nice=19 --wait --collect --quiet \
      -E ASAN_OPTIONS=detect_leaks=1:quarantine_size_mb=64:malloc_context_size=10 \
      $BASH -c "timeout 300 $BASH $PWD/seek/seekrss.sh $B $f $t > $OUT/$tag.log 2>&1"
    rc=$?
    peak=$(awk '/rss_kb/{print $2}' $OUT/$tag.log | sort -n | tail -1)
    err=$(grep -m1 -E "ERROR: |SUMMARY|Error decoding" $OUT/$tag.log | cut -c1-120)
    echo "$rc peak_kb=$peak $(tail -1 $OUT/$tag.log) $tag $err"
  done
done
