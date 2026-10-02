#!/bin/sh
# Build the GLES3 variant of Mupen64Plus-Next for this box, beside the GLES2
# build of build-n64.sh (checks/53 §9 item 13).
#
# The GLES2 build (FORCE_GLES=1) runs the emulation but GLideN64 hands the
# frontend a black frame on every driver - V3D 3.3 and Mesa's llvmpipe alike
# (RetroArch --max-frames-ss screenshots).  GLideN64 targets GL 3.3 / GLES 3.0;
# libretro builds a separate GLES3 variant (mupen64plus_next_gles3, the one the
# RPi4 platforms select with GLES3=1), and V3D 3.3 offers GLES 3.0.
#
# A copy of the source tree is used, so the GLES2 build and its objects stay.
# Output: /usr/local/lib/libretro/mupen64plus_next_gles3_libretro.so (the name
# Debian's libretro-core-info already describes).
# Run detached: nohup sh build-n64-gles3.sh > /root/src/n64-gles3-build.log 2>&1 &
set -u
SRC=/root/src/mupen64plus-libretro-nx
DST=/root/src/mupen64plus-libretro-nx-gles3
[ -d "$DST" ] || cp -a "$SRC" "$DST" || exit 1
cd "$DST" || exit 1
make clean > /dev/null 2>&1
make -j3 \
    platform=armv7-neon-hardfloat \
    FORCE_GLES3=1 \
    HAVE_PARALLEL_RDP=0 \
    HAVE_PARALLEL_RSP=0 \
    LLE=0 \
    2>&1
echo "=== make exit: $? ==="
ls -la mupen64plus_next_libretro.so 2>/dev/null &&
    install -m 0644 mupen64plus_next_libretro.so /usr/local/lib/libretro/mupen64plus_next_gles3_libretro.so &&
    sha256sum /usr/local/lib/libretro/mupen64plus_next_gles3_libretro.so
