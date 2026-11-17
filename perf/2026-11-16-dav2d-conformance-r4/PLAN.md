# dav2d conformance round 4 (16-17 Nov 2026)

## Starting point

- dav2d main is now 28e39df9. Since round 3, upstream merged ten of our MRs (!1074, !1077, !1079-!1085 and !1081) plus rbultje's same-POC refmvs fix (54856741) and his CLK POC/flush fix (28e39df9, which came out of the #91 report). !1088 is closed (system_v is fixing the CfL asm instead), and !1073 and !1078 are still open.
- Known feature gaps, all tracked elsewhere and left out of this round: RAS (`--sframe-type=1`; prototype `wip/ras-proto`, design on !1073), BRU, bridge frames, `--resize-mode 2/3`, TIP explicit QP (`FIXME yac` in obu.c), per-segment QM (`FIXME` in obu.c), lossless masked compound (round-3 open item; #99 from Peter de Rivaz is a related lossless IDTX bug), multi-xlayer streams (#93, urvang).
- Round 3 (5236 random configs, round-3 combo build) only used 4:2:0 sources, 8/10-bit, constant-q `.ivf`, the source sizes as they are, and plain C/asm decoders without sanitizers.

## What round 4 adds

1. **Baseline on fresh main**: the reduced regression corpus (non-hd, 1t/mt4/C) plus every round-3 failure stream (`fail/`, `fail_main/`, `tri/`, `rr/w/`, `triage/r/`, `mr/`, `clk-poc/`), and the private SVT-AV2 low-res set. This shows what still fails after the merges and whether something regressed.
2. **Memory errors**: the same corpus with an ASan+UBSan C build (UBSan fatal).
3. **New stress axes** (`stress4.py`, reference avmdec from AVM av2-enc 487d0761):
   - 4:2:2 and 4:4:4 sources (6 clips each, made from the 4:2:0 clips by nearest chroma upsampling; `tools/y4mfmt.py`), about 40% of configs
   - 12-bit coding (`--bit-depth=12`, 8/10-bit input), 15%
   - random crops of the sources: tiny (1-24 px) and odd sizes, 15%
   - rate control: cbr, vbr (also 2-pass), cq, `--rt`, 30%
   - sequence cropping window, 8% (dav2d exports it but its CLI does not apply it, so the script crops dav2d's y4m output itself)
   - still-picture header, `.obu` (section 5) output, denoiser film grain, colour metadata, chroma sample position, banding/short metadata, operating point sets, monotonic output order, loop filters off across tiles, min/max QP and GF settings
   - decoders per stream: asm 1t, C+ASan+UBSan 1t, asm with a random thread count (2/3/4/6) and frame delay
4. **Triage in the morning** (`triage4.py`): checks the reference against the av2-normative avmdec, reruns threaded failures 3x for flakiness, decodes each failure with the 13 Nov main build to tell new failures from old ones, buckets the failures by pattern (C+asm = parse/C, asm-only, threading-only, sanitizer) and format, and greedily reduces one stream per bucket.

## Schedule (pc, 4 cores, 3 workers, Nice 19; started 16 Nov evening with the owner's go-ahead)

| Phase | Time | What |
| --- | --- | --- |
| prep (done) | | builds: AVM 487d0761, dav2d main release/C/ASan+UBSan C/ASan asm; 4:2:2/4:4:4 sources; 9-config smoke test |
| baseline | ~2 h | `base_main`, `base_svt`, `base_asan` |
| stress | until 06:45 | stress4, 3 workers (round 3 did about 1200 configs per hour; the ASan decoder and 4:4:4 frames are slower, so expect 4000-6000) |
| triage | 06:45-09:30 | triage4 + reductions |

The scripts (`build.sh`, `run.sh`, `run2.sh`, `stress4.py`, `triage4.py`, `tools/y4mfmt.py`) and all output are in `/srv/compression/cache/av2conf/round4/` (`run.log` for progress, `summary.md` at the end). Units `av2-r4` (first run), `av2-r4b` (restart, see below).

## Restart (16 Nov 21:34)

The first run (unit `av2-r4`) finished the baseline in 16 minutes, but stress4 died after 18 configs: the unit inherited a nix dev shell PATH, so `python` was a bare Python 3.14 without numpy, and every crop config (`tools/y4mfmt.py`) killed its worker thread. `run.sh` still ran triage and wrote `run.done`. Attempt 1 is kept in `round4/attempt1/`.

Changes before the restart (unit `av2-r4b`, `run2.sh`, baseline not repeated):

- **Robustness**: absolute `ds` python path; each config runs in a try/except (worker gives up after 10 errors in a row, tracebacks in `worker_errors.log`); a preflight runs `y4mfmt.py` once and checks the decoder paths before the workers start; `run2.sh` writes `run.FAILED` if stress produced fewer than 500 configs.
- **Decoder = main 28e39df9 + !1018** (rbultje's draft CfL padding fix for #86). !1081 is merged without a CfL fix, so main's asm now crashes or mismatches on #86 streams; on IRC BBB (rbultje) suggested testing with !1018 applied, as he does. Checked: checkasm 3 seeds all 2473 pass; SVT low-res set 660/660 (main 650/660, the 10 failures are all #86: 4 crashes, 6 mismatches); corpus 1t 305/305 identical MD5 to main; the C assert `wpad * 4 < w / 2` that fired on `clk-poc/bay210_x2.ivf` in the ASan baseline is gone. Builds `round4/build/main-1018`, `main-1018-asan` (worktree `src/wt-x81-1018`).
- **4:2:2 down from 25% to 10%** (4:2:0 85%, 4:4:4 5%): the only 4:2:2 failure of attempt 1 (v000019, testsrc10 130x74 10-bit) has the #101 pattern: luma exact in all frames, frames 0-2 exact, then a small chroma patch (rows 46-53, columns 46-57) on frames 3-5.
- **Triage labels**: a mismatch with exact luma, exact frame 0 and differing chroma on a 4:2:2/4:4:4 stream goes to "known: #101-like" and is not reduced (checked: `i444/r444_ld.ivf` and v000019 are classified as #101-like, `tri/s2` is not). Sanitizer hits on `--enable-fwd-kf` configs go to a separate bucket that is reduced last: all 9 UBSan hits in the baseline (`recon_tmpl.c:2388/2443/2553`) are OLK/fwd-kf/S-frame streams (OLK reference handling is missing on main, `fix-olk-ref-reset` not upstream).
- Stress until 06:45, triage until 09:30, as planned.

## Baseline results (main 28e39df9, 16 Nov)

- Corpus: of the 261 stream/mode results also in round 3's main run, none went from ok to failing; 51 now pass. The 102 round-3 failure streams outside that set that still fail in 1t also failed on 13 Nov main (89 with the same MD5, 13 different but still wrong: `rr/w` restricted switch, `fkf_*`, `u2816`, `tri/s2`, `u001694`, `u004952`, `u005105`). The `mr/` failures are open MR repros.
- SVT low-res set: 77 streams fixed since 13 Nov main, none regressed; the 10 left are #86 (see above).
- ASan+UBSan: 198/305; sanitizer hits only on OLK/fwd-kf streams (UBSan) and the #86 C assert.

## Neon on the pi (at most 2 threads)

The pc only checks x86 asm and C, while a lot of AArch64 Neon code is landing in dav2d right now (!943, !1013, !1056, !1057, ...). dav2d main 28e39df9 is cross-built static for the pi (Cortex-A72): Neon, C only, checkasm.

1. checkasm with 3 seeds: done 16 Nov 20:46, all 1596 tests pass.
2. The pc baseline corpus (305 streams: non-hd corpus + round-3 failure streams) in Neon 1t, C 1t (2 streams at a time) and Neon with 2 threads/framedelay 2 (one at a time). Each result is compared with the reference and with pc main in the same mode, so Neon-only differences stand out. Done 16 Nov ~21:00: Neon 1t and C 1t give the same MD5 as pc main on all 305 streams (203 match the reference; the 102 others are known round-3 failures that fail the same way on the pc). Neon with 2 threads differs from pc main on 2 streams, both film grain on odd widths (#96, run-to-run nondeterminism on the pc too; u005105 gets an odd width from `--resize-mode=2`). No Neon-specific problem found.
3. Morning: stress4 now keeps its passing streams (`round4/keep/`); decode them on the pi the same way (`pi/mkkeep.py`, then `pidec.py`).

Files: `round4/pi/` on the pc, `~/av2conf-r4/` on the pi (`run_pi.log`, `checkasm_*.log`, `corpus.jsonl`, `pi.done`).

## 4:4:4 inter chroma bug (found during planning, posted as dav2d #101)

- 4:4:4 inter frames decode with wrong chroma in small areas; key frames and luma match. It is not new: every dav2d build fails (main 28e39df9 asm and C, 13 Nov main, the old bench build), with streams from both avmenc versions. avmdec 487d0761 and av2-normative agree. (The smoke-test impression that only the new encoder triggers it was luck on one stream.)
- Rate on 4-frame encodes of 4 clips (3 QPs, cpu-used 6/9, both encoders, inter-intra on/off): 4:4:4 40/96 mismatch, 4:2:2 4/96 (testsrc only), 4:2:0 0/96. Single encoder tool toggles only move the mismatch around.
- Public 2-frame repro: `i444/r444_ld.ivf` (testsrc 4:4:4, `--limit=2 --lag-in-frames=0 --end-usage=q --qp=80 --cpu-used=9`), frame 1 V differs at x 116-119, y 14-23. Posted with that repro as dav2d #101 (cause unknown).
- Effect on the run: the 4:4:4 share in stress4 is lowered from 20% to 5% so this one bug doesn't flood the triage; 4:2:2 went from 25% to 10% at the restart.
- Next step for the bug: block traces of frame 1 in both decoders (frame-1 trace builds are ready: `round4/build/dbg1`, `round4/build/avm-dbg1`).
- Solved the same night: two bugs. MHCCP used the top-right/bottom-left samples for 4 px luma edges (rbultje's !1102, same fix as ours) and inherited inter chroma tx types outside the chroma tx set (our !1105, merged). The 4:2:2 failures were the MHCCP bug.

## Morning work (next session)

- Read `summary.md` and `base_*.log`. Start with failures that are new against 13 Nov main, then sanitizer hits, then 4:2:2/4:4:4 and 12-bit.
- For each confirmed bug, find the cause, write a public testsrc-based repro and an MR draft, and run the regression and SVT set before anything goes upstream (see `upstream/dav2d-contributing.md`).
- Probe results from planning (encoder d891b232, older dav2d build): 12-bit, `.obu`, cbr/vbr/cq/rt, still picture and operating point sets all matched avmdec on a short testsrc encode. The cropping window gives a different MD5 because dav2d's CLI doesn't apply it. That is a tooling question for upstream (should `tools/dav2d` apply `seq_hdr->crop`?), not a decoder bug.

## Results (17 Nov)

The run finished cleanly (`run.done` 07:04, no `run.FAILED`): 13322 configs, 11127 ok, 774 fail, 1342 encoder failures, 79 without a usable reference. Coverage: 10167 4:2:0, 1175 4:2:2, 559 4:4:4; 1755 12-bit; 1181 `.obu`; rate control q 8362, cbr 960, rt 954, vbr 938, cq 687.

All 774 failures were decoded again (`scripts/r5/recheck.py`) with main 7b187849 + !1018 + !1102 + !1103 (`r5`: asm 1t, C ASan+UBSan 1t, the failing thread mode 3x), with gramner's new !1107-!1109 on top, and with plain main.

- **324 fixed** on current main + the open MHCCP/CfL MRs (mostly the two #101 bugs). gramner's MRs fix nothing extra.
- **134 reference disagreements**, all 12-bit: avmdec from av2-enc 487d0761 and from av2-normative 14f43e4c give different output. dav2d matches av2-enc on 69. Of the other 65, 10 are cropped (not checked) and 55 match neither decoder; 52 of those have a feature that fails for other reasons (24 lossless, 19 GER, 6 grain, 3 loop filters across tiles), 3 have none (v003085, v005121, v012262).
- **316 still failing**, all explained (clusters: `scripts/r5/clusters.py`, flag ablation: `scripts/r5/ablate.py`):

Mismatching streams by first matching cluster (159), then the sanitizer-only ones:

| cluster | streams | cause and status |
|---|---|---|
| GER switch frames (no RAS) | 87 | 84 match with our open !1073 (data posted on !1073); 2 are #102, 1 is #103 |
| cropping window | 30 | 29 are cropping window + grain, new issue **#103** (dav2d outputs the uncropped frame and synthesises grain on it; AVM crops first, so left/top crops change the grain); 1 is lossless 4:2:2 |
| `disable_loopfilters_across_tiles` | 22 | new issue **#102**: parsed but ignored by deblocking, CDEF, CCSO, LR and GDF (each mismatches on its own) |
| film grain / denoise | 15 | 14 are film grain on odd widths (#96; the random crops give odd widths); 1 (v011743) is the multi-frame header bug |
| `--enable-fwd-kf` | 2 | v013159: open-loop key frame references (round-3 fix rebased on main, matches with it); v011123 (4:2:2) not rechecked with that fix + !1102 yet |
| other | 3 | v010221: multi-frame header bug; v005357: lossless (#99 or round-3 lossless masked compound); v005552 (`--full-still-picture-hdr`, "No frames read"): open, the flag alone decodes fine |
| UBSan only, output correct | 157 | new MR **!1111**: null `rp` pointer arithmetic with `ref_frame_mvs` off (176 streams have the report, incl. mismatching ones) |

Multi-frame header bug (new MR **!1110**, frame size from the multi-frame header ignored): v010221 and v011743 match with it. v013159 (also a resized key frame with a multi-frame header) matches with the open-loop key frame fix alone.

- **New against 13 Nov main**: only v000656 and v008369 (S-frames, 4:2:0); both broke between 6fbce209 and 79e95ee1 and are fixed again on a9b01371, so nothing to report.
- 12-bit, 4:2:2 and `.obu` have no failures of their own once the causes above are taken out. Rate control (cbr/vbr/cq/rt) only shows up through the same causes.

Upstream (17 Nov, all with public testsrc samples): issues #102 and #103; MRs !1110 (multi-frame header size) and !1111 (UBSan); note on #101 (fixed by !1102 + !1105); stress data on !1073. Checks before each MR: the corpus + SVT-AV2 low-res set (808 streams; only change: 2 SVT streams that crash in both builds, #86) and all 11901 failing and kept stress streams (only the intended streams change), asm 1t; repros also in C and with 4 threads.
