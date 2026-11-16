"""Morning triage of the round-4 stress failures.

For every failure: confirm the reference with the av2-normative avmdec, rerun
the failing threaded mode 3x (flaky?), decode with the round-3 main build
(13 Nov) to see whether it is new, and bucket by failure pattern. Then reduce
one stream per bucket (greedy flag drop + fewer frames) until --stop-at.
Writes triage.jsonl and summary.md.

  python -I triage4.py --stop-at 09:00
"""
import argparse, collections, datetime as dt, json, re, subprocess, sys
from pathlib import Path

W = Path(__file__).resolve().parent
sys.path.insert(0, str(W))
import stress4 as s4  # noqa: E402

AVMN = W.parent / "build/avmn/avmdec"
OLD = W.parent / "build/r-main/tools/dav2d"


def md5_of(cmd, env=None, timeout=600):
    rc, out, err = s4.run(cmd, timeout, env)
    return (s4.first_md5(out) if rc == 0 else None), rc, err


def dav_cmd(kind):
    if kind == "asm":
        return [s4.DAV, "--threads", "1"], None
    if kind == "asan":
        return [s4.DAVASAN, "--threads", "1"], s4.ASAN_ENV
    m = re.fullmatch(r"mt(\d+)f(\d+)", kind)
    return [s4.DAV, "--threads", m[1], "--framedelay", m[2]], None


def pattern(verdict):
    kinds = {v.split(":")[0] if not v.split(":")[0].startswith("mt") else "mt": v.split(":")[1]
             for v in verdict}
    if any(k == "sanitizer" for k in kinds.values()):
        return "sanitizer"
    if "asan" in kinds and "asm" in kinds:
        return "c-and-asm"      # parse/C bug (or reference disagreement)
    if "asm" in kinds and "asan" not in kinds:
        return "asm-only"
    if "asan" in kinds and "asm" not in kinds:
        return "c-only"
    return "threading-only"


def chroma_only(strm, tag):
    """#101 pattern: luma exact in every frame, frame 0 exact, chroma differs."""
    import numpy as np
    d, a = s4.WORK / f"{tag}_d.y4m", s4.WORK / f"{tag}_a.yuv"
    try:
        s4.run([s4.DAV, "-q", "--threads", "1", "--filmgrain", "1", "-i", strm, "-o", d], 600)
        s4.run([s4.AVMDEC, strm, "--rawvideo", "-o", a], 600)
        raw = d.read_bytes()
        hdr = raw[:raw.index(b"\n")].split()
        tok = {t[:1].decode(): t[1:].decode() for t in hdr[1:]}
        w, h, c = int(tok["W"]), int(tok["H"]), tok.get("C", "420")
        hbd = "p" in c
        ssx, ssy = {"420": (1, 1), "422": (1, 0), "444": (0, 0)}[c[:3]]
        cw, ch = (w + ssx) >> ssx, (h + ssy) >> ssy
        dtp = np.uint16 if hbd else np.uint8
        fs = w * h + 2 * cw * ch
        frames = [np.frombuffer(f[f.index(b"\n") + 1:], dtp)
                  for f in raw[raw.index(b"\n") + 1:].split(b"FRAME")[1:]]
        ref = np.fromfile(a, dtp)
        if len(frames) * fs != ref.size or not frames:
            return None
        luma_bad, chroma_bad = [], []
        for i, f in enumerate(frames):
            r = ref[i * fs:(i + 1) * fs]
            if f.size != fs:
                return None
            if (f[:w * h] != r[:w * h]).any():
                luma_bad.append(i)
            if (f[w * h:] != r[w * h:]).any():
                chroma_bad.append(i)
        return bool(chroma_bad) and not luma_bad and chroma_bad[0] > 0
    except Exception:
        return None
    finally:
        d.unlink(missing_ok=True)
        a.unlink(missing_ok=True)


def check(row):
    d = W / "fail" / row["id"]
    strm = next(d.glob("stream.*"))
    out = dict(id=row["id"], verdict=row["verdict"], pattern=pattern(row["verdict"]))
    ref = row["res"]["ref"][1]
    out["avmn_agrees"] = md5_of([AVMN, strm, "--rawvideo", "--md5"])[0] == ref
    crop = row["cfg"]["flags"].get("--enable-cropping-window")
    if not crop:
        out["old_main_ok"] = md5_of([OLD, "-q", "--filmgrain", "1", "--threads", "1", "-i", strm,
                                     "--muxer", "md5", "-o", "-"])[0] == ref
    if (out["pattern"] in ("c-and-asm", "asm-only", "c-only") and not crop
            and all(v.endswith(":mismatch") for v in row["verdict"])):
        out["chroma_only"] = chroma_only(strm, row["id"])
    if out["pattern"] == "sanitizer" and row["cfg"]["flags"].get("--enable-fwd-kf"):
        out["fwd_kf"] = True
    mt = [v.split(":")[0] for v in row["verdict"] if v.startswith("mt")]
    if mt and not crop:
        cmd, _ = dav_cmd(mt[0])
        out["mt_ok_of_3"] = sum(md5_of(cmd + ["-q", "--filmgrain", "1", "-i", strm, "--muxer",
                                              "md5", "-o", "-"])[0] == ref for _ in range(3))
    return out


