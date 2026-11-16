#!/usr/bin/env bash
# Round-4 restart (16 Nov evening): the first stress run died after 18 configs
# (dev-shell python without numpy). Baseline is done; stress + triage only,
# decoding with main 28e39df9 + !1018 (CfL padding fix, as BBB suggested).
set -uo pipefail
export PATH=/run/current-system/sw/bin:$PATH R4_DAV=main-1018
W=/srv/compression/cache/av2conf; R=$W/round4; cd $R
log(){ echo "$(date +%H:%M:%S) $*" >> $R/run.log; }
rm -f $R/run.done $R/run.FAILED
log "restart: stress4 on $R4_DAV (attempt 1 saved in attempt1/)"
python -I stress4.py --workers 3 --stop-at 06:45 > $R/stress4.log 2>&1
n=$(wc -l < $R/results.jsonl)
log "stress done: $n configs"
if [ "$n" -lt 500 ]; then log "too few configs, see stress4.log"; touch $R/run.FAILED; fi
python -I triage4.py --stop-at 09:30 > $R/triage4.log 2>&1
log "triage done"
touch $R/run.done
