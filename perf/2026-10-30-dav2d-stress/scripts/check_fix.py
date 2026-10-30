"""Decode every kept failure (fail/*/{min,stream}.ivf) with a dav2d build
(1 thread, C and asm) and report against avmdec (av2-enc build)."""
import json, re, subprocess, sys
from pathlib import Path
W = Path(__file__).resolve().parent.parent
REF = W / "enc1030/avm_build_windows/Release/avmdec.exe"
DAV = Path(sys.argv[1]) if len(sys.argv) > 1 else W / "decoders/build-fix-gcc/tools/dav2d.exe"
def md5(cmd):
    try:
        p = subprocess.run([str(c) for c in cmd], capture_output=True, text=True, timeout=300)
    except subprocess.TimeoutExpired:
        return "timeout"
    t = p.stdout.split()
    return t[0] if p.returncode == 0 and t and re.fullmatch(r"[0-9a-f]{32}", t[0]) else f"rc{p.returncode}"
rows = {json.loads(l)["id"]: json.loads(l) for l in open(Path(__file__).parent / "results.jsonl")}
for d in sorted((Path(__file__).parent / "fail").iterdir()):
    r = rows.get(d.name, {})
    m = r.get("min")
    flags = m["cfg"]["flags"] if isinstance(m, dict) else r.get("flags")
    for name in ("min.ivf", "stream.ivf"):
        f = d / name
        if not f.exists():
            continue
        ref = md5([REF, f, "--rawvideo", "--md5", "--threads=1"])
        c = md5([DAV, "-q", "--threads", "1", "--cpumask", "0", "--filmgrain", "1", "-i", f, "--muxer", "md5", "-o", "-"])
        a = md5([DAV, "-q", "--threads", "1", "--filmgrain", "1", "-i", f, "--muxer", "md5", "-o", "-"])
        st = lambda x: "ok" if x == ref else ("CRASH" if x.startswith("rc") and x != "rc1" else "BAD")
        print(f"{d.name}/{name:10s} C={st(c):5s} asm={st(a):5s} {r.get('verdict')} {flags if name == 'min.ivf' else ''}", flush=True)
