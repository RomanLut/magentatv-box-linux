#!/bin/bash
# Build the MRG5 kernel (zImage with its rescue initramfs) from upstream Linux 6.18.
#
#   kernel/build-kernel.sh [output directory]        (default kernel/.build)
#
# Steps:
#   1. download linux-6.18.tar.xz from kernel.org (SHA-256 checked) and apply
#      linux-6.18-mrg5.patch: our machine support (display, SMP bring-up, HDMI audio, the KMS
#      driver, V3D 3.3 fixes, Bluetooth UART), against the upstream tree;
#   2. build the initramfs (initramfs/build-initramfs.sh);
#   3. fetch Realtek's Bluetooth firmware and make its config (firmware/), both built in;
#   4. config-mrg5 (the configuration of the released kernel) with the three paths of this
#      build, then make zImage.
#
# Needs: gcc-arm-linux-gnueabihf, make, bc, bison, flex, libssl-dev, cpio, xz-utils, curl,
# python3. The result is the released kernel's source and configuration; a rebuild is not
# bit-identical (build time, host and number are part of the image).
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
REPO=$(dirname "$HERE")
B=$(realpath -m "${1:-$HERE/.build}")
JOBS=${JOBS:-$(nproc)}
V=linux-6.18
URL=https://cdn.kernel.org/pub/linux/kernel/v6.x/$V.tar.xz
SHA=9106a4605da9e31ff17659d958782b815f9591ab308d03b0ee21aad6c7dced4b

mkdir -p "$B"
[ -f "$B/$V.tar.xz" ] || curl -fL --retry 3 -o "$B/$V.tar.xz" "$URL"
echo "$SHA  $B/$V.tar.xz" | sha256sum -c --quiet

echo "== source"
rm -rf "$B/$V"
tar -C "$B" -xf "$B/$V.tar.xz"
patch -d "$B/$V" -p1 -s < "$HERE/linux-6.18-mrg5.patch"

echo "== initramfs"
"$REPO/initramfs/build-initramfs.sh" "$B/initramfs"

echo "== firmware"
"$REPO/firmware/fetch-firmware.sh" "$B/firmware/rtl_bt"

echo "== configuration"
mkdir -p "$B/out"
sed -e "s|^CONFIG_INITRAMFS_SOURCE=.*|CONFIG_INITRAMFS_SOURCE=\"$B/initramfs\"|" \
    -e "s|^CONFIG_EXTRA_FIRMWARE_DIR=.*|CONFIG_EXTRA_FIRMWARE_DIR=\"$B/firmware\"|" \
    -e "s|^CONFIG_INITRAMFS_ROOT_UID=.*|CONFIG_INITRAMFS_ROOT_UID=$(id -u)|" \
    -e "s|^CONFIG_INITRAMFS_ROOT_GID=.*|CONFIG_INITRAMFS_ROOT_GID=$(id -g)|" \
    "$HERE/config-mrg5" > "$B/out/.config"
make -C "$B/$V" O="$B/out" ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- olddefconfig > /dev/null
# olddefconfig drops what it cannot satisfy: compare with the released configuration
diff <(grep -v -E '^CONFIG_(INITRAMFS_SOURCE|EXTRA_FIRMWARE_DIR|INITRAMFS_ROOT_[UG]ID|CC_VERSION_TEXT|GCC_VERSION|AS_VERSION|LD_VERSION|CC_IS_|AS_IS_|LD_IS_|CLANG|RUSTC|PAHOLE|CC_CAN_|CC_HAS_|TOOLCHAIN_HAS|GCC_ASM|LD_CAN_|AS_HAS_|BUILDTIME)' "$HERE/config-mrg5" | grep '^CONFIG_') \
     <(grep -v -E '^CONFIG_(INITRAMFS_SOURCE|EXTRA_FIRMWARE_DIR|INITRAMFS_ROOT_[UG]ID|CC_VERSION_TEXT|GCC_VERSION|AS_VERSION|LD_VERSION|CC_IS_|AS_IS_|LD_IS_|CLANG|RUSTC|PAHOLE|CC_CAN_|CC_HAS_|TOOLCHAIN_HAS|GCC_ASM|LD_CAN_|AS_HAS_|BUILDTIME)' "$B/out/.config" | grep '^CONFIG_') \
    || echo "NOTE: the configuration differs from config-mrg5 (see above; a different compiler can change some options)"

echo "== zImage"
make -C "$B/$V" O="$B/out" ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- -j"$JOBS" zImage > "$B/build.log" 2>&1 ||
    { tail -40 "$B/build.log"; exit 1; }
cp "$B/out/arch/arm/boot/zImage" "$B/zImage-mrg5"
ls -l "$B/zImage-mrg5"
sha256sum "$B/zImage-mrg5"
