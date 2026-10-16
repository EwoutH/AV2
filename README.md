# AV2 experiments
Some personal experiments with AV2. Everything below is also on
https://ewouth.github.io/AV2/ (built from [site](site)).

- **Nightly builds:** ready-to-run builds of AVM, the AV2 reference encoder
  and decoder, for Windows, macOS and Linux. Download them from
  https://ewouth.github.io/AV2/builds/ or the
  [releases](https://github.com/EwoutH/AV2/releases). They are unofficial and
  built by the [AVM nightly builds](.github/workflows/avm-nightly.yml)
  workflow.
- **Sample streams:** AV2 test streams with the MD5 of their decoded
  output. Browse them on https://ewouth.github.io/AV2/samples/ or download
  them from the releases
  ([samples-v1](https://github.com/EwoutH/AV2/releases/tag/samples-v1),
  [hd-streams-2026-10](https://github.com/EwoutH/AV2/releases/tag/hd-streams-2026-10)).
  The scripts that made them are in [samples](samples).
- **Performance:** encoder speed and compression measurements are in
  [perf](perf), starting with a
  [sweep of the AVM encoder presets](perf/2026-10-14-avm-preset-sweep/).
