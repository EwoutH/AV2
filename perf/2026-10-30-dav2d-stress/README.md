# dav2d stress test: random AVM encoder configs (29-30 Oct 2026)

Follow-up to the [29 Oct conformance update](../2026-10-29-dav2d-conformance-update/).
dav2d now matches nearly all of our AVM test streams, so this test looks for
what's still broken. It encodes small clips with random encoder tool settings
and compares dav2d's output with `avmdec`.

**Result:** 13 dav2d bugs, two of them with default encoder settings (F8,
F10). There are fixes for 11 of them. With all 11 applied, dav2d matches
`avmdec` on all 285 streams of the conformance corpus, with 1 thread and with
4 frame threads. Unpatched, it matches 284: the 285th,
`crowd_run_1080p50_qp110_s4_33f.ivf`, was taken for a truncated file but is
an F8 case.

## Setup

- **Encoder and reference decoder:** AVM `av2-enc`
  [`97e8004e4`](https://github.com/AOMediaCodec/avm/commit/97e8004e4)
  (`avmenc`, `avmdec`). The first 50 failing streams were also decoded with
  `av2-normative` `avmdec` 14f43e4cd, dav2d's target branch: identical
  output on all of them.
- **dav2d:** `main` 45609d91 +
  [!947](https://code.videolan.org/videolan/dav2d/-/merge_requests/947),
  MSVC (asm, C only with `--cpumask 0`, 4 frame threads) and GCC builds.
- **Clips:** 17 short clips from 16x16 to 640x360, 8- and 10-bit.
- **Configs:** 3,184 random sets of `avmenc` tool flags, presets and QPs.
  Each failure was minimised (fewer flags and frames, preset 9) and kept.
- **Root causes:** found by diffing dav2d's block-level debug trace
  (`DEBUG_BLOCK_INFO`, `DEBUG_B_PIXELS`) with an `av2-normative` build that
  carries dav2d's own debug patches, as in dav2d's CI
  ([`scripts/tracediff.py`](scripts/tracediff.py)).

## Failures

Of 3,184 configs, `avmenc` rejected 276, and unpatched dav2d failed on 478.
The 530 failures kept for analysis (including those where `avmdec` itself
fails), decoded with all 11 fixes:

| Bucket | Configs |
|---|---:|
| Fixed by the patches here | 282 |
| Features already tracked in dav2d #67 (S-frames, resize, LCR, ...) | 124 |
| AVM: `avmdec` rejects the encoder's own stream (32 of them with `--dpb-size` 2 or 4) | 52 |
| Not a bug: dav2d's CLI doesn't apply the crop window | 26 |
| Open, all builds (overlay, BRU, `rect-partitions=0`, lossless IntraBC chroma, ...) | 25 |
| Open, only with threads (mostly with tiles; 7 crash) | 21 |

## Bugs and fixes

| | Bug | Trigger | Fix |
|---|---|---|---|
| F1 | Lossless frames with 128x128 superblocks wrong with threads | `--lossless=1`, or low QP | [patch](patches/F1-lossless-chroma-split-in-parse-pass.patch) |
| F2a | CCSO/GDF unit size with 2+ tiles | `--tile-columns` | [patch](patches/F2a-ccso-gdf-unit-size-tile-boundaries.patch) |
| F2b | Loop-restoration unit rows with tile rows | `--tile-rows` | [patch](patches/F2b-lr-units-per-tile-row.patch) |
| F3 | Quantiser matrix applied to CCTX chroma IDTX blocks | `--enable-qm=1` | [patch](patches/F3-qm-ignore-cctx-bits.patch); reworked version as in !952: [F3b](patches/F3b-txtp-stx-cctx-rename.patch) |
| F4 | Deblocking at the cropped right edge (dav2d #78) | width not a multiple of 8 | [patch](patches/F4-deblock-crop-right-edge.patch) |
| F5 | Film grain in the last column of odd widths | `--film-grain-test`, width 97 | none (cause unknown) |
| F6 | GDF on small frames | `--gdf-unit-matches-sb=1` | fixed by F12 |
| F7 | Frame-threading hang with averaged CDFs | `--cdf-update-mode=0` | [patch](patches/F7-frame-threads-averaged-cdf-progress.patch) |
| F8 | Implicit MV refinement for a compound block with the same reference twice | **default settings**, `--cpu-used` 3/4, 8+ frames | [patch](patches/F8-refinemv-needs-nonzero-ref-distance.patch) |
| F9 | Optical flow on masked compound blocks | `--enable-opfl-refine=2` | [patch](patches/F9-opfl-only-for-compound-average.patch) |
| F10 | 10-bit qindex above 255 wraps to lossless | **default settings**, 10-bit, high QP | [patch](patches/F10-hbd-segment-qidx-overflow.patch) |
| F11 | `cdef_idx` context for units with only skipped blocks | `--enable-cdef-on-skip-txfm=0` | [patch](patches/F11-cdef-ctx-skipped-units.patch) |
| F12 | GDF block-flag bit counted per tile | small frames with tiles | [patch](patches/F12-gdf-flag-bit-units-per-tile.patch) (after F2a) |
| F13 | Tile-thread crash in the `load_tmvs` row copy (found 30 Oct, after the run) | `--tile-columns=2`, tile threads | [patch](patches/F13-tmv-row-copy-narrow-tile.patch) |

The patches are against dav2d `main` 45609d91 + !947. Each applies on its
own, except F12, which goes after F2a. F3b is against `main` 864281f0.
[`night1030-all.patch`](patches/night1030-all.patch) has all 11. Causes,
open cases and the exact `avmenc` commands are in [FINDINGS.md](FINDINGS.md).
Repro streams for each bug and for the open cases are in [repro/](repro/).

## Upstream status (30 Oct, evening)

- Merged: F9 (!953), F10 (!955, issue #81), F13 (!954).
- Open MRs: F8 (!951), F3 (!952, reworked after review into a
  `txtp_stx_cctx` rename). F7 and the tile-thread CDF averaging are covered
  by rbultje's !948. F4 is dav2d #78 (Kyle).
- Reported as an issue: the tile-thread race with 2 tile columns + TIP
  (dav2d #82, open).
- Not sent yet: F1, F2a, F2b, F11, F12, F5 (cause unknown).

## Files

- [`FINDINGS.md`](FINDINGS.md): the full analysis, written during the run.
- [`patches/`](patches/), [`repro/`](repro/): fixes and repro streams.
- [`data/`](data/): `results.jsonl` and `results_p.jsonl` (one row per
  config, from the two parallel runs), `classify.json` and
  `classify_final.txt` (the buckets above), `verify_normative.json`.
- [`scripts/`](scripts/): `stress.py` (encode, decode, minimise),
  `classify.py`, `verify_normative.py`, `tracediff.py`. They expect the
  local build layout under `samples/av2_work/`. The minimised failure
  streams (`c000xxx`, `p000xxx` in `FINDINGS.md`) are not included (97 MB).
