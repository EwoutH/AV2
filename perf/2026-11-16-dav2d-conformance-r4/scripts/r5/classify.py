import json, collections, sys
res = {}
for l in open("results.jsonl"):
    r = json.loads(l)
    if r.get("verdict"): res[r["id"]] = r
tri = {json.loads(l)["id"]: json.loads(l) for l in open("triage.jsonl")}
rows = [json.loads(l) for l in open(sys.argv[1] if len(sys.argv) > 1 else "r5/recheck.jsonl")]
def bad(x, b):
    d = x[b]; return (not d["ok"]) or d["san"] is not None or d["rc"] != 0
C = collections.Counter(); groups = collections.defaultdict(list)
for x in rows:
    t = tri[x["id"]]; c = res[x["id"]]["cfg"]
    if not t["avmn_agrees"]:
        C["refdisagree"] += 1; continue
    r5 = bad(x, "r5") or bad(x, "r5-asan") or (x.get("r5-mt", {}).get("ok_of_3", 3) < 3)
    r5g = bad(x, "r5g") or bad(x, "r5g-asan")
    if not r5:
        C["fixed on r5"] += 1; continue
    if not r5g:
        C["fixed only with gramner MRs"] += 1; groups["gramner-fixed " + c["fmt"]].append(x["id"]); continue
    kind = []
    if not x["r5"]["ok"]: kind.append("asm-mm")
    if not x["r5-asan"]["ok"]: kind.append("c-mm")
    if x["r5-asan"]["san"]: kind.append(x["r5-asan"]["san"].split(" applying")[0][:70])
    if x["r5"]["rc"] or x["r5-asan"]["rc"]: kind.append(f"rc{x['r5']['rc']}/{x['r5-asan']['rc']}")
    if x.get("r5-mt", {}).get("ok_of_3", 3) < 3 and x["r5"]["ok"]: kind.append(f"mt {x['r5-mt']['ok_of_3']}/3")
    key = f"{c['fmt']} " + " | ".join(kind)
    groups[key].append(x["id"]); C["still"] += 1
print(C)
for k, v in sorted(groups.items(), key=lambda kv: -len(kv[1])):
    print(f"{len(v):4d} {k}: {' '.join(v[:8])}")
