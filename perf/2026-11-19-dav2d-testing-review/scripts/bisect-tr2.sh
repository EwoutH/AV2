set -e
cd /srv/compression/projects/dav2d
W=/srv/compression/cache/av2conf/testreview/wt-bisect
[ -d $W ] || git worktree add -q --detach $W 5bf33c8f
cd $W
cat > /srv/compression/cache/av2conf/testreview/bisect-test.sh <<'EOT'
B=/srv/compression/cache/av2conf/testreview/b-bisect
[ -d $B ] || meson setup $B /srv/compression/cache/av2conf/testreview/wt-bisect --buildtype release -Denable_asm=false -Denable_tests=false >/dev/null || exit 125
ninja -j3 -C $B tools/dav2d >/dev/null || exit 125
m=$($B/tools/dav2d -q --threads 1 --filmgrain=1 -i /home/agent/.claude/jobs/e60fd380/tmp/tr/s/avm.testsrc.130x74.l12.10bit.tile-rows2.obu --muxer md5 -o - 2>/dev/null)
echo "$(git -C /srv/compression/cache/av2conf/testreview/wt-bisect log --oneline -1) -> $m" >&2
[ "$m" != "bf8b336b83a062fb201db0d31688917d" ]  # old (fails) -> exit 0, new (passes) -> exit 1
EOT
git bisect reset -q 2>/dev/null || true
git bisect start --term-old=old --term-new=new a9b01371 5bf33c8f >/dev/null
git bisect run bash /srv/compression/cache/av2conf/testreview/bisect-test.sh 2>&1 | grep -E "is the first new commit|->|^commit|^    " | head -30
git bisect reset -q
