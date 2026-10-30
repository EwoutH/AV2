#!/bin/sh
# 30 Oct overnight: av2-enc 89eae123d (14 Oct) vs 97e8004e4 (30 Oct), same
# conditions, low-res trio 33 f + KristenAndSara 65 f, presets 1-9 x 4 QPs.
cd "$(dirname "$0")" || exit 1
{
    echo "start $(date)"
    python -I sweep2.py --plan night --stop-at 07:30 --results sweep2.jsonl
    echo "ALL DONE $(date)"
} >> night2.log 2>&1
