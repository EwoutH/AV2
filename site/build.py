"""Build the GitHub Pages site (https://ewouth.github.io/AV2/).

The site has a landing page with one preview per section, and a full page
per section. Sections are listed in SECTIONS at the bottom; to add one,
write a class with the same methods and add it there.

Data comes from this repository's GitHub releases (nightly builds, sample
stream sets) and from perf/ (benchmark write-ups), so new nightly tools,
new sample releases and new streams in an existing release show up the
next time the site is built. Python standard library only.

    python site/build.py [--out _site]

Set GITHUB_TOKEN (or GH_TOKEN) to avoid the API's anonymous rate limit.
"""

import argparse
import datetime as dt
import html
import json
import os
import re
import shutil
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

REPO = "EwoutH/AV2"
REPO_URL = f"https://github.com/{REPO}"
ROOT = Path(__file__).resolve().parent.parent
STATIC = Path(__file__).resolve().parent / "static"

esc = html.escape


# --- Fetching ---------------------------------------------------------------

def _request(url, headers=None):
    headers = dict(headers or {})
    headers.setdefault("User-Agent", f"{REPO}-site-builder")
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token and url.startswith("https://api.github.com/"):
        headers["Authorization"] = f"Bearer {token}"
    return urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=60)


def api_all(path):
    """All items of a paginated GitHub API list."""
    url, items = f"https://api.github.com/{path}?per_page=100", []
    while url:
        with _request(url, {"Accept": "application/vnd.github+json"}) as r:
            items += json.load(r)
            m = re.search(r'<([^>]+)>;\s*rel="next"', r.headers.get("Link", ""))
            url = m.group(1) if m else None
    return items


def fetch_text(url):
    with _request(url) as r:
        return r.read().decode("utf-8")


def fetch_head(url, n):
    """The first n bytes of a file, or None if it can't be fetched."""
    try:
        with _request(url, {"Range": f"bytes=0-{n - 1}"}) as r:
            return r.read(n)
    except OSError:
        return None


# --- Formatting -------------------------------------------------------------

def fmt_date(iso):
    d = dt.date.fromisoformat(iso[:10])
    return f"{d.day} {d:%b %Y}"


def fmt_size(n):
    if n >= 1e9:
        return f"{n / 1e9:.1f} GB"
    if n >= 1e6:
        return f"{n / 1e6:.1f} MB"
    return f"{n / 1e3:.0f} kB"


def fmt_fps(fps):
    return f"{fps:.2f}".rstrip("0").rstrip(".")


def first_paragraph(markdown):
    """The first paragraph of a release body, as plain-ish HTML."""
    para = markdown.strip().split("\n\n")[0].replace("\n", " ")
    para = esc(para)
    para = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", para)
    para = re.sub(r"`(.+?)`", r"<code>\1</code>", para)
    return re.sub(r"\[(.+?)\]\((https?://[^)]+)\)", r'<a href="\2">\1</a>', para)


def page(title, description, body, sections, current=None, depth=0, wide=False):
    up = "../" * depth
    nav = "".join(
        f'<a href="{up}{s.slug}/"{" aria-current=page" if s.slug == current else ""}>{esc(s.short)}</a>'
        for s in sections)
    full_title = "AV2 tools and tests" if current is None else f"{title} · AV2 tools and tests"
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(full_title)}</title>
<meta name="description" content="{esc(description)}">
<link rel="stylesheet" href="{up}style.css">
</head>
<body>
<header class="site"><div class="bar{' wide' if wide else ''}">
  <a class="home" href="{up or './'}">AV2 tools and tests</a>
  <nav>{nav}</nav>
</div></header>
<main{' class="wide"' if wide else ''}>
{body}
</main>
<footer><div class="bar{' wide' if wide else ''}">
  Unofficial, not from the Alliance for Open Media. Built from
  <a href="{REPO_URL}">{REPO}</a> on {fmt_date(dt.datetime.now(dt.timezone.utc).isoformat())}.
