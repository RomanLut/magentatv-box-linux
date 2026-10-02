#!/bin/sh
# Build PPSSPP's libretro core (PSP) for this box on the box itself (checks/41, "Games and
# emulators"). Neither Debian nor libretro's buildbot ships an armhf PPSSPP core.
#
# Upstream's documented libretro build: cmake -DLIBRETRO=ON (PPSSPP's libretro/README).
# USING_GLES2 selects the GLES renderer (it runs GLES 3.0 when the context offers it; V3D 3.3
# does); VULKAN=OFF because V3D 3.3 has no Vulkan driver. The ARM32 JIT is PPSSPP's default
# on armv7. FFmpeg (the games' video and ATRAC audio) comes from PPSSPP's bundled static
# build when it has one for linux/armv7, otherwise from Debian (USE_SYSTEM_FFMPEG).
#
# -marm is required: Debian armhf's gcc emits Thumb-2 by default, and the ARM32 JIT calls C++
# helpers with a plain ARM `BL` whenever they are within 32 MB (QuickCallFunction in
# Common/ArmEmitter.cpp), which cannot enter Thumb code - SIGILL in CoreTiming::Advance as soon
# as the JIT's code region lands near the core (checks/41, PSP). Upstream's libretro Makefile
# builds ARM with -marm; its CMake does so only on ODROID-XU.
#
# Output: /usr/local/lib/libretro/ppsspp_libretro.so, and PPSSPP's assets (fonts, flash0,
# shaders) in the RetroArch system folder as PPSSPP/ (/DATA/Games/bios/PPSSPP), where the
# core looks for them.
#
# Run detached: nohup sh build-ppsspp.sh > /root/src/ppsspp-build.log 2>&1 &
set -u
TAG=${TAG:-v1.20.4}
SRC=/root/src/ppsspp-$TAG
OUT=/usr/local/lib/libretro/ppsspp_libretro.so
SYSDIR=/DATA/Games/bios
JOBS=${JOBS:-3}

echo "=== $(date -Is) PPSSPP $TAG ==="
command -v cmake >/dev/null && command -v g++ >/dev/null && command -v make >/dev/null ||
	DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends cmake g++ make || exit 1
if ! [ -d "$SRC/.git" ]; then
	git clone --depth 1 --branch "$TAG" --recurse-submodules --shallow-submodules \
		https://github.com/hrydgard/ppsspp.git "$SRC" || exit 1
fi
cd "$SRC" || exit 1
git log -1 --format='source: %H %cd'

FF=-DUSE_SYSTEM_FFMPEG=OFF
if ! ls ffmpeg/linux/armv7/lib/libavcodec.a >/dev/null 2>&1; then
	echo "no bundled FFmpeg for linux/armv7: using Debian's"
	DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
		libavcodec-dev libavformat-dev libavutil-dev libswscale-dev libswresample-dev || exit 1
	FF=-DUSE_SYSTEM_FFMPEG=ON
fi

rm -rf build-libretro && mkdir -p build-libretro && cd build-libretro || exit 1
cmake .. -DCMAKE_BUILD_TYPE=Release -DLIBRETRO=ON \
	-DCMAKE_C_FLAGS=-marm -DCMAKE_CXX_FLAGS=-marm \
	-DUSING_GLES2=ON -DVULKAN=OFF -DUSE_DISCORD=OFF -DUSE_FFMPEG=ON "$FF" \
	|| exit 1
echo "=== $(date -Is) cmake done, make -j$JOBS ==="
make -j"$JOBS" ppsspp_libretro 2>&1
echo "=== $(date -Is) make exit: $? ==="
SO=$(find . -name ppsspp_libretro.so | head -1)
[ -n "$SO" ] || { echo "no ppsspp_libretro.so"; exit 1; }
# PPSSPP's own code must be ARM (an odd symbol value is a Thumb function); the prebuilt FFmpeg
# libraries may be Thumb, which is harmless, since the JIT never calls them
thumb=$(readelf -sW "$SO" | awk '$4=="FUNC" && $2 ~ /[13579bdf]$/ {print $8}' | sort -u)
echo "Thumb functions: $(echo "$thumb" | grep -c .), outside FFmpeg: $(echo "$thumb" | grep -vcE '^(av|ff|sws|swr)_')"
echo "$thumb" | grep -qxE '_ZN10CoreTiming7AdvanceEv|_ZN4MIPSComp\w*' &&
	{ echo "PPSSPP code is Thumb: -marm did not apply"; exit 1; }
install -m 0644 "$SO" "$OUT" && sha256sum "$OUT"
mkdir -p "$SYSDIR/PPSSPP" && cp -a "$SRC/assets/." "$SYSDIR/PPSSPP/" && du -sh "$SYSDIR/PPSSPP"
echo "=== $(date -Is) done ==="
