"""Run conform.py from the 20 Oct report with one decoder.

Uses the reference rows (avmdec MD5s) from an earlier results file, so only
the given decoder is run. Needs the local work folder layout
(`samples/av2_work/decoders/conform.py`).

  python run_conform.py <name> <path to dav2d.exe> <results.jsonl> [reference.jsonl]
"""
import json
import sys
from pathlib import Path

WORK = Path(__file__).resolve().parents[3] / "samples" / "av2_work" / "decoders"
sys.path.insert(0, str(WORK))
import conform  # noqa: E402

name, exe, out = sys.argv[1], sys.argv[2], Path(sys.argv[3])
ref = Path(sys.argv[4]) if len(sys.argv) > 4 else conform.HERE / "conform.jsonl"
conform.DECODERS = {name: Path(exe)}
if not out.exists():
    rows = [r for r in map(json.loads, open(ref)) if r["decoder"] == "reference"]
    out.write_text("".join(json.dumps(r) + "\n" for r in rows))
sys.argv = [sys.argv[0], "--jobs", "4", "--results", str(out)]
conform.main()