</div></footer>
<script src="{up}site.js"></script>
</body>
</html>
"""


def section_card(s, preview):
    return f"""<section class="card" id="{s.slug}">
  <div class="card-head">
    <h2><a href="{s.slug}/">{esc(s.title)}</a></h2>
    <a class="more" href="{s.slug}/">{esc(s.more)} &rarr;</a>
  </div>
  <p class="blurb">{s.blurb}</p>
  {preview}
</section>"""


# --- Builds -----------------------------------------------------------------

# Platforms in display order: (asset suffix, label, detail).
PLATFORMS = [
    ("windows-x64", "Windows", "x64"),
    ("macos-arm64", "macOS", "Apple Silicon"),
    ("macos-x64", "macOS", "Intel"),
    ("linux-x64", "Linux", "x64"),
    ("linux-arm64", "Linux", "ARM"),
]

# Nightly tools. Releases are tagged <tag>-nightly-YYYYMMDD-<commit>, with
# assets named <tag>-<platform>.zip or .tar.gz.
TOOLS = [
    {
        "tag": "avm",
        "name": "AVM",
        "role": "Reference encoder and decoder",
        "about": """The AV2 reference software from the Alliance for Open Media:
            the encoder <code>avmenc</code> and decoder <code>avmdec</code>. Built
            from the <a href="https://github.com/AOMediaCodec/avm/tree/av2-enc"><code>av2-enc</code></a>
            branch, whose encoder is 4 to 5 times faster than <code>main</code>'s at
            the same <code>--cpu-used</code> with about the same quality; its
            streams decode with <code>main</code>'s avmdec.""",
        "commit_url": "https://github.com/AOMediaCodec/avm/commit/{}",
        "usage": """ffmpeg -i input.mp4 -pix_fmt yuv420p -frames:v 30 input.y4m
avmenc input.y4m -o output.ivf --ivf --end-usage=q --qp=160 --cpu-used=6
avmdec output.ivf -o decoded.y4m""",
        "notes": """<li><code>--qp</code> sets quality: lower is better and larger.
            The AV2 test conditions use 110 to 235.</li>
            <li><code>--cpu-used</code> sets speed, 0 (slowest, and the default) to 9.
            6 is the fastest in practice, see the
            <a href="../results/">results</a>. AVM is research software and slow at
            any setting: expect seconds per frame, or minutes for HD.</li>
            <li>TensorFlow Lite and the two encoder experiments that need it are
            turned off, so all platforms use the same encoder configuration.</li>
            <li>Licensed under the BSD 3-Clause Clear License and the AOM Patent
            License; both are in each download.</li>""",
    },
    {
        "tag": "dav2d",
        "name": "dav2d",
        "role": "Decoder (C) from VideoLAN",
        "about": """An independent AV2 decoder by VideoLAN, a sibling of dav1d.
            Source: <a href="https://code.videolan.org/videolan/dav2d">code.videolan.org/videolan/dav2d</a>.""",
        "commit_url": "https://code.videolan.org/videolan/dav2d/-/commit/{}",
        "usage": "dav2d -i input.ivf -o decoded.y4m",
        "notes": """<li>Each build decodes one of the <a href="../samples/">sample
            streams</a> and compares the output with avmdec. The result is in the
            release notes and <code>BUILD_INFO.txt</code>.</li>
            <li>BSD 2-Clause licensed; the licence is in each download.</li>""",
    },
    {
        "tag": "rav2d",
        "name": "rav2d",
        "role": "Decoder (Rust)",
        "about": """An independent AV2 decoder written in Rust.
            Source: <a href="https://github.com/stukenov/rav2d">github.com/stukenov/rav2d</a>.""",
        "commit_url": None,
        "usage": "rav2d input.ivf -o decoded.y4m",
        "notes": """<li>Each build decodes one of the <a href="../samples/">sample
            streams</a> and compares the output with avmdec. The result is in the
            release notes and <code>BUILD_INFO.txt</code>.</li>
            <li>BSD 2-Clause licensed; the licence is in each download.</li>""",
    },
]


