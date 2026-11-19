# Submitted 14-sample changes

The owner approved the 14-sample proposal after the audit. Only the shared list, runner, test-data CI check, and dav2d consumer were submitted. The optional 34-sample printing fixes remain local.

- Test-data [!14](https://code.videolan.org/videolan/dav2d-test-data/-/merge_requests/14), source branch `EwoutH/dav2d-test-data:ci-avm-traces`, commit `17f5af92cc`.
- dav2d [!1140](https://code.videolan.org/videolan/dav2d/-/merge_requests/1140), source branch `EwoutH/dav2d:ci-avm-traces`, commit `86cb6220`. Draft until test-data !14 is merged: the ordinary job reads test-data main.
- The dav2d consumer's actual AVM job passes in fork [pipeline 753338](https://code.videolan.org/EwoutH/dav2d/-/pipelines/753338), [job 2987045](https://code.videolan.org/EwoutH/dav2d/-/jobs/2987045). Its separate validation branch only changes CI setup to fetch the pending test-data branch. All 14 exact comparisons and the original Meson tests pass.
- Test-data fork [pipeline 753339](https://code.videolan.org/EwoutH/dav2d-test-data/-/pipelines/753339) validates its new trace job and existing sample tests. All 11 jobs passed, including the new 14-sample trace job (50.07 s including builds), independent AVM MD5 verification, native/sanitizer and cross-architecture sample tests.

Both fork pipelines are green. Both final configurations passed GitLab CI lint. The existing unmodified local AVM build without 12-bit support also passes all 14 comparisons. No decoder/debug-print modifications or 12-bit configuration change are included in these MRs.

The submitted test-data implementation corrects three gaps in the original proposal: the new job needs explicit runner tags; its inherited JUnit report is disabled; the reference checkout is named `avm-src`, because the data repository already has an `avm` sample directory. The superseded first push pipeline 753336 was cancelled. The final job builds only the decoder CLI, with tests disabled in that separate build.

The exact submitted diffs are [submitted-testdata.patch](patches/submitted-testdata.patch) and [submitted-dav2d.patch](patches/submitted-dav2d.patch). They supersede proposal patches 02 and 01 for the submitted scope. The numbered patches and original measurements remain as audit evidence.

Follow-up after test-data !14 lands: run a normal pipeline on dav2d `ci-avm-traces`, then mark !1140 ready. No further approval is needed for that dependency check and readiness update within the approved 14-sample change.
