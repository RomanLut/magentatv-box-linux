#!/bin/bash
# Build the rescue initramfs that is built into the kernel (kernel/build-kernel.sh).
#
#   initramfs/build-initramfs.sh <output directory>
#
# The output is root/ (our scripts and settings) plus three static ARM programs, built here from
# their upstream sources:
#   /init           src/init-wrapper.c: runs /bin/sh /init-script as PID 1
#   /bin/busybox    BusyBox 1.37.0, static (glibc), configuration src/busybox-1.37.0.config;
#                   copied (not linked) to the applet names the scripts call
#   /bin/dropbear   Dropbear 2025.88, static (musl), multi-user, password login off
#
# It runs /init-script: mount the pseudo file systems, then stage1-root.sh boots the Debian
# system (by root label, or a live image for the installer); without one it stays in this
# rescue system with a console shell. Its SSH server (Dropbear) accepts keys only, and
# root/root/.ssh/authorized_keys is empty: nobody can log in over the network. The build stops if
# a public key is put there (releases carry no maintainer access).
#
# Needs: arm-linux-gnueabihf-gcc (Debian/Ubuntu gcc-arm-linux-gnueabihf), make, curl, bzip2.
# Downloads BusyBox, Dropbear and musl.cc's arm-linux-musleabihf toolchain (for Dropbear: musl
# reads /etc/passwd itself, with no NSS plug-ins), each checked by SHA-256.
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
[ $# = 1 ] || { echo "usage: $0 <output directory>" >&2; exit 1; }
OUT=$(realpath -m "$1")
W=${WORK:-$HERE/.build}
JOBS=${JOBS:-$(nproc)}

BB=busybox-1.37.0
BB_URL=https://busybox.net/downloads/$BB.tar.bz2
BB_SHA=3311dff32e746499f4df0d5df04d7eb396382d7e108bb9250e7b519b837043a4
DB=dropbear-2025.88
DB_URL=https://matt.ucc.asn.au/dropbear/releases/$DB.tar.bz2
DB_SHA=783f50ea27b17c16da89578fafdb6decfa44bb8f6590e5698a4e4d3672dc53d4
MUSL=arm-linux-musleabihf-cross
MUSL_URL=https://musl.cc/$MUSL.tgz
MUSL_SHA=11e155a090789c854afb5d91e57c81f441ccdb92f7f277789c3a6d5884a68e58

# a public key: its type, then its base64 data
KEYRE="(ssh-(rsa|ed25519|dss)|ecdsa-sha2-nistp[0-9]+|sk-ssh-ed25519@openssh.com) AAAA"
if grep -rl -E "$KEYRE" "$HERE/root" >/dev/null; then
    echo "an SSH public key is in initramfs/root: the rescue system takes none" >&2
    exit 1
fi

fetch() {   # fetch <url> <sha256> <file>
    [ -f "$W/$3" ] || curl -fL --retry 3 -o "$W/$3" "$1"
    echo "$2  $W/$3" | sha256sum -c --quiet || { echo "checksum of $3 does not match" >&2; exit 1; }
}

mkdir -p "$W"
fetch "$BB_URL" "$BB_SHA" "$BB.tar.bz2"
fetch "$DB_URL" "$DB_SHA" "$DB.tar.bz2"
fetch "$MUSL_URL" "$MUSL_SHA" "$MUSL.tgz"

echo "== BusyBox"
rm -rf "$W/$BB"
tar -C "$W" -xjf "$W/$BB.tar.bz2"
cp "$HERE/src/busybox-1.37.0.config" "$W/$BB/.config"
make -C "$W/$BB" CROSS_COMPILE=arm-linux-gnueabihf- oldconfig < /dev/null > /dev/null
make -C "$W/$BB" CROSS_COMPILE=arm-linux-gnueabihf- -j"$JOBS" busybox > "$W/busybox.log" 2>&1

echo "== Dropbear"
[ -d "$W/$MUSL" ] || tar -C "$W" -xzf "$W/$MUSL.tgz"
rm -rf "$W/$DB"
tar -C "$W" -xjf "$W/$DB.tar.bz2"
echo '#define DROPBEAR_SVR_PASSWORD_AUTH 0' > "$W/$DB/localoptions.h"
(
    cd "$W/$DB"
    export PATH=$W/$MUSL/bin:$PATH
    CC=arm-linux-musleabihf-gcc ./configure --host=arm-linux-musleabihf --disable-zlib \
        --enable-bundled-libtom --enable-static > "$W/dropbear-configure.log" 2>&1
    make STATIC=1 PROGRAMS=dropbear -j"$JOBS" > "$W/dropbear.log" 2>&1
    arm-linux-musleabihf-strip dropbear
)

echo "== init"
arm-linux-gnueabihf-gcc -static -Os -s -o "$W/init" "$HERE/src/init-wrapper.c"

echo "== assembling $OUT"
rm -rf "$OUT"
cp -a "$HERE/root" "$OUT"
# empty folders (git keeps none)
for d in dev proc sys tmp mnt etc/dropbear lib/firmware/rtl_bt lib/firmware/rtw88 usr/share/udhcpc; do
    mkdir -p "$OUT/$d"
done
install -m 755 "$W/init" "$OUT/init"
install -m 755 "$W/$BB/busybox" "$OUT/bin/busybox"
for a in cat chmod cttyhack ifconfig ls mdev mkdir mount setsid sh udhcpc uname; do
    install -m 755 "$W/$BB/busybox" "$OUT/bin/$a"
done
for a in halt poweroff reboot.real; do
    install -m 755 "$W/$BB/busybox" "$OUT/sbin/$a"
done
install -m 755 "$W/$DB/dropbear" "$OUT/bin/dropbear"
chmod 700 "$OUT/root" "$OUT/root/.ssh"
chmod 600 "$OUT/root/.ssh/authorized_keys"
[ ! -s "$OUT/root/.ssh/authorized_keys" ] || { echo "authorized_keys is not empty" >&2; exit 1; }
file "$OUT/init" "$OUT/bin/busybox" "$OUT/bin/dropbear"
echo "done: $OUT"