class Builds:
    slug, short, title, more = "builds", "Builds", "Nightly builds", "All builds"
    blurb = """Ready-to-run AV2 encoders and decoders for Windows, macOS and
        Linux, rebuilt whenever their source changes. No compiler needed."""

    def load(self, releases):
        self.tools = []
        for tool in TOOLS:
            rx = re.compile(rf"^{tool['tag']}-nightly-(\d{{8}})-([0-9a-f]+)$")
            rels = [r for r in releases if rx.match(r["tag_name"])]
            rels.sort(key=lambda r: r["tag_name"], reverse=True)
            if not rels:
                continue
            builds = []
            for r in rels:
                date, commit = rx.match(r["tag_name"]).groups()
                assets = {a["name"]: a for a in r["assets"]}
                downloads = []
                for plat, label, detail in PLATFORMS:
                    for ext in (".zip", ".tar.gz"):
                        a = assets.get(f"{tool['tag']}-{plat}{ext}")
                        if a:
                            downloads.append((plat, label, detail, ext, a))
                builds.append({"date": f"{date[:4]}-{date[4:6]}-{date[6:]}",
                               "commit": commit, "url": r["html_url"],
                               "downloads": downloads})
            self.tools.append({**tool, "builds": builds})

    def _commit(self, tool, commit):
        if tool["commit_url"]:
            return f'<a href="{tool["commit_url"].format(commit)}"><code>{commit}</code></a>'
        return f"<code>{commit}</code>"

    def _platform_links(self, downloads, compact):
        out = []
        for plat, label, detail, ext, a in downloads:
            if compact:
                out.append(f'<a class="chip" data-os="{plat}" href="{a["browser_download_url"]}">'
                           f'{label} <span>{detail}</span></a>')
            else:
                out.append(f'<a class="dl" data-os="{plat}" href="{a["browser_download_url"]}">'
                           f'<strong>{label}</strong><span>{detail} &middot; {ext[1:]} &middot; '
                           f'{fmt_size(a["size"])}</span></a>')
        return "".join(out)

    def preview(self):
        rows = []
        for t in self.tools:
            b = t["builds"][0]
            rows.append(f"""<div class="tool">
    <div class="tool-name"><strong><a href="{self.slug}/#{t['tag']}">{esc(t['name'])}</a></strong>
      <span>{esc(t['role'])}</span></div>
    <div class="tool-ver">{fmt_date(b['date'])} &middot; {self._commit(t, b['commit'])}</div>
    <div class="chips">{self._platform_links(b['downloads'], compact=True)}</div>
  </div>""")
        return f'<div class="tools">{"".join(rows)}</div>'

    def page(self):
        parts = [f"""<h1>{self.title}</h1>
<p class="lead">{self.blurb} Downloads for your computer are highlighted.</p>
<p class="toc">{' &middot; '.join(f'<a href="#{t["tag"]}">{esc(t["name"])}</a>' for t in self.tools)}
 &middot; <a href="#known">Good to know</a></p>"""]
        for t in self.tools:
            latest = t["builds"][0]
            history = "".join(
                f'<li><a href="{b["url"]}">{fmt_date(b["date"])}</a> &middot; {self._commit(t, b["commit"])}</li>'
                for b in t["builds"][1:6])
            parts.append(f"""<section id="{t['tag']}">
  <h2>{esc(t['name'])} <span class="sub">{esc(t['role'])}</span></h2>
  <p>{t['about']}</p>
  <p class="status">Latest build: <a href="{latest['url']}">{fmt_date(latest['date'])}</a>,
    commit {self._commit(t, latest['commit'])}</p>
  <div class="downloads">{self._platform_links(latest['downloads'], compact=False)}</div>
  <pre>{esc(t['usage'])}</pre>
  <ul>{t['notes']}</ul>
  {f'<details><summary>Earlier builds</summary><ul class="history">{history}</ul>'
   f'<p><a href="{REPO_URL}/releases?q={t["tag"]}-nightly&amp;expanded=true">All {esc(t["name"])} builds</a></p></details>'
   if history else ''}
</section>""")
        parts.append("""<section id="known">
  <h2>Good to know</h2>
  <ul>
    <li>These builds are unofficial and not from the Alliance for Open Media.</li>
    <li>AV2 is still changing. A stream made with one build may not decode with
    another, so note the commit in <code>BUILD_INFO.txt</code>.</li>
    <li>The tools read and write <code>.y4m</code> video;
    <a href="https://ffmpeg.org/">FFmpeg</a> converts from almost any file.</li>
    <li>On macOS, downloaded tools are blocked at first. Allow them with
    <code>xattr -d com.apple.quarantine &lt;tool&gt;</code>.</li>
  </ul>
</section>""")
        return "\n".join(parts)


