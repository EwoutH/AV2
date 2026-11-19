# Instrument-free A/B follow-up

Status: in progress. The matched pair is built, with instrumentation removed. All six benchmark streams match their full reference hashes at two workers, frame delay one. The broader 88-stream check is resumable and checkpointed. Timing runs admit quiet intervals between other codec jobs; sanitizer and broader validation follow timing. No aggregate performance conclusion yet.

## Builds and validation

Both binaries use GCC 16.2.0, release, static linking, assembly enabled, no LTO, and identical Meson options. The baseline's `lib.c`, `decode.c` and `thread_task.c` were restored from `b130414d`, removing instrumentation, then rebuilt. The three-pass variant was rebuilt with only the previously recorded patch. Unchanged objects were reused from the same original source revision and toolchain. The earlier duplicate fresh build was stopped to avoid recompiling unchanged assembly while the server was shared.

[ab-provenance.json](data/ab-provenance.json) records binary and patch hashes, build options, and the upstream test-data revision. The full-stream reference hashes come from the previous public AVM benchmark manifest. Failures are rechecked against the unmodified two-worker, one-frame decoder to distinguish regressions from existing differences. Correctness runs began with one CPU's worth of time; their budget was raised to two while other codec jobs were idle, with low scheduling weight. These are not timed benchmarks.

## Timing protocol

[bench-ab.py](scripts/bench-ab.py) uses randomized, adjacent baseline/variant pairs, three repetitions, null output, film grain enabled, and a 130-frame limit on the existing six-stream selection. Small streams are repeated in separate processes for at least approximately 1.2 seconds at ideal three-core scaling, based on a one-thread calibration. Process startup remains included equally on both sides. Two- and three-worker, one-frame configurations are the primary comparisons; the unchanged two-frame mode can serve as a noise control.

The runner requires initial load below one. It checks CPU activity in an idle window before each subsequent pair, records competing CPU use during each decode, and accepts a pair only if both sides have ≤0.20 foreign cores, no errors and no diagnostics. The later admission check allows up to 0.50 busy cores in its short idle sample; the actual timed-pair ceiling remains 0.20. This avoids blocking on brief background bursts while still rejecting disturbed measurements. It retains rejected pairs, retries a bounded number of times and supports resuming. It also records per-process peak RSS, requested CPU frequency and CPU affinity. A finite waiting deadline prevents it from waiting indefinitely on a busy machine.

The initial admission ceiling was 0.10 cores. After the codec jobs finished, ordinary server background activity remained around 0.17–0.27 cores in short idle samples despite load below one. No timing pairs had run. The follow-up therefore explicitly allows up to 0.20 foreign cores, while reserving a core through affinity. This is a looser ceiling than the 14 November benchmark. Pair ranges and the unchanged-mode control must be considered before attributing small differences to the patch.

## Frequency control

The machine uses `schedutil` with `intel_cpufreq` (`intel_pstate` in passive mode). In one accepted ordinary-governor FourPeople pair, the average of the sampled maximum requested frequency was about 1.39 GHz for baseline versus 1.96 GHz for the variant. Its 1.86× speed ratio cannot be interpreted as a pure parallelism gain. These ordinary-governor measurements remain in `ab-benchmark.jsonl` as an incomplete exploratory series.

The primary follow-up uses `uclampset -m 1024 -M 1024` on the benchmark process, inherited by its children and workers. This is a per-task performance hint that reduces schedutil ramp-up effects, not a guarantee of fixed hardware clock frequency. Each pair records the requested and effective clamp values; separate files are named `ab-clamped-benchmark.jsonl` and `ab-clamped-control.jsonl`. In the first corresponding FourPeople pair the speed ratio fell to 1.28× and CPU time rose about 2%, consistent with better overlap rather than a large reduction in work. Full repetition and control results are still pending.

The Linux documentation describes [schedutil's utilization-based frequency selection](https://docs.kernel.org/admin-guide/pm/cpufreq.html#schedutil), [per-task utilization hints](https://docs.kernel.org/scheduler/sched-util-clamp.html), and the [passive intel_pstate interface](https://docs.kernel.org/admin-guide/pm/intel_pstate.html#passive-mode). With the passive driver, `scaling_cur_freq` reports the governor's last frequency selection; it is not a hardware-cycle counter. The frequency samples therefore support identifying a scaling-policy difference, not exact cycle normalization or energy claims.

## Hardware-counter series

The primary series adds user-space cycle and retired-instruction counters using [perf_event_open](https://man7.org/linux/man-pages/man2/perf_event_open.2.html), with the same utilization hint and timing acceptance rules. Its files are `ab-perf-benchmark.jsonl` and `ab-perf-control.jsonl`; the earlier series remain exploratory. The decoder binaries still contain no instrumentation.

[perf_counts.py](scripts/perf_counts.py) opens disabled parent events with `inherit` and `enable_on_exec`. They start in each decoder exec, include subsequently created workers, and accumulate into the parent when children exit. The main Python runner and its already-created sampling thread are not counted. Kernel/hypervisor cycles and instructions are excluded. A software task-clock event checks accounting; a two-worker smoke decode gave about 0.2117 seconds against 0.2108 seconds from `wait4`, with no event multiplexing. Each measurement retains enabled/running times and raw/scaled counts. Counts include user-space loader/startup work, just as wall time includes process startup.

Instruction and cycle ratios help test whether the extra pass increases work while improving overlap. They are not a claim about energy use. Three accepted pairs per stream/configuration and the unchanged two-frame control remain necessary before a final throughput conclusion.

The low-latency patch changes projected-MV buffer lifetimes as well as the pass split. A gain would motivate a further ablation rather than establish that pass count alone caused it. A loss would be a reason to drop or narrow the idea.
