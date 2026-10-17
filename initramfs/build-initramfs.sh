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
# Needs: arm-linux-gnueabihf-gcc and its glibc (Debian/Ubuntu gcc-arm-linux-gnueabihf,
# libc6-dev-armhf-cross), make, curl, bzip2.
# Downloads BusyBox, Dropbear and musl source, each checked by SHA-256. musl is built with
# the same Ubuntu/Debian ARM compiler, and its musl-gcc wrapper builds static Dropbear
# (musl reads /etc/passwd itself, with no NSS plug-ins). No musl.cc toolchain is needed.
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
[ $# = 1 ] || { echo "usage: $0 <output directory>" >&2; exit 1; }
OUT=$(realpath -m "$1")
W=$(realpath -m "${WORK:-$HERE/.build}")
JOBS=${JOBS:-$(nproc)}

BB=busybox-1.37.0
BB_URL=https://busybox.net/downloads/$BB.tar.bz2
BB_SHA=3311dff32e746499f4df0d5df04d7eb396382d7e108bb9250e7b519b837043a4
DB=dropbear-2025.88
DB_URL=https://matt.ucc.asn.au/dropbear/releases/$DB.tar.bz2
DB_SHA=783f50ea27b17c16da89578fafdb6decfa44bb8f6590e5698a4e4d3672dc53d4
MUSL=musl-1.2.5
# Buildroot's source mirror plus upstream, both with the same pinned release hash.
# Hash also recorded in Buildroot 2025.02 package/musl/musl.hash (signature-checked upstream).
MUSL_URL=https://sources.buildroot.net/musl/$MUSL.tar.gz
MUSL_UPSTREAM=https://musl.libc.org/releases/$MUSL.tar.gz
MUSL_SHA=a9a118bbe84d8764da0ea0d28b3ab3fae8477fc7e4085d90102b8596fc7c75e4

# a public key: its type, then its base64 data
KEYRE="(ssh-(rsa|ed25519|dss)|ecdsa-sha2-nistp[0-9]+|sk-ssh-ed25519@openssh.com) AAAA"
if grep -rl -E "$KEYRE" "$HERE/root" >/dev/null; then
    echo "an SSH public key is in initramfs/root: the rescue system takes none" >&2
    exit 1
fi

fetch() {   # fetch <sha256> <file> <url> [fallback url ...]
    local sha=$1 file=$W/$2 url
    shift 2
    if [ -f "$file" ] && echo "$sha  $file" | sha256sum -c --quiet; then
        return
    fi
    for url in "$@"; do
        if curl -fL --connect-timeout 15 --max-time 120 --retry 1 \
                -o "$file.part" "$url" &&
                echo "$sha  $file.part" | sha256sum -c --quiet; then
            mv "$file.part" "$file"
            return
        fi
        rm -f "$file.part"
    done
    echo "could not download a verified $(basename "$file")" >&2
    return 1
}

run_logged() {   # run_logged <log> <command ...>: on failure, show the log's end
    local log=$1
    shift
    "$@" > "$log" 2>&1 || { tail -40 "$log" >&2; echo "failed, full log: $log" >&2; return 1; }
}

mkdir -p "$W"
echo 'int main(void){return 0;}' | arm-linux-gnueabihf-gcc -static -x c -o /dev/null - ||
    { echo "arm-linux-gnueabihf-gcc cannot link a static program: install libc6-dev-armhf-cross" >&2; exit 1; }
fetch "$BB_SHA" "$BB.tar.bz2" "$BB_URL"
fetch "$DB_SHA" "$DB.tar.bz2" "$DB_URL"
fetch "$MUSL_SHA" "$MUSL.tar.gz" "$MUSL_URL" "$MUSL_UPSTREAM"

echo "== BusyBox"
rm -rf "$W/$BB"
tar -C "$W" -xjf "$W/$BB.tar.bz2"
cp "$HERE/src/busybox-1.37.0.config" "$W/$BB/.config"
make -C "$W/$BB" CROSS_COMPILE=arm-linux-gnueabihf- oldconfig < /dev/null > /dev/null
run_logged "$W/busybox.log" make -C "$W/$BB" CROSS_COMPILE=arm-linux-gnueabihf- -j"$JOBS" busybox

echo "== musl (ARM hard-float, static)"
rm -rf "$W/$MUSL" "$W/musl-install"
tar -C "$W" -xzf "$W/$MUSL.tar.gz"
(
    cd "$W/$MUSL"
    CC=arm-linux-gnueabihf-gcc CROSS_COMPILE=arm-linux-gnueabihf- \
        ./configure --target=arm-linux-musleabihf --prefix="$W/musl-install" \
        --disable-shared --enable-wrapper=gcc > "$W/musl-configure.log" 2>&1 ||
        { tail -40 "$W/musl-configure.log" >&2; exit 1; }
    run_logged "$W/musl-build.log" make -j"$JOBS"
    run_logged "$W/musl-install.log" make install
)

echo "== Dropbear"
rm -rf "$W/$DB"
tar -C "$W" -xjf "$W/$DB.tar.bz2"
echo '#define DROPBEAR_SVR_PASSWORD_AUTH 0' > "$W/$DB/localoptions.h"
(
    cd "$W/$DB"
    CC="$W/musl-install/bin/musl-gcc" AR=arm-linux-gnueabihf-ar \
        RANLIB=arm-linux-gnueabihf-ranlib ./configure --host=arm-linux-musleabihf --disable-zlib \
        --enable-bundled-libtom --enable-static > "$W/dropbear-configure.log" 2>&1 ||
        { tail -40 "$W/dropbear-configure.log" >&2; exit 1; }
    run_logged "$W/dropbear.log" make STATIC=1 PROGRAMS=dropbear -j"$JOBS"
    arm-linux-gnueabihf-strip dropbear
    if arm-linux-gnueabihf-readelf -l dropbear | grep -q INTERP ||
            arm-linux-gnueabihf-readelf -d dropbear | grep -q NEEDED; then
        echo "Dropbear must be static: unexpected interpreter or shared library" >&2
        exit 1
    fi
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
