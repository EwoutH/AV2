# dav2d testing review: addendum, 19 November 2026 (evening)

Second pass on top of the audit in [`../2026-11-19-dav2d-testing/`](../2026-11-19-dav2d-testing/README.md), which maps the CI matrix, checkasm, the coverage report, JUnit and the AVM trace subset. Read that first. This addendum adds two decoder bugs that the testing gaps hid, the data on threading and C-path sanitizers, and a merged ranking.

Baseline: dav2d upstream main `2ea62cc8`, test-data main `85af1c2`. Coverage numbers reuse the trace-pc-guard build `round5/build/main-cov` (dav2d `b130414d`, C only, debugoptimized). Sanitizer and seek builds are fresh from `2ea62cc8` in `/srv/compression/cache/av2conf/testreview/`. Since the pc froze on an uncapped seek run (not this session's FourPeople run, but this session also ran seek_stress uncapped earlier), every run here used `systemd-run --user -p MemoryMax=1G|3G -p MemorySwapMax=0`.

## Done on 19 Nov evening (ranks 1–4 of the first ranking)

| Was rank | Change | Outcome |
|---:|---|---|
| 1 | Land the coverage and regression samples | test-data !6, !9, !10 and !12 merged. Drafts !8 (GER, waits for dav2d !1073) and !11 (CLK, waits for !1135) rebased onto main. On BBB's question whether !9 should name the fixing MR per sample: 11 of 12 already decoded correctly on main `5bf33c8f` (14 Nov), so they are coverage samples; only `avm.testsrc.130x74.l12.10bit.tile-rows2` needed a fix, !1079 (`7e899beb`, bisected) |
| 2 | rbultje's !1136 + !1137 (sequence header parsing, seek_stress) | Tested and reported on !1136 ([note 598462](https://code.videolan.org/videolan/dav2d/-/merge_requests/1136#note_598462)), including the fuzzer impact. gramner reviewed !1136 (two small simplifications). Our duplicate branch deleted |
| 3 | Negative-stride shifts + UBSan `--negstride` | Opened [dav2d !1139](https://code.videolan.org/videolan/dav2d/-/merge_requests/1139): CI change alone fails ([753313](https://code.videolan.org/EwoutH/dav2d/-/pipelines/753313)), fix + CI green ([753312](https://code.videolan.org/EwoutH/dav2d/-/pipelines/753312)) |
| 4 | Seek tests on IVF samples | Opened draft [test-data !13](https://code.videolan.org/videolan/dav2d-test-data/-/merge_requests/13): two IVFs (6.4 and 5.5 KB, key frame every 8 frames, 4 and 3 random-access points), decode + seek_stress tests in `testdata_seek-stress`, the suite run in the common CI jobs, `check-samples-listed` covering `*.ivf`. Draft until !1136/!1137 land: with them testdata 40/40 and seek 2/2 at 1t, 2/1, 2/2, 4/4 (ASan, local); without them seek_stress is killed at a 512 MB cap. A fork push briefly started a pipeline against dav2d main; cancelled during the build phase. Validation pipeline against the combined branch `test-seek-1136-1137`: [753327](https://code.videolan.org/EwoutH/dav2d-test-data/-/pipelines/753327), 10/10 jobs green, seek tests 2/2 in each. Each seek test takes about 0.04 s: 10–11 seeks and 56 (1 thread) or 134 (2/2) `dav2d_send_data` calls per run, so it does decode, but lightly |

## Remaining, re-ranked

| Rank | Change | Why | State |
|---:|---|---|---|
| 1 | AVM trace job: 6 → 14 samples, list in test-data with a trace check in its CI | The trace diff catches header/block divergence that an MD5 only shows as "wrong". 8 trace-clean samples are not in the job (first audit, `traces.json`); rbultje OK'd the direction (note 598451) | Not started. Recheck which of the newly merged !9/!10 samples are trace-clean first (all 12 of !9 differed on 19 Nov) |
| 2 | Make seek_stress fail on decode errors and open failures | Without it, !13's seek tests only catch crashes, sanitizer reports and hangs; open failure and decode errors return `EXIT_SUCCESS` | After !1137 lands (same file). One small dav2d MR |
| 3 | Fuzzing follow-up | With !1136 the fuzzer reaches the decoder for the first time on valid AV2 input; the public samples (38 OBU on main, + 2 IVF in !13) are a seed corpus | Session 2 prompt (robustness and fuzzing) |
| 4 | Coverage collected after all runs, JUnit per invocation; land !1138 | Visibility: the report shows `thread_task.c` at 0%; sanitizer jobs upload no JUnit | Patches from the first audit in `upstream-drafts/dav2d-testing-{report-order,junit}.patch`; !1138 open |
| 5 | Bitdepth-limited jobs run the test data | Cheap, but both pass locally (21/21, 9/9), so it finds nothing today | `upstream-drafts/dav2d-testing-bitdepth.patch` |
| 6 | Small leads | `prep_bilin_c` (77 edges) never reached by anything; seeks onto the OLK sample's key frame print "Invalid argument" (leading frames?) | Look at in the robustness session |

Not worth proposing on this data: more thread/frame-delay combinations in MSan/UBSan/ASan (clean apart from rank 3), forced intermediate x86 SIMD levels (checkasm covers them), more architectures.

## Two bugs hidden by the gaps

### `dav2d_parse_sequence_header()` still reads AV1 OBU headers

`src/obu.c:726` reads forbidden bit, a 4-bit type and an optional length field after the header. AV2 OBUs start with a uleb128 length, then extension flag, 5-bit type and 2-bit tlayer, as `dav2d_parse_obus()` reads them. So the function returns `DAV2D_ERR(ENOENT)` for every AV2 temporal unit (`scripts/psh.py` calls it per IVF frame through ctypes: 0 of N frames on main for all 7 public repro IVFs, 1–3 with the fix).

Callers that loop "until a sequence header":

- `tests/libfuzzer/dav2d_fuzzer.c:148` skips frames until one parses. On main, for a 5-frame IVF, gdb counts 5 `dav2d_parse_sequence_header` calls and 1 `dav2d_send_data` (the final drain); with the fix, 1 and 6. So fuzzing from valid AV2 seeds exercises no decoding. Relevant for the fuzzing follow-up (session 2).
- `tests/seek_stress.c:150` (`seek()`): every seek reads to EOF, `ivf_read()` creating a new `Dav2dData` per frame without unreferencing the previous one, and the final `while (seek(...))` loop never ends. Release build: 943 MB RSS after 1 s, killed at the 1 GB cap. ASan has no leak to report because the process never exits. With the fix: 7 MB peak, exit 0 in 0.5 s on two streams. This is the same mechanism as the FourPeople ASan run (11 GB in ~80 s) that froze the pc.
- `tools/dav2d.c:246` (`--skip`): exits 1 on every stream on main.
- `examples/dav2dplay.c:413`: seeking never finds a sequence header.

rbultje's !1136 (opened 18:39, before this was found here) reads the header like `dav2d_parse_obus()`, the same as our `fix-parse-seq-hdr-av2`. !1137 fixes seek_stress itself (unref before each read, only read once the data is consumed, stop the end-seek loop). Tested together (`b-mr-asan`, `b-mr-rel`): 84 of 84 ASan runs on 28 IVFs at 1t, 2/2 and 4/4 exit 0 with no ASan/LSan report and a sampled peak RSS under 30 MB (`seek/mr-summary.txt` in the cache dir). On FourPeople 480x270 it makes 355 `dav2d_send_data` calls, 199 flushes and 20 seeks, so it does decode. After some seeks onto the OLK stream's open-loop key frame it prints "Error decoding frame: Invalid argument", presumably the leading frames; not investigated.

### Left shifts of negative strides

`ystride << ss_ver` (`ipred_tmpl.c:900`, `:1065`), `src_stride << 1` (`:1175`, `:1189`) and `PXSTRIDE(src_stride) << ss_ver` (`ccso_tmpl.c:95`) are undefined for negative strides. GCC/Clang produce the intended result, so asm and release runs pass, but UBSan (`halt_on_error=1`, as in CI) aborts. CI runs `--negstride` only in `test-debian` (asm, 1 thread) and TSan (asm). The fix multiplies instead; with it, 76 of 76 UBSan runs (38 samples, 1 thread and 3 threads/frame delay 3, both `--negstride`) pass with unchanged MD5s. `tmp_stride << ss_ver` at `ccso_tmpl.c:128` is a positive local stride and left alone.

CI detail: `meson test --test-args "--negstride"` fails with a usage error, because argparse takes a value starting with `--` as an option. The existing jobs only work because their values contain a space. Use `--test-args=--negstride`.

## Threading and C-path sanitizers

The CI coverage report is generated after the 1-thread pass only. To see what threading adds, the 40 public and pending samples were run on the guard build in five modes (`scripts/run.py`, `scripts/ana.py`):

- 854 edges are reached only with `--threads 2/4` (frame delay 1, 2 or 4), about 8% of what the samples reach: `dav2d_worker_task` 221, `dav2d_read_coef_blocks` 123, `derive_lowest_px` 68, `read_luma_tx_cf` 56, then task-queue and frame-init code. `--threads 4 --framedelay 4` adds only 13 edges beyond 2/1 and 2/2; `--negstride` adds 53.
- In CI, only TSan (asm build) and AVX512 reach these, so the C code they call never runs under MSan/UBSan multithreaded.
- Running that combination locally (`scripts/san.py`: MSan, UBSan and ASan with `--cpumask 0`; 38 samples × 1t, 2/2, 4/4, 3/3+negstride = 456 runs) gave 36 failures, all UBSan + `--negstride` (rank 3). Nothing threading-specific.

Round-4 stress data agrees. Each of 13,322 configs was decoded with asm 1 thread, C ASan+UBSan 1 thread, and asm with a random thread/frame-delay setting. Of 774 failures, 1 was threading-only (v010628). 175 were sanitizer-only in the C build, mostly the UBSan null `rp` offset fixed by !1111, which a sample would have caught at 1 thread. So adding samples is worth far more than adding runtime flags.

## Coverage by bitdepth and stage (guard build, 18,247 mapped guards)

| Stage | Edges |
|---|---:|
| upstream 16 samples, `--threads 1` (what the coverage job sees) | 8,251 |
| upstream, all CI flag sets (1t, 2/1, 2/2, negstride) | 9,006 |
| + `--threads 4 --framedelay 4` | 9,015 |
| + !6 (7 samples) | 9,285 |
| + !9 (12) | 10,826 |
| + !10 (3) | 10,879 |
| + !11 (1) | 10,905 |
| + round-4 archive (3,779 synthetic streams, 1t) | 11,981 |

Bitdepth-templated functions: 8bpc 61% → 70% (with pending MRs) → 75% (archive); 16bpc 43% → 60% → 68%. Functions with 0 CI edges that the pending samples reach: the 4:2:2/4:4:4 `cfl_pred` specialisations, `dav2d_read_pal_plane` (chroma palette), scaled MC (`put/prep_8tap_scaled`, `ext_warp4x4_scaled`), `parse_ci_hdr`. Never reached by anything here: `prep_bilin_c` (77 edges) and most of the remaining Wiener filter branches; not investigated.

These guard counts differ slightly from the first audit's (8,843 for main) because it counts all stored positions; this one counts guards mapped to a function through objdump (`scripts/gmap.py`, 18,247 of 19,423) and includes the threaded modes.

## Reproduction

Scripts in `scripts/` (paths inside are absolute to the pc's cache):

- `samples.py`: extracts the public and pending test-data samples per MR into `s/` and writes `sets.json`.
- `gmap.py <binary> <out.json>`: guard index → function and line, from objdump of the trace-pc-guard build.
- `run.py`, `ana.py`: guard runs in five modes and the stage/file/bitdepth tables.
- `san.py [jobs]`: MSan/UBSan/ASan-C runs over the samples.
- `seekrss.sh <bin> <ivf> [args]`: RSS sampler; always run it under `systemd-run --user -p MemoryMax=1G -p MemorySwapMax=0`.
- `psh.py <libdav2d.so> <ivf>`: calls `dav2d_parse_sequence_header` on each IVF frame.

`ci-coverage-files.txt`: per-file line/function/branch counts from the CI coverage artifact (job 2986029), ranked by missed lines.
