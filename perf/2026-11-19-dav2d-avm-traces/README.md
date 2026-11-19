# dav2d / AVM trace coverage, 19 November 2026

Propose the shared test-data list with **14 already compatible samples**, then expand to **34 of 38** after the small printing fixes below. Keep `diff -uw`, the existing six samples, the pixel/coeff dumps, and the current debug window. Do not spend time making the last four compatible now.

This follows [rbultje's agreement on test-data !9](https://code.videolan.org/videolan/dav2d-test-data/-/merge_requests/9#note_598451) with the proposal in [note 598396](https://code.videolan.org/videolan/dav2d-test-data/-/merge_requests/9#note_598396). The owner supplied this later IRC clarification from BBB: keep working cases working; extending trace compatibility is not urgent, because the original purpose was decoder-mismatch debugging. The owner also said fixes with minimal added complexity can still go in. Accordingly, the CI change and the printing fixes are separate patches; no decoder algorithm changes or trace-normalizing filter are proposed.

Nothing was posted upstream. These are local proposals, not GitLab pipeline results.

## Evidence and useful coverage

The first audit's **14/35** reproduces. Test-data main now has three more samples, so the frozen current denominator is **38**. With the original trace binaries it is **14/38**; all three additions initially differ. With the proposed printing fixes it is **34/38**. Independently, both trace-enabled decoders reproduce every stored full-output MD5 on all 38 samples, including film grain.

| Selected samples | Exact traces | Full-stream C guards hit | Median local trace-loop time |
| --- | ---: | ---: | ---: |
| Existing CI list | 6 | 5,171 | 0.515 s |
| Shared list before fixes | 14 | 8,653 | 1.168 s |
| Expanded list after fixes | 34 | 10,597 | 2.723 s |
| Entire current data set | 34 after fixes | 10,746 | Not timed as a passing loop |

The 14-sample list adds eight samples already known to work: partial lossless, QM, QM+CCTX, OPFL2, tile columns, OPFL/refinemv disabled, and both existing 10-bit samples. The 34-sample list also exercises all four 12-bit samples, 4:2:2 and 4:4:4, palette/screen content, film grain, resize, forward keyframes, tile rows, and additional lossless cases. Names and exact membership are in patches 02 and 05, not inferred from automatic acceptance of every file.

The guard figures come from the same C-only b130414d trace-pc-guard binary, with 19,423 stored positions, decoding complete streams in one thread and verifying MD5s. They are a **coverage proxy for the selected streams**, not coverage of the trace window, individual codec features, or the new debug printing code. The 14-sample subset covers 80.5% of the union hit by all 38 streams; the 34-sample subset covers 98.6%. The excluded four add only 149 guards beyond the 34-sample union in this build.

Timing used the actual shared shell runner, null decoded output, exact diff, and file-backed trace logs, five repetitions per subset. Initial one-minute load was below 1. The added loop cost was approximately 0.65 s for 6→14 and 2.21 s for 6→34 on this i5-4590. The 34 comparison uses the fixed binaries; 6 and 14 use the original binaries. These are local warm-loop measurements, not runner/job predictions. The added test-data job builds AVM and dav2d independently; its build, clone, and total CI costs have **not** been measured. It preserves the existing independent AVM MD5 job, so it does add another reference build.

## Why matching MD5s do not imply matching traces

The MD5 verifies final output pixels over the complete stream. The trace includes headers, entropy states, selected coefficients, and intermediate predictions/reconstructions. Its printing sites must agree about ordering, dimensions, coordinates, and the meaning of stored values. Different text need not mean different decoded output.

The small fixes that were built and checked are:

| Printing issue | Source and correction |
| --- | --- |
| Palette dump timing and dimensions | dav2d `src/recon_tmpl.c`: move the luma palette dump from block prediction to `recon_b_luma_tx()`, after coefficient decoding and before inverse transform, with transform dimensions. AVM already prints there. Palette pixels themselves are unchanged. |
| Unmatched scaling diagnostics | Remove dav2d's implementation-specific `Off ...` and `Emu` prints from scaled `mc()`. AVM has no corresponding lines. Prediction and reconstruction dumps remain. |
| Swapped color labels | AVM `obu_ci.c` passes matrix and transfer in the opposite order to its `trc`/`mtrx` labels. Swap the printf arguments, not parsed color values. This is in dav2d's local AVM instrumentation. |
| TIP reference versus output pictures | AVM `tip.c` dumps the entire synthetic reference picture, including outside the selected frame/spatial window. dav2d constructs reference predictions on demand and has no matching whole-reference dump. Print the TIP picture here only for `TIP_FRAME_AS_OUTPUT`, with the shared `BLOCK_TO_DEBUG` predicate; ordinary block prediction dumps still cover TIP references. |
| Large inter prediction dumps | AVM `decodeframe.c` prints every 64×64 chunk of a selected large block; dav2d's selected region prints only the first chunk. Limit this AVM dump to that first chunk. This aligns the existing spatial selection rather than broadening it. |
| Suffix metadata header omissions | AVM `obu.c` reads suffix metadata in a second loop without the OBU printf. Add it after accepting the suffix/padding OBU. The 10-bit tile-rows sample contains 13 such missing lines. |
| Derived segment IDs | AVM `read_segment_id()` returns the spatial prediction early for a skipped non-lossless block without printing it. Print that derived ID, matching dav2d. The 12-bit still-screen sample exposed three lines. |
| Absent grain fields | AVM `obu_fgm.c` subtracts 128/256 from default-zero unsigned chroma multipliers/offsets even when those fields were absent. Print zero when that plane has no scaling points, matching dav2d's signed representation. No grain parameters are changed. |

The first three experimental fixes (palette, color labels, and a TIP frame-window gate) gave 24 exact matches. Aligning TIP reference/output selection and removing scaling diagnostics gave 29. The final small print fixes gave 34. The latter is the exported, validated proposal; the intermediate source variants are not maintained as separate patch series.

These findings justify treating these particular failures as instrumentation differences. They do not establish that every future trace mismatch is harmless. The stored MD5 checks remain necessary alongside the trace test.

## The four exclusions

| Sample | Remaining difference and source evidence |
| --- | --- |
| `avm.testsrc.176x144.l12.444.fg` | `HDR: post-refs` prints all seven slots although fewer are active. AVM retains prior values in inactive `cm->remapped_ref_idx[]` slots; dav2d's corresponding unused `hdr->refidx[]` slots are zero. The differing tails are 3,3 versus 0,0 and 2 versus 0. A future format change could print only the active references in both decoders. |
| `avm.testsrc.176x144.l8.sframe` | AVM prints the signalled `features->enable_bawp` bit as 1; dav2d stores/prints effective BAWP as 0 on an S-frame. AVM's `av2_allow_bawp()` in `reconinter.h` explicitly rejects S-frames. This is signalled versus effective state, not a different entropy read. |
| `avm-v15.0.0-bus.352x288.l5.seg1` | AVM prints extra intra edge/prediction/coefficient/reconstruction dumps for transforms of a large block. Its intra/transform helpers select using the coding-block origin (`xd->mi_row/mi_col`); dav2d's transform helper uses the current transform position (`t->by/bx`). They select different regions beyond the initial 64×64 area. |
| `avm.testsrc.130x74.l4.10bit.sb256` | After fixing inter-prediction chunk selection, the remaining extra `dq`/`recon` dumps have the same coding-block versus transform-position selection issue. Harmonizing that consistently would touch several instrumentation helpers. |

The last two involve selecting different transform dumps, not a demonstrated unequal final reconstruction. They are excluded from exact comparison rather than filtering out pixel or coefficient lines. [residuals.json](data/residuals.json) contains a diagnostic comparison of non-pixel lines for the four exclusions; it is never used by CI. The two transform cases have identical non-pixel lines under that diagnostic. Raw first-difference excerpts are also retained in `data/fixed-*.diff` (bounded to 8,000 characters each).

## Patch ordering and review scope

All patches apply to the frozen bases in [patch-bases.json](data/patch-bases.json). Existing unrelated working files and canonical clones were left untouched.

1. **test-data list and CI check:** [02-testdata-shared-trace-list.patch](patches/02-testdata-shared-trace-list.patch). Adds `trace-samples.txt` with 14 paths relative to the data root and `check-traces.sh`. A separate CI job uses the configured dav2d repository/ref, its AVM patches, the same debug definitions/window as dav2d CI, and 12-bit reference support. The existing MD5 job remains independent. Land this before its consumer.
2. **dav2d consumes that list:** [01-dav2d-shared-trace-list.patch](patches/01-dav2d-shared-trace-list.patch). Replaces the hardcoded array/loop with the shared runner. It retains ordinary Meson tests and the original six samples. This can land without the printing fixes.
3. **Small printing corrections:** [03-dav2d-prediction-traces.patch](patches/03-dav2d-prediction-traces.patch) and [04-avm-debug-output.patch](patches/04-avm-debug-output.patch). The latter appends `patches/0006-...patch` to dav2d's existing reference instrumentation; it does not patch upstream AVM decoding logic. These two form the optional debug-alignment proposal and can be reviewed independently of CI.
4. **Enable the expanded list:** apply [06-dav2d-enable-12bit-traces.patch](patches/06-dav2d-enable-12bit-traces.patch) before [05-testdata-expand-after-fixes.patch](patches/05-testdata-expand-after-fixes.patch). Expand to 34 only after the printing changes are available in the dav2d ref used by test-data CI. Its new trace job already builds the reference with 12-bit support.

The list is explicit because a new MD5-clean sample need not have a compatible trace. New entries should pass the shared runner; samples outside the list continue receiving the ordinary MD5 tests. The four exclusions do not block coverage expansion or require changes to decoding state.

## Validation and reproduction

- Original audit: dav2d b130414d, patched AVM 9123f33b (av2-normative 14f43e4c plus dav2d's five patches and CI debug definitions), all 38 public test-data samples at a6aa3b48. Both decoders return success, 14 exact traces, 38/38 MD5s each. [baseline.json](data/baseline.json).
- Final audit: dav2d 840e2f08 plus printing fixes, the same patched AVM plus the appended printing patch, same 38 streams and debug definitions. Both return success, 34 exact traces, 38/38 MD5s each. [fixed.json](data/fixed.json). The three dav2d commits between the decoder bases concern frame-thread error/progress handling and CI; both audits use one thread.
- Source patches reproduce the experimental instrumented source trees byte-for-byte when combined with the saved debug-enabling diffs. All six proposal patches apply in their documented order. The appended AVM patch was also successfully applied with `git am` to the debug-disabled reference source.
- Both CI YAML files parse; the generated test-data shell script and shared runner pass shell syntax checks. The shared runner passes the 14 original and 34 fixed comparisons and rejects an actual S-frame trace mismatch, an empty list, a missing sample, and a decoder failure. A final line without a newline is handled. [runner-validation.json](data/runner-validation.json).
- Binary, shared-library and source-diff hashes are in [final-provenance.json](data/final-provenance.json); sample hashes and reference MD5s are in the audit JSON files. This includes libdav2d, not just its dynamically linked CLI executable.
- No new GitLab jobs or container-image builds were run. No sanitizer or multithreaded claim is made for these debug-print changes.

Sources and generated traces/builds stay under this report's ignored `scratch/`. On this server, the original binaries are also still in `cache/av2conf/round5/trace/`. To reconstruct fixed sources in a fresh report checkout with the named local clones available:

```sh
python perf/2026-11-19-dav2d-avm-traces/scripts/prepare.py
nix develop --command bash perf/2026-11-19-dav2d-avm-traces/scripts/build.sh
python perf/2026-11-19-dav2d-avm-traces/scripts/recheck.py --variant baseline
python perf/2026-11-19-dav2d-avm-traces/scripts/recheck.py --variant fixed
python perf/2026-11-19-dav2d-avm-traces/scripts/check-proposals.py
python perf/2026-11-19-dav2d-avm-traces/scripts/coverage.py
```

`prepare.py` refuses to overwrite existing source folders. Rechecking existing prepared sources starts with the build/recheck commands. Provenance is frozen in the saved results; reruns regenerate local measurements and should be compared against those hashes.
