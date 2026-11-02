#!/usr/bin/env bash
# Cross-build static aarch64 binaries on the pc for the pi (GCC, NEON on).
# Static linking: the pi has its own Nix store, so no store paths may leak in.
# Run inside: nix shell nixpkgs#pkgsCross.aarch64-multiplatform.buildPackages.gcc
#   nixpkgs#pkgsCross.aarch64-multiplatform.glibc.static nixpkgs#{cmake,ninja,meson,perl,python3,pkg-config}
# rav2d is built separately (Rust target std needed), see build_rav2d_aarch64.sh.
set -euo pipefail
W=${W:-/srv/compression/cache/av2bench}
S=$W/src; B=$W/build/aarch64; OUT=$W/pi/bin; mkdir -p "$B" "$OUT"
X=aarch64-unknown-linux-gnu-

cmake -S "$S/avm" -B "$B/avm" -G Ninja -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_TOOLCHAIN_FILE="$S/avm/cmake/toolchains/arm64-linux-gcc.cmake" \
  -DCROSS=$X -DCMAKE_EXE_LINKER_FLAGS=-static \
  -DCONFIG_AV2_ENCODER=0 -DENABLE_TESTS=0 -DENABLE_DOCS=0
ninja -C "$B/avm" avmdec

cat > "$B/cross.meson" <<EOF
[binaries]
c = '${X}gcc'
cpp = '${X}g++'
ar = '${X}ar'
strip = '${X}strip'
[built-in options]
c_link_args = ['-static']
[host_machine]
system = 'linux'
cpu_family = 'aarch64'
cpu = 'cortex-a72'
endian = 'little'
EOF
meson setup --wipe "$B/dav2d" "$S/dav2d" --cross-file "$B/cross.meson" \
  --buildtype release -Ddefault_library=static -Denable_tests=false -Denable_docs=false
meson compile -C "$B/dav2d"

cp "$B/avm/avmdec" "$B/dav2d/tools/dav2d" "$OUT/"
${X}strip "$OUT"/*
file "$OUT"/*
