# dav2d stress test findings (night of 29-30 Oct)

## Summary (07:30)

- 3184 random avmenc configs (2 runs, 00:49-07:21): 2378 all decoders
  match, 276 configs avmenc rejected, 52 where avmdec itself fails
  (32 of them with AVM `--dpb-size` 2 or 4), 478 where unpatched dav2d failed.
- Final classification of the 530 kept failures with dav2d main + !947 +
  the 11 patches here (MSVC build, `classify_final.txt`): 282 fixed, 124
  known upstream (#67 features), 52 AVM, 26 crop window (not a bug), 25
  open on the C path (overlay, BRU, rect-partitions, lossless IntraBC
  chroma, multi-flag ones), 21 threads-only (mostly with tiles; 7 crash
  with 4 frame threads; not looked at).
- Fixes (patches/): F1 lossless + threads, F2a CCSO/GDF unit size with
  tiles, F2b LR unit rows per tile, F3 QM + CCTX, F4 deblock right edge
  (#78), F7 frame-threading hang, F8 refine-MV with distance-0 refs
  (default settings; also the "truncated" crowd_run stream), F9 opfl only
  for COMPOUND_AVERAGE, F10 10-bit qindex >= 256 (default settings), F11
  cdef_idx context for skipped units, F12 GDF flag bit per tile (also F6).
- 29 Oct conformance corpus with all 11: 285/285 at 1 thread and at 4
  frame threads (unpatched: 284/285).

Setup: avmenc av2-enc 97e8004e4 (random tool configs, small clips),
reference avmdec from the same build. The first 50 failing streams (01:45)
were also decoded with av2-normative avmdec 14f43e4cd (dav2d's target):
identical output on all of them, and the trace diffs for F8-F12 use an
av2-normative build. dav2d = main 45609d91 + !947 (MSVC and GCC builds).

## F1 (fix ready): lossless frames + 128x128 SB, threads >= 2: wrong from SB row 2 down

- Repro: `repro/F1_lossless_threads.ivf` (fourpeople 480x270, 1 frame,
  `--lossless=1 --cpu-used=9`). `dav2d --threads 1` matches avmdec;
  `--threads 2 --framedelay 1` (and 3/4/8, frame threading too) gives a
  different, deterministic output. Diff starts at y=128 (Y), y=64 (UV) and
  covers everything below.
- `--sb-size=64` decodes fine with threads. Clips under 128 px tall are fine.
- Also triggered by low --qp: the encoder codes the keyframe at qindex 0
  (lossless) for --qp <= ~45.
- Same on dav2d nightly fdc99363 and dfbd7ac, MSVC and GCC: not new.
- Cause: for blocks larger than 64x64, `recon_b` (recon_tmpl.c) splits into
  64x64 quadrants and, in lossless segments, codes chroma with *every*
  quadrant (`csplit[...][0]`, `il`). `dav2d_read_coef_blocks()` (the parse
  pass, only used with threads) lacks that lossless case: it reads chroma
  only with the first quadrant (`csplit[...][ss_hor + ss_ver]`), so the
  coefficients go out of step. Fix: mirror the `il` logic
  (`patches/F1-lossless-chroma-split-in-parse-pass.patch`). F1 repro,
  c000016, c000017, c000031: correct with 1, 2 and 4 frame threads.

## F8 (fix ready): default settings, parse desync from implicit MV refinement

- `repro/F8_default_s4_8bit_fourpeople.ivf` (8-bit fourpeople 480x270, **no
  tool flags**, `--qp=56 --cpu-used=4 --limit=8`), also the 10-bit
  322x182 repro, c000403 (s3, defaults), c000015, c000050, c000000, c000350.
- The first temporal unit holds the keyframe plus a hidden alt-ref. In the
  alt-ref, an 8x32 NEARMV_NEARMV compound block uses the same reference
  (the keyframe) twice. dav2d's `refdist` for it is 0, so the refine-MV
  condition `refdist[r0] == -refdist[r1]` holds (0 == -0). dav2d sets
  implicit `refine_mv = 2` and skips the subpel filter symbol. AVM
  (`is_refinemv_allowed_reference()`) needs the references on opposite
  sides (`(d0 <= 0) ^ (d1 <= 0)`), rejects it, and reads the filter. From
  there dav2d is out of sync. Found by diffing dav2d's block trace against
  an AVM av2-normative build with dav2d's `patches/` (as in test-debian-avm),
  built with MinGW GCC in `av2_work/avmdbg1030/`.
- Symptoms: the decode error (`decode_coefs()` INT_MIN) is swallowed: the
  output frame is mostly zeros, with samples out of range, and the exit
  code is 0. The keyframe itself parses fine.
- Fix: also require `refdist[r0] != 0` (decode.c, refine_mv condition).
  `patches/F8-refinemv-needs-nonzero-ref-distance.patch`. All F8 streams
  above are correct with 1 thread and 4 frame threads.
- Separate small issue: the swallowed error (frame output plus exit 0).
- Also explains `crowd_run_1080p50_qp110_s4_33f.ivf` (29 Oct corpus), which
  was excluded as "truncated". It isn't: 18 IVF packets, 33 frames (hidden
  frames share packets), and the IVF header says 33. Unpatched dav2d
  mismatches; with F8 it matches avmdec. Corpus with all fixes: 285/285,
  1 thread and 4 frame threads.

## Open, narrowed down: MV candidate weights (overlay, rect-partitions=0)

Block-trace diff against AVM (as for F8) puts the first difference in
`find_mv_refs` in both cases: the same candidates, but a weight that's 1
higher in dav2d.
- c000032 (`--enable-overlay=1`, `repro/C_overlay_ocean_256x144.ivf`):
  the parse matches to the end of the stream; the first difference is
  `mv[0/1] ... w=6` (AVM) vs `w=7` (dav2d), 64x64 block at y=16 x=0 in the
  overlay frame. The overlay references its own alt-ref at distance 0
  (compare F8).
- c000041 (`--enable-rect-partitions=0`,
  `repro/C_rect_partitions0_wikipedia.ivf`), single-ref WARPMV 64x64 block
  at 4x4 (y=32, x=96) = pixel (128, 384), the top-left 64x64 of its
  128x128 SB. AVM's list: [ (0,0) w8 left y_off=15 | (-2,0) w1 left
  y_off=0 | (-1,0) w1 left y_off=16 (bottom-left, in the already decoded
  SB to the left) | ... ]. dav2d's has no (-1,0) candidate, and (0,0) has
  w9: for the bottom-left position it reads a block with MV (0,0) and
  merges it into candidate 0. dav2d's lookup (refmvs.c "bottom-left",
  `rt->r[((by4 + bh4) & 63) * 128 + bx4 - 1]` = 4x4 row 48, col 95) is the
  same position AVM uses, so the *stored* MV there differs: AVM (-1,0),
  dav2d (0,0). Unverified guess: the block there uses warped motion, and
  AVM stores per-subblock (warp-derived) MVs for refmvs where dav2d stores
  one MV. The parse stays in sync, so only the prediction differs.
