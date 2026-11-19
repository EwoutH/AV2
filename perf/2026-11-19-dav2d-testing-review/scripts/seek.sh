# $1 = build dir. seek_stress on the IVF samples in 3 thread modes. Run under a memory cap.
cd /srv/compression/cache/av2conf/testreview/ivf
for f in *.ivf; do
  for m in "--threads 1" "--threads 2 --framedelay 1" "--threads 2 --framedelay 2" "--threads 4 --framedelay 4"; do
    s=$(date +%s.%N)
    ASAN_OPTIONS=detect_leaks=1:quarantine_size_mb=64 timeout 120 $1/tests/seek_stress -q --filmgrain=1 $m -i $f --muxer null > seek.out 2>&1
    rc=$?
    echo "$rc $(printf %.2f $(echo "$(date +%s.%N) - $s" | bc)) s  $f [$m] $(grep -m1 -E 'ERROR|Error|Failed' seek.out | cut -c1-80)"
  done
done
