# dav2d testing audit, 19 November 2026

**Status update, 21:17 CET:** the sample MRs and four-frame CI changes below have merged. See [the refreshed ranking](CURRENT-PRIORITIES.md) for outstanding work. This document and its CI matrix retain the original measurement baseline; the AVM tracing work is now owned by another session.

The best return is to land the pending regression/format samples and four-frame runs, then repair the empty seek suite. The architecture matrix is already broad. Adding architectures or duplicating sanitizer builds is lower value than making existing jobs exercise more decoder states.

| Rank | Concrete change | Evidence | Added CI work / readiness |
|---:|---|---|---|
| 1 | Land test-data !6, then !9, including the reviewed replacement 12-bit 4:2:2 restoration sample | 16 → 23 → 35 public samples; same C build hits 8,843 → 9,108 → 10,692 stored guards. !9 adds 1,584 over !6 (+17.4%) in 19,894 bytes | Existing jobs, no new build. A 35-sample native testdata pass takes 0.879 s in observed CI. Existing MRs, green |
| 2 | Land dav2d !1138 / test-data !12 (`--threads 4 --framedelay 4`); collect coverage afterward and preserve each JUnit run | Existing baseline has one/two-thread runs; report has 0/640 lines in thread_task.c. Added 16-stream passes cost 0.444 s release, 0.468 s ASan, 0.870 s TSan. Sanitizer jobs fail to upload JUnit under the current filename | 1.782 summed invocation seconds in dav2d's observed pipeline; no new builds. Existing MRs green; separate report-order/JUnit patches prepared |
| 3 | Register real IVF seek/flush tests and make seek_stress report input/decode failures | Two explicit CI suite invocations each print `No suitable tests defined.` No seek suite is registered. Harness returns success on open failure and decode-error exits | Reuse existing seek-enabled builds. Fixture runtime unmeasured; proposal specifies registration and failure checks |
| 4 | Run the matching sample subset in both existing `bitdepths=8` and `bitdepths=16` jobs | Both jobs compile only. Existing Meson selection can already run 14/2 samples on main, or 25/10 with !6+!9 | Two corpus checkouts plus subset decodes; no extra decoder builds. Config patch prepared; CI cost not yet measured |
| 5 | Expand the AVM trace subset from six to 14 compatible samples; agree where its list lives | Fresh comparison: 14/35 equal traces, 21 differ, including all 12 of !9. Eight compatible samples are omitted by CI | Existing AVM build can be reused. Incremental CI cost unmeasured. Existing !9 discussion awaits maintainer answer |

