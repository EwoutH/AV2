#!/usr/bin/env bash
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
cmake -S "$root/scratch/avm" -B "$root/scratch/avm-build" -G Ninja -DAVM_TARGET_CPU=x86_64 -DENABLE_TESTS=0 -DCONFIG_AV2_ENCODER=0 -DCONFIG_TESTONLY_12BIT_SUPPORT=1
ninja -j3 -C "$root/scratch/avm-build" avmdec
meson setup "$root/scratch/dav2d-build" "$root/scratch/dav2d" --buildtype debugoptimized -Dtrim_dsp=false -Denable_tests=false
ninja -j3 -C "$root/scratch/dav2d-build" tools/dav2d
