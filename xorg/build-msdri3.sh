#!/bin/bash
# Build and install Raspberry Pi's msdri3 modesetting driver on the MRG5
# (checks/53 §6).  Run on the box.
#
#   bash build-msdri3.sh            build, keep Debian's module, install
#   bash build-msdri3.sh restore    put Debian's module back, drop the diversion
#
# Source: Raspberry Pi's xorg-server 2:21.1.7-3+rpt3+deb12u12 - Debian 12's
# 21.1.7-3+deb12u12 (the box's version) plus RPi's patches, among them
# 0003-modesetting-Add-DRI3-support-to-modesetting-driver-w.patch (Igalia,
# freedesktop MR 945, XDC 2022 "DRI3 modesetting without glamor"), which adds
# AccelMethod "msdri3": X draws on the CPU, GL clients use the GPU via DRI3.
# Configured exactly as RPi's debian/rules does (it already passes
# --enable-ms-dri3); only the modesetting module is built and installed, the
# rest of the server stays Debian's.
#
# Debian's modesetting_drv.so does not know "msdri3" and runs X unaccelerated
# without DRI3 (GL clients lose the GPU). A local dpkg diversion keeps
# xserver-xorg-core updates off ours: dpkg writes the package's copy to
# modesetting_drv.so.distrib instead. A 21.1.7 point update keeps the driver ABI;
# a new X version needs this build redone against its source.
set -euo pipefail
W=/root/xorg-msdri3
M=/usr/lib/xorg/modules/drivers/modesetting_drv.so
V=21.1.7-3+rpt3+deb12u12
B=https://archive.raspberrypi.com/debian/pool/main/x/xorg-server
DIFF_SHA=7f81abcc704edcec59f52325a5b94b9da515fae346188d41b43513a14a5be7b5
ORIG_SHA=1a9005f47c7ea83645a977581324439628a32c4426303e5a4b9c2d6615becfbf

if [ "${1:-}" = restore ]; then
	install -m 0644 "$W/modesetting_drv.so.debian" "$M"
	if dpkg-divert --list "$M" | grep -q distrib; then
		rm -f "$M.distrib"
		dpkg-divert --local --no-rename --remove "$M"
	fi
	sha256sum "$M"
	exit 0
fi

mkdir -p "$W"
cd "$W"
apt-get -y -q build-dep xorg-server > /dev/null
apt-get -y -q install quilt devscripts > /dev/null
for f in "xorg-server_$V.dsc" "xorg-server_$V.diff.gz" xorg-server_21.1.7.orig.tar.gz; do
	[ -f "$f" ] || wget -q "$B/$f"
done
echo "$DIFF_SHA  xorg-server_$V.diff.gz" | sha256sum -c -
echo "$ORIG_SHA  xorg-server_21.1.7.orig.tar.gz" | sha256sum -c -

[ -d xorg-server-21.1.7 ] || dpkg-source --no-check -x "xorg-server_$V.dsc" > /dev/null
cd xorg-server-21.1.7
QUILT_PATCHES=debian/patches quilt push -a -q > /dev/null || true
grep -q MS_DRI3 hw/xfree86/drivers/modesetting/driver.c
# ours on top: honour Option "ShadowFB" with msdri3 (checks/53 §6)
python3 "$W/mrg5-msdri3-shadowfb.py" .
# and read GL clients' frames through mrg5_drm's cached read-only dma-buf
# mapping (checks/53 §9 item 13; needs zImage-smp5q or later)
python3 "$W/mrg5-msdri3-cachedread.py" .

# configure the Debian way (debian/rules: dh_auto_configure, main build)
printf 'include debian/rules.flags\ninclude /usr/share/dpkg/architecture.mk\nall:\n\tdh_autoreconf\n\tdh_auto_configure --builddirectory=debian/build/main -- $(confflags) $(confflags_main) $(vars)\n' > "$W/cfg.mk"
[ -f debian/build/main/config.status ] || make -f "$W/cfg.mk" > "$W/configure.log" 2>&1
grep -q "define MS_DRI3 1" debian/build/main/include/dix-config.h
make -C debian/build/main/hw/xfree86/drivers/modesetting -j4 > "$W/build.log" 2>&1

[ -f "$W/modesetting_drv.so.debian" ] || cp "$M" "$W/modesetting_drv.so.debian"
if ! dpkg-divert --list "$M" | grep -q distrib; then
	dpkg-divert --local --no-rename --divert "$M.distrib" --add "$M"
	install -m 0644 "$W/modesetting_drv.so.debian" "$M.distrib"
fi
install -m 0644 debian/build/main/hw/xfree86/drivers/modesetting/.libs/modesetting_drv.so "$M"
sha256sum "$M"
echo "installed; restart the desktop (stop-desktop.sh, start-desktop.sh)"
