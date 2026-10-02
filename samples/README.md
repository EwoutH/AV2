# AV2 sample streams

Small AV2 test streams, encoded with the AVM reference encoder, for
testing and benchmarking AV2 decoders (such as dav2d).

These are **not official conformance streams**. AV2 tools are still
changing, so the streams are tied to the AVM version below and may not
decode with other versions.

## Streams

| Source clip | Resolution | QPs |
|---|---|---|
| FourPeople_480x270_60 | 480x270 | 110, 160, 210 |
| Vertical_Bayshore_270x480_2997 | 270x480 (vertical) | 110, 160, 210 |
| BlueSky_360p25_v2 | 360p | 110, 160, 210 |

Each clip is encoded at three quality levels: QP 110 (high), 160
(medium) and 210 (low), from the AV2 Common Test Conditions (CTC) QP
range. Files are named `<clip>_qp<QP>_<frames>f.ivf`; the frame count in
the name is the requested maximum, so shorter source clips contain fewer
frames. 720p and 1080p streams will follow.

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
- **Encoder settings:** `--end-usage=q --qp=<QP> --cpu-used=6`, IVF
  container
- **Script:** `encode_samples.py` does everything: builds AVM, downloads
  the source clips and encodes them in parallel. Run
  `python encode_samples.py --help` for options.
