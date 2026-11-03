# Title

Speed: C `gdf_prep` takes 40-60% of decode time on 10-bit x86 and on aarch64; profile and port priorities

# Body

_Found by Claude Code while benchmarking AV2 decoders._

On one thread of an i5-4590 (AVX2), dav2d `9b5d2f6e` decodes 8-bit AVM streams at 2.44x the speed of `avmdec`, but 10-bit streams at only 0.63x. On a Raspberry Pi 4 (Cortex-A72), NEON makes dav2d only 1.33x faster than its C build (x86 asm: 4.5x). We profiled both machines to find out why. In both cases most of the time goes to C loop filters that have 8-bit AVX2 but no 16bpc AVX2 and no NEON. GDF is by far the largest.

### Where the time goes

`perf record`, 1 thread, first 40 frames (pi: 20) of 1080p/720p AVM streams (QP 110-135, `--cpu-used 6`). Mean share of CPU time; "C" means no SIMD runs for that function.

| | x86, 10-bit (8 streams) | x86, 8-bit (8 streams) | pi, NEON build (9 streams) |
|---|---|---|---|
| GDF (`gdf_prep`, `compute_gradient_row`, `gdf_add`) | **55.7% C** | 10.7% asm | **39.3% C** |
| Wiener (`wiener_multi`, `ns_wiener_single_y`, features) | **15.7% C** | 3.4% asm | **15.7% C** |
| TMV projection (`load_tmvs_refs_c`) | 4.0% C | **20.2% C** | 5.4% C |
| CCSO | 3.2% C | 0.5% asm | 2.9% C |
| Deblock | 3.0% C | 1.8% asm + 1.1% C | 3.3% C |
| Inverse transform | 2.0% C | 0.8% asm | 0.6% C + 0.9% asm |
| Entropy decode + parse | 1.4% C + 0.5% asm | 6.7% C + 1.8% asm | 5.0% C + 0.4% asm |
| Inter prediction | 1.9% C + 6.7% asm | 7.2% C + 17.0% asm | 1.2% C + 9.6% asm |

On a single stream, C `gdf_prep` alone ranges from 37% to 66% on x86 10-bit and from 19% to 59% on the pi. On x86 10-bit, the asm build is no faster than `-Denable_asm=false` for GDF, Wiener, CCSO, deblock and itx (0.96-0.99x). For 8-bit, the same families gain 3-15x from asm: GDF 14.8x, Wiener 12.0x, CDEF 12.2x, deblock 3.0x.

### Expected gains

These estimates assume a port gives the speed-up per function that the 8-bit AVX2 code already gets over C, applied to the measured profile:

| port | x86 10-bit, 1 thread | pi (assumes NEON gains half to all of what AVX2 gains) |
|---|---|---|
| GDF | 2.1x (1.5-2.6x); about 1.3x `avmdec` instead of 0.63x | 1.5-1.6x (1.2-2.4x) |
| + Wiener | 3.0x (2.3-3.8x); about 1.9x `avmdec` | 1.9-2.1x |
| + CCSO, deblock, itx (x86) / + CCSO, deblock, TMV at 2x (pi) | 3.8x (2.5-4.7x); about 2.4x `avmdec` | 2.2-2.5x |

### Suggested work, in order

1. **16bpc AVX2 `gdf_prep` + `gdf_add`.** This should be a small port. The C code normalises every row to 10-bit `uint16_t` before filtering (`up_shift`/`down_shift` in `gdf_backup_row`), and `gdf_prep_8bpc` (`looprestoration_avx2.asm`) does the same with `pmovzxbw` + `psllw 2` in `.load_p`/`.load_tb_lr`/`.load_p_lr*`. After loading, the kernel already works on 16-bit lanes. A 16bpc version mostly needs a different loader (`movu` + `psrlw` by `bitdepth - 10`) and a `gdf_add` that clamps to `bitdepth_max`.
2. **NEON `gdf_prep`.** On aarch64, `looprestoration_dsp_init_arm()` sets only `gdf_add`. This is the largest item on the pi for both 8- and 10-bit.
3. **16bpc AVX2 and NEON Wiener** (`ns_wiener_multi`, `ns_wiener_single`, `pc_wiener`, `wiener_uv_*`). Today these are `#if BITDEPTH == 8` on x86 and absent on aarch64.
4. **`load_tmvs_refs`** (C on every arch, 11-36% of 8-bit x86 time, 20% on average). It is already a DSP hook (`Dav2dRefmvsDSPContext.load_tmvs_refs`) with no asm behind it. On Life_1080p30, 7.3 of its 16% is in `check_traj_intersect` (MV trajectories). Clearing the trajectory and map buffers costs only 0.15%. Making it 2x faster gives 1.11x overall on 8-bit (up to 1.22x).
5. **Film grain apply.** `fgy_32x32xn`/`fguv_32x32xn` SIMD has been `#if 0` since a93c8bf5 (variable block sizes) on x86 and aarch64. That is 45% of the time on our film-grain stream on x86, and 17% on the pi.
6. **Smaller items:** 16bpc AVX2 for CCSO, deblock and the inverse transforms (x86 16bpc has only `cctx`). On aarch64: NEON CCSO, `msac_decode_symbol_adapt4/8` (C on aarch64; 6% on a QP 110 stream on the pi), and the refmvs `splat_*`/`tip_*` functions. NEON deblock and `setup_thr` are already in progress in !943 and !879. `src/arm/deblock.h` is an unused leftover: it is not included anywhere and has no `.S`.

### Reproduce

```
meson setup b src/dav2d --buildtype release -Ddefault_library=static
meson compile -C b
perf record -F 1000 -- b/tools/dav2d -q -i TunnelFlag_1920x1080_60fps_10bit_420_qp135_600f.ivf \
    --muxer null -o - --threads 1 --limit 40
perf report --no-children --sort sym
#  55.9%  gdf_prep_c
#   6.1%  ns_wiener_single_y_c
#   3.7%  compute_gradient_row
```

Streams: [hd-streams-2026-10](https://github.com/EwoutH/AV2/releases/tag/hd-streams-2026-10). Every stream decodes to the `avmdec` pixel MD5. GCC 15.3. Per-symbol sample counts for all 41 profiles (32 x86, asm and no-asm builds; 9 pi), plus the scripts that group them: [perf/2026-11-03-dav2d-profile](https://github.com/EwoutH/AV2/tree/9ec61d8/perf/2026-11-03-dav2d-profile). The full speed benchmark (88 streams, `avmdec`/dav2d/splot): [perf/2026-11-02-av2-decode-speed](https://github.com/EwoutH/AV2/tree/main/perf/2026-11-02-av2-decode-speed).
