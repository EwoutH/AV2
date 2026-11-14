## Speed vs avmdec, 1 thread (geomean of per-stream ratios; streams both decoded correctly)

| host | decoder | bit depth | streams | Mpix/s (geomean) | x avmdec |
|---|---|---|---|---|---|
| pc | avmdec | 8 | 64/64 | 32.8 | 1.00 |
| pc | avmdec | 10 | 24/24 | 29.7 | 1.00 |
| pc | dav2d | 8 | 64/64 | 82.7 | 2.52 |
| pc | dav2d | 10 | 24/24 | 16.7 | 0.56 |
| pc | dav2d_noasm | 8 | 11/11 | 15.0 | 0.53 |
| pc | dav2d_noasm | 10 | 2/2 | 9.1 | 0.39 |
| pc | rusty_av2d | 8 | 4/4 | 7.6 | 0.29 |
| pc | splot | 8 | 64/64 | 69.7 | 2.12 |
| pc | splot | 10 | 24/24 | 44.6 | 1.50 |
| pi | avmdec | 8 | 11/11 | 3.6 | 1.00 |
| pi | avmdec | 10 | 2/2 | 2.2 | 1.00 |
| pi | dav2d | 8 | 11/11 | 7.2 | 2.03 |
| pi | dav2d | 10 | 2/2 | 3.9 | 1.77 |
| pi | dav2d_noasm | 8 | 11/11 | 5.3 | 1.49 |
| pi | dav2d_noasm | 10 | 2/2 | 3.1 | 1.40 |
| pi | splot | 8 | 11/11 | 10.1 | 2.85 |
| pi | splot | 10 | 2/2 | 6.4 | 2.87 |

## Thread scaling, core set (geomean Mpix/s over streams decoded correctly at every thread count)

| host | decoder | 1 thr | 2 thr | 3 thr | 4 thr |
|---|---|---|---|---|---|
| pc | avmdec | 27.8 |  |  | 28.7 |
| pc | dav2d | 55.5 | 105.3 | 139.6 | 155.5 |
| pc | splot | 57.7 | 101.9 | 138.0 | 164.1 |
| pi | avmdec (1 stream) | 2.7 |  |  | 3.4 |
| pi | dav2d | 6.6 | 13.0 |  | 22.5 |
| pi | splot | 9.4 | 15.7 |  | 23.0 |

## pc, 1 thread(s): dav2d vs avmdec over 88 streams

- 8-bit: 64 streams, geomean 2.52x, range 1.67-2.98x
- 10-bit: 24 streams, geomean 0.56x, range 0.36-0.96x
- all: geomean 1.67x, median 2.43x, range 0.36x (hd/Skater227_1920x1080_30fps_qp135_300f.ivf) to 2.98x (hd/crowd_run_1080p50_qp135_500f.ivf)

## pc, 4 thread(s): dav2d vs avmdec over 13 streams

- 8-bit: 11 streams, geomean 6.48x, range 4.72-9.55x
- 10-bit: 2 streams, geomean 2.03x, range 1.90-2.17x
- all: geomean 5.42x, median 5.88x, range 1.90x (hd/Netflix_DrivingPOV_720p_60fps_10bit_420_qp135_600f.ivf) to 9.55x (hd/crowd_run_1080p50_qp135_500f.ivf)

## pc, 1 thread(s): splot vs avmdec over 88 streams

- 8-bit: 64 streams, geomean 2.12x, range 1.78-3.00x
- 10-bit: 24 streams, geomean 1.50x, range 1.32-1.75x
- all: geomean 1.93x, median 2.04x, range 1.32x (hd/DinnerSceneCropped_1920x1080_2997fps_10bit_420_qp135_130f.ivf) to 3.00x (samples/FourPeople_480x270_60_qp210_130f.ivf)

## pc, 4 thread(s): splot vs avmdec over 13 streams

- 8-bit: 11 streams, geomean 5.92x, range 4.33-7.24x
- 10-bit: 2 streams, geomean 4.75x, range 4.66-4.85x
- all: geomean 5.72x, median 5.78x, range 4.33x (hd/old_town_cross_1080p50_tiles4x2_qp135_500f.ivf) to 7.24x (hd/crowd_run_1080p50_qp135_500f.ivf)