- Pixel-level trace (both decoders with `DEBUG_B_PIXELS`), c000032: the
  first wrong pixels are the luma prediction of the 64x64 TIP block at
  y=0 x=16 of the overlay frame (`ref 7` = TIP, tip_mode 13, MV 0). Its
  first row differs from x=32. So it's the TIP frame / TIP prediction when
  the overlay's references include its alt-ref at distance 0. Requiring
  refdist != 0 in the two TIP refine checks (like F8) did *not* fix it
  (reverted).
- Caveat: only the final candidate list is printed, and for c000032 there's
  a single candidate, so the weight difference may be harmless. The parse
  matches to the end, and the wrong pixels (frame 5, x 65-127, y 0-63) are
  not at that block. Next step: the pixel-level trace (`DEBUG_B_PIXELS` in
  both builds) to find the first wrong block, then compare weight
  increments in dav2d refmvs.c with AVM mvref_common.c.

## F10 (fix ready): 10-bit qindex >= 256 taken as lossless (default settings)

- `repro/F10_default_10bit_qidx256_sparks.ivf` (sparks10 480x270, **no tool
  flags**, `--qp=222 --cpu-used=9 --limit=16`): dav2d "Error decoding
  frame: Invalid argument".
- The keyframe's `base_q_idx` is 256, which is valid for 10-bit (AVM max
  255 + 48). dav2d stores `segmentation.qidx[]` as `uint8_t` (public
  headers.h), so it wraps to 0: the frame is treated as all-lossless, and
  TCQ, deblock, GDF, CDEF, LR and CCSO aren't parsed. The frame header diverges at
  `post-tcq_parity`. Also `iclip_u8()` clamps segment qindex to 255; AVM
  (`av2_get_qindex()`) clamps to 255 / 303 / 351 for 8 / 10 / 12-bit.
