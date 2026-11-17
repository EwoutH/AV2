"""Summarise the pi decode of the kept (passing on the pc) stress streams: keepsum.py <keep.jsonl>"""
import collections, json, sys
rows = [json.loads(l) for l in open(sys.argv[1])]
by = collections.defaultdict(list)
for r in rows:
    by[r["mode"]].append(r)
for m, rs in by.items():
    bad = [r for r in rs if not r["ok"]]
    print(f"{m}: {len(rs)} streams, {len(rs) - len(bad)} match avmdec, {len(bad)} don't;"
          f" differ from pc: {sum(not r['same_as_pc'] for r in rs)}")
    for r in bad[:15]:
        print("   ", r["stream"], r["rc"], r["md5"], r["err"].strip().splitlines()[-1:] if r["err"] else "")
