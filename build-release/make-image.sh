#!/bin/bash
# make-image.sh (checks/54, "Disk images"): pack a release folder (make-release.sh,
# make-uninstall.sh) into a disk image for Raspberry Pi Imager, compressed with xz.
#
#   /root/emmc-release/make-image.sh <folder> <name.img> <FAT label>
#
# The image: an MBR with one bootable FAT32 partition (type 0x0c) from 1 MiB, 4 KiB clusters,
# as on the MRG5-LINUX stick that BOLT boots from; the folder's contents at its top level.
# Output: <name.img>.xz and <name.img>.xz.sha256. The FAT checks SHA256SUMS after copying.
set -euo pipefail
die() { echo "ERROR: $*" >&2; exit 1; }
[ $# = 3 ] || die "usage: $0 <folder> <name.img> <FAT label>"
SRC=$1 IMG=$2 LABEL=$3
[ "$(id -u)" = 0 ] || die "run as root"
[ -f "$SRC/Testapp6/BOOT/boot.ini" ] && [ -f "$SRC/SHA256SUMS" ] || die "$SRC is not a release folder"

need=$(du -s -B1M "$SRC" | cut -f1)
part=$(( need + need / 20 + 32 ))     # MiB: the files, 5 % and 32 MiB for the FAT itself
[ "$part" -ge 300 ] || part=300       # FAT32 needs 65525 clusters: 256 MiB at 4 KiB
rm -f "$IMG" "$IMG.xz"
truncate -s $(( (part + 1) * 1024 * 1024 )) "$IMG"
printf 'label: dos\nstart=2048, size=%d, type=c, bootable\n' $(( part * 2048 )) | sfdisk -q "$IMG"
loop=$(losetup -f --show -o $(( 2048 * 512 )) --sizelimit $(( part * 1024 * 1024 )) "$IMG")
M=$(mktemp -d)
cleanup() { umount "$M" 2>/dev/null || true; losetup -d "$loop" 2>/dev/null || true; rmdir "$M"; }
trap cleanup EXIT
mkfs.vfat -F 32 -s 8 -n "$LABEL" "$loop" >/dev/null
mount -t vfat "$loop" "$M"
cp -r "$SRC"/. "$M"/
sync
(cd "$M" && sha256sum -c --quiet SHA256SUMS) || die "copy differs from SHA256SUMS"
umount "$M"
fsck.vfat -n "$loop" >/dev/null || die "fsck.vfat found errors"
losetup -d "$loop"
trap - EXIT
rmdir "$M"
xz -T4 -6 "$IMG"
(cd "$(dirname "$IMG")" && sha256sum "$(basename "$IMG").xz" > "$(basename "$IMG").xz.sha256")
ls -l "$IMG.xz"
cat "$IMG.xz.sha256"