- Fix: `uint16_t qidx[]` and clamp to `255 + 48 * hbd`
  (`patches/F10-hbd-segment-qidx-overflow.patch`; changes a public struct).
  p000469 then decodes correctly (1 thread, 4 frame threads). Any 10/12-bit
  stream with a high QP can hit this.

## F11 (fix ready): cdef_idx context with `--enable-cdef-on-skip-txfm=0`

- `repro/F11_cdef_on_skip_txfm0_fourpeople.ivf` (fourpeople 480x270, 3 f,
  `--qp=74 --cpu-used=9 --enable-cdef-on-skip-txfm=0`); also c000937,
  c001076. The first trace difference is `Post-cdef_idx[ctx=1]` (AVM) vs
  `ctx=2` (dav2d) in frame 1.
- AVM (`read_cdef()`): when a skipped block is the first in a 64x64 CDEF
  unit and cdef_on_skip_txfm is off, it sets `cdef_strength = -1` on the
  unit's top-left block. `av2_get_cdef_context()` then counts that unit as
  an *available* neighbour that isn't index 0. dav2d keeps -1 ("unset")
  for such units, and its context code reads -1 as "not available".
- Fix: mark these units -2 (seen, not coded, splat over the block like a
  coded index); code the index when the unit is `< 0`; read -2 as
  available, non-zero in the context; `cdef_idx < 0` = no CDEF in
  cdef_apply. `patches/F11-cdef-ctx-skipped-units.patch`. Fixes all three
  (1 thread and 4 frame threads).
- dav2d's own FIXME next to it (ctx 3 vs 2 when both edges come from the
  same coded block) is still open; AVM's rule is in
  `av2_get_cdef_context()` ("same superblock" branch).

## F12 (fix ready, on top of F2a): GDF per-block flag bit with small frames / tiles

- `repro/F12_gdf_tilecols_97x65.ivf` (fourpeople 97x65, 1 keyframe,
  `--qp=135 --cpu-used=9 --tile-columns=2`). Also fixes F6
  (`--gdf-unit-matches-sb=1` on 97x65), c000334, c000867 (crash), c000461.
- AVM `setup_gdf()` reads the second GDF mode bit when `gdf_block_num > 1`,
  where `init_gdf()` counts GDF units *per tile* with the real unit size
  (64 px with sb64 + gdf_unit_matches_sb, or after the tile-parity rule).
  dav2d reads it when `max(w, h) > 128` (256 for sb256). The frame
  header then shifts by one bit.
- Fix: compute `gdf.b64size` first, then count units per tile like AVM.
  `patches/F12-gdf-flag-bit-units-per-tile.patch` (applies after F2a).

## Open, cause known: chroma tx type of lossless inter/IntraBC blocks

- `repro/C_lossless_intrabc_chroma_txtp_slides.ivf` (slides 480x270, 2 f,
  `--qp=19 --cpu-used=6 --enable-sdp=0 --enable-global-motion=1`; the
  keyframe is lossless, global motion is incidental). First difference:
  a lossless IntraBC 32x16 block, chroma `Post-txtp[wht/wht]` (AVM) vs
  `identity/identity` (dav2d).
- AVM `av2_get_tx_type()` (blockd.h), lossless + inter-like + UV + luma tx
  4x4: start from `tx_type_map[0]`, but if `region_type != INTRA_REGION`
  and the block is its own chroma base, use the *co-located* luma 4x4:
  `tx_type_map[(blk_row << ss_y) * stride + (blk_col << ss_x)]`. dav2d
  (recon_tmpl.c ~3645) takes the luma type at the block's top-left
  (`txtp_map[(by & 15) * 16 + (bx & 15)]`) for every chroma tx block.
  A quick attempt (co-located luma type in both chroma loops when lossless,
  luma 4x4, `!t->intra_region`) did NOT fix the repro and broke
  c000017's full stream, so it was reverted. The AVM condition (chroma base,
  `region_type`, IntraBC counted as inter) needs a closer look.

## Open: threads-only failures (21, after all fixes)

