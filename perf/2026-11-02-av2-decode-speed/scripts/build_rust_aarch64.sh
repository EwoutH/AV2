#!/usr/bin/env bash
# Cross-build the Rust decoders for the pi: static aarch64 glibc binaries.
# Rust 1.95.0 (same as the x86 build) from rustup, with the aarch64 target std:
#   nix shell nixpkgs#rustup -c rustup toolchain install 1.95.0 --profile minimal \
#     --target aarch64-unknown-linux-gnu
# Run inside: nix shell nixpkgs#rustup nixpkgs#gcc nixpkgs#pkgsCross.aarch64-multiplatform.buildPackages.gcc
# (host gcc: build scripts and proc macros run on the pc).
# rusty_av2d pins a nightly but builds on 1.95.0 with RUSTC_BOOTSTRAP=1. splot needs
# rustc >= 1.99, so it uses its own pinned nightly-2026-07-22 (install it the same way).
# rav2d's NEON MC/intra (FFI into dav2d asm) needs the dav2d submodule and its
# build/config.h; without them its build.rs falls back to pure Rust, as here.
# Usage: build_rust_aarch64.sh [rav2d] [rusty_av2d] [splot]
set -uo pipefail
W=${W:-/srv/compression/cache/av2bench}
S=$W/src; B=$W/build/aarch64; OUT=$W/pi/bin; mkdir -p "$B" "$OUT"
T=aarch64-unknown-linux-gnu
GS=$(nix build --no-link --print-out-paths nixpkgs#pkgsCross.aarch64-multiplatform.glibc.static)
export CARGO_TARGET_AARCH64_UNKNOWN_LINUX_GNU_LINKER=$T-gcc
export CC_aarch64_unknown_linux_gnu=$T-gcc AR_aarch64_unknown_linux_gnu=$T-ar
export RUSTFLAGS="-C target-feature=+crt-static -L native=$GS/lib -C target-cpu=cortex-a72"
export RUSTC_BOOTSTRAP=1

build() {  # toolchain, name, src dir, built binary name, output name, cargo args...
  local tc=$1 name=$2 dir=$3 bin=$4 out=$5; shift 5
  (cd "$S/$dir" && CARGO_TARGET_DIR="$B/$name" cargo +$tc build --release --locked \
     --target $T "$@") && cp "$B/$name/$T/release/$bin" "$OUT/$out" && $T-strip "$OUT/$out"
  echo "$name exit $?"
}
[ $# -gt 0 ] || set -- rav2d rusty_av2d splot
for x in "$@"; do
  case $x in
    rav2d)      build 1.95.0 rav2d rav2d rav2d rav2d -p rav2d-cli --bin rav2d ;;
    rusty_av2d) build 1.95.0 rusty_av2d rusty_av2d dav1d rusty_av2d -p rusty_av2d-cli --bin dav1d ;;
    splot)      build nightly-2026-07-22 splot splot splot splot -p splot-cli ;;
  esac
done
file "$OUT"/* 2>/dev/null
