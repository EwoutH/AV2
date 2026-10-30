#!/bin/sh
# second stress instance on the P-cores after the sweep finished (30 Oct)
cd "$(dirname "$0")" || exit 1
{
    echo "start $(date)"
    python -I stress.py --workers 10 --cores 0-11 --prefix p --seed 20261031 --stop-at 07:15 --results results_p.jsonl
    echo "ALL DONE $(date)"
} >> stress_p.log 2>&1