Mostly configs with `--tile-columns`/`--tile-rows`; 7 crash with
`--threads 4 --framedelay 4`, the rest mismatch. Examples: p000470
(`--enable-pc-wiener=0 --tile-columns`, 3 f), c000366 (crash,
`--enable-global-motion --enable-inter-ist --tile-columns`). List in
`classify.json` (bucket "threads only").

## Not implemented in dav2d: BRU

`--enable-bru=1/2` (c000000 with gf-max-pyr-height 0 was F8; c000396 with
lag 0 is this): the frame headers diverge at `post-refmvbits` (AVM at bit
21, dav2d at 20). dav2d's parser has `// FIXME bru` right before it, so the
BRU header syntax isn't parsed yet. Report only if not already tracked.

## Already known upstream (dav2d #67, juliobbv; skip when reporting)

S-frames unsupported (`--enable-sframe`), `--global-error-resilient` (fails at
an S-frame), `--resize-mode 2` (linked to SVC draft !950), `--cdf-update-mode
2` (!948), `--enable-lcr`, `--enable-operating-point-sets`, `--timing-info`.
Our resize-mode 1/3 crashes may be the same area as resize-mode 2; check
against !950 before reporting.

## Candidate new findings (C path, all dav2d builds; minimised flags)

- **F2a (fix ready)** CCSO and GDF unit size with tiles. AVM
  (`get_ccso_unit_size_log2_adaptive_tile()`, `gdf.c`) picks the unit size
  from the parity of the *sizes* of all tiles but the last
  (`col_start_sb[i+1] - col_start_sb[i]`, i < cols-1). dav2d (obu.c, two
  places) ORs `col_start_sb[t]` for t < cols-1, i.e. the tile *starts*
  incl. start 0 and without the last inner boundary. With 2 tile columns it
  never sees the boundary: e.g. 322x182, sb64, tiles 3+3 SBs -> AVM uses
  64 px CCSO units, dav2d 256. Fix: loop t = 1 .. cols-1 (starts are prefix
  sums of the sizes, so the parity bits match).
  `patches/F2a-ccso-gdf-unit-size-tile-boundaries.patch`. Repro
  `repro/F2_tilecols1_322x182.ivf` (1 keyframe, 1763 B, `--qp=165
  --cpu-used=9 --tile-columns=1`); passes with `--enable-ccso=0`.
- **F2b (fix ready)** LR units with tile rows. `read_sb_restoration()`
  lays units out per tile (tile-relative position, short last unit merged
  only inside the tile), but `lr_sbrow()` aligns unit rows to the frame and
  merges against the frame height. 640x182, sb128, `--tile-rows=1`: tile
  row 2 is 54 px (< half a 128 px unit), so dav2d uses the unit above it:
  luma rows 128-179 wrong. Fix: find the SB row's tile row, align to its
  top, merge only inside it against its bottom.
  `patches/F2b-lr-units-per-tile-row.patch`. Not checked: the same per-tile
  rule for columns (lr_sbrow aligns `next_x & ~(unit-1)` to the frame and
  compares with the frame width).
- With F2a+F2b: 64/64 tile configs (4 sizes x sb64/128 x 4 tilings, C and
  asm) match; c000067, c000215, c000224 fixed. c000191 was F4.
- **F4 (fix ready) = dav2d #78** "deblock fixes up bottom edge but not
  right edge" (Kyle: "I don't think we have any samples that trigger
  this"). c000191 is one: drivingpov10 322x182 (coded width 328), 8 frames,
  `--qp=237 --cpu-used=5 --tile-columns=1`; frame 0 luma wrong at
  x 307-321, y 129-181; passes with `--enable-deblocking=0`. Fix: the same
  crop as the bottom one, for the vertical-edge masks of luma column
  `bw - 2` in `dav2d_deblock_slice_cols()`
  (`patches/F4-deblock-crop-right-edge.patch`); fixes c000191 (C, asm).
  Repro `repro/F4_deblock_right_edge_322x182_10bit.ivf`.
