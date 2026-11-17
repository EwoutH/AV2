#!/usr/bin/env bash
# Round-4 overnight driver: baseline on fresh main, then stress, then triage.
set -uo pipefail
W=/srv/compression/cache/av2conf; R=$W/round4; cd $W
log(){ echo "$(date +%H:%M:%S) $*" >> $R/run.log; }
D=$R/build/main/tools/dav2d; DA=$R/build/main-asan/tools/dav2d
EX=("fail/*/stream.ivf" "fail_main/*/stream.ivf" "tri/*.ivf" "rr/w/*.ivf" "triage/r/*.ivf" "mr/*.ivf" "clk-poc/*.ivf")
log "phase 1: baseline on main $(git -C $W/src/wt-r4main rev-parse --short HEAD)"
python -I regress.py $D --modes 1t,mt4,c --small --jobs 3 --extra "${EX[@]}" --out $R/base_main.jsonl > $R/base_main.log 2>&1
log "baseline main done: $(tail -1 $R/base_main.log)"
python -I review-2026-11-14/svt/run.py $R/base_svt.jsonl $W/build/r-main/tools/dav2d $D > $R/base_svt.log 2>&1
log "svt done"
ASAN_OPTIONS=detect_leaks=1 UBSAN_OPTIONS=halt_on_error=1:print_stacktrace=1 python -I regress.py $DA --modes 1t --small --jobs 3 --extra "${EX[@]}" --out $R/base_asan.jsonl > $R/base_asan.log 2>&1
log "baseline asan done: $(tail -1 $R/base_asan.log)"
log "phase 2: stress4"
cd $R && python -I stress4.py --workers 3 --stop-at 06:45 > $R/stress4.log 2>&1
log "stress done: $(wc -l < $R/results.jsonl) configs"
python -I triage4.py --stop-at 09:30 > $R/triage4.log 2>&1
log "triage done"
touch $R/run.done
