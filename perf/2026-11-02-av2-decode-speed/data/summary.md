## Speed vs avmdec, 1 thread (geomean of per-stream ratios; streams both decoded correctly)

| host | decoder | bit depth | streams | Mpix/s (geomean) | x avmdec |
|---|---|---|---|---|---|
| pc | avmdec | 8 | 64/64 | 27.7 | 1.00 |
| pc | avmdec | 10 | 24/24 | 23.8 | 1.00 |
| pc | dav2d | 8 | 64/64 | 67.7 | 2.44 |
| pc | dav2d | 10 | 24/24 | 15.0 | 0.63 |
| pc | dav2d_c | 8 | 64/64 | 16.6 | 0.60 |
| pc | dav2d_c | 10 | 24/24 | 10.4 | 0.43 |
| pc | dav2d_noasm | 8 | 11/11 | 13.4 | 0.55 |
| pc | dav2d_noasm | 10 | 2/2 | 8.3 | 0.43 |
| pc | rav2d | 8 | 0/11 | - | - (output wrong) |
| pc | rav2d | 10 | 0/2 | - | - (output wrong) |
| pc | rusty_av2d | 8 | 0/4 | - | - (output wrong) |
| pc | splot | 8 | 64/64 | 30.7 | 1.11 |
| pc | splot | 10 | 24/24 | 22.7 | 0.95 |
| pi | avmdec | 8 | 11/11 | 3.5 | 1.00 |
| pi | avmdec | 10 | 2/2 | 2.2 | 1.00 |
| pi | dav2d | 8 | 11/11 | 6.8 | 1.96 |
| pi | dav2d | 10 | 2/2 | 3.7 | 1.69 |
| pi | dav2d_noasm | 8 | 11/11 | 5.1 | 1.47 |
| pi | dav2d_noasm | 10 | 2/2 | 3.0 | 1.38 |
| pi | rav2d | 8 | 0/4 | - | - (output wrong) |
| pi | rusty_av2d | 8 | 0/4 | - | - (output wrong) |
| pi | splot | 8 | 11/11 | 9.7 | 2.79 |
| pi | splot | 10 | 2/2 | 6.6 | 3.00 |

## Thread scaling, core set (geomean Mpix/s over streams decoded correctly at every thread count)

| host | decoder | 1 thr | 2 thr | 3 thr | 4 thr |
|---|---|---|---|---|---|
| pc | avmdec | 23.7 | 24.3 | 24.3 | 24.4 |
| pc | dav2d | 46.9 | 96.9 | 119.2 | 126.3 |
| pc | dav2d_c | 13.8 | 27.4 | 35.9 | 41.0 |
| pc | splot | 28.0 | 50.6 | 69.3 | 83.6 |
| pi | avmdec | 3.3 |  |  | 3.3 |
| pi | dav2d | 6.2 | 12.9 |  | 21.0 |
| pi | splot | 9.2 | 14.5 |  | 19.3 |

## pc, whole corpus, 1 thread(s): dav2d vs avmdec over 88 streams

- 8-bit: 64 streams, geomean 2.44x, range 1.58-3.04x
- 10-bit: 24 streams, geomean 0.63x, range 0.45-1.00x
- all: geomean 1.69x, median 2.38x, range 0.45x (hd/Skater227_1920x1080_30fps_qp135_300f.ivf) to 3.04x (hd/riverbed_1080p25_qp135_250f.ivf)

## pc, whole corpus, 4 thread(s): dav2d vs avmdec over 88 streams

- 8-bit: 64 streams, geomean 6.17x, range 3.32-9.42x
- 10-bit: 24 streams, geomean 2.18x, range 1.63-2.61x
- all: geomean 4.65x, median 5.49x, range 1.63x (hd/Skater227_1920x1080_30fps_qp135_300f.ivf) to 9.42x (hd/crowd_run_1080p50_qp135_500f.ivf)

## dav2d asm gain, 1 thread, core set (dav2d vs no-asm build, geomean per-stream ratio)

| host | bit depth | streams | asm speed-up | --cpumask 0 vs no asm |
|---|---|---|---|---|
| pc | 8 | 11 | 4.47x | 1.13x |
| pc | 10 | 2 | 1.46x | 1.00x |
| pi | 8 | 11 | 1.33x | - |
| pi | 10 | 2 | 1.23x | - |

## Correctness (streams whose output matched avmdec, any thread count)

| host | decoder | matched | of |
|---|---|---|---|
| pc | avmdec | 88 | 88 |
| pc | dav2d | 88 | 88 |
| pc | dav2d_c | 88 | 88 |
| pc | dav2d_noasm | 13 | 13 |
| pc | rav2d | 0 | 13 |
| pc | rusty_av2d | 0 | 4 |
| pc | splot | 88 | 88 |
| pi | avmdec | 13 | 13 |
| pi | dav2d | 13 | 13 |
| pi | dav2d_noasm | 13 | 13 |
| pi | rav2d | 0 | 4 |
| pi | rusty_av2d | 0 | 4 |
| pi | splot | 13 | 13 |
