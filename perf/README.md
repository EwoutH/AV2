# Performance and benchmark results

Speed and compression measurements of AV2 encoders and decoders.

| Date | Test | Encoder | Summary |
|---|---|---|---|
| 2026-10-14 | [AVM encoder presets: speed vs compression](2026-10-14-avm-preset-sweep/) | AVM `av2-enc` 89eae123d | `--cpu-used` 0-9 on 4 clips. s6 is the fastest preset; s1 to s6 is ~10x faster for 10-14% more bits; the default s0 is 6-11x slower than s1 for ~2% fewer bits. |

## Layout

Each test has its own folder, `YYYY-MM-DD-<topic>/`, with:

- `README.md`: the write-up: question, setup, findings, limits.
- Raw results (for example `.jsonl` or `.csv`), so the numbers can be
  reanalysed.
- `figures/`: PNG charts used in the write-up.
- `scripts/`: the scripts that ran the test and made the figures.
