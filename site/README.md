# Pages site

Source of https://ewouth.github.io/AV2/. `build.py` writes the site to
`_site/` (git-ignored); the `Pages site` workflow builds and deploys it after
each nightly build, daily, and when `site/` or `perf/` changes.

The landing page shows one card per section with a preview; each section
also has its own page. Most of it comes from data, so it updates without
editing the site:

- **Builds:** every release tagged `<tool>-nightly-YYYYMMDD-<commit>` for a
  tool in `TOOLS`, with assets named `<tool>-<platform>.zip`/`.tar.gz`. To
  add a nightly tool, add an entry to `TOOLS`.
- **Sample streams:** every release with a `*manifest.txt` and a
  `sources.tsv` is a sample set; its title and first paragraph come from the
  release. Resolution and frame rate come from each stream's IVF header, bit
  depth from the source clip's `.y4m` header, features from the encoder
  settings in the manifest. Upload new streams (and the updated manifest)
  to a release and they appear on the next build.
- **Results:** the rows of the table in `perf/README.md`. The card image is
  the first figure in each write-up's README.

To add a section, write a class like `Results` (`slug`, `short`, `title`,
`more`, `blurb`, `load()`, `preview()`, `page()`) and add it to `SECTIONS`.

Preview locally:

    python site/build.py
    python -m http.server -d _site
