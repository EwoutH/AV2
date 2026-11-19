# Encode IVF seek samples (public bit-exact ffmpeg lavfi testsrc2 sources), verify with av2-normative avmdec.
set -e
cd /srv/compression/cache/av2conf/testreview/ivf
ENC=/srv/compression/cache/av2conf/round5/build/avm5/avmenc
REF=/srv/compression/cache/av2conf/build/avmn12/avmdec
S=/srv/compression/cache/av2conf/round5/cov/src
enc() { # name src limit extra...
  n=$1; src=$2; lim=$3; shift 3
  $ENC $S/$src -o $n.ivf --limit=$lim --cpu-used=5 --threads=1 --end-usage=q --qp=$QP --kf-min-dist=8 --kf-max-dist=8 --lag-in-frames=0 "$@" >/dev/null 2>enc_$n.err
  md5=$($REF --rawvideo --md5 $n.ivf | cut -d' ' -f1)
  echo "$n $(stat -c %s $n.ivf) bytes ref_md5=$md5"
}
QP=${QP:-200}
enc avm.testsrc.176x144.l32.kf8 testsrc_176x144_80f.y4m 32
enc avm.testsrc.130x74.l32.10bit.kf8 testsrc10_130x74.y4m 32
