# AV2 sample streams

AV2 test streams, encoded with the AVM reference encoder, for testing and
benchmarking AV2 decoders (such as dav2d). The streams themselves are on
the releases page; this folder has the scripts that made them.

These are **not official conformance streams**. AV2 tools are still
changing, so each set is tied to the AVM version it was made with and may
not decode with other versions.

## Downloads

Browse and filter all streams on https://ewouth.github.io/AV2/samples/, or
download them from the releases:

- **[samples-v1](https://github.com/EwoutH/AV2/releases/tag/samples-v1):**
  16 short streams, 270p to 1080p, 73 to 240 frames.
- **[hd-streams-2026-10](https://github.com/EwoutH/AV2/releases/tag/hd-streams-2026-10):**
  720p and 1080p streams of up to 600 frames, many for specific coding
  tools. This is a snapshot; more streams are added as they finish.

Each release has a manifest with the MD5 of each stream's decoded output,
as reported by the reference decoder (`avmdec --md5`), and a `sources.tsv`
linking each stream to its source clip. Use the MD5s to check another
decoder's output.

Files are named `<clip>_qp<QP>_<frames>f.ivf`, where `<frames>` is the
number of frames the stream decodes to. Streams for a specific coding tool
have the tool in the name, for example `_screen` or `_filmgrain`.

The source clips are the AV2 Common Test Conditions (CTC) set on
https://media.xiph.org/video/aomctc/.

## samples-v1

- **Encoder:** AVM (https://github.com/AOMediaCodec/avm) at commit
  `01803db6afa5a0616702a3814fc5934ab9e99adf`, built on Windows with MSVC.
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
  container. The low-res clips are at QP 110, 160 and 210 (the CTC Random
  Access range, high to low quality), the 720p and 1080p clips at QP 160.
- **Length:** the low-res streams are 130 frames, the whole clip. The 720p
  and 1080p encodes were interrupted, so those streams are the frames
  written before that (73 to 240), which decode without errors.
- **Script:** `encode_samples.py` does everything: builds AVM, downloads
  the source clips and encodes them in parallel. Run
  `python encode_samples.py --help` for options.

## hd-streams-2026-10

- **Encoder:** AVM `av2-enc` commit `9c72cb56a7814da244eadbe48019844f491d6b8c`,
  same build flags as above.
- **Encoder settings:** `--end-usage=q --qp=135` (`--qp=110` for some),
  `--cpu-used=6`, one thread per encode. Streams for specific coding tools
  (screen content tuning, film grain, global motion, HDR10, tiles) add the
  tool's options and are named after the tool.
- **Length:** up to 600 frames per stream.
- **Script:** `encode_long.py`, which runs a queue of encodes over several
  nights and checks each stream with `avmdec --md5` when it finishes.
- The release's `hd-manifest.txt` gives the MD5, encoder settings, encode
  time and peak memory for each stream.
