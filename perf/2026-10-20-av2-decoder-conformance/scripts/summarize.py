import json, collections, re, sys
rows = [json.loads(l) for l in open("conform.jsonl")]
by = collections.defaultdict(dict)
for r in rows: by[r["stream"]][r["decoder"]] = r
stat = collections.defaultdict(collections.Counter)
for s, d in by.items():
    ref = d.get("reference")
    if not ref or not ref["md5"]: continue
    for n, r in d.items():
        if n == "reference": continue
        k = ("match" if r["md5"] == ref["md5"] else "crash" if r["rc"] not in (0, 1) else
             "error" if r["rc"] else "mismatch")
        stat[n][k] += 1
print(f"{len(by)} streams")
for n in sorted(stat): print(f"  {n:22s}", " ".join(f"{k}={v}" for k, v in sorted(stat[n].items())))
