#!/bin/bash
# $1 binary, $2 stream, rest: args. Samples RSS every 0.5 s.
B=$1; S=$2; shift 2
"$B" -i "$S" -o /dev/null --muxer null "$@" &
p=$!
while kill -0 $p 2>/dev/null; do echo "rss_kb $(awk '/VmRSS/{print $2}' /proc/$p/status 2>/dev/null) t=$SECONDS"; sleep 0.5; done
wait $p; echo "exit $?"
