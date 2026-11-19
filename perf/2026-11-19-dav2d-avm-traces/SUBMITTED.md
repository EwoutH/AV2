# Submitted 14-sample changes

The owner approved the 14-sample proposal after the audit. The shared list, runner, test-data CI check, and dav2d consumer were submitted first. The owner then approved separate draft MRs for the small printing fixes, keeping sample-list expansion for later.

- Test-data [!14](https://code.videolan.org/videolan/dav2d-test-data/-/merge_requests/14), source branch `EwoutH/dav2d-test-data:ci-avm-traces`, commit `17f5af92cc`.
- dav2d [!1140](https://code.videolan.org/videolan/dav2d/-/merge_requests/1140), source branch `EwoutH/dav2d:ci-avm-traces`, commit `86cb6220`. Draft until test-data !14 is merged: the ordinary job reads test-data main.
- The dav2d consumer's actual AVM job passes in fork [pipeline 753338](https://code.videolan.org/EwoutH/dav2d/-/pipelines/753338), [job 2987045](https://code.videolan.org/EwoutH/dav2d/-/jobs/2987045). Its separate validation branch only changes CI setup to fetch the pending test-data branch. All 14 exact comparisons and the original Meson tests pass.
- Test-data fork [pipeline 753339](https://code.videolan.org/EwoutH/dav2d-test-data/-/pipelines/753339) validates its new trace job and existing sample tests. All 11 jobs passed, including the new 14-sample trace job (50.07 s including builds), independent AVM MD5 verification, native/sanitizer and cross-architecture sample tests.

Both fork pipelines are green. Both final configurations passed GitLab CI lint. The existing unmodified local AVM build without 12-bit support also passes all 14 comparisons. No decoder/debug-print modifications or 12-bit configuration change are included in these MRs.

The submitted test-data implementation corrects three gaps in the original proposal: the new job needs explicit runner tags; its inherited JUnit report is disabled; the reference checkout is named `avm-src`, because the data repository already has an `avm` sample directory. The superseded first push pipeline 753336 was cancelled. The final job builds only the decoder CLI, with tests disabled in that separate build.

The exact submitted diffs are [submitted-testdata.patch](patches/submitted-testdata.patch) and [submitted-dav2d.patch](patches/submitted-dav2d.patch). They supersede proposal patches 02 and 01 for the submitted scope. The numbered patches and original measurements remain as audit evidence.

Follow-up after test-data !14 lands: run a normal pipeline on dav2d `ci-avm-traces`, then mark !1140 ready. No further approval is needed for that dependency check and readiness update within the approved 14-sample change.

## Optional printing-fix drafts

Each MR is based directly on dav2d main and contains one printing issue. The six AVM changes extend dav2d's local reference patch series; nothing was submitted to the AVM project. None changes the shared list.

| MR | Printing issue |
| --- | --- |
| [!1141](https://code.videolan.org/videolan/dav2d/-/merge_requests/1141) | Palette dump placement and transform dimensions |
| [!1142](https://code.videolan.org/videolan/dav2d/-/merge_requests/1142) | Unmatched scaled-MC diagnostics |
| [!1143](https://code.videolan.org/videolan/dav2d/-/merge_requests/1143) | AVM color-description labels |
| [!1144](https://code.videolan.org/videolan/dav2d/-/merge_requests/1144) | AVM TIP output-picture selection |
| [!1145](https://code.videolan.org/videolan/dav2d/-/merge_requests/1145) | AVM inter-prediction spatial selection |
| [!1146](https://code.videolan.org/videolan/dav2d/-/merge_requests/1146) | AVM suffix metadata headers |
| [!1147](https://code.videolan.org/videolan/dav2d/-/merge_requests/1147) | AVM derived segment IDs |
| [!1148](https://code.videolan.org/videolan/dav2d/-/merge_requests/1148) | AVM absent chroma grain fields |

All eight individually preserve all 14 current comparisons in local checks. The combined split branches reproduce the previously audited source byte-for-byte and pass all 34 exact comparisons plus the ordinary Meson tests in [fork pipeline 753344](https://code.videolan.org/EwoutH/dav2d/-/pipelines/753344), [job 2987070](https://code.videolan.org/EwoutH/dav2d/-/jobs/2987070) (56.44 s including builds). Both decoders matched all 38 stored MD5s with that combined source in the original audit.

[Individual validation](data/printing-individual-validation.json), [MR/branch index](data/printing-mrs.json), and [combined CI evidence](data/printing-combined-ci.json) are retained. Draft branch push pipelines were skipped; one combined validation branch avoids launching eight full architecture matrices. Mark individual MRs ready only when choosing to advance them; a later list expansion should include only samples demonstrated compatible with the selected combination.
