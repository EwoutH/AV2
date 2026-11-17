#!/usr/bin/env bash
set -euo pipefail
W=/srv/compression/cache/av2conf; R=$W/round4; S=$W/src/wt-r4main; B=$R/build
git -C $W/src/avm worktree add -f --detach $W/src/wt-avm4 487d0761b 2>/dev/null || true
cmake -S $W/src/wt-avm4 -B $B/avm4 -G Ninja -DCMAKE_BUILD_TYPE=Release -DENABLE_TESTS=0 -DENABLE_DOCS=0 >/dev/null
ninja -C $B/avm4 avmenc avmdec >/dev/null
O="-Ddefault_library=static -Denable_tests=false"
[ -d $B/main ] || meson setup $B/main $S --buildtype release $O >/dev/null
[ -d $B/main-c ] || meson setup $B/main-c $S --buildtype debugoptimized -Denable_asm=false -Dtrim_dsp=false $O >/dev/null
[ -d $B/main-asan ] || CC=clang meson setup $B/main-asan $S --buildtype debugoptimized -Denable_asm=false -Dtrim_dsp=false -Db_sanitize=address,undefined -Db_lundef=false $O >/dev/null
[ -d $B/main-asan-asm ] || CC=clang meson setup $B/main-asan-asm $S --buildtype debugoptimized -Db_sanitize=address,undefined -Db_lundef=false $O >/dev/null
for b in main main-c main-asan main-asan-asm; do meson compile -C $B/$b >/dev/null; done
ls -l $B/avm4/avmenc $B/avm4/avmdec $B/*/tools/dav2d
echo BUILD-DONE
