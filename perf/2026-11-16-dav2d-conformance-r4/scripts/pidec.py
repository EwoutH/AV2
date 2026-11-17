"""Decode a manifest of streams on the pi with the Neon and C builds (at most 2 threads in total).

  python3 pidec.py manifest.json corpus_dir out.jsonl
Modes: neon 1t and c 1t run 3 streams at a time (owner: 3 threads, 17 Nov); neon mt2 (2 threads, framedelay 2) runs one.
Each row: stream, mode, md5, ok (vs ref), same_as_pc (vs the pc main md5 of the same mode).
"""
import json, re, subprocess, sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
B = Path(__file__).resolve().parent / "bin"
MODES = {"neon1t": ([B / "dav2d", "--threads", "1"], 3, "pc1t"),
         "c1t": ([B / "dav2d_noasm", "--threads", "1"], 3, "pcc"),
         "neonmt2": ([B / "dav2d", "--threads", "2", "--framedelay", "2"], 1, "pcmt4")}
man, cdir, out = json.load(open(sys.argv[1])), Path(sys.argv[2]), sys.argv[3]
done = set()
if Path(out).exists():
    done = {(r["stream"], r["mode"]) for r in map(json.loads, open(out))}


def one(job):
    m, e = job
    cmd, _, pck = MODES[m]
    try:
        p = subprocess.run([str(c) for c in cmd] + ["-q", "--filmgrain", "1", "-i", str(cdir / e["name"]),
                                                     "--muxer", "md5", "-o", "-"],
                           capture_output=True, text=True, timeout=1800)
        t = p.stdout.split()
        md5 = t[0] if p.returncode == 0 and t and re.fullmatch(r"[0-9a-f]{32}", t[0]) else None
        rc, err = p.returncode, p.stderr[-300:]
    except subprocess.TimeoutExpired:
        md5, rc, err = None, "timeout", ""
    return dict(stream=e["name"], mode=m, rc=rc, md5=md5, ok=md5 == e["ref"],
                same_as_pc=md5 == e.get(pck), err=err)


with open(out, "a") as fo:
    for m, (_, jobs, _) in MODES.items():
        todo = [(m, e) for e in man if (e["name"], m) not in done and e.get("ref")]
        with ThreadPoolExecutor(jobs) as ex:
            for r in ex.map(one, todo):
                fo.write(json.dumps(r) + "\n")
                fo.flush()
print("done")
