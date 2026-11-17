import json, collections
res = {}
for l in open("results.jsonl"):
    r = json.loads(l)
    if r.get("verdict"): res[r["id"]] = r
tri = {json.loads(l)["id"]: json.loads(l) for l in open("triage.jsonl")}
order = [("ger", lambda f: "--global-error-resilient" in f),
         ("lfat", lambda f: "--disable-loopfilters-across-tiles" in f),
         ("crop", lambda f: "--enable-cropping-window" in f),
         ("grain", lambda f: "--denoise-noise-level" in f or "--film-grain-test" in f),
         ("sframe", lambda f: "--enable-sframe" in f),
         ("fwdkf", lambda f: "--enable-fwd-kf" in f)]
cl = collections.defaultdict(list)
for l in open("r5/recheck.jsonl"):
    x = json.loads(l)
    if not tri[x["id"]]["avmn_agrees"] or (x["r5"]["ok"] and x["r5-asan"]["ok"]): continue
    c = res[x["id"]]["cfg"]
    k = next((n for n, p in order if p(c["flags"])), "rest")
    cl[k].append((x["id"], c))
json.dump({k: [i for i, _ in v] for k, v in cl.items()}, open("r5/clusters.json", "w"), indent=0)
for k, v in cl.items():
    print(k, len(v), collections.Counter(c["fmt"] for _, c in v))
for i, c in sorted(cl["rest"], key=lambda t: t[1]["frames"]):
    print(i, c["src"], c["fmt"], c.get("rc"), c["frames"], "obu" if c.get("obu") else "", c["flags"])