# --- Sample streams -----------------------------------------------------------

# Tags shown on the samples page, in filter order: (id, label).
TAGS = [
    ("10bit", "10-bit"), ("hdr10", "HDR10"), ("screen", "Screen content"),
    ("filmgrain", "Film grain"), ("globalmotion", "Global motion"),
    ("tiles", "Tiles"), ("vertical", "Vertical"),
]
TAG_LABEL = dict(TAGS)


def parse_manifest(text):
    """Header comments as {key: value}, and rows as dicts keyed by column."""
    meta, columns, rows = {}, None, []
    for line in text.splitlines():
        if line.startswith("# file\t"):
            columns = line[2:].split("\t")
        elif line.startswith("#"):
            key, _, value = line[1:].partition(":")
            meta[key.strip()] = value.strip()
        elif line.strip() and columns:
            rows.append(dict(zip(columns, line.split("\t"))))
    return meta, rows


def parse_sources(text):
    out = {}
    for line in text.splitlines():
        if line.strip() and not line.startswith("#"):
            key, url = line.split("\t")[:2]
            out[key] = url
    return out


def parse_ivf(head):
    if not head or head[:4] != b"DKIF":
        return None
    le = lambda a, b: int.from_bytes(head[a:b], "little")
    num, den = le(16, 20), le(20, 24)
    return {"w": le(12, 14), "h": le(14, 16), "fps": num / den if den else None}


def parse_y4m_bitdepth(head):
    """Bit depth from a .y4m header (8 when it has no C tag)."""
    if not head or not head.startswith(b"YUV4MPEG2"):
        return None
    m = re.search(rb" C\S*?p(\d+)", head.split(b"\n")[0])
    return int(m.group(1)) if m else 8


