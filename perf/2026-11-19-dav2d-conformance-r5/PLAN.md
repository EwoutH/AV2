# dav2d conformance round 5 (19-20 Nov 2026): plan

## Starting point

- dav2d main is b130414d (19 Nov 13:35). Since round 4's decoder (28e39df9 + !1018), upstream merged our !1078, !1105, !1110, !1111 and !1117, rbultje's !1102 (MHCCP edges, #101) and a batch of error-handling and robustness commits (allocation failures, palette errors, refmvs buffer realloc/heap overflow, film grain NULL deref, still-picture and skip-segment checks). !1018 was closed, so round 5 decodes with plain main.
- Still open on our side: !1073 (GER/restricted refs), !1112 (OLK refs), !1126 (event flags), issues #96 (film grain, odd width), #102 (loop filters across tiles), #103 (cropping window + grain), #86 (CfL crash).
- Reference: AVM av2-enc 800611294e (19 Nov, 12 commits after round 4's 62529b44c), built with `CONFIG_TESTONLY_12BIT_SUPPORT=1`. Second opinion in triage: av2-normative 14f43e4c with 12-bit on (`avmn12`, agreed with av2-enc on all 1755 round-4 12-bit streams).
- Known gaps left out, as in round 4: RAS (`--sframe-type=1`), BRU, bridge frames, `--resize-mode 2/3`, multi-xlayer (#93).

## What round 5 adds

1. **Baseline on b130414d**: the reduced corpus (1t/mt4/C) plus all round-4 failure streams and repros, the private SVT-AV2 low-res set (against the round-4 decoder), an ASan+UBSan corpus pass, and the whole round-4 stress archive (11,900 streams, asm 1t and 4 threads) against its archived avmdec MD5s. This shows how many of the 773 round-4 failures upstream has fixed and whether any of the 11,127 passing streams regressed.
2. **Fewer wasted configs**: round 4 lost 1342 of 13,322 configs to encoder failures. `stress5.py` now avoids the invalid flag combinations (monotonic output order without keyframe filtering off, min > max GF interval/pyramid height/partition size, chroma sample position 0, monochrome with 4:2:2/4:4:4, lossless with AQ/delta-q) and the AVM encoder bugs A-G from round 4 (`--max-drl-refmvs` 7/8, `--min-partition-size=32`, ERP 0 at preset ≤ 1, AQ 3 on tiny frames, banding metadata on frames ≤ 16 high, single-picture LCD gets `--enable-cdef-on-skip-txfm=2`).
3. **4:2:2 and 4:4:4 at full weight** (420/422/444 = 50/25/25; round 4 had 85/10/5 while #101 was open).
4. **Damaged streams** (new, 20% of configs): after a normal decode, three damaged copies (1-8 bit flips in frame payloads, a truncated frame, a dropped frame; IVF framing kept valid) go through the C ASan+UBSan build, the asm ASan+UBSan build with 2 or 4 threads, and asm with 4 threads. A decode error is fine; a crash, sanitizer report or hang (300 s) is a failure. Upstream's recent error-path fixes suggest this is where bugs are being found now, and the round-4 hangs (looped IVF at 4 threads) were never explained.
5. **Threading**: two threaded decodes per stream with different thread counts (2/3/4/6/8) and frame delays, to catch the nondeterminism seen on v000264/v000642; and a ThreadSanitizer build on 15% of configs with ≥ 3 frames (exit on the first report).
6. **One 640x360 source** (bluesky) at 5% of 4:2:0 configs, presets ≥ 6, ≤ 6 frames, so 256x256 superblocks and multi-tile layouts get real content.
7. **Triage** (`triage5.py`): as round 4, plus labels for open issues so they don't flood the buckets (#102, #103 crop + grain, #96 odd width + grain, GER → !1073, fwd-kf → !1112), separate buckets for damaged-stream and TSan failures, and "is it new" checked against the round-4 decoder.

## Schedule (pc, 4 cores, Nice 19)

| Phase | Time | What |
| --- | --- | --- |
| prep (done 19 Nov) | | builds: AVM 800611294e, dav2d b130414d release / C / C ASan+UBSan / asm ASan+UBSan / TSan; smoke test (below) |
| baseline | ~1.5 h | `base_main`, `base_svt`, `base_asan`, `base_r4arch` |
| stress | until 06:30 | stress5, 3 workers (round 4: ~1100 configs/h; damage and TSan cost extra, so expect 7000-9000) |
| triage | 06:30-09:30 | triage5 + reductions (15 buckets max) |

Workers: 3 by default (`R5_JOBS`). A stray `ev` test process from another session (event-flags check, 4 threads, running since 18 Nov) currently takes one core; if it is still there at start, it should be stopped first or the run should use 2 workers.

Scripts and output: `/srv/compression/cache/av2conf/round5/` (`build.sh`, `run.sh`, `stress5.py`, `triage5.py`, `base5.py`; `run.log` for progress, `summary.md` at the end). Unit `av2-r5`.

## Morning work

- Compare `base_r4arch` with the round-4 status per stream: fixed upstream / still failing / regressed. Regressions first.
- Damaged-stream and TSan failures: reduce by hand (the stream is in `fail/<id>/damaged_*`), check whether they reproduce on the asm build without sanitizers, and look for duplicates among upstream's open issues before drafting anything.
- New conformance failures: as round 4 (reference check, flakiness, reduction), then MR or issue drafts per `upstream/dav2d-contributing.md`.
- Pi: decode the kept streams with Neon (3 threads max) as in round 4.

## Smoke test (19 Nov, 18:45)

- 12 stress5 configs with damage and TSan forced on (`R5_FORCE=1`, 4:2:0/4:2:2/4:4:4 mixed): all match avmdec in every decoder, with no sanitizer or TSan reports and no hangs. Most bit-flipped and truncated copies give decode errors, as expected. Copies with a dropped frame never do (dav2d keeps decoding without a word), so they mainly test the missing-reference paths for memory errors.
- `base5.py` on the first 60 archive streams: 1.2 s with 2 jobs, so the whole archive takes about 4 min per build. Two of the three round-4 failures among them now match.