## splot vs dav2d (splot speed / dav2d speed, geomean per stream; >1: splot faster)

| host | threads | 8-bit | 10-bit | streams |
|---|---|---|---|---|
| pc | 1 | 0.84x (0.72-1.29) | 2.67x (1.82-3.76) | 88 |
| pc | 2 | 0.81x (0.65-1.33) | 2.49x (2.44-2.54) | 13 |
| pc | 4 | 0.88x (0.70-1.39) | 2.30x (1.31-3.09) | 88 |
| pi | 1 | 1.40x (0.94-1.87) | 1.62x (1.56-1.67) | 13 |
| pi | 2 | 1.17x (0.74-1.61) | 1.41x (1.35-1.47) | 13 |
| pi | 4 | 0.98x (0.66-1.38) | 1.26x (1.17-1.36) | 13 |

## 1080p, 4 threads: geomean fps over the 1920x1080 and 1080x1920 streams

| host | decoder | 8-bit | 10-bit |
|---|---|---|---|
| pc | avmdec | 15 fps (6) | 12 fps (1) |
| pc | dav2d | 113 fps (44) | 31 fps (18) |
| pc | splot | 96 fps (44) | 70 fps (18) |
| pi | avmdec | 2 fps (1) | - |
| pi | dav2d | 12 fps (6) | 8 fps (1) |
| pi | splot | 12 fps (6) | 9 fps (1) |

## dav2d asm gain, 1 thread, core set (dav2d vs no-asm build, geomean per-stream ratio)

| host | bit depth | streams | asm speed-up |
|---|---|---|---|
| pc | 8 | 11 | 4.79x |
| pc | 10 | 2 | 1.46x |
| pi | 8 | 11 | 1.36x |
| pi | 10 | 2 | 1.27x |

## Correctness (untimed check: raw output MD5 vs avmdec)

| host | check | matched | of | not matched |
|---|---|---|---|---|
| pc | dav2d_t4 | 13 | 13 | - |
| pc | rusty_av2d_t1 | 4 | 4 | - |
| pc | splot_t4 | 13 | 13 | - |

## Output sink, 1 thread, core set (wall time of the variant / the timed sink, geomean)

| host | variant | timed series | streams | time ratio |
|---|---|---|---|---|
| pc | dav2d_yuvnull | dav2d | 13 | 1.021 |
| pc | splot_null | splot | 13 | 0.980 |
| pc | avmdec_rawnull | avmdec | 13 | 1.015 |

## Change since 2 Nov, core set (geomean per-stream Mpix/s ratio, 14 Nov / 2 Nov)

| host | decoder | threads | streams | ratio |
|---|---|---|---|---|
| pc | avmdec | 1 | 13 | 1.17x |
| pc | avmdec | 4 | 13 | 1.18x |
| pc | dav2d | 1 | 13 | 1.18x |
| pc | dav2d | 4 | 13 | 1.23x |
| pc | dav2d_noasm | 1 | 13 | 1.12x |
| pc | splot | 1 | 13 | 2.06x |
| pc | splot | 4 | 13 | 1.96x |
| pi | avmdec | 1 | 13 | 1.02x |
| pi | avmdec | 4 | 1 | 1.02x |
| pi | dav2d | 1 | 13 | 1.06x |
| pi | dav2d | 4 | 13 | 1.07x |
| pi | dav2d_noasm | 1 | 13 | 1.03x |
| pi | splot | 1 | 13 | 1.03x |
| pi | splot | 4 | 13 | 1.19x |

## Today's build vs the 2 Nov binary, same sink (geomean per-stream speed ratio, core set)

| host | decoder | threads | streams | 8-bit | 10-bit | all |
|---|---|---|---|---|---|---|
| pc | avmdec | 1 | 13 | 1.07x | 1.09x | 1.08x |
| pc | dav2d | 1 | 13 | 1.03x | 1.03x | 1.03x |
| pc | dav2d | 4 | 13 | 1.03x | 1.03x | 1.03x |
| pc | splot | 1 | 13 | 2.31x | 1.96x | 2.25x |
| pc | splot | 4 | 13 | 2.39x | 1.80x | 2.29x |
| pi | dav2d | 1 | 13 | 1.00x | 1.01x | 1.00x |
| pi | splot | 1 | 13 | 1.14x | 0.95x | 1.11x |