class Samples:
    slug, short, title, more = "samples", "Sample streams", "Sample streams", "Browse all streams"
    blurb = """AV2 test streams encoded with AVM from the AV2 test clips, with
        the MD5 of each decoded stream to check a decoder against."""

    def load(self, releases):
        # A sample set is any release with a *manifest.txt and a sources.tsv.
        self.sets = []
        for r in sorted(releases, key=lambda r: r["published_at"] or ""):
            assets = {a["name"]: a for a in r["assets"]}
            manifest = next((a for n, a in assets.items() if n.endswith("manifest.txt")), None)
            if "nightly" in r["tag_name"] or not manifest or "sources.tsv" not in assets:
                continue
            meta, rows = parse_manifest(fetch_text(manifest["browser_download_url"]))
            sources = parse_sources(fetch_text(assets["sources.tsv"]["browser_download_url"]))
            streams = []
            for row in rows:
                a = assets.get(row["file"])
                if not a:
                    continue
                name = row["file"]
                m = re.search(r"_qp(\d+)_(\d+)f\.ivf$", name)
                # sources.tsv is keyed by stream, or by clip (stream name prefix).
                source = sources.get(name) or next(
                    (u for k, u in sources.items() if name.startswith(k + "_")), None)
                streams.append({
                    "file": name, "url": a["browser_download_url"], "bytes": a["size"],
                    "md5": next((v for k, v in row.items() if k.startswith("md5")), ""),
                    "settings": row.get("encoder settings") or meta.get("Encoder settings", ""),
                    "qp": int(m.group(1)) if m else None,
                    "frames": int(m.group(2)) if m else None,
                    "source": source,
                })
            self.sets.append({"tag": r["tag_name"], "name": r["name"], "url": r["html_url"],
                              "about": first_paragraph(r["body"] or ""),
                              "published": r["published_at"],
                              "avm": meta.get("AVM commit", ""), "streams": streams})

        # Resolution and frame rate from each stream's IVF header, bit depth
        # from the source clip's .y4m header.
        all_streams = [s for st in self.sets for s in st["streams"]]
        source_urls = sorted({s["source"] for s in all_streams if s["source"]})
        with ThreadPoolExecutor(16) as pool:
            ivf = dict(zip([s["url"] for s in all_streams],
                           pool.map(lambda s: parse_ivf(fetch_head(s["url"], 32)), all_streams)))
            depth = dict(zip(source_urls,
                             pool.map(lambda u: parse_y4m_bitdepth(fetch_head(u, 256)), source_urls)))
        for s in all_streams:
            s.update(ivf.get(s["url"]) or {"w": None, "h": None, "fps": None})
            s["bitdepth"] = depth.get(s["source"])
            if s["bitdepth"] is None:
                s["bitdepth"] = 10 if re.search(r"10bit|hdr10", s["file"], re.I) else None
            s["tags"] = self._tags(s)

    @staticmethod
    def _tags(s):
        tags, st, name = [], s["settings"], s["file"].lower()
        if s["bitdepth"] and s["bitdepth"] > 8:
            tags.append("10bit")
        if "smpte2084" in st or "_hdr10" in name:
            tags.append("hdr10")
        if "--tune-content=screen" in st or "_screen_" in name:
            tags.append("screen")
        if "--denoise-noise-level" in st or "filmgrain" in name:
            tags.append("filmgrain")
        if "--enable-global-motion=1" in st or "globalmotion" in name:
            tags.append("globalmotion")
        if "--tile-columns" in st or "--tile-rows" in st:
            tags.append("tiles")
        if s["w"] and s["h"] and s["h"] > s["w"]:
            tags.append("vertical")
        return tags

    def _all(self):
        return [s for st in self.sets for s in st["streams"]]

    def _tag_counts(self):
        streams = self._all()
        return [(t, label, sum(t in s["tags"] for s in streams)) for t, label in TAGS
                if any(t in s["tags"] for s in streams)]

    def _clip(self, s):
        return re.sub(r"_qp\d+_\d+f\.ivf$", "", s["file"])

    def preview(self):
        streams = self._all()
        clips = {s["source"] or self._clip(s) for s in streams}
        heights = [min(s["w"], s["h"]) for s in streams if s["w"]]
        frames = [s["frames"] for s in streams if s["frames"]]
        stats = [
            (str(len(streams)), "streams"),
            (str(len(clips)), "source clips"),
            (f"{min(heights)}p&ndash;{max(heights)}p" if heights else "&ndash;", "resolutions"),
            (f"up to {max(frames)}" if frames else "&ndash;", "frames per stream"),
        ]
        tiles = "".join(f'<div class="stat"><strong>{v}</strong><span>{k}</span></div>' for v, k in stats)
        chips = "".join(f'<a class="chip" href="{self.slug}/#{t}">{esc(label)} <span>{n}</span></a>'
                        for t, label, n in self._tag_counts())
        sets = "".join(f'<li><a href="{self.slug}/#{esc(st["tag"])}">{esc(st["name"])}</a>'
                       f' &middot; {len(st["streams"])} streams, {fmt_size(sum(s["bytes"] for s in st["streams"]))}</li>'
                       for st in reversed(self.sets))
        return f"""<div class="stats">{tiles}</div>
  <p class="chips-label">Streams with</p>
  <div class="chips">{chips}</div>
  <ul class="sets">{sets}</ul>"""

    def _row(self, s):
        res = f'{s["w"]}&times;{s["h"]}' if s["w"] else "?"
        fps = f'{fmt_fps(s["fps"])}' if s["fps"] else "?"
        tags = "".join(f'<span class="tag">{esc(TAG_LABEL[t])}</span>' for t in s["tags"])
        extra = re.sub(r"--end-usage=q --qp=\d+ --cpu-used=\d+( --threads=1)?", "", s["settings"]).strip()
        source = f'<a href="{s["source"]}">.y4m</a>' if s["source"] else ""
        search = " ".join([s["file"], res.replace("&times;", "x"), " ".join(TAG_LABEL[t] for t in s["tags"])])
        return f"""<tr data-tags="{' '.join(s['tags'])}" data-search="{esc(search.lower())}">
  <td class="name"><a href="{s['url']}" download>{esc(self._clip(s))}</a>{f'<small>{esc(extra)}</small>' if extra else ''}</td>
  <td class="num">{res}</td><td class="num">{fps}</td><td class="num">{s['frames'] or '?'}</td>
  <td class="num">{s['qp'] or '?'}</td><td>{tags}</td><td class="num">{fmt_size(s['bytes'])}</td>
  <td>{source}</td><td><code class="md5">{s['md5']}</code></td>
</tr>"""

    def page(self):
        chips = "".join(f'<button class="chip" data-filter="{t}" aria-pressed="false">{esc(label)} <span>{n}</span></button>'
                        for t, label, n in self._tag_counts())
        parts = [f"""<h1>{self.title}</h1>
<p class="lead">{self.blurb}</p>
<p>These are not official conformance streams. AV2 is still changing, so each set
only decodes with AVM versions close to the commit it was made with. Every
stream was decoded with <code>avmdec --md5</code> after encoding; the MD5 below
is of the decoded output, so a decoder that writes the same MD5 decodes the
stream exactly. Click a stream name to download it.</p>
<pre>avmdec --md5 stream.ivf</pre>
<div class="filter">
  <input type="search" id="q" placeholder="Filter by name, e.g. 1080 or Netflix" aria-label="Filter streams">
  <div class="chips">{chips}</div>
</div>"""]
        for st in reversed(self.sets):
            rows = "".join(self._row(s) for s in sorted(st["streams"], key=lambda s: s["file"].lower()))
            avm = (f'<a href="https://github.com/AOMediaCodec/avm/commit/{st["avm"]}"><code>{st["avm"][:10]}</code></a>'
                   if st["avm"] else "unknown")
            parts.append(f"""<section id="{esc(st['tag'])}" class="set">
  <h2>{esc(st['name'])}</h2>
  <p>{st['about']}</p>
  <p class="status">{len(st['streams'])} streams, {fmt_size(sum(s['bytes'] for s in st['streams']))},
    AVM commit {avm}. <a href="{st['url']}">Release with manifest and source list</a></p>
  <div class="table-wrap"><table>
    <thead><tr><th>Stream</th><th class="num">Size (px)</th><th class="num">fps</th><th class="num">Frames</th>
      <th class="num">QP</th><th>Features</th><th class="num">File</th><th>Source</th><th>MD5 of decoded output</th></tr></thead>
    <tbody>{rows}</tbody>
  </table></div>
  <p class="empty" hidden>No streams in this set match the filter.</p>
</section>""")
        parts.append(f"""<section>
  <h2>How they were made</h2>
  <p>The source clips are the AV2 Common Test Conditions set on
  <a href="https://media.xiph.org/video/aomctc/">media.xiph.org</a>. Streams are
  named <code>&lt;clip&gt;_qp&lt;QP&gt;_&lt;frames&gt;f.ivf</code>, where frames
  is the number of frames the stream decodes to. Encoder versions, build flags
  and scripts are described in
  <a href="{REPO_URL}/tree/main/samples">samples/</a>.</p>
</section>""")
        return "\n".join(parts)


