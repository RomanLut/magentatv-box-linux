#!/bin/sh
# Build the Mupen64Plus-Next libretro core for this box (armv7 + NEON + hard float,
# GLES2 so GLideN64 can use the V3D through GBM/EGL on KMS).
# Run detached: nohup sh build-n64.sh > /root/src/n64-build.log 2>&1 &
set -u
cd /root/src/mupen64plus-libretro-nx || exit 1
make -j3 \
    platform=armv7-neon-hardfloat \
    FORCE_GLES=1 \
    HAVE_PARALLEL_RDP=0 \
    HAVE_PARALLEL_RSP=0 \
    LLE=0 \
    2>&1
echo "=== make exit: $? ==="
ls -la mupen64plus_next_libretro.so 2>/dev/null
