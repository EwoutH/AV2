# list samples per test-data branch: name, path-in-repo, md5, extra args; extract files
import re, subprocess, json, os
R = "/srv/compression/projects/dav2d-test-data"
def git(*a): return subprocess.run(["git", "-C", R, *a], capture_output=True, text=True).stdout
def entries(ref):
    out = {}
    for m in git("ls-tree", "-r", "--name-only", ref).split():
        if not m.endswith("meson.build") or "/" not in m: continue
        d = m.split("/")[0]
        txt = git("show", f"{ref}:{m}")
        gl = re.findall(r"dav2d_test_args \+= \[([^\]]*)\]", txt)
        for l in txt.splitlines():
            if re.match(r"\s*\['", l):
                p = re.findall(r"'([^']*)'", l)
                out[p[0]] = (f"{d}/{p[1]}", p[2], p[3:], d)
    return out
sets = {}
base = entries("origin/main")
sets["upstream"] = base
for mr, br in [("!6", "fork/add-round3-samples"), ("!9", "fork/add-coverage-samples"), ("!10", "fork/add-round4-samples"), ("!11", "fork/add-clk-sample"), ("!8", "fork/add-ger-sample")]:
    e = entries(br); prev = set(base) | {k for s in sets.values() for k in s}
    sets[mr] = {k: v for k, v in e.items() if k not in prev}
    for k, v in sets[mr].items(): v_ref = br
    for k in sets[mr]: sets[mr][k] = sets[mr][k] + (br,)
for k in sets["upstream"]: sets["upstream"][k] = sets["upstream"][k] + ("origin/main",)
os.makedirs("s", exist_ok=True)
for mr, s in sets.items():
    for k, (p, md5, extra, d, ref) in s.items():
        f = f"s/{os.path.basename(p)}"
        if not os.path.exists(f):
            open(f, "wb").write(subprocess.run(["git", "-C", R, "show", f"{ref}:{p}"], capture_output=True).stdout)
    print(mr, len(s), list(s)[:20])
json.dump(sets, open("sets.json", "w"), indent=0)