# --- Results ----------------------------------------------------------------

class Results:
    slug, short, title, more = "results", "Results", "Results", "All results"
    blurb = """Measurements of AV2 encoders and decoders: speed, compression
        and how to get the most out of a machine. Each comes with its raw data
        and scripts."""

    def load(self, releases):
        self.items = []
        index = (ROOT / "perf" / "README.md").read_text(encoding="utf-8")
        for line in index.splitlines():
            m = re.match(r"\|\s*(\d{4}-\d{2}-\d{2})\s*\|\s*\[(.+?)\]\((.+?)/?\)\s*\|(.+?)\|(.+?)\|\s*$", line)
            if not m:
                continue
            date, title, folder, encoder, summary = (g.strip() for g in m.groups())
            readme = (ROOT / "perf" / folder / "README.md").read_text(encoding="utf-8")
            fig = re.search(r"!\[(.*?)\]\((.+?\.(?:svg|png))\)", readme)
            self.items.append({
                "date": date, "title": title, "folder": folder,
                "encoder": encoder, "summary": summary,
                "url": f"{REPO_URL}/tree/main/perf/{folder}",
                "figure": (ROOT / "perf" / folder / fig.group(2)) if fig else None,
                "figure_alt": fig.group(1) if fig else "",
            })
        self.items.sort(key=lambda i: i["date"], reverse=True)

    @staticmethod
    def _md(text):
        text = esc(text)
        text = re.sub(r"`(.+?)`", r"<code>\1</code>", text)
        return re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)

    def _card(self, i, prefix):
        img = (f'<img src="{prefix}{i["folder"]}{i["figure"].suffix}" alt="{esc(i["figure_alt"])}" loading="lazy">'
               if i["figure"] else "")
        return f"""<a class="result" href="{i['url']}">
  <div class="fig">{img}</div>
  <div class="result-text"><span class="date">{fmt_date(i['date'])} &middot; {self._md(i['encoder'])}</span>
  <strong>{esc(i['title'])}</strong>
  <p>{self._md(i['summary'])}</p></div>
</a>"""

    def preview(self):
        return f'<div class="results">{"".join(self._card(i, self.slug + "/") for i in self.items[:3])}</div>'

    def page(self):
        return f"""<h1>{self.title}</h1>
<p class="lead">{self.blurb} Each links to its full write-up on GitHub.</p>
<div class="results">{"".join(self._card(i, "") for i in self.items)}</div>"""

    def write_assets(self, out):
        for i in self.items:
            if i["figure"]:
                shutil.copy(i["figure"], out / self.slug / f'{i["folder"]}{i["figure"].suffix}')


