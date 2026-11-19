# Output and sanitizer checks

| File | Completed / planned | Reference matches | Baseline-only matches | Diagnostics |
|---|---:|---:|---:|---:|
| ab-core-correctness.jsonl | 6 / 6 | 6 | 0 | 0 |
| ab-correctness.jsonl | 60 / 88 | 60 | 0 | 0 |
| ab-core-t3.jsonl | 0 / 6 | 0 | 0 | 0 |
| ab-testdata-t2.jsonl | 0 / 16 | 0 | 0 | 0 |
| ab-testdata-t3.jsonl | 0 / 16 | 0 | 0 | 0 |
| ab-asan-testdata.jsonl | 0 / 16 | 0 | 0 | 0 |
| ab-asan-core.jsonl | 0 / 6 | 0 | 0 | 0 |

ASan/UBSan checks use C code with assembly disabled. They do not establish race freedom. Prefix comparisons cover 16 output frames; the other output checks decode complete streams. Missing results are pending, not passes.