Links: [test-data !6](https://code.videolan.org/videolan/dav2d-test-data/-/merge_requests/6), [!9](https://code.videolan.org/videolan/dav2d-test-data/-/merge_requests/9), [dav2d !1138](https://code.videolan.org/videolan/dav2d/-/merge_requests/1138), [test-data !12](https://code.videolan.org/videolan/dav2d-test-data/-/merge_requests/12). These are existing proposals, not new submissions from this audit. Nothing was posted upstream.

## Scope and evidence

CI source: dav2d upstream `2ea62cc802e1818ead9894612e0bb4d33a61916c`; its fetched source and live API CI file agree. The main clone's working checkout is older and was not used as the CI baseline. Test-data main is `85af1c2`, confirmed in CI clone logs and fetched manifests. Local corpus measurement uses decoder `b130414d`, C-only, debugoptimized, both bitdepth implementations, one thread and film grain enabled. Local trace comparison uses the already prepared CI replica in `round5/trace/`, dav2d b130414d and AVM with dav2d's trace patches/debug defines, using the 12-bit-enabled reference build. Binary hashes and source revisions are in [local-provenance.json](data/local-provenance.json).

Read [CI-MATRIX.md](CI-MATRIX.md) for every expanded job, build options, environment, exact Meson test commands, job links and costs; [ci-matrix.tsv](data/ci-matrix.tsv) is machine-readable. Public job/API evidence and HTML coverage pages are in `data/`. Saved job logs have ANSI color, trailing whitespace and upload-token fields removed; downloaded-log hashes preserve their original identities. Scripts only read public samples from git; this audit does not copy private corpora.

## CI topology and cost

Three successful upstream main pipelines (753097, 753262, 753287; 18–19 November) each ran **49 jobs: one style, 27 build, 21 test**. Summed job durations were **1,622.7, 1,796.3 and 1,954.5 seconds** (27.0–32.6 runner minutes). GitLab pipeline `duration` was **162, 227 and 310 seconds**, respectively. These are different measures: summing parallel jobs does not give pipeline latency or CPU time. Queue times are recorded separately per job. Three runs are a snapshot, not a stable cost model or trend.

The largest median job costs in this snapshot are build-debian-avx512 178 s (range 35–207), test-debian-ppc64le 106 s, native aarch64 test 76 s, LoongArch64 test 59 s, ASan 53 s, coverage test-debian 52 s, and AVM trace 51 s. The AVX512 variance alone makes unpaired total pipeline comparisons misleading. Do not propose removing architecture jobs on these figures.

Architectures and execution:

- Linux x86-64: GCC/Clang, minimum supported toolchain image, static build, AVX2 and AVX512 runners; full corpus, sanitizers and coverage in separate jobs. `-mavx` is used in AVX/AVX512 builds and the AVX512 corpus job. `trim_dsp=false` preserves scalar reference implementations where requested.
- Linux i686 and Windows i686: compile and run headers; the current `is_asm_enabled` expression excludes x86-32, so these do not exercise checkasm. Windows x86-64 runs through Wine, with full corpus only in test-win64.
- Native Linux AArch64 and ARMv7: GCC and old Clang build checks, plus native corpus jobs. Native macOS x86-64/arm64 runs headers/checkasm but does not clone test-data.
- Windows ARMv7/AArch64 and Android ARMv7/AArch64: cross-builds only, no runtime invocation.
- WASM32/WASM64: static Emscripten builds, header tests via Node, no asm/checkasm and no corpus.
- RISC-V64: Clang cross-build/checkasm through QEMU, plus one GCC artifact build consumed by four corpus/checkasm jobs at RVV lengths 128/256/512/1024 bits.
- AArch64 QEMU: one Clang artifact build consumed by five corpus/checkasm jobs at SVE lengths 128/256/512/1024/2048 bits. Both QEMU matrices use `--no-rebuild` and timeout multiplier 10.
- PPC64LE: native GCC13, full corpus plus checkasm. LoongArch64: GCC cross-build plus corpus/checkasm under QEMU `max`.

Most test jobs rebuild their own decoder; `needs: build-debian` establishes ordering, not artifact reuse (`dependencies: []`). The two QEMU artifact families explicitly reuse builds. Consequently small extra corpus passes generally add much less than another job/build would.

## Runtime flag map

The default data arguments are `-q --threads 1`, plus film-grain application. With main's corpus there are no per-sample thread overrides. Pending !6 adds one lossless-SB128 regression with its own 4-thread/4-frame override. Meson `--test-args` are appended after those arguments; the CLI processes repeated options in order, so the later value wins. A 1-thread suite is not necessarily uniformly single-threaded once a sample has an override.

| Job | Actual corpus runtime modes on main |
|---|---|
| test-debian | 1 thread; then 1 thread + negative stride. The two requested 2-thread seek modes currently run zero tests |
| test-debian-avx512 | 1 thread + `--cpumask avx512icl`; 2 threads / frame delay 2 + same mask |
| test-debian-asan | checkasm, then 1-thread corpus with `--cpumask 0` and `--cpumask 0xff`; leak detection disabled |
| test-debian-msan | C-only, all registered tests; another 1-thread data pass with `--frametimes /dev/null`; no seek tests despite building the binary |
| test-debian-ubsan | C-only, all registered tests; no seek tests despite building the binary |
| test-debian-tsan | 2/1, 2/2, 2/2 + negative stride; seek binary built but not registered |
| Windows64, native ARM, PPC, LoongArch and QEMU matrix data jobs | 1 thread, host/emulated CPU auto dispatch |
| test-debian-avm | Ordinary headers/checkasm, then separate trace loop on six hardcoded samples, `--threads=1`, null muxer |

`--cpumask` limits features supported by the host; it cannot enable absent hardware. `0` selects scalar C. `0xff` permits the current x86 SIMD flag bits, including AVX512 where available. Neither ASan pass is an exhaustive forced run at each intermediate SIMD level. Intermediate tiers are directly exercised by checkasm. No broad extra SIMD runtime matrix is justified by the evidence here.

## What checkasm proves

The registered groups are bacp, msac, palette, refmvs, and two bitdepth instantiations of CCSO, CDEF, deblock, filmgrain, intra prediction, inverse transforms, loop restoration (including GDF), motion compensation and secondary transforms: 22 top-level groups with both bitdepth implementations. The observed x86 jobs report **2,524 tests passed**; this count is specific to that revision and runner feature set, not a count of codec features or streams.

Checkasm compares optimized functions to their reference implementations using generated buffers and parameter combinations, and checks supported CPU tiers: SSE2/SSSE3/SSE4.1/AVX2/AVX512; NEON/DOTPROD/I8MM/SVE/SVE2; LSX/LASX; VSX/PWR9; RVV. Actual execution depends on available features and whether a distinct optimized function exists. High-bitdepth tests include 10/12-bit inputs; for example filmgrain and GDF choose a randomized 0x3ff or 0xfff maximum. Chroma layout loops include 420/422/444. A single randomized invocation does not exhaust every combination.

This catches DSP mismatches, buffer overwrites and ABI errors, but does not provide an independent normative reference for scalar C, parse real bitstreams, validate reference-picture transitions, or exercise scheduler/flush integration. Kernel coverage can therefore be high while whole-decoder coverage is missing.

Important silent behavior: checkasm immediately returns success with `TRIM_DSP_FUNCTIONS`. The static release job's log confirms `reference functions unavailable, reconfigure using '-Dtrim_dsp=false'`. The old-Clang AArch64/ARMv7 build jobs also leave release trimming at its default. This is not the highest-priority fix because dedicated untrimmed jobs already compare those implementations. The header suite only checks that each public API header compiles as C99; it is not an API behavior suite. MSan/UBSan's `enable_asm=false` builds do not register checkasm at all.

Fuzzer executables already exist (single-thread, multithread, allocation-failure variants), but the audited CI does not register fuzz runs. This audit does not establish the state of external continuous fuzzing, nor propose a new fuzzing service without a separate review.

## Test-data wiring and format coverage

`testdata_tests` defaults to false. `tests/meson.build` enters `tests/dav2d-test-data` only when enabled. `.testdata-common` updates/clones a mirror of upstream test-data, clones it into that path, and prints its revision. It follows current test-data main rather than a pinned sample revision.

Test-data's top-level Meson file registers a sanitizer timeout setup (3×), sets default CLI arguments, and includes `avm` when 8-bit support is built and `avm-10bit` when high-bitdepth support is built. Each row registers a CLI decode in both `avm` and `testdata` suites, verifying a stored raw-output MD5. High-bitdepth selection means 10 **and** 12 bits; the directory name does not restrict it to 10. Current main has 14 8-bit and two 10-bit samples, 94,058 bytes, with no 12-bit samples or IVF fixtures. The existing coverage additions supply 4:2:2, 4:4:4, 12-bit, still headers, resize, SB256, tile rows and more grain behavior.

Test-data CI reverses the dependency: clone decoder main (or `DAV2D_REPO`/`DAV2D_REF` override), symlink this data checkout into it, build, and test the candidate samples. Its ten jobs are native release, ASan, UBSan, C-only MSan, TSan, AArch64, PPC64LE, ARMv7, AVM MD5 verification and sample-list validation. Common native jobs run normal CPU dispatch and `--cpumask 0`. TSan overrides this with 2/1 and 2/2; !12 adds 4/4 to the common jobs and TSan. ARMv7 has its own script and !12 does not add a 4/4 pass there; MSan also has its own script. There is no checkasm invocation in test-data CI.

The AVM MD5 job validates listed samples against av2-normative and their stored MD5s. !9 enables `CONFIG_TESTONLY_12BIT_SUPPORT=1` for that job; without it AVM rejects 12-bit samples. The list check only ensures each tracked `*/*.obu` basename appears in its directory's Meson file; it does not validate trace compatibility.

Observed sample CI [753293](https://code.videolan.org/EwoutH/dav2d-test-data/-/pipelines/753293) runs **35 samples**, normal/C passes 0.879/0.906 s and TSan 0.667/0.629 s. Its job times include builds: release 37.55 s, ASan 37.04, UBSan 57.76, MSan 22.30, TSan 21.73, AArch64 80.59, PPC64LE 97.48, ARMv7 39.79, AVM MD5 34.14, list check 5.67. These are one observation each, not added-cost estimates.

Threading CI [753294](https://code.videolan.org/EwoutH/dav2d-test-data/-/pipelines/753294) runs **16**, not 35/38, samples: its branch is based on main without the sample MRs. Release/C/mt4 invocations take 0.711/0.679/0.692 s; TSan 2/1, 2/2 and 4/4 take 0.538/0.516/0.547 s. Its ten job times are in the captured JSON. The handoff's 38-sample local checks and a green 16-sample CI pipeline are separate evidence.

## Coverage: what the numbers mean

The [published coverage artifact](https://code.videolan.org/videolan/dav2d/-/jobs/2986098/artifacts/file/coverage/index.html) reports **76.4983% overall lines**, **15,751/20,590 lines**, **663/866 functions**, and **15,234/23,708 branches (64.3%)**. Despite `gcovr.cfg` exclusions, this HTML report includes tests, tools and the checkasm framework in its denominator. Source-only directory coverage is **12,743/15,819 lines (80.6%)**, **479/543 functions (88.2%)**, **12,656/17,296 branches (73.2%)**. Coverage includes checkasm and its scalar-reference calls, not just samples. It is not an independent corpus sufficiency score and does not measure handwritten assembly branches.

Useful file contrasts from [coverage-src.html](data/coverage-src.html):

| File | Lines | Branches |
|---|---:|---:|
| thread_task.c | 0/640 (0%) | 0/513 (0%) |
| obu.c | 997/1,639 (60.8%) | 770/1,554 (49.5%) |
| lib.c | 340/496 (68.5%) | 176/359 (49.0%) |
| recon_tmpl.c | 1,911/2,534 (75.4%) | 1,768/2,694 (65.6%) |
| fg_apply_tmpl.c | 86/113 (76.1%) | 36/88 (40.9%) |
| ipred_tmpl.c | 970/971 (99.9%) | 657/732 (89.8%) |
| looprestoration_tmpl.c | 586/588 (99.7%) | 441/470 (93.8%) |

Generation occurs immediately after the initial all-tests run, before the empty seek invocations and negative-stride pass. !1138 currently appends mt4 after that too. The zero scheduler figure describes the collected report, not all CI jobs: TSan and AVX512 explicitly decode with two threads.

JUnit collection has a separate defect: `.test-common` uploads only `testlog.junit.xml`, but sanitizer setup runs write `testlog-sanitizer.*`. ASan, MSan and TSan job logs explicitly end with `no matching files` / `No files to upload`; their successful exit status does not make test results appear in GitLab's test report. Repeated invocations also overwrite the same log base, so ordinary test-debian retains only its final negative-stride pass in JUnit. Use a distinct `testlog-*` base for each invocation and upload `testlog*.junit.xml`, as test-data already does for its common native/C/mt passes. This preserves diagnostics at negligible execution cost; it adds no test coverage by itself.

The local `round5/cov/` tool instruments C with Clang `-fsanitize-coverage=trace-pc-guard`, recording one hit byte per compiler guard. Its existing C-only binary has **19,423 stored positions**. Reusing exactly that binary, this audit freshly decoded the public samples and checked their stored MD5s:

| Corpus | Samples | Bytes | Hit stored guards | Fraction of stored positions |
|---|---:|---:|---:|---:|
| main | 16 | 94,058 | 8,843 | 45.53% |
| main + !6 | 23 | 125,461 | 9,108 | 46.89% |
| main + !6 + !9 | 35 | 145,355 | 10,692 | 55.05% |

This is **+1,849 hit guards (+20.9%) over public main**, or **+1,584 (+17.4%) for the 12 samples alone**. JSON files contain hashes, sample names, decoder status evidence via successful `--verify`, and per-sample counts. The 12 additions are 19,894 bytes after the reviewed 4:2:2 replacement; do not reuse the older greedy-selection size/count blindly.

The original candidate workflow ranks the marginal union of per-stream guards against the baseline, with gain divided by `(sample KB + 2)` to favor compact streams. Twenty initial picks were re-encoded from public deterministic sources, rechecked, then reduced to 12. That search used our larger archive to discover candidates, but the fresh measurements here only use the public git samples. Exact greedy selection does not promise exhaustive coverage or a feature oracle.

Limitations: compiler guards are not gcov source branches; the executable also contains CLI/demuxing code; no asm or scheduling coverage is established by these one-thread runs. Guard IDs are only comparable within the same binary. The callback stores `n` bytes for guards numbered 1..n, so index zero is unused and the last guard is omitted; retain that convention for comparing historical data, and correct it before a future instrumentation rebuild. The percentages above describe stored positions, not a whole-decoder completeness metric. The callback is also not suitable for race-free multithread coverage measurement as written.

## AVM trace job

test-debian-avm shallow-clones av2-normative, applies dav2d's patches, enables header/block/pixel/refmv debug prints in both decoders, and traces frames whose offset is at most four. It builds AVM without its tests or encoder, builds dav2d debugoptimized/untrimmed, runs ordinary headers/checkasm, then loops over six hardcoded 8-bit files with `diff -uw`. It does **not** enable testdata_tests or run a general corpus MD5 suite. It does clone test-data through its shared before_script to supply those six files.

The fresh local reproduction found **14 equal traces / 35 streams**, both decoders returning success for all 35. Of the 14 compatible streams, **eight are missing from CI**, including both 10-bit samples. See [traces.json](data/traces.json) for every result. All 12 format/coverage additions differ in their traces. The suite's pixel MD5s pass independently; a trace mismatch by itself is not a decoded-pixel bug. Debug print discrepancies have not been individually diagnosed here.

For now, add only the compatible eight (one depends on !6), using paths relative to the test-data root. A shared explicit trace-compatible list and a check of that list in test-data CI are possible follow-ups, awaiting the maintainer response to [the existing !9 discussion](https://code.videolan.org/videolan/dav2d-test-data/-/merge_requests/9#note_598396). Adding a second AVM build/job in test-data merely to validate metadata needs a separate cost justification. No compatible 12-bit sample has been demonstrated, so turning on 12-bit in the trace job alone adds no exercised feature.

## Review artifacts and reproduction

Short upstream-facing proposal text is in `upstream-drafts/dav2d-testing-proposals.md` (outside git, as required). Three config patches are beside it: `dav2d-testing-bitdepth.patch` and `dav2d-testing-junit.patch` against main, and `dav2d-testing-report-order.patch` against !1138. They are draft config changes, not claimed CI-tested patches. The seek/flush proposal deliberately specifies the fixture and exit-status prerequisites rather than shipping a passing empty test or handing raw OBUs to an IVF-only harness.

Run from the AV2 repo with the existing shared Python environment:

```sh
python perf/2026-11-19-dav2d-testing/scripts/fetch-ci.py
python perf/2026-11-19-dav2d-testing/scripts/summarize-ci.py
python perf/2026-11-19-dav2d-testing/scripts/measure-corpus.py
python perf/2026-11-19-dav2d-testing/scripts/measure-traces.py
```

The first script requires authenticated GitLab network access; the local measurement scripts require the named existing builds and sample refs. Generated scratch files stay under this report directory and are ignored. Corpus/trace scripts use mutable local refs, so compare their recorded hashes with this evidence set when rerunning. To refetch HTML coverage, use `glab api projects/4935/jobs/2986098/artifacts/coverage/index.html`; the XML report artifact is not available through the ordinary per-file artifact endpoint (404), so this audit uses the published HTML and logged headline. Job logs and metadata preserve the sampled timing evidence even after artifact expiry.

Validation completed: all 35 public sample MD5s match in the named C build; all 35 trace pairs ran to success with 14 equal; the job matrix contains all 49 jobs and YAML parses; the saved source/live CI files agree; all three draft diffs apply to their declared bases and produce valid YAML. New configuration patches have not been run in GitLab, and no scheduler branch increase or seek runtime cost is claimed before that validation.
