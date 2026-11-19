#!/usr/bin/env bash
# Run inside the AV2 Nix dev shell. Keep experiment sources separate from dav2d.
set -euo pipefail
task_root=$(cd "$(dirname "$0")/.." && pwd)
ab_root="$task_root/.work/ab"
source_repo=/srv/compression/cache/av2conf/src/wt-rd5main
revision=b130414d978a613671b6a14bf95040e2cba8d726
mkdir -p "$ab_root"
if [ -n "${REUSE_BUILD:-}" ]; then
    src="$task_root/.work/src"
    build="$REUSE_BUILD"
    cp "$build/tools/dav2d" "$ab_root/dav2d-instrumented-three-pass"
    for file in lib.c decode.c thread_task.c; do
        git -C "$source_repo" show "$revision:src/$file" > "$src/src/$file"
    done
    ninja -j"${BUILD_JOBS:-1}" -C "$build" tools/dav2d
    mkdir -p "$ab_root/baseline-build/tools" "$ab_root/three-pass-build/tools"
    cp "$build/tools/dav2d" "$ab_root/baseline-build/tools/dav2d"
    cp "$build/meson-info/intro-buildoptions.json" "$ab_root/baseline-options.json"
    patch -p1 -d "$src" < "$task_root/patches/three-pass-low-latency.patch"
    ninja -j"${BUILD_JOBS:-1}" -C "$build" tools/dav2d
    cp "$build/tools/dav2d" "$ab_root/three-pass-build/tools/dav2d"
    cp "$build/meson-info/intro-buildoptions.json" "$ab_root/three-pass-options.json"
    sha256sum "$ab_root"/*-build/tools/dav2d
    exit
fi
for variant in baseline three-pass; do
    src="$ab_root/$variant-src"
    build="$ab_root/$variant-build"
    if [ ! -d "$src" ]; then
        mkdir -p "$src"
        git -C "$source_repo" archive "$revision" | tar -x -C "$src"
        if [ "$variant" = three-pass ]; then
            patch -p1 -d "$src" < "$task_root/patches/three-pass-low-latency.patch"
        fi
    fi
    if [ ! -f "$build/build.ninja" ]; then
        CC=gcc meson setup "$build" "$src" --buildtype=release \
            --default-library=static -Denable_tests=false \
            -Denable_examples=false -Db_lto=false
    fi
    ninja -j"${BUILD_JOBS:-1}" -C "$build" tools/dav2d
done
sha256sum "$ab_root"/*-build/tools/dav2d
