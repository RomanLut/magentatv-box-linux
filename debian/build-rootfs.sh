#!/bin/bash
# Build the Debian 12 (bookworm) armhf root filesystem image for the MRG5 NAS.
#
# Runs in WSL without sudo: debootstrap's first stage (download + unpack) runs
# under fakeroot, and the ext4 image is populated in the same fakeroot session
# (mkfs.ext4 -d), so file ownership and device nodes are recorded correctly.
# Package configuration (debootstrap --second-stage) happens natively on the box
# the first time the initramfs finds this filesystem (work/nas/stage1-root.sh).
#
# Output: ~/mrg5-rootfs/out/mrg5root.img (ext4, label MRG5ROOT) + .gz
set -euo pipefail

SUITE=bookworm
MIRROR=http://deb.debian.org/debian
IMG_SIZE=3G
TOP=~/mrg5-rootfs
SRC=/mnt/d/Github/MagentaTVBox/work
TOOLS=$TOP/tools
ROOT=$TOP/root
OUT=$TOP/out

INCLUDE=systemd,systemd-sysv,systemd-resolved,systemd-timesyncd,dbus,udev,\
openssh-server,ca-certificates,curl,wget,gnupg,iproute2,iputils-ping,kmod,procps,\
less,nano,sudo,e2fsprogs,exfatprogs,parted,fbi,lsb-release,locales

mkdir -p "$TOOLS" "$OUT"
cd "$TOOLS"
[ -d dbs ] || { apt download debootstrap; dpkg-deb -x debootstrap_*.deb dbs; }
[ -d kr ]  || { apt download debian-archive-keyring; dpkg-deb -x debian-archive-keyring_*.deb kr; }
KEYRING=$TOOLS/kr/usr/share/keyrings/debian-archive-bookworm-stable.gpg

rm -rf "$ROOT" "$OUT/mrg5root.img" "$OUT/mrg5root.img.gz"
mkdir -p "$ROOT"

fakeroot -s "$TOP/fakeroot.state" -- env \
    DEBOOTSTRAP_DIR="$TOOLS/dbs/usr/share/debootstrap" \
    PATH="$TOOLS/dbs/usr/sbin:$PATH" \
    ROOT="$ROOT" SRC="$SRC" OUT="$OUT" IMG_SIZE="$IMG_SIZE" \
    SUITE="$SUITE" MIRROR="$MIRROR" INCLUDE="$INCLUDE" KEYRING="$KEYRING" \
    bash -euo pipefail -c '
debootstrap --foreign --arch=armhf --variant=minbase --keyring="$KEYRING" \
    --include="$INCLUDE" "$SUITE" "$ROOT" "$MIRROR"

# First-boot configuration, run by the initramfs inside the new root after
# the second stage.
install -d -m 755 "$ROOT/mrg5"
install -m 755 "$SRC/nas/firstboot.sh"     "$ROOT/mrg5/firstboot.sh"
install -m 644 "$SRC/nas/pigallery2-compose.yaml" "$ROOT/mrg5/pigallery2-compose.yaml"
install -m 600 "$SRC/linux-full-root/root/.ssh/authorized_keys" "$ROOT/mrg5/authorized_keys"

# mkfs.ext4 -d gives the root directory of the image the owner and mode of $ROOT itself;
# without this, the installed system had / owned by the build user (uid 1000 = admin), mode 777
chown 0:0 "$ROOT"
chmod 755 "$ROOT"
mkfs.ext4 -q -F -L MRG5ROOT -O ^metadata_csum_seed -d "$ROOT" "$OUT/mrg5root.img" "$IMG_SIZE"
'

e2fsck -fn "$OUT/mrg5root.img" | tail -1
gzip -1 -k "$OUT/mrg5root.img"
ls -l "$OUT"
sha256sum "$OUT/mrg5root.img.gz"
