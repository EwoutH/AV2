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

The scripts (`build.sh`, `run.sh`, `stress4.py`, `triage4.py`, `tools/y4mfmt.py`) and all output are in `/srv/compression/cache/av2conf/round4/` (`run.log` for progress, `summary.md` at the end). The unit will be `av2-r4`.

## 4:4:4 inter chroma bug (found during planning, posted as dav2d #101)

- 4:4:4 inter frames decode with wrong chroma in small areas; key frames and luma match. It is not new: every dav2d build fails (main 28e39df9 asm and C, 13 Nov main, the old bench build), with streams from both avmenc versions. avmdec 487d0761 and av2-normative agree. (The smoke-test impression that only the new encoder triggers it was luck on one stream.)
- Rate on 4-frame encodes of 4 clips (3 QPs, cpu-used 6/9, both encoders, inter-intra on/off): 4:4:4 40/96 mismatch, 4:2:2 4/96 (testsrc only), 4:2:0 0/96. Single encoder tool toggles only move the mismatch around.
- Public 2-frame repro: `i444/r444_ld.ivf` (testsrc 4:4:4, `--limit=2 --lag-in-frames=0 --end-usage=q --qp=80 --cpu-used=9`), frame 1 V differs at x 116-119, y 14-23. Posted with that repro as dav2d #101 (cause unknown).
- Effect on the run: the 4:4:4 share in stress4 is lowered from 20% to 5% so this one bug doesn't flood the triage. 4:2:2 stays at 25%.
- Next step for the bug: block traces of frame 1 in both decoders (frame-1 trace builds are ready: `round4/build/dbg1`, `round4/build/avm-dbg1`).

## Morning work (next session)

- Read `summary.md` and `base_*.log`. Start with failures that are new against 13 Nov main, then sanitizer hits, then 4:2:2/4:4:4 and 12-bit.
- For each confirmed bug, find the cause, write a public testsrc-based repro and an MR draft, and run the regression and SVT set before anything goes upstream (see `upstream/dav2d-contributing.md`).
- Probe results from planning (encoder d891b232, older dav2d build): 12-bit, `.obu`, cbr/vbr/cq/rt, still picture and operating point sets all matched avmdec on a short testsrc encode. The cropping window gives a different MD5 because dav2d's CLI doesn't apply it. That is a tooling question for upstream (should `tools/dav2d` apply `seq_hdr->crop`?), not a decoder bug.
