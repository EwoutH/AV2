# Instrument-free A/B follow-up

Status: in progress. The matched pair is built, with instrumentation removed; full-output checks on the 88 public benchmark streams are running. Timing must wait for the other codec jobs to finish. No new performance conclusion yet.

## Builds and validation

Both binaries use GCC 16.2.0, release, static linking, assembly enabled, no LTO, and identical Meson options. The baseline's `lib.c`, `decode.c` and `thread_task.c` were restored from `b130414d`, removing instrumentation, then rebuilt. The three-pass variant was rebuilt with only the previously recorded patch. Unchanged objects were reused from the same original source revision and toolchain. The earlier duplicate fresh build was stopped to avoid recompiling unchanged assembly while the server was shared.

[ab-provenance.json](data/ab-provenance.json) records binary and patch hashes, build options, and the upstream test-data revision. The full-stream reference hashes come from the previous public AVM benchmark manifest. Failures are rechecked against the unmodified two-worker, one-frame decoder to distinguish regressions from existing differences. Correctness runs are capped at one CPU's worth of time and are not timed benchmarks.

## Timing protocol

[bench-ab.py](scripts/bench-ab.py) uses randomized, adjacent baseline/variant pairs, three repetitions, null output, film grain enabled, and a 130-frame limit on the existing six-stream selection. Small streams are repeated in separate processes for at least approximately 1.2 seconds at ideal three-core scaling, based on a one-thread calibration. Process startup remains included equally on both sides. Two- and three-worker, one-frame configurations are the primary comparisons; the unchanged two-frame mode can serve as a noise control.

The runner requires initial load below one and ≤0.10 busy cores before starting. It checks CPU activity in an idle window before each subsequent pair, records competing CPU use during each decode, and accepts a pair only if both sides have ≤0.10 foreign cores, no errors and no diagnostics. It retains rejected pairs, retries a bounded number of times and supports resuming. It also records per-process peak RSS, sampled CPU frequency and CPU affinity. A finite waiting deadline prevents it from waiting indefinitely on a busy machine.

The low-latency patch changes projected-MV buffer lifetimes as well as the pass split. A gain would motivate a further ablation rather than establish that pass count alone caused it. A loss would be a reason to drop or narrow the idea.
