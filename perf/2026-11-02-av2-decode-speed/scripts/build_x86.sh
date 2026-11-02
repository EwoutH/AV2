#!/usr/bin/env bash
# Native x86-64 builds on the pc: avmdec, dav2d (asm; C-only via --cpumask 0), rav2d.
# Run inside: nix shell nixpkgs#{gcc,cmake,ninja,meson,nasm,perl,python3,pkg-config,cargo,rustc}
set -euo pipefail
W=${W:-/srv/compression/cache/av2bench}
S=$W/src; B=$W/build/x86_64; mkdir -p "$B"
cmake -S "$S/avm" -B "$B/avm" -G Ninja -DCMAKE_BUILD_TYPE=Release \
  -DCONFIG_AV2_ENCODER=0 -DENABLE_TESTS=0 -DENABLE_DOCS=0
ninja -C "$B/avm" avmdec
[ -d "$B/dav2d" ] || meson setup "$B/dav2d" "$S/dav2d" --buildtype release \
  -Ddefault_library=static -Denable_tests=false -Denable_docs=false
meson compile -C "$B/dav2d"
CARGO_TARGET_DIR="$B/rav2d" cargo build --manifest-path "$S/rav2d/Cargo.toml" \
  --release --locked -p rav2d-cli --bin rav2d
ls -l "$B/avm/avmdec" "$B/dav2d/tools/dav2d" "$B/rav2d/release/rav2d"
