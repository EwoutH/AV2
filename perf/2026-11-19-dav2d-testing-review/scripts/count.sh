# Count decoder API calls made by seek_stress (release build of !1136+!1137). Run under systemd-run with a memory cap.
F=${1:-/srv/compression/cache/av2bench/streams/samples/FourPeople_480x270_60_qp210_130f.ivf}
B=/srv/compression/cache/av2conf/testreview/b-mr-rel
for t in "--threads 1" "--threads 2 --framedelay 2"; do
  printf '%s: ' "$t"
  timeout 120 gdb -batch -ex 'set breakpoint pending on' -ex 'break dav2d_send_data' -ex 'break dav2d_flush' -ex 'break input_seek' \
    -ex 'ignore 1 1000000' -ex 'ignore 2 1000000' -ex 'ignore 3 1000000' -ex run -ex 'info breakpoints' \
    --args $B/tests/seek_stress -i $F -o /dev/null --muxer null $t 2>&1 | grep -E 'already hit|Error|Failed' | tr '\n' ' '
  echo
done
timeout 120 $B/tools/dav2d -q -i $F --muxer null -o /dev/null --threads 1; echo "dav2d full decode rc=$?"
