## ab-benchmark.jsonl

Incomplete series: exploratory observations only.

9 attempted pairs; 6 accepted.

| Stream | Workers / delay | Pairs | Speed ratio, median [range] | CPU ratio | RSS delta |
|---|---:|---:|---:|---:|---:|
| Netflix_DrivingPOV_720p_60fps_10bit_420_qp135_600f.ivf | 3 / 1 | 1 | 1.050 [1.050–1.050] | 1.003 | +0.3 MiB |
| Noise_Ocean_1920x1080_60fps_filmgrain_qp135_130f.ivf | 3 / 1 | 1 | 1.376 [1.376–1.376] | 0.873 | -0.0 MiB |
| crowd_run_1080p50_qp135_500f.ivf | 2 / 1 | 1 | 1.199 [1.199–1.199] | 0.999 | +0.2 MiB |
| FourPeople_480x270_60_qp210_130f.ivf | 2 / 1 | 2 | 1.948 [1.864–2.033] | 0.681 | -0.1 MiB |
| FourPeople_480x270_60_qp210_130f.ivf | 3 / 1 | 1 | 1.648 [1.648–1.648] | 0.816 | +0.0 MiB |

2 workers, delay 1: geometric mean of per-stream median speed ratios = **1.529×**, 2 streams.

3 workers, delay 1: geometric mean of per-stream median speed ratios = **1.336×**, 3 streams.

Speed ratio = baseline wall time / variant wall time; >1 favors the variant. CPU ratio = variant CPU time / baseline CPU time; <1 favors the variant. Ranges describe the accepted repetitions, not confidence intervals.

## ab-clamped-benchmark.jsonl

Incomplete series: exploratory observations only.

6 attempted pairs; 2 accepted.

| Stream | Workers / delay | Pairs | Speed ratio, median [range] | CPU ratio | RSS delta |
|---|---:|---:|---:|---:|---:|
| crowd_run_1080p50_qp135_500f.ivf | 2 / 1 | 1 | 1.202 [1.202–1.202] | 0.998 | +0.2 MiB |
| FourPeople_480x270_60_qp210_130f.ivf | 2 / 1 | 1 | 1.281 [1.281–1.281] | 1.020 | +0.0 MiB |

2 workers, delay 1: geometric mean of per-stream median speed ratios = **1.241×**, 2 streams.

Speed ratio = baseline wall time / variant wall time; >1 favors the variant. CPU ratio = variant CPU time / baseline CPU time; <1 favors the variant. Ranges describe the accepted repetitions, not confidence intervals.
