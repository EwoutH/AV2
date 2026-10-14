#!/usr/bin/env bash
# Package a decoder build for release.
# Usage: package_decoder.sh <name> <binary> <compiler> <licence files...>
# Expects PLATFORM, SHA and test.log (from decode_test.py) in the working dir.
set -euo pipefail
name=$1 bin=$2 compiler=$3; shift 3

pkg="$name-$PLATFORM"
mkdir "$pkg"
cp "$bin" "$@" "$pkg/"
exe="$pkg/$(basename "$bin")"
if [[ "$RUNNER_OS" != Windows ]]; then strip "$exe"; fi
# Stripping breaks the ad-hoc signature that Apple Silicon requires.
if [[ "$RUNNER_OS" == macOS ]]; then codesign --force -s - "$exe"; fi
{
  echo "Unofficial nightly build of $name, an AV2 decoder"
  echo "Built by:    $GITHUB_SERVER_URL/$GITHUB_REPOSITORY (run $GITHUB_RUN_ID)"
  echo "Commit:      $SHA ($(git -C src log -1 --format=%cd --date=short))"
  echo "Platform:    $PLATFORM"
  echo "Compiler:    $compiler"
  echo "Decode test: $(grep -m 1 '^decode test:' test.log | sed 's/^decode test: *//')"
} > "$pkg/BUILD_INFO.txt"
cat "$pkg/BUILD_INFO.txt"
if [[ "$RUNNER_OS" == Windows ]]; then
  7z a -bso0 "$pkg.zip" "$pkg"
else
  tar -czf "$pkg.tar.gz" "$pkg"
fi
cp "$pkg/BUILD_INFO.txt" "BUILD_INFO-$pkg.txt"