def fails_with(cfg, kinds, tag):
    strm = s4.WORK / f"red_{tag}.{'obu' if cfg.get('obu') else 'ivf'}"
    src = cfg["_srcpath"]
    rc, _, _ = s4.run(s4.enc_cmd(cfg, src, strm), 1800)
    if rc != 0:
        return False
    try:
        ref = md5_of([s4.AVMDEC, strm, "--rawvideo", "--md5"])[0]
        if not ref:
            return False
        for k in kinds:
            cmd, env = dav_cmd(k)
            md5, rc, err = md5_of(cmd + ["-q", "--filmgrain", "1", "-i", strm, "--muxer", "md5",
                                         "-o", "-"], env)
            bad = md5 != ref or re.search(r"runtime error:|AddressSanitizer", err)
            if bad:
                return True
        return False
    finally:
        strm.unlink(missing_ok=True)


def reduce(row, stop_dt):
    cfg = json.loads(json.dumps(row["cfg"]))
    d = W / "fail" / row["id"]
    cfg["_srcpath"] = str(d / "src.y4m") if (d / "src.y4m").exists() else \
        s4.sources()[cfg["src"]]["path"]
    kinds = sorted({v.split(":")[0] for v in row["verdict"]})
    tag = row["id"]
    if not fails_with(cfg, kinds, tag):
        return dict(id=tag, reduced=None, note="does not reproduce")
    if cfg.get("obu") and (c := dict(cfg, obu=False)) and fails_with(c, kinds, tag):
        cfg = c
    for k in list(cfg["flags"]):
        if dt.datetime.now() >= stop_dt:
            break
        t = dict(cfg, flags={a: b for a, b in cfg["flags"].items() if a != k})
        if fails_with(t, kinds, tag):
            cfg = t
    for f in (1, 2, 3, 4, 6, 8, 12):
        if f < cfg["frames"] and fails_with(dict(cfg, frames=f), kinds, tag):
            cfg["frames"] = f
            break
    cmd = s4.enc_cmd(cfg, cfg["_srcpath"], "out.ivf")
    return dict(id=tag, reduced=" ".join(cmd[3:]), src=cfg["_srcpath"], kinds=kinds)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stop-at", default="09:00")
    ap.add_argument("--max-reduce", type=int, default=15)
    a = ap.parse_args()
    h, m = map(int, a.stop_at.split(":"))
    now = dt.datetime.now()
    stop_dt = now.replace(hour=h, minute=m, second=0)
    if stop_dt <= now:
        stop_dt += dt.timedelta(days=1)
    rows = [json.loads(l) for l in open(W / "results.jsonl")]
    fails = [r for r in rows if r.get("verdict")]
    tri = []
    with open(W / "triage.jsonl", "w") as f:
        for r in fails:
            t = check(r)
            tri.append(t)
            f.write(json.dumps(t) + "\n")
            f.flush()
            print(t, flush=True)
    byid = {}
    for r in rows:  # attempt 1 and the restart share ids v000019..; keep the failing row
        if r["id"] not in byid or r.get("verdict"):
            byid[r["id"]] = r
    buckets = collections.defaultdict(list)
    for t in tri:
        if not t["avmn_agrees"]:
            buckets["reference-disagreement"].append(t["id"])
            continue
        if t.get("mt_ok_of_3", 0) == 3 and t["pattern"] == "threading-only":
            buckets["threading-flaky"].append(t["id"])
            continue
        cfg = byid[t["id"]]["cfg"]
        if t.get("chroma_only") and cfg["fmt"] != "420":
            buckets["known: #101-like (luma exact, chroma on inter frames)"].append(t["id"])
            continue
        if t.get("fwd_kf"):
            buckets["known?: sanitizer with fwd-kf (OLK refs)"].append(t["id"])
            continue
        key = (t["pattern"], cfg["fmt"], "12bit" if cfg["flags"].get("--bit-depth") == 12 else "",
               "crop" if cfg["flags"].get("--enable-cropping-window") else "",
               "obu" if cfg.get("obu") else "", cfg.get("rc", "q"))
        buckets[" ".join(x for x in key if x)].append(t["id"])
    reds = []
    with open(W / "reduce.jsonl", "a") as f:
        for key, ids in sorted(buckets.items(), key=lambda kv: (kv[0].startswith("known"), -len(kv[1]))):
            if len(reds) >= a.max_reduce or dt.datetime.now() >= stop_dt:
                break
            if key in ("reference-disagreement", "threading-flaky") or key.startswith("known: #101"):
                continue
            ids = sorted(ids, key=lambda i: byid[i]["cfg"]["frames"] * len(byid[i]["cfg"]["flags"]))
            r = reduce(byid[ids[0]], stop_dt)
            r["bucket"] = key
            reds.append(r)
            f.write(json.dumps(r) + "\n")
            f.flush()
            print(r, flush=True)
    enc = collections.Counter("encfail" if r.get("enc_rc") not in (0, None) else "refbad"
                              if r.get("verdict") is None else "ok" if r["verdict"] == [] else
                              "fail" for r in rows)
    lines = [f"# Round 4 stress summary ({dt.datetime.now():%Y-%m-%d %H:%M})", "",
             f"Configs: {len(rows)}; " + ", ".join(f"{k} {v}" for k, v in enc.most_common()), "",
             "## Buckets", ""]
    for key, ids in sorted(buckets.items(), key=lambda kv: -len(kv[1])):
        new = sum(1 for t in tri if t["id"] in ids and t.get("old_main_ok"))
        lines.append(f"- **{key}**: {len(ids)} ({new} pass on the 13 Nov main): {' '.join(ids[:12])}")
    lines += ["", "## Reductions", ""]
    for r in reds:
        lines.append(f"- {r['bucket']}: {r['id']} -> `{r.get('reduced')}` {r.get('note', '')}")
    (W / "summary.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
