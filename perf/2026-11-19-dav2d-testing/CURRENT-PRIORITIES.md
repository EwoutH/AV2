# Remaining testing priorities, 19 November 2026

Checked against GitLab at **21:17 CET**: dav2d main `840e2f084768944bfa6f11d49376da7ead167a46`, test-data main `a6aa3b48debdd20d2d6405a3fde68fe2a344bbb2`. MR states and current source snapshots are saved in `data/status-refresh.json` and `data/refresh-*`. This replaces the original audit's action ranking, not its historical measurements. The [later testing review](https://github.com/EwoutH/AV2/blob/worktree-dav2d-testing-review/perf/2026-11-19-dav2d-testing-review/README.md) supplies the sanitizer and seek results cited below; it is on the separate review branch, not AV2 main.

| Rank | Remaining action | Evidence and value | State / next step |
|---:|---|---|---|
| 1 | Finish the seek/flush chain: dav2d !1136 + !1137, then test-data !13 | The sequence-header API still parses AV1 headers, preventing the fuzzer and seek harness from reaching AV2 decoding normally. The seek loop can allocate without bound. The two new IVF fixtures turn the empty seek suite into actual lifecycle tests | All three MRs remain open; !13 is draft. Both decoder MRs have successful head pipelines. !13's combined-branch validation is green. Resolve review and land decoder fixes before enabling the sample tests against main |
| 2 | Land negative-stride fix and UBSan pass, dav2d !1139 | The CI-only change fails; fix + CI passes. UBSan found negative left shifts in 36/38 samples. This closes a demonstrated sanitizer gap, rather than adding speculative flag combinations | MR open, successful head pipeline. Existing contribution covers five stride expressions and `--test-args=--negstride`; no duplicate MR needed |
| 3 | Make seek_stress fail on input/decode errors after !1137 | !1137 fixes leaks and loops but its common exit still returns `EXIT_SUCCESS`. Registered seek tests can therefore pass after logging decode errors or failing to open their fixture | Separate small harness change after the same-file work settles. Verify bad input fails and valid supported random-access cases pass; distinguish expected unseekable positions from fatal errors |
| 4 | Collect coverage after runtime passes and preserve JUnit for every invocation | Four-frame runs now exist on main, but report generation still precedes them. The artifact rule still requests only `testlog.junit.xml`, while sanitizer setups use another name and repeated passes overwrite their reports | The report-order draft now targets a merged change, so it is directly relevant to main. Use unique log bases and `testlog*.junit.xml`. No new decode passes required; validate artifact contents in CI |
| 5 | Decode the corresponding samples in existing 8-only/high-bitdepth-only jobs | Both jobs still compile only. Test-data main now offers 28 8-bit and 10 high-bitdepth samples. The later review's earlier local subsets passed 21/21 and 9/9, so this is preventative coverage with no demonstrated current failure | Existing bitdepth config draft remains relevant. Measure checkout/subset-run cost in CI; no new decoder builds needed |

I rank the demonstrated decoder/harness failures above reporting and preventative matrix expansion. Rank 1 is already implemented and validated in MRs, but remains a dependency chain to finish; rank 3 is still new implementation work. No new heavy tests were run for this refresh.

## Completed: remove from the queue

- Test-data [!6](https://code.videolan.org/videolan/dav2d-test-data/-/merge_requests/6), [!9](https://code.videolan.org/videolan/dav2d-test-data/-/merge_requests/9) and [!10](https://code.videolan.org/videolan/dav2d-test-data/-/merge_requests/10) are merged. Main has **38 OBU decode samples**, including the format/coverage and recent regression additions. Do not keep recommending that these MRs be landed or present the old 16-sample baseline as current.
- Dav2d [!1138](https://code.videolan.org/videolan/dav2d/-/merge_requests/1138) and test-data [!12](https://code.videolan.org/videolan/dav2d-test-data/-/merge_requests/12) are merged. The additional four-frame passes are already configured. The original observed cost of 1.782 summed invocation seconds was for 16 streams; it is not a current 38-stream cost measurement.

## Already assigned: AVM tracing

The user confirms tracing is running in another session. Leave it there, outside this queue of work to pick up. The original proposal to expand six compatible samples to 14 remains historical evidence, not a newly verified target for today's 38-sample corpus. That session should own the updated compatible set, trace-print fixes and shared-list proposal. No tracing jobs, files or branches were modified in this refresh.

## Follow-ups that need investigation

- **Fuzzer smoke test after !1136:** the later review counted only the final drain call to `dav2d_send_data` before the header fix, versus actual frame submissions after it. That is strong justification for a small seed-based smoke test that proves decoding is reached. It does not yet establish the value or cost of a new continuous fuzzing service. Keep the broader robustness/fuzzing review separate.
- **GER/CLK regression samples:** test-data !8 and !11 are still drafts waiting for decoder !1073 and !1135. They become actionable with those fixes; do not enable known-failing tests against main.
- **More threading modes/architectures:** still low priority. The later review's 456 C-sanitizer runs found only the negative-stride UBSan failures, and mt4 added only 13 mapped guards beyond 2/1 and 2/2 in that experiment. Those mapped guard counts are a different metric from this audit's stored-position counts.

## Constraints and validation

Do not activate !13 against unfixed dav2d main: the reviewed seek run was killed at a 512 MB cap before !1136/!1137. Any future heavy seek validation needs a memory limit, as documented in the handoff. This refresh only reads source, MR metadata and existing results.

The [seek-test validation pipeline](https://code.videolan.org/EwoutH/dav2d-test-data/-/pipelines/753327) and [negative-stride failing](https://code.videolan.org/EwoutH/dav2d/-/pipelines/753313) / [fixed](https://code.videolan.org/EwoutH/dav2d/-/pipelines/753312) pipelines support ranks 1–2. The later review reports 84/84 ASan seek runs with the decoder fixes, 2/2 new seek fixtures across the requested modes, and 76/76 UBSan negative-stride decodes with unchanged MD5s. These are inherited validation results, not reruns from this session.

The report-order, JUnit and bitdepth drafts were checked against the refreshed dav2d main and still apply and parse as YAML. They remain drafts without CI validation. Nothing was posted upstream during this refresh.
