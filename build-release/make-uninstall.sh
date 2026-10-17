#!/bin/bash
# make-uninstall.sh (checks/54, "Uninstall image"): build the uninstall stick's files.
#
#   /root/emmc-release/make-uninstall.sh
#
# Output in $OUT (default /srv/mrg5-uninstall), for make-image.sh:
#   Testapp6/BOOT/boot.ini          "unsetenv STARTUP;", then our kernel in live mode
#   Testapp6/BOOT/<kernel>, <dtb>   the same kernel and device tree as the release
#   Testapp6/live/uninstall.sqfs    BusyBox (Debian's busybox-static) and uninstall-init, which
#                                   reads BOLT's environment and shows the result on the TV
#   SHA256SUMS
#
# Environment: OUT, KERNEL (zImage-smp6c), DTB (dtb-mrg5-release.bin), BOOTDIR (this
# script's directory).
set -euo pipefail
HERE=$(dirname "$(readlink -f "$0")")
OUT=${OUT:-/srv/mrg5-uninstall}
KERNEL=${KERNEL:-zImage-smp6c}
DTB=${DTB:-dtb-mrg5-release.bin}
BOOTDIR=${BOOTDIR:-$HERE}
TEMPLATE=$HERE/boot-template.ini
FONT=/usr/share/consolefonts/Uni3-TerminusBold32x16.psf.gz
die() { echo "ERROR: $*" >&2; exit 1; }

[ "$(id -u)" = 0 ] || die "run as root"
[ -f "$BOOTDIR/$KERNEL" ] && [ -f "$BOOTDIR/$DTB" ] || die "no $KERNEL and $DTB in BOOTDIR=$BOOTDIR"
# only a release kernel: built by kernel/build-kernel.sh, whose .release file
# records its sha256 and that its rescue initramfs holds no SSH keys (owner, 2026-10-03)
[ -f "$BOOTDIR/$KERNEL.release" ] || die "$KERNEL has no .release file (build it with kernel/build-kernel.sh)"
grep -qx "sha256=$(sha256sum "$BOOTDIR/$KERNEL" | cut -d' ' -f1)" "$BOOTDIR/$KERNEL.release" ||
    die "$KERNEL does not match its .release file"
grep -qx "rescue_ssh_keys=none.*" "$BOOTDIR/$KERNEL.release" || die "$KERNEL's rescue initramfs may hold SSH keys"
[ -f "$TEMPLATE" ] && [ -f "$HERE/uninstall-init" ] && [ -f "$FONT" ] || die "missing input files"

W=$(mktemp -d)
trap 'rm -rf "$W"' EXIT
# BusyBox from Debian's package, unpacked only (not installed on this system)
(cd "$W" && apt-get download -q busybox-static && dpkg-deb -x busybox-static_*.deb deb)
R=$W/root
mkdir -p "$R/bin" "$R/sbin" "$R/dev" "$R/proc" "$R/sys" "$R/run" "$R/tmp" "$R/etc" \
         "$R/lib/systemd" "$R/usr/share/consolefonts"
install -m 755 "$W/deb/bin/busybox" "$R/bin/busybox"
for a in sh awk od cat printf sleep setfont; do ln -s busybox "$R/bin/$a"; done
gunzip -c "$FONT" > "$R/usr/share/consolefonts/Uni3-TerminusBold32x16.psf"
install -m 755 "$HERE/uninstall-init" "$R/sbin/init"
# stage1-root.sh's live handover only switches to an image that has this path; it tests it
# from the initramfs (/newroot/...), so the link must be relative
ln -s ../../sbin/init "$R/lib/systemd/systemd"
: > "$R/etc/fstab"

rm -rf "$OUT"
B=$OUT/Testapp6/BOOT
mkdir -p "$B" "$OUT/Testapp6/live"
cp "$BOOTDIR/$KERNEL" "$BOOTDIR/$DTB" "$B/"
# BOLT clears STARTUP (unsetenv rewrites flash0.nvram only when the variable exists; checks/42
# §3a), then boots the live image
{
    echo 'unsetenv STARTUP;'
    sed -e "s|zImage-[A-Za-z0-9]*|$KERNEL|; s|dtb-[A-Za-z0-9-]*\.bin|$DTB|" \
        -e 's|^dt add prop /chosen mrg5,root s [A-Za-z0-9_-]*;|dt add prop /chosen mrg5,live s /Testapp6/live/uninstall.sqfs;|' \
        "$TEMPLATE"
} > "$B/boot.ini"
grep -q 'mrg5,live' "$B/boot.ini" || die "boot.ini has no live line"
[ "$(wc -c < "$B/boot.ini")" -le 2048 ] || die "boot.ini exceeds BOLT's 2048-byte buffer"
mksquashfs "$R" "$OUT/Testapp6/live/uninstall.sqfs" -comp zstd -noappend -all-root -no-progress
(cd "$OUT" && find Testapp6 -type f -print0 | sort -z | xargs -0 sha256sum > SHA256SUMS)
cat "$OUT/SHA256SUMS"
du -sh "$OUT" | cut -f1
