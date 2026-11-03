# Where dav2d spends its time (3 Nov 2026)

A follow-up to the [2 Nov decode-speed benchmark](../2026-11-02-av2-decode-speed/).
That benchmark found that dav2d on x86 runs at 2.44x `avmdec` on 8-bit but only
0.63x on 10-bit, and that NEON speeds dav2d up only 1.33x on the pi. This
profile shows why. The upstream issue draft is [`issue-draft.md`](issue-draft.md).

## Findings

1. **The C GDF filter is most of the time on x86 10-bit (56%) and on the pi
   (39%).** `gdf_prep` has 8-bit AVX2 only and no NEON. Wiener is next (16% on
   both), with the same coverage.
2. **On x86 10-bit, the asm build is no faster than C for GDF, Wiener, CCSO,
   deblock and itx (0.96-0.99x).** For 8-bit, the same families gain 3-15x.
3. **Estimated gains** (from the per-family gain of the 8-bit AVX2 code):
   - x86 10-bit: a 16bpc GDF port gives 2.1x; adding Wiener gives 3.0x; adding
     CCSO, deblock and itx gives 3.8x. That is about 1.3x, 1.9x and 2.4x
     `avmdec`.
   - pi: NEON GDF gives 1.5-1.6x; adding Wiener gives 1.9-2.1x.
4. **On 8-bit x86, `load_tmvs_refs_c` is the top C function (20% on
   average, 11-36% per stream).** About half of that is `check_traj_intersect`.
5. **Film grain apply runs as C everywhere.** Its asm has been disabled since
   a93c8bf5. That is 45% of the time on the film-grain stream on x86 and 17%
   on the pi.

## Follow-up: 16bpc AVX2 GDF, two versions

Item 1 of the issue (dav2d #88) was written twice, independently: once by
Claude (branch `gdf-16bpc-avx2` on the `EwoutH/dav2d` fork, `e2475122` +
`8f9f5a09`) and once by Codex `gpt-6.1-sol` at high reasoning effort (branch
`gdf-16bpc-codex`, `2c186ae4`). Both start from dav2d main `652ae8ab`, and
both reuse the 8bpc filter core and add 16bpc row loaders.

- **Same design for `gdf_prep`.** Claude's version calls the 8bpc
  function's `.calc_grad`/`.main` code (+2.3 KB `.text`). Codex's version
  emits the whole function twice from a macro (+6.8 KB).
- **Correct.** Both pass checkasm on 2000 seeds with Codex's extended tests
  (10- and 12-bit separately, every `gdf_add` width and scale). Both match
  `avmdec` on all 88 corpus streams with 1 and 4 threads, and both link with
  `-Dbitdepths=8` and `-Dbitdepths=16`.
- **Same decode speed.** On the 24 10-bit streams, 1 thread, pinned, 2
  interleaved repeats: 14.8 Mpix/s before, 29.3 Mpix/s after, for both.
  That is 1.98x (1.39-2.47x), against the 2.1x estimate. Codex's time divided
  by Claude's: 1.001 (0.991-1.008).
- **checkasm cycles** per 64x64 block (C = about 950k / 18k):
  - `gdf_prep`: Claude 58.6k / 58.3k (10/12-bit), Codex 56.2k / 56.2k. The
    8bpc function also moves by 3-6% between the two builds, so this is
    within code-placement noise.
  - `gdf_add`: Claude 1.47k (16 pixels per store; may write up to 8 pixels
    past `w`, the 8bpc asm writes up to 31), Codex 2.92k (8 pixels per store,
    never past `w`). `gdf_add` costs about 2.5% of `gdf_prep`.

## Setup

- **dav2d:** `9b5d2f6e`, the same builds as on 2 Nov (GCC 15.3, release, static),
  plus `-Denable_asm=false`.
- **Profiler:** `perf record -F 1000` (500 on the pi), 1 thread, first 40 frames
  (20 on the pi).
- **x86:** i5-4590, 8 10-bit and 8 8-bit 1080p/720p streams
  ([`scripts/streams.txt`](scripts/streams.txt)).
- **pi:** the 9 HD streams of the core set. The pi binaries are stripped, so
  addresses were resolved with `nm` on the unstripped cross build. The two
  binaries are the same apart from symbols.
- **Grouping:** symbols are grouped into DSP families by name
  ([`scripts/classify.py`](scripts/classify.py)). A symbol counts as asm if
  it has an ISA suffix (`_avx2`, `_neon`, ...).

## Files

- `data/x86/<build>.<stream>.tsv`, `data/pi/dav2d.<stream>.tsv`: samples per
  symbol.
- `data/load_tmvs_srclines_Life.txt`: `load_tmvs_refs_c` per source line
  (release + `-g` build).
- `scripts/prof.sh` records one profile. `classify.py data/x86 out.json`
  groups the symbols. `agg.py out.json` prints the shares and the per-family asm
  gains. `est.py out.json` prints the x86 10-bit estimates. `pi_agg.py data/pi`
  prints the pi table and estimates.

## Limits

- The estimates assume each port matches the 8-bit AVX2 gain over C. For NEON
  they assume half of that gain up to all of it. They ignore memory effects and
  any work the port leaves out.
- 40 frames per stream. Every stream comes from one encoder (AVM, mostly
  `--cpu-used 6`, QP 135).
- Only 1 thread was profiled. With more threads, the shares may move (for
  example, toward serial parsing).
