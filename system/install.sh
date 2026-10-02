#!/bin/bash
# Install the project's own system files (rootfs/, links.txt) into a Debian 12 armhf root:
#
#   system/install.sh /          on the box, as root
#   system/install.sh <root>     into a mounted root file system
#
# rootfs/ holds the files at their target paths: the TV launcher, the storage, standby and LED
# services, the game and desktop start commands, the X, PulseAudio, Bluetooth and network
# settings, and root's desktop configuration. It does not install the packages they use (see
# BUILDING.md); afterwards enable the services:
#   systemctl enable mrg5-launcher mrg5-storage mrg5-leds mrg5-zram mrg5-growfs \
#       mrg5-rcu-home-exit mrg5-v3d-overflow pulseaudio mrg5-bt-codec
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
T=${1:?usage: $0 <target root>}
# Blueman's applet with pair-before-connect replaces Debian's file: keep Debian's as a diversion,
# so a blueman update installs it beside ours instead of over it
B=/usr/lib/python3/dist-packages/blueman/plugins/applet/DBusService.py
if [ -e "$T$B" ] && ! dpkg-divert --root="$T" --list "$B" | grep -q .; then
    dpkg-divert --root="$T" --package mrg5-blueman --rename --divert "$B.distrib" --add "$B"
fi
cp -a "$HERE/rootfs/." "$T/"
grep -v '^#' "$HERE/links.txt" | while read -r link target; do
    [ -n "$link" ] && ln -sfn "$target" "$T/$link"
done
chmod 440 "$T"/etc/sudoers.d/mrg5-*
echo "installed into $T"
