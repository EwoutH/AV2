# Reanalysis of 14 November data

| Host | Group | Streams | 4t / 1t speed | Average busy cores, 4t | CPU time, 4t / 1t |
|---|---|---:|---:|---:|---:|
| pc | 8-bit | 64 | 2.73× | 3.13 | 1.15× |
| pc | 10-bit | 24 | 3.56× | 3.77 | 1.06× |
| pc | screen in filename | 11 | 2.49× | 2.93 | 1.18× |
| pi | 8-bit | 11 | 3.38× | 3.53 | 1.05× |
| pi | 10-bit | 2 | 3.58× | 3.62 | 1.02× |
| pi | screen in filename | 1 | 3.24× | 3.56 | 1.11× |

Geometric means of per-stream ratios. Screen classification uses filenames, not parsed feature flags. These groups overlap. CPU time includes the main thread.

# diagnostics.jsonl

| Stream | Workers / frames | Lock held | Lock acquisition wait | Condition wait | Hash matches |
|---|---:|---:|---:|---:|---|
| Noise_Ocean_1920x1080_60fps_filmgrain_qp135_130f.ivf | 2 / 1 | 0.08% | 0.01% | 39.08% | True |
| Noise_Ocean_1920x1080_60fps_filmgrain_qp135_130f.ivf | 2 / 2 | 0.09% | 0.01% | 15.08% | True |
| Slides1_1920x1080_30fps_8bit_420_screen_qp135_130f.ivf | 2 / 1 | 0.09% | 0.00% | 58.37% | True |
| Slides1_1920x1080_30fps_8bit_420_screen_qp135_130f.ivf | 2 / 2 | 0.14% | 0.01% | 19.38% | True |
| old_town_cross_1080p50_tiles4x2_qp135_500f.ivf | 2 / 1 | 0.26% | 0.03% | 26.34% | True |
| old_town_cross_1080p50_tiles4x2_qp135_500f.ivf | 2 / 2 | 0.36% | 0.05% | 0.11% | True |
| Netflix_DrivingPOV_720p_60fps_10bit_420_qp135_600f.ivf | 2 / 1 | 0.03% | 0.00% | 21.94% | True |
| Netflix_DrivingPOV_720p_60fps_10bit_420_qp135_600f.ivf | 2 / 2 | 0.04% | 0.00% | 0.18% | True |
| crowd_run_1080p50_qp135_500f.ivf | 2 / 1 | 0.05% | 0.00% | 39.63% | True |
| crowd_run_1080p50_qp135_500f.ivf | 2 / 2 | 0.06% | 0.00% | 0.39% | True |
| FourPeople_480x270_60_qp210_130f.ivf | 2 / 1 | 0.49% | 0.03% | 57.75% | True |
| FourPeople_480x270_60_qp210_130f.ivf | 2 / 2 | 0.64% | 0.13% | 3.47% | True |

Shares of aggregate instrumented worker wall time; includes descheduling. Condition waits include reacquiring the mutex. The main thread, output hashing, and single-frame initialization are outside this accounting. This is not a throughput benchmark.

# three-pass-diagnostics.jsonl

| Stream | Workers / frames | Lock held | Lock acquisition wait | Condition wait | Hash matches |
|---|---:|---:|---:|---:|---|
| Noise_Ocean_1920x1080_60fps_filmgrain_qp135_130f.ivf | 2 / 1 | 0.15% | 0.01% | 36.54% | True |
| Slides1_1920x1080_30fps_8bit_420_screen_qp135_130f.ivf | 2 / 1 | 0.25% | 0.00% | 53.08% | True |
| old_town_cross_1080p50_tiles4x2_qp135_500f.ivf | 2 / 1 | 0.33% | 0.05% | 25.27% | True |
| Netflix_DrivingPOV_720p_60fps_10bit_420_qp135_600f.ivf | 2 / 1 | 0.05% | 0.00% | 15.50% | True |
| crowd_run_1080p50_qp135_500f.ivf | 2 / 1 | 0.05% | 0.00% | 29.21% | True |
| FourPeople_480x270_60_qp210_130f.ivf | 2 / 1 | 0.60% | 0.06% | 46.53% | True |

Shares of aggregate instrumented worker wall time; includes descheduling. Condition waits include reacquiring the mutex. The main thread, output hashing, and single-frame initialization are outside this accounting. This is not a throughput benchmark.

# Interrupted sweep

49 completed runs; 10 with ≤0.10 foreign cores. Median foreign CPU: 1.03 cores. Incomplete randomized repetitions; no aggregate speed claim is made.
