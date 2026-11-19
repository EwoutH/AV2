cd /srv/compression/cache/av2conf/testreview/ivf
T=/srv/compression/cache/av2conf/testreview
for f in *.ivf; do
  echo "== $f ref $($T/../build/avmn12/avmdec --rawvideo --md5 $f 2>/dev/null | cut -d' ' -f1)"
  for m in "--threads 1" "--threads 4 --framedelay 4" "--threads 1 --cpumask 0" "--threads 2 --framedelay 2 --negstride"; do
    echo "  dav2d main [$m] $($T/b-rel/tools/dav2d -q --filmgrain=1 $m -i $f --muxer md5 -o - 2>&1)"
  done
  echo "  ubsan negstride main: $(UBSAN_OPTIONS=halt_on_error=1 $T/b-ubsan/tools/dav2d -q --negstride -i $f --muxer md5 -o - 2>&1 | tail -1 | cut -c1-100)"
  python3 -I $T/seek/psh.py $T/b-mr-rel/src/libdav2d.so $f | tail -1
done
