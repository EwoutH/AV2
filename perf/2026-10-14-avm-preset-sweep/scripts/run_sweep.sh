#!/bin/sh
# Overnight preset sweep of the av2-enc avmenc build (Release/).
# Plan (sweep.py PLAN, in priority order; x QP 110/145/180/210):
#   1. FourPeople, BlueSky, Vertical_Bayshore (270p/360p), 33 frames,
#      presets 0-9, + 3 repeated encodes (timing drift check)
#   2. KristenAndSara 720p, 65 frames, presets 1-9
#   3. crowd_run 1080p, 33 frames, presets 1-9
#   4. old_town_cross 1080p, 33 frames, presets 1-9 (filler)
# One queue, slowest jobs first within each step; six encodes at once, one
# per P-core, --threads=1. Jobs that would not finish by 07:00 are skipped.
# Resumable: rerun and finished encodes are skipped.
#
# Start it in its own Git Bash window (not the VS Code terminal):
#   sh run_sweep.sh
# Progress: night.log. Report: sweep_report/ (summary.txt and PNGs).
cd "$(dirname "$0")" || exit 1
{
    echo "start $(date)"
    python -I sweep.py --plan night --stop-at 07:00 --results sweep.jsonl
    python -I analyze_sweep.py --results sweep.jsonl --ref 1
    echo "ALL DONE $(date)"
} 2>&1 | tee -a night.log
