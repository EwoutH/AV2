#!/usr/bin/env bash
# Cross-build static aarch64 binaries on the pc for the pi (GCC, NEON on, -mcpu=cortex-a72
# like the Rust builds). dav2d is built twice: with asm and with -Denable_asm=false.
# Static linking: the pi has its own Nix store, so no store paths may leak in.
# Run inside: nix shell nixpkgs#pkgsCross.aarch64-multiplatform.buildPackages.gcc
#   nixpkgs#pkgsCross.aarch64-multiplatform.glibc.static nixpkgs#{cmake,ninja,meson,perl,python3,pkg-config}
# rusty_av2d and splot (Rust) are cross-built by build_rust_aarch64.sh.
set -euo pipefail
W=${W:-/srv/compression/cache/av2bench-1114}
S=$W/src; B=$W/build/aarch64; OUT=$W/pi/bin; mkdir -p "$B" "$OUT"
X=aarch64-unknown-linux-gnu-
# The nix gcc wrapper does not put the static glibc on the link path; add it.
GS=$(nix build --no-link --print-out-paths nixpkgs#pkgsCross.aarch64-multiplatform.glibc.static)
LDF="-static -L$GS/lib"
CF="-mcpu=cortex-a72"
rm -rf "$B/avm"

cmake -S "$S/avm" -B "$B/avm" -G Ninja -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_TOOLCHAIN_FILE="$S/avm/cmake/toolchains/arm64-linux-gcc.cmake" \
  -DCROSS=$X -DCMAKE_EXE_LINKER_FLAGS="$LDF" \
  -DCMAKE_C_FLAGS="$CF" -DCMAKE_CXX_FLAGS="$CF" \
  -DCONFIG_AV2_ENCODER=0 -DENABLE_TESTS=0 -DENABLE_DOCS=0
ninja -C "$B/avm" avmdec

cat > "$B/cross.meson" <<EOF
[binaries]
c = '${X}gcc'
cpp = '${X}g++'
ar = '${X}ar'
strip = '${X}strip'
[built-in options]
c_args = ['-mcpu=cortex-a72']
c_link_args = ['-static', '-L$GS/lib']
[host_machine]
system = 'linux'
cpu_family = 'aarch64'
cpu = 'cortex-a72'
endian = 'little'
EOF
for v in dav2d:true dav2d_noasm:false; do
  n=${v%%:*}; rm -rf "$B/$n"
  meson setup "$B/$n" "$S/dav2d" --cross-file "$B/cross.meson" --buildtype release \
    -Ddefault_library=static -Denable_tests=false -Denable_docs=false -Denable_asm=${v#*:}
  meson compile -C "$B/$n"
done

cp "$B/avm/avmdec" "$B/dav2d/tools/dav2d" "$OUT/"
cp "$B/dav2d_noasm/tools/dav2d" "$OUT/dav2d_noasm"
${X}strip "$OUT"/*
ls -l "$OUT"/
