#!/bin/bash
# build-cores.sh: cross-build the RetroArch cores for RetroArch's downloadable games
# (Online Updater -> Content Downloader) on the PC, in a debian:bookworm container,
# so they link against the same glibc (2.36) and libraries as the box.
# Neither Debian nor the libretro buildbot has these for armhf: the buildbot's armhf
# builds stop in 2020 and never had vitaQuake 2 or XRick.
#
#   prboom      Doom                 libretro/libretro-prboom
#   ecwolf      Wolfenstein 3D       libretro/ecwolf (src/libretro)
#   vitaquake2  Quake II             libretro/vitaquake2 with GLES=1, which builds the
#                                    software renderer only: upstream's Makefile turns
#                                    HAVE_OPENGL off for GLES, its GL renderer is for desktop
#                                    GL (the "unix" default links it); the release sets 480x272
#                                    at 50 fps, which keeps up (checks/41, "Core option defaults")
#   xrick       Rick Dangerous       libretro/xrick-libretro
#   scummvm     ScummVM              scummvm/scummvm (backends/platform/libretro),
#                                    platform rpi3 (Cortex-A53, armhf), all default
#                                    engines (the "lite" set lacks adl: Mystery House)
#
# Sources and objects live in the Docker volume mrg5-cores, never on the Windows
# disk (Avast removes cross-compiled ARM binaries there). Run from Git Bash with
# Docker Desktop running; ScummVM takes about an hour (the Docker VM has 2 GB, so
# its compile runs 6 jobs). Results: /src/ship in the volume, stripped; send them
# to the box with
#   docker run --rm -v mrg5-cores:/src mrg5-cores-bookworm tar -C /src/ship -cf - . |
#     ssh admin@<box> 'cat > /tmp/cores.tar'
# and install them into /usr/local/lib/libretro (mode 644), unzip scummvm.zip into
# /DATA/Games/bios, then run
# retroarch-menu-setup.py (checks/41, "Games and emulators").
set -e
export MSYS_NO_PATHCONV=1

docker build -q -t mrg5-cores-bookworm - <<'EOF'
FROM debian:bookworm
RUN dpkg --add-architecture armhf && apt-get update && apt-get install -y --no-install-recommends \
    crossbuild-essential-armhf git ca-certificates make pkg-config zip zlib1g-dev:armhf \
    libgles-dev:armhf libegl-dev:armhf libgl-dev:armhf && rm -rf /var/lib/apt/lists/*
EOF

docker volume create mrg5-cores >/dev/null
docker run --rm -i -v mrg5-cores:/src mrg5-cores-bookworm bash -s <<'EOF'
set -e
X=arm-linux-gnueabihf
# CPU flags go in the environment: on make's command line they would replace
# the Makefiles' own CFLAGS (include paths and all)
export CFLAGS="-mcpu=cortex-a53 -mfpu=neon-fp-armv8 -mfloat-abi=hard"
export CXXFLAGS="$CFLAGS"
CC=$X-gcc CXX=$X-g++
cd /src
for r in libretro/libretro-prboom libretro/ecwolf libretro/vitaquake2 libretro/xrick-libretro scummvm/scummvm; do
	[ -d ${r#*/} ] || git clone -q --depth 1 https://github.com/$r.git
	echo "${r#*/} $(git -C ${r#*/} rev-parse --short HEAD)"
done
mkdir -p out ship

step() { echo "=== $1 $(date +%T)"; }
step prboom
make -C libretro-prboom -j8 platform=unix CC=$CC >out/prboom.log 2>&1
step xrick
make -C xrick-libretro -j8 platform=unix CC=$CC >out/xrick.log 2>&1
step ecwolf
make -C ecwolf/src/libretro -j8 platform=unix CC=$CC CXX=$CXX >out/ecwolf.log 2>&1
step vitaquake2
make -C vitaquake2 -j8 platform=unix GLES=1 GLES3=1 CC=$CC CXX=$CXX >out/vitaquake2.log 2>&1
step scummvm
make -C scummvm/backends/platform/libretro -j6 platform=rpi3 CC=$CC CXX=$CXX \
	AR="$X-ar cru" RANLIB=$X-ranlib >out/scummvm.log 2>&1
# its themes and engine data (scummvm.zip: scummvm/theme, scummvm/extra); unzip it
# into the system directory, /DATA/Games/bios, where the core looks for them
make -C scummvm/backends/platform/libretro platform=rpi3 datafiles >>out/scummvm.log 2>&1
cp scummvm/backends/platform/libretro/scummvm.zip ship/
step done

for f in libretro-prboom/prboom xrick-libretro/xrick ecwolf/src/libretro/ecwolf \
         vitaquake2/vitaquake2 scummvm/backends/platform/libretro/scummvm; do
	$X-strip --strip-unneeded -o ship/${f##*/}_libretro.so ${f}_libretro.so
done
cd ship
sha256sum *.so
# the box has glibc 2.36: nothing may need a newer symbol version
for f in *.so; do
	printf "%-24s %s\n" $f "$($X-readelf -V $f | grep -o -E 'GLIBC_[0-9.]+' | sort -Vu | tail -1)"
done
EOF