- **F3 (fix ready)** `--enable-qm 1` alone: inter frames, only chroma
  (same pixels in U and V, |diff| <= 4); passes with `--enable-cctx=0` and
  at high QP (flat QM level). Cause: `decode_coefs()` picks `qm_tbl` by
  comparing `*txtp == IDTX` / `WHT_WHT`, but for plane 1 the CCTX type has
  already been OR-ed into bits 8+ of `*txtp`, so chroma IDTX blocks with
  CCTX get the QM applied. Fix: compare `*txtp & 0xff`
  (`patches/F3-qm-ignore-cctx-bits.patch`). Fixes c000136 and every QM test
  stream (C and asm). Repro `repro/F3_qm_cctx_parkjoy.ivf`. Needs a
  regression run on the sample corpus before sending.
  c000067 (`--tile-columns 1 --enable-qm 1`) still fails with the fix: F2.
  Sent as !952. After review (rbultje, IRC), reworked: the output is renamed
  to `*txtp_stx_cctx`, `decode_coefs()` uses a local `txtp` with only the
  transform type, and stx/cctx are packed into the output once at the end
  (`patches/F3b-txtp-stx-cctx-rename.patch`, on `main` 864281f0). Compared
  with the mask version on 362 of 937 streams before the session ended
  (C, asm, 4 frame threads): identical on all 10 AVM vectors and the first
  85 corpus streams (the smaller ones) in every mode, and at 1 thread on 249
  of 257 stress streams. The other 8, and all the frame-thread differences,
  are on streams already broken on `main` whose output changes from run to
  run with either version. F3 repro matches avmdec in all modes.
- `--enable-overlay 1` alone: ocean 256x144, frame 5 (c000032, c000118).
- `--enable-rect-partitions 0` alone: wikipedia 640x360, frame 2 (c000041).
- `--reduced-tx-part-set 1` alone: drivingpov10, s3, frame 0 (c000015).
- `--enable-bru 2 --gf-max-pyr-height 0`: sparks10, qp 0, s4 (c000000).
- `--enable-idtx-intra 0 --enable-chroma-deltaq 1`: bayshore qp 35 s4 (c000050).
- **F7 (fix ready)** frame threading hangs (`--threads 2 --framedelay 2`
  or more; framedelay 1 is fine) with `--cdf-update-mode=0` or `2`:
  `repro/F7_hang_cdf_update_mode0_parkjoy.ivf` (parkjoy 208x120, 6 f,
  `--qp=150 --cpu-used=9 --cdf-update-mode=0`). Also c000017, c000047.
  Cause: with averaged primary/secondary CDFs (`use_pri_sec_cdf`), `in_cdf`
  is a new buffer with its own progress counter; with disable_cdf_update it
  becomes `c->cdf[i]` for the refreshed slots, but only `out_cdf.progress`
  is ever set, so a later frame waits on it forever. Fix: set
  `in_cdf.progress` after `dav2d_decode_frame_init_cdf()` in thread_task.c
  (`patches/F7-frame-threads-averaged-cdf-progress.patch`). Repro now
  decodes correctly with 4 frame threads; c000017's remaining threaded
  mismatch is F1 (lossless).

## Newer candidates (after 03:00)

- **F5** film grain, odd width: `repro/F5_filmgrain_odd_width_97x65.ivf`
  (fourpeople 97x65, 3 f, `--qp=10 --cpu-used=9 --film-grain-test=7`;
  key Q0 then inter Q10). Without grain (`--filmgrain 0` vs avmdec
  `--skip-film-grain`) it matches; with grain 3 luma pixels differ in the
  last column (x=96, y 40-64, frame 1), C and asm. 97 = 3x32 + 1, so the
  last grain block is 1 px wide. Not seen at qp100 or on even widths.
  (The earlier "t4 OK" was F1 hiding it: lossless keyframe.)
- **F6 (fixed by F12)** `--gdf-unit-matches-sb=1` on 97x65 with 64x64 SBs:
  `repro/F6_gdf_unit_matches_sb_97x65.ivf` (1 frame, `--qp=145
  --cpu-used=9`) decodes but mismatches; the 10-frame stream gives "No data
  decoded". OK with `--enable-gdf=0`, with `--sb-size=128`, and on
  480x270/208x120. Frame 97x65 = 2x2 SBs with a 33 px last column and a
  1 px last row; AVM counts GDF units as `1 + (size-1)/unit` per tile (no
  merging). Not root-caused.
