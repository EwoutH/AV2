# Performance and benchmark results

Speed and compression measurements of AV2 encoders and decoders.

| Date | Test | Encoder | Summary |
|---|---|---|---|
| 2026-10-14 | [AVM encoder presets: speed vs compression](2026-10-14-avm-preset-sweep/) | AVM `av2-enc` 89eae123d | `--cpu-used` 0-9 on 4 clips. s6 is the fastest preset; s1 to s6 is ~10x faster for 10-14% more bits; the default s0 is 6-11x slower than s1 for ~2% fewer bits. |
| 2026-10-15 | [AVM on P-cores vs E-cores: parallel encoding](2026-10-15-avm-p-vs-e-cores/) | AVM `av2-enc` 89eae123d | i7-12700H: an E-core encodes at about half the speed of a P-core, but the 8 E-cores still add ~50% throughput. Run 14-20 single-thread encodes; hyperthreading adds little once the E-cores are busy. |
| 2026-10-19 | [AV2 vs AV1, VVC, HEVC and AVC encoders](2026-10-19-av2-vs-av1-vvc-hevc/) | AVM `av2-enc` 89eae123d; libaom, SVT-AV1, VVenC, x265, x264 | On small and 720p clips AVM s1 needs 15-26% fewer bits than libaom cpu-used 1 at 20-30x the time; VVenC slower gets close (-20%) at a fifth of AVM's time. At 1080p over 33 frames, AVM's large keyframe boost dominates. |
| 2026-10-20 | [AV2 decoder conformance and speed](2026-10-20-av2-decoder-conformance/) | dav2d, rav2d vs `avmdec` | dav2d matched 34 of 260 AVM streams (0 on its MSVC nightly); five fixes bring it to 258. Patched dav2d decodes 2.3-2.9x faster than `avmdec` on one thread, ~100 fps at 1080p on 20. |
| 2026-10-29 | [dav2d conformance update](2026-10-29-dav2d-conformance-update/) | dav2d `main` vs `avmdec` | All fixes from 20 Oct are now upstream. Unpatched dav2d matches all 284 AVM streams, with no errors or crashes. |

## Layout

Each test has its own folder, `YYYY-MM-DD-<topic>/`, with:

- `README.md`: the write-up: question, setup, findings, limits.
- Raw results (for example `.jsonl` or `.csv`), so the numbers can be
  reanalysed.
- `figures/`: PNG charts used in the write-up.
- `scripts/`: the scripts that ran the test and made the figures.
