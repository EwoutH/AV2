# AV2 sample streams

Small AV2 test streams, encoded with the AVM reference encoder, for
testing and benchmarking AV2 decoders (such as dav2d).

These are **not official conformance streams**. AV2 tools are still
changing, so the streams are tied to the AVM version below and may not
decode with other versions.

## Streams

| Source clip | Resolution | QP | Frames |
|---|---|---|---|
| FourPeople_480x270_60 | 480x270 | 110, 160, 210 | 130 |
| Vertical_Bayshore_270x480_2997 | 270x480 (vertical) | 110, 160, 210 | 130 |
| BlueSky_360p25_v2 | 360p | 110, 160, 210 | 130 |
| KristenAndSara_1280x720_60 | 1280x720 | 160 | 240 |
| vidyo4_720p_60fps | 1280x720 | 160 | 240 |
| Netflix_DrivingPOV_720p_60fps_10bit_420 | 1280x720, 10-bit | 160 | 209 |
| Vertical_bees_2997_1080x1920 | 1080x1920 (vertical) | 160 | 150 |
| old_town_cross_1080p50 | 1920x1080 | 160 | 188 |
| RitualDance_1920x1080_60fps_10bit_420 | 1920x1080, 10-bit | 160 | 120 |
| TunnelFlag_1920x1080_60fps_10bit_420 | 1920x1080, 10-bit | 160 | 73 |

The QPs are from the AV2 Common Test Conditions (CTC) Random Access range
(110 high quality to 210 low quality). The 480x270, 270x480 and 360p
clips were encoded at all three QPs; the 720p and 1080p streams are at
QP 160 only.

Files are named `<clip>_qp<QP>_<frames>f.ivf`, where `<frames>` is the
number of frames the stream decodes to. The 720p and 1080p streams stop
early: their encodes were interrupted, and the streams are the frames
written before that, which decode without errors. The rest of each clip
is not included.

`manifest.txt` lists the MD5 of each stream's decoded output, as
reported by the reference decoder (`avmdec --md5`). Use these to check
another decoder's output.

## How they were made

- **Sources:** the official AV2 CTC test set
  (https://media.xiph.org/video/aomctc/). See the source clips' own
  licenses before reusing them.
- **Encoder:** AVM (https://github.com/AOMediaCodec/avm) at commit
  `01803db6afa5a0616702a3814fc5934ab9e99adf`, built on Windows with MSVC
- **Build flags:** `-DCONFIG_TENSORFLOW_LITE=0 -DCONFIG_ML_PART_SPLIT=0
  -DCONFIG_DIP_EXT_PRUNING=0`. TensorFlow Lite doesn't build on
  Windows, so it and the two experiments that need it were turned off.
  This differs from AVM's default configuration.
- **Compiler:** the 480x270, 270x480 and 360p streams were built with
  Visual Studio 2022 (MSVC 19.34). The 720p and 1080p streams were built
  with Visual Studio 2026 (MSVC 19.51), which needs one extra flag,
  `/d2SSAOptimizer-` for `avm_dsp/x86/highbd_variance_avx2.c`, to
  compile (https://github.com/AOMediaCodec/avm/issues/5532).
- **Encoder settings:** `--end-usage=q --qp=<QP> --cpu-used=6`, IVF
  container
- **Script:** `encode_samples.py` does everything: builds AVM, downloads
  the source clips and encodes them in parallel. Run
  `python encode_samples.py --help` for options.
