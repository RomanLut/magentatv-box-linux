#!/bin/bash
# Apply kernel-nas.fragment to ~/mrg5-build/out/.config and report any option that did not stick.
set -e
FRAG=/mnt/d/Github/MagentaTVBox/work/nas/kernel-nas.fragment
cd ~/mrg5-build/linux-src
[ -e ../out/.config.pre-nas ] || cp ../out/.config ../out/.config.pre-nas
grep -E '^CONFIG_' "$FRAG" | cut -d= -f1 | sed 's/^CONFIG_//' | while read -r o; do
    scripts/config --file ../out/.config -e "$o"
done
make O=../out ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- olddefconfig >/dev/null
miss=0
for o in $(grep -E '^CONFIG_' "$FRAG" | cut -d= -f1); do
    grep -qx "$o=y" ../out/.config || { echo "NOT SET: $o"; miss=1; }
done
[ $miss = 0 ] && echo "all fragment options set"
