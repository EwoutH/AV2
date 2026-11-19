# guard index -> function, call address (from objdump of the trace-pc-guard build)
import re, subprocess, sys, json
B = sys.argv[1]
syms = subprocess.run(["objdump", "-t", B], capture_output=True, text=True).stdout
start = int(re.search(r"^([0-9a-f]+) .*__start___sancov_guards", syms, re.M).group(1), 16)
fn, prev, out = None, None, {}
p = subprocess.Popen(["objdump", "-d", "--no-show-raw-insn", B], stdout=subprocess.PIPE, text=True)
for l in p.stdout:
    m = re.match(r"^[0-9a-f]+ <(.+)>:", l)
    if m: fn = m.group(1); continue
    if "trace_pc_guard>" in l and "call" in l and prev:
        g = re.search(r"# ([0-9a-f]+) <", prev)
        if g:
            addr = l.split(":")[0].strip()
            out[(int(g.group(1), 16) - start) // 4 + 1] = (fn, addr)
    prev = l
addrs = [v[1] for k, v in sorted(out.items())]
a2l = subprocess.run(["addr2line", "-e", B, "-i"[:0] or "-e", B], input="", capture_output=True, text=True)
r = subprocess.run(["addr2line", "-e", B] + ["0x" + a for a in addrs], capture_output=True, text=True).stdout.split("\n")
res = {}
for (k, (f, a)), loc in zip(sorted(out.items()), r):
    res[k] = [f, loc.split(" ")[0].replace("/srv/compression/cache/av2conf/src/wt-rd5main/", "")]
json.dump(res, open(sys.argv[2], "w"))
print(len(res), "guards mapped")
