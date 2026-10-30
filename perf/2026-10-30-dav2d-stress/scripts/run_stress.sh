#!/bin/sh
# 30 Oct overnight dav2d stress test (E-cores), see stress.py.
cd "$(dirname "$0")" || exit 1
{
    echo "start $(date)"
    python -I stress.py --workers 6 --stop-at 07:15 --results results.jsonl
    echo "ALL DONE $(date)"
} >> stress.log 2>&1
