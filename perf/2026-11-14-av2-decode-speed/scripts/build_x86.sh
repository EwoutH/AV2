#!/usr/bin/env bash
# Native x86-64 builds on the pc (i5-4590, Haswell): avmdec, dav2d (asm and no-asm),
# splot, rusty_av2d. All compiled code targets x86-64-v3 (AVX2, the level splot's
# .cargo/config.toml sets), so C and Rust get the same CPU tuning. dav2d and AVM also
# pick their SIMD at run time.
# Run inside: nix develop /srv/compression/projects/AV2 -c nix shell nixpkgs#rustup -c bash build_x86.sh
set -euo pipefail
W=${W:-/srv/compression/cache/av2bench-1114}
S=$W/src; B=$W/build/x86_64; mkdir -p "$B"
CF="-march=x86-64-v3"

rm -rf "$B/avm"
cmake -S "$S/avm" -B "$B/avm" -G Ninja -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_C_FLAGS="$CF" -DCMAKE_CXX_FLAGS="$CF" \
  -DCONFIG_AV2_ENCODER=0 -DENABLE_TESTS=0 -DENABLE_DOCS=0
ninja -C "$B/avm" avmdec

for v in dav2d:true dav2d_noasm:false; do
  n=${v%%:*}; rm -rf "$B/$n"
  meson setup "$B/$n" "$S/dav2d" --buildtype release -Ddefault_library=static \
    -Denable_tests=false -Denable_docs=false -Denable_asm=${v#*:} -Dc_args="$CF"
  meson compile -C "$B/$n"
done

# splot: its pinned toolchain (rust-toolchain.toml) and its own release profile
# (fat LTO, target-cpu=x86-64-v3 from .cargo/config.toml).
(cd "$S/splot" && CARGO_TARGET_DIR="$B/splot" cargo build --release --locked -p splot-cli)
# rusty_av2d: its pinned nightly; same CPU level as the others.
(cd "$S/rusty_av2d" && RUSTFLAGS="-C target-cpu=x86-64-v3" CARGO_TARGET_DIR="$B/rusty_av2d" \
  cargo build --release --locked)
ls -l "$B/avm/avmdec" "$B"/dav2d*/tools/dav2d "$B/splot/release/splot" "$B/rusty_av2d/release/dav1d"