# --- Site ---------------------------------------------------------------------

SECTIONS = [Builds(), Samples(), Results()]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=str(ROOT / "_site"), help="output folder (default: _site)")
    args = ap.parse_args()
    out = Path(args.out)
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)

    releases = [r for r in api_all(f"repos/{REPO}/releases") if not r["draft"]]
    for s in SECTIONS:
        s.load(releases)

    cards = "\n".join(section_card(s, s.preview()) for s in SECTIONS)
    intro = f"""<h1>AV2 tools and tests</h1>
<p class="lead">Unofficial builds, test streams and measurements for AV2, the
next video codec from the Alliance for Open Media. Everything is free to download
and comes from one repository, <a href="{REPO_URL}">{REPO}</a>.</p>"""
    (out / "index.html").write_text(page(
        "AV2 tools and tests",
        "Unofficial nightly builds of AV2 encoders and decoders, AV2 sample streams, and AV2 encoder benchmarks.",
        intro + "\n" + cards, SECTIONS), encoding="utf-8")

    for s in SECTIONS:
        (out / s.slug).mkdir()
        (out / s.slug / "index.html").write_text(page(
            s.title, re.sub(r"\s+", " ", s.blurb).strip(), s.page(), SECTIONS,
            current=s.slug, depth=1, wide=isinstance(s, Samples)), encoding="utf-8")
        if hasattr(s, "write_assets"):
            s.write_assets(out)

    for f in STATIC.iterdir():
        shutil.copy(f, out / f.name)
    (out / ".nojekyll").write_text("")
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
