set -e
T=/srv/compression/cache/av2conf/testreview
ln -sfn $T/td-rebase $T/wt-mr1136/tests/dav2d-test-data
B=$T/b-mr-asan-td
[ -d $B ] || meson setup $B $T/wt-mr1136 --buildtype debugoptimized -Dlogging=false -Db_sanitize=address -Dtestdata_tests=true -Denable_seek_stress=true >/dev/null
ninja -j2 -C $B >/dev/null
cd $B
export ASAN_OPTIONS=detect_leaks=1:quarantine_size_mb=64
s() { meson test -q --setup=sanitizer "$@" 2>&1 | grep -E "^(Ok|Fail|Timeout):" | tr -s ' \n' ' '; echo " <- $*"; }
s --suite testdata
s --suite testdata_seek-stress
s --suite testdata_seek-stress --test-args "--threads 2 --framedelay 1"
s --suite testdata_seek-stress --test-args "--threads 2 --framedelay 2"
s --suite testdata_seek-stress --test-args "--threads 4 --framedelay 4"
meson test --list 2>/dev/null | grep -c seek
