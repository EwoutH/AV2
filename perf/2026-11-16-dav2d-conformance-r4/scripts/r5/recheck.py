"""Re-decode the round-4 stress failures with newer builds (17 Nov).

  python -I r5/recheck.py <out.jsonl> [--workers 3] [--builds r5,r5-asan,...]
Each row: id, per build (rc, md5 ok, sanitizer site).
"""
import argparse, json, re, sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

W = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(W))
import stress4 as s4  # noqa: E402

B = W / "build"


def site(err):
    m = re.search(r"(\S+\.[ch]:\d+):\d+: runtime error: ([^\n]{0,80})", err)
    if m:
        return f"ubsan {m[1].split('/')[-1]} {m[2]}"
    m = re.search(r"ERROR: AddressSanitizer: (\S+).*?\n(?:.*\n)*?\s+#\d+ 0x\w+ in (\S+) (\S+)", err)
    if m:
        return f"asan {m[1]} {m[2]} {m[3].split('/')[-1]}"
    if "AddressSanitizer" in err or "LeakSanitizer" in err:
        return "asan ?"
    return None


def dec(build, strm, crop, tag, threads="1", fd=None):
    cmd = [B / build / "tools/dav2d", "--threads", threads] + (["--framedelay", fd] if fd else [])
    env = s4.ASAN_ENV if "asan" in build else None
    to = 900 if "asan" in build else 300
    if crop:
        y4m = s4.WORK / f"r5_{tag}_{build}.y4m"
        rc, out, err = s4.run(cmd + ["-q", "--filmgrain", "1", "-i", strm, "-o", y4m], to, env)
        md5 = s4.cropped_md5(y4m, crop) if rc == 0 and y4m.exists() else None
        y4m.unlink(missing_ok=True)
    else:
        rc, out, err = s4.run(cmd + ["-q", "--filmgrain", "1", "-i", strm, "--muxer", "md5",
                                     "-o", "-"], to, env)
        md5 = s4.first_md5(out) if rc == 0 else None
    return rc, md5, site(err), err.strip().splitlines()[-1][:160] if err.strip() else ""


def one(row, builds):
    d = W / "fail" / row["id"]
    strm = next(d.glob("stream.*"))
    fl = row["cfg"]["flags"]
    crop = ([fl[f"--crop-win-{s}-offset"] for s in ("left", "right", "top", "bottom")]
            if fl.get("--enable-cropping-window") else None)
    ref = row["res"]["ref"][1]
    out = dict(id=row["id"], fmt=row["cfg"]["fmt"], verdict=row["verdict"])
    for b in builds:
        rc, md5, s, last = dec(b, strm, crop, row["id"])
        out[b] = dict(rc=rc, ok=md5 == ref, san=s, err=last if (rc != 0 or s) else "")
    mt = [v.split(":")[0] for v in row["verdict"] if v.startswith("mt")]
    if mt:
        m = re.fullmatch(r"mt(\d+)f(\d+)", mt[0])
        oks = [dec("r5", strm, crop, row["id"], m[1], m[2])[1] == ref for _ in range(3)]
        out["r5-mt"] = dict(mode=mt[0], ok_of_3=sum(oks))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--builds", default="r5,r5-asan,r5g,r5g-asan,r5main")
    ap.add_argument("--ids", default=None)
    a = ap.parse_args()
    byid = {}
    for l in open(W / "results.jsonl"):
        r = json.loads(l)
        if r.get("verdict"):
            byid[r["id"]] = r
    rows = [byid[i] for i in sorted(byid) if (W / "fail" / i).exists()]
    if a.ids:
        want = set(a.ids.split(","))
        rows = [r for r in rows if r["id"] in want]
    done = set()
    if Path(a.out).exists():
        done = {json.loads(l)["id"] for l in open(a.out)}
    rows = [r for r in rows if r["id"] not in done]
    builds = a.builds.split(",")
    with open(a.out, "a") as f, ThreadPoolExecutor(a.workers) as ex:
        for res in ex.map(lambda r: one(r, builds), rows):
            f.write(json.dumps(res) + "\n")
            f.flush()


if __name__ == "__main__":
    main()