- Not a decode bug: `--enable-cropping-window 1 --crop-win-*` (c000428).
  dav2d parses the crop window (obu.c) but the CLI outputs the full coded
  frame (270x556 vs avmdec's 270x554); the cropped region is identical.
  At most a CLI feature request (apply the crop when writing y4m/yuv/md5).
  The stress run counts these as mismatches.

## AVM (encoder/decoder) findings

- **A1** `--dpb-size 2` alone (c000389, slides 480x270, s6, qp185, 10 f):
  avmdec fails "Corrupt frame detected / Failed to decode tile data" at
  frame 2. Also `--dpb-size 4` (c000419, "Invalid value for chroma intra
  mode index" at frame 8), c000260. avmenc writes streams its own decoder
  rejects when the DPB is smaller than the default 8.
- **A2** avmenc `--enable-overlay=1` on a 16x16 clip: "The same superblock
  is recoded twice. Infinite loop detected?" (encoder error exit).

## Follow-up 30 Oct: the threads-only failures (all on plain `main` too)

All 21 fail with tile threads alone (`--threads 4 --framedelay 1`) and all
use 2+ tile columns or rows. Unpatched `main` (+ !947) fails the same way.
Three causes:

- **F13 (fix ready), crash:** default settings + `--tile-columns=2`:
  `repro/F13_tile_threads_4cols_fourpeople.ivf` (fourpeople 480x270, 2
  frames, `--qp=110 --cpu-used=9 --tile-columns=2`; avmdec MD5
  `046ac01dff6a4be57db84d5313a9538e`). Segfaults with 2-8 tile threads,
  every run; 1 thread and frame threading are fine. In
  `dav2d_refmvs_load_tmvs()` (tile-threading path, `!have_frame_threading`)
  the copy of the previous SB row's last two rows is split into head /
  32-aligned middle / tail. For a tile that starts and ends inside one
  32-wide group (last tile: 8x8 columns 48-60), the head covers it all and
  the middle width is 32 - 60 = -28: `if (w)` passes and memcpy gets a huge
  size. Fix: `if (w > 0)` (`patches/F13-tmv-row-copy-narrow-tile.patch`).
  Never happens at 1080p with 4 tile columns (tiles start at multiples of
  256 px), so the corpus didn't hit it. With F13, the F13 repro and the
  other small repros match in all thread modes on plain `main`.
- **Tile-thread CDF averaging (fixed by !948):** the tile-thread path in
  thread_task.c still averages over `1 << (log2_cols + log2_rows)` tiles;
  a6d97bd6 fixed only the single-thread path (real tile count, shift capped
  at 3). With fewer tiles than that power of two (narrow frames), it reads
  tile CDFs that don't exist: msac asserts `count <= 32` / `u <= s->rng`
  (c000366, c000766, p000256). !948 replaces both with
  `dav2d_decode_frame_update_cdf()`, which fixes it. Tested locally by
  porting the a6d97bd6 logic to thread_task.c: with that + F13 + the 11
  patches, 19 of the 21 match in every thread mode.
- **Open, reported as dav2d #82: tile-thread race with 2 tile columns +
  TIP:** `repro/C_tile_threads_2cols_tip_fourpeople.ivf` (avmdec MD5
  `e86051bbee686d3518a842cbd1feac59`). Encoded with `avmenc
  FourPeople_480x270_60.y4m --ivf --limit=3 --end-usage=q --qp=110
  --cpu-used=9 --tile-columns=1` (av2-enc 97e8004e4; re-encoding gives a
  byte-identical file). A race, not a fixed mismatch: on plain `main`
  864281f0, 20 runs each, 1 thread 20/20 correct, frame threads
  (framedelay 2 or 4) 20/20, tile threads (framedelay 1) 2t 1/20, 4t 0/20,
  8t 5/20, 4t C-only 9/20, with several different MD5s. Only frame 2 is
  wrong, luma only, x 64-96, y 127-136 (|diff| <= 16): the SB row edge at
  y=128 in the left tile, not the tile column edge at x=256, so the earlier
  guess (TIP hole filling / smoothing reading across the tile column edge)
  looks wrong. Correct with tile threads when encoded with
  `--enable-tip=0`, `--enable-ref-frame-mvs=0`, 1 tile column,
  `--tile-rows=1` instead of columns, 2 frames or 5 frames. (`--sb-size=64`
  is not a workaround: that stream is already wrong at 1 thread on plain
  `main`, from an unmerged bug.)
- Still open: c001493, p001355 (both `--disable-kf`,
  `--enable-ref-frame-mvs=0`; mismatch, no crash).
